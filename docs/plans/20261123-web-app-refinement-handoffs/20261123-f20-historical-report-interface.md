---
id: F20
status: implemented-and-tested
tier: optional
depends_on: [F19, F14, F11]
---

# F20 — Historical report interface (PROPOSED, rides F19 approval)

**Size: M · Risk: plausible 'latest' substitution for a missing historical artifact.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Select a stored run's report artifacts in the Report surface with clear frozen/report origin and honest missing-failure handling.

## Read before edit (existing)
- `frontend/src/pages/tabs/ReportTab.tsx` (post-F14 state model: Pending only with recorded in-progress evidence; otherwise Not generated/Unavailable)
- `frontend/src/services/api.ts` (F19 client), `frontend/src/pages/tabs/RunHistoryTab.tsx` (run pins)

## Proposed NEW paths
None beyond a focused run-pin panel if the tab cannot absorb it.

## Implementation steps
1. Optional run pin: selecting a recorded run shows its frozen report and the F19 artifact descriptors; the **current** report remains the default with an explicit link both ways ('current' never implicit).
2. Missing artifact → the F19 404 surfaces as a distinct failure state — **no plausible 'latest' or nearby-run substitution**, no recompute.
3. Checksum presentation: `checksumKind: payload_json|unknown` labelled as recorded payload checksum — never 'verified file checksum'.
4. No PDF/ZIP/generation; downloads limited to F19's allowlisted artifact bytes.

## Non-goals
No historical search, no report regeneration, no export bundles, no chain-of-custody claims.

## Acceptance criteria (testable)
1. Run pin lists exactly the F19 descriptors for the pinned run (mocked client test).
2. 'Current' report is the default view and the switch to/from a pin is an explicit link (interaction test).
3. Missing historical artifact renders the distinct failure state with no substitute content (fixture test).
4. No UI text claims verified file checksums or chain of custody (grep assertion).
5. Only F19 allowlisted downloads are offered (client spy: no other requests).

## Focused tests and commands
Extend `ReportTab.test.tsx`; `npm test -- --run src/pages/tabs`, then `npm run check`.

## Rollback and compatibility
UI-only atop F19; removing the pin panel restores current-only behaviour.

## Worker brief (copy-paste)
You are the single code worker for F20 (this card). One application code writer globally. **Optional — implement only with F19 landed and its owner approval recorded.** Read contracts §13 and specification X02. Current-by-default; explicit links; no latest substitution; checksumKind honesty. Focused tests first, `npm run check` + `npm test -- --run`. No commits. Return hub §5 format.