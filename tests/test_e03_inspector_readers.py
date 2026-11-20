"""E03: typed inspector read models (citation/claim/evidence/capture GETs).

Covers the specification §4 "User interaction"/"Quotation and relationship
contract" and §9 "Proposed GET contracts" contract for the read-only inspector:

* every alignment state (``exact``, ``ambiguous``, ``no_match``,
  ``not_provided``, ``source_unavailable``) plus an unassessed legacy link is
  served by both the claim and the evidence reader, with the policy-derived
  ``effectiveRelation`` (only ``exact`` + trusted collector is ``reported_by``;
  a legacy raw ``opposes``/``supports`` without provenance stays ``uncertain``);
* a citation resolves from its own frozen data after the live claim/link are
  deleted, and reports ``liveClaimPresent``;
* capture windows are code-point based, bounded, EOF-truncating and explicit
  about returned versus total length;
* status mapping: missing/wrong-case/dangling resources -> 404, malformed range
  or unsupported snapshot selector -> 422;
* case-level payloads never carry capture text, and GET creates nothing.

All databases are temporary; no provider/network/model call is made.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import json
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from src.cases.readers import (
    CaptureRangeError,
    read_capture_window,
    read_citation,
    read_claim_detail,
    read_evidence_detail,
)
from src.cases.service import TopicCaseService, _claim_signature
from src.http.app import app
from src.http.dependencies import get_case_service
from src.http.mappers import map_capture_window, map_claim_detail, map_evidence_detail
from src.storage import (
    CaseStatus,
    Claim,
    ClaimCitation,
    ClaimEvidenceLink,
    EvidenceCapture,
    EvidenceItem,
    Event,
    FactAllegationType,
    TopicCase,
    VerificationStatus,
    get_database,
    init_database,
)
from src.storage.captures import compute_text_sha256, record_evidence_capture
from src.storage.citations import (
    AnalysisScope,
    QuoteProposal,
    record_claim_citation,
)
from tests.fixtures.evidence_workbench import (
    CENTRAL_CLAIM,
    CENTRAL_QUOTE,
    REVISED_BODY_A,
    SOURCE_A,
    SOURCE_B,
    SOURCE_C,
    SOURCE_D,
    SOURCE_E,
)

CASE_ID = "case-e03"
OTHER_CASE_ID = "case-e03-other"
EVENT_ID = "event-e03"
OTHER_EVENT_ID = "event-e03-other"

# A body with one exact quotation occurring twice: the honest outcome is
# ``ambiguous`` because no disambiguating offsets were supplied.
REPEATED_BODY = (
    "Repeated passage here. Unrelated intervening text. "
    "Repeated passage here."
)
REPEATED_QUOTE = "Repeated passage here."

LEGACY_EVIDENCE_BODY = (
    "Legacy stored body that predates immutable captures and was never "
    "materialized."
)

OBSERVED_A = datetime(2026, 3, 3, 6, 25, tzinfo=UTC)
OBSERVED_A_REVISED = datetime(2026, 3, 4, 8, 15, tzinfo=UTC)

#: Alignment state -> expected policy relationship for the seeded fixtures.
EXPECTED_EFFECTIVE_RELATION = {
    "exact": "reported_by",
    "assessed_supports": "supports",
    "ambiguous": "uncertain",
    "no_match": "uncertain",
    "not_provided": "uncertain",
    "source_unavailable": "uncertain",
    "legacy": "uncertain",
}


@dataclass(frozen=True)
class Workbench:
    """IDs and bodies created by :func:`seed_workbench` (no ORM objects)."""

    case_id: str
    other_case_id: str
    claim_id: str
    legacy_claim_id: str
    other_claim_id: str
    evidence: dict[str, str]
    captures: dict[str, str]
    citations: dict[str, str]
    body_a: str
    body_a_revised: str
    body_repeated: str
    body_legacy: str


def db_session():
    """Open a session against the temporary database created by the fixture."""
    return get_database().get_session_sync()


def _scope(body: str, *, body_sha256: str | None = None) -> AnalysisScope:
    return AnalysisScope(
        start_char=0,
        end_char=len(body),
        body_sha256=body_sha256 if body_sha256 is not None else compute_text_sha256(body),
    )


def _add_evidence(
    session,
    *,
    evidence_id: str,
    source,
    body: str,
    observed_at: datetime,
) -> tuple[EvidenceItem, EvidenceCapture | None]:
    evidence = EvidenceItem(
        id=evidence_id,
        case_id=CASE_ID,
        event_id=EVENT_ID,
        evidence_type="article",
        source_type="rss",
        title=source.title,
        origin_url=source.origin_url,
        canonical_url=source.canonical_url,
        publisher=source.publisher,
        published_at=source.published_at,
        capture_metadata={"source_type": "rss"},
        verification_status="UNVERIFIED",
        credibility_tier="high",
        requires_human_review=0,
    )
    session.add(evidence)
    session.flush()
    capture = record_evidence_capture(
        session,
        evidence,
        text=body,
        observed_at=observed_at,
        metadata=source.capture_kwargs(),
    )
    return evidence, capture


def _attach(
    session,
    *,
    link_id: str,
    claim: Claim,
    evidence: EvidenceItem,
    capture: EvidenceCapture,
    proposal: QuoteProposal | None,
    scope: AnalysisScope | None,
    stored_relation: str,
    assessment_origin: str | None = None,
    assessment_version: str | None = None,
    collector_generated: bool = False,
) -> tuple[ClaimEvidenceLink, ClaimCitation | None]:
    """Attach one evidence link through the real citation writer.

    Mirrors ``event_store._link_semantics``: only an exact, policy-eligible
    passage becomes an immutable citation; every other state is a diagnostic on
    the link. The link stores the policy-resolved relation plus the frozen
    provenance, exactly like the E02 writer.
    """
    result = record_claim_citation(
        session,
        case_id=CASE_ID,
        # Classic ``Column[...]`` declarations type ORM attributes as descriptors;
        # at runtime these are the stored strings, so narrow explicitly here
        # rather than weakening the domain contract.
        capture_id=cast(str, capture.id),
        claim_signature=cast("str | None", claim.claim_signature),
        claim_text=cast(str, claim.claim_text),
        scope=scope,
        proposal=proposal,
        evidence_id=cast(str, evidence.id),
        original_claim_id=cast(str, claim.id),
        stored_relation=stored_relation,
        assessment_origin=assessment_origin,
        assessment_version=assessment_version,
        collector_generated=collector_generated,
    )
    alignment = result.alignment
    citation = result.citation
    exact = alignment.is_exact
    metadata: dict[str, object] = {
        "alignment_version": alignment.alignment_version,
        "relationship_policy": result.relationship.policy_version,
        "stored_relation": stored_relation,
    }
    if not exact:
        metadata["diagnostic_reason"] = alignment.diagnostic_reason
    link = ClaimEvidenceLink(
        id=link_id,
        claim_id=claim.id,
        evidence_id=evidence.id,
        relation=result.relationship.effective_relationship,
        source_diversity_rank=1,
        confidence_score=0.4,
        capture_id=capture.id,
        citation_id=citation.id if citation is not None else None,
        quote=alignment.quote if exact else None,
        start_char=alignment.start_char if exact else None,
        end_char=alignment.end_char if exact else None,
        alignment_status=alignment.status,
        assessment_origin=(
            citation.assessment_origin if citation is not None else assessment_origin
        ),
        assessment_version=(
            citation.assessment_version if citation is not None else assessment_version
        ),
        assessment_metadata=metadata,
    )
    session.add(link)
    session.flush()
    return link, citation


def seed_workbench() -> Workbench:
    """Create one synthetic case covering every alignment state.

    One claim carries one link per alignment state (each to a distinct evidence
    item), a second claim holds the unassessed legacy link, and a third claim
    belongs to another case so every wrong-case path can be exercised.
    """
    session = db_session()
    try:
        session.add(
            TopicCase(
                id=CASE_ID,
                query="Port Alden evacuation order",
                slug="port-alden-e03",
                conflict="Civic response",
                status=CaseStatus.REVIEW_READY,
                metadata_json={},
            )
        )
        session.add(
            TopicCase(
                id=OTHER_CASE_ID,
                query="Unrelated case",
                slug="unrelated-e03",
                conflict="Other",
                status=CaseStatus.REVIEW_READY,
                metadata_json={},
            )
        )
        session.add(
            Event(
                id=EVENT_ID,
                timestamp=datetime(2026, 3, 3, 6, 30, tzinfo=UTC),
                title="Port Alden briefing",
                verification_status=VerificationStatus.ALLEGED,
                case_id=CASE_ID,
            )
        )
        session.add(
            Event(
                id=OTHER_EVENT_ID,
                timestamp=datetime(2026, 3, 3, 7, 0, tzinfo=UTC),
                title="Other case event",
                verification_status=VerificationStatus.ALLEGED,
                case_id=OTHER_CASE_ID,
            )
        )
        session.flush()

        claim = Claim(
            id="claim-e03",
            event_id=EVENT_ID,
            claim_text=CENTRAL_CLAIM,
            verification_status=VerificationStatus.ALLEGED,
            fact_allegation_type=FactAllegationType.ALLEGATION,
            claim_signature=_claim_signature(CENTRAL_CLAIM),
            support_count=1,
            oppose_count=0,
            source_diversity_count=6,
            party_positions={"Port Alden Authority": "CONTESTED"},
            controversy_score=0.42,
        )
        legacy_claim = Claim(
            id="claim-e03-legacy",
            event_id=EVENT_ID,
            claim_text="A legacy assertion stored before quotations existed.",
            verification_status=VerificationStatus.CONFIRMED,
            fact_allegation_type=FactAllegationType.FACT,
            claim_signature=_claim_signature(
                "A legacy assertion stored before quotations existed."
            ),
        )
        other_claim = Claim(
            id="claim-other-case",
            event_id=OTHER_EVENT_ID,
            claim_text="A claim belonging to another case.",
            verification_status=VerificationStatus.ALLEGED,
            fact_allegation_type=FactAllegationType.ALLEGATION,
            claim_signature=_claim_signature("A claim belonging to another case."),
        )
        session.add_all([claim, legacy_claim, other_claim])
        session.flush()

        evidence_a, capture_a = _add_evidence(
            session, evidence_id="ev-exact", source=SOURCE_A, body=SOURCE_A.body or "",
            observed_at=OBSERVED_A,
        )
        evidence_b, capture_b = _add_evidence(
            session, evidence_id="ev-assessed", source=SOURCE_B, body=SOURCE_B.body or "",
            observed_at=OBSERVED_A,
        )
        evidence_c, capture_c = _add_evidence(
            session, evidence_id="ev-not-provided", source=SOURCE_C,
            body=SOURCE_C.body or "", observed_at=OBSERVED_A,
        )
        evidence_d, capture_d = _add_evidence(
            session, evidence_id="ev-no-match", source=SOURCE_D, body=SOURCE_D.body or "",
            observed_at=OBSERVED_A,
        )
        evidence_e, capture_e = _add_evidence(
            session, evidence_id="ev-source-unavailable", source=SOURCE_E,
            body=SOURCE_E.body or "", observed_at=OBSERVED_A,
        )
        evidence_repeat, capture_repeat = _add_evidence(
            session, evidence_id="ev-ambiguous", source=SOURCE_D,
            body=REPEATED_BODY, observed_at=OBSERVED_A,
        )
        # A changed source creates a second immutable capture version and moves
        # the current-capture pointer; the older capture stays readable.
        capture_a_revised = record_evidence_capture(
            session,
            evidence_a,
            text=REVISED_BODY_A,
            observed_at=OBSERVED_A_REVISED,
            metadata=SOURCE_A.capture_kwargs(),
        )
        # Legacy evidence: a stored body with no capture and no materialization.
        legacy_evidence = EvidenceItem(
            id="ev-legacy",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            evidence_type="article",
            source_type="rss",
            title="Legacy source without captures",
            origin_url="https://legacy.example.com/port-alden",
            publisher="Legacy Desk",
            content=LEGACY_EVIDENCE_BODY,
            capture_metadata={},
            verification_status="UNVERIFIED",
            credibility_tier="unknown",
            requires_human_review=0,
        )
        session.add(legacy_evidence)
        session.flush()

        assert capture_a is not None
        assert capture_b is not None
        assert capture_c is not None
        assert capture_d is not None
        assert capture_e is not None
        assert capture_repeat is not None
        assert capture_a_revised is not None

        _, citation_exact = _attach(
            session,
            link_id="link-exact",
            claim=claim,
            evidence=evidence_a,
            capture=capture_a,
            proposal=QuoteProposal(quote=CENTRAL_QUOTE),
            scope=_scope(SOURCE_A.body or ""),
            stored_relation="supports",
            collector_generated=True,
        )
        _, citation_assessed = _attach(
            session,
            link_id="link-assessed",
            claim=claim,
            evidence=evidence_b,
            capture=capture_b,
            proposal=QuoteProposal(quote=CENTRAL_QUOTE),
            scope=_scope(SOURCE_B.body or ""),
            stored_relation="supports",
            assessment_origin="human",
            assessment_version="v1",
        )
        _attach(
            session,
            link_id="link-ambiguous",
            claim=claim,
            evidence=evidence_repeat,
            capture=capture_repeat,
            proposal=QuoteProposal(quote=REPEATED_QUOTE),
            scope=_scope(REPEATED_BODY),
            stored_relation="supports",
            collector_generated=True,
        )
        _attach(
            session,
            link_id="link-no-match",
            claim=claim,
            evidence=evidence_d,
            capture=capture_d,
            proposal=QuoteProposal(quote=CENTRAL_QUOTE),
            scope=_scope(SOURCE_D.body or ""),
            stored_relation="supports",
            collector_generated=True,
        )
        _attach(
            session,
            link_id="link-not-provided",
            claim=claim,
            evidence=evidence_c,
            capture=capture_c,
            proposal=None,
            scope=_scope(SOURCE_C.body or ""),
            stored_relation="supports",
            collector_generated=True,
        )
        _attach(
            session,
            link_id="link-source-unavailable",
            claim=claim,
            evidence=evidence_e,
            capture=capture_e,
            proposal=QuoteProposal(quote=CENTRAL_QUOTE),
            scope=_scope(SOURCE_E.body or "", body_sha256="0" * 64),
            stored_relation="supports",
            collector_generated=True,
        )
        # Unassessed legacy link: raw ``opposes``, no capture, no citation and no
        # writer-generated metadata. It must never become support.
        session.add(
            ClaimEvidenceLink(
                id="link-legacy",
                claim_id=legacy_claim.id,
                evidence_id=legacy_evidence.id,
                relation="opposes",
                source_diversity_rank=1,
                confidence_score=0.8,
            )
        )
        session.commit()
    finally:
        session.close()

    assert citation_exact is not None
    assert citation_assessed is not None
    return Workbench(
        case_id=CASE_ID,
        other_case_id=OTHER_CASE_ID,
        claim_id="claim-e03",
        legacy_claim_id="claim-e03-legacy",
        other_claim_id="claim-other-case",
        evidence={
            "exact": "ev-exact",
            "assessed_supports": "ev-assessed",
            "ambiguous": "ev-ambiguous",
            "no_match": "ev-no-match",
            "not_provided": "ev-not-provided",
            "source_unavailable": "ev-source-unavailable",
            "legacy": "ev-legacy",
        },
        captures={
            "a_old": str(capture_a.id),
            "a_revised": str(capture_a_revised.id),
            "b": str(capture_b.id),
        },
        citations={
            "exact": str(citation_exact.id),
            "assessed": str(citation_assessed.id),
        },
        body_a=SOURCE_A.body or "",
        body_a_revised=REVISED_BODY_A,
        body_repeated=REPEATED_BODY,
        body_legacy=LEGACY_EVIDENCE_BODY,
    )


@pytest.fixture
def workbench(tmp_path) -> Workbench:
    init_database(str(tmp_path / "e03-inspector.sqlite3"))
    return seed_workbench()


@pytest.fixture
def client(workbench, tmp_path) -> Iterator[TestClient]:
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
    app.dependency_overrides[get_case_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def row_counts() -> dict[str, int]:
    session = db_session()
    try:
        return {
            "captures": int(
                session.scalar(
                    select(func.count()).select_from(EvidenceCapture)
                )
                or 0
            ),
            "citations": int(
                session.scalar(select(func.count()).select_from(ClaimCitation)) or 0
            ),
            "claims": int(
                session.scalar(select(func.count()).select_from(Claim)) or 0
            ),
            "evidence": int(
                session.scalar(select(func.count()).select_from(EvidenceItem)) or 0
            ),
            "links": int(
                session.scalar(
                    select(func.count()).select_from(ClaimEvidenceLink)
                )
                or 0
            ),
        }
    finally:
        session.close()


def analysis_snapshot() -> dict[str, Any]:
    session = db_session()
    try:
        claims = {
            claim.id: (
                claim.support_count,
                claim.oppose_count,
                claim.source_diversity_count,
                claim.claim_signature,
                claim.verification_status.value,
            )
            for claim in session.scalars(select(Claim)).all()
        }
        evidence = {
            item.id: (item.content, item.current_capture_id)
            for item in session.scalars(select(EvidenceItem)).all()
        }
        return {"claims": claims, "evidence": evidence}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Claim reader: every alignment state with the policy-derived relationship
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", sorted(EXPECTED_EFFECTIVE_RELATION))
def test_claim_and_evidence_readers_expose_every_alignment_state(
    workbench: Workbench, state: str
) -> None:
    expected_relation = EXPECTED_EFFECTIVE_RELATION[state]
    expected_alignment = {
        "exact": "exact",
        "assessed_supports": "exact",
        "ambiguous": "ambiguous",
        "no_match": "no_match",
        "not_provided": "not_provided",
        "source_unavailable": "source_unavailable",
        "legacy": "not_provided",
    }[state]

    session = db_session()
    try:
        claim_id = (
            workbench.legacy_claim_id if state == "legacy" else workbench.claim_id
        )
        claim_payload = read_claim_detail(
            session, case_id=workbench.case_id, claim_id=claim_id
        )
        assert claim_payload is not None
        evidence_id = workbench.evidence[state]
        passage = next(
            item for item in claim_payload["passages"] if item["evidence_id"] == evidence_id
        )
        assert passage["alignment_status"] == expected_alignment
        assert passage["effective_relation"] == expected_relation
        if expected_relation == "uncertain":
            assert passage["effective_relation"] != "supports"

        evidence_payload = read_evidence_detail(
            session, case_id=workbench.case_id, evidence_id=evidence_id
        )
        assert evidence_payload is not None
        reference = next(
            item
            for item in evidence_payload["related_claims"]
            if item["claim_id"] == claim_id
        )
        assert reference["alignment_status"] == expected_alignment
        assert reference["effective_relation"] == expected_relation
    finally:
        session.close()


def test_legacy_opposes_is_preserved_raw_and_never_becomes_support(
    workbench: Workbench,
) -> None:
    session = db_session()
    try:
        payload = read_claim_detail(
            session, case_id=workbench.case_id, claim_id=workbench.legacy_claim_id
        )
    finally:
        session.close()

    assert payload is not None
    passage = payload["passages"][0]
    # The raw stored value is kept verbatim for diagnostics ...
    assert passage["relation"] == "opposes"
    # ... but an unprovenanced legacy row is never counted as support/opposition.
    assert passage["effective_relation"] == "uncertain"
    assert passage["citation_id"] is None
    assert passage["capture_id"] is None
    assert passage["quote"] is None
    assert passage["start_char"] is None
    # Positive evidence of a pre-quotation row, and no invented actor.
    assert payload["verification_provenance"] == "legacy_unknown"


def test_exact_collector_passage_is_reported_by_with_frozen_reference(
    workbench: Workbench,
) -> None:
    session = db_session()
    try:
        payload = read_claim_detail(
            session, case_id=workbench.case_id, claim_id=workbench.claim_id
        )
    finally:
        session.close()

    assert payload is not None
    exact = next(
        item
        for item in payload["passages"]
        if item["evidence_id"] == workbench.evidence["exact"]
    )
    # ``relation`` is the stored value: the E02 writer stores the policy-resolved
    # relationship and keeps the original raw proposal in
    # ``assessment_metadata["stored_relation"]``. An unassessed legacy row (see
    # the legacy test below) instead keeps its verbatim raw value.
    assert exact["relation"] == "reported_by"
    assert exact["effective_relation"] == "reported_by"
    assert exact["alignment_status"] == "exact"
    assert exact["quote"] == CENTRAL_QUOTE
    assert workbench.body_a[exact["start_char"] : exact["end_char"]] == CENTRAL_QUOTE
    assert exact["capture_id"] == workbench.captures["a_old"]
    assert exact["citation_id"] == workbench.citations["exact"]
    assert exact["assessment_origin"] == "collector"


def test_explicitly_assessed_passage_keeps_assessment_provenance(
    workbench: Workbench,
) -> None:
    session = db_session()
    try:
        payload = read_claim_detail(
            session, case_id=workbench.case_id, claim_id=workbench.claim_id
        )
    finally:
        session.close()

    assert payload is not None
    assessed = next(
        item
        for item in payload["passages"]
        if item["evidence_id"] == workbench.evidence["assessed_supports"]
    )
    assert assessed["effective_relation"] == "supports"
    assert assessed["assessment_origin"] == "human"
    assert assessed["assessment_version"] == "v1"
    assert assessed["citation_id"] == workbench.citations["assessed"]


def test_invalid_proposals_stay_diagnostics_with_reasons(workbench: Workbench) -> None:
    session = db_session()
    try:
        payload = read_claim_detail(
            session, case_id=workbench.case_id, claim_id=workbench.claim_id
        )
    finally:
        session.close()

    assert payload is not None
    by_evidence = {item["evidence_id"]: item for item in payload["passages"]}
    assert (
        by_evidence[workbench.evidence["ambiguous"]]["diagnostic_reason"]
        == "repeated_exact_occurrence"
    )
    assert (
        by_evidence[workbench.evidence["no_match"]]["diagnostic_reason"]
        == "no_exact_occurrence_in_scope"
    )
    assert (
        by_evidence[workbench.evidence["not_provided"]]["diagnostic_reason"]
        == "quote_missing"
    )
    assert (
        by_evidence[workbench.evidence["source_unavailable"]]["diagnostic_reason"]
        == "body_sha256_mismatch"
    )
    for state in ("ambiguous", "no_match", "not_provided", "source_unavailable"):
        passage = by_evidence[workbench.evidence[state]]
        assert passage["citation_id"] is None
        assert passage["quote"] is None


def test_claim_detail_reports_stored_counts_and_metadata(workbench: Workbench) -> None:
    session = db_session()
    try:
        payload = read_claim_detail(
            session, case_id=workbench.case_id, claim_id=workbench.claim_id
        )
    finally:
        session.close()

    assert payload is not None
    assert payload["claim_text"] == CENTRAL_CLAIM
    assert payload["claim_signature"] == _claim_signature(CENTRAL_CLAIM)
    assert payload["controversy_score"] == pytest.approx(0.42)
    assert payload["party_positions"] == {"Port Alden Authority": "CONTESTED"}
    assert payload["counts"] == {
        "support_count": 1,
        "oppose_count": 0,
        "source_diversity_count": 6,
        "evidence_count": len(payload["passages"]),
    }
    # No provenance column exists, and this claim has E02-written attachments.
    assert payload["verification_provenance"] == "unknown"


def test_claim_detail_unknown_and_wrong_case_are_not_found(workbench: Workbench) -> None:
    session = db_session()
    try:
        assert (
            read_claim_detail(
                session, case_id=workbench.case_id, claim_id="claim-missing"
            )
            is None
        )
        # A real claim, but read under the wrong case.
        assert (
            read_claim_detail(
                session, case_id=workbench.other_case_id, claim_id=workbench.claim_id
            )
            is None
        )
        assert (
            read_claim_detail(
                session, case_id=workbench.case_id, claim_id=workbench.other_claim_id
            )
            is None
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Evidence reader
# ---------------------------------------------------------------------------


def test_evidence_detail_lists_ordered_captures_without_bodies(
    workbench: Workbench,
) -> None:
    session = db_session()
    try:
        payload = read_evidence_detail(
            session, case_id=workbench.case_id, evidence_id=workbench.evidence["exact"]
        )
    finally:
        session.close()

    assert payload is not None
    ids = [capture["id"] for capture in payload["captures"]]
    assert ids == [workbench.captures["a_old"], workbench.captures["a_revised"]]
    assert payload["current_capture_id"] == workbench.captures["a_revised"]

    old, revised = payload["captures"]
    assert old["is_current"] is False
    assert revised["is_current"] is True
    assert old["char_length"] == len(workbench.body_a)
    assert revised["char_length"] == len(workbench.body_a_revised)
    assert old["capture_kind"] == "live"
    assert old["text_sha256"] == compute_text_sha256(workbench.body_a)
    assert old["normalized_text_sha256"]
    assert old["normalization_version"] == "v1"
    assert old["metadata"]["publisher"] == SOURCE_A.publisher
    # Stored timestamps are reported as persisted (SQLite drops the tzinfo), not
    # rewritten with an invented offset.
    assert old["recorded_at"] is not None
    assert datetime.fromisoformat(old["recorded_at"]).year == datetime.now(UTC).year

    serialized = json.dumps(payload)
    # Only ids/hashes/kinds/times/metadata/char lengths -- never the bodies.
    assert workbench.body_a not in serialized
    assert workbench.body_a_revised not in serialized
    for capture in payload["captures"]:
        assert set(capture) == {
            "id",
            "evidence_id",
            "text_sha256",
            "normalized_text_sha256",
            "normalization_version",
            "capture_kind",
            "recorded_at",
            "observed_at",
            "metadata",
            "char_length",
            "is_current",
        }
        assert "text" not in capture


def test_evidence_detail_related_claims_carry_passages_not_text(
    workbench: Workbench,
) -> None:
    session = db_session()
    try:
        payload = read_evidence_detail(
            session,
            case_id=workbench.case_id,
            evidence_id=workbench.evidence["source_unavailable"],
        )
    finally:
        session.close()

    assert payload is not None
    assert len(payload["related_claims"]) == 1
    reference = payload["related_claims"][0]
    assert reference["claim_id"] == workbench.claim_id
    assert reference["claim_text"] == CENTRAL_CLAIM
    assert reference["alignment_status"] == "source_unavailable"
    assert reference["effective_relation"] == "uncertain"
    assert reference["citation_id"] is None
    assert reference["quote"] is None
    assert reference["link_id"] == "link-source-unavailable"
    assert (SOURCE_E.body or "") not in json.dumps(payload)


def test_evidence_detail_for_legacy_source_has_no_captures(
    workbench: Workbench,
) -> None:
    session = db_session()
    try:
        payload = read_evidence_detail(
            session, case_id=workbench.case_id, evidence_id=workbench.evidence["legacy"]
        )
    finally:
        session.close()

    assert payload is not None
    assert payload["captures"] == []
    assert payload["current_capture_id"] is None
    # A GET never materializes legacy content into a capture.
    session = db_session()
    try:
        assert (
            session.scalar(
                select(func.count())
                .select_from(EvidenceCapture)
                .where(EvidenceCapture.evidence_id == workbench.evidence["legacy"])
            )
            or 0
        ) == 0
    finally:
        session.close()
    assert workbench.body_legacy not in json.dumps(payload)


def test_evidence_detail_unknown_and_wrong_case_are_not_found(
    workbench: Workbench,
) -> None:
    session = db_session()
    try:
        assert (
            read_evidence_detail(
                session, case_id=workbench.case_id, evidence_id="ev-missing"
            )
            is None
        )
        assert (
            read_evidence_detail(
                session,
                case_id=workbench.other_case_id,
                evidence_id=workbench.evidence["exact"],
            )
            is None
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Citation reader
# ---------------------------------------------------------------------------


def test_citation_reader_serves_frozen_data_without_a_live_claim(
    workbench: Workbench,
) -> None:
    session = db_session()
    try:
        live = read_citation(
            session, case_id=workbench.case_id, citation_id=workbench.citations["exact"]
        )
        assert live is not None
        assert live["live_claim_present"] is True
        assert live["live_claim_id"] == workbench.claim_id

        # Remove the live claim and its links; the citation (and its capture)
        # must remain resolvable.
        for link in session.scalars(
            select(ClaimEvidenceLink).where(
                ClaimEvidenceLink.claim_id == workbench.claim_id
            )
        ).all():
            session.delete(link)
        session.flush()
        session.execute(delete(Claim).where(Claim.id == workbench.claim_id))
        session.commit()

        frozen = read_citation(
            session, case_id=workbench.case_id, citation_id=workbench.citations["exact"]
        )
    finally:
        session.close()

    assert frozen is not None
    assert frozen["live_claim_present"] is False
    assert frozen["live_claim_id"] is None
    assert frozen["original_claim_id"] == workbench.claim_id
    assert frozen["claim_text"] == CENTRAL_CLAIM
    assert frozen["claim_signature"] == _claim_signature(CENTRAL_CLAIM)
    assert frozen["relationship"] == "reported_by"
    assert frozen["quote"] == CENTRAL_QUOTE
    assert workbench.body_a[frozen["start_char"] : frozen["end_char"]] == CENTRAL_QUOTE
    assert frozen["alignment_status"] == "exact"
    assert frozen["assessment_origin"] == "collector"
    assert frozen["capture_id"] == workbench.captures["a_old"]
    assert frozen["evidence_id"] == workbench.evidence["exact"]

    capture = frozen["capture"]
    assert capture is not None
    assert capture["id"] == workbench.captures["a_old"]
    assert capture["text_sha256"] == compute_text_sha256(workbench.body_a)
    # The evidence now points at the newer capture version.
    assert capture["is_current"] is False
    assert workbench.body_a not in json.dumps(frozen)

    evidence = frozen["evidence"]
    assert evidence is not None
    assert evidence["title"] == SOURCE_A.title
    assert evidence["publisher"] == SOURCE_A.publisher
    assert evidence["canonical_url"] == SOURCE_A.canonical_url


def test_citation_reader_reports_assessed_provenance(workbench: Workbench) -> None:
    session = db_session()
    try:
        payload = read_citation(
            session,
            case_id=workbench.case_id,
            citation_id=workbench.citations["assessed"],
        )
    finally:
        session.close()

    assert payload is not None
    assert payload["relationship"] == "supports"
    assert payload["assessment_origin"] == "human"
    assert payload["assessment_version"] == "v1"
    assert payload["alignment_version"] == "exact-codepoint-v1"
    assert "relationship" in payload["assessment_metadata"]


def test_citation_reader_unknown_and_wrong_case_are_not_found(
    workbench: Workbench,
) -> None:
    session = db_session()
    try:
        assert (
            read_citation(
                session, case_id=workbench.case_id, citation_id="citation-missing"
            )
            is None
        )
        # An existing citation never leaks through another case ID.
        assert (
            read_citation(
                session,
                case_id=workbench.other_case_id,
                citation_id=workbench.citations["exact"],
            )
            is None
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Capture window
# ---------------------------------------------------------------------------


def test_capture_window_uses_code_points_and_reports_lengths(
    workbench: Workbench,
) -> None:
    body = workbench.body_a
    emoji_index = body.index("🚨")
    start = emoji_index - 5
    length = 24

    session = db_session()
    try:
        window = read_capture_window(
            session,
            case_id=workbench.case_id,
            evidence_id=workbench.evidence["exact"],
            capture_id=workbench.captures["a_old"],
            start=start,
            length=length,
        )
    finally:
        session.close()

    assert window is not None
    # Python code points, not UTF-16 units or bytes.
    assert window["text"] == body[start : start + length]
    assert window["length"] == len(window["text"]) == length
    assert window["total_length"] == len(body)
    assert "🚨" in window["text"]
    assert window["start"] == start
    assert window["text_sha256"] == compute_text_sha256(body)
    assert window["capture_kind"] == "live"
    assert window["metadata"]["title"] == SOURCE_A.title


def test_capture_window_covers_cjk_and_combining_characters(
    workbench: Workbench,
) -> None:
    body = workbench.body_a
    cjk_index = body.index("港口管理局")
    session = db_session()
    try:
        window = read_capture_window(
            session,
            case_id=workbench.case_id,
            evidence_id=workbench.evidence["exact"],
            capture_id=workbench.captures["a_old"],
            start=cjk_index,
            length=5,
        )
    finally:
        session.close()

    assert window is not None
    assert window["text"] == "港口管理局"
    assert window["length"] == 5


def test_capture_window_truncates_only_at_end_of_text(
    workbench: Workbench,
) -> None:
    body = workbench.body_a
    start = len(body) - 10
    session = db_session()
    try:
        window = read_capture_window(
            session,
            case_id=workbench.case_id,
            evidence_id=workbench.evidence["exact"],
            capture_id=workbench.captures["a_old"],
            start=start,
            length=5000,
        )
    finally:
        session.close()

    assert window is not None
    assert window["length"] == 10
    assert window["total_length"] == len(body)
    assert window["text"] == body[-10:]


def test_capture_window_full_capture_is_reachable_in_two_windows(
    workbench: Workbench,
) -> None:
    body = workbench.body_a
    split = 37
    session = db_session()
    try:
        first = read_capture_window(
            session,
            case_id=workbench.case_id,
            evidence_id=workbench.evidence["exact"],
            capture_id=workbench.captures["a_old"],
            start=0,
            length=split,
        )
        second = read_capture_window(
            session,
            case_id=workbench.case_id,
            evidence_id=workbench.evidence["exact"],
            capture_id=workbench.captures["a_old"],
            start=split,
            length=len(body) - split,
        )
    finally:
        session.close()

    assert first is not None and second is not None
    assert first["length"] == split
    assert second["length"] == len(body) - split
    assert first["text"] + second["text"] == body
    assert first["text"] == body[:split]
    assert second["text"] == body[split:]


def test_capture_window_at_total_length_is_empty_but_valid(
    workbench: Workbench,
) -> None:
    total = len(workbench.body_a)
    session = db_session()
    try:
        window = read_capture_window(
            session,
            case_id=workbench.case_id,
            evidence_id=workbench.evidence["exact"],
            capture_id=workbench.captures["a_old"],
            start=total,
            length=10,
        )
    finally:
        session.close()

    assert window is not None
    assert window["text"] == ""
    assert window["length"] == 0
    assert window["total_length"] == total
    assert window["start"] == total


@pytest.mark.parametrize(
    ("start", "length"),
    [
        (-1, 10),
        (10_000, 10),  # beyond total_length
        (0, 0),
        (0, 50001),
        (0, -5),
    ],
)
def test_capture_window_rejects_malformed_ranges(
    workbench: Workbench, start: int, length: int
) -> None:
    session = db_session()
    try:
        with pytest.raises(CaptureRangeError):
            read_capture_window(
                session,
                case_id=workbench.case_id,
                evidence_id=workbench.evidence["exact"],
                capture_id=workbench.captures["a_old"],
                start=start,
                length=length,
            )
    finally:
        session.close()


@pytest.mark.parametrize(("start", "length"), [("0", 10), (0, "abc"), (True, 5)])
def test_capture_window_rejects_non_integer_ranges(
    workbench: Workbench, start, length
) -> None:
    session = db_session()
    try:
        with pytest.raises(CaptureRangeError):
            read_capture_window(
                session,
                case_id=workbench.case_id,
                evidence_id=workbench.evidence["exact"],
                capture_id=workbench.captures["a_old"],
                start=start,
                length=length,
            )
    finally:
        session.close()


def test_capture_window_validates_case_and_evidence_ownership(
    workbench: Workbench,
) -> None:
    session = db_session()
    try:
        # Unknown capture ID.
        assert (
            read_capture_window(
                session,
                case_id=workbench.case_id,
                evidence_id=workbench.evidence["exact"],
                capture_id="capture-missing",
                start=0,
                length=10,
            )
            is None
        )
        # Existing capture, but addressed through a different evidence item.
        assert (
            read_capture_window(
                session,
                case_id=workbench.case_id,
                evidence_id=workbench.evidence["no_match"],
                capture_id=workbench.captures["a_old"],
                start=0,
                length=10,
            )
            is None
        )
        # Existing evidence/capture, but under a different case.
        assert (
            read_capture_window(
                session,
                case_id=workbench.other_case_id,
                evidence_id=workbench.evidence["exact"],
                capture_id=workbench.captures["a_old"],
                start=0,
                length=10,
            )
            is None
        )
        # Unknown evidence ID.
        assert (
            read_capture_window(
                session,
                case_id=workbench.case_id,
                evidence_id="ev-missing",
                capture_id=workbench.captures["a_old"],
                start=0,
                length=10,
            )
            is None
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# HTTP contracts
# ---------------------------------------------------------------------------


def test_claim_routes_keep_static_overview_and_add_detail(
    client: TestClient, workbench: Workbench
) -> None:
    claims = client.get(f"/api/cases/{workbench.case_id}/claims")
    overview = client.get(f"/api/cases/{workbench.case_id}/claims/overview")
    detail = client.get(
        f"/api/cases/{workbench.case_id}/claims/{workbench.claim_id}"
    )

    assert claims.status_code == 200
    assert overview.status_code == 200
    assert overview.json()["claims"][0]["id"] in {
        workbench.claim_id,
        workbench.legacy_claim_id,
    }
    assert detail.status_code == 200

    payload = detail.json()
    assert payload["id"] == workbench.claim_id
    assert payload["caseId"] == workbench.case_id
    assert payload["claimSignature"] == _claim_signature(CENTRAL_CLAIM)
    assert payload["verificationProvenance"] == "unknown"
    assert payload["counts"]["evidenceCount"] == len(payload["passages"])
    exact = next(
        item
        for item in payload["passages"]
        if item["id"] == workbench.evidence["exact"]
    )
    assert exact["effectiveRelation"] == "reported_by"
    assert exact["alignmentStatus"] == "exact"
    assert exact["citationId"] == workbench.citations["exact"]
    assert exact["captureId"] == workbench.captures["a_old"]
    assert exact["startChar"] is not None and exact["endChar"] is not None


def test_evidence_detail_route_and_capture_window_route(
    client: TestClient, workbench: Workbench
) -> None:
    detail = client.get(
        f"/api/cases/{workbench.case_id}/evidence/{workbench.evidence['exact']}"
    )
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["currentCaptureId"] == workbench.captures["a_revised"]
    assert [item["id"] for item in payload["captures"]] == [
        workbench.captures["a_old"],
        workbench.captures["a_revised"],
    ]
    assert payload["captures"][0]["charLength"] == len(workbench.body_a)
    assert payload["captures"][0]["isCurrent"] is False
    assert workbench.body_a not in detail.text

    window = client.get(
        f"/api/cases/{workbench.case_id}/evidence/{workbench.evidence['exact']}"
        f"/captures/{workbench.captures['a_old']}",
        params={"start": 3, "length": 12},
    )
    assert window.status_code == 200
    body = window.json()
    assert body["text"] == workbench.body_a[3:15]
    assert body["start"] == 3
    assert body["length"] == 12
    assert body["totalLength"] == len(workbench.body_a)

    defaulted = client.get(
        f"/api/cases/{workbench.case_id}/evidence/{workbench.evidence['exact']}"
        f"/captures/{workbench.captures['a_old']}"
    )
    assert defaulted.status_code == 200
    assert defaulted.json()["start"] == 0
    assert defaulted.json()["length"] == len(workbench.body_a)


def test_citation_route_serves_frozen_passage(
    client: TestClient, workbench: Workbench
) -> None:
    response = client.get(
        f"/api/cases/{workbench.case_id}/citations/{workbench.citations['exact']}"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["claimText"] == CENTRAL_CLAIM
    assert payload["quote"] == CENTRAL_QUOTE
    assert payload["relationship"] == "reported_by"
    assert payload["liveClaimPresent"] is True
    assert payload["capture"]["id"] == workbench.captures["a_old"]
    assert payload["evidence"]["publisher"] == SOURCE_A.publisher
    assert workbench.body_a not in response.text


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ({"start": -1}, None),
        ({"start": 100_000}, "beyond the capture length"),
        ({"length": 0}, None),
        ({"length": 50001}, None),
        ({"start": "abc"}, None),
        ({"length": "abc"}, None),
        ({"start": 1.5}, None),
    ],
)
def test_capture_window_http_rejects_bad_ranges_with_422(
    client: TestClient, workbench: Workbench, query: dict, message: str | None
) -> None:
    path = (
        f"/api/cases/{workbench.case_id}/evidence/{workbench.evidence['exact']}"
        f"/captures/{workbench.captures['a_old']}"
    )
    response = client.get(path, params=query)
    assert response.status_code == 422
    if message is not None:
        assert message in response.text


@pytest.mark.parametrize("selector", ["snapshotId", "snapshot_id"])
@pytest.mark.parametrize("resource", ["claim", "evidence"])
def test_snapshot_aware_readers_resolve_or_404(
    client: TestClient, workbench: Workbench, selector: str, resource: str
) -> None:
    """Supported selectors are accepted and an unknown snapshot is a 404.

    A supplied selector must never silently fall back to the current rows, so an
    unresolvable snapshot ID resolves explicitly instead of returning live data.
    """
    path = {
        "claim": f"/api/cases/{workbench.case_id}/claims/{workbench.claim_id}",
        "evidence": (
            f"/api/cases/{workbench.case_id}/evidence/{workbench.evidence['exact']}"
        ),
    }[resource]
    response = client.get(path, params={selector: "snapshot-missing"})
    assert response.status_code == 404
    assert "Snapshot snapshot-missing not found" in response.text


@pytest.mark.parametrize("selector", ["snapshotId", "snapshot_id"])
@pytest.mark.parametrize(
    "path_template",
    [
        "/api/cases/{case_id}",
        "/api/cases/{case_id}/claims",
        "/api/cases/{case_id}/claims/overview",
        "/api/cases/{case_id}/evidence",
        "/api/cases/{case_id}/sources",
        "/api/cases/{case_id}/citations/{citation_id}",
        "/api/cases/{case_id}/parties",
        "/api/cases/{case_id}/timeline",
        "/api/cases/{case_id}/exceptions",
        "/api/cases/{case_id}/run-history",
        "/api/cases/{case_id}/report",
        "/api/cases/{case_id}/investigation-runs",
        "/api/cases/{case_id}/investigation-runs/run-x",
        "/api/cases/{case_id}/investigation-runs/run-x/changes",
        "/api/cases/{case_id}/snapshots/snap-x",
        (
            "/api/cases/{case_id}/evidence/{evidence_id}"
            "/captures/{capture_id}"
        ),
    ],
)
def test_current_state_readers_reject_snapshot_selectors(
    client: TestClient,
    workbench: Workbench,
    selector: str,
    path_template: str,
) -> None:
    """Unsupported current-state readers fail explicitly instead of ignoring it."""
    path = path_template.format(
        case_id=workbench.case_id,
        citation_id=workbench.citations["exact"],
        evidence_id=workbench.evidence["exact"],
        capture_id=workbench.captures["a_old"],
    )
    response = client.get(path, params={selector: "abc"})
    assert response.status_code == 422
    assert "does not support snapshot selection" in response.text


def test_http_404_for_unknown_and_cross_case_resources(
    client: TestClient, workbench: Workbench
) -> None:
    assert client.get("/api/cases/case-missing/claims/claim-e03").status_code == 404
    assert (
        client.get(
            f"/api/cases/{workbench.case_id}/claims/{workbench.other_claim_id}"
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/cases/{workbench.case_id}/claims/claim-missing").status_code
        == 404
    )
    assert (
        client.get(
            f"/api/cases/{workbench.case_id}/evidence/{workbench.evidence['exact']}"
        ).status_code
        == 200
    )
    assert (
        client.get(f"/api/cases/{workbench.case_id}/evidence/ev-missing").status_code
        == 404
    )
    assert (
        client.get(
            f"/api/cases/{workbench.other_case_id}"
            f"/evidence/{workbench.evidence['exact']}"
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/cases/{workbench.case_id}/citations/citation-missing"
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/cases/{workbench.other_case_id}"
            f"/citations/{workbench.citations['exact']}"
        ).status_code
        == 404
    )
    # A capture addressed through the wrong evidence item is a 404, not a 422.
    assert (
        client.get(
            f"/api/cases/{workbench.case_id}/evidence/{workbench.evidence['no_match']}"
            f"/captures/{workbench.captures['a_old']}"
        ).status_code
        == 404
    )


@pytest.mark.parametrize("path_suffix", ["claims/{claim}", "evidence/{evidence}"])
def test_case_level_payloads_never_include_capture_text(
    client: TestClient, workbench: Workbench, path_suffix: str
) -> None:
    paths = [
        f"/api/cases/{workbench.case_id}",
        f"/api/cases/{workbench.case_id}/claims",
        f"/api/cases/{workbench.case_id}/evidence",
        f"/api/cases/{workbench.case_id}/claims/overview",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        # Full stored bodies are never part of a case-level payload.
        assert workbench.body_a not in response.text
        assert workbench.body_a_revised not in response.text
        assert workbench.body_legacy not in response.text

    case_payload = client.get(f"/api/cases/{workbench.case_id}").json()
    evidence_entry = next(
        item
        for item in case_payload["tabs"]["evidence"]
        if item["id"] == workbench.evidence["exact"]
    )
    # Only the pointer is exposed; hashes/lengths appear in the detail reader.
    assert evidence_entry["currentCaptureId"] == workbench.captures["a_revised"]
    exact_claim = next(
        item for item in case_payload["tabs"]["claims"] if item["id"] == workbench.claim_id
    )
    exact_link = next(
        item
        for item in exact_claim["evidence"]
        if item["id"] == workbench.evidence["exact"]
    )
    assert exact_link["captureId"] == workbench.captures["a_old"]
    assert exact_link["citationId"] == workbench.citations["exact"]
    assert exact_link["alignmentStatus"] == "exact"
    assert exact_link["effectiveRelation"] == "reported_by"
    assert exact_link["relation"] == "reported_by"
    assert exact_link["quote"] == CENTRAL_QUOTE
    assert exact_link["diagnosticReason"] is None
    assert exact_claim["verificationProvenance"] == "unknown"

    ambiguous_link = next(
        item
        for item in exact_claim["evidence"]
        if item["id"] == workbench.evidence["ambiguous"]
    )
    assert ambiguous_link["effectiveRelation"] == "uncertain"
    assert ambiguous_link["diagnosticReason"] == "repeated_exact_occurrence"


def test_get_readers_create_no_rows_or_analysis_changes(
    client: TestClient, workbench: Workbench
) -> None:
    before_counts = row_counts()
    before_analysis = analysis_snapshot()

    responses = [
        client.get(f"/api/cases/{workbench.case_id}/claims/{workbench.claim_id}"),
        client.get(
            f"/api/cases/{workbench.case_id}/evidence/{workbench.evidence['legacy']}"
        ),
        client.get(
            f"/api/cases/{workbench.case_id}/evidence/{workbench.evidence['exact']}"
            f"/captures/{workbench.captures['a_old']}"
        ),
        client.get(
            f"/api/cases/{workbench.case_id}/citations/{workbench.citations['exact']}"
        ),
    ]
    assert [response.status_code for response in responses] == [200, 200, 200, 200]

    assert row_counts() == before_counts
    assert analysis_snapshot() == before_analysis
    # In particular, a legacy evidence item is not materialized by a read.
    session = db_session()
    try:
        legacy = session.scalars(
            select(EvidenceItem).where(
                EvidenceItem.id == workbench.evidence["legacy"]
            )
        ).first()
        assert legacy is not None
        # Runtime values (stored str/str|None); the descriptors are only a
        # static-typing artefact of classic ``Column[...]`` declarations.
        stored_capture_id: Any = legacy.current_capture_id
        stored_content: Any = legacy.content
        assert stored_capture_id is None
        assert stored_content == workbench.body_legacy
    finally:
        session.close()


@pytest.mark.parametrize(
    "path",
    [
        "/api/cases/{case}/citations/{citation}",
        "/api/cases/{case}/claims/{claim}",
        "/api/cases/{case}/evidence/{evidence}",
        "/api/cases/{case}/evidence/{evidence}/captures/{capture}",
    ],
)
def test_new_routes_reject_mutation_methods(
    client: TestClient, workbench: Workbench, path: str
) -> None:
    resolved = path.format(
        case=workbench.case_id,
        citation=workbench.citations["exact"],
        claim=workbench.claim_id,
        evidence=workbench.evidence["exact"],
        capture=workbench.captures["a_old"],
    )
    for method in ("post", "put", "delete", "patch"):
        response = getattr(client, method)(resolved)
        assert response.status_code in {404, 405}, (method, resolved)
    assert client.get(resolved).status_code == 200


def test_inspector_routes_are_get_only() -> None:
    """E03 inspector endpoints never mutate; review/annotation writes are separate.

    The merged application also exposes explicit review/annotation mutation
    routes (a different feature). E03's contract is that *inspector* GET paths
    stay read-only and create nothing, so those are asserted individually here.
    """
    inspector_paths = (
        "/api/cases/{case_id}/citations/{citation_id}",
        "/api/cases/{case_id}/claims/{claim_id}",
        "/api/cases/{case_id}/evidence/{evidence_id}",
        "/api/cases/{case_id}/evidence/{evidence_id}/captures/{capture_id}",
    )
    methods_by_path = {
        getattr(route, "path", ""): set(getattr(route, "methods", set()))
        for route in app.routes
    }
    for path in inspector_paths:
        assert path in methods_by_path, path
        assert methods_by_path[path] <= {"GET", "HEAD", "OPTIONS"}, path


# ---------------------------------------------------------------------------
# Legacy-safe DTO defaults
# ---------------------------------------------------------------------------


class LegacyStubService:
    """Service stub returning a pre-E03 payload (no new fields at all)."""

    def get_case_details(self, case_id: str):
        if case_id != "case-1":
            return None
        return {
            "case": {
                "id": "case-1",
                "query": "Legacy case",
                "conflict": "Global Trade",
                "status": "REVIEW_READY",
                "current_stage": "REPORT",
                "routing_mode": "autonomous",
                "report_path": None,
                "latest_manifest_path": None,
                "article_count": 1,
                "event_count": 1,
                "open_review_items": 0,
                "review_notes": None,
                "metadata": {},
                "updated_at": "2026-03-11T10:00:00+00:00",
            },
            "claims": [
                {
                    "id": "claim-1",
                    "event_id": "event-1",
                    "claim_text": "Legacy claim text",
                    "verification_status": "CONFIRMED",
                    "fact_allegation_type": "FACT",
                    "claim_signature": "sig-1",
                    "support_count": 1,
                    "oppose_count": 0,
                    "source_diversity_count": 1,
                    "party_positions": {},
                    "controversy_score": 0.2,
                    "evidence": [
                        {
                            "id": "evidence-1",
                            "relation": "supports",
                            "confidence_score": 0.9,
                            "source_diversity_rank": 1,
                            "title": "Legacy article",
                            "publisher": "Legacy Example",
                            "origin_url": "https://example.com/legacy",
                            "source_type": "rss",
                        }
                    ],
                }
            ],
            "evidence": [
                {
                    "id": "evidence-1",
                    "title": "Legacy article",
                    "origin_url": "https://example.com/legacy",
                    "canonical_url": "https://example.com/legacy",
                    "publisher": "Legacy Example",
                    "source_type": "rss",
                    "verification_status": "UNVERIFIED",
                    "credibility_tier": "unknown",
                    "requires_human_review": False,
                    "verification_checks": [],
                }
            ],
            "exceptions": [],
            "parties": [],
            "events": [],
            "stage_runs": [],
            "party_investigations": [],
        }


def test_legacy_case_payload_still_validates_with_honest_defaults() -> None:
    app.dependency_overrides[get_case_service] = lambda: LegacyStubService()
    try:
        response = TestClient(app).get("/api/cases/case-1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    claim = payload["tabs"]["claims"][0]
    assert claim["verificationProvenance"] == "unknown"
    link = claim["evidence"][0]
    assert link["relation"] == "supports"  # raw value preserved
    assert link["effectiveRelation"] == "uncertain"  # never invented support
    assert link["alignmentStatus"] == "not_provided"
    assert link["citationId"] is None
    assert link["captureId"] is None
    assert link["quote"] is None
    assert link["startChar"] is None
    assert link["endChar"] is None
    assert link["effectiveRelation"] != "reported_by"
    evidence = payload["tabs"]["evidence"][0]
    assert evidence["currentCaptureId"] is None

    # The claims list and claims-overview routes keep their legacy shape too.
    app.dependency_overrides[get_case_service] = lambda: LegacyStubService()
    try:
        client = TestClient(app)
        assert client.get("/api/cases/case-1/claims").status_code == 200
        assert client.get("/api/cases/case-1/claims/overview").status_code == 200
        assert client.get("/api/cases/case-1/evidence").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_minimal_claim_and_evidence_payloads_map_with_defaults() -> None:
    claim = map_claim_detail(
        {"id": "claim-min", "case_id": "case-min", "claim_text": "text"}
    )
    assert claim.verificationStatus == "unknown"
    assert claim.verificationProvenance == "unknown"
    assert claim.type == "allegation"
    assert claim.counts.supportCount == 0
    assert claim.counts.evidenceCount == 0
    assert claim.passages == []

    evidence = map_evidence_detail({"id": "evidence-min"})
    assert evidence.currentCaptureId is None
    assert evidence.captures == []
    assert evidence.relatedClaims == []
    assert evidence.verificationStatus == "unknown"

    window = map_capture_window(
        {
            "capture_id": "capture-min",
            "evidence_id": "evidence-min",
            "start": 0,
            "length": 0,
            "total_length": 0,
            "text": "",
        }
    )
    assert window.text == ""
    assert window.totalLength == 0
