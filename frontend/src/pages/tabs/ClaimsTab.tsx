import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import type { Claim } from '../../types/backend-models';
import { getClaimsForCase } from '../../services/api';
import { ShieldAlert, ThumbsUp, ThumbsDown, GitCommit } from 'lucide-react';
import './ClaimsTab.css';

const ClaimsTab: React.FC<{ refreshToken?: number }> = ({ refreshToken = 0 }) => {
    const { id } = useParams();
    const navigate = useNavigate();
    const [claims, setClaims] = useState<Claim[]>([]);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (id) {
            getClaimsForCase(id).then(setClaims).catch((err: Error) => setError(err.message));
        }
    }, [id, refreshToken]);

    return (
        <div className="claims-container p-base">
            <div className="claims-header">
                <h3>Primary Claims Mapping</h3>
                <p className="subtitle">Corroboration network for identified facts and allegations.</p>
            </div>

            <div className="claims-list">
                {error && <div>Failed to load claims: {error}</div>}
                {claims.map(claim => (
                    <div key={claim.id} className="claim-row">
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
                            <button className="btn btn-secondary" onClick={() => navigate(`/cases/${id}/evidence?claim=${claim.id}`)}>
                                Inspect Evidence
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default ClaimsTab;
