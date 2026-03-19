import React, { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { Claim } from '../types/backend-models';
import { getClaimsForCase, getPartiesForCase, getTimelineForCase } from '../services/api';
import { TimelineChart } from '../components/data-visualization/TimelineChart';
import Card, { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';
import type { BadgeProps } from '../components/design-system/Badge';
import Badge from '../components/design-system/Badge';

export const NarrativeLandscape: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [selectedCluster, setSelectedCluster] = useState<string | null>(null);

  // Fetch case data
  const { data: claims = [], isLoading: claimsLoading } = useQuery({
    queryKey: ['claims', id],
    queryFn: () => getClaimsForCase(id || ''),
    enabled: !!id,
    refetchInterval: 15000, // 15s polling
  });

  const { data: parties = [], isLoading: partiesLoading } = useQuery({
    queryKey: ['parties', id],
    queryFn: () => getPartiesForCase(id || ''),
    enabled: !!id,
    refetchInterval: 15000,
  });

  const { data: timeline = [], isLoading: timelineLoading } = useQuery({
    queryKey: ['timeline', id],
    queryFn: () => getTimelineForCase(id || ''),
    enabled: !!id,
    refetchInterval: 15000,
  });

  const isLoading = claimsLoading || partiesLoading || timelineLoading;
  const error = null; // Simplified error handling

  // Group claims into narrative clusters based on similarity
  const narrativeClusters = useMemo(() => {
    // Simplified clustering - in production would use more sophisticated algorithm
    const clusters: Record<string, { claims: Claim[]; stance: string; sentiment: number }> = {
      'Origin Narrative': { claims: [], stance: 'mixed', sentiment: 0 },
      'Response Narrative': { claims: [], stance: 'mixed', sentiment: 0 },
      'Evidence Narrative': { claims: [], stance: 'mixed', sentiment: 0 },
      'Impact Narrative': { claims: [], stance: 'mixed', sentiment: 0 },
    };

    claims.forEach((claim) => {
      const text = claim.text.toLowerCase();
      if (text.includes('origin') || text.includes('began') || text.includes('started')) {
        clusters['Origin Narrative'].claims.push(claim);
      } else if (text.includes('response') || text.includes('reacted') || text.includes('said')) {
        clusters['Response Narrative'].claims.push(claim);
      } else if (text.includes('evidence') || text.includes('show') || text.includes('prove')) {
        clusters['Evidence Narrative'].claims.push(claim);
      } else if (text.includes('impact') || text.includes('effect') || text.includes('result')) {
        clusters['Impact Narrative'].claims.push(claim);
      } else {
        // Add to first cluster with space
        const cluster = Object.values(clusters).find((c) => c.claims.length < claims.length / 4);
        if (cluster) cluster.claims.push(claim);
      }
    });

    // Calculate sentiment for each cluster
    Object.entries(clusters).forEach(([, cluster]) => {
      const verifiedCount = cluster.claims.filter((c) => c.verificationStatus === 'confirmed' || c.verificationStatus === 'probable').length;
      cluster.sentiment = cluster.claims.length > 0 ? verifiedCount / cluster.claims.length : 0;
      cluster.claims.forEach((claim) => {
        if (claim.opposeCount > claim.supportCount) cluster.stance = 'against';
        else if (claim.supportCount > claim.opposeCount) cluster.stance = 'for';
      });
    });

    return clusters;
  }, [claims]);

  // Party position matrix
  const partyPositions = useMemo(() => {
    return parties.map((party) => {
      const partyClaims = claims.filter((c) => c.text.toLowerCase().includes(party.name.toLowerCase()));
      const supportCount = partyClaims.reduce((sum, c) => sum + c.supportCount, 0);
      const opposeCount = partyClaims.reduce((sum, c) => sum + c.opposeCount, 0);
      const stance = supportCount > opposeCount ? 'for' : opposeCount > supportCount ? 'against' : 'neutral';

      return {
        party,
        claimCount: partyClaims.length,
        supportCount,
        opposeCount,
        stance,
      };
    });
  }, [claims, parties]);

  const getStanceBadge = (stance: string): BadgeProps['variant'] => {
    switch (stance) {
      case 'for': return 'success';
      case 'against': return 'danger';
      default: return 'neutral';
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#f0f2f5]">Narrative Landscape</h1>
          <p className="text-sm text-[#9aa1b3] mt-1">
            Analysis of competing narratives and party positions
          </p>
        </div>
      </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card padding="sm">
          <CardBody className="space-y-1">
            <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Narratives</div>
            <div className="text-2xl font-bold text-[#00d4ff]">{Object.keys(narrativeClusters).length}</div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody className="space-y-1">
            <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Total Claims</div>
            <div className="text-2xl font-bold text-[#00ff9d]">{claims.length}</div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody className="space-y-1">
            <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Parties</div>
            <div className="text-2xl font-bold text-[#a55eea]">{parties.length}</div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody className="space-y-1">
            <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Timeline Events</div>
            <div className="text-2xl font-bold text-[#ffb800]">{timeline.length}</div>
          </CardBody>
        </Card>
      </div>

      {isLoading ? (
        <Card>
          <CardBody className="py-16">
            <div className="text-center text-[#9aa1b3]">Loading narrative analysis...</div>
          </CardBody>
        </Card>
      ) : error ? (
        <Card>
          <CardBody className="py-16">
            <div className="text-center text-[#ff4757]">Failed to load narrative data</div>
          </CardBody>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-6">
            {/* Narrative Clusters */}
            <Card>
              <CardHeader>
                <CardTitle>Narrative Clusters</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="space-y-4">
                  {Object.entries(narrativeClusters).map(([name, cluster]) => (
                    <div
                      key={name}
                      className={`p-4 border rounded-sm cursor-pointer transition-all ${
                        selectedCluster === name
                          ? 'border-[#00d4ff] bg-[#00d4ff10]'
                          : 'border-[#2d3340] hover:border-[#3f4758]'
                      }`}
                      onClick={() => setSelectedCluster(name)}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-base font-semibold text-[#f0f2f5]">{name}</h3>
                        <Badge variant={getStanceBadge(cluster.stance)} size="sm">
                          {cluster.stance}
                        </Badge>
                      </div>
                      <div className="grid grid-cols-2 gap-4 mb-3">
                        <div>
                          <div className="text-xs text-[#9aa1b3] mb-1">Claims</div>
                          <div className="text-lg font-bold text-[#00d4ff]">{cluster.claims.length}</div>
                        </div>
                        <div>
                          <div className="text-xs text-[#9aa1b3] mb-1">Sentiment</div>
                          <div className="text-lg font-bold text-[#00ff9d]">
                            {(cluster.sentiment * 100).toFixed(0)}%
                          </div>
                        </div>
                      </div>
                      {selectedCluster === name && cluster.claims.length > 0 && (
                        <div className="space-y-2 pt-3 border-t border-[#2d3340]">
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Key Claims</div>
                          {cluster.claims.slice(0, 3).map((claim) => (
                            <div key={claim.id} className="text-sm text-[#f0f2f5] truncate">
                              {claim.text}
                            </div>
                          ))}
                          {cluster.claims.length > 3 && (
                            <div className="text-xs text-[#6c7385]">
                              +{cluster.claims.length - 3} more claims
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </CardBody>
            </Card>

            {/* Party Position Matrix */}
            <Card>
              <CardHeader>
                <CardTitle>Party Position Matrix</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="space-y-3">
                  {partyPositions.map(({ party, claimCount, supportCount, opposeCount, stance }) => (
                    <div
                      key={party.id}
                      className="p-4 bg-[#0a0a0a] border border-[#1a1a1a] rounded-sm hover:border-[#2d3340] transition-colors"
                    >
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <div className="text-base font-semibold text-[#f0f2f5]">{party.name}</div>
                          <div className="text-xs text-[#9aa1b3] mt-1">{party.description}</div>
                        </div>
                        <Badge variant={getStanceBadge(stance)} size="sm">
                          {stance}
                        </Badge>
                      </div>
                      <div className="grid grid-cols-3 gap-4">
                        <div>
                          <div className="text-xs text-[#9aa1b3] mb-1">Claims</div>
                          <div className="text-sm font-mono text-[#00d4ff]">{claimCount}</div>
                        </div>
                        <div>
                          <div className="text-xs text-[#9aa1b3] mb-1">Support</div>
                          <div className="text-sm font-mono text-[#00ff9d]">{supportCount}</div>
                        </div>
                        <div>
                          <div className="text-xs text-[#9aa1b3] mb-1">Oppose</div>
                          <div className="text-sm font-mono text-[#ff4757]">{opposeCount}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                  {partyPositions.length === 0 && (
                    <div className="text-center text-[#6c7385] py-8">No party position data available</div>
                  )}
                </div>
              </CardBody>
            </Card>

            {/* Timeline Narrative Flow */}
            <Card className="col-span-2">
              <CardHeader>
                <CardTitle>Timeline Narrative Flow</CardTitle>
              </CardHeader>
              <CardBody>
                <TimelineChart
                  events={timeline}
                  onEventClick={(eventId) => console.log('Event clicked:', eventId)}
                  height="400px"
                />
              </CardBody>
            </Card>

            {/* Sentiment Analysis */}
            <Card>
              <CardHeader>
                <CardTitle>Sentiment Analysis</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="space-y-4">
                  <div>
                    <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-2">Overall Sentiment</div>
                    <div className="flex items-center gap-4">
                      <div className="flex-1">
                        <div className="w-full h-4 bg-[#1a1a1a] rounded-sm overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-[#ff4757] via-[#ffb800] to-[#00ff9d] transition-all duration-300"
                            style={{
                              width: '100%',
                            }}
                          />
                        </div>
                      </div>
                      <div className="text-sm font-mono text-[#f0f2f5]">
                        {claims.length > 0
                          ? (claims.filter((c) => c.verificationStatus === 'confirmed' || c.verificationStatus === 'probable').length / claims.length * 100).toFixed(0)
                          : 0}%
                      </div>
                    </div>
                    <div className="flex justify-between mt-1 text-xs text-[#6c7385]">
                      <span>Negative</span>
                      <span>Neutral</span>
                      <span>Positive</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4 pt-4 border-t border-[#2d3340]">
                    <div>
                      <div className="text-xs text-[#9aa1b3] mb-1">Confirmed Claims</div>
                      <div className="text-2xl font-bold text-[#00ff9d]">
                        {claims.filter((c) => c.verificationStatus === 'confirmed').length}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-[#9aa1b3] mb-1">Contested Claims</div>
                      <div className="text-2xl font-bold text-[#ffb800]">
                        {claims.filter((c) => c.verificationStatus === 'contested' || c.verificationStatus === 'debunked').length}
                      </div>
                    </div>
                  </div>
                </div>
              </CardBody>
            </Card>

            {/* Narrative Statistics */}
            <Card>
              <CardHeader>
                <CardTitle>Narrative Statistics</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <div className="text-xs text-[#9aa1b3] mb-1">Avg Claims per Narrative</div>
                      <div className="text-lg font-mono text-[#00d4ff]">
                        {(claims.length / Object.keys(narrativeClusters).length).toFixed(1)}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-[#9aa1b3] mb-1">Most Common Stance</div>
                      <div className="text-lg font-mono text-[#f0f2f5] capitalize">
                        {Object.values(narrativeClusters)
                          .sort((a, b) => {
                            const aCount = a.claims.filter((c) => c.supportCount > c.opposeCount).length;
                            const bCount = b.claims.filter((c) => c.supportCount > c.opposeCount).length;
                            return bCount - aCount;
                          })[0]?.stance || 'Unknown'}
                      </div>
                    </div>
                  </div>

                  <div className="pt-4 border-t border-[#2d3340]">
                    <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-2">Narrative Balance</div>
                    <div className="space-y-2">
                      {Object.entries(narrativeClusters)
                        .sort(([, a], [, b]) => b.claims.length - a.claims.length)
                        .slice(0, 3)
                        .map(([name, cluster]) => (
                          <div key={name} className="flex items-center gap-3">
                            <div className="text-sm text-[#f0f2f5] flex-1">{name}</div>
                            <div className="w-32 h-2 bg-[#1a1a1a] rounded-sm overflow-hidden">
                              <div
                                className="h-full bg-[#00d4ff] transition-all duration-300"
                                style={{
                                  width: `${(cluster.claims.length / claims.length) * 100}%`,
                                }}
                              />
                            </div>
                            <div className="text-sm font-mono text-[#00d4ff] w-12 text-right">
                              {((cluster.claims.length / claims.length) * 100).toFixed(0)}%
                            </div>
                          </div>
                        ))}
                    </div>
                  </div>
                </div>
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </div>
  );
};

export default NarrativeLandscape;
