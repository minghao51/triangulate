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
from src.cli.commands.topic import cmd_fetch_topic, cmd_interactive, cmd_monitor_start
from src.cli.commands.cases import (
    cmd_case_exception_action,
    cmd_list_cases,
    cmd_show_case,
    cmd_review_case,
    cmd_rerun_case,
)
from src.storage import init_database

app = typer.Typer(
    name="triangulate",
    help="Triangulate: Verify facts through multi-agent AI",
    add_completion=False,
)
console = Console()
case_app = typer.Typer(help="Case lifecycle commands", add_completion=False)
app.add_typer(case_app, name="case")

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
    case_id: str | None = typer.Option(
        None, "--case-id", "-c", help="Attach saved capture to an existing case"
    ),
) -> None:
    """Process a single article URL through the AI pipeline."""
    cmd_process_url(url, json_output=json_output, save=save, case_id=case_id)


@app.command()
def review(
    event_id: str | None = typer.Option(
        None, "--event-id", "-e", help="Specific event to review"
    ),
    case_id: str | None = typer.Option(
        None, "--case-id", "-c", help="Specific case to review"
    ),
) -> None:
    """Review pending events interactively."""
    if case_id:
        cmd_review_case(case_id=case_id)
        return
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
    """Run the configured topic case pipeline once."""
    cmd_run_pipeline()


@app.command()
def init_db() -> None:
    """Initialize the database."""
    console.print("[bold blue]Initializing database...[/bold blue]")
    db = init_database()
    console.print("[green]Database initialized[/green]")
    console.print(f"Database file: {db.db_path}")


@app.command()
def fetch_topic(
    query: str = typer.Argument(..., help="Topic to search for"),
    output: Path = typer.Option(
        Path("./output"), "--output", "-o", help="Output directory"
    ),
    format: str = typer.Option(
        "json,markdown", "--format", "-f", help="Export formats (comma-separated)"
    ),
    max_articles: int = typer.Option(
        50, "--max-articles", "-m", help="Maximum articles to fetch"
    ),
    relevance_threshold: float = typer.Option(
        0.3, "--relevance-threshold", "-r", help="Minimum relevance score (0-1)"
    ),
    conflict: str | None = typer.Option(
        None, "--conflict", "-c", help="Override conflict detection"
    ),
    confirmed_parties: list[str] = typer.Option(
        None,
        "--party",
        help="Bootstrap-confirmed parties/nationalities. Repeat for multiple values.",
    ),
    manual_links: list[str] = typer.Option(
        None,
        "--manual-link",
        help="Manual article or social links to include as evidence seeds.",
    ),
    automation_mode: str = typer.Option(
        "exceptions_only",
        "--automation-mode",
        help="Automation mode for the case bootstrap.",
    ),
) -> None:
    """Fetch and analyze news by topic using AI."""
    cmd_fetch_topic(
        query=query,
        output=output,
        format=format,
        max_articles=max_articles,
        relevance_threshold=relevance_threshold,
        conflict=conflict,
        confirmed_parties=confirmed_parties or None,
        manual_links=manual_links or None,
        automation_mode=automation_mode,
    )


@app.command()
def interactive() -> None:
    """Launch interactive topic exploration session."""
    cmd_interactive()


@app.command()
def monitor(
    start: bool = typer.Option(False, "--start", help="Start monitoring service"),
    topics_config: Path = typer.Option(
        Path("./topics.yaml"), "--topics", "-t", help="Topics configuration file"
    ),
    interval: int = typer.Option(
        30, "--interval", "-i", help="Check interval in minutes"
    ),
) -> None:
    """Background monitoring service for topics."""
    if start:
        cmd_monitor_start(topics_config=topics_config, interval=interval)
    else:
        console.print("[yellow]Use --start flag to start the monitor service[/yellow]")


@app.command()
def version() -> None:
    """Show version information."""
    console.print("Triangulate v0.1.0")
    console.print("Multi-agent fact verification system")


@app.command("cases")
def cases(
    output: Path = typer.Option(
        Path("./output"), "--output", "-o", help="Output directory root"
    ),
) -> None:
    """List persisted topic cases."""
    cmd_list_cases(output=output)


@case_app.command("show")
def case_show(
    case_id: str = typer.Argument(..., help="Case ID"),
    output: Path = typer.Option(
        Path("./output"), "--output", "-o", help="Output directory root"
    ),
) -> None:
    """Show case details."""
    cmd_show_case(case_id=case_id, output=output)


@case_app.command("review")
def case_review(
    case_id: str = typer.Argument(..., help="Case ID"),
    decision: str | None = typer.Option(
        None, "--decision", "-d", help="approve, reject, or defer"
    ),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Review notes"),
    output: Path = typer.Option(
        Path("./output"), "--output", "-o", help="Output directory root"
    ),
) -> None:
    """Review a case."""
    cmd_review_case(case_id=case_id, decision=decision, notes=notes, output=output)


@case_app.command("rerun")
def case_rerun(
    case_id: str = typer.Argument(..., help="Case ID"),
    from_stage: str = typer.Option(
        "retrieve", "--from", help="Stage to rerun from"
    ),
    output: Path = typer.Option(
        Path("./output"), "--output", "-o", help="Output directory root"
    ),
) -> None:
    """Rerun a case from a specific stage."""
    cmd_rerun_case(case_id=case_id, from_stage=from_stage, output=output)


@case_app.command("exception")
def case_exception(
    case_id: str = typer.Argument(..., help="Case ID"),
    exception_id: str = typer.Argument(..., help="Exception ID"),
    action: str = typer.Option(..., "--action", "-a", help="resolve, defer, or reopen"),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Operator notes"),
    output: Path = typer.Option(
        Path("./output"), "--output", "-o", help="Output directory root"
    ),
) -> None:
    """Update a case exception from the CLI."""
    cmd_case_exception_action(
        case_id=case_id,
        exception_id=exception_id,
        action=action,
        notes=notes,
        output=output,
    )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
) -> None:
    """Start the FastAPI HTTP server."""
    import uvicorn
    uvicorn.run("src.http.app:app", host=host, port=port, reload=reload)


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
