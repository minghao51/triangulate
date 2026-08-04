"""Narrator agent: Summarize each narrative cluster's stance."""

import logging
from typing import Any
import os
from litellm import acompletion

from src.ai.prompts import get_prompt
from src.ai.schemas import NarrativeSchema
from src.ai.utils import call_structured_llm, make_agent_envelope
from src.ai.agents._fallback import FallbackEngine

logger = logging.getLogger(__name__)

_fallback_narrative = FallbackEngine.narrative_strategy


async def narrate_cluster(
    cluster_id: str, claims: list[dict[str, Any]], *, include_metadata: bool = False
) -> dict[str, Any]:
    """Generate a narrative summary for a cluster of claims.

    Args:
        cluster_id: Cluster identifier
        claims: List of claim dictionaries in this cluster

    Returns:
        Narrative summary dictionary
    """
    if not claims:
        result = make_agent_envelope(
            {
                "stance_summary": "No claims in this cluster",
                "key_themes": [],
                "main_entities": [],
            }
        )
        return result if include_metadata else result["output"]

    try:
        if not os.getenv("LLM_API_KEY"):
            logger.error("No LLM_API_KEY found")
            result = make_agent_envelope(
                _fallback_narrative(claims),
                parse_status="no_api_key",
                structured_output_used=False,
                fallback_used=True,
            )
            return result if include_metadata else result["output"]

        # Format claims for prompt
        claims_text = "\n".join(
            [
                f"- {c.get('claim', '')} (confidence: {c.get('confidence', 'N/A')})"
                for c in claims[:10]  # Limit to 10 claims
            ]
        )

        prompt = get_prompt("NARRATOR", count=len(claims), claims=claims_text)

        logger.info(
            f"Generating narrative for cluster {cluster_id} with {len(claims)} claims"
        )

        result = await call_structured_llm(
            prompt=prompt,
            schema=NarrativeSchema,
            temperature=0.4,
            max_tokens=500,
            fallback=lambda: _fallback_narrative(claims),
            completion_func=acompletion,
        )
        logger.info(f"Generated narrative for cluster {cluster_id}")
        return result if include_metadata else result["output"]

    except Exception as e:
        logger.error(f"Error generating narrative: {e}")
        result = make_agent_envelope(
            _fallback_narrative(claims),
            parse_status="error",
            structured_output_used=True,
            fallback_used=True,
        )
        return result if include_metadata else result["output"]
