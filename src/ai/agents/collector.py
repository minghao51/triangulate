"""Collector agent: Extract factual claims from articles."""
import logging
from typing import Any
import os
from litellm import acompletion

from src.ai.prompts import get_prompt
from src.ai.schemas import ClaimCollectionSchema
from src.ai.utils import call_structured_llm, make_agent_envelope
from src.ai.agents._fallback import FallbackEngine

logger = logging.getLogger(__name__)

_fallback_claims = FallbackEngine.claim_extraction_strategy


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

        prompt = get_prompt(
            "COLLECTOR",
            title=article.get("title", ""),
            content=article.get("content", "")[:5000],
        )

        logger.info(f"Extracting claims from article: {article.get('title', '')[:50]}")

        result = await call_structured_llm(
            prompt=prompt,
            schema=ClaimCollectionSchema,
            temperature=0.3,
            max_tokens=4000,
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
