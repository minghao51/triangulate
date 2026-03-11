"""Topic case lifecycle orchestration."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import or_

from src.ai.workflow import AIWorkflow
from src.ai.workflows.party_investigation_workflow import (
    create_party_investigation_workflow,
)
from src.exporter import JSONExporter, MarkdownExporter
from src.ingester.topic_fetcher import TopicFetcher
from src.storage import (
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

logger = logging.getLogger(__name__)

STAGE_ORDER = [
    CaseStageName.BOOTSTRAP,
    CaseStageName.RETRIEVE,
    CaseStageName.TRIAGE,
    CaseStageName.INVESTIGATE,
    CaseStageName.ARBITRATE,
    CaseStageName.REPORT,
]


@dataclass
class CaseRunContext:
    """Mutable state shared across a case run."""

    case: TopicCase
    run_started_at: datetime
    output_dir: Path
    bootstrap_result: dict[str, Any] | None = None
    fetch_result: dict[str, Any] | None = None
    selected_articles: list[CaseArticle] | None = None
    processed_events: list[dict[str, Any]] | None = None
    report_bundle: dict[str, Any] | None = None
    exception_queue: list[dict[str, Any]] | None = None
    changed: bool = False


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

        requested_index = STAGE_ORDER.index(start_stage)
        for stage in STAGE_ORDER[requested_index:]:
            if stage == CaseStageName.BOOTSTRAP:
                await self._stage_bootstrap(
                    context,
                    conflict=conflict,
                    confirmed_parties=confirmed_parties or [],
                    manual_links=manual_links or [],
                    automation_mode=automation_mode,
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

        return self._reload_case(context.case.id)

    async def rerun_case(
        self,
        case_id: str,
        *,
        start_stage: CaseStageName,
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
        finally:
            session.close()

        return await self.run_case(
            query=query,
            output_dir=output_dir,
            conflict=conflict,
            importance=importance,
            start_stage=start_stage,
            case_id=case_id,
            monitor_mode=(start_stage == CaseStageName.RETRIEVE),
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
        checkpoint.last_successful_run_at = _utcnow()
        checkpoint.metadata_json = {
            "new_article_count": new_article_count,
            "articles_processed": result.get("articles_processed", 0),
            "fetch_exceptions": len(result.get("fetch_exceptions", [])),
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

    def _persist_investigation_outputs(
        self, session, context: CaseRunContext, stage_run: CaseStageRun, result: dict[str, Any]
    ) -> list[str]:
        artifact_ids: list[str] = []
        for event in context.processed_events or []:
            store_event_in_db(
                event,
                case_id=context.case.id,
                case_run_id=stage_run.id,
                create_review=True,
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
                artifact_ids = persist_callback(session, context, stage_run, result)
                stage_run.status = StageStatus.COMPLETED
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
                case.status = status_after_success
                case.current_stage = stage_name
                case.latest_run_completed_at = _utcnow()
                case.updated_at = _utcnow()
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
                {"support": 0, "oppose": 0, "sources": set(), "party_positions": {}},
            )
            for link in links_by_claim.get(claim.id, []):
                evidence = evidence_by_id.get(link.evidence_id)
                publisher = (
                    evidence.publisher if evidence else None
                ) or (evidence.origin_url if evidence else None) or "unknown"
                bucket["sources"].add(publisher)
                if link.relation == "opposes":
                    bucket["oppose"] += 1
                else:
                    bucket["support"] += 1
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
        parties = (
            session.query(Party)
            .filter(Party.event_id.in_([event.id for event in events]))
            .all()
            if events
            else []
        )
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
                    }
                )
            claim_payload = {
                "id": claim.id,
                "event_id": claim.event_id,
                "claim_text": claim.claim_text,
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
