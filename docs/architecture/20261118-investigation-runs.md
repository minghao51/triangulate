# Grouped investigation invocations (R01)

Date: 2026-11-18. Status: **delivered and verified; internal foundation only**. Contract:
[specification](../plans/20261114-evidence-workbench-specification.md) §7, ticket
[R01](../plans/20261114-evidence-workbench-worker-plan.md). Migration **12**.
No HTTP endpoint, no snapshot and no deployment behaviour was added.

## Why this exists

`Event.case_run_id` identifies one **stage attempt**, not a whole `run_case`
invocation. Release C needs to group the stage attempts, observations and (from
R03) the snapshot/delta of one invocation without reinterpreting that existing
FK. R01 adds that grouping identity and propagates it; it deliberately does not
claim concurrency safety or success semantics.

## Model

`InvestigationRun` (`investigation_runs`, migration 12):

| Field | Meaning |
|---|---|
| `id` | One ``run_case`` invocation ID; a rerun/resume gets a new ID |
| `case_id`, `sequence` | Owning case and per-case sequence (`UNIQUE(case_id, sequence)`) |
| `trigger` | `INITIAL`, `RERUN` (explicit rerun/resume) or `MONITOR` |
| `requested_start_stage` | Stage the invocation was asked to start from |
| `parameter_snapshot` | JSON of the run inputs (query, conflict, parties, links, caps, start stage, automation/monitor flags, trigger) |
| `predecessor_run_id` | Previous grouped run for the case, when one exists; null for the first |
| `status` | `RUNNING` → `SUCCEEDED` / `PAUSED` / `FAILED`; `INTERRUPTED` reserved for R02 |
| `coverage` | `COMPLETE_REQUESTED_SCOPE` / `PARTIAL` / `FAILED` / `NOT_ATTEMPTED` / `UNKNOWN` |
| `coverage_details` | JSON: requested stages, per-stage outcomes (status, stage-run ID, message, retrieval coverage), pause stage, trigger, predecessor |
| `started_at`, `completed_at`, `error_json` | Timing and recorded failure details |
| `baseline_snapshot_id`, `result_snapshot_id` | Nullable and **null in R01**; R03 populates them |

Enums are stored by member name, like the existing `StageStatus`/`CaseStatus`
SQL enums. The JSON uses camelCase keys for later DTO mapping.

Nullable origin references:

- `case_stage_runs.investigation_run_id` — every stage attempt of an invocation.
- `events.investigation_run_id` — the grouped invocation that created or
  authoritatively rewrote the event during investigation.
- `events.case_run_id` keeps its existing stage-attempt meaning. It is not
  repurposed.
- Intake (`_process_intake_item`), direct stage calls and legacy rows keep a null
  grouped origin: unknown history is not inferred from timestamps.

## Lifecycle and honest coverage

`run_case` records the `RUNNING` invocation before the first stage, then one
outcome per executed stage. Finalization:

- any failed stage (including a B02 recorded-but-fatal retrieval outcome) or a
  `FAILED` case → `FAILED` / coverage `FAILED`, with the failing stage/message in
  `error_json`;
- manual gate after a stage → `PAUSED` / coverage `PARTIAL` and the pause stage is
  recorded; remaining requested stages are not claimed as attempted;
- otherwise `SUCCEEDED`; coverage comes only from the canonical retrieval
  observation already on the stage result (`complete_requested_scope`, `partial`,
  `not_attempted`, `unknown`). A legacy result without structured outcomes stays
  `unknown` and is never upgraded.
- a scoped run that does not include RETRIEVE reports `COMPLETE_REQUESTED_SCOPE`
  only when every requested stage completed; otherwise `UNKNOWN`.

An unexpected error outside a stage transaction marks the invocation `FAILED`
before the exception propagates. A bookkeeping failure never masks the original
error.

## Explicit R01 non-claims

- **No concurrency safety.** Sequence/predecessor allocation is a read-then-insert
  in one session; R02 owns transactional writer admission and fencing.
- **No snapshot-ready success semantics.** The snapshot IDs stay null, and no
  change/delta or historical reader is implied. R03 owns snapshots/deltas and the
  guarded finalization transaction.
- **No public surface.** `/investigation-runs` and the changes UI belong to
  R03/R04. Grouped runs must not be deployed/used for change semantics before R02
  and R03 are integrated.

## Migration 12

Additive and inspector-guarded: creates `investigation_runs`, adds nullable
`investigation_run_id` columns (inline FK to the new table) plus indexes to
`case_stage_runs` and `events`. No row is rewritten, no stage history is
fabricated and legacy origins remain null. Fresh ORM databases and migrated
legacy databases expose the same references; the migration is idempotent and
safe to re-run.

## Tests and verification

`tests/test_r01_investigation_runs.py` (deterministic stubs, temporary DB):

- one grouped invocation across all six stages; sequence/trigger/parameters;
  stage and event origin references; `Event.case_run_id` still names the
  INVESTIGATE stage attempt; snapshot IDs null;
- rerun/resume gets a new ID, sequence 2 and the first run as predecessor; only
  the requested stage is attempted; earlier stage/event origins are unchanged;
- failed run records `FAILED` / coverage `FAILED`, failing stage/message, and no
  fabricated outcomes for stages that never ran;
- blocked run records `PAUSED` / coverage `PARTIAL` with the pause stage;
- monitor dispatch records the `MONITOR` trigger.

`tests/test_migrations.py` also covers the fresh schema and a raw version-11
legacy database (schema added, legacy stage/event rows preserved with null
grouped origins). Final gate in the disposable copy: **462 passed, 9 deselected;
Ruff clean**.
