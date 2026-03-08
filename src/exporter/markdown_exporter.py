"""Markdown exporter for human-readable reports.

This module provides functionality to export topic analysis results
as formatted Markdown documents for human consumption.
"""

from datetime import datetime
from pathlib import Path
from typing import Any


class MarkdownExporter:
    """Export topic analysis results as Markdown documents."""

    def export(
        self,
        results: dict[str, Any],
        metadata: dict[str, Any],
        output_path: Path,
    ) -> None:
        """Export results to Markdown file.

        Args:
            results: Analysis results containing articles, claims, narratives, parties, timeline
            metadata: Metadata about the query (topic, conflict, timestamp, sources, etc.)
            output_path: Path where Markdown file will be written
        """
        # Build markdown content
        sections = [
            self._format_header(metadata),
            self._format_summary(results),
            self._format_key_findings(results),
            self._format_party_perspectives(results),
            self._format_timeline(results),
            self._format_sources(metadata),
        ]

        markdown_content = "\n\n".join(sections)

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

    def _format_header(self, metadata: dict[str, Any]) -> str:
        """Format header section.

        Args:
            metadata: Metadata dictionary

        Returns:
            Header markdown string
        """
        topic = metadata.get("topic", "Unknown Topic")
        conflict = (metadata.get("conflict") or "").replace("_", " ").title()
        queried_at = metadata.get("queried_at", datetime.now().isoformat())

        header = f"# Topic Analysis: {topic}\n\n"
        header += f"**Conflict Context:** {conflict}\n\n"
        header += f"**Analyzed:** {queried_at}\n\n"

        return header

    def _format_summary(self, results: dict[str, Any]) -> str:
        """Format summary section.

        Args:
            results: Analysis results

        Returns:
            Summary markdown string
        """
        articles = results.get("articles", [])
        narratives = results.get("narratives", [])
        parties = results.get("parties", [])

        summary = "## Summary\n\n"
        summary += f"This analysis processed **{len(articles)} articles** "
        summary += f"and identified **{len(narratives)} distinct narratives** "
        summary += f"across **{len(parties)} parties/entities**.\n\n"

        # Add AI-generated executive summary if available
        if results.get("executive_summary"):
            summary += f"{results['executive_summary']}\n\n"

        return summary

    def _format_key_findings(self, results: dict[str, Any]) -> str:
        """Format key findings section.

        Args:
            results: Analysis results

        Returns:
            Key findings markdown string
        """
        findings = "## Key Findings\n\n"

        # Collect all claims from all articles
        all_claims = []
        for article in results.get("articles", []):
            all_claims.extend(article.get("claims", []))

        # Group by verification status
        confirmed = [c for c in all_claims if c.get("verification_status") in ["CONFIRMED", "PROBABLE"]]
        contested = [c for c in all_claims if c.get("verification_status") in ["ALLEGED", "CONTESTED"]]

        findings += "### Confirmed Facts\n\n"
        if confirmed:
            for claim in confirmed[:10]:  # Limit to top 10
                claim_text = claim.get("claim", claim.get("claim_text", ""))
                status = claim.get("verification_status", "UNKNOWN")
                findings += f"- **{status}**: {claim_text}\n"
        else:
            findings += "No confirmed facts identified.\n"

        findings += "\n### Contested Claims\n\n"
        if contested:
            for claim in contested[:10]:  # Limit to top 10
                claim_text = claim.get("claim", claim.get("claim_text", ""))
                status = claim.get("verification_status", "UNKNOWN")
                findings += f"- **{status}**: {claim_text}\n"
                # Add party positions if available
                if claim.get("party_positions"):
                    for party, stance in claim["party_positions"].items():
                        findings += f"  - *{party}*: {stance}\n"
        else:
            findings += "No contested claims identified.\n"

        return findings

    def _format_party_perspectives(self, results: dict[str, Any]) -> str:
        """Format party perspectives section.

        Args:
            results: Analysis results

        Returns:
            Party perspectives markdown string
        """
        parties = results.get("parties", [])

        perspectives = "## Party Perspectives\n\n"

        if not parties:
            perspectives += "No parties identified.\n"
            return perspectives

        for party in parties:
            name = party.get("canonical_name", party.get("name", "Unknown"))
            stance = party.get("stance_summary", "No stance information available.")
            stance = party.get("stance", stance)

            perspectives += f"### {name}\n\n"
            perspectives += f"{stance}\n\n"

        return perspectives

    def _format_timeline(self, results: dict[str, Any]) -> str:
        """Format timeline section.

        Args:
            results: Analysis results

        Returns:
            Timeline markdown string
        """
        timeline = results.get("timeline", [])

        timeline_section = "## Timeline\n\n"

        if not timeline:
            timeline_section += "No timeline events available.\n"
            return timeline_section

        # Sort by date if available
        sorted_timeline = sorted(
            timeline,
            key=lambda x: x.get("date", ""),
        )

        for event in sorted_timeline[:20]:  # Limit to 20 events
            date = event.get("date", "Unknown date")
            title = event.get("title", event.get("event", "Unknown event"))
            description = event.get("description", "")

            timeline_section += f"### {date}\n\n"
            timeline_section += f"**{title}**\n\n"
            if description:
                timeline_section += f"{description}\n\n"

        return timeline_section

    def _format_sources(self, metadata: dict[str, Any]) -> str:
        """Format sources section.

        Args:
            metadata: Metadata dictionary

        Returns:
            Sources markdown string
        """
        sources = metadata.get("sources_used", [])
        articles_fetched = metadata.get("articles_fetched", 0)
        articles_processed = metadata.get("articles_processed", 0)

        sources_section = "## Sources Analyzed\n\n"
        sources_section += f"- **Articles fetched:** {articles_fetched}\n"
        sources_section += f"- **Articles processed:** {articles_processed}\n"
        sources_section += f"- **Sources analyzed:** {len(sources)}\n\n"

        if sources:
            sources_section += "### Media Sources\n\n"
            for source in sources:
                sources_section += f"- {source}\n"

        return sources_section
