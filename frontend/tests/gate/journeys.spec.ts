import { test, expect } from '@playwright/test';
import {
  CASE_ID,
  assertNoForeignNetwork,
  assertReadOnlyAllowlist,
  installApiMock,
} from './support/mock-api';
import {
  assertNoHorizontalOverflow,
  attachPageHygiene,
  captureCell,
  recordCell,
} from './support/page-hygiene';

/**
 * F16 — critical end-to-end journeys, run on every installed engine.
 *
 * Projects: chromium-journeys (reference), firefox-journeys, webkit-journeys.
 * A missing engine or browser build is recorded as **not proven**; nothing here
 * downloads or upgrades a browser.
 *
 * Journey: dashboard → case overview → claims → evidence → inspector → report.
 */

test.describe('F16 critical journey', () => {
  test('dashboard, case overview, claims, evidence, inspector and report', async (
    { page },
    testInfo
  ) => {
    const hygiene = attachPageHygiene(page);
    const session = await installApiMock(page);
    const engine = testInfo.project.name;

    // 1. Dashboard renders the recorded case list.
    await page.goto('/dashboard');
    await expect(page.getByRole('heading', { name: 'Investigation Dashboard' })).toBeVisible();
    await expect(page.getByText('Gate Case').first()).toBeVisible();

    // 2. Open the case workspace through the UI (no direct URL shortcut).
    await page.goto('/cases');
    await expect(page.getByRole('heading', { name: 'Case Explorer' })).toBeVisible();
    await page.getByText('Gate Case').first().click();
    await expect(page).toHaveURL(new RegExp(`/cases/${CASE_ID}$`));
    await expect(page.getByRole('heading', { name: 'Case Information' })).toBeVisible();

    // 3. Navigate to claims and evidence through the case navigation.
    await page.locator('nav.case-tabs-nav a[data-view="claims"]').click();
    await expect(page).toHaveURL(new RegExp(`/cases/${CASE_ID}/claims$`));
    await expect(page.getByRole('heading', { name: 'Primary Claims Mapping' })).toBeVisible();
    await expect(
      page.getByText(/Gate claim two: a second recorded assertion/).first()
    ).toBeVisible();

    await page.locator('nav.case-tabs-nav a[data-view="evidence"]').click();
    await expect(page).toHaveURL(new RegExp(`/cases/${CASE_ID}/evidence$`));
    await expect(page.getByText('Gate evidence one').first()).toBeVisible();

    // 4. Open the inspector for the evidence item.
    await page.getByRole('button', { name: /Inspect source/ }).first().click();
    await expect(page).toHaveURL(/\/cases\/[^/]+\/evidence\?/);
    await expect(page.getByRole('heading', { name: /inspector/i }).first()).toBeVisible();

    // 5. Open the report through the case navigation.
    await page.locator('nav.case-tabs-nav a[data-view="report"]').click();
    await expect(page).toHaveURL(new RegExp(`/cases/${CASE_ID}/report$`));
    await expect(page.getByRole('heading', { name: 'Final Investigation Report' })).toBeVisible();
    await expect(page.getByText(/Gate Investigation Report/)).toBeVisible();

    // Cross-engine hygiene: no uncaught error, no console.error, no overflow.
    hygiene.assertClean(`journey-${engine}`);
    const overflow = await assertNoHorizontalOverflow(page, `journey-${engine}`);
    assertReadOnlyAllowlist(session.audit);
    assertNoForeignNetwork(session, `journey-${engine}`);
    expect(session.audit.some((entry) => entry.path === '/api/cases')).toBe(true);
    expect(session.audit.some((entry) => entry.path.endsWith('/report'))).toBe(true);

    await captureCell(page, engine, 'journey-report');
    recordCell({
      cell: 'journey-core',
      project: engine,
      suite: 'journeys',
      marker: 'dashboard → case overview → claims → evidence → inspector → report',
      overflow,
      transportStatusLines: hygiene.transportStatusLines,
      appConsoleErrors: hygiene.consoleErrors,
      pageErrors: hygiene.pageErrors,
    });
  });
});
