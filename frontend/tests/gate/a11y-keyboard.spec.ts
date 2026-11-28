import { test, expect, type Page } from '@playwright/test';
import { CASE_ID, assertNoForeignNetwork, installApiMock } from './support/mock-api';
import {
  assertNoHorizontalOverflow,
  attachPageHygiene,
  captureCell,
  recordCell,
} from './support/page-hygiene';

/**
 * F16 — keyboard, focus and 200 % zoom (contracts §2).
 *
 * Proven here (375, 768 and 1280): the skip link is the first Tab stop and moves focus
 * into `main`; the grouped case navigation is native links with exactly one
 * `aria-current="page"`, no ARIA tablist, and is operable from the keyboard.
 *
 * Proven here (1280, zoomed): the 200 % approximation (640×400 CSS px at
 * deviceScaleFactor 2) keeps the trust-boundary caveat visible and adds no
 * document-level horizontal overflow.
 */

const A11Y_PROJECTS = [
  'chromium-375x812',
  'chromium-768x1024',
  'chromium-1280x800',
  // Safari-class engine: WebKit's focus handling differs from Chromium's, so the
  // keyboard assertions are proven there too rather than assumed.
  'webkit-1280x800',
  'webkit-375x812',
];

async function openCase(page: Page) {
  await page.goto(`/cases/${CASE_ID}`);
  await expect(page.getByRole('heading', { name: 'Case Information' })).toBeVisible();
}

test.describe('F16 keyboard and focus', () => {
  test('skip link is the first Tab stop and Enter moves focus into main', async (
    { page },
    testInfo
  ) => {
    test.skip(
      !A11Y_PROJECTS.includes(testInfo.project.name),
      'keyboard assertions are recorded at every gate viewport'
    );
    const hygiene = attachPageHygiene(page);
    await installApiMock(page);
    await openCase(page);

    await page.keyboard.press('Tab');
    const firstStop = await page.evaluate(() => {
      const active = document.activeElement as HTMLElement | null;
      return {
        text: active?.textContent?.trim() ?? '',
        isSkipLink: active?.classList.contains('shell-skip-link') ?? false,
        href: active?.getAttribute('href') ?? '',
      };
    });
    expect(firstStop.isSkipLink, 'first Tab stop is the skip link').toBe(true);
    expect(firstStop.text).toBe('Skip to main content');
    expect(firstStop.href).toBe('#shell-main');

    await page.keyboard.press('Enter');
    await expect
      .poll(() => page.evaluate(() => document.activeElement?.id ?? ''))
      .toBe('shell-main');

    hygiene.assertClean('a11y-skip-link');
    const overflow = await assertNoHorizontalOverflow(page, 'a11y-skip-link');
    await captureCell(page, testInfo.project.name, 'a11y-skip-link');
    recordCell({
      cell: 'a11y-skip-link',
      project: testInfo.project.name,
      suite: 'a11y',
      marker: 'first Tab stop = "Skip to main content"; Enter focuses #shell-main',
      overflow,
      transportStatusLines: hygiene.transportStatusLines,
      appConsoleErrors: hygiene.consoleErrors,
      pageErrors: hygiene.pageErrors,
    });
  });

  test('case navigation is keyboard-operable with one aria-current and no tablist', async (
    { page },
    testInfo
  ) => {
    test.skip(
      !A11Y_PROJECTS.includes(testInfo.project.name),
      'keyboard assertions are recorded at every gate viewport'
    );
    const hygiene = attachPageHygiene(page);
    const session = await installApiMock(page);
    await openCase(page);

    const nav = page.locator('nav.case-tabs-nav');
    await expect(nav).toBeVisible();
    await expect(nav.locator('[aria-current="page"]')).toHaveCount(1);
    await expect(nav.locator('[aria-current="page"]')).toHaveAttribute('data-view', 'overview');
    await expect(nav.locator('[role="tablist"], [role="tab"]')).toHaveCount(0);
    await expect(nav.locator('a[href]')).toHaveCount(16);

    // Keyboard operation: focus the Claims link and activate it with Enter.
    const claimsLink = nav.locator('a[data-view="claims"]');
    await claimsLink.focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(new RegExp(`/cases/${CASE_ID}/claims$`));
    await expect(nav.locator('[aria-current="page"]')).toHaveCount(1);
    await expect(nav.locator('[aria-current="page"]')).toHaveAttribute('data-view', 'claims');
    await expect(nav.locator('[role="tablist"], [role="tab"]')).toHaveCount(0);

    // The boundary caveat stays readable on the case workspace.
    await expect(page.getByText(/Local, trusted, unauthenticated boundary/)).toBeVisible();

    hygiene.assertClean('a11y-case-nav');
    const overflow = await assertNoHorizontalOverflow(page, 'a11y-case-nav');
    await captureCell(page, testInfo.project.name, 'a11y-case-nav');
    recordCell({
      cell: 'a11y-case-nav',
      project: testInfo.project.name,
      suite: 'a11y',
      marker: 'one aria-current="page"; no role=tablist; 16 native case links; Enter navigates',
      overflow,
      transportStatusLines: hygiene.transportStatusLines,
      appConsoleErrors: hygiene.consoleErrors,
      pageErrors: hygiene.pageErrors,
    });
    expect(session.audit.every((entry) => entry.method === 'GET')).toBe(true);
    assertNoForeignNetwork(session, 'a11y-case-nav');
  });
});

test.describe('F16 200% zoom approximation', () => {
  test.use({ viewport: { width: 640, height: 400 }, deviceScaleFactor: 2 });

  test('zoomed case workspace keeps the boundary caveat and stays inside the viewport', async (
    { page },
    testInfo
  ) => {
    test.skip(
      testInfo.project.name !== 'chromium-1280x800',
      'the zoom approximation is measured once, on the 1280 project'
    );
    const hygiene = attachPageHygiene(page);
    await installApiMock(page);
    await openCase(page);

    await expect(page.getByText(/Local, trusted, unauthenticated boundary/)).toBeVisible();
    await expect(page.getByText(/Do not expose it to untrusted networks/)).toBeVisible();

    // The case navigation is still operable at the zoomed width.
    await expect(page.locator('nav.case-tabs-nav')).toBeVisible();

    hygiene.assertClean('a11y-zoom-200');
    const overflow = await assertNoHorizontalOverflow(page, 'a11y-zoom-200');
    await captureCell(page, testInfo.project.name, 'a11y-zoom-200');
    recordCell({
      cell: 'a11y-zoom-200',
      project: testInfo.project.name,
      suite: 'a11y',
      marker: 'boundary caveat visible at 640x400 CSS px (200% approximation)',
      overflow,
      transportStatusLines: hygiene.transportStatusLines,
      appConsoleErrors: hygiene.consoleErrors,
      pageErrors: hygiene.pageErrors,
    });
  });
});
