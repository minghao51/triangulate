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
    expect(screen.getByText('Claim one')).toBeDefined();
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
    expect(screen.getByText('Model-inferred record')).toBeDefined();
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
