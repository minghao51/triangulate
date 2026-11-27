import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import SourceAnalysis from './SourceAnalysis';
import type { Evidence } from '../types/backend-models';
import type { SourceSummary } from '../services/api';

const apiMocks = vi.hoisted(() => ({
  getCaseSources: vi.fn(),
  getEvidenceForCase: vi.fn(),
  // Detail readers exist in the real module; F09 must never call them from this
  // surface (no per-evidence or per-source fan-out).
  getEvidenceDetail: vi.fn(),
  getCitationDetail: vi.fn(),
  getCaptureWindow: vi.fn(),
}));

vi.mock('../services/api', () => apiMocks);

const evidence = (overrides: Partial<Evidence>): Evidence => ({
  id: 'ev-1',
  title: 'Title',
  originUrl: 'https://example.com/a',
  canonicalUrl: 'https://example.com/a',
  publisher: 'BBC News',
  sourceType: 'rss',
  verificationStatus: 'unknown',
  credibilityTier: null,
  requiresHumanReview: false,
  linkedClaims: [],
  verificationChecks: [],
  ...overrides,
});

/** One `SourceSummaryDTO` exactly as the existing GET returns it. */
const summary = (overrides: Partial<SourceSummary> = {}): SourceSummary => ({
  caseId: 'case-1',
  scope: 'case',
  claimId: null,
  claimSignature: null,
  evidenceCount: 4,
  distinctPublisherCount: 3,
  dependencyGroupCount: 1,
  unknownPublisherCount: 1,
  independenceStatus: 'unknown',
  policy: {
    version: 'source-dependency-policy-v1',
    urlNormalization: ['lowercase host', 'strip tracking parameters'],
    publisherIdentity: ['explicit origin key', 'host key'],
    dependencyEdges: ['same publisher key', 'identical normalized capture'],
    textFingerprint: 'text-fingerprint-v1',
    textFingerprintNormalization: 'NFKC + whitespace collapse',
    minCopyNonWhitespaceCodePoints: 200,
    limitations: ['Repeated wire copy is grouped, not removed.'],
  },
  publisherCounts: [
    {
      publisherKey: 'meridian-wire',
      publisher: 'Meridian Wire',
      evidenceCount: 3,
      dependencyGroupCount: 1,
      provisional: false,
    },
    {
      publisherKey: 'northern.example.com',
      publisher: 'Northern Post',
      evidenceCount: 1,
      dependencyGroupCount: 0,
      provisional: true,
    },
  ],
  groups: [
    {
      id: 'group-1',
      reasons: ['same_publisher', 'identical_normalized_capture'],
      publisherKeys: ['meridian-wire'],
      evidenceCount: 2,
      members: [
        {
          evidenceId: 'ev-1',
          publisher: 'Meridian Wire',
          publisherKey: 'meridian-wire',
          publisherKeyProvisional: false,
          host: 'meridian.example.com',
          originUrl: 'https://meridian.example.com/a',
          canonicalUrl: 'https://meridian.example.com/a',
          sourceUrl: 'https://meridian.example.com/a',
          caseArticleId: null,
          explicitOriginKey: null,
          captureId: 'cap-1',
          captureKind: 'live',
          captureTextSha256: 'sha-1',
          captureNormalizedTextSha256: 'nsha-1',
          captureCharLength: 900,
          recordedAt: '2026-03-03T06:30:00Z',
          observedAt: '2026-03-03T06:25:00Z',
          copyFingerprint: 'copy-1',
          copyNonWhitespaceCount: 880,
          dependencyReasons: ['same_publisher'],
        },
        {
          evidenceId: 'ev-2',
          publisher: 'Meridian Wire',
          publisherKey: 'meridian-wire',
          publisherKeyProvisional: false,
          host: 'meridian.example.com',
          originUrl: null,
          canonicalUrl: null,
          sourceUrl: null,
          caseArticleId: null,
          explicitOriginKey: null,
          captureId: null,
          captureKind: null,
          captureTextSha256: null,
          captureNormalizedTextSha256: null,
          captureCharLength: null,
          recordedAt: null,
          observedAt: null,
          copyFingerprint: null,
          copyNonWhitespaceCount: 0,
          dependencyReasons: [],
        },
      ],
    },
  ],
  ...overrides,
});

function renderSources() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/cases/case-1/sources']}>
        <Routes>
          <Route path="/cases/:id/sources" element={<SourceAnalysis />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.getCaseSources.mockResolvedValue(summary());
  apiMocks.getEvidenceForCase.mockResolvedValue([evidence({})]);
});

describe('SourceAnalysis source summary wiring', () => {
  it('issues exactly one case-scoped sources GET and renders the typed DTO fields', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([
      evidence({ id: 'ev-1', publisher: 'Meridian Wire' }),
      evidence({ id: 'ev-2', publisher: null, canonicalUrl: 'https://example.com/same' }),
      evidence({ id: 'ev-3', canonicalUrl: 'https://example.com/same' }),
      evidence({ id: 'ev-4' }),
    ]);
    renderSources();

    expect(await screen.findByText('Source summary (sources API)')).toBeDefined();

    // Exactly one summary GET, case-scoped, with no claim selector and no snapshot.
    expect(apiMocks.getCaseSources).toHaveBeenCalledTimes(1);
    expect(apiMocks.getCaseSources).toHaveBeenCalledWith('case-1');

    // Only the single case-keyed evidence collection read backs the metadata panel.
    expect(apiMocks.getEvidenceForCase).toHaveBeenCalledTimes(1);
    expect(apiMocks.getEvidenceForCase).toHaveBeenCalledWith('case-1');

    // No per-evidence or per-source detail fan-out of any kind.
    expect(apiMocks.getEvidenceDetail).not.toHaveBeenCalled();
    expect(apiMocks.getCitationDetail).not.toHaveBeenCalled();
    expect(apiMocks.getCaptureWindow).not.toHaveBeenCalled();

    // DTO totals, rendered from the API values rather than from the evidence list.
    expect(screen.getByText('Evidence Records (summary)')).toBeDefined();
    expect(screen.getByText('Distinct Publishers')).toBeDefined();
    expect(screen.getByText('Dependency Groups')).toBeDefined();
    expect(screen.getByText('Unknown Publishers')).toBeDefined();
    expect(screen.getByText('observed publisher identities')).toBeDefined();
    expect(
      screen.getByText(/Unknown — no independence determined/)
    ).toBeDefined();
    expect(screen.getByText(/Policy version: source-dependency-policy-v1/)).toBeDefined();

    // Publisher counts and dependency groups from the same DTO.
    expect(screen.getAllByText(/Meridian Wire · meridian-wire/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Northern Post · northern\.example\.com/)).toBeDefined();
    expect(screen.getByText(/provisional host/)).toBeDefined();
    expect(screen.getByText('group-1')).toBeDefined();
    expect(
      screen.getByText(/same publisher key, identical long captured text/)
    ).toBeDefined();
    expect(screen.getByText(/Publisher keys in this group: meridian-wire/)).toBeDefined();
    expect(screen.getByText(/capture cap-1 · live · 900 code points/)).toBeDefined();

    // The evidence-metadata panel is separately labelled and keeps its own count.
    expect(screen.getByText('Recorded evidence metadata')).toBeDefined();
    expect(screen.getByText('Evidence Items')).toBeDefined();
  });

  it('shows a dependency-detected status without turning it into an independence claim', async () => {
    apiMocks.getCaseSources.mockResolvedValue(
      summary({ independenceStatus: 'dependency_detected' })
    );
    renderSources();

    expect(
      await screen.findByText(/Dependency detected between recorded sources/)
    ).toBeDefined();
    expect(screen.getByText(/not an independence score and not corroboration/)).toBeDefined();
  });

  it('says an empty dependency list is not proof of independence', async () => {
    apiMocks.getCaseSources.mockResolvedValue(
      summary({ dependencyGroupCount: 0, groups: [] })
    );
    renderSources();

    expect(await screen.findByText(/no dependency group is recorded/i)).toBeDefined();
    expect(screen.getByText(/does not mean the sources were shown to be independent/)).toBeDefined();
  });

  it('retries both reads from the error state without inventing counts', async () => {
    apiMocks.getCaseSources.mockRejectedValueOnce(new Error('sources 500'));
    renderSources();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('sources 500');
    expect(screen.queryByText('Evidence Records (summary)')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(await screen.findByText('Source summary (sources API)')).toBeDefined();
    expect(apiMocks.getCaseSources).toHaveBeenCalledTimes(2);
  });

  it('renders the summary even when the evidence metadata list is empty', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([]);
    apiMocks.getCaseSources.mockResolvedValue(summary({ evidenceCount: 2 }));
    renderSources();

    expect(await screen.findByText('Source summary (sources API)')).toBeDefined();
    expect(screen.getByText('Recorded evidence metadata')).toBeDefined();
    expect(screen.getByText('No publisher is recorded for these evidence items.')).toBeDefined();
  });
});

describe('SourceAnalysis limitation copy', () => {
  it('never claims or implies publisher independence', async () => {
    renderSources();
    await screen.findByText('Source summary (sources API)');

    const text = document.body.textContent ?? '';
    const independentSentences = text.match(/[^.!?]*\bindependen[a-z]*\b[^.!?]*/gi) ?? [];
    // Every mention of independence on this surface is a negated one.
    expect(independentSentences.length).toBeGreaterThan(2);
    independentSentences.forEach((sentence) => {
      expect(sentence).toMatch(/not|no\b|never|cannot|without|unknown/i);
    });

    // No positive independence verdict anywhere in the copy.
    expect(text).not.toMatch(
      /independent (source|publisher)s? (were|are) (confirmed|verified|proven)/i
    );
    expect(text).not.toMatch(/proves? (publisher )?independence/i);
    // The only use of "verified independent" is a refusal of it.
    (text.match(/[^.!?]*verified independent[^.!?]*/gi) ?? []).forEach((sentence) => {
      expect(sentence).toMatch(/never|not|no\b/i);
    });
    expect(text).not.toMatch(/independence score: \d/i);

    // The mandatory honesty statements are present, adjacent to the summary.
    expect(
      screen.getByText(/not proof of independent corroboration/i)
    ).toBeDefined();
    expect(screen.getByText(/are not independent sources/i)).toBeDefined();
    expect(screen.getByText(/Model consensus is not truth/i)).toBeDefined();
    expect(
      screen.getByText(/A missing dependency is not proof of independence/i)
    ).toBeDefined();
  });

  it('states the server-reported policy and method limits', async () => {
    renderSources();
    await screen.findByText('Source summary (sources API)');

    expect(screen.getByText('What this summary does not establish')).toBeDefined();
    expect(screen.getByText('Repeated wire copy is grouped, not removed.')).toBeDefined();
    expect(screen.getByText(/at least 200 non-whitespace code points/)).toBeDefined();
    expect(screen.getByText(/lowercase host, strip tracking parameters/)).toBeDefined();
    expect(screen.getByText(/explicit origin key, host key/)).toBeDefined();
  });
});

describe('SourceAnalysis recorded evidence metadata', () => {
  it('does not derive bias, region or baseline scores from publisher names', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([
      evidence({ id: 'ev-1', publisher: 'Left Progressive Times', credibilityTier: 'high' }),
      evidence({ id: 'ev-2', publisher: 'Right Conservative Post', credibilityTier: null }),
    ]);
    renderSources();

    expect(await screen.findByText('Evidence Items')).toBeDefined();

    expect(screen.queryByText(/Left-leaning/i)).toBeNull();
    expect(screen.queryByText(/Right-leaning/i)).toBeNull();
    expect(screen.queryByText(/Source Bias/i)).toBeNull();
    expect(screen.queryByText(/Avg Credibility/i)).toBeNull();
    expect(screen.queryByText(/Verification Rate/i)).toBeNull();
    expect(screen.queryByText(/Baseline/i)).toBeNull();
    expect(screen.queryByText(/Source Diversity Analysis/i)).toBeNull();

    // Missing assessment is reported as not provided, not as a low score.
    expect(
      screen.getByText(/treated as not recorded\/provided, not as a low score/i)
    ).toBeDefined();
    expect(screen.getByText('Not provided')).toBeDefined();
  });

  it('labels the evidence count as evidence items, not as independent sources', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([
      evidence({ id: 'ev-1', canonicalUrl: 'https://example.com/same' }),
      evidence({ id: 'ev-2', canonicalUrl: 'https://example.com/same' }),
    ]);
    renderSources();

    expect(await screen.findByText('Evidence Items')).toBeDefined();
    expect(screen.queryByText('Total Sources')).toBeNull();
    expect(screen.getAllByText(/not a source-independence analysis/i).length).toBeGreaterThan(0);
    expect(screen.getByText('2 records')).toBeDefined();
  });

  it('shows a distinct empty state without zero-valued metric cards', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([]);
    apiMocks.getCaseSources.mockResolvedValue(summary({ evidenceCount: 0 }));
    renderSources();

    expect(await screen.findByText('No evidence records')).toBeDefined();
    expect(screen.queryByText('Evidence Items')).toBeNull();
    expect(screen.queryByText('0.0%')).toBeNull();
  });

  it('shows a retryable error and never fake zeros on failure', async () => {
    apiMocks.getEvidenceForCase.mockRejectedValueOnce(new Error('evidence 500'));
    renderSources();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('evidence 500');
    expect(screen.queryByText('Evidence Items')).toBeNull();

    apiMocks.getEvidenceForCase.mockResolvedValueOnce([evidence({})]);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(await screen.findByText('Evidence Items')).toBeDefined();
    expect(apiMocks.getEvidenceForCase).toHaveBeenCalledTimes(2);
  });

  it('avoids NaN/Infinity for items whose only fields are missing', async () => {
    apiMocks.getEvidenceForCase.mockResolvedValue([
      evidence({ id: 'ev-1', publisher: null, credibilityTier: null, sourceType: 'rss' }),
    ]);
    renderSources();

    expect(await screen.findByText('Evidence Items')).toBeDefined();
    expect(
      screen.getByText(/1 evidence item\(s\) have no\s+recorded publisher/i)
    ).toBeDefined();
    expect(screen.queryByText(/NaN|Infinity/)).toBeNull();
  });
});
