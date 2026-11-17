"""Case serialization: ORM models → dict payloads for HTTP layer."""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_

from src.storage import (
    AgentOutput,
    CaseArtifact,
    CaseArticle,
    CaseStageRun,
    Claim,
    ClaimEvidenceLink,
    EvidenceArtifactLink,
    Event,
    EvidenceItem,
    EvidenceVerificationCheck,
    Narrative,
    OsintArtifact,
    Party,
    PartyInvestigation,
    Review,
    TaxonomyVersion,
    TopicCase,
    WorkflowCheckpoint,
)

from src.cases._support import (
    _claim_signature,
    _compute_open_review_items,
    _merge_exception_lists,
)


def build_executive_summary_from_payload(events: list[dict[str, Any]]) -> str:
    """Build an executive summary string from a list of event dicts."""
    if not events:
        return "No events have been promoted into the case timeline yet."
    contested = sum(1 for event in events if event["verification_status"] == "CONTESTED")
    probable = sum(1 for event in events if event["verification_status"] == "PROBABLE")
    confirmed = sum(1 for event in events if event["verification_status"] == "CONFIRMED")
    return (
        f"This case currently tracks {len(events)} event(s): "
        f"{confirmed} confirmed, {probable} probable, and {contested} contested."
    )


def build_case_detail_payload(session, case: TopicCase) -> dict[str, Any]:
    """Serialize case and all related ORM objects into a dict for the HTTP layer."""

    stage_runs = (
        session.query(CaseStageRun)
        .filter(CaseStageRun.case_id == case.id)
        .order_by(CaseStageRun.started_at.asc())
        .all()
    )
    articles = (
        session.query(CaseArticle)
        .filter(CaseArticle.case_id == case.id)
        .order_by(CaseArticle.relevance_score.desc())
        .all()
    )
    events = (
        session.query(Event)
        .filter(Event.case_id == case.id)
        .order_by(Event.timestamp.desc())
        .all()
    )
    artifacts = (
        session.query(CaseArtifact)
        .filter(CaseArtifact.case_id == case.id)
        .order_by(CaseArtifact.created_at.desc())
        .all()
    )
    claims = (
        session.query(Claim)
        .join(Event, Claim.event_id == Event.id)
        .filter(Event.case_id == case.id)
        .all()
    )
    narratives = (
        session.query(Narrative)
        .filter(
            or_(*[Narrative.cluster_id.like(f"{event.id}:%") for event in events])
        )
        .all()
        if events
        else []
    )
    party_investigations = (
        session.query(PartyInvestigation)
        .filter(PartyInvestigation.event_id.in_([event.id for event in events]))
        .all()
        if events
        else []
    )
    evidence_items = (
        session.query(EvidenceItem)
        .filter(EvidenceItem.case_id == case.id)
        .all()
    )
    verification_checks = (
        session.query(EvidenceVerificationCheck)
        .filter(
            EvidenceVerificationCheck.evidence_id.in_([item.id for item in evidence_items])
        )
        .all()
        if evidence_items
        else []
    )
    claim_links = (
        session.query(ClaimEvidenceLink)
        .filter(ClaimEvidenceLink.claim_id.in_([claim.id for claim in claims]))
        .all()
        if claims
        else []
    )
    evidence_artifact_links = (
        session.query(EvidenceArtifactLink)
        .filter(EvidenceArtifactLink.evidence_id.in_([item.id for item in evidence_items]))
        .all()
        if evidence_items
        else []
    )
    osint_artifacts = (
        session.query(OsintArtifact)
        .filter(OsintArtifact.case_id == case.id)
        .order_by(OsintArtifact.imported_at.desc())
        .all()
    )
    workflow_checkpoints = (
        session.query(WorkflowCheckpoint)
        .filter(WorkflowCheckpoint.case_id == case.id)
        .order_by(WorkflowCheckpoint.created_at.desc())
        .all()
    )
    agent_outputs = (
        session.query(AgentOutput)
        .filter(AgentOutput.case_id == case.id)
        .order_by(AgentOutput.created_at.desc())
        .all()
    )
    active_taxonomy = (
        session.query(TaxonomyVersion)
        .filter(TaxonomyVersion.is_active == 1)
        .order_by(TaxonomyVersion.created_at.desc())
        .first()
    )
    party_ids = {
        claim.party_id for claim in claims if getattr(claim, "party_id", None)
    }
    party_ids.update(
        investigation.party_id
        for investigation in party_investigations
        if getattr(investigation, "party_id", None)
    )
    party_names = set()
    for claim in claims:
        party_names.update((claim.party_positions or {}).keys())
    parties = []
    if events:
        party_filters = [Party.event_id.in_([event.id for event in events])]
        if party_ids:
            party_filters.append(Party.id.in_(party_ids))
        if party_names:
            party_filters.append(Party.canonical_name.in_(party_names))
        parties = session.query(Party).filter(or_(*party_filters)).all()
    reviews = (
        session.query(Review)
        .join(Event, Review.event_id == Event.id)
        .filter(Event.case_id == case.id)
        .all()
    )

    evidence_by_id = {item.id: item for item in evidence_items}
    checks_by_evidence: dict[str, list[EvidenceVerificationCheck]] = {}
    for check in verification_checks:
        checks_by_evidence.setdefault(check.evidence_id, []).append(check)
    links_by_claim: dict[str, list[ClaimEvidenceLink]] = {}
    for link in claim_links:
        links_by_claim.setdefault(link.claim_id, []).append(link)
    artifact_links_by_evidence: dict[str, list[EvidenceArtifactLink]] = {}
    for link in evidence_artifact_links:
        artifact_links_by_evidence.setdefault(link.evidence_id, []).append(link)
    osint_artifacts_by_id = {artifact.id: artifact for artifact in osint_artifacts}

    serialized_evidence = []
    for item in evidence_items:
        serialized_evidence.append(
            {
                "id": item.id,
                "event_id": item.event_id,
                "case_article_id": item.case_article_id,
                "evidence_type": item.evidence_type,
                "source_type": item.source_type,
                "title": item.title,
                "origin_url": item.origin_url,
                "canonical_url": item.canonical_url,
                "publisher": item.publisher,
                "published_at": item.published_at,
                "verification_status": item.verification_status,
                "credibility_tier": item.credibility_tier,
                "requires_human_review": bool(item.requires_human_review),
                "capture_metadata": item.capture_metadata or {},
                "lineage": {
                    "case_id": case.id,
                    "event_id": item.event_id,
                    "case_article_id": item.case_article_id,
                    "origin": (item.capture_metadata or {}).get("lineage", {}).get(
                        "origin",
                        "native_ingestion",
                    ),
                },
                "artifacts": [
                    {
                        "id": artifact.id,
                        "tool": artifact.tool,
                        "artifact_type": artifact.artifact_type,
                        "source_path": artifact.source_path,
                        "relation": link.relation,
                        "imported_at": artifact.imported_at.isoformat()
                        if artifact.imported_at
                        else None,
                    }
                    for link in artifact_links_by_evidence.get(item.id, [])
                    for artifact in [osint_artifacts_by_id.get(link.osint_artifact_id)]
                    if artifact is not None
                ],
                "verification_checks": [
                    {
                        "id": check.id,
                        "check_type": check.check_type,
                        "result": check.result,
                        "method": check.method,
                        "notes": check.notes,
                        "verified_by": check.verified_by,
                        "verified_at": check.verified_at.isoformat()
                        if check.verified_at
                        else None,
                    }
                    for check in checks_by_evidence.get(item.id, [])
                ],
            }
        )

    serialized_claims = []
    grouped_claims: dict[str, dict[str, Any]] = {}
    for claim in claims:
        linked_evidence = []
        for link in links_by_claim.get(claim.id, []):
            evidence = evidence_by_id.get(link.evidence_id)
            if evidence is None:
                continue
            linked_evidence.append(
                {
                    "id": evidence.id,
                    "relation": link.relation,
                    "confidence_score": link.confidence_score,
                    "source_diversity_rank": link.source_diversity_rank,
                    "title": evidence.title,
                    "publisher": evidence.publisher,
                    "origin_url": evidence.origin_url,
                    "source_type": evidence.source_type,
                }
            )
        claim_payload = {
            "id": claim.id,
            "event_id": claim.event_id,
            "claim_text": claim.claim_text,
            "narrative_cluster_id": claim.narrative_cluster_id,
            "verification_status": claim.verification_status.value,
            "fact_allegation_type": claim.fact_allegation_type.value
            if claim.fact_allegation_type
            else None,
            "claim_signature": claim.claim_signature,
            "support_count": claim.support_count,
            "oppose_count": claim.oppose_count,
            "source_diversity_count": claim.source_diversity_count,
            "party_positions": claim.party_positions or {},
            "controversy_score": claim.controversy_score,
            "arbiter_reasoning": claim.arbiter_reasoning,
            "evidence": linked_evidence,
        }
        serialized_claims.append(claim_payload)
        signature = claim.claim_signature or _claim_signature(claim.claim_text)
        aggregate = grouped_claims.setdefault(
            signature,
            {
                "claim_signature": signature,
                "claim_text": claim.claim_text,
                "verification_status": claim.verification_status.value,
                "support_count": 0,
                "oppose_count": 0,
                "source_diversity_count": 0,
                "party_positions": {},
                "evidence": [],
                "event_ids": [],
            },
        )
        aggregate["support_count"] = max(aggregate["support_count"], claim.support_count)
        aggregate["oppose_count"] = max(aggregate["oppose_count"], claim.oppose_count)
        aggregate["source_diversity_count"] = max(
            aggregate["source_diversity_count"], claim.source_diversity_count
        )
        aggregate["party_positions"].update(claim.party_positions or {})
        aggregate["event_ids"].append(claim.event_id)
        for item in linked_evidence:
            if item["id"] not in {e["id"] for e in aggregate["evidence"]}:
                aggregate["evidence"].append(item)

    return {
        "case": {
            "id": case.id,
            "query": case.query,
            "slug": case.slug,
            "conflict": case.conflict,
            "status": case.status.value,
            "current_stage": case.current_stage.value if case.current_stage else None,
            "routing_mode": case.routing_mode,
            "report_path": case.report_path,
            "latest_manifest_path": case.latest_manifest_path,
            "source_count": case.source_count,
            "article_count": case.article_count,
            "event_count": case.event_count,
            "open_review_items": _compute_open_review_items(
                case.metadata_json or {}, reviews
            ),
            "review_notes": case.review_notes,
            "metadata": case.metadata_json or {},
            "created_at": case.created_at.isoformat() if case.created_at else None,
            "updated_at": case.updated_at.isoformat() if case.updated_at else None,
        },
        "stage_runs": [
            {
                "id": run.id,
                "stage": run.stage_name.value,
                "status": run.status.value,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat()
                if run.completed_at
                else None,
                "duration_ms": run.duration_ms,
                "workflow_name": run.workflow_name,
                "model_used": run.model_used,
                "fallback_count": run.fallback_count,
                "parse_failure_count": run.parse_failure_count,
                "metrics": run.metrics_json or {},
                "error_message": run.error_message,
            }
            for run in stage_runs
        ],
        "articles": [
            {
                "id": article.id,
                "url": article.url,
                "title": article.title,
                "source": article.source,
                "published_at": article.published_at,
                "relevance_score": article.relevance_score,
                "is_new": bool(article.is_new),
                "source_type": article.source_type,
                "source_metadata": article.source_metadata or {},
            }
            for article in articles
        ],
        "events": [
            {
                "id": event.id,
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                "title": event.title,
                "summary": event.summary,
                "verification_status": event.verification_status.value,
                "workflow_route": getattr(event, 'workflow_route', None),
                "source_url": getattr(event, 'source_url', None),
            }
            for event in events
        ],
        "claims": serialized_claims,
        "claim_groups": list(grouped_claims.values()),
        "narratives": [
            {
                "id": narrative.id,
                "cluster_id": narrative.cluster_id,
                "stance_summary": narrative.stance_summary,
                "source_count": narrative.source_count,
                "key_themes": getattr(narrative, 'key_themes', []),
                "main_entities": getattr(narrative, 'main_entities', []),
            }
            for narrative in narratives
        ],
        "evidence": serialized_evidence,
        "exceptions": _merge_exception_lists(
            [], list((case.metadata_json or {}).get("exception_queue", []))
        ),
        "party_investigations": [
            {
                "id": investigation.id,
                "event_id": investigation.event_id,
                "party_id": investigation.party_id,
                "party_name": getattr(investigation, 'party_name', None),
                "investigation_data": investigation.investigation_data,
                "party_stance": investigation.party_stance,
            }
            for investigation in party_investigations
        ],
        "parties": [
            {
                "id": party.id,
                "canonical_name": party.canonical_name,
                "aliases": party.aliases,
                "description": party.description,
                "is_bootstrap_confirmed": bool(party.is_bootstrap_confirmed),
            }
            for party in parties
        ],
        "artifacts": [
            {
                "id": artifact.id,
                "type": artifact.artifact_type,
                "path": artifact.path,
                "checksum": artifact.checksum,
                "created_at": artifact.created_at.isoformat()
                if artifact.created_at
                else None,
            }
            for artifact in artifacts
        ],
        "osint_artifacts": [
            {
                "id": artifact.id,
                "tool": artifact.tool,
                "artifact_type": artifact.artifact_type,
                "source_path": artifact.source_path,
                "imported_at": artifact.imported_at.isoformat()
                if artifact.imported_at
                else None,
                "import_metadata": artifact.import_metadata or {},
            }
            for artifact in osint_artifacts
        ],
        "workflow": {
            "taxonomy": {
                "id": active_taxonomy.id,
                "kind": active_taxonomy.taxonomy_kind,
                "version": active_taxonomy.version,
                "path": active_taxonomy.path,
                "checksum": active_taxonomy.checksum,
            }
            if active_taxonomy
            else None,
            "checkpoints": [
                {
                    "id": checkpoint.id,
                    "stage_name": checkpoint.stage_name,
                    "checkpoint_key": checkpoint.checkpoint_key,
                    "status": checkpoint.status,
                    "summary": checkpoint.summary,
                    "retry_count": checkpoint.retry_count,
                    "payload": checkpoint.payload_json or {},
                    "created_at": checkpoint.created_at.isoformat()
                    if checkpoint.created_at
                    else None,
                }
                for checkpoint in workflow_checkpoints
            ],
            "agent_outputs": [
                {
                    "id": output.id,
                    "stage_name": output.stage_name,
                    "agent_name": output.agent_name,
                    "output_type": output.output_type,
                    "summary": output.summary,
                    "payload": output.output_json or {},
                    "taxonomy_version_id": output.taxonomy_version_id,
                    "created_at": output.created_at.isoformat()
                    if output.created_at
                    else None,
                }
                for output in agent_outputs
            ],
        },
    }
