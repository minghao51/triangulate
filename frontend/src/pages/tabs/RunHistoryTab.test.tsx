import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import RunHistoryTab from './RunHistoryTab';
import CaseIntelligenceCenter from '../CaseIntelligenceCenter';
import { useCaseStore } from '../../stores/case-store';
import type {
  InvestigationRun,
  InvestigationRunList,
  RunHistoryItem,
} from '../../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getRunHistoryForCase: vi.fn(),
  getInvestigationRuns: vi.fn(),
  getCaseDetail: vi.fn(),
}));

// Spread the real module so unrelated readers stay defined, then override the
// few the run-history reader uses.
vi.mock('../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/api')>();
  return { ...actual, ...apiMocks };
});

const makeRun = (id: string, overrides: Partial<RunHistoryItem> = {}): RunHistoryItem => ({
  id,
  stage: 'RETRIEVE',
  model: 'rss-fetcher',
  durationMs: 1200,
  status: 'success',
  fallbackCount: 0,
  parseFailureCount: 0,
  timestamp: '2026-03-19T10:00:00Z',
  message: null,
  ...overrides,
});

const makeGroupedRun = (overrides: Partial<InvestigationRun> = {}): InvestigationRun => ({
  id: 'grouped-run-1',
  caseId: 'case-1',
  sequence: 1,
  trigger: 'initial',
  requestedStartStage: 'RETRIEVE',
  status: 'succeeded',
  coverage: 'complete_requested_scope',
  startedAt: '2026-03-19T10:00:00Z',
  completedAt: '2026-03-19T10:05:00Z',
  predecessorRunId: null,
  baselineSnapshotId: null,
  resultSnapshotId: 'snap-1',
  snapshotId: 'snap-1',
  errorMessage: null,
  ...overrides,
});

const groupedList = (items: InvestigationRun[]): InvestigationRunList => ({
  items,
  total: items.length,
  limit: 50,
  offset: 0,
  hasMore: false,
});

const baseCaseDetail = {
  case: {
    id: 'case-1',
    query: 'Example Case',
    conflictDomain: 'Energy Security',
    status: 'review ready',
    stage: 'REVIEW',
    counts: { articles: 0, events: 0, reviewItems: 0 },
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
    report: {
      status: 'pending',
      markdownPath: null,
      markdownContent: null,
      manifestPath: null,
    },
  },
};

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

function renderRuns(caseId: string, queryClient: QueryClient = newClient()) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/cases/${caseId}/run-history`]}>
        <RunHistoryTab caseId={caseId} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
};

function renderCaseRoute(entry: string) {
  return render(
    <QueryClientProvider client={newClient()}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route
            path="/cases/:id/*"
            element={
              <>
                <LocationProbe />
                <CaseIntelligenceCenter />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useCaseStore.getState().clearActiveCase();
  apiMocks.getInvestigationRuns.mockResolvedValue(groupedList([]));
  apiMocks.getCaseDetail.mockResolvedValue(baseCaseDetail);
});

describe('RunHistoryTab reader states', () => {
  it('shows the shared loading state, then the run rows', async () => {
    let resolveRuns: (value: RunHistoryItem[]) => void = () => {};
    apiMocks.getRunHistoryForCase.mockReturnValue(
      new Promise<RunHistoryItem[]>((resolve) => {
        resolveRuns = resolve;
      })
    );

    const { container } = renderRuns('case-1');
    expect(container.querySelector('[data-state="loading"]')?.textContent).toContain('Loading recorded data');
    expect(container.querySelector('table')).toBeNull();

    await (async () => resolveRuns([makeRun('run-1')]))();

    expect(await screen.findByText('RETRIEVE')).toBeDefined();
    expect(container.querySelector('[data-state]')).toBeNull();
    expect(container.querySelectorAll('.history-row')).toHaveLength(1);
  });

  it('renders a distinct empty state instead of an empty table', async () => {
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);

    const { container } = renderRuns('case-1');

    expect(
      await screen.findByText('No pipeline runs have been recorded for this case yet.')
    ).toBeDefined();
    expect(container.querySelector('[data-state="empty"]')).not.toBeNull();
    expect(container.querySelector('table')).toBeNull();
  });

  it('renders a retryable network error and recovers on retry', async () => {
    apiMocks.getRunHistoryForCase.mockRejectedValueOnce(new Error('run history 500'));

    const { container } = renderRuns('case-1');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('run history 500');
    expect(container.querySelector('[data-state="network-error"]')).not.toBeNull();

    apiMocks.getRunHistoryForCase.mockResolvedValueOnce([makeRun('run-2', { stage: 'ARBITRATE' })]);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByText('ARBITRATE')).toBeDefined();
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
  });

  it('caches each case separately', async () => {
    apiMocks.getRunHistoryForCase.mockImplementation((caseId: string) =>
      Promise.resolve([makeRun(`run-${caseId}`, { stage: caseId === 'case-a' ? 'RETRIEVE' : 'REVIEW' })])
    );

    const queryClient = newClient();
    const result = renderRuns('case-a', queryClient);
    expect(await screen.findByText('RETRIEVE')).toBeDefined();

    result.rerender(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/cases/case-b/run-history']}>
          <RunHistoryTab caseId="case-b" />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(await screen.findByText('REVIEW')).toBeDefined();
    expect(screen.queryByText('RETRIEVE')).toBeNull();

    expect(queryClient.getQueryData<RunHistoryItem[]>(['run-history', 'case-a'])).toHaveLength(1);
    expect(queryClient.getQueryData<RunHistoryItem[]>(['run-history', 'case-b'])).toHaveLength(1);
  });
});

describe('RunHistoryTab identifier labelling', () => {
  it('labels stage-attempt IDs and grouped-run IDs as different identifiers', async () => {
    apiMocks.getRunHistoryForCase.mockResolvedValue([
      makeRun('stage-attempt-0001', { stage: 'RETRIEVE' }),
    ]);
    apiMocks.getInvestigationRuns.mockResolvedValue(
      groupedList([
        makeGroupedRun({ id: 'grouped-run-0002', sequence: 2, trigger: 'rerun' }),
      ])
    );

    const { container } = renderRuns('case-1');

    expect(await screen.findByText('RETRIEVE')).toBeDefined();

    const stageSection = await screen.findByRole('region', { name: 'Stage attempts' });
    const groupedSection = await screen.findByRole('region', {
      name: 'Grouped investigation runs',
    });

    // Each identifier kind carries its own label.
    expect(stageSection.textContent).toContain('Stage attempt ID');
    expect(groupedSection.textContent).toContain('Grouped run ID');
    expect(groupedSection.textContent).toContain('Grouped run #2');

    const stageId = stageSection.querySelector('[data-id-kind="stage-attempt-id"]');
    const groupedId = groupedSection.querySelector('[data-id-kind="grouped-run-id"]');
    expect(stageId?.getAttribute('title')).toBe('stage-attempt-0001');
    expect(groupedId?.getAttribute('title')).toBe('grouped-run-0002');

    // The two kinds never bleed into each other's section.
    expect(stageSection.textContent).not.toContain('grouped-run-0002');
    expect(groupedSection.textContent).not.toContain('stage-attempt-0001');
    expect(stageSection.textContent).not.toContain('Grouped run ID');
    expect(groupedSection.textContent).not.toContain('Stage attempt ID');

    // A run reference is only a recording reference: never an actor or a cause.
    const allText = container.textContent ?? '';
    expect(allText).not.toMatch(/actor|author|caused by|changed by|attributed to/i);
  });

  it('states that grouped runs are unknown rather than inventing them', async () => {
    apiMocks.getRunHistoryForCase.mockResolvedValue([makeRun('run-1')]);
    apiMocks.getInvestigationRuns.mockResolvedValue(groupedList([]));

    renderRuns('case-1');

    expect(
      await screen.findByText(
        'No grouped investigation runs have been recorded for this case.'
      )
    ).toBeDefined();
  });
});

describe('grouped-run frozen-report link (X02/F20)', () => {
  it('links each recorded grouped run to the report tab pinned to that run', async () => {
    apiMocks.getRunHistoryForCase.mockResolvedValue([makeRun('stage-attempt-0001')]);
    apiMocks.getInvestigationRuns.mockResolvedValue(
      groupedList([
        makeGroupedRun({ id: 'grouped-run-0002', sequence: 2, status: 'succeeded' }),
      ])
    );

    const { container } = renderRuns('case-1');

    const groupedSection = await screen.findByRole('region', {
      name: 'Grouped investigation runs',
    });
    const link = await screen.findByTestId('history-grouped-report-link-grouped-run-0002');
    expect(link.getAttribute('href')).toBe('/cases/case-1/report?reportRun=grouped-run-0002');

    // The link is an explicit pin; it never claims a report exists and it
    // leaves the stage-attempt table and identifier semantics untouched.
    expect(groupedSection.textContent).toContain('View frozen report');
    expect(groupedSection.textContent).toContain('explicit');
    expect(groupedSection.textContent).toContain('no-report');
    expect(container.querySelectorAll('.history-row')).toHaveLength(1);
    expect(container.querySelector('[data-id-kind="stage-attempt-id"]')?.textContent).toBe(
      'stage-atte…'
    );
    expect(groupedSection.textContent).not.toMatch(
      /latest|most recent|previous report|chain[\s-]?of[\s-]?custody|custody|verified/i
    );
  });
});

describe('current-only historical boundary', () => {
  it('gates a snapshot selector on run history before any view fetch, and only "Open current" strips it', async () => {
    renderCaseRoute('/cases/case-1/run-history?snapshot=snap-1');

    expect(await screen.findByText('Unsupported historical view')).toBeDefined();
    await new Promise((resolve) => setTimeout(resolve, 0));

    // Nothing was fetched for the current-only view while the selector is shown.
    expect(apiMocks.getRunHistoryForCase).not.toHaveBeenCalled();
    expect(apiMocks.getInvestigationRuns).not.toHaveBeenCalled();
    expect(screen.queryByRole('heading', { name: 'Pipeline Execution History' })).toBeNull();
    // The historical selector is never silently dropped to reveal live data.
    expect(screen.getByTestId('location').textContent).toBe(
      '/cases/case-1/run-history?snapshot=snap-1'
    );

    const openCurrent = screen.getByRole('link', { name: 'Open current Run history' });
    expect(openCurrent.getAttribute('href')).toBe('/cases/case-1/run-history');

    fireEvent.click(openCurrent);

    expect(await screen.findByRole('heading', { name: 'Pipeline Execution History' })).toBeDefined();
    await waitFor(() => expect(apiMocks.getRunHistoryForCase).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId('location').textContent).toBe('/cases/case-1/run-history');
  });
});
