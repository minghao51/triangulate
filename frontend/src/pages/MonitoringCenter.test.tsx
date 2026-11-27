import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import MonitoringCenter from './MonitoringCenter';
import type { TopicCase } from '../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getCases: vi.fn(),
}));

vi.mock('../services/api', () => apiMocks);

const monitoringCase: TopicCase = {
  id: 'case-monitor-1',
  query: 'Port strike monitoring',
  conflictDomain: 'Labour',
  status: 'monitoring',
  stage: 'REVIEW',
  counts: { articles: 4, events: 2, reviewItems: 0 },
  automationMode: 'safe',
  hasNewMaterial: false,
  openExceptionsCount: 0,
  lastUpdated: '2026-03-19T10:00:00Z',
};

function renderMonitoring() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MonitoringCenter />
    </QueryClientProvider>
  );
}

const setVisibility = (value: 'visible' | 'hidden') => {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => value });
  act(() => {
    document.dispatchEvent(new Event('visibilitychange'));
  });
};

describe('MonitoringCenter truthful states', () => {
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

  it('renders no invented alerts, health, performance or schedules for an empty backend', async () => {
    apiMocks.getCases.mockResolvedValue([]);
    renderMonitoring();

    expect(await screen.findByText('No monitoring cases recorded')).toBeDefined();

    // No synthetic alert text, acknowledgement buttons or fabricated metrics.
    expect(screen.queryByText(/15 new articles found/i)).toBeNull();
    expect(screen.queryByText(/Verification status changed/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /Acknowledge/i })).toBeNull();
    expect(screen.queryByText(/98\.5%|98%|1\.2s|15%/)).toBeNull();
    expect(screen.queryByText('All time')).toBeNull();

    // Unavailable panels state that data is missing rather than "healthy"/"none".
    expect(screen.getAllByText('Not provided by the API').length).toBeGreaterThan(0);
    expect(screen.queryByText('No alerts')).toBeNull();
  });

  it('distinguishes loading from an empty result', async () => {
    let resolveCases: (value: TopicCase[]) => void = () => {};
    apiMocks.getCases.mockReturnValue(
      new Promise<TopicCase[]>((resolve) => {
        resolveCases = resolve;
      })
    );
    renderMonitoring();

    expect(screen.getByRole('status').textContent).toContain('Loading monitoring cases');
    expect(screen.queryByText('No monitoring cases recorded')).toBeNull();

    resolveCases([]);
    expect(await screen.findByText('No monitoring cases recorded')).toBeDefined();
  });

  it('renders only recorded monitoring cases with their recorded status/last update', async () => {
    apiMocks.getCases.mockResolvedValue([
      monitoringCase,
      { ...monitoringCase, id: 'case-other', query: 'Not monitoring', status: 'approved' },
    ]);
    renderMonitoring();

    const row = await screen.findByRole('button', { name: /Port strike monitoring/i });
    expect(row.getAttribute('aria-pressed')).toBe('false');
    expect(screen.queryByText('Not monitoring')).toBeNull();

    fireEvent.click(row);
    expect(row.getAttribute('aria-pressed')).toBe('true');
    expect(screen.getAllByText(/Last updated/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Not provided by the API').length).toBeGreaterThan(0);
  });

  it('shows a retryable error instead of a zeroed dashboard', async () => {
    apiMocks.getCases.mockRejectedValueOnce(new Error('upstream unavailable'));
    renderMonitoring();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('upstream unavailable');
    expect(screen.queryByText('No monitoring cases recorded')).toBeNull();

    // Observational metrics must not publish a fake zero / "Never recorded"
    // for an unknown (failed) read.
    const metricValue = (label: string) => {
      const labelEl = screen.getByText(label);
      return labelEl.nextElementSibling?.textContent;
    };
    expect(metricValue('Monitoring Cases')).toBe('—');
    expect(metricValue('Cases With Recorded Update')).toBe('—');
    expect(metricValue('Most Recent Valid Recorded Update')).toBe('—');
    expect(screen.queryByText('Never recorded')).toBeNull();
    expect(screen.getByRole('tab', { name: 'Monitors' })).toBeDefined();
    expect(screen.queryByRole('tab', { name: /Monitors \(/ })).toBeNull();

    // The always-unavailable telemetry cards stay explicitly unavailable.
    expect(screen.getAllByText('Not provided by the API').length).toBe(2);

    apiMocks.getCases.mockResolvedValueOnce([monitoringCase]);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    await waitFor(() => {
      expect(screen.queryByRole('alert')).toBeNull();
    });
    expect(await screen.findByRole('button', { name: /Port strike monitoring/i })).toBeDefined();
    expect(apiMocks.getCases).toHaveBeenCalledTimes(2);
  });

  it('disables unsupported mutation controls and explains CLI guidance', async () => {
    apiMocks.getCases.mockResolvedValue([monitoringCase]);
    renderMonitoring();

    const newMonitor = screen.getByRole('button', { name: 'New Monitor' });
    expect((newMonitor as HTMLButtonElement).disabled).toBe(true);
    expect(newMonitor.getAttribute('title')).toMatch(/read-only/i);

    fireEvent.click(await screen.findByRole('button', { name: /Port strike monitoring/i }));
    expect((screen.getByRole('button', { name: 'Run Now' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/uv run triangulate case rerun case-monitor-1 --from retrieve/)).toBeDefined();

    // Alert tab is an explicit unavailable state, never an empty "healthy" list.
    fireEvent.click(screen.getByRole('tab', { name: 'Alerts' }));
    expect(screen.getByText(/exposes no alert feed/i)).toBeDefined();
    expect(screen.queryByRole('button', { name: /Acknowledge All/i })).toBeNull();
  });

  it('never asserts a most-recent date from an unparseable timestamp', async () => {
    apiMocks.getCases.mockResolvedValue([
      { ...monitoringCase, lastUpdated: 'not-a-real-date' },
    ]);
    renderMonitoring();

    await screen.findByRole('button', { name: /Port strike monitoring/i });

    const label = screen.getByText('Most Recent Valid Recorded Update');
    expect(label.nextElementSibling?.textContent).toBe(
      'Unknown (unparseable recorded timestamp)'
    );
    expect(screen.queryByText(/Invalid Date/)).toBeNull();
  });

  it('claims no scheduling, alerting or governance capability it does not have', async () => {
    apiMocks.getCases.mockResolvedValue([monitoringCase]);
    renderMonitoring();
    await screen.findByRole('button', { name: /Port strike monitoring/i });

    expect(screen.queryByText(/Real-time/i)).toBeNull();
    expect(screen.queryByText(/Notifications/i)).toBeNull();
    expect(screen.queryByText(/RBAC|role-based/i)).toBeNull();
    expect(screen.queryByText(/WebSocket/i)).toBeNull();
    expect(screen.queryByText(/Deploy/i)).toBeNull();

    // Every scheduling mention is a disclosure, never a value or a feature.
    const schedulingMentions = screen.getAllByText(/Schedul/i);
    expect(schedulingMentions.length).toBeGreaterThan(0);
    for (const mention of schedulingMentions) {
      const container = mention.closest('.monitoring-stats, .monitoring-subtitle');
      expect(container?.textContent ?? '').toMatch(/Not provided by the API|not exposed/i);
    }
  });

  it('labels client fetch time and recorded observation time distinctly', async () => {
    apiMocks.getCases.mockResolvedValue([monitoringCase]);
    renderMonitoring();
    await screen.findByRole('button', { name: /Port strike monitoring/i });

    const fetched = screen.getByTestId('monitoring-last-fetched');
    const observed = screen.getByTestId('monitoring-last-observed');

    expect(fetched.textContent).toContain('Last fetched');
    expect(fetched.textContent).toContain('client request time');
    expect(observed.textContent).toContain('Last observed');
    expect(observed.textContent).toContain('newest timestamp recorded on a case');
    expect(observed.textContent).toContain(new Date('2026-03-19T10:00:00Z').toLocaleString());
    expect(fetched).not.toBe(observed);
  });

  it('renders monitoring-unavailable distinctly from an empty result', async () => {
    apiMocks.getCases.mockResolvedValue([]);
    renderMonitoring();

    expect(await screen.findByText('No monitoring cases recorded')).toBeDefined();

    const empty = document.querySelector('[data-state="monitoring-empty"]');
    expect(empty).not.toBeNull();
    expect(empty?.textContent).toContain('not a healthy system check');

    const unavailable = Array.from(
      document.querySelectorAll('[data-state="monitoring-unavailable"]')
    );
    expect(unavailable).toHaveLength(2);
    for (const node of unavailable) {
      expect(node.textContent).toContain('Not provided by the API');
      expect(node.getAttribute('data-state')).not.toBe('monitoring-empty');
    }
    expect(screen.queryByText('No alerts')).toBeNull();
  });

  it('stops polling while the tab is hidden and resumes when it is visible again', async () => {
    vi.useFakeTimers();
    apiMocks.getCases.mockResolvedValue([monitoringCase]);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <MonitoringCenter />
      </QueryClientProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(apiMocks.getCases).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(95000);
    });
    const pollsWhileVisible = apiMocks.getCases.mock.calls.length;
    expect(pollsWhileVisible).toBeGreaterThan(1);

    setVisibility('hidden');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(180000);
    });
    expect(apiMocks.getCases).toHaveBeenCalledTimes(pollsWhileVisible);

    setVisibility('visible');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(apiMocks.getCases.mock.calls.length).toBeGreaterThan(pollsWhileVisible);
  });

  it('keeps tabs keyboard operable with aria-selected', async () => {
    apiMocks.getCases.mockResolvedValue([monitoringCase]);
    renderMonitoring();
    await screen.findByRole('button', { name: /Port strike monitoring/i });

    const performanceTab = screen.getByRole('tab', { name: 'Performance' });
    expect(performanceTab.getAttribute('aria-selected')).toBe('false');
    fireEvent.click(performanceTab);
    expect(performanceTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText(/exposes no response-time/i)).toBeDefined();
  });
});
