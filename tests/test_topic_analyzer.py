"""Unit tests for topic analyzer module."""

import pytest

from src.ai.topic_analyzer import TopicAnalyzer


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
def analyzer(config):
    """Topic analyzer instance."""
    return TopicAnalyzer(config)


class TestTopicAnalyzer:
    """Test TopicAnalyzer class."""

    def test_init(self, config):
        """Test TopicAnalyzer initialization."""
        analyzer = TopicAnalyzer(config)

        assert analyzer.config == config
        assert analyzer.ai_config == config["ai"]

    @pytest.mark.asyncio
    async def test_detect_conflict_returns_string(self, analyzer):
        """Test that conflict detection returns a string."""
        # Just test that it runs and returns a string (actual LLM call)
        # In CI/test environment without API key, it will use default
        result = await analyzer.detect_conflict("Test topic")

        assert isinstance(result, str)
        assert result in ["gaza_war", "ukraine_war", "iran_war"]

    @pytest.mark.asyncio
    async def test_generate_search_queries_returns_list(self, analyzer):
        """Test that query generation returns a list."""
        result = await analyzer.generate_search_queries(
            "Test topic",
            "gaza_war"
        )

        assert isinstance(result, list)
        # Should return at least the original topic as fallback
        assert len(result) >= 1
        assert all(isinstance(q, str) for q in result)

    @pytest.mark.asyncio
    async def test_prioritize_sources_empty(self, analyzer):
        """Test source prioritization with empty list."""
        result = await analyzer.prioritize_sources(
            "Test topic",
            "gaza_war",
            []
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_prioritize_sources_returns_list(self, analyzer):
        """Test that source prioritization returns a list."""
        sources = [
            {"name": "Source A", "url": "http://a.com"},
            {"name": "Source B", "url": "http://b.com"},
        ]

        result = await analyzer.prioritize_sources(
            "Test topic",
            "gaza_war",
            sources
        )

        assert isinstance(result, list)
        assert len(result) == 2
        assert all("relevance_score" in s for s in result)

    @pytest.mark.asyncio
    async def test_extract_date_range_returns_tuple_or_none(self, analyzer):
        """Test that date range extraction returns tuple or None."""
        result = await analyzer.extract_date_range("Test topic")

        # Should be None or a tuple
        assert result is None or isinstance(result, tuple)

    @pytest.mark.asyncio
    async def test_extract_date_range_with_explicit_date(self, analyzer):
        """Test date range extraction with date in topic."""
        result = await analyzer.extract_date_range(
            "Gaza ceasefire October 2024"
        )

        # May return None or tuple depending on LLM
        assert result is None or isinstance(result, tuple)
        if result:
            assert len(result) == 2
            assert all(isinstance(d, str) for d in result)
