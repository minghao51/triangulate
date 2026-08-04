"""Party investigator agent: Analyze claims from a specific party's perspective."""

import logging
from typing import Any
import os

from src.ai.prompts import get_prompt
from src.ai.schemas import PartyInvestigationSchema
from src.ai.utils import call_structured_llm, make_agent_envelope
from src.ai.agents._fallback import FallbackEngine

logger = logging.getLogger(__name__)

_fallback_investigation = FallbackEngine.party_position_strategy


async def investigate_from_party_perspective(
    party: dict[str, Any],
    claims: list[dict[str, Any]],
    article: dict[str, Any],
    *,
    include_metadata: bool = False,
) -> dict[str, Any]:
    """Investigate claims from a specific party's perspective.

    Args:
        party: Party dictionary with canonical_name and aliases
        claims: List of claim dictionaries
        article: Article dictionary with title and content

    Returns:
        Dictionary with claims_supported, claims_contested, unique_claims, and party_stance
    """
    party_name = party.get("canonical_name", "Unknown Party")
    party_id = party.get("party_id", party_name)

    if not claims:
        result = make_agent_envelope(
            {
                "party_id": party_id,
                "party_name": party_name,
                "investigation": {
                    "claims_supported": [],
                    "claims_contested": [],
                    "unique_claims": [],
                },
                "party_stance": {
                    "overall_position": "No claims to analyze",
                    "key_concerns": [],
                    "priorities": [],
                },
            }
        )
        return result if include_metadata else result["output"]

    try:
        if not os.getenv("LLM_API_KEY"):
            logger.error("No LLM_API_KEY found")
            result = make_agent_envelope(
                _fallback_investigation(party_id, party_name, claims),
                parse_status="no_api_key",
                structured_output_used=False,
                fallback_used=True,
            )
            return result if include_metadata else result["output"]

        # Format claims for the prompt
        claims_formatted = "\n".join(
            [
                f"{i + 1}. {c.get('claim', '')}"
                for i, c in enumerate(claims[:20])  # Limit to 20 claims
            ]
        )

        article_title = article.get("title", "")
        article_content = article.get("content", "")

        prompt = get_prompt(
            "PARTY_INVESTIGATOR",
            party_name=party_name,
            article_title=article_title,
            article_content=article_content[:2000],
            claims_formatted=claims_formatted,
        )

        logger.info(
            f"Investigating {len(claims)} claims from {party_name}'s perspective"
        )

        result = await call_structured_llm(
            prompt=prompt,
            schema=PartyInvestigationSchema,
            temperature=0.7,
            max_tokens=4000,
            fallback=lambda: _fallback_investigation(party_id, party_name, claims)[
                "investigation"
            ],
        )
        investigation = result["output"]
        enriched = {
            "party_id": party_id,
            "party_name": party_name,
            "investigation": investigation,
            "party_stance": investigation.get("party_stance", {}),
        }
        if include_metadata:
            result["output"] = enriched
            return result
        return enriched

    except Exception as e:
        logger.warning(
            f"LLM investigation failed for {party_name}: {e}, using fallback"
        )
        result = make_agent_envelope(
            _fallback_investigation(party_id, party_name, claims),
            parse_status="error",
            structured_output_used=True,
            fallback_used=True,
        )
        return result if include_metadata else result["output"]
