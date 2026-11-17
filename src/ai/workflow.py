"""AI workflow orchestration using LangGraph."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any
from src.ai.agents.collector import collect_claims
from src.ai.agents.clusterer import cluster_claims
from src.ai.agents.narrator import narrate_cluster
from src.ai.agents.classifier import classify_verification, classify_event_verification
from src.ai.agents.party_classifier import classify_parties
from src.ai.geocoder import geocode_with_retry
from src.ai.schemas import ExtractionOutcomeSchema

logger = logging.getLogger(__name__)

# Envelope keys copied verbatim into ``llm_metadata`` entries.
_AGENT_METADATA_KEYS = (
    "parse_status",
    "structured_output_used",
    "fallback_used",
    "raw_response_excerpt",
)


def _collector_metadata(collector_result: dict[str, Any]) -> dict[str, Any]:
    """Return the legacy four-key collector metadata block."""
    return {key: collector_result.get(key) for key in _AGENT_METADATA_KEYS}


def _collector_outcome(
    collector_result: dict[str, Any], claims: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return the collector's honest extraction outcome for this article.

    The collector records ``extraction_outcome`` on its envelope. When a caller
    or test bypasses the collector and hands back a raw claim list
    (``_normalize_agent_result`` compat path) nothing proves the collector ever
    saw the article body, so the derived outcome is deliberately conservative:
    no scope, no trusted quote proposals.
    """
    outcome = collector_result.get("extraction_outcome")
    if isinstance(outcome, dict):
        return dict(outcome)
    return ExtractionOutcomeSchema(
        status="valid" if claims else "unavailable",
        quote_proposals_trusted=False,
        scope_start=0,
        scope_end=0,
        body_char_count=0,
        input_limit=0,
        source_available=False,
        reason="compat_collector_result",
    ).model_dump()


def _normalize_agent_result(
    result: Any, default_key: str | None = None
) -> dict[str, Any]:
    if isinstance(result, dict) and "output" in result:
        return result
    if default_key is None:
        payload = result if isinstance(result, dict) else {}
    else:
        payload = result if isinstance(result, dict) else {default_key: result}
        if not isinstance(result, dict):
            payload = {default_key: result}
    return {
        "output": payload,
        "parse_status": "compat_raw",
        "structured_output_used": False,
        "fallback_used": False,
        "raw_response_excerpt": "",
    }


def _extract_location(event_data: dict[str, Any], article: dict[str, Any]) -> dict[str, Any]:
    where_text = ""
    for claim in event_data.get("claims", []):
        claim_where = claim.get("where", "").strip()
        if claim_where and len(claim_where) > 2:
            where_text = claim_where
            break
    if not where_text:
        source_metadata = article.get("source_metadata", {})
        country = source_metadata.get("country", "").strip()
        if country:
            where_text = country
    if where_text:
        geo_result = geocode_with_retry(where_text)
        if geo_result:
            event_data["location_country_code"] = geo_result.country_code
            event_data["location_lat"] = geo_result.lat
            event_data["location_lon"] = geo_result.lon
    if "location_country_code" not in event_data:
        event_data["location_country_code"] = None
        event_data["location_lat"] = None
        event_data["location_lon"] = None
    return event_data


class AIWorkflow:
    """Orchestrate the multi-agent AI pipeline."""

    def __init__(self, config: dict):
        """Initialize AI workflow.

        Args:
            config: Configuration dictionary
        """
        self.config = config

    async def process_article(self, article: dict[str, Any]) -> dict[str, Any] | None:
        """Process an article through the full AI pipeline.

        Args:
            article: Article dictionary

        Returns:
            Processed event data with claims and narratives
        """
        logger.info(f"Processing article: {article.get('title', '')[:50]}")

        # Step 1: Extract claims
        collector_result = _normalize_agent_result(
            await collect_claims(article, include_metadata=True), "claims"
        )
        claims = collector_result.get("output", {}).get("claims", [])
        collector_meta = collector_result
        extraction_outcome = _collector_outcome(collector_result, claims)

        if not claims:
            # A validated explicit empty collection is a real result: report an
            # honest zero-claim event instead of overloading ``None``. Fallback
            # and unavailable extraction stay failures, exactly as before.
            if extraction_outcome.get("status") == "empty":
                logger.warning(
                    "Collector returned a validated empty claim collection for "
                    "article: %s",
                    article.get("title", "")[:50],
                )
                return {
                    "id": str(uuid.uuid4()),
                    "timestamp": article.get("timestamp", datetime.now(UTC)),
                    "title": article.get("title", ""),
                    "summary": (article.get("content") or "")[:500],
                    "verification_status": "ALLEGED",
                    "claims": [],
                    "narratives": [],
                    "parties": [],
                    "source_url": article.get("link", ""),
                    "source_name": article.get("source_name", "unknown"),
                    "location_country_code": None,
                    "location_lat": None,
                    "location_lon": None,
                    "llm_metadata": {
                        "collector": {
                            **_collector_metadata(collector_meta),
                            "extraction_outcome": extraction_outcome,
                        },
                    },
                    "extraction_outcome": extraction_outcome,
                }
            logger.warning("No claims extracted from article")
            return None

        # Step 2: Classify parties
        # Extract all unique entities
        all_entities = set()
        for claim in claims:
            all_entities.update(claim.get("who", []))

        # Run party classifier
        bootstrap_parties = article.get("confirmed_parties", [])
        if bootstrap_parties:
            party_data = {
                "parties": [
                    {
                        "canonical_name": party_name,
                        "aliases": [party_name],
                        "reasoning": "Bootstrap-confirmed party",
                    }
                    for party_name in bootstrap_parties
                ]
            }
            party_classifier_result = {
                "output": party_data,
                "parse_status": "bootstrap_override",
                "structured_output_used": False,
                "fallback_used": False,
                "raw_response_excerpt": "",
            }
        else:
            party_classifier_result = _normalize_agent_result(
                await classify_parties(
                    article, list(all_entities), include_metadata=True
                )
            )
            party_data = party_classifier_result.get("output", {"parties": []})

        # Step 3: Normalize claims with party information
        # Create simple entity -> canonical name mapping
        entity_to_party = {}
        for party in party_data.get("parties", []):
            canonical = party["canonical_name"]
            for alias in party["aliases"]:
                entity_to_party[alias] = canonical
            entity_to_party[canonical] = canonical

        # Add party_name to claims (we'll add party_id after DB persistence)
        for claim in claims:
            if claim.get("who"):
                # Use first entity's party as representative
                primary_entity = claim["who"][0]
                claim["party_name"] = entity_to_party.get(primary_entity)

        # Step 4: Cluster claims by narrative
        clustering_result = await cluster_claims(claims, n_clusters=3)

        # Step 5: Generate narrative summaries
        narratives = []
        for cluster_id, claims_in_cluster in clustering_result.get(
            "clusters", {}
        ).items():
            narrative_result = _normalize_agent_result(
                await narrate_cluster(
                    cluster_id, claims_in_cluster, include_metadata=True
                )
            )
            narrative = narrative_result.get("output", {})
            narrative["cluster_id"] = cluster_id
            narrative["claim_count"] = len(claims_in_cluster)
            narrative["source_count"] = 1 if claims_in_cluster else 0
            narrative["llm_metadata"] = {
                key: narrative_result.get(key)
                for key in (
                    "parse_status",
                    "structured_output_used",
                    "fallback_used",
                    "raw_response_excerpt",
                )
            }
            narratives.append(narrative)

        # Step 6: Classify verification status
        for claim in claims:
            claim["verification_status"] = classify_verification(
                claim,
                source_count=1,  # Will be updated after cross-source analysis
            )

        # Classify event verification
        event_verification = classify_event_verification(
            claims, narrative_count=len(narratives)
        )

        # Create event data
        event_data = {
            "id": str(uuid.uuid4()),
            "timestamp": article.get("timestamp", datetime.now(UTC)),
            "title": article.get("title", ""),
            "summary": article.get("content", "")[:500],
            "verification_status": event_verification,
            "claims": claims,
            "narratives": narratives,
            "parties": party_data.get("parties", []),  # NEW
            "source_url": article.get("link", ""),
            "source_name": article.get("source_name", "unknown"),
            "llm_metadata": {
                "collector": {
                    **_collector_metadata(collector_meta),
                    "extraction_outcome": extraction_outcome,
                },
                "party_classifier": {
                    key: party_classifier_result.get(key)
                    for key in _AGENT_METADATA_KEYS
                },
                "narrator": [
                    narrative.get("llm_metadata", {}) for narrative in narratives
                ],
            },
            "extraction_outcome": extraction_outcome,
        }

        event_data = _extract_location(event_data, article)

        logger.info(
            f"Processed article into event with {len(claims)} claims, "
            f"{len(narratives)} narratives, {len(party_data.get('parties', []))} parties"
        )

        return event_data

    async def process_articles(
        self, articles: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Process multiple articles through the AI pipeline.

        Args:
            articles: List of article dictionaries

        Returns:
            List of processed event data
        """
        logger.info(f"Processing {len(articles)} articles")

        events = []
        for article in articles:
            try:
                event = await self.process_article(article)
                if event:
                    events.append(event)
            except Exception as e:
                logger.error(f"Error processing article: {e}")
                continue

        logger.info(f"Successfully processed {len(events)} articles")
        return events
