import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import PartiesTab from './PartiesTab';
import CaseIntelligenceCenter from '../CaseIntelligenceCenter';
import type { Party } from '../../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getPartiesForCase: vi.fn(),
  getCaseDetail: vi.fn(),
}));

vi.mock('../../services/api', () => apiMocks);

const makeParty = (id: string, overrides: Partial<Party> = {}): Party => ({
  id,
  name: `Party ${id}`,
  aliases: [],
  description: 'Recorded party description',
  overallStance: 'neutral',
  isModelInferred: false,
  associatedClaimsCount: 1,
  investigationData: null,
  claimsSupported: 1,
  claimsContested: 0,
  ...overrides,
});

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

function renderParties(caseId: string, queryClient: QueryClient = newClient()) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/cases/case-1/parties']}>
        <PartiesTab caseId={caseId} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const caseDetail = {
  case: {
    id: 'case-1',
    query: 'Example Case',
    conflictDomain: 'Energy Security',
    status: 'review ready',
    stage: 'REVIEW',
    counts: { articles: 1, events: 1, reviewItems: 1 },
    automationMode: 'safe',
    hasNewMaterial: false,
    openExceptionsCount: 0,
    lastUpdated: '2026-03-19T10:00:00Z',
    reportPath: null,
  },
  tabs: {
    claims: [],
    evidence: [],
    exceptions: [],
    parties: [],
    timeline: [],
    runHistory: [],
    narratives: [],
    report: { status: 'pending', markdownPath: null, markdownContent: null, manifestPath: null },
  },
} as const;

function renderCaseAt(initialEntry: string) {
  const queryClient = newClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/cases/:id/*" element={<CaseIntelligenceCenter />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('PartiesTab reader states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the shared loading state, then the recorded parties', async () => {
    let resolveParties: (value: Party[]) => void = () => {};
    apiMocks.getPartiesForCase.mockReturnValue(
      new Promise<Party[]>((resolve) => {
        resolveParties = resolve;
      })
    );

    const { container } = renderParties('case-1');

    expect(container.querySelector('[data-state="loading"]')?.textContent).toContain('Loading recorded data');

    await act(async () => {
      resolveParties([makeParty('a')]);
    });

    expect(await screen.findByText('Party a')).toBeDefined();
    expect(container.querySelector('[data-state]')).toBeNull();
  });

  it('renders a distinct empty state', async () => {
    apiMocks.getPartiesForCase.mockResolvedValue([]);

    const { container } = renderParties('case-1');

    expect(
      await screen.findByText('No parties have been recorded for this case yet.')
    ).toBeDefined();
    expect(container.querySelector('[data-state="empty"]')).not.toBeNull();
  });

  it('renders a retryable network error', async () => {
    apiMocks.getPartiesForCase.mockRejectedValueOnce(new Error('parties 500'));

    const { container } = renderParties('case-1');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('parties 500');
    expect(container.querySelector('[data-state="network-error"]')).not.toBeNull();

    apiMocks.getPartiesForCase.mockResolvedValueOnce([makeParty('b')]);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByText('Party b')).toBeDefined();
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
  });

  it('keeps one cache entry per case so two cases can never share results', async () => {
    apiMocks.getPartiesForCase.mockImplementation((caseId: string) =>
      Promise.resolve([makeParty(`${caseId}-only`)])
    );

    const queryClient = newClient();
    const { rerenderWith } = (() => {
      const result = renderParties('case-a', queryClient);
      return {
        rerenderWith: (id: string) =>
          result.rerender(
            <QueryClientProvider client={queryClient}>
              <PartiesTab caseId={id} />
            </QueryClientProvider>
          ),
      };
    })();

    expect(await screen.findByText('Party case-a-only')).toBeDefined();

    rerenderWith('case-b');
    expect(await screen.findByText('Party case-b-only')).toBeDefined();
    expect(screen.queryByText('Party case-a-only')).toBeNull();

    expect(queryClient.getQueryData<Party[]>(['parties', 'case-a'])?.map((p) => p.id)).toEqual([
      'case-a-only',
    ]);
    expect(queryClient.getQueryData<Party[]>(['parties', 'case-b'])?.map((p) => p.id)).toEqual([
      'case-b-only',
    ]);
  });

  it('keeps an expanded card and its focus across a background refetch', async () => {
    apiMocks.getPartiesForCase.mockResolvedValue([makeParty('a'), makeParty('b')]);

    const queryClient = newClient();
    const { container } = renderParties('case-1', queryClient);

    expect(await screen.findByText('Party a')).toBeDefined();

    const header = container.querySelectorAll('.accordion-header')[0] as HTMLElement;
    fireEvent.click(header);
    header.focus();

    const card = container.querySelectorAll('.party-card-accordion')[0] as HTMLElement;
    expect(card.className).toContain('expanded');
    expect(document.activeElement).toBe(header);

    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ['parties', 'case-1'] });
    });

    // A background refresh must not collapse the card, drop data or steal focus.
    const cardAfter = container.querySelectorAll('.party-card-accordion')[0] as HTMLElement;
    expect(cardAfter.className).toContain('expanded');
    expect(container.querySelectorAll('.accordion-content')).toHaveLength(1);
    expect(document.activeElement).toBe(header);
    expect(screen.getByText('Party b')).toBeDefined();
    expect(apiMocks.getPartiesForCase).toHaveBeenCalledTimes(2);
  });
});

describe('PartiesTab recorded stance basis and links', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the recorded basis for model-derived and recorded stances, never a truth verdict', async () => {
    apiMocks.getPartiesForCase.mockResolvedValue([
      makeParty('model', { isModelInferred: true }),
      makeParty('plain', { isModelInferred: false }),
    ]);

    const { container } = renderParties('case-1');

    expect(await screen.findByText('Model-derived stance')).toBeDefined();
    expect(await screen.findByText('Recorded stance')).toBeDefined();
    expect(
      container.querySelector('[data-party-id="model"]')?.getAttribute('data-stance-basis')
    ).toBe('model-derived');
    expect(
      container.querySelector('[data-party-id="plain"]')?.getAttribute('data-stance-basis')
    ).toBe('recorded');

    // A recorded stance is not a truth/verification verdict.
    expect(screen.queryByText(/verified/i)).toBeNull();
    expect(screen.queryByText(/^true$/i)).toBeNull();
    expect(screen.queryByText(/human review/i)).toBeNull();
  });

  it('renders "Origin not recorded" when the party provenance flag is missing', async () => {
    const legacyParty = { ...makeParty('legacy') } as Partial<Party>;
    delete (legacyParty as { isModelInferred?: boolean }).isModelInferred;
    apiMocks.getPartiesForCase.mockResolvedValue([legacyParty as Party]);

    const { container } = renderParties('case-1');

    expect(await screen.findByText('Origin not recorded')).toBeDefined();
    expect(screen.getByText('Stance basis not recorded')).toBeDefined();
    expect(
      container.querySelector('[data-party-id="legacy"]')?.getAttribute('data-stance-basis')
    ).toBe('unknown');
    // Missing provenance must not be inferred as human review or verification.
    expect(screen.queryByText(/human/i)).toBeNull();
    expect(screen.queryByText(/verified/i)).toBeNull();
  });

  it('links only claim IDs the party record actually carries', async () => {
    apiMocks.getPartiesForCase.mockResolvedValue([
      makeParty('linked', {
        investigationData: {
          claims_supported: [{ claim_id: 'claim-1', claim_text: 'Recorded claim one' }],
          claims_contested: [{ claim_id: 'claim-2' }],
          unique_claims: [{ claim_id: 'claim-1', claim_text: 'duplicate ignored' }],
        },
      }),
    ]);

    renderParties('case-1');

    const first = await screen.findByRole('link', { name: 'Recorded claim one' });
    expect(first.getAttribute('href')).toBe('/cases/case-1/evidence?claim=claim-1');

    const second = screen.getByRole('link', { name: 'Claim claim-2' });
    expect(second.getAttribute('href')).toBe('/cases/case-1/evidence?claim=claim-2');

    // Deduplicated: the same recorded claim ID never renders twice.
    expect(screen.getAllByRole('link')).toHaveLength(2);
  });

  it('invents no links when the party record has no recorded claim IDs', async () => {
    apiMocks.getPartiesForCase.mockResolvedValue([
      makeParty('no-ids', {
        investigationData: {
          claims_supported: [{ claim_text: 'Text without an id' }],
          claims_contested: [{ claim_id: '' }],
          unique_claims: 'not-a-list',
        },
      }),
      makeParty('no-data', { investigationData: null }),
    ]);

    const { container } = renderParties('case-1');

    expect(await screen.findByText('Party no-ids')).toBeDefined();
    expect(screen.getByText('Party no-data')).toBeDefined();
    expect(container.querySelectorAll('a')).toHaveLength(0);
    expect(screen.queryByText('Recorded claim links')).toBeNull();
  });
});

describe('PartiesTab current-only historical gate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getCaseDetail.mockResolvedValue(caseDetail);
  });

  it('shows "Unsupported historical view" before any parties fetch for ?snapshot=', async () => {
    renderCaseAt('/cases/case-1/parties?snapshot=snap-9');

    expect(await screen.findByText('Unsupported historical view')).toBeDefined();
    await new Promise((resolve) => setTimeout(resolve, 0));

    // The historical selector is never dropped in favour of live parties.
    expect(apiMocks.getPartiesForCase).not.toHaveBeenCalled();
    expect(screen.queryByText('Confirmed & Inferred Parties')).toBeNull();

    const openCurrent = screen.getByRole('link', { name: 'Open current Parties' });
    expect(openCurrent.getAttribute('href')).toBe('/cases/case-1/parties');
  });
});
