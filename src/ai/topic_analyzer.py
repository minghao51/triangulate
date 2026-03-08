"""Topic analyzer for intelligent topic-based retrieval.

This module uses AI to analyze user queries and determine:
1. Which conflict context applies (Gaza, Ukraine, Iran)
2. What search queries to generate
3. Which sources to prioritize
4. What date range to filter by
"""

import logging
from datetime import datetime
from typing import Optional

from src.ai.utils import call_llm

logger = logging.getLogger(__name__)

# Conflict detection prompt
CONFLICT_DETECTION_PROMPT = """
You are an expert in geopolitical conflicts. Analyze the following topic/query
and determine which conflict context it relates to.

Available conflicts:
- gaza_war: Gaza War, Israel-Hamas conflict, Middle East tensions
- ukraine_war: Russia-Ukraine war, NATO-Russia tensions
- iran_war: Iran-related conflicts, Iran-Israel tensions, Iran nuclear program

Topic: {topic}

Return ONLY the conflict folder name (e.g., "gaza_war", "ukraine_war", "iran_war").
If the topic doesn't clearly relate to any conflict, return the most relevant one.
"""

# Query generation prompt
QUERY_GENERATION_PROMPT = """
You are an expert search strategist for news analysis. Given a topic and conflict context,
generate 5-10 relevant search queries that would find comprehensive news coverage.

Topic: {topic}
Conflict: {conflict}

Generate queries that:
- Use different keywords and phrases
- Include names of key parties/entities involved
- Cover different aspects and perspectives
- Include both broad and specific terms

Return queries as a JSON list of strings, e.g.:
["query 1", "query 2", "query 3", ...]
"""

# Source prioritization prompt
SOURCE_PRIORITIZATION_PROMPT = """
You are an expert in media analysis for the {conflict} conflict.

Given the topic "{topic}", analyze this list of media sources and score their
relevance on a scale of 0-1 (where 1.0 is highly relevant).

Sources:
{sources}

Return a JSON object mapping source names to relevance scores, e.g.:
{{"Source Name": 0.95, "Another Source": 0.80, ...}}

Consider:
- Does the source cover this topic?
- How reliable is the source for this conflict?
- Does the source provide unique perspectives?
"""

# Date extraction prompt
DATE_EXTRACTION_PROMPT = """
Analyze the following topic/query and extract any date or time range mentioned.

Topic: {topic}

If a date range is mentioned, return as JSON:
{{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}}

If no date range is mentioned, return:
{{"start": null, "end": null}}

Use ISO 8601 format (YYYY-MM-DD).
"""


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
        prompt = CONFLICT_DETECTION_PROMPT.format(topic=query)

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
        prompt = QUERY_GENERATION_PROMPT.format(
            topic=query,
            conflict=conflict,
        )

        try:
            response = await call_llm(
                prompt=prompt,
                response_format="json",
                config=self.ai_config,
            )
        except Exception as exc:
            logger.warning("Query generation failed, using original topic: %s", exc)
            return [query]

        # Parse response as list
        if isinstance(response, list):
            return response
        elif isinstance(response, dict) and "queries" in response:
            return response["queries"]
        else:
            # Fallback: return original query
            return [query]

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

        prompt = SOURCE_PRIORITIZATION_PROMPT.format(
            topic=query,
            conflict=conflict,
            sources=source_list,
        )

        try:
            response = await call_llm(
                prompt=prompt,
                response_format="json",
                config=self.ai_config,
            )
        except Exception as exc:
            logger.warning("Source prioritization failed, using default ordering: %s", exc)
            response = {}

        # Add relevance scores to sources
        source_scores = {}
        if isinstance(response, dict):
            source_scores = response

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
        prompt = DATE_EXTRACTION_PROMPT.format(topic=query)

        try:
            response = await call_llm(
                prompt=prompt,
                response_format="json",
                config=self.ai_config,
            )
        except Exception as exc:
            logger.warning("Date extraction failed, omitting range: %s", exc)
            return None

        if isinstance(response, dict):
            start = response.get("start")
            end = response.get("end")
            if start and end:
                return (start, end)

        return None
