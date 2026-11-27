import React from 'react';
import clsx from 'clsx';
import { FileQuestion, Inbox, Loader2, WifiOff } from 'lucide-react';
import Badge from './Badge';
import Button from './Button';
import Card from './Card';

/**
 * One shared recipe for the four reader states a case-scoped read surface can be
 * in: still loading, recorded-but-empty, not found, and network error.
 *
 * The states are distinguished by *text* (a badge label, a heading and a
 * sentence), not by colour alone, and each root element carries a stable
 * `data-state` attribute so callers and tests can assert which state rendered.
 *
 * This is deliberately presentation only: it fetches nothing, holds no cache and
 * introduces no state platform. Callers pass the state they already know from
 * their query.
 */
export type ReaderStateKind = 'loading' | 'empty' | 'not-found' | 'network-error';

interface ReaderStateCopy {
  label: string;
  title: string;
  description: string;
  badgeVariant: 'info' | 'neutral' | 'warning' | 'danger';
  Icon: React.ComponentType<{ size?: number; className?: string; 'aria-hidden'?: boolean }>;
  role: 'status' | 'alert';
}

const STATE_COPY: Record<ReaderStateKind, ReaderStateCopy> = {
  loading: {
    label: 'Loading',
    title: 'Loading recorded data',
    description: 'Fetching the recorded data for this view.',
    badgeVariant: 'info',
    Icon: Loader2,
    role: 'status',
  },
  empty: {
    label: 'Empty',
    title: 'No recorded data',
    description: 'This view has no recorded entries for this case yet.',
    badgeVariant: 'neutral',
    Icon: Inbox,
    role: 'status',
  },
  'not-found': {
    label: 'Not found',
    title: 'Record not found',
    description: 'The requested record is not available for this case.',
    badgeVariant: 'warning',
    Icon: FileQuestion,
    role: 'status',
  },
  'network-error': {
    label: 'Network error',
    title: 'Could not reach the server',
    description: 'The request failed before the server returned data.',
    badgeVariant: 'danger',
    Icon: WifiOff,
    role: 'alert',
  },
};

export interface ReaderStateProps {
  state: ReaderStateKind;
  /** Replaces the state's default heading. */
  title?: string;
  /** Replaces the state's default explanatory sentence. */
  description?: React.ReactNode;
  /** Server/transport detail line. Never used as the only signal of the state. */
  detail?: string | null;
  /** Offered for the error state only; a retry that cannot succeed is never shown. */
  onRetry?: () => void;
  retryLabel?: string;
  /** "Last fetched" label for a surface that refreshes (polling or manual). */
  lastFetched?: string | null;
  className?: string;
}

const ReaderState: React.FC<ReaderStateProps> = ({
  state,
  title,
  description,
  detail,
  onRetry,
  retryLabel = 'Retry',
  lastFetched,
  className,
}) => {
  const copy = STATE_COPY[state];
  const { Icon } = copy;
  const showRetry = state === 'network-error' && typeof onRetry === 'function';

  return (
    <Card
      variant="bordered"
      padding="md"
      className={clsx('reader-state', `reader-state--${state}`, className)}
      data-state={state}
      role={copy.role}
      aria-busy={state === 'loading' || undefined}
    >
      <div className="reader-state__header">
        <Badge variant={copy.badgeVariant} className="reader-state__badge">
          {copy.label}
        </Badge>
        <span className="reader-state__icon" aria-hidden="true">
          <Icon size={16} className={state === 'loading' ? 'reader-state__spinner' : undefined} />
        </span>
      </div>
      <h4 className="reader-state__title">{title ?? copy.title}</h4>
      <p className="reader-state__description">{description ?? copy.description}</p>
      {detail && <p className="reader-state__detail">{detail}</p>}
      {lastFetched && <p className="reader-state__last-fetched">Last fetched {lastFetched}</p>}
      {showRetry && (
        <div className="reader-state__actions">
          <Button variant="secondary" size="sm" onClick={onRetry}>
            {retryLabel}
          </Button>
        </div>
      )}
    </Card>
  );
};

export default ReaderState;
