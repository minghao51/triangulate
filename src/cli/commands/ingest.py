"""Ingest command: Fetch content from sources into the durable intake queue."""

import logging
from rich.console import Console
from rich.table import Table

from src.runtime import build_case_service

logger = logging.getLogger(__name__)
console = Console()


def cmd_ingest(source: str | None = None, limit: int | None = None) -> None:
    """Ingest content from sources.

    Args:
        source: Specific source to fetch from (None = all sources)
        limit: Maximum articles per source
    """
    console.print("[bold blue]Starting content ingestion...[/bold blue]")

    try:
        service = build_case_service()
        if source:
            console.print(f"Fetching from source: {source}")
        else:
            console.print("Fetching from all sources...")

        intake_items = service.fetch_and_intake_articles(source=source, limit=limit)
        if not intake_items:
            console.print("[yellow]No articles fetched[/yellow]")
            return

        console.print(
            f"[green]Queued {len(intake_items)} article(s) into the durable intake queue[/green]"
        )

        # Display summary
        table = Table(title="Fetched Articles")
        table.add_column("Source", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Timestamp", style="green")

        for item in intake_items[:10]:
            table.add_row(
                (item.source_name or "unknown")[:20],
                item.title[:60],
                str(item.published_at or "N/A")[:19],
            )

        console.print(table)

        if len(intake_items) > 10:
            console.print(f"... and {len(intake_items) - 10} more articles")

    except Exception as e:
        console.print(f"[red]Error during ingestion: {e}[/red]")
        logger.error(f"Ingestion error: {e}")
