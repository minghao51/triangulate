import React, { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import type { Evidence } from '../../types/backend-models';
import { getEvidenceForCase } from '../../services/api';
import { ShieldCheck, ShieldAlert, FileSearch, Link } from 'lucide-react';
import './EvidenceTab.css';

const EvidenceTab: React.FC<{ refreshToken?: number }> = ({ refreshToken = 0 }) => {
    const { id } = useParams();
    const [searchParams] = useSearchParams();
    const [evidence, setEvidence] = useState<Evidence[]>([]);
    const [error, setError] = useState<string | null>(null);
    const claimFilter = searchParams.get('claim');

    useEffect(() => {
        if (id) {
            getEvidenceForCase(id).then(setEvidence).catch((err: Error) => setError(err.message));
        }
    }, [id, refreshToken]);

    const renderVerificationBadge = (status: Evidence['verificationStatus']) => {
        switch (status) {
            case 'confirmed': return <span className="badge badge-success"><ShieldCheck size={12} /> Confirmed</span>;
            case 'contested': return <span className="badge badge-warning"><ShieldAlert size={12} /> Contested</span>;
            case 'debunked': return <span className="badge badge-danger">Debunked</span>;
            default: return <span className="badge badge-neutral">{status}</span>;
        }
    };

    const visibleEvidence = claimFilter
        ? evidence.filter((item) => item.linkedClaims.includes(claimFilter))
        : evidence;

    return (
        <div className="evidence-tab-container p-base">
            <div className="evidence-toolbar">
                <h3>Evidence Gallery ({visibleEvidence.length})</h3>
                <div className="toolbar-filters">
                    <select className="input-field">
                        <option>All Types</option>
                        <option>Web</option>
                        <option>Social</option>
                        <option>RSS</option>
                    </select>
                    <select className="input-field">
                        <option>Any Status</option>
                        <option>Confirmed</option>
                        <option>Contested</option>
                        <option>Needs Review</option>
                    </select>
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
                    <div key={ev.id} className={`evidence-card ${ev.requiresHumanReview ? 'requires-review' : ''}`}>
                        <div className="evidence-card-header">
                            {renderVerificationBadge(ev.verificationStatus)}
                            <span className="source-type">{ev.sourceType}</span>
                        </div>
                        <h4 className="evidence-title">{ev.title}</h4>
                        <div className="evidence-meta">
                            <span>{ev.publisher}</span>
                            <span className={`credibility tier-${ev.credibilityTier}`}>Tier: {ev.credibilityTier}</span>
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
                    </div>
                ))}
            </div>
        </div>
    );
};

export default EvidenceTab;
