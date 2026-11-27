import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ExceptionsTab from './ExceptionsTab';
import { clearExceptionRowAttempts } from './exception-row-attempts';
import { ApiError } from '../../services/api-error';
import type { Exception } from '../../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getExceptionsForCase: vi.fn(),
  submitExceptionAction: vi.fn(),
}));

vi.mock('../../services/api', () => apiMocks);

const openException = (overrides: Partial<Exception> = {}): Exception => ({
  id: 'exc-1',
  type: 'missing_source',
  message: 'Need another source',
  severity: 'medium',
  status: 'open',
  recommendedAction: 'Add corroboration',
  isOpen: true,
  ...overrides,
});

const twoExceptions = [
  openException({ id: 'exc-1', message: 'First exception' }),
  openException({ id: 'exc-2', message: 'Second exception' }),
];

function deferred<T>() {
  let resolve: (value: T) => void = () => {};
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function renderTab(caseId = 'case-1') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <ExceptionsTab caseId={caseId} />
    </QueryClientProvider>
  );
  return { ...result, queryClient };
}

const rowFor = (id: string): HTMLElement => {
  const row = document.querySelector(`[data-exception-id="${id}"]`);
  if (!row) throw new Error(`row ${id} not rendered`);
  return row as HTMLElement;
};

const writeBanner = (state: string) =>
  document.querySelector(`[data-write-state="${state}"]`);

describe('ExceptionsTab read states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // The real endpoint answers with a `CaseListItem`, which always carries the case id.
    apiMocks.submitExceptionAction.mockResolvedValue({ id: 'case-1' });
  });

  it('shows loading, then a distinct empty state', async () => {
    const pendingRead = deferred<Exception[]>();
    apiMocks.getExceptionsForCase.mockReturnValue(pendingRead.promise);

    renderTab();

    expect(screen.getByRole('status').textContent).toContain('Loading');
    expect(screen.queryByText(/No open exceptions/)).toBeNull();

    await act(async () => {
      pendingRead.resolve([]);
    });

    expect(await screen.findByText('No open exceptions')).toBeDefined();
    expect(screen.queryByText(/Loading/)).toBeNull();
  });

  it('renders a read error distinctly from an empty queue and retries the GET', async () => {
    apiMocks.getExceptionsForCase.mockRejectedValueOnce(new Error('queue 500'));

    renderTab();

    expect(await screen.findByText('Exception queue unavailable')).toBeDefined();
    expect(screen.getByText('queue 500')).toBeDefined();
    expect(screen.queryByText('No open exceptions')).toBeNull();

    apiMocks.getExceptionsForCase.mockResolvedValueOnce([openException()]);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByText('Need another source')).toBeDefined();
    expect(screen.queryByText('Exception queue unavailable')).toBeNull();
  });
});

describe('ExceptionsTab write states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearExceptionRowAttempts();
    apiMocks.getExceptionsForCase.mockResolvedValue(twoExceptions);
    apiMocks.submitExceptionAction.mockResolvedValue({ id: 'case-1' });
  });

  it('disables the pending row, then shows saved-and-refreshed', async () => {
    const pendingPost = deferred<unknown>();
    apiMocks.submitExceptionAction.mockReturnValue(pendingPost.promise);

    renderTab();
    await screen.findByText('First exception');

    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }));

    await waitFor(() => expect(writeBanner('pending')).toBeTruthy());
    expect(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }).hasAttribute('disabled')).toBe(true);
    // One POST is in flight, so the other row's control waits instead of
    // accepting a click that single-flight would refuse anyway.
    expect(within(rowFor('exc-2')).getByRole('button', { name: 'Resolve' }).hasAttribute('disabled')).toBe(true);
    fireEvent.click(within(rowFor('exc-2')).getByRole('button', { name: 'Resolve' }));
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);

    await act(async () => {
      pendingPost.resolve({ id: 'case-1' });
    });

    expect(await within(rowFor('exc-1')).findByText('Saved and refreshed')).toBeDefined();
    // That wait is transient, never a permanent lock on an unrelated row.
    expect(within(rowFor('exc-2')).getByRole('button', { name: 'Resolve' }).hasAttribute('disabled')).toBe(false);
  });

  it('renders a writer conflict (409) and a blocked action (422) differently', async () => {
    apiMocks.submitExceptionAction.mockRejectedValueOnce(new ApiError('writer busy', 409));

    renderTab();
    await screen.findByText('First exception');
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }));
    expect(await within(rowFor('exc-1')).findByText('Writer conflict (409)')).toBeDefined();

    apiMocks.submitExceptionAction.mockRejectedValueOnce(new ApiError('not permitted', 422));
    fireEvent.click(within(rowFor('exc-2')).getByRole('button', { name: 'Resolve' }));
    expect(await within(rowFor('exc-2')).findByText('Blocked (422)')).toBeDefined();

    expect(within(rowFor('exc-1')).queryByText('Blocked (422)')).toBeNull();
    expect(within(rowFor('exc-2')).queryByText('Writer conflict (409)')).toBeNull();
  });

  it('never retries a lost POST automatically and requires a confirmed manual retry', async () => {
    apiMocks.submitExceptionAction.mockRejectedValue(new Error('Failed to fetch'));

    renderTab();
    await screen.findByText('First exception');
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }));

    expect(await within(rowFor('exc-1')).findByText('Outcome unknown')).toBeDefined();
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);

    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Reconcile with read (GET)' }));
    expect(await within(rowFor('exc-1')).findByText('Read refreshed — still inconclusive')).toBeDefined();
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);

    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Confirm retry' }));
    await waitFor(() => expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(2));
  });

  it('shows "Accepted; refresh failed" and retries the GET only', async () => {
    apiMocks.getExceptionsForCase
      .mockResolvedValueOnce(twoExceptions)
      .mockRejectedValueOnce(new Error('queue refresh failed'));

    renderTab();
    await screen.findByText('First exception');
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }));

    expect(await within(rowFor('exc-1')).findByText('Accepted; refresh failed')).toBeDefined();
    expect(within(rowFor('exc-1')).queryByText('Not saved')).toBeNull();
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);

    apiMocks.getExceptionsForCase.mockResolvedValue(twoExceptions);
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Retry refresh (GET)' }));

    expect(await within(rowFor('exc-1')).findByText('Saved and refreshed')).toBeDefined();
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);
  });

  it('marks an earlier saved row stale when a later write re-reads the queue', async () => {
    renderTab();
    await screen.findByText('First exception');

    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }));
    expect(await within(rowFor('exc-1')).findByText('Saved and refreshed')).toBeDefined();

    fireEvent.click(within(rowFor('exc-2')).getByRole('button', { name: 'Resolve' }));
    await waitFor(() => expect(writeBanner('stale')).toBeTruthy());

    expect(within(rowFor('exc-1')).getByText('Stale')).toBeDefined();
    expect(within(rowFor('exc-1')).queryByText('Saved and refreshed')).toBeNull();
  });

  // R01: an acknowledged-but-unrefreshed row may never be POSTed again, and its
  // lock must not spread to an unrelated row.
  it('blocks every ordinary action on an acknowledged-but-unrefreshed row and leaves the other row usable', async () => {
    apiMocks.getExceptionsForCase
      .mockResolvedValueOnce(twoExceptions)
      .mockRejectedValueOnce(new Error('queue refresh failed'))
      .mockResolvedValue(twoExceptions);
    apiMocks.submitExceptionAction.mockResolvedValue({ id: 'case-1' });

    renderTab();
    await screen.findByText('First exception');
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }));
    expect(await within(rowFor('exc-1')).findByText('Accepted; refresh failed')).toBeDefined();
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);

    for (const label of ['Resolve', 'Defer']) {
      const button = within(rowFor('exc-1')).getByRole('button', { name: label });
      expect(button.hasAttribute('disabled')).toBe(true);
      fireEvent.click(button);
    }
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);

    const other = within(rowFor('exc-2')).getByRole('button', { name: 'Resolve' });
    expect(other.hasAttribute('disabled')).toBe(false);
    fireEvent.click(other);
    await waitFor(() => expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(2));
    expect(apiMocks.submitExceptionAction.mock.calls[1]).toEqual(['case-1', 'exc-2', 'resolve']);
  });

  it('blocks a 5xx-ambiguous row before and after reconciliation and sends one unchanged action on confirmation', async () => {
    apiMocks.submitExceptionAction.mockRejectedValueOnce(new ApiError('gateway', 503));

    renderTab();
    await screen.findByText('First exception');
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }));
    expect(await within(rowFor('exc-1')).findByText('Outcome unknown')).toBeDefined();
    expect(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }).hasAttribute('disabled')).toBe(true);

    // An unsuccessful reconciliation read does not unlock the row.
    apiMocks.getExceptionsForCase.mockRejectedValueOnce(new Error('reconcile read failed'));
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Reconcile with read (GET)' }));
    expect(await within(rowFor('exc-1')).findByText(/Reconciliation read failed/)).toBeDefined();
    expect(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }).hasAttribute('disabled')).toBe(true);
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);

    // A successful read reconciles but stays inconclusive.
    apiMocks.getExceptionsForCase.mockResolvedValue(twoExceptions);
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Reconcile with read (GET)' }));
    expect(await within(rowFor('exc-1')).findByText('Read refreshed — still inconclusive')).toBeDefined();
    expect(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }).hasAttribute('disabled')).toBe(true);
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }));
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);

    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Confirm retry' }));
    await waitFor(() => expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(2));
    expect(apiMocks.submitExceptionAction.mock.calls[1]).toEqual(['case-1', 'exc-1', 'resolve']);
  });

  it('refuses a confirmed retry when the row no longer permits the recorded action', async () => {
    apiMocks.submitExceptionAction.mockRejectedValueOnce(new Error('network down'));

    renderTab();
    await screen.findByText('First exception');
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }));
    expect(await within(rowFor('exc-1')).findByText('Outcome unknown')).toBeDefined();

    // The reconciliation read reports the row as already closed elsewhere.
    apiMocks.getExceptionsForCase.mockResolvedValue([
      openException({ id: 'exc-1', message: 'First exception', status: 'resolved', isOpen: false }),
      openException({ id: 'exc-2', message: 'Second exception' }),
    ]);
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Reconcile with read (GET)' }));
    expect(await within(rowFor('exc-1')).findByText('Read refreshed — still inconclusive')).toBeDefined();

    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Confirm retry' }));
    expect(
      await within(rowFor('exc-1')).findByText(/no longer permits the recorded action/)
    ).toBeDefined();
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);
  });

  it('keeps the read recovery available when the recovery GET fails', async () => {
    apiMocks.getExceptionsForCase
      .mockResolvedValueOnce(twoExceptions)
      .mockRejectedValueOnce(new Error('queue refresh failed'))
      .mockRejectedValueOnce(new Error('recovery read failed'));

    renderTab();
    await screen.findByText('First exception');
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }));
    expect(await within(rowFor('exc-1')).findByText('Accepted; refresh failed')).toBeDefined();

    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Retry refresh (GET)' }));
    expect(await within(rowFor('exc-1')).findByText('recovery read failed')).toBeDefined();
    expect(within(rowFor('exc-1')).getByText('Accepted; refresh failed')).toBeDefined();
    expect(
      within(rowFor('exc-1')).getByRole('button', { name: 'Retry refresh (GET)' }).hasAttribute('disabled')
    ).toBe(false);
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);
  });

  it('treats an ack that names another case as an unknown outcome', async () => {
    apiMocks.submitExceptionAction.mockResolvedValueOnce({ id: 'case-other' });

    renderTab();
    await screen.findByText('First exception');
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }));

    expect(await within(rowFor('exc-1')).findByText('Outcome unknown')).toBeDefined();
    expect(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }).hasAttribute('disabled')).toBe(true);
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);
  });

  it('treats an ack that names no case at all as an unknown outcome', async () => {
    // R01: the endpoint answers with a `CaseListItem`, so a success body with no
    // case identity cannot prove the expected result was recorded.
    apiMocks.submitExceptionAction.mockResolvedValueOnce({});

    renderTab();
    await screen.findByText('First exception');
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }));

    expect(await within(rowFor('exc-1')).findByText('Outcome unknown')).toBeDefined();
    expect(within(rowFor('exc-1')).queryByText('Saved and refreshed')).toBeNull();
    // No ordinary POST may follow an unverifiable ack.
    for (const label of ['Resolve', 'Defer']) {
      const button = within(rowFor('exc-1')).getByRole('button', { name: label });
      expect(button.hasAttribute('disabled')).toBe(true);
      fireEvent.click(button);
    }
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);

    // Only a read reconciles it, and that still does not claim success.
    apiMocks.getExceptionsForCase.mockResolvedValue(twoExceptions);
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Reconcile with read (GET)' }));
    expect(await within(rowFor('exc-1')).findByText('Read refreshed — still inconclusive')).toBeDefined();
    expect(within(rowFor('exc-1')).queryByText('Saved and refreshed')).toBeNull();
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);
  });

  it('treats the known 404 as a rejection that keeps the row usable', async () => {
    apiMocks.submitExceptionAction.mockRejectedValueOnce(new ApiError('Exception exc-1 not found', 404));

    renderTab();
    await screen.findByText('First exception');
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }));

    expect(await within(rowFor('exc-1')).findByText('Rejected by the server')).toBeDefined();
    expect(within(rowFor('exc-1')).queryByText('Outcome unknown')).toBeNull();
    expect(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }).hasAttribute('disabled')).toBe(false);
  });

  it('sends one exception POST for two dispatches in the same tick', async () => {
    const pendingPost = deferred<unknown>();
    apiMocks.submitExceptionAction.mockReturnValue(pendingPost.promise);

    renderTab();
    await screen.findByText('First exception');
    const resolve = within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' });
    act(() => {
      resolve.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      resolve.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);
    await act(async () => {
      pendingPost.resolve({ id: 'case-1' });
    });
  });

  it('keeps the row locked across a same-case unmount and remount', async () => {
    apiMocks.getExceptionsForCase
      .mockResolvedValueOnce(twoExceptions)
      .mockRejectedValueOnce(new Error('queue refresh failed'))
      .mockResolvedValue(twoExceptions);
    apiMocks.submitExceptionAction.mockResolvedValue({ id: 'case-1' });

    const first = renderTab();
    await screen.findByText('First exception');
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }));
    expect(await within(rowFor('exc-1')).findByText('Accepted; refresh failed')).toBeDefined();
    first.unmount();

    renderTab();
    expect(await screen.findByText('First exception')).toBeDefined();
    expect(within(rowFor('exc-1')).getByText('Accepted; refresh failed')).toBeDefined();
    expect(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }).hasAttribute('disabled')).toBe(true);
    fireEvent.click(within(rowFor('exc-1')).getByRole('button', { name: 'Resolve' }));
    expect(apiMocks.submitExceptionAction).toHaveBeenCalledTimes(1);
  });
});

describe('ExceptionsTab severity disclosure', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearExceptionRowAttempts();
    apiMocks.submitExceptionAction.mockResolvedValue({ id: 'case-1' });
  });

  it('writes the severity as text for every level, with the glyph decorative', async () => {
    apiMocks.getExceptionsForCase.mockResolvedValue([
      openException({ id: 'exc-high', severity: 'high', message: 'High row' }),
      openException({ id: 'exc-medium', severity: 'medium', message: 'Medium row' }),
      openException({ id: 'exc-low', severity: 'low', message: 'Low row' }),
    ]);

    renderTab();
    await screen.findByText('High row');

    const expected: Array<[string, string]> = [
      ['exc-high', 'Severity: High'],
      ['exc-medium', 'Severity: Medium'],
      ['exc-low', 'Severity: Low'],
    ];

    for (const [id, text] of expected) {
      const row = rowFor(id);
      const label = within(row).getByText(text);
      // Visible, real text — not a colour or a glyph alone.
      expect(label.textContent).toBe(text);
      expect(label.className).toBe('exc-severity');
      expect(label.closest('[aria-hidden="true"]')).toBeNull();
      // The glyph adds no second copy of the severity to the accessible tree.
      const icon = row.querySelector('.exc-icon') as HTMLElement;
      expect(icon.getAttribute('aria-hidden')).toBe('true');
      expect(icon.textContent).toBe('');
      // Exactly one announcement of the severity per row.
      expect((row.textContent ?? '').match(new RegExp(text, 'g'))).toHaveLength(1);
    }
  });

  it('keeps the severity class on the card alongside the written label', async () => {
    apiMocks.getExceptionsForCase.mockResolvedValue([
      openException({ id: 'exc-high', severity: 'high', message: 'High row' }),
    ]);

    renderTab();
    await screen.findByText('High row');

    const row = rowFor('exc-high');
    expect(row.className).toContain('severity-high');
    expect(within(row).getByText('Severity: High')).toBeDefined();
  });
});
