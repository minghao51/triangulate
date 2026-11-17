import React from 'react';
import type { Party } from '../../types/backend-models';
import { ThumbsUp, ThumbsDown, Search, ChevronDown, ChevronRight } from 'lucide-react';
import './PartyInvestigationPanel.css';

interface PartyInvestigationPanelProps {
    party: Party;
}

export const PartyInvestigationPanel: React.FC<PartyInvestigationPanelProps> = ({ party }) => {
    const { investigationData, claimsSupported, claimsContested } = party;

    if (!investigationData) {
        return null;
    }

    const typedData = investigationData as {
        claims_supported?: Array<{ claim_text?: string; claim_id?: string }>;
        claims_contested?: Array<{ claim_text?: string; claim_id?: string }>;
        unique_claims?: Array<{ claim_text?: string; claim_id?: string }>;
        party_stance?: {
            overall_position?: string;
            key_concerns?: string[];
            priorities?: string[];
        };
    };

    const claimsSupportedList = typedData.claims_supported || [];
    const claimsContestedList = typedData.claims_contested || [];
    const uniqueClaims = typedData.unique_claims || [];
    const partyStance = typedData.party_stance || {};

    return (
        <div className="party-investigation-panel">
            <div className="investigation-stats">
                <div className="stat-item supporting">
                    <ThumbsUp size={14} />
                    <span className="stat-value">{claimsSupported}</span>
                    <span className="stat-label">Supported</span>
                </div>
                <div className="stat-item contesting">
                    <ThumbsDown size={14} />
                    <span className="stat-value">{claimsContested}</span>
                    <span className="stat-label">Contested</span>
                </div>
                <div className="stat-item unique">
                    <Search size={14} />
                    <span className="stat-value">{uniqueClaims.length}</span>
                    <span className="stat-label">Unique Claims</span>
                </div>
            </div>

            {partyStance.overall_position && (
                <div className="stance-section">
                    <h5>Party Position</h5>
                    <p className="stance-text">{partyStance.overall_position}</p>
                </div>
            )}

            {partyStance.key_concerns && partyStance.key_concerns.length > 0 && (
                <div className="concerns-section">
                    <h5>Key Concerns</h5>
                    <ul className="concerns-list">
                        {partyStance.key_concerns.map((concern, idx) => (
                            <li key={idx}>{concern}</li>
                        ))}
                    </ul>
                </div>
            )}

            {partyStance.priorities && partyStance.priorities.length > 0 && (
                <div className="priorities-section">
                    <h5>Priorities</h5>
                    <ul className="priorities-list">
                        {partyStance.priorities.map((priority, idx) => (
                            <li key={idx}>{priority}</li>
                        ))}
                    </ul>
                </div>
            )}

            {claimsSupportedList.length > 0 && (
                <div className="claims-section">
                    <h5>Claims Supported</h5>
                    <div className="claims-list">
                        {claimsSupportedList.map((claim, idx) => (
                            <div key={idx} className="claim-item supported">
                                <ThumbsUp size={12} />
                                <span>{claim.claim_text || claim.claim_id}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {claimsContestedList.length > 0 && (
                <div className="claims-section">
                    <h5>Claims Contested</h5>
                    <div className="claims-list">
                        {claimsContestedList.map((claim, idx) => (
                            <div key={idx} className="claim-item contested">
                                <ThumbsDown size={12} />
                                <span>{claim.claim_text || claim.claim_id}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

interface PartyCardAccordionProps {
    party: Party;
    defaultExpanded?: boolean;
}

export const PartyCardAccordion: React.FC<PartyCardAccordionProps> = ({
    party,
    defaultExpanded = false
}) => {
    const [isExpanded, setIsExpanded] = React.useState(defaultExpanded);

    return (
        <div className={`party-card-accordion glass-panel ${isExpanded ? 'expanded' : ''}`}>
            <button
                className="accordion-header"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <div className="header-content">
                    <div className={`stance-indicator stance-${party.overallStance}`} />
                    <span className="party-name">{party.name}</span>
                    {party.claimsSupported > 0 || party.claimsContested > 0 ? (
                        <span className="investigation-summary">
                            {party.claimsSupported} supported, {party.claimsContested} contested
                        </span>
                    ) : null}
                </div>
                {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </button>

            {isExpanded && (
                <div className="accordion-content">
                    <PartyInvestigationPanel party={party} />
                </div>
            )}
        </div>
    );
};

export default PartyInvestigationPanel;
