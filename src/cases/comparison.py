"""Deterministic two-capture comparison read model (P02).

Contract: evidence-workbench specification §6. The comparison is a local,
read-only projection:

* both evidence IDs and both selected capture IDs must belong to the requested
  case and evidence; an explicit invalid ID is never replaced by a guessed one;
* claims are paired only by the existing exact ``claim_signature`` policy;
* claim rows and passages come only from persisted links that name the selected
  capture. Current links are never substituted for an older capture;
* dependency/copy warnings reuse the P01 source policy (`source-dependency-policy-v1`);
* no model, network or source-capture call is made and nothing is written.

Rows expose left-only/right-only status as extraction coverage, not as proof that
the other source omitted, lied or disagreed.
"""

from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.cases._support import _claim_signature
from src.cases.provenance import (
    REASON_IDENTICAL_CAPTURE_TEXT,
    SourceMember,
    build_source_summary,
    read_source_member,
)
from src.cases.readers import link_read_model
from src.storage import (
    Claim,
    ClaimEvidenceLink,
    EvidenceCapture,
    EvidenceItem,
    Event,
    TopicCase,
)

COMPARISON_POLICY_VERSION = "comparison-read-policy-v1"
DEFAULT_COMPARISON_LIMIT = 25
MAX_COMPARISON_LIMIT = 100


class ComparisonNotFound(LookupError):
    """A case/evidence/capture is unknown or belongs to another case (404)."""


class ComparisonInvalid(ValueError):
    """The comparison request is malformed even for existing resources (422)."""


def _iso(value: Any) -> str | None:
    rendered = getattr(value, "isoformat", None)
    if not callable(rendered):
        return None
    result = rendered()
    return result if isinstance(result, str) else None


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _extraction_metadata(
    capture: EvidenceCapture, evidence: EvidenceItem
) -> Any:
    """Read frozen extraction scope from the capture, falling back to evidence."""
    capture_metadata = (
        capture.metadata_json if isinstance(capture.metadata_json, dict) else {}
    )
    evidence_metadata = (
        evidence.capture_metadata
        if isinstance(evidence.capture_metadata, dict)
        else {}
    )
    return capture_metadata.get("extraction") or evidence_metadata.get("extraction")


def _analysis_scope(value: Any) -> dict[str, Any] | None:
    """Expose the collector's recorded analysis-input scope, when present."""
    if not isinstance(value, dict):
        return None
    return {
        "status": _as_str(value.get("status")),
        "start_char": _as_int(value.get("scope_start")),
        "end_char": _as_int(value.get("scope_end")),
        "body_char_count": _as_int(value.get("body_char_count")),
        "input_limit": _as_int(value.get("input_limit")),
        "source_available": (
            value.get("source_available")
            if isinstance(value.get("source_available"), bool)
            else None
        ),
        "reason": _as_str(value.get("reason")),
    }


def _owned_evidence(
    session: Session, *, case_id: str, evidence_id: str
) -> EvidenceItem:
    evidence = session.get(EvidenceItem, evidence_id)
    if evidence is None or _as_str(evidence.case_id) != case_id:
        raise ComparisonNotFound(f"Evidence {evidence_id} not found for case {case_id}")
    return evidence


def _selected_capture(
    session: Session,
    *,
    evidence: EvidenceItem,
    requested_capture_id: str | None,
) -> EvidenceCapture:
    evidence_id = _as_str(evidence.id)
    capture_id = requested_capture_id
    if capture_id is None:
        capture_id = _as_str(evidence.current_capture_id)
    if capture_id is None:
        raise ComparisonNotFound(
            f"Evidence {evidence_id} has no immutable capture to compare"
        )
    capture = session.get(EvidenceCapture, capture_id)
    if capture is None or _as_str(capture.evidence_id) != evidence_id:
        raise ComparisonNotFound(
            f"Capture {capture_id} not found for evidence {evidence_id} in this case"
        )
    return capture


def _claim_signature_for(claim: Claim) -> str:
    stored = _as_str(claim.claim_signature)
    if stored:
        return stored
    return _claim_signature(_as_str(claim.claim_text) or "")


def _case_claims(
    session: Session, *, case_id: str, claim_ids: list[str]
) -> dict[str, Claim]:
    if not claim_ids:
        return {}
    rows = session.scalars(
        select(Claim)
        .join(Event, Claim.event_id == Event.id)
        .where(Claim.id.in_(sorted(set(claim_ids))), Event.case_id == case_id)
        .order_by(Claim.id.asc())
    ).all()
    return {_as_str(claim.id) or "": claim for claim in rows}


def _passage_model(link: ClaimEvidenceLink, claim: Claim) -> dict[str, Any]:
    reference = link_read_model(link)
    return {
        "claim_id": _as_str(claim.id),
        "claim_text": _as_str(claim.claim_text) or "",
        "claim_signature": _claim_signature_for(claim),
        "link_id": _as_str(link.id),
        "citation_id": reference["citation_id"],
        "capture_id": reference["capture_id"],
        "relationship": reference["effective_relation"],
        "raw_relation": reference["relation"],
        "alignment_status": reference["alignment_status"],
        "quote": reference["quote"],
        "start_char": reference["start_char"],
        "end_char": reference["end_char"],
        "assessment_origin": reference["assessment_origin"],
        "assessment_version": reference["assessment_version"],
        "diagnostic_reason": reference["diagnostic_reason"],
    }


def _coverage(
    *,
    attributed_links: list[ClaimEvidenceLink],
    other_capture_links: int,
    unattributed_links: int,
    linked_claim_count: int,
    attributed_claim_count: int,
) -> dict[str, Any]:
    if attributed_claim_count > 0:
        status = "available"
        caveat = (
            "Some recorded links belong to other capture versions or predate "
            "captures and are excluded from this pinned comparison."
            if other_capture_links or unattributed_links
            else None
        )
    elif other_capture_links > 0:
        status = "historical_unavailable"
        caveat = (
            "No persisted claim links for this capture version; historical "
            "comparison analysis is unavailable. Current links are not substituted."
        )
    elif unattributed_links > 0:
        status = "unattributed_legacy"
        caveat = (
            "Only legacy links without a capture version are recorded; they cannot "
            "be attributed to this capture."
        )
    else:
        status = "empty"
        caveat = "No claims are linked to this capture."
    return {
        "linked_claim_count": linked_claim_count,
        "attributed_claim_count": attributed_claim_count,
        "attributed_link_count": len(attributed_links),
        "other_capture_link_count": other_capture_links,
        "unattributed_link_count": unattributed_links,
        "claim_linkage_status": status,
        "historical_analysis_available": (
            attributed_claim_count > 0
            or (other_capture_links == 0 and unattributed_links == 0)
        ),
        "caveat": caveat,
    }


def _side(
    session: Session,
    *,
    case_id: str,
    evidence: EvidenceItem,
    capture: EvidenceCapture,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build one comparison side plus its exact-signature claim map."""
    evidence_id = _as_str(evidence.id) or ""
    capture_id = _as_str(capture.id) or ""
    links = list(
        session.scalars(
            select(ClaimEvidenceLink)
            .where(ClaimEvidenceLink.evidence_id == evidence_id)
            .order_by(
                ClaimEvidenceLink.created_at.asc(), ClaimEvidenceLink.id.asc()
            )
        ).all()
    )
    claims = _case_claims(
        session,
        case_id=case_id,
        claim_ids=[
            claim_id
            for claim_id in (_as_str(link.claim_id) for link in links)
            if claim_id is not None
        ],
    )
    owned_links = [
        link for link in links if (_as_str(link.claim_id) or "") in claims
    ]
    attributed_links = [
        link
        for link in owned_links
        if _as_str(link.capture_id) == capture_id
    ]
    other_capture_links = sum(
        1
        for link in owned_links
        if _as_str(link.capture_id) not in (None, capture_id)
    )
    unattributed_links = sum(
        1 for link in owned_links if _as_str(link.capture_id) is None
    )

    claim_groups: dict[str, list[tuple[Claim, ClaimEvidenceLink]]] = {}
    for link in attributed_links:
        claim = claims[_as_str(link.claim_id) or ""]
        claim_groups.setdefault(_claim_signature_for(claim), []).append((claim, link))

    claim_map: dict[str, dict[str, Any]] = {}
    for signature, entries in claim_groups.items():
        entries.sort(key=lambda item: (_as_str(item[0].id) or "", _as_str(item[1].id) or ""))
        representative = entries[0][0]
        passages = [
            _passage_model(link, claim) for claim, link in entries
        ]
        passages.sort(
            key=lambda item: (
                item["citation_id"] or "",
                item["link_id"] or "",
            )
        )
        claim_map[signature] = {
            "claim_ids": sorted(
                {
                    _as_str(claim.id) or ""
                    for claim, _ in entries
                }
            ),
            "claim_id": _as_str(representative.id),
            "claim_text": _as_str(representative.claim_text) or "",
            "claim_signature": signature,
            "passages": passages,
        }

    member = read_source_member(
        session,
        case_id=case_id,
        evidence_id=evidence_id,
        capture_id=capture_id,
    )
    side = {
        "evidence_id": evidence_id,
        "capture_id": capture_id,
        "title": _as_str(evidence.title),
        "publisher": _as_str(evidence.publisher),
        "origin_url": _as_str(evidence.origin_url),
        "canonical_url": _as_str(evidence.canonical_url),
        "published_at": _as_str(evidence.published_at),
        "source_type": _as_str(evidence.source_type),
        "verification_status": _as_str(evidence.verification_status),
        "capture_kind": _as_str(capture.capture_kind),
        "recorded_at": _iso(capture.recorded_at),
        "observed_at": _iso(capture.observed_at),
        "text_sha256": _as_str(capture.text_sha256),
        "char_length": len(capture.text),
        "analysis_scope": _analysis_scope(
            _extraction_metadata(capture, evidence)
        ),
        "publisher_key": member.publisher_key if member else None,
        "publisher_key_provisional": (
            member.publisher_key_provisional if member else False
        ),
        "host": member.host if member else None,
        "source_url": member.source_url if member else None,
        "copy_fingerprint": member.copy_fingerprint if member else None,
        "copy_non_whitespace_count": (
            member.copy_non_whitespace_count if member else 0
        ),
        "coverage": _coverage(
            attributed_links=attributed_links,
            other_capture_links=other_capture_links,
            unattributed_links=unattributed_links,
            linked_claim_count=len(claims),
            attributed_claim_count=len(
                {
                    _as_str(link.claim_id)
                    for link in attributed_links
                    if _as_str(link.claim_id) is not None
                }
            ),
        ),
    }
    return side, claim_map


def _contradiction(
    left: dict[str, Any] | None, right: dict[str, Any] | None
) -> dict[str, Any]:
    """Report only explicitly assessed contradiction, never textual difference."""
    left_relations = (
        sorted({passage["relationship"] for passage in left["passages"]})
        if left
        else []
    )
    right_relations = (
        sorted({passage["relationship"] for passage in right["passages"]})
        if right
        else []
    )
    left_contradicts = "contradicts" in left_relations
    right_contradicts = "contradicts" in right_relations
    explicit = left_contradicts or right_contradicts
    conflict = False
    reason = "No explicitly assessed contradiction."
    if left and right and left_contradicts != right_contradicts:
        non_contradicting = right_relations if left_contradicts else left_relations
        if any(
            relation in {"supports", "reported_by"}
            for relation in non_contradicting
        ):
            conflict = True
            reason = (
                "One side explicitly contradicts the claim while the other reports "
                "or explicitly supports it."
            )
        else:
            reason = (
                "An explicit contradiction assessment exists on one side, but the "
                "other side has no opposing assessed relationship."
            )
    elif explicit:
        reason = "Explicit contradiction assessment present; no opposing assessed relationship."
    return {
        "explicit": explicit,
        "conflict": conflict,
        "left_relationships": left_relations,
        "right_relationships": right_relations,
        "reason": reason,
    }


def _dependency(
    left_member: SourceMember | None,
    right_member: SourceMember | None,
    *,
    case_id: str,
) -> dict[str, Any]:
    if left_member is None or right_member is None:
        return {
            "detected": False,
            "copy_detected": False,
            "reasons": [],
            "left_publisher_key": None,
            "right_publisher_key": None,
            "message": "Dependency could not be evaluated for both records.",
        }
    summary = build_source_summary(
        case_id=case_id,
        scope="case",
        claim_id=None,
        claim_signature=None,
        members=[left_member, right_member],
    )
    group = next(
        (
            item
            for item in summary["groups"]
            if item["evidence_count"] == 2
        ),
        None,
    )
    reasons = list(group["reasons"]) if group else []
    detected = group is not None
    copy_detected = REASON_IDENTICAL_CAPTURE_TEXT in reasons
    if detected:
        message = (
            "These records share a detected dependency ("
            + ", ".join(reasons)
            + "). They are not independent evidence."
        )
    else:
        message = (
            "No dependency was detected between these records; this does not "
            "prove that they are independent."
        )
    return {
        "detected": detected,
        "copy_detected": copy_detected,
        "reasons": reasons,
        "left_publisher_key": left_member.publisher_key,
        "right_publisher_key": right_member.publisher_key,
        "message": message,
    }


def read_comparison(
    session: Session,
    *,
    case_id: str,
    left_evidence_id: str,
    right_evidence_id: str,
    left_capture_id: str | None = None,
    right_capture_id: str | None = None,
    limit: int = DEFAULT_COMPARISON_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """Read one deterministic two-capture comparison for an owned case.

    Raises :class:`ComparisonNotFound` for unknown/foreign case, evidence or
    capture resources (404) and :class:`ComparisonInvalid` for a same-evidence
    or otherwise malformed selector (422).
    """
    if left_evidence_id == right_evidence_id:
        raise ComparisonInvalid(
            "Comparison requires two different evidence IDs; the same record "
            "cannot be compared with itself"
        )
    if left_capture_id is not None and left_capture_id == "":
        raise ComparisonInvalid("leftCapture must not be empty")
    if right_capture_id is not None and right_capture_id == "":
        raise ComparisonInvalid("rightCapture must not be empty")
    if limit < 1 or limit > MAX_COMPARISON_LIMIT:
        raise ComparisonInvalid(
            f"limit must be between 1 and {MAX_COMPARISON_LIMIT}"
        )
    if offset < 0:
        raise ComparisonInvalid("offset must be >= 0")

    case = session.get(TopicCase, case_id)
    if case is None:
        raise ComparisonNotFound(f"Case {case_id} not found")

    left_evidence = _owned_evidence(
        session, case_id=case_id, evidence_id=left_evidence_id
    )
    right_evidence = _owned_evidence(
        session, case_id=case_id, evidence_id=right_evidence_id
    )
    left_capture = _selected_capture(
        session,
        evidence=left_evidence,
        requested_capture_id=left_capture_id,
    )
    right_capture = _selected_capture(
        session,
        evidence=right_evidence,
        requested_capture_id=right_capture_id,
    )

    left_side, left_claims = _side(
        session, case_id=case_id, evidence=left_evidence, capture=left_capture
    )
    right_side, right_claims = _side(
        session, case_id=case_id, evidence=right_evidence, capture=right_capture
    )
    left_member = read_source_member(
        session,
        case_id=case_id,
        evidence_id=left_evidence_id,
        capture_id=_as_str(left_capture.id),
    )
    right_member = read_source_member(
        session,
        case_id=case_id,
        evidence_id=right_evidence_id,
        capture_id=_as_str(right_capture.id),
    )

    rows: list[dict[str, Any]] = []
    for signature in sorted(set(left_claims) | set(right_claims)):
        left = left_claims.get(signature)
        right = right_claims.get(signature)
        if left is not None and right is not None:
            status = "shared"
        elif left is not None:
            status = "left_only"
        else:
            status = "right_only"
        claim_text = (
            (left or {}).get("claim_text")
            or (right or {}).get("claim_text")
            or ""
        )
        rows.append(
            {
                "claim_signature": signature,
                "claim_text": claim_text,
                "status": status,
                "left": left,
                "right": right,
                "contradiction": _contradiction(left, right),
                "caveat": (
                    "This assertion was extracted from the selected capture on "
                    "one side only; that is not evidence that the other source "
                    "omitted, lied or disagreed."
                    if status != "shared"
                    else None
                ),
            }
        )

    total = len(rows)
    page = rows[offset : offset + limit]
    dependency = _dependency(left_member, right_member, case_id=case_id)
    return {
        "case_id": case_id,
        "left": left_side,
        "right": right_side,
        "left_capture_id": _as_str(left_capture.id),
        "right_capture_id": _as_str(right_capture.id),
        "dependency": dependency,
        "claims": {
            "rows": page,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(page) < total,
        },
        "policy": {
            "version": COMPARISON_POLICY_VERSION,
            "claim_identity": (
                "exact claim_signature (SHA-256 of lowercased, stripped claim "
                "text); paraphrases are never merged"
            ),
            "alignment": (
                "persisted capture-linked assessments for the selected capture "
                "only; current links are never substituted for an older capture"
            ),
            "dependency_policy": "source-dependency-policy-v1",
            "limitations": [
                "Not extracted on one side does not mean the source omitted, lied or disagreed.",
                "Historical claim alignment is unavailable where no link persisted for the selected capture.",
                "Copy/dependency warnings are deterministic P01 edges, not proof of independence when absent.",
                "Near-duplicate and semantic paraphrase detection are not implemented.",
            ],
        },
        "caveats": [
            "Rows are paired only by exact claim_signature; paraphrases are not merged.",
            "One-sided rows describe extraction coverage, not source behavior.",
            "The recorded analysis scope is the body region actually supplied to the extractor; a truncated prefix is not the whole capture.",
            "No model, network or source-capture call is made by this read.",
        ],
    }


__all__ = [
    "COMPARISON_POLICY_VERSION",
    "DEFAULT_COMPARISON_LIMIT",
    "MAX_COMPARISON_LIMIT",
    "ComparisonInvalid",
    "ComparisonNotFound",
    "read_comparison",
]
