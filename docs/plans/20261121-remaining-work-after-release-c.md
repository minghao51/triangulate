# Remaining work after Release C

Date: 2026-11-21. Status: **Release C is implemented, reviewed, verified and pushed
(`origin/main` = `dca1691`); nothing in S01/S02/V01 remains.** What is left is one
owner gate (D01), a separate deployment gate, and a short list of optional hygiene
that is not part of any ticket. This document is the brief for those items; it is
not authorization to start them.

Read first: the [completion map](20261120-release-c-completion-map.md) (the Release C
record, §7 for D01), the [Release C handoff](20261118-release-b-handoff.md), the
[setup and maintenance audit](../reference/20261114-setup-and-maintenance-audit.md),
the [test-database incident record](../reference/20261115-test-database-incident.md),
and the [search index](../architecture/20261120-search-index.md) /
[search read API](../architecture/20261120-search-api.md) notes.

## 0. State this brief starts from

| Item | Value |
|---|---|
| `origin/main` / local `main` | `dca1691`, in sync, clean tree |
| Migrations | 1..15 (15 = optional case FTS5 index) |
| Backend gate | **614 passed, 9 deselected**; Ruff clean over `src tests scripts` (committed tree, fresh export) |
| Frontend gate | `npm run check` exit 0; **164 tests / 14 files** |
| Release C docs | worker plan §7 final entries, completion map, handoff, two architecture notes, HTTP/CLI/operator reference |
| Production data | untouched; live DB sha256 `049a8a9d…d9f86` unchanged through all verification |
| Known non-issue | analyzer cascades on `scripts/qwen_manual_check.py` are stale: `py_compile` OK, Ruff clean, file untouched since `956954c` |

## 1. D01 — historical data recovery (owner gate; do not start)

**Why it is separate.** The audit's finding is a *data* problem in the production
database, not a code problem: `topic_cases` = 0 rows, the ORM
`case_articles` = 227 rows with missing case parents, a separate `CaseArticle`
table with 4,786 rows that the application does not map
(`src/storage/models.py:292–315` maps `CaseArticle` to `case_articles`), all other
domain tables empty, and `_migrations` absent. Nothing here is repairable by code,
and every plausible repair writes to historical data.

**Prerequisites — all must exist before any write:**

1. **Consistent backup with competing writers stopped.** Record the backup path,
   size and sha256; confirm the writers that caused the split
   (`_cron_tmp/step5_manifest_db.py:39–50` writes `CaseArticle`;
   `scripts/backfill_ingestion_2026-04-04_to_2026-04-10.py` targets
   `case_articles`) are not running.
2. **Dry-run reconciliation report on a copy**, not the original: per-table row
   counts, distinct URL/fingerprint counts, duplicate groups, rows with unusable
   or fabricated-looking case references, and the exact mapping decision proposed
   for `CaseArticle` → `case_articles` (or an explicit decision to keep them
   separate).
3. **Provenance and deduplication definition** (URL canonicalisation, fingerprint
   rule, which original timestamp wins), because the audit does not establish
   that the 5,013 historical rows are unique.
4. **Restore rehearsal**: restore the backup copy, apply the proposed
   transformation, compare row/content counts before/after, and keep the
   rehearsal log.
5. **Explicit owner approval of that plan**, plus a rollback step that returns to
   the untouched backup.

**Hard prohibitions (from the audit and the Release C map):** do not fabricate case
ownership; do not delete orphans to make counts tidy; do not drop `CaseArticle`;
do not run migration initialisation merely to make the schema look complete; do not
write to the original database before approval; do not leave the B02
test-database incident disclosure behind — the original hash mismatch remains
disclosed in the [incident record](../reference/20261115-test-database-incident.md).

**Deliverable for the approval decision:** a short report with the backup
manifest, the dry-run table, the mapping/dedup decisions, the rehearsal result,
the rollback step, and the residual uncertainty. Only then does an import or
mapping change become a ticket.

## 2. Production deployment (separate owner gate)

Not started, and not startable from this brief alone. When it is scoped, the
minimum known obligations are:

- Run `triangulate init-db` (or the documented startup path) so migration 15
  creates `case_search_index`; confirm the runtime SQLite actually has FTS5
  (`SQLite 3.50.4` in the verified environment) — otherwise search answers 503 and
  the operator remedy cannot help until the build changes.
- Run `triangulate case rebuild-search CASE_ID` for each case that must be
  searchable **before** relying on search; the index is current-state only and
  nothing backfills it on startup.
- Build the frontend with `VITE_API_BASE_URL` pointing at the deployed API (see
  §3.H3) — with it unset the client serves static `/data/*.json`.
- Keep the read path GET-only, the CLI-only mutation boundary, and the R02
  case-writer admission rules intact; do not introduce a rebuild-on-GET or a
  `LIKE` fallback as a deployment shortcut.
- Record a rollback step (previous image + previous DB backup) and the monitoring
  signal for search 503s.

## 3. Optional hygiene (non-blocking, no owner gate)

Each item is independent and safe to defer. Follow the repo rule for the
completion of any of them: focused checks, full gates where code changes, then an
owner-approved commit/push.

### H1 — Ephemeral evidence paths in the pushed docs
The V01 entries in the worker plan, map and handoff cite
`/tmp/v01-evidence/…` screenshots. That directory was partially cleaned after the
runs, so some images no longer exist. Action: either strip the ephemeral paths and
describe the evidence in words, or archive the surviving artifacts (with a
sha256 manifest) somewhere durable and point at that. Acceptance: no pushed doc
implies a file that no longer exists.

### H2 — Browser coverage gaps
Recorded as not proven in the V01 entry: the run was Chrome-driven through the
Playwright CLI — no Firefox/Safari matrix, no mobile viewport, no load test.
Action if wanted: repeat the fixture journey (`scripts/v01_e2e_fixture.py`) in the
second engine and at a 390×844 viewport, and add an operator-documented load
check for search (the benchmark in §0 is a latency record, not a load test).
Acceptance: evidence per engine/viewport with the same GET-only assertion.

### H3 — Static-data default in the frontend
`frontend/src/services/api.ts:29-31` makes `USE_STATIC_DATA = true` whenever
`VITE_API_BASE_URL` is unset, so a plain `npm run dev` silently serves
`/data/*.json` and the search tab cannot work. This is documented in
[CLI operations](../reference/cli-operations.md) but is a sharp edge. Action if
wanted: emit a single visible dev-mode notice (or console warning) when
`USE_STATIC_DATA` is active outside tests, or require the variable explicitly in
`npm run dev` scripts. Acceptance: a developer cannot land on an empty search tab
without being told why, and the production build is unchanged.

### H4 — Plans housekeeping
`docs/plans/README.md` says a plan moves to `docs/archive/` once implemented or
superseded. The completion map and the Release C handoff now qualify. Action:
move them, update inbound links (docs index, worker plan, architecture notes), and
keep the archive entry labelled "implemented 2026-11-21". Acceptance: a link check
over `docs/**/*.md` reports zero broken targets.

### H5 — Stray local dev server
A Vite dev server for `frontend/` from an earlier session listens on
`127.0.0.1:4310` (`PID 3386690`, started 2026-11-20). It was left running
deliberately. Action: stop it when its owner no longer needs it; it is not part of
the application.

## 4. Rules that still apply

- Backend Python and pytest run only in a disposable copy; never ingest, clean up
  or migrate against the live database. Never touch `data/`, `triangulate.db`,
  `.env`, `logs/`, `config.toml` or the scratch archive.
- Browser checks use a temporary DB/config or a Vite-only server; never point a
  browser at the default live backend.
- One application-code writer at a time; reviewers are read-only.
- Migrations: allocate from the then-current registry, additive only; stop and
  report if a ticket needs more than an additive index/capability table.
- Preserve the GET-only read boundary (no GET writes, rebuilds or index repair),
  the CLI-only mutation boundary, and the R02 owner/fencing rules.
- No commits or pushes without owner instruction; keep scratch work in `/tmp`.
- Mark only criteria actually proven; list residual risks explicitly.

## 5. Commands

```bash
# backend, disposable copy only
SAFE_DIR=$(head -1 /tmp/triangulate-safety-verification-dir)
cd /home/howt/work/triangulate
tar --exclude='__pycache__' --exclude='*.pyc' -cf - src tests scripts | tar -C "$SAFE_DIR" -xf -
cp bias_taxonomy.toml "$SAFE_DIR"/ 2>/dev/null || true
cd "$SAFE_DIR"
env LLM_API_KEY= OPENAI_API_KEY= LANGSMITH_TRACING=false uv run pytest -q --disable-warnings
uv run ruff check src tests scripts --output-format concise

# frontend
cd /home/howt/work/triangulate/frontend
npm run check
npm test -- --run

# scratch fixture for any browser work (never the live DB)
cd /home/howt/work/triangulate
uv run python scripts/v01_e2e_fixture.py --out /tmp/v01-e2e-scratch
# serve with CWD = that directory and DATABASE_PATH = its triangulate.db,
# frontend with VITE_API_BASE_URL=http://127.0.0.1:5173 through the Vite proxy
```

## 6. Return format per item

What was done; exact files/commits touched; the real gate or rehearsal output;
evidence paths; what is proven vs not proven; residual risks; and — for D01 and
deployment — an explicit statement that no write to production data occurred
unless the owner approved it in writing.
