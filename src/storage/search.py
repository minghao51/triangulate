"""Transactional, case-scoped FTS5 synchronization for current evidence and claims.

All writes use the caller's SQLAlchemy transaction. The application-level hook is
invoked by the event-store owner after its complete replacement is flushed; it is
therefore covered by the same case fencing and rollback as source writes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.storage.models import Claim, Event, EvidenceCapture, EvidenceItem

TABLE = "case_search_index"


@dataclass(frozen=True)
class SearchCapability:
    available: bool
    reason: str | None = None


def _fts5_module_available(session: Session) -> bool:
    """Check module registration without creating a probe virtual table."""
    try:
        return session.execute(
            text("SELECT 1 FROM pragma_module_list WHERE name='fts5'")
        ).first() is not None
    except Exception as exc:
        # Older SQLite versions may not expose pragma_module_list. Their compile
        # options provide a read-only fallback; unrelated DB errors still escape.
        message = str(exc).lower()
        if "no such table" not in message and "syntax error" not in message:
            raise
        options = session.execute(text("PRAGMA compile_options")).scalars().all()
        return any("ENABLE_FTS5" in str(option).upper() for option in options)


def probe_search_capability(session: Session) -> SearchCapability:
    """Cheap, read-only capability check; operational failures propagate."""
    if not _fts5_module_available(session):
        return SearchCapability(False, "SQLite FTS5 module is not compiled into this SQLite build.")
    found = session.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": TABLE},
    ).first()
    if not found:
        return SearchCapability(False, "FTS5 module is available, but case_search_index is missing (migration 15 is not applied).")
    # Compile/resolve the virtual table without scanning its corpus.
    session.execute(text(f"SELECT rowid FROM {TABLE} LIMIT 0"))
    return SearchCapability(True)


def build_evidence_row(session: Session, evidence: EvidenceItem) -> dict[str, Any]:
    capture = session.get(EvidenceCapture, evidence.current_capture_id) if evidence.current_capture_id else None
    return {
        "case_id": evidence.case_id, "entity_type": "evidence", "entity_id": evidence.id,
        "title": evidence.title or "", "body": capture.text if capture else "",
        "signature": "", "event_id": evidence.event_id or "", "party_id": "",
        "publisher": evidence.publisher or "", "status": "", "published_at": evidence.published_at or "",
    }


def build_claim_row(claim: Claim, event: Event) -> dict[str, Any]:
    return {
        "case_id": event.case_id, "entity_type": "claim", "entity_id": claim.id,
        "title": "", "body": claim.claim_text or "", "signature": claim.claim_signature or "",
        "event_id": claim.event_id, "party_id": claim.party_id or "", "publisher": "",
        "status": claim.verification_status.value if hasattr(claim.verification_status, "value") else str(claim.verification_status),
        "published_at": "",
    }


def deterministic_rowid(entity_type: str, entity_id: str) -> int:
    """Map an entity identity to a stable positive FTS5 rowid.

    A 63-bit digest makes accidental collisions extraordinarily unlikely
    (birthday bound). Entity IDs are primary keys and therefore unique within
    each entity type; case is metadata rather than part of the row identity.
    """
    identity = f"{entity_type}\0{entity_id}".encode("utf-8")
    return (int.from_bytes(hashlib.blake2b(identity, digest_size=8).digest(), "big") & ((1 << 63) - 1)) or 1


def _delete_row(session: Session, case_id: str, entity_type: str, entity_id: str) -> None:
    session.execute(text(f"DELETE FROM {TABLE} WHERE rowid=:rowid"),
                    {"rowid": deterministic_rowid(entity_type, entity_id)})


def _upsert_row(session: Session, row: dict[str, Any]) -> None:
    session.execute(text(f"""INSERT OR REPLACE INTO {TABLE}
        (rowid,case_id,entity_type,entity_id,title,body,signature,event_id,party_id,publisher,status,published_at)
        VALUES (:rowid,:case_id,:entity_type,:entity_id,:title,:body,:signature,:event_id,:party_id,:publisher,:status,:published_at)"""),
        {**row, "rowid": deterministic_rowid(row["entity_type"], row["entity_id"])})


def upsert_index_row(session: Session, row: dict[str, Any]) -> None:
    """Replace a single indexed entity row without committing."""
    if probe_search_capability(session).available:
        _upsert_row(session, row)


def delete_index_row(session: Session, case_id: str, entity_type: str, entity_id: str) -> None:
    if probe_search_capability(session).available:
        _delete_row(session, case_id, entity_type, entity_id)


def sync_event_index(session: Session, event_id: str) -> None:
    """Synchronize all current evidence/claims after an event-store write."""
    capability = probe_search_capability(session)
    if not capability.available:
        return
    session.execute(text(f"DELETE FROM {TABLE} WHERE event_id=:event"), {"event": event_id})
    event = session.get(Event, event_id)
    if event is None or event.case_id is None:
        return
    claims = session.query(Claim).filter(Claim.event_id == event_id).all()
    evidence = session.query(EvidenceItem).filter(
        EvidenceItem.case_id == event.case_id, EvidenceItem.event_id == event_id
    ).all()
    for item in evidence:
        _upsert_row(session, build_evidence_row(session, item))
    for claim in claims:
        _upsert_row(session, build_claim_row(claim, event))


def sync_evidence_index(session: Session, evidence: EvidenceItem) -> None:
    """Synchronize one standalone case-owned evidence write in its owner txn."""
    capability = probe_search_capability(session)
    if not capability.available:
        return
    if evidence.case_id is not None:
        _delete_row(session, evidence.case_id, "evidence", evidence.id)
    else:
        _delete_row(session, "", "evidence", evidence.id)
    if evidence.case_id is None:
        return
    session.flush([evidence])
    _upsert_row(session, build_evidence_row(session, evidence))


def indexed_counts(session: Session, case_id: str) -> dict[str, int]:
    if not probe_search_capability(session).available:
        return {"evidence": 0, "claim": 0}
    rows = session.execute(text(f"SELECT entity_type,count(*) FROM {TABLE} WHERE case_id=:case GROUP BY entity_type"), {"case": case_id})
    counts = {"evidence": 0, "claim": 0}
    counts.update({kind: int(count) for kind, count in rows})
    return counts


def rebuild_case_search_index(session: Session, case_id: str) -> dict[str, Any]:
    """Delete/rebuild one case's rows. Caller claims and commits the case owner."""
    capability = probe_search_capability(session)
    if not capability.available:
        return {"capability": capability, "counts": {"evidence": 0, "claim": 0}}
    session.execute(text(f"DELETE FROM {TABLE} WHERE case_id=:case"), {"case": case_id})
    evidence_rows = session.query(EvidenceItem).filter(EvidenceItem.case_id == case_id).all()
    for evidence in evidence_rows:
        _upsert_row(session, build_evidence_row(session, evidence))
    claims = session.query(Claim).join(Event, Claim.event_id == Event.id).filter(Event.case_id == case_id).all()
    for claim in claims:
        event = session.get(Event, claim.event_id)
        if event is not None:
            _upsert_row(session, build_claim_row(claim, event))
    rows = session.execute(text(f"SELECT entity_type,count(*) FROM {TABLE} WHERE case_id=:case GROUP BY entity_type"), {"case": case_id})
    counts = {"evidence": 0, "claim": 0}
    counts.update({kind: int(count) for kind, count in rows})
    return {"capability": capability, "counts": counts}


__all__ = ["SearchCapability", "build_claim_row", "build_evidence_row", "delete_index_row", "indexed_counts", "probe_search_capability", "rebuild_case_search_index", "sync_event_index", "sync_evidence_index", "upsert_index_row"]
