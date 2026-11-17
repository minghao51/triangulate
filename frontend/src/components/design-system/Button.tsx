import React from 'react';
import { Loader2 } from 'lucide-react';
import clsx from 'clsx';
import './Button.css';

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
  type = 'button',
  ...props
}) => {
  return (
    <button
      type={type}
      className={clsx(
        'ds-button',
        `ds-button--${variant}`,
        `ds-button--${size}`,
        loading && 'ds-button--loading',
        className
      )}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && (
        <span className="ds-button__spinner" aria-hidden="true">
          <Loader2 size={16} />
        </span>
      )}
      {!loading && icon && (
        <span className="ds-button__icon" aria-hidden="true">
          {icon}
        </span>
      )}
      {children}
    </button>
  );
};

export default Button;
