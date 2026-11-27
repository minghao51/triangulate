---
id: F03
status: implemented-and-tested
tier: core
depends_on: [F01]
---

# F03 — Consistent reader states

**Size: L · Risk: query-key collisions and late cross-case responses.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Migrate simple effect-based readers to the existing case-keyed React Query pattern and render the four shared states (loading/empty/not-found/network-error) consistently with existing components.

## Read before edit (existing)
- `frontend/src/services/api.ts` (client functions)
- Effect-based readers in `frontend/src/pages/tabs/` and `frontend/src/pages/` (Dashboard, MonitoringCenter, PipelineMonitor, NarrativeLandscape already query-backed — preserve)
- `@tanstack/react-query` v5 (`frontend/package.json`:22) usage patterns already in the app

## Proposed NEW paths
PROPOSED one shared state-presentation helper/component only if it cannot fit existing Card/Badge boundaries.

## Implementation steps
1. Inventory effect readers; migrate simple ones to case-keyed queries with keys including every case/entity/capture/snapshot/filter/paging selector; `enabled` only for valid IDs.
2. Cancel/ignore late responses for superseded cases (AbortSignal or ignore-stale guard). Scoped invalidation via existing keys — no `['case-detail']`/`['caseDetail']` duplication.
3. Shared state recipe: loading, empty, not-found, network-error rendered with existing Card/Badge/status components; text-not-colour.
4. Polling discipline: only visible active recorded surfaces; label 'Last fetched' vs 'Last observed'; pause hidden; polls never reset notes/focus or imply saved; drafts never vanish.

## Non-goals
No generic query platform, universal state registry, dependency upgrades, or backend changes.

## Acceptance criteria (testable)
1. Each migrated reader passes its existing tests unchanged in behaviour.
2. Switching Case A → Case B mid-flight never shows Case A data in Case B (simulated late response test).
3. Every migrated case-scoped query includes its case and relevant selectors; cache tests prove two cases cannot share results. Existing global collection queries retain their global keys; no key-factory framework is introduced.
4. A background refetch leaves an in-progress note and focus intact.
5. Hidden tabs stop polling (fake timers assertion) and the four shared states each render distinct text.

## Focused tests and commands
Per-reader tests beside their components; `npm test -- --run src/pages src/services`, then `npm run check`.

## Rollback and compatibility
Migrations are per-reader; revert restores the effect version. No API contract changes.

## Worker brief (copy-paste)
You are the single code worker for F03 (this card). Read contracts doc §2, §6–§8 and specification R03. Migrate readers incrementally with case-keyed queries and the shared state recipe; no new frameworks. Focused tests first, `npm run check` + `npm test -- --run`. No commits. Return hub §5 format.