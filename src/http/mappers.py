"""Mapping helpers from case service payloads to HTTP DTOs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.storage import TopicCase

from .schemas import (
    ArbiterReasoningDTO,
    AutomationMode,
    CaseBanner,
    CaseCounts,
    CaseDetailResponse,
    ClaimsOverviewResponse,
    CaseListItem,
    CaseTabs,
    ClaimDTO,
    ClaimEvidenceLinkDTO,
    EvidenceArtifactDTO,
    EvidenceDTO,
    EvidenceLineageDTO,
    EvidenceVerificationCheckDTO,
    ExceptionDTO,
    ReviewAnnotationDTO,
    ReviewAuditEntryDTO,
    ReviewActivityDTO,
    NarrativeDTO,
    OsintArtifactDTO,
    PartyConsensusDTO,
    PartyDTO,
    ReportDTO,
    RunHistoryItemDTO,
    SourceStanceBreakdown,
    TaxonomyDTO,
    TimelineEventDTO,
    WorkflowCheckpointDTO,
    WorkflowDiagnosticsDTO,
    AgentOutputDTO,
    EvaluationResultDTO,
    EvaluationSummaryDTO,
    MonitoringSummaryDTO,
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
        status=item.get("status", "open"),
        recommendedAction=item.get("recommended_action")
        or item.get("recommendedAction")
        or "Review and resolve before proceeding.",
        isOpen=is_open,
    )


def map_review_activity(payload: dict[str, Any]) -> ReviewActivityDTO:
    return ReviewActivityDTO(
        annotations=[
            ReviewAnnotationDTO(
                id=item["id"],
                targetType=item.get("target_type", "case"),
                targetId=item.get("target_id", ""),
                annotationType=item.get("annotation_type", "comment"),
                author=item.get("author", "operator"),
                content=item.get("content", ""),
                metadata=item.get("metadata", {}),
                createdAt=item.get("created_at"),
            )
            for item in payload.get("annotations", [])
        ],
        auditEntries=[
            ReviewAuditEntryDTO(
                id=item["id"],
                actionType=item.get("action_type", "unknown"),
                targetType=item.get("target_type", "case"),
                targetId=item.get("target_id", ""),
                actor=item.get("actor", "operator"),
                rationale=item.get("rationale"),
                metadata=item.get("metadata", {}),
                createdAt=item.get("created_at"),
            )
            for item in payload.get("audit_entries", [])
        ],
    )


def map_evaluation_summary(payload: dict[str, Any]) -> EvaluationSummaryDTO:
    def map_result(item: dict[str, Any]) -> EvaluationResultDTO:
        return EvaluationResultDTO(
            id=item["id"],
            status=item.get("status", "completed"),
            evaluationKind=item.get("evaluation_kind", "case_quality"),
            summary=item.get("summary", {}),
            metrics=item.get("metrics", {}),
            createdAt=item.get("created_at"),
        )

    return EvaluationSummaryDTO(
        latest=map_result(payload["latest"]),
        history=[map_result(item) for item in payload.get("history", [])],
    )


def map_monitoring_summary(payload: dict[str, Any]) -> MonitoringSummaryDTO:
    return MonitoringSummaryDTO(
        cases=payload.get("cases", {}),
        review=payload.get("review", {}),
        pipeline=payload.get("pipeline", {}),
        intake=payload.get("intake", {}),
        evaluation=payload.get("evaluation", {}),
    )
    return ExceptionDTO(
        id=item.get("id") or f"exception-{item.get('type', 'unknown')}",
        type=item.get("type", "unknown"),
        message=item.get("message", ""),
        severity=item.get("severity", "medium"),
        status=item.get("status", "open"),
        recommendedAction=item.get("recommended_action")
        or item.get("recommendedAction")
        or "Review and resolve before proceeding.",
        isOpen=is_open,
    )


def _map_case_counts(article_count: int, event_count: int, review_items: int) -> CaseCounts:
    return CaseCounts(
        articles=article_count or 0,
        events=event_count or 0,
        reviewItems=review_items or 0,
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


def _compute_source_stance_breakdown(claim: dict[str, Any], all_sources: set[str]) -> SourceStanceBreakdown:
    evidence = claim.get("evidence", [])
    agreed = set()
    disagreed = set()
    for item in evidence:
        publisher = item.get("publisher")
        if not publisher:
            continue
        relation = item.get("relation", "supports")
        if relation == "opposes":
            disagreed.add(publisher)
        else:
            agreed.add(publisher)

    didnt_report = all_sources - agreed - disagreed
    return SourceStanceBreakdown(
        agreedSources=sorted(list(agreed)),
        disagreedSources=sorted(list(disagreed)),
        didntReportSources=sorted(list(didnt_report)),
    )


def _map_claim(claim: dict[str, Any], all_sources: set[str] | None = None) -> ClaimDTO:
    arbiter_reasoning = claim.get("arbiter_reasoning")
    mapped_reasoning = None
    if arbiter_reasoning and isinstance(arbiter_reasoning, dict):
        party_consensus = arbiter_reasoning.get("party_consensus", {})
        mapped_reasoning = ArbiterReasoningDTO(
            isFact=arbiter_reasoning.get("is_fact", ""),
            verificationRationale=arbiter_reasoning.get("verification_rationale", ""),
            partyConsensus=PartyConsensusDTO(
                unanimous=party_consensus.get("unanimous", False),
                supportingParties=party_consensus.get("supporting_parties", []),
                opposingParties=party_consensus.get("opposing_parties", []),
                neutralParties=party_consensus.get("neutral_parties", []),
            ),
        )

    party_positions_raw = claim.get("party_positions") or {}
    party_positions = {}
    for party_name, position in party_positions_raw.items():
        mapped_position = POSITION_MAP.get(position.upper() if isinstance(position, str) else position, "neutral")
        if mapped_position in ("for", "against", "neutral"):
            party_positions[party_name] = mapped_position

    evidence_list = [
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
    ]

    stance_breakdown = _compute_source_stance_breakdown(claim, all_sources or set())

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
        narrativeClusterId=claim.get("narrative_cluster_id"),
        arbiterReasoning=mapped_reasoning,
        partyPositions=party_positions,
        evidence=evidence_list,
        sourceStanceBreakdown=stance_breakdown,
    )


def _collect_claim_ids_by_evidence(claims: list[dict[str, Any]]) -> dict[str, list[str]]:
    claim_ids_by_evidence: dict[str, list[str]] = {}
    for claim in claims:
        for evidence in claim.get("evidence", []):
            claim_ids_by_evidence.setdefault(evidence["id"], []).append(claim["id"])
    return claim_ids_by_evidence


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
        lineage=EvidenceLineageDTO(
            caseId=(evidence.get("lineage") or {}).get("case_id", ""),
            eventId=(evidence.get("lineage") or {}).get("event_id"),
            caseArticleId=(evidence.get("lineage") or {}).get("case_article_id"),
            origin=(evidence.get("lineage") or {}).get("origin", "native_ingestion"),
        )
        if evidence.get("lineage")
        else None,
        artifacts=[
            EvidenceArtifactDTO(
                id=item["id"],
                tool=item.get("tool", "unknown"),
                artifactType=item.get("artifact_type", "file"),
                sourcePath=item.get("source_path", ""),
                relation=item.get("relation", "derived_from"),
                importedAt=item.get("imported_at"),
            )
            for item in evidence.get("artifacts", [])
        ],
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

    party_investigation = next(
        (inv for inv in investigations if inv.get("party_id") == party["id"] or inv.get("party_name") == party_name),
        None
    )
    investigation_data = None
    claims_supported = 0
    claims_contested = 0
    if party_investigation:
        inv_data = party_investigation.get("investigation", {})
        investigation_data = party_investigation.get("investigation_data", inv_data)
        claims_supported = len(inv_data.get("claims_supported", []))
        claims_contested = len(inv_data.get("claims_contested", []))

    return PartyDTO(
        id=party["id"],
        name=party_name,
        aliases=party.get("aliases") or [],
        description=party.get("description") or "",
        overallStance=stance,
        isModelInferred=not bool(party.get("is_bootstrap_confirmed")),
        associatedClaimsCount=associated_claims,
        investigationData=investigation_data,
        claimsSupported=claims_supported,
        claimsContested=claims_contested,
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
        locationCountryCode=event.get("location_country_code"),
        locationLat=event.get("location_lat"),
        locationLon=event.get("location_lon"),
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


def _map_narrative(narrative: dict[str, Any]) -> NarrativeDTO:
    return _map_narrative_with_claims(narrative, [])


def _map_narrative_with_claims(
    narrative: dict[str, Any], claims: list[dict[str, Any]]
) -> NarrativeDTO:
    cluster_id = narrative.get("cluster_id", "")
    claims_in_cluster = [
        claim for claim in claims if claim.get("narrative_cluster_id") == cluster_id
    ]
    source_keys = {
        item.get("origin_url") or item.get("publisher") or item.get("id")
        for claim in claims_in_cluster
        for item in claim.get("evidence", [])
        if item.get("origin_url") or item.get("publisher") or item.get("id")
    }
    source_count = len(source_keys)
    if source_count == 0 and claims_in_cluster:
        source_count = max(narrative.get("source_count", 0), 1)

    return NarrativeDTO(
        id=narrative["id"],
        clusterId=cluster_id,
        stanceSummary=narrative.get("stance_summary", ""),
        sourceCount=source_count,
        claimCount=len(claims_in_cluster),
        keyThemes=narrative.get("key_themes", []),
        mainEntities=narrative.get("main_entities", []),
    )


def _load_report_content(path: str | None) -> str | None:
    if not path:
        return None
    report_path = Path(path)
    if not report_path.exists():
        return None
    return report_path.read_text(encoding="utf-8")


def _extract_all_sources(detail: dict[str, Any]) -> set[str]:
    sources: set[str] = set()
    for article in detail.get("articles", []):
        source = article.get("source")
        if source:
            sources.add(source)
    return sources


def map_case_detail(detail: dict[str, Any]) -> CaseDetailResponse:
    claims = detail.get("claims", [])
    claim_ids_by_evidence = _collect_claim_ids_by_evidence(claims)
    all_sources = _extract_all_sources(detail)
    workflow = detail.get("workflow") or {}
    taxonomy = workflow.get("taxonomy")

    return CaseDetailResponse(
        case=_map_case_banner(detail),
        tabs=CaseTabs(
            claims=[_map_claim(claim, all_sources) for claim in claims],
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
            narratives=[
                _map_narrative_with_claims(item, claims)
                for item in detail.get("narratives", [])
            ],
            osintArtifacts=[
                OsintArtifactDTO(
                    id=item["id"],
                    tool=item.get("tool", "unknown"),
                    artifactType=item.get("artifact_type", "file"),
                    sourcePath=item.get("source_path", ""),
                    importedAt=item.get("imported_at"),
                    importMetadata=item.get("import_metadata", {}),
                )
                for item in detail.get("osint_artifacts", [])
            ],
            workflow=WorkflowDiagnosticsDTO(
                taxonomy=TaxonomyDTO(
                    id=taxonomy["id"],
                    kind=taxonomy.get("kind", "bias_review"),
                    version=taxonomy.get("version", "unknown"),
                    path=taxonomy.get("path"),
                    checksum=taxonomy.get("checksum", ""),
                )
                if taxonomy
                else None,
                checkpoints=[
                    WorkflowCheckpointDTO(
                        id=item["id"],
                        stageName=item.get("stage_name", ""),
                        checkpointKey=item.get("checkpoint_key", ""),
                        status=item.get("status", "unknown"),
                        summary=item.get("summary"),
                        retryCount=item.get("retry_count", 0),
                        payload=item.get("payload", {}),
                        createdAt=item.get("created_at"),
                    )
                    for item in workflow.get("checkpoints", [])
                ],
                agentOutputs=[
                    AgentOutputDTO(
                        id=item["id"],
                        stageName=item.get("stage_name", ""),
                        agentName=item.get("agent_name", ""),
                        outputType=item.get("output_type", "stage_result"),
                        summary=item.get("summary"),
                        payload=item.get("payload", {}),
                        taxonomyVersionId=item.get("taxonomy_version_id"),
                        createdAt=item.get("created_at"),
                    )
                    for item in workflow.get("agent_outputs", [])
                ],
            ),
            report=ReportDTO(
                status="generated" if detail["case"].get("report_path") else "pending",
                markdownPath=detail["case"].get("report_path"),
                markdownContent=_load_report_content(detail["case"].get("report_path")),
                manifestPath=detail["case"].get("latest_manifest_path"),
            ),
        ),
    )


def map_claims_overview(detail: dict[str, Any]) -> ClaimsOverviewResponse:
    claims = detail.get("claims", [])
    all_sources = _extract_all_sources(detail)
    return ClaimsOverviewResponse(
        claims=[_map_claim(claim, all_sources) for claim in claims],
        narratives=[
            _map_narrative_with_claims(item, claims)
            for item in detail.get("narratives", [])
        ],
    )
