"""Regression tests for the review CLI command."""

from __future__ import annotations

from datetime import UTC, datetime

from typer.testing import CliRunner

from src.cli.main import app
from src.storage import Event, Review, ReviewStatus, VerificationStatus, init_database

runner = CliRunner()


def test_review_command_without_case_id_reviews_events(tmp_path):
    """The default review command should keep the legacy event review flow."""
    db = init_database(str(tmp_path / "triangulate.db"))
    session = db.get_session_sync()
    session.add(
        Event(
            id="event-1",
            timestamp=datetime(2026, 3, 8, 12, 0, 0, tzinfo=UTC),
            title="Needs review",
            summary="Pending event summary",
            verification_status=VerificationStatus.PROBABLE,
        )
    )
    session.add(
        Review(
            id="review-1",
            event_id="event-1",
            status=ReviewStatus.PENDING,
        )
    )
    session.commit()
    session.close()

    result = runner.invoke(app, ["review"], input="s\n")
    assert result.exit_code == 0
    assert "Event Review" in result.stdout
    assert "Needs review" in result.stdout
