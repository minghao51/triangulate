# Immutable case snapshots, deltas and run reports (R03a)

Date: 2026-11-18. Status: **storage/composition/finalization, run-level GET
contracts and the snapshot-aware detail/comparison readers are delivered and
verified; R03b is the reader half of the original R03 split.** Contract:
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
  timestamps, execution/run metadata, counts, ordering) — including derived
  claim support/oppose/source-diversity counts and narrative source counts, which
  are relationships/aggregates rather than independent observations. Entity lists
  are sorted by ID, so an equivalent rerun has an identical `semantic_hash`.
- **Stored delta**: `availability` (`initial`/`ready`), baseline/target snapshot
  IDs, coverage + caveat, observation time, and typed changes
  (`article_added`, `capture_changed`, `claim_added`,
  `claim_no_longer_extracted`, `classification_changed`,
  `relationship_changed`, `review_state_changed`, `exception_changed`) with
  before/after values. Each item records **two separate facts**: `originRunId` is
  the grouped run recorded as the entity's origin (`Event.investigation_run_id`,
  from the baseline observation for removals) or `null` when nothing recorded it —
  articles and exceptions have no origin reference, and a link row records no run
  of its own, so link changes keep an unknown origin rather than inheriting the
  claim's — and `observedByRunId` is the
  run whose successful observation produced the item. A change is never
  attributed to the observing run merely because it saw it, and `originRunId` is
  a provenance reference, not a statement about who changed a field. No actor
  attribution is invented for review/exception observations.

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

1. Compose the snapshot/delta under one explicitly opened read transaction
   (`begin_read_transaction`: pysqlite does not issue `BEGIN` for plain queries,
   so the observation is pinned deliberately) while the R02 case ownership token
   is still held.
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
  paginated typed changes carrying `originRunId` and `observedByRunId`. Running →
  pending; terminal without a snapshot → unavailable (never an empty delta);
  unknown/wrong-case run → 404. All run/snapshot GETs reject a `snapshotId` query
  selector explicitly (they are keyed by immutable IDs).
- `GET /api/cases/{case_id}/snapshots/{snapshot_id}` — snapshot metadata,
  versions, semantic hash, counts and observation time; unknown/wrong case → 404.

All are read-only; no GET creates a snapshot, report or index.

## Snapshot-aware readers (R03b)

`GET /api/cases/{case_id}/claims/{claim_id}`,
`GET /api/cases/{case_id}/evidence/{evidence_id}` and
`GET /api/cases/{case_id}/comparison` accept an optional `snapshotId`
(`snapshot_id` is accepted as the alias where the route already declared it).
Every entity is resolved from that snapshot's `payload_json`; live ORM joins are
never used to render historical state. The live row is reported only through an
explicit `liveState` comparison.

A selector names a **published** observation. A running invocation has no
snapshot ID, so there is no reader-side pending state to resolve: an unknown,
wrong-case or non-existent ID is 404. The run-level
`/investigation-runs/{id}/changes` contract keeps the
`initial|ready|pending|unavailable` distinction.

Resolution:

- **Claim** — frozen `text`, `claimSignature`, `verificationStatus`,
  `factAllegationType`, `narrativeClusterId`, `partyPositions`, `controversyScore`,
  stored support/oppose/source-diversity counts, and every payload link for that
  claim joined to its payload evidence (quote, range, capture/citation pointer,
  alignment and assessment provenance). `effectiveRelation` is recomputed with
  the same `relationship-policy-v1` resolver the live reader uses, so a frozen
  `contradicts`/`supports` cannot be upgraded and a collector link cannot
  corroborate. `verificationProvenance` applies the same legacy-shaped rule and
  otherwise stays `unknown`.
- **Evidence** — frozen metadata, the **frozen** `currentCaptureId`, and the
  snapshot's capture references. A capture body is read only from the immutable
  append-only capture row named by the snapshot and only when the stored
  `text_sha256` still equals the hash recorded in the payload; it is used for the
  code-point `charLength` and never returned. A reference whose body/hash cannot
  be verified is listed in `unavailableCaptureIds` instead of being replaced by
  another version. Related claims use the frozen claim text/signature.
- **Comparison** — both evidence rows, the pinned captures (explicit ID, else the
  snapshot's `currentCaptureId`) and the paired claims/links/citations come from
  the payload. Links added after the observation are never used, and the current
  live capture is never substituted for the pinned one. The exact-signature
  pairing, one-sided coverage caveat, explicit-contradiction rule, copy/dependency
  warnings and the response `policy` are shared with the live comparison (one
  `_claim_rows`/`_comparison_payload` implementation), plus an explicit
  “resolved from the pinned snapshot observation” caveat and
  `snapshotId` in the response.

Failure states:

| State                                                     | Result                                                                                                                              |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Unknown/wrong-case snapshot                               | 404 `Snapshot … not found for case …`                                                                                               |
| Entity absent from that snapshot                          | 404 `… is not present in snapshot …`                                                                                                |
| Conflicting `snapshotId`/`snapshot_id`, empty selector    | 422                                                                                                                                 |
| Selector on a reader without historical support           | 422 (case detail, its tabs, claims list/overview, evidence list, sources, citations, report, run/snapshot readers, capture windows) |
| Snapshot capture whose immutable body/hash is unavailable | `unavailableCaptureIds`; comparison 404s instead of showing a degraded side                                                         |
| Pinned capture with no recorded links                     | Existing `historical_unavailable` / `empty` / `unattributed_legacy` coverage                                                        |

Deliberate non-goal: historical `recordedAt`/`observedAt` values are returned
exactly as the payload froze them (they may carry `+00:00`) instead of being
reformatted into SQLite's normalized form, because a reader must not rewrite a
frozen observation. Live reads are unchanged and keep returning the persisted
form. Live responses gain the new optional `snapshotId`/`liveState`/
`unavailableCaptureIds` fields as null/empty defaults; no existing field changes
meaning. Unlike the readers above, the run/snapshot summary and capture-window
GETs are already keyed by immutable IDs, but they reject a snapshot selector too,
so no route silently ignores one.

A removed or rewritten live claim stays readable from its snapshot with its
frozen text and passages; `liveState` says `present: false` or
`textMatchesSnapshot: false`. No actor attribution, truth, corroboration,
independence or reviewer decision is ever invented, and no GET creates a
snapshot, capture or link.

Payload fidelity additions (additive; `schemaVersion`/`identityVersion`/
`policyVersion` unchanged and `semantic_view` untouched, so equivalent runs keep
an identical `semanticHash`): `claims[].narrativeClusterId`,
`evidence[].captureMetadata` and `links[].assessmentMetadata`. Snapshots
published before these additions read them as absent/unknown rather than
falling back to live rows.

## Reader tests and verification (R03b)

`tests/test_r03c_history_deltas.py` covers change-origin honesty (an entity
committed by an earlier failed run keeps that origin; removals resolve the origin
from the baseline observation; article origin stays unknown; link changes resolve
the claim origin) and consistent observation (derived counts cannot change the
projection/hash/delta, and an explicit read transaction pins one committed state
while a writer commits mid-read).

`tests/test_r03b_snapshot_readers.py` covers: frozen claim after a live rewrite;
removed claim with frozen passages and `present: false`; frozen evidence
metadata/capture list with the historical `currentCaptureId`; a frozen capture
metadata field; unavailable capture body (explicit list, comparison 404) for both
a hash mismatch and a payload with no recorded hash; a payload published before
the additive fields (absent stays unknown, never read from live rows); parity
between the live and snapshot comparison for unchanged rows; historical
contradiction plus copy/dependency caveats; a capture recorded only after the
observation; unknown/wrong-case snapshot and absent-entity 404s; both selector
aliases on all three routes; malformed/conflicting selectors; explicit rejection
on every unsupported reader; and unchanged live reads without a selector. No
capture body is duplicated into a snapshot payload.

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
version 14. Final accepted gate in the disposable project copy (after the R01–R03a
defect pass and R03c): **553 passed, 9 deselected; Ruff clean**
(`/tmp/triangulate-defectpass-{full,ruff}.log`).
