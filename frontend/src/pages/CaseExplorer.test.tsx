import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import CaseExplorer from './CaseExplorer';
import type { TopicCase } from '../types/backend-models';

const apiMocks = vi.hoisted(() => ({
  getCases: vi.fn(),
  getCaseDetail: vi.fn(),
}));

vi.mock('../services/api', () => apiMocks);

const makeCase = (overrides: Partial<TopicCase> & Pick<TopicCase, 'id' | 'query'>): TopicCase => ({
  conflictDomain: 'Water',
  status: 'investigating',
  stage: 'INVESTIGATE',
  counts: { articles: 0, events: 0, reviewItems: 0 },
  automationMode: 'safe',
  hasNewMaterial: false,
  openExceptionsCount: 0,
  lastUpdated: '2026-03-19T10:00:00Z',
  ...overrides,
});

// Scrambled payload order: the rendered order must come from recorded counts.
const cases: TopicCase[] = [
  makeCase({ id: 'case-c3', query: 'Tie break case-c3' }),
  makeCase({
    id: 'case-c1',
    query: 'Two open exceptions',
    conflictDomain: 'Labour',
    openExceptionsCount: 2,
    counts: { articles: 4, events: 3, reviewItems: 1 },
  }),
  makeCase({ id: 'case-c2', query: 'Fresh material recorded', hasNewMaterial: true }),
  makeCase({ id: 'case-c4', query: 'Tie break case-c4' }),
];

const rowTitles = () =>
  Array.from(document.querySelectorAll('.case-query')).map((el) => el.textContent);

const pager = () => screen.queryByRole('navigation', { name: 'Case pagination' });

const statValue = (label: string): string | undefined => {
  const item = Array.from(document.querySelectorAll('.stat-item')).find(
    (el) => el.querySelector('.stat-label')?.textContent === label
  );
  return item?.querySelector('.stat-value')?.textContent ?? undefined;
};

const checkboxFor = (query: string): HTMLInputElement => {
  const card = Array.from(document.querySelectorAll('.case-card')).find(
    (el) => el.querySelector('.case-query')?.textContent === query
  );
  const input = card?.querySelector('input[type="checkbox"]');
  if (!input) throw new Error(`no checkbox for ${query}`);
  return input as HTMLInputElement;
};

const openFilters = () => fireEvent.click(screen.getByRole('button', { name: /Filters/i }));

const sortSelect = () => screen.getByLabelText('Sort') as HTMLSelectElement;

function renderExplorer() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CaseExplorer />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('CaseExplorer — list DTO rows, no fan-out', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getCases.mockResolvedValue(cases);
  });

  it('renders rows from the one list read and issues no per-case detail request', async () => {
    renderExplorer();

    expect(await screen.findByText('Two open exceptions')).toBeDefined();
    expect(apiMocks.getCases).toHaveBeenCalledTimes(1);
    expect(apiMocks.getCaseDetail).not.toHaveBeenCalled();
    expect(rowTitles()).toHaveLength(4);
  });

  it('orders rows by recorded exceptions, new material and counts with an id tie-break', async () => {
    renderExplorer();
    await screen.findByText('Two open exceptions');

    expect(rowTitles()).toEqual([
      'Two open exceptions',
      'Fresh material recorded',
      'Tie break case-c3',
      'Tie break case-c4',
    ]);
  });

  it('shows recorded counts plus exception and new-material indicators as text', async () => {
    renderExplorer();
    await screen.findByText('Two open exceptions');

    expect(screen.getByText('2 open exceptions recorded')).toBeDefined();
    expect(screen.getAllByText('0 open exceptions recorded')).toHaveLength(3);
    expect(screen.getByText('New material recorded')).toBeDefined();
    expect(screen.getAllByText('No new material recorded')).toHaveLength(3);
    // Recorded counts from the list DTO are printed for every row.
    const metricTitles = Array.from(document.querySelectorAll('.case-metric')).map((el) =>
      el.getAttribute('title')
    );
    expect(metricTitles).toContain('Articles');
    expect(metricTitles).toContain('Events');
    expect(metricTitles).toContain('Recorded review items');
    expect(document.querySelectorAll('.case-metric').length).toBe(12);
  });

  it('labels the client fetch time separately from recorded timestamps', async () => {
    renderExplorer();
    await screen.findByText('Two open exceptions');

    const fetched = screen.getByTestId('explorer-last-fetched');
    expect(fetched.textContent).toContain('Last fetched');
    expect(fetched.textContent).toContain('client request time');
  });

  it('does not offer bulk actions the read API cannot perform', async () => {
    renderExplorer();
    await screen.findByText('Two open exceptions');

    fireEvent.click(document.querySelector('.case-checkbox input') as HTMLInputElement);
    const batch = screen.getByRole('button', { name: /CLI Only/i }) as HTMLButtonElement;
    const exportButton = screen.getByRole('button', { name: 'Export' }) as HTMLButtonElement;

    expect(batch.disabled).toBe(true);
    expect(batch.getAttribute('title')).toMatch(/CLI-only/i);
    expect(exportButton.disabled).toBe(true);
    expect(exportButton.getAttribute('title')).toMatch(/no download/i);
    expect(apiMocks.getCaseDetail).not.toHaveBeenCalled();
  });

  it('keeps the existing search and status filters working', async () => {
    renderExplorer();
    await screen.findByText('Two open exceptions');

    fireEvent.change(screen.getByPlaceholderText('Search queries or domains...'), {
      target: { value: 'labour' },
    });
    expect(rowTitles()).toEqual(['Two open exceptions']);

    fireEvent.change(screen.getByPlaceholderText('Search queries or domains...'), {
      target: { value: '' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Filters/i }));
    const selects = () =>
      Array.from(document.querySelectorAll('select.filter-select')) as HTMLSelectElement[];
    // The three filters only: sort is a toolbar control, not a filter.
    expect(selects()).toHaveLength(3);

    fireEvent.change(selects()[0], { target: { value: 'investigating' } });
    expect(rowTitles()).toHaveLength(4);

    fireEvent.change(selects()[0], { target: { value: 'review ready' } });
    expect(screen.getByText('No cases found')).toBeDefined();
    // Filtering never triggers a per-case read.
    expect(apiMocks.getCaseDetail).not.toHaveBeenCalled();
  });
});

// Priority, recorded timestamp and query are mutually distinct here, so each
// sort key produces a different, provable order.
const sortCases: TopicCase[] = [
  makeCase({
    id: 'case-s1',
    query: 'Bravo case',
    openExceptionsCount: 0,
    lastUpdated: '2026-03-25T10:00:00Z',
  }),
  makeCase({
    id: 'case-s2',
    query: 'Alpha case',
    openExceptionsCount: 2,
    lastUpdated: '2026-03-11T10:00:00Z',
  }),
  makeCase({
    id: 'case-s3',
    query: 'Charlie case',
    openExceptionsCount: 1,
    lastUpdated: null,
  }),
  makeCase({
    id: 'case-s4',
    query: 'Delta case',
    openExceptionsCount: 0,
    lastUpdated: '2026-03-15T10:00:00Z',
  }),
];

// Eleven rows: descending recorded exceptions pin the page membership, so page
// one is "Paged case 01"–"Paged case 10" and page two is "Paged case 11".
const pagedCases: TopicCase[] = Array.from({ length: 11 }, (_, index) => {
  const n = String(index + 1).padStart(2, '0');
  return makeCase({
    id: `case-p${n}`,
    query: `Paged case ${n}`,
    conflictDomain: 'Water',
    status: index < 2 ? 'review ready' : 'investigating',
    openExceptionsCount: 11 - index,
    lastUpdated: `2026-03-${n}T10:00:00Z`,
  });
});

describe('CaseExplorer — sort', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getCases.mockResolvedValue(sortCases);
  });

  it('offers exactly three orderings with priority as the default', async () => {
    renderExplorer();
    await screen.findByText('Alpha case');
    openFilters();

    const options = Array.from(sortSelect().options).map((option) => option.value);
    expect(options).toEqual(['priority', 'updated', 'name']);
    expect(sortSelect().value).toBe('priority');
    // The label is programmatically associated, not just adjacent text.
    expect(screen.getByLabelText('Sort')).toBe(sortSelect());
  });

  it('orders by recorded priority, then by the most recent update, then by name', async () => {
    renderExplorer();
    await screen.findByText('Alpha case');
    openFilters();

    expect(rowTitles()).toEqual(['Alpha case', 'Charlie case', 'Bravo case', 'Delta case']);

    fireEvent.change(sortSelect(), { target: { value: 'updated' } });
    expect(rowTitles()).toEqual(['Bravo case', 'Delta case', 'Alpha case', 'Charlie case']);

    fireEvent.change(sortSelect(), { target: { value: 'name' } });
    expect(rowTitles()).toEqual(['Alpha case', 'Bravo case', 'Charlie case', 'Delta case']);

    fireEvent.change(sortSelect(), { target: { value: 'priority' } });
    expect(rowTitles()).toEqual(['Alpha case', 'Charlie case', 'Bravo case', 'Delta case']);
  });

  it('sorts rows without a recorded timestamp last under the updated key', async () => {
    renderExplorer();
    await screen.findByText('Alpha case');
    openFilters();

    fireEvent.change(sortSelect(), { target: { value: 'updated' } });

    const titles = rowTitles();
    expect(titles[titles.length - 1]).toBe('Charlie case');
    expect(titles).toHaveLength(4);
  });
});

describe('CaseExplorer — pagination', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getCases.mockResolvedValue(pagedCases);
  });

  it('shows ten rows, the visible range and disabled bounds on the first page', async () => {
    renderExplorer();
    await screen.findByText('Paged case 01');

    expect(rowTitles()).toHaveLength(10);
    const nav = pager();
    expect(nav).not.toBeNull();
    expect(within(nav as HTMLElement).getByText('Showing 1–10 of 11 cases')).toBeDefined();

    const previous = within(nav as HTMLElement).getByRole('button', {
      name: 'Previous',
    }) as HTMLButtonElement;
    const next = within(nav as HTMLElement).getByRole('button', {
      name: 'Next',
    }) as HTMLButtonElement;
    expect(previous.disabled).toBe(true);
    expect(next.disabled).toBe(false);
  });

  it('advances to the last row and returns without losing the page contract', async () => {
    renderExplorer();
    await screen.findByText('Paged case 01');
    const nav = pager() as HTMLElement;

    fireEvent.click(within(nav).getByRole('button', { name: 'Next' }));
    expect(rowTitles()).toEqual(['Paged case 11']);
    expect(within(nav).getByText('Showing 11–11 of 11 cases')).toBeDefined();
    const next = within(nav).getByRole('button', { name: 'Next' }) as HTMLButtonElement;
    const previous = within(nav).getByRole('button', { name: 'Previous' }) as HTMLButtonElement;
    expect(next.disabled).toBe(true);
    expect(previous.disabled).toBe(false);

    fireEvent.click(previous);
    expect(rowTitles()).toHaveLength(10);
    expect(rowTitles()[9]).toBe('Paged case 10');
    expect(screen.queryByText('Paged case 11')).toBeNull();
  });

  it('renders no pager chrome when every case fits on one page', async () => {
    apiMocks.getCases.mockResolvedValue(pagedCases.slice(0, 10));
    renderExplorer();
    await screen.findByText('Paged case 01');

    expect(rowTitles()).toHaveLength(10);
    expect(pager()).toBeNull();
    expect(document.querySelector('.explorer-pagination')).toBeNull();
    expect(screen.queryByText(/Showing /)).toBeNull();
  });

  it('keeps summary counts on the full filtered set while paging', async () => {
    renderExplorer();
    await screen.findByText('Paged case 01');

    expect(statValue('Total')).toBe('11');
    expect(statValue('Active')).toBe('11');
    expect(statValue('Review Ready')).toBe('2');
    expect(statValue('Open Exceptions')).toBe('11');

    fireEvent.click(within(pager() as HTMLElement).getByRole('button', { name: 'Next' }));

    // Only one row is on screen, yet the summary still describes all 11 cases.
    expect(rowTitles()).toHaveLength(1);
    expect(statValue('Total')).toBe('11');
    expect(statValue('Active')).toBe('11');
    expect(statValue('Review Ready')).toBe('2');
    expect(statValue('Open Exceptions')).toBe('11');
  });

  it('returns to the first page when the sort changes', async () => {
    renderExplorer();
    await screen.findByText('Paged case 01');
    openFilters();
    fireEvent.click(within(pager() as HTMLElement).getByRole('button', { name: 'Next' }));
    expect(rowTitles()).toEqual(['Paged case 11']);

    fireEvent.change(sortSelect(), { target: { value: 'name' } });
    expect(rowTitles()).toHaveLength(10);
    expect(within(pager() as HTMLElement).getByText('Showing 1–10 of 11 cases')).toBeDefined();
  });

  it('returns to the first page when the search or a filter changes', async () => {
    renderExplorer();
    await screen.findByText('Paged case 01');
    openFilters();

    const statusSelect = () =>
      Array.from(document.querySelectorAll('select.filter-select'))[0] as HTMLSelectElement;

    fireEvent.click(within(pager() as HTMLElement).getByRole('button', { name: 'Next' }));
    expect(rowTitles()).toEqual(['Paged case 11']);

    // Nine rows survive this filter, so the pager goes away and page one returns.
    fireEvent.change(statusSelect(), { target: { value: 'investigating' } });
    expect(rowTitles()).toHaveLength(9);
    expect(pager()).toBeNull();

    fireEvent.change(statusSelect(), { target: { value: 'all' } });
    fireEvent.click(within(pager() as HTMLElement).getByRole('button', { name: 'Next' }));
    expect(rowTitles()).toEqual(['Paged case 11']);

    // A search term that still matches every row must also restart at page one.
    fireEvent.change(screen.getByPlaceholderText('Search queries or domains...'), {
      target: { value: 'water' },
    });
    expect(within(pager() as HTMLElement).getByText('Showing 1–10 of 11 cases')).toBeDefined();
  });

  it('clamps the page when the filtered set shrinks instead of rendering an empty grid', async () => {
    renderExplorer();
    await screen.findByText('Paged case 01');
    fireEvent.click(within(pager() as HTMLElement).getByRole('button', { name: 'Next' }));
    expect(rowTitles()).toEqual(['Paged case 11']);

    // The server now reports fewer cases: no control changes the page, so only
    // the derived clamp can keep the grid non-empty.
    apiMocks.getCases.mockResolvedValue(pagedCases.slice(0, 3));
    fireEvent.click(screen.getByRole('button', { name: /Refresh/i }));

    await waitFor(() => expect(rowTitles()).toHaveLength(3));
    expect(screen.queryByText('No cases found')).toBeNull();
    expect(pager()).toBeNull();
    expect(rowTitles()).toEqual(['Paged case 01', 'Paged case 02', 'Paged case 03']);
  });

  it('keeps a selection made on page one when paging to page two', async () => {
    renderExplorer();
    await screen.findByText('Paged case 01');

    fireEvent.click(checkboxFor('Paged case 02'));
    expect(screen.getByRole('button', { name: /CLI Only \(1\)/ })).toBeDefined();

    fireEvent.click(within(pager() as HTMLElement).getByRole('button', { name: 'Next' }));
    expect(rowTitles()).toEqual(['Paged case 11']);
    expect(screen.getByRole('button', { name: /CLI Only \(1\)/ })).toBeDefined();

    fireEvent.click(within(pager() as HTMLElement).getByRole('button', { name: 'Previous' }));
    expect(checkboxFor('Paged case 02').checked).toBe(true);
    expect(checkboxFor('Paged case 01').checked).toBe(false);
  });
});
