"""Persistence helpers for workflow outputs."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from src.storage import (
    Claim,
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


def store_event_in_db(
    event_data: dict[str, Any],
    *,
    case_id: str | None = None,
    case_run_id: str | None = None,
    create_review: bool = True,
) -> bool:
    """Store processed event in the database."""
    db = get_database()
    session = db.get_session_sync()

    try:
        event_id = event_data["id"]
        existing_event = session.query(Event).filter(Event.id == event_id).first()
        if existing_event is not None:
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
                    event_id=event_id,
                )
                session.add(party)
            else:
                party.aliases = party_data.get("aliases", party.aliases)
                party.description = party_data.get("description", party.description)
                party.event_id = event_id

            party_name_to_id[party_name] = party.id

        for claim_data in event_data.get("claims", []):
            claim = Claim(
                id=str(uuid.uuid4()),
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
            )
            session.add(claim)

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
