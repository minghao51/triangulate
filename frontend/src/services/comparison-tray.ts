/**
 * Session-only, case-scoped comparison draft ("compare tray").
 *
 * The tray is deliberately a focused module over module memory rather than a
 * new store: it holds at most two **distinct** evidence sources plus the pinned
 * captures that belong to them, for exactly one case and one historical context
 * at a time. Nothing is persisted, nothing is sent to the server, and nothing is
 * ever replaced silently — a third distinct selection and a repeated evidence
 * item are refused with a visible message and the existing entries stay put.
 *
 * Every reader passes its own case and context, so a tray built in one case can
 * never be read from another: `getComparisonTray` answers with an empty draft
 * when the query does not match the active record.
 */

/** A comparison needs exactly two distinct evidence sources; never a third. */
export const COMPARISON_TRAY_CAP = 2;

export interface TrayEntry {
  /** Stable evidence ID; the comparison identity. */
  evidenceId: string;
  /** Pinned capture ID when one was chosen; the server resolves defaults otherwise. */
  captureId: string | null;
  title: string | null;
  publisher: string | null;
}

export interface ComparisonTraySnapshot {
  caseId: string;
  contextId: string;
  entries: readonly TrayEntry[];
  /** Explicit notice shown after a draft was cleared. */
  notice: string | null;
  /** Explicit refusal message for the last rejected selection. */
  rejection: string | null;
}

export type TrayRefusalReason =
  | 'duplicate-evidence'
  | 'tray-full'
  | 'invalid-selection'
  | 'context-mismatch';

export interface TrayAddResult {
  ok: boolean;
  reason: TrayRefusalReason | null;
  message: string | null;
  entries: readonly TrayEntry[];
}

export const TRAY_DUPLICATE_MESSAGE =
  'The same evidence item cannot be compared with itself, even when it has more than one capture version. Its older versions stay in capture history, not Compare.';

export const TRAY_FULL_MESSAGE =
  'The comparison draft already holds two distinct sources. Nothing was replaced: remove one source before adding another.';

export const TRAY_INVALID_MESSAGE =
  'Select an evidence row before adding it to the comparison draft.';

export const TRAY_CASE_MISMATCH_MESSAGE =
  'That selection belongs to another case or historical context. The draft was left unchanged; open this case view before adding to comparison.';

export const TRAY_CASE_NOTICE =
  'The comparison draft was cleared because the case changed. Selections never carry across cases.';

export const TRAY_CONTEXT_NOTICE =
  'The comparison draft was cleared because the historical context changed. Current and historical selections are never mixed.';

const EMPTY_TRAY: ComparisonTraySnapshot = Object.freeze({
  caseId: '',
  contextId: '',
  entries: Object.freeze([]) as readonly TrayEntry[],
  notice: null,
  rejection: null,
});

let record: ComparisonTraySnapshot | null = null;
const listeners = new Set<() => void>();

function commit(next: ComparisonTraySnapshot): void {
  record = Object.freeze({
    ...next,
    entries: Object.freeze([...next.entries]) as readonly TrayEntry[],
  });
  for (const listener of [...listeners]) listener();
}

/** Subscribe to tray changes; returns the unsubscribe function. */
export function subscribeComparisonTray(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function scoped(
  caseId: string,
  contextId: string
): ComparisonTraySnapshot | null {
  if (!record) return null;
  if (record.caseId !== caseId) return null;
  if (record.contextId !== contextId) return null;
  return record;
}

/**
 * The draft for one case/context. The returned value keeps a stable identity
 * until the tray actually changes, so it is safe as a React snapshot.
 */
export function getComparisonTray(
  caseId: string,
  contextId: string
): ComparisonTraySnapshot {
  return scoped(caseId, contextId) ?? EMPTY_TRAY;
}

/** The raw record regardless of scope; only for reconciliation and tests. */
export function peekComparisonTray(): ComparisonTraySnapshot | null {
  return record;
}

function entryOf(selection: Partial<TrayEntry> & { evidenceId?: string | null }): TrayEntry {
  const title = typeof selection.title === 'string' ? selection.title.trim() : '';
  const publisher =
    typeof selection.publisher === 'string' ? selection.publisher.trim() : '';
  const captureId =
    typeof selection.captureId === 'string' ? selection.captureId.trim() : '';
  return {
    evidenceId: (selection.evidenceId ?? '').trim(),
    captureId: captureId === '' ? null : captureId,
    title: title === '' ? null : title,
    publisher: publisher === '' ? null : publisher,
  };
}

/**
 * Add one evidence source. Refusals are explicit and leave the draft untouched:
 * a repeated evidence item (even with another capture) and a third distinct
 * source are both rejected, never auto-replaced.
 */
export function addToComparisonTray(
  caseId: string,
  contextId: string,
  selection: Partial<TrayEntry> & { evidenceId?: string | null }
): TrayAddResult {
  const entry = entryOf(selection);
  const current = scoped(caseId, contextId);

  if (!caseId || entry.evidenceId === '') {
    return {
      ok: false,
      reason: 'invalid-selection',
      message: TRAY_INVALID_MESSAGE,
      entries: current?.entries ?? EMPTY_TRAY.entries,
    };
  }

  // A draft that belongs to another case or context is never extended, cleared
  // or replaced from here; the owning view must reconcile first.
  if (!current && record && record.entries.length > 0) {
    return {
      ok: false,
      reason: 'context-mismatch',
      message: TRAY_CASE_MISMATCH_MESSAGE,
      entries: EMPTY_TRAY.entries,
    };
  }

  const entries = current?.entries ?? [];

  if (entries.some((existing) => existing.evidenceId === entry.evidenceId)) {
    commit({
      caseId,
      contextId,
      entries,
      notice: null,
      rejection: TRAY_DUPLICATE_MESSAGE,
    });
    return {
      ok: false,
      reason: 'duplicate-evidence',
      message: TRAY_DUPLICATE_MESSAGE,
      entries,
    };
  }

  if (entries.length >= COMPARISON_TRAY_CAP) {
    commit({
      caseId,
      contextId,
      entries,
      notice: null,
      rejection: TRAY_FULL_MESSAGE,
    });
    return {
      ok: false,
      reason: 'tray-full',
      message: TRAY_FULL_MESSAGE,
      entries,
    };
  }

  const nextEntries = [...entries, entry];
  commit({ caseId, contextId, entries: nextEntries, notice: null, rejection: null });
  return { ok: true, reason: null, message: null, entries: nextEntries };
}

/** Remove one entry by its stable evidence ID. */
export function removeFromComparisonTray(
  caseId: string,
  contextId: string,
  evidenceId: string
): readonly TrayEntry[] {
  const current = scoped(caseId, contextId);
  if (!current) return EMPTY_TRAY.entries;
  const entries = current.entries.filter((entry) => entry.evidenceId !== evidenceId);
  if (entries.length === current.entries.length) return current.entries;
  commit({ caseId, contextId, entries, notice: null, rejection: null });
  return entries;
}

/** Forget the draft explicitly, optionally with a notice explaining why. */
export function clearComparisonTray(
  caseId: string,
  contextId: string,
  notice: string | null = null
): void {
  if (!record && notice === null) return;
  commit({ caseId, contextId, entries: [], notice, rejection: null });
}

export type TrayContextChange = 'case' | 'context' | null;

/**
 * Clear a draft that no longer matches the visible case or historical context.
 *
 * The clear is announced (the notice stays readable in the newly scoped record)
 * and never touches a draft that already matches. An empty draft is adopted
 * silently because there is nothing to clear.
 */
export function reconcileComparisonTrayContext(
  caseId: string,
  contextId: string
): TrayContextChange {
  if (!record) return null;
  if (record.caseId === caseId && record.contextId === contextId) return null;

  const changed: TrayContextChange = record.caseId !== caseId ? 'case' : 'context';
  if (record.entries.length === 0) {
    commit({ caseId, contextId, entries: [], notice: null, rejection: null });
    return null;
  }

  commit({
    caseId,
    contextId,
    entries: [],
    notice: changed === 'case' ? TRAY_CASE_NOTICE : TRAY_CONTEXT_NOTICE,
    rejection: null,
  });
  return changed;
}

/**
 * The historical context a view is showing: a frozen `snapshot` selector makes
 * it historical, everything else is the current context. Current and historical
 * drafts are never mixed.
 */
export const CURRENT_COMPARISON_CONTEXT = 'current';

export function comparisonContextFromSearchParams(params: URLSearchParams): string {
  const snapshot = params.get('snapshot');
  const trimmed = typeof snapshot === 'string' ? snapshot.trim() : '';
  return trimmed === '' ? CURRENT_COMPARISON_CONTEXT : `snapshot:${trimmed}`;
}

/** Test-only reset; the tray is session memory with no persistence. */
export function resetComparisonTray(): void {
  record = null;
  for (const listener of [...listeners]) listener();
}
