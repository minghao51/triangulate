import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { RunHistoryItem } from '../types/backend-models';
import { getCaseDetail, getRunHistoryForCase } from '../services/api';
import { PipelineFlow } from '../components/data-visualization/PipelineFlow';
import Card, { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';
import Button from '../components/design-system/Button';
import Badge from '../components/design-system/Badge';
import { useVisibleRefetchInterval } from '../components/design-system/reader-polling';
import './PipelineMonitor.css';

/**
 * Pipeline monitor.
 *
 * Shows only persisted case state and saved stage-attempt history. The read API
 * exposes no live log/event stream, so this page never renders a synthetic log
 * timeline or claims "real-time" execution. Every history-derived value is
 * withheld while history is loading or unavailable.
 */

const isValidDuration = (value: number | null | undefined): value is number =>
  value !== null && value !== undefined && Number.isFinite(value) && value >= 0;

const formatDuration = (durationMs: number | null): string => {
  // A recorded zero-duration attempt is real data, not a missing value.
  if (durationMs === null || durationMs === undefined) return 'Not recorded';
  if (!Number.isFinite(durationMs) || durationMs < 0) return 'Invalid duration';
  return `${(durationMs / 1000).toFixed(2)}s`;
};

const averageDuration = (runs: RunHistoryItem[]): string => {
  // Only known, finite, non-negative durations feed the average; 0 is valid.
  const recorded = runs.map((run) => run.durationMs).filter(isValidDuration);

  if (recorded.length === 0) return 'Not recorded';
  const total = recorded.reduce((sum, value) => sum + value, 0);
  const average = total / recorded.length;
  if (!Number.isFinite(average)) return 'Not recorded';
  return `${(average / 1000).toFixed(2)}s`;
};

const statusColor = (status: RunHistoryItem['status']): string => {
  switch (status) {
    case 'success': return 'var(--status-success)';
    case 'error': return 'var(--status-danger)';
    case 'running': return 'var(--accent-primary)';
    default: return 'var(--text-tertiary)';
  }
};

const PipelineMonitor: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [autoRefresh, setAutoRefresh] = useState(true);
  // One 5 s budget shared by both reads, cancelled while the tab is hidden and
  // switched off entirely when the operator unchecks polling.
  const pollInterval = useVisibleRefetchInterval(5000, autoRefresh);

  const {
    data: caseData,
    isLoading: caseLoading,
    error: caseError,
    refetch: refetchCase,
    isFetching: caseFetching,
    dataUpdatedAt: caseUpdatedAt,
  } = useQuery({
    queryKey: ['case-detail', id],
    queryFn: () => getCaseDetail(id!),
    enabled: !!id,
    refetchInterval: pollInterval,
  });

  const {
    data: runHistory,
    isLoading: historyLoading,
    error: historyError,
    refetch: refetchHistory,
  } = useQuery({
    queryKey: ['run-history', id],
    queryFn: () => getRunHistoryForCase(id!),
    enabled: !!id,
    refetchInterval: pollInterval,
  });

  // History-derived values are only published for a successful, available read.
  const historyAvailable = !historyLoading && !historyError && runHistory !== undefined;
  const recordedRuns = runHistory ?? [];
  const unknownValue = '—';

  const currentStage = caseData?.case?.stage ?? null;

  // "Last fetched" is the client's own request time. "Last observed" is the
  // newest timestamp recorded on a saved attempt — a server-side fact.
  const lastFetched =
    Number.isFinite(caseUpdatedAt) && caseUpdatedAt > 0
      ? new Date(caseUpdatedAt).toLocaleTimeString()
      : '—';
  const observedTimestamps = recordedRuns
    .map((run) => (run.timestamp ? Date.parse(run.timestamp) : Number.NaN))
    .filter((value) => Number.isFinite(value));
  const hasUnparseableObserved =
    historyAvailable &&
    recordedRuns.some((run) => run.timestamp && !Number.isFinite(Date.parse(run.timestamp)));
  const lastObserved = !historyAvailable
    ? unknownValue
    : hasUnparseableObserved
      ? 'Unknown (unparseable recorded timestamp)'
      : observedTimestamps.length === 0
        ? 'Never recorded'
        : new Date(Math.max(...observedTimestamps)).toLocaleString();
  const distinctStages = new Set(recordedRuns.map((run) => run.stage)).size;
  const succeeded = recordedRuns.filter((run) => run.status === 'success').length;
  const errored = recordedRuns.filter((run) => run.status === 'error').length;

  return (
    <div className="pipeline-monitor">
      <div className="pipeline-monitor-header">
        <div>
          <h1>Pipeline Monitor</h1>
          <p className="pipeline-monitor-subtitle">
            Recorded case stage and saved stage attempts. Polls the read API; it does not stream
            live execution.
          </p>
        </div>
        <div className="pipeline-monitor-controls">
          <Button
            variant="secondary"
            disabled={!id}
            title={!id ? 'No case ID in the route' : undefined}
            onClick={() => { void refetchCase(); void refetchHistory(); }}
            loading={caseFetching}
          >
            Refresh
          </Button>
          <label className="pipeline-monitor-toggle">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(event) => setAutoRefresh(event.target.checked)}
            />
            <span>Poll saved data (5s)</span>
          </label>
        </div>
      </div>

      <p className="pipeline-monitor-subtitle">
        <span data-testid="pipeline-last-fetched">
          <strong>Last fetched</strong> {lastFetched} (client request time)
        </span>
        {' · '}
        <span data-testid="pipeline-last-observed">
          <strong>Last observed</strong> {lastObserved} (newest timestamp saved on an attempt)
        </span>
      </p>

      {!id ? (
        <Card>
          <CardBody>
            <div className="pipeline-monitor-state" role="alert">
              No case ID in the route. Open
              <code> /cases/&lt;case-id&gt;/pipeline</code> to view recorded pipeline state.
            </div>
          </CardBody>
        </Card>
      ) : caseLoading ? (
        <Card>
          <CardBody>
            <div className="pipeline-monitor-state" role="status">Loading recorded pipeline state…</div>
          </CardBody>
        </Card>
      ) : caseError ? (
        <Card>
          <CardBody>
            <div className="pipeline-monitor-state pipeline-monitor-state--error" role="alert">
              <p>
                Failed to load case pipeline state
                {caseError instanceof Error && caseError.message ? `: ${caseError.message}` : '.'}
              </p>
              <Button variant="secondary" onClick={() => refetchCase()}>Retry</Button>
            </div>
          </CardBody>
        </Card>
      ) : !currentStage ? (
        <Card>
          <CardBody>
            <div
              className="pipeline-monitor-state"
              role="alert"
              data-state="pipeline-unrecorded"
            >
              <Badge variant="warning" size="sm">Not recorded</Badge>
              <p>
                No pipeline stage is recorded for this case. Nothing is assumed about its
                progress — this is an absent record, not an empty attempt list.
              </p>
            </div>
          </CardBody>
        </Card>
      ) : (
        <>
          {historyLoading ? (
            <Card>
              <CardBody>
                <div className="pipeline-monitor-state" role="status">
                  Recorded case stage: <strong>{currentStage}</strong>. Loading saved stage attempts…
                </div>
              </CardBody>
            </Card>
          ) : historyError ? (
            <Card>
              <CardBody>
                <div className="pipeline-monitor-state pipeline-monitor-state--error" role="alert">
                  <p>
                    Recorded case stage: <strong>{currentStage}</strong>. Saved stage attempts are
                    unavailable
                    {historyError instanceof Error && historyError.message
                      ? ` (${historyError.message})`
                      : ''}
                    , so stage execution status is unknown.
                  </p>
                  <Button variant="secondary" onClick={() => refetchHistory()}>Retry run history</Button>
                </div>
              </CardBody>
            </Card>
          ) : (
            <>
              <p className="pipeline-monitor-subtitle">
                Stage order below is <strong>configured</strong> workflow order. A stage&apos;s
                completion state is only ever shown as <strong>recorded</strong> when a saved
                stage attempt says so.
              </p>
              <PipelineFlow currentStage={currentStage} runHistory={recordedRuns} />
            </>
          )}

          <div className="pipeline-monitor-metrics">
            <Card padding="sm">
              <CardBody>
                <div className="pipeline-monitor-metric-label">Recorded Attempts</div>
                <div className="pipeline-monitor-metric-value">
                  {historyAvailable ? recordedRuns.length : unknownValue}
                </div>
              </CardBody>
            </Card>
            <Card padding="sm">
              <CardBody>
                <div className="pipeline-monitor-metric-label">Distinct Stages Recorded</div>
                <div className="pipeline-monitor-metric-value">
                  {historyAvailable ? distinctStages : unknownValue}
                </div>
              </CardBody>
            </Card>
            <Card padding="sm">
              <CardBody>
                <div className="pipeline-monitor-metric-label">Succeeded</div>
                <div className="pipeline-monitor-metric-value pipeline-monitor-metric-value--success">
                  {historyAvailable ? succeeded : unknownValue}
                </div>
              </CardBody>
            </Card>
            <Card padding="sm">
              <CardBody>
                <div className="pipeline-monitor-metric-label">Errors</div>
                <div className="pipeline-monitor-metric-value pipeline-monitor-metric-value--error">
                  {historyAvailable ? errored : unknownValue}
                </div>
              </CardBody>
            </Card>
            <Card padding="sm">
              <CardBody>
                <div className="pipeline-monitor-metric-label">Avg Recorded Duration</div>
                <div className="pipeline-monitor-metric-value pipeline-monitor-metric-value--text">
                  {historyAvailable ? averageDuration(recordedRuns) : unknownValue}
                </div>
              </CardBody>
            </Card>
          </div>

          <div className="pipeline-monitor-panels">
            <Card>
              <CardHeader>
                <CardTitle>Log Stream</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="pipeline-monitor-state pipeline-monitor-state--unavailable" role="status">
                  <Badge variant="neutral" size="sm">Unavailable</Badge>
                  <p>
                    The read API returns saved stage attempts, not a log or event stream, so no log
                    lines, log levels or live tail are shown here.
                  </p>
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Recorded Stage Attempts</CardTitle>
              </CardHeader>
              <CardBody>
                {historyLoading ? (
                  <div className="pipeline-monitor-state" role="status">Loading saved stage attempts…</div>
                ) : historyError ? (
                  <div className="pipeline-monitor-state pipeline-monitor-state--error">
                    Saved stage attempts are unavailable, so no attempt list is shown.
                  </div>
                ) : recordedRuns.length === 0 ? (
                  <div
                    className="pipeline-monitor-state"
                    role="status"
                    data-state="pipeline-attempts-empty"
                  >
                    No stage attempts are recorded for this case yet. The recorded case stage is
                    shown above; this panel is an empty attempt list, not a missing record.
                  </div>
                ) : (
                  <ul className="pipeline-monitor-runs">
                    {recordedRuns.map((run) => (
                      <li key={run.id} className="pipeline-monitor-run">
                        <span className="pipeline-monitor-run-dot" style={{ backgroundColor: statusColor(run.status) }} />
                        <span className="pipeline-monitor-run-main">
                          <span className="pipeline-monitor-run-stage">{run.stage}</span>
                          <span className="pipeline-monitor-run-model">{run.model || 'Model not recorded'}</span>
                        </span>
                        <span className="pipeline-monitor-run-side">
                          <span className="pipeline-monitor-run-duration">{formatDuration(run.durationMs)}</span>
                          <span className="pipeline-monitor-run-status">
                            {run.status}
                            {run.fallbackCount > 0 ? ` · ${run.fallbackCount} fallback` : ''}
                          </span>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </div>
  );
};

export default PipelineMonitor;
