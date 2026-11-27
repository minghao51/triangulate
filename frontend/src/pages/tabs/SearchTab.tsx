import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, RefreshCw, Search } from 'lucide-react';

import Badge from '../../components/design-system/Badge';
import Button from '../../components/design-system/Button';
import { formatTimestamp } from '../../components/inspector/inspector-utils';
import { ApiError, isNotFound, isUnprocessable } from '../../services/api-error';
import { getCaseSearch } from '../../services/api';
import {
  MAX_FILTER_TEXT_LENGTH,
  SEARCH_PARAMS,
  buildClaimEvidenceUrl,
  buildInspectorUrl,
  buildSearchUrl,
  parseSearchSelection,
  searchSavedFilters,
} from '../../services/deep-links';
import {
  deleteAllSavedViews,
  deleteSavedView,
  deleteSavedViewsForCase,
  describeSavedView,
  listSavedViews,
  saveSavedView,
  subscribeToSavedViews,
  type SavedView,
  type SavedViewsSnapshot,
} from '../../services/saved-views';
import './SearchTab.css';

const PAGE_SIZE = 25;
const MAX_SEARCH_OFFSET = 2_147_483_647;

interface SearchTabProps {
  caseId: string;
}

function dateInputValue(value: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toISOString().slice(0, 10);
}

function utcDate(value: string): string | null {
  if (!value) return null;
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

/** Client-side limit that matches the committed search URL allowlist. */
const MAX_SEARCH_TEXT_LENGTH = MAX_FILTER_TEXT_LENGTH;

type SearchFieldError = { field: 'q' | 'publisher' | 'dates'; message: string };

function tooLong(value: string): boolean {
  return Array.from(value.trim()).length > MAX_SEARCH_TEXT_LENGTH;
}

/** An inverted publication window is invalid before any request is made. */
function invertedDateRange(from: string | null, to: string | null): boolean {
  if (!from || !to) return false;
  const fromTime = new Date(from).getTime();
  const toTime = new Date(to).getTime();
  return Number.isFinite(fromTime) && Number.isFinite(toTime) && fromTime > toTime;
}

const SearchTab: React.FC<SearchTabProps> = ({ caseId }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const selection = useMemo(() => {
    const parsedSelection = parseSearchSelection(new URLSearchParams(location.search));
    const parsed = {
      ...parsedSelection,
      // Match the API's MAX_SEARCH_OFFSET instead of sending a deep link that 422s.
      offset: parsedSelection.offset > MAX_SEARCH_OFFSET ? 0 : parsedSelection.offset,
    };
    // Claims/status take precedence over publisher when resolving malformed deep links.
    if (parsed.status) {
      return {
        ...parsed,
        publisher: null,
        type: parsed.type === 'evidence' ? 'claim' as const : parsed.type,
      };
    }
    if (parsed.publisher && parsed.type === 'claim') {
      return { ...parsed, publisher: null };
    }
    return parsed;
  }, [location.search]);

  useEffect(() => {
    const canonicalUrl = buildSearchUrl(caseId, selection);
    if (`${location.pathname}${location.search}` !== canonicalUrl) {
      navigate(canonicalUrl, { replace: true });
    }
  }, [caseId, location.pathname, location.search, navigate, selection]);
  const [draftState, setDraftState] = useState({ source: selection.q, value: selection.q });
  const [fieldError, setFieldError] = useState<SearchFieldError | null>(null);
  const [savedSnapshot, setSavedSnapshot] = useState<SavedViewsSnapshot>(() => listSavedViews(caseId));
  const [savedName, setSavedName] = useState('');
  const [savedIncludeQuery, setSavedIncludeQuery] = useState(false);
  const [savedNotice, setSavedNotice] = useState<{ tone: 'status' | 'alert'; text: string } | null>(null);
  const [ephemeralViews, setEphemeralViews] = useState<SavedView[]>([]);
  const queryInputRef = useRef<HTMLInputElement>(null);
  const draft = draftState.source === selection.q ? draftState.value : selection.q;

  useEffect(
    () => subscribeToSavedViews(() => setSavedSnapshot(listSavedViews(caseId))),
    [caseId]
  );

  const activeQuery = selection.q.trim();
  const search = useQuery({
    queryKey: [
      'caseSearch', caseId, activeQuery, selection.type, selection.publisher,
      selection.status, selection.publishedFrom, selection.publishedTo,
      selection.offset,
    ],
    queryFn: () => getCaseSearch(caseId, {
      q: activeQuery,
      type: selection.type,
      publisher: selection.publisher,
      status: selection.status,
      publishedFrom: selection.publishedFrom,
      publishedTo: selection.publishedTo,
      limit: PAGE_SIZE,
      offset: selection.offset,
    }),
    enabled: activeQuery.length > 0,
    retry: false,
  });

  const update = (patch: Partial<typeof selection>, resetOffset = true) => {
    const next = {
      ...selection,
      ...patch,
      offset: resetOffset ? 0 : (patch.offset ?? selection.offset),
    };
    if (invertedDateRange(next.publishedFrom, next.publishedTo)) {
      setFieldError({
        field: 'dates',
        message: 'Published from must be on or before Published before. No request was sent.',
      });
      return;
    }
    if (next.publisher && tooLong(next.publisher)) {
      setFieldError({
        field: 'publisher',
        message: `Publisher is limited to ${MAX_SEARCH_TEXT_LENGTH} characters. No request was sent.`,
      });
      return;
    }
    setFieldError(null);
    navigate(buildSearchUrl(caseId, next));
  };

  const submit = (event: { preventDefault: () => void }) => {
    event.preventDefault();
    const query = draft.trim();
    if (!query) {
      setFieldError({ field: 'q', message: 'Enter at least one search term.' });
      queryInputRef.current?.focus();
      return;
    }
    if (tooLong(query)) {
      setFieldError({
        field: 'q',
        message: `Search terms are limited to ${MAX_SEARCH_TEXT_LENGTH} characters. No request was sent.`,
      });
      queryInputRef.current?.focus();
      return;
    }
    if (invertedDateRange(selection.publishedFrom, selection.publishedTo)) {
      setFieldError({
        field: 'dates',
        message: 'Published from must be on or before Published before. No request was sent.',
      });
      return;
    }
    setFieldError(null);
    update({ q: query });
  };

  const clearFilters = () => update({
    type: null, publisher: null, status: null, publishedFrom: null, publishedTo: null,
  });

  const caseSavedViews = savedSnapshot.views;
  const mergedSavedViews = [...ephemeralViews, ...caseSavedViews];
  const canConsentToQuery = activeQuery.length > 0;

  const handleSaveView = () => {
    const result = saveSavedView({
      caseId,
      view: 'search',
      name: savedName,
      filters: searchSavedFilters(selection),
      sort: null,
      includeQuery: savedIncludeQuery && canConsentToQuery,
      query: savedIncludeQuery && canConsentToQuery ? activeQuery : null,
    });
    if (result.ok) {
      setSavedSnapshot(result.snapshot);
      setSavedName('');
      setSavedIncludeQuery(false);
      setSavedNotice({ tone: 'status', text: `Saved “${result.view.name}” on this device.` });
      return;
    }
    const ephemeral = result.ephemeral;
    if (ephemeral) {
      setEphemeralViews((views) => [...views, ephemeral]);
      setSavedName('');
      setSavedIncludeQuery(false);
    }
    setSavedNotice({ tone: 'alert', text: result.message });
  };

  const applySavedView = (view: SavedView) => {
    const type = view.filters[SEARCH_PARAMS.type];
    update(
      {
        q: view.q ?? '',
        type: type === 'claim' || type === 'evidence' ? type : null,
        publisher: view.filters[SEARCH_PARAMS.publisher] ?? null,
        status: view.filters[SEARCH_PARAMS.status] ?? null,
        publishedFrom: view.filters[SEARCH_PARAMS.publishedFrom] ?? null,
        publishedTo: view.filters[SEARCH_PARAMS.publishedTo] ?? null,
        offset: 0,
      },
      false
    );
    setSavedNotice({ tone: 'status', text: `Applied “${view.name}”.` });
  };

  const handleDeleteView = (id: string) => {
    if (ephemeralViews.some((view) => view.id === id)) {
      setEphemeralViews((views) => views.filter((view) => view.id !== id));
      return;
    }
    setSavedSnapshot(deleteSavedView(id));
  };

  const handleDeleteCaseViews = () => {
    setSavedSnapshot(deleteSavedViewsForCase(caseId));
    setEphemeralViews([]);
  };

  const handleDeleteAllViews = () => {
    setSavedSnapshot(deleteAllSavedViews());
    setEphemeralViews([]);
  };

  const error = search.error;
  const statusCode = error instanceof ApiError ? error.status : null;
  const errorMessage = error instanceof Error ? error.message : 'Search failed unexpectedly.';

  return (
    <section className="case-search" aria-labelledby="case-search-heading">
      <header className="case-search-header">
        <h2 id="case-search-heading">Search this case</h2>
        <p>Search current evidence and claims in this case.</p>
      </header>

      <form className="case-search-form" onSubmit={submit} role="search">
        <label htmlFor="case-search-query">Search terms</label>
        <div className="case-search-query-row">
          <input
            id="case-search-query"
            ref={queryInputRef}
            name="q"
            type="search"
            value={draft}
            onChange={(event) => setDraftState({ source: selection.q, value: event.target.value })}
            placeholder="Enter search terms"
            aria-invalid={fieldError?.field === 'q' || undefined}
            aria-describedby={fieldError?.field === 'q' ? 'search-field-error' : undefined}
          />
          <Button type="submit" icon={<Search size={16} />}>Search</Button>
        </div>

        <div className="case-search-filters" aria-label="Search filters">
          <label htmlFor="search-type">Result type</label>
          <select id="search-type" aria-describedby="search-filter-hint" value={selection.type ?? ''} onChange={(event) =>
            update({ type: event.target.value === 'claim' || event.target.value === 'evidence' ? event.target.value : null })
          }>
            <option value="">All types</option>
            <option value="claim" disabled={Boolean(selection.publisher)}>Claims</option>
            <option value="evidence" disabled={Boolean(selection.status)}>Evidence</option>
          </select>

          <label htmlFor="search-publisher">Publisher</label>
          <input id="search-publisher" aria-describedby={fieldError?.field === 'publisher' ? 'search-filter-hint search-field-error' : 'search-filter-hint'} aria-invalid={fieldError?.field === 'publisher' || undefined} disabled={Boolean(selection.status)} value={selection.publisher ?? ''} onChange={(event) =>
            update({ publisher: event.target.value || null, type: event.target.value && selection.type === 'claim' ? null : selection.type })
          } />

          <label htmlFor="search-status">Claim status</label>
          <select id="search-status" aria-describedby="search-filter-hint" disabled={Boolean(selection.publisher)} value={selection.status ?? ''} onChange={(event) =>
            update({ status: event.target.value || null, publisher: event.target.value ? null : selection.publisher })
          }>
            <option value="">Any status</option>
            {['confirmed', 'probable', 'alleged', 'contested', 'debunked', 'unknown'].map((status) =>
              <option key={status} value={status}>{status}</option>
            )}
          </select>

          <label htmlFor="search-published-from">Published from</label>
          <input id="search-published-from" type="date" aria-invalid={fieldError?.field === 'dates' || undefined} aria-describedby={fieldError?.field === 'dates' ? 'search-field-error' : undefined} value={dateInputValue(selection.publishedFrom)} onChange={(event) =>
            update({ publishedFrom: utcDate(event.target.value) })
          } />
          <label htmlFor="search-published-to">Published before</label>
          <input id="search-published-to" type="date" aria-invalid={fieldError?.field === 'dates' || undefined} aria-describedby={fieldError?.field === 'dates' ? 'search-field-error' : undefined} value={dateInputValue(selection.publishedTo)} onChange={(event) =>
            update({ publishedTo: utcDate(event.target.value) })
          } />
          <Button type="button" variant="secondary" onClick={clearFilters}>Clear filters</Button>
          <p id="search-filter-hint" className="case-search-filter-hint" role="note">
            Status applies to claims; publisher applies to evidence.
          </p>
          {fieldError && (
            <p id="search-field-error" className="case-search-filter-hint" role="alert">
              {fieldError.message}
            </p>
          )}
        </div>
      </form>

      <section className="case-search-saved-views" aria-label="Saved search views">
        <h3>Saved search views</h3>
        <p id="search-saved-views-hint" className="case-search-filter-hint">
          Saved views stay in this browser. They are local, not private: anyone using this browser profile can read them.
        </p>
        <div className="case-search-query-row">
          <label htmlFor="search-saved-view-name">Saved view name</label>
          <input
            id="search-saved-view-name"
            value={savedName}
            onChange={(event) => setSavedName(event.target.value)}
            placeholder="e.g. Evidence by publisher"
            aria-describedby="search-saved-views-hint"
          />
          <Button type="button" variant="secondary" onClick={handleSaveView}>Save current filters</Button>
        </div>
        {canConsentToQuery && (
          <div>
            <label htmlFor="search-saved-consent">
              <input
                id="search-saved-consent"
                type="checkbox"
                checked={savedIncludeQuery}
                onChange={(event) => setSavedIncludeQuery(event.target.checked)}
              />{' '}
              Store the search text in this saved view
            </label>
            <p className="case-search-filter-hint">
              Search text can be sensitive. It is excluded unless you tick this box; with consent it is stored on this device.
            </p>
          </div>
        )}
        {savedNotice && (
          <p role={savedNotice.tone === 'alert' ? 'alert' : 'status'}>{savedNotice.text}</p>
        )}
        {mergedSavedViews.length > 0 && (
          <ul className="case-search-saved-views-list" aria-label="Saved search views list">
            {mergedSavedViews.map((view) => (
              <li key={view.id}>
                <span>{view.name}</span>
                <span className="case-search-filter-hint"> — {describeSavedView(view)}</span>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => applySavedView(view)}
                  aria-label={`Apply saved view ${view.name}`}
                >
                  Apply
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => handleDeleteView(view.id)}
                  aria-label={`Delete saved view ${view.name}`}
                >
                  Delete
                </Button>
              </li>
            ))}
          </ul>
        )}
        <div className="case-search-query-row">
          {(caseSavedViews.length > 0 || savedSnapshot.totalCount > 0) && (
            <Button type="button" variant="secondary" onClick={handleDeleteCaseViews}>
              Delete saved views for this case
            </Button>
          )}
          {(caseSavedViews.length > 0 || savedSnapshot.totalCount > 0 || savedSnapshot.status !== 'ok') && (
            <Button type="button" variant="secondary" onClick={handleDeleteAllViews}>
              {savedSnapshot.status === 'ok' ? 'Delete all saved views' : 'Discard stored saved views'}
            </Button>
          )}
        </div>
      </section>

      {!activeQuery ? (
        <p className="case-search-idle" role="status">Enter a search query to search this case.</p>
      ) : search.isLoading ? (
        <div className="case-search-loading" role="status" aria-busy="true">Searching this case…</div>
      ) : error ? (
        <div className="case-search-error" role="alert" aria-live="assertive">
          {isNotFound(error) ? (
            <><h3>Case not found</h3><p>This case could not be found for search. No results from another case are shown.</p></>
          ) : statusCode === 503 ? (
            <><h3>Search index unavailable</h3><p>{errorMessage}</p><p>Ask an operator to run <code>triangulate case rebuild-search {caseId}</code>, then retry.</p></>
          ) : isUnprocessable(error) ? (
            <><h3>Search query or filters are invalid</h3><p>{errorMessage}</p></>
          ) : (
            <><h3>Search failed</h3><p>{errorMessage}</p></>
          )}
          <Button type="button" variant="secondary" icon={<RefreshCw size={15} />} onClick={() => void search.refetch()}>Retry</Button>
        </div>
      ) : search.data ? (
        <>
          <p className="case-search-count" aria-live="polite">
            {search.data.total} {search.data.total === 1 ? 'result' : 'results'}
          </p>
          {search.data.items.length === 0 ? (
            <p className="case-search-empty" role="status">No matches for this query and these filters.</p>
          ) : (
            <ol className="case-search-results" aria-label="Search results">
              {search.data.items.map((item) => {
                const resultUrl = item.resultType === 'claim' && item.claimId
                  ? buildClaimEvidenceUrl(caseId, item.claimId)
                  : item.resultType === 'evidence' && item.evidenceId
                    ? buildInspectorUrl(caseId, { evidenceId: item.evidenceId, captureId: item.captureId })
                    : null;
                return (
                  <li key={`${item.resultType}:${item.id}`}>
                    <article className="case-search-result">
                      <div className="case-search-result-heading">
                        <Badge variant={item.resultType === 'claim' ? 'info' : 'neutral'} size="sm">{item.resultType}</Badge>
                        {resultUrl ? <Link to={resultUrl}>{item.title || item.snippet}</Link> : <span>{item.title || item.snippet}</span>}
                      </div>
                      {item.title && <p className="case-search-snippet">{item.snippet}</p>}
                      <div className="case-search-metadata">
                        <span>
                          Matched in {item.matchedField === 'title' ? 'title' : 'body'}
                        </span>
                        {item.publisher && <span>Publisher: {item.publisher}</span>}
                        {item.status && <span>Status: {item.status}</span>}
                        {item.publishedAt && <span>Published: {formatTimestamp(item.publishedAt)}</span>}
                      </div>
                    </article>
                  </li>
                );
              })}
            </ol>
          )}
          {search.data.total > 0 && selection.offset >= search.data.total ? (
            <div className="case-search-pagination" role="status">
              <span>This page is beyond the last result — showing the first page instead.</span>
              <Button type="button" variant="secondary" onClick={() => update({ offset: 0 }, false)}>Show first page</Button>
            </div>
          ) : search.data.total > 0 && search.data.total > search.data.limit ? (
            <nav className="case-search-pagination" aria-label="Search result pages">
              <Button type="button" variant="secondary" disabled={selection.offset <= 0}
                onClick={() => update({ offset: Math.max(0, selection.offset - search.data!.limit) }, false)}
                icon={<ChevronLeft size={16} />}>Previous</Button>
              <span>Showing {selection.offset + 1}–{Math.min(selection.offset + search.data.items.length, search.data.total)} of {search.data.total}</span>
              <Button type="button" variant="secondary" disabled={selection.offset + search.data.limit >= search.data.total}
                onClick={() => update({ offset: selection.offset + search.data!.limit }, false)}
                icon={<ChevronRight size={16} />}>Next</Button>
            </nav>
          ) : null}
        </>
      ) : null}

      {/* The link always describes the selection currently in the URL: query,
          filters and offset, using the same canonical builder the route uses. */}
      {activeQuery ? (
        <p className="case-search-permalink">
          <a href={buildSearchUrl(caseId, selection)}>Permalink for this selection</a>
        </p>
      ) : null}
    </section>
  );
};

export default SearchTab;
