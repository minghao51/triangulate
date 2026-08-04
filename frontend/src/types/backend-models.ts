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
}

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
  arbiterReasoning: ArbiterReasoning | null;
  partyPositions: Record<string, 'for' | 'against' | 'neutral'>;
  evidence: ClaimEvidenceLink[];
  sourceStanceBreakdown: SourceStanceBreakdown;
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
  linkedClaims: string[];
  lineage: {
    caseId: string;
    eventId: string | null;
    caseArticleId: string | null;
    origin: string;
  } | null;
  artifacts: Array<{
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
