"""Process command: Run AI pipeline on ingested content."""

import asyncio
import logging
import json
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.ai import AIWorkflow
from src.storage.event_store import store_event_in_db as persist_event_in_db

logger = logging.getLogger(__name__)
console = Console()


async def cmd_process_async(unreviewed: bool = False, limit: int | None = None) -> None:
    """Run AI processing pipeline (async).

    Args:
        unreviewed: Only process unreviewed content
        limit: Maximum articles to process
    """
    console.print("[bold blue]Starting AI processing pipeline...[/bold blue]")

    # Load articles from temporary storage (for now, from a JSON file)
    # In a real implementation, these would come from the database
    articles_file = Path("data/fetched_articles.json")

    if not articles_file.exists():
        console.print(
            "[yellow]No fetched articles found. Run 'triangulate ingest' first.[/yellow]"
        )
        return

    with open(articles_file) as f:
        articles = json.load(f)

    if limit:
        articles = articles[:limit]

    console.print(f"Processing {len(articles)} articles...")

    # Load config and initialize AI workflow
    import toml

    config_path = Path("config.toml")
    with open(config_path) as f:
        config = toml.load(f)

    workflow = AIWorkflow(config)

    # Process articles
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Processing articles...", total=len(articles))

        events = []
        for i, article in enumerate(articles):
            progress.update(
                task, description=f"Processing article {i + 1}/{len(articles)}..."
            )

            try:
                event = await workflow.process_article(article)
                if event and persist_event_in_db(event):
                    events.append(event)
            except Exception as e:
                console.print(f"[red]Error processing article: {e}[/red]")
                logger.error(f"Processing error: {e}")

            progress.update(task, advance=1)

    console.print(f"[green]Successfully processed {len(events)} articles[/green]")


async def store_event_in_db(event_data: dict) -> bool:
    """Async compatibility wrapper for event persistence."""
    return persist_event_in_db(event_data)

def cmd_process(unreviewed: bool = False, limit: int | None = None) -> None:
    """Run AI processing pipeline.

    Args:
        unreviewed: Only process unreviewed content
        limit: Maximum articles to process
    """

    asyncio.run(cmd_process_async(unreviewed, limit))
