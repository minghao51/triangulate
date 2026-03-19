import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { TopicCase } from '../types/backend-models';
import { getCases } from '../services/api';
import { formatDistanceToNow, parseISO } from 'date-fns';
import { AlertCircle, FileSearch, ShieldCheck, Activity, Search, Filter, Plus } from 'lucide-react';
import './CaseIndex.css';

const CaseIndex: React.FC = () => {
    const [cases, setCases] = useState<TopicCase[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [search, setSearch] = useState('');
    const [statusFilter, setStatusFilter] = useState<'all' | TopicCase['status']>('all');
    const [stageFilter, setStageFilter] = useState<'all' | TopicCase['stage']>('all');
    const navigate = useNavigate();

    useEffect(() => {
        getCases()
            .then(setCases)
            .catch((err: Error) => setError(err.message));
    }, []);

    const getStatusBadge = (status: TopicCase['status']) => {
        switch (status) {
            case 'review ready': return 'badge-success';
            case 'investigating': return 'badge-warning';
            case 'discovering': return 'badge-info';
            case 'processing': return 'badge-info';
            case 'failed': return 'badge-danger';
            case 'rejected': return 'badge-danger';
            default: return 'badge-neutral';
        }
    };

    const filteredCases = cases.filter((tc) => {
        const matchesSearch = !search
            || `${tc.query} ${tc.conflictDomain}`.toLowerCase().includes(search.toLowerCase());
        const matchesStatus = statusFilter === 'all' || tc.status === statusFilter;
        const matchesStage = stageFilter === 'all' || tc.stage === stageFilter;
        return matchesSearch && matchesStatus && matchesStage;
    });

    const statuses = Array.from(new Set(cases.map((tc) => tc.status)));
    const stages = Array.from(new Set(cases.map((tc) => tc.stage)));

    return (
        <div className="case-index">
            <div className="index-header">
                <div>
                    <h1 className="index-title">Active Investigations</h1>
                    <p className="index-subtitle">Monitor and review automated case pipelines.</p>
                </div>
                <button className="btn btn-primary" onClick={() => navigate('/cases/new')}>
                    <Plus size={16} /> CLI Guide
                </button>
            </div>

            <div className="index-toolbar card">
                <div className="toolbar-search">
                    <Search size={18} className="text-secondary" />
                    <input
                        type="text"
                        className="input-field"
                        placeholder="Search queries or domains..."
                        style={{ border: 'none', background: 'transparent' }}
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                    />
                </div>
                <div className="toolbar-filters">
                    <label className="btn btn-secondary">
                        <Filter size={16} /> Status
                        <select
                            value={statusFilter}
                            onChange={(event) => setStatusFilter(event.target.value as 'all' | TopicCase['status'])}
                            style={{ border: 'none', background: 'transparent' }}
                        >
                            <option value="all">All</option>
                            {statuses.map((status) => (
                                <option key={status} value={status}>{status}</option>
                            ))}
                        </select>
                    </label>
                    <label className="btn btn-secondary">
                        <Filter size={16} /> Stage
                        <select
                            value={stageFilter}
                            onChange={(event) => setStageFilter(event.target.value as 'all' | TopicCase['stage'])}
                            style={{ border: 'none', background: 'transparent' }}
                        >
                            <option value="all">All</option>
                            {stages.map((stage) => (
                                <option key={stage} value={stage}>{stage}</option>
                            ))}
                        </select>
                    </label>
                </div>
            </div>

            <div className="case-table-container card">
                {error && (
                    <div style={{ padding: '1rem', color: 'var(--danger, #b42318)' }}>
                        Failed to load cases: {error}
                    </div>
                )}
                <table className="case-table">
                    <thead>
                        <tr>
                            <th>Query & Domain</th>
                            <th>Status / Stage</th>
                            <th>Metrics</th>
                            <th>Exceptions</th>
                            <th>Last Updated</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredCases.map(tc => (
                            <tr key={tc.id} className="case-row" onClick={() => navigate(`/cases/${tc.id}`)}>
                                <td>
                                    <div className="case-query">{tc.query}</div>
                                    <div className="case-domain">{tc.conflictDomain}</div>
                                </td>
                                <td>
                                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                        <span className={`badge ${getStatusBadge(tc.status)}`}>{tc.status}</span>
                                        <span className="badge badge-neutral">{tc.stage}</span>
                                    </div>
                                </td>
                                <td>
                                    <div className="case-metrics">
                                        <span title="Articles"><FileSearch size={14} /> {tc.counts.articles}</span>
                                        <span title="Events"><Activity size={14} /> {tc.counts.events}</span>
                                    </div>
                                </td>
                                <td>
                                    {tc.openExceptionsCount > 0 ? (
                                        <div className="exception-indicator warning">
                                            <AlertCircle size={14} /> {tc.openExceptionsCount} Action{tc.openExceptionsCount > 1 ? 's' : ''} Required
                                        </div>
                                    ) : (
                                        <div className="exception-indicator healthy">
                                            <ShieldCheck size={14} /> Clear
                                        </div>
                                    )}
                                </td>
                                <td className="case-time">
                                    {tc.lastUpdated
                                        ? formatDistanceToNow(parseISO(tc.lastUpdated), { addSuffix: true })
                                        : 'Unknown'}
                                </td>
                                <td className="case-actions">
                                    <button className="btn btn-secondary" onClick={(e) => { e.stopPropagation(); navigate(`/cases/${tc.id}`); }}>
                                        Review
                                    </button>
                                </td>
                            </tr>
                        ))}
                        {filteredCases.length === 0 && (
                            <tr>
                                <td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-tertiary)' }}>
                                    No investigations match the current filters.
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default CaseIndex;
