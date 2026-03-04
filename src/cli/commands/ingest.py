"""Ingest command: Fetch content from RSS/API sources."""

import logging
import json
import toml
from pathlib import Path
from rich.console import Console
from rich.table import Table

from src.ingester import ContentFetcher

logger = logging.getLogger(__name__)
console = Console()


def save_fetched_articles(articles: list[dict]) -> Path:
    """Persist fetched articles so later CLI commands can process them.

    Args:
        articles: List of fetched article dictionaries

    Returns:
        Path to the saved JSON file
    """
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    output_path = data_dir / "fetched_articles.json"

    with open(output_path, "w") as f:
        json.dump(articles, f, indent=2, default=str)

    return output_path


def load_config() -> dict:
    """Load configuration from config.toml.

    Returns:
        Configuration dictionary
    """
    config_path = Path("config.toml")
    if not config_path.exists():
        console.print("[red]config.toml not found[/red]")
        raise FileNotFoundError("config.toml not found")

    with open(config_path) as f:
        return toml.load(f)


def cmd_ingest(source: str | None = None, limit: int | None = None) -> None:
    """Ingest content from sources.

    Args:
        source: Specific source to fetch from (None = all sources)
        limit: Maximum articles per source
    """
    console.print("[bold blue]Starting content ingestion...[/bold blue]")

    try:
        config = load_config()
        fetcher = ContentFetcher(config)

        if source:
            console.print(f"Fetching from source: {source}")
            articles = fetcher.fetch_from_source(source, limit=limit or 50)
        else:
            console.print("Fetching from all sources...")
            articles = fetcher.fetch_all(limit=limit)

        if not articles:
            console.print("[yellow]No articles fetched[/yellow]")
            return

        output_path = save_fetched_articles(articles)
        console.print(f"[green]Successfully fetched {len(articles)} articles[/green]")
        console.print(f"[dim]Saved fetched articles to {output_path}[/dim]")

        # Display summary
        table = Table(title="Fetched Articles")
        table.add_column("Source", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Timestamp", style="green")

        for article in articles[:10]:  # Show first 10
            table.add_row(
                article.get("source_name", article.get("source_url", "unknown"))[:20],
                article.get("title", "")[:60],
                str(article.get("timestamp", "N/A"))[:19],
            )

        console.print(table)

        if len(articles) > 10:
            console.print(f"... and {len(articles) - 10} more articles")

    except Exception as e:
        console.print(f"[red]Error during ingestion: {e}[/red]")
        logger.error(f"Ingestion error: {e}")
