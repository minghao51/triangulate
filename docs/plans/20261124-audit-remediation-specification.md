# Audit remediation specification — P1/P2

**Status:** Ready for implementation handoff; not implemented or release-approved by this document.  
**Baseline:** `d589359` (`origin/main` at audit time) **plus the existing staged, unstaged and untracked refinement worktree**. A clean worktree made from that commit alone lacks parts of the input.  
**Delivery:** One integrated bundle. Apply the six fixes, audit the complete candidate, run the gates, then commit and push directly. No split PRs. No code changes, commit or push are implied by preparing these handoffs.

## 1. Scope and evidence

| ID | Priority | Defect / gap | Handoff |
| --- | --- | --- | --- |
| R01 | P1 | An acknowledged annotation was POSTed twice after its refresh failed; analogous controls exist for review and exception writes. | [Guard review writes and recovery](20261124-audit-remediation-handoffs/20261124-r01-review-write-recovery.md) |
| R02 | P1 | A citation redirect stripped an explicit snapshot and opened unpinned Evidence. | [Preserve historical context in deep links](20261124-audit-remediation-handoffs/20261124-r02-historical-deep-links.md) |
| R03 | P1 | A target payload of `{}` produced a `ready` comparison with seven synthetic changes in the audit fixture. | [Validate frozen snapshot integrity](20261124-audit-remediation-handoffs/20261124-r03-snapshot-integrity.md) |
| R04 | P2 | CLI publication can use a custom output root, but the HTTP artifact reader is fixed to `./output`. | [Align artifact output-root configuration](20261124-audit-remediation-handoffs/20261124-r04-artifact-output-root.md) |
| R05 | P2 | A cold comparison GET created a missing SQLite database; the two reader dependencies call `init_db()`. | [Make historical GETs storage-read-only](20261124-audit-remediation-handoffs/20261124-r05-read-only-storage.md) |
| R06 | P2 | `defer` can change a terminal case back to review-ready while preserving its event decisions. The behavior pre-dates the explicit branch. | [Preserve review decisions on defer](20261124-audit-remediation-handoffs/20261124-r06-defer-transition.md) |
| R07 | Gate | Audit, integration evidence, whole-bundle staging, and direct release decision. | [Integrated audit and release](20261124-audit-remediation-handoffs/20261124-r07-integrated-audit-and-release.md) |

Prior audit evidence, **not** acceptance of this work: `npm run check` and Ruff passed, 516 frontend tests and 196 focused backend tests passed, mocked browser matrix passed 222 with 2 expected skips, and a separate WebKit journey passed. The full backend suite did not finish within the audit timeout. Four scratch regressions failed as expected against the audit baseline (duplicate POST, lost snapshot, false delta, cold-read DB creation); their durable equivalents must live in the repository tests. Do not depend on scratch artifacts or historical pass counts.

Read [project instructions](../../CLAUDE.md), [refinement contracts](20261123-web-app-refinement-contracts.md) (§3, §6, §9, §10, §12–13), [refinement evidence](20261123-web-app-refinement-evidence.md), and the linked card before editing. The six cards are a narrow addendum; where a prior refinement acceptance claim or planning card conflicts, record the new finding and revised behavior rather than rewriting historical test results.

## 2. Required behavior across the bundle

- **Write recovery:** Separate server acknowledgment, explicit refusal, and unknown outcome. No automatic POST retries or repeated submit from ambiguous/reconciled/acknowledged-but-unrefreshed states. Only an inconclusive reconciliation followed by explicit confirmation can retry that saved payload. An acknowledged write is never retried as recovery. Preserve notes, targets, and case/row isolation. No claim of HTTP idempotency or revision/CAS.
- **History:** Never silently substitute a current view, another snapshot/run, or an independently frozen citation for a requested pinned observation. Compare only validated immutable payloads. Existing API scopes, historical chronology and 404 parity stay intact; malformed observations are explicitly unavailable, not zero changes or apparent deletions.
- **Artifact configuration:** Support CLI-published files under a single operator-configured output root, with `./output` compatibility. Keep ownership, filename, descriptor-relative no-follow walk, size limit, uniform misses and no-latest-fallback behavior. Settings are startup/operator inputs, never supplied by a request, and errors must not disclose filesystem paths to clients.
- **Storage:** The historical comparison, artifact list and artifact download GETs must never create a directory, DB file, table, index, migration marker or domain row, including when they are the first requests. They use the same selected DB as case routes and do not bootstrap services on demand. A missing or uninitialized store gets a deliberate, sanitized `503`, not a fake case miss; initialized store and unknown resource retain `404`. `/health` stays liveness only.
- **Defer:** Keep case status, stage, event review decisions and their bindings unchanged. Keep the existing case-level review note/timestamp behavior. Do not reopen or touch exception resolution metadata solely because a case review was deferred. All other decisions, writer fencing and HTTP error families remain intact.
- **Boundaries:** No new endpoints, DB schema or migration; no bulk fix, legacy data rewrite, backfill, D01 recovery, dependency uplift, deploy or production-data action. Do not broaden the existing local, trusted, unauthenticated service boundary. General UI redesign, saved views, comparison tray, dashboard accessibility and unrelated audit suggestions are not in this fix bundle. Release documentation can reconcile stale assertions and remove proven whitespace blockers without changing unrelated behavior.

## 3. Execution and ownership

1. Main orchestrator inventories branch, refs, index, tracked diff and untracked files before work; preserves in-flight user edits. Review every candidate path, including generated sources/assets, before staging. Do not reset the index or use a `HEAD`-only worktree as a proxy for the input. If isolation is useful, transfer the actual intended tree (including new sources, without secrets/runtime files) into an explicit disposable checkout; verify the transfer before editing or testing.
2. One application-code writer at a time. Suggested sequence: **R01 → R02 → R03 → R04/R05 (coordinate and apply sequentially) → R06 → R07**. The first three are prioritized. R04/R05 share `src/http/app.py`, runtime configuration, and test fixtures; freeze the shared settings/fixture choices before either patch. R01/R02 share the case workspace and test file; do not edit those in parallel. Reviews and read-only checks may run independently.
3. Per card: capture a failing regression where feasible, make the smallest coherent fix, run focused tests, and report exact commands/results plus any compatibility decision. A card is not accepted while a required assertion is failing or unverified. If a historical payload shape or operator configuration contradicts the contract, show the concrete evidence and stop for a decision rather than weakening tests or introducing a silent fallback.
4. Independent reviewer audits the integrated candidate **against the original HEAD and the recorded starting worktree**: distinguish pre-existing bundle changes, remediation changes and remaining risks. Have findings checked against code and tests. R07 requires the full backend, frontend, mocked multi-engine browser + real disposable API/browser evidence, not just per-card tests. Fix and re-review findings; rerun affected gates and the final bundle gates as appropriate for the exact candidate.
5. The main orchestrator, not a card worker or reviewer, owns the final staging/commit/push. When the owner has authorized direct delivery, all gates have passed, and the remote has not diverged, commit the reviewed staged tree and push normally to the intended branch. No force, no automatic history rewrite and no merge from a stale or unknown remote. No reviewable PR split is required. Stop if review/testing is incomplete, sensitive files would be included, unrelated edits cannot be separated, branch policy blocks the push, or the remote moved. See R07 for exact checks and evidence.

### Per-card response format

- ID and status (`draft`, `implemented-unverified`, `verified`, or `blocked`).
- Cause and chosen contract; files edited; externally visible behavior or configuration change.
- Regression evidence before and after, expected skips, exact test commands/exit codes and output locations. Use only sanitized fixture identifiers.
- Compatibility/rollback notes; any deviations and open questions. No claim of merge/deploy or full-suite acceptance from a focused run.

### Coordinator prompt (copy/paste)

> Implement the P1/P2 audit remediation using `docs/plans/20261124-audit-remediation-specification.md` and R01–R07. Use the existing staged/unstaged/untracked refinement tree, not bare d589359. Respect repository instructions and preserve user changes. Use one code writer, focused regressions, independent integrated audit, and full gates including a disposable real-API browser run. Deliver as one reviewed direct commit/push, no split PRs; only the orchestrator releases after confirming owner authorization, reviewed index, green gates, and remote ancestry. Do not modify live data, perform D01, deploy, force-push, or expose unverified results as accepted.
