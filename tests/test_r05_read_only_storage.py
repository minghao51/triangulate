"""R05: historical comparison/artifact GETs are storage-read-only.

Each route must work as the *first* request to a fresh app against a missing,
empty, partial or bootstrapped database without creating a directory, database
file, table, index, migration marker or domain row. A missing or unusable store
is a sanitized ``503``; unknown resources on a usable store keep their scoped
``404`` and malformed requests keep ``422``.

The module-level ``app`` in ``src.http.app`` is never used for wiring here: every
app is built explicitly and bound to the disposable database under test, so the
suite's autouse default database cannot accidentally satisfy a regression.
"""

from __future__ import annotations

import hashlib
import importlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

import src.storage.database as storage_database
from src.http.app import (
    HISTORICAL_STORAGE_UNAVAILABLE_DETAIL,
    create_app,
)
from src.settings import DATABASE_PATH_ENV_VAR, resolve_database_path
from src.storage import Base, CaseStatus, TopicCase, get_database, init_database

app_module = importlib.import_module("src.http.app")

CASE_ID = "case-r05"
RUN_ID = "run-r05"
ARTIFACT_ID = "report_markdown"
COMPARISON_URL = f"/api/cases/{CASE_ID}/snapshot-comparison"
LIST_URL = f"/api/cases/{CASE_ID}/investigation-runs/{RUN_ID}/artifacts"
DOWNLOAD_URL = f"{LIST_URL}/{ARTIFACT_ID}"
VALID_COMPARISON = {"baseline": "snapshot-r05-a", "target": "snapshot-r05-b"}


def bound_app(database_path: str | Path):
    """A fresh app whose canonical storage path is this test's database."""
    fresh = create_app()
    fresh.state.database_path = Path(database_path)
    return fresh


def request_for(client: TestClient, route: str):
    if route == "comparison":
        return client.get(COMPARISON_URL, params=VALID_COMPARISON)
    if route == "list":
        return client.get(LIST_URL)
    if route == "download":
        return client.get(DOWNLOAD_URL)
    raise AssertionError(route)


ROUTES = ["comparison", "list", "download"]


def fingerprint(database_path: Path) -> tuple[str, list, list]:
    """Bytes, ``sqlite_master`` entries and migration rows, read-only."""
    raw = database_path.read_bytes()
    connection = sqlite3.connect(
        f"file:{quote(str(database_path), safe='/')}?mode=ro", uri=True
    )
    try:
        entries = connection.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
        try:
            migrations = connection.execute(
                "SELECT version, name FROM _migrations ORDER BY version"
            ).fetchall()
        except sqlite3.OperationalError:
            migrations = []
    finally:
        connection.close()
    return hashlib.sha256(raw).hexdigest(), entries, migrations


def directory_entries(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


def forbid_writes(monkeypatch) -> list[str]:
    """Fail the test if any bootstrap/DDL/migration/builder path is touched."""
    calls: list[str] = []

    def boom(label):
        def _raise(*_args, **_kwargs):
            calls.append(label)
            raise AssertionError(f"historical GET attempted {label}")

        return _raise

    monkeypatch.setattr(Base.metadata, "create_all", boom("create_all"))
    monkeypatch.setattr(Base.metadata, "drop_all", boom("drop_all"))
    monkeypatch.setattr(storage_database.Database, "__init__", boom("Database"))
    monkeypatch.setattr("src.runtime.init_database", boom("init_database"))
    monkeypatch.setattr("src.runtime.run_migrations", boom("run_migrations"))
    monkeypatch.setattr(
        "src.http.dependencies.build_case_service", boom("build_case_service")
    )
    return calls


@pytest.mark.parametrize("route", ROUTES)
def test_first_request_cold_miss_is_sanitized_503_and_creates_nothing(
    route: str, tmp_path: Path, monkeypatch
):
    missing_parent = tmp_path / "absent-node" / "nested"
    missing_db = missing_parent / "missing.sqlite3"
    monkeypatch.setenv(DATABASE_PATH_ENV_VAR, str(missing_db))
    calls = forbid_writes(monkeypatch)

    fresh = create_app()
    # The app selects the operator-configured path at startup, not from the
    # mutable global Database binding.
    assert fresh.state.database_path == missing_db

    with TestClient(fresh) as client:
        response = request_for(client, route)

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": HISTORICAL_STORAGE_UNAVAILABLE_DETAIL}
    assert str(missing_db) not in response.text
    assert str(missing_parent) not in response.text
    assert not missing_parent.exists()
    assert not missing_db.exists()
    assert calls == []


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("state", ["empty", "partial"])
def test_empty_and_partial_schema_are_byte_identical_after_503(
    route: str, state: str, tmp_path: Path, monkeypatch
):
    directory = tmp_path / "store"
    directory.mkdir()
    database_path = directory / "existing.sqlite3"
    if state == "empty":
        database_path.touch()
    else:
        connection = sqlite3.connect(database_path)
        try:
            connection.executescript(
                """
                CREATE TABLE _migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO _migrations (version, name) VALUES (15, 'partial');
                CREATE TABLE topic_cases (id TEXT PRIMARY KEY);
                """
            )
            connection.commit()
        finally:
            connection.close()

    before = fingerprint(database_path)
    before_entries = directory_entries(directory)
    calls = forbid_writes(monkeypatch)

    with TestClient(bound_app(database_path)) as client:
        response = request_for(client, route)

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": HISTORICAL_STORAGE_UNAVAILABLE_DETAIL}
    assert calls == []
    assert fingerprint(database_path) == before
    assert directory_entries(directory) == before_entries


def test_bootstrapped_disposable_db_keeps_results_and_scoped_misses(
    tmp_path: Path, monkeypatch
):
    database_path = tmp_path / "bootstrapped.sqlite3"
    init_database(str(database_path))
    before = fingerprint(database_path)

    with TestClient(bound_app(database_path)) as client:
        missing = client.get(LIST_URL)
        assert missing.status_code == 404
        assert missing.json() == {"detail": "Artifact not found for this case and run"}

        missing = client.get(DOWNLOAD_URL)
        assert missing.status_code == 404

        comparison = client.get(COMPARISON_URL, params=VALID_COMPARISON)
        assert comparison.status_code == 404

        # Request-schema validation and semantic validation keep their 422s.
        assert client.get(COMPARISON_URL).status_code == 422
        same = client.get(
            COMPARISON_URL,
            params={"baseline": "snapshot-r05-a", "target": "snapshot-r05-a"},
        )
        assert same.status_code == 422

        assert client.get("/health").status_code == 200

    assert fingerprint(database_path) == before


def test_historical_read_never_falls_back_to_a_usable_default_db(
    tmp_path: Path, monkeypatch
):
    # The autouse fixture leaves a usable default database behind; binding the
    # app to an absent path must still report unavailable, not read the default.
    default_database = Path(get_database().db_path)
    assert default_database.exists()

    missing = tmp_path / "no-fallback" / "absent.sqlite3"
    with TestClient(bound_app(missing)) as client:
        response = client.get(LIST_URL)

    assert response.status_code == 503
    assert response.json() == {"detail": HISTORICAL_STORAGE_UNAVAILABLE_DETAIL}
    assert not missing.parent.exists()


def test_wal_fixture_is_read_without_bootstrapping_the_database(tmp_path: Path):
    database_path = tmp_path / "wal-mode.sqlite3"
    writer = create_engine(
        f"sqlite:///file:{quote(str(database_path), safe='/')}?mode=rwc&uri=true"
    )
    try:
        Base.metadata.create_all(writer)
    finally:
        writer.dispose()
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("PRAGMA journal_mode=wal").fetchone() == ("wal",)
    finally:
        connection.close()

    before = fingerprint(database_path)
    with TestClient(bound_app(database_path)) as client:
        response = client.get(LIST_URL)

    # SQLite may create its normal -wal/-shm journal sidecars for a WAL file;
    # the database itself is neither bootstrapped nor changed.
    assert response.status_code == 404, response.text
    assert fingerprint(database_path) == before


def test_read_only_open_handles_spaces_and_special_characters(tmp_path: Path):
    directory = tmp_path / "scratch dir #1 %"
    directory.mkdir()
    database_path = directory / "data base ?%.sqlite3"
    # Build the file through an explicitly quoted URI so the special characters
    # exist in the on-disk name the reader must escape.
    writer = create_engine(
        f"sqlite:///file:{quote(str(database_path), safe='/')}?mode=rwc&uri=true"
    )
    try:
        Base.metadata.create_all(writer)
    finally:
        writer.dispose()
    assert database_path.exists()

    with TestClient(bound_app(database_path)) as client:
        response = client.get(LIST_URL)

    # A 404 proves the connection opened successfully through the encoded URI;
    # a quoting bug would surface as 503.
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Artifact not found for this case and run"}


def test_resolve_precedence_matches_documented_selection(monkeypatch, tmp_path):
    monkeypatch.delenv(DATABASE_PATH_ENV_VAR, raising=False)
    assert resolve_database_path(cwd=tmp_path) == tmp_path / "triangulate.db"

    env_path = tmp_path / "env" / "e.sqlite3"
    monkeypatch.setenv(DATABASE_PATH_ENV_VAR, str(env_path))
    assert resolve_database_path(cwd=tmp_path) == env_path
    # A config that merely spells out the shipped default does not mask env.
    assert resolve_database_path("./triangulate.db", cwd=tmp_path) == env_path

    custom = tmp_path / "config" / "custom.sqlite3"
    assert resolve_database_path(str(custom), cwd=tmp_path) == custom
    assert resolve_database_path("relative/custom.sqlite3", cwd=tmp_path) == (
        tmp_path / "relative" / "custom.sqlite3"
    )

    with pytest.raises(ValueError):
        resolve_database_path("bad\x00path", cwd=tmp_path)


def test_create_app_captures_config_then_env_then_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    env_path = tmp_path / "env" / "e.sqlite3"
    monkeypatch.setenv(DATABASE_PATH_ENV_VAR, str(env_path))

    assert create_app().state.database_path == env_path

    (tmp_path / "config.toml").write_text(
        '[database]\npath = "./triangulate.db"\n', encoding="utf-8"
    )
    assert create_app().state.database_path == env_path

    custom = tmp_path / "custom config" / "custom.sqlite3"
    (tmp_path / "config.toml").write_text(
        f'[database]\npath = "{custom}"\n', encoding="utf-8"
    )
    assert create_app().state.database_path == custom

    monkeypatch.delenv(DATABASE_PATH_ENV_VAR, raising=False)
    (tmp_path / "config.toml").unlink()
    assert create_app().state.database_path == tmp_path / "triangulate.db"


def _bootstrap(database_path: Path) -> None:
    init_database(str(database_path))


def _insert_case(database_path: Path, case_id: str) -> None:
    init_database(str(database_path))
    session = get_database().get_session_sync()
    try:
        session.add(
            TopicCase(
                id=case_id,
                query="R05 synthetic case",
                slug=f"{case_id}-slug",
                status=CaseStatus.REVIEW_READY,
            )
        )
        session.commit()
    finally:
        session.close()


def test_request_order_cannot_choose_a_different_database(tmp_path, monkeypatch):
    empty_db = tmp_path / "empty-identity.sqlite3"
    _bootstrap(empty_db)
    seeded_db = tmp_path / "seeded-identity.sqlite3"
    _bootstrap(seeded_db)
    _insert_case(seeded_db, "case-r05-seeded")

    seen: list[Path] = []
    real_open = app_module.open_read_only_session

    @contextmanager
    def recording(path) -> Iterator:
        seen.append(Path(path))
        with real_open(path) as session:
            yield session

    monkeypatch.setattr(app_module, "open_read_only_session", recording)

    # Historical first against the empty identity.
    app_empty = bound_app(empty_db)
    assert app_empty.state.database_path == empty_db
    with TestClient(app_empty) as client:
        assert client.get(COMPARISON_URL, params=VALID_COMPARISON).status_code == 404
        assert client.get("/api/cases").json() == []
    assert seen[-1] == empty_db
    assert app_empty.state.database_path == empty_db

    # Legacy first against the seeded identity; storage must not switch.
    app_seeded = bound_app(seeded_db)
    with TestClient(app_seeded) as client:
        listing = client.get("/api/cases")
        assert [item["id"] for item in listing.json()] == ["case-r05-seeded"]
        assert client.get(COMPARISON_URL, params=VALID_COMPARISON).status_code == 404
    assert seen[-1] == seeded_db
    assert app_seeded.state.database_path == seeded_db


def test_read_only_engines_are_disposed_after_success_and_failure(
    tmp_path: Path, monkeypatch
):
    database_path = tmp_path / "dispose.sqlite3"
    _bootstrap(database_path)
    disposed: list[Engine] = []
    original_dispose = Engine.dispose

    def tracking_dispose(self):
        disposed.append(self)
        return original_dispose(self)

    monkeypatch.setattr(Engine, "dispose", tracking_dispose)

    with TestClient(bound_app(database_path)) as client:
        before = len(disposed)
        assert client.get(LIST_URL).status_code == 404
        assert len(disposed) - before == 1

        before = len(disposed)
        assert client.get(
            "/api/cases/missing-case/investigation-runs/missing-run/artifacts"
        ).status_code == 404
        assert len(disposed) - before == 1

    # Unusable paths release their handle too.
    missing = tmp_path / "gone" / "missing.sqlite3"
    with TestClient(bound_app(missing)) as client:
        before = len(disposed)
        assert client.get(LIST_URL).status_code == 503
        assert len(disposed) - before == 1


@pytest.mark.parametrize(
    "defective_sql",
    ["SELECT no_such_column FROM case_artifacts", "SELEKT 1 FROM case_artifacts"],
)
def test_reader_programming_error_is_actionable_not_503(
    defective_sql: str, tmp_path: Path, monkeypatch
):
    """A present, initialized store keeps a reader defect actionable.

    Readiness (connect, read transaction, declared schema) succeeds here, so only
    the domain phase can fail. SQLite reports a malformed statement or a bad
    column reference as ``OperationalError`` -- the same class a readiness failure
    uses -- and it must reach the client as the app's ordinary ``500`` instead of
    the sanitized "historical storage is unavailable" ``503``. The sanitized body
    and path/identifier text must not appear either.
    """
    database_path = tmp_path / "programming-error.sqlite3"
    _bootstrap(database_path)

    def defective_reader(session, *, case_id, run_id):
        session.execute(text(defective_sql))
        raise AssertionError("the defective reader SQL unexpectedly succeeded")

    with TestClient(bound_app(database_path)) as client:
        # Control: this route on this store is a scoped 404, i.e. the store is
        # recognized as present and initialized.
        assert client.get(LIST_URL).status_code == 404

    monkeypatch.setattr(app_module, "list_run_artifacts", defective_reader)
    disposed: list[Engine] = []
    original_dispose = Engine.dispose

    def tracking_dispose(self):
        disposed.append(self)
        return original_dispose(self)

    monkeypatch.setattr(Engine, "dispose", tracking_dispose)

    with TestClient(bound_app(database_path), raise_server_exceptions=False) as client:
        before = len(disposed)
        response = client.get(LIST_URL)
        # The read-only engine of a failed request is still released.
        assert len(disposed) - before == 1

    assert response.status_code == 500, response.text
    assert HISTORICAL_STORAGE_UNAVAILABLE_DETAIL not in response.text
    assert str(database_path) not in response.text
    assert "no_such_column" not in response.text
    assert "SELEKT" not in response.text
