import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ReaderState, { type ReaderStateKind } from './ReaderState';
import { useVisibleRefetchInterval } from './reader-polling';

const ALL_STATES: ReaderStateKind[] = ['loading', 'empty', 'not-found', 'network-error'];

const renderState = (state: ReaderStateKind, props: Partial<React.ComponentProps<typeof ReaderState>> = {}) =>
  render(<ReaderState state={state} {...props} />);

describe('ReaderState shared recipe', () => {
  it('renders a stable data-state attribute for every shared state', () => {
    for (const state of ALL_STATES) {
      const { container, unmount } = renderState(state);
      const root = container.querySelector('[data-state]') as HTMLElement;
      expect(root).not.toBeNull();
      expect(root.dataset.state).toBe(state);
      unmount();
    }
  });

  it('distinguishes the four states by text, not colour alone', () => {
    const texts = ALL_STATES.map((state) => {
      const { container, unmount } = renderState(state);
      const text = (container.querySelector('[data-state]') as HTMLElement).textContent ?? '';
      unmount();
      return text.trim();
    });

    expect(new Set(texts).size).toBe(ALL_STATES.length);
    expect(texts[0]).toContain('Loading');
    expect(texts[1]).toContain('No recorded data');
    expect(texts[2]).toContain('Record not found');
    expect(texts[3]).toContain('Could not reach the server');
  });

  it('announces the error as an alert and the other states as status', () => {
    renderState('network-error');
    expect(screen.getByRole('alert')).toBeDefined();
    expect(screen.queryByRole('status')).toBeNull();

    renderState('loading');
    expect(screen.getAllByRole('status').length).toBeGreaterThan(0);
  });

  it('offers a retry action only for the network error state', () => {
    const onRetry = vi.fn();

    const loading = renderState('loading', { onRetry });
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
    loading.unmount();

    const empty = renderState('empty', { onRetry });
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
    empty.unmount();

    const notFound = renderState('not-found', { onRetry });
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
    notFound.unmount();

    renderState('network-error', { onRetry });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('shows the transport detail and a last-fetched label without replacing the state text', () => {
    renderState('network-error', { detail: 'timeline 500', lastFetched: '10:31:02' });

    expect(screen.getByText('timeline 500')).toBeDefined();
    expect(screen.getByText(/Last fetched 10:31:02/)).toBeDefined();
    expect(screen.getByText('Could not reach the server')).toBeDefined();
    // A retry that cannot be performed is never rendered as a dead button.
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
  });
});

describe('reader polling discipline', () => {
  let fetchCount = 0;

  const PollProbe = ({ intervalMs }: { intervalMs: number }) => {
    const refetchInterval = useVisibleRefetchInterval(intervalMs);
    const { data } = useQuery({
      queryKey: ['poll-probe'],
      queryFn: async () => {
        fetchCount += 1;
        return fetchCount;
      },
      refetchInterval,
    });
    return <div data-testid="poll-value">{data ?? 'none'}</div>;
  };

  const setVisibility = (value: 'visible' | 'hidden') => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => value });
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
  };

  beforeEach(() => {
    fetchCount = 0;
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('stops polling while the tab is hidden and resumes when it is visible again', async () => {
    vi.useFakeTimers();

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <PollProbe intervalMs={1000} />
      </QueryClientProvider>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    const pollsWhileVisible = fetchCount;
    expect(pollsWhileVisible).toBeGreaterThan(1);

    setVisibility('hidden');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(fetchCount).toBe(pollsWhileVisible);

    setVisibility('visible');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(fetchCount).toBeGreaterThan(pollsWhileVisible);

    queryClient.clear();
  });
});
