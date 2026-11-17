import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { Evidence } from '../../types/backend-models';
import { getEvidenceForCase } from '../../services/api';
import { ShieldCheck, ShieldAlert, FileSearch, Link, ChevronDown, ChevronRight, ClipboardCheck } from 'lucide-react';
import './EvidenceTab.css';

type CredibilityFilter = 'all' | 'high' | 'medium' | 'low' | 'unknown';

interface EvidenceTabProps {
  caseId: string;
  refreshToken?: number;
}

/**
 * Evidence tab.
 *
 * React Query keyed by case keeps a late response for a previous case from
 * replacing the current case's evidence, and the filter/expansion state lives in
 * a component keyed by case so it cannot leak across cases.
 */
const EvidenceTab: React.FC<EvidenceTabProps> = ({ caseId, refreshToken = 0 }) => {
    const { data, isLoading, error, refetch } = useQuery({
        queryKey: ['evidence', caseId, refreshToken],
        queryFn: () => getEvidenceForCase(caseId),
        enabled: !!caseId,
    });

    if (!caseId) {
        return (
            <div className="evidence-tab-container p-base">
                <div role="alert">No case selected for evidence.</div>
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className="evidence-tab-container p-base">
                <div className="evidence-toolbar">
                    <h3>Evidence Gallery</h3>
                </div>
                <div className="evidence-state" role="status">Loading evidence…</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="evidence-tab-container p-base">
                <div className="evidence-toolbar">
                    <h3>Evidence Gallery</h3>
                </div>
                <div className="evidence-state evidence-state--error" role="alert">
                    <p>
                        Failed to load evidence
                        {error instanceof Error && error.message ? `: ${error.message}` : '.'}
                    </p>
                    <button type="button" className="btn btn-secondary" onClick={() => refetch()}>
                        Retry
                    </button>
                </div>
            </div>
        );
    }

    return <EvidenceContent key={caseId} evidence={data ?? []} />;
};

interface EvidenceContentProps {
    evidence: Evidence[];
}

const EvidenceContent: React.FC<EvidenceContentProps> = ({ evidence }) => {
    const [searchParams] = useSearchParams();
    const [credibilityFilter, setCredibilityFilter] = useState<CredibilityFilter>('all');
    const [expandedChecks, setExpandedChecks] = useState<Set<string>>(new Set());
    const claimFilter = searchParams.get('claim');

    const toggleChecks = (id: string) => {
        setExpandedChecks((current) => {
            const next = new Set(current);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
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
                        {(['all', 'high', 'medium', 'low', 'unknown'] as CredibilityFilter[]).map((filter) => (
                            <button
                                key={filter}
                                type="button"
                                className={credibilityFilter === filter ? 'active' : ''}
                                aria-pressed={credibilityFilter === filter}
                                onClick={() => setCredibilityFilter(filter)}
                            >
                                {filter === 'all' ? 'All' : filter.charAt(0).toUpperCase() + filter.slice(1)}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {evidence.length === 0 && (
                <div className="evidence-state" role="status">
                    No evidence has been recorded for this case yet.
                </div>
            )}

            {evidence.length > 0 && claimFilter && (
                <div className="evidence-claim-filter-note">
                    Filtered to evidence linked to claim <code>{claimFilter}</code>.
                    {visibleEvidence.length === 0 && ' No recorded evidence links to this claim.'}
                </div>
            )}

            {evidence.length > 0 && visibleEvidence.length === 0 && !claimFilter && (
                <div className="evidence-state" role="status">
                    No evidence matches the selected credibility filter.
                </div>
            )}

            <div className="evidence-grid">
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
                                    type="button"
                                    className="verification-toggle"
                                    aria-expanded={expandedChecks.has(ev.id)}
                                    aria-controls={`verification-checks-${ev.id}`}
                                    onClick={() => toggleChecks(ev.id)}
                                >
                                    {expandedChecks.has(ev.id) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                    <ClipboardCheck size={14} />
                                    Verification Details ({ev.verificationChecks.length})
                                </button>

                                {expandedChecks.has(ev.id) && (
                                    <div className="verification-checks" id={`verification-checks-${ev.id}`}>
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
