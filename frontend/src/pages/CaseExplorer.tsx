import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Search,
  Filter,
  Plus,
  FileSearch,
  Activity,
  AlertCircle,
  ShieldCheck,
  ChevronDown,
  Download,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import type { TopicCase } from '../types/backend-models';
import { getCases } from '../services/api';
import { useVisibleRefetchInterval } from '../components/design-system/reader-polling';
import Button from '../components/design-system/Button';
import Card from '../components/design-system/Card';
import { CardBody } from '../components/design-system/Card';
import Badge from '../components/design-system/Badge';
import { formatDistanceToNow, parseISO } from 'date-fns';
import './CaseExplorer.css';

/**
 * Queue ordering derived only from the fields the list DTO already returns:
 * recorded open exceptions, recorded new material, recorded review items and the
 * recorded article/event counts. The case-id tie-break keeps the order stable
 * for identical payloads, so rows never reorder between identical reads.
 */
const casePriorityComparator = (a: TopicCase, b: TopicCase): number => {
  if (a.openExceptionsCount !== b.openExceptionsCount) {
    return b.openExceptionsCount - a.openExceptionsCount;
  }
  if (a.hasNewMaterial !== b.hasNewMaterial) {
    return a.hasNewMaterial ? -1 : 1;
  }
  const aReviewReady = a.status === 'review ready' ? 1 : 0;
  const bReviewReady = b.status === 'review ready' ? 1 : 0;
  if (aReviewReady !== bReviewReady) {
    return bReviewReady - aReviewReady;
  }
  if (a.counts.reviewItems !== b.counts.reviewItems) {
    return b.counts.reviewItems - a.counts.reviewItems;
  }
  const aMaterial = a.counts.articles + a.counts.events;
  const bMaterial = b.counts.articles + b.counts.events;
  if (aMaterial !== bMaterial) {
    return bMaterial - aMaterial;
  }
  return a.id.localeCompare(b.id);
};

/** One page of the case grid; the pager only renders past a single page. */
const CASE_PAGE_SIZE = 10;

/** The toolbar's three orderings, all derived from the list DTO only. */
type CaseSortKey = 'priority' | 'updated' | 'name';

const recordedUpdatedMs = (tc: TopicCase): number => {
  if (!tc.lastUpdated) return Number.NaN;
  const parsed = parseISO(tc.lastUpdated).getTime();
  return Number.isNaN(parsed) ? Number.NaN : parsed;
};

/**
 * `priority` keeps the recorded-count queue; `updated` puts the most recent
 * recorded timestamp first and rows without one last; `name` is the case query
 * in locale order. Every key falls back to the case id so ordering is stable.
 */
const compareCases = (sort: CaseSortKey, a: TopicCase, b: TopicCase): number => {
  if (sort === 'updated') {
    const aTime = recordedUpdatedMs(a);
    const bTime = recordedUpdatedMs(b);
    const aMissing = Number.isNaN(aTime);
    const bMissing = Number.isNaN(bTime);
    if (aMissing !== bMissing) return aMissing ? 1 : -1;
    if (!aMissing && aTime !== bTime) return bTime - aTime;
    return a.id.localeCompare(b.id);
  }
  if (sort === 'name') {
    const byQuery = a.query.localeCompare(b.query);
    return byQuery !== 0 ? byQuery : a.id.localeCompare(b.id);
  }
  return casePriorityComparator(a, b);
};

const formatFetched = (epochMs: number): string =>
  Number.isFinite(epochMs) && epochMs > 0 ? new Date(epochMs).toLocaleTimeString() : '—';

const CaseExplorer: React.FC = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [stageFilter, setStageFilter] = useState<string>('all');
  const [domainFilter, setDomainFilter] = useState<string>('all');
  const [showFilters, setShowFilters] = useState(false);
  const [sortKey, setSortKey] = useState<CaseSortKey>('priority');
  // Local page state only: the explorer has no URL contract, so the page is not
  // a search param and never appears in a deep link.
  const [page, setPage] = useState(1);
  const [selectedCases, setSelectedCases] = useState<Set<string>>(new Set());

  // Same poll budget as the other operator surfaces; a hidden tab stops it.
  const refetchInterval = useVisibleRefetchInterval(30000);

  const { data: cases = [], isLoading, error, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['cases'],
    queryFn: getCases,
    refetchInterval,
  });

  // Get unique values for filters
  const statuses = Array.from(new Set(cases.map((tc) => tc.status)));
  const stages = Array.from(new Set(cases.map((tc) => tc.stage)));
  const domains = Array.from(new Set(cases.map((tc) => tc.conflictDomain))).filter(Boolean);

  // Filter cases, then order the queue with the toolbar's sort key.
  const filteredCases = cases
    .filter((tc) => {
      const matchesSearch =
        !search ||
        `${tc.query} ${tc.conflictDomain}`.toLowerCase().includes(search.toLowerCase());
      const matchesStatus = statusFilter === 'all' || tc.status === statusFilter;
      const matchesStage = stageFilter === 'all' || tc.stage === stageFilter;
      const matchesDomain = domainFilter === 'all' || tc.conflictDomain === domainFilter;
      return matchesSearch && matchesStatus && matchesStage && matchesDomain;
    })
    .sort((a, b) => compareCases(sortKey, a, b));

  // Pagination is derived, never stored: a shrunk filtered set clamps the page
  // instead of rendering an empty grid.
  const pageCount = Math.max(1, Math.ceil(filteredCases.length / CASE_PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const pageStart = (currentPage - 1) * CASE_PAGE_SIZE;
  const visibleCases = filteredCases.slice(pageStart, pageStart + CASE_PAGE_SIZE);

  // Statistics stay scoped to every filtered case, never to the current page.
  const stats = {
    total: filteredCases.length,
    active: filteredCases.filter((c) => c.status !== 'approved' && c.status !== 'rejected').length,
    reviewReady: filteredCases.filter((c) => c.status === 'review ready').length,
    withExceptions: filteredCases.filter((c) => c.openExceptionsCount > 0).length,
    withNewMaterial: filteredCases.filter((c) => c.hasNewMaterial).length,
  };

  // Any narrowing or reorder returns to the first page.
  const resetPage = () => setPage(1);

  const handleSelectCase = (caseId: string) => {
    const newSelected = new Set(selectedCases);
    if (newSelected.has(caseId)) {
      newSelected.delete(caseId);
    } else {
      newSelected.add(caseId);
    }
    setSelectedCases(newSelected);
  };

  const getStatusVariant = (status: TopicCase['status']): 'success' | 'warning' | 'danger' | 'info' | 'neutral' => {
    switch (status) {
      case 'review ready': return 'success';
      case 'investigating': return 'warning';
      case 'discovering': return 'info';
      case 'processing': return 'info';
      case 'failed': return 'danger';
      case 'rejected': return 'danger';
      case 'approved': return 'success';
      case 'monitoring': return 'info';
      default: return 'neutral';
    }
  };

  return (
    <div className="case-explorer">
      {/* Header */}
      <div className="explorer-header">
        <div className="explorer-header-left">
          <h1 className="explorer-title">Case Explorer</h1>
          <p className="explorer-subtitle">
            Saved investigations from the case list, ordered by recorded counts. No per-case
            detail read is issued for these rows.
          </p>
        </div>
        <div className="explorer-header-right">
          <span className="explorer-fetched" data-testid="explorer-last-fetched">
            <span className="explorer-fetched-label">Last fetched</span>
            <span className="explorer-fetched-value">{formatFetched(dataUpdatedAt)}</span>
            <span className="explorer-fetched-note">client request time</span>
          </span>
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw size={14} />}
            onClick={() => refetch()}
          >
            Refresh
          </Button>
          <Button
            variant="primary"
            size="sm"
            icon={<Plus size={14} />}
            onClick={() => navigate('/cases/new')}
          >
            CLI Guide
          </Button>
        </div>
      </div>

      {error && (
        <div className="explorer-error">
          <AlertCircle size={16} />
          <span>Failed to load cases: {(error as Error).message}</span>
        </div>
      )}

      {isLoading ? (
        <div className="explorer-loading">Loading cases...</div>
      ) : (
        <>
          {/* Stats Bar */}
          <div className="explorer-stats">
            <div className="stat-item">
              <span className="stat-value">{stats.total}</span>
              <span className="stat-label">Total</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{stats.active}</span>
              <span className="stat-label">Active</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{stats.reviewReady}</span>
              <span className="stat-label">Review Ready</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{stats.withExceptions}</span>
              <span className="stat-label">Open Exceptions</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{stats.withNewMaterial}</span>
              <span className="stat-label">New Material</span>
            </div>
          </div>

          {/* Filters Toolbar */}
          <Card className="explorer-toolbar">
            <CardBody className="explorer-toolbar-body">
              <div className="toolbar-search">
                <Search size={18} className="search-icon" />
                <input
                  type="text"
                  className="search-input"
                  placeholder="Search queries or domains..."
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    resetPage();
                  }}
                />
              </div>

              <div className="toolbar-actions">
                {/* Sort is a primary list control, not a filter: it stays visible
                    when the filter panel is collapsed. */}
                <div className="toolbar-sort">
                  <label className="filter-label" htmlFor="case-explorer-sort">
                    Sort
                  </label>
                  <select
                    id="case-explorer-sort"
                    className="sort-select"
                    value={sortKey}
                    onChange={(e) => {
                      setSortKey(e.target.value as CaseSortKey);
                      resetPage();
                    }}
                  >
                    <option value="priority">Priority</option>
                    <option value="updated">Recently updated</option>
                    <option value="name">Case name</option>
                  </select>
                </div>

                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Filter size={14} />}
                  onClick={() => setShowFilters(!showFilters)}
                >
                  Filters
                  <ChevronDown
                    size={14}
                    style={{
                      transform: showFilters ? 'rotate(180deg)' : 'rotate(0)',
                      transition: 'transform 0.2s',
                    }}
                  />
                </Button>

                {selectedCases.size > 0 && (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<RefreshCw size={14} />}
                      disabled
                      title="Batch case execution is CLI-only; this UI never starts a run."
                    >
                      CLI Only ({selectedCases.size})
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<Download size={14} />}
                      disabled
                      title="Bulk export is not exposed by the read API; no download is offered."
                    >
                      Export
                    </Button>
                  </>
                )}
              </div>
            </CardBody>

            {showFilters && (
              <div className="explorer-filters">
                <div className="filter-group">
                  <label className="filter-label">Status</label>
                  <select
                    className="filter-select"
                    value={statusFilter}
                    onChange={(e) => {
                      setStatusFilter(e.target.value);
                      resetPage();
                    }}
                  >
                    <option value="all">All Statuses</option>
                    {statuses.map((status) => (
                      <option key={status} value={status}>{status}</option>
                    ))}
                  </select>
                </div>

                <div className="filter-group">
                  <label className="filter-label">Stage</label>
                  <select
                    className="filter-select"
                    value={stageFilter}
                    onChange={(e) => {
                      setStageFilter(e.target.value);
                      resetPage();
                    }}
                  >
                    <option value="all">All Stages</option>
                    {stages.map((stage) => (
                      <option key={stage} value={stage}>{stage}</option>
                    ))}
                  </select>
                </div>

                <div className="filter-group">
                  <label className="filter-label">Domain</label>
                  <select
                    className="filter-select"
                    value={domainFilter}
                    onChange={(e) => {
                      setDomainFilter(e.target.value);
                      resetPage();
                    }}
                  >
                    <option value="all">All Domains</option>
                    {domains.map((domain) => (
                      <option key={domain} value={domain}>{domain}</option>
                    ))}
                  </select>
                </div>

                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setStatusFilter('all');
                    setStageFilter('all');
                    setDomainFilter('all');
                    setSearch('');
                    resetPage();
                  }}
                >
                  Clear Filters
                </Button>
              </div>
            )}
          </Card>

          {/* Cases Grid */}
          <div className="explorer-grid">
            {visibleCases.map((caseItem) => (
              <Card
                key={caseItem.id}
                className="case-card"
                hover
                onClick={() => navigate(`/cases/${caseItem.id}`)}
              >
                <CardBody className="case-card-body">
                  {/* Checkbox */}
                  <div
                    className="case-checkbox"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleSelectCase(caseItem.id);
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selectedCases.has(caseItem.id)}
                      onChange={() => handleSelectCase(caseItem.id)}
                    />
                  </div>

                  {/* Header */}
                  <div className="case-header">
                    <h3 className="case-query">{caseItem.query}</h3>
                    <Badge variant={getStatusVariant(caseItem.status)} size="sm">
                      {caseItem.status}
                    </Badge>
                  </div>

                  {/* Domain */}
                  <div className="case-domain">{caseItem.conflictDomain}</div>

                  {/* Metrics */}
                  <div className="case-metrics">
                    <div className="case-metric" title="Articles">
                      <FileSearch size={14} />
                      <span>{caseItem.counts.articles}</span>
                    </div>
                    <div className="case-metric" title="Events">
                      <Activity size={14} />
                      <span>{caseItem.counts.events}</span>
                    </div>
                    <div className="case-metric" title="Recorded review items">
                      <AlertCircle size={14} />
                      <span>{caseItem.counts.reviewItems}</span>
                    </div>
                  </div>

                  {/* Footer */}
                  <div className="case-footer">
                    <div className="case-stage">
                      <Badge variant="neutral" size="sm">{caseItem.stage}</Badge>
                    </div>

                    {caseItem.openExceptionsCount > 0 ? (
                      <div className="case-exceptions">
                        <AlertCircle size={14} />
                        <span>
                          {caseItem.openExceptionsCount} open exception
                          {caseItem.openExceptionsCount === 1 ? '' : 's'} recorded
                        </span>
                      </div>
                    ) : (
                      <div className="case-status-clean">
                        <ShieldCheck size={14} />
                        <span>0 open exceptions recorded</span>
                      </div>
                    )}

                    <div
                      className={
                        caseItem.hasNewMaterial
                          ? 'case-new-material'
                          : 'case-new-material case-new-material--none'
                      }
                    >
                      <Sparkles size={14} />
                      <span>
                        {caseItem.hasNewMaterial
                          ? 'New material recorded'
                          : 'No new material recorded'}
                      </span>
                    </div>

                    <div className="case-time">
                      {caseItem.lastUpdated
                        ? formatDistanceToNow(parseISO(caseItem.lastUpdated), { addSuffix: true })
                        : 'Unknown'}
                    </div>
                  </div>
                </CardBody>
              </Card>
            ))}

            {filteredCases.length === 0 && (
              <div className="explorer-empty">
                <AlertCircle size={48} />
                <h3>No cases found</h3>
                <p>Try adjusting your filters or create a new investigation</p>
                <Button
                  variant="primary"
                  icon={<Plus size={16} />}
                  onClick={() => navigate('/cases/new')}
                >
                  Create New Case
                </Button>
              </div>
            )}
          </div>

          {/* Pager — only when there is more than one page to show. */}
          {filteredCases.length > CASE_PAGE_SIZE && (
            <nav className="explorer-pagination" aria-label="Case pagination">
              <span className="pagination-summary">
                Showing {pageStart + 1}–{pageStart + visibleCases.length} of{' '}
                {filteredCases.length} cases
              </span>
              <div className="pagination-controls">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setPage(currentPage - 1)}
                  disabled={currentPage <= 1}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setPage(currentPage + 1)}
                  disabled={currentPage >= pageCount}
                >
                  Next
                </Button>
              </div>
            </nav>
          )}
        </>
      )}
    </div>
  );
};

export default CaseExplorer;
