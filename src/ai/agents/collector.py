"""Collector agent: Extract factual claims from articles."""

import logging
from typing import Any
from litellm import acompletion
import os
import json

from src.ai.utils import call_with_retry, build_completion_params

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


async def collect_claims(article: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract claims from an article using LLM.

    Args:
        article: Article dictionary with title and content

    Returns:
        List of extracted claim dictionaries
    """
    try:
        if not os.getenv("LLM_API_KEY"):
            logger.error("No LLM_API_KEY found")
            return []

        prompt = COLLECTOR_PROMPT.format(
            title=article.get("title", ""),
            content=article.get("content", "")[:5000],  # Limit content length
        )

        logger.info(f"Extracting claims from article: {article.get('title', '')[:50]}")

        # Build completion parameters with retry logic
        params = build_completion_params(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )

        # Call with retry for rate limiting and error handling
        response = await call_with_retry(acompletion, **params)

        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Parse JSON response
        try:
            claims = json.loads(content)
            if isinstance(claims, list):
                logger.info(f"Extracted {len(claims)} claims")
                return claims
            else:
                logger.warning("LLM response is not a list")
                return []
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
                claims = json.loads(json_str)
                if isinstance(claims, list):
                    logger.info(f"Extracted {len(claims)} claims from markdown")
                    return claims
            logger.error(f"Failed to parse LLM response as JSON: {content[:200]}")
            return []

    except Exception as e:
        logger.error(f"Error extracting claims: {e}")
        return []
