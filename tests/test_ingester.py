"""Tests for content ingestion."""

import logging
from typing import Any, cast
from unittest.mock import patch, MagicMock

import pytest

from src.ingester.polling_fetcher import PollingFetcher
from src.storage import Database
from src.ingester.rss import RSSFeed
from src.ingester.fetcher import ContentFetcher
from src.storage.models import SourceType


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


# ============================================================================
# Source-metadata session lifecycle (fake sessions, no runtime database)
# ============================================================================


class _FakeSession:
    """Minimal SQLAlchemy-session stand-in recording lifecycle calls."""

    def __init__(self, *, existing=None, fail_on: str | None = None):
        self.existing = existing
        self.fail_on = fail_on
        self.added = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def query(self, model):
        if self.fail_on == "query":
            raise RuntimeError("query failed")
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.existing

    def add(self, obj):
        if self.fail_on == "add":
            raise RuntimeError("add failed")
        self.added.append(obj)

    def commit(self):
        if self.fail_on == "commit":
            raise RuntimeError("commit failed")
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class _FakeDatabase:
    """Session factory stand-in for :class:`Database`."""

    def __init__(self, factory):
        self._factory = factory
        self.calls = 0

    def get_session_sync(self):
        self.calls += 1
        return self._factory()


def _install_fake_database(fetcher: PollingFetcher, database: Any) -> None:
    """Swap the fetcher's DB handle for a stand-in session factory."""
    fetcher.db = cast(Database, database)


def _polling_fetcher() -> PollingFetcher:
    return PollingFetcher(
        {"sources": {"rss": {"test_source": "https://example.com/feed.xml"}}}
    )


def test_update_source_commits_and_closes_session():
    fetcher = _polling_fetcher()
    session = _FakeSession()
    _install_fake_database(fetcher, _FakeDatabase(lambda: session))

    fetcher._update_source("test-source", SourceType.RSS, "https://example.com/feed.xml")

    assert session.committed is True
    assert session.closed is True
    assert session.rolled_back is False
    assert len(session.added) == 1


@pytest.mark.parametrize("fail_on", ["query", "add", "commit"])
def test_update_source_rolls_back_and_closes_on_write_failure(fail_on):
    fetcher = _polling_fetcher()
    session = _FakeSession(fail_on=fail_on)
    _install_fake_database(fetcher, _FakeDatabase(lambda: session))

    fetcher._update_source("test-source", SourceType.RSS, "https://example.com/feed.xml")

    assert session.committed is False
    assert session.rolled_back is True
    assert session.closed is True


def test_update_source_is_safe_when_session_cannot_be_created(caplog):
    fetcher = _polling_fetcher()

    def boom():
        raise RuntimeError("session construction failed")

    _install_fake_database(fetcher, _FakeDatabase(boom))

    with caplog.at_level(logging.ERROR):
        fetcher._update_source(
            "test-source", SourceType.RSS, "https://example.com/feed.xml"
        )

    assert "session construction failed" in caplog.text


def test_metadata_update_failure_keeps_healthy_articles():
    """A logged metadata failure must not discard fetched articles."""
    fetcher = _polling_fetcher()
    _install_fake_database(fetcher, _FakeDatabase(lambda: _FakeSession(fail_on="query")))
    entry = {
        "title": "Healthy article",
        "link": "https://example.com/article1",
        "description": "Test description",
        "published_parsed": (2024, 3, 1, 12, 0, 0, 0, 0, 0),
        "author": "Test Author",
    }

    with (
        patch("src.ingester.rss.feedparser.parse") as mock_parse,
        patch.object(RSSFeed, "_fetch_full_article", return_value=""),
    ):
        mock_parse.return_value = {
            "entries": [entry],
            "bozo": False,
            "version": "rss20",
        }
        articles = fetcher.fetch_from_source("test_source", limit=5)

    assert len(articles) == 1
    assert articles[0]["title"] == "Healthy article"
