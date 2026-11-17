import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { Claim, NarrativeCluster } from '../../types/backend-models';
import { getClaimsOverviewForCase } from '../../services/api';
import { ShieldAlert, ThumbsUp, ThumbsDown, GitCommit, ChevronDown, ChevronRight, Layers } from 'lucide-react';
import './ClaimsTab.css';

interface ClaimsTabProps {
  caseId: string;
  refreshToken?: number;
}

/**
 * Claims tab.
 *
 * Data is fetched through React Query keyed by case, so a slow response for a
 * previous case can never overwrite the current case's claims. Selection and
 * expansion state live in a component keyed by case, so it resets with the case.
 */
const ClaimsTab: React.FC<ClaimsTabProps> = ({ caseId, refreshToken = 0 }) => {
    const { data, isLoading, error, refetch } = useQuery({
        queryKey: ['claims-overview', caseId, refreshToken],
        queryFn: () => getClaimsOverviewForCase(caseId),
        enabled: !!caseId,
    });

    if (!caseId) {
        return (
            <div className="claims-container p-base">
                <div role="alert">No case selected for claims.</div>
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className="claims-container p-base">
                <div className="claims-header">
                    <h3>Primary Claims Mapping</h3>
                    <p className="subtitle">Corroboration network for identified facts and allegations.</p>
                </div>
                <div className="claims-state" role="status">Loading claims…</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="claims-container p-base">
                <div className="claims-header">
                    <h3>Primary Claims Mapping</h3>
                    <p className="subtitle">Corroboration network for identified facts and allegations.</p>
                </div>
                <div className="claims-state claims-state--error" role="alert">
                    <p>
                        Failed to load claims
                        {error instanceof Error && error.message ? `: ${error.message}` : '.'}
                    </p>
                    <button type="button" className="btn btn-secondary" onClick={() => refetch()}>
                        Retry
                    </button>
                </div>
            </div>
        );
    }

    return (
        <ClaimsContent
            key={caseId}
            caseId={caseId}
            claims={data?.claims ?? []}
            narratives={data?.narratives ?? []}
        />
    );
};

interface ClaimsContentProps {
    caseId: string;
    claims: Claim[];
    narratives: NarrativeCluster[];
}

const ClaimsContent: React.FC<ClaimsContentProps> = ({ caseId, claims, narratives }) => {
    const navigate = useNavigate();
    const [expandedNarratives, setExpandedNarratives] = useState<Set<string>>(new Set());

    const toggleNarrative = (id: string) => {
        setExpandedNarratives((current) => {
            const next = new Set(current);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
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

            {claims.length === 0 && narratives.length === 0 ? (
                <div className="claims-state" role="status">
                    No claims have been recorded for this case yet.
                </div>
            ) : (
                <>
                    {narratives.length > 0 && (
                        <div className="narratives-section">
                            {narratives.map((narrative) => {
                                const isExpanded = expandedNarratives.has(narrative.id);
                                const narrativeClaims = claimsByNarrative[narrative.id] || [];

                                return (
                                    <div key={narrative.id} className="narrative-cluster glass-panel">
                                        <button
                                            type="button"
                                            className="narrative-header"
                                            aria-expanded={isExpanded}
                                            aria-controls={`narrative-claims-${narrative.id}`}
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
                                            <div className="narrative-claims" id={`narrative-claims-${narrative.id}`}>
                                                {narrativeClaims.length === 0 ? (
                                                    <p className="subtitle">No claim currently references this cluster.</p>
                                                ) : (
                                                    narrativeClaims.map((claim) => (
                                                        <ClaimRow key={claim.id} claim={claim} caseId={caseId} navigate={navigate} />
                                                    ))
                                                )}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}

                    <div className="claims-list">
                        {unclusteredClaims.map((claim) => (
                            <ClaimRow key={claim.id} claim={claim} caseId={caseId} navigate={navigate} />
                        ))}
                    </div>
                </>
            )}
        </div>
    );
};

interface ClaimRowProps {
    claim: Claim;
    caseId: string;
    navigate: ReturnType<typeof useNavigate>;
}

const ClaimRow: React.FC<ClaimRowProps> = ({ claim, caseId, navigate }) => (
    <div className="claim-row glass-panel">
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
            <button
                type="button"
                className="btn btn-secondary"
                onClick={() =>
                    navigate(`/cases/${caseId}/evidence?claim=${encodeURIComponent(claim.id)}`)
                }
            >
                Inspect Evidence
            </button>
        </div>
    </div>
);

export default ClaimsTab;
