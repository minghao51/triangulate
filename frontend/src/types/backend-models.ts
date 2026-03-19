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
