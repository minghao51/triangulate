import React from 'react';
import clsx from 'clsx';

export interface ProgressBarProps {
  value: number;
  max?: number;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'default' | 'success' | 'warning' | 'danger';
  showLabel?: boolean;
  label?: string;
  animated?: boolean;
}

const ProgressBar: React.FC<ProgressBarProps> = ({
  value,
  max = 100,
  size = 'md',
  variant = 'default',
  showLabel = false,
  label,
  animated = false,
}) => {
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100);

  const variants = {
    default: 'bg-[#00d4ff]',
    success: 'bg-[#00ff9d]',
    warning: 'bg-[#ffb800]',
    danger: 'bg-[#ff4757]',
  };

  const sizes = {
    sm: 'h-1',
    md: 'h-2',
    lg: 'h-3',
  };

  return (
    <div className="w-full">
      {(showLabel || label) && (
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-[#9aa1b3]">{label || 'Progress'}</span>
          <span className="text-sm font-medium text-[#f0f2f5]">{Math.round(percentage)}%</span>
        </div>
      )}
      <div className={clsx('w-full bg-[#1a1a1a] border border-[#2d3340] rounded-sm overflow-hidden', sizes[size])}>
        <div
          className={clsx(
            'h-full transition-all duration-300 ease-out',
            variants[variant],
            animated && 'animate-pulse'
          )}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
};

export default ProgressBar;
