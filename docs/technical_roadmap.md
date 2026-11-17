# Triangulate Technical Roadmap

This document is the active technical roadmap for Triangulate. It replaces earlier roadmap drafts and anchors future work in the repository as it exists today: a local-first Python application with CLI-triggered workflows, a read-only FastAPI projection layer, SQLite-backed persistence through SQLAlchemy, and a React frontend that consumes persisted case state.

## Summary

Triangulate already supports topic-oriented investigations, persisted case lifecycles, AI-assisted claim and party analysis, case review flows, and a presentation-oriented web UI. The next stages should deepen the platform in five directions without breaking current boundaries:

- strengthen schema and service contracts around cases, claims, parties, evidence, and run history
- expand ingestion and evidence enrichment, including operator-friendly OSINT import paths
- evolve the existing AI layer from specialized functions and workflows into more explicit orchestration with typed state and resumability
- improve operator review workflows in the CLI and frontend while keeping mutation boundaries deliberate
- add evaluation, regression tracking, and observability so quality can be measured as the system grows

The roadmap is intentionally incremental. It does not assume an immediate rewrite to a cloud-native system, a mandatory database migration, or a write-capable frontend from day one.

## Current State

### Runtime and boundaries

- `src/cli/` is the primary mutation surface. Operators can ingest content, process URLs, fetch topic cases, run the pipeline, monitor topics, and review or rerun cases.
- `src/cases/` is the orchestration boundary for topic-case lifecycle behavior and read-model construction.
- `src/http/` exposes a read-only FastAPI API for health checks, case lists, case detail, and tab-oriented case views.
- `src/storage/` uses SQLAlchemy models and migration helpers against SQLite today.
- `frontend/` is a React presentation layer that reads the HTTP API and does not own pipeline mutations.
- `src/ai/` already contains multiple agent-style modules and workflows, including claim collection, clustering, narration, classification, and party investigation.

### Capabilities already present

- local topic-driven case generation and monitor loops
- persisted case status, stage run, review, claim, event, narrative, and party data
- report export surfaces for JSON and Markdown artifacts
- HTTP read models for the case index and detail tabs
- a frontend with dashboard, case index, case detail, and investigation-oriented presentation flows
- a growing AI workflow surface, including LangGraph-based party investigation

### Gaps to address

- data contracts across claims, evidence, parties, exceptions, and lineage are still evolving and need stronger normalization
- ingestion is useful but not yet a broad evidence-ingestion platform for external OSINT tooling
- AI orchestration exists, but workflow state, retry policy, taxonomy-driven review, and auditability are not yet consistent across the stack
- the frontend helps operators inspect results but remains limited for review collaboration, annotations, and audit-heavy workflows
- quality evaluation and regression tracking are not yet a first-class operational loop

## Guiding Principles

1. Local-first remains the default. New features should work on a single developer machine before they assume background services or multi-user deployment.
2. Current boundaries are preserved until intentionally changed. The frontend should consume backend capabilities rather than forcing premature backend rewrites.
3. Typed contracts over implicit payloads. New AI workflow stages, HTTP responses, and stored artifacts should converge on explicit schemas.
4. Incremental operator trust. Review, audit, and evaluation features should ship alongside automation rather than after it.
5. Roadmap phases are cumulative. Each phase should leave behind stable interfaces that later phases extend rather than replace.

## Target Architecture Direction

The medium-term target is still a Python-first investigation platform with:

- CLI and background triggers for ingestion, investigation, reruns, and monitor jobs
- a service-layer orchestration boundary in `src/cases/` backed by typed workflow state
- a persistence layer that can continue on SQLite in the near term and remain portable to Postgres if concurrency demands increase
- a read-focused HTTP layer that can grow new operator views first, then selective mutation endpoints only where human-in-the-loop workflows justify them
- a frontend that becomes a richer operator console for investigation review, evidence comparison, and case monitoring
- an AI layer that supports multi-step, multi-agent investigation with durable state, transparent outputs, and evaluation hooks

## Phased Roadmap

### Phase 1: Stabilization and Contract Hardening

Goal: align the docs, data model, and service contracts with the as-built system so later phases land on stable foundations.

Key work:

- audit and tighten schemas for claims, evidence, parties, reviews, exceptions, case runs, and report bundles
- make lineage fields and case-stage metadata consistent across storage, service, HTTP mapper, and frontend model layers
- document canonical concepts such as case, event, claim, evidence item, party, exception, and operator review state
- identify places where current AI outputs rely on loosely structured dicts and introduce typed wrappers where that reduces drift
- ensure runtime configuration for models, sources, and workflow toggles is explicitly documented and test-covered

Acceptance signals:

- storage and HTTP layers use consistent terminology for core investigative entities
- case detail tabs no longer depend on ambiguous field names or shape translation quirks
- docs for architecture and roadmap agree on current boundaries and responsibilities

### Phase 2: Ingestion and Evidence Enrichment

Goal: expand from topic retrieval into broader evidence acquisition while staying compatible with the CLI-first operating model.

Key work:

- add OSINT import surfaces under the CLI, for example:
  - `triangulate osint ingest --tool <tool> --file <path> --case-id <id>`
  - `triangulate osint stream --tool <tool> --watch <dir> --case-id <id>`
- support structured imports for high-value external outputs such as SpiderFoot, Hunchly, Sherlock, TinEye, or similar evidence sources
- introduce persisted OSINT artifact and evidence-linkage records with source tool metadata, import timestamps, raw artifact pointers, and case relationships
- improve deduplication, provenance capture, and source linking so imported artifacts can be surfaced alongside native evidence
- extend read models so evidence and report views can expose provenance, source type, and artifact relationships without changing the frontend mutation boundary

Public interface additions:

- new CLI subcommands for OSINT import and optional directory watching
- additive storage models for imported artifacts, provenance, and evidence relationships
- new read-only HTTP fields or endpoints for OSINT-backed evidence views if the frontend needs dedicated presentation surfaces

Acceptance signals:

- operators can attach external OSINT artifacts to a case without manual database edits
- imported artifacts are visible in persisted case detail output and frontend evidence views
- provenance for imported evidence is queryable and exportable

### Phase 3: Orchestration, Taxonomy, and Durable AI Workflow State

Goal: evolve the current AI layer into a more explicit multi-stage orchestration model that is testable, resumable, and review-aware.

Key work:

- define typed workflow-state models for the existing investigation pipeline, including stage status, intermediate artifacts, retry counts, and operator-facing summaries
- consolidate current agent-style modules behind clearer contracts for collection, party analysis, classification, narrative synthesis, and arbitration
- introduce a versioned taxonomy file for bias, framing, and review heuristics so critique logic is configuration-backed rather than prompt-only
- persist workflow checkpoints and agent outputs needed for resumability, debugging, and later evaluation
- standardize retry guards, fallback behavior, and failure states for multi-step AI runs

Public interface additions:

- additive persisted workflow-state or agent-output records tied to cases and case-stage runs
- optional CLI inspection surfaces for workflow state, retries, or checkpoint summaries
- expanded read-only HTTP views for operator-visible workflow diagnostics where useful

Acceptance signals:

- long-running or multi-step investigations can be resumed from durable state
- AI outputs for core stages are typed and auditable instead of being opaque blobs only
- taxonomy version and workflow metadata can be traced from case output to stored records

### Phase 4: Operator Workflow and Selective HITL Expansion

Goal: improve review throughput and decision quality while preserving deliberate control over where mutations are allowed.

Key work:

- add annotation, commenting, and flagging workflows for claims, evidence, narratives, and exceptions
- support richer audit-trail capture for human review actions, including timestamps, decisions, and rationale
- improve side-by-side comparison and contradiction review surfaces for evidence, claim clusters, or narrative variants
- expand frontend operator tooling for monitoring, case detail, and review queues using read models first
- introduce selective mutation endpoints only where the product truly benefits from in-app human-in-the-loop checkpoints, such as approve, defer, inject context, or resolve exception actions

Mutation boundary rule for this phase:

- CLI remains the default trigger surface
- new HTTP mutation endpoints are additive and narrow in scope
- frontend write capabilities should be introduced only for clearly defined review actions, not as a blanket shift to a fully mutable web application

Acceptance signals:

- human review actions are captured in a durable audit trail
- operators can compare and triage evidence or claim conflicts faster than with the current presentation-only flows
- any new write-capable frontend actions map to explicit backend review operations with bounded scope

### Phase 5: Evaluation, Regression Tracking, and Observability

Goal: make system quality measurable and regressions visible as ingestion, AI orchestration, and HITL features expand.

Key work:

- add an evaluation CLI that scores completed cases, reports, or workflow outputs against stable quality criteria
- track metrics such as neutrality, evidence linkage, contradiction handling, review burden, and source diversity
- persist evaluation runs with references to model configuration, taxonomy version, workflow version, and case output version
- add lightweight observability for pipeline timing, retry counts, import volume, stage failures, and review backlog
- expose summary metrics in operator-facing read models and dashboards where they support decision-making

Public interface additions:

- evaluation-oriented CLI commands and storage tables
- read-only HTTP summaries for monitoring and reporting views
- exportable evaluation artifacts for regression comparison across versions

Acceptance signals:

- changes to prompts, taxonomy, or orchestration can be compared against a persisted baseline
- operators can identify failure hotspots and review bottlenecks from system metrics
- evaluation becomes part of normal iteration rather than an occasional manual exercise

## Cross-Cutting Interface Plan

### CLI

The CLI remains the primary operational control plane. Expected growth areas:

- OSINT ingest and watch commands
- workflow inspection and checkpoint commands
- evaluation and reporting commands
- more explicit review and exception-management helpers

### Storage

Likely additive entities over the roadmap horizon:

- OSINT artifacts and provenance links
- workflow checkpoints and agent outputs
- bias or review taxonomy versions
- audit trail entries for human review actions
- evaluation runs and metric summaries

These should remain additive where possible so current case data and report exports keep working during migration.

### HTTP API

Near-term changes should favor:

- broader read models for evidence, workflow diagnostics, audit history, and monitoring
- stable DTOs for richer frontend tabs and dashboards

Mutation-capable endpoints, if added, should be limited to explicit operator review actions and documented as a boundary change rather than treated as an implementation detail.

### Frontend

The frontend should continue to evolve as a consumer of backend capabilities:

- richer evidence and claim review tabs
- comparison and contradiction analysis views
- audit and run-history presentation
- monitoring and evaluation dashboards

Frontend features should not assume backend mutation support until corresponding service and HTTP contracts exist.

## Deferred Decisions and Non-Goals

The following are intentionally deferred until they are justified by concrete product pressure:

- mandatory migration from SQLite to Postgres before local concurrency or deployment needs require it
- a full replacement of current AI workflow tooling solely to standardize on one orchestration framework
- unrestricted write access from the frontend for all pipeline actions
- cloud-native queueing, multi-service decomposition, or managed infrastructure as a prerequisite for roadmap progress
- real-time collaborative multi-operator workflows beyond what the current product and deployment model demand

## Implementation Notes

- Prefer additive schema changes and backwards-compatible read-model evolution through Phases 1 to 4.
- Keep older roadmap drafts in `docs/archive/plans/` for historical context only.
- Update the roadmap when a phase materially lands, slips, or changes scope so it stays a living technical source of truth rather than a one-time proposal.

## Changelog

- 2026-03-24: Replaced prior roadmap drafts with a single canonical technical roadmap grounded in the current repository state
