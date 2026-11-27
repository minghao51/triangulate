import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';

import SearchTab from './SearchTab';
import { ApiError } from '../../services/api-error';
import { SAVED_VIEWS_STORAGE_KEY } from '../../services/saved-views';
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
    window.localStorage.removeItem(SAVED_VIEWS_STORAGE_KEY);
    window.localStorage.removeItem('other.feature');
  });

  it('derives all request parameters from URL state', async () => {
    renderSearch('/cases/case-1/search?q=term&type=claim&publisher=wire&status=probable&publishedFrom=2026-01-01T00%3A00%3A00.000Z&publishedTo=2026-02-01T00%3A00%3A00.000Z&offset=25');
    await screen.findByText('Found term');
    expect(apiMocks.getCaseSearch).toHaveBeenCalledWith('case-1', {
      q: 'term', type: 'claim', publisher: null, status: 'probable',
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

  it('does not change an existing search or request when submitting a blank draft', async () => {
    renderSearch('/cases/case-1/search?q=term');
    await screen.findByText('Found term');
    const originalLocation = screen.getByTestId('location').textContent;
    const input = screen.getByRole('searchbox', { name: 'Search terms' });
    fireEvent.change(input, { target: { value: '   ' } });
    fireEvent.submit(screen.getByRole('search'));
    expect(screen.getByTestId('location').textContent).toBe(originalLocation);
    expect(document.activeElement).toBe(input);
    expect(screen.getByText('Found term')).toBeTruthy();
    expect(apiMocks.getCaseSearch).toHaveBeenCalledTimes(1);
  });

  it('loads a deep link with filters and offset', async () => {
    renderSearch('/cases/case-1/search?q=term&type=evidence&publisher=AP&offset=50');
    await screen.findByText('Found term');
    expect(apiMocks.getCaseSearch).toHaveBeenCalledWith('case-1', {
      q: 'term', type: 'evidence', publisher: 'AP', status: null,
      publishedFrom: null, publishedTo: null, limit: 25, offset: 50,
    });
  });

  it('disables conflicting filters and clears publisher when status is selected', async () => {
    renderSearch('/cases/case-1/search?q=term&publisher=AP');
    await screen.findByText('Found term');
    fireEvent.change(screen.getByLabelText('Claim status'), { target: { value: 'probable' } });
    await waitFor(() => expect(screen.getByTestId('location').textContent).toContain('status=probable'));
    expect((screen.getByLabelText('Publisher') as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText('Publisher') as HTMLInputElement).value).toBe('');
    expect((screen.getByRole('option', { name: 'Evidence' }) as HTMLOptionElement).disabled).toBe(true);
    expect(screen.getByLabelText('Claim status').getAttribute('aria-describedby')).toBe('search-filter-hint');
    expect(screen.getByText('Status applies to claims; publisher applies to evidence.')).toBeTruthy();
  });

  it('disables claim and status filters when a publisher is entered', async () => {
    renderSearch('/cases/case-1/search?q=term');
    await screen.findByText('Found term');
    fireEvent.change(screen.getByLabelText('Publisher'), { target: { value: 'AP' } });
    await waitFor(() => expect(screen.getByTestId('location').textContent).toContain('publisher=AP'));
    expect((screen.getByLabelText('Claim status') as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByRole('option', { name: 'Claims' }) as HTMLOptionElement).disabled).toBe(true);
    expect(screen.getByLabelText('Publisher').getAttribute('aria-describedby')).toBe('search-filter-hint');
  });

  it('resolves conflicting deep links by keeping type/status and dropping publisher', async () => {
    renderSearch('/cases/case-1/search?q=term&type=claim&publisher=AP&status=probable');
    await screen.findByText('Found term');
    await waitFor(() => expect(screen.getByTestId('location').textContent).not.toContain('publisher='));
    expect(apiMocks.getCaseSearch).toHaveBeenCalledWith('case-1', expect.objectContaining({
      q: 'term', type: 'claim', publisher: null, status: 'probable',
    }));
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

  it('shows the loading state as busy', () => {
    apiMocks.getCaseSearch.mockReturnValue(new Promise(() => {}));
    renderSearch('/cases/case-1/search?q=term');
    expect(screen.getByText('Searching this case…').getAttribute('aria-busy')).toBe('true');
  });

  it('shows a generic error with retry distinct from special API errors', async () => {
    apiMocks.getCaseSearch.mockRejectedValue(new Error('Network unavailable'));
    renderSearch('/cases/case-1/search?q=term');
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByRole('heading', { name: 'Search failed' })).toBeTruthy();
    expect(alert.textContent).toContain('Network unavailable');
    expect(within(alert).getByRole('button', { name: 'Retry' })).toBeTruthy();
    expect(alert.textContent).not.toContain('Case not found');
    expect(alert.textContent).not.toContain('Search index unavailable');
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

  it('shows the partial final page range and disables Next', async () => {
    apiMocks.getCaseSearch.mockResolvedValue(response({ total: 51, limit: 25, offset: 50 }));
    renderSearch('/cases/case-1/search?q=term&offset=50');
    await screen.findByText('Found term');
    expect(screen.getByText('Showing 51–51 of 51')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Next' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('offers a reset when offset is beyond total and avoids an impossible range', async () => {
    apiMocks.getCaseSearch.mockResolvedValue(response({ total: 51, limit: 25, offset: 100 }));
    renderSearch('/cases/case-1/search?q=term&offset=100');
    await screen.findByText('Found term');
    expect(screen.getByText(/beyond the last result/)).toBeTruthy();
    expect(screen.queryByText(/Showing/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show first page' }));
    await waitFor(() => expect(screen.getByTestId('location').textContent).not.toContain('offset='));
  });

  it('normalizes offsets above the API maximum before requesting', async () => {
    renderSearch('/cases/case-1/search?q=term&offset=2147483648');
    await screen.findByText('Found term');
    expect(apiMocks.getCaseSearch).toHaveBeenCalledWith('case-1', expect.objectContaining({ offset: 0 }));
    await waitFor(() => expect(screen.getByTestId('location').textContent).not.toContain('offset='));
  });

  it('does not render a 0–0 range when total is zero', async () => {
    apiMocks.getCaseSearch.mockResolvedValue(response({ total: 0, items: [] }));
    renderSearch('/cases/case-1/search?q=none&offset=0');
    await screen.findByText(/No matches for this query/);
    expect(screen.queryByText(/Showing 0–0 of 0/)).toBeNull();
  });

  it('offers a permalink that pins the current query, filters and offset', async () => {
    apiMocks.getCaseSearch.mockResolvedValue(response({ total: 100, limit: 25, offset: 25 }));
    renderSearch('/cases/case-1/search?q=term&type=evidence&offset=25');
    await screen.findByText('Found term');

    const permalink = () => screen.getByRole('link', { name: 'Permalink for this selection' });
    expect(permalink().getAttribute('href')).toBe(
      '/cases/case-1/search?q=term&type=evidence&offset=25'
    );

    // The link follows the URL, so paging pins the new offset.
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() =>
      expect(permalink().getAttribute('href')).toBe(
        '/cases/case-1/search?q=term&type=evidence&offset=50'
      )
    );

    // A filter change resets paging and keeps the query in the link.
    fireEvent.change(screen.getByLabelText('Result type'), { target: { value: 'claim' } });
    await waitFor(() =>
      expect(permalink().getAttribute('href')).toBe('/cases/case-1/search?q=term&type=claim')
    );
  });

  it('offers no permalink when no query is present', () => {
    renderSearch('/cases/case-1/search?type=evidence');
    expect(screen.getByRole('status').textContent).toMatch(/enter a search query/i);
    expect(screen.queryByRole('link', { name: 'Permalink for this selection' })).toBeNull();
  });

  it('re-derives request parameters when navigating back and forward', async () => {
    const HistoryControls = () => {
      const navigate = useNavigate();
      return <><button onClick={() => navigate(-1)}>Go back</button><button onClick={() => navigate(1)}>Go forward</button></>;
    };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[
      '/cases/case-1/search?q=first', '/cases/case-1/search?q=second&type=evidence',
    ]} initialIndex={1}><HistoryControls /><Routes>
      <Route path="/cases/:id/search" element={<SearchTab caseId="case-1" />} />
    </Routes></MemoryRouter></QueryClientProvider>);
    await waitFor(() => expect(apiMocks.getCaseSearch).toHaveBeenCalledWith('case-1', expect.objectContaining({ q: 'second', type: 'evidence' })));
    fireEvent.click(screen.getByRole('button', { name: 'Go back' }));
    await waitFor(() => expect(apiMocks.getCaseSearch).toHaveBeenCalledWith('case-1', expect.objectContaining({ q: 'first', type: null })));
    fireEvent.click(screen.getByRole('button', { name: 'Go forward' }));
    await waitFor(() => expect(apiMocks.getCaseSearch).toHaveBeenCalledWith('case-1', expect.objectContaining({ q: 'second', type: 'evidence' })));
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

describe('SearchTab inline validation, snippets and local saved views', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getCaseSearch.mockResolvedValue(response());
    window.localStorage.removeItem(SAVED_VIEWS_STORAGE_KEY);
    window.localStorage.removeItem('other.feature');
  });

  const storedViews = (): Array<Record<string, unknown>> => {
    const raw = window.localStorage.getItem(SAVED_VIEWS_STORAGE_KEY);
    return raw ? (JSON.parse(raw).views as Array<Record<string, unknown>>) : [];
  };

  it('shows an inline date-range message and issues no further request', async () => {
    renderSearch('/cases/case-1/search?q=term&publishedFrom=2026-02-01T00%3A00%3A00.000Z');
    await screen.findByText('Found term');
    expect(apiMocks.getCaseSearch).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByLabelText('Published before'), { target: { value: '2026-01-01' } });

    expect(await screen.findByText(/Published from must be on or before/)).toBeTruthy();
    expect(apiMocks.getCaseSearch).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('Published before').getAttribute('aria-invalid')).toBe('true');
  });

  it('validates an over-long query inline before any network call', () => {
    renderSearch();
    const input = screen.getByRole('searchbox', { name: 'Search terms' });
    fireEvent.change(input, { target: { value: 'x'.repeat(257) } });
    fireEvent.submit(screen.getByRole('search'));

    expect(screen.getByText(/Search terms are limited to 256 characters/)).toBeTruthy();
    expect(apiMocks.getCaseSearch).not.toHaveBeenCalled();
    expect(screen.getByTestId('location').textContent).toBe('/cases/case-1/search');
    expect(input.getAttribute('aria-invalid')).toBe('true');
  });

  it('states the matched field as text instead of relying on colour', async () => {
    renderSearch('/cases/case-1/search?q=term');
    await screen.findByText('Found term');
    expect(screen.getByText('Matched in body')).toBeTruthy();
    expect(screen.getByText('evidence')).toBeTruthy();
  });

  it('saves filters without query text and applies only allowlisted metadata', async () => {
    renderSearch('/cases/case-1/search?q=term&type=evidence&publisher=AP&offset=50');
    await screen.findByText('Found term');

    fireEvent.change(screen.getByLabelText('Saved view name'), { target: { value: 'Evidence by AP' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save current filters' }));
    expect(await screen.findByText(/Saved “Evidence by AP”/)).toBeTruthy();

    const [entry] = storedViews();
    expect(entry.filters).toEqual({ type: 'evidence', publisher: 'AP' });
    expect(entry).not.toHaveProperty('q');
    expect(entry).not.toHaveProperty('offset');
    expect(entry.includeQuery).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/cases/case-1/search?q=term'));
    const callsBeforeApply = apiMocks.getCaseSearch.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: 'Apply saved view Evidence by AP' }));
    await waitFor(() => {
      const location = screen.getByTestId('location').textContent ?? '';
      expect(location).toBe('/cases/case-1/search?type=evidence&publisher=AP');
      expect(location).not.toContain('offset=');
      expect(location).not.toContain('q=');
    });
    // The saved view carried no query text, so applying it clears the query and
    // issues no new search request; only allowlisted filter metadata is restored.
    expect(apiMocks.getCaseSearch.mock.calls.length).toBe(callsBeforeApply);
    expect((screen.getByLabelText('Publisher') as HTMLInputElement).value).toBe('AP');
    expect((screen.getByLabelText('Result type') as HTMLSelectElement).value).toBe('evidence');
  });

  it('stores search text only after the explicit consent step', async () => {
    renderSearch('/cases/case-1/search?q=term');
    await screen.findByText('Found term');

    fireEvent.change(screen.getByLabelText('Saved view name'), { target: { value: 'Without text' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save current filters' }));
    expect(await screen.findByText(/Saved “Without text”/)).toBeTruthy();
    expect(storedViews()[0]).not.toHaveProperty('q');

    fireEvent.change(screen.getByLabelText('Saved view name'), { target: { value: 'With text' } });
    fireEvent.click(screen.getByLabelText(/Store the search text in this saved view/));
    fireEvent.click(screen.getByRole('button', { name: 'Save current filters' }));
    expect(await screen.findByText(/Saved “With text”/)).toBeTruthy();

    const withText = storedViews().find((entry) => entry.name === 'With text');
    expect(withText).toMatchObject({ q: 'term', includeQuery: true });

    // Applying the consented view restores the query text and refetches.
    fireEvent.click(screen.getByRole('button', { name: 'Apply saved view With text' }));
    await waitFor(() =>
      expect(apiMocks.getCaseSearch).toHaveBeenLastCalledWith(
        'case-1',
        expect.objectContaining({ q: 'term', offset: 0 })
      )
    );
  });

  it('refreshes on a storage event without applying a view or resetting the form', async () => {
    renderSearch('/cases/case-1/search?q=term');
    await screen.findByText('Found term');

    window.localStorage.setItem(
      SAVED_VIEWS_STORAGE_KEY,
      JSON.stringify({
        schemaVersion: 1,
        views: [
          {
            id: 'view-remote',
            caseId: 'case-1',
            name: 'Other tab view',
            view: 'search',
            filters: { type: 'claim' },
            includeQuery: false,
          },
        ],
      })
    );
    window.dispatchEvent(new StorageEvent('storage', { key: SAVED_VIEWS_STORAGE_KEY }));

    expect(await screen.findByText('Other tab view')).toBeTruthy();
    expect(screen.getByTestId('location').textContent).toBe('/cases/case-1/search?q=term');
    expect((screen.getByRole('searchbox', { name: 'Search terms' }) as HTMLInputElement).value).toBe('term');
    expect(apiMocks.getCaseSearch).toHaveBeenCalledTimes(1);
  });

  it('shows a visible ephemeral fallback when storage rejects the write', async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError');
    });
    renderSearch('/cases/case-1/search?q=term');
    await screen.findByText('Found term');

    fireEvent.change(screen.getByLabelText('Saved view name'), { target: { value: 'Quota view' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save current filters' }));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toMatch(/session only/i);
    expect(screen.getByText('Quota view')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Apply saved view Quota view' })).toBeTruthy();
    expect(window.localStorage.getItem(SAVED_VIEWS_STORAGE_KEY)).toBeNull();
    setItemSpy.mockRestore();
  });

  it('discards only its own namespace on reset and never calls localStorage.clear', async () => {
    window.localStorage.setItem('other.feature', 'keep-me');
    window.localStorage.setItem(SAVED_VIEWS_STORAGE_KEY, '{broken');
    const clearSpy = vi.spyOn(Storage.prototype, 'clear');
    renderSearch('/cases/case-1/search?q=term');
    await screen.findByText('Found term');

    fireEvent.click(screen.getByRole('button', { name: 'Discard stored saved views' }));

    await waitFor(() => expect(screen.queryByRole('button', { name: 'Discard stored saved views' })).toBeNull());
    expect(window.localStorage.getItem(SAVED_VIEWS_STORAGE_KEY)).toBeNull();
    expect(window.localStorage.getItem('other.feature')).toBe('keep-me');
    expect(clearSpy).not.toHaveBeenCalled();
    clearSpy.mockRestore();
  });
});
