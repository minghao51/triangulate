import { test, expect, type Locator, type Page } from '@playwright/test';
import { CASE_ID, assertNoForeignNetwork, installApiMock } from './support/mock-api';
import {
  assertNoHorizontalOverflow,
  attachPageHygiene,
  captureCell,
  recordCell,
} from './support/page-hygiene';

/**
 * F16 — all 24 primary screens at 375×812, 768×1024 and 1280×800.
 *
 * Every cell asserts, in a real browser:
 *  1. no uncaught page error and no `console.error`;
 *  2. the screen's own marker is rendered (heading plus recorded content where
 *     the surface has data-driven content);
 *  3. no document-level horizontal overflow.
 *
 * A cell is PASS only if it ran here. Anything a component test asserts instead
 * is recorded as "component-test-only" evidence, never as a browser pass.
 */

interface ScreenCell {
  id: string;
  path: string;
  /** Primary screen marker (heading or the surface's recorded content). */
  marker: (page: Page) => Locator;
  /** Extra recorded-content marker, when the screen renders fetched data. */
  content?: (page: Page) => Locator;
  /**
   * Screen `historical-snapshot` asks for a frozen claim view, served by the
   * evidence-hosted claim inspector with a pinned observation. The claims list
   * is current-only and gates a pinned observation instead (asserted in the
   * component suite).
   */
  expectedFailure?: string;
  settleMs?: number;
}

const T = (text: string | RegExp, exact = false) => (page: Page) =>
  page.getByText(text, { exact });
const H = (name: string | RegExp) => (page: Page) => page.getByRole('heading', { name });

const cells: ScreenCell[] = [
  {
    id: '01-dashboard',
    path: '/dashboard',
    marker: H('Investigation Dashboard'),
    content: T('Gate Case'),
  },
  {
    id: '02-case-explorer',
    path: '/cases',
    marker: H('Case Explorer'),
    content: T('Gate Case'),
  },
  {
    id: '03-operator-launch',
    path: '/cases/new',
    marker: H('Operator Launch Guide'),
  },
  {
    id: '04-case-overview',
    path: `/cases/${CASE_ID}`,
    marker: H('Case Information'),
    content: T('Gate Case'),
  },
  {
    id: '05-review-annotation',
    path: `/cases/${CASE_ID}`,
    marker: H('Operator Commands'),
    content: H('Annotations'),
  },
  {
    id: '06-evidence-gallery',
    path: `/cases/${CASE_ID}/evidence`,
    marker: H('Evidence Gallery'),
    content: T('Gate evidence one'),
  },
  {
    id: '07-claims',
    path: `/cases/${CASE_ID}/claims`,
    marker: H('Primary Claims Mapping'),
    // cl-gate-1 is grouped under a collapsed narrative cluster, so the recorded
    // row that is visible on first paint is the second claim.
    content: T(/Gate claim two: a second recorded assertion/),
  },
  {
    id: '08-capture-inspector',
    path: `/cases/${CASE_ID}/evidence?evidence=ev-gate-1&claim=cl-gate-1`,
    marker: H(/Evidence inspector/),
    content: H('Validated passage'),
  },
  {
    id: '09-comparison',
    path: `/cases/${CASE_ID}/compare?left=ev-gate-1&right=ev-gate-2`,
    marker: H('Comparison results'),
    content: T(/Gate source ev-gate-1/),
  },
  {
    id: '10-source-provenance',
    path: `/cases/${CASE_ID}/sources`,
    marker: H('Source Analysis'),
    content: T('Gate Publisher'),
  },
  {
    id: '11-runs-changes',
    path: `/cases/${CASE_ID}/changes`,
    marker: H('Changes between observations'),
    content: T(/Run #2/),
  },
  {
    id: '12-historical-snapshot',
    path: `/cases/${CASE_ID}/evidence?claim=cl-gate-1&snapshot=snap-gate-1`,
    marker: T(/Historical observation snap-gate-1/),
    content: T(/resolved from the pinned observation/i),
  },
  {
    id: '13-search',
    path: `/cases/${CASE_ID}/search`,
    marker: H('Search this case'),
  },
  {
    id: '14-stage-history',
    path: `/cases/${CASE_ID}/run-history`,
    marker: H('Pipeline Execution History'),
    content: H('Stage attempts'),
  },
  {
    id: '15-pipeline',
    path: `/cases/${CASE_ID}/pipeline`,
    marker: H('Pipeline Monitor'),
    content: T(/last recorded case stage/i),
  },
  {
    id: '16-exception-queue',
    path: `/cases/${CASE_ID}/exceptions`,
    marker: H('Exception Queue'),
    content: T('Gate exception recorded for the operator.'),
  },
  {
    id: '17-parties',
    path: `/cases/${CASE_ID}/parties`,
    marker: H('Confirmed & Inferred Parties'),
    content: T('Gate Authority'),
  },
  {
    id: '18-geographic-map',
    path: `/cases/${CASE_ID}/map`,
    marker: H('Geographic Event Map'),
    content: T(/Gate event one/),
    settleMs: 400,
  },
  {
    id: '19-timeline',
    path: `/cases/${CASE_ID}/timeline`,
    marker: H('Investigation Timeline'),
    content: T('Gate event one'),
  },
  {
    id: '20-report',
    path: `/cases/${CASE_ID}/report`,
    marker: H('Final Investigation Report'),
    content: T(/Gate Investigation Report/),
  },
  {
    id: '21-corroboration-network',
    path: `/cases/${CASE_ID}/network`,
    marker: H('Corroboration Network'),
    settleMs: 600,
  },
  {
    id: '22-narratives',
    path: `/cases/${CASE_ID}/narratives`,
    marker: H('Narrative Landscape'),
    content: T('Gate narrative cluster'),
  },
  {
    id: '23-monitoring',
    path: '/monitoring',
    marker: H('Active Monitoring'),
    content: T('Gate Watch Case'),
  },
  {
    id: '24-ai-info',
    path: '/ai-info',
    marker: H('AI Integration'),
  },
];

test.describe('F16 core screens', () => {
  for (const cell of cells) {
    test(`${cell.id} renders`, async ({ page }, testInfo) => {
      if (cell.expectedFailure) test.fail(true, cell.expectedFailure);

      const hygiene = attachPageHygiene(page);
      const session = await installApiMock(page);

      await page.goto(cell.path);
      await expect(page.locator('main#shell-main')).toBeVisible();
      if (cell.expectedFailure) {
        // The gate still records what the browser actually shows for a cell that
        // is expected to fail, so the defect has visible evidence.
        await captureCell(page, testInfo.project.name, `${cell.id}-observed`);
      }
      await expect(cell.marker(page).first()).toBeVisible();
      if (cell.content) {
        await expect(cell.content(page).first()).toBeVisible();
      }
      if (cell.settleMs) await page.waitForTimeout(cell.settleMs);

      hygiene.assertClean(cell.id);
      const overflow = await assertNoHorizontalOverflow(page, cell.id);
      await captureCell(page, testInfo.project.name, cell.id);
      recordCell({
        cell: cell.id,
        project: testInfo.project.name,
        suite: 'screens',
        marker: cell.expectedFailure
          ? `MISSING — ${cell.expectedFailure}`
          : `screen marker + recorded content rendered`,
        overflow,
        transportStatusLines: hygiene.transportStatusLines,
        appConsoleErrors: hygiene.consoleErrors,
        pageErrors: hygiene.pageErrors,
      });

      // Request audit: same-origin only, read-only on screen renders.
      expect(session.audit.every((entry) => entry.method === 'GET')).toBe(true);
      assertNoForeignNetwork(session, cell.id);
    });
  }
});
