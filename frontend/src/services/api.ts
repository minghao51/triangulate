import type {
  CaseDetail,
  Claim,
  ClaimsOverview,
  Evidence,
  Exception,
  Party,
  ReportData,
  RunHistoryItem,
  TimelineEvent,
  TopicCase,
} from '../types/backend-models';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with status ${response.status}`);
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

async function downloadBlob(path: string, fallbackName: string): Promise<void> {
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
