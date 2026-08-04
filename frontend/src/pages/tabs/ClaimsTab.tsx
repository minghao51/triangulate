import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Claim, NarrativeCluster, SourceStanceBreakdown as SourceStanceBreakdownType } from '../../types/backend-models';
import { getClaimsOverviewForCase } from '../../services/api';
import { ShieldAlert, ThumbsUp, ThumbsDown, GitCommit, ChevronDown, ChevronRight, ChevronUp, Layers, Minus } from 'lucide-react';
import { ClaimDetailPanel } from '../../components/claims/ClaimDetailPanel';
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
    const [expandedClaims, setExpandedClaims] = useState<Set<string>>(new Set());

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

    const toggleSet = (set: Set<string>, setter: (s: Set<string>) => void, id: string) => {
        const next = new Set(set);
        if (next.has(id)) {
            next.delete(id);
        } else {
            next.add(id);
        }
        setter(next);
    };

    const toggleNarrative = (id: string) => toggleSet(expandedNarratives, setExpandedNarratives, id);
    const toggleClaim = (id: string) => toggleSet(expandedClaims, setExpandedClaims, id);

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
                                        <ClaimRow
                                            key={claim.id}
                                            claim={claim}
                                            caseId={caseId}
                                            navigate={navigate}
                                            isExpanded={expandedClaims.has(claim.id)}
                                            onToggle={() => toggleClaim(claim.id)}
                                        />
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
                    <ClaimRow
                        key={claim.id}
                        claim={claim}
                        caseId={caseId}
                        navigate={navigate}
                        isExpanded={expandedClaims.has(claim.id)}
                        onToggle={() => toggleClaim(claim.id)}
                    />
                ))}
            </div>
        </div>
    );
};

interface ClaimRowProps {
    claim: Claim;
    caseId: string;
    navigate: ReturnType<typeof useNavigate>;
    isExpanded: boolean;
    onToggle: () => void;
}

const SourceStanceBreakdown: React.FC<{ breakdown: SourceStanceBreakdownType }> = ({ breakdown }) => {
    const hasSources = breakdown.agreedSources.length > 0 || breakdown.disagreedSources.length > 0 || breakdown.didntReportSources.length > 0;

    if (!hasSources) {
        return null;
    }

    return (
        <div className="source-stance-breakdown">
            {breakdown.agreedSources.length > 0 && (
                <div className="stance-group">
                    <span className="stance-label">Agreed</span>
                    <div className="stance-sources">
                        {breakdown.agreedSources.map((source) => (
                            <span key={source} className="stance-source agreed" title="Reported supporting this claim">
                                <ThumbsUp size={10} /> {source}
                            </span>
                        ))}
                    </div>
                </div>
            )}
            {breakdown.disagreedSources.length > 0 && (
                <div className="stance-group">
                    <span className="stance-label">Disagreed</span>
                    <div className="stance-sources">
                        {breakdown.disagreedSources.map((source) => (
                            <span key={source} className="stance-source disagreed" title="Reported contradicting this claim">
                                <ThumbsDown size={10} /> {source}
                            </span>
                        ))}
                    </div>
                </div>
            )}
            {breakdown.didntReportSources.length > 0 && (
                <div className="stance-group">
                    <span className="stance-label">Didn&apos;t Report</span>
                    <div className="stance-sources">
                        {breakdown.didntReportSources.map((source) => (
                            <span key={source} className="stance-source didnt-report" title="Did not report on this claim">
                                <Minus size={10} /> {source}
                            </span>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

const ClaimRow: React.FC<ClaimRowProps> = ({ claim, caseId, navigate, isExpanded, onToggle }) => (
    <div key={claim.id} className={`claim-row glass-panel ${isExpanded ? 'expanded' : ''}`}>
        <div className="claim-main">
            <div className="claim-header-row">
                <button className="expand-btn" onClick={onToggle}>
                    {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>
                <div className="claim-tags">
                    <span className={`badge ${claim.type === 'fact' ? 'badge-info' : 'badge-warning'}`}>
                        {claim.type}
                    </span>
                    <span className={`badge ${claim.verificationStatus === 'confirmed' ? 'badge-success' : 'badge-danger'}`}>
                        {claim.verificationStatus}
                    </span>
                </div>
            </div>
            <p className="claim-text">{claim.text}</p>
            <div className="claim-signature"><GitCommit size={14} /> {claim.claimSignature}</div>
            <SourceStanceBreakdown breakdown={claim.sourceStanceBreakdown} />
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

        {isExpanded && <ClaimDetailPanel claim={claim} />}
    </div>
);

export default ClaimsTab;
