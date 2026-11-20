import type {
  CaseDetail,
  CaseSearchResponse,
  CaptureWindow,
  CitationDetail,
  Claim,
  ClaimDetail,
  Comparison,
  ClaimsOverview,
  Evidence,
  EvidenceDetail,
  EvaluationSummary,
  Exception,
  MonitoringSummary,
  Party,
  ReportData,
  ReviewActivity,
  ReviewAnnotation,
  InvestigationRun,
  InvestigationRunList,
  RunChanges,
  RunHistoryItem,
  TimelineEvent,
  TopicCase,
} from '../types/backend-models';
import { ApiError } from './api-error';

export { ApiError, isNotFound, isUnprocessable } from './api-error';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';
const USE_STATIC_DATA = !API_BASE_URL || API_BASE_URL === '';

function mapStaticPath(apiPath: string): string {
  if (apiPath === '/api/cases') {
    return '/data/cases/cases.json';
  }
  const caseMatch = apiPath.match(/^\/api\/cases\/([^/]+)$/);
  if (caseMatch) {
    return `/data/cases/${caseMatch[1]}/detail.json`;
  }
  const claimsOverviewMatch = apiPath.match(/^\/api\/cases\/([^/]+)\/claims\/overview$/);
  if (claimsOverviewMatch) {
    return `/data/cases/${claimsOverviewMatch[1]}/claims/overview.json`;
  }
  const tabMatch = apiPath.match(/^\/api\/cases\/([^/]+)\/([^/]+)$/);
  if (tabMatch) {
    return `/data/cases/${tabMatch[1]}/${tabMatch[2]}.json`;
  }
  return apiPath.replace('/api/', '/data/');
}

async function fetchStatic<T>(path: string): Promise<T | null> {
  if (!USE_STATIC_DATA) return null;
  try {
    const response = await fetch(path);
    if (!response.ok) return null;
    return response.json() as Promise<T>;
  } catch {
    return null;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (USE_STATIC_DATA) {
    const staticPath = mapStaticPath(path);
    const staticData = await fetchStatic<T>(staticPath);
    if (staticData !== null) {
      return staticData;
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const rawDetail = await response.text();
    let detail = rawDetail;
    try {
      const parsed = JSON.parse(rawDetail) as { detail?: unknown };
      if (typeof parsed?.detail === 'string') detail = parsed.detail;
    } catch {
      // Non-JSON error bodies keep their raw text.
    }
    throw new ApiError(detail || `Request failed with status ${response.status}`, response.status);
  }

  return response.json() as Promise<T>;
}

export const getCases = async (): Promise<TopicCase[]> => request('/api/cases');

export const getCaseDetail = async (caseId: string): Promise<CaseDetail> =>
  request(`/api/cases/${caseId}`);

export const getClaimsOverviewForCase = async (caseId: string): Promise<ClaimsOverview> =>
  request(`/api/cases/${caseId}/claims/overview`);

export const getClaimsForCase = async (caseId: string): Promise<Claim[]> =>
  (await getClaimsOverviewForCase(caseId)).claims;

export const getEvidenceForCase = async (caseId: string): Promise<Evidence[]> =>
  request(`/api/cases/${caseId}/evidence`);

export interface CaseSearchQuery {
  q: string;
  type?: 'claim' | 'evidence' | null;
  publisher?: string | null;
  status?: string | null;
  publishedFrom?: string | null;
  publishedTo?: string | null;
  limit?: number;
  offset?: number;
}

/** Case-scoped lexical search; this reader issues GET only. */
export const getCaseSearch = async (
  caseId: string,
  query: CaseSearchQuery
): Promise<CaseSearchResponse> => {
  const params = new URLSearchParams();
  params.set('q', query.q);
  for (const key of ['type', 'publisher', 'status', 'publishedFrom', 'publishedTo'] as const) {
    const value = query[key];
    if (typeof value === 'string' && value.trim()) params.set(key, value.trim());
  }
  if (typeof query.limit === 'number') params.set('limit', String(query.limit));
  if (typeof query.offset === 'number') params.set('offset', String(query.offset));
  return request(
    `/api/cases/${encodeURIComponent(caseId)}/search?${params.toString()}`
  );
};

/** E03 inspector readers (GET-only). */
function snapshotQuery(snapshotId?: string | null): string {
  return snapshotId ? `?snapshotId=${encodeURIComponent(snapshotId)}` : '';
}

export const getClaimDetail = async (
  caseId: string,
  claimId: string,
  snapshotId?: string | null
): Promise<ClaimDetail> =>
  request(
    `/api/cases/${encodeURIComponent(caseId)}/claims/${encodeURIComponent(claimId)}` +
      snapshotQuery(snapshotId)
  );

export const getEvidenceDetail = async (
  caseId: string,
  evidenceId: string,
  snapshotId?: string | null
): Promise<EvidenceDetail> =>
  request(
    `/api/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(evidenceId)}` +
      snapshotQuery(snapshotId)
  );

export const getCitationDetail = async (
  caseId: string,
  citationId: string
): Promise<CitationDetail> =>
  request(
    `/api/cases/${encodeURIComponent(caseId)}/citations/${encodeURIComponent(citationId)}`
  );

/** One bounded code-point window of an immutable capture. */
export const getCaptureWindow = async (
  caseId: string,
  evidenceId: string,
  captureId: string,
  options: { start?: number; length?: number } = {}
): Promise<CaptureWindow> => {
  const params = new URLSearchParams();
  if (typeof options.start === 'number') params.set('start', String(options.start));
  if (typeof options.length === 'number') params.set('length', String(options.length));
  const query = params.toString();
  return request(
    `/api/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(
      evidenceId
    )}/captures/${encodeURIComponent(captureId)}${query ? `?${query}` : ''}`
  );
};

export interface ComparisonQuery {
  left: string;
  right: string;
  leftCapture?: string | null;
  rightCapture?: string | null;
  limit?: number;
  offset?: number;
}

/** P02 deterministic two-capture comparison (GET-only). */
export const getComparison = async (
  caseId: string,
  query: ComparisonQuery
): Promise<Comparison> => {
  const params = new URLSearchParams();
  params.set('left', query.left);
  params.set('right', query.right);
  if (query.leftCapture) params.set('leftCapture', query.leftCapture);
  if (query.rightCapture) params.set('rightCapture', query.rightCapture);
  if (typeof query.limit === 'number') params.set('limit', String(query.limit));
  if (typeof query.offset === 'number') params.set('offset', String(query.offset));
  return request(
    `/api/cases/${encodeURIComponent(caseId)}/comparison?${params.toString()}`
  );
};

export const getExceptionsForCase = async (caseId: string): Promise<Exception[]> =>
  request(`/api/cases/${caseId}/exceptions`);

export const getPartiesForCase = async (caseId: string): Promise<Party[]> =>
  request(`/api/cases/${caseId}/parties`);

export const getTimelineForCase = async (caseId: string): Promise<TimelineEvent[]> =>
  request(`/api/cases/${caseId}/timeline`);

export const getRunHistoryForCase = async (caseId: string): Promise<RunHistoryItem[]> =>
  request(`/api/cases/${caseId}/run-history`);

export interface RunQuery {
  limit?: number;
  offset?: number;
}

function runQueryString(query: RunQuery = {}): string {
  const params = new URLSearchParams();
  if (typeof query.limit === 'number') params.set('limit', String(query.limit));
  if (typeof query.offset === 'number') params.set('offset', String(query.offset));
  const rendered = params.toString();
  return rendered ? `?${rendered}` : '';
}

/** R04 grouped invocations, newest sequence first (distinct from stage history). */
export const getInvestigationRuns = async (
  caseId: string,
  query: RunQuery = {}
): Promise<InvestigationRunList> =>
  request(
    `/api/cases/${encodeURIComponent(caseId)}/investigation-runs${runQueryString(query)}`
  );

export const getInvestigationRun = async (
  caseId: string,
  runId: string
): Promise<InvestigationRun> =>
  request(
    `/api/cases/${encodeURIComponent(caseId)}/investigation-runs/${encodeURIComponent(runId)}`
  );

/** R04 typed changes for one run; pending/unavailable are not empty deltas. */
export const getRunChanges = async (
  caseId: string,
  runId: string,
  query: RunQuery = {}
): Promise<RunChanges> =>
  request(
    `/api/cases/${encodeURIComponent(caseId)}/investigation-runs/` +
      `${encodeURIComponent(runId)}/changes${runQueryString(query)}`
  );

export const getReportForCase = async (caseId: string): Promise<ReportData> =>
  request(`/api/cases/${caseId}/report`);

export const getReviewActivityForCase = async (caseId: string): Promise<ReviewActivity> =>
  request(`/api/cases/${caseId}/review-activity`);

export const submitCaseReviewAction = async (
  caseId: string,
  decision: string,
  notes?: string
): Promise<TopicCase> =>
  request(`/api/cases/${caseId}/review-actions/review`, {
    method: 'POST',
    body: JSON.stringify({ decision, notes }),
  });

export const submitExceptionAction = async (
  caseId: string,
  exceptionId: string,
  action: string,
  notes?: string
): Promise<TopicCase> =>
  request(`/api/cases/${caseId}/review-actions/exceptions/${exceptionId}`, {
    method: 'POST',
    body: JSON.stringify({ action, notes }),
  });

export const createCaseAnnotation = async (
  caseId: string,
  payload: {
    targetType: string;
    targetId: string;
    annotationType: string;
    content: string;
    author?: string;
    metadata?: Record<string, unknown>;
  }
): Promise<ReviewAnnotation> =>
  request(`/api/cases/${caseId}/annotations`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const getEvaluationForCase = async (caseId: string): Promise<EvaluationSummary> =>
  request(`/api/cases/${caseId}/evaluation`);

export const getMonitoringSummary = async (): Promise<MonitoringSummary> =>
  request('/api/monitoring/summary');

async function downloadBlob(path: string, fallbackName: string): Promise<void> {
  if (USE_STATIC_DATA) {
    const staticPath = mapStaticPath(path);
    try {
      const response = await fetch(staticPath);
      if (!response.ok) throw new Error('Static file not found');
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = fallbackName;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
      return;
    } catch {
      console.warn('Static download not available, skipping');
      return;
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with status ${response.status}`);
  }

  const blob = await response.blob();
  const contentDisposition = response.headers.get('Content-Disposition') ?? '';
  const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
  const filename = filenameMatch?.[1] ?? fallbackName;
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

export const downloadMarkdownReport = async (caseId: string): Promise<void> =>
  downloadBlob(`/api/cases/${caseId}/report/markdown`, `${caseId}.md`);

export const downloadManifestReport = async (caseId: string): Promise<void> =>
  downloadBlob(`/api/cases/${caseId}/report/manifest`, `${caseId}-manifest.json`);
