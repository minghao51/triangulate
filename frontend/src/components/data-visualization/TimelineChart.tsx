import React, { useRef, useEffect, useState } from 'react';
import * as d3 from 'd3';
import type { TimelineEvent, VerificationStatus } from '../../types/backend-models';
import Card, { CardHeader, CardTitle, CardBody } from '../design-system/Card';

export interface TimelineChartProps {
  events: TimelineEvent[];
  onEventClick?: (eventId: string) => void;
  height?: string | number;
  className?: string;
}

const getStatusColor = (status: VerificationStatus): string => {
  const colors = {
    confirmed: '#00d4ff',
    probable: '#00ff9d',
    alleged: '#ffb800',
    contested: '#ff6b00',
    debunked: '#ff4757',
    unknown: '#6c7385',
  };
  return colors[status] || colors.unknown;
};

export const TimelineChart: React.FC<TimelineChartProps> = ({
  events,
  onEventClick,
  height = '600px',
  className = '',
}) => {
  const svgRef = useRef<SVGSVGElement>(null);
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    statuses: ['confirmed', 'probable', 'alleged', 'contested', 'debunked', 'unknown'] as VerificationStatus[],
  });

  const filteredEvents = events.filter((event) =>
    filters.statuses.includes(event.verificationStatus)
  );

  type EventWithDate = TimelineEvent & { date: Date };

  useEffect(() => {
    if (!svgRef.current || filteredEvents.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const container = svgRef.current.parentElement;
    if (!container) return;

    const margin = { top: 40, right: 120, bottom: 40, left: 120 };
    const width = container.clientWidth - margin.left - margin.right;
    const heightValue = typeof height === 'number' ? height : parseInt(height) || 600;

    // Create main group
    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // Parse timestamps
    const eventsWithDates = (filteredEvents
      .filter((e) => e.timestamp !== null)
      .map((e) => ({
        ...e,
        date: new Date(e.timestamp as string),
      })) as EventWithDate[])
      .sort((a, b) => a.date.getTime() - b.date.getTime());

    if (eventsWithDates.length === 0) {
      g.append('text')
        .attr('x', width / 2)
        .attr('y', heightValue / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', '#6c7385')
        .style('font-size', '14px')
        .text('No events with valid timestamps to display');
      return;
    }

    // Create time scale
    const xScale = d3
      .scaleTime()
      .domain(d3.extent(eventsWithDates, (d) => d.date) as [Date, Date])
      .range([0, width]);

    // Create y scale for event lanes
    const laneHeight = 60;
    const yScale = d3
      .scaleLinear()
      .domain([0, Math.min(eventsWithDates.length, 10)])
      .range([0, Math.min(eventsWithDates.length, 10) * laneHeight]);

    // Add vertical grid lines for time periods
    const timeExtent = d3.extent(eventsWithDates, (d) => d.date) as [Date, Date];
    const timeDiff = timeExtent[1].getTime() - timeExtent[0].getTime();

    let tickInterval: d3.TimeInterval;
    if (timeDiff < 86400000) {
      // Less than a day - show hours
      tickInterval = d3.timeHour;
    } else if (timeDiff < 2592000000) {
      // Less than 30 days - show days
      tickInterval = d3.timeDay;
    } else if (timeDiff < 31536000000) {
      // Less than a year - show months
      tickInterval = d3.timeMonth;
    } else {
      // More than a year - show years
      tickInterval = d3.timeYear;
    }

    const xAxis = d3
      .axisTop(xScale)
      .ticks(tickInterval, timeDiff < 86400000 ? '%H:%M' : timeDiff < 2592000000 ? '%b %d' : '%b %Y')
      .tickSize(-heightValue)
      .tickPadding(10);

    g.append('g')
      .attr('class', 'grid')
      .attr('transform', `translate(0,0)`)
      .call(xAxis)
      .selectAll('line')
      .attr('stroke', '#2d3340')
      .attr('stroke-dasharray', '4,4');

    g.selectAll('.grid text')
      .attr('fill', '#9aa1b3')
      .attr('font-size', '11px')
      .attr('font-family', 'Inter Tight, sans-serif');

    g.selectAll('.grid path, .grid line').attr('stroke', '#2d3340');

    // Assign events to lanes to avoid overlap
    const lanes: EventWithDate[][] = [];
    eventsWithDates.forEach((event) => {
      let placed = false;
      for (let i = 0; i < lanes.length; i++) {
        const lastEvent = lanes[i][lanes[i].length - 1];
        const lastDate = new Date(lastEvent.timestamp!);
        const timeSinceLast = event.date.getTime() - lastDate.getTime();
        // Minimum 2 days between events in same lane
        if (timeSinceLast > 172800000) {
          lanes[i].push(event);
          placed = true;
          break;
        }
      }
      if (!placed) {
        lanes.push([event]);
      }
    });

    // Draw events
    lanes.forEach((lane, laneIndex) => {
      lane.forEach((event) => {
        const x = xScale(event.date);
        const y = yScale(laneIndex);

        // Event group
        const eventGroup = g.append('g').attr('class', 'event');

        // Event line
        eventGroup
          .append('line')
          .attr('x1', x)
          .attr('y1', y + 10)
          .attr('x2', x)
          .attr('y2', y + 40)
          .attr('stroke', getStatusColor(event.verificationStatus))
          .attr('stroke-width', 2);

        // Event dot
        eventGroup
          .append('circle')
          .attr('cx', x)
          .attr('cy', y + 10)
          .attr('r', 6)
          .attr('fill', '#0a0a0a')
          .attr('stroke', getStatusColor(event.verificationStatus))
          .attr('stroke-width', 2)
          .style('cursor', 'pointer')
          .on('click', () => {
            setSelectedEvent(event.id);
            if (onEventClick) onEventClick(event.id);
          })
          .on('mouseover', function () {
            d3.select(this).attr('r', 8).attr('stroke-width', 3);
          })
          .on('mouseout', function () {
            d3.select(this).attr('r', 6).attr('stroke-width', 2);
          });

        // Event label (truncated)
        const maxLength = 40;
        const label = event.title.length > maxLength
          ? event.title.substring(0, maxLength) + '...'
          : event.title;

        eventGroup
          .append('text')
          .attr('x', x)
          .attr('y', y + 55)
          .attr('text-anchor', 'middle')
          .attr('fill', selectedEvent === event.id ? '#00d4ff' : '#f0f2f5')
          .style('font-size', '11px')
          .style('font-family', 'Inter Tight, sans-serif')
          .style('cursor', 'pointer')
          .text(label)
          .on('click', () => {
            setSelectedEvent(event.id);
            if (onEventClick) onEventClick(event.id);
          });

        // Evidence count badge
        if (event.linkedEvidenceCount > 0) {
          eventGroup
            .append('text')
            .attr('x', x)
            .attr('y', y + 70)
            .attr('text-anchor', 'middle')
            .attr('fill', '#9aa1b3')
            .style('font-size', '10px')
            .style('font-family', 'JetBrains Mono, monospace')
            .text(`${event.linkedEvidenceCount} evidence`);
        }
      });
    });

    // Zoom behavior
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.5, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });

    svg.call(zoom);

    // Initial fit
    const zoomToFit = () => {
      const contentWidth = Math.max(width, xScale.range()[1]);
      const scale = Math.min(1, width / contentWidth);
      svg.transition().duration(750).call(
        zoom.transform,
        d3.zoomIdentity.translate(margin.left, margin.top).scale(scale)
      );
    };

    setTimeout(zoomToFit, 100);

    // Handle resize
    const handleResize = () => {
      // Redraw on resize
      // In production, would debounce this
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [filteredEvents, height, onEventClick, selectedEvent]);

  const toggleStatus = (status: VerificationStatus) => {
    setFilters((prev) => ({
      ...prev,
      statuses: prev.statuses.includes(status)
        ? prev.statuses.filter((s) => s !== status)
        : [...prev.statuses, status],
    }));
  };

  return (
    <div className={className} style={{ height }}>
      <Card className="h-full flex flex-col">
        <CardHeader>
          <CardTitle>Timeline Visualization</CardTitle>
        </CardHeader>

        <CardBody className="flex-1 flex gap-4 overflow-hidden">
          {/* Filters Panel */}
          <div className="w-48 flex-shrink-0 space-y-4">
            <div>
              <h4 className="text-xs font-semibold text-[#9aa1b3] uppercase tracking-wider mb-2">
                Verification Status
              </h4>
              <div className="space-y-1">
                {(['confirmed', 'probable', 'alleged', 'contested', 'debunked', 'unknown'] as VerificationStatus[]).map(
                  (status) => (
                    <label key={status} className="flex items-center gap-2 text-sm cursor-pointer">
                      <input
                        type="checkbox"
                        checked={filters.statuses.includes(status)}
                        onChange={() => toggleStatus(status)}
                        className="w-3 h-3 rounded-sm"
                      />
                      <div className="flex items-center gap-1.5">
                        <div
                          className="w-2 h-2 rounded-sm"
                          style={{ backgroundColor: getStatusColor(status) }}
                        />
                        <span className="text-[#f0f2f5] capitalize">{status}</span>
                      </div>
                    </label>
                  )
                )}
              </div>
            </div>

            <div className="pt-4 border-t border-[#2d3340]">
              <h4 className="text-xs font-semibold text-[#9aa1b3] uppercase tracking-wider mb-2">
                Statistics
              </h4>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-[#9aa1b3]">Total Events</span>
                  <span className="text-[#f0f2f5] font-mono">{filteredEvents.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#9aa1b3]">With Timestamps</span>
                  <span className="text-[#f0f2f5] font-mono">
                    {filteredEvents.filter((e) => e.timestamp !== null).length}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Chart Area */}
          <div className="flex-1 border border-[#2d3340] rounded-sm overflow-hidden relative">
            <svg
              ref={svgRef}
              style={{
                width: '100%',
                height: '100%',
                backgroundColor: '#0a0a0a',
              }}
            />
            {filteredEvents.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center">
                <p className="text-[#6c7385]">No events to display</p>
              </div>
            )}
          </div>
        </CardBody>
      </Card>
    </div>
  );
};

export default TimelineChart;
