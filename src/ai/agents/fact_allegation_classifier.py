"""Fact vs allegation classifier agent: Distinguish objective facts from subjective statements."""

import logging
from typing import Any
import os

from src.ai.schemas import FactAllegationResultSchema
from src.ai.utils import call_structured_llm, make_agent_envelope

logger = logging.getLogger(__name__)

FACT_ALLEGATION_CLASSIFIER_PROMPT = """You are an expert analyst who distinguishes between objective FACTS and subjective ALLEGATIONS.

Given this claim from a news article:
Claim: "{claim}"

Context:
- Article: {article_title}
- Source: {source_name}

Your task:
Classify this claim as either FACT or ALLEGATION based on the following criteria:

**FACT** - Observable events that occurred:
- Past tense actions that were completed
- Verifiable occurrences with specific dates/times
- Official announcements or signed agreements
- Events that can be independently verified
- Examples: "The summit was held in Geneva", "195 countries signed the agreement"

**ALLEGATION** - Interpretations, predictions, statements of intent:
- Future tense statements (pledges, promises, plans)
- Opinions, interpretations, or subjective judgments
- Statements of intent that may not be fulfilled
- Predictions or projections
- Examples: "China pledged to meet targets", "Most significant climate action", "Environmental groups praised"

Output format (JSON):
{{
  "claim": "{claim}",
  "classification": "FACT" | "ALLEGATION",
  "reasoning": "Brief explanation of why this is a FACT or ALLEGATION",
  "confidence": 0.0-1.0,
  "indicators": {{
    "factual_elements": ["element1", "element2"],
    "allegation_elements": ["element1", "element2"]
  }}
}}

Provide the classification:"""


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

        prompt = FACT_ALLEGATION_CLASSIFIER_PROMPT.format(
            claim=claim_text, article_title=article_title, source_name=source_name
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


def _fallback_classification(claim: dict[str, Any]) -> dict[str, Any]:
    """Rule-based fallback when LLM unavailable.

    Uses simple keyword and tense analysis.

    Args:
        claim: Claim dictionary

    Returns:
        Dictionary with classification result
    """
    claim_text = claim.get("claim", "").lower()

    # Indicators of allegations (future tense, intent, opinion)
    allegation_indicators = [
        "will ",
        "shall ",
        "pledged",
        "promised",
        "plans to",
        "expects to",
        "should",
        "could",
        "would",
        "might",
        "may",
        "believes",
        "thinks",
        "significant",
        "important",
        "historic",
        "landmark",  # subjective adjectives
        "praised",
        "criticized",
        "condemned",  # reactions
    ]

    # Indicators of facts (past tense, verifiable)
    fact_indicators = [
        "was ",
        "were ",
        "occurred",
        "happened",
        "signed",
        "announced",
        "agreement was",
        "meeting was",
        "summit was",
        "gathered",
    ]

    # Check indicators
    allegation_count = sum(
        1 for indicator in allegation_indicators if indicator in claim_text
    )
    fact_count = sum(1 for indicator in fact_indicators if indicator in claim_text)

    classification = "FACT"
    reasoning = "Rule-based classification"

    if allegation_count > fact_count:
        classification = "ALLEGATION"
        reasoning = "Contains allegation indicators (future tense, opinion, or intent)"
    elif fact_count > 0:
        classification = "FACT"
        reasoning = "Contains factual indicators (past tense, verifiable action)"
    else:
        # Default to allegation when uncertain
        classification = "ALLEGATION"
        reasoning = "Uncertain - defaulting to ALLEGATION"

    return {
        "claim": claim.get("claim", ""),
        "classification": classification,
        "reasoning": reasoning,
        "confidence": 0.6,
        "indicators": {
            "factual_elements": [ind for ind in fact_indicators if ind in claim_text],
            "allegation_elements": [
                ind for ind in allegation_indicators if ind in claim_text
            ],
        },
    }
