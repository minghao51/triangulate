"""Shared runtime helpers for config and service construction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import toml

from src.cases import TopicCaseService
from src.storage import get_database, init_database, run_migrations


def load_runtime_config(config_path: Path = Path("config.toml")) -> dict[str, Any]:
    """Load runtime configuration from disk."""
    with open(config_path, encoding="utf-8") as handle:
        return toml.load(handle)


def build_case_service(output: Path = Path("./output")) -> TopicCaseService:
    """Create the case service with runtime config."""
    config = load_runtime_config()
    configured_path = config.get("database", {}).get("path")
    current_path = get_database().db_path
    database_path = configured_path
    if current_path != "./triangulate.db" and configured_path == "./triangulate.db":
        database_path = current_path
    init_database(database_path)
    run_migrations(database_path)
    return TopicCaseService(config, output_root=output)
