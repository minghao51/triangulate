"""Party investigator agent: Analyze claims from a specific party's perspective."""

import logging
from typing import Any
import os

from src.ai.schemas import PartyInvestigationSchema
from src.ai.utils import call_structured_llm, make_agent_envelope

logger = logging.getLogger(__name__)

PARTY_INVESTIGATOR_PROMPT = """You are representing {party_name} in analyzing a news article.

Your task is to investigate claims from {party_name}'s perspective and determine:
1. Which claims you SUPPORT (align with our official position/knowledge)
2. Which claims you CONTEST (disagree with or find inaccurate)
3. What UNIQUE claims you would add (from our perspective not mentioned)

Article:
Title: {article_title}
{article_content}

Claims to analyze:
{claims_formatted}

As {party_name}, analyze each claim and provide your position:

For each claim, determine:
- **SUPPORTS**: This aligns with our official statements, knowledge, or positions
- **CONTESTS**: We disagree with this characterization or have a different view
- **NEUTRAL**: We don't have a position on this or it's not relevant to us

Provide specific evidence, official statements, or reasoning for your positions.

Output format (JSON):
{{
  "claims_supported": [
    {{
      "claim_id": "original_claim_text",
      "claim_text": "the full claim text",
      "position": "SUPPORTS",
      "evidence_from_party": "Official statements, data, or reasoning that supports this",
      "confidence": "HIGH" | "MEDIUM" | "LOW"
    }}
  ],
  "claims_contested": [
    {{
      "claim_id": "original_claim_text",
      "claim_text": "the full claim text",
      "position": "CONTESTS",
      "counter_argument": "Why we disagree or what's inaccurate",
      "alternative_perspective": "Our view on this matter",
      "confidence": "HIGH" | "MEDIUM" | "LOW"
    }}
  ],
  "unique_claims": [
    {{
      "claim_text": "A claim from our perspective not mentioned in the article",
      "confidence": "HIGH" | "MEDIUM" | "LOW",
      "sources": ["Official statement", "Press release", "Government report"]
    }}
  ],
  "party_stance": {{
    "overall_position": "Brief summary of our overall position on the topic",
    "key_concerns": ["concern1", "concern2"],
    "priorities": ["priority1", "priority2"]
  }}
}}

Provide the investigation from {party_name}'s perspective:"""


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

        prompt = PARTY_INVESTIGATOR_PROMPT.format(
            party_name=party_name,
            article_title=article_title,
            article_content=article_content[:2000],  # Limit content length
            claims_formatted=claims_formatted,
        )

        logger.info(
            f"Investigating {len(claims)} claims from {party_name}'s perspective"
        )

        result = await call_structured_llm(
            prompt=prompt,
            schema=PartyInvestigationSchema,
            temperature=0.7,
            max_tokens=2000,
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


def _fallback_investigation(
    party_id: str, party_name: str, claims: list[dict[str, Any]]
) -> dict[str, Any]:
    """Rule-based fallback when LLM unavailable.

    Uses simple keyword matching to determine party positions.

    Args:
        party_id: Party identifier
        party_name: Party canonical name
        claims: List of claim dictionaries

    Returns:
        Dictionary with investigation results
    """
    party_lower = party_name.lower()

    claims_supported = []
    claims_contested = []

    for claim in claims:
        claim_text = claim.get("claim", "").lower()
        who = [w.lower() for w in claim.get("who", [])]

        # If party is mentioned as a subject, they likely support it
        if any(party_lower in w for w in who):
            claims_supported.append(
                {
                    "claim_id": claim_text[:50],
                    "claim_text": claim.get("claim", ""),
                    "position": "SUPPORTS",
                    "evidence_from_party": "Party mentioned in claim (rule-based)",
                    "confidence": "MEDIUM",
                }
            )

        # If party is mentioned but with conflict indicators, they might contest
        elif party_lower in claim_text and any(
            word in claim_text
            for word in ["dispute", "deny", "reject", "oppose", "against"]
        ):
            claims_contested.append(
                {
                    "claim_id": claim_text[:50],
                    "claim_text": claim.get("claim", ""),
                    "position": "CONTESTS",
                    "counter_argument": "Rule-based detection of conflict",
                    "alternative_perspective": "Party may have different view",
                    "confidence": "LOW",
                }
            )

    return {
        "party_id": party_id,
        "party_name": party_name,
        "investigation": {
            "claims_supported": claims_supported,
            "claims_contested": claims_contested,
            "unique_claims": [],
        },
        "party_stance": {
            "overall_position": "Rule-based investigation (LLM unavailable)",
            "key_concerns": [],
            "priorities": [],
        },
    }
