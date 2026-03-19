import React from 'react';
import Card, { CardBody } from '../design-system/Card';

export interface MetricItem {
  label: string;
  value: number | string;
  unit?: string;
  trend?: number; // Percentage change
  sparkline?: number[]; // Array of values for mini chart
  color?: 'success' | 'warning' | 'danger' | 'info' | 'neutral';
  icon?: React.ReactNode;
}

export interface MetricsGridProps {
  metrics: MetricItem[];
  columns?: 2 | 3 | 4;
  className?: string;
}

const getColorClasses = (color: MetricItem['color']) => {
  const colors = {
    success: 'text-[#00ff9d]',
    warning: 'text-[#ffb800]',
    danger: 'text-[#ff4757]',
    info: 'text-[#00d4ff]',
    neutral: 'text-[#9aa1b3]',
  };
  return colors[color || 'neutral'];
};

const getTrendIcon = (trend: number) => {
  if (trend > 0) return '↑';
  if (trend < 0) return '↓';
  return '→';
};

const getTrendColor = (trend: number) => {
  if (trend > 0) return 'text-[#00ff9d]';
  if (trend < 0) return 'text-[#ff4757]';
  return 'text-[#6c7385]';
};

export const MetricsGrid: React.FC<MetricsGridProps> = ({
  metrics,
  columns = 4,
  className = '',
}) => {
  const gridCols = columns === 2 ? 'grid-cols-2' : columns === 3 ? 'grid-cols-3' : 'grid-cols-4';

  return (
    <div className={className}>
      <div className={`grid ${gridCols} gap-4`}>
        {metrics.map((metric, index) => (
          <Card key={index} hover padding="sm">
            <CardBody className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {metric.icon && (
                    <div className={getColorClasses(metric.color)}>
                      {metric.icon}
                    </div>
                  )}
                  <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">
                    {metric.label}
                  </div>
                </div>
                {metric.trend !== undefined && (
                  <div className={`text-xs font-mono ${getTrendColor(metric.trend)}`}>
                    {getTrendIcon(metric.trend)} {Math.abs(metric.trend)}%
                  </div>
                )}
              </div>

              <div className="flex items-baseline gap-1">
                <span className={`text-2xl font-semibold ${getColorClasses(metric.color)}`}>
                  {metric.value}
                </span>
                {metric.unit && (
                  <span className="text-xs text-[#6c7385]">{metric.unit}</span>
                )}
              </div>

              {metric.sparkline && metric.sparkline.length > 0 && (
                <div className="h-8">
                  <Sparkline data={metric.sparkline} color={metric.color || 'neutral'} />
                </div>
              )}
            </CardBody>
          </Card>
        ))}
      </div>
    </div>
  );
};

// Sparkline Mini Chart Component
const Sparkline: React.FC<{ data: number[]; color: MetricItem['color'] }> = ({ data, color }) => {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;

  const points = data.map((value, index) => {
    const x = (index / (data.length - 1)) * 100;
    const y = 100 - ((value - min) / range) * 100;
    return `${x},${y}`;
  }).join(' ');

  const getColor = () => {
    const colors = {
      success: '#00ff9d',
      warning: '#ffb800',
      danger: '#ff4757',
      info: '#00d4ff',
      neutral: '#6c7385',
    };
    return colors[color || 'neutral'];
  };

  return (
    <svg viewBox="0 0 100 100" className="w-full h-full" preserveAspectRatio="none">
      <polyline
        points={points}
        fill="none"
        stroke={getColor()}
        strokeWidth="2"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
};

export default MetricsGrid;
