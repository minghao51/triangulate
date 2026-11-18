# Immutable case snapshots, deltas and run reports (R03a)

Date: 2026-11-18. Status: **storage/composition/finalization and run-level GET
contracts delivered and verified; the snapshot-aware detail/comparison readers
are the explicitly split R03b remainder.** Contract:
[specification](../plans/20261114-evidence-workbench-specification.md) §7, ticket
[R03](../plans/20261114-evidence-workbench-worker-plan.md). Migration **14**.
Depends on R01 (grouped runs) and R02 (case writer admission/fencing).

## Why this exists

Live rows are mutable: claims are rewritten, captures advance and reviews are
invalidated. Release C needs to answer “what changed since the last successful
observation?” without inventing history. A `CaseSnapshot` is an observation of
**committed** state under one read transaction at a successful run's
finalization — not a claim that the whole pipeline committed atomically and not
a statement about who caused a change.

## Model (migration 14)

`CaseSnapshot` (`case_snapshots`): `id`, `case_id`, `investigation_run_id`
(unique), `baseline_snapshot_id`, `schema_version`, `identity_version`,
`policy_version`, `semantic_hash`, `payload_json`, `delta_json`, `created_at`.
Additive and inspector-guarded; legacy runs get no fabricated snapshot.

## Payload, semantic view and delta

`src/cases/history.py` composes:

- **Canonical payload**: case/query/review notes, articles, events, claims,
  current links, frozen citations, evidence metadata, capture **references**
  (ID/hash/kind/times/metadata, never bodies), reviews, exceptions, parties,
  party investigations and narratives, plus counts and the observation time.
- **Semantic view**: a stable projection used for hashing and diffing. It
  excludes volatile fields (observation/last-seen/created/reviewed/updated
  timestamps, execution/run metadata, counts, ordering). Entity lists are sorted
  by ID, so an equivalent rerun has an identical `semantic_hash`.
- **Stored delta**: `availability` (`initial`/`ready`), baseline/target snapshot
  IDs, coverage + caveat, observation time, and typed changes
  (`article_added`, `capture_changed`, `claim_added`,
  `claim_no_longer_extracted`, `classification_changed`,
  `relationship_changed`, `review_state_changed`, `exception_changed`) with
  before/after values and the observing run ID. No actor attribution is invented
  for review/exception observations.

Safety rules: article removals are **never** inferred (leaving an RSS window or a
cap is not a removal). A claim is reported as no longer extracted only when its
event was reprocessed in the current run with an authoritative extraction
outcome (`valid`/`empty`, or legacy no-outcome replacement semantics); fallback/
unavailable/unknown runs cannot remove claims.

Baseline selection is the latest eligible snapshot whose run sequence is earlier
than the current run. A first snapshot is `initial`; identical reruns produce
`ready` with an empty delta; partial coverage stores a caveat so an empty delta
means “no changes in observed data”, never “all sources unchanged”. Failed,
paused and interrupted runs publish no snapshot and never advance the baseline.

## Run finalization and run-specific reports

On a successful run, finalization follows the §7 file/DB protocol:

1. Compose the snapshot/delta under one read transaction while the R02 case
   ownership token is still held.
2. Generate the report in a fresh temporary sibling directory under
   `output/cases/{slug}/runs/.tmp-…` using the already-composed report bundle.
3. Flush/close the files and atomically rename the directory to the immutable
   `output/cases/{slug}/runs/{run_id}/` path.
4. In one owner-guarded transaction: validate the token, insert the snapshot and
   delta, insert report artifact rows referencing the run directory, mark the run
   `succeeded` with baseline/result snapshot IDs, and update the case’s current
   report/manifest pointers.

File writing/rename failure marks the run failed and cannot produce a successful
baseline or pointer. A database failure after the rename may leave an
unreferenced immutable directory (allowed and reported by the failure record) but
publishes no pointer/baseline. The previous report pointers stay untouched.
Paused/failed runs finalize exactly as before, with no snapshot and no report
pointer change.

The legacy case-level report files are no longer written; current pointers move
to the run-specific paths, while older run directories remain untouched.

## GET contracts (R03a)

- `GET /api/cases/{case_id}/investigation-runs?limit&offset` — grouped runs,
  newest sequence first, distinct from the stage-oriented `/run-history`.
- `GET /api/cases/{case_id}/investigation-runs/{run_id}` — detail, parameters,
  coverage details, error and snapshot IDs.
- `GET /api/cases/{case_id}/investigation-runs/{run_id}/changes?limit&offset` —
  `initial|ready|pending|unavailable`, baseline/target IDs, coverage/caveat and
  paginated typed changes. Running → pending; terminal without a snapshot →
  unavailable (never an empty delta); unknown/wrong-case run → 404.
- `GET /api/cases/{case_id}/snapshots/{snapshot_id}` — snapshot metadata,
  versions, semantic hash, counts and observation time; unknown/wrong case → 404.

All are read-only; no GET creates a snapshot, report or index.

## Explicit R03b remainder

Snapshot-aware detail and comparison readers are **not delivered here**:

- `GET /claims/{claim_id}?snapshotId=` and
  `GET /evidence/{evidence_id}?snapshotId=` still reject snapshot selectors with
  422; they continue to read current rows.
- `/comparison?...&snapshotId=` likewise rejects the selector.
- Removed/rewritten claims and historical comparisons are stored in snapshot
  payloads and are inspectable through the `changes`/snapshot summary, but not
  yet through the claim/evidence/comparison inspector endpoints.
- R04’s historical change links depend on R03b.

This split was anticipated by the R03 card (“split storage/composition from
delta/readers at parent review if needed”). R03b owns snapshot-aware claim/
evidence/comparison detail readers, selector acceptance (404 when the entity is
not in that snapshot; explicit pending/unavailable states) and their tests.

## Tests and verification

`tests/test_r03_snapshots.py` covers: first snapshot (`initial`, run-specific
report directory, capture bodies not duplicated); identical rerun (equal semantic
hash, empty `ready` delta, both report directories retained); changed claim and
capture (typed delta, old snapshot still renders the old claim text); fallback
(no claim removal); partial coverage (published snapshot with caveat and no
article removals); scoped REPORT rerun; failed and paused runs (no snapshot,
baseline unchanged); file-write failure; database failure after rename (trigger
injection, no pointer/baseline); legacy runs (`unavailable`, not empty); and the
run/snapshot/changes GET contracts with cross-case 404 and limit validation.

Migrations are covered by fresh and raw version-13 legacy tests; runtime expects
version 14. Final gate in the disposable project copy: **487 passed, 9
deselected; Ruff clean** (`/tmp/triangulate-r03-{focused,full,ruff}.log`).
