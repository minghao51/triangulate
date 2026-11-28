# R06 — Preserve review decisions on defer (P2)

**Status:** Implemented and verified in `34ca121` ([evidence](../20261124-audit-remediation-evidence.md)) · **Dependency:** none.  
[Specification](../20261124-audit-remediation-specification.md) · [HTTP review surface](../../../reference/http-api.md) · [CLI reference](../../../reference/cli.md)

## Problem and read-before-edit

`src/cases/service.py:review_case` sets `case.status = REVIEW_READY` for `defer` although the comment says to keep the gate as-is. Already approved/rejected cases can be put back in the queue while their event review decisions and bindings still say approved/rejected. The branch makes a pre-existing fallback behavior explicit; it isn't a new decision verb. `review_case` also passes `defer` through `_resolve_case_exceptions`, which updates exception timestamps and may copy case-level rationale into resolution notes. Read both methods, `_compute_open_review_items`, case/Review enums and models, `src/cli/commands/cases.py:cmd_review_case`, HTTP schema/route, and existing tests for writer fencing and approval rules.

## Chosen policy

**`defer` is a case-level acknowledgement, not a reopen, stage transition, event classification, or exception-queue action.**

| Before | After `defer` |
| --- | --- |
| `REVIEW_READY` | `REVIEW_READY` |
| `APPROVED` / `REJECTED` | Original terminal status unchanged. |
| Monitoring or another valid stored case status accepted by current review entry points | Same status; no new status eligibility rule. |
| Stage; persisted event reviews and their timestamps and analysis bindings | Unchanged. |
| Exception queue/status/timestamps/resolution notes | Unchanged. Exception-level `defer` remains a different action, unchanged. |
| Case-level `last_reviewed_at` and `review_notes` | Preserve existing update semantics, including existing handling of missing notes. Normal case timestamp behavior from the committed note is allowed. |

Preserve the existing open-item count policy. A healthy fixture with unchanged inputs keeps counts unchanged; do not make defer a historical-data reconciliation command. Retain writer admission, validation, release, rollback and `409` conflict handling even when no notes are supplied. Keep approval blocking on unresolved exceptions, reject resolution behavior, `action_required` and legacy `exception` alias, and unsupported-decision handling intact. Missing case remains `404` via HTTP; do not add a new audit event or change direct/CLI signatures. No historic decision rewrites; the change applies to future calls only.

## Regression and acceptance

- Parameterize direct-service regression over each `CaseStatus` (at minimum review-ready, approved, rejected and monitoring). Seed event reviews with recorded analysis bindings and existing exception notes/timestamps. Call `defer` with case notes; after a fresh read, compare before/after fields, proving statuses/stage/bindings/exception metadata are unchanged and case-level note and timestamp are recorded. Check missing-notes behavior and no write leak on 409/invalid action. Use the normal writer fence, not a mocked no-op lock.
- Add an HTTP integration check for `defer` on a terminal case, reading fresh state from storage; verify 200, same reported case status, and existing error conventions. Exercise actual CLI decision passthrough and output or confirm existing coverage with a CLI test using the real service/fixture rather than relying only on a stub acknowledgement.
- Keep existing approve/reject/action-required/exception regressions green. Update the operator and HTTP references to distinguish case defer from exception defer; document that defer does not reopen a terminal case. No UI change is required unless existing copy contradicts the decision behavior.

Focused: `uv run pytest -q tests/test_http_api.py tests/test_cli.py tests/test_refinement_review_targets.py tests/test_r02_case_writer_fencing.py tests/test_b01_persistence_reviews.py tests/test_review_command.py`. Run `uv run ruff check src tests scripts`.

**Worker brief:** Implement R06 only, preserving case and event decisions while recording the case-level defer note. Protect exception metadata and writer fencing. Prove the behavior on terminal and review-ready cases through a fresh read. Do not commit or push.
