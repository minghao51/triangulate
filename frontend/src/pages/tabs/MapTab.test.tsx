import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MapTab from './MapTab';
import { ApiError } from '../../services/api-error';
import type { TimelineEvent } from '../../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getTimelineForCase: vi.fn(),
}));

vi.mock('../../services/api', () => apiMocks);

const makeEvent = (id: string, overrides: Partial<TimelineEvent> = {}): TimelineEvent => ({
  id,
  timestamp: '2026-03-19T10:00:00Z',
  title: `Event ${id}`,
  summary: 'Recorded event summary',
  verificationStatus: 'confirmed',
  linkedEvidenceCount: 1,
  locationLat: 51.5,
  locationLon: -0.1,
  ...overrides,
});

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

function renderMap(caseId: string, queryClient: QueryClient = newClient()) {
  // The map links each event to its case event context, so it renders inside a
  // router like the case workspace does.
  const ui = (id: string) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/cases/${id || 'none'}/map`]}>
        <MapTab caseId={id} />
      </MemoryRouter>
    </QueryClientProvider>
  );
  const result = render(ui(caseId));
  return { queryClient, rerenderWith: (id: string) => result.rerender(ui(id)), ...result };
}

const deferred = <T,>() => {
  let resolve: (value: T) => void = () => {};
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
};

describe('MapTab reader states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the shared loading state, then the mapped events', async () => {
    const pending = deferred<TimelineEvent[]>();
    apiMocks.getTimelineForCase.mockReturnValue(pending.promise);

    const { container } = renderMap('case-1');

    const loading = container.querySelector('[data-state="loading"]');
    expect(loading).not.toBeNull();
    expect(loading?.textContent).toContain('Loading recorded data');
    expect(loading?.textContent).not.toContain('No recorded data');

    await act(async () => {
      pending.resolve([makeEvent('event-1')]);
    });

    expect(await screen.findByText('Event event-1')).toBeDefined();
    expect(container.querySelector('[data-state]')).toBeNull();
    expect(screen.getByText('1 mapped')).toBeDefined();
  });

  it('renders a distinct empty state that keeps the recorded wording', async () => {
    apiMocks.getTimelineForCase.mockResolvedValue([
      makeEvent('no-coords', { locationLat: null, locationLon: null }),
    ]);

    const { container } = renderMap('case-1');

    expect(
      await screen.findByText('No geotagged events are available for this case yet.')
    ).toBeDefined();
    expect(container.querySelector('[data-state="empty"]')).not.toBeNull();
    expect(container.querySelector('[data-state="loading"]')).toBeNull();
    expect(screen.getByText('0 mapped')).toBeDefined();
  });

  it('renders a retryable network error that clears after a successful retry', async () => {
    apiMocks.getTimelineForCase.mockRejectedValueOnce(new Error('timeline 500'));

    const { container } = renderMap('case-1');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Could not reach the server');
    expect(alert.textContent).toContain('timeline 500');
    expect(container.querySelector('[data-state="network-error"]')).not.toBeNull();

    apiMocks.getTimelineForCase.mockResolvedValueOnce([makeEvent('event-1')]);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByText('Event event-1')).toBeDefined();
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(apiMocks.getTimelineForCase).toHaveBeenCalledTimes(2);
  });

  it('distinguishes a not-found case from a network failure', async () => {
    apiMocks.getTimelineForCase.mockRejectedValue(new ApiError('Case not found', 404));

    const { container } = renderMap('case-missing');

    expect(await screen.findByText('Record not found')).toBeDefined();
    expect(container.querySelector('[data-state="not-found"]')).not.toBeNull();
    expect(container.querySelector('[data-state="network-error"]')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('does not fetch without a valid case id', () => {
    const { container } = renderMap('');

    expect(apiMocks.getTimelineForCase).not.toHaveBeenCalled();
    expect(container.querySelector('[data-state="not-found"]')?.textContent).toContain(
      'No case selected'
    );
  });

  it('keeps two cases in separate cache entries and never shows a late case A response under case B', async () => {
    const pendingA = deferred<TimelineEvent[]>();
    const eventB = makeEvent('event-b', { title: 'Event from B' });
    const eventA = makeEvent('event-a', { title: 'Event from A' });

    apiMocks.getTimelineForCase.mockImplementation((caseId: string) =>
      caseId === 'case-a' ? pendingA.promise : Promise.resolve([eventB])
    );

    const { queryClient, rerenderWith } = renderMap('case-a');
    expect(queryClient.getQueryData(['timeline', 'case-a'])).toBeUndefined();

    rerenderWith('case-b');

    expect(await screen.findByText('Event from B')).toBeDefined();

    await act(async () => {
      pendingA.resolve([eventA]);
    });

    // The late case A response fills only its own key and never renders under B.
    expect(queryClient.getQueryData(['timeline', 'case-a'])).toEqual([eventA]);
    const eventBCache = queryClient.getQueryData<TimelineEvent[]>(['timeline', 'case-b']);
    expect(eventBCache?.map((event) => event.id)).toEqual(['event-b']);
    expect(screen.getByText('Event from B')).toBeDefined();
    expect(screen.queryByText('Event from A')).toBeNull();
  });

  it('keeps data and keyboard focus across a background refetch', async () => {
    apiMocks.getTimelineForCase.mockResolvedValue([makeEvent('event-1'), makeEvent('event-2')]);

    const { container, queryClient } = renderMap('case-1');

    expect(await screen.findByText('Event event-1')).toBeDefined();

    const markers = container.querySelectorAll('.map-marker');
    expect(markers).toHaveLength(2);
    const focusedMarker = markers[1] as HTMLElement;
    focusedMarker.focus();
    expect(document.activeElement).toBe(focusedMarker);

    apiMocks.getTimelineForCase.mockResolvedValue([makeEvent('event-1'), makeEvent('event-2')]);
    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ['timeline', 'case-1'] });
    });

    // The refetch replaced data only: same markers, same focused element.
    expect(screen.getByText('Event event-1')).toBeDefined();
    expect(container.querySelectorAll('.map-marker')).toHaveLength(2);
    expect(document.activeElement).toBe(focusedMarker);
    expect(container.contains(focusedMarker)).toBe(true);
    expect(apiMocks.getTimelineForCase).toHaveBeenCalledTimes(2);
  });
});

describe('MapTab recorded geography', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('plots only recorded coordinates and lists invalid/missing as distinct states', async () => {
    apiMocks.getTimelineForCase.mockResolvedValue([
      makeEvent('recorded', { locationLat: 51.5, locationLon: -0.1 }),
      makeEvent('boundary', { locationLat: 90, locationLon: 180 }),
      makeEvent('out-of-range', { locationLat: 91, locationLon: 0 }),
      makeEvent('non-finite', { locationLat: Number.NaN, locationLon: 0 }),
      makeEvent('absent', { locationLat: null, locationLon: null }),
    ]);

    const { container } = renderMap('case-1');

    expect(await screen.findByText('Event recorded')).toBeDefined();

    // Only the two recorded pairs produce markers.
    const markerIds = Array.from(container.querySelectorAll('.map-marker')).map((node) =>
      node.getAttribute('data-event-id')
    );
    expect(markerIds).toEqual(['recorded', 'boundary']);
    expect(screen.getByText('2 mapped')).toBeDefined();

    // Invalid and missing are both visible, and distinguishable from each other.
    expect(screen.getByText('3 events not plotted')).toBeDefined();
    const invalidRows = container.querySelectorAll('[data-coordinate-state="invalid"]');
    const missingRows = container.querySelectorAll('[data-coordinate-state="missing"]');
    expect(invalidRows).toHaveLength(2);
    expect(missingRows).toHaveLength(1);
    expect(screen.getAllByText('Invalid coordinates')).toHaveLength(2);
    expect(screen.getByText('No recorded coordinates')).toBeDefined();
  });

  it('plots a stored 0,0 event as recorded, not as unknown', async () => {
    apiMocks.getTimelineForCase.mockResolvedValue([
      makeEvent('null-island', { locationLat: 0, locationLon: 0 }),
    ]);

    const { container } = renderMap('case-1');

    expect(await screen.findByText('Event null-island')).toBeDefined();
    const markers = container.querySelectorAll('.map-marker');
    expect(markers).toHaveLength(1);

    const marker = markers[0] as HTMLElement;
    expect(marker.style.left).toBe('50%');
    expect(marker.style.top).toBe('50%');
    expect(marker.getAttribute('aria-label')).toContain('at 0, 0');
    expect(screen.getByText('1 mapped')).toBeDefined();
    expect(screen.queryByText('No recorded coordinates')).toBeNull();
    expect(container.querySelector('[data-state="empty"]')).toBeNull();
  });

  it('selects from the list to the marker and back using recorded ids only', async () => {
    apiMocks.getTimelineForCase.mockResolvedValue([
      makeEvent('alpha', { title: 'Event alpha' }),
      makeEvent('beta', { title: 'Event beta' }),
      makeEvent('gamma-unplottable', { locationLat: 120, locationLon: 0 }),
    ]);

    const { container } = renderMap('case-1');

    await screen.findByText('Event alpha');

    const marker = container.querySelector('[data-event-id="alpha"].map-marker') as HTMLElement;
    const row = container.querySelector('[data-event-id="alpha"].map-event-select') as HTMLElement;
    expect(marker).not.toBeNull();
    expect(row).not.toBeNull();
    expect(marker.getAttribute('aria-pressed')).toBe('false');

    // List row -> marker.
    fireEvent.click(row);
    expect(marker.getAttribute('aria-pressed')).toBe('true');
    expect(marker.classList.contains('map-marker--selected')).toBe(true);
    expect(document.activeElement).toBe(marker);

    // Marker -> list row.
    const betaMarker = container.querySelector('[data-event-id="beta"].map-marker') as HTMLElement;
    fireEvent.click(betaMarker);
    const betaRow = container.querySelector('[data-event-id="beta"].map-event-select') as HTMLElement;
    expect(betaRow.getAttribute('aria-pressed')).toBe('true');
    expect(marker.getAttribute('aria-pressed')).toBe('false');
    expect(document.activeElement).toBe(betaRow);

    // An unplottable event has no marker and no selection control at all.
    expect(container.querySelector('[data-event-id="gamma-unplottable"].map-marker')).toBeNull();
    expect(container.querySelector('[data-event-id="gamma-unplottable"].map-event-select')).toBeNull();
  });

  it('links each event to event context instead of an invented claim inspector id', async () => {
    apiMocks.getTimelineForCase.mockResolvedValue([
      makeEvent('alpha', { title: 'Event alpha' }),
      makeEvent('gamma-unplottable', { locationLat: 120, locationLon: 0 }),
    ]);

    renderMap('case-1');

    await screen.findByText('Event alpha');

    const links = screen.getAllByRole('link', { name: 'Open event context' });
    expect(links.length).toBeGreaterThanOrEqual(2);
    for (const link of links) {
      const href = link.getAttribute('href') ?? '';
      expect(href).toBe('/cases/case-1/timeline');
      // Never a fabricated inspector selector.
      expect(href).not.toContain('claim=');
      expect(href).not.toContain('evidence=');
    }
  });

  it('renders the shared map-empty state when nothing is plottable', async () => {
    apiMocks.getTimelineForCase.mockResolvedValue([
      makeEvent('invalid', { locationLat: 200, locationLon: 0 }),
      makeEvent('missing', { locationLat: null, locationLon: null }),
    ]);

    const { container } = renderMap('case-1');

    expect(
      await screen.findByText('No geotagged events are available for this case yet.')
    ).toBeDefined();
    const empty = container.querySelector('[data-state="empty"]');
    expect(empty).not.toBeNull();
    expect(empty?.classList.contains('map-empty')).toBe(true);
    expect(container.querySelector('[data-state="loading"]')).toBeNull();
    expect(container.querySelector('[data-state="network-error"]')).toBeNull();

    // Nothing recorded is dropped: both unplottable events stay listed.
    expect(screen.getByText('2 events not plotted')).toBeDefined();
  });
});
