# Audit remediation execution evidence (2026-11-24 bundle)

Execution record for the six remediation cards in
[`20261124-audit-remediation-handoffs/`](20261124-audit-remediation-handoffs/) and the
integrated release gate [R07](20261124-audit-remediation-handoffs/20261124-r07-integrated-audit-and-release.md).
Requirements: [specification](20261124-audit-remediation-specification.md).

This file records **actual** edits and **actual** test runs for this bundle. It is not approval of
any unrun gate, not a deployment record and not a repair of historical data. Counts are today's
observations, not frozen totals.

## 1. Verification environment

- Baseline `d589359` **plus** the existing staged, unstaged and untracked refinement worktree —
  never a clean rebuild from `HEAD`.
- All gates ran in a disposable copy (`/tmp/r07-gate2/copy`) built from an explicit NUL-delimited
  manifest of candidate paths: 655 files, `.git`/`.env`/`config.toml`/local databases/sidecars/
  outputs/caches excluded, `node_modules` hardlinked read-only. Every copied file was verified
  byte-identical to the working tree (SHA-256, 0 mismatches), twice: before the gates and after
  the audit fixes. The tested copy and the committed tree were re-verified identical afterwards.
- Python dependencies were installed fresh in the copy with `uv sync --extra dev` from the locked
  versions; frontend dependencies were restored by hardlinking the checkout's approved locked
  `node_modules` rather than `npm ci`. No dependency was added, removed or upgraded
  (`pyproject.toml`, `uv.lock`, `package.json` unchanged).
- Deterministic fixture: `scripts/v01_e2e_fixture.py --out /tmp/r07-gate2/v01` (fake providers,
  own database and config). Published artifacts landed under that **non-default** output root.
- Checkout runtime files untouched: `config.toml` (mtime 2026-11-17) and `triangulate.db`
  (mtime 2026-11-15) unchanged; neither is in the commit. Metadata-only evidence, with the usual
  limits of mtime evidence.
- **Recorded substitution:** the first full-suite attempt used a synthetic `config.toml` pinning
  `[database].path` at the scratch database. R05's documented precedence then correctly outranked
  the tests' `DATABASE_PATH`, producing 6 false failures (3 R05 cold-miss, 3 CLI). The gate was
  re-run with the tracked `config.toml` as-is; the failures were a harness defect, not code.

## 2. Per-card results

Each card: cause, chosen contract, regression before/after, focused commands. Full-suite and
browser gates are in §4.

### R01 — guard review writes and recovery (`verified`)

Ordinary review/annotation/exception controls were disabled only while a POST was pending, so an
acknowledged write whose follow-up refresh GET failed could be POSTed again (the audit reproduced
two annotation POSTs from one draft); `uncertain`/`reconciled` left the same bypass.

Now a per-case attempt record separates server acknowledgment, definite refusal and unknown
outcome, and blocks ordinary submits at **render and dispatch** (native/keyboard submit, rapid
same-tick clicks) while pending, `refresh-failed`, `uncertain` or `reconciled`. Recovery is
GET-only; a successful reconciliation stays inconclusive and needs one explicit confirmation that
resends the immutable payload after re-validating the target. 409/422/known-404 stay definite;
5xx, transport loss and unidentifiable acks are ambiguous. Drafts clear only on ack plus verified
read. Records outlive a same-case tab switch and are released on workspace close; late case A work
cannot reach case B.

Files: `frontend/src/pages/CaseIntelligenceCenter.tsx` (+test), `frontend/src/pages/tabs/ExceptionsTab.tsx`
(+test), new `frontend/src/pages/tabs/exception-row-attempts.ts`, `frontend/src/pages/tabs/tabs-state.test.tsx`.

Evidence: before the fix the two new regressions were red (`expected false to be true` for the
still-enabled Save; `expected 1 times, but got 2` for the duplicate POST). After:
`npm run test:ci -- src/pages/CaseIntelligenceCenter.test.tsx src/pages/tabs/ExceptionsTab.test.tsx src/services/api.test.ts` → 92 passed, exit 0; `npm run check` → exit 0.

### R02 — preserve historical context in deep links (`verified`)

A `?citation=` redirect ran before the historical-view gate and rebuilt its destination from the
citation id alone, so `/cases/X/timeline?snapshot=S&citation=C` landed on unpinned Evidence.

Gate, redirect and canonicalisation are now one decision point (`decideCaseRoute`), with the
snapshot selector read as `none | valid | invalid | conflicting` and never guessed. An
unsupported/conflicting/invalid state renders **before** its data consumer mounts; pinned
Evidence reads only snapshot-aware detail and never falls back to current data after a 404; a
snapshot+citation conflict offers two explicit choices and issues no reads; a Changes pair keeps
its context and drops a stray citation; citation-only legacy links still redirect once with
`replace`.

Files: `frontend/src/services/deep-links.ts` (+test), `frontend/src/pages/CaseIntelligenceCenter.tsx`
(+test), `frontend/src/pages/tabs/EvidenceTab.tsx` (+css, +test), `frontend/src/pages/tabs/ChangesTab.test.tsx`.

Evidence: before, the combined Timeline URL produced `/cases/case-12345678/evidence?citation=cite-example`
(snapshot stripped, gate absent). After: focused suites 202 passed; R01 guards 46 passed;
`npm run check` exit 0; full `npm run test:ci` 556 passed.

### R03 — validate frozen snapshot integrity (`verified`)

`_payload_reason` type-checked a group only when present and `semantic_view` defaulted missing
arrays to `[]`, so a target payload of `{}` compared as "everything absent" and returned `ready`
with seven synthetic changes.

Both payloads must now satisfy the full `case-snapshot-v1` shape (mapping, owning `caseId`,
matching embedded schema/identity/policy, `query`, nullable `reviewNotes`, and all twelve entity
arrays with non-blank unique string IDs) **and** agree with their stored semantic hash through the
canonical writer projection — checked once, after the supported/compatible row-version check and
before any item is constructed. Unreadable payloads return the existing explicit
`availability: "unavailable"` / `unavailableReason: "payload_unreadable"` shape with `items: []`,
`total: null`, `hasMore: false` and intact selected IDs, metadata and paging. Recorded-run
`/changes`, `build_snapshot_delta` and the policy version are untouched; the reader stays read-only.

Files: `src/cases/snapshot_comparison.py`, `src/cases/history.py`,
`tests/test_refinement_snapshot_comparison.py`.

Evidence: before, `uv run pytest -q tests/test_refinement_snapshot_comparison.py -k "empty_target_payload or corrupt_frozen_payload"`
→ 29 failed, 6 passed (`assert 'ready' == 'unavailable'`). After: 73 passed; the focused set
(comparison, legacy status, `test_r03_snapshots`, `test_r03b_snapshot_readers`, fixtures,
`test_http_api`) 198 passed; `tests/test_r03c_history_deltas.py` 6 passed; Ruff clean. Every
corruption case asserts the mutated row's payload and hash are byte-identical afterwards.

### R04 — align the artifact output root (`verified`)

The HTTP artifact reader hard-coded `./output` while the CLI publishes under `--output`, so a
validly published artifact could be listed and then be unavailable; existing tests overrode the
dependency and hid the mismatch.

One operator setting, `TRIANGULATE_OUTPUT_ROOT` (unset/blank ⇒ `./output`), is captured once per
app instance against the startup cwd and wired into both artifact reads and the case service. The
recorded path must lexically equal the exact expected `root/cases/{slug}/runs/{run_id}/{fixed name}`;
a relative record is attributed only to the captured cwd, otherwise the existing uniform 404.
Ownership join, allowlisted types, fixed names, descriptor-relative no-follow walk, size limits,
attachment headers, checksum meaning and `200 []` list semantics are unchanged, and no path is
disclosed to clients.

Files: new `src/settings.py`, `src/http/app.py`, `src/http/dependencies.py`,
`src/cases/artifact_reader.py`, `tests/test_refinement_artifact_reader.py`,
`docs/reference/{http-api,cli,cli-operations}.md`, `.env.example`.

Evidence: before, the real-app custom-root regression failed with download `404` vs expected
`200` (1 failed, 8 passed, 48 deselected). After: 161 passed (baseline 151); Ruff clean.

### R05 — make historical GETs storage-read-only (`verified`)

The comparison, artifact list and artifact download GETs called `get_database().init_db()`, and a
cold first request to the comparison route created the configured database even for a missing case.

The three routes now share one narrow read-only dependency over a single canonical per-instance
database path resolved side-effect-free (non-default `[database].path` wins, else `DATABASE_PATH`,
else `./triangulate.db`; relative values against the server cwd). Historical reads open the file
with SQLite `mode=ro`, `NullPool`, a per-request engine and an explicit `BEGIN`, disposed on every
path including 503/404/422. A readiness phase (open + schema-presence probe) maps store failures
to a sanitized `503 {"detail": "Historical storage is unavailable"}`; the domain phase only maps
bare corruption errors, so a query-time programming defect surfaces as an actionable 500. No
builder, taxonomy sync, create-all, migration runner or write runs on these GETs. `/health` stays
liveness only.

Files: `src/settings.py`, `src/storage/database.py`, `src/storage/__init__.py`, `src/runtime.py`,
`src/http/app.py`, `src/http/dependencies.py`, `src/cli/main.py`, new
`tests/test_r05_read_only_storage.py`, plus binding-only edits in
`tests/test_refinement_snapshot_comparison.py`, `tests/test_refinement_artifact_reader.py`,
`tests/test_r03b_snapshot_readers.py`, `tests/test_cli.py`.

Evidence: before, the cold-miss repro returned `404` for all three routes with
`parent_created=True db_created=True`. After: `503` with `parent_created=False db_created=False`.
Focused set 244 passed; the read-only module alone 19 passed; Ruff clean. Tests fingerprint the
database bytes, `sqlite_master`, `_migrations` rows and directory entries before/after and install
booms on the builder/DDL/migration paths.

### R06 — preserve review decisions on defer (`verified`)

`review_case` set `case.status = REVIEW_READY` for `defer` (contradicting its own comment) and
routed `defer` through `_resolve_case_exceptions`, so an approved or rejected case returned to the
queue while its event decisions still said approved/rejected, and exception timestamps and
resolution notes changed.

`defer` is now a case-level acknowledgement: status, stage, event decisions and their bindings,
and exception metadata stay as stored; only the case-level note and timestamp are recorded.
Admission, validation, rollback and 409 handling are unchanged, and exception-level `defer` is a
different, unchanged action.

Files: `src/cases/service.py`, `tests/test_b01_persistence_reviews.py`,
`tests/test_r02_case_writer_fencing.py`, `tests/test_http_api.py`, `tests/test_cli.py`,
`docs/reference/{http-api,cli,cli-operations}.md`.

Evidence: before, the defer regressions failed with `APPROVED/REJECTED/MONITORING → REVIEW_READY`
and mutated exception `resolution_notes`/`updated_at` (5 failed, 1 passed). After: 184 passed
across the focused set; Ruff clean. Coverage is parameterized over REVIEW_READY/APPROVED/REJECTED/
MONITORING with seeded analysis-bound event reviews, a real writer fence, real HTTP and real CLI
passthrough.

## 3. Integrated audit

The candidate was audited against `HEAD` plus the recorded starting worktree, in three deep
per-pair reviews (R01/R02, R03/R04, R05/R06) after an initial single-pass review was rejected as
too shallow (12 tool uses, most items unverified).

**Path classification.** 456 candidate paths changed. Remediation touched 34 source/test/doc paths
(the six cards plus the gate-spec update); the remainder is the pre-existing refinement bundle
(UI, backend refinement, wireframes) and documentation. Attribution used per-card file lists
cross-checked against modification times and a full `git status` inventory. No path was left
unclassified.

**Findings → fixes → re-review.** All fixes were re-reviewed and accepted.

| # | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| 1 | major (R01) | Exception acks accepted a body with no `id`, so an unidentifiable success counted as acknowledged. | Fixed: identity is required; `tabs-state` mock corrected to a `CaseListItem`-shaped body; new regression pins `uncertain` + blocked + reconciliation. Accepted. |
| 2 | major (R02) | `?snapshot=&snapshot=x` silently selected `x` instead of reporting an invalid selector. | Fixed: any blank member is invalid; identical duplicates stay valid, distinct stay conflicting. Accepted. |
| 3 | minor (R02) | A Changes `baseline/target` pair without `mode=ad_hoc` lost its context to a citation redirect. | Fixed: an explicit pair is historical context — stays on Changes, citation dropped; bare citation-only links still redirect once. Accepted. |
| 4 | minor (R05) | A query-time `OperationalError` (e.g. malformed SQL) was reported as 503 unavailable storage. | Fixed by phase-splitting the mapping; new regression proves 500 not 503. Accepted with a documented residual (below). |
| 5 | major (R01) | Claimed unbounded growth of the per-case attempt store with no cleanup. | **Refuted**: `CaseIntelligenceCenter.tsx:270-278` releases records on workspace close and on case change. No change made. |

**Deviation to record.** The mocked browser matrix asserted `failed` for a 500. R01's contract
makes a bare 5xx *ambiguous*, so `review-failed`/`exception-failed` were re-pointed at a definitive
404 refusal and two `uncertain` cells were **added** (42 → 44 cells). Coverage increased; nothing
was weakened.

## 4. Gates

| Gate | Command | Result |
| --- | --- | --- |
| G1 backend | `uv run pytest -q --disable-warnings` | **937 passed, 9 deselected, 0 failed**, 348 warnings, **1153.57 s (19:13)** — the full suite completed |
| G1 lint | `uv run ruff check src tests scripts` | `All checks passed!` (exit 0), re-verified on the committed tree |
| G2 check | `npm run check` | exit 0 (lint + typecheck + build) |
| G2 tests | `npm run test:ci` | **563 passed / 33 files**, exit 0 |
| G3 matrix | `npx --no-install playwright test --config playwright.refinement.config.ts` | **228 expected, 0 unexpected, 0 flaky, 2 skipped** (3.0 m) |
| G3 WebKit | `REFINEMENT_GATE_WEBKIT=1 … --project=webkit-journeys` | **1 passed** |
| G4 API-only | scenarios 7–9 (see below) | **14/14 checks PASS** |

### G4 — real disposable API + browser

Real FastAPI on `127.0.0.1:8000` serving the published V01 fixture under the non-default root,
behind a Vite dev server pinned same-origin; headless Chrome. No mocks. Cleanup trap on the API and
Vite PIDs; non-loopback requests aborted at the context.

| # | Scenario | Result |
| --- | --- | --- |
| 1 | Happy-path reads | PASS — case detail and tabs from real HTTP, every API request GET |
| 2 | Two published snapshots | PASS — browser called `/snapshot-comparison?baseline=…0016&target=…1397`; `availability=ready`, 14 items; the added frozen claim rendered with its frozen text; side-scoped refs carry the right `snapshot=` |
| 3 | Artifact list + download (non-default root) | PASS — 3 descriptors pinned to the manifest run; all three downloaded through the UI, `attachment` + `nosniff` + expected media type, downloaded **bytes** equal to the independently located run files. No `./output` in the serve cwd, so the configured root was proven |
| 4 | R02 deep links | PASS — unsupported/conflict states render with **zero** citation and current-gallery reads under the pin, no automatic redirect; both explicit choices work |
| 5 | R01 annotation ack + failed refresh GET | PASS — one annotation POST acked; exactly one follow-up refresh GET aborted; repeated Save sent nothing (POST count 1); `Retry refresh (GET)` reached the real API and showed the acknowledged note |
| 6 | Request audit | PASS — **34 API requests: 33 GET + exactly 1 POST**, confirmed server-side; the only aborted request is the intended GET; no application console or page errors |
| 7 | Historical-GET-first instance | PASS — first three requests were the historical GETs; results identical to the warmed instance; comparison ready, 3 descriptors, download `200` with attachment headers |
| 8 | Cold-miss probes | PASS — each route as first request returned sanitized `503 {"detail": "Historical storage is unavailable"}`; neither the parent directory nor the database file appeared |
| 9 | R06 defer probe (separate DB copy, 1 POST) | PASS — `defer` on a seeded terminal case returned `200`, status stayed `approved`, stage unchanged, case note and timestamp recorded, event reviews and their hashes/timestamps unchanged, **1 POST** |

Scenario 4's one gap was closed afterwards: the fixture records no citation
(`claim_citations` empty, every `claim_evidence_links.citation_id` NULL), so the frozen-citation
render could not be observed. A citation was seeded into a scratch **copy** of the fixture database
and the journey re-run: the conflict state issued no citation or gallery read, the explicit choice
dropped the pin, the citation read returned `200` with no snapshot selector, and the frozen claim
text, passage and "Frozen citation context" note rendered. 1 test passed; 4 requests, all GET.
The application was not modified for this — only the scratch fixture.

## 5. Not proven, and residual risks

**Not proven:** 7 cross-origin Google Fonts requests (the app shell `@import`s them) were aborted
before the wire and recorded separately. **Zero non-loopback requests completed.** No other gate
item is unproven.

**Residual risks accepted, not fixed:**

- A query-phase `SQLITE_BUSY` on a healthy but locked store now yields 500 rather than 503.
  Malformed SQL is the same exception class, so separating them would need brittle message
  matching; the body stays generic with no path or SQL text.
- Legacy artifact records holding a *relative* path produced from a different cwd are
  intentionally unservable (uniform 404). The absolute-path workflow is the documented one.
- Two app instances with different databases in one process still share the legacy service's
  process-global `_db`. Pre-existing; readers are independent and the service cache is keyed by
  database path.
- A `case-snapshot-v1` payload missing any required marker is reported `payload_unreadable` even
  with a matching hash. The canonical writer always emits every marker.
- R02 treats `changes?baselineSnapshot&targetSnapshot` without `mode=ad_hoc` as historical context
  (stays on Changes, drops the citation) rather than redirecting.

**Out of scope by design:** no new endpoint, schema or migration; no bulk fix, legacy data rewrite,
backfill, D01 recovery, dependency uplift, deploy or production-data action; the local trusted
unauthenticated service boundary is unchanged.

## 6. Release record

- Baseline `HEAD` `d589359231e3d20c66a1349b0e8cf476fbe55ab1`; `origin/main` identical at start and
  re-checked immediately before the push (no drift).
- One integrated commit `34ca121a389236940ba30d54edd290dcb83abe5d`, reviewed tree
  `2e25712679e4bb4adceac6fe2083ef8e8add5bb3`; the committed tree matched the reviewed tree exactly
  (no hook modification). 456 files changed, 73 769 insertions, 1 749 deletions.
- Staged inventory equals the full candidate diff (`git diff HEAD` and `git diff --cached`: 456
  paths each); no protected path staged (`data/`, `logs/`, `output/`, `triangulate.db`,
  `config.toml`, `node_modules/`, `__pycache__/`, `frontend/dist/`); no mode changes (all 348 new
  files `100644`); secret scan clean apart from the variable name `token=annotation_owner`.
- Push: `d589359..34ca121  main -> main`, non-force, fast-forward. `origin/main` == `34ca121` after
  the push. No PR, no force, no history rewrite.
- No deployment step exists in this sequence; D01 and historical data are untouched.

**Recovery policy — no automatic reverts.** Before a push, a failing gate or an audit finding is
fixed with the smallest coherent change, independently re-reviewed, and the affected gates plus the
final bundle gates are re-run for the exact candidate; user or bundle work is never reverted to
force a green result. After a push, a discovered defect is **not** reverted automatically: there is
no force-push and no history rewrite. The owner chooses between a forward fix and an explicit
revert **commit**, and either path goes through the same review and gate discipline. Card workers
never commit, push or revert.

## 7. Carried figures from the prior audit — history, not results

Quoted only so they are not mistaken for this run's evidence: `npm run check` and Ruff passed;
516 frontend tests and 196 focused backend tests passed; the mocked browser matrix passed 222 with
2 expected skips; one separate WebKit journey passed; **the full backend suite did not finish
within that audit's timeout**. Four scratch regressions failed as expected against that baseline.
None of these figures is claimed as a result here; every number in §4 was produced fresh for
`34ca121`.

## 8. Concept-parity audit and follow-up fixes (post-release)

The gates above prove the remediation contracts and the 42 named states. They do **not** prove
that each screen renders what the [concept wireframe set](../../plans/20261123-product-wireframe-set.md)
specifies, so a separate parity audit was run after the release.

**Method.** All 29 screens (the 24 concept screens plus five populated variants) were captured at
desktop 1280×800 and mobile 375×812 against the real API and the V01 fixture — 58 captures — and
compared pane by pane with the manifest's `pane_plan` and the set's per-file numbered annotations.
This is a **content and control** comparison, not a pixel diff: the concept is a proposal wireframe
with different typography and colour, so a pixel diff would not be meaningful. Tablet 768×1024 was
not captured in this sweep; the mocked matrix covers tablet for state markers only.

**Health of the run.** Zero failed API calls across all 58 captures; zero horizontal overflow at
375 px.

**Corrections to the first pass.** Four findings were artifacts of the capture, not defects, and
are recorded here so they are not re-raised:

| First-pass finding | Actual |
| --- | --- |
| Search shows no results | Captured `/search` with no query. With `?q=evacuation` the app shows "6 results", matched fields, publisher, dates and status. |
| Comparison does not compare | Captured the empty draft. With `left`/`right` selected the app shows both sources, capture selectors, "Compare selected / Swap sides / Clear", an assertion table and dependency warnings. |
| Report has no per-run artifact list | Captured with the wrong parameter. `reportRun` renders the per-run artifacts with recorded payload checksums and download actions. |
| Network lacks the Collector→Arbiter flow | That flow is on the **Pipeline** screen (BOOTSTRAP→RETRIEVE→TRIAGE→INVESTIGATE→ARBITRATE→REPORT). Placement divergence, not a missing capability. |

**Two genuine gaps found and fixed** (frontend only; no API, schema or dependency change):

1. **Case explorer had no sort and no pagination** (`frontend/src/pages/CaseExplorer.tsx`). The
   list filtered and ordered by priority in memory with no sort control and no paging. Added a
   three-key sort (`priority` default / `updated` / `name`, all with a stable id tie-break) as an
   always-visible toolbar control — deliberately outside the collapsible filter panel, and with a
   distinct class so the three filters remain `select.filter-select` — plus a pager (page size 10)
   that renders only past one page, shows `Showing X–Y of Z cases`, disables at the bounds, resets
   on any filter/search/sort change and clamps when the filtered set shrinks. Summary counts stay
   scoped to every filtered case, never to the current page; bulk selection survives paging.
2. **Exception severity was icon-only** (`frontend/src/pages/tabs/ExceptionsTab.tsx`). Severity was
   conveyed by glyph and colour with no text and no accessible name. The row now states
   `Severity: High|Medium|Low` in the same register as the neighbouring `Status:` / `Action:` lines,
   with the glyph marked `aria-hidden` so the name is not announced twice.

**Evidence.** Frontend `npm run test:ci` → **576 passed / 33 files** (563 + 13 new); `npm run check`
exit 0; mocked matrix **228 expected, 0 unexpected, 2 skipped**; Ruff unaffected (no Python change).
The two fixes were then proven in a real browser against a scratch database with **15 cases**
(fixture + 13 seeded): the pager shows `Showing 1–10 of 15`, Next shows `Showing 11–15 of 15` with
five cards and Next disabled, sort returns to page 1, and the exception row states
`Severity: High` / `Severity: Medium` at both viewports with zero horizontal overflow — 4/4 browser
assertions passed. Sort *ordering* is pinned by the new unit tests rather than the browser capture.

## 9. SVG-versus-app parity audit and the fixes it produced

Section 8 compared the app to the wireframe set's *prose*. This section compares it to the
**artwork**, and fixes what that comparison found.

**Method.** All 263 concept SVGs were rendered to PNG at native size, and the app was captured as
**scroll frames** — one image per viewport-height step of its inner scroll container. The frame
model matters: `fullPage: true` silently produced viewport-only images because the app scrolls
`#shell-main{overflow-y:auto}`, which had made every below-the-fold pane look absent in the first
pass. The manifest's `required` control labels (110 per viewport) were also diffed mechanically
against rendered text.

**Findings, and what happened to each.**

| Finding | Class | Outcome |
| --- | --- | --- |
| Dashboard led with four KPI tiles while its own concept header states "No KPI tiles, scores or health metrics" | contradiction | **fixed** — tiles deleted, observed-totals prose restored |
| Monitoring rendered `System Health` and `Schedule / Next Run`, the two states the concept excludes ("no health, scheduler or alert state") | contradiction | **fixed** — stat blocks removed, the not-provided disclosure kept |
| Repeated case chrome consumed 69% of the desktop viewport and 146% of mobile before any tab content | density | **fixed** — see the measurements below |
| Corroboration network had no reading rule ("a shared edge is not independent proof… no independence or completion claim from graph shape alone") | missing | **fixed** — always-visible caveat beside the legend |
| Search had no permalink control | missing | **fixed** — permalink for the current query/filters/offset |
| Case explorer showed no updated date | missing | **fixed** — labelled relative value, explicit unknown for missing/unparseable |
| Per-case **Coverage** column (dashboard and explorer) | missing | **deferred** — `CaseListItem` has no coverage field; needs a backend DTO change |
| **Recent runs** panel (dashboard) | missing | **deferred** — every runs endpoint is case-scoped; a cross-case read does not exist and no N+1 fan-out was added |
| "Grouped runs on Run history contradict the stage-only rule" | claimed contradiction | **refuted** — `RunHistoryTab` documents that it lists grouped-run IDs as an identifier legend so two ID kinds are never conflated |
| "Comparison relabels alignment" | claimed relabel | **refuted** — `left_only: 'Extracted only on the left'` exists; the other string is a complementary cell message |
| Claims detail/provenance "missing" | claimed missing | **refuted as absence** — present after selecting a claim; the real issue is discoverability, recorded as a nit |
| Timeline six-state vocabulary "missing" | claimed missing | **refuted as absence** — present as per-event badges; only the legend table is absent |

**Case-chrome measurements** (real API, scratch DB, Chrome; task content = bottom of the tab nav):

| viewport | tab-nav block | task content starts at | share of screen |
| --- | --- | --- | --- |
| 1280×800 | 216 → **67 px** | 553 → **250 px** | 69% → **31%** |
| 375×812 | 418 → **36 px** | 1189 → **295–322 px** | 146% → **36–40%** |

The rail also moved 280 → 240 px, the concept's own width. The desktop target (≤400 px) is met.
The mobile target (≤300 px) is met on most tabs and **missed by up to 22 px** where the case header
wraps — reported rather than rounded up. All 16 tab links remain real links with a unique
`aria-current`, which the 228-cell matrix verifies at three viewports.

**Review corrections applied before commit.** An independent review caught two must-fixes: the
dashboard's review-item total silently switched between the case-row sum and the monitoring
summary's differently-scoped backlog (now one source only, with a test that pins it), and the
boundary notice had been compressed to 10 px on phones (now 12 px, wrapping, still always visible —
a security notice is read, not skimmed).

**Verification.** `npm run test:ci` → **588 passed / 33 files**; `npm run check` exit 0; mocked
matrix **228 expected, 0 unexpected, 2 skipped**; the fold measurements above taken independently
of the implementing worker.

**Environment incident, no repo impact.** A subagent's `pnpm` invocation restructured
`node_modules` (symlinked `@types`, removed `.bin`) and left `pnpm-lock.yaml` /
`pnpm-workspace.yaml`. The tree was restored from the verified install and the stray files deleted;
`git status` confirms no tracked file, lockfile or manifest changed.

**Residual, accepted.** The Refresh label is visually clipped on phones while its accessible name is
preserved; the mobile tab strip scrolls horizontally (all links keyboard-reachable, but no automated
test asserts focus visibility at 375 px); and the two deferred panes above stay unbuilt until the
backend can supply them honestly.
