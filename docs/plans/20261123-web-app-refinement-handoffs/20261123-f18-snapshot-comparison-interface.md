---
id: F18
status: implemented-and-tested
tier: optional
depends_on: [F17, F11]
---

# F18 — Snapshot comparison interface (PROPOSED, rides F17 approval)

**Size: M · Risk: ad-hoc observations conflated with recorded changes.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
UI for two explicit ad-hoc snapshot observations on the existing Changes route, clearly distinct from recorded run changes, with honest limitations and pinned links.

## Read before edit (existing)
- `frontend/src/pages/tabs/ChangesTab.tsx` (+ `ChangesTab.test.tsx`) — recorded view preserved as-is
- `frontend/src/services/deep-links.ts` — `CHANGES_PARAMS` :220 (new **browser allowlist** entry `mode=ad_hoc&baselineSnapshot=&targetSnapshot=`, explicit)
- `frontend/src/services/api.ts` (F17 client call)

## Proposed NEW paths
None beyond a focused ad-hoc panel component if the tab cannot absorb it.

## Implementation steps
1. Existing Changes route only, via `mode=ad_hoc&baselineSnapshot=&targetSnapshot=` (browser allowlist names; API query names `baseline`/`target` per contracts §12).
2. Render baseline/target as two explicit observations labelled ad-hoc: never `observedByRun`, cause, actor or deletion semantics ('absent from a later observation' phrasing per contracts).
3. Visually and semantically distinct from recorded changes; recorded view untouched when `mode` absent.
4. Render availability/unavailableReason + coverage/version limitations; pinned links to both snapshots; no historical search; no unsupported snapshot tabs on current-only views ('Unsupported historical view' before fetch).
5. Citation/capture GETs never receive snapshot params — only claim/evidence/comparison GETs accept `snapshotId`; citation/capture reject with 422 by design (`src/http/app.py:526-544`).

## Non-goals
No historical search, no snapshot tabs on current-only views, no source-article comparison changes (Compare stays), no recorded-changes edits.

## Acceptance criteria (testable)
1. `mode=ad_hoc` renders the ad-hoc panel; without it existing recorded-delta semantics, pagination and historical links remain unchanged. An additive mode-switch control is allowed; existing regressions remain green.
2. Unavailable comparisons show the reason with no empty-delta claim (fixture per reason).
3. Pinned links to baseline/target snapshots are stable across reload (URL round-trip test).
4. Client spy proves no snapshot param reaches citation/capture GETs.
5. Direct `?snapshot=` on a current-only view shows 'Unsupported historical view' before fetch.

## Focused tests and commands
Extend `ChangesTab.test.tsx` + `deep-links.test.ts`; `npm test -- --run src/pages/tabs src/services`, then `npm run check`.

## Rollback and compatibility
UI + allowlist entry only; removing the mode restores recorded-only behaviour.

## Worker brief (copy-paste)
You are the single code worker for F18 (this card). One application code writer globally. **Optional feature — implement only with F17 landed and its owner approval recorded.** Read contracts §12 and specification X01. Ad-hoc ≠ recorded; no observer/causal fabrication; citation snapshot rejection mandatory. Focused tests first, `npm run check` + `npm test -- --run`. No commits. Return hub §5 format.