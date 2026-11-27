import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import TimelineTab from './TimelineTab';
import type { TimelineEvent, VerificationStatus } from '../../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getTimelineForCase: vi.fn(),
}));

vi.mock('../../services/api', () => apiMocks);

const makeEvent = (id: string, status: VerificationStatus): TimelineEvent => ({
  id,
  timestamp: '2026-03-19T10:00:00Z',
  title: `Event ${id}`,
  summary: 'Recorded event summary',
  verificationStatus: status,
  linkedEvidenceCount: 1,
});

// The label a reader sees, the dot marker and the badge must all describe the
// same recorded status.
const recordedStatuses: Array<{
  status: VerificationStatus;
  label: string;
  dotClass: string;
}> = [
  { status: 'confirmed', label: 'Confirmed', dotClass: 'dot-success' },
  { status: 'probable', label: 'Probable', dotClass: 'dot-info' },
  { status: 'alleged', label: 'Alleged', dotClass: 'dot-warning' },
  { status: 'contested', label: 'Contested', dotClass: 'dot-warning' },
  { status: 'debunked', label: 'Debunked', dotClass: 'dot-danger' },
  { status: 'unknown', label: 'Unknown', dotClass: 'dot-neutral' },
];

// The reader is query-backed, so each render gets its own client. The
// assertions below are unchanged from the effect-based version.
const renderTimeline = (caseId: string) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TimelineTab caseId={caseId} />
    </QueryClientProvider>
  );

const dotForLabel = (label: string): HTMLElement => {
  const item = screen.getByText(label).closest('.timeline-item');
  expect(item).not.toBeNull();
  const dot = item?.querySelector('.timeline-dot');
  expect(dot).not.toBeNull();
  return dot as HTMLElement;
};

describe('TimelineTab recorded verification status', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders each recorded status honestly and only confirmed as Confirmed', async () => {
    apiMocks.getTimelineForCase.mockResolvedValue(
      recordedStatuses.map(({ status }, index) => makeEvent(`event-${index}`, status))
    );

    renderTimeline('case-1');

    await screen.findByText('Confirmed');

    for (const { label, dotClass } of recordedStatuses) {
      expect(screen.getByText(label)).toBeDefined();
      const dot = dotForLabel(label);
      expect(dot.className).toContain(dotClass);
      if (label !== 'Confirmed') {
        expect(dot.className).not.toContain('dot-success');
      }
    }

    // Exactly one recorded status is allowed to claim confirmation.
    expect(screen.getAllByText('Confirmed')).toHaveLength(1);
    expect(screen.queryByText('Unrecognized status')).toBeNull();
  });

  it('does not promote an unexpected status value to Confirmed', async () => {
    apiMocks.getTimelineForCase.mockResolvedValue([
      makeEvent('event-x', 'not-a-recorded-status' as VerificationStatus),
      makeEvent('event-y', 'constructor' as VerificationStatus),
    ]);

    renderTimeline('case-1');

    expect(await screen.findAllByText('Unrecognized status')).toHaveLength(2);
    expect(screen.queryByText('Confirmed')).toBeNull();
    expect(screen.queryByText('Unknown')).toBeNull();

    for (const label of screen.getAllByText('Unrecognized status')) {
      const dot = label.closest('.timeline-item')?.querySelector('.timeline-dot');
      expect(dot?.className).toContain('dot-neutral');
      expect(dot?.className).not.toContain('dot-success');
    }
  });
});

describe('TimelineTab unrecognized status and unknown dates', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('keeps the raw stored status value beside Unrecognized status', async () => {
    apiMocks.getTimelineForCase.mockResolvedValue([
      makeEvent('event-raw', 'not-a-recorded-status' as VerificationStatus),
    ]);

    const { container } = renderTimeline('case-1');

    expect(await screen.findByText('Unrecognized status')).toBeDefined();
    // The raw value is preserved verbatim, never coerced to Unknown.
    const raw = container.querySelector('.timeline-status-raw');
    expect(raw).not.toBeNull();
    expect(raw?.textContent).toContain('not-a-recorded-status');
    expect(screen.queryByText('Unknown')).toBeNull();
    // Exactly the six recorded statuses are recognized.
    expect(screen.queryByText('Confirmed')).toBeNull();
    expect(screen.queryByText('Probable')).toBeNull();
  });

  it('shows the recorded raw value when the API reports an unmapped status as unknown', async () => {
    apiMocks.getTimelineForCase.mockResolvedValue([
      {
        ...makeEvent('event-legacy', 'unknown'),
        rawVerificationStatus: 'LEGACY_UNREVIEWED',
      },
    ]);

    const { container } = renderTimeline('case-1');

    // The field maps to `unknown`, but the raw stored text must not be hidden
    // behind a plain "Unknown" label.
    expect(await screen.findByText('Unrecognized status')).toBeDefined();
    const raw = container.querySelector('.timeline-status-raw');
    expect(raw?.textContent).toContain('LEGACY_UNREVIEWED');
    expect(screen.queryByText('Unknown')).toBeNull();
  });

  it('does not coerce an inherited object key into a recognized status', async () => {
    apiMocks.getTimelineForCase.mockResolvedValue([
      makeEvent('event-proto', 'toString' as VerificationStatus),
      makeEvent('event-empty', '' as VerificationStatus),
    ]);

    const { container } = renderTimeline('case-1');

    expect(await screen.findAllByText('Unrecognized status')).toHaveLength(2);
    const rawValues = Array.from(container.querySelectorAll('.timeline-status-raw')).map(
      (node) => node.textContent
    );
    expect(rawValues.some((text) => text?.includes('toString'))).toBe(true);
    expect(screen.queryByText('Unknown')).toBeNull();
  });

  it('shows a dateless event as "Date not recorded" without an epoch placeholder', async () => {
    apiMocks.getTimelineForCase.mockResolvedValue([
      { ...makeEvent('event-dated', 'confirmed'), timestamp: '2026-03-19T10:00:00Z' },
      { ...makeEvent('event-undated', 'probable'), timestamp: null },
      { ...makeEvent('event-bad-date', 'alleged'), timestamp: 'not-a-date' },
    ]);

    const { container } = renderTimeline('case-1');

    await screen.findByText('Event event-undated');

    const dateCells = Array.from(container.querySelectorAll('.timeline-date'));
    expect(dateCells).toHaveLength(3);
    expect(dateCells[0].textContent).toContain('2026-03-19');
    expect(dateCells[1].textContent).toBe('Date not recorded');
    expect(dateCells[2].textContent).toBe('Date not recorded');
    expect(dateCells[1].getAttribute('data-date-state')).toBe('unknown');

    const rendered = container.textContent ?? '';
    expect(rendered).not.toContain('1970');
    expect(rendered).not.toContain('Invalid Date');
    expect(rendered).not.toContain('NaN');
  });

  it('keeps date-unknown independent from status-unknown', async () => {
    apiMocks.getTimelineForCase.mockResolvedValue([
      { ...makeEvent('event-1', 'confirmed'), timestamp: null },
      { ...makeEvent('event-2', 'unknown'), timestamp: '2026-03-19T10:00:00Z' },
    ]);

    const { container } = renderTimeline('case-1');

    await screen.findByText('Event event-1');

    const items = Array.from(container.querySelectorAll('.timeline-item'));
    expect(items).toHaveLength(2);
    // Undated but confirmed.
    expect(items[0].querySelector('.timeline-date')?.textContent).toBe('Date not recorded');
    expect(items[0].textContent).toContain('Confirmed');
    // Dated but unknown status.
    expect(items[1].querySelector('.timeline-date')?.textContent).toContain('2026-03-19');
    expect(items[1].textContent).toContain('Unknown');
  });
});
