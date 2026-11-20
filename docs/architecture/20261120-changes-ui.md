# Changes and grouped history UI (R04)

Date: 2026-11-20. Status: **delivered and verified frontend-only; owner/parent diff
review pending.** Depends on R03a (stored snapshots/deltas and run GETs), R03b
(snapshot-aware claim/evidence readers) and R03c (origin/observer split). Contract:
[specification](../plans/20261114-evidence-workbench-specification.md) §7, ticket
[R04](../plans/20261114-evidence-workbench-worker-plan.md).

## Why this exists

Release C's fourth capability is “what changed since the last successful
observation?”. The API stores that as typed deltas on immutable snapshots; this
ticket adds the read-only surface that shows them without inventing history,
attribution or a change surge.

## Surface

A new **Changes** tab in the normal case workspace
(`/cases/{case_id}/changes`), next to the unchanged stage-oriented **Run
History** tab. It is not a global monitoring platform: everything is case-scoped.

The URL is the only selection authority:

| Parameter | Meaning |
|---|---|
| `run` | Selected grouped investigation run; defaults (and is pinned with `replace`) to the newest, and an unknown ID is replaced rather than showing another run |
| `offset` | Page offset for the typed-change list (25 per page) |
| `claim` + `snapshot` | Opens the inline frozen-claim panel for one observed claim |

Reload, back/forward and case switching re-derive everything from the URL, and a
“Permalink for this selection” link reproduces it. A missing `run` is only pinned
after the run list loads, so an initial render never invents a selection.

## Data

- `GET /api/cases/{id}/investigation-runs?limit=50` — grouped runs (sequence,
  trigger, status, coverage, timestamps, snapshot IDs). The selector lists the
  latest 50 and says so when more exist.
- `GET /api/cases/{id}/investigation-runs/{run_id}/changes?limit&offset` —
  availability, baseline/target snapshot IDs, coverage + note, typed items.
- `GET /api/cases/{id}/claims/{claim_id}?snapshotId=`,
  `GET .../evidence/{evidence_id}?snapshotId=` — the frozen claim panel and the
  passage/evidence links. Nothing is recomputed from current rows.

Entity links follow what the snapshot readers can actually resolve:

| Change | Destination |
|---|---|
| `claim_added`, `classification_changed` | inline frozen claim at the **target** snapshot |
| `claim_no_longer_extracted` | inline frozen claim at the **baseline** snapshot that still holds it |
| `capture_changed` | evidence inspector with the target `snapshotId` |
| `article_added` | safe external `http(s)` link only (no article reader) |
| `relationship_changed` | no link — a link row has no reader and no recorded run |
| `review_state_changed`, `exception_changed` | no link; before/after values only |

Unsafe URL schemes (`javascript:`, `data:`) are never rendered as links, and the
inspector's 404 state distinguishes “not found for this case” from “may not be
present in the selected snapshot”.

## Truthful states

| Stored state | Rendering |
|---|---|
| `initial` | “First observation — no earlier successful observation to compare. It is not a surge of new changes.” |
| `pending` | “Run in progress — changes are not final.” Never shown as an empty delta. |
| `unavailable` | “Historical change data unavailable — no snapshot was published. This is not an empty delta.” Failed/paused/interrupted runs additionally state that they never advance the successful baseline, and the recorded error is shown when present. |
| `ready`, no items | “Unchanged — no changes in observed data between these two observations.” With incomplete coverage it also says this proves nothing about sources outside the scope. |
| `ready`, items | Typed rows with before/after fields, entity type/ID and the two run facts. |

Coverage other than `complete_requested_scope` always shows a conspicuous warning
(`coverageNote` plus “an empty list means no changes in observed data — not that
every source was unchanged”), including when the delta is empty.

Every item shows **`originRunId`** (“Recorded by run …”, or “origin not recorded”
when null) separately from **`observedByRunId`** (“Observed by run …”). Neither is
ever worded as who changed, confirmed or caused a value. “No longer extracted” is
labelled as a change in extraction, not a retraction.

## Frozen claim panel

Opening a claim link fetches the snapshot-aware claim detail and renders the
frozen text, signature, verification status + provenance, claim type, evidence
link count, and each recorded passage (quotation, effective relation, alignment,
capture, source title) with an “Open passage in evidence inspector” link that
carries the same `snapshotId`. A live-state line says whether the live claim is
gone, rewritten or unchanged — factually, without attribution. Closing the panel
clears `claim`/`snapshot` from the URL; switching runs clears them too.

## Verification

Frontend gates: `npm run check` (lint + typecheck + build) green;
`npm test -- --run` = **132 tests / 13 files**, including
`src/pages/tabs/ChangesTab.test.tsx` (16 cases: default-run pinning and stale-ID
replacement, initial/pending/unavailable/ready+partial/ready+complete, before/after
rendering with separate run facts, claim/evidence/article/link destinations,
unsafe URLs, pagination offset in the URL, run switching resets offset, no-runs vs
no-changes, retry, frozen claim + missing-claim states) and
`src/components/inspector/EvidenceInspector.test.tsx` snapshot cases (claim and
evidence resolution, live-state wording, snapshot-specific 404, citation reader
never receives the selector).

Isolated browser check (Vite-only server, intercepted `/api/**` with synthetic
fixtures, no backend and no database): default selection pinned to the newest run;
failed run → unavailable (not “unchanged”); run switch → partial-coverage warning,
origin/observed lines and “origin not recorded”; frozen claim panel shows the
withdrawn claim with “live case no longer contains this claim”; passage link
`/cases/case-1/evidence?claim=claim-gone&evidence=ev-9&capture=cap-1&snapshot=snap-1`
opened the inspector with the historical banner; pending and initial states
rendered distinctly; 390 px viewport stacked the layout to a single 358 px column;
**0 non-GET requests, 0 console errors** after interception, 274 intercepted
requests. Artifacts: `/tmp/r04-changes-desktop.png`,
`/tmp/r04-browser-result.txt`, `/tmp/r04-vite.log`. Browser and dev server were
closed by the reviewer.

## Limits

- No diffing, filtering or search inside the changes surface; it shows the stored
  delta as observed.
- Pending runs are not polled; the Refresh button refetches runs and the selected
  delta, and the case header keeps its existing case-detail polling.
- `relationship_changed` rows show before/after only, because no link reader
  exists.
