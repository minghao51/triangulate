---
id: F04
status: implemented-and-tested
tier: core
depends_on: [F02, F03, F05]
---

# F04 — Contextual review and annotations

**Size: L · Risk: 409/422/uncertainty semantics mis-signalled to the operator.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Complete, honest failure and uncertainty states for the three existing POST workflows (review, exceptions, annotations), plus evaluation-reader and target-picker polish.

## Read before edit (existing)
- `frontend/src/pages/CaseIntelligenceCenter.tsx` — overview review (Approve / action_required / Reject; rationale retained on error, cleared on success)
- `frontend/src/pages/tabs/ExceptionsTab.tsx`, review/annotation forms, `frontend/src/services/api.ts`
- `frontend/src/pages/tabs/tabs-state.test.tsx`, `CaseIntelligenceCenter.test.tsx`

## Proposed NEW paths
None.

## Implementation steps
1. Write-state model per form/row: pending (disable only that form/row), saved-and-refreshed, 409 writer conflict, 422 blocked approval/invalid target, transport uncertainty and recorded invalidation. A POST success followed by failed refresh means 'Accepted; refresh failed', with GET-only recovery, never 'Not saved'. For a lost POST response, GET may remain inconclusive without idempotency/correlation; require explicit confirmation and warn that retrying an annotation may append a duplicate. `retry: false`; no automatic POST retry or fake Undo.
2. Case-keyed guards: a late Case A submit response must not alter a Case B form; the 15 s caseDetail poll must never reset notes/focus or imply saved.
3. Staleness wording: 'recorded invalidation or detected refresh' only — never atomic proof of reviewed-current-revision (no server CAS exists).
4. Evaluation reader: `latest: null` renders 'No saved evaluation'; error distinct from empty; real score 0 renders 0; GET never creates an evaluation.
5. Contextual target picker: current-case entities only (case/claim/evidence/exception/narrative); frozen removed claims read-only — no fake annotation target; citation/capture are not target types.
6. Annotation audit: mirrored `annotation:*` entries shown once as technical audit, labelled distinct from human notes; no text/time dedup guessing.

## Non-goals
No new POST verbs (no supports/contradicts), no annotation update/delete, no revision/CAS preconditions, no identity from author strings.

## Acceptance criteria (testable)
1. Pending/saved/409/422/transport-uncertain/stale each render distinct text (component tests).
2. Simulated network failure triggers zero automatic POST repeats. POST-200/refresh-failure shows 'Accepted; refresh failed' and retries GET only; an inconclusive lost response warns before an explicitly confirmed retry.
3. Rationale is retained on error and cleared only on confirmed success (existing tests stay green).
4. Late Case A response cannot modify a Case B form (case-keyed test).
5. Poll-during-typing leaves notes and focus intact and shows no 'saved'.
6. `latest: null` shows 'No saved evaluation'; score 0 shows 0; GET count proves no evaluation created.
7. Target picker lists only current-case entities; mirrored audit entry renders once as audit.

## Focused tests and commands
Extend `CaseIntelligenceCenter.test.tsx`, `tabs-state.test.tsx`, ExceptionsTab tests; `npm test -- --run src/pages`, `npm run check`. Backend semantics covered by F05's PROPOSED `tests/test_refinement_review_targets.py`.

## Rollback and compatibility
UI-only; request/response payloads unchanged (F05 owns error-code changes). Per-component revert.

## Worker brief (copy-paste)
You are the single code worker for F04 (this card). Read contracts doc §6 and specification R04; depends on F02/F03/F05 landing first. Three existing POST families only, `retry: false`, honest states per contracts. Focused tests first, `npm run check` + `npm test -- --run`. No commits. Return hub §5 format.