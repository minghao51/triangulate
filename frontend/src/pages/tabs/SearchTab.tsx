import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, RefreshCw, Search } from 'lucide-react';

import Badge from '../../components/design-system/Badge';
import Button from '../../components/design-system/Button';
import { formatTimestamp } from '../../components/inspector/inspector-utils';
import { ApiError, isNotFound, isUnprocessable } from '../../services/api-error';
import { getCaseSearch } from '../../services/api';
import {
  buildClaimEvidenceUrl,
  buildInspectorUrl,
  buildSearchUrl,
  parseSearchSelection,
} from '../../services/deep-links';
import './SearchTab.css';

const PAGE_SIZE = 25;

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

const SearchTab: React.FC<SearchTabProps> = ({ caseId }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const selection = useMemo(
    () => parseSearchSelection(new URLSearchParams(location.search)),
    [location.search]
  );
  const [draftState, setDraftState] = useState({ source: selection.q, value: selection.q });
  const draft = draftState.source === selection.q ? draftState.value : selection.q;

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
    navigate(buildSearchUrl(caseId, {
      ...selection,
      ...patch,
      offset: resetOffset ? 0 : (patch.offset ?? selection.offset),
    }));
  };

  const submit = (event: { preventDefault: () => void }) => {
    event.preventDefault();
    update({ q: draft.trim() });
  };

  const clearFilters = () => update({
    type: null, publisher: null, status: null, publishedFrom: null, publishedTo: null,
  });

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
            name="q"
            type="search"
            value={draft}
            onChange={(event) => setDraftState({ source: selection.q, value: event.target.value })}
            placeholder="Enter search terms"
          />
          <Button type="submit" icon={<Search size={16} />}>Search</Button>
        </div>

        <div className="case-search-filters" aria-label="Search filters">
          <label htmlFor="search-type">Result type</label>
          <select id="search-type" value={selection.type ?? ''} onChange={(event) =>
            update({ type: event.target.value === 'claim' || event.target.value === 'evidence' ? event.target.value : null })
          }>
            <option value="">All types</option>
            <option value="claim">Claims</option>
            <option value="evidence">Evidence</option>
          </select>

          <label htmlFor="search-publisher">Publisher</label>
          <input id="search-publisher" value={selection.publisher ?? ''} onChange={(event) =>
            update({ publisher: event.target.value || null })
          } />

          <label htmlFor="search-status">Claim status</label>
          <select id="search-status" value={selection.status ?? ''} onChange={(event) =>
            update({ status: event.target.value || null })
          }>
            <option value="">Any status</option>
            {['confirmed', 'probable', 'alleged', 'contested', 'debunked', 'unknown'].map((status) =>
              <option key={status} value={status}>{status}</option>
            )}
          </select>

          <label htmlFor="search-published-from">Published from</label>
          <input id="search-published-from" type="date" value={dateInputValue(selection.publishedFrom)} onChange={(event) =>
            update({ publishedFrom: utcDate(event.target.value) })
          } />
          <label htmlFor="search-published-to">Published before</label>
          <input id="search-published-to" type="date" value={dateInputValue(selection.publishedTo)} onChange={(event) =>
            update({ publishedTo: utcDate(event.target.value) })
          } />
          <Button type="button" variant="secondary" onClick={clearFilters}>Clear filters</Button>
        </div>
      </form>

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
          {search.data.total > search.data.limit && (
            <nav className="case-search-pagination" aria-label="Search result pages">
              <Button type="button" variant="secondary" disabled={selection.offset <= 0}
                onClick={() => update({ offset: Math.max(0, selection.offset - search.data!.limit) }, false)}
                icon={<ChevronLeft size={16} />}>Previous</Button>
              <span>Showing {selection.offset + 1}–{Math.min(selection.offset + search.data.items.length, search.data.total)} of {search.data.total}</span>
              <Button type="button" variant="secondary" disabled={selection.offset + search.data.limit >= search.data.total}
                onClick={() => update({ offset: selection.offset + search.data!.limit }, false)}
                icon={<ChevronRight size={16} />}>Next</Button>
            </nav>
          )}
        </>
      ) : null}
    </section>
  );
};

export default SearchTab;
