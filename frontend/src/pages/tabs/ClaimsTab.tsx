import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { Claim, NarrativeCluster, SourceStanceBreakdown as SourceStanceBreakdownType } from '../../types/backend-models';
import { getClaimsOverviewForCase } from '../../services/api';
import { isNotFound } from '../../services/api-error';
import {
    CLAIMS_BROWSE_PARAMS,
    buildClaimEvidenceUrl,
    buildCitationUrl,
    sanitizeViewUrl,
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
import ReaderState from '../../components/design-system/ReaderState';
import { alignmentLabel, relationLabel } from '../../components/inspector/inspector-utils';
import { ShieldAlert, ThumbsUp, ThumbsDown, GitCommit, ChevronDown, ChevronRight, ChevronUp, Layers, Minus } from 'lucide-react';
import { ClaimDetailPanel } from '../../components/claims/ClaimDetailPanel';
import './ClaimsTab.css';

/** Loaded rows rendered per page; paging never changes the fetched array. */
const CLAIM_PAGE_SIZE = 50;

type ClaimSortKey = '' | 'text' | 'status';

const CLAIM_SORT_LABELS: Record<Exclude<ClaimSortKey, ''>, string> = {
    text: 'Claim text (A–Z)',
    status: 'Verification status (A–Z)',
};

/**
 * Claim provenance that can be *proven* from recorded fields.
 *
 * `claims` has no provenance column, so the claim reader returns
 * `verificationProvenance` (`unknown` / `legacy_unknown`) derived from the
 * recorded shape of its evidence links. On top of that we read the recorded
 * `assessmentOrigin` the writer stored on those links: a collector/pipeline
 * origin means a machine-recorded assessment, any other origin is reported
 * verbatim, and an absent origin stays unknown. Nothing here is inferred from
 * status, confidence or counts.
 */
type ProvenanceKind = 'model' | 'recorded' | 'legacy' | 'unknown';

const MODEL_ASSESSMENT_ORIGINS = new Set(['collector', 'pipeline', 'model']);

interface ProvenanceReading {
    kind: ProvenanceKind;
    label: string;
    detail: string;
    badgeClass: string;
}

function readClaimProvenance(claim: Claim): ProvenanceReading {
    if (claim.verificationProvenance === 'legacy_unknown') {
        return {
            kind: 'legacy',
            label: 'Legacy · provenance unknown',
            detail:
                'Verification status was recorded before provenance tracking; treat it as unverified, not as a reviewer confirmation.',
            badgeClass: 'badge-warning',
        };
    }

    const origins = Array.from(
        new Set(
            (claim.evidence ?? [])
                .map((link) => (link.assessmentOrigin ?? '').trim())
                .filter((origin) => origin !== '')
        )
    );
    const modelOrigin = origins.find((origin) => MODEL_ASSESSMENT_ORIGINS.has(origin.toLowerCase()));

    if (modelOrigin) {
        return {
            kind: 'model',
            label: `Model-recorded assessment (${modelOrigin})`,
            detail: `The recorded assessment origin is "${modelOrigin}". This is not a reviewer confirmation.`,
            badgeClass: 'badge-info',
        };
    }
    if (origins.length > 0) {
        return {
            kind: 'recorded',
            label: `Assessment recorded (${origins.join(', ')})`,
            detail: `Recorded assessment origin(s): ${origins.join(', ')}. No model or reviewer role is claimed here.`,
            badgeClass: 'badge-neutral',
        };
    }
    return {
        kind: 'unknown',
        label: 'Provenance unknown',
        detail:
            'No assessment origin is recorded for this claim, so its verification status cannot be attributed to a model or a reviewer.',
        badgeClass: 'badge-neutral',
    };
}

interface ClaimsTabProps {
  caseId: string;
  refreshToken?: number;
}

/**
 * Claims tab.
 *
 * Data is fetched through React Query keyed by case, so a slow response for a
 * previous case can never overwrite the current case's claims. Browse state
 * (filter/sort/page) and selection live in a component keyed by case, so they
 * reset with the case and never leak across cases.
 */
const ClaimsTab: React.FC<ClaimsTabProps> = ({ caseId, refreshToken = 0 }) => {
    const { data, isLoading, error, refetch, dataUpdatedAt } = useQuery({
        queryKey: ['claims-overview', caseId, refreshToken],
        queryFn: () => getClaimsOverviewForCase(caseId),
        enabled: !!caseId,
    });

    const lastFetched = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;
    const claims = data?.claims ?? [];
    const narratives = data?.narratives ?? [];

    let stateBody: React.ReactNode;
    if (!caseId) {
        stateBody = (
            <ReaderState
                state="not-found"
                title="No case selected"
                description="No case selected for claims."
            />
        );
    } else if (isLoading) {
        stateBody = <ReaderState state="loading" description="Loading claims for this case." />;
    } else if (error) {
        stateBody = isNotFound(error) ? (
            <ReaderState
                state="not-found"
                description="No claims overview is recorded for this case."
            />
        ) : (
            <ReaderState
                state="network-error"
                description="Failed to load claims."
                detail={error instanceof Error && error.message ? error.message : null}
                onRetry={() => {
                    void refetch();
                }}
                lastFetched={lastFetched}
            />
        );
    } else if (claims.length === 0 && narratives.length === 0) {
        stateBody = (
            <ReaderState
                state="empty"
                description="No claims have been recorded for this case yet."
                lastFetched={lastFetched}
            />
        );
    } else {
        stateBody = (
            <ClaimsContent key={caseId} caseId={caseId} claims={claims} narratives={narratives} />
        );
    }

    return (
        <div className="claims-container p-base">
            <div className="claims-header">
                <h3>Primary Claims Mapping</h3>
                <p className="subtitle">Corroboration network for identified facts and allegations.</p>
            </div>
            {stateBody}
        </div>
    );
};

interface ClaimBrowseState {
    query: string;
    status: string;
    sort: ClaimSortKey;
    page: number;
    /** Explicit values the allowlist rejected; they stay applied and visible. */
    rejectedQuery: string | null;
    rejectedStatus: string | null;
    messages: Partial<Record<string, string>>;
}

const EMPTY_CLAIM_BROWSE: ClaimBrowseState = {
    query: '',
    status: '',
    sort: '',
    page: 1,
    rejectedQuery: null,
    rejectedStatus: null,
    messages: {},
};

/** Initialise browse state from the allowlisted claims URL params only. */
function readClaimBrowse(params: URLSearchParams): ClaimBrowseState {
    const sanitized = sanitizeViewUrl('claims', params);
    const rawQuery = params.get(CLAIMS_BROWSE_PARAMS.query);
    const rawStatus = params.get(CLAIMS_BROWSE_PARAMS.status);
    const messages: Partial<Record<string, string>> = {};
    for (const key of Object.values(CLAIMS_BROWSE_PARAMS)) {
        const message = sanitized.invalid[key];
        if (message) messages[key] = message;
    }
    const sortValue = sanitized.params.get(CLAIMS_BROWSE_PARAMS.sort);
    const pageValue = Number(sanitized.params.get(CLAIMS_BROWSE_PARAMS.page) ?? '1');

    return {
        query: sanitized.params.get(CLAIMS_BROWSE_PARAMS.query) ?? '',
        status: sanitized.params.get(CLAIMS_BROWSE_PARAMS.status) ?? '',
        sort: sortValue === 'text' || sortValue === 'status' ? sortValue : '',
        page: Number.isInteger(pageValue) && pageValue >= 1 ? pageValue : 1,
        rejectedQuery: sanitized.invalid[CLAIMS_BROWSE_PARAMS.query] ? rawQuery : null,
        rejectedStatus: sanitized.invalid[CLAIMS_BROWSE_PARAMS.status] ? rawStatus : null,
        messages,
    };
}

function compareText(a: string | null | undefined, b: string | null | undefined): number {
    return (a ?? '').localeCompare(b ?? '', 'en', { sensitivity: 'base' });
}

function compareId(a: string, b: string): number {
    return a.localeCompare(b);
}

interface ClaimsContentProps {
    caseId: string;
    claims: Claim[];
    narratives: NarrativeCluster[];
}

const ClaimsContent: React.FC<ClaimsContentProps> = ({ caseId, claims, narratives }) => {
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const [browse, setBrowse] = useState<ClaimBrowseState>(() => readClaimBrowse(searchParams));
    const [expandedNarratives, setExpandedNarratives] = useState<Set<string>>(new Set());
    const [expandedClaims, setExpandedClaims] = useState<Set<string>>(new Set());
    const [selectedClaimId, setSelectedClaimId] = useState<string | null>(null);
    const [savedSnapshot, setSavedSnapshot] = useState<SavedViewsSnapshot>(() => listSavedViews(caseId));
    const [savedName, setSavedName] = useState('');
    const [savedConsent, setSavedConsent] = useState(false);
    const [savedNotice, setSavedNotice] = useState<{ tone: 'status' | 'alert'; text: string } | null>(null);
    const [ephemeralViews, setEphemeralViews] = useState<SavedView[]>([]);

    useEffect(
        () => subscribeToSavedViews(() => setSavedSnapshot(listSavedViews(caseId))),
        [caseId]
    );

    /**
     * Single expansion-state helper for both narrative and claim rows, so the
     * tab never keeps two competing sources of "what is open".
     */
    const toggleSet = (set: Set<string>, setter: (s: Set<string>) => void, id: string) => {
        const next = new Set(set);
        if (next.has(id)) {
            next.delete(id);
        } else {
            next.add(id);
        }
        setter(next);
    };

    const toggleNarrative = (id: string) => toggleSet(expandedNarratives, setExpandedNarratives, id);
    const toggleClaim = (id: string) => toggleSet(expandedClaims, setExpandedClaims, id);

    /** Cluster lookup by the recorded `clusterId`; grouping never reorders rows. */
    const narrativeByClusterId = useMemo(
        () => new Map(narratives.map((narrative) => [narrative.clusterId, narrative])),
        [narratives]
    );

    const filteredClaims = useMemo(() => {
        // A rejected explicit value keeps the filter applied and matches nothing;
        // it must never broaden back to the unfiltered loaded array.
        if (browse.rejectedQuery !== null || browse.rejectedStatus !== null) {
            return [] as Claim[];
        }
        const needle = browse.query.trim().toLowerCase();
        let rows = claims;
        if (needle) {
            rows = rows.filter((claim) => claim.text.toLowerCase().includes(needle));
        }
        if (browse.status) {
            rows = rows.filter((claim) => claim.verificationStatus === browse.status);
        }
        if (browse.sort === 'text') {
            return [...rows].sort(
                (a, b) => compareText(a.text, b.text) || compareId(a.id, b.id)
            );
        }
        if (browse.sort === 'status') {
            return [...rows].sort(
                (a, b) =>
                    compareText(a.verificationStatus, b.verificationStatus) ||
                    compareText(a.text, b.text) ||
                    compareId(a.id, b.id)
            );
        }
        return rows;
    }, [claims, browse.query, browse.status, browse.sort, browse.rejectedQuery, browse.rejectedStatus]);

    const totalPages = Math.max(1, Math.ceil(filteredClaims.length / CLAIM_PAGE_SIZE));
    const currentPage = Math.min(Math.max(1, browse.page), totalPages);
    const pageStart = (currentPage - 1) * CLAIM_PAGE_SIZE;
    const pageClaims = filteredClaims.slice(pageStart, pageStart + CLAIM_PAGE_SIZE);

    /** Grouped rows preserve the sorted page order; clusters never reorder rows. */
    const pageGroups = useMemo(() => {
        const groups: Array<{ key: string; narrative: NarrativeCluster | null; rows: Claim[] }> = [];
        for (const claim of pageClaims) {
            const narrative = claim.narrativeClusterId
                ? narrativeByClusterId.get(claim.narrativeClusterId) ?? null
                : null;
            const key = narrative ? `narrative:${narrative.id}` : 'unclustered';
            const last = groups[groups.length - 1];
            if (last && last.key === key) {
                last.rows.push(claim);
            } else {
                groups.push({ key, narrative, rows: [claim] });
            }
        }
        return groups;
    }, [pageClaims, narrativeByClusterId]);

    const hasBrowseFilters =
        browse.query !== '' ||
        browse.status !== '' ||
        browse.sort !== '' ||
        browse.rejectedQuery !== null ||
        browse.rejectedStatus !== null ||
        browse.page > 1;

    const selectedClaim = selectedClaimId
        ? claims.find((claim) => claim.id === selectedClaimId) ?? null
        : null;
    const selectedVisible = selectedClaimId !== null && pageClaims.some((claim) => claim.id === selectedClaimId);

    /** Mirror the allowlisted browse keys into the committed view URL. */
    const applyBrowse = (next: ClaimBrowseState) => {
        setBrowse(next);
        const params = new URLSearchParams(searchParams);
        for (const key of Object.values(CLAIMS_BROWSE_PARAMS)) {
            params.delete(key);
        }
        if (next.query) params.set(CLAIMS_BROWSE_PARAMS.query, next.query);
        if (next.status) params.set(CLAIMS_BROWSE_PARAMS.status, next.status);
        if (next.sort) params.set(CLAIMS_BROWSE_PARAMS.sort, next.sort);
        if (next.page > 1) params.set(CLAIMS_BROWSE_PARAMS.page, String(next.page));
        const canonical = sanitizeViewUrl('claims', params).params;
        // Rejected explicit values stay in the URL so a reload reproduces the same
        // field message instead of silently dropping back to the full list.
        if (next.rejectedQuery !== null) {
            canonical.set(CLAIMS_BROWSE_PARAMS.query, next.rejectedQuery);
        }
        if (next.rejectedStatus !== null) {
            canonical.set(CLAIMS_BROWSE_PARAMS.status, next.rejectedStatus);
        }
        setSearchParams(canonical, { replace: true });
    };

    const clearFilters = () => applyBrowse({ ...EMPTY_CLAIM_BROWSE });
    const clearField = (key: string) => {
        if (key === CLAIMS_BROWSE_PARAMS.query) {
            applyBrowse({ ...browse, query: '', rejectedQuery: null, page: 1, messages: { ...browse.messages, [key]: undefined } });
        } else if (key === CLAIMS_BROWSE_PARAMS.status) {
            applyBrowse({ ...browse, status: '', rejectedStatus: null, page: 1, messages: { ...browse.messages, [key]: undefined } });
        } else if (key === CLAIMS_BROWSE_PARAMS.sort) {
            applyBrowse({ ...browse, sort: '', page: 1, messages: { ...browse.messages, [key]: undefined } });
        } else {
            applyBrowse({ ...browse, page: 1, messages: { ...browse.messages, [key]: undefined } });
        }
    };

    const caseSavedViews = savedSnapshot.views;
    const mergedSavedViews = [...ephemeralViews, ...caseSavedViews];
    const canConsentToQuery = browse.query.trim() !== '' && browse.rejectedQuery === null;

    const handleSaveView = () => {
        const includeQuery = savedConsent && canConsentToQuery;
        const result = saveSavedView({
            caseId,
            view: 'claims',
            name: savedName,
            filters: { [CLAIMS_BROWSE_PARAMS.status]: browse.status },
            sort: browse.sort || null,
            includeQuery,
            query: includeQuery ? browse.query : null,
        });
        if (result.ok) {
            setSavedSnapshot(result.snapshot);
            setSavedName('');
            setSavedConsent(false);
            setSavedNotice({ tone: 'status', text: `Saved “${result.view.name}” on this device.` });
            return;
        }
        const ephemeral = result.ephemeral;
        if (ephemeral) {
            setEphemeralViews((views) => [...views, ephemeral]);
            setSavedName('');
            setSavedConsent(false);
        }
        setSavedNotice({ tone: 'alert', text: result.message });
    };

    /** Apply only allowlisted metadata; selection and paging are never restored. */
    const applySavedView = (view: SavedView) => {
        const sort = view.sort === 'text' || view.sort === 'status' ? view.sort : '';
        applyBrowse({
            ...EMPTY_CLAIM_BROWSE,
            query: view.filters[CLAIMS_BROWSE_PARAMS.query] ?? '',
            status: view.filters[CLAIMS_BROWSE_PARAMS.status] ?? '',
            sort,
            page: 1,
        });
        setSavedNotice({ tone: 'status', text: `Applied “${view.name}” to the loaded claims.` });
    };

    const handleDeleteSavedView = (id: string) => {
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

    return (
        <>
            <div className="claims-browse-bar" role="group" aria-label="Claim filters">
                <div className="claims-field">
                    <label htmlFor="claims-query">Filter loaded claims</label>
                    <input
                        id="claims-query"
                        type="search"
                        className="claims-input"
                        value={browse.query}
                        placeholder="Text contains…"
                        onChange={(event) => {
                            const value = event.target.value;
                            const messages = { ...browse.messages };
                            delete messages[CLAIMS_BROWSE_PARAMS.query];
                            applyBrowse({
                                ...browse,
                                query: value,
                                rejectedQuery: null,
                                page: 1,
                                messages,
                            });
                        }}
                    />
                </div>
                <div className="claims-field">
                    <label htmlFor="claims-status">Verification status</label>
                    <select
                        id="claims-status"
                        className="claims-input"
                        value={browse.status}
                        onChange={(event) => {
                            const messages = { ...browse.messages };
                            delete messages[CLAIMS_BROWSE_PARAMS.status];
                            applyBrowse({
                                ...browse,
                                status: event.target.value,
                                rejectedStatus: null,
                                page: 1,
                                messages,
                            });
                        }}
                    >
                        <option value="">All statuses</option>
                        {(['confirmed', 'probable', 'alleged', 'contested', 'debunked', 'unknown'] as const).map(
                            (status) => (
                                <option key={status} value={status}>
                                    {status}
                                </option>
                            )
                        )}
                    </select>
                </div>
                <div className="claims-field">
                    <label htmlFor="claims-sort">Sort</label>
                    <select
                        id="claims-sort"
                        className="claims-input"
                        value={browse.sort}
                        onChange={(event) => {
                            const messages = { ...browse.messages };
                            delete messages[CLAIMS_BROWSE_PARAMS.sort];
                            applyBrowse({
                                ...browse,
                                sort: event.target.value as ClaimSortKey,
                                page: 1,
                                messages,
                            });
                        }}
                    >
                        <option value="">Recorded order</option>
                        <option value="text">{CLAIM_SORT_LABELS.text}</option>
                        <option value="status">{CLAIM_SORT_LABELS.status}</option>
                    </select>
                </div>
            </div>

            {Object.entries(browse.messages).map(([key, message]) => (
                <div className="claims-field-error" key={key} role="alert">
                    <span>{message}</span>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => clearField(key)}>
                        Clear filter
                    </button>
                </div>
            ))}

            <div className="claims-saved-views" role="group" aria-label="Saved claim views">
                <h4>Saved claim views</h4>
                <p className="claims-saved-views-note">
                    Saved views stay in this browser. They are local, not private: anyone using this browser profile can read them.
                </p>
                <div className="claims-saved-views-save">
                    <div className="claims-field">
                        <label htmlFor="claims-saved-view-name">Saved view name</label>
                        <input
                            id="claims-saved-view-name"
                            className="claims-input"
                            value={savedName}
                            placeholder="e.g. Confirmed claims, text sorted"
                            onChange={(event) => setSavedName(event.target.value)}
                        />
                    </div>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={handleSaveView}>
                        Save current filters
                    </button>
                </div>
                {canConsentToQuery && (
                    <div className="claims-saved-consent">
                        <label htmlFor="claims-saved-consent">
                            <input
                                id="claims-saved-consent"
                                type="checkbox"
                                checked={savedConsent}
                                onChange={(event) => setSavedConsent(event.target.checked)}
                            />{' '}
                            Store the claim filter text in this saved view
                        </label>
                        <p className="claims-saved-views-note">
                            Claim filter text can be sensitive. It is excluded unless you tick this box; with consent it is stored on this browser.
                        </p>
                    </div>
                )}
                {savedNotice && (
                    <p role={savedNotice.tone === 'alert' ? 'alert' : 'status'}>{savedNotice.text}</p>
                )}
                {mergedSavedViews.length > 0 && (
                    <ul className="claims-saved-views-list" aria-label="Saved claim views list">
                        {mergedSavedViews.map((view) => (
                            <li key={view.id}>
                                <span>{view.name}</span>
                                <span className="claims-saved-views-summary">{describeSavedView(view)}</span>
                                <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    onClick={() => applySavedView(view)}
                                    aria-label={`Apply saved view ${view.name}`}
                                >
                                    Apply
                                </button>
                                <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    onClick={() => handleDeleteSavedView(view.id)}
                                    aria-label={`Delete saved view ${view.name}`}
                                >
                                    Delete
                                </button>
                            </li>
                        ))}
                    </ul>
                )}
                <div className="claims-saved-views-actions">
                    {(caseSavedViews.length > 0 || savedSnapshot.totalCount > 0) && (
                        <button type="button" className="btn btn-secondary btn-sm" onClick={handleDeleteCaseViews}>
                            Delete saved views for this case
                        </button>
                    )}
                    {(caseSavedViews.length > 0 || savedSnapshot.totalCount > 0 || savedSnapshot.status !== 'ok') && (
                        <button type="button" className="btn btn-secondary btn-sm" onClick={handleDeleteAllViews}>
                            {savedSnapshot.status === 'ok' ? 'Delete all saved views' : 'Discard stored saved views'}
                        </button>
                    )}
                </div>
            </div>

            <p className="claims-paging-note">
                Showing rows{' '}
                {filteredClaims.length === 0 ? 0 : pageStart + 1}–
                {pageStart + pageClaims.length} of {filteredClaims.length} loaded results · page {currentPage} of{' '}
                {totalPages}. Paging is client-side over the rows already loaded for this case.
            </p>

            {hasBrowseFilters && (
                <div className="claims-filter-summary">
                    <span>Filtered view applied to the loaded results.</span>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={clearFilters}>
                        Clear filters
                    </button>
                </div>
            )}

            {selectedClaimId !== null && (
                <div className="claims-selection" data-testid="claims-selection">
                    <p>
                        Selected claim <code>{selectedClaimId}</code>
                        {selectedVisible ? '' : ' — not in the current filter'}
                        {selectedClaim ? `: ${selectedClaim.text}` : ''}
                    </p>
                    <div className="claims-selection-actions">
                        <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            onClick={() => navigate(buildClaimEvidenceUrl(caseId, selectedClaimId))}
                        >
                            Inspect selected claim
                        </button>
                        <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => setSelectedClaimId(null)}
                        >
                            Clear selection
                        </button>
                    </div>
                </div>
            )}

            {filteredClaims.length === 0 ? (
                <div className="claims-filter-empty" data-state="claims-filter-empty">
                    <ReaderState
                        state="empty"
                        title="No loaded claims match these filters"
                        description={
                            hasBrowseFilters
                                ? 'The loaded claim list is unchanged; only the client-side filter hides every row. Adjust or clear the filters to see claims again.'
                                : 'This case has no claims to browse.'
                        }
                    />
                </div>
            ) : (
                <div className="claims-page">
                    {pageGroups.map((group) => {
                        if (!group.narrative) {
                            return group.rows.map((claim) => (
                                <ClaimRow
                                    key={claim.id}
                                    claim={claim}
                                    caseId={caseId}
                                    navigate={navigate}
                                    isExpanded={expandedClaims.has(claim.id)}
                                    isSelected={selectedClaimId === claim.id}
                                    onToggle={() => toggleClaim(claim.id)}
                                    onSelect={() =>
                                        setSelectedClaimId(selectedClaimId === claim.id ? null : claim.id)
                                    }
                                />
                            ));
                        }

                        const narrative = group.narrative;
                        const isExpanded = expandedNarratives.has(narrative.id);
                        return (
                            <div key={group.key} className="narrative-cluster glass-panel">
                                <button
                                    type="button"
                                    className="narrative-header"
                                    aria-expanded={isExpanded}
                                    aria-controls={`narrative-claims-${narrative.id}`}
                                    onClick={() => toggleNarrative(narrative.id)}
                                >
                                    <div className="narrative-title-row">
                                        {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                                        <Layers size={16} className="narrative-icon" />
                                        <span className="narrative-summary">{narrative.stanceSummary}</span>
                                    </div>
                                    <div className="narrative-meta">
                                        <span className="narrative-count">{narrative.claimCount} claims</span>
                                        <span className="narrative-sources">{narrative.sourceCount} sources</span>
                                    </div>
                                </button>

                                {isExpanded && (
                                    <div className="narrative-claims" id={`narrative-claims-${narrative.id}`}>
                                        {group.rows.map((claim) => (
                                            <ClaimRow
                                                key={claim.id}
                                                claim={claim}
                                                caseId={caseId}
                                                navigate={navigate}
                                                isExpanded={expandedClaims.has(claim.id)}
                                                isSelected={selectedClaimId === claim.id}
                                                onToggle={() => toggleClaim(claim.id)}
                                                onSelect={() =>
                                                    setSelectedClaimId(selectedClaimId === claim.id ? null : claim.id)
                                                }
                                            />
                                        ))}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}

            <div className="claims-pager">
                <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={currentPage <= 1}
                    onClick={() => applyBrowse({ ...browse, page: Math.max(1, currentPage - 1) })}
                >
                    Previous page
                </button>
                <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={currentPage >= totalPages}
                    onClick={() => applyBrowse({ ...browse, page: Math.min(totalPages, currentPage + 1) })}
                >
                    Next page
                </button>
            </div>
        </>
    );
};

interface ClaimRowProps {
    claim: Claim;
    caseId: string;
    navigate: ReturnType<typeof useNavigate>;
    isExpanded: boolean;
    isSelected: boolean;
    onToggle: () => void;
    onSelect: () => void;
}

const SourceStanceBreakdown: React.FC<{ breakdown: SourceStanceBreakdownType }> = ({ breakdown }) => {
    const hasSources = breakdown.agreedSources.length > 0 || breakdown.disagreedSources.length > 0 || breakdown.didntReportSources.length > 0;

    if (!hasSources) {
        return null;
    }

    return (
        <div className="source-stance-breakdown">
            {breakdown.agreedSources.length > 0 && (
                <div className="stance-group">
                    <span className="stance-label">Agreed</span>
                    <div className="stance-sources">
                        {breakdown.agreedSources.map((source) => (
                            <span key={source} className="stance-source agreed" title="Reported supporting this claim">
                                <ThumbsUp size={10} /> {source}
                            </span>
                        ))}
                    </div>
                </div>
            )}
            {breakdown.disagreedSources.length > 0 && (
                <div className="stance-group">
                    <span className="stance-label">Disagreed</span>
                    <div className="stance-sources">
                        {breakdown.disagreedSources.map((source) => (
                            <span key={source} className="stance-source disagreed" title="Reported contradicting this claim">
                                <ThumbsDown size={10} /> {source}
                            </span>
                        ))}
                    </div>
                </div>
            )}
            {breakdown.didntReportSources.length > 0 && (
                <div className="stance-group">
                    <span className="stance-label">Didn&apos;t Report</span>
                    <div className="stance-sources">
                        {breakdown.didntReportSources.map((source) => (
                            <span key={source} className="stance-source didnt-report" title="Did not report on this claim">
                                <Minus size={10} /> {source}
                            </span>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

const ClaimRow: React.FC<ClaimRowProps> = ({ claim, caseId, navigate, isExpanded, isSelected, onToggle, onSelect }) => {
    const detailId = `claim-detail-${claim.id}`;
    const provenance = readClaimProvenance(claim);

    return (
        <div
            className={`claim-row glass-panel ${isExpanded ? 'expanded' : ''} ${isSelected ? 'selected' : ''}`}
            data-provenance={provenance.kind}
            data-claim-id={claim.id}
        >
            <div className="claim-main">
                <div className="claim-header-row">
                    <button
                        type="button"
                        className="expand-btn"
                        aria-expanded={isExpanded}
                        aria-controls={detailId}
                        aria-label={isExpanded ? 'Collapse claim details' : 'Expand claim details'}
                        onClick={onToggle}
                    >
                        {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </button>
                    <div className="claim-tags">
                        <span className={`badge ${claim.type === 'fact' ? 'badge-info' : 'badge-warning'}`}>
                            {claim.type}
                        </span>
                        <span className={`badge ${claim.verificationStatus === 'confirmed' ? 'badge-success' : 'badge-danger'}`}>
                            {claim.verificationStatus}
                        </span>
                        <span
                            className={`badge claim-provenance ${provenance.badgeClass}`}
                            data-provenance={provenance.kind}
                            title={provenance.detail}
                        >
                            {provenance.label}
                        </span>
                    </div>
                    <span className="claim-id">{claim.id}</span>
                </div>
                <p className="claim-text">{claim.text}</p>
                <div className="claim-signature"><GitCommit size={14} /> {claim.claimSignature}</div>
                {claim.sourceStanceBreakdown && (
                    <SourceStanceBreakdown breakdown={claim.sourceStanceBreakdown} />
                )}
            </div>

            <div className="claim-metrics">
                <div className="corroboration-bar">
                    <div className="corroboration-stat support">
                        <ThumbsUp size={16} /> {claim.supportCount}
                    </div>
                    <div className="corroboration-stat oppose">
                        <ThumbsDown size={16} /> {claim.opposeCount}
                    </div>
                </div>
                <div className="diversity-badge">
                    {claim.sourceDiversityCount} distinct source{claim.sourceDiversityCount !== 1 && 's'}
                </div>
                {(claim.controversyScore ?? 0) > 0.5 && (
                    <div className="controversy-warning">
                        <ShieldAlert size={14} /> Highly Contested ({((claim.controversyScore ?? 0) * 100).toFixed(0)}%)
                    </div>
                )}
            </div>

            <div className="claim-actions">
                <button
                    type="button"
                    className={`btn btn-sm claim-select-btn ${isSelected ? 'btn-primary' : 'btn-secondary'}`}
                    aria-pressed={isSelected}
                    aria-label={isSelected ? `Deselect claim ${claim.id}` : `Select claim ${claim.id}`}
                    onClick={onSelect}
                >
                    {isSelected ? 'Selected' : 'Select'}
                </button>
                <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => navigate(buildClaimEvidenceUrl(caseId, claim.id))}
                >
                    Inspect Evidence
                </button>
            </div>

            {isExpanded && (
                <div id={detailId} className="claim-detail">
                    <ClaimPassageLinks claim={claim} caseId={caseId} navigate={navigate} />
                    <ClaimDetailPanel claim={claim} />
                </div>
            )}
        </div>
    );
};

interface ClaimPassageLinksProps {
    claim: Claim;
    caseId: string;
    navigate: ReturnType<typeof useNavigate>;
}

/**
 * Per-link passage entry points, rendered only in the expanded claim row.
 * Citations get a frozen deep link; unvalidated links fall back to the
 * claim-filtered evidence list instead of pretending a passage exists.
 */
const ClaimPassageLinks: React.FC<ClaimPassageLinksProps> = ({ claim, caseId, navigate }) => {
    const links = claim.evidence ?? [];
    if (links.length === 0) {
        return null;
    }

    return (
        <div className="claim-passages" aria-label="Linked evidence passages">
            <h4>Linked sources</h4>
            <ul className="claim-passage-list">
                {links.map((link, index) => {
                    const citationId = link.citationId;
                    return (
                        <li key={link.id || `${citationId ?? 'link'}-${index}`} className="claim-passage-item">
                            <div className="claim-passage-meta">
                                <strong>{relationLabel(link.effectiveRelation ?? 'uncertain')}</strong>
                                <span>{alignmentLabel(link.alignmentStatus ?? 'not_provided')}</span>
                            </div>
                            {link.quote ? (
                                <blockquote className="claim-passage-quote">{link.quote}</blockquote>
                            ) : (
                                <p className="claim-passage-missing">
                                    No validated quotation is stored for this source link.
                                </p>
                            )}
                            <div className="claim-passage-actions">
                                <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    onClick={() => navigate(buildClaimEvidenceUrl(caseId, claim.id))}
                                >
                                    Inspect sources
                                </button>
                                {citationId && (
                                    <button
                                        type="button"
                                        className="btn btn-ghost btn-sm"
                                        onClick={() => navigate(buildCitationUrl(caseId, citationId))}
                                    >
                                        Open frozen citation
                                    </button>
                                )}
                            </div>
                        </li>
                    );
                })}
            </ul>
        </div>
    );
};

export default ClaimsTab;
