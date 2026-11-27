import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import PipelineMonitor from './PipelineMonitor';
import type { RunHistoryItem } from '../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getCaseDetail: vi.fn(),
  getRunHistoryForCase: vi.fn(),
}));

vi.mock('../services/api', () => apiMocks);

const caseDetail = {
  case: {
    id: 'case-1',
    query: 'Case one',
    conflictDomain: 'Water',
    status: 'investigating',
    stage: 'INVESTIGATE',
    counts: { articles: 0, events: 0, reviewItems: 0 },
    automationMode: 'safe',
    hasNewMaterial: false,
    openExceptionsCount: 0,
    lastUpdated: null,
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

const run = (overrides: Partial<RunHistoryItem>): RunHistoryItem => ({
  id: 'run-x',
  stage: 'RETRIEVE',
  model: 'model-a',
  durationMs: 1000,
  status: 'success',
  fallbackCount: 0,
  parseFailureCount: 0,
  timestamp: '2026-03-19T10:00:00Z',
  message: null,
  ...overrides,
});

function renderPipeline(path = '/cases/case-1/pipeline') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/cases/:id/pipeline" element={<PipelineMonitor />} />
          <Route path="/nowhere" element={<PipelineMonitor />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const setVisibility = (value: 'visible' | 'hidden') => {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => value });
  act(() => {
    document.dispatchEvent(new Event('visibilitychange'));
  });
};

describe('PipelineMonitor truthful states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('never renders fabricated log lines for an empty run history', async () => {
    apiMocks.getCaseDetail.mockResolvedValue(caseDetail);
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);
    renderPipeline();

    expect(await screen.findByText(/No stage attempts are recorded/i)).toBeDefined();
    expect(screen.getByText(/not a log or event stream/i)).toBeDefined();

    expect(screen.queryByText(/Found 47 articles/i)).toBeNull();
    expect(screen.queryByText(/Starting retrieval phase/i)).toBeNull();
    expect(screen.queryByText(/Timeout during fact check/i)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Errors' })).toBeNull();

    // Recorded stage pointer still shown; no invented total-stage telemetry.
    expect(screen.getByText(/INVESTIGATE — last recorded case stage/)).toBeDefined();
    expect(screen.queryByText('Total Stages')).toBeNull();
    expect(screen.queryByText('Real-time pipeline execution monitoring')).toBeNull();
  });

  it('reports unavailable log stream instead of a fake real-time claim', async () => {
    apiMocks.getCaseDetail.mockResolvedValue(caseDetail);
    apiMocks.getRunHistoryForCase.mockResolvedValue([run({})]);
    renderPipeline();

    expect(await screen.findByText(/saved stage attempts, not a log or event stream/i)).toBeDefined();
    expect(screen.getByText('Unavailable')).toBeDefined();
  });

  it('treats a recorded zero duration as data, not missing', async () => {
    apiMocks.getCaseDetail.mockResolvedValue(caseDetail);
    apiMocks.getRunHistoryForCase.mockResolvedValue([
      run({ id: 'r1', durationMs: 0 }),
      run({ id: 'r2', durationMs: 0, stage: 'TRIAGE' }),
    ]);
    renderPipeline();

    expect(await screen.findByText('Avg Recorded Duration')).toBeDefined();
    expect(screen.getAllByText('0.00s').length).toBeGreaterThan(0);
    expect(screen.queryByText(/NaN|Infinity/)).toBeNull();
  });

  it('shows "Not recorded" when no durations were recorded', async () => {
    apiMocks.getCaseDetail.mockResolvedValue(caseDetail);
    apiMocks.getRunHistoryForCase.mockResolvedValue([run({ durationMs: null })]);
    renderPipeline();

    const label = await screen.findByText('Avg Recorded Duration');
    expect(label.parentElement?.textContent).toContain('Not recorded');
  });

  it('surfaces a run-history error with retry instead of ignoring it', async () => {
    apiMocks.getCaseDetail.mockResolvedValue(caseDetail);
    apiMocks.getRunHistoryForCase.mockRejectedValueOnce(new Error('history down'));
    renderPipeline();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('history down');

    apiMocks.getRunHistoryForCase.mockResolvedValueOnce([run({ stage: 'TRIAGE' })]);
    fireEvent.click(screen.getByRole('button', { name: 'Retry run history' }));

    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect((await screen.findAllByText('TRIAGE')).length).toBeGreaterThan(0);
    expect(apiMocks.getRunHistoryForCase).toHaveBeenCalledTimes(2);
  });

  it('publishes no numeric history metrics while history is unavailable', async () => {
    apiMocks.getCaseDetail.mockResolvedValue(caseDetail);
    apiMocks.getRunHistoryForCase.mockRejectedValueOnce(new Error('history unavailable'));
    renderPipeline();

    await screen.findByRole('alert');

    const metricValue = (label: string) => {
      const labelEl = screen.getByText(label);
      return labelEl.parentElement?.querySelector('.pipeline-monitor-metric-value')?.textContent;
    };
    expect(metricValue('Recorded Attempts')).toBe('—');
    expect(metricValue('Distinct Stages Recorded')).toBe('—');
    expect(metricValue('Succeeded')).toBe('—');
    expect(metricValue('Errors')).toBe('—');
    expect(metricValue('Avg Recorded Duration')).toBe('—');
    // No PipelineFlow execution states are claimed without usable history.
    expect(screen.queryByText('Unrecorded')).toBeNull();
    expect(screen.getByText(/stage execution status is unknown/i)).toBeDefined();
    expect(screen.getByText(/INVESTIGATE/)).toBeDefined();

    apiMocks.getRunHistoryForCase.mockResolvedValueOnce([]);
    fireEvent.click(screen.getByRole('button', { name: 'Retry run history' }));

    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(metricValue('Recorded Attempts')).toBe('0');
    expect((await screen.findAllByText('Unrecorded')).length).toBeGreaterThan(0);
  });

  it('never renders NaN or Infinity for non-finite or negative durations', async () => {
    apiMocks.getCaseDetail.mockResolvedValue(caseDetail);
    apiMocks.getRunHistoryForCase.mockResolvedValue([
      run({ id: 'a', durationMs: Number.NaN }),
      run({ id: 'b', durationMs: Number.POSITIVE_INFINITY }),
      run({ id: 'c', durationMs: Number.NEGATIVE_INFINITY }),
      run({ id: 'd', durationMs: -10 }),
      run({ id: 'e', durationMs: 0 }),
    ]);
    renderPipeline();

    expect(await screen.findByText('Avg Recorded Duration')).toBeDefined();
    expect(screen.getAllByText(/Invalid duration/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('0.00s').length).toBeGreaterThan(0);
    expect(screen.queryByText(/NaN|Infinity/)).toBeNull();
  });

  it('disables refresh and loads nothing when the route has no case id', async () => {
    renderPipeline('/nowhere');

    const refresh = screen.getByRole('button', { name: 'Refresh' });
    expect((refresh as HTMLButtonElement).disabled).toBe(true);
    expect(apiMocks.getCaseDetail).not.toHaveBeenCalled();
    expect(apiMocks.getRunHistoryForCase).not.toHaveBeenCalled();
  });

  it('labels configured workflow order apart from recorded attempts', async () => {
    apiMocks.getCaseDetail.mockResolvedValue(caseDetail);
    apiMocks.getRunHistoryForCase.mockResolvedValue([run({})]);
    renderPipeline();

    await screen.findByText(/saved stage attempts, not a log or event stream/i);

    // Configured-vs-recorded distinction is explicit, not implied by styling.
    expect(screen.getAllByText(/configured/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/recorded/i).length).toBeGreaterThan(0);
    expect(screen.getByText('Recorded Stage Attempts')).toBeDefined();
    expect(screen.getByText('Recorded Attempts')).toBeDefined();
  });

  it('claims no capability the read API does not provide', async () => {
    apiMocks.getCaseDetail.mockResolvedValue(caseDetail);
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);
    renderPipeline();

    await screen.findByText(/No stage attempts are recorded/i);

    expect(screen.queryByText(/Real-time/i)).toBeNull();
    expect(screen.queryByText('Alerts')).toBeNull();
    expect(screen.queryByText(/Notifications/i)).toBeNull();
    expect(screen.queryByText(/RBAC|role-based/i)).toBeNull();
    expect(screen.queryByText(/WebSocket/i)).toBeNull();
    expect(screen.queryByText(/Scheduling/i)).toBeNull();
    expect(screen.queryByText(/Deploy/i)).toBeNull();
  });

  it('labels client fetch time and recorded attempt time distinctly', async () => {
    apiMocks.getCaseDetail.mockResolvedValue(caseDetail);
    apiMocks.getRunHistoryForCase.mockResolvedValue([run({})]);
    renderPipeline();

    await screen.findByText('Recorded Stage Attempts');

    const fetched = screen.getByTestId('pipeline-last-fetched');
    const observed = screen.getByTestId('pipeline-last-observed');

    expect(fetched.textContent).toContain('Last fetched');
    expect(fetched.textContent).toContain('client request time');
    expect(observed.textContent).toContain('Last observed');
    expect(observed.textContent).toContain(
      new Date('2026-03-19T10:00:00Z').toLocaleString()
    );
    expect(fetched).not.toBe(observed);
  });

  it('renders pipeline-unrecorded distinctly from an empty attempt list', async () => {
    apiMocks.getCaseDetail.mockResolvedValue({
      ...caseDetail,
      case: { ...caseDetail.case, stage: null },
    } as never);
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);
    renderPipeline();

    await screen.findByText(/No pipeline stage is recorded for this case/i);

    const unrecorded = document.querySelector('[data-state="pipeline-unrecorded"]');
    expect(unrecorded).not.toBeNull();
    expect(unrecorded?.textContent).toContain('absent record');
    // The empty attempt list belongs to a different branch and is not claimed here.
    expect(document.querySelector('[data-state="pipeline-attempts-empty"]')).toBeNull();
    expect(screen.queryByText(/No stage attempts are recorded/i)).toBeNull();
  });

  it('marks an empty attempt list as data, not as an unrecorded pipeline', async () => {
    apiMocks.getCaseDetail.mockResolvedValue(caseDetail);
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);
    renderPipeline();

    await screen.findByText(/No stage attempts are recorded/i);

    const empty = document.querySelector('[data-state="pipeline-attempts-empty"]');
    expect(empty).not.toBeNull();
    expect(empty?.textContent).toContain('empty attempt list, not a missing record');
    expect(document.querySelector('[data-state="pipeline-unrecorded"]')).toBeNull();
  });

  it('stops polling while the tab is hidden and resumes when visible again', async () => {
    vi.useFakeTimers();
    apiMocks.getCaseDetail.mockResolvedValue(caseDetail);
    apiMocks.getRunHistoryForCase.mockResolvedValue([run({})]);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/cases/case-1/pipeline']}>
          <Routes>
            <Route path="/cases/:id/pipeline" element={<PipelineMonitor />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(apiMocks.getCaseDetail).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(16000);
    });
    const pollsWhileVisible = apiMocks.getCaseDetail.mock.calls.length;
    expect(pollsWhileVisible).toBeGreaterThan(1);

    setVisibility('hidden');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(apiMocks.getCaseDetail).toHaveBeenCalledTimes(pollsWhileVisible);

    setVisibility('visible');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(apiMocks.getCaseDetail.mock.calls.length).toBeGreaterThan(pollsWhileVisible);
  });

  it('surfaces a case error with retry and does not fall back to BOOTSTRAP', async () => {
    apiMocks.getCaseDetail.mockRejectedValueOnce(new Error('case missing'));
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);
    renderPipeline();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('case missing');
    expect(screen.queryByText(/BOOTSTRAP/)).toBeNull();

    apiMocks.getCaseDetail.mockResolvedValueOnce(caseDetail);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText(/INVESTIGATE — last recorded case stage/)).toBeDefined();
  });
});
