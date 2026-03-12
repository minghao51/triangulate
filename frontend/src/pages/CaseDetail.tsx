import React, { useEffect, useState } from 'react';
import { useParams, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import type { TopicCase } from '../types/backend-models';
import { getCaseDetail, rerunCase, reviewCase } from '../services/api';
import clsx from 'clsx';
import { ShieldAlert, PlayCircle, GitMerge, FileText, Users, Clock, AlertTriangle } from 'lucide-react';
import './CaseDetail.css';

// Sub-components
import EvidenceTab from './tabs/EvidenceTab';
import ClaimsTab from './tabs/ClaimsTab';
import ExceptionsTab from './tabs/ExceptionsTab';
import PartiesTab from './tabs/PartiesTab';
import TimelineTab from './tabs/TimelineTab';
import ReportTab from './tabs/ReportTab';
import RunHistoryTab from './tabs/RunHistoryTab';

const OverviewTab: React.FC<{
    activeCase: TopicCase;
    actionPending: boolean;
    onReviewAction: (decision: 'approve' | 'reject' | 'action_required') => Promise<void>;
}> = ({ activeCase, actionPending, onReviewAction }) => (
    <div className="p-base">
        <h3>Case Overview</h3>
        <p className="subtitle">Current workflow state and summary metrics for this investigation.</p>
        <div style={{ display: 'grid', gap: '1rem', marginTop: '1rem' }}>
            <div><strong>Query:</strong> {activeCase.query}</div>
            <div><strong>Conflict Domain:</strong> {activeCase.conflictDomain}</div>
            <div><strong>Status:</strong> {activeCase.status}</div>
            <div><strong>Stage:</strong> {activeCase.stage}</div>
            <div><strong>Review Items:</strong> {activeCase.counts.reviewItems}</div>
            <div><strong>Report Path:</strong> {activeCase.reportPath || 'Not generated yet'}</div>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.5rem', flexWrap: 'wrap' }}>
            <button className="btn btn-primary" disabled={actionPending || activeCase.openExceptionsCount > 0} onClick={() => onReviewAction('approve')}>
                Approve Case
            </button>
            <button className="btn btn-secondary" disabled={actionPending} onClick={() => onReviewAction('action_required')}>
                Mark Action Required
            </button>
            <button className="btn btn-secondary" disabled={actionPending} onClick={() => onReviewAction('reject')}>
                Reject Case
            </button>
        </div>
    </div>
);

const CaseDetail: React.FC = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const location = useLocation();
    const currentPath = location.pathname.split('/').pop();
    const [activeCase, setActiveCase] = useState<TopicCase | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [actionPending, setActionPending] = useState(false);
    const [refreshToken, setRefreshToken] = useState(0);

    useEffect(() => {
        if (!id) {
            return;
        }
        getCaseDetail(id)
            .then((detail) => setActiveCase(detail.case))
            .catch((err: Error) => setError(err.message));
    }, [id, refreshToken]);

    const handleRerun = async () => {
        if (!id) {
            return;
        }
        setActionPending(true);
        setError(null);
        try {
            const detail = await rerunCase(id);
            setActiveCase(detail.case);
            setRefreshToken((value) => value + 1);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to rerun case');
        } finally {
            setActionPending(false);
        }
    };

    const handleReviewAction = async (
        decision: 'approve' | 'reject' | 'action_required',
    ) => {
        if (!id) {
            return;
        }
        setActionPending(true);
        setError(null);
        try {
            const detail = await reviewCase(id, decision);
            setActiveCase(detail.case);
            setRefreshToken((value) => value + 1);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to review case');
        } finally {
            setActionPending(false);
        }
    };

    const tabs = [
        { id: 'overview', label: 'Overview', icon: <FileText size={16} /> },
        { id: 'evidence', label: 'Evidence', icon: <FileText size={16} /> },
        { id: 'claims', label: 'Claims', icon: <GitMerge size={16} /> },
        { id: 'parties', label: 'Parties', icon: <Users size={16} /> },
        { id: 'timeline', label: 'Timeline', icon: <Clock size={16} /> },
        { id: 'exceptions', label: 'Exceptions', icon: <AlertTriangle size={16} /> },
        { id: 'report', label: 'Report', icon: <FileText size={16} /> },
        { id: 'run-history', label: 'Run History', icon: <PlayCircle size={16} /> },
    ];

    if (error) {
        return <div className="p-base">Failed to load case: {error}</div>;
    }

    if (!activeCase) {
        return <div className="p-base">Loading case...</div>;
    }

    return (
        <div className="case-detail-container">
            {/* Top Summary Banner */}
            <div className="case-banner card">
                <div className="banner-top">
                    <div className="banner-title-area">
                        <h1>{activeCase.query}</h1>
                        <div className="domain-label">{activeCase.conflictDomain}</div>
                    </div>
                    <div className="banner-status-area">
                        <span className="badge badge-warning">{activeCase.status}</span>
                        <span className="badge badge-neutral">{activeCase.stage}</span>
                        <span className="badge badge-info">{activeCase.automationMode} mode</span>
                    </div>
                </div>
                <div className="banner-metrics">
                    <div className="metric">
                        <span className="metric-val">{activeCase.counts.articles}</span>
                        <span className="metric-lbl">Sources</span>
                    </div>
                    <div className="metric">
                        <span className="metric-val">{activeCase.counts.events}</span>
                        <span className="metric-lbl">Timeline Events</span>
                    </div>
                    <div className="metric">
                        <span className={`metric-val ${activeCase.openExceptionsCount > 0 ? 'text-warning' : ''}`}>
                            {activeCase.openExceptionsCount}
                        </span>
                        <span className="metric-lbl">Open Exceptions</span>
                    </div>
                    <div className="metric-actions">
                        <button className="btn btn-secondary" disabled={actionPending} onClick={handleRerun}>
                            <PlayCircle size={16} /> {actionPending ? 'Running...' : 'Run Next Stage'}
                        </button>
                        <button className="btn btn-primary" disabled={activeCase.openExceptionsCount === 0} onClick={() => navigate(`/cases/${id}/exceptions`)}>
                            <ShieldAlert size={16} /> Resolve Exceptions ({activeCase.openExceptionsCount})
                        </button>
                    </div>
                </div>
            </div>

            {error && (
                <div className="card" style={{ padding: '1rem', color: 'var(--danger, #b42318)' }}>
                    {error}
                </div>
            )}

            {/* Internal Navigation Tabs */}
            <div className="case-tabs">
                {tabs.map(tab => (
                    <button
                        key={tab.id}
                        className={clsx("tab-button", (currentPath === tab.id || (currentPath === id && tab.id === 'overview')) && "active")}
                        onClick={() => navigate(`/cases/${id}/${tab.id === 'overview' ? '' : tab.id}`)}
                    >
                        {tab.icon} {tab.label}
                    </button>
                ))}
            </div>

            {/* Tab Content Area */}
            <div className="case-tab-content card">
                <Routes>
                    <Route index element={<OverviewTab activeCase={activeCase} actionPending={actionPending} onReviewAction={handleReviewAction} />} />
                    <Route path="evidence" element={<EvidenceTab refreshToken={refreshToken} />} />
                    <Route path="claims" element={<ClaimsTab refreshToken={refreshToken} />} />
                    <Route path="exceptions" element={<ExceptionsTab refreshToken={refreshToken} onCaseMutated={() => setRefreshToken((value) => value + 1)} />} />
                    <Route path="parties" element={<PartiesTab refreshToken={refreshToken} />} />
                    <Route path="timeline" element={<TimelineTab refreshToken={refreshToken} />} />
                    <Route path="report" element={<ReportTab refreshToken={refreshToken} />} />
                    <Route path="run-history" element={<RunHistoryTab refreshToken={refreshToken} />} />
                    {/* Fallback for others */}
                    <Route path="*" element={<div className="p-base">Work in progress...</div>} />
                </Routes>
            </div>
        </div>
    );
};

export default CaseDetail;
