"""Case stage persistence callbacks and execution framework."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from src.storage import (
    AgentOutput,
    CaseArtifact,
    CaseArticle,
    CaseStageName,
    CaseStageRun,
    CaseStatus,
    Event,
    MonitorCheckpoint,
    Review,
    StageStatus,
    TaxonomyVersion,
    TopicCase,
    WorkflowCheckpoint,
    get_database,
)

if TYPE_CHECKING:
    from src.cases._support import CaseRunContext

from src.cases._support import _fingerprint_article, _utcnow

logger = logging.getLogger(__name__)


def _payload_checksum(payload: dict[str, Any]) -> str:
    import hashlib
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _persist_workflow_diagnostics(
    session,
    *,
    case_id: str,
    stage_run_id: str,
    stage_name: CaseStageName,
    workflow_name: str | None,
    status: str,
    result: dict[str, Any],
    summary: str,
    retry_count: int = 0,
) -> None:
    """Persist additive checkpoint and typed output records for a stage."""
    taxonomy = (
        session.query(TaxonomyVersion)
        .filter(TaxonomyVersion.is_active == 1)
        .order_by(TaxonomyVersion.created_at.desc())
        .first()
    )
    checkpoint_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"workflow-checkpoint:{stage_run_id}:{status}",
        )
    )
    checkpoint = (
        session.query(WorkflowCheckpoint)
        .filter(WorkflowCheckpoint.id == checkpoint_id)
        .first()
    )
    if checkpoint is None:
        checkpoint = WorkflowCheckpoint(
            id=checkpoint_id,
            case_id=case_id,
            stage_run_id=stage_run_id,
            stage_name=stage_name.value,
            checkpoint_key=f"{stage_name.value.lower()}:{status}",
            status=status,
            summary=summary,
            retry_count=retry_count,
            payload_json=result,
        )
        session.add(checkpoint)
    else:
        checkpoint.status = status
        checkpoint.summary = summary
        checkpoint.retry_count = retry_count
        checkpoint.payload_json = result

    output_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"agent-output:{stage_run_id}:{workflow_name or stage_name.value}:{status}",
        )
    )
    output = session.query(AgentOutput).filter(AgentOutput.id == output_id).first()
    if output is None:
        output = AgentOutput(
            id=output_id,
            case_id=case_id,
            stage_run_id=stage_run_id,
            stage_name=stage_name.value,
            agent_name=workflow_name or stage_name.value.lower(),
            output_type="stage_result",
            summary=summary,
            output_json=result,
            taxonomy_version_id=taxonomy.id if taxonomy else None,
        )
        session.add(output)
    else:
        output.summary = summary
        output.output_json = result
        output.taxonomy_version_id = taxonomy.id if taxonomy else None


# ─── Persistence Callbacks ─────────────────────────────────────────────────────


def _persist_bootstrap_payload(
    session,
    context: "CaseRunContext",
    stage_run: CaseStageRun,
    result: dict[str, Any],
) -> list[str]:
    """Persist bootstrap stage result as a case artifact."""
    # Import here to avoid circular import
    from src.cases._support import _coerce_exception

    case = session.query(TopicCase).filter(TopicCase.id == context.case.id).first()
    metadata_json = dict(case.metadata_json or {})
    metadata_json["bootstrap"] = result
    metadata_json["exception_queue"] = [
        _coerce_exception(item, CaseStageName.BOOTSTRAP)
        for item in result.get("exception_queue", [])
    ]
    case.conflict = result.get("conflict") or case.conflict
    case.routing_mode = result.get("automation_mode", case.routing_mode)
    case.metadata_json = metadata_json
    context.case.conflict = case.conflict
    context.case.routing_mode = case.routing_mode
    context.case.metadata_json = metadata_json
    artifact = CaseArtifact(
        id=str(uuid.uuid4()),
        case_id=context.case.id,
        stage_run_id=stage_run.id,
        artifact_type="bootstrap_result",
        payload_json=result,
        checksum=_payload_checksum(result),
    )
    session.add(artifact)
    return [artifact.id]


def _persist_retrieved_articles(
    session,
    context: "CaseRunContext",
    stage_run: CaseStageRun,
    result: dict[str, Any],
) -> list[str]:
    """Persist retrieved articles and update case metrics."""
    from src.cases._support import _coerce_exception, _merge_exception_lists

    artifact_ids: list[str] = []
    new_article_count = 0
    for article in result.get("articles", []):
        url = article.get("url") or f"urn:fingerprint:{_fingerprint_article(article)}"
        existing = (
            session.query(CaseArticle)
            .filter(CaseArticle.case_id == context.case.id, CaseArticle.url == url)
            .first()
        )
        if existing is None:
            existing = CaseArticle(
                id=str(uuid.uuid4()),
                case_id=context.case.id,
                url=url,
                title=article.get("title", "Untitled"),
                source=article.get("source"),
                published_at=str(article.get("published_at", "")),
                relevance_score=article.get("relevance_score", 0.0),
                fingerprint=_fingerprint_article(article),
                content=article.get("content"),
                raw_payload=article,
                last_seen_at=_utcnow(),
                is_new=1,
                source_type=article.get("source_type", "rss"),
                source_metadata=article.get("source_metadata", {}),
            )
            session.add(existing)
            new_article_count += 1
        else:
            existing.title = article.get("title", existing.title)
            existing.source = article.get("source", existing.source)
            existing.published_at = str(article.get("published_at", existing.published_at))
            existing.relevance_score = article.get(
                "relevance_score", existing.relevance_score
            )
            existing.content = article.get("content", existing.content)
            existing.raw_payload = article
            existing.last_seen_at = _utcnow()
            existing.is_new = 0
            existing.source_type = article.get("source_type", existing.source_type)
            existing.source_metadata = article.get(
                "source_metadata", existing.source_metadata
            )

    session.flush()
    context.changed = new_article_count > 0
    case = session.query(TopicCase).filter(TopicCase.id == context.case.id).first()
    article_count = (
        session.query(CaseArticle).filter(CaseArticle.case_id == context.case.id).count()
    )
    metadata_json = {
        **(context.case.metadata_json or {}),
        "bootstrap": context.bootstrap_result or {},
        "queries_generated": result.get("queries_generated", []),
        "sources_used": result.get("sources_used", []),
        "source_plan": result.get("source_plan", []),
        "articles_fetched": result.get("articles_fetched", 0),
        "articles_processed": result.get("articles_processed", 0),
        "last_retrieved_at": _utcnow().isoformat(),
        "last_retrieve_changed": context.changed,
        "exception_queue": _merge_exception_lists(
            context.exception_queue or [],
            [
                _coerce_exception(item, CaseStageName.RETRIEVE)
                for item in result.get("fetch_exceptions", [])
            ],
        ),
    }
    context.exception_queue = metadata_json["exception_queue"]
    case.conflict = result.get("conflict") or context.case.conflict
    case.article_count = article_count
    case.source_count = len(result.get("sources_used", []))
    case.metadata_json = metadata_json
    context.case.conflict = case.conflict
    context.case.article_count = article_count
    context.case.source_count = case.source_count
    context.case.metadata_json = metadata_json
    artifact = CaseArtifact(
        id=str(uuid.uuid4()),
        case_id=context.case.id,
        stage_run_id=stage_run.id,
        artifact_type="retrieval_result",
        payload_json=result,
        checksum=_payload_checksum(result),
    )
    session.add(artifact)
    artifact_ids.append(artifact.id)
    checkpoint = (
        session.query(MonitorCheckpoint)
        .filter(
            MonitorCheckpoint.case_id == context.case.id,
            MonitorCheckpoint.monitor_key == "default",
        )
        .first()
    )
    if checkpoint is None:
        checkpoint = MonitorCheckpoint(
            id=str(uuid.uuid4()),
            case_id=context.case.id,
            monitor_key="default",
        )
        session.add(checkpoint)
    checkpoint.last_checked_at = _utcnow()
    checkpoint.last_successful_run_at = _utcnow()
    checkpoint.metadata_json = {
        "new_article_count": new_article_count,
        "articles_processed": result.get("articles_processed", 0),
        "fetch_exceptions": len(result.get("fetch_exceptions", [])),
    }
    return artifact_ids


def _persist_investigation_outputs(
    session,
    context: "CaseRunContext",
    stage_run: CaseStageRun,
    result: dict[str, Any],
) -> list[str]:
    """Persist investigation outputs and recompute aggregates."""
    from src.cases._support import (
        _compute_open_review_items,
        _recompute_case_claim_aggregates,
    )
    from src.storage.event_store import store_event_in_db

    artifact_ids: list[str] = []
    for event in context.processed_events or []:
        store_event_in_db(
            event,
            case_id=context.case.id,
            case_run_id=stage_run.id,
            create_review=True,
            confirmed_parties=(
                (context.bootstrap_result or {}).get("confirmed_parties")
                or (context.case.metadata_json or {}).get("bootstrap", {}).get("confirmed_parties", [])
            ),
        )

    payload = {
        "event_ids": result.get("event_ids", []),
        "route_counts": result.get("route_counts", {}),
    }
    artifact = CaseArtifact(
        id=str(uuid.uuid4()),
        case_id=context.case.id,
        stage_run_id=stage_run.id,
        artifact_type="investigation_result",
        payload_json=payload,
        checksum=_payload_checksum(payload),
    )
    session.add(artifact)
    artifact_ids.append(artifact.id)
    case = session.query(TopicCase).filter(TopicCase.id == context.case.id).first()
    event_count = (
        session.query(Event).filter(Event.case_id == context.case.id).count()
    )
    case.event_count = event_count
    metadata_json = dict(case.metadata_json or {})
    metadata_json["exception_queue"] = result.get("exception_queue", [])
    case.metadata_json = metadata_json
    _recompute_case_claim_aggregates(session, context.case.id)
    reviews = (
        session.query(Review)
        .join(Event, Review.event_id == Event.id)
        .filter(Event.case_id == context.case.id)
        .all()
    )
    case.open_review_items = _compute_open_review_items(case.metadata_json, reviews)
    context.case.event_count = event_count
    context.case.metadata_json = case.metadata_json
    context.case.open_review_items = case.open_review_items
    return artifact_ids


def _persist_stage_payload(artifact_type: str):
    """Factory for generic stage persistence callbacks."""
    def callback(
        session,
        context: "CaseRunContext",
        stage_run: CaseStageRun,
        result: dict[str, Any],
    ) -> list[str]:
        from src.cases._support import _coerce_exception, _compute_open_review_items

        if "exception_queue" in result:
            case = session.query(TopicCase).filter(TopicCase.id == context.case.id).first()
            metadata_json = dict(case.metadata_json or {})
            metadata_json["exception_queue"] = [
                _coerce_exception(item, stage_run.stage_name)
                for item in result.get("exception_queue", [])
            ]
            case.metadata_json = metadata_json
            context.case.metadata_json = metadata_json
            reviews = (
                session.query(Review)
                .join(Event, Review.event_id == Event.id)
                .filter(Event.case_id == context.case.id)
                .all()
            )
            case.open_review_items = _compute_open_review_items(
                metadata_json, reviews
            )
            context.case.open_review_items = case.open_review_items
        artifact = CaseArtifact(
            id=str(uuid.uuid4()),
            case_id=context.case.id,
            stage_run_id=stage_run.id,
            artifact_type=artifact_type,
            payload_json=result,
            checksum=_payload_checksum(result),
        )
        session.add(artifact)
        return [artifact.id]

    return callback


def _persist_report_bundle(
    session,
    context: "CaseRunContext",
    stage_run: CaseStageRun,
    result: dict[str, Any],
) -> list[str]:
    """Export reports (JSON/MD) and persist artifacts."""
    if context.report_bundle is None:
        return []

    context.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = context.output_dir / "topic_analysis.json"
    md_path = context.output_dir / "topic_report.md"
    manifest_path = context.output_dir / "manifest.json"

    # Import exporters lazily to avoid circular imports
    from src.exporter import JSONExporter, MarkdownExporter

    json_exporter = JSONExporter()
    markdown_exporter = MarkdownExporter()
    json_exporter.export(
        context.report_bundle["results"],
        context.report_bundle["metadata"],
        json_path,
    )
    markdown_exporter.export(
        context.report_bundle["results"],
        context.report_bundle["metadata"],
        md_path,
    )
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(context.report_bundle["manifest"], handle, indent=2)

    artifact_specs = [
        ("report_json", json_path, context.report_bundle["results"]),
        ("report_markdown", md_path, {"path": str(md_path)}),
        ("execution_manifest", manifest_path, context.report_bundle["manifest"]),
    ]
    artifact_ids: list[str] = []
    for artifact_type, path, payload in artifact_specs:
        artifact = CaseArtifact(
            id=str(uuid.uuid4()),
            case_id=context.case.id,
            stage_run_id=stage_run.id,
            artifact_type=artifact_type,
            path=str(path),
            payload_json=payload if artifact_type != "report_markdown" else None,
            checksum=_payload_checksum(payload),
        )
        session.add(artifact)
        artifact_ids.append(artifact.id)

    case = session.query(TopicCase).filter(TopicCase.id == context.case.id).first()
    case.report_path = str(md_path)
    case.latest_manifest_path = str(manifest_path)
    context.case.report_path = str(md_path)
    context.case.latest_manifest_path = str(manifest_path)
    return artifact_ids


# ─── Stage Execution Framework ─────────────────────────────────────────────────


def _mark_stage_running(
    case_id: str,
    stage_run_id: str,
    stage_name: CaseStageName,
    started_at: datetime,
    *,
    workflow_name: str | None,
    model_used: str | None,
) -> None:
    """Mark a stage as running in the database."""
    session = get_database().get_session_sync()
    try:
        case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
        if case is None:
            raise RuntimeError(f"Case {case_id!r} is missing")
        attempt = (
            session.query(CaseStageRun)
            .filter(
                CaseStageRun.case_id == case_id,
                CaseStageRun.stage_name == stage_name,
            )
            .count()
            + 1
        )
        stage_run = CaseStageRun(
            id=stage_run_id,
            case_id=case_id,
            stage_name=stage_name,
            status=StageStatus.RUNNING,
            attempt=attempt,
            started_at=started_at,
            workflow_name=workflow_name,
            model_used=model_used,
            input_artifact_ids=[],
            output_artifact_ids=[],
            metrics_json={},
        )
        session.add(stage_run)
        case.current_stage = stage_name
        case.updated_at = _utcnow()
        session.commit()
    finally:
        session.close()


async def _execute_stage(
    context: "CaseRunContext",
    stage_name: CaseStageName,
    runner,
    *,
    workflow_name: str | None,
    model_used: str | None,
    status_after_success: CaseStatus,
    persist_callback,
) -> None:
    """Execute a case stage with the given runner and persistence callback."""
    from src.cases._support import (
        _count_nested_flag,
        _count_parse_failures,
        _derive_confidence,
        _derive_controversy,
        _make_exception,
        _merge_exception_lists,
    )

    stage_run_id = str(uuid.uuid4())
    started_at = _utcnow()
    _mark_stage_running(
        context.case.id,
        stage_run_id,
        stage_name,
        started_at,
        workflow_name=workflow_name,
        model_used=model_used,
    )

    try:
        started_perf = time.perf_counter()
        if asyncio.iscoroutinefunction(runner):
            result = await runner()
        else:
            result = runner()
        duration_ms = int((time.perf_counter() - started_perf) * 1000)

        session = get_database().get_session_sync()
        try:
            case = session.query(TopicCase).filter(TopicCase.id == context.case.id).first()
            stage_run = (
                session.query(CaseStageRun)
                .filter(CaseStageRun.id == stage_run_id)
                .first()
            )
            if case is None or stage_run is None:
                raise RuntimeError(
                    f"Stage run {stage_run_id!r} or its case is missing before "
                    "completion could be recorded"
                )
            artifact_ids = persist_callback(session, context, stage_run, result)
            stage_run.status = StageStatus.COMPLETED
            stage_run.completed_at = _utcnow()
            stage_run.duration_ms = duration_ms
            stage_run.output_artifact_ids = artifact_ids
            stage_run.metrics_json = json.loads(
                json.dumps(result, default=str)
            )
            stage_run.confidence_score = _derive_confidence(result)
            stage_run.controversy_score = _derive_controversy(result)
            stage_run.fallback_count = _count_nested_flag(
                result, flag_name="fallback_used"
            )
            stage_run.parse_failure_count = _count_parse_failures(result)
            case.status = status_after_success
            case.current_stage = stage_name
            case.latest_run_completed_at = _utcnow()
            case.updated_at = _utcnow()
            _persist_workflow_diagnostics(
                session,
                case_id=context.case.id,
                stage_run_id=stage_run.id,
                stage_name=stage_name,
                workflow_name=workflow_name,
                status="completed",
                result=json.loads(json.dumps(result, default=str)),
                summary=f"{stage_name.value} completed successfully.",
                retry_count=stage_run.retry_count,
            )
            session.commit()
            context.case = case
        finally:
            session.close()
    except Exception as exc:
        logger.exception("Case stage %s failed", stage_name.value)
        session = get_database().get_session_sync()
        try:
            case = session.query(TopicCase).filter(TopicCase.id == context.case.id).first()
            stage_run = (
                session.query(CaseStageRun)
                .filter(CaseStageRun.id == stage_run_id)
                .first()
            )
            if case is None or stage_run is None:
                logger.error(
                    "Cannot record failure for stage run %s: row or case missing",
                    stage_run_id,
                )
                return
            stage_run.status = StageStatus.FAILED
            stage_run.completed_at = _utcnow()
            stage_run.error_message = str(exc)
            stage_run.duration_ms = int(
                (_utcnow() - started_at).total_seconds() * 1000
            )
            case.status = CaseStatus.FAILED
            case.current_stage = stage_name
            case.latest_run_completed_at = _utcnow()
            case.updated_at = _utcnow()
            metadata_json = dict(case.metadata_json or {})
            metadata_json["exception_queue"] = _merge_exception_lists(
                metadata_json.get("exception_queue", []),
                [
                    _make_exception(
                        exception_type="source_fetch_failure"
                        if stage_name == CaseStageName.RETRIEVE
                        else "parse_failure",
                        stage=stage_name,
                        message=str(exc),
                        severity="high",
                        details={"error": str(exc)},
                    )
                ],
            )
            case.metadata_json = metadata_json
            _persist_workflow_diagnostics(
                session,
                case_id=context.case.id,
                stage_run_id=stage_run.id,
                stage_name=stage_name,
                workflow_name=workflow_name,
                status="failed",
                result={"error": str(exc), "exception_queue": metadata_json["exception_queue"]},
                summary=f"{stage_name.value} failed: {exc}",
                retry_count=stage_run.retry_count,
            )
            session.commit()
            context.case = case
        finally:
            session.close()
