"""Tests for database migrations."""

import sqlite3

from sqlalchemy import inspect, text

from src.storage.database import init_database
from src.storage.migrations import run_migrations


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

    with db.get_session_sync() as session:
        current_version = session.execute(
            text("SELECT MAX(version) FROM _migrations")
        ).scalar()

    assert current_version == 8


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
