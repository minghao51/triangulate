"""Collector agent: Extract factual claims from articles."""

import logging
from typing import Any
import os
from litellm import acompletion

from src.ai.schemas import ClaimCollectionSchema
from src.ai.utils import call_structured_llm, make_agent_envelope

logger = logging.getLogger(__name__)

COLLECTOR_PROMPT = """You are an expert analyst specializing in extracting factual claims from news articles.

Your task is to read an article and extract discrete, verifiable factual claims.

For each claim, extract:
1. The claim text (what is being asserted)
2. Who/what is involved (people, organizations, entities)
3. When it happened (timestamp or date)
4. Where it happened (location)
5. Confidence level (HIGH/MEDIUM/LOW based on source specificity)

Guidelines:
- Focus on objective facts, not opinions or predictions
- Extract multiple claims if they exist
- Be specific with names, dates, and locations
- If a claim is vague, assign LOW confidence
- Output as JSON array of claims

Article to analyze:
{title}

{content}

Output format (JSON array):
[
  {{
    "claim": "Specific factual assertion",
    "who": ["Entity1", "Entity2"],
    "when": "Date or time description",
    "where": "Location",
    "confidence": "HIGH|MEDIUM|LOW"
  }}
]

Extract claims:"""


async def collect_claims(
    article: dict[str, Any], *, include_metadata: bool = False
) -> list[dict[str, Any]] | dict[str, Any]:
    """Extract claims from an article using LLM.

    Args:
        article: Article dictionary with title and content

    Returns:
        List of extracted claim dictionaries
    """
    try:
        if not os.getenv("LLM_API_KEY"):
            logger.error("No LLM_API_KEY found")
            result = make_agent_envelope(
                {"claims": _fallback_claims(article)},
                parse_status="no_api_key",
                structured_output_used=False,
                fallback_used=True,
            )
            return result if include_metadata else []

        prompt = COLLECTOR_PROMPT.format(
            title=article.get("title", ""),
            content=article.get("content", "")[:5000],  # Limit content length
        )

        logger.info(f"Extracting claims from article: {article.get('title', '')[:50]}")

        result = await call_structured_llm(
            prompt=prompt,
            schema=ClaimCollectionSchema,
            temperature=0.3,
            max_tokens=2000,
            fallback=lambda: {"claims": _fallback_claims(article)},
            completion_func=acompletion,
        )
        claims = result["output"].get("claims", [])
        logger.info("Extracted %s claims", len(claims))
        if result.get("fallback_used") and not include_metadata and not result.get(
            "raw_response_excerpt"
        ):
            return []
        return result if include_metadata else claims
    except Exception as e:
        logger.error(f"Error extracting claims: {e}")
        result = make_agent_envelope(
            {"claims": _fallback_claims(article)},
            parse_status="error",
            structured_output_used=True,
            fallback_used=True,
        )
        return result if include_metadata else []


def _fallback_claims(article: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract coarse claims from article text without an LLM."""
    content = " ".join(
        part.strip()
        for part in [article.get("title", ""), article.get("content", "")]
        if part
    )
    sentences = [
        sentence.strip(" -\n\t")
        for sentence in content.replace("\n", " ").split(".")
        if sentence.strip()
    ]
    claims = []
    for sentence in sentences[:5]:
        if len(sentence) < 8:
            continue
        claims.append(
            {
                "claim": sentence,
                "who": [],
                "when": "",
                "where": "",
                "confidence": "LOW",
            }
        )
    return claims[:3]
