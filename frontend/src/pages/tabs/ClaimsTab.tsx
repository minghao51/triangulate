import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Claim, NarrativeCluster } from '../../types/backend-models';
import { getClaimsOverviewForCase } from '../../services/api';
import { ShieldAlert, ThumbsUp, ThumbsDown, GitCommit, ChevronDown, ChevronRight, Layers } from 'lucide-react';
import './ClaimsTab.css';

interface ClaimsTabProps {
  caseId: string;
  refreshToken?: number;
}

const ClaimsTab: React.FC<ClaimsTabProps> = ({ caseId, refreshToken = 0 }) => {
    const navigate = useNavigate();
    const [claims, setClaims] = useState<Claim[]>([]);
    const [narratives, setNarratives] = useState<NarrativeCluster[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [expandedNarratives, setExpandedNarratives] = useState<Set<string>>(new Set());

    useEffect(() => {
        if (caseId) {
            getClaimsOverviewForCase(caseId)
                .then((data) => {
                    setClaims(data.claims);
                    setNarratives(data.narratives);
                })
                .catch((err: Error) => setError(err.message));
        }
    }, [caseId, refreshToken]);

    const toggleNarrative = (id: string) => {
        const newExpanded = new Set(expandedNarratives);
        if (newExpanded.has(id)) {
            newExpanded.delete(id);
        } else {
            newExpanded.add(id);
        }
        setExpandedNarratives(newExpanded);
    };

    const claimsByNarrative = useMemo(
        () =>
            narratives.reduce((acc, narrative) => {
                acc[narrative.id] = claims.filter(
                    (claim) => claim.narrativeClusterId === narrative.clusterId
                );
                return acc;
            }, {} as Record<string, Claim[]>),
        [claims, narratives]
    );

    const clusteredClaimIds = useMemo(
        () =>
            new Set(
                Object.values(claimsByNarrative)
                    .flat()
                    .map((claim) => claim.id)
            ),
        [claimsByNarrative]
    );

    const unclusteredClaims = useMemo(
        () => claims.filter((claim) => !clusteredClaimIds.has(claim.id)),
        [claims, clusteredClaimIds]
    );

    return (
        <div className="claims-container p-base">
            <div className="claims-header">
                <h3>Primary Claims Mapping</h3>
                <p className="subtitle">Corroboration network for identified facts and allegations.</p>
            </div>

            <div className="narratives-section">
                {narratives.length > 0 && narratives.map((narrative) => {
                    const isExpanded = expandedNarratives.has(narrative.id);
                    const narrativeClaims = claimsByNarrative[narrative.id] || [];

                        return (
                        <div key={narrative.id} className="narrative-cluster glass-panel">
                            <button
                                className="narrative-header"
                                onClick={() => toggleNarrative(narrative.id)}
                            >
                                <div className="narrative-title-row">
                                    {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                                    <Layers size={16} className="narrative-icon" />
                                    <span className="narrative-summary">{narrative.stanceSummary}</span>
                                </div>
                                <div className="narrative-meta">
                                    <span className="narrative-count">{narrative.claimCount} claims</span>
                                    <span className="narrative-sources">{narrative.sourceCount} sources</span>
                                </div>
                            </button>

                            {isExpanded && (
                                <div className="narrative-claims">
                                    {narrativeClaims.map((claim) => (
                                        <ClaimRow key={claim.id} claim={claim} caseId={caseId} navigate={navigate} />
                                    ))}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>

            <div className="claims-list">
                {error && <div>Failed to load claims: {error}</div>}
                {unclusteredClaims.map((claim) => (
                    <ClaimRow key={claim.id} claim={claim} caseId={caseId} navigate={navigate} />
                ))}
            </div>
        </div>
    );
};

interface ClaimRowProps {
    claim: Claim;
    caseId: string;
    navigate: ReturnType<typeof useNavigate>;
}

const ClaimRow: React.FC<ClaimRowProps> = ({ claim, caseId, navigate }) => (
    <div key={claim.id} className="claim-row glass-panel">
        <div className="claim-main">
            <div className="claim-tags">
                <span className={`badge ${claim.type === 'fact' ? 'badge-info' : 'badge-warning'}`}>
                    {claim.type}
                </span>
                <span className={`badge ${claim.verificationStatus === 'confirmed' ? 'badge-success' : 'badge-danger'}`}>
                    {claim.verificationStatus}
                </span>
            </div>
            <p className="claim-text">{claim.text}</p>
            <div className="claim-signature"><GitCommit size={14} /> {claim.claimSignature}</div>
        </div>

        <div className="claim-metrics">
            <div className="corroboration-bar">
                <div className="corroboration-stat support">
                    <ThumbsUp size={16} /> {claim.supportCount}
                </div>
                <div className="corroboration-stat oppose">
                    <ThumbsDown size={16} /> {claim.opposeCount}
                </div>
            </div>
            <div className="diversity-badge">
                {claim.sourceDiversityCount} distinct source{claim.sourceDiversityCount !== 1 && 's'}
            </div>
            {(claim.controversyScore ?? 0) > 0.5 && (
                <div className="controversy-warning">
                    <ShieldAlert size={14} /> Highly Contested ({((claim.controversyScore ?? 0) * 100).toFixed(0)}%)
                </div>
            )}
        </div>

        <div className="claim-actions">
            <button className="btn btn-secondary" onClick={() => navigate(`/cases/${caseId}/evidence?claim=${claim.id}`)}>
                Inspect Evidence
            </button>
        </div>
    </div>
);

export default ClaimsTab;
