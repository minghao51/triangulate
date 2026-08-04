"""Shared utilities for AI workflows."""

from typing import Any


def build_bootstrap_parties_result(
    party_names: list[str],
) -> dict[str, Any]:
    """Build a standardized bootstrap parties result.

    Used when parties are pre-confirmed and don't need LLM classification.

    Args:
        party_names: List of confirmed party names

    Returns:
        Dictionary with parties data and metadata envelope
    """
    return {
        "parties": [
            {
                "canonical_name": party_name,
                "aliases": [party_name],
                "reasoning": "Bootstrap-confirmed party",
            }
            for party_name in party_names
        ]
    }


def build_bootstrap_envelope() -> dict[str, Any]:
    """Build a standardized envelope for bootstrap override results."""
    return {
        "output": None,
        "parse_status": "bootstrap_override",
        "structured_output_used": False,
        "fallback_used": False,
        "raw_response_excerpt": "",
    }
