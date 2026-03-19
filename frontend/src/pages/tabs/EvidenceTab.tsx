import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { Evidence } from '../../types/backend-models';
import { getEvidenceForCase } from '../../services/api';
import { ShieldCheck, ShieldAlert, FileSearch, Link, ChevronDown, ChevronRight, ClipboardCheck } from 'lucide-react';
import './EvidenceTab.css';

type CredibilityFilter = 'all' | 'high' | 'medium' | 'low' | 'unknown';

interface EvidenceTabProps {
  caseId: string;
  refreshToken?: number;
}

const EvidenceTab: React.FC<EvidenceTabProps> = ({ caseId, refreshToken = 0 }) => {
    const [searchParams] = useSearchParams();
    const [evidence, setEvidence] = useState<Evidence[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [credibilityFilter, setCredibilityFilter] = useState<CredibilityFilter>('all');
    const [expandedChecks, setExpandedChecks] = useState<Set<string>>(new Set());
    const claimFilter = searchParams.get('claim');

    useEffect(() => {
        if (caseId) {
            getEvidenceForCase(caseId).then(setEvidence).catch((err: Error) => setError(err.message));
        }
    }, [caseId, refreshToken]);

    const toggleChecks = (id: string) => {
        const newExpanded = new Set(expandedChecks);
        if (newExpanded.has(id)) {
            newExpanded.delete(id);
        } else {
            newExpanded.add(id);
        }
        setExpandedChecks(newExpanded);
    };

    const renderVerificationBadge = (status: Evidence['verificationStatus']) => {
        switch (status) {
            case 'confirmed': return <span className="badge badge-success"><ShieldCheck size={12} /> Confirmed</span>;
            case 'contested': return <span className="badge badge-warning"><ShieldAlert size={12} /> Contested</span>;
            case 'debunked': return <span className="badge badge-danger">Debunked</span>;
            default: return <span className="badge badge-neutral">{status}</span>;
        }
    };

    const getCredibilityLabel = (tier: string | null) => {
        switch (tier) {
            case 'high': return 'High';
            case 'medium': return 'Medium';
            case 'low': return 'Low';
            case 'unknown': return 'Unknown';
            case 'user_supplied': return 'User Supplied';
            default: return tier || 'Unknown';
        }
    };

    let visibleEvidence = claimFilter
        ? evidence.filter((item) => item.linkedClaims.includes(claimFilter))
        : evidence;

    if (credibilityFilter !== 'all') {
        visibleEvidence = visibleEvidence.filter((item) => item.credibilityTier === credibilityFilter);
    }

    return (
        <div className="evidence-tab-container p-base">
            <div className="evidence-toolbar">
                <h3>Evidence Gallery ({visibleEvidence.length})</h3>
                <div className="toolbar-filters">
                    <div className="credibility-filter">
                        <button
                            className={credibilityFilter === 'all' ? 'active' : ''}
                            onClick={() => setCredibilityFilter('all')}
                        >
                            All
                        </button>
                        <button
                            className={credibilityFilter === 'high' ? 'active' : ''}
                            onClick={() => setCredibilityFilter('high')}
                        >
                            High
                        </button>
                        <button
                            className={credibilityFilter === 'medium' ? 'active' : ''}
                            onClick={() => setCredibilityFilter('medium')}
                        >
                            Medium
                        </button>
                        <button
                            className={credibilityFilter === 'low' ? 'active' : ''}
                            onClick={() => setCredibilityFilter('low')}
                        >
                            Low
                        </button>
                        <button
                            className={credibilityFilter === 'unknown' ? 'active' : ''}
                            onClick={() => setCredibilityFilter('unknown')}
                        >
                            Unknown
                        </button>
                    </div>
                </div>
            </div>

            <div className="evidence-grid">
                {error && <div>Failed to load evidence: {error}</div>}
                {!error && claimFilter && (
                    <div style={{ gridColumn: '1 / -1', color: 'var(--text-secondary)' }}>
                        Filtered to evidence linked to claim <code>{claimFilter}</code>.
                    </div>
                )}
                {visibleEvidence.map(ev => (
                    <div key={ev.id} className={`evidence-card glass-panel ${ev.requiresHumanReview ? 'requires-review' : ''}`}>
                        <div className="evidence-card-header">
                            {renderVerificationBadge(ev.verificationStatus)}
                            <span className="source-type">{ev.sourceType}</span>
                        </div>
                        <h4 className="evidence-title">{ev.title}</h4>
                        <div className="evidence-meta">
                            <span>{ev.publisher}</span>
                            <span className={`credibility tier-${ev.credibilityTier}`}>
                                {getCredibilityLabel(ev.credibilityTier)}
                            </span>
                        </div>

                        <div className="evidence-footer">
                            <span className="linked-claims"><FileSearch size={14} /> {ev.linkedClaims.length} Claims</span>
                            {ev.originUrl ? (
                                <a href={ev.originUrl} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">
                                    <Link size={14} /> Source
                                </a>
                            ) : (
                                <span className="btn btn-secondary btn-sm" aria-disabled="true">
                                    <Link size={14} /> Source
                                </span>
                            )}
                        </div>

                        {ev.verificationChecks.length > 0 && (
                            <div className="verification-section">
                                <button
                                    className="verification-toggle"
                                    onClick={() => toggleChecks(ev.id)}
                                >
                                    {expandedChecks.has(ev.id) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                    <ClipboardCheck size={14} />
                                    Verification Details ({ev.verificationChecks.length})
                                </button>

                                {expandedChecks.has(ev.id) && (
                                    <div className="verification-checks">
                                        {ev.verificationChecks.map((check) => (
                                            <div key={check.id} className="check-row">
                                                <div className="check-header">
                                                    <span className="check-type">{check.checkType}</span>
                                                    <span className="check-result badge badge-info">{check.result}</span>
                                                    {check.method && <span className="check-method">{check.method}</span>}
                                                </div>
                                                {check.notes && <p className="check-notes">{check.notes}</p>}
                                                {check.verifiedBy && (
                                                    <span className="check-meta">
                                                        by {check.verifiedBy} {check.verifiedAt && `at ${new Date(check.verifiedAt).toLocaleString()}`}
                                                    </span>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
};

export default EvidenceTab;
