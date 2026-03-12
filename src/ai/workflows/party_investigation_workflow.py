"""Party-based adversarial investigation workflow using LangGraph.

This workflow spawns multiple party investigators in parallel, then routes their
findings to an arbiter for final determination.
"""

import logging
from typing import Any, TypedDict, Annotated, Sequence
from operator import add

from langgraph.graph import StateGraph, END

from src.ai.agents.collector import collect_claims
from src.ai.agents.party_classifier import classify_parties
from src.ai.agents.party_investigator import investigate_from_party_perspective
from src.ai.agents.arbiter import arbitrate_findings

logger = logging.getLogger(__name__)


# ============================================================================
# STATE SCHEMA
# ============================================================================


class PartyInvestigationState(TypedDict):
    """State for party-based adversarial investigation workflow."""

    # Input
    article: dict[str, Any]

    # Intermediate state
    claims: Annotated[Sequence[dict[str, Any]], add]  # From Collector
    parties: dict[str, Any]  # From Party Classifier

    # Parallel party investigations
    party_investigations: Annotated[Sequence[dict[str, Any]], add]

    # Arbiter output
    final_determinations: Sequence[dict[str, Any]]
    event_summary: dict[str, Any]
    llm_metadata: dict[str, Any]

    # Metadata
    error: str


# ============================================================================
# WORKFLOW NODES
# ============================================================================


async def collector_node(state: PartyInvestigationState) -> dict[str, Any]:
    """Extract claims from article."""
    logger.info("Executing Collector node...")

    result = await collect_claims(state["article"], include_metadata=True)
    claims = result.get("output", {}).get("claims", [])

    if not claims:
        logger.warning("No claims extracted from article")

    return {
        "claims": list(claims),
        "llm_metadata": {**state.get("llm_metadata", {}), "collector": result},
    }


async def party_classifier_node(state: PartyInvestigationState) -> dict[str, Any]:
    """Identify parties mentioned in the article."""
    logger.info("Executing Party Classifier node...")
    bootstrap_parties = state.get("article", {}).get("confirmed_parties", [])

    # Extract all entities from claims
    entities = set()
    for claim in state.get("claims", []):
        for entity in claim.get("who", []):
            entities.add(entity)

    if bootstrap_parties:
        party_data = {
            "parties": [
                {
                    "canonical_name": party_name,
                    "aliases": [party_name],
                    "reasoning": "Bootstrap-confirmed party",
                }
                for party_name in bootstrap_parties
            ]
        }
        party_result = {
            "output": party_data,
            "parse_status": "bootstrap_override",
            "structured_output_used": False,
            "fallback_used": False,
            "raw_response_excerpt": "",
        }
        return {
            "parties": party_data,
            "llm_metadata": {
                **state.get("llm_metadata", {}),
                "party_classifier": party_result,
            },
        }

    if not entities:
        logger.warning("No entities found in claims")
        return {
            "parties": {"parties": []},
            "llm_metadata": {
                **state.get("llm_metadata", {}),
                "party_classifier": {
                    "output": {"parties": []},
                    "parse_status": "no_entities",
                    "structured_output_used": False,
                    "fallback_used": False,
                    "raw_response_excerpt": "",
                },
            },
        }

    party_result = await classify_parties(
        state["article"], list(entities), include_metadata=True
    )
    party_data = party_result.get("output", {"parties": []})

    logger.info(f"Identified {len(party_data.get('parties', []))} parties")

    return {
        "parties": party_data,
        "llm_metadata": {
            **state.get("llm_metadata", {}),
            "party_classifier": party_result,
        },
    }


async def party_investigators_node(state: PartyInvestigationState) -> dict[str, Any]:
    """Run all party investigations in parallel."""
    parties = state["parties"].get("parties", [])
    claims = state.get("claims", [])
    article = state.get("article", {})

    if not parties:
        logger.info("No parties identified; skipping party investigations")
        return {"party_investigations": []}

    logger.info(f"Running {len(parties)} party investigations in parallel...")

    # Run all investigations concurrently
    import asyncio

    raw_results = await asyncio.gather(
        *[
            investigate_from_party_perspective(
                party, claims, article, include_metadata=True
            )
            for party in parties
        ],
        return_exceptions=True,
    )

    investigations = []
    diagnostics = []
    for party, result in zip(parties, raw_results, strict=False):
        if isinstance(result, Exception):
            party_name = party.get("canonical_name", "Unknown Party")
            logger.warning("Party investigation failed for %s: %s", party_name, result)
            investigations.append(
                {
                    "party_id": party.get("party_id", party_name),
                    "party_name": party_name,
                    "investigation": {
                        "claims_supported": [],
                        "claims_contested": [],
                        "unique_claims": [],
                    },
                    "party_stance": {
                        "overall_position": "Investigation failed",
                        "key_concerns": [],
                        "priorities": [],
                    },
                }
            )
            diagnostics.append(
                {"party_name": party_name, "parse_status": "error", "fallback_used": True}
            )
            continue
        investigations.append(result.get("output", {}))
        diagnostics.append(
            {
                "party_name": result.get("output", {}).get("party_name"),
                "parse_status": result.get("parse_status"),
                "structured_output_used": result.get("structured_output_used"),
                "fallback_used": result.get("fallback_used"),
                "raw_response_excerpt": result.get("raw_response_excerpt"),
            }
        )

    logger.info(f"Completed {len(investigations)} party investigations")

    return {
        "party_investigations": list(investigations),
        "llm_metadata": {
            **state.get("llm_metadata", {}),
            "party_investigators": diagnostics,
        },
    }


async def arbiter_node(state: PartyInvestigationState) -> dict[str, Any]:
    """Arbiter reviews all findings and makes final determinations."""
    logger.info("Executing Arbiter node...")

    findings_result = await arbitrate_findings(
        party_investigations=list(state.get("party_investigations", [])),
        original_claims=list(state.get("claims", [])),
        article=state["article"],
        include_metadata=True,
    )
    findings = findings_result.get("output", {})

    logger.info(
        f"Arbitration complete: "
        f"{findings['event_summary']['facts_count']} facts, "
        f"{findings['event_summary']['allegations_count']} allegations, "
        f"agreement: {findings['event_summary']['party_agreement_level']}"
    )

    return {
        "final_determinations": findings["final_determinations"],
        "event_summary": findings["event_summary"],
        "llm_metadata": {**state.get("llm_metadata", {}), "arbiter": findings_result},
    }


# ============================================================================
# WORKFLOW GRAPH
# ============================================================================


def create_party_investigation_workflow() -> StateGraph:
    """Create multi-agent LangGraph workflow for party-based investigation.

    This workflow:
    1. Collects claims from an article
    2. Identifies parties mentioned in the article
    3. Spawns parallel party investigators (one per party)
    4. Routes all findings to an arbiter for final determination

    Returns:
        Compiled StateGraph ready for execution
    """
    workflow = StateGraph(PartyInvestigationState)

    # Add nodes
    workflow.add_node("collector", collector_node)
    workflow.add_node("party_classifier", party_classifier_node)
    workflow.add_node("party_investigators", party_investigators_node)
    workflow.add_node("arbiter", arbiter_node)

    # Define the flow
    workflow.set_entry_point("collector")

    # Sequential: collector → party_classifier → party_investigators → arbiter → END
    workflow.add_edge("collector", "party_classifier")
    workflow.add_edge("party_classifier", "party_investigators")
    workflow.add_edge("party_investigators", "arbiter")
    workflow.add_edge("arbiter", END)

    # Compile the graph
    app = workflow.compile()

    logger.info("Party investigation workflow created successfully")

    return app


# ============================================================================
# UTILITIES
# ============================================================================


def format_workflow_results(state: dict[str, Any]) -> str:
    """Format workflow results for display.

    Args:
        state: Final state from workflow execution

    Returns:
        Formatted string with key results
    """
    lines = []
    lines.append("=" * 80)
    lines.append("PARTY INVESTIGATION WORKFLOW RESULTS")
    lines.append("=" * 80)

    # Claims
    claims = state.get("claims", [])
    lines.append(f"\n📝 Claims Extracted: {len(claims)}")

    # Parties
    parties = state.get("parties", {}).get("parties", [])
    lines.append(f"\n🎭 Parties Identified: {len(parties)}")
    for party in parties:
        lines.append(f"   - {party.get('canonical_name', 'Unknown')}")

    # Party Investigations
    investigations = state.get("party_investigations", [])
    lines.append(f"\n🔍 Party Investigations: {len(investigations)}")
    for inv in investigations:
        party_name = inv.get("party_name", "Unknown")
        stance = inv.get("party_stance", {}).get("overall_position", "N/A")
        supported = len(inv.get("investigation", {}).get("claims_supported", []))
        contested = len(inv.get("investigation", {}).get("claims_contested", []))
        lines.append(f"   - {party_name}")
        lines.append(f"     Stance: {stance}")
        lines.append(f"     Supports: {supported}, Contests: {contested}")

    # Final Determinations
    determinations = state.get("final_determinations", [])
    lines.append(f"\n⚖️  Final Determinations: {len(determinations)}")
    for det in determinations[:10]:  # Show first 10
        claim_text = det.get("claim_text", "")[:70]
        fact_type = det.get("fact_allegation_classification", "N/A")
        status = det.get("verification_status", "N/A")
        lines.append(f"   [{fact_type}] {status}: {claim_text}...")

    if len(determinations) > 10:
        lines.append(f"   ... and {len(determinations) - 10} more")

    # Event Summary
    summary = state.get("event_summary", {})
    if summary:
        lines.append("\n📊 Event Summary:")
        lines.append(f"   Total Claims: {summary.get('total_claims', 0)}")
        lines.append(f"   Facts: {summary.get('facts_count', 0)}")
        lines.append(f"   Allegations: {summary.get('allegations_count', 0)}")
        lines.append(
            f"   Party Agreement: {summary.get('party_agreement_level', 'N/A')}"
        )
        lines.append(f"   Controversy Score: {summary.get('controversy_score', 0.0)}")

        dist = summary.get("verification_distribution", {})
        if dist:
            lines.append("   Verification Distribution:")
            for status, count in dist.items():
                if count > 0:
                    lines.append(f"     - {status}: {count}")

    lines.append("\n" + "=" * 80)

    return "\n".join(lines)
