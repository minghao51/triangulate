import React, { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { Evidence } from '../types/backend-models';
import { getEvidenceForCase } from '../services/api';
import { SourceRadar } from '../components/data-visualization/SourceRadar';
import Card, { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';
import Badge from '../components/design-system/Badge';

export const SourceAnalysis: React.FC = () => {
  const { id } = useParams<{ id: string }>();

  // Fetch case data
  const { data: evidence = [], isLoading, error } = useQuery({
    queryKey: ['evidence', id],
    queryFn: () => getEvidenceForCase(id || ''),
    enabled: !!id,
    refetchInterval: 15000, // 15s polling
  });

  // Calculate source statistics
  const sourceStats = useMemo(() => {
    const byType: Record<string, number> = {};
    const byPublisher: Record<string, number> = {};
    const byCredibility: Record<string, number> = {};
    const byRegion: Record<string, number> = {};

    evidence.forEach((ev) => {
      // By type
      byType[ev.sourceType] = (byType[ev.sourceType] || 0) + 1;

      // By publisher
      if (ev.publisher) {
        byPublisher[ev.publisher] = (byPublisher[ev.publisher] || 0) + 1;
      }

      // By credibility tier
      if (ev.credibilityTier) {
        byCredibility[ev.credibilityTier] = (byCredibility[ev.credibilityTier] || 0) + 1;
      }

      // Extract region from publisher (simplified)
      if (ev.publisher) {
        const region = ev.publisher.includes('BBC') || ev.publisher.includes('UK')
          ? 'UK'
          : ev.publisher.includes('CNN') || ev.publisher.includes('NYTimes')
          ? 'US'
          : 'Other';
        byRegion[region] = (byRegion[region] || 0) + 1;
      }
    });

    return { byType, byPublisher, byCredibility, byRegion };
  }, [evidence]);

  // Calculate baseline for comparison
  const baseline = useMemo(() => {
    // Simplified baseline - in production would come from aggregated data
    const sourceTypeDiversity = Math.min(100, (Object.keys(sourceStats.byType).length / 5) * 100);
    const publisherDiversity = Math.min(100, (Object.keys(sourceStats.byPublisher).length / 10) * 100);
    const avgCredibility = 60; // Baseline average
    const verificationRate = 70; // Baseline verification
    const reviewNeeded = 20; // Baseline review needed

    return { sourceTypeDiversity, publisherDiversity, avgCredibility, verificationRate, reviewNeeded };
  }, [sourceStats]);

  // Top sources
  const topSources = useMemo(() => {
    return Object.entries(sourceStats.byPublisher)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 10);
  }, [sourceStats]);

  // Bias analysis (simplified)
  const biasAnalysis = useMemo(() => {
    const left = evidence.filter((e) => e.publisher?.toLowerCase().includes('left') || e.publisher?.toLowerCase().includes('progressive')).length;
    const right = evidence.filter((e) => e.publisher?.toLowerCase().includes('right') || e.publisher?.toLowerCase().includes('conservative')).length;
    const center = evidence.filter((e) => e.publisher?.toLowerCase().includes('center') || e.publisher?.toLowerCase().includes('times')).length;

    return { left, right, center, other: evidence.length - left - right - center };
  }, [evidence]);

  // Duplication detection
  const duplicateSources = useMemo(() => {
    const urlMap = new Map<string, Evidence[]>();
    evidence.forEach((ev) => {
      if (ev.canonicalUrl) {
        const urls = urlMap.get(ev.canonicalUrl) || [];
        urls.push(ev);
        urlMap.set(ev.canonicalUrl, urls);
      }
    });

    return Array.from(urlMap.entries())
      .filter(([, evs]) => evs.length > 1)
      .map(([url, evs]) => ({ url, count: evs.length, sources: evs }));
  }, [evidence]);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#f0f2f5]">Source Analysis</h1>
          <p className="text-sm text-[#9aa1b3] mt-1">
            Comprehensive analysis of evidence sources and credibility
          </p>
        </div>
      </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card padding="sm">
          <CardBody className="space-y-1">
            <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Total Sources</div>
            <div className="text-2xl font-bold text-[#00d4ff]">{evidence.length}</div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody className="space-y-1">
            <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Source Types</div>
            <div className="text-2xl font-bold text-[#00ff9d]">{Object.keys(sourceStats.byType).length}</div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody className="space-y-1">
            <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Publishers</div>
            <div className="text-2xl font-bold text-[#a55eea]">{Object.keys(sourceStats.byPublisher).length}</div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody className="space-y-1">
            <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Duplicates</div>
            <div className="text-2xl font-bold text-[#ff4757]">{duplicateSources.length}</div>
          </CardBody>
        </Card>
      </div>

      {isLoading ? (
        <Card>
          <CardBody className="py-16">
            <div className="text-center text-[#9aa1b3]">Loading source analysis...</div>
          </CardBody>
        </Card>
      ) : error ? (
        <Card>
          <CardBody className="py-16">
            <div className="text-center text-[#ff4757]">Failed to load source data</div>
          </CardBody>
        </Card>
      ) : (
        <>
          {/* Source Diversity Radar */}
          <SourceRadar
            evidence={evidence}
            baseline={baseline}
            size={500}
          />

          <div className="grid grid-cols-2 gap-6">
            {/* Source Distribution by Type */}
            <Card>
              <CardHeader>
                <CardTitle>Source Type Distribution</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="space-y-3">
                  {Object.entries(sourceStats.byType)
                    .sort(([, a], [, b]) => b - a)
                    .map(([type, count]) => {
                      const percentage = (count / evidence.length) * 100;
                      return (
                        <div key={type}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm text-[#f0f2f5] capitalize">{type}</span>
                            <span className="text-sm text-[#00d4ff] font-mono">{count} ({percentage.toFixed(1)}%)</span>
                          </div>
                          <div className="w-full h-2 bg-[#1a1a1a] rounded-sm overflow-hidden">
                            <div
                              className="h-full bg-[#00d4ff] transition-all duration-300"
                              style={{ width: `${percentage}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                </div>
              </CardBody>
            </Card>

            {/* Top Publishers */}
            <Card>
              <CardHeader>
                <CardTitle>Top Publishers</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="space-y-2">
                  {topSources.map(([publisher, count], index) => (
                    <div
                      key={publisher}
                      className="flex items-center justify-between p-2 bg-[#0a0a0a] border border-[#1a1a1a] rounded-sm hover:border-[#2d3340] transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <div className="text-xs text-[#6c7385] font-mono w-6">#{index + 1}</div>
                        <div className="text-sm text-[#f0f2f5]">{publisher}</div>
                      </div>
                      <Badge variant="neutral" size="sm">{count}</Badge>
                    </div>
                  ))}
                  {topSources.length === 0 && (
                    <div className="text-center text-[#6c7385] py-8">No publisher data available</div>
                  )}
                </div>
              </CardBody>
            </Card>

            {/* Credibility Tier Breakdown */}
            <Card>
              <CardHeader>
                <CardTitle>Credibility Tier Analysis</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="space-y-3">
                  {Object.entries(sourceStats.byCredibility)
                    .sort(([, a], [, b]) => b - a)
                    .map(([tier, count]) => {
                      const percentage = (count / evidence.length) * 100;
                      const tierColors: Record<string, string> = {
                        'high': 'bg-[#00ff9d]',
                        'medium': 'bg-[#ffb800]',
                        'low': 'bg-[#ff4757]',
                        'unknown': 'bg-[#6c7385]',
                      };
                      return (
                        <div key={tier}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm text-[#f0f2f5] capitalize">{tier}</span>
                            <span className="text-sm text-[#00d4ff] font-mono">{count} ({percentage.toFixed(1)}%)</span>
                          </div>
                          <div className="w-full h-2 bg-[#1a1a1a] rounded-sm overflow-hidden">
                            <div
                              className={`h-full ${tierColors[tier] || 'bg-[#6c7385]'} transition-all duration-300`}
                              style={{ width: `${percentage}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  {Object.keys(sourceStats.byCredibility).length === 0 && (
                    <div className="text-center text-[#6c7385] py-8">No credibility data available</div>
                  )}
                </div>
              </CardBody>
            </Card>

            {/* Bias Analysis */}
            <Card>
              <CardHeader>
                <CardTitle>Source Bias Distribution</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="space-y-3">
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-[#f0f2f5]">Left-leaning</span>
                      <span className="text-sm text-[#00d4ff] font-mono">{biasAnalysis.left}</span>
                    </div>
                    <div className="w-full h-2 bg-[#1a1a1a] rounded-sm overflow-hidden">
                      <div
                        className="h-full bg-[#00d4ff] transition-all duration-300"
                        style={{ width: `${(biasAnalysis.left / evidence.length) * 100}%` }}
                      />
                    </div>
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-[#f0f2f5]">Center</span>
                      <span className="text-sm text-[#00d4ff] font-mono">{biasAnalysis.center}</span>
                    </div>
                    <div className="w-full h-2 bg-[#1a1a1a] rounded-sm overflow-hidden">
                      <div
                        className="h-full bg-[#00ff9d] transition-all duration-300"
                        style={{ width: `${(biasAnalysis.center / evidence.length) * 100}%` }}
                      />
                    </div>
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-[#f0f2f5]">Right-leaning</span>
                      <span className="text-sm text-[#00d4ff] font-mono">{biasAnalysis.right}</span>
                    </div>
                    <div className="w-full h-2 bg-[#1a1a1a] rounded-sm overflow-hidden">
                      <div
                        className="h-full bg-[#ff4757] transition-all duration-300"
                        style={{ width: `${(biasAnalysis.right / evidence.length) * 100}%` }}
                      />
                    </div>
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-[#f0f2f5]">Other/Unknown</span>
                      <span className="text-sm text-[#00d4ff] font-mono">{biasAnalysis.other}</span>
                    </div>
                    <div className="w-full h-2 bg-[#1a1a1a] rounded-sm overflow-hidden">
                      <div
                        className="h-full bg-[#6c7385] transition-all duration-300"
                        style={{ width: `${(biasAnalysis.other / evidence.length) * 100}%` }}
                      />
                    </div>
                  </div>
                </div>
              </CardBody>
            </Card>

            {/* Duplicate Sources */}
            <Card className="col-span-2">
              <CardHeader>
                <CardTitle>Duplicate Source Detection</CardTitle>
              </CardHeader>
              <CardBody>
                {duplicateSources.length === 0 ? (
                  <div className="text-center text-[#00ff9d] py-8">
                    <div className="text-4xl mb-2">✓</div>
                    <div className="text-sm">No duplicate sources detected</div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {duplicateSources.map(({ url, count }) => (
                      <div
                        key={url}
                        className="flex items-center justify-between p-3 bg-[#0a0a0a] border border-[#ff4757] rounded-sm"
                      >
                        <div className="flex-1">
                          <div className="text-sm text-[#f0f2f5] truncate">{url}</div>
                          <div className="text-xs text-[#9aa1b3] mt-1">
                            Found in {count} sources
                          </div>
                        </div>
                        <Badge variant="danger" size="sm">{count}x</Badge>
                      </div>
                    ))}
                  </div>
                )}
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </div>
  );
};

export default SourceAnalysis;
