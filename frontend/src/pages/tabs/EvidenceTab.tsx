import React, { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { Evidence } from '../../types/backend-models';
import { getEvidenceForCase } from '../../services/api';
import { isNotFound } from '../../services/api-error';
import {
    EVIDENCE_BROWSE_PARAMS,
    INSPECTOR_PARAMS,
    buildInspectorUrl,
    buildViewHref,
    parseInspectorSelection,
    readSnapshotSelector,
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
import {
    addToComparisonTray,
    comparisonContextFromSearchParams,
    getComparisonTray,
    reconcileComparisonTrayContext,
    subscribeComparisonTray,
} from '../../services/comparison-tray';
import { EvidenceInspector } from '../../components/inspector/EvidenceInspector';
import ReaderState from '../../components/design-system/ReaderState';
import { safeExternalUrl } from '../../components/inspector/inspector-utils';
import { ShieldCheck, ShieldAlert, FileSearch, GitCompare, Link, ChevronDown, ChevronRight, ClipboardCheck } from 'lucide-react';
import './EvidenceTab.css';

/** Loaded rows rendered per page; paging never changes the fetched array. */
const EVIDENCE_PAGE_SIZE = 50;

/** Canonical credibility tiers the recorded DTO may carry. */
const CANONICAL_TIERS = ['high', 'medium', 'low', 'unknown', 'user_supplied'] as const;

type EvidenceSortKey = '' | 'title' | 'publishedAt';
type HasCaptureValue = '' | 'yes' | 'no';

const HIDDEN_FILTER = new Set(['all', '']);

const getCredibilityLabel = (tier: string | null) => {
    switch (tier) {
        case 'high': return 'High';
        case 'medium': return 'Medium';
        case 'low': return 'Low';
        case 'unknown': return 'Unknown';
        case 'user_supplied': return 'User Supplied';
        default: return tier || 'Unknown';
    }
};

/**
 * Evidence provenance that can be *proven* from recorded fields.
 *
 * The evidence list DTO has no provenance column, so the only recorded signals
 * are the assessment metadata the writer stored: a credibility tier other than
 * `unknown`, recorded verification checks, or tool artifacts. A tier of
 * `user_supplied` is an operator-recorded value, not a model one. Anything else
 * is reported as unknown — never promoted to a model claim.
 */
type ProvenanceKind = 'model' | 'recorded' | 'unknown';

interface ProvenanceReading {
    kind: ProvenanceKind;
    label: string;
    detail: string;
    badgeClass: string;
}

function readEvidenceProvenance(item: Evidence): ProvenanceReading {
    const tier = (item.credibilityTier ?? '').trim().toLowerCase();
    const checks = item.verificationChecks ?? [];
    const tools = Array.from(
        new Set((item.artifacts ?? []).map((artifact) => artifact.tool).filter((tool) => tool !== ''))
    );

    if (tier === 'user_supplied') {
        return {
            kind: 'recorded',
            label: 'Operator-recorded assessment',
            detail: 'The recorded credibility tier is user supplied; no model or reviewer role is claimed here.',
            badgeClass: 'badge-neutral',
        };
    }

    const signals: string[] = [];
    if (tier !== '' && tier !== 'unknown') signals.push(`credibility tier "${tier}"`);
    if (checks.length > 0) signals.push(`${checks.length} verification check${checks.length === 1 ? '' : 's'}`);
    if (tools.length > 0) signals.push(`tool artifacts (${tools.join(', ')})`);

    if (signals.length > 0) {
        return {
            kind: 'model',
            label: 'Model-recorded assessment',
            detail: `Recorded by the pipeline: ${signals.join('; ')}. This is not a reviewer confirmation.`,
            badgeClass: 'badge-info',
        };
    }

    return {
        kind: 'unknown',
        label: 'Provenance unknown',
        detail:
            'No credibility tier, verification check or tool artifact is recorded for this evidence item, so its assessment provenance is unknown.',
        badgeClass: 'badge-neutral',
    };
}

/**
 * Publication date recorded for a loaded evidence row.
 *
 * The list DTO carries the stored publication timestamp (`publishedAt`), and a
 * row without one keeps an unknown date: it is never given a synthetic date and
 * sorts after every dated row.
 */
function recordedPublishedAt(item: Evidence): string | null {
    const candidate = item.publishedAt;
    return typeof candidate === 'string' && candidate.trim() !== '' ? candidate : null;
}

function compareText(a: string | null | undefined, b: string | null | undefined): number {
    return (a ?? '').localeCompare(b ?? '', 'en', { sensitivity: 'base' });
}

function compareId(a: string, b: string): number {
    return a.localeCompare(b);
}

interface EvidenceTabProps {
  caseId: string;
  refreshToken?: number;
}

/**
 * The pinned (`?snapshot=`) form of the evidence view.
 *
 * A frozen observation is a destination in its own right: only the
 * snapshot-aware claim/evidence detail readers and the ID-frozen citation and
 * capture readers may answer it. The current gallery, its filters and its
 * selection affordances belong to live rows, so they are not mounted here — a
 * missing pinned entity stays missing instead of being replaced by current data.
 */
const PinnedEvidenceView: React.FC<{ caseId: string; snapshotId: string }> = ({
    caseId,
    snapshotId,
}) => {
    const [searchParams] = useSearchParams();
    const selection = parseInspectorSelection(searchParams);
    const hasSelection = Boolean(selection.claimId || selection.evidenceId);
    const currentParams = new URLSearchParams(searchParams);
    currentParams.delete(INSPECTOR_PARAMS.snapshot);
    const openCurrentHref = buildViewHref(caseId, 'evidence', currentParams);

    return (
        <>
            <div className="evidence-history-context" role="status" data-snapshot-id={snapshotId}>
                <h3>Historical evidence view</h3>
                <p>
                    Observation <code title={snapshotId}>{snapshotId}</code> — read-only. Values
                    below are read from that recorded observation; the current evidence gallery is
                    neither loaded nor shown here.
                </p>
                <RouterLink className="case-history-link" to={openCurrentHref}>
                    Open current Evidence
                </RouterLink>
            </div>
            {hasSelection ? null : (
                <div className="evidence-history-context" role="status">
                    <p>
                        No claim or evidence item is selected in this observation. This link pins a
                        recorded observation only, so no live evidence is substituted. Open a claim
                        or evidence deep link for this observation, or use the link above to leave
                        the pinned view.
                    </p>
                </div>
            )}
            <EvidenceInspector caseId={caseId} />
        </>
    );
};

/**
 * Evidence tab.
 *
 * React Query keyed by case keeps a late response for a previous case from
 * replacing the current case's evidence, and the filter/expansion state lives in
 * a component keyed by case so it cannot leak across cases.
 */
const EvidenceTab: React.FC<EvidenceTabProps> = ({ caseId, refreshToken = 0 }) => {
    // A historical selector is resolved before anything is mounted, so a pinned
    // link can never fall through to the live list.
    const [searchParams] = useSearchParams();
    const snapshot = useMemo(() => readSnapshotSelector(searchParams), [searchParams]);

    if (!caseId) {
        return (
            <div className="evidence-tab-container p-base">
                <ReaderState
                    state="not-found"
                    title="No case selected"
                    description="No case selected for evidence."
                />
            </div>
        );
    }

    if (snapshot.snapshotId) {
        return (
            <div className="evidence-tab-container p-base">
                <PinnedEvidenceView caseId={caseId} snapshotId={snapshot.snapshotId} />
            </div>
        );
    }

    return (
        <div className="evidence-tab-container p-base">
            {/* The inspector is independent of the evidence list request, so a
                frozen citation deep link still resolves while the list loads. */}
            <EvidenceInspector caseId={caseId} />
            <EvidenceList caseId={caseId} refreshToken={refreshToken} />
        </div>
    );
};

const EvidenceList: React.FC<EvidenceTabProps> = ({ caseId, refreshToken = 0 }) => {
    const { data, isLoading, error, refetch, dataUpdatedAt } = useQuery({
        queryKey: ['evidence', caseId, refreshToken],
        queryFn: () => getEvidenceForCase(caseId),
        enabled: !!caseId,
    });

    const lastFetched = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

    if (isLoading) {
        return (
            <>
                <div className="evidence-toolbar">
                    <h3>Evidence Gallery</h3>
                </div>
                <ReaderState state="loading" description="Loading evidence for this case." />
            </>
        );
    }

    if (error) {
        return (
            <>
                <div className="evidence-toolbar">
                    <h3>Evidence Gallery</h3>
                </div>
                {isNotFound(error) ? (
                    <ReaderState state="not-found" description="This case has no evidence recorded." />
                ) : (
                    <ReaderState
                        state="network-error"
                        description="Failed to load evidence."
                        detail={error instanceof Error && error.message ? error.message : null}
                        onRetry={() => {
                            void refetch();
                        }}
                        lastFetched={lastFetched}
                    />
                )}
            </>
        );
    }

    return <EvidenceContent key={caseId} caseId={caseId} evidence={data ?? []} lastFetched={lastFetched} />;
};

interface EvidenceBrowseState {
    publisher: string;
    sourceType: string;
    credibilityTier: string;
    hasCapture: HasCaptureValue;
    sort: EvidenceSortKey;
    page: number;
    /** Explicit values the allowlist rejected; they stay applied and visible. */
    rejected: Partial<Record<string, string>>;
    messages: Partial<Record<string, string>>;
}

const EMPTY_EVIDENCE_BROWSE: EvidenceBrowseState = {
    publisher: '',
    sourceType: '',
    credibilityTier: '',
    hasCapture: '',
    sort: '',
    page: 1,
    rejected: {},
    messages: {},
};

/** Initialise browse state from the allowlisted evidence URL params only. */
function readEvidenceBrowse(params: URLSearchParams): EvidenceBrowseState {
    const sanitized = sanitizeViewUrl('evidence', params);
    const messages: Partial<Record<string, string>> = {};
    const rejected: Partial<Record<string, string>> = {};
    const browseKeys = [
        EVIDENCE_BROWSE_PARAMS.publisher,
        EVIDENCE_BROWSE_PARAMS.sourceType,
        EVIDENCE_BROWSE_PARAMS.credibilityTier,
        EVIDENCE_BROWSE_PARAMS.hasCapture,
        EVIDENCE_BROWSE_PARAMS.sort,
        EVIDENCE_BROWSE_PARAMS.page,
    ];
    for (const key of browseKeys) {
        const message = sanitized.invalid[key];
        const raw = params.get(key);
        if (message) {
            messages[key] = message;
            if (raw !== null) rejected[key] = raw;
        }
    }

    const hasCapture = sanitized.params.get(EVIDENCE_BROWSE_PARAMS.hasCapture);
    const sort = sanitized.params.get(EVIDENCE_BROWSE_PARAMS.sort);
    const page = Number(sanitized.params.get(EVIDENCE_BROWSE_PARAMS.page) ?? '1');

    return {
        publisher: sanitized.params.get(EVIDENCE_BROWSE_PARAMS.publisher) ?? '',
        sourceType: sanitized.params.get(EVIDENCE_BROWSE_PARAMS.sourceType) ?? '',
        credibilityTier: sanitized.params.get(EVIDENCE_BROWSE_PARAMS.credibilityTier) ?? '',
        hasCapture: hasCapture === 'yes' || hasCapture === 'no' ? hasCapture : '',
        sort: sort === 'title' || sort === 'publishedAt' ? sort : '',
        page: Number.isInteger(page) && page >= 1 ? page : 1,
        rejected,
        messages,
    };
}

interface EvidenceContentProps {
    caseId: string;
    evidence: Evidence[];
    lastFetched?: string | null;
}

const EvidenceContent: React.FC<EvidenceContentProps> = ({ caseId, evidence, lastFetched = null }) => {
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const [browse, setBrowse] = useState<EvidenceBrowseState>(() => readEvidenceBrowse(searchParams));
    const [expandedChecks, setExpandedChecks] = useState<Set<string>>(new Set());
    const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
    const [savedSnapshot, setSavedSnapshot] = useState<SavedViewsSnapshot>(() => listSavedViews(caseId));
    const [savedName, setSavedName] = useState('');
    const [savedNotice, setSavedNotice] = useState<{ tone: 'status' | 'alert'; text: string } | null>(null);
    const [ephemeralViews, setEphemeralViews] = useState<SavedView[]>([]);
    const claimFilter = searchParams.get('claim');

    useEffect(
        () => subscribeToSavedViews(() => setSavedSnapshot(listSavedViews(caseId))),
        [caseId]
    );

    // Comparison draft: session-only, this case and this context only. A draft
    // from another case/context is cleared here after an explicit notice.
    const comparisonContext = comparisonContextFromSearchParams(searchParams);
    const comparisonTray = useSyncExternalStore(subscribeComparisonTray, () =>
        getComparisonTray(caseId, comparisonContext)
    );
    useEffect(() => {
        reconcileComparisonTrayContext(caseId, comparisonContext);
    }, [caseId, comparisonContext]);

    const toggleSet = (set: Set<string>, setter: (s: Set<string>) => void, id: string) => {
        const next = new Set(set);
        if (next.has(id)) {
            next.delete(id);
        } else {
            next.add(id);
        }
        setter(next);
    };

    const toggleChecks = (id: string) => toggleSet(expandedChecks, setExpandedChecks, id);

    const renderVerificationBadge = (status: Evidence['verificationStatus']) => {
        switch (status) {
            case 'confirmed': return <span className="badge badge-success"><ShieldCheck size={12} /> Confirmed</span>;
            case 'contested': return <span className="badge badge-warning"><ShieldAlert size={12} /> Contested</span>;
            case 'debunked': return <span className="badge badge-danger">Debunked</span>;
            default: return <span className="badge badge-neutral">{status}</span>;
        }
    };

    /** Tier options: the canonical list plus any tier actually recorded here. */
    const tierOptions = useMemo(() => {
        const recorded = evidence
            .map((item) => (item.credibilityTier ?? '').trim())
            .filter((tier) => !HIDDEN_FILTER.has(tier));
        const extra = browse.credibilityTier ? [browse.credibilityTier] : [];
        return Array.from(new Set<string>([...CANONICAL_TIERS, ...recorded, ...extra]));
    }, [evidence, browse.credibilityTier]);

    const publisherOptions = useMemo(
        () =>
            Array.from(
                new Set(
                    evidence
                        .map((item) => (item.publisher ?? '').trim())
                        .filter((publisher) => publisher !== '')
                )
            ).sort((a, b) => compareText(a, b)),
        [evidence]
    );

    const sourceTypeOptions = useMemo(
        () =>
            Array.from(
                new Set(
                    evidence
                        .map((item) => (item.sourceType ?? '').trim())
                        .filter((sourceType) => sourceType !== '')
                )
            ).sort((a, b) => compareText(a, b)),
        [evidence]
    );

    const rejectedActive = Object.keys(browse.rejected).length > 0;

    const visibleEvidence = useMemo(() => {
        // A rejected explicit value keeps the filter applied and matches nothing;
        // it must never broaden back to the unfiltered loaded array.
        if (rejectedActive) return [] as Evidence[];

        let rows = evidence;
        if (claimFilter) {
            rows = rows.filter((item) => item.linkedClaims.includes(claimFilter));
        }
        const publisher = browse.publisher.trim().toLowerCase();
        if (publisher) {
            rows = rows.filter((item) => (item.publisher ?? '').toLowerCase().includes(publisher));
        }
        const sourceType = browse.sourceType.trim().toLowerCase();
        if (sourceType) {
            rows = rows.filter((item) => (item.sourceType ?? '').toLowerCase() === sourceType);
        }
        if (browse.credibilityTier) {
            rows = rows.filter((item) => (item.credibilityTier ?? '') === browse.credibilityTier);
        }
        if (browse.hasCapture === 'yes') {
            rows = rows.filter((item) => Boolean(item.currentCaptureId));
        } else if (browse.hasCapture === 'no') {
            rows = rows.filter((item) => !item.currentCaptureId);
        }

        if (browse.sort === 'title') {
            return [...rows].sort((a, b) => compareText(a.title, b.title) || compareId(a.id, b.id));
        }
        if (browse.sort === 'publishedAt') {
            return [...rows].sort((a, b) => {
                const left = recordedPublishedAt(a);
                const right = recordedPublishedAt(b);
                // Newest first; unknown dates sort last; ties fall back to the
                // stable entity ID so the order never depends on input order.
                if (left === null && right === null) return compareId(a.id, b.id);
                if (left === null) return 1;
                if (right === null) return -1;
                return compareText(right, left) || compareId(a.id, b.id);
            });
        }
        return rows;
    }, [
        evidence,
        claimFilter,
        browse.publisher,
        browse.sourceType,
        browse.credibilityTier,
        browse.hasCapture,
        browse.sort,
        rejectedActive,
    ]);

    const totalPages = Math.max(1, Math.ceil(visibleEvidence.length / EVIDENCE_PAGE_SIZE));
    const currentPage = Math.min(Math.max(1, browse.page), totalPages);
    const pageStart = (currentPage - 1) * EVIDENCE_PAGE_SIZE;
    const pageEvidence = visibleEvidence.slice(pageStart, pageStart + EVIDENCE_PAGE_SIZE);

    const hasBrowseFilters =
        browse.publisher !== '' ||
        browse.sourceType !== '' ||
        browse.credibilityTier !== '' ||
        browse.hasCapture !== '' ||
        browse.sort !== '' ||
        browse.page > 1 ||
        rejectedActive;

    const selectedEvidence = selectedEvidenceId
        ? evidence.find((item) => item.id === selectedEvidenceId) ?? null
        : null;
    const selectedVisible =
        selectedEvidenceId !== null && pageEvidence.some((item) => item.id === selectedEvidenceId);

    /** Mirror the allowlisted browse keys into the committed view URL. */
    const applyBrowse = (next: EvidenceBrowseState) => {
        setBrowse(next);
        const params = new URLSearchParams(searchParams);
        params.delete(EVIDENCE_BROWSE_PARAMS.publisher);
        params.delete(EVIDENCE_BROWSE_PARAMS.sourceType);
        params.delete(EVIDENCE_BROWSE_PARAMS.credibilityTier);
        params.delete(EVIDENCE_BROWSE_PARAMS.hasCapture);
        params.delete(EVIDENCE_BROWSE_PARAMS.sort);
        params.delete(EVIDENCE_BROWSE_PARAMS.page);

        if (next.publisher) params.set(EVIDENCE_BROWSE_PARAMS.publisher, next.publisher);
        if (next.sourceType) params.set(EVIDENCE_BROWSE_PARAMS.sourceType, next.sourceType);
        if (next.credibilityTier) params.set(EVIDENCE_BROWSE_PARAMS.credibilityTier, next.credibilityTier);
        if (next.hasCapture) params.set(EVIDENCE_BROWSE_PARAMS.hasCapture, next.hasCapture);
        if (next.sort) params.set(EVIDENCE_BROWSE_PARAMS.sort, next.sort);
        if (next.page > 1) params.set(EVIDENCE_BROWSE_PARAMS.page, String(next.page));

        const canonical = sanitizeViewUrl('evidence', params).params;
        // Rejected explicit values stay in the URL so a reload reproduces the same
        // field message instead of silently dropping back to the full list.
        for (const [key, raw] of Object.entries(next.rejected)) {
            if (typeof raw === 'string') canonical.set(key, raw);
        }
        setSearchParams(canonical, { replace: true });
    };

    const clearFilters = () => applyBrowse({ ...EMPTY_EVIDENCE_BROWSE });
    const clearField = (key: string) => {
        const rejected = { ...browse.rejected };
        const messages = { ...browse.messages };
        delete rejected[key];
        delete messages[key];
        const next: EvidenceBrowseState = { ...browse, page: 1, rejected, messages };
        if (key === EVIDENCE_BROWSE_PARAMS.publisher) next.publisher = '';
        if (key === EVIDENCE_BROWSE_PARAMS.sourceType) next.sourceType = '';
        if (key === EVIDENCE_BROWSE_PARAMS.credibilityTier) next.credibilityTier = '';
        if (key === EVIDENCE_BROWSE_PARAMS.hasCapture) next.hasCapture = '';
        if (key === EVIDENCE_BROWSE_PARAMS.sort) next.sort = '';
        applyBrowse(next);
    };

    /** Any browse change resets the local page to 1. */
    const updateBrowse = (patch: Partial<EvidenceBrowseState>, clearedKey?: string) => {
        const rejected = { ...browse.rejected };
        const messages = { ...browse.messages };
        if (clearedKey) {
            delete rejected[clearedKey];
            delete messages[clearedKey];
        }
        applyBrowse({ ...browse, ...patch, page: 1, rejected, messages });
    };

    const caseSavedViews = savedSnapshot.views;
    const mergedSavedViews = [...ephemeralViews, ...caseSavedViews];

    /** Evidence views store no query text at all (contracts §5). */
    const handleSaveView = () => {
        const result = saveSavedView({
            caseId,
            view: 'evidence',
            name: savedName,
            filters: {
                [EVIDENCE_BROWSE_PARAMS.publisher]: browse.publisher,
                [EVIDENCE_BROWSE_PARAMS.sourceType]: browse.sourceType,
                [EVIDENCE_BROWSE_PARAMS.credibilityTier]: browse.credibilityTier,
                [EVIDENCE_BROWSE_PARAMS.hasCapture]: browse.hasCapture,
            },
            sort: browse.sort || null,
            includeQuery: false,
            query: null,
        });
        if (result.ok) {
            setSavedSnapshot(result.snapshot);
            setSavedName('');
            setSavedNotice({ tone: 'status', text: `Saved “${result.view.name}” on this device.` });
            return;
        }
        const ephemeral = result.ephemeral;
        if (ephemeral) {
            setEphemeralViews((views) => [...views, ephemeral]);
            setSavedName('');
        }
        setSavedNotice({ tone: 'alert', text: result.message });
    };

    /** Apply only allowlisted metadata; selection and paging are never restored. */
    const applySavedView = (view: SavedView) => {
        const sort = view.sort === 'title' || view.sort === 'publishedAt' ? view.sort : '';
        applyBrowse({
            ...EMPTY_EVIDENCE_BROWSE,
            publisher: view.filters[EVIDENCE_BROWSE_PARAMS.publisher] ?? '',
            sourceType: view.filters[EVIDENCE_BROWSE_PARAMS.sourceType] ?? '',
            credibilityTier: view.filters[EVIDENCE_BROWSE_PARAMS.credibilityTier] ?? '',
            hasCapture: (view.filters[EVIDENCE_BROWSE_PARAMS.hasCapture] ?? '') as HasCaptureValue,
            sort,
            page: 1,
        });
        setSavedNotice({ tone: 'status', text: `Applied “${view.name}” to the loaded evidence.` });
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
            <div className="evidence-toolbar">
                <h3>Evidence Gallery ({visibleEvidence.length})</h3>
                <div className="toolbar-filters">
                    <div className="credibility-filter" role="group" aria-label="Credibility tier filter">
                        <button
                            type="button"
                            className={browse.credibilityTier === '' ? 'active' : ''}
                            aria-pressed={browse.credibilityTier === ''}
                            onClick={() =>
                                updateBrowse({ credibilityTier: '' }, EVIDENCE_BROWSE_PARAMS.credibilityTier)
                            }
                        >
                            All
                        </button>
                        {tierOptions.map((tier) => (
                            <button
                                key={tier}
                                type="button"
                                className={browse.credibilityTier === tier ? 'active' : ''}
                                aria-pressed={browse.credibilityTier === tier}
                                onClick={() =>
                                    updateBrowse(
                                        { credibilityTier: browse.credibilityTier === tier ? '' : tier },
                                        EVIDENCE_BROWSE_PARAMS.credibilityTier
                                    )
                                }
                            >
                                {getCredibilityLabel(tier)}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            <div className="evidence-filter-bar" role="group" aria-label="Evidence filters">
                <div className="evidence-field">
                    <label htmlFor="evidence-publisher">Publisher contains</label>
                    <input
                        id="evidence-publisher"
                        type="search"
                        className="evidence-input"
                        list="evidence-publisher-options"
                        value={browse.publisher}
                        placeholder="Any recorded publisher"
                        onChange={(event) =>
                            updateBrowse({ publisher: event.target.value }, EVIDENCE_BROWSE_PARAMS.publisher)
                        }
                    />
                    <datalist id="evidence-publisher-options">
                        {publisherOptions.map((publisher) => (
                            <option key={publisher} value={publisher} />
                        ))}
                    </datalist>
                </div>
                <div className="evidence-field">
                    <label htmlFor="evidence-source-type">Source type</label>
                    <select
                        id="evidence-source-type"
                        className="evidence-input"
                        value={browse.sourceType}
                        onChange={(event) =>
                            updateBrowse({ sourceType: event.target.value }, EVIDENCE_BROWSE_PARAMS.sourceType)
                        }
                    >
                        <option value="">All source types</option>
                        {sourceTypeOptions.map((sourceType) => (
                            <option key={sourceType} value={sourceType}>
                                {sourceType}
                            </option>
                        ))}
                    </select>
                </div>
                <div className="evidence-field">
                    <label htmlFor="evidence-has-capture">Capture</label>
                    <select
                        id="evidence-has-capture"
                        className="evidence-input"
                        value={browse.hasCapture}
                        onChange={(event) =>
                            updateBrowse(
                                { hasCapture: event.target.value as HasCaptureValue },
                                EVIDENCE_BROWSE_PARAMS.hasCapture
                            )
                        }
                    >
                        <option value="">Any capture state</option>
                        <option value="yes">Capture recorded</option>
                        <option value="no">No capture recorded</option>
                    </select>
                </div>
                <div className="evidence-field">
                    <label htmlFor="evidence-sort">Sort</label>
                    <select
                        id="evidence-sort"
                        className="evidence-input"
                        value={browse.sort}
                        onChange={(event) =>
                            updateBrowse({ sort: event.target.value as EvidenceSortKey }, EVIDENCE_BROWSE_PARAMS.sort)
                        }
                    >
                        <option value="">Recorded order</option>
                        <option value="title">Title (A–Z)</option>
                        <option value="publishedAt">Publication date (newest first)</option>
                    </select>
                </div>
            </div>

            {Object.entries(browse.messages).map(([key, message]) => (
                <div className="evidence-field-error" key={key} role="alert">
                    <span>{message}</span>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => clearField(key)}>
                        Clear filter
                    </button>
                </div>
            ))}

            <div className="evidence-saved-views" role="group" aria-label="Saved evidence views">
                <h4>Saved evidence views</h4>
                <p className="evidence-saved-views-note">
                    Saved views stay in this browser. They are local, not private: anyone using this browser profile can read them.
                </p>
                <div className="evidence-saved-views-save">
                    <div className="evidence-field">
                        <label htmlFor="evidence-saved-view-name">Saved view name</label>
                        <input
                            id="evidence-saved-view-name"
                            className="evidence-input"
                            value={savedName}
                            placeholder="e.g. High-tier captures by publisher"
                            onChange={(event) => setSavedName(event.target.value)}
                        />
                    </div>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={handleSaveView}>
                        Save current filters
                    </button>
                </div>
                {savedNotice && (
                    <p role={savedNotice.tone === 'alert' ? 'alert' : 'status'}>{savedNotice.text}</p>
                )}
                {mergedSavedViews.length > 0 && (
                    <ul className="evidence-saved-views-list" aria-label="Saved evidence views list">
                        {mergedSavedViews.map((view) => (
                            <li key={view.id}>
                                <span>{view.name}</span>
                                <span className="evidence-saved-views-summary">{describeSavedView(view)}</span>
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
                <div className="evidence-saved-views-actions">
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

            <p className="evidence-paging-note">
                Showing rows {visibleEvidence.length === 0 ? 0 : pageStart + 1}–
                {pageStart + pageEvidence.length} of {visibleEvidence.length} loaded results · page {currentPage}{' '}
                of {totalPages}. Paging is client-side over the evidence rows already loaded for this case.
            </p>

            {evidence.length === 0 && (
                <ReaderState
                    state="empty"
                    description="No evidence has been recorded for this case yet."
                    lastFetched={lastFetched}
                />
            )}

            {evidence.length > 0 && claimFilter && (
                <div className="evidence-claim-filter-note">
                    Filtered to evidence linked to claim <code>{claimFilter}</code>.
                    {visibleEvidence.length === 0 && ' No recorded evidence links to this claim.'}
                </div>
            )}

            {hasBrowseFilters && (
                <div className="evidence-filter-summary">
                    <span>Filtered view applied to the loaded results.</span>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={clearFilters}>
                        Clear filters
                    </button>
                </div>
            )}

            {selectedEvidenceId !== null && (
                <div className="evidence-selection" data-testid="evidence-selection">
                    <p>
                        Selected evidence <code>{selectedEvidenceId}</code>
                        {selectedVisible ? '' : ' — not in the current filter'}
                        {selectedEvidence?.title ? `: ${selectedEvidence.title}` : ''}
                    </p>
                    <div className="evidence-selection-actions">
                        <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            onClick={() =>
                                navigate(
                                    buildInspectorUrl(caseId, {
                                        claimId: claimFilter,
                                        evidenceId: selectedEvidenceId,
                                        captureId: selectedEvidence?.currentCaptureId ?? null,
                                    })
                                )
                            }
                        >
                            Inspect selected evidence
                        </button>
                        <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() =>
                                addToComparisonTray(caseId, comparisonContext, {
                                    evidenceId: selectedEvidenceId,
                                    // No capture is chosen on this list; Compare resolves
                                    // the default capture and pins it in the URL.
                                    captureId: null,
                                    title: selectedEvidence?.title ?? null,
                                    publisher: selectedEvidence?.publisher ?? null,
                                })
                            }
                        >
                            <GitCompare size={14} /> Add to comparison
                        </button>
                        <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => setSelectedEvidenceId(null)}
                        >
                            Clear selection
                        </button>
                    </div>
                </div>
            )}

            {comparisonTray.notice && (
                <div
                    className="evidence-field-error"
                    role="status"
                    data-state="comparison-tray-cleared"
                >
                    <span>{comparisonTray.notice}</span>
                </div>
            )}

            {comparisonTray.rejection && (
                <div
                    className="evidence-field-error"
                    role="alert"
                    data-state="comparison-tray-refused"
                >
                    <span>
                        {comparisonTray.rejection} No source in the draft was replaced.
                    </span>
                </div>
            )}

            {(comparisonTray.entries.length > 0 || comparisonTray.rejection) && (
                <div className="evidence-claim-filter-note" data-testid="comparison-tray-draft">
                    <span>
                        Comparison draft: {comparisonTray.entries.length} of 2 distinct sources
                        {comparisonTray.entries.length > 0
                            ? ` (${comparisonTray.entries
                                  .map((entry) => entry.evidenceId)
                                  .join(', ')})`
                            : ''}
                        . Session-only and scoped to this case.
                    </span>
                    <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => navigate(`/cases/${encodeURIComponent(caseId)}/compare`)}
                    >
                        <GitCompare size={14} /> Open comparison
                    </button>
                </div>
            )}

            {evidence.length > 0 && visibleEvidence.length === 0 && (
                <div className="evidence-filter-empty" data-state="evidence-filter-empty">
                    <ReaderState
                        state="empty"
                        title="No loaded evidence matches these filters"
                        description="The loaded evidence list is unchanged; only the client-side filters hide every row. Adjust or clear a filter to see evidence again."
                    />
                </div>
            )}

            <div className="evidence-grid">
                {pageEvidence.map((ev) => {
                    const provenance = readEvidenceProvenance(ev);
                    const isSelected = selectedEvidenceId === ev.id;
                    return (
                        <div
                            key={ev.id}
                            className={`evidence-card glass-panel ${ev.requiresHumanReview ? 'requires-review' : ''} ${isSelected ? 'selected' : ''}`}
                            data-provenance={provenance.kind}
                            data-evidence-id={ev.id}
                        >
                            <div className="evidence-card-header">
                                <div className="evidence-card-tags">
                                    {renderVerificationBadge(ev.verificationStatus)}
                                    <span
                                        className={`badge evidence-provenance ${provenance.badgeClass}`}
                                        data-provenance={provenance.kind}
                                        title={provenance.detail}
                                    >
                                        {provenance.label}
                                    </span>
                                </div>
                                <span className="source-type">{ev.sourceType}</span>
                            </div>
                            <h4 className="evidence-title">{ev.title}</h4>
                            <div className="evidence-meta">
                                <span>{ev.publisher}</span>
                                <span className={`credibility tier-${ev.credibilityTier}`}>
                                    {getCredibilityLabel(ev.credibilityTier)}
                                </span>
                            </div>
                            <div className="evidence-facts">
                                <span className="evidence-id" title="Stable evidence ID">{ev.id}</span>
                                <span>{ev.currentCaptureId ? 'Capture recorded' : 'No capture recorded'}</span>
                            </div>

                            <div className="evidence-footer">
                                <span className="linked-claims"><FileSearch size={14} /> {ev.linkedClaims.length} Claims</span>
                                <div className="evidence-card-actions">
                                    <button
                                        type="button"
                                        className={`btn btn-sm evidence-select-btn ${isSelected ? 'btn-primary' : 'btn-secondary'}`}
                                        aria-pressed={isSelected}
                                        aria-label={
                                            isSelected
                                                ? `Deselect evidence ${ev.id}`
                                                : `Select evidence ${ev.id}`
                                        }
                                        onClick={() =>
                                            setSelectedEvidenceId(isSelected ? null : ev.id)
                                        }
                                    >
                                        {isSelected ? 'Selected' : 'Select'}
                                    </button>
                                    <button
                                        type="button"
                                        className="btn btn-secondary btn-sm"
                                        onClick={() =>
                                            navigate(
                                                buildInspectorUrl(caseId, {
                                                    claimId: claimFilter,
                                                    evidenceId: ev.id,
                                                    captureId: ev.currentCaptureId ?? null,
                                                })
                                            )
                                        }
                                    >
                                        <FileSearch size={14} /> Inspect source
                                    </button>
                                    {(() => {
                                        const sourceUrl =
                                            safeExternalUrl(ev.originUrl) ??
                                            safeExternalUrl(ev.canonicalUrl);
                                        if (sourceUrl) {
                                            return (
                                                <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="btn btn-secondary btn-sm">
                                                    <Link size={14} /> Source
                                                </a>
                                            );
                                        }
                                        return (
                                            <span className="btn btn-secondary btn-sm source-unavailable" title={ev.publisher ? `No link available for ${ev.publisher}` : "No source link available"}>
                                                <Link size={14} /> Source
                                            </span>
                                        );
                                    })()}
                                </div>
                            </div>

                            {ev.verificationChecks.length > 0 && (
                                <div className="verification-section">
                                    <button
                                        type="button"
                                        className="verification-toggle"
                                        aria-expanded={expandedChecks.has(ev.id)}
                                        aria-controls={`verification-checks-${ev.id}`}
                                        onClick={() => toggleChecks(ev.id)}
                                    >
                                        {expandedChecks.has(ev.id) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                        <ClipboardCheck size={14} />
                                        Verification Details ({ev.verificationChecks.length})
                                    </button>

                                    {expandedChecks.has(ev.id) && (
                                        <div className="verification-checks" id={`verification-checks-${ev.id}`}>
                                            {ev.verificationChecks.map((check) => (
                                                <div key={check.id} className="check-row">
                                                    <div className="check-header">
                                                        <span className="check-type">{check.checkType}</span>
                                                        <span className="check-result badge badge-info">{check.result}</span>
                                                        {check.method && <span className="check-method">{check.method}</span>}
                                                    </div>
                                                    {check.notes && <p className="check-notes">{check.notes}</p>}
                                                    {check.verifiedBy && (
                                                        <span className="check-meta">
                                                            by {check.verifiedBy} {check.verifiedAt && `at ${new Date(check.verifiedAt).toLocaleString()}`}
                                                        </span>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>

            <div className="evidence-pager">
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

export default EvidenceTab;
