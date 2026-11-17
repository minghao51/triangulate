"""Backward-compatible content fetcher exports."""

import logging

from src.ingester.polling_fetcher import PollingFetcher
from src.ingester.rss import SUCCESS_ACQUISITION_STATUSES, RSSFeed
from src.storage.models import SourceType

logger = logging.getLogger(__name__)


class ContentFetcher(PollingFetcher):
    """Backward-compatible alias for the polling fetcher.

    The acquisition loop is inherited from :class:`PollingFetcher`; only the two
    source-acquisition methods are overridden to keep the honest acquisition
    contract (B02): an RSS feed that failed or was skipped is never recorded as
    a freshly fetched source, and it never contributes articles.
    """

    def fetch_all(self, limit: int | None = None) -> list[dict]:
        """Fetch content from all configured sources.

        Args:
            limit: Maximum articles per source

        Returns:
            List of all fetched articles
        """
        all_articles = []
        sources_config = self.config.get("sources", {})

        # Fetch from RSS sources
        for name, url in sources_config.get("rss", {}).items():
            logger.info(f"Fetching from RSS source: {name}")
            feed = RSSFeed(url)
            outcome = feed.fetch_with_outcome(max_articles=limit or 50)
            all_articles.extend(outcome.articles)

            if outcome.status in SUCCESS_ACQUISITION_STATUSES:
                self._update_source(name, SourceType.RSS, url)
            else:
                logger.warning(
                    "RSS source %s not acquired (%s: %s); last_fetched unchanged",
                    name,
                    outcome.status,
                    outcome.error or outcome.reason,
                )

        # Fetch from NewsAPI
        if self.newsapi_client:
            logger.info("Fetching from NewsAPI")
            api_articles = self.newsapi_client.fetch_everything(page_size=limit or 50)
            all_articles.extend(api_articles)
            self._update_source("newsapi", SourceType.API, "newsapi")

        logger.info(f"Total articles fetched: {len(all_articles)}")
        return all_articles

    def fetch_from_source(self, source_name: str, limit: int = 50) -> list[dict]:
        """Fetch content from a specific source.

        Args:
            source_name: Name of the source to fetch from
            limit: Maximum articles to fetch

        Returns:
            List of fetched articles
        """
        sources_config = self.config.get("sources", {})

        # Check RSS sources
        rss_sources = sources_config.get("rss", {})
        if source_name in rss_sources:
            feed = RSSFeed(rss_sources[source_name])
            outcome = feed.fetch_with_outcome(max_articles=limit)
            if outcome.status in SUCCESS_ACQUISITION_STATUSES:
                self._update_source(
                    source_name, SourceType.RSS, rss_sources[source_name]
                )
            else:
                logger.warning(
                    "RSS source %s not acquired (%s: %s); last_fetched unchanged",
                    source_name,
                    outcome.status,
                    outcome.error or outcome.reason,
                )
            return outcome.articles

        # Check NewsAPI
        if source_name == "newsapi" and self.newsapi_client:
            articles = self.newsapi_client.fetch_everything(page_size=limit)
            self._update_source("newsapi", SourceType.API, "newsapi")
            return articles

        logger.warning(f"Unknown source: {source_name}")
        return []


__all__ = ["ContentFetcher", "PollingFetcher"]
