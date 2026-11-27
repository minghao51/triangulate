import { test, expect } from '@playwright/test';
import { installApiMock } from './support/mock-api';
import { assertNoHorizontalOverflow, attachPageHygiene, captureCell } from './support/page-hygiene';

/**
 * F21 — optional extended-history bundle (X01 + X02) browser evidence.
 *
 * Runs against the same fully synthetic API as the F16 core gate. Covers the
 * ad-hoc snapshot comparison on the Changes route (X01) and the pinned frozen
 * report on the Report route (X02), including their unavailable/failure states.
 */

const CASE_ID = 'case-gate';
const AD_HOC_URL = `/cases/${CASE_ID}/changes?mode=ad_hoc&baselineSnapshot=snap-gate-0&targetSnapshot=snap-gate-1`;

test.describe('F21 optional history', () => {
  test('ad-hoc comparison shows two explicit observations and their differences', async ({ page }) => {
    const hygiene = attachPageHygiene(page);
    const session = await installApiMock(page);

    await page.goto(AD_HOC_URL);

    const panel = page.locator('[data-mode="ad_hoc"]');
    await expect(panel).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Ad-hoc snapshot comparison' })).toBeVisible();

    // Both observations are named by their own immutable snapshot id.
    await expect(panel.getByText('snap-gate-0', { exact: false }).first()).toBeVisible();
    await expect(panel.getByText('snap-gate-1', { exact: false }).first()).toBeVisible();

    // Recorded items render; the entity id is visible.
    await expect(panel.getByText('cl-gate-1', { exact: false }).first()).toBeVisible();
    // Ad-hoc wording never claims deletion/retraction or an actor.
    await expect(panel).not.toContainText(/deleted|retracted|removed by|caused by/i);

    await assertNoHorizontalOverflow(page, 'optional:ad-hoc');
    await captureCell(page, test.info().project.name, 'optional-ad-hoc');

    // Everything the surface did was a read.
    expect(session.audit.every((entry) => entry.method === 'GET')).toBe(true);
    hygiene.assertClean('optional:ad-hoc');
  });

  test('ad-hoc unavailable renders the recorded reason without a zero-change claim', async ({ page }) => {
    await installApiMock(page, {
      overrides: {
        snapshotComparison: {
          body: {
            mode: 'ad_hoc',
            comparisonPolicyVersion: 'snapshot-comparison-policy-v1',
            baselineSnapshotId: 'snap-gate-0',
            targetSnapshotId: 'snap-gate-1',
            baselineRunId: 'run-gate-0',
            targetRunId: 'run-gate-1',
            baselineCoverage: 'partial',
            targetCoverage: 'partial',
            baselineMetadata: {
              sequence: 1,
              createdAt: '2026-11-01T09:00:00Z',
              schemaVersion: 'case-snapshot-v0',
              identityVersion: 'claim-signature-sha256-v1',
              policyVersion: 'case-history-policy-v1',
            },
            targetMetadata: {
              sequence: 2,
              createdAt: '2026-11-01T10:00:00Z',
              schemaVersion: 'case-snapshot-v1',
              identityVersion: 'claim-signature-sha256-v1',
              policyVersion: 'case-history-policy-v1',
            },
            availability: 'unavailable',
            unavailableReason: 'incompatible_schema',
            items: [],
            total: null,
            limit: 25,
            offset: 0,
            hasMore: false,
          },
        },
      },
    });

    await page.goto(AD_HOC_URL);

    const panel = page.locator('[data-mode="ad_hoc"]');
    await expect(panel).toBeVisible();
    await expect(panel.getByText(/incompatible_schema/).first()).toBeVisible();
    await expect(panel).not.toContainText(/no changes between these observations/i);
    await expect(panel).not.toContainText(/0 changes/i);
    await captureCell(page, test.info().project.name, 'optional-ad-hoc-unavailable');
  });

  test('pinned run lists exactly the recorded report artifacts', async ({ page }) => {
    const hygiene = attachPageHygiene(page);
    const session = await installApiMock(page);

    await page.goto(`/cases/${CASE_ID}/report?reportRun=run-gate-1`);

    const list = page.getByTestId('report-artifact-list');
    await expect(list).toBeVisible();
    await expect(page.getByTestId('report-artifact')).toHaveCount(2);
    await expect(list.getByText('topic_report.md', { exact: true })).toBeVisible();
    await expect(list.getByText('topic_analysis.json', { exact: true })).toBeVisible();

    // Honest checksum labelling: a recorded payload checksum, never file proof.
    await expect(list.getByText('Recorded payload checksum').first()).toBeVisible();
    await expect(list).not.toContainText(/verified file checksum|chain of custody/i);
    // No filesystem path leaks into the descriptor list.
    await expect(list).not.toContainText(/\/tmp\/|\/output\/|\\\\/);

    // Current stays reachable explicitly.
    await expect(page.getByRole('link', { name: /Back to the current report/i })).toBeVisible();

    await assertNoHorizontalOverflow(page, 'optional:pinned-report');
    await captureCell(page, test.info().project.name, 'optional-pinned-report');

    // Only the pinned run's artifact descriptor list was requested.
    const requested = session.audit.map((entry) => entry.path);
    expect(requested).toContain(`/api/cases/${CASE_ID}/investigation-runs/run-gate-1/artifacts`);
    expect(requested.some((path) => /snapshot-comparison/.test(path))).toBe(false);
    hygiene.assertClean('optional:pinned-report');
  });

  test('a missing pinned artifact is a distinct failure with no substitute', async ({ page }) => {
    await installApiMock(page, {
      overrides: {
        runArtifactDownload: { status: 404, body: { detail: 'not found' } },
      },
    });

    await page.goto(`/cases/${CASE_ID}/report?reportRun=run-gate-1`);
    const list = page.getByTestId('report-artifact-list');
    await expect(list).toBeVisible();

    await page
      .getByTestId('report-artifact')
      .first()
      .getByRole('button', { name: /download/i })
      .click();

    const missing = page.getByTestId('report-state-artifact-missing');
    await expect(missing).toBeVisible();
    await expect(missing).not.toContainText(/latest|most recent|nearby run/i);
    // The descriptor list is still exactly the pinned run's artifacts.
    await expect(page.getByTestId('report-artifact')).toHaveCount(2);
    await captureCell(page, test.info().project.name, 'optional-artifact-missing');
  });

  test('unknown pinned run is not substituted with the current report', async ({ page }) => {
    await installApiMock(page, {
      overrides: { runArtifacts: { status: 404, body: { detail: 'not available' } } },
    });

    await page.goto(`/cases/${CASE_ID}/report?reportRun=run-not-recorded`);

    await expect(page.getByTestId('report-state-run-not-recorded')).toBeVisible();
    await expect(page.getByTestId('report-artifact-list')).toHaveCount(0);
    await expect(page.getByTestId('report-content')).toHaveCount(0);
  });
});
