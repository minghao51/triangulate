"""Run-pipeline command: Execute full pipeline."""

import logging
from pathlib import Path
from rich.console import Console

from src.cli.commands.ingest import save_fetched_articles
from src.cli.commands.process import cmd_process
from src.cli.commands.review import cmd_review

logger = logging.getLogger(__name__)
console = Console()


def cmd_run_pipeline() -> None:
    """Run the complete pipeline: ingest -> process -> review."""
    console.print("[bold blue]Running Triangulate Pipeline[/bold blue]\n")

    # Step 1: Ingest
    console.print("[bold]Step 1: Ingesting content...[/bold]")
    console.print("=" * 50)

    # Temporarily patch the ingest command to save articles
    import toml

    config_path = Path("config.toml")
    with open(config_path) as f:
        config = toml.load(f)

    from src.ingester import ContentFetcher

    fetcher = ContentFetcher(config)
    articles = fetcher.fetch_all(limit=50)

    if not articles:
        console.print("[yellow]No articles fetched. Exiting.[/yellow]")
        return

    save_fetched_articles(articles)
    console.print(
        f"[dim]Saved {len(articles)} articles to data/fetched_articles.json[/dim]"
    )
    console.print()

    # Step 2: Process
    console.print("[bold]Step 2: Processing with AI...[/bold]")
    console.print("=" * 50)

    cmd_process(limit=None)
    console.print()

    # Step 3: Review
    console.print("[bold]Step 3: Reviewing events...[/bold]")
    console.print("=" * 50)

    cmd_review()

    console.print("\n[bold green]Pipeline complete![/bold green]")
