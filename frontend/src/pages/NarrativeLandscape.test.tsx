import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import NarrativeLandscape from './NarrativeLandscape';

const apiMocks = vi.hoisted(() => ({
  getClaimsOverviewForCase: vi.fn(),
  getPartiesForCase: vi.fn(),
  getTimelineForCase: vi.fn(),
}));

vi.mock('../services/api', () => apiMocks);

const claim = (id: string, text: string, clusterId: string | null) => ({
  id,
  text,
  verificationStatus: 'confirmed' as const,
  type: 'fact' as const,
  controversyScore: null,
  supportCount: 1,
  opposeCount: 0,
  sourceDiversityCount: 1,
  claimSignature: id,
  narrativeClusterId: clusterId,
  evidence: [],
});

function renderNarrativeAt(entry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/cases/:id/narratives" element={<NarrativeLandscape />} />
          <Route path="/narratives" element={<NarrativeLandscape />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const renderNarrative = () => renderNarrativeAt('/cases/case-1/narratives');

describe('NarrativeLandscape truthful states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getPartiesForCase.mockResolvedValue([]);
    apiMocks.getTimelineForCase.mockResolvedValue([]);
  });

  it('never invents keyword clusters or sentiment when none are persisted', async () => {
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({
      claims: [claim('c1', 'The strike began on Monday', null)],
      narratives: [],
    });
    renderNarrative();

    expect(await screen.findByText(/No narrative clusters have been persisted/i)).toBeDefined();
    expect(screen.queryByText('Origin Narrative')).toBeNull();
    expect(screen.queryByText('Response Narrative')).toBeNull();
    expect(screen.queryByText('Impact Narrative')).toBeNull();
    expect(screen.getByText(/This read API provides no sentiment field/i)).toBeDefined();
    expect(screen.queryByText(/Overall Sentiment/i)).toBeNull();
    expect(screen.queryByText(/Cluster Sentinel/i)).toBeNull();
  });

  it('renders persisted narratives with their persisted counts', async () => {
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({
      claims: [claim('c1', 'Claim one', 'cluster-a')],
      narratives: [
        { id: 'n1', clusterId: 'cluster-a', stanceSummary: 'Persisted stance summary', sourceCount: 3, claimCount: 1 },
      ],
    });
    renderNarrative();

    const button = await screen.findByRole('button', { name: /Persisted stance summary/i });
    expect(button.textContent).toContain('1 claims');
    expect(button.textContent).toContain('3 linked sources');
    expect(button.getAttribute('aria-pressed')).toBe('false');

    fireEvent.click(button);
    expect(button.getAttribute('aria-pressed')).toBe('true');
    expect(button.getAttribute('aria-expanded')).toBe('true');

    // The recorded claim ID links into the existing claim/evidence inspector URL.
    const claimLink = screen.getByRole('link', { name: 'Claim one' });
    expect(claimLink.getAttribute('href')).toBe('/cases/case-1/evidence?claim=c1');
  });

  it('does not match parties to claims by name substring', async () => {
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({
      claims: [claim('c1', 'Alpha said the water rose', null)],
      narratives: [],
    });
    apiMocks.getPartiesForCase.mockResolvedValue([
      {
        id: 'p1',
        name: 'Alpha',
        aliases: [],
        description: 'Recorded party',
        overallStance: 'neutral',
        isModelInferred: true,
        associatedClaimsCount: 0,
      },
    ]);
    renderNarrative();

    expect(await screen.findByText('Alpha')).toBeDefined();
    expect(screen.getByText('Model-derived stance')).toBeDefined();
    // The substring match would have produced 1 claim / 1 support.
    expect(screen.getByText('0 associated claims')).toBeDefined();
  });

  it('shows one combined retryable error for any failing query', async () => {
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims: [], narratives: [] });
    apiMocks.getPartiesForCase.mockRejectedValueOnce(new Error('parties down'));
    renderNarrative();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('parties down');

    apiMocks.getPartiesForCase.mockResolvedValueOnce([]);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(await screen.findByText('Narrative Clusters')).toBeDefined();
  });

  it('reports unavailable sentiment instead of a verification ratio', async () => {
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims: [claim('c1', 'x', null)], narratives: [] });
    renderNarrative();

    expect(await screen.findByText('Not provided')).toBeDefined();
    expect(screen.getByText(/This read API provides no sentiment field/i)).toBeDefined();
    expect(screen.queryByText(/Overall Sentiment/i)).toBeNull();
  });
});

describe('NarrativeLandscape missing case id', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows an explicit missing-ID state and issues no queries', async () => {
    renderNarrativeAt('/narratives');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('No case ID in the route');

    // No disabled queries fabricating empty zero-value data.
    expect(apiMocks.getClaimsOverviewForCase).not.toHaveBeenCalled();
    expect(apiMocks.getPartiesForCase).not.toHaveBeenCalled();
    expect(apiMocks.getTimelineForCase).not.toHaveBeenCalled();
    expect(screen.queryByText('Persisted Narratives')).toBeNull();
    expect(screen.queryByText('Recorded Claims')).toBeNull();
    expect(screen.queryByText('No narrative clusters have been persisted')).toBeNull();
  });
});

describe('NarrativeLandscape stance basis, links and empty state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getPartiesForCase.mockResolvedValue([]);
    apiMocks.getTimelineForCase.mockResolvedValue([]);
  });

  it('shows a recorded basis for every stance and never a truth verdict', async () => {
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims: [], narratives: [] });
    apiMocks.getPartiesForCase.mockResolvedValue([
      {
        id: 'p-model',
        name: 'Model Party',
        aliases: [],
        description: 'Recorded party',
        overallStance: 'for',
        isModelInferred: true,
        associatedClaimsCount: 0,
      },
      {
        id: 'p-plain',
        name: 'Recorded Party',
        aliases: [],
        description: 'Recorded party',
        overallStance: 'against',
        isModelInferred: false,
        associatedClaimsCount: 0,
      },
    ]);

    renderNarrative();

    expect(await screen.findByText('Model Party')).toBeDefined();
    expect(screen.getByText('Model-derived stance')).toBeDefined();
    expect(screen.getByText('Recorded stance')).toBeDefined();
    // Stances stay neutral badges; no verified/true wording is rendered.
    expect(screen.queryByText(/verified/i)).toBeNull();
    expect(screen.queryByText(/human review/i)).toBeNull();
  });

  it('renders "Origin not recorded" when the stance provenance flag is missing', async () => {
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims: [], narratives: [] });
    apiMocks.getPartiesForCase.mockResolvedValue([
      {
        id: 'p-legacy',
        name: 'Legacy Party',
        aliases: [],
        description: 'Recorded party',
        overallStance: 'neutral',
        associatedClaimsCount: 0,
      },
    ]);

    renderNarrative();

    expect(await screen.findByText('Origin not recorded')).toBeDefined();
    expect(screen.getByText('Stance basis not recorded')).toBeDefined();
    expect(screen.queryByText(/human/i)).toBeNull();
  });

  it('renders the narratives-empty state distinctly from loading and network error', async () => {
    let resolveOverview: (value: { claims: unknown[]; narratives: unknown[] }) => void = () => {};
    apiMocks.getClaimsOverviewForCase.mockReturnValue(
      new Promise((resolve) => {
        resolveOverview = resolve;
      })
    );

    const { container } = renderNarrative();

    // Loading state first: no narratives-empty marker while data is pending.
    expect(await screen.findByText('Loading narrative data…')).toBeDefined();
    expect(container.querySelector('.narratives-empty')).toBeNull();
    expect(container.querySelector('[data-state="empty"]')).toBeNull();

    resolveOverview({ claims: [], narratives: [] });

    const empty = await screen.findByText(/No narrative clusters have been persisted/i);
    expect(empty).toBeDefined();
    expect(container.querySelector('.narratives-empty')).not.toBeNull();
    expect(container.querySelector('[data-state="empty"]')).not.toBeNull();
    // Empty is not a failure: no alert is rendered.
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('keeps the network error state distinct from the empty narratives state', async () => {
    apiMocks.getClaimsOverviewForCase.mockRejectedValueOnce(new Error('overview down'));

    const { container } = renderNarrative();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('overview down');
    expect(screen.queryByText(/No narrative clusters have been persisted/i)).toBeNull();
    expect(container.querySelector('.narratives-empty')).toBeNull();
    expect(container.querySelector('[data-state="empty"]')).toBeNull();
  });

  it('renders no invented claim links for a cluster whose claims carry no recorded IDs', async () => {
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({
      claims: [{ ...claim('c1', 'Claim without persisted link', 'cluster-a') }],
      narratives: [
        { id: 'n1', clusterId: 'cluster-a', stanceSummary: 'Stance A', sourceCount: 1, claimCount: 1 },
      ],
    });

    renderNarrative();

    const button = await screen.findByRole('button', { name: /Stance A/i });
    fireEvent.click(button);

    // A recorded claim links once; nothing else is invented for the cluster.
    const links = screen.getAllByRole('link').filter((a) => a.textContent === 'Claim without persisted link');
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute('href')).toBe('/cases/case-1/evidence?claim=c1');
  });
});
