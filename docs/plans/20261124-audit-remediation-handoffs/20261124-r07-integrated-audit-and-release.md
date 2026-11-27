# R07 — Integrated audit and release (Gate)

**Status:** Ready for worker · **Release authority:** the main orchestrator alone executes staging, commit and push; this card produces the audit and gate evidence and a ready-to-run release checklist.  
**Baseline:** `d589359` plus the existing staged, unstaged and untracked refinement worktree. The candidate is the whole reviewed tree, never a clean rebuild from `HEAD`.  
[Specification](../20261124-audit-remediation-specification.md) · [Refinement contracts](../20261123-web-app-refinement-contracts.md) · [F16 gate](../20261123-web-app-refinement-handoffs/20261123-f16-core-integration-and-release-gate.md) · [F21 gate](../20261123-web-app-refinement-handoffs/20261123-f21-extended-history-release-gate.md)

## Scope of the integrated bundle (P1 ×3, P2 ×3)

One integrated bundle: apply R01–R06, audit the complete candidate, run the gates below, then one direct commit and a non-force push. No split PRs ([specification §Delivery](../20261124-audit-remediation-specification.md)). Defect detail lives in the specification §1 table and the cards; this column only names the end-to-end proof R07 owes each card.

| ID | Pri | Card | R07 end-to-end proof (gate phase) |
| --- | --- | --- | --- |
| R01 | P1 | [Guard review writes and recovery](20261124-r01-review-write-recovery.md) | G4 scenario 5: one real synthetic annotation POST + controlled single-GET failure + GET-only retry; session POST count |
| R02 | P1 | [Preserve historical context in deep links](20261124-r02-historical-deep-links.md) | G4 scenario 4: combined `snapshot`+`citation` deep links, zero fallback reads under a pin |
| R03 | P1 | [Validate frozen snapshot integrity](20261124-r03-snapshot-integrity.md) | G4 scenario 2: a valid two-snapshot pair from the real fixture, with a known frozen change rendered |
| R04 | P2 | [Align artifact output-root configuration](20261124-r04-artifact-output-root.md) | G4 scenario 3: list + download + file-content check from a non-default root |
| R05 | P2 | [Make historical GETs storage-read-only](20261124-r05-read-only-storage.md) | G4 scenarios 7–8: historical-GET-first instance, request-order identity, cold-miss sanitized 503 with no creation |
| R06 | P2 | [Preserve review decisions on defer](20261124-r06-defer-transition.md) | G4 scenario 9 (recommended): a separately audited `defer` probe on a terminal case; otherwise its pytest/CLI evidence re-run in G1 |
| R07 | Gate | this card | integrated audit, all gates, whole-bundle staging, release sequence |

**Prior audit figures — carried, not acceptance and not re-claimed here** ([specification §1](../20261124-audit-remediation-specification.md)): `npm run check` and Ruff passed; **516** frontend tests and **196** focused backend tests passed; the mocked browser matrix passed **222** with **2** expected skips, plus **1** separate WebKit journey passed; the full backend suite **did not finish within the audit timeout**. Four scratch regressions failed as expected against the audit baseline; their durable equivalents must live in the repository tests owned by R01–R06. R07 must produce fresh numbers for every gate; none of the figures above may be repeated as a result.

## Read before edit (existing)

- [Project instructions](../../../CLAUDE.md) (`uv run` only; frontend `npm run check` / `npm test` after changes).
- [Specification](../20261124-audit-remediation-specification.md) §2 (bundle boundaries), §3 (execution, ownership, per-card response format).
- [Contracts](../20261123-web-app-refinement-contracts.md) §1 (disposable-copy verification, protected paths, browser rules), §12–§14 (historical read contracts).
- F16/F21 gate cards (evidence discipline: engines missing ⇒ **not proven**, counts recorded verbatim, no deploy/commit from a gate).
- `scripts/v01_e2e_fixture.py` — scratch DB/config, real writer publication into `--out`, and manifest fields `snapshotId`, `runId`, `changeRunId`, `changeSnapshotId`, `baselineSnapshotId`, and frozen claim IDs. `expectedDeltaRows` describes **recorded-run** delta semantics, not ad-hoc comparison.
- `frontend/playwright.refinement.config.ts` (mock matrix, WebKit opt-in `REFINEMENT_GATE_WEBKIT=1`, artifacts under `/tmp/refinement-gate`), `frontend/tests/gate/`, `frontend/package.json:15-19`, `frontend/.nvmrc`, `frontend/vite.config.ts:7-10` (proxy `/api`,`/health` → `127.0.0.1:8000`).
- `src/cli/main.py:394-402` (`serve --host --port`), `docs/reference/cli-operations.md:91-92` (Vite same-origin proxy pattern), `docs/reference/http-api.md` (the three historical GETs and their status families).
- `tests/test_v01_e2e.py:35-63` (`RecordingASGI` request recorder — the model for any scratch-side audit harness), `tests/test_audit_external_boundaries.py` (stubbed external boundaries).

## Release sequence (orchestrator-executed, in order)

1. **P0 — Preconditions and inventory (read-only).** Confirm the owner has authorized direct delivery (spec §3.5). Record to scratch: `git rev-parse HEAD`, `git status --short`, `git diff --stat`, `git diff --cached --stat`, the untracked list, and `git fetch origin && git rev-parse origin/main`. The input is the full dirty worktree; never rebuild from `HEAD` alone (spec §3.1).
2. **P1 — Remediation (single application-code writer, spec §3.2).** Apply **R01 → R02 → R03 → R04/R05 (shared settings frozen first, applied sequentially) → R06**. Per card: failing regression where feasible, smallest coherent fix, focused tests, response in the spec's per-card format. No commits.
3. **P2 — Independent comprehensive audit (spec §3.4).** Reviewer diffs the candidate against the recorded P0 state and classifies every path: (a) pre-existing refinement bundle, (b) R01–R06 remediation, (c) documentation. Verify each remediation against its card contract and spec §2 boundaries (no new endpoints, schema, migrations, dependencies; the only HTTP writes remain the three POST families). Findings → fix → re-review; rerun affected gates.
4. **P3 — Gates** G0–G4 below, all in the disposable copy, fresh counts recorded.
5. **P4 — Diff, staging, permissions, audit, remote drift** (checklist below).
6. **P5 — Commit and push (orchestrator only, non-force).** One integrated commit of the reviewed staged tree; `git push origin main`. No PR, no `--force`, no `--force-with-lease`, no history rewrite. Stop if any P4 stop-condition holds.
7. **P6 — Post-push verification.** `git fetch origin && git rev-parse origin/main` equals the pushed commit SHA; record the push output line; publish the evidence bundle paths. No deployment step exists in this sequence; D01 is untouched.
8. **P7 — Failure handling.** See "Failure handling and recovery" below. Nothing in this sequence reverts automatically.

## Gates and precise commands (safe isolation)

Run the application gates from a disposable copy with no access to the checkout DB, checkout runtime configuration, live providers or external network (contracts §1). `tests/conftest.py` guards alone are not sufficient protection. Prepare locked dependencies separately using approved caches or package access, then run the gates without network egress except loopback. Do not introduce dependency upgrades.

### G0 — Disposable copy and fixture

1. Set `REPO` to the repository root, create a private scratch directory with `mktemp -d`, and name it in the evidence. Enumerate candidate files with `git -C "$REPO" ls-files -z --cached --others --exclude-standard`. From that list, prepare a **reviewed NUL-delimited manifest** of existing candidate source, test, lock and doc paths. Include staged/working-tree edits and intended untracked sources; omit deleted paths and out-of-scope work. Reject symlinks that would leave scratch isolation. Do not transfer `.git`, `.env*` except an approved example, user runtime config, local DBs/sidecars, credentials, outputs, browser storage, remote content or dependency caches as candidate files. Do not copy the entire checkout.
2. Copy only the manifest and verify all paths/hashes against the working candidate (record the manifest and hash; one sample `cmp` is insufficient). Example, after creating `"$SCRATCH/copy"` and reviewing `candidate.files0`:

   ```bash
   rsync -a --from0 --files-from="$SCRATCH/candidate.files0" "$REPO"/ "$SCRATCH/copy/"
   cd "$SCRATCH/copy"
   # Use a sanitized process environment with approved toolchain/cache paths only.
   uv run python scripts/v01_e2e_fixture.py --out "$SCRATCH/v01"
   ```

3. Run with provider credentials and inherited DB/output/API/Playwright overrides absent. Supply only explicit scratch settings as needed, including synthetic `config.toml` in the copy; do not load the checkout config or `.env`. The deterministic fixture uses fake providers and produces its own DB/config under `--out`; fail if it would overwrite an existing DB. Record the fixture's synthetic manifest. `--refinement-variants` is optional; the base manifest carries the two published snapshots required here.

### G1 — Backend (focused first, then full)

```bash
cd "$SCRATCH/copy"
# Run the focused commands from R03–R06 first, including the new wiring regressions.
uv run pytest -q --disable-warnings
uv run ruff check src tests scripts --output-format concise
```

The full suite must **complete**; record wall time and verbatim counts. The prior audit's timeout is history, not a budget.

### G2 — Frontend

```bash
cd "$SCRATCH/copy/frontend"      # node/npm per frontend/.nvmrc
npm ci --offline                 # or restore approved locked dependencies before the isolated runs
npm run check
npm run test:ci                  # vitest run; same as `npm test -- --run`
```

Plus the R01/R02 focused calls named in their cards (`npm run test:ci -- <files>`).

### G3 — Mock-browser matrix and WebKit

```bash
cd "$SCRATCH/copy/frontend"
npx --no-install playwright test --config playwright.refinement.config.ts
REFINEMENT_GATE_WEBKIT=1 npx --no-install playwright test --config playwright.refinement.config.ts --project=webkit-journeys --output "$SCRATCH/webkit" --reporter=line
```

The matrix uses the config's `/tmp/refinement-gate` output. Ensure it is not shared with another session and preserve its report before any second run. A missing engine or library (e.g. `libavif16`) is **not proven**, not a pass. Stop for the owner to resolve a missing required engine; do not silently downgrade or install/upgrade browsers to force a pass.

### G4 — Real disposable API + browser gate (after R01–R06 applied)

Setup — API first, from the disposable copy:

```bash
ss -ltn 'sport = :8000' | tail -n +2    # must be empty: the Vite proxy target is fixed (frontend/vite.config.ts:7-10).
                                        # Occupied ⇒ stop and report; never kill or adopt an unknown listener.
cd "$SCRATCH/copy"
# Use a synthetic config in the scratch copy; set its [database].path to the absolute scratch DB.
DATABASE_PATH="$SCRATCH/v01/triangulate.db" TRIANGULATE_OUTPUT_ROOT="$SCRATCH/v01" \
  uv run triangulate serve --host 127.0.0.1 --port 8000
```

Setting both the scratch `[database].path` and `DATABASE_PATH` to the same value makes R05's precedence rules immaterial; assert runtime identity by the fixture `caseId` in the responses. `TRIANGULATE_OUTPUT_ROOT` is the R04 setting; the fixture published under its `--out` root (`scripts/v01_e2e_fixture.py:177-183`), which is a non-default root — no `./output` exists in the serve cwd, so a successful download proves the configured root was used. Then:

```bash
cd "$SCRATCH/copy/frontend"
# VITE_PORT is a checked free loopback port set by the gate harness.
VITE_API_BASE_URL="http://127.0.0.1:$VITE_PORT" npm run dev -- --host 127.0.0.1 --port "$VITE_PORT" --strictPort
```

Use the playwright-cli skill and headless Chromium (installed Chrome channel); Firefox where installed. Prefer a repeatable test or bounded harness, not a screenshot-only sign-off. Readiness probes use `/health` only before the first case/historical requests; assert actual DB identity in the test. Set a cleanup trap for only the API/Vite PIDs and browser session you start, including on failures. Abort requests outside the approved loopback origins at the browser context and restrict process egress independently. Record request method, URL, status and application console errors. If necessary, use a scratch-side `RecordingASGI`-style recorder (`tests/test_v01_e2e.py`) to distinguish intercepted requests from requests that reached the API.

One audited browser session:

| # | Scenario | Assertions |
| --- | --- | --- |
| 1 | Happy-path reads on the fixture case | case detail + tabs load from real HTTP; all requests GET |
| 2 | Two published snapshots | Open Changes using `mode=ad_hoc`, the manifest's explicit `baselineSnapshotId` and `changeSnapshotId`. Verify the browser calls the actual comparison route, shows the same two IDs and a ready, non-empty comparison, and renders a known entity change matching the frozen payloads (e.g. the added `frozenChangeClaimId` if confirmed in both payloads). Verify side-scoped refs. Do not use `manifest.expectedDeltaRows` as the ad-hoc oracle. |
| 3 | Artifact list + download (non-default root) | Pin Report to an explicitly published manifest run, assert the scoped listing and invoke a download through the UI. Check response headers (`Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, expected media type), then compare the downloaded **bytes** with the independently located expected run file in scratch. Browser filename may be based on the descriptor. A recorded payload checksum is not a byte checksum; do not compare them. |
| 4 | R02 deep links (read-only) | open a combined `snapshot`+`citation` URL on a current-only view and one snapshot-aware destination; the conflict/unsupported state renders with **zero** citation or current-gallery reads under the pin and no automatic redirect (R02's routing table is the authority); explicit user choices work |
| 5 | R01 annotation ack + failed follow-up GET | install a route interception that aborts **exactly one** follow-up review-refresh GET, then passes through; submit **one** synthetic annotation (fixture claim/evidence target) → server ack; repeat-clicking the blocked control sends nothing (POST count still 1); explicit **Retry refresh (GET)** hits the real API through passthrough → saved/refreshed state with the acknowledged note |
| 6 | Request audit close-out | API session total: **exactly 1 POST** (the annotation); all other API traffic GET; the only unexpected-to-the-app failure is the intentionally intercepted GET. Record blocked assets separately, show zero external egress, and investigate unexpected application console errors. |

Separate API instances, no browser:

| # | Scenario | Assertions |
| --- | --- | --- |
| 7 | Historical-GET-first start | a fresh instance whose **first** requests are exactly the three historical GETs (snapshot-comparison, artifacts list, artifact download) returns the same results as the warmed instance — same configured DB regardless of request order (R05) |
| 8 | Cold-miss probes | For each historical route, start an isolated instance with a missing nested scratch DB path. The first historical GET returns sanitized `503`; verify neither the parent nor the DB file appears. Also pair with R05's existing-empty/partial database checks for no schema changes. |
| 9 | R06 defer probe (recommended) | one separate, separately audited phase: `defer` on a terminal case via the real API with its own POST budget of 1; fresh read shows case status/stage/event decisions unchanged and the case-level note recorded (R06's policy table). Alternative: rely on R06's pytest + CLI passthrough re-run in G1 and record that as the proof. Never fold this POST into scenario 6's count |

## Diff, staging, permissions, audit and remote drift (P4)

- **Diff:** `git diff d589359 --stat` plus the untracked list must equal the P0 inventory plus the reviewed remediation, gate and docs deltas; every path is classified (bundle / remediation / docs). Anything unclassified is a stop. Review the checked-in `config.toml` baseline by path/diff without transferring local runtime configuration, and document any synthetic runtime substitutions used by the test harness.
- **Staging:** stage explicit reviewed paths (`git add -- <paths>`) — never a blind `git add -A` against an unreviewed inventory. Check `git diff --check HEAD` and `git diff --cached --check`. Reconcile the staged path inventory, file contents, modes and deletions with the tested candidate; compare staged blobs to the recorded hashes and record the reviewed `git write-tree` value before commit. Unexpected unstaged/untracked changes are a stop, not an invitation to discard them.
- **Protected paths:** the staged set contains none of `data/`, `logs/`, `output/`, `triangulate.db`, `.env`, `config.toml`, `__pycache__/`, `node_modules/`. `config.toml` is tracked and must be unmodified; if modified, stop and separate it.
- **Permissions:** `git diff --cached --summary` shows no unintended mode changes (100644↔100755); untracked file modes checked (`stat -c %a`) before `git add`.
- **Secrets:** heuristic scan of `git diff --cached` for key/secret/token/password patterns, hits manually reviewed; never read `.env` to produce evidence.
- **Audit:** use the G4 request log (historical reads plus the exact annotation POST count), egress controls and `uv run pytest -q tests/test_audit_external_boundaries.py` for external-boundary evidence. Report dependency/package setup separately; do not imply those tools are application traffic.
- **Remote drift:** `git fetch origin`; `origin/main` must still equal the SHA recorded at P0. Remote moved ⇒ **stop**; no rebase, no merge from a stale remote, no force. Branch policy rejects the push ⇒ **stop** and report.
- **Push (orchestrator only):** verify current branch/target is the authorized `main`, fetched `origin/main` is an ancestor, and the index matches the reviewed tree. Commit once, verify `git rev-parse HEAD^{tree}` still matches the reviewed tree (hooks may change contents), then `git push origin main` (non-force). Verify the remote SHA afterward. Unexpected pre- or post-push state ⇒ stop and report.

## Success evidence

| Item | Evidence recorded |
| --- | --- |
| Backend full + focused | verbatim pass/fail/skip counts and wall time per command; the full suite completed |
| Ruff | clean over `src tests scripts` (concise output) |
| Frontend | `npm run check` exit 0; test/file counts from `npm run test:ci`; fresh `npm ci` |
| Mock matrix + WebKit | matrix passed/skips verbatim; WebKit pass or **not proven** with reason |
| G4 real gate | request log (POST count = 1, one intercepted refresh GET), scenario results 1–9, valid pair and frozen-entity proof, artifact byte match, cold-miss 503 + no-create proof, R02 zero-fallback reads |
| Isolation | fixture manifest + `$SCRATCH` paths; checkout `triangulate.db`, `config.toml`, `data/`, `logs/`, `.env` metadata (size/mtime) unchanged before/after — metadata-only evidence, with its limits stated |
| Git | `HEAD` before/after (after = the new commit SHA), `git diff --cached --name-status`, `git diff --cached --summary`, push output line, `origin/main` == commit SHA |
| Prior figures | the carried 516 / 196 / 222+2 / WebKit 1 / Ruff / timeout table, labelled carried-from-audit, not results |

## Failure handling and recovery — no automatic reverts

- **Before push, gate fails:** stop; report in the spec's per-card response format; smallest coherent fix; independent re-review; rerun the affected gates **and** the final bundle gates for the exact candidate. Never `git reset --hard`, `git checkout --` or otherwise revert user/bundle work to force green.
- **Before push, audit finding:** same loop as P2; a finding is not waived by a passing count.
- **After push, a defect is found:** no automatic revert, no force-push, no history rewrite. The orchestrator/owner decides between a forward fix and an explicit revert **commit**; either goes through the same review and gate discipline. Card workers never commit, push or revert.
- **Partial states:** rerun interrupted gates. On unexpected partial staging, preserve the current index and P0 inventory, report the discrepancy and reconcile only explicitly authorized paths. Never reset pre-existing staged work.

## Acceptance criteria (testable)

1. R01–R06 are all applied and each card's regression evidence exists in the repository (no scratch-only regressions), with no scope beyond spec §2.
2. The independent audit classifies every candidate path and records findings → fixes → re-reviews.
3. G1–G3 produce fresh verbatim counts (the prior audit's figures are not reused); the full backend suite completes, and required engines pass. A missing required engine remains **not proven** and blocks release unless the owner explicitly changes the gate with the gap recorded.
4. G4 scenarios 1–8 pass against the real disposable API and browser on the deterministic fixture; scenario 9 passes or its documented alternative is recorded.
5. The G4 request audit shows exactly one POST (the synthetic annotation), all other traffic GET, one controlled intercepted GET followed by a passthrough GET retry, zero external hosts.
6. P4 checklist is complete: staged inventory equals the approved inventory, no protected paths, no unintended mode changes, remote unchanged since P0.
7. One integrated commit exists locally and `origin/main` equals its SHA after a non-force push, executed by the orchestrator with recorded owner authorization.
8. Success evidence table is complete; recovery policy (no automatic reverts) is recorded in the release note.

## Non-goals

No deployment, D01 or historical-data repair, force-push or history rewrite, PR split, new endpoints/schema/migrations/dependencies, live-provider calls or non-loopback application traffic in any gate. Do not read `.env` or production content for evidence. Reproduce regressions only on controlled fixtures. Do not claim coverage percentages, load results or engine results that were not measured.

## Worker brief (copy-paste)

> You are the single code worker for R07 (this card). Read the specification §2–§3, contracts §1, and each R01–R06 card before starting; repository instructions in `CLAUDE.md` apply. Produce the integrated audit and the G0–G4 gate evidence for the whole candidate (baseline `d589359` plus the dirty refinement worktree, then the six remediations). One application-code writer at a time for any fix a gate surfaces; fixes are smallest-coherent and re-reviewed. All verification runs in a disposable copy with a scratch DB/config/output root, mocked providers and no checkout DB; engines missing ⇒ not proven; counts recorded verbatim and never borrowed from the prior audit (516/196/222+2/WebKit 1 are history). G4 is a real disposable API + browser gate on the deterministic V01 fixture: two published snapshots compared, artifact list + download with content check from a non-default root, exactly one legitimate synthetic annotation ack followed by one controlled failed refresh GET and a passthrough GET-only retry with a session POST count of 1, historical-GET-first and cold-miss request-order checks, no external hosts. Prepare the P4 staging/permissions/audit/drift checklist and the success-evidence table, but do not commit, push, revert or deploy — the release commit and non-force push are executed by the main orchestrator only, after owner authorization and a clean P4. Return in the specification's per-card response format with every command, count and evidence path; report failures and not-proven items as-is.
