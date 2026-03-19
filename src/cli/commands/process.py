"""Process command: Run AI pipeline on the durable intake queue."""

import asyncio
import logging
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.runtime import build_case_service

logger = logging.getLogger(__name__)
console = Console()


async def cmd_process_async(unreviewed: bool = False, limit: int | None = None) -> None:
    """Run AI processing pipeline (async).

    Args:
        unreviewed: Only process unreviewed content
        limit: Maximum articles to process
    """
    del unreviewed
    console.print("[bold blue]Starting AI processing pipeline...[/bold blue]")
    service = build_case_service()

    # Process articles
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Processing intake queue...", total=None)
        try:
            summary = await service.process_intake_queue(limit=limit)
        except Exception as e:
            console.print(f"[red]Error processing intake queue: {e}[/red]")
            logger.error(f"Processing error: {e}")
            return
        progress.update(task, completed=True)

    if summary["selected"] == 0:
        console.print("[yellow]No pending intake items found. Run 'triangulate ingest' first.[/yellow]")
        return

    console.print(
        f"[green]Processed {summary['processed']} item(s)[/green]"
        f"{' with failures: ' + str(summary['failed']) if summary['failed'] else ''}"
    )

def cmd_process(unreviewed: bool = False, limit: int | None = None) -> None:
    """Run AI processing pipeline.

    Args:
        unreviewed: Only process unreviewed content
        limit: Maximum articles to process
    """

    asyncio.run(cmd_process_async(unreviewed, limit))
