"""Regression coverage for the application-database test safety boundary."""

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import inspect

from src.storage import database as storage_database

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_default_application_database_is_temporary(tmp_path):
    database = storage_database.get_database()
    assert Path(database.db_path) == tmp_path / "default-application.sqlite3"
    assert inspect(database.engine).has_table("sources")


def test_checkout_database_rejected_before_engine_creation():
    with patch.object(storage_database, "create_engine") as create_engine:
        with pytest.raises(RuntimeError, match="inside the checkout"):
            storage_database.Database(str(PROJECT_ROOT / "triangulate.db"))
        create_engine.assert_not_called()


def test_relative_checkout_default_is_rejected(monkeypatch):
    monkeypatch.chdir(PROJECT_ROOT)
    with patch.object(storage_database, "create_engine") as create_engine:
        with pytest.raises(RuntimeError, match="inside the checkout"):
            storage_database.Database()
        create_engine.assert_not_called()


def test_explicit_temporary_database_remains_supported(tmp_path):
    path = tmp_path / "explicit.sqlite3"
    database = storage_database.init_database(str(path))
    assert storage_database.get_database() is database
    assert path.exists()


def test_in_memory_database_remains_supported():
    database = storage_database.Database(":memory:")
    database.init_db()
    assert inspect(database.engine).has_table("sources")
