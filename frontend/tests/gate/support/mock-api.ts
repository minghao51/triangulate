import { expect, type Page, type Route } from '@playwright/test';

/**
 * F16 refinement gate — synthetic API.
 *
 * Every `/api/**` request is answered here. Nothing reaches a real backend, the
 * Vite `/api` proxy or port 8000. Unknown paths return 404 so a missing mock is
 * a visible failure instead of a silent pass-through.
 *
 * The app is started with `VITE_API_BASE_URL` pointing at the same Vite origin,
 * which keeps every read same-origin and disables the bundled static-fixture
 * fallback (so no `/data/**` request can be mistaken for API traffic).
 */

export const ORIGIN = 'http://127.0.0.1:5189';
export const CASE_ID = 'case-gate';
export const WATCH_CASE_ID = 'case-watch';

export const CASE_SUMMARY = {
  id: CASE_ID,
  query: 'Gate Case',
  conflictDomain: 'Water',
  status: 'investigating',
  stage: 'INVESTIGATE',
  counts: { articles: 3, events: 2, reviewItems: 1 },
  automationMode: 'safe',
  hasNewMaterial: true,
  openExceptionsCount: 1,
  lastUpdated: '2026-03-19T10:00:00Z',
  reportPath: null,
};

const WATCH_SUMMARY = {
  id: WATCH_CASE_ID,
  query: 'Gate Watch Case',
  conflictDomain: 'Energy',
  status: 'monitoring',
  stage: 'RETRIEVE',
  counts: { articles: 1, events: 1, reviewItems: 0 },
  automationMode: 'safe',
  hasNewMaterial: false,
  openExceptionsCount: 0,
  lastUpdated: '2026-03-18T08:30:00Z',
  reportPath: null,
};

export const CAPTURE_TEXT =
  'Gate capture opening. The water concession was signed gate quote in March. Trailing context for the window.';
export const GATE_QUOTE = 'gate quote';
const QUOTE_START = CAPTURE_TEXT.indexOf(GATE_QUOTE);

export const SYNTHETIC_MARKDOWN = [
  '# Gate Investigation Report',
  '',
  'Synthetic markdown for the browser gate. It is not a real report.',
  '',
  '## Recorded summary',
  '',
  '- One recorded claim',
  '- One recorded evidence item',
].join('\n');

const claims = () => [
  {
    id: 'cl-gate-1',
    text: 'Gate claim: the water concession was signed in March.',
    verificationStatus: 'confirmed',
    type: 'fact',
    controversyScore: null,
    supportCount: 1,
    opposeCount: 0,
    sourceDiversityCount: 1,
    claimSignature: 'sig-gate-1',
    narrativeClusterId: 'nc-gate-1',
    verificationProvenance: 'unknown',
    evidence: [
      {
        id: 'link-gate-1',
        relation: 'supports',
        confidenceScore: null,
        sourceDiversityRank: null,
        title: 'Gate evidence one',
        publisher: 'Gate Publisher',
        originUrl: 'https://example.com/gate-1',
        sourceType: 'rss',
        captureId: 'cap-gate-1',
        citationId: 'cit-gate-1',
        quote: GATE_QUOTE,
        startChar: QUOTE_START,
        endChar: QUOTE_START + GATE_QUOTE.length,
        alignmentStatus: 'exact',
        effectiveRelation: 'reported_by',
        assessmentOrigin: 'collector',
        assessmentVersion: '1',
        diagnosticReason: null,
      },
    ],
  },
  {
    id: 'cl-gate-2',
    text: 'Gate claim two: a second recorded assertion.',
    verificationStatus: 'contested',
    type: 'allegation',
    controversyScore: null,
    supportCount: 0,
    opposeCount: 1,
    sourceDiversityCount: 1,
    claimSignature: 'sig-gate-2',
    narrativeClusterId: null,
    verificationProvenance: 'legacy_unknown',
    evidence: [],
  },
];

const narratives = () => [
  {
    id: 'nar-gate-1',
    clusterId: 'nc-gate-1',
    stanceSummary: 'Gate narrative cluster',
    sourceCount: 1,
    claimCount: 1,
    keyThemes: ['water'],
    mainEntities: ['Gate Authority'],
  },
];

const evidence = () => [
  {
    id: 'ev-gate-1',
    title: 'Gate evidence one',
    originUrl: 'https://example.com/gate-1',
    canonicalUrl: 'https://example.com/gate-1',
    publisher: 'Gate Publisher',
    sourceType: 'rss',
    verificationStatus: 'confirmed',
    credibilityTier: 'high',
    requiresHumanReview: false,
    currentCaptureId: 'cap-gate-1',
    linkedClaims: ['cl-gate-1'],
    verificationChecks: [],
  },
  {
    id: 'ev-gate-2',
    title: 'Gate evidence two',
    originUrl: 'https://example.com/gate-2',
    canonicalUrl: 'https://example.com/gate-2',
    publisher: 'Second Gate Publisher',
    sourceType: 'html',
    verificationStatus: 'probable',
    credibilityTier: 'medium',
    requiresHumanReview: false,
    currentCaptureId: 'cap-gate-2',
    linkedClaims: ['cl-gate-2'],
    verificationChecks: [],
  },
  {
    id: 'ev-gate-3',
    title: 'Gate evidence three',
    originUrl: 'https://example.com/gate-3',
    canonicalUrl: 'https://example.com/gate-3',
    publisher: 'Gate Publisher',
    sourceType: 'rss',
    verificationStatus: 'unknown',
    credibilityTier: null,
    requiresHumanReview: true,
    currentCaptureId: null,
    linkedClaims: [],
    verificationChecks: [],
  },
];

const evidenceSource = (id: string) => {
  const item = evidence().find((entry) => entry.id === id) ?? evidence()[0];
  return {
    id: item.id,
    eventId: 'evt-gate-1',
    caseArticleId: 'art-gate-1',
    evidenceType: 'article',
    sourceType: item.sourceType,
    title: item.title,
    publisher: item.publisher,
    originUrl: item.originUrl,
    canonicalUrl: item.canonicalUrl,
    publishedAt: '2026-03-01T00:00:00Z',
    verificationStatus: item.verificationStatus,
    credibilityTier: item.credibilityTier,
    requiresHumanReview: item.requiresHumanReview,
    captureMetadata: { extraction: { scope_start: 0, scope_end: CAPTURE_TEXT.length } },
  };
};

const captureSummary = (id: string, evidenceId: string) => ({
  id,
  evidenceId,
  textSha256: `sha-${id}`,
  normalizedTextSha256: `nsha-${id}`,
  normalizationVersion: '1',
  captureKind: 'html',
  recordedAt: '2026-03-01T00:00:00Z',
  observedAt: '2026-03-02T00:00:00Z',
  metadata: {},
  charLength: CAPTURE_TEXT.length,
  isCurrent: true,
});

/** `alignmentStatus` drives the five inspector diagnostic states. */
export const evidenceDetailFor = (alignmentStatus: string | null = 'exact') => {
  const exact = alignmentStatus === 'exact';
  return {
    ...evidenceSource('ev-gate-1'),
    currentCaptureId: 'cap-gate-1',
    captures: [captureSummary('cap-gate-1', 'ev-gate-1')],
    relatedClaims: [
      {
        claimId: 'cl-gate-1',
        claimText: claims()[0].text,
        claimSignature: 'sig-gate-1',
        linkId: 'link-gate-1',
        effectiveRelation: 'reported_by',
        relation: 'supports',
        alignmentStatus,
        citationId: 'cit-gate-1',
        captureId: 'cap-gate-1',
        quote: exact ? GATE_QUOTE : 'gate quotation that may not match',
        startChar: QUOTE_START,
        endChar: QUOTE_START + GATE_QUOTE.length,
        diagnosticReason: null,
      },
    ],
    snapshotId: null,
    unavailableCaptureIds: [],
    liveState: null,
  };
};

const claimDetail = () => ({
  id: 'cl-gate-1',
  caseId: CASE_ID,
  eventId: 'evt-gate-1',
  claimText: claims()[0].text,
  claimSignature: 'sig-gate-1',
  verificationStatus: 'confirmed',
  verificationProvenance: 'unknown',
  type: 'fact',
  controversyScore: null,
  narrativeClusterId: 'nc-gate-1',
  partyPositions: {},
  counts: { supportCount: 1, opposeCount: 0, sourceDiversityCount: 1, evidenceCount: 1 },
  passages: claims()[0].evidence,
  snapshotId: null,
  liveState: null,
});

const citationDetail = () => ({
  id: 'cit-gate-1',
  caseId: CASE_ID,
  captureId: 'cap-gate-1',
  evidenceId: 'ev-gate-1',
  originalClaimId: 'cl-gate-1',
  claimSignature: 'sig-gate-1',
  claimText: claims()[0].text,
  relationship: 'reported_by',
  quote: GATE_QUOTE,
  startChar: QUOTE_START,
  endChar: QUOTE_START + GATE_QUOTE.length,
  alignmentStatus: 'exact',
  alignmentVersion: '1',
  assessmentOrigin: 'collector',
  assessmentVersion: '1',
  assessmentMetadata: {},
  recordedAt: '2026-03-01T00:00:00Z',
  liveClaimPresent: true,
  liveClaimId: 'cl-gate-1',
  evidence: evidenceSource('ev-gate-1'),
  capture: captureSummary('cap-gate-1', 'ev-gate-1'),
});

const captureWindow = () => ({
  captureId: 'cap-gate-1',
  evidenceId: 'ev-gate-1',
  start: 0,
  length: CAPTURE_TEXT.length,
  totalLength: CAPTURE_TEXT.length,
  text: CAPTURE_TEXT,
  textSha256: 'sha-cap-gate-1',
  captureKind: 'html',
  recordedAt: '2026-03-01T00:00:00Z',
  observedAt: '2026-03-02T00:00:00Z',
  metadata: {},
});

const exceptions = () => [
  {
    id: 'exc-gate-1',
    type: 'source_conflict',
    message: 'Gate exception recorded for the operator.',
    severity: 'medium',
    status: 'open',
    recommendedAction: 'Review the recorded conflict.',
    isOpen: true,
  },
];

const parties = () => [
  {
    id: 'party-gate-1',
    name: 'Gate Authority',
    aliases: [],
    description: 'Recorded party for the gate case.',
    overallStance: 'neutral',
    isModelInferred: false,
    associatedClaimsCount: 1,
    investigationData: null,
    claimsSupported: 1,
    claimsContested: 0,
  },
];

const timeline = () => [
  {
    id: 'evt-gate-1',
    timestamp: '2026-03-01T00:00:00Z',
    title: 'Gate event one',
    summary: 'Recorded event for the gate case.',
    verificationStatus: 'confirmed',
    linkedEvidenceCount: 1,
    locationCountryCode: 'GB',
    locationLat: 51.5,
    locationLon: -0.12,
    workflowRoute: 'standard',
    sourceUrl: null,
  },
  {
    id: 'evt-gate-2',
    timestamp: null,
    title: 'Gate event two',
    summary: 'Recorded event without a recorded date.',
    verificationStatus: 'unknown',
    linkedEvidenceCount: 0,
    locationCountryCode: null,
    locationLat: null,
    locationLon: null,
    workflowRoute: null,
    sourceUrl: null,
  },
];

export const runHistory = () => [
  {
    id: 'stage-run-gate-1',
    stage: 'INVESTIGATE',
    model: 'gate-model',
    durationMs: 1200,
    status: 'success',
    fallbackCount: 0,
    parseFailureCount: 0,
    timestamp: '2026-03-19T09:58:00Z',
    message: 'Recorded stage attempt.',
  },
];

export const RUN_READY = {
  id: 'run-gate-1',
  caseId: CASE_ID,
  sequence: 2,
  trigger: 'rerun',
  requestedStartStage: 'retrieve',
  status: 'succeeded',
  coverage: 'complete_requested_scope',
  startedAt: '2026-03-19T09:00:00Z',
  completedAt: '2026-03-19T09:30:00Z',
  predecessorRunId: 'run-gate-0',
  baselineSnapshotId: 'snap-gate-0',
  resultSnapshotId: 'snap-gate-1',
  snapshotId: 'snap-gate-1',
  errorMessage: null,
};

export const RUN_INITIAL = {
  ...RUN_READY,
  id: 'run-gate-0',
  sequence: 1,
  trigger: 'initial',
  status: 'succeeded',
  baselineSnapshotId: null,
  predecessorRunId: null,
  resultSnapshotId: 'snap-gate-0',
  snapshotId: 'snap-gate-0',
};

const investigationRuns = () => ({
  items: [RUN_READY, RUN_INITIAL],
  total: 2,
  limit: 50,
  offset: 0,
  hasMore: false,
});

/** `availability` selects the changes state the tab must show. */
export const runChangesFor = (
  availability: 'initial' | 'ready' | 'pending' | 'unavailable',
  options: { total?: number; coverage?: string } = {}
) => {
  const total = options.total ?? (availability === 'ready' ? 1 : 0);
  const items =
    availability === 'ready' && total > 0
      ? [
          {
            type: 'claim_added',
            entityType: 'claims',
            entityId: 'cl-gate-2',
            before: null,
            after: { claimSignature: 'sig-gate-2' },
            originRunId: 'run-gate-1',
            observedByRunId: 'run-gate-1',
            observedAt: '2026-03-19T09:20:00Z',
          },
        ]
      : [];
  return {
    availability,
    baselineSnapshotId: availability === 'initial' ? null : 'snap-gate-0',
    targetSnapshotId: 'snap-gate-1',
    coverage: options.coverage ?? 'complete_requested_scope',
    coverageNote: options.coverage === 'partial' ? 'Only part of the scope was observed.' : null,
    items,
    total,
    limit: 25,
    offset: 0,
    hasMore: false,
  };
};

const reportReady = () => ({
  status: 'generated',
  markdownPath: 'topic_report.md',
  markdownContent: SYNTHETIC_MARKDOWN,
  manifestPath: 'manifest.json',
});

export const reportPending = () => ({
  status: 'pending',
  markdownPath: null,
  markdownContent: null,
  manifestPath: null,
});

const reviewActivity = () => ({
  annotations: [
    {
      id: 'ann-gate-1',
      targetType: 'case',
      targetId: CASE_ID,
      annotationType: 'comment',
      author: 'operator',
      content: 'Recorded human note for the gate case.',
      metadata: {},
      createdAt: '2026-03-19T09:40:00Z',
    },
  ],
  auditEntries: [
    {
      id: 'aud-gate-1',
      actionType: 'annotation:comment',
      targetType: 'case',
      targetId: CASE_ID,
      actor: 'operator',
      rationale: null,
      metadata: {},
      createdAt: '2026-03-19T09:40:01Z',
    },
  ],
});

export const searchResults = () => ({
  caseId: CASE_ID,
  query: 'gate',
  total: 1,
  limit: 25,
  offset: 0,
  appliedFilters: {
    type: null,
    publisher: null,
    status: null,
    publishedFrom: null,
    publishedTo: null,
  },
  items: [
    {
      resultType: 'evidence',
      id: 'ev-gate-1',
      claimId: null,
      evidenceId: 'ev-gate-1',
      eventId: null,
      captureId: 'cap-gate-1',
      title: 'Gate evidence one',
      snippet: 'Gate capture opening.',
      matchedField: 'body',
      publisher: 'Gate Publisher',
      status: null,
      publishedAt: '2026-03-01T00:00:00Z',
    },
  ],
});

const comparisonSide = (evidenceId: string, publisher: string) => ({
  evidenceId,
  captureId: `cap-${evidenceId}`,
  title: `Gate source ${evidenceId}`,
  publisher,
  originUrl: `https://example.com/${evidenceId}`,
  canonicalUrl: `https://example.com/${evidenceId}`,
  publishedAt: '2026-03-01T00:00:00Z',
  sourceType: 'rss',
  verificationStatus: 'confirmed',
  captureKind: 'html',
  recordedAt: '2026-03-01T00:00:00Z',
  observedAt: '2026-03-02T00:00:00Z',
  textSha256: `sha-${evidenceId}`,
  charLength: CAPTURE_TEXT.length,
  analysisScope: {
    status: 'recorded',
    startChar: 0,
    endChar: CAPTURE_TEXT.length,
    bodyCharCount: CAPTURE_TEXT.length,
    inputLimit: 20000,
    sourceAvailable: true,
    reason: null,
  },
  publisherKey: `${publisher.toLowerCase().replace(/[^a-z]+/g, '-')}`,
  publisherKeyProvisional: false,
  host: 'example.com',
  sourceUrl: `https://example.com/${evidenceId}`,
  copyFingerprint: null,
  copyNonWhitespaceCount: 12,
  coverage: {
    linkedClaimCount: 1,
    attributedClaimCount: 1,
    attributedLinkCount: 1,
    otherCaptureLinkCount: 0,
    unattributedLinkCount: 0,
    claimLinkageStatus: 'available',
    historicalAnalysisAvailable: true,
    caveat: null,
  },
});

export const comparisonFor = (
  options: { dependencyDetected?: boolean; historicalUnavailable?: boolean } = {}
) => {
  const left = comparisonSide('ev-gate-1', 'Gate Publisher');
  const right = comparisonSide('ev-gate-2', 'Second Gate Publisher');
  if (options.historicalUnavailable) {
    left.coverage.historicalAnalysisAvailable = false;
    left.coverage.claimLinkageStatus = 'historical_unavailable';
  }
  return {
    caseId: CASE_ID,
    left,
    right,
    leftCaptureId: left.captureId,
    rightCaptureId: right.captureId,
    dependency: {
      detected: Boolean(options.dependencyDetected),
      copyDetected: Boolean(options.dependencyDetected),
      reasons: options.dependencyDetected ? ['identical_copy'] : [],
      leftPublisherKey: left.publisherKey,
      rightPublisherKey: right.publisherKey,
      message: options.dependencyDetected
        ? 'The two captures share recorded dependency signals.'
        : 'No recorded dependency signal links these captures.',
    },
    claims: {
      rows: [
        {
          claimSignature: 'sig-gate-1',
          claimText: claims()[0].text,
          status: 'shared',
          left: {
            claimIds: ['cl-gate-1'],
            claimId: 'cl-gate-1',
            claimText: claims()[0].text,
            claimSignature: 'sig-gate-1',
            passages: [
              {
                claimId: 'cl-gate-1',
                claimText: claims()[0].text,
                claimSignature: 'sig-gate-1',
                linkId: 'link-gate-1',
                citationId: 'cit-gate-1',
                captureId: 'cap-gate-1',
                relationship: 'reported_by',
                rawRelation: 'supports',
                alignmentStatus: 'exact',
                quote: GATE_QUOTE,
                startChar: QUOTE_START,
                endChar: QUOTE_START + GATE_QUOTE.length,
                assessmentOrigin: 'collector',
                assessmentVersion: '1',
                diagnosticReason: null,
              },
            ],
          },
          right: null,
          contradiction: {
            explicit: false,
            conflict: false,
            leftRelationships: ['reported_by'],
            rightRelationships: [],
            reason: 'No contradiction was assessed.',
          },
          caveat: null,
        },
      ],
      total: 1,
      limit: 25,
      offset: 0,
      hasMore: false,
    },
    policy: {
      version: 'gate-policy-1',
      claimIdentity: 'Recorded claim signature.',
      alignment: 'Exact code-point alignment only.',
      dependencyPolicy: 'Recorded copy fingerprints and publisher identity.',
      limitations: ['Comparison is limited to the two selected captures.'],
    },
    caveats: ['Shared wording is not independent corroboration.'],
    snapshotId: null,
  };
};

const sourceSummary = () => ({
  caseId: CASE_ID,
  scope: 'case',
  claimId: null,
  claimSignature: null,
  evidenceCount: 3,
  distinctPublisherCount: 2,
  dependencyGroupCount: 1,
  unknownPublisherCount: 0,
  independenceStatus: 'unknown',
  policy: {
    version: 'gate-policy-1',
    urlNormalization: ['lowercase host'],
    publisherIdentity: ['recorded publisher'],
    dependencyEdges: ['copy fingerprint'],
    textFingerprint: 'sha256',
    textFingerprintNormalization: 'lf-only',
    minCopyNonWhitespaceCodePoints: 200,
    limitations: ['No independence verdict is recorded.'],
  },
  publisherCounts: [
    {
      publisherKey: 'gate-publisher',
      publisher: 'Gate Publisher',
      evidenceCount: 2,
      dependencyGroupCount: 1,
      provisional: false,
    },
  ],
  groups: [
    {
      id: 'grp-gate-1',
      reasons: ['copy'],
      publisherKeys: ['gate-publisher'],
      evidenceCount: 1,
      members: [
        {
          evidenceId: 'ev-gate-1',
          publisher: 'Gate Publisher',
          publisherKey: 'gate-publisher',
          publisherKeyProvisional: false,
          host: 'example.com',
          originUrl: 'https://example.com/gate-1',
          canonicalUrl: 'https://example.com/gate-1',
          sourceUrl: 'https://example.com/gate-1',
          caseArticleId: 'art-gate-1',
          explicitOriginKey: null,
          captureId: 'cap-gate-1',
          captureKind: 'html',
          captureTextSha256: 'sha-cap-gate-1',
          captureNormalizedTextSha256: 'nsha-cap-gate-1',
          captureCharLength: CAPTURE_TEXT.length,
          recordedAt: '2026-03-01T00:00:00Z',
          observedAt: '2026-03-02T00:00:00Z',
          copyFingerprint: 'fp-gate-1',
          copyNonWhitespaceCount: 12,
          dependencyReasons: ['copy'],
        },
      ],
    },
  ],
});

export const caseDetail = () => ({
  case: CASE_SUMMARY,
  tabs: {
    claims: claims(),
    evidence: evidence(),
    exceptions: exceptions(),
    parties: parties(),
    timeline: timeline(),
    runHistory: runHistory(),
    narratives: narratives(),
    osintArtifacts: [],
    workflow: { taxonomy: null, checkpoints: [], agentOutputs: [] },
    report: reportReady(),
  },
});

const annotationCreated = () => reviewActivity().annotations[0];

/**
 * Logical response keys. Each key is one mocked read/write; overrides address it
 * by name so a state test never has to know the URL shape.
 */
export type MockKey =
  | 'cases'
  | 'monitoringSummary'
  | 'caseDetail'
  | 'claimsOverview'
  | 'evidence'
  | 'evidenceDetail'
  | 'claimDetail'
  | 'citationDetail'
  | 'captureWindow'
  | 'exceptions'
  | 'parties'
  | 'timeline'
  | 'runHistory'
  | 'investigationRuns'
  | 'investigationRun'
  | 'runChanges'
  | 'report'
  | 'reportMarkdown'
  | 'reportManifest'
  | 'reviewActivity'
  | 'evaluation'
  | 'search'
  | 'comparison'
  | 'sources'
  | 'snapshotComparison'
  | 'runArtifacts'
  | 'runArtifactDownload'
  | 'reviewAction'
  | 'exceptionAction'
  | 'annotation';

const defaults = (): Record<MockKey, unknown> => ({
  cases: [CASE_SUMMARY, WATCH_SUMMARY],
  monitoringSummary: {
    cases: { monitoring: 1 },
    review: { open_exceptions: 1 },
    pipeline: {},
    intake: {},
    evaluation: { avg_overall_score: null },
  },
  caseDetail: caseDetail(),
  claimsOverview: { claims: claims(), narratives: narratives() },
  evidence: evidence(),
  evidenceDetail: evidenceDetailFor('exact'),
  claimDetail: claimDetail(),
  citationDetail: citationDetail(),
  captureWindow: captureWindow(),
  exceptions: exceptions(),
  parties: parties(),
  timeline: timeline(),
  runHistory: runHistory(),
  investigationRuns: investigationRuns(),
  investigationRun: RUN_READY,
  runChanges: runChangesFor('ready', { total: 1 }),
  report: reportReady(),
  reportMarkdown: SYNTHETIC_MARKDOWN,
  reportManifest: JSON.stringify({ gate: true }, null, 2),
  reviewActivity: reviewActivity(),
  evaluation: { latest: null, history: [] },
  search: searchResults(),
  comparison: comparisonFor(),
  sources: sourceSummary(),
  // X01 — ad-hoc comparison between two immutable snapshots.
  snapshotComparison: {
    mode: 'ad_hoc',
    comparisonPolicyVersion: 'snapshot-comparison-policy-v1',
    baselineSnapshotId: 'snap-gate-0',
    targetSnapshotId: 'snap-gate-1',
    baselineRunId: RUN_INITIAL.id,
    targetRunId: RUN_READY.id,
    baselineCoverage: 'partial',
    targetCoverage: 'partial',
    baselineMetadata: {
      sequence: 1,
      createdAt: '2026-11-01T09:00:00Z',
      schemaVersion: 'case-snapshot-v1',
      identityVersion: 'claim-signature-sha256-v1',
      policyVersion: 'case-history-policy-v1',
    },
    targetMetadata: {
      sequence: 2,
      createdAt: '2026-11-01T10:00:00Z',
      schemaVersion: 'case-snapshot-v1',
      identityVersion: 'claim-signature-sha256-v1',
      policyVersion: 'case-history-policy-v1',
    },
    availability: 'ready',
    unavailableReason: null,
    items: [
      {
        entityType: 'claims',
        entityId: 'cl-gate-1',
        changeKind: 'field_changed',
        changedFields: ['verificationStatus'],
        before: { verificationStatus: 'alleged' },
        after: { verificationStatus: 'confirmed' },
        refs: {
          baseline: { snapshotId: 'snap-gate-0', claimId: 'cl-gate-1' },
          target: { snapshotId: 'snap-gate-1', claimId: 'cl-gate-1' },
        },
      },
      {
        entityType: 'captures',
        entityId: 'cap-gate-2',
        changeKind: 'entity_added',
        changedFields: [],
        before: null,
        after: { id: 'cap-gate-2' },
        refs: {
          baseline: { snapshotId: 'snap-gate-0' },
          target: { snapshotId: 'snap-gate-1', captureId: 'cap-gate-2', evidenceId: 'ev-gate-1' },
        },
      },
    ],
    total: 2,
    limit: 25,
    offset: 0,
    hasMore: false,
  },
  // X02 — published artifacts of one recorded run (no filesystem paths).
  runArtifacts: [
    {
      artifactId: 'art-gate-markdown',
      type: 'report_markdown',
      displayName: 'topic_report.md',
      downloadUrl: `/api/cases/${CASE_ID}/investigation-runs/${RUN_READY.id}/artifacts/art-gate-markdown`,
      recordedChecksum: null,
      checksumKind: 'unknown',
    },
    {
      artifactId: 'art-gate-json',
      type: 'report_json',
      displayName: 'topic_analysis.json',
      downloadUrl: `/api/cases/${CASE_ID}/investigation-runs/${RUN_READY.id}/artifacts/art-gate-json`,
      recordedChecksum: 'payload-checksum-gate',
      checksumKind: 'payload_json',
    },
  ],
  runArtifactDownload: SYNTHETIC_MARKDOWN,
  reviewAction: CASE_SUMMARY,
  exceptionAction: CASE_SUMMARY,
  annotation: annotationCreated(),
});

export interface Override {
  status?: number;
  body?: unknown;
  /** Keep the request pending forever (write-pending / loading states). */
  hang?: boolean;
  /** Wait this long before answering. */
  delayMs?: number;
}

export interface MockOptions {
  overrides?: Partial<Record<MockKey, Override>>;
}

export interface ApiAuditEntry {
  method: string;
  path: string;
}

/** Map a request to a logical key; `null` means "not a mocked API path". */
function logicalKey(method: string, path: string): MockKey | null {
  const caseMatch = path.match(/^\/api\/cases\/([^/]+)(?:\/(.*))?$/);
  if (method === 'POST') {
    if (/^\/api\/cases\/[^/]+\/review-actions\/review$/.test(path)) return 'reviewAction';
    if (/^\/api\/cases\/[^/]+\/review-actions\/exceptions\/[^/]+$/.test(path)) {
      return 'exceptionAction';
    }
    if (/^\/api\/cases\/[^/]+\/annotations$/.test(path)) return 'annotation';
    return null;
  }
  if (method !== 'GET') return null;
  if (path === '/api/cases') return 'cases';
  if (path === '/api/monitoring/summary') return 'monitoringSummary';
  if (!caseMatch) return null;
  const rest = caseMatch[2] ?? '';
  if (rest === '') return 'caseDetail';
  if (rest === 'claims/overview') return 'claimsOverview';
  if (rest === 'evidence') return 'evidence';
  if (/^evidence\/[^/]+\/captures\/[^/]+$/.test(rest)) return 'captureWindow';
  if (/^evidence\/[^/]+$/.test(rest)) return 'evidenceDetail';
  if (/^claims\/[^/]+$/.test(rest)) return 'claimDetail';
  if (/^citations\/[^/]+$/.test(rest)) return 'citationDetail';
  if (rest === 'exceptions') return 'exceptions';
  if (rest === 'parties') return 'parties';
  if (rest === 'timeline') return 'timeline';
  if (rest === 'run-history') return 'runHistory';
  if (rest === 'investigation-runs') return 'investigationRuns';
  if (/^investigation-runs\/[^/]+\/changes$/.test(rest)) return 'runChanges';
  if (/^investigation-runs\/[^/]+$/.test(rest)) return 'investigationRun';
  if (rest === 'report') return 'report';
  if (rest === 'report/markdown') return 'reportMarkdown';
  if (rest === 'report/manifest') return 'reportManifest';
  if (rest === 'review-activity') return 'reviewActivity';
  if (rest === 'evaluation') return 'evaluation';
  if (rest === 'search') return 'search';
  if (rest === 'comparison') return 'comparison';
  if (rest === 'sources') return 'sources';
  if (rest === 'snapshot-comparison') return 'snapshotComparison';
  if (/^investigation-runs\/[^/]+\/artifacts\/[^/]+$/.test(rest)) return 'runArtifactDownload';
  if (/^investigation-runs\/[^/]+\/artifacts$/.test(rest)) return 'runArtifacts';
  return null;
}

const nonJsonKeys = new Set<MockKey>(['reportMarkdown', 'reportManifest', 'runArtifactDownload']);

function fulfil(route: Route, key: MockKey, value: unknown, status = 200) {
  if (nonJsonKeys.has(key)) {
    const contentType = key === 'reportMarkdown' ? 'text/markdown' : 'application/json';
    return route.fulfill({
      status,
      contentType,
      headers: { 'Content-Disposition': `attachment; filename="gate-${key}.txt"` },
      body: String(value),
    });
  }
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(value),
  });
}

/**
 * Install the synthetic API. Returns the request audit (method + path) so a test
 * can assert the read-only/three-POST allowlist.
 */
export interface MockSession {
  /** One entry per `/api/**` request: method + path. */
  audit: ApiAuditEntry[];
  /** Requests that left the app origin (fonts hosts are blocked separately). */
  foreign: string[];
}

const ALLOWED_FOREIGN_HOSTS = new Set(['fonts.googleapis.com', 'fonts.gstatic.com']);

export async function installApiMock(
  page: Page,
  options: MockOptions = {}
): Promise<MockSession> {
  const audit: ApiAuditEntry[] = [];
  const foreign: string[] = [];
  const bodies = defaults();

  // External IO guard: record anything that leaves the app origin.
  page.on('request', (request) => {
    const raw = request.url();
    if (!/^https?:/i.test(raw)) return;
    const host = new URL(raw).host;
    if (host === new URL(ORIGIN).host) return;
    if (host === '127.0.0.1:8000' || host === 'localhost:8000') {
      foreign.push(`backend:${raw}`);
      return;
    }
    if (ALLOWED_FOREIGN_HOSTS.has(host.split(':')[0])) return;
    foreign.push(raw);
  });

  // Fonts are blocked so no external IO happens during the gate.
  await page.route('https://fonts.googleapis.com/**', (route) =>
    route.fulfill({ status: 200, contentType: 'text/css', body: '/* blocked in gate */' })
  );
  await page.route('https://fonts.gstatic.com/**', (route) =>
    route.fulfill({ status: 200, contentType: 'font/woff2', body: '' })
  );

  await page.route(/\/api\//, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    audit.push({ method, path: url.pathname });

    const key = logicalKey(method, url.pathname);
    if (!key) {
      return route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: `unmocked api path ${url.pathname}` }),
      });
    }

    const override = options.overrides?.[key];
    if (override?.hang) {
      // Never fulfil: the client stays in its pending state.
      return;
    }
    if (override?.delayMs) {
      await new Promise((resolve) => setTimeout(resolve, override.delayMs));
    }
    const body = override && 'body' in override ? override.body : bodies[key];
    return fulfil(route, key, body, override?.status ?? 200);
  });

  return { audit, foreign };
}

/** Nothing may leave the app origin (the two font hosts are blocked in place). */
export function assertNoForeignNetwork(session: MockSession, label: string) {
  expect(session.foreign, `${label}: external IO during the gate run`).toEqual([]);
}

/** Every audited request must be same-origin; nothing may reach port 8000. */
export function assertSameOriginAudit(audit: ApiAuditEntry[]) {
  expect(audit.length).toBeGreaterThan(0);
  expect(audit.every((entry) => entry.path.startsWith('/api/'))).toBe(true);
}

/** GET plus exactly the three narrow POST families; nothing else. */
export function assertReadOnlyAllowlist(audit: ApiAuditEntry[]) {
  const offending = audit.filter(
    (entry) =>
      entry.method !== 'GET' &&
      !/^\/api\/cases\/[^/]+\/(review-actions\/review|review-actions\/exceptions\/[^/]+|annotations)$/.test(
        entry.path
      )
  );
  expect(offending, `non-allowlisted requests: ${JSON.stringify(offending)}`).toEqual([]);
}

export const fixtureIds = {
  caseId: CASE_ID,
  claimId: 'cl-gate-1',
  evidenceId: 'ev-gate-1',
  secondEvidenceId: 'ev-gate-2',
  captureId: 'cap-gate-1',
  citationId: 'cit-gate-1',
  snapshotId: 'snap-gate-1',
  runId: 'run-gate-1',
  exceptionId: 'exc-gate-1',
};
