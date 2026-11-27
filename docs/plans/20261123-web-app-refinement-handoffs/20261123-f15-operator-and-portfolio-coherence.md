---
id: F15
status: implemented-and-tested
tier: core
depends_on: [F01, F03, F11]
---

# F15 — Operator and portfolio coherence

**Size: M · Risk: polling load multiplication and capability overclaims.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Dashboard, Case Explorer, monitoring, pipeline, AI info and the CLI guide form one coherent operator surface built from existing counts — no N+1 fan-out, no new endpoints.

## Read before edit (existing)
- `frontend/src/pages/Dashboard.tsx` — 2 queries (cases + monitoringSummary), preserve
- `frontend/src/pages/CaseExplorer.tsx` + `CaseListItem` (`counts`, `openExceptionsCount`, `hasNewMaterial` in `frontend/src/types/backend-models.ts`)
- `frontend/src/pages/MonitoringCenter.tsx` (+ `.test.tsx`, 30 s poll), `PipelineMonitor.tsx` (+ `.test.tsx`, 5 s poll)
- `frontend/src/pages/OperatorLaunchGuide.tsx`, `AiIntegrationInfo.tsx`

## Proposed NEW paths
None.

## Implementation steps
1. Queue priorities from existing counts only (`openExceptionsCount`, `hasNewMaterial`, counts) — no per-case detail fan-out, no new dashboard endpoint.
2. Preserve truthful B03 states exactly: MonitoringCenter real counts + 'scheduling/alerts not provided'; PipelineMonitor saved case/stage attempts + explicit configured-vs-recorded distinction; keep `pipeline-unrecorded`/`monitoring-unavailable` distinct.
3. Polling budget: new tab polls must not multiply existing load; label 'Last fetched' vs 'Last observed'; pause when hidden.
4. AI-info/CLI guide accuracy: write surface = the three POST families + CLI case creation/ingest/rerun/rebuild/recovery only; no notifications/scheduling claims.

## Non-goals
No new dashboard API, no notification system, no scheduling features, no N+1 detail expansion.

## Acceptance criteria (testable)
1. Dashboard renders from ≤2 queries (mocked client spy); zero per-case detail calls.
2. Priority ordering follows recorded counts in a fixture (deterministic test).
3. Monitor/pipeline copy contains no unsupported capability claims (grep assertion); configured-vs-recorded is visibly labelled.
4. Hidden tab stops polling (fake-timers test); 'Last fetched'/'Last observed' labels distinct.
5. `pipeline-unrecorded` and `monitoring-unavailable` render distinctly from empty.

## Focused tests and commands
Extend `MonitoringCenter.test.tsx`, `PipelineMonitor.test.tsx`; PROPOSED Dashboard/CaseExplorer tests beside the pages; `npm test -- --run src/pages`, then `npm run check`.

## Rollback and compatibility
Frontend-only; polling constants revert independently.

## Worker brief (copy-paste)
You are the single code worker for F15 (this card). One application code writer globally — hub waves are eligibility order only. Read contracts doc §7–§8 and specification R13. Existing counts only; truthful B03 states preserved; budgeted polling; accurate AI/CLI copy. Focused tests first, `npm run check` + `npm test -- --run`. No commits. Return hub §5 format.