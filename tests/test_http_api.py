"""Tests for the frontend-facing FastAPI layer."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.cases import TopicCaseService
from src.http.app import app
from src.http.dependencies import get_case_service
from src.storage import (
    CaseStageName,
    CaseStatus,
    EvaluationRun,
    Event,
    Review,
    ReviewAnnotation,
    ReviewAuditEntry,
    ReviewStatus,
    TopicCase,
    VerificationStatus,
    claim_case_ownership,
    get_database,
    init_database,
    release_case_ownership,
)
from src.storage.review_state import (
    bind_review_decision,
    compute_event_analysis_hash,
)


class StubService:
    """Simple service stub for API contract tests."""

    def __init__(self) -> None:
        self.created_payload = None
        self.review_payload = None
        self.rerun_payload = None
        self.exception_payload = None
        self.annotation_payload = None

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
            "osint_artifacts": [
                {
                    "id": "artifact-1",
                    "tool": "spiderfoot",
                    "artifact_type": "json",
                    "source_path": "/tmp/spiderfoot.json",
                    "imported_at": "2026-03-11T08:50:00+00:00",
                    "import_metadata": {"import_mode": "cli"},
                }
            ],
            "workflow": {
                "taxonomy": {
                    "id": "taxonomy-1",
                    "kind": "bias_review",
                    "version": "2026.03.24",
                    "path": "./bias_taxonomy.toml",
                    "checksum": "abc123",
                },
                "checkpoints": [
                    {
                        "id": "checkpoint-1",
                        "stage_name": "INVESTIGATE",
                        "checkpoint_key": "investigate:completed",
                        "status": "completed",
                        "summary": "INVESTIGATE completed successfully.",
                        "retry_count": 0,
                        "payload": {"event_count": 1},
                        "created_at": "2026-03-11T09:00:05+00:00",
                    }
                ],
                "agent_outputs": [
                    {
                        "id": "output-1",
                        "stage_name": "INVESTIGATE",
                        "agent_name": "workflow_router",
                        "output_type": "stage_result",
                        "summary": "INVESTIGATE completed successfully.",
                        "payload": {"event_count": 1},
                        "taxonomy_version_id": "taxonomy-1",
                        "created_at": "2026-03-11T09:00:05+00:00",
                    }
                ],
            },
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

    def get_case_review_activity(self, case_id: str):
        return {
            "annotations": [
                {
                    "id": "annotation-1",
                    "target_type": "case",
                    "target_id": case_id,
                    "annotation_type": "comment",
                    "author": "operator",
                    "content": "Need one more source.",
                    "metadata": {},
                    "created_at": "2026-03-11T10:01:00+00:00",
                }
            ],
            "audit_entries": [
                {
                    "id": "audit-1",
                    "action_type": "review:action_required",
                    "target_type": "case",
                    "target_id": case_id,
                    "actor": "operator",
                    "rationale": "Need another source.",
                    "metadata": {},
                    "created_at": "2026-03-11T10:02:00+00:00",
                }
            ],
        }

    def add_review_annotation(
        self,
        case_id: str,
        *,
        target_type: str,
        target_id: str,
        annotation_type: str,
        content: str,
        author: str = "operator",
        metadata: dict | None = None,
    ):
        self.annotation_payload = {
            "case_id": case_id,
            "target_type": target_type,
            "target_id": target_id,
            "annotation_type": annotation_type,
            "content": content,
            "author": author,
            "metadata": metadata or {},
        }
        return {
            "id": "annotation-2",
            "target_type": target_type,
            "target_id": target_id,
            "annotation_type": annotation_type,
            "author": author,
            "content": content,
            "metadata": metadata or {},
            "created_at": "2026-03-11T10:03:00+00:00",
        }

    def get_case_evaluation_summary(self, case_id: str):
        return {
            "latest": {
                "id": "eval-1",
                "status": "completed",
                "evaluation_kind": "case_quality",
                "summary": {"overall_score": 0.81},
                "metrics": {"evidence_linkage": 1.0, "review_burden": 0.6},
                "created_at": "2026-03-11T10:05:00+00:00",
            },
            "history": [],
        }

    def get_monitoring_summary(self):
        return {
            "cases": {"total": 1, "review_ready": 1, "active": 1},
            "review": {"open_exceptions": 1, "backlog": 2},
            "pipeline": {"running_stage_runs": 0, "failed_stage_runs": 0, "avg_duration_ms": 1200},
            "intake": {"pending_items": 0, "processed_items": 1},
            "evaluation": {"recent_runs": 1, "avg_overall_score": 0.81},
        }

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


def test_get_case_workflow_returns_diagnostics(client):
    test_client, _service = client
    response = test_client.get("/api/cases/case-1/workflow")
    assert response.status_code == 200
    payload = response.json()
    assert payload["taxonomy"]["version"] == "2026.03.24"
    assert payload["checkpoints"][0]["checkpointKey"] == "investigate:completed"
    assert payload["agentOutputs"][0]["agentName"] == "workflow_router"


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


def test_mutation_routes_support_narrow_hitl_actions(client):
    test_client, _service = client

    assert test_client.post("/api/cases", json={"query": "New case"}).status_code == 405
    review_response = test_client.post(
        "/api/cases/case-1/review",
        json={"decision": "action_required"},
    )
    assert review_response.status_code == 404
    assert test_client.post("/api/cases/case-1/rerun", json={"fromStage": "RETRIEVE"}).status_code == 404

    review_action = test_client.post(
        "/api/cases/case-1/review-actions/review",
        json={"decision": "action_required", "notes": "Need more sources"},
    )
    exception_action = test_client.post(
        "/api/cases/case-1/review-actions/exceptions/exc-1",
        json={"action": "resolve"},
    )
    annotation = test_client.post(
        "/api/cases/case-1/annotations",
        json={
            "targetType": "case",
            "targetId": "case-1",
            "annotationType": "comment",
            "content": "Operator note",
        },
    )

    assert review_action.status_code == 200
    assert exception_action.status_code == 200
    assert annotation.status_code == 200


def test_review_activity_and_monitoring_endpoints(client):
    test_client, _service = client

    activity = test_client.get("/api/cases/case-1/review-activity")
    evaluation = test_client.get("/api/cases/case-1/evaluation")
    monitoring = test_client.get("/api/monitoring/summary")

    assert activity.status_code == 200
    assert activity.json()["annotations"][0]["annotationType"] == "comment"
    assert evaluation.status_code == 200
    assert evaluation.json()["latest"]["summary"]["overall_score"] == 0.81
    assert monitoring.status_code == 200
    assert monitoring.json()["review"]["open_exceptions"] == 1


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


def _add_eval_case(case_id: str = "case-eval") -> None:
    session = get_database().get_session_sync()
    try:
        session.add(
            TopicCase(
                id=case_id,
                query="Evaluation case",
                slug=case_id,
                status=CaseStatus.REVIEW_READY,
            )
        )
        session.commit()
    finally:
        session.close()


def _evaluation_read_state() -> tuple[int, int, str | None, str | None]:
    """Return stored evaluation/audit row counts and the case writer owner."""
    session = get_database().get_session_sync()
    try:
        evaluations = session.scalars(
            select(EvaluationRun).where(EvaluationRun.case_id == "case-eval")
        ).all()
        audit_entries = session.scalars(
            select(ReviewAuditEntry).where(ReviewAuditEntry.case_id == "case-eval")
        ).all()
        case_row = session.get(TopicCase, "case-eval")
        assert case_row is not None
        return (
            len(evaluations),
            len(audit_entries),
            case_row.owner_token,
            case_row.owner_kind,
        )
    finally:
        session.close()


def _fail_if_called(*args, **kwargs):
    raise AssertionError("evaluation GET must never generate an evaluation run")


def _get_evaluation_twice(service) -> list:
    app.dependency_overrides[get_case_service] = lambda: service
    try:
        client = TestClient(app)
        return [
            client.get("/api/cases/case-eval/evaluation"),
            client.get("/api/cases/case-eval/evaluation"),
        ]
    finally:
        app.dependency_overrides.clear()


def test_case_evaluation_get_without_runs_is_read_only(monkeypatch, tmp_path):
    """A case with no stored evaluation yields an empty summary and writes nothing."""
    service = make_real_service(tmp_path)
    _add_eval_case()
    monkeypatch.setattr(service, "evaluate_case", _fail_if_called)

    responses = _get_evaluation_twice(service)

    for response in responses:
        assert response.status_code == 200
        assert response.json() == {"latest": None, "history": []}
    assert _evaluation_read_state() == (0, 0, None, None)


def test_case_evaluation_get_returns_stored_run_without_writing(monkeypatch, tmp_path):
    """An explicit evaluate_case run is returned verbatim; reads add nothing."""
    service = make_real_service(tmp_path)
    _add_eval_case()
    evaluation = service.evaluate_case("case-eval")
    before = _evaluation_read_state()
    assert before == (1, 1, None, None)

    monkeypatch.setattr(service, "evaluate_case", _fail_if_called)

    responses = _get_evaluation_twice(service)

    for response in responses:
        assert response.status_code == 200
        payload = response.json()
        assert payload["latest"]["id"] == evaluation["id"]
        assert (
            payload["latest"]["summary"]["overall_score"]
            == evaluation["summary"]["overall_score"]
        )
        assert [item["id"] for item in payload["history"]] == [evaluation["id"]]
    assert _evaluation_read_state() == before


def test_case_evaluation_summary_missing_case_still_errors(tmp_path):
    service = make_real_service(tmp_path)

    with pytest.raises(ValueError):
        service.get_case_evaluation_summary("missing-case")


# ---------------------------------------------------------------------------
# Narrow HITL write contract: validation, normalization, and route surface
# ---------------------------------------------------------------------------

REVIEW_ACTION_PATH = "/api/cases/case-1/review-actions/review"
EXCEPTION_ACTION_PATH = "/api/cases/case-1/review-actions/exceptions/exc-1"
ANNOTATION_PATH = "/api/cases/case-1/annotations"


def _annotation_payload(**overrides) -> dict:
    payload = {
        "targetType": "case",
        "targetId": "case-1",
        "annotationType": "comment",
        "content": "Operator note",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "decision",
    ["bogus", "", "   ", "APPROVE_OR_ELSE", 7],
    ids=["unknown", "empty", "blank", "unsupported", "non-string"],
)
def test_review_action_rejects_unsupported_decision(client, decision):
    test_client, service = client

    response = test_client.post(REVIEW_ACTION_PATH, json={"decision": decision})

    assert response.status_code == 422
    assert service.review_payload is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("defer", "defer"),
        ("  DEFER  ", "defer"),
        ("action_required", "action_required"),
        ("Action_Required", "action_required"),
        ("exception", "exception"),
        (" approve ", "approve"),
        ("reject", "reject"),
    ],
)
def test_review_action_normalizes_supported_decisions(client, raw, expected):
    test_client, service = client

    response = test_client.post(
        REVIEW_ACTION_PATH, json={"decision": raw, "notes": "Need more sources"}
    )

    assert response.status_code == 200
    assert service.review_payload == {
        "case_id": "case-1",
        "decision": expected,
        "notes": "Need more sources",
    }


@pytest.mark.parametrize(
    "action",
    ["bogus", "", "   ", "RESOLVED", 7],
    ids=["unknown", "empty", "blank", "unsupported", "non-string"],
)
def test_exception_action_rejects_unsupported_action(client, action):
    test_client, service = client

    response = test_client.post(EXCEPTION_ACTION_PATH, json={"action": action})

    assert response.status_code == 422
    assert service.exception_payload is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("resolve", "resolve"),
        (" RESOLVE ", "resolve"),
        ("defer", "defer"),
        ("Defer", "defer"),
        ("reopen", "reopen"),
        (" REOPEN ", "reopen"),
    ],
)
def test_exception_action_normalizes_supported_actions(client, raw, expected):
    test_client, service = client

    response = test_client.post(EXCEPTION_ACTION_PATH, json={"action": raw})

    assert response.status_code == 200
    assert service.exception_payload == {
        "case_id": "case-1",
        "exception_id": "exc-1",
        "action": expected,
        "notes": None,
    }


@pytest.mark.parametrize("target_type", ["case", "claim", "evidence", "exception", "narrative"])
@pytest.mark.parametrize("annotation_type", ["comment", "flag", "context"])
def test_annotation_accepts_narrow_types_and_normalizes_values(
    client, target_type, annotation_type
):
    test_client, service = client

    response = test_client.post(
        ANNOTATION_PATH,
        json={
            "targetType": f"  {target_type.upper()}  ",
            "targetId": "  target-1  ",
            "annotationType": f" {annotation_type.upper()} ",
            "content": "  needs review  ",
            "author": "  analyst  ",
        },
    )

    assert response.status_code == 200
    assert service.annotation_payload == {
        "case_id": "case-1",
        "target_type": target_type,
        "target_id": "target-1",
        "annotation_type": annotation_type,
        "content": "needs review",
        "author": "analyst",
        "metadata": {},
    }


def test_annotation_defaults_author_to_operator(client):
    test_client, service = client

    response = test_client.post(ANNOTATION_PATH, json=_annotation_payload())

    assert response.status_code == 200
    assert service.annotation_payload["author"] == "operator"


@pytest.mark.parametrize(
    "overrides",
    [
        {"content": ""},
        {"content": "   "},
        {"targetId": "  "},
        {"author": "   "},
        {"annotationType": "note"},
        {"annotationType": "COMMENTARY"},
        {"targetType": "planet"},
        {"targetType": "cases"},
    ],
    ids=[
        "empty-content",
        "blank-content",
        "blank-target-id",
        "blank-author",
        "unknown-annotation-type",
        "unsupported-annotation-type",
        "unknown-target-type",
        "unsupported-target-type",
    ],
)
def test_annotation_rejects_contract_violations(client, overrides):
    test_client, service = client

    response = test_client.post(ANNOTATION_PATH, json=_annotation_payload(**overrides))

    assert response.status_code == 422
    assert service.annotation_payload is None


def test_post_surface_is_exactly_the_three_documented_routes(client):
    """The merged app exposes three narrow HITL POST routes and nothing else."""
    documented_post_paths = {
        "/api/cases/{case_id}/review-actions/review",
        "/api/cases/{case_id}/review-actions/exceptions/{exception_id}",
        "/api/cases/{case_id}/annotations",
    }
    post_paths = {
        getattr(route, "path", "")
        for route in app.routes
        if "POST" in getattr(route, "methods", set())
    }
    assert post_paths == documented_post_paths


def test_read_routes_stay_get_only(client):
    """The read surface keeps serving GET and rejects mutation methods."""
    test_client, _service = client
    read_paths = [
        "/health",
        "/api/cases",
        "/api/cases/case-1",
        "/api/cases/case-1/claims",
        "/api/cases/case-1/claims/overview",
        "/api/cases/case-1/evidence",
        "/api/cases/case-1/exceptions",
        "/api/cases/case-1/parties",
        "/api/cases/case-1/timeline",
        "/api/cases/case-1/run-history",
        "/api/cases/case-1/workflow",
        "/api/cases/case-1/review-activity",
        "/api/cases/case-1/evaluation",
        "/api/cases/case-1/report",
        "/api/monitoring/summary",
    ]

    for path in read_paths:
        assert test_client.get(path).status_code == 200, path
        assert test_client.post(path).status_code == 405, path


# ---------------------------------------------------------------------------
# The same contract holds for direct service callers (CLI, scripts, tests)
# ---------------------------------------------------------------------------

DIRECT_CASE_ID = "case-direct"


def _add_direct_review_case(
    case_id: str = DIRECT_CASE_ID,
    exception_queue: list[dict] | None = None,
) -> None:
    session = get_database().get_session_sync()
    try:
        session.add(
            TopicCase(
                id=case_id,
                query="Direct review case",
                slug=case_id,
                status=CaseStatus.REVIEW_READY,
                metadata_json={"exception_queue": exception_queue or []},
            )
        )
        session.add(
            Event(
                id=f"event-{case_id}",
                case_id=case_id,
                timestamp=datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
                title="Event",
                summary="Summary",
                verification_status=VerificationStatus.PROBABLE,
            )
        )
        session.add(
            Review(
                id=f"review-{case_id}",
                event_id=f"event-{case_id}",
                status=ReviewStatus.PENDING,
            )
        )
        session.commit()
    finally:
        session.close()


def _direct_review_state(case_id: str = DIRECT_CASE_ID) -> dict:
    session = get_database().get_session_sync()
    try:
        case_row = session.get(TopicCase, case_id)
        review_row = session.get(Review, f"review-{case_id}")
        assert case_row is not None
        assert review_row is not None
        return {
            "status": case_row.status,
            "last_reviewed_at": case_row.last_reviewed_at,
            "review_notes": case_row.review_notes,
            "open_review_items": case_row.open_review_items,
            "metadata": case_row.metadata_json,
            "owner_token": case_row.owner_token,
            "owner_kind": case_row.owner_kind,
            "review_status": review_row.status,
            "review_reviewed_at": review_row.reviewed_at,
        }
    finally:
        session.close()


def _direct_annotation_state(case_id: str = DIRECT_CASE_ID) -> tuple[int, int, str | None]:
    session = get_database().get_session_sync()
    try:
        annotations = session.scalars(
            select(ReviewAnnotation).where(ReviewAnnotation.case_id == case_id)
        ).all()
        audit_entries = session.scalars(
            select(ReviewAuditEntry).where(ReviewAuditEntry.case_id == case_id)
        ).all()
        case_row = session.get(TopicCase, case_id)
        assert case_row is not None
        return len(annotations), len(audit_entries), case_row.owner_token
    finally:
        session.close()


def test_direct_review_case_rejects_unknown_decision_without_state_change(tmp_path):
    """A bypassed request model still cannot rewrite a case with an unknown decision."""
    service = make_real_service(tmp_path)
    _add_direct_review_case()
    before = _direct_review_state()

    with pytest.raises(ValueError, match="Unsupported review decision"):
        service.review_case(DIRECT_CASE_ID, "bogus")

    assert _direct_review_state() == before


@pytest.mark.parametrize(
    ("target_type", "annotation_type", "content"),
    [
        ("case", "comment", "   "),
        ("case", "comment", ""),
        ("case", "note", "Valid content"),
        ("planet", "comment", "Valid content"),
    ],
    ids=["blank-content", "empty-content", "unknown-annotation-type", "unknown-target-type"],
)
def test_direct_annotation_rejects_invalid_payload_without_persisting(
    tmp_path, target_type, annotation_type, content
):
    service = make_real_service(tmp_path)
    _add_direct_review_case()

    with pytest.raises(ValueError):
        service.add_review_annotation(
            DIRECT_CASE_ID,
            target_type=target_type,
            target_id=DIRECT_CASE_ID,
            annotation_type=annotation_type,
            content=content,
        )

    assert _direct_annotation_state() == (0, 0, None)


@pytest.mark.parametrize(
    ("target_id", "author"),
    [("   ", "operator"), (DIRECT_CASE_ID, "   ")],
    ids=["blank-target-id", "blank-author"],
)
def test_direct_annotation_rejects_blank_ids_without_persisting(
    tmp_path, target_id, author
):
    service = make_real_service(tmp_path)
    _add_direct_review_case()

    with pytest.raises(ValueError):
        service.add_review_annotation(
            DIRECT_CASE_ID,
            target_type="case",
            target_id=target_id,
            annotation_type="comment",
            content="Valid content",
            author=author,
        )

    assert _direct_annotation_state() == (0, 0, None)


# ---------------------------------------------------------------------------
# Explicit statuses for the narrow POST surface (no global ValueError handler)
# ---------------------------------------------------------------------------


def _post_as(service, path: str, payload: dict | None = None):
    app.dependency_overrides[get_case_service] = lambda: service
    try:
        return TestClient(app).post(path, json=payload or {})
    finally:
        app.dependency_overrides.clear()


def _stored_case_row(case_id: str) -> TopicCase | None:
    session = get_database().get_session_sync()
    try:
        return session.get(TopicCase, case_id)
    finally:
        session.close()


def _annotation_audit_counts(case_id: str) -> tuple[int, int]:
    session = get_database().get_session_sync()
    try:
        annotations = session.scalars(
            select(ReviewAnnotation).where(ReviewAnnotation.case_id == case_id)
        ).all()
        audit_entries = session.scalars(
            select(ReviewAuditEntry).where(ReviewAuditEntry.case_id == case_id)
        ).all()
        return len(annotations), len(audit_entries)
    finally:
        session.close()


def test_post_review_missing_case_returns_404(tmp_path):
    service = make_real_service(tmp_path)

    response = _post_as(
        service,
        "/api/cases/missing-case/review-actions/review",
        {"decision": "defer"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Case missing-case not found"
    assert _stored_case_row("missing-case") is None
    assert _annotation_audit_counts("missing-case") == (0, 0)


def test_post_annotation_missing_case_returns_404(tmp_path):
    service = make_real_service(tmp_path)

    response = _post_as(
        service,
        "/api/cases/missing-case/annotations",
        {
            "targetType": "case",
            "targetId": "missing-case",
            "annotationType": "comment",
            "content": "Operator note",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Case missing-case not found"
    assert _stored_case_row("missing-case") is None
    assert _annotation_audit_counts("missing-case") == (0, 0)


def test_post_exception_missing_exception_returns_404(tmp_path):
    service = make_real_service(tmp_path)
    _add_direct_review_case()
    before = _direct_review_state()

    response = _post_as(
        service,
        f"/api/cases/{DIRECT_CASE_ID}/review-actions/exceptions/exc-missing",
        {"action": "resolve"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        f"Exception exc-missing not found for case {DIRECT_CASE_ID}"
    )
    assert _direct_review_state() == before


def test_post_review_unresolved_exception_returns_422(tmp_path):
    service = make_real_service(tmp_path)
    _add_direct_review_case(
        exception_queue=[
            {
                "id": "exc-open",
                "type": "needs_more_sources",
                "severity": "high",
                "status": "open",
                "message": "Need more sources",
            }
        ]
    )
    before = _direct_review_state()

    response = _post_as(
        service,
        f"/api/cases/{DIRECT_CASE_ID}/review-actions/review",
        {"decision": "approve"},
    )

    assert response.status_code == 422
    assert "still has unresolved exceptions" in response.json()["detail"]
    state = _direct_review_state()
    assert state == before
    assert state["status"] == CaseStatus.REVIEW_READY
    assert state["review_status"] == ReviewStatus.PENDING


def test_post_writer_conflict_still_returns_409(tmp_path):
    service = make_real_service(tmp_path)
    _add_direct_review_case()
    before = _direct_review_state()
    token = "test-owner-token"
    session = get_database().get_session_sync()
    try:
        claim_case_ownership(
            session,
            DIRECT_CASE_ID,
            token=token,
            kind="run",
            ref_id="run-conflict",
        )
        session.commit()
    finally:
        session.close()

    try:
        response = _post_as(
            service,
            f"/api/cases/{DIRECT_CASE_ID}/review-actions/review",
            {"decision": "defer"},
        )
    finally:
        session = get_database().get_session_sync()
        try:
            release_case_ownership(session, DIRECT_CASE_ID, token)
            session.commit()
        finally:
            session.close()

    assert response.status_code == 409
    assert "currently owned" in response.json()["detail"]
    assert "test-owner-token" not in response.json()["detail"]
    assert _direct_review_state() == before


def test_post_blank_annotation_content_stays_schema_422(client):
    """Schema validation still rejects blank content before the handler runs."""
    test_client, service = client

    response = test_client.post(
        ANNOTATION_PATH,
        json=_annotation_payload(content="   "),
    )

    assert response.status_code == 422
    assert service.annotation_payload is None


# ---------------------------------------------------------------------------
# R06 — case-level ``defer`` never reopens a terminal case
# ---------------------------------------------------------------------------

TERMINAL_CASE_ID = "case-terminal"


def _add_terminal_review_case(
    case_id: str = TERMINAL_CASE_ID,
    *,
    status: CaseStatus = CaseStatus.APPROVED,
) -> None:
    """An approved case whose event review decision is bound to its analysis."""
    session = get_database().get_session_sync()
    try:
        session.add(
            TopicCase(
                id=case_id,
                query="Terminal review case",
                slug=case_id,
                status=status,
                current_stage=CaseStageName.REVIEW,
                metadata_json={
                    "exception_queue": [
                        {
                            "id": "exc-terminal",
                            "type": "needs_more_sources",
                            "severity": "high",
                            "stage": "RETRIEVE",
                            "status": "open",
                            "message": "Need more sources",
                            "resolution_notes": "Analyst note.",
                            "updated_at": "2026-03-20T10:00:00+00:00",
                        }
                    ]
                },
            )
        )
        session.add(
            Event(
                id=f"event-{case_id}",
                case_id=case_id,
                timestamp=datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
                title="Event",
                summary="Summary",
                verification_status=VerificationStatus.PROBABLE,
            )
        )
        session.flush()
        review = Review(
            id=f"review-{case_id}",
            event_id=f"event-{case_id}",
            status=ReviewStatus.APPROVED,
            reviewed_at=datetime(2026, 4, 1, 9, 30, tzinfo=UTC),
            notes="Event analyst note.",
        )
        session.add(review)
        session.flush()
        bind_review_decision(
            review, compute_event_analysis_hash(session, f"event-{case_id}")
        )
        session.commit()
    finally:
        session.close()


def _terminal_case_state(case_id: str = TERMINAL_CASE_ID) -> dict:
    """Fresh read from storage of every field the deferral must not rewrite."""
    session = get_database().get_session_sync()
    try:
        case_row = session.get(TopicCase, case_id)
        review_row = session.get(Review, f"review-{case_id}")
        assert case_row is not None
        assert review_row is not None
        return {
            "status": case_row.status,
            "stage": case_row.current_stage,
            "case_review_notes": case_row.review_notes,
            "open_review_items": case_row.open_review_items,
            "metadata": case_row.metadata_json,
            "review_status": review_row.status,
            "review_reviewed_at": review_row.reviewed_at,
            "event_review_notes": review_row.notes,
            "analysis_hash": review_row.analysis_hash,
        }
    finally:
        session.close()


def test_post_defer_keeps_terminal_case_status_and_event_decision(tmp_path):
    """R06: HTTP ``defer`` on an approved case returns 200 and reopens nothing."""
    service = make_real_service(tmp_path)
    _add_terminal_review_case()
    before = _terminal_case_state()

    response = _post_as(
        service,
        f"/api/cases/{TERMINAL_CASE_ID}/review-actions/review",
        {"decision": "defer", "notes": "Deferred while a second source is sought"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == TERMINAL_CASE_ID
    assert body["status"] == "approved"
    assert body["stage"] == CaseStageName.REVIEW.value

    after = _terminal_case_state()
    for field in (
        "status",
        "stage",
        "open_review_items",
        "metadata",
        "review_status",
        "review_reviewed_at",
        "event_review_notes",
        "analysis_hash",
    ):
        assert after[field] == before[field], field
    assert after["status"] == CaseStatus.APPROVED
    assert after["review_status"] == ReviewStatus.APPROVED
    assert after["case_review_notes"] == "Deferred while a second source is sought"
    assert after["metadata"]["exception_queue"][0]["status"] == "open"
    assert after["metadata"]["exception_queue"][0]["resolution_notes"] == (
        "Analyst note."
    )


# ---------------------------------------------------------------------------
# F13 — stored geography/provenance passthrough on the timeline read model
# ---------------------------------------------------------------------------

GEO_CASE_ID = "case-geo-passthrough"


def _add_geography_case() -> None:
    """One case with three events covering the coordinate states that matter.

    ``event-geo-zero`` is stored at exactly 0,0 (a recorded position, never
    "unknown"), ``event-geo-null`` has no recorded geography at all, and
    ``event-geo-london`` is a normal recorded pair with provenance.
    """
    session = get_database().get_session_sync()
    try:
        session.add(
            TopicCase(
                id=GEO_CASE_ID,
                query="Geography passthrough",
                slug=GEO_CASE_ID,
                status=CaseStatus.REVIEW_READY,
            )
        )
        session.add_all(
            [
                Event(
                    id="event-geo-zero",
                    case_id=GEO_CASE_ID,
                    timestamp=datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
                    title="Null Island observation",
                    summary="Stored at exactly 0,0",
                    verification_status=VerificationStatus.CONFIRMED,
                    location_country_code="ZZ",
                    location_lat=0.0,
                    location_lon=0.0,
                    workflow_route="baseline_only",
                    source_url="https://example.com/zero",
                ),
                Event(
                    id="event-geo-null",
                    case_id=GEO_CASE_ID,
                    timestamp=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
                    title="Ungeotagged observation",
                    summary="No stored geography",
                    verification_status=VerificationStatus.PROBABLE,
                    location_country_code=None,
                    location_lat=None,
                    location_lon=None,
                    workflow_route=None,
                    source_url=None,
                ),
                Event(
                    id="event-geo-london",
                    case_id=GEO_CASE_ID,
                    timestamp=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
                    title="London observation",
                    summary="Recorded pair with provenance",
                    verification_status=VerificationStatus.ALLEGED,
                    location_country_code="GB",
                    location_lat=51.5,
                    location_lon=-0.1,
                    workflow_route="party_investigation",
                    source_url="https://example.com/london",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()


def test_timeline_dto_surfaces_stored_geography_and_provenance(tmp_path):
    """The timeline read model passes stored geography through verbatim.

    Nothing is inferred, repaired or defaulted: a 0,0 pair stays 0,0 and absent
    values stay absent. The stored ``workflow_route``/``source_url`` provenance is
    forwarded verbatim alongside the geography triplet.
    """
    service = make_real_service(tmp_path)
    _add_geography_case()

    app.dependency_overrides[get_case_service] = lambda: service
    try:
        response = TestClient(app).get(f"/api/cases/{GEO_CASE_ID}/timeline")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    events = {item["id"]: item for item in response.json()}
    assert set(events) == {"event-geo-zero", "event-geo-null", "event-geo-london"}

    # 0,0 is a recorded position, not a missing one.
    zero = events["event-geo-zero"]
    assert zero["locationLat"] == 0.0
    assert zero["locationLon"] == 0.0
    assert zero["locationCountryCode"] == "ZZ"

    # Absent values stay absent rather than being defaulted.
    null_event = events["event-geo-null"]
    assert null_event["locationLat"] is None
    assert null_event["locationLon"] is None
    assert null_event["locationCountryCode"] is None

    # A normal recorded pair survives unchanged.
    london = events["event-geo-london"]
    assert london["locationLat"] == 51.5
    assert london["locationLon"] == -0.1
    assert london["locationCountryCode"] == "GB"

    # The provenance is passed through, never inferred.
    assert zero["workflowRoute"] == "baseline_only"
    assert zero["sourceUrl"] == "https://example.com/zero"
    for item in (null_event,):
        assert item["workflowRoute"] is None
        assert item["sourceUrl"] is None
