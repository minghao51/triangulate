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

logger = logging.getLogger(__name__)


class AIWorkflow:
    """Orchestrate the multi-agent AI pipeline."""

    def __init__(self, config: dict):
        """Initialize AI workflow.

        Args:
            config: Configuration dictionary
        """
        self.config = config

    async def process_article(self, article: dict[str, Any]) -> dict[str, Any]:
        """Process an article through the full AI pipeline.

        Args:
            article: Article dictionary

        Returns:
            Processed event data with claims and narratives
        """
        logger.info(f"Processing article: {article.get('title', '')[:50]}")

        # Step 1: Extract claims
        claims = await collect_claims(article)

        if not claims:
            logger.warning("No claims extracted from article")
            return None

        # Step 2: Classify parties
        # Extract all unique entities
        all_entities = set()
        for claim in claims:
            all_entities.update(claim.get("who", []))

        # Run party classifier
        party_data = await classify_parties(article, list(all_entities))

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
            narrative = await narrate_cluster(cluster_id, claims_in_cluster)
            narrative["cluster_id"] = cluster_id
            narrative["claim_count"] = len(claims_in_cluster)
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
        }

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
