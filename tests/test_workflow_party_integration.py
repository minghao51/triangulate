"""Tests for party classification integration in workflow."""

import pytest
from unittest.mock import AsyncMock, patch
from src.ai.workflow import AIWorkflow
from src.ai.workflows.party_investigation_workflow import party_classifier_node


@pytest.mark.asyncio
async def test_workflow_classifies_parties():
    """Workflow includes party classification after collection."""
    config = {"llm": {"model": "gpt-4"}}
    workflow = AIWorkflow(config)

    article = {
        "title": "Test Article",
        "content": "The US and Iran are in conflict.",
        "timestamp": "2025-01-01T00:00:00Z",
        "link": "https://test.com",
        "source_name": "test",
    }

    # Mock collect_claims to return entities
    claims = [
        {
            "claim": "Test 1",
            "who": ["US", "America"],
            "when": "",
            "where": "",
            "confidence": "HIGH",
        },
        {
            "claim": "Test 2",
            "who": ["Iran"],
            "when": "",
            "where": "",
            "confidence": "HIGH",
        },
    ]

    # Mock party classification response
    party_data = {
        "parties": [
            {
                "canonical_name": "United States",
                "aliases": ["US", "America", "USA"],
                "party_type": "STATE",
            },
            {"canonical_name": "Iran", "aliases": ["Iran"], "party_type": "STATE"},
        ]
    }

    with patch("src.ai.workflow.collect_claims", new=AsyncMock(return_value=claims)):
        with patch(
            "src.ai.workflow.classify_parties", new=AsyncMock(return_value=party_data)
        ):
            with patch(
                "src.ai.workflow.cluster_claims",
                new=AsyncMock(return_value={"clusters": {"0": claims}}),
            ):
                with patch(
                    "src.ai.workflow.narrate_cluster",
                    new=AsyncMock(
                        return_value={
                            "stance_summary": "Test",
                            "key_themes": [],
                            "main_entities": ["US", "Iran"],
                        }
                    ),
                ):
                    result = await workflow.process_article(article)

    # Should have party information in result
    assert "parties" in result
    assert len(result["parties"]) == 2
    assert any("party_name" in c for c in result.get("claims", []))


@pytest.mark.asyncio
async def test_party_workflow_uses_bootstrap_confirmed_parties_without_entities():
    """Bootstrap-confirmed parties should bypass empty-entity classification."""
    result = await party_classifier_node(
        {
            "article": {"confirmed_parties": ["Alpha", "Beta"]},
            "claims": [{"claim": "Sparse claim", "who": []}],
            "parties": {},
            "party_investigations": [],
            "final_determinations": [],
            "event_summary": {},
            "llm_metadata": {},
            "error": "",
        }
    )

    parties = result["parties"]["parties"]
    assert [party["canonical_name"] for party in parties] == ["Alpha", "Beta"]
    assert result["llm_metadata"]["party_classifier"]["parse_status"] == "bootstrap_override"
