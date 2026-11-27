"""Tests for CLI commands."""

from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from typer.testing import CliRunner

from src.cli.main import app
from src.cli.commands.ingest import cmd_ingest
from src.cli.commands.query import cmd_query
from src.settings import DATABASE_PATH_ENV_VAR
from src.storage.event_store import store_event_in_db
from src.storage.migrations import MIGRATIONS, MigrationManager
from src.storage import (
    CaseStatus,
    Event,
    Review,
    ReviewStatus,
    TopicCase,
    VerificationStatus,
    init_database,
)

runner = CliRunner()


def test_version_command():
    """Test the version command."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "Triangulate" in result.stdout


def _latest_migration_version(db_file: Path) -> int:
    """Read the highest applied migration version straight from the temp database."""
    connection = sqlite3.connect(db_file)
    try:
        row = connection.execute("SELECT MAX(version) FROM _migrations").fetchone()
    finally:
        connection.close()
    return int(row[0] or 0)


def test_init_db_command(monkeypatch, tmp_path):
    """init-db applies every pending migration and is idempotent."""
    monkeypatch.chdir(tmp_path)
    latest = max(migration.version for migration in MIGRATIONS)

    result = runner.invoke(app, ["init-db"])
    assert result.exit_code == 0
    assert "Database initialized" in result.stdout

    db_files = list(tmp_path.glob("*.db"))
    assert len(db_files) > 0
    # Migration 15 is the FTS5 search index; it is recorded even when the
    # runtime SQLite build lacks FTS5, which is the supported degraded state.
    assert _latest_migration_version(db_files[0]) == latest

    rerun = runner.invoke(app, ["init-db"])
    assert rerun.exit_code == 0
    assert "Database initialized" in rerun.stdout
    assert _latest_migration_version(db_files[0]) == latest


def test_init_db_reports_migration_failure_as_failure(monkeypatch, tmp_path):
    """A failing non-FTS migration must not be reported as a successful init."""
    monkeypatch.chdir(tmp_path)
    original_apply = MigrationManager.apply_migration

    def fail_on_non_fts_migration(self, migration):
        if migration.version != 15:
            raise RuntimeError(f"injected migration {migration.version} failure")
        return original_apply(self, migration)

    monkeypatch.setattr(
        MigrationManager, "apply_migration", fail_on_non_fts_migration
    )

    result = runner.invoke(app, ["init-db"])

    assert result.exit_code != 0
    assert "Database initialized" not in result.stdout


def test_ingest_saves_articles(monkeypatch, tmp_path):
    """Test that ingest queues articles via the durable intake service."""

    class FakeService:
        def fetch_and_intake_articles(self, source=None, limit=None, case_id=None):
            return [
                SimpleNamespace(
                    title="Test article",
                    source_name="test-source",
                    published_at=datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC),
                )
            ]

    monkeypatch.setattr("src.cli.commands.ingest.build_case_service", lambda: FakeService())

    cmd_ingest()


def test_query_shows_approved_events(capsys, tmp_path):
    """Test that query joins reviews correctly and returns approved events."""
    db = init_database(str(tmp_path / "triangulate.db"))
    session = db.get_session_sync()

    event = Event(
        id="event-1",
        timestamp=datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC),
        title="Approved event",
        summary="Event summary",
        verification_status=VerificationStatus.PROBABLE,
    )
    review = Review(
        id="review-1",
        event_id="event-1",
        status=ReviewStatus.APPROVED,
    )

    session.add(event)
    session.add(review)
    session.commit()
    session.close()

    cmd_query()

    output = capsys.readouterr().out
    assert "Approved event" in output


def test_store_event_allows_reused_cluster_ids(tmp_path):
    """Test that narratives are scoped to an event instead of globally unique."""
    init_database(str(tmp_path / "triangulate.db"))

    event_one = {
        "id": "event-1",
        "timestamp": datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC),
        "title": "First event",
        "summary": "Summary one",
        "verification_status": "PROBABLE",
        "claims": [],
        "narratives": [
            {"cluster_id": "0", "stance_summary": "Narrative one", "claim_count": 1}
        ],
    }
    event_two = {
        "id": "event-2",
        "timestamp": datetime(2026, 3, 4, 13, 0, 0, tzinfo=UTC),
        "title": "Second event",
        "summary": "Summary two",
        "verification_status": "PROBABLE",
        "claims": [],
        "narratives": [
            {"cluster_id": "0", "stance_summary": "Narrative two", "claim_count": 1}
        ],
    }

    assert store_event_in_db(event_one) is True
    assert store_event_in_db(event_two) is True


def test_case_exception_command(monkeypatch):
    """The case exception command should delegate to the CLI command handler."""
    called = {}

    def fake_handler(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr("src.cli.main.cmd_case_exception_action", fake_handler)
    result = runner.invoke(
        app,
        [
            "case",
            "exception",
            "case-1",
            "exc-1",
            "--action",
            "resolve",
        ],
    )
    assert result.exit_code == 0
    assert called["case_id"] == "case-1"
    assert called["exception_id"] == "exc-1"
    assert called["action"] == "resolve"


def test_case_workflow_command(monkeypatch):
    """The case workflow command should delegate to the workflow handler."""
    called = {}

    def fake_handler(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr("src.cli.main.cmd_show_case_workflow", fake_handler)
    result = runner.invoke(app, ["case", "workflow", "case-1"])
    assert result.exit_code == 0
    assert called["case_id"] == "case-1"


def test_case_evaluate_command(monkeypatch):
    """The case evaluate command should delegate to the evaluation handler."""
    called = {}

    def fake_handler(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr("src.cli.main.cmd_evaluate_case", fake_handler)
    result = runner.invoke(app, ["case", "evaluate", "case-1"])
    assert result.exit_code == 0
    assert called["case_id"] == "case-1"


def test_osint_ingest_command(monkeypatch, tmp_path):
    """The OSINT ingest command should delegate to the OSINT handler."""
    called = {}
    sample = tmp_path / "artifact.json"
    sample.write_text('{"title":"artifact"}', encoding="utf-8")

    def fake_handler(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr("src.cli.main.cmd_osint_ingest", fake_handler)
    result = runner.invoke(
        app,
        [
            "osint",
            "ingest",
            "--tool",
            "spiderfoot",
            "--file",
            str(sample),
            "--case-id",
            "case-1",
        ],
    )
    assert result.exit_code == 0
    assert called["tool"] == "spiderfoot"
    assert called["case_id"] == "case-1"


def test_cases_command_lists_topic_cases(tmp_path, monkeypatch):
    """The case list command should surface persisted cases."""
    monkeypatch.setenv(DATABASE_PATH_ENV_VAR, str(tmp_path / "triangulate.db"))
    db = init_database(str(tmp_path / "triangulate.db"))
    session = db.get_session_sync()
    session.add(
        TopicCase(
            id="case-1",
            query="Example topic",
            slug="example-topic",
            status=CaseStatus.REVIEW_READY,
        )
    )
    session.commit()
    session.close()

    result = runner.invoke(app, ["cases"])
    assert result.exit_code == 0
    assert "case-1" in result.stdout


def test_case_show_command(tmp_path, monkeypatch):
    """The case show command should display case metadata."""
    monkeypatch.setenv(DATABASE_PATH_ENV_VAR, str(tmp_path / "triangulate.db"))
    db = init_database(str(tmp_path / "triangulate.db"))
    session = db.get_session_sync()
    session.add(
        TopicCase(
            id="case-1",
            query="Example topic",
            slug="example-topic",
            status=CaseStatus.REVIEW_READY,
        )
    )
    session.commit()
    session.close()

    result = runner.invoke(app, ["case", "show", "case-1"])
    assert result.exit_code == 0
    assert "Example topic" in result.stdout


def test_case_review_defer_keeps_terminal_case_status(tmp_path, monkeypatch):
    """R06: the real CLI decision reaches the service as an acknowledgement."""
    db_file = tmp_path / "triangulate.db"
    monkeypatch.setenv(DATABASE_PATH_ENV_VAR, str(db_file))
    db = init_database(str(db_file))
    session = db.get_session_sync()
    session.add(
        TopicCase(
            id="case-approved",
            query="Approved topic",
            slug="approved-topic",
            status=CaseStatus.APPROVED,
            metadata_json={
                "exception_queue": [
                    {
                        "id": "exc-cli",
                        "type": "needs_more_sources",
                        "severity": "high",
                        "stage": "RETRIEVE",
                        "status": "open",
                        "message": "Need more sources",
                        "resolution_notes": "Analyst note.",
                        "updated_at": "2026-03-20T10:00:00+00:00",
                    }
                ]
            },
        )
    )
    session.commit()
    session.close()

    result = runner.invoke(
        app,
        [
            "case",
            "review",
            "case-approved",
            "--decision",
            "defer",
            "--notes",
            "Deferred from the CLI",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Case updated: APPROVED" in result.stdout
    session = init_database(str(db_file)).get_session_sync()
    try:
        stored = session.get(TopicCase, "case-approved")
        assert stored is not None
        assert stored.status == CaseStatus.APPROVED
        assert stored.review_notes == "Deferred from the CLI"
        assert stored.last_reviewed_at is not None
        exception = stored.metadata_json["exception_queue"][0]
        assert exception["status"] == "open"
        assert exception["resolution_notes"] == "Analyst note."
        assert exception["updated_at"] == "2026-03-20T10:00:00+00:00"
    finally:
        session.close()


# ============================================================================
# Automation-facing exit codes (service boundaries monkeypatched)
# ============================================================================


def _write_minimal_config(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text('[ai]\nmodel = "test-model"\n', encoding="utf-8")


def test_ingest_hard_failure_exits_nonzero(monkeypatch):
    class FailingService:
        def fetch_and_intake_articles(self, source=None, limit=None):
            raise RuntimeError("source fetch exploded")

    monkeypatch.setattr(
        "src.cli.commands.ingest.build_case_service", lambda: FailingService()
    )

    result = runner.invoke(app, ["ingest"])

    assert result.exit_code != 0
    assert "Error during ingestion" in result.stdout
    assert "source fetch exploded" in result.stdout


def test_ingest_empty_result_is_success(monkeypatch):
    class EmptyService:
        def fetch_and_intake_articles(self, source=None, limit=None):
            return []

    monkeypatch.setattr(
        "src.cli.commands.ingest.build_case_service", lambda: EmptyService()
    )

    result = runner.invoke(app, ["ingest"])

    assert result.exit_code == 0
    assert "No articles fetched" in result.stdout


def test_process_queue_exception_exits_nonzero(monkeypatch):
    class FailingService:
        async def process_intake_queue(self, limit=None):
            raise RuntimeError("queue exploded")

    monkeypatch.setattr(
        "src.cli.commands.process.build_case_service", lambda: FailingService()
    )

    result = runner.invoke(app, ["process"])

    assert result.exit_code != 0
    assert "Error processing intake queue" in result.stdout
    assert "queue exploded" in result.stdout


def test_process_partial_failure_exits_nonzero(monkeypatch):
    class PartialService:
        async def process_intake_queue(self, limit=None):
            return {"selected": 2, "processed": 1, "failed": 1}

    monkeypatch.setattr(
        "src.cli.commands.process.build_case_service", lambda: PartialService()
    )

    result = runner.invoke(app, ["process"])

    assert result.exit_code != 0
    assert "Processed 1 item(s)" in result.stdout
    assert "1 item(s) failed" in result.stdout


def test_process_success_and_no_work_are_zero(monkeypatch):
    summaries = [
        {"selected": 0, "processed": 0, "failed": 0},
        {"selected": 1, "processed": 1, "failed": 0},
    ]

    class Service:
        async def process_intake_queue(self, limit=None):
            return summaries.pop(0)

    monkeypatch.setattr("src.cli.commands.process.build_case_service", lambda: Service())

    no_work = runner.invoke(app, ["process"])
    worked = runner.invoke(app, ["process"])

    assert no_work.exit_code == 0
    assert "No pending intake items" in no_work.stdout
    assert worked.exit_code == 0
    assert "Processed 1 item(s)" in worked.stdout


def test_process_url_fetch_failure_exits_nonzero(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _write_minimal_config(tmp_path)

    async def fail_fetch(url):
        raise RuntimeError("fetch exploded")

    monkeypatch.setattr(
        "src.cli.commands.process_url.fetch_article_content", fail_fetch
    )

    result = runner.invoke(app, ["process-url", "https://example.com/a"])

    assert result.exit_code != 0
    assert "Failed to fetch article" in result.stdout
    assert "fetch exploded" in result.stdout


def test_process_url_processing_failure_exits_nonzero(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _write_minimal_config(tmp_path)

    async def fake_fetch(url):
        return {"title": "Article", "content": "Body", "url": url}

    class FakeWorkflow:
        def __init__(self, config):
            self.config = config

        async def process_article(self, article):
            return None

    monkeypatch.setattr(
        "src.cli.commands.process_url.fetch_article_content", fake_fetch
    )
    monkeypatch.setattr("src.cli.commands.process_url.BaselineWorkflow", FakeWorkflow)

    result = runner.invoke(app, ["process-url", "https://example.com/a"])

    assert result.exit_code != 0
    assert "Failed to process article" in result.stdout


def test_process_url_success_exits_zero(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _write_minimal_config(tmp_path)

    async def fake_fetch(url):
        return {"title": "Article", "content": "Body", "url": url}

    class FakeWorkflow:
        def __init__(self, config):
            self.config = config

        async def process_article(self, article):
            return {"title": "Article", "claims": [], "narratives": []}

    monkeypatch.setattr(
        "src.cli.commands.process_url.fetch_article_content", fake_fetch
    )
    monkeypatch.setattr("src.cli.commands.process_url.BaselineWorkflow", FakeWorkflow)

    result = runner.invoke(app, ["process-url", "https://example.com/a", "--json"])

    assert result.exit_code == 0
    assert '"title": "Article"' in result.stdout
