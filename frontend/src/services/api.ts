import type {
  ArtifactDescriptor,
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
  SnapshotComparison,
  TimelineEvent,
  TopicCase,
} from '../types/backend-models';
import { ApiError } from './api-error';

export { ApiError, isNotFound, isUnprocessable } from './api-error';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';
const USE_STATIC_DATA = !API_BASE_URL || API_BASE_URL === '';

// Static fixtures are a development convenience, not a claim that no backend is
// reachable: a missing fixture still falls through to the same-origin /api path.
if (USE_STATIC_DATA && import.meta.env.DEV && import.meta.env.MODE !== 'test') {
  console.warn(
    '[triangulate] VITE_API_BASE_URL is not set; serving bundled static fixtures. ' +
      'Set VITE_API_BASE_URL to the backend origin, or run scripts/dev-with-api.sh, ' +
      'for live case data. A missing fixture falls through to the same-origin /api path.'
  );
}

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
  if (apiPath === '/api/monitoring/summary') {
    return '/data/monitoring/summary.json';
  }
  return apiPath.replace('/api/', '/data/');
}

async function fetchStatic<T>(path: string): Promise<T | null> {
  if (!USE_STATIC_DATA) return null;
  try {
    const response = await fetch(path);
    if (!response.ok) return null;
    return await response.json() as T;
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

/**
 * Frozen readers: the citation and the capture window are addressed by their
 * own immutable IDs, so they accept no snapshot selector. The backend rejects a
 * `snapshot`/`snapshotId` query on both routes with 422, which is why neither
 * fetcher below has a snapshot parameter — the browser's `snapshot` value is
 * never forwarded here. Only the claim/evidence/comparison readers are
 * snapshot-aware.
 */
export const getCitationDetail = async (
  caseId: string,
  citationId: string
): Promise<CitationDetail> =>
  request(
    `/api/cases/${encodeURIComponent(caseId)}/citations/${encodeURIComponent(citationId)}`
  );

/**
 * One bounded code-point window of an immutable capture. `start`/`length` are
 * the only accepted query values: this route is frozen per capture ID and
 * rejects a snapshot selector with 422.
 */
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

/**
 * P01 source dependency summary (GET /api/cases/{case_id}/sources).
 *
 * These are **observed** counts and grouping metadata. Nothing here rates bias,
 * factuality or independence: `independenceStatus` is either `unknown` or
 * `dependency_detected`, never a positive independence verdict.
 */
export interface SourcePolicy {
  version: string;
  urlNormalization: string[];
  publisherIdentity: string[];
  dependencyEdges: string[];
  textFingerprint: string;
  textFingerprintNormalization: string;
  minCopyNonWhitespaceCodePoints: number;
  limitations: string[];
}

/** One evidence/capture record inside a dependency group (no capture body). */
export interface SourceMember {
  evidenceId: string;
  publisher: string | null;
  publisherKey: string | null;
  publisherKeyProvisional: boolean;
  host: string | null;
  originUrl: string | null;
  canonicalUrl: string | null;
  sourceUrl: string | null;
  caseArticleId: string | null;
  explicitOriginKey: string | null;
  captureId: string | null;
  captureKind: string | null;
  captureTextSha256: string | null;
  captureNormalizedTextSha256: string | null;
  captureCharLength: number | null;
  recordedAt: string | null;
  observedAt: string | null;
  copyFingerprint: string | null;
  copyNonWhitespaceCount: number;
  dependencyReasons: string[];
}

/** One connected dependency component, with inspectable membership. */
export interface SourceDependencyGroup {
  id: string;
  reasons: string[];
  publisherKeys: string[];
  evidenceCount: number;
  members: SourceMember[];
}

/** Observed evidence count for one known publisher identity. */
export interface PublisherCount {
  publisherKey: string;
  publisher: string | null;
  evidenceCount: number;
  dependencyGroupCount: number;
  provisional: boolean;
}

/** `GET /api/cases/{case_id}/sources` — never an independence score. */
export interface SourceSummary {
  caseId: string;
  scope: 'case' | 'claim';
  claimId: string | null;
  claimSignature: string | null;
  evidenceCount: number;
  distinctPublisherCount: number;
  dependencyGroupCount: number;
  unknownPublisherCount: number;
  independenceStatus: 'unknown' | 'dependency_detected';
  policy: SourcePolicy;
  publisherCounts: PublisherCount[];
  groups: SourceDependencyGroup[];
}

/**
 * Observed publishers and dependency groups for one case (read-only).
 *
 * The route is current-only and rejects a `snapshot` selector with 422, so this
 * fetcher accepts no snapshot parameter — the browser's `snapshot` value is
 * never forwarded here.
 */
export const getCaseSources = async (
  caseId: string,
  options: { claimId?: string | null } = {}
): Promise<SourceSummary> => {
  const claimId =
    typeof options.claimId === 'string' ? options.claimId.trim() : '';
  const query = claimId ? `?claimId=${encodeURIComponent(claimId)}` : '';
  return request(`/api/cases/${encodeURIComponent(caseId)}/sources${query}`);
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

export interface SnapshotComparisonQuery {
  /** Baseline snapshot id (API query name `baseline`). */
  baseline: string;
  /** Target snapshot id (API query name `target`). */
  target: string;
  limit?: number;
  offset?: number;
}

/**
 * X01 ad-hoc comparison of two pinned snapshots (GET-only, zero writes).
 *
 * Distinct from the recorded-run changes reader: `baseline` and `target` are
 * explicit immutable snapshot ids, never resolved from "latest" here. An
 * unsupported pair answers 200 with `availability: "unavailable"` and a reason,
 * so the caller must never render it as an empty delta.
 */
export const getSnapshotComparison = async (
  caseId: string,
  query: SnapshotComparisonQuery
): Promise<SnapshotComparison> => {
  const params = new URLSearchParams();
  params.set('baseline', query.baseline);
  params.set('target', query.target);
  if (typeof query.limit === 'number') params.set('limit', String(query.limit));
  if (typeof query.offset === 'number') params.set('offset', String(query.offset));
  return request(
    `/api/cases/${encodeURIComponent(caseId)}/snapshot-comparison?${params.toString()}`
  );
};

export const getReportForCase = async (caseId: string): Promise<ReportData> =>
  request(`/api/cases/${caseId}/report`);

// ---------------------------------------------------------------------------
// X02 / F19 published report artifacts of one grouped run (GET-only)
// ---------------------------------------------------------------------------

/**
 * The only artifact types the publication step writes, and therefore the only
 * ones this client will ever offer for download. No PDF, ZIP or bundle type
 * exists here, and nothing below generates, repairs or republishes a report.
 */
export const INVESTIGATION_ARTIFACT_TYPES = [
  'report_markdown',
  'report_json',
  'execution_manifest',
] as const;

/**
 * Descriptors of one recorded grouped run's published report artifacts.
 *
 * An unknown or wrong-case run is a 404 (`isNotFound`), and a recorded run
 * without eligible published reports is `[]`. Neither case is ever resolved to
 * a nearby, newer or "latest" run — that decision belongs to the caller, and
 * the honest answer is to show the recorded state.
 */
export const getInvestigationRunArtifacts = async (
  caseId: string,
  runId: string
): Promise<ArtifactDescriptor[]> =>
  request(
    `/api/cases/${encodeURIComponent(caseId)}/investigation-runs/` +
      `${encodeURIComponent(runId)}/artifacts`
  );

/**
 * Download the bytes of one descriptor through the F19 download URL.
 *
 * The type must be on the allowlist and the descriptor's `downloadUrl` must be
 * exactly the canonical URL for this case, run and artifact id; anything else
 * is refused locally instead of being fetched. A 404 from the reader (missing
 * bytes, wrong owner, unlisted artifact) surfaces as `ApiError` with status
 * 404 and is never retried into a different artifact.
 */
export const downloadInvestigationRunArtifact = async (
  caseId: string,
  runId: string,
  descriptor: ArtifactDescriptor
): Promise<void> => {
  if (!(INVESTIGATION_ARTIFACT_TYPES as readonly string[]).includes(descriptor.type)) {
    throw new Error('This artifact type is not offered for download.');
  }
  const expected =
    `/api/cases/${encodeURIComponent(caseId)}/investigation-runs/` +
    `${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(descriptor.artifactId)}`;
  if (descriptor.downloadUrl !== expected) {
    throw new Error('This download reference does not address the recorded artifact.');
  }
  await downloadBlob(descriptor.downloadUrl, descriptor.displayName);
};

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
    // Keep the HTTP status on the error so a reader can distinguish a missing
    // recorded artifact (404) from a genuine transport failure.
    throw new ApiError(
      detail || `Request failed with status ${response.status}`,
      response.status
    );
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
