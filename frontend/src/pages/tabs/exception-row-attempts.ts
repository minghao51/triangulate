import type { Exception } from '../../types/backend-models';

/**
 * Per-row write attempts for the exception queue.
 *
 * A view switch unmounts the exceptions tab, so an unresolved row's lock has to
 * outlive it or the next visit would allow a second POST. This is plain in-memory
 * ownership keyed by case id: a late case A outcome can never reach a case B row,
 * nothing is persisted, and the case workspace releases the records on close.
 */
export type RowWriteKind =
  | 'pending'
  | 'saved'
  | 'conflict'
  | 'blocked'
  | 'failed'
  | 'uncertain'
  | 'reconciled'
  | 'refresh-failed'
  | 'stale';

export interface RowWriteState {
  kind: RowWriteKind;
  detail?: string | null;
  /** `dataUpdatedAt` of the read refresh that proved this row's save. */
  epoch?: number;
}

export interface ExceptionActionPayload {
  caseId: string;
  exceptionId: string;
  action: string;
}

/**
 * One row's write operation: the submitted payload is immutable (a confirmed
 * retry resends exactly it), the attempt identity stops a late callback from
 * unlocking a newer attempt, and `recoveryPending` prevents duplicate GETs.
 */
export interface RowAttempt {
  state: RowWriteState;
  attemptId: number;
  payload: ExceptionActionPayload | null;
  recoveryPending: boolean;
}

export type RowAttempts = Record<string, RowAttempt>;

const rowAttemptsByCase = new Map<string, RowAttempts>();

export function rowAttemptsFor(caseId: string): RowAttempts {
  return rowAttemptsByCase.get(caseId) ?? {};
}

export function storeRowAttempts(caseId: string, rows: RowAttempts): RowAttempts {
  rowAttemptsByCase.set(caseId, rows);
  return rows;
}

/** Drop the in-memory row records for one case (or all of them). */
export function clearExceptionRowAttempts(caseId?: string): void {
  if (caseId) rowAttemptsByCase.delete(caseId);
  else rowAttemptsByCase.clear();
}

/** States in which an ordinary POST is forbidden for this row. */
export function blocksRowPost(attempt: RowAttempt): boolean {
  if (attempt.recoveryPending) return true;
  return (
    attempt.state.kind === 'pending' ||
    attempt.state.kind === 'refresh-failed' ||
    attempt.state.kind === 'uncertain' ||
    attempt.state.kind === 'reconciled'
  );
}

/** A recorded action may only be retried while the row still permits it. */
export function actionEligible(exception: Exception, action: string): boolean {
  if (action === 'resolve' || action === 'defer') return exception.isOpen;
  if (action === 'reopen') return !exception.isOpen;
  return true;
}
