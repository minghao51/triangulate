"""R02: case-writer admission, fencing and explicit CLI recovery.

Every test uses a temporary database and deterministic stubs; no provider, feed
or production database is touched.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
import typer
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.cases import TopicCaseService
from src.storage import (
    CaseStageName,
    CaseStatus,
    CaseWriterConflict,
    Event,
    IntakeItem,
    InvestigationCoverage,
    InvestigationRun,
    InvestigationRunStatus,
    InvestigationRunTrigger,
    MonitorCheckpoint,
    OWNER_KIND_REVIEW,
    OWNER_KIND_RUN,
    ReviewAnnotation,
    TopicCase,
    claim_case_ownership,
    init_database,
    invalidate_case_ownership,
    new_writer_token,
    read_case_owner,
    release_case_ownership,
    validate_case_ownership,
)
from src.storage.event_store import store_event_in_db


def make_service(tmp_path: Path) -> TopicCaseService:
    init_database(str(tmp_path / "triangulate.db"))
    return TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)


def db_session(tmp_path: Path) -> Session:
    return init_database(str(tmp_path / "triangulate.db")).get_session_sync()


def seed_case(
    service: TopicCaseService,
    case_id: str = "case-r02",
    *,
    metadata_json: dict | None = None,
    status: CaseStatus = CaseStatus.REVIEW_READY,
) -> TopicCase:
    session = db_session(service.output_root)
    try:
        case = TopicCase(
            id=case_id,
            query="Fencing case",
            slug="fencing-case",
            status=status,
            metadata_json=metadata_json or {"exception_queue": []},
        )
        session.add(case)
        session.commit()
        return case
    finally:
        session.close()


def seed_running_run(tmp_path: Path, case_id: str, run_id: str = "run-r02") -> None:
    session = db_session(tmp_path)
    try:
        session.add(
            InvestigationRun(
                id=run_id,
                case_id=case_id,
                sequence=1,
                trigger=InvestigationRunTrigger.INITIAL,
                requested_start_stage=CaseStageName.BOOTSTRAP,
                parameter_snapshot={},
                status=InvestigationRunStatus.RUNNING,
                coverage=InvestigationCoverage.UNKNOWN,
                coverage_details={},
            )
        )
        session.commit()
    finally:
        session.close()


def claim_case(
    tmp_path: Path,
    case_id: str,
    *,
    kind: str = OWNER_KIND_RUN,
    ref_id: str | None = "run-live",
) -> str:
    token = new_writer_token()
    session = db_session(tmp_path)
    try:
        claim_case_ownership(
            session, case_id, token=token, kind=kind, ref_id=ref_id
        )
        session.commit()
    finally:
        session.close()
    return token


def release_case(tmp_path: Path, case_id: str, token: str) -> None:
    session = db_session(tmp_path)
    try:
        release_case_ownership(session, case_id, token)
        session.commit()
    finally:
        session.close()


def owner(tmp_path: Path, case_id: str):
    session = db_session(tmp_path)
    try:
        return read_case_owner(session, case_id)
    finally:
        session.close()


def read_case_row(tmp_path: Path, case_id: str) -> TopicCase:
    session = db_session(tmp_path)
    try:
        row = session.get(TopicCase, case_id)
        assert row is not None
        session.expunge(row)
        return row
    finally:
        session.close()


def seed_intake(tmp_path: Path, case_id: str, intake_id: str = "intake-r02") -> str:
    session = db_session(tmp_path)
    try:
        session.add(
            IntakeItem(
                id=intake_id,
                case_id=case_id,
                url="https://example.com/a",
                title="Article A",
                fingerprint="fp-r02",
                content="Alpha disputes Beta.",
                capture_type="manual_url",
                source_type="rss",
                raw_payload={
                    "title": "Article A",
                    "content": "Alpha disputes Beta.",
                    "url": "https://example.com/a",
                },
                intake_status="PENDING",
            )
        )
        session.commit()
        return intake_id
    finally:
        session.close()


def fetch_payload() -> dict:
    return {
        "articles": [],
        "conflict": "ukraine_war",
        "queries_generated": [],
        "sources_used": [],
        "articles_fetched": 0,
        "articles_processed": 0,
    }


def install_fakes(monkeypatch, service: TopicCaseService) -> None:
    async def fake_fetch(*args, **kwargs):
        return fetch_payload()

    async def fake_process(article):
        return {
            "id": "temporary",
            "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
            "title": article.get("title") or "Article",
            "summary": "Summary",
            "verification_status": "ALLEGED",
            "claims": [],
            "narratives": [],
            "parties": [],
            "evidence": [],
        }

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", fake_fetch)
    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)


def event_payload(event_id: str = "event-r02") -> dict:
    return {
        "id": event_id,
        "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
        "title": "Event",
        "summary": "Summary",
        "verification_status": "ALLEGED",
        "claims": [],
        "narratives": [],
        "parties": [],
        "evidence": [],
    }


def _count(tmp_path: Path, model) -> int:
    session = db_session(tmp_path)
    try:
        return len(session.execute(select(model)).scalars().all())
    finally:
        session.close()


@pytest.mark.asyncio
async def test_conflicting_run_rejected_without_side_effects(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)
    case = seed_case(service)
    token = claim_case(tmp_path, case.id, ref_id="run-live")

    with pytest.raises(CaseWriterConflict) as excinfo:
        await service.run_case(
            query="Fencing case",
            case_id=case.id,
            conflict="ukraine_war",
            start_stage=CaseStageName.REPORT,
            output_dir=tmp_path,
        )

    assert excinfo.value.active_kind == OWNER_KIND_RUN
    assert excinfo.value.active_ref_id == "run-live"
    # No grouped run row was created, and case prep did not leak a mutation.
    assert _count(tmp_path, InvestigationRun) == 0
    current = owner(tmp_path, case.id)
    assert current.ref_id == "run-live"
    assert current.kind == OWNER_KIND_RUN
    session = db_session(tmp_path)
    try:
        stored = session.get(TopicCase, case.id)
        assert stored is not None
        assert stored.query == "Fencing case"
        assert stored.latest_run_started_at is None
    finally:
        session.close()
    release_case(tmp_path, case.id, token)


@pytest.mark.asyncio
async def test_case_bound_intake_rejected_then_succeeds_after_release(tmp_path):
    service = make_service(tmp_path)
    case = seed_case(service)
    token = claim_case(tmp_path, case.id)

    with pytest.raises(CaseWriterConflict):
        service.ingest_articles(
            [{"url": "https://example.com/new", "title": "New", "content": "Body"}],
            capture_type="source_ingest",
            case_id=case.id,
        )
    assert _count(tmp_path, IntakeItem) == 0
    assert owner(tmp_path, case.id).ref_id == "run-live"

    release_case(tmp_path, case.id, token)
    queued = service.ingest_articles(
        [{"url": "https://example.com/new", "title": "New", "content": "Body"}],
        capture_type="source_ingest",
        case_id=case.id,
    )
    assert len(queued) == 1
    assert not owner(tmp_path, case.id).is_owned


@pytest.mark.asyncio
async def test_conflicting_intake_processing_rejected(tmp_path):
    service = make_service(tmp_path)
    case = seed_case(service)
    intake_id = seed_intake(tmp_path, case.id)
    token = claim_case(tmp_path, case.id, kind=OWNER_KIND_RUN, ref_id="run-live")

    # No AI stub is installed: the claim rejection must happen before analysis.
    assert await service._process_intake_item(intake_id) is False

    session = db_session(tmp_path)
    try:
        item = session.get(IntakeItem, intake_id)
        assert item is not None
        assert item.intake_status == "PENDING"
        assert item.processed_event_id is None
        assert session.execute(select(Event)).first() is None
    finally:
        session.close()
    assert owner(tmp_path, case.id).ref_id == "run-live"
    release_case(tmp_path, case.id, token)


@pytest.mark.asyncio
async def test_review_exception_annotation_evaluation_osint_rejected(
    monkeypatch, tmp_path
):
    service = make_service(tmp_path)
    case = seed_case(
        service,
        metadata_json={
            "exception_queue": [
                {
                    "id": "exc-r02",
                    "type": "needs_more_sources",
                    "severity": "high",
                    "stage": "RETRIEVE",
                    "status": "open",
                }
            ]
        },
    )
    osint_file = tmp_path / "artifact.json"
    osint_file.write_text('{"title": "OSINT note"}', encoding="utf-8")
    token = claim_case(tmp_path, case.id)

    with pytest.raises(CaseWriterConflict):
        service.review_case(case.id, "defer")
    with pytest.raises(CaseWriterConflict):
        service.update_exception_status(case.id, "exc-r02", action="resolve")
    with pytest.raises(CaseWriterConflict):
        service.add_review_annotation(
            case.id,
            target_type="case",
            target_id=case.id,
            annotation_type="note",
            content="Blocked",
        )
    with pytest.raises(CaseWriterConflict):
        service.evaluate_case(case.id)
    with pytest.raises(CaseWriterConflict):
        service.ingest_osint_artifact(
            tool="test", file_path=osint_file, case_id=case.id
        )

    session = db_session(tmp_path)
    try:
        stored = session.get(TopicCase, case.id)
        assert stored is not None
        assert stored.status == CaseStatus.REVIEW_READY
        queue = (stored.metadata_json or {}).get("exception_queue", [])
        assert queue[0]["status"] == "open"
        assert session.execute(select(ReviewAnnotation)).first() is None
    finally:
        session.close()
    release_case(tmp_path, case.id, token)

    reviewed = service.review_case(case.id, "defer")
    assert reviewed.status == CaseStatus.REVIEW_READY
    assert not owner(tmp_path, case.id).is_owned


def test_defer_conflict_on_terminal_case_leaves_decision_untouched(tmp_path):
    """R06: a fenced ``defer`` cannot reopen an approved case or touch the queue."""
    service = make_service(tmp_path)
    exception = {
        "id": "exc-r06",
        "type": "needs_more_sources",
        "severity": "high",
        "stage": "RETRIEVE",
        "status": "open",
        "message": "Need more sources",
        "resolution_notes": "Analyst note.",
        "updated_at": "2026-03-20T10:00:00+00:00",
    }
    case = seed_case(
        service,
        case_id="case-r06-terminal",
        status=CaseStatus.APPROVED,
        metadata_json={"exception_queue": [exception]},
    )
    token = claim_case(tmp_path, case.id)
    before = read_case_row(tmp_path, case.id)

    with pytest.raises(CaseWriterConflict):
        service.review_case(case.id, "defer", "Blocked deferral")

    after = read_case_row(tmp_path, case.id)
    assert after.status == CaseStatus.APPROVED
    assert after.review_notes is None
    assert after.last_reviewed_at is None
    assert after.metadata_json == before.metadata_json
    release_case(tmp_path, case.id, token)

    # Once the writer is released the acknowledgement is recorded without
    # reopening the terminal case or rewriting the exception queue.
    reviewed = service.review_case(case.id, "defer", "Deferred after release")
    assert reviewed.status == CaseStatus.APPROVED
    stored = read_case_row(tmp_path, case.id)
    assert stored.status == CaseStatus.APPROVED
    assert stored.review_notes == "Deferred after release"
    assert stored.metadata_json == before.metadata_json


@pytest.mark.asyncio
async def test_paused_run_releases_ownership(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    install_fakes(monkeypatch, service)
    case = seed_case(service)

    paused = await service.run_case(
        query="Fencing case",
        case_id=case.id,
        output_dir=tmp_path,
        conflict="ukraine_war",
        confirmed_parties=["Alpha"],
        automation_mode="blocked",
    )

    assert paused.status == CaseStatus.REVIEW_READY
    assert not owner(tmp_path, case.id).is_owned
    session = db_session(tmp_path)
    try:
        run = (
            session.execute(select(InvestigationRun))
            .scalars()
            .one()
        )
        assert run.status == InvestigationRunStatus.PAUSED
    finally:
        session.close()
    # A short writer can proceed once the paused invocation released ownership.
    assert service.review_case(case.id, "defer").status == CaseStatus.REVIEW_READY


def test_interrupt_requires_reason_confirmation_and_matching_owner(tmp_path):
    service = make_service(tmp_path)
    case = seed_case(service)
    seed_running_run(tmp_path, case.id, run_id="run-r02")
    token = claim_case(tmp_path, case.id, ref_id="run-r02")

    with pytest.raises(ValueError):
        service.interrupt_case(case.id, run_id="run-r02", reason="", confirmed=True)
    with pytest.raises(ValueError):
        service.interrupt_case(
            case.id, run_id="run-r02", reason="stuck", confirmed=False
        )
    with pytest.raises(ValueError):
        service.interrupt_case(case.id, reason="stuck", confirmed=True)
    with pytest.raises(CaseWriterConflict):
        service.interrupt_case(
            case.id, run_id="wrong-run", reason="stuck", confirmed=True
        )
    with pytest.raises(CaseWriterConflict):
        service.interrupt_case(
            case.id, token="wrong-token", reason="stuck", confirmed=True
        )

    current = service.get_case_owner(case.id)
    assert current["kind"] == OWNER_KIND_RUN
    assert current["refId"] == "run-r02"
    assert owner(tmp_path, case.id).is_owned

    result = service.interrupt_case(
        case.id, run_id="run-r02", reason="stuck", confirmed=True
    )
    assert result["runStatus"] == "interrupted"
    assert result["reason"] == "stuck"
    assert not owner(tmp_path, case.id).is_owned

    session = db_session(tmp_path)
    try:
        run = session.get(InvestigationRun, "run-r02")
        assert run is not None
        assert run.status == InvestigationRunStatus.INTERRUPTED
        assert run.completed_at is not None
        assert run.error_json is not None
        assert run.error_json["reason"] == "stuck"
    finally:
        session.close()

    with pytest.raises(CaseWriterConflict):
        service.interrupt_case(
            case.id, token=token, reason="again", confirmed=True
        )


def test_stale_token_cannot_commit_after_takeover(tmp_path):
    service = make_service(tmp_path)
    case = seed_case(service)
    old_token = claim_case(tmp_path, case.id, ref_id="run-old")

    session = db_session(tmp_path)
    try:
        invalidate_case_ownership(session, case.id, expected_ref_id="run-old")
        session.commit()
    finally:
        session.close()
    new_token = claim_case(tmp_path, case.id, ref_id="run-new")

    session = db_session(tmp_path)
    try:
        with pytest.raises(CaseWriterConflict):
            validate_case_ownership(session, case.id, old_token)
        validate_case_ownership(session, case.id, new_token)
    finally:
        session.close()
    release_case(tmp_path, case.id, new_token)


def test_direct_event_write_rejected_while_owned_and_legacy_allowed(tmp_path):
    service = make_service(tmp_path)
    case = seed_case(service)
    token = claim_case(tmp_path, case.id)

    with pytest.raises(CaseWriterConflict):
        store_event_in_db(event_payload(), case_id=case.id)
    assert _count(tmp_path, Event) == 0

    release_case(tmp_path, case.id, token)
    # Historical unowned single-writer path stays compatible.
    assert store_event_in_db(event_payload(), case_id=case.id) is True
    assert _count(tmp_path, Event) == 1


@pytest.mark.asyncio
async def test_interrupted_run_cannot_commit_retrieve_stage(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    case = seed_case(service)
    gate = asyncio.Event()
    started = asyncio.Event()

    async def gated_fetch(*args, **kwargs):
        started.set()
        await gate.wait()
        return fetch_payload()

    async def fake_process(article):
        return {
            "id": "temporary",
            "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
            "title": "Article",
            "summary": "Summary",
            "verification_status": "ALLEGED",
            "claims": [],
            "narratives": [],
            "parties": [],
            "evidence": [],
        }

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", gated_fetch)
    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)

    task = asyncio.create_task(
        service.run_case(
            query="Fencing case",
            case_id=case.id,
            output_dir=tmp_path,
            conflict="ukraine_war",
            start_stage=CaseStageName.RETRIEVE,
        )
    )
    await started.wait()

    session = db_session(tmp_path)
    try:
        running = (
            session.execute(
                select(InvestigationRun).where(
                    InvestigationRun.case_id == case.id,
                    InvestigationRun.status == InvestigationRunStatus.RUNNING,
                )
            )
            .scalars()
            .one()
        )
        run_id = running.id
    finally:
        session.close()

    service.interrupt_case(
        case.id, run_id=run_id, reason="test interrupt", confirmed=True
    )
    gate.set()

    with pytest.raises(CaseWriterConflict):
        await task

    session = db_session(tmp_path)
    try:
        run = session.get(InvestigationRun, run_id)
        assert run is not None
        assert run.status == InvestigationRunStatus.INTERRUPTED
        # The retrieve attempt was started before the interrupt but never
        # completed, and no checkpoint advanced.
        stages = session.execute(
            select(Event)
        ).scalars().all()
        assert stages == []
        checkpoints = session.execute(select(MonitorCheckpoint)).scalars().all()
        assert all(
            checkpoint.last_successful_run_at is None for checkpoint in checkpoints
        )
    finally:
        session.close()
    assert not owner(tmp_path, case.id).is_owned


def test_review_kind_claim_blocks_other_short_writers(tmp_path):
    service = make_service(tmp_path)
    case = seed_case(service)
    review_token = claim_case(tmp_path, case.id, kind=OWNER_KIND_REVIEW, ref_id=None)

    with pytest.raises(CaseWriterConflict):
        service.ingest_articles(
            [{"url": "https://example.com/x", "title": "X", "content": "Body"}],
            capture_type="source_ingest",
            case_id=case.id,
        )
    with pytest.raises(CaseWriterConflict):
        service.update_exception_status(case.id, "missing", action="resolve")

    release_case(tmp_path, case.id, review_token)
    assert not owner(tmp_path, case.id).is_owned


@pytest.mark.asyncio
async def test_interrupted_report_stage_does_not_publish_pointer(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    case = seed_case(service)
    install_fakes(monkeypatch, service)

    first = await service.run_case(
        query="Fencing case",
        case_id=case.id,
        output_dir=tmp_path,
        conflict="ukraine_war",
    )
    assert first.report_path
    prior_report_path = first.report_path

    gate = asyncio.Event()
    started = asyncio.Event()
    original_report = service._stage_report

    async def gated_report(context):
        started.set()
        await gate.wait()
        await original_report(context)

    monkeypatch.setattr(service, "_stage_report", gated_report)

    task = asyncio.create_task(
        service.rerun_case(
            case.id, start_stage=CaseStageName.REPORT, output_dir=tmp_path
        )
    )
    await started.wait()

    session = db_session(tmp_path)
    try:
        running = (
            session.execute(
                select(InvestigationRun).where(
                    InvestigationRun.case_id == case.id,
                    InvestigationRun.status == InvestigationRunStatus.RUNNING,
                )
            )
            .scalars()
            .one()
        )
        run_id = running.id
    finally:
        session.close()

    service.interrupt_case(
        case.id, run_id=run_id, reason="report interrupt", confirmed=True
    )
    gate.set()

    with pytest.raises(CaseWriterConflict):
        await task

    session = db_session(tmp_path)
    try:
        stored = session.get(TopicCase, case.id)
        assert stored is not None
        # The interrupted report transaction could not publish a new pointer.
        assert stored.report_path == prior_report_path
        run = session.get(InvestigationRun, run_id)
        assert run is not None
        assert run.status == InvestigationRunStatus.INTERRUPTED
    finally:
        session.close()
    assert not owner(tmp_path, case.id).is_owned


def test_http_conflicting_review_maps_to_409(tmp_path):
    from fastapi.testclient import TestClient

    from src.http.app import app
    from src.http.dependencies import get_case_service

    class ConflictService:
        def review_case(self, case_id, decision, notes=None):
            raise CaseWriterConflict(
                case_id, active_kind=OWNER_KIND_RUN, active_ref_id="run-x"
            )

    app.dependency_overrides[get_case_service] = lambda: ConflictService()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/cases/case-r02/review-actions/review",
            json={"decision": "approve"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "owned by a run" in response.json()["detail"]



def test_interrupt_rejects_finished_or_missing_run_and_keeps_ownership(tmp_path):
    """A rejected interrupt must not clear ownership (R02 review finding)."""
    service = make_service(tmp_path)
    case = seed_case(service)

    seed_running_run(tmp_path, case.id, run_id="run-done")
    session = db_session(tmp_path)
    try:
        run = session.get(InvestigationRun, "run-done")
        assert run is not None
        run.status = InvestigationRunStatus.SUCCEEDED
        run.completed_at = run.started_at
        session.commit()
    finally:
        session.close()

    finished_token = claim_case(tmp_path, case.id, ref_id="run-done")
    with pytest.raises(ValueError, match="not running"):
        service.interrupt_case(
            case.id, run_id="run-done", reason="stale", confirmed=True
        )
    assert owner(tmp_path, case.id).is_owned
    assert service.get_case_owner(case.id)["refId"] == "run-done"
    session = db_session(tmp_path)
    try:
        run = session.get(InvestigationRun, "run-done")
        assert run is not None and run.status == InvestigationRunStatus.SUCCEEDED
    finally:
        session.close()

    release_case(tmp_path, case.id, finished_token)

    claim_case(tmp_path, case.id, ref_id="run-missing")
    with pytest.raises(ValueError, match="not found"):
        service.interrupt_case(
            case.id, run_id="run-missing", reason="stale", confirmed=True
        )
    assert owner(tmp_path, case.id).is_owned
    assert service.get_case_owner(case.id)["refId"] == "run-missing"


def test_interrupt_command_exits_nonzero_on_rejection_and_cancel(tmp_path, monkeypatch):
    """Automation must not read a rejected/cancelled recovery as success."""
    from src.cli.commands import cases as cli_cases

    class RejectingService:
        def interrupt_case(self, *args, **kwargs):
            raise ValueError("nothing to interrupt")

    monkeypatch.setattr(
        cli_cases, "build_case_service", lambda output: RejectingService()
    )
    with pytest.raises(typer.Exit) as rejected:
        cli_cases.cmd_interrupt_case(
            "case-x",
            run_id="run-x",
            token=None,
            reason="stuck",
            yes=True,
            output=tmp_path,
        )
    assert rejected.value.exit_code == 1

    monkeypatch.setattr(cli_cases.Confirm, "ask", lambda *a, **k: False)
    with pytest.raises(typer.Exit) as cancelled:
        cli_cases.cmd_interrupt_case(
            "case-x",
            run_id="run-x",
            token=None,
            reason="stuck",
            yes=False,
            output=tmp_path,
        )
    assert cancelled.value.exit_code == 1

