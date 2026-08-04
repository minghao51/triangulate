"""Backward-compatible topic fetcher exports."""

from datetime import datetime
from typing import Any

from src.ai.prompts import get_prompt
from src.ingester.relevance_fetcher import RelevanceFetcher
from src.ai.utils import call_llm
from src.ingester.rss import RSSFeed


class TopicFetcher(RelevanceFetcher):
    """Backward-compatible alias for the relevance fetcher."""

    async def _fetch_from_sources(
        self,
        sources: list[dict],
        max_per_source: int,
    ) -> dict[str, list[dict]]:
        """Preserve the historical patch point for RSS fetches."""
        articles: list[dict[str, Any]] = []
        exceptions: list[dict[str, Any]] = []

        for source in sources:
            strategy = source.get("fetch_strategy", source.get("source_type", "rss"))
            source_name = source.get("name", "unknown")
            source_url = source.get("url")

            if strategy != "rss":
                return await super()._fetch_from_sources(sources, max_per_source)

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
                exceptions.append(
                    self._build_fetch_exception(
                        source,
                        "source_fetch_failure",
                        f"Failed to fetch RSS source '{source_name}'.",
                        details={"error": str(exc)},
                    )
                )

        return {"articles": articles, "exceptions": exceptions}

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
