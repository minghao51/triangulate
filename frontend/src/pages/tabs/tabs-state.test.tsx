import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Link, MemoryRouter, Route, Routes, useLocation, useParams } from 'react-router-dom';

import ClaimsTab from './ClaimsTab';
import EvidenceTab from './EvidenceTab';
import type { Claim, Evidence } from '../../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getClaimsOverviewForCase: vi.fn(),
  getEvidenceForCase: vi.fn(),
}));

vi.mock('../../services/api', () => apiMocks);

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

const makeEvidence = (overrides: Partial<Evidence>): Evidence => ({
  id: 'ev-1',
  title: 'Evidence one',
  originUrl: 'https://example.com/one',
  canonicalUrl: 'https://example.com/one',
  publisher: 'Example',
  sourceType: 'rss',
  verificationStatus: 'confirmed',
  credibilityTier: 'high',
  requiresHumanReview: false,
  linkedClaims: ['claim-1'],
  verificationChecks: [],
  ...overrides,
});

function renderAt(ui: React.ReactNode, entry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/cases/:id/claims" element={ui} />
          <Route path="/cases/:id/evidence" element={<EvidenceRoute />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const ClaimsRoute = () => {
  const { id } = useParams<{ id: string }>();
  return (
    <>
      <Link to="/cases/case-b/claims">to-b</Link>
      <ClaimsTab caseId={id!} />
    </>
  );
};

const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
};

const EvidenceRoute = () => {
  const { id } = useParams<{ id: string }>();
  return (
    <>
      <Link to="/cases/case-b/evidence">to-b</Link>
      <LocationProbe />
      <EvidenceTab caseId={id ?? 'case-1'} />
    </>
  );
};

describe('ClaimsTab case-scoped states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a loading state, then a distinct empty state', async () => {
    let resolve: (value: unknown) => void = () => {};
    apiMocks.getClaimsOverviewForCase.mockReturnValue(
      new Promise((r) => {
        resolve = r;
      })
    );
    renderAt(<ClaimsTab caseId="case-1" />, '/cases/case-1/claims');

    expect(screen.getByRole('status').textContent).toContain('Loading claims');
    expect(screen.queryByText(/No claims have been recorded/)).toBeNull();

    resolve({ claims: [], narratives: [] });
    expect(await screen.findByText(/No claims have been recorded/)).toBeDefined();
  });

  it('shows a retryable error that clears on retry', async () => {
    apiMocks.getClaimsOverviewForCase.mockRejectedValueOnce(new Error('claims 500'));
    renderAt(<ClaimsTab caseId="case-1" />, '/cases/case-1/claims');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('claims 500');

    apiMocks.getClaimsOverviewForCase.mockResolvedValueOnce({ claims: [makeClaim({})], narratives: [] });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(await screen.findByText('Claim text')).toBeDefined();
    expect(apiMocks.getClaimsOverviewForCase).toHaveBeenCalledTimes(2);
  });

  it('encodes the claim id in the evidence deep link', async () => {
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({
      claims: [makeClaim({ id: 'claim/with space&x' })],
      narratives: [],
    });
    apiMocks.getEvidenceForCase.mockResolvedValue([]);
    renderAt(<ClaimsTab caseId="case-1" />, '/cases/case-1/claims');

    fireEvent.click(await screen.findByRole('button', { name: 'Inspect Evidence' }));

    expect(await screen.findByTestId('location')).toBeDefined();
    expect(screen.getByTestId('location').textContent).toBe(
      '/cases/case-1/evidence?claim=claim%2Fwith%20space%26x'
    );
  });

  it('exposes narrative expansion state through aria-expanded', async () => {
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({
      claims: [makeClaim({ narrativeClusterId: 'c-1' })],
      narratives: [
        { id: 'n-1', clusterId: 'c-1', stanceSummary: 'Cluster summary', sourceCount: 2, claimCount: 1 },
      ],
    });
    renderAt(<ClaimsTab caseId="case-1" />, '/cases/case-1/claims');

    const toggle = await screen.findByRole('button', { name: /Cluster summary/i });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
  });
});

describe('EvidenceTab case-scoped states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('keeps the URL claim filter working and reports an unlinked filter', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([
      makeEvidence({ id: 'ev-1', title: 'Linked evidence', linkedClaims: ['claim-1'] }),
      makeEvidence({ id: 'ev-2', title: 'Unlinked evidence', linkedClaims: ['other'] }),
    ]);
    renderAt(<EvidenceTab caseId="case-1" />, '/cases/case-1/evidence?claim=claim-1');

    expect(await screen.findByText('Linked evidence')).toBeDefined();
    expect(screen.queryByText('Unlinked evidence')).toBeNull();
    expect(screen.getByText(/Filtered to evidence linked to claim/i)).toBeDefined();
  });

  it('reports a claim filter that matches no evidence instead of showing everything', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([makeEvidence({ linkedClaims: [] })]);
    renderAt(<EvidenceTab caseId="case-1" />, '/cases/case-1/evidence?claim=missing');

    expect(await screen.findByText(/No recorded evidence links to this claim/)).toBeDefined();
    expect(screen.getByText('Evidence Gallery (0)')).toBeDefined();
  });

  it('shows a distinct empty state without claiming success', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([]);
    renderAt(<EvidenceTab caseId="case-1" />, '/cases/case-1/evidence');

    expect(await screen.findByText(/No evidence has been recorded/)).toBeDefined();
  });

  it('shows a retryable error and clears it after a successful retry', async () => {
    apiMocks.getEvidenceForCase.mockRejectedValueOnce(new Error('evidence 500'));
    renderAt(<EvidenceTab caseId="case-1" />, '/cases/case-1/evidence');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('evidence 500');
    expect(screen.queryByText(/No evidence has been recorded/)).toBeNull();

    apiMocks.getEvidenceForCase.mockResolvedValueOnce([makeEvidence({ title: 'Recovered' })]);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(await screen.findByText('Recovered')).toBeDefined();
  });

  it('marks the active credibility filter with aria-pressed', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([makeEvidence({})]);
    renderAt(<EvidenceTab caseId="case-1" />, '/cases/case-1/evidence');

    const highButton = await screen.findByRole('button', { name: 'High' });
    expect(highButton.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(highButton);
    expect(highButton.getAttribute('aria-pressed')).toBe('true');
  });
});

describe('case switch races', () => {
  const Deferred = () => {
    let resolve: (value: never) => void = () => {};
    const promise = new Promise<never>((r) => {
      resolve = r as (value: never) => void;
    });
    return { promise, resolve: (value: unknown) => resolve(value as never) };
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('keeps case B claims when a late case A response arrives', async () => {
    const deferredA = Deferred();
    const claimB = makeClaim({ id: 'claim-b', text: 'Claim from B' });
    const claimA = makeClaim({ id: 'claim-a', text: 'Claim from A' });

    apiMocks.getClaimsOverviewForCase.mockImplementation((caseId: string) =>
      caseId === 'case-a'
        ? deferredA.promise
        : Promise.resolve({ claims: [claimB], narratives: [] })
    );

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const queryClientRef = queryClient;
    render(
      <QueryClientProvider client={queryClientRef}>
        <MemoryRouter initialEntries={['/cases/case-a/claims']}>
          <Routes>
            <Route path="/cases/:id/claims" element={<ClaimsRoute />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    fireEvent.click(screen.getByRole('link', { name: 'to-b' }));
    expect(await screen.findByText('Claim from B')).toBeDefined();

    await act(async () => {
      deferredA.resolve({ claims: [claimA], narratives: [] });
    });

    expect(screen.getByText('Claim from B')).toBeDefined();
    expect(screen.queryByText('Claim from A')).toBeNull();
  });

  it('resets an interacted case A filter and expansion when switching to case B', async () => {
    const evA = makeEvidence({
      id: 'shared-1',
      title: 'Case A low item',
      credibilityTier: 'low',
      linkedClaims: [],
      verificationChecks: [
        { id: 'check-1', checkType: 'source', result: 'pass', method: null, notes: null, verifiedBy: null, verifiedAt: null },
      ],
    });
    const evB = makeEvidence({
      id: 'shared-1',
      title: 'Case B high item',
      credibilityTier: 'high',
      linkedClaims: [],
      verificationChecks: [
        { id: 'check-1', checkType: 'source', result: 'pass', method: null, notes: null, verifiedBy: null, verifiedAt: null },
      ],
    });

    apiMocks.getEvidenceForCase.mockImplementation((caseId: string) =>
      Promise.resolve(caseId === 'case-b' ? [evB] : [evA])
    );

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/cases/case-a/evidence']}>
          <Routes>
            <Route path="/cases/:id/evidence" element={<EvidenceRoute />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    // Interact with case A: filter to Low and expand verification details.
    expect(await screen.findByText('Case A low item')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Low' }));
    expect(screen.getByRole('button', { name: 'Low' }).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: /Verification Details/ }));
    expect(screen.getByRole('button', { name: /Verification Details/ }).getAttribute('aria-expanded')).toBe('true');

    fireEvent.click(screen.getByRole('link', { name: 'to-b' }));

    // Case B starts clean: All selected, verification collapsed.
    expect(await screen.findByText('Case B high item')).toBeDefined();
    expect(screen.getByRole('button', { name: 'All' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: 'Low' }).getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByRole('button', { name: /Verification Details/ }).getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByText('Case A low item')).toBeNull();
  });

  it('keeps case B evidence and resets case A filter/expansion state', async () => {
    const deferredA = Deferred();
    const evB = makeEvidence({ id: 'ev-b', title: 'Evidence from B', credibilityTier: 'high', linkedClaims: [] });
    const evALow = makeEvidence({
      id: 'ev-a',
      title: 'Evidence from A',
      credibilityTier: 'low',
      linkedClaims: [],
      verificationChecks: [
        { id: 'check-a', checkType: 'source', result: 'pass', method: null, notes: null, verifiedBy: null, verifiedAt: null },
      ],
    });

    apiMocks.getEvidenceForCase.mockImplementation((caseId: string) =>
      caseId === 'case-a' ? deferredA.promise : Promise.resolve([evB])
    );

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/cases/case-a/evidence']}>
          <Routes>
            <Route path="/cases/:id/evidence" element={<EvidenceRoute />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    // React Query shows the new case's evidence after navigation.
    fireEvent.click(screen.getByRole('link', { name: 'to-b' }));
    expect(await screen.findByText('Evidence from B')).toBeDefined();

    // Filters/expansion are case-scoped and must start clean on case B.
    expect(screen.getByRole('button', { name: 'All' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: 'Low' }).getAttribute('aria-pressed')).toBe('false');

    await act(async () => {
      deferredA.resolve([evALow]);
    });

    expect(screen.getByText('Evidence from B')).toBeDefined();
    expect(screen.queryByText('Evidence from A')).toBeNull();
    expect(screen.getByRole('button', { name: 'All' }).getAttribute('aria-pressed')).toBe('true');
  });
});
