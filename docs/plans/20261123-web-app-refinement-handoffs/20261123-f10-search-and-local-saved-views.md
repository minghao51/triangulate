---
id: F10
status: implemented-and-tested
tier: core
depends_on: [F02, F03, F06]
---

# F10 — Search and local saved views

**Size: L · Risk: localStorage privacy and quota behaviour.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Keep the current lexical-only search matrix; add inline filter validation, snippet accessibility and explicit opt-in local saved filter views.

## Read before edit (existing)
- `frontend/src/pages/tabs/SearchTab.tsx` (+ `SearchTab.test.tsx`) — existing 503/422/empty/out-of-range, plain snippets, all-term semantics, type/publisher/status/date filters
- `frontend/src/pages/tabs/ClaimsTab.tsx`, `frontend/src/pages/tabs/EvidenceTab.tsx` — F06's committed browse filters and existing filter bars
- `frontend/src/services/deep-links.ts` — `SEARCH_PARAMS` :292, `toSearchSearchParams` :322, `parseSearchSelection` :342, `buildSearchUrl` :357

## Proposed NEW paths
- PROPOSED saved-views helper beside `frontend/src/services/` (localStorage v1 per contracts §5)

## Implementation steps
1. Preserve the search matrix exactly; improve inline per-field validation before submit (no request on invalid); snippet accessibility (text alternatives, no colour-only markers).
2. Expose Save/apply/manage controls in the existing Search, Claims and Evidence filter bars, using F06's committed allowlists and one focused saved-views helper. Saved views v1: explicit user Save only (no autosave/history); per-origin ≤50, per-case ≤10, names 1–80 codepoints, serialized ≤64 KiB; allowlisted filter/sort/view metadata + case id only.
3. Query-text privacy: both search `q` and claim `claimQuery` are excluded by default; `includeQuery: true` requires a separate explicit warning + consent. A consented query is 1–256 codepoints and only valid on its owning view. Never store captures, notes, review drafts, author identity, full URLs, credentials or arbitrary JSON.
4. Robustness: validate all read-back; unknown version/corrupt entries handled without crash; delete one / delete case / delete all; quota/private-mode failure → visible ephemeral fallback. No server writes, sync, import/export.

## Non-goals
No historical/global search, no backend search changes, no cloud sync, no encrypted storage claims ('local' ≠ 'private').

## Acceptance criteria (testable)
1. Existing search state-matrix tests pass unchanged.
2. Invalid filters produce inline messages with zero network calls (spy).
3. Save/apply works on Search, Claims and Evidence; only allowlisted metadata is restored, without selected entity/paging IDs. Storing either `q` or `claimQuery` requires the extra consent step (test allowed and denied paths for each).
4. Corrupt/unknown-version entries never crash or overwrite stored data. Reset affects only this feature's namespace, never `localStorage.clear()`; cross-tab updates do not apply a view or reset a form.
5. Simulated quota failure shows the ephemeral fallback; all three delete paths work.

## Focused tests and commands
Extend `SearchTab.test.tsx`; PROPOSED helper tests beside the service; `npm test -- --run src/pages/tabs src/services`, then `npm run check`.

## Rollback and compatibility
Frontend-only; delete the helper + UI to roll back. Existing search API and committed URL contracts remain compatible; F06 filters are prerequisites, not reimplemented here.

## Worker brief (copy-paste)
You are the single code worker for F10 (this card). Read contracts doc §3, §5 and specification R08. Lexical matrix preserved; saved views strictly per contracts §5 including the query-text consent rule. Focused tests first, `npm run check` + `npm test -- --run`. No commits. Return hub §5 format.