"""Dependency helpers for the HTTP app."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import Request

from src.cases import TopicCaseService
from src.runtime import build_case_service


@lru_cache(maxsize=4)
def _case_service_for_binding(
    output_root: Path, database_path: Path
) -> TopicCaseService:
    """One case service per captured (output root, database path) binding.

    Both values come from the app instance created by ``create_app``; the key
    includes the database path so two app instances configured against different
    databases never share a service.
    """
    return build_case_service(output_root, database_path=database_path)


def get_case_service(request: Request) -> TopicCaseService:
    """Return the shared case service for the app's captured configuration.

    The output root and database path are the same startup-captured values the
    historical artifact readers use, so one app instance can never mix two roots
    or two databases. Case routes keep their existing bootstrap behavior (the
    explicit legacy write path); only the historical readers are read-only.
    """
    return _case_service_for_binding(
        request.app.state.output_root, request.app.state.database_path
    )
