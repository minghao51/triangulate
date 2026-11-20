"""R01: grouped investigation invocation identity and origin references.

These tests exercise real ``run_case`` orchestration against a temporary
database. No model/provider/feed call is made: the fetcher and the article
workflow are replaced with deterministic in-process stubs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.cases import TopicCaseService
from src.cases.service import MAX_ERROR_MESSAGE_CHARS
from src.ingester.topic_fetcher import describe_source_outcomes
from src.storage import (
    CaseStageName,
    CaseStageRun,
    CaseStatus,
    Event,
    InvestigationCoverage,
    InvestigationRun,
    InvestigationRunStatus,
    InvestigationRunTrigger,
    StageStatus,
    init_database,
    read_case_owner,
)

ARTICLE = {
    "url": "https://example.com/a",
    "title": "Article A",
    "source": "Example",
    "published_at": "2026-03-08T12:00:00+00:00",
    "content": "Alpha and Beta disagree.",
    "relevance_score": 0.9,
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
                    "claim_text": "Alpha disputes Beta",
                    "verification_status": "CONTESTED",
                    "fact_allegation_classification": "FACT",
                    "reasoning": "Conflicting positions",
                    "party_positions": {"Alpha": "SUPPORTS", "Beta": "CONTEST"},
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
    service = TopicCaseService(
        {"ai": {"model": "test-model"}},
        output_root=tmp_path,
    )
    service.party_workflow = FakePartyWorkflow()
    return service


def fetch_payload(*, articles: list[dict], outcomes: list[dict] | None = None) -> dict:
    """A TopicFetcher-shaped result whose coverage is derived from outcomes."""
    outcomes = outcomes if outcomes is not None else [SUCCESS_OUTCOME]
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


def install_fakes(
    monkeypatch,
    service: TopicCaseService,
    *,
    payload: dict | None = None,
    fail_process: bool = False,
) -> None:
    async def fake_fetch(*args, **kwargs):
        return payload if payload is not None else fetch_payload(articles=[ARTICLE])

    async def fake_process(article):
        if fail_process:
            raise RuntimeError("investigation boom")
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


def _session(tmp_path: Path) -> Session:
    return init_database(str(tmp_path / "triangulate.db")).get_session_sync()


def _runs(tmp_path: Path, case_id: str) -> list[InvestigationRun]:
    session = _session(tmp_path)
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


@pytest.mark.asyncio
async def test_full_run_records_one_grouped_run_and_origin_references(
    monkeypatch, tmp_path
):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)

    case = await service.run_case(
        query="Grouped run", output_dir=tmp_path, conflict="ukraine_war"
    )

    assert case.status == CaseStatus.REVIEW_READY

    session = _session(tmp_path)
    try:
        runs = list(
            session.execute(
                select(InvestigationRun).where(InvestigationRun.case_id == case.id)
            )
            .scalars()
            .all()
        )
        assert len(runs) == 1
        run = runs[0]
        assert run.sequence == 1
        assert run.trigger == InvestigationRunTrigger.INITIAL
        assert run.requested_start_stage == CaseStageName.BOOTSTRAP
        assert run.status == InvestigationRunStatus.SUCCEEDED
        assert run.coverage == InvestigationCoverage.COMPLETE_REQUESTED_SCOPE
        assert run.predecessor_run_id is None
        assert run.started_at is not None
        assert run.completed_at is not None
        assert run.error_json is None
        # R03 publishes a snapshot for a successful observation; the first run
        # has no earlier baseline.
        assert run.baseline_snapshot_id is None
        assert run.result_snapshot_id is not None
        assert run.parameter_snapshot["query"] == "Grouped run"
        assert run.parameter_snapshot["maxArticles"] == 50
        assert run.parameter_snapshot["startStage"] == "BOOTSTRAP"
        assert run.parameter_snapshot["trigger"] != "monitor"
        assert run.coverage_details["requestedStages"] == [
            "BOOTSTRAP",
            "RETRIEVE",
            "TRIAGE",
            "INVESTIGATE",
            "ARBITRATE",
            "REPORT",
        ]
        assert run.coverage_details["retrievalCoverage"] == "complete_requested_scope"
        assert run.coverage_details["predecessorRunId"] is None
        outcomes = run.coverage_details["stageOutcomes"]
        assert [item["stage"] for item in outcomes] == [
            "BOOTSTRAP",
            "RETRIEVE",
            "TRIAGE",
            "INVESTIGATE",
            "ARBITRATE",
            "REPORT",
        ]
        assert all(item["status"] == "COMPLETED" for item in outcomes)

        stage_runs = list(
            session.execute(
                select(CaseStageRun).where(CaseStageRun.case_id == case.id)
            )
            .scalars()
            .all()
        )
        assert len(stage_runs) == 6
        assert {run.id} == {
            stage_run.investigation_run_id for stage_run in stage_runs
        }
        assert all(run.status == StageStatus.COMPLETED for run in stage_runs)
        assert [item["stageRunId"] for item in outcomes] == [
            stage_run.id
            for stage_name in (
                CaseStageName.BOOTSTRAP,
                CaseStageName.RETRIEVE,
                CaseStageName.TRIAGE,
                CaseStageName.INVESTIGATE,
                CaseStageName.ARBITRATE,
                CaseStageName.REPORT,
            )
            for stage_run in stage_runs
            if stage_run.stage_name == stage_name
        ]

        # Event.case_run_id keeps its stage-FK meaning; the grouped reference is
        # a separate column that names this invocation.
        investigate_run_id = next(
            stage_run.id
            for stage_run in stage_runs
            if stage_run.stage_name == CaseStageName.INVESTIGATE
        )
        events = list(
            session.execute(select(Event).where(Event.case_id == case.id))
            .scalars()
            .all()
        )
        assert events
        assert all(event.investigation_run_id == run.id for event in events)
        assert all(event.case_run_id == investigate_run_id for event in events)
    finally:
        session.close()


@pytest.mark.asyncio
async def test_rerun_gets_new_sequence_predecessor_and_keeps_stage_history(
    monkeypatch, tmp_path
):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)

    first_case = await service.run_case(
        query="Rerun case", output_dir=tmp_path, conflict="ukraine_war"
    )
    first_runs = _runs(tmp_path, first_case.id)
    assert len(first_runs) == 1
    first_run = first_runs[0]

    session = _session(tmp_path)
    try:
        first_event_origin = {
            event.id: event.investigation_run_id
            for event in session.execute(
                select(Event).where(Event.case_id == first_case.id)
            )
            .scalars()
            .all()
        }
    finally:
        session.close()

    await service.rerun_case(
        first_case.id, start_stage=CaseStageName.REPORT, output_dir=tmp_path
    )

    runs = _runs(tmp_path, first_case.id)
    assert [run.sequence for run in runs] == [1, 2]
    second_run = runs[1]
    assert second_run.id != first_run.id
    assert second_run.trigger == InvestigationRunTrigger.RERUN
    assert second_run.requested_start_stage == CaseStageName.REPORT
    assert second_run.predecessor_run_id == first_run.id
    assert second_run.status == InvestigationRunStatus.SUCCEEDED
    assert second_run.coverage == InvestigationCoverage.COMPLETE_REQUESTED_SCOPE
    assert second_run.coverage_details["requestedStages"] == ["REPORT"]
    assert second_run.coverage_details["predecessorRunId"] == first_run.id
    # R03 observations chain: the scoped rerun's baseline is the previous snapshot.
    assert second_run.result_snapshot_id is not None
    assert second_run.baseline_snapshot_id == first_run.result_snapshot_id

    session = _session(tmp_path)
    try:
        stage_runs = list(
            session.execute(
                select(CaseStageRun)
                .where(CaseStageRun.case_id == first_case.id)
                .order_by(CaseStageRun.started_at)
            )
            .scalars()
            .all()
        )
        # A scoped rerun adds only the requested stage attempt.
        assert len(stage_runs) == 7
        assert sum(
            1 for run in stage_runs if run.stage_name == CaseStageName.REPORT
        ) == 2
        assert sum(
            1 for run in stage_runs if run.stage_name == CaseStageName.BOOTSTRAP
        ) == 1
        assert [
            run.investigation_run_id
            for run in stage_runs
            if run.stage_name != CaseStageName.REPORT
            or run.attempt == 1
        ] == [first_run.id] * 6
        report_attempt = next(
            run
            for run in stage_runs
            if run.stage_name == CaseStageName.REPORT and run.attempt == 2
        )
        assert report_attempt.investigation_run_id == second_run.id

        # Earlier observations keep their original grouped origin.
        events = list(
            session.execute(select(Event).where(Event.case_id == first_case.id))
            .scalars()
            .all()
        )
        assert {
            event.id: event.investigation_run_id for event in events
        } == first_event_origin
    finally:
        session.close()


@pytest.mark.asyncio
async def test_failed_run_records_failed_status_without_success_coverage(
    monkeypatch, tmp_path
):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service, fail_process=True)

    case = await service.run_case(
        query="Failing run", output_dir=tmp_path, conflict="ukraine_war"
    )

    assert case.status == CaseStatus.FAILED
    runs = _runs(tmp_path, case.id)
    assert len(runs) == 1
    run = runs[0]
    assert run.status == InvestigationRunStatus.FAILED
    assert run.coverage == InvestigationCoverage.FAILED
    assert run.error_json is not None
    assert run.error_json["stage"] == "INVESTIGATE"
    assert "investigation boom" in run.error_json["message"]
    assert run.completed_at is not None
    assert run.baseline_snapshot_id is None
    assert run.result_snapshot_id is None

    outcomes = run.coverage_details["stageOutcomes"]
    assert [item["stage"] for item in outcomes] == [
        "BOOTSTRAP",
        "RETRIEVE",
        "TRIAGE",
        "INVESTIGATE",
    ]
    assert outcomes[-1]["status"] == "FAILED"
    # No fabricated success for stages that never ran.
    assert "ARBITRATE" not in {item["stage"] for item in outcomes}
    assert "REPORT" not in {item["stage"] for item in outcomes}


@pytest.mark.asyncio
async def test_paused_run_is_not_recorded_as_success(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)

    case = await service.run_case(
        query="Blocked run",
        output_dir=tmp_path,
        conflict="ukraine_war",
        confirmed_parties=["Alpha"],
        automation_mode="blocked",
    )

    assert case.status == CaseStatus.REVIEW_READY
    runs = _runs(tmp_path, case.id)
    assert len(runs) == 1
    run = runs[0]
    assert run.status == InvestigationRunStatus.PAUSED
    assert run.coverage == InvestigationCoverage.PARTIAL
    assert run.error_json is None
    assert run.coverage_details["pausedAfterStage"] == "BOOTSTRAP"
    assert [item["stage"] for item in run.coverage_details["stageOutcomes"]] == [
        "BOOTSTRAP"
    ]
    assert run.completed_at is not None


@pytest.mark.asyncio
async def test_monitor_dispatch_trigger_is_recorded(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)

    case = await service.run_case(
        query="Monitor dispatch",
        output_dir=tmp_path,
        conflict="ukraine_war",
        monitor_mode=True,
    )

    runs = _runs(tmp_path, case.id)
    assert len(runs) == 1
    assert runs[0].trigger == InvestigationRunTrigger.MONITOR


@pytest.mark.asyncio
async def test_setup_failure_finalizes_stalled_run_and_releases_claim(
    monkeypatch, tmp_path
):
    """R01/R02: the post-commit setup window cannot strand a RUNNING run.

    The grouped-run row and owner claim are committed before the in-memory context
    exists. If reloading/hydrating that context fails, the run must still be
    finalized as failed (with a bounded message) and ownership must be released,
    otherwise every later case-bound write is rejected until a manual interrupt.
    """
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)
    case = await service.run_case(
        query="Stalled run", output_dir=tmp_path, conflict="ukraine_war"
    )
    runs_before = _runs(tmp_path, case.id)

    oversized_message = "context hydration exploded " + "x" * 2000

    def explode(_context):
        raise RuntimeError(oversized_message)

    monkeypatch.setattr(service, "_hydrate_context_from_case", explode)

    with pytest.raises(RuntimeError, match="context hydration exploded"):
        await service.run_case(
            query="Stalled run",
            case_id=case.id,
            output_dir=tmp_path,
            conflict="ukraine_war",
            start_stage=CaseStageName.RETRIEVE,
        )

    runs = _runs(tmp_path, case.id)
    assert len(runs) == len(runs_before) + 1
    stalled = runs[-1]
    assert stalled.status == InvestigationRunStatus.FAILED
    assert stalled.coverage == InvestigationCoverage.FAILED
    assert stalled.completed_at is not None
    assert stalled.baseline_snapshot_id is None
    assert stalled.result_snapshot_id is None
    assert stalled.error_json is not None
    assert stalled.error_json["abandonedBeforeStage"] is True
    assert "context hydration exploded" in stalled.error_json["message"]
    assert len(stalled.error_json["message"]) == (
        MAX_ERROR_MESSAGE_CHARS + len(" [truncated]")
    )

    session = _session(tmp_path)
    try:
        assert not read_case_owner(session, case.id).is_owned
    finally:
        session.close()
