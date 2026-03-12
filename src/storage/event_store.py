"""Persistence helpers for workflow outputs."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from src.storage import (
    Claim,
    ClaimEvidenceLink,
    EvidenceItem,
    EvidenceVerificationCheck,
    Event,
    Narrative,
    Party,
    PartyInvestigation,
    Review,
    ReviewStatus,
    VerificationStatus,
    FactAllegationType,
    get_database,
)

logger = logging.getLogger(__name__)


def _claim_identifier(event_id: str, claim_data: dict[str, Any]) -> str:
    signature = claim_data.get("claim_signature") or claim_data.get("claim", "")
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"claim:{event_id}:{signature}"))


def _evidence_identifier(
    case_id: str | None, event_id: str, evidence_data: dict[str, Any], event_data: dict[str, Any]
) -> str:
    candidate = (
        evidence_data.get("canonical_url")
        or evidence_data.get("origin_url")
        or event_data.get("source_url")
        or evidence_data.get("title")
        or event_data.get("title")
        or event_id
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"evidence:{case_id}:{candidate}"))


def _to_verification_status(value: str | VerificationStatus) -> VerificationStatus:
    if isinstance(value, VerificationStatus):
        return value
    return VerificationStatus[str(value).upper()]


def _to_fact_type(value: str | FactAllegationType | None) -> FactAllegationType | None:
    if value is None:
        return None
    if isinstance(value, FactAllegationType):
        return value
    return FactAllegationType[str(value).upper()]


def _normalize_party_name(value: str) -> str:
    return value.strip().casefold()


def store_event_in_db(
    event_data: dict[str, Any],
    *,
    case_id: str | None = None,
    case_run_id: str | None = None,
    create_review: bool = True,
    confirmed_parties: list[str] | None = None,
) -> bool:
    """Store processed event in the database."""
    db = get_database()
    session = db.get_session_sync()

    try:
        event_id = event_data["id"]
        confirmed_party_names = {
            _normalize_party_name(name)
            for name in (confirmed_parties or [])
            if isinstance(name, str) and name.strip()
        }
        existing_event = session.query(Event).filter(Event.id == event_id).first()
        if existing_event is not None:
            existing_claim_ids = [
                claim_id
                for (claim_id,) in session.query(Claim.id)
                .filter(Claim.event_id == event_id)
                .all()
            ]
            if existing_claim_ids:
                session.query(ClaimEvidenceLink).filter(
                    ClaimEvidenceLink.claim_id.in_(existing_claim_ids)
                ).delete(synchronize_session=False)
            session.query(Claim).filter(Claim.event_id == event_id).delete()
            session.query(PartyInvestigation).filter(
                PartyInvestigation.event_id == event_id
            ).delete()

            narrative_prefix = f"{event_id}:"
            existing_narratives = (
                session.query(Narrative)
                .filter(Narrative.cluster_id.like(f"{narrative_prefix}%"))
                .all()
            )
            for narrative in existing_narratives:
                session.delete(narrative)

            event = existing_event
            event.timestamp = event_data["timestamp"]
            event.title = event_data["title"]
            event.summary = event_data["summary"]
            event.verification_status = _to_verification_status(
                event_data["verification_status"]
            )
            event.case_id = case_id
            event.case_run_id = case_run_id
        else:
            event = Event(
                id=event_id,
                timestamp=event_data["timestamp"],
                title=event_data["title"],
                summary=event_data["summary"],
                verification_status=_to_verification_status(
                    event_data["verification_status"]
                ),
                case_id=case_id,
                case_run_id=case_run_id,
            )
            session.add(event)

        party_name_to_id: dict[str, str] = {}
        for party_data in event_data.get("parties", []):
            party_name = party_data.get("canonical_name")
            if not party_name:
                continue

            party = session.query(Party).filter(
                Party.canonical_name == party_name
            ).first()
            if party is None:
                party = Party(
                    id=str(uuid.uuid4()),
                    canonical_name=party_name,
                    aliases=party_data.get("aliases", [party_name]),
                    description=party_data.get("description"),
                    is_bootstrap_confirmed=0,
                    event_id=event_id,
                )
                session.add(party)
            else:
                party.aliases = party_data.get("aliases", party.aliases)
                party.description = party_data.get("description", party.description)
                party.event_id = event_id

            candidate_names = {
                _normalize_party_name(party_name),
                *{
                    _normalize_party_name(alias)
                    for alias in (party_data.get("aliases") or [])
                    if isinstance(alias, str) and alias.strip()
                },
            }
            if candidate_names & confirmed_party_names:
                party.is_bootstrap_confirmed = 1

            party_name_to_id[party_name] = party.id

        for claim_data in event_data.get("claims", []):
            claim_id = claim_data.get("id") or _claim_identifier(event_id, claim_data)
            claim = Claim(
                id=claim_id,
                event_id=event_id,
                claim_text=claim_data.get("claim", claim_data.get("claim_text", "")),
                verification_status=_to_verification_status(
                    claim_data.get("verification_status", "ALLEGED")
                ),
                narrative_cluster_id=claim_data.get("cluster_id"),
                party_id=party_name_to_id.get(claim_data.get("party_name")),
                fact_allegation_type=_to_fact_type(
                    claim_data.get("fact_allegation_type")
                    or claim_data.get("fact_allegation_classification")
                ),
                arbiter_reasoning=claim_data.get("arbiter_reasoning")
                or claim_data.get("reasoning"),
                party_positions=claim_data.get("party_positions"),
                controversy_score=claim_data.get("controversy_score"),
                claim_signature=claim_data.get("claim_signature"),
                support_count=claim_data.get("support_count", 0),
                oppose_count=claim_data.get("oppose_count", 0),
                source_diversity_count=claim_data.get("source_diversity_count", 0),
            )
            session.add(claim)

            evidence_payload = claim_data.get("evidence", [])
            for evidence_data in evidence_payload:
                evidence_id = evidence_data.get("id") or _evidence_identifier(
                    case_id, event_id, evidence_data, event_data
                )
                evidence = (
                    session.query(EvidenceItem)
                    .filter(EvidenceItem.id == evidence_id)
                    .first()
                )
                if evidence is None:
                    evidence = (
                        session.query(EvidenceItem)
                        .filter(
                            EvidenceItem.case_id == (case_id or ""),
                            EvidenceItem.canonical_url
                            == (evidence_data.get("canonical_url") or event_data.get("source_url")),
                        )
                        .first()
                    )
                if evidence is None:
                    evidence = EvidenceItem(
                        id=evidence_id,
                        case_id=case_id or "",
                        event_id=event_id,
                        case_article_id=evidence_data.get("case_article_id")
                        or event_data.get("case_article_id"),
                        evidence_type=evidence_data.get("evidence_type", "article"),
                        source_type=evidence_data.get("source_type", "article"),
                        title=evidence_data.get("title", event_data.get("title")),
                        origin_url=evidence_data.get("origin_url")
                        or event_data.get("source_url"),
                        canonical_url=evidence_data.get("canonical_url")
                        or event_data.get("source_url"),
                        archived_url=evidence_data.get("archived_url"),
                        publisher=evidence_data.get("publisher")
                        or event_data.get("source_name"),
                        published_at=evidence_data.get("published_at"),
                        content=evidence_data.get("content"),
                        capture_metadata=evidence_data.get("capture_metadata", {}),
                        verification_status=evidence_data.get(
                            "verification_status", "UNVERIFIED"
                        ),
                        credibility_tier=evidence_data.get("credibility_tier"),
                        requires_human_review=1
                        if evidence_data.get("requires_human_review")
                        else 0,
                    )
                    session.add(evidence)
                else:
                    evidence.event_id = event_id
                    evidence.case_article_id = evidence_data.get("case_article_id") or evidence.case_article_id
                    evidence.evidence_type = evidence_data.get("evidence_type", evidence.evidence_type)
                    evidence.source_type = evidence_data.get("source_type", evidence.source_type)
                    evidence.title = evidence_data.get("title", evidence.title)
                    evidence.origin_url = evidence_data.get("origin_url") or evidence.origin_url
                    evidence.canonical_url = evidence_data.get("canonical_url") or evidence.canonical_url
                    evidence.publisher = evidence_data.get("publisher") or evidence.publisher
                    evidence.content = evidence_data.get("content", evidence.content)
                    evidence.capture_metadata = evidence_data.get(
                        "capture_metadata", evidence.capture_metadata
                    )
                    evidence.verification_status = evidence_data.get(
                        "verification_status", evidence.verification_status
                    )
                    evidence.credibility_tier = evidence_data.get(
                        "credibility_tier", evidence.credibility_tier
                    )
                    evidence.requires_human_review = (
                        1 if evidence_data.get("requires_human_review") else evidence.requires_human_review
                    )
                existing_link = (
                    session.query(ClaimEvidenceLink)
                    .filter(
                        ClaimEvidenceLink.claim_id == claim.id,
                        ClaimEvidenceLink.evidence_id == evidence.id,
                    )
                    .first()
                )
                if existing_link is None:
                    session.add(
                        ClaimEvidenceLink(
                            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"claim-evidence:{claim.id}:{evidence.id}")),
                            claim_id=claim.id,
                            evidence_id=evidence.id,
                            relation=evidence_data.get("relation", "supports"),
                            source_diversity_rank=evidence_data.get(
                                "source_diversity_rank", 1
                            ),
                            confidence_score=evidence_data.get("confidence_score"),
                            notes=evidence_data.get("notes"),
                        )
                    )
                for check_data in evidence_data.get("verification_checks", []):
                    check_id = str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"verification-check:{evidence.id}:{check_data.get('check_type')}:{check_data.get('result')}",
                        )
                    )
                    check = (
                        session.query(EvidenceVerificationCheck)
                        .filter(EvidenceVerificationCheck.id == check_id)
                        .first()
                    )
                    if check is None:
                        session.add(
                            EvidenceVerificationCheck(
                                id=check_id,
                                evidence_id=evidence.id,
                                check_type=check_data.get("check_type", "ingestion"),
                                result=check_data.get("result", "unknown"),
                                method=check_data.get("method"),
                                notes=check_data.get("notes"),
                                verified_by=check_data.get("verified_by"),
                            )
                        )

        for narrative_data in event_data.get("narratives", []):
            stored_cluster_id = f"{event_id}:{narrative_data['cluster_id']}"
            narrative = Narrative(
                id=str(uuid.uuid4()),
                cluster_id=stored_cluster_id,
                stance_summary=narrative_data["stance_summary"],
                source_count=narrative_data.get("claim_count", 0),
            )
            session.add(narrative)

        for investigation in event_data.get("party_investigations", []):
            party_name = investigation.get("party_name")
            party_id = party_name_to_id.get(party_name)
            if party_id is None:
                continue
            session.add(
                PartyInvestigation(
                    id=str(uuid.uuid4()),
                    event_id=event_id,
                    party_id=party_id,
                    investigation_data=investigation.get("investigation", {}),
                    party_stance=investigation.get("party_stance", {}).get(
                        "overall_position"
                    ),
                )
            )

        if create_review:
            review = session.query(Review).filter(Review.event_id == event_id).first()
            if review is None:
                review = Review(
                    id=str(uuid.uuid4()),
                    event_id=event_id,
                    status=ReviewStatus.PENDING,
                )
                session.add(review)
            else:
                review.status = ReviewStatus.PENDING
                review.reviewed_at = None

        session.commit()
        return True
    except Exception as exc:
        session.rollback()
        logger.error("Error storing event %s: %s", event_data.get("id"), exc)
        return False
    finally:
        session.close()
