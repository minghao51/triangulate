"""Shared fallback engine for rule-based agent responses when LLM is unavailable."""

from typing import Any

from src.ai.utils import make_agent_envelope


class FallbackEngine:
    """Provides rule-based fallback strategies for agent responses."""

    @staticmethod
    def claim_extraction_strategy(article: dict[str, Any]) -> list[dict[str, Any]]:
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

    @staticmethod
    def fact_classification_strategy(claim: dict[str, Any]) -> dict[str, Any]:
        """Rule-based fact vs allegation classification."""
        claim_text = claim.get("claim", "").lower()

        allegation_indicators = [
            "will ", "shall ", "pledged", "promised", "plans to", "expects to",
            "should", "could", "would", "might", "may", "believes", "thinks",
            "significant", "important", "historic", "landmark", "praised", "criticized", "condemned",
        ]

        fact_indicators = [
            "was ", "were ", "occurred", "happened", "signed", "announced",
            "agreement was", "meeting was", "summit was", "gathered",
        ]

        allegation_count = sum(
            1 for indicator in allegation_indicators if indicator in claim_text
        )
        fact_count = sum(1 for indicator in fact_indicators if indicator in claim_text)

        if allegation_count > fact_count:
            classification = "ALLEGATION"
            reasoning = "Contains allegation indicators (future tense, opinion, or intent)"
        elif fact_count > 0:
            classification = "FACT"
            reasoning = "Contains factual indicators (past tense, verifiable action)"
        else:
            classification = "ALLEGATION"
            reasoning = "Uncertain - defaulting to ALLEGATION"

        return {
            "claim": claim.get("claim", ""),
            "classification": classification,
            "reasoning": reasoning,
            "confidence": 0.6,
            "indicators": {
                "factual_elements": [ind for ind in fact_indicators if ind in claim_text],
                "allegation_elements": [ind for ind in allegation_indicators if ind in claim_text],
            },
        }

    @staticmethod
    def party_position_strategy(
        party_id: str, party_name: str, claims: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Rule-based party position determination."""
        party_lower = party_name.lower()

        claims_supported = []
        claims_contested = []

        for claim in claims:
            claim_text = claim.get("claim", "").lower()
            who = [w.lower() for w in claim.get("who", [])]

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
            elif party_lower in claim_text and any(
                word in claim_text for word in ["dispute", "deny", "reject", "oppose", "against"]
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

    @staticmethod
    def narrative_strategy(claims: list[dict[str, Any]]) -> dict[str, Any]:
        """Generate a simple narrative summary without LLM."""
        entities = set()
        for claim in claims:
            for entity in claim.get("who", []):
                entities.add(entity)

        return {
            "stance_summary": f"Group of {len(claims)} related claims about {', '.join(list(entities)[:3])}",
            "key_themes": [],
            "main_entities": list(entities)[:5],
        }


def create_fallback_envelope(output: Any, status: str) -> dict[str, Any]:
    """Create a normalized agent result envelope for fallback responses."""
    return make_agent_envelope(
        output,
        parse_status=status,
        structured_output_used=False,
        fallback_used=True,
    )
