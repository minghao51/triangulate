"""RSS feed parser with enhanced content extraction."""

import logging
from datetime import UTC, datetime
import feedparser
from httpx import TimeoutException
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Try to import trafilatura for better content extraction
try:
    from trafilatura import fetch_url, extract

    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    logger.warning("trafilatura not available, using basic RSS content only")

# Try to import BeautifulSoup for fallback
try:
    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logger.warning("beautifulsoup4 not available")


class RSSFeed:
    """RSS feed parser."""

    def __init__(self, url: str, timeout: int = 10):
        """Initialize RSS feed parser.

        Args:
            url: RSS feed URL
            timeout: Request timeout in seconds
        """
        self.url = url
        self.timeout = timeout

    def fetch(self, max_articles: int = 50) -> list[dict]:
        """Fetch articles from RSS feed.

        Args:
            max_articles: Maximum number of articles to fetch

        Returns:
            List of article dictionaries
        """
        try:
            logger.info(f"Fetching RSS feed: {self.url}")
            feed = feedparser.parse(self.url)

            if feed.bozo:
                logger.warning(
                    f"Feed parsing warning for {self.url}: {feed.bozo_exception}"
                )

            articles = []
            for entry in feed.entries[:max_articles]:
                article = self._parse_entry(entry)
                if article:
                    articles.append(article)

            logger.info(f"Fetched {len(articles)} articles from {self.url}")
            return articles

        except TimeoutException:
            logger.error(f"Timeout fetching RSS feed: {self.url}")
            return []
        except Exception as e:
            logger.error(f"Error fetching RSS feed {self.url}: {e}")
            return []

    def _fetch_full_article(self, url: str, title: str) -> str:
        """Fetch full article content from URL.

        Args:
            url: Article URL
            title: Article title (for metadata)

        Returns:
            Article content as string
        """
        if not TRAFILATURA_AVAILABLE:
            return ""

        try:
            # Try trafilatura first
            downloaded = fetch_url(url, timeout=self.timeout)
            if downloaded:
                result = extract(
                    downloaded,
                    include_comments=False,
                    include_tables=False,
                    no_fallback=False,
                )
                if result and len(result) > 200:
                    logger.info(f"Enhanced content extraction for: {title[:50]}...")
                    return result
        except Exception as e:
            logger.debug(f"Trafilatura extraction failed: {e}")

        if BS4_AVAILABLE:
            # Fallback to BeautifulSoup
            try:
                import httpx

                response = httpx.get(url, timeout=self.timeout, follow_redirects=True)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")

                # Try common article containers
                content_selectors = [
                    "article",
                    '[class*="article"]',
                    '[class*="story"]',
                    '[class*="content"]',
                    "main",
                ]

                content = ""
                for selector in content_selectors:
                    element = soup.select_one(selector)
                    if element:
                        # Remove script and style elements
                        for script in element(
                            ["script", "style", "nav", "footer", "header"]
                        ):
                            script.decompose()
                        content = element.get_text(separator="\n", strip=True)
                        if len(content) > 200:
                            break

                # Fallback: get all paragraphs
                if not content or len(content) < 200:
                    paragraphs = soup.find_all("p")
                    content = "\n".join([p.get_text().strip() for p in paragraphs])

                if content and len(content) > 200:
                    logger.info(f"BeautifulSoup extraction for: {title[:50]}...")
                    return content

            except Exception as e:
                logger.debug(f"BeautifulSoup extraction failed: {e}")

        return ""

    def _parse_entry(self, entry: dict) -> dict | None:
        """Parse a single RSS entry.

        Args:
            entry: Feedparser entry object

        Returns:
            Article dictionary or None if parsing fails
        """
        try:
            # Extract basic fields using dict access
            title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published_parsed")

            # Extract content/description using dict access
            content = ""
            if "content" in entry:
                content_list = entry.get("content", [])
                if content_list and len(content_list) > 0:
                    content = content_list[0].get("value", "")
            elif "description" in entry:
                content = entry.get("description", "")
            elif "summary" in entry:
                content = entry.get("summary", "")

            # Enhance content if it's too short
            # Use trafilatura or BeautifulSoup to fetch full article
            if link and len(content) < 500:
                enhanced_content = self._fetch_full_article(link, title)
                if enhanced_content and len(enhanced_content) > len(content):
                    content = enhanced_content

            # Parse timestamp
            timestamp = None
            if published:
                try:
                    timestamp = datetime(*published[:6])
                except (TypeError, ValueError):
                    pass

            if not timestamp:
                timestamp = datetime.now(UTC)

            # Extract author if available
            author = entry.get("author", "")

            # Extract source name from URL
            source_name = urlparse(link).netloc.replace("www.", "") if link else ""

            return {
                "title": title,
                "link": link,
                "content": content,
                "timestamp": timestamp,
                "author": author,
                "source_type": "rss",
                "source_url": self.url,
                "source_name": source_name,
            }

        except Exception as e:
            logger.warning(f"Error parsing entry: {e}")
            return None
