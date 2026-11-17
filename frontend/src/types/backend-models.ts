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
  verificationProvenance?: VerificationProvenance;
  evidence: ClaimEvidenceLink[];
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

export interface Party {
  id: string;
  name: string;
  aliases: string[];
  description: string;
  overallStance: 'for' | 'against' | 'neutral' | 'mixed';
  isModelInferred: boolean;
  associatedClaimsCount: number;
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

export interface NarrativeCluster {
  id: string;
  clusterId: string;
  stanceSummary: string;
  sourceCount: number;
  claimCount: number;
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

/** `GET /api/cases/{case_id}/evidence/{evidence_id}` (no capture bodies). */
export interface EvidenceDetail extends EvidenceSource {
  currentCaptureId: string | null;
  captures: CaptureSummary[];
  relatedClaims: EvidenceClaimReference[];
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
    report: ReportData;
  };
}
