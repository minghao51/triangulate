import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams, useNavigate, Routes, Route, useLocation } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Play,
  ShieldAlert,
  FileText,
  GitMerge,
  GitCompare,
  Users,
  Clock,
  AlertTriangle,
  RefreshCw,
  TerminalSquare,
  MessageSquare,
  Search,
  Flag,
  CheckCheck,
  History,
} from 'lucide-react';
import type { CaseDetail, TopicCase } from '../types/backend-models';
import {
  createCaseAnnotation,
  getCaseDetail,
  getEvaluationForCase,
  getReviewActivityForCase,
  submitCaseReviewAction,
} from '../services/api';
import { ApiError } from '../services/api-error';
import { useCaseStore } from '../stores/case-store';
import {
  buildInspectorUrl,
  buildViewHref,
  CHANGES_PARAMS,
  INSPECTOR_PARAMS,
  isHistoricalView,
  parseAdHocChangesSelection,
  readSnapshotSelector,
  recallCaseViewHref,
  rememberCaseViewHref,
  sanitizeViewUrl,
  stripHistoricalSelector,
  viewFromPathSegment,
  type CaseViewId,
} from '../services/deep-links';
import Button from '../components/design-system/Button';
import Card from '../components/design-system/Card';
import { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';
import Badge from '../components/design-system/Badge';
import ReaderState from '../components/design-system/ReaderState';
import StatusIndicator from '../components/design-system/StatusIndicator';
import './CaseIntelligenceCenter.css';

// Tab components
import EvidenceTab from './tabs/EvidenceTab';
import CompareTab from './tabs/CompareTab';
import ClaimsTab from './tabs/ClaimsTab';
import ExceptionsTab from './tabs/ExceptionsTab';
import { clearExceptionRowAttempts } from './tabs/exception-row-attempts';
import PartiesTab from './tabs/PartiesTab';
import TimelineTab from './tabs/TimelineTab';
import MapTab from './tabs/MapTab';
import ReportTab from './tabs/ReportTab';
import RunHistoryTab from './tabs/RunHistoryTab';
import ChangesTab from './tabs/ChangesTab';
import SearchTab from './tabs/SearchTab';
import { Layers, Share2, BookOpen, Workflow, Map } from 'lucide-react';

interface NavDestination {
  view: CaseViewId;
  label: string;
  icon: React.ReactNode;
  badge?: number;
}

interface NavGroup {
  id: string;
  label: string;
  destinations: NavDestination[];
}

const NAV_DESTINATIONS: readonly NavDestination[] = [
  { view: 'overview', label: 'Overview', icon: <FileText size={16} /> },
  { view: 'search', label: 'Search', icon: <Search size={16} /> },
  { view: 'evidence', label: 'Evidence', icon: <FileText size={16} /> },
  { view: 'claims', label: 'Claims', icon: <GitMerge size={16} /> },
  { view: 'compare', label: 'Compare', icon: <GitCompare size={16} /> },
  { view: 'sources', label: 'Sources', icon: <Layers size={16} /> },
  { view: 'parties', label: 'Parties', icon: <Users size={16} /> },
  { view: 'map', label: 'Map', icon: <Map size={16} /> },
  { view: 'timeline', label: 'Timeline', icon: <Clock size={16} /> },
  { view: 'network', label: 'Network', icon: <Share2 size={16} /> },
  { view: 'narratives', label: 'Narratives', icon: <BookOpen size={16} /> },
  { view: 'exceptions', label: 'Exceptions', icon: <AlertTriangle size={16} /> },
  { view: 'report', label: 'Report', icon: <FileText size={16} /> },
  { view: 'changes', label: 'Changes', icon: <History size={16} /> },
  { view: 'run-history', label: 'Run history', icon: <Play size={16} /> },
  { view: 'pipeline', label: 'Pipeline', icon: <Workflow size={16} /> },
];

/** Five presentation groups over the same routes; headings create no route. */
const NAV_GROUP_LAYOUT: readonly { id: string; label: string; views: CaseViewId[] }[] = [
  { id: 'start', label: 'Start', views: ['overview', 'search'] },
  { id: 'evidence', label: 'Evidence', views: ['evidence', 'claims', 'compare', 'sources'] },
  {
    id: 'context',
    label: 'Context',
    views: ['parties', 'map', 'timeline', 'network', 'narratives'],
  },
  { id: 'review', label: 'Review & Output', views: ['exceptions', 'report'] },
  { id: 'activity', label: 'Activity', views: ['changes', 'run-history', 'pipeline'] },
];

function destinationFor(view: CaseViewId): NavDestination {
  return NAV_DESTINATIONS.find((destination) => destination.view === view) ?? NAV_DESTINATIONS[0];
}

/** Short, stable rendering of an observation ID inside gate copy. */
function shortenSnapshotId(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

/**
 * The one decision that governs a case-workspace URL.
 *
 * The citation redirect, the historical gate and the allowlist canonicalisation
 * are alternatives, never independent effects: only one of them acts on a given
 * URL, so a redirect can never strip a snapshot and no gate can be undone by a
 * rewrite that races it.
 */
type CaseRouteDecision =
  | { kind: 'view' }
  /** A current-only view carries a `snapshot`: render the gate, mount nothing. */
  | { kind: 'unsupported-history'; snapshotId: string; openCurrentHref: string }
  /** `snapshot` is empty, oversized or ambiguous: unavailable, never live data. */
  | { kind: 'invalid-history'; reason: string; openCurrentHref: string }
  /** Evidence with both a pin and a citation: two explicit user choices only. */
  | {
      kind: 'citation-conflict';
      snapshotId: string;
      keepSnapshotHref: string;
      citationHref: string;
    }
  /** A legacy citation-only link: one `replace` redirect to Evidence. */
  | { kind: 'redirect-citation'; href: string };

/**
 * Classify one case-workspace URL into exactly one of those outcomes.
 *
 * Historical selectors are never dropped to reveal live data, a citation is
 * never forwarded as proof of a pinned observation, and only an allowlist-valid
 * citation is ever encoded into a destination.
 */
function decideCaseRoute(
  caseId: string,
  view: CaseViewId,
  routeParams: URLSearchParams
): CaseRouteDecision {
  // "Open current": strip both historical selectors and keep only this view's
  // valid browse state, so the escape can never resurrect the citation redirect.
  const openCurrentParams = stripHistoricalSelector(routeParams);
  openCurrentParams.delete(INSPECTOR_PARAMS.citation);
  const openCurrentHref = buildViewHref(caseId, view, openCurrentParams);

  // Validate the citation through the evidence allowlist: only this value is
  // encoded into another route, never the raw query string.
  const citationId = sanitizeViewUrl('evidence', routeParams).params.get(
    INSPECTOR_PARAMS.citation
  );

  const snapshot = readSnapshotSelector(routeParams);
  if (snapshot.state === 'invalid' || snapshot.state === 'conflicting') {
    return {
      kind: 'invalid-history',
      reason: snapshot.reason ?? 'The snapshot selector is not usable.',
      openCurrentHref,
    };
  }

  const snapshotId = snapshot.snapshotId;
  if (snapshotId) {
    // A current-only reader must never reinterpret a frozen link as live data.
    if (!isHistoricalView(view)) {
      return { kind: 'unsupported-history', snapshotId, openCurrentHref };
    }
    // A citation is frozen by its own ID and cannot prove membership of the
    // pinned observation, so neither selector is read until the operator picks.
    if (view === 'evidence' && citationId) {
      const keepSnapshotParams = new URLSearchParams(routeParams);
      keepSnapshotParams.delete(INSPECTOR_PARAMS.citation);
      return {
        kind: 'citation-conflict',
        snapshotId,
        keepSnapshotHref: buildViewHref(caseId, 'evidence', keepSnapshotParams),
        citationHref: buildInspectorUrl(caseId, { citationId }),
      };
    }
    // Evidence/Changes keep the pin and the rest of their allowlisted state.
    return { kind: 'view' };
  }

  // No explicit snapshot selector: a legacy citation-only link still lands on the
  // evidence inspector once. A historical destination that names its own context —
  // an explicit ad-hoc mode or a `baselineSnapshot`/`targetSnapshot` pair, complete
  // or not — stays where it is and drops the stray citation instead, so an
  // incomplete selection can be corrected instead of being destroyed.
  if (!citationId || view === 'evidence') return { kind: 'view' };
  if (view === 'changes' && changesNamesOwnHistory(routeParams)) {
    return { kind: 'view' };
  }
  return { kind: 'redirect-citation', href: buildInspectorUrl(caseId, { citationId }) };
}

/**
 * Changes is a historical view: an ad-hoc mode or either side of an explicit
 * comparison pair is the operator's own frozen context, so a stray citation must
 * not redirect away from it. Presence (not validity) counts, so an incomplete or
 * blank selection stays visible for correction.
 */
function changesNamesOwnHistory(params: URLSearchParams): boolean {
  const adHoc = parseAdHocChangesSelection(params);
  return (
    adHoc.active ||
    adHoc.baselineSnapshotId !== null ||
    adHoc.targetSnapshotId !== null ||
    params.has(CHANGES_PARAMS.baselineSnapshot) ||
    params.has(CHANGES_PARAMS.targetSnapshot)
  );
}

function buildNavGroups(openExceptionsCount: number): NavGroup[] {
  return NAV_GROUP_LAYOUT.map((group) => ({
    id: group.id,
    label: group.label,
    destinations: group.views.map((view) => {
      const destination = destinationFor(view);
      return view === 'exceptions' && openExceptionsCount > 0
        ? { ...destination, badge: openExceptionsCount }
        : destination;
    }),
  }));
}

const CaseIntelligenceCenter: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  // `/cases/<id>[/<view>]`; an empty view segment is the case root (Overview).
  const pathSegments = location.pathname.split('/').filter(Boolean);
  const viewSegment = pathSegments.length > 2 ? pathSegments[2] : '';
  const currentView: CaseViewId | null = viewFromPathSegment(viewSegment);

  const { setActiveCase, setCaseDetail, clearActiveCase } = useCaseStore();

  // Fetch case data
  const { data: detailData, isLoading, error: queryError, refetch } = useQuery({
    queryKey: ['caseDetail', id],
    queryFn: () => getCaseDetail(id!),
    enabled: !!id,
    refetchInterval: 15000, // Poll every 15 seconds
  });

  // Only trust detail that belongs to the case currently in the route.
  const activeCase =
    detailData?.case && detailData.case.id === id ? detailData.case : null;

  // Clear the shared store when the route's case changes so a previous case can
  // never stay active behind a new case.
  useEffect(() => {
    clearActiveCase();
  }, [id, clearActiveCase]);

  // Apply store state only for the matching case; a late response for case A can
  // never overwrite case B because the id is compared before writing.
  useEffect(() => {
    if (detailData?.case && detailData.case.id === id) {
      setActiveCase(detailData.case);
      setCaseDetail(detailData);
    }
  }, [detailData, id, setActiveCase, setCaseDetail]);

  // Release the shared store when leaving the case workspace entirely.
  useEffect(() => () => clearActiveCase(), [clearActiveCase]);

  // The in-memory write records outlive a view switch, not the case visit: drop
  // this case's records when its workspace closes or the route moves to another
  // case, so nothing is persisted and no other case can inherit them.
  useEffect(() => {
    if (!id) return;
    return () => {
      reviewFormRecords.delete(id);
      clearExceptionRowAttempts(id);
    };
  }, [id]);

  // A frozen `?citation=` link without a historical selector still lands on the
  // evidence inspector once; that redirect is part of the decision below, not a
  // separate effect that could strip a snapshot pin.

  // Per-view URL state is strictly allowlisted; `snapshot` on a current-only
  // view is a conflict, never an unknown parameter to drop silently.
  const sanitizedUrl = useMemo(
    () => (currentView ? sanitizeViewUrl(currentView, location.search) : null),
    [currentView, location.search]
  );
  const routeParams = useMemo(
    () => new URLSearchParams(location.search),
    [location.search]
  );
  const currentViewLabel = currentView ? destinationFor(currentView).label : 'view';
  const canonicalHref =
    id && currentView && sanitizedUrl
      ? buildViewHref(id, currentView, sanitizedUrl.params)
      : null;
  const navGroups = buildNavGroups(activeCase?.openExceptionsCount ?? 0);

  // R02 — one decision point for redirect, gate and canonicalisation.
  const routeDecision: CaseRouteDecision = useMemo(
    () => (id && currentView ? decideCaseRoute(id, currentView, routeParams) : { kind: 'view' }),
    [id, currentView, routeParams]
  );

  // The single navigation this workspace performs on its own: a legacy
  // citation-only link resolving once on Evidence.
  useEffect(() => {
    if (routeDecision.kind !== 'redirect-citation') return;
    navigate(routeDecision.href, { replace: true });
  }, [routeDecision, navigate]);

  // Commit the canonical href for the active view so Back/reload and later
  // cross-links return to it. Unknown/invalid params are stripped instead of
  // being carried forward; a historical conflict is left untouched for the gate.
  useEffect(() => {
    if (!id || !currentView || !sanitizedUrl || !canonicalHref) return;
    // Only an ordinary view commits: a redirect or a gate owns every other case.
    if (routeDecision.kind !== 'view') return;
    const hasDropped = sanitizedUrl.dropped.length > 0;
    const hasInvalid = Object.keys(sanitizedUrl.invalid).length > 0;
    if (hasDropped || hasInvalid) {
      const actual = `${location.pathname}${location.search}`;
      if (actual !== canonicalHref) {
        navigate(canonicalHref, { replace: true });
        return;
      }
    }
    rememberCaseViewHref(id, currentView, canonicalHref);
  }, [
    id,
    currentView,
    sanitizedUrl,
    canonicalHref,
    routeDecision.kind,
    location.pathname,
    location.search,
    navigate,
  ]);

  // A group link restores the last committed href for its view (session memory)
  // and otherwise opens the bare route.
  const hrefForView = (view: CaseViewId): string => {
    if (!id) return '/cases';
    if (canonicalHref && view === currentView) return canonicalHref;
    return recallCaseViewHref(id, view) ?? buildViewHref(id, view);
  };

  if (isLoading) {
    return (
      <div className="case-intelligence-center">
        <div className="case-loading">
          <div className="loading-spinner" />
          <p>Loading case intelligence...</p>
        </div>
      </div>
    );
  }

  if (!id) {
    return (
      <div className="case-intelligence-center">
        <div className="case-error" role="alert">
          <AlertTriangle size={24} />
          <div>
            <h3>No case selected</h3>
            <p>The route does not include a case ID.</p>
            <Button variant="secondary" icon={<ArrowLeft size={16} />} onClick={() => navigate('/cases')}>
              Back to Cases
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (queryError) {
    return (
      <div className="case-intelligence-center">
        <div className="case-error" role="alert">
          <AlertTriangle size={24} />
          <div>
            <h3>Failed to load case</h3>
            <p>
              {queryError instanceof Error && queryError.message
                ? queryError.message
                : 'The case could not be loaded.'}
            </p>
            <div className="case-error-actions">
              <Button variant="secondary" onClick={() => refetch()}>Retry</Button>
              <Button variant="ghost" icon={<ArrowLeft size={16} />} onClick={() => navigate('/cases')}>
                Back to Cases
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!activeCase) {
    return (
      <div className="case-intelligence-center">
        <div className="case-error" role="alert">
          <AlertTriangle size={24} />
          <div>
            <h3>Case not found</h3>
            <p>No case with ID <code>{id}</code> was returned by the API.</p>
            <Button variant="secondary" icon={<ArrowLeft size={16} />} onClick={() => navigate('/cases')}>
              Back to Cases
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="case-intelligence-center">
      {/* Persistent Header */}
      <div className="case-header">
        <div className="case-header-top">
          <div className="case-header-left">
            <Button
              variant="ghost"
              size="sm"
              icon={<ArrowLeft size={16} />}
              onClick={() => navigate('/cases')}
            >
              Back
            </Button>
            <div className="case-title-section">
              <h1 className="case-title">{activeCase.query}</h1>
            </div>
          </div>

          <div className="case-header-right">
            <div className="case-actions">
              <Button
                variant="secondary"
                size="sm"
                icon={<RefreshCw size={14} />}
                onClick={() => refetch()}
              >
                {/* The label is visually clipped (not removed) on phones so the
                    title keeps its full width; the accessible name is intact. */}
                <span className="case-header-action-label">Refresh</span>
              </Button>
            </div>
          </div>
        </div>

        {/* Metrics strip: the case identity (domain + ID) rides on the same
            dense row as every count and the status group, so no capability is
            dropped and the strip stays one row at any width. */}
        <div className="case-metrics-bar">
          <div className="case-meta">
            <Badge variant="neutral" size="sm">{activeCase.conflictDomain}</Badge>
            <span className="case-id">ID: {activeCase.id.slice(0, 8)}</span>
          </div>

          <div className="case-metric">
            <FileText size={14} />
            <span className="metric-label">Articles</span>
            <span className="metric-value">{activeCase.counts.articles}</span>
          </div>

          <div className="case-metric">
            <GitMerge size={14} />
            <span className="metric-label">Events</span>
            <span className="metric-value">{activeCase.counts.events}</span>
          </div>

          <div className="case-metric">
            <AlertTriangle size={14} />
            <span className="metric-label">Review Items</span>
            <span className="metric-value">{activeCase.counts.reviewItems}</span>
          </div>

          <div className="case-metric">
            <ShieldAlert size={14} />
            <span className="metric-label">Exceptions</span>
            <span className={`metric-value ${activeCase.openExceptionsCount > 0 ? 'has-exceptions' : ''}`}>
              {activeCase.openExceptionsCount}
            </span>
          </div>

          <div className="case-status-group">
            <StatusIndicator status={activeCase.status} size="sm" />
            <Badge variant="neutral" size="sm">{activeCase.stage}</Badge>
            <Badge variant="info" size="sm">{activeCase.automationMode}</Badge>
          </div>
        </div>
      </div>

      {/* Grouped case navigation: native links over the existing routes, no
          ARIA tab roles, so keyboard and screen-reader semantics stay standard. */}
      <nav className="case-tabs-nav" aria-label="Case views">
        <div className="case-nav-groups">
          {navGroups.map((group) => (
            <div className="case-nav-group" key={group.id}>
              <h2 className="case-nav-group-title" id={`case-nav-${group.id}`}>
                {group.label}
              </h2>
              <ul
                className="case-nav-list"
                aria-labelledby={`case-nav-${group.id}`}
              >
                {group.destinations.map((destination) => {
                  const isActive = currentView === destination.view;
                  return (
                    <li key={destination.view}>
                      <Link
                        to={hrefForView(destination.view)}
                        className={`case-tab ${isActive ? 'case-tab-active' : ''}`}
                        aria-current={isActive ? 'page' : undefined}
                        data-view={destination.view}
                      >
                        <span className="tab-icon">{destination.icon}</span>
                        <span className="tab-label">{destination.label}</span>
                        {destination.badge !== undefined && destination.badge > 0 && (
                          <span className="tab-badge">{destination.badge}</span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </nav>

      {/* Historical/current boundary: the decision above renders this state
          before any view consumer mounts. Only the explicit link below removes
          the historical selector, and it never revives a citation redirect. */}
      {routeDecision.kind === 'unsupported-history' ? (
        <div className="case-tab-content">
          <div className="case-history-unavailable" role="alert">
            <AlertTriangle size={24} />
            <div>
              <h3>Unsupported historical view</h3>
              <p>
                The {currentViewLabel} view only shows current data. This link carries a
                frozen snapshot selector ({routeDecision.snapshotId}), so live data is not
                shown here.
              </p>
              <div className="case-history-actions">
                <Link className="case-history-link" to={routeDecision.openCurrentHref}>
                  Open current {currentViewLabel}
                </Link>
              </div>
            </div>
          </div>
        </div>
      ) : routeDecision.kind === 'invalid-history' ? (
        <div className="case-tab-content">
          <div className="case-history-unavailable" role="alert">
            <AlertTriangle size={24} />
            <div>
              <h3>Invalid historical selector</h3>
              <p>
                {routeDecision.reason} The {currentViewLabel} view therefore does not render
                live data for this link, and the selector is not deleted for you.
              </p>
              <div className="case-history-actions">
                <Link className="case-history-link" to={routeDecision.openCurrentHref}>
                  Open current {currentViewLabel}
                </Link>
              </div>
            </div>
          </div>
        </div>
      ) : routeDecision.kind === 'citation-conflict' ? (
        <div className="case-tab-content">
          <div className="case-history-unavailable" role="alert">
            <AlertTriangle size={24} />
            <div>
              <h3>Snapshot and citation selectors conflict</h3>
              <p>
                This link pins observation {shortenSnapshotId(routeDecision.snapshotId)} and
                also names a frozen citation. A citation is frozen by its own ID, so it proves
                nothing about that observation: neither is loaded here. Choose which one you
                meant.
              </p>
              <div className="case-history-actions">
                <Link className="case-history-link" to={routeDecision.keepSnapshotHref}>
                  Keep snapshot {shortenSnapshotId(routeDecision.snapshotId)}
                </Link>
                <Link className="case-history-link" to={routeDecision.citationHref}>
                  Open frozen citation by ID
                </Link>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="case-tab-content" key={id}>
          <Routes>
            <Route
              index
              element={
                <OverviewTab
                  activeCase={activeCase}
                  caseDetail={detailData}
                />
              }
            />
            <Route
              path="evidence"
              element={<EvidenceTab caseId={id!} />}
            />
            <Route
              path="claims"
              element={<ClaimsTab caseId={id!} />}
            />
            <Route
              path="compare"
              element={<CompareTab caseId={id!} />}
            />
            <Route
              path="exceptions"
              element={
                <ExceptionsTab
                  caseId={id!}
                />
              }
            />
            <Route
              path="parties"
              element={<PartiesTab caseId={id!} />}
            />
            <Route
              path="map"
              element={<MapTab caseId={id!} />}
            />
            <Route
              path="timeline"
              element={<TimelineTab caseId={id!} />}
            />
            <Route
              path="report"
              element={<ReportTab caseId={id!} />}
            />
            <Route
              path="changes"
              element={<ChangesTab caseId={id!} />}
            />
            <Route
              path="search"
              element={<SearchTab caseId={id!} />}
            />
            <Route
              path="run-history"
              element={<RunHistoryTab caseId={id!} />}
            />
            <Route path="*" element={<div>Tab not found</div>} />
          </Routes>
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// F04 — review / annotation write-state model
// ---------------------------------------------------------------------------
//
// Every write form/row owns one of these states. They are distinguished by
// their own words (not colour) so an operator can tell a writer conflict from a
// rejected target, a lost response from a saved write, and a stale form from a
// fresh one. `retry: false` on the mutations means nothing here ever repeats a
// POST by itself: only the operator can, and only after confirming.

type WriteStateKind =
  | 'idle'
  | 'pending'
  | 'saved'
  | 'conflict'
  | 'blocked'
  | 'failed'
  | 'uncertain'
  | 'reconciled'
  | 'refresh-failed'
  | 'stale';

interface WriteState {
  kind: WriteStateKind;
  detail?: string | null;
  /** `dataUpdatedAt` of the read refresh that proved this save. */
  epoch?: number;
}

const IDLE_WRITE_STATE: WriteState = { kind: 'idle' };

type ActiveWriteKind = Exclude<WriteStateKind, 'idle'>;

interface WriteStateCopy {
  label: string;
  text: string;
  tone: 'success' | 'warning' | 'danger' | 'info';
  role: 'status' | 'alert';
}

const WRITE_STATE_COPY: Record<ActiveWriteKind, WriteStateCopy> = {
  pending: {
    label: 'Saving…',
    text: 'Saving: only this form is disabled while the server answers.',
    tone: 'info',
    role: 'status',
  },
  saved: {
    label: 'Saved and refreshed',
    text: 'The server acknowledged this write and the recorded read was refreshed.',
    tone: 'success',
    role: 'status',
  },
  conflict: {
    label: 'Writer conflict (409)',
    text: 'Another writer currently holds this case. Nothing from this form was changed; retry only after the other writer finishes.',
    tone: 'warning',
    role: 'alert',
  },
  blocked: {
    label: 'Blocked (422)',
    text: 'The server rejected this write as invalid or not permitted for this case. No record was changed.',
    tone: 'danger',
    role: 'alert',
  },
  failed: {
    label: 'Rejected by the server',
    text: 'The server answered with an error and rejected this write.',
    tone: 'danger',
    role: 'alert',
  },
  uncertain: {
    label: 'Outcome unknown',
    text: 'The response was lost, so the server may or may not have recorded this write. Reconcile with a read before retrying; never repeat it blindly.',
    tone: 'warning',
    role: 'alert',
  },
  reconciled: {
    label: 'Read refreshed — still inconclusive',
    text: 'The read cannot prove whether this write landed. A manual retry requires your explicit confirmation and may append a duplicate record.',
    tone: 'warning',
    role: 'alert',
  },
  'refresh-failed': {
    label: 'Accepted; refresh failed',
    text: 'The server acknowledged this write, but the follow-up read failed. Retry the read only — do not resubmit the write.',
    tone: 'warning',
    role: 'alert',
  },
  stale: {
    label: 'Stale',
    text: 'A recorded invalidation or detected refresh happened after this form was saved. Re-check the latest recorded state before saving again.',
    tone: 'warning',
    role: 'status',
  },
};

const WRITE_TONE_COLOR: Record<WriteStateCopy['tone'], string> = {
  success: '#00ff9d',
  warning: '#ffb800',
  danger: '#ff4757',
  info: '#00d4ff',
};

/**
 * Classify a failed POST.
 *
 * Only the statuses this service uses to refuse a write before it is applied are
 * proof of refusal: 409 (writer conflict at admission), 422 (invalid/blocked
 * target) and the known 404 (missing case/exception). Any other response — a 5xx,
 * an unexpected 4xx, or no response at all — can arrive after the write
 * committed, so it is an unknown outcome, never a rejection.
 */
function writeStateFromError(error: unknown): WriteState {
  if (error instanceof ApiError) {
    if (error.status === 409) return { kind: 'conflict', detail: error.message };
    if (error.status === 422) return { kind: 'blocked', detail: error.message };
    if (error.status === 404) return { kind: 'failed', detail: `404: ${error.message}` };
    return {
      kind: 'uncertain',
      detail: `The server answered ${error.status} (${error.message}); that is not proof this write was refused.`,
    };
  }
  // No HTTP response at all: the transport outcome is genuinely unknown.
  return { kind: 'uncertain', detail: messageOf(error) };
}

function messageOf(error: unknown): string | null {
  return error instanceof Error ? error.message : null;
}

/**
 * States in which an ordinary POST is forbidden for this operation: an attempt is
 * in flight, the server acknowledged a write whose read failed, the outcome is
 * unknown, or a read reconciled it without proof. Only a deliberate submit from
 * idle/saved/stale/conflict/blocked/failed — or one explicitly confirmed retry —
 * may POST again.
 */
function blocksOrdinaryPost(state: WriteState, recoveryPending: boolean): boolean {
  if (recoveryPending) return true;
  return (
    state.kind === 'pending' ||
    state.kind === 'refresh-failed' ||
    state.kind === 'uncertain' ||
    state.kind === 'reconciled'
  );
}

/**
 * One review/annotation write operation.
 *
 * The submitted payload is kept apart from the editable draft (a confirmed retry
 * sends exactly this payload, never the current selection or edited text), the
 * attempt identity stops a late callback from unlocking a newer attempt, and
 * `recoveryPending` prevents duplicate recovery GETs.
 */
interface WriteAttempt<P> {
  state: WriteState;
  attemptId: number;
  payload: P | null;
  recoveryPending: boolean;
}

interface ReviewAttemptInput {
  payload: ReviewRetryPayload;
  attemptId: number;
}

interface AnnotationAttemptInput {
  payload: AnnotationRetryPayload;
  attemptId: number;
}

function idleWriteAttempt<P>(): WriteAttempt<P> {
  return { state: IDLE_WRITE_STATE, attemptId: 0, payload: null, recoveryPending: false };
}

function isCurrentAttempt<P>(attempt: WriteAttempt<P>, attemptId: number): boolean {
  return attempt.attemptId === attemptId;
}

interface ReviewFormRecord {
  notes: string;
  annotationContent: string;
  annotationType: string;
  annotationTargetType: AnnotationTargetType;
  annotationTargetId: string;
  review: WriteAttempt<ReviewRetryPayload>;
  annotation: WriteAttempt<AnnotationRetryPayload>;
}

function emptyReviewFormRecord(): ReviewFormRecord {
  return {
    notes: '',
    annotationContent: '',
    annotationType: 'comment',
    annotationTargetType: 'case',
    annotationTargetId: '',
    review: idleWriteAttempt(),
    annotation: idleWriteAttempt(),
  };
}

// In-memory, page-lifetime ownership. The case workspace unmounts this tab on a
// view switch, so an unresolved write's lock has to outlive the tab. Records are
// keyed by case id, so a late case A outcome can never reach a case B form, and
// nothing here is persisted: a reload starts from the server's recorded state.
// `Map` is the lucide icon in this module, so the record map is explicit.
const reviewFormRecords = new globalThis.Map<string, ReviewFormRecord>();

function reviewFormRecord(caseId: string): ReviewFormRecord {
  const existing = reviewFormRecords.get(caseId);
  if (existing) return existing;
  const created = emptyReviewFormRecord();
  reviewFormRecords.set(caseId, created);
  return created;
}

/** An ack proves nothing unless it identifies the entry the server recorded. */
function annotationAckMatches(ack: unknown): boolean {
  const id = (ack as { id?: unknown } | null)?.id;
  return typeof id === 'string' && id.length > 0;
}

function caseAckMatches(ack: unknown, caseId: string): boolean {
  return (ack as { id?: unknown } | null)?.id === caseId;
}

const WriteStateBanner: React.FC<{ state: WriteState; children?: React.ReactNode }> = ({
  state,
  children,
}) => {
  if (state.kind === 'idle') return null;
  const copy = WRITE_STATE_COPY[state.kind];
  const color = WRITE_TONE_COLOR[copy.tone];
  return (
    <div
      role={copy.role}
      data-write-state={state.kind}
      aria-live={copy.role === 'status' ? 'polite' : undefined}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.375rem',
        padding: '0.75rem',
        borderRadius: 'var(--radius-sm)',
        border: `1px solid ${color}33`,
        background: `${color}1a`,
        color,
        fontSize: '0.8125rem',
      }}
    >
      <strong>{copy.label}</strong>
      <span>{copy.text}</span>
      {state.detail && <span>{state.detail}</span>}
      {children}
    </div>
  );
};

// ---------------------------------------------------------------------------
// F04 — contextual annotation targets (current-case entities only)
// ---------------------------------------------------------------------------

type AnnotationTargetType = 'case' | 'claim' | 'evidence' | 'exception' | 'narrative';

const ANNOTATION_TARGET_TYPES: readonly AnnotationTargetType[] = [
  'case',
  'claim',
  'evidence',
  'exception',
  'narrative',
];

const ANNOTATION_TARGET_LABEL: Record<AnnotationTargetType, string> = {
  case: 'Case',
  claim: 'Claim',
  evidence: 'Evidence',
  exception: 'Exception',
  narrative: 'Narrative',
};

interface AnnotationTargetOption {
  id: string;
  label: string;
  readOnly?: boolean;
  readOnlyReason?: string;
}

function truncateLabel(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function formatActivityTimestamp(value: string | null): string {
  return value ? value.slice(0, 16).replace('T', ' ') : 'n/a';
}

interface ReviewRetryPayload {
  caseId: string;
  decision: string;
  notes: string;
}

interface AnnotationRetryPayload {
  caseId: string;
  targetType: AnnotationTargetType;
  targetId: string;
  annotationType: string;
  content: string;
}

// Overview Tab Component
const OverviewTab: React.FC<{
  activeCase: TopicCase;
  caseDetail?: CaseDetail;
}> = ({ activeCase, caseDetail }) => {
  const queryClient = useQueryClient();
  const caseId = activeCase.id;

  // A late submit response for case A must never alter a case B form.
  const caseIdRef = useRef(caseId);
  // The editable draft, the submitted payloads and the write states live in one
  // in-memory record per case so a same-case view switch cannot unlock a write.
  const [form, setForm] = useState<ReviewFormRecord>(() => reviewFormRecord(caseId));

  useEffect(() => {
    caseIdRef.current = caseId;
    setForm(reviewFormRecord(caseId));
  }, [caseId]);

  /**
   * Apply a record update for `targetCaseId`. Reads come from the in-memory
   * record, so a disclosure sent before React re-renders already sees the new
   * state; only the mounted case is mirrored into component state.
   */
  const commitRecord = useCallback(
    (targetCaseId: string, update: (record: ReviewFormRecord) => ReviewFormRecord) => {
      const next = update(reviewFormRecord(targetCaseId));
      reviewFormRecords.set(targetCaseId, next);
      if (targetCaseId === caseIdRef.current) setForm(next);
      return next;
    },
    []
  );

  const {
    data: reviewActivity,
    dataUpdatedAt: activityUpdatedAt,
    isLoading: activityLoading,
    error: activityError,
    refetch: refetchActivity,
  } = useQuery({
    queryKey: ['reviewActivity', caseId],
    queryFn: () => getReviewActivityForCase(caseId),
    enabled: !!caseId,
  });

  const {
    data: evaluation,
    isLoading: evaluationLoading,
    error: evaluationError,
    refetch: refetchEvaluation,
  } = useQuery({
    queryKey: ['evaluationSummary', caseId],
    queryFn: () => getEvaluationForCase(caseId),
    enabled: !!caseId,
  });

  // A reported save requires a successful server ack *and* a successful read.
  const refreshReviewReads = async (submittedCaseId: string) => {
    const [refreshedDetail, refreshedActivity] = await Promise.all([
      getCaseDetail(submittedCaseId),
      getReviewActivityForCase(submittedCaseId),
    ]);
    queryClient.setQueryData(['caseDetail', submittedCaseId], refreshedDetail);
    queryClient.setQueryData(['reviewActivity', submittedCaseId], refreshedActivity);
    await queryClient.invalidateQueries({ queryKey: ['cases'] });
  };

  const readEpoch = (submittedCaseId: string) =>
    queryClient.getQueryState(['reviewActivity', submittedCaseId])?.dataUpdatedAt ?? 0;

  const reviewMutation = useMutation({
    // A review write is never repeated automatically.
    retry: false,
    mutationFn: (attempt: ReviewAttemptInput) =>
      submitCaseReviewAction(
        attempt.payload.caseId,
        attempt.payload.decision,
        attempt.payload.notes
      ),
    onSuccess: async (ack, attempt) => {
      const { payload, attemptId } = attempt;
      if (!caseAckMatches(ack, payload.caseId)) {
        // An ack that cannot identify the recorded case is not proof of success.
        commitRecord(payload.caseId, (record) =>
          isCurrentAttempt(record.review, attemptId)
            ? {
                ...record,
                review: {
                  ...record.review,
                  state: {
                    kind: 'uncertain',
                    detail:
                      'The server answered without identifying the recorded case, so whether this write landed is unknown.',
                  },
                },
              }
            : record
        );
        return;
      }
      try {
        await refreshReviewReads(payload.caseId);
      } catch (refreshError) {
        commitRecord(payload.caseId, (record) =>
          isCurrentAttempt(record.review, attemptId)
            ? {
                ...record,
                review: {
                  ...record.review,
                  state: { kind: 'refresh-failed', detail: messageOf(refreshError) },
                },
              }
            : record
        );
        return;
      }
      const epoch = readEpoch(payload.caseId);
      commitRecord(payload.caseId, (record) =>
        isCurrentAttempt(record.review, attemptId)
          ? {
              ...record,
              // Cleared only for the acknowledged submission, and only while the
              // draft still matches it: newer edits are never overwritten.
              notes: record.notes === payload.notes ? '' : record.notes,
              review: {
                state: { kind: 'saved', epoch },
                attemptId,
                payload: null,
                recoveryPending: false,
              },
            }
          : record
      );
    },
    onError: (error, attempt) => {
      const { payload, attemptId } = attempt;
      commitRecord(payload.caseId, (record) =>
        isCurrentAttempt(record.review, attemptId)
          ? { ...record, review: { ...record.review, state: writeStateFromError(error) } }
          : record
      );
    },
  });

  const annotationMutation = useMutation({
    retry: false,
    mutationFn: (attempt: AnnotationAttemptInput) =>
      createCaseAnnotation(attempt.payload.caseId, {
        targetType: attempt.payload.targetType,
        targetId: attempt.payload.targetId,
        annotationType: attempt.payload.annotationType,
        content: attempt.payload.content,
      }),
    onSuccess: async (ack, attempt) => {
      const { payload, attemptId } = attempt;
      if (!annotationAckMatches(ack)) {
        commitRecord(payload.caseId, (record) =>
          isCurrentAttempt(record.annotation, attemptId)
            ? {
                ...record,
                annotation: {
                  ...record.annotation,
                  state: {
                    kind: 'uncertain',
                    detail:
                      'The server answered without identifying the recorded annotation, so whether this write landed is unknown.',
                  },
                },
              }
            : record
        );
        return;
      }
      try {
        await refreshReviewReads(payload.caseId);
      } catch (refreshError) {
        commitRecord(payload.caseId, (record) =>
          isCurrentAttempt(record.annotation, attemptId)
            ? {
                ...record,
                annotation: {
                  ...record.annotation,
                  state: { kind: 'refresh-failed', detail: messageOf(refreshError) },
                },
              }
            : record
        );
        return;
      }
      const epoch = readEpoch(payload.caseId);
      commitRecord(payload.caseId, (record) =>
        isCurrentAttempt(record.annotation, attemptId)
          ? {
              ...record,
              annotationContent:
                record.annotationContent === payload.content ? '' : record.annotationContent,
              annotation: {
                state: { kind: 'saved', epoch },
                attemptId,
                payload: null,
                recoveryPending: false,
              },
            }
          : record
      );
    },
    onError: (error, attempt) => {
      const { payload, attemptId } = attempt;
      commitRecord(payload.caseId, (record) =>
        isCurrentAttempt(record.annotation, attemptId)
          ? { ...record, annotation: { ...record.annotation, state: writeStateFromError(error) } }
          : record
      );
    },
  });

  // "Detected refresh": once a later read lands, an earlier saved banner is
  // stale evidence, so it must not keep claiming a fresh save.
  useEffect(() => {
    const record = reviewFormRecord(caseId);
    const savedBeyond = (state: WriteState) =>
      state.kind === 'saved' && typeof state.epoch === 'number' && activityUpdatedAt > state.epoch;
    if (savedBeyond(record.review.state)) {
      commitRecord(caseId, (current) =>
        isCurrentAttempt(current.review, record.review.attemptId) &&
        current.review.state.kind === 'saved'
          ? { ...current, review: { ...current.review, state: { kind: 'stale' } } }
          : current
      );
    }
    if (savedBeyond(record.annotation.state)) {
      commitRecord(caseId, (current) =>
        isCurrentAttempt(current.annotation, record.annotation.attemptId) &&
        current.annotation.state.kind === 'saved'
          ? { ...current, annotation: { ...current.annotation, state: { kind: 'stale' } } }
          : current
      );
    }
  }, [activityUpdatedAt, caseId, commitRecord]);

  const updateForm = (patch: Partial<ReviewFormRecord>) =>
    commitRecord(caseId, (record) => ({ ...record, ...patch }));

  /**
   * Start one attempt. The record is written synchronously so a second dispatch
   * in the same tick (rapid click, keyboard repeat) sees the lock before React
   * re-renders.
   */
  const startReviewAttempt = (payload: ReviewRetryPayload) => {
    const record = reviewFormRecord(payload.caseId);
    if (record.review.recoveryPending || record.review.state.kind === 'pending') return;
    const attemptId = record.review.attemptId + 1;
    commitRecord(payload.caseId, (current) => ({
      ...current,
      review: { state: { kind: 'pending' }, attemptId, payload, recoveryPending: false },
    }));
    reviewMutation.mutate({ payload, attemptId });
  };

  const submitReview = (decision: string) => {
    const record = reviewFormRecord(caseId);
    if (blocksOrdinaryPost(record.review.state, record.review.recoveryPending)) return;
    startReviewAttempt({ caseId, decision, notes: record.notes });
  };

  // One explicit confirmation sends exactly the immutable submitted payload.
  const confirmReviewRetry = () => {
    const record = reviewFormRecord(caseId);
    if (record.review.state.kind !== 'reconciled' || record.review.recoveryPending) return;
    const payload = record.review.payload;
    // Never retry against a switched case or an unknown payload.
    if (!payload || payload.caseId !== caseId) return;
    startReviewAttempt(payload);
  };

  /** Recovery after an acknowledged write: the read only, never a resubmission. */
  const retryReviewRefresh = async () => {
    const review = reviewFormRecord(caseId).review;
    const { attemptId, payload } = review;
    if (review.state.kind !== 'refresh-failed' || review.recoveryPending) return;
    commitRecord(caseId, (current) =>
      isCurrentAttempt(current.review, attemptId)
        ? { ...current, review: { ...current.review, recoveryPending: true } }
        : current
    );
    let epoch: number;
    try {
      await refreshReviewReads(caseId);
      epoch = readEpoch(caseId);
    } catch (refreshError) {
      // A failed recovery preserves the retry capability for the read.
      commitRecord(caseId, (current) =>
        isCurrentAttempt(current.review, attemptId) &&
        current.review.state.kind === 'refresh-failed'
          ? {
              ...current,
              review: {
                ...current.review,
                recoveryPending: false,
                state: { kind: 'refresh-failed', detail: messageOf(refreshError) },
              },
            }
          : current
      );
      return;
    }
    commitRecord(caseId, (current) => {
      if (
        !isCurrentAttempt(current.review, attemptId) ||
        current.review.state.kind !== 'refresh-failed'
      ) {
        return current;
      }
      return {
        ...current,
        notes: payload && current.notes === payload.notes ? '' : current.notes,
        review: {
          state: { kind: 'saved', epoch },
          attemptId,
          payload: null,
          recoveryPending: false,
        },
      };
    });
  };

  // GET-only reconciliation. It never concludes that the write landed.
  const reconcileReview = async () => {
    const review = reviewFormRecord(caseId).review;
    const { attemptId } = review;
    if (review.state.kind !== 'uncertain' || review.recoveryPending) return;
    commitRecord(caseId, (current) =>
      isCurrentAttempt(current.review, attemptId)
        ? { ...current, review: { ...current.review, recoveryPending: true } }
        : current
    );
    try {
      await refreshReviewReads(caseId);
      commitRecord(caseId, (current) =>
        isCurrentAttempt(current.review, attemptId) && current.review.state.kind === 'uncertain'
          ? {
              ...current,
              review: {
                ...current.review,
                recoveryPending: false,
                state: { kind: 'reconciled', detail: current.review.state.detail ?? null },
              },
            }
          : current
      );
    } catch (refreshError) {
      commitRecord(caseId, (current) =>
        isCurrentAttempt(current.review, attemptId) && current.review.state.kind === 'uncertain'
          ? {
              ...current,
              review: {
                ...current.review,
                recoveryPending: false,
                state: {
                  kind: 'uncertain',
                  detail: `Reconciliation read failed: ${
                    messageOf(refreshError) ?? 'unknown error'
                  }`,
                },
              },
            }
          : current
      );
    }
  };

  const targetOptions = useMemo<Record<AnnotationTargetType, AnnotationTargetOption[]>>(() => {
    const tabs = caseDetail?.tabs;
    return {
      case: [{ id: caseId, label: `${activeCase.query} (this case)` }],
      claim: (tabs?.claims ?? []).map((claim) => {
        const readOnly = claim.isFrozen === true || claim.isRemoved === true;
        return {
          id: claim.id,
          label: truncateLabel(claim.text || claim.id, 90),
          readOnly,
          readOnlyReason: claim.isRemoved ? 'removed' : claim.isFrozen ? 'frozen' : undefined,
        };
      }),
      evidence: (tabs?.evidence ?? []).map((evidence) => ({
        id: evidence.id,
        label: truncateLabel(evidence.title || evidence.id, 90),
      })),
      exception: (tabs?.exceptions ?? []).map((exception) => ({
        id: exception.id,
        label: truncateLabel(
          `${exception.type.replace(/_/g, ' ')}: ${exception.message}`,
          90
        ),
      })),
      narrative: (tabs?.narratives ?? []).map((narrative) => ({
        id: narrative.id,
        label: truncateLabel(narrative.stanceSummary || narrative.clusterId, 90),
      })),
    };
  }, [caseDetail, caseId, activeCase.query]);

  const currentTargetOptions = targetOptions[form.annotationTargetType];
  const effectiveTargetId =
    form.annotationTargetType === 'case' ? caseId : form.annotationTargetId;
  const selectedTarget = currentTargetOptions.find(
    (option) => option.id === effectiveTargetId && !option.readOnly
  );
  const targetProblem =
    effectiveTargetId && !selectedTarget
      ? `The selected ${form.annotationTargetType} is not part of the current case (removed or frozen); it cannot be annotated.`
      : currentTargetOptions.length === 0
        ? `No ${form.annotationTargetType} records exist in this case, so no target can be offered.`
        : !effectiveTargetId
          ? `Select a ${form.annotationTargetType} recorded in this case.`
          : null;

  const changeTargetType = (nextType: AnnotationTargetType) =>
    updateForm({ annotationTargetType: nextType, annotationTargetId: '' });

  /** A confirmed retry may not use a target that left the current case. */
  const annotationTargetEligible = (payload: AnnotationRetryPayload) => {
    if (payload.caseId !== caseId) return false;
    const options = targetOptions[payload.targetType] ?? [];
    return options.some((option) => option.id === payload.targetId && !option.readOnly);
  };

  const startAnnotationAttempt = (payload: AnnotationRetryPayload) => {
    const record = reviewFormRecord(payload.caseId);
    if (record.annotation.recoveryPending || record.annotation.state.kind === 'pending') return;
    const attemptId = record.annotation.attemptId + 1;
    commitRecord(payload.caseId, (current) => ({
      ...current,
      annotation: { state: { kind: 'pending' }, attemptId, payload, recoveryPending: false },
    }));
    annotationMutation.mutate({ payload, attemptId });
  };

  const submitAnnotation = () => {
    const record = reviewFormRecord(caseId);
    if (blocksOrdinaryPost(record.annotation.state, record.annotation.recoveryPending)) return;
    if (targetProblem || !record.annotationContent.trim()) return;
    startAnnotationAttempt({
      caseId,
      targetType: record.annotationTargetType,
      targetId: record.annotationTargetType === 'case' ? caseId : record.annotationTargetId,
      annotationType: record.annotationType,
      content: record.annotationContent,
    });
  };

  /** One explicit confirmation sends exactly the submitted payload, or nothing. */
  const confirmAnnotationRetry = () => {
    const record = reviewFormRecord(caseId);
    if (record.annotation.state.kind !== 'reconciled' || record.annotation.recoveryPending) return;
    const payload = record.annotation.payload;
    if (!payload) return;
    if (!annotationTargetEligible(payload)) {
      commitRecord(caseId, (current) =>
        isCurrentAttempt(current.annotation, record.annotation.attemptId)
          ? {
              ...current,
              annotation: {
                ...current.annotation,
                state: {
                  kind: 'reconciled',
                  detail:
                    'The originally submitted target is no longer an annotatable entity of this case, so the retry was refused without sending anything.',
                },
              },
            }
          : current
      );
      return;
    }
    startAnnotationAttempt(payload);
  };

  /** Recovery after an acknowledged write: the read only, never a resubmission. */
  const retryAnnotationRefresh = async () => {
    const annotation = reviewFormRecord(caseId).annotation;
    const { attemptId, payload } = annotation;
    if (annotation.state.kind !== 'refresh-failed' || annotation.recoveryPending) return;
    commitRecord(caseId, (current) =>
      isCurrentAttempt(current.annotation, attemptId)
        ? { ...current, annotation: { ...current.annotation, recoveryPending: true } }
        : current
    );
    let epoch: number;
    try {
      await refreshReviewReads(caseId);
      epoch = readEpoch(caseId);
    } catch (refreshError) {
      commitRecord(caseId, (current) =>
        isCurrentAttempt(current.annotation, attemptId) &&
        current.annotation.state.kind === 'refresh-failed'
          ? {
              ...current,
              annotation: {
                ...current.annotation,
                recoveryPending: false,
                state: { kind: 'refresh-failed', detail: messageOf(refreshError) },
              },
            }
          : current
      );
      return;
    }
    commitRecord(caseId, (current) => {
      if (
        !isCurrentAttempt(current.annotation, attemptId) ||
        current.annotation.state.kind !== 'refresh-failed'
      ) {
        return current;
      }
      return {
        ...current,
        annotationContent:
          payload && current.annotationContent === payload.content
            ? ''
            : current.annotationContent,
        annotation: {
          state: { kind: 'saved', epoch },
          attemptId,
          payload: null,
          recoveryPending: false,
        },
      };
    });
  };

  // GET-only reconciliation. It never concludes that the write landed.
  const reconcileAnnotation = async () => {
    const annotation = reviewFormRecord(caseId).annotation;
    const { attemptId } = annotation;
    if (annotation.state.kind !== 'uncertain' || annotation.recoveryPending) return;
    commitRecord(caseId, (current) =>
      isCurrentAttempt(current.annotation, attemptId)
        ? { ...current, annotation: { ...current.annotation, recoveryPending: true } }
        : current
    );
    try {
      await refreshReviewReads(caseId);
      commitRecord(caseId, (current) =>
        isCurrentAttempt(current.annotation, attemptId) &&
        current.annotation.state.kind === 'uncertain'
          ? {
              ...current,
              annotation: {
                ...current.annotation,
                recoveryPending: false,
                state: { kind: 'reconciled', detail: current.annotation.state.detail ?? null },
              },
            }
          : current
      );
    } catch (refreshError) {
      commitRecord(caseId, (current) =>
        isCurrentAttempt(current.annotation, attemptId) &&
        current.annotation.state.kind === 'uncertain'
          ? {
              ...current,
              annotation: {
                ...current.annotation,
                recoveryPending: false,
                state: {
                  kind: 'uncertain',
                  detail: `Reconciliation read failed: ${
                    messageOf(refreshError) ?? 'unknown error'
                  }`,
                },
              },
            }
          : current
      );
    }
  };

  const latestEvaluation = evaluation?.latest;
  const evaluationScore =
    typeof latestEvaluation?.summary?.overall_score === 'number'
      ? String(latestEvaluation.summary.overall_score)
      : null;

  // Human annotations and mirrored `annotation:*` audit entries are partitioned
  // by array membership and labelled. Nothing is deduplicated by text or time.
  const humanNotes = [...(reviewActivity?.annotations ?? [])]
    .sort((a, b) => (b.createdAt || '').localeCompare(a.createdAt || ''))
    .slice(0, 20);
  const technicalAudit = [...(reviewActivity?.auditEntries ?? [])]
    .sort((a, b) => (b.createdAt || '').localeCompare(a.createdAt || ''))
    .slice(0, 20);
  // Render-time lock; the dispatch guards read the same record synchronously.
  const reviewLocked = blocksOrdinaryPost(form.review.state, form.review.recoveryPending);
  const annotationLocked = blocksOrdinaryPost(
    form.annotation.state,
    form.annotation.recoveryPending
  );
  const operatorCommands = buildOperatorCommands(activeCase);

  return (
    <div className="overview-tab">
      <div className="overview-grid">
        {/* Case Information */}
        <Card className="overview-card">
          <CardHeader>
            <CardTitle>Case Information</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="info-list">
              <div className="info-item">
                <span className="info-label">Query</span>
                <span className="info-value">{activeCase.query}</span>
              </div>
              <div className="info-item">
                <span className="info-label">Conflict Domain</span>
                <span className="info-value">{activeCase.conflictDomain}</span>
              </div>
              <div className="info-item">
                <span className="info-label">Status</span>
                <StatusIndicator status={activeCase.status} size="sm" />
              </div>
              <div className="info-item">
                <span className="info-label">Current Stage</span>
                <Badge variant="neutral" size="sm">{activeCase.stage}</Badge>
              </div>
              <div className="info-item">
                <span className="info-label">Automation Mode</span>
                <Badge variant="info" size="sm">{activeCase.automationMode}</Badge>
              </div>
              <div className="info-item">
                <span className="info-label">Has New Material</span>
                <Badge variant={activeCase.hasNewMaterial ? 'success' : 'neutral'} size="sm">
                  {activeCase.hasNewMaterial ? 'Yes' : 'No'}
                </Badge>
              </div>
            </div>
          </CardBody>
        </Card>

        <Card className="overview-card">
          <CardHeader>
            <CardTitle>Operator Commands</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="review-actions" data-write-scope="review">
              <p className="review-description">Use narrow in-app review controls for approvals and notes, with CLI commands still available for reruns and deeper operations.</p>
              <textarea
                value={form.notes}
                onChange={(event) => updateForm({ notes: event.target.value })}
                placeholder="Decision rationale or handoff notes"
                aria-label="Review notes"
                style={{
                  width: '100%',
                  minHeight: '84px',
                  borderRadius: '12px',
                  background: 'rgba(10, 19, 31, 0.68)',
                  color: 'inherit',
                  border: '1px solid rgba(133, 157, 186, 0.24)',
                  padding: '0.85rem',
                  marginBottom: '0.85rem',
                }}
              />
              <div className="action-buttons">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => submitReview('approve')}
                  disabled={reviewLocked}
                >
                  Approve
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => submitReview('action_required')}
                  disabled={reviewLocked}
                >
                  Action Required
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => submitReview('reject')}
                  disabled={reviewLocked}
                >
                  Reject
                </Button>
              </div>
              <WriteStateBanner state={form.review.state}>
                {form.review.recoveryPending && (
                  <p role="status">Read-only recovery request in progress…</p>
                )}
                {form.review.state.kind === 'refresh-failed' && (
                  <div>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => void retryReviewRefresh()}
                      disabled={form.review.recoveryPending}
                    >
                      {form.review.recoveryPending ? 'Retrying refresh…' : 'Retry refresh (GET)'}
                    </Button>
                  </div>
                )}
                {form.review.state.kind === 'uncertain' && (
                  <div>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => void reconcileReview()}
                      disabled={form.review.recoveryPending}
                    >
                      {form.review.recoveryPending ? 'Reconciling…' : 'Reconcile with read (GET)'}
                    </Button>
                  </div>
                )}
                {form.review.state.kind === 'reconciled' && (
                  <div>
                    <p style={{ marginBottom: '0.375rem' }}>
                      Retrying this decision may append a duplicate audit entry; it does not edit the
                      earlier one.
                    </p>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={confirmReviewRetry}
                      disabled={form.review.recoveryPending}
                    >
                      Confirm retry
                    </Button>
                  </div>
                )}
              </WriteStateBanner>
              {activeCase.openExceptionsCount > 0 && (
                <div className="review-warning">
                  <AlertTriangle size={14} />
                  <span>
                    {activeCase.openExceptionsCount} open exception
                    {activeCase.openExceptionsCount > 1 ? 's remain' : ' remains'} in the operator queue.
                  </span>
                </div>
              )}
              <div className="review-label" style={{ marginTop: '1rem', marginBottom: '0.375rem' }}>
                <TerminalSquare size={14} /> CLI fallback
              </div>
              <div className="action-buttons" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                {operatorCommands.map((command) => (
                  <div key={command.label}>
                    <div className="review-label" style={{ marginBottom: '0.375rem' }}>
                      <TerminalSquare size={14} /> {command.label}
                    </div>
                    <code className="review-value" style={{ display: 'block' }}>{command.command}</code>
                  </div>
                ))}
              </div>
            </div>
          </CardBody>
        </Card>

        <Card className="overview-card">
          <CardHeader>
            <CardTitle>Evaluation Snapshot</CardTitle>
          </CardHeader>
          <CardBody>
            {evaluationLoading ? (
              <ReaderState
                state="loading"
                title="Loading evaluation"
                description="Fetching the saved evaluation for this case."
              />
            ) : evaluationError ? (
              <ReaderState
                state="network-error"
                title="Evaluation unavailable"
                description="The saved evaluation could not be read. This is not the same as no saved evaluation."
                detail={evaluationError instanceof Error ? evaluationError.message : null}
                onRetry={() => void refetchEvaluation()}
              />
            ) : !latestEvaluation ? (
              <ReaderState
                state="empty"
                title="No saved evaluation"
                description="The server has recorded no evaluation for this case. Viewing this page creates nothing."
              />
            ) : (
              <div className="info-list" data-testid="evaluation-snapshot">
                <div className="info-item">
                  <span className="info-label">Overall score</span>
                  <span className="info-value">{evaluationScore ?? 'n/a'}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Evidence linkage</span>
                  <span className="info-value">{String(latestEvaluation.metrics?.evidence_linkage ?? 'n/a')}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Review burden</span>
                  <span className="info-value">{String(latestEvaluation.metrics?.review_burden ?? 'n/a')}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Pipeline resilience</span>
                  <span className="info-value">{String(latestEvaluation.metrics?.pipeline_resilience ?? 'n/a')}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Last evaluated</span>
                  <span className="info-value">{latestEvaluation.createdAt ?? 'Not recorded'}</span>
                </div>
              </div>
            )}
          </CardBody>
        </Card>

        <Card className="overview-card">
          <CardHeader>
            <CardTitle>Annotations</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="review-actions" data-write-scope="annotation">
              <div className="action-buttons" style={{ marginBottom: '0.75rem' }}>
                <select
                  value={form.annotationType}
                  onChange={(e) => updateForm({ annotationType: e.target.value })}
                >
                  <option value="comment">Comment</option>
                  <option value="flag">Flag</option>
                  <option value="context">Context</option>
                </select>
                <select
                  value={form.annotationTargetType}
                  aria-label="Annotation target type"
                  onChange={(e) => changeTargetType(e.target.value as AnnotationTargetType)}
                >
                  {ANNOTATION_TARGET_TYPES.map((targetType) => (
                    <option key={targetType} value={targetType}>
                      {ANNOTATION_TARGET_LABEL[targetType]}
                    </option>
                  ))}
                </select>
              </div>
              {form.annotationTargetType === 'case' ? (
                <input
                  value={`${activeCase.query} (${caseId})`}
                  readOnly
                  aria-label="Annotation target"
                  style={{
                    width: '100%',
                    borderRadius: '12px',
                    background: 'rgba(10, 19, 31, 0.4)',
                    color: 'inherit',
                    border: '1px solid rgba(133, 157, 186, 0.24)',
                    padding: '0.75rem',
                    marginBottom: '0.75rem',
                  }}
                />
              ) : currentTargetOptions.length === 0 ? (
                <p
                  data-testid="annotation-target-problem"
                  role="status"
                  style={{ fontSize: '0.8125rem', color: 'var(--status-warning)', marginBottom: '0.75rem' }}
                >
                  {targetProblem ??
                    `No ${form.annotationTargetType} records exist in this case, so no target can be offered.`}
                </p>
              ) : (
                <select
                  value={form.annotationTargetId}
                  aria-label="Annotation target"
                  onChange={(e) => updateForm({ annotationTargetId: e.target.value })}
                  style={{ marginBottom: '0.75rem', width: '100%' }}
                >
                  <option value="">Select a {form.annotationTargetType} recorded in this case…</option>
                  {currentTargetOptions.map((option) => (
                    <option key={option.id} value={option.id} disabled={option.readOnly}>
                      {option.readOnly
                        ? `${option.label} (${option.readOnlyReason ?? 'read-only'} — no annotation target)`
                        : option.label}
                    </option>
                  ))}
                </select>
              )}
              {form.annotationTargetType !== 'case' &&
                currentTargetOptions.length > 0 &&
                targetProblem && (
                  <p
                    data-testid="annotation-target-problem"
                    role="status"
                    style={{ fontSize: '0.8125rem', color: 'var(--status-warning)', marginBottom: '0.75rem' }}
                  >
                    {targetProblem}
                  </p>
                )}
              <textarea
                value={form.annotationContent}
                onChange={(event) => updateForm({ annotationContent: event.target.value })}
                placeholder="Add comment, flag rationale, or injected context"
                aria-label="Annotation content"
                style={{
                  width: '100%',
                  minHeight: '90px',
                  borderRadius: '12px',
                  background: 'rgba(10, 19, 31, 0.68)',
                  color: 'inherit',
                  border: '1px solid rgba(133, 157, 186, 0.24)',
                  padding: '0.85rem',
                  marginBottom: '0.85rem',
                }}
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={submitAnnotation}
                disabled={
                  annotationLocked || !form.annotationContent.trim() || Boolean(targetProblem)
                }
              >
                Save Annotation
              </Button>
              <WriteStateBanner state={form.annotation.state}>
                {form.annotation.recoveryPending && (
                  <p role="status">Read-only recovery request in progress…</p>
                )}
                {form.annotation.state.kind === 'refresh-failed' && (
                  <div>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => void retryAnnotationRefresh()}
                      disabled={form.annotation.recoveryPending}
                    >
                      {form.annotation.recoveryPending ? 'Retrying refresh…' : 'Retry refresh (GET)'}
                    </Button>
                  </div>
                )}
                {form.annotation.state.kind === 'uncertain' && (
                  <div>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => void reconcileAnnotation()}
                      disabled={form.annotation.recoveryPending}
                    >
                      {form.annotation.recoveryPending ? 'Reconciling…' : 'Reconcile with read (GET)'}
                    </Button>
                  </div>
                )}
                {form.annotation.state.kind === 'reconciled' && (
                  <div>
                    <p style={{ marginBottom: '0.375rem' }}>
                      Retrying an annotation may append a duplicate note; it does not edit the earlier one.
                    </p>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={confirmAnnotationRetry}
                      disabled={form.annotation.recoveryPending}
                    >
                      Confirm retry
                    </Button>
                  </div>
                )}
              </WriteStateBanner>
            </div>
          </CardBody>
        </Card>

        <Card className="overview-card">
          <CardHeader>
            <CardTitle>Review Activity</CardTitle>
          </CardHeader>
          <CardBody>
            {activityLoading ? (
              <ReaderState
                state="loading"
                description="Fetching human notes and technical audit entries for this case."
              />
            ) : activityError ? (
              <ReaderState
                state="network-error"
                title="Review activity unavailable"
                description="Review activity could not be read. This is not the same as no recorded activity."
                detail={activityError instanceof Error ? activityError.message : null}
                onRetry={() => void refetchActivity()}
              />
            ) : humanNotes.length === 0 && technicalAudit.length === 0 ? (
              <ReaderState
                state="empty"
                title="No review activity"
                description="No human annotations or technical audit entries have been recorded for this case."
              />
            ) : (
              <div className="recent-list" data-testid="review-activity">
                <section aria-labelledby="human-notes-heading" data-testid="human-notes">
                  <h4 id="human-notes-heading" className="review-label" style={{ marginBottom: '0.5rem' }}>
                    <MessageSquare size={14} /> Human notes
                  </h4>
                  {humanNotes.length === 0 ? (
                    <div className="empty-state">No human annotations recorded.</div>
                  ) : (
                    humanNotes.map((item) => (
                      <div
                        key={`annotation-${item.id}`}
                        className="recent-item"
                        data-annotation-id={item.id}
                      >
                        <div className="recent-content">
                          <div className="recent-query" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                            {item.annotationType === 'flag' ? <Flag size={14} /> : <MessageSquare size={14} />}
                            <span>{item.annotationType} on {item.targetType}</span>
                            <Badge variant="info" size="sm">Human note</Badge>
                          </div>
                          <div className="recent-domain">{item.content}</div>
                        </div>
                        <div className="recent-status">
                          <Badge variant="neutral" size="sm">{formatActivityTimestamp(item.createdAt)}</Badge>
                        </div>
                      </div>
                    ))
                  )}
                </section>
                <section
                  aria-labelledby="technical-audit-heading"
                  data-testid="technical-audit"
                  style={{ marginTop: '1rem' }}
                >
                  <h4 id="technical-audit-heading" className="review-label" style={{ marginBottom: '0.5rem' }}>
                    <CheckCheck size={14} /> Technical audit
                  </h4>
                  {technicalAudit.length === 0 ? (
                    <div className="empty-state">No technical audit entries recorded.</div>
                  ) : (
                    technicalAudit.map((item) => (
                      <div
                        key={`audit-${item.id}`}
                        className="recent-item"
                        data-audit-entry={item.id}
                      >
                        <div className="recent-content">
                          <div className="recent-query" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                            <CheckCheck size={14} />
                            <code>{item.actionType}</code>
                            <Badge variant="neutral" size="sm">Technical audit</Badge>
                          </div>
                          <div className="recent-domain">
                            {item.rationale || `${item.actor} updated ${item.targetType}`}
                          </div>
                        </div>
                        <div className="recent-status">
                          <Badge variant="neutral" size="sm">{formatActivityTimestamp(item.createdAt)}</Badge>
                        </div>
                      </div>
                    ))
                  )}
                </section>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
};

function buildOperatorCommands(activeCase: TopicCase): Array<{ label: string; command: string }> {
  const commands = [
    {
      label: 'Inspect Case State',
      command: `uv run triangulate case show ${activeCase.id}`,
    },
  ];

  if (activeCase.status === 'review ready') {
    commands.push({
      label: 'Approve Case',
      command: `uv run triangulate case review ${activeCase.id} --decision approve`,
    });
    commands.push({
      label: 'Mark Action Required',
      command: `uv run triangulate case review ${activeCase.id} --decision action_required`,
    });
  }

  if (activeCase.status !== 'approved') {
    commands.push({
      label: 'Rerun From Retrieve',
      command: `uv run triangulate case rerun ${activeCase.id} --from retrieve`,
    });
  }

  return commands;
}

export default CaseIntelligenceCenter;
