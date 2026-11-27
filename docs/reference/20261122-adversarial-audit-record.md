# Adversarial audit and remediation record

Date: 2026-11-22. Baseline: `d589359231e3d20c66a1349b0e8cf476fbe55ab1`.
Status: remediation implemented in the working tree, not committed. D01
(historical-data recovery) and production deployment remain separate owner gates
and were **not** started. No production database, `data/`, `.env`, `logs/` or
`config.toml` write was performed by this audit.

The observation-only discovery report and its supporting inventories are scratch
evidence under `/tmp/triangulate-audit-d589359/` and are not durable repository
artifacts. This record captures the verified conclusions and the implemented
changes.

## Scope and measured state

- 308 tracked files; 131 runtime code files and 41,877 physical LOC; 63 test /
  support files and 27,468 LOC (definitions in the scratch structure report).
- 47 runtime files exceed 300 lines and 23 exceed 500; this is a size flag, not a
  claim that every long file is badly structured. `src/cases/service.py` remains
  the largest at 4,744 lines.
- All 59 direct dependency declarations were inventoried; public registry metadata
  was checked for all of them. Newer releases are not treated as vulnerabilities
  or automatic upgrade instructions.
- No current coverage percentage exists. The measured test/source physical-line
  ratio is 0.656, which is not statement or branch coverage.

## Verified defects fixed

| Defect | Evidence before fix | Change |
|---|---|---|
| Evaluation GET wrote domain state | `src/http/app.py` GET called `get_case_evaluation_summary`, which called `evaluate_case` and committed an `EvaluationRun`/audit/owner change | Reader now returns `{"latest": None, "history": []}` (`src/cases/service.py:4397-4442`); DTO/mapper/TS allow null; explicit CLI evaluation unchanged |
| `init-db` did not apply migrations despite operator docs | command called only `init_database` (ORM `create_all`) | now calls `run_migrations(db.db_path)` on the same path (`src/cli/main.py:136-143`) |
| Timeline labelled every non-contested event “Confirmed” | binary branch in `TimelineTab.tsx` | explicit status table covering confirmed/probable/alleged/contested/debunked/unknown plus neutral fallback (`frontend/src/pages/tabs/TimelineTab.tsx:17-38`) |
| Graph click truncated hyphenated IDs | `node.id.split('-')` kept two pieces | `parseNodeId` splits only the first delimiter and validates type (`frontend/src/components/data-visualization/node-id.ts:10-22`) |
| Corroboration query failure looked like empty success | `const error = null` made the error branch unreachable | real error states, retry, distinct unavailable/empty states (`frontend/src/pages/CorroborationNetwork.tsx:17-68,123-142`) |
| Source timestamp update leaked sessions/swallowed without rollback | caller-owned session never closed; broad catch logged only | rollback on failure and close in `finally` (`src/ingester/polling_fetcher.py:93-134`) |
| CLI hard failures returned success | ingest/process/process-url printed and returned | nonzero `typer.Exit(1)` for hard failures and partial queue failures; healthy-empty remains success |
| Default test selection could invoke a live workflow from inherited credentials | unmarked async `test_*` helper | renamed to non-test `run_current_workflow`; collection-safety test added (`tests/integration/test_langgraph_demo.py:79,626`) |
| Three POST routes accepted arbitrary vocabularies and leaked service `ValueError` as 500 | plain string request models; no route-level mapping | validators for decision/action/annotation vocabularies and non-blank fields; POST-only `ValueError`→404/422 helper (`src/http/schemas.py:256+`, `src/http/app.py:153-166`); conflicts still 409 |
| Static fixture parse failure skipped the `/api` fallback | `return response.json()` was not awaited inside the try/catch | `await response.json()` (`frontend/src/services/api.ts:70`), regression-tested with a 200 HTML response |
| Trafilatura primary title extraction used nonexistent `Metadata` | `trafilatura.metadata.Metadata` is absent in pinned 2.0.0 | `extract_metadata(..., default_url=url)` and primary failure now falls back to BeautifulSoup (`src/ingester/url_capture.py:15-46`) |
| Geocoder retry was defeated by `lru_cache` | retry slept, then re-read the cached `None` | normalized cache key + uncached retry attempt (`src/ai/baseline_workflow.py:38-104`) |
| Static monitoring summary path had no `.json` | generic prefix swap | explicit `/data/monitoring/summary.json` mapping |

These last three were found while adding boundary tests, not in the original
inventory; they were fixed rather than documented as accepted behavior.

## Documentation reconciliation

- `docs/reference/http-api.md` now lists the full registered surface (28 GET + 3
  narrow POST routes), including nullable evaluation, 404/422/409/503 semantics,
  report downloads and the read-only inspection vs narrow review-write boundary.
- `docs/reference/cli.md` lists every registered command, including
  workflow/owner/interrupt/evaluate and osint ingest/stream, plus the initializer
  and rebuild-search semantics.
- Architecture/README/roadmap/specification text no longer claims “no mutation
  endpoints” without qualification. The three review/exception/annotation POSTs
  are documented as the only HTTP write surface; CLI/service remains the boundary
  for creation, ingestion, reruns and execution. No authentication or
  authorization is claimed.
- Release C status statements now distinguish preserved pre-push history from the
  later pushed state. The completion map and release-B handoff were moved to
  `docs/archive/` and inbound links updated.
- H1 evidence claims now state that browser/bundle artifacts are no longer
  available; surviving raw JSON/log artifacts and one screenshot are ephemeral
  `/tmp` evidence.
- H3 is documented accurately: static fixtures remain the dev default, a dev-only
  warning names the remedy, and a missing/non-JSON fixture falls through to the
  same-origin `/api` path.
- H2 evidence added: the B03 fixture journey passed in Chromium, Firefox and a
  390×844 Chromium viewport. WebKit/Safari and a search load test remain
  **not proven**. H5 was observed but deliberately not stopped.

## Verification actually performed

- Backend, disposable copy with sanitized environment and temporary database:
  `739 passed, 9 deselected` (756.20s); Ruff over `src tests scripts`: clean.
- Frontend: `npm run check` exit 0; `194 tests / 18 files` passed.
- B03 browser fixture journey (mocked APIs, Vite-only):
  Chromium 10/10; Firefox 10/10; Chromium 390×844 10/10.
- WebKit install downloaded but the host lacks `libavif16`; no WebKit/Safari run
  was performed. No load test was performed.

No application tests were run against the live checkout database. The nine
deselected tests remain the integration-marked set.

## Residual risks and unproven items

- D01 historical data: row counts and split tables remain historical claims; no
  backup, reconciliation, mapping, rehearsal or production write was performed.
- Deployment: FTS5 capability, migration 15 and per-case search rebuild are not
  verified in any deployed runtime; this record does not authorize deployment.
- WebKit/Safari, real mobile devices, real network providers, live LLM quality,
  multi-worker races and search load behavior are not proven.
- No current line/branch coverage percentage exists.
- POST not-found detection still depends on service message shape (` not found`);
  a typed exception would be more robust. Allowed vocabularies exist in both the
  request schemas and service checks and could drift.
- Pre-existing analyzer-only type issues remain in
  `tests/integration/test_langgraph_demo.py` (demo return types and compiled graph
  typing); default gates are green.
- The working tree is uncommitted; no commit or push was performed. An owner
  still needs to review and decide on committing these changes.
