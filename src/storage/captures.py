"""Immutable evidence capture helpers.

This is the shared, session-owned write path for :class:`EvidenceCapture`.
Keeping it in ``src.storage`` avoids the import cycle caused by
``src.cases.__init__`` eagerly importing the case service; ``src.cases.evidence``
re-exports these helpers as the service-facing name.

Contract (specification §4):

* capture text is normalized for CRLF/CR -> LF only, then hashed as exact UTF-8;
* a separate NFKC + casefold + whitespace-collapse fingerprint is recorded for
  future dependency grouping (``normalization_version``), never for quotation
  offsets and never written back over the raw body;
* capture rows are append-only: identical ``(evidence_id, text_sha256)`` reuses
  the existing row, and a reobservation never overwrites the first body, hash,
  metadata, recorded time or observation time;
* helpers never commit/rollback/close a caller-owned session and never swallow
  errors; capture rows are flushed before the compatibility pointer is set so
  the pointer cannot reference an unflushed row.
"""

from __future__ import annotations

import copy
import hashlib
import unicodedata
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from src.storage.models import (
    CaptureKind,
    EvidenceCapture,
    EvidenceItem,
    utc_now,
)

# Version of the dependency-detection fingerprint normalization. Bump only with
# a documented policy change; stored captures keep the version they were written
# with.
CAPTURE_NORMALIZATION_VERSION = "v1"

_VALID_CAPTURE_KINDS = {kind.value for kind in CaptureKind}


def _normalize_observed_at(observed_at: datetime | None) -> datetime | None:
    """Normalize a known observation timestamp to an aware UTC instant.

    ``None`` stays unknown. Naive datetimes are rejected rather than guessed:
    an unqualified wall-clock value has no honest UTC interpretation, and this
    module must never infer observation time from publication/event timestamps.
    """
    if observed_at is None:
        return None
    if not isinstance(observed_at, datetime):
        raise TypeError("observed_at must be a datetime or None")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError(
            "observed_at must be timezone-aware; naive values are not a known "
            "UTC instant"
        )
    return observed_at.astimezone(UTC)


def _normalize_recorded_at(recorded_at: datetime | None) -> datetime:
    """Return the actual persistence time, normalized to aware UTC."""
    if recorded_at is None:
        return utc_now()
    if not isinstance(recorded_at, datetime):
        raise TypeError("recorded_at must be a datetime or None")
    if recorded_at.tzinfo is None:
        # Internal caller-supplied compatibility value: interpret as UTC.
        return recorded_at.replace(tzinfo=UTC)
    return recorded_at.astimezone(UTC)


def normalize_capture_text(text: str) -> str:
    """Normalize capture text for storage: CRLF/CR -> LF and nothing else.

    Deliberately does not NFKC-normalize, casefold or collapse whitespace: the
    stored body and its hash are the exact extraction used for quotation offsets.
    """
    if text is None:
        raise ValueError("Capture text must not be None; skip capture creation instead")
    if not isinstance(text, str):
        raise TypeError("Capture text must be a str")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def compute_text_sha256(text: str) -> str:
    """SHA-256 over the exact UTF-8 capture body."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprint_text(text: str) -> str:
    """Return the v1 dependency fingerprint text (NFKC + casefold + collapse)."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(folded.split())


def compute_normalized_text_sha256(text: str) -> str:
    """SHA-256 over the v1 fingerprint text, separate from ``text_sha256``."""
    return hashlib.sha256(fingerprint_text(text).encode("utf-8")).hexdigest()


def build_capture_metadata(
    source: Mapping[str, Any] | EvidenceItem,
    *,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze known provenance fields into a deterministic metadata dict.

    Only values actually known to the caller are included. ``published_at`` is
    publication metadata, never an observation time. Unknown values stay absent
    (and therefore null when read back), not fabricated.
    """
    if isinstance(source, Mapping):
        def get(key: str) -> Any:
            return source.get(key)
    else:
        def get(key: str) -> Any:
            return getattr(source, key, None)

    metadata: dict[str, Any] = {}
    for key in (
        "title",
        "publisher",
        "source_type",
        "origin_url",
        "canonical_url",
        "archived_url",
        "published_at",
        "case_article_id",
    ):
        value = get(key)
        if value is not None:
            metadata[key] = value

    capture_metadata = get("capture_metadata")
    if capture_metadata:
        metadata["capture_metadata"] = copy.deepcopy(capture_metadata)

    if extra:
        for key, value in extra.items():
            if value is not None:
                metadata[key] = copy.deepcopy(value)
    return metadata


def get_capture(
    session: Session, *, evidence_id: str, text_sha256: str
) -> EvidenceCapture | None:
    """Look up an existing capture version by evidence and exact body hash."""
    return (
        session.query(EvidenceCapture)
        .filter(
            EvidenceCapture.evidence_id == evidence_id,
            EvidenceCapture.text_sha256 == text_sha256,
        )
        .first()
    )


def upsert_evidence_capture(
    session: Session,
    *,
    evidence_id: str,
    text: str,
    observed_at: datetime | None = None,
    capture_kind: CaptureKind | str = CaptureKind.LIVE,
    metadata: Mapping[str, Any] | None = None,
    recorded_at: datetime | None = None,
) -> EvidenceCapture:
    """Get-or-create an immutable capture version and flush it.

    Identical text for the same evidence (after LF normalization) reuses the
    existing row without touching its first body/time/metadata. A different
    body appends a new row. This function never commits the caller's session.
    """
    normalized = normalize_capture_text(text)
    text_sha256 = compute_text_sha256(normalized)
    kind = capture_kind.value if isinstance(capture_kind, CaptureKind) else str(capture_kind)
    if kind not in _VALID_CAPTURE_KINDS:
        raise ValueError(f"Unsupported capture kind: {capture_kind!r}")

    existing = get_capture(session, evidence_id=evidence_id, text_sha256=text_sha256)
    if existing is not None:
        return existing

    capture = EvidenceCapture(
        id=str(uuid.uuid4()),
        evidence_id=evidence_id,
        text=normalized,
        text_sha256=text_sha256,
        normalized_text_sha256=compute_normalized_text_sha256(normalized),
        normalization_version=CAPTURE_NORMALIZATION_VERSION,
        recorded_at=_normalize_recorded_at(recorded_at),
        observed_at=_normalize_observed_at(observed_at),
        capture_kind=kind,
        metadata_json=copy.deepcopy(dict(metadata or {})),
    )
    session.add(capture)
    # Flush only the capture before any caller sets the current-capture pointer.
    # A broad flush here would let SQLAlchemy insert a pending Claim before its
    # parent Event (no relationships are declared), breaking FK enforcement.
    session.flush([capture])
    return capture


def record_evidence_capture(
    session: Session,
    evidence: EvidenceItem,
    *,
    text: str | None,
    observed_at: datetime | None = None,
    capture_kind: CaptureKind | str = CaptureKind.LIVE,
    metadata: Mapping[str, Any] | None = None,
) -> EvidenceCapture | None:
    """Persist a supplied body, point the evidence at it and sync projection.

    ``None`` means "no incoming body": no capture is created and the existing
    capture/pointer/projection is preserved. An explicit empty string is a real
    (empty) capture; consumers may still reject quoting it.
    """
    if text is None:
        return None

    # Support a newly added EvidenceItem: flush only that parent row first so
    # the capture FK is valid without flushing unrelated pending claims.
    state = sa_inspect(evidence)
    if state.pending:
        session.flush([evidence])

    if metadata is None:
        metadata = build_capture_metadata(evidence)
    capture = upsert_evidence_capture(
        session,
        evidence_id=str(evidence.id),
        text=text,
        observed_at=observed_at,
        capture_kind=capture_kind,
        metadata=metadata,
    )
    # Compatibility projection always matches the normalized current body.
    evidence.current_capture_id = capture.id
    evidence.content = capture.text
    return capture


def materialize_legacy_capture(
    session: Session,
    evidence_id: str,
    *,
    recorded_at: datetime | None = None,
) -> EvidenceCapture | None:
    """Explicitly snapshot an existing ``EvidenceItem.content`` offline.

    This is a service/operator call, never a GET, startup or migration backfill.
    The capture is marked ``legacy_snapshot`` with ``observed_at=None`` because
    the historical observation time is unknown. Repeated calls reuse the first
    body/hash/metadata (and therefore do not overwrite the first recorded time).
    If ``content`` is missing there is nothing honest to copy and ``None`` is
    returned.
    """
    evidence = session.query(EvidenceItem).filter(EvidenceItem.id == evidence_id).first()
    if evidence is None:
        raise LookupError(f"Evidence item {evidence_id!r} does not exist")
    if evidence.content is None:
        return None

    # ORM columns are typed as ``Column[str]`` by the checker; at runtime this
    # value is the stored string body.
    legacy_body = cast(str, evidence.content)
    metadata = build_capture_metadata(evidence)
    capture = upsert_evidence_capture(
        session,
        evidence_id=str(evidence.id),
        text=legacy_body,
        observed_at=None,
        capture_kind=CaptureKind.LEGACY_SNAPSHOT,
        metadata=metadata,
        recorded_at=recorded_at,
    )
    evidence.current_capture_id = capture.id
    evidence.content = capture.text
    return capture


__all__ = [
    "CAPTURE_NORMALIZATION_VERSION",
    "build_capture_metadata",
    "compute_normalized_text_sha256",
    "compute_text_sha256",
    "fingerprint_text",
    "get_capture",
    "materialize_legacy_capture",
    "normalize_capture_text",
    "record_evidence_capture",
    "upsert_evidence_capture",
]
