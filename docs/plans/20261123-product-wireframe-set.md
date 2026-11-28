# Product wireframe set (proposal)

Date: 2026-11-23. Status: **proposal wireframes, not shipped and not implementation evidence.** Static design artifacts only: no application code, runtime, database, schema or API changed. All case ids, hosts, quotes and counts are synthetic (`example.invalid`).

This set illustrates the five workbench capabilities in [the evidence workbench specification](20261114-evidence-workbench-specification.md) §§4–8, [comparison UI](../architecture/20261118-comparison-ui.md), [changes UI](../architecture/20261120-changes-ui.md) and [search API](../architecture/20261120-search-api.md). The original single-screen artifact is retained: [20261123-evidence-workbench-wireframe.md](20261123-evidence-workbench-wireframe.md) / [.svg](20261123-evidence-workbench-wireframe.svg).

## 1. Inventory and shape

- **66 definitions** = 24 primary screens + 42 states, each drawn at **all three viewports** (desktop 1280×800, tablet 768×1024, mobile 375×812).
- **198 base frame files** plus **55 continuation frames** = **253 screen/state SVG files**, and **10 desktop flow boards** = **263 SVG files** plus `manifest.json`.
- Continuation frames are real screens at the same sanctioned viewport (`-part-2.svg`, `-part-3.svg`) carrying the remaining panes with compact repeated navigation and a `Part k of N` header; nothing is reduced to a title list.
- Coverage is **bounded and complete for the current routes/tabs plus the documented states below**. It is not every Cartesian state × module permutation and not a claim of implementation coverage.
- Shared state patterns represent multiple applicable modules explicitly in §6; only the named frames exist.
- Each file is standalone SVG, immediately previewable in a browser, with no HTML viewer and no external references.

## 2. Scope boundaries and explicit exclusions

In scope: low-fidelity layout proposals for the current product surfaces listed in §3 and §4, the five workbench capabilities, the documented reader states, and navigation/review flow boards.

Out of scope, and **not authorized by this artifact**: authentication and RBAC, public ingestion or a browser ingestion form, real-time collaboration, notifications, OCR, semantic/vector search, automated truth certification, production data recovery or repair, new API/schema fields, and any change to CI or app code. These remain separate proposals; drawing a placeholder for them would invent scope.

Navigation is browse-GET only. The only browser writes drawn are the three narrow human review POST families (review decision, exception action, review annotation). Ingest, rerun, rebuild and recovery stay CLI-only, local/trusted and unauthenticated. The annotation form is labelled as an explicit exception to the reader rule. The review API also accepts `defer`/`exception`; the current browser controls are Approve, action_required and Reject only, so no extra browser control is drawn.

## 3. Route to screen mapping (10 routes)

| Route | Screens |
|---|---|
| `/dashboard` | dashboard |
| `/cases` | case-explorer |
| `/cases/new` | operator-launch |
| `/cases/:id/*` | case-overview + 12 case tabs |
| `/cases/:id/pipeline` | pipeline |
| `/cases/:id/network` | corroboration-network |
| `/cases/:id/sources` | source-provenance |
| `/cases/:id/narratives` | narratives |
| `/monitoring` | monitoring |
| `/ai-info` | ai-info |

Tab paths: overview and the review/annotation form are the index route `/cases/:id/` (path `''`); the canonical inspector is `/cases/:id/evidence?claim=&evidence=&capture=`; the frozen claim panel is on `/cases/:id/changes?run=&claim=&snapshot=`.

## 4. Case tab to screen mapping (12 tabs)

| Tab | Screens |
|---|---|
| Overview | case-overview, review-annotation |
| Evidence | evidence-gallery, source-provenance |
| Claims | claims, capture-inspector, historical-snapshot |
| Compare | comparison |
| Parties | parties |
| Map | geographic-map |
| Timeline | timeline |
| Exceptions | exception-queue |
| Report | report |
| Changes | runs-changes |
| Search | search |
| Run history | stage-history |

## 5. Five-capability matrix

| Capability | Primary screens |
|---|---|
| E1 claim → quotation → capture inspector | claims, capture-inspector, historical-snapshot, review-annotation |
| E2 provenance and dependency grouping | source-provenance, comparison |
| E3 side-by-side comparison | comparison |
| E4 durable runs and changes | runs-changes, stage-history, historical-snapshot, pipeline |
| E5 case search and stable links | search, case-overview |

## 6. State applicability matrix (42 states)

Each state exists as three files. `applies` lists the modules the shared pattern represents; only the parent screen's frame exists. A generic network failure is a shared pattern in addition to the named frames.

| State | Parent screen | Applies to | Files |
|---|---|---|---|
| shared-loading | case-explorer | every list, tab and detail reader | [desktop](20261123-product-wireframes/shared-loading-desktop.svg), [tablet](20261123-product-wireframes/shared-loading-tablet.svg), [mobile](20261123-product-wireframes/shared-loading-mobile.svg) |
| shared-empty | case-explorer | all case and evidence lists | [desktop](20261123-product-wireframes/shared-empty-desktop.svg), [tablet](20261123-product-wireframes/shared-empty-tablet.svg), [mobile](20261123-product-wireframes/shared-empty-mobile.svg) |
| shared-not-found | case-overview | case routes, tab routes and deep links (includes unknown-tab fallback) | [desktop](20261123-product-wireframes/shared-not-found-desktop.svg), [tablet](20261123-product-wireframes/shared-not-found-tablet.svg), [mobile](20261123-product-wireframes/shared-not-found-mobile.svg) |
| shared-network-error | dashboard | all readers; generic submission failure pattern | [desktop](20261123-product-wireframes/shared-network-error-desktop.svg), [tablet](20261123-product-wireframes/shared-network-error-tablet.svg), [mobile](20261123-product-wireframes/shared-network-error-mobile.svg) |
| inspector-missing-quotation | capture-inspector | claim/evidence inspector links | [desktop](20261123-product-wireframes/inspector-missing-quotation-desktop.svg), [tablet](20261123-product-wireframes/inspector-missing-quotation-tablet.svg), [mobile](20261123-product-wireframes/inspector-missing-quotation-mobile.svg) |
| inspector-source-unavailable | capture-inspector | capture inspector | [desktop](20261123-product-wireframes/inspector-source-unavailable-desktop.svg), [tablet](20261123-product-wireframes/inspector-source-unavailable-tablet.svg), [mobile](20261123-product-wireframes/inspector-source-unavailable-mobile.svg) |
| inspector-ambiguous | capture-inspector | capture inspector | [desktop](20261123-product-wireframes/inspector-ambiguous-desktop.svg), [tablet](20261123-product-wireframes/inspector-ambiguous-tablet.svg), [mobile](20261123-product-wireframes/inspector-ambiguous-mobile.svg) |
| inspector-no-match | capture-inspector | capture inspector | [desktop](20261123-product-wireframes/inspector-no-match-desktop.svg), [tablet](20261123-product-wireframes/inspector-no-match-tablet.svg), [mobile](20261123-product-wireframes/inspector-no-match-mobile.svg) |
| inspector-legacy | capture-inspector | capture inspector | [desktop](20261123-product-wireframes/inspector-legacy-desktop.svg), [tablet](20261123-product-wireframes/inspector-legacy-tablet.svg), [mobile](20261123-product-wireframes/inspector-legacy-mobile.svg) |
| comparison-selection | comparison | comparison tab | [desktop](20261123-product-wireframes/comparison-selection-desktop.svg), [tablet](20261123-product-wireframes/comparison-selection-tablet.svg), [mobile](20261123-product-wireframes/comparison-selection-mobile.svg) |
| comparison-same-source | comparison | comparison tab | [desktop](20261123-product-wireframes/comparison-same-source-desktop.svg), [tablet](20261123-product-wireframes/comparison-same-source-tablet.svg), [mobile](20261123-product-wireframes/comparison-same-source-mobile.svg) |
| comparison-no-second-source | comparison | comparison tab | [desktop](20261123-product-wireframes/comparison-no-second-source-desktop.svg), [tablet](20261123-product-wireframes/comparison-no-second-source-tablet.svg), [mobile](20261123-product-wireframes/comparison-no-second-source-mobile.svg) |
| comparison-empty | comparison | comparison tab | [desktop](20261123-product-wireframes/comparison-empty-desktop.svg), [tablet](20261123-product-wireframes/comparison-empty-tablet.svg), [mobile](20261123-product-wireframes/comparison-empty-mobile.svg) |
| comparison-historical-unavailable | comparison | comparison tab | [desktop](20261123-product-wireframes/comparison-historical-unavailable-desktop.svg), [tablet](20261123-product-wireframes/comparison-historical-unavailable-tablet.svg), [mobile](20261123-product-wireframes/comparison-historical-unavailable-mobile.svg) |
| comparison-dependency-warning | comparison | comparison tab | [desktop](20261123-product-wireframes/comparison-dependency-warning-desktop.svg), [tablet](20261123-product-wireframes/comparison-dependency-warning-tablet.svg), [mobile](20261123-product-wireframes/comparison-dependency-warning-mobile.svg) |
| changes-initial | runs-changes | changes tab | [desktop](20261123-product-wireframes/changes-initial-desktop.svg), [tablet](20261123-product-wireframes/changes-initial-tablet.svg), [mobile](20261123-product-wireframes/changes-initial-mobile.svg) |
| changes-pending | runs-changes | changes tab | [desktop](20261123-product-wireframes/changes-pending-desktop.svg), [tablet](20261123-product-wireframes/changes-pending-tablet.svg), [mobile](20261123-product-wireframes/changes-pending-mobile.svg) |
| changes-unavailable | runs-changes | changes tab | [desktop](20261123-product-wireframes/changes-unavailable-desktop.svg), [tablet](20261123-product-wireframes/changes-unavailable-tablet.svg), [mobile](20261123-product-wireframes/changes-unavailable-mobile.svg) |
| changes-unchanged-partial | runs-changes | changes tab | [desktop](20261123-product-wireframes/changes-unchanged-partial-desktop.svg), [tablet](20261123-product-wireframes/changes-unchanged-partial-tablet.svg), [mobile](20261123-product-wireframes/changes-unchanged-partial-mobile.svg) |
| search-no-results | search | search tab | [desktop](20261123-product-wireframes/search-no-results-desktop.svg), [tablet](20261123-product-wireframes/search-no-results-tablet.svg), [mobile](20261123-product-wireframes/search-no-results-mobile.svg) |
| search-index-unavailable | search | search tab | [desktop](20261123-product-wireframes/search-index-unavailable-desktop.svg), [tablet](20261123-product-wireframes/search-index-unavailable-tablet.svg), [mobile](20261123-product-wireframes/search-index-unavailable-mobile.svg) |
| search-invalid-filters | search | search tab | [desktop](20261123-product-wireframes/search-invalid-filters-desktop.svg), [tablet](20261123-product-wireframes/search-invalid-filters-tablet.svg), [mobile](20261123-product-wireframes/search-invalid-filters-mobile.svg) |
| search-out-of-range | search | search tab | [desktop](20261123-product-wireframes/search-out-of-range-desktop.svg), [tablet](20261123-product-wireframes/search-out-of-range-tablet.svg), [mobile](20261123-product-wireframes/search-out-of-range-mobile.svg) |
| review-saving | review-annotation | review decision form | [desktop](20261123-product-wireframes/review-saving-desktop.svg), [tablet](20261123-product-wireframes/review-saving-tablet.svg), [mobile](20261123-product-wireframes/review-saving-mobile.svg) |
| review-failed | review-annotation | review decision form | [desktop](20261123-product-wireframes/review-failed-desktop.svg), [tablet](20261123-product-wireframes/review-failed-tablet.svg), [mobile](20261123-product-wireframes/review-failed-mobile.svg) |
| review-stale | review-annotation | review decision form | [desktop](20261123-product-wireframes/review-stale-desktop.svg), [tablet](20261123-product-wireframes/review-stale-tablet.svg), [mobile](20261123-product-wireframes/review-stale-mobile.svg) |
| review-saved | review-annotation | review decision form | [desktop](20261123-product-wireframes/review-saved-desktop.svg), [tablet](20261123-product-wireframes/review-saved-tablet.svg), [mobile](20261123-product-wireframes/review-saved-mobile.svg) |
| review-blocked | review-annotation | review decision form (approval path) | [desktop](20261123-product-wireframes/review-blocked-desktop.svg), [tablet](20261123-product-wireframes/review-blocked-tablet.svg), [mobile](20261123-product-wireframes/review-blocked-mobile.svg) |
| annotation-invalid | review-annotation | annotation form | [desktop](20261123-product-wireframes/annotation-invalid-desktop.svg), [tablet](20261123-product-wireframes/annotation-invalid-tablet.svg), [mobile](20261123-product-wireframes/annotation-invalid-mobile.svg) |
| evaluation-unavailable | claims | claims/evaluation reader | [desktop](20261123-product-wireframes/evaluation-unavailable-desktop.svg), [tablet](20261123-product-wireframes/evaluation-unavailable-tablet.svg), [mobile](20261123-product-wireframes/evaluation-unavailable-mobile.svg) |
| evaluation-failed | claims | claims/evaluation reader | [desktop](20261123-product-wireframes/evaluation-failed-desktop.svg), [tablet](20261123-product-wireframes/evaluation-failed-tablet.svg), [mobile](20261123-product-wireframes/evaluation-failed-mobile.svg) |
| exception-pending | exception-queue | exception queue | [desktop](20261123-product-wireframes/exception-pending-desktop.svg), [tablet](20261123-product-wireframes/exception-pending-tablet.svg), [mobile](20261123-product-wireframes/exception-pending-mobile.svg) |
| exception-failed | exception-queue | exception queue | [desktop](20261123-product-wireframes/exception-failed-desktop.svg), [tablet](20261123-product-wireframes/exception-failed-tablet.svg), [mobile](20261123-product-wireframes/exception-failed-mobile.svg) |
| exception-empty | exception-queue | exception queue | [desktop](20261123-product-wireframes/exception-empty-desktop.svg), [tablet](20261123-product-wireframes/exception-empty-tablet.svg), [mobile](20261123-product-wireframes/exception-empty-mobile.svg) |
| report-pending | report | report tab | [desktop](20261123-product-wireframes/report-pending-desktop.svg), [tablet](20261123-product-wireframes/report-pending-tablet.svg), [mobile](20261123-product-wireframes/report-pending-mobile.svg) |
| report-download-error | report | report tab | [desktop](20261123-product-wireframes/report-download-error-desktop.svg), [tablet](20261123-product-wireframes/report-download-error-tablet.svg), [mobile](20261123-product-wireframes/report-download-error-mobile.svg) |
| map-empty | geographic-map | map tab | [desktop](20261123-product-wireframes/map-empty-desktop.svg), [tablet](20261123-product-wireframes/map-empty-tablet.svg), [mobile](20261123-product-wireframes/map-empty-mobile.svg) |
| timeline-unknown | timeline | timeline tab | [desktop](20261123-product-wireframes/timeline-unknown-desktop.svg), [tablet](20261123-product-wireframes/timeline-unknown-tablet.svg), [mobile](20261123-product-wireframes/timeline-unknown-mobile.svg) |
| pipeline-unrecorded | pipeline | pipeline route | [desktop](20261123-product-wireframes/pipeline-unrecorded-desktop.svg), [tablet](20261123-product-wireframes/pipeline-unrecorded-tablet.svg), [mobile](20261123-product-wireframes/pipeline-unrecorded-mobile.svg) |
| monitoring-unavailable | monitoring | monitoring route | [desktop](20261123-product-wireframes/monitoring-unavailable-desktop.svg), [tablet](20261123-product-wireframes/monitoring-unavailable-tablet.svg), [mobile](20261123-product-wireframes/monitoring-unavailable-mobile.svg) |
| evidence-filter-empty | evidence-gallery | evidence gallery | [desktop](20261123-product-wireframes/evidence-filter-empty-desktop.svg), [tablet](20261123-product-wireframes/evidence-filter-empty-tablet.svg), [mobile](20261123-product-wireframes/evidence-filter-empty-mobile.svg) |
| narratives-empty | narratives | narratives route | [desktop](20261123-product-wireframes/narratives-empty-desktop.svg), [tablet](20261123-product-wireframes/narratives-empty-tablet.svg), [mobile](20261123-product-wireframes/narratives-empty-mobile.svg) |

## 7. Pagination and full render coverage

Every definition is drawn at all three viewports: desktop 1280×800 with a 240 px navigation rail, tablet 768×1024 and mobile 375×812 with a top bar (mobile uses a menu control). Panes that sit side by side on desktop stack on tablet and mobile; tables become labelled blocks on mobile. All regions use 24 px horizontal and vertical gutters; the mobile canvas uses a 368×808 drawing rect with a 375×812 root viewport (the only non-8 multiple).

When the body does not fit one viewport, the **remaining panes are rendered in continuation frames** at the same viewport (`<id>-<viewport>-part-2.svg`, ...). Each frame repeats compact navigation and carries a `Part k of N` header with previous/next frame labels; every pane is wrapped in `<g data-pane="pN">` and the manifest records `renderedPanes`, `frameIndex` and `frameCount` per file. The validator asserts that, for every definition and viewport, the union of rendered pane ids equals the declared pane inventory exactly once — no pane, control, field group, status vocabulary or metadata row is dropped. A pane too tall for one compact frame is split into real parts, and field groups keep their actions after the last group.

Frame counts below are derived by the generator, not fixed. Every definition at every viewport is base frame 1 plus the listed continuations.

| Definition | desktop | tablet | mobile |
|---|---|---|---|
| dashboard | 1 | 1 | 2 |
| case-explorer | 1 | 1 | 3 |
| operator-launch | 1 | 1 | 2 |
| case-overview | 1 | 1 | 2 |
| review-annotation | 1 | 2 | 3 |
| evidence-gallery | 2 | 2 | 3 |
| claims | 1 | 2 | 3 |
| capture-inspector | 1 | 2 | 3 |
| comparison | 2 | 2 | 4 |
| source-provenance | 1 | 1 | 2 |
| runs-changes | 2 | 2 | 4 |
| historical-snapshot | 1 | 1 | 2 |
| search | 2 | 2 | 2 |
| stage-history | 1 | 1 | 3 |
| pipeline | 1 | 1 | 2 |
| exception-queue | 1 | 1 | 2 |
| parties | 1 | 1 | 2 |
| geographic-map | 1 | 1 | 2 |
| timeline | 1 | 1 | 2 |
| report | 1 | 1 | 2 |
| corroboration-network | 1 | 2 | 2 |
| monitoring | 1 | 1 | 2 |
| ai-info | 1 | 1 | 2 |
| comparison-selection | 1 | 1 | 2 |
| comparison-same-source | 1 | 1 | 2 |
| comparison-empty | 1 | 1 | 2 |
| search-invalid-filters | 1 | 1 | 2 |
| search-out-of-range | 1 | 1 | 2 |
| annotation-invalid | 1 | 1 | 2 |
| exception-pending | 1 | 1 | 2 |
| report-pending | 1 | 1 | 2 |
| map-empty | 1 | 1 | 2 |
| timeline-unknown | 1 | 1 | 2 |

## 8. Flow boards (10)

Flow order labels are **navigation and review paths, not automatic execution or causal state transitions**. Thumbnails are geometry-derived miniatures of the desktop SVGs (rect/line primitives, snapped to 8 px); source text is omitted below the 12 px legibility floor and every thumbnail is captioned outside the frame. Annotations number each thumbnail and each transition. Annotation style exception: normal region numbers sit in the left gutter (24 px horizontal and vertical gutters, 8 px callout offset); the ten flow boards' narrow 16 px transition regions put their number immediately above the region instead, clear of the arrow and its caption.

| Board | Screens (left to right) | File |
|---|---|---|
| Primary evidence-workbench flow | case-explorer → claims → capture-inspector | [flow.svg](20261123-product-wireframes/flow.svg) |
| Claims, review and evidence flow | capture-inspector → review-annotation → evidence-gallery | [flow-claims-review.svg](20261123-product-wireframes/flow-claims-review.svg) |
| Comparison and provenance flow | evidence-gallery → comparison → source-provenance | [flow-compare-provenance.svg](20261123-product-wireframes/flow-compare-provenance.svg) |
| Runs, snapshots and stage history flow | runs-changes → historical-snapshot → stage-history | [flow-changes-history.svg](20261123-product-wireframes/flow-changes-history.svg) |
| Search and snapshot flow | search → historical-snapshot → case-overview | [flow-search-snapshot.svg](20261123-product-wireframes/flow-search-snapshot.svg) |
| Operator, pipeline and monitoring flow | operator-launch → pipeline → runs-changes → monitoring | [flow-operator-pipeline.svg](20261123-product-wireframes/flow-operator-pipeline.svg) |
| Review, exceptions and timeline flow | review-annotation → exception-queue → timeline | [flow-review-exceptions.svg](20261123-product-wireframes/flow-review-exceptions.svg) |
| Parties, map and timeline flow | parties → geographic-map → timeline | [flow-geography-parties.svg](20261123-product-wireframes/flow-geography-parties.svg) |
| Network, narratives and report flow | corroboration-network → narratives → report | [flow-network-report.svg](20261123-product-wireframes/flow-network-report.svg) |
| Dashboard, AI info, case and search flow | dashboard → ai-info → case-overview → search | [flow-dashboard-ai.svg](20261123-product-wireframes/flow-dashboard-ai.svg) |

## 9. Proposal status and honesty rules

Every SVG is a proposal: `<desc>` states it, headers/captions carry `Proposal · synthetic data`, and the status is recorded per manifest entry. Nothing here is evidence that a capability exists. Drawings must not contradict implemented invariants: capture is not verification; an exact quotation is not entailment; generated relations are `reported_by` or `uncertain`; model assessment provenance stays visible; a missing value is `unavailable`, never zero; independence is `unknown` unless a dependency edge is detected; configured is not completed; pending is not final; an empty delta with partial coverage is not "all sources unchanged"; party stance and Arbiter consensus are not truth.

Review-specific: `review-failed` is an explicit **409 active case writer conflict** with a read/refresh action; it does not claim the decision was saved and retains entered notes. Generic transport failure is a shared pattern, distinct from 409. `review-blocked` is **422 approval blocked by unresolved exceptions** and links the exception queue without saving. `annotation-invalid` covers a bad target and blank content (422). `evaluation-unavailable` is no saved evaluation (never 0); `evaluation-failed` is a failed evaluation read (retry, not pending and not empty). An unrecognized case tab route falls back to `shared-not-found` ("Tab not found"); it has no separate frame.

## 10. Interaction intent (SVG files are static)

Keyboard and focus intent is documented, not implemented: selection survives reload/back/forward through URL parameters (`claim`, `evidence`, `capture`, `citation`, `snapshot`, `tab`, `run`, `offset`, query/filters); the selected inspector or results heading receives focus once per selection; native select and button semantics are assumed; tab strips scroll horizontally on mobile. No SVG is interactive: no scripts, styles, links or `<a>` elements exist here.

## 11. Regenerate and validate

```bash
uv run --no-sync python docs/plans/20261123-product-wireframes/generate.py
uv run --no-sync python docs/plans/20261123-product-wireframes/validate.py
```

Generation is deterministic (no timestamps in output); running it twice produces byte-identical files. The validator holds the authoritative non-computed inventory (24 screen ids, 42 state ids, 10 flow files), re-runs generation in temporary directories, and checks XML, geometry, palette, fonts, strokes, annotation mapping, doc links, manifest bijection, counts, flow coverage and the mobile canvas exception. Source-of-truth context: `frontend/src/app/routes.tsx`, `frontend/src/pages/CaseIntelligenceCenter.tsx`, `frontend/src/pages/tabs/`, `docs/plans/20261114-evidence-workbench-specification.md` §§4–8, `docs/architecture/20261118-comparison-ui.md`, `docs/architecture/20261120-changes-ui.md`, `docs/architecture/20261120-search-api.md`, `docs/reference/http-api.md`.

## Known inconsistencies and backend dependencies

Status: proposal. Two limits of this set are recorded here rather than drawn as shipped behaviour.

- **Navigation.** Earlier revisions drew Network, Sources and Narratives in the global navigation rail. The route table (§3) scopes them to a case (`/cases/:id/network`, `/cases/:id/sources`, `/cases/:id/narratives`), so the rail now lists only the global destinations (Dashboard, Cases, Monitoring, AI info). The three readers are reached from a case and highlight `Cases`, with the case tab row and title carrying their context.
- **Dashboard backend dependencies.** The Coverage column and the Recent runs panel depend on backend changes that do not exist: the case-list DTO (`CaseListItem` in `src/http/schemas.py`) has no coverage field, and every runs endpoint is case-scoped (`/api/cases/:id/...`), so no cross-case recent-runs read exists. The application omits both today; the dashboard frames mark them as requiring backend support rather than as an app deficiency.

## 12. Per-file numbered annotations

Region numbers match `data-region` in each SVG and the manifest `regions` array one-to-one. Empty list means the file failed generation; the validator rejects that.

### dashboard-desktop.svg

[Open SVG](20261123-product-wireframes/dashboard-desktop.svg) · screen · desktop · Dashboard — case portfolio · route `/dashboard`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Dashboard — case portfolio header — title, synthetic context and available actions.
3 — Case portfolio — observed status and acquisition coverage per case, not a truth score. Requires backend support: a coverage field on the case-list DTO; CaseListItem has none today. · frame 1 of 1
4 — Observed totals — row counts only; no confidence, health or trend claim. · frame 1 of 1
5 — Recent grouped runs — recorded status and coverage across cases. Requires backend support: a cross-case runs read; every runs endpoint is case-scoped today. · frame 1 of 1
6 — Navigation entry points — monitoring and AI info are readers, not control planes. · frame 1 of 1

### dashboard-tablet.svg

[Open SVG](20261123-product-wireframes/dashboard-tablet.svg) · screen · tablet · Dashboard — case portfolio · route `/dashboard`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Dashboard — case portfolio header — title, synthetic context and available actions.
3 — Case portfolio — observed status and acquisition coverage per case, not a truth score. Requires backend support: a coverage field on the case-list DTO; CaseListItem has none today. · frame 1 of 1
4 — Observed totals — row counts only; no confidence, health or trend claim. · frame 1 of 1
5 — Recent grouped runs — recorded status and coverage across cases. Requires backend support: a cross-case runs read; every runs endpoint is case-scoped today. · frame 1 of 1
6 — Navigation entry points — monitoring and AI info are readers, not control planes. · frame 1 of 1

### dashboard-mobile.svg

[Open SVG](20261123-product-wireframes/dashboard-mobile.svg) · screen · mobile · Dashboard — case portfolio · frame 1 of 2 · route `/dashboard`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Dashboard — case portfolio header — title, synthetic context and available actions.
3 — Case portfolio — observed status and acquisition coverage per case, not a truth score. Requires backend support: a coverage field on the case-list DTO; CaseListItem has none today. · frame 1 of 2

### dashboard-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/dashboard-mobile-part-2.svg) · screen · mobile · Dashboard — case portfolio · frame 2 of 2 · route `/dashboard`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Dashboard — case portfolio — frame 2 of 2; full coverage continues in the named companion frame.
3 — Observed totals — row counts only; no confidence, health or trend claim. · frame 2 of 2
4 — Recent grouped runs — recorded status and coverage across cases. Requires backend support: a cross-case runs read; every runs endpoint is case-scoped today. · frame 2 of 2
5 — Navigation entry points — monitoring and AI info are readers, not control planes. · frame 2 of 2

### case-explorer-desktop.svg

[Open SVG](20261123-product-wireframes/case-explorer-desktop.svg) · screen · desktop · Case explorer · route `/cases`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Case explorer header — title, synthetic context and available actions.
3 — Case filters — literal query, status and sort; no hidden full-text index is claimed. · frame 1 of 1
4 — Case table — per-case observed status, coverage and update time. · frame 1 of 1
5 — Pagination — disabled Previous on the first page; no synthetic totals. · frame 1 of 1

### case-explorer-tablet.svg

[Open SVG](20261123-product-wireframes/case-explorer-tablet.svg) · screen · tablet · Case explorer · route `/cases`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Case explorer header — title, synthetic context and available actions.
3 — Case filters — literal query, status and sort; no hidden full-text index is claimed. · frame 1 of 1
4 — Case table — per-case observed status, coverage and update time. · frame 1 of 1
5 — Pagination — disabled Previous on the first page; no synthetic totals. · frame 1 of 1

### case-explorer-mobile.svg

[Open SVG](20261123-product-wireframes/case-explorer-mobile.svg) · screen · mobile · Case explorer · frame 1 of 3 · route `/cases`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Case explorer header — title, synthetic context and available actions.
3 — Case filters — literal query, status and sort; no hidden full-text index is claimed. · frame 1 of 3

### case-explorer-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/case-explorer-mobile-part-2.svg) · screen · mobile · Case explorer · frame 2 of 3 · route `/cases`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Case explorer — frame 2 of 3; full coverage continues in the named companion frame.
3 — Case table — per-case observed status, coverage and update time. · frame 2 of 3

### case-explorer-mobile-part-3.svg

[Open SVG](20261123-product-wireframes/case-explorer-mobile-part-3.svg) · screen · mobile · Case explorer · frame 3 of 3 · route `/cases`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Case explorer — frame 3 of 3; full coverage continues in the named companion frame.
3 — Pagination — disabled Previous on the first page; no synthetic totals. · frame 3 of 3

### operator-launch-desktop.svg

[Open SVG](20261123-product-wireframes/operator-launch-desktop.svg) · screen · desktop · Operator launch guide · route `/cases/new`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Operator launch guide header — title, synthetic context and available actions.
3 — Launch steps — the only ingestion path is a local CLI command, not this page. · frame 1 of 1
4 — Prerequisites — local database, single writer, operator-run network access. · frame 1 of 1
5 — Scope note — the browser exposes reads and three narrow review POSTs only. · frame 1 of 1

### operator-launch-tablet.svg

[Open SVG](20261123-product-wireframes/operator-launch-tablet.svg) · screen · tablet · Operator launch guide · route `/cases/new`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Operator launch guide header — title, synthetic context and available actions.
3 — Launch steps — the only ingestion path is a local CLI command, not this page. · frame 1 of 1
4 — Prerequisites — local database, single writer, operator-run network access. · frame 1 of 1
5 — Scope note — the browser exposes reads and three narrow review POSTs only. · frame 1 of 1

### operator-launch-mobile.svg

[Open SVG](20261123-product-wireframes/operator-launch-mobile.svg) · screen · mobile · Operator launch guide · frame 1 of 2 · route `/cases/new`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Operator launch guide header — title, synthetic context and available actions.
3 — Launch steps — the only ingestion path is a local CLI command, not this page. · frame 1 of 2
4 — Prerequisites — local database, single writer, operator-run network access. · frame 1 of 2

### operator-launch-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/operator-launch-mobile-part-2.svg) · screen · mobile · Operator launch guide · frame 2 of 2 · route `/cases/new`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Operator launch guide — frame 2 of 2; full coverage continues in the named companion frame.
3 — Scope note — the browser exposes reads and three narrow review POSTs only. · frame 2 of 2

### case-overview-desktop.svg

[Open SVG](20261123-product-wireframes/case-overview-desktop.svg) · screen · desktop · Case overview · route `/cases/:id/`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Case overview header — title, synthetic context and available actions.
3 — Case tabs (12) — active Overview; tabs are navigation, not state changes.
4 — Observed counts — only observed rows; a failed read is unavailable, never zero. · frame 1 of 1
5 — Case status — review readiness, stage and automation; claim verification states are separate per claim. · frame 1 of 1
6 — Review decision — rationale plus Approve, Action Required or Reject; no extra decision dropdown. · frame 1 of 1

### case-overview-tablet.svg

[Open SVG](20261123-product-wireframes/case-overview-tablet.svg) · screen · tablet · Case overview · route `/cases/:id/`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Case overview header — title, synthetic context and available actions.
3 — Case tabs (12) — active Overview; tabs are navigation, not state changes.
4 — Observed counts — only observed rows; a failed read is unavailable, never zero. · frame 1 of 1
5 — Case status — review readiness, stage and automation; claim verification states are separate per claim. · frame 1 of 1
6 — Review decision — rationale plus Approve, Action Required or Reject; no extra decision dropdown. · frame 1 of 1

### case-overview-mobile.svg

[Open SVG](20261123-product-wireframes/case-overview-mobile.svg) · screen · mobile · Case overview · frame 1 of 2 · route `/cases/:id/`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Case overview header — title, synthetic context and available actions.
3 — Case tabs (12) — active Overview; the strip scrolls, no tab is removed.
4 — Observed counts — only observed rows; a failed read is unavailable, never zero. · frame 1 of 2

### case-overview-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/case-overview-mobile-part-2.svg) · screen · mobile · Case overview · frame 2 of 2 · route `/cases/:id/`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Case overview — frame 2 of 2; full coverage continues in the named companion frame.
3 — Case status — review readiness, stage and automation; claim verification states are separate per claim. · frame 2 of 2
4 — Review decision — rationale plus Approve, Action Required or Reject; no extra decision dropdown. · frame 2 of 2

### review-annotation-desktop.svg

[Open SVG](20261123-product-wireframes/review-annotation-desktop.svg) · screen · desktop · Review and annotation · route `/cases/:id/`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Review and annotation header — title, synthetic context and available actions.
3 — Case tabs (12) — active Overview; tabs are navigation, not state changes.
4 — Review decision form — rationale plus the three decision buttons; decision value is the pressed control, not a dropdown. · frame 1 of 1
5 — Annotation form — type comment/flag/context, target case/claim/evidence/exception/narrative, target ID and content; save disabled while empty or pending. · frame 1 of 1
6 — Recorded annotations — stored rows with type and target; no attribution beyond the stored record. · frame 1 of 1
7 — Reader-rule note — the annotation POST is an explicit, labelled exception to the GET-only reader rule. · frame 1 of 1

### review-annotation-tablet.svg

[Open SVG](20261123-product-wireframes/review-annotation-tablet.svg) · screen · tablet · Review and annotation · frame 1 of 2 · route `/cases/:id/`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Review and annotation header — title, synthetic context and available actions.
3 — Case tabs (12) — active Overview; tabs are navigation, not state changes.
4 — Review decision form — rationale plus the three decision buttons; decision value is the pressed control, not a dropdown. · frame 1 of 2
5 — Annotation form — type comment/flag/context, target case/claim/evidence/exception/narrative, target ID and content; save disabled while empty or pending. · frame 1 of 2
6 — Recorded annotations — stored rows with type and target; no attribution beyond the stored record. · frame 1 of 2

### review-annotation-tablet-part-2.svg

[Open SVG](20261123-product-wireframes/review-annotation-tablet-part-2.svg) · screen · tablet · Review and annotation · frame 2 of 2 · route `/cases/:id/`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Review and annotation — frame 2 of 2; full coverage continues in the named companion frame.
3 — Reader-rule note — the annotation POST is an explicit, labelled exception to the GET-only reader rule. · frame 2 of 2

### review-annotation-mobile.svg

[Open SVG](20261123-product-wireframes/review-annotation-mobile.svg) · screen · mobile · Review and annotation · frame 1 of 3 · route `/cases/:id/`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Review and annotation header — title, synthetic context and available actions.
3 — Case tabs (12) — active Overview; the strip scrolls, no tab is removed.
4 — Review decision form — rationale plus the three decision buttons; decision value is the pressed control, not a dropdown. · frame 1 of 3

### review-annotation-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/review-annotation-mobile-part-2.svg) · screen · mobile · Review and annotation · frame 2 of 3 · route `/cases/:id/`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Review and annotation — frame 2 of 3; full coverage continues in the named companion frame.
3 — Annotation form — type comment/flag/context, target case/claim/evidence/exception/narrative, target ID and content; save disabled while empty or pending. · frame 2 of 3
4 — Recorded annotations — stored rows with type and target; no attribution beyond the stored record. · frame 2 of 3

### review-annotation-mobile-part-3.svg

[Open SVG](20261123-product-wireframes/review-annotation-mobile-part-3.svg) · screen · mobile · Review and annotation · frame 3 of 3 · route `/cases/:id/`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Review and annotation — frame 3 of 3; full coverage continues in the named companion frame.
3 — Reader-rule note — the annotation POST is an explicit, labelled exception to the GET-only reader rule. · frame 3 of 3

### evidence-gallery-desktop.svg

[Open SVG](20261123-product-wireframes/evidence-gallery-desktop.svg) · screen · desktop · Evidence gallery · frame 1 of 2 · route `/cases/:id/evidence`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Evidence gallery header — title, synthetic context and available actions.
3 — Case tabs (12) — active Evidence; tabs are navigation, not state changes.
4 — Evidence filters — All/High/Medium/Low/Unknown are provided extraction tiers, not truth levels. · frame 1 of 2
5 — Evidence table — source, publisher and provided tier; missing capture says unavailable. · frame 1 of 2

### evidence-gallery-desktop-part-2.svg

[Open SVG](20261123-product-wireframes/evidence-gallery-desktop-part-2.svg) · screen · desktop · Evidence gallery · frame 2 of 2 · route `/cases/:id/evidence`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Evidence gallery — frame 2 of 2; full coverage continues in the named companion frame.
3 — Selected source pane — title, capture pointer, provided tier and stored verification metadata labelled model/legacy_unknown; never certified truth. · frame 2 of 2
4 — Selected-source actions — Inspect source, safe HTTP(S) Open source and Verification details. · frame 2 of 2
5 — Pagination — filter and page state is URL-persisted; no synthetic total. · frame 2 of 2

### evidence-gallery-tablet.svg

[Open SVG](20261123-product-wireframes/evidence-gallery-tablet.svg) · screen · tablet · Evidence gallery · frame 1 of 2 · route `/cases/:id/evidence`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Evidence gallery header — title, synthetic context and available actions.
3 — Case tabs (12) — active Evidence; tabs are navigation, not state changes.
4 — Evidence filters — All/High/Medium/Low/Unknown are provided extraction tiers, not truth levels. · frame 1 of 2
5 — Evidence table — source, publisher and provided tier; missing capture says unavailable. · frame 1 of 2
6 — Selected source pane — title, capture pointer, provided tier and stored verification metadata labelled model/legacy_unknown; never certified truth. · frame 1 of 2
7 — Selected-source actions — Inspect source, safe HTTP(S) Open source and Verification details. · frame 1 of 2

### evidence-gallery-tablet-part-2.svg

[Open SVG](20261123-product-wireframes/evidence-gallery-tablet-part-2.svg) · screen · tablet · Evidence gallery · frame 2 of 2 · route `/cases/:id/evidence`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Evidence gallery — frame 2 of 2; full coverage continues in the named companion frame.
3 — Pagination — filter and page state is URL-persisted; no synthetic total. · frame 2 of 2

### evidence-gallery-mobile.svg

[Open SVG](20261123-product-wireframes/evidence-gallery-mobile.svg) · screen · mobile · Evidence gallery · frame 1 of 3 · route `/cases/:id/evidence`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Evidence gallery header — title, synthetic context and available actions.
3 — Case tabs (12) — active Evidence; the strip scrolls, no tab is removed.
4 — Evidence filters — All/High/Medium/Low/Unknown are provided extraction tiers, not truth levels. · frame 1 of 3

### evidence-gallery-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/evidence-gallery-mobile-part-2.svg) · screen · mobile · Evidence gallery · frame 2 of 3 · route `/cases/:id/evidence`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Evidence gallery — frame 2 of 3; full coverage continues in the named companion frame.
3 — Evidence table — source, publisher and provided tier; missing capture says unavailable. · frame 2 of 3

### evidence-gallery-mobile-part-3.svg

[Open SVG](20261123-product-wireframes/evidence-gallery-mobile-part-3.svg) · screen · mobile · Evidence gallery · frame 3 of 3 · route `/cases/:id/evidence`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Evidence gallery — frame 3 of 3; full coverage continues in the named companion frame.
3 — Selected source pane — title, capture pointer, provided tier and stored verification metadata labelled model/legacy_unknown; never certified truth. · frame 3 of 3
4 — Selected-source actions — Inspect source, safe HTTP(S) Open source and Verification details. · frame 3 of 3
5 — Pagination — filter and page state is URL-persisted; no synthetic total. · frame 3 of 3

### claims-desktop.svg

[Open SVG](20261123-product-wireframes/claims-desktop.svg) · screen · desktop · Claims · route `/cases/:id/claims`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Claims header — title, synthetic context and available actions.
3 — Case tabs (12) — active Claims; tabs are navigation, not state changes.
4 — Claims list — cluster text, linked source count and alignment state; generated relations are reported_by or uncertain. · frame 1 of 1
5 — Selected claim detail — frozen citation reference, effective relation and assessment provenance. · frame 1 of 1
6 — Claim actions — Inspect evidence opens the inspector; Open frozen citation opens the immutable citation reader. · frame 1 of 1
7 — Expanded claim detail — model-labelled Arbiter classification, rationale and recorded for/against/neutral party positions; consensus is not truth. · frame 1 of 1
8 — Detail provenance — model origin stays visible and the frozen citation links to the inspector. · frame 1 of 1

### claims-tablet.svg

[Open SVG](20261123-product-wireframes/claims-tablet.svg) · screen · tablet · Claims · frame 1 of 2 · route `/cases/:id/claims`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Claims header — title, synthetic context and available actions.
3 — Case tabs (12) — active Claims; tabs are navigation, not state changes.
4 — Claims list — cluster text, linked source count and alignment state; generated relations are reported_by or uncertain. · frame 1 of 2
5 — Selected claim detail — frozen citation reference, effective relation and assessment provenance. · frame 1 of 2
6 — Claim actions — Inspect evidence opens the inspector; Open frozen citation opens the immutable citation reader. · frame 1 of 2
7 — Expanded claim detail — model-labelled Arbiter classification, rationale and recorded for/against/neutral party positions; consensus is not truth. · frame 1 of 2

### claims-tablet-part-2.svg

[Open SVG](20261123-product-wireframes/claims-tablet-part-2.svg) · screen · tablet · Claims · frame 2 of 2 · route `/cases/:id/claims`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Claims — frame 2 of 2; full coverage continues in the named companion frame.
3 — Detail provenance — model origin stays visible and the frozen citation links to the inspector. · frame 2 of 2

### claims-mobile.svg

[Open SVG](20261123-product-wireframes/claims-mobile.svg) · screen · mobile · Claims · frame 1 of 3 · route `/cases/:id/claims`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Claims header — title, synthetic context and available actions.
3 — Case tabs (12) — active Claims; the strip scrolls, no tab is removed.
4 — Claims list — cluster text, linked source count and alignment state; generated relations are reported_by or uncertain. · frame 1 of 3

### claims-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/claims-mobile-part-2.svg) · screen · mobile · Claims · frame 2 of 3 · route `/cases/:id/claims`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Claims — frame 2 of 3; full coverage continues in the named companion frame.
3 — Selected claim detail — frozen citation reference, effective relation and assessment provenance. · frame 2 of 3
4 — Claim actions — Inspect evidence opens the inspector; Open frozen citation opens the immutable citation reader. · frame 2 of 3
5 — Expanded claim detail — model-labelled Arbiter classification, rationale and recorded for/against/neutral party positions; consensus is not truth. · frame 2 of 3

### claims-mobile-part-3.svg

[Open SVG](20261123-product-wireframes/claims-mobile-part-3.svg) · screen · mobile · Claims · frame 3 of 3 · route `/cases/:id/claims`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Claims — frame 3 of 3; full coverage continues in the named companion frame.
3 — Detail provenance — model origin stays visible and the frozen citation links to the inspector. · frame 3 of 3

### capture-inspector-desktop.svg

[Open SVG](20261123-product-wireframes/capture-inspector-desktop.svg) · screen · desktop · Capture inspector · route `/cases/:id/evidence?claim=&evidence=&capture=`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Capture inspector header — title, synthetic context and available actions.
3 — Case tabs (12) — active Evidence; tabs are navigation, not state changes.
4 — Claim and immutable citation — frozen claim text, relationship and model assessment provenance. · frame 1 of 1
5 — Capture metadata — publisher host, observation and recording times, hash, published-unavailable and recorded extraction scope. · frame 1 of 1
6 — Synthetic passage block — grey box stands for captured text; labelled mock example, so no validated code-point range is claimed. · frame 1 of 1
7 — Capture version selector and Open source control — an actual field plus a safe HTTP(S) link control; both are visible, not prose only. · frame 1 of 1
8 — Provenance — provisional publisher host, unknown independence and both source URLs. · frame 1 of 1
9 — Reader notes — quotation validation rules and the synthetic-passage limitation. · frame 1 of 1

### capture-inspector-tablet.svg

[Open SVG](20261123-product-wireframes/capture-inspector-tablet.svg) · screen · tablet · Capture inspector · frame 1 of 2 · route `/cases/:id/evidence?claim=&evidence=&capture=`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Capture inspector header — title, synthetic context and available actions.
3 — Case tabs (12) — active Evidence; tabs are navigation, not state changes.
4 — Claim and immutable citation — frozen claim text, relationship and model assessment provenance. · frame 1 of 2
5 — Capture metadata — publisher host, observation and recording times, hash, published-unavailable and recorded extraction scope. · frame 1 of 2
6 — Synthetic passage block — grey box stands for captured text; labelled mock example, so no validated code-point range is claimed. · frame 1 of 2
7 — Capture version selector and Open source control — an actual field plus a safe HTTP(S) link control; both are visible, not prose only. · frame 1 of 2

### capture-inspector-tablet-part-2.svg

[Open SVG](20261123-product-wireframes/capture-inspector-tablet-part-2.svg) · screen · tablet · Capture inspector · frame 2 of 2 · route `/cases/:id/evidence?claim=&evidence=&capture=`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Capture inspector — frame 2 of 2; full coverage continues in the named companion frame.
3 — Provenance — provisional publisher host, unknown independence and both source URLs. · frame 2 of 2
4 — Reader notes — quotation validation rules and the synthetic-passage limitation. · frame 2 of 2

### capture-inspector-mobile.svg

[Open SVG](20261123-product-wireframes/capture-inspector-mobile.svg) · screen · mobile · Capture inspector · frame 1 of 3 · route `/cases/:id/evidence?claim=&evidence=&capture=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Capture inspector header — title, synthetic context and available actions.
3 — Case tabs (12) — active Evidence; the strip scrolls, no tab is removed.
4 — Claim and immutable citation — frozen claim text, relationship and model assessment provenance. · frame 1 of 3
5 — Capture metadata — publisher host, observation and recording times, hash, published-unavailable and recorded extraction scope. · frame 1 of 3

### capture-inspector-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/capture-inspector-mobile-part-2.svg) · screen · mobile · Capture inspector · frame 2 of 3 · route `/cases/:id/evidence?claim=&evidence=&capture=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Capture inspector — frame 2 of 3; full coverage continues in the named companion frame.
3 — Synthetic passage block — grey box stands for captured text; labelled mock example, so no validated code-point range is claimed. · frame 2 of 3
4 — Capture version selector and Open source control — an actual field plus a safe HTTP(S) link control; both are visible, not prose only. · frame 2 of 3

### capture-inspector-mobile-part-3.svg

[Open SVG](20261123-product-wireframes/capture-inspector-mobile-part-3.svg) · screen · mobile · Capture inspector · frame 3 of 3 · route `/cases/:id/evidence?claim=&evidence=&capture=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Capture inspector — frame 3 of 3; full coverage continues in the named companion frame.
3 — Provenance — provisional publisher host, unknown independence and both source URLs. · frame 3 of 3
4 — Reader notes — quotation validation rules and the synthetic-passage limitation. · frame 3 of 3

### comparison-desktop.svg

[Open SVG](20261123-product-wireframes/comparison-desktop.svg) · screen · desktop · Comparison · frame 1 of 2 · route `/cases/:id/compare?left=&right=&leftCapture=&rightCapture=`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Comparison header — title, synthetic context and available actions.
3 — Case tabs (12) — active Compare; tabs are navigation, not state changes.
4 — Selection controls — four visible fields (left/right source and capture) plus Compare, Swap and Clear; selections stay in the URL. · frame 1 of 2
5 — Left source panel — its own capture time, hash and Open passage navigation. · frame 1 of 2
6 — Right source panel — its own capture time, hash and Open passage navigation; desktop side by side, tablet and mobile stack. · frame 1 of 2

### comparison-desktop-part-2.svg

[Open SVG](20261123-product-wireframes/comparison-desktop-part-2.svg) · screen · desktop · Comparison · frame 2 of 2 · route `/cases/:id/compare?left=&right=&leftCapture=&rightCapture=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Comparison — frame 2 of 2; full coverage continues in the named companion frame.
3 — Alignment rows — explicit 'Reported in both extractions' and 'Extracted only on left/right' labels, never omission or disagreement. · frame 2 of 2
4 — Dependency warning — detected copy edge reasons; never presented as corroboration or independence. · frame 2 of 2
5 — Pagination controls — actual previous/next controls; offset stays in the URL. · frame 2 of 2

### comparison-tablet.svg

[Open SVG](20261123-product-wireframes/comparison-tablet.svg) · screen · tablet · Comparison · frame 1 of 2 · route `/cases/:id/compare?left=&right=&leftCapture=&rightCapture=`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Comparison header — title, synthetic context and available actions.
3 — Case tabs (12) — active Compare; tabs are navigation, not state changes.
4 — Selection controls — four visible fields (left/right source and capture) plus Compare, Swap and Clear; selections stay in the URL. · frame 1 of 2
5 — Left source panel — its own capture time, hash and Open passage navigation. · frame 1 of 2
6 — Right source panel — its own capture time, hash and Open passage navigation; desktop side by side, tablet and mobile stack. · frame 1 of 2

### comparison-tablet-part-2.svg

[Open SVG](20261123-product-wireframes/comparison-tablet-part-2.svg) · screen · tablet · Comparison · frame 2 of 2 · route `/cases/:id/compare?left=&right=&leftCapture=&rightCapture=`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Comparison — frame 2 of 2; full coverage continues in the named companion frame.
3 — Alignment rows — explicit 'Reported in both extractions' and 'Extracted only on left/right' labels, never omission or disagreement. · frame 2 of 2
4 — Dependency warning — detected copy edge reasons; never presented as corroboration or independence. · frame 2 of 2
5 — Pagination controls — actual previous/next controls; offset stays in the URL. · frame 2 of 2

### comparison-mobile.svg

[Open SVG](20261123-product-wireframes/comparison-mobile.svg) · screen · mobile · Comparison · frame 1 of 4 · route `/cases/:id/compare?left=&right=&leftCapture=&rightCapture=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Comparison header — title, synthetic context and available actions.
3 — Case tabs (12) — active Compare; the strip scrolls, no tab is removed.
4 — Selection controls — four visible fields (left/right source and capture) plus Compare, Swap and Clear; selections stay in the URL. · frame 1 of 4

### comparison-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/comparison-mobile-part-2.svg) · screen · mobile · Comparison · frame 2 of 4 · route `/cases/:id/compare?left=&right=&leftCapture=&rightCapture=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Comparison — frame 2 of 4; full coverage continues in the named companion frame.
3 — Left source panel — its own capture time, hash and Open passage navigation. · frame 2 of 4
4 — Right source panel — its own capture time, hash and Open passage navigation; desktop side by side, tablet and mobile stack. · frame 2 of 4

### comparison-mobile-part-3.svg

[Open SVG](20261123-product-wireframes/comparison-mobile-part-3.svg) · screen · mobile · Comparison · frame 3 of 4 · route `/cases/:id/compare?left=&right=&leftCapture=&rightCapture=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Comparison — frame 3 of 4; full coverage continues in the named companion frame.
3 — Alignment rows — explicit 'Reported in both extractions' and 'Extracted only on left/right' labels, never omission or disagreement. · frame 3 of 4
4 — Dependency warning — detected copy edge reasons; never presented as corroboration or independence. · frame 3 of 4

### comparison-mobile-part-4.svg

[Open SVG](20261123-product-wireframes/comparison-mobile-part-4.svg) · screen · mobile · Comparison · frame 4 of 4 · route `/cases/:id/compare?left=&right=&leftCapture=&rightCapture=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Comparison — frame 4 of 4; full coverage continues in the named companion frame.
3 — Pagination controls — actual previous/next controls; offset stays in the URL. · frame 4 of 4

### source-provenance-desktop.svg

[Open SVG](20261123-product-wireframes/source-provenance-desktop.svg) · screen · desktop · Source provenance · route `/cases/:id/sources`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Source provenance header — title, synthetic context and available actions.
3 — Case tabs (12) — active Evidence; tabs are navigation, not state changes.
4 — Dependency groups — connected components with method and status; a singleton group has no detected edge. · frame 1 of 1
5 — Group detail — the copy edge is labelled dependency_detected and explicitly not independent; groups without an edge stay unknown. · frame 1 of 1
6 — Coverage limits — v1 detection scope, disclosed rather than implied. · frame 1 of 1

### source-provenance-tablet.svg

[Open SVG](20261123-product-wireframes/source-provenance-tablet.svg) · screen · tablet · Source provenance · route `/cases/:id/sources`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Source provenance header — title, synthetic context and available actions.
3 — Case tabs (12) — active Evidence; tabs are navigation, not state changes.
4 — Dependency groups — connected components with method and status; a singleton group has no detected edge. · frame 1 of 1
5 — Group detail — the copy edge is labelled dependency_detected and explicitly not independent; groups without an edge stay unknown. · frame 1 of 1
6 — Coverage limits — v1 detection scope, disclosed rather than implied. · frame 1 of 1

### source-provenance-mobile.svg

[Open SVG](20261123-product-wireframes/source-provenance-mobile.svg) · screen · mobile · Source provenance · frame 1 of 2 · route `/cases/:id/sources`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Source provenance header — title, synthetic context and available actions.
3 — Case tabs (12) — active Evidence; the strip scrolls, no tab is removed.
4 — Dependency groups — connected components with method and status; a singleton group has no detected edge. · frame 1 of 2

### source-provenance-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/source-provenance-mobile-part-2.svg) · screen · mobile · Source provenance · frame 2 of 2 · route `/cases/:id/sources`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Source provenance — frame 2 of 2; full coverage continues in the named companion frame.
3 — Group detail — the copy edge is labelled dependency_detected and explicitly not independent; groups without an edge stay unknown. · frame 2 of 2
4 — Coverage limits — v1 detection scope, disclosed rather than implied. · frame 2 of 2

### runs-changes-desktop.svg

[Open SVG](20261123-product-wireframes/runs-changes-desktop.svg) · screen · desktop · Runs and changes · frame 1 of 2 · route `/cases/:id/changes?run=&offset=`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Runs and changes header — title, synthetic context and available actions.
3 — Case tabs (12) — active Changes; tabs are navigation, not state changes.
4 — Grouped run selector — an actual selector field listing run-0007 (run-0006 selectable), plus Refresh and Permalink; the selection is pinned in the URL. · frame 1 of 2
5 — Baseline and target snapshot ids with the coverage warning. · frame 1 of 2
6 — Run semantics — pending, failed and attribution rules stated next to the selector. · frame 1 of 2
7 — Typed before/after rows — review_state_changed carries the case review state, not a claim verification state. · frame 1 of 2

### runs-changes-desktop-part-2.svg

[Open SVG](20261123-product-wireframes/runs-changes-desktop-part-2.svg) · screen · desktop · Runs and changes · frame 2 of 2 · route `/cases/:id/changes?run=&offset=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Runs and changes — frame 2 of 2; full coverage continues in the named companion frame.
3 — Per-item run facts — origin run and observer run as separate recorded values; neither implies who caused a change. · frame 2 of 2
4 — Delta pagination — offset lives in the URL; the selected run stays pinned. · frame 2 of 2

### runs-changes-tablet.svg

[Open SVG](20261123-product-wireframes/runs-changes-tablet.svg) · screen · tablet · Runs and changes · frame 1 of 2 · route `/cases/:id/changes?run=&offset=`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Runs and changes header — title, synthetic context and available actions.
3 — Case tabs (12) — active Changes; tabs are navigation, not state changes.
4 — Grouped run selector — an actual selector field listing run-0007 (run-0006 selectable), plus Refresh and Permalink; the selection is pinned in the URL. · frame 1 of 2
5 — Baseline and target snapshot ids with the coverage warning. · frame 1 of 2
6 — Run semantics — pending, failed and attribution rules stated next to the selector. · frame 1 of 2

### runs-changes-tablet-part-2.svg

[Open SVG](20261123-product-wireframes/runs-changes-tablet-part-2.svg) · screen · tablet · Runs and changes · frame 2 of 2 · route `/cases/:id/changes?run=&offset=`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Runs and changes — frame 2 of 2; full coverage continues in the named companion frame.
3 — Typed before/after rows — review_state_changed carries the case review state, not a claim verification state. · frame 2 of 2
4 — Per-item run facts — origin run and observer run as separate recorded values; neither implies who caused a change. · frame 2 of 2
5 — Delta pagination — offset lives in the URL; the selected run stays pinned. · frame 2 of 2

### runs-changes-mobile.svg

[Open SVG](20261123-product-wireframes/runs-changes-mobile.svg) · screen · mobile · Runs and changes · frame 1 of 4 · route `/cases/:id/changes?run=&offset=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Runs and changes header — title, synthetic context and available actions.
3 — Case tabs (12) — active Changes; the strip scrolls, no tab is removed.
4 — Grouped run selector — an actual selector field listing run-0007 (run-0006 selectable), plus Refresh and Permalink; the selection is pinned in the URL. · frame 1 of 4
5 — Baseline and target snapshot ids with the coverage warning. · frame 1 of 4

### runs-changes-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/runs-changes-mobile-part-2.svg) · screen · mobile · Runs and changes · frame 2 of 4 · route `/cases/:id/changes?run=&offset=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Runs and changes — frame 2 of 4; full coverage continues in the named companion frame.
3 — Run semantics — pending, failed and attribution rules stated next to the selector. · frame 2 of 4

### runs-changes-mobile-part-3.svg

[Open SVG](20261123-product-wireframes/runs-changes-mobile-part-3.svg) · screen · mobile · Runs and changes · frame 3 of 4 · route `/cases/:id/changes?run=&offset=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Runs and changes — frame 3 of 4; full coverage continues in the named companion frame.
3 — Typed before/after rows — review_state_changed carries the case review state, not a claim verification state. · frame 3 of 4

### runs-changes-mobile-part-4.svg

[Open SVG](20261123-product-wireframes/runs-changes-mobile-part-4.svg) · screen · mobile · Runs and changes · frame 4 of 4 · route `/cases/:id/changes?run=&offset=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Runs and changes — frame 4 of 4; full coverage continues in the named companion frame.
3 — Per-item run facts — origin run and observer run as separate recorded values; neither implies who caused a change. · frame 4 of 4
4 — Delta pagination — offset lives in the URL; the selected run stays pinned. · frame 4 of 4

### historical-snapshot-desktop.svg

[Open SVG](20261123-product-wireframes/historical-snapshot-desktop.svg) · screen · desktop · Historical snapshot · route `/cases/:id/changes?run=&claim=&snapshot=`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Historical snapshot header — title, synthetic context and available actions.
3 — Snapshot metadata — frozen identifiers, versions and creation time. · frame 1 of 1
4 — Frozen claim — claim text from the baseline snapshot, retrieved by immutable reference. · frame 1 of 1
5 — Immutable passage — frozen quotation range and its capture; no latest-capture substitution. · frame 1 of 1
6 — Live-state note — distinguishes gone/rewritten from unchanged without attribution. · frame 1 of 1

### historical-snapshot-tablet.svg

[Open SVG](20261123-product-wireframes/historical-snapshot-tablet.svg) · screen · tablet · Historical snapshot · route `/cases/:id/changes?run=&claim=&snapshot=`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Historical snapshot header — title, synthetic context and available actions.
3 — Snapshot metadata — frozen identifiers, versions and creation time. · frame 1 of 1
4 — Frozen claim — claim text from the baseline snapshot, retrieved by immutable reference. · frame 1 of 1
5 — Immutable passage — frozen quotation range and its capture; no latest-capture substitution. · frame 1 of 1
6 — Live-state note — distinguishes gone/rewritten from unchanged without attribution. · frame 1 of 1

### historical-snapshot-mobile.svg

[Open SVG](20261123-product-wireframes/historical-snapshot-mobile.svg) · screen · mobile · Historical snapshot · frame 1 of 2 · route `/cases/:id/changes?run=&claim=&snapshot=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Historical snapshot header — title, synthetic context and available actions.
3 — Snapshot metadata — frozen identifiers, versions and creation time. · frame 1 of 2
4 — Frozen claim — claim text from the baseline snapshot, retrieved by immutable reference. · frame 1 of 2
5 — Immutable passage — frozen quotation range and its capture; no latest-capture substitution. · frame 1 of 2

### historical-snapshot-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/historical-snapshot-mobile-part-2.svg) · screen · mobile · Historical snapshot · frame 2 of 2 · route `/cases/:id/changes?run=&claim=&snapshot=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Historical snapshot — frame 2 of 2; full coverage continues in the named companion frame.
3 — Live-state note — distinguishes gone/rewritten from unchanged without attribution. · frame 2 of 2

### search-desktop.svg

[Open SVG](20261123-product-wireframes/search-desktop.svg) · screen · desktop · Case search · frame 1 of 2 · route `/cases/:id/search?q=&type=&offset=`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Case search header — title, synthetic context and available actions.
3 — Case tabs (12) — active Search; tabs are navigation, not state changes.
4 — Search filters — six visible fields: literal all-term query, type All/claim/evidence, publisher, claim status, and UTC published-from/before (before is end-exclusive). · frame 1 of 2

### search-desktop-part-2.svg

[Open SVG](20261123-product-wireframes/search-desktop-part-2.svg) · screen · desktop · Case search · frame 2 of 2 · route `/cases/:id/search?q=&type=&offset=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Case search — frame 2 of 2; full coverage continues in the named companion frame.
3 — Results — plain-text mock snippets with the matched field; each row has Open result navigation. Snippets never imply a validated quotation. · frame 2 of 2
4 — Pagination and permalink controls — result count and offset are shown with the results; offset is URL-persisted. · frame 2 of 2

### search-tablet.svg

[Open SVG](20261123-product-wireframes/search-tablet.svg) · screen · tablet · Case search · frame 1 of 2 · route `/cases/:id/search?q=&type=&offset=`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Case search header — title, synthetic context and available actions.
3 — Case tabs (12) — active Search; tabs are navigation, not state changes.
4 — Search filters — six visible fields: literal all-term query, type All/claim/evidence, publisher, claim status, and UTC published-from/before (before is end-exclusive). · frame 1 of 2
5 — Results — plain-text mock snippets with the matched field; each row has Open result navigation. Snippets never imply a validated quotation. · frame 1 of 2

### search-tablet-part-2.svg

[Open SVG](20261123-product-wireframes/search-tablet-part-2.svg) · screen · tablet · Case search · frame 2 of 2 · route `/cases/:id/search?q=&type=&offset=`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Case search — frame 2 of 2; full coverage continues in the named companion frame.
3 — Pagination and permalink controls — result count and offset are shown with the results; offset is URL-persisted. · frame 2 of 2

### search-mobile.svg

[Open SVG](20261123-product-wireframes/search-mobile.svg) · screen · mobile · Case search · frame 1 of 2 · route `/cases/:id/search?q=&type=&offset=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Case search header — title, synthetic context and available actions.
3 — Case tabs (12) — active Search; the strip scrolls, no tab is removed.
4 — Search filters — six visible fields: literal all-term query, type All/claim/evidence, publisher, claim status, and UTC published-from/before (before is end-exclusive). · frame 1 of 2

### search-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/search-mobile-part-2.svg) · screen · mobile · Case search · frame 2 of 2 · route `/cases/:id/search?q=&type=&offset=`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Case search — frame 2 of 2; full coverage continues in the named companion frame.
3 — Results — plain-text mock snippets with the matched field; each row has Open result navigation. Snippets never imply a validated quotation. · frame 2 of 2
4 — Pagination and permalink controls — result count and offset are shown with the results; offset is URL-persisted. · frame 2 of 2

### stage-history-desktop.svg

[Open SVG](20261123-product-wireframes/stage-history-desktop.svg) · screen · desktop · Run history (stage-oriented) · route `/cases/:id/run-history`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Run history (stage-oriented) header — title, synthetic context and available actions.
3 — Case tabs (12) — active Run history; tabs are navigation, not state changes.
4 — Stage attempts — per-stage model, duration, fallback flag, status and recorded time; not grouped investigation runs. · frame 1 of 1
5 — Interpretation — this tab remains stage-oriented; grouped runs and deltas are a separate reader. · frame 1 of 1

### stage-history-tablet.svg

[Open SVG](20261123-product-wireframes/stage-history-tablet.svg) · screen · tablet · Run history (stage-oriented) · route `/cases/:id/run-history`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Run history (stage-oriented) header — title, synthetic context and available actions.
3 — Case tabs (12) — active Run history; tabs are navigation, not state changes.
4 — Stage attempts — per-stage model, duration, fallback flag, status and recorded time; not grouped investigation runs. · frame 1 of 1
5 — Interpretation — this tab remains stage-oriented; grouped runs and deltas are a separate reader. · frame 1 of 1

### stage-history-mobile.svg

[Open SVG](20261123-product-wireframes/stage-history-mobile.svg) · screen · mobile · Run history (stage-oriented) · frame 1 of 3 · route `/cases/:id/run-history`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Run history (stage-oriented) header — title, synthetic context and available actions.
3 — Case tabs (12) — active Run history; the strip scrolls, no tab is removed.
4 — Stage attempts — per-stage model, duration, fallback flag, status and recorded time; not grouped investigation runs. · frame 1 of 3

### stage-history-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/stage-history-mobile-part-2.svg) · screen · mobile · Run history (stage-oriented) · frame 2 of 3 · route `/cases/:id/run-history`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Run history (stage-oriented) — frame 2 of 3; full coverage continues in the named companion frame.
3 — Stage attempts — per-stage model, duration, fallback flag, status and recorded time; not grouped investigation runs. · frame 2 of 3

### stage-history-mobile-part-3.svg

[Open SVG](20261123-product-wireframes/stage-history-mobile-part-3.svg) · screen · mobile · Run history (stage-oriented) · frame 3 of 3 · route `/cases/:id/run-history`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Run history (stage-oriented) — frame 3 of 3; full coverage continues in the named companion frame.
3 — Stage attempts — per-stage model, duration, fallback flag, status and recorded time; not grouped investigation runs. · frame 3 of 3
4 — Interpretation — this tab remains stage-oriented; grouped runs and deltas are a separate reader. · frame 3 of 3

### pipeline-desktop.svg

[Open SVG](20261123-product-wireframes/pipeline-desktop.svg) · screen · desktop · Pipeline monitor · route `/cases/:id/pipeline`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Pipeline monitor header — title, synthetic context and available actions.
3 — Configured stages — configuration order and enabled flag; configuration is not an attempt. · frame 1 of 1
4 — Recorded attempts — only actually recorded attempts; an unrecorded stage is not a success. · frame 1 of 1

### pipeline-tablet.svg

[Open SVG](20261123-product-wireframes/pipeline-tablet.svg) · screen · tablet · Pipeline monitor · route `/cases/:id/pipeline`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Pipeline monitor header — title, synthetic context and available actions.
3 — Configured stages — configuration order and enabled flag; configuration is not an attempt. · frame 1 of 1
4 — Recorded attempts — only actually recorded attempts; an unrecorded stage is not a success. · frame 1 of 1

### pipeline-mobile.svg

[Open SVG](20261123-product-wireframes/pipeline-mobile.svg) · screen · mobile · Pipeline monitor · frame 1 of 2 · route `/cases/:id/pipeline`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Pipeline monitor header — title, synthetic context and available actions.
3 — Configured stages — configuration order and enabled flag; configuration is not an attempt. · frame 1 of 2

### pipeline-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/pipeline-mobile-part-2.svg) · screen · mobile · Pipeline monitor · frame 2 of 2 · route `/cases/:id/pipeline`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Pipeline monitor — frame 2 of 2; full coverage continues in the named companion frame.
3 — Recorded attempts — only actually recorded attempts; an unrecorded stage is not a success. · frame 2 of 2

### exception-queue-desktop.svg

[Open SVG](20261123-product-wireframes/exception-queue-desktop.svg) · screen · desktop · Exception queue · route `/cases/:id/exceptions`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Exception queue header — title, synthetic context and available actions.
3 — Case tabs (12) — active Exceptions; tabs are navigation, not state changes.
4 — Exception table — pending disables all row actions; an open row enables Resolve/Defer, a closed row enables Reopen. · frame 1 of 1
5 — Exception actions — the pending row disables Resolve, Defer and Reopen; open and closed rows enable their listed actions. · frame 1 of 1

### exception-queue-tablet.svg

[Open SVG](20261123-product-wireframes/exception-queue-tablet.svg) · screen · tablet · Exception queue · route `/cases/:id/exceptions`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Exception queue header — title, synthetic context and available actions.
3 — Case tabs (12) — active Exceptions; tabs are navigation, not state changes.
4 — Exception table — pending disables all row actions; an open row enables Resolve/Defer, a closed row enables Reopen. · frame 1 of 1
5 — Exception actions — the pending row disables Resolve, Defer and Reopen; open and closed rows enable their listed actions. · frame 1 of 1

### exception-queue-mobile.svg

[Open SVG](20261123-product-wireframes/exception-queue-mobile.svg) · screen · mobile · Exception queue · frame 1 of 2 · route `/cases/:id/exceptions`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Exception queue header — title, synthetic context and available actions.
3 — Case tabs (12) — active Exceptions; the strip scrolls, no tab is removed.
4 — Exception table — pending disables all row actions; an open row enables Resolve/Defer, a closed row enables Reopen. · frame 1 of 2

### exception-queue-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/exception-queue-mobile-part-2.svg) · screen · mobile · Exception queue · frame 2 of 2 · route `/cases/:id/exceptions`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Exception queue — frame 2 of 2; full coverage continues in the named companion frame.
3 — Exception actions — the pending row disables Resolve, Defer and Reopen; open and closed rows enable their listed actions. · frame 2 of 2

### parties-desktop.svg

[Open SVG](20261123-product-wireframes/parties-desktop.svg) · screen · desktop · Parties · route `/cases/:id/parties`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Parties header — title, synthetic context and available actions.
3 — Case tabs (12) — active Parties; tabs are navigation, not state changes.
4 — Party table — recorded, inferred or confirmed basis; counts are recorded rows, never guessed stance. · frame 1 of 1
5 — Expanded party accordion — recorded/model position, concerns, priorities, supported/contested/unique claim counts and explicit unavailable fields. · frame 1 of 1
6 — Honesty rules — recorded/model party position only; missing data is shown, never invented. · frame 1 of 1

### parties-tablet.svg

[Open SVG](20261123-product-wireframes/parties-tablet.svg) · screen · tablet · Parties · route `/cases/:id/parties`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Parties header — title, synthetic context and available actions.
3 — Case tabs (12) — active Parties; tabs are navigation, not state changes.
4 — Party table — recorded, inferred or confirmed basis; counts are recorded rows, never guessed stance. · frame 1 of 1
5 — Expanded party accordion — recorded/model position, concerns, priorities, supported/contested/unique claim counts and explicit unavailable fields. · frame 1 of 1
6 — Honesty rules — recorded/model party position only; missing data is shown, never invented. · frame 1 of 1

### parties-mobile.svg

[Open SVG](20261123-product-wireframes/parties-mobile.svg) · screen · mobile · Parties · frame 1 of 2 · route `/cases/:id/parties`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Parties header — title, synthetic context and available actions.
3 — Case tabs (12) — active Parties; the strip scrolls, no tab is removed.
4 — Party table — recorded, inferred or confirmed basis; counts are recorded rows, never guessed stance. · frame 1 of 2

### parties-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/parties-mobile-part-2.svg) · screen · mobile · Parties · frame 2 of 2 · route `/cases/:id/parties`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Parties — frame 2 of 2; full coverage continues in the named companion frame.
3 — Expanded party accordion — recorded/model position, concerns, priorities, supported/contested/unique claim counts and explicit unavailable fields. · frame 2 of 2
4 — Honesty rules — recorded/model party position only; missing data is shown, never invented. · frame 2 of 2

### geographic-map-desktop.svg

[Open SVG](20261123-product-wireframes/geographic-map-desktop.svg) · screen · desktop · Geographic map · route `/cases/:id/map`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Geographic map header — title, synthetic context and available actions.
3 — Case tabs (12) — active Map; tabs are navigation, not state changes.
4 — Map area — placeholder X and geotagged markers; no map tiles are loaded or implied. · frame 1 of 1
5 — Event list — geotagged events only; untagged events are listed as unknown place. · frame 1 of 1
6 — Place data — untagged stays unknown; the map is a placeholder, not a live basemap. · frame 1 of 1

### geographic-map-tablet.svg

[Open SVG](20261123-product-wireframes/geographic-map-tablet.svg) · screen · tablet · Geographic map · route `/cases/:id/map`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Geographic map header — title, synthetic context and available actions.
3 — Case tabs (12) — active Map; tabs are navigation, not state changes.
4 — Map area — placeholder X and geotagged markers; no map tiles are loaded or implied. · frame 1 of 1
5 — Event list — geotagged events only; untagged events are listed as unknown place. · frame 1 of 1
6 — Place data — untagged stays unknown; the map is a placeholder, not a live basemap. · frame 1 of 1

### geographic-map-mobile.svg

[Open SVG](20261123-product-wireframes/geographic-map-mobile.svg) · screen · mobile · Geographic map · frame 1 of 2 · route `/cases/:id/map`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Geographic map header — title, synthetic context and available actions.
3 — Case tabs (12) — active Map; the strip scrolls, no tab is removed.
4 — Map area — placeholder X and geotagged markers; no map tiles are loaded or implied. · frame 1 of 2
5 — Event list — geotagged events only; untagged events are listed as unknown place. · frame 1 of 2

### geographic-map-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/geographic-map-mobile-part-2.svg) · screen · mobile · Geographic map · frame 2 of 2 · route `/cases/:id/map`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Geographic map — frame 2 of 2; full coverage continues in the named companion frame.
3 — Place data — untagged stays unknown; the map is a placeholder, not a live basemap. · frame 2 of 2

### timeline-desktop.svg

[Open SVG](20261123-product-wireframes/timeline-desktop.svg) · screen · desktop · Timeline · route `/cases/:id/timeline`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Timeline header — title, synthetic context and available actions.
3 — Case tabs (12) — active Timeline; tabs are navigation, not state changes.
4 — Timeline entries — each row shows a verification state; a missing timestamp is shown as unknown and never inferred. · frame 1 of 1
5 — Verification vocabulary — the six stored states; an unexpected raw value renders as 'Unrecognized status', and an unknown date stays distinct from the state. · frame 1 of 1

### timeline-tablet.svg

[Open SVG](20261123-product-wireframes/timeline-tablet.svg) · screen · tablet · Timeline · route `/cases/:id/timeline`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Timeline header — title, synthetic context and available actions.
3 — Case tabs (12) — active Timeline; tabs are navigation, not state changes.
4 — Timeline entries — each row shows a verification state; a missing timestamp is shown as unknown and never inferred. · frame 1 of 1
5 — Verification vocabulary — the six stored states; an unexpected raw value renders as 'Unrecognized status', and an unknown date stays distinct from the state. · frame 1 of 1

### timeline-mobile.svg

[Open SVG](20261123-product-wireframes/timeline-mobile.svg) · screen · mobile · Timeline · frame 1 of 2 · route `/cases/:id/timeline`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Timeline header — title, synthetic context and available actions.
3 — Case tabs (12) — active Timeline; the strip scrolls, no tab is removed.
4 — Timeline entries — each row shows a verification state; a missing timestamp is shown as unknown and never inferred. · frame 1 of 2

### timeline-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/timeline-mobile-part-2.svg) · screen · mobile · Timeline · frame 2 of 2 · route `/cases/:id/timeline`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Timeline — frame 2 of 2; full coverage continues in the named companion frame.
3 — Verification vocabulary — the six stored states; an unexpected raw value renders as 'Unrecognized status', and an unknown date stays distinct from the state. · frame 2 of 2

### report-desktop.svg

[Open SVG](20261123-product-wireframes/report-desktop.svg) · screen · desktop · Report · route `/cases/:id/report`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Report header — title, synthetic context and available actions.
3 — Case tabs (12) — active Report; tabs are navigation, not state changes.
4 — Report pane — document preview plus Markdown/JSON downloads; a missing artifact keeps its control disabled. · frame 1 of 1
5 — Report facts — run-specific paths and formats; the report is stored, not regenerated on read. · frame 1 of 1
6 — Historical reports — report documents bind to their run and snapshot. · frame 1 of 1

### report-tablet.svg

[Open SVG](20261123-product-wireframes/report-tablet.svg) · screen · tablet · Report · route `/cases/:id/report`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Report header — title, synthetic context and available actions.
3 — Case tabs (12) — active Report; tabs are navigation, not state changes.
4 — Report pane — document preview plus Markdown/JSON downloads; a missing artifact keeps its control disabled. · frame 1 of 1
5 — Report facts — run-specific paths and formats; the report is stored, not regenerated on read. · frame 1 of 1
6 — Historical reports — report documents bind to their run and snapshot. · frame 1 of 1

### report-mobile.svg

[Open SVG](20261123-product-wireframes/report-mobile.svg) · screen · mobile · Report · frame 1 of 2 · route `/cases/:id/report`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Report header — title, synthetic context and available actions.
3 — Case tabs (12) — active Report; the strip scrolls, no tab is removed.
4 — Report pane — document preview plus Markdown/JSON downloads; a missing artifact keeps its control disabled. · frame 1 of 2
5 — Report facts — run-specific paths and formats; the report is stored, not regenerated on read. · frame 1 of 2

### report-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/report-mobile-part-2.svg) · screen · mobile · Report · frame 2 of 2 · route `/cases/:id/report`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Report — frame 2 of 2; full coverage continues in the named companion frame.
3 — Historical reports — report documents bind to their run and snapshot. · frame 2 of 2

### corroboration-network-desktop.svg

[Open SVG](20261123-product-wireframes/corroboration-network-desktop.svg) · screen · desktop · Corroboration network · route `/cases/:id/network`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Corroboration network header — title, synthetic context and available actions.
3 — Claim and source graph — rect nodes and line edges; a shared edge is not independent proof. · frame 1 of 1
4 — Adversarial investigation flow — Collector, classifier, investigators, Arbiter; only recorded outcomes are shown, never completed merely because configured. · frame 1 of 1
5 — Edge and outcome list — relationship per edge plus the prior run's recorded Arbiter counts; facts and allegations are model classifications, not certification. · frame 1 of 1
6 — Reading rule — no independence or completion claim from graph shape alone. · frame 1 of 1

### corroboration-network-tablet.svg

[Open SVG](20261123-product-wireframes/corroboration-network-tablet.svg) · screen · tablet · Corroboration network · frame 1 of 2 · route `/cases/:id/network`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Corroboration network header — title, synthetic context and available actions.
3 — Claim and source graph — rect nodes and line edges; a shared edge is not independent proof. · frame 1 of 2
4 — Adversarial investigation flow — Collector, classifier, investigators, Arbiter; only recorded outcomes are shown, never completed merely because configured. · frame 1 of 2
5 — Edge and outcome list — relationship per edge plus the prior run's recorded Arbiter counts; facts and allegations are model classifications, not certification. · frame 1 of 2

### corroboration-network-tablet-part-2.svg

[Open SVG](20261123-product-wireframes/corroboration-network-tablet-part-2.svg) · screen · tablet · Corroboration network · frame 2 of 2 · route `/cases/:id/network`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Corroboration network — frame 2 of 2; full coverage continues in the named companion frame.
3 — Reading rule — no independence or completion claim from graph shape alone. · frame 2 of 2

### corroboration-network-mobile.svg

[Open SVG](20261123-product-wireframes/corroboration-network-mobile.svg) · screen · mobile · Corroboration network · frame 1 of 2 · route `/cases/:id/network`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Corroboration network header — title, synthetic context and available actions.
3 — Claim and source graph — rect nodes and line edges; a shared edge is not independent proof. · frame 1 of 2
4 — Adversarial investigation flow — Collector, classifier, investigators, Arbiter; only recorded outcomes are shown, never completed merely because configured. · frame 1 of 2

### corroboration-network-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/corroboration-network-mobile-part-2.svg) · screen · mobile · Corroboration network · frame 2 of 2 · route `/cases/:id/network`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Corroboration network — frame 2 of 2; full coverage continues in the named companion frame.
3 — Edge and outcome list — relationship per edge plus the prior run's recorded Arbiter counts; facts and allegations are model classifications, not certification. · frame 2 of 2
4 — Reading rule — no independence or completion claim from graph shape alone. · frame 2 of 2

### narratives-desktop.svg

[Open SVG](20261123-product-wireframes/narratives-desktop.svg) · screen · desktop · Narratives · route `/cases/:id/narratives`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Narratives header — title, synthetic context and available actions.
3 — Persisted clusters — stored cluster rows with their claim counts; no stance is generated on read. · frame 1 of 1
4 — Cluster detail — member claims and shared terms; the reader never invents a narrative position. · frame 1 of 1
5 — Reader rule — persisted data only; empty is distinct from unavailable. · frame 1 of 1

### narratives-tablet.svg

[Open SVG](20261123-product-wireframes/narratives-tablet.svg) · screen · tablet · Narratives · route `/cases/:id/narratives`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Narratives header — title, synthetic context and available actions.
3 — Persisted clusters — stored cluster rows with their claim counts; no stance is generated on read. · frame 1 of 1
4 — Cluster detail — member claims and shared terms; the reader never invents a narrative position. · frame 1 of 1
5 — Reader rule — persisted data only; empty is distinct from unavailable. · frame 1 of 1

### narratives-mobile.svg

[Open SVG](20261123-product-wireframes/narratives-mobile.svg) · screen · mobile · Narratives · route `/cases/:id/narratives`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Narratives header — title, synthetic context and available actions.
3 — Persisted clusters — stored cluster rows with their claim counts; no stance is generated on read. · frame 1 of 1
4 — Cluster detail — member claims and shared terms; the reader never invents a narrative position. · frame 1 of 1
5 — Reader rule — persisted data only; empty is distinct from unavailable. · frame 1 of 1

### monitoring-desktop.svg

[Open SVG](20261123-product-wireframes/monitoring-desktop.svg) · screen · desktop · Monitoring · route `/monitoring`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Monitoring header — title, synthetic context and available actions.
3 — Recorded checks — stored observation time and status only; no health, scheduler or alert state. · frame 1 of 1
4 — Scope note — monitoring is a recorded-status reader, not an operations dashboard. · frame 1 of 1

### monitoring-tablet.svg

[Open SVG](20261123-product-wireframes/monitoring-tablet.svg) · screen · tablet · Monitoring · route `/monitoring`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Monitoring header — title, synthetic context and available actions.
3 — Recorded checks — stored observation time and status only; no health, scheduler or alert state. · frame 1 of 1
4 — Scope note — monitoring is a recorded-status reader, not an operations dashboard. · frame 1 of 1

### monitoring-mobile.svg

[Open SVG](20261123-product-wireframes/monitoring-mobile.svg) · screen · mobile · Monitoring · frame 1 of 2 · route `/monitoring`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Monitoring header — title, synthetic context and available actions.
3 — Recorded checks — stored observation time and status only; no health, scheduler or alert state. · frame 1 of 2

### monitoring-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/monitoring-mobile-part-2.svg) · screen · mobile · Monitoring · frame 2 of 2 · route `/monitoring`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Monitoring — frame 2 of 2; full coverage continues in the named companion frame.
3 — Scope note — monitoring is a recorded-status reader, not an operations dashboard. · frame 2 of 2

### ai-info-desktop.svg

[Open SVG](20261123-product-wireframes/ai-info-desktop.svg) · screen · desktop · AI integration info · route `/ai-info`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — AI integration info header — title, synthetic context and available actions.
3 — Capabilities — available and unavailable features stated explicitly; no general chatbot. · frame 1 of 1
4 — Provenance note — model assessment origin stays visible and unknown origin stays unknown. · frame 1 of 1
5 — Unavailable features — listed rather than hidden. · frame 1 of 1

### ai-info-tablet.svg

[Open SVG](20261123-product-wireframes/ai-info-tablet.svg) · screen · tablet · AI integration info · route `/ai-info`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — AI integration info header — title, synthetic context and available actions.
3 — Capabilities — available and unavailable features stated explicitly; no general chatbot. · frame 1 of 1
4 — Provenance note — model assessment origin stays visible and unknown origin stays unknown. · frame 1 of 1
5 — Unavailable features — listed rather than hidden. · frame 1 of 1

### ai-info-mobile.svg

[Open SVG](20261123-product-wireframes/ai-info-mobile.svg) · screen · mobile · AI integration info · frame 1 of 2 · route `/ai-info`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — AI integration info header — title, synthetic context and available actions.
3 — Capabilities — available and unavailable features stated explicitly; no general chatbot. · frame 1 of 2

### ai-info-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/ai-info-mobile-part-2.svg) · screen · mobile · AI integration info · frame 2 of 2 · route `/ai-info`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — AI integration info — frame 2 of 2; full coverage continues in the named companion frame.
3 — Provenance note — model assessment origin stays visible and unknown origin stays unknown. · frame 2 of 2
4 — Unavailable features — listed rather than hidden. · frame 2 of 2

### shared-loading-desktop.svg

[Open SVG](20261123-product-wireframes/shared-loading-desktop.svg) · state · desktop · Loading — cases · parent `case-explorer`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Loading — cases header — title, synthetic context and available actions.
3 — Loading skeleton — pending request; no partial rows or totals are asserted. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Bounded wait note — the skeleton is replaced by a resolved state, never left silently. · frame 1 of 1

### shared-loading-tablet.svg

[Open SVG](20261123-product-wireframes/shared-loading-tablet.svg) · state · tablet · Loading — cases · parent `case-explorer`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Loading — cases header — title, synthetic context and available actions.
3 — Loading skeleton — pending request; no partial rows or totals are asserted. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Bounded wait note — the skeleton is replaced by a resolved state, never left silently. · frame 1 of 1

### shared-loading-mobile.svg

[Open SVG](20261123-product-wireframes/shared-loading-mobile.svg) · state · mobile · Loading — cases · parent `case-explorer`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Loading — cases header — title, synthetic context and available actions.
3 — Loading skeleton — pending request; no partial rows or totals are asserted. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Bounded wait note — the skeleton is replaced by a resolved state, never left silently. · frame 1 of 1

### shared-empty-desktop.svg

[Open SVG](20261123-product-wireframes/shared-empty-desktop.svg) · state · desktop · Empty — no cases · parent `case-explorer`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Empty — no cases header — title, synthetic context and available actions.
3 — Empty state — a valid empty result is not an error and not a failed read. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Next step — case creation stays an operator CLI action, not a browser form. · frame 1 of 1

### shared-empty-tablet.svg

[Open SVG](20261123-product-wireframes/shared-empty-tablet.svg) · state · tablet · Empty — no cases · parent `case-explorer`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Empty — no cases header — title, synthetic context and available actions.
3 — Empty state — a valid empty result is not an error and not a failed read. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Next step — case creation stays an operator CLI action, not a browser form. · frame 1 of 1

### shared-empty-mobile.svg

[Open SVG](20261123-product-wireframes/shared-empty-mobile.svg) · state · mobile · Empty — no cases · parent `case-explorer`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Empty — no cases header — title, synthetic context and available actions.
3 — Empty state — a valid empty result is not an error and not a failed read. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Next step — case creation stays an operator CLI action, not a browser form. · frame 1 of 1

### shared-not-found-desktop.svg

[Open SVG](20261123-product-wireframes/shared-not-found-desktop.svg) · state · desktop · Not found — unknown case or tab · parent `case-overview`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Not found — unknown case or tab header — title, synthetic context and available actions.
3 — 404 state — unknown case id or unknown tab route; no substitution. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Deep-link note — selection parameters never fall back to another item. · frame 1 of 1

### shared-not-found-tablet.svg

[Open SVG](20261123-product-wireframes/shared-not-found-tablet.svg) · state · tablet · Not found — unknown case or tab · parent `case-overview`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Not found — unknown case or tab header — title, synthetic context and available actions.
3 — 404 state — unknown case id or unknown tab route; no substitution. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Deep-link note — selection parameters never fall back to another item. · frame 1 of 1

### shared-not-found-mobile.svg

[Open SVG](20261123-product-wireframes/shared-not-found-mobile.svg) · state · mobile · Not found — unknown case or tab · parent `case-overview`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Not found — unknown case or tab header — title, synthetic context and available actions.
3 — 404 state — unknown case id or unknown tab route; no substitution. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Deep-link note — selection parameters never fall back to another item. · frame 1 of 1

### shared-network-error-desktop.svg

[Open SVG](20261123-product-wireframes/shared-network-error-desktop.svg) · state · desktop · Network error — dashboard · parent `dashboard`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Network error — dashboard header — title, synthetic context and available actions.
3 — Network error — retryable failed read, visually distinct from empty. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Generic pattern note — transport failure is shared by reads and the review form. · frame 1 of 1

### shared-network-error-tablet.svg

[Open SVG](20261123-product-wireframes/shared-network-error-tablet.svg) · state · tablet · Network error — dashboard · parent `dashboard`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Network error — dashboard header — title, synthetic context and available actions.
3 — Network error — retryable failed read, visually distinct from empty. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Generic pattern note — transport failure is shared by reads and the review form. · frame 1 of 1

### shared-network-error-mobile.svg

[Open SVG](20261123-product-wireframes/shared-network-error-mobile.svg) · state · mobile · Network error — dashboard · parent `dashboard`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Network error — dashboard header — title, synthetic context and available actions.
3 — Network error — retryable failed read, visually distinct from empty. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Generic pattern note — transport failure is shared by reads and the review form. · frame 1 of 1

### inspector-missing-quotation-desktop.svg

[Open SVG](20261123-product-wireframes/inspector-missing-quotation-desktop.svg) · state · desktop · Inspector — missing quotation · parent `capture-inspector`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Inspector — missing quotation header — title, synthetic context and available actions.
3 — Source list — one link has no quotation proposal; the reason is stated per row. · frame 1 of 1
4 — No-quotation block — nothing is highlighted and no offsets are claimed. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### inspector-missing-quotation-tablet.svg

[Open SVG](20261123-product-wireframes/inspector-missing-quotation-tablet.svg) · state · tablet · Inspector — missing quotation · parent `capture-inspector`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Inspector — missing quotation header — title, synthetic context and available actions.
3 — Source list — one link has no quotation proposal; the reason is stated per row. · frame 1 of 1
4 — No-quotation block — nothing is highlighted and no offsets are claimed. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### inspector-missing-quotation-mobile.svg

[Open SVG](20261123-product-wireframes/inspector-missing-quotation-mobile.svg) · state · mobile · Inspector — missing quotation · parent `capture-inspector`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Inspector — missing quotation header — title, synthetic context and available actions.
3 — Source list — one link has no quotation proposal; the reason is stated per row. · frame 1 of 1
4 — No-quotation block — nothing is highlighted and no offsets are claimed. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### inspector-source-unavailable-desktop.svg

[Open SVG](20261123-product-wireframes/inspector-source-unavailable-desktop.svg) · state · desktop · Inspector — source unavailable · parent `capture-inspector`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Inspector — source unavailable header — title, synthetic context and available actions.
3 — Unavailable capture — the quotation cannot be highlighted; reason stated. · frame 1 of 1
4 — Metadata pane — capture identity remains visible even when the body is unavailable. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### inspector-source-unavailable-tablet.svg

[Open SVG](20261123-product-wireframes/inspector-source-unavailable-tablet.svg) · state · tablet · Inspector — source unavailable · parent `capture-inspector`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Inspector — source unavailable header — title, synthetic context and available actions.
3 — Unavailable capture — the quotation cannot be highlighted; reason stated. · frame 1 of 1
4 — Metadata pane — capture identity remains visible even when the body is unavailable. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### inspector-source-unavailable-mobile.svg

[Open SVG](20261123-product-wireframes/inspector-source-unavailable-mobile.svg) · state · mobile · Inspector — source unavailable · parent `capture-inspector`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Inspector — source unavailable header — title, synthetic context and available actions.
3 — Unavailable capture — the quotation cannot be highlighted; reason stated. · frame 1 of 1
4 — Metadata pane — capture identity remains visible even when the body is unavailable. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### inspector-ambiguous-desktop.svg

[Open SVG](20261123-product-wireframes/inspector-ambiguous-desktop.svg) · state · desktop · Inspector — ambiguous quotation · parent `capture-inspector`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Inspector — ambiguous quotation header — title, synthetic context and available actions.
3 — Ambiguity list — repeated exact matches without disambiguating offsets; nothing is highlighted. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Resolution note — only a unique exact occurrence becomes exact. · frame 1 of 1

### inspector-ambiguous-tablet.svg

[Open SVG](20261123-product-wireframes/inspector-ambiguous-tablet.svg) · state · tablet · Inspector — ambiguous quotation · parent `capture-inspector`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Inspector — ambiguous quotation header — title, synthetic context and available actions.
3 — Ambiguity list — repeated exact matches without disambiguating offsets; nothing is highlighted. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Resolution note — only a unique exact occurrence becomes exact. · frame 1 of 1

### inspector-ambiguous-mobile.svg

[Open SVG](20261123-product-wireframes/inspector-ambiguous-mobile.svg) · state · mobile · Inspector — ambiguous quotation · parent `capture-inspector`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Inspector — ambiguous quotation header — title, synthetic context and available actions.
3 — Ambiguity list — repeated exact matches without disambiguating offsets; nothing is highlighted. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Resolution note — only a unique exact occurrence becomes exact. · frame 1 of 1

### inspector-no-match-desktop.svg

[Open SVG](20261123-product-wireframes/inspector-no-match-desktop.svg) · state · desktop · Inspector — quotation not in scope · parent `capture-inspector`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Inspector — quotation not in scope header — title, synthetic context and available actions.
3 — No-match state — no highlight and no scope widening on read. · frame 1 of 1
4 — Recorded scope — the reader does not search outside the recorded scope. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### inspector-no-match-tablet.svg

[Open SVG](20261123-product-wireframes/inspector-no-match-tablet.svg) · state · tablet · Inspector — quotation not in scope · parent `capture-inspector`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Inspector — quotation not in scope header — title, synthetic context and available actions.
3 — No-match state — no highlight and no scope widening on read. · frame 1 of 1
4 — Recorded scope — the reader does not search outside the recorded scope. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### inspector-no-match-mobile.svg

[Open SVG](20261123-product-wireframes/inspector-no-match-mobile.svg) · state · mobile · Inspector — quotation not in scope · parent `capture-inspector`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Inspector — quotation not in scope header — title, synthetic context and available actions.
3 — No-match state — no highlight and no scope widening on read. · frame 1 of 1
4 — Recorded scope — the reader does not search outside the recorded scope. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### inspector-legacy-desktop.svg

[Open SVG](20261123-product-wireframes/inspector-legacy-desktop.svg) · state · desktop · Inspector — legacy snapshot · parent `capture-inspector`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Inspector — legacy snapshot header — title, synthetic context and available actions.
3 — Legacy capture — imported text is labelled legacy_snapshot with unknown observation time. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Legacy quotation note — imported text never gains validated offsets by reading. · frame 1 of 1

### inspector-legacy-tablet.svg

[Open SVG](20261123-product-wireframes/inspector-legacy-tablet.svg) · state · tablet · Inspector — legacy snapshot · parent `capture-inspector`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Inspector — legacy snapshot header — title, synthetic context and available actions.
3 — Legacy capture — imported text is labelled legacy_snapshot with unknown observation time. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Legacy quotation note — imported text never gains validated offsets by reading. · frame 1 of 1

### inspector-legacy-mobile.svg

[Open SVG](20261123-product-wireframes/inspector-legacy-mobile.svg) · state · mobile · Inspector — legacy snapshot · parent `capture-inspector`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Inspector — legacy snapshot header — title, synthetic context and available actions.
3 — Legacy capture — imported text is labelled legacy_snapshot with unknown observation time. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Legacy quotation note — imported text never gains validated offsets by reading. · frame 1 of 1

### comparison-selection-desktop.svg

[Open SVG](20261123-product-wireframes/comparison-selection-desktop.svg) · state · desktop · Comparison — selection required · parent `comparison`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Comparison — selection required header — title, synthetic context and available actions.
3 — Selection prompt — Compare stays disabled until two different evidence captures are chosen. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Pinned URL — an empty selection is honest and reproducible. · frame 1 of 1

### comparison-selection-tablet.svg

[Open SVG](20261123-product-wireframes/comparison-selection-tablet.svg) · state · tablet · Comparison — selection required · parent `comparison`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Comparison — selection required header — title, synthetic context and available actions.
3 — Selection prompt — Compare stays disabled until two different evidence captures are chosen. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Pinned URL — an empty selection is honest and reproducible. · frame 1 of 1

### comparison-selection-mobile.svg

[Open SVG](20261123-product-wireframes/comparison-selection-mobile.svg) · state · mobile · Comparison — selection required · frame 1 of 2 · parent `comparison`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Comparison — selection required header — title, synthetic context and available actions.
3 — Selection prompt — Compare stays disabled until two different evidence captures are chosen. · frame 1 of 2
4 — State scope note — what the state does and does not assert. · frame 1 of 2

### comparison-selection-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/comparison-selection-mobile-part-2.svg) · state · mobile · Comparison — selection required · frame 2 of 2 · parent `comparison`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Comparison — selection required — frame 2 of 2; full coverage continues in the named companion frame.
3 — Pinned URL — an empty selection is honest and reproducible. · frame 2 of 2

### comparison-same-source-desktop.svg

[Open SVG](20261123-product-wireframes/comparison-same-source-desktop.svg) · state · desktop · Comparison — same source rejected · parent `comparison`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Comparison — same source rejected header — title, synthetic context and available actions.
3 — Same-source validation — the opposite source and capture are disabled; Compare stays disabled. · frame 1 of 1
4 — Validation state — the same evidence cannot be compared with itself. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### comparison-same-source-tablet.svg

[Open SVG](20261123-product-wireframes/comparison-same-source-tablet.svg) · state · tablet · Comparison — same source rejected · parent `comparison`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Comparison — same source rejected header — title, synthetic context and available actions.
3 — Same-source validation — the opposite source and capture are disabled; Compare stays disabled. · frame 1 of 1
4 — Validation state — the same evidence cannot be compared with itself. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### comparison-same-source-mobile.svg

[Open SVG](20261123-product-wireframes/comparison-same-source-mobile.svg) · state · mobile · Comparison — same source rejected · frame 1 of 2 · parent `comparison`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Comparison — same source rejected header — title, synthetic context and available actions.
3 — Same-source validation — the opposite source and capture are disabled; Compare stays disabled. · frame 1 of 2

### comparison-same-source-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/comparison-same-source-mobile-part-2.svg) · state · mobile · Comparison — same source rejected · frame 2 of 2 · parent `comparison`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Comparison — same source rejected — frame 2 of 2; full coverage continues in the named companion frame.
3 — Validation state — the same evidence cannot be compared with itself. · frame 2 of 2
4 — State scope note — what the state does and does not assert. · frame 2 of 2

### comparison-no-second-source-desktop.svg

[Open SVG](20261123-product-wireframes/comparison-no-second-source-desktop.svg) · state · desktop · Comparison — no second source · parent `comparison`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Comparison — no second source header — title, synthetic context and available actions.
3 — No-second-source state — distinct from a selection error or an empty comparison. · frame 1 of 1
4 — Next step — a second source arrives through the operator CLI, never a browser form. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### comparison-no-second-source-tablet.svg

[Open SVG](20261123-product-wireframes/comparison-no-second-source-tablet.svg) · state · tablet · Comparison — no second source · parent `comparison`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Comparison — no second source header — title, synthetic context and available actions.
3 — No-second-source state — distinct from a selection error or an empty comparison. · frame 1 of 1
4 — Next step — a second source arrives through the operator CLI, never a browser form. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### comparison-no-second-source-mobile.svg

[Open SVG](20261123-product-wireframes/comparison-no-second-source-mobile.svg) · state · mobile · Comparison — no second source · parent `comparison`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Comparison — no second source header — title, synthetic context and available actions.
3 — No-second-source state — distinct from a selection error or an empty comparison. · frame 1 of 1
4 — Next step — a second source arrives through the operator CLI, never a browser form. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### comparison-empty-desktop.svg

[Open SVG](20261123-product-wireframes/comparison-empty-desktop.svg) · state · desktop · Comparison — no aligned rows · parent `comparison`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Comparison — no aligned rows header — title, synthetic context and available actions.
3 — Selection summary — both captures are pinned and readable. · frame 1 of 1
4 — Empty comparison — a valid empty alignment is not an unavailable historical capture. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### comparison-empty-tablet.svg

[Open SVG](20261123-product-wireframes/comparison-empty-tablet.svg) · state · tablet · Comparison — no aligned rows · parent `comparison`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Comparison — no aligned rows header — title, synthetic context and available actions.
3 — Selection summary — both captures are pinned and readable. · frame 1 of 1
4 — Empty comparison — a valid empty alignment is not an unavailable historical capture. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### comparison-empty-mobile.svg

[Open SVG](20261123-product-wireframes/comparison-empty-mobile.svg) · state · mobile · Comparison — no aligned rows · frame 1 of 2 · parent `comparison`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Comparison — no aligned rows header — title, synthetic context and available actions.
3 — Selection summary — both captures are pinned and readable. · frame 1 of 2
4 — Empty comparison — a valid empty alignment is not an unavailable historical capture. · frame 1 of 2

### comparison-empty-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/comparison-empty-mobile-part-2.svg) · state · mobile · Comparison — no aligned rows · frame 2 of 2 · parent `comparison`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Comparison — no aligned rows — frame 2 of 2; full coverage continues in the named companion frame.
3 — State scope note — what the state does and does not assert. · frame 2 of 2

### comparison-historical-unavailable-desktop.svg

[Open SVG](20261123-product-wireframes/comparison-historical-unavailable-desktop.svg) · state · desktop · Comparison — historical unavailable · parent `comparison`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Comparison — historical unavailable header — title, synthetic context and available actions.
3 — Historical banner — an old capture without retained alignment stays unavailable. · frame 1 of 1
4 — Capture context — each side reads its stored capture; no latest links. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### comparison-historical-unavailable-tablet.svg

[Open SVG](20261123-product-wireframes/comparison-historical-unavailable-tablet.svg) · state · tablet · Comparison — historical unavailable · parent `comparison`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Comparison — historical unavailable header — title, synthetic context and available actions.
3 — Historical banner — an old capture without retained alignment stays unavailable. · frame 1 of 1
4 — Capture context — each side reads its stored capture; no latest links. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### comparison-historical-unavailable-mobile.svg

[Open SVG](20261123-product-wireframes/comparison-historical-unavailable-mobile.svg) · state · mobile · Comparison — historical unavailable · parent `comparison`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Comparison — historical unavailable header — title, synthetic context and available actions.
3 — Historical banner — an old capture without retained alignment stays unavailable. · frame 1 of 1
4 — Capture context — each side reads its stored capture; no latest links. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### comparison-dependency-warning-desktop.svg

[Open SVG](20261123-product-wireframes/comparison-dependency-warning-desktop.svg) · state · desktop · Comparison — dependency warning · parent `comparison`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Comparison — dependency warning header — title, synthetic context and available actions.
3 — Dependency warning — reasons and limitation shown before the rows. · frame 1 of 1
4 — Rows under warning — alignment states remain extraction coverage, not endorsement. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### comparison-dependency-warning-tablet.svg

[Open SVG](20261123-product-wireframes/comparison-dependency-warning-tablet.svg) · state · tablet · Comparison — dependency warning · parent `comparison`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Comparison — dependency warning header — title, synthetic context and available actions.
3 — Dependency warning — reasons and limitation shown before the rows. · frame 1 of 1
4 — Rows under warning — alignment states remain extraction coverage, not endorsement. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### comparison-dependency-warning-mobile.svg

[Open SVG](20261123-product-wireframes/comparison-dependency-warning-mobile.svg) · state · mobile · Comparison — dependency warning · parent `comparison`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Comparison — dependency warning header — title, synthetic context and available actions.
3 — Dependency warning — reasons and limitation shown before the rows. · frame 1 of 1
4 — Rows under warning — alignment states remain extraction coverage, not endorsement. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### changes-initial-desktop.svg

[Open SVG](20261123-product-wireframes/changes-initial-desktop.svg) · state · desktop · Changes — first observation · parent `runs-changes`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Changes — first observation header — title, synthetic context and available actions.
3 — Initial banner — the first snapshot has no baseline and is not a change surge. · frame 1 of 1
4 — Snapshot facts — first snapshot identifiers and coverage. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### changes-initial-tablet.svg

[Open SVG](20261123-product-wireframes/changes-initial-tablet.svg) · state · tablet · Changes — first observation · parent `runs-changes`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Changes — first observation header — title, synthetic context and available actions.
3 — Initial banner — the first snapshot has no baseline and is not a change surge. · frame 1 of 1
4 — Snapshot facts — first snapshot identifiers and coverage. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### changes-initial-mobile.svg

[Open SVG](20261123-product-wireframes/changes-initial-mobile.svg) · state · mobile · Changes — first observation · parent `runs-changes`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Changes — first observation header — title, synthetic context and available actions.
3 — Initial banner — the first snapshot has no baseline and is not a change surge. · frame 1 of 1
4 — Snapshot facts — first snapshot identifiers and coverage. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### changes-pending-desktop.svg

[Open SVG](20261123-product-wireframes/changes-pending-desktop.svg) · state · desktop · Changes — run in progress · parent `runs-changes`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Changes — run in progress header — title, synthetic context and available actions.
3 — Pending banner — pending is not an empty delta. · frame 1 of 1
4 — Pending skeleton — no partial before/after rows are shown. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### changes-pending-tablet.svg

[Open SVG](20261123-product-wireframes/changes-pending-tablet.svg) · state · tablet · Changes — run in progress · parent `runs-changes`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Changes — run in progress header — title, synthetic context and available actions.
3 — Pending banner — pending is not an empty delta. · frame 1 of 1
4 — Pending skeleton — no partial before/after rows are shown. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### changes-pending-mobile.svg

[Open SVG](20261123-product-wireframes/changes-pending-mobile.svg) · state · mobile · Changes — run in progress · parent `runs-changes`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Changes — run in progress header — title, synthetic context and available actions.
3 — Pending banner — pending is not an empty delta. · frame 1 of 1
4 — Pending skeleton — no partial before/after rows are shown. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### changes-unavailable-desktop.svg

[Open SVG](20261123-product-wireframes/changes-unavailable-desktop.svg) · state · desktop · Changes — no snapshot published · parent `runs-changes`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Changes — no snapshot published header — title, synthetic context and available actions.
3 — Unavailable banner — failed or interrupted runs never advance the baseline. · frame 1 of 1
4 — Recorded error — the stored failure is shown; recovery stays CLI-only. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### changes-unavailable-tablet.svg

[Open SVG](20261123-product-wireframes/changes-unavailable-tablet.svg) · state · tablet · Changes — no snapshot published · parent `runs-changes`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Changes — no snapshot published header — title, synthetic context and available actions.
3 — Unavailable banner — failed or interrupted runs never advance the baseline. · frame 1 of 1
4 — Recorded error — the stored failure is shown; recovery stays CLI-only. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### changes-unavailable-mobile.svg

[Open SVG](20261123-product-wireframes/changes-unavailable-mobile.svg) · state · mobile · Changes — no snapshot published · parent `runs-changes`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Changes — no snapshot published header — title, synthetic context and available actions.
3 — Unavailable banner — failed or interrupted runs never advance the baseline. · frame 1 of 1
4 — Recorded error — the stored failure is shown; recovery stays CLI-only. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### changes-unchanged-partial-desktop.svg

[Open SVG](20261123-product-wireframes/changes-unchanged-partial-desktop.svg) · state · desktop · Changes — unchanged with partial coverage · parent `runs-changes`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Changes — unchanged with partial coverage header — title, synthetic context and available actions.
3 — Unchanged state — a valid delta with zero typed rows. · frame 1 of 1
4 — Coverage warning — persistent alongside an empty delta. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### changes-unchanged-partial-tablet.svg

[Open SVG](20261123-product-wireframes/changes-unchanged-partial-tablet.svg) · state · tablet · Changes — unchanged with partial coverage · parent `runs-changes`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Changes — unchanged with partial coverage header — title, synthetic context and available actions.
3 — Unchanged state — a valid delta with zero typed rows. · frame 1 of 1
4 — Coverage warning — persistent alongside an empty delta. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### changes-unchanged-partial-mobile.svg

[Open SVG](20261123-product-wireframes/changes-unchanged-partial-mobile.svg) · state · mobile · Changes — unchanged with partial coverage · parent `runs-changes`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Changes — unchanged with partial coverage header — title, synthetic context and available actions.
3 — Unchanged state — a valid delta with zero typed rows. · frame 1 of 1
4 — Coverage warning — persistent alongside an empty delta. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### search-no-results-desktop.svg

[Open SVG](20261123-product-wireframes/search-no-results-desktop.svg) · state · desktop · Search — no results · parent `search`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Search — no results header — title, synthetic context and available actions.
3 — Filters remain visible — the applied query and filters are printed with the empty result. · frame 1 of 1
4 — No-results state — a valid empty result, not an unavailable index. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### search-no-results-tablet.svg

[Open SVG](20261123-product-wireframes/search-no-results-tablet.svg) · state · tablet · Search — no results · parent `search`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Search — no results header — title, synthetic context and available actions.
3 — Filters remain visible — the applied query and filters are printed with the empty result. · frame 1 of 1
4 — No-results state — a valid empty result, not an unavailable index. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### search-no-results-mobile.svg

[Open SVG](20261123-product-wireframes/search-no-results-mobile.svg) · state · mobile · Search — no results · parent `search`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Search — no results header — title, synthetic context and available actions.
3 — Filters remain visible — the applied query and filters are printed with the empty result. · frame 1 of 1
4 — No-results state — a valid empty result, not an unavailable index. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### search-index-unavailable-desktop.svg

[Open SVG](20261123-product-wireframes/search-index-unavailable-desktop.svg) · state · desktop · Search — index unavailable · parent `search`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Search — index unavailable header — title, synthetic context and available actions.
3 — 503 state — index capability absent; explicit unavailable, not empty. · frame 1 of 1
4 — Operator remedy — printed remediation, not a browser rebuild button. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### search-index-unavailable-tablet.svg

[Open SVG](20261123-product-wireframes/search-index-unavailable-tablet.svg) · state · tablet · Search — index unavailable · parent `search`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Search — index unavailable header — title, synthetic context and available actions.
3 — 503 state — index capability absent; explicit unavailable, not empty. · frame 1 of 1
4 — Operator remedy — printed remediation, not a browser rebuild button. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### search-index-unavailable-mobile.svg

[Open SVG](20261123-product-wireframes/search-index-unavailable-mobile.svg) · state · mobile · Search — index unavailable · parent `search`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Search — index unavailable header — title, synthetic context and available actions.
3 — 503 state — index capability absent; explicit unavailable, not empty. · frame 1 of 1
4 — Operator remedy — printed remediation, not a browser rebuild button. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### search-invalid-filters-desktop.svg

[Open SVG](20261123-product-wireframes/search-invalid-filters-desktop.svg) · state · desktop · Search — invalid filters · parent `search`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Search — invalid filters header — title, synthetic context and available actions.
3 — Invalid filter combination — status applies to claims only and conflicts with evidence-only type. · frame 1 of 1
4 — 422 state — invalid combination is explained inline. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### search-invalid-filters-tablet.svg

[Open SVG](20261123-product-wireframes/search-invalid-filters-tablet.svg) · state · tablet · Search — invalid filters · parent `search`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Search — invalid filters header — title, synthetic context and available actions.
3 — Invalid filter combination — status applies to claims only and conflicts with evidence-only type. · frame 1 of 1
4 — 422 state — invalid combination is explained inline. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### search-invalid-filters-mobile.svg

[Open SVG](20261123-product-wireframes/search-invalid-filters-mobile.svg) · state · mobile · Search — invalid filters · frame 1 of 2 · parent `search`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Search — invalid filters header — title, synthetic context and available actions.
3 — Invalid filter combination — status applies to claims only and conflicts with evidence-only type. · frame 1 of 2
4 — 422 state — invalid combination is explained inline. · frame 1 of 2

### search-invalid-filters-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/search-invalid-filters-mobile-part-2.svg) · state · mobile · Search — invalid filters · frame 2 of 2 · parent `search`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Search — invalid filters — frame 2 of 2; full coverage continues in the named companion frame.
3 — State scope note — what the state does and does not assert. · frame 2 of 2

### search-out-of-range-desktop.svg

[Open SVG](20261123-product-wireframes/search-out-of-range-desktop.svg) · state · desktop · This page is beyond the last result · parent `search`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — This page is beyond the last result header — title, synthetic context and available actions.
3 — Paging controls — a valid offset past the last row with the query preserved; Return first page clears offset and keeps the query. · frame 1 of 1
4 — Beyond-last-page state — a valid empty page, not a 422 and not an unavailable index. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### search-out-of-range-tablet.svg

[Open SVG](20261123-product-wireframes/search-out-of-range-tablet.svg) · state · tablet · This page is beyond the last result · parent `search`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — This page is beyond the last result header — title, synthetic context and available actions.
3 — Paging controls — a valid offset past the last row with the query preserved; Return first page clears offset and keeps the query. · frame 1 of 1
4 — Beyond-last-page state — a valid empty page, not a 422 and not an unavailable index. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### search-out-of-range-mobile.svg

[Open SVG](20261123-product-wireframes/search-out-of-range-mobile.svg) · state · mobile · This page is beyond the last result · frame 1 of 2 · parent `search`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — This page is beyond the last result header — title, synthetic context and available actions.
3 — Paging controls — a valid offset past the last row with the query preserved; Return first page clears offset and keeps the query. · frame 1 of 2
4 — Beyond-last-page state — a valid empty page, not a 422 and not an unavailable index. · frame 1 of 2

### search-out-of-range-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/search-out-of-range-mobile-part-2.svg) · state · mobile · This page is beyond the last result · frame 2 of 2 · parent `search`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — This page is beyond the last result — frame 2 of 2; full coverage continues in the named companion frame.
3 — State scope note — what the state does and does not assert. · frame 2 of 2

### review-saving-desktop.svg

[Open SVG](20261123-product-wireframes/review-saving-desktop.svg) · state · desktop · Review — saving · parent `review-annotation`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Review — saving header — title, synthetic context and available actions.
3 — Saving state — rationale only plus the three decision buttons; all controls disabled while the review POST is in flight and no success is claimed yet. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Write-scope note — a single narrow review write, explicit failure and no client retry loop. · frame 1 of 1

### review-saving-tablet.svg

[Open SVG](20261123-product-wireframes/review-saving-tablet.svg) · state · tablet · Review — saving · parent `review-annotation`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Review — saving header — title, synthetic context and available actions.
3 — Saving state — rationale only plus the three decision buttons; all controls disabled while the review POST is in flight and no success is claimed yet. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Write-scope note — a single narrow review write, explicit failure and no client retry loop. · frame 1 of 1

### review-saving-mobile.svg

[Open SVG](20261123-product-wireframes/review-saving-mobile.svg) · state · mobile · Review — saving · parent `review-annotation`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Review — saving header — title, synthetic context and available actions.
3 — Saving state — rationale only plus the three decision buttons; all controls disabled while the review POST is in flight and no success is claimed yet. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Write-scope note — a single narrow review write, explicit failure and no client retry loop. · frame 1 of 1

### review-failed-desktop.svg

[Open SVG](20261123-product-wireframes/review-failed-desktop.svg) · state · desktop · Review — writer conflict · parent `review-annotation`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Review — writer conflict header — title, synthetic context and available actions.
3 — 409 conflict — active case writer conflict; the decision is explicitly not saved. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Recovery note — retry the chosen review action after writer release; browser review retry and CLI recovery are separate. · frame 1 of 1

### review-failed-tablet.svg

[Open SVG](20261123-product-wireframes/review-failed-tablet.svg) · state · tablet · Review — writer conflict · parent `review-annotation`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Review — writer conflict header — title, synthetic context and available actions.
3 — 409 conflict — active case writer conflict; the decision is explicitly not saved. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Recovery note — retry the chosen review action after writer release; browser review retry and CLI recovery are separate. · frame 1 of 1

### review-failed-mobile.svg

[Open SVG](20261123-product-wireframes/review-failed-mobile.svg) · state · mobile · Review — writer conflict · parent `review-annotation`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Review — writer conflict header — title, synthetic context and available actions.
3 — 409 conflict — active case writer conflict; the decision is explicitly not saved. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Recovery note — retry the chosen review action after writer release; browser review retry and CLI recovery are separate. · frame 1 of 1

### review-stale-desktop.svg

[Open SVG](20261123-product-wireframes/review-stale-desktop.svg) · state · desktop · Review — case data changed · parent `review-annotation`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Review — case data changed header — title, synthetic context and available actions.
3 — Stale banner — the form is frozen rather than silently overwriting newer data. · frame 1 of 1
4 — Frozen form — the three decision buttons are disabled until the newer case state is reloaded; Reload case is the only enabled control. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### review-stale-tablet.svg

[Open SVG](20261123-product-wireframes/review-stale-tablet.svg) · state · tablet · Review — case data changed · parent `review-annotation`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Review — case data changed header — title, synthetic context and available actions.
3 — Stale banner — the form is frozen rather than silently overwriting newer data. · frame 1 of 1
4 — Frozen form — the three decision buttons are disabled until the newer case state is reloaded; Reload case is the only enabled control. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### review-stale-mobile.svg

[Open SVG](20261123-product-wireframes/review-stale-mobile.svg) · state · mobile · Review — case data changed · parent `review-annotation`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Review — case data changed header — title, synthetic context and available actions.
3 — Stale banner — the form is frozen rather than silently overwriting newer data. · frame 1 of 1
4 — Frozen form — the three decision buttons are disabled until the newer case state is reloaded; Reload case is the only enabled control. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### review-saved-desktop.svg

[Open SVG](20261123-product-wireframes/review-saved-desktop.svg) · state · desktop · Review — decision recorded · parent `review-annotation`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Review — decision recorded header — title, synthetic context and available actions.
3 — Saved confirmation — recorded decision is reported as observed, without actor attribution. · frame 1 of 1
4 — Recorded review — fields as stored; no human audit trail is implied. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### review-saved-tablet.svg

[Open SVG](20261123-product-wireframes/review-saved-tablet.svg) · state · tablet · Review — decision recorded · parent `review-annotation`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Review — decision recorded header — title, synthetic context and available actions.
3 — Saved confirmation — recorded decision is reported as observed, without actor attribution. · frame 1 of 1
4 — Recorded review — fields as stored; no human audit trail is implied. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### review-saved-mobile.svg

[Open SVG](20261123-product-wireframes/review-saved-mobile.svg) · state · mobile · Review — decision recorded · parent `review-annotation`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Review — decision recorded header — title, synthetic context and available actions.
3 — Saved confirmation — recorded decision is reported as observed, without actor attribution. · frame 1 of 1
4 — Recorded review — fields as stored; no human audit trail is implied. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### review-blocked-desktop.svg

[Open SVG](20261123-product-wireframes/review-blocked-desktop.svg) · state · desktop · Review — blocked by exceptions · parent `review-annotation`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Review — blocked by exceptions header — title, synthetic context and available actions.
3 — Blocked state — 422 approval blocked by unresolved exceptions; links the queue. · frame 1 of 1
4 — Unresolved exception list — the blocking rows with their recorded states. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### review-blocked-tablet.svg

[Open SVG](20261123-product-wireframes/review-blocked-tablet.svg) · state · tablet · Review — blocked by exceptions · parent `review-annotation`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Review — blocked by exceptions header — title, synthetic context and available actions.
3 — Blocked state — 422 approval blocked by unresolved exceptions; links the queue. · frame 1 of 1
4 — Unresolved exception list — the blocking rows with their recorded states. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### review-blocked-mobile.svg

[Open SVG](20261123-product-wireframes/review-blocked-mobile.svg) · state · mobile · Review — blocked by exceptions · parent `review-annotation`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Review — blocked by exceptions header — title, synthetic context and available actions.
3 — Blocked state — 422 approval blocked by unresolved exceptions; links the queue. · frame 1 of 1
4 — Unresolved exception list — the blocking rows with their recorded states. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### annotation-invalid-desktop.svg

[Open SVG](20261123-product-wireframes/annotation-invalid-desktop.svg) · state · desktop · Annotation — invalid input · parent `review-annotation`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Annotation — invalid input header — title, synthetic context and available actions.
3 — Invalid annotation — bad target and blank content are rejected block-side with 422. · frame 1 of 1
4 — 422 validation — inline field errors; Save stays disabled. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### annotation-invalid-tablet.svg

[Open SVG](20261123-product-wireframes/annotation-invalid-tablet.svg) · state · tablet · Annotation — invalid input · parent `review-annotation`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Annotation — invalid input header — title, synthetic context and available actions.
3 — Invalid annotation — bad target and blank content are rejected block-side with 422. · frame 1 of 1
4 — 422 validation — inline field errors; Save stays disabled. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### annotation-invalid-mobile.svg

[Open SVG](20261123-product-wireframes/annotation-invalid-mobile.svg) · state · mobile · Annotation — invalid input · frame 1 of 2 · parent `review-annotation`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Annotation — invalid input header — title, synthetic context and available actions.
3 — Invalid annotation — bad target and blank content are rejected block-side with 422. · frame 1 of 2
4 — 422 validation — inline field errors; Save stays disabled. · frame 1 of 2

### annotation-invalid-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/annotation-invalid-mobile-part-2.svg) · state · mobile · Annotation — invalid input · frame 2 of 2 · parent `review-annotation`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Annotation — invalid input — frame 2 of 2; full coverage continues in the named companion frame.
3 — State scope note — what the state does and does not assert. · frame 2 of 2

### evaluation-unavailable-desktop.svg

[Open SVG](20261123-product-wireframes/evaluation-unavailable-desktop.svg) · state · desktop · Evaluation — no saved evaluation · parent `claims`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Evaluation — no saved evaluation header — title, synthetic context and available actions.
3 — Unavailable evaluation — absence of a saved result, not a score of zero. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — What remains — claim reading is independent of a saved evaluation. · frame 1 of 1

### evaluation-unavailable-tablet.svg

[Open SVG](20261123-product-wireframes/evaluation-unavailable-tablet.svg) · state · tablet · Evaluation — no saved evaluation · parent `claims`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Evaluation — no saved evaluation header — title, synthetic context and available actions.
3 — Unavailable evaluation — absence of a saved result, not a score of zero. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — What remains — claim reading is independent of a saved evaluation. · frame 1 of 1

### evaluation-unavailable-mobile.svg

[Open SVG](20261123-product-wireframes/evaluation-unavailable-mobile.svg) · state · mobile · Evaluation — no saved evaluation · parent `claims`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Evaluation — no saved evaluation header — title, synthetic context and available actions.
3 — Unavailable evaluation — absence of a saved result, not a score of zero. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — What remains — claim reading is independent of a saved evaluation. · frame 1 of 1

### evaluation-failed-desktop.svg

[Open SVG](20261123-product-wireframes/evaluation-failed-desktop.svg) · state · desktop · Evaluation — read failed · parent `claims`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Evaluation — read failed header — title, synthetic context and available actions.
3 — Failed evaluation — retryable read error, distinct from unavailable and empty. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Distinct-state note — unavailable, failed and zero never collapse. · frame 1 of 1

### evaluation-failed-tablet.svg

[Open SVG](20261123-product-wireframes/evaluation-failed-tablet.svg) · state · tablet · Evaluation — read failed · parent `claims`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Evaluation — read failed header — title, synthetic context and available actions.
3 — Failed evaluation — retryable read error, distinct from unavailable and empty. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Distinct-state note — unavailable, failed and zero never collapse. · frame 1 of 1

### evaluation-failed-mobile.svg

[Open SVG](20261123-product-wireframes/evaluation-failed-mobile.svg) · state · mobile · Evaluation — read failed · parent `claims`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Evaluation — read failed header — title, synthetic context and available actions.
3 — Failed evaluation — retryable read error, distinct from unavailable and empty. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Distinct-state note — unavailable, failed and zero never collapse. · frame 1 of 1

### exception-pending-desktop.svg

[Open SVG](20261123-product-wireframes/exception-pending-desktop.svg) · state · desktop · Exception — pending row · parent `exception-queue`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Exception — pending row header — title, synthetic context and available actions.
3 — Pending exception — a pending row disables every row action, including Reopen, until its prerequisite clears. · frame 1 of 1
4 — Pending action controls — Resolve, Defer and Reopen are all disabled for the pending row. · frame 1 of 1
5 — Blocked-by note — the reason is stated; recovery stays CLI-only. · frame 1 of 1

### exception-pending-tablet.svg

[Open SVG](20261123-product-wireframes/exception-pending-tablet.svg) · state · tablet · Exception — pending row · parent `exception-queue`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Exception — pending row header — title, synthetic context and available actions.
3 — Pending exception — a pending row disables every row action, including Reopen, until its prerequisite clears. · frame 1 of 1
4 — Pending action controls — Resolve, Defer and Reopen are all disabled for the pending row. · frame 1 of 1
5 — Blocked-by note — the reason is stated; recovery stays CLI-only. · frame 1 of 1

### exception-pending-mobile.svg

[Open SVG](20261123-product-wireframes/exception-pending-mobile.svg) · state · mobile · Exception — pending row · frame 1 of 2 · parent `exception-queue`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Exception — pending row header — title, synthetic context and available actions.
3 — Pending exception — a pending row disables every row action, including Reopen, until its prerequisite clears. · frame 1 of 2
4 — Pending action controls — Resolve, Defer and Reopen are all disabled for the pending row. · frame 1 of 2

### exception-pending-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/exception-pending-mobile-part-2.svg) · state · mobile · Exception — pending row · frame 2 of 2 · parent `exception-queue`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Exception — pending row — frame 2 of 2; full coverage continues in the named companion frame.
3 — Blocked-by note — the reason is stated; recovery stays CLI-only. · frame 2 of 2

### exception-failed-desktop.svg

[Open SVG](20261123-product-wireframes/exception-failed-desktop.svg) · state · desktop · Exception — action failed · parent `exception-queue`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Exception — action failed header — title, synthetic context and available actions.
3 — Failed action — inline error, row state unchanged. · frame 1 of 1
4 — Row state — still deferred; the failed action is not reflected as applied. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### exception-failed-tablet.svg

[Open SVG](20261123-product-wireframes/exception-failed-tablet.svg) · state · tablet · Exception — action failed · parent `exception-queue`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Exception — action failed header — title, synthetic context and available actions.
3 — Failed action — inline error, row state unchanged. · frame 1 of 1
4 — Row state — still deferred; the failed action is not reflected as applied. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### exception-failed-mobile.svg

[Open SVG](20261123-product-wireframes/exception-failed-mobile.svg) · state · mobile · Exception — action failed · parent `exception-queue`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Exception — action failed header — title, synthetic context and available actions.
3 — Failed action — inline error, row state unchanged. · frame 1 of 1
4 — Row state — still deferred; the failed action is not reflected as applied. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### exception-empty-desktop.svg

[Open SVG](20261123-product-wireframes/exception-empty-desktop.svg) · state · desktop · Exception — none recorded · parent `exception-queue`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Exception — none recorded header — title, synthetic context and available actions.
3 — Empty queue — not a failed read and not an unavailable capability. · frame 1 of 1
4 — Interpretation note — an empty queue is a valid read, not a failure. · frame 1 of 1

### exception-empty-tablet.svg

[Open SVG](20261123-product-wireframes/exception-empty-tablet.svg) · state · tablet · Exception — none recorded · parent `exception-queue`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Exception — none recorded header — title, synthetic context and available actions.
3 — Empty queue — not a failed read and not an unavailable capability. · frame 1 of 1
4 — Interpretation note — an empty queue is a valid read, not a failure. · frame 1 of 1

### exception-empty-mobile.svg

[Open SVG](20261123-product-wireframes/exception-empty-mobile.svg) · state · mobile · Exception — none recorded · parent `exception-queue`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Exception — none recorded header — title, synthetic context and available actions.
3 — Empty queue — not a failed read and not an unavailable capability. · frame 1 of 1
4 — Interpretation note — an empty queue is a valid read, not a failure. · frame 1 of 1

### report-pending-desktop.svg

[Open SVG](20261123-product-wireframes/report-pending-desktop.svg) · state · desktop · Report — pending · parent `report`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Report — pending header — title, synthetic context and available actions.
3 — Pending report — downloads stay disabled until the run finalizes. · frame 1 of 1
4 — Disabled downloads — pending report has no stored Markdown or JSON. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### report-pending-tablet.svg

[Open SVG](20261123-product-wireframes/report-pending-tablet.svg) · state · tablet · Report — pending · parent `report`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Report — pending header — title, synthetic context and available actions.
3 — Pending report — downloads stay disabled until the run finalizes. · frame 1 of 1
4 — Disabled downloads — pending report has no stored Markdown or JSON. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### report-pending-mobile.svg

[Open SVG](20261123-product-wireframes/report-pending-mobile.svg) · state · mobile · Report — pending · frame 1 of 2 · parent `report`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Report — pending header — title, synthetic context and available actions.
3 — Pending report — downloads stay disabled until the run finalizes. · frame 1 of 2
4 — Disabled downloads — pending report has no stored Markdown or JSON. · frame 1 of 2

### report-pending-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/report-pending-mobile-part-2.svg) · state · mobile · Report — pending · frame 2 of 2 · parent `report`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Report — pending — frame 2 of 2; full coverage continues in the named companion frame.
3 — State scope note — what the state does and does not assert. · frame 2 of 2

### report-download-error-desktop.svg

[Open SVG](20261123-product-wireframes/report-download-error-desktop.svg) · state · desktop · Report — download error · parent `report`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Report — download error header — title, synthetic context and available actions.
3 — Download error — explicit failure, no empty document rendered. · frame 1 of 1
4 — Artifact note — the run-specific directory and stored formats. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### report-download-error-tablet.svg

[Open SVG](20261123-product-wireframes/report-download-error-tablet.svg) · state · tablet · Report — download error · parent `report`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Report — download error header — title, synthetic context and available actions.
3 — Download error — explicit failure, no empty document rendered. · frame 1 of 1
4 — Artifact note — the run-specific directory and stored formats. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### report-download-error-mobile.svg

[Open SVG](20261123-product-wireframes/report-download-error-mobile.svg) · state · mobile · Report — download error · parent `report`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Report — download error header — title, synthetic context and available actions.
3 — Download error — explicit failure, no empty document rendered. · frame 1 of 1
4 — Artifact note — the run-specific directory and stored formats. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### map-empty-desktop.svg

[Open SVG](20261123-product-wireframes/map-empty-desktop.svg) · state · desktop · Map — no geotagged events · parent `geographic-map`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Map — no geotagged events header — title, synthetic context and available actions.
3 — Empty map — placeholder area with no geotagged markers. · frame 1 of 1
4 — Empty map — untagged events stay unknown; no invented coordinates. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### map-empty-tablet.svg

[Open SVG](20261123-product-wireframes/map-empty-tablet.svg) · state · tablet · Map — no geotagged events · parent `geographic-map`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Map — no geotagged events header — title, synthetic context and available actions.
3 — Empty map — placeholder area with no geotagged markers. · frame 1 of 1
4 — Empty map — untagged events stay unknown; no invented coordinates. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### map-empty-mobile.svg

[Open SVG](20261123-product-wireframes/map-empty-mobile.svg) · state · mobile · Map — no geotagged events · frame 1 of 2 · parent `geographic-map`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Map — no geotagged events header — title, synthetic context and available actions.
3 — Empty map — placeholder area with no geotagged markers. · frame 1 of 2
4 — Empty map — untagged events stay unknown; no invented coordinates. · frame 1 of 2

### map-empty-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/map-empty-mobile-part-2.svg) · state · mobile · Map — no geotagged events · frame 2 of 2 · parent `geographic-map`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Map — no geotagged events — frame 2 of 2; full coverage continues in the named companion frame.
3 — State scope note — what the state does and does not assert. · frame 2 of 2

### timeline-unknown-desktop.svg

[Open SVG](20261123-product-wireframes/timeline-unknown-desktop.svg) · state · desktop · Timeline — unknown date and raw status · parent `timeline`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Timeline — unknown date and raw status header — title, synthetic context and available actions.
3 — Timeline with an unknown date and an unexpected raw status — both labelled explicitly. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Status keys — the six states plus the unrecognized-raw-value label. · frame 1 of 1

### timeline-unknown-tablet.svg

[Open SVG](20261123-product-wireframes/timeline-unknown-tablet.svg) · state · tablet · Timeline — unknown date and raw status · parent `timeline`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Timeline — unknown date and raw status header — title, synthetic context and available actions.
3 — Timeline with an unknown date and an unexpected raw status — both labelled explicitly. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Status keys — the six states plus the unrecognized-raw-value label. · frame 1 of 1

### timeline-unknown-mobile.svg

[Open SVG](20261123-product-wireframes/timeline-unknown-mobile.svg) · state · mobile · Timeline — unknown date and raw status · frame 1 of 2 · parent `timeline`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Timeline — unknown date and raw status header — title, synthetic context and available actions.
3 — Timeline with an unknown date and an unexpected raw status — both labelled explicitly. · frame 1 of 2
4 — State scope note — what the state does and does not assert. · frame 1 of 2

### timeline-unknown-mobile-part-2.svg

[Open SVG](20261123-product-wireframes/timeline-unknown-mobile-part-2.svg) · state · mobile · Timeline — unknown date and raw status · frame 2 of 2 · parent `timeline`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Timeline — unknown date and raw status — frame 2 of 2; full coverage continues in the named companion frame.
3 — Status keys — the six states plus the unrecognized-raw-value label. · frame 2 of 2

### pipeline-unrecorded-desktop.svg

[Open SVG](20261123-product-wireframes/pipeline-unrecorded-desktop.svg) · state · desktop · Pipeline — stage unrecorded · parent `pipeline`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Pipeline — stage unrecorded header — title, synthetic context and available actions.
3 — Unrecorded stages — no attempt row exists; unrecorded is not success and not failure. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Configuration note — the configured count and recorded count differ honestly. · frame 1 of 1

### pipeline-unrecorded-tablet.svg

[Open SVG](20261123-product-wireframes/pipeline-unrecorded-tablet.svg) · state · tablet · Pipeline — stage unrecorded · parent `pipeline`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Pipeline — stage unrecorded header — title, synthetic context and available actions.
3 — Unrecorded stages — no attempt row exists; unrecorded is not success and not failure. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Configuration note — the configured count and recorded count differ honestly. · frame 1 of 1

### pipeline-unrecorded-mobile.svg

[Open SVG](20261123-product-wireframes/pipeline-unrecorded-mobile.svg) · state · mobile · Pipeline — stage unrecorded · parent `pipeline`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Pipeline — stage unrecorded header — title, synthetic context and available actions.
3 — Unrecorded stages — no attempt row exists; unrecorded is not success and not failure. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — Configuration note — the configured count and recorded count differ honestly. · frame 1 of 1

### monitoring-unavailable-desktop.svg

[Open SVG](20261123-product-wireframes/monitoring-unavailable-desktop.svg) · state · desktop · Monitoring — unavailable · parent `monitoring`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Monitoring — unavailable header — title, synthetic context and available actions.
3 — Unavailable monitoring — absence of recorded status, not a healthy or unhealthy verdict. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — What would appear — the reader's actual fields, none of which are health scores. · frame 1 of 1

### monitoring-unavailable-tablet.svg

[Open SVG](20261123-product-wireframes/monitoring-unavailable-tablet.svg) · state · tablet · Monitoring — unavailable · parent `monitoring`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Monitoring — unavailable header — title, synthetic context and available actions.
3 — Unavailable monitoring — absence of recorded status, not a healthy or unhealthy verdict. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — What would appear — the reader's actual fields, none of which are health scores. · frame 1 of 1

### monitoring-unavailable-mobile.svg

[Open SVG](20261123-product-wireframes/monitoring-unavailable-mobile.svg) · state · mobile · Monitoring — unavailable · parent `monitoring`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Monitoring — unavailable header — title, synthetic context and available actions.
3 — Unavailable monitoring — absence of recorded status, not a healthy or unhealthy verdict. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1
5 — What would appear — the reader's actual fields, none of which are health scores. · frame 1 of 1

### evidence-filter-empty-desktop.svg

[Open SVG](20261123-product-wireframes/evidence-filter-empty-desktop.svg) · state · desktop · Evidence — filter empty · parent `evidence-gallery`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Evidence — filter empty header — title, synthetic context and available actions.
3 — Active filters — the applied tier and capture filters that produced the empty result. · frame 1 of 1
4 — Filter-empty state — no rows match, which is not a case without sources. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### evidence-filter-empty-tablet.svg

[Open SVG](20261123-product-wireframes/evidence-filter-empty-tablet.svg) · state · tablet · Evidence — filter empty · parent `evidence-gallery`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Evidence — filter empty header — title, synthetic context and available actions.
3 — Active filters — the applied tier and capture filters that produced the empty result. · frame 1 of 1
4 — Filter-empty state — no rows match, which is not a case without sources. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### evidence-filter-empty-mobile.svg

[Open SVG](20261123-product-wireframes/evidence-filter-empty-mobile.svg) · state · mobile · Evidence — filter empty · parent `evidence-gallery`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Evidence — filter empty header — title, synthetic context and available actions.
3 — Active filters — the applied tier and capture filters that produced the empty result. · frame 1 of 1
4 — Filter-empty state — no rows match, which is not a case without sources. · frame 1 of 1
5 — State scope note — what the state does and does not assert. · frame 1 of 1

### narratives-empty-desktop.svg

[Open SVG](20261123-product-wireframes/narratives-empty-desktop.svg) · state · desktop · Narratives — none persisted · parent `narratives`

1 — Primary navigation — global destinations only (Network, Sources and Narratives open inside a case); GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.
2 — Narratives — none persisted header — title, synthetic context and available actions.
3 — Empty narratives — no stored clusters; the reader does not generate stance. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1

### narratives-empty-tablet.svg

[Open SVG](20261123-product-wireframes/narratives-empty-tablet.svg) · state · tablet · Narratives — none persisted · parent `narratives`

1 — Primary navigation (top bar) — global destinations only (case views open inside a case); GET reads only; CLI owns ingest and runs.
2 — Narratives — none persisted header — title, synthetic context and available actions.
3 — Empty narratives — no stored clusters; the reader does not generate stance. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1

### narratives-empty-mobile.svg

[Open SVG](20261123-product-wireframes/narratives-empty-mobile.svg) · state · mobile · Narratives — none persisted · parent `narratives`

1 — Primary navigation (menu) — the four global destinations; case views open inside a case; CLI owns ingest.
2 — Narratives — none persisted header — title, synthetic context and available actions.
3 — Empty narratives — no stored clusters; the reader does not generate stance. · frame 1 of 1
4 — State scope note — what the state does and does not assert. · frame 1 of 1

### flow.svg

[Open SVG](20261123-product-wireframes/flow.svg) · flow · desktop · Primary evidence-workbench flow · screens: case-explorer, claims, capture-inspector

1 — Flow title — reading rule stated before any transition; order is navigation, not execution.
2 — Thumbnail 1 — Case explorer (case-explorer); geometry-derived miniature, source text omitted.
3 — Transition 1 — 'open claim': navigation/review path only.
4 — Thumbnail 2 — Claims (claims); geometry-derived miniature, source text omitted.
5 — Transition 2 — 'inspect': navigation/review path only.
6 — Thumbnail 3 — Capture inspector (capture-inspector); geometry-derived miniature, source text omitted.
7 — Legend — thumbnail abstraction and grid rules; no automatic transition is implied.

### flow-claims-review.svg

[Open SVG](20261123-product-wireframes/flow-claims-review.svg) · flow · desktop · Claims, review and evidence flow · screens: capture-inspector, review-annotation, evidence-gallery

1 — Flow title — reading rule stated before any transition; order is navigation, not execution.
2 — Thumbnail 1 — Capture inspector (capture-inspector); geometry-derived miniature, source text omitted.
3 — Transition 1 — 'annotate': navigation/review path only.
4 — Thumbnail 2 — Review and annotation (review-annotation); geometry-derived miniature, source text omitted.
5 — Transition 2 — 'sources': navigation/review path only.
6 — Thumbnail 3 — Evidence gallery (evidence-gallery); geometry-derived miniature, source text omitted.
7 — Legend — thumbnail abstraction and grid rules; no automatic transition is implied.

### flow-compare-provenance.svg

[Open SVG](20261123-product-wireframes/flow-compare-provenance.svg) · flow · desktop · Comparison and provenance flow · screens: evidence-gallery, comparison, source-provenance

1 — Flow title — reading rule stated before any transition; order is navigation, not execution.
2 — Thumbnail 1 — Evidence gallery (evidence-gallery); geometry-derived miniature, source text omitted.
3 — Transition 1 — 'compare': navigation/review path only.
4 — Thumbnail 2 — Comparison (comparison); geometry-derived miniature, source text omitted.
5 — Transition 2 — 'deps': navigation/review path only.
6 — Thumbnail 3 — Source provenance (source-provenance); geometry-derived miniature, source text omitted.
7 — Legend — thumbnail abstraction and grid rules; no automatic transition is implied.

### flow-changes-history.svg

[Open SVG](20261123-product-wireframes/flow-changes-history.svg) · flow · desktop · Runs, snapshots and stage history flow · screens: runs-changes, historical-snapshot, stage-history

1 — Flow title — reading rule stated before any transition; order is navigation, not execution.
2 — Thumbnail 1 — Runs and changes (runs-changes); geometry-derived miniature, source text omitted.
3 — Transition 1 — 'snapshot': navigation/review path only.
4 — Thumbnail 2 — Historical snapshot (historical-snapshot); geometry-derived miniature, source text omitted.
5 — Transition 2 — 'stages': navigation/review path only.
6 — Thumbnail 3 — Run history (stage-oriented) (stage-history); geometry-derived miniature, source text omitted.
7 — Legend — thumbnail abstraction and grid rules; no automatic transition is implied.

### flow-search-snapshot.svg

[Open SVG](20261123-product-wireframes/flow-search-snapshot.svg) · flow · desktop · Search and snapshot flow · screens: search, historical-snapshot, case-overview

1 — Flow title — reading rule stated before any transition; order is navigation, not execution.
2 — Thumbnail 1 — Case search (search); geometry-derived miniature, source text omitted.
3 — Transition 1 — 'open': navigation/review path only.
4 — Thumbnail 2 — Historical snapshot (historical-snapshot); geometry-derived miniature, source text omitted.
5 — Transition 2 — 'context': navigation/review path only.
6 — Thumbnail 3 — Case overview (case-overview); geometry-derived miniature, source text omitted.
7 — Legend — thumbnail abstraction and grid rules; no automatic transition is implied.

### flow-operator-pipeline.svg

[Open SVG](20261123-product-wireframes/flow-operator-pipeline.svg) · flow · desktop · Operator, pipeline and monitoring flow · screens: operator-launch, pipeline, runs-changes, monitoring

1 — Flow title — reading rule stated before any transition; order is navigation, not execution.
2 — Thumbnail 1 — Operator launch guide (operator-launch); geometry-derived miniature, source text omitted.
3 — Transition 1 — 'run CLI': navigation/review path only.
4 — Thumbnail 2 — Pipeline monitor (pipeline); geometry-derived miniature, source text omitted.
5 — Transition 2 — 'observe': navigation/review path only.
6 — Thumbnail 3 — Runs and changes (runs-changes); geometry-derived miniature, source text omitted.
7 — Transition 3 — 'status': navigation/review path only.
8 — Thumbnail 4 — Monitoring (monitoring); geometry-derived miniature, source text omitted.
9 — Legend — thumbnail abstraction and grid rules; no automatic transition is implied.

### flow-review-exceptions.svg

[Open SVG](20261123-product-wireframes/flow-review-exceptions.svg) · flow · desktop · Review, exceptions and timeline flow · screens: review-annotation, exception-queue, timeline

1 — Flow title — reading rule stated before any transition; order is navigation, not execution.
2 — Thumbnail 1 — Review and annotation (review-annotation); geometry-derived miniature, source text omitted.
3 — Transition 1 — 'resolve': navigation/review path only.
4 — Thumbnail 2 — Exception queue (exception-queue); geometry-derived miniature, source text omitted.
5 — Transition 2 — 'in time': navigation/review path only.
6 — Thumbnail 3 — Timeline (timeline); geometry-derived miniature, source text omitted.
7 — Legend — thumbnail abstraction and grid rules; no automatic transition is implied.

### flow-geography-parties.svg

[Open SVG](20261123-product-wireframes/flow-geography-parties.svg) · flow · desktop · Parties, map and timeline flow · screens: parties, geographic-map, timeline

1 — Flow title — reading rule stated before any transition; order is navigation, not execution.
2 — Thumbnail 1 — Parties (parties); geometry-derived miniature, source text omitted.
3 — Transition 1 — 'map party': navigation/review path only.
4 — Thumbnail 2 — Geographic map (geographic-map); geometry-derived miniature, source text omitted.
5 — Transition 2 — 'date': navigation/review path only.
6 — Thumbnail 3 — Timeline (timeline); geometry-derived miniature, source text omitted.
7 — Legend — thumbnail abstraction and grid rules; no automatic transition is implied.

### flow-network-report.svg

[Open SVG](20261123-product-wireframes/flow-network-report.svg) · flow · desktop · Network, narratives and report flow · screens: corroboration-network, narratives, report

1 — Flow title — reading rule stated before any transition; order is navigation, not execution.
2 — Thumbnail 1 — Corroboration network (corroboration-network); geometry-derived miniature, source text omitted.
3 — Transition 1 — 'cluster': navigation/review path only.
4 — Thumbnail 2 — Narratives (narratives); geometry-derived miniature, source text omitted.
5 — Transition 2 — 'report': navigation/review path only.
6 — Thumbnail 3 — Report (report); geometry-derived miniature, source text omitted.
7 — Legend — thumbnail abstraction and grid rules; no automatic transition is implied.

### flow-dashboard-ai.svg

[Open SVG](20261123-product-wireframes/flow-dashboard-ai.svg) · flow · desktop · Dashboard, AI info, case and search flow · screens: dashboard, ai-info, case-overview, search

1 — Flow title — reading rule stated before any transition; order is navigation, not execution.
2 — Thumbnail 1 — Dashboard — case portfolio (dashboard); geometry-derived miniature, source text omitted.
3 — Transition 1 — 'capability': navigation/review path only.
4 — Thumbnail 2 — AI integration info (ai-info); geometry-derived miniature, source text omitted.
5 — Transition 2 — 'open case': navigation/review path only.
6 — Thumbnail 3 — Case overview (case-overview); geometry-derived miniature, source text omitted.
7 — Transition 3 — 'search': navigation/review path only.
8 — Thumbnail 4 — Case search (search); geometry-derived miniature, source text omitted.
9 — Legend — thumbnail abstraction and grid rules; no automatic transition is implied.
