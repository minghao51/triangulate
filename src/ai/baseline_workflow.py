"""AI workflow orchestration using LangGraph."""

import logging
import time
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, NamedTuple

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

from src.ai.agents.collector import collect_claims
from src.ai.agents.clusterer import cluster_claims
from src.ai.agents.narrator import narrate_cluster
from src.ai.agents.classifier import classify_verification, classify_event_verification
from src.ai.agents.party_classifier import classify_parties

logger = logging.getLogger(__name__)


class GeoResult(NamedTuple):
    country_code: str
    lat: float
    lon: float


_geolocator: Nominatim | None = None


def _get_geolocator() -> Nominatim:
    global _geolocator
    if _geolocator is None:
        _geolocator = Nominatim(user_agent="triangulate-investigation-toolkit")
    return _geolocator


@lru_cache(maxsize=1000)
def _geocode_location(location_text: str) -> GeoResult | None:
    if not location_text or not location_text.strip():
        return None

    location_text = location_text.strip()
    geolocator = _get_geolocator()

    try:
        location = geolocator.geocode(location_text, language="en", timeout=10)
        if location:
            address = location.raw.get("address", {})
            country_code = address.get("country_code", "").upper()
            if not country_code:
                country_code = _infer_country_code(address, location_text)
            return GeoResult(
                country_code=country_code,
                lat=location.latitude,
                lon=location.longitude,
            )
    except GeocoderTimedOut:
        logger.warning(f"Geocoding timeout for: {location_text}")
    except GeocoderServiceError as e:
        logger.warning(f"Geocoding service error for '{location_text}': {e}")
    except Exception as e:
        logger.warning(f"Geocoding failed for '{location_text}': {e}")

    return None


def _geocode_with_retry(location_text: str, retries: int = 2, delay: float = 1.5) -> GeoResult | None:
    for attempt in range(retries):
        result = _geocode_location(location_text)
        if result:
            return result
        if attempt < retries - 1:
            time.sleep(delay)
    return None


def _infer_country_code(address: dict, location_text: str = "") -> str:
    country = address.get("country", "")
    country_code = address.get("country_code", "").upper()
    if country_code:
        return country_code
    location_text_lower = location_text.lower()
    country_to_code = {
        "gaza": "PS",
        "palestine": "PS",
        "palestinian": "PS",
        "israel": "IL",
        "jerusalem": "IL",
        "tel aviv": "IL",
        "ukraine": "UA",
        "kyiv": "UA",
        "kiev": "UA",
        "russia": "RU",
        "moscow": "RU",
        "united states": "US",
        "usa": "US",
        "washington": "US",
        "united kingdom": "GB",
        "uk": "GB",
        "britain": "GB",
        "london": "GB",
        "germany": "DE",
        "berlin": "DE",
        "france": "FR",
        "paris": "FR",
        "iran": "IR",
        "tehran": "IR",
        "iraq": "IQ",
        "syria": "SY",
        "damascus": "SY",
        "lebanon": "LB",
        "beirut": "LB",
        "jordan": "JO",
        "amman": "JO",
        "egypt": "EG",
        "cairo": "EG",
        "saudi": "SA",
        "uae": "AE",
        "qatar": "QA",
        "doha": "QA",
    }
    for key, code in country_to_code.items():
        if key in location_text_lower:
            return code
    return country_to_code.get(country, "").upper()


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
        geo_result = _geocode_with_retry(where_text)
        if geo_result:
            event_data["location_country_code"] = geo_result.country_code
            event_data["location_lat"] = geo_result.lat
            event_data["location_lon"] = geo_result.lon
    if "location_country_code" not in event_data:
        event_data["location_country_code"] = None
        event_data["location_lat"] = None
        event_data["location_lon"] = None
    return event_data


class BaselineWorkflow:
    """Orchestrate the baseline multi-agent AI pipeline."""

    def __init__(self, config: dict):
        """Initialize baseline workflow.

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
            await self._collect_claims(article, include_metadata=True), "claims"
        )
        claims = collector_result.get("output", {}).get("claims", [])
        collector_meta = collector_result

        if not claims:
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
                await self._classify_parties(
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
        clustering_result = await self._cluster_claims(claims, n_clusters=3)

        # Step 5: Generate narrative summaries
        narratives = []
        for cluster_id, claims_in_cluster in clustering_result.get(
            "clusters", {}
        ).items():
            narrative_result = _normalize_agent_result(
                await self._narrate_cluster(
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
                    key: collector_meta.get(key)
                    for key in (
                        "parse_status",
                        "structured_output_used",
                        "fallback_used",
                        "raw_response_excerpt",
                    )
                },
                "party_classifier": {
                    key: party_classifier_result.get(key)
                    for key in (
                        "parse_status",
                        "structured_output_used",
                        "fallback_used",
                        "raw_response_excerpt",
                    )
                },
                "narrator": [
                    narrative.get("llm_metadata", {}) for narrative in narratives
                ],
            },
        }

        event_data = _extract_location(event_data, article)

        logger.info(
            f"Processed article into event with {len(claims)} claims, "
            f"{len(narratives)} narratives, {len(party_data.get('parties', []))} parties"
        )

        return event_data

    async def _collect_claims(self, *args: Any, **kwargs: Any) -> Any:
        return await collect_claims(*args, **kwargs)

    async def _classify_parties(self, *args: Any, **kwargs: Any) -> Any:
        return await classify_parties(*args, **kwargs)

    async def _cluster_claims(self, *args: Any, **kwargs: Any) -> Any:
        return await cluster_claims(*args, **kwargs)

    async def _narrate_cluster(self, *args: Any, **kwargs: Any) -> Any:
        return await narrate_cluster(*args, **kwargs)

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
