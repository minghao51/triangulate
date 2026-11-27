"""Side-effect-free operator path settings.

These helpers resolve startup/operator inputs only. They import no database
object, open no file, and never create a directory, so both write and read code
paths can call them safely. Callers capture the result once per app/runtime
instance; values never come from request data or persisted rows.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Operator setting for the directory CLI publication and HTTP readers share.
OUTPUT_ROOT_ENV_VAR = "TRIANGULATE_OUTPUT_ROOT"
#: Compatibility default when the setting is unset or blank.
DEFAULT_OUTPUT_ROOT = Path("./output")

#: Operator environment setting for the SQLite database location.
DATABASE_PATH_ENV_VAR = "DATABASE_PATH"
#: Compatibility default when runtime config and the environment are unset.
DEFAULT_DATABASE_PATH = Path("./triangulate.db")


def resolve_output_root(
    configured: str | Path | None = None, *, cwd: Path | None = None
) -> Path:
    """Resolve the artifact output root lexically without touching the filesystem.

    Precedence: an explicit ``configured`` value, then
    ``TRIANGULATE_OUTPUT_ROOT``, then :data:`DEFAULT_OUTPUT_ROOT`. A blank value
    means the default. A relative result is joined to ``cwd`` -- the documented
    server startup working directory, or the current one when omitted -- and the
    result is normalized lexically (no ``resolve``, so no symlink lookup).

    ``ValueError`` rejects unsafe configuration (a NUL byte or a ``..``
    component) before any normalization.
    """
    raw = configured if configured is not None else os.getenv(OUTPUT_ROOT_ENV_VAR)
    text = "" if raw is None else str(raw).strip()
    if not text:
        text = str(DEFAULT_OUTPUT_ROOT)
    if "\x00" in text:
        raise ValueError(f"{OUTPUT_ROOT_ENV_VAR} must not contain a NUL byte")
    path = Path(text)
    if ".." in path.parts:
        raise ValueError(
            f"{OUTPUT_ROOT_ENV_VAR} must not contain '..' path components"
        )
    base = Path(cwd) if cwd is not None else Path.cwd()
    absolute = path if path.is_absolute() else base / path
    return Path(os.path.normpath(absolute))


def _is_default_database_path(text: str) -> bool:
    """True when a configured value only names the compatibility default.

    ``./triangulate.db`` and ``triangulate.db`` both denote the default, so a
    runtime config that spells out the shipped default does not mask an
    operator's explicit ``DATABASE_PATH``.
    """
    path = Path(text)
    return not path.is_absolute() and Path(os.path.normpath(text)) == Path(
        "triangulate.db"
    )


def resolve_database_path(
    configured: str | Path | None = None, *, cwd: Path | None = None
) -> Path:
    """Resolve the canonical SQLite path without touching the filesystem.

    Precedence, preserving the historical runtime behavior deliberately: a
    non-default ``[database].path`` from runtime config wins; otherwise a
    configured ``DATABASE_PATH`` environment value wins; otherwise
    :data:`DEFAULT_DATABASE_PATH`. A blank value is unset. A relative result is
    joined to ``cwd`` -- the documented server working directory, or the
    current one when omitted -- and normalized lexically (no ``resolve``, so no
    symlink lookup and no directory creation).

    ``ValueError`` rejects a NUL byte before any normalization.
    """
    text = "" if configured is None else str(configured).strip()
    if not text or _is_default_database_path(text):
        env_value = os.getenv(DATABASE_PATH_ENV_VAR)
        text = "" if env_value is None else str(env_value).strip()
        if not text:
            text = str(DEFAULT_DATABASE_PATH)
    if "\x00" in text:
        raise ValueError(f"{DATABASE_PATH_ENV_VAR} must not contain a NUL byte")
    path = Path(text)
    base = Path(cwd) if cwd is not None else Path.cwd()
    absolute = path if path.is_absolute() else base / path
    return Path(os.path.normpath(absolute))
