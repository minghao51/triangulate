# Web-app refinement specification (2026-11-23)

Status: **PROPOSED** — implementation-ready specification for owner review. This document
is not an approval and not evidence of implementation: no application code, schema, tests or
configuration were changed to produce it, and no tests were run. All 22 tasks referenced here
are `status: proposed` / not started.

Companion documents: [technical contracts](20261123-web-app-refinement-contracts.md) ·
[implementation hub](20261123-web-app-refinement-implementation.md). Design basis:
[product wireframe set](20261123-product-wireframe-set.md) and the
[wireframe SVG folder](20261123-product-wireframes/). Prior context:
[remaining work after Release C](20261121-remaining-work-after-release-c.md).

## 1. Purpose and boundaries

This specification defines bold but evidence-first improvements to the delivered web app:
a truthful responsive shell, grouped case information architecture with URL context, consistent
reader states, safe case-scoped review/annotation/exception workflows, dense evidence and capture
reading, recorded-history integrity, and two **optional** history extensions (X01 ad-hoc snapshot
comparison, X02 historical report artifacts) that require separate owner approval.

What this document does **not** claim or authorize:

- Nothing is implemented. Proposal ≠ shipped ≠ owner approval.
- The X01/X02 API routes are **PROPOSED and do not exist today**. Core GET readers cited below
  already exist and are reused, not rebuilt.
- No public deployment, auth/RBAC, OCR, vector search, notifications, server jobs, new core POST
  endpoints, PDF/ZIP export, or production data repair. D01 (historical data repair) is a separate
  owner gate and is not feature approval.
- No dependency framework, theme, state-platform or routing-framework rewrite. Improvements use the
  existing CSS/design system and the existing React Query pattern (`@tanstack/react-query`,
  `frontend/package.json:22`).

## 2. Verified baseline (already implemented — do not rebuild)

E1–E5 are delivered and verified against source: captures/citations/inspector, source grouping,
source comparison, immutable snapshots / grouped runs / stored deltas, and case lexical FTS search.
Older proposal and status paragraphs in historical documents are stale where they disagree with
actual source, the delivered architecture notes, and the 2026-11-21 remaining-work brief; those
outrank them. Historical test counts (e.g. the 2026-11-21 figures) are not today's verification.

Parent-verified baseline facts this spec builds on:

- **Routes and tabs.** 10 frontend routes, 12 case tabs. `frontend/src/pages/CaseIntelligenceCenter.tsx`
  holds 12 route-backed case tab buttons and currently navigates in a way
  that drops per-view state. Specialized existing routes (Sources, Network, Narratives, Pipeline) stay
  compatible and receive coherent case chrome without duplicate shells.
- **Wireframes.** The suite is 24 primary screens / 42 selected states / 3 viewports
  (375×812, 768×1024, 1280×800) = 263 SVG files (66 definitions × 3 = 198, plus 55 continuation
  frames and 10 flow diagrams). Static design only: continuation frames describe overflow/reflow,
  **not** a required app wizard, pagination or new routes. Red annotations and the 8-grid are drawing
  style, not production CSS.
- **Shell truthfulness gap.** `frontend/src/components/Layout/Shell.tsx` hardcodes "System Online"
  (:124), a bell badge of 3 (:159) and an "Analyst / Administrator" identity (:176–177). There is no
  real identity, notification or telemetry source behind them. `/health` reports process liveness only
  and must not be presented as whole-system health.
- **Deep links.** `frontend/src/services/deep-links.ts` already owns the inspector, comparison,
  changes and search URL families (`INSPECTOR_PARAMS`:9, `COMPARISON_PARAMS`:140,
  `CHANGES_PARAMS`:220, `SEARCH_PARAMS`:292, with builders such as `buildComparisonUrl`:205).
- **Review already works.** The overview review flow in `CaseIntelligenceCenter.tsx` already supports
  Approve / action_required / Reject with rationale retained on error and cleared on success. What is
  missing is the full error/uncertainty state set, not the workflow.
- **Existing readers.** `get_case_sources` (`src/http/app.py:254`) and
  `TopicCaseService.get_source_summary` (`src/cases/service.py:424`, claimId option, typed
  `SourceSummaryDTO` at `src/http/schemas.py:665`) already exist; `ChangesBody` already has truthful
  initial/pending/unavailable/partial states with pagination; `SearchTab` already implements the full
  503/422/empty/out-of-range/plain-snippet/all-term lexical matrix; NarrativeLandscape, MonitoringCenter
  (30 s poll) and PipelineMonitor (5 s poll, configured-vs-recorded distinction) already present
  truthful states; Dashboard already uses 2 queries (cases + monitoringSummary) with
  `CaseListItem` counts / `openExceptionsCount` / `hasNewMaterial`.
- **Known defects for deliberate correction.** Review-activity and evaluation readers on an unknown
  case leave a service `ValueError` unmapped, so the HTTP request fails rather than returning 404.
  `tests/test_http_api.py:727` (`test_case_evaluation_summary_missing_case_still_errors`) pins the
  direct service's `ValueError`, not an HTTP 500 assertion. Preserve that service behavior; add
  HTTP-specific 404 regressions. The
  annotation service (`add_review_annotation`, `src/cases/service.py:4154`) validates vocabulary and
  non-empty content but not target ownership. `SourceAnalysis` derives source counts from evidence
  records instead of displaying the existing source-dependency summary. Map markers accept
  `typeof number` only.

## 3. Requirements

### R01 — Truthful, responsive shell

**Goal.** Remove fabricated status, notification and identity chrome; make the shell responsive,
accessible and honest about its trust boundary.

**Interactions & data.** Delete the hardcoded "System Online" text, the static bell badge "3" and the
"Analyst / Administrator" profile block (`Shell.tsx:124,159,176–177`). Replace with a visible,
persistent caveat that the app runs at a local/trusted unauthenticated boundary — no health-derived
whole-system status; `/health` may only be described as process liveness ("process ok"). Add a
responsive navigation menu (rail ≥1024 px, top bar 768–1023 px, stacked below 768), a skip link,
route breadcrumbs and correct focus management. Show the configured transport mode accurately:
"Configured API" when an API base is configured; otherwise "Static preferred; missing fixtures may
use API". Do not call fallback-capable mode fixture-only or imply response freshness. No new routing
framework or change to fallback policy.

**States.** Shell has no loading/empty states of its own; menu open/closed per breakpoint; the
trust-boundary and configured-data-mode caveats are always visible (not dismissible toasts).

**Acceptance.** No fabricated status/identity/notification strings remain in rendered output; the
boundary caveat is visible at all three viewports; keyboard users can reach the skip link first,
operate the menu and see focus; breadcrumbs match the current route; text (not colour alone)
conveys any status.

**Code targets.** `frontend/src/components/Layout/Shell.tsx`, `Shell.css`; existing CSS/design-system
tokens only.

### R02 — Grouped case IA and URL context

**Goal.** Grouped, route-backed case navigation that preserves existing paths and carries explicit,
allowlisted per-view URL state.

**Interactions & data.** Replace bare tab buttons with grouped native links using
`aria-current` (no fake ARIA tabs without the full keyboard pattern). Groups: **Start**
(Overview, Search) · **Evidence** (Evidence, Claims, Compare, Sources) · **Context**
(Parties, Map, Timeline, Network, Narratives) · **Review & Output** (Exceptions, Report) ·
**Activity** (Changes, Run history, Pipeline). Group headings create no routes. Existing paths stay
stable. Extend `deep-links.ts` families; do not invent a registry/router/state engine. Each target
view gets an explicit allowlist of URL params; unrelated unknown params are dropped, never blindly carried.
A historical-selector conflict is an exception: never silently discard it and reinterpret a frozen
link as current data. The 12 tabs plus four existing specialized routes are 16 destinations, not
16 tabs. Last committed per-view href may be remembered as session memory per case; Back and
reload always return stable committed URLs; explicit cross-links choose their context and "Clear" is
explicit.

**Historical/current boundary.** The browser key `snapshot` maps to the API `snapshotId` (no invented
`snapshotId` browser key). Current-only readers (search, timeline, parties, overview, monitoring, …)
reject snapshot selectors with 422 — they must not silently become historical. Only existing
claim/evidence/comparison readers accept snapshot selectors. Citations are independently frozen
by citation ID; their GET rejects snapshot selectors (as does capture-window GET). A current-only
view opened with a historical selector shows "Historical view unavailable" before fetching, or
surfaces the API's 422; it never silently shows current data. Only an explicit
"Open current ⟨view⟩" transition strips historical selectors. No historical lexical, global
or vector search exists or is added.

**Acceptance.** All existing route URLs still resolve; grouped nav exposes the five groups with
`aria-current`; Back/reload restore committed view state; an unsupported param is dropped from the
URL; a snapshot selector on a current-only view yields 422 (or is stripped by "Open current");
cross-links land on the intended case and view.

**Code targets.** `frontend/src/pages/CaseIntelligenceCenter.tsx`,
`frontend/src/services/deep-links.ts` (+ `deep-links.test.ts`), tab components under
`frontend/src/pages/tabs/`.

### R03 — Consistent reader states and query discipline

**Goal.** Migrate simple effect-based readers to the existing case-keyed React Query pattern and
present loading/empty/error/unavailable consistently with existing components.

**Interactions & data.** Query keys include every case/entity/capture/snapshot/filter/paging selector;
`enabled` only for valid IDs; late responses for a previous case are cancelled or ignored; invalidation
uses the existing keys (no `['case-detail']` vs `['caseDetail']` cache duplication). Polling only on
visible, active, recorded surfaces; label "Last fetched" vs "Last observed"; pause when hidden using
existing query capabilities. Background polling (e.g. the 15 s caseDetail poll) must never reset
in-progress notes or move focus, and must never imply "saved". Drafts never vanish. No generic query
platform or universal state registry is introduced — new focused components/helpers only where a
feature cannot fit an existing boundary.

**States.** The four shared states (`shared-loading`, `shared-empty`, `shared-not-found`,
`shared-network-error`) get one shared recipe rendered with existing Card/Badge/status components.

**Acceptance.** An effect-based reader migrated to React Query passes its existing tests; switching
case mid-flight cannot populate the wrong case's UI; a poll refresh leaves an in-progress note intact;
hidden tabs do not poll; every query key contains its case key.

**Code targets.** `frontend/src/services/api.ts`, tab readers in `frontend/src/pages/tabs/` and pages
under `frontend/src/pages/`; `@tanstack/react-query` v5 patterns already in use.

### R04 — Safe case review, annotation, exception and evaluation

**Goal.** Keep the three existing POST families (review, exceptions, annotations) and make their
failure and uncertainty states complete and honest.

**Interactions & data.** Overview review keeps Approve / action_required / Reject; rationale is
retained on error and cleared only on confirmed success. Every write form distinguishes: pending
(disabled only the same write form/row), saved (after server ack **and** read refresh), 409 writer
conflict, 422 blocked approval / invalid target, transport uncertainty (unknown outcome), and
"server invalidated a prior review" (stale). Review mutations use `retry: false`; an ambiguous
network outcome is reconciled via GET before any manual retry; there is **never** an automatic POST
retry or a fake Undo. A successful POST followed by a failed refresh means "Accepted; refresh failed",
not "Not saved"; offer a GET retry. For a lost POST response, refresh may remain inconclusive because
there is no idempotency/correlation guarantee; require explicit confirmation and warn that retrying
an annotation may create a duplicate. A late submit response for Case A must not alter a Case B form. Because there is
no server expected-revision/CAS today, the UI must describe staleness as "recorded invalidation or
detected refresh" — never as atomic proof that the operator reviewed the current revision (full
revision preconditions are a future, separately designed task).

**Evaluation reader.** `latest: null` is valid and renders "No saved evaluation"; an error is distinct
from empty; a real score of 0 renders 0; GET never creates an evaluation.

**Annotation targeting.** A contextual target picker offers current-case entities only (case, claim,
evidence, exception, narrative). Frozen/removed claims are read-only and offer no fake annotation
target; citation/capture are not target types. Missing case → 404; missing or wrong-case target →
the same uniform 422 (no existence leak). No identity is trusted from an author string. No
update/delete endpoints. Annotation events carry mirrored `annotation:*` audit entries; the UI
partitions and labels technical audit entries vs human notes and never shows one annotation as two
human comments or dedups by text/time guesswork.

**Acceptance.** Each state above is reachable and visibly distinct; retry is never automatic; notes
survive a background poll; a 409 and a 422 render differently; "No saved evaluation" shows for
`latest: null`; score 0 shows 0; the target picker lists only current-case entities.

**Code targets.** `frontend/src/pages/CaseIntelligenceCenter.tsx` (overview review), review/annotation
forms and `ExceptionsTab.tsx`; backend corrections in F05.

### R05 — Claims and evidence browsing + comparison selection

**Goal.** A dense, responsive claim/evidence reader with explicit provenance and a safe two-source
comparison selection flow.

**Interactions & data.** `EvidenceTab.tsx` / `ClaimsTab.tsx`: responsive dense lists, explicit
model-vs-legacy provenance labels, allowlisted filters and sort applied to the **loaded dataset
only** (client paging of loaded arrays, labelled as such — no claim of server pagination), stable IDs
and selection that survives re-render, and contextual "inspect" actions that carry the selection into
the inspector URL family. Comparison selection lives in a session-only, case-scoped tray (see R07 and
the contracts doc): exactly two **distinct** sources, a third is explicitly rejected (no silent
replacement), pinned captures ride on the committed Compare URL.

**States.** `evidence-filter-empty`; comparison selection states per the state inventory.

**Acceptance.** Filtering/sorting never triggers a network claim of server paging; provenance is shown
for every row; selection survives a re-render and reuses the existing inspector URL builder; the tray
holds max 2 distinct sources and visibly refuses a third.

**Code targets.** `frontend/src/pages/tabs/EvidenceTab.tsx`, `ClaimsTab.tsx`, `CompareTab.tsx`,
`frontend/src/services/api.ts`, `frontend/src/types/backend-models.ts`.

### R06 — Inspector reading

**Goal.** Improve (not rebuild) the E1 capture inspector: explicit diagnostics, exact quotation
windows and complete mobile metadata.

**Interactions & data.** All inspector diagnostics are explicit: missing quotation, source
unavailable, ambiguous match, no match, legacy record. Highlight windows use exact Unicode codepoint
offsets (Python slice semantics server-side; `Array.from` in the browser; LF normalization only, never
NFKC/casefold for highlighting). Citation rows show frozen context where the citation is historical;
frozen contexts are read-only. On mobile, all metadata (capture id, timestamps, offsets, provenance)
is reachable without horizontal clipping. Focus is restored when the inspector closes.

**States.** The five `inspector-*` states, each with distinct text (not colour alone).

**Acceptance.** Each diagnostic state renders its own message; an offset window containing astral
characters highlights the exact codepoints; frozen citations cannot be edited; closing the inspector
returns focus to the invoking control; 375×812 shows all metadata.

**Code targets.** `frontend/src/components/inspector/EvidenceInspector.tsx`,
`frontend/src/components/inspector/inspector-utils.ts`.

### R07 — Comparison and source provenance

**Goal.** Keep existing comparison states/paging and honest source provenance; wire SourceAnalysis to
the existing sources API instead of implying publisher independence.

**Interactions & data.** Comparison keeps its existing states, paging and own-capture crosslinks
(two distinct evidence IDs are required; selecting one source twice is a validation state even
when its capture versions differ). Older versions of one source remain inspectable through capture
history, not the two-source Compare view. The comparison tray (session-only, case-scoped, capped at two distinct sources + pins,
explicit third rejection, cleared on case/historical-context change after explicit notice) commits via
the existing `buildComparisonUrl`, which then resolves default captures server-side and replaces the
URL with pinned IDs. `SourceAnalysis.tsx` keeps useful recorded evidence counts and additionally
consumes the existing `get_case_sources` API (`src/http/app.py:254`) rendering the typed `SourceSummaryDTO`
(`src/http/schemas.py:665`); it states policy/method limitations (aggregated summaries are not proof
of independent corroboration; model consensus is not truth).

**States.** `comparison-selection`, `comparison-same-source`, `comparison-no-second-source`,
`comparison-empty`, `comparison-historical-unavailable`, `comparison-dependency-warning`.

**Acceptance.** Committing the tray yields a Compare URL with pinned capture IDs; a third selection is
refused visibly; SourceAnalysis issues the sources GET and renders DTO fields; no UI text claims
publisher independence; same-source selection is rejected without rendering a self-comparison.

**Code targets.** `frontend/src/pages/tabs/CompareTab.tsx`, `frontend/src/pages/SourceAnalysis.tsx`
(+ `SourceAnalysis.test.tsx`), `frontend/src/services/deep-links.ts`.

### R08 — Search and local saved views

**Goal.** Preserve the current lexical-only search matrix; add inline validation, snippet
accessibility and explicit opt-in local saved filter views.

**Interactions & data.** Search stays case-scoped lexical (FTS) with all-term semantics, plain-text
snippets, and the existing type/publisher/status/date filters; the existing 503/422/empty/out-of-range
page handling is kept. Inline field validation improves (per-field messages before submit); the
backend is not rebuilt and no historical or global scope is added. Saved views are local-only
(localStorage v1; full limits and privacy rules in the contracts doc): explicit user "Save" — no
autosave, no history tracking — and free-text query values (`q` and `claimQuery`) are **excluded by
default**; including either requires a separate explicit warning and consent. Save/apply/manage
controls are available in the existing Search, Claims and Evidence filter bars. Delete one /
delete case / delete all feature-owned views are provided.

**States.** `search-no-results`, `search-index-unavailable`, `search-invalid-filters`,
`search-out-of-range`.

**Acceptance.** The existing search state matrix still passes unchanged; invalid filters show inline
messages without a request; a saved view restores only allowlisted metadata; saving with query text
requires the extra consent step; quota/private-mode failure yields a visible ephemeral fallback.

**Code targets.** `frontend/src/pages/tabs/SearchTab.tsx` (+ `SearchTab.test.tsx`),
`frontend/src/services/deep-links.ts` (`SEARCH_PARAMS`).

### R09 — Recorded history and frozen navigation

**Goal.** Expose recorded run deltas and stage history without conflating IDs, and freeze only the
readers that support freezing.

**Interactions & data.** `ChangesTab.tsx` keeps `ChangesBody` exactly as delivered: truthful
initial/pending/unavailable/unchanged-partial states with pagination. `RunHistoryTab.tsx` stays
stage-oriented: `Event.case_run_id` is the stage-attempt FK
(`src/storage/models.py:193`) while `InvestigationRun` IDs identify grouped runs
(`src/storage/models.py:337`) — the UI labels these distinctly and never conflates them.
`ObservedByRunId` is an observer stamp, never a cause/actor attribution. No synthetic severity.
Freezing applies only to the supported historical readers: claim, evidence and comparison views plus
frozen citations. "Open current ⟨view⟩" is an explicit transition that strips historical selectors.

**States.** `changes-initial`, `changes-pending`, `changes-unavailable`, `changes-unchanged-partial`;
`historical-snapshot` screen; `comparison-historical-unavailable`.

**Acceptance.** A grouped-run ID and a stage ID are visually and semantically distinct; an observer
stamp is never rendered as an actor; the changes state set is unchanged; a frozen reader shows frozen
context and offers "Open current"; current-only views reject snapshot selectors.

**Code targets.** `frontend/src/pages/tabs/ChangesTab.tsx` (+ `ChangesTab.test.tsx`),
`RunHistoryTab.tsx`, `src/cases/history.py` (readers only).

### R10 — Linked analysis exploration (parties, narratives, network)

**Goal.** Selected IDs and claim/evidence links flow across parties, narratives and the corroboration
network without inventing linkage or truth claims.

**Interactions & data.** `PartiesTab.tsx`, `NarrativeLandscape.tsx`, `CorroborationNetwork.tsx` /
`frontend/src/components/data-visualization/NetworkGraph.tsx`: selection is carried by stable entity
IDs (existing node-ID handling and its tests are preserved); claims and evidence link from each view
into the existing claim/evidence URLs. Stances are labelled "recorded" or "model-derived" — never
"true". Existing truthful B03 behaviours (real loading/error/retry in NarrativeLandscape; real counts
in MonitoringCenter) are preserved.

**States.** `narratives-empty`; `shared-*` states via the R03 recipe.

**Acceptance.** Selecting a party highlights and links only recorded IDs; node-ID tests still pass;
every stance label distinguishes recorded vs model-derived; empty narratives state renders distinctly.

**Code targets.** `frontend/src/pages/tabs/PartiesTab.tsx`, `frontend/src/pages/NarrativeLandscape.tsx`,
`frontend/src/pages/CorroborationNetwork.tsx`, `frontend/src/components/data-visualization/NetworkGraph.tsx`.

### R11 — Geography and timeline

**Goal.** Map markers and timeline entries honour stored data exactly: finite in-range coordinates
only, six valid timeline statuses plus an explicit unrecognized state, and no invented linkage.

**Interactions & data.** `MapTab.tsx` currently plots plain CSS projected markers with a
`typeof number` guard only. F13 requires finite numbers with latitude ∈ [−90, 90] and longitude
∈ [−180, 180] (`TimelineEvent.locationLat/locationLon`, optional country code). Invalid and missing
are **different** states; 0,0 is not "unknown"; no centroid inference, no new geocoder/tiles/browser
location permissions. An accessible linked event list accompanies the marker field; selection is
bi-directional with only recorded IDs; events do not always map to known claims, so navigation goes to
the event context/list — never an invented inspector claim ID. Timeline statuses are exactly
confirmed / probable / alleged / contested / debunked / unknown; an unexpected stored value renders
"Unrecognized status" with the raw value preserved. Date-unknown is separate from status; no 1970
epoch placeholders, no inferred chronology or geography.

**States.** `map-empty`, `timeline-unknown`.

**Acceptance.** A marker with out-of-range coordinates is classified invalid and excluded from the
field; 0,0 plots as recorded at 0,0 (not unknown); missing coordinates are listed as unknown;
selecting a list row highlights its marker and vice versa; an invalid stored status shows
"Unrecognized status"; no synthetic dates appear.

**Code targets.** `frontend/src/pages/tabs/MapTab.tsx`, `TimelineTab.tsx` (+ `TimelineTab.test.tsx`),
`frontend/src/types/backend-models.ts`.

### R12 — Current report reader and download recovery

**Goal.** A clear reader for the current stored report with honest pending/missing/error distinctions
and the two existing downloads.

**Interactions & data.** `ReportTab.tsx` reads the current stored report (GET) and offers the two
existing downloads (markdown, manifest). "Pending" requires recorded evidence of an in-progress
run/report stage; merely lacking a stored report means "Not generated" or "Unavailable", not pending.
A missing artifact and a failed read/download are distinct; each offers recovery (retry read / retry
download) without regenerating anything. Markdown rendering is accessible and safe (no raw HTML
execution). Core makes **no historical report claims** and no "latest" fallback is implied; the
optional historical extension is X02/F20.

**States.** `report-pending`, `report-download-error`.

**Acceptance.** Pending vs missing vs error render as three distinct states; both downloads use the
existing endpoints; a failed download shows `report-download-error` with retry; markdown headings are
navigable by screen reader and no script executes.

**Code targets.** `frontend/src/pages/tabs/ReportTab.tsx`, `ReportTab.css`.

### R13 — Operator and portfolio coherence

**Goal.** Dashboard, Case Explorer, monitoring, pipeline, AI info and the CLI guide form one coherent
operator surface built from existing counts — no N+1 fan-out, no new dashboard endpoint.

**Interactions & data.** `Dashboard.tsx` keeps its 2 queries (cases + monitoringSummary);
`CaseListItem` counts, `openExceptionsCount` and `hasNewMaterial` drive queue priorities in
`CaseExplorer.tsx`. MonitoringCenter keeps its real 30 s counts and continues to say
scheduling/alerts are not provided; PipelineMonitor keeps its 5 s saved case/stage attempts poll and
the explicit configured-vs-recorded distinction. Polling intervals are budgeted with existing polls
(new tab polls must not multiply load) and label "Last fetched" vs "Last observed".
`OperatorLaunchGuide.tsx` and `AiIntegrationInfo.tsx` present accurate AI/CLI information: the only
write surface is the three POST families plus CLI case creation/ingest/rerun/rebuild/recovery.

**States.** `pipeline-unrecorded`, `monitoring-unavailable`; B03 truthful states preserved.

**Acceptance.** Dashboard renders from the existing queries without per-case fan-out; priority order
follows recorded counts; monitor/pipeline texts contain no unsupported capability claims; hidden tabs
stop polling.

**Code targets.** `frontend/src/pages/Dashboard.tsx`, `CaseExplorer.tsx`, `MonitoringCenter.tsx`,
`PipelineMonitor.tsx`, `OperatorLaunchGuide.tsx`, `AiIntegrationInfo.tsx`.

### R14 — Verification, safety and performance

**Goal.** Every delivered change is gated by reproducible checks and the safety contract, with
proposed performance budgets that are recorded as budgets, not benchmark claims.

**Verification (from the contracts doc).** All backend verification runs in a **disposable copy of the
current worktree** (dirty bytes included — not `git archive HEAD`), scratch config/DB/output, paid
providers mocked, external IO disabled. `uv run pytest -q --disable-warnings` and
`uv run ruff check src tests scripts --output-format concise` in the disposable copy;
`npm run check` + `npm test -- --run` after frontend changes; focused tests first, then full relevant
gates. Browser verification uses the playwright-cli skill in an isolated headless session against a
synthetic API/DB; core journeys on Chromium + Firefox + WebKit where available — a missing engine is
recorded as "not proven", never "PASS". Viewports 375×812, 768×1024, 1280×800 plus 200 % zoom,
keyboard/focus, text-not-colour-alone, and no unintended document horizontal overflow.

**Performance budgets (proposed, not measurements).** No per-case fan-out; bounded rendered rows
(e.g. 50/page); search backend unchanged (25 default / 100 max page size, offset cap 2³¹−1);
the reproducible fixture latency record keeps its warm-search p95 500 ms target definition (not a
claimed current SLO); no hardware-dependent pytest asserts; capture windows 20k default / 50k max.
API traffic is read-only except the three narrow intentional POST families.

**Acceptance.** Each task lists its focused tests; F16 assembles the 24-screen/42-state coverage
evidence (3 viewports), keyboard and privacy/security/performance evidence; no deploy or commit is
performed; missing engines are explicitly unproven.

**Code targets.** `frontend/package.json` (scripts :15/:17), `frontend/playwright.config.ts`,
`frontend/playwright.b03.config.ts`, `tests/test_v01_e2e.py`, `scripts/v01_e2e_fixture.py`,
`frontend/.nvmrc`, `tests/conftest.py`.

## 4. Optional extensions (summary; full contracts in the contracts doc)

- **X01 — ad-hoc snapshot comparison** (F17/F18): a PROPOSED additive GET comparing two immutable
  snapshots of one case with an `ad_hoc` DTO distinct from recorded run changes; UI rides the existing
  Changes route behind an explicit owner decision. Never fabricates observed-by/causal attribution.
- **X02 — historical report artifacts** (F19/F20): PROPOSED artifact-descriptor-list and
  allowlisted-file-download GETs over immutable stored run artifacts, with strict case/run ownership,
  path containment and honest checksum semantics; UI pins a frozen run in the Report surface.

Both are optional, independently approvable, and explicitly **not** D01 (historical data repair) and
not production deployment approval.

## 5. Requirement → task traceability

| Requirement | Tasks |
|---|---|
| R01 truthful shell | F01, F16 |
| R02 case IA + URL context | F02, F16 |
| R03 reader/query consistency | F03, F16 |
| R04 review/annotation/evaluation | F04, F05, F16 |
| R05 claims/evidence + comparison selection | F06, F07, F16 |
| R06 inspector reading | F08, F16 |
| R07 comparison + source provenance | F09, F16 |
| R08 search + saved views | F10, F16 |
| R09 history + frozen links | F11, F16 |
| R10 linked analysis | F12, F16 |
| R11 geography/timeline | F13, F16 |
| R12 current report | F14, F16 |
| R13 portfolio/ops | F15, F16 |
| R14 verification/safety/performance | F00, F16, F21 |
| X01 snapshot comparison | F17, F18, F21 |
| X02 historical artifacts | F19, F20, F21 |

Task details, DAG, coverage tables and dispatch templates live in the
[implementation hub](20261123-web-app-refinement-implementation.md).
