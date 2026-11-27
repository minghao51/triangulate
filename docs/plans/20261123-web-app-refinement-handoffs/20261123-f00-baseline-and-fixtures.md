---
id: F00
status: implemented-and-tested
tier: core
depends_on: []
---

# F00 — Baseline and fixtures

**Size: M · Risk: the snapshot must capture dirty worktree bytes while never touching live data.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Create the safe verification baseline every later task uses: a disposable copy of the current worktree (dirty bytes included), fixture variants for later failure states, and a recorded gate inventory. No feature work.

## Read before edit (existing)
- `scripts/v01_e2e_fixture.py` (fixture builder), `tests/conftest.py` (guards — not sufficient alone), `tests/test_v01_e2e.py`
- `frontend/package.json` (scripts :15/:17), `frontend/.nvmrc`
- `docs/plans/20261121-remaining-work-after-release-c.md` (historical counts only)

## Proposed NEW paths
- PROPOSED `tests/fixtures/refinement/` + `tests/test_refinement_fixtures.py` (fixture variants only)

## Implementation steps
1. Export the current worktree including dirty bytes (not `git archive HEAD`) into an isolated disposable copy; write a content manifest (paths + hashes) to scratch, never into `data/`.
2. Extend the fixture builder with the variants later tasks need: missing case, wrong-case annotation target, out-of-range/missing coordinates, unrecognized timeline status, absent report, legacy capture. Paid providers mocked, external IO disabled.
3. Record the gate inventory verbatim from the disposable copy: `npm ci` (fresh, isolated), `npm run check`, `npm test -- --run`, `uv run pytest -q --disable-warnings`, `uv run ruff check src tests scripts --output-format concise`. Node/npm per `frontend/.nvmrc`.
4. Record protected-path metadata and code-diff boundaries without reading credentials or production content. Use an owner-supplied read-only integrity manifest only if explicitly authorized; never hash/read `.env` or production data just to create test evidence. State the limits of metadata-only evidence.

## Non-goals
No feature work, no D01 data repair, no commits, no fixing pre-existing failures (record them as baseline).

## Acceptance criteria (testable)
1. Manifest proves at least one known dirty worktree file's bytes match the disposable copy.
2. Fresh `npm ci` + `npm run check` + `npm test -- --run` complete in the isolated copy; exit codes and counts recorded.
3. `uv run pytest -q --disable-warnings` and `uv run ruff check src tests scripts --output-format concise` recorded with counts from the disposable copy only.
4. Each new fixture variant is exercised by a focused pytest call and produces its documented state.
5. Disposable paths resolve outside the original runtime; protected-path metadata and existing-code boundaries are unchanged. Any stronger integrity claim identifies its authorized evidence; absent evidence is reported, not invented.

## Focused tests and commands
PROPOSED new: `tests/test_refinement_fixtures.py`; run `uv run pytest -q tests/test_refinement_fixtures.py` then the full gates above. Counts recorded, not frozen.

## Rollback and compatibility
Additive only; deleting `tests/fixtures/refinement/` restores prior state. Manifest stays scratch, uncommitted.

## Worker brief (copy-paste)
You are the single code worker for F00 (this card). Read contracts doc §1 (`docs/plans/20261123-web-app-refinement-contracts.md`) and specification R14. Scope: baseline + fixtures only; one worker, no recursion, no commits; never touch `data/`, `triangulate.db`, `.env`, `logs/`, `config.toml`. Return the shared return format from hub §5 with exact commands and counts.