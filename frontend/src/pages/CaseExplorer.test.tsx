import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
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
    expect(selects()).toHaveLength(3);

    fireEvent.change(selects()[0], { target: { value: 'investigating' } });
    expect(rowTitles()).toHaveLength(4);

    fireEvent.change(selects()[0], { target: { value: 'review ready' } });
    expect(screen.getByText('No cases found')).toBeDefined();
    // Filtering never triggers a per-case read.
    expect(apiMocks.getCaseDetail).not.toHaveBeenCalled();
  });
});
