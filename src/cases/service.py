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

from src.ai.workflow import AIWorkflow
from src.ai.workflows.party_investigation_workflow import (
    create_party_investigation_workflow,
)
from src.exporter import JSONExporter, MarkdownExporter
from src.ingester.topic_fetcher import TopicFetcher
from src.storage import (
    CaseArtifact,
    CaseArticle,
    CaseStageName,
    CaseStageRun,
    CaseStatus,
    Event,
    MonitorCheckpoint,
    Review,
    ReviewStatus,
    StageStatus,
    TopicCase,
    get_database,
)
from src.storage.event_store import store_event_in_db

logger = logging.getLogger(__name__)

STAGE_ORDER = [
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
    fetch_result: dict[str, Any] | None = None
    selected_articles: list[CaseArticle] | None = None
    processed_events: list[dict[str, Any]] | None = None
    report_bundle: dict[str, Any] | None = None
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

            stage_runs = (
                session.query(CaseStageRun)
                .filter(CaseStageRun.case_id == case_id)
                .order_by(CaseStageRun.started_at.asc())
                .all()
            )
            articles = (
                session.query(CaseArticle)
                .filter(CaseArticle.case_id == case_id)
                .order_by(CaseArticle.relevance_score.desc())
                .all()
            )
            events = (
                session.query(Event)
                .filter(Event.case_id == case_id)
                .order_by(Event.timestamp.desc())
                .all()
            )
            artifacts = (
                session.query(CaseArtifact)
                .filter(CaseArtifact.case_id == case_id)
                .order_by(CaseArtifact.created_at.desc())
                .all()
            )

            return {
                "case": case,
                "stage_runs": stage_runs,
                "articles": articles,
                "events": events,
                "artifacts": artifacts,
            }
        finally:
            session.close()

    async def run_case(
        self,
        *,
        query: str,
        output_dir: Path | None = None,
        conflict: str | None = None,
        max_articles: int = 50,
        relevance_threshold: float = 0.3,
        importance: str | None = None,
        monitor_mode: bool = False,
        start_stage: CaseStageName = CaseStageName.RETRIEVE,
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

        requested_index = STAGE_ORDER.index(start_stage)
        for stage in STAGE_ORDER[requested_index:]:
            if stage == CaseStageName.RETRIEVE:
                await self._stage_retrieve(
                    context,
                    conflict=conflict,
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
                case.status = CaseStatus.APPROVED
                target_status = ReviewStatus.APPROVED
            elif normalized == "reject":
                case.status = CaseStatus.REJECTED
                target_status = ReviewStatus.REJECTED
            else:
                case.status = CaseStatus.REVIEW_READY
                target_status = None

            if target_status is not None:
                for review in reviews:
                    review.status = target_status
                    review.reviewed_at = _utcnow()

            case.last_reviewed_at = _utcnow()
            case.review_notes = notes
            case.open_review_items = sum(
                1 for review in reviews if review.status == ReviewStatus.PENDING
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
                max_articles=topic.get("max_articles", 20),
                relevance_threshold=topic.get("relevance_threshold", 0.3),
                importance=topic.get("importance"),
                output_dir=output_root or self.output_root,
                monitor_mode=True,
            )
            completed_cases.append(case)
        return completed_cases

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
                current_stage=CaseStageName.RETRIEVE,
                metadata_json={"history": []},
            )
            session.add(case)
        else:
            case.query = query
            case.conflict = conflict or case.conflict
            case.importance = importance or case.importance
            case.status = CaseStatus.MONITORING if monitor_mode else CaseStatus.DISCOVERING
            case.current_stage = CaseStageName.RETRIEVE

        case.latest_run_started_at = _utcnow()
        return case

    def _reload_case(self, case_id: str) -> TopicCase:
        session = get_database().get_session_sync()
        try:
            return session.query(TopicCase).filter(TopicCase.id == case_id).first()
        finally:
            session.close()

    async def _stage_retrieve(
        self,
        context: CaseRunContext,
        *,
        conflict: str | None,
        max_articles: int,
        relevance_threshold: float,
        monitor_mode: bool,
    ) -> None:
        async def runner() -> dict[str, Any]:
            result = await self.topic_fetcher.fetch_articles_by_topic(
                query=context.case.query,
                conflict=conflict or context.case.conflict,
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

        session.flush()
        context.changed = new_article_count > 0
        case = session.query(TopicCase).filter(TopicCase.id == context.case.id).first()
        article_count = (
            session.query(CaseArticle).filter(CaseArticle.case_id == context.case.id).count()
        )
        metadata_json = {
            **(context.case.metadata_json or {}),
            "queries_generated": result.get("queries_generated", []),
            "sources_used": result.get("sources_used", []),
            "articles_fetched": result.get("articles_fetched", 0),
            "articles_processed": result.get("articles_processed", 0),
            "last_retrieved_at": _utcnow().isoformat(),
            "last_retrieve_changed": context.changed,
        }
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
        }
        return artifact_ids

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
            for article in context.selected_articles or []:
                event = await self._process_case_article(context.case, article)
                processed_events.append(event)
                route_counts[event["workflow_route"]] += 1

            context.processed_events = processed_events
            return {
                "event_ids": [event["id"] for event in processed_events],
                "event_count": len(processed_events),
                "route_counts": route_counts,
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
        article = dict(case_article.raw_payload or {})
        article_data = {
            "title": article.get("title", case_article.title),
            "content": article.get("content", case_article.content or ""),
            "timestamp": _parse_timestamp(article.get("published_at")),
            "link": article.get("url", case_article.url),
            "source_name": article.get("source", case_article.source or ""),
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
        merged = {
            **baseline,
            "claims": normalized_claims or baseline.get("claims", []),
            "parties": party_state.get("parties", {}).get("parties", baseline.get("parties", [])),
            "party_investigations": party_state.get("party_investigations", []),
            "event_summary": summary,
        }
        if summary.get("verification_distribution"):
            distribution = summary["verification_distribution"]
            for status in ["CONTESTED", "PROBABLE", "CONFIRMED", "ALLEGED", "DEBUNKED"]:
                if distribution.get(status):
                    merged["verification_status"] = status
                    break
        return merged

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
        event_count = len(context.processed_events or [])
        case = session.query(TopicCase).filter(TopicCase.id == context.case.id).first()
        case.event_count = event_count
        context.case.event_count = event_count
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
            result = {
                "event_count": len(events),
                "contested_event_ids": contested,
                "review_count": len(reviews),
                "changed": context.changed,
                "monitor_mode": monitor_mode,
            }
            context.case.open_review_items = sum(
                1 for review in reviews if review.status == ReviewStatus.PENDING
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
                case_articles = (
                    session.query(CaseArticle)
                    .filter(CaseArticle.case_id == context.case.id)
                    .order_by(CaseArticle.relevance_score.desc())
                    .all()
                )
                events = (
                    session.query(Event)
                    .filter(Event.case_id == context.case.id)
                    .order_by(Event.timestamp.asc())
                    .all()
                )
                stage_runs = (
                    session.query(CaseStageRun)
                    .filter(CaseStageRun.case_id == context.case.id)
                    .order_by(CaseStageRun.started_at.asc())
                    .all()
                )
            finally:
                session.close()

            articles_payload = []
            for article in case_articles:
                article_payload = dict(article.raw_payload or {})
                article_payload["claims"] = []
                articles_payload.append(article_payload)

            timeline = [
                {
                    "date": event.timestamp.isoformat() if event.timestamp else "",
                    "title": event.title,
                    "description": event.summary,
                    "status": event.verification_status.value,
                }
                for event in events
            ]

            metadata = {
                "topic": context.case.query,
                "conflict": context.case.conflict,
                "queried_at": _utcnow().isoformat(),
                "sources_used": (context.case.metadata_json or {}).get("sources_used", []),
                "articles_fetched": (context.case.metadata_json or {}).get("articles_fetched", 0),
                "articles_processed": len(case_articles),
                "queries_generated": (context.case.metadata_json or {}).get(
                    "queries_generated", []
                ),
                "case_id": context.case.id,
                "status": context.case.status.value,
            }
            results = {
                "articles": articles_payload,
                "narratives": [],
                "parties": [],
                "timeline": timeline,
                "executive_summary": self._build_executive_summary(events),
            }
            manifest = {
                "case_id": context.case.id,
                "status": context.case.status.value,
                "current_stage": context.case.current_stage.value
                if context.case.current_stage
                else None,
                "stage_runs": [
                    {
                        "stage": run.stage_name.value,
                        "status": run.status.value,
                        "started_at": run.started_at.isoformat()
                        if run.started_at
                        else None,
                        "completed_at": run.completed_at.isoformat()
                        if run.completed_at
                        else None,
                        "duration_ms": run.duration_ms,
                        "workflow_name": run.workflow_name,
                        "model_used": run.model_used,
                        "retry_count": run.retry_count,
                        "fallback_count": run.fallback_count,
                        "parse_failure_count": run.parse_failure_count,
                        "confidence_score": run.confidence_score,
                        "controversy_score": run.controversy_score,
                        "error_message": run.error_message,
                    }
                    for run in stage_runs
                ],
            }
            context.report_bundle = {
                "metadata": metadata,
                "results": results,
                "manifest": manifest,
            }
            return {
                "article_count": len(case_articles),
                "event_count": len(events),
                "report_ready": True,
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
                stage_run.metrics_json = result
                stage_run.confidence_score = self._derive_confidence(result)
                stage_run.controversy_score = self._derive_controversy(result)
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
