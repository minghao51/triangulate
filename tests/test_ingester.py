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

    with patch("src.ingester.rss.feedparser.parse", return_value=mock_feed):
        feed = RSSFeed("https://example.com/feed.xml")
        articles = feed.fetch(max_articles=10)

        assert len(articles) == 1
        assert articles[0]["title"] == "Test Article"
        assert articles[0]["link"] == "https://example.com/article1"


def test_content_fetcher():
    """Test content fetcher."""
    config = {
        "sources": {
            "rss": {
                "test_source": "https://example.com/feed.xml",
            }
        }
    }

    with patch("src.ingester.rss.feedparser.parse") as mock_parse:
        mock_parse.return_value = {"entries": [], "bozo": False}

        fetcher = ContentFetcher(config)
        articles = fetcher.fetch_from_source("test_source", limit=5)

        # Should return empty list but not crash
        assert isinstance(articles, list)
