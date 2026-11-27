"""HTTP DTOs for the frontend-facing API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


AutomationMode = Literal["autonomous", "blocked", "safe"]
CaseStatus = Literal[
    "discovering",
    "processing",
    "investigating",
    "review ready",
    "approved",
    "rejected",
    "monitoring",
    "failed",
]
CaseStage = Literal[
    "BOOTSTRAP",
    "RETRIEVE",
    "TRIAGE",
    "INVESTIGATE",
    "ARBITRATE",
    "REPORT",
    "REVIEW",
]
VerificationStatus = Literal[
    "confirmed",
    "probable",
    "alleged",
    "contested",
    "debunked",
    "unknown",
]


class CaseCounts(BaseModel):
    articles: int
    events: int
    reviewItems: int


class CaseListItem(BaseModel):
    id: str
    query: str
    conflictDomain: str
    status: CaseStatus
    stage: CaseStage
    counts: CaseCounts
    reportPath: str | None = None
    automationMode: AutomationMode
    hasNewMaterial: bool
    openExceptionsCount: int
    lastUpdated: str | None = None


class CaseBanner(BaseModel):
    id: str
    query: str
    conflictDomain: str
    status: CaseStatus
    stage: CaseStage
    counts: CaseCounts
    reportPath: str | None = None
    automationMode: AutomationMode
    hasNewMaterial: bool
    openExceptionsCount: int
    reviewNotes: str | None = None
    lastUpdated: str | None = None


class ClaimEvidenceLinkDTO(BaseModel):
    """One claim/evidence passage plus its diagnostic and policy provenance.

    ``id`` keeps its existing meaning (the **evidence** ID, not the link ID) for
    compatibility. ``relation`` is the raw stored value and is never rewritten;
    every new field below defaults so legacy payloads keep validating.
    """

    id: str
    relation: str
    confidenceScore: float | None = None
    sourceDiversityRank: int | None = None
    title: str | None = None
    publisher: str | None = None
    originUrl: str | None = None
    sourceType: str | None = None
    captureId: str | None = None
    citationId: str | None = None
    quote: str | None = None
    startChar: int | None = None
    endChar: int | None = None
    # Honest default for a link that never had a quote proposal or assessment.
    alignmentStatus: str = "not_provided"
    # Policy-resolved relationship; never inferred from the raw value alone.
    effectiveRelation: str = "uncertain"
    assessmentOrigin: str | None = None
    assessmentVersion: str | None = None
    diagnosticReason: str | None = None


class PartyConsensusDTO(BaseModel):
    unanimous: bool
    supportingParties: list[str] = Field(default_factory=list)
    opposingParties: list[str] = Field(default_factory=list)
    neutralParties: list[str] = Field(default_factory=list)


class ArbiterReasoningDTO(BaseModel):
    isFact: str
    verificationRationale: str
    partyConsensus: PartyConsensusDTO


class SourceStanceBreakdown(BaseModel):
    agreedSources: list[str] = Field(default_factory=list)
    disagreedSources: list[str] = Field(default_factory=list)
    didntReportSources: list[str] = Field(default_factory=list)


class ClaimDTO(BaseModel):
    id: str
    text: str
    verificationStatus: VerificationStatus
    type: Literal["fact", "allegation"]
    controversyScore: float | None = None
    supportCount: int
    opposeCount: int
    sourceDiversityCount: int
    claimSignature: str
    narrativeClusterId: str | None = None
    # The claims table stores no verification provenance, so the honest value is
    # ``unknown`` unless stored evidence proves a legacy row.
    verificationProvenance: str = "unknown"
    arbiterReasoning: ArbiterReasoningDTO | None = None
    partyPositions: dict[str, Literal["for", "against", "neutral"]] = Field(default_factory=dict)
    evidence: list[ClaimEvidenceLinkDTO] = Field(default_factory=list)
    sourceStanceBreakdown: SourceStanceBreakdown = Field(default_factory=SourceStanceBreakdown)


class EvidenceVerificationCheckDTO(BaseModel):
    id: str
    checkType: str
    result: str
    method: str | None = None
    notes: str | None = None
    verifiedBy: str | None = None
    verifiedAt: str | None = None


class EvidenceArtifactDTO(BaseModel):
    id: str
    tool: str
    artifactType: str
    sourcePath: str
    relation: str
    importedAt: str | None = None


class EvidenceLineageDTO(BaseModel):
    caseId: str
    eventId: str | None = None
    caseArticleId: str | None = None
    origin: str


class EvidenceDTO(BaseModel):
    id: str
    title: str | None = None
    originUrl: str | None = None
    canonicalUrl: str | None = None
    publisher: str | None = None
    sourceType: str
    verificationStatus: VerificationStatus
    # Additive: the stored text when it is outside the recorded status set, so a
    # legacy value is visible instead of being collapsed into ``unknown``.
    rawVerificationStatus: str | None = None
    credibilityTier: str | None = None
    requiresHumanReview: bool
    # Recorded publication timestamp of the evidence item (F06 sort key);
    # ``None`` means no date is recorded, never an inferred one.
    publishedAt: str | None = None
    # Pointer to the immutable current capture; the body is never inlined.
    currentCaptureId: str | None = None
    linkedClaims: list[str] = Field(default_factory=list)
    lineage: EvidenceLineageDTO | None = None
    artifacts: list[EvidenceArtifactDTO] = Field(default_factory=list)
    verificationChecks: list[EvidenceVerificationCheckDTO] = Field(default_factory=list)


class ExceptionDTO(BaseModel):
    id: str
    type: str
    message: str
    severity: Literal["high", "medium", "low"]
    status: Literal["open", "deferred", "resolved"]
    recommendedAction: str
    isOpen: bool


class ReviewAnnotationDTO(BaseModel):
    id: str
    targetType: str
    targetId: str
    annotationType: str
    author: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    createdAt: str | None = None


class ReviewAuditEntryDTO(BaseModel):
    id: str
    actionType: str
    targetType: str
    targetId: str
    actor: str
    rationale: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    createdAt: str | None = None


class ReviewActivityDTO(BaseModel):
    annotations: list[ReviewAnnotationDTO] = Field(default_factory=list)
    auditEntries: list[ReviewAuditEntryDTO] = Field(default_factory=list)


# The narrow HITL write surface. These are the only accepted values; the
# service re-checks them so a direct/CLI caller cannot bypass the contract.
REVIEW_DECISIONS = frozenset(
    {"approve", "reject", "defer", "action_required", "exception"}
)
EXCEPTION_ACTIONS = frozenset({"resolve", "defer", "reopen"})
ANNOTATION_TARGET_TYPES = frozenset(
    {"case", "claim", "evidence", "exception", "narrative"}
)
ANNOTATION_TYPES = frozenset({"comment", "flag", "context"})


def _normalize_choice(
    value: str, *, allowed: frozenset[str], field_name: str
) -> str:
    """Trim and lowercase a contract choice, rejecting anything unsupported."""
    normalized = value.strip().lower()
    if normalized not in allowed:
        expected = ", ".join(sorted(allowed))
        raise ValueError(f"{field_name} must be one of: {expected}")
    return normalized


def _require_non_blank(value: str, *, field_name: str) -> str:
    """Trim a free-text field and reject an empty result."""
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be blank")
    return stripped


class ReviewActionRequest(BaseModel):
    decision: str
    notes: str | None = None

    @field_validator("decision")
    @classmethod
    def _normalize_decision(cls, value: str) -> str:
        return _normalize_choice(
            value, allowed=REVIEW_DECISIONS, field_name="decision"
        )


class ExceptionActionRequest(BaseModel):
    action: str
    notes: str | None = None

    @field_validator("action")
    @classmethod
    def _normalize_action(cls, value: str) -> str:
        return _normalize_choice(
            value, allowed=EXCEPTION_ACTIONS, field_name="action"
        )


class AnnotationCreateRequest(BaseModel):
    targetType: str
    targetId: str
    annotationType: str
    content: str
    author: str = "operator"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("targetType")
    @classmethod
    def _normalize_target_type(cls, value: str) -> str:
        return _normalize_choice(
            value, allowed=ANNOTATION_TARGET_TYPES, field_name="targetType"
        )

    @field_validator("annotationType")
    @classmethod
    def _normalize_annotation_type(cls, value: str) -> str:
        return _normalize_choice(
            value, allowed=ANNOTATION_TYPES, field_name="annotationType"
        )

    @field_validator("targetId", "content", "author")
    @classmethod
    def _require_non_blank_text(cls, value: str, info) -> str:
        return _require_non_blank(value, field_name=info.field_name)


class PartyDTO(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str
    overallStance: Literal["for", "against", "neutral", "mixed"]
    isModelInferred: bool
    associatedClaimsCount: int
    investigationData: dict[str, Any] | None = None
    claimsSupported: int = 0
    claimsContested: int = 0


class TimelineEventDTO(BaseModel):
    id: str
    timestamp: str | None = None
    title: str
    summary: str | None = None
    verificationStatus: VerificationStatus
    # Additive: the stored text when it is outside the recorded status set, so a
    # legacy value is visible instead of being collapsed into ``unknown``.
    rawVerificationStatus: str | None = None
    linkedEvidenceCount: int
    locationCountryCode: str | None = None
    locationLat: float | None = None
    locationLon: float | None = None
    workflowRoute: str | None = None
    sourceUrl: str | None = None


class RunHistoryItemDTO(BaseModel):
    id: str
    stage: str
    model: str | None = None
    durationMs: int | None = None
    status: Literal["success", "error", "running", "pending", "skipped"]
    fallbackCount: int
    parseFailureCount: int
    timestamp: str | None = None
    message: str | None = None


class NarrativeDTO(BaseModel):
    id: str
    clusterId: str
    stanceSummary: str
    sourceCount: int
    claimCount: int = 0
    keyThemes: list[str] = Field(default_factory=list)
    mainEntities: list[str] = Field(default_factory=list)


class ReportDTO(BaseModel):
    status: Literal["generated", "pending"]
    markdownPath: str | None = None
    markdownContent: str | None = None
    manifestPath: str | None = None


class OsintArtifactDTO(BaseModel):
    id: str
    tool: str
    artifactType: str
    sourcePath: str
    importedAt: str | None = None
    importMetadata: dict[str, Any] = Field(default_factory=dict)


class TaxonomyDTO(BaseModel):
    id: str
    kind: str
    version: str
    path: str | None = None
    checksum: str


class WorkflowCheckpointDTO(BaseModel):
    id: str
    stageName: str
    checkpointKey: str
    status: str
    summary: str | None = None
    retryCount: int = 0
    payload: dict[str, Any] = Field(default_factory=dict)
    createdAt: str | None = None


class AgentOutputDTO(BaseModel):
    id: str
    stageName: str
    agentName: str
    outputType: str
    summary: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    taxonomyVersionId: str | None = None
    createdAt: str | None = None


class WorkflowDiagnosticsDTO(BaseModel):
    taxonomy: TaxonomyDTO | None = None
    checkpoints: list[WorkflowCheckpointDTO] = Field(default_factory=list)
    agentOutputs: list[AgentOutputDTO] = Field(default_factory=list)


class EvaluationResultDTO(BaseModel):
    id: str
    status: str
    evaluationKind: str
    summary: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    createdAt: str | None = None


class EvaluationSummaryDTO(BaseModel):
    latest: EvaluationResultDTO | None = None
    history: list[EvaluationResultDTO] = Field(default_factory=list)


class MonitoringSummaryDTO(BaseModel):
    cases: dict[str, Any] = Field(default_factory=dict)
    review: dict[str, Any] = Field(default_factory=dict)
    pipeline: dict[str, Any] = Field(default_factory=dict)
    intake: dict[str, Any] = Field(default_factory=dict)
    evaluation: dict[str, Any] = Field(default_factory=dict)


class CaseTabs(BaseModel):
    claims: list[ClaimDTO] = Field(default_factory=list)
    evidence: list[EvidenceDTO] = Field(default_factory=list)
    exceptions: list[ExceptionDTO] = Field(default_factory=list)
    parties: list[PartyDTO] = Field(default_factory=list)
    timeline: list[TimelineEventDTO] = Field(default_factory=list)
    runHistory: list[RunHistoryItemDTO] = Field(default_factory=list)
    narratives: list[NarrativeDTO] = Field(default_factory=list)
    osintArtifacts: list[OsintArtifactDTO] = Field(default_factory=list)
    workflow: WorkflowDiagnosticsDTO = Field(default_factory=WorkflowDiagnosticsDTO)
    report: ReportDTO


class CaseDetailResponse(BaseModel):
    case: CaseBanner
    tabs: CaseTabs


class ClaimsOverviewResponse(BaseModel):
    claims: list[ClaimDTO] = Field(default_factory=list)
    narratives: list[NarrativeDTO] = Field(default_factory=list)


class CaptureSummaryDTO(BaseModel):
    """One immutable capture version: metadata, hash and length only."""

    id: str
    evidenceId: str | None = None
    textSha256: str | None = None
    normalizedTextSha256: str | None = None
    normalizationVersion: str | None = None
    captureKind: str | None = None
    recordedAt: str | None = None
    observedAt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    charLength: int = 0
    isCurrent: bool = False


class CaptureWindowDTO(BaseModel):
    """One bounded code-point window of a capture (the only text-bearing DTO)."""

    captureId: str
    evidenceId: str
    start: int
    length: int
    totalLength: int
    text: str
    textSha256: str | None = None
    captureKind: str | None = None
    recordedAt: str | None = None
    observedAt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceSourceDTO(BaseModel):
    """Source metadata for one evidence item (no capture bodies)."""

    id: str
    eventId: str | None = None
    caseArticleId: str | None = None
    evidenceType: str | None = None
    sourceType: str | None = None
    title: str | None = None
    publisher: str | None = None
    originUrl: str | None = None
    canonicalUrl: str | None = None
    publishedAt: str | None = None
    verificationStatus: VerificationStatus = "unknown"
    credibilityTier: str | None = None
    requiresHumanReview: bool = False
    captureMetadata: dict[str, Any] = Field(default_factory=dict)


class CitationDTO(BaseModel):
    """Frozen validated passage; resolvable without a live claim/link."""

    id: str
    caseId: str
    captureId: str | None = None
    evidenceId: str | None = None
    originalClaimId: str | None = None
    claimSignature: str | None = None
    claimText: str
    relationship: str
    quote: str
    startChar: int | None = None
    endChar: int | None = None
    alignmentStatus: str = "not_provided"
    alignmentVersion: str | None = None
    assessmentOrigin: str | None = None
    assessmentVersion: str | None = None
    assessmentMetadata: dict[str, Any] = Field(default_factory=dict)
    recordedAt: str | None = None
    liveClaimPresent: bool = False
    liveClaimId: str | None = None
    evidence: EvidenceSourceDTO | None = None
    capture: CaptureSummaryDTO | None = None


class ClaimCountsDTO(BaseModel):
    supportCount: int = 0
    opposeCount: int = 0
    sourceDiversityCount: int = 0
    evidenceCount: int = 0


class SnapshotLiveStateDTO(BaseModel):
    """Whether a frozen snapshot entity still exists in the current rows.

    Read-only, factual comparison; it never claims who changed anything. Fields
    that do not apply to a given entity type stay null.
    """

    present: bool
    claimSignature: str | None = None
    textMatchesSnapshot: bool | None = None
    currentCaptureId: str | None = None
    currentCaptureMatchesSnapshot: bool | None = None


class ClaimDetailDTO(BaseModel):
    """One claim with its evidence passages and policy-derived counts."""

    id: str
    caseId: str
    eventId: str | None = None
    claimText: str
    claimSignature: str
    verificationStatus: VerificationStatus = "unknown"
    verificationProvenance: str = "unknown"
    type: Literal["fact", "allegation"] = "allegation"
    controversyScore: float | None = None
    narrativeClusterId: str | None = None
    partyPositions: dict[str, Any] = Field(default_factory=dict)
    counts: ClaimCountsDTO = Field(default_factory=ClaimCountsDTO)
    passages: list[ClaimEvidenceLinkDTO] = Field(default_factory=list)
    # Historical selection (null on a current-state read).
    snapshotId: str | None = None
    liveState: SnapshotLiveStateDTO | None = None


class EvidenceClaimReferenceDTO(BaseModel):
    """Reference to a claim that is attached to an evidence item."""

    claimId: str
    claimText: str
    claimSignature: str | None = None
    linkId: str | None = None
    effectiveRelation: str = "uncertain"
    relation: str | None = None
    alignmentStatus: str = "not_provided"
    citationId: str | None = None
    captureId: str | None = None
    quote: str | None = None
    startChar: int | None = None
    endChar: int | None = None
    diagnosticReason: str | None = None


class EvidenceDetailDTO(EvidenceSourceDTO):
    """One evidence item with its capture list and claim references.

    Deliberately carries no capture bodies; text is only reachable through
    ``GET /evidence/{evidence_id}/captures/{capture_id}``.
    """

    currentCaptureId: str | None = None
    captures: list[CaptureSummaryDTO] = Field(default_factory=list)
    relatedClaims: list[EvidenceClaimReferenceDTO] = Field(default_factory=list)
    # Historical selection (null/empty on a current-state read).
    snapshotId: str | None = None
    unavailableCaptureIds: list[str] = Field(default_factory=list)
    liveState: SnapshotLiveStateDTO | None = None


class SourcePolicyDTO(BaseModel):
    """Published methodology for source dependency grouping (policy v1)."""

    version: str
    urlNormalization: list[str] = Field(default_factory=list)
    publisherIdentity: list[str] = Field(default_factory=list)
    dependencyEdges: list[str] = Field(default_factory=list)
    textFingerprint: str
    textFingerprintNormalization: str
    minCopyNonWhitespaceCodePoints: int = 200
    limitations: list[str] = Field(default_factory=list)


class SourceMemberDTO(BaseModel):
    """One evidence/capture record inside a dependency group."""

    evidenceId: str
    publisher: str | None = None
    publisherKey: str | None = None
    publisherKeyProvisional: bool = False
    host: str | None = None
    originUrl: str | None = None
    canonicalUrl: str | None = None
    sourceUrl: str | None = None
    caseArticleId: str | None = None
    explicitOriginKey: str | None = None
    captureId: str | None = None
    captureKind: str | None = None
    captureTextSha256: str | None = None
    captureNormalizedTextSha256: str | None = None
    captureCharLength: int | None = None
    recordedAt: str | None = None
    observedAt: str | None = None
    copyFingerprint: str | None = None
    copyNonWhitespaceCount: int = 0
    dependencyReasons: list[str] = Field(default_factory=list)


class SourceDependencyGroupDTO(BaseModel):
    """One connected component, with reasons and inspectable membership."""

    id: str
    reasons: list[str] = Field(default_factory=list)
    publisherKeys: list[str] = Field(default_factory=list)
    evidenceCount: int = 0
    members: list[SourceMemberDTO] = Field(default_factory=list)


class PublisherCountDTO(BaseModel):
    """Observed evidence count for one known publisher identity."""

    publisherKey: str
    publisher: str | None = None
    evidenceCount: int = 0
    dependencyGroupCount: int = 0
    provisional: bool = False


class SourceSummaryDTO(BaseModel):
    """Observed publishers plus dependency groups; never an independence score."""

    caseId: str
    scope: Literal["case", "claim"]
    claimId: str | None = None
    claimSignature: str | None = None
    evidenceCount: int = 0
    distinctPublisherCount: int = 0
    dependencyGroupCount: int = 0
    unknownPublisherCount: int = 0
    independenceStatus: Literal["unknown", "dependency_detected"] = "unknown"
    policy: SourcePolicyDTO
    publisherCounts: list[PublisherCountDTO] = Field(default_factory=list)
    groups: list[SourceDependencyGroupDTO] = Field(default_factory=list)


class ComparisonAnalysisScopeDTO(BaseModel):
    """The body region the collector actually supplied to analysis."""

    status: str | None = None
    startChar: int | None = None
    endChar: int | None = None
    bodyCharCount: int | None = None
    inputLimit: int | None = None
    sourceAvailable: bool | None = None
    reason: str | None = None


class ComparisonCoverageDTO(BaseModel):
    """Explicit capture-link attribution and historical-availability state."""

    linkedClaimCount: int = 0
    attributedClaimCount: int = 0
    attributedLinkCount: int = 0
    otherCaptureLinkCount: int = 0
    unattributedLinkCount: int = 0
    claimLinkageStatus: Literal[
        "available", "historical_unavailable", "unattributed_legacy", "empty"
    ] = "empty"
    historicalAnalysisAvailable: bool = True
    caveat: str | None = None


class ComparisonSideDTO(BaseModel):
    """One pinned evidence/capture side of a comparison (never capture bodies)."""

    evidenceId: str
    captureId: str
    title: str | None = None
    publisher: str | None = None
    originUrl: str | None = None
    canonicalUrl: str | None = None
    publishedAt: str | None = None
    sourceType: str | None = None
    verificationStatus: str | None = None
    captureKind: str | None = None
    recordedAt: str | None = None
    observedAt: str | None = None
    textSha256: str | None = None
    charLength: int = 0
    analysisScope: ComparisonAnalysisScopeDTO | None = None
    publisherKey: str | None = None
    publisherKeyProvisional: bool = False
    host: str | None = None
    sourceUrl: str | None = None
    copyFingerprint: str | None = None
    copyNonWhitespaceCount: int = 0
    coverage: ComparisonCoverageDTO


class ComparisonPassageDTO(BaseModel):
    """One persisted capture-linked passage on one side of a comparison row."""

    claimId: str | None = None
    claimText: str = ""
    claimSignature: str | None = None
    linkId: str | None = None
    citationId: str | None = None
    captureId: str | None = None
    relationship: str = "uncertain"
    rawRelation: str | None = None
    alignmentStatus: str = "not_provided"
    quote: str | None = None
    startChar: int | None = None
    endChar: int | None = None
    assessmentOrigin: str | None = None
    assessmentVersion: str | None = None
    diagnosticReason: str | None = None


class ComparisonClaimSideDTO(BaseModel):
    """A claim's presence in one selected capture."""

    claimIds: list[str] = Field(default_factory=list)
    claimId: str | None = None
    claimText: str = ""
    claimSignature: str | None = None
    passages: list[ComparisonPassageDTO] = Field(default_factory=list)


class ComparisonContradictionDTO(BaseModel):
    """Only explicitly assessed contradiction; never textual difference."""

    explicit: bool = False
    conflict: bool = False
    leftRelationships: list[str] = Field(default_factory=list)
    rightRelationships: list[str] = Field(default_factory=list)
    reason: str = "No explicitly assessed contradiction."


class ComparisonRowDTO(BaseModel):
    """One exact-signature claim alignment row."""

    claimSignature: str
    claimText: str = ""
    status: Literal["shared", "left_only", "right_only"]
    left: ComparisonClaimSideDTO | None = None
    right: ComparisonClaimSideDTO | None = None
    contradiction: ComparisonContradictionDTO
    caveat: str | None = None


class ComparisonClaimsPageDTO(BaseModel):
    """Deterministically ordered, paginated comparison rows."""

    rows: list[ComparisonRowDTO] = Field(default_factory=list)
    total: int = 0
    limit: int = 25
    offset: int = 0
    hasMore: bool = False


class ComparisonDependencyDTO(BaseModel):
    """P01 dependency/copy warning for the two pinned records."""

    detected: bool = False
    copyDetected: bool = False
    reasons: list[str] = Field(default_factory=list)
    leftPublisherKey: str | None = None
    rightPublisherKey: str | None = None
    message: str


class ComparisonPolicyDTO(BaseModel):
    version: str
    claimIdentity: str
    alignment: str
    dependencyPolicy: str
    limitations: list[str] = Field(default_factory=list)


class ComparisonDTO(BaseModel):
    """Deterministic two-capture comparison response."""

    caseId: str
    left: ComparisonSideDTO
    right: ComparisonSideDTO
    leftCaptureId: str
    rightCaptureId: str
    dependency: ComparisonDependencyDTO
    claims: ComparisonClaimsPageDTO
    policy: ComparisonPolicyDTO
    caveats: list[str] = Field(default_factory=list)
    # Set only when both sides were resolved from a pinned snapshot observation.
    snapshotId: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]


class InvestigationRunDTO(BaseModel):
    """One grouped investigation invocation (distinct from stage attempts)."""

    id: str
    caseId: str
    sequence: int
    trigger: str
    requestedStartStage: str | None = None
    status: str
    coverage: str
    startedAt: str | None = None
    completedAt: str | None = None
    predecessorRunId: str | None = None
    baselineSnapshotId: str | None = None
    resultSnapshotId: str | None = None
    snapshotId: str | None = None
    errorMessage: str | None = None


class InvestigationRunDetailDTO(InvestigationRunDTO):
    parameterSnapshot: dict[str, Any] = Field(default_factory=dict)
    coverageDetails: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None


class InvestigationRunListDTO(BaseModel):
    items: list[InvestigationRunDTO] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
    hasMore: bool


class ChangeItemDTO(BaseModel):
    """One typed semantic change; before/after are observations, not verdicts."""

    type: str
    entityType: str
    entityId: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    #: Grouped run recorded as the entity's origin, or null when unknown. It is a
    #: provenance reference, not a statement about who caused a field change.
    originRunId: str | None = None
    #: The run whose successful observation produced this delta item.
    observedByRunId: str | None = None
    observedAt: str | None = None


class RunChangesDTO(BaseModel):
    availability: Literal["initial", "ready", "pending", "unavailable"]
    baselineSnapshotId: str | None = None
    targetSnapshotId: str | None = None
    coverage: str
    coverageNote: str | None = None
    items: list[ChangeItemDTO] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
    hasMore: bool


ArtifactType = Literal["report_markdown", "report_json", "execution_manifest"]
ArtifactChecksumKind = Literal["payload_json", "unknown"]


class ArtifactDescriptorDTO(BaseModel):
    """One published run artifact; never exposes a filesystem path.

    ``recordedChecksum`` is the writer's canonical **payload** checksum, not a
    checksum of the file bytes; ``checksumKind`` says whether that value could
    be confirmed as the payload checksum (``payload_json``) or stays
    ``unknown``. ``downloadUrl`` is a relative API URL and is not a
    file-existence claim -- bytes are checked when downloading.
    """

    artifactId: str
    type: ArtifactType
    displayName: str
    downloadUrl: str
    recordedChecksum: str | None = None
    checksumKind: ArtifactChecksumKind


class SnapshotSummaryDTO(BaseModel):
    """Snapshot metadata/counts; entity bodies resolve through detail readers."""

    id: str
    caseId: str
    investigationRunId: str
    baselineSnapshotId: str | None = None
    schemaVersion: str
    identityVersion: str
    policyVersion: str
    semanticHash: str
    createdAt: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    observedAt: str | None = None


SnapshotComparisonEntityType = Literal[
    "case",
    "articles",
    "events",
    "claims",
    "links",
    "citations",
    "evidence",
    "captures",
    "reviews",
    "exceptions",
    "parties",
    "partyInvestigations",
    "narratives",
]
SnapshotComparisonChangeKind = Literal[
    "entity_added", "entity_absent", "field_changed"
]
SnapshotComparisonUnavailableReason = Literal[
    "incompatible_schema",
    "incompatible_identity",
    "incompatible_policy",
    "unknown_version",
    "payload_unreadable",
]


class SnapshotComparisonSideDTO(BaseModel):
    """Metadata of one side of an ad-hoc comparison, recorded independently."""

    sequence: int
    #: Snapshot-save time, never the source-observation time.
    createdAt: str | None = None
    schemaVersion: str
    identityVersion: str
    policyVersion: str


class SnapshotComparisonRefDTO(BaseModel):
    """Frozen references for one side; only ids that side actually recorded."""

    snapshotId: str
    claimId: str | None = None
    evidenceId: str | None = None
    captureId: str | None = None
    citationId: str | None = None


class SnapshotComparisonItemRefsDTO(BaseModel):
    baseline: SnapshotComparisonRefDTO
    target: SnapshotComparisonRefDTO


class SnapshotComparisonItemDTO(BaseModel):
    """One entity-level difference between two frozen observations.

    ``entity_absent`` means absent from the later observation only; it is never
    a deletion, retraction or "no longer extracted" verdict. ``before``/``after``
    are frozen semantic-field objects, never live ORM rows or capture bodies.
    """

    entityType: SnapshotComparisonEntityType
    entityId: str
    changeKind: SnapshotComparisonChangeKind
    changedFields: list[str] = Field(default_factory=list)
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    refs: SnapshotComparisonItemRefsDTO


class SnapshotComparisonDTO(BaseModel):
    """Ad-hoc comparison of two snapshots; distinct from recorded run changes."""

    mode: Literal["ad_hoc"]
    comparisonPolicyVersion: str
    baselineSnapshotId: str
    targetSnapshotId: str
    baselineRunId: str
    targetRunId: str
    baselineCoverage: str
    targetCoverage: str
    baselineMetadata: SnapshotComparisonSideDTO
    targetMetadata: SnapshotComparisonSideDTO
    availability: Literal["ready", "unavailable"]
    #: ``None`` exactly when the comparison is ready.
    unavailableReason: SnapshotComparisonUnavailableReason | None = None
    items: list[SnapshotComparisonItemDTO] = Field(default_factory=list)
    #: ``None`` when unavailable; an integer (including 0) when ready.
    total: int | None = None
    limit: int
    offset: int
    hasMore: bool


SearchResultType = Literal["claim", "evidence"]
SearchMatchedField = Literal["title", "body"]


class SearchAppliedFiltersDTO(BaseModel):
    """Echo of the effective filters; ``null`` means "not applied".

    ``type`` is ``"claim"`` when a ``status`` filter was supplied without a
    ``type``, because that is the effective narrowing.
    """

    type: SearchResultType | None = None
    publisher: str | None = None
    status: VerificationStatus | None = None
    publishedFrom: str | None = None
    publishedTo: str | None = None


class SearchResultItemDTO(BaseModel):
    """One typed lexical hit. ``snippet`` is plain text, never FTS HTML."""

    resultType: SearchResultType
    id: str
    claimId: str | None = None
    evidenceId: str | None = None
    eventId: str | None = None
    captureId: str | None = None
    title: str | None = None
    snippet: str
    matchedField: SearchMatchedField
    publisher: str | None = None
    status: VerificationStatus | None = None
    publishedAt: str | None = None


class SearchResponseDTO(BaseModel):
    caseId: str
    query: str
    total: int
    limit: int
    offset: int
    appliedFilters: SearchAppliedFiltersDTO
    items: list[SearchResultItemDTO] = Field(default_factory=list)
