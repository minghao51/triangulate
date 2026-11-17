"""Keep application database access inside disposable test directories."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.storage import database as storage_database

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_application_database(tmp_path, monkeypatch):
    """Give each test a safe default and reject checkout-local app databases.

    This guards the application Database wrapper, not arbitrary raw sqlite3
    calls. Tests using raw connections must still supply their own tmp_path.
    """
    original_init = storage_database.Database.__init__
    created_databases = []

    def guarded_init(instance, db_path=None):
        target = db_path if db_path is not None else os.getenv(
            "DATABASE_PATH", "./triangulate.db"
        )
        if str(target) != ":memory:":
            resolved = Path(target).expanduser().resolve()
            if resolved.is_relative_to(PROJECT_ROOT):
                raise RuntimeError(
                    "Tests must not open application databases inside the checkout; "
                    "use tmp_path or :memory:."
                )
        original_init(instance, str(target))
        created_databases.append(instance)

    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.setattr(storage_database.Database, "__init__", guarded_init)
    default_database = storage_database.Database(
        str(tmp_path / "default-application.sqlite3")
    )
    default_database.init_db()
    monkeypatch.setattr(storage_database, "_db", default_database)

    try:
        yield
    finally:
        for database in created_databases:
            database.engine.dispose()
