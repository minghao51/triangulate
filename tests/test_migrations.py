"""Tests for database migrations."""

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

    with db.get_session_sync() as session:
        current_version = session.execute(
            text("SELECT MAX(version) FROM _migrations")
        ).scalar()

    assert current_version == 1
