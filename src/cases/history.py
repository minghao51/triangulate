"""Immutable case snapshots, semantic deltas and historical run readers (R03).

A snapshot is an observation of **committed** state at a successful run's
finalization, not a claim that the whole pipeline committed atomically. The
canonical payload references immutable captures/citations by ID and keeps enough
claim text to render claims that were removed from the live rows later.

``semantic_view`` deliberately excludes volatile fields (observation/last-seen
timestamps, execution IDs, ordering, counts, run durations) so an equivalent
rerun produces no semantic change and an empty delta never looks like a surge.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.storage import (
    CaseArticle,
    CaseSnapshot,
    Claim,
    ClaimCitation,
    ClaimEvidenceLink,
    Event,
    EvidenceCapture,
    EvidenceItem,
    InvestigationRun,
    InvestigationRunStatus,
    Narrative,
    Party,
    PartyInvestigation,
    Review,
    TopicCase,
)

SNAPSHOT_SCHEMA_VERSION = "case-snapshot-v1"
SNAPSHOT_IDENTITY_VERSION = "claim-signature-sha256-v1"
SNAPSHOT_POLICY_VERSION = "case-history-policy-v1"

COVERAGE_COMPLETE = "complete_requested_scope"

CHANGE_ARTICLE_ADDED = "article_added"
CHANGE_CAPTURE_CHANGED = "capture_changed"
CHANGE_CLAIM_ADDED = "claim_added"
CHANGE_CLAIM_REMOVED = "claim_no_longer_extracted"
CHANGE_CLASSIFICATION_CHANGED = "classification_changed"
CHANGE_RELATIONSHIP_CHANGED = "relationship_changed"
CHANGE_REVIEW_STATE_CHANGED = "review_state_changed"
CHANGE_EXCEPTION_CHANGED = "exception_changed"

_AVAILABILITY_INITIAL = "initial"
_AVAILABILITY_READY = "ready"
_AVAILABILITY_PENDING = "pending"
_AVAILABILITY_UNAVAILABLE = "unavailable"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _sorted(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda item: str(item.get("id") or ""))


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _first_known_origin(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None


def _origin_index(payload: dict[str, Any]) -> dict[str, dict[str, str | None]]:
    """Map entity IDs to the grouped run recorded as their origin, when known.

    ``Event.investigation_run_id`` is the only stored origin reference. An entity
    whose event carries none -- and every entity type without one (articles,
    exceptions) -- resolves to ``None``: an observation never attributes a change
    to the observing run merely because it was the one that saw it.
    """
    entity_lists = {
        name: payload.get(name)
        for name in ("events", "claims", "evidence", "links", "reviews")
    }

    def rows(name: str) -> list[dict[str, Any]]:
        value = entity_lists.get(name)
        if not isinstance(value, list):
            return []
        return [row for row in value if isinstance(row, dict)]

    events = {
        str(row.get("id")): _as_str(row.get("investigationRunId"))
        for row in rows("events")
        if row.get("id") is not None
    }
    claims = {
        str(row.get("id")): events.get(str(row.get("eventId")))
        for row in rows("claims")
        if row.get("id") is not None
    }
    evidence = {
        str(row.get("id")): events.get(str(row.get("eventId")))
        for row in rows("evidence")
        if row.get("id") is not None
    }
    # A link row records no run of its own. Inheriting the claim's or evidence's
    # event run would attribute a later-added or edited link to an earlier run, so
    # link changes keep an unknown origin.
    links: dict[str, str | None] = {
        str(row.get("id")): None
        for row in rows("links")
        if row.get("id") is not None
    }
    reviews = {
        str(row.get("id")): events.get(str(row.get("eventId")))
        for row in rows("reviews")
        if row.get("id") is not None
    }
    return {
        "claims": claims,
        "evidence": evidence,
        "links": links,
        "reviews": reviews,
    }


def compose_case_snapshot(session: Session, *, case_id: str) -> dict[str, Any]:
    """Compose the canonical snapshot payload for one case.

    The caller should run this inside a single read transaction while holding the
    case writer ownership. Returns ``payload``, its ``semantic`` projection and
    the ``semanticHash``.
    """
    case = session.get(TopicCase, case_id)
    if case is None:
        raise LookupError(f"Case {case_id!r} does not exist")

    events = list(
        session.execute(select(Event).where(Event.case_id == case_id)).scalars()
    )
    event_ids = [event.id for event in events]
    articles = list(
        session.execute(
            select(CaseArticle).where(CaseArticle.case_id == case_id)
        ).scalars()
    )
    claims = (
        list(
            session.execute(
                select(Claim)
                .join(Event, Claim.event_id == Event.id)
                .where(Event.case_id == case_id)
            ).scalars()
        )
        if event_ids
        else []
    )
    claim_ids = [claim.id for claim in claims]
    evidence = list(
        session.execute(
            select(EvidenceItem).where(EvidenceItem.case_id == case_id)
        ).scalars()
    )
    evidence_ids = [item.id for item in evidence]
    captures = (
        list(
            session.execute(
                select(EvidenceCapture).where(
                    EvidenceCapture.evidence_id.in_(evidence_ids)
                )
            ).scalars()
        )
        if evidence_ids
        else []
    )
    links = (
        list(
            session.execute(
                select(ClaimEvidenceLink).where(
                    ClaimEvidenceLink.claim_id.in_(claim_ids)
                )
            ).scalars()
        )
        if claim_ids
        else []
    )
    citations = list(
        session.execute(
            select(ClaimCitation).where(ClaimCitation.case_id == case_id)
        ).scalars()
    )
    reviews = (
        list(
            session.execute(
                select(Review)
                .join(Event, Review.event_id == Event.id)
                .where(Event.case_id == case_id)
            ).scalars()
        )
        if event_ids
        else []
    )
    investigations = (
        list(
            session.execute(
                select(PartyInvestigation).where(
                    PartyInvestigation.event_id.in_(event_ids)
                )
            ).scalars()
        )
        if event_ids
        else []
    )
    narratives: list[Narrative] = []
    if events:
        for event in events:
            narratives.extend(
                session.execute(
                    select(Narrative).where(
                        Narrative.cluster_id.like(f"{event.id}:%")
                    )
                ).scalars()
            )

    party_ids = {claim.party_id for claim in claims if claim.party_id}
    party_ids.update(
        investigation.party_id
        for investigation in investigations
        if investigation.party_id
    )
    parties = (
        list(
            session.execute(
                select(Party).where(Party.id.in_(sorted(party_ids)))
            ).scalars()
        )
        if party_ids
        else []
    )

    metadata = case.metadata_json or {}
    exceptions = [
        {
            "id": item.get("id"),
            "type": item.get("type"),
            "stage": item.get("stage"),
            "status": item.get("status"),
            "severity": item.get("severity"),
            "message": item.get("message"),
            "resolutionNotes": item.get("resolution_notes"),
            "updatedAt": item.get("updated_at"),
        }
        for item in metadata.get("exception_queue", [])
        if isinstance(item, dict)
    ]

    payload: dict[str, Any] = {
        "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
        "identityVersion": SNAPSHOT_IDENTITY_VERSION,
        "policyVersion": SNAPSHOT_POLICY_VERSION,
        "caseId": case.id,
        "query": case.query,
        "status": _enum_value(case.status),
        "currentStage": _enum_value(case.current_stage),
        "reviewNotes": case.review_notes,
        "observedAt": _iso(_utcnow()),
        "counts": {
            "articles": len(articles),
            "events": len(events),
            "claims": len(claims),
            "evidence": len(evidence),
            "captures": len(captures),
            "links": len(links),
            "citations": len(citations),
            "reviews": len(reviews),
            "exceptions": len(exceptions),
        },
        "articles": _sorted(
            [
                {
                    "id": row.id,
                    "url": row.url,
                    "title": row.title,
                    "source": row.source,
                    "publishedAt": row.published_at,
                    "fingerprint": row.fingerprint,
                    "status": row.status,
                    "sourceType": row.source_type,
                    "relevanceScore": row.relevance_score,
                    "firstSeenAt": _iso(row.first_seen_at),
                    "lastSeenAt": _iso(row.last_seen_at),
                }
                for row in articles
            ]
        ),
        "events": _sorted(
            [
                {
                    "id": row.id,
                    "timestamp": _iso(row.timestamp),
                    "title": row.title,
                    "summary": row.summary,
                    "verificationStatus": _enum_value(row.verification_status),
                    "locationCountryCode": row.location_country_code,
                    "locationLat": row.location_lat,
                    "locationLon": row.location_lon,
                    "workflowRoute": row.workflow_route,
                    "sourceUrl": row.source_url,
                    "investigationRunId": row.investigation_run_id,
                }
                for row in events
            ]
        ),
        "claims": _sorted(
            [
                {
                    "id": row.id,
                    "eventId": row.event_id,
                    "sourceId": row.source_id,
                    "text": row.claim_text,
                    "claimSignature": row.claim_signature,
                    "verificationStatus": _enum_value(row.verification_status),
                    "factAllegationType": _enum_value(row.fact_allegation_type),
                    "partyPositions": row.party_positions,
                    "controversyScore": row.controversy_score,
                    "supportCount": row.support_count,
                    "opposeCount": row.oppose_count,
                    "sourceDiversityCount": row.source_diversity_count,
                    "narrativeClusterId": row.narrative_cluster_id,
                    "arbiterReasoning": row.arbiter_reasoning,
                }
                for row in claims
            ]
        ),
        "links": _sorted(
            [
                {
                    "id": row.id,
                    "claimId": row.claim_id,
                    "evidenceId": row.evidence_id,
                    "captureId": row.capture_id,
                    "citationId": row.citation_id,
                    "relation": row.relation,
                    "sourceDiversityRank": row.source_diversity_rank,
                    "confidenceScore": row.confidence_score,
                    "notes": row.notes,
                    "quote": row.quote,
                    "startChar": row.start_char,
                    "endChar": row.end_char,
                    "alignmentStatus": row.alignment_status,
                    "assessmentOrigin": row.assessment_origin,
                    "assessmentVersion": row.assessment_version,
                    "assessmentMetadata": row.assessment_metadata or {},
                }
                for row in links
            ]
        ),
        "citations": _sorted(
            [
                {
                    "id": row.id,
                    "captureId": row.capture_id,
                    "originalClaimId": row.original_claim_id,
                    "claimSignature": row.claim_signature,
                    "text": row.text,
                    "relationship": row.relationship,
                    "quote": row.quote,
                    "startChar": row.start_char,
                    "endChar": row.end_char,
                    "alignmentStatus": row.alignment_status,
                    "alignmentVersion": row.alignment_version,
                    "assessmentOrigin": row.assessment_origin,
                    "assessmentVersion": row.assessment_version,
                    "recordedAt": _iso(row.recorded_at),
                }
                for row in citations
            ]
        ),
        "evidence": _sorted(
            [
                {
                    "id": row.id,
                    "eventId": row.event_id,
                    "caseArticleId": row.case_article_id,
                    "evidenceType": row.evidence_type,
                    "sourceType": row.source_type,
                    "title": row.title,
                    "originUrl": row.origin_url,
                    "canonicalUrl": row.canonical_url,
                    "archivedUrl": row.archived_url,
                    "publisher": row.publisher,
                    "publishedAt": _iso(row.published_at),
                    "currentCaptureId": row.current_capture_id,
                    "verificationStatus": _enum_value(row.verification_status),
                    "credibilityTier": row.credibility_tier,
                    "requiresHumanReview": bool(row.requires_human_review),
                    "captureMetadata": row.capture_metadata or {},
                }
                for row in evidence
            ]
        ),
        "captures": _sorted(
            [
                {
                    "id": row.id,
                    "evidenceId": row.evidence_id,
                    "textSha256": row.text_sha256,
                    "normalizedTextSha256": row.normalized_text_sha256,
                    "normalizationVersion": row.normalization_version,
                    "captureKind": _enum_value(row.capture_kind),
                    "observedAt": _iso(row.observed_at),
                    "recordedAt": _iso(row.recorded_at),
                    "metadata": row.metadata_json,
                }
                for row in captures
            ]
        ),
        "reviews": _sorted(
            [
                {
                    "id": row.id,
                    "eventId": row.event_id,
                    "status": _enum_value(row.status),
                    "reviewedAt": _iso(row.reviewed_at),
                    "notes": row.notes,
                    "analysisHash": row.analysis_hash,
                }
                for row in reviews
            ]
        ),
        "exceptions": _sorted(exceptions),
        "parties": _sorted(
            [
                {
                    "id": row.id,
                    "canonicalName": row.canonical_name,
                    "aliases": row.aliases,
                    "description": row.description,
                    "isBootstrapConfirmed": bool(row.is_bootstrap_confirmed),
                }
                for row in parties
            ]
        ),
        "partyInvestigations": _sorted(
            [
                {
                    "id": row.id,
                    "eventId": row.event_id,
                    "partyId": row.party_id,
                    "partyName": row.party_name,
                    "investigationData": row.investigation_data,
                    "partyStance": row.party_stance,
                }
                for row in investigations
            ]
        ),
        "narratives": _sorted(
            [
                {
                    "id": row.id,
                    "clusterId": row.cluster_id,
                    "stanceSummary": row.stance_summary,
                    "sourceCount": row.source_count,
                    "keyThemes": row.key_themes,
                    "mainEntities": row.main_entities,
                }
                for row in narratives
            ]
        ),
    }
    semantic = semantic_view(payload)
    return {
        "payload": payload,
        "semantic": semantic,
        "semanticHash": _semantic_hash(semantic),
    }


def semantic_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the stable projection used for hashing and diffing.

    Volatile observation fields, counts, ordering, last-seen/created timestamps
    and execution metadata are excluded. Entity lists are sorted by ID.
    """

    def entities(name: str, fields: tuple[str, ...]) -> list[dict[str, Any]]:
        rows = payload.get(name) or []
        return sorted(
            [
                {field: row.get(field) for field in fields}
                for row in rows
            ],
            key=lambda item: str(item.get("id") or ""),
        )

    return {
        "case": {
            "query": payload.get("query"),
            "reviewNotes": payload.get("reviewNotes"),
        },
        "articles": entities(
            "articles",
            ("id", "url", "title", "source", "publishedAt", "fingerprint", "status", "sourceType"),
        ),
        "events": entities(
            "events",
            (
                "id",
                "timestamp",
                "title",
                "summary",
                "verificationStatus",
                "locationCountryCode",
                "locationLat",
                "locationLon",
                "workflowRoute",
                "sourceUrl",
            ),
        ),
        "claims": entities(
            "claims",
            (
                "id",
                "eventId",
                "sourceId",
                "text",
                "claimSignature",
                "verificationStatus",
                "factAllegationType",
                "partyPositions",
                "controversyScore",
            ),
        ),
        "links": entities(
            "links",
            (
                "id",
                "claimId",
                "evidenceId",
                "captureId",
                "citationId",
                "relation",
                "sourceDiversityRank",
                "confidenceScore",
                "quote",
                "startChar",
                "endChar",
                "alignmentStatus",
                "assessmentOrigin",
                "assessmentVersion",
            ),
        ),
        "citations": entities(
            "citations",
            (
                "id",
                "captureId",
                "originalClaimId",
                "claimSignature",
                "text",
                "relationship",
                "quote",
                "startChar",
                "endChar",
                "alignmentStatus",
                "assessmentOrigin",
                "assessmentVersion",
            ),
        ),
        "evidence": entities(
            "evidence",
            (
                "id",
                "eventId",
                "evidenceType",
                "sourceType",
                "title",
                "originUrl",
                "canonicalUrl",
                "publisher",
                "publishedAt",
                "currentCaptureId",
                "verificationStatus",
                "credibilityTier",
            ),
        ),
        "captures": entities(
            "captures",
            ("id", "evidenceId", "textSha256", "captureKind"),
        ),
        "reviews": entities(
            "reviews",
            ("id", "eventId", "status", "notes", "analysisHash"),
        ),
        "exceptions": entities(
            "exceptions",
            ("id", "type", "stage", "status", "severity", "message", "resolutionNotes"),
        ),
        "parties": entities(
            "parties",
            ("id", "canonicalName", "aliases", "description", "isBootstrapConfirmed"),
        ),
        "partyInvestigations": entities(
            "partyInvestigations",
            ("id", "eventId", "partyId", "partyName", "investigationData", "partyStance"),
        ),
        "narratives": entities(
            "narratives",
            ("id", "clusterId", "stanceSummary", "keyThemes", "mainEntities"),
        ),
    }


def _semantic_hash(semantic: dict[str, Any]) -> str:
    canonical = json.dumps(
        semantic, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def semantic_hash_for_payload(payload: dict[str, Any]) -> str:
    return _semantic_hash(semantic_view(payload))


def build_snapshot_delta(
    *,
    snapshot_id: str,
    baseline_payload: dict[str, Any] | None,
    baseline_snapshot_id: str | None,
    current_payload: dict[str, Any],
    current_semantic: dict[str, Any],
    coverage: str,
    run_id: str,
    authoritative_event_ids: set[str] | None,
    observed_at: str,
) -> dict[str, Any]:
    """Build the deterministic stored delta from the baseline observation.

    Only an event reprocessed with a valid/empty extraction may remove claims;
    otherwise a disappeared claim is not reported as removed. Article removals
    are never inferred (a source disappearing from a window is not a removal).
    """
    if baseline_payload is None:
        return {
            "availability": _AVAILABILITY_INITIAL,
            "baselineSnapshotId": None,
            "targetSnapshotId": snapshot_id,
            "coverage": coverage,
            "coverageNote": _coverage_note(coverage),
            "observedAt": observed_at,
            "changes": [],
        }

    baseline_semantic = semantic_view(baseline_payload)
    changes: list[dict[str, Any]] = []
    authoritative = authoritative_event_ids or set()
    origin_before = _origin_index(baseline_payload)
    origin_after = _origin_index(current_payload)

    def index(semantic: dict[str, Any], name: str) -> dict[str, dict[str, Any]]:
        return {str(row.get("id")): row for row in semantic.get(name, [])}

    base_articles = index(baseline_semantic, "articles")
    now_articles = index(current_semantic, "articles")
    for entity_id in sorted(set(now_articles) - set(base_articles)):
        changes.append(
            {
                "type": CHANGE_ARTICLE_ADDED,
                "entityType": "article",
                "entityId": entity_id,
                "before": None,
                "after": now_articles[entity_id],
                "originRunId": None,
                "observedByRunId": run_id,
                "observedAt": observed_at,
            }
        )

    base_evidence = index(baseline_semantic, "evidence")
    now_evidence = index(current_semantic, "evidence")
    for entity_id in sorted(set(base_evidence) & set(now_evidence)):
        before = base_evidence[entity_id]
        after = now_evidence[entity_id]
        if before.get("currentCaptureId") != after.get("currentCaptureId"):
            changes.append(
                {
                    "type": CHANGE_CAPTURE_CHANGED,
                    "entityType": "evidence",
                    "entityId": entity_id,
                    "before": {
                        "currentCaptureId": before.get("currentCaptureId")
                    },
                    "after": {"currentCaptureId": after.get("currentCaptureId")},
                    "originRunId": origin_after["evidence"].get(entity_id),
                    "observedByRunId": run_id,
                    "observedAt": observed_at,
                }
            )

    base_claims = index(baseline_semantic, "claims")
    now_claims = index(current_semantic, "claims")
    for entity_id in sorted(set(now_claims) - set(base_claims)):
        after = now_claims[entity_id]
        changes.append(
            {
                "type": CHANGE_CLAIM_ADDED,
                "entityType": "claim",
                "entityId": entity_id,
                "before": None,
                "after": {"text": after.get("text"), "claimSignature": after.get("claimSignature")},
                "originRunId": origin_after["claims"].get(entity_id),
                "observedByRunId": run_id,
                "observedAt": observed_at,
            }
        )
    for entity_id in sorted(set(base_claims) - set(now_claims)):
        before = base_claims[entity_id]
        if str(before.get("eventId")) not in authoritative:
            continue
        changes.append(
            {
                "type": CHANGE_CLAIM_REMOVED,
                "entityType": "claim",
                "entityId": entity_id,
                "before": {"text": before.get("text"), "claimSignature": before.get("claimSignature")},
                "after": None,
                "originRunId": origin_before["claims"].get(entity_id),
                "observedByRunId": run_id,
                "observedAt": observed_at,
            }
        )
    classification_fields = (
        "verificationStatus",
        "factAllegationType",
        "partyPositions",
        "controversyScore",
        "sourceId",
    )
    for entity_id in sorted(set(base_claims) & set(now_claims)):
        before = base_claims[entity_id]
        after = now_claims[entity_id]
        changed = {
            field: {"before": before.get(field), "after": after.get(field)}
            for field in classification_fields
            if before.get(field) != after.get(field)
        }
        if changed:
            changes.append(
                {
                    "type": CHANGE_CLASSIFICATION_CHANGED,
                    "entityType": "claim",
                    "entityId": entity_id,
                    "before": {field: value["before"] for field, value in changed.items()},
                    "after": {field: value["after"] for field, value in changed.items()},
                    "originRunId": origin_after["claims"].get(entity_id),
                    "observedByRunId": run_id,
                    "observedAt": observed_at,
                }
            )

    base_links = index(baseline_semantic, "links")
    now_links = index(current_semantic, "links")
    link_fields = (
        "relation",
        "captureId",
        "citationId",
        "quote",
        "startChar",
        "endChar",
        "alignmentStatus",
        "assessmentOrigin",
        "assessmentVersion",
    )
    for entity_id in sorted(set(now_links) | set(base_links)):
        before = base_links.get(entity_id)
        after = now_links.get(entity_id)
        if before is None or after is None:
            changes.append(
                {
                    "type": CHANGE_RELATIONSHIP_CHANGED,
                    "entityType": "link",
                    "entityId": entity_id,
                    "before": before,
                    "after": after,
                    "originRunId": _first_known_origin(origin_after["links"].get(entity_id), origin_before["links"].get(entity_id)),
                    "observedByRunId": run_id,
                    "observedAt": observed_at,
                }
            )
            continue
        changed = {
            field: {"before": before.get(field), "after": after.get(field)}
            for field in link_fields
            if before.get(field) != after.get(field)
        }
        if changed:
            changes.append(
                {
                    "type": CHANGE_RELATIONSHIP_CHANGED,
                    "entityType": "link",
                    "entityId": entity_id,
                    "before": {field: value["before"] for field, value in changed.items()},
                    "after": {field: value["after"] for field, value in changed.items()},
                    "originRunId": origin_after["links"].get(entity_id),
                    "observedByRunId": run_id,
                    "observedAt": observed_at,
                }
            )

    base_reviews = index(baseline_semantic, "reviews")
    now_reviews = index(current_semantic, "reviews")
    for entity_id in sorted(set(base_reviews) | set(now_reviews)):
        before = base_reviews.get(entity_id)
        after = now_reviews.get(entity_id)
        if before is None or after is None or before != after:
            changes.append(
                {
                    "type": CHANGE_REVIEW_STATE_CHANGED,
                    "entityType": "review",
                    "entityId": entity_id,
                    "before": before,
                    "after": after,
                    "originRunId": _first_known_origin(origin_after["reviews"].get(entity_id), origin_before["reviews"].get(entity_id)),
                    "observedByRunId": run_id,
                    "observedAt": observed_at,
                }
            )

    base_exceptions = index(baseline_semantic, "exceptions")
    now_exceptions = index(current_semantic, "exceptions")
    for entity_id in sorted(set(base_exceptions) | set(now_exceptions)):
        before = base_exceptions.get(entity_id)
        after = now_exceptions.get(entity_id)
        if before is None or after is None or before != after:
            changes.append(
                {
                    "type": CHANGE_EXCEPTION_CHANGED,
                    "entityType": "exception",
                    "entityId": entity_id,
                    "before": before,
                    "after": after,
                    "originRunId": None,
                    "observedByRunId": run_id,
                    "observedAt": observed_at,
                }
            )

    changes.sort(key=lambda item: (item["type"], item["entityType"], item["entityId"]))
    return {
        "availability": _AVAILABILITY_READY,
        "baselineSnapshotId": baseline_snapshot_id,
        "targetSnapshotId": snapshot_id,
        "coverage": coverage,
        "coverageNote": _coverage_note(coverage),
        "observedAt": observed_at,
        "changes": changes,
    }


def _coverage_note(coverage: str) -> str | None:
    if coverage == COVERAGE_COMPLETE:
        return None
    return (
        f"Coverage was {coverage}; changes describe observed data only and do not "
        "mean every source was unchanged."
    )


def latest_snapshot_before(
    session: Session, *, case_id: str, run_sequence: int
) -> CaseSnapshot | None:
    """Latest eligible snapshot whose run sequence is earlier than this run."""
    return (
        session.execute(
            select(CaseSnapshot)
            .join(
                InvestigationRun,
                CaseSnapshot.investigation_run_id == InvestigationRun.id,
            )
            .where(
                CaseSnapshot.case_id == case_id,
                InvestigationRun.sequence < run_sequence,
            )
            .order_by(InvestigationRun.sequence.desc())
        )
        .scalars()
        .first()
    )


def snapshot_for_run(session: Session, *, run_id: str) -> CaseSnapshot | None:
    return (
        session.execute(
            select(CaseSnapshot).where(CaseSnapshot.investigation_run_id == run_id)
        )
        .scalars()
        .first()
    )


def get_case_snapshot(
    session: Session, *, case_id: str, snapshot_id: str
) -> CaseSnapshot | None:
    """Return one snapshot owned by ``case_id`` (``None`` for unknown/cross-case).

    Read-only: no snapshot is composed or published on a GET.
    """
    snapshot = session.get(CaseSnapshot, snapshot_id)
    if snapshot is None or snapshot.case_id != case_id:
        return None
    return snapshot


def snapshot_payload(snapshot: CaseSnapshot) -> dict[str, Any]:
    """Return the frozen payload mapping (an absent payload is an empty one)."""
    payload = snapshot.payload_json
    return payload if isinstance(payload, dict) else {}


def snapshot_entities(
    payload: dict[str, Any], name: str
) -> dict[str, dict[str, Any]]:
    """Index one payload entity list by stored ID, ignoring malformed rows."""
    index: dict[str, dict[str, Any]] = {}
    rows = payload.get(name)
    if not isinstance(rows, list):
        return index
    for row in rows:
        if not isinstance(row, dict):
            continue
        entity_id = row.get("id")
        if isinstance(entity_id, str) and entity_id not in index:
            index[entity_id] = row
    return index


def snapshot_entity_list(payload: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """Return one payload entity list in stored (already sorted) order."""
    rows = payload.get(name)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _run_summary(run: InvestigationRun, snapshot: CaseSnapshot | None) -> dict[str, Any]:
    error_message = None
    if isinstance(run.error_json, dict):
        error_message = run.error_json.get("message") or run.error_json.get("reason")
    return {
        "id": run.id,
        "caseId": run.case_id,
        "sequence": run.sequence,
        "trigger": _enum_value(run.trigger),
        "requestedStartStage": _enum_value(run.requested_start_stage),
        "status": _enum_value(run.status),
        "coverage": _enum_value(run.coverage),
        "startedAt": _iso(run.started_at),
        "completedAt": _iso(run.completed_at),
        "predecessorRunId": run.predecessor_run_id,
        "baselineSnapshotId": run.baseline_snapshot_id,
        "resultSnapshotId": run.result_snapshot_id,
        "snapshotId": snapshot.id if snapshot is not None else None,
        "errorMessage": error_message,
    }


def read_investigation_runs(
    session: Session, *, case_id: str, limit: int, offset: int
) -> dict[str, Any] | None:
    """Paginated grouped runs, newest sequence first; distinct from stage history."""
    if session.get(TopicCase, case_id) is None:
        return None
    total = session.execute(
        select(func.count(InvestigationRun.id)).where(
            InvestigationRun.case_id == case_id
        )
    ).scalar_one()
    runs = list(
        session.execute(
            select(InvestigationRun)
            .where(InvestigationRun.case_id == case_id)
            .order_by(
                InvestigationRun.sequence.desc(), InvestigationRun.id.desc()
            )
            .offset(offset)
            .limit(limit)
        ).scalars()
    )
    run_ids = [run.id for run in runs]
    snapshots = (
        list(
            session.execute(
                select(CaseSnapshot).where(
                    CaseSnapshot.investigation_run_id.in_(run_ids)
                )
            ).scalars()
        )
        if run_ids
        else []
    )
    by_run = {snapshot.investigation_run_id: snapshot for snapshot in snapshots}
    return {
        "items": [_run_summary(run, by_run.get(run.id)) for run in runs],
        "total": total,
        "limit": limit,
        "offset": offset,
        "hasMore": offset + len(runs) < total,
    }


def read_investigation_run(
    session: Session, *, case_id: str, run_id: str
) -> dict[str, Any] | None:
    run = session.get(InvestigationRun, run_id)
    if run is None or run.case_id != case_id:
        return None
    snapshot = snapshot_for_run(session, run_id=run_id)
    summary = _run_summary(run, snapshot)
    summary["parameterSnapshot"] = run.parameter_snapshot or {}
    summary["coverageDetails"] = run.coverage_details or {}
    summary["error"] = run.error_json
    return summary


def read_run_changes(
    session: Session, *, case_id: str, run_id: str, limit: int, offset: int
) -> dict[str, Any] | None:
    run = session.get(InvestigationRun, run_id)
    if run is None or run.case_id != case_id:
        return None
    snapshot = snapshot_for_run(session, run_id=run_id)
    if run.status == InvestigationRunStatus.RUNNING:
        return {
            "availability": _AVAILABILITY_PENDING,
            "baselineSnapshotId": run.baseline_snapshot_id,
            "targetSnapshotId": run.result_snapshot_id,
            "coverage": _enum_value(run.coverage),
            "coverageNote": "The run is still in progress; changes are not final.",
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "hasMore": False,
        }
    if snapshot is None:
        return {
            "availability": _AVAILABILITY_UNAVAILABLE,
            "baselineSnapshotId": run.baseline_snapshot_id,
            "targetSnapshotId": run.result_snapshot_id,
            "coverage": _enum_value(run.coverage),
            "coverageNote": (
                "No snapshot was published for this run. Historical change data is "
                "unavailable; it is not an empty delta."
            ),
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "hasMore": False,
        }
    delta = snapshot.delta_json or {}
    changes = list(delta.get("changes") or [])
    return {
        "availability": delta.get("availability", _AVAILABILITY_READY),
        "baselineSnapshotId": delta.get("baselineSnapshotId"),
        "targetSnapshotId": snapshot.id,
        "coverage": delta.get("coverage", _enum_value(run.coverage)),
        "coverageNote": delta.get("coverageNote"),
        "items": changes[offset : offset + limit],
        "total": len(changes),
        "limit": limit,
        "offset": offset,
        "hasMore": offset + limit < len(changes),
    }


def read_snapshot_summary(
    session: Session, *, case_id: str, snapshot_id: str
) -> dict[str, Any] | None:
    snapshot = session.get(CaseSnapshot, snapshot_id)
    if snapshot is None or snapshot.case_id != case_id:
        return None
    payload = snapshot.payload_json or {}
    return {
        "id": snapshot.id,
        "caseId": snapshot.case_id,
        "investigationRunId": snapshot.investigation_run_id,
        "baselineSnapshotId": snapshot.baseline_snapshot_id,
        "schemaVersion": snapshot.schema_version,
        "identityVersion": snapshot.identity_version,
        "policyVersion": snapshot.policy_version,
        "semanticHash": snapshot.semantic_hash,
        "createdAt": _iso(snapshot.created_at),
        "counts": payload.get("counts") or {},
        "observedAt": payload.get("observedAt"),
    }


__all__ = [
    "SNAPSHOT_SCHEMA_VERSION",
    "SNAPSHOT_IDENTITY_VERSION",
    "SNAPSHOT_POLICY_VERSION",
    "compose_case_snapshot",
    "semantic_view",
    "semantic_hash_for_payload",
    "build_snapshot_delta",
    "get_case_snapshot",
    "latest_snapshot_before",
    "snapshot_for_run",
    "snapshot_payload",
    "snapshot_entity_list",
    "snapshot_entities",
    "read_investigation_runs",
    "read_investigation_run",
    "read_run_changes",
    "read_snapshot_summary",
]
