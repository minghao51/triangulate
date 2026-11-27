import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import CompareTab from './CompareTab';
import { ApiError } from '../../services/api-error';
import {
  addToComparisonTray,
  getComparisonTray,
  resetComparisonTray,
} from '../../services/comparison-tray';
import type {
  CaptureSummary,
  Comparison,
  ComparisonClaimSide,
  ComparisonPassage,
  ComparisonRow,
  ComparisonSide,
  Evidence,
  EvidenceDetail,
} from '../../types/backend-models';

afterEach(cleanup);

const apiMocks = vi.hoisted(() => ({
  getEvidenceForCase: vi.fn(),
  getEvidenceDetail: vi.fn(),
  getComparison: vi.fn(),
  // Frozen readers (owned by F08) are present in the real module; this surface
  // must never call them, and never with a snapshot selector.
  getCitationDetail: vi.fn(),
  getCaptureWindow: vi.fn(),
}));

vi.mock('../../services/api', () => apiMocks);

const evidenceItem = (overrides: Partial<Evidence> = {}): Evidence => ({
  id: 'ev-left',
  title: 'Left source',
  originUrl: 'https://left.example.com/story',
  canonicalUrl: 'https://left.example.com/story',
  publisher: 'Meridian Wire',
  sourceType: 'rss',
  verificationStatus: 'unknown',
  credibilityTier: null,
  requiresHumanReview: false,
  currentCaptureId: 'cap-left',
  linkedClaims: [],
  verificationChecks: [],
  ...overrides,
});

const capture = (overrides: Partial<CaptureSummary> = {}): CaptureSummary => ({
  id: 'cap-left',
  evidenceId: 'ev-left',
  textSha256: 'sha-left',
  normalizedTextSha256: 'nsha-left',
  normalizationVersion: 'v1',
  captureKind: 'live',
  recordedAt: '2026-03-03T06:30:00Z',
  observedAt: '2026-03-03T06:25:00Z',
  metadata: {},
  charLength: 500,
  isCurrent: true,
  ...overrides,
});

const evidenceDetail = (overrides: Partial<EvidenceDetail> = {}): EvidenceDetail => ({
  id: 'ev-left',
  eventId: null,
  caseArticleId: null,
  evidenceType: 'article',
  sourceType: 'rss',
  title: 'Left source',
  publisher: 'Meridian Wire',
  originUrl: 'https://left.example.com/story',
  canonicalUrl: 'https://left.example.com/story',
  publishedAt: '2026-03-03T06:25:00Z',
  verificationStatus: 'unknown',
  credibilityTier: null,
  requiresHumanReview: false,
  captureMetadata: {},
  currentCaptureId: 'cap-left',
  captures: [capture()],
  relatedClaims: [],
  ...overrides,
});

const passage = (overrides: Partial<ComparisonPassage> = {}): ComparisonPassage => ({
  claimId: 'claim-shared',
  claimText: 'Shared claim text',
  claimSignature: 'sig-shared',
  linkId: 'link-shared-left',
  citationId: null,
  captureId: 'cap-left',
  relationship: 'reported_by',
  rawRelation: 'reported_by',
  alignmentStatus: 'exact',
  quote: 'shared quote',
  startChar: 10,
  endChar: 22,
  assessmentOrigin: 'collector',
  assessmentVersion: 'v1',
  diagnosticReason: null,
  ...overrides,
});

const claimSide = (overrides: Partial<ComparisonClaimSide> = {}): ComparisonClaimSide => ({
  claimIds: ['claim-shared'],
  claimId: 'claim-shared',
  claimText: 'Shared claim text',
  claimSignature: 'sig-shared',
  passages: [passage()],
  ...overrides,
});

const side = (overrides: Partial<ComparisonSide> = {}): ComparisonSide => ({
  evidenceId: 'ev-left',
  captureId: 'cap-left',
  title: 'Left source',
  publisher: 'Meridian Wire',
  originUrl: 'https://left.example.com/story',
  canonicalUrl: 'https://left.example.com/story',
  publishedAt: '2026-03-03T06:25:00Z',
  sourceType: 'rss',
  verificationStatus: 'unknown',
  captureKind: 'live',
  recordedAt: '2026-03-03T06:30:00Z',
  observedAt: '2026-03-03T06:25:00Z',
  textSha256: 'sha-left',
  charLength: 500,
  analysisScope: {
    status: 'valid',
    startChar: 0,
    endChar: 200,
    bodyCharCount: 500,
    inputLimit: 20000,
    sourceAvailable: true,
    reason: null,
  },
  publisherKey: 'meridian-wire',
  publisherKeyProvisional: false,
  host: 'left.example.com',
  sourceUrl: 'https://left.example.com/story',
  copyFingerprint: 'copy-left',
  copyNonWhitespaceCount: 400,
  coverage: {
    linkedClaimCount: 3,
    attributedClaimCount: 3,
    attributedLinkCount: 3,
    otherCaptureLinkCount: 0,
    unattributedLinkCount: 0,
    claimLinkageStatus: 'available',
    historicalAnalysisAvailable: true,
    caveat: null,
  },
  ...overrides,
});

const row = (overrides: Partial<ComparisonRow> = {}): ComparisonRow => ({
  claimSignature: 'sig-shared',
  claimText: 'Shared claim text',
  status: 'shared',
  left: claimSide(),
  right: claimSide({
    claimIds: ['claim-shared'],
    passages: [passage({ linkId: 'link-shared-right', captureId: 'cap-right' })],
  }),
  contradiction: {
    explicit: false,
    conflict: false,
    leftRelationships: ['reported_by'],
    rightRelationships: ['reported_by'],
    reason: 'No explicitly assessed contradiction.',
  },
  caveat: null,
  ...overrides,
});

const comparison = (overrides: Partial<Comparison> = {}): Comparison => ({
  caseId: 'case-1',
  left: side(),
  right: side({
    evidenceId: 'ev-right',
    captureId: 'cap-right',
    title: 'Right source',
    publisher: 'Northern Post',
    originUrl: 'javascript:alert(1)',
    canonicalUrl: 'https://right.example.com/story',
    publisherKey: 'northern.example.com',
    publisherKeyProvisional: true,
    host: 'northern.example.com',
    sourceUrl: 'https://northern.example.com/story',
    copyFingerprint: 'copy-left',
  }),
  leftCaptureId: 'cap-left',
  rightCaptureId: 'cap-right',
  dependency: {
    detected: true,
    copyDetected: true,
    reasons: ['identical_normalized_capture'],
    leftPublisherKey: 'meridian-wire',
    rightPublisherKey: 'northern.example.com',
    message: 'These records share a detected dependency. They are not independent evidence.',
  },
  claims: {
    rows: [
      row(),
      row({
        claimSignature: 'sig-left',
        claimText: 'Left only claim',
        status: 'left_only',
        right: null,
        caveat: 'Extracted from one side only.',
      }),
      row({
        claimSignature: 'sig-right',
        claimText: 'Right only claim',
        status: 'right_only',
        left: null,
        caveat: 'Extracted from one side only.',
      }),
    ],
    total: 3,
    limit: 25,
    offset: 0,
    hasMore: false,
  },
  policy: {
    version: 'comparison-read-policy-v1',
    claimIdentity: 'exact claim_signature',
    alignment: 'persisted capture-linked assessments',
    dependencyPolicy: 'source-dependency-policy-v1',
    limitations: ['Paraphrases are not merged.'],
  },
  caveats: ['One-sided rows describe extraction coverage, not source behavior.'],
  ...overrides,
});

const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
};

function renderCompare(entry = '/cases/case-1/compare', caseId = 'case-1') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route
            path="/cases/:id/compare"
            element={
              <>
                <LocationProbe />
                <CompareTab caseId={caseId} />
              </>
            }
          />
          <Route path="/cases/:id/evidence" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  resetComparisonTray();
  apiMocks.getEvidenceForCase.mockResolvedValue([
    evidenceItem(),
    evidenceItem({
      id: 'ev-right',
      title: 'Right source',
      publisher: 'Northern Post',
      originUrl: 'https://right.example.com/story',
      currentCaptureId: 'cap-right',
    }),
  ]);
  apiMocks.getEvidenceDetail.mockImplementation((_caseId: string, evidenceId: string) =>
    Promise.resolve(
      evidenceDetail({
        id: evidenceId,
        title: evidenceId === 'ev-right' ? 'Right source' : 'Left source',
        currentCaptureId: evidenceId === 'ev-right' ? 'cap-right' : 'cap-left',
        captures: [
          capture({
            id: evidenceId === 'ev-right' ? 'cap-right' : 'cap-left',
            evidenceId,
          }),
        ],
      })
    )
  );
  apiMocks.getComparison.mockResolvedValue(comparison());
});

describe('CompareTab source selection', () => {
  it('shows the selection prompt before two sources are chosen', async () => {
    renderCompare();
    expect(await screen.findByRole('heading', { name: /Compare sources/ })).toBeDefined();
    expect(screen.getByRole('combobox', { name: 'Left source' })).toBeDefined();
    expect(screen.getByRole('combobox', { name: 'Right source' })).toBeDefined();
    expect(
      screen.getByText(/Choose a left and a right source to compare/)
    ).toBeDefined();
    expect(apiMocks.getComparison).not.toHaveBeenCalled();
  });

  it('selects two sources, pins default captures in the URL and renders the alignment', async () => {
    renderCompare();
    await waitFor(() =>
      expect(
        screen.getByRole('combobox', { name: 'Left source' }).querySelectorAll('option').length
      ).toBeGreaterThan(1)
    );

    fireEvent.change(screen.getByRole('combobox', { name: 'Left source' }), {
      target: { value: 'ev-left' },
    });
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain('left=ev-left')
    );
    fireEvent.change(screen.getByRole('combobox', { name: 'Right source' }), {
      target: { value: 'ev-right' },
    });

    expect(await screen.findByText('Shared claim text')).toBeDefined();
    expect(screen.getByText('Left only claim')).toBeDefined();
    expect(screen.getByText('Right only claim')).toBeDefined();
    expect(screen.getByText('Reported in both extractions')).toBeDefined();
    expect(screen.getByText('Extracted only on the left')).toBeDefined();
    expect(screen.getByText('Extracted only on the right')).toBeDefined();
    expect(screen.getByText(/Dependency detected/)).toBeDefined();
    expect(screen.getByText(/Identical long captured text/)).toBeDefined();
    expect(screen.getByText(/not independent evidence/)).toBeDefined();
    expect(screen.getByText(/Extraction coverage, not source behavior/i)).toBeDefined();
    expect(screen.getAllByText(/code points 0–200/).length).toBeGreaterThan(0);

    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain(
        'left=ev-left&right=ev-right&leftCapture=cap-left&rightCapture=cap-right'
      )
    );
    expect(apiMocks.getComparison).toHaveBeenCalledWith(
      'case-1',
      expect.objectContaining({ left: 'ev-left', right: 'ev-right' })
    );
  });

  it('shows an explicit contradiction and does not turn reporting into support', async () => {
    const contradiction = row({
      claimSignature: 'sig-contra',
      claimText: 'Contradicted claim',
      contradiction: {
        explicit: true,
        conflict: true,
        leftRelationships: ['contradicts'],
        rightRelationships: ['reported_by'],
        reason: 'One side explicitly contradicts the claim while the other reports it.',
      },
    });
    apiMocks.getComparison.mockResolvedValue(
      comparison({
        claims: {
          rows: [contradiction],
          total: 1,
          limit: 25,
          offset: 0,
          hasMore: false,
        },
      })
    );
    renderCompare('/cases/case-1/compare?left=ev-left&right=ev-right');

    expect(await screen.findByText('Contradicted claim')).toBeDefined();
    expect(screen.getByText('Explicitly assessed contradiction')).toBeDefined();
    expect(
      screen.getAllByText('Reported by the source (not corroboration)').length
    ).toBeGreaterThan(0);
    expect(screen.queryByText('Confirmed')).toBeNull();
  });
});

describe('CompareTab capture and URL states', () => {
  it('keeps a pinned older capture and shows historical unavailability', async () => {
    apiMocks.getComparison.mockResolvedValue(
      comparison({
        right: side({
          evidenceId: 'ev-old',
          captureId: 'cap-old',
          title: 'Old source',
          coverage: {
            linkedClaimCount: 2,
            attributedClaimCount: 0,
            attributedLinkCount: 0,
            otherCaptureLinkCount: 1,
            unattributedLinkCount: 0,
            claimLinkageStatus: 'historical_unavailable',
            historicalAnalysisAvailable: false,
            caveat:
              'No persisted claim links for this capture version; historical comparison analysis is unavailable. Current links are not substituted.',
          },
        }),
        rightCaptureId: 'cap-old',
      })
    );
    renderCompare(
      '/cases/case-1/compare?left=ev-left&right=ev-old&rightCapture=cap-old'
    );

    expect(await screen.findByText(/Historical claim alignment unavailable/)).toBeDefined();
    expect(screen.getByText(/Current links are not substituted/)).toBeDefined();
    expect(screen.getByRole('combobox', { name: 'Right capture' })).toHaveProperty(
      'value',
      'cap-old'
    );
    expect(screen.getByTestId('location').textContent).toContain('rightCapture=cap-old');
  });

  it('pages with the offset in the URL', async () => {
    apiMocks.getComparison.mockImplementation(
      (_caseId: string, query: { offset?: number }) =>
        Promise.resolve(
          comparison({
            claims: {
              rows: [row({ claimSignature: `sig-${query.offset ?? 0}` })],
              total: 30,
              limit: 25,
              offset: query.offset ?? 0,
              hasMore: (query.offset ?? 0) === 0,
            },
          })
        )
    );
    renderCompare(
      '/cases/case-1/compare?left=ev-left&right=ev-right&leftCapture=cap-left&rightCapture=cap-right'
    );

    expect(await screen.findByText(/Showing 1–1 of 30/)).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /Next/ }));
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain('offset=25')
    );
    expect(apiMocks.getComparison).toHaveBeenLastCalledWith(
      'case-1',
      expect.objectContaining({ offset: 25 })
    );
  });

  it('rejects the same evidence selected on both sides without querying', async () => {
    renderCompare('/cases/case-1/compare?left=ev-left&right=ev-left');
    expect(await screen.findByText('Choose two different sources.')).toBeDefined();
    expect(apiMocks.getComparison).not.toHaveBeenCalled();
  });
});

describe('CompareTab errors, safety and keyboard focus', () => {
  it('distinguishes a missing comparison from a retryable error', async () => {
    apiMocks.getComparison.mockRejectedValueOnce(new ApiError('missing', 404));
    renderCompare('/cases/case-1/compare?left=ev-left&right=ev-right');
    expect(await screen.findByText('Comparison unavailable.')).toBeDefined();
    expect(screen.queryByRole('button', { name: /Retry/ })).toBeNull();
    expect(screen.getByRole('button', { name: 'Clear selection' })).toBeDefined();
  });

  it('retries a network error and then renders results', async () => {
    apiMocks.getComparison
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce(comparison());
    renderCompare('/cases/case-1/compare?left=ev-left&right=ev-right');

    expect(await screen.findByText(/network down/)).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /Retry/ }));
    expect(await screen.findByText('Shared claim text')).toBeDefined();
  });

  it('never links unsafe URLs and keeps safe links noopener', async () => {
    const { container } = renderCompare(
      '/cases/case-1/compare?left=ev-left&right=ev-right'
    );
    await screen.findByText('Shared claim text');
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    const safe = container.querySelector(
      'a[href="https://right.example.com/story"]'
    );
    expect(safe).not.toBeNull();
    expect(safe?.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('focuses the results heading and exposes native controls', async () => {
    renderCompare('/cases/case-1/compare?left=ev-left&right=ev-right');
    const heading = await screen.findByRole('heading', {
      name: 'Comparison results',
    });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(screen.getByRole('combobox', { name: 'Left source' }).tagName).toBe('SELECT');
    expect(screen.getByRole('button', { name: /Compare selected/ }).tagName).toBe(
      'BUTTON'
    );
  });
});

describe('CompareTab same-evidence refusal and frozen readers', () => {
  it('refuses the same evidence even when both sides pin different captures', async () => {
    renderCompare(
      '/cases/case-1/compare?left=ev-left&right=ev-left&leftCapture=cap-left&rightCapture=cap-old'
    );

    const state = await screen.findByText('Choose two different sources.');
    expect(state).toBeDefined();
    expect(apiMocks.getComparison).not.toHaveBeenCalled();
    expect(screen.queryByRole('heading', { name: 'Comparison results' })).toBeNull();
    const alert = document.querySelector('[data-state="comparison-same-source"]');
    expect(alert?.getAttribute('role')).toBe('alert');
    expect(alert?.textContent).toContain('Differing capture versions of one source belong in capture history');
    expect(screen.getByRole('button', { name: /Compare selected/ })).toHaveProperty(
      'disabled',
      true
    );
  });

  it('refuses a repeated evidence item in the tray even with another capture id', async () => {
    addToComparisonTray('case-1', 'current', { evidenceId: 'ev-left', captureId: 'cap-left' });
    const duplicate = addToComparisonTray('case-1', 'current', {
      evidenceId: 'ev-left',
      captureId: 'cap-old',
    });
    expect(duplicate.ok).toBe(false);
    expect(duplicate.reason).toBe('duplicate-evidence');

    renderCompare();
    const refusal = await screen.findByRole('alert');
    expect(refusal.textContent).toContain('cannot be compared with itself');
    expect(refusal.getAttribute('data-state')).toBe('comparison-tray-refused');
    expect(getComparisonTray('case-1', 'current').entries).toHaveLength(1);
    expect(apiMocks.getComparison).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /Compare draft/ })).toHaveProperty(
      'disabled',
      true
    );
  });

  it('keeps historical unavailability and the dependency warning as distinct states', async () => {
    apiMocks.getComparison.mockResolvedValue(
      comparison({
        right: side({
          evidenceId: 'ev-old',
          captureId: 'cap-old',
          coverage: {
            linkedClaimCount: 2,
            attributedClaimCount: 0,
            attributedLinkCount: 0,
            otherCaptureLinkCount: 1,
            unattributedLinkCount: 0,
            claimLinkageStatus: 'historical_unavailable',
            historicalAnalysisAvailable: false,
            caveat: 'Historical claim alignment is unavailable for this capture.',
          },
        }),
        rightCaptureId: 'cap-old',
      })
    );
    renderCompare(
      '/cases/case-1/compare?left=ev-left&right=ev-old&rightCapture=cap-old'
    );

    expect(await screen.findByText('Shared claim text')).toBeDefined();
    const historical = document.querySelector(
      '[data-state="comparison-historical-unavailable"]'
    );
    const dependency = document.querySelector(
      '[data-state="comparison-dependency-warning"]'
    );
    expect(historical).not.toBeNull();
    expect(dependency).not.toBeNull();
    expect(historical).not.toBe(dependency);
    expect(historical?.textContent).toMatch(/historical claim alignment is not available/i);
    expect(dependency?.textContent).toMatch(/Dependency detected/);
    expect(dependency?.textContent).not.toMatch(
      /Absence of a detected dependency does not prove independence/i
    );
  });

  it('never forwards the browser snapshot selector to citation or capture readers', async () => {
    renderCompare(
      '/cases/case-1/compare?snapshot=snap-1&left=ev-left&right=ev-right&leftCapture=cap-left&rightCapture=cap-right'
    );
    await screen.findByText('Shared claim text');

    // Frozen readers are never called from Compare, so no 422 can be provoked.
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
    expect(apiMocks.getCaptureWindow).not.toHaveBeenCalled();

    // And no call made by this surface carries a snapshot selector at all.
    const allCalls = [
      ...apiMocks.getComparison.mock.calls,
      ...apiMocks.getEvidenceDetail.mock.calls,
      ...apiMocks.getEvidenceForCase.mock.calls,
    ];
    expect(allCalls.length).toBeGreaterThan(0);
    allCalls.forEach((call) => {
      expect(JSON.stringify(call)).not.toMatch(/snapshot/i);
    });
  });
});

describe('CompareTab comparison tray draft', () => {
  it('commits the draft through buildComparisonUrl and pins the resolved captures', async () => {
    addToComparisonTray('case-1', 'current', { evidenceId: 'ev-left', captureId: null });
    addToComparisonTray('case-1', 'current', { evidenceId: 'ev-right', captureId: null });
    renderCompare();

    expect(await screen.findByText(/Comparison draft \(2 of 2\)/)).toBeDefined();
    // No capture was pinned in the draft, so the commit URL carries only the ids.
    fireEvent.click(screen.getByRole('button', { name: /Compare draft/ }));
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain(
        'left=ev-left&right=ev-right'
      )
    );
    expect(screen.getByTestId('location').textContent).not.toContain('leftCapture');

    // After the server's default-capture resolution the URL is replaced with pins.
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain(
        'leftCapture=cap-left&rightCapture=cap-right'
      )
    );
    expect(await screen.findByText('Shared claim text')).toBeDefined();
    expect(apiMocks.getComparison).toHaveBeenLastCalledWith(
      'case-1',
      expect.objectContaining({ left: 'ev-left', right: 'ev-right' })
    );
  });

  it('keeps an already pinned capture id in the committed URL', async () => {
    addToComparisonTray('case-1', 'current', {
      evidenceId: 'ev-left',
      captureId: 'cap-left-old',
    });
    addToComparisonTray('case-1', 'current', {
      evidenceId: 'ev-right',
      captureId: 'cap-right-old',
    });
    renderCompare();

    fireEvent.click(await screen.findByRole('button', { name: /Compare draft/ }));
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain(
        'leftCapture=cap-left-old&rightCapture=cap-right-old'
      )
    );
    expect(apiMocks.getComparison).toHaveBeenLastCalledWith(
      'case-1',
      expect.objectContaining({
        leftCapture: 'cap-left-old',
        rightCapture: 'cap-right-old',
      })
    );
  });

  it('directs a single source with older capture versions to capture history, not Compare', async () => {
    apiMocks.getEvidenceDetail.mockResolvedValue(
      evidenceDetail({
        id: 'ev-old',
        currentCaptureId: 'cap-new',
        captures: [
          capture({ id: 'cap-new', evidenceId: 'ev-old', isCurrent: true }),
          capture({ id: 'cap-old', evidenceId: 'ev-old', isCurrent: false }),
        ],
      })
    );
    addToComparisonTray('case-1', 'current', { evidenceId: 'ev-old', captureId: null });
    renderCompare();

    expect(await screen.findByText(/2 recorded capture versions/)).toBeDefined();
    expect(screen.getByText(/belong in capture history, not in Compare/)).toBeDefined();
    // One source never becomes a self-comparison.
    expect(screen.getByRole('button', { name: /Compare draft/ })).toHaveProperty(
      'disabled',
      true
    );
    expect(apiMocks.getComparison).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Open capture history/ }));
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toContain(
        '/cases/case-1/evidence?'
      )
    );
    const location = screen.getByTestId('location').textContent ?? '';
    expect(location).toContain('evidence=ev-old');
    expect(location).not.toContain('/compare');
  });

  it('renders comparison-same-source as a validation error and never as a comparison', async () => {
    renderCompare('/cases/case-1/compare?left=ev-left&right=ev-left');

    const state = document.querySelector('[data-state="comparison-same-source"]');
    expect(state).not.toBeNull();
    await waitFor(() => expect(screen.getByText('Choose two different sources.')).toBeDefined());
    expect(state?.getAttribute('role')).toBe('alert');
    expect(state?.textContent).toContain('validation error, not a comparison');
    // Two captures of one source are refused before any comparison is requested.
    expect(apiMocks.getComparison).not.toHaveBeenCalled();
    expect(screen.queryByRole('heading', { name: 'Comparison results' })).toBeNull();
    expect(screen.queryByText('Shared claim text')).toBeNull();
  });

  it('clears the draft on a case switch after the notice and is empty from another case', async () => {
    addToComparisonTray('case-1', 'current', { evidenceId: 'ev-left' });
    addToComparisonTray('case-1', 'current', { evidenceId: 'ev-right' });

    renderCompare('/cases/case-2/compare', 'case-2');

    expect(await screen.findByText(/cleared because the case changed/)).toBeDefined();
    expect(screen.getByText(/Comparison draft \(0 of 2\)/)).toBeDefined();
    expect(getComparisonTray('case-2', 'current').entries).toHaveLength(0);
    // No cross-case mixing: the original case's draft is gone too.
    expect(getComparisonTray('case-1', 'current').entries).toHaveLength(0);
  });

  it('keeps the draft across re-renders within the session', async () => {
    addToComparisonTray('case-1', 'current', { evidenceId: 'ev-left' });
    addToComparisonTray('case-1', 'current', { evidenceId: 'ev-right' });
    const { container } = renderCompare();

    // Present on the first paint, before the evidence list resolves.
    expect(screen.getByText(/Comparison draft \(2 of 2\)/)).toBeDefined();
    expect(container.querySelectorAll('.compare-tray-entries [data-evidence-id]')).toHaveLength(2);

    // Still there after the async evidence load re-renders the tab.
    expect(await screen.findByText(/2 sources in this case/)).toBeDefined();
    expect(
      screen.getByRole('button', { name: 'Remove ev-left from comparison draft' })
    ).toBeDefined();
    expect(screen.getByText(/Comparison draft \(2 of 2\)/)).toBeDefined();
  });

  it('removes one draft entry and refuses a third without replacing the rest', async () => {
    addToComparisonTray('case-1', 'current', { evidenceId: 'ev-left' });
    addToComparisonTray('case-1', 'current', { evidenceId: 'ev-right' });
    const third = addToComparisonTray('case-1', 'current', { evidenceId: 'ev-extra' });
    expect(third.ok).toBe(false);

    renderCompare();

    expect(await screen.findByText(/already holds two distinct sources/)).toBeDefined();
    expect(getComparisonTray('case-1', 'current').entries.map((e) => e.evidenceId)).toEqual([
      'ev-left',
      'ev-right',
    ]);

    fireEvent.click(
      screen.getByRole('button', { name: 'Remove ev-left from comparison draft' })
    );
    await waitFor(() => expect(screen.getByText(/Comparison draft \(1 of 2\)/)).toBeDefined());
    expect(getComparisonTray('case-1', 'current').entries.map((e) => e.evidenceId)).toEqual([
      'ev-right',
    ]);
  });
});
