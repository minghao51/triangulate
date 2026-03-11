"""Mapping helpers from case service payloads to HTTP DTOs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.storage import TopicCase

from .schemas import (
    AutomationMode,
    CaseBanner,
    CaseCounts,
    CaseDetailResponse,
    CaseListItem,
    CaseTabs,
    ClaimDTO,
    ClaimEvidenceLinkDTO,
    CreateCaseResponse,
    EvidenceDTO,
    EvidenceVerificationCheckDTO,
    ExceptionDTO,
    PartyDTO,
    ReportDTO,
    RunHistoryItemDTO,
    TimelineEventDTO,
)


STATUS_MAP = {
    "DISCOVERING": "discovering",
    "PROCESSING": "processing",
    "INVESTIGATING": "investigating",
    "REVIEW_READY": "review ready",
    "APPROVED": "approved",
    "REJECTED": "rejected",
    "MONITORING": "monitoring",
    "FAILED": "failed",
}
VERIFICATION_MAP = {
    "CONFIRMED": "confirmed",
    "PROBABLE": "probable",
    "ALLEGED": "alleged",
    "CONTESTED": "contested",
    "DEBUNKED": "debunked",
    "UNVERIFIED": "unknown",
}
AUTOMATION_MAP = {
    "autonomous": "autonomous",
    "blocked": "blocked",
    "safe": "safe",
    "exceptions_only": "safe",
}
POSITION_MAP = {
    "SUPPORTS": "for",
    "CONTESTS": "against",
    "NEUTRAL": "neutral",
    "MIXED": "mixed",
}
RUN_STATUS_MAP = {
    "COMPLETED": "success",
    "FAILED": "error",
    "RUNNING": "running",
    "PENDING": "pending",
    "SKIPPED": "skipped",
}


def _count_open_exceptions(items: list[dict[str, Any]]) -> int:
    return sum(
        1
        for item in items
        if not bool(item.get("resolved_at") or item.get("resolvedAt"))
        and item.get("status", "open") != "resolved"
    )


def _map_status(value: str | None) -> str:
    return STATUS_MAP.get((value or "").upper(), "processing")


def _map_verification_status(value: str | None) -> str:
    return VERIFICATION_MAP.get((value or "").upper(), "unknown")


def _map_automation(value: str | None) -> AutomationMode:
    return AUTOMATION_MAP.get((value or "").lower(), "safe")


def _map_exception(item: dict[str, Any]) -> ExceptionDTO:
    is_open = not (
        bool(item.get("resolved_at") or item.get("resolvedAt"))
        or item.get("status", "open") == "resolved"
    )
    return ExceptionDTO(
        id=item.get("id") or f"exception-{item.get('type', 'unknown')}",
        type=item.get("type", "unknown"),
        message=item.get("message", ""),
        severity=item.get("severity", "medium"),
        recommendedAction=item.get("recommended_action")
        or item.get("recommendedAction")
        or "Review and resolve before proceeding.",
        isOpen=is_open,
    )


def _map_case_counts(article_count: int, event_count: int, review_items: int) -> CaseCounts:
    return CaseCounts(
        articles=article_count,
        events=event_count,
        reviewItems=review_items,
    )


def map_case_list_item(case: TopicCase) -> CaseListItem:
    metadata = case.metadata_json or {}
    exceptions = metadata.get("exception_queue", [])
    return CaseListItem(
        id=case.id,
        query=case.query,
        conflictDomain=case.conflict or "Unspecified",
        status=_map_status(case.status.value if case.status else None),
        stage=(case.current_stage.value if case.current_stage else "BOOTSTRAP"),
        counts=_map_case_counts(case.article_count, case.event_count, case.open_review_items),
        reportPath=case.report_path,
        automationMode=_map_automation(case.routing_mode),
        hasNewMaterial=bool(metadata.get("last_retrieve_changed", False)),
        openExceptionsCount=_count_open_exceptions(exceptions),
        lastUpdated=case.updated_at.isoformat() if case.updated_at else None,
    )


def _map_case_banner(detail: dict[str, Any]) -> CaseBanner:
    case = detail["case"]
    exceptions = detail.get("exceptions", [])
    return CaseBanner(
        id=case["id"],
        query=case["query"],
        conflictDomain=case.get("conflict") or "Unspecified",
        status=_map_status(case.get("status")),
        stage=(case.get("current_stage") or "BOOTSTRAP"),
        counts=_map_case_counts(
            case.get("article_count", 0),
            case.get("event_count", 0),
            case.get("open_review_items", 0),
        ),
        reportPath=case.get("report_path"),
        automationMode=_map_automation(
            (case.get("metadata") or {}).get("bootstrap", {}).get("automation_mode")
            or case.get("routing_mode")
            or (case.get("metadata") or {}).get("routing_mode")
        ),
        hasNewMaterial=bool((case.get("metadata") or {}).get("last_retrieve_changed", False)),
        openExceptionsCount=_count_open_exceptions(exceptions),
        reviewNotes=case.get("review_notes"),
        lastUpdated=case.get("updated_at"),
    )


def _map_claim(claim: dict[str, Any]) -> ClaimDTO:
    return ClaimDTO(
        id=claim["id"],
        text=claim.get("claim_text", ""),
        verificationStatus=_map_verification_status(claim.get("verification_status")),
        type=((claim.get("fact_allegation_type") or "ALLEGATION").lower()),
        controversyScore=claim.get("controversy_score"),
        supportCount=claim.get("support_count", 0),
        opposeCount=claim.get("oppose_count", 0),
        sourceDiversityCount=claim.get("source_diversity_count", 0),
        claimSignature=claim.get("claim_signature") or claim["id"],
        evidence=[
            ClaimEvidenceLinkDTO(
                id=item["id"],
                relation=item.get("relation", "supports"),
                confidenceScore=item.get("confidence_score"),
                sourceDiversityRank=item.get("source_diversity_rank"),
                title=item.get("title"),
                publisher=item.get("publisher"),
                originUrl=item.get("origin_url"),
                sourceType=item.get("source_type"),
            )
            for item in claim.get("evidence", [])
        ],
    )


def _map_evidence(evidence: dict[str, Any], claim_ids_by_evidence: dict[str, list[str]]) -> EvidenceDTO:
    return EvidenceDTO(
        id=evidence["id"],
        title=evidence.get("title"),
        originUrl=evidence.get("origin_url"),
        canonicalUrl=evidence.get("canonical_url"),
        publisher=evidence.get("publisher"),
        sourceType=evidence.get("source_type", "web"),
        verificationStatus=_map_verification_status(evidence.get("verification_status")),
        credibilityTier=evidence.get("credibility_tier") or "unknown",
        requiresHumanReview=bool(evidence.get("requires_human_review")),
        linkedClaims=claim_ids_by_evidence.get(evidence["id"], []),
        verificationChecks=[
            EvidenceVerificationCheckDTO(
                id=item["id"],
                checkType=item.get("check_type", "unknown"),
                result=item.get("result", "unknown"),
                method=item.get("method"),
                notes=item.get("notes"),
                verifiedBy=item.get("verified_by"),
                verifiedAt=item.get("verified_at"),
            )
            for item in evidence.get("verification_checks", [])
        ],
    )


def _map_party(party: dict[str, Any], claims: list[dict[str, Any]], investigations: list[dict[str, Any]]) -> PartyDTO:
    party_name = party.get("canonical_name", "")
    positions = []
    associated_claims = 0
    for claim in claims:
        party_positions = claim.get("party_positions") or {}
        if party_name in party_positions:
            associated_claims += 1
            positions.append(party_positions[party_name])

    stance = "neutral"
    normalized = {POSITION_MAP.get(position, "neutral") for position in positions}
    if len(normalized) > 1:
        stance = "mixed"
    elif normalized:
        stance = normalized.pop()
    elif any(item.get("party_id") == party["id"] for item in investigations):
        stance = "mixed"

    return PartyDTO(
        id=party["id"],
        name=party_name,
        aliases=party.get("aliases") or [],
        description=party.get("description") or "",
        overallStance=stance,
        isModelInferred=True,
        associatedClaimsCount=associated_claims,
    )


def _map_timeline_event(event: dict[str, Any], claims: list[dict[str, Any]]) -> TimelineEventDTO:
    linked_evidence_ids = {
        item["id"]
        for claim in claims
        if claim.get("event_id") == event["id"]
        for item in claim.get("evidence", [])
    }
    return TimelineEventDTO(
        id=event["id"],
        timestamp=event.get("timestamp"),
        title=event.get("title", ""),
        summary=event.get("summary"),
        verificationStatus=_map_verification_status(event.get("verification_status")),
        linkedEvidenceCount=len(linked_evidence_ids),
    )


def _map_run_history(run: dict[str, Any]) -> RunHistoryItemDTO:
    return RunHistoryItemDTO(
        id=run["id"],
        stage=run.get("stage", "UNKNOWN"),
        model=run.get("model_used"),
        durationMs=run.get("duration_ms"),
        status=RUN_STATUS_MAP.get(run.get("status", "").upper(), "pending"),
        fallbackCount=run.get("fallback_count", 0),
        parseFailureCount=run.get("parse_failure_count", 0),
        timestamp=run.get("started_at"),
        message=run.get("error_message"),
    )


def _load_report_content(path: str | None) -> str | None:
    if not path:
        return None
    report_path = Path(path)
    if not report_path.exists():
        return None
    return report_path.read_text(encoding="utf-8")


def map_case_detail(detail: dict[str, Any]) -> CaseDetailResponse:
    claims = detail.get("claims", [])
    claim_ids_by_evidence: dict[str, list[str]] = {}
    for claim in claims:
        for evidence in claim.get("evidence", []):
            claim_ids_by_evidence.setdefault(evidence["id"], []).append(claim["id"])

    return CaseDetailResponse(
        case=_map_case_banner(detail),
        tabs=CaseTabs(
            claims=[_map_claim(claim) for claim in claims],
            evidence=[
                _map_evidence(item, claim_ids_by_evidence)
                for item in detail.get("evidence", [])
            ],
            exceptions=[_map_exception(item) for item in detail.get("exceptions", [])],
            parties=[
                _map_party(item, claims, detail.get("party_investigations", []))
                for item in detail.get("parties", [])
            ],
            timeline=[
                _map_timeline_event(item, claims)
                for item in detail.get("events", [])
            ],
            runHistory=[
                _map_run_history(item)
                for item in detail.get("stage_runs", [])
            ],
            report=ReportDTO(
                status="generated" if detail["case"].get("report_path") else "pending",
                markdownPath=detail["case"].get("report_path"),
                markdownContent=_load_report_content(detail["case"].get("report_path")),
                manifestPath=detail["case"].get("latest_manifest_path"),
            ),
        ),
    )


def map_create_case_response(case: TopicCase) -> CreateCaseResponse:
    return CreateCaseResponse(
        id=case.id,
        status=_map_status(case.status.value if case.status else None),
        stage=(case.current_stage.value if case.current_stage else "BOOTSTRAP"),
    )
