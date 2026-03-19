import React from 'react';
import clsx from 'clsx';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'confirmed' | 'probable' | 'alleged' | 'contested' | 'debunked';
  size?: 'sm' | 'md';
  dot?: boolean;
}

const Badge: React.FC<BadgeProps> = ({
  variant = 'neutral',
  size = 'sm',
  dot = false,
  children,
  className,
  ...props
}) => {
  const variants = {
    success: 'bg-[#00ff9d]/10 text-[#00ff9d] border-[#00ff9d]/20',
    warning: 'bg-[#ffb800]/10 text-[#ffb800] border-[#ffb800]/20',
    danger: 'bg-[#ff4757]/10 text-[#ff4757] border-[#ff4757]/20',
    info: 'bg-[#00d4ff]/10 text-[#00d4ff] border-[#00d4ff]/20',
    neutral: 'bg-[#6c7385]/10 text-[#6c7385] border-[#6c7385]/20',
    confirmed: 'bg-[#00d4ff]/10 text-[#00d4ff] border-[#00d4ff]/20',
    probable: 'bg-[#00ff9d]/10 text-[#00ff9d] border-[#00ff9d]/20',
    alleged: 'bg-[#ffb800]/10 text-[#ffb800] border-[#ffb800]/20',
    contested: 'bg-[#ff6b00]/10 text-[#ff6b00] border-[#ff6b00]/20',
    debunked: 'bg-[#ff4757]/10 text-[#ff4757] border-[#ff4757]/20',
  };

  const sizes = {
    sm: 'px-2 py-0.5 text-xs font-semibold tracking-wide',
    md: 'px-2.5 py-1 text-xs font-semibold tracking-wide',
  };

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 border font-medium uppercase tracking-wider rounded-sm',
        variants[variant],
        sizes[size],
        className
      )}
      {...props}
    >
      {dot && (
        <span
          className={clsx(
            'w-1.5 h-1.5 rounded-full animate-pulse',
            variant === 'success' || variant === 'confirmed' || variant === 'probable' ? 'bg-[#00ff9d]' :
            variant === 'warning' || variant === 'alleged' ? 'bg-[#ffb800]' :
            variant === 'danger' || variant === 'debunked' ? 'bg-[#ff4757]' :
            variant === 'info' ? 'bg-[#00d4ff]' :
            'bg-[#6c7385]'
          )}
        />
      )}
      {children}
    </span>
  );
};

export default Badge;
