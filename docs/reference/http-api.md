# HTTP API Reference

The frontend-facing API lives in `src/http/app.py` and exposes persisted case
data over JSON. It registers 31 GET routes and 3 POST routes.

## Read-only inspection surface vs narrow review mutation exception

- **Inspection/read surface: GET only.** No GET handler creates, edits or
  deletes domain state. `GET /api/cases/{case_id}/evaluation` is a pure reader:
  a case without an evaluation returns `latest: null` and never generates a run
  (`src/cases/service.py:4358-4404`). Cold-start schema initialization (tables
  plus migrations on first service construction) is documented separately and is
  not a domain mutation (`docs/architecture/20261114-current-architecture.md:37`).
- **Narrow review mutation exception: three POST routes** for human-in-the-loop
  review only — a review decision, an exception action and a review annotation
  (see [Review mutation POSTs](#review-mutation-posts-the-narrow-exception)).
  They do not create cases, run or rerun stages, ingest material, or execute the
  pipeline.
- **Case creation, ingestion, reruns and execution stay at the CLI/service
  boundary.** `POST /api/cases` (case creation) is not registered and answers
  405; `POST /api/cases/{case_id}/review` and `POST /api/cases/{case_id}/rerun`
  are not registered and answer 404
  (`tests/test_http_api.py:445-453`).
- There is **no authentication or authorization** on any route. The deployment
  assumption is local/trusted (specification §1). Do not expose this API
  publicly without a separate access-control decision.

## Cross-cutting request semantics

**Snapshot selectors.** Snapshot-aware readers (`claims/{claim_id}`,
`evidence/{evidence_id}`, `comparison`) accept `snapshotId` (or `snapshot_id`)
to pin an immutable observation; current rows are never substituted for a
historical one. Current-state readers reject any `snapshotId`/`snapshot_id`
query parameter with **422** (`reject_snapshot_selector`,
`src/http/app.py:92-103`). On snapshot-aware readers, conflicting
`snapshotId`/`snapshot_id` values or an empty selector are **422**
(`src/http/app.py:106-123`); an unknown snapshot is **404**.
The ad-hoc snapshot-comparison reader is different: it pins **two** observations
with `baseline`/`target` (see [Snapshot Comparison](#snapshot-comparison-ad-hoc))
and rejects an unrelated `snapshotId`/`snapshot_id` with **422**.

**Common failure codes.**

| Status | Meaning |
|---|---|
| 404 | Unknown case/entity, unknown snapshot on a snapshot-aware reader, or any snapshot-comparison miss |
| 422 | Malformed query/body, unsupported snapshot selector, or invalid input range |
| 409 | Case-writer conflict on a review POST (writer fencing; see below) |
| 503 | Search index capability unavailable (search route only), or historical storage missing/uninitialized/unusable (the three historical GETs only) |

**Missing-case readers.** A missing case on the review-activity reader and the
evaluation reader is a **404** at the HTTP layer (`_reader_missing_case_error`
in `src/http/app.py`). Only the service's exact missing-case `ValueError` is
translated; every other reader failure keeps propagating unmapped so a genuine
evaluation/activity read fault is never disguised as "case not found". The
service functions still raise `ValueError` for direct and CLI callers
(`src/cases/service.py`), a contract pinned by
`tests/test_http_api.py::test_case_evaluation_summary_missing_case_still_errors`;
the route-level 404s are covered by `tests/test_refinement_review_targets.py`.
The three review POSTs below also map their errors explicitly.

## Endpoints

### Health

```text
GET /health
```

Returns literal `{ "status": "ok" }` without resolving the case service or
opening the database (`src/http/app.py:153-155`). It is a **liveness** probe
only: `ok` does not mean the configured historical database exists, is migrated
or is readable. See [Historical storage availability](#historical-storage-availability).

### Case Collection and Detail

```text
GET /api/cases                                 -> list[CaseListItem]
GET /api/cases/{case_id}                       -> CaseDetailResponse
```

### Case Tab Readers

Each returns one tab slice of the case detail. Unknown case → 404; snapshot
selector → 422.

```text
GET /api/cases/{case_id}/claims
GET /api/cases/{case_id}/claims/overview       -> ClaimsOverviewResponse
GET /api/cases/{case_id}/evidence
GET /api/cases/{case_id}/exceptions
GET /api/cases/{case_id}/parties
GET /api/cases/{case_id}/timeline
GET /api/cases/{case_id}/run-history
GET /api/cases/{case_id}/workflow              -> WorkflowDiagnosticsDTO
GET /api/cases/{case_id}/report
GET /api/cases/{case_id}/review-activity       -> ReviewActivityDTO
```

The review-activity reader returns the case's annotations plus its audit
entries, newest first, with no pagination. Unknown case → 404.

### Entity Detail Readers

```text
GET /api/cases/{case_id}/claims/{claim_id}                      -> ClaimDetailDTO
GET /api/cases/{case_id}/evidence/{evidence_id}                 -> EvidenceDetailDTO
GET /api/cases/{case_id}/evidence/{evidence_id}/captures/{capture_id} -> CaptureWindowDTO
GET /api/cases/{case_id}/citations/{citation_id}                -> CitationDTO
GET /api/cases/{case_id}/snapshots/{snapshot_id}                -> SnapshotSummaryDTO
```

- Claim and evidence detail accept `snapshotId` (see snapshot semantics above);
  unknown claim/evidence (or one absent from the pinned snapshot) → 404.
- `CaptureWindowDTO` is the only text-bearing DTO: one bounded code-point window
  of an immutable capture. `start` ≥ 0 (default 0), `length` 1..50,000 (default
  20,000) (`src/http/app.py:86-87, 476-488`). A malformed range (e.g. `start`
  beyond the stored body) → 422, never a silently clamped window; unknown
  capture → 404.
- `CitationDTO` resolves a frozen validated passage without a live claim or
  link; unknown citation → 404.
- `SnapshotSummaryDTO` is metadata/counts; entity bodies use the snapshot-aware
  detail readers.

### Sources

```text
GET /api/cases/{case_id}/sources               -> SourceSummaryDTO
```

Observed publishers and dependency groups (P01). Optional `claimId`/`claim_id`
filter (conflicting aliases → 422); unknown claim → 404, unknown case → 404
(`src/http/app.py:234-256`).

### Comparison

```text
GET /api/cases/{case_id}/comparison            -> ComparisonDTO
```

Deterministic two-capture comparison (P02). Query parameters:

| Parameter | Meaning |
|---|---|
| `left`, `right` | required; evidence IDs |
| `leftCapture`, `rightCapture` | optional capture IDs |
| `snapshotId` | optional immutable-observation pin |
| `limit` | default 25, 1..100 (`src/cases/comparison.py:53-54`) |
| `offset` | default 0, ≥ 0 |

Missing `left`/`right` or out-of-range paging → 422; unknown evidence/capture
(`ComparisonNotFound`) → 404; semantically invalid comparison
(`ComparisonInvalid`) → 422 (`src/http/app.py:258-293`).

### Case Search

```text
GET /api/cases/{case_id}/search
```

Case-scoped lexical search over the optional FTS5 index (migration 15). `GET`
only; the route never writes, rebuilds or repairs the index. Full contract:
[`../architecture/20261120-search-api.md`](../architecture/20261120-search-api.md).

Query parameters:

| Parameter | Meaning |
|---|---|
| `q` | required; trimmed, 1..256 code points, literal all-term words (AND-ed; no FTS operators) |
| `type` | optional; `claim` or `evidence` |
| `publisher` | optional; exact indexed publisher key (evidence results only) |
| `status` | optional; claim verification-state label (claim results only) |
| `publishedFrom`, `publishedTo` | optional; UTC ISO-8601, start-inclusive / end-exclusive |
| `limit` | default 25, 1..100 |
| `offset` | default 0, 0..2,147,483,647 |

Response DTOs (`src/http/schemas.py`): `SearchResponseDTO` with `caseId`,
`query`, `total`, `limit`, `offset`, `appliedFilters` and `items[]` of
`SearchResultItemDTO` (`resultType`, `id`, `claimId`, `evidenceId`, `eventId`,
`captureId`, `title`, `snippet`, `matchedField`, `publisher`, `status`,
`publishedAt`). `snippet` is always plain text — never HTML. `eventId`,
`captureId`, `title`, `publisher`, `status` and `publishedAt` may be `null`.

Failure semantics:

| Condition | Status |
|---|---|
| unknown case | 404 |
| malformed query/filter/range (including `status` with `type=evidence`, `publisher` with an effective claim type, `offset` > 2,147,483,647) | 422 |
| search index capability unavailable (FTS5 absent, or `case_search_index` missing because migration 15 is not applied) | 503 |
| valid query with no matches | 200, `items: []`, real `total` |

The 503 detail names the operator remedy, for example:

```text
Case search is unavailable for case <case_id>: <capability reason> Operator remedy: run `triangulate case rebuild-search <case_id>` and retry.
```

There is no `LIKE` fallback and no GET-side repair; `triangulate case
rebuild-search <case_id>` is the only repair path.

### Investigation Runs and Deltas

```text
GET /api/cases/{case_id}/investigation-runs                        -> InvestigationRunListDTO
GET /api/cases/{case_id}/investigation-runs/{run_id}               -> InvestigationRunDetailDTO
GET /api/cases/{case_id}/investigation-runs/{run_id}/changes       -> RunChangesDTO
```

Grouped investigation invocations (R01), newest sequence first; `limit` 1..100
(default 25), `offset` ≥ 0. The `changes` route returns the stored delta for one
run (R03b) — pending/unavailable are distinct from empty. Unknown case or run →
404.

### Historical Artifacts (X02)

```text
GET /api/cases/{case_id}/investigation-runs/{run_id}/artifacts
  -> list[ArtifactDescriptorDTO]
GET /api/cases/{case_id}/investigation-runs/{run_id}/artifacts/{artifact_id}
  -> bytes (attachment)
```

Additive read-only reader over the report files a successfully finalized
`InvestigationRun` published (`src/cases/artifact_reader.py`). Ownership is
proved through the persisted join — `artifact.case_id == case_id`,
`stage_run.case_id == case_id`, `stage_run.investigation_run_id == run_id` (via
`artifact.stage_run_id`) — and only a `SUCCEEDED` run qualifies. `CaseArtifact`
has no direct grouped-run FK, so stage ids and grouped-run ids are never
conflated. Only `report_markdown`, `report_json` and `execution_manifest` are
eligible; temporary/unpublished stage attempts never are.

The list is a JSON array sorted by type then artifact ID. Each descriptor is
`{artifactId, type, displayName, downloadUrl, recordedChecksum, checksumKind}`:
`displayName` is the fixed published filename, `downloadUrl` is a relative API
URL, and **no filesystem path is ever exposed**. `recordedChecksum` is the
writer's canonical JSON **payload** checksum — not a checksum of the file bytes;
`checksumKind` is `payload_json` only when the stored payload re-hashes to the
recorded value and `unknown` otherwise. Listing is not a file-existence claim.
Unknown/wrong-case run → 404; an existing run without eligible published
reports (including a run that did not succeed) → `200 []`. There are at most
three types, so there is no paging. A missing, uninitialized or unreadable
configured database is a sanitized `503` (see
[Historical storage availability](#historical-storage-availability)), never a
store bootstrap or a fake `404`.

The download never accepts a client path and never falls back to an inline,
latest or nearby-run file. It resolves inside the approved run root
`output_root/cases/{case.slug}/runs/{run_id}` only, using the fixed per-type
filename; a recorded path with a `..` component, a filename other than the
fixed one, a recorded path that is not exactly this run's expected file, a
symlink component below the case directory, a wrong-owner artifact or missing
bytes is the **same uniform 404**
(`{"detail": "Artifact not found for this case and run"}`). The file is opened
once with `O_NOFOLLOW` and the descriptor `fstat` is taken from the same handle
that is read, so the checked file is the served file. Files above 50 MiB are
`413` with `{"detail": "too_large"}`; permission and OS failures are redacted
(no path or exception text in the body). Responses use `text/markdown` or
`application/json`, `X-Content-Type-Options: nosniff`, and
`Content-Disposition: attachment` with a constant filename plus percent-encoded
identifiers (no CRLF). Nothing is generated, repaired, published or fetched
remotely on a GET: the reader has no directory-creating helper, and a batch of
GETs leaves the output tree unchanged.

**Historical storage availability.** Every historical GET — the artifact list,
the artifact download and the ad-hoc snapshot comparison — reads the same
database the case routes use, selected **once at app startup**. Precedence is a
non-default `[database].path` in the runtime config, otherwise `DATABASE_PATH`,
otherwise `./triangulate.db`; relative values are resolved against the server's
startup working directory. These reads open the existing SQLite file in
read-only mode: a first request never creates a directory, database file,
table, index, migration marker or row, and never builds the case service or
syncs the taxonomy. If the configured file is missing, empty/uninitialized,
partially migrated or unreadable, the response is a sanitized
`503 {"detail": "Historical storage is unavailable"}` — never a bootstrap, a
fallback to another database or a misleading case-not-found `404`. On a usable
store, unknown resources keep their scoped `404` and malformed requests keep
their `422`s (request-schema validation and semantic validation are unchanged).
`GET /health` does not imply storage availability. Prepare the same configured
database explicitly with `uv run triangulate init-db` run from the server's
working directory (see
[CLI operations](cli-operations.md#6-database-selection-and-initialization-http-503-on-historical-gets)).
A read-only open intentionally does not change journal mode; a WAL-mode file
whose `-shm` sidecar cannot be created by the server account is unusable and
reports the same `503` rather than being forced open. No response body contains
a path, SQL text or driver error.

**Output root configuration.** The HTTP server reads one operator setting,
`TRIANGULATE_OUTPUT_ROOT`, captured once per app instance at startup; unset or
blank means the compatibility default `./output`. A relative value is resolved
against the server's startup working directory and compared lexically with the
writer's recorded path — the same directory may be published as a relative or
absolute path, as long as both resolve to the same location. There is no
`mkdir`, repair or write on this read path, and no request parameter, header or
artifact row can supply or override the root. If a legacy custom relative path
was recorded from a different working directory it cannot be attributed safely
and fails closed with the same uniform 404. There is no second knob and no
change to the writer's published layout or filenames; publish with
`--output <dir>` and start the server with that same directory in
`TRIANGULATE_OUTPUT_ROOT` (an absolute directory is the most robust).

### Snapshot Comparison (ad-hoc)

```text
GET /api/cases/{case_id}/snapshot-comparison?baseline=<snapshotId>&target=<snapshotId>&limit=25&offset=0
  -> SnapshotComparisonDTO
```

Ad-hoc comparison of **two immutable snapshots of one case** (F17 / X01). It is
an additive read-only reader, distinct from `RunChangesDTO`: the delta is
computed per request from the stored semantic projection
(`src/cases/snapshot_comparison.py`), is never stored, and does not reuse
`build_snapshot_delta` publication semantics (`src/cases/history.py`). Ordering
is strictly chronological by the owning `InvestigationRun.sequence` — not by
UUID and not by source publication time.

| Parameter | Meaning |
|---|---|
| `baseline` | required; the earlier immutable snapshot ID |
| `target` | required; the later immutable snapshot ID |
| `limit` | default 25, 1..100 |
| `offset` | default 0, 0..2,147,483,647 |

Failure semantics:

| Condition | Status |
|---|---|
| missing or empty `baseline`/`target` (request validation) | 422 |
| same baseline and target, or a reversed pair (by owning run sequence) | 422 |
| `limit`/`offset` out of range | 422 |
| an unrelated `snapshotId`/`snapshot_id` (a hidden third snapshot context) | 422 |
| unknown snapshot, unknown case, cross-case snapshot, or a snapshot whose owning run is not case-owned | 404 with one uniform body (`{"detail": "Snapshot comparison is not available for this case"}`) |
| configured database missing, uninitialized or unreadable | 503 `{"detail": "Historical storage is unavailable"}` (storage readiness is checked before query validation; see [Historical storage availability](#historical-storage-availability)) |

A supplied `snapshotId`/`snapshot_id` is tolerated only when it repeats
`baseline` or `target`; anything else (including conflicting values) is 422.
Because this reader's API names are `baseline`/`target`, the frontend's `snapshot`
selector for other historical readers is not forwarded to it.

Availability is decided **before** any delta is produced. An unsupported or
incompatible pair answers `200` with `availability: "unavailable"`, one of
`incompatible_schema | incompatible_identity | incompatible_policy |
unknown_version | payload_unreadable`, `items: []`, `total: null` and
`hasMore: false` — never an apparent zero-change result. `incompatible_*` means
the two snapshots record *different* schema/identity/policy versions;
`unknown_version` means they agree on a version this build does not support (or a
recorded version value is unreadable); `payload_unreadable` means a stored
payload is not a readable mapping for this case.

`SnapshotComparisonDTO` (`src/http/schemas.py`): `mode` (always `"ad_hoc"`),
`comparisonPolicyVersion`, `baselineSnapshotId`, `targetSnapshotId`,
`baselineRunId`, `targetRunId`, `baselineCoverage`, `targetCoverage`,
`baselineMetadata`, `targetMetadata`, `availability`, `unavailableReason`,
`items`, `total`, `limit`, `offset`, `hasMore`. Each metadata object contains
`sequence`, `createdAt` (snapshot-save time, not source-observation time),
`schemaVersion`, `identityVersion` and `policyVersion` (version values are
strings); coverage, times and run IDs are recorded independently per side.

Each item is `{entityType, entityId, changeKind, changedFields, before, after,
refs}`. `entityType` is one of the existing semantic projection groups (`case`,
`articles`, `events`, `claims`, `links`, `citations`, `evidence`, `captures`,
`reviews`, `exceptions`, `parties`, `partyInvestigations`, `narratives`), and the
case singleton uses the case ID. `changeKind` is `entity_added`,
`entity_absent` or `field_changed`. `before`/`after` are frozen semantic-field
objects (for `field_changed`, only the changed fields) — never live ORM rows or
capture bodies — and `changedFields` is sorted. `refs.baseline`/`refs.target`
each carry their own `snapshotId` plus only the `claimId`/`evidenceId`/
`captureId`/`citationId` values that side actually recorded (`null`
otherwise); no inspector link is fabricated, for example for an event that
carried no claim. Items are stably ordered by `entityType`, then `entityId`,
then `changeKind`; `total` counts entities, not changed fields.

`entity_absent` means the entity is absent from the later observation. It is not
a deletion, a retraction, or a "claim no longer extracted" verdict. A ready
response always carries an integer `total` (including `0`) and
`unavailableReason: null`; an offset past the end returns `200` with the true
total and an empty page. Nothing is composed, published, indexed or modelled:
the reader opens no writer path, and a batch leaves database, index and
migration state unchanged.

### Evaluation

```text
GET /api/cases/{case_id}/evaluation            -> EvaluationSummaryDTO
```

Read-only summary of stored evaluation runs. **`latest` is nullable**: a case
with no stored evaluation returns `200 {"latest": null, "history": []}` and
writes nothing (`src/cases/service.py`;
`tests/test_http_api.py:682-693`). Stored runs come back newest-first in
`history` (up to 10) with `latest` set. Evaluations are created only by the
explicit `triangulate case evaluate` command. Unknown case → 404.

### Monitoring

```text
GET /api/monitoring/summary                    -> MonitoringSummaryDTO
```

Aggregate operator-facing metrics (case counts, review backlog, pipeline,
intake, evaluation) across all cases (`src/http/app.py:641-646`).

### Report Downloads

```text
GET /api/cases/{case_id}/report/markdown       -> text/markdown file
GET /api/cases/{case_id}/report/manifest       -> application/json file or inline bundle
```

- `report/markdown` streams the case's Markdown report file; no stored report or
  missing file → 404 (`src/http/app.py:653-669`).
- `report/manifest` streams `latest_manifest_path` when present; otherwise falls
  back to the inline `report_bundle` object; neither → 404
  (`src/http/app.py:671-689`).

### Review mutation POSTs (the narrow exception)

These three routes are the deliberately narrow human-in-the-loop review surface
recorded in the [2026-11-22 specification
amendment](../plans/20261114-evidence-workbench-specification.md). They are the
only mutation routes in the API.

```text
POST /api/cases/{case_id}/review-actions/review                       -> CaseListItem
POST /api/cases/{case_id}/review-actions/exceptions/{exception_id}    -> CaseListItem
POST /api/cases/{case_id}/annotations                                -> ReviewAnnotationDTO
```

Request bodies (`src/http/schemas.py:225-288`); request models validate the
accepted vocabularies with field validators and trim free text:

| Route | Body |
|---|---|
| review | `{"decision": str, "notes": str?}` — allowed: `approve`, `reject`, `defer`, `action_required`, `exception` |
| exception | `{"action": "resolve"\|"defer"\|"reopen", "notes": str?}` |
| annotations | `{"targetType" (case/claim/evidence/exception/narrative), "targetId", "annotationType" (comment/flag/context), "content", "author"?="operator", "metadata"?={}}` |

Decision semantics: `approve`/`reject` set the case status and rewrite every
case event review decision; `action_required` (and the legacy `exception`
alias) reopens the case as review-ready and reopens its exceptions. `defer` is
a **case-level acknowledgement**, not a reopen: it stores only the case-level
`review_notes`/`last_reviewed_at`, so a `REVIEW_READY` case stays review-ready
and an `APPROVED`/`REJECTED`/monitoring case keeps its stored status, its
stage, its event review decisions and analysis bindings, and its exception
queue (statuses, timestamps, resolution notes) exactly as stored. It returns
200 with the unchanged case status. Exception-level `defer` (the exception
route) is a different action that marks one exception `deferred`.

Responses: the updated `CaseListItem` for review/exception routes; the created
`ReviewAnnotationDTO` for annotations.

Error behavior:

| Condition | Status |
|---|---|
| malformed/missing body fields, or an unsupported decision/action/type value | 422 (request validation) |
| active case writer holds the case (fencing) | 409 with a safe detail (`CaseWriterConflict` handler, `src/http/app.py:695-701`) |
| unknown case or exception ID | 404 |
| domain validation failure at the service (e.g. `approve` while exceptions are unresolved, blank content reaching the service) | 422 |
| annotation target missing **or** owned by another case | 422 with one uniform detail (`Annotation target is not part of case <id>`) so the response cannot reveal whether the target id exists |

The 404/422 mapping is scoped to these three handlers via
`_post_write_error` (`src/http/app.py`); the service re-checks the same
rules because CLI and direct callers bypass the request models.

**Annotation target ownership.** An annotation target must provably belong to
the case in the URL: `case` matches the case id, `claim` follows its event's
`case_id`, `evidence` uses the evidence row's own `case_id`, `exception` must be
in the case's stored exception queue, and `narrative` must be reachable through
the case-scoped claims overview association (`claim.narrativeClusterId ==
narrative.clusterId`; `Narrative` has no case column, so no narrative case
ownership is invented). Writer admission runs first, so a 409 writer conflict
still wins over this 422, and a rejected target writes no annotation and no
audit row. No identity is trusted from the `author` string.

Annotation content is stored as plain text and rendered as text; nothing here
executes or imports case material.

## Schema Source

The request and response DTOs are defined in `src/http/schemas.py`. The frontend
TypeScript models live in `frontend/src/types/backend-models.ts`.

## Consumption Pattern

The React client calls these endpoints through `frontend/src/services/api.ts`
and reads the base URL from `VITE_API_BASE_URL`. Use the CLI or background
operators to create cases, rerun stages, ingest material, or execute the
pipeline; the website covers inspection plus the three review POSTs above.
