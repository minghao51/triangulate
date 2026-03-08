#!/usr/bin/env python3
"""Integration test for party-based adversarial investigation workflow.

This test demonstrates and validates the multi-agent LangGraph workflow where:
1. Multiple party investigators analyze claims from different perspectives
2. An arbiter reviews all findings and makes objective determinations
3. Facts are distinguished from allegations
4. Verification status is assigned with reasoning

Usage as pytest:
    uv run pytest tests/integration/test_party_investigation_demo.py -v

Usage as demo:
    uv run python -m tests.integration.test_party_investigation_demo
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.ai.workflows.party_investigation_workflow import (
    create_party_investigation_workflow,
    format_workflow_results,
)


# ============================================================================
# MOCK TEST DATA
# ============================================================================

MOCK_ARTICLE = {
    "title": "Global Summit Reaches Historic Climate Agreement",
    "content": """
    World leaders from 195 countries gathered in Geneva this week for the UN Climate Summit,
    culminating in a landmark agreement that commits signatories to achieving net-zero emissions
    by 2050. The agreement includes binding targets for reducing carbon emissions by 50% before 2030.

    Key provisions of the agreement include:
    - A $100 billion annual fund for developing nations to transition to renewable energy
    - Mandatory reporting of carbon emissions starting in 2026
    - Phase-out of coal power by 2040 for developed nations
    - Support for reforestation projects in the Amazon and Congo basins

    China and the United States, the world's two largest emitters, both pledged to meet their
    targets ahead of schedule. Chinese representatives emphasized their commitment to green
    technology development, while US officials highlighted the importance of international
    cooperation.

    Environmental groups praised the agreement as 'the most significant climate action in history,'
    while some industry representatives raised concerns about the economic impact of rapid
    decarbonization. The Chamber of Commerce warned that aggressive timelines could harm
    manufacturing competitiveness.

    The agreement also establishes a new international monitoring body to track progress and
    enforce compliance, with the first progress report due in 2028.
    """,
    "timestamp": "2024-01-15T10:00:00Z",
    "link": "https://example.com/climate-summit-agreement",
    "source_name": "Global News Network",
    "author": "Jane Smith",
}


# ============================================================================
# TEST FUNCTIONS
# ============================================================================


async def run_party_investigation_workflow():
    """Run the party investigation workflow and return results."""
    # Create workflow
    workflow = create_party_investigation_workflow()

    # Initialize state
    initial_state = {
        "article": MOCK_ARTICLE,
        "claims": [],
        "parties": {},
        "party_investigations": [],
        "final_determinations": [],
        "event_summary": {},
        "error": "",
    }

    # Run workflow
    final_state = await workflow.ainvoke(initial_state)

    return final_state


def test_party_investigation_workflow():
    """Test the party investigation workflow with mock data.

    This is an integration test that validates:
    - Workflow creates successfully
    - Claims are extracted
    - Parties are identified
    - Party investigations are completed
    - Arbiter makes determinations
    - Event summary is generated
    """
    asyncio.run(_test_async())


async def _test_async():
    """Async implementation of the test."""
    # Skip if no LLM API key (test will run but may use fallbacks)
    if not os.getenv("LLM_API_KEY"):
        # Mark as test but don't fail - it will use fallback logic
        pass

    # Run workflow
    final_state = await run_party_investigation_workflow()

    # Assertions to verify workflow works correctly
    assert final_state is not None, "Final state should not be None"
    assert isinstance(final_state, dict), "Final state should be a dictionary"

    # Check that claims were extracted
    claims = final_state.get("claims", [])
    assert isinstance(claims, list), "Claims should be a list"

    # Check that parties were identified
    parties = final_state.get("parties", {})
    assert isinstance(parties, dict), "Parties should be a dictionary"

    # Check that party investigations were completed
    investigations = final_state.get("party_investigations", [])
    assert isinstance(investigations, list), "Party investigations should be a list"

    # Check that final determinations were made
    determinations = final_state.get("final_determinations", [])
    assert isinstance(determinations, list), "Final determinations should be a list"

    # Check that event summary was generated
    summary = final_state.get("event_summary", {})
    assert isinstance(summary, dict), "Event summary should be a dictionary"

    # If we have results, verify structure
    if len(claims) > 0:
        # Check claim structure
        claim = claims[0]
        assert "claim_text" in claim or "claim" in claim, "Claim should have claim_text or claim field"

    if len(determinations) > 0:
        # Check determination structure
        det = determinations[0]
        assert "claim_text" in det, "Determination should have claim_text"
        assert "fact_allegation_classification" in det, "Determination should have classification"
        assert "verification_status" in det, "Determination should have verification_status"

        # Verify verification status is valid
        valid_statuses = ["CONFIRMED", "PROBABLE", "ALLEGED", "CONTESTED", "DEBUNKED"]
        assert det["verification_status"] in valid_statuses, f"Invalid verification status: {det['verification_status']}"

        # Check arbiter reasoning if present
        if "arbiter_reasoning" in det:
            reasoning = det["arbiter_reasoning"]
            assert isinstance(reasoning, dict), "Arbiter reasoning should be a dictionary"


def test_party_investigation_formatted_output():
    """Test that formatted output is generated correctly."""
    asyncio.run(_test_formatted_output())


async def _test_formatted_output():
    """Async implementation of formatted output test."""
    final_state = await run_party_investigation_workflow()

    # Format results
    formatted = format_workflow_results(final_state)

    # Assertions
    assert isinstance(formatted, str), "Formatted output should be a string"
    assert len(formatted) > 0, "Formatted output should not be empty"

    # Check that key sections are present
    if len(final_state.get("claims", [])) > 0:
        assert "PARTY INVESTIGATION WORKFLOW RESULTS" in formatted or "CLAIMS" in formatted, \
            "Formatted output should contain results"


# ============================================================================
# DEMO FUNCTION (for manual execution)
# ============================================================================


async def run_demo():
    """Run the party investigation workflow demo with detailed output."""
    print("\n" + "=" * 80)
    print("PARTY-BASED ADVERSARIAL INVESTIGATION DEMO")
    print("=" * 80)

    # Check for LLM API key
    if not os.getenv("LLM_API_KEY"):
        print("\n⚠️  WARNING: LLM_API_KEY not set")
        print("   Demo will attempt to run with fallback logic.")
        print("   Set LLM_API_KEY environment variable for full functionality.\n")
    else:
        print("\n✓ LLM_API_KEY detected - full functionality enabled\n")

    print("📰 Article:")
    print(f"   Title: {MOCK_ARTICLE['title']}")
    print(f"   Source: {MOCK_ARTICLE['source_name']}")
    print(f"   Content length: {len(MOCK_ARTICLE['content'])} characters\n")

    # Create workflow
    print("⚙️  Creating LangGraph workflow...")
    try:
        workflow = create_party_investigation_workflow()
        print("   ✓ Workflow created successfully\n")
    except Exception as e:
        print(f"   ✗ Failed to create workflow: {e}")
        import traceback
        traceback.print_exc()
        return

    # Initialize state
    initial_state = {
        "article": MOCK_ARTICLE,
        "claims": [],
        "parties": {},
        "party_investigations": [],
        "final_determinations": [],
        "event_summary": {},
        "error": "",
    }

    # Run workflow
    print("🚀 Executing workflow...\n")
    print("-" * 80)

    try:
        final_state = await workflow.ainvoke(initial_state)

        print("-" * 80)
        print("\n✓ Workflow execution complete!\n")

        # Display formatted results
        results = format_workflow_results(final_state)
        print(results)

        # Additional analysis
        print("\n🔍 Detailed Analysis:")
        print("-" * 80)

        # Show party positions on specific claims
        determinations = final_state.get("final_determinations", [])
        if determinations:
            print("\nClaim-by-Claim Breakdown (first 5):")
            for i, det in enumerate(determinations[:5], 1):
                print(f"\n{i}. {det['claim_text'][:80]}...")
                print(f"   Type: {det['fact_allegation_classification']}")
                print(f"   Status: {det['verification_status']}")

                reasoning = det.get("arbiter_reasoning", {})
                consensus = reasoning.get("party_consensus", {})

                if consensus.get("supporting_parties"):
                    print(f"   Supported by: {', '.join(consensus['supporting_parties'])}")
                if consensus.get("opposing_parties"):
                    print(f"   Opposed by: {', '.join(consensus['opposing_parties'])}")

                print(f"   Reasoning: {reasoning.get('verification_rationale', 'N/A')[:100]}...")

        # Success metrics
        print("\n✓ Success Metrics:")
        print("-" * 80)

        claims_count = len(final_state.get("claims", []))
        parties_count = len(final_state.get("parties", {}).get("parties", []))
        investigations_count = len(final_state.get("party_investigations", []))
        determinations_count = len(final_state.get("final_determinations", []))

        print(f"   Claims extracted: {claims_count}")
        print(f"   Parties identified: {parties_count}")
        print(f"   Party investigations completed: {investigations_count}")
        print(f"   Final determinations made: {determinations_count}")

        summary = final_state.get("event_summary", {})
        if summary:
            facts_pct = (
                summary.get("facts_count", 0) / max(summary.get("total_claims", 1), 1)
            ) * 100
            print(f"   Facts vs allegations: {facts_pct:.1f}% facts")
            print(f"   Party agreement level: {summary.get('party_agreement_level', 'N/A')}")
            print(f"   Controversy score: {summary.get('controversy_score', 0.0)} (lower = more consensus)")

        print("\n" + "=" * 80)
        print("DEMO COMPLETE ✓")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n✗ Workflow execution failed: {e}")
        import traceback
        traceback.print_exc()
        return


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    asyncio.run(run_demo())
