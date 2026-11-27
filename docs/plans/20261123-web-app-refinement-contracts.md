# Web-app refinement technical contracts (2026-11-23)

Status: **PROPOSED** shared contracts for all 22 refinement tasks. Not an approval; nothing here is
implemented. Task cards reference this document as "the contracts doc". Product behaviour lives in
the [specification](20261123-web-app-refinement-specification.md); task DAG and coverage live in the
[implementation hub](20261123-web-app-refinement-implementation.md).

## 1. Scope, safety and verification contract

- One application code worker (`deepseek-v4.1-flash`) per dispatched task; no subagent recursion or
  auto-workflows; read-only independent review, then parent-run actual gates per ticket. Preserve all
  existing dirty worktree files. No commits or pushes without instruction.
- **All backend verification runs in a disposable copy of the current worktree** — export code and
  manifests including dirty bytes, not `git archive HEAD` alone — with scratch config/DB/output,
  paid providers mocked and external IO disabled. `tests/conftest.py` guards are not sufficient
  protection for import-time, subprocess or raw-SQLite access; the disposable copy is.
- Never touch the original repository/live `data/`, `triangulate.db`, `.env`, `logs/`, `config.toml`,
  scratch archives or unknown running servers. Explicitly created synthetic DB/config/output files
  under the disposable test root are permitted; they must not resolve to the original paths. Never repair historical data or case ownership (that is D01, a separate owner gate).
- Commands: `uv run` for Python; `uv run pytest -q --disable-warnings` and
  `uv run ruff check src tests scripts --output-format concise` in the disposable copy;
  `npm run check` and `npm test -- --run` after frontend changes (`frontend/package.json:15,17`);
  focused tests first, then full relevant gates. Node/npm versions from `frontend/.nvmrc` and the
  current package — no arbitrary upgrades. Fresh `npm ci` in an isolated copy at F00/F16.
- Browser verification: playwright-cli skill, isolated headless session, synthetic API or DB (never a
  production default backend), close your own server/browser. Core journeys on Chromium + Firefox +
  WebKit where available; a missing engine is recorded as **not proven**, never PASS; the owner may
  record a scoped defer but not certify.
- Write surface: API calls are read-only except the three narrow intentional POST families (review,
  exceptions, annotations) already present. CLI write surface: case creation/ingest/rerun/rebuild/
  recovery only. Nothing here authorizes public deployment, auth/RBAC, server jobs, new POSTs, OCR,
  vector search, notifications, bundle ZIP/PDF, export-content rights or production data repair.
  A proposed read-only API approval ≠ production repair/deploy approval.

## 2. Presentation and accessibility contract

- Shared recipes use **existing** Card/Button/Badge/status components and existing CSS/design-system
  tokens; React Query v5 patterns already in the app (`@tanstack/react-query`,
  `frontend/package.json:22`). No new query framework, universal state registry, theme or
  dependency upgrades. A new focused component/helper is allowed only where a feature cannot fit an
  existing boundary.
- Breakpoints: ≥1024 px navigation rail; 768–1023 px top bar; below 768 px stacked layout. Verify
  against wireframe viewports 375×812, 768×1024, 1280×800 plus 200 % zoom, keyboard/focus traversal,
  status conveyed by text not colour alone, and no unintended document-level horizontal overflow
  (real apps scroll; SVG continuation frames are not app steps). Wireframe red annotations and the
  8-grid are drawing style — never production CSS. No production red callouts.
- Screen-reader labels and live updates (polls) must not steal focus or disrupt typing.
- Grouped case navigation uses grouped native links with `aria-current`; do not use ARIA tab roles
  unless the full tab keyboard pattern is implemented.

## 3. Client state, paging and URL contract

- Client list paging/sort operates on **loaded arrays only** and labels its scope ("loaded results");
  no claim that server pagination was added. Bound rendered rows (e.g. 50/page). Server search
  pagination is unchanged: 25 default / 100 max page size, offset cap 2³¹−1.
- Stable entity/selection IDs across re-renders. Filters in URLs use per-view allowlists only; no raw
  captured text in URLs. Unknown/unsupported URL params are dropped, never blindly carried.
- Last committed per-view href may be session memory per case; Back/reload restore stable committed
  URLs; explicit cross-links choose context; "Clear" is explicit.
- Historical-selector conflicts are not ordinary unknown parameters. A current-only view opened with
  `snapshot` must show an unsupported-history state before fetching (or surface 422), not silently
  discard the selector and display current data. Only an explicit "Open current" action removes it.
- Browser-only browse additions are proposed below; never forward them as unsupported API filters.
  Defaults are omitted, filter/sort changes reset the local page, and ties use stable entity ID.

| View | Allowed local browse keys | Semantics |
| --- | --- | --- |
| Claims | `claimQuery`, `claimStatus`, `claimSort`, `claimPage` | Query is a case-insensitive substring of loaded claim text; status uses the existing enum; sort is `text` or `status`; page is a positive integer, 50 loaded rows/page |
| Evidence | `publisher`, `sourceType`, `credibilityTier`, `hasCapture`, `evidenceSort`, `evidencePage` | Values use recorded DTO metadata; `hasCapture` is `yes`/`no`; sort is `title` or `publishedAt`; unknown dates sort last; page is a positive integer, 50 loaded rows/page |
| Search | Existing `SEARCH_PARAMS` only | Current case-scoped server search and its existing filter/pagination contract; no new historical scope |

Existing inspector selection keys may coexist with browse keys on their owning view. Explicit
invalid values produce a field message and a clear-filter action; they do not silently broaden the
result set. A saved publisher/tier absent from a later dataset stays visible as an applied filter
with zero matches, rather than being silently removed.

## 4. Compare tray contract

- Session-only, case-scoped temporary memory (existing state; no new store). Cap: exactly 2
  **distinct** evidence sources plus pins within one context. A third selection is **explicitly
  rejected** — never silently replaced. Commit uses the existing `buildComparisonUrl`
  (`frontend/src/services/deep-links.ts:205`); after server-side default-capture resolution the URL is
  replaced with pinned capture IDs. Changing case or historical context clears the draft after an
  explicit notice. No auto-replacement, no cross-context mixing.

## 5. Local saved views contract (localStorage v1)

- Storage namespace `triangulate.savedViews`; payload `schemaVersion: 1`. Limits: per-origin total
  ≤ 50 views, per-case ≤ 10, names 1–80 codepoints,
  total serialized ≤ 64 KiB. Explicit user "Save" only — no autosave, no history tracking.
- Stored payload allowlist: filter/sort/view metadata, case id only. Free-text query values (search
  `q` and claim `claimQuery`) are **excluded by default**. Including either requires
  `includeQuery: true` with a separate explicit warning + consent; the query is 1–256 codepoints. **Never** store captures, notes, review drafts, author identity, full
  URLs, credentials or arbitrary JSON.
- Validate everything read back (shape, lengths, version). Unknown version or corrupt data is handled
  without a crash (visible fallback; invalid entries are excluded in memory). Do not overwrite an
  unsupported version or delete stored data without an explicit reset. No server writes, sync,
  import or export features. Deleting: one view / all for a case / all feature-owned views; never
  call `localStorage.clear()` or remove another feature's keys. Quota-exceeded or private-mode
  failure produces a visible ephemeral fallback (session-only view), never a silent loss.
- Privacy: case ids and query terms can be sensitive. "Local" does not mean "private". No identity,
  confidentiality or encryption claims in UI or docs.

Proposed stored shape (example values are synthetic):

```json
{
  "schemaVersion": 1,
  "views": [
    {
      "id": "view-example-1",
      "caseId": "case-example",
      "name": "Evidence by publisher",
      "view": "evidence",
      "filters": {"publisher": "Example Publisher", "hasCapture": "yes"},
      "sort": "publishedAt",
      "includeQuery": false
    }
  ]
}
```

`view` is `claims`, `evidence` or `search`; filters/sort use only that view's allowlist above.
Pagination and selected entity/capture/citation/snapshot IDs are not saved. IDs are locally generated,
not identities. Only a consented search view may contain top-level `q`; only a consented claims view may contain
`filters.claimQuery`. `includeQuery: false` requires both query fields to be absent. Evidence views
cannot store either. Save/apply/manage controls live in each of the three existing filter bars,
sharing a focused helper rather than a new state platform. Store no arbitrary metadata or URL blobs. Re-read and merge validated
feature-owned entries before Save; a `storage` event refreshes the list in another tab without
applying a view or resetting an active form. This is not a transactional collaboration store.

## 6. Review mutation contract

- `retry: false` on all review/exception/annotation POSTs. Pending disables only the same write
  form/row. Notes and case-keyed context are preserved through errors and background refreshes.
- Ambiguous transport outcome (unknown whether the write landed): reconcile with GET before allowing
  an explicitly confirmed manual retry; never blindly auto-repeat a POST. Refresh alone cannot prove
  whether this submission landed when the API provides no idempotency/correlation guarantee. Warn
  that repeating an annotation may append a duplicate; never infer success by matching text/time.
  Saved-and-refreshed state requires server ack **and** read refresh. If POST succeeds but refresh
  fails, show "Accepted; refresh failed" and offer GET-only refresh recovery, not resubmission or
  "Not saved". Keep the draft until its outcome is reconciled. No fake Undo. No new claim-specific
  supports/contradicts review verbs.
- A late submit response from Case A must never alter a Case B form (case-keyed guards).
- Staleness wording: the server has **no** expected-revision/CAS today. The UI may say "recorded
  invalidation or detected refresh"; it must never claim atomic proof that the operator reviewed the
  current revision. Full revision preconditions are a future, separately designed task — out of scope.

## 7. Query keys, polling and cache contract

- Query keys include every case/entity/capture/snapshot/filter/paging selector that affects the
  result. `enabled` only with valid IDs. Late responses for a superseded case/selection are cancelled
  or ignored. Invalidation uses the existing keys — no `['case-detail']` vs `['caseDetail']` duplicate
  caches.
- Poll only visible, active, recorded surfaces; label "Last fetched" vs "Last observed"; pause when
  hidden using existing query capabilities; drafts never vanish on refetch. `/health` is process
  liveness only and is not a readiness signal.

## 8. Performance budgets (proposed — not benchmarks, not current SLOs)

No per-case fan-out (no N+1 caseDetail expansion, no new dashboard endpoint). Bounded rendered rows
(e.g. 50/page). Search backend unchanged (25/100/offset cap above). The reproducible fixture latency
record keeps its warm-search p95 500 ms target **definition**; do not present it as a measured
current-load SLO. No hardware-dependent pytest asserts. Capture windows 20k default / 50k max.

## 9. Data model and validation contract (F05 — case-owned annotation targets)

Verified schema facts (`src/storage/models.py`):

- `Claim.event_id` is a FK to `Event.id` (`:209`); `Event.case_id` carries case ownership (`:192`).
  Claim membership therefore follows its event's case.
- `Claim.narrative_cluster_id` (`:212`) is a **plain column with no FK**; it matches
  `Narrative.cluster_id` (`:235`, unique). `Narrative.id` is the annotation target and `Narrative`
  has **no `case_id`** — never invent `narrative.case_id`. Narrative membership is established by
  reachable case association, i.e. the case-scoped claims overview where
  `claim.narrativeClusterId == narrative.clusterId`.

Behaviour contract:

- `add_review_annotation` (`src/cases/service.py:4154`) gains case-scoped membership checks for
  target types `case`, `claim`, `evidence`, `exception`, `narrative`: the target must belong to
  `case_id` (claim via `Event.case_id`; narrative via the cluster association above). Inspect existing
  readers before changing them; if membership cannot be proven, reject with the **uniform 422**. No
  history rewrites, no backfill.
- Missing case → 404. Missing or wrong-case target → the same uniform 422 (prevents an existence
  leak). Validation runs **after** writer admission so 409 writer-conflict precedence is preserved.
- No identity is trusted from the author string. No update/delete endpoints. No immutability or
  tamper-proof audit claims. Review activity GET (already existing: case-wide annotations + audit
  arrays, no pagination — `get_case_review_activity`, `src/cases/service.py:4099`) is not extended;
  do not invent a current-annotation GET.
- Each annotation already mirrors an `annotation:*` audit entry. The UI partitions/labels technical
  audit entries vs human notes; it must never render one annotation as two human comments nor guess
  dedup by text/time.
- F05 also maps review-activity/evaluation missing-case errors to a deliberate HTTP **404** (today
  their service `ValueError` is unmapped at the route). The existing direct-service regression
  `tests/test_http_api.py:727` asserts `ValueError`, not HTTP 500: preserve it and direct/CLI caller
  compatibility. Add HTTP-route 404 tests and update the documented HTTP contract. Map only missing
  case failures; genuine evaluation/activity read failures must not be disguised as 404.
  Evaluation reader semantics stay: `latest: null` valid ("No saved evaluation"), errors distinct,
  score 0 shown as 0, GET never creates an evaluation.
- No new core DB schema. F05 is constrained behaviour correction only; additive/new APIs are OPTIONAL
  and separately approved. Do not mistake D01 (historical DATA repair) for feature approval.

## 10. Historical text, citation and provenance semantics

- Capture/citation text offsets are Unicode **codepoint** offsets: Python slice semantics server-side,
  `Array.from` in the browser. Normalization is LF-only, server-side — never NFKC/casefold for
  highlight matching. Exact quotation is not verification. Copies are not independent corroboration.
  Absent dependency information stays "unknown" (not "none"). Model consensus is not truth. Legacy
  unknown values stay unknown.
- Claim/evidence/comparison readers accept a snapshot selector and show frozen context read-only.
  Citation GET is independently frozen by citation ID and rejects snapshot selectors, as does
  capture-window GET; do not blindly forward the browser's `snapshot` key to either request.
  "Open current ⟨view⟩" is an explicit transition that strips historical selectors. Current-only
  readers reject snapshot selectors with 422. No historical lexical/global/vector search.

## 11. Report and artifact provenance contract

- `CaseArtifact` has `case_id` and `stage_run_id` (`src/storage/models.py:463,469–470`) — **no direct
  `investigation_run_id`**. `CaseStageRun.investigation_run_id` (`:457`) bridges a stage run to its
  grouped `InvestigationRun` (`:337`). `Event.case_run_id` (`:193`) is the stage-attempt FK. Never
  conflate stage IDs and grouped-run IDs in APIs or UI.
- `TopicCaseService._publish_successful_run` (`src/cases/service.py:3156+`) saves
  `report_json → topic_analysis.json`, `report_markdown → topic_report.md`,
  `execution_manifest → manifest.json`. The stored checksum is the **canonical payload checksum**
  (`_payload_checksum`, `src/cases/service.py:267`) — it is NOT a verified file-bytes checksum and
  must never be labelled as one.

## 12. X01 — PROPOSED snapshot-comparison read API (does not exist today)

```text
GET /api/cases/{case_id}/snapshot-comparison?baseline=<snapshotId>&target=<snapshotId>&limit=25&offset=0
```

- Both params required; same case; explicit immutable snapshot ids; strictly chronological —
  baseline before target; same or reversed → 422. Unknown snapshot or wrong case → uniform 404.
  Order is by the owning `InvestigationRun.sequence`, not UUID or source publication time.
  `limit` 1–100, `offset` 0–2147483647. Reject unrelated `snapshotId`/`snapshot_id` selectors with
  422 rather than allowing a hidden third snapshot context.
- Snapshots must be schema/identity/policy-version compatible **and** supported; otherwise 200 with
  `availability: "unavailable"` plus
  `unavailableReason ∈ {incompatible_schema, incompatible_identity, incompatible_policy, unknown_version, payload_unreadable}`
  and **no** empty "ready" delta. Baseline/target coverage, times and run IDs are recorded
  independently.
- DTO `mode: "ad_hoc"` — distinct from `RunChangesDTO` (recorded run changes). Fields:
  `comparisonPolicyVersion`, `baselineSnapshotId`, `targetSnapshotId`, `baselineRunId`, `targetRunId`,
  `baselineCoverage`, `targetCoverage`, `baselineMetadata`, `targetMetadata`, `availability`,
  `unavailableReason`, `items`, `total`, `limit`, `offset`, `hasMore`. Each metadata object contains
  `sequence`, `createdAt` (snapshot-save time, not source-observation time), `schemaVersion`,
  `identityVersion` and `policyVersion` (version values are strings). Items are stably ordered by
  entityType/entityId/changeKind with `changeKind ∈ {entity_added, entity_absent, field_changed}`,
  before/after/frozen refs and sorted changed-field lists. "Absent from a later observation" is not deletion, retraction or
  "claim no longer extracted". No fabricated `observedByRun`/causal actor. No new baseline, snapshot,
  report, index or model calls/writes; raw DB/index/migration dumps must be unchanged after a batch.
- Proposed item schema: `{entityType, entityId, changeKind, changedFields, before, after, refs}`.
  `entityType` uses the existing semantic projection groups (`case`, `articles`, `events`, `claims`,
  `links`, `citations`, `evidence`, `captures`, `reviews`, `exceptions`, `parties`,
  `partyInvestigations`, `narratives`). The case singleton uses the case ID. Each item represents
  one entity; `before`/`after` are nullable semantic-field objects, not live ORM rows or full capture
  bodies. `refs.baseline` and `refs.target` carry their own snapshot ID and only recorded, applicable
  claim/evidence/capture/citation IDs. No fabricated inspector link for an event without a claim.
  `total` counts entities, not changed fields. Ready responses use an integer total (including 0),
  `unavailableReason: null`, and ordinary paging; unsupported responses use `items: []`,
  `total: null`, `hasMore: false` and a reason — never an apparent zero-change result. Offset beyond
  a ready result returns 200 with the true total and an empty page.
- Reuse `src/cases/history.py` `semantic_view` (:500), `get_case_snapshot` (:922),
  `snapshot_payload` (:935), `snapshot_entities` (:941) **after compatibility checks**.
  `build_snapshot_delta` (:646) is publication semantics (stamps `observedByRunId`, requires
  authoritative event ids for removals) — **do not call it unmodified** to manufacture an ad-hoc
  delta. Use a focused new reader (proposed NEW `src/cases/snapshot_comparison.py`) reusing the
  semantic projection, not the whole writer. The current recorded-run `/changes` surface is never
  altered.
- UI: rides the existing Changes route via `mode=ad_hoc&baselineSnapshot=&targetSnapshot=` — a new
  **browser** allowlist entry, explicit. API query names are `baseline`/`target`. Source-article
  comparison remains Compare. Historical search remains unsupported. Feature is behind an explicit
  owner decision; it is not D01-dependent.

## 13. X02 — PROPOSED historical artifact read API (does not exist today)

```text
GET /api/cases/{case_id}/investigation-runs/{run_id}/artifacts
GET /api/cases/{case_id}/investigation-runs/{run_id}/artifacts/{artifact_id}
```

- Prove `run.case_id == artifact.case_id == stage_run.case_id == case_id` and
  `stage_run.investigation_run_id == run_id`; join through `artifact.stage_run_id`. Do **not** assume
  a direct `CaseArtifact`→grouped-run FK. Only successfully published grouped-run reports qualify;
  temporary/unpublished artifacts do not. Allowed types: `report_markdown`, `report_json`,
  `execution_manifest`.
- List returns a JSON array of descriptors sorted by type and artifact ID. Descriptor fields are
  `artifactId`, `type`, `displayName`, `downloadUrl` (relative API URL), `recordedChecksum` (nullable)
  and `checksumKind ∈ {payload_json, unknown}` — never a filesystem path; the stored checksum is not
  raw file proof. There are at most three published report types, so no paging is introduced.
  Unknown/wrong-case run → 404; an existing run without eligible published reports → 200 `[]`.
  This is not a file-existence claim: bytes are checked when downloading. Missing paths/bytes or a
  wrong-case/wrong-run artifact → uniform 404; no inline/latest fallback, ever.
- Example descriptor (synthetic):

  ```json
  {"artifactId":"artifact-example","type":"report_markdown","displayName":"topic_report.md","downloadUrl":"/api/cases/case-example/investigation-runs/run-example/artifacts/artifact-example","recordedChecksum":null,"checksumKind":"unknown"}
  ```
- Download safety: no client path input. Resolve within the approved case output/run root containment
  and reject traversal, symlink components, escapes, wrong-owner and temporary unpublished artifacts;
  fixed allowlisted filenames per type; max 50 MiB (413 `too_large`); `Content-Disposition: attachment`
  with safe constants and encoded identifiers, no CRLF; correct `text/markdown` /
  `application/json` mime; `X-Content-Type-Options: nosniff`. Verify the **opened file handle** is the
  same file that was checked (guard the check-then-follow race). No HTTP/S3/remote-fetch paths.
- Optional historical artifact readers must implement **pure path resolution only** — they must NOT
  reuse any writer directory helper that creates or writes directories/files (the writer creates
  directories at `src/cases/service.py:3091` and `:3218`; those helpers are off-limits to readers).
- Never generate, repair, create reports or publish unreferenced files on GET. No legal chain-of-custody
  promise. No migration needed (`CaseArtifact` + `CaseStageRun` suffice). Tests cover: missing file,
  wrong case/wrong run, symlinks/path escape, oversize, permission failure, GET-makes-no-writes, and
  source-error body redaction.
- UI: Report shows current by default; an optional run pin shows the frozen run and its artifact
  descriptors; "current" is an explicit link; no plausible "latest" substitution.

## 14. F17/F19/F21 approval structure

F17 (X01 API) and F19 (X02 API) are independent and start only after the core gate (F16), each with
separate owner approval. F21 covers the full optional bundle (both tracks). If the owner chooses only
one track, run that track's required tests and record F21 as **not full-bundle accepted**.
