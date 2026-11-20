"""R03: immutable snapshots, deltas, run-specific reports and run GET contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.cases import TopicCaseService
from src.http.app import app
from src.http.dependencies import get_case_service
from src.ingester.topic_fetcher import describe_source_outcomes
from src.storage import (
    CaseSnapshot,
    CaseStageName,
    CaseStatus,
    InvestigationCoverage,
    InvestigationRun,
    InvestigationRunStatus,
    InvestigationRunTrigger,
    TopicCase,
    init_database,
)

ARTICLE = {
    "url": "https://example.com/a",
    "title": "Article A",
    "source": "Example",
    "published_at": "2026-03-08T12:00:00+00:00",
    "content": "Alpha disputes Beta.",
    "relevance_score": 0.9,
}


def make_service(tmp_path: Path) -> TopicCaseService:
    init_database(str(tmp_path / "triangulate.db"))
    return TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)


def db_session(tmp_path: Path) -> Session:
    return init_database(str(tmp_path / "triangulate.db")).get_session_sync()


def install_fakes(
    monkeypatch,
    service: TopicCaseService,
    *,
    article: dict | None = None,
    claim_text: str = "Alpha disputes Beta",
    outcome: dict | None = None,
    fail_process: bool = False,
):
    current_article = dict(article or ARTICLE)

    async def fake_fetch(*args, **kwargs):
        return structured_payload(
            articles=[current_article], outcomes=[SUCCESS_OUTCOME]
        )

    async def fake_process(payload):
        if fail_process:
            raise RuntimeError("investigation boom")
        event = {
            "id": "temporary",
            "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
            "title": "Stable event",
            "summary": "Stable summary",
            "verification_status": "ALLEGED",
            "claims": (
                [
                    {
                        "claim": claim_text,
                        "who": ["Alpha", "Beta"],
                        "verification_status": "ALLEGED",
                    }
                ]
                if claim_text
                else []
            ),
            "narratives": [],
            "parties": [
                {"canonical_name": "Alpha", "aliases": ["Alpha"]},
                {"canonical_name": "Beta", "aliases": ["Beta"]},
            ],
        }
        if outcome is not None:
            event["extraction_outcome"] = outcome
        return event

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", fake_fetch)
    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)


def structured_payload(
    *, articles: list[dict], outcomes: list[dict]
) -> dict:
    summary = describe_source_outcomes(outcomes, requested_count=len(outcomes))
    return {
        "articles": list(articles),
        "conflict": "ukraine_war",
        "queries_generated": ["alpha"],
        "source_plan": [{"name": "Example"}],
        "source_plan_total": len(outcomes),
        "source_outcomes": outcomes,
        "sources_used": ["Example"],
        "articles_fetched": len(articles),
        "articles_processed": len(articles),
        "acquisition_coverage": summary["coverage"],
        "acquisition_counts": summary["counts"],
    }


SUCCESS_OUTCOME = {
    "source_name": "Example",
    "source_url": "https://example.com/feed.xml",
    "source_type": "rss",
    "fetch_strategy": "rss",
    "status": "success_with_items",
    "attempted": True,
    "article_count": 1,
    "error": None,
    "warning": None,
    "reason": None,
}
FAILED_OUTCOME = {
    **SUCCESS_OUTCOME,
    "source_name": "Broken",
    "status": "failed",
    "article_count": 0,
    "error": "timeout",
    "reason": "timeout",
}


def runs(tmp_path: Path, case_id: str) -> list[InvestigationRun]:
    session = db_session(tmp_path)
    try:
        return list(
            session.execute(
                select(InvestigationRun)
                .where(InvestigationRun.case_id == case_id)
                .order_by(InvestigationRun.sequence)
            )
            .scalars()
            .all()
        )
    finally:
        session.close()


def snapshots(tmp_path: Path, case_id: str) -> list[CaseSnapshot]:
    session = db_session(tmp_path)
    try:
        return list(
            session.execute(
                select(CaseSnapshot)
                .where(CaseSnapshot.case_id == case_id)
                .order_by(CaseSnapshot.created_at)
            )
            .scalars()
            .all()
        )
    finally:
        session.close()


async def run_full(service, tmp_path: Path, case_id: str | None = None):
    return await service.run_case(
        query="Snapshot case",
        case_id=case_id,
        output_dir=tmp_path,
        conflict="ukraine_war",
    )


@pytest.mark.asyncio
async def test_first_snapshot_is_initial_and_report_is_run_specific(
    monkeypatch, tmp_path
):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)

    case = await run_full(service, tmp_path)
    run = runs(tmp_path, case.id)[0]
    snaps = snapshots(tmp_path, case.id)

    assert len(snaps) == 1
    snapshot = snaps[0]
    assert run.status == InvestigationRunStatus.SUCCEEDED
    assert run.baseline_snapshot_id is None
    assert run.result_snapshot_id == snapshot.id
    assert snapshot.baseline_snapshot_id is None
    assert snapshot.schema_version == "case-snapshot-v1"
    assert snapshot.delta_json["availability"] == "initial"
    assert snapshot.delta_json["changes"] == []
    assert snapshot.payload_json["claims"]
    # Capture bodies are referenced, never duplicated.
    assert snapshot.payload_json["captures"]
    assert all("text" not in capture for capture in snapshot.payload_json["captures"])

    report_path = Path(case.report_path or "")
    assert report_path.exists()
    assert report_path.parent.parent.name == "runs"
    assert report_path.parent.name == run.id
    manifest = report_path.parent / "manifest.json"
    assert manifest.exists()

    overview = service.get_investigation_runs(case.id, limit=25, offset=0)
    assert overview is not None
    assert overview["total"] == 1
    assert overview["items"][0]["id"] == run.id
    assert overview["items"][0]["snapshotId"] == snapshot.id

    changes = service.get_run_changes(case.id, run.id, limit=25, offset=0)
    assert changes is not None
    assert changes["availability"] == "initial"
    assert changes["targetSnapshotId"] == snapshot.id
    assert changes["total"] == 0

    summary = service.get_snapshot_summary(case.id, snapshot.id)
    assert summary is not None
    assert summary["investigationRunId"] == run.id
    assert summary["counts"]["claims"] >= 1


@pytest.mark.asyncio
async def test_successful_finalization_composes_under_a_read_transaction(
    monkeypatch, tmp_path
):
    """The production path must open the explicit read transaction, not just the
    helper in isolation."""
    from src.cases import service as service_module

    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)
    calls: list[object] = []
    real = service_module.begin_read_transaction

    def spy(session):
        calls.append(session)
        return real(session)

    monkeypatch.setattr(service_module, "begin_read_transaction", spy)

    case = await run_full(service, tmp_path)

    assert calls, "snapshot composition must open a read transaction"
    assert len(snapshots(tmp_path, case.id)) == 1


@pytest.mark.asyncio
async def test_identical_rerun_has_no_semantic_change(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)
    case = await run_full(service, tmp_path)
    first_snapshot = snapshots(tmp_path, case.id)[0]
    first_report_path = Path(case.report_path or "")

    second_case = await run_full(service, tmp_path, case.id)
    second_run = runs(tmp_path, case.id)[1]
    second_snapshot = snapshots(tmp_path, case.id)[1]

    assert second_run.baseline_snapshot_id == first_snapshot.id
    assert second_run.result_snapshot_id == second_snapshot.id
    assert second_snapshot.semantic_hash == first_snapshot.semantic_hash
    assert second_snapshot.delta_json["availability"] == "ready"
    assert second_snapshot.delta_json["changes"] == []
    assert Path(second_case.report_path or "").parent.name == second_run.id
    assert first_report_path.exists()


@pytest.mark.asyncio
async def test_changed_claim_and_capture_are_detected(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)
    case = await run_full(service, tmp_path)
    first_snapshot = snapshots(tmp_path, case.id)[0]

    changed_article = {**ARTICLE, "content": "Alpha now agrees with Beta."}
    install_fakes(
        monkeypatch,
        service,
        article=changed_article,
        claim_text="Alpha now agrees with Beta",
    )
    await run_full(service, tmp_path, case.id)
    second_run = runs(tmp_path, case.id)[1]
    second_snapshot = snapshots(tmp_path, case.id)[1]
    changes = second_snapshot.delta_json["changes"]
    change_types = {item["type"] for item in changes}

    assert "capture_changed" in change_types
    assert "claim_added" in change_types
    assert "claim_no_longer_extracted" in change_types
    first_run = runs(tmp_path, case.id)[0]
    by_type = {item["type"]: item for item in changes}
    # R03c: the observing run and the entity's recorded origin are separate facts.
    assert by_type["claim_added"]["observedByRunId"] == second_run.id
    assert by_type["claim_added"]["originRunId"] == second_run.id
    assert by_type["claim_no_longer_extracted"]["observedByRunId"] == second_run.id
    assert by_type["claim_no_longer_extracted"]["originRunId"] == first_run.id
    assert all(item["observedByRunId"] == second_run.id for item in changes)
    # No invented actor attribution on review/exception observations.
    assert all("actor" not in (item.get("before") or {}) for item in changes)
    assert all("actor" not in (item.get("after") or {}) for item in changes)

    # The old observation still renders the old claim text.
    old_claims = first_snapshot.payload_json["claims"]
    assert any("Alpha disputes Beta" in claim["text"] for claim in old_claims)


@pytest.mark.asyncio
async def test_fallback_does_not_remove_live_claims(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)
    case = await run_full(service, tmp_path)
    first_snapshot = snapshots(tmp_path, case.id)[0]

    install_fakes(
        monkeypatch,
        service,
        claim_text="",
        outcome={"status": "fallback", "reason": "no_api_key"},
    )
    await run_full(service, tmp_path, case.id)
    second_snapshot = snapshots(tmp_path, case.id)[1]
    change_types = {item["type"] for item in second_snapshot.delta_json["changes"]}

    assert "claim_no_longer_extracted" not in change_types
    assert second_snapshot.payload_json["claims"]
    assert len(second_snapshot.payload_json["claims"]) == len(
        first_snapshot.payload_json["claims"]
    )


@pytest.mark.asyncio
async def test_partial_coverage_publishes_snapshot_with_caveat(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)
    case = await run_full(service, tmp_path)
    first_snapshot = snapshots(tmp_path, case.id)[0]

    async def partial_fetch(*args, **kwargs):
        return structured_payload(
            articles=[{**ARTICLE, "url": "https://example.com/b", "title": "B"}],
            outcomes=[SUCCESS_OUTCOME, FAILED_OUTCOME],
        )

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", partial_fetch)
    await run_full(service, tmp_path, case.id)
    run = runs(tmp_path, case.id)[1]
    second_snapshot = snapshots(tmp_path, case.id)[1]

    assert run.status == InvestigationRunStatus.SUCCEEDED
    assert run.coverage == InvestigationCoverage.PARTIAL
    assert second_snapshot.delta_json["coverage"] == "partial"
    assert second_snapshot.delta_json["coverageNote"]
    # Prior articles are never removed because they disappeared from a window.
    article_ids = {item["id"] for item in second_snapshot.payload_json["articles"]}
    assert {item["id"] for item in first_snapshot.payload_json["articles"]} <= article_ids
    assert "article_removed" not in {
        item["type"] for item in second_snapshot.delta_json["changes"]
    }


@pytest.mark.asyncio
async def test_scoped_report_rerun_publishes_new_snapshot(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)
    case = await run_full(service, tmp_path)
    first_snapshot = snapshots(tmp_path, case.id)[0]

    await service.rerun_case(
        case.id, start_stage=CaseStageName.REPORT, output_dir=tmp_path
    )
    second_run = runs(tmp_path, case.id)[1]
    second_snapshot = snapshots(tmp_path, case.id)[1]

    assert second_run.requested_start_stage == CaseStageName.REPORT
    assert second_run.baseline_snapshot_id == first_snapshot.id
    assert second_run.result_snapshot_id == second_snapshot.id
    assert second_snapshot.delta_json["availability"] == "ready"
    assert second_snapshot.delta_json["changes"] == []


@pytest.mark.asyncio
async def test_failed_run_does_not_publish_or_advance_baseline(
    monkeypatch, tmp_path
):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)
    case = await run_full(service, tmp_path)
    first_snapshot = snapshots(tmp_path, case.id)[0]
    prior_report = case.report_path

    install_fakes(monkeypatch, service, fail_process=True)
    failed = await run_full(service, tmp_path, case.id)
    failed_run = runs(tmp_path, case.id)[1]

    assert failed.status == CaseStatus.FAILED
    assert failed_run.status == InvestigationRunStatus.FAILED
    assert failed_run.baseline_snapshot_id is None
    assert failed_run.result_snapshot_id is None
    assert len(snapshots(tmp_path, case.id)) == 1
    changes = service.get_run_changes(case.id, failed_run.id, limit=25, offset=0)
    assert changes is not None
    assert changes["availability"] == "unavailable"
    assert changes["items"] == []
    session = db_session(tmp_path)
    try:
        stored = session.get(TopicCase, case.id)
        assert stored is not None
        assert stored.report_path == prior_report
    finally:
        session.close()
    assert snapshots(tmp_path, case.id)[0].id == first_snapshot.id


@pytest.mark.asyncio
async def test_paused_run_does_not_publish_snapshot(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)
    case = await run_full(service, tmp_path)

    paused = await service.run_case(
        query="Snapshot case",
        case_id=case.id,
        output_dir=tmp_path,
        conflict="ukraine_war",
        confirmed_parties=["Alpha"],
        automation_mode="blocked",
    )
    paused_run = runs(tmp_path, case.id)[1]

    assert paused.status == CaseStatus.REVIEW_READY
    assert paused_run.status == InvestigationRunStatus.PAUSED
    assert paused_run.result_snapshot_id is None
    assert len(snapshots(tmp_path, case.id)) == 1
    changes = service.get_run_changes(case.id, paused_run.id, limit=25, offset=0)
    assert changes is not None
    assert changes["availability"] == "unavailable"


@pytest.mark.asyncio
async def test_file_failure_cannot_publish_success(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)
    case = await run_full(service, tmp_path)
    prior_report = case.report_path
    prior_snapshot = snapshots(tmp_path, case.id)[0]

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(service.markdown_exporter, "export", explode)
    with pytest.raises(OSError):
        await run_full(service, tmp_path, case.id)

    failed_run = runs(tmp_path, case.id)[1]
    assert failed_run.status == InvestigationRunStatus.FAILED
    assert failed_run.result_snapshot_id is None
    assert len(snapshots(tmp_path, case.id)) == 1
    session = db_session(tmp_path)
    try:
        stored = session.get(TopicCase, case.id)
        assert stored is not None
        assert stored.report_path == prior_report
        assert stored.status == CaseStatus.FAILED
    finally:
        session.close()
    assert snapshots(tmp_path, case.id)[0].id == prior_snapshot.id


@pytest.mark.asyncio
async def test_db_failure_after_rename_leaves_no_pointer_or_baseline(
    monkeypatch, tmp_path
):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)
    case = await run_full(service, tmp_path)
    prior_report = case.report_path
    prior_snapshot = snapshots(tmp_path, case.id)[0]

    session = db_session(tmp_path)
    try:
        session.execute(
            text(
                "CREATE TRIGGER fail_case_snapshot BEFORE INSERT ON case_snapshots "
                "BEGIN SELECT RAISE(ABORT, 'snapshot failure'); END;"
            )
        )
        session.commit()
    finally:
        session.close()
    try:
        with pytest.raises(SQLAlchemyError):
            await run_full(service, tmp_path, case.id)
        failed_run = runs(tmp_path, case.id)[1]
        assert failed_run.status == InvestigationRunStatus.FAILED
        assert failed_run.result_snapshot_id is None
        assert failed_run.baseline_snapshot_id is None
        assert len(snapshots(tmp_path, case.id)) == 1
        session = db_session(tmp_path)
        try:
            stored = session.get(TopicCase, case.id)
            assert stored is not None
            assert stored.report_path == prior_report
        finally:
            session.close()
        assert snapshots(tmp_path, case.id)[0].id == prior_snapshot.id
        # The renamed run directory may remain unreferenced (allowed by §7).
        assert (tmp_path / "cases" / "snapshot-case" / "runs").exists()
    finally:
        session = db_session(tmp_path)
        try:
            session.execute(text("DROP TRIGGER IF EXISTS fail_case_snapshot"))
            session.commit()
        finally:
            session.close()


def test_legacy_run_changes_are_unavailable_not_empty(tmp_path):
    service = make_service(tmp_path)
    session = db_session(tmp_path)
    try:
        case = TopicCase(
            id="case-legacy-r03",
            query="Legacy",
            slug="legacy-r03",
            status=CaseStatus.REVIEW_READY,
        )
        session.add(case)
        session.add(
            InvestigationRun(
                id="run-legacy-r03",
                case_id=case.id,
                sequence=1,
                trigger=InvestigationRunTrigger.INITIAL,
                requested_start_stage=CaseStageName.BOOTSTRAP,
                parameter_snapshot={},
                status=InvestigationRunStatus.SUCCEEDED,
                coverage=InvestigationCoverage.UNKNOWN,
                coverage_details={},
            )
        )
        session.commit()
    finally:
        session.close()

    changes = service.get_run_changes(
        "case-legacy-r03", "run-legacy-r03", limit=25, offset=0
    )
    assert changes is not None
    assert changes["availability"] == "unavailable"
    assert changes["items"] == []
    assert service.get_snapshot_summary("case-legacy-r03", "missing") is None


@pytest.mark.asyncio
async def test_run_and_snapshot_get_contracts_and_cross_case_404(
    monkeypatch, tmp_path
):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)
    case = await run_full(service, tmp_path)
    run = runs(tmp_path, case.id)[0]
    snapshot = snapshots(tmp_path, case.id)[0]

    session = db_session(tmp_path)
    try:
        session.add(
            TopicCase(
                id="case-other-r03",
                query="Other",
                slug="other-r03",
                status=CaseStatus.REVIEW_READY,
            )
        )
        session.commit()
    finally:
        session.close()

    app.dependency_overrides[get_case_service] = lambda: service
    try:
        client = TestClient(app)
        listing = client.get(f"/api/cases/{case.id}/investigation-runs")
        assert listing.status_code == 200
        body = listing.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == run.id
        assert body["items"][0]["resultSnapshotId"] == snapshot.id

        detail = client.get(
            f"/api/cases/{case.id}/investigation-runs/{run.id}"
        )
        assert detail.status_code == 200
        assert detail.json()["coverage"] == "complete_requested_scope"
        assert detail.json()["parameterSnapshot"]["query"] == "Snapshot case"

        changes = client.get(
            f"/api/cases/{case.id}/investigation-runs/{run.id}/changes"
        )
        assert changes.status_code == 200
        assert changes.json()["availability"] == "initial"

        summary = client.get(
            f"/api/cases/{case.id}/snapshots/{snapshot.id}"
        )
        assert summary.status_code == 200
        assert summary.json()["investigationRunId"] == run.id

        # Wrong case never leaks a run/snapshot.
        wrong_run = client.get(
            f"/api/cases/case-other-r03/investigation-runs/{run.id}"
        )
        assert wrong_run.status_code == 404
        wrong_changes = client.get(
            f"/api/cases/case-other-r03/investigation-runs/{run.id}/changes"
        )
        assert wrong_changes.status_code == 404
        wrong_snapshot = client.get(
            f"/api/cases/case-other-r03/snapshots/{snapshot.id}"
        )
        assert wrong_snapshot.status_code == 404

        invalid_limit = client.get(
            f"/api/cases/{case.id}/investigation-runs", params={"limit": 0}
        )
        assert invalid_limit.status_code == 422
    finally:
        app.dependency_overrides.clear()
