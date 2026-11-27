import type { AlignmentStatus, EffectiveRelation } from '../../types/backend-models';

/**
 * Human-readable, deliberately non-promotional labels.
 *
 * In particular: an exact quotation is alignment, never corroboration, and no
 * label here may read as "confirmed" or imply reviewer sign-off.
 */
export const RELATION_LABELS: Record<EffectiveRelation, string> = {
  reported_by: 'Reported by the source (not corroboration)',
  supports: 'Supports (explicit assessment)',
  contradicts: 'Contradicts (explicit assessment)',
  uncertain: 'Uncertain / unvalidated',
};

export const ALIGNMENT_LABELS: Record<AlignmentStatus, string> = {
  exact: 'Exact validated quotation',
  ambiguous: 'Ambiguous — repeated text could not be disambiguated',
  no_match: 'No exact match in the captured text',
  not_provided: 'No quotation was provided',
  source_unavailable: 'Source text unavailable in this capture',
};

export function relationLabel(value: string | null | undefined): string {
  if (value && value in RELATION_LABELS) {
    return RELATION_LABELS[value as EffectiveRelation];
  }
  return RELATION_LABELS.uncertain;
}

export function alignmentLabel(value: string | null | undefined): string {
  if (value && value in ALIGNMENT_LABELS) {
    return ALIGNMENT_LABELS[value as AlignmentStatus];
  }
  return 'Alignment not assessed';
}

export function isExactAlignment(value: string | null | undefined): boolean {
  return value === 'exact';
}

/** Missing/blank values stay explicitly unknown; nothing is guessed. */
export function knownOrUnknown(value: unknown): string {
  if (value === null || value === undefined) return 'Unknown';
  if (typeof value === 'string') return value.trim() === '' ? 'Unknown' : value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return String(value);
}

/** Format a persisted timestamp without inventing a timezone offset. */
export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return 'Unknown';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

/**
 * Only absolute http(s) URLs are rendered as links. This blocks
 * `javascript:`, `data:` and other unexpected schemes from frozen metadata.
 */
export function safeExternalUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return parsed.toString();
    }
  } catch {
    // Relative or malformed values are not treated as external links.
  }
  return null;
}

/** Number of Unicode code points, matching the API's offset unit. */
export function codePointLength(text: string): number {
  return Array.from(text).length;
}

/**
 * One exact code-point window, matching the server's Python slice semantics
 * (`text[start:start + length]`).
 *
 * String indices are UTF-16 code units, so `text.slice` would split surrogate
 * pairs and count astral characters twice. `Array.from` iterates code points
 * instead: one emoji, one Deseret letter and one combining-mark sequence all
 * count exactly as Python counts them. No NFKC/casefold normalisation happens
 * here — offsets are only meaningful against unchanged text.
 */
export function codePointSlice(
  text: string,
  start: number,
  length: number
): string {
  if (!Number.isFinite(start) || !Number.isFinite(length) || length <= 0) {
    return '';
  }
  const chars = Array.from(text);
  const from = Math.min(Math.max(0, Math.trunc(start)), chars.length);
  const to = Math.min(from + Math.trunc(length), chars.length);
  return chars.slice(from, to).join('');
}

export interface HighlightParts {
  before: string;
  match: string;
  after: string;
}

/**
 * Split one capture window around an exact validated quotation using code
 * points (never raw UTF-16 indices), then verify the slice equals the quote.
 *
 * Returns `null` when the offsets are missing, outside this window, or do not
 * reproduce the quotation exactly — the UI then shows an explanatory state
 * instead of a fabricated highlight.
 */
export function splitHighlight(
  windowText: string,
  windowStart: number,
  quote: string | null | undefined,
  startChar: number | null | undefined,
  endChar: number | null | undefined
): HighlightParts | null {
  if (!quote || typeof startChar !== 'number' || typeof endChar !== 'number') {
    return null;
  }
  const relativeStart = startChar - windowStart;
  const relativeEnd = endChar - windowStart;
  const chars = Array.from(windowText);
  if (relativeStart < 0 || relativeEnd > chars.length || relativeEnd <= relativeStart) {
    return null;
  }
  const match = codePointSlice(windowText, relativeStart, relativeEnd - relativeStart);
  if (match !== quote) return null;
  return {
    before: chars.slice(0, relativeStart).join(''),
    match,
    after: chars.slice(relativeEnd).join(''),
  };
}

/**
 * The five explicit inspector diagnostics plus the `exact` reading.
 *
 * Every state has distinct text and its own stable `data-state` attribute, so
 * the diagnostic is never carried by colour alone. `legacy` is the honest
 * fallback for records that predate alignment assessment: nothing is inferred
 * from the absence of a recognised status.
 */
export type InspectorDiagnosticState =
  | 'exact'
  | 'missing-quotation'
  | 'source-unavailable'
  | 'ambiguous'
  | 'no-match'
  | 'legacy';

export interface InspectorDiagnostic {
  state: InspectorDiagnosticState;
  /** Stable hook for tests and consumers; never a CSS-only distinction. */
  attribute: string;
  label: string;
  message: string;
  tone: 'ok' | 'warning' | 'neutral';
}

const KNOWN_ALIGNMENT = new Set<string>([
  'exact',
  'ambiguous',
  'no_match',
  'not_provided',
  'source_unavailable',
]);

const DIAGNOSTICS: Record<InspectorDiagnosticState, InspectorDiagnostic> = {
  exact: {
    state: 'exact',
    attribute: 'inspector-exact',
    label: ALIGNMENT_LABELS.exact,
    message:
      'The quotation matches these code points exactly. That is alignment with the captured text, not corroboration and not reviewer confirmation.',
    tone: 'ok',
  },
  'missing-quotation': {
    state: 'missing-quotation',
    attribute: 'inspector-missing-quotation',
    label: 'No quotation was recorded',
    message:
      'This link records no quotation, so there is nothing to highlight in the captured text. A missing quotation is not a failed match and does not make the claim supported.',
    tone: 'neutral',
  },
  'source-unavailable': {
    state: 'source-unavailable',
    attribute: 'inspector-source-unavailable',
    label: 'Source text unavailable',
    message:
      'The captured source text was unavailable when this link was assessed, so the quotation could not be checked against it. This does not claim the quotation is absent from the source.',
    tone: 'warning',
  },
  ambiguous: {
    state: 'ambiguous',
    attribute: 'inspector-ambiguous',
    label: 'Ambiguous quotation',
    message:
      'The quotation occurs more than once in the captured text and no offsets disambiguate it. The inspector never picks one occurrence for you.',
    tone: 'warning',
  },
  'no-match': {
    state: 'no-match',
    attribute: 'inspector-no-match',
    label: 'No exact match in the captured text',
    message:
      'The recorded quotation does not appear exactly in this capture. It may differ in wording or punctuation; nothing is re-matched fuzzily here.',
    tone: 'warning',
  },
  legacy: {
    state: 'legacy',
    attribute: 'inspector-legacy',
    label: 'Legacy record — alignment not recorded',
    message:
      'This link carries no recognised alignment status, offsets or quotation because it predates that assessment. Stored values are shown exactly as recorded and nothing is inferred.',
    tone: 'neutral',
  },
};

/**
 * Resolve one explicit diagnostic for a passage, derived only from the frozen
 * record: the recorded alignment status and whether a quotation exists.
 */
export function resolveInspectorDiagnostic(
  alignmentStatus: string | null | undefined,
  quote: string | null | undefined
): InspectorDiagnostic {
  const hasQuote = typeof quote === 'string' && quote.length > 0;
  switch (alignmentStatus) {
    case 'exact':
      return hasQuote ? DIAGNOSTICS.exact : DIAGNOSTICS.legacy;
    case 'ambiguous':
      return DIAGNOSTICS.ambiguous;
    case 'no_match':
      return DIAGNOSTICS['no-match'];
    case 'source_unavailable':
      return DIAGNOSTICS['source-unavailable'];
    case 'not_provided':
      return DIAGNOSTICS['missing-quotation'];
    default:
      return DIAGNOSTICS.legacy;
  }
}

/** Known statuses are recognised; anything else is a legacy/unknown record. */
export function isKnownAlignment(value: string | null | undefined): boolean {
  return Boolean(value) && KNOWN_ALIGNMENT.has(value as string);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Compact, factual rendering of one frozen provenance value. */
export function summariseProvenance(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') return value.trim() === '' ? null : value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (isRecord(value)) {
    const parts = Object.entries(value)
      .filter(([, item]) => item !== null && item !== undefined && typeof item !== 'object')
      .map(([key, item]) => `${key}: ${String(item)}`);
    if (parts.length > 0) return parts.join('; ');
    try {
      return JSON.stringify(value);
    } catch {
      return null;
    }
  }
  return null;
}

/** Extraction scope recorded on the frozen capture metadata, when present. */
export function extractionScope(metadata: Record<string, unknown> | null | undefined): string {
  if (!metadata) return 'Unknown';
  const extraction = metadata.extraction;
  if (isRecord(extraction)) {
    const start = extraction.scope_start;
    const end = extraction.scope_end;
    if (typeof start === 'number' && typeof end === 'number') {
      return `code points ${start}–${end}`;
    }
    if (typeof extraction.status === 'string') {
      return `status ${extraction.status}; scope and limits not recorded`;
    }
  }
  return summariseProvenance(extraction) ?? 'Unknown';
}
