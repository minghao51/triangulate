"""SQLAlchemy models for Triangulate database."""

from datetime import UTC, datetime
import enum
from typing import Any

from sqlalchemy import (
    String,
    Text,
    Integer,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
    JSON,
    Float,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

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
    ACTION_REQUIRED = "action_required"
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

    BOOTSTRAP = "BOOTSTRAP"
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


class InvestigationRunTrigger(str, enum.Enum):
    """Why a grouped investigation invocation started.

    Stored by member name like the other SQL enums; ``RERUN`` covers both an
    explicit rerun and a resume that starts from a later stage, and ``MONITOR``
    covers a monitor-cycle dispatch. A new invocation always gets a new ID.
    """

    INITIAL = "initial"
    RERUN = "rerun"
    MONITOR = "monitor"


class InvestigationRunStatus(str, enum.Enum):
    """Lifecycle status for one ``run_case`` invocation.

    ``RUNNING`` is only an in-flight marker. ``INTERRUPTED`` exists for the
    future explicit R02 interrupt contract; R01 never invents an interruption.
    """

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PAUSED = "paused"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class InvestigationCoverage(str, enum.Enum):
    """Honest coverage classification for one invocation's requested scope."""

    COMPLETE_REQUESTED_SCOPE = "complete_requested_scope"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_ATTEMPTED = "not_attempted"
    UNKNOWN = "unknown"


class SourceType(str, enum.Enum):
    """Source type enumeration."""

    RSS = "rss"
    API = "api"


class CaptureKind(str, enum.Enum):
    """How an immutable evidence capture came to exist.

    ``live`` means the body was supplied by a current ingestion/analysis run.
    ``legacy_snapshot`` marks operator-requested materialization of an existing
    ``EvidenceItem.content`` value whose observation time is unknown.
    """

    LIVE = "live"
    LEGACY_SNAPSHOT = "legacy_snapshot"


class AlignmentStatus(str, enum.Enum):
    """Result of checking a proposed quotation against immutable capture text.

    Only ``EXACT`` means a validated passage exists. Everything else is an
    honest non-answer: the quote was not provided, the capture/source text was
    unavailable, no exact occurrence was found in the recorded analysis scope, or
    more than one occurrence made an unambiguous span impossible.
    """

    NOT_PROVIDED = "not_provided"
    SOURCE_UNAVAILABLE = "source_unavailable"
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"
    EXACT = "exact"


class Source(Base):
    """News sources (RSS feeds, APIs)."""

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[SourceType] = mapped_column(SQLEnum(SourceType), nullable=False)
    url: Mapped[str | None] = mapped_column(String, unique=True)
    last_fetched: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)


class Event(Base):
    """Main timeline events."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SQLEnum(VerificationStatus), nullable=False, index=True
    )
    location_country_code: Mapped[str | None] = mapped_column(String, nullable=True)
    location_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    case_id: Mapped[str | None] = mapped_column(String, ForeignKey("topic_cases.id"), index=True)
    case_run_id: Mapped[str | None] = mapped_column(String, ForeignKey("case_stage_runs.id"))
    # Grouped invocation that produced this observation. Kept separate from
    # ``case_run_id``, which still identifies the stage attempt.
    investigation_run_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("investigation_runs.id"), index=True
    )

    workflow_route: Mapped[str | None] = mapped_column(String, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)

class Claim(Base):
    """Individual factual claims extracted from sources."""

    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_id: Mapped[str] = mapped_column(String, ForeignKey("events.id"), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String, ForeignKey("sources.id"))
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    narrative_cluster_id: Mapped[str | None] = mapped_column(String)
    verification_status: Mapped[VerificationStatus] = mapped_column(SQLEnum(VerificationStatus), nullable=False)
    party_id: Mapped[str | None] = mapped_column(String, ForeignKey("parties.id"))

    # Party investigation fields
    fact_allegation_type: Mapped[FactAllegationType | None] = mapped_column(SQLEnum(FactAllegationType))
    arbiter_reasoning: Mapped[str | None] = mapped_column(Text)
    party_positions: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # {"party_id": "SUPPORTS|CONTESTS|NEUTRAL"}
    controversy_score: Mapped[float | None] = mapped_column(Float)
    claim_signature: Mapped[str | None] = mapped_column(String, index=True)
    support_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    oppose_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_diversity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)


class Narrative(Base):
    """Narrative cluster summaries."""

    __tablename__ = "narratives"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    cluster_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    stance_summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_count: Mapped[int | None] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)

    key_themes: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    main_entities: Mapped[list[str] | None] = mapped_column(JSON, default=list)

class Review(Base):
    """Human review workflow tracking."""

    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_id: Mapped[str] = mapped_column(String, ForeignKey("events.id"), nullable=False, unique=True)
    status: Mapped[ReviewStatus] = mapped_column(SQLEnum(ReviewStatus), nullable=False, default=ReviewStatus.PENDING)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    # Versioned canonical analysis fingerprint the current decision applies to.
    # Null on legacy rows: unknown baseline, treated conservatively on rewrite.
    analysis_hash: Mapped[str | None] = mapped_column(String)
    # Prior decision retained when a rewrite invalidates the review; never
    # replaces the human-authored ``notes`` column.
    previous_decision_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)


class Party(Base):
    """Normalized political/geographical entities."""

    __tablename__ = "parties"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_bootstrap_confirmed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_id: Mapped[str | None] = mapped_column(String, ForeignKey("events.id"))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)


class PartyInvestigation(Base):
    """Party investigation results from adversarial analysis."""

    __tablename__ = "party_investigations"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "party_id", name="uq_party_investigation_event_party"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_id: Mapped[str] = mapped_column(String, ForeignKey("events.id"), nullable=False)
    party_id: Mapped[str] = mapped_column(String, ForeignKey("parties.id"), nullable=False)

    # Full investigation data
    investigation_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    party_stance: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)

    party_name: Mapped[str | None] = mapped_column(String, nullable=True)

class TopicCase(Base):
    """Top-level topic/question case that owns the workflow lifecycle."""

    __tablename__ = "topic_cases"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    query: Mapped[str] = mapped_column(String, nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    conflict: Mapped[str | None] = mapped_column(String)
    status: Mapped[CaseStatus] = mapped_column(SQLEnum(CaseStatus), nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    importance: Mapped[str | None] = mapped_column(String)
    routing_mode: Mapped[str | None] = mapped_column(String)
    current_stage: Mapped[CaseStageName | None] = mapped_column(SQLEnum(CaseStageName))
    report_path: Mapped[str | None] = mapped_column(String)
    latest_manifest_path: Mapped[str | None] = mapped_column(String)
    latest_run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_run_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    article_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_review_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # R02 single-writer admission/fencing. The token is claimed atomically before
    # a case-bound writer starts and validated in every case-bound write
    # transaction; ``owner_ref_id`` names the investigation run or intake item.
    # All fields are nullable so legacy rows simply have no active owner.
    owner_token: Mapped[str | None] = mapped_column(String, index=True)
    owner_kind: Mapped[str | None] = mapped_column(String)
    owner_ref_id: Mapped[str | None] = mapped_column(String)
    owner_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True
    )


class InvestigationRun(Base):
    """One grouped ``run_case`` invocation.

    This is an internal foundation record: it groups the stage attempts and
    observations of a single invocation without repurposing
    ``Event.case_run_id`` (which remains the stage-attempt FK). Existing stage
    history keeps a null grouped-run reference and therefore stays explicitly
    unknown. R01 does not claim concurrency safety: sequence allocation and
    write admission are fenced in R02, and snapshot IDs are populated by R03.
    """

    __tablename__ = "investigation_runs"
    __table_args__ = (
        UniqueConstraint("case_id", "sequence", name="uq_investigation_run_case_sequence"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String, ForeignKey("topic_cases.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger: Mapped[InvestigationRunTrigger] = mapped_column(
        SQLEnum(InvestigationRunTrigger), nullable=False, index=True
    )
    requested_start_stage: Mapped[CaseStageName | None] = mapped_column(
        SQLEnum(CaseStageName)
    )
    parameter_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    predecessor_run_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("investigation_runs.id")
    )
    status: Mapped[InvestigationRunStatus] = mapped_column(
        SQLEnum(InvestigationRunStatus), nullable=False, index=True
    )
    coverage: Mapped[InvestigationCoverage] = mapped_column(
        SQLEnum(InvestigationCoverage), nullable=False
    )
    coverage_details: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Snapshot references stay plain nullable values until R03 creates the
    # snapshot table; R01 leaves them null instead of inventing a baseline.
    baseline_snapshot_id: Mapped[str | None] = mapped_column(String)
    result_snapshot_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class CaseStageRun(Base):
    """Persisted execution metadata for each case stage."""

    __tablename__ = "case_stage_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, ForeignKey("topic_cases.id"), nullable=False, index=True)
    stage_name: Mapped[CaseStageName] = mapped_column(SQLEnum(CaseStageName), nullable=False, index=True)
    status: Mapped[StageStatus] = mapped_column(SQLEnum(StageStatus), nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    workflow_name: Mapped[str | None] = mapped_column(String)
    model_used: Mapped[str | None] = mapped_column(String)
    input_artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    output_artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    controversy_score: Mapped[float | None] = mapped_column(Float)
    fallback_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parse_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_estimate_usd: Mapped[float | None] = mapped_column(Float)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # Nullable grouped-invocation reference; legacy stage history stays unknown.
    investigation_run_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("investigation_runs.id"), index=True
    )
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)


class CaseArtifact(Base):
    """Artifacts emitted by case stages, such as reports and manifests."""

    __tablename__ = "case_artifacts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, ForeignKey("topic_cases.id"), nullable=False, index=True)
    stage_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("case_stage_runs.id"), nullable=False, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    path: Mapped[str | None] = mapped_column(String)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    checksum: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)


class CaseArticle(Base):
    """Fetched and deduplicated article candidate associated with a case."""

    __tablename__ = "case_articles"
    __table_args__ = (
        UniqueConstraint("case_id", "url", name="uq_case_article_case_url"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, ForeignKey("topic_cases.id"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str | None] = mapped_column(String)
    published_at: Mapped[str | None] = mapped_column(String)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fingerprint: Mapped[str] = mapped_column(String, nullable=False, index=True)
    content: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ACTIVE")
    is_new: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_type: Mapped[str] = mapped_column(String, nullable=False, default="rss")
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class IntakeItem(Base):
    """Durable intake queue for non-website capture and ingestion workflows."""

    __tablename__ = "intake_items"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str | None] = mapped_column(String, ForeignKey("topic_cases.id"), index=True)
    url: Mapped[str | None] = mapped_column(String)
    title: Mapped[str] = mapped_column(String, nullable=False)
    source_name: Mapped[str | None] = mapped_column(String)
    published_at: Mapped[str | None] = mapped_column(String)
    fingerprint: Mapped[str] = mapped_column(String, nullable=False, index=True)
    content: Mapped[str | None] = mapped_column(Text)
    capture_type: Mapped[str] = mapped_column(String, nullable=False, default="source_ingest")
    source_type: Mapped[str] = mapped_column(String, nullable=False, default="rss")
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    intake_status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING", index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    processed_event_id: Mapped[str | None] = mapped_column(String, ForeignKey("events.id"), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class MonitorCheckpoint(Base):
    """Track topic monitor progress for recurring runs."""

    __tablename__ = "monitor_checkpoints"
    __table_args__ = (
        UniqueConstraint("case_id", "monitor_key", name="uq_monitor_checkpoint"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, ForeignKey("topic_cases.id"), nullable=False, index=True)
    monitor_key: Mapped[str] = mapped_column(String, nullable=False)
    cursor: Mapped[str | None] = mapped_column(String)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_successful_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class EvidenceItem(Base):
    """First-class evidence objects linked to cases and events."""

    __tablename__ = "evidence_items"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, ForeignKey("topic_cases.id"), nullable=False, index=True)
    event_id: Mapped[str | None] = mapped_column(String, ForeignKey("events.id"), index=True)
    case_article_id: Mapped[str | None] = mapped_column(String, ForeignKey("case_articles.id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String)
    origin_url: Mapped[str | None] = mapped_column(String)
    canonical_url: Mapped[str | None] = mapped_column(String)
    archived_url: Mapped[str | None] = mapped_column(String)
    publisher: Mapped[str | None] = mapped_column(String)
    published_at: Mapped[str | None] = mapped_column(String)
    # Compatibility projection: mirrors the normalized text of the current
    # immutable capture when one exists. Never the source of truth for an old
    # quotation; use EvidenceCapture rows for that.
    content: Mapped[str | None] = mapped_column(Text)
    # Nullable pointer to the selected immutable capture. Deliberately not a
    # relationship and without cascade: deleting a claim/link must never remove
    # capture history.
    current_capture_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("evidence_captures.id"), index=True, nullable=True
    )
    capture_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    verification_status: Mapped[str] = mapped_column(String, nullable=False, default="UNVERIFIED")
    credibility_tier: Mapped[str | None] = mapped_column(String)
    requires_human_review: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class EvidenceCapture(Base):
    """Append-only immutable snapshot of an evidence item's source body.

    ``text`` is the exact UTF-8 extraction after CRLF/CR -> LF normalization
    only. ``text_sha256`` is the SHA-256 of that text. The separate fingerprint
    (``normalized_text_sha256`` under ``normalization_version``) is for future
    dependency grouping and is never used for quotation offsets.

    Rows are append-only: identical ``(evidence_id, text_sha256)`` reuses the
    existing version, and reobservations do not overwrite the first recorded or
    observed time, body or metadata.
    """

    __tablename__ = "evidence_captures"
    __table_args__ = (
        UniqueConstraint(
            "evidence_id", "text_sha256", name="uq_evidence_capture_evidence_text"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    evidence_id: Mapped[str] = mapped_column(
        String, ForeignKey("evidence_items.id"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String, nullable=False, index=True)
    normalized_text_sha256: Mapped[str] = mapped_column(String, nullable=False, index=True)
    normalization_version: Mapped[str] = mapped_column(String, nullable=False, default="v1")
    # Actual persistence time of this capture row.
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    # Actual fetch/observation time when known; null when legacy-unknown.
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capture_kind: Mapped[str] = mapped_column(String, nullable=False, default=CaptureKind.LIVE.value)
    # Frozen provenance (URLs/title/publisher/source/publication, extraction,
    # model/prompt and origin stage IDs when known). Stored as an independent
    # deep copy; later caller mutations must not rewrite history.
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


@event.listens_for(EvidenceCapture, "before_update")
def _prevent_evidence_capture_update(mapper, connection, target) -> None:
    """Enforce append-only captures at the ORM write boundary.

    Deliberately narrow: it is not a raw-SQL ACL framework. Application code
    creates another capture version instead of editing an existing row.
    """
    raise ValueError(
        "EvidenceCapture rows are append-only; record a new capture version instead"
    )


@event.listens_for(EvidenceCapture, "before_delete")
def _prevent_evidence_capture_delete(mapper, connection, target) -> None:
    """Reject ORM deletion of capture history (including old versions).

    Narrow application-boundary guard only; claim/link deletion remains allowed
    and never cascades to captures. Fixture ``drop_all`` DDL is unaffected.
    """
    raise ValueError(
        "EvidenceCapture rows are append-only; delete is not permitted"
    )


class EvidenceVerificationCheck(Base):
    """Verification metadata for a specific evidence item."""

    __tablename__ = "evidence_verification_checks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    evidence_id: Mapped[str] = mapped_column(
        String, ForeignKey("evidence_items.id"), nullable=False, index=True
    )
    check_type: Mapped[str] = mapped_column(String, nullable=False)
    result: Mapped[str] = mapped_column(String, nullable=False)
    method: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    verified_by: Mapped[str | None] = mapped_column(String)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)


class ClaimEvidenceLink(Base):
    """Relationship between a claim and the evidence that supports or contests it."""

    __tablename__ = "claim_evidence_links"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    claim_id: Mapped[str] = mapped_column(String, ForeignKey("claims.id"), nullable=False, index=True)
    evidence_id: Mapped[str] = mapped_column(
        String, ForeignKey("evidence_items.id"), nullable=False, index=True
    )
    # Raw stored relationship. Preserved verbatim for diagnostics: legacy values
    # (for example ``opposes``) are never rewritten here. Effective/counted
    # relationships are derived by ``src.storage.citations`` policy helpers.
    relation: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_diversity_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    # Nullable pointer to the immutable capture the passage was validated
    # against. Deliberately no cascade: deleting a claim/link never removes
    # capture history.
    capture_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("evidence_captures.id"), index=True, nullable=True
    )
    # Nullable pointer to the append-only validated citation, if any. Invalid or
    # unvalidated proposals leave this null and stay diagnostics on the link.
    citation_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("claim_citations.id"), index=True, nullable=True
    )
    # Diagnostic quotation proposal preserved as supplied (possibly invalid).
    # Only a validated citation carries the authoritative frozen passage.
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_char: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_char: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Honest default for legacy rows: no quote/offset was ever proposed.
    alignment_status: Mapped[str] = mapped_column(
        String, nullable=False, default="not_provided", index=True
    )
    assessment_origin: Mapped[str | None] = mapped_column(String, nullable=True)
    assessment_version: Mapped[str | None] = mapped_column(String, nullable=True)
    assessment_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)


class ClaimCitation(Base):
    """Append-only record of one validated claim passage.

    A citation freezes the exact claim text/signature, the immutable capture it
    was validated against, the exact code-point passage and the assessment
    provenance. ``original_claim_id`` is a historical **value**, not a deleting
    foreign key to mutable ``Claim`` rows, so deleting/rewriting a live claim or
    its current link leaves the citation (and its capture) resolvable.

    ``metadata_json`` is an independent deep copy of the frozen assessment
    context (recorded analysis scope, alignment version, proposal diagnostics).
    Rows are append-only: identical content reuses the existing row without
    overwriting its first metadata or recorded time.
    """

    __tablename__ = "claim_citations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String, ForeignKey("topic_cases.id"), nullable=False, index=True
    )
    capture_id: Mapped[str] = mapped_column(
        String, ForeignKey("evidence_captures.id"), nullable=False, index=True
    )
    # Historical claim identity as a plain value; intentionally not an FK.
    original_claim_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    claim_signature: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Frozen exact claim text at validation time.
    text: Mapped[str] = mapped_column(Text, nullable=False)
    relationship: Mapped[str] = mapped_column(String, nullable=False, index=True)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    alignment_status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    alignment_version: Mapped[str] = mapped_column(String, nullable=False)
    assessment_origin: Mapped[str | None] = mapped_column(String, nullable=True)
    assessment_version: Mapped[str | None] = mapped_column(String, nullable=True)
    # Frozen assessment context; deep-copied, never a shared caller dict.
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # Actual UTC persistence time of this citation row.
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


@event.listens_for(ClaimCitation, "before_update")
def _prevent_claim_citation_update(mapper, connection, target) -> None:
    """Enforce append-only citations at the ORM write boundary.

    Mirrors the ``EvidenceCapture`` guards. Deliberately narrow: it is not a
    raw-SQL ACL. Changed assessments create a new citation instead of editing
    history.
    """
    raise ValueError(
        "ClaimCitation rows are append-only; record a new citation instead"
    )


@event.listens_for(ClaimCitation, "before_delete")
def _prevent_claim_citation_delete(mapper, connection, target) -> None:
    """Reject ORM deletion of validated citation history.

    Narrow application-boundary guard only; it is not a raw-SQL ACL. Deleting a
    live claim or link never cascades to citations.
    """
    raise ValueError(
        "ClaimCitation rows are append-only; delete is not permitted"
    )


class OsintArtifact(Base):
    """Imported external OSINT artifact attached to a case."""

    __tablename__ = "osint_artifacts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, ForeignKey("topic_cases.id"), nullable=False, index=True)
    tool: Mapped[str] = mapped_column(String, nullable=False, index=True)
    artifact_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_path: Mapped[str] = mapped_column(String, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String, nullable=False, index=True)
    raw_text: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    import_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

class EvidenceArtifactLink(Base):
    """Normalized provenance link between evidence and imported artifacts."""

    __tablename__ = "evidence_artifact_links"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    evidence_id: Mapped[str] = mapped_column(
        String, ForeignKey("evidence_items.id"), nullable=False, index=True
    )
    osint_artifact_id: Mapped[str] = mapped_column(
        String, ForeignKey("osint_artifacts.id"), nullable=False, index=True
    )
    relation: Mapped[str] = mapped_column(String, nullable=False, default="derived_from")
    confidence_score: Mapped[float | None] = mapped_column(Float)
    provenance_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)

class WorkflowCheckpoint(Base):
    """Durable checkpoint for resumable case workflow stages."""

    __tablename__ = "workflow_checkpoints"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, ForeignKey("topic_cases.id"), nullable=False, index=True)
    stage_run_id: Mapped[str | None] = mapped_column(String, ForeignKey("case_stage_runs.id"), index=True)
    stage_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    checkpoint_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

class TaxonomyVersion(Base):
    """Versioned taxonomy metadata used by workflow diagnostics and review logic."""

    __tablename__ = "taxonomy_versions"
    __table_args__ = (
        UniqueConstraint("taxonomy_kind", "version", name="uq_taxonomy_kind_version"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    taxonomy_kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String, nullable=False, index=True)
    path: Mapped[str | None] = mapped_column(String)
    checksum: Mapped[str] = mapped_column(String, nullable=False)
    taxonomy_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

class AgentOutput(Base):
    """Persisted typed output for an AI or orchestration stage."""

    __tablename__ = "agent_outputs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, ForeignKey("topic_cases.id"), nullable=False, index=True)
    stage_run_id: Mapped[str | None] = mapped_column(String, ForeignKey("case_stage_runs.id"), index=True)
    stage_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    output_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    taxonomy_version_id: Mapped[str | None] = mapped_column(String, ForeignKey("taxonomy_versions.id"), index=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now)

class ReviewAnnotation(Base):
    """Human-authored annotation, comment, or flag against reviewable case entities."""

    __tablename__ = "review_annotations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, ForeignKey("topic_cases.id"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    annotation_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    author: Mapped[str] = mapped_column(String, nullable=False, default="operator")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

class ReviewAuditEntry(Base):
    """Immutable audit log for human review actions."""

    __tablename__ = "review_audit_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, ForeignKey("topic_cases.id"), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String, nullable=False, default="operator")
    rationale: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

class EvaluationRun(Base):
    """Persisted evaluation result for a case and its current outputs."""

    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, ForeignKey("topic_cases.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed", index=True)
    evaluation_kind: Mapped[str] = mapped_column(String, nullable=False, default="case_quality", index=True)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    model_config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    workflow_version: Mapped[str | None] = mapped_column(String)
    output_version: Mapped[str | None] = mapped_column(String)
    taxonomy_version_id: Mapped[str | None] = mapped_column(String, ForeignKey("taxonomy_versions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
