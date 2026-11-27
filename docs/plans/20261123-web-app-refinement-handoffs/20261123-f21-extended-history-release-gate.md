---
id: F21
status: implemented-and-tested
tier: optional
depends_on: [F18, F20]
---

# F21 — Extended history release gate

**Size: M · Risk: partial-bundle acceptance drift.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Independent gate for the optional extensions: X01/X02 regressions, security and version/file-failure matrices, scope tracking — with every baseline core regression retained.

## Read before edit (existing)
- F17/F18/F19/F20 focused suites (PROPOSED names in their cards)
- F16 evidence format (hub §5), contracts §12–§14

## Proposed NEW paths
- PROPOSED `tests/test_refinement_extended_gate.py` only if the focused suites cannot be orchestrated as-is.

## Implementation steps
1. Re-run the full core gates (F16 commands) — all baseline core regressions must stay green.
2. X01 matrix: one entry per `unavailableReason` (`incompatible_schema|incompatible_identity|incompatible_policy|unknown_version|payload_unreadable`) plus ordering/422/404 coverage.
3. X02 file-failure matrix: missing file, wrong case/run, symlink, traversal, oversize (413), permission failure, race guard, no-writes-on-GET, error-body redaction.
4. Security review evidence: containment, no CRLF, `nosniff`, correct mimes, request audit (GET-read-only + 3 POST families). Track **which scope the owner approved**; if only one track (X01 or X02) was approved, run that track's tests and record F21 as **not-full-bundle-accepted**.

## Non-goals
No new features, no repairs, no deploy/commit, no scope expansion.

## Acceptance criteria (testable)
1. All core gates green unchanged (counts recorded verbatim).
2. X01 matrix has a passing entry for all five unavailable reasons + the 422/404/parity cases.
3. X02 failure matrix fully covered with passing tests.
4. Request audit shows GET-read-only plus exactly the 3 POST families across both tracks.
5. The acceptance record explicitly states full bundle vs single-track (and records not-full-bundle-accepted when applicable).

## Focused tests and commands
Focused suites from F17–F20; orchestration script only if needed; full gates in the disposable copy per contracts §1.

## Rollback and compatibility
Gate-only; no feature code.

## Worker brief (copy-paste)
You are the single code worker for F21 (this card). One application code writer globally. Read contracts §12–§14 and specification X01/X02/R14. Gate the optional bundle; record scope honestly (full vs single track); engines missing ⇒ not proven; no deploy/commit. Return hub §5 format with both matrices.