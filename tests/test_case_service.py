"""Tests for topic case orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.cases import TopicCaseService
from src.storage import (
    CaseArticle,
    CaseStageName,
    CaseStageRun,
    CaseStatus,
    EvidenceItem,
    Event,
    Review,
    ReviewStatus,
    TopicCase,
    VerificationStatus,
    Claim,
    init_database,
)


class FakePartyWorkflow:
    """Small async stub for the party workflow."""

    async def ainvoke(self, state):
        return {
            "parties": {
                "parties": [
                    {"canonical_name": "Alpha", "aliases": ["Alpha"]},
                    {"canonical_name": "Beta", "aliases": ["Beta"]},
                ]
            },
            "party_investigations": [
                {
                    "party_name": "Alpha",
                    "investigation": {"claims_supported": [0], "claims_contested": []},
                    "party_stance": {"overall_position": "Supports"},
                }
            ],
            "final_determinations": [
                {
                    "claim_text": "Claim routed through arbiter",
                    "verification_status": "CONTESTED",
                    "fact_allegation_classification": "FACT",
                    "reasoning": "Conflicting positions",
                    "party_positions": {"Alpha": "SUPPORTS", "Beta": "CONTESTS"},
                    "controversy_score": 0.8,
                }
            ],
            "event_summary": {
                "verification_distribution": {"CONTESTED": 1},
                "party_agreement_level": "LOW",
                "controversy_score": 0.8,
            },
        }


def make_service(tmp_path: Path) -> TopicCaseService:
    init_database(str(tmp_path / "triangulate.db"))
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
    service.party_workflow = FakePartyWorkflow()
    return service


@pytest.mark.asyncio
async def test_case_lifecycle_and_party_routing(monkeypatch, tmp_path):
    """Case pipeline persists stages, events, and report bundle."""
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
                }
            ],
            "conflict": "ukraine_war",
            "queries_generated": ["alpha beta dispute"],
            "sources_used": ["Example"],
            "articles_fetched": 1,
            "articles_processed": 1,
        }

    async def fake_process(article):
        return {
            "id": "temporary",
            "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
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
                {
                    "cluster_id": "0",
                    "stance_summary": "Dispute narrative",
                    "claim_count": 1,
                }
            ],
            "parties": [
                {"canonical_name": "Alpha", "aliases": ["Alpha"]},
                {"canonical_name": "Beta", "aliases": ["Beta"]},
            ],
        }

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", fake_fetch)
    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)

    case = await service.run_case(query="Alpha Beta dispute", output_dir=tmp_path)

    assert case.status == CaseStatus.REVIEW_READY
    assert case.report_path is not None
    assert Path(case.report_path).exists()

    session = init_database(str(tmp_path / "triangulate.db")).get_session_sync()
    try:
        stored_case = session.query(TopicCase).filter(TopicCase.id == case.id).first()
        assert stored_case is not None
        assert stored_case.article_count == 1
        assert stored_case.event_count == 1

        stage_runs = (
            session.query(CaseStageRun)
            .filter(CaseStageRun.case_id == case.id)
            .all()
        )
        assert len(stage_runs) == 6

        event = session.query(Event).filter(Event.case_id == case.id).first()
        assert event is not None
        assert event.verification_status.value == "CONTESTED"

        review = session.query(Review).filter(Review.event_id == event.id).first()
        assert review is not None
        assert review.status == ReviewStatus.PENDING
    finally:
        session.close()


@pytest.mark.asyncio
async def test_monitor_cycle_deduplicates_articles(monkeypatch, tmp_path):
    """Repeated monitor runs update the case without duplicating URLs."""
    service = make_service(tmp_path)
    payload = {
        "articles": [
            {
                "url": "https://example.com/a",
                "title": "Article A",
                "source": "Example",
                "published_at": "2026-03-08T12:00:00+00:00",
                "content": "Alpha and Beta disagree.",
                "relevance_score": 0.9,
            }
        ],
        "conflict": "ukraine_war",
        "queries_generated": ["alpha beta dispute"],
        "sources_used": ["Example"],
        "articles_fetched": 1,
        "articles_processed": 1,
    }

    async def fake_fetch(*args, **kwargs):
        return payload

    async def fake_process(article):
        return {
            "id": "temporary",
            "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
            "title": article["title"],
            "summary": article["content"][:500],
            "verification_status": "PROBABLE",
            "claims": [{"claim": "Claim", "who": ["Alpha"], "verification_status": "PROBABLE"}],
            "narratives": [{"cluster_id": "0", "stance_summary": "Narrative", "claim_count": 1}],
            "parties": [{"canonical_name": "Alpha", "aliases": ["Alpha"]}],
        }

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", fake_fetch)
    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)

    first = await service.run_case(query="Alpha monitor", output_dir=tmp_path, monitor_mode=True)
    second = await service.run_case(query="Alpha monitor", output_dir=tmp_path, monitor_mode=True)

    assert first.id == second.id

    session = init_database(str(tmp_path / "triangulate.db")).get_session_sync()
    try:
        articles = session.query(CaseArticle).filter(CaseArticle.case_id == first.id).all()
        assert len(articles) == 1
        assert articles[0].is_new == 0
    finally:
        session.close()


@pytest.mark.asyncio
async def test_monitor_cycle_deduplicates_evidence(monkeypatch, tmp_path):
    """Repeated runs should reuse equivalent evidence rows for the same article."""
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
                }
            ],
            "conflict": "ukraine_war",
            "queries_generated": ["alpha beta dispute"],
            "sources_used": ["Example"],
            "articles_fetched": 1,
            "articles_processed": 1,
        }

    async def fake_process(article):
        return {
            "id": "temporary",
            "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
            "title": article["title"],
            "summary": article["content"][:500],
            "verification_status": "PROBABLE",
            "claims": [{"claim": "Claim", "who": ["Alpha"], "verification_status": "PROBABLE"}],
            "narratives": [{"cluster_id": "0", "stance_summary": "Narrative", "claim_count": 1}],
            "parties": [{"canonical_name": "Alpha", "aliases": ["Alpha"]}],
        }

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", fake_fetch)
    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)

    case = await service.run_case(query="Alpha evidence", output_dir=tmp_path, monitor_mode=True)
    await service.run_case(query="Alpha evidence", output_dir=tmp_path, monitor_mode=True)

    session = init_database(str(tmp_path / "triangulate.db")).get_session_sync()
    try:
        evidence = session.query(EvidenceItem).filter(EvidenceItem.case_id == case.id).all()
        assert len(evidence) == 1
    finally:
        session.close()


@pytest.mark.asyncio
async def test_case_run_allows_same_claim_text_across_multiple_events(monkeypatch, tmp_path):
    """Repeated claim text in different articles should not collide on claim IDs."""
    service = make_service(tmp_path)

    async def fake_fetch(*args, **kwargs):
        return {
            "articles": [
                {
                    "url": "https://example.com/a",
                    "title": "Article A",
                    "source": "Example",
                    "published_at": "2026-03-08T12:00:00+00:00",
                    "content": "Alpha repeated claim.",
                    "relevance_score": 0.9,
                },
                {
                    "url": "https://example.com/b",
                    "title": "Article B",
                    "source": "Example",
                    "published_at": "2026-03-08T13:00:00+00:00",
                    "content": "Alpha repeated claim again.",
                    "relevance_score": 0.8,
                },
            ],
            "conflict": "ukraine_war",
            "queries_generated": ["alpha repeated claim"],
            "sources_used": ["Example"],
            "articles_fetched": 2,
            "articles_processed": 2,
        }

    async def fake_process(article):
        return {
            "id": "temporary",
            "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
            "title": article["title"],
            "summary": article["content"][:500],
            "verification_status": "PROBABLE",
            "claims": [
                {
                    "claim": "Alpha repeated claim",
                    "who": ["Alpha"],
                    "verification_status": "PROBABLE",
                }
            ],
            "narratives": [
                {
                    "cluster_id": "0",
                    "stance_summary": "Narrative",
                    "claim_count": 1,
                }
            ],
            "parties": [{"canonical_name": "Alpha", "aliases": ["Alpha"]}],
        }

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", fake_fetch)
    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)

    case = await service.run_case(query="Alpha repeated claim", output_dir=tmp_path)

    session = init_database(str(tmp_path / "triangulate.db")).get_session_sync()
    try:
        events = session.query(Event).filter(Event.case_id == case.id).all()
        assert len(events) == 2

        claims = (
            session.query(Claim)
            .join(Event, Claim.event_id == Event.id)
            .filter(Event.case_id == case.id)
            .all()
        )
        assert len(claims) == 2
    finally:
        session.close()


@pytest.mark.asyncio
async def test_case_details_returns_serialized_read_model(monkeypatch, tmp_path):
    """Case detail payload should be frontend-ready and include canonical exceptions."""
    service = make_service(tmp_path)

    async def fake_fetch(*args, **kwargs):
        return {
            "articles": [],
            "conflict": "ukraine_war",
            "queries_generated": ["alpha beta dispute"],
            "sources_used": [],
            "articles_fetched": 0,
            "articles_processed": 0,
            "fetch_exceptions": [
                {
                    "type": "source_fetch_failure",
                    "message": "Unsupported fetch strategy 'web'.",
                    "severity": "high",
                }
            ],
        }

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", fake_fetch)

    case = await service.run_case(query="Serialized detail", output_dir=tmp_path, start_stage=CaseStageName.RETRIEVE)
    detail = service.get_case_details(case.id)

    assert detail is not None
    assert detail["case"]["id"] == case.id
    assert isinstance(detail["stage_runs"], list)
    assert detail["exceptions"][0]["type"] == "source_fetch_failure"
    assert detail["exceptions"][0]["severity"] == "high"


@pytest.mark.asyncio
async def test_case_details_include_non_numeric_cluster_ids(monkeypatch, tmp_path):
    """Case detail payload should include stored narratives regardless of cluster ID format."""
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
                }
            ],
            "conflict": "ukraine_war",
            "queries_generated": ["alpha beta dispute"],
            "sources_used": ["Example"],
            "articles_fetched": 1,
            "articles_processed": 1,
        }

    async def fake_process(article):
        return {
            "id": "temporary",
            "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
            "title": article["title"],
            "summary": article["content"][:500],
            "verification_status": "PROBABLE",
            "claims": [{"claim": "Claim", "who": ["Alpha"], "verification_status": "PROBABLE"}],
            "narratives": [
                {
                    "cluster_id": "topic-12",
                    "stance_summary": "Narrative",
                    "claim_count": 1,
                }
            ],
            "parties": [{"canonical_name": "Alpha", "aliases": ["Alpha"]}],
        }

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", fake_fetch)
    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)

    case = await service.run_case(query="Narrative detail", output_dir=tmp_path)
    detail = service.get_case_details(case.id)

    assert detail is not None
    assert detail["narratives"]
    assert detail["narratives"][0]["cluster_id"].endswith(":topic-12")


@pytest.mark.asyncio
async def test_rerun_from_retrieve_reuses_bootstrap_context(monkeypatch, tmp_path):
    """Later-stage reruns should preserve stored bootstrap inputs."""
    service = make_service(tmp_path)
    fetch_calls: list[dict[str, object]] = []

    async def fake_fetch(*args, **kwargs):
        fetch_calls.append(kwargs)
        return {
            "articles": [
                {
                    "url": "https://example.com/a",
                    "title": "Article A",
                    "source": "Example",
                    "published_at": "2026-03-08T12:00:00+00:00",
                    "content": "Alpha and Beta disagree.",
                    "relevance_score": 0.9,
                }
            ],
            "conflict": kwargs.get("conflict", "ukraine_war"),
            "queries_generated": ["alpha beta dispute"],
            "sources_used": ["Example"],
            "articles_fetched": 1,
            "articles_processed": 1,
        }

    async def fake_process(article):
        return {
            "id": "temporary",
            "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
            "title": article["title"],
            "summary": article["content"][:500],
            "verification_status": "PROBABLE",
            "claims": [{"claim": "Claim", "who": ["Alpha"], "verification_status": "PROBABLE"}],
            "narratives": [{"cluster_id": "0", "stance_summary": "Narrative", "claim_count": 1}],
            "parties": [{"canonical_name": "Alpha", "aliases": ["Alpha"]}],
        }

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", fake_fetch)
    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)

    case = await service.run_case(
        query="Bootstrap reuse",
        output_dir=tmp_path,
        conflict="ukraine_war",
        confirmed_parties=["Alpha"],
        manual_links=["https://manual.example/source"],
    )

    await service.rerun_case(case.id, start_stage=CaseStageName.RETRIEVE, output_dir=tmp_path)

    assert len(fetch_calls) == 2
    assert fetch_calls[1]["conflict"] == "ukraine_war"
    assert fetch_calls[1]["confirmed_parties"] == ["Alpha"]
    assert fetch_calls[1]["manual_links"] == ["https://manual.example/source"]


@pytest.mark.asyncio
async def test_monitor_rerun_keeps_total_event_count(monkeypatch, tmp_path):
    """Monitor reruns should not shrink persisted event counts when triage processes a subset."""
    service = make_service(tmp_path)

    async def fake_fetch(*args, **kwargs):
        return {
            "articles": [
                {
                    "url": "https://example.com/a",
                    "title": "Article A",
                    "source": "Example",
                    "published_at": "2026-03-08T12:00:00+00:00",
                    "content": "Alpha update A.",
                    "relevance_score": 0.9,
                },
                {
                    "url": "https://example.com/b",
                    "title": "Article B",
                    "source": "Example",
                    "published_at": "2026-03-08T13:00:00+00:00",
                    "content": "Alpha update B.",
                    "relevance_score": 0.8,
                },
            ],
            "conflict": "ukraine_war",
            "queries_generated": ["alpha update"],
            "sources_used": ["Example"],
            "articles_fetched": 2,
            "articles_processed": 2,
        }

    async def fake_process(article):
        return {
            "id": "temporary",
            "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
            "title": article["title"],
            "summary": article["content"][:500],
            "verification_status": "PROBABLE",
            "claims": [{"claim": article["title"], "who": ["Alpha"], "verification_status": "PROBABLE"}],
            "narratives": [{"cluster_id": article["title"], "stance_summary": "Narrative", "claim_count": 1}],
            "parties": [{"canonical_name": "Alpha", "aliases": ["Alpha"]}],
        }

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", fake_fetch)
    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)

    case = await service.run_case(query="Alpha monitor subset", output_dir=tmp_path)
    rerun = await service.run_case(
        query="Alpha monitor subset",
        output_dir=tmp_path,
        monitor_mode=True,
        max_articles=1,
        case_id=case.id,
    )

    session = init_database(str(tmp_path / "triangulate.db")).get_session_sync()
    try:
        stored_case = session.query(TopicCase).filter(TopicCase.id == rerun.id).first()
        assert stored_case is not None
        assert stored_case.event_count == 2
    finally:
        session.close()


@pytest.mark.asyncio
async def test_case_details_keep_parties_when_reused_by_later_case(monkeypatch, tmp_path):
    """Case detail party lists should survive when a shared party is reused in another case."""
    service = make_service(tmp_path)

    async def fake_fetch(*args, **kwargs):
        query = kwargs["query"]
        slug = query.replace(" ", "-").lower()
        return {
            "articles": [
                {
                    "url": f"https://example.com/{slug}",
                    "title": query,
                    "source": "Example",
                    "published_at": "2026-03-08T12:00:00+00:00",
                    "content": f"{query} content.",
                    "relevance_score": 0.9,
                }
            ],
            "conflict": "ukraine_war",
            "queries_generated": [query],
            "sources_used": ["Example"],
            "articles_fetched": 1,
            "articles_processed": 1,
        }

    async def fake_process(article):
        return {
            "id": "temporary",
            "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
            "title": article["title"],
            "summary": article["content"][:500],
            "verification_status": "CONTESTED",
            "claims": [
                {
                    "claim": "Shared claim",
                    "who": ["Alpha", "Beta"],
                    "verification_status": "ALLEGED",
                }
            ],
            "narratives": [{"cluster_id": "0", "stance_summary": "Narrative", "claim_count": 1}],
            "parties": [
                {"canonical_name": "Alpha", "aliases": ["Alpha"]},
                {"canonical_name": "Beta", "aliases": ["Beta"]},
            ],
        }

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", fake_fetch)
    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)

    first = await service.run_case(query="First party case", output_dir=tmp_path)
    await service.run_case(query="Second party case", output_dir=tmp_path)

    detail = service.get_case_details(first.id)

    assert detail is not None
    assert [party["canonical_name"] for party in detail["parties"]] == ["Alpha", "Beta"]


def test_review_case_transitions(tmp_path):
    """Case review updates the case and underlying event reviews."""
    service = make_service(tmp_path)
    session = init_database(str(tmp_path / "triangulate.db")).get_session_sync()
    try:
        case = TopicCase(
            id="case-1",
            query="Test",
            slug="test",
            status=CaseStatus.REVIEW_READY,
        )
        event = Event(
            id="event-1",
            case_id="case-1",
            timestamp=datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
            title="Event",
            summary="Summary",
            verification_status=VerificationStatus.PROBABLE,
        )
        review = Review(id="review-1", event_id="event-1", status=ReviewStatus.PENDING)
        session.add(case)
        session.add(event)
        session.add(review)
        session.commit()
    finally:
        session.close()

    reviewed = service.review_case("case-1", "approve", "Ship it")
    assert reviewed.status == CaseStatus.APPROVED

    session = init_database(str(tmp_path / "triangulate.db")).get_session_sync()
    try:
        review = session.query(Review).filter(Review.id == "review-1").first()
        assert review.status == ReviewStatus.APPROVED
    finally:
        session.close()
