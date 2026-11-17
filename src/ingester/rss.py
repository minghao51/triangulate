"""RSS feed parser with enhanced content extraction."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import feedparser
from httpx import TimeoutException
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class AcquisitionStatus(str, Enum):
    """Honest per-source acquisition status vocabulary."""

    SUCCESS_WITH_ITEMS = "success_with_items"
    SUCCESS_EMPTY = "success_empty"
    FAILED = "failed"
    SKIPPED = "skipped"


SUCCESS_ACQUISITION_STATUSES = frozenset(
    {
        AcquisitionStatus.SUCCESS_WITH_ITEMS.value,
        AcquisitionStatus.SUCCESS_EMPTY.value,
    }
)


def feed_field(feed: Any, name: str, default: Any = None) -> Any:
    """Read a feed field from feedparser structs or plain mappings.

    ``feedparser`` feed objects support both attribute and item access, while a
    plain ``dict`` (used by callers/tests) supports only item access. Attribute
    access is attempted first so mocked feed objects keep their configured
    values instead of receiving synthetic mapping values.
    """
    try:
        return getattr(feed, name)
    except AttributeError:
        pass
    try:
        value = feed[name]
    except (KeyError, TypeError, IndexError):
        return default
    return default if value is None else value


def _coerce_http_status(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        # Some Unicode digits (for example "²") report ``isdigit()`` but are not
        # accepted by ``int()``; never raise out of classification.
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


# Real ``feedparser`` reports a concrete feed version such as ``rss20``,
# ``atom10`` or ``rdf``. Anything else (a plain HTML page, an XML error or
# maintenance message, empty bytes) is not recognised feed evidence.
RECOGNIZED_FEED_VERSION_PREFIXES = ("rss", "atom", "rdf")


def _recognized_feed_version(value: Any) -> str | None:
    """Return a normalised recognised feed version, or ``None``."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized.startswith(RECOGNIZED_FEED_VERSION_PREFIXES):
        return normalized
    return None


@dataclass
class FeedAcquisitionOutcome:
    """Structured, honest result of one feed acquisition attempt.

    ``success_with_items`` and ``success_empty`` are genuine acquisitions;
    ``failed`` covers timeouts, transport/parse errors, non-success HTTP
    responses and feeds whose entries could not be parsed at all; ``skipped``
    covers responses that deliberately returned no fresh content (for example a
    cached 304 Not Modified). A recovered entry set alongside a ``bozo``
    warning stays usable but keeps the warning/``bozo`` disclosure.
    """

    source_url: str
    status: str
    source_name: str = ""
    articles: list[dict] = field(default_factory=list)
    attempted: bool = True
    error: str | None = None
    warning: str | None = None
    reason: str | None = None
    http_status: int | None = None
    bozo: bool = False
    entries_seen: int = 0
    entries_parsed: int = 0
    entries_considered: int = 0
    parse_failures: int = 0
    degraded: bool = False
    feed_version: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status in SUCCESS_ACQUISITION_STATUSES

    @property
    def usable(self) -> bool:
        """True when the outcome carries articles that may be processed."""
        return bool(self.articles)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "source_name": self.source_name,
            "source_type": "rss",
            "fetch_strategy": "rss",
            "status": self.status,
            "attempted": self.attempted,
            "succeeded": self.succeeded,
            "article_count": len(self.articles),
            "error": self.error,
            "warning": self.warning,
            "reason": self.reason,
            "http_status": self.http_status,
            "bozo": self.bozo,
            "entries_seen": self.entries_seen,
            "entries_parsed": self.entries_parsed,
            "entries_considered": self.entries_considered,
            "parse_failures": self.parse_failures,
            "degraded": self.degraded,
            "feed_version": self.feed_version,
        }

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
        self.source_name = urlparse(url).netloc.replace("www.", "") or url

    def fetch(self, max_articles: int = 50) -> list[dict]:
        """Fetch articles from RSS feed.

        Legacy list-returning wrapper around :meth:`fetch_with_outcome`. A
        failed or skipped acquisition returns an empty list, exactly as before;
        callers that need to distinguish failure from a healthy empty feed must
        use :meth:`fetch_with_outcome`.

        Args:
            max_articles: Maximum number of articles to fetch

        Returns:
            List of article dictionaries
        """
        return self.fetch_with_outcome(max_articles=max_articles).articles

    def fetch_with_outcome(self, max_articles: int = 50) -> FeedAcquisitionOutcome:
        """Fetch articles and report a structured acquisition outcome.

        Args:
            max_articles: Maximum number of entries to parse

        Returns:
            A :class:`FeedAcquisitionOutcome` describing what actually happened.
        """
        logger.info(f"Fetching RSS feed: {self.url}")
        try:
            feed = feedparser.parse(self.url)
        except TimeoutException as exc:
            logger.error(f"Timeout fetching RSS feed: {self.url}")
            return FeedAcquisitionOutcome(
                source_url=self.url,
                status=AcquisitionStatus.FAILED.value,
                error=str(exc) or "timeout",
                reason="timeout",
            )
        except Exception as exc:
            logger.error(f"Error fetching RSS feed {self.url}: {exc}")
            return FeedAcquisitionOutcome(
                source_url=self.url,
                status=AcquisitionStatus.FAILED.value,
                error=str(exc),
                reason="transport_error",
            )

        try:
            return self._classify_feed(feed, max_articles)
        except Exception as exc:
            # Classification is part of the acquisition attempt: a malformed
            # parser result must not raise through the legacy ``fetch() -> list``
            # wrapper, and must never look like a fresh success.
            logger.error(f"Error classifying RSS feed {self.url}: {exc}")
            return FeedAcquisitionOutcome(
                source_url=self.url,
                status=AcquisitionStatus.FAILED.value,
                error=str(exc),
                reason="parse_error",
            )

    def _classify_feed(self, feed: Any, max_articles: int) -> FeedAcquisitionOutcome:
        """Classify a feedparser result as success, failure or skipped."""
        http_status = _coerce_http_status(feed_field(feed, "status"))
        bozo = bool(feed_field(feed, "bozo", False))
        bozo_exception = feed_field(feed, "bozo_exception")
        feed_version = _recognized_feed_version(feed_field(feed, "version"))

        raw_entries = feed_field(feed, "entries", []) or []
        try:
            entries_seen = len(raw_entries)
        except TypeError:
            raw_entries = []
            entries_seen = 0
        selected_entries = list(raw_entries)[:max_articles]

        base: dict[str, Any] = {
            "source_url": self.url,
            "source_name": self.source_name,
            "http_status": http_status,
            "bozo": bozo,
            "entries_seen": entries_seen,
            "entries_considered": len(selected_entries),
            "feed_version": feed_version,
        }
        bozo_warning = (
            f"Feed parsing warning for {self.url}: {bozo_exception}" if bozo else None
        )
        if bozo_warning:
            logger.warning(bozo_warning)

        if http_status == 304:
            # A cached/not-modified response cannot stand in for a fresh success.
            return FeedAcquisitionOutcome(
                status=AcquisitionStatus.SKIPPED.value,
                attempted=True,
                reason="http_not_modified",
                warning=bozo_warning,
                **base,
            )
        if http_status is not None and http_status >= 400:
            return FeedAcquisitionOutcome(
                status=AcquisitionStatus.FAILED.value,
                error=f"HTTP {http_status} from feed endpoint",
                reason=f"http_{http_status}",
                warning=bozo_warning,
                entries_parsed=0,
                **base,
            )

        articles: list[dict] = []
        parse_failures = 0
        for entry in selected_entries:
            article = self._parse_entry(entry)
            if article:
                articles.append(article)
            else:
                parse_failures += 1

        warnings = [w for w in (bozo_warning,) if w]
        if parse_failures:
            warnings.append(
                f"{parse_failures} of {len(selected_entries)} selected feed "
                "entries could not be parsed"
            )
        combined_warning = "; ".join(warnings) or None
        # Recovered-but-imperfect acquisition: a ``bozo`` feed that still yielded
        # articles, or a mixed entry set with unparseable entries. Articles stay
        # usable, but the acquisition is explicitly degraded and must never be
        # treated as a clean complete success. Bounded ``max_articles`` truncation
        # is intentional and is not a parse failure.
        degraded = bool(parse_failures) or bool(bozo and articles)

        if articles:
            logger.info(f"Fetched {len(articles)} articles from {self.url}")
            return FeedAcquisitionOutcome(
                status=AcquisitionStatus.SUCCESS_WITH_ITEMS.value,
                articles=articles,
                entries_parsed=len(articles),
                parse_failures=parse_failures,
                degraded=degraded,
                warning=combined_warning,
                **base,
            )

        if bozo:
            return FeedAcquisitionOutcome(
                status=AcquisitionStatus.FAILED.value,
                error=bozo_warning or "feed parser reported a malformed feed",
                reason="entries_unparseable" if entries_seen else "malformed_feed",
                entries_parsed=0,
                parse_failures=parse_failures,
                warning=combined_warning,
                **base,
            )

        if entries_seen == 0:
            if feed_version is not None:
                logger.info(
                    f"Feed {self.url} returned no entries "
                    f"({feed_version} feed, healthy empty)"
                )
                return FeedAcquisitionOutcome(
                    status=AcquisitionStatus.SUCCESS_EMPTY.value,
                    entries_parsed=0,
                    warning=combined_warning,
                    **base,
                )
            # No entries, no parser warning and no recognised feed version: empty
            # bytes, a maintenance message or a well-formed HTML page is not a
            # healthy empty feed.
            return FeedAcquisitionOutcome(
                status=AcquisitionStatus.FAILED.value,
                error=(
                    "Response was not a recognised RSS/Atom/RDF feed "
                    "(no feed version reported)"
                ),
                reason="unrecognized_feed",
                entries_parsed=0,
                warning=combined_warning,
                **base,
            )

        return FeedAcquisitionOutcome(
            status=AcquisitionStatus.FAILED.value,
            error=(
                f"{parse_failures or entries_seen} feed entr"
                f"{'y' if (parse_failures or entries_seen) == 1 else 'ies'} "
                f"could not be parsed"
            ),
            reason="entries_unparseable",
            entries_parsed=0,
            parse_failures=parse_failures,
            warning=combined_warning,
            **base,
        )

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
