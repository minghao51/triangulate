/**
 * Local saved views v1 (contracts §5).
 *
 * Browser-local filter/sort metadata for the Search, Claims and Evidence
 * filter bars. Only an explicit user "Save" writes; there is no autosave and
 * no history. Free-text query values (`q`, `claimQuery`) are excluded by
 * default and are only stored when the caller passes `includeQuery: true`
 * after the separate consent step in the owning tab.
 *
 * "Local" is not "private": case ids and consented query text may be sensitive
 * and are readable by anyone using this browser profile. Nothing here writes
 * to the server, syncs, imports/exports, encrypts or claims confidentiality.
 */

import {
  CASE_VIEW_ALLOWLISTS,
  CLAIMS_BROWSE_PARAMS,
  CLAIM_SORT_VALUES,
  EVIDENCE_BROWSE_PARAMS,
  EVIDENCE_SORT_VALUES,
  MAX_FILTER_TEXT_LENGTH,
  SEARCH_PARAMS,
  SEARCH_SAVED_FILTER_KEYS,
} from './deep-links';

export const SAVED_VIEWS_STORAGE_KEY = 'triangulate.savedViews';
export const SAVED_VIEWS_SCHEMA_VERSION = 1;

/** Hard limits from contracts §5. */
export const SAVED_VIEW_LIMITS = {
  perOrigin: 50,
  perCase: 10,
  nameMaxCodepoints: 80,
  queryMaxCodepoints: 256,
  serializedMaxBytes: 64 * 1024,
} as const;

/**
 * Stored query text is capped by the URL allowlist as well, so a stored query
 * can always be applied back through the committed view URL.
 */
const STORED_QUERY_MAX_CODEPOINTS = Math.min(
  SAVED_VIEW_LIMITS.queryMaxCodepoints,
  MAX_FILTER_TEXT_LENGTH
);

export type SavedViewKind = 'claims' | 'evidence' | 'search';

export const SAVED_VIEW_KINDS: readonly SavedViewKind[] = ['claims', 'evidence', 'search'];

/**
 * Non-query filter metadata each view may persist. Query text is handled
 * separately (`includeQuery` + consent) and paging/selection ids are never
 * persisted.
 */
export const SAVED_VIEW_FILTER_KEYS: Record<SavedViewKind, readonly string[]> = {
  search: SEARCH_SAVED_FILTER_KEYS,
  claims: [CLAIMS_BROWSE_PARAMS.status],
  evidence: [
    EVIDENCE_BROWSE_PARAMS.publisher,
    EVIDENCE_BROWSE_PARAMS.sourceType,
    EVIDENCE_BROWSE_PARAMS.credibilityTier,
    EVIDENCE_BROWSE_PARAMS.hasCapture,
  ],
};

export const SAVED_VIEW_SORT_VALUES: Record<SavedViewKind, readonly string[]> = {
  search: [],
  claims: CLAIM_SORT_VALUES,
  evidence: EVIDENCE_SORT_VALUES,
};

export interface SavedView {
  /** Locally generated id; never an identity. */
  id: string;
  caseId: string;
  name: string;
  view: SavedViewKind;
  /** Allowlisted filter metadata only (never pagination or selection ids). */
  filters: Record<string, string>;
  sort: string | null;
  /** True only when a query was stored with explicit consent. */
  includeQuery: boolean;
  /** Consented search text; only ever set on a `search` view. */
  q: string | null;
}

export type SavedViewsStatus = 'ok' | 'unsupported-version' | 'corrupt' | 'unavailable';

export interface SavedViewsSnapshot {
  /** `ok` only when every stored entry validated. */
  status: SavedViewsStatus;
  /** Validated entries (optionally narrowed to one case). */
  views: SavedView[];
  /** Declared version of a payload we refused to interpret. */
  storedVersion: number | null;
  /** Entries present in storage but rejected by validation. */
  invalidEntries: number;
  /** Entries present in storage before validation/limits. */
  totalCount: number;
  /** Serialized payload size of the stored bytes. */
  bytes: number;
}

export type SaveSavedViewFailure =
  | 'invalid-name'
  | 'invalid-filters'
  | 'invalid-query'
  | 'limit-per-origin'
  | 'limit-per-case'
  | 'limit-bytes'
  | 'unsupported-version'
  | 'corrupt-data'
  | 'storage-unavailable';

export interface SavedViewDraft {
  caseId: string;
  view: SavedViewKind;
  name: string;
  filters?: Record<string, string | null | undefined>;
  sort?: string | null;
  /** Must be true only after the owning tab showed the explicit warning. */
  includeQuery?: boolean;
  query?: string | null;
}

export type SaveSavedViewResult =
  | { ok: true; view: SavedView; snapshot: SavedViewsSnapshot }
  | { ok: false; reason: SaveSavedViewFailure; message: string; ephemeral?: SavedView };

const STORED_ENTRY_KEYS = new Set([
  'id',
  'caseId',
  'name',
  'view',
  'filters',
  'sort',
  'includeQuery',
  'q',
]);

function defaultStorage(): Storage | null {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null;
  } catch {
    return null;
  }
}

function codepointLength(value: string): number {
  return Array.from(value).length;
}

function byteLength(value: string): number {
  if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(value).length;
  return encodeURIComponent(value).replace(/%[0-9A-F]{2}/gi, 'x').length;
}

function boundedText(raw: unknown, maxCodepoints: number): string | null {
  if (typeof raw !== 'string') return null;
  const trimmed = raw.trim();
  if (trimmed === '') return null;
  return codepointLength(trimmed) <= maxCodepoints ? trimmed : null;
}

function storedQuery(raw: unknown): string | null {
  if (typeof raw !== 'string') return null;
  const trimmed = raw.trim();
  if (trimmed === '') return null;
  const length = codepointLength(trimmed);
  return length >= 1 && length <= STORED_QUERY_MAX_CODEPOINTS ? trimmed : null;
}

function normaliser(view: SavedViewKind, key: string) {
  return CASE_VIEW_ALLOWLISTS[view].find((rule) => rule.key === key)?.accept ?? null;
}

function emptySnapshot(status: SavedViewsStatus): SavedViewsSnapshot {
  return {
    status,
    views: [],
    storedVersion: null,
    invalidEntries: 0,
    totalCount: 0,
    bytes: 0,
  };
}

/**
 * Validate one stored entry. Returns null when the entry must be excluded;
 * partial/unknown fields are never merged into a usable view.
 */
function parseStoredView(raw: unknown): SavedView | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const candidate = raw as Record<string, unknown>;
  for (const key of Object.keys(candidate)) {
    if (!STORED_ENTRY_KEYS.has(key)) return null;
  }

  const view = candidate.view;
  if (view !== 'claims' && view !== 'evidence' && view !== 'search') return null;

  const id = boundedText(candidate.id, 100);
  if (!id || !/^[A-Za-z0-9_-]+$/.test(id)) return null;
  const caseId = boundedText(candidate.caseId, 200);
  if (!caseId) return null;
  const name = boundedText(candidate.name, SAVED_VIEW_LIMITS.nameMaxCodepoints);
  if (!name) return null;
  if (typeof candidate.includeQuery !== 'boolean') return null;
  const includeQuery = candidate.includeQuery;

  if (!candidate.filters || typeof candidate.filters !== 'object' || Array.isArray(candidate.filters)) {
    return null;
  }
  const allowedFilterKeys = new Set<string>(SAVED_VIEW_FILTER_KEYS[view]);
  if (view === 'claims' && includeQuery) allowedFilterKeys.add(CLAIMS_BROWSE_PARAMS.query);
  const filters: Record<string, string> = {};
  for (const [key, value] of Object.entries(candidate.filters as Record<string, unknown>)) {
    if (!allowedFilterKeys.has(key)) return null;
    const accept = normaliser(view, key);
    const accepted = typeof value === 'string' && accept ? accept(value) : null;
    if (accepted === null) return null;
    filters[key] = accepted;
  }
  const claimQuery = view === 'claims' ? filters[CLAIMS_BROWSE_PARAMS.query] ?? null : null;
  if (claimQuery !== null && !includeQuery) return null;

  let sort: string | null = null;
  if (candidate.sort !== undefined && candidate.sort !== null) {
    if (typeof candidate.sort !== 'string') return null;
    const trimmed = candidate.sort.trim();
    if (trimmed !== '') {
      if (!SAVED_VIEW_SORT_VALUES[view].includes(trimmed)) return null;
      sort = trimmed;
    }
  }

  let q: string | null = null;
  if (Object.prototype.hasOwnProperty.call(candidate, 'q')) {
    // Only a consented search view may carry top-level `q`; claims keep their
    // consented query inside `filters.claimQuery`, evidence stores neither.
    if (view !== 'search' || !includeQuery) return null;
    q = storedQuery(candidate.q);
    if (q === null) return null;
    const accept = normaliser('search', SEARCH_PARAMS.q);
    if (!accept || accept(q) === null) return null;
  }

  const storesQuery = view === 'search' ? q !== null : claimQuery !== null;
  return {
    id,
    caseId,
    name,
    view,
    filters,
    sort,
    includeQuery: includeQuery && storesQuery,
    q,
  };
}

function storedViewPayload(view: SavedView): Record<string, unknown> {
  const stored: Record<string, unknown> = {
    id: view.id,
    caseId: view.caseId,
    name: view.name,
    view: view.view,
    filters: view.filters,
    includeQuery: view.includeQuery,
  };
  if (view.sort) stored.sort = view.sort;
  if (view.q) stored.q = view.q;
  return stored;
}

/** Serialized v1 payload; the only shape this feature ever writes. */
export function serializeSavedViews(views: readonly SavedView[]): string {
  return JSON.stringify({
    schemaVersion: SAVED_VIEWS_SCHEMA_VERSION,
    views: views.map(storedViewPayload),
  });
}

/**
 * Read and validate the stored payload. Unknown versions and corrupt data are
 * reported, never repaired in place: callers must not overwrite them without
 * an explicit reset.
 */
export function readSavedViews(storage: Storage | null = defaultStorage()): SavedViewsSnapshot {
  if (!storage) return emptySnapshot('unavailable');

  let raw: string | null;
  try {
    raw = storage.getItem(SAVED_VIEWS_STORAGE_KEY);
  } catch {
    return emptySnapshot('unavailable');
  }
  if (raw === null) {
    return { ...emptySnapshot('ok'), storedVersion: SAVED_VIEWS_SCHEMA_VERSION };
  }

  const bytes = byteLength(raw);
  if (bytes > SAVED_VIEW_LIMITS.serializedMaxBytes) {
    // An oversized payload is not interpreted at all; it is never rewritten in place.
    return { ...emptySnapshot('corrupt'), bytes };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ...emptySnapshot('corrupt'), bytes };
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { ...emptySnapshot('corrupt'), bytes };
  }

  const record = parsed as Record<string, unknown>;
  const version = record.schemaVersion;
  if (typeof version !== 'number' || !Number.isInteger(version)) {
    return { ...emptySnapshot('corrupt'), bytes };
  }
  if (version !== SAVED_VIEWS_SCHEMA_VERSION) {
    return { ...emptySnapshot('unsupported-version'), storedVersion: version, bytes };
  }

  const rawViews = record.views;
  if (!Array.isArray(rawViews)) {
    return { ...emptySnapshot('corrupt'), storedVersion: version, bytes };
  }

  const views: SavedView[] = [];
  const seenIds = new Set<string>();
  let invalidEntries = 0;
  for (const entry of rawViews) {
    if (views.length >= SAVED_VIEW_LIMITS.perOrigin) {
      invalidEntries += 1;
      continue;
    }
    const view = parseStoredView(entry);
    if (!view || seenIds.has(view.id)) {
      invalidEntries += 1;
      continue;
    }
    seenIds.add(view.id);
    views.push(view);
  }

  return {
    status: invalidEntries > 0 ? 'corrupt' : 'ok',
    views,
    storedVersion: version,
    invalidEntries,
    totalCount: rawViews.length,
    bytes,
  };
}

/** Validated saved views for one case. */
export function listSavedViews(
  caseId: string,
  storage: Storage | null = defaultStorage()
): SavedViewsSnapshot {
  const snapshot = readSavedViews(storage);
  return { ...snapshot, views: snapshot.views.filter((view) => view.caseId === caseId) };
}

let idCounter = 0;

/** Locally generated view id; not a user, device or server identity. */
export function createSavedViewId(): string {
  idCounter += 1;
  return `view-${Date.now().toString(36)}-${idCounter.toString(36)}${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

function persistViews(views: readonly SavedView[], storage: Storage): boolean {
  try {
    storage.setItem(SAVED_VIEWS_STORAGE_KEY, serializeSavedViews(views));
    return true;
  } catch {
    return false;
  }
}

function withViews(snapshot: SavedViewsSnapshot, views: SavedView[]): SavedViewsSnapshot {
  return {
    ...snapshot,
    status: 'ok',
    views,
    invalidEntries: 0,
    totalCount: views.length,
    bytes: byteLength(serializeSavedViews(views)),
  };
}

/**
 * Save one view. Returns an `ephemeral` view (session-only) when browser
 * storage is unavailable or full so nothing is silently lost.
 */
export function saveSavedView(
  draft: SavedViewDraft,
  storage: Storage | null = defaultStorage()
): SaveSavedViewResult {
  const name = boundedText(draft.name, SAVED_VIEW_LIMITS.nameMaxCodepoints);
  if (!name) {
    return {
      ok: false,
      reason: 'invalid-name',
      message: `A saved view name is required (1–${SAVED_VIEW_LIMITS.nameMaxCodepoints} characters).`,
    };
  }
  const caseId = boundedText(draft.caseId, 200);
  if (!caseId) {
    return { ok: false, reason: 'invalid-filters', message: 'A case is required to save a view.' };
  }

  const filters: Record<string, string> = {};
  const allowedKeys = SAVED_VIEW_FILTER_KEYS[draft.view];
  for (const [key, value] of Object.entries(draft.filters ?? {})) {
    if (!allowedKeys.includes(key)) continue;
    if (typeof value !== 'string') continue;
    const trimmed = value.trim();
    if (trimmed !== '') filters[key] = trimmed;
  }

  const requestedQuery = draft.includeQuery === true;
  const rawQuery = (draft.query ?? '').trim();
  if (requestedQuery && draft.view === 'evidence') {
    return {
      ok: false,
      reason: 'invalid-query',
      message: 'Evidence views cannot store query text.',
    };
  }
  let q: string | null = null;
  let includeQuery = false;
  if (requestedQuery) {
    q = storedQuery(rawQuery);
    if (q === null) {
      return {
        ok: false,
        reason: 'invalid-query',
        message: `A consented query must be 1–${STORED_QUERY_MAX_CODEPOINTS} characters.`,
      };
    }
    if (draft.view === 'claims') filters[CLAIMS_BROWSE_PARAMS.query] = q;
    includeQuery = true;
  }

  const candidate: Record<string, unknown> = {
    id: createSavedViewId(),
    caseId,
    name,
    view: draft.view,
    filters,
    includeQuery,
  };
  if (draft.sort) candidate.sort = draft.sort.trim();
  if (draft.view === 'search' && q !== null) candidate.q = q;

  const view = parseStoredView(candidate);
  if (!view) {
    return {
      ok: false,
      reason: 'invalid-filters',
      message: 'Those filter values cannot be saved as a local view.',
    };
  }

  const snapshot = readSavedViews(storage);
  if (snapshot.status === 'unsupported-version') {
    return {
      ok: false,
      reason: 'unsupported-version',
      message:
        'Saved views were written by a newer app version, so they were left untouched. This view can only be used for this session.',
      ephemeral: view,
    };
  }
  if (snapshot.status === 'corrupt') {
    return {
      ok: false,
      reason: 'corrupt-data',
      message:
        'Stored saved views could not be read, so they were left untouched. This view can only be used for this session until you discard the stored data.',
      ephemeral: view,
    };
  }
  if (!storage || snapshot.status === 'unavailable') {
    return {
      ok: false,
      reason: 'storage-unavailable',
      message: `Browser storage is unavailable, so “${view.name}” is kept for this session only.`,
      ephemeral: view,
    };
  }

  const caseCount = snapshot.views.filter((saved) => saved.caseId === view.caseId).length;
  if (caseCount >= SAVED_VIEW_LIMITS.perCase) {
    return {
      ok: false,
      reason: 'limit-per-case',
      message: `This case already has the maximum of ${SAVED_VIEW_LIMITS.perCase} saved views. Delete one first.`,
    };
  }
  if (snapshot.views.length >= SAVED_VIEW_LIMITS.perOrigin) {
    return {
      ok: false,
      reason: 'limit-per-origin',
      message: `This browser already has the maximum of ${SAVED_VIEW_LIMITS.perOrigin} saved views. Delete one first.`,
    };
  }

  const nextViews = [...snapshot.views, view];
  const payload = serializeSavedViews(nextViews);
  if (byteLength(payload) > SAVED_VIEW_LIMITS.serializedMaxBytes) {
    return {
      ok: false,
      reason: 'limit-bytes',
      message: 'The saved views storage limit would be exceeded. Delete a view or shorten the filters.',
    };
  }

  if (!persistViews(nextViews, storage)) {
    return {
      ok: false,
      reason: 'storage-unavailable',
      message: `Browser storage rejected the write, so “${view.name}” is kept for this session only.`,
      ephemeral: view,
    };
  }

  return { ok: true, view, snapshot: withViews(snapshot, nextViews) };
}

/** Delete one saved view. Corrupt/unsupported payloads are never rewritten. */
export function deleteSavedView(
  id: string,
  storage: Storage | null = defaultStorage()
): SavedViewsSnapshot {
  const snapshot = readSavedViews(storage);
  if (!storage || snapshot.status !== 'ok') return snapshot;
  const nextViews = snapshot.views.filter((view) => view.id !== id);
  if (nextViews.length === snapshot.views.length) return snapshot;
  return persistViews(nextViews, storage) ? withViews(snapshot, nextViews) : snapshot;
}

/** Delete every saved view that belongs to one case. */
export function deleteSavedViewsForCase(
  caseId: string,
  storage: Storage | null = defaultStorage()
): SavedViewsSnapshot {
  const snapshot = readSavedViews(storage);
  if (!storage || snapshot.status !== 'ok') return snapshot;
  const nextViews = snapshot.views.filter((view) => view.caseId !== caseId);
  if (nextViews.length === snapshot.views.length) return snapshot;
  return persistViews(nextViews, storage) ? withViews(snapshot, nextViews) : snapshot;
}

/**
 * Explicit reset of every feature-owned view (including a corrupt or
 * unsupported payload). Removes only this feature's key; never `clear()`.
 */
export function deleteAllSavedViews(storage: Storage | null = defaultStorage()): SavedViewsSnapshot {
  if (!storage) return emptySnapshot('unavailable');
  try {
    storage.removeItem(SAVED_VIEWS_STORAGE_KEY);
  } catch {
    return readSavedViews(storage);
  }
  return { ...emptySnapshot('ok'), storedVersion: SAVED_VIEWS_SCHEMA_VERSION };
}

/**
 * Observe cross-tab changes without applying anything: listeners only re-read
 * the list, so an active form and the current view are never reset.
 */
export function subscribeToSavedViews(listener: () => void): () => void {
  if (typeof window === 'undefined') return () => {};
  const handler = (event: StorageEvent) => {
    if (event.key !== null && event.key !== SAVED_VIEWS_STORAGE_KEY) return;
    listener();
  };
  window.addEventListener('storage', handler);
  return () => window.removeEventListener('storage', handler);
}

/** Display labels for the allowlisted filter keys (no query text). */
const FILTER_SUMMARY_LABELS: Record<string, string> = {
  type: 'type',
  publisher: 'publisher',
  status: 'status',
  publishedFrom: 'published from',
  publishedTo: 'published before',
  sourceType: 'source type',
  credibilityTier: 'credibility tier',
  hasCapture: 'capture',
};

/** Human-readable, non-sensitive summary of what a saved view restores. */
export function describeSavedView(view: SavedView): string {
  const parts: string[] = [`${view.view} view`];
  for (const [key, value] of Object.entries(view.filters)) {
    if (key === CLAIMS_BROWSE_PARAMS.query) continue;
    parts.push(`${FILTER_SUMMARY_LABELS[key] ?? key}: ${value}`);
  }
  if (view.sort) parts.push(`sort: ${view.sort}`);
  if (view.includeQuery) {
    parts.push(view.view === 'search' ? 'includes search text' : 'includes claim filter text');
  }
  return parts.join(' · ');
}
