# Web-app refinement implementation hub (2026-11-23)

Status: **EXECUTED** for all 22 tasks (17 core + 5 optional). Actual edits and actual gate runs are
recorded per card in [the execution evidence log](20261123-web-app-refinement-evidence.md). Counts there
are dated observations, not frozen totals. No commit, deployment or production-data repair was made.
Product requirements: [specification](20261123-web-app-refinement-specification.md). Shared rules:
[technical contracts](20261123-web-app-refinement-contracts.md) ("the contracts doc").

## 1. Recommended core phase order

Dependency-respecting eligibility waves, not parallel code-writing groups. Exactly one application
code worker is active across the project at a time; ready tasks may be ordered within a wave.
Read-only review may run independently. Every ticket remains parent-gated:

| Wave | Tasks | Gate before next wave |
|---|---|---|
| 0 | F00 | Baseline + disposable-copy fixture variants exist; gate inventory recorded |
| 1 | F01, F05 | Shell truthful/responsive; annotation-target 404/422 contract landed |
| 2 | F02, F03 | Grouped nav + URL context; reader/query migration pattern established |
| 3 | F04, F06, F14 | Review/annotation UX, claims/evidence reader, report reader |
| 4 | F07, F08, F10 | Comparison tray; inspector states/reading; search+saved views built on browse filters |
| 5 | F09, F11, F12, F13 | Source provenance, run history/frozen, linked analysis, map/timeline |
| 6 | F15 | Operator/portfolio coherence |
| 7 | F16 | Core integration + release gate (24 screens / 42 states / 3 viewports) |

Optional track after F16: F17 ∥ F19 → F18 (needs F17+F11), F20 (needs F19+F14+F11) → F21.

## 2. Safety and approval decisions (summary; contracts doc is authoritative)

- One code worker per task (`deepseek-v4.1-flash`), no recursion; read-only independent review then
  parent-run gates per ticket. Preserve all dirty worktree files; no commits/pushes without
  instruction. All backend verification in a **disposable copy of the current worktree** (dirty bytes
  included) with scratch config/DB/output; never `data/`, `triangulate.db`, `.env`, `logs/`,
  `config.toml`. Never repair historical data/case ownership (D01 is a separate owner gate).
- Commands: focused tests first; `uv run pytest -q --disable-warnings` +
  `uv run ruff check src tests scripts --output-format concise` in the disposable copy;
  `npm run check` + `npm test -- --run` after frontend changes; node/npm from `frontend/.nvmrc`;
  fresh `npm ci` in isolated copy at F00/F16. Browser: playwright-cli skill, isolated headless,
  synthetic API/DB, own server/browser lifecycle; Chromium+Firefox+WebKit where available — missing
  engine ⇒ "not proven", never PASS.
- New core DB schema: none. New APIs: only X01/X02 as **PROPOSED**, separately approved, after F16.
  Core write surface stays the three POST families (review, exceptions, annotations).
- Approval boundaries: proposal ≠ owner approval; read-only API approval ≠ production repair/deploy
  approval; D01 ≠ feature approval.

Before dispatch, record the owner's choices:

- [ ] Approve the 17 core tasks F00–F16 and their bounded file scopes.
- [ ] Accept F05's deliberate corrections: invalid/foreign annotation targets become uniform 422;
  missing-case activity/evaluation HTTP reads become 404 rather than an unmapped failure, while
  the direct-service `ValueError` regression remains valid.
- [ ] Approve the saved-view privacy policy, including separate consent for saving query text.
- [ ] Separately approve X01/F17–F18, or leave it deferred.
- [ ] Separately approve X02/F19–F20 and its artifact roots/type/size policy, or leave it deferred.
- [ ] Keep production deployment, historical-data recovery and public access out of this approval.

None of these boxes is checked by producing this document. The optional ∥ notation below denotes
logical independence, not permission for concurrent application code writers.

## 3. Task table (22 cards)

All cards live in [`20261123-web-app-refinement-handoffs/`](20261123-web-app-refinement-handoffs/).
Status for every row: **implemented-and-tested** (`status: implemented-and-tested` in card
frontmatter); per-card commands, counts and evidence pointers are in the
[execution evidence log](20261123-web-app-refinement-evidence.md). Sizes are relative S/M/L with named
risk — not deadlines.

| ID | Task | Tier | Depends on | Size & primary risk | Card |
|---|---|---|---|---|---|
| F00 | baseline-and-fixtures | core | — | M — snapshot must not touch dirty worktree | [F00](20261123-web-app-refinement-handoffs/20261123-f00-baseline-and-fixtures.md) |
| F01 | truthful-responsive-shell | core | F00 | M — CSS regressions across 3 viewports | [F01](20261123-web-app-refinement-handoffs/20261123-f01-truthful-responsive-shell.md) |
| F02 | case-navigation-and-url-context | core | F01 | L — breaking existing deep links | [F02](20261123-web-app-refinement-handoffs/20261123-f02-case-navigation-and-url-context.md) |
| F03 | consistent-reader-states | core | F01 | L — query-key collisions / late responses | [F03](20261123-web-app-refinement-handoffs/20261123-f03-consistent-reader-states.md) |
| F04 | contextual-review-and-annotations | core | F02, F03, F05 | L — 409/422/uncertainty semantics | [F04](20261123-web-app-refinement-handoffs/20261123-f04-contextual-review-and-annotations.md) |
| F05 | annotation-target-and-reader-contracts | core | F00 | M — preserve direct callers/CLI while correcting HTTP errors | [F05](20261123-web-app-refinement-handoffs/20261123-f05-annotation-target-and-reader-contracts.md) |
| F06 | claims-and-evidence-browsing | core | F02, F03 | L — render budget on loaded arrays | [F06](20261123-web-app-refinement-handoffs/20261123-f06-claims-and-evidence-browsing.md) |
| F07 | two-source-comparison-tray | core | F06 | M — cross-context/cross-case mixing | [F07](20261123-web-app-refinement-handoffs/20261123-f07-two-source-comparison-tray.md) |
| F08 | inspector-states-and-responsive-reading | core | F06 | L — Unicode offset fidelity | [F08](20261123-web-app-refinement-handoffs/20261123-f08-inspector-states-and-responsive-reading.md) |
| F09 | comparison-and-source-provenance | core | F07, F08 | M — overclaiming independence | [F09](20261123-web-app-refinement-handoffs/20261123-f09-comparison-and-source-provenance.md) |
| F10 | search-and-local-saved-views | core | F02, F03, F06 | L — privacy/quota of localStorage | [F10](20261123-web-app-refinement-handoffs/20261123-f10-search-and-local-saved-views.md) |
| F11 | run-history-and-frozen-navigation | core | F02, F03, F08 | L — stage vs grouped-run ID conflation | [F11](20261123-web-app-refinement-handoffs/20261123-f11-run-history-and-frozen-navigation.md) |
| F12 | linked-analysis-exploration | core | F02, F03, F08 | M — node-ID test regressions | [F12](20261123-web-app-refinement-handoffs/20261123-f12-linked-analysis-exploration.md) |
| F13 | geography-and-timeline | core | F02, F03, F08 | M — coordinate/status semantics drift | [F13](20261123-web-app-refinement-handoffs/20261123-f13-geography-and-timeline.md) |
| F14 | report-reader-and-download-recovery | core | F03 | S — unsafe markdown rendering | [F14](20261123-web-app-refinement-handoffs/20261123-f14-report-reader-and-download-recovery.md) |
| F15 | operator-and-portfolio-coherence | core | F01, F03, F11 | M — polling load multiplication | [F15](20261123-web-app-refinement-handoffs/20261123-f15-operator-and-portfolio-coherence.md) |
| F16 | core-integration-and-release-gate | core | F00–F15 | L — engine availability / evidence assembly | [F16](20261123-web-app-refinement-handoffs/20261123-f16-core-integration-and-release-gate.md) |
| F17 | snapshot-comparison-read-api | optional | F16 | M — misuse of `build_snapshot_delta` | [F17](20261123-web-app-refinement-handoffs/20261123-f17-snapshot-comparison-read-api.md) |
| F18 | snapshot-comparison-interface | optional | F17, F11 | M — ad-hoc vs recorded conflation | [F18](20261123-web-app-refinement-handoffs/20261123-f18-snapshot-comparison-interface.md) |
| F19 | historical-artifact-read-api | optional | F16 | L — path traversal/symlink/race | [F19](20261123-web-app-refinement-handoffs/20261123-f19-historical-artifact-read-api.md) |
| F20 | historical-report-interface | optional | F19, F14, F11 | M — plausible "latest" substitution | [F20](20261123-web-app-refinement-handoffs/20261123-f20-historical-report-interface.md) |
| F21 | extended-history-release-gate | optional | F18, F20 | M — partial-bundle acceptance drift | [F21](20261123-web-app-refinement-handoffs/20261123-f21-extended-history-release-gate.md) |

## 4. Shared worker dispatch template

> Approval record: {explicit owner decision/date/scope}. Verified dependencies: {IDs with actual
> acceptance evidence}. Baseline: {HEAD, preserved dirty paths and current relevant behavior}.
> Allowed files: {bounded list from this card}; stop if additional API/schema/scope is needed.
> You are the single application code worker for task **{ID} — {slug}**. Read in full first:
> [the contracts doc](20261123-web-app-refinement-contracts.md) (safety, presentation, state, privacy
> and API contracts), [the specification](20261123-web-app-refinement-specification.md) requirement
> **{Rxx}**, and your card `docs/plans/20261123-web-app-refinement-handoffs/{file}`. Work only inside
> the card's scope and allowed paths; do not delegate or recurse; preserve all dirty worktree files;
> no commits. All backend verification runs in a disposable copy of the current worktree per contracts
> §1. Frontend changes: `npm run check` + `npm test -- --run`, focused tests first. New APIs in your
> card are marked PROPOSED — implement only when this dispatch includes their explicit approval. Report back in
> the shared return format below. Proposal ≠ approval; do not mark anything "done" beyond your actual
> edits and actual test runs, with commands and counts.

## 5. Shared return format

```text
Task: {ID} — {slug}
Status: {implemented-and-tested | partially-implemented | blocked | stopped-for-approval}
Diff: {files added/changed, one line each; NO commit made}
Tests run (exact commands): {...}
Results: {counts per command; engines available/unproven}
Acceptance criteria: {AC1..ACn -> met/not-met with evidence pointer}
Coverage touched: {screens/states from §6}
Risks/rollback: {...}
Requires owner decision: {none | question(s)}
```

## 6. Coverage inventory — 24 primary screens and 42 selected states

Wireframe basis: [wireframe set](20261123-product-wireframe-set.md) + [SVG folder](20261123-product-wireframes/)
(24 + 42 = 66 definitions × 3 viewports + 55 continuation frames + 10 flows = 263 SVG; static design
only). F16 must evidence all of the below at 375×812, 768×1024, 1280×800 (+200 % zoom, keyboard,
text-not-colour).

| # | Screen | Owner | Card |
|---|---|---|---|
| 1 | dashboard | F15 | [F15](20261123-web-app-refinement-handoffs/20261123-f15-operator-and-portfolio-coherence.md) |
| 2 | case-explorer | F15 | [F15](20261123-web-app-refinement-handoffs/20261123-f15-operator-and-portfolio-coherence.md) |
| 3 | operator-launch | F15 | [F15](20261123-web-app-refinement-handoffs/20261123-f15-operator-and-portfolio-coherence.md) |
| 4 | case-overview | F04 | [F04](20261123-web-app-refinement-handoffs/20261123-f04-contextual-review-and-annotations.md) |
| 5 | review-annotation | F04 | [F04](20261123-web-app-refinement-handoffs/20261123-f04-contextual-review-and-annotations.md) |
| 6 | evidence-gallery | F06 | [F06](20261123-web-app-refinement-handoffs/20261123-f06-claims-and-evidence-browsing.md) |
| 7 | claims | F06 | [F06](20261123-web-app-refinement-handoffs/20261123-f06-claims-and-evidence-browsing.md) |
| 8 | capture-inspector | F08 | [F08](20261123-web-app-refinement-handoffs/20261123-f08-inspector-states-and-responsive-reading.md) |
| 9 | comparison | F09 | [F09](20261123-web-app-refinement-handoffs/20261123-f09-comparison-and-source-provenance.md) |
| 10 | source-provenance | F09 | [F09](20261123-web-app-refinement-handoffs/20261123-f09-comparison-and-source-provenance.md) |
| 11 | runs-changes | F11 | [F11](20261123-web-app-refinement-handoffs/20261123-f11-run-history-and-frozen-navigation.md) |
| 12 | historical-snapshot | F11 | [F11](20261123-web-app-refinement-handoffs/20261123-f11-run-history-and-frozen-navigation.md) |
| 13 | search | F10 | [F10](20261123-web-app-refinement-handoffs/20261123-f10-search-and-local-saved-views.md) |
| 14 | stage-history | F11 | [F11](20261123-web-app-refinement-handoffs/20261123-f11-run-history-and-frozen-navigation.md) |
| 15 | pipeline | F15 | [F15](20261123-web-app-refinement-handoffs/20261123-f15-operator-and-portfolio-coherence.md) |
| 16 | exception-queue | F04 | [F04](20261123-web-app-refinement-handoffs/20261123-f04-contextual-review-and-annotations.md) |
| 17 | parties | F12 | [F12](20261123-web-app-refinement-handoffs/20261123-f12-linked-analysis-exploration.md) |
| 18 | geographic-map | F13 | [F13](20261123-web-app-refinement-handoffs/20261123-f13-geography-and-timeline.md) |
| 19 | timeline | F13 | [F13](20261123-web-app-refinement-handoffs/20261123-f13-geography-and-timeline.md) |
| 20 | report | F14 | [F14](20261123-web-app-refinement-handoffs/20261123-f14-report-reader-and-download-recovery.md) |
| 21 | corroboration-network | F12 | [F12](20261123-web-app-refinement-handoffs/20261123-f12-linked-analysis-exploration.md) |
| 22 | narratives | F12 | [F12](20261123-web-app-refinement-handoffs/20261123-f12-linked-analysis-exploration.md) |
| 23 | monitoring | F15 | [F15](20261123-web-app-refinement-handoffs/20261123-f15-operator-and-portfolio-coherence.md) |
| 24 | ai-info | F15 | [F15](20261123-web-app-refinement-handoffs/20261123-f15-operator-and-portfolio-coherence.md) |

States, grouped by parent category (state owner = category owner; the shared recipe is owned by F03
and rendered per screen; F16 evidences all):

| Category | States | Owner |
|---|---|---|
| shared | shared-loading, shared-empty, shared-not-found, shared-network-error | F03 recipe (all screens render; F16 verifies) |
| inspector | inspector-missing-quotation, inspector-source-unavailable, inspector-ambiguous, inspector-no-match, inspector-legacy | F08 |
| comparison | comparison-selection, comparison-same-source, comparison-no-second-source, comparison-empty, comparison-historical-unavailable, comparison-dependency-warning | F09 (selection/tray behaviour fed by F07) |
| changes | changes-initial, changes-pending, changes-unavailable, changes-unchanged-partial | F11 |
| search | search-no-results, search-index-unavailable, search-invalid-filters, search-out-of-range | F10 |
| review | review-saving, review-failed, review-stale, review-saved, review-blocked | F04 |
| annotation | annotation-invalid | F04 (UI) / F05 (uniform 422) |
| exception | exception-pending, exception-failed, exception-empty | F04 |
| evaluation | evaluation-unavailable, evaluation-failed | F04 (reader contract via F05) |
| report | report-pending, report-download-error | F14 |
| map | map-empty | F13 |
| timeline | timeline-unknown | F13 |
| pipeline | pipeline-unrecorded | F15 |
| monitoring | monitoring-unavailable | F15 |
| evidence | evidence-filter-empty | F06 |
| narratives | narratives-empty | F12 |

(4 + 5 + 6 + 4 + 4 + 5 + 1 + 3 + 2 + 2 + 1 + 1 + 1 + 1 + 1 + 1 = 42 states.)

## 7. Requirement → task traceability

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
| X01 snapshot comparison (optional) | F17, F18, F21 |
| X02 historical artifacts (optional) | F19, F20, F21 |

## 8. Optional DAG (executed)

```text
core: F00 -> F01 -> {F02, F03} -> {F04, F06, F14} -> {F07, F08, F10}
      -> {F09, F11, F12, F13} -> F15 -> F16      (F05: F00 -> F05 -> F04)
optional (after F16, separate owner approval per API):
      F16 -> F17 -> F18 ┐
      F16 -> F19 -> F20 ├-> F21
      (F18 also needs F11; F20 also needs F14, F11)
```

F21 covers the **full** optional bundle. Both tracks (X01 and X02) were approved and delivered, so F21
records **full-bundle accepted**. If only one track is ever approved, run that track's required tests and
record F21 as not-full-bundle-accepted.

## 9. Non-gating advisory guardrails (not approval)

- Proposed performance budgets (contracts §8) are targets to record, not benchmarks to claim.
- Historical gate counts (e.g. 2026-11-21: 614 backend / 164 frontend) are prior evidence only —
  re-run gates for today's claims; actual unit counts after refinement are not frozen.
- A missing browser engine is a scoped defer recorded by the owner, never a PASS.
- Stylistic Markdown advisories are informational. Broken links, contradictory contracts, unmet
  dependencies and failed required checks block dispatch.

## 10. Documentation verification record

This planning pass checked all 25 new documents: 22 task cards (17 core, five optional), exact task
IDs/tiers/dependencies, an acyclic dependency graph, all 24 primary surfaces and 42 selected states,
and 134 relative links. Active Markdown LSP error checks were clean. Existing tracked changes and
pre-existing untracked paths/modified times were preserved; only the 25 planning files and two
plans-index bullets were introduced. Proposed future code/test paths are explicitly marked NEW.

These are documentation checks, not frontend/backend/browser application gates. No application code,
schema, configuration, runtime data, deployment or commit was changed by this planning pass.

## 11. Execution record

All 22 cards were executed after the planning pass. Every card's actual edits, commands, counts and
acceptance notes are in [the execution evidence log](20261123-web-app-refinement-evidence.md), including
the F16/F21 browser matrices, the F17/F19 optional security matrices and the recorded limitations
(WebKit engine not proven on this host; the tokenizer-level residual race noted for F19; the evidence
DTO's missing publication timestamp noted for F06).
