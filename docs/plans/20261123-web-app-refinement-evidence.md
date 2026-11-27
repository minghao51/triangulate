# Web-app refinement execution evidence (2026-11-23)

Execution record for the 22 refinement cards in
[`20261123-web-app-refinement-handoffs/`](20261123-web-app-refinement-handoffs/). Product
requirements: [specification](20261123-web-app-refinement-specification.md). Shared rules:
[contracts](20261123-web-app-refinement-contracts.md). Hub: [implementation](20261123-web-app-refinement-implementation.md).

This file records **actual** edits and **actual** test runs. It is not approval, not a deployment
record and not evidence of any unrun gate. Counts are today's observations, not frozen totals.

## 1. Verification environment

| Item | Value |
|---|---|
| Baseline HEAD | `git rev-parse HEAD` recorded in §2; no commits made by any task |
| Disposable worktree | `/tmp/triangulate-disposable` (full worktree incl. dirty bytes; no live `data/`, `triangulate.db`, `.env`, `logs/`, `config.toml`) |
| Export manifest | `/tmp/disposable-manifest.txt` — 641 files; `frontend/src/pages/CaseIntelligenceCenter.tsx` bytes match the origin working tree (dirty-byte proof) |
| Python | `uv 0.9.7`, CPython 3.11.14 in the disposable copy, `uv sync --frozen --extra dev` |
| Node | `v24.13.0`, `npm 11.6.2` (matches `frontend/.nvmrc`), fresh `npm ci` in the disposable copy |
| Browsers | Playwright cache has chromium, firefox, webkit builds installed |

### Baseline gates (pristine worktree, before any refinement edit)

- `uv run pytest -q --disable-warnings` in the disposable copy → **739 passed, 9 deselected** (966 s)
- `uv run ruff check src tests scripts --output-format concise` → **clean**
- `npm test -- --run` → **194 passed / 18 files**
- `npm run check` (eslint + tsc + vite build) → **pass**

Known pre-existing failures: none. Pre-existing dirty worktree files were preserved throughout.

## 2. Per-card results

Status vocabulary: **implemented-and-tested** means the card's edits exist and its focused tests ran;
it does not mean the release gate (F16/F21) passed.

### F00 — baseline and fixtures

- Status: implemented-and-tested (steps 1/3 pre-done by the orchestrator; steps 2/4 by the worker)
- Diff: `scripts/v01_e2e_fixture.py` (additive `materialize_refinement_states` +
  `--refinement-variants`; default `materialize()`/manifest unchanged), NEW
  `tests/test_refinement_fixtures.py` (7 tests)
- Gates: `uv run pytest -q tests/test_refinement_fixtures.py tests/test_v01_e2e.py --disable-warnings`
  → 8 passed; `uv run ruff check` on both files → clean; default fixture manifest byte-identical
- Fixture states: missing case; wrong-case claim/evidence targets; invalid (120.5 / 245.0) vs missing
  vs recorded 0,0 coordinates; raw unrecognized timeline status in the frozen report payload; absent
  report; legacy capture
- Notes: an out-of-enum `events.verification_status` makes ORM reads raise `LookupError`, so the raw
  unrecognized status is carried in the frozen report payload; live timeline coordinates are
  serialized after the orchestrator passthrough noted under F13

### F01 — truthful responsive shell

- Status: implemented-and-tested
- Diff: `frontend/src/components/Layout/Shell.tsx`, `Shell.css`, NEW `Shell.test.tsx` (9 tests)
- Removed: "System Online", static notification badge 3, Analyst/Administrator identity
- Added: persistent trust-boundary caveat; truthful data-mode label (`Configured API` vs
  `Static preferred; missing fixtures may use API`); skip link; route breadcrumbs; disclosure menu with
  focus return; route-change focus to `main`; rail/top-bar/stacked breakpoints; no `100vw` overflow
- Gates: `npx vitest run src/components/Layout` → 9 passed; `npx eslint`/`npx tsc --noEmit` clean;
  headless Chromium measurement at 375/768/1280 + 200 % zoom showed no document horizontal overflow

### F02 — case navigation and URL context

- Status: implemented-and-tested
- Diff: `frontend/src/pages/CaseIntelligenceCenter.tsx` (+ test, + CSS), `frontend/src/services/deep-links.ts` (+ test)
- Added: five grouped native-link nav groups with `aria-current="page"` (16 destinations, unchanged
  paths), per-view allowlists (`CASE_VIEW_ALLOWLISTS`), `sanitizeViewUrl`/`buildViewHref`,
  "Unsupported historical view" gate before any fetch with "Open current ⟨view⟩" as the only strip path,
  session memory of the last committed per-view href
- Gates: `npx vitest run src/services/deep-links.test.ts src/pages/CaseIntelligenceCenter.test.tsx`
  → 45 passed; eslint/tsc clean
- Not proven at this card: browser Back behaviour and visual stacking (covered by the F16 browser gate)

### F03 — consistent reader states

- Status: implemented-and-tested
- Diff: NEW `frontend/src/components/design-system/ReaderState.tsx`, NEW
  `.../reader-polling.ts` (hook split required by `react-refresh/only-export-components`), NEW
  `ReaderState.test.tsx`; `MapTab`, `TimelineTab`, `PartiesTab`, `RunHistoryTab` migrated from
  `useEffect` + `.then` to case-keyed React Query; NEW tests for Map/Parties/Run history, `TimelineTab.test.tsx`
  gained only a `QueryClientProvider` wrapper (assertions unchanged)
- Gates: `npx vitest run src/pages/tabs src/components/design-system` → 98 passed; full frontend
  `npx vitest run` → 243 passed / 23 files; eslint/tsc clean
- Behaviour: four shared states textually distinct with `data-state`; late Case A response never
  renders under Case B; per-case cache isolation proven; focus/selection survives refetch; polling
  hook pauses when the document is hidden

### F04 — contextual review and annotations

- Status: implemented-and-tested
- Diff: `frontend/src/pages/CaseIntelligenceCenter.tsx` (+ test), `frontend/src/pages/tabs/ExceptionsTab.tsx`,
  NEW `ExceptionsTab.test.tsx`, `tabs-state.test.tsx`, additive typing in `frontend/src/types/backend-models.ts`
- Behaviour: per-form write states (pending / saved-and-refreshed / 409 / 422 / transport-uncertain /
  stale); `retry: false` on review, annotation and exception mutations; POST-OK + refresh-failed shows
  "Accepted; refresh failed" with GET-only retry; a lost response reconciles by GET, then requires an
  explicit confirmed retry with a duplicate-append warning; case-keyed guards for late responses;
  `latest: null` → "No saved evaluation", score 0 → 0; annotation target picker offers only current-case
  entities (case/claim/evidence/exception/narrative), no free text; review activity partitioned into
  human notes vs technical audit without text/time dedup guessing
- Gates: `npx vitest run src/pages` → 186 passed / 18 files; eslint and `tsc --noEmit` clean

### F06 — claims and evidence browsing

- Status: implemented-and-tested
- Diff: `frontend/src/pages/tabs/ClaimsTab.tsx`/`.css`/NEW test, `EvidenceTab.tsx`/`.css`/NEW test,
  additive `CLAIMS_BROWSE_PARAMS`/`EVIDENCE_BROWSE_PARAMS` in `deep-links.ts` (+ drift guard test)
- Behaviour: dense rows with per-row provenance (model-derived vs legacy/unknown from recorded fields
  only); allowlisted filters/sort over the loaded array with page reset on change; explicit "loaded
  results" paging label, 50 rows/page; stable single selection across re-render/filter; inspect links
  carry the selected IDs; invalid explicit filter shows a field message without broadening results;
  `evidence-filter-empty` distinct from loading/empty/error
- Gates: `npx vitest run src/pages/tabs` → 110 passed / 11 files (14 new tab tests); eslint/tsc clean
- Note: at delivery the evidence list DTO had no publication timestamp, so `publishedAt` sorting treated
  all loaded rows as unknown-date. **Closed in the follow-up pass** (§4): `EvidenceDTO.publishedAt` is
  now exposed and the sort uses it (newest first, unknown last, stable tie-break)

### F14 — report reader and download recovery

- Status: implemented-and-tested
- Diff: `frontend/src/pages/tabs/ReportTab.tsx` (rewritten), `ReportTab.css`, NEW `ReportTab.test.tsx` (14 tests)
- Behaviour: "Pending" only with a recorded `running`/`pending` stage attempt from run history; a missing
  report otherwise renders "Not generated" (no attempt) or "Unavailable" (read failed); read and download
  failures are separate states with separate retries and never regenerate; safe semantic markdown
  renderer (real heading/list/quote elements, no `dangerouslySetInnerHTML`, XSS payload inert as text);
  exactly the two existing download calls; no historical/"latest" copy
- Gates: `npx vitest run src/pages/tabs` → 96 passed / 9 files (14 new); eslint/tsc clean

### F07 — two-source comparison tray

- Status: implemented-and-tested
- Diff: NEW `frontend/src/services/comparison-tray.ts` + test; `CompareTab.tsx`/`CompareTab.test.tsx`;
  `EvidenceTab.tsx`/`EvidenceTab.test.tsx`; additive round-trip tests in `deep-links.test.ts`
- Behaviour: session-only, case- and context-scoped draft capped at exactly 2 distinct evidence
  sources plus pinned captures; a third distinct selection is refused with a visible message and the
  original two remain; the same evidence item is refused even with another capture (routes to capture
  history); commit uses the unchanged `buildComparisonUrl` and the URL is replaced with pinned capture
  IDs after server resolution; a case/context change clears the draft only after an explicit notice;
  tray survives re-render and reads empty from another case; `comparison-same-source` renders as an
  alert-styled validation error, never results
- Gates: `npx vitest run src/pages/tabs src/services` → 195 passed / 15 files; eslint/tsc clean
- Follow-up: F07 added CSS hook names but no styles (its allowlist excluded the CSS files); the tray
  styling is completed under F09/F10-owned CSS.

### F08 — inspector states and responsive reading

- Status: implemented-and-tested
- Diff: `components/inspector/inspector-utils.ts` (+ NEW test), `EvidenceInspector.tsx`/`.css`/`.test.tsx`,
  doc comments on the frozen citation/capture fetchers in `services/api.ts`, NEW `api.test.ts` cases
- Behaviour: five distinct diagnostics with `data-state` (`missing-quotation`, `source-unavailable`,
  `ambiguous`, `no-match`, `legacy`); codepoint slicing via `Array.from` (astral/combining tests);
  citation/capture GETs carry no snapshot parameter (spy test; only claim/evidence forward
  `snapshotId`); frozen citation context is read-only; focus returns to the invoking control; 375px
  metadata is complete and unclipped structurally
- Gates: `npx vitest run src/components/inspector src/services` → 115 passed / 5 files; eslint/tsc clean

### F05 — annotation target and reader contracts

- Status: implemented-and-tested
- Diff: `src/cases/service.py` (`_annotation_target_in_case`, membership gate in
  `add_review_annotation`), `src/http/app.py` (`_reader_missing_case_error`), NEW
  `tests/test_refinement_review_targets.py` (26 tests), `docs/reference/http-api.md`
- Behaviour: targets `case|claim|evidence|exception|narrative` must belong to the case (claim via
  `Event.case_id`; narrative via the case-scoped `Claim.narrative_cluster_id` association, never an
  invented `narrative.case_id`); missing and wrong-case targets return the same 422 body; missing case
  → 404; validation runs after writer admission so 409 wins; invalid target writes no annotation and
  no audit row; only the exact missing-case `ValueError` maps to 404 in readers
- Gates: `uv run pytest -q tests/test_refinement_review_targets.py tests/test_http_api.py
  --disable-warnings` → 101 passed; `... test_b01_persistence_reviews.py test_r02_case_writer_fencing.py` →
  49 passed; pinned `tests/test_http_api.py:727` unchanged and green; `uv run ruff check src tests scripts`
  → clean

### F09 — comparison and source provenance

- Status: implemented-and-tested
- Diff: `services/api.ts` (+ test) gains `getCaseSources` and the source-summary types; `SourceAnalysis.tsx`
  (+ test, + CSS) renders the existing sources GET; `CompareTab.tsx` (+ test, + CSS) gains distinct
  `comparison-historical-unavailable`/`comparison-dependency-warning` hooks and the missing `.compare-tray*` styles
- Behaviour: exactly one sources-summary GET plus the single case-keyed evidence collection query, no
  per-source/evidence detail fan-out; evidence records are no longer counted as sources; limitation copy
  states that aggregated summaries are not independent corroboration, copies are not independent and
  consensus is not truth (sentence-level negation assertion); existing comparison states/paging untouched;
  citation/capture reads never receive a snapshot selector
- Gates: `npx vitest run src/pages/tabs/CompareTab.test.tsx src/pages/SourceAnalysis.test.tsx src/services/api.test.ts`
  → 56 passed / 3 files; eslint/tsc clean

### F10 — search and local saved views

- Status: implemented-and-tested
- Diff: `SearchTab.tsx` (+ test) inline validation and accessible snippets; `ClaimsTab`/`EvidenceTab`
  (+ tests, + CSS) saved-view bars; NEW `services/saved-views.ts` + 24-test suite; additive
  `deep-links.ts` search-saved filter keys
- Behaviour: search matrix preserved (index-unavailable / invalid / empty / out-of-range / all-term);
  invalid input → inline message with zero requests; saved views v1 with the §5 namespace, version,
  ≤50/≤10/1–80-codepoint/64 KiB limits, allowlisted metadata only, consent-gated `q`/`claimQuery`
  (evidence view has no query field at all), validated read-back, non-overwriting corrupt/unknown-version
  handling, three deletes plus feature-scoped reset (never `localStorage.clear()`), quota/private-mode
  ephemeral fallback, cross-tab `storage` refresh without applying or resetting
- Gates: `npx vitest run SearchTab.test.tsx ClaimsTab.test.tsx EvidenceTab.test.tsx saved-views.test.ts deep-links.test.ts`
  → 114 passed / 5 files; eslint/tsc clean
- Deviation recorded: consented stored queries are capped at the existing URL allowlist maximum (200
  codepoints) although the contract allows up to 256; conservative and re-appliable through the URL

### F11 — run history and frozen navigation

- Status: implemented-and-tested
- Diff: `RunHistoryTab.tsx` (+ test, + CSS), `ChangesTab.tsx` (+ test), additive `deep-links.test.ts` cases
- Behaviour: `ChangesBody` untouched (states/pagination/links identical); stage-attempt IDs and grouped
  `InvestigationRun` IDs are separately labelled regions with `data-id-kind` and no cross-bleed; observer
  stamps render as "Observed by run" and never as actor/cause; frozen claim context is read-only with the
  only "Open current claim" strip control; citation/capture GET spies prove no snapshot forwarding
- Gates: `npx vitest run ChangesTab.test.tsx RunHistoryTab.test.tsx deep-links.test.ts` → 60 passed / 3 files
- Follow-up completed by the orchestrator: the frozen **evidence** inspector also gained an explicit
  "Open current evidence" transition (no fetch until chosen), with a focused inspector test —
  `npx vitest run src/components/inspector/EvidenceInspector.test.tsx` → 39 passed

### F12 — linked analysis exploration

- Status: implemented-and-tested
- Diff: `PartiesTab.tsx` (+ test, + CSS), `NarrativeLandscape.tsx` (+ test, + CSS),
  `CorroborationNetwork.tsx` (+ test); `NetworkGraph`/`node-id` untouched
- Behaviour: stable entity-ID selection and links built only from recorded IDs (a party without recorded
  claim IDs renders no links); stance basis is labelled (`model-derived` / `recorded` / "Origin not
  recorded") with no truth/verified claim; `narratives-empty` renders distinctly from loading and network
  error; party view is current-only and the existing gate is proven to block the fetch
- Gates: `npx vitest run NarrativeLandscape.test.tsx CorroborationNetwork.test.tsx PartiesTab.test.tsx node-id.test.ts`
  → 33 passed / 4 files; eslint/tsc clean

### F13 — geography and timeline

- Status: implemented-and-tested
- Diff: NEW `pages/tabs/coordinates.ts` + test; `MapTab.tsx`/`.css`/test; `TimelineTab.tsx`/`.css`/test;
  one additive backend regression test in `tests/test_http_api.py`
- Behaviour: three coordinate states (`recorded` includes 0,0 / `invalid` out-of-range or non-finite /
  `missing`), unplottable events listed with distinct labels; bi-directional list↔marker selection by
  recorded event ID only; event-context links (never a fabricated claim/evidence selector); `map-empty`
  via the shared recipe; timeline statuses limited to the six known values with "Unrecognized status" +
  raw value; unparseable dates render "Date not recorded" (no 1970/NaN) and are independent of status.
- Gates: `npx vitest run MapTab.test.tsx TimelineTab.test.tsx coordinates.test.ts` → 27 passed;
  disposable copy `uv run pytest -q tests/test_http_api.py` → 76 passed; eslint/tsc/ruff clean
- Orchestrator follow-up: `_map_timeline_event` dropped `workflowRoute`/`sourceUrl`; both are now
  forwarded verbatim and the regression test pins them.

### F15 — operator and portfolio coherence

- Status: implemented-and-tested
- Diff: `Dashboard.tsx`/`.css`/NEW test, `CaseExplorer.tsx`/`.css`/NEW test, `MonitoringCenter.tsx`/`.css`/test,
  `PipelineMonitor.tsx`/test, `OperatorLaunchGuide.tsx`/`.css`, `AiIntegrationInfo.tsx`/`.css`
- Behaviour: dashboard keeps exactly two reads (`['cases']`, `['monitoringSummary']`) and orders a
  counts-only priority queue with a stable id tie-break; case explorer renders the list DTO with text
  indicators; monitoring keeps real counts + "Not provided by the API" and pipeline keeps
  configured-vs-recorded with distinct `monitoring-unavailable`/`monitoring-empty` and
  `pipeline-unrecorded`/`pipeline-attempts-empty` markers; all polls use the visibility-aware interval and
  "Last fetched" vs "Last observed" are distinct; AI-info/CLI guide now state the real write surface
  (three POST families + CLI create/ingest/rerun/rebuild/recovery) and drop scheduling/notification claims
- Gates: `npx vitest run Dashboard.test.tsx CaseExplorer.test.tsx MonitoringCenter.test.tsx PipelineMonitor.test.tsx`
  → 38 passed; full frontend suite at this boundary → 474 passed / 33 files; `npm run check` pass;
  eslint/tsc clean after the orchestrator added the missing `afterEach` vitest import in two test files

### F16 — core integration and release gate

- Status: implemented-and-tested (gate only; no feature code changed)
- Diff: NEW `frontend/playwright.refinement.config.ts`, NEW `frontend/tests/gate/*.spec.ts`
  (`core-screens`, `core-states`, `a11y-keyboard`, `journeys`) and `tests/gate/support/*`
  (synthetic-API mock router + hygiene helpers). Artifacts and screenshots go to
  `/tmp/refinement-gate` (outside the checkout).
- Environment: Vite-only dev server, every `/api/**` request answered by the synthetic mock router
  (unknown paths 404, font hosts blocked, same-origin assertion), three viewport projects
  375×812 / 768×1024 / 1280×800.
- Results (exact):
  - `npx playwright test --config playwright.refinement.config.ts` → **205 passed, 4 skipped, 0 failed**
    (2 m 48 s). Screens 24/24 at all three viewports; states 42/42 at all three viewports; keyboard/a11y
    at 375 and 1280 (768 skipped by design); critical journey on Chromium and Firefox.
  - Engine status: Chromium and Firefox proven. **WebKit not proven** — the host lacks `libavif16`;
    nothing was downloaded or upgraded. Recorded as a scoped defer, never a PASS.
  - Console/overflow/request audit: 0 application `console.error`, 0 uncaught page errors, 0
    document-level horizontal-overflow violations across 202 observed cells; screen/a11y requests GET-only,
    mutation cells only the three POST families; zero external/8000 calls. Skip link is the first Tab stop
    and moves focus to `#shell-main`; 16 native case links, exactly one `aria-current="page"`, no
    `role="tablist"`; 200 % approximation shows the boundary caveat with no overflow.
  - Backend gate in the disposable copy: `uv run pytest -q --disable-warnings` → **773 passed,
    9 deselected** (436 s); `uv run ruff check src tests scripts` → clean.
  - Frontend gate: `npm run check` pass; `npm test -- --run` → **474 passed / 33 files**.
- Defect found by the gate and fixed before acceptance: `claims?snapshot=…` silently rendered current
  claims while keeping the selector (contracts §3/§10 violation). Resolution: the claims **list** is a
  current-only overview reader, so `claims` was removed from `HISTORICAL_VIEWS`; the F02 gate now shows
  "Unsupported historical view" with an "Open current Claims" link that strips the selector (and the
  strip link now actually removes `snapshot`). Frozen claim context remains available in the
  evidence-hosted inspector (`/evidence?claim=…&snapshot=…`), which the historical-snapshot gate cell
  now exercises. Component test updated; gate cell 12 re-run green at all three viewports.

## 3. Optional extensions

### F17 — snapshot comparison read API (X01)

- Status: implemented-and-tested (owner approved implementing the PROPOSED endpoint)
- Diff: NEW `src/cases/snapshot_comparison.py`, NEW `tests/test_refinement_snapshot_comparison.py`
  (34 tests), `src/http/app.py`, `src/http/schemas.py`, `src/http/mappers.py`, `docs/reference/http-api.md`
- Behaviour: `GET /api/cases/{case_id}/snapshot-comparison?baseline=&target=&limit=&offset=` with both
  params required, chronological ordering by the owning run sequence (same/reversed → 422), uniform
  byte-identical 404 for unknown/wrong-case snapshots, third-snapshot selectors rejected with 422,
  `limit` 1–100 / `offset` 0–2147483647. Availability is decided before any delta: incompatible
  schema/identity/policy, unknown version or unreadable payload → 200 `unavailable` with the reason and
  no ready items; ready responses always carry an integer total. DTO `mode: ad_hoc` with the full
  contracts §12 field list, per-side metadata (save time, versions, sequence, coverage, run id), items
  over the 13 projection groups (case singleton uses the case ID), `changeKind` in
  `{entity_added, entity_absent, field_changed}`, sorted changed fields, per-side refs and stable
  `(entityType, entityId, changeKind)` ordering. Absence wording only — never deletion/retraction.
- Read-only proof: reuses `semantic_view`/`get_case_snapshot`/`snapshot_payload`/`snapshot_entities`;
  never calls `build_snapshot_delta` (stubbed with raising writers in a test and the read still
  succeeds); DB file hash, table counts and `sqlite_master` unchanged across a mixed 200/404/422 batch.
- Gates (disposable copy): `uv run pytest -q tests/test_refinement_snapshot_comparison.py tests/test_r03_snapshots.py
  tests/test_r03b_snapshot_readers.py tests/test_r03c_history_deltas.py tests/test_http_api.py --disable-warnings`
  → 153 passed (34 new); `uv run ruff check src tests scripts` → clean
- Deviations (documented): `changedFields` is empty for added/absent entities (presence is not a field);
  refs pin all five keys with `null` for unrecorded ids; `incompatible_*` (pair disagrees) is distinct
  from `unknown_version` (pair agrees on an unsupported version).

### F18 — snapshot comparison interface (X01 UI)

- Status: implemented-and-tested
- Diff: `ChangesTab.tsx`/`.test.tsx`/`.css` (additive `mode=ad_hoc` branch + ad-hoc panel), `deep-links.ts`
  (+ test) changes-only allowlist entry `mode`/`baselineSnapshot`/`targetSnapshot` and
  `parseAdHocChangesSelection`, `api.ts` (+ test) `getSnapshotComparison`, `types/backend-models.ts`
- Behaviour: ad-hoc mode is reachable only through the explicit Changes allowlist; without the mode the
  recorded view is untouched (all pre-existing state/pagination/historical-link tests unchanged). The
  panel labels two explicit observations (snapshot id, owning run, save time, sequence, versions,
  coverage), renders `unavailableReason` with no ready-zero claim, says "No changes between these
  observations" for a ready zero total, uses absence-only wording, and exposes reload-stable pinned
  permalinks. An incomplete pair shows an explicit message with zero requests and no defaulting. Citation
  and capture GETs never receive a snapshot parameter.
- Gates: `npx vitest run ChangesTab.test.tsx deep-links.test.ts api.test.ts` → 98 passed / 3 files;
  eslint/tsc clean

### F19 — historical artifact read API (X02)

- Status: implemented-and-tested (owner approved implementing the PROPOSED endpoints)
- Diff: NEW `src/cases/artifact_reader.py`, NEW `tests/test_refinement_artifact_reader.py` (36 tests),
  `src/http/app.py`, `src/http/schemas.py`, `src/http/mappers.py`, `docs/reference/http-api.md`
- Behaviour: `GET .../investigation-runs/{run_id}/artifacts` returns descriptors sorted by type then id,
  proving `artifact.case_id`/`stage_run.case_id`/`stage_run.investigation_run_id` ownership, only
  succeeded runs and the three published types; descriptors carry `artifactId`, `type`, `displayName`,
  relative `downloadUrl`, nullable `recordedChecksum` and `checksumKind ∈ {payload_json, unknown}` and
  never a filesystem path. `GET .../artifacts/{artifact_id}` serves bytes only from the resolved
  `cases/{slug}/runs/{run_id}/` root with the fixed per-type filename, `O_NOFOLLOW` open plus `fstat` of
  the same descriptor, a 50 MiB cap (`413 too_large`), attachment disposition with no CRLF, correct
  mime and `nosniff`. Wrong case/run/owner/temporary/missing artifact all return one uniform 404; no
  latest or inline fallback; no generation.
- Read-only proof: the reader imports no writer helper and contains no `mkdir`/`makedirs`/`touch`/
  write-mode open; a mixed GET batch leaves the output-tree fingerprint unchanged.
- Gates (disposable copy): `uv run pytest -q tests/test_refinement_artifact_reader.py --disable-warnings`
  → 36 passed; with `tests/test_http_api.py tests/test_r01_investigation_runs.py` → 118 passed;
  `uv run ruff check src tests scripts` → clean
- Residual risk **closed in the follow-up pass** (§4): the reader now opens the case directory once and
  every component relative to the previous descriptor with `O_NOFOLLOW` (+`O_DIRECTORY`), so an
  intermediate symlink swap is refused at open time; `fstat`/reads use the same final descriptor. The
  case directory itself may still be an operator-configured symlink by contract.

### F20 — historical report interface (X02 UI)

- Status: implemented-and-tested
- Diff: `ReportTab.tsx`/`.test.tsx`/`.css` (explicit run pin + descriptor list + states),
  `RunHistoryTab.tsx`/`.test.tsx` ("View frozen report" link), `deep-links.ts` (+ test)
  `REPORT_PARAMS.run = 'reportRun'` allowlisted on the report view only, `api.ts` (+ test)
  `getInvestigationRunArtifacts` / `downloadInvestigationRunArtifact` (refuses a non-allowlisted type or
  a download URL that does not address the recorded artifact, without fetching), `types/backend-models.ts`
- Behaviour: the current report stays the F14 default (all 14 F14 tests unchanged); a pinned run is
  addressed by an explicit reload-stable `reportRun` selector and reads ONLY that run's F19 descriptor
  list. Missing descriptors/bytes, unknown run and empty list are four distinct states
  (`artifact-missing`, `run-not-recorded`, `run-no-report`, `pin-unavailable`) with no latest/nearby
  substitution and no regeneration. Checksums are labelled "recorded payload checksum" with
  `checksumKind`; no verified-file/chain-of-custody copy. Switching back to the current report is an
  explicit link.
- Gates: `npx vitest run ReportTab.test.tsx RunHistoryTab.test.tsx deep-links.test.ts api.test.ts`
  → 105 passed / 4 files; eslint/tsc clean
- Gap found and fixed while gating: `downloadBlob` threw a plain `Error` for a non-2xx response, so a
  real 404 download could never be classified as `artifact-missing` (only the mocked test could).
  It now throws `ApiError` with the status; a new `api.test.ts` case pins the 404 classification.

### F21 — extended history release gate

- Status: implemented-and-tested (full optional bundle: X01 **and** X02 both approved and delivered)
- Diff: NEW `frontend/tests/gate/optional-history.spec.ts`; `tests/gate/support/mock-api.ts` gained the X01
  `snapshot-comparison` and X02 artifact list/download synthetic endpoints. One product fix found here:
  `downloadBlob` now throws `ApiError` with the HTTP status (see F20).
- Core gates re-run on the current tree (no baseline regression):
  - `uv run pytest -q --disable-warnings` in the disposable copy → **843 passed, 9 deselected** (499 s);
    `uv run ruff check src tests scripts` → clean
  - `npm run check` → pass; `npm test -- --run` → **514 passed / 33 files**
  - `npx playwright test --config playwright.refinement.config.ts` → **220 passed, 4 skipped, 0 failed**
    (F16 core 24 screens × 3 viewports + 42 states, plus the 5 X01/X02 optional cells on each viewport)
- X01 matrix (browser, 3 viewports): ad-hoc comparison renders two labelled observations and their
  items; an `incompatible_schema` unavailable response renders the reason with no zero-change claim.
  Unit matrix (F17): all five `unavailableReason` values, 422 same/reversed/missing, uniform 404 parity,
  deterministic ordering, no-writes proof.
- X02 matrix (browser, 3 viewports): the pinned run lists exactly its recorded descriptors with honest
  checksum labelling; a missing artifact renders a distinct failure with no substitute; an unknown run is
  not substituted with the current report. Unit matrix (F19): missing file, wrong case/run, symlink,
  traversal, oversize 413, permission redaction, same-handle race guard, GET-makes-no-writes.
- Request audit: screen/state/optional cells are GET-only apart from the three POST families;
  no external or port-8000 request was observed.
- Engine status at F21 time: Chromium + Firefox proven; WebKit not proven (host missing `libavif16`).
  **Closed in the follow-up pass**: with `libavif16` installed the full gate also runs WebKit
  (`REFINEMENT_GATE_WEBKIT=1` → 223 passed, 2 skipped, 0 failed).
- Acceptance scope: **full bundle accepted** (both X01 and X02), not a single-track record.

## 4. Follow-up closure pass (after the gate)

| Item recorded at gate time | Resolution | Evidence |
|---|---|---|
| WebKit not proven (host missing `libavif16`) | **Closed** — `libavif16` was installed; the WebKit journey passes | `REFINEMENT_GATE_WEBKIT=1 npx playwright test --config playwright.refinement.config.ts --project=webkit-journeys` → **1 passed** (5.2 s) |
| F19 intermediate-symlink race (`openat2`) | **Closed without a dependency**: the reader now opens the case directory once and each path component relative to the previous descriptor with `O_NOFOLLOW` (+`O_DIRECTORY`), `fstat`/reads the same final descriptor, and closes every descriptor on all paths. `openat2` is a kernel syscall, not an installable package, and Python's `os` module does not expose it | `tests/test_refinement_artifact_reader.py` → **48 passed** (12 new: intermediate/final symlink for each type, per-type positive control, 100-call fd-leak guard, source guard). `case_dir` itself may still be an operator-configured symlink by contract; a swap above that anchor is out of scope |
| 768 viewport a11y cells skipped | **Closed** — the keyboard/skip-link/nav assertions now run at 375, 768 and 1280 | `tests/gate/a11y-keyboard.spec.ts` (`A11Y_PROJECTS` includes all three) |
| Saved-view query cap 200 vs contract 256 | **Closed** — `MAX_FILTER_TEXT_LENGTH` is 256, so a stored consented query always re-applies through the URL | `deep-links.test.ts`, `saved-views.test.ts`, `SearchTab.test.tsx` updated to the 256 boundary |
| F06 `publishedAt` sort had no data | **Closed** — evidence list DTO now exposes `publishedAt` and the tab sorts on it (unknown dates last, stable tie-break) | see the legacy-status follow-up entry below |
| Out-of-enum timeline status crashed ORM reads | **Closed** — lenient enum read + raw value surfaced additively (`rawVerificationStatus`); no migration | see the legacy-status follow-up entry below |
| Gate artifacts could land in the checkout if the default reporter is used | **Closed** — `frontend/.gitignore` ignores `playwright-report/`, `test-results/`, `blob-report/` | `frontend/.gitignore` |

### 4.1 Follow-up implementation detail

- **Legacy `verification_status`** (`src/storage/models.py`, `src/cases/service.py`,
  `src/cases/_serializers.py`, `src/http/mappers.py`, `src/http/schemas.py`, frontend types +
  `TimelineTab.tsx`): `LenientEnum(SQLEnum)` returns the raw stored text when a row holds a value outside
  the six members (bind validation unchanged), a `verification_status_value()` helper replaces every
  status `.value` access, and `rawVerificationStatus` is added additively to `TimelineEventDTO` and
  `EvidenceDTO`. `TimelineTab` shows "Unrecognized status" with the raw value instead of a plain
  "Unknown". CLI readers (`src/cli/commands/review.py`, `query.py`) were also switched to the tolerant
  helper by the orchestrator. New `tests/test_refinement_legacy_status.py` plants out-of-enum values with
  plain SQL and proves all four GETs return 200, carry the raw value, map known values unchanged, and
  write nothing. `tests/test_refinement_legacy_status.py` → 5 tests; combined focused run → 138 passed.
- **Evidence `publishedAt`** (same commit-set): `EvidenceDTO.publishedAt` mapped from the already
  serialized `published_at`; frontend `Evidence.publishedAt` drives a newest-first sort with unknown
  dates last and an ID tie-break, covered by a mixed dated/undated `EvidenceTab.test.tsx` case.
- **Artifact path walk** (`src/cases/artifact_reader.py`): descriptor-relative component walk; 12 new
  tests including per-type positive controls, intermediate/final symlink rejection and a 100-call
  `/proc/self/fd` leak guard (48 tests total for the file).

### 4.2 Final gates after the follow-up pass

- Backend (disposable copy): `uv run pytest -q --disable-warnings` → **860 passed, 9 deselected**;
  `uv run ruff check src tests scripts` → clean
- Frontend: `npm run check` pass; `npm test -- --run` → **516 passed / 33 files**
- Browser: `REFINEMENT_GATE_WEBKIT=1 npx playwright test --config playwright.refinement.config.ts`
  → **223 passed, 2 skipped, 0 failed** on Chromium (3 viewports), Firefox and WebKit
- No commits, no migration and no live-data change; `git status` shows only intended source/test/doc edits
