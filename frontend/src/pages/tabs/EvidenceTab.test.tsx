import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import EvidenceTab from './EvidenceTab';
import { getComparisonTray, resetComparisonTray } from '../../services/comparison-tray';
import { SAVED_VIEWS_STORAGE_KEY } from '../../services/saved-views';
import type { Evidence, EvidenceVerificationCheck } from '../../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getEvidenceForCase: vi.fn(),
  getClaimsOverviewForCase: vi.fn(),
  // The evidence inspector shares the tab; unresolved promises keep its own
  // queries out of these list assertions.
  getClaimDetail: vi.fn(() => new Promise(() => {})),
  getEvidenceDetail: vi.fn(() => new Promise(() => {})),
  getCitationDetail: vi.fn(() => new Promise(() => {})),
  getCaptureWindow: vi.fn(() => new Promise(() => {})),
}));

vi.mock('../../services/api', () => apiMocks);

const makeCheck = (overrides: Partial<EvidenceVerificationCheck> = {}): EvidenceVerificationCheck => ({
  id: 'check-1',
  checkType: 'source',
  result: 'pass',
  method: null,
  notes: null,
  verifiedBy: null,
  verifiedAt: null,
  ...overrides,
});

const makeEvidence = (overrides: Partial<Evidence>): Evidence => ({
  id: 'ev-1',
  title: 'Evidence one',
  originUrl: 'https://example.com/one',
  canonicalUrl: 'https://example.com/one',
  publisher: 'Example Publisher',
  sourceType: 'rss',
  verificationStatus: 'confirmed',
  credibilityTier: 'high',
  requiresHumanReview: false,
  currentCaptureId: 'cap-1',
  linkedClaims: ['claim-1'],
  verificationChecks: [],
  ...overrides,
});

const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
};

function renderEvidence(entry = '/cases/case-1/evidence') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route
            path="/cases/:id/evidence"
            element={
              <>
                <LocationProbe />
                <EvidenceTab caseId="case-1" />
              </>
            }
          />
          <Route path="/cases/:id/claims" element={<LocationProbe />} />
          <Route path="/cases/:id/compare" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const rows = (container: HTMLElement) => Array.from(container.querySelectorAll('.evidence-card'));
const pagingNote = (container: HTMLElement) => container.querySelector('.evidence-paging-note');

describe('EvidenceTab loaded-dataset browse', () => {
  beforeEach(() => {
    resetComparisonTray();
    vi.clearAllMocks();
    window.localStorage.removeItem(SAVED_VIEWS_STORAGE_KEY);
  });

  it('filters and sorts the loaded array without any further network call', async () => {
    const evidence = [
      makeEvidence({ id: 'ev-1', title: 'Zulu source', publisher: 'Alpha Wire' }),
      makeEvidence({ id: 'ev-2', title: 'Alpha source', publisher: 'Beta Wire' }),
      makeEvidence({ id: 'ev-3', title: 'Mike source', publisher: 'Alpha Wire', currentCaptureId: null }),
    ];
    apiMocks.getEvidenceForCase.mockResolvedValue(evidence);
    const { container } = renderEvidence();

    expect(await screen.findByText('Zulu source')).toBeDefined();
    expect(rows(container)).toHaveLength(3);

    fireEvent.change(screen.getByLabelText('Publisher contains'), { target: { value: 'alpha' } });
    expect(rows(container)).toHaveLength(2);
    expect(screen.queryByText('Alpha source')).toBeNull();

    fireEvent.change(screen.getByLabelText('Capture'), { target: { value: 'no' } });
    expect(rows(container)).toHaveLength(1);
    expect(rows(container)[0].getAttribute('data-evidence-id')).toBe('ev-3');

    fireEvent.change(screen.getByLabelText('Capture'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'title' } });
    expect(rows(container).map((row) => row.getAttribute('data-evidence-id'))).toEqual(['ev-3', 'ev-1']);
    expect(apiMocks.getEvidenceForCase).toHaveBeenCalledTimes(1);
  });

  it('labels client paging over loaded results and renders at most 50 rows per page', async () => {
    const evidence = Array.from({ length: 500 }, (_, index) =>
      makeEvidence({
        id: `ev-${String(index).padStart(3, '0')}`,
        title: `Loaded evidence ${index}`,
        publisher: `Publisher ${index % 5}`,
      })
    );
    apiMocks.getEvidenceForCase.mockResolvedValue(evidence);
    const { container } = renderEvidence();

    expect(await screen.findByText('Loaded evidence 0')).toBeDefined();
    expect(rows(container)).toHaveLength(50);

    const note = pagingNote(container);
    expect(note?.textContent).toContain('50 of 500 loaded results');
    expect(note?.textContent).toContain('page 1 of 10');
    expect(note?.textContent).toMatch(/client-side/);
    expect(note?.textContent?.toLowerCase()).not.toContain('server');

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(rows(container)[0].getAttribute('data-evidence-id')).toBe('ev-050');
    expect(pagingNote(container)?.textContent).toContain('page 2 of 10');

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(rows(container)).toHaveLength(50);
    expect(apiMocks.getEvidenceForCase).toHaveBeenCalledTimes(1);
  });

  it('shows a recorded provenance reading on every rendered evidence row', async () => {
    const evidence = [
      makeEvidence({ id: 'ev-model', title: 'Model row', credibilityTier: 'high' }),
      makeEvidence({ id: 'ev-operator', title: 'Operator row', credibilityTier: 'user_supplied' }),
      makeEvidence({ id: 'ev-unknown', title: 'Unknown row', credibilityTier: 'unknown', currentCaptureId: null }),
      makeEvidence({
        id: 'ev-checks',
        title: 'Checked row',
        credibilityTier: null,
        verificationChecks: [makeCheck()],
      }),
    ];
    apiMocks.getEvidenceForCase.mockResolvedValue(evidence);
    const { container } = renderEvidence();

    expect(await screen.findByText('Model row')).toBeDefined();
    const readings = rows(container).map((row) => ({
      id: row.getAttribute('data-evidence-id'),
      kind: row.getAttribute('data-provenance'),
      text: row.querySelector('.evidence-provenance')?.textContent,
    }));

    expect(readings).toEqual([
      { id: 'ev-model', kind: 'model', text: 'Model-recorded assessment' },
      { id: 'ev-operator', kind: 'recorded', text: 'Operator-recorded assessment' },
      { id: 'ev-unknown', kind: 'unknown', text: 'Provenance unknown' },
      { id: 'ev-checks', kind: 'model', text: 'Model-recorded assessment' },
    ]);

    // The unknown row reads as unknown, never as model-derived.
    expect(readings[2].text?.toLowerCase()).toContain('unknown');
    expect(readings[2].text).not.toContain('Model');
  });

  it('keeps a selected evidence row across filters and puts its id in the inspect URL', async () => {
    const evidence = [
      makeEvidence({ id: 'ev-1', title: 'Alpha source', publisher: 'Alpha Wire' }),
      makeEvidence({ id: 'ev-2', title: 'Beta source', publisher: 'Beta Wire' }),
    ];
    apiMocks.getEvidenceForCase.mockResolvedValue(evidence);
    const { container } = renderEvidence();

    fireEvent.click(await screen.findByRole('button', { name: 'Select evidence ev-2' }));
    expect(screen.getByTestId('evidence-selection').textContent).toContain('ev-2');

    fireEvent.change(screen.getByLabelText('Publisher contains'), { target: { value: 'beta' } });
    expect(rows(container)).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Deselect evidence ev-2' })).toBeDefined();

    // Selection survives a re-render triggered by an unrelated sort change.
    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'title' } });
    expect(screen.getByTestId('evidence-selection').textContent).toContain('ev-2');

    fireEvent.click(screen.getByRole('button', { name: 'Inspect selected evidence' }));

    const location = screen.getByTestId('location').textContent ?? '';
    expect(location.startsWith('/cases/case-1/evidence?')).toBe(true);
    expect(location).toContain('evidence=ev-2');
    expect(location).toContain('capture=cap-1');
  });

  it('keeps a hidden selection as not-in-current-filter instead of switching it', async () => {
    const evidence = [
      makeEvidence({ id: 'ev-1', title: 'Alpha source', publisher: 'Alpha Wire' }),
      makeEvidence({ id: 'ev-2', title: 'Beta source', publisher: 'Beta Wire' }),
    ];
    apiMocks.getEvidenceForCase.mockResolvedValue(evidence);
    const { container } = renderEvidence();

    fireEvent.click(await screen.findByRole('button', { name: 'Select evidence ev-2' }));
    fireEvent.change(screen.getByLabelText('Publisher contains'), { target: { value: 'alpha' } });

    expect(rows(container)).toHaveLength(1);
    expect(rows(container)[0].getAttribute('data-evidence-id')).toBe('ev-1');
    const selection = screen.getByTestId('evidence-selection');
    expect(selection.textContent).toContain('ev-2');
    expect(selection.textContent).toContain('not in the current filter');

    fireEvent.click(screen.getByRole('button', { name: 'Inspect selected evidence' }));
    expect(screen.getByTestId('location').textContent).toContain('evidence=ev-2');
  });

  it('reports an invalid explicit filter with a field message and never broadens', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([
      makeEvidence({ id: 'ev-1', title: 'Alpha source' }),
      makeEvidence({ id: 'ev-2', title: 'Beta source' }),
    ]);
    const { container } = renderEvidence('/cases/case-1/evidence?hasCapture=maybe');

    expect(await screen.findByText('Has-capture must be yes or no.')).toBeDefined();
    expect(rows(container)).toHaveLength(0);
    expect(screen.queryByText('Alpha source')).toBeNull();

    // The invalid filter renders as a distinct filtered-empty state.
    const filteredEmpty = container.querySelector('[data-state="evidence-filter-empty"]');
    expect(filteredEmpty).not.toBeNull();
    expect(container.querySelector('[data-state="loading"]')).toBeNull();
    expect(container.querySelector('[data-state="network-error"]')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Clear filter' }));
    expect(rows(container)).toHaveLength(2);
    expect(screen.queryByText('Has-capture must be yes or no.')).toBeNull();
  });

  it('keeps the filtered-empty state distinct from loading, error and dataset-empty', async () => {
    let resolve: (value: Evidence[]) => void = () => {};
    apiMocks.getEvidenceForCase.mockReturnValue(
      new Promise<Evidence[]>((r) => {
        resolve = r;
      })
    );
    const { container, unmount } = renderEvidence();

    expect(container.querySelector('[data-state="loading"]')).not.toBeNull();
    expect(container.querySelector('[data-state="evidence-filter-empty"]')).toBeNull();

    resolve([makeEvidence({ id: 'ev-1', title: 'Alpha source', credibilityTier: 'high' })]);
    expect(await screen.findByText('Alpha source')).toBeDefined();
    expect(container.querySelector('[data-state="loading"]')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Low' }));
    const filteredEmpty = container.querySelector('[data-state="evidence-filter-empty"]');
    expect(filteredEmpty).not.toBeNull();
    expect(filteredEmpty?.textContent).toContain('No loaded evidence matches these filters');
    expect(screen.queryByText('Alpha source')).toBeNull();
    unmount();

    apiMocks.getEvidenceForCase.mockRejectedValue(new Error('evidence 500'));
    const failed = renderEvidence();
    expect((await screen.findByRole('alert')).textContent).toContain('evidence 500');
    expect(failed.container.querySelector('[data-state="network-error"]')).not.toBeNull();
    expect(failed.container.querySelector('[data-state="evidence-filter-empty"]')).toBeNull();
    failed.unmount();

    apiMocks.getEvidenceForCase.mockResolvedValue([]);
    const emptied = renderEvidence();
    expect(await screen.findByText(/No evidence has been recorded/)).toBeDefined();
    expect(emptied.container.querySelector('[data-state="empty"]')).not.toBeNull();
    expect(emptied.container.querySelector('[data-state="evidence-filter-empty"]')).toBeNull();
  });

  it('sorts by the recorded publication date, newest first, unknown dates last', async () => {
    const evidence = [
      makeEvidence({ id: 'ev-old', title: 'Oldest', publishedAt: '2026-03-01T00:00:00+00:00' }),
      makeEvidence({ id: 'ev-undated', title: 'Undated', publishedAt: null }),
      makeEvidence({ id: 'ev-new-b', title: 'Newest B', publishedAt: '2026-05-20T00:00:00+00:00' }),
      makeEvidence({ id: 'ev-new-a', title: 'Newest A', publishedAt: '2026-05-20T00:00:00+00:00' }),
      makeEvidence({ id: 'ev-missing', title: 'Missing', publishedAt: undefined }),
      makeEvidence({ id: 'ev-recent', title: 'Recent', publishedAt: '2026-04-02T00:00:00+00:00' }),
    ];
    apiMocks.getEvidenceForCase.mockResolvedValue(evidence);
    const { container } = renderEvidence();

    expect(await screen.findByText('Oldest')).toBeDefined();
    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'publishedAt' } });

    // Newest recorded date first; equal dates fall back to the stable entity ID;
    // a null or missing date is last (never dated by inference).
    expect(rows(container).map((row) => row.getAttribute('data-evidence-id'))).toEqual([
      'ev-new-a',
      'ev-new-b',
      'ev-recent',
      'ev-old',
      'ev-missing',
      'ev-undated',
    ]);
    expect(apiMocks.getEvidenceForCase).toHaveBeenCalledTimes(1);
  });

  it('sorts by publication date with unknown dates last and stable id tie-breaks', async () => {
    const evidence = [
      makeEvidence({ id: 'ev-3', title: 'Third' }),
      makeEvidence({ id: 'ev-1', title: 'First' }),
      makeEvidence({ id: 'ev-2', title: 'Second' }),
    ];
    apiMocks.getEvidenceForCase.mockResolvedValue(evidence);
    const { container } = renderEvidence();

    expect(await screen.findByText('Third')).toBeDefined();
    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'publishedAt' } });

    // No publication timestamp is recorded on the list payload, so every row is
    // an unknown date and the stable entity ID is the tie-break.
    expect(rows(container).map((row) => row.getAttribute('data-evidence-id'))).toEqual([
      'ev-1',
      'ev-2',
      'ev-3',
    ]);
    expect(apiMocks.getEvidenceForCase).toHaveBeenCalledTimes(1);
  });
});

describe('EvidenceTab comparison entry point', () => {
  const threeRows = () => [
    makeEvidence({ id: 'ev-1', title: 'Alpha source', publisher: 'Alpha Wire' }),
    makeEvidence({ id: 'ev-2', title: 'Beta source', publisher: 'Beta Wire' }),
    makeEvidence({ id: 'ev-3', title: 'Gamma source', publisher: 'Gamma Wire' }),
  ];

  const addSelected = async (id: string) => {
    fireEvent.click(await screen.findByRole('button', { name: `Select evidence ${id}` }));
    fireEvent.click(screen.getByRole('button', { name: /Add to comparison/ }));
  };

  beforeEach(() => {
    resetComparisonTray();
    vi.clearAllMocks();
    apiMocks.getEvidenceForCase.mockResolvedValue(threeRows());
  });

  it('adds the selected row to the comparison draft and offers the compare view', async () => {
    renderEvidence();
    await addSelected('ev-2');

    const tray = getComparisonTray('case-1', 'current');
    expect(tray.entries.map((entry) => entry.evidenceId)).toEqual(['ev-2']);
    // No capture is chosen on the list; Compare resolves and pins the default.
    expect(tray.entries[0].captureId).toBeNull();
    expect(screen.getByTestId('comparison-tray-draft').textContent).toContain(
      '1 of 2 distinct sources'
    );

    fireEvent.click(screen.getByRole('button', { name: /Open comparison/ }));
    await screen.findByTestId('location');
    expect(screen.getByTestId('location').textContent).toBe('/cases/case-1/compare');
  });

  it('refuses a third distinct source visibly and keeps the original two', async () => {
    renderEvidence();
    await addSelected('ev-1');
    await addSelected('ev-2');
    await addSelected('ev-3');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('already holds two distinct sources');
    expect(alert.textContent).toContain('Nothing was replaced');

    // The draft keeps exactly its original two entries, in order.
    expect(getComparisonTray('case-1', 'current').entries.map((e) => e.evidenceId)).toEqual([
      'ev-1',
      'ev-2',
    ]);
    expect(screen.getByTestId('comparison-tray-draft').textContent).toContain(
      '2 of 2 distinct sources'
    );
  });

  it('refuses the same evidence item again instead of adding a second capture', async () => {
    renderEvidence();
    await addSelected('ev-1');
    // Re-select the same row and try again.
    fireEvent.click(screen.getByRole('button', { name: /Add to comparison/ }));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('cannot be compared with itself');
    expect(alert.textContent).toContain('capture history');
    expect(getComparisonTray('case-1', 'current').entries).toHaveLength(1);
  });

  it('keeps the draft scoped to one case and never mixes another case', async () => {
    renderEvidence();
    await addSelected('ev-1');
    expect(getComparisonTray('case-1', 'current').entries).toHaveLength(1);

    // Another case reads an empty draft; nothing leaks across cases.
    expect(getComparisonTray('case-2', 'current').entries).toHaveLength(0);
    // A case-scoped reader never sees the case-1 notice either.
    expect(getComparisonTray('case-2', 'current').notice).toBeNull();
  });
});

describe('EvidenceTab local saved views', () => {
  beforeEach(() => {
    resetComparisonTray();
    vi.clearAllMocks();
    window.localStorage.removeItem(SAVED_VIEWS_STORAGE_KEY);
  });

  const storedViews = (): Array<Record<string, unknown>> => {
    const raw = window.localStorage.getItem(SAVED_VIEWS_STORAGE_KEY);
    return raw ? (JSON.parse(raw).views as Array<Record<string, unknown>>) : [];
  };

  const saveView = async (name: string) => {
    fireEvent.change(screen.getByLabelText('Saved view name'), { target: { value: name } });
    fireEvent.click(screen.getByRole('button', { name: 'Save current filters' }));
    await screen.findByText(new RegExp(`Saved “${name}”`));
  };

  it('saves and applies only allowlisted evidence metadata without query fields', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([
      makeEvidence({ id: 'ev-1', title: 'Alpha source', publisher: 'Alpha Wire', credibilityTier: 'high' }),
      makeEvidence({ id: 'ev-2', title: 'Beta source', publisher: 'Beta Wire', credibilityTier: 'low' }),
    ]);
    const { container } = renderEvidence();
    await screen.findByText('Alpha source');

    fireEvent.change(screen.getByLabelText('Publisher contains'), { target: { value: 'alpha' } });
    fireEvent.change(screen.getByLabelText('Capture'), { target: { value: 'yes' } });
    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'title' } });
    await saveView('Alpha captured');
    expect(rows(container)).toHaveLength(1);

    const [entry] = storedViews();
    expect(entry.filters).toEqual({ publisher: 'alpha', hasCapture: 'yes' });
    expect(entry.sort).toBe('title');
    expect(entry.includeQuery).toBe(false);
    // Evidence views store neither query field and no paging.
    expect(entry).not.toHaveProperty('q');
    expect(JSON.stringify(entry)).not.toContain('claimQuery');
    expect(entry).not.toHaveProperty('evidencePage');
    expect(screen.queryByLabelText(/Store the .* in this saved view/)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    await waitFor(() => expect(rows(container)).toHaveLength(2));

    fireEvent.click(screen.getByRole('button', { name: 'Apply saved view Alpha captured' }));
    await waitFor(() =>
      expect((screen.getByLabelText('Publisher contains') as HTMLInputElement).value).toBe('alpha')
    );
    expect((screen.getByLabelText('Capture') as HTMLSelectElement).value).toBe('yes');
    expect((screen.getByLabelText('Sort') as HTMLSelectElement).value).toBe('title');
    expect(rows(container)).toHaveLength(1);
    expect(screen.queryByTestId('evidence-selection')).toBeNull();
    // Applying a saved view never refetches the case.
    expect(apiMocks.getEvidenceForCase).toHaveBeenCalledTimes(1);
  });

  it('creates no evidence query-consent option at all', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([makeEvidence({ id: 'ev-1', title: 'Alpha source' })]);
    renderEvidence();
    await screen.findByText('Alpha source');
    expect(screen.getByRole('button', { name: 'Save current filters' })).toBeTruthy();
    expect(screen.queryByRole('checkbox')).toBeNull();
  });

  it('deletes one saved view from the filter bar', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([makeEvidence({ id: 'ev-1', title: 'Alpha source' })]);
    renderEvidence();
    await screen.findByText('Alpha source');

    await saveView('Delete me');
    expect(storedViews()).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'Delete saved view Delete me' }));
    await waitFor(() => expect(storedViews()).toHaveLength(0));
    expect(screen.queryByText('Delete me')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// R02 — a pinned observation is a destination, not a filter on live rows
// ---------------------------------------------------------------------------

const pinnedSource = {
  id: 'ev-pinned',
  eventId: null,
  caseArticleId: null,
  evidenceType: 'article' as const,
  sourceType: 'rss',
  title: 'Pinned source',
  publisher: 'Example Publisher',
  originUrl: 'https://example.com/original',
  canonicalUrl: 'https://example.com/canonical',
  publishedAt: '2026-10-01T12:00:00Z',
  verificationStatus: 'unknown' as const,
  credibilityTier: null,
  requiresHumanReview: false,
  captureMetadata: {},
};

const pinnedDetail = {
  ...pinnedSource,
  currentCaptureId: null,
  captures: [],
  relatedClaims: [],
};

describe('EvidenceTab pinned observation (R02)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    resetComparisonTray();
    apiMocks.getEvidenceForCase.mockResolvedValue([makeEvidence({ id: 'ev-1' })]);
    apiMocks.getEvidenceDetail.mockResolvedValue(pinnedDetail);
  });

  it('renders the pinned observation instead of the current gallery', async () => {
    renderEvidence('/cases/case-1/evidence?snapshot=snap-1&evidence=ev-pinned');

    expect(await screen.findByText('Historical evidence view')).toBeDefined();
    await waitFor(() =>
      expect(apiMocks.getEvidenceDetail).toHaveBeenCalledWith('case-1', 'ev-pinned', 'snap-1')
    );
    // The live gallery and its selection affordances are not mounted at all.
    expect(apiMocks.getEvidenceForCase).not.toHaveBeenCalled();
    expect(screen.queryByText(/Evidence Gallery/)).toBeNull();
    expect(screen.queryByText('Saved evidence views')).toBeNull();
  });

  it('offers an explicit current escape that keeps the pinned selection', async () => {
    renderEvidence('/cases/case-1/evidence?snapshot=snap-1&evidence=ev-pinned');

    const escape = await screen.findByRole('link', { name: 'Open current Evidence' });
    expect(escape.getAttribute('href')).toBe('/cases/case-1/evidence?evidence=ev-pinned');

    fireEvent.click(escape);
    await waitFor(() => expect(apiMocks.getEvidenceForCase).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId('location').textContent).toBe(
      '/cases/case-1/evidence?evidence=ev-pinned'
    );
  });

  it('shows the historical context without substituting live rows when nothing is selected', async () => {
    renderEvidence('/cases/case-1/evidence?snapshot=snap-1');

    expect(await screen.findByText('Historical evidence view')).toBeDefined();
    expect(screen.getByText(/No claim or evidence item is selected/)).toBeDefined();
    await waitFor(() => expect(apiMocks.getEvidenceForCase).not.toHaveBeenCalled());
    expect(apiMocks.getEvidenceDetail).not.toHaveBeenCalled();
    expect(screen.getByRole('link', { name: 'Open current Evidence' }).getAttribute('href')).toBe(
      '/cases/case-1/evidence'
    );
  });
});
