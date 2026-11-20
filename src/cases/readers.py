"""Typed read models for the evidence inspector (E03).

Every function here is a **session-in, plain-dict-out** reader:

* no commit, rollback or session closing;
* no capture creation, no legacy materialization, no analysis, no model call;
* case ownership is re-checked against stored rows, never trusted from the URL;
* one deterministic query per lookup and no lazy loading of unrelated rows.

Callers are :class:`src.cases.service.TopicCaseService` (which owns the session
lifetime) and, through it, the HTTP layer, which maps these snake_case dicts onto
the camelCase DTOs. ``None`` means "not found for this case" and maps to HTTP
404; :class:`CaptureRangeError` means "malformed text window" and maps to 422.

Nothing here exposes capture bodies at the case/claim/evidence level: only the
explicit capture-window reader returns stored text, and only for the window the
caller asked for.
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.cases.history import (
    get_case_snapshot,
    snapshot_entities,
    snapshot_entity_list,
    snapshot_payload,
)
from src.storage import (
    Claim,
    ClaimCitation,
    ClaimEvidenceLink,
    EvidenceCapture,
    EvidenceItem,
    Event,
)
from src.storage.citations import (
    AlignmentStatus,
    COLLECTOR_ORIGIN,
    DEFAULT_ALIGNMENT_STATUS,
    resolve_effective_relationship,
)

#: Default and maximum capture text-window length, in Unicode code points.
DEFAULT_CAPTURE_WINDOW_LENGTH = 20000
MAX_CAPTURE_WINDOW_LENGTH = 50000


class CaptureRangeError(ValueError):
    """A malformed capture text-window request (maps to HTTP 422).

    Deliberately an exception rather than a ``None`` return: ``None`` already
    means "this capture is not yours / does not exist" (404), and a bad range
    must never be confused with a missing resource.
    """


class SnapshotNotFound(LookupError):
    """The requested snapshot selector is unknown or belongs to another case.

    A supplied but unresolvable snapshot is a distinct failure from an entity
    that is absent *inside* a resolved snapshot (``None`` -> 404) and from a
    reader that does not support historical selection at all (422). Raising
    explicitly keeps a caller from believing it read historical state when the
    selector was ignored.
    """


def _iso(value: Any) -> str | None:
    """Serialize a stored timestamp without inventing a value when absent.

    ``value`` is typed loosely because these models use classic ``Column[...]``
    declarations, so reading an attribute is typed as a descriptor rather than
    the stored value. At runtime it is an aware ``datetime`` or ``None``.
    """
    isoformat = getattr(value, "isoformat", None)
    if not callable(isoformat):
        return None
    rendered = isoformat()
    return rendered if isinstance(rendered, str) else None


def _as_int(value: Any) -> int | None:
    """Return a genuine stored int (``bool`` is not an offset)."""
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _label(value: Any) -> str | None:
    """Return a stored enum member's value (or a plain stored string)."""
    if value is None:
        return None
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    return value if isinstance(value, str) else None


def _metadata(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _is_legacy_shaped_link(
    *,
    citation_id: str | None,
    capture_id: str | None,
    alignment_status: str | None,
    assessment_origin: str | None,
    assessment_version: str | None,
    assessment_metadata: dict[str, Any],
) -> bool:
    """Positive evidence that a link predates the E02 quotation writer.

    Shared by the live and snapshot claim readers so a historical claim cannot
    acquire a stronger provenance than the same row would report when live.
    """
    return (
        citation_id is None
        and capture_id is None
        and (
            alignment_status is None
            or alignment_status == DEFAULT_ALIGNMENT_STATUS
        )
        and assessment_origin is None
        and assessment_version is None
        and "relationship_policy" not in assessment_metadata
    )


def _link_reference_from_fields(
    *,
    relation: str | None,
    alignment_status: str,
    quote: str | None,
    start_char: int | None,
    end_char: int | None,
    capture_id: str | None,
    citation_id: str | None,
    assessment_origin: str | None,
    assessment_version: str | None,
    diagnostic_reason: str | None,
) -> dict[str, Any]:
    """Policy-resolve one link reference from already-read values.

    Used for live ORM links and for frozen snapshot link rows, so a historical
    comparison resolves relationships with exactly the live policy.
    """
    resolution = resolve_effective_relationship(
        stored_relation=relation,
        alignment_status=alignment_status,
        assessment_origin=assessment_origin,
        assessment_version=assessment_version,
        exact_anchor=(alignment_status == AlignmentStatus.EXACT.value),
        collector_generated=(assessment_origin == COLLECTOR_ORIGIN),
    )
    return {
        "relation": relation,
        "effective_relation": resolution.effective_relationship,
        "alignment_status": alignment_status,
        "quote": quote,
        "start_char": start_char,
        "end_char": end_char,
        "capture_id": capture_id,
        "citation_id": citation_id,
        "assessment_origin": assessment_origin,
        "assessment_version": assessment_version,
        "diagnostic_reason": diagnostic_reason,
    }


def link_read_model(link: ClaimEvidenceLink) -> dict[str, Any]:
    """Return the honest read model of one claim/evidence link.

    ``relation`` is the raw stored value kept for diagnostics (a legacy
    ``opposes``/``supports`` is never rewritten). ``effective_relation`` is the
    policy-resolved value, using exactly the same inputs as the aggregate
    recomputation in the case service, so a reader can never claim more support
    than the writer counted.
    """
    return _link_reference_from_fields(
        relation=_as_str(link.relation),
        alignment_status=_as_str(link.alignment_status)
        or DEFAULT_ALIGNMENT_STATUS,
        quote=_as_str(link.quote),
        start_char=_as_int(link.start_char),
        end_char=_as_int(link.end_char),
        capture_id=_as_str(link.capture_id),
        citation_id=_as_str(link.citation_id),
        assessment_origin=_as_str(link.assessment_origin),
        assessment_version=_as_str(link.assessment_version),
        diagnostic_reason=_as_str(
            _metadata(link.assessment_metadata).get("diagnostic_reason")
        ),
    )


def snapshot_link_read_model(link: dict[str, Any]) -> dict[str, Any]:
    """Policy-resolve one **frozen snapshot** link row (camelCase payload keys)."""
    return _link_reference_from_fields(
        relation=_as_str(link.get("relation")),
        alignment_status=_as_str(link.get("alignmentStatus"))
        or DEFAULT_ALIGNMENT_STATUS,
        quote=_as_str(link.get("quote")),
        start_char=_as_int(link.get("startChar")),
        end_char=_as_int(link.get("endChar")),
        capture_id=_as_str(link.get("captureId")),
        citation_id=_as_str(link.get("citationId")),
        assessment_origin=_as_str(link.get("assessmentOrigin")),
        assessment_version=_as_str(link.get("assessmentVersion")),
        diagnostic_reason=_as_str(
            _metadata(link.get("assessmentMetadata")).get("diagnostic_reason")
        ),
    )


def _evidence_source_model(evidence: EvidenceItem) -> dict[str, Any]:
    """Source metadata shared by the citation and evidence detail readers."""
    return {
        "id": evidence.id,
        "event_id": _as_str(evidence.event_id),
        "case_article_id": _as_str(evidence.case_article_id),
        "evidence_type": _as_str(evidence.evidence_type),
        "source_type": _as_str(evidence.source_type),
        "title": _as_str(evidence.title),
        "origin_url": _as_str(evidence.origin_url),
        "canonical_url": _as_str(evidence.canonical_url),
        "publisher": _as_str(evidence.publisher),
        "published_at": _as_str(evidence.published_at),
        "verification_status": _label(evidence.verification_status),
        "credibility_tier": _as_str(evidence.credibility_tier),
        "requires_human_review": bool(evidence.requires_human_review),
        "capture_metadata": _metadata(evidence.capture_metadata),
        "current_capture_id": _as_str(evidence.current_capture_id),
    }


def _capture_summary_model(
    capture: EvidenceCapture, *, current_capture_id: str | None
) -> dict[str, Any]:
    """Capture metadata only: the body is never part of a summary."""
    body = cast(str, capture.text)
    capture_id = _as_str(capture.id)
    return {
        "id": capture_id,
        "evidence_id": _as_str(capture.evidence_id),
        "text_sha256": _as_str(capture.text_sha256),
        "normalized_text_sha256": _as_str(capture.normalized_text_sha256),
        "normalization_version": _as_str(capture.normalization_version),
        "capture_kind": _as_str(capture.capture_kind),
        "recorded_at": _iso(capture.recorded_at),
        "observed_at": _iso(capture.observed_at),
        "metadata": _metadata(capture.metadata_json),
        "char_length": len(body),
        "is_current": bool(capture_id) and capture_id == current_capture_id,
    }


def _belongs_to_case(row: Any, case_id: str) -> bool:
    """Explicit ownership check against the stored ``case_id`` value."""
    return _as_str(getattr(row, "case_id", None)) == case_id


def _claim_belongs_to_case(session: Session, claim: Any, case_id: str) -> bool:
    """A claim is owned through its event's case (there is no claim case FK)."""
    event_id = _as_str(claim.event_id)
    event = session.get(Event, event_id) if event_id else None
    return event is not None and _belongs_to_case(event, case_id)


def _captures_for_evidence(
    session: Session, evidence: EvidenceItem
) -> list[EvidenceCapture]:
    return list(
        session.scalars(
            select(EvidenceCapture)
            .where(EvidenceCapture.evidence_id == evidence.id)
            .order_by(EvidenceCapture.recorded_at.asc(), EvidenceCapture.id.asc())
        ).all()
    )


def read_citation(
    session: Session, *, case_id: str, citation_id: str
) -> dict[str, Any] | None:
    """Read one append-only citation by ID **and** owning case.

    The citation is resolved from its own frozen claim text/signature,
    relationship, passage, alignment/assessment provenance and capture pointer;
    no live ``Claim``/``ClaimEvidenceLink`` join is required, so a rewritten or
    deleted live claim cannot delete the inspector view. Whether the historical
    claim still exists is reported separately (``live_claim_present`` /
    ``live_claim_id``) instead of being guessed.
    """
    citation = session.get(ClaimCitation, citation_id)
    if citation is None or not _belongs_to_case(citation, case_id):
        return None

    capture_id = _as_str(citation.capture_id)
    capture = session.get(EvidenceCapture, capture_id) if capture_id else None
    evidence: EvidenceItem | None = None
    if capture is not None:
        capture_evidence_id = _as_str(capture.evidence_id)
        candidate = (
            session.get(EvidenceItem, capture_evidence_id)
            if capture_evidence_id
            else None
        )
        if candidate is not None and _belongs_to_case(candidate, case_id):
            evidence = candidate

    live_claim_id: str | None = None
    original_claim_id = _as_str(citation.original_claim_id)
    if original_claim_id is not None:
        live_claim = session.get(Claim, original_claim_id)
        if live_claim is not None and _claim_belongs_to_case(
            session, live_claim, case_id
        ):
            live_claim_id = _as_str(live_claim.id)

    return {
        "id": _as_str(citation.id),
        "case_id": _as_str(citation.case_id),
        "capture_id": capture_id,
        "evidence_id": _as_str(evidence.id) if evidence is not None else None,
        "original_claim_id": original_claim_id,
        "claim_signature": _as_str(citation.claim_signature),
        "claim_text": _as_str(citation.text) or "",
        "relationship": _as_str(citation.relationship) or "uncertain",
        "quote": _as_str(citation.quote) or "",
        "start_char": _as_int(citation.start_char),
        "end_char": _as_int(citation.end_char),
        "alignment_status": _as_str(citation.alignment_status)
        or DEFAULT_ALIGNMENT_STATUS,
        "alignment_version": _as_str(citation.alignment_version),
        "assessment_origin": _as_str(citation.assessment_origin),
        "assessment_version": _as_str(citation.assessment_version),
        "assessment_metadata": _metadata(citation.metadata_json),
        "recorded_at": _iso(citation.recorded_at),
        "live_claim_present": live_claim_id is not None,
        "live_claim_id": live_claim_id,
        "evidence": (
            _evidence_source_model(evidence) if evidence is not None else None
        ),
        "capture": (
            _capture_summary_model(
                capture,
                current_capture_id=(
                    _as_str(evidence.current_capture_id)
                    if evidence is not None
                    else None
                ),
            )
            if capture is not None
            else None
        ),
    }


def read_claim_detail(
    session: Session,
    *,
    case_id: str,
    claim_id: str,
    snapshot_id: str | None = None,
) -> dict[str, Any] | None:
    """Read one claim owned by ``case_id`` plus its evidence-linked passages.

    The claim is joined through ``Event.case_id``; a claim of another case is
    indistinguishable from an unknown claim (``None``). Counts are the stored
    policy-derived aggregates -- the reader never recomputes or inflates them.

    With ``snapshot_id`` the claim is resolved from that snapshot's frozen
    payload instead (see :func:`_read_claim_detail_from_snapshot`); current rows
    are never substituted. Live behavior is unchanged when no selector is given.
    """
    if snapshot_id is not None:
        return _read_claim_detail_from_snapshot(
            session, case_id=case_id, claim_id=claim_id, snapshot_id=snapshot_id
        )

    claim = session.get(Claim, claim_id)
    if claim is None or not _claim_belongs_to_case(session, claim, case_id):
        return None

    links = list(
        session.scalars(
            select(ClaimEvidenceLink)
            .where(ClaimEvidenceLink.claim_id == claim.id)
            .order_by(
                ClaimEvidenceLink.created_at.asc(), ClaimEvidenceLink.id.asc()
            )
        ).all()
    )
    evidence_ids = [
        evidence_id
        for evidence_id in (_as_str(link.evidence_id) for link in links)
        if evidence_id is not None
    ]
    evidence_by_id: dict[str, EvidenceItem] = {}
    if evidence_ids:
        rows = session.scalars(
            select(EvidenceItem).where(
                EvidenceItem.id.in_(evidence_ids),
                EvidenceItem.case_id == case_id,
            )
        ).all()
        evidence_by_id = {cast(str, row.id): row for row in rows}

    passages: list[dict[str, Any]] = []
    for link in links:
        evidence = evidence_by_id.get(_as_str(link.evidence_id) or "")
        if evidence is None:
            # A link whose evidence row is missing or belongs to another case has
            # no source metadata to show and must not leak across cases.
            continue
        passage: dict[str, Any] = {
            "id": evidence.id,
            "evidence_id": evidence.id,
            "title": _as_str(evidence.title),
            "publisher": _as_str(evidence.publisher),
            "origin_url": _as_str(evidence.origin_url),
            "canonical_url": _as_str(evidence.canonical_url),
            "source_type": _as_str(evidence.source_type),
            "confidence_score": link.confidence_score,
            "source_diversity_rank": _as_int(link.source_diversity_rank),
        }
        passage.update(link_read_model(link))
        passages.append(passage)

    return {
        "id": _as_str(claim.id),
        "case_id": case_id,
        "event_id": _as_str(claim.event_id),
        "claim_text": _as_str(claim.claim_text) or "",
        "claim_signature": _as_str(claim.claim_signature),
        "verification_status": _label(claim.verification_status),
        "verification_provenance": _verification_provenance(links),
        "fact_allegation_type": _label(claim.fact_allegation_type),
        "narrative_cluster_id": _as_str(claim.narrative_cluster_id),
        "controversy_score": claim.controversy_score,
        "party_positions": _metadata(claim.party_positions),
        "counts": {
            "support_count": claim.support_count or 0,
            "oppose_count": claim.oppose_count or 0,
            "source_diversity_count": claim.source_diversity_count or 0,
            "evidence_count": len(passages),
        },
        "passages": passages,
    }


def _verification_provenance(links: list[ClaimEvidenceLink]) -> str:
    """Derive the claim's verification provenance from provable stored data only.

    The ``claims`` table has no provenance column, so the honest default is
    ``"unknown"``. ``"legacy_unknown"`` is returned only on positive evidence
    that every attachment predates the E02 quotation writer: no citation, no
    capture, the honest ``not_provided`` alignment, no assessment origin/version
    and no writer-generated policy metadata. This reader never claims ``model``,
    ``human`` or reviewer confirmation.
    """
    if not links:
        return "unknown"
    for link in links:
        if not _is_legacy_shaped_link(
            citation_id=_as_str(link.citation_id),
            capture_id=_as_str(link.capture_id),
            alignment_status=_as_str(link.alignment_status),
            assessment_origin=_as_str(link.assessment_origin),
            assessment_version=_as_str(link.assessment_version),
            assessment_metadata=_metadata(link.assessment_metadata),
        ):
            return "unknown"
    return "legacy_unknown"


def _snapshot_verification_provenance(links: list[dict[str, Any]]) -> str:
    """Same provenance rule as :func:`_verification_provenance`, for frozen rows."""
    if not links:
        return "unknown"
    for link in links:
        if not _is_legacy_shaped_link(
            citation_id=_as_str(link.get("citationId")),
            capture_id=_as_str(link.get("captureId")),
            alignment_status=_as_str(link.get("alignmentStatus")),
            assessment_origin=_as_str(link.get("assessmentOrigin")),
            assessment_version=_as_str(link.get("assessmentVersion")),
            assessment_metadata=_metadata(link.get("assessmentMetadata")),
        ):
            return "unknown"
    return "legacy_unknown"


def _claim_live_state(
    session: Session,
    *,
    case_id: str,
    claim_id: str,
    frozen_text: str,
) -> dict[str, Any]:
    """Report whether the live claim still exists, without inventing history.

    A rewritten or deleted live claim must not erase a historical observation,
    and the historical view must say honestly whether the current row still
    matches the frozen text. Cross-case rows count as absent.
    """
    claim = session.get(Claim, claim_id)
    if claim is None or not _claim_belongs_to_case(session, claim, case_id):
        return {
            "present": False,
            "claim_signature": None,
            "text_matches_snapshot": None,
        }
    live_text = _as_str(claim.claim_text) or ""
    return {
        "present": True,
        "claim_signature": _as_str(claim.claim_signature),
        "text_matches_snapshot": live_text == frozen_text,
    }


def _snapshot_passage(
    link: dict[str, Any], evidence: dict[str, Any]
) -> dict[str, Any]:
    """One historical claim passage, mirroring the live passage read model."""
    passage: dict[str, Any] = {
        "id": _as_str(evidence.get("id")),
        "evidence_id": _as_str(evidence.get("id")),
        "title": _as_str(evidence.get("title")),
        "publisher": _as_str(evidence.get("publisher")),
        "origin_url": _as_str(evidence.get("originUrl")),
        "canonical_url": _as_str(evidence.get("canonicalUrl")),
        "source_type": _as_str(evidence.get("sourceType")),
        "confidence_score": link.get("confidenceScore"),
        "source_diversity_rank": _as_int(link.get("sourceDiversityRank")),
    }
    passage.update(snapshot_link_read_model(link))
    return passage


def _read_claim_detail_from_snapshot(
    session: Session, *, case_id: str, claim_id: str, snapshot_id: str
) -> dict[str, Any] | None:
    """Resolve one claim from a pinned snapshot payload, never from live rows.

    Returns ``None`` when the resolved snapshot does not contain the claim (404
    for that entity) and raises :class:`SnapshotNotFound` when the selector itself
    does not resolve for this case. Every entity attribute comes from the frozen
    payload; the only live read is the explicit ``live_state`` comparison.
    """
    snapshot = get_case_snapshot(session, case_id=case_id, snapshot_id=snapshot_id)
    if snapshot is None:
        raise SnapshotNotFound(
            f"Snapshot {snapshot_id} not found for case {case_id}"
        )
    payload = snapshot_payload(snapshot)
    claim = snapshot_entities(payload, "claims").get(claim_id)
    if claim is None:
        return None

    evidence_by_id = snapshot_entities(payload, "evidence")
    passages: list[dict[str, Any]] = []
    claim_links: list[dict[str, Any]] = []
    for link in snapshot_entity_list(payload, "links"):
        if _as_str(link.get("claimId")) != claim_id:
            continue
        claim_links.append(link)
        evidence = evidence_by_id.get(_as_str(link.get("evidenceId")) or "")
        if evidence is None:
            # A link whose evidence is not part of this observation has no
            # historical source metadata to show; it is not replaced by a live row.
            continue
        passages.append(_snapshot_passage(link, evidence))

    frozen_text = _as_str(claim.get("text")) or ""
    return {
        "id": _as_str(claim.get("id")),
        "case_id": case_id,
        "event_id": _as_str(claim.get("eventId")),
        "claim_text": frozen_text,
        "claim_signature": _as_str(claim.get("claimSignature")),
        "verification_status": _as_str(claim.get("verificationStatus")),
        "verification_provenance": _snapshot_verification_provenance(claim_links),
        "fact_allegation_type": _as_str(claim.get("factAllegationType")),
        "narrative_cluster_id": _as_str(claim.get("narrativeClusterId")),
        "controversy_score": claim.get("controversyScore"),
        "party_positions": _metadata(claim.get("partyPositions")),
        "counts": {
            "support_count": _as_int(claim.get("supportCount")) or 0,
            "oppose_count": _as_int(claim.get("opposeCount")) or 0,
            "source_diversity_count": _as_int(claim.get("sourceDiversityCount")) or 0,
            "evidence_count": len(passages),
        },
        "passages": passages,
        "snapshot_id": snapshot_id,
        "live_state": _claim_live_state(
            session, case_id=case_id, claim_id=claim_id, frozen_text=frozen_text
        ),
    }


def read_evidence_detail(
    session: Session,
    *,
    case_id: str,
    evidence_id: str,
    snapshot_id: str | None = None,
) -> dict[str, Any] | None:
    """Read one evidence item owned by ``case_id``, its captures and its claims.

    Capture **bodies** are deliberately absent: only IDs, hashes, kinds, times,
    frozen metadata and code-point lengths are returned. Source text is reachable
    only through :func:`read_capture_window`.

    With ``snapshot_id`` the item, its capture **references** and its related
    claims are resolved from that snapshot's frozen payload; a capture body is
    read only from the immutable capture row named by the snapshot and only when
    its recorded hash matches. Live behavior is unchanged without a selector.
    """
    if snapshot_id is not None:
        return _read_evidence_detail_from_snapshot(
            session,
            case_id=case_id,
            evidence_id=evidence_id,
            snapshot_id=snapshot_id,
        )

    evidence = session.get(EvidenceItem, evidence_id)
    if evidence is None or not _belongs_to_case(evidence, case_id):
        return None

    current_capture_id = _as_str(evidence.current_capture_id)
    captures = _captures_for_evidence(session, evidence)

    links = list(
        session.scalars(
            select(ClaimEvidenceLink)
            .where(ClaimEvidenceLink.evidence_id == evidence.id)
            .order_by(
                ClaimEvidenceLink.created_at.asc(), ClaimEvidenceLink.id.asc()
            )
        ).all()
    )
    claim_ids = [
        claim_id
        for claim_id in (_as_str(link.claim_id) for link in links)
        if claim_id is not None
    ]
    claims_by_id: dict[str, Claim] = {}
    if claim_ids:
        rows = session.scalars(
            select(Claim)
            .join(Event, Claim.event_id == Event.id)
            .where(Claim.id.in_(claim_ids), Event.case_id == case_id)
        ).all()
        claims_by_id = {cast(str, row.id): row for row in rows}

    related_claims: list[dict[str, Any]] = []
    for link in links:
        claim = claims_by_id.get(_as_str(link.claim_id) or "")
        if claim is None:
            continue
        reference = link_read_model(link)
        related_claims.append(
            {
                "claim_id": _as_str(claim.id),
                "claim_text": _as_str(claim.claim_text) or "",
                "claim_signature": _as_str(claim.claim_signature),
                "link_id": _as_str(link.id),
                "effective_relation": reference["effective_relation"],
                "relation": reference["relation"],
                "alignment_status": reference["alignment_status"],
                "citation_id": reference["citation_id"],
                "capture_id": reference["capture_id"],
                "quote": reference["quote"],
                "start_char": reference["start_char"],
                "end_char": reference["end_char"],
                "diagnostic_reason": reference["diagnostic_reason"],
            }
        )

    payload = _evidence_source_model(evidence)
    payload["current_capture_id"] = current_capture_id
    payload["captures"] = [
        _capture_summary_model(capture, current_capture_id=current_capture_id)
        for capture in captures
    ]
    payload["related_claims"] = related_claims
    return payload


def read_immutable_capture_text(
    session: Session,
    *,
    capture_id: str,
    evidence_id: str,
    recorded_text_sha256: str | None,
) -> str | None:
    """Return the immutable capture body a snapshot points at, or ``None``.

    The snapshot records a capture reference (ID + hash), never the body. The
    body is read from the append-only capture row **only** when that row belongs
    to the same evidence, the snapshot recorded a hash for it, and the stored hash
    still equals that recorded hash. Anything else is explicitly unavailable
    instead of being filled in from another version: a missing recorded hash fails
    closed, because the body could not then be tied to this observation.
    """
    capture = session.get(EvidenceCapture, capture_id)
    if capture is None or _as_str(capture.evidence_id) != evidence_id:
        return None
    recorded = _as_str(recorded_text_sha256)
    if recorded is None or _as_str(capture.text_sha256) != recorded:
        return None
    return cast(str, capture.text)


def _snapshot_capture_summary(
    capture: dict[str, Any],
    *,
    char_length: int,
    current_capture_id: str | None,
) -> dict[str, Any]:
    """One snapshot capture reference plus its immutable body length."""
    capture_id = _as_str(capture.get("id"))
    return {
        "id": capture_id,
        "evidence_id": _as_str(capture.get("evidenceId")),
        "text_sha256": _as_str(capture.get("textSha256")),
        "normalized_text_sha256": _as_str(
            capture.get("normalizedTextSha256")
        ),
        "normalization_version": _as_str(capture.get("normalizationVersion")),
        "capture_kind": _as_str(capture.get("captureKind")),
        "recorded_at": _as_str(capture.get("recordedAt")),
        "observed_at": _as_str(capture.get("observedAt")),
        "metadata": _metadata(capture.get("metadata")),
        "char_length": char_length,
        "is_current": bool(capture_id) and capture_id == current_capture_id,
    }


def _evidence_live_state(
    session: Session,
    *,
    case_id: str,
    evidence_id: str,
    snapshot_current_capture_id: str | None,
) -> dict[str, Any]:
    """Report whether the live evidence row still exists and how it advanced."""
    evidence = session.get(EvidenceItem, evidence_id)
    if evidence is None or not _belongs_to_case(evidence, case_id):
        return {
            "present": False,
            "current_capture_id": None,
            "current_capture_matches_snapshot": None,
        }
    live_current_capture_id = _as_str(evidence.current_capture_id)
    return {
        "present": True,
        "current_capture_id": live_current_capture_id,
        "current_capture_matches_snapshot": (
            None
            if snapshot_current_capture_id is None
            else live_current_capture_id == snapshot_current_capture_id
        ),
    }


def _read_evidence_detail_from_snapshot(
    session: Session, *, case_id: str, evidence_id: str, snapshot_id: str
) -> dict[str, Any] | None:
    """Resolve one evidence item from a pinned snapshot payload.

    ``None`` means the evidence is not part of that observation (404); an
    unresolvable selector raises :class:`SnapshotNotFound`. Capture bodies stay in
    the immutable captures: a capture reference whose body/hash cannot be
    verified is listed in ``unavailable_capture_ids`` rather than substituted.
    """
    snapshot = get_case_snapshot(session, case_id=case_id, snapshot_id=snapshot_id)
    if snapshot is None:
        raise SnapshotNotFound(
            f"Snapshot {snapshot_id} not found for case {case_id}"
        )
    payload = snapshot_payload(snapshot)
    evidence = snapshot_entities(payload, "evidence").get(evidence_id)
    if evidence is None:
        return None

    current_capture_id = _as_str(evidence.get("currentCaptureId"))
    captures: list[dict[str, Any]] = []
    unavailable_capture_ids: list[str] = []
    for capture in snapshot_entity_list(payload, "captures"):
        if _as_str(capture.get("evidenceId")) != evidence_id:
            continue
        capture_id = _as_str(capture.get("id"))
        if capture_id is None:
            continue
        body = read_immutable_capture_text(
            session,
            capture_id=capture_id,
            evidence_id=evidence_id,
            recorded_text_sha256=_as_str(capture.get("textSha256")),
        )
        if body is None:
            unavailable_capture_ids.append(capture_id)
            continue
        captures.append(
            _snapshot_capture_summary(
                capture,
                char_length=len(body),
                current_capture_id=current_capture_id,
            )
        )

    claims_by_id = snapshot_entities(payload, "claims")
    related_claims: list[dict[str, Any]] = []
    for link in snapshot_entity_list(payload, "links"):
        if _as_str(link.get("evidenceId")) != evidence_id:
            continue
        claim = claims_by_id.get(_as_str(link.get("claimId")) or "")
        if claim is None:
            # A link to a claim outside this observation is not shown with a
            # current claim row substituted for it.
            continue
        reference = snapshot_link_read_model(link)
        related_claims.append(
            {
                "claim_id": _as_str(claim.get("id")),
                "claim_text": _as_str(claim.get("text")) or "",
                "claim_signature": _as_str(claim.get("claimSignature")),
                "link_id": _as_str(link.get("id")),
                "effective_relation": reference["effective_relation"],
                "relation": reference["relation"],
                "alignment_status": reference["alignment_status"],
                "citation_id": reference["citation_id"],
                "capture_id": reference["capture_id"],
                "quote": reference["quote"],
                "start_char": reference["start_char"],
                "end_char": reference["end_char"],
                "diagnostic_reason": reference["diagnostic_reason"],
            }
        )

    result: dict[str, Any] = {
        "id": _as_str(evidence.get("id")),
        "event_id": _as_str(evidence.get("eventId")),
        "case_article_id": _as_str(evidence.get("caseArticleId")),
        "evidence_type": _as_str(evidence.get("evidenceType")),
        "source_type": _as_str(evidence.get("sourceType")),
        "title": _as_str(evidence.get("title")),
        "origin_url": _as_str(evidence.get("originUrl")),
        "canonical_url": _as_str(evidence.get("canonicalUrl")),
        "publisher": _as_str(evidence.get("publisher")),
        "published_at": _as_str(evidence.get("publishedAt")),
        "verification_status": _as_str(evidence.get("verificationStatus")),
        "credibility_tier": _as_str(evidence.get("credibilityTier")),
        "requires_human_review": bool(evidence.get("requiresHumanReview")),
        "capture_metadata": _metadata(evidence.get("captureMetadata")),
        "current_capture_id": current_capture_id,
        "captures": captures,
        "related_claims": related_claims,
        "snapshot_id": snapshot_id,
        "unavailable_capture_ids": unavailable_capture_ids,
        "live_state": _evidence_live_state(
            session,
            case_id=case_id,
            evidence_id=evidence_id,
            snapshot_current_capture_id=current_capture_id,
        ),
    }
    return result


def read_capture_window(
    session: Session,
    *,
    case_id: str,
    evidence_id: str,
    capture_id: str,
    start: int,
    length: int,
) -> dict[str, Any] | None:
    """Return one bounded code-point window of an immutable capture.

    Ownership: the evidence must belong to ``case_id`` **and** the capture must
    belong to that evidence. Anything else is ``None`` (404).

    Semantics (specification §9): ``start`` is a zero-based code-point index and
    must be inside ``[0, total_length]``; ``length`` is in ``[1, 50000]`` code
    points. The window is ``text[start:start + length]`` -- Python code points,
    the same reference the quotation validator uses. It is truncated only by end
    of text, and the returned ``length``/``total_length`` state both numbers so a
    partial window is never mistaken for the whole capture. ``start ==
    total_length`` is valid and yields empty text.

    Malformed ranges raise :class:`CaptureRangeError` (422); they are never
    silently clamped.
    """
    if isinstance(start, bool) or not isinstance(start, int):
        raise CaptureRangeError("start must be an integer code-point offset")
    if isinstance(length, bool) or not isinstance(length, int):
        raise CaptureRangeError("length must be an integer code-point count")
    if start < 0:
        raise CaptureRangeError("start must be >= 0")
    if length < 1 or length > MAX_CAPTURE_WINDOW_LENGTH:
        raise CaptureRangeError(
            f"length must be between 1 and {MAX_CAPTURE_WINDOW_LENGTH} code points"
        )

    evidence = session.get(EvidenceItem, evidence_id)
    if evidence is None or not _belongs_to_case(evidence, case_id):
        return None
    capture = session.get(EvidenceCapture, capture_id)
    if capture is None or _as_str(capture.evidence_id) != _as_str(evidence.id):
        return None

    body = cast(str, capture.text)
    total_length = len(body)
    if start > total_length:
        raise CaptureRangeError(
            f"start {start} is beyond the capture length {total_length}"
        )
    window = body[start : start + length]
    return {
        "capture_id": _as_str(capture.id),
        "evidence_id": _as_str(evidence.id),
        "start": start,
        "length": len(window),
        "total_length": total_length,
        "text": window,
        "text_sha256": _as_str(capture.text_sha256),
        "capture_kind": _as_str(capture.capture_kind),
        "recorded_at": _iso(capture.recorded_at),
        "observed_at": _iso(capture.observed_at),
        "metadata": _metadata(capture.metadata_json),
    }


__all__ = [
    "CaptureRangeError",
    "DEFAULT_CAPTURE_WINDOW_LENGTH",
    "MAX_CAPTURE_WINDOW_LENGTH",
    "SnapshotNotFound",
    "link_read_model",
    "read_capture_window",
    "read_citation",
    "read_claim_detail",
    "read_evidence_detail",
    "read_immutable_capture_text",
    "snapshot_link_read_model",
]
