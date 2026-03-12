"""Case-centric CLI commands."""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from src.runtime import build_case_service
from src.storage import CaseStageName, CaseStatus

console = Console()


def cmd_list_cases(output: Path = Path("./output")) -> None:
    """List persisted topic cases."""
    service = build_case_service(output)
    cases = service.list_cases()

    if not cases:
        console.print("[yellow]No cases found[/yellow]")
        return

    table = Table(title="Topic Cases")
    table.add_column("ID", style="cyan")
    table.add_column("Query", style="white")
    table.add_column("Status", style="yellow")
    table.add_column("Stage", style="magenta")
    table.add_column("Articles", style="green")
    table.add_column("Events", style="green")
    table.add_column("Updated", style="dim")

    for case in cases:
        table.add_row(
            case.id[:8],
            case.query[:60],
            case.status.value,
            case.current_stage.value if case.current_stage else "-",
            str(case.article_count),
            str(case.event_count),
            case.updated_at.strftime("%Y-%m-%d %H:%M") if case.updated_at else "-",
        )

    console.print(table)


def cmd_show_case(case_id: str, output: Path = Path("./output")) -> None:
    """Show detailed case state."""
    service = build_case_service(output)
    details = service.get_case_details(case_id)
    if details is None:
        console.print(f"[red]Case {case_id} not found[/red]")
        return

    case = details["case"]
    console.print(
        Panel.fit(
            f"[bold]{case['query']}[/bold]\n\n"
            f"Status: [yellow]{case['status']}[/yellow]\n"
            f"Conflict: {case.get('conflict') or 'n/a'}\n"
            f"Stage: {case.get('current_stage') or 'n/a'}\n"
            f"Articles: {case.get('article_count', 0)}\n"
            f"Events: {case.get('event_count', 0)}\n"
            f"Open review items: {case.get('open_review_items', 0)}\n"
            f"Report: {case.get('report_path') or 'n/a'}",
            title=f"Case {case['id']}",
        )
    )

    stage_table = Table(title="Stage Runs")
    stage_table.add_column("Stage", style="magenta")
    stage_table.add_column("Status", style="yellow")
    stage_table.add_column("Attempt", style="cyan")
    stage_table.add_column("Duration", style="green")
    stage_table.add_column("Workflow", style="white")

    for run in details["stage_runs"]:
        stage_table.add_row(
            run["stage"],
            run["status"],
            str(run.get("attempt", 1)),
            f"{run.get('duration_ms') or 0} ms",
            run.get("workflow_name") or "-",
        )
    console.print(stage_table)

    events_table = Table(title="Case Events")
    events_table.add_column("Status", style="yellow")
    events_table.add_column("Title", style="white")
    events_table.add_column("Date", style="cyan")
    for event in details["events"][:15]:
        events_table.add_row(
            event["verification_status"],
            event["title"][:70],
            (event.get("timestamp") or "-")[:16].replace("T", " "),
        )
    console.print(events_table)


def cmd_review_case(
    case_id: str | None = None,
    *,
    decision: str | None = None,
    notes: str | None = None,
    output: Path = Path("./output"),
) -> None:
    """Review a case, optionally interactively."""
    service = build_case_service(output)
    if case_id is None:
        for case in service.list_cases():
            if case.status == CaseStatus.REVIEW_READY:
                case_id = case.id
                break

    if case_id is None:
        console.print("[yellow]No review-ready cases found[/yellow]")
        return

    details = service.get_case_details(case_id)
    if details is None:
        console.print(f"[red]Case {case_id} not found[/red]")
        return

    case = details["case"]
    console.print(
        Panel.fit(
            f"[bold]{case['query']}[/bold]\n\n"
            f"Status: {case['status']}\n"
            f"Articles: {case.get('article_count', 0)}\n"
            f"Events: {case.get('event_count', 0)}\n"
            f"Open review items: {case.get('open_review_items', 0)}\n"
            f"Notes: {case.get('review_notes') or 'n/a'}",
            title="Case Review",
        )
    )

    contested = [
        event for event in details["events"] if event["verification_status"] == "CONTESTED"
    ]
    if contested:
        table = Table(title="Contested Events")
        table.add_column("Title", style="white")
        table.add_column("Summary", style="dim")
        for event in contested[:10]:
            table.add_row(event["title"][:50], (event.get("summary") or "")[:80])
        console.print(table)

    if decision is None:
        console.print("\n[bold]Actions:[/bold]")
        console.print("  [A]pprove  [R]eject  [X] Action required  [D]efer")
        decision = Prompt.ask(
            "What would you like to do?",
            choices=["a", "r", "x", "d"],
            default="d",
        ).lower()
        decision = {
            "a": "approve",
            "r": "reject",
            "x": "action_required",
            "d": "defer",
        }[decision]

    reviewed = service.review_case(case["id"], decision, notes)
    console.print(f"[green]Case updated: {reviewed.status.value}[/green]")


def cmd_rerun_case(
    case_id: str,
    *,
    from_stage: str,
    output: Path = Path("./output"),
) -> None:
    """Rerun an existing case from a specific stage."""
    service = build_case_service(output)
    stage = CaseStageName[from_stage.upper()]
    case = asyncio.run(service.rerun_case(case_id, start_stage=stage, output_dir=output))
    console.print(
        f"[green]Case {case.id} rerun complete[/green] "
        f"({case.status.value} / {case.current_stage.value if case.current_stage else 'n/a'})"
    )


def cmd_fetch_topic_case(
    query: str,
    output: Path = Path("./output"),
    format: str = "json,markdown",
    max_articles: int = 50,
    relevance_threshold: float = 0.3,
    conflict: str | None = None,
    confirmed_parties: list[str] | None = None,
    manual_links: list[str] | None = None,
    automation_mode: str = "exceptions_only",
) -> None:
    """Run the canonical topic case pipeline."""
    del format  # Reports are always emitted as part of the case bundle.
    service = build_case_service(output)
    case = asyncio.run(
        service.run_case(
            query=query,
            output_dir=output,
            conflict=conflict,
            confirmed_parties=confirmed_parties,
            manual_links=manual_links,
            max_articles=max_articles,
            relevance_threshold=relevance_threshold,
            automation_mode=automation_mode,
        )
    )
    console.print(f"[green]Case ready:[/green] {case.id}")
    console.print(f"[green]Status:[/green] {case.status.value}")
    console.print(f"[green]Report:[/green] {case.report_path or 'n/a'}")


def cmd_monitor_cases(
    topics_config: Path,
    interval: int,
    output: Path = Path("./output"),
) -> None:
    """Run the recurring topic monitor loop."""
    import time
    import yaml

    if not topics_config.exists():
        console.print(f"[red]Config file not found: {topics_config}[/red]")
        return

    with open(topics_config) as handle:
        config = yaml.safe_load(handle) or {}

    topics = config.get("topics", [])
    if not topics:
        console.print("[yellow]No topics configured[/yellow]")
        return

    service = build_case_service(output)
    console.print(
        f"[bold blue]Monitoring {len(topics)} topic(s) every {interval} minute(s)[/bold blue]"
    )
    try:
        while True:
            cases = asyncio.run(service.run_monitor_cycle(topics, output_root=output))
            console.print(
                f"[green]Completed monitor cycle for {len(cases)} case(s)[/green]"
            )
            time.sleep(max(interval, 1) * 60)
    except KeyboardInterrupt:
        console.print("\n[yellow]Monitor stopped[/yellow]")
