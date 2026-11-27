import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  SAVED_VIEW_LIMITS,
  SAVED_VIEWS_SCHEMA_VERSION,
  SAVED_VIEWS_STORAGE_KEY,
  createSavedViewId,
  deleteAllSavedViews,
  deleteSavedView,
  deleteSavedViewsForCase,
  describeSavedView,
  listSavedViews,
  readSavedViews,
  saveSavedView,
  serializeSavedViews,
  subscribeToSavedViews,
  type SavedViewDraft,
} from './saved-views';

/** Minimal in-memory Storage; jsdom localStorage is shared across tests. */
class MemoryStorage implements Storage {
  protected map = new Map<string, string>();

  get length(): number {
    return this.map.size;
  }

  clear(): void {
    this.map.clear();
  }

  getItem(key: string): string | null {
    return this.map.has(key) ? this.map.get(key)! : null;
  }

  key(index: number): string | null {
    return Array.from(this.map.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.map.delete(key);
  }

  setItem(key: string, value: string): void {
    this.map.set(key, value);
  }

  raw(key: string): string | null {
    return this.map.get(key) ?? null;
  }
}

class QuotaStorage extends MemoryStorage {
  setItem(): void {
    throw new Error('QuotaExceededError');
  }
}

const searchDraft = (overrides: Partial<SavedViewDraft> = {}): SavedViewDraft => ({
  caseId: 'case-1',
  view: 'search',
  name: 'Evidence by publisher',
  filters: { type: 'evidence', publisher: 'Wire', status: '', publishedFrom: null },
  sort: null,
  includeQuery: false,
  query: 'needle',
  ...overrides,
});

function storedPayload(storage: MemoryStorage): Record<string, unknown> {
  const raw = storage.getItem(SAVED_VIEWS_STORAGE_KEY);
  expect(raw).not.toBeNull();
  return JSON.parse(raw as string) as Record<string, unknown>;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('saved views v1 — storage shape and allowlist', () => {
  it('stores only allowlisted filter metadata, excluding query text by default', () => {
    const storage = new MemoryStorage();
    const result = saveSavedView(searchDraft(), storage);
    expect(result.ok).toBe(true);

    const payload = storedPayload(storage);
    expect(payload.schemaVersion).toBe(SAVED_VIEWS_SCHEMA_VERSION);
    const entries = payload.views as Array<Record<string, unknown>>;
    expect(entries).toHaveLength(1);
    const entry = entries[0];
    expect(entry.caseId).toBe('case-1');
    expect(entry.view).toBe('search');
    expect(entry.includeQuery).toBe(false);
    expect(entry.filters).toEqual({
      type: 'evidence',
      publisher: 'Wire',
    });
    // No query, no paging, no arbitrary values.
    expect(entry).not.toHaveProperty('q');
    expect(entry).not.toHaveProperty('offset');
    expect((entry.filters as Record<string, unknown>)).not.toHaveProperty('claimQuery');
    expect(Object.keys(entry).sort()).toEqual([
      'caseId',
      'filters',
      'id',
      'includeQuery',
      'name',
      'view',
    ]);
  });

  it('round-trips a validated view through listSavedViews', () => {
    const storage = new MemoryStorage();
    const result = saveSavedView(searchDraft(), storage);
    expect(result.ok).toBe(true);

    const snapshot = listSavedViews('case-1', storage);
    expect(snapshot.status).toBe('ok');
    expect(snapshot.views).toHaveLength(1);
    const view = snapshot.views[0];
    expect(view.name).toBe('Evidence by publisher');
    expect(view.filters).toEqual({ type: 'evidence', publisher: 'Wire' });
    expect(view.sort).toBeNull();
    expect(view.includeQuery).toBe(false);
    expect(view.q).toBeNull();
    expect(listSavedViews('case-2', storage).views).toHaveLength(0);
  });

  it('rejects unknown filter keys, unknown top-level keys and bad sort values on read', () => {
    const storage = new MemoryStorage();
    const base = {
      id: 'view-1',
      caseId: 'case-1',
      name: 'Example',
      view: 'evidence',
      filters: { publisher: 'Wire' },
      includeQuery: false,
    };
    storage.setItem(
      SAVED_VIEWS_STORAGE_KEY,
      JSON.stringify({
        schemaVersion: 1,
        views: [
          base,
          { ...base, id: 'view-2', filters: { publisher: 'Wire', notes: 'secret' } },
          { ...base, id: 'view-3', arbitrary: { nested: true } },
          { ...base, id: 'view-4', sort: 'not-a-sort' },
          { ...base, id: 'view-5', name: 'x'.repeat(SAVED_VIEW_LIMITS.nameMaxCodepoints + 1) },
          { ...base, id: 'view-6', caseId: '' },
        ],
      })
    );

    const snapshot = readSavedViews(storage);
    expect(snapshot.views).toHaveLength(1);
    expect(snapshot.views[0].id).toBe('view-1');
    expect(snapshot.invalidEntries).toBe(5);
    // Partially corrupt payloads stay read-only; nothing is repaired in place.
    expect(snapshot.status).toBe('corrupt');
  });
});

describe('saved views v1 — query-text consent', () => {
  it('stores consented search text only when includeQuery is true', () => {
    const storage = new MemoryStorage();
    const denied = saveSavedView(searchDraft({ includeQuery: false, query: 'secret term' }), storage);
    expect(denied.ok).toBe(true);
    expect(listSavedViews('case-1', storage).views[0]).toMatchObject({
      includeQuery: false,
      q: null,
    });

    const allowed = saveSavedView(
      searchDraft({ name: 'With query', includeQuery: true, query: 'secret term' }),
      storage
    );
    expect(allowed.ok).toBe(true);
    const view = listSavedViews('case-1', storage).views.find((entry) => entry.name === 'With query');
    expect(view).toMatchObject({ includeQuery: true, q: 'secret term' });
  });

  it('stores claim query text only in filters.claimQuery with consent', () => {
    const storage = new MemoryStorage();
    const claimsDraft: SavedViewDraft = {
      caseId: 'case-1',
      view: 'claims',
      name: 'Confirmed needle',
      filters: { claimStatus: 'confirmed' },
      sort: 'text',
      includeQuery: true,
      query: 'needle',
    };
    const result = saveSavedView(claimsDraft, storage);
    expect(result.ok).toBe(true);

    const entry = (storedPayload(storage).views as Array<Record<string, unknown>>)[0];
    expect(entry.filters).toEqual({ claimStatus: 'confirmed', claimQuery: 'needle' });
    expect(entry.includeQuery).toBe(true);
    expect(entry).not.toHaveProperty('q');

    const denied = saveSavedView(
      { ...claimsDraft, name: 'No query', includeQuery: false },
      storage
    );
    expect(denied.ok).toBe(true);
    const deniedEntry = listSavedViews('case-1', storage).views.find((view) => view.name === 'No query');
    expect(deniedEntry?.filters).toEqual({ claimStatus: 'confirmed' });
    expect(deniedEntry?.includeQuery).toBe(false);
  });

  it('never stores query fields on an evidence view', () => {
    const storage = new MemoryStorage();
    const result = saveSavedView(
      {
        caseId: 'case-1',
        view: 'evidence',
        name: 'Evidence consent',
        filters: { publisher: 'Wire' },
        includeQuery: true,
        query: 'needle',
      },
      storage
    );
    expect(result).toMatchObject({ ok: false, reason: 'invalid-query' });
    expect(storage.getItem(SAVED_VIEWS_STORAGE_KEY)).toBeNull();

    // A hand-written evidence entry carrying a query is excluded on read.
    storage.setItem(
      SAVED_VIEWS_STORAGE_KEY,
      JSON.stringify({
        schemaVersion: 1,
        views: [
          {
            id: 'view-1',
            caseId: 'case-1',
            name: 'Bad evidence view',
            view: 'evidence',
            filters: { publisher: 'Wire' },
            includeQuery: true,
            q: 'needle',
          },
        ],
      })
    );
    const snapshot = readSavedViews(storage);
    expect(snapshot.views).toHaveLength(0);
    expect(snapshot.invalidEntries).toBe(1);
  });

  it('requires 1–256 codepoints for a consented query', () => {
    const storage = new MemoryStorage();
    expect(
      saveSavedView(searchDraft({ includeQuery: true, query: '   ' }), storage)
    ).toMatchObject({ ok: false, reason: 'invalid-query' });
    expect(
      saveSavedView(searchDraft({ includeQuery: true, query: 'x'.repeat(257) }), storage)
    ).toMatchObject({ ok: false, reason: 'invalid-query' });
  });
});

describe('saved views v1 — corrupt data and version handling', () => {
  it('handles unparseable JSON without crashing and never overwrites it', () => {
    const storage = new MemoryStorage();
    storage.setItem(SAVED_VIEWS_STORAGE_KEY, '{not json');
    const snapshot = readSavedViews(storage);
    expect(snapshot.status).toBe('corrupt');
    expect(snapshot.views).toEqual([]);

    const result = saveSavedView(searchDraft(), storage);
    expect(result).toMatchObject({ ok: false, reason: 'corrupt-data' });
    expect(result.ok ? null : result.ephemeral?.name).toBe('Evidence by publisher');
    expect(storage.raw(SAVED_VIEWS_STORAGE_KEY)).toBe('{not json');
  });

  it('refuses an unknown schema version and leaves the payload intact', () => {
    const storage = new MemoryStorage();
    const payload = JSON.stringify({ schemaVersion: 99, views: [] });
    storage.setItem(SAVED_VIEWS_STORAGE_KEY, payload);

    const snapshot = readSavedViews(storage);
    expect(snapshot.status).toBe('unsupported-version');
    expect(snapshot.storedVersion).toBe(99);
    expect(snapshot.views).toEqual([]);

    const result = saveSavedView(searchDraft(), storage);
    expect(result).toMatchObject({ ok: false, reason: 'unsupported-version' });
    expect(storage.raw(SAVED_VIEWS_STORAGE_KEY)).toBe(payload);
  });

  it('treats a payload larger than the serialized limit as corrupt', () => {
    const storage = new MemoryStorage();
    const payload = JSON.stringify({ schemaVersion: 1, views: [] }).padEnd(
      SAVED_VIEW_LIMITS.serializedMaxBytes + 1024,
      ' '
    );
    storage.setItem(SAVED_VIEWS_STORAGE_KEY, payload);
    const snapshot = readSavedViews(storage);
    expect(snapshot.status).toBe('corrupt');
    expect(snapshot.views).toEqual([]);
    expect(snapshot.bytes).toBeGreaterThan(SAVED_VIEW_LIMITS.serializedMaxBytes);
  });

  it('treats missing storage as unavailable without throwing', () => {
    expect(readSavedViews(null).status).toBe('unavailable');
    expect(saveSavedView(searchDraft(), null)).toMatchObject({
      ok: false,
      reason: 'storage-unavailable',
    });
    expect(deleteAllSavedViews(null).status).toBe('unavailable');
  });
});

describe('saved views v1 — limits', () => {
  it('enforces the per-case and per-origin limits', () => {
    const storage = new MemoryStorage();
    for (let index = 0; index < SAVED_VIEW_LIMITS.perCase; index += 1) {
      expect(saveSavedView(searchDraft({ name: `View ${index}` }), storage).ok).toBe(true);
    }
    expect(saveSavedView(searchDraft({ name: 'One too many' }), storage)).toMatchObject({
      ok: false,
      reason: 'limit-per-case',
    });

    for (let caseIndex = 1; caseIndex < 5; caseIndex += 1) {
      const caseId = `case-${caseIndex + 1}`;
      for (let index = 0; index < SAVED_VIEW_LIMITS.perCase; index += 1) {
        expect(saveSavedView(searchDraft({ caseId, name: `C${caseIndex} view ${index}` }), storage).ok).toBe(true);
      }
    }
    expect(listSavedViews('case-1', storage).views).toHaveLength(SAVED_VIEW_LIMITS.perCase);
    expect(saveSavedView(searchDraft({ caseId: 'case-6', name: 'Over origin' }), storage)).toMatchObject({
      ok: false,
      reason: 'limit-per-origin',
    });
  });

  it('validates the name length in codepoints', () => {
    const storage = new MemoryStorage();
    expect(saveSavedView(searchDraft({ name: '' }), storage)).toMatchObject({
      ok: false,
      reason: 'invalid-name',
    });
    expect(
      saveSavedView(searchDraft({ name: '😀'.repeat(SAVED_VIEW_LIMITS.nameMaxCodepoints + 1) }), storage)
    ).toMatchObject({ ok: false, reason: 'invalid-name' });
    expect(
      saveSavedView(searchDraft({ name: '😀'.repeat(SAVED_VIEW_LIMITS.nameMaxCodepoints) }), storage).ok
    ).toBe(true);
  });

  it('generates local ids that are not identities', () => {
    const first = createSavedViewId();
    const second = createSavedViewId();
    expect(first).not.toBe(second);
    expect(first).toMatch(/^view-[a-z0-9]+-[a-z0-9]+$/);
  });
});

describe('saved views v1 — quota and ephemeral fallback', () => {
  it('returns a visible session-only view when the write quota fails', () => {
    const storage = new QuotaStorage();
    const result = saveSavedView(searchDraft(), storage);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toBe('storage-unavailable');
    expect(result.message).toMatch(/session only/i);
    expect(result.ephemeral).toMatchObject({ name: 'Evidence by publisher', caseId: 'case-1' });
    expect(storage.getItem(SAVED_VIEWS_STORAGE_KEY)).toBeNull();
  });

  it('treats a throwing storage accessor as unavailable, never a crash', () => {
    const storage = new MemoryStorage();
    vi.spyOn(storage, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });
    expect(readSavedViews(storage).status).toBe('unavailable');
  });
});

describe('saved views v1 — deletes and reset', () => {
  function seed(storage: MemoryStorage): void {
    saveSavedView(searchDraft({ name: 'A one' }), storage);
    saveSavedView(searchDraft({ name: 'A two' }), storage);
    saveSavedView(searchDraft({ caseId: 'case-2', name: 'B one' }), storage);
  }

  it('deletes one view by id', () => {
    const storage = new MemoryStorage();
    seed(storage);
    const target = listSavedViews('case-1', storage).views[0];
    const snapshot = deleteSavedView(target.id, storage);
    expect(snapshot.views.map((view) => view.name)).toEqual(['A two', 'B one']);
  });

  it('deletes every view for one case and leaves other cases', () => {
    const storage = new MemoryStorage();
    seed(storage);
    const snapshot = deleteSavedViewsForCase('case-1', storage);
    expect(snapshot.views.map((view) => view.name)).toEqual(['B one']);
  });

  it('deletes all feature-owned views without touching other keys or clear()', () => {
    const storage = new MemoryStorage();
    storage.setItem('triangulate.case-view', 'keep-me');
    seed(storage);
    const clearSpy = vi.spyOn(storage, 'clear');

    const snapshot = deleteAllSavedViews(storage);
    expect(snapshot.views).toEqual([]);
    expect(storage.getItem(SAVED_VIEWS_STORAGE_KEY)).toBeNull();
    expect(storage.getItem('triangulate.case-view')).toBe('keep-me');
    expect(clearSpy).not.toHaveBeenCalled();
  });

  it('refuses to rewrite a corrupt payload when asked to delete one view', () => {
    const storage = new MemoryStorage();
    storage.setItem(SAVED_VIEWS_STORAGE_KEY, '{"schemaVersion":1,"views":[{"bad":true}]}');
    const raw = storage.raw(SAVED_VIEWS_STORAGE_KEY);
    const snapshot = deleteSavedView('view-1', storage);
    expect(snapshot.status).toBe('corrupt');
    expect(storage.raw(SAVED_VIEWS_STORAGE_KEY)).toBe(raw);
  });

  it('explicit reset removes only this namespace (never clear())', () => {
    const storage = new MemoryStorage();
    storage.setItem('other.feature', 'keep-me');
    storage.setItem(SAVED_VIEWS_STORAGE_KEY, '{broken');
    const clearSpy = vi.spyOn(storage, 'clear');
    const reset = deleteAllSavedViews(storage);
    expect(reset.status).toBe('ok');
    expect(storage.getItem(SAVED_VIEWS_STORAGE_KEY)).toBeNull();
    expect(storage.getItem('other.feature')).toBe('keep-me');
    expect(clearSpy).not.toHaveBeenCalled();
  });
});

describe('saved views v1 — cross-tab refresh', () => {
  it('notifies listeners only for this feature key', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeToSavedViews(listener);

    window.dispatchEvent(new StorageEvent('storage', { key: 'other.feature' }));
    expect(listener).not.toHaveBeenCalled();

    window.dispatchEvent(new StorageEvent('storage', { key: SAVED_VIEWS_STORAGE_KEY }));
    expect(listener).toHaveBeenCalledTimes(1);

    window.dispatchEvent(new StorageEvent('storage', { key: null }));
    expect(listener).toHaveBeenCalledTimes(2);

    unsubscribe();
    window.dispatchEvent(new StorageEvent('storage', { key: SAVED_VIEWS_STORAGE_KEY }));
    expect(listener).toHaveBeenCalledTimes(2);
  });
});

describe('saved views v1 — serialization and summaries', () => {
  it('serializes a stable versioned payload without query fields when not consented', () => {
    const storage = new MemoryStorage();
    saveSavedView(searchDraft(), storage);
    const views = readSavedViews(storage).views;
    const serialized = serializeSavedViews(views);
    expect(JSON.parse(serialized)).toMatchObject({ schemaVersion: 1 });
    expect(serialized).not.toContain('needle');
  });

  it('summarizes a view without exposing query text', () => {
    const storage = new MemoryStorage();
    saveSavedView(searchDraft({ includeQuery: true }), storage);
    const view = listSavedViews('case-1', storage).views[0];
    const summary = describeSavedView(view);
    expect(summary).toContain('search view');
    expect(summary).toContain('publisher: Wire');
    expect(summary).toContain('includes search text');
    expect(summary).not.toContain('needle');
  });
});
