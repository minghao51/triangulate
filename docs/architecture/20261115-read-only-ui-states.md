# Read-only UI states and operational truth

Date: 2026-11-15. Status: B03 implemented and independently accepted.

This supplements the [current architecture](20261114-current-architecture.md)
and [acquisition/checkpoint architecture](20261115-acquisition-outcomes.md).
The website remains a reader. No new mutation endpoint, scheduler, alert service,
source assessment system or evidence inspector is introduced by B03.

## Page boundaries

- **Monitoring:** list cases reported as monitoring, their saved stage/status and
  available timestamps. Schedules, next runs, alert acknowledgement, system
  health and performance telemetry are unavailable from the read API. Unsupported
  operations are disabled with visible CLI guidance, not simulated locally.
- **Pipeline:** display the recorded case-stage pointer separately from saved
  stage attempts. Workflow order is configuration, not proof of completed work.
  Stage outcomes come from recorded attempts; no agent roster/count is invented.
  Unknown history cannot become zero successes/errors. Zero duration is valid;
  non-finite/negative durations are invalid and excluded from averages. With
  multiple attempts, missing/unparseable timestamps or conflicting latest-time
  ties make the latest outcome indeterminate; the conservative UI fallback is
  `Unrecorded`, while raw attempt rows remain available.
- **Sources:** count evidence records and their provided type/publisher/credibility
  labels. Repeated canonical URLs are repeated records, not independent sources.
  Publisher spelling never determines political leaning, geography or accuracy.
  An absent API assessment is not proof that no assessment exists elsewhere.
- **Narratives:** use persisted cluster records and their claim references from
  the claims-overview API, plus provided party/timeline data. No keyword-generated
  clusters, text-substring party positions or verification-as-sentiment score.
- **Case workspace:** query errors and missing/mismatched IDs produce explicit
  reader states with Retry/Back actions rather than a blank detail panel. Article
  counts are labelled articles, not unique sources or independent publishers.

## Query and local-state ownership

React Query keys include the case ID for details, claims and evidence. Slow
responses update their own case cache, not another case's rendered data. Claims
and evidence expansion/filter state lives in components keyed by case. Claim
filters remain in the URL and claim IDs are URI-encoded in navigation links.

The workspace only copies detail into the shared Zustand store when the detail's
case ID matches the route. It clears shared case state on case transitions and
when leaving the workspace. Loading, failed, empty and unavailable reads are
distinct: failed/not-loaded queries must not manufacture healthy zero metrics.

The application still retries failed reads once. Browser fixtures must hold an
error through automatic retries before testing the explicit Retry control; they
must not accidentally recover on the automatic attempt and then wait for an
error that cannot appear.

## Styling and interaction

The shared `Button` uses scoped, actual CSS rather than uncompiled utility class
names. Variants/sizes have explicit padding, colors and focus-visible styling;
disabled/loading states retain native button semantics. Its default type is
`button`, while callers can explicitly choose another native type. Pipeline stage
selectors similarly use labelled native buttons, pressed state and scoped focus
styles. No utility framework or dependency upgrade is required.

## Safe verification boundary

`frontend/playwright.b03.config.ts` starts only Vite on loopback port 5183 and
sets an empty API base URL. Tests fulfill every `/api/**` request, return mocked
404s for unknown API routes and intercept external fonts. Installed Chrome is
used without downloading a browser. Test artifacts are outside the checkout.

```bash
cd frontend
npm run check
npm test -- --run
PLAYWRIGHT_HTML_OPEN=never npx playwright test --config=playwright.b03.config.ts
```

Do **not** substitute the default Playwright config or `dev-with-api.sh`: those
start a backend and are not approved scratch-runtime launchers. These mocked
checks validate frontend behavior, not live ingestion or backend/data recovery.
The [production database incident](../reference/20261115-test-database-incident.md)
remains disclosed; UI tests do not imply restoration.

Final parent verification: **72 component tests, 10 mocked Chrome tests,
`npm run check` and diff checks passed**. The browser suite includes real Retry,
claim-filter navigation and case-switch journeys, plus computed Button color,
padding and keyboard focus. Two accidentally dropped journey tests were restored
by the parent before final verification. Logs:
`/tmp/triangulate-b03-parent-final-{check,tests,browser}.log`.

Independent re-review found no remaining blocker in the corrected code. Active
LSP reported no findings across 11 frontend files, with 6 confirmed clean and 5
inconclusive push-only checks; typecheck/build passed, but no universal LSP-clean
claim is made. These are mocked UI checks, not proof of live backend behavior.
Acceptance and residual gates are recorded in the
[worker plan](../plans/20261114-evidence-workbench-worker-plan.md).
