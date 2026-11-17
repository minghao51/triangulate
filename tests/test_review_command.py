"""Regression tests for the review CLI command."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from src.cli.main import app
from src.storage import (
    Event,
    Review,
    ReviewStatus,
    VerificationStatus,
    get_database,
    init_database,
)
from src.storage.event_store import store_event_in_db
from src.storage.review_state import ANALYSIS_HASH_VERSION

runner = CliRunner()

APPROVAL_INPUT = {"a": ReviewStatus.APPROVED, "r": ReviewStatus.REJECTED}


def build_event(
    event_id: str = "event-1",
    *,
    claim_id: str | None = None,
    aggregates: tuple[int, int, int] = (1, 0, 1),
    evidence: list[dict] | None = None,
) -> dict:
    claim = {
        "claim": "Alpha disputes Beta",
        "claim_signature": "sig-alpha-disputes-beta",
        "verification_status": "ALLEGED",
        "party_name": "Alpha",
        "evidence": evidence
        or [
            {
                "canonical_url": "https://example.com/a",
                "title": "Article A",
                "publisher": "Example",
                "published_at": "2026-03-08T00:00:00+00:00",
                "content": "Alpha disputes Beta.",
                "relation": "supports",
            }
        ],
        "support_count": aggregates[0],
        "oppose_count": aggregates[1],
        "source_diversity_count": aggregates[2],
        "party_positions": {"Alpha": "NEUTRAL"},
    }
    if claim_id is not None:
        claim["id"] = claim_id
    return {
        "id": event_id,
        "timestamp": datetime(2026, 3, 8, 12, 0, 0, tzinfo=UTC),
        "title": "Needs review",
        "summary": "Pending event summary",
        "verification_status": "PROBABLE",
        "source_url": "https://example.com/a",
        "source_name": "Example",
        "claims": [claim],
        "narratives": [],
        "parties": [{"canonical_name": "Alpha", "aliases": ["Alpha"]}],
        "party_investigations": [],
    }


def read_review() -> Review:
    session = get_database().get_session_sync()
    try:
        review = session.query(Review).filter(Review.event_id == "event-1").one()
        session.expunge(review)
        return review
    finally:
        session.close()


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


@pytest.mark.parametrize("choice,expected_status", sorted(APPROVAL_INPUT.items()))
def test_cli_decision_binds_current_analysis_and_survives_equivalent_rewrite(
    tmp_path, choice, expected_status
):
    """A CLI decision binds the current analysis hash, mirroring case review.

    The row starts with a legacy NULL hash, so this also proves the CLI writes a
    real baseline instead of relying on unchanged pre-existing state.
    """
    init_database(str(tmp_path / "triangulate.db"))
    assert store_event_in_db(build_event()) is True

    session = get_database().get_session_sync()
    try:
        review = session.query(Review).filter(Review.event_id == "event-1").one()
        review.analysis_hash = None
        review.notes = "Analyst note."
        session.commit()
    finally:
        session.close()

    result = runner.invoke(app, ["review"], input=f"{choice}\n")
    assert result.exit_code == 0

    decided = read_review()
    assert decided.status == expected_status
    assert decided.analysis_hash is not None
    assert decided.analysis_hash.startswith(f"{ANALYSIS_HASH_VERSION}:")
    assert decided.reviewed_at is not None
    assert decided.notes == "Analyst note."

    # Equivalent rerun: different generated claim ID, derived aggregates and
    # evidence ordering, same meaningful analysis.
    equivalent = build_event(
        claim_id="a-different-generated-claim-uuid",
        aggregates=(7, 2, 4),
    )
    assert store_event_in_db(equivalent) is True

    rewritten = read_review()
    assert rewritten.status == expected_status
    assert rewritten.analysis_hash == decided.analysis_hash
    assert rewritten.notes == "Analyst note."
    assert rewritten.previous_decision_json is None
    assert rewritten.reviewed_at == decided.reviewed_at


def test_cli_decision_is_invalidated_when_analysis_materially_changes(tmp_path):
    init_database(str(tmp_path / "triangulate.db"))
    assert store_event_in_db(build_event()) is True

    result = runner.invoke(app, ["review"], input="a\n")
    assert result.exit_code == 0
    decided = read_review()
    assert decided.status == ReviewStatus.APPROVED

    changed = build_event()
    changed["claims"][0]["claim"] = "Alpha now agrees with Beta"
    assert store_event_in_db(changed) is True

    rewritten = read_review()
    assert rewritten.status == ReviewStatus.PENDING
    assert rewritten.reviewed_at is None
    assert rewritten.previous_decision_json is not None
    assert rewritten.previous_decision_json["status"] == "approved"
    assert rewritten.previous_decision_json["reason"] == "analysis_changed"
