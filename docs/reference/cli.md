# CLI Reference

The CLI entrypoint is `triangulate`, defined in `src/cli/main.py`.
This is the canonical operator trigger surface for ingestion, execution, reruns, reviews, and exception handling.
GitHub Actions or other worker runtimes may also trigger Triangulate, but they should do so by invoking the same CLI commands rather than the website.

## Setup Commands

```bash
uv run triangulate init-db    # Create the database and apply all pending migrations
uv run triangulate version
```

`init-db` initializes the database at the selected path and then runs every
pending migration against that same database (`src/cli/main.py:135-143`, via
`init_database()` + `run_migrations()`). It is idempotent: repeating it applies
only what is missing. Migration 15 (the optional FTS5 search index) is created
by its migration, not by ORM table creation, so `init-db` is what makes the
search capability state correct.

## Server Commands

```bash
uv run triangulate serve                    # Start FastAPI server on 127.0.0.1:8000
uv run triangulate serve --host 0.0.0.0 --port 8000 --reload
```

The HTTP artifact reader serves the report files that CLI publication wrote, so
both sides must agree on one directory through `TRIANGULATE_OUTPUT_ROOT`. It is
captured once at server startup (default `./output` when unset or blank) and a
relative value is resolved against the server's startup working directory.
Absolute directories are the most robust choice; publish with the same value:

```bash
uv run triangulate fetch-topic "<query>" --output "$SCRATCH/output"
TRIANGULATE_OUTPUT_ROOT="$SCRATCH/output" \
  uv run triangulate serve --host 127.0.0.1 --port <isolated-port>
```

`case rerun <case-id> --output <dir>` follows the same rule. A run published
under a directory the server is not configured for still lists (listing is
metadata) but its download is a uniform `404`; the server never guesses another
root, creates the directory or repairs recorded paths.

## Case-Oriented Commands

```bash
uv run triangulate fetch-topic "<query>"
uv run triangulate cases
uv run triangulate case show <case-id>
uv run triangulate case workflow <case-id>
uv run triangulate case review <case-id>
uv run triangulate case rerun <case-id>
uv run triangulate case exception <case-id> <exception-id> --action resolve
uv run triangulate case owner <case-id>
uv run triangulate case interrupt <case-id> --reason "<why>" [--run-id <id> | --token <t>] [--yes]
uv run triangulate case evaluate <case-id>
uv run triangulate case rebuild-search <case-id>
uv run triangulate run-pipeline
uv run triangulate monitor --start --topics ./topics.yaml --interval 30
uv run triangulate interactive
```

- `fetch-topic` bootstraps a case from a topic query; options: `--output/-o`,
  `--format/-f` (default `json,markdown`), `--max-articles/-m`,
  `--relevance-threshold/-r`, `--conflict/-c`, repeatable `--party` (confirmed
  parties/nationalities), repeatable `--manual-link` (evidence seeds),
  `--automation-mode` (default `exceptions_only`).
- `case workflow` prints the workflow diagnostics for one case.
- `case review --decision/-d` accepts `approve`, `reject`, `defer`,
  `action_required` and `exception`, with optional `--notes/-n`. `defer` is a
  case-level acknowledgement: it records the review note/timestamp only and
  never reopens a terminal case (no status, stage, event-review or exception
  change). The exception-level `case exception --action defer` is a separate
  action that sets one exception to `deferred`.
- `case owner` shows the active case writer (kind/reference/time; never the
  token).
- `case interrupt` is CLI-only writer recovery: it requires `--reason/-r`, asks
  for confirmation (skip with `--yes/-y`), and may target the active writer by
  `--run-id` or `--token`.
- `case evaluate` runs a lightweight evaluation over the current case state and
  stores the resulting evaluation record. It is the only way evaluations are
  created; the HTTP `GET .../evaluation` reader never generates one.
- `case exception` accepts `--action/-a` of `resolve`, `defer` or `reopen`, with
  optional `--notes/-n`.
- `case rerun` accepts `--from` (default `retrieve`).

## OSINT Import Commands

```bash
uv run triangulate osint ingest --tool <tool> --file <artifact> --case-id <case-id>
uv run triangulate osint stream --tool <tool> --watch <dir> --case-id <case-id> [--once]
```

- `osint ingest` imports a single OSINT artifact file into a case.
- `osint stream` imports all OSINT artifacts currently present in a watch
  directory; `--once` imports the current files once instead of continuous
  watching.

## Legacy Event Commands

```bash
uv run triangulate ingest
uv run triangulate process
uv run triangulate process-url <url>
uv run triangulate review
uv run triangulate query --days 7
```

Hard failures now exit non-zero: `ingest`, `process` and `process-url` raise
`typer.Exit(1)` on acquisition/processing errors instead of returning success
(`src/cli/commands/ingest.py:58-60`, `src/cli/commands/process.py:32-55`,
`src/cli/commands/process_url.py:125-166`). `process` also exits non-zero when
the batch completed with failed items (durable results are kept).

## Case Search Index

`triangulate case rebuild-search CASE_ID` rebuilds one case's rows in the
optional FTS5 search index (migration 15, `case_search_index`). It claims the
case with a short R02 `evidence` owner, deletes and re-inserts only that case's
current evidence and claim rows in one transaction, validates and releases the
owner, then commits once. A foreign active writer is refused with a clean
non-zero exit (`Search rebuild rejected`); there is no force/steal path.
Repeating the rebuild is idempotent: the same rows and counts come back. The
output reports either the rebuilt counts or, when the index cannot exist, the
capability reason (FTS5 module missing from the SQLite build, or
`case_search_index` missing because migration 15 is not applied). The command
touches only the named case and is the only repair path for a search 503 — see
[`./cli-operations.md`](./cli-operations.md).

## Notes

- Case commands read and write case artifacts under the configured output root, which defaults to `./output`.
- Inspection over HTTP is GET-only; three narrow review/annotation POSTs exist
  for human-in-the-loop review (see [`./http-api.md`](./http-api.md)). Case
  creation, ingestion, reruns and pipeline execution are not exposed over HTTP —
  the website does not trigger these workflows.
- GitHub Actions is an allowed trigger surface when it runs the CLI or shared service-layer workflows.
- `review` can target either the legacy event flow or a case via `--case-id`.
- `process-url` is useful for single-article inspection through the AI pipeline and can persist to the intake queue with `--save`.

For setup and common workflows, use [`../getting-started/quickstart.md`](../getting-started/quickstart.md).
For the operator workflow in Markdown form, use [`./cli-operations.md`](./cli-operations.md).
