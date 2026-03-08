"""Tests for topic case orchestration."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.cases import TopicCaseService
from src.storage import (
    CaseArticle,
    CaseStageRun,
    CaseStatus,
    Event,
    Review,
    ReviewStatus,
    TopicCase,
    VerificationStatus,
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
        assert len(stage_runs) == 5

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
