"""Dependency helpers for the HTTP app."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.cases import TopicCaseService
from src.runtime import build_case_service
from src.storage import get_database


@lru_cache(maxsize=1)
def get_case_service() -> TopicCaseService:
    """Return a shared case service for HTTP handlers."""
    get_database().init_db()
    return build_case_service(Path("./output"))
