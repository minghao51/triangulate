---
id: F02
status: implemented-and-tested
tier: core
depends_on: [F01]
---

# F02 — Case navigation and URL context

**Size: L · Risk: breaking existing deep links (inspector/comparison/changes/search families).**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Grouped route-backed case navigation with stable existing paths, plus allowlisted per-view URL state and correct historical/current boundaries.

## Read before edit (existing)
- `frontend/src/pages/CaseIntelligenceCenter.tsx` (12 route-backed tab buttons; navigate currently drops view state) + `CaseIntelligenceCenter.test.tsx`
- `frontend/src/services/deep-links.ts` — `INSPECTOR_PARAMS` :9, `COMPARISON_PARAMS` :140, `CHANGES_PARAMS` :220, `SEARCH_PARAMS` :292, builders `buildCaseTabUrl` :117, `buildComparisonUrl` :205 — + `deep-links.test.ts`
- Tab components under `frontend/src/pages/tabs/`

## Proposed NEW paths
None; extend `deep-links.ts` only.

## Implementation steps
1. Replace bare tab buttons with grouped native links + `aria-current` (no ARIA tab roles without the full keyboard pattern). Groups: Start (Overview, Search); Evidence (Evidence, Claims, Compare, Sources); Context (Parties, Map, Timeline, Network, Narratives); Review & Output (Exceptions, Report); Activity (Changes, Run history, Pipeline). Group headings create no routes. 12 tabs + 4 existing specialized routes (Sources, Network, Narratives, Pipeline) = 16 destinations; specialized routes keep their paths and get coherent case chrome without duplicate shells.
2. Add per-view param allowlists in `deep-links.ts`; drop unknown/unsupported params; no raw captured text in URLs. Exception: an explicit `snapshot` selector conflicting with a current-only view is **not** silently dropped — the view shows 'Unsupported historical view' before any fetch (or surfaces the API 422) with an intentional 'Open current' link as the only strip path. Session-memory of last committed per-view href per case; Back/reload restore committed URLs; 'Clear' is explicit.
3. Snapshot boundary: browser key `snapshot` maps to API `snapshotId`. Only claim/evidence/comparison GETs accept `snapshotId`; citations are frozen by citation ID and captures by capture ID; those GETs **reject** snapshot selectors with 422 (`src/http/app.py:526-544`, `Depends(reject_snapshot_selector)`) — the API client must never forward the browser snapshot to them. Current-only readers likewise reject snapshot selectors with 422; explicit 'Open current <view>' strips historical selectors. No new router/state engine.

## Non-goals
No new routes, no historical/global/vector search, no URL registry rewrite.

## Acceptance criteria (testable)
1. All previously valid case URLs still resolve (existing route tests pass unchanged).
2. Nav exposes exactly the five groups with `aria-current` on the active destination (DOM assertion).
3. Back/reload restores committed per-view state; an unlisted param is dropped (unit test on the parser).
4. Direct navigation to a current-only view with `?snapshot=...` (e.g. timeline/parties/search) shows an explicit 'Unsupported historical view' message before any fetch (or surfaces the API 422) — the param is never silently dropped to reveal live data; only the intentional 'Open current <view>' link strips historical selectors.
5. Cross-links land on the intended case+view; keyboard navigation works without ARIA-tab traps.

## Focused tests and commands
Extend `deep-links.test.ts` and `CaseIntelligenceCenter.test.tsx`; `npm test -- --run src/services src/pages`, then `npm run check`.

## Rollback and compatibility
URL builders keep existing signatures; old URLs remain valid. Revert is per-file.

## Worker brief (copy-paste)
You are the single code worker for F02 (this card). Read contracts doc §2–§3 and specification R02. Preserve every existing path; group nav is presentation over the same routes; URL state strictly allowlisted. Focused tests first, `npm run check` + `npm test -- --run`. No commits. Return hub §5 format.