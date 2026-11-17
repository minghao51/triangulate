# Evidence workbench: product and implementation specification

Date: 2026-11-14. Version: 0.1. Status: **defaults approved by the owner on 2026-11-14; sequential implementation authorized, beginning with B00**. Production deployment, historical-data recovery and cleanup remain separate approval gates.

Related: [roadmap/comparison](20261114-product-enhancement-roadmap.md), [audit](../reference/20261114-setup-and-maintenance-audit.md), [current architecture](../architecture/20261114-current-architecture.md), [worker execution plan](20261114-evidence-workbench-worker-plan.md).

## 1. Objective and release boundaries

Enable an analyst to answer: **What was asserted, where was it asserted, which sources are dependent, how do accounts differ, and what changed?**

Deliver five capabilities incrementally:

1. Claim → quotation → captured source inspector.
2. Side-by-side source comparison.
3. Transparent source provenance/dependency grouping.
4. Changes between saved investigation observations.
5. Full-text case search and stable links.

**Default architectural decisions proposed for approval:** Python/SQLite remain; FastAPI and browser remain read-only; all ingestion/analysis/index writes run through CLI/service code; first release is local/trusted and single-writer. No new mutation endpoints, autonomous public web input, vector database, separate queue service or general chatbot.

**Release A:** setup/reliability prerequisites plus the evidence inspector. **Release B:** dependency grouping and comparison. **Release C:** durable run changes and case search. Each release needs its own verified handoff; approval of a design is not approval to deploy against the historical database.

Not in this specification: production database repair, deletion/archival of existing files, account/RBAC infrastructure, browser review editing, immutable human audit history, notifications, OCR, multimedia verification, broad OSINT imports, semantic claim merging or automatic truth certification. These remain separate proposals.

## 2. Non-negotiable invariants

- Preserve `triangulate.db`, `data/`, logs, raw artifacts and all existing scratch helpers. Workers use temporary databases and synthetic fixtures. Existing split-table/orphan data is not a migration fixture to repair automatically.
- Capture is not verification. Quotation presence is not proof of entailment. A publication's reputation is not a claim truth score. Two domains are not proof of two independent sources.
- Every highlighted quotation resolves to immutable stored text and an exact validated range. Never manufacture a quotation or silently use the latest version of a page for an old claim.
- Failed, fallback, incomplete and legacy analysis remain visible as such. Missing data is not zero, no result is not failure, and failed retrieval is not successful empty retrieval.
- No GET handler triggers analysis, recapture, snapshot creation, index rebuilding or recovery. Existing startup schema initialization is documented separately; introducing these features must not add new GET-side domain mutations.
- No HTML from captured pages or search results is injected into the DOM. Render text/React nodes; source links accept only HTTP(S), with `noopener noreferrer` for new tabs.
- Current API field meanings and IDs remain compatible. In particular, `ClaimEvidenceLinkDTO.id` currently identifies evidence, not the link; add `linkId`/`evidenceId`, do not reinterpret `id`. `Event.case_run_id` currently references a stage run, not a whole investigation.
- Do not refactor the entire 2,000-line case service. New focused helpers may isolate capture/alignment, provenance, snapshots and search; existing service remains the orchestration boundary.

## 3. Prerequisites and promotion gates

Before feature work is accepted:

1. Repair frontend test/coverage peers and lockfile; prove fresh `npm ci` without `--force` or `--legacy-peer-deps`. Select supported matching versions after current advisory review, not an arbitrary broad upgrade.
2. Make event persistence fail closed. For case-stage batches, support a caller-owned event-store session so one failed event rolls back that investigation-stage batch; preserve standalone store behavior. Do not claim the entire multi-stage case is transactional.
3. Preserve per-source acquisition outcomes: `success_with_items`, `success_empty`, `failed`, `skipped`. All attempted sources failing must not advance a successful checkpoint. Partial success is explicitly partial.
4. Remove synthetic production alerts/logs/health/analytical scores; show measured data or unavailable/empty states. Fix query-error handling, missing button CSS and keyboard/label basics without redesigning the UI.
5. Add small deterministic two-source case fixtures, including a duplicate, a contradiction example, invalid/missing quotation, non-ASCII text, a changed capture, and an unavailable source. Tests do not call paid/live LLMs or feed endpoints.

The existing 116 Python / 13 frontend passing tests are an audit baseline, not a frozen required count. New behavior needs new tests. Normal frontend installation was broken at audit time; isolated workaround results do not meet gate 1.

Production promotion additionally requires a separately approved backup/reconciliation exercise and deployment/security review. Development on valid temporary databases may proceed without repairing production data.

## 4. Capability E1 — Claim-to-source inspector

### User interaction

From a claim, “Inspect evidence” opens its linked source records. Selecting a source opens captured text with a validated quotation highlighted and surrounding context. Show claim text, relationship, alignment state, evidence/capture IDs, title, publisher, original/canonical URLs, publication time if known, observation/recording times, content hash, extraction scope and analysis provenance. Missing content/quotation gives an explanatory state, not a fake highlight.

Use the existing claim/evidence tabs and URL query parameters before adding a new top-level page. Selection must survive reload/back/forward, work by keyboard and place focus on the selected inspector heading. Loading, 404, network error/retry and empty states are distinct.

### Immutable capture model — proposed new `EvidenceCapture`

Keep `EvidenceItem` as the logical source record and its current compatibility projection. Add:

| Field | Contract |
|---|---|
| `id`, `evidence_id` | Stable capture ID and owning evidence FK |
| `text`, `text_sha256` | Exact UTF-8 stored extraction after CRLF/CR → LF normalization only; SHA-256 over that text |
| `normalized_text_sha256`, `normalization_version` | Separate dependency-detection fingerprint; never used for quotation offsets |
| `recorded_at` | Actual persistence timestamp |
| `observed_at` | Actual fetch/observation time if known; null for unknown legacy history |
| `capture_kind` | `live` or `legacy_snapshot`; do not label imported old text as newly fetched |
| `metadata_json` | Frozen URLs/title/publisher/source type/publication metadata, extraction method/scope, model/prompt metadata when known, and origin stage/run IDs when available |

Unique `(evidence_id, text_sha256)`; identical text reuses a version. Capture text/metadata are append-only. Reobservations are recorded by run/intake metadata, not by overwriting the capture's first observation time. Add nullable `EvidenceItem.current_capture_id`; create evidence, flush capture, then set the pointer within the same transaction. Compare explicit capture IDs to inspect older versions.

Legacy `EvidenceItem.content` can be copied by an explicit offline materialization operation on an approved database, marked `legacy_snapshot` with unknown observation time. Schema migration itself does not invent capture history or validate legacy links. Read handlers do not perform this materialization. No old table or content is removed.

### Quotation and relationship contract

Extend collector structured output with optional `source_quote` and optional proposed offsets. Default remains compatible with old mocked/provider payloads. The quotation must refer to the article **body supplied to the collector**, not a generated summary or title. Record the current input prefix/truncation limit; do not claim the collector examined the entire capture when it only saw a prefix.

Extend each current `ClaimEvidenceLink` with nullable `capture_id`, `citation_id`, `quote`, `start_char`, `end_char`, plus `alignment_status`, `assessment_origin`, `assessment_version`, and assessment metadata. One passage per current claim/evidence link is sufficient for v1; multiple passages are deferred.

**Release A citation retention:** add append-only `ClaimCitation` records for validated passages. Each freezes its case ID, capture FK, original claim ID/signature/text, relationship, quote/range, alignment/assessment version and origin metadata. Its historical claim ID is a value, **not a deleting FK to mutable `Claim`**. Use a deterministic ID over the frozen claim/capture/assessment content; identical output reuses the record, changed assessments create another. Current links point to a citation, but replacing/deleting a live claim/link must not delete the citation or capture. Invalid proposals remain diagnostics on the current link and do not create validated citations. A direct citation GET and `citation` deep-link parameter resolve frozen claim text/relationship and capture even if the live claim no longer exists. This guarantee does not depend on Release C snapshots.

- Offsets are zero-based Unicode code-point indices, end-exclusive, against the capture's stored text. Python string slicing is the reference. Browser highlighting uses code points (`Array.from` or equivalent), not raw UTF-16 slicing. Check bounds and exact slice equality.
- If valid provided offsets match the exact quotation, accept. Otherwise resolve a unique exact occurrence within the recorded analysis scope. Repeated matches without valid disambiguating offsets → `ambiguous`; missing text → `source_unavailable`; no quote → `not_provided`; no match/out-of-scope → `no_match`; only a validated result is `exact`.
- No fuzzy matching, synthesized ellipses, casefold matching or LLM-generated offsets can bypass this check. Preserve diagnostic quote proposals separately; invalid proposals never become validated spans.
- Effective relationship vocabulary: `reported_by`, `supports`, `contradicts`, `uncertain`. Map legacy `opposes` to `contradicts` when reading old data.
- Generated collector links have exactly two effective states: `alignment_status=exact` → **`reported_by`**; every other alignment state → **`uncertain`**. The collector never generates `supports`/`contradicts`, and an aligned quotation never certifies a claim. Existing blanket `supports` links without assessment/quotation provenance are exposed as `uncertain`/legacy-unvalidated, preserving their original stored value for diagnostics.
- `supports`/`contradicts` require an explicit assessment, version/origin metadata and exact passage, not extraction confidence. This release defines/preserves those inputs if supplied by a service caller, but does not add a second automatic verifier, claim-level review UI or new human approval workflow. Model assessments must be labeled model-assessed, not reviewer-confirmed.
- Fix `_recompute_case_claim_aggregates`: explicitly count only eligible support/contradiction links; never treat every non-`opposes` relation as support. Deduplicate repeated link contributions. `reported_by`, uncertain, invalid and unanchored links do not increment support/opposition.
- Preserve existing verification enum compatibility, but expose its provenance (`model`, `legacy_unknown`, etc.) and label it separately from source alignment. Do not automatically promote a claim to confirmed from quotation matches or source counts. When assessment origin is unknown, say so.

### E1 acceptance

An exact real quotation highlights correctly, including emoji/CJK and repeated-quotation cases. Changed source content creates another capture and leaves the old citation valid. Fabricated/out-of-scope quotations cannot become support. No-key/fallback extraction is not upgraded to validated analysis. Identical reruns preserve IDs/captures and do not reset a valid human review merely due to a row rewrite; meaningful changed analysis invalidates the current approval explicitly while retaining the prior decision in snapshot/history where available. A valid event with no claims still retains its captured source record.

## 5. Capability E2 — Source provenance and dependency grouping

Provide **observed publisher counts and dependency groups**, not an “independent truth score”. No left/right guessing from publisher names.

- Canonicalize HTTP(S) source identity locally: lowercase/IDNA host, remove fragment/default port, normalize empty path to `/`, and remove only a documented allowlist of tracking parameters (`utm_*`, `fbclid`, `gclid`). Preserve other query values, path case and trailing slashes. Do not equate HTTP with HTTPS or follow URLs while reading. Preserve original URL. Canonicalization does not rewrite existing IDs or destructively merge evidence.
- `publisher_key` comes from explicit configured identity/alias metadata when available; otherwise normalized host is provisional. Do not infer ownership or common editorial control from string similarity. Unknown source identity stays unknown.
- Detect deterministic dependence from identical canonical URLs, the same known publisher identity, sufficiently long identical normalized captured text, or a documented common origin. Text fingerprint v1 collapses whitespace after NFKC+casefold; require at least 200 non-whitespace code points before using it as copy evidence. Small shared snippets must not merge sources.
- Dependency groups are connected components of those explicit edges, with method/reason and policy version. Sort inputs/outputs deterministically. Do not assert that no detected dependency proves independence.
- Expose `distinctPublisherCount`, `dependencyGroupCount`, `unknownPublisherCount`, `independenceStatus` (`unknown` or `dependency_detected`) and per-group evidence/capture membership and reasons. Do not manufacture a positive verified-independent state.
- Keep document-copy dependencies separate from publisher identity. For a claim signature, compute grouping on that claim's relevant evidence, adding same-publisher edges there; a copy relationship about a different claim must not imply dependence for all reporting by those publishers. Case-level summaries show the underlying document dependencies and publisher counts separately. Repeated relevant wire copies count once for observed source-group breadth; they still remain separately inspectable records.
- Exact text detection and documented origins are v1. Near-duplicate/semantic syndication detection is explicitly deferred; disclose that coverage limitation.

**Acceptance:** same publisher/URL/body copies do not inflate breadth; short snippets do not collapse unrelated sources; two unrelated domains remain independence-unknown; grouping is stable under input reordering. Case-level and claim-level summaries use the same policy. Existing diversity fields remain documented compatibility fields, not independently verified-source counts.

## 6. Capability E3 — Side-by-side comparison

Select two evidence records/captures in the same case, choose “Compare”, and render two source panels plus a claim alignment table. Expose this view through the case navigation rather than requiring a hand-entered route. Stack panels on small screens.

- Pair claims by the existing exact `claim_signature` policy (currently SHA-256 of lowercased, stripped claim text). Do not change that identity algorithm or silently merge paraphrases in v1.
- Rows: reported in both extractions; extracted only on left; extracted only on right; explicitly assessed contradiction when an actual validated relationship says so. “Not extracted on the other side” does **not** mean the source omitted it, lied, or disagreed.
- Every side links to its own captured passage with extraction/coverage caveats. Show dependency/copy warnings from E2 and publication/capture times.
- The comparison is deterministic read-model work; opening the page makes no model/network/source-capture call. Sparse/manual sources and invalid alignments remain visible with unknowns.
- Inputs must be different evidence IDs; both evidence IDs and selected capture versions must belong to the requested case/evidence. Do not guess a capture when an explicit invalid ID was requested.

**Acceptance:** two known reports can be compared after reload; default selected capture IDs are returned so the UI can pin the URL; original source links are safe; exact shared assertions and unpaired extractions are correct; copying does not look like corroboration. Old captured text remains inspectable after refresh. Until Release C provides a saved snapshot, historical claim alignment that was not retained is explicitly unavailable; never substitute the latest live claim links for an older capture. With a saved snapshot, the historical comparison remains reproducible. No unsupported contradiction is inferred from textual difference.

## 7. Capability E4 — Durable investigation runs and changes

### Minimal new records

Add `InvestigationRun` for one `run_case` invocation: `id`, `case_id`, per-case `sequence`, trigger (`initial|rerun|monitor`), requested start stage, parameter snapshot, optional predecessor ID, status (`running|succeeded|paused|failed|interrupted`), coverage (`complete_requested_scope|partial|failed|not_attempted|unknown`), coverage details, timestamps, error details, baseline snapshot ID and resulting snapshot ID. A rerun/resume gets a new ID.

Add nullable grouped-run references to `CaseStageRun` and `Event`; keep `Event.case_run_id` as its existing stage FK. Keep the existing `/run-history` response stage-oriented.

For case write exclusion, add nullable owner-token/kind/ID fields to `TopicCase` (or an equivalently small transactional guard if implementation review justifies it). Claim/release ownership atomically. Every case-bound write transaction must validate its owner token before committing. An explicit interrupt atomically invalidates the token and run state; an old worker cannot commit using its superseded token. Legacy direct SQL scripts are not fenced by this application mechanism and must be stopped before production promotion.

Add immutable `CaseSnapshot`: `id`, `case_id`, `investigation_run_id`, creation time, schema/identity/policy versions, canonical payload, semantic hash and stored delta. Payload freezes article metadata/content hashes, individual claims, statuses, link/passages/immutable-citation/capture references, review state and exceptions. Capture text is referenced by immutable ID, not duplicated or read through mutable evidence content. Store enough before/after text to render removed claims without a live row.

### Observation semantics, not a new event-sourcing system

- The MVP snapshot is an observation of the actual committed case state under a consistent read transaction. It is not a claim that the entire pipeline committed atomically or that every observed entity was discovered by the current run.
- Freeze the comparison baseline when the invocation starts: latest earlier eligible successful snapshot ordered by case sequence. Use a single-writer case-operation guard; a conflicting invocation must be rejected explicitly rather than interleaving snapshots. Scope the guard to automatic runs and case-bound intake/review/exception writers. Crash recovery is CLI-only, explicit and fenced so an abandoned worker cannot later commit. Do not infer interruption merely from elapsed time or mutate on GET.
- Finalize success, snapshot and delta together. Full successful runs and successful scoped/partial-acquisition runs with valid analysis can publish eligible snapshots; partial coverage is conspicuous. Failed/paused/interrupted runs remain visible but do not advance the successful baseline. A first snapshot is `initial`, not a surge of new-change alerts.
- Earlier successful stage commits can survive an ultimately failed run. Carry known origin stage/run IDs into observations; changes incorporated later are attributed to that origin, or `unknown`, not automatically to the next successful run. Candidates/failed analysis must not masquerade as newly validated claims.
- Never remove articles because they disappear from an RSS window, relevance selection or capped retrieval. Preserve untouched events/claims on scoped runs. “No longer extracted” is allowed only for a successfully reprocessed event with valid, complete-for-its-recorded-input extraction; never for fallback, failure, no-content or unprocessed events. This is a change in extraction, not a retraction or truth determination.
- Diff individual claims by stable IDs/signatures, not grouped-claim counts or random row IDs. Relation/capture changes and classifications are meaningful. Execution IDs, order, run duration, last-seen timestamps and regenerated timestamps are not semantic changes.
- Review/exception states can be compared as observed at snapshot times. Without a persisted actor/action record, the UI must not say who made a change or label it a human decision. A full immutable reviewer audit log is deferred.
- Case-bound intake/review/exception changes between runs appear in the next observation with available provenance. No-op runs create an observation but an empty semantic delta. An empty delta with partial coverage means “no changes in observed data”, never “all sources unchanged”.
- Future report files use run-specific paths; retain current case pointers for compatibility. A report referring to an older run resolves its corresponding snapshot, not latest mutable data. Failed report writing does not produce a successful run.

**File/database finalization protocol:** under the case owner guard, construct a consistent snapshot/delta candidate and generate its report into a temporary sibling directory on the same filesystem. Finish/flush the files, then atomically rename the complete directory to a new immutable run-specific destination. Only afterward, in one guarded SQLite transaction, insert snapshot/delta/artifact references, mark the invocation succeeded and update case report/snapshot pointers. Revalidate the owner token in that transaction. Report generation/rename failure leaves no successful baseline or new report pointer; record failure. DB finalization failure after a successful rename may leave an unreferenced immutable directory, which is acceptable and reported for later cleanup; it must not be exposed via uncommitted pointers. Do not publish/copy a required report after committing success, overwrite an older run directory, or clean orphan directories as part of normal GET handling. Test both file-side and DB-side failures.

Changes response: availability (`initial|ready|pending|unavailable`), baseline/target snapshot IDs, coverage, paginated typed changes (`article_added`, `capture_changed`, `claim_added`, `claim_no_longer_extracted`, `classification_changed`, `relationship_changed`, `review_state_changed`, `exception_changed`), before/after values and immutable entity references.

**Acceptance:** identical runs have no semantic changes; partial retrieval causes no false removals; event persistence failure cannot become a successful baseline; paused runs do not masquerade as completed; changed content is detected at the same URL; historical claims remain inspectable after live rewrites; reviews are not spuriously reset; case write conflicts and explicit interruption are tested.

## 8. Capability E5 — Search and stable navigation

V1 is **case-scoped lexical search** over current source titles/text and current claim text. Cross-case and historical full-text search, semantic/vector retrieval and arbitrary filter DSL are deferred. Historical navigation remains available by snapshot/capture link.

- Use SQLite FTS5 when available. An explicit capability check/test must precede installation. Missing FTS/index → a clear unavailable state/503 with an operator remedy, not silent `LIKE` fallback or an empty result. Rebuild only through a CLI command scoped to a supplied database.
- Index current evidence captures once per logical evidence and individual current claims with typed IDs/case metadata. Older capture text must not appear as current content after a refresh. Index updates/removals participate in the owning database transaction; rollback cannot leave search ahead of stored state. Bootstrap/rebuild is idempotent and excludes unowned legacy tables.
- `q` is trimmed, 1–256 code points, interpreted as literal all-term search. Tokenize deterministic Unicode word terms, quote/escape them for FTS, bind SQL parameters, and do not expose raw FTS operators. A query with no searchable terms is a validation error, not a full scan.
- Filters: result type (`claim|evidence`), publisher key, claim verification state, publication date range (UTC, start-inclusive/end-exclusive; unknown dates excluded when date filters apply). Status applies only to claim results. Reject a status filter combined with evidence-only type; when type is omitted, a status filter narrows results to claims. Party filtering can follow later rather than inventing evidence-party semantics.
- Default page size 25, max 100; nonnegative offset; deterministic rank plus `(resultType,id)` tie-break. Return total count, applied filters, plain-text snippet, matched field and safe deep link. Snippets do not imply validated citations; raw FTS `<mark>` HTML is not returned/rendered.
- Deep links use existing case tabs with explicit `claim`, `evidence`, `capture`, immutable `citation` and optional `snapshot` selection parameters. Case IDs and resource IDs are URI-encoded by the client. Use snapshot-backed readers for historical/removed claims; return explanatory 404/unavailable states rather than silently redirecting to another item.
- Add a search entry point in the case workspace, accessible labels, keyboard selection, filter clearing and URL-persisted query state. Search results link to the inspector, timeline/graph entry points use the same link helpers.

**Acceptance:** known title/body/claim terms are found; source updates and deleted/replaced current claims are reflected transactionally; repeated rebuild produces identical results; quotes/punctuation/SQL-like input cannot escape query semantics; pagination is stable; wrong-case resources never leak. Benchmark a documented synthetic fixture (target p95 under 500ms warm for 10k evidence/20k claims); record actual results, avoid hardware-dependent timing assertions in unit tests.

## 9. Proposed GET contracts

New names below are proposals, not existing endpoints. DTOs use existing camelCase conventions. Define resource-specific service readers instead of rebuilding the entire case payload for every quotation or search request.

| Route below `/api/cases/{case_id}` | Response / behavior |
|---|---|
| `/citations/{citation_id}` | Frozen claim/assessment/passage/capture reference; resolves independently of a live claim/link |
| `/claims/{claim_id}?snapshotId=...` | Claim detail, effective relationship/provenance, passages, counts and immutable references; snapshot optional |
| `/evidence/{evidence_id}?snapshotId=...` | Source metadata, capture list/current selection and related claim references; no bulk source bodies |
| `/evidence/{evidence_id}/captures/{capture_id}?start=0&length=20000` | Text window, start/total lengths, hash and metadata; length max 50000 code points; exact full capture remains in storage |
| `/sources` | Current publisher/dependency groups and policy/methodology limitations |
| `/comparison?left=...&right=...&leftCapture=...&rightCapture=...` | Two pinned capture selections and paginated claim-alignment rows |
| `/investigation-runs` and `/investigation-runs/{run_id}` | Paginated grouped runs / details; distinct from existing stage history |
| `/investigation-runs/{run_id}/changes` | Availability, baseline/target IDs, coverage and paginated delta |
| `/snapshots/{snapshot_id}` | Snapshot metadata/counts/versions; entity bodies resolve through snapshot-aware detail readers |
| `/search?q=...` | Paginated typed lexical results and applied filters |

List/comparison/changes endpoints use `limit`/`offset`, defaults 25/max 100. Unknown case or wrong-case/evidence/run/snapshot/capture ID → 404; malformed query/range/incompatible selectors → 422; optional unavailable index capability → 503. Empty valid results → 200 with empty items. Capture `start` must be within `[0,totalLength]`, length within `[1,50000]`; truncate only the returned window at EOF, with explicit lengths. Opening any view makes GET requests only.

Additive DTO fields default safely for legacy data. Preserve current list/tab endpoints. Update Python DTOs, service serializers, mappers, TypeScript interfaces, fixtures and clients in the same ticket. Existing `supportCount`/`opposeCount` become evidence-assessment counts, not attachments; document that correctness change and test every consumer.

## 10. Migration, rollout and safety

- Use additive, inspector/idempotency-aware migrations in the existing manager; serialize migration ownership and allocate the next unused version at implementation time. Test fresh creation plus upgrade from pre-feature versions, including existing legacy links. Update runtime tests that currently assume six versions.
- Do not infer historical grouped runs from timestamps, rewrite existing primary IDs, or attach unassigned legacy articles to fabricated cases. Nullable new fields represent unknown history.
- Test fixtures enable/check referential integrity for new relationships. Production-wide FK enforcement and historical-data repair stay separate; new features must validate case ownership regardless of that setting.
- Persist snapshot/passage/policy schema versions. Schema rollback after writes is via a tested backup restore, not a down migration that drops captures/history. Stage rollout so the older-compatible reader remains available until new readers are verified.
- Run all server/browser acceptance checks with an explicit temporary working directory/config/database, not the default production DB. E2E startup must not initialize or migrate production as a side effect.
- Keep deployment loopback/trusted. No worker may expose a server publicly or add public input surfaces as part of these tickets.

## 11. End-to-end release acceptance

On a deterministic synthetic case: ingest two sources and one copied source; extract claims with a valid quote and one invalid quote; open the valid inspector by deep link; compare sources and see dependency warnings; rerun identical inputs and observe no semantic change; update one source and see a new immutable capture plus a meaningful delta; search for old/new current text and navigate to the right version; open the older snapshot after a claim rewrite; simulate a failed source, failed write and interrupted run without a false-success baseline.

Also verify keyboard/reload/back/forward behavior, no injected source HTML, no invented alerts or scores, no web mutation routes, no production-data writes, backend/frontend test gates, current architecture documentation and no undocumented API/schema drift.

## 12. Owner decisions before dispatch

The owner approved the following defaults on 2026-11-14. Implement one bounded ticket at a time with parent verification; stop at release review gates:

1. Read-only website and local/trusted, single-writer deployment remain in place.
2. Deliver A → B → C; build on fixtures before separately approved historical-data reconciliation.
3. V1 uses exact quoted passages, conservative dependency detection and exact claim signatures; fuzzy/semantic matching and automatic fact certification are deferred.
4. Search is case-scoped first; collaboration, notifications and OCR remain out of scope.
5. Run DeepSeek v4.1 workers one bounded ticket at a time, with parent review and verification before the next dependent ticket. No large multi-agent workflow or production rollout is authorized implicitly.
