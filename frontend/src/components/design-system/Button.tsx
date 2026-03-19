import React from 'react';
import { Loader2 } from 'lucide-react';
import clsx from 'clsx';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  icon?: React.ReactNode;
}

const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  children,
  disabled,
  className,
  ...props
}) => {
  const baseStyles = 'inline-flex items-center justify-center font-medium transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-[#0a0a0a] disabled:opacity-50 disabled:cursor-not-allowed';

  const variants = {
    primary: 'bg-[#00d4ff] text-black hover:bg-[#00b8e6] focus:ring-[#00d4ff]',
    secondary: 'bg-[#1a1a1a] text-[#f0f2f5] border border-[#2d3340] hover:bg-[#222631] focus:ring-[#3f4758]',
    danger: 'bg-[#ff4757] text-white hover:bg-[#e63e52] focus:ring-[#ff4757]',
    ghost: 'bg-transparent text-[#9aa1b3] hover:bg-[#1a1a1a] hover:text-[#f0f2f5] focus:ring-[#3f4758]',
  };

  const sizes = {
    sm: 'px-3 py-1.5 text-sm gap-1.5 rounded',
    md: 'px-4 py-2 text-sm gap-2 rounded-sm',
    lg: 'px-6 py-3 text-base gap-2 rounded-sm',
  };

  return (
    <button
      className={clsx(
        baseStyles,
        variants[variant],
        sizes[size],
        loading && 'cursor-wait',
        className
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 size={16} className="animate-spin" />}
      {!loading && icon && <span className="flex-shrink-0">{icon}</span>}
      {children}
    </button>
  );
};

export default Button;
