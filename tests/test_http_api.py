"""Tests for the frontend-facing FastAPI layer."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.cases import TopicCaseService
from src.http.app import app
from src.http.dependencies import get_case_service
from src.storage import CaseStatus, TopicCase, init_database


class StubService:
    """Simple service stub for API contract tests."""

    def __init__(self) -> None:
        self.created_payload = None
        self.review_payload = None
        self.rerun_payload = None
        self.exception_payload = None

    def list_cases(self):
        case = TopicCase(
            id="case-1",
            query="Example case",
            slug="example-case",
            conflict="Global Trade",
            status=CaseStatus.REVIEW_READY,
            routing_mode="exceptions_only",
            article_count=8,
            event_count=3,
            open_review_items=2,
            metadata_json={
                "last_retrieve_changed": True,
                "exception_queue": [
                    {"id": "exc-1", "type": "needs_more_sources", "status": "open"},
                    {"id": "exc-2", "type": "resolved_item", "status": "resolved"},
                ],
            },
            updated_at=datetime(2026, 3, 11, 10, 0, tzinfo=UTC),
        )
        return [case]

    def get_case_details(self, case_id: str):
        if case_id != "case-1":
            return None
        return {
            "case": {
                "id": "case-1",
                "query": "Example case",
                "conflict": "Global Trade",
                "status": "REVIEW_READY",
                "current_stage": "REPORT",
                "routing_mode": "autonomous",
                "report_path": None,
                "latest_manifest_path": None,
                "article_count": 8,
                "event_count": 3,
                "open_review_items": 2,
                "review_notes": None,
                "metadata": {
                    "last_retrieve_changed": True,
                },
                "updated_at": "2026-03-11T10:00:00+00:00",
            },
            "claims": [
                {
                    "id": "claim-1",
                    "event_id": "event-1",
                    "claim_text": "Claim text",
                    "verification_status": "CONFIRMED",
                    "fact_allegation_type": "FACT",
                    "claim_signature": "sig-1",
                    "support_count": 4,
                    "oppose_count": 0,
                    "source_diversity_count": 2,
                    "party_positions": {"Alpha": "SUPPORTS"},
                    "controversy_score": 0.1,
                    "evidence": [
                        {
                            "id": "evidence-1",
                            "relation": "supports",
                            "confidence_score": 0.9,
                            "source_diversity_rank": 1,
                            "title": "Article",
                            "publisher": "Example",
                            "origin_url": "https://example.com/a",
                            "source_type": "rss",
                        }
                    ],
                }
            ],
            "evidence": [
                {
                    "id": "evidence-1",
                    "title": "Article",
                    "origin_url": "https://example.com/a",
                    "canonical_url": "https://example.com/a",
                    "publisher": "Example",
                    "source_type": "rss",
                    "verification_status": "UNVERIFIED",
                    "credibility_tier": "high",
                    "requires_human_review": False,
                    "verification_checks": [],
                }
            ],
            "exceptions": [
                {
                    "id": "exc-1",
                    "type": "needs_more_sources",
                    "message": "Need more sources",
                    "severity": "medium",
                    "recommended_action": "Provide more links",
                    "status": "open",
                },
                {
                    "id": "exc-2",
                    "type": "resolved_item",
                    "message": "Already handled",
                    "severity": "low",
                    "recommended_action": "None",
                    "status": "resolved",
                },
            ],
            "parties": [
                {
                    "id": "party-1",
                    "canonical_name": "Alpha",
                    "aliases": ["Alpha"],
                    "description": "Party A",
                    "is_bootstrap_confirmed": True,
                }
            ],
            "events": [
                {
                    "id": "event-1",
                    "timestamp": "2026-03-11T09:00:00+00:00",
                    "title": "Event",
                    "summary": "Summary",
                    "verification_status": "CONFIRMED",
                }
            ],
            "stage_runs": [
                {
                    "id": "run-1",
                    "stage": "INVESTIGATE",
                    "status": "COMPLETED",
                    "started_at": "2026-03-11T09:00:00+00:00",
                    "duration_ms": 1200,
                    "model_used": "test-model",
                    "fallback_count": 1,
                    "parse_failure_count": 0,
                    "error_message": None,
                }
            ],
            "party_investigations": [],
        }

    def review_case(self, case_id: str, decision: str, notes: str | None = None):
        self.review_payload = {"case_id": case_id, "decision": decision, "notes": notes}
        return TopicCase(
            id=case_id,
            query="Example case",
            slug="example-case",
            conflict="Global Trade",
            status=CaseStatus.REVIEW_READY,
        )

    async def rerun_case(self, case_id: str, start_stage=None, output_dir=None):
        self.rerun_payload = {
            "case_id": case_id,
            "start_stage": start_stage.value if start_stage else None,
            "output_dir": str(output_dir) if output_dir else None,
        }
        return TopicCase(
            id=case_id,
            query="Example case",
            slug="example-case",
            conflict="Global Trade",
            status=CaseStatus.REVIEW_READY,
        )

    def update_exception_status(
        self,
        case_id: str,
        exception_id: str,
        *,
        action: str,
        notes: str | None = None,
    ):
        self.exception_payload = {
            "case_id": case_id,
            "exception_id": exception_id,
            "action": action,
            "notes": notes,
        }
        return TopicCase(
            id=case_id,
            query="Example case",
            slug="example-case",
            conflict="Global Trade",
            status=CaseStatus.REVIEW_READY,
        )

    async def run_case(self, **kwargs):
        self.created_payload = kwargs
        return TopicCase(
            id="new-case",
            query=kwargs["query"],
            slug="new-case",
            conflict=kwargs.get("conflict"),
            status=CaseStatus.REVIEW_READY,
            article_count=0,
            event_count=0,
        )


@pytest.fixture
def client():
    service = StubService()
    app.dependency_overrides[get_case_service] = lambda: service
    try:
        yield TestClient(app), service
    finally:
        app.dependency_overrides.clear()


def test_health_returns_ok(client):
    test_client, _service = client
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_cases_maps_frontend_shape(client):
    test_client, _service = client
    response = test_client.get("/api/cases")
    assert response.status_code == 200

    payload = response.json()
    assert payload == [
        {
            "id": "case-1",
            "query": "Example case",
            "conflictDomain": "Global Trade",
            "status": "review ready",
            "stage": "BOOTSTRAP",
            "counts": {"articles": 8, "events": 3, "reviewItems": 2},
            "reportPath": None,
            "automationMode": "safe",
            "hasNewMaterial": True,
            "openExceptionsCount": 1,
            "lastUpdated": "2026-03-11T10:00:00+00:00",
        }
    ]


def test_get_case_not_found_returns_404(client):
    test_client, _service = client
    response = test_client.get("/api/cases/missing")
    assert response.status_code == 404


def test_get_case_counts_only_open_exceptions(client):
    test_client, _service = client
    response = test_client.get("/api/cases/case-1")
    assert response.status_code == 200
    assert response.json()["case"]["openExceptionsCount"] == 1
    assert response.json()["case"]["automationMode"] == "autonomous"


def test_tab_endpoints_return_frontend_slices(client):
    test_client, _service = client

    claims = test_client.get("/api/cases/case-1/claims")
    claims_overview = test_client.get("/api/cases/case-1/claims/overview")
    evidence = test_client.get("/api/cases/case-1/evidence")
    exceptions = test_client.get("/api/cases/case-1/exceptions")
    parties = test_client.get("/api/cases/case-1/parties")
    timeline = test_client.get("/api/cases/case-1/timeline")
    run_history = test_client.get("/api/cases/case-1/run-history")
    report = test_client.get("/api/cases/case-1/report")

    assert claims.json()[0]["text"] == "Claim text"
    assert claims_overview.json()["claims"][0]["text"] == "Claim text"
    assert evidence.json()[0]["linkedClaims"] == ["claim-1"]
    assert exceptions.json()[0]["recommendedAction"] == "Provide more links"
    assert exceptions.json()[0]["status"] == "open"
    assert parties.json()[0]["name"] == "Alpha"
    assert parties.json()[0]["isModelInferred"] is False
    assert timeline.json()[0]["linkedEvidenceCount"] == 1
    assert run_history.json()[0]["status"] == "success"
    assert report.json()["status"] == "pending"
    assert exceptions.json()[1]["isOpen"] is False


def test_mutation_routes_are_not_exposed(client):
    test_client, _service = client

    assert test_client.post("/api/cases", json={"query": "New case"}).status_code == 405
    assert test_client.post(
        "/api/cases/case-1/review",
        json={"decision": "action_required"},
    ).status_code == 404
    assert test_client.post(
        "/api/cases/case-1/rerun",
        json={"fromStage": "RETRIEVE"},
    ).status_code == 404
    assert test_client.post(
        "/api/cases/case-1/exceptions/exc-1",
        json={"action": "resolve"},
    ).status_code == 404


class FakePartyWorkflow:
    async def ainvoke(self, state):
        return {
            "parties": {"parties": [{"canonical_name": "Alpha", "aliases": ["Alpha"]}]},
            "party_investigations": [],
            "final_determinations": [],
            "event_summary": {"verification_distribution": {"PROBABLE": 1}},
        }


def make_real_service(tmp_path: Path) -> TopicCaseService:
    init_database(str(tmp_path / "triangulate.db"))
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
    service.party_workflow = FakePartyWorkflow()
    return service


@pytest.mark.asyncio
async def test_api_smoke_with_real_service(monkeypatch, tmp_path):
    service = make_real_service(tmp_path)

    async def fake_fetch(*args, **kwargs):
        return {
            "articles": [
                {
                    "url": "https://example.com/a",
                    "title": "Article A",
                    "source": "Example",
                    "published_at": "2026-03-08T12:00:00+00:00",
                    "content": "Alpha update",
                    "relevance_score": 0.9,
                }
            ],
            "conflict": "trade",
            "queries_generated": ["alpha"],
            "sources_used": ["Example"],
            "articles_fetched": 1,
            "articles_processed": 1,
        }

    async def fake_process(article):
        return {
            "id": "temporary",
            "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
            "title": article["title"],
            "summary": article["content"],
            "verification_status": "PROBABLE",
            "claims": [
                {
                    "claim": "Alpha happened",
                    "who": ["Alpha"],
                    "verification_status": "PROBABLE",
                }
            ],
            "narratives": [{"cluster_id": "0", "stance_summary": "Narrative", "claim_count": 1}],
            "parties": [{"canonical_name": "Alpha", "aliases": ["Alpha"]}],
        }

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", fake_fetch)
    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)

    case = await service.run_case(query="Alpha", output_dir=tmp_path)

    app.dependency_overrides[get_case_service] = lambda: service
    try:
        client = TestClient(app)
        list_response = client.get("/api/cases")
        detail_response = client.get(f"/api/cases/{case.id}")
        assert list_response.status_code == 200
        assert detail_response.status_code == 200
        assert list_response.json()[0]["id"] == case.id
        assert detail_response.json()["case"]["query"] == "Alpha"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_report_download_endpoints(monkeypatch, tmp_path):
    service = make_real_service(tmp_path)

    async def fake_fetch(*args, **kwargs):
        return {
            "articles": [
                {
                    "url": "https://example.com/a",
                    "title": "Article A",
                    "source": "Example",
                    "published_at": "2026-03-08T12:00:00+00:00",
                    "content": "Alpha update",
                    "relevance_score": 0.9,
                }
            ],
            "conflict": "trade",
            "queries_generated": ["alpha"],
            "sources_used": ["Example"],
            "articles_fetched": 1,
            "articles_processed": 1,
        }

    async def fake_process(article):
        return {
            "id": "temporary",
            "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
            "title": article["title"],
            "summary": article["content"],
            "verification_status": "PROBABLE",
            "claims": [
                {
                    "claim": "Alpha happened",
                    "who": ["Alpha"],
                    "verification_status": "PROBABLE",
                }
            ],
            "narratives": [{"cluster_id": "0", "stance_summary": "Narrative", "claim_count": 1}],
            "parties": [{"canonical_name": "Alpha", "aliases": ["Alpha"]}],
        }

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", fake_fetch)
    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)

    case = await service.run_case(query="Alpha report", output_dir=tmp_path, automation_mode="autonomous")

    app.dependency_overrides[get_case_service] = lambda: service
    try:
        client = TestClient(app)
        markdown_response = client.get(f"/api/cases/{case.id}/report/markdown")
        manifest_response = client.get(f"/api/cases/{case.id}/report/manifest")
        assert markdown_response.status_code == 200
        assert "Alpha report" in markdown_response.text
        assert manifest_response.status_code == 200
        assert json.loads(manifest_response.text)["case_id"] == case.id
    finally:
        app.dependency_overrides.clear()
