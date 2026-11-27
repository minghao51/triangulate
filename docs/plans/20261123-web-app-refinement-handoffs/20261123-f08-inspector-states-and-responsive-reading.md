---
id: F08
status: implemented-and-tested
tier: core
depends_on: [F06]
---

# F08 — Inspector states and responsive reading

**Size: L · Risk: Unicode offset fidelity and frozen-context correctness.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Improve (not rebuild) the E1 capture inspector: explicit diagnostics, exact quotation windows, frozen citation context, complete mobile metadata and focus restoration.

## Read before edit (existing)
- `frontend/src/components/inspector/EvidenceInspector.tsx` (+ `.test.tsx`, `.css`), `inspector-utils.ts`
- `src/http/app.py:526-544` — citation GET decorator `Depends(reject_snapshot_selector)`
- `frontend/src/services/api.ts` (capture/citation fetchers)

## Proposed NEW paths
None.

## Implementation steps
1. Explicit diagnostics, one per state: missing quotation, source unavailable, ambiguous, no match, legacy — distinct text, not colour.
2. Exact Unicode codepoint windows: Python-slice semantics server-side, `Array.from` in the browser; LF normalization server-side only — never NFKC/casefold for highlight matching.
3. Frozen citation context: citations are fetched **frozen by citation ID** — the citation GET is NOT snapshot-aware and rejects a snapshot query with 422; the API client must never forward the browser `snapshot` param to citation/capture GETs (only claim/evidence/comparison GETs accept `snapshotId`). Frozen context renders read-only.
4. Mobile completeness: all metadata (capture id, timestamps, offsets, provenance) reachable at 375x812 without horizontal clipping. Focus restored to the invoking control on close.

## Non-goals
No inspector rebuild, no new capture semantics, no snapshot-aware citation API, no NFKC/casefold highlighting.

## Acceptance criteria (testable)
1. Each of the five `inspector-*` states renders its own message (component tests).
2. A window containing astral characters highlights exactly the codepoint slice (offset unit tests).
3. Citation/capture fetch calls carry no snapshot param even when browser state has one (client spy test); a snapshot query on citation GET would 422 per `app.py:526-544`.
4. Frozen citation context is read-only (interaction test).
5. Closing the inspector returns focus to the invoking control; all metadata visible at 375x812.

## Focused tests and commands
Extend `EvidenceInspector.test.tsx` + offset tests for `inspector-utils.ts`; `npm test -- --run src/components/inspector`, then `npm run check`.

## Rollback and compatibility
Component-scoped; URL/API shapes unchanged. Revert per-file.

## Worker brief (copy-paste)
You are the single code worker for F08 (this card). Read contracts doc §10 and specification R06; the citation snapshot-rejection rule is mandatory. Improve E1, do not rebuild it. Focused tests first, `npm run check` + `npm test -- --run`. No commits. Return hub §5 format.