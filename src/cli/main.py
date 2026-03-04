"""Main CLI entry point for Triangulate."""

import logging
from pathlib import Path
from rich.console import Console

import typer

from src.cli.commands.ingest import cmd_ingest
from src.cli.commands.process import cmd_process
from src.cli.commands.review import cmd_review
from src.cli.commands.query import cmd_query
from src.cli.commands.pipeline import cmd_run_pipeline
from src.cli.commands.process_url import cmd_process_url
from src.storage import init_database

app = typer.Typer(
    name="triangulate",
    help="Triangulate: Verify facts through multi-agent AI",
    add_completion=False,
)
console = Console()

# Ensure runtime directories exist before any file-backed services initialize.
Path("logs").mkdir(exist_ok=True)
Path("data").mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/triangulate.log"),
        logging.StreamHandler(),
    ],
)


@app.command()
def ingest(
    source: str | None = typer.Option(
        None, "--source", "-s", help="Specific source to fetch from"
    ),
    limit: int | None = typer.Option(
        None, "--limit", "-l", help="Maximum articles per source"
    ),
) -> None:
    """Fetch content from RSS/API sources."""
    cmd_ingest(source=source, limit=limit)


@app.command()
def process(
    unreviewed: bool = typer.Option(
        False, "--unreviewed", "-u", help="Only process unreviewed content"
    ),
    limit: int | None = typer.Option(
        None, "--limit", "-l", help="Maximum articles to process"
    ),
) -> None:
    """Run AI pipeline on ingested content."""
    cmd_process(unreviewed=unreviewed, limit=limit)


@app.command()
def process_url(
    url: str = typer.Argument(..., help="Article URL to process"),
    json_output: bool = typer.Option(
        False, "--json", "-j", help="Output JSON instead of pretty print"
    ),
    save: bool = typer.Option(False, "--save", "-s", help="Save result to database"),
) -> None:
    """Process a single article URL through the AI pipeline."""
    cmd_process_url(url, json_output=json_output, save=save)


@app.command()
def review(
    event_id: str | None = typer.Option(
        None, "--event-id", "-e", help="Specific event to review"
    ),
) -> None:
    """Review pending events interactively."""
    cmd_review(event_id=event_id)


@app.command()
def query(
    start: str | None = typer.Option(None, "--start", help="Start date (YYYY-MM-DD)"),
    end: str | None = typer.Option(None, "--end", help="End date (YYYY-MM-DD)"),
    status: str | None = typer.Option(
        None, "--status", "-s", help="Filter by verification status"
    ),
    days: int | None = typer.Option(
        None, "--days", "-d", help="Number of recent days to show"
    ),
) -> None:
    """Query and display the timeline."""
    cmd_query(start=start, end=end, status=status, days=days)


@app.command()
def run_pipeline() -> None:
    """Run the complete pipeline: ingest -> process -> review."""
    cmd_run_pipeline()


@app.command()
def init_db() -> None:
    """Initialize the database."""
    console.print("[bold blue]Initializing database...[/bold blue]")
    db = init_database()
    console.print("[green]Database initialized[/green]")
    console.print(f"Database file: {db.db_path}")


@app.command()
def version() -> None:
    """Show version information."""
    console.print("Triangulate v0.1.0")
    console.print("Multi-agent fact verification system")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
