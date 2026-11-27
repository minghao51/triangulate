---
id: F12
status: implemented-and-tested
tier: core
depends_on: [F02, F03, F08]
---

# F12 — Linked analysis exploration

**Size: M · Risk: node-ID test regressions and invented linkage.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Selected IDs and claim/evidence links flow across parties, narratives and the corroboration network without inventing linkage or truth claims.

## Read before edit (existing)
- `frontend/src/pages/tabs/PartiesTab.tsx`
- `frontend/src/pages/NarrativeLandscape.tsx` (+ `.test.tsx`) — real loading/error/retry already; preserve
- `frontend/src/pages/CorroborationNetwork.tsx` (+ `.test.tsx`), `frontend/src/components/data-visualization/NetworkGraph.tsx`
- `frontend/src/types/backend-models.ts`

## Proposed NEW paths
None.

## Implementation steps
1. Selection carried by stable entity IDs only; preserve existing node-ID handling and its tests exactly.
2. Claims and evidence link from each view into the existing claim/evidence URLs (F02 allowlists).
3. Stances show their recorded/model-derived basis, never 'true'. When assessment origin is missing, add 'Origin not recorded'; do not infer human review. A recorded stance is not a truth verdict.
4. Preserve truthful B03 behaviours: NarrativeLandscape loading/error/retry; empty narratives state distinct (`narratives-empty`) via the shared recipe.
5. Parties is current-only: direct `?snapshot=...` shows 'Unsupported historical view' before any fetch (or the API 422) with the intentional 'Open current' link (F02/F11 boundary).

## Non-goals
No new graph engine, no truth/confidence scoring, no inferred edges, no historical scope.

## Acceptance criteria (testable)
1. Existing node-ID tests pass unchanged.
2. Selecting a party/node links only recorded IDs (fixture with missing links renders no invented ones).
3. Every stance shows its known basis; missing provenance renders 'Origin not recorded', with no inferred human/verified badge (render assertions).
4. `narratives-empty` renders distinctly from network error and from loading.
5. Direct `?snapshot=` on parties shows 'Unsupported historical view' before fetch.

## Focused tests and commands
Extend `NarrativeLandscape.test.tsx`, `CorroborationNetwork.test.tsx`; PROPOSED PartiesTab tests beside the component; `npm test -- --run src/pages`, then `npm run check`.

## Rollback and compatibility
Frontend-only; per-component revert. No API changes.

## Worker brief (copy-paste)
You are the single code worker for F12 (this card). One application code writer globally — hub waves are eligibility order only. Read contracts doc §2–§3, §10 and specification R10. Stable IDs, recorded/model stance labels, truthful B03 states preserved. Focused tests first, `npm run check` + `npm test -- --run`. No commits. Return hub §5 format.