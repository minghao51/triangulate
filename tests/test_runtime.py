"""Tests for runtime service bootstrap."""

from __future__ import annotations


from sqlalchemy import create_engine, inspect, text

from src.runtime import build_case_service


def test_build_case_service_runs_migrations(tmp_path, monkeypatch):
    """Service bootstrap should initialize the configured database and apply migrations."""
    db_path = tmp_path / "triangulate.db"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[ai]",
                'model = "test-model"',
                "",
                "[database]",
                f'path = "{db_path}"',
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    service = build_case_service(output=tmp_path / "output")

    assert service.config["database"]["path"] == str(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    assert "_migrations" in inspector.get_table_names()

    with engine.connect() as connection:
        current_version = connection.execute(
            text("SELECT MAX(version) FROM _migrations")
        ).scalar()

    assert current_version == 3
