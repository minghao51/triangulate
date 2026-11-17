import React from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getClaimsForCase, getPartiesForCase, getCaseDetail } from '../services/api';
import { AdversarialFlowDiagram } from '../components/discussion/AdversarialFlowDiagram';
import { ClaimDetailPanel } from '../components/claims/ClaimDetailPanel';
import { PartyInvestigationPanel } from '../components/parties/PartyInvestigationPanel';
import Card, { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';
import type { Claim, Party } from '../types/backend-models';

export const CaseDiscussionView: React.FC = () => {
    const { id } = useParams<{ id: string }>();

    const { data: caseDetail } = useQuery({
        queryKey: ['case', id],
        queryFn: () => getCaseDetail(id || ''),
        enabled: !!id,
    });

    const { data: claims = [], isLoading: claimsLoading } = useQuery({
        queryKey: ['claims', id],
        queryFn: () => getClaimsForCase(id || ''),
        enabled: !!id,
    });

    const { data: parties = [], isLoading: partiesLoading } = useQuery({
        queryKey: ['parties', id],
        queryFn: () => getPartiesForCase(id || ''),
        enabled: !!id,
    });

    const isLoading = claimsLoading || partiesLoading;

    const partyInvestigations = parties.map((party: Party) => ({
        partyName: party.name,
        status: 'completed' as const,
        claimsInvestigated: party.claimsSupported + party.claimsContested,
    }));

    const claimsWithArbiterData = claims.filter(
        (claim: Claim) => claim.arbiterReasoning || Object.keys(claim.partyPositions || {}).length > 0
    );

    const partiesWithInvestigation = parties.filter(
        (party: Party) => party.investigationData !== null
    );

    return (
        <div className="case-discussion-view">
            <div className="discussion-header">
                <h2>Adversarial Discussion View</h2>
                <p className="subtitle">
                    Explore how different parties investigated claims and how the arbiter made determinations
                </p>
            </div>

            {isLoading ? (
                <div className="loading-state">Loading discussion data...</div>
            ) : (
                <>
                    <Card className="flow-diagram-card">
                        <CardHeader>
                            <CardTitle>Workflow Overview</CardTitle>
                        </CardHeader>
                        <CardBody>
                            <AdversarialFlowDiagram
                                claimsCount={claims.length}
                                partiesCount={parties.length}
                                partyInvestigations={partyInvestigations}
                                arbiterResult={
                                    caseDetail?.tabs?.runHistory?.length
                                        ? {
                                              factsCount: claims.filter((c: Claim) => c.type === 'fact').length,
                                              allegationsCount: claims.filter((c: Claim) => c.type === 'allegation').length,
                                              agreementLevel: 'MEDIUM',
                                          }
                                        : undefined
                                }
                            />
                        </CardBody>
                    </Card>

                    <div className="discussion-sections">
                        <Card className="arbiter-decisions-card">
                            <CardHeader>
                                <CardTitle>Arbiter Decisions</CardTitle>
                            </CardHeader>
                            <CardBody>
                                <p className="section-description">
                                    Claims with arbiter reasoning and party consensus analysis
                                </p>
                                <div className="claims-list">
                                    {claimsWithArbiterData.length === 0 ? (
                                        <div className="empty-state">
                                            No arbiter analysis available yet
                                        </div>
                                    ) : (
                                        claimsWithArbiterData.map((claim: Claim) => (
                                            <div key={claim.id} className="claim-item glass-panel">
                                                <div className="claim-header">
                                                    <span className={`badge ${claim.type === 'fact' ? 'badge-info' : 'badge-warning'}`}>
                                                        {claim.type}
                                                    </span>
                                                    <span className={`badge ${claim.verificationStatus === 'confirmed' ? 'badge-success' : 'badge-danger'}`}>
                                                        {claim.verificationStatus}
                                                    </span>
                                                    <span className="claim-text-preview">{claim.text.substring(0, 100)}...</span>
                                                </div>
                                                <ClaimDetailPanel claim={claim} />
                                            </div>
                                        ))
                                    )}
                                </div>
                            </CardBody>
                        </Card>

                        <Card className="party-investigations-card">
                            <CardHeader>
                                <CardTitle>Party Investigations</CardTitle>
                            </CardHeader>
                            <CardBody>
                                <p className="section-description">
                                    Each party's investigation results and their stance on claims
                                </p>
                                <div className="parties-list">
                                    {partiesWithInvestigation.length === 0 ? (
                                        <div className="empty-state">
                                            No party investigation data available yet
                                        </div>
                                    ) : (
                                        partiesWithInvestigation.map((party: Party) => (
                                            <div key={party.id} className="party-item glass-panel">
                                                <div className="party-header">
                                                    <span className="party-name">{party.name}</span>
                                                    <span className={`stance-badge stance-${party.overallStance}`}>
                                                        {party.overallStance}
                                                    </span>
                                                    <span className="claims-summary">
                                                        {party.claimsSupported} supported, {party.claimsContested} contested
                                                    </span>
                                                </div>
                                                <PartyInvestigationPanel party={party} />
                                            </div>
                                        ))
                                    )}
                                </div>
                            </CardBody>
                        </Card>
                    </div>
                </>
            )}
        </div>
    );
};

export default CaseDiscussionView;
