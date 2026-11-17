import { test, expect, type Page } from '@playwright/test';

/**
 * Bounded B03 browser checks against the Vite-only dev server.
 *
 * Every /api/** request is fulfilled by a mock; unknown API paths return 404 so
 * nothing can reach a real backend or the Vite `/api` proxy. External font
 * requests are fulfilled with empty bodies.
 */

const claimsFor = (prefix: string) => [
  {
    id: `${prefix}-claim-1`,
    text: `${prefix} claim text`,
    verificationStatus: 'confirmed',
    type: 'fact',
    controversyScore: null,
    supportCount: 1,
    opposeCount: 0,
    sourceDiversityCount: 1,
    claimSignature: `${prefix}-claim-1`,
    narrativeClusterId: null,
    evidence: [],
  },
];

const evidenceFor = (prefix: string) => [
  {
    id: `${prefix}-ev-1`,
    title: `${prefix} evidence item`,
    originUrl: 'https://example.com/a',
    canonicalUrl: 'https://example.com/a',
    publisher: 'Example Publisher',
    sourceType: 'rss',
    verificationStatus: 'confirmed',
    credibilityTier: 'high',
    requiresHumanReview: false,
    linkedClaims: [`${prefix}-claim-1`],
    verificationChecks: [],
  },
];

type CaseFixture = { query: string; stage: string; status: string; evidence?: unknown[] };

const fixtures: Record<string, CaseFixture> = {
  caseAlpha: { query: 'Case Alpha', stage: 'INVESTIGATE', status: 'investigating' },
  caseBeta: { query: 'Case Beta', stage: 'TRIAGE', status: 'review ready' },
  caseEmpty: { query: 'Case Empty', stage: 'RETRIEVE', status: 'monitoring', evidence: [] },
};

const caseSummary = (id: string) => {
  const fixture = fixtures[id] ?? { query: `Case ${id}`, stage: 'BOOTSTRAP', status: 'discovering' };
  return {
    id,
    query: fixture.query,
    conflictDomain: 'Water',
    status: fixture.status,
    stage: fixture.stage,
    counts: { articles: 2, events: 1, reviewItems: 0 },
    automationMode: 'safe',
    hasNewMaterial: false,
    openExceptionsCount: 0,
    lastUpdated: '2026-03-19T10:00:00Z',
    reportPath: null,
  };
};

const caseDetail = (id: string) => {
  const fixture = fixtures[id] ?? { query: `Case ${id}`, stage: 'BOOTSTRAP', status: 'discovering' };
  const prefix = id;
  return {
    case: caseSummary(id),
    tabs: {
      claims: claimsFor(prefix),
      evidence: fixture.evidence ?? evidenceFor(prefix),
      exceptions: [],
      parties: [],
      timeline: [],
      runHistory: [],
      narratives: [],
      report: { status: 'pending', markdownPath: null, markdownContent: null, manifestPath: null },
    },
  };
};

type MockOptions = {
  cases?: string[];
  caseStatus?: Record<string, number>;
  evidenceStatus?: Record<string, number>;
  partiesStatus?: Record<string, number>;
  runHistory?: unknown[];
};

const json = (route: Parameters<Parameters<Page['route']>[1]>[0], status: number, body: unknown) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

const handler = (route: Parameters<Parameters<Page['route']>[1]>[0]) => {
  const url = new URL(route.request().url());
  const match = url.pathname.match(/^\/api\/cases\/([^/]+)(?:\/([^/]+)(?:\/([^/]+))?)?$/);
  return match;
};

const installMocks = async (page: Page, options: MockOptions = {}) => {
  const seen: string[] = [];
  page.on('request', (request) => seen.push(request.url()));

  await page.route('https://fonts.googleapis.com/**', (route) =>
    route.fulfill({ status: 200, contentType: 'text/css', body: '/* blocked in test */' })
  );
  await page.route('https://fonts.gstatic.com/**', (route) =>
    route.fulfill({ status: 200, contentType: 'font/woff2', body: '' })
  );

  // Catch-all first (last registered route wins in Playwright): unknown API paths 404.
  await page.route(/\/api\/.*/, (route) =>
    json(route, 404, { detail: 'unmocked api path' })
  );

  await page.route(/\/api\/cases$/, (route) =>
    json(route, 200, (options.cases ?? ['caseAlpha', 'caseBeta']).map(caseSummary))
  );

  await page.route(/\/api\/cases\/[^/]+(\/(claims\/overview|evidence|parties|timeline|run-history|exceptions|report))?$/, (route) => {
    const match = handler(route);
    if (!match) return json(route, 404, { detail: 'unmocked' });

    const [, caseId] = match;
    // One-level endpoints give match[2] only (match[3] undefined); nested ones
    // (claims/overview) give both. Normalize so an empty endpoint is the only
    // case-detail request.
    const endpoint = [match[2], match[3]].filter(Boolean).join('/');

    const status = options.caseStatus?.[caseId] ?? 200;
    if (status !== 200) return json(route, status, { detail: 'case backend down' });

    if (endpoint === '') return json(route, 200, caseDetail(caseId));

    switch (endpoint) {
      case 'claims/overview':
        return json(route, 200, { claims: claimsFor(caseId), narratives: [] });
      case 'evidence': {
        const evidenceStatus = options.evidenceStatus?.[caseId] ?? 200;
        if (evidenceStatus !== 200) return json(route, evidenceStatus, { detail: 'evidence backend down' });
        const fixture = fixtures[caseId];
        return json(route, 200, fixture?.evidence ?? evidenceFor(caseId));
      }
      case 'parties': {
        const partiesStatus = options.partiesStatus?.[caseId] ?? 200;
        if (partiesStatus !== 200) return json(route, partiesStatus, { detail: 'parties backend down' });
        return json(route, 200, []);
      }
      case 'timeline':
        return json(route, 200, []);
      case 'run-history':
        return json(route, 200, options.runHistory ?? []);
      case 'exceptions':
        return json(route, 200, []);
      case 'report':
        return json(route, 200, {
          status: 'pending',
          markdownPath: null,
          markdownContent: null,
          manifestPath: null,
        });
      default:
        return json(route, 404, { detail: 'unmocked' });
    }
  });

  return seen;
};

const assertSameOrigin = (seen: string[]) => {
  expect(
    seen.every(
      (url) => url.startsWith('http://127.0.0.1:5183/') || url.startsWith('https://fonts.')
    )
  ).toBe(true);
  expect(seen.some((url) => url.includes(':8000'))).toBe(false);
};

test('monitoring shows only recorded state and styled, keyboard-operable controls', async ({ page }) => {
  const seen = await installMocks(page, { cases: [] });
  await page.goto('/monitoring');

  await expect(page.getByText('No monitoring cases recorded')).toBeVisible();
  await expect(page.getByText('98%')).toHaveCount(0);
  await expect(page.getByText('1.2s')).toHaveCount(0);
  await expect(page.getByText(/15 new articles found/)).toHaveCount(0);
  await expect(page.getByText('Not provided by the API').first()).toBeVisible();

  const newMonitor = page.getByRole('button', { name: 'New Monitor' });
  await expect(newMonitor).toBeDisabled();

  const primary = await newMonitor.evaluate((el) => {
    const style = getComputedStyle(el);
    return { backgroundColor: style.backgroundColor, padding: style.padding };
  });
  expect(primary.backgroundColor).toBe('rgb(0, 212, 255)');
  expect(primary.padding).toBe('8px 16px');

  await page.keyboard.press('Tab');
  for (let i = 0; i < 12; i += 1) {
    const id = await page.evaluate(() => document.activeElement?.id ?? '');
    if (id === 'monitoring-tab-alerts') break;
    await page.keyboard.press('Tab');
  }
  expect(await page.evaluate(() => document.activeElement?.id)).toBe('monitoring-tab-alerts');

  const focusStyle = await page.evaluate(() => {
    const style = getComputedStyle(document.activeElement as Element);
    return { outlineWidth: style.outlineWidth, outlineStyle: style.outlineStyle };
  });
  expect(focusStyle.outlineStyle).toBe('solid');
  expect(focusStyle.outlineWidth).toBe('2px');

  await page.keyboard.press('Enter');
  await expect(page.getByRole('tab', { name: 'Alerts' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByText(/exposes no alert feed/i)).toBeVisible();

  assertSameOrigin(seen);
});

test('monitoring failure shows a retryable error and recovers', async ({ page }) => {
  // The app retries once (QueryClient retry: 1), so every automatic attempt must
  // fail until the error UI has actually rendered.
  let failing = true;
  let serverAttempts = 0;
  const seen: string[] = [];
  page.on('request', (request) => seen.push(request.url()));

  await page.route('https://fonts.googleapis.com/**', (route) =>
    route.fulfill({ status: 200, contentType: 'text/css', body: '' })
  );
  await page.route(/\/api\/.*/, (route) => json(route, 404, { detail: 'unmocked' }));
  await page.route(/\/api\/cases$/, (route) => {
    serverAttempts += 1;
    if (failing) return json(route, 500, { detail: 'boom' });
    return json(route, 200, []);
  });

  await page.goto('/monitoring');

  const alert = page.getByRole('alert');
  await expect(alert).toContainText('Failed to load monitoring cases');
  await expect(page.getByText('No monitoring cases recorded')).toHaveCount(0);
  expect(serverAttempts).toBeGreaterThanOrEqual(2);

  const metricValue = (label: string) =>
    page.locator('.monitoring-stat-label', { hasText: label }).locator('xpath=following-sibling::*[1]');
  await expect(metricValue('Monitoring Cases')).toHaveText('—');
  await expect(metricValue('Cases With Recorded Update')).toHaveText('—');
  await expect(metricValue('Most Recent Valid Recorded Update')).toHaveText('—');
  await expect(page.getByText('Never recorded')).toHaveCount(0);

  failing = false;
  await page.getByRole('button', { name: 'Retry' }).click();
  await expect(page.getByText('No monitoring cases recorded')).toBeVisible();
  await expect(alert).toHaveCount(0);
  await expect(metricValue('Monitoring Cases')).toHaveText('0');
  await expect(metricValue('Most Recent Valid Recorded Update')).toHaveText('Never recorded');

  assertSameOrigin(seen);
});

test('pipeline monitor never fabricates log lines', async ({ page }) => {
  await installMocks(page);
  await page.goto('/cases/caseAlpha/pipeline');

  await expect(page.getByText(/INVESTIGATE — last recorded case stage/)).toBeVisible();
  await expect(page.getByText(/not a log or event stream/i)).toBeVisible();
  await expect(page.getByText(/No stage attempts are recorded/i)).toBeVisible();
  await expect(page.getByText(/Found 47 articles/)).toHaveCount(0);
  await expect(page.getByText('Total Stages')).toHaveCount(0);

  // Scope execution-state assertions to the stage nodes themselves; the page has
  // a legitimate 'Succeeded' metric *label*, which is not an execution claim.
  await expect(page.getByRole('button', { name: /^Stage .+: Succeeded/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /^Stage .+: Running/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /^Stage .+: Unrecorded/ })).toHaveCount(7);
  await expect(page.locator('.pipeline-flow-node--success')).toHaveCount(0);
  await expect(page.locator('.pipeline-flow-node--running')).toHaveCount(0);
});

test('case detail failure is visible with retry instead of a blank panel', async ({ page }) => {
  await installMocks(page, { caseStatus: { caseAlpha: 500 } });
  await page.goto('/cases/caseAlpha');

  const alert = page.getByRole('alert');
  await expect(alert).toContainText('Failed to load case');
  await expect(alert).toContainText('case backend down');
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Back to Cases/i })).toBeVisible();
});

test('source analysis shows a distinct empty state', async ({ page }) => {
  await installMocks(page);
  await page.goto('/cases/caseEmpty/sources');

  await expect(page.getByText('No evidence records')).toBeVisible();
  await expect(page.getByText('Evidence Items', { exact: true })).toHaveCount(0);
});

test('source analysis error retries to recovery', async ({ page }) => {
  // Mutable so the same mock router can fail, then succeed, around the real Retry.
  const options: MockOptions = { cases: ['caseAlpha'], evidenceStatus: { caseAlpha: 500 } };
  await installMocks(page, options);
  await page.goto('/cases/caseAlpha/sources');

  const alert = page.getByRole('alert');
  await expect(alert).toContainText('Failed to load source data');
  await expect(page.getByText('Evidence Items', { exact: true })).toHaveCount(0);

  options.evidenceStatus = {};
  await page.getByRole('button', { name: 'Retry' }).click();

  await expect(page.getByText('Evidence Items', { exact: true })).toBeVisible();
  await expect(alert).toHaveCount(0);
  await expect(page.getByText('caseAlpha evidence item')).toHaveCount(0);
});

test('narrative landscape shows a distinct empty state', async ({ page }) => {
  await installMocks(page);
  await page.goto('/cases/caseAlpha/narratives');

  await expect(page.getByText(/No narrative clusters have been persisted/i)).toBeVisible();
  await expect(page.getByText('Origin Narrative')).toHaveCount(0);
});

test('narrative landscape error retries to recovery', async ({ page }) => {
  const options: MockOptions = { cases: ['caseBeta'], partiesStatus: { caseBeta: 500 } };
  await installMocks(page, options);
  await page.goto('/cases/caseBeta/narratives');

  const alert = page.getByRole('alert');
  await expect(alert).toContainText('parties backend down');
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();

  options.partiesStatus = {};
  await page.getByRole('button', { name: 'Retry' }).click();

  await expect(alert).toHaveCount(0);
  await expect(page.getByText(/No narrative clusters have been persisted/i)).toBeVisible();
});

test('claims and evidence tabs navigate with a URL claim filter', async ({ page }) => {
  const seen = await installMocks(page);
  await page.goto('/cases/caseAlpha');

  await page.getByRole('button', { name: 'Evidence', exact: true }).click();
  await expect(page.getByText('caseAlpha evidence item', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Claims', exact: true }).click();
  await expect(page.getByText('caseAlpha claim text', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Inspect Evidence', exact: true }).click();
  await expect(page).toHaveURL(/\/cases\/caseAlpha\/evidence\?claim=caseAlpha-claim-1$/);
  await expect(page.getByText(/Filtered to evidence linked to claim/i)).toBeVisible();
  await expect(page.getByText('caseAlpha evidence item', { exact: true })).toBeVisible();
  assertSameOrigin(seen);
});

test('case switch via the real UI never shows the previous case', async ({ page }) => {
  const seen = await installMocks(page, { cases: ['caseAlpha', 'caseBeta'] });

  await page.goto('/cases');
  await page.locator('.case-card', { hasText: 'Case Alpha' }).click();
  await page.getByRole('button', { name: 'Claims', exact: true }).click();
  await expect(page.getByText('caseAlpha claim text', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Evidence', exact: true }).click();
  await expect(page.getByText('caseAlpha evidence item', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Back', exact: true }).click();
  await expect(page).toHaveURL(/\/cases$/);

  await page.locator('.case-card', { hasText: 'Case Beta' }).click();
  await page.getByRole('button', { name: 'Claims', exact: true }).click();
  await expect(page.getByText('caseBeta claim text', { exact: true })).toBeVisible();
  await expect(page.getByText('caseAlpha claim text', { exact: true })).toHaveCount(0);

  await page.getByRole('button', { name: 'Evidence', exact: true }).click();
  await expect(page.getByText('caseBeta evidence item', { exact: true })).toBeVisible();
  await expect(page.getByText('caseAlpha evidence item', { exact: true })).toHaveCount(0);
  assertSameOrigin(seen);
});
