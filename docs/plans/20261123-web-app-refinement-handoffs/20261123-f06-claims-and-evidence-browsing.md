---
id: F06
status: implemented-and-tested
tier: core
depends_on: [F02, F03]
---

# F06 — Claims and evidence browsing

**Size: L · Risk: render budget on large loaded datasets.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
A dense responsive claim/evidence reader with explicit provenance, allowlisted client-side filters/sort/paging over the loaded dataset, stable selection and contextual inspect actions.

## Read before edit (existing)
- `frontend/src/pages/tabs/EvidenceTab.tsx`, `ClaimsTab.tsx` (+ CSS), `frontend/src/pages/tabs/tabs-state.test.tsx`
- `frontend/src/services/api.ts`, `frontend/src/types/backend-models.ts`
- `frontend/src/services/deep-links.ts` (`buildInspectorUrl` :122, `buildClaimEvidenceUrl` :127)

## Proposed NEW paths
PROPOSED small filter/sort helper beside the tabs only if it cannot fit existing components.

## Implementation steps
1. Dense responsive rows for claims and evidence; model-derived vs legacy provenance shown explicitly on every row.
2. Allowlisted filters + sort applied to the loaded array only; client paging labelled as such (no server-pagination claim); bound rendered rows (e.g. 50/page).
3. Stable selection IDs surviving re-render and filter changes; multi-select avoided unless it keeps IDs stable.
4. Contextual inspect actions deep-link via the existing inspector/claim-evidence URL builders (reuse F02 allowlists).
5. Empty-filtered state uses the shared recipe (`evidence-filter-empty`).

## Non-goals
No server pagination additions, no backend filter changes, no new endpoints, no historical scope.

## Acceptance criteria (testable)
1. Filtering/sorting issues zero network calls (mocked client assertion).
2. Loaded-dataset paging label is present and never claims server paging.
3. Every rendered row shows provenance (model/legacy) — snapshot test over fixture rows.
4. Selection survives re-render and filter application; inspect action URL contains the selected IDs.
5. Row bound is respected (renders ≤50 rows per page over a 500-row fixture).

## Focused tests and commands
Tests beside `EvidenceTab`/`ClaimsTab`; `npm test -- --run src/pages/tabs`, then `npm run check`.

## Rollback and compatibility
Presentational + client-state only; revert per-tab. No API contract changes.

## Worker brief (copy-paste)
You are the single code worker for F06 (this card). Read contracts doc §2–§3 and specification R05. Dense reader over loaded arrays only; provenance explicit; stable IDs; reuse existing URL builders. Focused tests first, `npm run check` + `npm test -- --run`. No commits. Return hub §5 format.