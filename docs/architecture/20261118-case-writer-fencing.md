# Case writer admission and fencing (R02)

Date: 2026-11-18. Status: **delivered and verified; no deployment performed**.
Contract: [specification](../plans/20261114-evidence-workbench-specification.md)
§7, ticket [R02](../plans/20261114-evidence-workbench-worker-plan.md). Migration
**13**. Depends on R01. No snapshot/delta, grouped-run API or change semantics
were added.

## Why this exists

Single-writer is a deployment assumption, not an enforced property. A run, a
case-bound intake item, a review action and an exception action could previously
interleave case writes, and there was no way to stop an abandoned writer from
committing later. R02 adds one transactional owner token per case, validates it
in every case-bound write transaction (including after awaited work) and provides
an explicit CLI interrupt that invalidates the token.

## Storage model

Nullable fields on `topic_cases` (migration 13, additive/idempotent):

| Field | Meaning |
|---|---|
| `owner_token` | Opaque UUID token; null means the case has no active writer |
| `owner_kind` | `run`, `intake`, `review`, `exception`, `annotation`, `evaluation`, `evidence` |
| `owner_ref_id` | Investigation run ID, intake item ID, or null for short writers |
| `owner_claimed_at` | Claim time |

Legacy cases have no owner. The migration claims nothing and rewrites no row.
The token is never returned by `case owner` or the HTTP API.

## Guard primitives (`src/storage/write_guard.py`)

- `claim_case_ownership(...)` — atomic `UPDATE ... WHERE owner_token IS NULL`.
  Row-count 1 is admission; otherwise `CaseWriterConflict` with the active
  kind/reference (never the token). Caller owns the transaction.
- `validate_case_ownership(...)` — compare the committed token to the writer's
  token; fail closed on mismatch/null. Used immediately before case-bound
  commits.
- `release_case_ownership(...)` — conditional clear only if the token still
  owns the case. False means the writer was superseded.
- `invalidate_case_ownership(...)` — CLI interrupt primitive; requires a matching
  token or owner reference and clears ownership atomically.
- `case_write_admission(...)` — context manager for short writers: claim →
  body → validate → release inside one caller-owned transaction; the caller
  commits **after** the context. A crash rolls the whole transaction back, so no
  claim leaks.
- `validate_or_allow_legacy_writer(...)` — direct event-store compatibility: an
  unowned case allows the historical single-writer path; an active owner rejects
  a foreign writer, and a supplied token is strict even after an interrupt.

## Protected paths

| Writer | Kind | Mechanism |
|---|---|---|
| `run_case` / `rerun_case` / `run_monitor_cycle` (via `run_case`) | `run`, ref = investigation run ID | case preparation + claim + grouped-run row commit atomically; every stage start/commit/failure, pause and finalization validates; released on success, pause, failure and conflict |
| `ingest_articles` / `capture_url_to_intake` when case-bound | `intake` | short admission; unassigned intake is outside the guard |
| `_process_intake_item` when case-bound | `intake`, ref = intake item ID | claim + `PROCESSING` commit, validation before every commit and in the event write, release in `finally` |
| `review_case` | `review` | short admission (validation + release before the outer commit) |
| `update_exception_status` | `exception` | short admission |
| `add_review_annotation` | `annotation` | short claim/write/validate/release |
| `evaluate_case` | `evaluation` | short claim/write/validate/release |
| `ingest_osint_artifact` | `evidence` | short claim/write/validate/release |
| CLI interactive event review (`review_event`) when the event has a case | `review` | admission around the decision commit only, never while prompting |
| Direct `store_event_in_db` with `case_id` | caller token | active-owner check before write and before commit; a fencing rejection is never converted to the legacy `False` result |

`_execute_stage` validates immediately before its success and failure commits, so
an interrupt during an awaited external call makes the whole stage transaction
(events, artifacts, workflow diagnostics, checkpoint, report pointer) roll back.
`_mark_stage_running` validates before creating the next attempt. A private
direct-stage seam with no owner token is not a writer entry point and is
documented as unguarded.

## Run lifecycle

1. Generate the owner token and investigation-run ID.
2. In one transaction: create/update the case, claim ownership, insert the
   `RUNNING` investigation run (sequence/predecessor read under the claim), commit.
3. Run stages; each case-bound commit validates the token.
4. Finalize the grouped run (status/coverage) under the same token, then release.
5. On a conflict/interrupt: stop, do not overwrite the interrupt's terminal run
   state, and release only if this token is still the owner.

Paused/failed runs release ownership. A resumed invocation gets a new token and a
new run ID. An old token can never commit after a takeover.

## Explicit CLI recovery

```text
triangulate case owner CASE_ID
triangulate case interrupt CASE_ID --run-id <owner-ref> --reason "..." [--yes]
# or --token <active-token> for an orphaned short-writer claim
```

An active RUN owner must resolve to a run row for that case with status
`RUNNING`; a missing or already-finished run is rejected and the ownership clear
is rolled back in the same transaction, so a rejected interrupt never reports a
recovery that did not happen. Every path that does not actually interrupt
(missing reason, missing reference, declined confirmation, rejected interrupt)
exits **nonzero**, so automation cannot read a failed recovery as a success.

`interrupt` requires a non-empty reason, explicit confirmation (prompt unless
`--yes`) and a matching owner reference or token. It atomically clears ownership
and marks the owning `RUNNING` investigation run `INTERRUPTED` with the reason;
it does **not** stop the process. Later case-bound commits from the old writer
fail validation. There is no elapsed-time recovery and no GET-side recovery. A
process death can leave a claim until an operator runs this explicit command.

HTTP review/exception/annotation conflict responses map to **409** with a safe
detail; no new mutation endpoint was added.

## Tests and verification

`tests/test_r02_case_writer_fencing.py` covers: conflicting run rejection with no
run row or leaked case mutation; case-bound intake rejection and post-release
success; conflicting intake processing; review/exception/annotation/evaluation/
OSINT rejection; paused-run release; interrupt reason/confirmation/match
validation and INTERRUPTED run state; stale-token takeover; direct event writes
(rejected while owned, legacy allowed when unowned); a gated retrieve stage whose
commit fails after an interrupt (no event, no advanced checkpoint); a gated report
stage whose pointer commit fails after an interrupt; and the HTTP 409 mapping.
`tests/test_migrations.py` covers fresh and raw version-12 legacy databases;
`tests/test_runtime.py` expects migration 13.

Final gate in the disposable project copy: **475 passed, 9 deselected; Ruff
clean** (`/tmp/triangulate-r02-{focused,full,ruff}.log`).
