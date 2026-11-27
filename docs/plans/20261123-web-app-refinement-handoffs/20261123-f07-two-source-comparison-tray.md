---
id: F07
status: implemented-and-tested
tier: core
depends_on: [F06]
---

# F07 — Two-source comparison tray

**Size: M · Risk: cross-context or cross-case selection mixing; same-evidence slips through.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
A session-only, case-scoped comparison draft that pins exactly two distinct **evidence** items and commits to the existing Compare URL safely.

## Read before edit (existing)
- `frontend/src/pages/tabs/CompareTab.tsx` (+ `CompareTab.test.tsx`)
- `frontend/src/services/deep-links.ts` — `COMPARISON_PARAMS` :140, `buildComparisonUrl` :205, `parseComparisonSelection` :187

## Proposed NEW paths
None; tray state lives in existing state containers.

## Implementation steps
1. Tray in session memory, case-scoped: max 2 **distinct evidence** items + pins within one context. Selecting a third is **explicitly rejected** (visible message) — never silent replacement. Same-evidence comparison is **disallowed even with different captures**: the selection is refused up front and, if it ever reaches the compare view, `comparison-same-source` is a **validation-error** state — never a valid committed comparison. For an older single source with multiple versions, direct users to capture history — not Compare.
2. Commit path: `buildComparisonUrl` → server default-capture resolution → URL replaced with pinned capture IDs.
3. Changing case or historical context clears the draft after an explicit notice; no cross-context mixing; no auto-replacement anywhere.
4. Tray survives re-render within a session; never persists across cases.

## Non-goals
No new store/framework, no server-side drafts, no third-slot design, no historical comparison scope.

## Acceptance criteria (testable)
1. Third distinct selection is visibly refused and the tray keeps its original two entries.
2. Same-evidence selection with two different captures is refused; if forced to the compare view, `comparison-same-source` renders as a validation error — never as a comparison.
3. A single source with older versions links to capture history, not Compare (interaction test).
4. Committed URL contains pinned capture IDs after default resolution (unit + URL-parse integration).
5. Case switch clears the tray after the explicit notice; tray is empty when inspected from another case.

## Focused tests and commands
Extend `CompareTab.test.tsx` and `deep-links.test.ts`; `npm test -- --run src/pages/tabs src/services`, then `npm run check`.

## Rollback and compatibility
Session-only state; delete the tray module to roll back. URL builder signatures unchanged.

## Worker brief (copy-paste)
You are the single code worker for F07 (this card). One application code writer globally — hub waves are eligibility order only. Read contracts doc §4 and specification R05/R07. Cap 2 distinct evidence items; same-evidence comparison disallowed even with different captures; `comparison-same-source` is a validation error; single-source versions go to capture history. Focused tests first, `npm run check` + `npm test -- --run`. No commits. Return hub §5 format.