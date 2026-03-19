import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, Routes, Route, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  Play,
  ShieldAlert,
  FileText,
  GitMerge,
  Users,
  Clock,
  AlertTriangle,
  CheckCircle2,
  X,
  RefreshCw,
} from 'lucide-react';
import type { TopicCase } from '../types/backend-models';
import { getCaseDetail, rerunCase, reviewCase } from '../services/api';
import { useCaseStore } from '../stores/case-store';
import Button from '../components/design-system/Button';
import Card from '../components/design-system/Card';
import { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';
import Badge from '../components/design-system/Badge';
import StatusIndicator from '../components/design-system/StatusIndicator';
import './CaseIntelligenceCenter.css';

// Tab components
import EvidenceTab from './tabs/EvidenceTab';
import ClaimsTab from './tabs/ClaimsTab';
import ExceptionsTab from './tabs/ExceptionsTab';
import PartiesTab from './tabs/PartiesTab';
import TimelineTab from './tabs/TimelineTab';
import ReportTab from './tabs/ReportTab';
import RunHistoryTab from './tabs/RunHistoryTab';

interface TabConfig {
  id: string;
  label: string;
  icon: React.ReactNode;
  path: string;
  badge?: number;
}

const CaseIntelligenceCenter: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const currentPath = location.pathname.split('/').pop() || '';
  const [actionPending, setActionPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { setActiveCase, setCaseDetail } = useCaseStore();

  // Fetch case data
  const { data: detailData, isLoading, refetch } = useQuery({
    queryKey: ['caseDetail', id],
    queryFn: () => getCaseDetail(id!),
    enabled: !!id,
    refetchInterval: 15000, // Poll every 15 seconds
  });

  const activeCase = detailData?.case || null;

  // Update store when data changes
  useEffect(() => {
    if (activeCase) {
      setActiveCase(activeCase);
      setCaseDetail(detailData!);
    }
  }, [activeCase, detailData, setActiveCase, setCaseDetail]);

  const handleRerun = async () => {
    if (!id) return;
    setActionPending(true);
    setError(null);
    try {
      const detail = await rerunCase(id);
      setActiveCase(detail.case);
      setCaseDetail(detail);
      refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rerun case');
    } finally {
      setActionPending(false);
    }
  };

  const handleReviewAction = async (
    decision: 'approve' | 'reject' | 'action_required'
  ) => {
    if (!id) return;
    setActionPending(true);
    setError(null);
    try {
      const detail = await reviewCase(id, decision);
      setActiveCase(detail.case);
      setCaseDetail(detail);
      refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to review case');
    } finally {
      setActionPending(false);
    }
  };

  const tabs: TabConfig[] = [
    { id: 'overview', label: 'Overview', icon: <FileText size={16} />, path: '' },
    { id: 'evidence', label: 'Evidence', icon: <FileText size={16} />, path: 'evidence' },
    { id: 'claims', label: 'Claims', icon: <GitMerge size={16} />, path: 'claims' },
    { id: 'parties', label: 'Parties', icon: <Users size={16} />, path: 'parties' },
    { id: 'timeline', label: 'Timeline', icon: <Clock size={16} />, path: 'timeline' },
    {
      id: 'exceptions',
      label: 'Exceptions',
      icon: <AlertTriangle size={16} />,
      path: 'exceptions',
      badge: activeCase?.openExceptionsCount || 0,
    },
    { id: 'report', label: 'Report', icon: <FileText size={16} />, path: 'report' },
    { id: 'run-history', label: 'Run History', icon: <Play size={16} />, path: 'run-history' },
  ];

  if (isLoading) {
    return (
      <div className="case-intelligence-center">
        <div className="case-loading">
          <div className="loading-spinner" />
          <p>Loading case intelligence...</p>
        </div>
      </div>
    );
  }

  if (error && !activeCase) {
    return (
      <div className="case-intelligence-center">
        <div className="case-error">
          <AlertTriangle size={24} />
          <div>
            <h3>Failed to load case</h3>
            <p>{error}</p>
            <Button variant="secondary" onClick={() => navigate('/cases')}>
              <ArrowLeft size={16} />
              Back to Cases
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (!activeCase) {
    return null;
  }

  const activeTab = tabs.find((t) => t.path === currentPath) || tabs[0];

  return (
    <div className="case-intelligence-center">
      {/* Persistent Header */}
      <div className="case-header">
        <div className="case-header-top">
          <div className="case-header-left">
            <Button
              variant="ghost"
              size="sm"
              icon={<ArrowLeft size={16} />}
              onClick={() => navigate('/cases')}
            >
              Back
            </Button>
            <div className="case-title-section">
              <h1 className="case-title">{activeCase.query}</h1>
              <div className="case-meta">
                <Badge variant="neutral" size="sm">{activeCase.conflictDomain}</Badge>
                <span className="case-id">ID: {activeCase.id.slice(0, 8)}</span>
              </div>
            </div>
          </div>

          <div className="case-header-right">
            <div className="case-actions">
              <Button
                variant="secondary"
                size="sm"
                icon={<RefreshCw size={14} />}
                onClick={() => refetch()}
                disabled={actionPending}
              >
                Refresh
              </Button>
              {activeCase.stage !== 'REVIEW' && activeCase.status !== 'approved' && (
                <Button
                  variant="primary"
                  size="sm"
                  icon={<Play size={14} />}
                  onClick={handleRerun}
                  disabled={actionPending}
                  loading={actionPending}
                >
                  Run Next Stage
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Metrics Bar */}
        <div className="case-metrics-bar">
          <div className="case-metric">
            <FileText size={14} />
            <span className="metric-label">Sources</span>
            <span className="metric-value">{activeCase.counts.articles}</span>
          </div>

          <div className="case-metric">
            <GitMerge size={14} />
            <span className="metric-label">Events</span>
            <span className="metric-value">{activeCase.counts.events}</span>
          </div>

          <div className="case-metric">
            <AlertTriangle size={14} />
            <span className="metric-label">Review Items</span>
            <span className="metric-value">{activeCase.counts.reviewItems}</span>
          </div>

          <div className="case-metric">
            <ShieldAlert size={14} />
            <span className="metric-label">Exceptions</span>
            <span className={`metric-value ${activeCase.openExceptionsCount > 0 ? 'has-exceptions' : ''}`}>
              {activeCase.openExceptionsCount}
            </span>
          </div>

          <div className="case-status-group">
            <StatusIndicator status={activeCase.status} size="sm" />
            <Badge variant="neutral" size="sm">{activeCase.stage}</Badge>
            <Badge variant="info" size="sm">{activeCase.automationMode}</Badge>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="case-error-banner">
          <AlertTriangle size={16} />
          <span>{error}</span>
          <button
            className="error-close"
            onClick={() => setError(null)}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Tabs Navigation */}
      <div className="case-tabs-nav">
        <div className="tabs-list">
          {tabs.map((tab) => {
            const isActive = activeTab.id === tab.id;
            return (
              <button
                key={tab.id}
                className={`case-tab ${isActive ? 'case-tab-active' : ''}`}
                onClick={() => navigate(`/cases/${id}/${tab.path}`)}
              >
                <span className="tab-icon">{tab.icon}</span>
                <span className="tab-label">{tab.label}</span>
                {tab.badge !== undefined && tab.badge > 0 && (
                  <span className="tab-badge">{tab.badge}</span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab Content */}
      <div className="case-tab-content">
        <Routes>
          <Route
            index
            element={
              <OverviewTab
                activeCase={activeCase}
                actionPending={actionPending}
                onReviewAction={handleReviewAction}
              />
            }
          />
          <Route
            path="evidence"
            element={<EvidenceTab caseId={id!} />}
          />
          <Route
            path="claims"
            element={<ClaimsTab caseId={id!} />}
          />
          <Route
            path="exceptions"
            element={
              <ExceptionsTab
                caseId={id!}
                onCaseMutated={() => refetch()}
              />
            }
          />
          <Route
            path="parties"
            element={<PartiesTab caseId={id!} />}
          />
          <Route
            path="timeline"
            element={<TimelineTab caseId={id!} />}
          />
          <Route
            path="report"
            element={<ReportTab caseId={id!} />}
          />
          <Route
            path="run-history"
            element={<RunHistoryTab caseId={id!} />}
          />
          <Route path="*" element={<div>Tab not found</div>} />
        </Routes>
      </div>
    </div>
  );
};

// Overview Tab Component
const OverviewTab: React.FC<{
  activeCase: TopicCase;
  actionPending: boolean;
  onReviewAction: (decision: 'approve' | 'reject' | 'action_required') => Promise<void>;
}> = ({ activeCase, actionPending, onReviewAction }) => {
  return (
    <div className="overview-tab">
      <div className="overview-grid">
        {/* Case Information */}
        <Card className="overview-card">
          <CardHeader>
            <CardTitle>Case Information</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="info-list">
              <div className="info-item">
                <span className="info-label">Query</span>
                <span className="info-value">{activeCase.query}</span>
              </div>
              <div className="info-item">
                <span className="info-label">Conflict Domain</span>
                <span className="info-value">{activeCase.conflictDomain}</span>
              </div>
              <div className="info-item">
                <span className="info-label">Status</span>
                <StatusIndicator status={activeCase.status} size="sm" />
              </div>
              <div className="info-item">
                <span className="info-label">Current Stage</span>
                <Badge variant="neutral" size="sm">{activeCase.stage}</Badge>
              </div>
              <div className="info-item">
                <span className="info-label">Automation Mode</span>
                <Badge variant="info" size="sm">{activeCase.automationMode}</Badge>
              </div>
              <div className="info-item">
                <span className="info-label">Has New Material</span>
                <Badge variant={activeCase.hasNewMaterial ? 'success' : 'neutral'} size="sm">
                  {activeCase.hasNewMaterial ? 'Yes' : 'No'}
                </Badge>
              </div>
            </div>
          </CardBody>
        </Card>

        {/* Review Actions */}
        {activeCase.status === 'review ready' && (
          <Card className="overview-card">
            <CardHeader>
              <CardTitle>Review Actions</CardTitle>
            </CardHeader>
            <CardBody>
              <div className="review-actions">
                <p className="review-description">
                  This case is ready for review. Approve to mark as complete, or request
                  additional action if needed.
                </p>
                <div className="action-buttons">
                  <Button
                    variant="primary"
                    icon={<CheckCircle2 size={16} />}
                    onClick={() => onReviewAction('approve')}
                    disabled={actionPending || activeCase.openExceptionsCount > 0}
                    loading={actionPending}
                  >
                    Approve Case
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => onReviewAction('action_required')}
                    disabled={actionPending}
                  >
                    Mark Action Required
                  </Button>
                  <Button
                    variant="danger"
                    onClick={() => onReviewAction('reject')}
                    disabled={actionPending}
                  >
                    Reject Case
                  </Button>
                </div>
                {activeCase.openExceptionsCount > 0 && (
                  <div className="review-warning">
                    <AlertTriangle size={14} />
                    <span>
                      Resolve {activeCase.openExceptionsCount} open exception
                      {activeCase.openExceptionsCount > 1 ? 's' : ''} before approving
                    </span>
                  </div>
                )}
              </div>
            </CardBody>
          </Card>
        )}
      </div>
    </div>
  );
};

export default CaseIntelligenceCenter;
