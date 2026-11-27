import React, { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getClaimsOverviewForCase, getPartiesForCase, getTimelineForCase } from '../services/api';
import { buildClaimEvidenceUrl } from '../services/deep-links';
import { TimelineChart } from '../components/data-visualization/TimelineChart';
import Card, { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';
import Badge from '../components/design-system/Badge';
import Button from '../components/design-system/Button';
import ReaderState from '../components/design-system/ReaderState';
import './NarrativeLandscape.css';

/**
 * Narrative landscape.
 *
 * Persisted narrative clusters (the same records the Claims tab uses) and recorded
 * claim/party/timeline data only. There is no sentiment or keyword stance
 * inference, and no fallback clusters are invented when none are persisted.
 */

/**
 * A stanced record is never a truth verdict: the badge stays neutral and the
 * recorded basis (`isModelInferred`) is spelled out in text. Absent provenance
 * stays "Origin not recorded" — it is never inferred as human review.
 */
interface StanceBasis {
  kind: 'model-derived' | 'recorded' | 'unknown';
  label: string;
  origin: string;
}

const describeStanceBasis = (party: { isModelInferred?: boolean }): StanceBasis => {
  if (typeof party.isModelInferred !== 'boolean') {
    return { kind: 'unknown', label: 'Stance basis not recorded', origin: 'Origin not recorded' };
  }
  return party.isModelInferred
    ? { kind: 'model-derived', label: 'Model-derived stance', origin: 'Origin: model-derived record' }
    : { kind: 'recorded', label: 'Recorded stance', origin: 'Origin: recorded party record' };
};

interface ViewProps {
  caseId: string;
}

const NarrativeLandscapeView: React.FC<ViewProps> = ({ caseId }) => {
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null);

  // The overview endpoint is what the Claims tab already uses; it returns the
  // persisted narratives alongside the claims that reference them.
  const overviewQuery = useQuery({
    queryKey: ['claims-overview', caseId],
    queryFn: () => getClaimsOverviewForCase(caseId),
    enabled: !!caseId,
    refetchInterval: 15000,
  });

  const partiesQuery = useQuery({
    queryKey: ['parties', caseId],
    queryFn: () => getPartiesForCase(caseId),
    enabled: !!caseId,
    refetchInterval: 15000,
  });

  const timelineQuery = useQuery({
    queryKey: ['timeline', caseId],
    queryFn: () => getTimelineForCase(caseId),
    enabled: !!caseId,
    refetchInterval: 15000,
  });

  const isLoading = overviewQuery.isLoading || partiesQuery.isLoading || timelineQuery.isLoading;
  const error = overviewQuery.error ?? partiesQuery.error ?? timelineQuery.error;
  const claims = overviewQuery.data?.claims ?? [];
  const narratives = overviewQuery.data?.narratives ?? [];
  const parties = partiesQuery.data ?? [];
  const timeline = timelineQuery.data ?? [];

  const retryAll = () => {
    void overviewQuery.refetch();
    void partiesQuery.refetch();
    void timelineQuery.refetch();
  };

  const selectedCluster = narratives.find((cluster) => cluster.id === selectedClusterId) ?? null;
  const selectedClusterClaims = selectedCluster
    ? claims.filter((claim) => claim.narrativeClusterId === selectedCluster.clusterId)
    : [];

  return (
    <div className="narrative-landscape">
      <div className="narrative-landscape-header">
        <div>
          <h1>Narrative Landscape</h1>
          <p className="narrative-landscape-subtitle">
            Persisted narrative clusters, recorded party data and the event timeline for this case.
          </p>
        </div>
        <Button variant="secondary" onClick={retryAll}>Refresh</Button>
      </div>

      {isLoading ? (
        <Card>
          <CardBody>
            <div className="narrative-landscape-state" role="status">Loading narrative data…</div>
          </CardBody>
        </Card>
      ) : error ? (
        <Card>
          <CardBody>
            <div className="narrative-landscape-state narrative-landscape-state--error" role="alert">
              <p>
                Failed to load narrative data
                {error instanceof Error && error.message ? `: ${error.message}` : '.'}
              </p>
              <Button variant="secondary" onClick={retryAll}>Retry</Button>
            </div>
          </CardBody>
        </Card>
      ) : (
        <>
          <div className="narrative-landscape-stats">
            <Card padding="sm">
              <CardBody>
                <div className="narrative-landscape-stat-label">Persisted Narratives</div>
                <div className="narrative-landscape-stat-value">{narratives.length}</div>
              </CardBody>
            </Card>
            <Card padding="sm">
              <CardBody>
                <div className="narrative-landscape-stat-label">Recorded Claims</div>
                <div className="narrative-landscape-stat-value">{claims.length}</div>
              </CardBody>
            </Card>
            <Card padding="sm">
              <CardBody>
                <div className="narrative-landscape-stat-label">Parties</div>
                <div className="narrative-landscape-stat-value">{parties.length}</div>
              </CardBody>
            </Card>
            <Card padding="sm">
              <CardBody>
                <div className="narrative-landscape-stat-label">Timeline Events</div>
                <div className="narrative-landscape-stat-value">{timeline.length}</div>
              </CardBody>
            </Card>
          </div>

          <div className="narrative-landscape-grid">
            <Card>
              <CardHeader>
                <CardTitle>Narrative Clusters</CardTitle>
              </CardHeader>
              <CardBody>
                {narratives.length === 0 ? (
                  <ReaderState
                    state="empty"
                    className="narratives-empty"
                    title="No narrative clusters recorded"
                    description="No narrative clusters have been persisted for this case. Nothing is grouped or inferred here."
                  />
                ) : (
                  <ul className="narrative-cluster-list">
                    {narratives.map((cluster) => {
                      const isSelected = cluster.id === selectedClusterId;
                      return (
                        <li key={cluster.id}>
                          <button
                            type="button"
                            className={`narrative-cluster ${isSelected ? 'narrative-cluster--selected' : ''}`}
                            aria-pressed={isSelected}
                            aria-expanded={isSelected}
                            onClick={() => setSelectedClusterId(isSelected ? null : cluster.id)}
                          >
                            <span className="narrative-cluster-head">
                              <span className="narrative-cluster-summary">{cluster.stanceSummary}</span>
                              <Badge variant="neutral" size="sm">{cluster.claimCount} claims</Badge>
                            </span>
                            <span className="narrative-cluster-meta">
                              <span>{cluster.sourceCount} linked sources</span>
                              <span className="narrative-cluster-id">cluster {cluster.clusterId}</span>
                            </span>
                          </button>
                          {isSelected && (
                            <div className="narrative-cluster-claims">
                              {selectedClusterClaims.length === 0 ? (
                                <p className="narrative-landscape-note">
                                  No claim currently references this cluster.
                                </p>
                              ) : (
                                selectedClusterClaims.slice(0, 3).map((claim) => (
                                  <p key={claim.id} className="narrative-cluster-claim">
                                    <Link
                                      className="narrative-cluster-claim-link"
                                      to={buildClaimEvidenceUrl(caseId, claim.id)}
                                    >
                                      {claim.text}
                                    </Link>
                                  </p>
                                ))
                              )}
                              {selectedClusterClaims.length > 3 && (
                                <p className="narrative-landscape-note">
                                  +{selectedClusterClaims.length - 3} more claims
                                </p>
                              )}
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Parties</CardTitle>
              </CardHeader>
              <CardBody>
                {parties.length === 0 ? (
                  <div className="narrative-landscape-state" role="status">
                    No parties have been recorded for this case.
                  </div>
                ) : (
                  <ul className="narrative-party-list">
                    {parties.map((party) => {
                      const basis = describeStanceBasis(party);
                      return (
                      <li key={party.id} className="narrative-party">
                        <div className="narrative-party-head">
                          <div>
                            <div className="narrative-party-name">{party.name}</div>
                            {party.description && (
                              <div className="narrative-party-description">{party.description}</div>
                            )}
                          </div>
                          <Badge variant="neutral" size="sm">
                            {party.overallStance ?? 'not recorded'}
                          </Badge>
                        </div>
                        <div className="narrative-party-meta">
                          <span>{party.associatedClaimsCount} associated claims</span>
                          <span className={`narrative-party-basis narrative-party-basis--${basis.kind}`}>
                            {basis.label}
                          </span>
                          <span className="narrative-party-origin">{basis.origin}</span>
                        </div>
                      </li>
                      );
                    })}
                  </ul>
                )}
              </CardBody>
            </Card>

            <Card className="narrative-landscape-wide">
              <CardHeader>
                <CardTitle>Timeline Narrative Flow</CardTitle>
              </CardHeader>
              <CardBody>
                {timeline.length === 0 ? (
                  <div className="narrative-landscape-state" role="status">
                    No timeline events have been recorded for this case.
                  </div>
                ) : (
                  <TimelineChart events={timeline} height="400px" />
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Sentiment</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="narrative-landscape-state narrative-landscape-state--unavailable" role="status">
                  <Badge variant="neutral" size="sm">Not provided</Badge>
                  <p>
                    This read API provides no sentiment field for claims or narratives.
                    Verification status is a separate recorded field and is not converted into
                    sentiment.
                  </p>
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Recorded Verification Counts</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="narrative-verification-grid">
                  <div>
                    <div className="narrative-landscape-stat-label">Confirmed</div>
                    <div className="narrative-verification-value">
                      {claims.filter((claim) => claim.verificationStatus === 'confirmed').length}
                    </div>
                  </div>
                  <div>
                    <div className="narrative-landscape-stat-label">Probable</div>
                    <div className="narrative-verification-value">
                      {claims.filter((claim) => claim.verificationStatus === 'probable').length}
                    </div>
                  </div>
                  <div>
                    <div className="narrative-landscape-stat-label">Contested</div>
                    <div className="narrative-verification-value">
                      {claims.filter((claim) => claim.verificationStatus === 'contested').length}
                    </div>
                  </div>
                  <div>
                    <div className="narrative-landscape-stat-label">Unassessed</div>
                    <div className="narrative-verification-value">
                      {claims.filter((claim) => claim.verificationStatus === 'unknown').length}
                    </div>
                  </div>
                </div>
                <p className="narrative-landscape-note">
                  Counts of recorded verification statuses, not sentiment or support scores.
                </p>
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </div>
  );
};

export const NarrativeLandscape: React.FC = () => {
  const { id } = useParams<{ id: string }>();

  // A missing case ID must not mount the view: disabled queries would report
  // empty data as if the case were genuinely empty.
  if (!id) {
    return (
      <div className="narrative-landscape">
        <div className="narrative-landscape-header">
          <div>
            <h1>Narrative Landscape</h1>
          </div>
        </div>
        <Card>
          <CardBody>
            <div className="narrative-landscape-state narrative-landscape-state--error" role="alert">
              No case ID in the route. Open <code>/cases/&lt;case-id&gt;/narratives</code> to view a
              case's narratives.
            </div>
          </CardBody>
        </Card>
      </div>
    );
  }

  // Remount per case so a cluster selection can never survive a route change.
  return <NarrativeLandscapeView key={id} caseId={id} />;
};

export default NarrativeLandscape;
