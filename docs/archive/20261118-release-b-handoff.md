# Release B handoff: P03 review and Release C (R01–V01)

> **Status note (2026-11-22): the state recorded below is the pre-push
> checkpoint of 2026-11-21 and is preserved as history. Release C was pushed to
> `origin/main` as `dca1691`; `origin/main` now resolves to `d589359`. Current
> status lives in [remaining work after Release C](../plans/20261121-remaining-work-after-release-c.md);
> this handoff is an accepted historical record.
> Archive label: implemented 2026-11-21 (moved to `docs/archive/` 2026-11-22).
> D01 and deployment remain separate owner gates.**

Date: 2026-11-20 (updated 2026-11-21). Status: **Release A and Release B are accepted; R01, R02, R03a,
R03b and R03c are delivered, independently reviewed, accepted and pushed; R04
(changes/grouped-history UI) is accepted after its review fix (`dfc809c`), and
Release C (S01, S02, V01) is implemented, reviewed and verified locally —
committed (`3096c0f`, `5501842`, `0ae9359`, `b92c453`, `ff838cc`, `3594d1c`,
`2fd91a2`, `19f42e3`, `0db8971`) and not pushed. Nothing remains to implement;
the next step is owner review/push. D01 and deployment are owner gates.** Review evidence lives in the
[worker plan](../plans/20261114-evidence-workbench-worker-plan.md) §7 and the architecture
docs. This document is the Release C handoff and remains self-contained for a
fresh agent. Contract authority remains the
[specification](../plans/20261114-evidence-workbench-specification.md) and the
[worker plan](../plans/20261114-evidence-workbench-worker-plan.md).

## 1. Where things stand

| Item | State |
|---|---|
| Local `main` | 13 commits ahead of `origin/main` (`81b8778`); code head `0db8971` plus this documentation commit — Release B acceptance, R01–R04 and all of Release C — **not pushed** |
| Release A | Accepted: B00–B03, E01–E04; E04 = `8ee32eb` |
| P01 | `e95bfb2` — conservative source dependency groups |
| P02 | `4d93c12` — deterministic comparison read API |
| P03 | `4226856` — comparison navigation and panels; **Release B reviewed and accepted 2026-11-18** |
| R01 | `ed8459f` — grouped invocation identity; migration 12; committed; **accepted 2026-11-18 after a defect pass** |
| R02 | `0ea524a` — case writer admission/fencing + CLI interrupt; migration 13; committed; **accepted 2026-11-18 after a defect pass** |
| R03a | `44b9870` — snapshots/deltas, guarded finalization, run-specific reports, run/snapshot/changes GETs; migration 14; committed; **accepted 2026-11-18 after a defect pass** |
| R03b | `6c67f86` — snapshot-aware claim/evidence/comparison readers + selector acceptance; no migration; **accepted** |
| R03c | `6c67f86` — change-origin honesty (`originRunId`/`observedByRunId`), count-free semantic projection, explicit read transaction, report path containment; no migration; **accepted** |
| R04 | `44f1e58` — case-scoped Changes tab with truthful initial/pending/unavailable/unchanged states, coverage warnings, origin/observed provenance and snapshot-aware historical links; no migration; **accepted after review fix `dfc809c`** |
| S01 | `3096c0f`, `5501842` — transactional case FTS5 index (migration 15), deterministic rowids, CLI `case rebuild-search`; **implemented, reviewed and verified locally, not pushed** |
| S02 | `0ae9359`, `b92c453`, `ff838cc`, `3594d1c` — `GET /api/cases/{case_id}/search` and the workspace Search tab with URL-persisted state; **implemented, reviewed and verified locally, not pushed** |
| V01 | `2fd91a2`, `19f42e3`, `0db8971` — Release C journey test/fixture, browser E2E and documentation; **verified locally, not pushed** |
| Next ticket | **None — Release C is complete locally.** Next step is owner review/push per the [completion map](20261120-release-c-completion-map.md); D01 and deployment remain owner gates |
| Migrations | 1..15 (…12 grouped investigation runs, 13 case writer ownership, 14 immutable case snapshots, 15 optional case FTS5 index) |
| Frontend gate | `npm run check` exit 0; `npm test -- --run` = **164 tests / 14 files** |
| Backend gate | **614 passed, 9 deselected** (`tests/test_v01_e2e.py` is the 614th); Ruff clean over `src tests scripts` |
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
   accepted** after its review fix (`dfc809c`; frontend-only, 132 tests / 13 files
   at delivery, isolated browser check, committed `44f1e58`). **Release C is now
   complete locally**: S01 (`3096c0f`, `5501842`), S02 (`0ae9359`, `b92c453`,
   `ff838cc`, `3594d1c`) and V01 (`2fd91a2`, `19f42e3`, `0db8971`) are
   implemented, reviewed and verified locally and not pushed. Verification
   evidence (worker-plan §7 final entries): backend **614 passed / 9 deselected**
   with Ruff clean over `src tests scripts`; frontend `npm run check` exit 0 with
   **164 tests / 14 files**; clean-export fresh install green (init reaches
   migration 15); journey test 275 GET-only requests with byte-identical
   index/`_migrations` dumps and unchanged live DB sha256 (`049a8a9d…d9f86`);
   Chrome Playwright-CLI browser run covering search, filters, URL persistence,
   inspector (capture + historical `snapshot` key), the Changes-tab frozen-claim
   link, empty/404/503-with-remedy states, keyboard submit and literal
   markup-title rendering (no Firefox/Safari matrix, no load test, no mobile
   viewport). Final docs: [search index](../architecture/20261120-search-index.md),
   [search read API](../architecture/20261120-search-api.md),
   [HTTP API](../reference/http-api.md), [CLI](../reference/cli.md),
   [CLI operations](../reference/cli-operations.md) (503 runbook and the
   `VITE_API_BASE_URL` requirement). Next: owner review/push; D01 and production
   deployment are separate owner gates.

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
the R03a review is **R03b → R04 → S01 → S02 → V01**. All of these are now
delivered; S01/S02/V01 are verified locally and recorded below. R03b is the other half of
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

### S01 — Transactional case FTS index and explicit rebuild — **delivered, reviewed and verified locally**

- `src/storage/search.py`, additive FTS migration/capability checks, write hooks,
  narrow CLI rebuild command, index tests.
- Probe FTS5 in a temporary DB. Index current evidence and current individual
  claims only. One authoritative transactional synchronization mechanism; no
  best-effort async index.
- No auto-index on GET; no silent `LIKE` fallback; unsupported index has explicit
  capability status. Rebuild repeatable and case-owned only.

### S02 — Search API and workspace UI — **delivered, reviewed and verified locally**

- Resource-specific search reader/DTO/GET, case workspace search component,
  URL/filter/link helpers, unit/API/component/browser tests.
- Literal all-term semantics, type/publisher/status/date filters, deterministic
  pagination, plain-text snippets and deep links. A snippet is not a validated
  quotation.
- Query/filters persist in URL; no global/cross-case or vector search.
- Missing FTS → 503 with operator remedy. Measure the documented synthetic
  benchmark without brittle timing unit tests.

### V01 — Release C verification and documentation — **delivered and verified locally**

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
  without owner instruction. Local `main` is already 13 commits ahead of origin
  (the head is the Release C documentation commit on top of `0db8971`).
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
  committed (`44f1e58`, not pushed) and verified with its diff review pending.
- The remaining tickets were sequenced in the
  [completion map](20261120-release-c-completion-map.md) and are all delivered:
  S01 took migration 15, S02 and V01 none. Migrations stay additive and must be
  re-allocated from the live registry.
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
- Local `main` is 13 commits ahead of `origin/main` (`81b8778`) — Release B
  acceptance, R01–R04 and all of Release C, code head `0db8971` plus the
  documentation commit — and has not been pushed.
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

## 9. Paste-ready Release C completion brief

```text
Finish Release C by implementing S01, then S02, then V01, following
docs/archive/20261120-release-c-completion-map.md (which is the single brief and
contains the per-ticket scope, acceptance, stop conditions, commands and return
format). Contract authority: docs/plans/20261114-evidence-workbench-specification.md
§8 and §11.

Start by reading, in this order:
1. docs/archive/20261120-release-c-completion-map.md
2. docs/archive/20261118-release-b-handoff.md
3. docs/architecture/20261120-changes-ui.md and
   docs/architecture/20261118-case-snapshots.md
4. src/storage/{database,models,migrations,write_guard,event_store,captures}.py,
   the case service mutation paths, and src/cli/{main.py,commands/cases.py}
5. specification §8 (search) and §11 (verification)

CURRENT STATE (2026-11-20)
- Release A/B accepted; R01, R02, R03a, R03b, R03c pushed; R04 committed as
  44f1e58 (not pushed) with diff review pending.
- Backend 553 passed / 9 deselected, Ruff clean; frontend 132 tests / 13 files,
  npm run check green; migrations 1..14.

SEQUENCE
- S01: transactional case FTS5 index (current evidence + current individual
  claims), capability probe, additive migration ~15, one authoritative
  transactional sync mechanism, narrow case-owned CLI rebuild, no GET writes and no
  LIKE fallback.
- S02: GET /api/cases/{case_id}/search with literal all-term semantics, type/
  publisher/status/date filters, deterministic rank+pagination, plain-text
  snippets, 404/422/503 semantics, plus a case-workspace search surface with
  URL-persisted state and snapshot-aware result links.
- V01: Release C verification — deterministic fixtures/E2E on a scratch runtime/DB,
  all gates, GET-only boundary, safe rendering, docs, benchmark evidence, residual
  risks. Release C review gate only.

HARD STOPS
- D01 (historical data recovery) and production deployment are owner gates: do not
  start them.
- Stop and report if a migration would need to modify/drop/backfill existing rows,
  if search needs a new mutation endpoint or a GET-side write, or if FTS5
  unavailability cannot be represented as an explicit capability state.
- No commits, pushes, resets, branches, dependency changes or deletions without
  owner instruction. Backend Python/tests only in the disposable copy; browser
  checks only with a temporary DB/config or a Vite-only server with intercepted
  APIs. Never touch data/, triangulate.db, .env, logs/, config.toml or the live
  database.

RETURN
Per ticket: behaviour delivered; files/symbols/migration changed; capability and
failure semantics; transactional/idempotency evidence; real focused/full/Ruff and
check/test/browser output; remaining risks. After each ticket get an independent
reviewer pass, fix confirmed findings, record the evidence in worker plan §7 and
the map, then continue. Do not call partial work done.
```
