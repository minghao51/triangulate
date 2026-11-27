---
id: F16
status: implemented-and-tested
tier: core
depends_on: [F00, F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15]
---

# F16 — Core integration and release gate

**Size: L · Risk: browser-engine availability; evidence assembly across 24 screens/42 states.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Assemble and gate the integrated core: full screen/state/viewport coverage with actual frontend, backend and browser evidence. No deploy, no commit.

## Read before edit (existing)
- `frontend/playwright.config.ts`, `frontend/playwright.b03.config.ts`, `tests/test_v01_e2e.py`, `scripts/v01_e2e_fixture.py`
- `frontend/package.json` (:15 `check`, :17 `test`), `frontend/.nvmrc`
- Hub §6 coverage tables (24 screens, 42 states, owners)

## Proposed NEW paths
- PROPOSED `tests/test_refinement_core_gate.py` only if gate automation cannot reuse existing suites; evidence log lives in scratch/return report.

## Implementation steps
1. Fresh `npm ci` in an isolated disposable copy (F00 baseline + all core cards applied); run focused suites first, then full gates: `npm run check`, `npm test -- --run`, `uv run pytest -q --disable-warnings`, `uv run ruff check src tests scripts --output-format concise`.
2. Browser journeys via playwright-cli skill, isolated headless, synthetic API/DB: 24 primary surfaces at three viewports (72 cells), plus 42 selected states on their applicable parent surfaces at three viewports (126 state cells), with overlap reusable. This is NOT a 24×42 Cartesian matrix or 24 new routes. Check 200% zoom, keyboard/focus, text-not-colour-alone and unintended document overflow. Use Chromium for full layout coverage and critical end-to-end journeys on the other available engines.
3. Privacy/security/performance evidence: no raw captured text in URLs; request audit shows GET-read-only plus exactly the three POST families; no external IO; bounded rendered rows; no per-case fan-out. Record the proposed budgets as budgets, not benchmarks.
4. Missing engine ⇒ record **not proven** (owner may record a scoped defer, never certify). Produce the return report; no deploy, no commit.

## Non-goals
No deployments, commits, production repair (D01), load-SLO claims, or frozen unit counts.

## Acceptance criteria (testable)
1. Coverage matrix evidences all 24 screens at all 3 viewports (screenshot/entry per cell).
2. All 42 states exercised via fixture variants (state × evidence list complete).
3. Backend gates pass in the disposable copy with verbatim counts; Ruff clean over `src tests scripts`.
4. Frontend `npm run check` + `npm test -- --run` pass from a fresh `npm ci`.
5. Browser journeys pass on every available engine (Chromium/Firefox/WebKit); unavailable engines listed as not proven.
6. Request-allowlist audit shows only GET + the 3 POST families; no external IO during the run.
7. Record HEAD before/after as unchanged (status alone cannot prove no commit); diffs and status show only task-approved changes on top of the preserved baseline.

## Focused tests and commands
Existing `tests/test_v01_e2e.py` + focused suites per card; PROPOSED gate script only if unavoidable. Commands exactly as in step 1–2.

## Rollback and compatibility
Gate-only task; no feature code changes expected — any fix found goes back to its owning card, not here.

## Worker brief (copy-paste)
You are the single code worker for F16 (this card). One application code writer globally — hub waves are eligibility order only. Read contracts doc §1–§2, §8 and specification R14 plus hub §6. Assemble evidence for 24 screens/42 states/3 viewports; engines missing ⇒ not proven; no deploy/commit. Return hub §5 format with the full coverage matrix.