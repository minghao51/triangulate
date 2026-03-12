"""Party classifier agent: Normalize entity variations into canonical parties."""

import logging
from typing import Any
import os

from src.ai.schemas import PartyClassificationSchema
from src.ai.utils import call_structured_llm, make_agent_envelope

logger = logging.getLogger(__name__)

PARTY_CLASSIFIER_PROMPT = """You are an expert analyst who groups entity variations by the real-world party they represent.

Given this article:
Title: {title}
Summary: {summary_excerpt}

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


async def classify_parties(
    article: dict[str, Any], entities: list[str], *, include_metadata: bool = False
) -> dict[str, Any]:
    """Classify entities into canonical parties using LLM.

    Args:
        article: Article dictionary with title and content
        entities: List of unique entity strings

    Returns:
        Dictionary with "parties" list containing canonical names and aliases
    """
    if not entities:
        result = make_agent_envelope({"parties": []})
        return result if include_metadata else result["output"]

    try:
        if not os.getenv("LLM_API_KEY"):
            logger.error("No LLM_API_KEY found")
            result = make_agent_envelope(
                _fallback_classification(entities),
                parse_status="no_api_key",
                structured_output_used=False,
                fallback_used=True,
            )
            return result if include_metadata else result["output"]

        # Format entities list
        entities_str = ", ".join(entities[:50])  # Limit to 50 entities
        summary_excerpt = article.get("content", "")[:200]

        prompt = PARTY_CLASSIFIER_PROMPT.format(
            title=article.get("title", ""),
            summary_excerpt=summary_excerpt,
            entities=entities_str,
        )

        logger.info(f"Classifying {len(entities)} entities into parties")

        result = await call_structured_llm(
            prompt=prompt,
            schema=PartyClassificationSchema,
            temperature=0.3,
            max_tokens=800,
            fallback=lambda: _fallback_classification(entities),
        )
        logger.info(
            "Classified into %s parties", len(result["output"].get("parties", []))
        )
        return result if include_metadata else result["output"]

    except Exception as e:
        logger.warning(f"LLM party classification failed: {e}, using fallback")
        result = make_agent_envelope(
            _fallback_classification(entities),
            parse_status="error",
            structured_output_used=True,
            fallback_used=True,
        )
        return result if include_metadata else result["output"]


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

        parties.append(
            {
                "canonical_name": entity,
                "aliases": aliases,
                "reasoning": "Rule-based grouping by string similarity",
            }
        )
        used_entities.add(entity)

    return {"parties": parties}
