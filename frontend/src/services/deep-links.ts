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
}

export interface ParsedInspectorSelection {
  claimId: string | null;
  evidenceId: string | null;
  captureId: string | null;
  citationId: string | null;
  start: number | null;
  length: number | null;
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

  if (claimId) params.set(INSPECTOR_PARAMS.claim, claimId);
  if (evidenceId) params.set(INSPECTOR_PARAMS.evidence, evidenceId);
  if (captureId) params.set(INSPECTOR_PARAMS.capture, captureId);
  if (citationId) params.set(INSPECTOR_PARAMS.citation, citationId);
  if (start !== null) params.set(INSPECTOR_PARAMS.start, String(start));
  if (length !== null) params.set(INSPECTOR_PARAMS.length, String(length));

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
