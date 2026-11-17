"""E02 regression tests: exact-span validation and immutable claim citations.

Covers specification §4 quotation/citation semantics: the pure validator matrix,
the central versioned relationship policy (including the trusted-collector
priority, known assessment origins/version markers and fail-closed defaults),
deterministic citation identity/reuse, frozen assessment provenance, ownership
checks, caller-owned transactions with ``autoflush`` untouched, ORM append-only
guards and survival of live claim/link deletion.

All databases are ``tmp_path``/in-memory; no network, provider or model calls.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event as sqlalchemy_event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from src.cases.evidence import (
    normalize_capture_text,
    record_evidence_capture,
)
from src.storage import (
    Base,
    CaseStatus,
    Claim,
    ClaimCitation,
    ClaimEvidenceLink,
    EvidenceCapture,
    EvidenceItem,
    Event,
    TopicCase,
    VerificationStatus,
    init_database,
)
from src.storage.citations import (
    ALIGNMENT_VERSION,
    AnalysisScope,
    QuoteProposal,
    canonical_relationship,
    compute_quote_text_sha256,
    link_contribution,
    record_claim_citation,
    resolve_effective_relationship,
    validate_quote_alignment,
)
from src.storage.models import AlignmentStatus
from tests.fixtures.evidence_workbench import (
    CENTRAL_CLAIM,
    CENTRAL_QUOTE,
    LEGACY_WORKBENCH_SOURCES,
    REVISED_BODY_A,
    SOURCE_A,
    SOURCE_B,
    SOURCE_C,
    SOURCE_D,
    SOURCE_E,
    UNAVAILABLE,
    UNICODE_MARKERS,
    WORKBENCH_SOURCES,
)

EVENT_TS = datetime(2026, 3, 3, 6, 30, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def full_scope(body: str) -> AnalysisScope:
    return AnalysisScope(start_char=0, end_char=len(body))


def db_session(tmp_path) -> Session:
    db = init_database(str(tmp_path / "triangulate.db"))
    return db.get_session_sync()


def ensure_case(session: Session, case_id: str = "case-1") -> None:
    if session.query(TopicCase).filter(TopicCase.id == case_id).first() is None:
        session.add(
            TopicCase(
                id=case_id,
                query="Quotation case",
                slug=f"{case_id}-slug",
                status=CaseStatus.INVESTIGATING,
                metadata_json={},
            )
        )
        session.commit()


def add_evidence(
    session: Session, *, evidence_id: str, case_id: str = "case-1"
) -> EvidenceItem:
    evidence = EvidenceItem(
        id=evidence_id,
        case_id=case_id,
        evidence_type="article",
        source_type="rss",
        verification_status="UNVERIFIED",
    )
    session.add(evidence)
    session.flush([evidence])
    return evidence


def capture_source(
    tmp_path, *, case_id: str = "case-1", source=SOURCE_A, evidence_id="evidence-a"
):
    """Persist a case/evidence/capture triple and return (capture_id, body)."""
    session = db_session(tmp_path)
    try:
        ensure_case(session, case_id)
        evidence = add_evidence(session, evidence_id=evidence_id, case_id=case_id)
        capture = record_evidence_capture(
            session,
            evidence,
            text=source.body,
            metadata=source.capture_kwargs(),
        )
        session.commit()
        assert capture is not None
        return capture.id, capture.text
    finally:
        session.close()


def scratch_session(tmp_path, *, foreign_keys: bool = True):
    """Scratch engine/ORM session; FK enforcement only on this connection."""
    engine = create_engine(f"sqlite:///{tmp_path / 'scratch.db'}")
    if foreign_keys:

        @sqlalchemy_event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    Base.metadata.create_all(engine)
    session = sessionmaker(
        autocommit=False, autoflush=False, expire_on_commit=False, bind=engine
    )()
    return session, engine


def record(
    tmp_path,
    *,
    capture_id: str,
    case_id: str = "case-1",
    body: str | None = None,
    quote: str = CENTRAL_QUOTE,
    scope: AnalysisScope | None = None,
    proposal: QuoteProposal | None = None,
    collector_generated: bool = True,
    **kwargs,
):
    session = db_session(tmp_path)
    try:
        if body is None:
            capture = (
                session.query(EvidenceCapture)
                .filter(EvidenceCapture.id == capture_id)
                .first()
            )
            body = capture.text
        result = record_claim_citation(
            session,
            case_id=case_id,
            capture_id=capture_id,
            claim_signature=kwargs.pop("claim_signature", "sig-1"),
            claim_text=kwargs.pop("claim_text", CENTRAL_CLAIM),
            scope=scope if scope is not None else full_scope(body),
            proposal=proposal or QuoteProposal(quote=quote),
            collector_generated=collector_generated,
            **kwargs,
        )
        return result, session
    except Exception:
        session.close()
        raise


# ---------------------------------------------------------------------------
# Pure validator matrix
# ---------------------------------------------------------------------------


def test_exact_with_provided_offsets_over_unicode_body():
    """Valid provided offsets over emoji/CJK/combining text slice exactly."""
    body = SOURCE_A.body
    assert body is not None
    for marker in UNICODE_MARKERS.values():
        assert marker in body
    start = body.index(CENTRAL_QUOTE)
    result = validate_quote_alignment(
        body,
        QuoteProposal(
            quote=CENTRAL_QUOTE, start_char=start, end_char=start + len(CENTRAL_QUOTE)
        ),
        full_scope(body),
    )
    assert result.status == AlignmentStatus.EXACT.value
    assert result.is_exact
    assert (result.start_char, result.end_char) == (start, start + len(CENTRAL_QUOTE))
    assert body[result.start_char : result.end_char] == CENTRAL_QUOTE
    assert result.alignment_version == ALIGNMENT_VERSION


def test_exact_unique_occurrence_without_offsets():
    body = SOURCE_A.body
    assert body is not None
    assert body.count(CENTRAL_QUOTE) == 1
    result = validate_quote_alignment(
        body, QuoteProposal(quote=CENTRAL_QUOTE), full_scope(body)
    )
    assert result.status == AlignmentStatus.EXACT.value
    assert body[result.start_char : result.end_char] == CENTRAL_QUOTE
    assert result.proposed_start_char is None


def test_repeated_exact_occurrence_is_ambiguous_unless_offsets_disambiguate():
    body = "the order stands. Later: the order stands.\n"
    quote = "the order stands"
    without = validate_quote_alignment(
        body, QuoteProposal(quote=quote), full_scope(body)
    )
    assert without.status == AlignmentStatus.AMBIGUOUS.value
    assert without.quote is None and without.start_char is None

    second = body.rindex(quote)
    with_offsets = validate_quote_alignment(
        body,
        QuoteProposal(
            quote=quote, start_char=second, end_char=second + len(quote)
        ),
        full_scope(body),
    )
    assert with_offsets.status == AlignmentStatus.EXACT.value
    assert with_offsets.start_char == second


def test_overlapping_matches_count_as_multiple():
    """``aa`` overlaps in ``aaaa`` three times -> ambiguous, not a greedy match."""
    result = validate_quote_alignment(
        "aaaa", QuoteProposal(quote="aa"), AnalysisScope(0, 4)
    )
    assert result.status == AlignmentStatus.AMBIGUOUS.value
    assert result.diagnostic_reason == "repeated_exact_occurrence"

    single = validate_quote_alignment(
        "aaaa", QuoteProposal(quote="aa"), AnalysisScope(0, 2)
    )
    assert single.status == AlignmentStatus.EXACT.value
    assert single.start_char == 0 and single.end_char == 2


def test_prefix_scope_limits_search_and_out_of_scope_quote_is_no_match():
    body = SOURCE_A.body
    assert body is not None
    prefix_end = body.index("The order")
    prefix = AnalysisScope(start_char=0, end_char=prefix_end)
    inside = validate_quote_alignment(body, QuoteProposal(quote=CENTRAL_QUOTE), prefix)
    assert inside.status == AlignmentStatus.EXACT.value
    assert inside.end_char <= prefix_end

    after = body.index("residents")
    tail = AnalysisScope(start_char=after, end_char=len(body))
    outside = validate_quote_alignment(body, QuoteProposal(quote=CENTRAL_QUOTE), tail)
    assert outside.status == AlignmentStatus.NO_MATCH.value
    assert outside.quote is None and outside.start_char is None


def test_unknown_scope_fails_closed_and_never_assumes_full_capture():
    body = SOURCE_A.body
    assert body is not None
    result = validate_quote_alignment(body, QuoteProposal(quote=CENTRAL_QUOTE), None)
    assert result.status == AlignmentStatus.NO_MATCH.value
    assert result.diagnostic_reason == "scope_unknown"
    assert result.status != AlignmentStatus.EXACT.value


@pytest.mark.parametrize(
    "scope",
    [
        "not-a-scope",
        AnalysisScope(start_char=True, end_char=10),  # bool is not a real int
        AnalysisScope(start_char=0, end_char=True),
        AnalysisScope(start_char=-1, end_char=10),
        AnalysisScope(start_char=8, end_char=4),
        AnalysisScope(start_char=0, end_char=10_000),
    ],
)
def test_malformed_scope_fails_closed(scope):
    body = "The Port Alden Authority ordered an evacuation"
    result = validate_quote_alignment(
        body,
        QuoteProposal(quote="ordered an evacuation"),
        scope if isinstance(scope, AnalysisScope) else None,
    )
    assert result.status == AlignmentStatus.NO_MATCH.value
    assert result.quote is None


def test_body_sha256_mismatch_is_source_unavailable_and_match_succeeds():
    body = SOURCE_A.body
    assert body is not None
    good = compute_quote_text_sha256(body)
    ok = validate_quote_alignment(
        body,
        QuoteProposal(quote=CENTRAL_QUOTE),
        AnalysisScope(0, len(body), good),
    )
    assert ok.status == AlignmentStatus.EXACT.value

    mismatch = validate_quote_alignment(
        body,
        QuoteProposal(quote=CENTRAL_QUOTE),
        AnalysisScope(0, len(body), "0" * 64),
    )
    assert mismatch.status == AlignmentStatus.SOURCE_UNAVAILABLE.value
    assert mismatch.diagnostic_reason == "body_sha256_mismatch"


def test_missing_text_versus_missing_or_empty_quote_are_distinct():
    unavailable = validate_quote_alignment(
        None, QuoteProposal(quote=CENTRAL_QUOTE), AnalysisScope(0, 1)
    )
    assert unavailable.status == AlignmentStatus.SOURCE_UNAVAILABLE.value

    missing = validate_quote_alignment(
        "body", QuoteProposal(quote=None), AnalysisScope(0, 4)
    )
    assert missing.status == AlignmentStatus.NOT_PROVIDED.value

    empty = validate_quote_alignment(
        "body", QuoteProposal(quote=""), AnalysisScope(0, 4)
    )
    assert empty.status == AlignmentStatus.NOT_PROVIDED.value

    # An explicit empty capture is a real capture but cannot support a quote.
    explicit_empty = validate_quote_alignment("", QuoteProposal(quote="x"), AnalysisScope(0, 0))
    assert explicit_empty.status == AlignmentStatus.NO_MATCH.value


def test_crlf_capture_text_is_lf_normalized_and_quotes_are_not_normalized():
    raw = "First line\r\nPort Alden ordered an evacuation.\r\nThird line"
    stored = normalize_capture_text(raw)
    assert "\r" not in stored
    lf_quote = "Port Alden ordered an evacuation.\nThird"
    assert validate_quote_alignment(
        stored, QuoteProposal(quote=lf_quote), full_scope(stored)
    ).status == AlignmentStatus.EXACT.value
    crlf_quote = "Port Alden ordered an evacuation.\r\nThird"
    assert validate_quote_alignment(
        stored, QuoteProposal(quote=crlf_quote), full_scope(stored)
    ).status == AlignmentStatus.NO_MATCH.value


@pytest.mark.parametrize(
    "quote",
    [
        CENTRAL_QUOTE.upper(),  # casefold would match
        CENTRAL_QUOTE.capitalize(),
        "\t" + CENTRAL_QUOTE,  # trimming would match
        CENTRAL_QUOTE + " ",
        CENTRAL_QUOTE.replace("00", "\uff10\uff10"),  # fullwidth digits (NFKC)
    ],
)
def test_validation_never_casefolds_trims_or_nfkc_normalizes(quote):
    body = SOURCE_A.body
    assert body is not None
    result = validate_quote_alignment(body, QuoteProposal(quote=quote), full_scope(body))
    assert result.status == AlignmentStatus.NO_MATCH.value
    assert result.quote is None


@pytest.mark.parametrize(
    "proposal",
    [
        QuoteProposal(quote=CENTRAL_QUOTE, start_char=True, end_char=True),
        QuoteProposal(quote=CENTRAL_QUOTE, start_char=-5, end_char=-1),
        QuoteProposal(quote=CENTRAL_QUOTE, start_char=0, end_char=10_000),
        QuoteProposal(quote=CENTRAL_QUOTE, start_char=0, end_char=5),
    ],
)
def test_invalid_offsets_recover_via_unique_occurrence(proposal):
    body = SOURCE_A.body
    assert body is not None
    result = validate_quote_alignment(body, proposal, full_scope(body))
    assert result.status == AlignmentStatus.EXACT.value
    assert body[result.start_char : result.end_char] == CENTRAL_QUOTE


def test_offsets_inside_capture_but_outside_scope_fall_back_to_scope_search():
    body = SOURCE_A.body
    assert body is not None
    start = body.index(CENTRAL_QUOTE)
    prefix = AnalysisScope(0, body.index("The order"))
    # Offsets point at the real (but out-of-scope) occurrence: not accepted as-is,
    # yet the unique in-scope occurrence still validates.
    result = validate_quote_alignment(
        body,
        QuoteProposal(quote=CENTRAL_QUOTE, start_char=start, end_char=start + len(CENTRAL_QUOTE)),
        prefix,
    )
    assert result.status == AlignmentStatus.EXACT.value
    assert result.end_char <= prefix.end_char


def test_diagnostics_retain_original_proposal_and_reason():
    body = SOURCE_A.body
    assert body is not None
    result = validate_quote_alignment(
        body,
        QuoteProposal(quote="fabricated passage", start_char=3, end_char=19),
        full_scope(body),
    )
    assert result.status == AlignmentStatus.NO_MATCH.value
    assert result.proposed_quote == "fabricated passage"
    assert (result.proposed_start_char, result.proposed_end_char) == (3, 19)
    assert result.diagnostic_reason == "no_exact_occurrence_in_scope"
    assert result.quote is None and result.start_char is None


# ---------------------------------------------------------------------------
# Central relationship policy
# ---------------------------------------------------------------------------


def test_trusted_collector_priority_overrides_requested_relation_and_provenance():
    """Reproduced bugs: collector contexts must never yield support/contradiction."""
    exact = AlignmentStatus.EXACT.value
    cases = [
        # (collector_generated, origin, version, status, exact_anchor)
        (True, "collector", "v1", exact, True),
        (True, "human", "v1", exact, True),
        (True, None, None, exact, True),
    ]
    for collector, origin, version, status, anchor in cases:
        for stored in ("supports", "contradicts", "opposes", "reported_by", None):
            resolution = resolve_effective_relationship(
                stored_relation=stored,
                alignment_status=status,
                assessment_origin=origin,
                assessment_version=version,
                exact_anchor=anchor,
                collector_generated=collector,
            )
            assert resolution.effective_relationship == "reported_by", (
                collector, origin, stored
            )
            assert resolution.contribution is None
            assert link_contribution(resolution) is None

    non_exact = resolve_effective_relationship(
        stored_relation="supports",
        alignment_status=AlignmentStatus.AMBIGUOUS.value,
        exact_anchor=False,
        collector_generated=True,
    )
    assert non_exact.effective_relationship == "uncertain"


def test_unknown_or_unrecognized_origins_never_qualify():
    exact = AlignmentStatus.EXACT.value
    for origin in (None, "", "   ", "unknown", "legacy", "fallback", "collector", "robot"):
        resolution = resolve_effective_relationship(
            stored_relation="supports",
            alignment_status=exact,
            assessment_origin=origin,
            assessment_version="v1",
            exact_anchor=True,
            collector_generated=False,
        )
        assert resolution.effective_relationship == "uncertain", origin
        assert resolution.assessed is False
        assert resolution.contribution is None
        assert resolution.citation_eligible is False


def test_non_exact_status_with_anchor_flag_fails_closed():
    resolution = resolve_effective_relationship(
        stored_relation="supports",
        alignment_status=AlignmentStatus.NO_MATCH.value,
        assessment_origin="human",
        assessment_version="v1",
        exact_anchor=True,  # inconsistent with the status
        collector_generated=False,
    )
    assert resolution.effective_relationship == "uncertain"
    assert resolution.assessed is False


def test_unknown_version_sentinels_fail_closed_and_concrete_versions_are_accepted():
    """``assessment_version`` is an opaque identifier, not a policy registry."""
    for version in (
        None,
        "",
        "   ",
        "unknown",
        "UNKNOWN",
        "legacy",
        "Fallback",
        "unavailable",
        "none",
        "null",
        "N/A",
        "unversioned",
    ):
        resolution = resolve_effective_relationship(
            stored_relation="contradicts",
            alignment_status=AlignmentStatus.EXACT.value,
            assessment_origin="model",
            assessment_version=version,
            exact_anchor=True,
            collector_generated=False,
        )
        assert resolution.effective_relationship == "uncertain", version
        assert resolution.assessed is False
        assert resolution.citation_eligible is False

    # Concrete assessor/model/prompt versions all qualify, whatever the value.
    for version in ("v1", "v2", "model-v2", "prompt.2026-11-01", "Model-V3", "42"):
        resolution = resolve_effective_relationship(
            stored_relation="supports",
            alignment_status=AlignmentStatus.EXACT.value,
            assessment_origin="model",
            assessment_version=version,
            exact_anchor=True,
            collector_generated=False,
        )
        assert resolution.effective_relationship == "supports", version
        assert resolution.assessed is True
        assert resolution.citation_eligible is True


@pytest.mark.parametrize("flag", ["false", "true", "True", 1, 0, [], {}, None])
def test_non_boolean_collector_context_is_not_trusted(flag):
    """Only a real ``True`` enables the trusted collector branch."""
    resolution = resolve_effective_relationship(
        stored_relation="supports",
        alignment_status=AlignmentStatus.EXACT.value,
        assessment_origin="human",
        assessment_version="v1",
        exact_anchor=True,
        collector_generated=flag,
    )
    assert resolution.effective_relationship == "uncertain"
    assert resolution.assessed is False
    assert resolution.citation_eligible is False
    assert link_contribution(resolution) is None


def test_collector_generated_defaults_to_fail_closed():
    resolution = resolve_effective_relationship(
        stored_relation="supports", alignment_status=AlignmentStatus.EXACT.value
    )
    # Legacy/blanket supports without explicit assessment provenance.
    assert resolution.effective_relationship == "uncertain"
    assert resolution.stored_relationship == "supports"


def test_legacy_opposes_alias_is_uncertain_unprovenanced_and_contradicts_assessed():
    assert canonical_relationship("opposes") == "contradicts"
    assert canonical_relationship("OPPOSES ") == "contradicts"
    assert canonical_relationship("something-else") == "uncertain"
    assert canonical_relationship(None) == "uncertain"

    unprovenanced = resolve_effective_relationship(
        stored_relation="opposes",
        alignment_status=AlignmentStatus.EXACT.value,
        exact_anchor=True,
        collector_generated=False,
    )
    assert unprovenanced.effective_relationship == "uncertain"
    assert unprovenanced.stored_relationship == "opposes"

    assessed = resolve_effective_relationship(
        stored_relation="opposes",
        alignment_status=AlignmentStatus.EXACT.value,
        assessment_origin="human",
        assessment_version="v1",
        exact_anchor=True,
        collector_generated=False,
    )
    assert assessed.effective_relationship == "contradicts"
    assert assessed.assessed is True
    assert link_contribution(assessed) == "opposition"


@pytest.mark.parametrize("origin", ["model", "human", "service"])
def test_known_versioned_assessment_can_assert_support(origin):
    resolution = resolve_effective_relationship(
        stored_relation="supports",
        alignment_status=AlignmentStatus.EXACT.value,
        assessment_origin=origin,
        assessment_version="v1",
        exact_anchor=True,
        collector_generated=False,
    )
    assert resolution.effective_relationship == "supports"
    assert resolution.assessed is True
    assert resolution.contribution == "support"
    assert resolution.citation_eligible is True


@pytest.mark.parametrize("relationship", ["reported_by", "uncertain"])
def test_explicit_versioned_non_corroborating_relationships_are_allowed(relationship):
    resolution = resolve_effective_relationship(
        stored_relation=relationship,
        alignment_status=AlignmentStatus.EXACT.value,
        assessment_origin="service",
        assessment_version="v1",
        exact_anchor=True,
        collector_generated=False,
    )
    assert resolution.effective_relationship == relationship
    assert resolution.assessed is True
    assert resolution.contribution is None
    assert link_contribution(resolution) is None


def test_link_contribution_matrix():
    def res(**kwargs):
        base = {
            "stored_relation": "supports",
            "alignment_status": AlignmentStatus.EXACT.value,
            "assessment_origin": "model",
            "assessment_version": "v1",
            "exact_anchor": True,
            "collector_generated": False,
        }
        base.update(kwargs)
        return resolve_effective_relationship(**base)

    assert link_contribution(res()) == "support"
    assert link_contribution(res(stored_relation="contradicts")) == "opposition"
    assert link_contribution(res(stored_relation="reported_by")) is None
    assert link_contribution(res(stored_relation="uncertain")) is None
    # Collector-generated exact alignment never counts.
    assert (
        link_contribution(res(collector_generated=True, stored_relation="supports"))
        is None
    )
    # Unprovenanced legacy rows never count.
    assert (
        link_contribution(res(collector_generated=False, assessment_origin=None))
        is None
    )


def test_confidence_is_not_an_assessment_parameter():
    with pytest.raises(TypeError):
        resolve_effective_relationship(  # type: ignore[call-arg]
            stored_relation="supports",
            alignment_status=AlignmentStatus.EXACT.value,
            exact_anchor=True,
            confidence_score=0.99,
        )


# ---------------------------------------------------------------------------
# Immutable citations
# ---------------------------------------------------------------------------


def test_record_creates_citation_with_frozen_fields(tmp_path):
    capture_id, body = capture_source(tmp_path)
    proposal = QuoteProposal(quote=CENTRAL_QUOTE)
    result, session = record(tmp_path, capture_id=capture_id, proposal=proposal)
    try:
        assert result.is_validated and result.created
        citation = result.citation
        assert citation is not None
        assert citation.case_id == "case-1"
        assert citation.capture_id == capture_id
        assert citation.text == CENTRAL_CLAIM
        assert citation.claim_signature == "sig-1"
        assert citation.quote == CENTRAL_QUOTE
        assert body[citation.start_char : citation.end_char] == CENTRAL_QUOTE
        assert citation.alignment_status == AlignmentStatus.EXACT.value
        assert citation.alignment_version == ALIGNMENT_VERSION
        assert citation.relationship == "reported_by"
        assert citation.assessment_origin == "collector"
        assert citation.recorded_at is not None
        assert citation.metadata_json["alignment"]["status"] == "exact"
        assert citation.metadata_json["alignment"]["scope"]["start_char"] == 0
        session.commit()
    finally:
        session.close()

    check = db_session(tmp_path)
    try:
        assert check.query(ClaimCitation).count() == 1
    finally:
        check.close()


def test_identical_rerun_reuses_and_first_provenance_is_frozen(tmp_path):
    capture_id, _ = capture_source(tmp_path)
    metadata = {
        "reasoning": "the passage restates the claim",
        "origin_run_id": "run-1",
        "recorded_at": "2026-03-03T06:31:00+00:00",
    }
    first, session = record(
        tmp_path,
        capture_id=capture_id,
        original_claim_id="claim-generated-1",
        assessment_metadata=metadata,
        assessment_version="model-v1",
    )
    first_id = first.citation.id
    first_metadata = copy.deepcopy(first.citation.metadata_json)
    assert first.citation.original_claim_id == "claim-generated-1"
    session.commit()
    session.close()

    # Mutating the caller's dict after recording must not alter the stored row.
    metadata["reasoning"] = "mutated after the fact"
    metadata["origin_run_id"] = "run-2"

    second, session = record(
        tmp_path,
        capture_id=capture_id,
        original_claim_id="claim-generated-2",  # generated ID churn
        assessment_metadata={
            "reasoning": "the passage restates the claim",
            "origin_run_id": "run-2",
            "recorded_at": "2026-03-03T09:00:00+00:00",
        },
        assessment_version="model-v1",
    )
    try:
        assert second.created is False
        assert second.citation.id == first_id
        # First provenance and historical ID retained, not overwritten.
        assert second.citation.original_claim_id == "claim-generated-1"
        assert second.citation.metadata_json == first_metadata
    finally:
        session.close()


def test_changed_version_quote_or_capture_creates_another_citation(tmp_path):
    capture_id, body = capture_source(tmp_path)
    base, session = record(tmp_path, capture_id=capture_id, assessment_version="model-v1")
    base_id = base.citation.id
    session.commit()
    session.close()

    changed_version, session = record(
        tmp_path, capture_id=capture_id, assessment_version="model-v2"
    )
    assert changed_version.created is True
    assert changed_version.citation.id != base_id
    session.commit()
    session.close()

    other_quote = "The order, confirmed in a brief written statement"
    changed_quote, session = record(tmp_path, capture_id=capture_id, quote=other_quote)
    assert changed_quote.created is True
    assert changed_quote.citation.id != base_id
    session.commit()
    session.close()

    # A later capture version of the same evidence is a different citation basis.
    session = db_session(tmp_path)
    try:
        evidence = session.query(EvidenceItem).filter(EvidenceItem.id == "evidence-a").one()
        new_capture = record_evidence_capture(
            session, evidence, text=REVISED_BODY_A, metadata=SOURCE_A.capture_kwargs()
        )
        assert new_capture is not None and new_capture.id != capture_id
        session.commit()
        new_capture_id = new_capture.id
    finally:
        session.close()

    changed_capture, session = record(
        tmp_path, capture_id=new_capture_id, body=REVISED_BODY_A
    )
    assert changed_capture.created is True
    assert changed_capture.citation.id != base_id
    assert changed_capture.citation.capture_id == new_capture_id
    session.commit()
    session.close()


def test_meaningful_assessment_content_changes_identity_but_volatile_does_not(tmp_path):
    capture_id, _ = capture_source(tmp_path)
    base, session = record(
        tmp_path,
        capture_id=capture_id,
        assessment_metadata={"reasoning": "supports it", "timestamp": "2026-03-03T06:00:00Z"},
    )
    base_id = base.citation.id
    session.commit()
    session.close()

    # A semantic top-level ``timestamp`` is meaningful content, not volatile.
    semantic_time, session = record(
        tmp_path,
        capture_id=capture_id,
        assessment_metadata={"reasoning": "supports it", "timestamp": "2026-03-04T06:00:00Z"},
    )
    try:
        assert semantic_time.created is True
        assert semantic_time.citation.id != base_id
    finally:
        session.close()

    # A nested meaningful change also creates a new citation (no recursive strip).
    nested, session = record(
        tmp_path,
        capture_id=capture_id,
        assessment_metadata={
            "reasoning": "supports it",
            "timestamp": "2026-03-03T06:00:00Z",
            "details": {"note": "changed"},
        },
    )
    try:
        assert nested.created is True
        assert nested.citation.id != base_id
    finally:
        session.close()

    # Volatile operation/provenance IDs and times stay out of identity.
    volatile, session = record(
        tmp_path,
        capture_id=capture_id,
        assessment_metadata={
            "reasoning": "supports it",
            "timestamp": "2026-03-03T06:00:00Z",
            "origin_stage_attempt_id": "stage-9",
            "origin_run_id": "run-9",
            "recorded_at": "2026-03-05T00:00:00Z",
        },
    )
    try:
        assert volatile.created is False
        assert volatile.citation.id == base_id
        # The FIRST full raw metadata is retained verbatim, volatile keys included.
        assert volatile.citation.metadata_json["assessment_metadata"] == {
            "reasoning": "supports it",
            "timestamp": "2026-03-03T06:00:00Z",
        }
    finally:
        session.close()

    # Volatile-only churn over an identical semantic assessment reuses the row and
    # never overwrites the first stored provenance.
    churn, session = record(
        tmp_path,
        capture_id=capture_id,
        assessment_metadata={
            "reasoning": "supports it",
            "timestamp": "2026-03-03T06:00:00Z",
            "origin_stage_attempt_id": "stage-77",
            "origin_run_id": "run-77",
        },
    )
    try:
        assert churn.created is False
        assert churn.citation.id == base_id
        assert (
            churn.citation.metadata_json["assessment_metadata"]
            == volatile.citation.metadata_json["assessment_metadata"]
        )
    finally:
        session.close()


def test_assessed_changed_versions_create_distinct_citations_and_are_preserved(tmp_path):
    """Explicit assessments: v1 -> v2 -> model-V3 are all eligible and distinct."""
    capture_id, _ = capture_source(tmp_path)
    claim_text = CENTRAL_CLAIM
    signature = "sig-assessed"

    created = []
    for version in ("v1", "v2", "model-V3"):
        result, session = record(
            tmp_path,
            capture_id=capture_id,
            collector_generated=False,
            stored_relation="supports",
            assessment_origin="model",
            assessment_version=version,
            claim_signature=signature,
            claim_text=claim_text,
            assessment_metadata={"reasoning": "the passage restates the claim"},
        )
        try:
            assert result.citation is not None, version
            assert result.relationship.assessed is True, version
            assert result.relationship.effective_relationship == "supports", version
            assert result.relationship.citation_eligible is True, version
            assert result.citation.assessment_version == version, version
            assert result.citation.assessment_origin == "model"
            session.commit()
            created.append(result.citation.id)
        finally:
            session.close()

    assert len(set(created)) == 3  # every distinct version is its own citation

    # Repeating one version with different stage/time/historical claim ID reuses
    # the row and keeps the first metadata/historical ID.
    repeated, session = record(
        tmp_path,
        capture_id=capture_id,
        collector_generated=False,
        stored_relation="supports",
        assessment_origin="model",
        assessment_version="model-V3",
        claim_signature=signature,
        claim_text=claim_text,
        original_claim_id="claim-regenerated",
        assessment_metadata={
            "reasoning": "the passage restates the claim",
            "origin_run_id": "later-run",
        },
    )
    try:
        assert repeated.created is False
        assert repeated.citation.id == created[-1]
        assert repeated.citation.assessment_version == "model-V3"
        assert repeated.citation.original_claim_id is None  # first row kept
        assert repeated.citation.metadata_json["assessment_metadata"] == {
            "reasoning": "the passage restates the claim"
        }
    finally:
        session.close()


def test_invalid_proposals_create_no_citation_and_keep_diagnostics(tmp_path):
    capture_id, _ = capture_source(tmp_path)
    for proposal, expected in (
        (QuoteProposal(quote="fabricated passage"), AlignmentStatus.NO_MATCH.value),
        (QuoteProposal(quote=None), AlignmentStatus.NOT_PROVIDED.value),
        (QuoteProposal(quote=""), AlignmentStatus.NOT_PROVIDED.value),
    ):
        result, session = record(tmp_path, capture_id=capture_id, proposal=proposal)
        try:
            assert result.citation is None
            assert result.created is False
            assert result.alignment.status == expected
            assert result.alignment.proposed_quote == proposal.quote
            assert "invalid_proposal_diagnostic_only" in result.notes
        finally:
            session.close()

    check = db_session(tmp_path)
    try:
        assert check.query(ClaimCitation).count() == 0
    finally:
        check.close()


def test_exact_span_with_unknown_assessment_origin_is_not_citable(tmp_path):
    """An exact passage alone is not enough: provenance must be recognised."""
    capture_id, _ = capture_source(tmp_path)
    result, session = record(
        tmp_path,
        capture_id=capture_id,
        collector_generated=False,
        assessment_origin="mystery",
        assessment_version="v1",
    )
    try:
        assert result.alignment.status == AlignmentStatus.EXACT.value
        assert result.citation is None
        assert result.relationship.effective_relationship == "uncertain"
        assert "exact_passage_not_citation_eligible" in result.notes
    finally:
        session.close()


def test_ownership_and_cross_case_protections(tmp_path):
    capture_id, _ = capture_source(tmp_path)
    other_capture, _ = capture_source(
        tmp_path, case_id="case-2", source=SOURCE_C, evidence_id="evidence-c"
    )

    session = db_session(tmp_path)
    try:
        with pytest.raises(LookupError):
            record_claim_citation(
                session,
                case_id="missing-case",
                capture_id=capture_id,
                claim_signature="s",
                claim_text=CENTRAL_CLAIM,
                scope=AnalysisScope(0, 10),
                collector_generated=True,
            )
        with pytest.raises(LookupError):
            record_claim_citation(
                session,
                case_id="case-1",
                capture_id="missing-capture",
                claim_signature="s",
                claim_text=CENTRAL_CLAIM,
                scope=AnalysisScope(0, 10),
                collector_generated=True,
            )
        with pytest.raises(ValueError):
            record_claim_citation(
                session,
                case_id="case-1",
                capture_id=other_capture,
                claim_signature="s",
                claim_text=CENTRAL_CLAIM,
                scope=AnalysisScope(0, 10),
                collector_generated=True,
            )
        with pytest.raises(ValueError):
            record_claim_citation(
                session,
                case_id="case-1",
                capture_id=capture_id,
                evidence_id="evidence-c",
                claim_signature="s",
                claim_text=CENTRAL_CLAIM,
                scope=AnalysisScope(0, 10),
                collector_generated=True,
            )
        assert session.query(ClaimCitation).count() == 0
    finally:
        session.close()


def test_live_claim_from_another_case_is_rejected_but_absent_id_is_allowed(tmp_path):
    capture_id, _ = capture_source(tmp_path)
    capture_2, _ = capture_source(
        tmp_path, case_id="case-2", source=SOURCE_C, evidence_id="evidence-c"
    )

    session = db_session(tmp_path)
    try:
        event = Event(
            id="event-case-2",
            timestamp=EVENT_TS,
            title="Other case event",
            verification_status=VerificationStatus.ALLEGED,
            case_id="case-2",
        )
        session.add(event)
        session.flush([event])
        session.add(
            Claim(
                id="claim-case-2",
                event_id=event.id,
                claim_text=CENTRAL_CLAIM,
                verification_status=VerificationStatus.ALLEGED,
                claim_signature="sig-other",
            )
        )
        session.commit()

        with pytest.raises(ValueError):
            record_claim_citation(
                session,
                case_id="case-1",
                capture_id=capture_id,
                original_claim_id="claim-case-2",
                claim_signature="s",
                claim_text=CENTRAL_CLAIM,
                scope=AnalysisScope(0, len(SOURCE_A.body or "")),
                collector_generated=True,
            )

        # A historical claim ID that no longer exists is perfectly valid.
        ok = record_claim_citation(
            session,
            case_id="case-2",
            capture_id=capture_2,
            original_claim_id="claim-deleted-long-ago",
            claim_signature="s",
            claim_text=CENTRAL_CLAIM,
            scope=AnalysisScope(0, len(SOURCE_C.body or "")),
            proposal=QuoteProposal(quote="Residents in the north of the city"),
            collector_generated=True,
        )
        assert ok.citation is not None
        assert ok.citation.original_claim_id == "claim-deleted-long-ago"
        session.rollback()
    finally:
        session.close()


def test_validation_reads_do_not_autoflush_unrelated_pending_rows(tmp_path):
    """A caller's generic autoflush session must not be flushed by validation."""
    session, engine = scratch_session(tmp_path)
    session.autoflush = True
    try:
        case = TopicCase(
            id="case-1",
            query="Quotation case",
            slug="case-1-slug",
            status=CaseStatus.INVESTIGATING,
            metadata_json={},
        )
        session.add(case)
        session.flush([case])
        evidence = add_evidence(session, evidence_id="evidence-a")
        capture = record_evidence_capture(
            session, evidence, text=SOURCE_A.body, metadata=SOURCE_A.capture_kwargs()
        )
        assert capture is not None
        capture_id = capture.id
        session.commit()
        # An incomplete pending Event would fail on any implicit flush.
        pending = Event(id="pending-event", title="not committed")
        session.add(pending)
        assert pending in session.new

        result = record_claim_citation(
            session,
            case_id="case-1",
            capture_id=capture_id,
            claim_signature="sig-1",
            claim_text=CENTRAL_CLAIM,
            scope=full_scope(SOURCE_A.body or ""),
            proposal=QuoteProposal(quote=CENTRAL_QUOTE),
            collector_generated=True,
        )
        assert result.citation is not None
        assert pending in session.new  # unrelated object never flushed
        session.rollback()
    finally:
        session.close()
        engine.dispose()

    check, engine2 = scratch_session(tmp_path)
    try:
        assert check.query(ClaimCitation).count() == 0
        assert check.query(Event).count() == 0
    finally:
        check.close()
        engine2.dispose()


def test_citation_rows_are_append_only_at_the_orm_boundary(tmp_path):
    capture_id, _ = capture_source(tmp_path)
    result, session = record(tmp_path, capture_id=capture_id)
    try:
        citation = result.citation
        assert citation is not None
        session.commit()
        citation.quote = "rewritten"
        with pytest.raises(ValueError):
            session.flush()
        session.rollback()
    finally:
        session.close()

    session = db_session(tmp_path)
    try:
        row = session.query(ClaimCitation).one()
        with pytest.raises(ValueError):
            session.delete(row)
            session.flush()
        session.rollback()
        assert session.query(ClaimCitation).count() == 1
    finally:
        session.close()


def test_fk_enforced_deletion_of_live_claim_and_link_keeps_citation_and_capture(tmp_path):
    session, engine = scratch_session(tmp_path)
    try:
        case = TopicCase(
            id="case-fk",
            query="FK case",
            slug="fk-case",
            status=CaseStatus.INVESTIGATING,
            metadata_json={},
        )
        session.add(case)
        session.flush([case])
        event = Event(
            id="event-fk",
            timestamp=EVENT_TS,
            title="FK event",
            verification_status=VerificationStatus.ALLEGED,
            case_id="case-fk",
        )
        session.add(event)
        session.flush([event])
        claim = Claim(
            id="claim-fk",
            event_id="event-fk",
            claim_text=CENTRAL_CLAIM,
            verification_status=VerificationStatus.ALLEGED,
            claim_signature="sig-fk",
        )
        session.add(claim)
        session.flush([claim])
        evidence = EvidenceItem(
            id="evidence-fk",
            case_id="case-fk",
            evidence_type="article",
            source_type="rss",
            verification_status="UNVERIFIED",
        )
        session.add(evidence)
        session.flush([evidence])
        capture = record_evidence_capture(
            session, evidence, text=SOURCE_A.body, metadata={}
        )
        assert capture is not None
        link = ClaimEvidenceLink(
            id="link-fk",
            claim_id="claim-fk",
            evidence_id="evidence-fk",
            relation="supports",
            capture_id=capture.id,
        )
        session.add(link)
        session.flush([link])

        result = record_claim_citation(
            session,
            case_id="case-fk",
            capture_id=capture.id,
            original_claim_id="claim-fk",
            claim_signature="sig-fk",
            claim_text=CENTRAL_CLAIM,
            scope=full_scope(SOURCE_A.body or ""),
            proposal=QuoteProposal(quote=CENTRAL_QUOTE),
            collector_generated=True,
        )
        citation = result.citation
        assert citation is not None
        link.citation_id = citation.id
        session.flush()
        session.commit()

        session.delete(link)
        session.flush()
        session.delete(claim)
        session.flush()
        session.commit()

        assert session.query(ClaimCitation).count() == 1
        assert session.query(EvidenceCapture).count() == 1
        assert session.query(EvidenceItem).one().current_capture_id == capture.id
        surviving = session.query(ClaimCitation).one()
        assert surviving.text == CENTRAL_CLAIM
        assert surviving.original_claim_id == "claim-fk"
    finally:
        session.close()
        engine.dispose()


def test_citation_and_link_pointer_fks_are_enforced_on_scratch_connection(tmp_path):
    session, engine = scratch_session(tmp_path)
    try:
        case = TopicCase(
            id="case-fk2",
            query="FK case 2",
            slug="fk-case-2",
            status=CaseStatus.INVESTIGATING,
            metadata_json={},
        )
        session.add(case)
        session.flush([case])
        evidence = EvidenceItem(
            id="evidence-fk2",
            case_id="case-fk2",
            evidence_type="article",
            source_type="rss",
            verification_status="UNVERIFIED",
        )
        session.add(evidence)
        session.flush([evidence])
        capture = record_evidence_capture(
            session, evidence, text=SOURCE_A.body, metadata={}
        )
        assert capture is not None
        event = Event(
            id="event-fk2",
            timestamp=EVENT_TS,
            title="FK event 2",
            verification_status=VerificationStatus.ALLEGED,
            case_id="case-fk2",
        )
        session.add(event)
        session.flush([event])
        claim = Claim(
            id="claim-fk2",
            event_id="event-fk2",
            claim_text=CENTRAL_CLAIM,
            verification_status=VerificationStatus.ALLEGED,
            claim_signature="sig-fk2",
        )
        session.add(claim)
        session.flush([claim])
        session.commit()

        # Invalid capture pointer on a link is rejected while FK enforcement is on.
        session.add(
            ClaimEvidenceLink(
                id="link-bad-capture",
                claim_id="claim-fk2",
                evidence_id="evidence-fk2",
                relation="supports",
                capture_id="missing-capture",
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

        # Invalid citation pointer likewise.
        session.add(
            ClaimEvidenceLink(
                id="link-bad-citation",
                claim_id="claim-fk2",
                evidence_id="evidence-fk2",
                relation="supports",
                citation_id="missing-citation",
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

        # The historical claim ID is a plain value: no FK, so a dangling ID is fine.
        session.add(
            ClaimCitation(
                id="citation-manual",
                case_id="case-fk2",
                capture_id=capture.id,
                original_claim_id="historical-claim-not-in-table",
                claim_signature="sig-fk2",
                text=CENTRAL_CLAIM,
                relationship="reported_by",
                quote=CENTRAL_QUOTE,
                start_char=0,
                end_char=len(CENTRAL_QUOTE),
                alignment_status="exact",
                alignment_version=ALIGNMENT_VERSION,
                metadata_json={},
            )
        )
        session.flush()
        assert session.query(ClaimCitation).count() == 1
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_caller_rollback_after_record_undoes_the_citation(tmp_path):
    capture_id, _ = capture_source(tmp_path)
    session = db_session(tmp_path)
    try:
        result = record_claim_citation(
            session,
            case_id="case-1",
            capture_id=capture_id,
            claim_signature="sig-1",
            claim_text=CENTRAL_CLAIM,
            scope=full_scope(SOURCE_A.body or ""),
            proposal=QuoteProposal(quote=CENTRAL_QUOTE),
            collector_generated=True,
        )
        assert result.citation is not None
        # Visible inside the transaction via the explicit flush only.
        assert session.query(ClaimCitation).count() == 1
        session.rollback()
    finally:
        session.close()

    check = db_session(tmp_path)
    try:
        assert check.query(ClaimCitation).count() == 0
    finally:
        check.close()


def test_workbench_fixture_shapes_are_usable_without_truth_claims(tmp_path):
    """The shared fixture exposes five sources, Unicode, and missing metadata."""
    assert {source.key for source in WORKBENCH_SOURCES} == {"A", "B", "C", "D", "E"}
    assert SOURCE_A.body == SOURCE_B.body  # verbatim copy
    assert SOURCE_A.body != SOURCE_C.body
    assert SOURCE_D.body is not None and CENTRAL_QUOTE not in SOURCE_D.body
    assert UNAVAILABLE.body is None
    legacy = {source.key: source for source in LEGACY_WORKBENCH_SOURCES}
    assert legacy["A"].publisher is None and legacy["A"].capture_kwargs() == {"legacy": True}
    assert CENTRAL_QUOTE in (SOURCE_A.body or "")
    assert CENTRAL_QUOTE not in (SOURCE_E.body or "")
