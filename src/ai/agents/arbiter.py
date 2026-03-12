"""Arbiter agent: Review party investigations and make final determinations."""

import logging
from typing import Any
import os

from src.ai.schemas import ArbiterResultSchema
from src.ai.utils import call_structured_llm, make_agent_envelope
from src.ai.agents.fact_allegation_classifier import classify_fact_vs_allegation

logger = logging.getLogger(__name__)

ARBITER_PROMPT = """You are an impartial arbiter analyzing conflicting perspectives on an event.

Your task is to review party investigations and make objective determinations about each claim.

Article:
Title: {article_title}
Source: {source_name}

Original Claims:
{claims_formatted}

Party Investigations:
{investigations_formatted}

For each claim, provide your determination:

1. **Fact vs Allegation Classification**:
   - FACT: Observable event that occurred (past tense, verifiable, timestamped)
   - ALLEGATION: Interpretation, prediction, statement of intent (future tense, subjective)

2. **Verification Status**:
   - CONFIRMED: Verifiable fact, multiple sources, no disputes
   - PROBABLE: Likely true, credible sources, minor disputes
   - ALLEGED: Claim made but not verified, or is opinion
   - CONTESTED: Factual dispute between credible sources
   - DEBUNKED: Proven false

3. **Arbiter Reasoning**:
   - Why is this a FACT or ALLEGATION?
   - What evidence supports this verification status?
   - What is the party consensus (unanimous, divided, conflicting)?

Output format (JSON):
{{
  "final_determinations": [
    {{
      "claim_id": "claim_text_or_id",
      "claim_text": "full claim text",
      "fact_allegation_classification": "FACT" | "ALLEGATION",
      "verification_status": "CONFIRMED" | "PROBABLE" | "ALLEGED" | "CONTESTED" | "DEBUNKED",
      "arbiter_reasoning": {{
        "is_fact": "Explanation of why this is FACT or ALLEGATION",
        "verification_rationale": "Explanation of verification status",
        "party_consensus": {{
          "unanimous": true|false,
          "supporting_parties": ["Party1", "Party2"],
          "opposing_parties": ["Party3"],
          "neutral_parties": ["Party4"]
        }}
      }}
    }}
  ],
  "event_summary": {{
    "total_claims": {total_claims},
    "facts_count": N,
    "allegations_count": N,
    "verification_distribution": {{
      "CONFIRMED": N,
      "PROBABLE": N,
      "ALLEGED": N,
      "CONTESTED": N,
      "DEBUNKED": N
    }},
    "party_agreement_level": "HIGH" | "MEDIUM" | "LOW" | "NONE",
    "controversy_score": 0.0-1.0
  }}
}}

Provide your impartial arbitration:"""


async def arbitrate_findings(
    party_investigations: list[dict[str, Any]],
    original_claims: list[dict[str, Any]],
    article: dict[str, Any],
    *,
    include_metadata: bool = False,
) -> dict[str, Any]:
    """Review all party investigations and make final determinations.

    Args:
        party_investigations: List of party investigation results
        original_claims: List of original claim dictionaries
        article: Article dictionary with title and content

    Returns:
        Dictionary with final_determinations and event_summary
    """
    if not original_claims:
        result = make_agent_envelope(
            {
                "final_determinations": [],
                "event_summary": {
                    "total_claims": 0,
                    "facts_count": 0,
                    "allegations_count": 0,
                    "verification_distribution": {},
                    "party_agreement_level": "NONE",
                    "controversy_score": 0.0,
                },
            }
        )
        return result if include_metadata else result["output"]

    try:
        if not os.getenv("LLM_API_KEY"):
            logger.error("No LLM_API_KEY found")
            result = await _fallback_arbitration(
                party_investigations, original_claims, article
            )
            envelope = make_agent_envelope(
                result,
                parse_status="no_api_key",
                structured_output_used=False,
                fallback_used=True,
            )
            return envelope if include_metadata else result

        # Format claims and investigations for the prompt
        claims_formatted = "\n".join(
            [
                f"{i + 1}. {c.get('claim', '')}"
                for i, c in enumerate(original_claims[:20])  # Limit to 20 claims
            ]
        )

        investigations_formatted = "\n\n".join(
            [
                f"**{inv.get('party_name', 'Unknown')}**:\n"
                f"Position: {inv.get('party_stance', {}).get('overall_position', 'N/A')}\n"
                f"Supports: {len(inv.get('investigation', {}).get('claims_supported', []))} claims\n"
                f"Contests: {len(inv.get('investigation', {}).get('claims_contested', []))} claims"
                for inv in party_investigations[:10]  # Limit to 10 parties
            ]
        )

        article_title = article.get("title", "")
        source_name = article.get("source_name", "")

        prompt = ARBITER_PROMPT.format(
            article_title=article_title,
            source_name=source_name,
            claims_formatted=claims_formatted,
            investigations_formatted=investigations_formatted,
            total_claims=len(original_claims),
        )

        logger.info(
            f"Arbitrating {len(original_claims)} claims based on {len(party_investigations)} party investigations"
        )

        result = await call_structured_llm(
            prompt=prompt,
            schema=ArbiterResultSchema,
            temperature=0.5,
            max_tokens=3000,
            fallback=lambda: {
                "final_determinations": [],
                "event_summary": {
                    "total_claims": len(original_claims),
                    "facts_count": 0,
                    "allegations_count": 0,
                    "verification_distribution": {},
                    "party_agreement_level": "NONE",
                    "controversy_score": 0.0,
                },
            },
        )
        normalized = _normalize_arbiter_result(result["output"], len(original_claims))
        logger.info(
            f"Arbitration complete: "
            f"{normalized['event_summary']['facts_count']} facts, "
            f"{normalized['event_summary']['allegations_count']} allegations, "
            f"agreement level: {normalized['event_summary']['party_agreement_level']}"
        )
        if result["fallback_used"]:
            normalized = await _fallback_arbitration(
                party_investigations, original_claims, article
            )
        result["output"] = normalized
        return result if include_metadata else normalized

    except Exception as e:
        logger.warning(f"LLM arbitration failed: {e}, using fallback")
        result = await _fallback_arbitration(
            party_investigations, original_claims, article
        )
        envelope = make_agent_envelope(
            result,
            parse_status="error",
            structured_output_used=True,
            fallback_used=True,
        )
        return envelope if include_metadata else result


async def _fallback_arbitration(
    party_investigations: list[dict[str, Any]],
    original_claims: list[dict[str, Any]],
    article: dict[str, Any],
) -> dict[str, Any]:
    """Fallback arbitration using rule-based classification.

    Args:
        party_investigations: List of party investigation results
        original_claims: List of original claim dictionaries
        article: Article dictionary

    Returns:
        Dictionary with final_determinations and event_summary
    """
    logger.info("Using rule-based fallback arbitration")

    final_determinations = []
    facts_count = 0
    allegations_count = 0
    verification_distribution = {
        "CONFIRMED": 0,
        "PROBABLE": 0,
        "ALLEGED": 0,
        "CONTESTED": 0,
        "DEBUNKED": 0,
    }

    # Process each claim
    for claim in original_claims:
        claim_text = claim.get("claim", "")

        # Use fact/allegation classifier
        context = {"article": article}
        classification_result = await classify_fact_vs_allegation(
            claim, context, include_metadata=True
        )

        fact_allegation = classification_result["output"].get(
            "classification", "ALLEGATION"
        )

        # Count party positions
        supporting_parties = []
        opposing_parties = []

        for inv in party_investigations:
            party_name = inv.get("party_name", "")
            investigation = inv.get("investigation", {})

            # Check if party supports this claim
            for supported in investigation.get("claims_supported", []):
                if claim_text in supported.get("claim_text", "") or claim_text[
                    :50
                ] in supported.get("claim_id", ""):
                    supporting_parties.append(party_name)

            # Check if party contests this claim
            for contested in investigation.get("claims_contested", []):
                if claim_text in contested.get("claim_text", "") or claim_text[
                    :50
                ] in contested.get("claim_id", ""):
                    opposing_parties.append(party_name)

        # Deduplicate while preserving order
        supporting_parties = list(dict.fromkeys(supporting_parties))
        opposing_parties = list(dict.fromkeys(opposing_parties))
        opposing_parties = [p for p in opposing_parties if p not in supporting_parties]
        all_parties = [
            inv.get("party_name", "")
            for inv in party_investigations
            if inv.get("party_name")
        ]
        neutral_parties = [
            party
            for party in all_parties
            if party not in supporting_parties and party not in opposing_parties
        ]

        # Determine verification status
        unanimous = (
            len(supporting_parties) + len(opposing_parties) > 0
            and len(opposing_parties) == 0
        )

        if fact_allegation == "FACT":
            facts_count += 1
            if unanimous and len(supporting_parties) >= 2:
                verification_status = "CONFIRMED"
            elif len(supporting_parties) > 0:
                verification_status = "PROBABLE"
            else:
                verification_status = "ALLEGED"
        else:  # ALLEGATION
            allegations_count += 1
            if len(opposing_parties) > 0:
                verification_status = "CONTESTED"
            else:
                verification_status = "ALLEGED"

        verification_distribution[verification_status] += 1

        final_determinations.append(
            {
                "claim_id": claim_text[:50],
                "claim_text": claim_text,
                "fact_allegation_classification": fact_allegation,
                "verification_status": verification_status,
                "arbiter_reasoning": {
                    "is_fact": classification_result.get(
                        "output", {}
                    ).get(
                        "reasoning", "Rule-based classification"
                    ),
                    "verification_rationale": f"Based on party consensus: {len(supporting_parties)} support, {len(opposing_parties)} oppose",
                    "party_consensus": {
                        "unanimous": len(opposing_parties) == 0,
                        "supporting_parties": supporting_parties,
                        "opposing_parties": opposing_parties,
                        "neutral_parties": neutral_parties,
                    },
                },
            }
        )

    # Calculate controversy score (0.0 = unanimous, 1.0 = completely contested)
    total_with_positions = sum(
        1
        for det in final_determinations
        if det["arbiter_reasoning"]["party_consensus"]["supporting_parties"]
        or det["arbiter_reasoning"]["party_consensus"]["opposing_parties"]
    )
    contested_count = sum(
        1
        for det in final_determinations
        if det["arbiter_reasoning"]["party_consensus"]["opposing_parties"]
    )
    controversy_score = (
        contested_count / total_with_positions if total_with_positions > 0 else 0.0
    )

    # Determine party agreement level
    if controversy_score < 0.2:
        party_agreement_level = "HIGH"
    elif controversy_score < 0.5:
        party_agreement_level = "MEDIUM"
    elif controversy_score < 0.8:
        party_agreement_level = "LOW"
    else:
        party_agreement_level = "NONE"

    return {
        "final_determinations": final_determinations,
        "event_summary": {
            "total_claims": len(original_claims),
            "facts_count": facts_count,
            "allegations_count": allegations_count,
            "verification_distribution": verification_distribution,
            "party_agreement_level": party_agreement_level,
            "controversy_score": round(controversy_score, 2),
        },
    }


def _normalize_arbiter_result(
    result: dict[str, Any], total_claims: int
) -> dict[str, Any]:
    """Ensure arbiter response has the expected keys and default structure."""

    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _safe_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    final_determinations = result.get("final_determinations", [])
    if not isinstance(final_determinations, list):
        final_determinations = []

    event_summary = result.get("event_summary", {})
    if not isinstance(event_summary, dict):
        event_summary = {}

    verification_distribution = event_summary.get("verification_distribution", {})
    if not isinstance(verification_distribution, dict):
        verification_distribution = {}
    for status in ("CONFIRMED", "PROBABLE", "ALLEGED", "CONTESTED", "DEBUNKED"):
        verification_distribution.setdefault(status, 0)

    normalized_summary = {
        "total_claims": _safe_int(event_summary.get("total_claims"), total_claims),
        "facts_count": _safe_int(event_summary.get("facts_count"), 0),
        "allegations_count": _safe_int(event_summary.get("allegations_count"), 0),
        "verification_distribution": verification_distribution,
        "party_agreement_level": event_summary.get("party_agreement_level", "NONE"),
        "controversy_score": _safe_float(event_summary.get("controversy_score"), 0.0),
    }

    return {
        "final_determinations": final_determinations,
        "event_summary": normalized_summary,
    }
