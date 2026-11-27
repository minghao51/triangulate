import { test, expect, type Locator, type Page } from '@playwright/test';
import {
  CASE_ID,
  CASE_SUMMARY,
  caseDetail,
  comparisonFor,
  evidenceDetailFor,
  assertNoForeignNetwork,
  installApiMock,
  reportPending,
  runChangesFor,
  runHistory,
  searchResults,
  type MockOptions,
  type MockKey,
} from './support/mock-api';
import {
  assertNoHorizontalOverflow,
  attachPageHygiene,
  captureCell,
  recordCell,
} from './support/page-hygiene';

/**
 * F16 — the 42 selected states from hub §6 plus the two R01 "uncertain" write
 * states (44 cells), each triggered by an endpoint
 * override, a URL value or a real UI interaction, and each proven by a distinct
 * text/DOM marker that only that state renders.
 *
 * The marker column in the report is the `evidence` string below: that is the
 * text actually observed in the browser for this state.
 */

type Overrides = Partial<Record<MockKey, { status?: number; body?: unknown; hang?: boolean }>>;

interface StateCell {
  id: string;
  path: string;
  overrides?: Overrides;
  /** Real UI interaction that produces the state (after the route loads). */
  setup?: (page: Page) => Promise<void>;
  marker: (page: Page) => Locator;
  /** Distinct text recorded as the observed marker for this state. */
  evidence: string;
}

const overview = `/cases/${CASE_ID}`;
const evidenceDetail = (status: string | null) => ({
  evidenceDetail: { body: evidenceDetailFor(status) },
});
const comparePath = `/cases/${CASE_ID}/compare?left=ev-gate-1&right=ev-gate-2`;

const states: StateCell[] = [
  // ---------------------------------------------------------------- shared (4)
  {
    id: 'shared-loading',
    path: `/cases/${CASE_ID}/claims`,
    overrides: { claimsOverview: { hang: true } },
    marker: (page) => page.locator('[data-state="loading"]').first(),
    evidence: 'data-state="loading" — "Loading claims for this case."',
  },
  {
    id: 'shared-empty',
    path: `/cases/${CASE_ID}/parties`,
    overrides: { parties: { body: [] } },
    marker: (page) => page.locator('[data-state="empty"]').first(),
    evidence: '"No parties have been recorded for this case yet."',
  },
  {
    id: 'shared-not-found',
    path: `/cases/${CASE_ID}/timeline`,
    overrides: { timeline: { status: 404, body: { detail: 'no timeline recorded' } } },
    marker: (page) => page.locator('[data-state="not-found"]').first(),
    evidence: '"This case has no timeline recorded."',
  },
  {
    id: 'shared-network-error',
    path: `/cases/${CASE_ID}/parties`,
    overrides: { parties: { status: 500, body: { detail: 'gate parties backend down' } } },
    marker: (page) => page.locator('[data-state="network-error"]').first(),
    evidence: '"The recorded parties could not be loaded." + detail + Retry',
  },

  // ------------------------------------------------------------- inspector (5)
  ...[
    ['inspector-missing-quotation', 'not_provided'],
    ['inspector-source-unavailable', 'source_unavailable'],
    ['inspector-ambiguous', 'ambiguous'],
    ['inspector-no-match', 'no_match'],
    // A stored value that predates alignment assessment is the legacy fallback.
    ['inspector-legacy', 'unmapped_legacy_value'],
  ].map(([id, status]) => ({
    id: id as string,
    path: `/cases/${CASE_ID}/evidence?evidence=ev-gate-1&claim=cl-gate-1`,
    overrides: evidenceDetail(status as string | null),
    marker: (page: Page) => page.locator(`[data-state="${id}"]`).first(),
    evidence: `data-state="${id}"`,
  })),

  // ------------------------------------------------------------ comparison (6)
  {
    id: 'comparison-selection',
    path: `/cases/${CASE_ID}/compare`,
    marker: (page) => page.locator('[data-state="comparison-selection"]').first(),
    evidence: '"Choose a left and a right source to compare their capture-linked claims."',
  },
  {
    id: 'comparison-same-source',
    path: `/cases/${CASE_ID}/compare?left=ev-gate-1&right=ev-gate-1`,
    marker: (page) => page.locator('[data-state="comparison-same-source"]').first(),
    evidence: '"Choose two different sources."',
  },
  {
    id: 'comparison-no-second-source',
    path: `/cases/${CASE_ID}/evidence`,
    setup: async (page) => {
      await page.getByRole('button', { name: 'Select evidence ev-gate-1' }).click();
      await page.getByRole('button', { name: /Add to comparison/ }).click();
      await page.getByRole('button', { name: /Open comparison/ }).click();
      await expect(page).toHaveURL(/\/compare$/);
    },
    marker: (page) => page.locator('[data-state="comparison-no-second-source"]').first(),
    evidence: '"One source in the draft. Add one more distinct source before comparing"',
  },
  {
    id: 'comparison-empty',
    path: `/cases/${CASE_ID}/compare`,
    marker: (page) => page.locator('.compare-tray[data-state="comparison-empty"]').first(),
    evidence: '"No sources in the draft yet." (tray data-state="comparison-empty")',
  },
  {
    id: 'comparison-historical-unavailable',
    path: comparePath,
    overrides: { comparison: { body: comparisonFor({ historicalUnavailable: true }) } },
    marker: (page) =>
      page.locator('[data-state="comparison-historical-unavailable"]').first(),
    evidence:
      '"This capture\'s historical claim alignment is not available. The current claim links are not substituted."',
  },
  {
    id: 'comparison-dependency-warning',
    path: comparePath,
    overrides: { comparison: { body: comparisonFor({ dependencyDetected: true }) } },
    marker: (page) => page.locator('[data-state="comparison-dependency-warning"]').first(),
    evidence: '"Dependency detected" + recorded dependency reasons',
  },

  // --------------------------------------------------------------- changes (4)
  {
    id: 'changes-initial',
    path: `/cases/${CASE_ID}/changes`,
    overrides: { runChanges: { body: runChangesFor('initial') } },
    marker: (page) => page.getByText('First observation', { exact: true }).first(),
    evidence: '"First observation" — no earlier successful observation',
  },
  {
    id: 'changes-pending',
    path: `/cases/${CASE_ID}/changes`,
    overrides: { runChanges: { body: runChangesFor('pending') } },
    marker: (page) => page.getByText('Run in progress', { exact: true }).first(),
    evidence: '"Run in progress" — a pending run is not an empty delta',
  },
  {
    id: 'changes-unavailable',
    path: `/cases/${CASE_ID}/changes`,
    overrides: { runChanges: { body: runChangesFor('unavailable') } },
    marker: (page) => page.getByText('Historical change data unavailable', { exact: true }).first(),
    evidence: '"Historical change data unavailable"',
  },
  {
    id: 'changes-unchanged-partial',
    path: `/cases/${CASE_ID}/changes`,
    overrides: {
      runChanges: { body: runChangesFor('ready', { total: 0, coverage: 'partial' }) },
    },
    marker: (page) => page.getByText('Unchanged', { exact: true }).first(),
    evidence:
      '"Coverage: Partial coverage" warning + "Unchanged" + "This says nothing about sources outside the observed scope"',
  },

  // ---------------------------------------------------------------- search (4)
  {
    id: 'search-no-results',
    path: `/cases/${CASE_ID}/search?q=gate`,
    overrides: {
      search: { body: { ...searchResults(), total: 0, items: [] } },
    },
    marker: (page) => page.getByText('No matches for this query and these filters.').first(),
    evidence: '"No matches for this query and these filters."',
  },
  {
    id: 'search-index-unavailable',
    path: `/cases/${CASE_ID}/search?q=gate`,
    overrides: { search: { status: 503, body: { detail: 'search index unavailable' } } },
    marker: (page) => page.getByRole('heading', { name: 'Search index unavailable' }).first(),
    evidence: '"Search index unavailable" + rebuild-search CLI hint',
  },
  {
    id: 'search-invalid-filters',
    path: `/cases/${CASE_ID}/search?q=gate`,
    overrides: { search: { status: 422, body: { detail: 'invalid search filters' } } },
    marker: (page) =>
      page.getByRole('heading', { name: 'Search query or filters are invalid' }).first(),
    evidence: '"Search query or filters are invalid"',
  },
  {
    id: 'search-out-of-range',
    path: `/cases/${CASE_ID}/search?q=gate&offset=50`,
    overrides: {
      search: { body: { ...searchResults(), total: 3, offset: 50, items: [] } },
    },
    marker: (page) => page.getByText(/This page is beyond the last result/).first(),
    evidence: '"This page is beyond the last result — showing the first page instead."',
  },

  // ---------------------------------------------------------------- review (5)
  {
    id: 'review-saving',
    path: overview,
    overrides: { reviewAction: { hang: true } },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Approve', exact: true }).click();
    },
    marker: (page) =>
      page.locator('[data-write-scope="review"] [data-write-state="pending"]').first(),
    evidence: '"Saving…" — only this form is disabled while the server answers',
  },
  {
    // A known pre-write refusal (the API's 404) is definite: "failed". A bare
    // 5xx proves nothing about whether the write landed, so R01 reports it as
    // "uncertain" in the cell below instead.
    id: 'review-failed',
    path: overview,
    overrides: {
      reviewAction: { status: 404, body: { detail: 'no such review target' } },
    },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Approve', exact: true }).click();
    },
    marker: (page) =>
      page.locator('[data-write-scope="review"] [data-write-state="failed"]').first(),
    evidence: '"Rejected by the server" + 404 detail (known pre-write refusal)',
  },
  {
    id: 'review-uncertain',
    path: overview,
    overrides: { reviewAction: { status: 500, body: { detail: 'gate review write failed' } } },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Approve', exact: true }).click();
    },
    marker: (page) =>
      page.locator('[data-write-scope="review"] [data-write-state="uncertain"]').first(),
    evidence: '"Outcome unknown" — an ambiguous 5xx blocks repeats and offers GET-only reconciliation',
  },
  {
    id: 'review-blocked',
    path: overview,
    overrides: { reviewAction: { status: 422, body: { detail: 'not permitted for this case' } } },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Approve', exact: true }).click();
    },
    marker: (page) =>
      page.locator('[data-write-scope="review"] [data-write-state="blocked"]').first(),
    evidence: '"Blocked (422)" — the server rejected this write as invalid or not permitted',
  },
  {
    id: 'review-saved',
    path: overview,
    setup: async (page) => {
      await page.getByRole('button', { name: 'Approve', exact: true }).click();
    },
    marker: (page) =>
      page.locator('[data-write-scope="review"] [data-write-state="saved"]').first(),
    evidence: '"Saved and refreshed" — server ack plus refreshed read',
  },
  {
    id: 'review-stale',
    path: overview,
    setup: async (page) => {
      await page.getByRole('button', { name: 'Approve', exact: true }).click();
      await expect(
        page.locator('[data-write-scope="review"] [data-write-state="saved"]')
      ).toBeVisible();
      // A later read (triggered by the annotation save's refresh) makes the
      // earlier saved banner stale evidence instead of a fresh save.
      await page.getByLabel('Annotation content').fill('Gate annotation after save.');
      await page.getByRole('button', { name: 'Save Annotation' }).click();
    },
    marker: (page) =>
      page.locator('[data-write-scope="review"] [data-write-state="stale"]').first(),
    evidence: '"Stale" — a recorded refresh happened after this form was saved',
  },

  // ------------------------------------------------------------ annotation (1)
  {
    id: 'annotation-invalid',
    path: overview,
    overrides: { annotation: { status: 422, body: { detail: 'target not in this case' } } },
    setup: async (page) => {
      await page.getByLabel('Annotation content').fill('Gate annotation rejected target.');
      await page.getByRole('button', { name: 'Save Annotation' }).click();
    },
    marker: (page) =>
      page.locator('[data-write-scope="annotation"] [data-write-state="blocked"]').first(),
    evidence: 'annotation scope "Blocked (422)" + uniform 422 detail',
  },

  // ------------------------------------------------------------- exception (3)
  {
    id: 'exception-pending',
    path: `/cases/${CASE_ID}/exceptions`,
    overrides: { exceptionAction: { hang: true } },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Resolve', exact: true }).click();
    },
    marker: (page) =>
      page
        .locator('[data-exception-id="exc-gate-1"] [data-write-state="pending"]')
        .first(),
    evidence: 'exception row "Saving…" pending banner',
  },
  {
    // Same R01 split as the review form: 404 is a definite refusal, a bare 5xx
    // is an unknown outcome.
    id: 'exception-failed',
    path: `/cases/${CASE_ID}/exceptions`,
    overrides: {
      exceptionAction: { status: 404, body: { detail: 'no such exception' } },
    },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Resolve', exact: true }).click();
    },
    marker: (page) =>
      page
        .locator('[data-exception-id="exc-gate-1"] [data-write-state="failed"]')
        .first(),
    evidence: 'exception row "Rejected by the server" banner',
  },
  {
    id: 'exception-uncertain',
    path: `/cases/${CASE_ID}/exceptions`,
    overrides: {
      exceptionAction: { status: 500, body: { detail: 'gate exception write failed' } },
    },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Resolve', exact: true }).click();
    },
    marker: (page) =>
      page
        .locator('[data-exception-id="exc-gate-1"] [data-write-state="uncertain"]')
        .first(),
    evidence: 'exception row "Outcome unknown" banner — repeat POSTs blocked, GET reconciliation only',
  },
  {
    id: 'exception-empty',
    path: `/cases/${CASE_ID}/exceptions`,
    overrides: { exceptions: { body: [] } },
    marker: (page) => page.locator('[data-state="empty"]').first(),
    evidence: '"No open exceptions"',
  },

  // ------------------------------------------------------------ evaluation (2)
  {
    id: 'evaluation-unavailable',
    path: overview,
    overrides: { evaluation: { body: { latest: null, history: [] } } },
    marker: (page) => page.getByText('No saved evaluation', { exact: true }).first(),
    evidence: '"No saved evaluation" — latest: null is a valid recorded answer',
  },
  {
    id: 'evaluation-failed',
    path: overview,
    overrides: { evaluation: { status: 500, body: { detail: 'gate evaluation read failed' } } },
    marker: (page) => page.getByText('Evaluation unavailable', { exact: true }).first(),
    evidence: '"Evaluation unavailable" + read error detail + Retry',
  },

  // ---------------------------------------------------------------- report (2)
  {
    id: 'report-pending',
    path: `/cases/${CASE_ID}/report`,
    overrides: {
      report: { body: reportPending() },
      runHistory: { body: [{ ...runHistory()[0], id: 'stage-run-gate-running', status: 'running' }] },
    },
    marker: (page) => page.locator('[data-report-state="pending"]').first(),
    evidence: 'data-report-state="pending" — "Report generation in progress"',
  },
  {
    id: 'report-download-error',
    path: `/cases/${CASE_ID}/report`,
    overrides: { reportMarkdown: { status: 500, body: 'gate download failed' } },
    setup: async (page) => {
      await page.getByTestId('report-download-markdown').click();
    },
    marker: (page) => page.locator('[data-report-state="download-error"]').first(),
    evidence: '"Download error" + "The stored report itself was not changed."',
  },

  // ------------------------------------------------------------- singletons (6)
  {
    id: 'map-empty',
    path: `/cases/${CASE_ID}/map`,
    overrides: { timeline: { body: [] } },
    marker: (page) => page.locator('.map-empty').first(),
    evidence: '"No geotagged events are available for this case yet."',
  },
  {
    id: 'timeline-unknown',
    path: `/cases/${CASE_ID}/timeline`,
    overrides: {
      timeline: {
        body: [
          {
            id: 'evt-gate-unknown',
            timestamp: null,
            title: 'Gate event with no recorded date',
            summary: 'Recorded event without a date.',
            verificationStatus: 'unknown',
            linkedEvidenceCount: 0,
          },
        ],
      },
    },
    marker: (page) => page.locator('[data-date-state="unknown"]').first(),
    evidence: '"Date not recorded" (data-date-state="unknown")',
  },
  {
    id: 'pipeline-unrecorded',
    path: `/cases/${CASE_ID}/pipeline`,
    overrides: {
      caseDetail: {
        body: { ...caseDetail(), case: { ...CASE_SUMMARY, stage: null } },
      },
    },
    marker: (page) => page.locator('[data-state="pipeline-unrecorded"]').first(),
    evidence: '"Not recorded" — no pipeline stage is recorded for this case',
  },
  {
    id: 'monitoring-unavailable',
    path: '/monitoring',
    marker: (page) => page.locator('[data-state="monitoring-unavailable"]').first(),
    evidence: '"Not provided by the API" for schedule/next-run and system health',
  },
  {
    id: 'evidence-filter-empty',
    path: `/cases/${CASE_ID}/evidence?publisher=No%20Recorded%20Publisher`,
    marker: (page) => page.locator('[data-state="evidence-filter-empty"]').first(),
    evidence: '"No loaded evidence matches these filters"',
  },
  {
    id: 'narratives-empty',
    path: `/cases/${CASE_ID}/narratives`,
    overrides: {
      claimsOverview: { body: { claims: [], narratives: [] } },
      parties: { body: [] },
      timeline: { body: [] },
    },
    marker: (page) => page.getByText(/No narrative clusters have been persisted/).first(),
    evidence: '"No narrative clusters have been persisted for this case."',
  },
];

test.describe('F16 selected states', () => {
  for (const cell of states) {
    test(`${cell.id} shows its own state`, async ({ page }, testInfo) => {
      const hygiene = attachPageHygiene(page);
      const session = await installApiMock(page, {
        overrides: cell.overrides as MockOptions['overrides'],
      });

      await page.goto(cell.path);
      await expect(page.locator('main#shell-main')).toBeVisible();
      if (cell.setup) await cell.setup(page);
      await expect(cell.marker(page)).toBeVisible();

      hygiene.assertClean(cell.id);
      const overflow = await assertNoHorizontalOverflow(page, cell.id);
      await captureCell(page, testInfo.project.name, cell.id);
      recordCell({
        cell: cell.id,
        project: testInfo.project.name,
        suite: 'states',
        marker: cell.evidence,
        overflow,
        transportStatusLines: hygiene.transportStatusLines,
        appConsoleErrors: hygiene.consoleErrors,
        pageErrors: hygiene.pageErrors,
      });

      // The state trigger itself is allowed the three narrow POST families; a
      // pure read surface must stay GET-only.
      assertNoForeignNetwork(session, cell.id);
      const posts = session.audit.filter((entry) => entry.method !== 'GET');
      for (const entry of posts) {
        expect(
          entry.path,
          `${cell.id}: unexpected non-GET ${entry.method} ${entry.path}`
        ).toMatch(
          /^\/api\/cases\/[^/]+\/(review-actions\/review|review-actions\/exceptions\/[^/]+|annotations)$/
        );
      }
    });
  }
});
