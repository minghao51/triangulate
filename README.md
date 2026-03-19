# Triangulate

Triangulate is a Python-first investigation workflow for building topic-oriented cases from news coverage, AI analysis, and linked evidence. The current product surface is:

- A CLI for retrieval, case generation, review, exception handling, and monitor loops
- A FastAPI layer that exposes persisted case data to clients
- A React frontend for browsing investigations and operator output as a presentation layer

## Current Architecture

- `src/cli/`: operator-facing commands for ingest, fetch-topic, case review, and monitor runs
- `src/cases/`: orchestration boundary and read model construction
- `src/http/`: read-only frontend-facing FastAPI endpoints
- `src/storage/`: SQLite-backed persistence and migrations
- `frontend/`: React app consuming the read-only `/api/cases*` endpoints

The codebase currently runs as a local Python application backed by SQLite. Older design material for Node/NestJS, Postgres, ArchiveBox, and other aspirational architecture has been moved under [`docs/archive/`](docs/archive/README.md).

## Start Here

- Setup and local workflow: [`docs/getting-started/quickstart.md`](docs/getting-started/quickstart.md)
- Documentation index: [`docs/README.md`](docs/README.md)
- Architecture as built: [`docs/architecture/system-overview.md`](docs/architecture/system-overview.md)
- CLI reference: [`docs/reference/cli.md`](docs/reference/cli.md)
- CLI operations guide: [`docs/reference/cli-operations.md`](docs/reference/cli-operations.md)
- HTTP API reference: [`docs/reference/http-api.md`](docs/reference/http-api.md)
- Topic retrieval details: [`docs/features/topic-based-retrieval.md`](docs/features/topic-based-retrieval.md)
- Frontend setup: [`frontend/README.md`](frontend/README.md)

## Core CLI Workflow

Install dependencies and initialize the database:

```bash
uv sync --all-extras
cp .env.example .env
uv run triangulate init-db
```

Create a case from a topic:

```bash
uv run triangulate fetch-topic "Gaza ceasefire negotiations"
```

Inspect or review saved cases:

```bash
uv run triangulate cases
uv run triangulate case show <case-id>
uv run triangulate case review <case-id>
```

Run the monitor-oriented pipeline:

```bash
uv run triangulate run-pipeline
uv run triangulate monitor --start --topics ./topics.yaml --interval 30
```

Start the FastAPI server for the frontend:

```bash
uv run triangulate serve
```

The website is presentation-only. Use the CLI, GitHub Actions, or background operators to trigger ingestion, case creation, reruns, reviews, and exception handling.

## Repository Layout

```text
frontend/                  React application
docs/                      Active docs, archive, and future plans
scripts/                   Manual utilities and one-off helpers
src/                       Application code
tests/                     Automated tests
output/                    Generated case artifacts
logs/                      Runtime logs
```

## Notes

- `docs/` is organized by active usage: `getting-started`, `architecture`, `features`, `reference`, `archive`, and `plans`.
- Historical reports and superseded design material are preserved in `docs/archive/`, not at repository root.
- `scripts/qwen_manual_check.py` is a manual utility, not part of the standard automated test workflow.
