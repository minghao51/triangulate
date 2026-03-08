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
    Float,
    UniqueConstraint,
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


class FactAllegationType(str, enum.Enum):
    """Classification of claims as facts or allegations."""

    FACT = "FACT"
    ALLEGATION = "ALLEGATION"


class ReviewStatus(str, enum.Enum):
    """Review workflow status."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


class CaseStatus(str, enum.Enum):
    """Lifecycle status for a topic-oriented investigation case."""

    DISCOVERING = "DISCOVERING"
    PROCESSING = "PROCESSING"
    INVESTIGATING = "INVESTIGATING"
    REVIEW_READY = "REVIEW_READY"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MONITORING = "MONITORING"
    FAILED = "FAILED"


class CaseStageName(str, enum.Enum):
    """Named stages for persisted case runs."""

    RETRIEVE = "RETRIEVE"
    TRIAGE = "TRIAGE"
    INVESTIGATE = "INVESTIGATE"
    ARBITRATE = "ARBITRATE"
    REPORT = "REPORT"
    REVIEW = "REVIEW"


class StageStatus(str, enum.Enum):
    """Execution status for an individual case stage."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


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
    case_id = Column(String, ForeignKey("topic_cases.id"), index=True)
    case_run_id = Column(String, ForeignKey("case_stage_runs.id"))


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

    # Party investigation fields
    fact_allegation_type = Column(SQLEnum(FactAllegationType))
    arbiter_reasoning = Column(Text)
    party_positions = Column(JSON)  # {"party_id": "SUPPORTS|CONTESTS|NEUTRAL"}
    controversy_score = Column(Float)

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


class PartyInvestigation(Base):
    """Party investigation results from adversarial analysis."""

    __tablename__ = "party_investigations"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "party_id", name="uq_party_investigation_event_party"
        ),
    )

    id = Column(String, primary_key=True)
    event_id = Column(String, ForeignKey("events.id"), nullable=False)
    party_id = Column(String, ForeignKey("parties.id"), nullable=False)

    # Full investigation data
    investigation_data = Column(JSON, nullable=False)
    party_stance = Column(Text)

    created_at = Column(DateTime(timezone=True), default=utc_now)


class TopicCase(Base):
    """Top-level topic/question case that owns the workflow lifecycle."""

    __tablename__ = "topic_cases"

    id = Column(String, primary_key=True)
    query = Column(String, nullable=False, index=True)
    slug = Column(String, nullable=False, unique=True, index=True)
    conflict = Column(String)
    status = Column(SQLEnum(CaseStatus), nullable=False, index=True)
    priority = Column(Integer, nullable=False, default=0)
    importance = Column(String)
    routing_mode = Column(String)
    current_stage = Column(SQLEnum(CaseStageName))
    report_path = Column(String)
    latest_manifest_path = Column(String)
    latest_run_started_at = Column(DateTime(timezone=True))
    latest_run_completed_at = Column(DateTime(timezone=True))
    last_reviewed_at = Column(DateTime(timezone=True))
    review_notes = Column(Text)
    source_count = Column(Integer, nullable=False, default=0)
    article_count = Column(Integer, nullable=False, default=0)
    event_count = Column(Integer, nullable=False, default=0)
    open_review_items = Column(Integer, nullable=False, default=0)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at = Column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True
    )


class CaseStageRun(Base):
    """Persisted execution metadata for each case stage."""

    __tablename__ = "case_stage_runs"

    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("topic_cases.id"), nullable=False, index=True)
    stage_name = Column(SQLEnum(CaseStageName), nullable=False, index=True)
    status = Column(SQLEnum(StageStatus), nullable=False, index=True)
    attempt = Column(Integer, nullable=False, default=1)
    started_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at = Column(DateTime(timezone=True))
    duration_ms = Column(Integer)
    workflow_name = Column(String)
    model_used = Column(String)
    input_artifact_ids = Column(JSON, nullable=False, default=list)
    output_artifact_ids = Column(JSON, nullable=False, default=list)
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text)
    confidence_score = Column(Float)
    controversy_score = Column(Float)
    fallback_count = Column(Integer, nullable=False, default=0)
    parse_failure_count = Column(Integer, nullable=False, default=0)
    cost_estimate_usd = Column(Float)
    metrics_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class CaseArtifact(Base):
    """Artifacts emitted by case stages, such as reports and manifests."""

    __tablename__ = "case_artifacts"

    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("topic_cases.id"), nullable=False, index=True)
    stage_run_id = Column(
        String, ForeignKey("case_stage_runs.id"), nullable=False, index=True
    )
    artifact_type = Column(String, nullable=False, index=True)
    path = Column(String)
    payload_json = Column(JSON)
    checksum = Column(String)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class CaseArticle(Base):
    """Fetched and deduplicated article candidate associated with a case."""

    __tablename__ = "case_articles"
    __table_args__ = (
        UniqueConstraint("case_id", "url", name="uq_case_article_case_url"),
    )

    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("topic_cases.id"), nullable=False, index=True)
    url = Column(String, nullable=False)
    title = Column(String, nullable=False)
    source = Column(String)
    published_at = Column(String)
    relevance_score = Column(Float, nullable=False, default=0.0)
    fingerprint = Column(String, nullable=False, index=True)
    content = Column(Text)
    raw_payload = Column(JSON, nullable=False, default=dict)
    first_seen_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_seen_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    status = Column(String, nullable=False, default="ACTIVE")
    is_new = Column(Integer, nullable=False, default=1)


class MonitorCheckpoint(Base):
    """Track topic monitor progress for recurring runs."""

    __tablename__ = "monitor_checkpoints"
    __table_args__ = (
        UniqueConstraint("case_id", "monitor_key", name="uq_monitor_checkpoint"),
    )

    id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("topic_cases.id"), nullable=False, index=True)
    monitor_key = Column(String, nullable=False)
    cursor = Column(String)
    last_checked_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_successful_run_at = Column(DateTime(timezone=True))
    metadata_json = Column(JSON, nullable=False, default=dict)
