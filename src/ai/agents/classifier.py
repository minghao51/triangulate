"""Classifier agent: Assign verification status to claims."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def classify_verification(
    claim: dict[str, Any], source_count: int, cross_source_corroboration: float = 0.0
) -> str:
    """Assign verification status based on claim characteristics.

    Args:
        claim: Claim dictionary with metadata
        source_count: Number of sources that corroborate this claim
        cross_source_corroboration: Ratio of sources that agree (0-1)

    Returns:
        Verification status (CONFIRMED, PROBABLE, ALLEGED, CONTESTED, DEBUNKED)
    """
    confidence = claim.get("confidence", "MEDIUM").upper()

    # Base classification on confidence level
    if confidence == "HIGH" and source_count >= 2:
        return "CONFIRMED"
    elif confidence == "HIGH" and source_count == 1:
        return "PROBABLE"
    elif confidence == "MEDIUM" and source_count >= 2:
        return "PROBABLE"
    elif confidence == "MEDIUM" and source_count == 1:
        return "ALLEGED"
    elif confidence == "LOW":
        return "ALLEGED"
    else:
        return "ALLEGED"


def classify_event_verification(
    claims: list[dict[str, Any]], narrative_count: int
) -> str:
    """Assign verification status to an event based on its claims.

    Args:
        claims: List of claim dictionaries
        narrative_count: Number of distinct narrative clusters

    Returns:
        Event verification status
    """
    if not claims:
        return "ALLEGED"

    # Count verification statuses of claims
    status_counts = {}
    for claim in claims:
        status = claim.get("verification_status", "ALLEGED")
        status_counts[status] = status_counts.get(status, 0) + 1

    # Determine overall status
    confirmed = status_counts.get("CONFIRMED", 0)
    probable = status_counts.get("PROBABLE", 0)
    contested = status_counts.get("CONTESTED", 0)

    total = len(claims)

    # If there's significant disagreement
    if contested > total / 3:
        return "CONTESTED"

    # If multiple narratives exist without agreement
    if narrative_count > 2 and confirmed == 0:
        return "CONTESTED"

    # Strong corroboration
    if confirmed > total / 2:
        return "CONFIRMED"

    # Good corroboration
    if (confirmed + probable) > total / 2:
        return "PROBABLE"

    # Default to alleged
    return "ALLEGED"
