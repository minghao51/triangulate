import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import ClaimsTab from './ClaimsTab';
import { SAVED_VIEWS_STORAGE_KEY } from '../../services/saved-views';
import type { Claim, ClaimEvidenceLink } from '../../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getClaimsOverviewForCase: vi.fn(),
  getEvidenceForCase: vi.fn(),
  // The evidence inspector is mounted by the deep-link target only; unresolved
  // promises keep those unrelated queries out of these assertions.
  getClaimDetail: vi.fn(() => new Promise(() => {})),
  getEvidenceDetail: vi.fn(() => new Promise(() => {})),
  getCitationDetail: vi.fn(() => new Promise(() => {})),
  getCaptureWindow: vi.fn(() => new Promise(() => {})),
}));

vi.mock('../../services/api', () => apiMocks);

const makeLink = (overrides: Partial<ClaimEvidenceLink>): ClaimEvidenceLink => ({
  id: 'link-1',
  relation: 'reported_by',
  confidenceScore: null,
  sourceDiversityRank: null,
  title: null,
  publisher: null,
  originUrl: null,
  sourceType: null,
  ...overrides,
});

const makeClaim = (overrides: Partial<Claim>): Claim => ({
  id: 'claim-1',
  text: 'Claim text',
  verificationStatus: 'confirmed',
  type: 'fact',
  controversyScore: 0.1,
  supportCount: 1,
  opposeCount: 0,
  sourceDiversityCount: 1,
  claimSignature: 'sig-1',
  narrativeClusterId: null,
  evidence: [],
  ...overrides,
});

const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
};

function renderClaims(entry = '/cases/case-1/claims') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route
            path="/cases/:id/claims"
            element={
              <>
                <LocationProbe />
                <ClaimsTab caseId="case-1" />
              </>
            }
          />
          <Route path="/cases/:id/evidence" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { ...view, queryClient };
}

const rows = (container: HTMLElement) => Array.from(container.querySelectorAll('.claim-row'));
const pagingNote = (container: HTMLElement) => container.querySelector('.claims-paging-note');

describe('ClaimsTab loaded-dataset browse', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.removeItem(SAVED_VIEWS_STORAGE_KEY);
  });

  it('filters and sorts the loaded array without any further network call', async () => {
    const claims = [
      makeClaim({ id: 'claim-1', text: 'Alpha grid claim' }),
      makeClaim({ id: 'claim-2', text: 'Beta pipeline claim' }),
      makeClaim({ id: 'claim-3', text: 'Gamma grid claim' }),
    ];
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims, narratives: [] });
    const { container } = renderClaims();

    expect(await screen.findByText('Alpha grid claim')).toBeDefined();
    expect(rows(container)).toHaveLength(3);

    fireEvent.change(screen.getByLabelText('Filter loaded claims'), { target: { value: 'grid' } });
    expect(rows(container)).toHaveLength(2);
    expect(screen.queryByText('Beta pipeline claim')).toBeNull();

    fireEvent.change(screen.getByLabelText('Filter loaded claims'), { target: { value: 'GAMMA' } });
    expect(rows(container)).toHaveLength(1);
    expect(rows(container)[0].getAttribute('data-claim-id')).toBe('claim-3');

    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'text' } });
    expect(apiMocks.getClaimsOverviewForCase).toHaveBeenCalledTimes(1);

    // Sorting the filtered single row is stable and still does not refetch.
    fireEvent.change(screen.getByLabelText('Filter loaded claims'), { target: { value: '' } });
    const ids = rows(container).map((row) => row.getAttribute('data-claim-id'));
    expect(ids).toEqual(['claim-1', 'claim-2', 'claim-3']);
    expect(apiMocks.getClaimsOverviewForCase).toHaveBeenCalledTimes(1);
  });

  it('labels client paging over loaded results and renders at most 50 rows per page', async () => {
    const claims = Array.from({ length: 500 }, (_, index) =>
      makeClaim({ id: `claim-${String(index).padStart(3, '0')}`, text: `Loaded claim ${index}` })
    );
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims, narratives: [] });
    const { container } = renderClaims();

    expect(await screen.findByText('Loaded claim 0')).toBeDefined();
    expect(rows(container)).toHaveLength(50);

    const note = pagingNote(container);
    expect(note?.textContent).toContain('50 of 500 loaded results');
    expect(note?.textContent).toContain('page 1 of 10');
    expect(note?.textContent).toMatch(/client-side/);
    expect(note?.textContent?.toLowerCase()).not.toContain('server');

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(rows(container)[0].getAttribute('data-claim-id')).toBe('claim-050');
    expect(pagingNote(container)?.textContent).toContain('page 2 of 10');
    expect(rows(container)).toHaveLength(50);

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(pagingNote(container)?.textContent).toContain('page 4 of 10');
    expect(rows(container)).toHaveLength(50);
    expect(apiMocks.getClaimsOverviewForCase).toHaveBeenCalledTimes(1);
  });

  it('shows a recorded provenance reading on every rendered claim row', async () => {
    const claims = [
      makeClaim({ id: 'claim-legacy', text: 'Legacy claim', verificationProvenance: 'legacy_unknown' }),
      makeClaim({
        id: 'claim-model',
        text: 'Model claim',
        evidence: [makeLink({ id: 'link-model', assessmentOrigin: 'collector' })],
      }),
      makeClaim({ id: 'claim-unknown', text: 'Unattributed claim', verificationProvenance: 'unknown' }),
      makeClaim({ id: 'claim-operator', text: 'Operator claim', evidence: [makeLink({ id: 'link-op', assessmentOrigin: 'reviewer' })] }),
    ];
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims, narratives: [] });
    const { container } = renderClaims();

    expect(await screen.findByText('Legacy claim')).toBeDefined();
    const renderedRows = rows(container);
    expect(renderedRows).toHaveLength(4);

    const provenanceByRow = renderedRows.map((row) => ({
      id: row.getAttribute('data-claim-id'),
      kind: row.getAttribute('data-provenance'),
      text: row.querySelector('.claim-provenance')?.textContent,
    }));

    expect(provenanceByRow).toEqual([
      { id: 'claim-legacy', kind: 'legacy', text: 'Legacy · provenance unknown' },
      { id: 'claim-model', kind: 'model', text: 'Model-recorded assessment (collector)' },
      { id: 'claim-unknown', kind: 'unknown', text: 'Provenance unknown' },
      { id: 'claim-operator', kind: 'recorded', text: 'Assessment recorded (reviewer)' },
    ]);

    // Legacy/unknown rows never read as model-derived.
    for (const row of provenanceByRow) {
      if (row.kind === 'legacy' || row.kind === 'unknown') {
        expect(row.text?.toLowerCase()).toContain('unknown');
        expect(row.text).not.toContain('Model');
      }
    }
  });

  it('keeps a selected claim across filter changes and puts its id in the inspect URL', async () => {
    const claims = [
      makeClaim({ id: 'claim-1', text: 'Alpha grid claim' }),
      makeClaim({ id: 'claim-2', text: 'Beta grid claim' }),
    ];
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims, narratives: [] });
    const { container } = renderClaims();

    fireEvent.click(await screen.findByRole('button', { name: 'Select claim claim-2' }));
    expect(screen.getByTestId('claims-selection').textContent).toContain('claim-2');

    // Filter still shows the selection: it stays selected, same id.
    fireEvent.change(screen.getByLabelText('Filter loaded claims'), { target: { value: 'beta' } });
    expect(rows(container)).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Deselect claim claim-2' })).toBeDefined();
    expect(screen.getByTestId('claims-selection').textContent).not.toContain('not in the current filter');

    // Force a re-render through an unrelated sort change: selection survives.
    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'status' } });
    expect(screen.getByTestId('claims-selection').textContent).toContain('claim-2');

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    fireEvent.click(screen.getByRole('button', { name: 'Inspect selected claim' }));

    expect(screen.getByTestId('location').textContent).toBe('/cases/case-1/evidence?claim=claim-2');
  });

  it('keeps a hidden selection as not-in-current-filter instead of switching it', async () => {
    const claims = [
      makeClaim({ id: 'claim-1', text: 'Alpha grid claim' }),
      makeClaim({ id: 'claim-2', text: 'Beta pipeline claim' }),
    ];
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims, narratives: [] });
    const { container } = renderClaims();

    fireEvent.click(await screen.findByRole('button', { name: 'Select claim claim-2' }));
    fireEvent.change(screen.getByLabelText('Filter loaded claims'), { target: { value: 'alpha' } });

    expect(rows(container)).toHaveLength(1);
    expect(rows(container)[0].getAttribute('data-claim-id')).toBe('claim-1');
    const selection = screen.getByTestId('claims-selection');
    expect(selection.textContent).toContain('claim-2');
    expect(selection.textContent).toContain('not in the current filter');

    fireEvent.click(screen.getByRole('button', { name: 'Inspect selected claim' }));
    // The hidden selection is still the one inspected; it is never re-pointed.
    expect(screen.getByTestId('location').textContent).toBe('/cases/case-1/evidence?claim=claim-2');
  });

  it('reports an invalid explicit status filter and does not broaden the result set', async () => {
    const claims = [
      makeClaim({ id: 'claim-1', text: 'Alpha grid claim' }),
      makeClaim({ id: 'claim-2', text: 'Beta grid claim' }),
    ];
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims, narratives: [] });
    const { container } = renderClaims('/cases/case-1/claims?claimStatus=bogus&claimPage=2');

    expect(await screen.findByText('Status must be a known claim status.')).toBeDefined();
    // Nothing from the unfiltered loaded array leaks through.
    expect(rows(container)).toHaveLength(0);
    expect(screen.queryByText('Alpha grid claim')).toBeNull();
    expect(screen.queryByText('Beta grid claim')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Clear filter' }));
    expect(rows(container)).toHaveLength(2);
    expect(screen.queryByText('Status must be a known claim status.')).toBeNull();
  });
});

describe('ClaimsTab local saved views', () => {
  beforeEach(() => {
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

  it('saves and applies only allowlisted claim metadata', async () => {
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({
      claims: [
        makeClaim({ id: 'claim-1', text: 'Alpha grid claim' }),
        makeClaim({ id: 'claim-2', text: 'Beta grid claim' }),
      ],
      narratives: [],
    });
    const { container } = renderClaims();
    await screen.findByText('Alpha grid claim');

    fireEvent.change(screen.getByLabelText('Verification status'), { target: { value: 'confirmed' } });
    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'text' } });
    await saveView('Confirmed A–Z');

    const [entry] = storedViews();
    expect(entry.filters).toEqual({ claimStatus: 'confirmed' });
    expect(entry.sort).toBe('text');
    expect(entry.includeQuery).toBe(false);
    // Paging and selection ids are never stored.
    expect(entry).not.toHaveProperty('claimPage');
    expect(entry).not.toHaveProperty('claimId');
    expect(JSON.stringify(entry)).not.toContain('claim-1');

    fireEvent.change(screen.getByLabelText('Verification status'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply saved view Confirmed A–Z' }));

    await waitFor(() =>
      expect((screen.getByLabelText('Verification status') as HTMLSelectElement).value).toBe('confirmed')
    );
    expect((screen.getByLabelText('Sort') as HTMLSelectElement).value).toBe('text');
    expect(pagingNote(container)?.textContent).toContain('page 1 of');
    expect(screen.queryByTestId('claims-selection')).toBeNull();
  });

  it('stores claim filter text only after the explicit consent step', async () => {
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({
      claims: [makeClaim({ id: 'claim-1', text: 'Alpha grid claim' })],
      narratives: [],
    });
    renderClaims();
    await screen.findByText('Alpha grid claim');

    fireEvent.change(screen.getByLabelText('Filter loaded claims'), { target: { value: 'grid' } });
    fireEvent.click(screen.getByLabelText(/Store the claim filter text in this saved view/));
    await saveView('With claim text');

    const withText = storedViews().find((entry) => entry.name === 'With claim text');
    expect(withText).toMatchObject({ includeQuery: true, filters: { claimQuery: 'grid' } });
    expect(withText).not.toHaveProperty('q');

    fireEvent.change(screen.getByLabelText('Saved view name'), { target: { value: 'No claim text' } });
    // Consent is reset after each save, so this save deliberately omits the query.
    await saveView('No claim text');

    const noText = storedViews().find((entry) => entry.name === 'No claim text');
    expect(noText).toMatchObject({ includeQuery: false, filters: {} });
    expect(JSON.stringify(noText)).not.toContain('grid');
  });

  it('applies a consented claim query and resets paging to page 1', async () => {
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({
      claims: Array.from({ length: 120 }, (_, index) =>
        makeClaim({ id: `claim-${index}`, text: `Grid claim ${index}` })
      ),
      narratives: [],
    });
    const { container } = renderClaims();
    await screen.findByText('Grid claim 0');

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(pagingNote(container)?.textContent).toContain('page 2 of 3');

    fireEvent.change(screen.getByLabelText('Filter loaded claims'), { target: { value: 'grid' } });
    fireEvent.click(screen.getByLabelText(/Store the claim filter text in this saved view/));
    await saveView('Grid query');

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(pagingNote(container)?.textContent).toContain('page 2 of');

    fireEvent.change(screen.getByLabelText('Filter loaded claims'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply saved view Grid query' }));

    await waitFor(() =>
      expect((screen.getByLabelText('Filter loaded claims') as HTMLInputElement).value).toBe('grid')
    );
    expect(pagingNote(container)?.textContent).toContain('page 1 of');
  });

  it('refreshes the saved list on a storage event without touching the active form', async () => {
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({
      claims: [makeClaim({ id: 'claim-1', text: 'Alpha grid claim' })],
      narratives: [],
    });
    renderClaims();
    await screen.findByText('Alpha grid claim');

    fireEvent.change(screen.getByLabelText('Filter loaded claims'), { target: { value: 'grid' } });
    window.localStorage.setItem(
      SAVED_VIEWS_STORAGE_KEY,
      JSON.stringify({
        schemaVersion: 1,
        views: [
          {
            id: 'view-remote',
            caseId: 'case-1',
            name: 'Remote claims view',
            view: 'claims',
            filters: { claimStatus: 'confirmed' },
            includeQuery: false,
          },
        ],
      })
    );
    window.dispatchEvent(new StorageEvent('storage', { key: SAVED_VIEWS_STORAGE_KEY }));

    expect(await screen.findByText('Remote claims view')).toBeTruthy();
    expect((screen.getByLabelText('Filter loaded claims') as HTMLInputElement).value).toBe('grid');
    expect(screen.getByTestId('location').textContent).toContain('claimQuery=grid');
  });

  it('deletes every saved view for the case and then all feature-owned views', async () => {
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({
      claims: [makeClaim({ id: 'claim-1', text: 'Alpha grid claim' })],
      narratives: [],
    });
    renderClaims();
    await screen.findByText('Alpha grid claim');

    await saveView('First');
    await saveView('Second');
    expect(storedViews()).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', { name: 'Delete saved views for this case' }));
    await waitFor(() => expect(storedViews()).toHaveLength(0));
    expect(screen.queryByText('First')).toBeNull();
    expect(screen.queryByText('Second')).toBeNull();
  });
});
