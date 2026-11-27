import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { CorroborationNetwork } from './CorroborationNetwork';
import type { Claim, Evidence, Party } from '../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getClaimsForCase: vi.fn(),
  getEvidenceForCase: vi.fn(),
  getPartiesForCase: vi.fn(),
}));

vi.mock('../services/api', () => apiMocks);

// React Flow needs a real layout engine; the page's error/empty/stance/link
// states are what this suite verifies, so the graph itself is a visible stub
// that fires the real click callback with the stable entity IDs only.
vi.mock('../components/data-visualization/NetworkGraph', () => ({
  NetworkGraph: ({
    claims,
    evidence,
    parties,
    onNodeClick,
  }: {
    claims: Claim[];
    evidence: Evidence[];
    parties: Party[];
    onNodeClick?: (nodeId: string, nodeType: 'claim' | 'evidence' | 'party') => void;
  }) => (
    <div>
      Network graph rendered
      {claims.map((claim) => (
        <button key={`claim-${claim.id}`} onClick={() => onNodeClick?.(claim.id, 'claim')}>
          {`node claim ${claim.id}`}
        </button>
      ))}
      {evidence.map((item) => (
        <button key={`evidence-${item.id}`} onClick={() => onNodeClick?.(item.id, 'evidence')}>
          {`node evidence ${item.id}`}
        </button>
      ))}
      {parties.map((party) => (
        <button key={`party-${party.id}`} onClick={() => onNodeClick?.(party.id, 'party')}>
          {`node party ${party.id}`}
        </button>
      ))}
    </div>
  ),
}));

const makeClaim = (id: string): Claim => ({
  id,
  text: 'Recorded claim text',
  verificationStatus: 'confirmed',
  type: 'fact',
  controversyScore: null,
  supportCount: 1,
  opposeCount: 0,
  sourceDiversityCount: 1,
  claimSignature: id,
  narrativeClusterId: null,
  evidence: [],
});

const makeEvidence = (id: string): Evidence => ({
  id,
  title: 'Recorded evidence',
  originUrl: 'https://example.com',
  canonicalUrl: 'https://example.com',
  publisher: 'Example News',
  sourceType: 'rss',
  verificationStatus: 'confirmed',
  credibilityTier: 'high',
  requiresHumanReview: false,
  linkedClaims: ['claim-1'],
  verificationChecks: [],
});

function renderNetwork() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/cases/case-1/network']}>
        <Routes>
          <Route path="/cases/:id/network" element={<CorroborationNetwork />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const emptySuccess = () => {
  apiMocks.getClaimsForCase.mockResolvedValue([]);
  apiMocks.getEvidenceForCase.mockResolvedValue([]);
  apiMocks.getPartiesForCase.mockResolvedValue([]);
};

describe('CorroborationNetwork unavailable and empty states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows an accessible unavailable state and hides metrics when every read fails', async () => {
    apiMocks.getClaimsForCase.mockRejectedValue(new Error('claims down'));
    apiMocks.getEvidenceForCase.mockRejectedValue(new Error('evidence down'));
    apiMocks.getPartiesForCase.mockRejectedValue(new Error('parties down'));

    renderNetwork();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Network data is unavailable');
    expect(alert.textContent).toContain('claims down');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeDefined();

    // No complete-looking counters or graph on top of a failed read.
    expect(screen.queryByText('Claims')).toBeNull();
    expect(screen.queryByText('Connections')).toBeNull();
    expect(screen.queryByText('Network graph rendered')).toBeNull();
  });

  it('does not present complete metrics when only one read fails', async () => {
    apiMocks.getClaimsForCase.mockResolvedValue([makeClaim('claim-1')]);
    apiMocks.getEvidenceForCase.mockRejectedValue(new Error('evidence read failed'));
    apiMocks.getPartiesForCase.mockResolvedValue([]);

    renderNetwork();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Network data is unavailable');
    expect(alert.textContent).toContain('evidence read failed');
    expect(screen.queryByText('Claims')).toBeNull();
    expect(screen.queryByText('Connections')).toBeNull();
  });

  it('distinguishes a successful empty response from a failure', async () => {
    emptySuccess();

    renderNetwork();

    expect(
      await screen.findByText('No claims, evidence or parties have been recorded for this case.')
    ).toBeDefined();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByText('Claims')).toBeDefined();
    expect(screen.queryByText('Network graph rendered')).toBeNull();
  });

  it('recovers from a total failure after Retry succeeds', async () => {
    apiMocks.getClaimsForCase.mockRejectedValueOnce(new Error('claims down'));
    apiMocks.getEvidenceForCase.mockRejectedValueOnce(new Error('evidence down'));
    apiMocks.getPartiesForCase.mockRejectedValueOnce(new Error('parties down'));

    renderNetwork();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Network data is unavailable');

    apiMocks.getClaimsForCase.mockResolvedValue([makeClaim('claim-1')]);
    apiMocks.getEvidenceForCase.mockResolvedValue([makeEvidence('evidence-1')]);
    apiMocks.getPartiesForCase.mockResolvedValue([]);

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(await screen.findByText('Network graph rendered')).toBeDefined();
    expect(screen.getByText('Claims')).toBeDefined();
    expect(screen.getByText('Connections')).toBeDefined();
  });
});

describe('CorroborationNetwork reading rule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('states next to the legend that graph shape proves nothing', async () => {
    emptySuccess();

    renderNetwork();
    await screen.findByText('No claims, evidence or parties have been recorded for this case.');

    expect(screen.getByText('Legend')).toBeDefined();
    const caveat = screen.getByRole('note');
    expect(caveat.textContent).toContain('A shared edge is not independent proof');
    expect(caveat.textContent).toMatch(
      /graph shape alone supports no independence or completion claim/i
    );
    // A reading rule, not a dismissible banner.
    expect(screen.queryByRole('button', { name: /dismiss|close|hide/i })).toBeNull();
  });

  it('keeps the reading rule visible alongside a populated network', async () => {
    apiMocks.getClaimsForCase.mockResolvedValue([makeClaim('claim-1')]);
    apiMocks.getEvidenceForCase.mockResolvedValue([makeEvidence('evidence-1')]);
    apiMocks.getPartiesForCase.mockResolvedValue([makeParty('party-1')]);

    renderNetwork();
    await screen.findByText('Network graph rendered');

    expect(screen.getByRole('note').textContent).toContain(
      'Graph shape alone supports no independence or completion claim'
    );
    // The rule never doubles as a corroboration verdict.
    expect(screen.queryByText(/corroborated|verified/i)).toBeNull();
  });
});

const makeParty = (id: string, overrides: Partial<Party> = {}): Party => ({
  id,
  name: `Party ${id}`,
  aliases: [],
  description: 'Recorded party',
  overallStance: 'neutral',
  isModelInferred: false,
  associatedClaimsCount: 1,
  investigationData: null,
  claimsSupported: 1,
  claimsContested: 0,
  ...overrides,
});

describe('CorroborationNetwork linked exploration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the recorded stance basis, and "Origin not recorded" when the flag is missing', async () => {
    apiMocks.getClaimsForCase.mockResolvedValue([]);
    apiMocks.getEvidenceForCase.mockResolvedValue([]);
    apiMocks.getPartiesForCase.mockResolvedValue([
      makeParty('model', { isModelInferred: true }),
      makeParty('legacy', { isModelInferred: undefined as unknown as boolean }),
    ]);

    renderNetwork();

    fireEvent.click(await screen.findByRole('button', { name: 'node party model' }));
    expect(await screen.findByText('Model-derived stance')).toBeDefined();

    // Stance basis is provenance, never a truth/verification verdict.
    expect(screen.queryByText(/verified/i)).toBeNull();
    expect(screen.queryByText(/human review/i)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'node party legacy' }));
    expect(await screen.findByText('Origin not recorded')).toBeDefined();
    expect(screen.getByText('Stance basis not recorded')).toBeDefined();
    expect(screen.queryByText(/human/i)).toBeNull();
  });

  it('links a selected claim into the claim and recorded evidence inspector URLs only', async () => {
    apiMocks.getClaimsForCase.mockResolvedValue([
      {
        ...makeClaim('claim-1'),
        evidence: [
          {
            id: 'evidence-1',
            relation: 'supports',
            confidenceScore: null,
            sourceDiversityRank: null,
            title: 'Recorded evidence',
            publisher: 'Example News',
            originUrl: null,
            sourceType: 'rss',
          },
        ],
      },
      makeClaim('claim-empty'),
    ]);
    apiMocks.getEvidenceForCase.mockResolvedValue([]);
    apiMocks.getPartiesForCase.mockResolvedValue([]);

    renderNetwork();

    fireEvent.click(await screen.findByRole('button', { name: 'node claim claim-1' }));

    const claimLink = await screen.findByRole('link', { name: 'Open claim in the evidence inspector' });
    expect(claimLink.getAttribute('href')).toBe('/cases/case-1/evidence?claim=claim-1');
    const evidenceLink = screen.getByRole('link', { name: 'Link evidence-1' });
    expect(evidenceLink.getAttribute('href')).toBe('/cases/case-1/evidence?evidence=evidence-1');

    // A claim with no recorded evidence links renders no invented ones.
    fireEvent.click(screen.getByRole('button', { name: 'node claim claim-empty' }));
    expect(
      await screen.findByText('No evidence links are recorded for this claim.')
    ).toBeDefined();
    expect(screen.queryByRole('link', { name: /^Link evidence-/ })).toBeNull();
  });

  it('links a selected evidence record to the inspector and only its recorded claim IDs', async () => {
    apiMocks.getClaimsForCase.mockResolvedValue([]);
    apiMocks.getEvidenceForCase.mockResolvedValue([
      { ...makeEvidence('evidence-1'), linkedClaims: ['claim-1', 'claim-2'] },
      { ...makeEvidence('evidence-2'), linkedClaims: [] },
    ]);
    apiMocks.getPartiesForCase.mockResolvedValue([]);

    renderNetwork();

    fireEvent.click(await screen.findByRole('button', { name: 'node evidence evidence-1' }));

    const evidenceLink = await screen.findByRole('link', { name: 'Open evidence in the inspector' });
    expect(evidenceLink.getAttribute('href')).toBe('/cases/case-1/evidence?evidence=evidence-1');
    expect(screen.getByRole('link', { name: 'Claim claim-1' }).getAttribute('href')).toBe(
      '/cases/case-1/evidence?claim=claim-1'
    );
    expect(screen.getByRole('link', { name: 'Claim claim-2' }).getAttribute('href')).toBe(
      '/cases/case-1/evidence?claim=claim-2'
    );

    fireEvent.click(screen.getByRole('button', { name: 'node evidence evidence-2' }));
    expect(
      await screen.findByText('No claim links are recorded for this evidence.')
    ).toBeDefined();
    expect(screen.queryByRole('link', { name: /^Claim / })).toBeNull();
  });
});
