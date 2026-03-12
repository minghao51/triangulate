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
            self._format_evidence(results),
            self._format_stage_diagnostics(metadata),
            self._format_exceptions(metadata, results),
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

        all_claims = list(results.get("claims", []))
        if not all_claims:
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
        investigations = results.get("party_investigations", [])

        perspectives = "## Party Perspectives\n\n"

        if not parties and not investigations:
            perspectives += "No parties identified.\n"
            return perspectives

        for party in parties:
            name = party.get("canonical_name", party.get("name", "Unknown"))
            stance = party.get("stance_summary", "No stance information available.")
            stance = party.get("stance", stance)

            perspectives += f"### {name}\n\n"
            perspectives += f"{stance}\n\n"

        if investigations:
            perspectives += "### Investigations\n\n"
            for investigation in investigations:
                data = investigation.get("investigation_data", investigation.get("investigation", {}))
                stance = investigation.get("party_stance", "")
                perspectives += (
                    f"- Party `{investigation.get('party_id', investigation.get('party_name', 'unknown'))}`: "
                    f"{stance or 'No stance recorded'}; "
                    f"supports {len(data.get('claims_supported', []))}, "
                    f"contests {len(data.get('claims_contested', []))}, "
                    f"unique {len(data.get('unique_claims', []))}\n"
                )

        return perspectives

    def _format_evidence(self, results: dict[str, Any]) -> str:
        """Format evidence summary section."""
        evidence = results.get("evidence", [])
        claims = results.get("claims", [])

        section = "## Evidence\n\n"
        section += f"- Evidence objects: {len(evidence)}\n"
        section += f"- Claim aggregates: {len(claims)}\n\n"

        if claims:
            section += "### Claim Corroboration\n\n"
            for claim in claims[:10]:
                section += (
                    f"- **{claim.get('verification_status', 'UNKNOWN')}** "
                    f"{claim.get('claim_text', '')}\n"
                )
                section += (
                    f"  Sources: {claim.get('source_diversity_count', 0)}, "
                    f"Support: {claim.get('support_count', 0)}, "
                    f"Oppose: {claim.get('oppose_count', 0)}\n"
                )
                for linked in claim.get("evidence", [])[:3]:
                    section += (
                        f"  Evidence: {linked.get('publisher', 'Unknown')} "
                        f"({linked.get('relation', 'supports')}) {linked.get('origin_url', '')}\n"
                    )
        return section

    def _format_exceptions(self, metadata: dict[str, Any], results: dict[str, Any]) -> str:
        """Format unresolved exception queue."""
        exceptions = results.get("exceptions") or metadata.get("exception_queue", [])
        section = "## Exceptions\n\n"
        if not exceptions:
            section += "No open exception items.\n"
            return section

        for item in exceptions:
            section += (
                f"- **{item.get('type', 'unknown')}** [{item.get('severity', 'unknown')}/"
                f"{item.get('status', 'open')}]: {item.get('message', '')}\n"
            )
        return section

    def _format_stage_diagnostics(self, metadata: dict[str, Any]) -> str:
        stage_runs = metadata.get("stage_runs", [])
        section = "## Stage Diagnostics\n\n"
        if not stage_runs:
            section += "No stage diagnostics available.\n"
            return section

        for run in stage_runs:
            section += (
                f"- **{run.get('stage', 'UNKNOWN')}** {run.get('status', 'UNKNOWN')}: "
                f"fallbacks={run.get('fallback_count', 0)}, "
                f"parse_failures={run.get('parse_failure_count', 0)}, "
                f"duration_ms={run.get('duration_ms', 'n/a')}\n"
            )
        return section

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
