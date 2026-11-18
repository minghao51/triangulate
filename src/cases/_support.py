"""Case service support: utilities, exceptions, metrics."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.storage import (
    CaseStageName,
    CaseArticle,
    Claim,
    ClaimEvidenceLink,
    Event,
    EvidenceItem,
    Review,
    ReviewStatus,
    TopicCase,
)

logger = logging.getLogger(__name__)


STAGE_ORDER = [
    CaseStageName.BOOTSTRAP,
    CaseStageName.RETRIEVE,
    CaseStageName.TRIAGE,
    CaseStageName.INVESTIGATE,
    CaseStageName.ARBITRATE,
    CaseStageName.REPORT,
]

AUTOMATION_MODE_ALIASES = {
    "exceptions_only": "safe",
    "safe": "safe",
    "blocked": "blocked",
    "autonomous": "autonomous",
}


@dataclass
class CaseRunContext:
    """Mutable state shared across a case run."""

    case: TopicCase
    run_started_at: datetime
    output_dir: Path
    bootstrap_result: dict[str, Any] | None = None
    fetch_result: dict[str, Any] | None = None
    selected_articles: list[CaseArticle] | None = None
    processed_events: list[dict[str, Any]] | None = None
    report_bundle: dict[str, Any] | None = None
    exception_queue: list[dict[str, Any]] | None = None
    changed: bool = False
    # Delay-aware stage failure recorded by a persistence callback (B02).
    stage_failure: dict[str, Any] | None = None
    # Grouped invocation identity (R01). ``None`` means the caller is exercising
    # a stage outside a recorded ``run_case`` invocation; legacy/direct stage
    # calls legitimately leave the grouped origin unknown.
    investigation_run_id: str | None = None
    run_trigger: str | None = None
    requested_start_stage: CaseStageName | None = None
    predecessor_run_id: str | None = None
    # Per-stage outcomes recorded by ``_execute_stage`` for honest run coverage.
    stage_outcomes: list[dict[str, Any]] = field(default_factory=list)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "case"


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return _utcnow()


def _fingerprint_article(article: dict[str, Any]) -> str:
    payload = f"{article.get('url','')}|{article.get('title','')}|{article.get('source','')}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _payload_checksum(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _claim_signature(claim_text: str) -> str:
    return hashlib.sha256(claim_text.lower().strip().encode("utf-8")).hexdigest()


def _normalize_automation_mode(value: str | None) -> str:
    return AUTOMATION_MODE_ALIASES.get((value or "").strip().lower(), "safe")


def _execution_automation_mode(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized == "exceptions_only":
        return "autonomous"
    return _normalize_automation_mode(value)


# ─── Exception System ────────────────────────────────────────────────────────


def _make_exception(
    *,
    exception_type: str,
    stage: CaseStageName,
    message: str,
    severity: str,
    details: dict[str, Any] | None = None,
    status: str = "open",
) -> dict[str, Any]:
    fingerprint = _payload_checksum(
        {
            "type": exception_type,
            "stage": stage.value,
            "message": message,
            "details": details or {},
        }
    )
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"exception:{fingerprint}")),
        "type": exception_type,
        "stage": stage.value,
        "severity": severity,
        "status": status,
        "message": message,
        "details": details or {},
        "created_at": _utcnow().isoformat(),
        "updated_at": _utcnow().isoformat(),
    }


def _coerce_exception(item: dict[str, Any], stage: CaseStageName | None = None) -> dict[str, Any]:
    if "id" in item and "status" in item and "severity" in item:
        normalized = dict(item)
        normalized.setdefault("updated_at", _utcnow().isoformat())
        return normalized
    return _make_exception(
        exception_type=item.get("type", "unknown_exception"),
        stage=stage or CaseStageName.REVIEW,
        message=item.get("message", ""),
        severity=item.get("severity", "medium"),
        details=item.get("details")
        or {
            key: value
            for key, value in item.items()
            if key not in {"type", "message", "severity"}
        },
        status=item.get("status", "open"),
    )


def _merge_exception_lists(
    base: list[dict[str, Any]], updates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in base + updates:
        normalized = _coerce_exception(item)
        existing = merged.get(normalized["id"], {})
        merged[normalized["id"]] = {**existing, **normalized, "updated_at": _utcnow().isoformat()}
    return list(merged.values())


def _get_open_exceptions(metadata_json: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in metadata_json.get("exception_queue", [])
        if item.get("status", "open") != "resolved"
    ]


def _resolve_case_exceptions(
    metadata_json: dict[str, Any], *, decision: str, notes: str | None
) -> dict[str, Any]:
    exception_queue = []
    for item in metadata_json.get("exception_queue", []):
        normalized = _coerce_exception(item)
        if decision in {"reject"}:
            normalized["status"] = "resolved"
        elif decision in {"action_required", "exception"}:
            normalized["status"] = "open"
        normalized["updated_at"] = _utcnow().isoformat()
        if notes:
            normalized["resolution_notes"] = notes
        exception_queue.append(normalized)
    return {**metadata_json, "exception_queue": exception_queue}


def _compute_open_review_items(
    metadata_json: dict[str, Any], reviews: list[Review]
) -> int:
    review_count = sum(
        1
        for review in reviews
        if review.status in {ReviewStatus.PENDING, ReviewStatus.ACTION_REQUIRED}
    )
    return review_count + len(_get_open_exceptions(metadata_json))


# ─── Metrics Derivation ──────────────────────────────────────────────────────


def _derive_confidence(result: dict[str, Any]) -> float | None:
    if "confidence_score" in result:
        return result["confidence_score"]
    if result.get("event_count") == 0:
        return 0.0
    if result.get("route_counts"):
        total = sum(result["route_counts"].values()) or 1
        return result["route_counts"].get("baseline_only", 0) / total
    return None


def _derive_controversy(result: dict[str, Any]) -> float | None:
    if "controversy_score" in result:
        return result["controversy_score"]
    contested = len(result.get("contested_event_ids", []))
    total = result.get("event_count", 0)
    if total:
        return contested / total
    return None


def _count_nested_flag(payload: Any, *, flag_name: str) -> int:
    if isinstance(payload, dict):
        count = 1 if payload.get(flag_name) else 0
        return count + sum(
            _count_nested_flag(value, flag_name=flag_name)
            for value in payload.values()
        )
    if isinstance(payload, list):
        return sum(_count_nested_flag(item, flag_name=flag_name) for item in payload)
    return 0


def _count_parse_failures(payload: Any) -> int:
    if isinstance(payload, dict):
        count = 1 if payload.get("parse_status") in {"fallback", "error"} else 0
        return count + sum(_count_parse_failures(value) for value in payload.values())
    if isinstance(payload, list):
        return sum(_count_parse_failures(item) for item in payload)
    return 0


# ─── Claim Aggregate Recomputation ────────────────────────────────────────────


def _recompute_case_claim_aggregates(session, case_id: str) -> None:
    claims = (
        session.query(Claim)
        .join(Event, Claim.event_id == Event.id)
        .filter(Event.case_id == case_id)
        .all()
    )
    if not claims:
        return
    evidence_links = (
        session.query(ClaimEvidenceLink)
        .filter(ClaimEvidenceLink.claim_id.in_([claim.id for claim in claims]))
        .all()
    )
    evidence_items = (
        session.query(EvidenceItem)
        .filter(EvidenceItem.case_id == case_id)
        .all()
    )
    evidence_by_id = {item.id: item for item in evidence_items}
    links_by_claim: dict[str, list[ClaimEvidenceLink]] = {}
    for link in evidence_links:
        links_by_claim.setdefault(link.claim_id, []).append(link)
    grouped: dict[str, dict[str, Any]] = {}
    for claim in claims:
        signature = claim.claim_signature or _claim_signature(claim.claim_text)
        bucket = grouped.setdefault(
            signature,
            {"support": 0, "oppose": 0, "sources": set(), "party_positions": {}},
        )
        for link in links_by_claim.get(claim.id, []):
            evidence = evidence_by_id.get(link.evidence_id)
            publisher = (
                evidence.publisher if evidence else None
            ) or (evidence.origin_url if evidence else None) or "unknown"
            bucket["sources"].add(publisher)
            if link.relation == "opposes":
                bucket["oppose"] += 1
            else:
                bucket["support"] += 1
        bucket["party_positions"].update(claim.party_positions or {})

    for claim in claims:
        signature = claim.claim_signature or _claim_signature(claim.claim_text)
        aggregate = grouped[signature]
        claim.claim_signature = signature
        claim.support_count = aggregate["support"]
        claim.oppose_count = aggregate["oppose"]
        claim.source_diversity_count = len(aggregate["sources"])
        if aggregate["party_positions"]:
            claim.party_positions = aggregate["party_positions"]
