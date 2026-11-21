# Release C completion map: S01, S02, V01 (D01 gated)

Date: 2026-11-20 (updated 2026-11-21). Status: **Release C is implemented,
reviewed and verified locally (S01 `3096c0f`/`5501842`, S02
`0ae9359`/`b92c453`/`ff838cc`/`3594d1c`, V01 `2fd91a2`/`19f42e3`/`0db8971`) — not
pushed.** Release A and
Release B are accepted. R01–R04 are accepted; the R04 review fix is `dfc809c`.
This map remains the single brief for Release C; the next step is owner
review/push of the local commits. **D01 and production
deployment are separate owner gates and must not be started.**

Contract authority remains the
[specification](20261114-evidence-workbench-specification.md) (especially §8 and
§11) and the [worker plan](20261114-evidence-workbench-worker-plan.md). Current
state lives in the [Release C handoff](20261118-release-b-handoff.md).

## 0. State at the start of the next session

| Item | Value |
|---|---|
| Local `main` / `origin/main` | `origin/main` at `81b8778`; local `main` is **13 commits ahead, nothing pushed** — code head `0db8971` plus this documentation commit (R04 `44f1e58` + review fix `dfc809c`, S01 `3096c0f`/`5501842`, S02 `0ae9359`/`b92c453`/`ff838cc`/`3594d1c`, V01 `2fd91a2`/`19f42e3`/`0db8971`, plus doc maps `96a7d15`) |
| Migrations | 1..15 (12 grouped runs, 13 case-writer ownership, 14 immutable snapshots, 15 optional case FTS5 index) |
| Backend gate | Final **614 passed, 9 deselected** (`tests/test_v01_e2e.py` is the 614th), Ruff clean over `src tests scripts` (disposable copy) |
| Frontend gate | `npm run check` exit 0; **164 tests / 14 files** |
| Fresh install | `git archive HEAD` → `uv sync --frozen --extra dev` green; `triangulate init-db` reaches migration 15 |
| Frontend consistency | React 18 + Vite + TanStack Query; `src/services/api.ts`, `src/services/deep-links.ts`, `src/types/backend-models.ts` are the API seams |
| Research lane | R01–R04 delivered and accepted (R04 review fix `dfc809c`); **S01, S02 and V01 implemented, reviewed and verified locally — not pushed** |
| Production data | untouched (V01 recorded the live DB sha256 `049a8a9d…d9f86` unchanged); the B02 test-database incident remains disclosed |
| Scratch | 382 files archived at `/tmp/triangulate-scratch-archive-20261118T005339Z.tar.gz` |

Read first, in this order: this map, the handoff, worker plan §5/§7, specification
§8/§11, the [changes UI architecture](../architecture/20261120-changes-ui.md), the
[snapshot architecture](../architecture/20261118-case-snapshots.md), and
`src/storage/database.py`, `src/storage/models.py`, `src/storage/migrations.py`,
`src/storage/write_guard.py`, `src/storage/event_store.py`,
`src/storage/captures.py`.

## 1. Operating rules (do not relax these)

- One application-code writer at a time. If a reviewer subagent is running, it is
  read-only.
- Backend Python and tests run **only** in the disposable copy recorded in
  `/tmp/triangulate-safety-verification-dir`
  (`tar --exclude='__pycache__' --exclude='*.pyc' -cf - src tests | tar -C "$SAFE_DIR" -xf -`
  plus `bias_taxonomy.toml`). Never run ingestion, cleanup or migrations against
  the live database. Never touch `data/`, `triangulate.db`, `.env`, `logs/`,
  `config.toml` or the scratch archive.
- Frontend work runs in the repository, but browser checks need a **temporary
  DB/config** or a Vite-only server with intercepted APIs. Never point a browser
  at the default live backend.
- Migrations: allocate the next number from the then-current registry (S01 is
  expected to take **15**). Additive only. If a ticket appears to need more than
  an additive index/capability table, **stop and report** instead of expanding.
- Preserve the CLI-only mutation boundary, the R02 owner/fencing rules and the
  GET-only read boundary. No new mutation endpoint. No GET may create, rebuild or
  repair an index.
- **No commits, pushes, resets, branches, dependency changes or deletions without
  owner instruction.** Prepare clean, green commits and ask. Keep scratch work in
  `/tmp`.
- After each ticket: run focused tests, then the full backend suite and Ruff (or
  `npm run check` + `npm test -- --run` for frontend), record the real output in
  worker plan §7 and this map, and get an independent reviewer pass on the diff.
  Fix what it confirms before declaring the ticket done. Never call partial work
  done.

## 2. Stop conditions (report, do not improvise)

- FTS5 is unavailable in the runtime SQLite build and the ticket cannot deliver an
  explicit capability state without a schema redesign.
- A migration must modify or drop an existing table, backfill parsed content, or
  touch historical/unowned rows.
- Search cannot be implemented without a new mutation endpoint or a GET-side
  write.
- A ticket would need a paid/live model or network call in tests.
- The owner has not authorized a commit/push when the work is ready.

## 3. Sequence

| # | Ticket | Lane | Depends on | Migration |
|---|---|---|---|---|
| 1 | S01 — transactional case FTS index + explicit rebuild (**implemented, reviewed and verified locally, not pushed**) | backend | R01/R02, current schema | 15 |
| 2 | S02 — search read API + workspace UI (**implemented, reviewed and verified locally, not pushed**) | backend + frontend | S01 | none |
| 3 | V01 — Release C verification, E2E, docs (**implemented, reviewed and verified locally, not pushed**) | full stack | S01, S02 | none |
| — | D01 — historical data recovery | — | **owner gate, do not start** | — |

S01 must land and be verified before S02 starts: the API contract depends on the
index's actual capability/failure semantics. V01 starts only when S01 and S02 are
accepted by their gates.

## 4. S01 — Transactional case FTS index and explicit rebuild

Status: **implemented (`3096c0f`, `5501842`), reviewed and verified locally; not
pushed.** Migration **15** is applied; the final gate numbers and defect record
are in the worker-plan §7 S01/S01-perf final entries and the
[search index architecture](../architecture/20261120-search-index.md).

**Goal:** one authoritative, transactional, case-scoped FTS5 index over *current*
evidence text and *current individual claims*, with an explicit capability probe
and a narrow CLI rebuild.

**Scope**

1. `src/storage/search.py` (new): capability probe, index row builders, upsert/
   delete helpers, query-independent metadata (indexed row counts per case), and
   the rebuild entry point. All functions are session-in/out; no inner commits.
2. Migration **15** (additive): FTS5 virtual table plus any small capability/
   metadata row storage the design needs. Create it only when the probe succeeds;
   when FTS5 is unavailable the migration must still complete and the runtime must
   report the index as unavailable with a reason (never a silent fallback).
3. **One** synchronization mechanism, inside the owning transaction:
   - index current evidence once per logical evidence (`title` + the text of the
     **current** capture only; replacing the current capture replaces the indexed
     text, and older capture text must never remain indexed as current);
   - index current individual claims (`claim_text`, signature, case/event/party
     metadata needed by S02 filters);
   - delete rows when a claim is replaced/removed or an evidence row leaves the
     case; rollback must leave the index exactly as it was.
   Enumerate the actual write call sites first (event store claim upsert/removal,
   capture pointer changes, intake/OSINT evidence writes, review-driven claim text
   changes). Do not index events, narratives, articles, citations or legacy
   unowned rows.
4. CLI rebuild: a narrow case-scoped command (for example
   `triangulate case rebuild-search CASE_ID`) that validates/claims the case owner
   like the other short writers, refuses a foreign active writer, deletes and
   re-inserts that case's rows in one transaction, is idempotent, and reports
   indexed counts plus the capability state. No other case may be touched.
5. GET-only and R02 rules: no index work on any HTTP GET; case-bound writes keep
   their existing owner validation, so an interrupted writer cannot index.

**Out of scope:** the search read API/UI (S02), cross-case/global indexes,
historical or capture-version search, semantic/vector search, LIKE fallback,
async/background indexing, article/narrative indexing, D01.

**Acceptance evidence**

- Known title/body/claim terms are found through the index helpers; a source
  update (new current capture) and a claim replace/delete are reflected
  transactionally; a rolled-back write leaves no index drift.
- Repeated rebuild of the same case produces identical results and counts; a
  rebuild during a foreign active writer is refused and changes nothing.
- FTS-unavailable capability state is explicit (probe test in a temporary DB;
  simulate absence if the platform always has FTS5).
- Fresh and legacy-v14 migration tests; the full backend suite and Ruff.
- No `LIKE` fallback, no async queue, no GET-side write, no unowned rows indexed.

**Risks to settle in the first hour**

- Table shape: prefer a single FTS5 table with `case_id`/`entity_type`/`entity_id`
  stored for filtering plus indexed title/body, `unicode61` tokenizer; per-case
  virtual tables are not acceptable. Decide contentless versus stored text by
  whether S02 snippets need `snippet()` (they do, so keep the indexed text
  retrievable without duplicating capture bodies more than once per evidence).
- Trigger-based sync versus application-level sync: pick **one**. Application-level
  writes inside the same transaction compose with R02 fencing and the CLI rebuild;
  if you choose triggers, prove the transaction/rollback semantics and document why
  they cannot drift from the owner guard.
- Snippet/HTML: never return raw FTS `<mark>` HTML (S02 consumes plain text).

## 5. S02 — Search read API and workspace UI

Status: **implemented (backend `0ae9359`/`b92c453`, workspace UI
`ff838cc`/`3594d1c`), reviewed and verified locally; not pushed.** See the
[search read API architecture](../architecture/20261120-search-api.md) and the
worker-plan §7 S02 final entry for the recorded gate output, benchmark and
defect record. The UI persists `q`, filters and `offset` in the URL and deep-links
results into the inspector with the `snapshot` key for historical selections
(`snapshotId` is not a supported URL key).

**Goal:** `GET /api/cases/{case_id}/search` plus a case-workspace search surface,
over the S01 index only.

**API contract (specification §8)**

- Query `q`: trimmed, 1–256 code points, **literal all-term** semantics. Tokenize
  Unicode word terms client-independent, quote/escape each term for FTS, bind
  parameters, AND them. No raw FTS operators reachable; a query with no searchable
  terms is 422, never a full scan or empty success.
- Filters: `type=claim|evidence`, `publisher` (publisher key), `status` (claim
  verification state), `publishedFrom`/`publishedTo` (UTC, start-inclusive /
  end-exclusive; unknown dates excluded when a date filter applies). Reject a
  status filter combined with `type=evidence`; when `type` is omitted a status
  filter narrows to claims. Do not invent evidence-party semantics.
- Paging: default 25, max 100, non-negative offset. Deterministic order: rank then
  `(resultType, id)` tie-break. Return `total`, applied filters, plain-text
  snippet, matched field and enough typed IDs for deep links.
- Failure states: unknown/wrong-case → 404; missing index capability → **503 with
  an operator remedy** (CLI rebuild command), never an empty result; malformed
  query/filters → 422.
- Read-only: no GET writes, rebuilds or index repair.

**UI**

- A case-scoped search entry point (button/tab, not a global page), with labelled
  input, result type/publisher/status/date filters, clear-filters, keyboard
  operability and URL-persisted state (`q`, filters, `offset`) using
  `src/services/deep-links.ts` helpers (add a `SEARCH_PARAMS` block there).
- Distinct loading / empty / no-index-503 / error / retry states; snippets render
  as text (never HTML); safe `http(s)` links only.
- Results deep-link into the existing inspector with explicit `claim`, `evidence`,
  `capture` and optional `snapshot` selectors; historical/removed claims use the
  snapshot-backed readers, and absent resources show the explanatory 404 rather
  than another item. Do not add a `snapshotId` selector to readers that reject it.
- Add the DTOs to `src/types/backend-models.ts` and the client helpers to
  `src/services/api.ts`.

**Out of scope:** cross-case/global search, semantic/vector search, arbitrary
filter DSL, party filters, search over snapshots/articles/narratives, new mutation
endpoints, production deployment.

**Acceptance evidence**

- API tests: literal all-term matching; quotes/punctuation/SQL-like input cannot
  escape semantics; status/type/publisher/date filters; deterministic pagination
  and total; wrong-case 404; 503 when the index is unavailable; no raw HTML in
  snippets; no non-GET requests.
- Component tests for every state and URL persistence; frontend gates.
- A documented synthetic benchmark (10k evidence / 20k claims fixture) with the
  measured warm p95 recorded in the docs; **no** hardware-dependent timing
  assertions in unit tests.
- A focused browser check with a temporary DB/config (rebuild via CLI, search a
  known term, open a result in the inspector, verify the 503 state with the index
  disabled).

## 6. V01 — Release C verification and documentation

Status: **implemented and verified locally (`2fd91a2`, `19f42e3`, `0db8971`);
not pushed.** Gates: backend **614 passed, 9 deselected**, Ruff clean over
`src tests scripts`; frontend `npm run check` exit 0, **164 tests / 14 files**;
clean-export fresh install green (init reaches migration 15); the journey test
records 275 GET-only requests with byte-identical index/`_migrations` dumps and
an unchanged live DB sha256 (`049a8a9d…d9f86`). Browser evidence and the
not-proven list are in the worker-plan §7 V01 final entry. **Release C review
gate only; production deployment is separately approved.**

**Goal:** prove the Release C journey end-to-end and leave current docs; this is
the Release C review gate, **not** production deployment.

**Scope**

- Deterministic fixtures/E2E: the §11 journey on a scratch runtime/DB — ingest a
  synthetic case, inspect a quotation, compare sources, view changes, search, open
  a historical claim via a snapshot link.
- E2E launcher uses **temporary config and DB** and must never start against the
  default live backend; record that the live DB was untouched.
- Run every gate: backend full suite + Ruff in the disposable copy; frontend
  `npm run check` + `npm test -- --run`; the browser/E2E run; a fresh-install check.
- Verify and record: GET-only boundary (network log; zero non-GET on read paths),
  safe rendering (no HTML injection, http(s)-only links), no synthetic/placeholder
  values, no index write on GET, wrong-case isolation.
- Update current architecture, API and operator docs (including how to rebuild the
  search index and what 503 means), and the worker plan status/gates.
- Mark only criteria actually proven; list residual risks explicitly.

**Out of scope:** production deployment, D01, historical-data repair, performance
guarantees beyond the recorded benchmark, new features.

## 7. D01 — historical data recovery (owner gate; do not start)

The audit's orphan `CaseArticle`/lineage findings and any table merge/drop or
ownership change are outside Release C. D01 requires an owner-approved
backup/restore plan, a dry-run reconciliation report, explicit approval before any
data write, and a separate deployment gate. Do not begin it from this map.

## 8. Commands

```bash
# backend, disposable copy only
SAFE_DIR=$(head -1 /tmp/triangulate-safety-verification-dir)
cd /home/howt/work/triangulate
tar --exclude='__pycache__' --exclude='*.pyc' -cf - src tests | tar -C "$SAFE_DIR" -xf -
cp bias_taxonomy.toml "$SAFE_DIR"/ 2>/dev/null || true
cd "$SAFE_DIR"
env LLM_API_KEY= OPENAI_API_KEY= LANGSMITH_TRACING=false uv run pytest -q --disable-warnings
uv run ruff check src tests --output-format concise

# frontend
cd /home/howt/work/triangulate/frontend
npm run check
npm test -- --run

# browser (isolated; Vite-only with intercepted APIs, or temp DB/config)
# follow the playwright-cli skill: record console/network findings and close your own browser/server
```

## 9. Return format per ticket

Behaviour delivered; exact files/symbols/migrations changed; index capability and
failure semantics (S01/S02); write-path and rebuild idempotency evidence; API
contract and filter semantics; real focused/full/ruff or check/test output; browser
evidence paths; remaining risks/blockers; what was explicitly **not** done. Do not
call partial work done, and stop at the owner gates (commit/push, D01, deployment).
