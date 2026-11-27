/**
 * One source of truth for case-workspace deep links.
 *
 * The inspector is hosted by the existing evidence tab, so every consumer
 * (claims tab, evidence tab, future pages) builds and parses the same
 * URI-encoded selectors here instead of hand-assembling query strings.
 */

export const INSPECTOR_PARAMS = {
  claim: 'claim',
  evidence: 'evidence',
  capture: 'capture',
  citation: 'citation',
  start: 'start',
  length: 'length',
  snapshot: 'snapshot',
} as const;

export type CaseTab = 'evidence' | 'claims';

export interface InspectorSelection {
  claimId?: string | null;
  evidenceId?: string | null;
  captureId?: string | null;
  citationId?: string | null;
  /** Zero-based code-point offset of the requested capture window. */
  start?: number | null;
  /** Requested code-point window length (the API caps it at 50000). */
  length?: number | null;
  /** Pinned observation ID; only claim/evidence detail readers accept it. */
  snapshotId?: string | null;
}

export interface ParsedInspectorSelection {
  claimId: string | null;
  evidenceId: string | null;
  captureId: string | null;
  citationId: string | null;
  start: number | null;
  length: number | null;
  snapshotId: string | null;
}

function cleaned(value: string | null | undefined): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

function cleanedOffset(value: number | null | undefined, minimum: number): number | null {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < minimum) {
    return null;
  }
  return value;
}

/**
 * Serialise a selection. Null/undefined selectors are omitted entirely, the
 * order is stable, and `URLSearchParams` performs the URI encoding.
 */
export function toInspectorSearchParams(selection: InspectorSelection): URLSearchParams {
  const params = new URLSearchParams();
  const claimId = cleaned(selection.claimId);
  const evidenceId = cleaned(selection.evidenceId);
  const captureId = cleaned(selection.captureId);
  const citationId = cleaned(selection.citationId);
  const start = cleanedOffset(selection.start, 0);
  const length = cleanedOffset(selection.length, 1);
  const snapshotId = cleaned(selection.snapshotId);

  if (claimId) params.set(INSPECTOR_PARAMS.claim, claimId);
  if (evidenceId) params.set(INSPECTOR_PARAMS.evidence, evidenceId);
  if (captureId) params.set(INSPECTOR_PARAMS.capture, captureId);
  if (citationId) params.set(INSPECTOR_PARAMS.citation, citationId);
  if (start !== null) params.set(INSPECTOR_PARAMS.start, String(start));
  if (length !== null) params.set(INSPECTOR_PARAMS.length, String(length));
  if (snapshotId) params.set(INSPECTOR_PARAMS.snapshot, snapshotId);

  return params;
}

/** Parse a URL query into typed selectors; malformed offsets become `null`. */
export function parseInspectorSelection(
  params: URLSearchParams
): ParsedInspectorSelection {
  const rawStart = params.get(INSPECTOR_PARAMS.start);
  const rawLength = params.get(INSPECTOR_PARAMS.length);
  const parsedStart = rawStart === null ? null : Number(rawStart);
  const parsedLength = rawLength === null ? null : Number(rawLength);

  return {
    claimId: cleaned(params.get(INSPECTOR_PARAMS.claim)),
    evidenceId: cleaned(params.get(INSPECTOR_PARAMS.evidence)),
    captureId: cleaned(params.get(INSPECTOR_PARAMS.capture)),
    citationId: cleaned(params.get(INSPECTOR_PARAMS.citation)),
    start: parsedStart === null ? null : cleanedOffset(parsedStart, 0),
    length: parsedLength === null ? null : cleanedOffset(parsedLength, 1),
    snapshotId: cleaned(params.get(INSPECTOR_PARAMS.snapshot)),
  };
}

function buildCaseUrl(
  caseId: string,
  tab: CaseTab | null,
  selection: InspectorSelection
): string {
  const path = `/cases/${encodeURIComponent(caseId)}${tab ? `/${tab}` : ''}`;
  // `URLSearchParams.toString()` encodes spaces as `+`; encodeURIComponent keeps
  // the conventional `%20` form expected by existing links and tests.
  const query = [...toInspectorSearchParams(selection).entries()]
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join('&');
  return query ? `${path}?${query}` : path;
}

/** Build a tab URL without inspector selectors. */
export function buildCaseTabUrl(caseId: string, tab: CaseTab): string {
  return buildCaseUrl(caseId, tab, {});
}

/** Build an evidence-tab URL with claim/evidence/capture/citation selectors. */
export function buildInspectorUrl(caseId: string, selection: InspectorSelection): string {
  return buildCaseUrl(caseId, 'evidence', selection);
}

/** Claim -> linked sources (the existing "Inspect Evidence" entry point). */
export function buildClaimEvidenceUrl(caseId: string, claimId: string): string {
  return buildInspectorUrl(caseId, { claimId });
}

/** A frozen citation deep link, resolvable without a live claim. */
export function buildCitationUrl(caseId: string, citationId: string): string {
  return buildInspectorUrl(caseId, { citationId });
}

// ---------------------------------------------------------------------------
// P02/P03 comparison selectors
// ---------------------------------------------------------------------------

export const COMPARISON_PARAMS = {
  left: 'left',
  right: 'right',
  leftCapture: 'leftCapture',
  rightCapture: 'rightCapture',
  offset: 'offset',
  limit: 'limit',
} as const;

export interface ComparisonSelection {
  leftId?: string | null;
  rightId?: string | null;
  leftCaptureId?: string | null;
  rightCaptureId?: string | null;
  offset?: number | null;
  limit?: number | null;
}

export interface ParsedComparisonSelection {
  leftId: string | null;
  rightId: string | null;
  leftCaptureId: string | null;
  rightCaptureId: string | null;
  offset: number | null;
  limit: number | null;
}

export function toComparisonSearchParams(
  selection: ComparisonSelection
): URLSearchParams {
  const params = new URLSearchParams();
  const leftId = cleaned(selection.leftId);
  const rightId = cleaned(selection.rightId);
  const leftCaptureId = cleaned(selection.leftCaptureId);
  const rightCaptureId = cleaned(selection.rightCaptureId);
  const offset = cleanedOffset(selection.offset, 0);
  const limit = cleanedOffset(selection.limit, 1);

  if (leftId) params.set(COMPARISON_PARAMS.left, leftId);
  if (rightId) params.set(COMPARISON_PARAMS.right, rightId);
  if (leftCaptureId) params.set(COMPARISON_PARAMS.leftCapture, leftCaptureId);
  if (rightCaptureId) params.set(COMPARISON_PARAMS.rightCapture, rightCaptureId);
  if (offset !== null) params.set(COMPARISON_PARAMS.offset, String(offset));
  if (limit !== null) params.set(COMPARISON_PARAMS.limit, String(limit));
  return params;
}

export function parseComparisonSelection(
  params: URLSearchParams
): ParsedComparisonSelection {
  const rawOffset = params.get(COMPARISON_PARAMS.offset);
  const rawLimit = params.get(COMPARISON_PARAMS.limit);
  const parsedOffset = rawOffset === null ? null : Number(rawOffset);
  const parsedLimit = rawLimit === null ? null : Number(rawLimit);
  return {
    leftId: cleaned(params.get(COMPARISON_PARAMS.left)),
    rightId: cleaned(params.get(COMPARISON_PARAMS.right)),
    leftCaptureId: cleaned(params.get(COMPARISON_PARAMS.leftCapture)),
    rightCaptureId: cleaned(params.get(COMPARISON_PARAMS.rightCapture)),
    offset: parsedOffset === null ? null : cleanedOffset(parsedOffset, 0),
    limit: parsedLimit === null ? null : cleanedOffset(parsedLimit, 1),
  };
}

/** Build an encoded compare-tab URL that survives reload/back/forward. */
export function buildComparisonUrl(
  caseId: string,
  selection: ComparisonSelection
): string {
  const path = `/cases/${encodeURIComponent(caseId)}/compare`;
  const query = [...toComparisonSearchParams(selection).entries()]
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join('&');
  return query ? `${path}?${query}` : path;
}

// ---------------------------------------------------------------------------
// R04 grouped-run changes selectors
// ---------------------------------------------------------------------------

export const CHANGES_PARAMS = {
  // X01 ad-hoc comparison mode rides this route; the API query names are
  // `baseline`/`target`, the browser allowlist names are longer on purpose.
  mode: 'mode',
  baselineSnapshot: 'baselineSnapshot',
  targetSnapshot: 'targetSnapshot',
  run: 'run',
  claim: 'claim',
  snapshot: 'snapshot',
  offset: 'offset',
  limit: 'limit',
} as const;

/** The only changes-mode value this build renders; everything else is recorded. */
export const CHANGES_MODES = ['ad_hoc'] as const;
export type ChangesMode = (typeof CHANGES_MODES)[number];
export const CHANGES_MODE_AD_HOC: ChangesMode = 'ad_hoc';

export interface ChangesSelection {
  /** `ad_hoc` compares two explicitly pinned snapshots on request. */
  mode?: ChangesMode | null;
  /** Baseline side of an ad-hoc comparison (never defaulted to "latest"). */
  baselineSnapshotId?: string | null;
  /** Target side of an ad-hoc comparison (never defaulted to "latest"). */
  targetSnapshotId?: string | null;
  runId?: string | null;
  /** Frozen claim opened inline from a change row. */
  claimId?: string | null;
  /** Observation the inline claim is resolved from. */
  snapshotId?: string | null;
  offset?: number | null;
  limit?: number | null;
}

export interface ParsedChangesSelection {
  runId: string | null;
  claimId: string | null;
  snapshotId: string | null;
  offset: number | null;
  limit: number | null;
}

/**
 * Ad-hoc comparison selectors parsed independently of the recorded selection,
 * so the recorded view keeps its exact shape when `mode` is absent.
 */
export interface AdHocChangesSelection {
  /** `mode=ad_hoc` and a value this build renders. */
  active: boolean;
  /** The raw mode value, kept so an unsupported mode is never silently read. */
  mode: string | null;
  baselineSnapshotId: string | null;
  targetSnapshotId: string | null;
}

export function toChangesSearchParams(selection: ChangesSelection): URLSearchParams {
  const params = new URLSearchParams();
  const mode =
    selection.mode && CHANGES_MODES.includes(selection.mode as ChangesMode)
      ? selection.mode
      : null;
  const baselineSnapshotId = cleaned(selection.baselineSnapshotId);
  const targetSnapshotId = cleaned(selection.targetSnapshotId);
  const runId = cleaned(selection.runId);
  const claimId = cleaned(selection.claimId);
  const snapshotId = cleaned(selection.snapshotId);
  const offset = cleanedOffset(selection.offset, 0);
  const limit = cleanedOffset(selection.limit, 1);

  if (mode) params.set(CHANGES_PARAMS.mode, mode);
  if (baselineSnapshotId) params.set(CHANGES_PARAMS.baselineSnapshot, baselineSnapshotId);
  if (targetSnapshotId) params.set(CHANGES_PARAMS.targetSnapshot, targetSnapshotId);
  if (runId) params.set(CHANGES_PARAMS.run, runId);
  if (claimId) params.set(CHANGES_PARAMS.claim, claimId);
  if (snapshotId) params.set(CHANGES_PARAMS.snapshot, snapshotId);
  if (offset !== null) params.set(CHANGES_PARAMS.offset, String(offset));
  if (limit !== null) params.set(CHANGES_PARAMS.limit, String(limit));
  return params;
}

/** The recorded-view selectors only; `mode`/snapshot sides are not included. */
export function parseChangesSelection(params: URLSearchParams): ParsedChangesSelection {
  const rawOffset = params.get(CHANGES_PARAMS.offset);
  const rawLimit = params.get(CHANGES_PARAMS.limit);
  const parsedOffset = rawOffset === null ? null : Number(rawOffset);
  const parsedLimit = rawLimit === null ? null : Number(rawLimit);
  return {
    runId: cleaned(params.get(CHANGES_PARAMS.run)),
    claimId: cleaned(params.get(CHANGES_PARAMS.claim)),
    snapshotId: cleaned(params.get(CHANGES_PARAMS.snapshot)),
    offset: parsedOffset === null ? null : cleanedOffset(parsedOffset, 0),
    limit: parsedLimit === null ? null : cleanedOffset(parsedLimit, 1),
  };
}

/**
 * Parse the additive ad-hoc selectors. A missing side stays `null`: it is never
 * replaced with the newest snapshot, and only `mode=ad_hoc` activates the mode.
 */
export function parseAdHocChangesSelection(
  params: URLSearchParams
): AdHocChangesSelection {
  const mode = cleaned(params.get(CHANGES_PARAMS.mode));
  return {
    active: mode === CHANGES_MODE_AD_HOC,
    mode,
    baselineSnapshotId: cleaned(params.get(CHANGES_PARAMS.baselineSnapshot)),
    targetSnapshotId: cleaned(params.get(CHANGES_PARAMS.targetSnapshot)),
  };
}

/** Build an encoded changes-tab URL that survives reload/back/forward. */
export function buildChangesUrl(
  caseId: string,
  selection: ChangesSelection
): string {
  const path = `/cases/${encodeURIComponent(caseId)}/changes`;
  const query = [...toChangesSearchParams(selection).entries()]
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join('&');
  return query ? `${path}?${query}` : path;
}

// ---------------------------------------------------------------------------
// X02 / F20 report run pin
// ---------------------------------------------------------------------------

/**
 * The report view keeps the **current** stored report as its default. An
 * optional pin names one recorded grouped `InvestigationRun` whose frozen
 * report artifacts are shown instead.
 *
 * This is a browser-only selector: the F19 API addresses artifacts by
 * `case_id` + grouped `run_id` + `artifact_id`, and the artifact-type allowlist
 * (`report_markdown`, `report_json`, `execution_manifest`) is enforced by the
 * reader, never by this URL. Nothing here resolves "the latest" or a nearby
 * run for a missing pin.
 */
export const REPORT_PARAMS = {
  run: 'reportRun',
} as const;

export interface ReportSelection {
  /** Recorded grouped-run id; absent/null means the current report. */
  runId?: string | null;
}

export interface ParsedReportSelection {
  runId: string | null;
}

export function toReportSearchParams(selection: ReportSelection = {}): URLSearchParams {
  const params = new URLSearchParams();
  const runId = cleaned(selection.runId);
  if (runId) params.set(REPORT_PARAMS.run, runId);
  return params;
}

/**
 * A missing pin means "current" and is never filled with a run. An *empty* pin
 * is reported as `null` too, so the caller can distinguish "no pin" from "a pin
 * that names nothing" by asking whether the key is present.
 */
export function parseReportSelection(params: URLSearchParams): ParsedReportSelection {
  return { runId: cleaned(params.get(REPORT_PARAMS.run)) };
}

/** Build an encoded report-tab URL that survives reload/back/forward. */
export function buildReportUrl(caseId: string, selection: ReportSelection = {}): string {
  const path = `/cases/${encodeURIComponent(caseId)}/report`;
  const query = [...toReportSearchParams(selection).entries()]
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join('&');
  return query ? `${path}?${query}` : path;
}

// ---------------------------------------------------------------------------
// S02 case-search selection
// ---------------------------------------------------------------------------

export const SEARCH_PARAMS = {
  q: 'q',
  type: 'type',
  publisher: 'publisher',
  status: 'status',
  publishedFrom: 'publishedFrom',
  publishedTo: 'publishedTo',
  offset: 'offset',
} as const;

export interface SearchSelection {
  q?: string | null;
  type?: 'claim' | 'evidence' | null;
  publisher?: string | null;
  status?: string | null;
  publishedFrom?: string | null;
  publishedTo?: string | null;
  offset?: number | null;
}

export interface ParsedSearchSelection {
  q: string;
  type: 'claim' | 'evidence' | null;
  publisher: string | null;
  status: string | null;
  publishedFrom: string | null;
  publishedTo: string | null;
  offset: number;
}

export function toSearchSearchParams(selection: SearchSelection): URLSearchParams {
  const params = new URLSearchParams();
  const q = cleaned(selection.q);
  const publisher = cleaned(selection.publisher);
  const status = cleaned(selection.status);
  const from = cleaned(selection.publishedFrom);
  const to = cleaned(selection.publishedTo);
  const offset = cleanedOffset(selection.offset, 0);
  if (q) params.set(SEARCH_PARAMS.q, q);
  if (selection.type === 'claim' || selection.type === 'evidence') {
    params.set(SEARCH_PARAMS.type, selection.type);
  }
  if (publisher) params.set(SEARCH_PARAMS.publisher, publisher);
  if (status) params.set(SEARCH_PARAMS.status, status);
  if (from) params.set(SEARCH_PARAMS.publishedFrom, from);
  if (to) params.set(SEARCH_PARAMS.publishedTo, to);
  if (offset !== null && offset > 0) params.set(SEARCH_PARAMS.offset, String(offset));
  return params;
}

export function parseSearchSelection(params: URLSearchParams): ParsedSearchSelection {
  const rawOffset = params.get(SEARCH_PARAMS.offset);
  const offset = rawOffset === null ? null : cleanedOffset(Number(rawOffset), 0);
  const rawType = params.get(SEARCH_PARAMS.type);
  return {
    q: cleaned(params.get(SEARCH_PARAMS.q)) ?? '',
    type: rawType === 'claim' || rawType === 'evidence' ? rawType : null,
    publisher: cleaned(params.get(SEARCH_PARAMS.publisher)),
    status: cleaned(params.get(SEARCH_PARAMS.status)),
    publishedFrom: cleaned(params.get(SEARCH_PARAMS.publishedFrom)),
    publishedTo: cleaned(params.get(SEARCH_PARAMS.publishedTo)),
    offset: offset ?? 0,
  };
}

export function buildSearchUrl(caseId: string, selection: SearchSelection): string {
  const path = `/cases/${encodeURIComponent(caseId)}/search`;
  const query = [...toSearchSearchParams(selection).entries()]
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join('&');
  return query ? `${path}?${query}` : path;
}

/**
 * Search filter metadata a local saved view may persist (contracts §5).
 * Free-text `q` and paging (`offset`) are deliberately absent: the query is
 * only stored through the explicit consent step and paging is never stored.
 */
export const SEARCH_SAVED_FILTER_KEYS = [
  SEARCH_PARAMS.type,
  SEARCH_PARAMS.publisher,
  SEARCH_PARAMS.status,
  SEARCH_PARAMS.publishedFrom,
  SEARCH_PARAMS.publishedTo,
] as const;

/** Non-empty, allowlisted search filters for a local saved view. */
export function searchSavedFilters(selection: SearchSelection): Record<string, string> {
  const params = toSearchSearchParams(selection);
  const filters: Record<string, string> = {};
  for (const key of SEARCH_SAVED_FILTER_KEYS) {
    const value = params.get(key);
    if (value) filters[key] = value;
  }
  return filters;
}

// ---------------------------------------------------------------------------
// R02 per-view URL allowlists, historical boundary and session memory
// ---------------------------------------------------------------------------

/**
 * Every case-workspace destination. The 12 in-case tabs plus the four
 * specialized routes that already exist; no new path is invented here.
 */
export type CaseViewId =
  | 'overview'
  | 'search'
  | 'evidence'
  | 'claims'
  | 'compare'
  | 'sources'
  | 'parties'
  | 'map'
  | 'timeline'
  | 'network'
  | 'narratives'
  | 'exceptions'
  | 'report'
  | 'changes'
  | 'run-history'
  | 'pipeline';

/** Path segment per destination; the empty string is the case root. */
export const CASE_VIEW_PATHS: Record<CaseViewId, string> = {
  overview: '',
  search: 'search',
  evidence: 'evidence',
  claims: 'claims',
  compare: 'compare',
  sources: 'sources',
  parties: 'parties',
  map: 'map',
  timeline: 'timeline',
  network: 'network',
  narratives: 'narratives',
  exceptions: 'exceptions',
  report: 'report',
  changes: 'changes',
  'run-history': 'run-history',
  pipeline: 'pipeline',
};

/**
 * Views whose readers accept a historical (`snapshot`) selector. Everything
 * else is current-only and must never reinterpret a frozen link as live data.
 *
 * The claims *list* is served by a current-only overview reader, so a pinned
 * observation on `claims` is an unsupported-historical request rather than a
 * frozen list (claim detail is frozen inside the evidence view).
 */
export const HISTORICAL_VIEWS: readonly CaseViewId[] = ['evidence', 'changes'];

export function isHistoricalView(view: CaseViewId): boolean {
  return HISTORICAL_VIEWS.includes(view);
}

export const CLAIM_STATUS_VALUES = [
  'confirmed',
  'probable',
  'alleged',
  'contested',
  'debunked',
  'unknown',
] as const;
export const CLAIM_SORT_VALUES = ['text', 'status'] as const;
export const EVIDENCE_SORT_VALUES = ['title', 'publishedAt'] as const;
export const HAS_CAPTURE_VALUES = ['yes', 'no'] as const;
export const SEARCH_TYPE_VALUES = ['claim', 'evidence'] as const;

/** Longest accepted free-text filter; keeps captured prose out of URLs. */
export const MAX_FILTER_TEXT_LENGTH = 256;

type ValueNormaliser = (raw: string) => string | null;

function filterText(maxLength: number = MAX_FILTER_TEXT_LENGTH): ValueNormaliser {
  return (raw) => {
    const trimmed = raw.trim();
    return trimmed !== '' && trimmed.length <= maxLength ? trimmed : null;
  };
}

function oneOf(values: readonly string[]): ValueNormaliser {
  return (raw) => {
    const trimmed = raw.trim();
    return values.includes(trimmed) ? trimmed : null;
  };
}

function integerAtLeast(minimum: number): ValueNormaliser {
  return (raw) => {
    const trimmed = raw.trim();
    if (!/^\d+$/.test(trimmed)) return null;
    const parsed = Number(trimmed);
    return Number.isInteger(parsed) && parsed >= minimum ? String(parsed) : null;
  };
}

/**
 * Browse-filter keys owned by the claims reader (contracts §3). Exported so the
 * tab never re-types a key the allowlist above already canonicalises.
 */
export const CLAIMS_BROWSE_PARAMS = {
  query: 'claimQuery',
  status: 'claimStatus',
  sort: 'claimSort',
  page: 'claimPage',
} as const;

/** Browse-filter keys owned by the evidence reader (contracts §3). */
export const EVIDENCE_BROWSE_PARAMS = {
  publisher: 'publisher',
  sourceType: 'sourceType',
  credibilityTier: 'credibilityTier',
  hasCapture: 'hasCapture',
  sort: 'evidenceSort',
  page: 'evidencePage',
} as const;

export interface ViewParamRule {
  key: string;
  accept: ValueNormaliser;
  /** Field message used when an explicit value is rejected. */
  message: string;
}

const browse = (key: string, accept: ValueNormaliser, message: string): ViewParamRule => ({
  key,
  accept,
  message,
});

const INSPECTOR_RULES: readonly ViewParamRule[] = [
  browse(INSPECTOR_PARAMS.claim, filterText(), 'Unknown claim selector.'),
  browse(INSPECTOR_PARAMS.evidence, filterText(), 'Unknown evidence selector.'),
  browse(INSPECTOR_PARAMS.capture, filterText(), 'Unknown capture selector.'),
  browse(INSPECTOR_PARAMS.citation, filterText(), 'Unknown citation selector.'),
  browse(INSPECTOR_PARAMS.start, integerAtLeast(0), 'Start must be a non-negative integer.'),
  browse(INSPECTOR_PARAMS.length, integerAtLeast(1), 'Length must be a positive integer.'),
];

const SNAPSHOT_RULE: ViewParamRule = browse(
  INSPECTOR_PARAMS.snapshot,
  filterText(),
  'Unknown snapshot selector.'
);

/**
 * Per-view allowlist. Order is canonical: a sanitised URL keeps exactly this
 * key order so re-navigation never rewrites a committed href.
 */
export const CASE_VIEW_ALLOWLISTS: Record<CaseViewId, readonly ViewParamRule[]> = {
  overview: [],
  search: [
    browse(SEARCH_PARAMS.q, filterText(), 'Search text is too long.'),
    browse(SEARCH_PARAMS.type, oneOf(SEARCH_TYPE_VALUES), 'Type must be claim or evidence.'),
    browse(SEARCH_PARAMS.publisher, filterText(), 'Publisher filter is too long.'),
    browse(SEARCH_PARAMS.status, filterText(), 'Status filter is too long.'),
    browse(SEARCH_PARAMS.publishedFrom, filterText(), 'Published-from filter is invalid.'),
    browse(SEARCH_PARAMS.publishedTo, filterText(), 'Published-to filter is invalid.'),
    browse(SEARCH_PARAMS.offset, integerAtLeast(0), 'Offset must be a non-negative integer.'),
  ],
  evidence: [
    ...INSPECTOR_RULES,
    SNAPSHOT_RULE,
    browse('publisher', filterText(), 'Publisher filter is too long.'),
    browse('sourceType', filterText(), 'Source type filter is too long.'),
    browse('credibilityTier', filterText(), 'Credibility tier filter is too long.'),
    browse('hasCapture', oneOf(HAS_CAPTURE_VALUES), 'Has-capture must be yes or no.'),
    browse('evidenceSort', oneOf(EVIDENCE_SORT_VALUES), 'Evidence sort must be title or publishedAt.'),
    browse('evidencePage', integerAtLeast(1), 'Page must be a positive integer.'),
  ],
  claims: [
    browse('claimQuery', filterText(), 'Claim query is too long.'),
    browse('claimStatus', oneOf(CLAIM_STATUS_VALUES), 'Status must be a known claim status.'),
    browse('claimSort', oneOf(CLAIM_SORT_VALUES), 'Sort must be text or status.'),
    browse('claimPage', integerAtLeast(1), 'Page must be a positive integer.'),
    SNAPSHOT_RULE,
  ],
  compare: [
    browse(COMPARISON_PARAMS.left, filterText(), 'Unknown left selector.'),
    browse(COMPARISON_PARAMS.right, filterText(), 'Unknown right selector.'),
    browse(COMPARISON_PARAMS.leftCapture, filterText(), 'Unknown left capture selector.'),
    browse(COMPARISON_PARAMS.rightCapture, filterText(), 'Unknown right capture selector.'),
    browse(COMPARISON_PARAMS.offset, integerAtLeast(0), 'Offset must be a non-negative integer.'),
    browse(COMPARISON_PARAMS.limit, integerAtLeast(1), 'Limit must be a positive integer.'),
  ],
  sources: [],
  parties: [],
  map: [],
  timeline: [],
  network: [],
  narratives: [],
  exceptions: [],
  // X02 pin: an explicit recorded-run selector, and only on this destination.
  report: [browse(REPORT_PARAMS.run, filterText(), 'Unknown run selector.')],
  changes: [
    // X01 ad-hoc mode: explicit, and only on this route.
    browse(CHANGES_PARAMS.mode, oneOf(CHANGES_MODES), 'Mode must be ad_hoc.'),
    browse(
      CHANGES_PARAMS.baselineSnapshot,
      filterText(),
      'Unknown baseline snapshot selector.'
    ),
    browse(
      CHANGES_PARAMS.targetSnapshot,
      filterText(),
      'Unknown target snapshot selector.'
    ),
    browse(CHANGES_PARAMS.run, filterText(), 'Unknown run selector.'),
    browse(CHANGES_PARAMS.claim, filterText(), 'Unknown claim selector.'),
    SNAPSHOT_RULE,
    browse(CHANGES_PARAMS.offset, integerAtLeast(0), 'Offset must be a non-negative integer.'),
    browse(CHANGES_PARAMS.limit, integerAtLeast(1), 'Limit must be a positive integer.'),
  ],
  'run-history': [],
  pipeline: [],
};

export interface SanitizedViewUrl {
  view: CaseViewId;
  /** Allowlisted, validated params in canonical order. */
  params: URLSearchParams;
  /** Present but not allowlisted for this view, therefore dropped. */
  dropped: string[];
  /** Allowlisted key -> field message when an explicit value was rejected. */
  invalid: Record<string, string>;
  /** Accepted historical selector for a historical view, else null. */
  snapshotId: string | null;
  /** A `snapshot` selector arrived on a current-only view. */
  unsupportedHistory: boolean;
  /** Canonical query string without the leading `?`. */
  search: string;
}

/**
 * Apply the view's allowlist: unknown keys are dropped, invalid explicit
 * values are rejected with a field message, and a `snapshot` selector on a
 * current-only view is reported as a conflict instead of being dropped.
 */
export function sanitizeViewUrl(
  view: CaseViewId,
  search: string | URLSearchParams = ''
): SanitizedViewUrl {
  const input =
    search instanceof URLSearchParams
      ? new URLSearchParams(search)
      : new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  const rules = CASE_VIEW_ALLOWLISTS[view];
  const allowed = new Set(rules.map((rule) => rule.key));
  const params = new URLSearchParams();
  const invalid: Record<string, string> = {};

  for (const rule of rules) {
    const raw = input.get(rule.key);
    if (raw === null) continue;
    const value = rule.accept(raw);
    if (value === null) {
      invalid[rule.key] = rule.message;
      continue;
    }
    params.set(rule.key, value);
  }

  // A historical selector is a conflict, not an unknown parameter: it stays
  // visible (never silently reinterpreted as current data).
  const rawSnapshot = cleaned(input.get(INSPECTOR_PARAMS.snapshot));
  const unsupportedHistory = rawSnapshot !== null && !isHistoricalView(view);

  const dropped: string[] = [];
  for (const key of input.keys()) {
    if (allowed.has(key) || dropped.includes(key)) continue;
    if (key === INSPECTOR_PARAMS.snapshot && unsupportedHistory) continue;
    dropped.push(key);
  }

  const query = [...params.entries()]
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join('&');

  return {
    view,
    params,
    dropped,
    invalid,
    snapshotId: unsupportedHistory ? null : cleaned(params.get(INSPECTOR_PARAMS.snapshot)),
    unsupportedHistory,
    search: query,
  };
}

/** Canonical query (no `?`) for a committed view URL. */
export function buildViewSearch(view: CaseViewId, search: string | URLSearchParams = ''): string {
  return sanitizeViewUrl(view, search).search;
}

/** Canonical, allowlisted href for a case destination. */
export function buildViewHref(
  caseId: string,
  view: CaseViewId,
  search: string | URLSearchParams = ''
): string {
  const path = `/cases/${encodeURIComponent(caseId)}`;
  const segment = CASE_VIEW_PATHS[view];
  const query = buildViewSearch(view, search);
  const fullPath = segment ? `${path}/${segment}` : path;
  return query ? `${fullPath}?${query}` : fullPath;
}

/** Parse a route's final path segment into a destination. */
export function viewFromPathSegment(segment: string | undefined | null): CaseViewId | null {
  const value = (segment ?? '').trim();
  if (value === '') return 'overview';
  return (Object.keys(CASE_VIEW_PATHS) as CaseViewId[]).find(
    (view) => CASE_VIEW_PATHS[view] === value
  ) ?? null;
}

/**
 * Classification of the explicit `snapshot` selector carried by a deep link.
 *
 * A pinned observation is never guessed from a malformed selector: an empty,
 * oversized or internally conflicting value is reported so the workspace can
 * show an invalid/unavailable state instead of deleting the pin and reading
 * current rows.
 */
export type SnapshotSelectorState = 'none' | 'valid' | 'invalid' | 'conflicting';

export interface SnapshotSelectorReading {
  state: SnapshotSelectorState;
  /** Every raw `snapshot` value supplied by the link, in URL order. */
  values: string[];
  /** The single accepted observation ID; null unless `state === 'valid'`. */
  snapshotId: string | null;
  /** Field sentence for the invalid/conflicting state; null otherwise. */
  reason: string | null;
}

/**
 * Read the explicit `snapshot` selector without choosing between duplicates.
 * Identical repeated values are one selector; two different values are a
 * conflict that only the operator can resolve. An explicit blank member is a
 * contradictory selector — the link names an observation and its absence at
 * once — so it names no unambiguous observation at all; a sibling value is never
 * elected in its place.
 */
export function readSnapshotSelector(
  search: string | URLSearchParams = ''
): SnapshotSelectorReading {
  const params =
    search instanceof URLSearchParams
      ? search
      : new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  const values = params.getAll(INSPECTOR_PARAMS.snapshot);
  if (values.length === 0) {
    return { state: 'none', values, snapshotId: null, reason: null };
  }
  const trimmed = values.map((value) => value.trim());
  const nonEmpty = trimmed.filter((value) => value !== '');
  if (nonEmpty.length !== trimmed.length) {
    return {
      state: 'invalid',
      values,
      snapshotId: null,
      reason:
        nonEmpty.length === 0
          ? 'The snapshot selector in this link is empty, so it names no observation.'
          : 'This link carries an empty snapshot selector, so it names no unambiguous observation.',
    };
  }
  const distinct = Array.from(new Set(nonEmpty));
  if (distinct.length > 1) {
    return {
      state: 'conflicting',
      values,
      snapshotId: null,
      reason: `This link carries ${distinct.length} different snapshot selectors (${distinct.join(
        ', '
      )}); no observation is chosen.`,
    };
  }
  const single = distinct[0];
  if (single.length > MAX_FILTER_TEXT_LENGTH) {
    return {
      state: 'invalid',
      values,
      snapshotId: null,
      reason: 'The snapshot selector in this link is longer than a recorded observation ID.',
    };
  }
  return { state: 'valid', values, snapshotId: single, reason: null };
}

/** Remove the historical selector while keeping other allowlisted params. */
export function stripHistoricalSelector(
  search: string | URLSearchParams = ''
): URLSearchParams {
  const params =
    search instanceof URLSearchParams
      ? new URLSearchParams(search)
      : new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  params.delete(INSPECTOR_PARAMS.snapshot);
  return params;
}

// ---------------------------------------------------------------------------
// Session memory of last committed per-view href (no new store)
// ---------------------------------------------------------------------------

const VIEW_MEMORY_PREFIX = 'triangulate:case-view:v1:';

function defaultStorage(): Storage | null {
  try {
    return typeof window !== 'undefined' ? window.sessionStorage : null;
  } catch {
    return null;
  }
}

function readMemory(caseId: string, storage: Storage | null): Record<string, string> {
  if (!storage) return {};
  try {
    const raw = storage.getItem(`${VIEW_MEMORY_PREFIX}${caseId}`);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    const memory: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof value === 'string') memory[key] = value;
    }
    return memory;
  } catch {
    return {};
  }
}

function writeMemory(
  caseId: string,
  storage: Storage | null,
  memory: Record<string, string>
): void {
  if (!storage) return;
  try {
    storage.setItem(`${VIEW_MEMORY_PREFIX}${caseId}`, JSON.stringify(memory));
  } catch {
    // Storage can be full or blocked; session memory is best effort.
  }
}

/** Record the last committed href for one view of one case. */
export function rememberCaseViewHref(
  caseId: string,
  view: CaseViewId,
  href: string,
  storage: Storage | null = defaultStorage()
): void {
  if (!caseId || !href.startsWith(`/cases/${encodeURIComponent(caseId)}`)) return;
  const memory = readMemory(caseId, storage);
  if (memory[view] === href) return;
  memory[view] = href;
  writeMemory(caseId, storage, memory);
}

/** Last committed href for one view of one case, if it is still valid. */
export function recallCaseViewHref(
  caseId: string,
  view: CaseViewId,
  storage: Storage | null = defaultStorage()
): string | null {
  const href = readMemory(caseId, storage)[view];
  if (typeof href !== 'string') return null;
  const prefix = `/cases/${encodeURIComponent(caseId)}`;
  if (href !== prefix && !href.startsWith(`${prefix}/`) && !href.startsWith(`${prefix}?`)) {
    return null;
  }
  return href;
}

/** Explicitly forget every remembered view href for a case. */
export function clearCaseViewMemory(
  caseId: string,
  storage: Storage | null = defaultStorage()
): void {
  if (!storage) return;
  try {
    storage.removeItem(`${VIEW_MEMORY_PREFIX}${caseId}`);
  } catch {
    // Best effort; nothing depends on the removal succeeding.
  }
}
