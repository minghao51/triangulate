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


def link_read_model(link: ClaimEvidenceLink) -> dict[str, Any]:
    """Return the honest read model of one claim/evidence link.

    ``relation`` is the raw stored value kept for diagnostics (a legacy
    ``opposes``/``supports`` is never rewritten). ``effective_relation`` is the
    policy-resolved value, using exactly the same inputs as the aggregate
    recomputation in the case service, so a reader can never claim more support
    than the writer counted.
    """
    relation = _as_str(link.relation)
    alignment_status = _as_str(link.alignment_status) or DEFAULT_ALIGNMENT_STATUS
    assessment_origin = _as_str(link.assessment_origin)
    assessment_version = _as_str(link.assessment_version)
    resolution = resolve_effective_relationship(
        stored_relation=relation,
        alignment_status=alignment_status,
        assessment_origin=assessment_origin,
        assessment_version=assessment_version,
        exact_anchor=(alignment_status == AlignmentStatus.EXACT.value),
        collector_generated=(assessment_origin == COLLECTOR_ORIGIN),
    )
    diagnostic_reason = _as_str(
        _metadata(link.assessment_metadata).get("diagnostic_reason")
    )
    return {
        "relation": relation,
        "effective_relation": resolution.effective_relationship,
        "alignment_status": alignment_status,
        "quote": _as_str(link.quote),
        "start_char": _as_int(link.start_char),
        "end_char": _as_int(link.end_char),
        "capture_id": _as_str(link.capture_id),
        "citation_id": _as_str(link.citation_id),
        "assessment_origin": assessment_origin,
        "assessment_version": assessment_version,
        "diagnostic_reason": diagnostic_reason,
    }


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
    session: Session, *, case_id: str, claim_id: str
) -> dict[str, Any] | None:
    """Read one claim owned by ``case_id`` plus its evidence-linked passages.

    The claim is joined through ``Event.case_id``; a claim of another case is
    indistinguishable from an unknown claim (``None``). Counts are the stored
    policy-derived aggregates -- the reader never recomputes or inflates them.
    """
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
        metadata = _metadata(link.assessment_metadata)
        is_legacy_shaped = (
            _as_str(link.citation_id) is None
            and _as_str(link.capture_id) is None
            and (
                _as_str(link.alignment_status) is None
                or _as_str(link.alignment_status) == DEFAULT_ALIGNMENT_STATUS
            )
            and _as_str(link.assessment_origin) is None
            and _as_str(link.assessment_version) is None
            and "relationship_policy" not in metadata
        )
        if not is_legacy_shaped:
            return "unknown"
    return "legacy_unknown"


def read_evidence_detail(
    session: Session, *, case_id: str, evidence_id: str
) -> dict[str, Any] | None:
    """Read one evidence item owned by ``case_id``, its captures and its claims.

    Capture **bodies** are deliberately absent: only IDs, hashes, kinds, times,
    frozen metadata and code-point lengths are returned. Source text is reachable
    only through :func:`read_capture_window`.
    """
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
    "link_read_model",
    "read_capture_window",
    "read_citation",
    "read_claim_detail",
    "read_evidence_detail",
]
