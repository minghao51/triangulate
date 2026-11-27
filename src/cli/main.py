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
    cmd_evaluate_case,
    cmd_get_case_owner,
    cmd_interrupt_case,
    cmd_list_cases,
    cmd_show_case,
    cmd_show_case_workflow,
    cmd_review_case,
    cmd_rerun_case,
    cmd_rebuild_case_search,
)
from src.cli.commands.osint import cmd_osint_ingest, cmd_osint_stream
from src.runtime import configured_database_path
from src.settings import resolve_database_path
from src.storage import init_database, run_migrations

app = typer.Typer(
    name="triangulate",
    help="Triangulate: Verify facts through multi-agent AI",
    add_completion=False,
)
console = Console()
case_app = typer.Typer(help="Case lifecycle commands", add_completion=False)
osint_app = typer.Typer(help="OSINT ingestion commands", add_completion=False)
app.add_typer(case_app, name="case")
app.add_typer(osint_app, name="osint")

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
    """Initialize the database and apply pending migrations.

    The target path uses the same precedence as the HTTP server: a non-default
    ``[database].path``, then ``DATABASE_PATH``, then ``./triangulate.db``,
    relative to the current working directory. Running the server and this
    command from the same directory therefore address the same file.
    """
    console.print("[bold blue]Initializing database...[/bold blue]")
    db_path = resolve_database_path(configured_database_path())
    db = init_database(str(db_path))
    run_migrations(db.db_path)
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


@case_app.command("rebuild-search")
def case_rebuild_search(case_id: str = typer.Argument(..., help="Case ID")) -> None:
    """Rebuild one case's current FTS search index."""
    cmd_rebuild_case_search(case_id)


@case_app.command("show")
def case_show(
    case_id: str = typer.Argument(..., help="Case ID"),
    output: Path = typer.Option(
        Path("./output"), "--output", "-o", help="Output directory root"
    ),
) -> None:
    """Show case details."""
    cmd_show_case(case_id=case_id, output=output)


@case_app.command("workflow")
def case_workflow(
    case_id: str = typer.Argument(..., help="Case ID"),
    output: Path = typer.Option(
        Path("./output"), "--output", "-o", help="Output directory root"
    ),
) -> None:
    """Show persisted workflow checkpoints and agent outputs."""
    cmd_show_case_workflow(case_id=case_id, output=output)


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


@case_app.command("owner")
def case_owner(
    case_id: str = typer.Argument(..., help="Case ID"),
    output: Path = typer.Option(
        Path("./output"), "--output", "-o", help="Output directory root"
    ),
) -> None:
    """Show the active case writer (kind/reference/time, never the token)."""
    cmd_get_case_owner(case_id=case_id, output=output)


@case_app.command("interrupt")
def case_interrupt(
    case_id: str = typer.Argument(..., help="Case ID"),
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Active owner reference (investigation run ID or intake item ID)",
    ),
    token: str | None = typer.Option(
        None, "--token", help="Active owner token, for explicit operator recovery"
    ),
    reason: str = typer.Option(
        ..., "--reason", "-r", help="Why the active writer is being interrupted"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt"
    ),
    output: Path = typer.Option(
        Path("./output"), "--output", "-o", help="Output directory root"
    ),
) -> None:
    """Explicitly interrupt the active case writer (CLI-only recovery)."""
    cmd_interrupt_case(
        case_id=case_id,
        run_id=run_id,
        token=token,
        reason=reason,
        yes=yes,
        output=output,
    )


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


@case_app.command("evaluate")
def case_evaluate(
    case_id: str = typer.Argument(..., help="Case ID"),
    output: Path = typer.Option(
        Path("./output"), "--output", "-o", help="Output directory root"
    ),
) -> None:
    """Run a lightweight evaluation over the current case state."""
    cmd_evaluate_case(case_id=case_id, output=output)


@osint_app.command("ingest")
def osint_ingest(
    tool: str = typer.Option(..., "--tool", help="Source OSINT tool name"),
    file: Path = typer.Option(..., "--file", help="Artifact file to import"),
    case_id: str = typer.Option(..., "--case-id", help="Case to attach the artifact to"),
    output: Path = typer.Option(
        Path("./output"), "--output", "-o", help="Output directory root"
    ),
) -> None:
    """Import a single OSINT artifact into a case."""
    cmd_osint_ingest(tool=tool, file=file, case_id=case_id, output=output)


@osint_app.command("stream")
def osint_stream(
    tool: str = typer.Option(..., "--tool", help="Source OSINT tool name"),
    watch: Path = typer.Option(..., "--watch", help="Directory of OSINT artifacts"),
    case_id: str = typer.Option(..., "--case-id", help="Case to attach artifacts to"),
    once: bool = typer.Option(
        False, "--once", help="Import current files once instead of continuous watching"
    ),
    output: Path = typer.Option(
        Path("./output"), "--output", "-o", help="Output directory root"
    ),
) -> None:
    """Import all OSINT artifacts currently present in a watch directory."""
    cmd_osint_stream(tool=tool, watch=watch, case_id=case_id, once=once, output=output)


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
