"""Versioned taxonomy loading and persistence helpers."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

import toml

from src.ai.schemas import BiasTaxonomySchema
from src.storage import TaxonomyVersion, get_database


DEFAULT_TAXONOMY_PATH = Path(__file__).resolve().parents[2] / "bias_taxonomy.toml"


def load_bias_taxonomy(path: Path | None = None) -> BiasTaxonomySchema:
    """Load the configured taxonomy file from disk."""
    taxonomy_path = path or DEFAULT_TAXONOMY_PATH
    with open(taxonomy_path, encoding="utf-8") as handle:
        payload = toml.load(handle)
    return BiasTaxonomySchema.model_validate(payload)


def taxonomy_checksum(payload: dict[str, Any]) -> str:
    """Return a stable checksum for a taxonomy payload."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def sync_bias_taxonomy(path: Path | None = None) -> TaxonomyVersion:
    """Persist the active taxonomy version and return the active row."""
    taxonomy_path = path or DEFAULT_TAXONOMY_PATH
    taxonomy = load_bias_taxonomy(taxonomy_path)
    payload = taxonomy.model_dump()
    checksum = taxonomy_checksum(payload)

    session = get_database().get_session_sync()
    try:
        existing = (
            session.query(TaxonomyVersion)
            .filter(
                TaxonomyVersion.taxonomy_kind == taxonomy.taxonomy_kind,
                TaxonomyVersion.version == taxonomy.version,
            )
            .first()
        )
        session.query(TaxonomyVersion).filter(
            TaxonomyVersion.taxonomy_kind == taxonomy.taxonomy_kind
        ).update({"is_active": 0})
        if existing is None:
            existing = TaxonomyVersion(
                id=str(uuid.uuid4()),
                taxonomy_kind=taxonomy.taxonomy_kind,
                version=taxonomy.version,
                path=str(taxonomy_path),
                checksum=checksum,
                taxonomy_json=payload,
                is_active=1,
            )
            session.add(existing)
        else:
            existing.path = str(taxonomy_path)
            existing.checksum = checksum
            existing.taxonomy_json = payload
            existing.is_active = 1
        session.commit()
        return existing
    finally:
        session.close()
