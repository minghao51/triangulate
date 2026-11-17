"""Tests for content ingestion."""

from unittest.mock import patch, MagicMock

from src.ingester.rss import RSSFeed
from src.ingester.fetcher import ContentFetcher


def test_rss_feed_parsing():
    """Test RSS feed parsing."""
    # Mock feedparser response - need both attribute and dict access
    mock_entry = {
        "title": "Test Article",
        "link": "https://example.com/article1",
        "description": "Test description",
        "published_parsed": (2024, 3, 1, 12, 0, 0, 0, 0, 0),
        "author": "Test Author",
    }

    mock_feed = MagicMock()
    mock_feed.entries = [mock_entry]
    mock_feed.bozo = False

    with (
        patch("src.ingester.rss.feedparser.parse", return_value=mock_feed),
        # Keep the test hermetic: short descriptions would otherwise trigger a
        # real full-article HTTP fetch.
        patch.object(RSSFeed, "_fetch_full_article", return_value=""),
    ):
        feed = RSSFeed("https://example.com/feed.xml")
        articles = feed.fetch(max_articles=10)

        assert len(articles) == 1
        assert articles[0]["title"] == "Test Article"
        assert articles[0]["link"] == "https://example.com/article1"


def test_content_fetcher(tmp_path):
    """Test content fetching without accessing the runtime database."""
    config = {
        "sources": {
            "rss": {
                "test_source": "https://example.com/feed.xml",
            }
        }
    }

    with patch("src.ingester.rss.feedparser.parse") as mock_parse:
        mock_parse.return_value = {
            "entries": [],
            "bozo": False,
            # A recognised feed version is required for a genuine healthy-empty
            # feed (see B02 recognised-feed evidence).
            "version": "rss20",
        }

        fetcher = ContentFetcher(config)
        with patch.object(fetcher, "_update_source") as update_source:
            articles = fetcher.fetch_from_source("test_source", limit=5)

        # The healthy empty feed updates metadata through the mocked boundary,
        # never through a connection to a local runtime database.
        assert isinstance(articles, list)
        assert articles == []
        update_source.assert_called_once()
