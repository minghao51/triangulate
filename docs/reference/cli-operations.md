# CLI Operations Guide

This document describes the canonical operator workflow for Triangulate.

## Boundary

- Inspection over HTTP is GET-only. A narrow human-in-the-loop review exception
  exists: three POST routes for review decisions, exception actions and review
  annotations (see [`./http-api.md`](./http-api.md)).
- Case creation, ingestion, reruns and pipeline execution are not exposed over
  HTTP and are triggered outside the website.
- The default trigger surface is the `triangulate` CLI.
- GitHub Actions or other worker runtimes may invoke the same CLI commands for scheduled or remote operation.

## Primary Operator Flows

### 1. Create or Update a Topic Case

```bash
uv run triangulate fetch-topic "Gaza ceasefire negotiations"
```

Use this to run the case-oriented workflow from topic retrieval through persisted outputs.

### 2. Monitor Recurring Topics

```bash
uv run triangulate monitor --start --topics ./topics.yaml --interval 30
uv run triangulate run-pipeline
```

Use `monitor --start` for a recurring local loop and `run-pipeline` for a single monitor-oriented pass.

### 3. Ingest and Process External Material

```bash
uv run triangulate ingest
uv run triangulate process
uv run triangulate process-url "https://example.com/article" --save
```

These commands feed the durable intake queue and process saved captures through the service layer.

### 4. Inspect and Operate on Existing Cases

```bash
uv run triangulate cases
uv run triangulate case show <case-id>
uv run triangulate case review <case-id> --decision approve
uv run triangulate case rerun <case-id> --from retrieve
uv run triangulate case exception <case-id> <exception-id> --action resolve
```

Use these commands for operator control after a case already exists.

`case review --decision` accepts `approve`, `reject`, `defer`,
`action_required` and `exception`. `defer` is a **case-level acknowledgement**:
it records the review note and timestamp but never reopens a case. A
`REVIEW_READY` case stays review-ready, and an `APPROVED`/`REJECTED` (or
monitoring) case keeps its stored status, its stage and every persisted event
review decision and analysis binding. It also leaves the exception queue — its
statuses, timestamps and resolution notes — untouched. That is different from
`case exception --action defer`, which defers one exception to `deferred`.

### 5. Repair the Case Search Index (HTTP 503 on search)

```bash
uv run triangulate case rebuild-search <case-id>
```

A `503` from `GET /api/cases/{case_id}/search` means the search index
capability is unavailable — it is never an empty result and there is no `LIKE`
fallback. The 503 detail carries the capability reason and names this command
as the remedy. Expect it in exactly two situations:

- **FTS5 is not compiled into the runtime SQLite build** — the reason text is
  `SQLite FTS5 module is not compiled into this SQLite build.` Rebuilding cannot
  fix this; use a SQLite build with FTS5 (runtime SQLite 3.50.4 has it).
- **Migration 15 is not applied** — the reason text is `FTS5 module is
  available, but case_search_index is missing (migration 15 is not applied).`
  Run `uv run triangulate init-db` (applies pending migrations) and then rebuild.

Diagnose by reading the reason text in the 503 detail, then run the rebuild
command for that case. The rebuild is the **only** repair path: no GET creates,
repairs or rebuilds index rows, and no fallback query path exists. The command
claims the case with a short `evidence` owner (a foreign active writer is
refused), touches only that case, is idempotent, and prints the rebuilt
evidence/claim counts or the capability reason. After a successful rebuild,
retry the search request.

UI note: the static-data default remains — with `VITE_API_BASE_URL` unset the
frontend prefers bundled static `/data/*.json` fixtures (`frontend/src/services/api.ts`).
That mode is a development convenience with two qualifications (as of
2026-11-22): it emits a dev-only console warning when active outside tests, and
a failed static fixture lookup falls through to the same-origin `/api` path,
which Vite proxies to the backend (`frontend/vite.config.ts`). So search (and
other live data) can work in that configuration if a backend is reachable via
the proxy — but any data set without matching fixtures will look empty or
partial until then. For predictable live data, run the backend
(`uv run triangulate serve`) and start Vite with
`VITE_API_BASE_URL=http://127.0.0.1:5173` so every request goes through the Vite
`/api` proxy to the real API. The production build is unchanged.

### 6. Database Selection and Initialization (HTTP 503 on historical GETs)

The HTTP server and `init-db` resolve the SQLite path with the same deliberate
precedence, so an explicit bootstrap targets exactly the file the server reads:

1. a **non-default** `[database].path` in the runtime `config.toml`;
2. otherwise a configured `DATABASE_PATH` environment variable;
3. otherwise the compatibility default `./triangulate.db`.

A config value that only spells out the default (`./triangulate.db` or
`triangulate.db`) does not mask `DATABASE_PATH`. Relative values are resolved
against the process working directory, so run `init-db` and `serve` from the
same directory (or use absolute paths).

```bash
# Bootstrap the same configured database the server will read
uv run triangulate init-db
uv run triangulate serve
```

The three historical GETs (`snapshot-comparison`, the run artifact list and an
artifact download) never create or migrate storage. If the selected file is
missing, empty/uninitialized, partially migrated or unreadable, they answer a
sanitized `503 {"detail": "Historical storage is unavailable"}`. The remedy is
to run `init-db` with the same configuration and working directory, then retry.
An unknown case/run/artifact or snapshot on a usable store is still a scoped
`404`, and malformed requests keep their `422`s. `GET /health` is liveness only
and does not prove the historical database is available. Reads do not force a
journal mode; a WAL file whose `-shm` sidecar the server cannot create is
reported as unavailable rather than modified.

## GitHub Actions as a Trigger Surface

GitHub Actions is a valid trigger surface as long as it calls the same CLI or service-layer workflows rather than the website.

Example uses:

- scheduled monitor runs
- manual `workflow_dispatch` case creation
- periodic ingestion or intake processing
- automated reruns for a known case

The important rule is unchanged: GitHub Actions may trigger the CLI, but the website must not trigger execution.

## Recommended Automation Pattern

- Check out the repository.
- Set up Python and project dependencies with `uv`.
- Provide runtime secrets and config through Actions secrets or environment variables.
- Run the same `uv run triangulate ...` commands used locally.
- Let the website read the resulting persisted state afterward.

## Notes

- Prefer case-oriented commands over older event-oriented commands when both can satisfy the task.
- `process-url --save` is useful for attaching ad hoc captures to the durable intake pipeline.
- For local browsing after a run, start the API with `uv run triangulate serve` and open the frontend separately. If a historical GET returns `503 "Historical storage is unavailable"`, run `uv run triangulate init-db` from that same working directory; `GET /health` remains `ok` either way.
- If you published a case under a custom directory (`fetch-topic --output <dir>`
  or `case rerun --output <dir>`), start the server with the same directory in
  `TRIANGULATE_OUTPUT_ROOT` (an absolute directory is the most robust). The
  setting is read once at startup; a relative value is resolved against the
  server's startup working directory, defaults to `./output` when unset, and the
  server never creates, repairs or searches for another output root.
