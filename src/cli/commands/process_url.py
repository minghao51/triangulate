"""Process command: Run AI pipeline on a single URL."""

import asyncio
import json
import toml
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.ai.workflow import AIWorkflow

console = Console()


async def fetch_article_content(url: str) -> dict:
    """Fetch article content from URL using trafilatura + BeautifulSoup fallback.

    Args:
        url: Article URL

    Returns:
        Article dictionary with title, content, etc.
    """
    import httpx
    from bs4 import BeautifulSoup

    # Try trafilatura first
    try:
        from trafilatura import fetch_url, extract

        console.print("[dim]Trying trafilatura extraction...[/dim]")
        downloaded = fetch_url(url)

        if downloaded:
            result = extract(downloaded, include_comments=False, include_tables=False)
            if result and len(result) > 200:
                # Get title from metadata
                title = ""
                try:
                    import trafilatura.metadata

                    metadata = trafilatura.metadata.Metadata(downloaded)
                    title = metadata.title or ""
                except Exception:
                    pass

                parsed_url = urlparse(url)
                return {
                    "title": title or "Untitled Article",
                    "content": result,
                    "timestamp": datetime.now().isoformat(),
                    "link": url,
                    "author": "",
                    "source_name": parsed_url.netloc.replace("www.", ""),
                    "source_url": f"{parsed_url.scheme}://{parsed_url.netloc}",
                }
    except ImportError:
        console.print("[yellow]Trafilatura not available, using BeautifulSoup[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Trafilatura extraction failed: {e}[/yellow]")

    # Fallback to BeautifulSoup
    console.print("[dim]Using BeautifulSoup fallback...[/dim]")
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Try to extract title
        title = ""
        for tag in ["h1", "title"]:
            element = soup.find(tag)
            if element:
                title = element.get_text().strip()
                break

        # Try to extract content from common article containers
        content_selectors = [
            "article",
            '[class*="article"]',
            '[class*="story"]',
            '[class*="content"]',
            "main",
        ]

        content = ""
        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                # Remove script and style elements
                for script in element(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                content = element.get_text(separator="\n", strip=True)
                if len(content) > 200:
                    break

        # Fallback: get all paragraphs
        if not content or len(content) < 200:
            paragraphs = soup.find_all("p")
            content = "\n".join([p.get_text().strip() for p in paragraphs])

        # Extract source name from URL
        parsed_url = urlparse(url)
        source_name = parsed_url.netloc.replace("www.", "")

        article = {
            "title": title or "Untitled Article",
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "link": url,
            "author": "",
            "source_name": source_name,
            "source_url": f"{parsed_url.scheme}://{parsed_url.netloc}",
        }

        return article

    except Exception as e:
        console.print(f"[red]Error fetching article: {e}[/red]")
        raise


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
    url: str, json_output: bool = False, save: bool = False
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
        from src.cli.commands.process import store_event_in_db

        await store_event_in_db(event)
        console.print("[green]✓ Saved to database[/green]")


def cmd_process_url(url: str, json_output: bool = False, save: bool = False) -> None:
    """Process a single URL.

    Args:
        url: Article URL to process
        json_output: If True, output JSON instead of pretty print
        save: If True, save to database
    """
    asyncio.run(cmd_process_url_async(url, json_output, save))
