"""Topic analyzer for intelligent topic-based retrieval.

This module uses AI to analyze user queries and determine:
1. Which conflict context applies (Gaza, Ukraine, Iran)
2. What search queries to generate
3. Which sources to prioritize
4. What date range to filter by
"""

import logging
from typing import Optional

from src.ai.prompts import get_prompt
from src.ai.schemas import DateRangeSchema, QueryGenerationSchema, SourcePrioritySchema
from src.ai.utils import call_llm, call_structured_llm

logger = logging.getLogger(__name__)


class TopicAnalyzer:
    """Analyze topics and determine retrieval strategy."""

    def __init__(self, config: dict):
        """Initialize topic analyzer.

        Args:
            config: Configuration dictionary with AI settings
        """
        self.config = config
        self.ai_config = config.get("ai", {})

    async def detect_conflict(self, query: str) -> str:
        """Detect which conflict context the query relates to.

        Args:
            query: User's topic query

        Returns:
            Conflict folder name (gaza_war, ukraine_war, or iran_war)
        """
        prompt = get_prompt("CONFLICT_DETECTION", topic=query)

        try:
            response = await call_llm(
                prompt=prompt,
                response_format="text",
                config=self.ai_config,
            )
        except Exception as exc:
            logger.warning("Conflict detection failed, defaulting to gaza_war: %s", exc)
            return "gaza_war"

        # Clean up response
        conflict = response.strip().lower()

        # Validate conflict name
        valid_conflicts = ["gaza_war", "ukraine_war", "iran_war"]
        if conflict not in valid_conflicts:
            # Default to gaza_war if unclear
            conflict = "gaza_war"

        return conflict

    async def generate_search_queries(
        self,
        query: str,
        conflict: str,
    ) -> list[str]:
        """Generate relevant search queries for the topic.

        Args:
            query: User's topic query
            conflict: Conflict context

        Returns:
            List of search query strings
        """
        prompt = get_prompt("QUERY_GENERATION", topic=query, conflict=conflict)

        try:
            response = await call_structured_llm(
                prompt=prompt,
                schema=QueryGenerationSchema,
                config=self.ai_config,
                max_tokens=800,
                fallback=lambda: {"queries": [query]},
            )
        except Exception as exc:
            logger.warning("Query generation failed, using original topic: %s", exc)
            return [query]

        payload = response["output"] if isinstance(response, dict) else response
        return payload.get("queries", [query]) or [query]

    async def prioritize_sources(
        self,
        query: str,
        conflict: str,
        sources: list[dict],
    ) -> list[dict]:
        """Score and prioritize sources by relevance to topic.

        Args:
            query: User's topic query
            conflict: Conflict context
            sources: List of source dictionaries

        Returns:
            Prioritized list of sources with relevance scores
        """
        if not sources:
            return []

        # Build source list string
        source_list = "\n".join([
            f"- {s.get('name', s.get('source', 'Unknown'))}"
            for s in sources
        ])

        prompt = get_prompt(
            "SOURCE_PRIORITIZATION",
            topic=query,
            conflict=conflict,
            sources=source_list,
        )

        try:
            response = await call_structured_llm(
                prompt=prompt,
                schema=SourcePrioritySchema,
                config=self.ai_config,
                max_tokens=1500,
                fallback=lambda: {"scores": {}},
            )
        except Exception as exc:
            logger.warning("Source prioritization failed, using default ordering: %s", exc)
            response = {"output": {"scores": {}}}

        # Add relevance scores to sources
        source_scores = {}
        if isinstance(response, dict):
            source_scores = response.get("output", {}).get("scores", {})

        # Score and sort sources
        scored_sources = []
        for source in sources:
            name = source.get("name", source.get("source", ""))
            score = source_scores.get(name, 0.5)  # Default score
            source["relevance_score"] = score
            scored_sources.append(source)

        # Sort by relevance (highest first)
        scored_sources.sort(key=lambda s: s.get("relevance_score", 0), reverse=True)

        return scored_sources

    async def extract_date_range(
        self,
        query: str,
    ) -> Optional[tuple[str, str]]:
        """Extract date range from query if mentioned.

        Args:
            query: User's topic query

        Returns:
            Tuple of (start_date, end_date) or None
        """
        prompt = get_prompt("DATE_EXTRACTION", topic=query)

        try:
            response = await call_structured_llm(
                prompt=prompt,
                schema=DateRangeSchema,
                config=self.ai_config,
                max_tokens=300,
                fallback=lambda: {"start": None, "end": None},
            )
        except Exception as exc:
            logger.warning("Date extraction failed, omitting range: %s", exc)
            return None

        if isinstance(response, dict):
            payload = response.get("output", response)
            start = payload.get("start")
            end = payload.get("end")
            if start and end:
                return (start, end)

        return None
