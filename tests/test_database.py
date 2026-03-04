"""Tests for database operations."""

import pytest
import tempfile
import os
from datetime import UTC, datetime

from src.storage import (
    Database,
    Source,
    Event,
    Claim,
    Review,
    VerificationStatus,
    ReviewStatus,
    SourceType,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    db = Database(db_path)
    db.init_db()

    yield db

    # Cleanup
    os.unlink(db_path)


def test_database_initialization(temp_db):
    """Test that database initializes correctly."""
    assert temp_db.db_path.endswith(".db")
    assert temp_db.engine is not None


def test_create_source(temp_db):
    """Test creating a source."""
    session = temp_db.get_session_sync()

    source = Source(
        id="test-source-1",
        name="Test RSS Feed",
        type=SourceType.RSS,
        url="https://example.com/feed.xml",
    )

    session.add(source)
    session.commit()

    retrieved = session.query(Source).filter(Source.id == "test-source-1").first()
    assert retrieved is not None
    assert retrieved.name == "Test RSS Feed"
    assert retrieved.type == SourceType.RSS


def test_create_event(temp_db):
    """Test creating an event."""
    session = temp_db.get_session_sync()

    event = Event(
        id="test-event-1",
        timestamp=datetime.now(UTC),
        title="Test Event",
        summary="Test event summary",
        verification_status=VerificationStatus.PROBABLE,
    )

    session.add(event)
    session.commit()

    retrieved = session.query(Event).filter(Event.id == "test-event-1").first()
    assert retrieved is not None
    assert retrieved.title == "Test Event"
    assert retrieved.verification_status == VerificationStatus.PROBABLE


def test_create_claim(temp_db):
    """Test creating a claim."""
    session = temp_db.get_session_sync()

    # First create an event
    event = Event(
        id="test-event-1",
        timestamp=datetime.now(UTC),
        title="Test Event",
        verification_status=VerificationStatus.PROBABLE,
    )
    session.add(event)
    session.flush()

    # Create claim
    claim = Claim(
        id="test-claim-1",
        event_id="test-event-1",
        claim_text="Test claim text",
        verification_status=VerificationStatus.ALLEGED,
    )

    session.add(claim)
    session.commit()

    retrieved = session.query(Claim).filter(Claim.id == "test-claim-1").first()
    assert retrieved is not None
    assert retrieved.claim_text == "Test claim text"
    assert retrieved.event_id == "test-event-1"


def test_create_review(temp_db):
    """Test creating a review."""
    session = temp_db.get_session_sync()

    # First create an event
    event = Event(
        id="test-event-1",
        timestamp=datetime.now(UTC),
        title="Test Event",
        verification_status=VerificationStatus.PROBABLE,
    )
    session.add(event)
    session.flush()

    # Create review
    review = Review(
        id="test-review-1",
        event_id="test-event-1",
        status=ReviewStatus.PENDING,
    )

    session.add(review)
    session.commit()

    retrieved = session.query(Review).filter(Review.event_id == "test-event-1").first()
    assert retrieved is not None
    assert retrieved.status == ReviewStatus.PENDING
