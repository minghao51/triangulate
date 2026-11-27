---
id: F11
status: implemented-and-tested
tier: core
depends_on: [F02, F03, F08]
---

# F11 — Run history and frozen navigation

**Size: L · Risk: stage vs grouped-run ID conflation; snapshot misuse on citation/capture GETs.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Recorded run deltas and stage history linked without conflating IDs, with freezing limited to the readers that actually support it.

## Read before edit (existing)
- `frontend/src/pages/tabs/ChangesTab.tsx` (+ `ChangesTab.test.tsx`) — `ChangesBody` pagination + truthful initial/pending/unavailable/unchanged-partial states, **preserve as delivered**
- `frontend/src/pages/tabs/RunHistoryTab.tsx` — stage-oriented
- `src/storage/models.py` — `Event.case_run_id` :193 (stage-attempt FK), `InvestigationRun` :337, `CaseStageRun.investigation_run_id` :457
- `src/cases/history.py` (readers; `build_snapshot_delta` :646 is publication semantics — not a UI reader)
- `src/http/app.py:526-544` — citation GET `Depends(reject_snapshot_selector)`

## Proposed NEW paths
None.

## Implementation steps
1. Preserve `ChangesBody` states/pagination exactly; no synthetic severity anywhere.
2. RunHistory stays stage-oriented: stage-attempt IDs (`Event.case_run_id`) and grouped `InvestigationRun` IDs labelled distinctly, never conflated. `ObservedByRunId` renders as observer stamp only — never cause/actor.
3. Freezing supports exactly claim/evidence/comparison GETs (`snapshotId` accepted) plus citations which are frozen **by citation ID** — citation/capture GETs reject snapshot selectors with 422 and the client must never forward the browser `snapshot` to them.
4. Historical boundary: direct `?snapshot=...` on current-only views (timeline/parties/search) shows 'Unsupported historical view' **before any fetch** (or surfaces the API 422) with an intentional 'Open current <view>' link — the only path that strips historical selectors.

## Non-goals
No run/ID model changes, no observer-attribution features, no historical search, no snapshot-aware citation API.

## Acceptance criteria (testable)
1. Existing ChangesBody tests pass unchanged (state set identical).
2. Fixture with both ID kinds shows distinct labelled stage vs grouped-run identifiers.
3. Observer stamps never render as actor/cause strings (render assertion).
4. Frozen claim/evidence/comparison views show frozen context + explicit 'Open current' link; citation fetch carries no snapshot param (spy).
5. `?snapshot=...` direct nav on a current-only view shows 'Unsupported historical view' before fetch; only 'Open current' strips it.

## Focused tests and commands
Extend `ChangesTab.test.tsx`; PROPOSED `RunHistoryTab` tests beside the component; `npm test -- --run src/pages/tabs`, then `npm run check`.

## Rollback and compatibility
Frontend + read-only flows; no writer or schema changes.

## Worker brief (copy-paste)
You are the single code worker for F11 (this card). Read contracts doc §10–§11 and specification R09. Preserve ChangesBody; label stage vs grouped-run IDs; citation snapshot rejection is mandatory; unsupported-historical-view before fetch. Focused tests first, `npm run check` + `npm test -- --run`. No commits. Return hub §5 format.