# R01 — Guard review writes and recovery (P1)

**Status:** Ready for worker · **Dependency:** none. Complete before R02 touches the same view/tests.  
[Specification](../20261124-audit-remediation-specification.md) · [Original write contract §6](../20261123-web-app-refinement-contracts.md#6-review-mutation-contract)

## Problem and read-before-edit

`frontend/src/pages/CaseIntelligenceCenter.tsx` (`OverviewTab`, `writeStateFromError`, `refreshReviewReads`, ordinary and recovery handlers) and `frontend/src/pages/tabs/ExceptionsTab.tsx` (`rowStateFromError`, row actions/recovery) disable ordinary controls only while pending. On acknowledged POST + failed GET, a second ordinary click sends another POST; the audit reproduced two annotation POSTs from one draft. `uncertain` and `reconciled` likewise leave bypass controls. Existing tests exercise the intended recovery button, not the forbidden ordinary controls. Read both test files, `frontend/src/services/api.ts`, `frontend/src/services/api-error.ts`, the three server actions in `src/http/app.py`, and the service commit/return points. A non-contract failure response can occur after commit, so merely having an HTTP response does not prove rejection.

## Required state and transitions

| State | Ordinary POST control / handler | Recovery |
| --- | --- | --- |
| Idle, fresh draft, saved/stale, or definitively rejected | Allow a deliberate valid submit (existing restrictions still apply). | None required. |
| POST or a recovery GET is pending | Block repeat requests for this operation. | Announce pending; do not launch duplicate recovery GETs. |
| Acknowledged; refresh failed | Block every POST for that operation. Preserve the submitted payload and affected draft. | Only `Retry refresh (GET)`; success goes to saved/refreshed, failure stays here. |
| Unknown outcome (lost response, ambiguous 5xx or invalid success response) | Block all ordinary POST paths for that operation. | GET-only reconciliation; unsuccessful read remains unknown. Successful read means inconclusive, **not** saved or rejected. |
| Reconciled but inconclusive | Ordinary submit stays blocked. | One explicit **Confirm retry** using the immutable submitted payload after validating current case/row/target. Warn of possible duplicate audit/annotation. Each new attempt re-enters pending; if again ambiguous it requires a new read and confirmation. |

1. Apply the guard at both rendering and dispatch, including native submission/keyboard paths and rapid clicks before a re-render. Prevent concurrent same-scope POST/refresh from letting a stale callback unlock a newer attempt. Scope by at least `caseId + operation` or `caseId + exceptionId`, plus attempt identity if needed. One unresolved form must not disable unrelated review/annotation forms; do not let a blocked row permanently disable unrelated exception rows. Keep any intentional single-in-flight exception POST behavior honest in the UI.
2. Preserve the existing 409 writer-conflict and 422 invalid/blocked states; known pre-write refusals (e.g. the API's known 404) should not be labeled ambiguous. Use a conservative classification for statuses/transport errors without proof of refusal. An error parsing an acknowledgment, or a success body that cannot identify the expected recorded result, is ambiguous, not proof of rollback. Assert at least the existing response's case/entry identity where available; TypeScript's response cast is not runtime proof. No automatic POST retry in React Query, wrapper, or recovery callback.
3. Keep an unresolved operation and its submitted payload separate from editable input. GET recovery clears only the successfully acknowledged draft if it still matches, including the retry-refresh success path. If inputs remain editable, newer edits must not be overwritten by a late response. Confirmation may not switch to the current selection or edited text; if the target/row is no longer eligible, refuse the retry without a POST. An acknowledged but no-longer-visible row must not be presented as an available retry target.
4. Keep unresolved state for same-case tab switches while the case workspace remains mounted. Its state owner must outlive the tab if tab unmount would otherwise bypass the lock; prefer local in-memory ownership, not a new durable store. Late Case A work must never alter Case B. This is not cross-tab, reload, or multi-client idempotency: do not persist notes, store tokens, promise exactly-once delivery, or claim a matching note proves which POST landed. Keep explicit read reconciliation as the only recovery from ambiguity.

## Regression and integration matrix

- `CaseIntelligenceCenter.test.tsx`: annotation POST mock ack → follow-up GET fails → repeated Save (including keyboard/native path, if applicable) → call count remains 1; GET-only refresh works; original draft clears only on ack + verified read. Repeat for review buttons (different decisions still must not bypass the lock). Assert independent form remains enabled.
- Both UI test files: lost response and API 5xx → ordinary controls and dispatch blocked before **and after** reconciliation; unsuccessful reconciliation does not unlock; explicit confirmation sends exactly one unchanged payload. Confirm no second automatic POST, disabled/busy semantics, known 409/422/404 behavior, later input untouched, target disappeared after read, stale updates, same-case tab return and late Case A completion.
- `ExceptionsTab.test.tsx`: use at least two rows; ack/refresh-failure and uncertain/reconciled paths on one row do not post via alternate row action (resolve/defer/reopen), or prevent unrelated rows from being used beyond any existing single-flight POST. A recovery failure preserves retry capability for the read.
- Preserve existing successful paths and React Query invalidation contracts; artificial failures must be confined to these tests. R07 exercises one real annotation POST and a controlled failed follow-up GET with a successful real GET-only retry.

Focused: from `frontend/`, `npm run test:ci -- src/pages/CaseIntelligenceCenter.test.tsx src/pages/tabs/ExceptionsTab.test.tsx src/services/api.test.ts` and `npm run check`. Add to existing unit/gate suites rather than inventing a second state platform. No new server action, data migration, or idempotency feature.

**Worker brief:** Implement R01 only. Start with the reproduced annotation test, then enforce the same state contract for review and exception actions. Verify both forbidden and allowed paths, preserve drafts and case/row scope, and report exact commands and regressions. Do not commit or push.
