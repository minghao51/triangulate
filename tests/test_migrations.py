"""Tests for database migrations."""

import sqlite3

import pytest
from sqlalchemy import inspect, text

from src.storage.captures import compute_normalized_text_sha256, compute_text_sha256
from src.storage.database import init_database
from src.storage.migrations import run_migrations
from src.storage.models import CaseStatus, EvidenceItem, TopicCase

# Highest migration version after S01 added the optional FTS5 index.
LATEST_MIGRATION_VERSION = 15



LEGACY_REVIEW_ROW = (
    "review-legacy-1",
    "event-legacy-1",
    "approved",
    "2026-04-01 09:30:00",
    "Previous human approval notes.",
    "2026-03-31 08:00:00",
)


def _current_version(engine) -> int:
    with engine.connect() as connection:
        return connection.execute(text("SELECT MAX(version) FROM _migrations")).scalar()



def _create_legacy_core_tables(connection) -> None:
    """Create the pre-merge core tables that migrations 7+ still touch.

    Only tables the remaining migrations alter are created, and only when the
    fixture has not already created a richer version of them.
    """
    connection.execute(
        """CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            timestamp TIMESTAMP,
            title TEXT,
            summary TEXT,
            verification_status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS narratives (
            id TEXT PRIMARY KEY,
            cluster_id TEXT,
            stance_summary TEXT,
            source_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS party_investigations (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            party_id TEXT NOT NULL,
            investigation_data JSON NOT NULL,
            party_stance TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS claims (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            source_id TEXT,
            claim_text TEXT NOT NULL,
            narrative_cluster_id TEXT,
            verification_status TEXT NOT NULL,
            party_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS case_articles (
            id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            source TEXT,
            published_at TEXT,
            relevance_score REAL NOT NULL DEFAULT 0.0,
            fingerprint TEXT NOT NULL,
            content TEXT,
            raw_payload JSON,
            first_seen_at TIMESTAMP,
            last_seen_at TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            is_new INTEGER NOT NULL DEFAULT 1
        );"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS parties (
            id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL UNIQUE,
            aliases JSON NOT NULL,
            description TEXT,
            event_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS topic_cases (
            id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            metadata_json JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            url TEXT UNIQUE,
            last_fetched TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );"""
    )

def _create_legacy_database(db_path) -> None:
    """Create a pre-B01 database: version 6 with a legacy ``reviews`` table.

    Deliberately raw SQL so the old schema really lacks the new columns; an ORM
    table would already include them and prove nothing about the upgrade path.
    """
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE _migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for version in range(1, 7):
            connection.execute(
                "INSERT INTO _migrations (version, name) VALUES (?, ?)",
                (version, f"legacy migration {version}"),
            )
        connection.execute(
            """
            CREATE TABLE reviews (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                reviewed_at TIMESTAMP,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO reviews (id, event_id, status, reviewed_at, notes, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            LEGACY_REVIEW_ROW,
        )
        _create_legacy_core_tables(connection)
        connection.commit()
    finally:
        connection.close()


def _create_legacy_v11_database_with_stage_history(db_path) -> None:
    """Create a version-11 database with stage/event rows but no grouped runs.

    Deliberately raw SQL so the old schema really lacks the new table/columns;
    an ORM-created database would already include them and prove nothing about
    the upgrade path.
    """
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE _migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        for version in range(1, 12):
            connection.execute(
                "INSERT INTO _migrations (version, name) VALUES (?, ?)",
                (version, f"legacy migration {version}"),
            )
        connection.execute("CREATE TABLE topic_cases (id TEXT PRIMARY KEY)")
        connection.execute(
            """CREATE TABLE case_stage_runs (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                stage_name TEXT NOT NULL,
                status TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE events (
                id TEXT PRIMARY KEY,
                case_id TEXT,
                case_run_id TEXT,
                title TEXT
            )"""
        )
        connection.execute(
            "INSERT INTO topic_cases (id) VALUES ('case-legacy-r01')"
        )
        connection.execute(
            "INSERT INTO case_stage_runs (id, case_id, stage_name, status)"
            " VALUES ('stage-legacy-r01', 'case-legacy-r01', 'REPORT', 'COMPLETED')"
        )
        connection.execute(
            "INSERT INTO events (id, case_id, case_run_id, title)"
            " VALUES ('event-legacy-r01', 'case-legacy-r01',"
            " 'stage-legacy-r01', 'Legacy event')"
        )
        connection.commit()
    finally:
        connection.close()


def test_migration_12_adds_grouped_runs_without_rewriting_stage_history(tmp_path):
    """A version-11 database gains the grouped-run schema; old rows stay unknown."""
    db_path = tmp_path / "triangulate-legacy-v11.db"
    _create_legacy_v11_database_with_stage_history(db_path)

    run_migrations(str(db_path))
    # Idempotent: applying the registry again must not fail or invent origins.
    run_migrations(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        version = connection.execute(
            "SELECT MAX(version) FROM _migrations"
        ).fetchone()[0]
        assert version == LATEST_MIGRATION_VERSION

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "investigation_runs" in tables
        for table_name in ("case_stage_runs", "events"):
            columns = {
                row[1]
                for row in connection.execute(
                    f"PRAGMA table_info({table_name})"
                ).fetchall()
            }
            assert "investigation_run_id" in columns

        stage_row = connection.execute(
            "SELECT id, case_id, stage_name, status, investigation_run_id"
            " FROM case_stage_runs"
        ).fetchone()
        assert stage_row[:4] == (
            "stage-legacy-r01",
            "case-legacy-r01",
            "REPORT",
            "COMPLETED",
        )
        assert stage_row[4] is None

        event_row = connection.execute(
            "SELECT id, case_id, case_run_id, title, investigation_run_id"
            " FROM events"
        ).fetchone()
        assert event_row[:4] == (
            "event-legacy-r01",
            "case-legacy-r01",
            "stage-legacy-r01",
            "Legacy event",
        )
        assert event_row[4] is None
    finally:
        connection.close()



def _create_legacy_v12_database_with_case(db_path) -> None:
    """Create a version-12 database whose cases have no writer-owner fields."""
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE _migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        for version in range(1, 13):
            connection.execute(
                "INSERT INTO _migrations (version, name) VALUES (?, ?)",
                (version, f"legacy migration {version}"),
            )
        connection.execute(
            """CREATE TABLE topic_cases (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                metadata_json JSON
            )"""
        )
        connection.execute(
            "INSERT INTO topic_cases (id, query, slug, status, metadata_json)"
            " VALUES ('case-legacy-r02', 'Legacy query', 'legacy-query',"
            " 'REVIEW_READY', '{}')"
        )
        connection.commit()
    finally:
        connection.close()


def test_migration_13_adds_case_owner_fields_without_claiming(tmp_path):
    """A version-12 database gains nullable owner fields; no writer is claimed."""
    db_path = tmp_path / "triangulate-legacy-v12.db"
    _create_legacy_v12_database_with_case(db_path)

    run_migrations(str(db_path))
    run_migrations(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        version = connection.execute(
            "SELECT MAX(version) FROM _migrations"
        ).fetchone()[0]
        assert version == LATEST_MIGRATION_VERSION

        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(topic_cases)").fetchall()
        }
        assert {
            "owner_token",
            "owner_kind",
            "owner_ref_id",
            "owner_claimed_at",
        } <= columns

        row = connection.execute(
            "SELECT id, query, slug, status, owner_token, owner_kind,"
            " owner_ref_id, owner_claimed_at FROM topic_cases"
        ).fetchone()
        assert row[:4] == (
            "case-legacy-r02",
            "Legacy query",
            "legacy-query",
            "REVIEW_READY",
        )
        # Migration 13 claims no writer and invents no ownership.
        assert row[4:] == (None, None, None, None)
    finally:
        connection.close()


def test_run_migrations_is_idempotent_on_fresh_database(tmp_path):
    """Fresh ORM-created databases should not fail when migrations run."""
    db_path = tmp_path / "triangulate.db"

    db = init_database(str(db_path))
    run_migrations(str(db_path))

    inspector = inspect(db.engine)
    claim_columns = {column["name"] for column in inspector.get_columns("claims")}

    assert "fact_allegation_type" in claim_columns
    assert "arbiter_reasoning" in claim_columns
    assert "party_positions" in claim_columns
    assert "controversy_score" in claim_columns
    assert "party_investigations" in inspector.get_table_names()
    assert "topic_cases" in inspector.get_table_names()
    assert "case_stage_runs" in inspector.get_table_names()
    assert "case_artifacts" in inspector.get_table_names()
    assert "case_articles" in inspector.get_table_names()
    assert "intake_items" in inspector.get_table_names()
    assert "monitor_checkpoints" in inspector.get_table_names()
    assert "osint_artifacts" in inspector.get_table_names()
    assert "evidence_artifact_links" in inspector.get_table_names()
    assert "workflow_checkpoints" in inspector.get_table_names()
    assert "taxonomy_versions" in inspector.get_table_names()
    assert "agent_outputs" in inspector.get_table_names()
    assert "investigation_runs" in inspector.get_table_names()
    assert "case_snapshots" in inspector.get_table_names()
    snapshot_columns = {
        column["name"] for column in inspector.get_columns("case_snapshots")
    }
    assert {
        "id",
        "case_id",
        "investigation_run_id",
        "baseline_snapshot_id",
        "schema_version",
        "identity_version",
        "policy_version",
        "semantic_hash",
        "payload_json",
        "delta_json",
        "created_at",
    } <= snapshot_columns
    event_columns = {column["name"] for column in inspector.get_columns("events")}
    stage_run_columns = {
        column["name"] for column in inspector.get_columns("case_stage_runs")
    }
    assert "investigation_run_id" in event_columns
    assert "investigation_run_id" in stage_run_columns
    topic_case_columns = {
        column["name"] for column in inspector.get_columns("topic_cases")
    }
    assert {
        "owner_token",
        "owner_kind",
        "owner_ref_id",
        "owner_claimed_at",
    } <= topic_case_columns

    with db.get_session_sync() as session:
        current_version = session.execute(
            text("SELECT MAX(version) FROM _migrations")
        ).scalar()

    assert current_version == LATEST_MIGRATION_VERSION


def test_run_migrations_upgrades_existing_v6_database_columns(tmp_path):
    """Migration 7 should add new columns for existing databases, not just new tables."""
    db_path = tmp_path / "triangulate-v6.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE _migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO _migrations (version, name) VALUES (6, 'Add event location schema');

            CREATE TABLE topic_cases (
                id TEXT PRIMARY KEY
            );
            CREATE TABLE case_stage_runs (
                id TEXT PRIMARY KEY,
                case_id TEXT
            );
            CREATE TABLE evidence_items (
                id TEXT PRIMARY KEY
            );
            CREATE TABLE events (
                id TEXT PRIMARY KEY,
                case_id TEXT,
                case_run_id TEXT
            );
            CREATE TABLE narratives (
                id TEXT PRIMARY KEY
            );
            CREATE TABLE party_investigations (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                party_id TEXT NOT NULL,
                investigation_data JSON NOT NULL,
                party_stance TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        _create_legacy_core_tables(connection)
        connection.commit()
    finally:
        connection.close()

    db = init_database(str(db_path))
    run_migrations(str(db_path))

    inspector = inspect(db.engine)
    event_columns = {column["name"] for column in inspector.get_columns("events")}
    narrative_columns = {
        column["name"] for column in inspector.get_columns("narratives")
    }
    investigation_columns = {
        column["name"] for column in inspector.get_columns("party_investigations")
    }

    assert "workflow_route" in event_columns
    assert "source_url" in event_columns
    assert "key_themes" in narrative_columns
    assert "main_entities" in narrative_columns
    assert "party_name" in investigation_columns


def _create_legacy_v8_database_with_evidence(db_path) -> None:
    """Create a version-7 SQL database with legacy evidence content."""
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE _migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for version in range(1, 8):
            connection.execute(
                "INSERT INTO _migrations (version, name) VALUES (?, ?)",
                (version, f"legacy migration {version}"),
            )
        connection.execute(
            """
            CREATE TABLE evidence_items (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                content TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO evidence_items (id, case_id, content) VALUES (?, ?, ?)",
            ("evidence-legacy-1", "case-legacy-1", "Legacy body\r\nkept verbatim."),
        )
        _create_legacy_core_tables(connection)
        connection.commit()
    finally:
        connection.close()


def test_migration_9_upgrades_legacy_reviews_and_preserves_decision(tmp_path):
    """A version-6 database gains the review hash columns without data loss."""
    db_path = tmp_path / "triangulate-legacy.db"
    _create_legacy_database(db_path)

    run_migrations(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        version = connection.execute("SELECT MAX(version) FROM _migrations").fetchone()[0]
        assert version == LATEST_MIGRATION_VERSION
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(reviews)").fetchall()
        }
        assert {"analysis_hash", "previous_decision_json"} <= columns

        row = connection.execute(
            "SELECT id, event_id, status, reviewed_at, notes, analysis_hash,"
            " previous_decision_json FROM reviews"
        ).fetchone()
        assert row[:5] == LEGACY_REVIEW_ROW[:5]
        # Nullable new fields: an unknown baseline stays unknown, never invented.
        assert row[5] is None
        assert row[6] is None
    finally:
        connection.close()


def test_migration_9_is_repeatable_and_keeps_existing_rows(tmp_path):
    """Re-running migrations is a no-op for version 7 and preserves review rows."""
    db_path = tmp_path / "triangulate-repeat.db"
    _create_legacy_database(db_path)

    run_migrations(str(db_path))
    run_migrations(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM _migrations ORDER BY version"
            ).fetchall()
        ]
        assert versions.count(LATEST_MIGRATION_VERSION) == 1
        if versions:
            assert versions == list(range(1, LATEST_MIGRATION_VERSION + 1))

        count = connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        assert count == 1
        row = connection.execute(
            "SELECT id, event_id, status, reviewed_at, notes FROM reviews"
        ).fetchone()
        assert row == LEGACY_REVIEW_ROW[:5]
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Migration 11: validated claim citations + link alignment fields
# ---------------------------------------------------------------------------


def _create_v9_database_with_link(db_path) -> None:
    """A version-8 SQL database with a legacy link row (raw ``opposes``)."""
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE _migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for version in range(1, 9):
            connection.execute(
                "INSERT INTO _migrations (version, name) VALUES (?, ?)",
                (version, f"legacy migration {version}"),
            )
        connection.execute(
            """
            CREATE TABLE topic_cases (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                slug TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO topic_cases (id, query, slug) VALUES (?, ?, ?)",
            ("case-legacy-1", "Legacy case", "legacy-case"),
        )
        connection.execute(
            """
            CREATE TABLE evidence_items (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                content TEXT,
                current_capture_id TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE evidence_captures (
                id TEXT PRIMARY KEY,
                evidence_id TEXT NOT NULL,
                text TEXT NOT NULL,
                text_sha256 TEXT NOT NULL,
                normalized_text_sha256 TEXT NOT NULL,
                normalization_version TEXT NOT NULL DEFAULT 'v1',
                recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                observed_at TIMESTAMP,
                capture_kind TEXT NOT NULL DEFAULT 'live',
                metadata_json JSON NOT NULL DEFAULT '{}'
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE claim_evidence_links (
                id TEXT PRIMARY KEY,
                claim_id TEXT NOT NULL,
                evidence_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                source_diversity_rank INTEGER NOT NULL DEFAULT 1,
                confidence_score REAL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO claim_evidence_links "
            "(id, claim_id, evidence_id, relation) VALUES (?, ?, ?, ?)",
            ("link-legacy-1", "claim-legacy-1", "evidence-legacy-1", "opposes"),
        )
        _create_legacy_core_tables(connection)
        connection.commit()
    finally:
        connection.close()


def test_migration_10_adds_capture_schema_without_copying_legacy_content(tmp_path):
    """Migration 10 is schema-only: legacy content is not materialized."""
    db_path = tmp_path / "triangulate-legacy-captures.db"
    _create_legacy_v8_database_with_evidence(db_path)

    run_migrations(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        version = connection.execute(
            "SELECT MAX(version) FROM _migrations"
        ).fetchone()[0]
        assert version == LATEST_MIGRATION_VERSION
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(evidence_items)"
            ).fetchall()
        }
        assert "current_capture_id" in columns
        assert connection.execute(
            "SELECT COUNT(*) FROM evidence_captures"
        ).fetchone()[0] == 0
        row = connection.execute(
            "SELECT content, current_capture_id FROM evidence_items"
        ).fetchone()
        assert row == ("Legacy body\r\nkept verbatim.", None)
        indexes = {
            row[1]
            for row in connection.execute(
                "PRAGMA index_list(evidence_captures)"
            ).fetchall()
        }
        assert "uq_evidence_capture_evidence_text" in indexes
    finally:
        connection.close()


@pytest.mark.parametrize("schema", ["fresh", "upgrade"])
def test_migration_10_pointer_fk_parity_and_enforcement(tmp_path, schema):
    """Both schema paths enforce the pointer FK without materializing content."""
    db_path = tmp_path / f"capture-fk-{schema}.db"
    original_body = "Legacy body\r\nkept verbatim."
    if schema == "legacy":
        _create_legacy_v8_database_with_evidence(db_path)
    else:
        db = init_database(str(db_path))
        with db.get_session_sync() as session:
            case = TopicCase(
                id="case-legacy-1", query="FK parity", slug="capture-fk-parity",
                status=CaseStatus.INVESTIGATING,
            )
            session.add(case)
            session.flush([case])
            session.add(
                EvidenceItem(
                    id="evidence-legacy-1",
                    case_id=case.id,
                    evidence_type="article",
                    source_type="rss",
                    content=original_body,
                )
            )
            session.commit()

    run_migrations(str(db_path))
    run_migrations(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(evidence_items)"
        ).fetchall()
        assert any(
            row[2:5] == ("evidence_captures", "current_capture_id", "id")
            for row in foreign_keys
        )
        assert connection.execute(
            "SELECT content, current_capture_id FROM evidence_items WHERE id=?",
            ("evidence-legacy-1",),
        ).fetchone() == (original_body, None)
        assert connection.execute(
            "SELECT COUNT(*) FROM evidence_captures"
        ).fetchone()[0] == 0

        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            connection.execute(
                "UPDATE evidence_items SET current_capture_id=? WHERE id=?",
                ("missing-capture", "evidence-legacy-1"),
            )
        connection.rollback()

        # Explicit test fixture, not migration backfill: a valid target works.
        body = original_body.replace("\r\n", "\n")
        connection.execute(
            "INSERT INTO evidence_captures "
            "(id, evidence_id, text, text_sha256, normalized_text_sha256, "
            "normalization_version, recorded_at, observed_at, capture_kind, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, NULL, ?, ?)",
            (
                "capture-parity", "evidence-legacy-1", body,
                compute_text_sha256(body), compute_normalized_text_sha256(body),
                "v1", "legacy_snapshot", "{}",
            ),
        )
        connection.execute(
            "UPDATE evidence_items SET current_capture_id=?, content=? WHERE id=?",
            ("capture-parity", body, "evidence-legacy-1"),
        )
        connection.commit()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT current_capture_id FROM evidence_items WHERE id=?",
            ("evidence-legacy-1",),
        ).fetchone() == ("capture-parity",)
    finally:
        connection.close()


def test_migration_10_is_repeatable_and_never_materializes_captures(tmp_path):
    """Repeated migration runs leave legacy content uncopied."""
    db_path = tmp_path / "triangulate-legacy-captures-repeat.db"
    _create_legacy_v8_database_with_evidence(db_path)

    run_migrations(str(db_path))
    run_migrations(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM _migrations ORDER BY version"
            ).fetchall()
        ]
        assert versions == list(range(1, LATEST_MIGRATION_VERSION + 1))
        assert connection.execute(
            "SELECT COUNT(*) FROM evidence_captures"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT content FROM evidence_items"
        ).fetchone()[0] == "Legacy body\r\nkept verbatim."
    finally:
        connection.close()


def test_migration_11_adds_citation_schema_without_backfill_or_rewrite(tmp_path):
    """Migration 11 is additive: no citation rows and no legacy relation rewrite."""
    db_path = tmp_path / "triangulate-v8-citations.db"
    _create_v9_database_with_link(db_path)

    run_migrations(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        version = connection.execute("SELECT MAX(version) FROM _migrations").fetchone()[0]
        assert version == LATEST_MIGRATION_VERSION

        link_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(claim_evidence_links)"
            ).fetchall()
        }
        assert {
            "capture_id",
            "citation_id",
            "quote",
            "start_char",
            "end_char",
            "alignment_status",
            "assessment_origin",
            "assessment_version",
            "assessment_metadata",
        } <= link_columns

        citation_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(claim_citations)"
            ).fetchall()
        }
        assert {
            "id",
            "case_id",
            "capture_id",
            "original_claim_id",
            "claim_signature",
            "text",
            "relationship",
            "quote",
            "start_char",
            "end_char",
            "alignment_status",
            "alignment_version",
            "assessment_origin",
            "assessment_version",
            "metadata_json",
            "recorded_at",
        } <= citation_columns

        # No backfill / no invented citations.
        assert connection.execute(
            "SELECT COUNT(*) FROM claim_citations"
        ).fetchone()[0] == 0

        # Legacy row untouched: raw relation preserved and honest defaults only.
        row = connection.execute(
            "SELECT relation, capture_id, citation_id, quote, start_char, end_char,"
            " alignment_status FROM claim_evidence_links WHERE id=?",
            ("link-legacy-1",),
        ).fetchone()
        assert row == ("opposes", None, None, None, None, None, "not_provided")
    finally:
        connection.close()


def test_migration_11_is_repeatable_and_schema_only(tmp_path):
    """Repeated runs add nothing new and never rewrite or copy data."""
    db_path = tmp_path / "triangulate-v8-citations-repeat.db"
    _create_v9_database_with_link(db_path)

    run_migrations(str(db_path))
    run_migrations(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM _migrations ORDER BY version"
            ).fetchall()
        ]
        assert versions == list(range(1, LATEST_MIGRATION_VERSION + 1))
        assert connection.execute(
            "SELECT COUNT(*) FROM claim_citations"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT relation FROM claim_evidence_links WHERE id=?",
            ("link-legacy-1",),
        ).fetchone() == ("opposes",)
    finally:
        connection.close()


@pytest.mark.parametrize("schema", ["fresh", "upgrade"])
def test_migration_11_fk_parity_and_enforcement(tmp_path, schema):
    """Both schema paths expose/enforce the same link + citation references."""
    db_path = tmp_path / f"citation-fk-{schema}.db"
    if schema == "upgrade":
        _create_v9_database_with_link(db_path)
    else:
        db = init_database(str(db_path))
        with db.get_session_sync() as session:
            case = TopicCase(
                id="case-legacy-1",
                query="Citation FK parity",
                slug="citation-fk-parity",
                status=CaseStatus.INVESTIGATING,
            )
            session.add(case)
            session.flush([case])
            session.add(
                EvidenceItem(
                    id="evidence-legacy-1",
                    case_id="case-legacy-1",
                    evidence_type="article",
                    source_type="rss",
                    content="Body",
                )
            )
            session.commit()

    run_migrations(str(db_path))
    run_migrations(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")

        link_fks = connection.execute(
            "PRAGMA foreign_key_list(claim_evidence_links)"
        ).fetchall()
        assert any(
            row[2:5] == ("evidence_captures", "capture_id", "id") for row in link_fks
        )
        assert any(
            row[2:5] == ("claim_citations", "citation_id", "id") for row in link_fks
        )

        citation_fks = connection.execute(
            "PRAGMA foreign_key_list(claim_citations)"
        ).fetchall()
        assert any(row[2:5] == ("topic_cases", "case_id", "id") for row in citation_fks)
        assert any(
            row[2:5] == ("evidence_captures", "capture_id", "id")
            for row in citation_fks
        )
        # The historical claim id is deliberately NOT a foreign key.
        assert not any(row[3] == "original_claim_id" for row in citation_fks)

        if schema == "upgrade":
            with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
                connection.execute(
                    "UPDATE claim_evidence_links SET capture_id=? WHERE id=?",
                    ("missing-capture", "link-legacy-1"),
                )
            connection.rollback()

        body = "Body"
        capture_id = f"capture-{schema}"
        connection.execute(
            "INSERT INTO evidence_captures "
            "(id, evidence_id, text, text_sha256, normalized_text_sha256, "
            "normalization_version, recorded_at, observed_at, capture_kind, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, NULL, ?, ?)",
            (
                capture_id,
                "evidence-legacy-1",
                body,
                compute_text_sha256(body),
                compute_normalized_text_sha256(body),
                "v1",
                "live",
                "{}",
            ),
        )
        connection.execute(
            "INSERT INTO claim_citations "
            "(id, case_id, capture_id, original_claim_id, claim_signature, text, "
            "relationship, quote, start_char, end_char, alignment_status, "
            "alignment_version, assessment_origin, assessment_version, "
            "metadata_json, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (
                f"citation-{schema}",
                "case-legacy-1",
                capture_id,
                "claim-that-does-not-exist",
                "sig",
                "Claim text",
                "reported_by",
                "Body",
                0,
                4,
                "exact",
                "exact-codepoint-v1",
                "collector",
                None,
                "{}",
            ),
        )
        connection.commit()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

        # An unknown citation target is rejected under FK enforcement.
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            connection.execute(
                "INSERT INTO claim_citations "
                "(id, case_id, capture_id, text, relationship, quote, start_char, "
                "end_char, alignment_status, alignment_version, metadata_json, "
                "recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (
                    "citation-bad-capture",
                    "case-legacy-1",
                    "missing-capture",
                    "t",
                    "reported_by",
                    "q",
                    0,
                    1,
                    "exact",
                    "exact-codepoint-v1",
                    "{}",
                ),
            )
        connection.rollback()
    finally:
        connection.close()
