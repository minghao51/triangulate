# Comparison navigation and panels (P03)

Date: 2026-11-18. Status: **implemented, pending Release B review**. Contract:
[specification](../plans/20261114-evidence-workbench-specification.md) §6, ticket
[P03](../plans/20261114-evidence-workbench-worker-plan.md). Depends on P02 and
E04. No backend behaviour changed in this ticket.

## Navigation and URL

A **Compare** tab now sits in the normal case navigation
(`/cases/{case_id}/compare`). The URL is the single selection authority:

```text
/cases/{case_id}/compare?left={evidenceId}&right={evidenceId}
  &leftCapture={captureId}&rightCapture={captureId}&offset={n}
```

`services/deep-links.ts` owns the encoded builders/parsers
(`buildComparisonUrl`, `parseComparisonSelection`,
`toComparisonSearchParams`) and is covered by unit tests. Reload, back/forward
and case switching re-derive the view from the URL. The API-resolved default
capture IDs are pinned into the URL with a replace navigation after the first
comparison response.

## Controls and states

- Two native source selects (the opposite source is disabled to prevent
  same-record comparison), two capture selectors populated from the evidence
  detail readers, Refresh/Compare, Swap sides and Clear.
- Distinct states: evidence-list loading/error/retry/empty, no second source,
  same-source validation, comparison loading, 404, network error/retry, empty
  row set, historical-capture unavailability and unsafe external URLs.
- Keyboard: native selects/buttons; the results heading receives focus once per
  selection key and is `tabIndex=-1`.
- Mobile: source panels stack below 960 px; the alignment table becomes labelled
  blocks below 760 px.

## Panels and alignment table

Each side shows title/publisher, safe original/canonical links, publication and
capture times, capture ID/kind, code-point length, content hash, recorded
analysis scope, publisher key (with a provisional-host note) and capture-link
coverage. Historical unavailability is explicit and current links are never
substituted.

Rows use the exact `claim_signature` alignment from P02:

- status labels are **Reported in both extractions**, **Extracted only on the
  left/right**;
- one-sided rows state that this is extraction coverage, not omission or
  disagreement;
- each side renders its persisted passages with quote, code-point range,
  relationship, alignment status, assessment origin/version and an **Open
  captured passage** link into the E04 inspector;
- contradiction appears only when P02 reports an explicitly assessed
  `contradicts`; the conflict badge is used only when the other side explicitly
  reports/supports. Textual difference alone never produces it;
- dependency/copy warnings show P01 reasons and the “not independent” message;
  absence of an edge is labelled as no detected dependency, not proven
  independence.
- pagination keeps `offset` in the URL.

## Tests and gates

- `CompareTab.test.tsx`: 10 tests — selection prompt, URL pinning, row statuses,
  contradiction wording, unsafe links, historical capture state, pagination,
  same-source rejection, 404 vs retry, focus.
- `deep-links.test.ts`: comparison URL encoding/parsing.
- Frontend: `npm run check` green; `npm test -- --run` = **107 passed in 12
  files**.
- Browser (isolated Playwright session, temporary DB/config): tab renders,
  default captures pin, reload persists, passage opens the inspector with the
  correct highlight and back returns, old capture shows historical
  unavailability, mobile stacks panels/table, keyboard focus traverses selects,
  source links use `noopener noreferrer`, missing evidence shows the distinct
  404 state, console **0 errors**, comparison/evidence requests GET-only.
- Backend unchanged: **456 passed, 9 deselected**, Ruff clean.

## Known limitations / deferred

- No saved snapshot selector until R03; historical availability is limited to
  persisted capture-linked assessments.
- Row identity remains exact `claim_signature`; paraphrases are not merged.
- Dependency coverage is exactly P01 v1; semantic/near-duplicate detection is
  deferred.
- Pagination is client-controlled by URL offset (25 rows per page).
