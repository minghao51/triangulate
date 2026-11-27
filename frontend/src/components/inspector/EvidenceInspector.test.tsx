import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  Link,
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useParams,
  useSearchParams,
} from 'react-router-dom';

import { EvidenceInspector } from './EvidenceInspector';
import EvidenceTab from '../../pages/tabs/EvidenceTab';
import { ApiError } from '../../services/api-error';
import type {
  AlignmentStatus,
  CaptureSummary,
  CaptureWindow,
  CitationDetail,
  ClaimDetail,
  ClaimEvidenceLink,
  Evidence,
  EvidenceClaimReference,
  EvidenceDetail,
  EvidenceSource,
} from '../../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getEvidenceForCase: vi.fn(),
  getClaimDetail: vi.fn(),
  getEvidenceDetail: vi.fn(),
  getCitationDetail: vi.fn(),
  getCaptureWindow: vi.fn(),
}));

vi.mock('../../services/api', () => apiMocks);

const source = (overrides: Partial<EvidenceSource> = {}): EvidenceSource => ({
  id: 'ev-1',
  eventId: null,
  caseArticleId: null,
  evidenceType: 'article',
  sourceType: 'rss',
  title: 'Example source',
  publisher: 'Example Publisher',
  originUrl: 'https://example.com/original',
  canonicalUrl: 'https://example.com/canonical',
  publishedAt: '2026-10-01T12:00:00Z',
  verificationStatus: 'unknown',
  credibilityTier: null,
  requiresHumanReview: false,
  captureMetadata: {},
  ...overrides,
});

const capture = (overrides: Partial<CaptureSummary> = {}): CaptureSummary => ({
  id: 'cap-1',
  evidenceId: 'ev-1',
  textSha256: 'sha-1',
  normalizedTextSha256: 'nsha-1',
  normalizationVersion: 'v1',
  captureKind: 'live',
  recordedAt: '2026-11-01T10:00:00Z',
  observedAt: '2026-11-01T09:00:00Z',
  metadata: {},
  charLength: 17,
  isCurrent: true,
  ...overrides,
});

const evidenceDetail = (overrides: Partial<EvidenceDetail> = {}): EvidenceDetail => ({
  ...source(),
  currentCaptureId: 'cap-1',
  captures: [capture()],
  relatedClaims: [],
  ...overrides,
});

const reference = (
  overrides: Partial<EvidenceClaimReference> = {}
): EvidenceClaimReference => ({
  claimId: 'claim-1',
  claimText: 'Claim text',
  claimSignature: 'sig-1',
  linkId: 'link-1',
  effectiveRelation: 'reported_by',
  relation: 'reported_by',
  alignmentStatus: 'not_provided',
  citationId: null,
  captureId: 'cap-1',
  quote: null,
  startChar: null,
  endChar: null,
  diagnosticReason: null,
  ...overrides,
});

const claimLink = (overrides: Partial<ClaimEvidenceLink> = {}): ClaimEvidenceLink => ({
  id: 'link-1',
  relation: 'reported_by',
  confidenceScore: null,
  sourceDiversityRank: null,
  title: 'Example source',
  publisher: 'Example Publisher',
  originUrl: 'https://example.com/original',
  sourceType: 'rss',
  captureId: 'cap-1',
  citationId: null,
  quote: null,
  startChar: null,
  endChar: null,
  alignmentStatus: 'not_provided',
  effectiveRelation: 'reported_by',
  assessmentOrigin: null,
  assessmentVersion: null,
  diagnosticReason: null,
  ...overrides,
});

const claimDetail = (overrides: Partial<ClaimDetail> = {}): ClaimDetail => ({
  id: 'claim-1',
  caseId: 'case-1',
  eventId: null,
  claimText: 'Claim text',
  claimSignature: 'sig-1',
  verificationStatus: 'unknown',
  verificationProvenance: 'unknown',
  type: 'fact',
  controversyScore: null,
  narrativeClusterId: null,
  partyPositions: {},
  counts: { supportCount: 0, opposeCount: 0, sourceDiversityCount: 0, evidenceCount: 1 },
  passages: [],
  ...overrides,
});

const citation = (overrides: Partial<CitationDetail> = {}): CitationDetail => ({
  id: 'cit-1',
  caseId: 'case-1',
  captureId: 'cap-1',
  evidenceId: 'ev-1',
  originalClaimId: 'claim-gone',
  claimSignature: 'sig-frozen',
  claimText: 'Frozen claim text',
  relationship: 'reported_by',
  quote: '東京 😀',
  startChar: 5,
  endChar: 9,
  alignmentStatus: 'exact',
  alignmentVersion: 'v1',
  assessmentOrigin: 'collector',
  assessmentVersion: 'v1',
  assessmentMetadata: {},
  recordedAt: '2026-11-01T10:00:00Z',
  liveClaimPresent: false,
  liveClaimId: null,
  evidence: source(),
  capture: capture(),
  ...overrides,
});

const windowFor = (
  text: string,
  start = 0,
  totalLength = Array.from(text).length,
  captureId = 'cap-1'
): CaptureWindow => ({
  captureId,
  evidenceId: 'ev-1',
  start,
  length: Array.from(text).length,
  totalLength,
  text,
  textSha256: 'sha-1',
  captureKind: 'live',
  recordedAt: '2026-11-01T10:00:00Z',
  observedAt: '2026-11-01T09:00:00Z',
  metadata: {},
});

const evidenceItem = (overrides: Partial<Evidence> = {}): Evidence => ({
  id: 'ev-1',
  title: 'Example source',
  originUrl: 'https://example.com/original',
  canonicalUrl: 'https://example.com/canonical',
  publisher: 'Example Publisher',
  sourceType: 'rss',
  verificationStatus: 'unknown',
  credibilityTier: null,
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

function withProviders(initialEntry: string, element: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route
            path="/cases/:id/evidence"
            element={
              <>
                <LocationProbe />
                {element}
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderInspector(entry: string, caseId = 'case-1') {
  return withProviders(entry, <EvidenceInspector caseId={caseId} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.getEvidenceForCase.mockResolvedValue([]);
  apiMocks.getClaimDetail.mockResolvedValue(claimDetail());
});

describe('EvidenceInspector frozen citations', () => {
  it('shows loading, then a frozen citation that survives a missing live claim', async () => {
    let resolveCitation: (value: CitationDetail) => void = () => {};
    apiMocks.getCitationDetail.mockReturnValue(
      new Promise<CitationDetail>((resolve) => {
        resolveCitation = resolve;
      })
    );
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('abcde東京 😀 tail'));

    renderInspector('/cases/case-1/evidence?citation=cit-1');

    expect(screen.getByRole('status').textContent).toContain('Loading frozen citation');
    resolveCitation(citation());

    expect(await screen.findByRole('heading', { name: 'Frozen claim text' })).toBeDefined();
    expect(screen.getByText(/current claim is no longer present/i)).toBeDefined();
    expect(
      screen.getByText('Reported by the source (not corroboration)')
    ).toBeDefined();
    // No false confirmation badge and no invented support language.
    expect(screen.queryByText('Confirmed')).toBeNull();
    expect(document.querySelector('.badge-success')).toBeNull();
  });

  it('highlights an emoji/CJK quotation using code-point offsets', async () => {
    apiMocks.getCitationDetail.mockResolvedValue(citation());
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('abcde東京 😀 tail'));

    const { container } = renderInspector('/cases/case-1/evidence?citation=cit-1');

    const mark = await waitFor(() => {
      const element = container.querySelector('mark');
      expect(element).not.toBeNull();
      return element as HTMLElement;
    });
    expect(mark.textContent).toBe('東京 😀');
    expect(mark.previousSibling?.textContent).toBe('abcde');
    expect(mark.nextSibling?.textContent).toBe(' tail');
    expect(container.querySelectorAll('mark')).toHaveLength(1);
  });

  it('focuses the selected inspector heading and keeps a native-button selector', async () => {
    apiMocks.getCitationDetail.mockResolvedValue(citation());
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('abcde東京 😀 tail'));

    renderInspector('/cases/case-1/evidence?citation=cit-1');

    const heading = await screen.findByRole('heading', { name: /Frozen citation/ });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(heading.tagName).toBe('H3');

    const closeButton = screen.getByRole('button', { name: 'Close inspector' });
    expect(closeButton.tagName).toBe('BUTTON');
  });
});

describe('EvidenceInspector quotation states', () => {
  it('highlights the correct repeated quotation using its offsets', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({
        relatedClaims: [
          reference({
            alignmentStatus: 'exact',
            quote: 'repeat',
            startChar: 11,
            endChar: 17,
          }),
        ],
      })
    );
    apiMocks.getClaimDetail.mockResolvedValue(
      claimDetail({
        passages: [
          claimLink({
            alignmentStatus: 'exact',
            quote: 'repeat',
            startChar: 11,
            endChar: 17,
          }),
        ],
      })
    );
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('repeat and repeat'));

    const { container } = renderInspector(
      '/cases/case-1/evidence?evidence=ev-1&claim=claim-1&capture=cap-1'
    );

    const mark = await waitFor(() => {
      const element = container.querySelector('mark');
      expect(element).not.toBeNull();
      return element as HTMLElement;
    });
    expect(mark.textContent).toBe('repeat');
    expect(mark.previousSibling?.textContent).toBe('repeat and ');
    expect(container.querySelectorAll('mark')).toHaveLength(1);
  });

  it('shows an explanatory ambiguous state and no fake highlight', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({
        relatedClaims: [
          reference({
            alignmentStatus: 'ambiguous',
            quote: 'repeat',
            startChar: null,
            endChar: null,
          }),
        ],
      })
    );
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('repeat and repeat'));

    const { container } = renderInspector(
      '/cases/case-1/evidence?evidence=ev-1&claim=claim-1&capture=cap-1'
    );

    expect((await screen.findAllByText(/Ambiguous/)).length).toBeGreaterThan(0);
    expect(container.querySelector('mark')).toBeNull();
  });

  it('explains a legacy link with no quotation instead of inventing a span', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({
        relatedClaims: [reference({ alignmentStatus: 'not_provided', quote: null })],
      })
    );
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('legacy body without a quote'));

    const { container } = renderInspector(
      '/cases/case-1/evidence?evidence=ev-1&claim=claim-1&capture=cap-1'
    );

    expect((await screen.findAllByText(/No quotation was provided/)).length).toBeGreaterThan(0);
    expect(container.querySelector('mark')).toBeNull();
    expect(screen.queryByText('Quotation')).toBeNull();
  });

  it('renders source HTML as text, never as markup', async () => {
    const html = '<img src=x onerror=alert(1)>';
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({
        relatedClaims: [
          reference({
            alignmentStatus: 'exact',
            quote: html,
            startChar: 0,
            endChar: Array.from(html).length,
          }),
        ],
      })
    );
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor(html));

    const { container } = renderInspector(
      '/cases/case-1/evidence?evidence=ev-1&claim=claim-1&capture=cap-1'
    );

    await waitFor(() => expect(container.querySelector('mark')).not.toBeNull());
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByTestId('capture-text').textContent).toContain(
      '<img src=x onerror=alert(1)>'
    );
  });
});

describe('EvidenceInspector capture windows and metadata', () => {
  it('navigates forward with explicit returned/total code-point lengths', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({ relatedClaims: [], captures: [capture()] })
    );
    apiMocks.getCaptureWindow.mockImplementation(
      (
        _caseId: string,
        _evidenceId: string,
        _captureId: string,
        options: { start?: number; length?: number } = {}
      ) => {
        const start = options.start ?? 0;
        if (start === 0) {
          return Promise.resolve(
            windowFor('A'.repeat(20000), 0, 30000)
          );
        }
        return Promise.resolve(windowFor('B'.repeat(10000), 20000, 30000));
      }
    );

    renderInspector('/cases/case-1/evidence?evidence=ev-1&capture=cap-1');

    expect(
      await screen.findByText(/Showing code points 0–20000 of 30000/)
    ).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: /Next window/ }));

    expect(
      await screen.findByText(/Showing code points 20000–30000 of 30000/)
    ).toBeDefined();
    expect(apiMocks.getCaptureWindow).toHaveBeenLastCalledWith(
      'case-1',
      'ev-1',
      'cap-1',
      expect.objectContaining({ start: 20000 })
    );
    expect(
      (screen.getByRole('button', { name: /Next window/ }) as HTMLButtonElement).disabled
    ).toBe(true);
  });

  it('offers recovery for a window rejected as out of range', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(evidenceDetail({ relatedClaims: [] }));
    apiMocks.getCaptureWindow.mockRejectedValue(
      new ApiError('start is beyond the stored body', 422)
    );

    renderInspector('/cases/case-1/evidence?evidence=ev-1&capture=cap-1&start=999999');

    expect(await screen.findByText(/outside this capture/)).toBeDefined();
    expect(screen.getByRole('button', { name: 'Start of capture' })).toBeDefined();
  });

  it('links only safe external URLs and labels unknowns honestly', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({
        relatedClaims: [],
        publisher: null,
        originUrl: 'javascript:alert(1)',
        canonicalUrl: 'https://safe.example.com/canonical',
      })
    );
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('body'));

    const { container } = renderInspector(
      '/cases/case-1/evidence?evidence=ev-1&capture=cap-1'
    );

    expect(await screen.findByText('Not a safe external URL')).toBeDefined();
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();

    const safeLink = container.querySelector(
      'a[href="https://safe.example.com/canonical"]'
    );
    expect(safeLink).not.toBeNull();
    expect(safeLink?.getAttribute('rel')).toBe('noopener noreferrer');
    expect(screen.getAllByText('Unknown').length).toBeGreaterThan(0);
  });

  it('shows an explicit unavailable state when no capture exists', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({ currentCaptureId: null, captures: [], relatedClaims: [] })
    );

    renderInspector('/cases/case-1/evidence?evidence=ev-1');

    expect(
      await screen.findByText(/No immutable capture is recorded for this source/)
    ).toBeDefined();
    expect(screen.queryByTestId('capture-text')).toBeNull();
  });
});

describe('EvidenceInspector error states and selection', () => {
  it('distinguishes a missing citation (404) from a retryable network error', async () => {
    apiMocks.getCitationDetail.mockRejectedValue(new ApiError('missing', 404));
    renderInspector('/cases/case-1/evidence?citation=missing');
    expect(await screen.findByText(/Citation not found for this case/)).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
  });

  it('retries a network error and then renders the source', async () => {
    apiMocks.getEvidenceDetail
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce(evidenceDetail({ relatedClaims: [] }));
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('body'));

    renderInspector('/cases/case-1/evidence?evidence=ev-1&capture=cap-1');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('network down');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByText('Example source')).toBeDefined();
    expect(apiMocks.getEvidenceDetail).toHaveBeenCalledTimes(2);
  });

  it('selects a linked claim and moves focus to the inspector heading', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({
        relatedClaims: [
          reference({
            alignmentStatus: 'exact',
            quote: 'quote',
            startChar: 0,
            endChar: 5,
          }),
        ],
      })
    );
    apiMocks.getClaimDetail.mockResolvedValue(
      claimDetail({
        passages: [
          claimLink({
            alignmentStatus: 'exact',
            quote: 'quote',
            startChar: 0,
            endChar: 5,
          }),
        ],
      })
    );
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('quote in body'));

    renderInspector('/cases/case-1/evidence?evidence=ev-1');

    const button = await screen.findByRole('button', { name: /Show passage/ });
    expect(button.tagName).toBe('BUTTON');
    fireEvent.click(button);

    expect(await screen.findByTestId('location')).toBeDefined();
    expect(screen.getByTestId('location').textContent).toContain(
      'claim=claim-1&evidence=ev-1&capture=cap-1'
    );
    const heading = screen.getByRole('heading', { name: /Evidence inspector/ });
    await waitFor(() => expect(document.activeElement).toBe(heading));
  });
});

describe('EvidenceTab inspector entry points', () => {
  it('opens the inspector from an evidence card with encoded selectors', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([evidenceItem()]);
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({ relatedClaims: [] })
    );
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('body'));

    withProviders(
      '/cases/case-1/evidence',
      <EvidenceTab caseId="case-1" />
    );

    expect(await screen.findByText('Example source')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /Inspect source/ }));

    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain(
        'evidence=ev-1&capture=cap-1'
      )
    );
    expect(await screen.findByText(/Captured text/)).toBeDefined();
  });
});

describe('EvidenceInspector case scoping', () => {
  const CaseInspectorRoute = () => {
    const { id } = useParams<{ id: string }>();
    return (
      <>
        <Link to="/cases/case-b/evidence?evidence=ev-1&capture=cap-1">to-b</Link>
        <EvidenceInspector caseId={id!} />
      </>
    );
  };

  it('never reuses case A inspector data after switching to case B', async () => {
    apiMocks.getEvidenceDetail.mockImplementation((caseId: string) =>
      Promise.resolve(
        evidenceDetail({
          id: 'ev-1',
          title: caseId === 'case-b' ? 'Case B source' : 'Case A source',
          relatedClaims: [],
        })
      )
    );
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('body'));

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/cases/case-a/evidence?evidence=ev-1&capture=cap-1']}>
          <Routes>
            <Route path="/cases/:id/evidence" element={<CaseInspectorRoute />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(await screen.findByText('Case A source')).toBeDefined();
    fireEvent.click(screen.getByRole('link', { name: 'to-b' }));
    expect(await screen.findByText('Case B source')).toBeDefined();
    expect(screen.queryByText('Case A source')).toBeNull();
  });
});

describe('EvidenceInspector claim-only selections', () => {
  it('renders frozen claim text, signature, and changed-live-state note', async () => {
    apiMocks.getClaimDetail.mockResolvedValue(
      claimDetail({
        claimText: 'Frozen snapshot claim',
        claimSignature: 'frozen-signature',
        verificationStatus: 'alleged',
        verificationProvenance: 'legacy_unknown',
        snapshotId: 'snap-1',
        liveState: {
          present: true,
          claimSignature: 'live-signature',
          textMatchesSnapshot: false,
          currentCaptureId: null,
          currentCaptureMatchesSnapshot: null,
        },
      })
    );

    renderInspector('/cases/case-1/evidence?claim=claim-1&snapshot=snap-1');

    expect(await screen.findByRole('heading', { name: 'Frozen claim text' })).toBeDefined();
    expect(screen.getByText('Frozen snapshot claim')).toBeDefined();
    expect(screen.getByText('frozen-signature')).toBeDefined();
    expect(screen.getByText(/live claim has changed since this observation/i)).toBeDefined();
    expect(screen.getByText(/not a reviewer confirmation/)).toBeDefined();
    expect(screen.queryByText('No evidence source is available for this selection.')).toBeNull();
    expect(apiMocks.getClaimDetail).toHaveBeenCalledWith('case-1', 'claim-1', 'snap-1');
  });

  it('shows the no-longer-present note for a frozen claim', async () => {
    apiMocks.getClaimDetail.mockResolvedValue(
      claimDetail({
        liveState: {
          present: false,
          claimSignature: null,
          textMatchesSnapshot: null,
          currentCaptureId: null,
          currentCaptureMatchesSnapshot: null,
        },
      })
    );

    renderInspector('/cases/case-1/evidence?claim=claim-1&snapshot=snap-1');

    expect(await screen.findByText(/live case no longer contains this claim/i)).toBeDefined();
    expect(screen.getByText('Claim text')).toBeDefined();
  });

  it('renders current claim text without a snapshot', async () => {
    apiMocks.getClaimDetail.mockResolvedValue(claimDetail({ claimText: 'Current claim body' }));

    renderInspector('/cases/case-1/evidence?claim=claim-1');

    expect(await screen.findByRole('heading', { name: 'Claim text' })).toBeDefined();
    expect(screen.getByText('Current claim body')).toBeDefined();
    expect(screen.queryByText('Frozen claim text')).toBeNull();
    expect(screen.queryByText('No evidence source is available for this selection.')).toBeNull();
  });

  it('keeps the evidence passage claim text in one existing claim section', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({ relatedClaims: [reference({ claimText: 'Linked reference text' })] })
    );
    apiMocks.getClaimDetail.mockResolvedValue(claimDetail({ claimText: 'Evidence-linked claim' }));

    const { container } = renderInspector(
      '/cases/case-1/evidence?evidence=ev-1&claim=claim-1'
    );

    expect(await screen.findByRole('heading', { name: 'Claim being inspected' })).toBeDefined();
    expect(screen.getByRole('heading', { name: 'Validated passage' })).toBeDefined();
    expect(screen.queryByRole('heading', { name: 'Claim text' })).toBeNull();
    expect(
      container.querySelectorAll('[aria-labelledby="claim-passage-heading"] .inspector-claim-text')
    ).toHaveLength(1);
    expect(
      container.querySelector('[aria-labelledby="claim-passage-heading"] .inspector-claim-text')
        ?.textContent
    ).toBe('Linked reference text');
  });

  it('renders the claim query error for a claim-only selection', async () => {
    apiMocks.getClaimDetail.mockRejectedValue(new Error('claim service unavailable'));

    renderInspector('/cases/case-1/evidence?claim=claim-1');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('claim service unavailable');
    expect(screen.queryByRole('heading', { name: 'Claim text' })).toBeNull();
    expect(screen.queryByText('No evidence source is available for this selection.')).toBeNull();
  });

  it('explains a claim missing from the selected snapshot without showing other claim text', async () => {
    apiMocks.getClaimDetail.mockRejectedValue(new ApiError('missing', 404));

    renderInspector('/cases/case-1/evidence?claim=missing-claim&snapshot=snap-1');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toMatch(/Claim not found for this case/i);
    expect(alert.textContent).toMatch(/may not be present in the selected snapshot/i);
    expect(screen.queryByText('Claim text')).toBeNull();
  });
});

describe('EvidenceInspector historical observations', () => {
  it('resolves a claim from the pinned snapshot and states the live difference', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({
        snapshotId: 'snap-1',
        liveState: {
          present: true,
          claimSignature: null,
          textMatchesSnapshot: null,
          currentCaptureId: 'cap-1',
          currentCaptureMatchesSnapshot: true,
        },
      })
    );
    apiMocks.getClaimDetail.mockResolvedValue(
      claimDetail({
        snapshotId: 'snap-1',
        liveState: {
          present: true,
          claimSignature: 'sig-2',
          textMatchesSnapshot: false,
          currentCaptureId: null,
          currentCaptureMatchesSnapshot: null,
        },
      })
    );
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('Example body text'));

    renderInspector(
      '/cases/case-1/evidence?evidence=ev-1&claim=claim-1&snapshot=snap-1'
    );

    expect(
      await screen.findByText(/Historical observation snap-1/i)
    ).toBeDefined();
    expect(
      await screen.findByText(/live claim has changed since this observation/i)
    ).toBeDefined();
    expect(apiMocks.getClaimDetail).toHaveBeenCalledWith('case-1', 'claim-1', 'snap-1');
    expect(apiMocks.getEvidenceDetail).toHaveBeenCalledWith('case-1', 'ev-1', 'snap-1');
    // The historical view never says who changed anything.
    expect(document.body.textContent ?? '').not.toMatch(/changed by/i);
  });

  it('reports a frozen claim that the live case no longer contains', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({ snapshotId: 'snap-1' })
    );
    apiMocks.getClaimDetail.mockResolvedValue(
      claimDetail({
        snapshotId: 'snap-1',
        liveState: {
          present: false,
          claimSignature: null,
          textMatchesSnapshot: null,
          currentCaptureId: null,
          currentCaptureMatchesSnapshot: null,
        },
      })
    );
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('Example body text'));

    renderInspector(
      '/cases/case-1/evidence?evidence=ev-1&claim=claim-1&snapshot=snap-1'
    );

    expect(
      await screen.findByText(/live case no longer contains this claim/i)
    ).toBeDefined();
  });

  it('resolves evidence metadata from the pinned snapshot and notes a newer capture', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({
        snapshotId: 'snap-1',
        liveState: {
          present: true,
          claimSignature: null,
          textMatchesSnapshot: null,
          currentCaptureId: 'cap-2',
          currentCaptureMatchesSnapshot: false,
        },
      })
    );
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('Example body text'));

    renderInspector('/cases/case-1/evidence?evidence=ev-1&snapshot=snap-1');

    expect(
      await screen.findByText(/Historical observation snap-1/i)
    ).toBeDefined();
    expect(
      await screen.findByText(/newer capture exists in the live case/i)
    ).toBeDefined();
    expect(apiMocks.getEvidenceDetail).toHaveBeenCalledWith('case-1', 'ev-1', 'snap-1');
  });

  it('offers an explicit transition from a pinned observation to current evidence', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({
        snapshotId: 'snap-1',
        liveState: {
          present: true,
          claimSignature: null,
          textMatchesSnapshot: null,
          currentCaptureId: 'cap-1',
          currentCaptureMatchesSnapshot: true,
        },
      })
    );
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('Example body text'));

    renderInspector('/cases/case-1/evidence?evidence=ev-1&snapshot=snap-1');

    const transition = await screen.findByRole('button', { name: /open current evidence/i });
    expect(apiMocks.getEvidenceDetail).toHaveBeenCalledWith('case-1', 'ev-1', 'snap-1');
    // Nothing is fetched as current until the operator chooses the transition.
    expect(apiMocks.getEvidenceDetail).toHaveBeenCalledTimes(1);

    fireEvent.click(transition);

    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).not.toContain('snapshot');
    });
    await waitFor(() => {
      expect(apiMocks.getEvidenceDetail).toHaveBeenLastCalledWith(
        'case-1',
        'ev-1',
        null
      );
    });
  });

  it('explains that a snapshot 404 can mean the entity is absent from that observation', async () => {
    apiMocks.getEvidenceDetail.mockRejectedValue(new ApiError('missing', 404));

    renderInspector('/cases/case-1/evidence?evidence=ev-1&snapshot=snap-1');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent ?? '').toMatch(/may not be present in the selected snapshot/i);
    expect(alert.textContent ?? '').not.toMatch(/no longer exist/i);
  });

  it('does not pass a snapshot selector to the immutable citation reader', async () => {
    apiMocks.getCitationDetail.mockResolvedValue(citation());
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('abcde tail'));

    renderInspector('/cases/case-1/evidence?citation=cit-1&snapshot=snap-1');

    expect(await screen.findByRole('heading', { name: /Frozen citation/ })).toBeDefined();
    expect(apiMocks.getCitationDetail).toHaveBeenCalledWith('case-1', 'cit-1');
    expect(apiMocks.getCitationDetail).toHaveBeenCalledTimes(1);
    await screen.findByTestId('capture-text');
    // The capture-window reader is frozen by capture ID too: the browser's
    // `snapshot` selector must not be forwarded to it either.
    const [, , , windowOptions] = apiMocks.getCaptureWindow.mock.calls[0] as [
      string,
      string,
      string,
      Record<string, unknown>,
    ];
    expect(Object.keys(windowOptions).sort()).toEqual(['length', 'start']);
    expect(JSON.stringify(apiMocks.getCaptureWindow.mock.calls)).not.toMatch(
      /snapshot/i
    );
  });
});

describe('EvidenceInspector explicit diagnostics', () => {
  const states: Array<{
    name: string;
    status: AlignmentStatus | string;
    quote: string | null;
    attribute: string;
    message: RegExp;
  }> = [
    {
      name: 'missing quotation',
      status: 'not_provided',
      quote: null,
      attribute: 'inspector-missing-quotation',
      message: /records no quotation/i,
    },
    {
      name: 'source unavailable',
      status: 'source_unavailable',
      quote: 'quote',
      attribute: 'inspector-source-unavailable',
      message: /captured source text was unavailable/i,
    },
    {
      name: 'ambiguous',
      status: 'ambiguous',
      quote: 'repeat',
      attribute: 'inspector-ambiguous',
      message: /occurs more than once/i,
    },
    {
      name: 'no match',
      status: 'no_match',
      quote: 'absent words',
      attribute: 'inspector-no-match',
      message: /does not appear exactly/i,
    },
    {
      name: 'legacy',
      status: 'legacy_unknown',
      quote: null,
      attribute: 'inspector-legacy',
      message: /predates that assessment/i,
    },
  ];

  it.each(states)(
    'renders its own $name diagnostic with a stable data-state',
    async ({ status, quote, attribute, message }) => {
      apiMocks.getEvidenceDetail.mockResolvedValue(
        evidenceDetail({
          relatedClaims: [
            reference({
              alignmentStatus: status as AlignmentStatus,
              quote,
              startChar: quote ? 0 : null,
              endChar: quote ? Array.from(quote).length : null,
            }),
          ],
        })
      );
      apiMocks.getCaptureWindow.mockResolvedValue(windowFor('repeat and repeat'));

      const { container } = renderInspector(
        '/cases/case-1/evidence?evidence=ev-1&claim=claim-1&capture=cap-1'
      );

      const panel = await waitFor(() => {
        const element = container.querySelector(`[data-state="${attribute}"]`);
        expect(element).not.toBeNull();
        return element as HTMLElement;
      });
      // Distinct text, never colour alone.
      expect(panel.textContent).toMatch(message);
      expect(panel.getAttribute('data-state')).toBe(attribute);

      // Exactly one of the five diagnostics is active at a time.
      const active = container.querySelectorAll(
        '.inspector-diagnostic-state[data-state]'
      );
      expect(active).toHaveLength(1);
      expect(active[0].getAttribute('data-state')).toBe(attribute);

      // No fabricated highlight for any non-exact reading.
      expect(container.querySelector('mark')).toBeNull();
    }
  );

  it('gives the five diagnostics five distinct messages', async () => {
    const messages = new Set<string>();

    for (const state of states) {
      apiMocks.getEvidenceDetail.mockResolvedValue(
        evidenceDetail({
          relatedClaims: [
            reference({
              alignmentStatus: state.status as AlignmentStatus,
              quote: state.quote,
            }),
          ],
        })
      );
      apiMocks.getCaptureWindow.mockResolvedValue(windowFor('repeat and repeat'));

      const { container, unmount } = renderInspector(
        `/cases/case-1/evidence?evidence=ev-1&claim=claim-1&capture=cap-1&start=${messages.size}`
      );
      const panel = await waitFor(() => {
        const element = container.querySelector(
          `.inspector-diagnostic-state[data-state="${state.attribute}"]`
        );
        expect(element).not.toBeNull();
        return element as HTMLElement;
      });
      messages.add(panel.textContent ?? '');
      unmount();
    }

    expect(messages.size).toBe(states.length);
  });

  it('keeps the exact reading as alignment, not a confirmation', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({
        relatedClaims: [
          reference({ alignmentStatus: 'exact', quote: 'quote', startChar: 0, endChar: 5 }),
        ],
      })
    );
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('quote in body'));

    const { container } = renderInspector(
      '/cases/case-1/evidence?evidence=ev-1&claim=claim-1&capture=cap-1'
    );

    await waitFor(() => expect(container.querySelector('mark')).not.toBeNull());
    expect(container.querySelector('[data-state="inspector-exact"]')).not.toBeNull();
    expect(container.querySelector('.inspector-diagnostic-state')).toBeNull();
    // The label never reads as a confirmation badge.
    expect(document.body.textContent ?? '').not.toMatch(/\bConfirmed\b/);
    expect(container.querySelector('.badge-success')).toBeNull();
  });
});

describe('EvidenceInspector frozen citation read-only context', () => {
  it('renders frozen citation values without editable controls', async () => {
    apiMocks.getCitationDetail.mockResolvedValue(citation());
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('abcde東京 😀 tail'));

    const { container } = renderInspector(
      '/cases/case-1/evidence?citation=cit-1&snapshot=snap-1'
    );

    const frozen = await waitFor(() => {
      const element = container.querySelector('[data-frozen="true"]');
      expect(element).not.toBeNull();
      return element as HTMLElement;
    });
    expect(frozen.getAttribute('data-readonly')).toBe('true');
    expect(frozen.textContent).toContain('Frozen claim text');
    expect(frozen.textContent).toMatch(/read from the immutable citation record/i);

    // Nothing in the frozen context (or the inspector) is an editable field.
    for (const selector of ['input', 'textarea', 'select', '[contenteditable="true"]']) {
      expect(container.querySelectorAll(selector)).toHaveLength(0);
    }

    // The captured text is static, read-only text.
    const capturedText = await screen.findByTestId('capture-text');
    expect(capturedText.tagName).toBe('PRE');
    expect(capturedText.getAttribute('data-readonly')).toBe('true');
    expect(capturedText.querySelectorAll('input, textarea')).toHaveLength(0);

    // The citation reader is frozen by ID, so it never receives a snapshot.
    expect(apiMocks.getCitationDetail).toHaveBeenCalledWith('case-1', 'cit-1');
  });
});

describe('EvidenceInspector focus restoration', () => {
  const OpenerProbe = () => {
    const [, setSearchParams] = useSearchParams();
    return (
      <button
        type="button"
        onClick={() => setSearchParams({ evidence: 'ev-1', capture: 'cap-1' })}
      >
        Inspect this source
      </button>
    );
  };

  it('returns focus to the invoking control when the inspector closes', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(evidenceDetail({ relatedClaims: [] }));
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('body'));

    withProviders(
      '/cases/case-1/evidence',
      <>
        <OpenerProbe />
        <EvidenceInspector caseId="case-1" />
      </>
    );

    const opener = screen.getByRole('button', { name: 'Inspect this source' });
    opener.focus();
    expect(document.activeElement).toBe(opener);

    fireEvent.click(opener);

    const heading = await screen.findByRole('heading', { name: /Evidence inspector/ });
    await waitFor(() => expect(document.activeElement).toBe(heading));

    fireEvent.click(screen.getByRole('button', { name: 'Close inspector' }));

    await waitFor(() => expect(document.activeElement).toBe(opener));
    expect(screen.queryByRole('heading', { name: /Evidence inspector/ })).toBeNull();
  });

  it('uses an explicit return-focus target when one is supplied', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(evidenceDetail({ relatedClaims: [] }));
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('body'));

    const ReturnProbe = () => {
      const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
      return (
        <>
          <button type="button" ref={setAnchor} data-testid="return-target">
            Return target
          </button>
          <EvidenceInspector caseId="case-1" returnFocusTo={anchor} />
        </>
      );
    };

    withProviders('/cases/case-1/evidence?evidence=ev-1&capture=cap-1', <ReturnProbe />);
    // The heading takes focus on open…
    const heading = await screen.findByRole('heading', { name: /Evidence inspector/ });
    await waitFor(() => expect(document.activeElement).toBe(heading));

    fireEvent.click(screen.getByRole('button', { name: 'Close inspector' }));
    // …and focus returns to the supplied target rather than to the body.
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByTestId('return-target'))
    );
  });
});

describe('EvidenceInspector narrow viewport metadata', () => {
  const METADATA_LABELS = [
    'Evidence ID',
    'Title',
    'Publisher',
    'Source type',
    'Recorded verification',
    'Published',
    'Original URL',
    'Canonical URL',
    'Capture ID',
    'Capture kind',
    'Current capture',
    'Recorded at',
    'Observed at',
    'Content SHA-256',
    'Capture length',
    'Extraction scope',
    'Analysis provenance',
    'Extraction metadata',
    'Code-point range',
    'Assessment origin',
    'Assessment version',
    'Citation ID',
    'Claim signature',
    'Original claim ID',
  ];

  it('exposes every metadata field, stacked, at 375px', async () => {
    // jsdom performs no layout: this asserts the DOM contract (every label/value
    // pair rendered, wrap-friendly classes, no fixed widths) plus the narrow
    // stylesheet rules. Visual proof belongs to the F16 browser gate.
    const originalWidth = window.innerWidth;
    window.innerWidth = 375;

    apiMocks.getCitationDetail.mockResolvedValue(citation());
    apiMocks.getCaptureWindow.mockResolvedValue(windowFor('abcde東京 😀 tail'));

    const { container } = renderInspector('/cases/case-1/evidence?citation=cit-1');

    await screen.findByRole('heading', { name: 'Frozen claim text' });
    await screen.findByTestId('capture-text');

    const labels = Array.from(container.querySelectorAll('.inspector-field-label')).map(
      (element) => element.textContent ?? ''
    );
    for (const label of METADATA_LABELS) {
      expect(labels).toContain(label);
    }

    const fields = Array.from(container.querySelectorAll('.inspector-field'));
    expect(fields.length).toBeGreaterThanOrEqual(METADATA_LABELS.length);
    for (const field of fields) {
      expect(field.querySelectorAll('.inspector-field-label')).toHaveLength(1);
      const value = field.querySelector('.inspector-field-value');
      expect(value).not.toBeNull();
      expect((value?.textContent ?? '').trim()).not.toBe('');
    }

    // Nothing may force a fixed width or suppress wrapping inside the panel.
    for (const element of Array.from(container.querySelectorAll('*'))) {
      const style = element.getAttribute('style') ?? '';
      expect(style).not.toMatch(/width\s*:/);
      expect(style).not.toMatch(/nowrap/);
    }

    // Every metadata value is rendered through the wrap-friendly value class,
    // so a long capture id or hash wraps instead of widening the panel.
    expect(container.querySelectorAll('.inspector-field-value').length).toBe(
      fields.length
    );

    window.innerWidth = originalWidth;
  });
});
