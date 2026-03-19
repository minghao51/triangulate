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
  ShieldAlert,
  BarChart3,
  Zap,
} from 'lucide-react';
import { getCases } from '../services/api';
import Button from '../components/design-system/Button';
import Card from '../components/design-system/Card';
import { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';
import Badge from '../components/design-system/Badge';
import StatusIndicator from '../components/design-system/StatusIndicator';
import './Dashboard.css';

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

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const { data: cases = [], isLoading, error } = useQuery({
    queryKey: ['cases'],
    queryFn: getCases,
    refetchInterval: 30000, // Poll every 30 seconds
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

  const recentCases = cases.slice(0, 5);
  const casesRequiringAttention = cases
    .filter((c) => c.openExceptionsCount > 0 || c.status === 'review ready')
    .slice(0, 5);

  return (
    <div className="dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div className="dashboard-header-left">
          <h1 className="dashboard-title">Investigation Dashboard</h1>
          <p className="dashboard-subtitle">Real-time overview of all investigative activity</p>
        </div>
        <div className="dashboard-header-right">
          <Button
            variant="primary"
            icon={<Plus size={16} />}
            onClick={() => navigate('/cases/new')}
          >
            New Investigation
          </Button>
        </div>
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
            <Card className="metric-card">
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

            <Card className="metric-card">
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

            <Card className="metric-card">
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

            <Card className="metric-card">
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
            <Card className="dashboard-card dashboard-card-stages">
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
                    <div className="empty-state">No active cases</div>
                  )}
                </div>
              </CardBody>
            </Card>

            {/* Cases Requiring Attention */}
            <Card className="dashboard-card dashboard-card-attention">
              <CardHeader>
                <CardTitle>Requires Attention</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="attention-list">
                  {casesRequiringAttention.map((caseItem) => (
                    <div
                      key={caseItem.id}
                      className="attention-item"
                      onClick={() => navigate(`/cases/${caseItem.id}`)}
                    >
                      <div className="attention-content">
                        <div className="attention-query">{caseItem.query}</div>
                        <div className="attention-meta">
                          {caseItem.openExceptionsCount > 0 && (
                            <span className="attention-exception">
                              <AlertTriangle size={12} />
                              {caseItem.openExceptionsCount} exception
                              {caseItem.openExceptionsCount > 1 ? 's' : ''}
                            </span>
                          )}
                          {caseItem.status === 'review ready' && (
                            <span className="attention-review">
                              <CheckCircle size={12} />
                              Ready for review
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="attention-status">
                        <StatusIndicator status={caseItem.status} size="sm" showLabel={false} />
                      </div>
                    </div>
                  ))}
                  {casesRequiringAttention.length === 0 && (
                    <div className="empty-state">All cases clear</div>
                  )}
                </div>
              </CardBody>
            </Card>

            {/* Recent Cases */}
            <Card className="dashboard-card dashboard-card-recent">
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
                        <div className="recent-metric" title="Articles">
                          <FileText size={12} />
                          {caseItem.counts.articles}
                        </div>
                        <div className="recent-metric" title="Events">
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

            {/* System Health */}
            <Card className="dashboard-card dashboard-card-health">
              <CardHeader>
                <CardTitle>System Health</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="health-list">
                  <div className="health-item">
                    <div className="health-info">
                      <Zap size={16} className="health-icon" />
                      <span className="health-label">Pipeline Status</span>
                    </div>
                    <StatusIndicator status="running" size="sm" />
                  </div>
                  <div className="health-item">
                    <div className="health-info">
                      <ShieldAlert size={16} className="health-icon" />
                      <span className="health-label">Exception Queue</span>
                    </div>
                    <Badge variant={metrics.openExceptions > 0 ? 'warning' : 'success'} size="sm">
                      {metrics.openExceptions} items
                    </Badge>
                  </div>
                  <div className="health-item">
                    <div className="health-info">
                      <BarChart3 size={16} className="health-icon" />
                      <span className="health-label">Active Agents</span>
                    </div>
                    <Badge variant="info" size="sm">3 running</Badge>
                  </div>
                </div>
              </CardBody>
            </Card>
          </div>

          {/* Quick Actions */}
          <Card className="dashboard-card dashboard-card-actions">
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
                  Create New Case
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
