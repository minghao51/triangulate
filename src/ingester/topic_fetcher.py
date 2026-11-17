"""Topic-based article fetcher with AI relevance scoring.

This module fetches articles relevant to a specific topic from RSS feeds,
using AI to score and filter by relevance.

Acquisition honesty (B02): each source attempt produces a structured
:class:`SourceAcquisitionOutcome` (``success_with_items``, ``success_empty``,
``failed`` or ``skipped``) plus a coverage classification, so callers can tell a
healthy empty feed from a timeout, a malformed feed, a missing URL or a
manual/social seed that was never network-acquired.
"""

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from src.ai.topic_analyzer import TopicAnalyzer
from src.ai.utils import call_llm
from src.ingester.rss import (
    SUCCESS_ACQUISITION_STATUSES,
    AcquisitionStatus,
    FeedAcquisitionOutcome,
    RSSFeed,
)

COVERAGE_COMPLETE = "complete_requested_scope"
COVERAGE_PARTIAL = "partial"
COVERAGE_FAILED = "failed"
COVERAGE_NOT_ATTEMPTED = "not_attempted"
COVERAGE_UNKNOWN = "unknown"
COVERAGE_VALUES = frozenset(
    {
        COVERAGE_COMPLETE,
        COVERAGE_PARTIAL,
        COVERAGE_FAILED,
        COVERAGE_NOT_ATTEMPTED,
        COVERAGE_UNKNOWN,
    }
)


def coerce_attempted(value: Any) -> bool | None:
    """Normalise an ``attempted`` flag; ``None`` means not trustworthy."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no", ""}:
            return False
    return None


def coerce_flag(value: Any) -> bool:
    """Best-effort boolean for diagnostics such as ``degraded``."""
    return coerce_attempted(value) is True


def _coerce_article_count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


VALID_STATUS_VALUES = frozenset(
    {
        AcquisitionStatus.SUCCESS_WITH_ITEMS.value,
        AcquisitionStatus.SUCCESS_EMPTY.value,
        AcquisitionStatus.FAILED.value,
        AcquisitionStatus.SKIPPED.value,
    }
)


def _outcome_identity(outcome: dict[str, Any]) -> tuple[str, str, str] | None:
    """Return ``(name, url, strategy)`` source identity, or ``None``.

    A success requires a real, supported acquisition strategy (``rss``,
    ``manual`` or ``social``); a missing, non-string or unsupported strategy is
    anonymous, not a success identity. Missing-URL/unsupported-strategy
    *failures* are validated without this requirement.
    """
    name = outcome.get("source_name") or outcome.get("name")
    url = outcome.get("source_url") or outcome.get("url")
    strategy = outcome.get("fetch_strategy") or outcome.get("source_type")
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(url, str) or not url.strip():
        return None
    if not isinstance(strategy, str):
        return None
    normalized_strategy = strategy.strip().lower()
    if normalized_strategy not in {"rss", "manual", "social"}:
        return None
    return (name.strip(), url.strip(), normalized_strategy)


def _positive_int(value: Any) -> bool:
    """True only for a positive integer (or numeric string) diagnostic."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value > 0
    if isinstance(value, str):
        try:
            return int(value) > 0
        except (TypeError, ValueError):
            return False
    return False


def validated_outcome_kind(outcome: dict[str, Any]) -> str | None:
    """Return a trustworthy status for a serialized outcome, else ``None``.

    This is the single authority used for coverage/counts and for
    ``sources_used``: a self-declared ``succeeded: true`` is ignored, and
    contradictory records (unknown status, missing/invalid ``attempted``, a
    success that was never attempted, ``success_empty`` carrying articles or
    ``success_with_items`` with no articles) are rejected instead of being
    counted as network success. A success must also carry a meaningful source
    identity (non-empty name and URL), while a missing-URL failure remains a
    valid failure.
    """
    status = outcome.get("status")
    if status not in VALID_STATUS_VALUES:
        return None
    attempted = coerce_attempted(outcome.get("attempted"))
    if attempted is None:
        return None
    article_count = _coerce_article_count(outcome.get("article_count"))
    if article_count is None:
        return None
    if status == AcquisitionStatus.SUCCESS_WITH_ITEMS.value:
        if article_count <= 0 or not attempted:
            return None
    elif status == AcquisitionStatus.SUCCESS_EMPTY.value:
        if article_count != 0 or not attempted:
            return None
    if status in SUCCESS_ACQUISITION_STATUSES and _outcome_identity(outcome) is None:
        return None
    return status


def describe_source_outcomes(
    outcomes: list[dict[str, Any]], *, requested_count: int | None = None
) -> dict[str, Any]:
    """Summarize serialized source outcomes into counts plus coverage.

    Coverage is derived only from validated per-source outcomes (see
    :func:`validated_outcome_kind`); a caller-supplied top-level coverage or
    ``succeeded`` flag can never upgrade a degraded observation.

    ``requested_count`` is the known number of requested sources (the full
    source plan). It is reconciled against the observed records, so missing or
    duplicated records can never be reported as complete coverage. Counts and
    coverage from caller summaries remain untrusted.

    Coverage rules:

    * nothing requested and nothing observed -> ``not_attempted``;
    * no success and no attempt/failure (only never-attempted seed/skip records)
      -> ``not_attempted``; rejected records without attempts -> ``unknown``;
    * no success with a failure -> ``failed`` (attempts without failure ->
      ``unknown``, for example a cached 304);
    * some success with any failure, skip (including a manual/social seed),
      invalid/duplicate record, unaccounted requested source or degraded parse
      recovery -> ``partial``;
    * every requested source uniquely, cleanly and completely acquired ->
      ``complete_requested_scope``.
    """
    observed = len(outcomes)
    known_requested = (
        requested_count
        if isinstance(requested_count, int)
        and not isinstance(requested_count, bool)
        and requested_count > 0
        else 0
    )
    counts = {
        "requested": max(observed, known_requested),
        "observed": observed,
        "unaccounted": max(0, known_requested - observed),
        "attempted": 0,
        "succeeded": 0,
        "success_with_items": 0,
        "success_empty": 0,
        "failed": 0,
        "skipped": 0,
        "attempted_skipped": 0,
        "invalid": 0,
        "duplicates": 0,
        "degraded": 0,
        "warnings": 0,
        "articles": 0,
    }
    seen_identities: set[tuple[str, str, str]] = set()
    for outcome in outcomes:
        # A trusted, typed attempt flag is counted even for records rejected
        # below, so real attempts are never hidden by invalidity.
        attempted = coerce_attempted(outcome.get("attempted"))
        if attempted:
            counts["attempted"] += 1
        if outcome.get("warning"):
            counts["warnings"] += 1
        status = validated_outcome_kind(outcome)
        if status is None:
            counts["invalid"] += 1
            continue
        identity = _outcome_identity(outcome)
        if identity is not None:
            if identity in seen_identities:
                counts["duplicates"] += 1
                continue
            seen_identities.add(identity)
        counts["articles"] += _coerce_article_count(outcome.get("article_count")) or 0
        # Conservative degradation: a positive parse-failure count, bozo
        # evidence, a warning or an explicit degraded flag downgrades a success
        # even when the record otherwise looks consistent.
        if (
            coerce_flag(outcome.get("degraded"))
            or _positive_int(outcome.get("parse_failures"))
            or coerce_flag(outcome.get("bozo"))
            or bool(outcome.get("warning"))
        ):
            counts["degraded"] += 1
        if status == AcquisitionStatus.SUCCESS_WITH_ITEMS.value:
            counts["success_with_items"] += 1
            counts["succeeded"] += 1
        elif status == AcquisitionStatus.SUCCESS_EMPTY.value:
            counts["success_empty"] += 1
            counts["succeeded"] += 1
        elif status == AcquisitionStatus.FAILED.value:
            counts["failed"] += 1
        elif status == AcquisitionStatus.SKIPPED.value:
            counts["skipped"] += 1
            if attempted:
                counts["attempted_skipped"] += 1

    effective_requested = counts["requested"]
    if effective_requested == 0:
        coverage = COVERAGE_NOT_ATTEMPTED
    elif counts["succeeded"] == 0:
        if counts["failed"]:
            coverage = COVERAGE_FAILED
        elif counts["attempted"] or counts["invalid"] or counts["duplicates"]:
            coverage = COVERAGE_UNKNOWN
        else:
            # Only never-attempted seed/skip records: reviewable context.
            coverage = COVERAGE_NOT_ATTEMPTED
    elif (
        counts["failed"]
        or counts["skipped"]
        or counts["invalid"]
        or counts["duplicates"]
        or counts["degraded"]
        or counts["unaccounted"]
        or counts["succeeded"] < effective_requested
    ):
        coverage = COVERAGE_PARTIAL
    else:
        coverage = COVERAGE_COMPLETE

    return {"coverage": coverage, "counts": counts}


@dataclass
class SourceAcquisitionOutcome:
    """Structured acquisition outcome for one planned source."""

    source_name: str
    source_url: str
    source_type: str
    fetch_strategy: str
    status: str
    attempted: bool
    article_count: int = 0
    error: str | None = None
    warning: str | None = None
    reason: str | None = None
    degraded: bool = False
    parse_failures: int = 0

    @property
    def succeeded(self) -> bool:
        return self.status in SUCCESS_ACQUISITION_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "fetch_strategy": self.fetch_strategy,
            "status": self.status,
            "attempted": self.attempted,
            "succeeded": self.succeeded,
            "article_count": self.article_count,
            "error": self.error,
            "warning": self.warning,
            "reason": self.reason,
            "degraded": self.degraded,
            "parse_failures": self.parse_failures,
        }


# Relevance scoring prompt
RELEVANCE_SCORING_PROMPT = """
You are an expert in content relevance analysis. Given a topic and an article,
score how relevant the article is to the topic on a scale of 0.0 to 1.0.

Topic: {topic}

Article:
Title: {title}
Source: {source}
Content Preview: {content}

Scoring criteria:
- 0.9-1.0: Highly relevant - directly about the topic
- 0.7-0.9: Very relevant - closely related to the topic
- 0.5-0.7: Moderately relevant - tangentially related
- 0.3-0.5: Somewhat relevant - mentions the topic but not focus
- 0.0-0.3: Not relevant - barely mentions or unrelated

Return ONLY a number between 0.0 and 1.0.
"""


class TopicFetcher:
    """Fetch articles relevant to a topic using AI guidance."""

    def __init__(self, config: dict):
        """Initialize topic fetcher.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.analyzer = TopicAnalyzer(config)
        self.data_dir = Path("data/source")

    async def fetch_articles_by_topic(
        self,
        query: str,
        conflict: Optional[str] = None,
        max_articles: int = 50,
        relevance_threshold: float = 0.3,
        manual_links: Optional[list[str]] = None,
        confirmed_parties: Optional[list[str]] = None,
    ) -> dict:
        """Fetch articles relevant to the topic.

        Args:
            query: User's topic query
            conflict: Conflict context (auto-detected if None)
            max_articles: Maximum number of articles to fetch
            relevance_threshold: Minimum relevance score (0-1)

        Returns:
            Dictionary with fetched articles and metadata
        """
        # Detect conflict if not provided
        if conflict is None:
            conflict = await self.analyzer.detect_conflict(query)

        # Generate search queries
        search_queries = await self.analyzer.generate_search_queries(query, conflict)

        # Load sources for this conflict
        sources = self._load_sources(conflict)
        fetch_exceptions: list[dict[str, Any]] = []
        if not sources:
            fetch_exceptions.append(
                {
                    "type": "source_fetch_failure",
                    "message": f"No source pack available for conflict '{conflict}'.",
                    "severity": "high",
                    "details": {"conflict": conflict},
                }
            )

        # Prioritize sources
        prioritized_sources = await self.analyzer.prioritize_sources(
            query,
            conflict,
            sources,
        )

        # Fetch articles from RSS feeds
        source_plan = self._build_source_plan(
            prioritized_sources,
            search_queries=search_queries,
            confirmed_parties=confirmed_parties or [],
        )

        for link in manual_links or []:
            source_plan.append(
                {
                    "name": urlparse(link).netloc.replace("www.", "") or "manual",
                    "url": link,
                    "source_type": "manual",
                    "party_affiliation": "",
                    "language": "",
                    "credibility_tier": "user_supplied",
                    "fetch_strategy": "manual",
                    "queries": search_queries[:5],
                    "confirmed_parties": confirmed_parties or [],
                    "relevance_score": 1.0,
                }
            )

        fetched = await self._fetch_from_sources(
            source_plan,
            max_articles * 2,  # Fetch more to account for filtering
        )
        outcomes: list[dict[str, Any]] | None
        if isinstance(fetched, list):
            articles = fetched
            outcomes = None
        else:
            articles = fetched["articles"]
            fetch_exceptions.extend(fetched["exceptions"])
            raw_outcomes = fetched.get("source_outcomes")
            outcomes = (
                [dict(outcome) for outcome in raw_outcomes]
                if raw_outcomes is not None
                else None
            )

        if outcomes is None:
            # A legacy/mock caller result without structured outcomes must not be
            # reported as complete, successful acquisition.
            legacy_counts = describe_source_outcomes(
                [], requested_count=len(source_plan)
            )["counts"]
            legacy_counts["articles"] = len(articles)
            acquisition = {
                "coverage": COVERAGE_UNKNOWN,
                "counts": legacy_counts,
                "observed": False,
            }
            sources_used: list[str] = []
        else:
            acquisition = describe_source_outcomes(
                outcomes, requested_count=len(source_plan)
            )
            acquisition["observed"] = True
            # ``sources_used`` derives from validated status + attempt, never
            # from a self-declared ``succeeded`` flag.
            sources_used = [
                outcome["source_name"]
                for outcome in outcomes
                if validated_outcome_kind(outcome) in SUCCESS_ACQUISITION_STATUSES
            ]

        # Score articles by relevance
        scored_articles = await self._score_articles(
            articles,
            query,
            relevance_threshold,
        )

        # Sort by relevance and limit
        scored_articles.sort(key=lambda a: a.get("relevance_score", 0), reverse=True)
        final_articles = scored_articles[:max_articles]

        return {
            "articles": final_articles,
            "conflict": conflict,
            "queries_generated": search_queries,
            # Display truncation only; the full outcome set below keeps coverage.
            "source_plan": source_plan[:20],
            "source_plan_total": len(source_plan),
            "source_outcomes": outcomes or [],
            "acquisition_coverage": acquisition["coverage"],
            "acquisition_counts": acquisition["counts"],
            "acquisition_observed": acquisition["observed"],
            "sources_used": sources_used,
            "articles_fetched": len(articles),
            "articles_processed": len(final_articles),
            "confirmed_parties": confirmed_parties or [],
            "manual_links": manual_links or [],
            "fetch_exceptions": fetch_exceptions,
        }

    def _load_sources(self, conflict: str) -> list[dict]:
        """Load media sources for a conflict.

        Args:
            conflict: Conflict folder name

        Returns:
            List of source dictionaries
        """
        conflict_dir = self.data_dir / conflict

        if not conflict_dir.exists():
            print(f"Warning: Conflict directory not found: {conflict_dir}")
            return []

        # Find sources CSV file
        csv_files = list(conflict_dir.glob("*.csv"))
        if not csv_files:
            print(f"Warning: No CSV file found in {conflict_dir}")
            return []

        csv_file = csv_files[0]

        sources = []
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sources.append({
                    "name": row.get("name", row.get("source", "")),
                    "url": row.get("url", row.get("rss", "")),
                    "country": row.get("country", ""),
                    "language": row.get("language", ""),
                    "affiliation": row.get(
                        "affiliation", row.get("party_affiliation", "")
                    ),
                    "source_type": row.get("source_type", "rss"),
                    "credibility_tier": row.get("credibility_tier", "unknown"),
                    "fetch_strategy": row.get("fetch_strategy", "rss"),
                    "perspective": row.get("perspective", ""),
                })

        return sources

    def _build_source_plan(
        self,
        sources: list[dict],
        *,
        search_queries: list[str],
        confirmed_parties: list[str],
    ) -> list[dict]:
        """Build a source-plan that preserves acquisition intent."""
        plan = []
        for source in sources:
            plan.append(
                {
                    "name": source.get("name", ""),
                    "url": source.get("url", ""),
                    "source_type": source.get("source_type", "rss"),
                    "party_affiliation": source.get("affiliation", ""),
                    "language": source.get("language", ""),
                    "credibility_tier": source.get("credibility_tier", "unknown"),
                    "fetch_strategy": source.get("fetch_strategy", "rss"),
                    "queries": search_queries[:5],
                    "confirmed_parties": confirmed_parties,
                    "relevance_score": source.get("relevance_score", 0.0),
                }
            )
        return plan

    async def _fetch_from_sources(
        self,
        sources: list[dict],
        max_per_source: int,
    ) -> dict[str, Any]:
        """Fetch articles using the source plan and record honest outcomes.

        Args:
            sources: Prioritized list of sources
            max_per_source: Max articles to fetch per source

        Returns:
            ``articles``/``exceptions`` (legacy keys) plus ``source_outcomes``,
            ``acquisition_coverage`` and ``acquisition_counts``.
        """
        articles: list[dict[str, Any]] = []
        exceptions: list[dict[str, Any]] = []
        outcomes: list[SourceAcquisitionOutcome] = []

        for source in sources:
            strategy = source.get("fetch_strategy", source.get("source_type", "rss"))
            source_name = source.get("name", "unknown")
            source_url = source.get("url") or ""

            if strategy in {"manual", "social"}:
                if source_url:
                    # A sparse seed is useful context, never a network acquisition.
                    articles.append(self._build_sparse_article(source, source_url, strategy))
                    outcomes.append(
                        self._build_source_outcome(
                            source,
                            status=AcquisitionStatus.SKIPPED.value,
                            attempted=False,
                            article_count=1,
                            reason=f"{strategy}_seed_not_network_acquired",
                        )
                    )
                else:
                    exceptions.append(
                        self._build_fetch_exception(
                            source,
                            "source_fetch_failure",
                            (
                                "Manual link source is missing a URL."
                                if strategy == "manual"
                                else "Social source is missing a URL."
                            ),
                        )
                    )
                    outcomes.append(
                        self._build_source_outcome(
                            source,
                            status=AcquisitionStatus.FAILED.value,
                            attempted=False,
                            reason="missing_url",
                            error=f"{strategy} source is missing a URL.",
                        )
                    )
                continue

            if strategy == "rss":
                if not source_url:
                    exceptions.append(
                        self._build_fetch_exception(
                            source,
                            "source_fetch_failure",
                            "RSS source is missing a feed URL.",
                        )
                    )
                    outcomes.append(
                        self._build_source_outcome(
                            source,
                            status=AcquisitionStatus.FAILED.value,
                            attempted=False,
                            reason="missing_url",
                            error="RSS source is missing a feed URL.",
                        )
                    )
                    continue
                outcome, feed_articles = self._acquire_rss_source(
                    source, source_url, max_per_source
                )
                outcomes.append(outcome)
                articles.extend(feed_articles)
                if outcome.status == AcquisitionStatus.FAILED.value:
                    print(
                        f"Warning: Failed to fetch from {source_name}: "
                        f"{outcome.error or outcome.reason}"
                    )
                    exceptions.append(
                        self._build_fetch_exception(
                            source,
                            "source_fetch_failure",
                            f"Failed to fetch RSS source '{source_name}'.",
                            details={
                                "error": outcome.error,
                                "reason": outcome.reason,
                            },
                        )
                    )
                continue

            exceptions.append(
                self._build_fetch_exception(
                    source,
                    "source_fetch_failure",
                    f"Unsupported fetch strategy '{strategy}' for source '{source_name}'.",
                )
            )
            outcomes.append(
                self._build_source_outcome(
                    source,
                    status=AcquisitionStatus.FAILED.value,
                    attempted=False,
                    reason="unsupported_strategy",
                    error=f"Unsupported fetch strategy '{strategy}'.",
                )
            )

        serialized = [outcome.to_dict() for outcome in outcomes]
        summary = describe_source_outcomes(serialized, requested_count=len(sources))
        return {
            "articles": articles,
            "exceptions": exceptions,
            "source_outcomes": serialized,
            "acquisition_coverage": summary["coverage"],
            "acquisition_counts": summary["counts"],
        }

    def _build_source_outcome(
        self,
        source: dict[str, Any],
        *,
        status: str,
        attempted: bool,
        article_count: int = 0,
        reason: str | None = None,
        error: str | None = None,
        warning: str | None = None,
        degraded: bool = False,
        parse_failures: int = 0,
    ) -> SourceAcquisitionOutcome:
        return SourceAcquisitionOutcome(
            source_name=source.get("name") or source.get("url") or "unknown",
            source_url=source.get("url") or "",
            source_type=source.get("source_type", "rss"),
            fetch_strategy=source.get("fetch_strategy", source.get("source_type", "rss")),
            status=status,
            attempted=attempted,
            article_count=article_count,
            reason=reason,
            error=error,
            warning=warning,
            degraded=degraded,
            parse_failures=parse_failures,
        )

    def _acquire_rss_source(
        self,
        source: dict[str, Any],
        source_url: str,
        max_per_source: int,
    ) -> tuple[SourceAcquisitionOutcome, list[dict[str, Any]]]:
        """Acquire one RSS source and translate its outcome into article dicts."""
        try:
            feed = RSSFeed(source_url)
            feed_outcome = feed.fetch_with_outcome(max_articles=max_per_source)
            if not isinstance(feed_outcome, FeedAcquisitionOutcome):
                raise TypeError(
                    "RSSFeed.fetch_with_outcome did not return a FeedAcquisitionOutcome"
                )
        except Exception as exc:
            return (
                self._build_source_outcome(
                    source,
                    status=AcquisitionStatus.FAILED.value,
                    attempted=True,
                    reason="fetch_exception",
                    error=str(exc),
                ),
                [],
            )

        if feed_outcome.status == AcquisitionStatus.FAILED.value:
            return (
                self._build_source_outcome(
                    source,
                    status=AcquisitionStatus.FAILED.value,
                    attempted=True,
                    reason=feed_outcome.reason,
                    error=feed_outcome.error,
                    warning=feed_outcome.warning,
                    degraded=feed_outcome.degraded,
                    parse_failures=feed_outcome.parse_failures,
                ),
                [],
            )

        if feed_outcome.status == AcquisitionStatus.SKIPPED.value:
            return (
                self._build_source_outcome(
                    source,
                    status=AcquisitionStatus.SKIPPED.value,
                    attempted=feed_outcome.attempted,
                    reason=feed_outcome.reason,
                    warning=feed_outcome.warning,
                    degraded=feed_outcome.degraded,
                    parse_failures=feed_outcome.parse_failures,
                ),
                [],
            )

        feed_articles = [
            self._build_rss_article(source, article)
            for article in feed_outcome.articles
        ]
        return (
            self._build_source_outcome(
                source,
                status=feed_outcome.status,
                attempted=True,
                article_count=len(feed_articles),
                reason=feed_outcome.reason,
                warning=feed_outcome.warning,
                degraded=feed_outcome.degraded,
                parse_failures=feed_outcome.parse_failures,
            ),
            feed_articles,
        )

    def _build_rss_article(
        self, source: dict[str, Any], article: dict[str, Any]
    ) -> dict[str, Any]:
        strategy = source.get("fetch_strategy", source.get("source_type", "rss"))
        return {
            "title": article.get("title", ""),
            "url": article.get("link", ""),
            "content": article.get("content", ""),
            "published_at": article.get("timestamp", datetime.now().isoformat()),
            "source": source.get("name", article.get("source_name", "")),
            "source_type": source.get("source_type", "rss"),
            "source_metadata": {
                "party_affiliation": source.get("party_affiliation")
                or source.get("affiliation", ""),
                "credibility_tier": source.get("credibility_tier", "unknown"),
                "fetch_strategy": strategy,
                "queries": source.get("queries", []),
                "confirmed_parties": source.get("confirmed_parties", []),
                "source_plan_score": source.get("relevance_score", 0.0),
            },
        }

    def _build_sparse_article(
        self, source: dict[str, Any], url: str, source_type: str
    ) -> dict[str, Any]:
        source_name = source.get("name") or urlparse(url).netloc.replace("www.", "") or source_type
        content = (
            f"{source_type.title()} source placeholder for {source_name}. "
            f"Original URL: {url}. Queries: {', '.join(source.get('queries', [])[:3])}"
        )
        return {
            "title": f"{source_type.title()} source: {source_name}",
            "url": url,
            "content": content,
            "published_at": datetime.now().isoformat(),
            "source": source_name,
            "source_type": source_type,
            "source_metadata": {
                "submitted_via": "source_plan",
                "credibility_tier": source.get("credibility_tier", "unknown"),
                "fetch_strategy": source.get("fetch_strategy", source_type),
                "queries": source.get("queries", []),
                "confirmed_parties": source.get("confirmed_parties", []),
                "source_plan_score": source.get("relevance_score", 0.0),
            },
        }

    def _build_fetch_exception(
        self,
        source: dict[str, Any],
        exception_type: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": exception_type,
            "message": message,
            "severity": "high",
            "details": {
                "source_name": source.get("name"),
                "source_type": source.get("source_type"),
                "fetch_strategy": source.get("fetch_strategy"),
                **(details or {}),
            },
        }

    async def _score_articles(
        self,
        articles: list[dict],
        query: str,
        threshold: float,
    ) -> list[dict]:
        """Score articles by relevance to topic.

        Args:
            articles: List of article dictionaries
            query: Topic query
            threshold: Minimum relevance score

        Returns:
            Filtered and scored articles
        """
        scored_articles = []

        for article in articles:
            # Score relevance
            score = await self._score_relevance(article, query)

            # Filter by threshold
            if score >= threshold:
                article["relevance_score"] = score
                scored_articles.append(article)

        return scored_articles

    async def _score_relevance(
        self,
        article: dict,
        query: str,
    ) -> float:
        """Score article's relevance to topic.

        Args:
            article: Article dictionary
            query: Topic query

        Returns:
            Relevance score 0.0-1.0
        """
        # Get content preview (first 500 chars)
        content = article.get("content", "")[:500]
        title = article.get("title", "")
        source = article.get("source", "")

        prompt = RELEVANCE_SCORING_PROMPT.format(
            topic=query,
            title=title,
            source=source,
            content=content,
        )

        try:
            response = await call_llm(
                prompt=prompt,
                response_format="text",
                config=self.config.get("ai", {}),
            )

            # Parse score
            score = float(response.strip())
            return max(0.0, min(1.0, score))  # Clamp to 0-1

        except Exception:
            # Default to moderate score on error
            return 0.5
