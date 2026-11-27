import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Link, MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import CaseIntelligenceCenter from './CaseIntelligenceCenter';
import { ApiError } from '../services/api-error';
import { useCaseStore } from '../stores/case-store';

const apiMocks = vi.hoisted(() => ({
  getCaseDetail: vi.fn(),
  getClaimsOverviewForCase: vi.fn(),
  getEvidenceForCase: vi.fn(),
  getExceptionsForCase: vi.fn(),
  getPartiesForCase: vi.fn(),
  getTimelineForCase: vi.fn(),
  getRunHistoryForCase: vi.fn(),
  getInvestigationRuns: vi.fn(),
  getRunChanges: vi.fn(),
  getClaimDetail: vi.fn(),
  getEvidenceDetail: vi.fn(),
  getCitationDetail: vi.fn(),
  getCaptureWindow: vi.fn(),
  getReportForCase: vi.fn(),
  getEvaluationForCase: vi.fn(),
  getReviewActivityForCase: vi.fn(),
  submitCaseReviewAction: vi.fn(),
  submitExceptionAction: vi.fn(),
  createCaseAnnotation: vi.fn(),
  downloadManifestReport: vi.fn(),
  downloadMarkdownReport: vi.fn(),
}));

vi.mock('../services/api', () => apiMocks);

const baseCaseDetail = {
  case: {
    id: 'case-12345678',
    query: 'Example Case',
    conflictDomain: 'Energy Security',
    status: 'review ready',
    stage: 'REVIEW',
    counts: {
      articles: 1,
      events: 1,
      reviewItems: 1,
    },
    automationMode: 'safe',
    hasNewMaterial: true,
    openExceptionsCount: 1,
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
    report: {
      status: 'pending',
      markdownPath: null,
      markdownContent: null,
      manifestPath: null,
    },
  },
} as const;

const routeExpectations = [
  { initialEntry: '/cases/case-12345678', heading: 'Operator Commands' },
  { initialEntry: '/cases/case-12345678/evidence', heading: 'Evidence Gallery (1)' },
  { initialEntry: '/cases/case-12345678/claims', heading: 'Primary Claims Mapping' },
  { initialEntry: '/cases/case-12345678/compare', heading: 'Compare sources' },
  { initialEntry: '/cases/case-12345678/parties', heading: 'Confirmed & Inferred Parties' },
  { initialEntry: '/cases/case-12345678/map', heading: 'Geographic Event Map' },
  { initialEntry: '/cases/case-12345678/timeline', heading: 'Investigation Timeline' },
  { initialEntry: '/cases/case-12345678/exceptions', heading: 'Exception Queue' },
  { initialEntry: '/cases/case-12345678/report', heading: 'Final Investigation Report' },
  { initialEntry: '/cases/case-12345678/changes', heading: 'Changes between observations' },
  { initialEntry: '/cases/case-12345678/run-history', heading: 'Pipeline Execution History' },
];

function renderCaseRoute(initialEntry: string) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

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

describe('CaseIntelligenceCenter routes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCaseStore.getState().clearActiveCase();

    apiMocks.getCaseDetail.mockResolvedValue(baseCaseDetail);
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({
      claims: [
        {
          id: 'claim-1',
          text: 'Claim text',
          verificationStatus: 'confirmed',
          type: 'fact',
          controversyScore: 0.1,
          supportCount: 2,
          opposeCount: 0,
          sourceDiversityCount: 1,
          claimSignature: 'claim-1',
          narrativeClusterId: 'cluster-1',
          evidence: [],
        },
      ],
      narratives: [
        {
          id: 'narrative-1',
          clusterId: 'cluster-1',
          stanceSummary: 'Primary cluster',
          sourceCount: 1,
          claimCount: 1,
        },
      ],
    });
    apiMocks.getEvidenceForCase.mockResolvedValue([
      {
        id: 'evidence-1',
        title: 'Evidence title',
        originUrl: 'https://example.com',
        canonicalUrl: 'https://example.com',
        publisher: 'Example News',
        sourceType: 'rss',
        verificationStatus: 'confirmed',
        credibilityTier: 'high',
        requiresHumanReview: false,
        linkedClaims: ['claim-1'],
        verificationChecks: [],
      },
    ]);
    apiMocks.getExceptionsForCase.mockResolvedValue([
      {
        id: 'exc-1',
        type: 'missing_source',
        message: 'Need another source',
        severity: 'medium',
        status: 'open',
        recommendedAction: 'Add corroboration',
        isOpen: true,
      },
    ]);
    apiMocks.getPartiesForCase.mockResolvedValue([
      {
        id: 'party-1',
        name: 'Alpha',
        aliases: [],
        description: 'Example party',
        overallStance: 'neutral',
        isModelInferred: false,
        associatedClaimsCount: 1,
      },
    ]);
    apiMocks.getTimelineForCase.mockResolvedValue([
      {
        id: 'event-1',
        timestamp: '2026-03-19T10:00:00Z',
        title: 'Timeline event',
        summary: 'Event summary',
        verificationStatus: 'confirmed',
        linkedEvidenceCount: 1,
        locationCountryCode: 'SG',
        locationLat: 1.3521,
        locationLon: 103.8198,
      },
    ]);
    apiMocks.getInvestigationRuns.mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
      hasMore: false,
    });
    apiMocks.getRunHistoryForCase.mockResolvedValue([
      {
        id: 'run-1',
        stage: 'REVIEW',
        model: 'gpt-5.4',
        durationMs: 1000,
        status: 'success',
        fallbackCount: 0,
        parseFailureCount: 0,
        timestamp: '2026-03-19T10:00:00Z',
        message: null,
      },
    ]);
    apiMocks.getReportForCase.mockResolvedValue({
      status: 'pending',
      markdownPath: null,
      markdownContent: null,
      manifestPath: null,
    });
    apiMocks.getEvaluationForCase.mockResolvedValue({ latest: null, history: [] });
    apiMocks.getReviewActivityForCase.mockResolvedValue({ auditEntries: [], annotations: [] });
  });

  it.each(routeExpectations)('renders the expected view for $initialEntry', async ({ initialEntry, heading }) => {
    renderCaseRoute(initialEntry);

    expect(await screen.findByRole('heading', { name: heading })).toBeDefined();
    expect(screen.queryByText('Tab not found')).toBeNull();
  });

  it('shows "No saved evaluation" instead of inventing one when none is recorded', async () => {
    renderCaseRoute('/cases/case-12345678');

    expect(await screen.findByText('No saved evaluation')).toBeDefined();
    expect(screen.queryByText('Pending')).toBeNull();
    expect(screen.queryByText('Not recorded')).toBeNull();
  });
});

describe('CaseIntelligenceCenter failure and case-switch states', () => {
  const storeState = () => useCaseStore.getState();

  beforeEach(() => {
    vi.clearAllMocks();
    useCaseStore.getState().clearActiveCase();
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims: [], narratives: [] });
    apiMocks.getEvidenceForCase.mockResolvedValue([]);
    apiMocks.getExceptionsForCase.mockResolvedValue([]);
    apiMocks.getPartiesForCase.mockResolvedValue([]);
    apiMocks.getTimelineForCase.mockResolvedValue([]);
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);
    apiMocks.getReportForCase.mockResolvedValue({
      status: 'pending',
      markdownPath: null,
      markdownContent: null,
      manifestPath: null,
    });
    apiMocks.getEvaluationForCase.mockResolvedValue({ latest: null, history: [] });
    apiMocks.getReviewActivityForCase.mockResolvedValue({ auditEntries: [], annotations: [] });
  });

  it('shows a retryable error instead of a blank panel when the case read fails', async () => {
    apiMocks.getCaseDetail.mockRejectedValueOnce(new Error('case read failed'));

    renderCaseRoute('/cases/case-12345678');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('case read failed');
    expect(screen.queryByText('Operator Commands')).toBeNull();

    apiMocks.getCaseDetail.mockResolvedValueOnce(baseCaseDetail);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByRole('heading', { name: 'Operator Commands' })).toBeDefined();
  });

  it('states that a case is not found instead of returning nothing', async () => {
    apiMocks.getCaseDetail.mockResolvedValue({
      ...baseCaseDetail,
      case: { ...baseCaseDetail.case, id: 'a-different-case' },
    });

    renderCaseRoute('/cases/case-12345678');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Case not found');
    expect(alert.textContent).toContain('case-12345678');
    expect(screen.getByRole('button', { name: /Back to Cases/i })).toBeDefined();
  });

  it('never lets a late response for the previous case overwrite the current case', async () => {
    const caseA = { ...baseCaseDetail, case: { ...baseCaseDetail.case, id: 'case-AAAAAAAA', query: 'Case A' } };
    const caseB = { ...baseCaseDetail, case: { ...baseCaseDetail.case, id: 'case-BBBBBBBB', query: 'Case B' } };

    let resolveA: (value: unknown) => void = () => {};
    apiMocks.getCaseDetail.mockImplementation((caseId: string) => {
      if (caseId === 'case-AAAAAAAA') {
        return new Promise((resolve) => {
          resolveA = resolve;
        });
      }
      return Promise.resolve(caseB);
    });

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/cases/case-AAAAAAAA']}>
          <Routes>
            <Route path="/cases/:id/*" element={<CaseSwitcher />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(await screen.findByText('Loading case intelligence...')).toBeDefined();
    expect(storeState().activeCase).toBeNull();

    fireEvent.click(screen.getByRole('link', { name: 'go-to-b' }));
    expect(await screen.findByRole('heading', { name: 'Operator Commands' })).toBeDefined();
    expect(storeState().activeCase?.id).toBe('case-BBBBBBBB');

    // The stale case A answer arrives after case B is displayed.
    resolveA(caseA);
    await waitFor(() => expect(storeState().activeCase?.id).toBe('case-BBBBBBBB'));
    expect(storeState().activeCase?.query).toBe('Case B');
    expect(storeState().caseDetail?.case.id).toBe('case-BBBBBBBB');
  });

  it('clears the shared store when the case workspace unmounts', async () => {
    apiMocks.getCaseDetail.mockResolvedValue(baseCaseDetail);

    const { unmount } = renderCaseRoute('/cases/case-12345678');
    expect(await screen.findByRole('heading', { name: 'Operator Commands' })).toBeDefined();
    expect(storeState().activeCase?.id).toBe('case-12345678');

    unmount();
    await waitFor(() => expect(storeState().activeCase).toBeNull());
    expect(storeState().caseDetail).toBeNull();
  });
});

const CaseSwitcher = () => (
  <>
    <Link to="/cases/case-BBBBBBBB">go-to-b</Link>
    <CaseIntelligenceCenter />
  </>
);

describe('CaseIntelligenceCenter grouped navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    useCaseStore.getState().clearActiveCase();
    apiMocks.getCaseDetail.mockResolvedValue(baseCaseDetail);
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims: [], narratives: [] });
    apiMocks.getEvidenceForCase.mockResolvedValue([]);
    apiMocks.getExceptionsForCase.mockResolvedValue([]);
    apiMocks.getPartiesForCase.mockResolvedValue([]);
    apiMocks.getTimelineForCase.mockResolvedValue([]);
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);
    apiMocks.getReportForCase.mockResolvedValue({
      status: 'pending',
      markdownPath: null,
      markdownContent: null,
      manifestPath: null,
    });
    apiMocks.getEvaluationForCase.mockResolvedValue({ latest: null, history: [] });
    apiMocks.getReviewActivityForCase.mockResolvedValue({ auditEntries: [], annotations: [] });
  });

  it('exposes exactly five group headings and sixteen link destinations', async () => {
    renderCaseRoute('/cases/case-12345678');

    const nav = await screen.findByRole('navigation', { name: 'Case views' });

    const groupHeadings = Array.from(nav.querySelectorAll('h2')).map((node) => node.textContent);
    expect(groupHeadings).toEqual(['Start', 'Evidence', 'Context', 'Review & Output', 'Activity']);
    // Group headings are not navigation targets themselves.
    expect(screen.queryByRole('link', { name: 'Start' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Review & Output' })).toBeNull();

    const links = Array.from(nav.querySelectorAll('a'));
    expect(links).toHaveLength(16);
    const hrefs = links.map((link) => link.getAttribute('href'));
    expect(hrefs).toEqual([
      '/cases/case-12345678',
      '/cases/case-12345678/search',
      '/cases/case-12345678/evidence',
      '/cases/case-12345678/claims',
      '/cases/case-12345678/compare',
      '/cases/case-12345678/sources',
      '/cases/case-12345678/parties',
      '/cases/case-12345678/map',
      '/cases/case-12345678/timeline',
      '/cases/case-12345678/network',
      '/cases/case-12345678/narratives',
      '/cases/case-12345678/exceptions',
      '/cases/case-12345678/report',
      '/cases/case-12345678/changes',
      '/cases/case-12345678/run-history',
      '/cases/case-12345678/pipeline',
    ]);
  });

  it('marks only the active destination with aria-current and keeps standard link semantics', async () => {
    renderCaseRoute('/cases/case-12345678/timeline');

    const nav = await screen.findByRole('navigation', { name: 'Case views' });
    const current = Array.from(nav.querySelectorAll('[aria-current]'));
    expect(current).toHaveLength(1);
    expect(current[0].textContent).toContain('Timeline');
    expect(current[0].getAttribute('aria-current')).toBe('page');
    // Native links, not ARIA tabs.
    expect(nav.querySelectorAll('[role="tab"], [role="tablist"]')).toHaveLength(0);
  });

  it('drops an unlisted parameter from the committed url', async () => {
    renderCaseRoute('/cases/case-12345678/timeline?foo=bar&claimQuery=grid');

    const nav = await screen.findByRole('navigation', { name: 'Case views' });
    await waitFor(() => {
      const active = nav.querySelector('[aria-current="page"]');
      expect(active?.getAttribute('href')).toBe('/cases/case-12345678/timeline');
    });
  });

  it('shows the unsupported historical view gate before any view fetch', async () => {
    renderCaseRoute('/cases/case-12345678/timeline?snapshot=snap-1');

    expect(await screen.findByText('Unsupported historical view')).toBeDefined();
    await new Promise((resolve) => setTimeout(resolve, 0));

    // The historical selector is never dropped to reveal live data.
    expect(apiMocks.getTimelineForCase).not.toHaveBeenCalled();
    expect(screen.queryByRole('heading', { name: 'Investigation Timeline' })).toBeNull();

    const openCurrent = screen.getByRole('link', { name: 'Open current Timeline' });
    expect(openCurrent.getAttribute('href')).toBe('/cases/case-12345678/timeline');

    fireEvent.click(openCurrent);
    expect(await screen.findByRole('heading', { name: 'Investigation Timeline' })).toBeDefined();
    expect(apiMocks.getTimelineForCase).toHaveBeenCalledTimes(1);
  });

  it('gates every current-only view but leaves historical readers alone', async () => {
    const { unmount } = renderCaseRoute('/cases/case-12345678/parties?snapshot=snap-9');
    expect(await screen.findByText('Unsupported historical view')).toBeDefined();
    expect(apiMocks.getPartiesForCase).not.toHaveBeenCalled();
    unmount();

    // The claims list is a current-only overview reader: a pinned observation
    // must be gated, never silently rendered as live claims.
    const claims = renderCaseRoute('/cases/case-12345678/claims?snapshot=snap-9');
    expect(await screen.findByText('Unsupported historical view')).toBeDefined();
    expect(apiMocks.getClaimsOverviewForCase).not.toHaveBeenCalled();
    expect(
      screen.getByRole('link', { name: 'Open current Claims' }).getAttribute('href')
    ).toBe('/cases/case-12345678/claims');
    claims.unmount();

    // Changes keeps its recorded-delta reader and its frozen-claim panel.
    renderCaseRoute('/cases/case-12345678/changes?snapshot=snap-9');
    expect(
      await screen.findByRole('heading', { name: 'Changes between observations' })
    ).toBeDefined();
    expect(screen.queryByText('Unsupported historical view')).toBeNull();
  });

  it('restores the last committed per-view href from session memory', async () => {
    const first = renderCaseRoute('/cases/case-12345678/claims?claimStatus=contested');
    expect(await screen.findByRole('heading', { name: 'Primary Claims Mapping' })).toBeDefined();
    await waitFor(() =>
      expect(
        window.sessionStorage.getItem('triangulate:case-view:v1:case-12345678')
      ).toContain('claimStatus=contested')
    );
    first.unmount();

    renderCaseRoute('/cases/case-12345678');
    const nav = await screen.findByRole('navigation', { name: 'Case views' });
    await waitFor(() => {
      const claimsLink = Array.from(nav.querySelectorAll('a')).find((link) =>
        link.textContent?.includes('Claims')
      );
      expect(claimsLink?.getAttribute('href')).toBe(
        '/cases/case-12345678/claims?claimStatus=contested'
      );
    });
  });
});

// ---------------------------------------------------------------------------
// F04 — contextual review and annotations
// ---------------------------------------------------------------------------

const entityCaseDetail = {
  ...baseCaseDetail,
  tabs: {
    ...baseCaseDetail.tabs,
    claims: [
      {
        id: 'claim-current',
        text: 'Current-case claim about the grid',
        verificationStatus: 'confirmed',
        type: 'fact',
        controversyScore: 0.1,
        supportCount: 1,
        opposeCount: 0,
        sourceDiversityCount: 1,
        claimSignature: 'sig-current',
        narrativeClusterId: 'cluster-current',
        evidence: [],
      },
      {
        id: 'claim-frozen',
        text: 'Frozen historical claim',
        verificationStatus: 'unknown',
        type: 'fact',
        controversyScore: null,
        supportCount: 0,
        opposeCount: 0,
        sourceDiversityCount: 0,
        claimSignature: 'sig-frozen',
        narrativeClusterId: null,
        evidence: [],
        isFrozen: true,
      },
    ],
    evidence: [
      {
        id: 'evidence-current',
        title: 'Recorded evidence item',
        originUrl: 'https://example.com',
        canonicalUrl: 'https://example.com',
        publisher: 'Example News',
        sourceType: 'rss',
        verificationStatus: 'confirmed',
        credibilityTier: 'high',
        requiresHumanReview: false,
        linkedClaims: ['claim-current'],
        verificationChecks: [],
      },
    ],
    exceptions: [
      {
        id: 'exception-current',
        type: 'missing_source',
        message: 'Need another source',
        severity: 'medium',
        status: 'open',
        recommendedAction: 'Add corroboration',
        isOpen: true,
      },
    ],
    narratives: [
      {
        id: 'narrative-current',
        clusterId: 'cluster-current',
        stanceSummary: 'Primary current narrative',
        sourceCount: 1,
        claimCount: 1,
        keyThemes: [],
        mainEntities: [],
      },
    ],
  },
} as const;

const emptyActivity = { auditEntries: [], annotations: [] };

function deferred<T>() {
  let resolve: (value: T) => void = () => {};
  let reject: (reason?: unknown) => void = () => {};
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function renderF04(initialEntry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/cases/:id/*" element={<CaseIntelligenceCenter />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { ...result, queryClient };
}

const F04CaseSwitcher = () => (
  <>
    <Link to="/cases/case-BBBBBBBB">switch-to-b</Link>
    <CaseIntelligenceCenter />
  </>
);

const writeBanner = (state: string) =>
  document.querySelector(`[data-write-state="${state}"]`);

const reviewNotesValue = () =>
  (screen.getByLabelText('Review notes') as HTMLTextAreaElement).value;
const annotationContentValue = () =>
  (screen.getByLabelText('Annotation content') as HTMLTextAreaElement).value;

describe('CaseIntelligenceCenter contextual review write states (F04)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCaseStore.getState().clearActiveCase();
    window.sessionStorage.clear();
    apiMocks.getCaseDetail.mockResolvedValue(entityCaseDetail);
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims: [], narratives: [] });
    apiMocks.getEvidenceForCase.mockResolvedValue([]);
    apiMocks.getExceptionsForCase.mockResolvedValue([]);
    apiMocks.getPartiesForCase.mockResolvedValue([]);
    apiMocks.getTimelineForCase.mockResolvedValue([]);
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);
    apiMocks.getReportForCase.mockResolvedValue({
      status: 'pending',
      markdownPath: null,
      markdownContent: null,
      manifestPath: null,
    });
    apiMocks.getEvaluationForCase.mockResolvedValue({ latest: null, history: [] });
    apiMocks.getReviewActivityForCase.mockResolvedValue(emptyActivity);
    apiMocks.submitCaseReviewAction.mockResolvedValue(entityCaseDetail.case);
    apiMocks.createCaseAnnotation.mockResolvedValue({
      id: 'annotation-new',
      targetType: 'case',
      targetId: 'case-12345678',
      annotationType: 'comment',
      author: 'operator',
      content: 'saved',
      metadata: {},
      createdAt: '2026-03-19T10:00:00Z',
    });
  });

  it('renders pending (only that form) then saved-and-refreshed', async () => {
    const pendingPost = deferred<unknown>();
    apiMocks.submitCaseReviewAction.mockReturnValue(pendingPost.promise);

    renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Review notes'), {
      target: { value: 'Retain this rationale' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

    await waitFor(() => expect(writeBanner('pending')).toBeTruthy());
    expect(screen.getByText('Saving…')).toBeDefined();
    // Only the review form is disabled; the annotation draft stays editable.
    expect(screen.getByLabelText('Annotation content').hasAttribute('disabled')).toBe(false);
    expect(apiMocks.submitCaseReviewAction).toHaveBeenCalledTimes(1);

    await act(async () => {
      pendingPost.resolve(entityCaseDetail.case);
    });

    expect(await screen.findByText('Saved and refreshed')).toBeDefined();
    expect(reviewNotesValue()).toBe('');
  });

  it('renders a writer conflict (409) and keeps the rationale', async () => {
    apiMocks.submitCaseReviewAction.mockRejectedValue(new ApiError('writer busy', 409));

    renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Review notes'), {
      target: { value: 'Keep me on conflict' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

    expect(await screen.findByText('Writer conflict (409)')).toBeDefined();
    expect(reviewNotesValue()).toBe('Keep me on conflict');
    expect(screen.queryByText('Blocked (422)')).toBeNull();
  });

  it('renders an invalid/blocked target (422) distinctly from 409', async () => {
    apiMocks.submitCaseReviewAction.mockRejectedValue(new ApiError('not permitted', 422));

    renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Review notes'), {
      target: { value: 'Keep me on blocked' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

    expect(await screen.findByText('Blocked (422)')).toBeDefined();
    expect(reviewNotesValue()).toBe('Keep me on blocked');
    expect(screen.queryByText('Writer conflict (409)')).toBeNull();
  });

  it('marks no automatic POST retry on a lost response and requires an explicit confirmed retry', async () => {
    apiMocks.createCaseAnnotation.mockRejectedValue(new Error('Failed to fetch'));

    renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Annotation target type'), {
      target: { value: 'claim' },
    });
    fireEvent.change(screen.getByLabelText('Annotation target'), {
      target: { value: 'claim-current' },
    });
    fireEvent.change(screen.getByLabelText('Annotation content'), {
      target: { value: 'Lost annotation content' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Annotation' }));

    expect(await screen.findByText('Outcome unknown')).toBeDefined();
    expect(annotationContentValue()).toBe('Lost annotation content');
    expect(apiMocks.createCaseAnnotation).toHaveBeenCalledTimes(1);

    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(apiMocks.createCaseAnnotation).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Reconcile with read (GET)' }));
    expect(await screen.findByText('Read refreshed — still inconclusive')).toBeDefined();
    expect(screen.getByText(/may append a duplicate note/)).toBeDefined();
    // Reconciliation is GET-only and never repeats the write.
    expect(apiMocks.createCaseAnnotation).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Confirm retry' }));
    await waitFor(() => expect(apiMocks.createCaseAnnotation).toHaveBeenCalledTimes(2));
  });

  it('shows "Accepted; refresh failed" after a POST ack and retries only the GET', async () => {
    apiMocks.getReviewActivityForCase
      .mockResolvedValueOnce(emptyActivity)
      .mockRejectedValueOnce(new Error('refresh read failed'));

    renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Review notes'), {
      target: { value: 'Acked but unrefreshed' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

    expect(await screen.findByText('Accepted; refresh failed')).toBeDefined();
    expect(screen.queryByText('Not saved')).toBeNull();
    expect(reviewNotesValue()).toBe('Acked but unrefreshed');
    expect(apiMocks.submitCaseReviewAction).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Retry refresh (GET)' }));
    expect(await screen.findByText('Saved and refreshed')).toBeDefined();
    expect(apiMocks.submitCaseReviewAction).toHaveBeenCalledTimes(1);
  });

  it('turns a saved banner stale after a later detected refresh', async () => {
    const { queryClient } = renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Review notes'), {
      target: { value: 'Saved once' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(await screen.findByText('Saved and refreshed')).toBeDefined();

    apiMocks.getReviewActivityForCase.mockResolvedValue({
      ...emptyActivity,
      auditEntries: [
        {
          id: 'audit-later',
          actionType: 'review:approve',
          targetType: 'case',
          targetId: 'case-12345678',
          actor: 'someone',
          rationale: null,
          metadata: {},
          createdAt: '2026-03-19T11:00:00Z',
        },
      ],
    });
    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ['reviewActivity', 'case-12345678'] });
    });

    expect(await screen.findByText('Stale')).toBeDefined();
    expect(screen.queryByText('Saved and refreshed')).toBeNull();
  });

  it('keeps the note, the focus and no saved claim during a background poll', async () => {
    const { queryClient } = renderF04('/cases/case-12345678');
    const notes = await screen.findByLabelText('Review notes');
    act(() => notes.focus());
    fireEvent.change(notes, { target: { value: 'Draft survives polling' } });
    expect(document.activeElement).toBe(notes);

    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ['caseDetail', 'case-12345678'] });
    });

    expect(reviewNotesValue()).toBe('Draft survives polling');
    expect(document.activeElement).toBe(screen.getByLabelText('Review notes'));
    expect(screen.queryByText('Saved and refreshed')).toBeNull();
  });

  it('never lets a late case A annotation response modify the case B form', async () => {
    const caseA = {
      ...entityCaseDetail,
      case: { ...entityCaseDetail.case, id: 'case-AAAAAAAA', query: 'Case A' },
    };
    const caseB = {
      ...entityCaseDetail,
      case: { ...entityCaseDetail.case, id: 'case-BBBBBBBB', query: 'Case B' },
    };
    apiMocks.getCaseDetail.mockImplementation((caseId: string) =>
      Promise.resolve(caseId === 'case-AAAAAAAA' ? caseA : caseB)
    );
    const pendingPost = deferred<unknown>();
    apiMocks.createCaseAnnotation.mockReturnValue(pendingPost.promise);

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={['/cases/case-AAAAAAAA']}>
          <Routes>
            <Route path="/cases/:id/*" element={<F04CaseSwitcher />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    fireEvent.change(await screen.findByLabelText('Annotation content'), {
      target: { value: 'Draft for case A' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Annotation' }));
    await waitFor(() => expect(writeBanner('pending')).toBeTruthy());

    fireEvent.click(screen.getByRole('link', { name: 'switch-to-b' }));
    expect(await screen.findByRole('heading', { name: 'Case B' })).toBeDefined();
    fireEvent.change(screen.getByLabelText('Annotation content'), {
      target: { value: 'Draft for case B' },
    });

    await act(async () => {
      pendingPost.resolve({ id: 'annotation-a' });
    });
    await new Promise((resolve) => setTimeout(resolve, 60));

    expect(annotationContentValue()).toBe('Draft for case B');
    expect(screen.queryByText('Saved and refreshed')).toBeNull();
    expect(apiMocks.createCaseAnnotation).toHaveBeenCalledTimes(1);
    expect(apiMocks.createCaseAnnotation.mock.calls[0][0]).toBe('case-AAAAAAAA');
  });

  // R01: an acknowledged-but-unrefreshed write may never be POSTed again.
  it('never re-POSTs an acknowledged annotation whose refresh failed', async () => {
    apiMocks.getReviewActivityForCase
      .mockResolvedValueOnce(emptyActivity)
      .mockRejectedValueOnce(new Error('refresh read failed'));

    renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Annotation content'), {
      target: { value: 'Acked annotation draft' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Annotation' }));

    expect(await screen.findByText('Accepted; refresh failed')).toBeDefined();
    expect(apiMocks.createCaseAnnotation).toHaveBeenCalledTimes(1);

    const save = screen.getByRole('button', { name: 'Save Annotation' });
    expect(save.hasAttribute('disabled')).toBe(true);
    fireEvent.click(save);
    fireEvent.click(save);
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(apiMocks.createCaseAnnotation).toHaveBeenCalledTimes(1);
    expect(annotationContentValue()).toBe('Acked annotation draft');
  });

  it('sends one annotation POST for two dispatches in the same tick', async () => {
    const pendingPost = deferred<unknown>();
    apiMocks.createCaseAnnotation.mockReturnValue(pendingPost.promise);

    renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Annotation content'), {
      target: { value: 'Rapid double click draft' },
    });

    const save = screen.getByRole('button', { name: 'Save Annotation' });
    act(() => {
      save.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      save.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(apiMocks.createCaseAnnotation).toHaveBeenCalledTimes(1);
    await act(async () => {
      pendingPost.resolve({ id: 'annotation-rapid' });
    });
  });

  it('blocks every review decision after an acknowledged write whose read failed', async () => {
    apiMocks.getReviewActivityForCase
      .mockResolvedValueOnce(emptyActivity)
      .mockRejectedValueOnce(new Error('refresh read failed'));

    renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Review notes'), {
      target: { value: 'Acked review rationale' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(await screen.findByText('Accepted; refresh failed')).toBeDefined();
    expect(apiMocks.submitCaseReviewAction).toHaveBeenCalledTimes(1);

    for (const label of ['Approve', 'Action Required', 'Reject']) {
      const button = screen.getByRole('button', { name: label });
      expect(button.hasAttribute('disabled')).toBe(true);
      fireEvent.click(button);
    }
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(apiMocks.submitCaseReviewAction).toHaveBeenCalledTimes(1);
    expect(reviewNotesValue()).toBe('Acked review rationale');

    // The unresolved review form never disables the independent annotation form.
    fireEvent.change(screen.getByLabelText('Annotation content'), {
      target: { value: 'Independent annotation draft' },
    });
    expect(screen.getByRole('button', { name: 'Save Annotation' }).hasAttribute('disabled')).toBe(false);
  });

  it('treats a 5xx as an unknown outcome that needs a read plus one explicit confirmation', async () => {
    apiMocks.submitCaseReviewAction.mockRejectedValueOnce(new ApiError('gateway timeout', 502));

    renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Review notes'), {
      target: { value: 'Maybe recorded rationale' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

    expect(await screen.findByText('Outcome unknown')).toBeDefined();
    expect(screen.queryByText('Rejected by the server')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Confirm retry' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Approve' }).hasAttribute('disabled')).toBe(true);

    // An unsuccessful reconciliation does not unlock the form.
    apiMocks.getReviewActivityForCase.mockRejectedValueOnce(new Error('reconcile read failed'));
    fireEvent.click(screen.getByRole('button', { name: 'Reconcile with read (GET)' }));
    expect(await screen.findByText(/Reconciliation read failed/)).toBeDefined();
    expect(screen.getByRole('button', { name: 'Approve' }).hasAttribute('disabled')).toBe(true);
    expect(apiMocks.submitCaseReviewAction).toHaveBeenCalledTimes(1);

    // A successful read reconciles but stays inconclusive.
    fireEvent.click(screen.getByRole('button', { name: 'Reconcile with read (GET)' }));
    expect(await screen.findByText('Read refreshed — still inconclusive')).toBeDefined();
    expect(screen.getByRole('button', { name: 'Approve' }).hasAttribute('disabled')).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(apiMocks.submitCaseReviewAction).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Confirm retry' }));
    await waitFor(() => expect(apiMocks.submitCaseReviewAction).toHaveBeenCalledTimes(2));
    expect(apiMocks.submitCaseReviewAction.mock.calls[1]).toEqual([
      'case-12345678',
      'approve',
      'Maybe recorded rationale',
    ]);
  });

  it('does not claim a save when the ack cannot identify the recorded annotation', async () => {
    apiMocks.createCaseAnnotation.mockResolvedValueOnce({});

    renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Annotation content'), {
      target: { value: 'Unidentifiable ack draft' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Annotation' }));

    expect(await screen.findByText('Outcome unknown')).toBeDefined();
    expect(screen.queryByText('Saved and refreshed')).toBeNull();
    expect(screen.getByRole('button', { name: 'Save Annotation' }).hasAttribute('disabled')).toBe(true);
    expect(annotationContentValue()).toBe('Unidentifiable ack draft');
    expect(apiMocks.createCaseAnnotation).toHaveBeenCalledTimes(1);
  });

  it('keeps the known 404 a rejection, not an unknown outcome', async () => {
    apiMocks.createCaseAnnotation.mockRejectedValueOnce(
      new ApiError('Case case-12345678 not found', 404)
    );

    renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Annotation content'), {
      target: { value: 'Rejected draft' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Annotation' }));

    expect(await screen.findByText('Rejected by the server')).toBeDefined();
    expect(screen.queryByText('Outcome unknown')).toBeNull();
    expect(screen.getByRole('button', { name: 'Save Annotation' }).hasAttribute('disabled')).toBe(false);
  });

  it('leaves edits typed after an acknowledgement untouched when the refresh recovers', async () => {
    apiMocks.getReviewActivityForCase
      .mockResolvedValueOnce(emptyActivity)
      .mockRejectedValueOnce(new Error('refresh read failed'));

    renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Review notes'), {
      target: { value: 'Submitted rationale' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(await screen.findByText('Accepted; refresh failed')).toBeDefined();

    fireEvent.change(screen.getByLabelText('Review notes'), {
      target: { value: 'Late edit after acknowledgement' },
    });
    apiMocks.getReviewActivityForCase.mockResolvedValue(emptyActivity);
    fireEvent.click(screen.getByRole('button', { name: 'Retry refresh (GET)' }));

    expect(await screen.findByText('Saved and refreshed')).toBeDefined();
    expect(reviewNotesValue()).toBe('Late edit after acknowledgement');
  });

  it('keeps an unresolved annotation lock across a same-case tab switch', async () => {
    apiMocks.getReviewActivityForCase
      .mockResolvedValueOnce(emptyActivity)
      .mockRejectedValueOnce(new Error('refresh read failed'));

    renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Annotation content'), {
      target: { value: 'Acked annotation stays locked' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Annotation' }));
    expect(await screen.findByText('Accepted; refresh failed')).toBeDefined();

    const nav = await screen.findByRole('navigation', { name: 'Case views' });
    const exceptionsLink = Array.from(nav.querySelectorAll('a')).find((link) =>
      link.textContent?.includes('Exceptions')
    );
    fireEvent.click(exceptionsLink!);
    expect(await screen.findByRole('heading', { name: 'Exception Queue' })).toBeDefined();

    const backNav = await screen.findByRole('navigation', { name: 'Case views' });
    const overviewLink = Array.from(backNav.querySelectorAll('a')).find((link) =>
      link.textContent?.includes('Overview')
    );
    fireEvent.click(overviewLink!);

    expect(await screen.findByText('Accepted; refresh failed')).toBeDefined();
    expect(screen.getByRole('button', { name: 'Save Annotation' }).hasAttribute('disabled')).toBe(true);
    expect(screen.getByRole('button', { name: 'Retry refresh (GET)' })).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Save Annotation' }));
    expect(apiMocks.createCaseAnnotation).toHaveBeenCalledTimes(1);
    expect(annotationContentValue()).toBe('Acked annotation stays locked');
  });

  it('refuses a confirmed annotation retry when the recorded target left the case', async () => {
    apiMocks.createCaseAnnotation.mockRejectedValueOnce(new Error('Failed to fetch'));

    renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Annotation target type'), {
      target: { value: 'claim' },
    });
    fireEvent.change(screen.getByLabelText('Annotation target'), {
      target: { value: 'claim-current' },
    });
    fireEvent.change(screen.getByLabelText('Annotation content'), {
      target: { value: 'Claim annotation draft' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save Annotation' }));
    expect(await screen.findByText('Outcome unknown')).toBeDefined();

    // The reconciliation read no longer offers the submitted claim as a target.
    apiMocks.getCaseDetail.mockResolvedValue({
      ...entityCaseDetail,
      tabs: { ...entityCaseDetail.tabs, claims: [] },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Reconcile with read (GET)' }));
    expect(await screen.findByText('Read refreshed — still inconclusive')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: 'Confirm retry' }));
    expect(await screen.findByText(/no longer an annotatable entity/)).toBeDefined();
    expect(apiMocks.createCaseAnnotation).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Save Annotation' }).hasAttribute('disabled')).toBe(true);
  });
});

describe('CaseIntelligenceCenter evaluation reader (F04)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCaseStore.getState().clearActiveCase();
    window.sessionStorage.clear();
    apiMocks.getCaseDetail.mockResolvedValue(entityCaseDetail);
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims: [], narratives: [] });
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);
    apiMocks.getReportForCase.mockResolvedValue({
      status: 'pending',
      markdownPath: null,
      markdownContent: null,
      manifestPath: null,
    });
    apiMocks.getReviewActivityForCase.mockResolvedValue(emptyActivity);
    apiMocks.submitCaseReviewAction.mockResolvedValue(entityCaseDetail.case);
    apiMocks.createCaseAnnotation.mockResolvedValue({ id: 'annotation-new' });
  });

  it('renders "No saved evaluation" for latest:null without calling any write', async () => {
    apiMocks.getEvaluationForCase.mockResolvedValue({ latest: null, history: [] });

    renderF04('/cases/case-12345678');

    expect(await screen.findByText('No saved evaluation')).toBeDefined();
    expect(apiMocks.getEvaluationForCase).toHaveBeenCalled();
    expect(apiMocks.submitCaseReviewAction).not.toHaveBeenCalled();
    expect(apiMocks.createCaseAnnotation).not.toHaveBeenCalled();
  });

  it('renders an evaluation read error distinctly from an empty evaluation', async () => {
    apiMocks.getEvaluationForCase.mockRejectedValue(new Error('eval read failed'));

    renderF04('/cases/case-12345678');

    expect(await screen.findByText('Evaluation unavailable')).toBeDefined();
    expect(screen.getByText('eval read failed')).toBeDefined();
    expect(screen.queryByText('No saved evaluation')).toBeNull();
  });

  it('renders a real score of 0 as "0"', async () => {
    apiMocks.getEvaluationForCase.mockResolvedValue({
      latest: {
        id: 'eval-1',
        status: 'complete',
        evaluationKind: 'case',
        summary: { overall_score: 0 },
        metrics: {},
        createdAt: '2026-03-19T10:00:00Z',
      },
      history: [],
    });

    renderF04('/cases/case-12345678');

    const snapshot = await screen.findByTestId('evaluation-snapshot');
    expect(within(snapshot).getByText('0')).toBeDefined();
    expect(within(snapshot).queryByText('Pending')).toBeNull();
    expect(screen.queryByText('No saved evaluation')).toBeNull();
  });
});

describe('CaseIntelligenceCenter annotation targeting and audit partition (F04)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCaseStore.getState().clearActiveCase();
    window.sessionStorage.clear();
    apiMocks.getCaseDetail.mockResolvedValue(entityCaseDetail);
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims: [], narratives: [] });
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);
    apiMocks.getReportForCase.mockResolvedValue({
      status: 'pending',
      markdownPath: null,
      markdownContent: null,
      manifestPath: null,
    });
    apiMocks.getEvaluationForCase.mockResolvedValue({ latest: null, history: [] });
    apiMocks.getReviewActivityForCase.mockResolvedValue(emptyActivity);
    apiMocks.createCaseAnnotation.mockResolvedValue({ id: 'annotation-new' });
  });

  it('offers only current-case target types and entities, never free text', async () => {
    renderF04('/cases/case-12345678');

    const typeSelect = await screen.findByLabelText('Annotation target type');
    const typeLabels = Array.from(typeSelect.querySelectorAll('option')).map(
      (option) => option.textContent
    );
    expect(typeLabels).toEqual(['Case', 'Claim', 'Evidence', 'Exception', 'Narrative']);
    expect(typeLabels).not.toContain('Citation');
    expect(typeLabels).not.toContain('Capture');
    expect(screen.queryByPlaceholderText('Target ID')).toBeNull();

    fireEvent.change(typeSelect, { target: { value: 'claim' } });
    const targetSelect = screen.getByLabelText('Annotation target');
    const claimOptions = Array.from(targetSelect.querySelectorAll('option'));
    expect(claimOptions.map((option) => option.getAttribute('value'))).toEqual([
      '',
      'claim-current',
      'claim-frozen',
    ]);
    expect(claimOptions.some((option) => option.textContent?.includes('Current-case claim'))).toBe(true);
    const frozenOption = claimOptions.find(
      (option) => option.getAttribute('value') === 'claim-frozen'
    );
    expect(frozenOption?.hasAttribute('disabled')).toBe(true);
    expect(frozenOption?.textContent).toContain('frozen');
  });

  it('says so when a target type has no current-case entities instead of offering free text', async () => {
    apiMocks.getCaseDetail.mockResolvedValue({
      ...entityCaseDetail,
      tabs: { ...entityCaseDetail.tabs, narratives: [] },
    });

    renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Annotation target type'), {
      target: { value: 'narrative' },
    });

    const problem = await screen.findByTestId('annotation-target-problem');
    expect(problem.textContent).toContain('No narrative records exist in this case');
    expect(screen.queryByPlaceholderText('Target ID')).toBeNull();
  });

  it('turns a selection that left the current case read-only with no fake target', async () => {
    const { queryClient } = renderF04('/cases/case-12345678');
    fireEvent.change(await screen.findByLabelText('Annotation target type'), {
      target: { value: 'claim' },
    });
    fireEvent.change(screen.getByLabelText('Annotation target'), {
      target: { value: 'claim-current' },
    });
    fireEvent.change(screen.getByLabelText('Annotation content'), {
      target: { value: 'Draft for a claim' },
    });

    apiMocks.getCaseDetail.mockResolvedValue({
      ...entityCaseDetail,
      tabs: { ...entityCaseDetail.tabs, claims: [] },
    });
    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ['caseDetail', 'case-12345678'] });
    });

    const problem = await screen.findByTestId('annotation-target-problem');
    expect(problem.textContent).toContain('not part of the current case');
    expect(screen.getByRole('button', { name: 'Save Annotation' }).hasAttribute('disabled')).toBe(true);
  });

  it('partitions human notes from mirrored annotation:* audit entries', async () => {
    apiMocks.getReviewActivityForCase.mockResolvedValue({
      annotations: [
        {
          id: 'annotation-1',
          targetType: 'claim',
          targetId: 'claim-current',
          annotationType: 'comment',
          author: 'operator',
          content: 'Mirror annotation content',
          metadata: {},
          createdAt: '2026-03-19T10:00:00Z',
        },
      ],
      auditEntries: [
        {
          id: 'audit-mirror',
          actionType: 'annotation:create',
          targetType: 'claim',
          targetId: 'claim-current',
          actor: 'operator',
          rationale: null,
          metadata: {},
          createdAt: '2026-03-19T10:00:00Z',
        },
        {
          id: 'audit-review',
          actionType: 'review:approve',
          targetType: 'case',
          targetId: 'case-12345678',
          actor: 'operator',
          rationale: 'Approved',
          metadata: {},
          createdAt: '2026-03-19T09:00:00Z',
        },
      ],
    });

    renderF04('/cases/case-12345678');

    const humanSection = await screen.findByTestId('human-notes');
    const auditSection = await screen.findByTestId('technical-audit');

    // The annotation appears exactly once, as a human note.
    expect(humanSection.querySelectorAll('[data-annotation-id]')).toHaveLength(1);
    expect(within(humanSection).getByText('Human note')).toBeDefined();
    expect(within(humanSection).getByText('Mirror annotation content')).toBeDefined();
    expect(screen.getAllByText('Mirror annotation content')).toHaveLength(1);

    // Its mirror appears once, as technical audit, never as a second human note.
    expect(auditSection.querySelectorAll('[data-audit-entry]')).toHaveLength(2);
    expect(within(auditSection).getAllByText('Technical audit', { selector: 'span' })).toHaveLength(2);
    expect(within(auditSection).getByText('annotation:create')).toBeDefined();
    expect(within(auditSection).getByText('review:approve')).toBeDefined();

    expect(screen.getByText('Human notes')).toBeDefined();
    expect(screen.getByText('Technical audit', { selector: 'h4' })).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// R02 — historical context in deep links
// ---------------------------------------------------------------------------

const r02Source = {
  id: 'ev-example',
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

const pinnedEvidenceDetail = {
  ...r02Source,
  currentCaptureId: null,
  captures: [],
  relatedClaims: [],
};

const frozenCitation = {
  id: 'cite-example',
  caseId: 'case-12345678',
  captureId: 'cap-example',
  evidenceId: 'ev-example',
  originalClaimId: 'claim-gone',
  claimSignature: 'sig-frozen',
  claimText: 'Frozen claim text',
  relationship: 'reported_by',
  quote: 'quoted text',
  startChar: 0,
  endChar: 11,
  alignmentStatus: 'exact',
  alignmentVersion: 'v1',
  assessmentOrigin: 'collector',
  assessmentVersion: 'v1',
  assessmentMetadata: {},
  recordedAt: '2026-11-01T10:00:00Z',
  liveClaimPresent: false,
  liveClaimId: null,
  evidence: r02Source,
  capture: {
    id: 'cap-example',
    evidenceId: 'ev-example',
    textSha256: 'sha-1',
    normalizedTextSha256: 'nsha-1',
    normalizationVersion: 'v1',
    captureKind: 'live',
    recordedAt: '2026-11-01T10:00:00Z',
    observedAt: '2026-11-01T09:00:00Z',
    metadata: {},
    charLength: 11,
    isCurrent: true,
    caseId: 'case-12345678',
  },
};

const R02LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
};

function renderR02(initialEntry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route
            path="/cases/:id/*"
            element={
              <>
                <R02LocationProbe />
                <CaseIntelligenceCenter />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const r02Location = () => screen.getByTestId('location').textContent;

/** Let gated renders settle so a late fetch or redirect would be visible. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('CaseIntelligenceCenter historical deep links (R02)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    useCaseStore.getState().clearActiveCase();

    apiMocks.getCaseDetail.mockResolvedValue(baseCaseDetail);
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({ claims: [], narratives: [] });
    apiMocks.getEvidenceForCase.mockResolvedValue([]);
    apiMocks.getExceptionsForCase.mockResolvedValue([]);
    apiMocks.getPartiesForCase.mockResolvedValue([]);
    apiMocks.getTimelineForCase.mockResolvedValue([]);
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);
    apiMocks.getReportForCase.mockResolvedValue({
      status: 'pending',
      markdownPath: null,
      markdownContent: null,
      manifestPath: null,
    });
    apiMocks.getEvaluationForCase.mockResolvedValue({ latest: null, history: [] });
    apiMocks.getReviewActivityForCase.mockResolvedValue({ auditEntries: [], annotations: [] });
    apiMocks.getInvestigationRuns.mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
      hasMore: false,
    });
    apiMocks.getEvidenceDetail.mockResolvedValue(pinnedEvidenceDetail);
    apiMocks.getClaimDetail.mockResolvedValue({
      id: 'claim-frozen',
      caseId: 'case-12345678',
      eventId: null,
      claimText: 'Frozen claim text',
      claimSignature: 'sig-frozen',
      verificationStatus: 'unknown',
      verificationProvenance: 'unknown',
      type: 'fact',
      controversyScore: null,
      narrativeClusterId: null,
      partyPositions: {},
      counts: { supportCount: 0, opposeCount: 0, sourceDiversityCount: 0, evidenceCount: 0 },
      passages: [],
    });
    apiMocks.getCitationDetail.mockResolvedValue(frozenCitation);
    apiMocks.getCaptureWindow.mockResolvedValue({
      captureId: 'cap-example',
      evidenceId: 'ev-example',
      start: 0,
      length: 11,
      totalLength: 11,
      text: 'quoted text',
      textSha256: 'sha-1',
      captureKind: 'live',
      recordedAt: '2026-11-01T10:00:00Z',
      observedAt: '2026-11-01T09:00:00Z',
      metadata: {},
    });
  });

  it('keeps the combined Timeline deep link, its snapshot and its explicit escape', async () => {
    const pinned =
      '/cases/case-12345678/timeline?snapshot=snap-example&citation=cite-example';
    renderR02(pinned);

    expect(await screen.findByText('Unsupported historical view')).toBeDefined();
    await settle();

    // The explicit pin is never stripped to reveal unpinned Evidence.
    expect(r02Location()).toBe(pinned);
    expect(apiMocks.getTimelineForCase).not.toHaveBeenCalled();
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
    expect(apiMocks.getEvidenceForCase).not.toHaveBeenCalled();
    expect(apiMocks.getEvidenceDetail).not.toHaveBeenCalled();

    // The escape removes the pin and cannot resurrect the citation redirect.
    fireEvent.click(screen.getByRole('link', { name: 'Open current Timeline' }));
    expect(await screen.findByRole('heading', { name: 'Investigation Timeline' })).toBeDefined();
    await waitFor(() => expect(r02Location()).toBe('/cases/case-12345678/timeline'));
    expect(apiMocks.getTimelineForCase).toHaveBeenCalledTimes(1);
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
    expect(screen.queryByText('Unsupported historical view')).toBeNull();
  });

  it('applies the same gate to the case root and to claims', async () => {
    const root = renderR02('/cases/case-12345678?snapshot=snap-example&citation=cite-example');
    expect(await screen.findByText('Unsupported historical view')).toBeDefined();
    await settle();
    expect(r02Location()).toBe('/cases/case-12345678?snapshot=snap-example&citation=cite-example');
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('link', { name: 'Open current Overview' }));
    expect(await screen.findByRole('heading', { name: 'Operator Commands' })).toBeDefined();
    await waitFor(() => expect(r02Location()).toBe('/cases/case-12345678'));
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
    root.unmount();

    // Claims keeps only its own valid browse state, never the citation.
    renderR02(
      '/cases/case-12345678/claims?claimStatus=contested&snapshot=snap-example&citation=cite-example'
    );
    expect(await screen.findByText('Unsupported historical view')).toBeDefined();
    await settle();
    expect(apiMocks.getClaimsOverviewForCase).not.toHaveBeenCalled();
    const escape = screen.getByRole('link', { name: 'Open current Claims' });
    expect(escape.getAttribute('href')).toBe('/cases/case-12345678/claims?claimStatus=contested');

    fireEvent.click(escape);
    expect(await screen.findByRole('heading', { name: 'Primary Claims Mapping' })).toBeDefined();
    await waitFor(() =>
      expect(r02Location()).toBe('/cases/case-12345678/claims?claimStatus=contested')
    );
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
  });

  it('reads pinned evidence detail from the snapshot without loading the gallery', async () => {
    renderR02('/cases/case-12345678/evidence?snapshot=snap-example&evidence=ev-example');

    expect(await screen.findByText('Historical evidence view')).toBeDefined();
    await waitFor(() =>
      expect(apiMocks.getEvidenceDetail).toHaveBeenCalledWith(
        'case-12345678',
        'ev-example',
        'snap-example'
      )
    );
    expect(apiMocks.getEvidenceForCase).not.toHaveBeenCalled();
    expect(screen.queryByRole('heading', { name: /Evidence Gallery/ })).toBeNull();
    expect(screen.queryByText(/Evidence Gallery/)).toBeNull();
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
  });

  it('shows the pinned observation without a selection and offers a current escape', async () => {
    renderR02('/cases/case-12345678/evidence?snapshot=snap-example');

    expect(await screen.findByText('Historical evidence view')).toBeDefined();
    expect(screen.getByText(/No claim or evidence item is selected/)).toBeDefined();
    await settle();
    expect(apiMocks.getEvidenceForCase).not.toHaveBeenCalled();
    expect(apiMocks.getEvidenceDetail).not.toHaveBeenCalled();

    const escape = screen.getByRole('link', { name: 'Open current Evidence' });
    expect(escape.getAttribute('href')).toBe('/cases/case-12345678/evidence');
    fireEvent.click(escape);
    await waitFor(() => expect(apiMocks.getEvidenceForCase).toHaveBeenCalledTimes(1));
    expect(r02Location()).toBe('/cases/case-12345678/evidence');
  });

  it('never falls back to current gallery data when a pinned entity is absent', async () => {
    apiMocks.getEvidenceDetail.mockRejectedValue(
      new ApiError('Evidence not found in snapshot', 404)
    );
    renderR02('/cases/case-12345678/evidence?snapshot=snap-example&evidence=ev-missing');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent ?? '').toMatch(/may not be present in the selected snapshot/i);
    await settle();
    expect(apiMocks.getEvidenceDetail).toHaveBeenCalledTimes(1);
    expect(apiMocks.getEvidenceDetail).toHaveBeenCalledWith(
      'case-12345678',
      'ev-missing',
      'snap-example'
    );
    expect(apiMocks.getEvidenceForCase).not.toHaveBeenCalled();
  });

  it('resolves a pinned claim through the snapshot-aware claim reader', async () => {
    renderR02('/cases/case-12345678/evidence?snapshot=snap-example&claim=claim-frozen');

    expect(await screen.findByText('Historical evidence view')).toBeDefined();
    await waitFor(() =>
      expect(apiMocks.getClaimDetail).toHaveBeenCalledWith(
        'case-12345678',
        'claim-frozen',
        'snap-example'
      )
    );
    expect(screen.getAllByText('Frozen claim text').length).toBeGreaterThan(0);
    expect(apiMocks.getEvidenceForCase).not.toHaveBeenCalled();
  });

  it('refuses a snapshot plus citation selector conflict until the operator chooses', async () => {
    const conflict =
      '/cases/case-12345678/evidence?snapshot=snap-example&citation=cite-example&evidence=ev-example';
    const view = renderR02(conflict);

    expect(await screen.findByText('Snapshot and citation selectors conflict')).toBeDefined();
    await settle();
    // Neither reader is allowed to answer for a link that names both selectors.
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
    expect(apiMocks.getEvidenceDetail).not.toHaveBeenCalled();
    expect(apiMocks.getEvidenceForCase).not.toHaveBeenCalled();
    expect(r02Location()).toBe(conflict);

    const keepSnapshot = screen.getByRole('link', { name: /Keep snapshot/ });
    expect(keepSnapshot.getAttribute('href')).toBe(
      '/cases/case-12345678/evidence?evidence=ev-example&snapshot=snap-example'
    );
    const openCitation = screen.getByRole('link', { name: 'Open frozen citation by ID' });
    expect(openCitation.getAttribute('href')).toBe(
      '/cases/case-12345678/evidence?citation=cite-example'
    );

    fireEvent.click(keepSnapshot);
    await waitFor(() =>
      expect(apiMocks.getEvidenceDetail).toHaveBeenCalledWith(
        'case-12345678',
        'ev-example',
        'snap-example'
      )
    );
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
    expect(apiMocks.getEvidenceForCase).not.toHaveBeenCalled();
    view.unmount();
  });

  it('resolves the citation half of a selector conflict only when chosen', async () => {
    const conflict =
      '/cases/case-12345678/evidence?snapshot=snap-example&citation=cite-example&evidence=ev-example';
    renderR02(conflict);

    fireEvent.click(await screen.findByRole('link', { name: 'Open frozen citation by ID' }));
    await waitFor(() =>
      expect(apiMocks.getCitationDetail).toHaveBeenCalledWith('case-12345678', 'cite-example')
    );
    expect(apiMocks.getCitationDetail).toHaveBeenCalledTimes(1);
    expect(apiMocks.getEvidenceDetail).not.toHaveBeenCalled();
    expect(r02Location()).toBe('/cases/case-12345678/evidence?citation=cite-example');
  });

  it('keeps Changes on a pinned snapshot and drops a stray citation', async () => {
    renderR02(
      '/cases/case-12345678/changes?snapshot=snap-example&claim=claim-frozen&citation=cite-example'
    );

    expect(
      await screen.findByRole('heading', { name: 'Changes between observations' })
    ).toBeDefined();
    await waitFor(() =>
      expect(r02Location()).toBe(
        '/cases/case-12345678/changes?claim=claim-frozen&snapshot=snap-example'
      )
    );
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
    expect(apiMocks.getEvidenceForCase).not.toHaveBeenCalled();
    expect(screen.queryByText('Unsupported historical view')).toBeNull();
    // The dropped citation never turns into a redirect to Evidence.
    expect(r02Location()).not.toContain('citation');
  });

  it('keeps an incomplete ad-hoc pair in Changes when a citation is attached', async () => {
    renderR02(
      '/cases/case-12345678/changes?mode=ad_hoc&baselineSnapshot=snap-a&citation=cite-example'
    );

    const panel = await screen.findByRole('region', { name: /ad-hoc snapshot comparison/i });
    expect(within(panel).getByText('Two snapshots are required')).toBeDefined();
    await waitFor(() =>
      expect(r02Location()).toBe(
        '/cases/case-12345678/changes?mode=ad_hoc&baselineSnapshot=snap-a'
      )
    );
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
    expect(screen.queryByText('Unsupported historical view')).toBeNull();
  });

  it('keeps Changes on an explicit baseline/target pair without a mode and drops a stray citation', async () => {
    renderR02(
      '/cases/case-12345678/changes?baselineSnapshot=snap-a&targetSnapshot=snap-b&citation=cite-example'
    );

    // The pair is the operator's own historical context even without `mode=ad_hoc`.
    expect(
      await screen.findByRole('heading', { name: 'Changes between observations' })
    ).toBeDefined();
    await waitFor(() =>
      expect(r02Location()).toBe(
        '/cases/case-12345678/changes?baselineSnapshot=snap-a&targetSnapshot=snap-b'
      )
    );
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
    expect(apiMocks.getEvidenceForCase).not.toHaveBeenCalled();
    expect(r02Location()).not.toContain('citation');
  });

  it('keeps Changes on a single explicit selector without a mode so it can be completed', async () => {
    renderR02('/cases/case-12345678/changes?baselineSnapshot=snap-a&citation=cite-example');

    expect(
      await screen.findByRole('heading', { name: 'Changes between observations' })
    ).toBeDefined();
    await waitFor(() =>
      expect(r02Location()).toBe('/cases/case-12345678/changes?baselineSnapshot=snap-a')
    );
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
    expect(apiMocks.getEvidenceForCase).not.toHaveBeenCalled();
  });

  it('still redirects a bare citation-only link on Changes to Evidence once', async () => {
    renderR02('/cases/case-12345678/changes?citation=cite-example');

    await waitFor(() =>
      expect(r02Location()).toBe('/cases/case-12345678/evidence?citation=cite-example')
    );
    await waitFor(() =>
      expect(apiMocks.getCitationDetail).toHaveBeenCalledWith('case-12345678', 'cite-example')
    );
    expect(apiMocks.getCitationDetail).toHaveBeenCalledTimes(1);
  });

  it('shows an invalid-selector state for an empty snapshot instead of live evidence', async () => {
    renderR02('/cases/case-12345678/evidence?snapshot=&evidence=ev-example');

    expect(await screen.findByText('Invalid historical selector')).toBeDefined();
    await settle();
    expect(apiMocks.getEvidenceForCase).not.toHaveBeenCalled();
    expect(apiMocks.getEvidenceDetail).not.toHaveBeenCalled();
    expect(screen.getByRole('link', { name: 'Open current Evidence' }).getAttribute('href')).toBe(
      '/cases/case-12345678/evidence?evidence=ev-example'
    );
  });

  it('refuses to choose between conflicting duplicate snapshot selectors', async () => {
    renderR02('/cases/case-12345678/evidence?snapshot=snap-a&snapshot=snap-b&evidence=ev-example');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent ?? '').toContain('Invalid historical selector');
    expect(alert.textContent ?? '').toContain('snap-a');
    expect(alert.textContent ?? '').toContain('snap-b');
    await settle();
    expect(apiMocks.getEvidenceForCase).not.toHaveBeenCalled();
    expect(apiMocks.getEvidenceDetail).not.toHaveBeenCalled();
  });

  it('never redirects on an empty citation selector', async () => {
    renderR02('/cases/case-12345678/claims?citation=');

    expect(await screen.findByRole('heading', { name: 'Primary Claims Mapping' })).toBeDefined();
    await settle();
    // A blank selector is dropped by the allowlist, never encoded into a redirect.
    await waitFor(() => expect(r02Location()).toBe('/cases/case-12345678/claims'));
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
  });

  it('still resolves a legacy citation-only link once, with an encoded ID', async () => {
    renderR02('/cases/case-12345678/claims?citation=cite%2Fexample%20x');

    await waitFor(() =>
      expect(r02Location()).toBe(
        '/cases/case-12345678/evidence?citation=cite%2Fexample%20x'
      )
    );
    await waitFor(() =>
      expect(apiMocks.getCitationDetail).toHaveBeenCalledWith('case-12345678', 'cite/example x')
    );
    expect(apiMocks.getCitationDetail).toHaveBeenCalledTimes(1);
    // Legacy behaviour: a citation-only link lands on the current Evidence view.
    expect(apiMocks.getEvidenceDetail).not.toHaveBeenCalled();
  });
});
