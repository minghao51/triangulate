import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, Routes, Route, useLocation } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Play,
  ShieldAlert,
  FileText,
  GitMerge,
  Users,
  Clock,
  AlertTriangle,
  RefreshCw,
  TerminalSquare,
  MessageSquare,
  Flag,
  CheckCheck,
} from 'lucide-react';
import type { TopicCase } from '../types/backend-models';
import {
  createCaseAnnotation,
  getCaseDetail,
  getEvaluationForCase,
  getReviewActivityForCase,
  submitCaseReviewAction,
} from '../services/api';
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
import MapTab from './tabs/MapTab';
import ReportTab from './tabs/ReportTab';
import RunHistoryTab from './tabs/RunHistoryTab';
import { Map } from 'lucide-react';

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

  const { setActiveCase, setCaseDetail, clearActiveCase } = useCaseStore();

  // Fetch case data
  const { data: detailData, isLoading, error: queryError, refetch } = useQuery({
    queryKey: ['caseDetail', id],
    queryFn: () => getCaseDetail(id!),
    enabled: !!id,
    refetchInterval: 15000, // Poll every 15 seconds
  });

  // Only trust detail that belongs to the case currently in the route.
  const activeCase =
    detailData?.case && detailData.case.id === id ? detailData.case : null;

  // Clear the shared store when the route's case changes so a previous case can
  // never stay active behind a new case.
  useEffect(() => {
    clearActiveCase();
  }, [id, clearActiveCase]);

  // Apply store state only for the matching case; a late response for case A can
  // never overwrite case B because the id is compared before writing.
  useEffect(() => {
    if (detailData?.case && detailData.case.id === id) {
      setActiveCase(detailData.case);
      setCaseDetail(detailData);
    }
  }, [detailData, id, setActiveCase, setCaseDetail]);

  // Release the shared store when leaving the case workspace entirely.
  useEffect(() => () => clearActiveCase(), [clearActiveCase]);

  const tabs: TabConfig[] = [
    { id: 'overview', label: 'Overview', icon: <FileText size={16} />, path: '' },
    { id: 'evidence', label: 'Evidence', icon: <FileText size={16} />, path: 'evidence' },
    { id: 'claims', label: 'Claims', icon: <GitMerge size={16} />, path: 'claims' },
    { id: 'parties', label: 'Parties', icon: <Users size={16} />, path: 'parties' },
    { id: 'map', label: 'Map', icon: <Map size={16} />, path: 'map' },
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

  if (!id) {
    return (
      <div className="case-intelligence-center">
        <div className="case-error" role="alert">
          <AlertTriangle size={24} />
          <div>
            <h3>No case selected</h3>
            <p>The route does not include a case ID.</p>
            <Button variant="secondary" icon={<ArrowLeft size={16} />} onClick={() => navigate('/cases')}>
              Back to Cases
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (queryError) {
    return (
      <div className="case-intelligence-center">
        <div className="case-error" role="alert">
          <AlertTriangle size={24} />
          <div>
            <h3>Failed to load case</h3>
            <p>
              {queryError instanceof Error && queryError.message
                ? queryError.message
                : 'The case could not be loaded.'}
            </p>
            <div className="case-error-actions">
              <Button variant="secondary" onClick={() => refetch()}>Retry</Button>
              <Button variant="ghost" icon={<ArrowLeft size={16} />} onClick={() => navigate('/cases')}>
                Back to Cases
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!activeCase) {
    return (
      <div className="case-intelligence-center">
        <div className="case-error" role="alert">
          <AlertTriangle size={24} />
          <div>
            <h3>Case not found</h3>
            <p>No case with ID <code>{id}</code> was returned by the API.</p>
            <Button variant="secondary" icon={<ArrowLeft size={16} />} onClick={() => navigate('/cases')}>
              Back to Cases
            </Button>
          </div>
        </div>
      </div>
    );
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
              >
                Refresh
              </Button>
            </div>
          </div>
        </div>

        {/* Metrics Bar */}
        <div className="case-metrics-bar">
          <div className="case-metric">
            <FileText size={14} />
            <span className="metric-label">Articles</span>
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
      {/* Keyed so per-case tab state (filters, expansions, selections) is reset on
          case changes instead of leaking across cases. */}
      <div className="case-tab-content" key={id}>
        <Routes>
          <Route
            index
            element={
              <OverviewTab
                activeCase={activeCase}
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
              />
            }
          />
          <Route
            path="parties"
            element={<PartiesTab caseId={id!} />}
          />
          <Route
            path="map"
            element={<MapTab caseId={id!} />}
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
}> = ({ activeCase }) => {
  const queryClient = useQueryClient();
  const [reviewNotes, setReviewNotes] = useState('');
  const [annotationType, setAnnotationType] = useState('comment');
  const [annotationTargetType, setAnnotationTargetType] = useState('case');
  const [annotationTargetId, setAnnotationTargetId] = useState('');
  const [annotationContent, setAnnotationContent] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);
  const operatorCommands = buildOperatorCommands(activeCase);
  const { data: reviewActivity } = useQuery({
    queryKey: ['reviewActivity', activeCase.id],
    queryFn: () => getReviewActivityForCase(activeCase.id),
  });
  const { data: evaluation } = useQuery({
    queryKey: ['evaluationSummary', activeCase.id],
    queryFn: () => getEvaluationForCase(activeCase.id),
  });
  const effectiveAnnotationTargetId =
    annotationTargetType === 'case' ? activeCase.id : annotationTargetId.trim();

  const refreshCaseQueries = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['caseDetail', activeCase.id] }),
      queryClient.invalidateQueries({ queryKey: ['cases'] }),
      queryClient.invalidateQueries({ queryKey: ['reviewActivity', activeCase.id] }),
      queryClient.invalidateQueries({ queryKey: ['evaluationSummary', activeCase.id] }),
      queryClient.invalidateQueries({ queryKey: ['monitoringSummary'] }),
    ]);
  };

  const reviewMutation = useMutation({
    mutationFn: ({ decision, notes }: { decision: string; notes?: string }) =>
      submitCaseReviewAction(activeCase.id, decision, notes),
    onSuccess: async () => {
      setReviewNotes('');
      setLocalError(null);
      await refreshCaseQueries();
    },
    onError: (err: Error) => setLocalError(err.message),
  });

  const annotationMutation = useMutation({
    mutationFn: () =>
      createCaseAnnotation(activeCase.id, {
        targetType: annotationTargetType,
        targetId: effectiveAnnotationTargetId || activeCase.id,
        annotationType,
        content: annotationContent,
      }),
    onSuccess: async () => {
      setAnnotationContent('');
      setLocalError(null);
      await refreshCaseQueries();
    },
    onError: (err: Error) => setLocalError(err.message),
  });

  const latestEvaluation = evaluation?.latest;
  const evaluationScore =
    typeof latestEvaluation?.summary?.overall_score === 'number'
      ? latestEvaluation.summary.overall_score
      : null;
  const activityItems = [
    ...(reviewActivity?.auditEntries ?? []).map((item) => ({
      id: `audit-${item.id}`,
      title: item.actionType.replace(/[:_]/g, ' '),
      subtitle: item.rationale || `${item.actor} updated ${item.targetType}`,
      timestamp: item.createdAt,
      icon: <CheckCheck size={14} />,
    })),
    ...(reviewActivity?.annotations ?? []).map((item) => ({
      id: `annotation-${item.id}`,
      title: `${item.annotationType} on ${item.targetType}`,
      subtitle: item.content,
      timestamp: item.createdAt,
      icon: item.annotationType === 'flag' ? <Flag size={14} /> : <MessageSquare size={14} />,
    })),
  ]
    .sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''))
    .slice(0, 8);

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

        <Card className="overview-card">
          <CardHeader>
            <CardTitle>Operator Commands</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="review-actions">
              <p className="review-description">Use narrow in-app review controls for approvals and notes, with CLI commands still available for reruns and deeper operations.</p>
              <textarea
                value={reviewNotes}
                onChange={(event) => setReviewNotes(event.target.value)}
                placeholder="Decision rationale or handoff notes"
                style={{
                  width: '100%',
                  minHeight: '84px',
                  borderRadius: '12px',
                  background: 'rgba(10, 19, 31, 0.68)',
                  color: 'inherit',
                  border: '1px solid rgba(133, 157, 186, 0.24)',
                  padding: '0.85rem',
                  marginBottom: '0.85rem',
                }}
              />
              <div className="action-buttons">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => reviewMutation.mutate({ decision: 'approve', notes: reviewNotes })}
                  disabled={reviewMutation.isPending}
                >
                  Approve
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => reviewMutation.mutate({ decision: 'action_required', notes: reviewNotes })}
                  disabled={reviewMutation.isPending}
                >
                  Action Required
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => reviewMutation.mutate({ decision: 'reject', notes: reviewNotes })}
                  disabled={reviewMutation.isPending}
                >
                  Reject
                </Button>
              </div>
              {localError && <div className="review-warning"><AlertTriangle size={14} /><span>{localError}</span></div>}
              {activeCase.openExceptionsCount > 0 && (
                <div className="review-warning">
                  <AlertTriangle size={14} />
                  <span>
                    {activeCase.openExceptionsCount} open exception
                    {activeCase.openExceptionsCount > 1 ? 's remain' : ' remains'} in the operator queue.
                  </span>
                </div>
              )}
              <div className="review-label" style={{ marginTop: '1rem', marginBottom: '0.375rem' }}>
                <TerminalSquare size={14} /> CLI fallback
              </div>
              <div className="action-buttons" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                {operatorCommands.map((command) => (
                  <div key={command.label}>
                    <div className="review-label" style={{ marginBottom: '0.375rem' }}>
                      <TerminalSquare size={14} /> {command.label}
                    </div>
                    <code className="review-value" style={{ display: 'block' }}>{command.command}</code>
                  </div>
                ))}
              </div>
            </div>
          </CardBody>
        </Card>

        <Card className="overview-card">
          <CardHeader>
            <CardTitle>Evaluation Snapshot</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="info-list">
              <div className="info-item">
                <span className="info-label">Overall score</span>
                <span className="info-value">{evaluationScore ?? 'Pending'}</span>
              </div>
              <div className="info-item">
                <span className="info-label">Evidence linkage</span>
                <span className="info-value">{String(latestEvaluation?.metrics?.evidence_linkage ?? 'n/a')}</span>
              </div>
              <div className="info-item">
                <span className="info-label">Review burden</span>
                <span className="info-value">{String(latestEvaluation?.metrics?.review_burden ?? 'n/a')}</span>
              </div>
              <div className="info-item">
                <span className="info-label">Pipeline resilience</span>
                <span className="info-value">{String(latestEvaluation?.metrics?.pipeline_resilience ?? 'n/a')}</span>
              </div>
              <div className="info-item">
                <span className="info-label">Last evaluated</span>
                <span className="info-value">{latestEvaluation?.createdAt ?? 'Running on first view'}</span>
              </div>
            </div>
          </CardBody>
        </Card>

        <Card className="overview-card">
          <CardHeader>
            <CardTitle>Annotations</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="review-actions">
              <div className="action-buttons" style={{ marginBottom: '0.75rem' }}>
                <select value={annotationType} onChange={(e) => setAnnotationType(e.target.value)}>
                  <option value="comment">Comment</option>
                  <option value="flag">Flag</option>
                  <option value="context">Context</option>
                </select>
                <select
                  value={annotationTargetType}
                  onChange={(e) => setAnnotationTargetType(e.target.value)}
                >
                  <option value="case">Case</option>
                  <option value="claim">Claim</option>
                  <option value="evidence">Evidence</option>
                  <option value="exception">Exception</option>
                  <option value="narrative">Narrative</option>
                </select>
              </div>
              <input
                value={annotationTargetType === 'case' ? activeCase.id : annotationTargetId}
                onChange={(event) => setAnnotationTargetId(event.target.value)}
                placeholder="Target ID"
                disabled={annotationTargetType === 'case'}
                style={{
                  width: '100%',
                  borderRadius: '12px',
                  background: 'rgba(10, 19, 31, 0.68)',
                  color: 'inherit',
                  border: '1px solid rgba(133, 157, 186, 0.24)',
                  padding: '0.75rem',
                  marginBottom: '0.75rem',
                }}
              />
              <textarea
                value={annotationContent}
                onChange={(event) => setAnnotationContent(event.target.value)}
                placeholder="Add comment, flag rationale, or injected context"
                style={{
                  width: '100%',
                  minHeight: '90px',
                  borderRadius: '12px',
                  background: 'rgba(10, 19, 31, 0.68)',
                  color: 'inherit',
                  border: '1px solid rgba(133, 157, 186, 0.24)',
                  padding: '0.85rem',
                  marginBottom: '0.85rem',
                }}
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={() => annotationMutation.mutate()}
                disabled={annotationMutation.isPending || !annotationContent.trim()}
              >
                Save Annotation
              </Button>
            </div>
          </CardBody>
        </Card>

        <Card className="overview-card">
          <CardHeader>
            <CardTitle>Review Activity</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="recent-list">
              {activityItems.map((item) => (
                <div key={item.id} className="recent-item">
                  <div className="recent-content">
                    <div className="recent-query" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      {item.icon}
                      <span>{item.title}</span>
                    </div>
                    <div className="recent-domain">{item.subtitle}</div>
                  </div>
                  <div className="recent-status">
                    <Badge variant="neutral" size="sm">{item.timestamp ? item.timestamp.slice(0, 16).replace('T', ' ') : 'n/a'}</Badge>
                  </div>
                </div>
              ))}
              {activityItems.length === 0 && <div className="empty-state">No review actions recorded yet.</div>}
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
};

function buildOperatorCommands(activeCase: TopicCase): Array<{ label: string; command: string }> {
  const commands = [
    {
      label: 'Inspect Case State',
      command: `uv run triangulate case show ${activeCase.id}`,
    },
  ];

  if (activeCase.status === 'review ready') {
    commands.push({
      label: 'Approve Case',
      command: `uv run triangulate case review ${activeCase.id} --decision approve`,
    });
    commands.push({
      label: 'Mark Action Required',
      command: `uv run triangulate case review ${activeCase.id} --decision action_required`,
    });
  }

  if (activeCase.status !== 'approved') {
    commands.push({
      label: 'Rerun From Retrieve',
      command: `uv run triangulate case rerun ${activeCase.id} --from retrieve`,
    });
  }

  return commands;
}

export default CaseIntelligenceCenter;
