"""Tests for CLI commands."""

import json
from datetime import UTC, datetime
from pathlib import Path
import tempfile

from typer.testing import CliRunner

from src.cli.main import app
from src.cli.commands.ingest import cmd_ingest
from src.cli.commands.query import cmd_query
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


def test_init_db_command():
    """Test the init-db command."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Change to temp directory
        import os

        original_dir = os.getcwd()
        os.chdir(tmpdir)

        try:
            result = runner.invoke(app, ["init-db"])
            assert result.exit_code == 0
            assert "Database initialized" in result.stdout

            # Check database file was created
            db_files = [f for f in Path(".").glob("*.db")]
            assert len(db_files) > 0

        finally:
            os.chdir(original_dir)


def test_ingest_saves_articles(monkeypatch, tmp_path):
    """Test that ingest persists fetched articles for the process command."""

    class FakeFetcher:
        def __init__(self, config):
            self.config = config

        def fetch_all(self, limit=None):
            return [
                {
                    "title": "Test article",
                    "source_name": "test-source",
                    "timestamp": datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC),
                }
            ]

    monkeypatch.setattr("src.cli.commands.ingest.load_config", lambda: {"sources": {}})
    monkeypatch.setattr("src.cli.commands.ingest.ContentFetcher", FakeFetcher)

    original_dir = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        cmd_ingest()

        output_path = tmp_path / "data" / "fetched_articles.json"
        assert output_path.exists()

        with open(output_path) as f:
            payload = json.load(f)

        assert len(payload) == 1
        assert payload[0]["title"] == "Test article"
    finally:
        os.chdir(original_dir)


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
    import asyncio

    from src.cli.commands.process import store_event_in_db

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

    assert asyncio.run(store_event_in_db(event_one)) is True
    assert asyncio.run(store_event_in_db(event_two)) is True


def test_cases_command_lists_topic_cases(tmp_path):
    """The case list command should surface persisted cases."""
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


def test_case_show_command(tmp_path):
    """The case show command should display case metadata."""
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
