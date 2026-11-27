import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation, useParams } from 'react-router-dom';

import ReportTab from './ReportTab';
import { ApiError } from '../../services/api-error';
import type {
  ArtifactDescriptor,
  InvestigationRun,
  InvestigationRunList,
  ReportData,
  RunHistoryItem,
} from '../../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getReportForCase: vi.fn(),
  getRunHistoryForCase: vi.fn(),
  getInvestigationRuns: vi.fn(),
  getInvestigationRunArtifacts: vi.fn(),
  downloadMarkdownReport: vi.fn(),
  downloadManifestReport: vi.fn(),
  downloadInvestigationRunArtifact: vi.fn(),
}));

vi.mock('../../services/api', () => apiMocks);

/** The report tab lives on a router route, so a pin is a real URL. */
const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
};

const ReportRoute = () => {
  const { id } = useParams();
  return <ReportTab caseId={id ?? ''} />;
};

const storedReport = (overrides: Partial<ReportData> = {}): ReportData => ({
  status: 'generated',
  markdownPath: '/data/case-1/topic_report.md',
  markdownContent: '# Case one report\n\n## Findings\n\nA paragraph of stored text.\n',
  manifestPath: '/data/case-1/manifest.json',
  ...overrides,
});

/** The API's own `status: 'pending'` alone is not evidence of an in-progress run. */
const pendingToTheApiOnly = (): ReportData => ({
  status: 'pending',
  markdownPath: null,
  markdownContent: null,
  manifestPath: null,
});

const makeRun = (overrides: Partial<RunHistoryItem> = {}): RunHistoryItem => ({
  id: 'stage-1',
  stage: 'REPORT',
  model: null,
  durationMs: null,
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

/** Exactly the F19 descriptor shape; no path field exists to leak. */
const descriptorsForRun = (runId: string): ArtifactDescriptor[] => [
  {
    artifactId: 'artifact-manifest',
    type: 'execution_manifest',
    displayName: 'manifest.json',
    downloadUrl: `/api/cases/case-1/investigation-runs/${runId}/artifacts/artifact-manifest`,
    recordedChecksum: 'sha-manifest-recorded',
    checksumKind: 'payload_json',
  },
  {
    artifactId: 'artifact-json',
    type: 'report_json',
    displayName: 'topic_analysis.json',
    downloadUrl: `/api/cases/case-1/investigation-runs/${runId}/artifacts/artifact-json`,
    recordedChecksum: 'sha-json-recorded',
    checksumKind: 'payload_json',
  },
  {
    artifactId: 'artifact-md',
    type: 'report_markdown',
    displayName: 'topic_report.md',
    downloadUrl: `/api/cases/case-1/investigation-runs/${runId}/artifacts/artifact-md`,
    recordedChecksum: 'sha-markdown-recorded',
    checksumKind: 'unknown',
  },
];

const newClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });

function renderTab(caseId = 'case-1', refreshToken = 0, queryClient: QueryClient = newClient()) {
  const ui = (id: string, token: number) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/cases/${id}/report`]}>
        <ReportTab caseId={id} refreshToken={token} />
      </MemoryRouter>
    </QueryClientProvider>
  );
  const result = render(ui(caseId, refreshToken));
  return {
    ...result,
    queryClient,
    rerenderTab: (id: string, token = 0) => result.rerender(ui(id, token)),
  };
}

/** Render the tab on its real route so a pin is addressable and reloadable. */
function renderRoute(entry: string, queryClient: QueryClient = newClient()) {
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route
            path="/cases/:id/report"
            element={
              <>
                <LocationProbe />
                <ReportRoute />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { ...result, queryClient };
}

const forbiddenCopy = /latest|historical|most recent|previous report|most-recent|republish/i;

// Defaults for every reader the tab can reach. Each describe below overrides
// only what its own case needs.
beforeEach(() => {
  vi.resetAllMocks();
  apiMocks.downloadMarkdownReport.mockResolvedValue(undefined);
  apiMocks.downloadManifestReport.mockResolvedValue(undefined);
  apiMocks.downloadInvestigationRunArtifact.mockResolvedValue(undefined);
  apiMocks.getInvestigationRuns.mockResolvedValue(groupedList([]));
  apiMocks.getInvestigationRunArtifacts.mockResolvedValue([]);
});

describe('ReportTab truthful state model', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.downloadMarkdownReport.mockResolvedValue(undefined);
    apiMocks.downloadManifestReport.mockResolvedValue(undefined);
  });

  it('labels Pending only when a recorded stage attempt is in progress', async () => {
    apiMocks.getReportForCase.mockResolvedValue(pendingToTheApiOnly());
    apiMocks.getRunHistoryForCase.mockResolvedValue([makeRun({ status: 'running' })]);

    renderTab();

    const pendingPanel = await screen.findByTestId('report-state-pending');
    expect(pendingPanel.textContent).toContain('Pending');
    expect(screen.queryByTestId('report-state-not-generated')).toBeNull();
    expect(screen.queryByTestId('report-state-unavailable')).toBeNull();
  });

  it('shows Not generated (never Pending) when no attempt is recorded', async () => {
    apiMocks.getReportForCase.mockResolvedValue(pendingToTheApiOnly());
    apiMocks.getRunHistoryForCase.mockResolvedValue([makeRun({ status: 'success' })]);

    const { container } = renderTab();

    await screen.findByTestId('report-state-not-generated');
    expect(container.textContent).toContain('Not generated');
    expect(container.textContent).not.toMatch(/pending/i);
    expect(screen.queryByTestId('report-state-pending')).toBeNull();
  });

  it('pairs the two cases: identical report payload, different recorded history', async () => {
    apiMocks.getReportForCase.mockResolvedValue(pendingToTheApiOnly());
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);

    const first = renderTab();
    await screen.findByTestId('report-state-not-generated');
    first.unmount();

    apiMocks.getRunHistoryForCase.mockResolvedValue([makeRun({ status: 'pending' })]);
    renderTab();
    await screen.findByTestId('report-state-pending');
  });
});

describe('ReportTab read and download recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.downloadMarkdownReport.mockResolvedValue(undefined);
    apiMocks.downloadManifestReport.mockResolvedValue(undefined);
  });

  it('shows Unavailable (not Pending) when a generated record carries no readable text', async () => {
    apiMocks.getReportForCase.mockResolvedValue(
      storedReport({ markdownContent: null, markdownPath: null, manifestPath: null })
    );
    apiMocks.getRunHistoryForCase.mockResolvedValue([makeRun()]);

    renderTab();

    const state = await screen.findByTestId('report-state-unavailable');
    expect(state.textContent).toContain('Unavailable');
    expect(state.textContent).toContain('no readable text');
    expect(screen.queryByTestId('report-state-pending')).toBeNull();
  });

  it('shows a distinct read-error state with a working retry read', async () => {
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);
    apiMocks.getReportForCase
      .mockRejectedValueOnce(new Error('report read failed'))
      .mockResolvedValue(storedReport());

    const { container } = renderTab();

    const state = await screen.findByTestId('report-state-unavailable');
    expect(state.textContent).toContain('Unavailable');
    expect(state.textContent).toContain('report read failed');
    expect(screen.queryByTestId('report-state-not-generated')).toBeNull();
    expect(container.textContent).not.toMatch(/pending/i);

    fireEvent.click(screen.getByRole('button', { name: 'Retry read' }));

    await waitFor(() => expect(apiMocks.getReportForCase).toHaveBeenCalledTimes(2));
    await screen.findByTestId('report-content');
    expect(screen.queryByTestId('report-state-unavailable')).toBeNull();
  });

  it('shows a distinct empty state whose retry read re-reads', async () => {
    apiMocks.getReportForCase.mockResolvedValue(pendingToTheApiOnly());
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);

    renderTab();

    const state = await screen.findByTestId('report-state-not-generated');
    expect(state.textContent).toContain('Not generated');
    expect(screen.queryByTestId('report-state-unavailable')).toBeNull();

    fireEvent.click(screen.getByTestId('report-retry-read'));

    await waitFor(() => expect(apiMocks.getReportForCase).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId('report-state-unavailable')).toBeNull();
  });

  it('shows a distinct download-error state with its own retry download', async () => {
    apiMocks.getReportForCase.mockResolvedValue(storedReport());
    apiMocks.getRunHistoryForCase.mockResolvedValue([makeRun()]);
    apiMocks.downloadMarkdownReport
      .mockRejectedValueOnce(new Error('markdown download failed'))
      .mockResolvedValueOnce(undefined);

    renderTab();
    await screen.findByTestId('report-content');

    fireEvent.click(screen.getByTestId('report-download-markdown'));

    const failure = await screen.findByTestId('report-download-error');
    expect(failure.textContent).toContain('Download error');
    expect(failure.textContent).toContain('markdown download failed');
    // A failed download is not a failed read: the report stays readable.
    expect(screen.queryByTestId('report-state-unavailable')).toBeNull();
    expect(screen.getByTestId('report-content')).toBeDefined();
    expect(apiMocks.downloadManifestReport).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('report-retry-download'));

    await waitFor(() => expect(apiMocks.downloadMarkdownReport).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByTestId('report-download-error')).toBeNull());
  });

  it('uses exactly the two existing download functions with the case id', async () => {
    apiMocks.getReportForCase.mockResolvedValue(storedReport());
    apiMocks.getRunHistoryForCase.mockResolvedValue([makeRun()]);

    renderTab();
    await screen.findByTestId('report-content');

    fireEvent.click(screen.getByTestId('report-download-markdown'));
    await waitFor(() => expect(apiMocks.downloadMarkdownReport).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect((screen.getByTestId('report-download-manifest') as HTMLButtonElement).disabled).toBe(
        false
      )
    );

    fireEvent.click(screen.getByTestId('report-download-manifest'));
    await waitFor(() => expect(apiMocks.downloadManifestReport).toHaveBeenCalledTimes(1));

    expect(apiMocks.downloadMarkdownReport).toHaveBeenCalledWith('case-1');
    expect(apiMocks.downloadManifestReport).toHaveBeenCalledWith('case-1');
    expect(apiMocks.downloadMarkdownReport).toHaveBeenCalledTimes(1);
  });

  it('disables each download when its stored path is absent', async () => {
    apiMocks.getReportForCase.mockResolvedValue(
      storedReport({ markdownPath: null, manifestPath: '/data/case-1/manifest.json' })
    );
    apiMocks.getRunHistoryForCase.mockResolvedValue([makeRun()]);

    renderTab();
    await screen.findByTestId('report-content');

    expect((screen.getByTestId('report-download-markdown') as HTMLButtonElement).disabled).toBe(
      true
    );
    expect((screen.getByTestId('report-download-manifest') as HTMLButtonElement).disabled).toBe(
      false
    );
  });
});

describe('ReportTab safe markdown rendering', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getRunHistoryForCase.mockResolvedValue([makeRun()]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders headings, lists and blockquotes as semantic elements', async () => {
    apiMocks.getReportForCase.mockResolvedValue(
      storedReport({
        markdownContent: [
          '# Case report',
          '',
          '## Findings',
          '',
          '### Detail',
          '',
          'A paragraph of stored text with **emphasis**.',
          '',
          '- first bullet',
          '- second bullet',
          '',
          '> A recorded quotation.',
          '',
          '1. ordered one',
          '2. ordered two',
        ].join('\n'),
      })
    );

    const { container } = renderTab();
    await screen.findByTestId('report-content');

    expect(screen.getByRole('heading', { level: 1, name: 'Case report' })).toBeDefined();
    expect(screen.getByRole('heading', { level: 2, name: 'Findings' })).toBeDefined();
    expect(screen.getByRole('heading', { level: 3, name: 'Detail' })).toBeDefined();
    expect(screen.getAllByRole('list')).toHaveLength(2);
    expect(screen.getAllByRole('listitem')).toHaveLength(4);
    expect(container.querySelector('blockquote')?.textContent).toContain('A recorded quotation.');
    expect(container.querySelector('strong')?.textContent).toBe('emphasis');
    expect(container.querySelector('h1')?.dataset.testid).toBe('report-heading-1');
  });

  it('renders an XSS payload as inert visible text and executes nothing', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    apiMocks.getReportForCase.mockResolvedValue(
      storedReport({
        markdownContent: [
          '# Report',
          '',
          '<script>alert(1)</script>',
          '',
          '<img src=x onerror="alert(2)">',
          '',
          '[click](javascript:alert(3))',
        ].join('\n'),
      })
    );

    const { container } = renderTab();
    await screen.findByTestId('report-content');

    expect(screen.getByText('<script>alert(1)</script>')).toBeDefined();
    expect(screen.getByText('<img src=x onerror="alert(2)">')).toBeDefined();

    await act(async () => {
      await Promise.resolve();
    });

    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelectorAll('a')).toHaveLength(0);
    expect(alertSpy).not.toHaveBeenCalled();
  });

  it('never claims a historical or "latest" report', async () => {
    apiMocks.getReportForCase.mockResolvedValue(storedReport());

    const generated = renderTab();
    await screen.findByTestId('report-content');
    expect(generated.container.textContent).not.toMatch(forbiddenCopy);
    generated.unmount();

    apiMocks.getReportForCase.mockResolvedValue(pendingToTheApiOnly());
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);
    const missing = renderTab();
    await screen.findByTestId('report-state-not-generated');
    expect(missing.container.textContent).not.toMatch(forbiddenCopy);
    missing.unmount();

    apiMocks.getRunHistoryForCase.mockResolvedValue([makeRun({ status: 'running' })]);
    const pending = renderTab();
    await screen.findByTestId('report-state-pending');
    expect(pending.container.textContent).not.toMatch(forbiddenCopy);
  });
});

describe('ReportTab case scoping', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.downloadMarkdownReport.mockResolvedValue(undefined);
    apiMocks.downloadManifestReport.mockResolvedValue(undefined);
    apiMocks.getRunHistoryForCase.mockResolvedValue([]);
  });

  it('never renders another case report after a case switch', async () => {
    let resolveCaseOne: (value: ReportData) => void = () => {};
    apiMocks.getReportForCase.mockImplementation((id: string) => {
      if (id === 'case-1') {
        return new Promise<ReportData>((resolve) => {
          resolveCaseOne = resolve;
        });
      }
      return Promise.resolve(storedReport({ markdownContent: '# Case two report\n' }));
    });

    const { rerenderTab } = renderTab('case-1');
    rerenderTab('case-2');

    await screen.findByText('Case two report');

    await act(async () => {
      resolveCaseOne(storedReport({ markdownContent: '# Case one report\n' }));
    });

    expect(screen.queryByText('Case one report')).toBeNull();
    expect(screen.getByText('Case two report')).toBeDefined();
  });

  it('treats refreshToken as a refetch trigger, not a cache key', async () => {
    apiMocks.getReportForCase.mockResolvedValue(storedReport());

    const { rerenderTab, queryClient } = renderTab('case-1', 0);
    await screen.findByTestId('report-content');
    expect(apiMocks.getReportForCase).toHaveBeenCalledTimes(1);

    rerenderTab('case-1', 1);

    await waitFor(() => expect(apiMocks.getReportForCase).toHaveBeenCalledTimes(2));
    expect(queryClient.getQueryData(['report', 'case-1'])).toBeDefined();
    expect(queryClient.getQueryData(['report', 'case-1', 1])).toBeUndefined();
  });
});

describe('ReportTab current report default (X02/F20)', () => {
  it('keeps the current report as the default and offers a pin only as an explicit link', async () => {
    apiMocks.getReportForCase.mockResolvedValue(storedReport());
    apiMocks.getRunHistoryForCase.mockResolvedValue([makeRun()]);
    apiMocks.getInvestigationRuns.mockResolvedValue(groupedList([makeGroupedRun()]));

    renderRoute('/cases/case-1/report');

    await screen.findByTestId('report-content');
    // No pin is implied: no artifact read happens on the current view.
    expect(apiMocks.getInvestigationRunArtifacts).not.toHaveBeenCalled();
    expect(screen.queryByTestId('report-pinned-run')).toBeNull();
    expect(screen.getByTestId('location').textContent).toBe('/cases/case-1/report');
    expect(screen.getByTestId('report-pin-picker').textContent).toContain(
      'stays the default'
    );

    const pinLink = await screen.findByTestId('report-pin-link-grouped-run-1');
    expect(pinLink.getAttribute('href')).toBe('/cases/case-1/report?reportRun=grouped-run-1');
    expect(pinLink.textContent).toContain('View frozen report');
  });
});

describe('ReportTab pinned run (X02/F20)', () => {
  it('lists exactly the recorded F19 descriptors of the pinned run and requests nothing else', async () => {
    apiMocks.getInvestigationRunArtifacts.mockResolvedValue(descriptorsForRun('run-2'));

    renderRoute('/cases/case-1/report?reportRun=run-2');

    const list = await screen.findByTestId('report-artifact-list');
    const rows = within(list).getAllByTestId('report-artifact');
    expect(rows).toHaveLength(3);
    expect(rows.map((row) => row.getAttribute('data-artifact-id'))).toEqual([
      'artifact-manifest',
      'artifact-json',
      'artifact-md',
    ]);
    expect(rows.map((row) => row.getAttribute('data-artifact-type'))).toEqual([
      'execution_manifest',
      'report_json',
      'report_markdown',
    ]);
    expect(
      within(list).getAllByTestId('report-artifact-checksum').map((node) => node.textContent)
    ).toEqual(['sha-manifest-recorded', 'sha-json-recorded', 'sha-markdown-recorded']);

    const kinds = within(list).getAllByTestId('report-artifact-checksum-kind');
    expect(kinds[0].textContent).toContain('payload_json');
    expect(kinds[2].textContent).toContain('unknown');
    expect(list.textContent).toContain('manifest.json');
    expect(list.textContent).toContain('topic_analysis.json');
    expect(list.textContent).toContain('topic_report.md');

    // Exactly one F19 read, for exactly the pinned run.
    expect(apiMocks.getInvestigationRunArtifacts).toHaveBeenCalledTimes(1);
    expect(apiMocks.getInvestigationRunArtifacts).toHaveBeenCalledWith('case-1', 'run-2');
    // Nothing else is requested on a pinned view.
    expect(apiMocks.getReportForCase).not.toHaveBeenCalled();
    expect(apiMocks.getRunHistoryForCase).not.toHaveBeenCalled();
    expect(apiMocks.getInvestigationRuns).not.toHaveBeenCalled();
    expect(apiMocks.downloadMarkdownReport).not.toHaveBeenCalled();
    expect(apiMocks.downloadManifestReport).not.toHaveBeenCalled();
    expect(apiMocks.downloadInvestigationRunArtifact).not.toHaveBeenCalled();
    // The current report body is not rendered on a pinned view.
    expect(screen.queryByTestId('report-content')).toBeNull();
  });

  it('switches current↔pin only through explicit links and survives a reload', async () => {
    apiMocks.getReportForCase.mockResolvedValue(storedReport());
    apiMocks.getRunHistoryForCase.mockResolvedValue([makeRun()]);
    apiMocks.getInvestigationRuns.mockResolvedValue(groupedList([makeGroupedRun()]));
    apiMocks.getInvestigationRunArtifacts.mockResolvedValue(descriptorsForRun('grouped-run-1'));

    const first = renderRoute('/cases/case-1/report');
    await screen.findByTestId('report-content');
    expect(screen.queryByTestId('report-pinned-run')).toBeNull();

    fireEvent.click(await screen.findByTestId('report-pin-link-grouped-run-1'));

    await screen.findByTestId('report-artifact-list');
    expect(screen.getByTestId('location').textContent).toBe(
      '/cases/case-1/report?reportRun=grouped-run-1'
    );
    expect(screen.getByTestId('report-pinned-run-id').textContent).toBe('grouped-run-1');
    expect(screen.queryByTestId('report-content')).toBeNull();
    // The current report is not read while a run is pinned.
    expect(apiMocks.getReportForCase).toHaveBeenCalledTimes(1);
    first.unmount();

    // Reload: the same URL reproduces exactly the same pinned run.
    const reloaded = renderRoute('/cases/case-1/report?reportRun=grouped-run-1');
    await screen.findByTestId('report-artifact-list');
    expect(screen.getByTestId('report-pinned-run-id').textContent).toBe('grouped-run-1');
    expect(apiMocks.getInvestigationRunArtifacts).toHaveBeenCalledTimes(2);
    expect(apiMocks.getInvestigationRunArtifacts).toHaveBeenLastCalledWith(
      'case-1',
      'grouped-run-1'
    );
    expect(apiMocks.getReportForCase).toHaveBeenCalledTimes(1);

    // Back to current is an explicit control, never an implicit substitution.
    fireEvent.click(screen.getByTestId('report-back-to-current'));

    await screen.findByTestId('report-content');
    expect(screen.getByTestId('location').textContent).toBe('/cases/case-1/report');
    expect(screen.queryByTestId('report-pinned-run')).toBeNull();
    expect(apiMocks.getReportForCase).toHaveBeenCalledTimes(2);
    reloaded.unmount();
  });

  it('renders the F19 404 as a distinct missing-artifact state with no substitute content', async () => {
    apiMocks.getInvestigationRunArtifacts.mockResolvedValue(descriptorsForRun('run-2'));
    apiMocks.downloadInvestigationRunArtifact.mockRejectedValue(
      new ApiError('Artifact not found for this case and run', 404)
    );

    const { container } = renderRoute('/cases/case-1/report?reportRun=run-2');
    await screen.findByTestId('report-artifact-list');

    fireEvent.click(screen.getByTestId('report-artifact-download-report_markdown'));

    const missing = await screen.findByTestId('report-state-artifact-missing');
    expect(missing.getAttribute('data-report-state')).toBe('artifact-missing');
    expect(missing.textContent).toContain('Artifact missing');
    expect(missing.textContent).toContain('topic_report.md');
    expect(missing.textContent).toContain('Artifact not found for this case and run');

    // No substitute content of any kind.
    expect(screen.queryByTestId('report-content')).toBeNull();
    expect(apiMocks.getReportForCase).not.toHaveBeenCalled();
    expect(apiMocks.downloadMarkdownReport).not.toHaveBeenCalled();
    expect(apiMocks.downloadManifestReport).not.toHaveBeenCalled();
    expect(container.textContent).not.toMatch(/latest|most recent|previous report/i);

    // Only a re-read is offered: descriptors are re-read, no download is repeated.
    fireEvent.click(screen.getByTestId('report-artifact-retry-read'));
    await waitFor(() =>
      expect(apiMocks.getInvestigationRunArtifacts).toHaveBeenCalledTimes(2)
    );
    expect(apiMocks.downloadInvestigationRunArtifact).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByTestId('report-state-artifact-missing')).toBeNull());
    // The descriptor record is still shown; nothing was regenerated.
    expect(screen.getByTestId('report-artifact-list')).toBeDefined();
  });

  it('separates an unknown run from a recorded run with no published report', async () => {
    apiMocks.getInvestigationRunArtifacts.mockRejectedValue(
      new ApiError('Artifact not found for this case and run', 404)
    );
    const { container } = renderRoute('/cases/case-1/report?reportRun=run-gone');

    const notRecorded = await screen.findByTestId('report-state-run-not-recorded');
    expect(notRecorded.getAttribute('data-report-state')).toBe('run-not-recorded');
    expect(notRecorded.textContent).toContain('Run not recorded');
    expect(screen.queryByTestId('report-artifact-list')).toBeNull();
    expect(screen.queryByTestId('report-content')).toBeNull();
    expect(apiMocks.getReportForCase).not.toHaveBeenCalled();
    expect(container.textContent).not.toMatch(/latest|most recent|previous report/i);
    expect(
      screen.getByRole('link', { name: 'Open the current report' }).getAttribute('href')
    ).toBe('/cases/case-1/report');
    container.remove();
  });

  it('shows no published report for a recorded run whose artifact list is empty', async () => {
    apiMocks.getInvestigationRunArtifacts.mockResolvedValue([]);

    renderRoute('/cases/case-1/report?reportRun=run-2');

    const none = await screen.findByTestId('report-state-run-no-report');
    expect(none.getAttribute('data-report-state')).toBe('run-no-report');
    expect(none.textContent).toContain('No published report for this run');
    expect(screen.queryByTestId('report-state-run-not-recorded')).toBeNull();
    expect(screen.queryByTestId('report-artifact-list')).toBeNull();
    expect(apiMocks.getReportForCase).not.toHaveBeenCalled();
  });

  it('never silently shows the current report for a blank pin', async () => {
    renderRoute('/cases/case-1/report?reportRun=');

    await screen.findByTestId('report-state-run-not-recorded');
    expect(apiMocks.getInvestigationRunArtifacts).not.toHaveBeenCalled();
    expect(apiMocks.getReportForCase).not.toHaveBeenCalled();
    expect(screen.queryByTestId('report-content')).toBeNull();
  });
});

describe('ReportTab artifact provenance honesty (X02/F20)', () => {
  it('labels the stored value a recorded payload checksum and claims no verification', async () => {
    apiMocks.getInvestigationRunArtifacts.mockResolvedValue(descriptorsForRun('run-2'));

    const { container } = renderRoute('/cases/case-1/report?reportRun=run-2');
    await screen.findByTestId('report-artifact-list');

    const text = container.textContent ?? '';
    expect(text).toContain('Recorded payload checksum');
    expect(text).toContain('recorded payload checksum stored at');

    // The stored value is never presented as proof about downloaded bytes.
    expect(text).not.toMatch(/verified\s+(file\s+|bytes\s+|download(ed)?\s+)?checksum/i);
    expect(text).not.toMatch(/checksum\s+(of|for)\s+the\s+(downloaded\s+)?file/i);
    expect(text).not.toMatch(/file\s+hash\s+verified/i);
    // No chain-of-custody or tamper-proof claim of any kind.
    expect(text).not.toMatch(/chain[-\s]?of[-\s]?custody/i);
    expect(text).not.toMatch(/\bcustody\b|\btamper[-\s]?proof\b|\bnotariz/i);
  });

  it('offers only the F19 allowlisted artifact downloads', async () => {
    apiMocks.getInvestigationRunArtifacts.mockResolvedValue(descriptorsForRun('run-2'));

    renderRoute('/cases/case-1/report?reportRun=run-2');
    await screen.findByTestId('report-artifact-list');

    // The current-report download routes are never offered on a pinned view.
    expect(screen.queryByTestId('report-download-markdown')).toBeNull();
    expect(screen.queryByTestId('report-download-manifest')).toBeNull();

    const types = ['report_markdown', 'report_json', 'execution_manifest'];
    for (const type of types) {
      const button = screen.getByTestId(`report-artifact-download-${type}`);
      await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
      fireEvent.click(button);
      await waitFor(() =>
        expect(apiMocks.downloadInvestigationRunArtifact).toHaveBeenCalledTimes(
          types.indexOf(type) + 1
        )
      );
    }

    const calls = apiMocks.downloadInvestigationRunArtifact.mock.calls;
    expect(calls).toHaveLength(3);
    for (const [caseId, runId, descriptor] of calls) {
      expect(caseId).toBe('case-1');
      expect(runId).toBe('run-2');
      expect(['report_markdown', 'report_json', 'execution_manifest']).toContain(
        (descriptor as ArtifactDescriptor).type
      );
    }
    // Never the legacy current-report download endpoints, and no PDF/ZIP offer.
    expect(apiMocks.downloadMarkdownReport).not.toHaveBeenCalled();
    expect(apiMocks.downloadManifestReport).not.toHaveBeenCalled();
    expect(apiMocks.getInvestigationRunArtifacts).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/pdf|zip|bundle/i)).toBeNull();
  });

  it('records an artifact type outside the allowlist as not offered', async () => {
    apiMocks.getInvestigationRunArtifacts.mockResolvedValue([
      ...descriptorsForRun('run-2'),
      {
        artifactId: 'artifact-pdf',
        type: 'report_pdf' as never,
        displayName: 'topic_report.pdf',
        downloadUrl: '/api/cases/case-1/investigation-runs/run-2/artifacts/artifact-pdf',
        recordedChecksum: null,
        checksumKind: 'unknown' as const,
      },
    ]);

    renderRoute('/cases/case-1/report?reportRun=run-2');
    await screen.findByTestId('report-artifact-list');

    expect(screen.getByTestId('report-artifact-not-offered').textContent).toContain(
      'Not an offered artifact type'
    );
    expect(screen.queryByTestId('report-artifact-download-report_pdf')).toBeNull();
    fireEvent.click(screen.getByTestId('report-artifact-download-report_markdown'));
    await waitFor(() =>
      expect(apiMocks.downloadInvestigationRunArtifact).toHaveBeenCalledTimes(1)
    );
    expect(
      (apiMocks.downloadInvestigationRunArtifact.mock.calls[0][2] as ArtifactDescriptor).type
    ).toBe('report_markdown');
  });
});
