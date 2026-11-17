"""B02 regression tests: honest acquisition outcomes and checkpoints.

Covers the B02 contract without any live feed/provider call:

* structured RSS outcomes distinguish ``success_with_items``, ``success_empty``,
  timeouts/transport errors, non-success HTTP, malformed/bozo feeds (recovered
  entries stay usable but disclosed) and entirely unparseable entry sets;
* a cached/not-modified response can never masquerade as a fresh success;
* the legacy ``fetch() -> list`` contract still works for existing callers
  (including ``ContentFetcher``);
* topic-fetching records requested/attempted/success/failed/skipped counts with
  source identity, keeps manual/social sparse seeds as skipped context, treats
  missing URLs / unsupported strategies as validation failures and reports full
  coverage beyond the 20/10 display limits;
* legacy results with no structured outcomes are reported as ``unknown``;
* the case service only advances ``last_successful_run_at`` for a complete
  requested scope (including a genuine empty success), retains the prior
  success time for partial/failed/not-attempted/unknown observations, keeps
  already-acquired articles on partial runs, and fails the RETRIEVE stage/case
  (without running later stages) while durably retaining the diagnostics when
  every attempted acquisition failed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import feedparser
import pytest
from httpx import TimeoutException

from src.cases.service import TopicCaseService, retrieval_acquisition_observation
from src.ingester.fetcher import ContentFetcher
from src.ingester.rss import FeedAcquisitionOutcome, RSSFeed
from src.ingester.topic_fetcher import (
    TopicFetcher,
    describe_source_outcomes,
    validated_outcome_kind,
)
from src.storage import (
    CaseArtifact,
    CaseArticle,
    CaseStageName,
    CaseStageRun,
    CaseStatus,
    MonitorCheckpoint,
    StageStatus,
    TopicCase,
    init_database,
)

FEED_URL = "https://example.com/feed.xml"


def entry(title: str = "Test Article", link: str = "https://example.com/a") -> dict:
    return {
        "title": title,
        "link": link,
        "description": "Short description",
        "published_parsed": (2024, 3, 1, 12, 0, 0, 0, 0, 0),
        "author": "Test Author",
    }


def fake_feed(*, entries=(), bozo=False, status=200, bozo_exception=None,
              version="rss20"):
    return SimpleNamespace(
        entries=list(entries),
        bozo=bozo,
        status=status,
        bozo_exception=bozo_exception,
        version=version,
    )


class _UnparseableEntry:
    """Entry whose every field access raises, so ``_parse_entry`` returns None."""

    def get(self, *_args, **_kwargs):
        raise RuntimeError("unparseable entry")


# ---------------------------------------------------------------------------
# RSS acquisition outcomes
# ---------------------------------------------------------------------------


def _rss_outcome(feed, *, max_articles=10) -> FeedAcquisitionOutcome:
    with (
        patch("src.ingester.rss.feedparser.parse", return_value=feed),
        patch.object(RSSFeed, "_fetch_full_article", return_value=""),
    ):
        return RSSFeed(FEED_URL).fetch_with_outcome(max_articles=max_articles)


def test_rss_success_with_items_is_usable():
    outcome = _rss_outcome(fake_feed(entries=[entry()]))

    assert outcome.status == "success_with_items"
    assert outcome.attempted is True
    assert outcome.succeeded is True
    assert len(outcome.articles) == 1
    assert outcome.articles[0]["title"] == "Test Article"
    assert outcome.entries_seen == 1
    assert outcome.entries_parsed == 1


def test_rss_healthy_empty_feed_is_success_empty():
    outcome = _rss_outcome(fake_feed(entries=[]))

    assert outcome.status == "success_empty"
    assert outcome.succeeded is True
    assert outcome.articles == []
    assert outcome.bozo is False


def test_rss_timeout_is_failure_not_empty_success():
    with patch(
        "src.ingester.rss.feedparser.parse",
        side_effect=TimeoutException("timed out"),
    ):
        outcome = RSSFeed(FEED_URL).fetch_with_outcome()

    assert outcome.status == "failed"
    assert outcome.succeeded is False
    assert outcome.attempted is True
    assert outcome.reason == "timeout"
    assert outcome.articles == []


def test_rss_transport_error_is_failure():
    with patch(
        "src.ingester.rss.feedparser.parse",
        side_effect=RuntimeError("connection reset"),
    ):
        outcome = RSSFeed(FEED_URL).fetch_with_outcome()

    assert outcome.status == "failed"
    assert outcome.reason == "transport_error"
    assert "connection reset" in (outcome.error or "")


def test_rss_http_error_cannot_be_success_even_with_entries():
    outcome = _rss_outcome(fake_feed(entries=[entry()], status=500))

    assert outcome.status == "failed"
    assert outcome.reason == "http_500"
    assert outcome.http_status == 500
    assert outcome.articles == []
    assert outcome.succeeded is False


def test_rss_not_modified_cannot_fake_fresh_success():
    outcome = _rss_outcome(fake_feed(entries=[], status=304))

    assert outcome.status == "skipped"
    assert outcome.attempted is True
    assert outcome.succeeded is False
    assert outcome.reason == "http_not_modified"

    summary = describe_source_outcomes([outcome.to_dict()])
    assert summary["coverage"] != "complete_requested_scope"


def test_rss_bozo_with_recovered_entries_stays_usable_and_disclosed():
    outcome = _rss_outcome(
        fake_feed(
            entries=[entry()],
            bozo=True,
            bozo_exception=Exception("character encoding declared incorrectly"),
        )
    )

    assert outcome.status == "success_with_items"
    assert outcome.articles
    assert outcome.bozo is True
    assert outcome.warning and "encoding" in outcome.warning


def test_rss_bozo_empty_feed_is_failure_not_healthy_empty():
    outcome = _rss_outcome(
        fake_feed(entries=[], bozo=True, bozo_exception=Exception("syntax error"))
    )

    assert outcome.status == "failed"
    assert outcome.reason == "malformed_feed"
    assert outcome.succeeded is False
    assert outcome.warning


def test_rss_all_entries_unparseable_is_failure_not_healthy_empty():
    outcome = _rss_outcome(fake_feed(entries=[_UnparseableEntry()]))

    assert outcome.status == "failed"
    assert outcome.reason == "entries_unparseable"
    assert outcome.entries_seen == 1
    assert outcome.entries_parsed == 0
    assert outcome.succeeded is False


def test_rss_legacy_fetch_wrapper_returns_lists():
    with (
        patch("src.ingester.rss.feedparser.parse", return_value=fake_feed(entries=[entry()])),
        patch.object(RSSFeed, "_fetch_full_article", return_value=""),
    ):
        assert [a["title"] for a in RSSFeed(FEED_URL).fetch()] == ["Test Article"]

    with patch(
        "src.ingester.rss.feedparser.parse", side_effect=RuntimeError("boom")
    ):
        assert RSSFeed(FEED_URL).fetch() == []


def test_content_fetcher_remains_list_compatible_and_skips_failed_updates(tmp_path):
    init_database(str(tmp_path / "triangulate.db"))
    config = {"sources": {"rss": {"example": FEED_URL}}}
    fetcher = ContentFetcher(config)
    updates = MagicMock()
    fetcher._update_source = updates  # type: ignore[method-assign]

    with (
        patch("src.ingester.rss.feedparser.parse", return_value=fake_feed(entries=[entry()])),
        patch.object(RSSFeed, "_fetch_full_article", return_value=""),
    ):
        articles = fetcher.fetch_from_source("example", limit=5)
    assert isinstance(articles, list) and len(articles) == 1
    assert updates.call_count == 1

    updates.reset_mock()
    with patch(
        "src.ingester.rss.feedparser.parse", side_effect=RuntimeError("down")
    ):
        failed = fetcher.fetch_from_source("example", limit=5)
    assert failed == []
    # A failed RSS acquisition must not pretend the source was freshly fetched.
    assert updates.call_count == 0


# ---------------------------------------------------------------------------
# Topic-level acquisition outcomes and coverage
# ---------------------------------------------------------------------------


def _plan_source(name: str, url: str = FEED_URL, strategy: str = "rss") -> dict:
    return {
        "name": name,
        "url": url,
        "source_type": strategy,
        "party_affiliation": "",
        "language": "en",
        "credibility_tier": "unknown",
        "fetch_strategy": strategy,
        "queries": ["q"],
        "confirmed_parties": [],
        "relevance_score": 0.5,
    }


def _outcome_for(url: str, outcome: FeedAcquisitionOutcome) -> MagicMock:
    mocked = MagicMock()
    if url == "fail":
        mocked.fetch_with_outcome.return_value = FeedAcquisitionOutcome(
            source_url=url,
            status="failed",
            attempted=True,
            error="timeout",
            reason="timeout",
        )
    elif url == "empty":
        mocked.fetch_with_outcome.return_value = FeedAcquisitionOutcome(
            source_url=url, status="success_empty", attempted=True
        )
    else:
        mocked.fetch_with_outcome.return_value = outcome
    return mocked


@pytest.mark.asyncio
async def test_topic_partial_outcome_preserves_articles_and_counts():
    fetcher = TopicFetcher({"ai": {"model": "test"}})
    good = FeedAcquisitionOutcome(
        source_url=FEED_URL,
        status="success_with_items",
        articles=[
            {"title": "A", "link": "https://example.com/a", "content": "Body of article A"}
        ],
        attempted=True,
    )
    sources = [_plan_source("Good"), _plan_source("Bad", url="fail")]

    with patch("src.ingester.topic_fetcher.RSSFeed") as feed_cls:
        feed_cls.side_effect = lambda url: _outcome_for(url, good)
        result = await fetcher._fetch_from_sources(sources, 10)

    assert [a["title"] for a in result["articles"]] == ["A"]
    assert len(result["exceptions"]) == 1
    assert result["acquisition_coverage"] == "partial"
    counts = result["acquisition_counts"]
    assert counts["requested"] == 2
    assert counts["attempted"] == 2
    assert counts["succeeded"] == 1
    assert counts["success_with_items"] == 1
    assert counts["failed"] == 1
    outcomes = {o["source_name"]: o for o in result["source_outcomes"]}
    assert outcomes["Good"]["status"] == "success_with_items"
    assert outcomes["Good"]["source_url"] == FEED_URL
    assert outcomes["Bad"]["status"] == "failed"
    assert outcomes["Bad"]["reason"] == "timeout"


@pytest.mark.asyncio
async def test_topic_all_failed_has_no_sources_used():
    fetcher = TopicFetcher({"ai": {"model": "test"}})
    failed = MagicMock()
    failed.fetch_with_outcome.return_value = FeedAcquisitionOutcome(
        source_url=FEED_URL, status="failed", attempted=True, error="boom",
        reason="transport_error",
    )

    with patch("src.ingester.topic_fetcher.RSSFeed", return_value=failed):
        result = await fetcher._fetch_from_sources(
            [_plan_source("A"), _plan_source("B")], 10
        )

    assert result["articles"] == []
    assert result["acquisition_coverage"] == "failed"
    assert result["acquisition_counts"]["failed"] == 2
    assert len(result["exceptions"]) == 2


@pytest.mark.asyncio
async def test_topic_manual_and_social_seeds_are_skipped_context():
    fetcher = TopicFetcher({"ai": {"model": "test"}})
    plan = [
        _plan_source("Manual", url="https://manual.example/x", strategy="manual"),
        _plan_source("Social", url="https://social.example/y", strategy="social"),
    ]

    result = await fetcher._fetch_from_sources(plan, 10)

    assert len(result["articles"]) == 2
    assert result["exceptions"] == []
    assert result["acquisition_coverage"] == "not_attempted"
    counts = result["acquisition_counts"]
    assert counts["attempted"] == 0
    assert counts["skipped"] == 2
    assert counts["succeeded"] == 0
    assert all(o["status"] == "skipped" for o in result["source_outcomes"])
    assert all(o["attempted"] is False for o in result["source_outcomes"])


@pytest.mark.asyncio
async def test_topic_missing_url_and_unsupported_strategy_fail_validation():
    fetcher = TopicFetcher({"ai": {"model": "test"}})
    plan = [
        _plan_source("NoUrl", url="", strategy="rss"),
        _plan_source("NoManualUrl", url="", strategy="manual"),
        _plan_source("Web", url="https://example.com/w", strategy="web"),
    ]

    result = await fetcher._fetch_from_sources(plan, 10)

    assert result["articles"] == []
    assert len(result["exceptions"]) == 3
    outcomes = {o["source_name"]: o for o in result["source_outcomes"]}
    assert outcomes["NoUrl"]["status"] == "failed"
    assert outcomes["NoUrl"]["reason"] == "missing_url"
    assert outcomes["NoUrl"]["attempted"] is False
    assert outcomes["NoManualUrl"]["status"] == "failed"
    assert outcomes["Web"]["status"] == "failed"
    assert outcomes["Web"]["reason"] == "unsupported_strategy"
    assert result["acquisition_coverage"] == "failed"


@pytest.mark.asyncio
async def test_topic_full_coverage_beyond_display_truncation():
    fetcher = TopicFetcher({"ai": {"model": "test"}})
    sources = [_plan_source(f"Source {index}") for index in range(25)]
    empty_feed = MagicMock()
    empty_feed.fetch_with_outcome.return_value = FeedAcquisitionOutcome(
        source_url=FEED_URL, status="success_empty", attempted=True
    )

    fetcher._load_sources = lambda _conflict: sources  # type: ignore[method-assign]
    fetcher.analyzer.detect_conflict = AsyncMock(return_value="conflict")
    fetcher.analyzer.generate_search_queries = AsyncMock(return_value=["q"])
    fetcher.analyzer.prioritize_sources = AsyncMock(return_value=sources)
    fetcher._score_articles = AsyncMock(return_value=[])  # type: ignore[method-assign]

    with patch("src.ingester.topic_fetcher.RSSFeed", return_value=empty_feed):
        result = await fetcher.fetch_articles_by_topic(
            query="topic", conflict="conflict", max_articles=10
        )

    # Display truncation may remain ...
    assert len(result["source_plan"]) == 20
    assert result["source_plan_total"] == 25
    # ... but full outcome coverage and counts are retained.
    assert len(result["source_outcomes"]) == 25
    assert result["acquisition_coverage"] == "complete_requested_scope"
    assert result["acquisition_counts"]["succeeded"] == 25
    assert len(result["sources_used"]) == 25
    assert result["articles"] == []


@pytest.mark.asyncio
async def test_topic_no_sources_is_not_attempted():
    fetcher = TopicFetcher({"ai": {"model": "test"}})
    fetcher._load_sources = lambda _conflict: []  # type: ignore[method-assign]
    fetcher.analyzer.detect_conflict = AsyncMock(return_value="conflict")
    fetcher.analyzer.generate_search_queries = AsyncMock(return_value=["q"])
    fetcher.analyzer.prioritize_sources = AsyncMock(return_value=[])
    fetcher._score_articles = AsyncMock(return_value=[])  # type: ignore[method-assign]

    result = await fetcher.fetch_articles_by_topic(
        query="topic", conflict="conflict", max_articles=10
    )

    assert result["source_outcomes"] == []
    assert result["acquisition_coverage"] == "not_attempted"
    assert result["acquisition_counts"]["requested"] == 0
    assert result["sources_used"] == []
    assert any(
        exc["message"].startswith("No source pack available")
        for exc in result["fetch_exceptions"]
    )


@pytest.mark.asyncio
async def test_topic_legacy_fetch_result_is_unknown_not_success():
    fetcher = TopicFetcher({"ai": {"model": "test"}})
    fetcher._load_sources = lambda _conflict: [_plan_source("A")]  # type: ignore[method-assign]
    fetcher.analyzer.detect_conflict = AsyncMock(return_value="conflict")
    fetcher.analyzer.generate_search_queries = AsyncMock(return_value=["q"])
    fetcher.analyzer.prioritize_sources = AsyncMock(return_value=[_plan_source("A")])
    fetcher._score_articles = AsyncMock(return_value=[])  # type: ignore[method-assign]
    fetcher._fetch_from_sources = AsyncMock(  # type: ignore[method-assign]
        return_value={"articles": [], "exceptions": []}
    )

    result = await fetcher.fetch_articles_by_topic(
        query="topic", conflict="conflict", max_articles=10
    )

    assert result["acquisition_observed"] is False
    assert result["acquisition_coverage"] == "unknown"
    assert result["source_outcomes"] == []
    assert result["sources_used"] == []


def test_describe_source_outcomes_coverage_rules():
    def outcome(
        status,
        *,
        name="Example",
        url=FEED_URL,
        strategy="rss",
        attempted=True,
        articles=0,
        **extra,
    ):
        return {
            "source_name": name,
            "source_url": url,
            "fetch_strategy": strategy,
            "status": status,
            "attempted": attempted,
            "article_count": articles,
            **extra,
        }

    def summarized(outcomes, requested_count=None):
        return describe_source_outcomes(
            outcomes, requested_count=requested_count
        )["coverage"]

    assert summarized([]) == "not_attempted"
    assert (
        summarized(
            [
                outcome(
                    "skipped",
                    name="Seed",
                    url="https://manual.example/x",
                    strategy="manual",
                    attempted=False,
                    articles=1,
                )
            ]
        )
        == "not_attempted"
    )
    assert (
        summarized(
            [
                outcome("success_with_items", articles=1),
                outcome("success_empty", name="Second", url="https://example.com/feed2"),
            ]
        )
        == "complete_requested_scope"
    )
    assert (
        summarized(
            [
                outcome("success_empty"),
                outcome("failed", name="Bad", url="https://down.example/f"),
            ]
        )
        == "partial"
    )
    assert summarized([outcome("failed")]) == "failed"
    assert summarized([outcome("skipped", attempted=True)]) == "unknown"


# ---------------------------------------------------------------------------
# Case service: retrieval observation and checkpoints
# ---------------------------------------------------------------------------


ARTICLE = {
    "url": "https://example.com/a",
    "title": "Article A",
    "source": "Example",
    "published_at": "2026-03-08T12:00:00+00:00",
    "content": "Alpha and Beta disagree.",
    "relevance_score": 0.9,
}


def _fetch_payload(
    coverage: str, *, outcomes=None, articles=None, source_plan_total=None
) -> dict:
    """Build a TopicFetcher-shaped result from validated per-source outcomes.

    ``coverage`` is only the caller's *reported* claim (kept for readability of
    the call sites and as a reported field); the canonical
    ``acquisition_coverage``/counts/``sources_used`` are derived from the
    outcomes exactly like a real TopicFetcher payload, so these tests cannot
    pass an arbitrary coverage that the service should reject.
    """
    outcomes = outcomes or []
    requested = len(outcomes) if source_plan_total is None else source_plan_total
    summary = describe_source_outcomes(outcomes, requested_count=requested)
    return {
        "articles": list(articles if articles is not None else []),
        "conflict": "ukraine_war",
        "queries_generated": ["alpha"],
        "source_plan": [{"name": "Example"}],
        "source_plan_total": requested,
        "source_outcomes": outcomes,
        "acquisition_coverage": summary["coverage"],
        "acquisition_counts": summary["counts"],
        "acquisition_observed": True,
        "reported_coverage_claim": coverage,
        "sources_used": [
            o["source_name"]
            for o in outcomes
            if validated_outcome_kind(o) in {"success_with_items", "success_empty"}
        ],
        "articles_fetched": len(articles or []),
        "articles_processed": len(articles or []),
        "fetch_exceptions": [],
    }


SUCCESS_OUTCOME = {
    "source_name": "Example",
    "source_url": FEED_URL,
    "source_type": "rss",
    "fetch_strategy": "rss",
    "status": "success_with_items",
    "attempted": True,
    "article_count": 1,
    "error": None,
    "warning": None,
    "reason": None,
}
EMPTY_OUTCOME = {**SUCCESS_OUTCOME, "status": "success_empty", "article_count": 0}
FAILED_OUTCOME = {
    **SUCCESS_OUTCOME,
    "status": "failed",
    "article_count": 0,
    "error": "timeout",
    "reason": "timeout",
}


def _make_service(tmp_path) -> TopicCaseService:
    init_database(str(tmp_path / "triangulate.db"))
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
    return service


def _session(tmp_path):
    return init_database(str(tmp_path / "triangulate.db")).get_session_sync()


def _checkpoint(tmp_path, case_id: str):
    session = _session(tmp_path)
    try:
        return (
            session.query(MonitorCheckpoint)
            .filter(MonitorCheckpoint.case_id == case_id)
            .first()
        )
    finally:
        session.close()


async def _run_retrieve(service, *, case_id, payload):
    service.topic_fetcher.fetch_articles_by_topic = AsyncMock(return_value=payload)  # type: ignore[method-assign]
    return await service.run_case(
        query="Honest acquisition",
        output_dir=service.output_root,
        conflict="ukraine_war",
        start_stage=CaseStageName.RETRIEVE,
        case_id=case_id,
        automation_mode="blocked",
    )


@pytest.mark.asyncio
async def test_complete_empty_scope_advances_checkpoint(tmp_path):
    service = _make_service(tmp_path)
    case = await _run_retrieve(
        service,
        case_id=None,
        payload=_fetch_payload("complete_requested_scope", outcomes=[EMPTY_OUTCOME]),
    )

    assert case.status != CaseStatus.FAILED
    assert case.metadata_json["retrieval_coverage"] == "complete_requested_scope"
    checkpoint = _checkpoint(tmp_path, case.id)
    assert checkpoint is not None
    assert checkpoint.last_checked_at is not None
    assert checkpoint.last_successful_run_at is not None
    assert checkpoint.metadata_json["coverage"] == "complete_requested_scope"
    assert checkpoint.metadata_json["advanced_successful_checkpoint"] is True


@pytest.mark.asyncio
async def test_partial_keeps_articles_and_retains_prior_success(tmp_path):
    service = _make_service(tmp_path)
    first = await _run_retrieve(
        service,
        case_id=None,
        payload=_fetch_payload(
            "complete_requested_scope", outcomes=[SUCCESS_OUTCOME], articles=[ARTICLE]
        ),
    )
    prior_success = _checkpoint(tmp_path, first.id).last_successful_run_at
    assert prior_success is not None

    partial_article = {**ARTICLE, "url": "https://example.com/b", "title": "Article B"}
    second = await _run_retrieve(
        service,
        case_id=first.id,
        payload=_fetch_payload(
            "partial",
            outcomes=[SUCCESS_OUTCOME, FAILED_OUTCOME],
            articles=[partial_article],
        ),
    )

    checkpoint = _checkpoint(tmp_path, second.id)
    assert checkpoint.last_successful_run_at == prior_success
    assert checkpoint.metadata_json["coverage"] == "partial"
    assert checkpoint.metadata_json["advanced_successful_checkpoint"] is False
    assert second.metadata_json["retrieval_coverage"] == "partial"

    session = _session(tmp_path)
    try:
        urls = {
            row.url
            for row in session.query(CaseArticle)
            .filter(CaseArticle.case_id == second.id)
            .all()
        }
    finally:
        session.close()
    # Partial acquisition preserves already-acquired articles.
    assert {"https://example.com/a", "https://example.com/b"} <= urls


@pytest.mark.asyncio
async def test_all_failed_stops_pipeline_and_retains_diagnostics(tmp_path):
    service = _make_service(tmp_path)
    first = await _run_retrieve(
        service,
        case_id=None,
        payload=_fetch_payload(
            "complete_requested_scope", outcomes=[SUCCESS_OUTCOME], articles=[ARTICLE]
        ),
    )
    prior_success = _checkpoint(tmp_path, first.id).last_successful_run_at
    assert prior_success is not None

    failed = await _run_retrieve(
        service,
        case_id=first.id,
        payload=_fetch_payload("failed", outcomes=[FAILED_OUTCOME]),
    )

    assert failed.status == CaseStatus.FAILED
    assert failed.current_stage == CaseStageName.RETRIEVE

    session = _session(tmp_path)
    try:
        stage_names = [
            run.stage_name
            for run in session.query(CaseStageRun)
            .filter(CaseStageRun.case_id == failed.id)
            .all()
        ]
        # No later stage may run after a failed retrieval.
        assert CaseStageName.RETRIEVE in stage_names
        assert CaseStageName.TRIAGE not in stage_names
        assert CaseStageName.INVESTIGATE not in stage_names
        assert CaseStageName.REPORT not in stage_names

        retrieve_run = (
            session.query(CaseStageRun)
            .filter(
                CaseStageRun.case_id == failed.id,
                CaseStageRun.stage_name == CaseStageName.RETRIEVE,
            )
            .order_by(CaseStageRun.started_at.desc())
            .first()
        )
        assert retrieve_run.status == StageStatus.FAILED
        assert retrieve_run.error_message

        # Diagnostic artifacts survive the failure (not rolled back).
        artifact = (
            session.query(CaseArtifact)
            .filter(
                CaseArtifact.case_id == failed.id,
                CaseArtifact.artifact_type == "retrieval_result",
            )
            .order_by(CaseArtifact.created_at.desc())
            .first()
        )
        assert artifact is not None
        assert artifact.payload_json["acquisition_coverage"] == "failed"
        assert artifact.payload_json["source_outcomes"][0]["status"] == "failed"

        checkpoint = (
            session.query(MonitorCheckpoint)
            .filter(MonitorCheckpoint.case_id == failed.id)
            .first()
        )
        # Failure never advances the successful checkpoint time.
        assert checkpoint.last_successful_run_at == prior_success
        assert checkpoint.metadata_json["coverage"] == "failed"
        assert checkpoint.metadata_json["source_outcomes"][0]["status"] == "failed"
        assert checkpoint.metadata_json["advanced_successful_checkpoint"] is False
    finally:
        session.close()

    assert failed.metadata_json["retrieval_acquisition"]["coverage"] == "failed"
    assert failed.metadata_json["retrieval_acquisition"]["sources"][0]["status"] == "failed"


@pytest.mark.asyncio
async def test_not_attempted_and_unknown_retain_prior_success(tmp_path):
    service = _make_service(tmp_path)
    first = await _run_retrieve(
        service,
        case_id=None,
        payload=_fetch_payload(
            "complete_requested_scope", outcomes=[SUCCESS_OUTCOME], articles=[ARTICLE]
        ),
    )
    prior_success = _checkpoint(tmp_path, first.id).last_successful_run_at

    manual_seed_outcome = {
        **SUCCESS_OUTCOME,
        "source_name": "Manual",
        "source_url": "https://manual.example/source",
        "source_type": "manual",
        "fetch_strategy": "manual",
        "status": "skipped",
        "attempted": False,
        "reason": "manual_seed_not_network_acquired",
        "article_count": 1,
    }
    seed_article = {
        "url": "https://manual.example/source",
        "title": "Manual source: Manual",
        "source": "Manual",
        "source_type": "manual",
        "content": (
            "Manual source placeholder for Manual. "
            "Original URL: https://manual.example/source."
        ),
        "published_at": "2026-03-08T12:00:00+00:00",
        "relevance_score": 1.0,
    }
    seeded = await _run_retrieve(
        service,
        case_id=first.id,
        payload=_fetch_payload(
            "not_attempted", outcomes=[manual_seed_outcome], articles=[seed_article]
        ),
    )
    assert seeded.status != CaseStatus.FAILED  # seeds remain reviewable context
    checkpoint = _checkpoint(tmp_path, seeded.id)
    assert checkpoint.metadata_json["coverage"] == "not_attempted"
    assert checkpoint.last_successful_run_at == prior_success

    legacy_payload = {
        "articles": [ARTICLE],
        "conflict": "ukraine_war",
        "queries_generated": ["alpha"],
        "sources_used": ["Example"],
        "articles_fetched": 1,
        "articles_processed": 1,
    }
    legacy = await _run_retrieve(service, case_id=first.id, payload=legacy_payload)
    assert legacy.metadata_json["retrieval_coverage"] == "unknown"
    assert legacy.metadata_json["retrieval_acquisition"]["observed"] is False
    checkpoint = _checkpoint(tmp_path, legacy.id)
    assert checkpoint.last_successful_run_at == prior_success
    assert checkpoint.metadata_json["coverage"] == "unknown"
    assert checkpoint.metadata_json["advanced_successful_checkpoint"] is False


@pytest.mark.asyncio
async def test_topic_derived_result_advances_checkpoint_end_to_end(tmp_path, monkeypatch):
    """A genuine (mocked) TopicFetcher result flows through to the checkpoint."""
    service = _make_service(tmp_path)
    fetcher = service.topic_fetcher
    fetcher._load_sources = lambda _conflict: [_plan_source("Example")]  # type: ignore[method-assign]
    fetcher.analyzer.detect_conflict = AsyncMock(return_value="ukraine_war")
    fetcher.analyzer.generate_search_queries = AsyncMock(return_value=["alpha"])
    fetcher.analyzer.prioritize_sources = AsyncMock(
        return_value=[_plan_source("Example")]
    )
    fetcher._score_articles = AsyncMock(side_effect=lambda articles, *_a, **_k: list(articles))  # type: ignore[method-assign]

    good_feed = MagicMock()
    good_feed.fetch_with_outcome.return_value = FeedAcquisitionOutcome(
        source_url=FEED_URL,
        status="success_with_items",
        attempted=True,
        articles=[
            {
                "title": "Article A",
                "link": "https://example.com/a",
                "content": "Alpha and Beta disagree.",
                "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC).isoformat(),
            }
        ],
    )

    with patch("src.ingester.topic_fetcher.RSSFeed", return_value=good_feed):
        case = await service.run_case(
            query="End to end acquisition",
            output_dir=tmp_path,
            conflict="ukraine_war",
            start_stage=CaseStageName.RETRIEVE,
            automation_mode="blocked",
        )

    assert case.metadata_json["retrieval_coverage"] == "complete_requested_scope"
    assert case.metadata_json["sources_used"] == ["Example"]
    assert case.source_count == 1
    checkpoint = _checkpoint(tmp_path, case.id)
    assert checkpoint.last_successful_run_at is not None
    assert checkpoint.metadata_json["counts"]["success_with_items"] == 1

    session = _session(tmp_path)
    try:
        stored = session.query(TopicCase).filter(TopicCase.id == case.id).first()
        assert stored.article_count == 1
    finally:
        session.close()


# ---------------------------------------------------------------------------
# B02 correction regressions (reviewer-identified gaps)
# ---------------------------------------------------------------------------


def test_real_parser_requires_recognised_feed_evidence():
    """Non-feed bodies are not healthy-empty feeds; real empty RSS/Atom are."""
    classifier = RSSFeed("memory://feed")
    empty_rss = (
        b'<?xml version="1.0"?><rss version="2.0"><channel>'
        b"<title>Empty feed</title><link>https://example.com</link>"
        b"<description>No items yet</description></channel></rss>"
    )
    empty_atom = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<feed xmlns="http://www.w3.org/2005/Atom">'
        b"<title>Empty atom</title><id>urn:example:1</id>"
        b"<updated>2026-01-01T00:00:00Z</updated></feed>"
    )

    rss_outcome = classifier._classify_feed(feedparser.parse(empty_rss), 10)
    atom_outcome = classifier._classify_feed(feedparser.parse(empty_atom), 10)
    assert rss_outcome.status == "success_empty"
    assert (rss_outcome.feed_version or "").startswith("rss")
    assert atom_outcome.status == "success_empty"
    assert (atom_outcome.feed_version or "").startswith("atom")

    for payload in (
        b"",
        b"<message>maintenance window</message>",
        b"<html><body><h1>Service unavailable</h1></body></html>",
    ):
        outcome = classifier._classify_feed(feedparser.parse(payload), 10)
        assert outcome.status == "failed", payload
        assert outcome.reason in {"unrecognized_feed", "malformed_feed"}
        assert outcome.succeeded is False


def test_bozo_recovered_and_mixed_parse_are_degraded_partial():
    classifier = RSSFeed(FEED_URL)
    recovered = classifier._classify_feed(
        fake_feed(entries=[entry()], bozo=True, bozo_exception=Exception("bad encoding")),
        10,
    )
    assert recovered.status == "success_with_items"
    assert recovered.degraded is True
    assert recovered.warning

    mixed = classifier._classify_feed(fake_feed(entries=[entry(), _UnparseableEntry()]), 10)
    assert mixed.status == "success_with_items"
    assert mixed.parse_failures == 1
    assert mixed.degraded is True
    assert mixed.warning

    summary = describe_source_outcomes([mixed.to_dict()])
    assert summary["coverage"] == "partial"
    assert summary["counts"]["degraded"] == 1


def test_bounded_entry_limit_is_not_degradation():
    entries = [
        entry(title=f"Article {i}", link=f"https://example.com/{i}") for i in range(5)
    ]
    with (
        patch("src.ingester.rss.feedparser.parse", return_value=fake_feed(entries=entries)),
        patch.object(RSSFeed, "_fetch_full_article", return_value=""),
    ):
        outcome = RSSFeed(FEED_URL).fetch_with_outcome(max_articles=2)

    assert outcome.status == "success_with_items"
    assert outcome.entries_considered == 2
    assert outcome.parse_failures == 0
    assert outcome.degraded is False
    assert (
        describe_source_outcomes([outcome.to_dict()])["coverage"]
        == "complete_requested_scope"
    )


@pytest.mark.asyncio
async def test_degraded_recovery_retains_prior_success(tmp_path):
    service = _make_service(tmp_path)
    first = await _run_retrieve(
        service,
        case_id=None,
        payload=_fetch_payload(
            "complete_requested_scope", outcomes=[SUCCESS_OUTCOME], articles=[ARTICLE]
        ),
    )
    prior = _checkpoint(tmp_path, first.id).last_successful_run_at
    assert prior is not None

    degraded_outcome = {
        **SUCCESS_OUTCOME,
        "degraded": True,
        "warning": "1 of 2 selected feed entries could not be parsed",
        "parse_failures": 1,
    }
    second = await _run_retrieve(
        service,
        case_id=first.id,
        payload=_fetch_payload(
            "complete_requested_scope", outcomes=[degraded_outcome], articles=[ARTICLE]
        ),
    )

    assert second.metadata_json["retrieval_coverage"] == "partial"
    # Articles from a degraded recovery stay usable and attributed.
    assert second.metadata_json["sources_used"] == ["Example"]
    assert second.metadata_json["retrieval_acquisition"]["counts"]["degraded"] == 1
    checkpoint = _checkpoint(tmp_path, second.id)
    assert checkpoint.metadata_json["coverage"] == "partial"
    assert checkpoint.metadata_json["advanced_successful_checkpoint"] is False
    assert checkpoint.last_successful_run_at == prior


def test_forged_summary_cannot_upgrade_observation():
    forged = {
        "source_outcomes": [dict(FAILED_OUTCOME)],
        "acquisition_observed": True,
        "acquisition_coverage": "complete_requested_scope",
        "acquisition_counts": {"requested": 1, "succeeded": 99, "failed": 0},
    }
    observation = retrieval_acquisition_observation(forged)
    assert observation["coverage"] == "failed"
    assert observation["counts"]["succeeded"] == 0
    assert observation["counts"]["failed"] == 1

    partial_forged = {
        "source_outcomes": [dict(SUCCESS_OUTCOME), dict(FAILED_OUTCOME)],
        "acquisition_observed": True,
        "acquisition_coverage": "complete_requested_scope",
        "acquisition_counts": {"requested": 2, "succeeded": 2, "failed": 0},
    }
    assert retrieval_acquisition_observation(partial_forged)["coverage"] == "partial"

    # Legacy/unobserved output stays unknown, even with an empty outcome list.
    legacy_empty = {"source_outcomes": [], "acquisition_observed": False}
    assert retrieval_acquisition_observation(legacy_empty)["coverage"] == "unknown"
    assert retrieval_acquisition_observation(legacy_empty)["observed"] is False
    assert retrieval_acquisition_observation({"articles": []})["coverage"] == "unknown"


@pytest.mark.asyncio
async def test_forged_summary_persisted_surfaces_are_canonical(tmp_path):
    service = _make_service(tmp_path)
    forged_payload = {
        "articles": [ARTICLE],
        "conflict": "ukraine_war",
        "queries_generated": ["alpha"],
        "source_plan": [{"name": "Example"}],
        "source_outcomes": [dict(FAILED_OUTCOME)],
        "acquisition_observed": True,
        "acquisition_coverage": "complete_requested_scope",
        "acquisition_counts": {"requested": 1, "succeeded": 99, "failed": 0},
        "sources_used": ["Forged source"],
        "articles_fetched": 1,
        "articles_processed": 1,
        "fetch_exceptions": [],
    }

    case = await _run_retrieve(service, case_id=None, payload=forged_payload)

    assert case.status == CaseStatus.FAILED
    assert case.metadata_json["retrieval_coverage"] == "failed"
    assert case.metadata_json["retrieval_stage_failure"]["reason"] == "all_sources_failed"
    assert case.metadata_json["sources_used"] == []

    session = _session(tmp_path)
    try:
        artifact = (
            session.query(CaseArtifact)
            .filter(
                CaseArtifact.case_id == case.id,
                CaseArtifact.artifact_type == "retrieval_result",
            )
            .order_by(CaseArtifact.created_at.desc())
            .first()
        )
        assert artifact.payload_json["acquisition_coverage"] == "failed"
        assert artifact.payload_json["acquisition_counts"]["succeeded"] == 0
        assert artifact.payload_json["sources_used"] == []
        assert (
            artifact.payload_json["reported_acquisition_summary"]["coverage"]
            == "complete_requested_scope"
        )
        assert artifact.payload_json["reported_acquisition_summary"]["trusted"] is False
        assert artifact.payload_json["reported_sources_used"] == ["Forged source"]

        retrieve_run = (
            session.query(CaseStageRun)
            .filter(
                CaseStageRun.case_id == case.id,
                CaseStageRun.stage_name == CaseStageName.RETRIEVE,
            )
            .order_by(CaseStageRun.started_at.desc())
            .first()
        )
        # Stage metrics are built from the same canonicalized result.
        assert retrieve_run.metrics_json["acquisition_coverage"] == "failed"

        checkpoint = (
            session.query(MonitorCheckpoint)
            .filter(MonitorCheckpoint.case_id == case.id)
            .first()
        )
        assert checkpoint.metadata_json["coverage"] == "failed"
        assert checkpoint.metadata_json["fatal_reason"] == "all_sources_failed"
        assert checkpoint.last_successful_run_at is None
    finally:
        session.close()


@pytest.mark.asyncio
async def test_empty_catalog_autonomous_retrieval_fails_and_stops(tmp_path):
    service = _make_service(tmp_path)
    service.topic_fetcher.fetch_articles_by_topic = AsyncMock(
        return_value=_fetch_payload("not_attempted", outcomes=[])
    )

    case = await service.run_case(
        query="Empty catalog",
        output_dir=tmp_path,
        conflict="ukraine_war",
        start_stage=CaseStageName.RETRIEVE,
        automation_mode="autonomous",
    )

    assert case.status == CaseStatus.FAILED
    assert case.current_stage == CaseStageName.RETRIEVE
    assert case.metadata_json["retrieval_coverage"] == "not_attempted"
    assert case.metadata_json["retrieval_stage_failure"]["reason"] == "no_source_acquisition"

    session = _session(tmp_path)
    try:
        stage_names = {
            run.stage_name
            for run in session.query(CaseStageRun)
            .filter(CaseStageRun.case_id == case.id)
            .all()
        }
        assert CaseStageName.RETRIEVE in stage_names
        assert CaseStageName.TRIAGE not in stage_names
        assert CaseStageName.INVESTIGATE not in stage_names
        assert CaseStageName.REPORT not in stage_names

        checkpoint = (
            session.query(MonitorCheckpoint)
            .filter(MonitorCheckpoint.case_id == case.id)
            .first()
        )
        assert checkpoint.metadata_json["coverage"] == "not_attempted"
        assert checkpoint.metadata_json["fatal_reason"] == "no_source_acquisition"
        assert checkpoint.last_successful_run_at is None
    finally:
        session.close()


@pytest.mark.asyncio
async def test_legacy_topic_result_stays_unknown_through_service(tmp_path):
    fetcher = TopicFetcher({"ai": {"model": "test"}})
    fetcher._load_sources = lambda _conflict: [_plan_source("A")]  # type: ignore[method-assign]
    fetcher.analyzer.detect_conflict = AsyncMock(return_value="conflict")
    fetcher.analyzer.generate_search_queries = AsyncMock(return_value=["q"])
    fetcher.analyzer.prioritize_sources = AsyncMock(return_value=[_plan_source("A")])
    fetcher._score_articles = AsyncMock(return_value=[])  # type: ignore[method-assign]
    fetcher._fetch_from_sources = AsyncMock(  # type: ignore[method-assign]
        return_value={"articles": [], "exceptions": []}
    )

    result = await fetcher.fetch_articles_by_topic(
        query="topic", conflict="conflict", max_articles=10
    )
    assert result["acquisition_observed"] is False
    assert result["acquisition_coverage"] == "unknown"

    service = _make_service(tmp_path)
    service.topic_fetcher.fetch_articles_by_topic = AsyncMock(return_value=result)
    case = await service.run_case(
        query="Legacy unknown",
        output_dir=tmp_path,
        conflict="ukraine_war",
        start_stage=CaseStageName.RETRIEVE,
        automation_mode="blocked",
    )

    assert case.status != CaseStatus.FAILED
    assert case.metadata_json["retrieval_coverage"] == "unknown"
    assert case.metadata_json["retrieval_acquisition"]["observed"] is False
    assert _checkpoint(tmp_path, case.id).last_successful_run_at is None


def test_contradictory_outcomes_never_yield_complete():
    forged_success = {
        "source_name": "X",
        "status": "success_with_items",
        "attempted": "false",
        "article_count": 1,
        "succeeded": True,
    }
    contradictory_empty = {
        "source_name": "Y",
        "status": "success_empty",
        "attempted": True,
        "article_count": 3,
    }
    unknown_status = {
        "source_name": "Z",
        "status": "maybe",
        "attempted": True,
        "article_count": 1,
    }
    for outcome in (forged_success, contradictory_empty, unknown_status):
        summary = describe_source_outcomes([outcome])
        assert summary["coverage"] != "complete_requested_scope"
        assert summary["counts"]["invalid"] == 1
        assert summary["counts"]["succeeded"] == 0
        assert validated_outcome_kind(outcome) is None

    healthy = dict(SUCCESS_OUTCOME)
    for outcome in (forged_success, contradictory_empty, unknown_status):
        summary = describe_source_outcomes([healthy, outcome])
        assert summary["coverage"] == "partial"

    # A self-declared ``succeeded: true`` on a failed outcome is ignored.
    assert validated_outcome_kind({**FAILED_OUTCOME, "succeeded": True}) == "failed"

    # Healthy RSS plus a reviewable (never attempted) seed is partial.
    seed = {
        **SUCCESS_OUTCOME,
        "source_name": "Seed",
        "status": "skipped",
        "attempted": False,
        "article_count": 1,
        "succeeded": False,
    }
    assert describe_source_outcomes([healthy, seed])["coverage"] == "partial"


@pytest.mark.asyncio
async def test_sources_used_ignores_self_declared_success():
    fetcher = TopicFetcher({"ai": {"model": "test"}})
    fetcher._load_sources = lambda _conflict: [_plan_source("Bad")]  # type: ignore[method-assign]
    fetcher.analyzer.detect_conflict = AsyncMock(return_value="conflict")
    fetcher.analyzer.generate_search_queries = AsyncMock(return_value=["q"])
    fetcher.analyzer.prioritize_sources = AsyncMock(return_value=[_plan_source("Bad")])
    fetcher._score_articles = AsyncMock(return_value=[])  # type: ignore[method-assign]
    forged = {
        "source_name": "Bad",
        "source_url": FEED_URL,
        "source_type": "rss",
        "fetch_strategy": "rss",
        "status": "failed",
        "attempted": True,
        "article_count": 0,
        "succeeded": True,
    }
    fetcher._fetch_from_sources = AsyncMock(  # type: ignore[method-assign]
        return_value={"articles": [], "exceptions": [], "source_outcomes": [forged]}
    )

    result = await fetcher.fetch_articles_by_topic(
        query="topic", conflict="conflict", max_articles=10
    )

    assert result["sources_used"] == []
    assert result["acquisition_coverage"] == "failed"


@pytest.mark.asyncio
async def test_fabricated_rss_skip_is_not_usable_seed(tmp_path):
    service = _make_service(tmp_path)
    fabricated = {
        **SUCCESS_OUTCOME,
        "status": "skipped",
        "attempted": False,
        "reason": "rss_seed_not_network_acquired",
        "article_count": 1,
    }

    case = await _run_retrieve(
        service, case_id=None, payload=_fetch_payload("not_attempted", outcomes=[fabricated])
    )

    assert case.status == CaseStatus.FAILED
    assert case.current_stage == CaseStageName.RETRIEVE
    assert case.metadata_json["retrieval_stage_failure"]["reason"] == "no_source_acquisition"
    session = _session(tmp_path)
    try:
        stage_names = {
            run.stage_name
            for run in session.query(CaseStageRun)
            .filter(CaseStageRun.case_id == case.id)
            .all()
        }
        assert CaseStageName.TRIAGE not in stage_names
        checkpoint = (
            session.query(MonitorCheckpoint)
            .filter(MonitorCheckpoint.case_id == case.id)
            .first()
        )
        assert checkpoint.last_successful_run_at is None
        assert checkpoint.metadata_json["coverage"] == "not_attempted"
    finally:
        session.close()


@pytest.mark.asyncio
async def test_manual_skip_without_matching_article_is_fatal(tmp_path):
    service = _make_service(tmp_path)
    manual = {
        **SUCCESS_OUTCOME,
        "source_name": "Manual",
        "source_url": "https://manual.example/x",
        "source_type": "manual",
        "fetch_strategy": "manual",
        "status": "skipped",
        "attempted": False,
        "article_count": 1,
    }

    case = await _run_retrieve(
        service, case_id=None, payload=_fetch_payload("not_attempted", outcomes=[manual])
    )

    assert case.status == CaseStatus.FAILED
    assert case.metadata_json["retrieval_stage_failure"]["reason"] == "no_source_acquisition"


def test_known_requested_count_reconciliation():
    success = dict(SUCCESS_OUTCOME)

    assert (
        describe_source_outcomes([success], requested_count=2)["coverage"]
        == "partial"
    )
    assert (
        describe_source_outcomes([success], requested_count=1)["coverage"]
        == "complete_requested_scope"
    )

    # Anonymous success records cannot complete requested coverage.
    anonymous = {"status": "success_with_items", "attempted": True, "article_count": 1}
    assert validated_outcome_kind(anonymous) is None
    assert describe_source_outcomes([anonymous])["coverage"] == "unknown"

    # Duplicate identities cannot complete (and are not double counted).
    duplicate_summary = describe_source_outcomes(
        [success, dict(success)], requested_count=2
    )
    assert duplicate_summary["coverage"] == "partial"
    assert duplicate_summary["counts"]["duplicates"] == 1
    assert duplicate_summary["counts"]["succeeded"] == 1

    # A missing-URL failure remains a valid failure.
    assert validated_outcome_kind({**FAILED_OUTCOME, "source_url": ""}) == "failed"

    # Trusted attempts on rejected records are still counted.
    rejected = {
        "source_name": "X",
        "source_url": "",
        "status": "success_with_items",
        "attempted": True,
        "article_count": 1,
    }
    rejected_summary = describe_source_outcomes([rejected])
    assert rejected_summary["counts"]["attempted"] == 1
    assert rejected_summary["counts"]["invalid"] == 1


@pytest.mark.asyncio
async def test_inconsistent_degradation_diagnostics_cannot_complete(tmp_path):
    inconsistent = {**SUCCESS_OUTCOME, "degraded": False, "parse_failures": 1}
    summary = describe_source_outcomes([inconsistent], requested_count=1)
    assert summary["coverage"] == "partial"
    assert summary["counts"]["degraded"] == 1

    warning_only = {**SUCCESS_OUTCOME, "warning": "recovered parse warning"}
    assert (
        describe_source_outcomes([warning_only], requested_count=1)["coverage"]
        == "partial"
    )
    bozo_only = {**SUCCESS_OUTCOME, "bozo": True}
    assert describe_source_outcomes([bozo_only], requested_count=1)["coverage"] == "partial"

    service = _make_service(tmp_path)
    first = await _run_retrieve(
        service,
        case_id=None,
        payload=_fetch_payload(
            "complete_requested_scope", outcomes=[SUCCESS_OUTCOME], articles=[ARTICLE]
        ),
    )
    prior = _checkpoint(tmp_path, first.id).last_successful_run_at
    assert prior is not None

    second = await _run_retrieve(
        service,
        case_id=first.id,
        payload=_fetch_payload(
            "complete_requested_scope", outcomes=[inconsistent], articles=[ARTICLE]
        ),
    )
    checkpoint = _checkpoint(tmp_path, second.id)
    assert second.metadata_json["retrieval_coverage"] == "partial"
    assert checkpoint.metadata_json["advanced_successful_checkpoint"] is False
    assert checkpoint.last_successful_run_at == prior


def test_legacy_fetch_wrapper_survives_malformed_parser_results():
    from src.ingester.rss import _coerce_http_status

    assert _coerce_http_status("²") is None

    weird_feed = SimpleNamespace(
        entries=[], bozo=False, status="²", version="rss20"
    )
    with patch("src.ingester.rss.feedparser.parse", return_value=weird_feed):
        outcome = RSSFeed(FEED_URL).fetch_with_outcome()
        assert outcome.http_status is None
        assert outcome.status in {"success_empty", "failed"}
        assert RSSFeed(FEED_URL).fetch() == []

    # A failure while classifying a malformed parser result is contained and
    # reported as a parse failure; the legacy list wrapper stays non-throwing.
    with (
        patch("src.ingester.rss.feedparser.parse", return_value=fake_feed()),
        patch.object(
            RSSFeed, "_classify_feed", side_effect=RuntimeError("bad parser result")
        ),
    ):
        outcome = RSSFeed(FEED_URL).fetch_with_outcome()
        assert outcome.status == "failed"
        assert outcome.reason == "parse_error"
        assert RSSFeed(FEED_URL).fetch() == []


def test_missing_or_unsupported_strategy_cannot_complete():
    missing = {
        "source_name": "NoStrategy",
        "source_url": FEED_URL,
        "status": "success_with_items",
        "attempted": True,
        "article_count": 1,
    }
    unsupported = {**missing, "source_name": "Web", "fetch_strategy": "web"}
    non_string = {**missing, "source_name": "Odd", "fetch_strategy": 42}
    healthy = dict(SUCCESS_OUTCOME)

    for record in (missing, unsupported, non_string):
        assert validated_outcome_kind(record) is None
        assert (
            describe_source_outcomes([record], requested_count=1)["coverage"]
            != "complete_requested_scope"
        )
        assert (
            describe_source_outcomes([healthy, record], requested_count=2)["coverage"]
            == "partial"
        )

    # Failure records stay valid failures without a success strategy identity.
    assert validated_outcome_kind({**FAILED_OUTCOME, "fetch_strategy": ""}) == "failed"
    assert validated_outcome_kind({**FAILED_OUTCOME, "fetch_strategy": "web"}) == "failed"


def test_direct_rss_outcome_dict_carries_supported_strategy():
    with patch.object(RSSFeed, "_fetch_full_article", return_value=""):
        payload = RSSFeed(FEED_URL)._classify_feed(
            fake_feed(entries=[entry()]), 10
        ).to_dict()

    assert payload["source_type"] == "rss"
    assert payload["fetch_strategy"] == "rss"
    assert validated_outcome_kind(payload) == "success_with_items"
    assert (
        describe_source_outcomes([payload], requested_count=1)["coverage"]
        == "complete_requested_scope"
    )


def test_requested_hint_never_shrinks_below_visible_plan():
    payload = _fetch_payload(
        "complete_requested_scope",
        outcomes=[SUCCESS_OUTCOME],
        articles=[ARTICLE],
        source_plan_total=1,
    )
    payload["source_plan"] = [{"name": "One"}, {"name": "Two"}]

    observation = retrieval_acquisition_observation(payload)

    assert observation["counts"]["requested"] == 2
    assert observation["counts"]["succeeded"] == 1
    assert observation["coverage"] == "partial"
