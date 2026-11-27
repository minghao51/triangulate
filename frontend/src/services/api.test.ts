import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * These tests pin the shared request implementation in `services/api.ts` with a
 * global fetch stub. No backend, fixture directory or browser network is used:
 * every response below is a deterministic object literal.
 *
 * `API_BASE_URL` / `USE_STATIC_DATA` are captured when the module is evaluated,
 * so mode-switching tests stub the env var, reset the module registry and then
 * dynamically import a fresh copy of the module.
 */

const BASE_URL_ENV = 'VITE_API_BASE_URL';
const LIVE_ORIGIN = 'https://api.example.test';

type FetchMock = ReturnType<typeof vi.fn<typeof fetch>>;

function okResponse(body: unknown, status = 200): Response {
  return {
    ok: true,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
    blob: async () => new Blob([JSON.stringify(body)]),
    headers: new Headers(),
  } as unknown as Response;
}

/** A non-OK response whose body text is exactly what the server sent. */
function errorResponse(rawText: string, status: number): Response {
  return {
    ok: false,
    status,
    json: async () => {
      throw new SyntaxError(`Unexpected token in JSON: ${rawText}`);
    },
    text: async () => rawText,
    blob: async () => new Blob([rawText]),
    headers: new Headers(),
  } as unknown as Response;
}

function installFetch(): FetchMock {
  const fetchMock = vi.fn<typeof fetch>();
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function apiMode(): void {
  vi.stubEnv(BASE_URL_ENV, LIVE_ORIGIN);
}

function staticMode(): void {
  vi.stubEnv(BASE_URL_ENV, '');
}

async function loadApi(): Promise<typeof import('./api')> {
  vi.resetModules();
  return import('./api');
}

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.resetModules();
});

describe('request: API mode success', () => {
  it('returns the decoded JSON body and sends JSON content-type', async () => {
    apiMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse([{ id: 'case-1' }]));
    const api = await loadApi();

    const cases = await api.getCases();

    expect(cases).toEqual([{ id: 'case-1' }]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${LIVE_ORIGIN}/api/cases`);
    expect(init?.headers).toEqual({ 'Content-Type': 'application/json' });
    // Static mode must be skipped entirely when an API origin is configured.
    expect(fetchMock.mock.calls.some(([input]) => String(input).startsWith('/data/'))).toBe(
      false
    );
  });
});

describe('request: API mode failures', () => {
  it('preserves a JSON detail string and status in ApiError', async () => {
    apiMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(
      errorResponse('{"detail":"Case not found"}', 404)
    );
    const api = await loadApi();

    const error: unknown = await api.getCases().catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(api.ApiError);
    expect(error).toMatchObject({
      name: 'ApiError',
      message: 'Case not found',
      status: 404,
    });
  });

  it('keeps a non-JSON error body verbatim', async () => {
    apiMode();
    installFetch().mockResolvedValue(errorResponse('Bad Gateway', 502));
    const api = await loadApi();

    await expect(api.getCases()).rejects.toMatchObject({
      name: 'ApiError',
      message: 'Bad Gateway',
      status: 502,
    });
  });

  it('falls back to a status-derived message for an empty error body', async () => {
    apiMode();
    installFetch().mockResolvedValue(errorResponse('', 503));
    const api = await loadApi();

    await expect(api.getCases()).rejects.toMatchObject({
      name: 'ApiError',
      message: 'Request failed with status 503',
      status: 503,
    });
  });
});

describe('request: mutation methods forward method, body and headers', () => {
  it('submitCaseReviewAction POSTs the decision payload', async () => {
    apiMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse({ id: 'case-1' }));
    const api = await loadApi();

    await api.submitCaseReviewAction('case-1', 'approve', 'looks right');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      `${LIVE_ORIGIN}/api/cases/case-1/review-actions/review`
    );
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe(
      JSON.stringify({ decision: 'approve', notes: 'looks right' })
    );
    expect(init?.headers).toEqual({ 'Content-Type': 'application/json' });
  });

  it('submitExceptionAction POSTs the exception action payload', async () => {
    apiMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse({ id: 'case-1' }));
    const api = await loadApi();

    await api.submitExceptionAction('case-1', 'exc-1', 'resolve', undefined);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      `${LIVE_ORIGIN}/api/cases/case-1/review-actions/exceptions/exc-1`
    );
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe(
      JSON.stringify({ action: 'resolve', notes: undefined })
    );
    expect(init?.headers).toEqual({ 'Content-Type': 'application/json' });
  });

  it('createCaseAnnotation POSTs the annotation payload', async () => {
    apiMode();
    const payload = {
      targetType: 'claim',
      targetId: 'claim-1',
      annotationType: 'note',
      content: 'Worth a second look',
      author: 'reviewer',
      metadata: { source: 'unit-test' },
    };
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse({ id: 'annotation-1' }));
    const api = await loadApi();

    await api.createCaseAnnotation('case-1', payload);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${LIVE_ORIGIN}/api/cases/case-1/annotations`);
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe(JSON.stringify(payload));
    expect(init?.headers).toEqual({ 'Content-Type': 'application/json' });
  });
});

describe('request: download failures', () => {
  it('rejects with the server detail when the download is not OK', async () => {
    apiMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(errorResponse('Report missing', 404));
    const api = await loadApi();

    await expect(api.downloadMarkdownReport('case-1')).rejects.toThrow(
      'Report missing'
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(
      `${LIVE_ORIGIN}/api/cases/case-1/report/markdown`
    );
  });

  it('falls back to the status-derived message for an empty download body', async () => {
    apiMode();
    installFetch().mockResolvedValue(errorResponse('', 500));
    const api = await loadApi();

    await expect(api.downloadManifestReport('case-1')).rejects.toThrow(
      'Request failed with status 500'
    );
  });

  it('skips a missing static download instead of failing', async () => {
    staticMode();
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(errorResponse('not found', 404));
    const api = await loadApi();

    await expect(api.downloadMarkdownReport('case-1')).resolves.toBeUndefined();

    expect(fetchMock.mock.calls[0][0]).toBe('/data/cases/case-1/report/markdown');
    expect(warn).toHaveBeenCalledWith('Static download not available, skipping');
  });
});

describe('request: static mode path mapping', () => {
  it('maps known and unrecognised API paths onto bundled fixtures', async () => {
    staticMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse([]));
    const api = await loadApi();

    await api.getCases();
    await api.getCaseDetail('case-1');
    await api.getClaimsOverviewForCase('case-1');
    await api.getEvidenceForCase('case-1');
    await api.getMonitoringSummary();

    // Explicit mappings append `.json`; only a path with no explicit mapping
    // falls back to the prefix swap that keeps its trailing segment verbatim.
    expect(fetchMock.mock.calls.map(([input]) => input)).toEqual([
      '/data/cases/cases.json',
      '/data/cases/case-1/detail.json',
      '/data/cases/case-1/claims/overview.json',
      '/data/cases/case-1/evidence.json',
      '/data/monitoring/summary.json',
    ]);
    expect(fetchMock.mock.calls.map(([, init]) => init)).toEqual([
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
    ]);
  });

  it('maps the monitoring summary endpoint to its .json fixture', async () => {
    staticMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse({ total_claims: 0 }));
    const api = await loadApi();

    await api.getMonitoringSummary();

    // The generic fallback would yield '/data/monitoring/summary' (no suffix),
    // so this endpoint needs its own explicit mapping like the case paths.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe('/data/monitoring/summary.json');
  });

  it('returns fixture data without a second request', async () => {
    staticMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse([{ id: 'case-1' }]));
    const api = await loadApi();

    await expect(api.getCases()).resolves.toEqual([{ id: 'case-1' }]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('falls through to the same-origin /api path when a fixture is missing', async () => {
    staticMode();
    const fetchMock = installFetch();
    fetchMock
      .mockResolvedValueOnce(errorResponse('not found', 404))
      .mockResolvedValueOnce(okResponse([{ id: 'live-case' }]));
    const api = await loadApi();

    const cases = await api.getCases();

    expect(cases).toEqual([{ id: 'live-case' }]);
    expect(fetchMock.mock.calls.map(([input]) => input)).toEqual([
      '/data/cases/cases.json',
      '/api/cases',
    ]);
    const [, liveInit] = fetchMock.mock.calls[1];
    expect(liveInit?.headers).toEqual({ 'Content-Type': 'application/json' });
  });

  it('falls through to the /api path when the fixture request throws', async () => {
    staticMode();
    const fetchMock = installFetch();
    fetchMock
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValueOnce(okResponse({ summary: 'empty' }));
    const api = await loadApi();

    await expect(api.getMonitoringSummary()).resolves.toEqual({
      summary: 'empty',
    });
    expect(fetchMock.mock.calls.map(([input]) => input)).toEqual([
      '/data/monitoring/summary.json',
      '/api/monitoring/summary',
    ]);
  });

  it('falls through to the /api path when a fixture returns non-JSON HTML', async () => {
    staticMode();
    const fetchMock = installFetch();
    const htmlFallback = {
      ok: true,
      status: 200,
      json: async () => {
        throw new SyntaxError("Unexpected token '<'");
      },
      text: async () => '<!doctype html>',
      blob: async () => new Blob(['<!doctype html>']),
      headers: new Headers(),
    } as unknown as Response;
    fetchMock
      .mockResolvedValueOnce(htmlFallback)
      .mockResolvedValueOnce(okResponse([{ id: 'live-case' }]));
    const api = await loadApi();

    await expect(api.getCases()).resolves.toEqual([{ id: 'live-case' }]);
    expect(fetchMock.mock.calls.map(([input]) => input)).toEqual([
      '/data/cases/cases.json',
      '/api/cases',
    ]);
  });

  it('propagates a live /api failure after a missing fixture', async () => {
    staticMode();
    const fetchMock = installFetch();
    fetchMock
      .mockResolvedValueOnce(errorResponse('not found', 404))
      .mockResolvedValueOnce(errorResponse('{"detail":"Backend down"}', 500));
    const api = await loadApi();

    await expect(api.getCases()).rejects.toMatchObject({
      name: 'ApiError',
      message: 'Backend down',
      status: 500,
    });
  });
});

describe('source summary reader', () => {
  const dto = {
    caseId: 'case-1',
    scope: 'case',
    claimId: null,
    claimSignature: null,
    evidenceCount: 3,
    distinctPublisherCount: 2,
    dependencyGroupCount: 1,
    unknownPublisherCount: 1,
    independenceStatus: 'unknown',
    policy: {
      version: 'source-dependency-policy-v1',
      urlNormalization: [],
      publisherIdentity: [],
      dependencyEdges: [],
      textFingerprint: 'text-fingerprint-v1',
      textFingerprintNormalization: 'nfkc-collapse',
      minCopyNonWhitespaceCodePoints: 200,
      limitations: [],
    },
    publisherCounts: [],
    groups: [],
  };

  it('GETs the case-scoped sources summary unchanged and returns the DTO', async () => {
    apiMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse(dto));
    const api = await loadApi();

    const result = await api.getCaseSources('case-1');

    expect(result).toEqual(dto);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(`${LIVE_ORIGIN}/api/cases/case-1/sources`);
    expect(init?.method).toBeUndefined();
    expect(String(url)).not.toMatch(/snapshot/i);
  });

  it('forwards an optional claim selector and never a snapshot', async () => {
    apiMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse(dto));
    const api = await loadApi();

    await api.getCaseSources('case-1', { claimId: ' claim-1 ' });
    await (api.getCaseSources as unknown as (
      caseId: string,
      options: { claimId?: string; snapshotId?: string }
    ) => Promise<unknown>)('case-1', { snapshotId: 'snap-1' });

    expect(fetchMock.mock.calls.map(([input]) => input)).toEqual([
      `${LIVE_ORIGIN}/api/cases/case-1/sources?claimId=claim-1`,
      `${LIVE_ORIGIN}/api/cases/case-1/sources`,
    ]);
    expect(fetchMock.mock.calls.map(([input]) => String(input)).join(' ')).not.toMatch(
      /snapshot/i
    );
  });
});

describe('frozen readers never forward a snapshot selector', () => {
  /**
   * Contract (§10 / F08): the citation GET and the capture-window GET are frozen
   * by their own immutable IDs and reject `snapshot` with 422, so the browser's
   * `snapshot` value must never reach them. Claim/evidence readers are the only
   * snapshot-aware GETs, and they are asserted below as the positive control.
   */
  type FrozenCitationFn = (
    caseId: string,
    citationId: string,
    snapshotId?: string
  ) => Promise<unknown>;
  type FrozenWindowFn = (
    caseId: string,
    evidenceId: string,
    captureId: string,
    options?: { start?: number; length?: number; snapshotId?: string }
  ) => Promise<unknown>;

  it('citation GET carries no snapshot even when the caller supplies one', async () => {
    apiMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse({ id: 'cit-1' }));
    const api = await loadApi();

    await (api.getCitationDetail as unknown as FrozenCitationFn)(
      'case-1',
      'cit-1',
      'snap-1'
    );

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(`${LIVE_ORIGIN}/api/cases/case-1/citations/cit-1`);
    expect(String(url)).not.toMatch(/snapshot/i);
  });

  it('capture-window GET carries no snapshot even when the options object has one', async () => {
    apiMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse({ text: 'body' }));
    const api = await loadApi();

    await (api.getCaptureWindow as unknown as FrozenWindowFn)(
      'case-1',
      'ev-1',
      'cap-1',
      { start: 5, length: 10, snapshotId: 'snap-1' }
    );

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(
      `${LIVE_ORIGIN}/api/cases/case-1/evidence/ev-1/captures/cap-1?start=5&length=10`
    );
    expect(String(url)).not.toMatch(/snapshot/i);
  });

  it('claim and evidence GETs still forward the snapshot selector', async () => {
    apiMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse({ id: 'claim-1' }));
    const api = await loadApi();

    await api.getClaimDetail('case-1', 'claim-1', 'snap-1');
    await api.getEvidenceDetail('case-1', 'ev-1', 'snap-1');

    expect(fetchMock.mock.calls.map(([input]) => input)).toEqual([
      `${LIVE_ORIGIN}/api/cases/case-1/claims/claim-1?snapshotId=snap-1`,
      `${LIVE_ORIGIN}/api/cases/case-1/evidence/ev-1?snapshotId=snap-1`,
    ]);
  });
});

describe('module side effects', () => {
  it('does not warn about static fixtures while running under test mode', async () => {
    staticMode();
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    installFetch().mockResolvedValue(okResponse([]));

    await loadApi();

    const fixtureWarnings = warn.mock.calls
      .map(([message]) => String(message))
      .filter((message) => message.includes('VITE_API_BASE_URL'));
    expect(fixtureWarnings).toEqual([]);
  });
});

describe('snapshot comparison reader (X01 ad-hoc)', () => {
  /**
   * Contract §12: the ad-hoc comparison takes two explicit immutable snapshot
   * ids as `baseline`/`target`. The browser allowlist names (`baselineSnapshot`,
   * `targetSnapshot`) never reach the API, and nothing here resolves "latest".
   */
  const dto = {
    mode: 'ad_hoc',
    comparisonPolicyVersion: 'snapshot-comparison-policy-v1',
    baselineSnapshotId: 'snap-1',
    targetSnapshotId: 'snap-2',
    baselineRunId: 'run-1',
    targetRunId: 'run-2',
    baselineCoverage: 'complete_requested_scope',
    targetCoverage: 'complete_requested_scope',
    baselineMetadata: {
      sequence: 1,
      createdAt: '2026-03-01T09:00:00Z',
      schemaVersion: 'case-snapshot-v1',
      identityVersion: 'claim-signature-sha256-v1',
      policyVersion: 'case-history-policy-v1',
    },
    targetMetadata: {
      sequence: 2,
      createdAt: '2026-03-04T10:05:00Z',
      schemaVersion: 'case-snapshot-v1',
      identityVersion: 'claim-signature-sha256-v1',
      policyVersion: 'case-history-policy-v1',
    },
    availability: 'ready',
    unavailableReason: null,
    items: [],
    total: 0,
    limit: 25,
    offset: 0,
    hasMore: false,
  };

  it('GETs both pinned snapshots under the baseline/target query names', async () => {
    apiMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse(dto));
    const api = await loadApi();

    const result = await api.getSnapshotComparison('case-1', {
      baseline: 'snap-1',
      target: 'snap-2',
      limit: 25,
      offset: 50,
    });

    expect(result).toEqual(dto);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(
      `${LIVE_ORIGIN}/api/cases/case-1/snapshot-comparison?baseline=snap-1&target=snap-2&limit=25&offset=50`
    );
    expect(init?.method).toBeUndefined();
    const parsed = new URL(String(url));
    expect(parsed.searchParams.get('baseline')).toBe('snap-1');
    expect(parsed.searchParams.get('target')).toBe('snap-2');
    // Browser-only allowlist names are never sent to the API.
    expect(parsed.searchParams.has('baselineSnapshot')).toBe(false);
    expect(parsed.searchParams.has('targetSnapshot')).toBe(false);
    expect(parsed.searchParams.has('mode')).toBe(false);
  });

  it('encodes snapshot ids and omits paging when it is not supplied', async () => {
    apiMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse(dto));
    const api = await loadApi();

    await api.getSnapshotComparison('case/1', {
      baseline: 'snap 1',
      target: 'snap&2',
    });

    const [url] = fetchMock.mock.calls[0];
    const parsed = new URL(String(url));
    expect(parsed.pathname).toBe('/api/cases/case%2F1/snapshot-comparison');
    expect(parsed.searchParams.get('baseline')).toBe('snap 1');
    expect(parsed.searchParams.get('target')).toBe('snap&2');
    expect(parsed.searchParams.has('limit')).toBe(false);
    expect(parsed.searchParams.has('offset')).toBe(false);
  });
});

// F19/X02: one grouped run's published report artifacts. The reader is GET-only,
// serves the three published types and never falls back to another run.
describe('run artifact readers (F19/X02)', () => {
  const descriptor = {
    artifactId: 'artifact-md',
    type: 'report_markdown',
    displayName: 'topic_report.md',
    downloadUrl: '/api/cases/case-1/investigation-runs/run-2/artifacts/artifact-md',
    recordedChecksum: null,
    checksumKind: 'unknown',
  } as const;

  it('GETs the descriptor list for one case and run with encoded identifiers', async () => {
    apiMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse([descriptor]));
    const api = await loadApi();

    const entries = await api.getInvestigationRunArtifacts('case/1', 'run 2');

    expect(entries).toEqual([descriptor]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(
      `${LIVE_ORIGIN}/api/cases/case%2F1/investigation-runs/run%202/artifacts`
    );
    expect(init?.method).toBeUndefined();
  });

  it('surfaces the F19 404 as an ApiError with status 404', async () => {
    apiMode();
    installFetch().mockResolvedValue(
      errorResponse('{"detail":"Artifact not found for this case and run"}', 404)
    );
    const api = await loadApi();
    const { ApiError, isNotFound } = await import('./api-error');

    await expect(api.getInvestigationRunArtifacts('case-1', 'run-x')).rejects.toThrow(
      'Artifact not found for this case and run'
    );
    const failure = await api
      .getInvestigationRunArtifacts('case-1', 'run-x')
      .then(() => null)
      .catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(isNotFound(failure)).toBe(true);
  });

  it('downloads exactly the descriptor downloadUrl for an allowlisted artifact', async () => {
    apiMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse('stored report bytes'));
    const api = await loadApi();

    await api.downloadInvestigationRunArtifact('case-1', 'run-2', descriptor);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(`${LIVE_ORIGIN}${descriptor.downloadUrl}`);
    expect(fetchMock.mock.calls[0][1]).toBeUndefined();
  });

  it('keeps the 404 status on a failed artifact download so the UI can distinguish it', async () => {
    apiMode();
    installFetch().mockResolvedValue(
      errorResponse('{"detail":"Artifact bytes are not available"}', 404)
    );
    const api = await loadApi();
    const { ApiError, isNotFound } = await import('./api-error');

    const failure = await api
      .downloadInvestigationRunArtifact('case-1', 'run-2', descriptor)
      .then(() => null)
      .catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect(isNotFound(failure)).toBe(true);
  });

  it('refuses a non-allowlisted type and a foreign download URL without fetching', async () => {
    apiMode();
    const fetchMock = installFetch();
    fetchMock.mockResolvedValue(okResponse('bytes'));
    const api = await loadApi();

    await expect(
      api.downloadInvestigationRunArtifact('case-1', 'run-2', {
        ...descriptor,
        type: 'report_pdf' as never,
      })
    ).rejects.toThrow('This artifact type is not offered for download.');

    // A descriptor that points at another run, case or host is never fetched.
    await expect(
      api.downloadInvestigationRunArtifact('case-1', 'run-2', {
        ...descriptor,
        downloadUrl: '/api/cases/case-1/investigation-runs/run-9/artifacts/artifact-md',
      })
    ).rejects.toThrow('This download reference does not address the recorded artifact.');

    await expect(
      api.downloadInvestigationRunArtifact('case-1', 'run-2', {
        ...descriptor,
        downloadUrl: 'https://evil.example/artifact-md',
      })
    ).rejects.toThrow('This download reference does not address the recorded artifact.');

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('offers only the three published artifact types', async () => {
    const api = await loadApi();
    expect([...api.INVESTIGATION_ARTIFACT_TYPES]).toEqual([
      'report_markdown',
      'report_json',
      'execution_manifest',
    ]);
  });
});
