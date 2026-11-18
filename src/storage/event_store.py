"""Persistence helpers for workflow outputs."""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any, cast

from sqlalchemy.orm import Session

from src.storage import (
    Claim,
    ClaimEvidenceLink,
    EvidenceCapture,
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
from src.storage.citations import (
    ALIGNMENT_VERSION,
    DEFAULT_ALIGNMENT_STATUS,
    RELATIONSHIP_POLICY_VERSION,
    AnalysisScope,
    QuoteProposal,
    record_claim_citation,
    resolve_effective_relationship,
    validate_quote_alignment,
)
from src.storage.review_state import (
    LEGACY_ANALYSIS_HASH_VERSION,
    compute_event_analysis_hash,
    compute_legacy_event_analysis_hash,
    reconcile_review_with_analysis,
)
from src.storage.captures import build_capture_metadata, record_evidence_capture

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


def _is_real_int(value: Any) -> bool:
    """Return True for a genuine int (``bool`` is deliberately excluded)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _analysis_scope(
    event_data: dict[str, Any], capture: Any
) -> AnalysisScope | None:
    """Build the recorded analysis scope, or ``None`` when it is not known.

    The scope is the actual body region supplied to the extractor, recorded by the
    collector on ``event_data["extraction_outcome"]``. Missing/non-int bounds mean
    *no scope* (never the whole capture), so validation fails closed. The body hash
    is the immutable capture's own full-body SHA-256.
    """
    if capture is None:
        return None
    outcome = event_data.get("extraction_outcome")
    if not isinstance(outcome, dict):
        return None
    start_char = outcome.get("scope_start")
    end_char = outcome.get("scope_end")
    if not _is_real_int(start_char) or not _is_real_int(end_char):
        return None
    return AnalysisScope(
        start_char=cast(int, start_char),
        end_char=cast(int, end_char),
        body_sha256=cast("str | None", capture.text_sha256),
    )


def _quote_proposal(claim_data: dict[str, Any]) -> QuoteProposal | None:
    """Return the claim's own proposal, or ``None`` when no quote was proposed."""
    quote = claim_data.get("source_quote")
    start_char = claim_data.get("source_quote_start")
    end_char = claim_data.get("source_quote_end")
    if quote is None and start_char is None and end_char is None:
        return None
    return QuoteProposal(
        quote=quote if isinstance(quote, str) else None,
        start_char=start_char if _is_real_int(start_char) else None,
        end_char=end_char if _is_real_int(end_char) else None,
    )


def _assessment_inputs(
    evidence_data: dict[str, Any],
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    """Extract explicit assessment provenance supplied by a caller.

    Nothing is synthesized from extraction confidence: an absent/unknown origin or
    version stays ``None`` and the policy fails closed.
    """
    origin = evidence_data.get("assessment_origin")
    version = evidence_data.get("assessment_version")
    metadata = evidence_data.get("assessment_metadata")
    return (
        origin if isinstance(origin, str) else None,
        version if isinstance(version, str) else None,
        dict(metadata) if isinstance(metadata, dict) else None,
    )


def _claim_signature_for(
    claim_data: dict[str, Any], claim_text: str
) -> str:
    """Stored claim signature, falling back to the documented text rule."""
    signature = claim_data.get("claim_signature")
    if isinstance(signature, str) and signature:
        return signature
    return hashlib.sha256(claim_text.lower().strip().encode("utf-8")).hexdigest()


def _link_semantics(
    session: Session,
    *,
    event_data: dict[str, Any],
    claim_data: dict[str, Any],
    evidence_data: dict[str, Any],
    claim: Claim,
    evidence: Any,
    case_id: str | None,
) -> dict[str, Any]:
    """Resolve one claim/evidence attachment through the evidence policy.

    Ordering guaranteed to the caller: the evidence and its immutable capture are
    already flushed, so a citation can be recorded here and the returned
    ``citation_id`` is immediately valid for the link row.
    """
    capture_id = cast("str | None", evidence.current_capture_id)
    capture = (
        session.get(EvidenceCapture, capture_id) if capture_id else None
    )
    if capture is not None:
        # A dangling pointer is "no capture", never a fabricated FK value.
        capture_id = cast(str, capture.id)
    else:
        capture_id = None

    stored_relation = evidence_data.get("relation")
    proposal = _quote_proposal(claim_data)
    origin, version, assessment_metadata = _assessment_inputs(evidence_data)
    explicit_assessment = (
        origin is not None or version is not None or assessment_metadata is not None
    )

    # Only a trusted collector outcome marks a claim/evidence attachment as
    # collector-generated. An explicit caller assessment labels it as an assessor
    # contribution instead, so the collector branch cannot suppress it.
    outcome = event_data.get("extraction_outcome")
    trusted_outcome = (
        isinstance(outcome, dict) and outcome.get("quote_proposals_trusted") is True
    )
    collector_generated = trusted_outcome and not explicit_assessment

    claim_text = cast(str, claim.claim_text)
    claim_signature = _claim_signature_for(claim_data, claim_text)
    scope = _analysis_scope(event_data, capture)

    result = None
    if (
        case_id
        and capture is not None
        and capture_id
        and (proposal is not None or explicit_assessment)
    ):
        result = record_claim_citation(
            session,
            case_id=case_id,
            capture_id=capture_id,
            claim_signature=claim_signature,
            claim_text=claim_text,
            scope=scope,
            proposal=proposal,
            evidence_id=cast(str, evidence.id),
            original_claim_id=cast(str, claim.id),
            stored_relation=stored_relation,
            assessment_origin=origin,
            assessment_version=version,
            assessment_metadata=assessment_metadata,
            collector_generated=collector_generated,
        )
        alignment = result.alignment
        resolution = result.relationship
        citation = result.citation
    elif capture is not None and (proposal is not None or explicit_assessment):
        # No case/citation context (legacy or CLI event): still resolve the
        # relationship honestly instead of silently defaulting to support.
        alignment = validate_quote_alignment(
            cast(str, capture.text), proposal, scope
        )
        resolution = resolve_effective_relationship(
            stored_relation=stored_relation,
            alignment_status=alignment.status,
            assessment_origin=origin,
            assessment_version=version,
            exact_anchor=alignment.is_exact,
            collector_generated=collector_generated,
        )
        citation = None
    else:
        alignment = None
        resolution = None
        citation = None

    if alignment is not None and resolution is not None:
        alignment_status = alignment.status
        relation = resolution.effective_relationship
        diagnostic_reason = alignment.diagnostic_reason
        alignment_version = alignment.alignment_version
        relationship_policy = resolution.policy_version
    else:
        alignment_status = DEFAULT_ALIGNMENT_STATUS
        relation = "uncertain"
        relationship_policy = RELATIONSHIP_POLICY_VERSION
        alignment_version = ALIGNMENT_VERSION
        if capture is None:
            diagnostic_reason = "capture_unavailable"
        elif proposal is None:
            diagnostic_reason = "quote_not_proposed"
        else:
            diagnostic_reason = "case_context_unavailable"

    # Only the citation's frozen provenance labels the link as collector/assessed.
    if citation is not None:
        link_origin = cast("str | None", citation.assessment_origin)
        link_version = cast("str | None", citation.assessment_version)
    else:
        link_origin = origin
        link_version = version

    metadata: dict[str, Any] = {
        "alignment_version": alignment_version,
        "relationship_policy": relationship_policy,
        "stored_relation": stored_relation,
    }
    if alignment is None or not alignment.is_exact:
        metadata["diagnostic_reason"] = diagnostic_reason

    exact = alignment is not None and alignment.is_exact
    return {
        "capture_id": capture_id,
        "citation_id": cast("str | None", citation.id) if citation is not None else None,
        "quote": alignment.quote if exact and alignment is not None else None,
        "start_char": alignment.start_char if exact and alignment is not None else None,
        "end_char": alignment.end_char if exact and alignment is not None else None,
        "alignment_status": alignment_status,
        "assessment_origin": link_origin,
        "assessment_version": link_version,
        "assessment_metadata": metadata,
        "relation": relation,
    }


def store_event_in_db(
    event_data: dict[str, Any],
    *,
    case_id: str | None = None,
    case_run_id: str | None = None,
    investigation_run_id: str | None = None,
    create_review: bool = True,
    confirmed_parties: list[str] | None = None,
    session: Session | None = None,
) -> bool:
    """Store processed event in the database.

    Without ``session`` this owns a short-lived session and keeps the legacy
    ``True``/``False`` return contract: it commits on success, rolls back and
    logs on failure, and always closes its own session.

    With ``session`` the caller owns the transaction. The writer only flushes
    (so subsequent queries in the caller's session see the writes) and never
    commits, rolls back or closes it; write errors propagate so the caller can
    roll back a whole event batch.
    """
    if session is not None:
        _write_event(
            session,
            event_data,
            case_id=case_id,
            case_run_id=case_run_id,
            investigation_run_id=investigation_run_id,
            create_review=create_review,
            confirmed_parties=confirmed_parties,
        )
        return True

    own_session = get_database().get_session_sync()
    try:
        _write_event(
            own_session,
            event_data,
            case_id=case_id,
            case_run_id=case_run_id,
            investigation_run_id=investigation_run_id,
            create_review=create_review,
            confirmed_parties=confirmed_parties,
        )
        own_session.commit()
        return True
    except Exception as exc:
        own_session.rollback()
        logger.error("Error storing event %s: %s", event_data.get("id"), exc)
        return False
    finally:
        own_session.close()


def _upsert_evidence(
    session: Session,
    *,
    evidence_data: dict[str, Any],
    event_data: dict[str, Any],
    case_id: str | None,
    event_id: str,
    case_run_id: str | None,
    pending_evidence: dict[str, Any],
    pending_checks: dict[str, Any],
) -> Any:
    """Get-or-create one source record and persist any supplied body.

    Shared by top-level ``event_data["evidence"]`` and per-claim evidence
    payloads, so a valid zero-claim event still retains its captured source.
    Any supplied ``content`` becomes an immutable capture version; claim links
    are created by the caller only for actual claims.
    """
    evidence_id = evidence_data.get("id") or _evidence_identifier(
        case_id, event_id, evidence_data, event_data
    )
    evidence = pending_evidence.get(evidence_id)
    if evidence is None:
        evidence = (
            session.query(EvidenceItem)
            .filter(EvidenceItem.id == evidence_id)
            .first()
        )
        if evidence is not None:
            existing_case_id = cast("str | None", evidence.case_id)
            if (existing_case_id or "") != (case_id or ""):
                raise ValueError(
                    f"Evidence {evidence_id!r} belongs to a different case; "
                    "refusing to reparent existing capture history"
                )
    # Canonical fallback requires a non-empty known URL. Querying
    # ``canonical_url == None`` would merge unrelated anonymous evidence items
    # once earlier rows become visible through staged flushes.
    fallback_url = evidence_data.get("canonical_url") or event_data.get("source_url")
    if evidence is None and fallback_url:
        evidence = (
            session.query(EvidenceItem)
            .filter(
                EvidenceItem.case_id == (case_id or ""),
                EvidenceItem.canonical_url == fallback_url,
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
            origin_url=evidence_data.get("origin_url") or event_data.get("source_url"),
            canonical_url=evidence_data.get("canonical_url")
            or event_data.get("source_url"),
            archived_url=evidence_data.get("archived_url"),
            publisher=evidence_data.get("publisher") or event_data.get("source_name"),
            published_at=evidence_data.get("published_at"),
            # The compatibility projection is set only by the capture helper
            # below so it always matches the normalized capture text.
            content=None,
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
        # Parent before dependent: make a new EvidenceItem visible before its
        # capture/check children are flushed (no ORM relationships declare
        # this ordering, so rely on explicit staged flushes).
        session.flush([evidence])
    else:
        evidence.event_id = event_id
        evidence.case_article_id = (
            evidence_data.get("case_article_id") or evidence.case_article_id
        )
        evidence.evidence_type = evidence_data.get(
            "evidence_type", evidence.evidence_type
        )
        evidence.source_type = evidence_data.get(
            "source_type", evidence.source_type
        )
        evidence.title = evidence_data.get("title", evidence.title)
        evidence.origin_url = evidence_data.get("origin_url") or evidence.origin_url
        evidence.canonical_url = (
            evidence_data.get("canonical_url") or evidence.canonical_url
        )
        evidence.publisher = evidence_data.get("publisher") or evidence.publisher
        # Explicitly supplied provenance is applied before freezing capture
        # metadata: omitted keeps the stored value, explicit None clears it.
        if "archived_url" in evidence_data:
            evidence.archived_url = evidence_data["archived_url"]
        if "published_at" in evidence_data:
            evidence.published_at = evidence_data["published_at"]
        supplied_capture_metadata = evidence_data.get("capture_metadata")
        if supplied_capture_metadata is not None:
            evidence.capture_metadata = supplied_capture_metadata
        evidence.verification_status = evidence_data.get(
            "verification_status", evidence.verification_status
        )
        evidence.credibility_tier = evidence_data.get(
            "credibility_tier", evidence.credibility_tier
        )
        evidence.requires_human_review = (
            1
            if evidence_data.get("requires_human_review")
            else evidence.requires_human_review
        )

    pending_evidence[evidence_id] = evidence
    pending_evidence[str(evidence.id)] = evidence

    # A supplied body (including an explicit empty string) is an immutable
    # capture. ``None``/missing means no incoming body: keep any existing
    # capture and compatibility projection untouched.
    supplied_body = evidence_data.get("content")
    if supplied_body is not None:
        metadata = build_capture_metadata(
            evidence,
            extra={
                # Event.case_run_id is a stage-attempt ID, not a future grouped
                # investigation invocation ID; label it accordingly.
                "origin_stage_attempt_id": case_run_id,
                "extraction": evidence_data.get("extraction_metadata"),
            },
        )
        record_evidence_capture(
            session,
            evidence,
            text=supplied_body,
            observed_at=evidence_data.get("observed_at"),
            capture_kind=evidence_data.get("capture_kind", "live"),
            metadata=metadata,
        )

    for check_data in evidence_data.get("verification_checks", []):
        check_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"verification-check:{evidence.id}:{check_data.get('check_type')}:{check_data.get('result')}",
            )
        )
        check = pending_checks.get(check_id)
        if check is None:
            check = (
                session.query(EvidenceVerificationCheck)
                .filter(EvidenceVerificationCheck.id == check_id)
                .first()
            )
            if check is not None:
                pending_checks[check_id] = check
        if check is None:
            check = EvidenceVerificationCheck(
                id=check_id,
                evidence_id=evidence.id,
                check_type=check_data.get("check_type", "ingestion"),
                result=check_data.get("result", "unknown"),
                method=check_data.get("method"),
                notes=check_data.get("notes"),
                verified_by=check_data.get("verified_by"),
            )
            session.add(check)
            pending_checks[check_id] = check
        else:
            # Bounded upsert of supplied semantic fields: an omitted key
            # keeps its stored value and an explicit null clears it. Other
            # checks are never deleted — verification checks are cumulative
            # observations, not an authoritative full replacement.
            for field in ("method", "notes", "verified_by"):
                if field in check_data:
                    setattr(check, field, check_data[field])

    return evidence


# Only a collector outcome that actually completed a scoped extraction may
# replace stored analysis. ``empty`` is included because a truthfully validated
# empty collection is an authoritative result (it is allowed to remove prior
# claims); fallback/unavailable/unknown statuses are not.
_AUTHORITATIVE_OUTCOME_STATUSES = ("valid", "empty")


def _payload_may_replace_analysis(event_data: dict[str, Any]) -> bool:
    """Return whether this payload may replace an existing event's analysis.

    Authority is derived **only** from ``extraction_outcome.status``:

    * the outcome is absent/not a dict -> ``True``. Legacy/CLI callers (and
      direct ``store_event_in_db`` users) keep the historical full-replacement
      semantics; this is a hard compatibility requirement.
    * status ``valid`` or ``empty`` -> ``True``; the extraction completed over
      its recorded scope, and an explicitly validated empty result is allowed
      to replace prior claims.
    * anything else, including ``fallback``, ``unavailable`` and an unrecognised
      or forged status -> ``False``. A separate boolean flag is deliberately
      not trusted, so a malformed payload cannot claim authority.
    """
    outcome = event_data.get("extraction_outcome")
    if not isinstance(outcome, dict):
        return True
    return outcome.get("status") in _AUTHORITATIVE_OUTCOME_STATUSES


def _persist_source_evidence_only(
    session: Session,
    event_data: dict[str, Any],
    *,
    case_id: str | None,
    event_id: str,
    case_run_id: str | None,
) -> None:
    """Persist/reuse an event's source evidence without replacing analysis.

    Used by the guarded path in ``_write_event`` when an existing event is
    rewritten by a non-authoritative extraction. Only the top-level source
    evidence is written: claims, links, narratives, party investigations and
    the event's own analysis fields are left untouched. Any supplied body still
    becomes (or reuses) an immutable capture exactly as in the full path.
    """
    pending_evidence: dict[str, Any] = {}
    pending_checks: dict[str, Any] = {}
    for evidence_data in event_data.get("evidence", []) or []:
        _upsert_evidence(
            session,
            evidence_data=evidence_data,
            event_data=event_data,
            case_id=case_id,
            event_id=event_id,
            case_run_id=case_run_id,
            pending_evidence=pending_evidence,
            pending_checks=pending_checks,
        )
    session.flush()


def _write_event(
    session: Session,
    event_data: dict[str, Any],
    *,
    case_id: str | None,
    case_run_id: str | None,
    investigation_run_id: str | None = None,
    create_review: bool,
    confirmed_parties: list[str] | None,
) -> None:
    """Write one event inside a caller-owned transaction.

    Never commits, rolls back or closes ``session``; any error propagates.
    """
    # Make writes from a previous event in the same batch visible to the
    # queries below (SessionLocal uses autoflush=False).
    session.flush()

    event_id = event_data["id"]
    confirmed_party_names = {
        _normalize_party_name(name)
        for name in (confirmed_parties or [])
        if isinstance(name, str) and name.strip()
    }
    existing_event = session.query(Event).filter(Event.id == event_id).first()
    if existing_event is not None and not _payload_may_replace_analysis(event_data):
        # A fallback/unavailable/unknown rerun must never erase valid analysis.
        # Source evidence (and its immutable capture) is still persisted or
        # reused; reviews are deliberately left exactly as they are.
        outcome = event_data.get("extraction_outcome")
        status = outcome.get("status") if isinstance(outcome, dict) else None
        logger.warning(
            "Preserving stored analysis for event %s: extraction outcome %r is "
            "not authoritative; persisting source evidence only",
            event_id,
            status,
        )
        _persist_source_evidence_only(
            session,
            event_data,
            case_id=case_id,
            event_id=event_id,
            case_run_id=case_run_id,
        )
        return

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
        # Execute the pending narrative DELETEs before the rewritten rows are
        # added; the unit of work can otherwise order INSERTs first and hit the
        # unique ``narratives.cluster_id`` constraint on a rewrite.
        if existing_narratives:
            session.flush()

        event = existing_event
        event.timestamp = event_data["timestamp"]
        event.title = event_data["title"]
        event.summary = event_data["summary"]
        event.verification_status = _to_verification_status(
            event_data["verification_status"]
        )
        event.location_country_code = event_data.get("location_country_code")
        event.location_lat = event_data.get("location_lat")
        event.location_lon = event_data.get("location_lon")
        event.case_id = case_id
        event.case_run_id = case_run_id
        event.investigation_run_id = investigation_run_id
        event.workflow_route = event_data.get("workflow_route")
        event.source_url = event_data.get("source_url")
    else:
        event = Event(
            id=event_id,
            timestamp=event_data["timestamp"],
            title=event_data["title"],
            summary=event_data["summary"],
            verification_status=_to_verification_status(
                event_data["verification_status"]
            ),
            location_country_code=event_data.get("location_country_code"),
            location_lat=event_data.get("location_lat"),
            location_lon=event_data.get("location_lon"),
            case_id=case_id,
            case_run_id=case_run_id,
            investigation_run_id=investigation_run_id,
            workflow_route=event_data.get("workflow_route"),
            source_url=event_data.get("source_url"),
        )
        session.add(event)

    # Parent before dependent: Event must be inserted/updated before parties,
    # claims, evidence and captures. A broad autoflush from a capture write would
    # otherwise be free to insert a Claim before its Event under FK enforcement.
    session.flush([event])

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

    # Parent before dependent: Claim.party_id references a party that may be
    # newly pending. Flush parties before any claim/capture/check write.
    session.flush()

    # Pending rows written in this event that a DB query cannot see yet
    # (SessionLocal uses autoflush=False). Two claims commonly share the same
    # evidence payload, so without these caches the second reference would
    # attempt a duplicate INSERT with the same deterministic primary key.
    pending_evidence: dict[str, Any] = {}
    pending_links: set[tuple[str, str]] = set()
    pending_checks: dict[str, Any] = {}

    # Top-level source evidence is persisted independently of claims: a valid
    # zero-claim event still retains its captured source record (and capture),
    # but no claim attachment links are invented.
    for evidence_data in event_data.get("evidence", []) or []:
        _upsert_evidence(
            session,
            evidence_data=evidence_data,
            event_data=event_data,
            case_id=case_id,
            event_id=event_id,
            case_run_id=case_run_id,
            pending_evidence=pending_evidence,
            pending_checks=pending_checks,
        )

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
        # Parent before dependent: the claim must exist before its link is
        # flushed, even if an evidence/capture write flushes in between.
        session.flush([claim])

        evidence_payload = claim_data.get("evidence", [])
        for evidence_data in evidence_payload:
            evidence = _upsert_evidence(
                session,
                evidence_data=evidence_data,
                event_data=event_data,
                case_id=case_id,
                event_id=event_id,
                case_run_id=case_run_id,
                pending_evidence=pending_evidence,
                pending_checks=pending_checks,
            )
            link_key = (str(claim.id), str(evidence.id))
            existing_link = None
            if link_key not in pending_links:
                existing_link = (
                    session.query(ClaimEvidenceLink)
                    .filter(
                        ClaimEvidenceLink.claim_id == claim.id,
                        ClaimEvidenceLink.evidence_id == evidence.id,
                    )
                    .first()
                )
            if existing_link is None and link_key not in pending_links:
                pending_links.add(link_key)
                semantics = _link_semantics(
                    session,
                    event_data=event_data,
                    claim_data=claim_data,
                    evidence_data=evidence_data,
                    claim=claim,
                    evidence=evidence,
                    case_id=case_id,
                )
                session.add(
                    ClaimEvidenceLink(
                        id=str(
                            uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                f"claim-evidence:{claim.id}:{evidence.id}",
                            )
                        ),
                        claim_id=claim.id,
                        evidence_id=evidence.id,
                        relation=semantics["relation"],
                        source_diversity_rank=evidence_data.get(
                            "source_diversity_rank", 1
                        ),
                        confidence_score=evidence_data.get("confidence_score"),
                        notes=evidence_data.get("notes"),
                        capture_id=semantics["capture_id"],
                        citation_id=semantics["citation_id"],
                        quote=semantics["quote"],
                        start_char=semantics["start_char"],
                        end_char=semantics["end_char"],
                        alignment_status=semantics["alignment_status"],
                        assessment_origin=semantics["assessment_origin"],
                        assessment_version=semantics["assessment_version"],
                        assessment_metadata=semantics["assessment_metadata"],
                    )
                )

    for narrative_data in event_data.get("narratives", []):
        stored_cluster_id = f"{event_id}:{narrative_data['cluster_id']}"
        narrative = Narrative(
            id=str(uuid.uuid4()),
            cluster_id=stored_cluster_id,
            stance_summary=narrative_data["stance_summary"],
            source_count=narrative_data.get(
                "source_count", narrative_data.get("claim_count", 0)
            ),
            # Party-investigation narrative metadata (union with the baseline
            # workflow's narrative schema).
            key_themes=narrative_data.get("key_themes", []),
            main_entities=narrative_data.get("main_entities", []),
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
                party_name=party_name,
                investigation_data=investigation.get("investigation", {}),
                party_stance=investigation.get("party_stance", {}).get(
                    "overall_position"
                ),
            )
        )

    # Flush the complete event write (including the create_review=False path) so
    # the caller-owned session can immediately query the rows it just wrote.
    session.flush()

    if create_review:
        # The hash is computed from the flushed rows above.
        analysis_hash = compute_event_analysis_hash(session, event_id)
        review = session.query(Review).filter(Review.event_id == event_id).first()
        if review is None:
            session.add(
                Review(
                    id=str(uuid.uuid4()),
                    event_id=event_id,
                    status=ReviewStatus.PENDING,
                    analysis_hash=analysis_hash,
                )
            )
        else:
            # A pre-E02 stored decision was bound to the legacy digest. Only
            # compute it when the stored hash is actually a legacy one that
            # differs, so the conservative NULL-hash policy is unchanged and no
            # extra projection runs for current hashes.
            stored_hash = cast("str | None", review.analysis_hash) or None
            legacy_hash = None
            if (
                stored_hash is not None
                and stored_hash != analysis_hash
                and stored_hash.startswith(f"{LEGACY_ANALYSIS_HASH_VERSION}:")
            ):
                legacy_hash = compute_legacy_event_analysis_hash(session, event_id)
            reconcile_review_with_analysis(
                review,
                analysis_hash,
                legacy_analysis_hash=legacy_hash,
            )


__all__ = ["store_event_in_db"]
