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

const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  status,
  size = 'sm',
  showLabel = true,
  label,
  pulse = false,
}) => {
  const getStatusConfig = () => {
    switch (status) {
      case 'confirmed':
        return { color: 'text-[#00d4ff]', bgColor: 'bg-[#00d4ff]', label: 'Confirmed' };
      case 'probable':
        return { color: 'text-[#00ff9d]', bgColor: 'bg-[#00ff9d]', label: 'Probable' };
      case 'alleged':
        return { color: 'text-[#ffb800]', bgColor: 'bg-[#ffb800]', label: 'Alleged' };
      case 'contested':
        return { color: 'text-[#ff6b00]', bgColor: 'bg-[#ff6b00]', label: 'Contested' };
      case 'debunked':
        return { color: 'text-[#ff4757]', bgColor: 'bg-[#ff4757]', label: 'Debunked' };
      case 'unknown':
        return { color: 'text-[#6c7385]', bgColor: 'bg-[#6c7385]', label: 'Unknown' };
      case 'approved':
        return { color: 'text-[#00ff9d]', bgColor: 'bg-[#00ff9d]', label: 'Approved' };
      case 'rejected':
        return { color: 'text-[#ff4757]', bgColor: 'bg-[#ff4757]', label: 'Rejected' };
      case 'review ready':
        return { color: 'text-[#00d4ff]', bgColor: 'bg-[#00d4ff]', label: 'Review Ready' };
      case 'investigating':
        return { color: 'text-[#ffb800]', bgColor: 'bg-[#ffb800]', label: 'Investigating' };
      case 'processing':
        return { color: 'text-[#00d4ff]', bgColor: 'bg-[#00d4ff]', label: 'Processing' };
      case 'discovering':
        return { color: 'text-[#a55eea]', bgColor: 'bg-[#a55eea]', label: 'Discovering' };
      case 'monitoring':
        return { color: 'text-[#00ff9d]', bgColor: 'bg-[#00ff9d]', label: 'Monitoring' };
      case 'failed':
        return { color: 'text-[#ff4757]', bgColor: 'bg-[#ff4757]', label: 'Failed' };
      case 'running':
        return { color: 'text-[#00d4ff]', bgColor: 'bg-[#00d4ff]', label: 'Running' };
      case 'idle':
        return { color: 'text-[#6c7385]', bgColor: 'bg-[#6c7385]', label: 'Idle' };
      case 'error':
        return { color: 'text-[#ff4757]', bgColor: 'bg-[#ff4757]', label: 'Error' };
      default:
        return { color: 'text-[#6c7385]', bgColor: 'bg-[#6c7385]', label: String(status) };
    }
  };

  const config = getStatusConfig();
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
