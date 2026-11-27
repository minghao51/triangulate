import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Exception } from '../../types/backend-models';
import { getExceptionsForCase, submitExceptionAction } from '../../services/api';
import { ApiError } from '../../services/api-error';
import {
  actionEligible,
  blocksRowPost,
  rowAttemptsFor,
  storeRowAttempts,
  type RowAttempt,
  type RowAttempts,
  type ExceptionActionPayload,
  type RowWriteKind,
  type RowWriteState,
} from './exception-row-attempts';
import Button from '../../components/design-system/Button';
import ReaderState from '../../components/design-system/ReaderState';
import { AlertOctagon, AlertTriangle, Info, TerminalSquare } from 'lucide-react';
import './ExceptionsTab.css';

interface ExceptionsTabProps {
  caseId: string;
  refreshToken?: number;
}

// Each row owns its write state. Pending disables only that row; every other
// state is honest about whether the server acked the write *and* the read
// refreshed. The mutation never retries by itself (`retry: false`).
interface RowWriteCopy {
  label: string;
  text: string;
  tone: 'success' | 'warning' | 'danger' | 'info';
  role: 'status' | 'alert';
}

const ROW_WRITE_COPY: Record<RowWriteKind, RowWriteCopy> = {
  pending: {
    label: 'Saving…',
    text: 'Saving this row; other rows wait for this answer before they can post.',
    tone: 'info',
    role: 'status',
  },
  saved: {
    label: 'Saved and refreshed',
    text: 'The server acknowledged this action and the queue was re-read.',
    tone: 'success',
    role: 'status',
  },
  conflict: {
    label: 'Writer conflict (409)',
    text: 'Another writer holds this case; this row was not changed. Retry only after the other writer finishes.',
    tone: 'warning',
    role: 'alert',
  },
  blocked: {
    label: 'Blocked (422)',
    text: 'The server rejected this action as invalid or not permitted for this case.',
    tone: 'danger',
    role: 'alert',
  },
  failed: {
    label: 'Rejected by the server',
    text: 'The server answered with an error and rejected this action.',
    tone: 'danger',
    role: 'alert',
  },
  uncertain: {
    label: 'Outcome unknown',
    text: 'The response was lost, so the server may or may not have applied this action. Reconcile with a read before retrying.',
    tone: 'warning',
    role: 'alert',
  },
  reconciled: {
    label: 'Read refreshed — still inconclusive',
    text: 'The read cannot prove whether this action landed. A manual retry requires your explicit confirmation.',
    tone: 'warning',
    role: 'alert',
  },
  'refresh-failed': {
    label: 'Accepted; refresh failed',
    text: 'The server acknowledged this action, but the queue re-read failed. Retry the read only — do not resubmit.',
    tone: 'warning',
    role: 'alert',
  },
  stale: {
    label: 'Stale',
    text: 'A recorded invalidation or detected refresh happened after this row was saved. Re-check the latest recorded state.',
    tone: 'warning',
    role: 'status',
  },
};

const ROW_TONE_COLOR: Record<RowWriteCopy['tone'], string> = {
  success: '#00ff9d',
  warning: '#ffb800',
  danger: '#ff4757',
  info: '#00d4ff',
};

/**
 * Classify a failed POST.
 *
 * 409 (writer conflict at admission), 422 (invalid/blocked action) and the known
 * 404 (missing case/exception) refuse the write before it is applied. Any other
 * response — 5xx, an unexpected 4xx — or no response at all can arrive after the
 * write committed, so it is an unknown outcome, never a rejection.
 */
function rowStateFromError(error: unknown): RowWriteState {
  if (error instanceof ApiError) {
    if (error.status === 409) return { kind: 'conflict', detail: error.message };
    if (error.status === 422) return { kind: 'blocked', detail: error.message };
    if (error.status === 404) return { kind: 'failed', detail: `404: ${error.message}` };
    return {
      kind: 'uncertain',
      detail: `The server answered ${error.status} (${error.message}); that is not proof this action was refused.`,
    };
  }
  return { kind: 'uncertain', detail: error instanceof Error ? error.message : null };
}

function messageOf(error: unknown): string | null {
  return error instanceof Error ? error.message : null;
}

/**
 * The exception action answers with the updated case (`CaseListItem`), which
 * always carries the case `id`. An ack that names a different case — or names
 * no case at all — cannot identify the expected recorded result, so it is
 * ambiguous rather than acknowledged and the follow-up read is the only
 * evidence reported.
 */
function ackIdentifiesCase(ack: unknown, caseId: string): boolean {
  if (ack === null || typeof ack !== 'object') return false;
  const id = (ack as { id?: unknown }).id;
  return typeof id === 'string' && id === caseId;
}

interface ExceptionAttemptInput {
  payload: ExceptionActionPayload;
  attemptId: number;
}

const RowStateBanner: React.FC<{ state: RowWriteState; children?: React.ReactNode }> = ({
  state,
  children,
}) => {
  const copy = ROW_WRITE_COPY[state.kind];
  const color = ROW_TONE_COLOR[copy.tone];
  return (
    <div
      role={copy.role}
      data-write-state={state.kind}
      aria-live={copy.role === 'status' ? 'polite' : undefined}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.375rem',
        marginTop: '0.5rem',
        padding: '0.625rem',
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

const ExceptionsTab: React.FC<ExceptionsTabProps> = ({ caseId, refreshToken = 0 }) => {
  const queryClient = useQueryClient();
  // Row locks live in the in-memory per-case record so a view switch cannot
  // unlock a row whose outcome is still unresolved.
  const [rowAttempts, setRowAttempts] = useState<RowAttempts>(() => rowAttemptsFor(caseId));

  const caseIdRef = useRef(caseId);
  useEffect(() => {
    caseIdRef.current = caseId;
    setRowAttempts(rowAttemptsFor(caseId));
  }, [caseId]);

  /** Apply a record update for `targetCaseId`; only the mounted case re-renders. */
  const commitRows = useCallback(
    (targetCaseId: string, update: (rows: RowAttempts) => RowAttempts) => {
      const next = update(rowAttemptsFor(targetCaseId));
      storeRowAttempts(targetCaseId, next);
      if (targetCaseId === caseIdRef.current) setRowAttempts(next);
      return next;
    },
    []
  );

  const setRow = (targetCaseId: string, exceptionId: string, attempt: RowAttempt) =>
    commitRows(targetCaseId, (rows) => ({ ...rows, [exceptionId]: attempt }));

  const {
    data,
    isLoading,
    error: readError,
    refetch,
    dataUpdatedAt,
  } = useQuery({
    queryKey: ['exceptions', caseId],
    queryFn: () => getExceptionsForCase(caseId),
    enabled: Boolean(caseId),
    retry: false,
  });

  const lastRefreshToken = useRef(refreshToken);
  useEffect(() => {
    if (lastRefreshToken.current === refreshToken) return;
    lastRefreshToken.current = refreshToken;
    void refetch();
  }, [refreshToken, refetch]);

  const refreshQueue = async (targetCaseId: string) => {
    const refreshedQueue = await getExceptionsForCase(targetCaseId);
    queryClient.setQueryData(['exceptions', targetCaseId], refreshedQueue);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['caseDetail', targetCaseId] }),
      queryClient.invalidateQueries({ queryKey: ['cases'] }),
      queryClient.invalidateQueries({ queryKey: ['reviewActivity', targetCaseId] }),
      queryClient.invalidateQueries({ queryKey: ['evaluationSummary', targetCaseId] }),
      queryClient.invalidateQueries({ queryKey: ['monitoringSummary'] }),
    ]);
  };

  const queueEpoch = (targetCaseId: string) =>
    queryClient.getQueryState(['exceptions', targetCaseId])?.dataUpdatedAt ?? 0;

  const markOtherRowsStale = (previous: RowAttempts, savedId: string): RowAttempts => {
    const next: RowAttempts = {};
    for (const [id, attempt] of Object.entries(previous)) {
      if (id === savedId) {
        next[id] = attempt;
      } else if (attempt.state.kind === 'saved' || attempt.state.kind === 'refresh-failed') {
        // Re-reading the queue is a detected refresh: older save banners are
        // no longer proof of the current recorded state.
        next[id] = { ...attempt, state: { kind: 'stale' } };
      } else {
        next[id] = attempt;
      }
    }
    return next;
  };

  const actionMutation = useMutation({
    retry: false,
    mutationFn: (attempt: ExceptionAttemptInput) =>
      submitExceptionAction(
        attempt.payload.caseId,
        attempt.payload.exceptionId,
        attempt.payload.action
      ),
    onSuccess: async (ack, attempt) => {
      const { payload, attemptId } = attempt;
      if (!ackIdentifiesCase(ack, payload.caseId)) {
        // An ack that cannot identify the recorded case is not proof of success.
        commitRows(payload.caseId, (rows) =>
          rows[payload.exceptionId]?.attemptId === attemptId
            ? {
                ...rows,
                [payload.exceptionId]: {
                  ...rows[payload.exceptionId],
                  state: {
                    kind: 'uncertain',
                    detail:
                      'The server answered without identifying the recorded case, so whether this action landed is unknown.',
                  },
                },
              }
            : rows
        );
        return;
      }
      try {
        await refreshQueue(payload.caseId);
      } catch (refreshError) {
        commitRows(payload.caseId, (rows) =>
          rows[payload.exceptionId]?.attemptId === attemptId
            ? {
                ...rows,
                [payload.exceptionId]: {
                  ...rows[payload.exceptionId],
                  state: { kind: 'refresh-failed', detail: messageOf(refreshError) },
                },
              }
            : rows
        );
        return;
      }
      const epoch = queueEpoch(payload.caseId);
      commitRows(payload.caseId, (rows) =>
        rows[payload.exceptionId]?.attemptId === attemptId
          ? markOtherRowsStale(
              {
                ...rows,
                [payload.exceptionId]: {
                  state: { kind: 'saved', epoch },
                  attemptId,
                  payload: null,
                  recoveryPending: false,
                },
              },
              payload.exceptionId
            )
          : rows
      );
    },
    onError: (error, attempt) => {
      const { payload, attemptId } = attempt;
      commitRows(payload.caseId, (rows) =>
        rows[payload.exceptionId]?.attemptId === attemptId
          ? {
              ...rows,
              [payload.exceptionId]: {
                ...rows[payload.exceptionId],
                state: rowStateFromError(error),
              },
            }
          : rows
      );
    },
  });

  // A later queue read turns an earlier "saved" banner stale instead of letting
  // it keep claiming the current state.
  useEffect(() => {
    const rows = rowAttemptsFor(caseId);
    const staleIds = Object.entries(rows)
      .filter(
        ([, attempt]) =>
          attempt.state.kind === 'saved' &&
          typeof attempt.state.epoch === 'number' &&
          dataUpdatedAt > attempt.state.epoch
      )
      .map(([id]) => id);
    if (staleIds.length === 0) return;
    commitRows(caseId, (current) => {
      const next: RowAttempts = { ...current };
      let changed = false;
      for (const id of staleIds) {
        const attempt = next[id];
        if (attempt?.state.kind === 'saved') {
          next[id] = { ...attempt, state: { kind: 'stale' } };
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [dataUpdatedAt, caseId, commitRows]);

  /** Start one attempt; the record write is synchronous so a second dispatch in
   * the same tick sees the lock before React re-renders. */
  const startActionAttempt = (payload: ExceptionActionPayload) => {
    const current = rowAttemptsFor(payload.caseId)[payload.exceptionId];
    if (current?.recoveryPending || current?.state.kind === 'pending') return;
    const attemptId = (current?.attemptId ?? 0) + 1;
    setRow(payload.caseId, payload.exceptionId, {
      state: { kind: 'pending' },
      attemptId,
      payload,
      recoveryPending: false,
    });
    actionMutation.mutate({ payload, attemptId });
  };

  const submitAction = (exceptionId: string, action: string) => {
    const rows = rowAttemptsFor(caseId);
    // One POST at a time: the second row's ordinary control is refused here, not
    // silently dropped after the click.
    if (Object.values(rows).some((attempt) => attempt.state.kind === 'pending')) return;
    const current = rows[exceptionId];
    if (current && blocksRowPost(current)) return;
    startActionAttempt({ caseId, exceptionId, action });
  };

  /** One explicit confirmation resends exactly the submitted payload, or nothing
   * when the row no longer permits that action. */
  const confirmRowRetry = (exceptionId: string) => {
    const current = rowAttemptsFor(caseId)[exceptionId];
    if (!current || current.state.kind !== 'reconciled' || current.recoveryPending) return;
    const payload = current.payload;
    if (!payload || payload.caseId !== caseId) return;
    const row = exceptions.find((exception) => exception.id === payload.exceptionId);
    if (!row || !actionEligible(row, payload.action)) {
      setRow(caseId, exceptionId, {
        ...current,
        state: {
          kind: 'reconciled',
          detail:
            'This row no longer permits the recorded action, so the retry was refused without sending anything.',
        },
      });
      return;
    }
    startActionAttempt(payload);
  };

  /** Recovery after an acknowledged action: the queue read only. */
  const retryRowRefresh = async (exceptionId: string) => {
    const current = rowAttemptsFor(caseId)[exceptionId];
    if (!current || current.state.kind !== 'refresh-failed' || current.recoveryPending) return;
    const { attemptId } = current;
    setRow(caseId, exceptionId, { ...current, recoveryPending: true });
    let epoch: number;
    try {
      await refreshQueue(caseId);
      epoch = queueEpoch(caseId);
    } catch (refreshError) {
      // A failed recovery preserves the retry capability for the read.
      commitRows(caseId, (rows) => {
        const attempt = rows[exceptionId];
        if (
          attempt?.attemptId !== attemptId ||
          attempt.state.kind !== 'refresh-failed'
        ) {
          return rows;
        }
        return {
          ...rows,
          [exceptionId]: {
            ...attempt,
            recoveryPending: false,
            state: { kind: 'refresh-failed', detail: messageOf(refreshError) },
          },
        };
      });
      return;
    }
    commitRows(caseId, (rows) => {
      const attempt = rows[exceptionId];
      if (attempt?.attemptId !== attemptId || attempt.state.kind !== 'refresh-failed') return rows;
      return markOtherRowsStale(
        {
          ...rows,
          [exceptionId]: { state: { kind: 'saved', epoch }, attemptId, payload: null, recoveryPending: false },
        },
        exceptionId
      );
    });
  };

  // GET-only reconciliation. It never concludes that the action landed.
  const reconcileRow = async (exceptionId: string) => {
    const current = rowAttemptsFor(caseId)[exceptionId];
    if (!current || current.state.kind !== 'uncertain' || current.recoveryPending) return;
    const { attemptId } = current;
    setRow(caseId, exceptionId, { ...current, recoveryPending: true });
    try {
      await refreshQueue(caseId);
      commitRows(caseId, (rows) => {
        const attempt = rows[exceptionId];
        if (attempt?.attemptId !== attemptId || attempt.state.kind !== 'uncertain') return rows;
        return {
          ...rows,
          [exceptionId]: {
            ...attempt,
            recoveryPending: false,
            state: { kind: 'reconciled', detail: attempt.state.detail ?? null },
          },
        };
      });
    } catch (refreshError) {
      commitRows(caseId, (rows) => {
        const attempt = rows[exceptionId];
        if (attempt?.attemptId !== attemptId || attempt.state.kind !== 'uncertain') return rows;
        return {
          ...rows,
          [exceptionId]: {
            ...attempt,
            recoveryPending: false,
            state: {
              kind: 'uncertain',
              detail: `Reconciliation read failed: ${messageOf(refreshError) ?? 'unknown error'}`,
            },
          },
        };
      });
    }
  };

  /** Severity stated as text, so it is never conveyed by icon and colour alone. */
  const getSeverityLabel = (severity: Exception['severity']): string => {
    switch (severity) {
      case 'high': return 'High';
      case 'medium': return 'Medium';
      case 'low': return 'Low';
    }
  };

  const getSeverityIcon = (severity: Exception['severity']) => {
    switch (severity) {
      case 'high': return <AlertOctagon size={18} className="text-danger" />;
      case 'medium': return <AlertTriangle size={18} className="text-warning" />;
      case 'low': return <Info size={18} className="text-info" />;
    }
  };

  const exceptions = data ?? [];
  const anyRowPending = Object.values(rowAttempts).some(
    (attempt) => attempt.state.kind === 'pending'
  );
  const lastFetched = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  let stateBody: React.ReactNode = null;
  if (!caseId) {
    stateBody = (
      <ReaderState
        state="not-found"
        title="No case selected"
        description="Choose a case to view its exception queue."
      />
    );
  } else if (isLoading) {
    stateBody = (
      <ReaderState
        state="loading"
        description="Fetching the exception queue for this case."
      />
    );
  } else if (readError) {
    stateBody = (
      <ReaderState
        state="network-error"
        title="Exception queue unavailable"
        description="The exception queue could not be read. This is not the same as an empty queue."
        detail={readError instanceof Error ? readError.message : null}
        onRetry={() => void refetch()}
        lastFetched={lastFetched}
      />
    );
  } else if (exceptions.length === 0) {
    stateBody = (
      <ReaderState
        state="empty"
        title="No open exceptions"
        description="No exceptions are blocking the pipeline for this case."
        lastFetched={lastFetched}
      />
    );
  }

  return (
    <div className="exceptions-container p-base">
      <div className="exceptions-header">
        <h3>Exception Queue</h3>
        <p className="subtitle">Human interventions blocking the automated pipeline.</p>
      </div>

      <div className="exceptions-list">
        {stateBody}
        {!stateBody && exceptions.map(exc => {
          const rowAttempt = rowAttempts[exc.id];
          const rowState = rowAttempt?.state;
          const rowBusy = rowState?.kind === 'pending';
          // One POST at a time: while a row posts, other rows wait instead of
          // accepting a click that would be refused.
          const rowDisabled = rowAttempt
            ? blocksRowPost(rowAttempt) || (anyRowPending && !rowBusy)
            : anyRowPending;
          return (
            <div
              key={exc.id}
              className={`exception-card glass-panel severity-${exc.severity}`}
              data-exception-id={exc.id}
            >
              <div className="exc-main">
                <div className="exc-icon" aria-hidden="true">{getSeverityIcon(exc.severity)}</div>
                <div className="exc-content">
                  <div className="exc-type">{exc.type.replace(/_/g, ' ')}</div>
                  <div className="exc-severity">Severity: {getSeverityLabel(exc.severity)}</div>
                  <div className="exc-message">{exc.message}</div>
                  <div className="exc-recommendation">Status: {exc.status}</div>
                  <div className="exc-recommendation">Action: {exc.recommendedAction}</div>
                  {rowAttempt && rowState && (
                    <RowStateBanner state={rowState}>
                      {rowAttempt.recoveryPending && (
                        <p role="status">Read-only recovery request in progress…</p>
                      )}
                      {rowState.kind === 'refresh-failed' && (
                        <div>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => void retryRowRefresh(exc.id)}
                            disabled={rowAttempt.recoveryPending}
                          >
                            {rowAttempt.recoveryPending ? 'Retrying refresh…' : 'Retry refresh (GET)'}
                          </Button>
                        </div>
                      )}
                      {rowState.kind === 'uncertain' && (
                        <div>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => void reconcileRow(exc.id)}
                            disabled={rowAttempt.recoveryPending}
                          >
                            {rowAttempt.recoveryPending ? 'Reconciling…' : 'Reconcile with read (GET)'}
                          </Button>
                        </div>
                      )}
                      {rowState.kind === 'reconciled' && (
                        <div>
                          <p style={{ marginBottom: '0.375rem' }}>
                            Retrying may append a duplicate audit entry; it does not edit the earlier one.
                          </p>
                          <Button
                            variant="danger"
                            size="sm"
                            onClick={() => confirmRowRetry(exc.id)}
                            disabled={rowAttempt.recoveryPending}
                          >
                            Confirm retry
                          </Button>
                        </div>
                      )}
                    </RowStateBanner>
                  )}
                </div>
              </div>
              <div className="exc-actions">
                <div className="action-buttons">
                  {exc.isOpen ? (
                    <>
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => submitAction(exc.id, 'resolve')}
                        disabled={rowDisabled}
                      >
                        Resolve
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => submitAction(exc.id, 'defer')}
                        disabled={rowDisabled}
                      >
                        Defer
                      </Button>
                    </>
                  ) : (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => submitAction(exc.id, 'reopen')}
                      disabled={rowDisabled}
                    >
                      Reopen
                    </Button>
                  )}
                </div>
                <div className="exc-recommendation">
                  <TerminalSquare size={14} /> CLI fallback
                </div>
                <code className="exc-recommendation">
                  {`uv run triangulate case exception ${caseId} ${exc.id} --action ${exc.isOpen ? 'resolve' : 'reopen'}`}
                </code>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ExceptionsTab;
