export type CaseStage =
  | 'BOOTSTRAP'
  | 'RETRIEVE'
  | 'TRIAGE'
  | 'INVESTIGATE'
  | 'ARBITRATE'
  | 'REPORT'
  | 'REVIEW';

export type CaseStatus =
  | 'discovering'
  | 'processing'
  | 'investigating'
  | 'review ready'
  | 'approved'
  | 'rejected'
  | 'monitoring'
  | 'failed';

export type VerificationStatus =
  | 'confirmed'
  | 'probable'
  | 'alleged'
  | 'contested'
  | 'debunked'
  | 'unknown';

export interface TopicCaseCounts {
  articles: number;
  events: number;
  reviewItems: number;
}

export interface TopicCase {
  id: string;
  query: string;
  conflictDomain: string;
  status: CaseStatus;
  stage: CaseStage;
  counts: TopicCaseCounts;
  reportPath?: string | null;
  automationMode: 'autonomous' | 'blocked' | 'safe';
  hasNewMaterial: boolean;
  openExceptionsCount: number;
  lastUpdated: string | null;
}

export interface ClaimEvidenceLink {
  id: string;
  relation: string;
  confidenceScore: number | null;
  sourceDiversityRank: number | null;
  title: string | null;
  publisher: string | null;
  originUrl: string | null;
  sourceType: string | null;
  // Additive E03 inspector fields. `relation` above stays the raw stored value;
  // `effectiveRelation` is the policy-resolved reading (never inflated support).
  captureId?: string | null;
  citationId?: string | null;
  quote?: string | null;
  startChar?: number | null;
  endChar?: number | null;
  alignmentStatus?: AlignmentStatus;
  effectiveRelation?: EffectiveRelation;
  assessmentOrigin?: string | null;
  assessmentVersion?: string | null;
  diagnosticReason?: string | null;
}

export type AlignmentStatus =
  | 'exact'
  | 'ambiguous'
  | 'no_match'
  | 'not_provided'
  | 'source_unavailable';

export type EffectiveRelation =
  | 'reported_by'
  | 'supports'
  | 'contradicts'
  | 'uncertain';

export type VerificationProvenance = 'unknown' | 'legacy_unknown';

export interface PartyConsensus {
  unanimous: boolean;
  supportingParties: string[];
  opposingParties: string[];
  neutralParties: string[];
}

export interface ArbiterReasoning {
  isFact: string;
  verificationRationale: string;
  partyConsensus: PartyConsensus;
}

export interface SourceStanceBreakdown {
  agreedSources: string[];
  disagreedSources: string[];
  didntReportSources: string[];
}

export interface Claim {
  id: string;
  text: string;
  verificationStatus: VerificationStatus;
  type: 'fact' | 'allegation';
  controversyScore: number | null;
  supportCount: number;
  opposeCount: number;
  sourceDiversityCount: number;
  claimSignature: string;
  narrativeClusterId: string | null;
  // Evidence-workbench provenance (E02/E03): absent on legacy payloads.
  verificationProvenance?: VerificationProvenance;
  // Review/investigation fields (origin/main). Optional so legacy payloads
  // and older fixtures still typecheck.
  arbiterReasoning?: ArbiterReasoning | null;
  partyPositions?: Record<string, 'for' | 'against' | 'neutral'>;
  // Per-party argument framing, when the arbiter attached one.
  position?: 'for' | 'against' | 'neutral' | null;
  evidenceFromParty?: string | null;
  counterArgument?: string | null;
  alternativePerspective?: string | null;
  evidence: ClaimEvidenceLink[];
  sourceStanceBreakdown?: SourceStanceBreakdown;
}

export interface EvidenceVerificationCheck {
  id: string;
  checkType: string;
  result: string;
  method: string | null;
  notes: string | null;
  verifiedBy: string | null;
  verifiedAt: string | null;
}

export interface Evidence {
  id: string;
  title: string | null;
  originUrl: string | null;
  canonicalUrl: string | null;
  publisher: string | null;
  sourceType: string;
  verificationStatus: VerificationStatus;
  credibilityTier: string | null;
  requiresHumanReview: boolean;
  /** Pointer to the immutable current capture. Capture text is never inlined. */
  currentCaptureId?: string | null;
  linkedClaims: string[];
  // Merge-added review fields: optional so pre-review payloads/fixtures still typecheck.
  lineage?: {
    caseId: string;
    eventId: string | null;
    caseArticleId: string | null;
    origin: string;
  } | null;
  artifacts?: Array<{
    id: string;
    tool: string;
    artifactType: string;
    sourcePath: string;
    relation: string;
    importedAt: string | null;
  }>;
  verificationChecks: EvidenceVerificationCheck[];
}

export interface Exception {
  id: string;
  type: string;
  message: string;
  severity: 'high' | 'medium' | 'low';
  status: 'open' | 'deferred' | 'resolved';
  recommendedAction: string;
  isOpen: boolean;
}

export interface ReviewAnnotation {
  id: string;
  targetType: string;
  targetId: string;
  annotationType: string;
  author: string;
  content: string;
  metadata: Record<string, unknown>;
  createdAt: string | null;
}

export interface ReviewAuditEntry {
  id: string;
  actionType: string;
  targetType: string;
  targetId: string;
  actor: string;
  rationale: string | null;
  metadata: Record<string, unknown>;
  createdAt: string | null;
}

export interface ReviewActivity {
  annotations: ReviewAnnotation[];
  auditEntries: ReviewAuditEntry[];
}

export interface Party {
  id: string;
  name: string;
  aliases: string[];
  description: string;
  overallStance: 'for' | 'against' | 'neutral' | 'mixed';
  isModelInferred: boolean;
  associatedClaimsCount: number;
  investigationData: Record<string, unknown> | null;
  claimsSupported: number;
  claimsContested: number;
}

export interface TimelineEvent {
  id: string;
  timestamp: string | null;
  title: string;
  summary: string | null;
  verificationStatus: VerificationStatus;
  linkedEvidenceCount: number;
  locationCountryCode?: string | null;
  locationLat?: number | null;
  locationLon?: number | null;
  workflowRoute?: string | null;
  sourceUrl?: string | null;
}

export interface RunHistoryItem {
  id: string;
  stage: string;
  model: string | null;
  durationMs: number | null;
  status: 'success' | 'error' | 'running' | 'pending' | 'skipped';
  fallbackCount: number;
  parseFailureCount: number;
  timestamp: string | null;
  message: string | null;
}

export interface ReportData {
  status: 'generated' | 'pending';
  markdownPath: string | null;
  markdownContent: string | null;
  manifestPath: string | null;
}

export interface OsintArtifact {
  id: string;
  tool: string;
  artifactType: string;
  sourcePath: string;
  importedAt: string | null;
  importMetadata: Record<string, unknown>;
}

export interface WorkflowCheckpoint {
  id: string;
  stageName: string;
  checkpointKey: string;
  status: string;
  summary: string | null;
  retryCount: number;
  payload: Record<string, unknown>;
  createdAt: string | null;
}

export interface AgentOutput {
  id: string;
  stageName: string;
  agentName: string;
  outputType: string;
  summary: string | null;
  payload: Record<string, unknown>;
  taxonomyVersionId: string | null;
  createdAt: string | null;
}

export interface WorkflowDiagnostics {
  taxonomy: {
    id: string;
    kind: string;
    version: string;
    path: string | null;
    checksum: string;
  } | null;
  checkpoints: WorkflowCheckpoint[];
  agentOutputs: AgentOutput[];
}

export interface EvaluationResult {
  id: string;
  status: string;
  evaluationKind: string;
  summary: Record<string, unknown>;
  metrics: Record<string, unknown>;
  createdAt: string | null;
}

export interface EvaluationSummary {
  latest: EvaluationResult;
  history: EvaluationResult[];
}

export interface MonitoringSummary {
  cases: Record<string, number>;
  review: Record<string, number>;
  pipeline: Record<string, number>;
  intake: Record<string, number>;
  evaluation: Record<string, number | null>;
}

export interface NarrativeCluster {
  id: string;
  clusterId: string;
  stanceSummary: string;
  sourceCount: number;
  claimCount: number;
  keyThemes: string[];
  mainEntities: string[];
}

export interface ClaimsOverview {
  claims: Claim[];
  narratives: NarrativeCluster[];
}

/** One immutable capture version: metadata, hash and code-point length only. */
export interface CaptureSummary {
  id: string;
  evidenceId: string | null;
  textSha256: string | null;
  normalizedTextSha256: string | null;
  normalizationVersion: string | null;
  captureKind: string | null;
  recordedAt: string | null;
  observedAt: string | null;
  metadata: Record<string, unknown>;
  charLength: number;
  isCurrent: boolean;
}

/** The only response that carries captured text, and only for one window. */
export interface CaptureWindow {
  captureId: string;
  evidenceId: string;
  start: number;
  length: number;
  totalLength: number;
  text: string;
  textSha256: string | null;
  captureKind: string | null;
  recordedAt: string | null;
  observedAt: string | null;
  metadata: Record<string, unknown>;
}

/** Source metadata for one evidence item (no capture bodies). */
export interface EvidenceSource {
  id: string;
  eventId: string | null;
  caseArticleId: string | null;
  evidenceType: string | null;
  sourceType: string | null;
  title: string | null;
  publisher: string | null;
  originUrl: string | null;
  canonicalUrl: string | null;
  publishedAt: string | null;
  verificationStatus: VerificationStatus;
  credibilityTier: string | null;
  requiresHumanReview: boolean;
  captureMetadata: Record<string, unknown>;
}

/** Reference to a claim attached to an evidence item. */
export interface EvidenceClaimReference {
  claimId: string;
  claimText: string;
  claimSignature: string | null;
  linkId: string | null;
  effectiveRelation: EffectiveRelation;
  relation: string | null;
  alignmentStatus: AlignmentStatus;
  citationId: string | null;
  captureId: string | null;
  quote: string | null;
  startChar: number | null;
  endChar: number | null;
  diagnosticReason: string | null;
}

/**
 * Frozen-vs-current comparison for a snapshot entity (R03b).
 *
 * Present only when a `snapshotId` selected a historical observation. It reports
 * what the current row is, never who changed anything or whether a claim is true.
 */
export interface SnapshotLiveState {
  present: boolean;
  claimSignature: string | null;
  textMatchesSnapshot: boolean | null;
  currentCaptureId: string | null;
  currentCaptureMatchesSnapshot: boolean | null;
}

/** `GET /api/cases/{case_id}/evidence/{evidence_id}` (no capture bodies). */
export interface EvidenceDetail extends EvidenceSource {
  currentCaptureId: string | null;
  captures: CaptureSummary[];
  relatedClaims: EvidenceClaimReference[];
  /** Set when the read was resolved from a pinned snapshot observation. */
  snapshotId?: string | null;
  /** Snapshot capture references whose immutable body/hash cannot be verified. */
  unavailableCaptureIds?: string[];
  liveState?: SnapshotLiveState | null;
}

/** `GET /api/cases/{case_id}/citations/{citation_id}`. */
export interface CitationDetail {
  id: string;
  caseId: string;
  captureId: string | null;
  evidenceId: string | null;
  originalClaimId: string | null;
  claimSignature: string | null;
  claimText: string;
  relationship: EffectiveRelation;
  quote: string;
  startChar: number | null;
  endChar: number | null;
  alignmentStatus: AlignmentStatus;
  alignmentVersion: string | null;
  assessmentOrigin: string | null;
  assessmentVersion: string | null;
  assessmentMetadata: Record<string, unknown>;
  recordedAt: string | null;
  /** False once the live claim/link was rewritten or removed. */
  liveClaimPresent: boolean;
  liveClaimId: string | null;
  evidence: EvidenceSource | null;
  capture: CaptureSummary | null;
}

export interface ClaimCounts {
  supportCount: number;
  opposeCount: number;
  sourceDiversityCount: number;
  evidenceCount: number;
}

/** `GET /api/cases/{case_id}/claims/{claim_id}`. */
export interface ClaimDetail {
  id: string;
  caseId: string;
  eventId: string | null;
  claimText: string;
  claimSignature: string;
  verificationStatus: VerificationStatus;
  verificationProvenance: VerificationProvenance;
  type: 'fact' | 'allegation';
  controversyScore: number | null;
  narrativeClusterId: string | null;
  partyPositions: Record<string, unknown>;
  counts: ClaimCounts;
  passages: ClaimEvidenceLink[];
  /** Set when the read was resolved from a pinned snapshot observation. */
  snapshotId?: string | null;
  liveState?: SnapshotLiveState | null;
}

export interface CaseDetail {
  case: TopicCase & {
    reviewNotes?: string | null;
  };
  tabs: {
    claims: Claim[];
    evidence: Evidence[];
    exceptions: Exception[];
    parties: Party[];
    timeline: TimelineEvent[];
    runHistory: RunHistoryItem[];
    narratives: NarrativeCluster[];
    osintArtifacts: OsintArtifact[];
    workflow: WorkflowDiagnostics;
    report: ReportData;
  };
}

/** P02 comparison read model (GET /api/cases/{id}/comparison). */
export type ComparisonRowStatus = 'shared' | 'left_only' | 'right_only';

export type ComparisonLinkageStatus =
  | 'available'
  | 'historical_unavailable'
  | 'unattributed_legacy'
  | 'empty';

export interface ComparisonAnalysisScope {
  status: string | null;
  startChar: number | null;
  endChar: number | null;
  bodyCharCount: number | null;
  inputLimit: number | null;
  sourceAvailable: boolean | null;
  reason: string | null;
}

export interface ComparisonCoverage {
  linkedClaimCount: number;
  attributedClaimCount: number;
  attributedLinkCount: number;
  otherCaptureLinkCount: number;
  unattributedLinkCount: number;
  claimLinkageStatus: ComparisonLinkageStatus;
  historicalAnalysisAvailable: boolean;
  caveat: string | null;
}

export interface ComparisonSide {
  evidenceId: string;
  captureId: string;
  title: string | null;
  publisher: string | null;
  originUrl: string | null;
  canonicalUrl: string | null;
  publishedAt: string | null;
  sourceType: string | null;
  verificationStatus: string | null;
  captureKind: string | null;
  recordedAt: string | null;
  observedAt: string | null;
  textSha256: string | null;
  charLength: number;
  analysisScope: ComparisonAnalysisScope | null;
  publisherKey: string | null;
  publisherKeyProvisional: boolean;
  host: string | null;
  sourceUrl: string | null;
  copyFingerprint: string | null;
  copyNonWhitespaceCount: number;
  coverage: ComparisonCoverage;
}

export interface ComparisonPassage {
  claimId: string | null;
  claimText: string;
  claimSignature: string | null;
  linkId: string | null;
  citationId: string | null;
  captureId: string | null;
  relationship: string;
  rawRelation: string | null;
  alignmentStatus: string;
  quote: string | null;
  startChar: number | null;
  endChar: number | null;
  assessmentOrigin: string | null;
  assessmentVersion: string | null;
  diagnosticReason: string | null;
}

export interface ComparisonClaimSide {
  claimIds: string[];
  claimId: string | null;
  claimText: string;
  claimSignature: string | null;
  passages: ComparisonPassage[];
}

export interface ComparisonContradiction {
  explicit: boolean;
  conflict: boolean;
  leftRelationships: string[];
  rightRelationships: string[];
  reason: string;
}

export interface ComparisonRow {
  claimSignature: string;
  claimText: string;
  status: ComparisonRowStatus;
  left: ComparisonClaimSide | null;
  right: ComparisonClaimSide | null;
  contradiction: ComparisonContradiction;
  caveat: string | null;
}

export interface ComparisonClaimsPage {
  rows: ComparisonRow[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
}

export interface ComparisonDependency {
  detected: boolean;
  copyDetected: boolean;
  reasons: string[];
  leftPublisherKey: string | null;
  rightPublisherKey: string | null;
  message: string;
}

export interface ComparisonPolicy {
  version: string;
  claimIdentity: string;
  alignment: string;
  dependencyPolicy: string;
  limitations: string[];
}

export interface Comparison {
  caseId: string;
  left: ComparisonSide;
  right: ComparisonSide;
  leftCaptureId: string;
  rightCaptureId: string;
  dependency: ComparisonDependency;
  claims: ComparisonClaimsPage;
  policy: ComparisonPolicy;
  caveats: string[];
  /** Set when both sides were resolved from a pinned snapshot observation. */
  snapshotId?: string | null;
}
