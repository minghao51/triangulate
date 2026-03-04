"""Review command: Interactive human review of pending events."""

import logging
from datetime import UTC, datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt

from src.storage import get_database, Event, Claim, Review, ReviewStatus

logger = logging.getLogger(__name__)
console = Console()


def cmd_review(event_id: str | None = None) -> None:
    """Review pending events.

    Args:
        event_id: Specific event to review (None = review all pending)
    """
    console.print("[bold blue]Event Review[/bold blue]\n")

    db = get_database()
    session = db.get_session_sync()

    try:
        if event_id:
            # Review specific event
            event = session.query(Event).filter(Event.id == event_id).first()
            if not event:
                console.print(f"[red]Event {event_id} not found[/red]")
                return
            events = [event]
        else:
            # Get all pending events
            events = (
                session.query(Event)
                .join(Review)
                .filter(Review.status == ReviewStatus.PENDING)
                .all()
            )

        if not events:
            console.print("[yellow]No pending events to review[/yellow]")
            return

        console.print(f"Found {len(events)} pending event(s)\n")

        for event in events:
            review_event(event, session)

    finally:
        session.close()


def review_event(event: Event, session) -> None:
    """Review a single event.

    Args:
        event: Event to review
        session: Database session
    """
    # Get claims for this event
    claims = session.query(Claim).filter(Claim.event_id == event.id).all()

    # Display event
    console.print(
        Panel.fit(
            f"[bold]{event.title}[/bold]\n\n"
            f"{event.summary}\n\n"
            f"Status: [yellow]{event.verification_status.value}[/yellow] | "
            f"Claims: {len(claims)} | "
            f"Date: {event.timestamp.strftime('%Y-%m-%d %H:%M')}",
            title="Event Review",
        )
    )

    # Display claims
    if claims:
        table = Table(title="Claims")
        table.add_column("#", style="dim")
        table.add_column("Claim", style="white")
        table.add_column("Status", style="yellow")

        for i, claim in enumerate(claims, 1):
            table.add_row(
                str(i),
                claim.claim_text[:80],
                claim.verification_status.value,
            )

        console.print(table)

    # Get user action
    console.print("\n[bold]Actions:[/bold]")
    console.print("  [A]pprove  [R]eject  [E]dit  [S]kip  [Q]uit")

    choice = Prompt.ask(
        "What would you like to do?",
        choices=["a", "r", "e", "s", "q"],
        default="s",
    ).lower()

    # Update review based on choice
    review = session.query(Review).filter(Review.event_id == event.id).first()

    if choice == "a":
        review.status = ReviewStatus.APPROVED
        review.reviewed_at = datetime.now(UTC)
        session.commit()
        console.print("[green]Event approved[/green]\n")
    elif choice == "r":
        review.status = ReviewStatus.REJECTED
        review.reviewed_at = datetime.now(UTC)
        session.commit()
        console.print("[red]Event rejected[/red]\n")
    elif choice == "e":
        # For now, just approve
        console.print("[yellow]Edit feature coming soon[/yellow]")
    elif choice == "q":
        console.print("Exiting review...")
        return
    else:
        console.print("Skipped\n")
