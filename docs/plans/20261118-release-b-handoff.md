# Release B handoff: P03 review and Release C (R01–V01)

Date: 2026-11-20. Status: **Release A and Release B are accepted; R01, R02, R03a,
R03b and R03c are delivered, independently reviewed, accepted and pushed, and R04
(changes/grouped-history UI) is delivered and verified with its diff review
pending. Next ticket is S01.** Review evidence lives in the
[worker plan](20261114-evidence-workbench-worker-plan.md) §7 and the architecture
docs. This document is the Release C handoff and remains self-contained for a
fresh agent. Contract authority remains the
[specification](20261114-evidence-workbench-specification.md) and the
[worker plan](20261114-evidence-workbench-worker-plan.md).

## 1. Where things stand

| Item | State |
|---|---|
| Local `main` | Ahead of `origin/main` by the Release B acceptance, R01, R02 and this R03a commit — **not pushed** |
| Release A | Accepted: B00–B03, E01–E04; E04 = `8ee32eb` |
| P01 | `e95bfb2` — conservative source dependency groups |
| P02 | `4d93c12` — deterministic comparison read API |
| P03 | `4226856` — comparison navigation and panels; **Release B reviewed and accepted 2026-11-18** |
| R01 | `ed8459f` — grouped invocation identity; migration 12; committed; **accepted 2026-11-18 after a defect pass** |
| R02 | `0ea524a` — case writer admission/fencing + CLI interrupt; migration 13; committed; **accepted 2026-11-18 after a defect pass** |
| R03a | `44b9870` — snapshots/deltas, guarded finalization, run-specific reports, run/snapshot/changes GETs; migration 14; committed; **accepted 2026-11-18 after a defect pass** |
| R03b | `6c67f86` — snapshot-aware claim/evidence/comparison readers + selector acceptance; no migration; **accepted** |
| R03c | `6c67f86` — change-origin honesty (`originRunId`/`observedByRunId`), count-free semantic projection, explicit read transaction, report path containment; no migration; **accepted** |
| R04 | working tree — case-scoped Changes tab with truthful initial/pending/unavailable/unchanged states, coverage warnings, origin/observed provenance and snapshot-aware historical links; no migration; **diff review pending** |
| Next ticket | **S01 — transactional case FTS index and explicit rebuild (not started)** |
| Migrations | 1..14 (…12 grouped investigation runs, 13 case writer ownership, 14 immutable case snapshots) |
| Frontend gate | `npm run check` green; `npm test -- --run` = **132 tests / 13 files** |
| Backend gate | **553 passed, 9 deselected**; Ruff clean |
| Scratch files | 382 removed after archive at `/tmp/triangulate-scratch-archive-20261118T005339Z.tar.gz` (382/382 verified, sha256 `6a38b51c41a7542819f30d23bddc0a83ebb07f8b9eda943df69e554314bad4e5`); no untracked scratch files remain |
| Production data | untouched; B02 test-database incident remains disclosed |

P01/P02/P03 docs:

- [source dependency groups](../architecture/20261118-source-dependency-groups.md)
- [comparison read API](../architecture/20261118-comparison-read-api.md)
- [comparison UI](../architecture/20261118-comparison-ui.md)

## 2. First actions in the new thread (completed for Release B)

1. ~~Read this handoff, the worker plan and specification §5–§11.~~ Done.
2. ~~Review the P03 commit/diff (`git show 4226856`) and the three P01–P03
   architecture docs.~~ Done; no blocker found, no P03 fix required.
3. ~~Re-run the gates (§7) and repeat the focused browser check with a temporary
   DB/config.~~ Done on 2026-11-18: frontend check green, 107 tests / 12 files,
   backend 456 passed / 9 deselected (disposable copy), Ruff clean. Focused
   browser check passed with 47 backend GETs, 0 non-GET and 0 happy-path console
   errors; runtime evidence at `/tmp/triangulate-p03-browser.20261118T104309Z`.
4. ~~Record Release B acceptance in the worker plan and commit the documentation.~~
   Recorded (`aaa4f16`). R01 was committed (`ed8459f`) and R02 committed
   (`0ea524a`).
5. R03a/R03b were independently reviewed; a bounded **defect pass**
   (R01/R02/R03a) plus **R03c** were completed, re-reviewed and pushed. **R04 is
   now delivered and verified** (frontend-only, 132 tests / 13 files, isolated
   browser check). **Implement S01 only.** One bounded ticket at a time, parent
   review after each.

## 3. P03 delivered behaviour

- **Compare** tab in the normal case navigation (`/cases/{case_id}/compare`),
  no hand-entered route required.
- URL is the sole selection authority:
  `?left=&right=&leftCapture=&rightCapture=&offset=`.
  Reload, back/forward and case switching re-derive from it; API-resolved default
  capture IDs are pinned into the URL.
- Two native source selects (opposite source disabled), capture-version selects,
  Swap, Clear and Compare actions; keyboard traversal works.
- Two source panels show title/publisher, safe original/canonical links,
  publication/capture times, capture ID/kind, code-point length, content hash,
  recorded analysis scope, publisher key/provisional-host note and capture-link
  coverage.
- Alignment table uses exact `claim_signature` only:
  shared / left-only / right-only, per-side passages with quote, ranges,
  relationship, alignment, assessment provenance and **Open captured passage**
  links into the E04 inspector.
- Explicit contradiction only from validated `contradicts`; textual difference
  never creates one. Dependency/copy warnings use P01 and say “not independent”
  or “does not prove independence”.
- Historical capture unavailability is explicit; current links are never
  substituted. Empty, loading, 404, retry, unsafe-link and same-source states are
  distinct.
- Mobile: panels stack below 960 px; table becomes labelled blocks below 760 px.
- Pagination keeps `offset` in the URL; results heading receives focus once per
  selection key.

Previous browser evidence (isolated session, temp DB/config):

- default captures pinned; reload persisted
- passage link opened the inspector with the correct highlight; Back returned
- old capture showed historical unavailability
- mobile 390 px stacked panels/table
- 404 state for missing evidence
- console **0 errors**; comparison/evidence requests GET-only
- browser and both servers closed

## 4. Release B review checklist (completed 2026-11-18)

- [x] P01 policy matches §5: URL normalization, explicit/provisional publisher
      identity, 200-non-whitespace copy threshold, deterministic groups, honest
      unknown/independence states.
- [x] P02 matches §6: different evidence IDs, pinned capture validation, exact
      signature pairing, explicit contradiction only, old-capture no-substitution,
      copy warnings, pagination, GET-only.
- [x] P03 matches §6 UI: normal navigation, URL persistence, both passages
      reachable, partial/duplicate caveats visible, trustworthy wording,
      keyboard/mobile/error states.
- [x] No false support/confirmation signals; reported-by is not corroboration.
- [x] `npm run check`, `npm test -- --run`, backend disposable-copy suite and
      Ruff all pass.
- [x] Acceptance recorded in the worker plan §7 and the comparison UI doc; P03
      remains the Release B gate.

## 5. Remaining work map

Because R01/R02 are committed and R03a is delivered, the remaining order after
the R03a review is **R03b → R04 → S01 → S02 → V01**. R03b is the other half of
the R03 ticket (snapshot-aware claim/evidence/comparison readers); S01 depends on
E02/E03 and is technically independent of the R lane, but shared
storage/event-store writers mean one application-code writer at a time.

### R01 — Grouped invocation identity (internal only) — **delivered, accepted, committed**

Delivered in the working tree on 2026-11-18 (migration 12, not committed): one
`InvestigationRun` per `run_case` with per-case sequence, trigger, requested start
stage, parameter snapshot, predecessor, status, coverage/details, timestamps and
error; nullable grouped-run references on `CaseStageRun` and `Event` (while
`Event.case_run_id` stays the stage FK); one ID propagated through stages,
invocation events, reruns and monitor dispatch. Coverage is derived from recorded
stage outcomes (failed/paused/complete/partial/not-attempted/unknown) and never
upgraded from a legacy unobserved retrieval. Snapshot IDs stay null. Full gate
**462 passed, 9 deselected**, Ruff clean; see the worker plan §7 and
[grouped-run architecture](../architecture/20261118-investigation-runs.md).
Review the diff before starting R02; do not deploy/use grouped runs for change
semantics before R02 fencing and R03 finalization.

The original R01 scope (now delivered) was:

- Add `InvestigationRun` model/migration/exports; one `run_case` invocation ID
  and per-case sequence, trigger, requested stage, parameter snapshot,
  predecessor, status, coverage, timestamps, error, baseline/result snapshot IDs.
- Add nullable grouped-run references to `CaseStageRun` and `Event`; keep
  `Event.case_run_id` as the stage FK. Existing stage history stays readable;
  legacy origins stay null/unknown.
- Pass one ID through stages; a rerun/resume gets a new ID. Full/scoped/paused/
  failed statuses and origin references.
- **Do not deploy/use grouped runs before R02 fencing and R03 finalization.**
  Migration/legacy regression tests required.

### R02 — Case writer admission, fencing and explicit recovery — **delivered, accepted, committed**

Delivered in the working tree on 2026-11-18 (migration 13): nullable `owner_token`,
`owner_kind`, `owner_ref_id` and `owner_claimed_at` on `topic_cases`, plus
`src/storage/write_guard.py` primitives. Case preparation, the ownership claim and
the grouped-run row commit atomically; every case-bound stage start/commit/failure,
pause and finalization validates the token, so an interrupt during awaited work
rolls back events, artifacts, diagnostics, checkpoints and report pointers.
Case-bound intake holds the claim across analysis; review/exception/annotation/
evaluation/OSINT writes use short claim/write/validate/release transactions; direct
case-bound event writes reject a foreign active owner. `case owner` shows the active
kind/reference without the token; `case interrupt` requires a reason, explicit
confirmation and a matching reference/token, atomically clears ownership and marks
the running invocation `INTERRUPTED`. HTTP conflicts return 409. Explicit non-claims:
process death leaves a claim until the operator interrupts; no elapsed-time or
GET-side recovery; external direct-SQL scripts remain unfenced. Full gate **475
passed, 9 deselected**, Ruff clean; see the worker plan §7 and
[case-writer architecture](../architecture/20261118-case-writer-fencing.md).
Review the diff before starting R03.

The original R02 scope (now delivered) was:

- Small transactional guard/owner fields; protect `run_case`/rerun/monitor stage
  writes, case-bound intake/URL intake, `_process_intake_item`, `review_case`,
  `update_exception_status`, and direct case-bound `store_event_in_db` callers.
- Atomically claim/release a case owner token; validate it in every case-bound
  write transaction, including after awaited work. CLI-only interrupt with
  reason/confirmation invalidates ownership; old tokens cannot commit.
- Enumerate actual call sites before editing. Purely unassigned intake is outside
  the guard. No elapsed-time or GET-side recovery.
- Explicit test matrix per protected path; paused/finalized release ownership;
  resumed invocation gets a new owner; interrupted later commits fail.

### R03a — Snapshots, deltas, finalization and run APIs — **delivered, accepted**

Delivered in the working tree on 2026-11-18 (migration 14): immutable
`CaseSnapshot` payloads with a stable semantic projection/hash and stored typed
deltas; successful runs compose under a read transaction, write an immutable
run-specific report directory (temp → atomic rename), then publish
snapshot/delta/artifacts/pointers in one owner-guarded transaction. File failure
cannot produce success; DB failure after rename leaves no pointer/baseline;
failed/paused runs never advance the baseline; article removals are never
inferred and claim removals require current-run authoritative extraction. New
GETs: grouped run list/detail, run changes (`initial|ready|pending|unavailable`)
and snapshot summary, with cross-case/unknown 404. Full gate **487 passed, 9
deselected**, Ruff clean; see the worker plan §7 and
[snapshot architecture](../architecture/20261118-case-snapshots.md).

### R03b — Snapshot-aware historical readers — **delivered and accepted**

Delivered in the working tree on 2026-11-18 (no migration): `GET
/claims/{claim_id}`, `GET /evidence/{evidence_id}` and `GET /comparison` accept an
optional `snapshotId` (`snapshot_id` alias where the route already declared it)
and resolve every entity from the snapshot's frozen `payload_json`, never from
live joins. Claim detail returns frozen text/signature/status/type/party
positions/stored counts and payload link passages whose `effectiveRelation` is
resolved by the same policy; evidence detail returns frozen metadata, the frozen
`currentCaptureId`, snapshot capture references (code-point length read only from
the immutable capture row verified against the recorded hash) and frozen related
claims; comparison pins both captures and pairs claims/links/citations from the
payload with the same exact-signature/contradiction/dependency rules and an
explicit pinned-observation caveat. Removed or rewritten claims stay readable
(`liveState` reports present/text-matches), and no actor, truth, corroboration or
independence is invented. Unknown/wrong-case snapshot → 404, entity absent from
the snapshot → 404 (distinct message), malformed/conflicting/empty selector → 422,
unverifiable capture body → `unavailableCaptureIds` (comparison 404s), and every
reader without historical support (case detail, tabs, claims/overview lists,
sources, citations, report, run/snapshot readers, capture windows) rejects the
selector explicitly. Additive payload
fidelity fields do not change `semanticHash`. Full gate in the disposable copy:
**543 passed, 9 deselected; Ruff clean**; frontend type-only addition of the new optional fields with `npm run check` green and 107 tests / 12 files. See the
[snapshot architecture](../architecture/20261118-case-snapshots.md).

### R03c — Change-origin honesty and consistent observation — **delivered and accepted**

Committed as `6c67f86` on 2026-11-18 (no migration). Each delta item now
records the two separate facts: `originRunId` is the entity's recorded grouped run
(`Event.investigation_run_id`, baseline observation for removals) or `null` when
nothing recorded it, and `observedByRunId` is the run whose observation produced
the item. Articles, exceptions and links have no run of their own, so they stay
`unknown` instead of being attributed to the observer or inheriting the claim's
origin. Derived counts (claim support/oppose/source-diversity, narrative source
count) left the semantic projection, so a count-only difference can no longer
change `semanticHash` or imply a change without a typed item. Snapshot composition
opens an explicit SQLite read transaction (pysqlite does not issue `BEGIN` for
plain queries), and report destinations are refused if any component below the
case output directory is a symlink. Full gate **553 passed, 9 deselected; Ruff
clean**; logs `/tmp/triangulate-defectpass-{full,ruff}.log`. Note: removing the
counts changes `semanticHash` for observations taken after the fix; typed deltas
are unaffected.

### R04 — Changes and grouped history UI — **delivered and verified**

Delivered on 2026-11-20 (frontend-only, no migration): a case-scoped **Changes**
tab (`/cases/{case_id}/changes`) showing grouped runs separately from the untouched
stage-oriented Run History, driven entirely by the URL (`run`, `offset`, plus
`claim`+`snapshot` for the inline frozen-claim panel). States are distinct —
`initial` (“not a surge of new changes”), `pending`, `unavailable` (“not an empty
delta”, plus “failed/paused/interrupted never advances the successful baseline”),
`ready` with items, `ready` with none (“unchanged — no changes in observed data”).
Incomplete coverage is conspicuous even for an empty delta, including the “not
that every source was unchanged” caveat. Each row separates `originRunId`
(“Recorded by run …”, or “origin not recorded”) from `observedByRunId` and never
says who changed a value; “no longer extracted” is not a retraction. Historical
links use the snapshot readers: inline frozen claim (target, or baseline for a
removed claim) with live-state wording and passages, evidence inspector with the
pinned `snapshotId` for capture changes, safe external links for articles, and no
invented link for link-level/review/exception rows. Gates: `npm run check` green,
**132 tests / 13 files**; isolated Vite-only browser check with intercepted APIs
(no backend, no database) verified every state plus removed-claim readability, the
pinned-snapshot inspector link, 390 px single-column layout, **0 non-GET requests
and 0 console errors** after interception. Evidence:
`/tmp/r04-changes-desktop.png`, `/tmp/r04-browser-result.txt`,
`/tmp/r04-vite.log`. See the
[changes UI architecture](../architecture/20261120-changes-ui.md).

- Existing run-history tab plus a small changes panel/tab; DISTINCT from stage
  attempts. Baseline/target/coverage, real delta items, snapshot links.
- Label initial/pending/unavailable/unchanged correctly; partial coverage is
  conspicuous even for an empty delta. Historical links use snapshot-aware
  readers.
- No-op creates no change surge; failed/paused are not successful baselines;
  unknown review origin stays unknown. Frontend gates + fixture browser check.

### S01 — Transactional case FTS index and explicit rebuild

- `src/storage/search.py`, additive FTS migration/capability checks, write hooks,
  narrow CLI rebuild command, index tests.
- Probe FTS5 in a temporary DB. Index current evidence and current individual
  claims only. One authoritative transactional synchronization mechanism; no
  best-effort async index.
- No auto-index on GET; no silent `LIKE` fallback; unsupported index has explicit
  capability status. Rebuild repeatable and case-owned only.

### S02 — Search API and workspace UI

- Resource-specific search reader/DTO/GET, case workspace search component,
  URL/filter/link helpers, unit/API/component/browser tests.
- Literal all-term semantics, type/publisher/status/date filters, deterministic
  pagination, plain-text snippets and deep links. A snippet is not a validated
  quotation.
- Query/filters persist in URL; no global/cross-case or vector search.
- Missing FTS → 503 with operator remedy. Measure the documented synthetic
  benchmark without brittle timing unit tests.

### V01 — Release C verification and documentation

- Deterministic fixtures/E2E, CI paths, current architecture/API/operator docs,
  residual risk notes.
- Run the §11 journey on a scratch runtime/DB; E2E launcher must use temporary
  config/DB, never the default live backend.
- Verify fresh install, all gates, GET-only boundary, safe rendering and no
  synthetic values. Mark only proven plan criteria complete.
- **Release C review gate; production deployment is separately approved.**

### D01 — Historical data recovery (separate gate)

Do not merge/drop tables or change historical case ownership under these tickets.
A future D01 needs backup/restore, dry-run reconciliation, owner approval before
any data write. The audit’s orphan `CaseArticle`/lineage findings remain outside
Release C implementation.

## 6. Safety and operating rules

- Run backend Python/tests **only** in the disposable copy recorded in
  `/tmp/triangulate-safety-verification-dir`. Copy only `src/` and `tests/`
  (`tar --exclude='__pycache__' --exclude='*.pyc' -cf - src tests | tar -C "$SAFE_DIR" -xf -`),
  plus `bias_taxonomy.toml`.
- Never copy/commit `data/`, `triangulate.db`, `.env`, `logs/`, `config.toml`, or
  the scratch archive. Never run ingestion/cleanup/migrations against the live DB.
- Browser work follows the playwright-cli skill: isolated session, temporary DB
  and config, real controls, record console/network findings, close your own
  browser/server. A prior seed helper is
  `tests.test_p02_comparison_api.seed_workbench(tmp_path)`.
- No commits, resets, branches, dependency changes, pushes or deletions on `main`
  without owner instruction. Local `main` is already 7 commits ahead of origin.
- One application-code writer at a time. New migrations: allocate the next
  number from the then-current registry; do not reserve conflicting versions.
- Preserve the CLI-only mutation boundary; no new public mutation endpoints.
- Keep scratch work in `/tmp`; do not recreate untracked root scripts.

## 7. Commands

```bash
# frontend
cd /home/howt/work/triangulate/frontend
npm run check
npm test -- --run

# backend (disposable copy only)
SAFE_DIR=$(head -1 /tmp/triangulate-safety-verification-dir)
cd /home/howt/work/triangulate
tar --exclude='__pycache__' --exclude='*.pyc' -cf - src tests | tar -C "$SAFE_DIR" -xf -
cp bias_taxonomy.toml "$SAFE_DIR"/ 2>/dev/null || true
cd "$SAFE_DIR"
env LLM_API_KEY= OPENAI_API_KEY= LANGSMITH_TRACING=false uv run pytest -q --disable-warnings
uv run ruff check src tests --output-format concise
```

## 8. Known caveats

- P03 is committed and **accepted as Release B** (2026-11-18).
- R01 (`ed8459f`, migration 12) and R02 (`0ea524a`, migration 13) are committed.
- R03a, R03b, R03c and the R01–R03a defect pass are accepted and pushed; R04 is
  implemented and verified with its diff review pending.
- R04 does not poll pending runs: Refresh refetches the run list and the selected
  delta, and the case header keeps its existing case-detail polling. Link-level
  (`relationship_changed`) rows show before/after without a navigation link because
  no link reader exists.
- `snapshotId` names a *published* observation; a running invocation has no
  snapshot ID, so there is no reader-side pending state (the run-level `changes`
  contract keeps `initial|ready|pending|unavailable`).
- Historical comparison sides require the immutable capture body: if a snapshot's
  recorded hash no longer matches the stored capture row, evidence detail lists it
  in `unavailableCaptureIds` and the comparison 404s instead of degrading
  silently.
- Local `main` is ahead of `origin/main` (Release B acceptance, R01, R02 and this
  R03a commit) and has not been pushed.
- Snapshots are observations of committed state, not a whole-case transaction;
  report publishing is now run-specific and only a successful guarded
  finalization moves the current report pointers.
- A process death can leave a case ownership claim until an operator runs
  `triangulate case interrupt` (explicit CLI recovery); there is no elapsed-time
  or GET-side recovery, and external direct-SQL scripts remain unfenced.
  `interrupt` now rejects a reference that is missing or not `RUNNING` (rolling the
  ownership clear back) and exits nonzero on any non-interrupting path.
- Change items report `originRunId` (the entity's recorded run, or null) separately
  from `observedByRunId` (the observing run). Articles, exceptions and links have no
  recorded run, so their origin is `null` by design — never the observer and never
  the claim's event run. `originRunId` is provenance, not "who changed this field".
- The semantic projection no longer includes derived claim/narrative counts, so
  `semanticHash` values taken before that fix differ from later ones for identical
  data; typed deltas are unaffected because they compare fields, not hashes.
- The scratch archive is in `/tmp` and is not durable across a machine cleanup;
  copy it somewhere durable if the old one-offs must be retained.
- P02 test fixtures now expose `seed_workbench(tmp_path)` for browser seeding;
  P03 tests use mocked APIs.
- Timestamps are returned as persisted; SQLite drops `tzinfo` and the UI does not
  invent an offset.
- `sourceDiversityCount` remains a compatibility field, not an independence count.
- No `.pi-lens.json` ignore file was added; the scratch-file cascade is gone
  because the files were archived/removed.

## 9. Paste-ready S01 dispatch brief

```text
Implement ticket S01 (transactional case FTS index and explicit rebuild) from
docs/plans/20261114-evidence-workbench-worker-plan.md
(contract: docs/plans/20261114-evidence-workbench-specification.md §8).

Start by reading, in this order:
1. docs/plans/20261118-release-b-handoff.md (current state, safety rules)
2. docs/architecture/20261120-changes-ui.md (what R04 consumes) and
   docs/architecture/20261118-case-snapshots.md
3. the storage layer (src/storage/database.py, models.py, migrations.py,
   event_store.py, captures.py), the case service mutation paths and the CLI
   command surface (src/cli/main.py, src/cli/commands/cases.py).
4. specification §8 (search) and the audit note on why LIKE fallbacks and
   best-effort async indexing are rejected.

CURRENT STATE (2026-11-20)
- Release A/B accepted; R01, R02, R03a, R03b, R03c pushed; R04 delivered and
  verified (frontend 132 tests / 13 files, check green) with review pending.
- Backend 553 passed / 9 deselected, Ruff clean; migrations 1..14.
- Next ticket after S01 is S02 (search API + workspace UI).

SCOPE
- Add one transactional case-scoped FTS5 index over current evidence and current
  individual claims, with an additive migration and an explicit capability probe.
- Index writes must be part of the same transaction as the case-bound write that
  changes the row (no best-effort or async queue), and must respect the R02
  owner/fencing rules. No GET may create or rebuild the index.
- Unsupported FTS must report an explicit capability status; no silent LIKE or
  scan fallback, and no cross-case/global index in this ticket.
- Add a narrow CLI rebuild command that is case-owned, repeatable and idempotent;
  a rebuild must refuse a case with an active foreign writer.
- Probe FTS5 availability in a temporary database and keep every test hermetic.

OUT OF SCOPE
Search read API and UI (S02), vector/semantic search, production deployment,
historical-data recovery, unrelated refactors, snapshots or changes work.

SAFETY
- Run backend Python/tests only in the disposable copy recorded in
  /tmp/triangulate-safety-verification-dir. Copy only src/ and tests/ plus
  bias_taxonomy.toml.
- Never touch data/, triangulate.db, .env, logs/, config.toml or the scratch
  archive; no ingestion, cleanup or migration against the live database.
- Allocate the next migration number from the then-current registry and stop for
  review if more than an additive index table is required.
- No commits, resets, branches, dependency changes, pushes or deletions without
  owner instruction. Keep scratch work in /tmp. One application-code writer.
- Preserve the CLI-only mutation boundary and the GET-only read boundary.

RETURN
Behaviour delivered; exact files/symbols/migration changed; index capability and
failure semantics; write-path and rebuild idempotency evidence; real migration and
test output (focused, full, Ruff); remaining risks/blockers. Do not call partial
work done.
```
