# Current architecture: implementation audit

Date: 2026-11-14. This is an implementation-grounded supplement to [the system overview](system-overview.md), not a proposed replacement stack. See the [maintenance audit](../reference/20261114-setup-and-maintenance-audit.md) for defects and local-data findings, and the [product comparison and roadmap](../plans/20261114-product-enhancement-roadmap.md) for future work.

The [evidence workbench specification](../plans/20261114-evidence-workbench-specification.md) describes proposed evolution, including immutable captures and grouped run history. Those additions are not implemented and are not part of the current architecture described below.

## 1. Runtime boundaries

```text
Operator / external scheduler
  -> Typer CLI (src/cli/main.py)
     -> runtime config and database initialization (src/runtime.py)
     -> TopicCaseService (src/cases/service.py)
        -> source retrieval / durable intake
        -> baseline AIWorkflow / conditional party LangGraph
        -> SQLite persistence + generated report bundles

React browser
  -> services/api.ts (GET and report download helpers)
  -> FastAPI (src/http/app.py)
  -> shared TopicCaseService read models
  -> same SQLite database and report files
```

The mutation boundary is deliberately outside the website. Case creation, ingestion, reruns, review decisions, exception resolution, and recurring execution belong to CLI/service workflows. A future web control plane would require an explicit architectural decision, authentication, authorization, and job execution semantics; it is not an implied bug fix.

There is no checked-in GitHub Actions workflow. External schedulers can invoke the CLI, but the audit did not establish that external schedules are absent.

## 2. Boot and configuration

- `pyproject.toml` registers `triangulate = src.cli.main:app`; Python packages are managed with `uv` and pinned by `uv.lock`.
- `src/cli/main.py` creates runtime `logs/` and `data/` directories and configures a file/console logger at import time.
- `src/runtime.py` reads `config.toml`, initializes storage, applies migrations, and constructs the case service. Database selection includes a compatibility rule for an already-selected nondefault database.
- `src/storage/database.py` falls back to `DATABASE_PATH` when no explicit path is provided. It maintains a process-global database object and creates SQLAlchemy sessions.
- `src/ai/utils.py` loads `.env`; its LLM helpers read `LLM_MODEL`, `LLM_API_KEY`, and optional `LLM_BASE_URL`. Explicit AI configuration can override environment defaults. Do not assume all `.env.example` options are uniformly consumed by every component.
- `config.toml` contains RSS, AI endpoint/model, database, logging, and ingestion settings. Some bootstrap/logging settings are independently hardcoded, so configuration is not fully centralized.
- `triangulate serve` binds to `127.0.0.1:8000` by default. Read-only HTTP means no mutation endpoints; it does **not** mean a read-only database connection: the cached HTTP dependency initializes tables and runs migrations on first service construction.

## 3. Intake and case execution

### Durable intake

`ingest` fetches configured source material and persists `IntakeItem` records. Saved URL capture can attach an intake item to an existing case. `process` consumes queue items, runs analysis, stores an event, and marks the intake item processed or failed. Case-bound intake also creates/reuses a `CaseArticle` and refreshes case metrics.

Selection and claiming are currently separate database operations. This is a durable queue, not yet a safe multiworker job system. Supplying explicit intake IDs also bypasses the normal pending-only filter.

### Case lifecycle

`TopicCaseService.run_case()` gets or creates a case, builds a run context, and executes ordered stages:

1. **BOOTSTRAP:** infer topic/conflict context, record confirmed parties, manual links, source planning, and automation settings.
2. **RETRIEVE:** acquire source articles, record source/fetch diagnostics, deduplicate case articles, and update a monitor checkpoint.
3. **TRIAGE:** select article candidates for investigation.
4. **INVESTIGATE:** analyze articles, optionally invoke party investigation, and persist events/evidence/claims.
5. **ARBITRATE:** calculate case-level determinations and review exceptions.
6. **REPORT:** build export payloads and write the report bundle; the case becomes review-ready.
7. **REVIEW:** a lifecycle stage supported by operator review decisions, rather than another automatic branch in the run loop.

Each executed stage has a `CaseStageRun`, duration, status, metrics, artifact references, and error/fallback information. `_execute_stage()` records failures and case exceptions. Automation modes can pause work for manual action. Reruns can hydrate persisted bootstrap context and resume from a requested stage. Monitor cycles reuse case state and track newly retrieved material.

This is stage-oriented persistence, not a single transaction spanning the entire case. Each stage's persistence callback runs in one caller-owned database session. The INVESTIGATE stage passes that session to `store_event_in_db`, so a failed event write rolls back the whole investigation batch (events, claims, evidence, links, reviews, artifact and count changes), the stage and case are marked `FAILED`, and later stages including REPORT do not run. Earlier committed stages remain persisted; this is stage-transactional, not whole-case atomic. Standalone callers keep the legacy own-session `True`/`False` contract. Review decisions are bound to a versioned canonical analysis hash so an equivalent rerun preserves the decision, while materially changed analysis invalidates it and retains the prior decision metadata. See [review invalidation and transaction ownership](20261115-review-invalidation.md).

## 4. Retrieval and AI

- `ContentFetcher` handles configured RSS/API ingestion; `TopicFetcher` handles topic-driven source selection and relevance scoring.
- `TopicFetcher._load_sources()` expects a CSV under `data/source/<conflict>/`. The folder and all `data/` contents are ignored by Git. There are no source CSVs in this checkout, so a clean source-catalog setup must be supplied separately.
- `url_capture.py` extracts a manually supplied page with trafilatura, with an HTTP/BeautifulSoup fallback. Social/manual source seeds can require human review.
- Baseline `AIWorkflow` extracts claims, classifies/normalizes parties, clusters claims, produces narrative summaries, assigns provisional verification statuses, and adds location information. It is Python orchestration; do not describe every baseline step as a LangGraph node.
- The conditional party investigation workflow uses LangGraph for additional party-specific analysis when routing criteria apply.
- LLM utilities provide typed structured-output validation, retry/backoff, fail-fast authentication handling, parsing metadata, and fallbacks.
- Case/article event and evidence IDs are deterministic in the case-oriented flow. Standalone baseline events use random IDs. Deduplication is therefore not uniformly equivalent across entry points.

### Evidence semantics

Article capture creates an `EvidenceItem` with source URLs/content, provenance metadata, an unverified status, and ingestion checks. Current processing attaches that article evidence to every extracted claim as `supports`; it does not validate a supporting quotation or independently verify every claim. Source capture, LLM confidence, publisher reputation, independent corroboration, and human verification must not be treated as interchangeable concepts.

## 5. Persistence model

SQLAlchemy models live in `src/storage/models.py`:

| Group | Models / purpose |
|---|---|
| Case ownership | `TopicCase`: query, slug, lifecycle, counts, output paths, metadata |
| Execution history | `CaseStageRun`, `CaseArtifact`, `MonitorCheckpoint` |
| Input | `IntakeItem`, `CaseArticle` (`case_articles` table) |
| Analysis | `Event`, `Claim`, `Narrative`, `Party`, `PartyInvestigation` |
| Evidence | `EvidenceItem`, append-only `EvidenceCapture`, `ClaimEvidenceLink`, `EvidenceVerificationCheck` |
| Oversight | `Review`; case exception queues also live in case metadata |
| Source metadata | `Source` |

`MigrationManager` tracks schema versions in `_migrations`; eight migration versions are covered by runtime regression tests. Migration version 7 additively and idempotently adds nullable `reviews.analysis_hash` and `reviews.previous_decision_json` (see [review invalidation](20261115-review-invalidation.md)). Model `create_all()` alone is not proof that migration history is present or that an older database is fully reconciled.

E01 adds immutable source text/hash/metadata versions and a nullable current-capture pointer. Source persistence no longer requires claims; one normalized body is shared with analysis, and unavailable text is not fabricated as an empty capture. Migration 8 only adds schema, with matching fresh/legacy pointer FKs; explicit offline materialization is required for legacy content. [Capture architecture and verification](20261115-immutable-evidence-captures.md). The final isolated E01 baseline is **229 passed, 9 deselected**, with Ruff and diff checks passed.

SQLite foreign keys are declared by the ORM but are not enabled on default application connections; E01 tests enforce them on scratch connections. Existing local data contains orphan case articles; enabling enforcement must be preceded by a repair plan on a backup, not a blind toggle against production data.

The local database also contains a separate `CaseArticle` table not mapped by the application model. Its records are not automatically visible through the app's `case_articles`/`topic_cases` read model. This is observed local drift, not a supported second storage architecture.

## 6. Read API and exports

`src/http/app.py` exposes health, case list/detail, claims overview, evidence, parties, exceptions, timeline, run history, report data, and Markdown/manifest downloads. DTOs and mapper functions translate service payloads into frontend shapes. Report downloads read persisted filesystem paths; the manifest endpoint can fall back to the stored report bundle.

There are no API authentication/authorization dependencies in the reviewed application. Keep it local/trusted unless access controls are added. `/health` is a basic process response, not proof that retrieval, migrations, the LLM provider, or all cases are healthy.

Generated exports and captures belong under `output/`; logs under `logs/`; the configured SQLite file is local state. These, `.env`, environments, and caches must remain outside source control and must not be deleted merely because Git ignores them.

## 7. Frontend structure and actual capability

- React 19 + TypeScript + Vite; `App.tsx` owns React Query defaults, router, shell, and Suspense.
- `src/app/routes.tsx` lazy-loads top-level pages. `/` redirects to `/dashboard`; `/cases` is the explorer; `/cases/new` is a CLI launch guide, not a creation form.
- React Query manages HTTP state and polling; Zustand holds UI/case state. B03 case-keyed claims/evidence readers prevent late cross-case responses, reset local selection/filter state per case, and clear shared case state on workspace transitions.
- `services/api.ts` uses `VITE_API_BASE_URL`, or same-origin requests when unset. The Vite dev proxy forwards API/health requests to `127.0.0.1:8000`.
- API-backed case tabs cover evidence, claims, parties, map, timeline, exceptions, report, and run history. Viewing review state does not mean the website submits review decisions.
- Specialized pipeline/network/source/narrative routes exist outside the main case tabs. B03 monitoring/pipeline/source/narrative pages use provided records instead of synthetic alerts/health/logs, arbitrary source baselines or keyword/sentiment inference. Missing telemetry is unavailable, not a healthy zero. Recorded stage pointers do not imply completed/running stages; ambiguous attempt chronology remains indeterminate.
- Styling mixes custom page CSS with a small handwritten utility subset in `index.css`; a utility framework is not installed. B03 gives the shared Button and affected stage selectors scoped CSS with real padding/colors, native controls and visible keyboard focus rather than depending on uncompiled utility names.
- D3/React Flow support visualizations. Installed packages are not proof of implemented features; several mapping/animation dependencies have no source consumers.

## 8. Verification boundary

The default Python suite covers mocked lifecycle, storage, API contracts, exports, and related helpers. At B01 acceptance, the independently verified default run passed 156 tests with nine integration tests deselected; the accepted B02 baseline is recorded below. It does not validate the local database's historical contents, adversarial evidence grounding, scheduler operation, multiworker races, or live-provider quality.

### Test database isolation and current safety gate

After a focused B02 test accidentally wrote to the production database, `tests/conftest.py` now supplies a fresh initialized application database per test, replaces the process-global instance and rejects checkout-local paths through the application `Database` constructor before engine creation. Created engines are disposed at teardown. This protects test-time application wrapper calls, not raw SQLite/SQLAlchemy connections, import-time setup, retained references outside the fixture or subprocesses. The ingestion unit test also mocks `_update_source`.

After the safety fix and subsequent B02 corrections, the parent verified **60 focused tests; 203 passed, 9 deselected overall**, plus Ruff and diff checks in a disposable project copy. Independent review confirmed the identified acquisition blockers resolved. [Delivered acquisition/checkpoint architecture](20261115-acquisition-outcomes.md) describes canonical coverage, source identity/count validation, durable failures and legacy compatibility. Final checks did not further alter the observed post-incident production DB hash/size/mtime. The original pre-B02 hash differs; matching counts are not proof of restoration. The owner authorized continuation; B02 application behavior is now accepted, but no production repair is authorized. [Incident, evidence and owner gate](../reference/20261115-test-database-incident.md).

B00 verified a fresh `npm ci`, 13 component tests and a coverage smoke under Node 24.13.0/npm 11.6.2. B03 final parent checks passed lint/typecheck/build, **72 component tests and 10 mocked Chrome checks**, with independent re-review. [Delivered read-only UI architecture](20261115-read-only-ui-states.md) describes page boundaries, race-safe query/state ownership, styling and the Vite-only test launcher. Active LSP: 6 confirmed-clean frontend files, 5 inconclusive; not a universal clean claim. No live end-to-end ingestion was tested. The audit itself performed no production ingestion/migration/deletion/repair; the later B02 write incident remains separately disclosed above.
