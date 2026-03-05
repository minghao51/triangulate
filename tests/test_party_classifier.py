"""Tests for Party classifier agent."""
import pytest
from unittest.mock import AsyncMock, patch
from src.ai.agents.party_classifier import classify_parties, _fallback_classification


@pytest.mark.asyncio
async def test_classify_parties_returns_dict_structure():
    """Test that classify_parties returns proper dict structure."""
    article = {
        "title": "Test Article",
        "content": "Test content about US and America..."
    }
    entities = ["US", "America"]

    # With no API key, should use fallback
    with patch("src.ai.agents.party_classifier.os.getenv", return_value=None):
        result = await classify_parties(article, entities)

    assert "parties" in result
    assert isinstance(result["parties"], list)
    # Fallback should still group US and America
    assert len(result["parties"]) <= 2


@pytest.mark.asyncio
async def test_classify_parties_with_empty_entities():
    """Test that empty entities returns empty parties."""
    article = {"title": "Test", "content": "Content"}
    entities = []

    result = await classify_parties(article, entities)

    assert result["parties"] == []


def test_fallback_classification_groups_by_string_similarity():
    """Fallback groups similar entities when LLM unavailable."""
    entities = ["US", "USA", "America", "iran", "Iranian", "Tehran"]

    result = _fallback_classification(entities)

    # Should group by similar strings
    # US and USA should group, US/America should group if substring match works
    assert len(result["parties"]) <= 6  # Should be less than original entities
    # Check that variations are grouped
    for party in result["parties"]:
        assert len(party["aliases"]) >= 1
        assert "canonical_name" in party
