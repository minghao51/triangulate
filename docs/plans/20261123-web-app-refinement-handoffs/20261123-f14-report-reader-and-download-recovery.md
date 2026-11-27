---
id: F14
status: implemented-and-tested
tier: core
depends_on: [F03]
---

# F14 — Report reader and download recovery

**Size: S · Risk: unsafe markdown rendering; mislabelled pending state.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
A clear reader for the current stored report with honest state distinctions and the two existing downloads.

## Read before edit (existing)
- `frontend/src/pages/tabs/ReportTab.tsx` (+ `ReportTab.css`)
- `frontend/src/services/api.ts` — report GET, markdown + manifest downloads (existing)

## Proposed NEW paths
None.

## Implementation steps
1. State model, strictly: **Pending** only when recorded in-progress run/stage evidence exists for the case; otherwise 'Not generated'/'Unavailable' — a missing report is **not** pending. Read errors and download errors are separate states with retry (retry read / retry download; never regenerate).
2. Render the current stored report only (core: no historical report claims, no 'latest' fallback).
3. Accessible safe markdown: headings navigable by screen reader, no raw HTML execution/script.
4. Keep exactly the two existing downloads (markdown, manifest) with their existing endpoints.

## Non-goals
No PDF/ZIP, no recompute/generation on GET, no historical artifacts (X02/F20 owns that), no new endpoints.

## Acceptance criteria (testable)
1. Fixture with a recorded in-progress stage shows Pending; fixture without one shows Not generated/Unavailable — never Pending (paired test).
2. Read error, download error and empty states render as three distinct states with working retry actions.
3. Markdown headings are navigable (a11y tree assertion) and an XSS-payload fixture executes nothing.
4. Both downloads hit the existing endpoints exactly (mocked client spy).
5. No text implies historical or 'latest' report fallback (grep assertion).

## Focused tests and commands
PROPOSED `ReportTab.test.tsx` beside the component; `npm test -- --run src/pages/tabs`, then `npm run check`.

## Rollback and compatibility
Frontend-only; revert per-file. API surface unchanged.

## Worker brief (copy-paste)
You are the single code worker for F14 (this card). One application code writer globally — hub waves are eligibility order only. Read contracts doc §11 and specification R12. Pending only with recorded in-progress evidence; otherwise Not generated/Unavailable; safe markdown; two existing downloads. Focused tests first, `npm run check` + `npm test -- --run`. No commits. Return hub §5 format.