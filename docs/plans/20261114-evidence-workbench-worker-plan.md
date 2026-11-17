# Evidence workbench: DeepSeek v4.1 implementation handoff

Date: 2026-11-14. Last verified: 2026-11-15. Status: **B00, B01, B02, B03, E01, E02 (passes A/B1/B2/B3) and E03 are completed, independently verified, and merged into `main` (PR #2, merge commit `af870da`); the ORM typing migration and the review/investigation/OSINT/evaluation features from the remote line are integrated in the same merge. Migration history is 1..11 (7 OSINT, 8 review audit/evaluation, 9 review hash, 10 captures, 11 citations); backend 418 passed / 9 deselected, Ruff clean; frontend `npm run check` + 72 tests. **Next ticket: E04 — evidence inspector and deep links, which is the Release A review gate** (handoff: [E04 handoff](20261115-e04-handoff.md)). There is no E05: after E04 the sequence continues with P01 and must not start before the owner signs off Release A. The B02 database incident remains disclosed**.

Contract authority: [implementation specification](20261114-evidence-workbench-specification.md). Context: [roadmap](20261114-product-enhancement-roadmap.md), [audit](../reference/20261114-setup-and-maintenance-audit.md), [architecture](../architecture/20261114-current-architecture.md).

## 1. Execution model

The configured `worker` role was inspected: **`opencode-go/deepseek-v4.1-flash`**. Use that role/model for implementation after approval. Do not silently substitute another provider/model. This document is a handoff, not a workflow script. The owner approved the defaults on 2026-11-14, authorizing bounded sequential workers; production/data/cleanup gates remain separate.

- Default: **one bounded ticket/worker at a time**, parent review after each. No recursive delegation or automatic multi-agent orchestration.
- A worker receives the approved specification, one ticket, its exact dependencies and the current baseline diff. It must read the relevant implementation before editing.
- Sequential work in the shared checkout can see the currently untracked planning docs. A fresh git worktree cannot see them unless they are first included in an approved baseline or explicitly supplied to the worker. Do not launch a worktree and assume this spec exists there.
- Shared files (`service.py`, models, migrations, HTTP schemas, frontend DTOs) must have one writer. Allocate migration numbers from the then-current registry; do not reserve conflicting versions across tickets.
- No worker may run old ingestion/cleanup scripts, delete untracked user files, repair/migrate the live DB, start a server against it, reset the worktree, change secrets, make a public listener or commit/deploy without explicit permission.
- Prefer precise edits and narrowly named helper modules over broad service rewrites. One logical change per handoff. If a ticket cannot stay bounded, stop and propose a split before extending scope.
- A ticket is complete only after actual diff review and passing required checks. Failing tests, blocked install, partial implementation or unverified schema/API changes are blockers, not successful completion.

## 2. Ticket dependency map

```text
B00 clean installation ───────────────┐
B01 atomic persistence/reviews ── E01 immutable captures ── E02 quotation semantics
B02 honest acquisition ───────────────────────────────────┘
B03 truthful/usable UI ───────────────────────────────────────────┐
E02 ── E03 inspector read API ── E04 inspector UI/deep links ──────┘  [Release A]
E02 + E03 ── P01 dependency groups ── P02 comparison API
P02 + E04 ── P03 comparison UI                                      [Release B]
B01 + B02 + E02 ── R01 grouped identity ── R02 admission/fencing/recovery
R02 + P01 ── R03 snapshots/deltas/API ── R04 changes UI
E02 + E03 ── S01 transactional FTS index
S01 + E04 + P01 ── S02 search API/UI
R04 + S02 + P03 ── V01 release verification                         [Release C]
```

Default dispatch order: **B00 → B01 → B02 → B03 → E01 → E02 → E03 → E04 → P01 → P02 → P03 → R01 → R02 → R03 → R04 → S01 → S02 → V01**. This intentionally avoids shared-file races. Stop after each release for review.

## 3. Task cards

Paths/symbols below identify the inspected implementation seam, not permission to edit every file in the group. New module paths are **proposed** and must be kept small.

### B00 — Restore a reproducible frontend toolchain

**Depends on:** owner approval. **Scope:** `frontend/package.json`, `package-lock.json`, supported runtime metadata and setup documentation; optional CI install smoke gate.

Align supported/security-reviewed Vitest and coverage-provider versions; inspect other peer conflicts rather than hiding them. Repair missing native optional lock entries. Document the Node/npm baseline. No general dependency pruning, forced audit fix, UI changes or unrelated AI-library upgrades.

**Acceptance:** fresh install in an isolated directory with `npm ci`; `npm run check`; `npm test -- --run`. Report remaining advisories by runtime/dev reachability and fixes/deferments. Do not use the audit's workaround as success evidence. Stop for approval if a major unrelated package upgrade is needed.

### B01 — Make case event writes atomic and preserve meaningful review state

**Depends on:** approval. **Scope:** `src/storage/event_store.py:store_event_in_db`, `src/cases/service.py:_persist_investigation_outputs`, `_execute_stage`, relevant storage/case/review tests; narrow analysis-hash helper and minimal additive review hash/invalidation metadata fields with an idempotent migration if needed. Do not overwrite human notes with hidden metadata.

Add an internal session-owned writer and optional caller-owned transaction path. With a caller-owned session, do not commit/rollback independently or swallow write errors; the stage owns rollback. Keep standalone Boolean-return behavior compatible. The stage must fail if any event write fails; no report progression after failed persistence. Zero-claim capture persistence is implemented with E01/E02, not used to expand this transaction ticket.

Define a versioned canonical analysis hash from meaningful claim/evidence/determination state, excluding generated IDs/timestamps. Preserve an unchanged approval; changed analysis becomes pending with explicit invalidation metadata, not a fabricated reviewer rejection. Do not build a new multiuser audit subsystem.

**Acceptance:** force the second event of a batch to fail; neither event persists, stage is failed, report does not advance. Standalone store remains tested. Unchanged rerun retains review; changed analysis invalidates it; prior decision metadata is retained. Repeat these tests after E02 expands analysis content.

### B02 — Make source outcomes and checkpoints honest

**Depends on:** approval. **Scope:** `src/ingester/rss.py`, `topic_fetcher.py:_fetch_from_sources`, `src/cases/service.py:_persist_retrieved_articles` and narrow retrieval failure-recording seams, RSS compatibility in `src/ingester/fetcher.py`, ingestion/case tests. No transport/NewsAPI redesign.

Introduce typed/structured acquisition outcomes without breaking list-returning legacy callers: preserve a wrapper where needed. Record requested/attempted/skipped sources and success-empty versus failure. Propagate these into retrieval artifacts and checkpoint metadata. All attempted sources failing is failure; partial success preserves data but is explicitly partial.

**Acceptance:** success-empty, source timeout/error, partial success, all-failed and no-attempted-source cases have distinct outcomes. Failure never advances successful checkpoint time. No real feeds or provider calls in tests.

### B03 — Remove invented operational claims and fix essential reader states

**Depends on:** B00. **Scope:** `MonitoringCenter`, `PipelineMonitor`, `SourceAnalysis`, `NarrativeLandscape`, `CaseIntelligenceCenter`, affected tab state, `Button.tsx`, associated CSS/tests.

Remove synthetic alerts/logs/health values and misleading bias/sentiment/baseline results from the normal app. Preserve real stage/history/count data. Disable unsupported controls with an explanation or replace them with CLI guidance. Fix React Query error branches, route-change stale state and empty-division behavior. Use scoped custom CSS for missing design-system styles rather than adding a new styling framework. Fix directly affected keyboard controls/labels/focus.

**Acceptance:** an empty backend produces no invented activity; errors provide retry and never a blank detail panel; case changes do not retain old evidence; primary controls have real padding/color/focus styling in a browser. `npm run check`, `npm test -- --run`, focused mocked browser checks. No new mutation endpoint.

### E01 — Add immutable evidence captures

**Depends on:** B01. **Scope:** storage models/exports/migrations, event-store capture persistence, proposed `src/cases/evidence.py`, temporary-db migration/store tests; narrow CLI materialization handler only if exposed in this ticket.

Implement specification §4 `EvidenceCapture`, immutable text/hash/metadata and nullable current-capture pointer. Persist/reuse capture versions independently of whether claims exist. Normalize line endings before analysis/persistence consistently. Record actual/unknown times honestly. Provide an explicit service/CLI-only legacy materialization path; no GET or automatic migration backfill.

**Acceptance:** changed text adds a capture; identical text reuses it; old body/hash/metadata remain unchanged; rollback leaves no orphan pointer; zero-claim capture survives; fresh/legacy/idempotent migrations work. Legacy materialization on a synthetic database marks unknown observation time and is repeatable. No historical production data is touched.

### E02 — Add validated quotations and correct relationship counts

**Depends on:** E01, B02. **Scope:** `src/ai/schemas.py:ClaimSchema`, `agents/collector.py`, `ai/workflow.py`, `src/cases/service.py:_process_case_article`, `_build_event_evidence`, `_augment_claims_with_evidence`, `_recompute_case_claim_aggregates`, event store, citation/link models/exports/migrations and focused tests.

Own the small reusable synthetic evidence-workbench fixture in `tests/fixtures/` for subsequent API/browser contract tests. Add optional quote proposals, analysis-input scope and extraction outcome metadata. Validate exact code-point spans against the immutable body. Add the specification's append-only `ClaimCitation` model/migration/export and current-link reference: frozen claim text/identity, capture, passage and assessment survive live link/claim rewrites independently of snapshots. Exactly aligned new collector attachments are `reported_by`; unaligned ones remain `uncertain`, and unassessed legacy links are not counted as support. Add assessment/alignment fields and canonical relation handling. Preserve old payload compatibility and raw legacy relationship diagnostics. Invalid/fallback analysis cannot erase valid prior claims by pretending to be a complete replacement.

**Acceptance:** valid/invalid/ambiguous/missing/out-of-scope quotations; emoji/CJK; CRLF; fallback; `opposes` alias; every relation's count semantics; changed analysis-review hash; identical reruns; unprocessed/failed events retain valid claims; rewritten/deleted live claims and links leave their old immutable citation resolvable. No additional automatic verification model call. Run the full backend suite after focused tests.

### E03 — Expose typed inspector read models

**Depends on:** E02. **Scope:** dedicated readers in `src/cases/`, `src/http/app.py`, `schemas.py`, `mappers.py`, API/service tests; additive TypeScript interfaces when needed for contract fixtures.

Implement proposed citation/claim/evidence/capture GET readers and legacy-safe DTO extensions from specification §9. Citation lookup uses its own saved case/capture ownership and frozen claim text, not a required live claim join. Preserve current tab routes/field IDs. Text windows use code-point lengths and on-demand bodies. Validate ownership for all case/evidence/capture selectors. Add snapshot selector support later in R03; until then an unsupported supplied snapshot selector must fail explicitly, not be silently ignored.

**Acceptance:** API response fixtures for every alignment state; missing/wrong-case resources return 404; invalid ranges 422; full case payloads do not bulk include captures; GET creates no captures or analysis. Existing mutation-route absence tests remain.

### E04 — Build the evidence inspector and deep links

**Depends on:** E03, B03, B00. **Scope:** `frontend/src/types/backend-models.ts`, `services/api.ts`, claim/evidence tabs, small proposed inspector/link helper components and CSS, component/E2E tests.

Implement the existing tab/query-parameter flow with pinned capture and immutable citation IDs, safe code-point highlighting, metadata, relationships, provenance labels, text-window navigation and distinct loading/error/empty/unavailable states. A citation URL renders frozen claim/passage context even after its live claim/link is removed; explain that the current claim is no longer present. Add shared URI-encoded deep-link helpers; don't duplicate link construction in each consumer.

**Acceptance:** keyboard selection, reload/back/forward, legacy data, ambiguous/invalid quote, missing content, case switching, safe external links and source text containing HTML. No false support/confirmation badges. `npm run check`, `npm test -- --run`, Playwright inspection of actual controls. **Release A review gate.**

### P01 — Implement conservative source dependency groups

**Depends on:** E02, E03. **Scope:** proposed `src/cases/provenance.py`, source/claim summary service readers, GET `/sources`, DTOs and deterministic unit/API tests; no separate publisher service.

Implement specification §5 versioned identity/URL/text normalization, explicit dependency edges, connected components and honest unknowns. Do not change existing evidence/claim IDs. Use saved metadata only; no network resolution. Expose grouping reasons and counts with the same policy for case and claim scope.

**Acceptance:** tracking URL normalization without collapsing meaningful parameters; same publisher/copy groups; short snippet non-grouping; unknown publisher; no independence assertion from domain difference; stable results under shuffled inputs; repeatable claim-specific counts.

### P02 — Add deterministic comparison read API

**Depends on:** P01, E03. **Scope:** proposed `src/cases/comparison.py`, typed HTTP contract, route/read tests.

Implement two same-case pinned capture inputs, exact-signature claim alignment, copy warnings and extraction-scope caveats. No LLM calls or inferred semantic contradictions. Paginate alignment rows. Old selected captures must not accidentally use the latest claim links: v1 returns matching persisted capture-linked assessments, or explicitly unavailable historical comparison analysis until a snapshot is selected/supported in R03. Individual immutable citation links remain inspectable without a snapshot; do not combine historical assessments into an invented analysis version.

**Acceptance:** shared/left-only/right-only extracted assertions, explicit assessed contradiction, duplicate warning, missing/invalid/wrong-case captures, different-ID validation and stable pinned selections. Comparison reads do not mutate storage.

### P03 — Build comparison navigation and panels

**Depends on:** P02, E04. **Scope:** evidence selection controls, a small comparison page/tab, `CaseIntelligenceCenter` navigation/routes, existing API/link helpers, CSS/tests.

Allow two evidence selections, link to compare from the normal case workflow, persist choices/capture versions in URL and render two source/passage panels with the alignment table. On mobile stack panels. Use “not extracted” wording and provenance warnings, not bias/factuality scores.

**Acceptance:** both source passages reachable, pinned comparison survives refresh, duplicate and partial-extraction caveats visible, keyboard/mobile/error cases, frontend gates and focused browser verification. **Release B review gate.**

### R01 — Add grouped invocation identity and propagation

**Depends on:** B01, B02, E02. **Scope:** `InvestigationRun` model/migration/exports; `CaseRunContext`, `run_case`, reruns/monitor dispatch, `_execute_stage`, `_mark_stage_running`; focused temporary-db tests.

Create one invocation ID/sequence and pass it through stages without repurposing existing stage FKs. Record coverage/outcomes/parameters and origin references. Existing stage history remains readable; legacy origins remain null/unknown. This is internal foundation only: do not deploy/use grouped runs before R02's exclusion/fencing and R03's finalization contract are integrated.

**Acceptance:** one ID across stages; new ID on rerun; full/scoped/paused/failed statuses; origin references; migration/legacy compatibility and stage API regression tests. This ticket does not claim concurrency safety or snapshot-ready success semantics.

### R02 — Enforce case writer admission, fencing and explicit recovery

**Depends on:** R01. **Scope:** small transactional guard helper/owner fields; admission and commit checks for case mutation paths; CLI interrupt handler and ownership/race tests.

Protected-path checklist: `run_case`/rerun/monitor stage writes; `ingest_articles` and URL intake when case-bound; `_process_intake_item` case article/event/metrics writes; `review_case`; `update_exception_status`; any direct case-bound `store_event_in_db` caller. Enumerate actual call sites before editing; helper methods inherit the caller's token and must not acquire conflicting nested owners. Purely unassigned intake is outside the case guard. Known external direct-SQL scripts remain unsupported writers, not falsely protected ones.

Atomically claim/release a case owner token. Validate it in every case-bound write transaction, including after awaited external work. An explicit CLI-only interrupt requires matching owner/run ID, reason and confirmation; atomically mark it interrupted/invalidate ownership. It does not claim to stop the process. Its old token cannot commit even after a new writer starts. No elapsed-time or GET-side recovery.

**Acceptance:** conflicting automatic/intake/review/exception writes rejected; paused/finalized operations release ownership; a resumed invocation gets a new owner; interrupted writer's later event/checkpoint/report-pointer commits fail. Keep an explicit test matrix covering every protected path. No deployment before this inventory and tests pass.

### R03 — Persist observational snapshots, deltas and historical readers

**Depends on:** R02, P01, E03. **Scope:** `CaseSnapshot` model/migration; proposed `src/cases/history.py`; run finalization; snapshot-aware inspector/comparison readers; run-specific report output; new GET contracts and tests.

Implement specification §7 exactly: snapshots observe committed state, not an imaginary whole-case transaction. Freeze successful baseline selection; retain origin of earlier failed-run stage commits or mark unknown. Include immutable citation/capture/relationship and before/after claim state; exclude volatile fields. Scoped runs preserve untouched state; missing feed items never remove articles. Add snapshot-aware claim/evidence lookup and historical comparison semantics.

Follow the specified file/DB protocol: build report in a same-filesystem sibling directory, flush and atomically rename to its immutable run path, then commit guarded success/snapshot/delta/artifact/pointer records together. File failure cannot produce success; DB failure may leave a reported unreferenced directory but no published pointer/baseline. No required output publication after success commit and no overwrite of older run reports.

**Acceptance:** first/unchanged/changed/partial/scoped/fallback/failed/paused cases; no false removals; current-row replacement does not break old views; review/exception observations do not invent actor attribution; file-write/rename/DB-finalization failures cannot advance baseline; legacy grouped history is not fabricated. API: 404 cross-case, pending/unavailable distinct from empty. Full backend regression suite. If needed, split storage/composition from delta/readers at parent review before expanding the worker's scope.

### R04 — Add truthful changes and grouped history UI

**Depends on:** R03, E04. **Scope:** existing run-history tab and a small changes panel/tab, DTO/client/link helpers/tests; no new global monitoring platform.

Show grouped runs separately from stage attempts, baseline/target/coverage, real delta items and snapshot links. Label initial/pending/unavailable/unchanged appropriately; show partial-coverage warnings even for an empty delta. Historical links use the snapshot-aware readers.

**Acceptance:** no-op generates no change surge; failed/paused runs are not successful baselines; removed live claims remain viewable historically; review-origin unknown stays unknown. Frontend gates and fixture-based browser test.

### S01 — Add transactional case FTS index and explicit rebuild

**Depends on:** E02, E03. **Scope:** proposed `src/storage/search.py`, additive FTS migration/capability checks, event/capture write hooks, narrow CLI rebuild command, index tests.

Probe FTS5 in a temporary database. Index current evidence and current individual claims only. Choose one authoritative transactional synchronization mechanism; do not mix a best-effort async index with source writes. Rebuild uses a supplied database path and includes only valid case-owned application records. Snapshot/capture history remains outside current search.

**Acceptance:** writes/rollback/current-capture change/claim replacement reflected correctly; legacy unowned table excluded; rebuild repeatable; unsupported/missing index has explicit capability status. No auto-index creation on GET and no silent `LIKE` fallback. Migrations never touch the production DB during development.

### S02 — Add case search API and workspace search UI

**Depends on:** S01, E04, P01. **Scope:** resource-specific search reader/DTO/GET handler; case workspace search component, URL/filter/link helpers, unit/API/component/browser tests.

Implement literal all-term query semantics, type/publisher/status/date filters, bounded deterministic pagination, plain-text snippets and deep links from specification §8. A snippet is not a validated source quotation. Query/filters persist in URL. No global/cross-case or vector search.

**Acceptance:** known title/body/claim queries; Unicode and punctuation; raw operator/injection-like strings; invalid selectors/filters/ranges; stable paging; missing FTS 503; correct source version after updates; keyboard/back/forward behavior. Run frontend/backend gates and measure the documented synthetic benchmark without brittle unit-test timing thresholds.

### V01 — Verify Release C and document the delivered architecture

**Depends on:** P03, R04, S02 and all prerequisite checks. **Scope:** deterministic fixtures/end-to-end tests, CI verification paths, current architecture/API/operator documentation and residual risk notes.

Run the specification §11 journey on a scratch runtime/DB. The E2E launcher must receive/use a temporary config and DB rather than starting the default live backend. Verify fresh installation, all test/check commands, GET-only boundary, safe source rendering and no synthetic values. Update delivered architecture docs and mark only proven plan criteria complete. Record remaining security/data/deployment blockers.

**Acceptance:** parent verifies actual diffs and outputs; no skipped required gate presented as success; no production data modified; documentation/contract links valid. **Release C review gate; production deployment still separately approved.**

## 4. Explicit separate gate — historical data recovery

The audit found a separate `CaseArticle` table, orphan official case articles and no migration history. No ticket above authorizes merging/dropping tables or changing historical case ownership.

A future **D01** must first produce a backup/restore and dry-run reconciliation plan: stop external writers, use consistent SQLite backup, hash/inventory captured files, identify row duplicates/provenance, define valid ownership/import-to-intake rules and rehearse restoration. Owner approves that plan before a worker applies it. Enabling production-wide FK enforcement and retiring ingestion helpers depend on this separate gate.

## 5. Verification contract for every worker

Required where applicable. Following the B02 incident, run backend verification from a disposable project copy; never use the production-configured runtime. The new test fixture guards application database calls during test execution, not raw SQLite, collection-time setup or subprocesses. See the [incident and safety controls](../reference/20261115-test-database-incident.md).

```bash
# Python: frozen dependencies and bounded tests, no paid provider use
uv sync --frozen --all-extras
env LLM_API_KEY= OPENAI_API_KEY= LANGSMITH_TRACING=false uv run pytest -q
uv run ruff check src tests

# Frontend: non-watch mode, after any frontend change
cd frontend
npm ci
npm run check
npm test -- --run
```

First run focused tests for the task, then the required full gate. Run fresh-install verification in an isolated copy when the current working environment would mask lockfile problems. If `.env` or another provider could still enable external integrations, explicitly disable/mock them; do not print credentials.

Before builds/tests, probe changed code paths with active LSP diagnostics where supported. Browser work must follow the installed playwright-cli skill, use its isolated session, exercise actual controls, record console/network findings and close the worker's own browser/server. E2E browser tests use synthetic data and a temporary DB/config only. Do not reuse an unknown server or personal browser.

For schema/API tasks include fresh/legacy migration tests, case ownership checks, transaction rollback, null/unknown legacy behavior, and existing contract regressions. Preserve the tested CLI-only mutation boundary.

## 6. Copyable worker dispatch brief

Replace placeholders with **one** approved task and concrete current context:

```text
Implement ticket <ID> from docs/plans/20261114-evidence-workbench-worker-plan.md.
Contract: docs/plans/20261114-evidence-workbench-specification.md, sections <N>.
Dependencies completed and independently verified: <IDs and actual outcomes>.

Current baseline: <existing user changes and prior approved ticket changes>.
Read these existing files/symbols before editing: <exact bounded list from task>.
Expected changes: <specific task behavior and module boundaries>.
Do not modify: production DB/data/logs/raw artifacts/scratch scripts, unrelated features,
HTTP mutation boundary, other workers' files or secrets. No recursive agents/workflows,
commits, destructive cleanup, real ingestion or production migrations.

Use uv run for Python commands. After frontend changes run npm run check and
npm test -- --run. Use a scratch DB/config for every runtime/browser check.
Run <focused checks> then <full relevant gates>. Stop and report blockers if the
contract requires scope expansion or a dependency/API/schema change not specified.

Return: completed behavior; exact files/symbols changed; real commands/results;
migration/compatibility notes; remaining risks/blockers. Do not call partial work done.
```

The parent supplies the actual target files and understood implementation change for each task; it must not delegate open-ended “investigate and fix everything” work. After the worker finishes, inspect the diff, verify tests and contracts independently, and only then dispatch the next dependent task. Resume an interrupted worker rather than recreating one with no context.

## 7. Approval and tracking

The owner approved the specification/defaults and the narrow removal of unused `react-simple-maps` and `@types/react-simple-maps`. **B00 completed on 2026-11-15:** DeepSeek applied matching Vitest/coverage 4.1.12, repaired platform-native lock entries, documented Node 24.13.0/npm 11.6.2 and added `.nvmrc`. The parent reviewed the actual diff (unrelated React/Vite/Node-types/ESLint/TypeScript pins preserved), verified active config diagnostics, and independently ran fresh `npm ci`, `npm run check`, 13 tests, coverage and `npm ls --all` from repository files. Coverage smoke: 64.33% statements / 52.15% branches / 54.2% functions / 66.66% lines of the collected suite; not a whole-app coverage guarantee. Logs: `/tmp/triangulate-b00-final-{ci,check,test,coverage,peers}.log`. Production DB hash and all 382 original non-doc untracked paths remained intact at B00 acceptance; see the subsequent B02 incident below. Residual npm audit: 24 entries, 0 critical (13 high, 9 moderate, 2 low), deferred for separate reachability/upgrade review—not claimed fixed. **B01 is complete** with independent verification recorded below. **B02 is accepted** after owner-authorized isolated continuation and independent verification recorded below. **B03 is accepted** with final evidence below; **E01 is accepted** with final evidence below; later tickets remain pending. Record status/test evidence as work actually completes, not from intended behavior or an agent summary. Review Release A before starting B's dependent feature work; review Release B before integrating Release C. The owner has authorized isolated B02 review; do not dispatch B03 before B02 acceptance.

**B01 accepted (2026-11-15):** caller-owned investigation transactions now roll back the entire event batch on failure, with standalone Boolean-return ownership preserved. Review decisions bind a documented versioned analysis hash; equivalent rewrites preserve decisions, meaningful changes invalidate with prior metadata retained. CLI binding and additive migration 7 are covered by fresh/legacy/repeat tests. Review findings were fixed and independently rechecked: checks/stable capture metadata included, verification-check semantic upserts applied before hashing, identity dictionary keys normalized with explicit collision handling, and ordered nested lists preserved except three documented unordered claim sets. Verification checks remain cumulative observations, not an invented authoritative-replacement feed. The parent reviewed actual diffs, corrected minor module-docstring drift, and reran final tests: **156 passed, 9 deselected; Ruff and diff checks passed**. Logs: `/tmp/triangulate-b01-parent-final-{pytest,ruff}.log`. Active hash-helper diagnostics show no new errors; inherited classic-Column ORM false positives were individually triaged, not claimed universally clean. [Delivered transaction/review architecture](../architecture/20261115-review-invalidation.md). At B01 acceptance, the production DB hash and all original 382 non-doc user paths remained unchanged; migration 7 was not run against production. The later B02 incident does not alter that historical verification, but supersedes permission to proceed.

**B02 checkpoint (2026-11-15), not accepted:** the DeepSeek worker left acquisition/checkpoint code and 24 new tests, reporting 180 passing tests. Its focused legacy ingestion test also inserted a test-source row into the default production DB; the worker then deleted that row without approval. The parent disclosed the incident, paused features and preserved a read-only snapshot/manifest. The original byte hash differs; current counts/integrity do not prove complete logical restoration. Parent test-only isolation fixes add a temporary global application DB per test, reject checkout-local application DB paths before engine creation, and mock the legacy unit test's persistence call. A separate reviewer found no blocker in this narrow fix, with raw SQL/import-time/subprocess limitations documented. Parent verification from a disposable project copy: **7 focused tests; 185 passed, 9 deselected overall; Ruff and diff checks passed**. The observed post-incident production DB hash/size/mtime stayed unchanged through these checks; all original user paths remain. The owner authorized resuming isolated B02 review. This was a pre-correction checkpoint; final acceptance is recorded below. The original DB hash mismatch remains disclosed. [Full incident, evidence locations, limitations and owner gate](../reference/20261115-test-database-incident.md). No production remediation is authorized.

**B02 corrective review checkpoint:** the independent reviewer and parent isolated mock probes confirmed four blockers in the first implementation: summary flags could override failed outcomes at checkpoint persistence; recovered bozo/partially parsed feeds could be reported as complete; empty/non-feed responses could be labeled healthy empty; and no-source/no-seed retrieval could continue downstream. The same DeepSeek worker has been resumed with narrow corrections and deterministic regressions. Coverage/counts must be derived from validated source outcomes across metadata, artifacts and metrics, legacy unobserved results remain unknown, usable seed-only context remains distinct, and all verification executes in the disposable project copy. The first correction passed parent verification from the disposable copy: **52 focused tests; 195 passed, 9 deselected overall; Ruff passed** (`/tmp/triangulate-b02-parent-{focused,full,ruff}.log`). Re-review confirmed the original four fixes but found three remaining blockers: skipped outcomes were treated as seed context without matching actual manual/social articles; source identity/duplicate/requested-count reconciliation was insufficient; and parse-failure/warning evidence could be ignored when the explicit degraded flag was false. The same worker applied the remaining corrections, regressions and legacy RSS classification exception guard. The 195-pass result was a pre-acceptance checkpoint; final verification is recorded below.

**B02 accepted (2026-11-15):** structured feed/source outcomes distinguish acquired items, recognized healthy emptiness, failure and skip while retaining legacy list callers. Coverage/counts are derived from validated identities, strategies, attempts, request-count reconciliation and degradation evidence; missing/duplicate/contradictory observations cannot certify completeness. Canonical fields reach artifacts, stage metrics, case metadata and checkpoints; reported summaries remain explicitly untrusted. Only complete requested-scope acquisition advances the retrieval-success timestamp. Failed/no-acquisition runs retain durable diagnostics while failing the stage/case; seed-only context requires actual matching manual/social articles and never advances success. The parent inspected actual bodies/diffs and independently verified **60 focused tests; 203 passed, 9 deselected overall; Ruff and diff checks passed**, from the disposable project copy. Logs: `/tmp/triangulate-b02-parent-final-{focused,full,ruff}.log`. Independent re-review confirmed all identified blockers resolved, including the final supported-strategy and conservative request-bound fixes. [Delivered acquisition architecture](../architecture/20261115-acquisition-outcomes.md). LSP is not globally clean: inherited ORM/optional-row/import diagnostics remain; an existing trafilatura timeout-keyword mismatch is separately deferred as task #16, not falsely called fixed. The post-incident DB hash/size/mtime and all 382 original user paths stayed unchanged during final verification; original byte-identical restoration is not claimed. No production migration, ingestion, repair or deployment is authorized. B03 has now been dispatched under the approved sequential plan: frontend-only removal of invented operational/source/narrative claims, real query/error/empty states and route-safe readers, scoped Button styling/accessibility, mocked component tests and browser checks. The worker must not use the default Playwright launcher (it starts the backend); browser verification uses Vite-only loopback serving and intercepted APIs. No backend/data access, dependencies, mutations or new inspector features are authorized.

**B03 checkpoint, not accepted:** the frontend worker removed synthetic monitoring/source/narrative content, added scoped Button styles and case-keyed readers, and reported 54 component tests plus `npm run check` passing. An initial browser retry test failed because its first-500/next-200 mock was consumed by the app's automatic retry; the worker corrected it to hold failure until the actual Retry click, without weakening production retries, and reported all four safe Vite-only browser checks passing. Monitoring error metrics were also corrected to unknown rather than zero. Independent review and parent body inspection found remaining operational-truth gaps in PipelineFlow's stage-order completion inference/static agent assignments, pipeline error metrics and invalid durations, missing-case narrative state, and absent tab race/browser journey coverage. The worker applied those corrections; parent verification passed `npm run check` and **68 component tests**. An independent safe-browser precheck then produced **2 passed, 1 failed, 5 not run**: the expanded mock router incorrectly returned case-detail objects for one-level endpoints. Parent and reviewer also confirmed that mixed missing timestamps or conflicting timestamp ties could still produce a false latest-stage success. The same worker corrected that bounded chronology edge and the browser fixtures/assertions, with regression coverage. Logs: `/tmp/triangulate-b03-parent-{check,tests,browser-precheck}.log`. SourceAnalysis already has a missing-ID guard; that review warning was refuted. At this checkpoint final checks/re-review were still required; subsequent acceptance is recorded below. All browser work must use the safe Vite-only config and intercepted APIs; no backend/data access is authorized.

**B03 accepted (2026-11-15):** the parent inspected actual frontend changes and independent re-review confirmed the identified blockers resolved. Normal monitoring/pipeline/source/narrative views no longer invent operational telemetry, source scores, sentiment or keyword clusters. Failed reads remain unknown rather than zero; saved attempt outcomes do not follow stage-order inference, and missing/conflicting chronology cannot certify success. Case-scoped readers/store cleanup, genuine Retry flows, URI claim filters, state reset and scoped keyboard-visible Button/stage styling are covered. The parent discovered and restored two accidentally dropped browser journey tests rather than accepting reduced coverage. Final parent gates: **`npm run check` passed; 72 component tests passed; 10 safe mocked Chrome tests passed; diff checks passed**. Logs: `/tmp/triangulate-b03-parent-final-{check,tests,browser}.log`. Browser cases exercise computed button padding/color/focus, empty/error/retry views, source/narrative recovery, actual claim-to-evidence navigation and real UI case switching; the launcher is Vite-only and all APIs/fonts are intercepted. Active frontend LSP found no reported errors across 11 files, but only 6 were confirmed clean and 5 were inconclusive; this is not an all-clean LSP claim. Typecheck/build passed. [Delivered UI architecture](../architecture/20261115-read-only-ui-states.md). The post-incident DB hash/size/mtime and all 382 original user paths remain unchanged; no original DB restoration is claimed. No backend, model, migration, dependency or mutation changes were authorized by this frontend ticket. E01 is now dispatched under the sequential plan. The parent inspected the capture contract, event-store evidence writes, case/intake normalization and zero-claim paths, and migration registry (next version 8). Its bounded worker will add immutable capture versions/current pointers, shared normalization, claim-independent evidence persistence, case-bound zero-claim source retention and explicit service-only legacy materialization. Verification is restricted to the disposable project copy and temporary databases. No automatic backfill/GET materialization, quotation/relationship features, unowned-case invention or production migration is authorized. Existing unrelated CLI preview/no-event behavior is not silently claimed fixed.

**E01 checkpoint, not accepted:** the worker added the capture model/helpers, claim-independent evidence upsert, canonical case-body finalization and migration 8, but its first focused run finished **20 passed, 1 failed** (FK-enforced scratch insertion order); full backend/Ruff gates were not run. Parent inspection and independent review confirmed the legacy pointer lacked its FK and ORM deletion was not guarded. A parent in-memory SQLite probe proved nullable `ADD COLUMN ... REFERENCES` is supported, so parity does not require a table rebuild. The same worker corrected parent/dependent flush order, legacy FK parity, missing-body versus explicit-empty handling, ORM delete protection and UTC observation normalization, plus narrowly identified provenance/identity issues in the extracted evidence upsert. All checks remain confined to the disposable project copy and temporary databases. New classic ORM descriptor warnings do not authorize an unrelated typing migration or blanket suppression; actual FK/full-suite failures remain blockers. This was a pre-acceptance checkpoint; final verification is recorded below.

**E01 accepted (2026-11-15):** immutable capture versions/current pointers, LF-only exact body hashes and separate v1 dependency fingerprints are implemented. Normal ORM updates/deletes are rejected; same evidence/body reuses first metadata/times; missing versus explicit-empty source bodies stay distinct. Shared source upsert no longer depends on claims; canonical source text reaches both analysis and capture, including case-bound zero-claim fallback. Source ownership/null-URL identity and publication/archive provenance are protected. Session-owned parent/dependent flushes pass FK-enforced scratch tests without inner commits. Migration **8** is idempotent/schema-only with fresh/legacy pointer FK parity and no history/content copy; legacy materialization is an explicit service operation with unknown observation time, not a GET/startup path. Independent re-review found no remaining E01 blocker. Parent added the missing parametrized FK parity/enforcement regressions and independently verified **30 focused tests; 229 passed, 9 deselected overall; Ruff and diff checks passed**, in the disposable project copy. Logs: `/tmp/triangulate-e01-parent-final-{focused,full,ruff}.log`. Capture helper/service seam/migration tests have confirmed clean active probes; broader inherited ORM findings and individually reviewed fixed-dictionary DDL audit false positives are not a universal-clean claim. [Delivered capture architecture](../architecture/20261115-immutable-evidence-captures.md). Post-incident production DB hash/size/mtime and all 382 original user paths remain unchanged. No production migration/materialization/repair or original byte restoration is claimed. Quote alignment, citations, relationship counts and authoritative fallback replacement remain E02 work; unrelated unassigned CLI preview behavior was not silently redesigned.

**E02 dispatched (foundation pass, not accepted):** parent inspected collector truncation/envelopes, workflow empty/fallback behavior and case augmentation/party merging; an independent read-only storage plan confirmed the writer/hash/read seams. To keep the approved ticket bounded, pass A adds the exact Unicode/body-input-scope validator, immutable citation/link schema and migration 9, session-owned helpers, shared synthetic fixture and focused regressions. Only after parent inspection will a sequential integration pass change collector metadata, extraction replacement protection, claim-specific quote carry-forward, effective relationships, aggregate eligibility and review hashes. The current collector sees only a 5,000-code-point body prefix; title/summary-only text must not validate a source passage. Unknown scope fails closed. Party merging currently uses positional baseline claims, so integration must not transfer an old quotation onto a different rewritten claim. Historical original claim IDs remain values, not deleting FKs. No independent-source grouping, automatic verifier, endpoint/frontend expansion or production operation is authorized by the foundation pass. **E02 pass A verified, E02 still in progress.** Three checkpoints: (1) models/helper/migration 9 with no tests — parent precheck **24 passed, 6 failed** (version 9 versus still-8 assertions), reproducing collector-metadata, unknown-origin and non-exact-status/anchor paths that wrongly granted support; independent review confirmed those plus lost first origin metadata and implicit autoflush. (2) Corrections plus the fixture/regression matrix — parent **87 focused, 286 passed / 9 deselected**, Ruff clean; re-review then found that only the literal `v1` assessment version was accepted and that the changed-version test exercised the collector default instead of an assessed change. (3) Assessment versions became an opaque preserved-case identifier (only empty/whitespace and explicit unknown sentinels rejected), the trusted-collector flag became a strict boolean, the `AnalysisScope.body_sha256` documentation was corrected and two `type: ignore` lines were replaced with explicit fail-closed assertions. Final parent gates: **96 focused passed; 295 passed, 9 deselected overall; Ruff passed**; probes confirmed assessed `v2` support, sentinel rejection, collector priority, string-`"false"` context and status/flag mismatch. Logs: `/tmp/triangulate-e02a-parent-version-{focused,full,ruff}.log`. Delivered: `ClaimEvidenceLink`/`ClaimCitation` schema, migration 9, exact-span validator, versioned relationship policy, session-owned citation writer, shared synthetic fixture. **Not delivered:** collector quote proposals/analysis scope, extraction-outcome honesty, fallback replacement protection, event-store wiring, aggregate eligibility and review hashes — no produced evidence carries a real quotation yet. [Integration notes](20261115-e02-integration-handoff.md) and the [new-thread pass B handoff](20261115-e02-pass-b-handoff.md) record the exact seams, split and acceptance matrix.

The audit cleanup remains a separate unapproved task. These tickets do not silently authorize archiving completed reports, pruning old frontend files or deleting caches/user scripts.
