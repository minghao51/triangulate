"""Topic case lifecycle orchestration."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import statistics
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import or_

from src.ai.taxonomy import sync_bias_taxonomy
from src.ai.workflow import AIWorkflow
from src.cases._serializers import build_case_detail_payload
from src.ai.workflows.party_investigation_workflow import (
    create_party_investigation_workflow,
)
from src.exporter import JSONExporter, MarkdownExporter
from src.ingester.fetcher import ContentFetcher
from src.ingester.topic_fetcher import (
    COVERAGE_COMPLETE,
    COVERAGE_FAILED,
    COVERAGE_NOT_ATTEMPTED,
    COVERAGE_UNKNOWN,
    SUCCESS_ACQUISITION_STATUSES,
    AcquisitionStatus,
    TopicFetcher,
    coerce_attempted,
    describe_source_outcomes,
    validated_outcome_kind,
)
from src.ingester.url_capture import fetch_article_content
from src.storage import (
    AgentOutput,
    EvaluationRun,
    EvidenceArtifactLink,
    OsintArtifact,
    ReviewAnnotation,
    ReviewAuditEntry,
    TaxonomyVersion,
    WorkflowCheckpoint,
    Claim,
    ClaimEvidenceLink,
    CaseArtifact,
    CaseArticle,
    CaseStageName,
    CaseStageRun,
    CaseStatus,
    EvidenceItem,
    EvidenceVerificationCheck,
    Event,
    IntakeItem,
    MonitorCheckpoint,
    Narrative,
    Party,
    PartyInvestigation,
    Review,
    ReviewStatus,
    StageStatus,
    TopicCase,
    get_database,
)
from src.storage.event_store import store_event_in_db
from src.cases._support import CaseRunContext
from src.cases._persistence import _persist_workflow_diagnostics
from src.cases.evidence import (
    link_contribution,
    normalize_capture_text,
    resolve_effective_relationship,
)
from src.cases.readers import (
    link_read_model,
    read_capture_window,
    read_citation,
    read_claim_detail,
    read_evidence_detail,
)
from src.storage.review_state import (
    bind_review_decision,
    compute_event_analysis_hash,
)

logger = logging.getLogger(__name__)

STAGE_ORDER = [
    CaseStageName.BOOTSTRAP,
    CaseStageName.RETRIEVE,
    CaseStageName.TRIAGE,
    CaseStageName.INVESTIGATE,
    CaseStageName.ARBITRATE,
    CaseStageName.REPORT,
]

AUTOMATION_MODE_ALIASES = {
    "exceptions_only": "safe",
    "safe": "safe",
    "blocked": "blocked",
    "autonomous": "autonomous",
}


def retrieval_acquisition_observation(result: dict[str, Any]) -> dict[str, Any]:
    """Derive the canonical acquisition observation for a retrieval result.

    Coverage and counts are derived **only** from validated per-source outcomes.
    A caller-supplied top-level ``acquisition_coverage``/``acquisition_counts`` is
    untrusted and can never upgrade a failed/partial/not-attempted/unknown
    observation to ``complete_requested_scope``. A result without structured
    outcomes, or explicitly flagged ``acquisition_observed=False`` (legacy
    TopicFetcher/caller output), stays ``unknown`` and unobserved - an empty
    ``source_outcomes`` list is never retroactively treated as a fresh success.
    """
    total = result.get("source_plan_total")
    if not isinstance(total, int) or isinstance(total, bool) or total <= 0:
        total = 0
    plan = result.get("source_plan")
    visible_plan_length = len(plan) if isinstance(plan, list) else 0
    # Conservative reconciliation: a reported total may never shrink the known
    # requested scope below the visible plan; the summarizer then enforces at
    # least the observed record count.
    requested_hint = max(total, visible_plan_length)
    known_requested = requested_hint if requested_hint > 0 else None

    raw_outcomes = result.get("source_outcomes")
    if raw_outcomes is None or result.get("acquisition_observed") is False:
        return {
            "coverage": COVERAGE_UNKNOWN,
            "counts": describe_source_outcomes(
                [], requested_count=known_requested
            )["counts"],
            "sources": [],
            "observed": False,
        }

    sources = [dict(outcome) for outcome in raw_outcomes]
    summary = describe_source_outcomes(sources, requested_count=known_requested)
    return {
        "coverage": summary["coverage"],
        "counts": summary["counts"],
        "sources": sources,
        "observed": True,
    }


def _has_usable_seed_context(
    acquisition_sources: list[dict[str, Any]], articles: list[dict[str, Any]]
) -> bool:
    """True when a never-attempted manual/social seed has a real sparse article.

    A fabricated skip outcome, or a seed outcome with no matching usable article
    in the retrieval result, is not seed context: it cannot soften a fatal
    no-acquisition run. Matching is by URL plus seed kind (the fetch strategy
    drives the seed kind, so a catalogue row that still reports ``source_type``
    ``rss`` is fine), which avoids legitimate fallback-name differences.
    """
    articles_by_url: dict[str, list[dict[str, Any]]] = {}
    for article in articles:
        url = article.get("url")
        if isinstance(url, str) and url:
            articles_by_url.setdefault(url, []).append(article)

    for source in acquisition_sources:
        if validated_outcome_kind(source) != AcquisitionStatus.SKIPPED.value:
            continue
        if coerce_attempted(source.get("attempted")) is not False:
            continue
        strategy = source.get("fetch_strategy")
        if strategy not in {"manual", "social"}:
            continue
        article_count = source.get("article_count")
        if isinstance(article_count, bool) or not isinstance(article_count, int):
            continue
        if article_count <= 0:
            continue
        url = source.get("source_url")
        if not isinstance(url, str) or not url:
            continue
        for article in articles_by_url.get(url, []):
            if article.get("source_type") != strategy:
                continue
            content = article.get("content")
            if isinstance(content, str) and content.strip():
                return True
    return False


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "case"


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return _utcnow()


def _fingerprint_article(article: dict[str, Any]) -> str:
    payload = f"{article.get('url','')}|{article.get('title','')}|{article.get('source','')}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _payload_checksum(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _claim_signature(claim_text: str) -> str:
    return hashlib.sha256(claim_text.lower().strip().encode("utf-8")).hexdigest()


def _normalize_automation_mode(value: str | None) -> str:
    return AUTOMATION_MODE_ALIASES.get((value or "").strip().lower(), "safe")


def _execution_automation_mode(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized == "exceptions_only":
        return "autonomous"
    return _normalize_automation_mode(value)


class TopicCaseService:
    """Owns topic-oriented case creation, orchestration, and review."""

    def __init__(self, config: dict[str, Any], output_root: Path = Path("./output")):
        self.config = config
        self.output_root = output_root
        self.ai_workflow = AIWorkflow(config)
        self.topic_fetcher = TopicFetcher(config)
        self.party_workflow = create_party_investigation_workflow()
        self.json_exporter = JSONExporter()
        self.markdown_exporter = MarkdownExporter()
        # Runtime taxonomy snapshot (bias taxonomy file), used by the
        # evaluation/agent-output diagnostics.
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
            return self._build_case_detail_payload(session, case)
        finally:
            session.close()

    # -- Inspector readers (E03) -----------------------------------------
    #
    # Thin, GET-only delegation to ``src.cases.readers``. Each call opens and
    # closes its own session exactly like ``get_case_details``; none of them
    # commits, creates captures, materializes legacy rows or runs analysis.
    # ``None`` means "not found for this case" (404); a malformed capture range
    # raises ``CaptureRangeError`` (422).

    def get_citation_detail(
        self, case_id: str, citation_id: str
    ) -> dict[str, Any] | None:
        """Read one immutable citation owned by ``case_id``."""
        session = get_database().get_session_sync()
        try:
            return read_citation(
                session, case_id=case_id, citation_id=citation_id
            )
        finally:
            session.close()

    def get_claim_detail(
        self, case_id: str, claim_id: str
    ) -> dict[str, Any] | None:
        """Read one case-owned claim with its evidence passages."""
        session = get_database().get_session_sync()
        try:
            return read_claim_detail(session, case_id=case_id, claim_id=claim_id)
        finally:
            session.close()

    def get_evidence_detail(
        self, case_id: str, evidence_id: str
    ) -> dict[str, Any] | None:
        """Read one case-owned evidence item, its captures and its claims."""
        session = get_database().get_session_sync()
        try:
            return read_evidence_detail(
                session, case_id=case_id, evidence_id=evidence_id
            )
        finally:
            session.close()

    def get_capture_window(
        self,
        case_id: str,
        evidence_id: str,
        capture_id: str,
        *,
        start: int,
        length: int,
    ) -> dict[str, Any] | None:
        """Read one bounded code-point window of an immutable capture."""
        session = get_database().get_session_sync()
        try:
            return read_capture_window(
                session,
                case_id=case_id,
                evidence_id=evidence_id,
                capture_id=capture_id,
                start=start,
                length=length,
            )
        finally:
            session.close()

    def fetch_and_intake_articles(
        self,
        *,
        source: str | None = None,
        limit: int | None = None,
        case_id: str | None = None,
    ) -> list[IntakeItem]:
        """Fetch source content and persist it to the durable intake queue."""
        fetcher = ContentFetcher(self.config)
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
                open_exceptions = self._get_open_exceptions(case.metadata_json or {})
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
                    # Bind the decision to the analysis revision it reviewed so
                    # a later rewrite only invalidates a materially changed one.
                    review_event_id: Any = review.event_id
                    bind_review_decision(
                        review,
                        compute_event_analysis_hash(session, review_event_id),
                    )

            case.last_reviewed_at = _utcnow()
            case.review_notes = notes
            case.metadata_json = self._resolve_case_exceptions(
                case.metadata_json or {}, decision=normalized, notes=notes
            )
            case.open_review_items = self._compute_open_review_items(
                case.metadata_json, reviews
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
                normalized = self._coerce_exception(item)
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
            case.open_review_items = self._compute_open_review_items(metadata_json, reviews)
            case.updated_at = _utcnow()
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
                    self._make_exception(
                        exception_type="needs_more_sources",
                        stage=CaseStageName.BOOTSTRAP,
                        message=f"No source pack found for {detected_conflict}",
                        severity="high",
                        details={"conflict": detected_conflict},
                    )
                )
            if not confirmed_parties:
                exception_queue.append(
                    self._make_exception(
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

        await self._execute_stage(
            context,
            CaseStageName.BOOTSTRAP,
            runner,
            workflow_name="case_bootstrap",
            model_used=self.config.get("ai", {}).get("model"),
            status_after_success=CaseStatus.PROCESSING,
            persist_callback=self._persist_bootstrap_payload,
        )

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
        self._recompute_case_claim_aggregates(session, case_id)
        case.open_review_items = self._compute_open_review_items(metadata_json, reviews)

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

        await self._execute_stage(
            context,
            CaseStageName.RETRIEVE,
            runner,
            workflow_name="topic_fetcher",
            model_used=self.config.get("ai", {}).get("model"),
            status_after_success=CaseStatus.MONITORING if monitor_mode else CaseStatus.PROCESSING,
            persist_callback=self._persist_retrieved_articles,
        )

    def _persist_retrieved_articles(
        self, session, context: CaseRunContext, stage_run: CaseStageRun, result: dict[str, Any]
    ) -> list[str]:
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
        acquisition = retrieval_acquisition_observation(result)
        acquisition["fetch_exceptions"] = list(result.get("fetch_exceptions", []))
        coverage = acquisition["coverage"]

        # Canonicalize acquisition fields on every persisted surface (artifact
        # payload, stage metrics built from this result, case metadata and the
        # checkpoint). A caller-supplied top-level coverage/counts or
        # ``sources_used`` claim is never trusted; when supplied it is kept
        # separately and explicitly labelled as reported/untrusted.
        reported_coverage = result.get("acquisition_coverage")
        reported_counts = result.get("acquisition_counts")
        reported_sources_used = result.get("sources_used")
        canonical_sources_used = [
            source.get("source_name")
            for source in acquisition["sources"]
            if validated_outcome_kind(source) in SUCCESS_ACQUISITION_STATUSES
        ]
        result["source_outcomes"] = acquisition["sources"]
        result["acquisition_coverage"] = coverage
        result["acquisition_counts"] = acquisition["counts"]
        result["acquisition_observed"] = acquisition["observed"]
        result["sources_used"] = canonical_sources_used
        if reported_coverage is not None or reported_counts is not None:
            result["reported_acquisition_summary"] = {
                "coverage": reported_coverage,
                "counts": reported_counts,
                "trusted": False,
            }
        if reported_sources_used and list(reported_sources_used) != canonical_sources_used:
            result["reported_sources_used"] = list(reported_sources_used)

        # A never-attempted manual/social seed is reviewable context only when a
        # real matching sparse article is present; it distinguishes a reviewable
        # config gap from a fatal no-source retrieval.
        usable_seed_present = _has_usable_seed_context(
            acquisition["sources"], list(result.get("articles") or [])
        )
        stage_failure: dict[str, Any] | None = None
        if coverage == COVERAGE_FAILED:
            stage_failure = {
                "reason": "all_sources_failed",
                "coverage": coverage,
                "counts": acquisition["counts"],
                "message": (
                    "All attempted source acquisitions failed; "
                    "retrieval is not successful."
                ),
            }
        elif (
            acquisition["observed"]
            and coverage in (COVERAGE_NOT_ATTEMPTED, COVERAGE_UNKNOWN)
            and not usable_seed_present
        ):
            # No source, no acquisition and no usable seed (empty source pack or a
            # cached-only response) is a fatal retrieval, while its distinct
            # not_attempted/unknown coverage is retained verbatim.
            stage_failure = {
                "reason": "no_source_acquisition",
                "coverage": coverage,
                "counts": acquisition["counts"],
                "message": (
                    "No source was acquired and no usable seed source was "
                    "supplied; retrieval is not successful."
                ),
            }
        if stage_failure is not None:
            # Recorded for the owning stage transaction (same commit): retrieved
            # context and diagnostics stay durable, the stage/case is FAILED and
            # later stages do not run.
            context.stage_failure = stage_failure

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
            "retrieval_acquisition": acquisition,
            "retrieval_coverage": coverage,
            "retrieval_stage_failure": stage_failure,
            "exception_queue": self._merge_exception_lists(
                context.exception_queue or [],
                [
                    self._coerce_exception(item, CaseStageName.RETRIEVE)
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
        prior_successful_run_at = checkpoint.last_successful_run_at
        advanced_successful_checkpoint = coverage == COVERAGE_COMPLETE
        if advanced_successful_checkpoint:
            checkpoint.last_successful_run_at = _utcnow()
        checkpoint.metadata_json = {
            "coverage": coverage,
            "counts": acquisition["counts"],
            "source_outcomes": acquisition["sources"],
            "acquisition_observed": acquisition["observed"],
            "fetch_exceptions": acquisition["fetch_exceptions"],
            "new_article_count": new_article_count,
            "articles_processed": result.get("articles_processed", 0),
            "advanced_successful_checkpoint": advanced_successful_checkpoint,
            "fatal_reason": stage_failure["reason"] if stage_failure else None,
            "retained_successful_run_at": (
                prior_successful_run_at.isoformat()
                if prior_successful_run_at is not None
                else None
            ),
        }
        return artifact_ids

    def _persist_bootstrap_payload(
        self, session, context: CaseRunContext, stage_run: CaseStageRun, result: dict[str, Any]
    ) -> list[str]:
        case = session.query(TopicCase).filter(TopicCase.id == context.case.id).first()
        metadata_json = dict(case.metadata_json or {})
        metadata_json["bootstrap"] = result
        metadata_json["exception_queue"] = [
            self._coerce_exception(item, CaseStageName.BOOTSTRAP)
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

        await self._execute_stage(
            context,
            CaseStageName.TRIAGE,
            runner,
            workflow_name="triage_selector",
            model_used=None,
            status_after_success=CaseStatus.INVESTIGATING,
            persist_callback=self._persist_stage_payload("triage_result"),
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
                        self._make_exception(
                            exception_type="parse_failure",
                            stage=CaseStageName.INVESTIGATE,
                            message=f"No claims extracted for article '{event['title']}'.",
                            severity="medium",
                            details={"event_id": event["id"], "article_url": event.get("source_url")},
                        )
                    )

            context.processed_events = processed_events
            context.exception_queue = self._merge_exception_lists(
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

        await self._execute_stage(
            context,
            CaseStageName.INVESTIGATE,
            runner,
            workflow_name="workflow_router",
            model_used=self.config.get("ai", {}).get("model"),
            status_after_success=CaseStatus.INVESTIGATING,
            persist_callback=self._persist_investigation_outputs,
        )

    async def _process_case_article(
        self, case: TopicCase, case_article: CaseArticle
    ) -> dict[str, Any]:
        bootstrap = (case.metadata_json or {}).get("bootstrap", {})
        article = dict(case_article.raw_payload or {})
        # One canonical source body: prefer the raw payload body (the text the
        # collector has always received) when it is known, otherwise the stored
        # case-article projection. Normalize CRLF/CR -> LF once and use the same
        # text for analysis, the evidence payload, the compatibility projection
        # and the immutable capture. A generated summary/title is never used as
        # a substitute source body.
        raw_content = article.get("content")
        source_body = (
            raw_content if raw_content is not None else case_article.content
        )
        # ``None`` stays unknown: it only becomes a compatibility empty string
        # for the AI call, never an invented empty capture. An explicit empty
        # string remains a real empty body.
        canonical_content = (
            normalize_capture_text(source_body) if source_body is not None else None
        )
        article_data = {
            "title": article.get("title", case_article.title),
            "content": canonical_content if canonical_content is not None else "",
            "timestamp": _parse_timestamp(article.get("published_at")),
            "link": article.get("url", case_article.url),
            "source_name": article.get("source", case_article.source or ""),
            "confirmed_parties": bootstrap.get("confirmed_parties", []),
        }

        baseline: dict[str, Any] | None = (
            await self.ai_workflow.process_article(article_data)
        )
        is_fallback = baseline is None
        if is_fallback:
            # The workflow only returns ``None`` for fallback/unavailable
            # extraction. Record that explicitly instead of leaving the event
            # outcome absent: the event store derives replacement authority from
            # this status and must not treat a failed rerun as a legacy caller
            # that may overwrite valid stored analysis. The key set mirrors
            # ``ExtractionOutcomeSchema``; scope numbers stay zero because this
            # path never performed a scoped extraction.
            outcome: Any = {
                "status": "fallback",
                "quote_proposals_trusted": False,
                "scope_start": 0,
                "scope_end": 0,
                "body_char_count": 0,
                "input_limit": 0,
                "source_available": bool(canonical_content),
                "reason": "no_claims_extracted",
            }
            baseline = {
                "id": str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL, f"{case.id}:{case_article.url}"
                    )
                ),
                "timestamp": article_data["timestamp"],
                "title": article_data["title"],
                "summary": (canonical_content or "")[:500],
                "verification_status": "ALLEGED",
                "claims": [],
                "narratives": [],
                "parties": [],
                "party_investigations": [],
                "workflow_route": "baseline_only",
                "routing_reason": "no_claims_extracted",
                "extraction_outcome": outcome,
            }
        else:
            # Capture the collector's own outcome before the merge/rewrite can
            # change anything; ``None`` means a caller/fake did not supply one
            # and therefore keeps legacy replacement semantics in the store.
            outcome = baseline.get("extraction_outcome")
            baseline["id"] = str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"{case.id}:{case_article.url}")
            )
            baseline["timestamp"] = _parse_timestamp(baseline.get("timestamp"))
            baseline["extraction_outcome"] = outcome

        # Common finalization: a fallback zero-claim event is still a valid event
        # with a supplied source, so it keeps the same source evidence/capture.
        baseline["source_url"] = article_data["link"]
        baseline["source_name"] = article_data["source_name"]
        baseline["source_type"] = getattr(case_article, "source_type", "rss")
        baseline["source_metadata"] = getattr(case_article, "source_metadata", {}) or {}
        baseline["case_article_id"] = case_article.id
        baseline["evidence"] = self._build_event_evidence(
            case, case_article, baseline, content=canonical_content
        )
        baseline["claims"] = self._augment_claims_with_evidence(
            baseline.get("claims", []),
            baseline["evidence"],
            bootstrap.get("confirmed_parties", []),
            baseline["id"],
        )

        if is_fallback:
            return baseline

        # A validated empty collection is a real, authoritative result with no
        # claims. Routing it through the party workflow would launch a second
        # extraction attempt over zero claims, so short-circuit here.
        if isinstance(outcome, dict) and outcome.get("status") == "empty":
            baseline["workflow_route"] = "baseline_only"
            baseline["routing_reason"] = "validated_empty_extraction"
            return baseline

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
        baseline_claims = baseline.get("claims", []) or []
        # Match determinations to baseline claims by real claim identity (the
        # existing exact signature), never by list position. A quotation or any
        # other assertion-specific field must never move onto different text.
        claims_by_signature: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for position, claim in enumerate(baseline_claims):
            claim_text = claim.get("claim", claim.get("claim_text", ""))
            claims_by_signature.setdefault(_claim_signature(claim_text), []).append(
                (position, claim)
            )
        consumed_positions: set[int] = set()

        def take_baseline_claim(signature: str) -> dict[str, Any] | None:
            """Return the first unconsumed baseline claim with this signature."""
            for position, claim in claims_by_signature.get(signature, []):
                if position not in consumed_positions:
                    consumed_positions.add(position)
                    return claim
            return None

        normalized_claims: list[dict[str, Any]] = []
        # Event-level source attachment. Every baseline claim is linked to the
        # same source document(s) for this event, so a claim whose text changed is
        # still backed by that source even when no quotation may follow it.
        source_evidence = list(baseline.get("evidence") or [])
        for determination in determinations:
            proposed_text = determination.get("claim_text")
            base_claim = (
                take_baseline_claim(_claim_signature(proposed_text))
                if isinstance(proposed_text, str)
                else None
            )
            final_text = proposed_text if isinstance(proposed_text, str) else ""
            if not final_text.strip() and base_claim is not None:
                # Defensive compatibility: keep the matched baseline assertion
                # when a determination omits its own text.
                final_text = base_claim.get(
                    "claim", base_claim.get("claim_text", "")
                )
            if not isinstance(final_text, str) or not final_text.strip():
                # Never store an empty assertion: with no text there is nothing
                # to attach a source or a proposal to.
                logger.warning(
                    "Skipping party determination without claim text for event %s",
                    baseline.get("id"),
                )
                continue
            finalized: dict[str, Any] = (
                {**base_claim} if base_claim is not None else {}
            )
            finalized.update(
                {
                    "claim": final_text,
                    "verification_status": determination.get(
                        "verification_status",
                        finalized.get("verification_status", "ALLEGED"),
                    ),
                    "fact_allegation_type": determination.get(
                        "fact_allegation_classification"
                    ),
                    "arbiter_reasoning": determination.get("reasoning"),
                    "party_positions": determination.get("party_positions"),
                    "controversy_score": determination.get("controversy_score"),
                }
            )
            if base_claim is None:
                # No identity match: the claim is genuinely new text. Keep the
                # event-level source attachment (and the attachment-derived
                # counts/identity the shared helper recomputes from the final
                # text) but nothing assertion-specific from a positional
                # neighbour -- no quotation, offsets, citation or assessment.
                finalized = self._augment_claims_with_evidence(
                    [finalized], source_evidence, [], baseline["id"]
                )[0]
            else:
                # Identity always describes the text that is actually stored.
                final_signature = _claim_signature(final_text)
                finalized["id"] = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"claim:{baseline['id']}:{final_signature}",
                    )
                )
                finalized["claim_signature"] = final_signature
            normalized_claims.append(finalized)

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
        self,
        case: TopicCase,
        case_article: CaseArticle,
        event: dict[str, Any],
        *,
        content: str | None = None,
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
                # The same canonical body supplied to analysis; never a summary
                # or title substitute.
                "content": (
                    content if content is not None else case_article.content
                ),
                "capture_metadata": getattr(case_article, "source_metadata", {}) or {},
                "verification_status": "UNVERIFIED",
                "credibility_tier": (
                    getattr(case_article, "source_metadata", {}) or {}
                ).get("credibility_tier", "unknown"),
                "requires_human_review": requires_human_review,
                "source_diversity_rank": 1,
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
                    # Corroboration is never attachment-based: an attachment is
                    # not evidence of support. Real support/opposition counts are
                    # derived by ``_recompute_case_claim_aggregates`` from
                    # eligible, policy-resolved stored links only.
                    "support_count": 0,
                    "oppose_count": 0,
                    "source_diversity_count": len(seen_publishers),
                    "party_positions": party_positions,
                    "evidence": evidence,
                }
            )
        return augmented

    def _persist_investigation_outputs(
        self, session, context: CaseRunContext, stage_run: CaseStageRun, result: dict[str, Any]
    ) -> list[str]:
        artifact_ids: list[str] = []
        confirmed_parties = (
            (context.bootstrap_result or {}).get("confirmed_parties")
            or (context.case.metadata_json or {}).get("bootstrap", {}).get("confirmed_parties", [])
        )
        for event in context.processed_events or []:
            # Share the caller-owned session with the artifact/count writes below
            # so one failed event write fails the whole investigation batch.
            store_event_in_db(
                event,
                case_id=context.case.id,
                case_run_id=stage_run.id,
                create_review=True,
                confirmed_parties=confirmed_parties,
                session=session,
            )

        # SessionLocal uses autoflush=False; make the rewritten events visible
        # before counting events, recomputing aggregates and loading reviews.
        session.flush()

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
        self._recompute_case_claim_aggregates(session, context.case.id)
        reviews = (
            session.query(Review)
            .join(Event, Review.event_id == Event.id)
            .filter(Event.case_id == context.case.id)
            .all()
        )
        case.open_review_items = self._compute_open_review_items(case.metadata_json, reviews)
        context.case.event_count = event_count
        context.case.metadata_json = case.metadata_json
        context.case.open_review_items = case.open_review_items
        return artifact_ids

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
                    self._make_exception(
                        exception_type="needs_evidence_review",
                        stage=CaseStageName.ARBITRATE,
                        message=f"{len(contested)} contested event(s) require review.",
                        severity="high",
                        details={"event_ids": contested},
                    )
                )
            exception_queue = self._merge_exception_lists([], exception_queue)
            result = {
                "event_count": len(events),
                "contested_event_ids": contested,
                "review_count": len(reviews),
                "changed": context.changed,
                "monitor_mode": monitor_mode,
                "exception_queue": exception_queue,
            }
            context.exception_queue = exception_queue
            context.case.open_review_items = self._compute_open_review_items(
                {"exception_queue": exception_queue}, reviews
            )
            return result

        await self._execute_stage(
            context,
            CaseStageName.ARBITRATE,
            runner,
            workflow_name="case_arbiter",
            model_used=None,
            status_after_success=CaseStatus.REVIEW_READY,
            persist_callback=self._persist_stage_payload("arbitration_result"),
        )

    async def _stage_report(self, context: CaseRunContext) -> None:
        def runner() -> dict[str, Any]:
            session = get_database().get_session_sync()
            try:
                case = session.query(TopicCase).filter(TopicCase.id == context.case.id).first()
                detail = self._build_case_detail_payload(session, case)
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
                "executive_summary": self._build_executive_summary_from_payload(detail["events"]),
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

        await self._execute_stage(
            context,
            CaseStageName.REPORT,
            runner,
            workflow_name="report_bundle",
            model_used=None,
            status_after_success=CaseStatus.REVIEW_READY,
            persist_callback=self._persist_report_bundle,
        )

    def _persist_report_bundle(
        self, session, context: CaseRunContext, stage_run: CaseStageRun, result: dict[str, Any]
    ) -> list[str]:
        if context.report_bundle is None:
            return []

        context.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = context.output_dir / "topic_analysis.json"
        md_path = context.output_dir / "topic_report.md"
        manifest_path = context.output_dir / "manifest.json"

        self.json_exporter.export(
            context.report_bundle["results"],
            context.report_bundle["metadata"],
            json_path,
        )
        self.markdown_exporter.export(
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

    def _persist_stage_payload(self, artifact_type: str):
        def callback(session, context: CaseRunContext, stage_run: CaseStageRun, result: dict[str, Any]) -> list[str]:
            if "exception_queue" in result:
                case = session.query(TopicCase).filter(TopicCase.id == context.case.id).first()
                metadata_json = dict(case.metadata_json or {})
                metadata_json["exception_queue"] = [
                    self._coerce_exception(item, stage_run.stage_name)
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
                case.open_review_items = self._compute_open_review_items(
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

    def _build_executive_summary(self, events: list[Event]) -> str:
        if not events:
            return "No events have been promoted into the case timeline yet."
        contested = sum(1 for event in events if event.verification_status.value == "CONTESTED")
        probable = sum(1 for event in events if event.verification_status.value == "PROBABLE")
        confirmed = sum(1 for event in events if event.verification_status.value == "CONFIRMED")
        return (
            f"This case currently tracks {len(events)} event(s): "
            f"{confirmed} confirmed, {probable} probable, and {contested} contested."
        )

    def _build_executive_summary_from_payload(
        self, events: list[dict[str, Any]]
    ) -> str:
        if not events:
            return "No events have been promoted into the case timeline yet."
        contested = sum(1 for event in events if event["verification_status"] == "CONTESTED")
        probable = sum(1 for event in events if event["verification_status"] == "PROBABLE")
        confirmed = sum(1 for event in events if event["verification_status"] == "CONFIRMED")
        return (
            f"This case currently tracks {len(events)} event(s): "
            f"{confirmed} confirmed, {probable} probable, and {contested} contested."
        )

    async def _execute_stage(
        self,
        context: CaseRunContext,
        stage_name: CaseStageName,
        runner,
        *,
        workflow_name: str | None,
        model_used: str | None,
        status_after_success: CaseStatus,
        persist_callback,
    ) -> None:
        stage_run_id = str(uuid.uuid4())
        started_at = _utcnow()
        self._mark_stage_running(
            context.case.id,
            stage_run_id,
            stage_name,
            started_at,
            workflow_name=workflow_name,
            model_used=model_used,
        )

        try:
            context.stage_failure = None
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
                # A persist callback may record a recorded-but-fatal outcome (for
                # example: every attempted source acquisition failed). It must be
                # honoured inside this same transaction so diagnostics persist and
                # no fake COMPLETED stage is committed first.
                stage_failure = context.stage_failure
                context.stage_failure = None
                stage_run.completed_at = _utcnow()
                stage_run.duration_ms = duration_ms
                stage_run.output_artifact_ids = artifact_ids
                stage_run.metrics_json = json.loads(
                    json.dumps(result, default=str)
                )
                stage_run.confidence_score = self._derive_confidence(result)
                stage_run.controversy_score = self._derive_controversy(result)
                stage_run.fallback_count = self._count_nested_flag(
                    result, flag_name="fallback_used"
                )
                stage_run.parse_failure_count = self._count_parse_failures(result)
                if stage_failure is not None:
                    stage_run.status = StageStatus.FAILED
                    stage_run.error_message = str(
                        stage_failure.get("message")
                        or f"Stage {stage_name.value} reported failure"
                    )
                    case.status = CaseStatus.FAILED
                else:
                    stage_run.status = StageStatus.COMPLETED
                    case.status = status_after_success
                case.current_stage = stage_name
                case.latest_run_completed_at = _utcnow()
                case.updated_at = _utcnow()
                # Durable per-stage checkpoint + typed agent outputs (diagnostics
                # only; never a success claim beyond the recorded status).
                _persist_workflow_diagnostics(
                    session,
                    case_id=context.case.id,
                    stage_run_id=stage_run.id,
                    stage_name=stage_name,
                    workflow_name=workflow_name,
                    status="failed" if stage_failure is not None else "completed",
                    result=json.loads(json.dumps(result, default=str)),
                    summary=(
                        str(stage_failure.get("message"))
                        if stage_failure is not None
                        else f"{stage_name.value} completed successfully."
                    ),
                    retry_count=stage_run.retry_count or 0,
                )
                session.commit()
                context.case = case
            except Exception:
                session.rollback()
                raise
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
                metadata_json["exception_queue"] = self._merge_exception_lists(
                    metadata_json.get("exception_queue", []),
                    [
                        self._make_exception(
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
                session.commit()
                context.case = case
            finally:
                session.close()

    def _mark_stage_running(
        self,
        case_id: str,
        stage_run_id: str,
        stage_name: CaseStageName,
        started_at: datetime,
        *,
        workflow_name: str | None,
        model_used: str | None,
    ) -> None:
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

    def _derive_confidence(self, result: dict[str, Any]) -> float | None:
        if "confidence_score" in result:
            return result["confidence_score"]
        if result.get("event_count") == 0:
            return 0.0
        if result.get("route_counts"):
            total = sum(result["route_counts"].values()) or 1
            return result["route_counts"].get("baseline_only", 0) / total
        return None

    def _derive_controversy(self, result: dict[str, Any]) -> float | None:
        if "controversy_score" in result:
            return result["controversy_score"]
        contested = len(result.get("contested_event_ids", []))
        total = result.get("event_count", 0)
        if total:
            return contested / total
        return None

    def _count_nested_flag(self, payload: Any, *, flag_name: str) -> int:
        if isinstance(payload, dict):
            count = 1 if payload.get(flag_name) else 0
            return count + sum(
                self._count_nested_flag(value, flag_name=flag_name)
                for value in payload.values()
            )
        if isinstance(payload, list):
            return sum(
                self._count_nested_flag(item, flag_name=flag_name) for item in payload
            )
        return 0

    def _count_parse_failures(self, payload: Any) -> int:
        if isinstance(payload, dict):
            count = 1 if payload.get("parse_status") in {"fallback", "error"} else 0
            return count + sum(
                self._count_parse_failures(value) for value in payload.values()
            )
        if isinstance(payload, list):
            return sum(self._count_parse_failures(item) for item in payload)
        return 0

    def _make_exception(
        self,
        *,
        exception_type: str,
        stage: CaseStageName,
        message: str,
        severity: str,
        details: dict[str, Any] | None = None,
        status: str = "open",
    ) -> dict[str, Any]:
        fingerprint = _payload_checksum(
            {
                "type": exception_type,
                "stage": stage.value,
                "message": message,
                "details": details or {},
            }
        )
        return {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"exception:{fingerprint}")),
            "type": exception_type,
            "stage": stage.value,
            "severity": severity,
            "status": status,
            "message": message,
            "details": details or {},
            "created_at": _utcnow().isoformat(),
            "updated_at": _utcnow().isoformat(),
        }

    def _coerce_exception(
        self, item: dict[str, Any], stage: CaseStageName | None = None
    ) -> dict[str, Any]:
        if "id" in item and "status" in item and "severity" in item:
            normalized = dict(item)
            normalized.setdefault("updated_at", _utcnow().isoformat())
            return normalized
        return self._make_exception(
            exception_type=item.get("type", "unknown_exception"),
            stage=stage or CaseStageName.REVIEW,
            message=item.get("message", ""),
            severity=item.get("severity", "medium"),
            details=item.get("details")
            or {
                key: value
                for key, value in item.items()
                if key not in {"type", "message", "severity"}
            },
            status=item.get("status", "open"),
        )

    def _merge_exception_lists(
        self, base: list[dict[str, Any]], updates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for item in base + updates:
            normalized = self._coerce_exception(item)
            existing = merged.get(normalized["id"], {})
            merged[normalized["id"]] = {**existing, **normalized, "updated_at": _utcnow().isoformat()}
        return list(merged.values())

    def _get_open_exceptions(self, metadata_json: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            item
            for item in metadata_json.get("exception_queue", [])
            if item.get("status", "open") != "resolved"
        ]

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
        return bool(self._get_open_exceptions(case.metadata_json or {}))

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
            if case is None:
                raise RuntimeError(f"Case {case_id!r} is missing")
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

    def _resolve_case_exceptions(
        self, metadata_json: dict[str, Any], *, decision: str, notes: str | None
    ) -> dict[str, Any]:
        exception_queue = []
        for item in metadata_json.get("exception_queue", []):
            normalized = self._coerce_exception(item)
            if decision in {"reject"}:
                normalized["status"] = "resolved"
            elif decision in {"action_required", "exception"}:
                normalized["status"] = "open"
            normalized["updated_at"] = _utcnow().isoformat()
            if notes:
                normalized["resolution_notes"] = notes
            exception_queue.append(normalized)
        return {**metadata_json, "exception_queue": exception_queue}

    def _compute_open_review_items(
        self, metadata_json: dict[str, Any], reviews: list[Review]
    ) -> int:
        review_count = sum(
            1
            for review in reviews
            if review.status in {ReviewStatus.PENDING, ReviewStatus.ACTION_REQUIRED}
        )
        return review_count + len(self._get_open_exceptions(metadata_json))

    def _recompute_case_claim_aggregates(self, session, case_id: str) -> None:
        claims = (
            session.query(Claim)
            .join(Event, Claim.event_id == Event.id)
            .filter(Event.case_id == case_id)
            .all()
        )
        if not claims:
            return
        evidence_links = (
            session.query(ClaimEvidenceLink)
            .filter(ClaimEvidenceLink.claim_id.in_([claim.id for claim in claims]))
            .all()
        )
        evidence_items = (
            session.query(EvidenceItem)
            .filter(EvidenceItem.case_id == case_id)
            .all()
        )
        evidence_by_id = {item.id: item for item in evidence_items}
        links_by_claim: dict[str, list[ClaimEvidenceLink]] = {}
        for link in evidence_links:
            links_by_claim.setdefault(link.claim_id, []).append(link)
        grouped: dict[str, dict[str, Any]] = {}
        for claim in claims:
            signature = claim.claim_signature or _claim_signature(claim.claim_text)
            bucket = grouped.setdefault(
                signature,
                {
                    "support": 0,
                    "oppose": 0,
                    "sources": set(),
                    "contributions": set(),
                    "party_positions": {},
                },
            )
            for link in links_by_claim.get(claim.id, []):
                evidence = evidence_by_id.get(link.evidence_id)
                publisher = (
                    evidence.publisher if evidence else None
                ) or (evidence.origin_url if evidence else None) or "unknown"
                # Observed distinct publishers, not an independence claim.
                bucket["sources"].add(publisher)

                # Only eligible, policy-resolved contributions count. A
                # collector ``reported_by``, ``uncertain``, an invalid/unanchored
                # link and a bare source attachment all contribute nothing; the
                # raw legacy ``opposes`` alias alone never becomes opposition.
                resolution = resolve_effective_relationship(
                    stored_relation=link.relation,
                    alignment_status=link.alignment_status,
                    assessment_origin=link.assessment_origin,
                    assessment_version=link.assessment_version,
                    exact_anchor=(link.alignment_status == "exact"),
                    collector_generated=(link.assessment_origin == "collector"),
                )
                contribution = link_contribution(resolution)
                if contribution is None:
                    continue
                # Deduplicate per existing claim group: repeated links/rows for
                # the same evidence and effective relationship count once.
                dedup_key = (str(link.evidence_id), resolution.effective_relationship)
                if dedup_key in bucket["contributions"]:
                    continue
                bucket["contributions"].add(dedup_key)
                if contribution == "support":
                    bucket["support"] += 1
                else:
                    bucket["oppose"] += 1
            bucket["party_positions"].update(claim.party_positions or {})

        for claim in claims:
            signature = claim.claim_signature or _claim_signature(claim.claim_text)
            aggregate = grouped[signature]
            claim.claim_signature = signature
            claim.support_count = aggregate["support"]
            claim.oppose_count = aggregate["oppose"]
            claim.source_diversity_count = len(aggregate["sources"])
            if aggregate["party_positions"]:
                claim.party_positions = aggregate["party_positions"]

    def _build_case_detail_payload(self, session, case: TopicCase) -> dict[str, Any]:
        stage_runs = (
            session.query(CaseStageRun)
            .filter(CaseStageRun.case_id == case.id)
            .order_by(CaseStageRun.started_at.asc())
            .all()
        )
        articles = (
            session.query(CaseArticle)
            .filter(CaseArticle.case_id == case.id)
            .order_by(CaseArticle.relevance_score.desc())
            .all()
        )
        events = (
            session.query(Event)
            .filter(Event.case_id == case.id)
            .order_by(Event.timestamp.desc())
            .all()
        )
        artifacts = (
            session.query(CaseArtifact)
            .filter(CaseArtifact.case_id == case.id)
            .order_by(CaseArtifact.created_at.desc())
            .all()
        )
        claims = (
            session.query(Claim)
            .join(Event, Claim.event_id == Event.id)
            .filter(Event.case_id == case.id)
            .all()
        )
        narratives = (
            session.query(Narrative)
            .filter(
                or_(*[Narrative.cluster_id.like(f"{event.id}:%") for event in events])
            )
            .all()
            if events
            else []
        )
        party_investigations = (
            session.query(PartyInvestigation)
            .filter(PartyInvestigation.event_id.in_([event.id for event in events]))
            .all()
            if events
            else []
        )
        evidence_items = (
            session.query(EvidenceItem)
            .filter(EvidenceItem.case_id == case.id)
            .all()
        )
        verification_checks = (
            session.query(EvidenceVerificationCheck)
            .filter(
                EvidenceVerificationCheck.evidence_id.in_([item.id for item in evidence_items])
            )
            .all()
            if evidence_items
            else []
        )
        claim_links = (
            session.query(ClaimEvidenceLink)
            .filter(ClaimEvidenceLink.claim_id.in_([claim.id for claim in claims]))
            .all()
            if claims
            else []
        )
        party_ids = {
            claim.party_id for claim in claims if getattr(claim, "party_id", None)
        }
        party_ids.update(
            investigation.party_id
            for investigation in party_investigations
            if getattr(investigation, "party_id", None)
        )
        party_names = set()
        for claim in claims:
            party_names.update((claim.party_positions or {}).keys())
        parties = []
        if events:
            party_filters = [Party.event_id.in_([event.id for event in events])]
            if party_ids:
                party_filters.append(Party.id.in_(party_ids))
            if party_names:
                party_filters.append(Party.canonical_name.in_(party_names))
            parties = session.query(Party).filter(or_(*party_filters)).all()
        reviews = (
            session.query(Review)
            .join(Event, Review.event_id == Event.id)
            .filter(Event.case_id == case.id)
            .all()
        )

        evidence_by_id = {item.id: item for item in evidence_items}
        checks_by_evidence: dict[str, list[EvidenceVerificationCheck]] = {}
        for check in verification_checks:
            checks_by_evidence.setdefault(check.evidence_id, []).append(check)
        links_by_claim: dict[str, list[ClaimEvidenceLink]] = {}
        for link in claim_links:
            links_by_claim.setdefault(link.claim_id, []).append(link)

        serialized_evidence = []
        for item in evidence_items:
            serialized_evidence.append(
                {
                    "id": item.id,
                    "event_id": item.event_id,
                    "case_article_id": item.case_article_id,
                    "evidence_type": item.evidence_type,
                    "source_type": item.source_type,
                    "title": item.title,
                    "origin_url": item.origin_url,
                    "canonical_url": item.canonical_url,
                    "publisher": item.publisher,
                    "published_at": item.published_at,
                    "verification_status": item.verification_status,
                    "credibility_tier": item.credibility_tier,
                    "requires_human_review": bool(item.requires_human_review),
                    # Pointer to the immutable current capture; never the body.
                    "current_capture_id": item.current_capture_id,
                    "capture_metadata": item.capture_metadata or {},
                    "verification_checks": [
                        {
                            "id": check.id,
                            "check_type": check.check_type,
                            "result": check.result,
                            "method": check.method,
                            "notes": check.notes,
                            "verified_by": check.verified_by,
                            "verified_at": check.verified_at.isoformat()
                            if check.verified_at
                            else None,
                        }
                        for check in checks_by_evidence.get(item.id, [])
                    ],
                }
            )

        serialized_claims = []
        grouped_claims: dict[str, dict[str, Any]] = {}
        for claim in claims:
            linked_evidence = []
            for link in links_by_claim.get(claim.id, []):
                evidence = evidence_by_id.get(link.evidence_id)
                if evidence is None:
                    continue
                link_fields = link_read_model(link)
                linked_evidence.append(
                    {
                        "id": evidence.id,
                        "relation": link.relation,
                        "confidence_score": link.confidence_score,
                        "source_diversity_rank": link.source_diversity_rank,
                        "title": evidence.title,
                        "publisher": evidence.publisher,
                        "origin_url": evidence.origin_url,
                        "source_type": evidence.source_type,
                        # Citation/alignment diagnostics. ``relation`` above stays
                        # the raw stored value; ``effective_relation`` is the
                        # policy-resolved one (never inflating support).
                        "capture_id": link_fields["capture_id"],
                        "citation_id": link_fields["citation_id"],
                        "quote": link_fields["quote"],
                        "start_char": link_fields["start_char"],
                        "end_char": link_fields["end_char"],
                        "alignment_status": link_fields["alignment_status"],
                        "effective_relation": link_fields["effective_relation"],
                        "assessment_origin": link_fields["assessment_origin"],
                        "assessment_version": link_fields["assessment_version"],
                        "diagnostic_reason": link_fields["diagnostic_reason"],
                    }
                )
            claim_payload = {
                "id": claim.id,
                "event_id": claim.event_id,
                "claim_text": claim.claim_text,
                "narrative_cluster_id": claim.narrative_cluster_id,
                "verification_status": claim.verification_status.value,
                "fact_allegation_type": claim.fact_allegation_type.value
                if claim.fact_allegation_type
                else None,
                "claim_signature": claim.claim_signature,
                "support_count": claim.support_count,
                "oppose_count": claim.oppose_count,
                "source_diversity_count": claim.source_diversity_count,
                "party_positions": claim.party_positions or {},
                "controversy_score": claim.controversy_score,
                "arbiter_reasoning": claim.arbiter_reasoning,
                "evidence": linked_evidence,
            }
            serialized_claims.append(claim_payload)
            signature = claim.claim_signature or _claim_signature(claim.claim_text)
            aggregate = grouped_claims.setdefault(
                signature,
                {
                    "claim_signature": signature,
                    "claim_text": claim.claim_text,
                    "verification_status": claim.verification_status.value,
                    "support_count": 0,
                    "oppose_count": 0,
                    "source_diversity_count": 0,
                    "party_positions": {},
                    "evidence": [],
                    "event_ids": [],
                },
            )
            aggregate["support_count"] = max(aggregate["support_count"], claim.support_count)
            aggregate["oppose_count"] = max(aggregate["oppose_count"], claim.oppose_count)
            aggregate["source_diversity_count"] = max(
                aggregate["source_diversity_count"], claim.source_diversity_count
            )
            aggregate["party_positions"].update(claim.party_positions or {})
            aggregate["event_ids"].append(claim.event_id)
            for item in linked_evidence:
                if item["id"] not in {e["id"] for e in aggregate["evidence"]}:
                    aggregate["evidence"].append(item)

        return {
            "case": {
                "id": case.id,
                "query": case.query,
                "slug": case.slug,
                "conflict": case.conflict,
                "status": case.status.value,
                "current_stage": case.current_stage.value if case.current_stage else None,
                "routing_mode": case.routing_mode,
                "report_path": case.report_path,
                "latest_manifest_path": case.latest_manifest_path,
                "source_count": case.source_count,
                "article_count": case.article_count,
                "event_count": case.event_count,
                "open_review_items": self._compute_open_review_items(
                    case.metadata_json or {}, reviews
                ),
                "review_notes": case.review_notes,
                "metadata": case.metadata_json or {},
                "created_at": case.created_at.isoformat() if case.created_at else None,
                "updated_at": case.updated_at.isoformat() if case.updated_at else None,
            },
            "stage_runs": [
                {
                    "id": run.id,
                    "stage": run.stage_name.value,
                    "status": run.status.value,
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "completed_at": run.completed_at.isoformat()
                    if run.completed_at
                    else None,
                    "duration_ms": run.duration_ms,
                    "workflow_name": run.workflow_name,
                    "model_used": run.model_used,
                    "fallback_count": run.fallback_count,
                    "parse_failure_count": run.parse_failure_count,
                    "metrics": run.metrics_json or {},
                    "error_message": run.error_message,
                }
                for run in stage_runs
            ],
            "articles": [
                {
                    "id": article.id,
                    "url": article.url,
                    "title": article.title,
                    "source": article.source,
                    "published_at": article.published_at,
                    "relevance_score": article.relevance_score,
                    "is_new": bool(article.is_new),
                    "source_type": article.source_type,
                    "source_metadata": article.source_metadata or {},
                }
                for article in articles
            ],
            "events": [
                {
                    "id": event.id,
                    "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                    "title": event.title,
                    "summary": event.summary,
                    "verification_status": event.verification_status.value,
                }
                for event in events
            ],
            "claims": serialized_claims,
            "claim_groups": list(grouped_claims.values()),
            "narratives": [
                {
                    "id": narrative.id,
                    "cluster_id": narrative.cluster_id,
                    "stance_summary": narrative.stance_summary,
                    "source_count": narrative.source_count,
                }
                for narrative in narratives
            ],
            "evidence": serialized_evidence,
            "exceptions": self._merge_exception_lists(
                [], list((case.metadata_json or {}).get("exception_queue", []))
            ),
            "party_investigations": [
                {
                    "id": investigation.id,
                    "event_id": investigation.event_id,
                    "party_id": investigation.party_id,
                    "investigation_data": investigation.investigation_data,
                    "party_stance": investigation.party_stance,
                }
                for investigation in party_investigations
            ],
            "parties": [
                {
                    "id": party.id,
                    "canonical_name": party.canonical_name,
                    "aliases": party.aliases,
                    "description": party.description,
                    "is_bootstrap_confirmed": bool(party.is_bootstrap_confirmed),
                }
                for party in parties
            ],
            "artifacts": [
                {
                    "id": artifact.id,
                    "type": artifact.artifact_type,
                    "path": artifact.path,
                    "checksum": artifact.checksum,
                    "created_at": artifact.created_at.isoformat()
                    if artifact.created_at
                    else None,
                }
                for artifact in artifacts
            ],
        }

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
                "taxonomy": (
                    {
                        "id": self.active_taxonomy.id,
                        "kind": self.active_taxonomy.taxonomy_kind,
                        "version": self.active_taxonomy.version,
                        "path": self.active_taxonomy.path,
                        "checksum": self.active_taxonomy.checksum,
                    }
                    if self.active_taxonomy is not None
                    else None
                ),
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
                len(self._get_open_exceptions(case.metadata_json or {})) for case in cases
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
