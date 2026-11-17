"""Relevance-based article fetcher with AI relevance scoring.

This module fetches articles relevant to a specific topic from RSS feeds,
using AI to score and filter by relevance.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from src.ai.prompts import get_prompt
from src.ai.topic_analyzer import TopicAnalyzer
from src.ai.utils import call_llm
from src.ingester.rss import RSSFeed


class RelevanceFetcher:
    """Fetch articles relevant to a topic using AI guidance."""

    def __init__(self, config: dict):
        """Initialize relevance fetcher.

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
        raw_outcomes = None
        if isinstance(fetched, list):
            articles = fetched
        else:
            articles = fetched["articles"]
            fetch_exceptions.extend(fetched["exceptions"])
            raw_outcomes = fetched.get("source_outcomes")

        # B02: acquisition coverage/sources are derived only from validated
        # per-source outcomes (never from a caller-declared ``succeeded`` flag).
        # Imported lazily because ``TopicFetcher`` subclasses this class.
        from src.ingester.topic_fetcher import (
            COVERAGE_UNKNOWN,
            SUCCESS_ACQUISITION_STATUSES,
            describe_source_outcomes,
            validated_outcome_kind,
        )

        requested_hint = len(source_plan)
        if raw_outcomes is None:
            acquisition_sources: list[dict] = []
            coverage = COVERAGE_UNKNOWN
            counts = describe_source_outcomes(
                [], requested_count=requested_hint
            )["counts"]
            acquisition_observed = False
        else:
            acquisition_sources = [dict(outcome) for outcome in raw_outcomes]
            summary = describe_source_outcomes(
                acquisition_sources, requested_count=requested_hint
            )
            coverage = summary["coverage"]
            counts = summary["counts"]
            acquisition_observed = True

        canonical_sources_used = [
            source.get("source_name")
            for source in acquisition_sources
            if validated_outcome_kind(source) in SUCCESS_ACQUISITION_STATUSES
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
            "source_plan": source_plan[:20],
            "sources_used": canonical_sources_used,
            "source_outcomes": acquisition_sources,
            "acquisition_coverage": coverage,
            "acquisition_counts": counts,
            "acquisition_observed": acquisition_observed,
            "source_plan_total": requested_hint,
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
                    "name": row.get("media_name", row.get("name", row.get("source", ""))),
                    "url": row.get("rss_url", row.get("url", "")),
                    "website_url": row.get("website_url", row.get("url", "")),
                    "country": row.get("country", ""),
                    "language": row.get("language", ""),
                    "affiliation": row.get(
                        "affiliation", row.get("party_affiliation", "")
                    ),
                    "source_type": row.get("media_type", row.get("source_type", "rss")),
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
    ) -> dict[str, list[dict]]:
        """Fetch articles using the source plan.

        Args:
            sources: Prioritized list of sources
            max_per_source: Max articles to fetch per source

        Returns:
            List of article dictionaries
        """
        articles: list[dict[str, Any]] = []
        exceptions: list[dict[str, Any]] = []

        for source in sources:
            strategy = source.get("fetch_strategy", source.get("source_type", "rss"))
            source_name = source.get("name", "unknown")
            source_url = source.get("url")

            if strategy == "manual":
                if source_url:
                    articles.append(self._build_sparse_article(source, source_url, "manual"))
                else:
                    exceptions.append(
                        self._build_fetch_exception(
                            source,
                            "source_fetch_failure",
                            "Manual link source is missing a URL.",
                        )
                    )
                continue

            if strategy == "social":
                if source_url:
                    articles.append(self._build_sparse_article(source, source_url, "social"))
                else:
                    exceptions.append(
                        self._build_fetch_exception(
                            source,
                            "source_fetch_failure",
                            "Social source is missing a URL.",
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
                    continue
                try:
                    feed = RSSFeed(source_url)
                    feed_articles = feed.fetch(max_articles=max_per_source)

                    for article in feed_articles:
                        articles.append(
                            {
                                "title": article.get("title", ""),
                                "url": article.get("link", ""),
                                "content": article.get("content", ""),
                                "published_at": article.get(
                                    "timestamp", datetime.now().isoformat()
                                ),
                                "source": source.get("name", article.get("source_name", "")),
                                "source_type": source.get("source_type", "rss"),
                                "source_metadata": {
                                    "party_affiliation": source.get("party_affiliation")
                                    or source.get("affiliation", ""),
                                    "credibility_tier": source.get(
                                        "credibility_tier", "unknown"
                                    ),
                                    "fetch_strategy": strategy,
                                    "queries": source.get("queries", []),
                                    "confirmed_parties": source.get(
                                        "confirmed_parties", []
                                    ),
                                    "source_plan_score": source.get("relevance_score", 0.0),
                                },
                            }
                        )
                except Exception as exc:
                    print(f"Warning: Failed to fetch from {source_name}: {exc}")
                    exceptions.append(
                        self._build_fetch_exception(
                            source,
                            "source_fetch_failure",
                            f"Failed to fetch RSS source '{source_name}'.",
                            details={"error": str(exc)},
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

        return {"articles": articles, "exceptions": exceptions}

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

            # Parse score
            score = float(response.strip())
            return max(0.0, min(1.0, score))  # Clamp to 0-1

        except Exception:
            # Default to moderate score on error
            return 0.5
