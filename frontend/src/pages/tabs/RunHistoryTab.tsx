import React, { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getInvestigationRuns, getRunHistoryForCase } from '../../services/api';
import { isNotFound } from '../../services/api-error';
import { buildReportUrl } from '../../services/deep-links';
import ReaderState from '../../components/design-system/ReaderState';
import { Activity, Code2, AlertCircle, Clock } from 'lucide-react';
import { formatDistanceStrict, parseISO } from 'date-fns';
import type { InvestigationRun } from '../../types/backend-models';
import './RunHistoryTab.css';

interface RunHistoryTabProps {
  caseId: string;
  refreshToken?: number;
}

/** How many recent grouped runs the identifier legend loads. */
const GROUPED_RUN_LIMIT = 50;

function shortId(value: string): string {
    return value.length > 14 ? `${value.slice(0, 10)}…` : value;
}

/**
 * Grouped-run status wording. A grouped run reports its own invocation status;
 * it is not a stage attempt status and it never attributes a change to anyone.
 */
function groupedStatusLabel(status: string): string {
    switch (status) {
        case 'running':
            return 'Running';
        case 'succeeded':
            return 'Succeeded';
        case 'paused':
            return 'Paused — manual gate';
        case 'failed':
            return 'Failed';
        case 'interrupted':
            return 'Interrupted';
        default:
            return status;
    }
}

/**
 * Run-history reader.
 *
 * The table is stage-oriented: every row is one recorded stage attempt and its
 * `case_stage_runs` ID (the same value `Event.case_run_id` points at). Grouped
 * `InvestigationRun` IDs are listed separately and labelled as grouped-run IDs,
 * so the two identifier kinds are never conflated. A run reference is an
 * observer/recording reference only — it never names an actor or a cause.
 *
 * Keyed by case with the existing `['run-history', caseId]` shape, so the
 * pipeline monitor and this table never hold two caches for the same run list.
 */
const RunHistoryTab: React.FC<RunHistoryTabProps> = ({ caseId, refreshToken = 0 }) => {
    const { data, isLoading, error, refetch, dataUpdatedAt } = useQuery({
        queryKey: ['run-history', caseId],
        queryFn: () => getRunHistoryForCase(caseId),
        enabled: Boolean(caseId),
    });

    // Same cache key and limit as the Changes tab so one grouped-run list is
    // shared rather than fetched twice for the same case.
    const {
        data: groupedData,
        error: groupedError,
        refetch: refetchGrouped,
    } = useQuery({
        queryKey: ['investigation-runs', caseId],
        queryFn: () => getInvestigationRuns(caseId, { limit: GROUPED_RUN_LIMIT }),
        enabled: Boolean(caseId),
        retry: false,
    });

    const lastRefreshToken = useRef(refreshToken);
    useEffect(() => {
        if (lastRefreshToken.current === refreshToken) return;
        lastRefreshToken.current = refreshToken;
        void refetch();
        void refetchGrouped();
    }, [refreshToken, refetch, refetchGrouped]);

    const runs = data ?? [];
    const groupedRuns: InvestigationRun[] = groupedData?.items ?? [];
    const groupedTotal = groupedData?.total ?? groupedRuns.length;
    const lastFetched = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

    const groupedSection = (
        <section className="history-grouped" aria-labelledby="grouped-runs-heading">
            <h4 id="grouped-runs-heading">Grouped investigation runs</h4>
            <p className="history-id-note">
                A <strong>grouped run ID</strong> identifies one investigation invocation and
                groups the stage attempts below it. It is not a stage attempt ID, and neither
                reference identifies who made a change. A run's published report artifacts open
                from the Report tab; a run without published artifacts shows an explicit
                no-report state there.
            </p>
            {groupedError ? (
                <div className="history-grouped-state" role="alert">
                    <AlertCircle size={14} />
                    <span>
                        Grouped runs could not be loaded.{' '}
                        {groupedError instanceof Error ? groupedError.message : ''}
                    </span>
                    <button
                        type="button"
                        className="history-grouped-retry"
                        onClick={() => {
                            void refetchGrouped();
                        }}
                    >
                        Retry grouped runs
                    </button>
                </div>
            ) : null}
            {!groupedError && groupedRuns.length === 0 ? (
                <p className="history-grouped-state">
                    No grouped investigation runs have been recorded for this case.
                </p>
            ) : null}
            {groupedRuns.length > 0 ? (
                <ul className="history-grouped-list">
                    {groupedRuns.map((run) => (
                        <li
                            className="history-grouped-run"
                            key={run.id}
                            data-id-kind="grouped-run"
                        >
                            <span className="history-grouped-sequence">
                                Grouped run <strong>#{run.sequence}</strong>
                            </span>
                            <span className="history-grouped-id">
                                Grouped run ID{' '}
                                <code data-id-kind="grouped-run-id" title={run.id}>
                                    {shortId(run.id)}
                                </code>
                            </span>
                            <span className="history-grouped-status">
                                {groupedStatusLabel(run.status)}
                            </span>
                            <span className="history-grouped-time">
                                Started{' '}
                                {run.startedAt ? parseISO(run.startedAt).toISOString() : 'not recorded'}
                            </span>
                            <Link
                                className="history-grouped-report-link"
                                to={buildReportUrl(caseId, { runId: run.id })}
                                data-testid={`history-grouped-report-link-${run.id}`}
                            >
                                View frozen report
                            </Link>
                        </li>
                    ))}
                </ul>
            ) : null}
            {groupedRuns.length > 0 && groupedTotal > groupedRuns.length ? (
                <p className="history-grouped-state">
                    Showing the latest {groupedRuns.length} of {groupedTotal} grouped runs.
                </p>
            ) : null}
        </section>
    );

    let stateBody: React.ReactNode;
    if (!caseId) {
        stateBody = (
            <ReaderState
                state="not-found"
                title="No case selected"
                description="Choose a case to view its pipeline run history."
            />
        );
    } else if (isLoading) {
        stateBody = <ReaderState state="loading" description="Fetching the pipeline run history for this case." />;
    } else if (error) {
        stateBody = isNotFound(error) ? (
            <ReaderState state="not-found" description="This case has no run history." />
        ) : (
            <ReaderState
                state="network-error"
                description="The run history could not be loaded."
                detail={error instanceof Error ? error.message : null}
                onRetry={() => {
                    void refetch();
                }}
                lastFetched={lastFetched}
            />
        );
    } else if (runs.length === 0) {
        stateBody = (
            <ReaderState
                state="empty"
                description="No pipeline runs have been recorded for this case yet."
                lastFetched={lastFetched}
            />
        );
    } else {
        stateBody = (
            <section className="history-stage-attempts" aria-labelledby="stage-attempts-heading">
                <h4 id="stage-attempts-heading">Stage attempts</h4>
                <p className="history-id-note">
                    One row per recorded stage attempt. Its <strong>stage attempt ID</strong> is
                    the recorded pipeline step attempt, never a grouped run ID.
                </p>
                <div className="history-table-container glass-panel">
                    <table className="history-table">
                        <thead>
                            <tr>
                                <th>Stage</th>
                                <th>Stage attempt ID</th>
                                <th>Model / Engine</th>
                                <th>Duration</th>
                                <th>Fallbacks</th>
                                <th>Status / Output</th>
                                <th>Time</th>
                            </tr>
                        </thead>
                        <tbody>
                            {runs.map(run => (
                                <tr key={run.id} className="history-row" data-id-kind="stage-attempt">
                                    <td>
                                        <span className="badge badge-neutral">{run.stage}</span>
                                    </td>
                                    <td>
                                        <code
                                            className="history-stage-id"
                                            data-id-kind="stage-attempt-id"
                                            title={run.id}
                                        >
                                            {shortId(run.id)}
                                        </code>
                                    </td>
                                    <td className="model-cell">
                                        <Code2 size={14} className="text-secondary" /> {run.model}
                                    </td>
                                    <td>{run.durationMs ? formatDistanceStrict(0, run.durationMs) : '-'}</td>
                                    <td>{run.fallbackCount}</td>
                                    <td>
                                        {run.status === 'success' ? (
                                            <span className="text-success" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                                <Activity size={14} /> Success
                                            </span>
                                        ) : (
                                            <span className="text-danger" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.875rem' }}>
                                                <AlertCircle size={14} /> {run.message}
                                            </span>
                                        )}
                                    </td>
                                    <td className="time-cell">
                                        <Clock size={12} className="text-tertiary" /> {run.timestamp ? parseISO(run.timestamp).toISOString() : '-'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </section>
        );
    }

    return (
        <div className="run-history-container p-base">
            <div className="history-header">
                <h3>Pipeline Execution History</h3>
                <p className="subtitle">Audit log of recorded stage attempts, model interventions, and parse fallbacks.</p>
            </div>

            {caseId ? groupedSection : null}

            {stateBody}
        </div>
    );
};

export default RunHistoryTab;
