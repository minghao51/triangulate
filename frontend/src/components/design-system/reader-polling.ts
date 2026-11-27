import { useEffect, useState } from 'react';

const isDocumentHidden = (): boolean =>
  typeof document !== 'undefined' && document.visibilityState === 'hidden';

/**
 * Polling discipline for reader queries: hand the result straight to React
 * Query's `refetchInterval`. A hidden tab reports `false`, so a background tab
 * stops polling instead of polling a surface nobody is looking at.
 *
 * React Query only re-evaluates `refetchInterval` when a query updates, so this
 * hook re-renders the query on `visibilitychange` to make the pause immediate.
 *
 * Kept out of `ReaderState.tsx` so that file stays component-only (fast refresh);
 * this is the shared pattern every polling reader uses, not a new query platform.
 */
export function useVisibleRefetchInterval(intervalMs: number, enabled = true): number | false {
  const [hidden, setHidden] = useState(isDocumentHidden);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const onVisibilityChange = () => setHidden(isDocumentHidden());
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => document.removeEventListener('visibilitychange', onVisibilityChange);
  }, []);

  return enabled && !hidden ? intervalMs : false;
}

export default useVisibleRefetchInterval;
