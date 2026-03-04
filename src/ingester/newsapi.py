"""NewsAPI client."""

from datetime import UTC, datetime
import logging
import os
import httpx

logger = logging.getLogger(__name__)


class NewsAPIClient:
    """NewsAPI client for fetching news articles."""

    def __init__(
        self, api_key: str | None = None, base_url: str = "https://newsapi.org/v2"
    ):
        """Initialize NewsAPI client.

        Args:
            api_key: NewsAPI key (defaults to NEWSAPI_KEY env var)
            base_url: NewsAPI base URL
        """
        self.api_key = api_key or os.getenv("NEWSAPI_KEY")
        self.base_url = base_url

        if not self.api_key:
            logger.warning("No NewsAPI key provided")

        self.client = httpx.Client(timeout=10.0)

    def fetch_everything(
        self,
        query: str | None = None,
        sources: str | None = None,
        language: str = "en",
        page_size: int = 50,
    ) -> list[dict]:
        """Fetch articles from NewsAPI Everything endpoint.

        Args:
            query: Search query
            sources: Comma-separated list of sources
            language: Article language
            page_size: Number of articles to fetch

        Returns:
            List of article dictionaries
        """
        if not self.api_key:
            logger.error("Cannot fetch from NewsAPI: no API key")
            return []

        try:
            logger.info(f"Fetching from NewsAPI: query={query}, sources={sources}")

            params = {
                "apiKey": self.api_key,
                "language": language,
                "pageSize": page_size,
            }

            if query:
                params["q"] = query
            if sources:
                params["sources"] = sources

            response = self.client.get(f"{self.base_url}/everything", params=params)
            response.raise_for_status()

            data = response.json()

            if data.get("status") != "ok":
                logger.error(f"NewsAPI error: {data.get('message', 'Unknown error')}")
                return []

            articles = []
            for article in data.get("articles", []):
                parsed = self._parse_article(article)
                if parsed:
                    articles.append(parsed)

            logger.info(f"Fetched {len(articles)} articles from NewsAPI")
            return articles

        except httpx.HTTPStatusError as e:
            logger.error(f"NewsAPI HTTP error: {e.response.status_code}")
            return []
        except httpx.TimeoutException:
            logger.error("NewsAPI request timeout")
            return []
        except Exception as e:
            logger.error(f"Error fetching from NewsAPI: {e}")
            return []

    def _parse_article(self, article: dict) -> dict | None:
        """Parse a NewsAPI article.

        Args:
            article: NewsAPI article object

        Returns:
            Parsed article dictionary or None
        """
        try:
            # Parse timestamp
            timestamp = None
            if article.get("publishedAt"):
                try:
                    timestamp = datetime.fromisoformat(
                        article["publishedAt"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            if not timestamp:
                timestamp = datetime.now(UTC)

            return {
                "title": article.get("title", ""),
                "link": article.get("url", ""),
                "content": article.get("content") or article.get("description", ""),
                "timestamp": timestamp,
                "author": article.get("author", ""),
                "source_name": article.get("source", {}).get("name", ""),
                "source_type": "api",
                "source_url": "newsapi",
            }

        except Exception as e:
            logger.warning(f"Error parsing NewsAPI article: {e}")
            return None

    def close(self):
        """Close the HTTP client."""
        self.client.close()
