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
  run: 'run',
  claim: 'claim',
  snapshot: 'snapshot',
  offset: 'offset',
  limit: 'limit',
} as const;

export interface ChangesSelection {
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

export function toChangesSearchParams(selection: ChangesSelection): URLSearchParams {
  const params = new URLSearchParams();
  const runId = cleaned(selection.runId);
  const claimId = cleaned(selection.claimId);
  const snapshotId = cleaned(selection.snapshotId);
  const offset = cleanedOffset(selection.offset, 0);
  const limit = cleanedOffset(selection.limit, 1);

  if (runId) params.set(CHANGES_PARAMS.run, runId);
  if (claimId) params.set(CHANGES_PARAMS.claim, claimId);
  if (snapshotId) params.set(CHANGES_PARAMS.snapshot, snapshotId);
  if (offset !== null) params.set(CHANGES_PARAMS.offset, String(offset));
  if (limit !== null) params.set(CHANGES_PARAMS.limit, String(limit));
  return params;
}

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
