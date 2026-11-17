import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import SourceAnalysis from './SourceAnalysis';
import type { Evidence } from '../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getEvidenceForCase: vi.fn(),
}));

vi.mock('../services/api', () => apiMocks);

const evidence = (overrides: Partial<Evidence>): Evidence => ({
  id: 'ev-1',
  title: 'Title',
  originUrl: 'https://example.com/a',
  canonicalUrl: 'https://example.com/a',
  publisher: 'BBC News',
  sourceType: 'rss',
  verificationStatus: 'unknown',
  credibilityTier: null,
  requiresHumanReview: false,
  linkedClaims: [],
  verificationChecks: [],
  ...overrides,
});

function renderSources() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/cases/case-1/sources']}>
        <Routes>
          <Route path="/cases/:id/sources" element={<SourceAnalysis />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('SourceAnalysis truthful states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not derive bias, region or baseline scores from publisher names', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([
      evidence({ id: 'ev-1', publisher: 'Left Progressive Times', credibilityTier: 'high' }),
      evidence({ id: 'ev-2', publisher: 'Right Conservative Post', credibilityTier: null }),
    ]);
    renderSources();

    expect(await screen.findByText('Evidence Items')).toBeDefined();

    expect(screen.queryByText(/Left-leaning/i)).toBeNull();
    expect(screen.queryByText(/Right-leaning/i)).toBeNull();
    expect(screen.queryByText(/Source Bias/i)).toBeNull();
    expect(screen.queryByText(/Avg Credibility/i)).toBeNull();
    expect(screen.queryByText(/Verification Rate/i)).toBeNull();
    expect(screen.queryByText(/Baseline/i)).toBeNull();
    expect(screen.queryByText(/Source Diversity Analysis/i)).toBeNull();

    // Missing assessment is reported as not provided, not as a low score.
    expect(screen.getByText(/treated as not recorded\/provided, not as a low score/i)).toBeDefined();
    expect(screen.getByText('Not provided')).toBeDefined();
  });

  it('labels the total as evidence items rather than independent sources', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([
      evidence({ id: 'ev-1', canonicalUrl: 'https://example.com/same' }),
      evidence({ id: 'ev-2', canonicalUrl: 'https://example.com/same' }),
    ]);
    renderSources();

    expect(await screen.findByText('Evidence Items')).toBeDefined();
    expect(screen.queryByText('Total Sources')).toBeNull();
    expect(screen.getByText(/not a source-independence analysis/i)).toBeDefined();
    expect(screen.getByText('2 records')).toBeDefined();
  });

  it('shows a distinct empty state without zero-valued metric cards', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([]);
    renderSources();

    expect(await screen.findByText('No evidence records')).toBeDefined();
    expect(screen.queryByText('Evidence Items')).toBeNull();
    expect(screen.queryByText('0.0%')).toBeNull();
  });

  it('shows a retryable error and never fake zeros on failure', async () => {
    apiMocks.getEvidenceForCase.mockRejectedValueOnce(new Error('evidence 500'));
    renderSources();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('evidence 500');
    expect(screen.queryByText('Evidence Items')).toBeNull();

    apiMocks.getEvidenceForCase.mockResolvedValueOnce([evidence({})]);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(await screen.findByText('Evidence Items')).toBeDefined();
    expect(apiMocks.getEvidenceForCase).toHaveBeenCalledTimes(2);
  });

  it('avoids NaN/Infinity for items whose only fields are missing', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([
      evidence({ id: 'ev-1', publisher: null, credibilityTier: null, sourceType: 'rss' }),
    ]);
    renderSources();

    expect(await screen.findByText('Evidence Items')).toBeDefined();
    expect(screen.getByText(/1 evidence item\(s\) have no\s+recorded publisher/i)).toBeDefined();
    expect(screen.queryByText(/NaN|Infinity/)).toBeNull();
  });
});
