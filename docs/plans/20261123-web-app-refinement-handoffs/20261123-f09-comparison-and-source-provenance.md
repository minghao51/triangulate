---
id: F09
status: implemented-and-tested
tier: core
depends_on: [F07, F08]
---

# F09 — Comparison and source provenance

**Size: M · Risk: overclaiming publisher independence from aggregated summaries.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Keep existing comparison states/paging and crosslinks; wire SourceAnalysis to the existing sources API with honest policy/method limitations.

## Read before edit (existing)
- `frontend/src/pages/tabs/CompareTab.tsx` (+ `CompareTab.test.tsx`)
- `frontend/src/pages/SourceAnalysis.tsx` (+ `SourceAnalysis.test.tsx`) — currently counts evidence **records** (not GET calls)
- `src/http/app.py:254` `get_case_sources` (already exists), `src/cases/service.py:424` `get_source_summary` (claimId option), `src/http/schemas.py:665` `SourceSummaryDTO`, `src/http/mappers.py:871` `map_source_summary`

## Proposed NEW paths
None — **no new sources endpoint**.

## Implementation steps
1. SourceAnalysis calls the existing `get_case_sources` API and renders typed `SourceSummaryDTO` fields (`evidenceCount`, publisher/group/unknown counts, policy, groups). Keep useful existing evidence-metadata distributions separately labelled, reusing at most one case-keyed evidence collection query; no per-source fan-out or independence inferred from those counts.
2. Limitation copy adjacent to the summary: aggregated summaries are not proof of independent corroboration; copies are not independent; model consensus is not truth; policy/method limits stated plainly.
3. Comparison semantics (with F07): same-evidence comparison is **disallowed even with different captures**; `comparison-same-source` is a **validation-error** state; older single-source versions are inspected via capture history, not Compare. Keep existing states/paging; `comparison-historical-unavailable` and `comparison-dependency-warning` distinct.
4. Client guard per F08: never forward browser `snapshot` to citation/capture GETs (they 422 by design).

## Non-goals
No new endpoints, no independence scoring, no historical comparison scope, no backend changes.

## Acceptance criteria (testable)
1. SourceAnalysis issues one sources-summary GET and renders its DTO fields; any retained evidence distributions reuse the single evidence collection query. No per-evidence/source detail fan-out is introduced (client-spy test).
2. No UI copy claims publisher independence (grep assertion over component strings).
3. Existing comparison state/paging tests stay green unchanged.
4. Same-evidence comparison is refused even with different captures; `comparison-same-source` renders as a validation error; older single-source versions route to capture history, not Compare.
5. Citation/capture fetchers receive no snapshot param from this surface (spy test).

## Focused tests and commands
Extend `SourceAnalysis.test.tsx`, `CompareTab.test.tsx`; `npm test -- --run src/pages`, then `npm run check`.

## Rollback and compatibility
Read-only wiring to an existing GET; revert restores record counting. No schema change.

## Worker brief (copy-paste)
You are the single code worker for F09 (this card). One application code writer globally — hub waves are eligibility order only. Read contracts doc §10–§11 and specification R07. Wire the existing sources API (evidence records, not GET-call counting); same-evidence comparison disallowed; validation-error semantics for `comparison-same-source`. Focused tests first, `npm run check` + `npm test -- --run`. No commits. Return hub §5 format.