import { defineConfig, devices } from '@playwright/test';

/**
 * F16 refinement gate — 24 screens × 42 states × 3 viewports, plus critical
 * end-to-end journeys on every installed engine.
 *
 * Safe by construction:
 * - only the Vite dev server is started (no FastAPI, no `dev-with-api.sh`);
 * - `VITE_API_BASE_URL` points at the same Vite origin, so every read is
 *   same-origin AND the bundled static-fixture fallback is disabled;
 * - each spec installs `tests/gate/support/mock-api.ts`, which answers every
 *   `/api/**` request synthetically and 404s unknown paths — nothing can reach a
 *   real backend or port 8000;
 * - external font hosts are blocked;
 * - every artifact (report, screenshots, traces) is written outside the
 *   checkout, under /tmp/refinement-gate.
 */

const PORT = 5189;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const ARTIFACT_ROOT = '/tmp/refinement-gate';

/**
 * WebKit (Safari engine) is part of the gate: `webkit-1280x800` runs the whole
 * gate — the state matrix (`core-screens`, `core-states`, `optional-history`,
 * `a11y-keyboard`) *and* the critical journey — so Safari-class rendering and
 * behaviour is exercised on the same 24 screens and 44 states as Chromium.
 *
 * It needs the host's `libavif16` system library. Where that library is missing
 * the browser cannot launch, so the engine must be recorded as **not proven**
 * rather than silently dropped — opt out explicitly (nothing is downloaded or
 * upgraded here):
 *
 *   REFINEMENT_GATE_WEBKIT=0 npx playwright test --config playwright.refinement.config.ts
 */
const includeWebkit = process.env.REFINEMENT_GATE_WEBKIT !== '0';

/**
 * WebKit projects.
 *
 * `webkit-1280x800` runs the whole gate — the state matrix *and* the critical
 * journey — because WebKit only runs at this one width, so splitting the
 * journey into its own project would duplicate config for no coverage gain.
 *
 * `webkit-375x812` runs the state matrix only (the journey is already proven at
 * 1280×800): Safari-class engines diverge most under a constrained width, where
 * font metrics, flex/grid shrinking and scrollbars decide whether content
 * overflows. 768×1024 is deliberately Chromium-only to bound gate runtime — the
 * tablet width adds no WebKit-specific risk that 375 and 1280 do not already
 * cover.
 */
const webkitUse = (width: number, height: number) => ({
  ...devices['Desktop Safari'],
  viewport: { width, height },
});

const viewportUse = (width: number, height: number) => ({
  ...devices['Desktop Chrome'],
  // The installed Playwright chromium build does not match this release's
  // revision, so the installed Chrome channel is used instead (as in b03).
  channel: 'chrome',
  viewport: { width, height },
});

export default defineConfig({
  testDir: './tests/gate',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [
    ['list'],
    ['json', { outputFile: `${ARTIFACT_ROOT}/report.json` }],
  ],
  outputDir: `${ARTIFACT_ROOT}/artifacts`,
  use: {
    baseURL: BASE_URL,
    trace: 'off',
    video: 'off',
    screenshot: 'off',
  },
  projects: [
    {
      name: 'chromium-375x812',
      use: viewportUse(375, 812),
      testIgnore: /journeys\.spec\.ts/,
    },
    {
      name: 'chromium-768x1024',
      use: viewportUse(768, 1024),
      testIgnore: /journeys\.spec\.ts/,
    },
    {
      name: 'chromium-1280x800',
      use: viewportUse(1280, 800),
      testIgnore: /journeys\.spec\.ts/,
    },
    {
      // Reference run for the journeys, so the same journeys are proven on
      // Chromium as well as on the other installed engines.
      name: 'chromium-journeys',
      use: viewportUse(1280, 800),
      testMatch: /journeys\.spec\.ts/,
    },
    {
      name: 'firefox-journeys',
      use: { ...devices['Desktop Firefox'], viewport: { width: 1280, height: 800 } },
      testMatch: /journeys\.spec\.ts/,
    },
    // Safari-class engine across the whole gate, journey included.
    ...(includeWebkit
      ? [
          { name: 'webkit-1280x800', use: webkitUse(1280, 800) },
          {
            name: 'webkit-375x812',
            use: webkitUse(375, 812),
            testIgnore: /journeys\.spec\.ts/,
          },
        ]
      : []),
  ],
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: BASE_URL,
    reuseExistingServer: false,
    timeout: 60_000,
    env: {
      // Same-origin absolute base: keeps requests on the mocked origin and turns
      // off the bundled static fixtures so these runs are API-only.
      VITE_API_BASE_URL: BASE_URL,
    },
  },
});
