import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import ChangesTab from './ChangesTab';
import type {
  ChangeItem,
  ClaimDetail,
  InvestigationRun,
  RunChanges,
} from '../../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getInvestigationRuns: vi.fn(),
  getRunChanges: vi.fn(),
  getClaimDetail: vi.fn(),
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
    renderTab('/cases/case-1/changes?run=run-missing');

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

  it('states that a claim is absent from the selected snapshot', async () => {
    apiMocks.getClaimDetail.mockRejectedValue(
      new Error('Claim claim-gone is not present in snapshot snap-1 for case case-1')
    );

    renderTab('/cases/case-1/changes?run=run-2&claim=claim-gone&snapshot=snap-1');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent ?? '').toMatch(/Claim not available in this observation/i);
    expect(alert.textContent ?? '').toMatch(/not present in snapshot snap-1/i);
    expect(alert.textContent ?? '').toMatch(/never replaced by a current row/i);
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
