import React, { useRef, useEffect, useState } from 'react';
import * as d3 from 'd3';
import type { Evidence } from '../../types/backend-models';
import Card, { CardHeader, CardTitle, CardBody } from '../design-system/Card';

export interface SourceRadarProps {
  evidence: Evidence[];
  baseline?: { [key: string]: number }; // Baseline for comparison
  onSliceClick?: (axis: string) => void;
  size?: number;
  className?: string;
}

interface RadarAxis {
  name: string;
  value: number;
  baseline?: number;
}

export const SourceRadar: React.FC<SourceRadarProps> = ({
  evidence,
  baseline = {},
  onSliceClick,
  size = 400,
  className = '',
}) => {
  const svgRef = useRef<SVGSVGElement>(null);
  const [selectedAxis, setSelectedAxis] = useState<string | null>(null);
  const [comparisonMode, setComparisonMode] = useState(false);

  // Calculate metrics for radar chart
  const metrics = React.useMemo(() => {
    const sourceTypeCounts: { [key: string]: number } = {};
    const publisherCounts: { [key: string]: number } = {};
    const credibilityTierCounts: { [key: string]: number } = {};

    evidence.forEach((ev) => {
      // Count by source type
      sourceTypeCounts[ev.sourceType] = (sourceTypeCounts[ev.sourceType] || 0) + 1;

      // Count by publisher
      if (ev.publisher) {
        publisherCounts[ev.publisher] = (publisherCounts[ev.publisher] || 0) + 1;
      }

      // Count by credibility tier
      if (ev.credibilityTier) {
        credibilityTierCounts[ev.credibilityTier] = (credibilityTierCounts[ev.credibilityTier] || 0) + 1;
      }
    });

    // Calculate diversity scores (normalized 0-100)
    const sourceTypeDiversity =
      Object.keys(sourceTypeCounts).length > 0
        ? Math.min(100, (Object.keys(sourceTypeCounts).length / 5) * 100)
        : 0;

    const publisherDiversity =
      Object.keys(publisherCounts).length > 0
        ? Math.min(100, (Object.keys(publisherCounts).length / 10) * 100)
        : 0;

    const avgCredibility =
      Object.values(credibilityTierCounts).length > 0
        ? (Object.values(credibilityTierCounts).reduce((a, b) => a + b, 0) /
            Object.values(credibilityTierCounts).length) *
          20
        : 0;

    const verifiedCount = evidence.filter((e) => e.verificationStatus === 'confirmed' || e.verificationStatus === 'probable').length;
    const verificationScore = evidence.length > 0 ? (verifiedCount / evidence.length) * 100 : 0;

    const requiresReviewCount = evidence.filter((e) => e.requiresHumanReview).length;
    const reviewNeededScore = evidence.length > 0 ? (requiresReviewCount / evidence.length) * 100 : 0;

    return {
      axes: [
        { name: 'Source Type Diversity', value: sourceTypeDiversity, baseline: baseline.sourceTypeDiversity },
        { name: 'Publisher Diversity', value: publisherDiversity, baseline: baseline.publisherDiversity },
        { name: 'Avg Credibility', value: avgCredibility, baseline: baseline.avgCredibility },
        { name: 'Verification Rate', value: verificationScore, baseline: baseline.verificationRate },
        { name: 'Review Needed', value: reviewNeededScore, baseline: baseline.reviewNeeded },
      ] as RadarAxis[],
      breakdowns: {
        sourceTypes: sourceTypeCounts,
        publishers: Object.fromEntries(
          Object.entries(publisherCounts)
            .sort(([, a], [, b]) => b - a)
            .slice(0, 10)
        ),
        credibilityTiers: credibilityTierCounts,
      },
    };
  }, [evidence, baseline]);

  useEffect(() => {
    if (!svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const margin = { top: 40, right: 40, bottom: 40, left: 40 };
    const chartSize = size - margin.left - margin.right;
    const radius = chartSize / 2;
    const centerX = chartSize / 2 + margin.left;
    const centerY = chartSize / 2 + margin.top;

    const g = svg
      .append('g')
      .attr('transform', `translate(${centerX},${centerY})`);

    const axes = metrics.axes;
    const angleSlice = (Math.PI * 2) / axes.length;

    // Scales
    const rScale = d3.scaleLinear().domain([0, 100]).range([0, radius]);

    // Draw grid circles
    const levels = 5;
    for (let i = 1; i <= levels; i++) {
      const levelRadius = (radius / levels) * i;
      g.append('circle')
        .attr('cx', 0)
        .attr('cy', 0)
        .attr('r', levelRadius)
        .style('fill', 'none')
        .style('stroke', '#2d3340')
        .style('stroke-width', '1px')
        .style('stroke-dasharray', '3,3');

      // Add level labels
      g.append('text')
        .attr('x', 4)
        .attr('y', -levelRadius + 4)
        .attr('text-anchor', 'start')
        .style('fill', '#6c7385')
        .style('font-size', '9px')
        .style('font-family', 'JetBrains Mono, monospace')
        .text(`${(i / levels) * 100}`);
    }

    // Draw axes
    axes.forEach((axis, i) => {
      const angle = i * angleSlice - Math.PI / 2;
      const x = Math.cos(angle) * radius;
      const y = Math.sin(angle) * radius;

      g.append('line')
        .attr('x1', 0)
        .attr('y1', 0)
        .attr('x2', x)
        .attr('y2', y)
        .style('stroke', '#2d3340')
        .style('stroke-width', '1px');

      // Axis labels
      const labelRadius = radius + 20;
      const labelX = Math.cos(angle) * labelRadius;
      const labelY = Math.sin(angle) * labelRadius;

      g.append('text')
        .attr('x', labelX)
        .attr('y', labelY)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .style('fill', selectedAxis === axis.name ? '#00d4ff' : '#9aa1b3')
        .style('font-size', '10px')
        .style('font-family', 'Inter Tight, sans-serif')
        .style('cursor', 'pointer')
        .text(axis.name.split(' ')[0])
        .on('click', () => {
          setSelectedAxis(axis.name);
          if (onSliceClick) onSliceClick(axis.name);
        })
        .on('mouseover', function () {
          d3.select(this).style('fill', '#00d4ff');
        })
        .on('mouseout', function () {
          d3.select(this).style('fill', selectedAxis === axis.name ? '#00d4ff' : '#9aa1b3');
        });
    });

    // Draw data polygon
    const line = d3
      .lineRadial<{ angle: number; value: number }>()
      .angle((d) => d.angle)
      .radius((d) => rScale(d.value))
      .curve(d3.curveLinearClosed);

    const dataPoints = axes.map((axis, i) => ({
      angle: i * angleSlice,
      value: axis.value,
    }));

    g.append('path')
      .datum(dataPoints)
      .attr('d', line)
      .style('fill', 'rgba(0, 212, 255, 0.1)')
      .style('stroke', '#00d4ff')
      .style('stroke-width', '2px');

    // Draw data points
    dataPoints.forEach((point, i) => {
      const angle = point.angle;
      const r = rScale(point.value);
      const x = Math.cos(angle - Math.PI / 2) * r;
      const y = Math.sin(angle - Math.PI / 2) * r;

      g.append('circle')
        .attr('cx', x)
        .attr('cy', y)
        .attr('r', 4)
        .style('fill', '#00d4ff')
        .style('cursor', 'pointer')
        .on('click', () => {
          setSelectedAxis(axes[i].name);
          if (onSliceClick) onSliceClick(axes[i].name);
        })
        .on('mouseover', function () {
          d3.select(this).attr('r', 6).style('fill', '#00ff9d');
        })
        .on('mouseout', function () {
          d3.select(this).attr('r', 4).style('fill', '#00d4ff');
        });
    });

    // Draw baseline polygon if in comparison mode
    if (comparisonMode) {
      const baselinePoints = axes.map((axis, i) => ({
        angle: i * angleSlice,
        value: axis.baseline || 0,
      }));

      g.append('path')
        .datum(baselinePoints)
        .attr('d', line)
        .style('fill', 'rgba(255, 184, 0, 0.1)')
        .style('stroke', '#ffb800')
        .style('stroke-width', '2px')
        .style('stroke-dasharray', '5,5');
    }

    // Add tooltip
    const tooltip = d3
      .select('body')
      .append('div')
      .attr('class', 'radar-tooltip')
      .style('position', 'absolute')
      .style('visibility', 'hidden')
      .style('background', '#0a0a0a')
      .style('border', '1px solid #2d3340')
      .style('padding', '8px 12px')
      .style('border-radius', '2px')
      .style('font-size', '11px')
      .style('font-family', 'Inter Tight, sans-serif')
      .style('color', '#f0f2f5')
      .style('pointer-events', 'none')
      .style('z-index', '1000');

    dataPoints.forEach((point, i) => {
      const angle = point.angle;
      const r = rScale(point.value);
      const x = Math.cos(angle - Math.PI / 2) * r;
      const y = Math.sin(angle - Math.PI / 2) * r;

      g.append('circle')
        .attr('cx', x)
        .attr('cy', y)
        .attr('r', 15)
        .style('fill', 'transparent')
        .style('cursor', 'pointer')
        .on('mouseover', (event) => {
          const axis = axes[i];
          tooltip
            .style('visibility', 'visible')
            .html(`
              <div style="font-weight: 600; margin-bottom: 4px;">${axis.name}</div>
              <div>Current: ${axis.value.toFixed(1)}%</div>
              ${axis.baseline !== undefined ? `<div>Baseline: ${axis.baseline.toFixed(1)}%</div>` : ''}
            `)
            .style('left', `${event.pageX + 10}px`)
            .style('top', `${event.pageY - 10}px`);
        })
        .on('mousemove', (event) => {
          tooltip
            .style('left', `${event.pageX + 10}px`)
            .style('top', `${event.pageY - 10}px`);
        })
        .on('mouseout', () => {
          tooltip.style('visibility', 'hidden');
        });
    });

    return () => {
      tooltip.remove();
    };
  }, [metrics, size, selectedAxis, onSliceClick, comparisonMode]);

  return (
    <div className={className}>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Source Diversity Analysis</CardTitle>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={comparisonMode}
                onChange={(e) => setComparisonMode(e.target.checked)}
                className="w-3 h-3 rounded-sm"
              />
              <span className="text-[#f0f2f5]">Compare Baseline</span>
            </label>
          </div>
        </CardHeader>

        <CardBody>
          <div className="flex gap-6">
            {/* Radar Chart */}
            <div className="flex-shrink-0">
              <svg
                ref={svgRef}
                width={size}
                height={size}
                style={{
                  backgroundColor: '#0a0a0a',
                }}
              />
            </div>

            {/* Breakdown Panel */}
            <div className="flex-1 space-y-4">
              <div>
                <h4 className="text-xs font-semibold text-[#9aa1b3] uppercase tracking-wider mb-2">
                  Source Types
                </h4>
                <div className="space-y-1">
                  {Object.entries(metrics.breakdowns.sourceTypes).map(([type, count]) => (
                    <div key={type} className="flex items-center justify-between text-sm">
                      <span className="text-[#f0f2f5] capitalize">{type}</span>
                      <span className="text-[#00d4ff] font-mono">{count}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h4 className="text-xs font-semibold text-[#9aa1b3] uppercase tracking-wider mb-2">
                  Top Publishers
                </h4>
                <div className="space-y-1">
                  {Object.entries(metrics.breakdowns.publishers).map(([publisher, count]) => (
                    <div key={publisher} className="flex items-center justify-between text-sm">
                      <span className="text-[#f0f2f5]">{publisher}</span>
                      <span className="text-[#00d4ff] font-mono">{count}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h4 className="text-xs font-semibold text-[#9aa1b3] uppercase tracking-wider mb-2">
                  Credibility Tiers
                </h4>
                <div className="space-y-1">
                  {Object.entries(metrics.breakdowns.credibilityTiers).map(([tier, count]) => (
                    <div key={tier} className="flex items-center justify-between text-sm">
                      <span className="text-[#f0f2f5] capitalize">{tier}</span>
                      <span className="text-[#00d4ff] font-mono">{count}</span>
                    </div>
                  ))}
                </div>
              </div>

              {selectedAxis && (
                <div className="pt-4 border-t border-[#2d3340]">
                  <h4 className="text-xs font-semibold text-[#00d4ff] uppercase tracking-wider mb-2">
                    Selected: {selectedAxis}
                  </h4>
                  <p className="text-sm text-[#9aa1b3]">
                    {metrics.axes.find((a) => a.name === selectedAxis)?.value.toFixed(1)}%
                  </p>
                </div>
              )}
            </div>
          </div>
        </CardBody>
      </Card>
    </div>
  );
};

export default SourceRadar;
