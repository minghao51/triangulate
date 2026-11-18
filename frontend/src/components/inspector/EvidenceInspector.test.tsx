import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Link, MemoryRouter, Route, Routes, useLocation, useParams } from 'react-router-dom';

import { EvidenceInspector } from './EvidenceInspector';
import EvidenceTab from '../../pages/tabs/EvidenceTab';
import { ApiError } from '../../services/api-error';
import type {
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
