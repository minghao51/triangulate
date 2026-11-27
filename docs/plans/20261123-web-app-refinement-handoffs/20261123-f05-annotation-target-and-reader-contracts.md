---
id: F05
status: implemented-and-tested
tier: core
depends_on: [F00]
---

# F05 — Annotation target and reader contracts

**Size: M · Risk: service-level compatibility (pinned ValueError test) and over-broad 404 mapping.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Case-owned annotation target validation with a uniform 422, plus HTTP route-level 404 for missing cases on review-activity/evaluation readers — while preserving service-level read exception semantics exactly.

## Read before edit (existing)
- `src/cases/service.py` — `add_review_annotation` :4154, `get_case_review_activity` :4099, `get_case_evaluation_summary` :4403
- `src/http/app.py` — annotations + review-actions POST routes, `/api/cases/{case_id}/review-activity` :577–585
- `src/http/schemas.py` (`ReviewActivityDTO` :220, `EvaluationSummaryDTO` :418), `src/http/mappers.py`
- `src/storage/models.py` — `Claim` :203 (`event_id` FK :209 → `Event.id`), `Event.case_id` :192, `Claim.narrative_cluster_id` :212 (**no FK**), `Narrative` :229 (`cluster_id` :235, **no case_id**)
- `tests/test_http_api.py` — pinned `test_case_evaluation_summary_missing_case_still_errors` :727: **direct service call asserting `pytest.raises(ValueError)` — service compatibility, NOT an HTTP-500 assertion. Preserve it verbatim.**

## Proposed NEW paths
- PROPOSED `tests/test_refinement_review_targets.py` (route-level 404s, membership, parity, no-write proofs)

## Implementation steps
1. Membership checks for targets `case|claim|evidence|exception|narrative`: claim via its event's `case_id`; narrative via reachable case association — the case-scoped claims overview where `claim.narrativeClusterId == narrative.clusterId`. **Never invent `narrative.case_id`.** If membership is unprovable → uniform 422. No history rewrites/backfill.
2. Missing case → 404 (HTTP layer). Missing or wrong-case target → the **same** uniform 422 (no existence leak). Validation runs after writer admission so 409 precedence is preserved. Invalid target writes no annotation and no audit rows.
3. Route-layer missing-case mapping **only**: review-activity/evaluation GET handlers translate a missing-case `ValueError` to 404; genuine evaluation/activity read failures keep their current behaviour and are **not** masked as 404. The service functions keep raising `ValueError` on missing case — pinned test :727 stays **unchanged and green**. Add new HTTP route-level 404 tests instead of rewriting it.
4. No identity trust from author strings; no update/delete endpoints; no immutability/tamper-proof audit claims; no current-annotation GET invention.

## Non-goals
No new POST families or schemas, no DB schema change (no `narrative.case_id` column), no service-exception redesign, no audit redesign, no pagination on review-activity.

## Acceptance criteria (testable)
1. Wrong-case target and missing target return byte-equivalent 422 bodies (parity test).
2. Missing case returns 404 at the HTTP route level on annotation POST, review-activity GET and evaluation GET (new route tests).
3. Direct service calls on a missing case still raise `ValueError`: `tests/test_http_api.py:727` is unchanged and green.
4. A genuine non-missing-case evaluation/activity read failure is not converted to 404 (discriminating test with a stubbed failing reader).
5. A 409 writer conflict still fires before target 422 (ordering test).
6. Narrative target accepted iff reachable via the case claims-overview cluster association; rejected otherwise.
7. Invalid target leaves zero new annotation rows and zero new audit rows.

## Focused tests and commands
PROPOSED new `tests/test_refinement_review_targets.py`; preserve the direct-service `ValueError` regression in `tests/test_http_api.py` (including :727). Add HTTP-specific regressions without changing that service contract. `uv run pytest -q tests/test_refinement_review_targets.py tests/test_http_api.py`, then `uv run pytest -q --disable-warnings` + `uv run ruff check src tests scripts --output-format concise` in the disposable copy.

## Rollback and compatibility
Service exception semantics untouched (`ValueError` preserved) — only route-level mapping is new; reverting the route handlers restores the prior unmapped-500 behaviour with the pinned test unaffected either way. No request/response shape change.

## Worker brief (copy-paste)
You are the single code worker for F05 (this card). One application code writer globally — hub waves are eligibility order only. Read contracts doc §9 and specification R04. Constrained behaviour corrections only: uniform 422 targets, route-level missing-case 404 **only** (never mask genuine read failures), service `ValueError` compatibility preserved, pinned test :727 untouched. Python gates in the disposable copy per contracts §1. No commits. Return hub §5 format.