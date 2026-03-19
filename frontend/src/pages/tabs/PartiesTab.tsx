import React, { useEffect, useState } from 'react';
import type { Party } from '../../types/backend-models';
import { getPartiesForCase } from '../../services/api';
import { GitMerge, Check, AlertCircle } from 'lucide-react';
import './PartiesTab.css';

interface PartiesTabProps {
  caseId: string;
  refreshToken?: number;
}

const PartiesTab: React.FC<PartiesTabProps> = ({ caseId, refreshToken = 0 }) => {
    const [parties, setParties] = useState<Party[]>([]);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (caseId) {
            getPartiesForCase(caseId).then(setParties).catch((err: Error) => setError(err.message));
        }
    }, [caseId, refreshToken]);

    return (
        <div className="parties-container p-base">
            <div className="parties-header">
                <h3>Confirmed & Inferred Parties</h3>
                <p className="subtitle">Entities and their narrative stances detected across the retrieved sources.</p>
            </div>

            <div className="parties-grid">
                {error && <div>Failed to load parties: {error}</div>}
                {parties.map(party => (
                    <div key={party.id} className="party-card glass-panel">
                        <div className={`party-stance-bar stance-${party.overallStance}`} />
                        <div className="party-card-inner">
                            <div className="party-card-header">
                                <h4>{party.name}</h4>
                                {party.isModelInferred ? (
                                    <span className="badge badge-warning" title="Model Inferred"><AlertCircle size={12} /> Inferred</span>
                                ) : (
                                    <span className="badge badge-success" title="Bootstrap Confirmed"><Check size={12} /> Confirmed</span>
                                )}
                            </div>

                            <div className="party-aliases">
                                {party.aliases.length > 0 && <span className="alias-label">a.k.a: </span>}
                                {party.aliases.join(', ')}
                            </div>

                            <p className="party-description">{party.description}</p>

                            <div className="party-footer">
                                <div className="party-metric">
                                    <GitMerge size={16} className="text-secondary" />
                                    <span>{party.associatedClaimsCount} Associated Claims</span>
                                </div>
                                <div className={`party-stance-badge stance-badge-${party.overallStance}`}>
                                    Stance: {party.overallStance.toUpperCase()}
                                </div>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default PartiesTab;
