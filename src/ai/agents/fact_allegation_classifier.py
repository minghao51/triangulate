"""Fact vs allegation classifier agent: Distinguish objective facts from subjective statements."""

import logging
from typing import Any
import os

from src.ai.prompts import get_prompt
from src.ai.schemas import FactAllegationResultSchema
from src.ai.utils import call_structured_llm, make_agent_envelope
from src.ai.agents._fallback import FallbackEngine

logger = logging.getLogger(__name__)

_fallback_classification = FallbackEngine.fact_classification_strategy


async def classify_fact_vs_allegation(
    claim: dict[str, Any], context: dict[str, Any], *, include_metadata: bool = False
) -> dict[str, Any]:
    """Classify a claim as FACT or ALLEGATION.

    Args:
        claim: Claim dictionary with "claim" field containing the claim text
        context: Context dictionary with article title and source name

    Returns:
        Dictionary with classification, reasoning, confidence, and indicators
    """
    claim_text = claim.get("claim", "")

    if not claim_text:
        result = make_agent_envelope(
            {
                "claim": "",
                "classification": "ALLEGATION",
                "reasoning": "Empty claim",
                "confidence": 0.0,
                "indicators": {"factual_elements": [], "allegation_elements": []},
            }
        )
        return result if include_metadata else result["output"]

    try:
        if not os.getenv("LLM_API_KEY"):
            logger.error("No LLM_API_KEY found")
            result = make_agent_envelope(
                _fallback_classification(claim),
                parse_status="no_api_key",
                structured_output_used=False,
                fallback_used=True,
            )
            return result if include_metadata else result["output"]

        article_title = context.get("article", {}).get("title", "")
        source_name = context.get("article", {}).get("source_name", "")

        prompt = get_prompt(
            "FACT_ALLEGATION_CLASSIFIER",
            claim=claim_text,
            article_title=article_title,
            source_name=source_name,
        )

        logger.info(f"Classifying claim as FACT or ALLEGATION: {claim_text[:60]}...")

        result = await call_structured_llm(
            prompt=prompt,
            schema=FactAllegationResultSchema,
            temperature=0.3,
            max_tokens=500,
            fallback=lambda: _fallback_classification(claim),
        )
        logger.info(
            "Classified as %s with confidence %s",
            result["output"].get("classification"),
            result["output"].get("confidence", 0.0),
        )
        return result if include_metadata else result["output"]

    except Exception as e:
        logger.warning(f"LLM classification failed: {e}, using fallback")
        result = make_agent_envelope(
            _fallback_classification(claim),
            parse_status="error",
            structured_output_used=True,
            fallback_used=True,
        )
        return result if include_metadata else result["output"]
