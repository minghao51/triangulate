"""Unit tests for topic fetcher module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.ingester.rss import FeedAcquisitionOutcome
from src.ingester.topic_fetcher import TopicFetcher


@pytest.fixture
def config():
    """Test configuration."""
    return {
        "ai": {
            "model": "test-model",
            "api_key": "test-key",
        }
    }


@pytest.fixture
def fetcher(config):
    """Topic fetcher instance."""
    return TopicFetcher(config)


@pytest.fixture
def mock_sources():
    """Mock media sources."""
    return [
        {
            "name": "Reuters",
            "url": "http://reuters.com/rss",
            "country": "International",
            "language": "en",
            "affiliation": "Independent"
        },
        {
            "name": "Al Jazeera",
            "url": "http://aljazeera.com/rss",
            "country": "Qatar",
            "language": "en",
            "affiliation": "State-funded"
        }
    ]


class TestTopicFetcher:
    """Test TopicFetcher class."""

    def test_init(self, config):
        """Test TopicFetcher initialization."""
        fetcher = TopicFetcher(config)

        assert fetcher.config == config
        assert fetcher.data_dir == Path("data/source")

    def test_load_sources_not_found(self, fetcher, tmp_path):
        """Test loading sources when directory doesn't exist."""
        fetcher.data_dir = tmp_path / "nonexistent"

        result = fetcher._load_sources("gaza_war")

        assert result == []

    def test_load_sources_no_csv(self, fetcher, tmp_path):
        """Test loading sources when no CSV file exists."""
        # Create directory but no CSV
        conflict_dir = tmp_path / "gaza_war"
        conflict_dir.mkdir()
        fetcher.data_dir = tmp_path

        result = fetcher._load_sources("gaza_war")

        assert result == []

    def test_load_sources_success(self, fetcher, tmp_path):
        """Test successful source loading."""
        import csv

        # Create test CSV file
        conflict_dir = tmp_path / "gaza_war"
        conflict_dir.mkdir()

        csv_file = conflict_dir / "sources.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "url", "country"])
            writer.writeheader()
            writer.writerow({
                "name": "Test Source",
                "url": "http://test.com/rss",
                "country": "Test"
            })

        fetcher.data_dir = tmp_path

        result = fetcher._load_sources("gaza_war")

        assert len(result) == 1
        assert result[0]["name"] == "Test Source"
        assert result[0]["url"] == "http://test.com/rss"

    @pytest.mark.asyncio
    async def test_fetch_articles_by_topic(self, fetcher, mock_sources):
        """Test fetching articles by topic."""
        with patch.object(fetcher, '_load_sources', return_value=mock_sources):
            with patch.object(fetcher, '_fetch_from_sources', new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = {
                    "articles": [
                        {
                            "title": "Test Article",
                            "url": "http://test.com/article1",
                            "content": "Test content",
                            "published_at": "2024-01-01",
                            "source": "Reuters"
                        }
                    ],
                    "exceptions": [],
                }

                with patch.object(fetcher, '_score_articles', new_callable=AsyncMock) as mock_score:
                    mock_score.return_value = [
                        {
                            **mock_fetch.return_value["articles"][0],
                            "relevance_score": 0.9
                        }
                    ]

                    result = await fetcher.fetch_articles_by_topic(
                        query="Gaza ceasefire",
                        conflict="gaza_war",
                        max_articles=10
                    )

                    assert "articles" in result
                    assert result["conflict"] == "gaza_war"
                    assert len(result["articles"]) == 1

    @pytest.mark.asyncio
    async def test_fetch_from_sources_empty(self, fetcher):
        """Test fetching from empty source list."""
        result = await fetcher._fetch_from_sources([], 10)

        # Legacy keys stay present for existing callers.
        assert result["articles"] == []
        assert result["exceptions"] == []
        # ... and B02 adds structured coverage: no source was even requested.
        assert result["source_outcomes"] == []
        assert result["acquisition_coverage"] == "not_attempted"
        assert result["acquisition_counts"]["requested"] == 0
        assert result["acquisition_counts"]["attempted"] == 0

    @pytest.mark.asyncio
    async def test_fetch_from_sources_rss_error(self, fetcher, mock_sources):
        """Test fetching from sources when RSS fails."""
        failed_outcome = FeedAcquisitionOutcome(
            source_url="http://example.com/rss",
            status="failed",
            attempted=True,
            error="RSS error",
            reason="transport_error",
        )
        with patch("src.ingester.topic_fetcher.RSSFeed") as mock_feed_class:
            mock_feed = MagicMock()
            mock_feed.fetch_with_outcome.return_value = failed_outcome
            mock_feed_class.return_value = mock_feed

            result = await fetcher._fetch_from_sources(mock_sources, 10)

            assert result["articles"] == []
            assert len(result["exceptions"]) == len(mock_sources)
            assert result["acquisition_coverage"] == "failed"
            assert result["acquisition_counts"]["failed"] == len(mock_sources)
            assert all(
                outcome["status"] == "failed"
                for outcome in result["source_outcomes"]
            )

    @pytest.mark.asyncio
    async def test_score_articles(self, fetcher):
        """Test article relevance scoring."""
        articles = [
            {
                "title": "Gaza Ceasefire Talks",
                "url": "http://test.com/article1",
                "content": "Discussions about Gaza ceasefire...",
                "source": "Reuters"
            },
            {
                "title": "Unrelated Article",
                "url": "http://test.com/article2",
                "content": "Something completely different...",
                "source": "BBC"
            }
        ]

        with patch.object(fetcher, '_score_relevance', new_callable=AsyncMock) as mock_score:
            # First article relevant, second not
            mock_score.side_effect = [0.9, 0.2]

            result = await fetcher._score_articles(
                articles,
                "Gaza ceasefire",
                threshold=0.3
            )

            # Should only include the relevant article
            assert len(result) == 1
            assert result[0]["relevance_score"] == 0.9

    @pytest.mark.asyncio
    async def test_score_relevance_high(self, fetcher):
        """Test scoring highly relevant article."""
        with patch('src.ingester.topic_fetcher.call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "0.9"

            article = {
                "title": "Gaza Ceasefire Agreement Reached",
                "content": "Hamas and Israel agree to ceasefire...",
                "source": "Reuters"
            }

            result = await fetcher._score_relevance(article, "Gaza ceasefire")

            assert result == 0.9

    @pytest.mark.asyncio
    async def test_score_relevance_clamping(self, fetcher):
        """Test that scores are clamped to 0-1 range."""
        with patch('src.ingester.topic_fetcher.call_llm', new_callable=AsyncMock) as mock_llm:
            # Test values outside 0-1 range
            mock_llm.return_value = "1.5"

            article = {
                "title": "Test",
                "content": "Test content",
                "source": "Test"
            }

            result = await fetcher._score_relevance(article, "Test")

            # Should be clamped to 1.0
            assert result == 1.0

    @pytest.mark.asyncio
    async def test_score_relevance_error_fallback(self, fetcher):
        """Test scoring fallback on error."""
        with patch('src.ingester.topic_fetcher.call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("LLM error")

            article = {
                "title": "Test",
                "content": "Test content",
                "source": "Test"
            }

            result = await fetcher._score_relevance(article, "Test")

            # Should return default score on error
            assert result == 0.5
