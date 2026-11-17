import React from 'react';
import { FileText, Users, UserSearch, Scale, ArrowRight, GitBranch } from 'lucide-react';
import './AdversarialFlowDiagram.css';

interface WorkflowNode {
    id: string;
    label: string;
    description: string;
    icon: React.ReactNode;
    status?: 'completed' | 'running' | 'pending';
    metadata?: Record<string, unknown>;
}

interface PartyInvestigationNode {
    partyName: string;
    status: 'completed' | 'running' | 'pending';
    claimsInvestigated: number;
}

interface AdversarialFlowDiagramProps {
    claimsCount: number;
    partiesCount: number;
    partyInvestigations: PartyInvestigationNode[];
    arbiterResult?: {
        factsCount: number;
        allegationsCount: number;
        agreementLevel: string;
    };
}

export const AdversarialFlowDiagram: React.FC<AdversarialFlowDiagramProps> = ({
    claimsCount,
    partiesCount,
    partyInvestigations,
    arbiterResult,
}) => {
    const nodes: WorkflowNode[] = [
        {
            id: 'collector',
            label: 'Collector',
            description: `Extracted ${claimsCount} claims from sources`,
            icon: <FileText size={20} />,
            status: 'completed',
        },
        {
            id: 'party_classifier',
            label: 'Party Classifier',
            description: `Identified ${partiesCount} parties`,
            icon: <Users size={20} />,
            status: 'completed',
        },
        {
            id: 'party_investigators',
            label: 'Party Investigators',
            description: `${partiesCount} parties investigating in parallel`,
            icon: <UserSearch size={20} />,
            status: 'completed',
        },
        {
            id: 'arbiter',
            label: 'Arbiter',
            description: arbiterResult
                ? `${arbiterResult.factsCount} facts, ${arbiterResult.allegationsCount} allegations`
                : 'Making final determinations',
            icon: <Scale size={20} />,
            status: arbiterResult ? 'completed' : 'pending',
        },
    ];

    return (
        <div className="adversarial-flow-diagram">
            <h3 className="diagram-title">Adversarial Investigation Flow</h3>

            <div className="flow-container">
                <div className="flow-nodes">
                    {nodes.map((node, index) => (
                        <React.Fragment key={node.id}>
                            <div className={`flow-node ${node.status || ''}`}>
                                <div className="node-icon">{node.icon}</div>
                                <div className="node-content">
                                    <div className="node-label">{node.label}</div>
                                    <div className="node-description">{node.description}</div>
                                </div>
                                <div className={`node-status-badge ${node.status || 'pending'}`}>
                                    {node.status || 'pending'}
                                </div>
                            </div>

                            {index < nodes.length - 1 && (
                                <div className="flow-arrow">
                                    <ArrowRight size={16} />
                                </div>
                            )}
                        </React.Fragment>
                    ))}
                </div>

                {partyInvestigations.length > 0 && (
                    <div className="party-investigations-branch">
                        <div className="branch-header">
                            <GitBranch size={14} />
                            <span>Parallel Party Investigations</span>
                        </div>
                        <div className="branch-nodes">
                            {partyInvestigations.map((inv) => (
                                <div key={inv.partyName} className={`party-node ${inv.status}`}>
                                    <div className="party-icon">
                                        <UserSearch size={14} />
                                    </div>
                                    <div className="party-info">
                                        <span className="party-name">{inv.partyName}</span>
                                        <span className="party-claims">
                                            {inv.claimsInvestigated} claims investigated
                                        </span>
                                    </div>
                                    <div className={`party-status ${inv.status}`}>
                                        {inv.status}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {arbiterResult && (
                    <div className="arbiter-summary">
                        <div className="summary-header">
                            <Scale size={16} />
                            <span>Final Determinations</span>
                        </div>
                        <div className="summary-stats">
                            <div className="stat">
                                <span className="stat-value">{arbiterResult.factsCount}</span>
                                <span className="stat-label">Facts</span>
                            </div>
                            <div className="stat">
                                <span className="stat-value">{arbiterResult.allegationsCount}</span>
                                <span className="stat-label">Allegations</span>
                            </div>
                            <div className="stat">
                                <span className="stat-value">{arbiterResult.agreementLevel}</span>
                                <span className="stat-label">Agreement</span>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default AdversarialFlowDiagram;
