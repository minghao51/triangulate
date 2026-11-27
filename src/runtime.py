"""Shared runtime helpers for config and service construction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import toml

from src.cases import TopicCaseService
from src.settings import resolve_database_path
from src.storage import init_database, run_migrations


def load_runtime_config(config_path: Path = Path("config.toml")) -> dict[str, Any]:
    """Load runtime configuration from disk.

    A missing file is still an error for callers that require configuration, but
    it is re-raised with the attempted path so the failure is actionable.
    """
    try:
        with open(config_path, encoding="utf-8") as handle:
            return toml.load(handle)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Runtime configuration not found: {config_path}"
        ) from exc


def configured_database_path(
    config_path: Path = Path("config.toml"),
) -> str | None:
    """Read ``[database].path`` without creating or opening anything.

    Returns ``None`` when no runtime config file is present, so callers can fall
    back to the documented precedence (environment, then the default) instead of
    failing for a config-less checkout or test directory.
    """
    try:
        config = load_runtime_config(config_path)
    except FileNotFoundError:
        return None
    value = config.get("database", {}).get("path")
    return None if value is None else str(value)


def build_case_service(
    output: Path = Path("./output"),
    database_path: str | Path | None = None,
) -> TopicCaseService:
    """Create the case service against one explicitly selected database.

    ``database_path`` is the HTTP app's startup-captured canonical path. When
    omitted (CLI), the same side-effect-free precedence is resolved from runtime
    config, ``DATABASE_PATH`` and the compatibility default. Selecting the path
    never reads the mutable global ``Database`` binding.
    """
    config = load_runtime_config()
    if database_path is None:
        database_path = resolve_database_path(
            config.get("database", {}).get("path")
        )
    resolved = str(database_path)
    init_database(resolved)
    run_migrations(resolved)
    return TopicCaseService(config, output_root=output)
