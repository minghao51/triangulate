---
id: F01
status: implemented-and-tested
tier: core
depends_on: [F00]
---

# F01 — Truthful responsive shell

**Size: M · Risk: CSS regressions across the three wireframe viewports.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Remove fabricated status, notification and identity chrome from the app shell; make it responsive, accessible and honest about its local/trusted unauthenticated boundary.

## Read before edit (existing)
- `frontend/src/components/Layout/Shell.tsx` — 'System Online' :124, notification badge 3 :159, 'Analyst'/'Administrator' :176–177
- `frontend/src/components/Layout/Shell.css`

## Proposed NEW paths
None required; a small focus/menu helper is allowed only if it cannot fit the existing component.

## Implementation steps
1. Delete the three fabrications above (no health-derived status; `/health` may only be described as process liveness).
2. Add a persistent visible caveat: local/trusted unauthenticated boundary — text, not a dismissible toast. Any data-mode label must truthfully distinguish the actually configured API backend from the existing 'Static preferred; missing fixtures may use API' fallback — never an unconditional Demo/Live claim.
3. Responsive navigation: rail at ≥1024px, top bar 768–1023px, stacked below 768px; skip link as first focusable; breadcrumbs reflecting the current route; focus management on menu open/close and route change.
4. Use existing CSS/design-system tokens only; no theme/framework rewrite.

## Non-goals
No notification system, identity, auth/RBAC, telemetry or new routing framework.

## Acceptance criteria (testable)
1. Rendered output contains no 'System Online', no static badge count, no Analyst/Administrator strings (grep + rendered assertion).
2. Boundary caveat is visible at 375x812, 768x1024, 1280x800.
3. First Tab stop is the skip link; it moves focus to main content (keyboard test).
4. Menu is operable by keyboard at <1024px and focus returns correctly on close.
5. No unintended document-level horizontal overflow at any viewport or 200% zoom; status conveyed by text, not colour alone.
6. The data-mode label reflects reality in both modes: configured API vs 'Static preferred; missing fixtures may use API' fallback — no unconditional Demo/Live text.

## Focused tests and commands
Extend `Shell` tests alongside the component; `npm test -- --run src/components/Layout`, then `npm run check`. Playwright smoke at three viewports via playwright-cli skill (isolated, synthetic API).

## Rollback and compatibility
Pure presentation change in two files; revert restores prior chrome. No API/URL contracts touched.

## Worker brief (copy-paste)
You are the single code worker for F01 (this card). Read contracts doc §1–§2 and specification R01. Remove only the named fabrications; add the caveat and responsive/a11y behaviour with existing CSS. Frontend gates: `npm run check` + `npm test -- --run`, focused tests first. No commits; preserve dirty files. Return hub §5 format.