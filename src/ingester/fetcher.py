"""Content fetcher that coordinates RSS and API sources."""

import logging
import uuid
from datetime import UTC, datetime

from src.ingester.rss import RSSFeed
from src.ingester.newsapi import NewsAPIClient
from src.storage import get_database, Source
from src.storage.models import SourceType

logger = logging.getLogger(__name__)


class ContentFetcher:
    """Fetch content from multiple sources."""

    def __init__(self, config: dict):
        """Initialize content fetcher.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.db = get_database()
        self.newsapi_client = (
            NewsAPIClient()
            if config.get("sources", {}).get("api", {}).get("newsapi_enabled")
            else None
        )

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
            articles = feed.fetch(max_articles=limit or 50)
            all_articles.extend(articles)

            # Update source last_fetched time
            self._update_source(name, SourceType.RSS, url)

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
            articles = feed.fetch(max_articles=limit)
            self._update_source(source_name, SourceType.RSS, rss_sources[source_name])
            return articles

        # Check NewsAPI
        if source_name == "newsapi" and self.newsapi_client:
            articles = self.newsapi_client.fetch_everything(page_size=limit)
            self._update_source("newsapi", SourceType.API, "newsapi")
            return articles

        logger.warning(f"Unknown source: {source_name}")
        return []

    def _update_source(self, name: str, source_type: SourceType, url: str) -> None:
        """Update source in database.

        Args:
            name: Source name
            source_type: Source type
            url: Source URL
        """
        try:
            session = self.db.get_session_sync()

            # Try to get existing source
            source = session.query(Source).filter(Source.name == name).first()

            if source:
                # Update last_fetched time
                source.last_fetched = datetime.now(UTC)
            else:
                # Create new source
                source = Source(
                    id=str(uuid.uuid4()),
                    name=name,
                    type=source_type,
                    url=url,
                    last_fetched=datetime.now(UTC),
                )
                session.add(source)

            session.commit()

        except Exception as e:
            logger.error(f"Error updating source {name}: {e}")

    def store_articles(self, articles: list[dict]) -> int:
        """Store raw articles in database.

        Args:
            articles: List of article dictionaries

        Returns:
            Number of articles stored
        """
        # For now, just return the count
        # Actual storage will be done after AI processing
        return len(articles)
