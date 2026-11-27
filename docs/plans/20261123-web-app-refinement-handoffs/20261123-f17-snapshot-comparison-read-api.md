---
id: F17
status: implemented-and-tested
tier: optional
depends_on: [F16]
---

# F17 — Snapshot comparison read API (PROPOSED, requires owner approval)

**Size: M · Risk: misusing `build_snapshot_delta` publication semantics for ad-hoc deltas.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Additive read-only GET comparing two immutable snapshots of one case, returning an `ad_hoc` DTO distinct from recorded run changes. The endpoint does **not** exist today; implement only after explicit owner approval. Not D01.

## Read before edit (existing)
- `src/cases/history.py` — `semantic_view` :500, `get_case_snapshot` :922, `snapshot_payload` :935, `snapshot_entities` :941 (reuse after compatibility checks); `build_snapshot_delta` :646 is publication semantics (stamps `observedByRunId`, needs authoritative event ids) — **do not call it unmodified**
- `src/storage/models.py` `CaseSnapshot` :393; `src/http/app.py` route/mapper patterns; `src/http/schemas.py`, `src/http/mappers.py`

## Proposed NEW paths
- PROPOSED `src/cases/snapshot_comparison.py` (focused reader over the semantic projection, not the writer)
- PROPOSED `tests/test_refinement_snapshot_comparison.py`

## Implementation steps
1. `GET /api/cases/{case_id}/snapshot-comparison?baseline=<snapshotId>&target=<snapshotId>&limit=25&offset=0` per contracts §12: both required, same case, strictly chronological (422 same/reversed), uniform 404 unknown/wrong case, limit 1–100, offset 0–2147483647.
2. Schema/identity/policy version compatibility + support checks first; otherwise 200 `availability: unavailable` + one of `incompatible_schema|incompatible_identity|incompatible_policy|unknown_version|payload_unreadable` and **no** empty ready delta. Record baseline/target coverage, times, run IDs independently.
3. DTO `mode: ad_hoc` with the contracts §12 field list; items stably ordered by entityType/entityId/changeKind; `changeKind` `entity_added|entity_absent|field_changed`; sorted changed fields; 'absent from a later observation' is never deletion/retraction; no fabricated `observedByRun`/actor.
4. Read-only: no new baseline/snapshot/report/index/model calls or writes; raw DB/index/migration dumps unchanged after a batch (assert in tests).

## Non-goals
No recorded-delta reuse (`RunChangesDTO` untouched), no `/changes` alteration, no historical search, no writes.

## Acceptance criteria (testable)
1. Same/reversed/missing params → 422; unknown snapshot or wrong case → uniform 404 (parity with each other).
2. Each of the five unavailable reasons produces 200 + `availability: unavailable` and no ready-delta items (parametrized test).
3. DTO matches contracts §12 field-for-field; ordering deterministic across calls.
4. A test replaces `build_snapshot_delta` and publication writers with raising stubs; the ad-hoc GET still succeeds with structural-presence semantics.
5. Raw DB/index/migration dump hashes identical before/after the batch (no-writes proof).

## Focused tests and commands
PROPOSED `tests/test_refinement_snapshot_comparison.py`; `uv run pytest -q tests/test_refinement_snapshot_comparison.py`; full gates in the disposable copy per contracts §1.

## Rollback and compatibility
Additive route + module; delete both to roll back. Recorded run surfaces unchanged.

## Worker brief (copy-paste)
You are the single code worker for F17 (this card). One application code writer globally. **PROPOSED endpoint — implement only with explicit owner approval recorded first.** Read contracts §12 and specification X01. Reuse the semantic projection only; never `build_snapshot_delta` unmodified; zero writes. Disposable-copy gates per contracts §1. No commits. Return hub §5 format.