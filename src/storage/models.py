"""SQLAlchemy models for Triangulate database."""

from datetime import UTC, datetime
import enum

from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
    JSON,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class VerificationStatus(str, enum.Enum):
    """Verification status for claims and events."""

    CONFIRMED = "CONFIRMED"
    PROBABLE = "PROBABLE"
    ALLEGED = "ALLEGED"
    CONTESTED = "CONTESTED"
    DEBUNKED = "DEBUNKED"


class ReviewStatus(str, enum.Enum):
    """Review workflow status."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


class SourceType(str, enum.Enum):
    """Source type enumeration."""

    RSS = "rss"
    API = "api"


class Source(Base):
    """News sources (RSS feeds, APIs)."""

    __tablename__ = "sources"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    type = Column(SQLEnum(SourceType), nullable=False)
    url = Column(String, unique=True)
    last_fetched = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utc_now)


class Event(Base):
    """Main timeline events."""

    __tablename__ = "events"

    id = Column(String, primary_key=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    title = Column(String, nullable=False)
    summary = Column(Text)
    verification_status = Column(
        SQLEnum(VerificationStatus), nullable=False, index=True
    )
    created_at = Column(DateTime(timezone=True), default=utc_now, index=True)


class Claim(Base):
    """Individual factual claims extracted from sources."""

    __tablename__ = "claims"

    id = Column(String, primary_key=True)
    event_id = Column(String, ForeignKey("events.id"), nullable=False)
    source_id = Column(String, ForeignKey("sources.id"))
    claim_text = Column(Text, nullable=False)
    narrative_cluster_id = Column(String)
    verification_status = Column(SQLEnum(VerificationStatus), nullable=False)
    party_id = Column(String, ForeignKey("parties.id"))
    created_at = Column(DateTime(timezone=True), default=utc_now)


class Narrative(Base):
    """Narrative cluster summaries."""

    __tablename__ = "narratives"

    id = Column(String, primary_key=True)
    cluster_id = Column(String, unique=True, nullable=False)
    stance_summary = Column(Text, nullable=False)
    source_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class Review(Base):
    """Human review workflow tracking."""

    __tablename__ = "reviews"

    id = Column(String, primary_key=True)
    event_id = Column(String, ForeignKey("events.id"), nullable=False, unique=True)
    status = Column(SQLEnum(ReviewStatus), nullable=False, default=ReviewStatus.PENDING)
    reviewed_at = Column(DateTime(timezone=True))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class Party(Base):
    """Normalized political/geographical entities."""

    __tablename__ = "parties"

    id = Column(String, primary_key=True)
    canonical_name = Column(String, nullable=False, unique=True)
    aliases = Column(JSON, nullable=False)
    description = Column(Text)
    event_id = Column(String, ForeignKey("events.id"))
    created_at = Column(DateTime(timezone=True), default=utc_now)
