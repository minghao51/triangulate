"""E02 pass B3: writer wiring, effective relationships, aggregates, review hash.

Covers the contract in specification §4 "Quotation and relationship contract":

* per claim/evidence attachment the event writer resolves the relationship through
  the versioned policy (never a raw ``supports`` default), persists the capture
  pointer, the validated passage, alignment/assessment provenance and an immutable
  citation for an eligible exact passage;
* invalid/out-of-scope proposals stay diagnostics, ``reported_by``/``uncertain``
  are never corroboration and an explicit versioned assessment is required for
  ``supports``/``contradicts``;
* aggregates count eligible, deduplicated contributions only and never promote
  ``verification_status``;
* the e02 review hash pins quotation/alignment/assessment semantics and the cited
  capture body hash, while a version-only transition keeps an unchanged legacy
  approval (identically to B01) and a real change invalidates it.

All application databases are temporary; no provider/network/model calls occur.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import update

import pytest

from src.cases.service import TopicCaseService, _claim_signature
from src.storage import (
    CaseArticle,
    CaseStatus,
    Claim,
    ClaimCitation,
    ClaimEvidenceLink,
    EvidenceCapture,
    Review,
    ReviewStatus,
    TopicCase,
    VerificationStatus,
    init_database,
)
from src.storage.citations import (
    ALIGNMENT_VERSION,
    RELATIONSHIP_POLICY_VERSION,
    resolve_effective_relationship,
)
from src.storage.event_store import store_event_in_db
from src.storage.review_state import (
    ANALYSIS_HASH_VERSION,
    LEGACY_ANALYSIS_HASH_VERSION,
    canonical_analysis_payload,
    compute_event_analysis_hash,
    compute_legacy_event_analysis_hash,
)
from tests.fixtures.evidence_workbench import SOURCE_A

EVENT_TS = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)
REVIEW_TS = datetime(2026, 4, 1, 9, 30, tzinfo=UTC)
REVIEW_NOTES = "Reviewed and approved."

UNICODE_QUOTE = "the marker \U0001f6a8 and the agency name \u6e2f\u53e3\u7ba1\u7406\u5c40"
REPEATED_BODY = (
    "Repeated passage here. Some unrelated intervening text. "
    "Repeated passage here."
)
REPEATED_QUOTE = "Repeated passage here."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def db_session(tmp_path):
    db = init_database(str(tmp_path / "triangulate.db"))
    return db.get_session_sync()


def ensure_case(tmp_path, case_id: str = "case-1") -> None:
    session = db_session(tmp_path)
    try:
        if session.query(TopicCase).filter(TopicCase.id == case_id).first() is None:
            session.add(
                TopicCase(
                    id=case_id,
                    query="Writer wiring case",
                    slug=f"{case_id}-slug",
                    status=CaseStatus.INVESTIGATING,
                    metadata_json={},
                )
            )
            session.commit()
    finally:
        session.close()


def outcome_payload(
    scope_start: int,
    scope_end: int,
    *,
    trusted: bool = True,
    status: str = "valid",
) -> dict:
    return {
        "status": status,
        "quote_proposals_trusted": trusted,
        "scope_start": scope_start,
        "scope_end": scope_end,
        "body_char_count": scope_end - scope_start,
        "input_limit": 5000,
        "source_available": True,
        "reason": "",
    }


def evidence_payload(
    *,
    evidence_id: str = "evidence-1",
    content: str | None = "The bridge closed at noon. The bridge reopened at midnight.",
    title: str = "Bridge report",
    url: str = "https://example.com/source-1",
    publisher: str = "Outlet One",
    **extra,
) -> dict:
    payload = {
        "id": evidence_id,
        "evidence_type": "article",
        "source_type": "rss",
        "title": title,
        "origin_url": url,
        "canonical_url": url,
        "publisher": publisher,
        "published_at": "2026-03-08T00:00:00+00:00",
        "content": content,
        "capture_metadata": {},
        "verification_status": "UNVERIFIED",
        "credibility_tier": "unknown",
        "requires_human_review": False,
        "verification_checks": [],
    }
    payload.update(extra)
    return payload


def claim_payload(
    text: str,
    *,
    claim_id: str | None = None,
    evidence: list[dict] | None = None,
    verification_status: str = "ALLEGED",
    signature: str | None = None,
    source_quote: str | None = None,
    source_quote_start: int | None = None,
    source_quote_end: int | None = None,
) -> dict:
    payload = {
        "claim": text,
        "verification_status": verification_status,
        "claim_signature": signature or _claim_signature(text),
        "evidence": evidence or [],
        "support_count": 0,
        "oppose_count": 0,
        "source_diversity_count": 1,
    }
    if claim_id is not None:
        payload["id"] = claim_id
    if source_quote is not None:
        payload["source_quote"] = source_quote
        payload["source_quote_start"] = source_quote_start
        payload["source_quote_end"] = source_quote_end
    return payload


def build_event(
    event_id: str = "event-1",
    *,
    claims: list[dict] | None = None,
    evidence: list[dict] | None = None,
    outcome: dict | None = None,
    timestamp: datetime = EVENT_TS,
    narratives: list[dict] | None = None,
) -> dict:
    payload = {
        "id": event_id,
        "timestamp": timestamp,
        "title": "Bridge closure",
        "summary": "The bridge closed and later reopened.",
        "verification_status": "PROBABLE",
        "source_url": "https://example.com/source-1",
        "source_name": "Example",
        "claims": claims if claims is not None else [],
        "narratives": narratives if narratives is not None else [],
        "parties": [{"canonical_name": "Alpha", "aliases": ["Alpha"]}],
        "party_investigations": [],
        "evidence": evidence if evidence is not None else [],
    }
    if outcome is not None:
        payload["extraction_outcome"] = outcome
    return payload


@dataclass(frozen=True)
class ReviewSnapshot:
    """Typed plain-value view of one review row (see :func:`stored`)."""

    id: str
    status: Any
    reviewed_at: Any
    notes: Any
    analysis_hash: Any
    previous_decision_json: Any


def stored(row: Any, attribute: str) -> Any:
    """Return a stored value from a classic ``Column[...]`` ORM attribute.

    The storage models declare columns with ``Column[...]``, so a static reader
    sees a descriptor where the runtime value is stored. Tests assert on the
    stored value; narrowing at this single boundary keeps every assertion exact
    without suppressing or weakening the type checker.
    """
    return getattr(row, attribute)


def _review_snapshot(session, event_id: str) -> ReviewSnapshot | None:
    row = session.query(Review).filter(Review.event_id == event_id).first()
    if row is None:
        return None
    return ReviewSnapshot(
        id=cast(str, row.id),
        status=row.status,
        reviewed_at=row.reviewed_at,
        notes=row.notes,
        analysis_hash=row.analysis_hash,
        previous_decision_json=row.previous_decision_json,
    )


def approve(tmp_path, event_id: str, analysis_hash: str | None = None) -> None:
    session = db_session(tmp_path)
    try:
        # Core update: same semantics as ``bind_review_decision`` without
        # assigning to classic ``Column[...]`` descriptors (typing artefacts).
        values: dict[str, Any] = {
            "status": ReviewStatus.APPROVED,
            "reviewed_at": REVIEW_TS,
            "notes": REVIEW_NOTES,
        }
        if analysis_hash is not None:
            values["analysis_hash"] = analysis_hash
        else:
            values["analysis_hash"] = compute_event_analysis_hash(session, event_id)
            values["previous_decision_json"] = None
        session.execute(
            update(Review).where(Review.event_id == event_id).values(**values)
        )
        session.commit()
    finally:
        session.close()


def read_review(tmp_path, event_id: str) -> ReviewSnapshot:
    session = db_session(tmp_path)
    try:
        snapshot = _review_snapshot(session, event_id)
        assert snapshot is not None
        return snapshot
    finally:
        session.close()


def read_hash(tmp_path, event_id: str) -> str:
    session = db_session(tmp_path)
    try:
        return compute_event_analysis_hash(session, event_id)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 1. Validated exact collector quotation persists capture/citation/span
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "quote", "use_offsets"),
    [
        pytest.param(SOURCE_A.body, UNICODE_QUOTE, False, id="unicode-emoji-cjk"),
        pytest.param(
            REPEATED_BODY,
            REPEATED_QUOTE,
            True,
            id="repeated-text-explicit-offsets",
        ),
    ],
)
def test_validated_collector_quotation_persists_span_and_citation(
    tmp_path, body, quote, use_offsets
):
    assert body is not None
    assert quote in body
    ensure_case(tmp_path)
    quote_start = body.find(quote)
    if use_offsets:
        # Ambiguous without offsets: pick the second occurrence explicitly.
        quote_start = body.find(quote, quote_start + 1)
        assert quote_start > 0
    quote_end = quote_start + len(quote)

    claim_text = "The bridge closure was ordered at noon."
    event = build_event(
        claims=[
            claim_payload(
                claim_text,
                evidence=[evidence_payload(content=body)],
                source_quote=quote,
                source_quote_start=quote_start if use_offsets else None,
                source_quote_end=quote_end if use_offsets else None,
            )
        ],
        evidence=[evidence_payload(content=body)],
        outcome=outcome_payload(0, len(body)),
    )
    assert store_event_in_db(event, case_id="case-1", create_review=False) is True

    session = db_session(tmp_path)
    try:
        claim = session.query(Claim).one()
        link = session.query(ClaimEvidenceLink).one()
        capture = session.query(EvidenceCapture).one()
        citation = session.query(ClaimCitation).one()

        assert stored(link, "capture_id") == capture.id
        assert stored(link, "citation_id") == citation.id
        assert stored(link, "quote") == quote
        assert stored(link, "start_char") == quote_start
        assert stored(link, "end_char") == quote_end
        assert stored(link, "alignment_status") == "exact"
        assert stored(link, "relation") == "reported_by"
        assert stored(link, "assessment_origin") == "collector"
        assert stored(link, "assessment_version") is None
        assert stored(link, "assessment_metadata") == {
            "alignment_version": ALIGNMENT_VERSION,
            "relationship_policy": RELATIONSHIP_POLICY_VERSION,
            "stored_relation": None,
        }

        # The immutable citation freezes the claim text/signature as they were.
        assert stored(citation, "text") == claim_text
        assert stored(citation, "claim_signature") == _claim_signature(claim_text)
        assert stored(citation, "original_claim_id") == claim.id
        assert stored(citation, "capture_id") == capture.id
        assert stored(citation, "quote") == quote
        assert stored(citation, "start_char") == quote_start
        assert stored(citation, "end_char") == quote_end
        assert stored(citation, "alignment_status") == "exact"
        assert stored(citation, "alignment_version") == ALIGNMENT_VERSION
        assert stored(citation, "relationship") == "reported_by"
        assert stored(citation, "assessment_origin") == "collector"
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 2. A fabricated/out-of-scope quotation is a diagnostic, never support
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "quote", "scope_end"),
    [
        pytest.param(
            "The bridge closed at noon.",
            "A fabricated passage that never appears",
            26,
            id="fabricated",
        ),
        pytest.param(
            "Short scope only. A hidden passage outside the analysed scope.",
            "A hidden passage outside the analysed scope",
            16,
            id="out-of-scope",
        ),
    ],
)
def test_invalid_quotation_persists_diagnostic_and_no_citation(
    tmp_path, body, quote, scope_end
):
    ensure_case(tmp_path)
    event = build_event(
        claims=[
            claim_payload(
                "The bridge closure was ordered.",
                evidence=[evidence_payload(content=body)],
                source_quote=quote,
                source_quote_start=0,
                source_quote_end=len(quote),
            )
        ],
        evidence=[evidence_payload(content=body)],
        outcome=outcome_payload(0, scope_end),
    )
    assert store_event_in_db(event, case_id="case-1", create_review=False) is True

    session = db_session(tmp_path)
    try:
        link = session.query(ClaimEvidenceLink).one()
        assert stored(link, "alignment_status") in {"no_match", "source_unavailable"}
        assert stored(link, "alignment_status") != "exact"
        assert stored(link, "citation_id") is None
        assert session.query(ClaimCitation).count() == 0
        assert stored(link, "relation") == "uncertain"
        assert stored(link, "quote") is None
        assert stored(link, "start_char") is None
        assert stored(link, "end_char") is None
        assert stored(link, "assessment_metadata")["diagnostic_reason"]

        service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
        service._recompute_case_claim_aggregates(session, "case-1")
        session.commit()
        claim = session.query(Claim).one()
        assert stored(claim, "support_count") == 0
        assert stored(claim, "oppose_count") == 0
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 3. No proposal and legacy no-case/no-capture payloads still work honestly
# ---------------------------------------------------------------------------


def test_no_proposal_is_not_provided_uncertain_and_uncited(tmp_path):
    ensure_case(tmp_path)
    event = build_event(
        claims=[claim_payload("The bridge closed.", evidence=[evidence_payload()])],
        evidence=[evidence_payload()],
        outcome=outcome_payload(0, len(evidence_payload()["content"])),
    )
    assert store_event_in_db(event, case_id="case-1", create_review=False) is True

    session = db_session(tmp_path)
    try:
        link = session.query(ClaimEvidenceLink).one()
        assert stored(link, "capture_id") is not None  # anchored to the observed capture
        assert stored(link, "alignment_status") == "not_provided"
        assert stored(link, "relation") == "uncertain"
        assert stored(link, "citation_id") is None
        assert session.query(ClaimCitation).count() == 0
        assert stored(link, "assessment_metadata")["diagnostic_reason"] == "quote_not_proposed"
    finally:
        session.close()


def test_legacy_payload_without_case_or_capture_still_writes_links(tmp_path):
    init_database(str(tmp_path / "triangulate.db"))
    event = build_event(
        claims=[
            claim_payload(
                "A legacy assertion.",
                evidence=[evidence_payload(content=None)],
            )
        ],
        evidence=[evidence_payload(content=None)],
    )
    # No case_id, no capture and no extraction outcome: the historical CLI path.
    assert store_event_in_db(event) is True

    session = db_session(tmp_path)
    try:
        link = session.query(ClaimEvidenceLink).one()
        assert stored(link, "capture_id") is None
        assert stored(link, "citation_id") is None
        assert stored(link, "alignment_status") == "not_provided"
        assert stored(link, "relation") == "uncertain"
        assert stored(link, "assessment_metadata")["diagnostic_reason"] == "capture_unavailable"
        assert session.query(ClaimCitation).count() == 0
        assert session.query(Claim).count() == 1
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 4. Aggregate eligibility and dedup
# ---------------------------------------------------------------------------


def test_collector_reported_by_does_not_increment_support(tmp_path):
    ensure_case(tmp_path)
    body = "The bridge closed at noon. The bridge reopened at midnight."
    quote = "The bridge closed at noon."
    start = body.find(quote)
    event = build_event(
        claims=[
            claim_payload(
                "The bridge closure was ordered.",
                evidence=[evidence_payload(content=body)],
                source_quote=quote,
                source_quote_start=start,
                source_quote_end=start + len(quote),
            )
        ],
        evidence=[evidence_payload(content=body)],
        outcome=outcome_payload(0, len(body)),
    )
    assert store_event_in_db(event, case_id="case-1", create_review=False) is True

    session = db_session(tmp_path)
    try:
        service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
        service._recompute_case_claim_aggregates(session, "case-1")
        session.commit()
        link = session.query(ClaimEvidenceLink).one()
        claim = session.query(Claim).one()
        assert stored(link, "relation") == "reported_by"
        assert stored(claim, "support_count") == 0
        assert stored(claim, "oppose_count") == 0
    finally:
        session.close()


def test_explicit_versioned_assessments_count_once_and_never_promote_status(
    tmp_path,
):
    ensure_case(tmp_path)
    body = "The bridge closed at noon. Then it stayed open."
    support_quote = "The bridge closed at noon."
    scope = outcome_payload(0, len(body))

    support_evidence = evidence_payload(
        evidence_id="evidence-support",
        content=body,
        relation="supports",
        assessment_origin="human",
        assessment_version="review-v1",
        assessment_metadata={"rationale": "affirms the closure"},
    )
    oppose_evidence = evidence_payload(
        evidence_id="evidence-oppose",
        content=body,
        url="https://example.com/source-2",
        relation="contradicts",
        assessment_origin="human",
        assessment_version="review-v1",
        assessment_metadata={"rationale": "denies the closure"},
    )
    claim_text = "Alpha disputes the bridge closure."
    claims = [
        claim_payload(
            claim_text,
            claim_id="claim-a",
            evidence=[copy.deepcopy(support_evidence), copy.deepcopy(oppose_evidence)],
            verification_status="ALLEGED",
            source_quote=support_quote,
            source_quote_start=body.find(support_quote),
            source_quote_end=body.find(support_quote) + len(support_quote),
        ),
        # Same assertion group and the same evidence: this duplicate link must
        # not double count the support contribution.
        claim_payload(
            claim_text,
            claim_id="claim-b",
            evidence=[copy.deepcopy(support_evidence)],
            verification_status="ALLEGED",
            source_quote=support_quote,
            source_quote_start=body.find(support_quote),
            source_quote_end=body.find(support_quote) + len(support_quote),
        ),
    ]
    event = build_event(
        claims=claims,
        evidence=[copy.deepcopy(support_evidence), copy.deepcopy(oppose_evidence)],
        outcome=scope,
    )
    assert store_event_in_db(event, case_id="case-1", create_review=False) is True

    session = db_session(tmp_path)
    try:
        assert session.query(ClaimEvidenceLink).count() == 3
        service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
        service._recompute_case_claim_aggregates(session, "case-1")
        session.commit()
        stored_claims = session.query(Claim).order_by(Claim.id.asc()).all()
        assert [stored(claim, "support_count") for claim in stored_claims] == [1, 1]
        assert [stored(claim, "oppose_count") for claim in stored_claims] == [1, 1]
        # Verification status is a human/model classification, never derived from
        # quotation presence, alignment or aggregate counts.
        assert all(
            stored(claim, "verification_status") == VerificationStatus.ALLEGED
            for claim in stored_claims
        )
        link = (
            session.query(ClaimEvidenceLink)
            .filter(ClaimEvidenceLink.evidence_id == "evidence-support")
            .first()
        )
        assert stored(link, "relation") == "supports"
        assert stored(link, "alignment_status") == "exact"
        assert stored(link, "assessment_origin") == "human"
        assert stored(link, "assessment_version") == "review-v1"
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 5. Review hash: changed semantics invalidate, identical reruns and version
#    transitions preserve an approval
# ---------------------------------------------------------------------------


def _quoted_event(
    *,
    quote: str,
    body: str,
    assessment_origin: str | None = None,
    assessment_version: str | None = None,
    evidence_relation: str | None = None,
) -> dict:
    extra: dict = {}
    if assessment_origin is not None:
        extra["assessment_origin"] = assessment_origin
    if assessment_version is not None:
        extra["assessment_version"] = assessment_version
    if evidence_relation is not None:
        extra["relation"] = evidence_relation
    start = body.find(quote)
    # A fabricated quote is a deliberate diagnostic (no valid offsets).
    quote_start = start if start >= 0 else None
    quote_end = start + len(quote) if start >= 0 else None
    return build_event(
        claims=[
            claim_payload(
                "The bridge closure was ordered.",
                evidence=[evidence_payload(content=body, **extra)],
                source_quote=quote,
                source_quote_start=quote_start,
                source_quote_end=quote_end,
            )
        ],
        evidence=[evidence_payload(content=body, **extra)],
        outcome=outcome_payload(0, len(body)),
    )


def test_changed_quotation_invalidates_an_approval(tmp_path):
    ensure_case(tmp_path)
    body = "The bridge closed at noon. The bridge reopened at midnight."
    first = _quoted_event(quote="The bridge closed at noon.", body=body)
    assert store_event_in_db(first, case_id="case-1", create_review=True) is True
    approve(tmp_path, "event-1")

    changed = _quoted_event(quote="The bridge reopened at midnight.", body=body)
    assert store_event_in_db(changed, case_id="case-1", create_review=True) is True

    review = read_review(tmp_path, "event-1")
    assert stored(review, "status") == ReviewStatus.PENDING
    assert stored(review, "reviewed_at") is None
    assert stored(review, "notes") == REVIEW_NOTES
    assert stored(review, "previous_decision_json") is not None
    assert stored(review, "previous_decision_json")["reason"] == "analysis_changed"
    assert stored(review, "previous_decision_json")["status"] == "approved"
    assert stored(review, "previous_decision_json")["notes"] == REVIEW_NOTES


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param("alignment", id="changed-alignment"),
        pytest.param("assessment_version", id="changed-assessment-version"),
    ],
)
def test_changed_alignment_or_assessment_invalidates(tmp_path, mutation):
    ensure_case(tmp_path)
    body = "The bridge closed at noon. Then it stayed open."
    quote = "The bridge closed at noon."
    first = _quoted_event(
        quote=quote,
        body=body,
        assessment_origin="human",
        assessment_version="review-v1",
        evidence_relation="supports",
    )
    assert store_event_in_db(first, case_id="case-1", create_review=True) is True
    approve(tmp_path, "event-1")

    if mutation == "alignment":
        # Same claim text, but the quotation no longer matches the source.
        changed = _quoted_event(
            quote="The bridge never closed.",
            body=body,
            assessment_origin="human",
            assessment_version="review-v1",
            evidence_relation="supports",
        )
    else:
        changed = _quoted_event(
            quote=quote,
            body=body,
            assessment_origin="human",
            assessment_version="review-v2",
            evidence_relation="supports",
        )
    assert store_event_in_db(changed, case_id="case-1", create_review=True) is True

    review = read_review(tmp_path, "event-1")
    assert stored(review, "status") == ReviewStatus.PENDING
    assert stored(review, "previous_decision_json")["reason"] == "analysis_changed"


def test_identical_rerun_preserves_the_approval(tmp_path):
    ensure_case(tmp_path)
    body = "The bridge closed at noon. The bridge reopened at midnight."
    event = _quoted_event(quote="The bridge closed at noon.", body=body)
    assert store_event_in_db(event, case_id="case-1", create_review=True) is True
    approve(tmp_path, "event-1")
    approved_hash = read_hash(tmp_path, "event-1")

    rerun = _quoted_event(quote="The bridge closed at noon.", body=body)
    assert store_event_in_db(rerun, case_id="case-1", create_review=True) is True

    review = read_review(tmp_path, "event-1")
    assert stored(review, "status") == ReviewStatus.APPROVED
    assert stored(review, "reviewed_at") == REVIEW_TS.replace(tzinfo=None)
    assert stored(review, "notes") == REVIEW_NOTES
    assert stored(review, "previous_decision_json") is None
    assert stored(review, "analysis_hash") == approved_hash
    assert read_hash(tmp_path, "event-1") == approved_hash


def test_legacy_hash_transition_preserves_unchanged_legacy_approval(tmp_path):
    ensure_case(tmp_path)
    body = "Original legacy source body."
    legacy_event = build_event(
        claims=[
            claim_payload(
                "A legacy assertion.",
                evidence=[
                    evidence_payload(
                        content=body, relation="supports", confidence_score=0.9
                    )
                ],
            )
        ],
        evidence=[
            evidence_payload(content=body, relation="supports", confidence_score=0.9)
        ],
    )
    # No extraction outcome: the historical CLI/full-replacement path.
    assert store_event_in_db(legacy_event, case_id="case-1", create_review=True) is True

    session = db_session(tmp_path)
    try:
        legacy_hash = compute_legacy_event_analysis_hash(session, "event-1")
        current_hash = compute_event_analysis_hash(session, "event-1")
        b01_payload = canonical_analysis_payload(
            session, "event-1", projection="b01"
        )
        e02_payload = canonical_analysis_payload(
            session, "event-1", projection="e02"
        )
    finally:
        session.close()
    assert legacy_hash.startswith(f"{LEGACY_ANALYSIS_HASH_VERSION}:")
    assert current_hash.startswith(f"{ANALYSIS_HASH_VERSION}:")
    # Links without citation semantics contribute an entry identical to the B01
    # projection: only the version field differs, so the *content* the legacy
    # transition compares is unchanged.
    b01_payload.pop("version")
    e02_payload.pop("version")
    assert b01_payload == e02_payload
    approve(tmp_path, "event-1", analysis_hash=legacy_hash)

    rerun = copy.deepcopy(legacy_event)
    assert store_event_in_db(rerun, case_id="case-1", create_review=True) is True

    review = read_review(tmp_path, "event-1")
    new_hash = read_hash(tmp_path, "event-1")
    assert new_hash.startswith(f"{ANALYSIS_HASH_VERSION}:")
    assert new_hash != legacy_hash
    # Unchanged stored analysis, algorithm version only: the decision survives.
    assert stored(review, "status") == ReviewStatus.APPROVED
    assert stored(review, "reviewed_at") == REVIEW_TS.replace(tzinfo=None)
    assert stored(review, "notes") == REVIEW_NOTES
    assert stored(review, "previous_decision_json") is None
    assert stored(review, "analysis_hash") == new_hash


def test_ids_times_and_row_order_do_not_affect_the_hash(tmp_path):
    ensure_case(tmp_path)
    body = "The bridge closed at noon. Then it stayed open."
    evidence = evidence_payload(content=body, relation="supports")
    claims = [
        claim_payload("First assertion.", claim_id="claim-a", evidence=[evidence]),
        claim_payload("Second assertion.", claim_id="claim-b", evidence=[evidence]),
    ]
    first = build_event(claims=claims, evidence=[evidence])
    assert store_event_in_db(first, case_id="case-1", create_review=False) is True
    before = read_hash(tmp_path, "event-1")

    # Reverse row order, use different generated claim IDs and a different event
    # timestamp. None of these are substantive analysis.
    reversed_claims = [
        claim_payload("Second assertion.", claim_id="claim-z", evidence=[evidence]),
        claim_payload("First assertion.", claim_id="claim-y", evidence=[evidence]),
    ]
    second = build_event(
        claims=reversed_claims,
        evidence=[evidence],
        timestamp=datetime(2026, 3, 9, 7, 0, tzinfo=UTC),
    )
    assert store_event_in_db(second, case_id="case-1", create_review=False) is True
    assert read_hash(tmp_path, "event-1") == before


# ---------------------------------------------------------------------------
# 6. The service no longer invents support/confidence or attachment support
# ---------------------------------------------------------------------------


def test_build_event_evidence_does_not_invent_relation_or_confidence(tmp_path):
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
    case = TopicCase(
        id="case-1",
        query="q",
        slug="case-1-slug",
        status=CaseStatus.INVESTIGATING,
        metadata_json={},
    )
    article = CaseArticle(
        id="article-1",
        case_id="case-1",
        url="https://example.com/article",
        title="Article title",
        source="Example",
        published_at="2026-03-08T12:00:00+00:00",
        fingerprint="fingerprint-1",
        content="Projection body",
        raw_payload={},
    )

    evidence = service._build_event_evidence(
        case, article, {"title": "Article title", "source_name": "Example"}
    )

    assert len(evidence) == 1
    item = evidence[0]
    assert "relation" not in item
    assert "confidence_score" not in item
    assert item["source_diversity_rank"] == 1
    assert item["content"] == "Projection body"
    assert item["verification_status"] == "UNVERIFIED"


def test_augment_claims_leaves_support_and_opposition_at_zero(tmp_path):
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
    attachments = [
        {"id": "evidence-1", "publisher": "Outlet One"},
        {"id": "evidence-2", "publisher": "Outlet Two"},
    ]
    claim = {"claim": "The bridge closed at noon.", "verification_status": "ALLEGED"}

    augmented = service._augment_claims_with_evidence(
        [claim], attachments, [], "event-1"
    )

    assert len(augmented) == 1
    result = augmented[0]
    assert result["support_count"] == 0
    assert result["oppose_count"] == 0
    # Observed distinct publishers across the event's attachments, not support.
    assert result["source_diversity_count"] == 2
    assert result["evidence"] == attachments
    assert result["claim_signature"] == _claim_signature(claim["claim"])


# ---------------------------------------------------------------------------
# Sanity: the aggregate rule matches the policy's own contribution semantics
# ---------------------------------------------------------------------------


def test_policy_resolution_used_by_writer_and_aggregates_is_consistent():
    collector = resolve_effective_relationship(
        stored_relation="supports",
        alignment_status="exact",
        exact_anchor=True,
        collector_generated=True,
    )
    unassessed = resolve_effective_relationship(
        stored_relation="supports",
        alignment_status="not_provided",
    )
    assessed = resolve_effective_relationship(
        stored_relation="contradicts",
        alignment_status="exact",
        assessment_origin="model",
        assessment_version="m-1",
        exact_anchor=True,
    )
    assert stored(collector, "effective_relationship") == "reported_by"
    assert stored(collector, "contribution") is None
    assert stored(unassessed, "effective_relationship") == "uncertain"
    assert stored(unassessed, "contribution") is None
    assert stored(assessed, "effective_relationship") == "contradicts"
    assert stored(assessed, "contribution") == "opposition"
