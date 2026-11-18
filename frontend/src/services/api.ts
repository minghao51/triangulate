import type {
  CaseDetail,
  CaptureWindow,
  CitationDetail,
  Claim,
  ClaimDetail,
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

/** E03 inspector readers (GET-only). */
export const getClaimDetail = async (
  caseId: string,
  claimId: string
): Promise<ClaimDetail> =>
  request(`/api/cases/${encodeURIComponent(caseId)}/claims/${encodeURIComponent(claimId)}`);

export const getEvidenceDetail = async (
  caseId: string,
  evidenceId: string
): Promise<EvidenceDetail> =>
  request(
    `/api/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(evidenceId)}`
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

export const getExceptionsForCase = async (caseId: string): Promise<Exception[]> =>
  request(`/api/cases/${caseId}/exceptions`);

export const getPartiesForCase = async (caseId: string): Promise<Party[]> =>
  request(`/api/cases/${caseId}/parties`);

export const getTimelineForCase = async (caseId: string): Promise<TimelineEvent[]> =>
  request(`/api/cases/${caseId}/timeline`);

export const getRunHistoryForCase = async (caseId: string): Promise<RunHistoryItem[]> =>
  request(`/api/cases/${caseId}/run-history`);

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
