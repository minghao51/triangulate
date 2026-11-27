"""B01 regression tests: atomic event batches and meaningful review state.

Covers:

* the caller-owned event writer contract (flush, never commit/rollback/close,
  error propagation) versus the legacy standalone ``True``/``False`` writer;
* an investigation persistence batch failing on its second event rolling back
  every first-event write, artifact, count and review change, marking the
  stage/case failed and never reaching the report stage;
* review preservation/invalidation driven by the versioned canonical analysis
  hash (ordering, generated IDs, timestamps and derived aggregates ignored;
  claim/classification/evidence-content/relationship changes invalidating);
* the parent-identified hash hazards: an investigated party that is not a
  claim's representative, nested generated claim IDs inside investigation JSON
  and event-prefixed narrative cluster identity.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime

import pytest

from src.cases.service import CaseRunContext, TopicCaseService
from src.storage import (
    CaseArtifact,
    CaseStageName,
    CaseStageRun,
    CaseStatus,
    Claim,
    ClaimEvidenceLink,
    Event,
    EvidenceItem,
    EvidenceVerificationCheck,
    Narrative,
    Party,
    Review,
    ReviewStatus,
    StageStatus,
    TopicCase,
    VerificationStatus,
    init_database,
)
from src.storage.event_store import store_event_in_db
from src.storage.review_state import (
    ANALYSIS_HASH_VERSION,
    AnalysisCanonicalizationError,
    bind_review_decision,
    compute_event_analysis_hash,
)

EVENT_TS = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)
REVIEW_TS = datetime(2026, 4, 1, 9, 30, tzinfo=UTC)
NOTES = "Reviewed by an analyst."


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def party(name: str) -> dict:
    return {"canonical_name": name, "aliases": [name]}


def evidence_payload(
    *,
    evidence_id: str | None = None,
    content: str = "Alpha said the bridge was closed.",
    relation: str = "supports",
    url: str = "https://example.com/source-1",
    title: str = "Source 1",
    publisher: str = "Outlet One",
    confidence: float | None = 0.8,
    checks: list[dict] | None = None,
    capture_metadata: dict | None = None,
    requires_human_review: bool = False,
) -> dict:
    payload = {
        "canonical_url": url,
        "origin_url": url,
        "title": title,
        "publisher": publisher,
        "published_at": "2026-03-08T00:00:00+00:00",
        "content": content,
        "relation": relation,
        "confidence_score": confidence,
        "verification_checks": checks or [],
        "capture_metadata": capture_metadata or {},
        "requires_human_review": requires_human_review,
    }
    if evidence_id is not None:
        payload["id"] = evidence_id
    return payload


def claim_payload(
    text: str = "Alpha disputes Beta",
    *,
    claim_id: str | None = None,
    status: str = "ALLEGED",
    signature: str | None = "sig-alpha-disputes-beta",
    party_name: str = "Alpha",
    fact_type: str | None = None,
    evidence: list[dict] | None = None,
    aggregates: tuple[int, int, int] = (2, 0, 1),
    cluster_id: str | None = None,
) -> dict:
    payload = {
        "claim": text,
        "verification_status": status,
        "claim_signature": signature,
        "party_name": party_name,
        "evidence": [evidence_payload()] if evidence is None else evidence,
        "support_count": aggregates[0],
        "oppose_count": aggregates[1],
        "source_diversity_count": aggregates[2],
        "party_positions": {party_name: "NEUTRAL"},
    }
    if claim_id is not None:
        payload["id"] = claim_id
    if fact_type is not None:
        payload["fact_allegation_type"] = fact_type
    if cluster_id is not None:
        payload["cluster_id"] = cluster_id
    return payload


def investigation_payload(
    party_name: str = "Beta",
    *,
    supported: list[dict] | None = None,
    position: str = "Contests",
) -> dict:
    return {
        "party_name": party_name,
        "investigation": {
            "claims_supported": supported or [],
            "claims_contested": [],
            "unique_claims": [],
        },
        "party_stance": {"overall_position": position},
    }


def build_event(
    event_id: str,
    *,
    timestamp: datetime = EVENT_TS,
    claims: list[dict] | None = None,
    narratives: list[dict] | None = None,
    parties: list[dict] | None = None,
    investigations: list[dict] | None = None,
    verification_status: str = "PROBABLE",
    title: str = "Alpha/Beta dispute",
    summary: str = "Alpha and Beta dispute the bridge closure.",
    ui_type: str | None = None,
) -> dict:
    event = {
        "id": event_id,
        "timestamp": timestamp,
        "title": title,
        "summary": summary,
        "verification_status": verification_status,
        "source_url": "https://example.com/article",
        "source_name": "Example",
        "claims": claims if claims is not None else [claim_payload()],
        "narratives": narratives
        if narratives is not None
        else [{"cluster_id": "0", "stance_summary": "Dispute narrative", "claim_count": 1}],
        "parties": parties
        if parties is not None
        else [party("Alpha"), party("Beta")],
        "party_investigations": investigations or [],
    }
    if ui_type is not None:
        event["verification_status"] = ui_type
    return event


def db_session(tmp_path):
    db = init_database(str(tmp_path / "triangulate.db"))
    return db.get_session_sync()


def approve_event(
    tmp_path,
    event_id: str,
    *,
    status: ReviewStatus = ReviewStatus.APPROVED,
    notes: str = NOTES,
) -> None:
    session = db_session(tmp_path)
    try:
        review = session.query(Review).filter(Review.event_id == event_id).first()
        review.status = status
        review.reviewed_at = REVIEW_TS
        review.notes = notes
        bind_review_decision(review, compute_event_analysis_hash(session, event_id))
        session.commit()
    finally:
        session.close()


def read_review(tmp_path, event_id: str) -> Review:
    session = db_session(tmp_path)
    try:
        review = session.query(Review).filter(Review.event_id == event_id).first()
        session.expunge(review)
        return review
    finally:
        session.close()


def read_hash(tmp_path, event_id: str) -> str:
    session = db_session(tmp_path)
    try:
        return compute_event_analysis_hash(session, event_id)
    finally:
        session.close()


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None)


class TrackingSession:
    """Session proxy that records transaction lifecycle calls."""

    def __init__(self, inner):
        self.inner = inner
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def commit(self):
        self.commits += 1
        return self.inner.commit()

    def rollback(self):
        self.rollbacks += 1
        return self.inner.rollback()

    def close(self):
        self.closes += 1
        return self.inner.close()

    def __getattr__(self, name):
        return getattr(self.inner, name)


class TrackingDatabase:
    def __init__(self, real_db):
        self.real_db = real_db
        self.sessions: list[TrackingSession] = []

    def get_session_sync(self) -> TrackingSession:
        tracked = TrackingSession(self.real_db.get_session_sync())
        self.sessions.append(tracked)
        return tracked


# ---------------------------------------------------------------------------
# Writer contract
# ---------------------------------------------------------------------------


def test_standalone_store_keeps_boolean_contract_and_owns_session(
    tmp_path, monkeypatch
):
    from src.storage import get_database

    init_database(str(tmp_path / "triangulate.db"))
    tracking = TrackingDatabase(get_database())
    monkeypatch.setattr("src.storage.event_store.get_database", lambda: tracking)

    assert store_event_in_db(build_event("event-ok")) is True
    assert store_event_in_db({"id": "event-bad"}) is False

    assert len(tracking.sessions) == 2
    success, failure = tracking.sessions
    assert (success.commits, success.rollbacks, success.closes) == (1, 0, 1)
    assert (failure.commits, failure.rollbacks, failure.closes) == (0, 1, 1)

    session = db_session(tmp_path)
    try:
        assert session.query(Event).filter(Event.id == "event-ok").count() == 1
        assert session.query(Event).filter(Event.id == "event-bad").count() == 0
    finally:
        session.close()


def test_caller_owned_writer_never_commits_rolls_back_or_closes(tmp_path):
    init_database(str(tmp_path / "triangulate.db"))
    session = TrackingSession(db_session(tmp_path))
    try:
        stored = store_event_in_db(
            build_event("event-owned"), session=session, create_review=False
        )
        assert stored is True
        assert (session.commits, session.rollbacks, session.closes) == (0, 0, 0)
        # The writer flushed, so a SQL query in the caller's session (autoflush
        # is disabled) can already see the row before any commit.
        assert session.query(Event).filter(Event.id == "event-owned").count() == 1
        session.commit()
    finally:
        session.close()

    session = db_session(tmp_path)
    try:
        assert session.query(Event).filter(Event.id == "event-owned").count() == 1
    finally:
        session.close()


def test_caller_owned_writer_raises_and_caller_can_roll_back_whole_batch(tmp_path):
    init_database(str(tmp_path / "triangulate.db"))
    session = TrackingSession(db_session(tmp_path))
    try:
        store_event_in_db(build_event("event-first"), session=session, create_review=False)
        assert (session.commits, session.rollbacks, session.closes) == (0, 0, 0)

        # Fail the second write in the middle of the batch (invalid enum value).
        bad = build_event("event-second")
        bad["verification_status"] = "NOT_A_REAL_STATUS"
        with pytest.raises(KeyError):
            store_event_in_db(bad, session=session, create_review=False)

        assert (session.commits, session.rollbacks, session.closes) == (0, 0, 0)
        session.rollback()
        assert session.query(Event).count() == 0
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Investigation batch atomicity
# ---------------------------------------------------------------------------


def make_service(tmp_path) -> TopicCaseService:
    init_database(str(tmp_path / "triangulate.db"))
    return TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)


def seed_case(service: TopicCaseService, case_id: str = "case-b01") -> TopicCase:
    session = db_session(service.output_root)
    try:
        session.add(
            TopicCase(
                id=case_id,
                query="Atomic batch",
                slug="atomic-batch",
                status=CaseStatus.PROCESSING,
            )
        )
        session.commit()
    finally:
        session.close()
    return service._reload_case(case_id)


@pytest.mark.asyncio
async def test_failed_second_event_rolls_back_batch_and_marks_case_failed(tmp_path):
    service = make_service(tmp_path)
    case = seed_case(service)
    context = CaseRunContext(
        case=case, run_started_at=datetime.now(UTC), output_dir=tmp_path
    )
    events = [build_event("event-a"), build_event("event-b")]
    events[1]["verification_status"] = "NOT_A_REAL_STATUS"
    context.processed_events = events

    async def runner():
        return {"event_ids": ["event-a", "event-b"], "route_counts": {}, "exception_queue": []}

    await service._execute_stage(
        context,
        CaseStageName.INVESTIGATE,
        runner,
        workflow_name="test",
        model_used=None,
        status_after_success=CaseStatus.INVESTIGATING,
        persist_callback=service._persist_investigation_outputs,
    )

    session = db_session(tmp_path)
    try:
        stored_case = session.query(TopicCase).filter(TopicCase.id == case.id).first()
        assert stored_case.status == CaseStatus.FAILED
        assert stored_case.current_stage == CaseStageName.INVESTIGATE
        assert stored_case.event_count == 0

        stage = (
            session.query(CaseStageRun)
            .filter(CaseStageRun.case_id == case.id, CaseStageRun.stage_name == CaseStageName.INVESTIGATE)
            .order_by(CaseStageRun.attempt.desc())
            .first()
        )
        assert stage.status == StageStatus.FAILED
        assert "NOT_A_REAL_STATUS" in (stage.error_message or "")

        assert session.query(Event).filter(Event.case_id == case.id).count() == 0
        assert session.query(Claim).count() == 0
        assert session.query(EvidenceItem).count() == 0
        assert session.query(ClaimEvidenceLink).count() == 0
        assert session.query(Review).count() == 0
        assert session.query(Narrative).count() == 0
        assert session.query(CaseArtifact).count() == 0
        assert session.query(CaseStageRun).filter(
            CaseStageRun.case_id == case.id, CaseStageRun.stage_name == CaseStageName.REPORT
        ).count() == 0
    finally:
        session.close()


@pytest.mark.asyncio
async def test_failed_batch_restores_prior_event_state(tmp_path):
    service = make_service(tmp_path)
    case = seed_case(service)

    original = build_event("event-a", claims=[claim_payload("Original claim")])
    assert store_event_in_db(original, case_id=case.id) is True
    hash_before = read_hash(tmp_path, "event-a")

    context = CaseRunContext(
        case=case, run_started_at=datetime.now(UTC), output_dir=tmp_path
    )
    changed = build_event("event-a", claims=[claim_payload("Changed claim")])
    broken = build_event("event-b")
    broken["claims"] = [{"claim": "broken", "verification_status": "NOT_A_REAL_STATUS"}]
    context.processed_events = [changed, broken]

    async def runner():
        return {"event_ids": ["event-a", "event-b"], "route_counts": {}, "exception_queue": []}

    await service._execute_stage(
        context,
        CaseStageName.INVESTIGATE,
        runner,
        workflow_name="test",
        model_used=None,
        status_after_success=CaseStatus.INVESTIGATING,
        persist_callback=service._persist_investigation_outputs,
    )

    session = db_session(tmp_path)
    try:
        claim = session.query(Claim).filter(Claim.event_id == "event-a").one()
        assert claim.claim_text == "Original claim"
        assert session.query(Event).filter(Event.id == "event-b").count() == 0
        review = session.query(Review).filter(Review.event_id == "event-a").one()
        assert review.status == ReviewStatus.PENDING
        assert review.analysis_hash == hash_before
    finally:
        session.close()

    assert read_hash(tmp_path, "event-a") == hash_before


@pytest.mark.asyncio
async def test_run_case_does_not_reach_report_after_batch_failure(monkeypatch, tmp_path):
    service = make_service(tmp_path)

    async def fake_fetch(*args, **kwargs):
        return {
            "articles": [
                {
                    "url": "https://example.com/a",
                    "title": "Article A",
                    "source": "Example",
                    "published_at": "2026-03-08T12:00:00+00:00",
                    "content": "Alpha and Beta disagree.",
                    "relevance_score": 0.9,
                },
                {
                    "url": "https://example.com/b",
                    "title": "Article B",
                    "source": "Example",
                    "published_at": "2026-03-08T13:00:00+00:00",
                    "content": "Alpha and Beta disagree again.",
                    "relevance_score": 0.8,
                },
            ],
            "conflict": "ukraine_war",
            "queries_generated": ["alpha beta dispute"],
            "sources_used": ["Example"],
            "articles_fetched": 2,
            "articles_processed": 2,
        }

    async def fake_process(article):
        return {
            "id": "temporary",
            "timestamp": EVENT_TS,
            "title": article["title"],
            "summary": article["content"][:500],
            "verification_status": "CONTESTED",
            "claims": [
                {
                    "claim": "Alpha disputes Beta",
                    "who": ["Alpha", "Beta"],
                    "verification_status": "ALLEGED",
                }
            ],
            "narratives": [
                {"cluster_id": "0", "stance_summary": "Dispute narrative", "claim_count": 1}
            ],
            "parties": [party("Alpha"), party("Beta")],
        }

    real_store = store_event_in_db

    def corrupt_second_event(event_data, **kwargs):
        payload = dict(event_data)
        if payload.get("title") == "Article B":
            payload["verification_status"] = "NOT_A_REAL_STATUS"
        return real_store(payload, **kwargs)

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", fake_fetch)
    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)
    monkeypatch.setattr("src.cases.service.store_event_in_db", corrupt_second_event)

    case = await service.run_case(query="Atomic full run", output_dir=tmp_path)

    assert case.status == CaseStatus.FAILED
    assert case.current_stage == CaseStageName.INVESTIGATE
    assert case.report_path is None

    session = db_session(tmp_path)
    try:
        assert session.query(Event).filter(Event.case_id == case.id).count() == 0

        # The case pipeline is stage-transactional: artifacts committed by earlier
        # successful stages remain valid, but the failed INVESTIGATE stage must
        # have written no artifact and no later stage may have run.
        artifact_stages = [
            run.stage_name
            for run in session.query(CaseStageRun)
            .join(CaseArtifact, CaseArtifact.stage_run_id == CaseStageRun.id)
            .filter(CaseArtifact.case_id == case.id)
            .all()
        ]
        assert artifact_stages
        assert CaseStageName.INVESTIGATE not in artifact_stages
        assert CaseStageName.ARBITRATE not in artifact_stages
        assert CaseStageName.REPORT not in artifact_stages

        stages = {
            stage.stage_name
            for stage in session.query(CaseStageRun)
            .filter(CaseStageRun.case_id == case.id)
            .all()
        }
        assert CaseStageName.INVESTIGATE in stages
        assert CaseStageName.ARBITRATE not in stages
        assert CaseStageName.REPORT not in stages
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Review preservation and invalidation
# ---------------------------------------------------------------------------


def full_event(event_id: str, *, reverse: bool = False) -> dict:
    evidence = [
        evidence_payload(
            url="https://example.com/source-1",
            title="Source 1",
            publisher="Outlet One",
            checks=[
                {
                    "check_type": "ingestion",
                    "result": "passed",
                    "method": "rss",
                    "notes": "feed parsed",
                    "verified_by": "ingestion",
                }
            ],
            capture_metadata={
                "country": "UA",
                "language": "en",
                "fetch_strategy": "rss",
                "fetched_at": "2026-03-08T00:00:00+00:00",
            },
        ),
        evidence_payload(
            url="https://example.com/source-2",
            title="Source 2",
            publisher="Outlet Two",
            content="Beta denied the report.",
            relation="contradicts",
        ),
    ]
    if reverse:
        evidence = list(reversed(evidence))
    claims = [
        claim_payload("Alpha disputes Beta", signature="sig-alpha", evidence=evidence),
        claim_payload(
            "Beta denies the report",
            claim_id="claim-beta-explicit" if reverse else None,
            signature="sig-beta",
            status="CONTESTED",
            party_name="Beta",
            evidence=evidence,
            aggregates=(1, 1, 2) if reverse else (2, 0, 1),
        ),
    ]
    if reverse:
        claims = list(reversed(claims))
    narratives = [
        {"cluster_id": "0", "stance_summary": "Dispute narrative", "claim_count": 2},
        {"cluster_id": "1", "stance_summary": "Denial narrative", "claim_count": 1},
    ]
    if reverse:
        narratives = list(reversed(narratives))
    investigations = [
        investigation_payload(
            "Beta",
            supported=[{"claim_text": "Beta denies the report", "position": "CONTRADICTS"}],
        ),
        investigation_payload(
            "Alpha",
            supported=[{"claim_text": "Alpha disputes Beta", "position": "SUPPORTS"}],
        ),
    ]
    if reverse:
        investigations = list(reversed(investigations))
    return build_event(
        event_id,
        timestamp=datetime(2026, 3, 9, 8, 0, tzinfo=UTC) if reverse else EVENT_TS,
        claims=claims,
        narratives=narratives,
        investigations=investigations,
    )


@pytest.mark.parametrize(
    "status",
    [ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.ACTION_REQUIRED],
)
def test_equivalent_rewrite_preserves_decision(tmp_path, status):
    init_database(str(tmp_path / "triangulate.db"))
    assert store_event_in_db(full_event("event-1")) is True
    approve_event(tmp_path, "event-1", status=status)

    session = db_session(tmp_path)
    try:
        before = session.query(Review).filter(Review.event_id == "event-1").one()
        before_reviewed_at = before.reviewed_at
        before_hash = before.analysis_hash
    finally:
        session.close()

    # Different ordering, generated link/claim IDs, event timestamp, case run ID
    # and derived aggregate counts must not invalidate the decision.
    rewritten = full_event("event-1", reverse=True)
    rewritten["claims"][0]["support_count"] = 99
    rewritten["claims"][0]["oppose_count"] = 5
    rewritten["claims"][0]["source_diversity_count"] = 42
    assert store_event_in_db(rewritten, case_run_id="run-2") is True

    review = read_review(tmp_path, "event-1")
    assert review.status == status
    assert review.notes == NOTES
    assert review.previous_decision_json is None
    assert review.analysis_hash == before_hash

    session = db_session(tmp_path)
    try:
        reread = session.query(Review).filter(Review.event_id == "event-1").one()
        assert reread.reviewed_at == before_reviewed_at
    finally:
        session.close()

    assert read_hash(tmp_path, "event-1") == before_hash


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param("claim_text", id="changed-claim-text"),
        pytest.param("claim_status", id="changed-classification"),
        pytest.param("fact_type", id="changed-fact-type"),
        pytest.param("evidence_content", id="changed-evidence-body"),
        pytest.param("relation", id="changed-relationship"),
        pytest.param("investigation", id="changed-investigation"),
        pytest.param("event_status", id="changed-event-determination"),
        pytest.param("check_result", id="changed-verification-check-result"),
        pytest.param("capture_country", id="changed-capture-metadata-country"),
        pytest.param("requires_human_review", id="changed-human-review-flag"),
    ],
)
def test_material_analysis_change_invalidates_with_prior_metadata(tmp_path, mutation):
    init_database(str(tmp_path / "triangulate.db"))
    base = full_event("event-1")
    assert store_event_in_db(base) is True
    approve_event(tmp_path, "event-1")

    session = db_session(tmp_path)
    try:
        before = session.query(Review).filter(Review.event_id == "event-1").one()
        old_hash = before.analysis_hash
        old_reviewed_at = before.reviewed_at
    finally:
        session.close()

    changed = copy.deepcopy(base)
    if mutation == "claim_text":
        changed["claims"][0]["claim"] = "Alpha completely disputes Beta"
    elif mutation == "claim_status":
        changed["claims"][0]["verification_status"] = "CONFIRMED"
    elif mutation == "fact_type":
        changed["claims"][0]["fact_allegation_type"] = "FACT"
    elif mutation == "evidence_content":
        changed["claims"][0]["evidence"][0]["content"] = "Alpha said the bridge stayed open."
    elif mutation == "relation":
        changed["claims"][0]["evidence"][0]["relation"] = "contradicts"
    elif mutation == "investigation":
        changed["party_investigations"][0]["investigation"]["claims_supported"] = [
            {"claim_text": "A different claim", "position": "SUPPORTS"}
        ]
    elif mutation == "event_status":
        changed["verification_status"] = "CONFIRMED"
    elif mutation == "check_result":
        changed["claims"][0]["evidence"][0]["verification_checks"][0]["result"] = (
            "failed"
        )
    elif mutation == "capture_country":
        # A stable source-identity/capture field, not a generated timestamp.
        changed["claims"][0]["evidence"][0]["capture_metadata"]["country"] = "RU"
    elif mutation == "requires_human_review":
        changed["claims"][0]["evidence"][0]["requires_human_review"] = True
    assert store_event_in_db(changed) is True

    review = read_review(tmp_path, "event-1")
    assert review.status == ReviewStatus.PENDING
    assert review.reviewed_at is None
    assert review.notes == NOTES  # human notes are never overwritten
    previous = review.previous_decision_json
    assert previous is not None
    assert previous["status"] == "approved"
    assert previous["notes"] == NOTES
    assert previous["analysis_hash"] == old_hash
    assert previous["reason"] == "analysis_changed"
    assert previous["new_analysis_hash"] == review.analysis_hash
    assert _naive(datetime.fromisoformat(previous["reviewed_at"])) == _naive(
        old_reviewed_at
    )
    assert review.analysis_hash != old_hash


def test_pending_review_stays_pending_and_keeps_notes(tmp_path):
    init_database(str(tmp_path / "triangulate.db"))
    assert store_event_in_db(full_event("event-1")) is True

    session = db_session(tmp_path)
    try:
        review = session.query(Review).filter(Review.event_id == "event-1").one()
        review.notes = "Needs another look."
        session.commit()
    finally:
        session.close()

    changed = full_event("event-1")
    changed["claims"][0]["claim"] = "Alpha disputes Beta strongly"
    assert store_event_in_db(changed) is True

    review = read_review(tmp_path, "event-1")
    assert review.status == ReviewStatus.PENDING
    assert review.notes == "Needs another look."
    assert review.previous_decision_json is None
    assert review.analysis_hash is not None
    assert review.analysis_hash == read_hash(tmp_path, "event-1")


def test_legacy_null_hash_decision_is_invalidated_conservatively(tmp_path):
    init_database(str(tmp_path / "triangulate.db"))
    assert store_event_in_db(full_event("event-1")) is True

    session = db_session(tmp_path)
    try:
        review = session.query(Review).filter(Review.event_id == "event-1").one()
        review.status = ReviewStatus.APPROVED
        review.reviewed_at = REVIEW_TS
        review.notes = NOTES
        review.analysis_hash = None
        session.commit()
    finally:
        session.close()

    # Equivalent content, but the legacy row has no baseline to compare with.
    assert store_event_in_db(full_event("event-1")) is True

    review = read_review(tmp_path, "event-1")
    assert review.status == ReviewStatus.PENDING
    assert review.reviewed_at is None
    assert review.notes == NOTES
    previous = review.previous_decision_json
    assert previous["status"] == "approved"
    assert previous["analysis_hash"] is None
    assert previous["reason"] == "analysis_hash_unavailable"
    assert review.analysis_hash == read_hash(tmp_path, "event-1")


def test_legacy_pending_null_hash_adopts_baseline(tmp_path):
    init_database(str(tmp_path / "triangulate.db"))
    assert store_event_in_db(full_event("event-1")) is True

    session = db_session(tmp_path)
    try:
        review = session.query(Review).filter(Review.event_id == "event-1").one()
        review.notes = "Awaiting decision."
        review.analysis_hash = None
        session.commit()
    finally:
        session.close()

    assert store_event_in_db(full_event("event-1", reverse=True)) is True

    review = read_review(tmp_path, "event-1")
    assert review.status == ReviewStatus.PENDING
    assert review.notes == "Awaiting decision."
    assert review.previous_decision_json is None
    assert review.analysis_hash == read_hash(tmp_path, "event-1")


# ---------------------------------------------------------------------------
# Canonicalization hazards
# ---------------------------------------------------------------------------


def test_investigated_party_not_claim_representative_is_id_independent(tmp_path):
    """Party row IDs are generated; an investigated non-representative party
    must resolve to its canonical name in both databases."""
    hashes = []
    for index in (1, 2):
        db_path = tmp_path / f"db{index}" / "triangulate.db"
        db_path.parent.mkdir()
        init_database(str(db_path))
        event = build_event(
            "event-1",
            claims=[claim_payload("Alpha disputes Beta", party_name="Alpha")],
            investigations=[investigation_payload("Beta")],
        )
        assert store_event_in_db(event) is True
        hashes.append(read_hash(db_path.parent, "event-1"))

    assert hashes[0] == hashes[1]


def test_nested_generated_claim_ids_and_list_order_do_not_change_hash(tmp_path):
    hashes = []
    orderings = [
        ["claim one", "claim two"],
        ["claim two", "claim one"],
    ]
    for index, ordering in enumerate(orderings):
        db_path = tmp_path / f"nested{index}" / "triangulate.db"
        db_path.parent.mkdir()
        init_database(str(db_path))
        claim_id = f"generated-claim-uuid-{index}"
        event = build_event(
            "event-1",
            claims=[
                claim_payload(
                    "Alpha disputes Beta",
                    claim_id=claim_id,
                    signature="sig-alpha",
                )
            ],
            investigations=[
                investigation_payload(
                    "Beta",
                    supported=[
                        {"claim_id": claim_id, "claim_text": text, "position": "SUPPORTS"}
                        for text in ordering
                    ],
                )
            ],
        )
        assert store_event_in_db(event) is True
        hashes.append(read_hash(db_path.parent, "event-1"))

    assert hashes[0] == hashes[1]


def test_evidence_prefix_narrative_cluster_identity_is_not_substantive(tmp_path):
    init_database(str(tmp_path / "triangulate.db"))
    event = build_event("event-1")
    event["claims"][0]["cluster_id"] = "0"
    assert store_event_in_db(event) is True
    before = read_hash(tmp_path, "event-1")

    session = db_session(tmp_path)
    try:
        claim = session.query(Claim).filter(Claim.event_id == "event-1").one()
        assert claim.narrative_cluster_id == "0"
        claim.narrative_cluster_id = "event-1:0"
        session.commit()
    finally:
        session.close()

    assert read_hash(tmp_path, "event-1") == before


def test_hash_is_versioned(tmp_path):
    init_database(str(tmp_path / "triangulate.db"))
    assert store_event_in_db(build_event("event-1")) is True
    assert read_hash(tmp_path, "event-1").startswith(f"{ANALYSIS_HASH_VERSION}:")


def read_check(tmp_path, check_result: str = "passed") -> EvidenceVerificationCheck:
    session = db_session(tmp_path)
    try:
        check = (
            session.query(EvidenceVerificationCheck)
            .filter(EvidenceVerificationCheck.check_type == "ingestion")
            .filter(EvidenceVerificationCheck.result == check_result)
            .one()
        )
        session.expunge(check)
        return check
    finally:
        session.close()


@pytest.mark.parametrize(
    "field,new_value",
    [
        pytest.param("method", "archive_lookup", id="changed-check-method"),
        pytest.param("notes", "manually cross-checked", id="changed-check-notes"),
        pytest.param("verified_by", "second_ingestion", id="changed-check-verified-by"),
    ],
)
def test_check_semantic_metadata_rewrite_persists_and_invalidates(
    tmp_path, field, new_value
):
    """A same-(type,result) rewrite must upsert supplied check semantics."""
    init_database(str(tmp_path / "triangulate.db"))
    base = full_event("event-1")
    assert store_event_in_db(base) is True
    approve_event(tmp_path, "event-1")
    before_hash = read_hash(tmp_path, "event-1")
    assert getattr(read_check(tmp_path), field) != new_value

    changed = copy.deepcopy(base)
    check_payload = changed["claims"][0]["evidence"][0]["verification_checks"][0]
    check_payload[field] = new_value
    # Same check_type/result -> same deterministic check ID, so this exercises
    # the existing-row upsert path rather than inserting a new record.
    assert store_event_in_db(changed) is True

    assert getattr(read_check(tmp_path), field) == new_value
    assert read_hash(tmp_path, "event-1") != before_hash
    review = read_review(tmp_path, "event-1")
    assert review.status == ReviewStatus.PENDING
    assert review.previous_decision_json["reason"] == "analysis_changed"


def test_check_rewrite_preserves_omitted_fields_and_unchanged_metadata(tmp_path):
    """Omitted check fields keep stored values; unchanged metadata preserves."""
    init_database(str(tmp_path / "triangulate.db"))
    base = full_event("event-1")
    assert store_event_in_db(base) is True
    approve_event(tmp_path, "event-1")
    before_hash = read_hash(tmp_path, "event-1")

    changed = copy.deepcopy(base)
    check_payload = changed["claims"][0]["evidence"][0]["verification_checks"][0]
    for field in ("method", "notes", "verified_by"):
        check_payload.pop(field)
    assert store_event_in_db(changed) is True

    persisted = read_check(tmp_path)
    assert persisted.method == "rss"
    assert persisted.notes == "feed parsed"
    assert persisted.verified_by == "ingestion"
    assert read_hash(tmp_path, "event-1") == before_hash
    review = read_review(tmp_path, "event-1")
    assert review.status == ReviewStatus.APPROVED
    assert review.previous_decision_json is None


def test_explicit_null_check_field_is_cleared(tmp_path):
    init_database(str(tmp_path / "triangulate.db"))
    base = full_event("event-1")
    assert store_event_in_db(base) is True

    changed = copy.deepcopy(base)
    changed["claims"][0]["evidence"][0]["verification_checks"][0]["notes"] = None
    assert store_event_in_db(changed) is True

    assert read_check(tmp_path).notes is None


def test_new_check_result_adds_record_without_deleting_history(tmp_path):
    """Checks are cumulative observations; a new type/result adds a record."""
    init_database(str(tmp_path / "triangulate.db"))
    base = full_event("event-1")
    assert store_event_in_db(base) is True
    approve_event(tmp_path, "event-1")

    changed = copy.deepcopy(base)
    changed["claims"][0]["evidence"][0]["verification_checks"].append(
        {
            "check_type": "ingestion",
            "result": "failed",
            "method": "rss",
            "notes": "checksum mismatch",
            "verified_by": "ingestion",
        }
    )
    assert store_event_in_db(changed) is True

    session = db_session(tmp_path)
    try:
        checks = (
            session.query(EvidenceVerificationCheck)
            .filter(EvidenceVerificationCheck.evidence_id == read_check(tmp_path).evidence_id)
            .all()
        )
        assert len(checks) == 2
    finally:
        session.close()
    # The original passed check is retained, not replaced.
    assert read_check(tmp_path, "passed").method == "rss"
    review = read_review(tmp_path, "event-1")
    assert review.status == ReviewStatus.PENDING


def test_volatile_capture_metadata_only_preserves_approval(tmp_path):
    """Generated observation/scoring metadata alone is not a semantic change."""
    init_database(str(tmp_path / "triangulate.db"))
    base = full_event("event-1")
    assert store_event_in_db(base) is True
    approve_event(tmp_path, "event-1")
    before = read_hash(tmp_path, "event-1")
    before_reviewed_at = read_review(tmp_path, "event-1").reviewed_at

    changed = copy.deepcopy(base)
    metadata = changed["claims"][0]["evidence"][0]["capture_metadata"]
    metadata["fetched_at"] = "2026-05-01T11:22:33+00:00"
    metadata["relevance_score"] = 0.01
    metadata["queries"] = ["a different regenerated query"]
    assert store_event_in_db(changed) is True

    assert read_hash(tmp_path, "event-1") == before
    review = read_review(tmp_path, "event-1")
    assert review.status == ReviewStatus.APPROVED
    assert review.previous_decision_json is None
    assert review.reviewed_at == before_reviewed_at


def test_party_positions_keyed_by_generated_party_id_normalize(tmp_path):
    """A generated party-ID key projects onto the canonical party name."""
    init_database(str(tmp_path / "triangulate.db"))
    base = full_event("event-1")
    assert store_event_in_db(base) is True
    before = read_hash(tmp_path, "event-1")

    session = db_session(tmp_path)
    try:
        alpha = session.query(Party).filter(Party.canonical_name == "Alpha").one()
        alpha_id = str(alpha.id)
    finally:
        session.close()

    rewritten = copy.deepcopy(base)
    for claim in rewritten["claims"]:
        if claim["party_name"] == "Alpha":
            claim["party_positions"] = {alpha_id: "NEUTRAL"}
    assert store_event_in_db(rewritten) is True
    assert read_hash(tmp_path, "event-1") == before

    # Conflicting values projected onto the same canonical key must raise, not
    # silently drop one of the two positions.
    session = db_session(tmp_path)
    try:
        claim = (
            session.query(Claim)
            .filter(Claim.event_id == "event-1")
            .filter(Claim.claim_text == "Alpha disputes Beta")
            .one()
        )
        claim.party_positions = {alpha_id: "NEUTRAL", "Alpha": "SUPPORTS"}
        session.commit()
    finally:
        session.close()

    with pytest.raises(AnalysisCanonicalizationError):
        read_hash(tmp_path, "event-1")


# ---------------------------------------------------------------------------
# R06 — case-level ``defer`` is an acknowledgement, never a reopen
# ---------------------------------------------------------------------------

DEFER_CASE_ID = "case-defer"
DEFER_EVENT_ID = "event-defer"
EXCEPTION_TS = "2026-03-20T10:00:00+00:00"
EXISTING_CASE_NOTES = "Earlier deferral note."
EXISTING_RESOLUTION_NOTES = "Analyst asked for a second source."


def seed_defer_case(tmp_path, *, status: CaseStatus) -> None:
    """One case-scoped event with an approved, analysis-bound review.

    The case also carries an open exception with existing resolution notes and
    an existing timestamp, and a case-level note from an earlier review.
    """
    init_database(str(tmp_path / "triangulate.db"))
    session = db_session(tmp_path)
    try:
        session.add(
            TopicCase(
                id=DEFER_CASE_ID,
                query="Defer case",
                slug="defer-case",
                status=status,
                current_stage=CaseStageName.REVIEW,
                last_reviewed_at=datetime(2026, 3, 21, 8, 0, tzinfo=UTC),
                review_notes=EXISTING_CASE_NOTES,
                open_review_items=1,
                metadata_json={
                    "exception_queue": [
                        {
                            "id": "exc-defer",
                            "type": "needs_more_sources",
                            "severity": "high",
                            "stage": "RETRIEVE",
                            "status": "open",
                            "message": "Need more sources",
                            "resolution_notes": EXISTING_RESOLUTION_NOTES,
                            "updated_at": EXCEPTION_TS,
                        }
                    ]
                },
            )
        )
        session.add(
            Event(
                id=DEFER_EVENT_ID,
                case_id=DEFER_CASE_ID,
                timestamp=EVENT_TS,
                title="Event",
                summary="Summary",
                verification_status=VerificationStatus.PROBABLE,
            )
        )
        session.flush()
        review = Review(
            id="review-defer",
            event_id=DEFER_EVENT_ID,
            status=ReviewStatus.APPROVED,
            reviewed_at=REVIEW_TS,
            notes="Event analyst note.",
        )
        session.add(review)
        session.flush()
        bind_review_decision(
            review, compute_event_analysis_hash(session, DEFER_EVENT_ID)
        )
        session.commit()
    finally:
        session.close()


def read_defer_case_state(tmp_path) -> dict:
    """Fresh read of every case- and event-level field ``defer`` may touch."""
    session = db_session(tmp_path)
    try:
        case = session.get(TopicCase, DEFER_CASE_ID)
        review = session.query(Review).filter(Review.event_id == DEFER_EVENT_ID).one()
        assert case is not None
        return {
            "status": case.status,
            "stage": case.current_stage,
            "case_review_notes": case.review_notes,
            "last_reviewed_at": case.last_reviewed_at,
            "open_review_items": case.open_review_items,
            "metadata": copy.deepcopy(case.metadata_json),
            "review_status": review.status,
            "review_reviewed_at": review.reviewed_at,
            "event_review_notes": review.notes,
            "analysis_hash": review.analysis_hash,
            "previous_decision_json": copy.deepcopy(review.previous_decision_json),
        }
    finally:
        session.close()


# Everything a case-level acknowledgement must leave exactly as stored. The
# case-level note and ``last_reviewed_at`` are the only permitted changes; the
# generic row ``updated_at`` touch is pre-existing write behavior.
DEFER_PROTECTED_FIELDS = (
    "status",
    "stage",
    "open_review_items",
    "metadata",
    "review_status",
    "review_reviewed_at",
    "event_review_notes",
    "analysis_hash",
    "previous_decision_json",
)


@pytest.mark.parametrize(
    "status",
    [
        CaseStatus.REVIEW_READY,
        CaseStatus.APPROVED,
        CaseStatus.REJECTED,
        CaseStatus.MONITORING,
    ],
)
def test_defer_acknowledges_case_without_reopening_or_touching_decisions(
    tmp_path, status
):
    """R06: ``defer`` keeps the case status, stage, review decision and queue."""
    seed_defer_case(tmp_path, status=status)
    before = read_defer_case_state(tmp_path)
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)

    service.review_case(
        DEFER_CASE_ID, "defer", "Operator deferred; gather one more source."
    )

    after = read_defer_case_state(tmp_path)
    for field in DEFER_PROTECTED_FIELDS:
        assert after[field] == before[field], field
    assert after["status"] == status
    assert after["case_review_notes"] == "Operator deferred; gather one more source."
    assert after["last_reviewed_at"] is not None
    assert after["last_reviewed_at"] != before["last_reviewed_at"]


def test_defer_without_notes_keeps_existing_note_semantics(tmp_path):
    """A deferral with no notes keeps the existing ``review_notes`` update rule."""
    seed_defer_case(tmp_path, status=CaseStatus.APPROVED)
    before = read_defer_case_state(tmp_path)
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)

    service.review_case(DEFER_CASE_ID, "defer")

    after = read_defer_case_state(tmp_path)
    for field in DEFER_PROTECTED_FIELDS:
        assert after[field] == before[field], field
    assert after["case_review_notes"] is None
    assert after["last_reviewed_at"] is not None


def test_defer_invalid_decision_writes_nothing(tmp_path):
    """An unsupported decision is still rejected before any write."""
    seed_defer_case(tmp_path, status=CaseStatus.REJECTED)
    before = read_defer_case_state(tmp_path)
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)

    with pytest.raises(ValueError):
        service.review_case(DEFER_CASE_ID, "deferred", "Not a decision")

    assert read_defer_case_state(tmp_path) == before


def test_ordered_reasoning_reorder_invalidates_but_claim_set_reorder_does_not(tmp_path):
    init_database(str(tmp_path / "triangulate.db"))
    base = full_event("event-1")
    investigation = base["party_investigations"][0]["investigation"]
    investigation["reasoning_steps"] = ["first", "second"]
    investigation["claims_supported"] = [
        {"claim_text": "one", "position": "SUPPORTS"},
        {"claim_text": "two", "position": "CONTRADICTS"},
    ]
    assert store_event_in_db(base) is True
    before = read_hash(tmp_path, "event-1")
    approve_event(tmp_path, "event-1")

    # ``claims_supported`` is a documented unordered claim set.
    equivalent = copy.deepcopy(base)
    equivalent["party_investigations"][0]["investigation"]["claims_supported"] = list(
        reversed(equivalent["party_investigations"][0]["investigation"]["claims_supported"])
    )
    assert store_event_in_db(equivalent) is True
    assert read_hash(tmp_path, "event-1") == before
    assert read_review(tmp_path, "event-1").status == ReviewStatus.APPROVED

    # An arbitrary nested sequence is ordered; reordering it is meaningful.
    reordered = copy.deepcopy(equivalent)
    reordered["party_investigations"][0]["investigation"]["reasoning_steps"] = [
        "second",
        "first",
    ]
    assert store_event_in_db(reordered) is True
    assert read_hash(tmp_path, "event-1") != before
    review = read_review(tmp_path, "event-1")
    assert review.status == ReviewStatus.PENDING
    assert review.previous_decision_json["reason"] == "analysis_changed"
