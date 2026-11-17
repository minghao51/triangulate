import React from 'react';
import type { Claim } from '../../types/backend-models';
import { ThumbsUp, ThumbsDown, Minus, Users, Scale } from 'lucide-react';
import './ClaimDetailPanel.css';

interface ClaimDetailPanelProps {
    claim: Claim;
}

export const ClaimDetailPanel: React.FC<ClaimDetailPanelProps> = ({ claim }) => {
    const { arbiterReasoning, partyPositions } = claim;

    if (!arbiterReasoning && (!partyPositions || Object.keys(partyPositions).length === 0)) {
        return null;
    }

    const groupPartiesByPosition = (position: string) =>
        Object.entries(partyPositions || {})
            .filter(([, p]) => p === position)
            .map(([name]) => name);

    const supportingParties = groupPartiesByPosition('for');
    const opposingParties = groupPartiesByPosition('against');
    const neutralParties = groupPartiesByPosition('neutral');

    return (
        <div className="claim-detail-panel">
            {arbiterReasoning && (
                <div className="arbiter-section">
                    <div className="section-header">
                        <Scale size={16} />
                        <h4>Arbiter Analysis</h4>
                    </div>

                    <div className="arbiter-content">
                        <div className="arbiter-field">
                            <span className="field-label">Classification:</span>
                            <span className="field-value">{arbiterReasoning.isFact}</span>
                        </div>

                        <div className="arbiter-field">
                            <span className="field-label">Verification:</span>
                            <span className="field-value">{arbiterReasoning.verificationRationale}</span>
                        </div>

                        {arbiterReasoning.partyConsensus && (
                            <div className="party-consensus">
                                <div className="consensus-header">
                                    <Users size={14} />
                                    <span>Party Consensus: </span>
                                    {arbiterReasoning.partyConsensus.unanimous ? (
                                        <span className="unanimous-badge">Unanimous</span>
                                    ) : (
                                        <span className="divided-badge">Divided</span>
                                    )}
                                </div>

                                <div className="consensus-parties">
                                    {supportingParties.length > 0 && (
                                        <div className="party-group supporting">
                                            <ThumbsUp size={12} />
                                            <span className="party-label">Support:</span>
                                            <span className="party-names">{supportingParties.join(', ')}</span>
                                        </div>
                                    )}

                                    {opposingParties.length > 0 && (
                                        <div className="party-group opposing">
                                            <ThumbsDown size={12} />
                                            <span className="party-label">Oppose:</span>
                                            <span className="party-names">{opposingParties.join(', ')}</span>
                                        </div>
                                    )}

                                    {neutralParties.length > 0 && (
                                        <div className="party-group neutral">
                                            <Minus size={12} />
                                            <span className="party-label">Neutral:</span>
                                            <span className="party-names">{neutralParties.join(', ')}</span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {partyPositions && Object.keys(partyPositions).length > 0 && !arbiterReasoning && (
                <div className="party-positions-only">
                    <div className="section-header">
                        <Users size={16} />
                        <h4>Party Positions</h4>
                    </div>
                    <div className="party-positions-list">
                        {supportingParties.length > 0 && (
                            <div className="position-row supporting">
                                <ThumbsUp size={12} />
                                <span>{supportingParties.join(', ')}</span>
                            </div>
                        )}
                        {opposingParties.length > 0 && (
                            <div className="position-row opposing">
                                <ThumbsDown size={12} />
                                <span>{opposingParties.join(', ')}</span>
                            </div>
                        )}
                        {neutralParties.length > 0 && (
                            <div className="position-row neutral">
                                <Minus size={12} />
                                <span>{neutralParties.join(', ')}</span>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default ClaimDetailPanel;
