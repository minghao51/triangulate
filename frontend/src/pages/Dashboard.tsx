import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Plus,
  Activity,
  AlertTriangle,
  CheckCircle,
  Clock,
  FileText,
  BarChart3,
  Sparkles,
} from 'lucide-react';
import { getCases, getMonitoringSummary } from '../services/api';
import type { TopicCase } from '../types/backend-models';
import { useVisibleRefetchInterval } from '../components/design-system/reader-polling';
import Button from '../components/design-system/Button';
import Card from '../components/design-system/Card';
import { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';
import Badge from '../components/design-system/Badge';
import './Dashboard.css';

/**
 * Operator dashboard.
 *
 * Renders only two reads: the case list (`GET /api/cases`) and the recorded
 * monitoring summary (`GET /api/monitoring/summary`). The priority queue is
 * derived purely from counts already present on the list DTO
 * (`openExceptionsCount`, `hasNewMaterial`, `counts`), so no per-case detail
 * request is issued and no new endpoint is required.
 */

interface DashboardMetrics {
  totalCases: number;
  activeCases: number;
  reviewReady: number;
  openExceptions: number;
  stages: {
    name: string;
    count: number;
    color: string;
  }[];
}

interface PriorityQueueEntry {
  case: TopicCase;
  reasons: string[];
}

const RECORDED_ACTIVITY =
  'Recorded case records and saved counts. This view does not stream live execution.';

/**
 * Deterministic queue ordering from recorded counts only. Every comparison key
 * comes from the list DTO; the final case-id tie-break keeps the order stable
 * across identical payloads.
 */
const casePriorityComparator = (a: TopicCase, b: TopicCase): number => {
  if (a.openExceptionsCount !== b.openExceptionsCount) {
    return b.openExceptionsCount - a.openExceptionsCount;
  }
  if (a.hasNewMaterial !== b.hasNewMaterial) {
    return a.hasNewMaterial ? -1 : 1;
  }
  const aReviewReady = a.status === 'review ready' ? 1 : 0;
  const bReviewReady = b.status === 'review ready' ? 1 : 0;
  if (aReviewReady !== bReviewReady) {
    return bReviewReady - aReviewReady;
  }
  if (a.counts.reviewItems !== b.counts.reviewItems) {
    return b.counts.reviewItems - a.counts.reviewItems;
  }
  const aMaterial = a.counts.articles + a.counts.events;
  const bMaterial = b.counts.articles + b.counts.events;
  if (aMaterial !== bMaterial) {
    return bMaterial - aMaterial;
  }
  return a.id.localeCompare(b.id);
};

/** The recorded facts that put a case in the queue, as plain text. */
const describeCasePriority = (item: TopicCase): string[] => {
  const reasons: string[] = [];
  if (item.openExceptionsCount > 0) {
    reasons.push(
      `${item.openExceptionsCount} open exception${item.openExceptionsCount === 1 ? '' : 's'}`
    );
  }
  if (item.hasNewMaterial) {
    reasons.push('new material recorded');
  }
  if (item.status === 'review ready') {
    reasons.push('recorded status review ready');
  }
  if (item.counts.reviewItems > 0) {
    reasons.push(
      `${item.counts.reviewItems} recorded review item${item.counts.reviewItems === 1 ? '' : 's'}`
    );
  }
  reasons.push(`${item.counts.articles} recorded articles, ${item.counts.events} events`);
  return reasons;
};

const buildPriorityQueue = (cases: TopicCase[]): PriorityQueueEntry[] =>
  [...cases]
    .sort(casePriorityComparator)
    .map((caseItem) => ({ case: caseItem, reasons: describeCasePriority(caseItem) }));

const formatClock = (epochMs: number | null): string =>
  epochMs === null || !Number.isFinite(epochMs) || epochMs <= 0
    ? '—'
    : new Date(epochMs).toLocaleTimeString();

const formatObserved = (iso: string | null): string => {
  if (!iso) return 'Never recorded';
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? 'Unknown (unparseable recorded timestamp)' : parsed.toLocaleString();
};

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  // One polling budget shared by both reads; a hidden tab stops both timers.
  const refetchInterval = useVisibleRefetchInterval(30000);

  const {
    data: cases = [],
    isLoading,
    error,
    dataUpdatedAt,
  } = useQuery({
    queryKey: ['cases'],
    queryFn: getCases,
    refetchInterval,
  });
  const { data: monitoringSummary } = useQuery({
    queryKey: ['monitoringSummary'],
    queryFn: getMonitoringSummary,
    refetchInterval,
  });

  const metrics = useMemo<DashboardMetrics>(() => {
    const activeCases = cases.filter(
      (c) => c.status !== 'approved' && c.status !== 'rejected'
    );
    const reviewReady = cases.filter((c) => c.status === 'review ready');
    const openExceptions = cases.reduce((sum, c) => sum + c.openExceptionsCount, 0);

    const stageCounts = cases.reduce((acc, c) => {
      acc[c.stage] = (acc[c.stage] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    const stageColors: Record<string, string> = {
      BOOTSTRAP: '#6c5ce7',
      RETRIEVE: '#00d4ff',
      TRIAGE: '#00ff9d',
      INVESTIGATE: '#ffb800',
      ARBITRATE: '#ff6b00',
      REPORT: '#a55eea',
      REVIEW: '#ff4757',
    };

    const stages = Object.entries(stageCounts).map(([name, count]) => ({
      name,
      count,
      color: stageColors[name] || '#6c7385',
    }));

    return {
      totalCases: cases.length,
      activeCases: activeCases.length,
      reviewReady: reviewReady.length,
      openExceptions,
      stages,
    };
  }, [cases]);

  const priorityQueue = useMemo(() => buildPriorityQueue(cases).slice(0, 6), [cases]);

  // "Last observed" is the newest timestamp the server recorded on a case row,
  // which is a different fact from when this client last fetched.
  const lastObserved = useMemo(() => {
    const recorded = cases
      .map((caseItem) => caseItem.lastUpdated)
      .filter((value): value is string => Boolean(value));
    if (recorded.length === 0) return 'Never recorded';
    const parsed = recorded.map((value) => Date.parse(value));
    if (parsed.some((value) => !Number.isFinite(value))) {
      return 'Unknown (unparseable recorded timestamp)';
    }
    return formatObserved(new Date(Math.max(...parsed)).toISOString());
  }, [cases]);

  const recentCases = cases.slice(0, 5);

  return (
    <div className="dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div className="dashboard-header-left">
          <h1 className="dashboard-title">Investigation Dashboard</h1>
          <p className="dashboard-subtitle">{RECORDED_ACTIVITY}</p>
        </div>
        <div className="dashboard-header-right">
          <Button
            variant="primary"
            icon={<Plus size={16} />}
            onClick={() => navigate('/cases/new')}
          >
            CLI Launch Guide
          </Button>
        </div>
      </div>

      <div className="dashboard-freshness">
        <span className="dashboard-freshness-item" data-testid="dashboard-last-fetched">
          <span className="dashboard-freshness-label">Last fetched</span>
          <span className="dashboard-freshness-value">{formatClock(dataUpdatedAt)}</span>
          <span className="dashboard-freshness-note">client request time</span>
        </span>
        <span className="dashboard-freshness-item" data-testid="dashboard-last-observed">
          <span className="dashboard-freshness-label">Last observed</span>
          <span className="dashboard-freshness-value">{lastObserved}</span>
          <span className="dashboard-freshness-note">recorded server observation</span>
        </span>
        <span className="dashboard-freshness-item dashboard-freshness-item--muted">
          <span className="dashboard-freshness-label">Process health</span>
          <span className="dashboard-freshness-note">
            <code>/health</code> is liveness only and is not shown as a readiness signal.
          </span>
        </span>
      </div>

      {error && (
        <div className="dashboard-error">
          <AlertTriangle size={16} />
          <span>Failed to load cases: {(error as Error).message}</span>
        </div>
      )}

      {isLoading ? (
        <div className="dashboard-loading">Loading dashboard...</div>
      ) : (
        <div className="dashboard-content">
          {/* Metrics Grid */}
          <div className="dashboard-metrics">
            <Card className="metric-card glass-panel">
              <CardBody className="metric-card-body">
                <div className="metric-icon metric-icon-primary">
                  <FileText size={20} />
                </div>
                <div className="metric-content">
                  <div className="metric-value">{metrics.totalCases}</div>
                  <div className="metric-label">Total Cases</div>
                </div>
              </CardBody>
            </Card>

            <Card className="metric-card glass-panel">
              <CardBody className="metric-card-body">
                <div className="metric-icon metric-icon-success">
                  <Activity size={20} />
                </div>
                <div className="metric-content">
                  <div className="metric-value">{metrics.activeCases}</div>
                  <div className="metric-label">Active Investigations</div>
                </div>
              </CardBody>
            </Card>

            <Card className="metric-card glass-panel">
              <CardBody className="metric-card-body">
                <div className="metric-icon metric-icon-warning">
                  <CheckCircle size={20} />
                </div>
                <div className="metric-content">
                  <div className="metric-value">{metrics.reviewReady}</div>
                  <div className="metric-label">Ready for Review</div>
                </div>
              </CardBody>
            </Card>

            <Card className="metric-card glass-panel">
              <CardBody className="metric-card-body">
                <div className="metric-icon metric-icon-danger">
                  <AlertTriangle size={20} />
                </div>
                <div className="metric-content">
                  <div className="metric-value">{metrics.openExceptions}</div>
                  <div className="metric-label">Open Exceptions</div>
                </div>
              </CardBody>
            </Card>
          </div>

          {/* Main Grid */}
          <div className="dashboard-grid">
            {/* Pipeline Stage Distribution */}
            <Card className="dashboard-card dashboard-card-stages glass-panel">
              <CardHeader>
                <CardTitle>Pipeline Stage Distribution</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="stages-list">
                  {metrics.stages.map((stage) => (
                    <div key={stage.name} className="stage-item">
                      <div className="stage-info">
                        <div
                          className="stage-dot"
                          style={{ backgroundColor: stage.color }}
                        />
                        <span className="stage-name">{stage.name}</span>
                      </div>
                      <div className="stage-value">{stage.count}</div>
                    </div>
                  ))}
                  {metrics.stages.length === 0 && (
                    <div className="empty-state">No recorded cases</div>
                  )}
                </div>
              </CardBody>
            </Card>

            {/* Priority Queue — ordered from recorded counts in the list DTO */}
            <Card className="dashboard-card dashboard-card-attention glass-panel">
              <CardHeader>
                <CardTitle>Priority Queue</CardTitle>
              </CardHeader>
              <CardBody>
                <p className="dashboard-card-note">
                  Ordered by recorded open exceptions, new material, review items and case counts.
                </p>
                <div className="attention-list">
                  {priorityQueue.map((entry, index) => (
                    <div
                      key={entry.case.id}
                      className="attention-item"
                      data-testid="dashboard-queue-item"
                      onClick={() => navigate(`/cases/${entry.case.id}`)}
                    >
                      <span className="attention-rank">{index + 1}</span>
                      <div className="attention-content">
                        <div className="attention-query">{entry.case.query}</div>
                        <div className="attention-meta attention-meta--text">
                          <span className="attention-reasons">{entry.reasons.join(' · ')}</span>
                        </div>
                      </div>
                      <div className="attention-status attention-status--text">
                        <span className="attention-stage">{entry.case.stage}</span>
                        <span className="attention-state">{entry.case.status}</span>
                      </div>
                    </div>
                  ))}
                  {priorityQueue.length === 0 && (
                    <div className="empty-state">No recorded cases to queue</div>
                  )}
                </div>
              </CardBody>
            </Card>

            {/* Recent Cases */}
            <Card className="dashboard-card dashboard-card-recent glass-panel">
              <CardHeader>
                <CardTitle>Recent Cases</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="recent-list">
                  {recentCases.map((caseItem) => (
                    <div
                      key={caseItem.id}
                      className="recent-item"
                      onClick={() => navigate(`/cases/${caseItem.id}`)}
                    >
                      <div className="recent-content">
                        <div className="recent-query">{caseItem.query}</div>
                        <div className="recent-domain">{caseItem.conflictDomain}</div>
                      </div>
                      <div className="recent-metrics">
                        <div className="recent-metric" title="Recorded articles">
                          <FileText size={12} />
                          {caseItem.counts.articles}
                        </div>
                        <div className="recent-metric" title="Recorded events">
                          <Clock size={12} />
                          {caseItem.counts.events}
                        </div>
                      </div>
                      <div className="recent-status">
                        <Badge variant="neutral" size="sm">{caseItem.stage}</Badge>
                      </div>
                    </div>
                  ))}
                  {recentCases.length === 0 && (
                    <div className="empty-state">No cases yet</div>
                  )}
                </div>
              </CardBody>
            </Card>

            {/* Recorded Summary — only values the read API returns */}
            <Card className="dashboard-card dashboard-card-health glass-panel">
              <CardHeader>
                <CardTitle>Recorded Summary</CardTitle>
              </CardHeader>
              <CardBody>
                <p className="dashboard-card-note">
                  Values come from <code>GET /api/monitoring/summary</code>. Missing values are
                  shown as <code>Not recorded</code> rather than as a zero.
                </p>
                <div className="health-list">
                  <div className="health-item">
                    <div className="health-info">
                      <Activity size={16} className="health-icon" />
                      <span className="health-label">Exception Queue</span>
                    </div>
                    <Badge variant={metrics.openExceptions > 0 ? 'warning' : 'success'} size="sm">
                      {monitoringSummary?.review?.open_exceptions ?? metrics.openExceptions} items
                    </Badge>
                  </div>
                  <div className="health-item">
                    <div className="health-info">
                      <BarChart3 size={16} className="health-icon" />
                      <span className="health-label">Avg Evaluation</span>
                    </div>
                    <Badge variant="info" size="sm">
                      {monitoringSummary?.evaluation?.avg_overall_score ?? 'Not recorded'}
                    </Badge>
                  </div>
                  <div className="health-item">
                    <div className="health-info">
                      <Clock size={16} className="health-icon" />
                      <span className="health-label">Avg Stage Duration</span>
                    </div>
                    <Badge variant="neutral" size="sm">
                      {monitoringSummary?.pipeline?.avg_duration_ms === undefined
                        ? 'Not recorded'
                        : `${monitoringSummary.pipeline.avg_duration_ms} ms`}
                    </Badge>
                  </div>
                  <div className="health-item">
                    <div className="health-info">
                      <Sparkles size={16} className="health-icon" />
                      <span className="health-label">Scheduling / alerts</span>
                    </div>
                    <Badge variant="neutral" size="sm">Not provided by the API</Badge>
                  </div>
                </div>
              </CardBody>
            </Card>
          </div>

          {/* Quick Actions */}
          <Card className="dashboard-card dashboard-card-actions glass-panel">
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
            </CardHeader>
            <CardBody>
              <div className="quick-actions">
                <Button
                  variant="secondary"
                  icon={<Plus size={16} />}
                  onClick={() => navigate('/cases/new')}
                >
                  Open CLI Guide
                </Button>
                <Button
                  variant="secondary"
                  icon={<FileText size={16} />}
                  onClick={() => navigate('/cases')}
                >
                  Browse All Cases
                </Button>
                <Button
                  variant="secondary"
                  icon={<AlertTriangle size={16} />}
                  onClick={() => navigate('/monitoring')}
                >
                  View Exceptions
                </Button>
              </div>
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
