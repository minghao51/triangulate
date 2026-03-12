"""Tests for AI agents."""

import pytest
from unittest.mock import patch

from src.ai.agents.collector import collect_claims
from src.ai.agents.classifier import classify_verification, classify_event_verification


@pytest.mark.asyncio
async def test_collect_claims():
    """Test the collector agent."""
    article = {
        "title": "Test Article",
        "content": "This is an article about an event that happened on March 1st involving Entity A.",
    }

    # Mock the LLM response and environment
    with (
        patch("src.ai.agents.collector.call_structured_llm") as mock_structured,
        patch("src.ai.agents.collector.os.getenv", return_value="test-api-key"),
    ):
        mock_structured.return_value = {
            "output": {
                "claims": [
                    {
                        "claim": "Event happened on March 1st",
                        "who": ["Entity A"],
                        "when": "March 1st",
                        "where": "Unknown",
                        "confidence": "HIGH",
                    }
                ]
            }
        }

        claims = await collect_claims(article)

        assert len(claims) > 0
        assert claims[0]["claim"] == "Event happened on March 1st"
        assert claims[0]["confidence"] == "HIGH"


def test_classify_verification():
    """Test verification classification."""
    claim_high_confidence = {
        "confidence": "HIGH",
    }

    # High confidence with multiple sources should be CONFIRMED
    status = classify_verification(claim_high_confidence, source_count=2)
    assert status == "CONFIRMED"

    # High confidence with single source should be PROBABLE
    status = classify_verification(claim_high_confidence, source_count=1)
    assert status == "PROBABLE"

    # Low confidence should be ALLEGED
    claim_low_confidence = {"confidence": "LOW"}
    status = classify_verification(claim_low_confidence, source_count=2)
    assert status == "ALLEGED"


def test_classify_event_verification():
    """Test event verification classification."""
    claims_confirmed = [
        {"verification_status": "CONFIRMED"},
        {"verification_status": "CONFIRMED"},
        {"verification_status": "PROBABLE"},
    ]

    status = classify_event_verification(claims_confirmed, narrative_count=1)
    assert status == "CONFIRMED"

    # Contested claims - need more than 1/3 to be CONTESTED
    claims_contested = [
        {"verification_status": "CONTESTED"},
        {"verification_status": "ALLEGED"},
        {"verification_status": "CONTESTED"},
    ]

    status = classify_event_verification(claims_contested, narrative_count=3)
    assert status == "CONTESTED"
