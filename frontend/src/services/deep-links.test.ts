import { describe, expect, it } from 'vitest';
import {
  CLAIMS_BROWSE_PARAMS,
  CASE_VIEW_ALLOWLISTS,
  EVIDENCE_BROWSE_PARAMS,
  MAX_FILTER_TEXT_LENGTH,
  SEARCH_SAVED_FILTER_KEYS,
  buildCaseTabUrl,
  buildCitationUrl,
  buildChangesUrl,
  buildComparisonUrl,
  buildClaimEvidenceUrl,
  buildInspectorUrl,
  buildReportUrl,
  buildSearchUrl,
  buildViewHref,
  buildViewSearch,
  clearCaseViewMemory,
  isHistoricalView,
  parseChangesSelection,
  parseAdHocChangesSelection,
  parseComparisonSelection,
  parseInspectorSelection,
  parseReportSelection,
  readSnapshotSelector,
  recallCaseViewHref,
  rememberCaseViewHref,
  sanitizeViewUrl,
  REPORT_PARAMS,
  searchSavedFilters,
  stripHistoricalSelector,
  toChangesSearchParams,
  toComparisonSearchParams,
  toInspectorSearchParams,
  viewFromPathSegment,
  type CaseViewId,
} from './deep-links';

describe('deep-link helpers', () => {
  it('URI-encodes every selector exactly once and preserves stable ordering', () => {
    const url = buildInspectorUrl('case/one & two', {
      claimId: 'claim/with space&x',
      evidenceId: 'ev 1',
      captureId: 'cap#2',
      citationId: 'citation?3',
      start: 40,
      length: 20000,
    });

    expect(url).toBe(
      '/cases/case%2Fone%20%26%20two/evidence?claim=claim%2Fwith%20space%26x&evidence=ev%201&capture=cap%232&citation=citation%3F3&start=40&length=20000'
    );
    expect(parseInspectorSelection(new URL(url, 'https://example.test').searchParams)).toEqual({
      claimId: 'claim/with space&x',
      evidenceId: 'ev 1',
      captureId: 'cap#2',
      citationId: 'citation?3',
      start: 40,
      length: 20000,
      snapshotId: null,
    });
  });

  it('carries a pinned snapshot selector only when one is supplied', () => {
    const url = buildInspectorUrl('case-1', {
      claimId: 'claim-1',
      snapshotId: 'snap/1',
    });
    expect(url).toBe(
      '/cases/case-1/evidence?claim=claim-1&snapshot=snap%2F1'
    );
    const parsed = parseInspectorSelection(
      new URL(url, 'https://example.test').searchParams
    );
    expect(parsed.claimId).toBe('claim-1');
    expect(parsed.snapshotId).toBe('snap/1');

    expect(toInspectorSearchParams({ snapshotId: '  ' }).toString()).toBe('');
  });

  it('keeps the legacy claim evidence link byte-identical', () => {
    expect(buildClaimEvidenceUrl('case-1', 'claim/with space&x')).toBe(
      '/cases/case-1/evidence?claim=claim%2Fwith%20space%26x'
    );
  });

  it('builds frozen citation links without requiring an evidence id', () => {
    expect(buildCitationUrl('case-1', 'cit-1')).toBe(
      '/cases/case-1/evidence?citation=cit-1'
    );
    expect(buildCaseTabUrl('case-1', 'claims')).toBe('/cases/case-1/claims');
  });

  it('parses and rejects malformed window offsets without throwing', () => {
    const parsed = parseInspectorSelection(
      new URLSearchParams('claim=%20%20&start=-1&length=0')
    );
    expect(parsed.claimId).toBeNull();
    expect(parsed.start).toBeNull();
    expect(parsed.length).toBeNull();

    const nonInteger = parseInspectorSelection(
      new URLSearchParams('start=1.5&length=abc')
    );
    expect(nonInteger.start).toBeNull();
    expect(nonInteger.length).toBeNull();
  });

  it('serialises start=0 explicitly, distinct from an absent start', () => {
    expect(toInspectorSearchParams({ start: 0 }).toString()).toBe('start=0');
    expect(toInspectorSearchParams({ start: null }).toString()).toBe('');
    expect(toInspectorSearchParams({ start: -5, length: 0 }).toString()).toBe('');
  });
});

describe('comparison deep links', () => {
  it('encodes evidence/capture selectors and the page offset', () => {
    const url = buildComparisonUrl('case/one', {
      leftId: 'ev left',
      rightId: 'ev/right',
      leftCaptureId: 'cap 1',
      rightCaptureId: 'cap#2',
      offset: 25,
    });
    expect(url).toBe(
      '/cases/case%2Fone/compare?left=ev%20left&right=ev%2Fright&leftCapture=cap%201&rightCapture=cap%232&offset=25'
    );
    const parsed = parseComparisonSelection(
      new URL(url, 'https://example.test').searchParams
    );
    expect(parsed).toEqual({
      leftId: 'ev left',
      rightId: 'ev/right',
      leftCaptureId: 'cap 1',
      rightCaptureId: 'cap#2',
      offset: 25,
      limit: null,
    });
  });

  it('rejects malformed offsets but keeps the evidence selectors', () => {
    const parsed = parseComparisonSelection(
      new URLSearchParams('left=ev-a&right=ev-b&offset=-2&limit=abc')
    );
    expect(parsed.leftId).toBe('ev-a');
    expect(parsed.rightId).toBe('ev-b');
    expect(parsed.offset).toBeNull();
    expect(parsed.limit).toBeNull();
  });

  it('serialises offset=0 explicitly and omits absent selectors', () => {
    expect(toComparisonSearchParams({ offset: 0 }).toString()).toBe('offset=0');
    expect(toComparisonSearchParams({ leftId: null, offset: null }).toString()).toBe('');
  });

  it('round-trips a tray commit that carries no capture pins yet', () => {
    // The tray commits evidence ids only; the server resolves default captures
    // later, so the builder must stay capture-free when nothing is pinned.
    const url = buildComparisonUrl('case-1', {
      leftId: 'ev-1',
      rightId: 'ev-2',
      leftCaptureId: null,
      rightCaptureId: null,
    });
    expect(url).toBe('/cases/case-1/compare?left=ev-1&right=ev-2');
    expect(
      parseComparisonSelection(new URL(url, 'https://example.test').searchParams)
    ).toEqual({
      leftId: 'ev-1',
      rightId: 'ev-2',
      leftCaptureId: null,
      rightCaptureId: null,
      offset: null,
      limit: null,
    });
  });

  it('replaces the resolved default captures with pinned ids on the same signature', () => {
    // Same builder, same call shape: only the resolved capture ids are added.
    const resolved = buildComparisonUrl('case-1', {
      leftId: 'ev-1',
      rightId: 'ev-2',
      leftCaptureId: 'cap-left',
      rightCaptureId: 'cap-right',
    });
    expect(resolved).toBe(
      '/cases/case-1/compare?left=ev-1&right=ev-2&leftCapture=cap-left&rightCapture=cap-right'
    );
    const parsed = parseComparisonSelection(
      new URL(resolved, 'https://example.test').searchParams
    );
    expect(parsed.leftCaptureId).toBe('cap-left');
    expect(parsed.rightCaptureId).toBe('cap-right');
    // The pinned selectors survive the compare-view allowlist unchanged.
    const sanitized = sanitizeViewUrl('compare', `?${new URL(resolved, 'https://example.test').search}`);
    expect(sanitized.search).toBe(
      'left=ev-1&right=ev-2&leftCapture=cap-left&rightCapture=cap-right'
    );
    expect(sanitized.dropped).toEqual([]);
  });

  it('keeps a pin on one side only when just one capture was chosen', () => {
    const url = buildComparisonUrl('case-1', {
      leftId: 'ev-1',
      rightId: 'ev-2',
      leftCaptureId: 'cap-old',
    });
    expect(url).toBe('/cases/case-1/compare?left=ev-1&right=ev-2&leftCapture=cap-old');
    expect(
      parseComparisonSelection(new URL(url, 'https://example.test').searchParams)
    ).toEqual({
      leftId: 'ev-1',
      rightId: 'ev-2',
      leftCaptureId: 'cap-old',
      rightCaptureId: null,
      offset: null,
      limit: null,
    });
  });
});

describe('changes deep links', () => {
  it('encodes the run, frozen claim, snapshot and page offset', () => {
    const url = buildChangesUrl('case/one', {
      runId: 'run 1',
      claimId: 'claim/2',
      snapshotId: 'snap 3',
      offset: 25,
    });
    expect(url).toBe(
      '/cases/case%2Fone/changes?run=run%201&claim=claim%2F2&snapshot=snap%203&offset=25'
    );
    expect(
      parseChangesSelection(new URL(url, 'https://example.test').searchParams)
    ).toEqual({
      runId: 'run 1',
      claimId: 'claim/2',
      snapshotId: 'snap 3',
      offset: 25,
      limit: null,
    });
  });

  it('omits absent selectors and rejects malformed offsets', () => {
    expect(toChangesSearchParams({ runId: 'run-1', offset: null }).toString()).toBe(
      'run=run-1'
    );
    const parsed = parseChangesSelection(
      new URLSearchParams('run=run-1&offset=-1&limit=abc')
    );
    expect(parsed.runId).toBe('run-1');
    expect(parsed.offset).toBeNull();
    expect(parsed.limit).toBeNull();
  });
});

describe('per-view URL allowlists', () => {
  it('keeps allowlisted claim keys and drops everything else', () => {
    const sanitized = sanitizeViewUrl(
      'claims',
      '?claimQuery=tariff&claimStatus=contested&claimSort=status&claimPage=2&utm_source=x&foo=bar'
    );
    expect(sanitized.search).toBe(
      'claimQuery=tariff&claimStatus=contested&claimSort=status&claimPage=2'
    );
    expect(sanitized.dropped).toEqual(['utm_source', 'foo']);
    expect(sanitized.invalid).toEqual({});
    expect(sanitized.unsupportedHistory).toBe(false);
  });

  it('omits defaults and rejects invalid values instead of carrying them', () => {
    expect(sanitizeViewUrl('claims', '?claimQuery=   ').search).toBe('');
    expect(buildViewSearch('claims', '?claimPage=0')).toBe('');

    const sanitized = sanitizeViewUrl(
      'claims',
      '?claimStatus=bogus&claimSort=date&claimPage=-1&claimQuery=ok'
    );
    expect(sanitized.search).toBe('claimQuery=ok');
    expect(Object.keys(sanitized.invalid).sort()).toEqual([
      'claimPage',
      'claimSort',
      'claimStatus',
    ]);
  });

  it('never carries raw captured prose in a filter value', () => {
    const longText = 'x'.repeat(257);
    const sanitized = sanitizeViewUrl('claims', `?claimQuery=${longText}`);
    expect(sanitized.search).toBe('');
    expect(sanitized.invalid.claimQuery).toBeDefined();
  });

  it('accepts evidence browse keys alongside inspector selection keys', () => {
    const sanitized = sanitizeViewUrl(
      'evidence',
      '?evidence=ev-1&citation=cit-1&publisher=Example&sourceType=rss&credibilityTier=high&hasCapture=yes&evidenceSort=publishedAt&evidencePage=3&junk=1'
    );
    expect(sanitized.search).toBe(
      'evidence=ev-1&citation=cit-1&publisher=Example&sourceType=rss&credibilityTier=high&hasCapture=yes&evidenceSort=publishedAt&evidencePage=3'
    );
    expect(sanitized.dropped).toEqual(['junk']);
    expect(sanitizeViewUrl('evidence', '?hasCapture=maybe').search).toBe('');
    expect(sanitizeViewUrl('evidence', '?evidenceSort=score').search).toBe('');
  });

  it('keeps search on the existing SEARCH_PARAMS allowlist only', () => {
    const sanitized = sanitizeViewUrl(
      'search',
      '?q=grid&type=claim&publisher=Example&status=confirmed&publishedFrom=2026-01-01&publishedTo=2026-02-01&offset=25&snapshot=snap-1'
    );
    expect(sanitized.search).toBe(
      'q=grid&type=claim&publisher=Example&status=confirmed&publishedFrom=2026-01-01&publishedTo=2026-02-01&offset=25'
    );
    // A historical selector is a conflict, not an unknown parameter.
    expect(sanitized.unsupportedHistory).toBe(true);
    expect(sanitized.dropped).toEqual([]);
    expect(sanitized.snapshotId).toBeNull();
  });
});

describe('historical/current boundary', () => {
  it('reports a snapshot selector on a current-only view without stripping it silently', () => {
    for (const view of ['timeline', 'parties', 'search', 'overview', 'report'] as const) {
      const sanitized = sanitizeViewUrl(view, '?snapshot=snap-1');
      expect(sanitized.unsupportedHistory).toBe(true);
      expect(sanitized.snapshotId).toBeNull();
      expect(sanitized.dropped).toEqual([]);
      expect([...sanitized.params.keys()]).not.toContain('snapshot');
    }
  });

  it('accepts snapshot selectors on the historical readers only', () => {
    // The claims list is a current-only overview reader; claim detail is frozen
    // inside the evidence view.
    expect(isHistoricalView('claims')).toBe(false);
    expect(isHistoricalView('evidence')).toBe(true);
    expect(isHistoricalView('changes')).toBe(true);
    expect(isHistoricalView('timeline')).toBe(false);

    const claims = sanitizeViewUrl('claims', '?snapshot=snap-1');
    expect(claims.unsupportedHistory).toBe(true);
    expect(claims.snapshotId).toBeNull();

    const sanitized = sanitizeViewUrl('evidence', '?claim=c-1&snapshot=snap-1');
    expect(sanitized.unsupportedHistory).toBe(false);
    expect(sanitized.snapshotId).toBe('snap-1');
    expect(sanitized.search).toBe('claim=c-1&snapshot=snap-1');
  });

  it('strips only the historical selector when asked explicitly', () => {
    const stripped = stripHistoricalSelector('?snapshot=snap-1&claimQuery=grid');
    expect(stripped.get('snapshot')).toBeNull();
    expect(stripped.get('claimQuery')).toBe('grid');
    expect(buildViewHref('case-1', 'claims', stripped)).toBe(
      '/cases/case-1/claims?claimQuery=grid'
    );
    // Everything else still goes through the view allowlist.
    expect(buildViewHref('case-1', 'timeline', '?snapshot=snap-1&from=x')).toBe(
      '/cases/case-1/timeline'
    );
  });
});

describe('view hrefs match the existing builders byte for byte', () => {
  it('keeps every existing path and query shape', () => {
    expect(buildViewHref('case-1', 'overview')).toBe('/cases/case-1');
    expect(buildViewHref('case-1', 'claims')).toBe(buildCaseTabUrl('case-1', 'claims'));
    expect(buildViewHref('case/one & two', 'evidence', '?claim=claim%2Fwith%20space%26x')).toBe(
      buildClaimEvidenceUrl('case/one & two', 'claim/with space&x')
    );
    expect(
      buildViewHref('case-1', 'compare', '?left=ev-1&right=ev-2&offset=25')
    ).toBe(buildComparisonUrl('case-1', { leftId: 'ev-1', rightId: 'ev-2', offset: 25 }));
    expect(buildViewHref('case-1', 'changes', '?run=run-1&offset=0')).toBe(
      buildChangesUrl('case-1', { runId: 'run-1', offset: 0 })
    );
    expect(buildViewHref('case-1', 'search', '?q=grid&offset=25')).toBe(
      buildSearchUrl('case-1', { q: 'grid', offset: 25 })
    );
  });

  it('maps all 16 destinations to their existing path segments', () => {
    const expected: Record<string, string> = {
      overview: '/cases/c-1',
      search: '/cases/c-1/search',
      evidence: '/cases/c-1/evidence',
      claims: '/cases/c-1/claims',
      compare: '/cases/c-1/compare',
      sources: '/cases/c-1/sources',
      parties: '/cases/c-1/parties',
      map: '/cases/c-1/map',
      timeline: '/cases/c-1/timeline',
      network: '/cases/c-1/network',
      narratives: '/cases/c-1/narratives',
      exceptions: '/cases/c-1/exceptions',
      report: '/cases/c-1/report',
      changes: '/cases/c-1/changes',
      'run-history': '/cases/c-1/run-history',
      pipeline: '/cases/c-1/pipeline',
    };
    for (const [view, href] of Object.entries(expected)) {
      expect(buildViewHref('c-1', view as CaseViewId)).toBe(href);
      expect(viewFromPathSegment(href.split('/').pop() === 'c-1' ? '' : href.split('/').pop())).toBe(
        view === 'overview' ? 'overview' : view
      );
    }
    expect(viewFromPathSegment('nope')).toBeNull();
  });
});

describe('session memory of committed view hrefs', () => {
  function memoryStorage(): Storage {
    const map = new Map<string, string>();
    return {
      get length() {
        return map.size;
      },
      clear: () => map.clear(),
      getItem: (key: string) => map.get(key) ?? null,
      key: (index: number) => [...map.keys()][index] ?? null,
      removeItem: (key: string) => void map.delete(key),
      setItem: (key: string, value: string) => void map.set(key, value),
    } as Storage;
  }

  it('remembers the last committed href per view and case', () => {
    const storage = memoryStorage();
    expect(recallCaseViewHref('case-1', 'claims', storage)).toBeNull();

    rememberCaseViewHref('case-1', 'claims', '/cases/case-1/claims?claimStatus=confirmed', storage);
    rememberCaseViewHref('case-1', 'claims', '/cases/case-1/claims?claimStatus=contested', storage);
    rememberCaseViewHref('case-1', 'evidence', '/cases/case-1/evidence?claim=c-1', storage);

    expect(recallCaseViewHref('case-1', 'claims', storage)).toBe(
      '/cases/case-1/claims?claimStatus=contested'
    );
    expect(recallCaseViewHref('case-1', 'evidence', storage)).toBe(
      '/cases/case-1/evidence?claim=c-1'
    );
    expect(recallCaseViewHref('case-2', 'claims', storage)).toBeNull();
  });

  it('ignores hrefs from another case and clears explicitly only', () => {
    const storage = memoryStorage();
    rememberCaseViewHref('case-1', 'claims', '/cases/case-2/claims', storage);
    expect(recallCaseViewHref('case-1', 'claims', storage)).toBeNull();

    rememberCaseViewHref('case-1', 'claims', '/cases/case-1/claims', storage);
    clearCaseViewMemory('case-1', storage);
    expect(recallCaseViewHref('case-1', 'claims', storage)).toBeNull();
  });
});

describe('browse-key constants match the per-view allowlists', () => {
  it('exposes exactly the allowlisted claims browse keys', () => {
    const allowed = new Set(CASE_VIEW_ALLOWLISTS.claims.map((rule) => rule.key));
    for (const key of Object.values(CLAIMS_BROWSE_PARAMS)) {
      expect(allowed.has(key)).toBe(true);
    }
    expect(Object.keys(CLAIMS_BROWSE_PARAMS).sort()).toEqual(['page', 'query', 'sort', 'status']);
  });

  it('exposes exactly the allowlisted evidence browse keys', () => {
    const allowed = new Set(CASE_VIEW_ALLOWLISTS.evidence.map((rule) => rule.key));
    for (const key of Object.values(EVIDENCE_BROWSE_PARAMS)) {
      expect(allowed.has(key)).toBe(true);
    }
    expect(Object.keys(EVIDENCE_BROWSE_PARAMS).sort()).toEqual([
      'credibilityTier',
      'hasCapture',
      'page',
      'publisher',
      'sort',
      'sourceType',
    ]);
  });
});

// F11: run history is a current-only destination. A frozen link must be gated,
// never silently reinterpreted as live data.
describe('run-history historical boundary', () => {
  it('treats run history as current-only instead of dropping the selector', () => {
    expect(isHistoricalView('run-history')).toBe(false);

    const sanitized = sanitizeViewUrl('run-history', '?snapshot=snap-1');
    expect(sanitized.unsupportedHistory).toBe(true);
    expect(sanitized.snapshotId).toBeNull();
    // A conflict is not an unknown parameter, so it is never silently dropped.
    expect(sanitized.dropped).toEqual([]);
    expect(sanitized.search).toBe('');
  });

  it('needs the explicit "Open current" strip to leave the observation', () => {
    const gated = sanitizeViewUrl('run-history', '?snapshot=snap-1&offset=25');
    expect(gated.unsupportedHistory).toBe(true);
    expect(gated.params.has('snapshot')).toBe(false);

    // Only the explicit transition removes the historical selector.
    const stripped = stripHistoricalSelector('?snapshot=snap-1&offset=25');
    expect(stripped.get('snapshot')).toBeNull();
    expect(buildViewHref('case-1', 'run-history', stripped)).toBe(
      '/cases/case-1/run-history'
    );
    // Historical readers keep their selector; the same key is never stripped there.
    expect(sanitizeViewUrl('changes', '?snapshot=snap-1').search).toBe('snapshot=snap-1');
  });
});

describe('search saved-view metadata (F10, additive)', () => {
  it('exposes only non-query, non-paging search filter keys', () => {
    expect([...SEARCH_SAVED_FILTER_KEYS]).toEqual([
      'type',
      'publisher',
      'status',
      'publishedFrom',
      'publishedTo',
    ]);
    expect(SEARCH_SAVED_FILTER_KEYS).not.toContain('q');
    expect(SEARCH_SAVED_FILTER_KEYS).not.toContain('offset');
    expect(MAX_FILTER_TEXT_LENGTH).toBe(256);
  });

  it('builds only non-empty allowlisted filters and never the query or offset', () => {
    expect(
      searchSavedFilters({
        q: 'secret search text',
        type: 'evidence',
        publisher: '  AP  ',
        status: null,
        publishedFrom: '2026-01-01T00:00:00.000Z',
        publishedTo: null,
        offset: 75,
      })
    ).toEqual({
      type: 'evidence',
      publisher: 'AP',
      publishedFrom: '2026-01-01T00:00:00.000Z',
    });
  });

  it('returns an empty object when no allowlisted filter is applied', () => {
    expect(searchSavedFilters({ q: 'only a query', offset: 25 })).toEqual({});
  });
});

// F18/X01: the ad-hoc comparison rides the existing changes route through an
// explicit browser allowlist entry; the API query names stay `baseline`/`target`.
describe('ad-hoc snapshot comparison selection', () => {
  const AD_HOC_SEARCH = 'mode=ad_hoc&baselineSnapshot=snap-1&targetSnapshot=snap-2';

  it('allowlists mode and both pinned snapshot sides on the changes route only', () => {
    const sanitized = sanitizeViewUrl('changes', `?${AD_HOC_SEARCH}&junk=1`);
    expect(sanitized.search).toBe(AD_HOC_SEARCH);
    expect(sanitized.dropped).toEqual(['junk']);
    expect(sanitized.invalid).toEqual({});
    // A pinned comparison is not a historical conflict on its own view.
    expect(sanitized.unsupportedHistory).toBe(false);

    const allowed = new Set(CASE_VIEW_ALLOWLISTS.changes.map((rule) => rule.key));
    expect(allowed.has('mode')).toBe(true);
    expect(allowed.has('baselineSnapshot')).toBe(true);
    expect(allowed.has('targetSnapshot')).toBe(true);
  });

  it('drops the ad-hoc keys on every other destination', () => {
    for (const view of [
      'overview',
      'search',
      'evidence',
      'claims',
      'compare',
      'sources',
      'parties',
      'map',
      'timeline',
      'network',
      'narratives',
      'exceptions',
      'report',
      'run-history',
      'pipeline',
    ] as const) {
      const sanitized = sanitizeViewUrl(view, `?${AD_HOC_SEARCH}`);
      expect([...sanitized.params.keys()]).not.toContain('mode');
      expect([...sanitized.params.keys()]).not.toContain('baselineSnapshot');
      expect([...sanitized.params.keys()]).not.toContain('targetSnapshot');
      expect(sanitized.search).toBe('');
      expect(sanitized.dropped).toEqual(['mode', 'baselineSnapshot', 'targetSnapshot']);
    }
  });

  it('rejects an unsupported mode value instead of carrying it', () => {
    const sanitized = sanitizeViewUrl('changes', '?mode=recorded&baselineSnapshot=snap-1');
    expect(sanitized.search).toBe('baselineSnapshot=snap-1');
    expect(sanitized.invalid.mode).toBe('Mode must be ad_hoc.');
  });

  it('round-trips both pinned snapshots through the URL byte for byte', () => {
    const url = buildChangesUrl('case-1', {
      mode: 'ad_hoc',
      baselineSnapshotId: 'snap/one',
      targetSnapshotId: 'snap two',
    });
    expect(url).toBe(
      '/cases/case-1/changes?mode=ad_hoc&baselineSnapshot=snap%2Fone&targetSnapshot=snap%20two'
    );

    const search = new URL(url, 'https://example.test').search;
    // A reload goes through the view allowlist: nothing is dropped or rewritten.
    const sanitized = sanitizeViewUrl('changes', search);
    expect(sanitized.search).toBe(
      'mode=ad_hoc&baselineSnapshot=snap%2Fone&targetSnapshot=snap%20two'
    );
    expect(sanitized.dropped).toEqual([]);
    expect(buildViewHref('case-1', 'changes', sanitized.params)).toBe(url);

    const parsed = parseAdHocChangesSelection(new URL(url, 'https://example.test').searchParams);
    expect(parsed).toEqual({
      active: true,
      mode: 'ad_hoc',
      baselineSnapshotId: 'snap/one',
      targetSnapshotId: 'snap two',
    });
    // Re-building from the parsed selectors keeps the same pinned pair.
    expect(
      buildChangesUrl('case-1', {
        mode: parsed.active ? 'ad_hoc' : null,
        baselineSnapshotId: parsed.baselineSnapshotId,
        targetSnapshotId: parsed.targetSnapshotId,
      })
    ).toBe(url);
  });

  it('never defaults a missing snapshot side or activates without the mode', () => {
    expect(
      parseAdHocChangesSelection(
        new URLSearchParams('mode=ad_hoc&baselineSnapshot=snap-1')
      )
    ).toEqual({
      active: true,
      mode: 'ad_hoc',
      baselineSnapshotId: 'snap-1',
      targetSnapshotId: null,
    });
    expect(parseAdHocChangesSelection(new URLSearchParams('baselineSnapshot=snap-1'))).toEqual({
      active: false,
      mode: null,
      baselineSnapshotId: 'snap-1',
      targetSnapshotId: null,
    });
    expect(
      parseAdHocChangesSelection(new URLSearchParams('mode=ad_hoc&baselineSnapshot=%20%20'))
    ).toMatchObject({ active: true, baselineSnapshotId: null });
    expect(parseAdHocChangesSelection(new URLSearchParams('mode=recorded'))).toMatchObject({
      active: false,
      mode: 'recorded',
    });
  });

  it('leaves the recorded changes selection untouched when the mode is absent', () => {
    expect(
      toChangesSearchParams({ runId: 'run-1', claimId: 'claim-1', snapshotId: 'snap-1', offset: 25 }).toString()
    ).toBe('run=run-1&claim=claim-1&snapshot=snap-1&offset=25');
    expect(
      toChangesSearchParams({ mode: 'ad_hoc', baselineSnapshotId: ' ', targetSnapshotId: null }).toString()
    ).toBe('mode=ad_hoc');
  });
});

// X02/F20: the report view keeps "current" as its default and adds one explicit
// browser selector for a recorded run. It is allowlisted on the report
// destination only, so no other view can be handed a run pin.
describe('report run pin (X02/F20)', () => {
  it('allowlists reportRun on the report destination only', () => {
    const sanitized = sanitizeViewUrl('report', '?reportRun=run-2&junk=1');
    expect(sanitized.search).toBe('reportRun=run-2');
    expect(sanitized.dropped).toEqual(['junk']);
    expect(sanitized.invalid).toEqual({});
    // A pinned run is not a historical-snapshot conflict on its own view.
    expect(sanitized.unsupportedHistory).toBe(false);

    const allowed = new Set(CASE_VIEW_ALLOWLISTS.report.map((rule) => rule.key));
    expect(allowed.has(REPORT_PARAMS.run)).toBe(true);
  });

  it('drops the pin on every other destination', () => {
    const views: CaseViewId[] = [
      'overview',
      'search',
      'evidence',
      'claims',
      'compare',
      'sources',
      'parties',
      'map',
      'timeline',
      'network',
      'narratives',
      'exceptions',
      'changes',
      'run-history',
      'pipeline',
    ];
    for (const view of views) {
      const sanitized = sanitizeViewUrl(view, '?reportRun=run-2');
      expect([...sanitized.params.keys()]).not.toContain(REPORT_PARAMS.run);
      expect(sanitized.search).toBe('');
      expect(sanitized.dropped).toEqual([REPORT_PARAMS.run]);
    }
  });

  it('round-trips the pinned run through the URL byte for byte', () => {
    expect(buildReportUrl('case-1', {})).toBe('/cases/case-1/report');
    expect(buildReportUrl('case-1', { runId: 'run-2' })).toBe(
      '/cases/case-1/report?reportRun=run-2'
    );
    expect(buildReportUrl('case/one & two', { runId: 'run/2 & 3' })).toBe(
      '/cases/case%2Fone%20%26%20two/report?reportRun=run%2F2%20%26%203'
    );

    const url = buildReportUrl('case-1', { runId: 'run/2 & 3' });
    const search = new URL(url, 'https://example.test').search;
    // A reload goes through the view allowlist: nothing is dropped or rewritten.
    const sanitized = sanitizeViewUrl('report', search);
    expect(sanitized.dropped).toEqual([]);
    expect(sanitized.invalid).toEqual({});
    expect(parseReportSelection(sanitized.params).runId).toBe('run/2 & 3');
    expect(buildViewHref('case-1', 'report', sanitized.params)).toBe(
      '/cases/case-1/report?reportRun=run%2F2%20%26%203'
    );
  });

  it('treats a missing or blank pin as no run and never invents one', () => {
    expect(parseReportSelection(new URLSearchParams(''))).toEqual({ runId: null });
    expect(parseReportSelection(new URLSearchParams('other=1'))).toEqual({ runId: null });
    expect(parseReportSelection(new URLSearchParams('reportRun='))).toEqual({ runId: null });
    expect(parseReportSelection(new URLSearchParams('reportRun=%20%20'))).toEqual({
      runId: null,
    });
    // The key itself stays observable so a blank pin is not silently "current".
    expect(new URLSearchParams('reportRun=').has(REPORT_PARAMS.run)).toBe(true);
    expect(sanitizeViewUrl('report', '?reportRun=%20').invalid.reportRun).toBe(
      'Unknown run selector.'
    );
  });
});

describe('explicit snapshot selector reading (R02)', () => {
  it('reports no selector when the key is absent', () => {
    expect(readSnapshotSelector('?claim=claim-1')).toEqual({
      state: 'none',
      values: [],
      snapshotId: null,
      reason: null,
    });
  });

  it('accepts one explicit observation ID, trimming only outer whitespace', () => {
    const reading = readSnapshotSelector('?snapshot=%20snap-1%20');
    expect(reading.state).toBe('valid');
    expect(reading.snapshotId).toBe('snap-1');
    expect(reading.reason).toBeNull();
  });

  it('treats identical repeated selectors as one selector', () => {
    const reading = readSnapshotSelector('?snapshot=snap-1&snapshot=snap-1');
    expect(reading.state).toBe('valid');
    expect(reading.snapshotId).toBe('snap-1');
  });

  it('reports an empty selector instead of falling back to current data', () => {
    const reading = readSnapshotSelector('?snapshot=');
    expect(reading.state).toBe('invalid');
    expect(reading.snapshotId).toBeNull();
    expect(reading.reason).toMatch(/empty/i);
    expect(readSnapshotSelector('?snapshot=%20%20').state).toBe('invalid');
  });

  it('refuses to pick a side of conflicting duplicate selectors', () => {
    const reading = readSnapshotSelector('?snapshot=snap-1&snapshot=snap-2');
    expect(reading.state).toBe('conflicting');
    expect(reading.snapshotId).toBeNull();
    expect(reading.reason).toContain('snap-1');
    expect(reading.reason).toContain('snap-2');
  });

  // R02: an explicit blank member is a contradictory selector, not something to
  // filter out before deciding — the link names an observation and its absence.
  it('reports a blank member of a repeated snapshot selector as invalid, in either order', () => {
    for (const search of ['?snapshot=&snapshot=snap-x', '?snapshot=snap-x&snapshot=']) {
      const reading = readSnapshotSelector(search);
      expect(reading.state).toBe('invalid');
      expect(reading.snapshotId).toBeNull();
      expect(reading.reason).toMatch(/no unambiguous observation/i);
    }
  });

  it('still accepts identical non-empty repeated selectors as one selector', () => {
    const reading = readSnapshotSelector('?snapshot=snap-x&snapshot=snap-x');
    expect(reading.state).toBe('valid');
    expect(reading.snapshotId).toBe('snap-x');
    expect(reading.reason).toBeNull();
  });

  it('rejects an oversized selector rather than truncating it', () => {
    const reading = readSnapshotSelector(`?snapshot=${'s'.repeat(MAX_FILTER_TEXT_LENGTH + 1)}`);
    expect(reading.state).toBe('invalid');
    expect(reading.snapshotId).toBeNull();
  });
});
