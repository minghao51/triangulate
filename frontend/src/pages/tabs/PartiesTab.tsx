import React, { useEffect, useState } from 'react';
import type { Party } from '../../types/backend-models';
import { getPartiesForCase } from '../../services/api';
import { PartyCardAccordion } from '../../components/parties/PartyInvestigationPanel';
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
                    <PartyCardAccordion key={party.id} party={party} />
                ))}
            </div>
        </div>
    );
};

export default PartiesTab;
