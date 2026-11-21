# CLI Operations Guide

This document describes the canonical operator workflow for Triangulate.

## Boundary

- The website is presentation-only.
- The HTTP API is read-only.
- Pipeline execution is triggered outside the website.
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

UI note: the frontend serves static `/data/*.json` fixtures when
`VITE_API_BASE_URL` is unset (`frontend/src/services/api.ts`), and the search tab
does not work in that static-data mode. To use search (and any live API data) in
the UI, run the backend (`uv run triangulate serve`) and start Vite with
`VITE_API_BASE_URL=http://127.0.0.1:5173` so requests go through the Vite `/api`
proxy to the real API.

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
- For local browsing after a run, start the API with `uv run triangulate serve` and open the frontend separately.
