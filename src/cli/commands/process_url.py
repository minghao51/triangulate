"""Process command: Run AI pipeline on a single URL."""

import asyncio
import json
import toml
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.ai.workflow import AIWorkflow
from src.ingester.url_capture import fetch_article_content
from src.runtime import build_case_service

console = Console()


def pretty_print_results(event_data: dict):
    """Pretty print the workflow results.

    Args:
        event_data: Processed event data from AIWorkflow
    """
    console.print("\n[bold cyan]{'=' * 80}[/bold cyan]")
    console.print("[bold cyan]AI WORKFLOW RESULTS[/bold cyan]")
    console.print("[bold cyan]{'=' * 80}[/bold cyan]\n")

    # Event Overview
    console.print("[bold yellow]📰 EVENT OVERVIEW[/bold yellow]")
    console.print("-" * 80)
    console.print(f"Title:       {event_data.get('title', 'N/A')}")
    console.print(f"Status:      {event_data.get('verification_status', 'N/A')}")
    console.print(f"Source:      {event_data.get('source_name', 'N/A')}")
    console.print(f"URL:         {event_data.get('source_url', 'N/A')}")
    console.print("")

    # Claims
    claims = event_data.get("claims", [])
    console.print(
        f"[bold yellow]📝 EXTRACTED CLAIMS ({len(claims)} total)[/bold yellow]"
    )
    console.print("-" * 80)
    if claims:
        for i, claim in enumerate(claims, 1):
            console.print(f"\n[{i}] {claim.get('claim', 'N/A')}")
            console.print(f"    Who:        {', '.join(claim.get('who', [])) or 'N/A'}")
            console.print(f"    When:       {claim.get('when', 'N/A')}")
            console.print(f"    Where:      {claim.get('where', 'N/A')}")
            console.print(f"    Confidence: {claim.get('confidence', 'N/A')}")
            console.print(f"    Status:     {claim.get('verification_status', 'N/A')}")
    else:
        console.print("No claims extracted.")
    console.print("")

    # Narratives
    narratives = event_data.get("narratives", [])
    console.print(f"[bold yellow]🎭 NARRATIVES ({len(narratives)} total)[/bold yellow]")
    console.print("-" * 80)
    if narratives:
        for i, narrative in enumerate(narratives, 1):
            console.print(
                f"\n[Narrative {i}] Cluster ID: {narrative.get('cluster_id', 'N/A')}"
            )
            console.print(f"    Claims: {narrative.get('claim_count', 0)}")
            console.print(f"    Stance: {narrative.get('stance_summary', 'N/A')}")
            console.print(
                f"    Themes: {', '.join(narrative.get('key_themes', [])) or 'N/A'}"
            )
            console.print(
                f"    Entities (Parties): {', '.join(narrative.get('main_entities', [])) or 'N/A'}"
            )
    else:
        console.print("No narratives generated.")
    console.print("")

    # Summary
    console.print("[bold yellow]📊 SUMMARY[/bold yellow]")
    console.print("-" * 80)
    console.print(f"Total Claims:      {len(claims)}")
    console.print(f"Total Narratives:  {len(narratives)}")
    console.print(f"Verification:      {event_data.get('verification_status', 'N/A')}")

    # Parties/Entities Summary
    all_entities = set()
    for narrative in narratives:
        all_entities.update(narrative.get("main_entities", []))
    for claim in claims:
        all_entities.update(claim.get("who", []))

    console.print(f"Identified Parties: {', '.join(sorted(all_entities)) or 'N/A'}")
    console.print("")


async def cmd_process_url_async(
    url: str,
    json_output: bool = False,
    save: bool = False,
    case_id: str | None = None,
) -> None:
    """Process a single URL through the AI pipeline (async).

    Args:
        url: Article URL to process
        json_output: If True, output JSON instead of pretty print
        save: If True, save to database
    """
    console.print(f"[bold blue]Processing: {url}[/bold blue]")

    # Load config
    config_path = Path("config.toml")
    with open(config_path) as f:
        config = toml.load(f)

    # Fetch article
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching article...", total=None)

        try:
            article = await fetch_article_content(url)
            progress.update(task, completed=True)
        except Exception as e:
            console.print(f"[red]✗ Failed to fetch article: {e}[/red]")
            return

    console.print(f"[green]✓ Fetched: {article['title'][:60]}...[/green]")
    console.print(f"[green]✓ Content: {len(article['content'])} characters[/green]\n")

    # Process
    console.print("Processing through AI workflow...")
    console.print("This may take a minute...\n")

    workflow = AIWorkflow(config)
    event = await workflow.process_article(article)

    if not event:
        console.print(
            "[red]✗ Failed to process article. No claims were extracted.[/red]"
        )
        return

    # Display or save results
    if json_output:
        console.print(json.dumps(event, indent=2, default=str))
    else:
        pretty_print_results(event)

    # Save to database if requested
    if save:
        console.print("\n[bold blue]Saving to database...[/bold blue]")
        service = build_case_service()
        queued = await service.capture_url_to_intake(url, case_id=case_id)
        summary = await service.process_intake_queue(intake_ids=[item.id for item in queued])
        if summary["processed"] > 0:
            console.print("[green]✓ Saved through the durable intake pipeline[/green]")
        else:
            console.print("[red]✗ Capture was queued but processing failed[/red]")


def cmd_process_url(
    url: str,
    json_output: bool = False,
    save: bool = False,
    case_id: str | None = None,
) -> None:
    """Process a single URL.

    Args:
        url: Article URL to process
        json_output: If True, output JSON instead of pretty print
        save: If True, save to database
        case_id: Optional case to attach the saved capture to
    """
    asyncio.run(cmd_process_url_async(url, json_output, save, case_id))
