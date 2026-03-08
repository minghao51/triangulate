"""JSON exporter for structured data export.

This module provides functionality to export topic analysis results
as structured JSON for programmatic consumption.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class JSONExporter:
    """Export topic analysis results as structured JSON."""

    def export(
        self,
        results: dict[str, Any],
        metadata: dict[str, Any],
        output_path: Path,
    ) -> None:
        """Export results to JSON file.

        Args:
            results: Analysis results containing articles, claims, narratives, parties, timeline
            metadata: Metadata about the query (topic, conflict, timestamp, sources, etc.)
            output_path: Path where JSON file will be written
        """
        # Construct complete JSON structure
        output_data = {
            "metadata": self._format_metadata(metadata),
            "articles": self._format_articles(results.get("articles", [])),
            "narratives": self._format_narratives(results.get("narratives", [])),
            "parties": self._format_parties(results.get("parties", [])),
            "timeline": self._format_timeline(results.get("timeline", [])),
        }

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, default=str, ensure_ascii=False)

    def _format_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Format metadata for JSON export.

        Args:
            metadata: Raw metadata dictionary

        Returns:
            Formatted metadata with all required fields
        """
        return {
            "topic": metadata.get("topic", ""),
            "conflict": metadata.get("conflict", ""),
            "queried_at": metadata.get("queried_at", datetime.now().isoformat()),
            "sources_used": metadata.get("sources_used", []),
            "articles_fetched": metadata.get("articles_fetched", 0),
            "articles_processed": metadata.get("articles_processed", 0),
            "queries_generated": metadata.get("queries_generated", []),
        }

    def _format_articles(self, articles: list[dict]) -> list[dict]:
        """Format articles for JSON export.

        Args:
            articles: List of article dictionaries

        Returns:
            Formatted articles with all required fields
        """
        formatted = []
        for article in articles:
            formatted.append({
                "url": article.get("url", ""),
                "title": article.get("title", ""),
                "source": article.get("source", ""),
                "published_at": article.get("published_at", ""),
                "relevance_score": article.get("relevance_score", 0.0),
                "claims": article.get("claims", []),
            })
        return formatted

    def _format_narratives(self, narratives: list[dict]) -> list[dict]:
        """Format narratives for JSON export.

        Args:
            narratives: List of narrative dictionaries

        Returns:
            Formatted narratives
        """
        return narratives

    def _format_parties(self, parties: list[dict]) -> list[dict]:
        """Format parties for JSON export.

        Args:
            parties: List of party dictionaries

        Returns:
            Formatted parties
        """
        return parties

    def _format_timeline(self, timeline: list[dict]) -> list[dict]:
        """Format timeline for JSON export.

        Args:
            timeline: List of timeline event dictionaries

        Returns:
            Formatted timeline
        """
        return timeline
