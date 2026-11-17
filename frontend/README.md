# Frontend

This directory contains the React frontend for browsing persisted cases and operator outputs against the read-only Triangulate HTTP API.

## Stack

- React 19
- TypeScript
- Vite
- React Router

## Runtime baseline

- Node.js 24.13.0 and npm 11.6.2 are the current tested baseline. The supported Node range is declared in `package.json` `engines` (`^20.19.0 || ^22.12.0 || >=24.0.0`); `.nvmrc` records the tested Node version.
- npm 10 or newer is supported. Use `npm ci` for a reproducible install from `package-lock.json`; do not use `--force` or `--legacy-peer-deps` to bypass peer resolution.
- The lockfile includes the platform-native esbuild and Rollup optional packages needed by a clean install.

## Scripts

```bash
npm ci
npm run dev
npm run check
npm test -- --run
npm test -- --run --coverage
npm run preview
```

## API Integration

- The client reads `VITE_API_BASE_URL` to locate the backend.
- API helpers live in `src/services/api.ts`.
- Shared backend-facing types live in `src/types/backend-models.ts`.
- The frontend must not initiate pipeline mutations; operators use the CLI or background workers for that.
- `npm run check` runs lint, typecheck and the production build. Tests run with Vitest in non-watch mode via `npm test -- --run`; coverage uses the matching `@vitest/coverage-v8` provider.

## Mocked browser verification

```bash
PLAYWRIGHT_HTML_OPEN=never npx playwright test --config=playwright.b03.config.ts
```

This bounded suite starts **only Vite** on `127.0.0.1:5183`, intercepts all API
requests and external fonts, and writes artifacts under
`/tmp/triangulate-b03-playwright/artifacts`. It requires installed Google Chrome;
it does not download a browser or launch FastAPI. Do not substitute the default
Playwright config or `scripts/dev-with-api.sh` for frontend-only verification:
those start a backend and require a separately approved scratch runtime.

B03 parent verification: `npm run check`, 72 component tests and 10 mocked browser
tests passed. These checks do not exercise live ingestion or certify source
independence. See [read-only UI architecture](../docs/architecture/20261115-read-only-ui-states.md).

## Current Routes

- `/`: case index
- `/cases/new`: CLI launch guidance
- `/cases/:id/*`: case detail views

## Notes

- This is no longer a stock Vite template; keep this README focused on project-specific behavior.
- Remove template-only assets and references when they are not used by the app.
