import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import CaseIntelligenceCenter from './CaseIntelligenceCenter';
import { useCaseStore } from '../stores/case-store';

const apiMocks = vi.hoisted(() => ({
  getCaseDetail: vi.fn(),
  getClaimsOverviewForCase: vi.fn(),
  getEvidenceForCase: vi.fn(),
  getExceptionsForCase: vi.fn(),
  getPartiesForCase: vi.fn(),
  getTimelineForCase: vi.fn(),
  getRunHistoryForCase: vi.fn(),
  getReportForCase: vi.fn(),
  downloadManifestReport: vi.fn(),
  downloadMarkdownReport: vi.fn(),
}));

vi.mock('../services/api', () => apiMocks);

const baseCaseDetail = {
  case: {
    id: 'case-12345678',
    query: 'Example Case',
    conflictDomain: 'Energy Security',
    status: 'review ready',
    stage: 'REVIEW',
    counts: {
      articles: 1,
      events: 1,
      reviewItems: 1,
    },
    automationMode: 'safe',
    hasNewMaterial: true,
    openExceptionsCount: 1,
    lastUpdated: '2026-03-19T10:00:00Z',
    reportPath: null,
  },
  tabs: {
    claims: [],
    evidence: [],
    exceptions: [],
    parties: [],
    timeline: [],
    runHistory: [],
    narratives: [],
    report: {
      status: 'pending',
      markdownPath: null,
      markdownContent: null,
      manifestPath: null,
    },
  },
} as const;

const routeExpectations = [
  { initialEntry: '/cases/case-12345678', heading: 'Operator Commands' },
  { initialEntry: '/cases/case-12345678/evidence', heading: 'Evidence Gallery (1)' },
  { initialEntry: '/cases/case-12345678/claims', heading: 'Primary Claims Mapping' },
  { initialEntry: '/cases/case-12345678/parties', heading: 'Confirmed & Inferred Parties' },
  { initialEntry: '/cases/case-12345678/map', heading: 'Geographic Event Map' },
  { initialEntry: '/cases/case-12345678/timeline', heading: 'Investigation Timeline' },
  { initialEntry: '/cases/case-12345678/exceptions', heading: 'Exception Queue' },
  { initialEntry: '/cases/case-12345678/report', heading: 'Final Investigation Report' },
  { initialEntry: '/cases/case-12345678/run-history', heading: 'Pipeline Execution History' },
];

function renderCaseRoute(initialEntry: string) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/cases/:id/*" element={<CaseIntelligenceCenter />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('CaseIntelligenceCenter routes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCaseStore.getState().clearActiveCase();

    apiMocks.getCaseDetail.mockResolvedValue(baseCaseDetail);
    apiMocks.getClaimsOverviewForCase.mockResolvedValue({
      claims: [
        {
          id: 'claim-1',
          text: 'Claim text',
          verificationStatus: 'confirmed',
          type: 'fact',
          controversyScore: 0.1,
          supportCount: 2,
          opposeCount: 0,
          sourceDiversityCount: 1,
          claimSignature: 'claim-1',
          narrativeClusterId: 'cluster-1',
          evidence: [],
        },
      ],
      narratives: [
        {
          id: 'narrative-1',
          clusterId: 'cluster-1',
          stanceSummary: 'Primary cluster',
          sourceCount: 1,
          claimCount: 1,
        },
      ],
    });
    apiMocks.getEvidenceForCase.mockResolvedValue([
      {
        id: 'evidence-1',
        title: 'Evidence title',
        originUrl: 'https://example.com',
        canonicalUrl: 'https://example.com',
        publisher: 'Example News',
        sourceType: 'rss',
        verificationStatus: 'confirmed',
        credibilityTier: 'high',
        requiresHumanReview: false,
        linkedClaims: ['claim-1'],
        verificationChecks: [],
      },
    ]);
    apiMocks.getExceptionsForCase.mockResolvedValue([
      {
        id: 'exc-1',
        type: 'missing_source',
        message: 'Need another source',
        severity: 'medium',
        status: 'open',
        recommendedAction: 'Add corroboration',
        isOpen: true,
      },
    ]);
    apiMocks.getPartiesForCase.mockResolvedValue([
      {
        id: 'party-1',
        name: 'Alpha',
        aliases: [],
        description: 'Example party',
        overallStance: 'neutral',
        isModelInferred: false,
        associatedClaimsCount: 1,
      },
    ]);
    apiMocks.getTimelineForCase.mockResolvedValue([
      {
        id: 'event-1',
        timestamp: '2026-03-19T10:00:00Z',
        title: 'Timeline event',
        summary: 'Event summary',
        verificationStatus: 'confirmed',
        linkedEvidenceCount: 1,
        locationCountryCode: 'SG',
        locationLat: 1.3521,
        locationLon: 103.8198,
      },
    ]);
    apiMocks.getRunHistoryForCase.mockResolvedValue([
      {
        id: 'run-1',
        stage: 'REVIEW',
        model: 'gpt-5.4',
        durationMs: 1000,
        status: 'success',
        fallbackCount: 0,
        parseFailureCount: 0,
        timestamp: '2026-03-19T10:00:00Z',
        message: null,
      },
    ]);
    apiMocks.getReportForCase.mockResolvedValue({
      status: 'pending',
      markdownPath: null,
      markdownContent: null,
      manifestPath: null,
    });
  });

  it.each(routeExpectations)('renders the expected view for $initialEntry', async ({ initialEntry, heading }) => {
    renderCaseRoute(initialEntry);

    expect(await screen.findByRole('heading', { name: heading })).toBeDefined();
    expect(screen.queryByText('Tab not found')).toBeNull();
  });
});
