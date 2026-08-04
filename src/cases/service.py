"""Topic case lifecycle orchestration — core use-case logic."""

from __future__ import annotations

import json
import logging
import statistics
import uuid
from pathlib import Path
from typing import Any

from src.ai.baseline_workflow import BaselineWorkflow
from src.ai.taxonomy import sync_bias_taxonomy
from src.ai.workflows.party_investigation_workflow import (
    create_party_investigation_workflow,
)
from src.cases._persistence import (
    _execute_stage,
    _persist_bootstrap_payload,
    _persist_retrieved_articles,
    _persist_investigation_outputs,
    _persist_stage_payload,
    _persist_report_bundle,
)
from src.cases._serializers import (
    build_case_detail_payload,
    build_executive_summary_from_payload,
)
from src.cases._support import (
    CaseRunContext,
    STAGE_ORDER,
    _claim_signature,
    _coerce_exception,
    _compute_open_review_items,
    _execution_automation_mode,
    _fingerprint_article,
    _get_open_exceptions,
    _make_exception,
    _merge_exception_lists,
    _normalize_automation_mode,
    _parse_timestamp,
    _resolve_case_exceptions,
    _slugify,
    _utcnow,
)
from src.exporter import JSONExporter, MarkdownExporter
from src.ingester.polling_fetcher import PollingFetcher
from src.ingester.relevance_fetcher import RelevanceFetcher
from src.ingester.url_capture import fetch_article_content
from src.storage import (
    CaseArticle,
    CaseStageRun,
    CaseStageName,
    CaseStatus,
    Event,
    EvidenceArtifactLink,
    EvidenceItem,
    IntakeItem,
    OsintArtifact,
    Review,
    ReviewStatus,
    TopicCase,
    WorkflowCheckpoint,
    AgentOutput,
    TaxonomyVersion,
    get_database,
    EvaluationRun,
    ReviewAnnotation,
    ReviewAuditEntry,
)
from src.storage.event_store import store_event_in_db

logger = logging.getLogger(__name__)


class TopicCaseService:
    """Owns topic-oriented case creation, orchestration, and review."""

    def __init__(self, config: dict[str, Any], output_root: Path = Path("./output")):
        self.config = config
        self.output_root = output_root
        self.ai_workflow = BaselineWorkflow(config)
        self.topic_fetcher = RelevanceFetcher(config)
        self.party_workflow = create_party_investigation_workflow()
        self.json_exporter = JSONExporter()
        self.markdown_exporter = MarkdownExporter()
        taxonomy_path_value = self.config.get("ai", {}).get("taxonomy_path")
        taxonomy_path = Path(taxonomy_path_value) if taxonomy_path_value else None
        self.active_taxonomy = sync_bias_taxonomy(taxonomy_path)

    def list_cases(self) -> list[TopicCase]:
        session = get_database().get_session_sync()
        try:
            return session.query(TopicCase).order_by(TopicCase.updated_at.desc()).all()
        finally:
            session.close()

    def get_case(self, case_id: str) -> TopicCase | None:
        session = get_database().get_session_sync()
        try:
            return session.query(TopicCase).filter(TopicCase.id == case_id).first()
        finally:
            session.close()

    def get_case_details(self, case_id: str) -> dict[str, Any] | None:
        session = get_database().get_session_sync()
        try:
            case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
            if case is None:
                return None
            return build_case_detail_payload(session, case)
        finally:
            session.close()

    def get_case_workflow_details(self, case_id: str) -> dict[str, Any]:
        """Return durable workflow diagnostics for a case."""
        session = get_database().get_session_sync()
        try:
            case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
            if case is None:
                raise ValueError(f"Case {case_id} not found")
            checkpoints = (
                session.query(WorkflowCheckpoint)
                .filter(WorkflowCheckpoint.case_id == case_id)
                .order_by(WorkflowCheckpoint.created_at.desc())
                .all()
            )
            outputs = (
                session.query(AgentOutput)
                .filter(AgentOutput.case_id == case_id)
                .order_by(AgentOutput.created_at.desc())
                .all()
            )
            return {
                "case_id": case_id,
                "current_stage": case.current_stage.value if case.current_stage else None,
                "status": case.status.value if case.status else None,
                "taxonomy": {
                    "id": self.active_taxonomy.id,
                    "kind": self.active_taxonomy.taxonomy_kind,
                    "version": self.active_taxonomy.version,
                    "path": self.active_taxonomy.path,
                    "checksum": self.active_taxonomy.checksum,
                },
                "checkpoints": [
                    {
                        "id": checkpoint.id,
                        "stage_name": checkpoint.stage_name,
                        "checkpoint_key": checkpoint.checkpoint_key,
                        "status": checkpoint.status,
                        "summary": checkpoint.summary,
                        "retry_count": checkpoint.retry_count,
                        "payload": checkpoint.payload_json or {},
                        "created_at": checkpoint.created_at.isoformat()
                        if checkpoint.created_at
                        else None,
                    }
                    for checkpoint in checkpoints
                ],
                "agent_outputs": [
                    {
                        "id": output.id,
                        "stage_name": output.stage_name,
                        "agent_name": output.agent_name,
                        "output_type": output.output_type,
                        "summary": output.summary,
                        "payload": output.output_json or {},
                        "taxonomy_version_id": output.taxonomy_version_id,
                        "created_at": output.created_at.isoformat()
                        if output.created_at
                        else None,
                    }
                    for output in outputs
                ],
            }
        finally:
            session.close()

    def get_case_review_activity(self, case_id: str) -> dict[str, Any]:
        """Return annotations and audit log entries for human review actions."""
        session = get_database().get_session_sync()
        try:
            case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
            if case is None:
                raise ValueError(f"Case {case_id} not found")

            annotations = (
                session.query(ReviewAnnotation)
                .filter(ReviewAnnotation.case_id == case_id)
                .order_by(ReviewAnnotation.created_at.desc())
                .all()
            )
            audit_entries = (
                session.query(ReviewAuditEntry)
                .filter(ReviewAuditEntry.case_id == case_id)
                .order_by(ReviewAuditEntry.created_at.desc())
                .all()
            )
            return {
                "annotations": [
                    {
                        "id": item.id,
                        "target_type": item.target_type,
                        "target_id": item.target_id,
                        "annotation_type": item.annotation_type,
                        "author": item.author,
                        "content": item.content,
                        "metadata": item.metadata_json or {},
                        "created_at": item.created_at.isoformat()
                        if item.created_at
                        else None,
                    }
                    for item in annotations
                ],
                "audit_entries": [
                    {
                        "id": item.id,
                        "action_type": item.action_type,
                        "target_type": item.target_type,
                        "target_id": item.target_id,
                        "actor": item.actor,
                        "rationale": item.rationale,
                        "metadata": item.metadata_json or {},
                        "created_at": item.created_at.isoformat()
                        if item.created_at
                        else None,
                    }
                    for item in audit_entries
                ],
            }
        finally:
            session.close()

    def add_review_annotation(
        self,
        case_id: str,
        *,
        target_type: str,
        target_id: str,
        annotation_type: str,
        content: str,
        author: str = "operator",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist a review annotation and mirror it into the audit trail."""
        session = get_database().get_session_sync()
        try:
            case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
            if case is None:
                raise ValueError(f"Case {case_id} not found")

            annotation = ReviewAnnotation(
                id=str(uuid.uuid4()),
                case_id=case_id,
                target_type=target_type,
                target_id=target_id,
                annotation_type=annotation_type,
                author=author,
                content=content.strip(),
                metadata_json=metadata or {},
            )
            session.add(annotation)
            self._record_audit_entry(
                session,
                case_id=case_id,
                action_type=f"annotation:{annotation_type}",
                target_type=target_type,
                target_id=target_id,
                actor=author,
                rationale=content.strip(),
                metadata=metadata or {},
            )
            session.commit()
            return {
                "id": annotation.id,
                "target_type": annotation.target_type,
                "target_id": annotation.target_id,
                "annotation_type": annotation.annotation_type,
                "author": annotation.author,
                "content": annotation.content,
                "metadata": annotation.metadata_json or {},
                "created_at": annotation.created_at.isoformat()
                if annotation.created_at
                else None,
            }
        finally:
            session.close()

    def evaluate_case(
        self,
        case_id: str,
        *,
        evaluation_kind: str = "case_quality",
    ) -> dict[str, Any]:
        """Score a case using lightweight, stable evaluation heuristics and persist the run."""
        session = get_database().get_session_sync()
        try:
            case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
            if case is None:
                raise ValueError(f"Case {case_id} not found")

            detail = build_case_detail_payload(session, case)
            claims = detail.get("claims", [])
            evidence = detail.get("evidence", [])
            exceptions = detail.get("exceptions", [])
            stage_runs = detail.get("stage_runs", [])
            active_taxonomy = (
                session.query(TaxonomyVersion)
                .filter(TaxonomyVersion.is_active == 1)
                .order_by(TaxonomyVersion.created_at.desc())
                .first()
            )

            total_claims = len(claims)
            total_evidence = len(evidence)
            open_exceptions = sum(1 for item in exceptions if item.get("status") != "resolved")
            linked_claims = sum(1 for item in claims if item.get("evidence"))
            contested_claims = sum(
                1
                for item in claims
                if item.get("verification_status") == "CONTESTED"
                or (item.get("oppose_count") or 0) > 0
            )
            source_diversity_values = [
                float(item.get("source_diversity_count") or 0) for item in claims
            ]
            requires_human_review = sum(
                1 for item in evidence if item.get("requires_human_review")
            )
            failed_runs = sum(1 for item in stage_runs if item.get("status") == "FAILED")
            retry_count = sum(int((item.get("metrics") or {}).get("retry_count", 0)) for item in stage_runs)
            fallback_count = sum(int(item.get("fallback_count") or 0) for item in stage_runs)
            total_duration_ms = sum(int(item.get("duration_ms") or 0) for item in stage_runs)

            evidence_linkage = linked_claims / total_claims if total_claims else 1.0
            contradiction_handling = (
                (sum(1 for item in claims if item.get("evidence") and ((item.get("oppose_count") or 0) > 0 or item.get("verification_status") == "CONTESTED")) / contested_claims)
                if contested_claims
                else 1.0
            )
            source_diversity = min(
                (statistics.mean(source_diversity_values) / 3.0) if source_diversity_values else 0.0,
                1.0,
            )
            review_burden = max(
                0.0,
                1.0
                - (
                    (case.open_review_items + requires_human_review)
                    / max(total_claims + total_evidence, 1)
                ),
            )
            neutrality = max(
                0.0,
                1.0 - ((contested_claims + open_exceptions) / max(total_claims + 1, 1)),
            )
            pipeline_resilience = max(
                0.0,
                1.0
                - (
                    (failed_runs + retry_count + fallback_count)
                    / max(len(stage_runs) * 3, 1)
                ),
            )
            overall_score = round(
                (
                    evidence_linkage
                    + contradiction_handling
                    + source_diversity
                    + review_burden
                    + neutrality
                    + pipeline_resilience
                )
                / 6,
                3,
            )

            metrics = {
                "neutrality": round(neutrality, 3),
                "evidence_linkage": round(evidence_linkage, 3),
                "contradiction_handling": round(contradiction_handling, 3),
                "review_burden": round(review_burden, 3),
                "source_diversity": round(source_diversity, 3),
                "pipeline_resilience": round(pipeline_resilience, 3),
                "claims_total": total_claims,
                "evidence_total": total_evidence,
                "open_exceptions": open_exceptions,
                "requires_human_review": requires_human_review,
                "failed_stage_runs": failed_runs,
                "total_duration_ms": total_duration_ms,
            }
            summary = {
                "overall_score": overall_score,
                "case_status": case.status.value if case.status else None,
                "current_stage": case.current_stage.value if case.current_stage else None,
                "taxonomy_version": active_taxonomy.version if active_taxonomy else None,
                "workflow_version": "phase4-5-local",
            }

            evaluation = EvaluationRun(
                id=str(uuid.uuid4()),
                case_id=case_id,
                status="completed",
                evaluation_kind=evaluation_kind,
                summary_json=summary,
                metrics_json=metrics,
                model_config_json=self.config.get("ai", {}),
                workflow_version="phase4-5-local",
                output_version=detail["case"].get("updated_at"),
                taxonomy_version_id=active_taxonomy.id if active_taxonomy else None,
            )
            session.add(evaluation)
            self._record_audit_entry(
                session,
                case_id=case_id,
                action_type="evaluation:run",
                target_type="case",
                target_id=case_id,
                actor="system",
                rationale="Generated evaluation run for current case state.",
                metadata={"evaluation_kind": evaluation_kind, "overall_score": overall_score},
            )
            session.commit()
            return {
                "id": evaluation.id,
                "status": evaluation.status,
                "evaluation_kind": evaluation.evaluation_kind,
                "summary": summary,
                "metrics": metrics,
                "created_at": evaluation.created_at.isoformat()
                if evaluation.created_at
                else None,
            }
        finally:
            session.close()

    def get_case_evaluation_summary(self, case_id: str) -> dict[str, Any]:
        """Return the latest evaluation run and a compact historical view for a case."""
        session = get_database().get_session_sync()
        try:
            case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
            if case is None:
                raise ValueError(f"Case {case_id} not found")

            runs = (
                session.query(EvaluationRun)
                .filter(EvaluationRun.case_id == case_id)
                .order_by(EvaluationRun.created_at.desc())
                .all()
            )
            if runs:
                latest = runs[0]
                return {
                    "latest": {
                        "id": latest.id,
                        "status": latest.status,
                        "evaluation_kind": latest.evaluation_kind,
                        "summary": latest.summary_json or {},
                        "metrics": latest.metrics_json or {},
                        "created_at": latest.created_at.isoformat()
                        if latest.created_at
                        else None,
                    },
                    "history": [
                        {
                            "id": item.id,
                            "status": item.status,
                            "evaluation_kind": item.evaluation_kind,
                            "summary": item.summary_json or {},
                            "metrics": item.metrics_json or {},
                            "created_at": item.created_at.isoformat()
                            if item.created_at
                            else None,
                        }
                        for item in runs[:10]
                    ],
                }
        finally:
            session.close()
        latest_payload = self.evaluate_case(case_id)
        return {"latest": latest_payload, "history": [latest_payload]}

    def get_monitoring_summary(self) -> dict[str, Any]:
        """Return aggregate operator-facing observability and review backlog metrics."""
        session = get_database().get_session_sync()
        try:
            cases = session.query(TopicCase).all()
            stage_runs = session.query(CaseStageRun).all()
            intake_items = session.query(IntakeItem).all()
            evaluations = (
                session.query(EvaluationRun)
                .order_by(EvaluationRun.created_at.desc())
                .limit(25)
                .all()
            )

            open_exceptions = sum(
                len(_get_open_exceptions(case.metadata_json or {})) for case in cases
            )
            review_backlog = sum(int(case.open_review_items or 0) for case in cases)
            failed_stage_runs = sum(1 for run in stage_runs if run.status.name == "FAILED")
            running_stage_runs = sum(1 for run in stage_runs if run.status.name == "RUNNING")
            retry_count = sum(int(run.retry_count or 0) for run in stage_runs)
            fallback_count = sum(int(run.fallback_count or 0) for run in stage_runs)
            avg_duration_ms = round(
                statistics.mean(
                    [int(run.duration_ms or 0) for run in stage_runs if run.duration_ms]
                ),
                2,
            ) if any(run.duration_ms for run in stage_runs) else 0.0
            avg_evaluation_score = round(
                statistics.mean(
                    [
                        float((item.summary_json or {}).get("overall_score", 0.0))
                        for item in evaluations
                    ]
                ),
                3,
            ) if evaluations else None

            return {
                "cases": {
                    "total": len(cases),
                    "review_ready": sum(
                        1 for case in cases if (case.status.value if case.status else "") == "REVIEW_READY"
                    ),
                    "active": sum(
                        1
                        for case in cases
                        if (case.status.value if case.status else "")
                        not in {"APPROVED", "REJECTED"}
                    ),
                },
                "review": {
                    "open_exceptions": open_exceptions,
                    "backlog": review_backlog,
                },
                "pipeline": {
                    "running_stage_runs": running_stage_runs,
                    "failed_stage_runs": failed_stage_runs,
                    "retry_count": retry_count,
                    "fallback_count": fallback_count,
                    "avg_duration_ms": avg_duration_ms,
                },
                "intake": {
                    "pending_items": sum(1 for item in intake_items if item.intake_status == "PENDING"),
                    "processed_items": sum(1 for item in intake_items if item.intake_status == "PROCESSED"),
                },
                "evaluation": {
                    "recent_runs": len(evaluations),
                    "avg_overall_score": avg_evaluation_score,
                },
            }
        finally:
            session.close()

    def ingest_osint_artifact(
        self,
        *,
        tool: str,
        file_path: Path,
        case_id: str,
        artifact_type: str | None = None,
    ) -> dict[str, Any]:
        """Import an external OSINT artifact and attach it to a case."""
        session = get_database().get_session_sync()
        try:
            case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
            if case is None:
                raise ValueError(f"Case {case_id} not found")

            source_path = file_path.expanduser().resolve()
            raw_text = source_path.read_text(encoding="utf-8")
            raw_payload: dict[str, Any]
            if source_path.suffix.lower() == ".json":
                loaded = json.loads(raw_text)
                raw_payload = loaded if isinstance(loaded, dict) else {"items": loaded}
            else:
                raw_payload = {"content": raw_text}

            fingerprint = _fingerprint_article(
                {
                    "url": str(source_path),
                    "title": raw_payload.get("title", source_path.name),
                    "source": tool,
                }
            )
            existing_artifact = (
                session.query(OsintArtifact)
                .filter(
                    OsintArtifact.case_id == case_id,
                    OsintArtifact.tool == tool,
                    OsintArtifact.fingerprint == fingerprint,
                )
                .first()
            )
            artifact_kind = artifact_type or raw_payload.get("artifact_type") or source_path.suffix.lstrip(".") or "file"
            if existing_artifact is None:
                existing_artifact = OsintArtifact(
                    id=str(uuid.uuid4()),
                    case_id=case_id,
                    tool=tool,
                    artifact_type=artifact_kind,
                    source_path=str(source_path),
                    fingerprint=fingerprint,
                    raw_text=raw_text[:20000],
                    raw_payload=raw_payload,
                    import_metadata={
                        "file_name": source_path.name,
                        "suffix": source_path.suffix.lower(),
                        "import_mode": "cli",
                    },
                )
                session.add(existing_artifact)
            else:
                existing_artifact.source_path = str(source_path)
                existing_artifact.raw_text = raw_text[:20000]
                existing_artifact.raw_payload = raw_payload
                existing_artifact.import_metadata = {
                    **(existing_artifact.import_metadata or {}),
                    "file_name": source_path.name,
                    "suffix": source_path.suffix.lower(),
                    "import_mode": "cli",
                }

            evidence_url = (
                raw_payload.get("origin_url")
                or raw_payload.get("canonical_url")
                or raw_payload.get("url")
                or raw_payload.get("link")
            )
            evidence_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"osint-evidence:{case_id}:{tool}:{source_path}",
                )
            )
            evidence = (
                session.query(EvidenceItem)
                .filter(EvidenceItem.id == evidence_id)
                .first()
            )
            if evidence is None:
                evidence = EvidenceItem(
                    id=evidence_id,
                    case_id=case_id,
                    evidence_type="osint_artifact",
                    source_type="osint",
                    title=raw_payload.get("title", source_path.name),
                    origin_url=evidence_url,
                    canonical_url=evidence_url,
                    publisher=raw_payload.get("publisher")
                    or raw_payload.get("source")
                    or raw_payload.get("source_name")
                    or tool,
                    published_at=raw_payload.get("published_at")
                    or raw_payload.get("timestamp"),
                    content=raw_payload.get("content") or raw_text[:4000],
                    capture_metadata={
                        "tool": tool,
                        "artifact_id": existing_artifact.id,
                        "source_path": str(source_path),
                        "lineage": {
                            "case_id": case_id,
                            "origin": "osint_import",
                            "tool": tool,
                        },
                    },
                    verification_status="UNVERIFIED",
                    credibility_tier=raw_payload.get("credibility_tier", "operator_supplied"),
                    requires_human_review=1,
                )
                session.add(evidence)
            else:
                evidence.title = raw_payload.get("title", evidence.title)
                evidence.origin_url = evidence_url or evidence.origin_url
                evidence.canonical_url = evidence_url or evidence.canonical_url
                evidence.publisher = (
                    raw_payload.get("publisher")
                    or raw_payload.get("source")
                    or raw_payload.get("source_name")
                    or evidence.publisher
                )
                evidence.content = raw_payload.get("content") or evidence.content
                evidence.capture_metadata = {
                    **(evidence.capture_metadata or {}),
                    "tool": tool,
                    "artifact_id": existing_artifact.id,
                    "source_path": str(source_path),
                    "lineage": {
                        "case_id": case_id,
                        "origin": "osint_import",
                        "tool": tool,
                    },
                }

            link_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"osint-link:{evidence.id}:{existing_artifact.id}",
                )
            )
            link = (
                session.query(EvidenceArtifactLink)
                .filter(EvidenceArtifactLink.id == link_id)
                .first()
            )
            if link is None:
                session.add(
                    EvidenceArtifactLink(
                        id=link_id,
                        evidence_id=evidence.id,
                        osint_artifact_id=existing_artifact.id,
                        relation="derived_from",
                        confidence_score=1.0,
                        provenance_metadata={
                            "tool": tool,
                            "source_path": str(source_path),
                            "artifact_type": artifact_kind,
                        },
                    )
                )

            metadata = dict(case.metadata_json or {})
            osint_summary = dict(metadata.get("osint_summary") or {})
            osint_summary["last_imported_at"] = _utcnow().isoformat()
            osint_summary["artifact_count"] = (
                session.query(OsintArtifact)
                .filter(OsintArtifact.case_id == case_id)
                .count()
                + (0 if existing_artifact.id else 1)
            )
            osint_summary["tools"] = sorted(
                {
                    row.tool
                    for row in session.query(OsintArtifact.tool)
                    .filter(OsintArtifact.case_id == case_id)
                    .all()
                }
                | {tool}
            )
            metadata["osint_summary"] = osint_summary
            case.metadata_json = metadata
            self._refresh_case_metrics(session, case_id)
            session.commit()
            return {
                "artifact_id": existing_artifact.id,
                "evidence_id": evidence.id,
                "tool": tool,
                "source_path": str(source_path),
                "artifact_type": artifact_kind,
            }
        finally:
            session.close()

    def stream_osint_artifacts(
        self,
        *,
        tool: str,
        watch_dir: Path,
        case_id: str,
        once: bool = False,
    ) -> dict[str, Any]:
        """Import all OSINT files from a directory."""
        directory = watch_dir.expanduser().resolve()
        if not directory.exists():
            raise ValueError(f"Watch directory not found: {directory}")

        imported = []
        for file_path in sorted(path for path in directory.iterdir() if path.is_file()):
            imported.append(
                self.ingest_osint_artifact(tool=tool, file_path=file_path, case_id=case_id)
            )

        return {
            "tool": tool,
            "watch_dir": str(directory),
            "imported_count": len(imported),
            "mode": "once" if once else "snapshot",
            "artifacts": imported,
        }

    def fetch_and_intake_articles(
        self,
        *,
        source: str | None = None,
        limit: int | None = None,
        case_id: str | None = None,
    ) -> list[IntakeItem]:
        """Fetch source content and persist it to the durable intake queue."""
        fetcher = PollingFetcher(self.config)
        if source:
            articles = fetcher.fetch_from_source(source, limit=limit or 50)
        else:
            articles = fetcher.fetch_all(limit=limit)
        return self.ingest_articles(
            articles,
            capture_type="source_ingest",
            case_id=case_id,
        )

    def ingest_articles(
        self,
        articles: list[dict[str, Any]],
        *,
        capture_type: str,
        case_id: str | None = None,
    ) -> list[IntakeItem]:
        """Persist captured articles to the intake queue."""
        session = get_database().get_session_sync()
        try:
            if case_id is not None:
                case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
                if case is None:
                    raise ValueError(f"Case {case_id} not found")

            queued: list[IntakeItem] = []
            now = _utcnow()
            for article in articles:
                normalized_url = (
                    article.get("url")
                    or article.get("link")
                    or article.get("origin_url")
                )
                fingerprint = _fingerprint_article(
                    {
                        "url": normalized_url or "",
                        "title": article.get("title", ""),
                        "source": article.get("source") or article.get("source_name", ""),
                    }
                )
                existing = (
                    session.query(IntakeItem)
                    .filter(
                        IntakeItem.case_id == case_id,
                        IntakeItem.fingerprint == fingerprint,
                    )
                    .order_by(IntakeItem.created_at.desc())
                    .first()
                )

                payload = {
                    **article,
                    "url": normalized_url,
                    "link": normalized_url,
                }
                if existing is None:
                    existing = IntakeItem(
                        id=str(uuid.uuid4()),
                        case_id=case_id,
                        url=normalized_url,
                        title=article.get("title") or "Untitled Article",
                        source_name=article.get("source") or article.get("source_name"),
                        published_at=str(
                            article.get("published_at") or article.get("timestamp") or ""
                        ),
                        fingerprint=fingerprint,
                        content=article.get("content"),
                        capture_type=capture_type,
                        source_type=article.get("source_type", "rss"),
                        raw_payload=payload,
                        intake_status="PENDING",
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                    session.add(existing)
                else:
                    existing.url = normalized_url or existing.url
                    existing.title = article.get("title") or existing.title
                    existing.source_name = (
                        article.get("source") or article.get("source_name") or existing.source_name
                    )
                    existing.published_at = str(
                        article.get("published_at")
                        or article.get("timestamp")
                        or existing.published_at
                        or ""
                    )
                    existing.content = article.get("content", existing.content)
                    existing.capture_type = capture_type
                    existing.source_type = article.get("source_type", existing.source_type)
                    existing.raw_payload = payload
                    existing.last_seen_at = now
                    if existing.intake_status == "FAILED":
                        existing.intake_status = "PENDING"
                        existing.error_message = None
                        existing.processed_at = None
                        existing.processed_event_id = None
                queued.append(existing)

            session.commit()
            return queued
        finally:
            session.close()

    async def capture_url_to_intake(
        self, url: str, *, case_id: str | None = None
    ) -> list[IntakeItem]:
        """Fetch a single URL and persist it to the intake queue."""
        article = await fetch_article_content(url)
        return self.ingest_articles(
            [article],
            capture_type="manual_url",
            case_id=case_id,
        )

    async def process_intake_queue(
        self,
        *,
        limit: int | None = None,
        case_id: str | None = None,
        intake_ids: list[str] | None = None,
    ) -> dict[str, int]:
        """Process pending intake records through the AI pipeline."""
        session = get_database().get_session_sync()
        try:
            query = session.query(IntakeItem)
            if intake_ids:
                query = query.filter(IntakeItem.id.in_(intake_ids))
            else:
                query = query.filter(IntakeItem.intake_status == "PENDING")
            if case_id is not None:
                query = query.filter(IntakeItem.case_id == case_id)
            items = query.order_by(IntakeItem.created_at.asc()).all()
            if limit is not None:
                items = items[:limit]
            item_ids = [item.id for item in items]
        finally:
            session.close()

        processed = 0
        failed = 0
        for item_id in item_ids:
            ok = await self._process_intake_item(item_id)
            if ok:
                processed += 1
            else:
                failed += 1

        return {
            "processed": processed,
            "failed": failed,
            "selected": len(item_ids),
        }

    async def run_case(
        self,
        *,
        query: str,
        output_dir: Path | None = None,
        conflict: str | None = None,
        confirmed_parties: list[str] | None = None,
        manual_links: list[str] | None = None,
        max_articles: int = 50,
        relevance_threshold: float = 0.3,
        importance: str | None = None,
        monitor_mode: bool = False,
        start_stage: CaseStageName = CaseStageName.BOOTSTRAP,
        automation_mode: str = "exceptions_only",
        case_id: str | None = None,
    ) -> TopicCase:
        session = get_database().get_session_sync()
        try:
            case = self._get_or_create_case(
                session,
                query=query,
                case_id=case_id,
                conflict=conflict,
                importance=importance,
                monitor_mode=monitor_mode,
            )
            session.commit()
            case_id_value = case.id
        finally:
            session.close()

        case = self._reload_case(case_id_value)
        context = CaseRunContext(
            case=case,
            run_started_at=_utcnow(),
            output_dir=(output_dir or self.output_root) / "cases" / case.slug,
        )
        if start_stage != CaseStageName.BOOTSTRAP:
            self._hydrate_context_from_case(context)

        effective_automation_mode = _normalize_automation_mode(
            automation_mode
            or context.case.routing_mode
            or (context.case.metadata_json or {}).get("bootstrap", {}).get("automation_mode")
        )
        execution_automation_mode = _execution_automation_mode(
            automation_mode
            or context.case.routing_mode
            or (context.case.metadata_json or {}).get("bootstrap", {}).get("automation_mode")
        )

        requested_index = STAGE_ORDER.index(start_stage)
        for stage in STAGE_ORDER[requested_index:]:
            if stage == CaseStageName.BOOTSTRAP:
                await self._stage_bootstrap(
                    context,
                    conflict=conflict,
                    confirmed_parties=confirmed_parties or [],
                    manual_links=manual_links or [],
                    automation_mode=effective_automation_mode,
                )
            elif stage == CaseStageName.RETRIEVE:
                await self._stage_retrieve(
                    context,
                    conflict=conflict,
                    confirmed_parties=confirmed_parties or [],
                    manual_links=manual_links or [],
                    max_articles=max_articles,
                    relevance_threshold=relevance_threshold,
                    monitor_mode=monitor_mode,
                )
            elif stage == CaseStageName.TRIAGE:
                await self._stage_triage(
                    context, max_articles=max_articles, monitor_mode=monitor_mode
                )
            elif stage == CaseStageName.INVESTIGATE:
                await self._stage_investigate(context)
            elif stage == CaseStageName.ARBITRATE:
                await self._stage_arbitrate(context, monitor_mode=monitor_mode)
            elif stage == CaseStageName.REPORT:
                await self._stage_report(context)

            if context.case.status == CaseStatus.FAILED:
                break

            if self._should_pause_after_stage(
                context.case, stage_name=stage, automation_mode=execution_automation_mode
            ):
                self._pause_case_for_manual_action(
                    context.case.id,
                    stage_name=stage,
                    automation_mode=execution_automation_mode,
                )
                context.case = self._reload_case(context.case.id)
                break

        return self._reload_case(context.case.id)

    async def rerun_case(
        self,
        case_id: str,
        *,
        start_stage: CaseStageName | None = None,
        output_dir: Path | None = None,
    ) -> TopicCase:
        session = get_database().get_session_sync()
        try:
            case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
            if case is None:
                raise ValueError(f"Case {case_id} not found")
            query = case.query
            conflict = case.conflict
            importance = case.importance
            monitor_mode = case.status == CaseStatus.MONITORING
            automation_mode = (
                case.routing_mode
                or (case.metadata_json or {}).get("bootstrap", {}).get("automation_mode")
            )
            next_stage = start_stage or self._next_stage_for_case(case)
        finally:
            session.close()

        return await self.run_case(
            query=query,
            output_dir=output_dir,
            conflict=conflict,
            importance=importance,
            start_stage=next_stage,
            case_id=case_id,
            automation_mode=automation_mode,
            monitor_mode=monitor_mode,
        )

    def review_case(
        self, case_id: str, decision: str, notes: str | None = None
    ) -> TopicCase:
        session = get_database().get_session_sync()
        try:
            case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
            if case is None:
                raise ValueError(f"Case {case_id} not found")

            reviews = (
                session.query(Review)
                .join(Event, Review.event_id == Event.id)
                .filter(Event.case_id == case_id)
                .all()
            )

            normalized = decision.lower()
            if normalized == "approve":
                open_exceptions = _get_open_exceptions(case.metadata_json or {})
                if open_exceptions:
                    unresolved = ", ".join(sorted({item["type"] for item in open_exceptions}))
                    raise ValueError(
                        f"Case {case_id} still has unresolved exceptions: {unresolved}"
                    )
                case.status = CaseStatus.APPROVED
                target_status = ReviewStatus.APPROVED
            elif normalized == "reject":
                case.status = CaseStatus.REJECTED
                target_status = ReviewStatus.REJECTED
            elif normalized in {"action_required", "exception"}:
                case.status = CaseStatus.REVIEW_READY
                target_status = ReviewStatus.ACTION_REQUIRED
            else:
                case.status = CaseStatus.REVIEW_READY
                target_status = None

            if target_status is not None:
                for review in reviews:
                    review.status = target_status
                    review.reviewed_at = _utcnow()

            case.last_reviewed_at = _utcnow()
            case.review_notes = notes
            case.metadata_json = _resolve_case_exceptions(
                case.metadata_json or {}, decision=normalized, notes=notes
            )
            case.open_review_items = _compute_open_review_items(
                case.metadata_json, reviews
            )
            self._record_audit_entry(
                session,
                case_id=case_id,
                action_type=f"review:{normalized}",
                target_type="case",
                target_id=case_id,
                actor="operator",
                rationale=notes,
                metadata={"status": case.status.value if case.status else None},
            )
            session.commit()
            return case
        finally:
            session.close()

    def update_exception_status(
        self,
        case_id: str,
        exception_id: str,
        *,
        action: str,
        notes: str | None = None,
    ) -> TopicCase:
        session = get_database().get_session_sync()
        try:
            case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
            if case is None:
                raise ValueError(f"Case {case_id} not found")

            normalized_action = action.strip().lower()
            if normalized_action not in {"resolve", "defer", "reopen"}:
                raise ValueError(f"Unsupported exception action: {action}")

            exception_queue = []
            found = False
            for item in (case.metadata_json or {}).get("exception_queue", []):
                normalized = _coerce_exception(item)
                if normalized["id"] == exception_id:
                    found = True
                    if normalized_action == "resolve":
                        normalized["status"] = "resolved"
                    elif normalized_action == "defer":
                        normalized["status"] = "deferred"
                    else:
                        normalized["status"] = "open"
                    normalized["updated_at"] = _utcnow().isoformat()
                    if notes:
                        normalized["resolution_notes"] = notes
                exception_queue.append(normalized)

            if not found:
                raise ValueError(f"Exception {exception_id} not found for case {case_id}")

            metadata_json = dict(case.metadata_json or {})
            metadata_json["exception_queue"] = exception_queue
            case.metadata_json = metadata_json
            reviews = (
                session.query(Review)
                .join(Event, Review.event_id == Event.id)
                .filter(Event.case_id == case_id)
                .all()
            )
            case.open_review_items = _compute_open_review_items(metadata_json, reviews)
            case.updated_at = _utcnow()
            self._record_audit_entry(
                session,
                case_id=case_id,
                action_type=f"exception:{normalized_action}",
                target_type="exception",
                target_id=exception_id,
                actor="operator",
                rationale=notes,
                metadata={"action": normalized_action},
            )
            session.commit()
            return case
        finally:
            session.close()

    async def run_monitor_cycle(
        self,
        topics: list[dict[str, Any]],
        *,
        output_root: Path | None = None,
    ) -> list[TopicCase]:
        completed_cases: list[TopicCase] = []
        for topic in topics:
            case = await self.run_case(
                query=topic.get("query", ""),
                conflict=topic.get("conflict"),
                confirmed_parties=topic.get("confirmed_parties"),
                manual_links=topic.get("manual_links"),
                max_articles=topic.get("max_articles", 20),
                relevance_threshold=topic.get("relevance_threshold", 0.3),
                importance=topic.get("importance"),
                output_dir=output_root or self.output_root,
                monitor_mode=True,
                automation_mode=topic.get("automation_mode", "exceptions_only"),
            )
            completed_cases.append(case)
        return completed_cases

    # ─── Stage Methods ───────────────────────────────────────────────────────────

    async def _stage_bootstrap(
        self,
        context: CaseRunContext,
        *,
        conflict: str | None,
        confirmed_parties: list[str],
        manual_links: list[str],
        automation_mode: str,
    ) -> None:
        async def runner() -> dict[str, Any]:
            detected_conflict = conflict or await self.topic_fetcher.analyzer.detect_conflict(
                context.case.query
            )
            source_dir = self.topic_fetcher.data_dir / detected_conflict
            exception_queue: list[dict[str, Any]] = []
            if not source_dir.exists():
                exception_queue.append(
                    _make_exception(
                        exception_type="needs_more_sources",
                        stage=CaseStageName.BOOTSTRAP,
                        message=f"No source pack found for {detected_conflict}",
                        severity="high",
                        details={"conflict": detected_conflict},
                    )
                )
            if not confirmed_parties:
                exception_queue.append(
                    _make_exception(
                        exception_type="needs_party_confirmation",
                        stage=CaseStageName.BOOTSTRAP,
                        message="No bootstrap-confirmed parties were supplied.",
                        severity="medium",
                    )
                )

            bootstrap_result = {
                "query": context.case.query,
                "conflict": detected_conflict,
                "confirmed_parties": confirmed_parties,
                "manual_links": manual_links,
                "automation_mode": automation_mode,
                "exception_queue": exception_queue,
                "source_registry_path": str(source_dir),
            }
            context.bootstrap_result = bootstrap_result
            context.exception_queue = exception_queue
            return bootstrap_result

        await _execute_stage(
            context,
            CaseStageName.BOOTSTRAP,
            runner,
            workflow_name="case_bootstrap",
            model_used=self.config.get("ai", {}).get("model"),
            status_after_success=CaseStatus.PROCESSING,
            persist_callback=_persist_bootstrap_payload,
        )

    async def _stage_retrieve(
        self,
        context: CaseRunContext,
        *,
        conflict: str | None,
        confirmed_parties: list[str],
        manual_links: list[str],
        max_articles: int,
        relevance_threshold: float,
        monitor_mode: bool,
    ) -> None:
        async def runner() -> dict[str, Any]:
            bootstrap = context.bootstrap_result or {}
            result = await self.topic_fetcher.fetch_articles_by_topic(
                query=context.case.query,
                conflict=conflict or bootstrap.get("conflict") or context.case.conflict,
                confirmed_parties=confirmed_parties
                or bootstrap.get("confirmed_parties", []),
                manual_links=manual_links or bootstrap.get("manual_links", []),
                max_articles=max_articles,
                relevance_threshold=relevance_threshold,
            )
            context.fetch_result = result
            return result

        await _execute_stage(
            context,
            CaseStageName.RETRIEVE,
            runner,
            workflow_name="topic_fetcher",
            model_used=self.config.get("ai", {}).get("model"),
            status_after_success=CaseStatus.MONITORING if monitor_mode else CaseStatus.PROCESSING,
            persist_callback=_persist_retrieved_articles,
        )

    async def _stage_triage(
        self, context: CaseRunContext, *, max_articles: int, monitor_mode: bool
    ) -> None:
        def runner() -> dict[str, Any]:
            session = get_database().get_session_sync()
            try:
                query = session.query(CaseArticle).filter(CaseArticle.case_id == context.case.id)
                if monitor_mode:
                    articles = (
                        query.order_by(CaseArticle.is_new.desc(), CaseArticle.relevance_score.desc())
                        .limit(max_articles)
                        .all()
                    )
                else:
                    articles = (
                        query.order_by(CaseArticle.relevance_score.desc()).limit(max_articles).all()
                    )
                context.selected_articles = articles
                summary = {
                    "selected_article_ids": [article.id for article in articles],
                    "selected_count": len(articles),
                    "new_article_count": sum(1 for article in articles if article.is_new),
                    "changed": context.changed,
                }
                return summary
            finally:
                session.close()

        await _execute_stage(
            context,
            CaseStageName.TRIAGE,
            runner,
            workflow_name="triage_selector",
            model_used=None,
            status_after_success=CaseStatus.INVESTIGATING,
            persist_callback=_persist_stage_payload("triage_result"),
        )

    async def _stage_investigate(self, context: CaseRunContext) -> None:
        async def runner() -> dict[str, Any]:
            session = get_database().get_session_sync()
            try:
                if context.selected_articles is None:
                    context.selected_articles = (
                        session.query(CaseArticle)
                        .filter(CaseArticle.case_id == context.case.id)
                        .order_by(CaseArticle.relevance_score.desc())
                        .all()
                    )
            finally:
                session.close()

            processed_events = []
            route_counts = {"baseline_only": 0, "party_investigation": 0}
            exceptions: list[dict[str, Any]] = []
            for article in context.selected_articles or []:
                event = await self._process_case_article(context.case, article)
                processed_events.append(event)
                route_counts[event["workflow_route"]] += 1
                if not event.get("claims"):
                    exceptions.append(
                        _make_exception(
                            exception_type="parse_failure",
                            stage=CaseStageName.INVESTIGATE,
                            message=f"No claims extracted for article '{event['title']}'.",
                            severity="medium",
                            details={"event_id": event["id"], "article_url": event.get("source_url")},
                        )
                    )

            context.processed_events = processed_events
            context.exception_queue = _merge_exception_lists(
                list((context.case.metadata_json or {}).get("exception_queue", [])),
                exceptions,
            )
            return {
                "event_ids": [event["id"] for event in processed_events],
                "event_count": len(processed_events),
                "route_counts": route_counts,
                "events": processed_events,
                "exception_queue": context.exception_queue,
            }

        await _execute_stage(
            context,
            CaseStageName.INVESTIGATE,
            runner,
            workflow_name="workflow_router",
            model_used=self.config.get("ai", {}).get("model"),
            status_after_success=CaseStatus.INVESTIGATING,
            persist_callback=_persist_investigation_outputs,
        )

    async def _stage_arbitrate(
        self, context: CaseRunContext, *, monitor_mode: bool
    ) -> None:
        async def runner() -> dict[str, Any]:
            session = get_database().get_session_sync()
            try:
                events = (
                    session.query(Event)
                    .filter(Event.case_id == context.case.id)
                    .order_by(Event.timestamp.desc())
                    .all()
                )
                reviews = (
                    session.query(Review)
                    .join(Event, Review.event_id == Event.id)
                    .filter(Event.case_id == context.case.id)
                    .all()
                )
            finally:
                session.close()

            contested = [event.id for event in events if event.verification_status.value == "CONTESTED"]
            exception_queue = list((context.case.metadata_json or {}).get("exception_queue", []))
            if contested:
                exception_queue.append(
                    _make_exception(
                        exception_type="needs_evidence_review",
                        stage=CaseStageName.ARBITRATE,
                        message=f"{len(contested)} contested event(s) require review.",
                        severity="high",
                        details={"event_ids": contested},
                    )
                )
            exception_queue = _merge_exception_lists([], exception_queue)
            result = {
                "event_count": len(events),
                "contested_event_ids": contested,
                "review_count": len(reviews),
                "changed": context.changed,
                "monitor_mode": monitor_mode,
                "exception_queue": exception_queue,
            }
            context.exception_queue = exception_queue
            context.case.open_review_items = _compute_open_review_items(
                {"exception_queue": exception_queue}, reviews
            )
            return result

        await _execute_stage(
            context,
            CaseStageName.ARBITRATE,
            runner,
            workflow_name="case_arbiter",
            model_used=None,
            status_after_success=CaseStatus.REVIEW_READY,
            persist_callback=_persist_stage_payload("arbitration_result"),
        )

    async def _stage_report(self, context: CaseRunContext) -> None:
        def runner() -> dict[str, Any]:
            session = get_database().get_session_sync()
            try:
                case = session.query(TopicCase).filter(TopicCase.id == context.case.id).first()
                detail = build_case_detail_payload(session, case)
            finally:
                session.close()
            metadata = {
                "topic": detail["case"]["query"],
                "conflict": detail["case"]["conflict"],
                "queried_at": _utcnow().isoformat(),
                "sources_used": (detail["case"]["metadata"] or {}).get("sources_used", []),
                "articles_fetched": (detail["case"]["metadata"] or {}).get("articles_fetched", 0),
                "articles_processed": len(detail["articles"]),
                "queries_generated": (detail["case"]["metadata"] or {}).get("queries_generated", []),
                "case_id": context.case.id,
                "status": detail["case"]["status"],
                "bootstrap": (detail["case"]["metadata"] or {}).get("bootstrap", {}),
                "exception_queue": detail["exceptions"],
                "stage_runs": detail["stage_runs"],
            }
            results = {
                "articles": detail["articles"],
                "claims": detail["claim_groups"],
                "narratives": detail["narratives"],
                "parties": detail["parties"],
                "party_investigations": detail["party_investigations"],
                "evidence": detail["evidence"],
                "timeline": [
                    {
                        "date": event["timestamp"] or "",
                        "title": event["title"],
                        "description": event["summary"],
                        "status": event["verification_status"],
                    }
                    for event in detail["events"]
                ],
                "executive_summary": build_executive_summary_from_payload(detail["events"]),
                "exceptions": detail["exceptions"],
                "case_detail": detail,
            }
            manifest = {
                "case_id": context.case.id,
                "status": detail["case"]["status"],
                "current_stage": detail["case"]["current_stage"],
                "stage_runs": detail["stage_runs"],
            }
            context.report_bundle = {
                "metadata": metadata,
                "results": results,
                "manifest": manifest,
            }
            return {
                "article_count": len(detail["articles"]),
                "event_count": len(detail["events"]),
                "report_ready": True,
                "stage_runs": detail["stage_runs"],
                "exception_queue": detail["exceptions"],
            }

        await _execute_stage(
            context,
            CaseStageName.REPORT,
            runner,
            workflow_name="report_bundle",
            model_used=None,
            status_after_success=CaseStatus.REVIEW_READY,
            persist_callback=_persist_report_bundle,
        )

    # ─── Internal Helpers ───────────────────────────────────────────────────────

    def _get_or_create_case(
        self,
        session,
        *,
        query: str,
        case_id: str | None,
        conflict: str | None,
        importance: str | None,
        monitor_mode: bool,
    ) -> TopicCase:
        case = None
        if case_id:
            case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
        if case is None:
            case = session.query(TopicCase).filter(
                TopicCase.slug == _slugify(query)
            ).first()

        if case is None:
            case = TopicCase(
                id=str(uuid.uuid4()),
                query=query,
                slug=_slugify(query),
                conflict=conflict,
                importance=importance,
                status=CaseStatus.MONITORING if monitor_mode else CaseStatus.DISCOVERING,
                current_stage=CaseStageName.BOOTSTRAP,
                metadata_json={"history": [], "exception_queue": []},
            )
            session.add(case)
        else:
            case.query = query
            case.conflict = conflict or case.conflict
            case.importance = importance or case.importance
            case.status = CaseStatus.MONITORING if monitor_mode else CaseStatus.DISCOVERING
            case.current_stage = CaseStageName.BOOTSTRAP

        case.latest_run_started_at = _utcnow()
        return case

    def _reload_case(self, case_id: str) -> TopicCase:
        session = get_database().get_session_sync()
        try:
            return session.query(TopicCase).filter(TopicCase.id == case_id).first()
        finally:
            session.close()

    def _hydrate_context_from_case(self, context: CaseRunContext) -> None:
        metadata = context.case.metadata_json or {}
        context.bootstrap_result = dict(metadata.get("bootstrap") or {}) or None
        context.exception_queue = list(metadata.get("exception_queue") or [])

    async def _process_intake_item(self, intake_id: str) -> bool:
        session = get_database().get_session_sync()
        try:
            item = session.query(IntakeItem).filter(IntakeItem.id == intake_id).first()
            if item is None:
                return False
            item.intake_status = "PROCESSING"
            item.error_message = None
            session.commit()

            article_payload = dict(item.raw_payload or {})
            article_payload.setdefault("title", item.title)
            article_payload.setdefault("content", item.content or "")
            article_payload.setdefault("link", item.url)
            article_payload.setdefault("url", item.url)
            article_payload.setdefault("source_name", item.source_name or "")
            article_payload.setdefault("published_at", item.published_at)
            article_payload.setdefault("timestamp", item.published_at or _utcnow().isoformat())
            article_payload.setdefault("source_type", item.source_type)

            if item.case_id:
                case = session.query(TopicCase).filter(TopicCase.id == item.case_id).first()
                if case is None:
                    item.intake_status = "FAILED"
                    item.error_message = f"Case {item.case_id} not found"
                    session.commit()
                    return False
                case_article = self._ensure_case_article_from_intake(session, item)
                session.commit()
                event = await self._process_case_article(case, case_article)
                create_review = True
                confirmed_parties = (
                    (case.metadata_json or {}).get("bootstrap", {}).get(
                        "confirmed_parties", []
                    )
                )
            else:
                event = await self.ai_workflow.process_article(article_payload)
                create_review = True
                confirmed_parties = None

            if event is None:
                item.intake_status = "FAILED"
                item.error_message = "No claims extracted from intake item"
                session.commit()
                return False

            stored = store_event_in_db(
                event,
                case_id=item.case_id,
                create_review=create_review,
                confirmed_parties=confirmed_parties,
            )
            if not stored:
                item.intake_status = "FAILED"
                item.error_message = "Failed to persist processed event"
                session.commit()
                return False

            item.intake_status = "PROCESSED"
            item.processed_event_id = event["id"]
            item.processed_at = _utcnow()
            item.error_message = None
            item.last_seen_at = _utcnow()

            if item.case_id:
                self._refresh_case_metrics(session, item.case_id)

            session.commit()
            return True
        except Exception as exc:
            logger.exception("Failed to process intake item %s", intake_id)
            failing = session.query(IntakeItem).filter(IntakeItem.id == intake_id).first()
            if failing is not None:
                failing.intake_status = "FAILED"
                failing.error_message = str(exc)
                session.commit()
            return False
        finally:
            session.close()

    def _ensure_case_article_from_intake(
        self, session, intake_item: IntakeItem
    ) -> CaseArticle:
        existing = (
            session.query(CaseArticle)
            .filter(
                CaseArticle.case_id == intake_item.case_id,
                CaseArticle.url == (intake_item.url or f"urn:intake:{intake_item.id}"),
            )
            .first()
        )
        payload = dict(intake_item.raw_payload or {})
        if existing is None:
            existing = CaseArticle(
                id=str(uuid.uuid4()),
                case_id=intake_item.case_id,
                url=intake_item.url or f"urn:intake:{intake_item.id}",
                title=intake_item.title,
                source=intake_item.source_name,
                published_at=intake_item.published_at or "",
                relevance_score=float(payload.get("relevance_score", 0.0) or 0.0),
                fingerprint=intake_item.fingerprint,
                content=intake_item.content,
                raw_payload=payload,
                first_seen_at=intake_item.first_seen_at or _utcnow(),
                last_seen_at=_utcnow(),
                is_new=1,
                source_type=intake_item.source_type,
                source_metadata={
                    "capture_type": intake_item.capture_type,
                    "intake_id": intake_item.id,
                    **(payload.get("source_metadata", {}) or {}),
                },
            )
            session.add(existing)
        else:
            existing.title = intake_item.title or existing.title
            existing.source = intake_item.source_name or existing.source
            existing.published_at = intake_item.published_at or existing.published_at
            existing.content = intake_item.content or existing.content
            existing.raw_payload = payload
            existing.last_seen_at = _utcnow()
            existing.source_type = intake_item.source_type or existing.source_type
            existing.source_metadata = {
                **(existing.source_metadata or {}),
                "capture_type": intake_item.capture_type,
                "intake_id": intake_item.id,
                **(payload.get("source_metadata", {}) or {}),
            }
        return existing

    def _refresh_case_metrics(self, session, case_id: str) -> None:
        from src.cases._support import _compute_open_review_items, _recompute_case_claim_aggregates

        case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
        if case is None:
            return
        case.article_count = (
            session.query(CaseArticle).filter(CaseArticle.case_id == case_id).count()
        )
        case.event_count = session.query(Event).filter(Event.case_id == case_id).count()
        reviews = (
            session.query(Review)
            .join(Event, Review.event_id == Event.id)
            .filter(Event.case_id == case_id)
            .all()
        )
        metadata_json = dict(case.metadata_json or {})
        metadata_json["last_intake_processed_at"] = _utcnow().isoformat()
        metadata_json["intake_summary"] = {
            "processed_items": session.query(IntakeItem)
            .filter(
                IntakeItem.case_id == case_id,
                IntakeItem.intake_status == "PROCESSED",
            )
            .count(),
            "pending_items": session.query(IntakeItem)
            .filter(
                IntakeItem.case_id == case_id,
                IntakeItem.intake_status == "PENDING",
            )
            .count(),
        }
        case.metadata_json = metadata_json
        _recompute_case_claim_aggregates(session, case_id)
        case.open_review_items = _compute_open_review_items(metadata_json, reviews)

    def _record_audit_entry(
        self,
        session,
        *,
        case_id: str,
        action_type: str,
        target_type: str,
        target_id: str,
        actor: str,
        rationale: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReviewAuditEntry:
        entry = ReviewAuditEntry(
            id=str(uuid.uuid4()),
            case_id=case_id,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            actor=actor,
            rationale=rationale,
            metadata_json=metadata or {},
        )
        session.add(entry)
        return entry

    async def _process_case_article(
        self, case: TopicCase, case_article: CaseArticle
    ) -> dict[str, Any]:
        bootstrap = (case.metadata_json or {}).get("bootstrap", {})
        article = dict(case_article.raw_payload or {})
        article_data = {
            "title": article.get("title", case_article.title),
            "content": article.get("content", case_article.content or ""),
            "timestamp": _parse_timestamp(article.get("published_at")),
            "link": article.get("url", case_article.url),
            "source_name": article.get("source", case_article.source or ""),
            "confirmed_parties": bootstrap.get("confirmed_parties", []),
        }

        baseline = await self.ai_workflow.process_article(article_data)
        if baseline is None:
            return {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{case.id}:{case_article.url}")),
                "timestamp": article_data["timestamp"],
                "title": article_data["title"],
                "summary": article_data["content"][:500],
                "verification_status": "ALLEGED",
                "claims": [],
                "narratives": [],
                "parties": [],
                "party_investigations": [],
                "workflow_route": "baseline_only",
                "routing_reason": "no_claims_extracted",
                "source_url": article_data["link"],
                "source_name": article_data["source_name"],
            }

        baseline["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{case.id}:{case_article.url}"))
        baseline["timestamp"] = _parse_timestamp(baseline.get("timestamp"))
        baseline["source_url"] = article_data["link"]
        baseline["source_name"] = article_data["source_name"]
        baseline["source_type"] = getattr(case_article, "source_type", "rss")
        baseline["source_metadata"] = getattr(case_article, "source_metadata", {}) or {}
        baseline["case_article_id"] = case_article.id
        baseline["evidence"] = self._build_event_evidence(case, case_article, baseline)
        baseline["claims"] = self._augment_claims_with_evidence(
            baseline.get("claims", []),
            baseline["evidence"],
            bootstrap.get("confirmed_parties", []),
            baseline["id"],
        )

        should_investigate = self._should_route_to_party_workflow(case, baseline)
        if not should_investigate:
            baseline["workflow_route"] = "baseline_only"
            baseline["routing_reason"] = "baseline_sufficient"
            return baseline

        party_state = await self.party_workflow.ainvoke(
            {
                "article": article_data,
                "claims": [],
                "parties": {},
                "party_investigations": [],
                "final_determinations": [],
                "event_summary": {},
                "error": "",
            }
        )
        normalized = self._merge_party_results(baseline, party_state)
        normalized["workflow_route"] = "party_investigation"
        normalized["routing_reason"] = "contested_or_multi_party"
        return normalized

    def _should_route_to_party_workflow(
        self, case: TopicCase, baseline: dict[str, Any]
    ) -> bool:
        if (case.importance or "").lower() == "high":
            return True
        if baseline.get("verification_status") == "CONTESTED":
            return True
        return len(baseline.get("parties", [])) >= 2

    def _merge_party_results(
        self, baseline: dict[str, Any], party_state: dict[str, Any]
    ) -> dict[str, Any]:
        determinations = party_state.get("final_determinations", [])
        normalized_claims = []
        for index, determination in enumerate(determinations):
            base_claim = (
                baseline.get("claims", [])[index]
                if index < len(baseline.get("claims", []))
                else {}
            )
            normalized_claims.append(
                {
                    **base_claim,
                    "claim": determination.get(
                        "claim_text", base_claim.get("claim", base_claim.get("claim_text"))
                    ),
                    "verification_status": determination.get(
                        "verification_status",
                        base_claim.get("verification_status", "ALLEGED"),
                    ),
                    "fact_allegation_type": determination.get(
                        "fact_allegation_classification"
                    ),
                    "arbiter_reasoning": determination.get("reasoning"),
                    "party_positions": determination.get("party_positions"),
                    "controversy_score": determination.get("controversy_score"),
                }
            )

        summary = party_state.get("event_summary", {})
        llm_metadata = dict(baseline.get("llm_metadata", {}))
        llm_metadata["party_workflow"] = party_state.get("llm_metadata", {})
        merged = {
            **baseline,
            "claims": normalized_claims or baseline.get("claims", []),
            "parties": party_state.get("parties", {}).get("parties", baseline.get("parties", [])),
            "party_investigations": party_state.get("party_investigations", []),
            "event_summary": summary,
            "llm_metadata": llm_metadata,
        }
        if summary.get("verification_distribution"):
            distribution = summary["verification_distribution"]
            for status in ["CONTESTED", "PROBABLE", "CONFIRMED", "ALLEGED", "DEBUNKED"]:
                if distribution.get(status):
                    merged["verification_status"] = status
                    break
        return merged

    def _build_event_evidence(
        self, case: TopicCase, case_article: CaseArticle, event: dict[str, Any]
    ) -> list[dict[str, Any]]:
        source_type = getattr(case_article, "source_type", "rss")
        evidence_type = (
            "manual_submission"
            if source_type == "manual"
            else "social_post"
            if source_type == "social"
            else "article"
        )
        requires_human_review = 1 if source_type in {"social", "manual"} else 0
        return [
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"evidence:{case.id}:{case_article.url}")),
                "case_article_id": case_article.id,
                "evidence_type": evidence_type,
                "source_type": source_type,
                "title": event.get("title", case_article.title),
                "origin_url": case_article.url,
                "canonical_url": case_article.url,
                "publisher": event.get("source_name", case_article.source),
                "published_at": getattr(case_article, "published_at", None),
                "content": case_article.content,
                "capture_metadata": getattr(case_article, "source_metadata", {}) or {},
                "verification_status": "UNVERIFIED",
                "credibility_tier": (
                    getattr(case_article, "source_metadata", {}) or {}
                ).get("credibility_tier", "unknown"),
                "requires_human_review": requires_human_review,
                "relation": "supports",
                "source_diversity_rank": 1,
                "confidence_score": 0.5,
                "verification_checks": [
                    {
                        "check_type": "ingestion",
                        "result": "placeholder_only"
                        if source_type in {"social", "manual"}
                        else "captured",
                        "method": "case_article_ingestion",
                        "notes": (
                            "Sparse content requires review."
                            if source_type in {"social", "manual"}
                            else "Article content captured during retrieval."
                        ),
                        "verified_by": "system",
                    }
                ],
            }
        ]

    def _augment_claims_with_evidence(
        self,
        claims: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        confirmed_parties: list[str],
        event_id: str,
    ) -> list[dict[str, Any]]:
        seen_publishers = {
            (item.get("publisher") or item.get("origin_url") or "unknown")
            for item in evidence
        }
        augmented = []
        for claim in claims:
            claim_text = claim.get("claim", claim.get("claim_text", ""))
            claim_signature = _claim_signature(claim_text)
            party_positions = claim.get("party_positions") or {
                party_name: "NEUTRAL" for party_name in confirmed_parties
            }
            augmented.append(
                {
                    **claim,
                    "id": str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"claim:{event_id}:{claim_signature}",
                        )
                    ),
                    "claim_signature": claim_signature,
                    "support_count": len(evidence),
                    "oppose_count": 0,
                    "source_diversity_count": len(seen_publishers),
                    "party_positions": party_positions,
                    "evidence": evidence,
                }
            )
        return augmented

    def _should_pause_after_stage(
        self,
        case: TopicCase,
        *,
        stage_name: CaseStageName,
        automation_mode: str,
    ) -> bool:
        normalized_mode = _normalize_automation_mode(automation_mode)
        if normalized_mode == "autonomous" or stage_name == CaseStageName.REPORT:
            return False
        if normalized_mode == "blocked":
            return True
        return bool(_get_open_exceptions(case.metadata_json or {}))

    def _pause_case_for_manual_action(
        self,
        case_id: str,
        *,
        stage_name: CaseStageName,
        automation_mode: str,
    ) -> None:
        session = get_database().get_session_sync()
        try:
            case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
            metadata_json = dict(case.metadata_json or {})
            metadata_json["manual_gate"] = {
                "stage": stage_name.value,
                "automation_mode": _normalize_automation_mode(automation_mode),
                "updated_at": _utcnow().isoformat(),
            }
            case.metadata_json = metadata_json
            case.status = CaseStatus.REVIEW_READY
            case.current_stage = stage_name
            case.updated_at = _utcnow()
            session.commit()
        finally:
            session.close()

    def _next_stage_for_case(self, case: TopicCase) -> CaseStageName:
        current_stage = case.current_stage or CaseStageName.BOOTSTRAP
        if current_stage not in STAGE_ORDER:
            return CaseStageName.BOOTSTRAP
        current_index = STAGE_ORDER.index(current_stage)
        if current_index >= len(STAGE_ORDER) - 1:
            return current_stage
        return STAGE_ORDER[current_index + 1]
