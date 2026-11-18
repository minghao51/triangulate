"""HTTP DTOs for the frontend-facing API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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
    credibilityTier: str | None = None
    requiresHumanReview: bool
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


class ReviewActionRequest(BaseModel):
    decision: str
    notes: str | None = None


class ExceptionActionRequest(BaseModel):
    action: str
    notes: str | None = None


class AnnotationCreateRequest(BaseModel):
    targetType: str
    targetId: str
    annotationType: str
    content: str
    author: str = "operator"
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    latest: EvaluationResultDTO
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
    originRunId: str | None = None
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
