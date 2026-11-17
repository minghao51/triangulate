import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getCases } from '../services/api';
import Card, { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';
import Badge from '../components/design-system/Badge';
import Button from '../components/design-system/Button';
import type { TopicCase } from '../types/backend-models';
import './MonitoringCenter.css';

/**
 * Monitoring overview.
 *
 * Only values the read API actually returns are rendered here. The API has no
 * schedule, next-run, alert, acknowledgement or performance endpoints, so those
 * panels state that the data is not provided instead of inventing numbers.
 */

type MonitoringTab = 'monitors' | 'alerts' | 'performance';

const NOT_PROVIDED = 'Not provided by the API';

const UNAVAILABLE_EXPLANATIONS: Record<Exclude<MonitoringTab, 'monitors'>, string> = {
  alerts:
    'The current read API exposes no alert feed, so nothing is listed here. Alert acknowledgement is not available from this UI and no client-side acknowledgement is stored.',
  performance:
    'The current read API exposes no response-time, success-rate or aggregate run metrics for monitoring cases, so no performance values are shown.',
};

const formatTimestamp = (value: string | null): string => {
  if (!value) return 'Never recorded';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? 'Unparseable timestamp' : parsed.toLocaleString();
};

const MonitoringCenter: React.FC = () => {
  const [activeTab, setActiveTab] = useState<MonitoringTab>('monitors');
  const [selectedMonitorId, setSelectedMonitorId] = useState<string | null>(null);

  const {
    data: cases,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['cases'],
    queryFn: () => getCases(),
    refetchInterval: 30000,
  });

  // Only recorded monitoring cases; nothing is synthesised from other statuses.
  const monitors = useMemo(
    () => (cases ?? []).filter((c: TopicCase) => c.status === 'monitoring'),
    [cases]
  );

  // Look the selection up by ID so a changed/removed case can never leave a
  // stale monitor object selected.
  const selectedMonitor = monitors.find((monitor) => monitor.id === selectedMonitorId) ?? null;

  const lastUpdatedValues = monitors
    .map((monitor) => monitor.lastUpdated)
    .filter((value): value is string => Boolean(value));

  // Only parseable timestamps may produce "most recent"; an unparseable value
  // makes the aggregate unknown instead of silently picking an arbitrary row.
  const parsedUpdates = lastUpdatedValues
    .map((value) => Date.parse(value))
    .filter((value) => Number.isFinite(value));
  const hasUnparseableTimestamp = parsedUpdates.length !== lastUpdatedValues.length;
  const newestUpdate =
    !hasUnparseableTimestamp && parsedUpdates.length > 0
      ? new Date(Math.max(...parsedUpdates)).toISOString()
      : null;

  // Counts are only published for a successful, current read. While loading or
  // after an error the value is unknown, so an em dash is shown instead of 0.
  const hasResolvedData = !isLoading && !error && cases !== undefined;
  const unknownValue = '—';

  return (
    <div className="monitoring-center">
      <div className="monitoring-header">
        <div>
          <h1>Active Monitoring</h1>
          <p className="monitoring-subtitle">
            Cases whose recorded status is <code>monitoring</code>. Scheduling, alerting and
            performance telemetry are not exposed by the current read API.
          </p>
        </div>
        <div className="monitoring-header-actions">
          <Button variant="secondary" onClick={() => refetch()} loading={isFetching && !isLoading}>
            Refresh
          </Button>
          <Button
            variant="primary"
            disabled
            title="Creating a monitor requires a mutation endpoint, which this read-only UI does not expose."
          >
            New Monitor
          </Button>
        </div>
      </div>

      <p className="monitoring-notice" role="note">
        Monitor creation, editing and manual runs are unavailable in this UI. Use the CLI
        (<code>uv run triangulate case rerun &lt;case-id&gt; --from retrieve</code>) to start work
        for a case.
      </p>

      <div className="monitoring-stats">
        <Card padding="sm">
          <CardBody>
            <div className="monitoring-stat-label">Monitoring Cases</div>
            <div className="monitoring-stat-value">
              {hasResolvedData ? monitors.length : unknownValue}
            </div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody>
            <div className="monitoring-stat-label">Cases With Recorded Update</div>
            <div className="monitoring-stat-value">
              {hasResolvedData ? lastUpdatedValues.length : unknownValue}
            </div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody>
            <div className="monitoring-stat-label">Most Recent Valid Recorded Update</div>
            <div className="monitoring-stat-value monitoring-stat-value--text">
              {hasResolvedData
                ? hasUnparseableTimestamp
                  ? 'Unknown (unparseable recorded timestamp)'
                  : newestUpdate
                    ? formatTimestamp(newestUpdate)
                    : 'Never recorded'
                : unknownValue}
            </div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody>
            <div className="monitoring-stat-label">Schedule / Next Run</div>
            <div className="monitoring-stat-value monitoring-stat-value--muted">{NOT_PROVIDED}</div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody>
            <div className="monitoring-stat-label">System Health</div>
            <div className="monitoring-stat-value monitoring-stat-value--muted">{NOT_PROVIDED}</div>
          </CardBody>
        </Card>
      </div>

      <div className="monitoring-tabs" role="tablist" aria-label="Monitoring sections">
        {(['monitors', 'alerts', 'performance'] as MonitoringTab[]).map((tab) => (
          <button
            key={tab}
            role="tab"
            id={`monitoring-tab-${tab}`}
            aria-selected={activeTab === tab}
            aria-controls={`monitoring-panel-${tab}`}
            className={`monitoring-tab ${activeTab === tab ? 'monitoring-tab--active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === 'monitors'
              ? hasResolvedData
                ? `Monitors (${monitors.length})`
                : 'Monitors'
              : tab === 'alerts'
                ? 'Alerts'
                : 'Performance'}
          </button>
        ))}
      </div>

      {isLoading ? (
        <Card>
          <CardBody>
            <div className="monitoring-state" role="status">Loading monitoring cases…</div>
          </CardBody>
        </Card>
      ) : error ? (
        <Card>
          <CardBody>
            <div className="monitoring-state monitoring-state--error" role="alert">
              <p>Failed to load monitoring cases{error instanceof Error && error.message ? `: ${error.message}` : '.'}</p>
              <Button variant="secondary" onClick={() => refetch()}>Retry</Button>
            </div>
          </CardBody>
        </Card>
      ) : (
        <div
          role="tabpanel"
          id={`monitoring-panel-${activeTab}`}
          aria-labelledby={`monitoring-tab-${activeTab}`}
        >
          {activeTab === 'monitors' && (
            <div className="monitoring-layout">
              <div className="monitoring-list">
                {monitors.length === 0 ? (
                  <Card>
                    <CardBody>
                      <div className="monitoring-state" role="status">
                        <div className="monitoring-state-title">No monitoring cases recorded</div>
                        <p>
                          No case currently has the recorded status <code>monitoring</code>. This is
                          an empty result, not a healthy system check.
                        </p>
                      </div>
                    </CardBody>
                  </Card>
                ) : (
                  <ul className="monitoring-list-items">
                    {monitors.map((monitor) => {
                      const isSelected = monitor.id === selectedMonitorId;
                      return (
                        <li key={monitor.id}>
                          <button
                            type="button"
                            className={`monitoring-row ${isSelected ? 'monitoring-row--selected' : ''}`}
                            aria-pressed={isSelected}
                            onClick={() => setSelectedMonitorId(monitor.id)}
                          >
                            <span className="monitoring-row-main">
                              <span className="monitoring-row-title">{monitor.query}</span>
                              <span className="monitoring-row-meta">
                                <Badge variant="success" size="sm">{monitor.status}</Badge>
                                <span>{monitor.conflictDomain}</span>
                                <span>{monitor.stage}</span>
                              </span>
                            </span>
                            <span className="monitoring-row-side">
                              <span className="monitoring-row-label">Last updated</span>
                              <span>{formatTimestamp(monitor.lastUpdated)}</span>
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              <div className="monitoring-detail">
                {selectedMonitor ? (
                  <Card>
                    <CardHeader>
                      <CardTitle>Recorded Monitor State</CardTitle>
                    </CardHeader>
                    <CardBody>
                      <dl className="monitoring-detail-list">
                        <div>
                          <dt>Query</dt>
                          <dd>{selectedMonitor.query}</dd>
                        </div>
                        <div>
                          <dt>Case ID</dt>
                          <dd><code>{selectedMonitor.id}</code></dd>
                        </div>
                        <div>
                          <dt>Recorded status</dt>
                          <dd>{selectedMonitor.status}</dd>
                        </div>
                        <div>
                          <dt>Stage</dt>
                          <dd>{selectedMonitor.stage}</dd>
                        </div>
                        <div>
                          <dt>Last updated</dt>
                          <dd>{formatTimestamp(selectedMonitor.lastUpdated)}</dd>
                        </div>
                        <div>
                          <dt>Schedule / next run</dt>
                          <dd className="monitoring-unavailable">{NOT_PROVIDED}</dd>
                        </div>
                      </dl>
                      <div className="monitoring-detail-actions">
                        <Button
                          variant="secondary"
                          disabled
                          title="No run-trigger endpoint exists; use the CLI."
                        >
                          Run Now
                        </Button>
                        <Button
                          variant="ghost"
                          disabled
                          title="Monitor configuration is not persisted by any current API."
                        >
                          Edit Configuration
                        </Button>
                      </div>
                      <p className="monitoring-cli-hint">
                        Start work with{' '}
                        <code>uv run triangulate case rerun {selectedMonitor.id} --from retrieve</code>.
                      </p>
                    </CardBody>
                  </Card>
                ) : (
                  <Card>
                    <CardBody>
                      <div className="monitoring-state" role="status">
                        Select a monitoring case to view its recorded state.
                      </div>
                    </CardBody>
                  </Card>
                )}
              </div>
            </div>
          )}

          {activeTab !== 'monitors' && (
            <Card>
              <CardHeader>
                <CardTitle>{activeTab === 'alerts' ? 'Alerts' : 'Performance'}</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="monitoring-state monitoring-state--unavailable" role="status">
                  <Badge variant="neutral" size="sm">Unavailable</Badge>
                  <p>{UNAVAILABLE_EXPLANATIONS[activeTab]}</p>
                </div>
              </CardBody>
            </Card>
          )}
        </div>
      )}
    </div>
  );
};

export default MonitoringCenter;
