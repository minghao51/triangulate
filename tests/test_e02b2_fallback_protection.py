"""E02 pass B2: fallback must not erase valid analysis.

Covers the collector-outcome replacement guard in ``_write_event`` (a
fallback/unavailable/unknown rerun preserves claims, links, narratives, party
investigations, event analysis fields and reviews while still persisting or
reusing the source capture), the authoritative ``valid``/``empty`` replacement
paths, the legacy no-outcome compatibility path, first-time zero-claim events,
the case-service empty-extraction routing short-circuit, and claim-identity
matching (not list position) in ``_merge_party_results``.

All application databases are temporary; no provider/network calls are made.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import update

from src.cases.service import TopicCaseService, _claim_signature
from src.storage import (
    CaseArticle,
    CaseStatus,
    Claim,
    ClaimEvidenceLink,
    EvidenceCapture,
    EvidenceItem,
    Event,
    Narrative,
    PartyInvestigation,
    Review,
    ReviewStatus,
    TopicCase,
    init_database,
)
from src.storage.event_store import store_event_in_db

EVENT_TS = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)
REVIEW_TS = datetime(2026, 4, 1, 9, 30, tzinfo=UTC)
REVIEW_NOTES = "Reviewed by an analyst."


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
                    query="Fallback protection case",
                    slug=f"{case_id}-slug",
                    status=CaseStatus.INVESTIGATING,
                    metadata_json={},
                )
            )
            session.commit()
    finally:
        session.close()


def outcome_payload(
    status: str,
    *,
    reason: str = "",
    body_char_count: int = 20,
) -> dict:
    return {
        "status": status,
        "quote_proposals_trusted": status == "valid",
        "scope_start": 0,
        "scope_end": body_char_count,
        "body_char_count": body_char_count,
        "input_limit": 5000,
        "source_available": True,
        "reason": reason,
    }


def evidence_payload(
    *,
    evidence_id: str = "evidence-1",
    content: str | None = "Original source body",
    title: str = "Original source title",
    url: str = "https://example.com/source-1",
) -> dict:
    return {
        "id": evidence_id,
        "evidence_type": "article",
        "source_type": "rss",
        "title": title,
        "origin_url": url,
        "canonical_url": url,
        "publisher": "Outlet One",
        "published_at": "2026-03-08T00:00:00+00:00",
        "content": content,
        "capture_metadata": {},
        "verification_status": "UNVERIFIED",
        "credibility_tier": "unknown",
        "requires_human_review": False,
        "verification_checks": [],
    }


def claim_payload(
    text: str,
    *,
    evidence: list[dict] | None = None,
    verification_status: str = "ALLEGED",
    claim_id: str | None = None,
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
        "support_count": len(evidence or []),
        "oppose_count": 0,
        "source_diversity_count": 1,
        "party_positions": {"Alpha": "NEUTRAL"},
    }
    if claim_id is not None:
        payload["id"] = claim_id
    if source_quote is not None:
        payload["source_quote"] = source_quote
        payload["source_quote_start"] = source_quote_start
        payload["source_quote_end"] = source_quote_end
    return payload


def narrative_payload(
    cluster_id: str = "0", stance_summary: str = "Original narrative"
) -> dict:
    return {
        "cluster_id": cluster_id,
        "stance_summary": stance_summary,
        "claim_count": 1,
    }


def investigation_payload(
    party_name: str = "Alpha",
    *,
    supported: str = "Alpha disputes Beta",
) -> dict:
    return {
        "party_name": party_name,
        "investigation": {
            "claims_supported": [
                {"claim_text": supported, "position": "SUPPORTS"}
            ],
            "claims_contested": [],
            "unique_claims": [],
        },
        "party_stance": {"overall_position": "Supports"},
    }


def build_event(
    event_id: str = "event-1",
    *,
    outcome: dict | None = None,
    title: str = "Original title",
    summary: str = "Original summary",
    verification_status: str = "PROBABLE",
    claims: list[dict] | None = None,
    narratives: list[dict] | None = None,
    parties: list[dict] | None = None,
    investigations: list[dict] | None = None,
    evidence: list[dict] | None = None,
    source_url: str = "https://example.com/source-1",
) -> dict:
    payload = {
        "id": event_id,
        "timestamp": EVENT_TS,
        "title": title,
        "summary": summary,
        "verification_status": verification_status,
        "source_url": source_url,
        "source_name": "Example",
        "claims": claims if claims is not None else [],
        "narratives": narratives if narratives is not None else [],
        "parties": parties if parties is not None else [],
        "party_investigations": (
            investigations if investigations is not None else []
        ),
        "evidence": evidence if evidence is not None else [],
    }
    if outcome is not None:
        payload["extraction_outcome"] = outcome
    return payload


def full_event(event_id: str = "event-1", *, outcome: dict | None = None) -> dict:
    evidence = evidence_payload()
    return build_event(
        event_id,
        outcome=outcome
        if outcome is not None
        else outcome_payload("valid", body_char_count=len("Original source body")),
        claims=[
            claim_payload(
                "Alpha disputes Beta",
                evidence=[copy.deepcopy(evidence)],
                source_quote="Alpha disputes",
                source_quote_start=0,
                source_quote_end=14,
            )
        ],
        narratives=[narrative_payload()],
        parties=[{"canonical_name": "Alpha", "aliases": ["Alpha"]}],
        investigations=[investigation_payload()],
        evidence=[copy.deepcopy(evidence)],
    )


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


def read_review(tmp_path, event_id: str) -> ReviewSnapshot | None:
    session = db_session(tmp_path)
    try:
        return _review_snapshot(session, event_id)
    finally:
        session.close()


def approve_review(tmp_path, event_id: str) -> None:
    session = db_session(tmp_path)
    try:
        # Core update stores the same values without assigning to a classic
        # ``Column[...]`` descriptor (a typing artefact, not a runtime contract).
        session.execute(
            update(Review)
            .where(Review.event_id == event_id)
            .values(
                status=ReviewStatus.APPROVED,
                reviewed_at=REVIEW_TS,
                notes=REVIEW_NOTES,
            )
        )
        session.commit()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 1–2. Non-authoritative rewrites preserve every piece of existing analysis
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status", ["fallback", "unavailable", "totally_unknown_status"]
)
def test_non_authoritative_rewrite_preserves_existing_analysis(tmp_path, status):
    ensure_case(tmp_path)
    original = full_event()
    assert store_event_in_db(original, case_id="case-1", create_review=True) is True
    approve_review(tmp_path, "event-1")

    session = db_session(tmp_path)
    try:
        before_review = session.query(Review).filter(Review.event_id == "event-1").one()
        review_id = before_review.id
        review_hash = before_review.analysis_hash
        original_claim = session.query(Claim).one()
        original_claim_id = original_claim.id
        original_link_id = session.query(ClaimEvidenceLink).one().id
        original_capture = session.query(EvidenceCapture).one()
        capture_id = original_capture.id
    finally:
        session.close()

    replacement_evidence = evidence_payload(
        content="Original source body", title="Fallback source title"
    )
    rewrite = build_event(
        "event-1",
        outcome=outcome_payload(status, reason="rewrite_not_authoritative"),
        title="Fallback title",
        summary="Fallback summary",
        verification_status="ALLEGED",
        claims=[
            claim_payload(
                "Fallback replacement claim",
                evidence=[copy.deepcopy(replacement_evidence)],
            )
        ],
        narratives=[narrative_payload("9", "Fallback narrative")],
        parties=[{"canonical_name": "Beta", "aliases": ["Beta"]}],
        investigations=[investigation_payload("Beta")],
        evidence=[copy.deepcopy(replacement_evidence)],
    )

    assert store_event_in_db(rewrite, case_id="case-1", create_review=True) is True

    session = db_session(tmp_path)
    try:
        event = session.query(Event).filter(Event.id == "event-1").one()
        assert stored(event, "title") == "Original title"
        assert stored(event, "summary") == "Original summary"
        assert stored(event, "verification_status").value == "PROBABLE"

        claims = session.query(Claim).filter(Claim.event_id == "event-1").all()
        assert len(claims) == 1
        assert stored(claims[0], "id") == original_claim_id
        assert stored(claims[0], "claim_text") == "Alpha disputes Beta"
        assert stored(claims[0], "verification_status").value == "ALLEGED"
        assert (
            session.query(Claim)
            .filter(Claim.claim_text == "Fallback replacement claim")
            .count()
            == 0
        )

        links = session.query(ClaimEvidenceLink).all()
        assert len(links) == 1
        assert stored(links[0], "id") == original_link_id
        assert stored(links[0], "claim_id") == original_claim_id
        assert stored(links[0], "evidence_id") == "evidence-1"

        narratives = session.query(Narrative).all()
        assert len(narratives) == 1
        assert stored(narratives[0], "cluster_id") == "event-1:0"
        assert stored(narratives[0], "stance_summary") == "Original narrative"

        investigations = session.query(PartyInvestigation).all()
        assert len(investigations) == 1
        assert stored(investigations[0], "investigation_data")["claims_supported"] == [
            {"claim_text": "Alpha disputes Beta", "position": "SUPPORTS"}
        ]
        assert stored(investigations[0], "party_stance") == "Supports"

        review = session.query(Review).filter(Review.event_id == "event-1").one()
        assert stored(review, "id") == review_id
        assert stored(review, "status") == ReviewStatus.APPROVED
        assert stored(review, "notes") == REVIEW_NOTES
        assert stored(review, "analysis_hash") == review_hash

        # E01: the source record and its immutable capture are still written.
        evidence = session.query(EvidenceItem).one()
        assert stored(evidence, "title") == "Fallback source title"
        captures = session.query(EvidenceCapture).all()
        assert len(captures) == 1
        assert stored(captures[0], "id") == capture_id
        assert stored(captures[0], "text") == "Original source body"
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 3. An authoritative valid rerun still replaces analysis as today
# ---------------------------------------------------------------------------


def test_valid_outcome_still_fully_replaces_analysis(tmp_path):
    ensure_case(tmp_path)
    assert store_event_in_db(full_event(), case_id="case-1", create_review=False) is True

    session = db_session(tmp_path)
    try:
        old_claim_id = session.query(Claim).one().id
        old_narrative_id = session.query(Narrative).one().id
    finally:
        session.close()

    replacement_evidence = evidence_payload()
    rewrite = build_event(
        "event-1",
        outcome=outcome_payload("valid", body_char_count=len("Replacement body")),
        title="Replacement title",
        summary="Replacement summary",
        verification_status="CONFIRMED",
        claims=[
            claim_payload(
                "Replacement claim",
                evidence=[copy.deepcopy(replacement_evidence)],
                verification_status="CONFIRMED",
            )
        ],
        narratives=[narrative_payload("0", "Replacement narrative")],
        investigations=[investigation_payload("Alpha", supported="Replacement claim")],
        parties=[{"canonical_name": "Alpha", "aliases": ["Alpha"]}],
        evidence=[copy.deepcopy(replacement_evidence)],
    )
    assert store_event_in_db(rewrite, case_id="case-1", create_review=False) is True

    session = db_session(tmp_path)
    try:
        event = session.query(Event).filter(Event.id == "event-1").one()
        assert stored(event, "title") == "Replacement title"
        assert stored(event, "summary") == "Replacement summary"
        assert stored(event, "verification_status").value == "CONFIRMED"

        claims = session.query(Claim).filter(Claim.event_id == "event-1").all()
        assert len(claims) == 1
        assert stored(claims[0], "claim_text") == "Replacement claim"
        assert stored(claims[0], "id") != old_claim_id
        assert stored(claims[0], "support_count") == 1

        link = session.query(ClaimEvidenceLink).one()
        assert stored(link, "claim_id") == claims[0].id

        narrative = session.query(Narrative).one()
        assert stored(narrative, "id") != old_narrative_id
        assert stored(narrative, "stance_summary") == "Replacement narrative"

        investigation = session.query(PartyInvestigation).one()
        assert stored(investigation, "investigation_data")["claims_supported"] == [
            {"claim_text": "Replacement claim", "position": "SUPPORTS"}
        ]
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 4. An explicit empty outcome is authoritative and replaces prior claims
# ---------------------------------------------------------------------------


def test_empty_outcome_replaces_prior_analysis(tmp_path):
    ensure_case(tmp_path)
    assert store_event_in_db(full_event(), case_id="case-1", create_review=False) is True

    empty_rewrite = build_event(
        "event-1",
        outcome=outcome_payload("empty", reason="validated_empty_collection"),
        title="Empty title",
        summary="Empty summary",
        verification_status="ALLEGED",
        claims=[],
        narratives=[],
        parties=[],
        investigations=[],
        evidence=[evidence_payload()],
    )
    assert (
        store_event_in_db(empty_rewrite, case_id="case-1", create_review=False)
        is True
    )

    session = db_session(tmp_path)
    try:
        event = session.query(Event).filter(Event.id == "event-1").one()
        assert stored(event, "title") == "Empty title"
        assert stored(event, "verification_status").value == "ALLEGED"
        assert session.query(Claim).count() == 0
        assert session.query(ClaimEvidenceLink).count() == 0
        assert session.query(Narrative).count() == 0
        assert session.query(PartyInvestigation).count() == 0
    finally:
        session.close()


@pytest.mark.asyncio
async def test_empty_extraction_does_not_invoke_party_workflow(tmp_path, monkeypatch):
    init_database(str(tmp_path / "triangulate.db"))
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
    service.party_workflow = AsyncMock()

    async def fake_process(article_data):
        return {
            "id": "temporary",
            "timestamp": EVENT_TS,
            "title": article_data["title"],
            "summary": "",
            "verification_status": "ALLEGED",
            "claims": [],
            "narratives": [],
            "parties": [],
            "party_investigations": [],
            "extraction_outcome": outcome_payload(
                "empty",
                reason="validated_empty_collection",
                body_char_count=len("Empty body"),
            ),
        }

    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)

    # Importance "high" would normally route this zero-claim event into the
    # party workflow (a second extraction attempt over zero claims).
    case = TopicCase(
        id="case-1",
        query="Empty extraction",
        slug="empty-extraction",
        status=CaseStatus.INVESTIGATING,
        importance="high",
        metadata_json={},
    )
    article = CaseArticle(
        id="article-1",
        case_id="case-1",
        url="https://example.com/empty",
        title="Empty article",
        source="Example",
        published_at="2026-03-08T12:00:00+00:00",
        fingerprint="fingerprint-empty",
        content="Empty body",
        raw_payload={"content": "Empty body"},
    )

    event = await service._process_case_article(case, article)

    assert service._should_route_to_party_workflow(case, event) is True
    service.party_workflow.ainvoke.assert_not_awaited()
    assert event["workflow_route"] == "baseline_only"
    assert event["routing_reason"] == "validated_empty_extraction"
    assert event["claims"] == []
    assert event["extraction_outcome"] == outcome_payload(
        "empty",
        reason="validated_empty_collection",
        body_char_count=len("Empty body"),
    )
    assert event["evidence"][0]["content"] == "Empty body"


# ---------------------------------------------------------------------------
# 5. Legacy payloads without an outcome keep full-replacement semantics
# ---------------------------------------------------------------------------


def test_legacy_payload_without_outcome_still_replaces_claims(tmp_path):
    ensure_case(tmp_path)
    assert store_event_in_db(full_event(), case_id="case-1", create_review=False) is True

    legacy_rewrite = build_event(
        "event-1",
        outcome=None,
        title="Legacy title",
        claims=[
            claim_payload(
                "Legacy replacement claim",
                evidence=[evidence_payload()],
            )
        ],
        narratives=[narrative_payload("0", "Legacy narrative")],
        evidence=[evidence_payload()],
    )
    assert "extraction_outcome" not in legacy_rewrite
    assert (
        store_event_in_db(legacy_rewrite, case_id="case-1", create_review=False)
        is True
    )

    session = db_session(tmp_path)
    try:
        event = session.query(Event).filter(Event.id == "event-1").one()
        assert stored(event, "title") == "Legacy title"
        claims = session.query(Claim).filter(Claim.event_id == "event-1").all()
        assert len(claims) == 1
        assert stored(claims[0], "claim_text") == "Legacy replacement claim"
        assert session.query(Narrative).one().stance_summary == "Legacy narrative"
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 6. Zero-claim fallback events keep evidence and the guard is a safe no-op
# ---------------------------------------------------------------------------


def test_first_time_zero_claim_fallback_event_creates_evidence_and_capture(tmp_path):
    ensure_case(tmp_path)
    event = build_event(
        "event-zero",
        outcome=outcome_payload("fallback", reason="no_claims_extracted"),
        title="Zero claim title",
        summary="Zero claim summary",
        claims=[],
        narratives=[],
        evidence=[evidence_payload(content="Fallback body")],
    )
    assert store_event_in_db(event, case_id="case-1", create_review=False) is True

    session = db_session(tmp_path)
    try:
        assert session.query(Event).count() == 1
        assert session.query(Claim).count() == 0
        assert session.query(EvidenceItem).count() == 1
        captures = session.query(EvidenceCapture).all()
        assert len(captures) == 1
        assert stored(captures[0], "text") == "Fallback body"
        first_capture_id = captures[0].id
    finally:
        session.close()

    # A second non-authoritative rewrite of the same zero-claim event must not
    # raise even though there is no analysis to protect.
    rewrite = build_event(
        "event-zero",
        outcome=outcome_payload("fallback", reason="no_claims_extracted"),
        title="Second zero title",
        summary="Second zero summary",
        claims=[],
        narratives=[],
        evidence=[evidence_payload(content="Fallback body")],
    )
    assert store_event_in_db(rewrite, case_id="case-1", create_review=False) is True

    session = db_session(tmp_path)
    try:
        event = session.query(Event).filter(Event.id == "event-zero").one()
        assert stored(event, "title") == "Zero claim title"
        assert session.query(Claim).count() == 0
        assert session.query(EvidenceCapture).count() == 1
        assert session.query(EvidenceCapture).one().id == first_capture_id
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 7. Party merge uses claim identity, never list position
# ---------------------------------------------------------------------------


def test_merge_party_results_matches_claims_by_identity(tmp_path):
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
    baseline = {
        "id": "event-merge",
        "claims": [
            {
                "claim": "Alpha met Beta",
                "id": "baseline-claim-1",
                "claim_signature": "stale-signature-1",
                "verification_status": "ALLEGED",
                "source_quote": "Alpha met",
                "source_quote_start": 0,
                "source_quote_end": 9,
                "evidence": [{"id": "evidence-1"}],
                "support_count": 1,
                "oppose_count": 0,
                "source_diversity_count": 1,
            },
            {
                "claim": "Beta denied the report",
                "id": "baseline-claim-2",
                "claim_signature": "stale-signature-2",
                "verification_status": "ALLEGED",
                "source_quote": "Beta denied",
                "source_quote_start": 0,
                "source_quote_end": 11,
                "evidence": [{"id": "evidence-2"}],
                "support_count": 1,
                "oppose_count": 0,
                "source_diversity_count": 1,
            },
        ],
        "parties": [],
        "party_investigations": [],
        "evidence": [{"id": "event-source"}],
        "llm_metadata": {"collector": {"parse_status": "ok"}},
    }
    declaration = {
        "final_determinations": [
            {
                "claim_text": "  ALPHA met beta ",
                "verification_status": "CONTESTED",
                "fact_allegation_classification": "FACT",
                "reasoning": "Reason one",
                "party_positions": {"Alpha": "SUPPORTS", "Beta": "CONTRADICTS"},
                "controversy_score": 0.8,
            },
            {
                "claim_text": "Totally different assertion",
                "verification_status": "PROBABLE",
                "fact_allegation_classification": "ALLEGATION",
                "reasoning": "Reason two",
                "party_positions": {"Alpha": "NEUTRAL"},
                "controversy_score": 0.2,
            },
        ],
        "event_summary": {},
        "parties": {"parties": []},
        "party_investigations": [],
        "llm_metadata": {"arbiter": {"parse_status": "ok"}},
    }

    merged = service._merge_party_results(baseline, declaration)
    matched, unmatched = merged["claims"]

    final_matched_text = "  ALPHA met beta "
    matched_signature = _claim_signature(final_matched_text)
    assert matched["claim"] == final_matched_text
    # The proposal follows the assertion it was made against, not the index.
    assert matched["source_quote"] == "Alpha met"
    assert matched["source_quote_start"] == 0
    assert matched["source_quote_end"] == 9
    assert matched["evidence"] == [{"id": "evidence-1"}]
    assert matched["verification_status"] == "CONTESTED"
    assert matched["fact_allegation_type"] == "FACT"
    assert matched["arbiter_reasoning"] == "Reason one"
    assert matched["party_positions"] == {
        "Alpha": "SUPPORTS",
        "Beta": "CONTRADICTS",
    }
    assert matched["controversy_score"] == 0.8
    assert matched["claim_signature"] == matched_signature
    assert matched["claim_signature"] != "stale-signature-1"
    assert matched["id"] == str(
        uuid.uuid5(
            uuid.NAMESPACE_URL, f"claim:event-merge:{matched_signature}"
        )
    )
    assert matched["id"] != "baseline-claim-1"

    unmatched_signature = _claim_signature("Totally different assertion")
    assert unmatched["claim"] == "Totally different assertion"
    # No assertion-specific data may leak from the positional neighbour: in
    # particular no quotation may follow different text.
    for leaked_key in (
        "source_quote",
        "source_quote_start",
        "source_quote_end",
    ):
        assert leaked_key not in unmatched
    # Source attachment is event-level, not assertion-specific: the rewritten
    # claim still links to this event's source document, never to the positional
    # neighbour's claim-specific evidence.
    assert unmatched["evidence"] == [{"id": "event-source"}]
    assert unmatched["evidence"] != [{"id": "evidence-2"}]
    # B3 contract: a source attachment is not evidence of support. Support and
    # opposition stay zero until `_recompute_case_claim_aggregates` derives them
    # from eligible, policy-resolved stored links; only the observed distinct
    # publisher count is attachment-based.
    assert unmatched["support_count"] == 0
    assert unmatched["oppose_count"] == 0
    assert unmatched["source_diversity_count"] == 1
    assert unmatched["verification_status"] == "PROBABLE"
    assert unmatched["claim_signature"] == unmatched_signature
    assert unmatched["id"] == str(
        uuid.uuid5(
            uuid.NAMESPACE_URL, f"claim:event-merge:{unmatched_signature}"
        )
    )

    # No determinations means the baseline claims are retained unchanged.
    baseline_only = service._merge_party_results(
        baseline,
        {
            "final_determinations": [],
            "event_summary": {},
            "parties": {"parties": []},
            "party_investigations": [],
            "llm_metadata": {},
        },
    )
    assert baseline_only["claims"] is baseline["claims"]


def test_merge_party_results_consumes_duplicate_signatures_once(tmp_path):
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
    baseline = {
        "id": "event-duplicate",
        "claims": [
            {
                "claim": "Same assertion",
                "id": "baseline-a",
                "source_quote": "Same",
                "source_quote_start": 0,
                "source_quote_end": 4,
                "evidence": [{"id": "evidence-a"}],
            },
            {
                "claim": "Same assertion",
                "id": "baseline-b",
                "source_quote": "assertion",
                "source_quote_start": 5,
                "source_quote_end": 14,
                "evidence": [{"id": "evidence-b"}],
            },
        ],
        "parties": [],
        "party_investigations": [],
        "llm_metadata": {},
    }
    declaration = {
        "final_determinations": [
            {
                "claim_text": "Same assertion",
                "verification_status": "ALLEGED",
            },
            {
                "claim_text": "Same assertion",
                "verification_status": "ALLEGED",
            },
            {
                "claim_text": "Same assertion",
                "verification_status": "ALLEGED",
            },
        ],
        "event_summary": {},
        "parties": {"parties": []},
        "party_investigations": [],
        "llm_metadata": {},
    }

    merged = service._merge_party_results(baseline, declaration)

    assert [
        claim.get("source_quote") for claim in merged["claims"]
    ] == ["Same", "assertion", None]
    assert "source_quote" not in merged["claims"][2]
    # The third identical text consumed no baseline claim, so it must not inherit
    # either neighbour's claim-specific source attachment. Attachment is
    # event-level (empty in this baseline), never taken from a neighbour.
    assert merged["claims"][2]["evidence"] == []
    assert merged["claims"][2]["support_count"] == 0
    assert [claim["claim"] for claim in merged["claims"]] == [
        "Same assertion",
        "Same assertion",
        "Same assertion",
    ]


# ---------------------------------------------------------------------------
# 8. The guarded path never creates or resets a review
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 9. Determinations without usable text are never stored as empty assertions
# ---------------------------------------------------------------------------


def test_merge_party_results_skips_determinations_without_text(tmp_path):
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
    baseline = {
        "id": "event-empty-text",
        "claims": [
            {
                "claim": "Alpha met Beta",
                "id": "baseline-claim-1",
                "support_count": 1,
                "evidence": [{"id": "evidence-1"}],
            }
        ],
        "parties": [],
        "party_investigations": [],
        "evidence": [{"id": "event-source"}],
        "llm_metadata": {},
    }
    declaration = {
        "final_determinations": [
            {"claim_text": "   \n\t", "verification_status": "CONTESTED"},
            {"verification_status": "PROBABLE"},
            {
                "claim_text": "Alpha met Beta",
                "verification_status": "CONFIRMED",
            },
        ],
        "event_summary": {},
        "parties": {"parties": []},
        "party_investigations": [],
        "llm_metadata": {},
    }

    merged = service._merge_party_results(baseline, declaration)

    assert len(merged["claims"]) == 1
    assert merged["claims"][0]["claim"] == "Alpha met Beta"
    assert merged["claims"][0]["verification_status"] == "CONFIRMED"
    assert merged["claims"][0]["claim_signature"] == _claim_signature(
        "Alpha met Beta"
    )


def test_guarded_rewrite_never_creates_or_resets_reviews(tmp_path):
    ensure_case(tmp_path)
    assert store_event_in_db(full_event(), case_id="case-1", create_review=True) is True
    approve_review(tmp_path, "event-1")

    before = read_review(tmp_path, "event-1")
    assert before is not None
    review_id = before.id
    review_hash = before.analysis_hash

    fallback_rewrite = build_event(
        "event-1",
        outcome=outcome_payload("fallback", reason="no_claims_extracted"),
        claims=[],
        narratives=[],
        evidence=[evidence_payload()],
    )
    assert (
        store_event_in_db(fallback_rewrite, case_id="case-1", create_review=True)
        is True
    )

    session = db_session(tmp_path)
    try:
        reviews = session.query(Review).filter(Review.event_id == "event-1").all()
        assert len(reviews) == 1
        assert stored(reviews[0], "id") == review_id
        assert stored(reviews[0], "status") == ReviewStatus.APPROVED
        assert stored(reviews[0], "notes") == REVIEW_NOTES
        assert stored(reviews[0], "analysis_hash") == review_hash
        assert stored(reviews[0], "reviewed_at") == REVIEW_TS.replace(tzinfo=None)
    finally:
        session.close()

    # An existing event that never had a review must not gain one on a
    # non-authoritative rewrite, even when create_review=True.
    no_review_event = build_event(
        "event-no-review",
        outcome=outcome_payload("valid"),
        claims=[],
        narratives=[],
        evidence=[evidence_payload(evidence_id="evidence-2")],
    )
    assert (
        store_event_in_db(
            no_review_event, case_id="case-1", create_review=False
        )
        is True
    )
    assert read_review(tmp_path, "event-no-review") is None

    no_review_rewrite = build_event(
        "event-no-review",
        outcome=outcome_payload("unavailable", reason="source_unavailable"),
        claims=[],
        narratives=[],
        evidence=[evidence_payload(evidence_id="evidence-2")],
    )
    assert (
        store_event_in_db(
            no_review_rewrite, case_id="case-1", create_review=True
        )
        is True
    )
    assert read_review(tmp_path, "event-no-review") is None
