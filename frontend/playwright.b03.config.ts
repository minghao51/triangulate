import { defineConfig, devices } from '@playwright/test';

/**
 * Bounded B03 browser checks.
 *
 * Safe by construction: it only starts the Vite dev server (no FastAPI, no
 * `dev-with-api.sh`) and every `/api/**` request is mocked inside the tests.
 * Artifacts are written outside the checkout.
 */
export default defineConfig({
  testDir: './tests/b03',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  outputDir: '/tmp/triangulate-b03-playwright/artifacts',
  use: {
    baseURL: 'http://127.0.0.1:5183',
    trace: 'off',
    video: 'off',
    screenshot: 'off',
  },
  projects: [
    {
      name: 'chrome',
      // Use the installed Chrome channel so no browser download is needed.
      use: { ...devices['Desktop Chrome'], channel: 'chrome' },
    },
  ],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5183 --strictPort',
    url: 'http://127.0.0.1:5183',
    reuseExistingServer: false,
    timeout: 60_000,
    env: {
      // Empty base URL keeps the app on same-origin /api paths, all of which are
      // intercepted below; it never reaches the Vite proxy target.
      VITE_API_BASE_URL: '',
    },
  },
});
