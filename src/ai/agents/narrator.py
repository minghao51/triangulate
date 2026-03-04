"""Narrator agent: Summarize each narrative cluster's stance."""

import logging
from typing import Any
from litellm import acompletion
import os
import json

from src.ai.utils import call_with_retry, build_completion_params

logger = logging.getLogger(__name__)

NARRATOR_PROMPT = """You are an expert analyst who summarizes the stance and perspective of groups of related claims.

Below are {count} factual claims that have been grouped together because they express a similar narrative perspective:

{claims}

Your task:
1. Identify the common theme or perspective these claims share
2. Summarize what this narrative stance is asserting
3. Note key entities, events, or positions involved
4. Keep your summary concise (2-3 sentences)

Output format (JSON):
{{
  "stance_summary": "Brief summary of this narrative's perspective",
  "key_themes": ["theme1", "theme2"],
  "main_entities": ["entity1", "entity2"]
}}

Provide the narrative summary:"""


async def narrate_cluster(
    cluster_id: str, claims: list[dict[str, Any]]
) -> dict[str, Any]:
    """Generate a narrative summary for a cluster of claims.

    Args:
        cluster_id: Cluster identifier
        claims: List of claim dictionaries in this cluster

    Returns:
        Narrative summary dictionary
    """
    if not claims:
        return {
            "stance_summary": "No claims in this cluster",
            "key_themes": [],
            "main_entities": [],
        }

    try:
        if not os.getenv("LLM_API_KEY"):
            logger.error("No LLM_API_KEY found")
            return _fallback_narrative(claims)

        # Format claims for prompt
        claims_text = "\n".join(
            [
                f"- {c.get('claim', '')} (confidence: {c.get('confidence', 'N/A')})"
                for c in claims[:10]  # Limit to 10 claims
            ]
        )

        prompt = NARRATOR_PROMPT.format(count=len(claims), claims=claims_text)

        logger.info(
            f"Generating narrative for cluster {cluster_id} with {len(claims)} claims"
        )

        # Build completion parameters with retry logic
        params = build_completion_params(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=500,
        )

        # Call with retry for rate limiting and error handling
        response = await call_with_retry(acompletion, **params)

        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Parse JSON response
        try:
            narrative = json.loads(content)
            logger.info(f"Generated narrative for cluster {cluster_id}")
            return narrative
        except json.JSONDecodeError:
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
                narrative = json.loads(json_str)
                return narrative
            logger.error(f"Failed to parse narrative JSON: {content[:200]}")
            return _fallback_narrative(claims)

    except Exception as e:
        logger.error(f"Error generating narrative: {e}")
        return _fallback_narrative(claims)


def _fallback_narrative(claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate a simple summary without LLM.

    Args:
        claims: List of claim dictionaries

    Returns:
        Simple narrative summary
    """
    # Extract entities and themes from claims
    entities = set()
    for claim in claims:
        for entity in claim.get("who", []):
            entities.add(entity)

    return {
        "stance_summary": f"Group of {len(claims)} related claims about {', '.join(list(entities)[:3])}",
        "key_themes": [],
        "main_entities": list(entities)[:5],
    }
