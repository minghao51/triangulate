import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import SearchTab from './SearchTab';
import { ApiError } from '../../services/api-error';
import type { CaseSearchResponse } from '../../types/backend-models';

const apiMocks = vi.hoisted(() => ({ getCaseSearch: vi.fn() }));
vi.mock('../../services/api', () => apiMocks);

const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
};

function response(overrides: Partial<CaseSearchResponse> = {}): CaseSearchResponse {
  return {
    caseId: 'case-1', query: 'term', total: 1, limit: 25, offset: 0,
    appliedFilters: { type: null, publisher: null, status: null, publishedFrom: null, publishedTo: null },
    items: [{
      resultType: 'evidence', id: 'ev-1', claimId: null, evidenceId: 'ev-1',
      eventId: null, captureId: null, title: null, snippet: 'Found term',
      matchedField: 'body', publisher: null, status: null, publishedAt: null,
    }],
    ...overrides,
  };
}

function renderSearch(entry = '/cases/case-1/search') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/cases/:id/search" element={<><LocationProbe /><SearchTab caseId="case-1" /></>} />
          <Route path="/cases/:id/evidence" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('SearchTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getCaseSearch.mockResolvedValue(response());
  });

  it('derives all request parameters from URL state', async () => {
    renderSearch('/cases/case-1/search?q=term&type=claim&publisher=wire&status=probable&publishedFrom=2026-01-01T00%3A00%3A00.000Z&publishedTo=2026-02-01T00%3A00%3A00.000Z&offset=25');
    await screen.findByText('Found term');
    expect(apiMocks.getCaseSearch).toHaveBeenCalledWith('case-1', {
      q: 'term', type: 'claim', publisher: 'wire', status: 'probable',
      publishedFrom: '2026-01-01T00:00:00.000Z', publishedTo: '2026-02-01T00:00:00.000Z',
      limit: 25, offset: 25,
    });
  });

  it('submits a trimmed query into the URL', async () => {
    renderSearch();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search terms' }), { target: { value: '  new term  ' } });
    fireEvent.submit(screen.getByRole('search'));
    await waitFor(() => expect(screen.getByTestId('location').textContent).toContain('?q=new%20term'));
    await waitFor(() => expect(apiMocks.getCaseSearch).toHaveBeenCalledWith('case-1', expect.objectContaining({ q: 'new term', offset: 0 })));
  });

  it('loads a deep link with filters and offset', async () => {
    renderSearch('/cases/case-1/search?q=term&type=evidence&publisher=AP&offset=50');
    await screen.findByText('Found term');
    expect(apiMocks.getCaseSearch).toHaveBeenCalledWith('case-1', {
      q: 'term', type: 'evidence', publisher: 'AP', status: null,
      publishedFrom: null, publishedTo: null, limit: 25, offset: 50,
    });
  });

  it('resets pagination when a filter changes', async () => {
    apiMocks.getCaseSearch.mockResolvedValue(response({ total: 100, offset: 25 }));
    renderSearch('/cases/case-1/search?q=term&offset=25');
    await screen.findByText('Found term');
    fireEvent.change(screen.getByLabelText('Result type'), { target: { value: 'claim' } });
    await waitFor(() => expect(screen.getByTestId('location').textContent).toContain('type=claim'));
    expect(screen.getByTestId('location').textContent).not.toContain('offset=25');
    await waitFor(() => expect(apiMocks.getCaseSearch).toHaveBeenLastCalledWith('case-1', expect.objectContaining({ type: 'claim', offset: 0 })));
  });

  it('does not issue a request for an empty query and shows the idle prompt', () => {
    renderSearch('/cases/case-1/search?q=%20%20');
    expect(screen.getByRole('status').textContent).toMatch(/enter a search query/i);
    expect(apiMocks.getCaseSearch).not.toHaveBeenCalled();
  });

  it('shows a valid empty result separately', async () => {
    apiMocks.getCaseSearch.mockResolvedValue(response({ total: 0, items: [] }));
    renderSearch('/cases/case-1/search?q=none');
    expect(await screen.findByText(/No matches for this query/)).toBeTruthy();
  });

  it('shows 503 remedy and retries the search', async () => {
    apiMocks.getCaseSearch.mockRejectedValueOnce(new ApiError('FTS5 index is unavailable', 503));
    renderSearch('/cases/case-1/search?q=term');
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('triangulate case rebuild-search case-1');
    apiMocks.getCaseSearch.mockResolvedValueOnce(response());
    fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('Found term')).toBeTruthy();
    expect(apiMocks.getCaseSearch).toHaveBeenCalledTimes(2);
  });

  it('renders a 422 validation message', async () => {
    apiMocks.getCaseSearch.mockRejectedValue(new ApiError('Invalid publication date range', 422));
    renderSearch('/cases/case-1/search?q=term');
    expect((await screen.findByRole('alert')).textContent).toContain('Invalid publication date range');
  });

  it('renders the case-scoped 404 state', async () => {
    apiMocks.getCaseSearch.mockRejectedValue(new ApiError('Case was not found', 404));
    renderSearch('/cases/case-1/search?q=term');
    expect((await screen.findByRole('alert')).textContent).toContain('No results from another case');
  });

  it('renders snippets containing script tags as literal text', async () => {
    apiMocks.getCaseSearch.mockResolvedValue(response({ items: [{
      resultType: 'evidence', id: 'ev-1', claimId: null, evidenceId: 'ev-1', eventId: null,
      captureId: null, title: null, snippet: '<script>alert(1)</script>', matchedField: 'body',
      publisher: null, status: null, publishedAt: null,
    }] }));
    renderSearch('/cases/case-1/search?q=term');
    const snippet = await screen.findByText('<script>alert(1)</script>');
    expect(snippet.tagName.toLowerCase()).not.toBe('script');
    expect(document.querySelector('script')).toBeNull();
  });

  it('paginates using total, limit, and offset', async () => {
    apiMocks.getCaseSearch.mockResolvedValue(response({ total: 51, limit: 25, offset: 25 }));
    renderSearch('/cases/case-1/search?q=term&offset=25');
    await screen.findByText('Found term');
    expect(screen.getByText('Showing 26–26 of 51')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(screen.getByTestId('location').textContent).toContain('offset=50'));
    fireEvent.click(await screen.findByRole('button', { name: 'Previous' }));
    await waitFor(() => expect(screen.getByTestId('location').textContent).toContain('offset=25'));
    fireEvent.click(await screen.findByRole('button', { name: 'Previous' }));
    await waitFor(() => expect(screen.getByTestId('location').textContent).not.toContain('offset='));
  });

  it('submits from the keyboard and performs no mutation calls', async () => {
    renderSearch();
    const input = screen.getByRole('searchbox', { name: 'Search terms' });
    fireEvent.change(input, { target: { value: 'keyboard' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter', charCode: 13 });
    fireEvent.submit(screen.getByRole('search'));
    await waitFor(() => expect(screen.getByTestId('location').textContent).toContain('q=keyboard'));
    expect(apiMocks.getCaseSearch).toHaveBeenCalledWith('case-1', expect.objectContaining({ q: 'keyboard' }));
    expect(Object.keys(apiMocks)).toEqual(['getCaseSearch']);
  });
});
