# R02 — Preserve historical context in deep links (P1)

**Status:** Implemented and verified in `34ca121` ([evidence](../20261124-audit-remediation-evidence.md)) · **Sequencing:** after R01 when sharing the checkout.  
[Specification](../20261124-audit-remediation-specification.md) · [URL contract §3](../../../plans/20261123-web-app-refinement-contracts.md#3-client-state-paging-and-url-contract)

## Problem and read-before-edit

`frontend/src/pages/CaseIntelligenceCenter.tsx` runs a `?citation=` redirect before enforcing the historical-view gate. Its destination is built with only `citationId`. Audit repro: open `/cases/case-example/timeline?snapshot=snap-example&citation=cite-example`; the resulting active tab is `/cases/case-example/evidence?citation=cite-example`. Inspect the navigation effect, URL sanitizer and per-view allowlists in `frontend/src/services/deep-links.ts`, both evidence views (`EvidenceTab`, `EvidenceInspector`), `ChangesTab`, and `src/http/app.py` claim/evidence/citation readers. Existing case tests have snapshots without citations; don't weaken those assertions.

**Important distinction:** Evidence and Changes are the two snapshot-aware *destinations*; parts of Evidence (gallery/list) still read current data, and the citation endpoint is frozen **by citation ID**, not by snapshot. It rejects snapshot selectors. Simply forwarding `snapshot` to that endpoint or adding it to the URL while continuing to render the unverified citation under a snapshot label is not correct.

## Required routing policy

| Input | Result |
| --- | --- |
| Any current-only case view + explicit `snapshot`, with or without `citation` | Render the unsupported-historical state **before mounting its data consumer**; no citation redirect, current tab read, or historical-pin rewrite. The explicit **Open current [view]** link removes the pin and preserves only the destination's valid browse state; it must not resurrect the citation redirect. |
| Evidence + valid snapshot with claim/evidence selection and no citation | Keep snapshot and selection. Call the appropriate snapshot-aware detail reader; never replace missing pinned content with a current query. Do not load/show the current Evidence gallery or its selection/editing affordances while pinned. |
| Evidence + explicit snapshot and citation | Do not imply the independent citation proves snapshot membership. Show an explicit selector-conflict state without issuing citation or current Evidence reads. Offer clear user choices: keep the snapshot (drop citation, preserve valid pinned selectors) or explicitly **Open frozen citation by ID** (drop the snapshot, use the existing citation-only URL). Neither transition runs automatically. |
| Changes + historical context (`snapshot` or explicit ad-hoc mode/pair) with a stray `citation` | Stay on Changes; preserve the snapshot and valid run/claim/ad-hoc selectors. Drop the unsupported citation through allowlist normalization, or surface it without changing context. An incomplete ad-hoc selection stays in Changes so the user can correct it. |
| Valid citation without a historical selection | Preserve legacy citation-only behavior: existing explicit links resolve on Evidence; supported legacy non-Evidence landing URLs may redirect there with `replace`, once. Validate and encode the citation, not arbitrary query strings. Existing current-only browse and normal legacy evidence links stay functional. |
| Empty, invalid or ambiguous explicit snapshot selector | Visible invalid/unavailable state rather than deleting the pin and rendering live evidence. Don't pick a side of conflicting duplicate snapshot parameters. No path to current data except a clear user action. |

Use one decision point for redirect/gate/canonicalization; none should race another effect or write a state that session-memory navigation can later restore as if it were pinned. An independently labeled case header/context read is outside the blocked tab-data contract; do not turn the shared case detail DTO into a historical payload. For Evidence with a valid pin and no claim/evidence selection, show explicit historical context and a usable escape/action, not a current gallery. Inspector close may clear the selection but must not clear the pin. Capture-window details may only be read from a recorded pin; no new endpoint or widening of scope.

Keep Back/Forward, reload, explicit current escape, and case isolation predictable; preserve supported selectors only and never forward arbitrary route state to API calls. The invalid/unsupported state must expose an accessible recovery link. No frozen-citation membership endpoint, cross-case fallback, or change to API selector names in this card.

## Regression and acceptance

- `CaseIntelligenceCenter.test.tsx`: reproduce the exact combined Timeline URL; assert stable path/selector, unsupported state, and zero timeline/citation/current-evidence tab reads. Activate **Open current Timeline** and see exactly the intended view and fetch, no fallback redirect. Exercise overview and claims equivalents.
- Evidence/inspector tests: direct pinned claim and evidence (successful and missing), pinned URL without selected entity, and direct pinned citation conflict before any conflicting request. Assert no call to the current gallery during the pin, exact `snapshotId` on supported detail reads, no `snapshotId` on independent citation reads, and no generic fallback after 404. Verify both explicit choices, close inspector, and switch between pins without stale display.
- Changes: combined selectors, pinned ad-hoc pair with stray citation, current legacy citation compatibility, encoded ID, invalid/empty selector or conflicting duplicate. Verify reload/history and session-memory behavior at least in a browser case; assert URL and request selection, not only a heading.
- Existing history/citation fallbacks and frozen capture behavior remain green. Use frontend focused suites: `npm run test:ci -- src/pages/CaseIntelligenceCenter.test.tsx src/pages/tabs/EvidenceTab.test.tsx src/components/inspector/EvidenceInspector.test.tsx src/pages/tabs/ChangesTab.test.tsx src/services/deep-links.test.ts`, then `npm run check` (in `frontend/`). Add browser regression to existing gate suite where appropriate.

**Worker brief:** Implement R02 only. Freeze a routing table before editing; preserve snapshot semantics and legacy citation-only links without implying membership or showing current data under a pin. Report exact test evidence, zero-fallback assertions and any intentional legacy behavior change. Do not commit or push.
