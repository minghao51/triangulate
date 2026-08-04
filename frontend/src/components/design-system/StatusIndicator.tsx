import React from 'react';
import { Circle } from 'lucide-react';
import clsx from 'clsx';
import type { VerificationStatus, CaseStatus } from '../../types/backend-models';

export interface StatusIndicatorProps {
  status: VerificationStatus | CaseStatus | 'running' | 'idle' | 'error';
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  label?: string;
  pulse?: boolean;
}

const STATUS_CONFIG: Record<string, { color: string; bgColor: string; label: string }> = {
  confirmed: { color: 'text-[#00d4ff]', bgColor: 'bg-[#00d4ff]', label: 'Confirmed' },
  probable: { color: 'text-[#00ff9d]', bgColor: 'bg-[#00ff9d]', label: 'Probable' },
  alleged: { color: 'text-[#ffb800]', bgColor: 'bg-[#ffb800]', label: 'Alleged' },
  contested: { color: 'text-[#ff6b00]', bgColor: 'bg-[#ff6b00]', label: 'Contested' },
  debunked: { color: 'text-[#ff4757]', bgColor: 'bg-[#ff4757]', label: 'Debunked' },
  unknown: { color: 'text-[#6c7385]', bgColor: 'bg-[#6c7385]', label: 'Unknown' },
  approved: { color: 'text-[#00ff9d]', bgColor: 'bg-[#00ff9d]', label: 'Approved' },
  rejected: { color: 'text-[#ff4757]', bgColor: 'bg-[#ff4757]', label: 'Rejected' },
  'review ready': { color: 'text-[#00d4ff]', bgColor: 'bg-[#00d4ff]', label: 'Review Ready' },
  investigating: { color: 'text-[#ffb800]', bgColor: 'bg-[#ffb800]', label: 'Investigating' },
  processing: { color: 'text-[#00d4ff]', bgColor: 'bg-[#00d4ff]', label: 'Processing' },
  discovering: { color: 'text-[#a55eea]', bgColor: 'bg-[#a55eea]', label: 'Discovering' },
  monitoring: { color: 'text-[#00ff9d]', bgColor: 'bg-[#00ff9d]', label: 'Monitoring' },
  failed: { color: 'text-[#ff4757]', bgColor: 'bg-[#ff4757]', label: 'Failed' },
  running: { color: 'text-[#00d4ff]', bgColor: 'bg-[#00d4ff]', label: 'Running' },
  idle: { color: 'text-[#6c7385]', bgColor: 'bg-[#6c7385]', label: 'Idle' },
  error: { color: 'text-[#ff4757]', bgColor: 'bg-[#ff4757]', label: 'Error' },
};

const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  status,
  size = 'sm',
  showLabel = true,
  label,
  pulse = false,
}) => {
  const config = STATUS_CONFIG[status] || { color: 'text-[#6c7385]', bgColor: 'bg-[#6c7385]', label: String(status) };
  const displayLabel = label || config.label;

  const sizes = {
    sm: 'w-2 h-2',
    md: 'w-2.5 h-2.5',
    lg: 'w-3 h-3',
  };

  return (
    <div className="inline-flex items-center gap-2">
      <div className="relative">
        <Circle
          className={clsx(
            sizes[size],
            config.color,
            'fill-current'
          )}
        />
        {pulse && (
          <Circle
            className={clsx(
              sizes[size],
              'absolute top-0 left-0 animate-ping opacity-75',
              config.bgColor
            )}
            style={{ filter: 'blur(2px)' }}
          />
        )}
      </div>
      {showLabel && (
        <span className={clsx('text-sm font-medium', config.color)}>
          {displayLabel}
        </span>
      )}
    </div>
  );
};

export default StatusIndicator;
