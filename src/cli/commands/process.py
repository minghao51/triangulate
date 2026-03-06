"""Process command: Run AI pipeline on ingested content."""

import asyncio
import logging
import json
import uuid
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.ai import AIWorkflow
from src.storage import (
    get_database,
    Event,
    Claim,
    Narrative,
    Review,
    VerificationStatus,
    ReviewStatus,
)

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
                if event and await store_event_in_db(event):
                    events.append(event)
            except Exception as e:
                console.print(f"[red]Error processing article: {e}[/red]")
                logger.error(f"Processing error: {e}")

            progress.update(task, advance=1)

    console.print(f"[green]Successfully processed {len(events)} articles[/green]")


async def store_event_in_db(event_data: dict) -> bool:
    """Store processed event in database.

    Args:
        event_data: Event data dictionary

    Returns:
        True when the event and related records were persisted
    """
    db = get_database()
    session = db.get_session_sync()

    try:
        # Create event
        event = Event(
            id=event_data["id"],
            timestamp=event_data["timestamp"],
            title=event_data["title"],
            summary=event_data["summary"],
            verification_status=VerificationStatus[event_data["verification_status"]],
        )
        session.add(event)

        # Create claims
        for claim_data in event_data.get("claims", []):
            claim = Claim(
                id=str(uuid.uuid4()),
                event_id=event_data["id"],
                claim_text=claim_data["claim"],
                verification_status=VerificationStatus[
                    claim_data.get("verification_status", "ALLEGED")
                ],
                narrative_cluster_id=claim_data.get("cluster_id"),
            )
            session.add(claim)

        # Create narratives
        for narrative_data in event_data.get("narratives", []):
            stored_cluster_id = f"{event_data['id']}:{narrative_data['cluster_id']}"
            narrative = Narrative(
                id=str(uuid.uuid4()),
                cluster_id=stored_cluster_id,
                stance_summary=narrative_data["stance_summary"],
                source_count=narrative_data["claim_count"],
            )
            session.add(narrative)

        # Create review entry
        review = Review(
            id=str(uuid.uuid4()),
            event_id=event_data["id"],
            status=ReviewStatus.PENDING,
        )
        session.add(review)

        session.commit()
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error storing event {event_data.get('id')}: {e}")
        return False
    finally:
        session.close()


def cmd_process(unreviewed: bool = False, limit: int | None = None) -> None:
    """Run AI processing pipeline.

    Args:
        unreviewed: Only process unreviewed content
        limit: Maximum articles to process
    """

    asyncio.run(cmd_process_async(unreviewed, limit))
