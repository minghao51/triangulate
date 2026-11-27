import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import Dashboard from './Dashboard';
import type { TopicCase } from '../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getCases: vi.fn(),
  getMonitoringSummary: vi.fn(),
  getCaseDetail: vi.fn(),
}));

vi.mock('../services/api', () => apiMocks);

const makeCase = (overrides: Partial<TopicCase> & Pick<TopicCase, 'id' | 'query'>): TopicCase => ({
  conflictDomain: 'Water',
  status: 'investigating',
  stage: 'INVESTIGATE',
  counts: { articles: 0, events: 0, reviewItems: 0 },
  automationMode: 'safe',
  hasNewMaterial: false,
  openExceptionsCount: 0,
  lastUpdated: '2026-03-19T10:00:00Z',
  ...overrides,
});

/**
 * Deliberately scrambled so the rendered order can only come from the recorded
 * counts comparator, never from payload order.
 */
const cases: TopicCase[] = [
  makeCase({ id: 'case-zz', query: 'No recorded signal' }),
  makeCase({
    id: 'case-aa',
    query: 'Material recorded',
    hasNewMaterial: true,
    counts: { articles: 1, events: 1, reviewItems: 0 },
  }),
  makeCase({
    id: 'case-bb',
    query: 'Exceptions recorded',
    openExceptionsCount: 3,
    counts: { articles: 1, events: 1, reviewItems: 0 },
  }),
  makeCase({
    id: 'case-yy',
    query: 'Second zero-signal case',
  }),
  makeCase({
    id: 'case-cc',
    query: 'Review items recorded',
    counts: { articles: 5, events: 2, reviewItems: 2 },
  }),
  makeCase({
    id: 'case-dd',
    query: 'Most material',
    counts: { articles: 9, events: 9, reviewItems: 0 },
  }),
];

const EXPECTED_ORDER = [
  'Exceptions recorded',
  'Material recorded',
  'Review items recorded',
  'Most material',
  // Identical recorded counts: broken by case id (case-yy before case-zz).
  'Second zero-signal case',
  'No recorded signal',
];

const summary = {
  cases: {},
  review: { open_exceptions: 3 },
  pipeline: { avg_duration_ms: 1200 },
  intake: {},
  evaluation: { avg_overall_score: 0.72 },
};

function renderDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Dashboard — two reads, counts-only queue', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getCases.mockResolvedValue(cases);
    apiMocks.getMonitoringSummary.mockResolvedValue(summary);
  });

  it('renders from the existing two queries with zero per-case detail reads', async () => {
    renderDashboard();

    expect(await screen.findByText('Investigation Dashboard')).toBeDefined();
    expect((await screen.findAllByTestId('dashboard-queue-item')).length).toBe(6);

    // Exactly the two preserved reads, each issued once.
    expect(apiMocks.getCases).toHaveBeenCalledTimes(1);
    expect(apiMocks.getMonitoringSummary).toHaveBeenCalledTimes(1);
    // No N+1 fan-out: the queue is built from list-DTO counts only.
    expect(apiMocks.getCaseDetail).not.toHaveBeenCalled();
  });

  it('orders the queue deterministically from recorded counts only', async () => {
    renderDashboard();
    await screen.findAllByTestId('dashboard-queue-item');

    const titles = screen
      .getAllByTestId('dashboard-queue-item')
      .map((item) => item.querySelector('.attention-query')?.textContent);

    expect(titles).toEqual(EXPECTED_ORDER);
  });

  it('keeps the same order when the payload order changes (id tie-break)', async () => {
    apiMocks.getCases.mockResolvedValue([...cases].reverse());
    renderDashboard();
    await screen.findAllByTestId('dashboard-queue-item');

    const titles = screen
      .getAllByTestId('dashboard-queue-item')
      .map((item) => item.querySelector('.attention-query')?.textContent);

    // Reversed payload, identical order: the zero-signal pair is broken by id.
    expect(titles).toEqual(EXPECTED_ORDER);
  });

  it('shows recorded reasons instead of invented priorities', async () => {
    renderDashboard();
    await screen.findAllByTestId('dashboard-queue-item');

    const queue = screen.getAllByTestId('dashboard-queue-item');
    expect(queue[0].textContent).toContain('3 open exceptions');
    expect(queue[0].textContent).toContain('1 recorded articles');
    expect(queue[1].textContent).toContain('new material recorded');
    expect(queue[2].textContent).toContain('2 recorded review items');
  });

  it('labels client fetch time and recorded observation time distinctly', async () => {
    renderDashboard();
    await screen.findAllByTestId('dashboard-queue-item');

    const fetched = screen.getByTestId('dashboard-last-fetched');
    const observed = screen.getByTestId('dashboard-last-observed');

    expect(fetched.textContent).toContain('Last fetched');
    expect(fetched.textContent).toContain('client request time');
    expect(observed.textContent).toContain('Last observed');
    expect(observed.textContent).toContain('recorded server observation');
    expect(observed.textContent).toContain(
      new Date('2026-03-19T10:00:00Z').toLocaleString()
    );
    // The two values are separate facts, rendered in separate elements.
    expect(fetched).not.toBe(observed);
  });

  it('makes no live-monitoring or healthy-pipeline capability claim', async () => {
    renderDashboard();
    await screen.findAllByTestId('dashboard-queue-item');

    expect(screen.queryByText(/real-time/i)).toBeNull();
    expect(screen.queryByText(/live monitoring/i)).toBeNull();
    expect(screen.queryByText('Pipeline Status')).toBeNull();
    expect(screen.queryByText(/All systems/i)).toBeNull();
    // Health is disclosed as liveness-only, not as a readiness signal.
    expect(screen.getByText(/liveness only/i)).toBeDefined();
    expect(screen.getAllByText('Not provided by the API').length).toBeGreaterThan(0);
  });
});
