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
  const match = chars.slice(relativeStart, relativeEnd).join('');
  if (match !== quote) return null;
  return {
    before: chars.slice(0, relativeStart).join(''),
    match,
    after: chars.slice(relativeEnd).join(''),
  };
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
