# System Overview

This document describes the current implementation as built in the repository.

## Runtime Components

- CLI: Typer application in `src/cli/main.py`
- Case orchestration: `src/cases/`
- HTTP API: FastAPI app in `src/http/app.py`
- Storage: SQLite models, migrations, and services in `src/storage/`
- Frontend: React app in `frontend/`

## Runtime Configuration

- Primary config file: `config.toml`
- Environment variables: `.env`
- Runtime helpers: `src/runtime.py`

The application reads model and source configuration from disk and constructs services locally. Generated artifacts and logs are stored in the workspace rather than an external managed platform.

## Data and Output Paths

- `data/`: source and local dataset inputs
- `output/`: generated case bundles and exported reports
- `logs/`: runtime logs
- SQLite database path: configured through the storage layer and initialized by `triangulate init-db`

## Case Flow

The current case-oriented flow is:

1. `fetch-topic` or monitor input creates a topic case request.
2. Retrieval and analysis stages gather articles, infer conflict context, and score relevance.
3. Investigation stages persist claims, parties, evidence, exceptions, and run history.
4. A report bundle is written to `output/`.
5. The CLI and HTTP API read from the same persisted case state.

## Boundary Note

- `src/cases/` is the orchestration boundary.
- `src/cli/` and future worker processes are the trigger surfaces for ingestion and execution.
- GitHub Actions is an acceptable trigger surface when it invokes the same CLI or service-layer workflows.
- `src/http/` is a read-model projection layer only.
- `frontend/` must not initiate pipeline mutations.

## HTTP Boundary

The frontend-facing API exposes:

- `GET /health`
- `GET /api/cases`
- `GET /api/cases/{case_id}`
- Tab-oriented case detail endpoints under `/api/cases/{case_id}/...`

The HTTP boundary is intentionally read-only. Case creation, reruns, reviews, exception handling,
ingestion, and monitoring are triggered outside the website via CLI or background operators.

These endpoints are defined in `src/http/app.py` and use DTOs from `src/http/schemas.py`.

## Frontend Boundary

The frontend calls the HTTP API via `frontend/src/services/api.ts` and reads its base URL from `VITE_API_BASE_URL`. The current UI supports:

- case index
- CLI launch guidance
- case detail tabs

## Non-Goals for This Doc

This is not a roadmap or speculative architecture document. Historical design material has been archived under `docs/archive/`.
