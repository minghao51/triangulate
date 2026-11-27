import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import ChangesTab from './ChangesTab';
import { EvidenceInspector } from '../../components/inspector/EvidenceInspector';
import { ApiError } from '../../services/api-error';
import type {
  CaptureWindow,
  ChangeItem,
  CitationDetail,
  ClaimDetail,
  EvidenceDetail,
  InvestigationRun,
  RunChanges,
  SnapshotComparison,
  SnapshotComparisonItem,
  SnapshotComparisonRef,
  SnapshotComparisonSide,
  SnapshotComparisonUnavailableReason,
} from '../../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getInvestigationRuns: vi.fn(),
  getInvestigationRun: vi.fn(),
  getRunChanges: vi.fn(),
  getClaimDetail: vi.fn(),
  getEvidenceDetail: vi.fn(),
  getCitationDetail: vi.fn(),
  getCaptureWindow: vi.fn(),
  getSnapshotComparison: vi.fn(),
}));

vi.mock('../../services/api', () => apiMocks);

const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
};

function makeRun(overrides: Partial<InvestigationRun> = {}): InvestigationRun {
  return {
    id: 'run-2',
    caseId: 'case-1',
    sequence: 2,
    trigger: 'rerun',
    requestedStartStage: 'RETRIEVE',
    status: 'succeeded',
    coverage: 'complete_requested_scope',
    startedAt: '2026-03-04T10:00:00Z',
    completedAt: '2026-03-04T10:05:00Z',
    predecessorRunId: 'run-1',
    baselineSnapshotId: 'snap-1',
    resultSnapshotId: 'snap-2',
    snapshotId: 'snap-2',
    errorMessage: null,
    ...overrides,
  };
}

function makeRunList(items: InvestigationRun[], total = items.length) {
  return { items, total, limit: 50, offset: 0, hasMore: total > items.length };
}

function makeChange(overrides: Partial<ChangeItem> = {}): ChangeItem {
  return {
    type: 'claim_added',
    entityType: 'claim',
    entityId: 'claim-new',
    before: null,
    after: { text: 'A newly recorded assertion.', claimSignature: 'sig-new' },
    originRunId: 'run-1',
    observedByRunId: 'run-2',
    observedAt: '2026-03-04T10:05:00Z',
    ...overrides,
  };
}

function makeChanges(overrides: Partial<RunChanges> = {}): RunChanges {
  return {
    availability: 'ready',
    baselineSnapshotId: 'snap-1',
    targetSnapshotId: 'snap-2',
    coverage: 'complete_requested_scope',
    coverageNote: null,
    items: [],
    total: 0,
    limit: 25,
    offset: 0,
    hasMore: false,
    ...overrides,
  };
}

function renderTab(entry = '/cases/case-1/changes') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route
            path="/cases/:id/changes"
            element={
              <>
                <LocationProbe />
                <ChangesTab caseId="case-1" />
              </>
            }
          />
          <Route path="/cases/:id/evidence" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

/** Fixtures for the frozen citation/capture readers hosted by the inspector. */
const evidenceSource = {
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
} as const;

const captureSummary = {
  id: 'cap-1',
  evidenceId: 'ev-1',
  textSha256: 'sha-1',
  normalizedTextSha256: 'nsha-1',
  normalizationVersion: 'v1',
  captureKind: 'live',
  recordedAt: '2026-11-01T10:00:00Z',
  observedAt: '2026-11-01T09:00:00Z',
  metadata: {},
  charLength: 19,
  isCurrent: true,
} as const;

function makeEvidenceDetail(): EvidenceDetail {
  return {
    ...evidenceSource,
    currentCaptureId: 'cap-1',
    captures: [{ ...captureSummary }],
    relatedClaims: [],
  };
}

function makeCitationDetail(): CitationDetail {
  return {
    id: 'cit-1',
    caseId: 'case-1',
    captureId: 'cap-1',
    evidenceId: 'ev-1',
    originalClaimId: 'claim-gone',
    claimSignature: 'sig-frozen',
    claimText: 'Frozen claim text',
    relationship: 'reported_by',
    quote: 'Frozen capture',
    startChar: 0,
    endChar: 14,
    alignmentStatus: 'exact',
    alignmentVersion: 'v1',
    assessmentOrigin: 'collector',
    assessmentVersion: 'v1',
    assessmentMetadata: {},
    recordedAt: '2026-11-01T10:00:00Z',
    liveClaimPresent: false,
    liveClaimId: null,
    evidence: { ...evidenceSource },
    capture: { ...captureSummary },
  };
}

function makeCaptureWindow(): CaptureWindow {
  return {
    captureId: 'cap-1',
    evidenceId: 'ev-1',
    start: 0,
    length: 19,
    totalLength: 19,
    text: 'Frozen capture text',
    textSha256: 'sha-1',
    captureKind: 'live',
    recordedAt: '2026-11-01T10:00:00Z',
    observedAt: '2026-11-01T09:00:00Z',
    metadata: {},
  };
}

function renderInspector(entry: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route
            path="/cases/:id/evidence"
            element={
              <>
                <LocationProbe />
                <EvidenceInspector caseId="case-1" />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function observedRows() {
  return within(screen.getByRole('list', { name: 'Observed changes' })).getAllByRole(
    'listitem'
  );
}

describe('ChangesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getInvestigationRuns.mockResolvedValue(makeRunList([makeRun()]));
    apiMocks.getRunChanges.mockResolvedValue(makeChanges());
    // Out-of-list run IDs are checked through the single-run reader; absence is
    // only proven by its 404, so that is the default for unknown IDs.
    apiMocks.getInvestigationRun.mockRejectedValue(
      new ApiError('Investigation run not found', 404)
    );
  });

  it('pins the newest run into the URL and loads its changes', async () => {
    apiMocks.getInvestigationRuns.mockResolvedValue(
      makeRunList([makeRun({ id: 'run-3', sequence: 3 }), makeRun({ id: 'run-2' })])
    );

    renderTab();

    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain('run=run-3')
    );
    await waitFor(() =>
      expect(apiMocks.getRunChanges).toHaveBeenCalledWith('case-1', 'run-3', {
        limit: 25,
        offset: 0,
      })
    );
  });

  it('replaces an unknown run id in the URL instead of showing another run', async () => {
    apiMocks.getInvestigationRun.mockRejectedValue(
      new ApiError('Investigation run run-missing not found', 404)
    );

    renderTab('/cases/case-1/changes?run=run-missing');

    await waitFor(() =>
      expect(apiMocks.getInvestigationRun).toHaveBeenCalledWith('case-1', 'run-missing')
    );
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain('run=run-2')
    );
    expect(apiMocks.getRunChanges).toHaveBeenCalledWith('case-1', 'run-2', {
      limit: 25,
      offset: 0,
    });
    expect(
      screen.queryByText(/No grouped runs recorded/i)
    ).toBeNull();
  });

  it('keeps an out-of-list run that the single-run reader resolves', async () => {
    // Only the newest run is within the latest-50 list; the permalink targets an
    // older run that the list cannot show but the detail reader still resolves.
    apiMocks.getInvestigationRuns.mockResolvedValue(
      makeRunList([makeRun({ id: 'run-2', sequence: 2 })], 7)
    );
    apiMocks.getInvestigationRun.mockResolvedValue(
      makeRun({ id: 'run-old', sequence: 1, trigger: 'initial' })
    );

    renderTab('/cases/case-1/changes?run=run-old');

    // The resolved out-of-list run is rendered in the run header, not as a
    // selector row (the selector lists only the latest-50 runs).
    expect(
      await screen.findByRole('heading', { name: /Run #1 · Initial run/ })
    ).toBeTruthy();
    expect(apiMocks.getRunChanges).toHaveBeenCalledWith('case-1', 'run-old', {
      limit: 25,
      offset: 0,
    });
    // The selection is legitimate, so the URL is never rewritten to the newest run.
    expect(screen.getByTestId('location').textContent).toContain('run=run-old');
    expect(screen.getByTestId('location').textContent).not.toContain('run=run-2');
    expect(screen.getByText(/Showing the latest 1 of 7 runs/i)).toBeTruthy();
  });

  it('keeps the selected run when the lookup fails and retries it', async () => {
    apiMocks.getInvestigationRuns.mockResolvedValue(
      makeRunList([makeRun({ id: 'run-2', sequence: 2 })])
    );
    apiMocks.getInvestigationRun
      .mockRejectedValueOnce(new ApiError('backend exploded', 500))
      .mockResolvedValueOnce(makeRun({ id: 'run-old', sequence: 1 }));

    renderTab('/cases/case-1/changes?run=run-old');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent ?? '').toMatch(/Could not resolve the selected run/i);
    expect(alert.textContent ?? '').toMatch(/backend exploded/i);
    // A failed lookup is not evidence of absence: no run switch, no changes read.
    expect(screen.getByTestId('location').textContent).toContain('run=run-old');
    expect(apiMocks.getRunChanges).not.toHaveBeenCalled();

    fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

    await waitFor(() =>
      expect(apiMocks.getInvestigationRun).toHaveBeenCalledTimes(2)
    );
    expect(
      await screen.findByRole('heading', { name: /Run #1 · Rerun or resume/ })
    ).toBeTruthy();
    expect(screen.getByTestId('location').textContent).toContain('run=run-old');
    await waitFor(() =>
      expect(apiMocks.getRunChanges).toHaveBeenCalledWith('case-1', 'run-old', {
        limit: 25,
        offset: 0,
      })
    );
  });

  it('labels a first observation as initial rather than a change surge', async () => {
    apiMocks.getRunChanges.mockResolvedValue(
      makeChanges({ availability: 'initial', baselineSnapshotId: null })
    );

    renderTab();

    expect(await screen.findByText('First observation')).toBeTruthy();
    expect(
      screen.getByText(/not a surge of new changes/i)
    ).toBeTruthy();
    expect(screen.queryByText('Unchanged')).toBeNull();
  });

  it('distinguishes a pending run from an empty delta', async () => {
    apiMocks.getInvestigationRuns.mockResolvedValue(
      makeRunList([makeRun({ status: 'running', snapshotId: null })])
    );
    apiMocks.getRunChanges.mockResolvedValue(makeChanges({ availability: 'pending' }));

    renderTab();

    expect(await screen.findByText('Run in progress')).toBeTruthy();
    expect(screen.getByText(/not an empty\s+delta/i)).toBeTruthy();
    expect(screen.queryByText('Unchanged')).toBeNull();
  });

  it('labels a run without a snapshot as unavailable, not empty', async () => {
    apiMocks.getInvestigationRuns.mockResolvedValue(
      makeRunList([
        makeRun({
          status: 'failed',
          snapshotId: null,
          resultSnapshotId: null,
          errorMessage: 'investigation boom',
        }),
      ])
    );
    apiMocks.getRunChanges.mockResolvedValue(makeChanges({ availability: 'unavailable' }));

    renderTab();

    expect(
      await screen.findByText('Historical change data unavailable')
    ).toBeTruthy();
    expect(screen.getByText(/not an empty delta/i)).toBeTruthy();
    expect(
      screen.getByText(/never advances the successful\s+baseline/i)
    ).toBeTruthy();
    expect(screen.getByText(/investigation boom/i)).toBeTruthy();
    expect(screen.queryByText('Unchanged')).toBeNull();
  });

  it('shows partial coverage conspicuously even for an empty delta', async () => {
    apiMocks.getRunChanges.mockResolvedValue(
      makeChanges({
        coverage: 'partial',
        coverageNote:
          'Coverage was partial; changes describe observed data only and do not mean every source was unchanged.',
      })
    );

    renderTab();

    expect(await screen.findByText(/Coverage: Partial coverage/i)).toBeTruthy();
    expect(
      screen.getByText(/every source was\s+unchanged/i)
    ).toBeTruthy();
    expect(screen.getByText('Unchanged')).toBeTruthy();
    expect(
      screen.getByText(/No changes in observed data between these two observations/i)
    ).toBeTruthy();
  });

  it('does not warn about coverage when the requested scope was complete', async () => {
    renderTab();

    expect(await screen.findByText('Unchanged')).toBeTruthy();
    expect(screen.queryByText(/Coverage: /i)).toBeNull();
  });

  it('renders typed changes with before/after values and separate run facts', async () => {
    apiMocks.getRunChanges.mockResolvedValue(
      makeChanges({
        items: [
          makeChange({
            type: 'classification_changed',
            entityId: 'claim-1',
            before: { verificationStatus: 'ALLEGED' },
            after: { verificationStatus: 'CONFIRMED' },
            originRunId: 'run-1',
            observedByRunId: 'run-2',
          }),
          makeChange({
            type: 'review_state_changed',
            entityType: 'review',
            entityId: 'review-1',
            before: { status: 'pending' },
            after: { status: 'approved' },
            originRunId: null,
            observedByRunId: 'run-2',
          }),
        ],
        total: 2,
      })
    );

    renderTab();

    expect(await screen.findByText('Classification changed')).toBeTruthy();
    expect(screen.getByText('Review state changed')).toBeTruthy();
    expect(screen.getByText('ALLEGED')).toBeTruthy();
    expect(screen.getByText('CONFIRMED')).toBeTruthy();
    expect(screen.getAllByText(/Recorded by run/i).length).toBeGreaterThan(0);
    expect(screen.getByText('run-1')).toBeTruthy();
    expect(screen.getByText('origin not recorded')).toBeTruthy();
    expect(screen.getAllByText('run-2')).toHaveLength(2);
    expect(
      screen.getByText(/neither run reference identifies who/i)
    ).toBeTruthy();
    expect(screen.getByTestId('location').textContent).not.toMatch(/changed by/i);
  });

  it('links claims and evidence through the snapshot-aware readers', async () => {
    apiMocks.getRunChanges.mockResolvedValue(
      makeChanges({
        items: [
          makeChange({ type: 'claim_added', entityId: 'claim-new' }),
          makeChange({
            type: 'claim_no_longer_extracted',
            entityId: 'claim-gone',
            before: { text: 'Withdrawn assertion.', claimSignature: 'sig-gone' },
            after: null,
          }),
          makeChange({
            type: 'capture_changed',
            entityType: 'evidence',
            entityId: 'ev-9',
            before: { currentCaptureId: 'cap-old' },
            after: { currentCaptureId: 'cap-new' },
          }),
        ],
        total: 3,
      })
    );

    renderTab();

    const added = await screen.findByRole('link', { name: 'View frozen claim' });
    expect(added.getAttribute('href')).toBe(
      '/cases/case-1/changes?run=run-2&claim=claim-new&snapshot=snap-2'
    );

    const removed = screen.getByRole('link', {
      name: 'View frozen claim (before)',
    });
    expect(removed.getAttribute('href')).toBe(
      '/cases/case-1/changes?run=run-2&claim=claim-gone&snapshot=snap-1'
    );

    const capture = screen.getByRole('link', { name: 'Open frozen evidence' });
    expect(capture.getAttribute('href')).toBe(
      '/cases/case-1/evidence?evidence=ev-9&snapshot=snap-2'
    );

    fireEvent.click(added);
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain('claim=claim-new')
    );
    expect(screen.getByTestId('location').textContent).toContain('snapshot=snap-2');
  });

  it('adds no internal link for link-level changes and no unsafe article link', async () => {
    apiMocks.getRunChanges.mockResolvedValue(
      makeChanges({
        items: [
          makeChange({
            type: 'relationship_changed',
            entityType: 'link',
            entityId: 'link-1',
            before: { relation: 'supports' },
            after: { relation: 'reported_by' },
          }),
          makeChange({
            type: 'article_added',
            entityType: 'article',
            entityId: 'article-1',
            after: {
              title: 'Port Alden report',
              url: 'https://example.com/a',
            },
          }),
          makeChange({
            type: 'article_added',
            entityType: 'article',
            entityId: 'article-2',
            after: { title: 'Unsafe', url: 'javascript:alert(1)' },
          }),
        ],
        total: 3,
      })
    );

    renderTab();

    await screen.findByText('Relationship changed');
    const rows = observedRows();
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).queryByRole('link')).toBeNull();

    const external = within(rows[1]).getByRole('link', { name: 'Open article' });
    expect(external.getAttribute('href')).toBe('https://example.com/a');
    expect(external.getAttribute('target')).toBe('_blank');
    expect(external.getAttribute('rel')).toBe('noopener noreferrer');

    expect(within(rows[2]).queryByRole('link')).toBeNull();
    expect(within(rows[2]).getByText('javascript:alert(1)')).toBeTruthy();
  });

  it('opens a frozen claim that the live case no longer contains', async () => {
    apiMocks.getRunChanges.mockResolvedValue(
      makeChanges({
        items: [
          makeChange({
            type: 'claim_no_longer_extracted',
            entityId: 'claim-gone',
            before: { text: 'Withdrawn assertion.', claimSignature: 'sig-gone' },
            after: null,
          }),
        ],
        total: 1,
      })
    );
    apiMocks.getClaimDetail.mockResolvedValue({
      id: 'claim-gone',
      caseId: 'case-1',
      eventId: 'event-1',
      claimText: 'Withdrawn assertion.',
      claimSignature: 'sig-gone',
      verificationStatus: 'alleged',
      verificationProvenance: 'unknown',
      type: 'allegation',
      controversyScore: 0.4,
      narrativeClusterId: null,
      partyPositions: {},
      counts: {
        supportCount: 1,
        opposeCount: 0,
        sourceDiversityCount: 1,
        evidenceCount: 1,
      },
      passages: [
        {
          id: 'ev-9',
          relation: 'reported_by',
          confidenceScore: null,
          sourceDiversityRank: 1,
          title: 'Port Alden report',
          publisher: 'Example Publisher',
          originUrl: 'https://example.com/a',
          sourceType: 'rss',
          captureId: 'cap-1',
          citationId: null,
          quote: 'Withdrawn assertion.',
          startChar: 4,
          endChar: 23,
          alignmentStatus: 'exact',
          effectiveRelation: 'reported_by',
          assessmentOrigin: 'collector',
          assessmentVersion: 'v1',
          diagnosticReason: null,
        },
      ],
      snapshotId: 'snap-1',
      liveState: {
        present: false,
        claimSignature: null,
        textMatchesSnapshot: null,
        currentCaptureId: null,
        currentCaptureMatchesSnapshot: null,
      },
    } satisfies ClaimDetail);

    renderTab('/cases/case-1/changes?run=run-2&claim=claim-gone&snapshot=snap-1');

    const panel = await screen.findByRole('region', { name: 'Frozen claim' });
    await within(panel).findByText(/live case no longer contains this claim/i);
    expect(panel.querySelector('blockquote')?.textContent).toBe(
      'Withdrawn assertion.'
    );
    expect(
      await within(panel).findByText(/live case no longer contains this claim/i)
    ).toBeDefined();
    expect(apiMocks.getClaimDetail).toHaveBeenCalledWith(
      'case-1',
      'claim-gone',
      'snap-1'
    );

    const passage = await screen.findByRole('link', {
      name: 'Open passage in evidence inspector',
    });
    expect(passage.getAttribute('href')).toBe(
      '/cases/case-1/evidence?claim=claim-gone&evidence=ev-9&capture=cap-1&snapshot=snap-1'
    );

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).not.toContain('claim=')
    );
    expect(
      screen.queryByRole('region', { name: 'Frozen claim' })
    ).toBeNull();
  });

  it('states that a claim is absent from the selected snapshot on a 404', async () => {
    apiMocks.getClaimDetail.mockRejectedValue(
      new ApiError(
        'Claim claim-gone is not present in snapshot snap-1 for case case-1',
        404
      )
    );

    renderTab('/cases/case-1/changes?run=run-2&claim=claim-gone&snapshot=snap-1');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent ?? '').toMatch(/Claim not available in this observation/i);
    expect(alert.textContent ?? '').toMatch(/not present in snapshot snap-1/i);
    expect(alert.textContent ?? '').toMatch(/never replaced by a current row/i);
    // Absence is terminal for the reader; no retry is offered for a 404.
    expect(within(alert).queryByRole('button', { name: 'Retry' })).toBeNull();
  });

  it('shows a retryable error for a failed frozen-claim read and retries it', async () => {
    apiMocks.getClaimDetail
      .mockRejectedValueOnce(new ApiError('backend exploded', 500))
      .mockResolvedValueOnce({
        id: 'claim-gone',
        caseId: 'case-1',
        eventId: 'event-1',
        claimText: 'Withdrawn assertion.',
        claimSignature: 'sig-gone',
        verificationStatus: 'alleged',
        verificationProvenance: 'unknown',
        type: 'allegation',
        controversyScore: 0.4,
        narrativeClusterId: null,
        partyPositions: {},
        counts: {
          supportCount: 1,
          opposeCount: 0,
          sourceDiversityCount: 1,
          evidenceCount: 1,
        },
        passages: [],
        snapshotId: 'snap-1',
        liveState: null,
      } satisfies ClaimDetail);

    renderTab('/cases/case-1/changes?run=run-2&claim=claim-gone&snapshot=snap-1');

    const panel = await screen.findByRole('region', { name: 'Frozen claim' });
    const alert = await within(panel).findByRole('alert');
    // A non-404 failure is never labelled as snapshot absence.
    expect(alert.textContent ?? '').toMatch(/Could not load the frozen claim/i);
    expect(alert.textContent ?? '').toMatch(/backend exploded/i);
    expect(alert.textContent ?? '').not.toMatch(/Claim not available in this observation/i);

    fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

    expect(apiMocks.getClaimDetail).toHaveBeenCalledTimes(2);
    expect(await within(panel).findByText('Withdrawn assertion.')).toBeTruthy();
    expect(within(panel).queryByRole('alert')).toBeNull();
  });

  it('keeps pagination offset in the URL and requests the next page', async () => {
    apiMocks.getRunChanges.mockResolvedValue(
      makeChanges({
        items: [makeChange({ entityId: 'claim-1' })],
        total: 60,
        offset: 25,
        hasMore: true,
      })
    );

    renderTab('/cases/case-1/changes?run=run-2&offset=25');

    await waitFor(() =>
      expect(apiMocks.getRunChanges).toHaveBeenCalledWith('case-1', 'run-2', {
        limit: 25,
        offset: 25,
      })
    );
    const range = await screen.findByTestId('changes-range');
    expect(range.textContent ?? '').toContain('26–26 of 60');

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain('offset=50')
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Previous' }));
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain('offset=25')
    );
  });

  it('switches runs from the selector and resets the page offset', async () => {
    apiMocks.getInvestigationRuns.mockResolvedValue(
      makeRunList([
        makeRun({ id: 'run-3', sequence: 3 }),
        makeRun({ id: 'run-2', sequence: 2 }),
      ])
    );

    renderTab('/cases/case-1/changes?run=run-3&offset=25');

    fireEvent.click(await screen.findByRole('button', { name: /Run #2/ }));

    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain('run=run-2')
    );
    expect(screen.getByTestId('location').textContent).not.toContain('offset=25');
    await waitFor(() =>
      expect(apiMocks.getRunChanges).toHaveBeenCalledWith('case-1', 'run-2', {
        limit: 25,
        offset: 0,
      })
    );
  });

  it('distinguishes "no runs yet" from "no changes"', async () => {
    apiMocks.getInvestigationRuns.mockResolvedValue(makeRunList([]));

    renderTab();

    expect(await screen.findByText('No grouped runs recorded')).toBeTruthy();
    expect(
      screen.getByText(/not an empty change set/i)
    ).toBeTruthy();
    expect(screen.queryByText('Unchanged')).toBeNull();
    expect(apiMocks.getRunChanges).not.toHaveBeenCalled();
  });

  it('surfaces a load failure with a working retry', async () => {
    apiMocks.getInvestigationRuns.mockRejectedValueOnce(new Error('network down'));

    renderTab();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent ?? '').toMatch(/Could not load grouped runs/i);
    expect(alert.textContent ?? '').toMatch(/network down/i);

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    await waitFor(() =>
      expect(apiMocks.getInvestigationRuns).toHaveBeenCalledTimes(2)
    );
    expect(await screen.findByText('Unchanged')).toBeTruthy();
  });
});

describe('ChangesTab observer stamp and frozen navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getInvestigationRuns.mockResolvedValue(makeRunList([makeRun()]));
    apiMocks.getRunChanges.mockResolvedValue(makeChanges());
    apiMocks.getInvestigationRun.mockRejectedValue(
      new ApiError('Run not found', 404)
    );
  });

  it('renders the observer run as an observer stamp, never as an actor or cause', async () => {
    apiMocks.getRunChanges.mockResolvedValue(
      makeChanges({
        items: [
          makeChange({
            type: 'claim_added',
            entityId: 'claim-new',
            originRunId: 'run-1',
            observedByRunId: 'run-2',
          }),
        ],
        total: 1,
      })
    );

    renderTab();

    const rows = await waitFor(() => {
      const observed = observedRows();
      expect(observed).toHaveLength(1);
      return observed;
    });
    const text = rows[0].textContent ?? '';

    // Both run references are labelled as recording/observation facts.
    expect(text).toMatch(/Recorded by run/);
    expect(text).toMatch(/Observed by run/);
    // The observer stamp never becomes an actor, author or cause.
    expect(text).not.toMatch(/caused by|changed by|author|actor|attributed to|created by/i);
    expect(within(rows[0]).getByText('run-2')).toBeTruthy();
  });

  it('shows a frozen claim read-only and offers the explicit current-claim transition', async () => {
    apiMocks.getRunChanges.mockResolvedValue(
      makeChanges({
        items: [
          makeChange({
            type: 'claim_no_longer_extracted',
            entityId: 'claim-gone',
            before: { text: 'Withdrawn assertion.', claimSignature: 'sig-gone' },
            after: null,
          }),
        ],
        total: 1,
      })
    );
    apiMocks.getClaimDetail.mockResolvedValue({
      id: 'claim-gone',
      caseId: 'case-1',
      eventId: null,
      claimText: 'Withdrawn assertion.',
      claimSignature: 'sig-gone',
      verificationStatus: 'alleged',
      verificationProvenance: 'unknown',
      type: 'allegation',
      controversyScore: null,
      narrativeClusterId: null,
      partyPositions: {},
      counts: { supportCount: 0, opposeCount: 0, sourceDiversityCount: 0, evidenceCount: 0 },
      passages: [],
      snapshotId: 'snap-1',
      liveState: {
        present: false,
        claimSignature: null,
        textMatchesSnapshot: null,
        currentCaptureId: null,
        currentCaptureMatchesSnapshot: null,
      },
    } satisfies ClaimDetail);

    renderTab('/cases/case-1/changes?run=run-2&claim=claim-gone&snapshot=snap-1');

    const panel = await screen.findByRole('region', { name: 'Frozen claim' });
    expect(await within(panel).findByText('Withdrawn assertion.')).toBeTruthy();
    // Frozen context is explicit and read-only.
    expect(panel.textContent ?? '').toMatch(/read-only/i);
    expect(panel.textContent ?? '').toContain('snap-1');
    // No editing control exists on a frozen observation.
    expect(within(panel).queryByRole('textbox')).toBeNull();
    expect(apiMocks.getClaimDetail).toHaveBeenCalledWith('case-1', 'claim-gone', 'snap-1');

    const openCurrent = within(panel).getByRole('link', { name: 'Open current claim' });
    expect(openCurrent.getAttribute('href')).toBe(
      '/cases/case-1/changes?run=run-2&claim=claim-gone'
    );

    fireEvent.click(openCurrent);

    // Only this explicit transition drops the historical selector.
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toBe(
        '/cases/case-1/changes?run=run-2&claim=claim-gone'
      )
    );
    expect(screen.queryByRole('region', { name: 'Frozen claim' })).toBeNull();
    expect(apiMocks.getClaimDetail).toHaveBeenCalledTimes(1);
  });

  it('never forwards the browser snapshot to the frozen citation reader', async () => {
    apiMocks.getCitationDetail.mockResolvedValue(makeCitationDetail());
    apiMocks.getCaptureWindow.mockResolvedValue(makeCaptureWindow());

    renderInspector('/cases/case-1/evidence?citation=cit-1&snapshot=snap-1');

    await waitFor(() => expect(apiMocks.getCitationDetail).toHaveBeenCalled());
    // Two positional arguments only: the citation is frozen by its own ID.
    expect(apiMocks.getCitationDetail).toHaveBeenCalledWith('case-1', 'cit-1');
    expect(apiMocks.getCitationDetail.mock.calls[0]).toHaveLength(2);
    expect(JSON.stringify(apiMocks.getCitationDetail.mock.calls[0])).not.toMatch(/snap-1/);

    // The frozen citation renders its frozen context read-only.
    expect(await screen.findByRole('heading', { name: 'Frozen claim text' })).toBeDefined();
    expect(screen.getByText(/cannot be edited here/i)).toBeDefined();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('never forwards the browser snapshot to the capture-window reader', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(makeEvidenceDetail());
    apiMocks.getCaptureWindow.mockResolvedValue(makeCaptureWindow());

    renderInspector('/cases/case-1/evidence?evidence=ev-1&capture=cap-1&snapshot=snap-1');

    await waitFor(() => expect(apiMocks.getCaptureWindow).toHaveBeenCalled());
    const captureCall = apiMocks.getCaptureWindow.mock.calls[0];
    expect(captureCall).toHaveLength(4);
    expect(captureCall[0]).toBe('case-1');
    expect(captureCall[1]).toBe('ev-1');
    expect(captureCall[2]).toBe('cap-1');
    expect(JSON.stringify(captureCall[3] ?? {})).not.toMatch(/snapshot/i);

    // The snapshot-aware evidence reader, by contrast, keeps the selector.
    expect(apiMocks.getEvidenceDetail).toHaveBeenCalledWith('case-1', 'ev-1', 'snap-1');
  });
});

// ---------------------------------------------------------------------------
// F18 / X01 ad-hoc snapshot comparison
// ---------------------------------------------------------------------------

const AD_HOC_URL =
  '/cases/case-1/changes?mode=ad_hoc&baselineSnapshot=snap-1&targetSnapshot=snap-2';

const UNAVAILABLE_REASONS: SnapshotComparisonUnavailableReason[] = [
  'incompatible_schema',
  'incompatible_identity',
  'incompatible_policy',
  'unknown_version',
  'payload_unreadable',
];

function makeComparisonSide(
  overrides: Partial<SnapshotComparisonSide> = {}
): SnapshotComparisonSide {
  return {
    sequence: 1,
    createdAt: '2026-03-01T09:00:00Z',
    schemaVersion: 'case-snapshot-v1',
    identityVersion: 'claim-signature-sha256-v1',
    policyVersion: 'case-history-policy-v1',
    ...overrides,
  };
}

function makeComparisonRef(
  overrides: Partial<SnapshotComparisonRef> = {}
): SnapshotComparisonRef {
  return {
    snapshotId: 'snap-1',
    claimId: null,
    evidenceId: null,
    captureId: null,
    citationId: null,
    ...overrides,
  };
}

function makeComparisonItem(
  overrides: Partial<SnapshotComparisonItem> = {}
): SnapshotComparisonItem {
  return {
    entityType: 'claims',
    entityId: 'claim-1',
    changeKind: 'field_changed',
    changedFields: ['verificationStatus'],
    before: { verificationStatus: 'ALLEGED' },
    after: { verificationStatus: 'CONFIRMED' },
    refs: {
      baseline: makeComparisonRef({ snapshotId: 'snap-1', claimId: 'claim-1' }),
      target: makeComparisonRef({ snapshotId: 'snap-2', claimId: 'claim-1' }),
    },
    ...overrides,
  };
}

function makeComparison(overrides: Partial<SnapshotComparison> = {}): SnapshotComparison {
  return {
    mode: 'ad_hoc',
    comparisonPolicyVersion: 'snapshot-comparison-policy-v1',
    baselineSnapshotId: 'snap-1',
    targetSnapshotId: 'snap-2',
    baselineRunId: 'run-1',
    targetRunId: 'run-2',
    baselineCoverage: 'complete_requested_scope',
    targetCoverage: 'complete_requested_scope',
    baselineMetadata: makeComparisonSide({ sequence: 1 }),
    targetMetadata: makeComparisonSide({
      sequence: 2,
      createdAt: '2026-03-04T10:05:00Z',
    }),
    availability: 'ready',
    unavailableReason: null,
    items: [],
    total: 0,
    limit: 25,
    offset: 0,
    hasMore: false,
    ...overrides,
  };
}

describe('ChangesTab ad-hoc snapshot comparison', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getInvestigationRuns.mockResolvedValue(makeRunList([makeRun()]));
    apiMocks.getRunChanges.mockResolvedValue(makeChanges());
    apiMocks.getInvestigationRun.mockRejectedValue(
      new ApiError('Investigation run not found', 404)
    );
    apiMocks.getSnapshotComparison.mockResolvedValue(makeComparison());
  });

  it('renders a distinct ad-hoc panel with two labelled observations', async () => {
    renderTab(AD_HOC_URL);

    const panel = await screen.findByRole('region', {
      name: /ad-hoc snapshot comparison/i,
    });
    // Distinct from recorded changes, semantically and visually.
    expect(panel.getAttribute('data-mode')).toBe('ad_hoc');
    expect(within(panel).getByRole('heading', { name: /Ad-hoc snapshot comparison/i })).toBeTruthy();

    await waitFor(() =>
      expect(apiMocks.getSnapshotComparison).toHaveBeenCalledWith('case-1', {
        baseline: 'snap-1',
        target: 'snap-2',
        limit: 25,
        offset: 0,
      })
    );

    const baseline = panel.querySelector('[data-observation="baseline"]') as HTMLElement;
    const target = panel.querySelector('[data-observation="target"]') as HTMLElement;
    expect(within(baseline).getByRole('heading', { name: /Baseline observation/i })).toBeTruthy();
    expect(within(target).getByRole('heading', { name: /Target observation/i })).toBeTruthy();

    for (const [card, snapshotId, runId] of [
      [baseline, 'snap-1', 'run-1'],
      [target, 'snap-2', 'run-2'],
    ] as const) {
      const text = card.textContent ?? '';
      expect(text).toContain(snapshotId);
      expect(text).toContain(runId);
      expect(text).toContain('case-snapshot-v1');
      expect(text).toContain('claim-signature-sha256-v1');
      expect(text).toContain('case-history-policy-v1');
      expect(text).toContain('Complete requested scope');
      expect(text).toMatch(/Snapshot saved at/i);
    }

    // No observer/cause/actor attribution, no deletion language and no
    // recorded-run concepts.
    expect(panel.textContent ?? '').not.toMatch(/observed by run|observedByRun|caused by|changed by/i);
    expect(panel.textContent ?? '').not.toMatch(/deleted|deletion|removed|retracted|no longer extracted/i);
    expect(panel.textContent ?? '').not.toMatch(/Grouped runs/i);

    // The ad-hoc mode never reads or pins grouped runs.
    expect(apiMocks.getInvestigationRuns).not.toHaveBeenCalled();
    expect(apiMocks.getRunChanges).not.toHaveBeenCalled();
    expect(screen.getByTestId('location').textContent).toBe(AD_HOC_URL);
  });

  it('leaves the recorded view untouched when the mode is absent', async () => {
    renderTab('/cases/case-1/changes?run=run-2');

    expect(await screen.findByText('Unchanged')).toBeTruthy();
    expect(screen.queryByRole('region', { name: /ad-hoc snapshot comparison/i })).toBeNull();
    expect(apiMocks.getSnapshotComparison).not.toHaveBeenCalled();
    expect(screen.getByTestId('location').textContent).not.toContain('mode=');
  });

  it('renders every unavailable reason with no zero-change claim', async () => {
    for (const reason of UNAVAILABLE_REASONS) {
      apiMocks.getSnapshotComparison.mockResolvedValueOnce(
        makeComparison({
          availability: 'unavailable',
          unavailableReason: reason,
          items: [],
          total: null,
          hasMore: false,
        })
      );

      const view = renderTab(AD_HOC_URL);
      const panel = await screen.findByRole('region', {
        name: /ad-hoc snapshot comparison/i,
      });
      await within(panel).findByText('Comparison unavailable');

      expect(panel.textContent ?? '').toContain(reason);
      expect(panel.textContent ?? '').toMatch(/is not a zero-change result/i);
      // Neither the ready-zero sentence nor a pager may appear.
      expect(within(panel).queryByText(/No changes between these observations/i)).toBeNull();
      expect(within(panel).queryByTestId('changes-adhoc-range')).toBeNull();
      // The two observations are still reported independently.
      expect(panel.querySelector('[data-observation="baseline"]')).not.toBeNull();
      expect(panel.querySelector('[data-observation="target"]')).not.toBeNull();

      view.unmount();
    }
  });

  it('says there are no changes between the observations for a ready zero total', async () => {
    renderTab(AD_HOC_URL);

    const panel = await screen.findByRole('region', {
      name: /ad-hoc snapshot comparison/i,
    });
    await within(panel).findByText('No changes between these observations');
    expect(panel.textContent ?? '').toMatch(/No entity-level differences were reported/i);
    expect(within(panel).queryByText('Comparison unavailable')).toBeNull();
  });

  it('renders returned items in order with changed fields and per-side refs', async () => {
    apiMocks.getSnapshotComparison.mockResolvedValue(
      makeComparison({
        items: [
          makeComparisonItem(),
          makeComparisonItem({
            entityType: 'evidence',
            entityId: 'ev-1',
            changeKind: 'entity_added',
            changedFields: [],
            before: null,
            after: { title: 'Port Alden report' },
            refs: {
              baseline: makeComparisonRef({ snapshotId: 'snap-1' }),
              target: makeComparisonRef({
                snapshotId: 'snap-2',
                evidenceId: 'ev-1',
                captureId: 'cap-1',
              }),
            },
          }),
          makeComparisonItem({
            entityType: 'citations',
            entityId: 'cit-1',
            changeKind: 'entity_absent',
            changedFields: [],
            before: { quote: 'Frozen quotation' },
            after: null,
            refs: {
              baseline: makeComparisonRef({ snapshotId: 'snap-1', citationId: 'cit-1' }),
              target: makeComparisonRef({ snapshotId: 'snap-2' }),
            },
          }),
          makeComparisonItem({
            entityType: 'captures',
            entityId: 'cap-only',
            changeKind: 'entity_absent',
            changedFields: [],
            before: { textSha256: 'sha-1' },
            after: null,
            refs: {
              baseline: makeComparisonRef({ snapshotId: 'snap-1', captureId: 'cap-only' }),
              target: makeComparisonRef({ snapshotId: 'snap-2' }),
            },
          }),
        ],
        total: 4,
      })
    );

    renderTab(AD_HOC_URL);

    const panel = await screen.findByRole('region', {
      name: /ad-hoc snapshot comparison/i,
    });
    const rows = await waitFor(() => {
      const items = within(panel)
        .getByRole('list', { name: 'Ad-hoc comparison items' })
        .querySelectorAll('li');
      expect(items).toHaveLength(4);
      return [...items] as HTMLElement[];
    });

    // Order is exactly the order the reader returned.
    expect(rows[0].textContent).toContain('claim-1');
    expect(rows[0].textContent).toContain('Fields changed between observations');
    expect(rows[0].textContent).toContain('Verification');
    expect(rows[0].textContent).toContain('ALLEGED');
    expect(rows[0].textContent).toContain('CONFIRMED');

    // Only the ids that side actually carries become recorded links.
    expect(
      within(rows[0]).getByRole('link', { name: 'Baseline frozen claim' }).getAttribute('href')
    ).toBe('/cases/case-1/changes?claim=claim-1&snapshot=snap-1');
    expect(
      within(rows[1]).getByRole('link', { name: 'Target frozen evidence' }).getAttribute('href')
    ).toBe('/cases/case-1/evidence?evidence=ev-1&snapshot=snap-2');
    expect(
      within(rows[1]).getByRole('link', { name: 'Target frozen capture' }).getAttribute('href')
    ).toBe('/cases/case-1/evidence?evidence=ev-1&capture=cap-1&snapshot=snap-2');
    expect(within(rows[1]).queryByRole('link', { name: /Baseline/ })).toBeNull();

    const citation = within(rows[2]).getByRole('link', { name: 'Baseline frozen citation' });
    expect(citation.getAttribute('href')).toBe('/cases/case-1/evidence?citation=cit-1');
    expect(citation.getAttribute('href')).not.toContain('snapshot');

    // A capture reference without its evidence id gets no invented link.
    expect(rows[3].textContent).toContain('Absent from a later observation');
    expect(within(rows[3]).queryByRole('link')).toBeNull();
  });

  it('never forwards the browser snapshot to the citation or capture readers', async () => {
    apiMocks.getSnapshotComparison.mockResolvedValue(
      makeComparison({
        items: [
          makeComparisonItem({
            entityType: 'citations',
            entityId: 'cit-1',
            changedFields: ['quote'],
            before: { quote: 'before' },
            after: { quote: 'after' },
            refs: {
              baseline: makeComparisonRef({
                snapshotId: 'snap-1',
                citationId: 'cit-1',
                evidenceId: 'ev-1',
                captureId: 'cap-1',
              }),
              target: makeComparisonRef({
                snapshotId: 'snap-2',
                citationId: 'cit-1',
                evidenceId: 'ev-1',
                captureId: 'cap-1',
              }),
            },
          }),
        ],
        total: 1,
      })
    );

    // The browser's `snapshot` selector is present and must not be forwarded.
    renderTab(`${AD_HOC_URL}&snapshot=snap-2`);

    const panel = await screen.findByRole('region', {
      name: /ad-hoc snapshot comparison/i,
    });
    const rows = await waitFor(() => {
      const items = within(panel)
        .getByRole('list', { name: 'Ad-hoc comparison items' })
        .querySelectorAll('li');
      expect(items).toHaveLength(1);
      return [...items] as HTMLElement[];
    });

    const citation = within(rows[0]).getByRole('link', { name: 'Baseline frozen citation' });
    expect(citation.getAttribute('href')).not.toContain('snapshot=');

    fireEvent.click(citation);
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain('citation=cit-1')
    );
    expect(screen.getByTestId('location').textContent).not.toContain('snapshot=');

    // Neither frozen reader ever receives a snapshot argument.
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
    expect(apiMocks.getCaptureWindow).not.toHaveBeenCalled();
    for (const mock of [apiMocks.getCitationDetail, apiMocks.getCaptureWindow]) {
      expect(JSON.stringify(mock.mock.calls)).not.toMatch(/snapshot/i);
    }
  });

  it('keeps both pinned snapshots across a reload and the historical context link', async () => {
    const view = renderTab(AD_HOC_URL);

    const panel = await screen.findByRole('region', {
      name: /ad-hoc snapshot comparison/i,
    });
    const permalink = within(panel).getByRole('link', {
      name: 'Permalink for this comparison',
    });
    expect(permalink.getAttribute('href')).toBe(AD_HOC_URL);

    await within(panel).findByRole('heading', { name: /Target observation/i });
    const target = panel.querySelector('[data-observation="target"]') as HTMLElement;
    const historical = within(target).getByRole('link', {
      name: 'Open recorded changes pinned to the target observation',
    });
    expect(historical.getAttribute('href')).toBe(
      '/cases/case-1/changes?run=run-2&snapshot=snap-2'
    );

    // Reload: the permalink itself re-issues the same pinned pair, never "latest".
    view.unmount();
    renderTab(permalink.getAttribute('href') as string);
    await waitFor(() =>
      expect(apiMocks.getSnapshotComparison).toHaveBeenCalledWith('case-1', {
        baseline: 'snap-1',
        target: 'snap-2',
        limit: 25,
        offset: 0,
      })
    );
    expect(screen.getByTestId('location').textContent).toBe(AD_HOC_URL);
  });

  it('opens the historical changes context with that snapshot still pinned', async () => {
    const view = renderTab(AD_HOC_URL);
    const panel = await screen.findByRole('region', {
      name: /ad-hoc snapshot comparison/i,
    });
    await within(panel).findByRole('heading', { name: /Target observation/i });
    const target = panel.querySelector('[data-observation="target"]') as HTMLElement;

    fireEvent.click(
      within(target).getByRole('link', {
        name: 'Open recorded changes pinned to the target observation',
      })
    );
    const pinned = '/cases/case-1/changes?run=run-2&snapshot=snap-2';
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe(pinned));
    const comparisonCalls = apiMocks.getSnapshotComparison.mock.calls.length;

    // Reload the recorded view at that pinned URL: the snapshot is never dropped.
    view.unmount();
    renderTab(pinned);
    await waitFor(() =>
      expect(apiMocks.getRunChanges).toHaveBeenCalledWith('case-1', 'run-2', {
        limit: 25,
        offset: 0,
      })
    );
    expect(screen.getByTestId('location').textContent).toBe(pinned);
    // The recorded view never falls back to an ad-hoc comparison request.
    expect(apiMocks.getSnapshotComparison).toHaveBeenCalledTimes(comparisonCalls);
  });

  it('requires both selectors with an explicit message and no request', async () => {
    renderTab('/cases/case-1/changes?mode=ad_hoc&baselineSnapshot=snap-1');

    const panel = await screen.findByRole('region', {
      name: /ad-hoc snapshot comparison/i,
    });
    await within(panel).findByText('Two snapshots are required');
    expect(panel.textContent ?? '').toMatch(/The target snapshot is not pinned/i);
    expect(panel.textContent ?? '').toMatch(/never substituted/i);

    // No request, no defaulted selector, no pinned run.
    expect(apiMocks.getSnapshotComparison).not.toHaveBeenCalled();
    expect(apiMocks.getInvestigationRuns).not.toHaveBeenCalled();
    expect(apiMocks.getRunChanges).not.toHaveBeenCalled();
    expect(screen.getByTestId('location').textContent).toBe(
      '/cases/case-1/changes?mode=ad_hoc&baselineSnapshot=snap-1'
    );

    // Supplying the missing side is an explicit operator action.
    fireEvent.change(within(panel).getByLabelText('Target snapshot ID'), {
      target: { value: 'snap-2' },
    });
    fireEvent.click(within(panel).getByRole('button', { name: 'Compare these snapshots' }));

    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toBe(AD_HOC_URL)
    );
    await waitFor(() =>
      expect(apiMocks.getSnapshotComparison).toHaveBeenCalledWith('case-1', {
        baseline: 'snap-1',
        target: 'snap-2',
        limit: 25,
        offset: 0,
      })
    );
  });

  it('paginates the ad-hoc delta without touching the recorded pager', async () => {
    apiMocks.getSnapshotComparison.mockResolvedValue(
      makeComparison({
        items: [makeComparisonItem()],
        total: 60,
        offset: 25,
        hasMore: true,
      })
    );

    renderTab(`${AD_HOC_URL}&offset=25`);

    await waitFor(() =>
      expect(apiMocks.getSnapshotComparison).toHaveBeenCalledWith('case-1', {
        baseline: 'snap-1',
        target: 'snap-2',
        limit: 25,
        offset: 25,
      })
    );
    expect((await screen.findByTestId('changes-adhoc-range')).textContent).toContain(
      '26–26 of 60'
    );
    expect(apiMocks.getRunChanges).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain('offset=50')
    );
    expect(screen.getByTestId('location').textContent).toBe(`${AD_HOC_URL}&offset=50`);
    await waitFor(() =>
      expect(apiMocks.getSnapshotComparison).toHaveBeenCalledWith('case-1', {
        baseline: 'snap-1',
        target: 'snap-2',
        limit: 25,
        offset: 50,
      })
    );
  });

  it('adds the mode switch additively and restores the recorded view', async () => {
    renderTab('/cases/case-1/changes?run=run-2');

    await waitFor(() =>
      expect(apiMocks.getRunChanges).toHaveBeenCalledWith('case-1', 'run-2', {
        limit: 25,
        offset: 0,
      })
    );

    fireEvent.click(screen.getByRole('link', { name: 'Compare two snapshots' }));
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toBe(
        '/cases/case-1/changes?mode=ad_hoc'
      )
    );
    const panel = await screen.findByRole('region', {
      name: /ad-hoc snapshot comparison/i,
    });
    expect(panel.getAttribute('data-mode')).toBe('ad_hoc');
    expect(within(panel).getByText('Two snapshots are required')).toBeTruthy();
    expect(apiMocks.getSnapshotComparison).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('link', { name: 'Recorded changes' }));
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain('run=run-2')
    );
    expect(screen.getByTestId('location').textContent).not.toContain('mode=');
    expect(await screen.findByText('Unchanged')).toBeTruthy();
  });
});

describe('ChangesTab stray citation normalization (R02)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getInvestigationRuns.mockResolvedValue(makeRunList([makeRun()]));
    apiMocks.getRunChanges.mockResolvedValue(makeChanges());
    apiMocks.getInvestigationRun.mockRejectedValue(
      new ApiError('Investigation run not found', 404)
    );
    apiMocks.getClaimDetail.mockResolvedValue({
      id: 'claim-gone',
      caseId: 'case-1',
      eventId: null,
      claimText: 'Withdrawn assertion.',
      claimSignature: 'sig-gone',
      verificationStatus: 'alleged',
      verificationProvenance: 'unknown',
      type: 'allegation',
      controversyScore: null,
      narrativeClusterId: null,
      partyPositions: {},
      counts: { supportCount: 0, opposeCount: 0, sourceDiversityCount: 0, evidenceCount: 0 },
      passages: [],
      snapshotId: 'snap-1',
      liveState: {
        present: false,
        claimSignature: null,
        textMatchesSnapshot: null,
        currentCaptureId: null,
        currentCaptureMatchesSnapshot: null,
      },
    } satisfies ClaimDetail);
  });

  it('keeps the pinned snapshot and drops a stray citation from the committed URL', async () => {
    renderTab(
      '/cases/case-1/changes?run=run-2&claim=claim-gone&snapshot=snap-1&citation=cit-1'
    );

    const panel = await screen.findByRole('region', { name: 'Frozen claim' });
    await waitFor(() =>
      expect(apiMocks.getClaimDetail).toHaveBeenCalledWith('case-1', 'claim-gone', 'snap-1')
    );
    // The stray citation is not a selector this view reads.
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();

    fireEvent.click(within(panel).getByRole('link', { name: 'Open current claim' }));

    // Allowlist normalization drops the citation and keeps run/claim.
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toBe(
        '/cases/case-1/changes?run=run-2&claim=claim-gone'
      )
    );
    expect(apiMocks.getClaimDetail).toHaveBeenCalledTimes(1);
  });
});
