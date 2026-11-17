"""Backward-compatible topic fetcher exports.

This module provides the backward-compatible ``TopicFetcher`` facade over
``RelevanceFetcher`` together with the honest per-source acquisition records
(B02) that the relevance fetcher does not express on its own.

Acquisition honesty (B02): each source attempt produces a structured
:class:`SourceAcquisitionOutcome` (``success_with_items``, ``success_empty``,
``failed`` or ``skipped``) plus a coverage classification, so callers can tell a
healthy empty feed from a timeout, a malformed feed, a missing URL or a
manual/social seed that was never network-acquired.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.ai.prompts import get_prompt
from src.ingester.relevance_fetcher import RelevanceFetcher
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


class TopicFetcher(RelevanceFetcher):
    """Backward-compatible relevance fetcher that also reports acquisition honesty.

    Source loading, article retrieval and relevance scoring are inherited from
    :class:`RelevanceFetcher`; :meth:`_fetch_from_sources` and
    :meth:`fetch_articles_by_topic` are overridden so the honest per-source
    outcome records from B02 are attached without duplicating the fetch loop.
    """

    # Populated by ``_fetch_from_sources``; ``None`` means the caller supplied a
    # legacy result without structured outcomes, which must never be reported as
    # a complete acquisition.
    _last_source_outcomes: list[dict[str, Any]] | None = None
    _last_source_plan_total: int = 0

    async def fetch_articles_by_topic(
        self,
        query: str,
        conflict: str | None = None,
        max_articles: int = 50,
        relevance_threshold: float = 0.3,
        manual_links: list[str] | None = None,
        confirmed_parties: list[str] | None = None,
    ) -> dict:
        """Delegate to the relevance fetcher and add honest acquisition data.

        Articles, fetch exceptions and relevance scoring all come from
        :class:`RelevanceFetcher`; this override only attaches validated
        per-source outcome records plus coverage, so a caller can never mistake
        an unobserved or degraded run for a complete acquisition.
        """
        self._last_source_outcomes = None
        self._last_source_plan_total = 0
        result = await super().fetch_articles_by_topic(
            query,
            conflict=conflict,
            max_articles=max_articles,
            relevance_threshold=relevance_threshold,
            manual_links=manual_links,
            confirmed_parties=confirmed_parties,
        )

        outcomes = self._last_source_outcomes
        if outcomes is None:
            # The base class canonicalises ``source_outcomes`` from whatever the
            # fetch path returned (including a patched ``_fetch_from_sources``);
            # prefer those validated records over the legacy side channel.
            inherited = result.get("source_outcomes")
            if isinstance(inherited, list) and result.get("acquisition_observed") is True:
                outcomes = inherited
        requested_total = self._last_source_plan_total or 0
        if not requested_total:
            visible_plan = result.get("source_plan")
            requested_total = len(visible_plan) if isinstance(visible_plan, list) else 0
        result["source_plan_total"] = requested_total

        if outcomes is None:
            # A legacy/mock caller result without structured outcomes must not be
            # reported as complete, successful acquisition.
            legacy_counts = describe_source_outcomes(
                [], requested_count=requested_total
            )["counts"]
            fetched = result.get("articles_fetched")
            if isinstance(fetched, int) and not isinstance(fetched, bool):
                legacy_counts["articles"] = fetched
            result["source_outcomes"] = []
            result["acquisition_coverage"] = COVERAGE_UNKNOWN
            result["acquisition_counts"] = legacy_counts
            result["acquisition_observed"] = False
            result["sources_used"] = []
            return result

        summary = describe_source_outcomes(outcomes, requested_count=requested_total)
        result["source_outcomes"] = outcomes
        result["acquisition_coverage"] = summary["coverage"]
        result["acquisition_counts"] = summary["counts"]
        result["acquisition_observed"] = True
        # ``sources_used`` derives from validated status, never from a
        # self-declared ``succeeded`` flag.
        result["sources_used"] = [
            outcome["source_name"]
            for outcome in outcomes
            if validated_outcome_kind(outcome) in SUCCESS_ACQUISITION_STATUSES
        ]
        return result

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
        # Hand the honest observation to ``fetch_articles_by_topic`` without
        # re-deriving it (the relevance fetcher drops non-article keys).
        self._last_source_outcomes = serialized
        self._last_source_plan_total = len(sources)
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

    async def _score_relevance(
        self,
        article: dict,
        query: str,
    ) -> float:
        """Preserve the historical patch point for LLM scoring."""
        content = article.get("content", "")[:500]
        title = article.get("title", "")
        source = article.get("source", "")

        prompt = get_prompt(
            "RELEVANCE_SCORING",
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
            score = float(response.strip())
            return max(0.0, min(1.0, score))
        except Exception:
            return 0.5


__all__ = ["TopicFetcher", "RelevanceFetcher", "call_llm", "RSSFeed"]
