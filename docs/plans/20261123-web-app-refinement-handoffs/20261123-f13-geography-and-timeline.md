---
id: F13
status: implemented-and-tested
tier: core
depends_on: [F02, F03, F08]
---

# F13 — Geography and timeline

**Size: M · Risk: coordinate/status semantics drift (0,0 vs unknown vs invalid).**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Map markers and timeline entries honour stored data exactly: finite in-range coordinates only, six valid statuses plus explicit unrecognized, no invented linkage or chronology.

## Read before edit (existing)
- `frontend/src/pages/tabs/MapTab.tsx` (+ `MapTab.css`) — plain CSS projected markers, currently `typeof number` only
- `frontend/src/pages/tabs/TimelineTab.tsx` (+ `TimelineTab.test.tsx`, `.css`)
- `frontend/src/types/backend-models.ts` — `TimelineEvent.locationLat/locationLon` nullable, optional country code

## Proposed NEW paths
PROPOSED coordinate-validation helper beside the tabs (pure functions, unit-testable).

## Implementation steps
1. Coordinates: finite numbers with latitude ∈ [-90, 90], longitude ∈ [-180, 180] plotted; **invalid** (out-of-range/non-finite) and **missing** are distinct states; 0,0 is recorded at 0,0 — never 'unknown'; no centroid inference, no geocoder/tiles/browser location permissions.
2. Accessible linked event list beside the marker field; bi-directional selection with recorded IDs only; an event without known claims navigates to event context/list — never an invented inspector claim ID.
3. Timeline statuses exactly: confirmed/probable/alleged/contested/debunked/unknown; unexpected stored value renders 'Unrecognized status' with the raw value preserved.
4. Date-unknown is separate from status; no 1970 placeholders; no inferred chronology or geography.

## Non-goals
No map library/tiles, no geocoding, no coordinate repair/backfill (D01), no new API.

## Acceptance criteria (testable)
1. Inclusive finite boundaries latitude ±90 and longitude ±180 are valid; immediately outside those ranges, NaN and Infinity are invalid and excluded (unit tests).
2. 0,0 plots as recorded; missing coordinates render as unknown — three states visibly distinct.
3. List row ↔ marker selection works both directions with only recorded IDs (interaction test).
4. A fixture with an out-of-enum status renders 'Unrecognized status' + raw value.
5. No synthetic dates: date-unknown events show no epoch placeholder.

## Focused tests and commands
Extend `TimelineTab.test.tsx`; PROPOSED `MapTab.test.tsx` + helper unit tests beside the components; `npm test -- --run src/pages/tabs`, then `npm run check`.

## Rollback and compatibility
Frontend-only validation/presentation; stored data untouched (no repair — that is D01).

## Worker brief (copy-paste)
You are the single code worker for F13 (this card). One application code writer globally — hub waves are eligibility order only. Read contracts doc §3 and specification R11. Finite in-range coordinates only; invalid/missing/0,0 semantics as stated; six statuses + unrecognized raw. Focused tests first, `npm run check` + `npm test -- --run`. No commits. Return hub §5 format.