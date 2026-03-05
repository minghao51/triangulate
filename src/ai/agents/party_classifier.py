"""Party classifier agent: Normalize entity variations into canonical parties."""

import logging
from typing import Any
from litellm import acompletion
import json
import os

from src.ai.utils import call_with_retry, build_completion_params

logger = logging.getLogger(__name__)

PARTY_CLASSIFIER_PROMPT = """You are an expert analyst who groups entity variations by the real-world party they represent.

Given this article:
Title: {title}
Summary: {summary[:200]}

Extracted entities from the article: {entities}

Your task:
1. Group these entities by the real-world party they represent
2. For each group, provide a canonical name and list all aliases
3. Consider that leaders/administrations represent their countries (e.g., "Trump" → United States)
4. Keep canonical names formal (e.g., "United States" not "USA")

Output format (JSON):
{{
  "parties": [
    {{
      "canonical_name": "Formal Party Name",
      "aliases": ["entity1", "entity2", "entity3"],
      "reasoning": "Brief explanation of grouping"
    }}
  ]
}}

Provide the party classification:"""


async def classify_parties(article: dict[str, Any], entities: list[str]) -> dict[str, Any]:
    """Classify entities into canonical parties using LLM.

    Args:
        article: Article dictionary with title and content
        entities: List of unique entity strings

    Returns:
        Dictionary with "parties" list containing canonical names and aliases
    """
    if not entities:
        return {"parties": []}

    try:
        if not os.getenv("LLM_API_KEY"):
            logger.error("No LLM_API_KEY found")
            return _fallback_classification(entities)

        # Format entities list
        entities_str = ", ".join(entities[:50])  # Limit to 50 entities

        prompt = PARTY_CLASSIFIER_PROMPT.format(
            title=article.get("title", ""),
            summary=article.get("content", ""),
            entities=entities_str
        )

        logger.info(f"Classifying {len(entities)} entities into parties")

        # Build completion parameters
        params = build_completion_params(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
        )

        # Call LLM with retry
        response = await call_with_retry(acompletion, **params)

        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Parse JSON response
        try:
            result = json.loads(content)
            logger.info(f"Classified into {len(result.get('parties', []))} parties")
            return result
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
                result = json.loads(json_str)
                return result
            logger.error(f"Failed to parse party classification JSON: {content[:200]}")
            return _fallback_classification(entities)

    except Exception as e:
        logger.warning(f"LLM party classification failed: {e}, using fallback")
        return _fallback_classification(entities)


def _fallback_classification(entities: list[str]) -> dict[str, Any]:
    """Rule-based fallback when LLM unavailable.

    Groups entities by simple string similarity.

    Args:
        entities: List of entity strings

    Returns:
        Dictionary with "parties" list
    """
    parties = []
    used_entities = set()

    for entity in sorted(entities):
        if entity.lower() in [e.lower() for e in used_entities]:
            continue

        # Find similar entities (case-insensitive substring match)
        aliases = [entity]
        entity_lower = entity.lower()

        for other in sorted(entities):
            if other.lower() == entity_lower:
                continue
            if other.lower() in entity_lower or entity_lower in other.lower():
                if len(aliases) < 10:  # Limit group size
                    aliases.append(other)
                    used_entities.add(other)

        parties.append({
            "canonical_name": entity,
            "aliases": aliases,
            "reasoning": "Rule-based grouping by string similarity"
        })
        used_entities.add(entity)

    return {"parties": parties}
