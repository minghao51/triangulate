"""Query command: Search and display timeline."""

import logging
from datetime import UTC, datetime, timedelta
from rich.console import Console
from rich.table import Table

from src.storage import get_database, Event, VerificationStatus, Review, ReviewStatus

logger = logging.getLogger(__name__)
console = Console()


def cmd_query(
    start: str | None = None,
    end: str | None = None,
    status: str | None = None,
    days: int | None = None,
) -> None:
    """Query and display events.

    Args:
        start: Start date (YYYY-MM-DD)
        end: End date (YYYY-MM-DD)
        status: Filter by verification status
        days: Number of recent days to show
    """
    console.print("[bold blue]Querying events...[/bold blue]\n")

    db = get_database()
    session = db.get_session_sync()

    try:
        # Build query
        query = session.query(Event)

        # Date filters
        if days:
            start_date = datetime.now(UTC) - timedelta(days=days)
            query = query.filter(Event.timestamp >= start_date)
        elif start:
            start_date = datetime.strptime(start, "%Y-%m-%d")
            query = query.filter(Event.timestamp >= start_date)
            if end:
                end_date = datetime.strptime(end, "%Y-%m-%d")
                query = query.filter(Event.timestamp <= end_date)

        # Status filter
        if status:
            try:
                verification_status = VerificationStatus[status.upper()]
                query = query.filter(Event.verification_status == verification_status)
            except KeyError:
                console.print(f"[red]Invalid status: {status}[/red]")
                console.print(
                    f"Valid values: {', '.join([s.value for s in VerificationStatus])}"
                )
                return

        # Only show approved events
        query = query.join(Review, Review.event_id == Event.id).filter(
            Review.status == ReviewStatus.APPROVED
        )

        # Order by timestamp descending
        query = query.order_by(Event.timestamp.desc())

        events = query.limit(100).all()

        if not events:
            console.print("[yellow]No events found[/yellow]")
            return

        console.print(f"Found {len(events)} event(s)\n")

        # Display events
        table = Table(title="Timeline")
        table.add_column("Status", style="bold", width=12)
        table.add_column("Date", style="cyan", width=12)
        table.add_column("Title", style="white")
        table.add_column("Summary", style="dim")

        for event in events:
            # Color-code status
            status_emoji = {
                VerificationStatus.CONFIRMED: "[green]✓ CONFIRMED[/green]",
                VerificationStatus.PROBABLE: "[blue]? PROBABLE[/blue]",
                VerificationStatus.ALLEGED: "[yellow]⚠ ALLEGED[/yellow]",
                VerificationStatus.CONTESTED: "[red]✗ CONTESTED[/red]",
                VerificationStatus.DEBUNKED: "[dim]× DEBUNKED[/dim]",
            }

            table.add_row(
                status_emoji.get(
                    event.verification_status, event.verification_status.value
                ),
                event.timestamp.strftime("%Y-%m-%d"),
                event.title[:60],
                event.summary[:80] if event.summary else "",
            )

        console.print(table)

    finally:
        session.close()
