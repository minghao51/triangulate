# Release B handoff: P03 review and Release C (R01–V01)

Date: 2026-11-18. Status: **Release A and Release B are accepted. P01/P02/P03
were reviewed and accepted on 2026-11-18; the review evidence is recorded in the
[worker plan](20261114-evidence-workbench-worker-plan.md) §7 and
[comparison UI](../architecture/20261118-comparison-ui.md). This document is now
the Release C (R01–V01) handoff.** It remains self-contained for a fresh agent.
Contract authority remains the
[specification](20261114-evidence-workbench-specification.md) and the
[worker plan](20261114-evidence-workbench-worker-plan.md).

## 1. Where things stand

| Item | State |
|---|---|
| Local `main` | P03 `4226856` plus this handoff commit — **ahead of `origin/main` by 6 commits, not pushed** |
| Release A | Accepted: B00–B03, E01–E04; E04 = `8ee32eb` |
| P01 | `e95bfb2` — conservative source dependency groups |
| P02 | `4d93c12` — deterministic comparison read API |
| P03 | `4226856` — comparison navigation and panels; **Release B reviewed and accepted 2026-11-18** |
| Next ticket | **R01 — grouped invocation identity (not started)** |
| Migrations | 1..11 (7 OSINT, 8 review audit/evaluation, 9 review hash, 10 captures, 11 citations) |
| Frontend gate | `npm run check` green; `npm test -- --run` = **107 tests / 12 files** |
| Backend gate | **456 passed, 9 deselected**; Ruff clean |
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
   Recorded. **R01 is now the only active ticket.**
5. One bounded ticket at a time, parent diff review after each. Do not start R02
   before R01 is reviewed.

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

Default order after Release B acceptance: **R01 → R02 → R03 → R04 → S01 → S02 →
V01**. Stop after each ticket for parent review and after V01 for the Release C
gate. S01 depends on E02/E03 and is technically independent of the R lane, but
shared storage/event-store writers mean one application-code writer at a time;
the default order avoids races.

### R01 — Grouped invocation identity (internal only)

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

### R02 — Case writer admission, fencing and explicit recovery

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

### R03 — Snapshots, deltas and historical readers

- `CaseSnapshot` model/migration, `src/cases/history.py`, run finalization,
  snapshot-aware inspector/comparison readers, run-specific report output, new
  GET contracts.
- Snapshot is an observation of committed state under a consistent read; freeze
  baseline selection; carry known origin stage/run IDs; exclude volatile fields.
- Immutable capture/citation/relationship references and before/after claim text;
  removed live claims stay viewable.
- Follow the §7 file/DB protocol exactly: temp sibling report dir → flush/rename →
  guarded success/snapshot/delta/artifact/pointer transaction. File failure cannot
  produce success; DB failure may leave an unreferenced directory but no published
  pointer/baseline.
- No false article removals, no fallback/no-content “retraction”, no invented
  actor attribution. Failed/paused runs never advance the successful baseline.
- Split storage/composition from delta/readers at parent review if needed.

### R04 — Changes and grouped history UI

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
  without owner instruction. Local `main` is already 6 commits ahead of origin.
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

- P03 is committed but **not yet accepted as Release B**; the new thread owns
  that review.
- Local `main` is 6 commits ahead of `origin/main` and has not been pushed.
- The scratch archive is in `/tmp` and is not durable across a machine cleanup;
  copy it somewhere durable if the old one-offs must be retained.
- P02 test fixtures now expose `seed_workbench(tmp_path)` for browser seeding;
  P03 tests use mocked APIs.
- Timestamps are returned as persisted; SQLite drops `tzinfo` and the UI does not
  invent an offset.
- `sourceDiversityCount` remains a compatibility field, not an independence count.
- Historical comparison analysis is unavailable without persisted
  capture-linked assessments until R03 snapshots exist.
- No `.pi-lens.json` ignore file was added; the scratch-file cascade is gone
  because the files were archived/removed.

## 9. Paste-ready R01 dispatch brief

```text
Implement ticket R01 from docs/plans/20261114-evidence-workbench-worker-plan.md
(contract: docs/plans/20261114-evidence-workbench-specification.md §7).
Start by reading docs/plans/20261118-release-b-handoff.md and confirming the
Release B acceptance is recorded (P01/P02/P03 commits e95bfb2/4d93c12/4226856).

Scope: InvestigationRun model/migration/exports; run_case invocation identity,
per-case sequence, trigger, stage/parameters, predecessor, status, coverage,
timestamps, error, baseline/result snapshot IDs; nullable grouped-run references
on CaseStageRun and Event; pass one ID through stages. Keep Event.case_run_id as
the stage FK and existing stage history unchanged. Legacy origins stay unknown.
No deployment/use of grouped runs before R02 fencing and R03 finalization.

Do not modify: production DB/data/logs, unrelated features, HTTP mutation
boundaries, other tickets' files, or re-add scratch scripts. Use the disposable
backend copy for tests and allocate the next migration number from the current
registry. Stop and report blockers rather than expanding scope.

Return: behaviour delivered; files/symbols changed; real migration/test output;
full backend suite and Ruff; remaining risks. Do not call partial work done.
```
