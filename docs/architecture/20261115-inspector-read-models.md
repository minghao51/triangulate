# Inspector read models (E03)

Status: **delivered and independently verified on 2026-11-15; pending owner
acceptance**. *(Status note 2026-11-22: this pending state is historical — E03
was subsequently accepted; see the [E02 pass B handoff](../plans/20261115-e02-pass-b-handoff.md),
which records E02 passes A/B1/B2/B3 and E03 "implemented, independently
verified, and ACCEPTED: merged into `main` as PR #2".)* Contract: [specification](../plans/20261114-evidence-workbench-specification.md)
§4 and §9, ticket [E03](../plans/20261114-evidence-workbench-worker-plan.md).
Depends on E02 (validated quotations, `ClaimCitation`, immutable captures).

This document describes the read side that the browser inspector (E04) consumes.
Everything here is GET-only: no endpoint in this feature creates captures,
citations, analysis or reviews, and no read path materializes legacy content.

## Where the code lives

| Layer | File | Responsibility |
|---|---|---|
| Readers | `src/cases/readers.py` (new) | Session-in/plain-dict-out lookups with ownership checks; no commit/rollback/close; no lazy loading of unrelated rows |
| Service seam | `src/cases/service.py` | Four thin delegating methods that own the session lifetime, matching the existing `get_case_details` pattern |
| DTOs | `src/http/schemas.py` | Additive camelCase models; every new field is optional/defaulted so legacy payloads keep validating |
| Mappers | `src/http/mappers.py` | snake_case reader dicts → DTOs |
| Routes | `src/http/app.py` | Four new `@router.get` endpoints on the existing router |
| Types | `frontend/src/types/backend-models.ts` | Additive optional interfaces only; no UI change here (E04) |

## Routes

All below the existing `/api/cases/{case_id}` prefix, added after the static
sibling routes so `/claims` and `/claims/overview` keep winning:

| Route | Returns |
|---|---|
| `GET /citations/{citation_id}` | Frozen claim text/signature, relationship, passage and alignment/assessment provenance, capture summary and evidence source metadata; `liveClaimPresent`/`liveClaimId` report whether the historical claim still exists |
| `GET /claims/{claim_id}` | Claim detail with counts, signature, party positions, `verificationProvenance`, and one passage entry per evidence link |
| `GET /evidence/{evidence_id}` | Source metadata, ordered capture summaries and related claim references |
| `GET /evidence/{evidence_id}/captures/{capture_id}?start=&length=` | One bounded code-point text window of an immutable capture |

`snapshotId`/`snapshot_id` is **rejected with 422** on the claim and evidence
readers until R03 implements snapshots; it is never silently ignored.

## Ownership and status mapping

| Condition | Status |
|---|---|
| Unknown case, resource of another case, dangling id, capture not belonging to that evidence | 404 |
| Malformed range (`start < 0`, `start > totalLength`, `length ∉ [1, 50000]`, non-integer) | 422 |
| Supplied snapshot selector | 422 (explicit message) |
| Unknown route method (POST/PUT/DELETE/PATCH on these paths) | 404/405; no mutating route exists |

Readers re-check ownership against stored rows rather than trusting the URL or
FK enforcement: claims are joined through `Event.case_id`, evidence through
`EvidenceItem.case_id`, and a capture must belong to the evidence in that case.
A citation is looked up by **its own** `case_id`, so it resolves after its live
claim and link are deleted; the capture and evidence summaries come from the
citation's frozen pointers.

## Capture windows

`start` is a zero-based Unicode **code-point** index (`start == totalLength` is
valid and returns empty text) and `length` is `1..50000` code points. The slice is
`text[start:start+length]` — Python slicing is the reference, the same rule the
quotation validator uses. Windows truncate only at end of text and always report
the returned `length` alongside `totalLength`, so a partial window can never be
mistaken for the whole capture. The complete body stays in storage and is
reachable by requesting successive windows; nothing is clamped or resynthesized.

## What the read models deliberately do **not** contain

- No capture **bodies** at case, claim or evidence level. `GET /api/cases/{id}`,
  `/claims`, `/evidence`, `/claims/{id}` and `/evidence/{id}` carry ids, hashes,
  code-point lengths, kinds, times and frozen metadata only. Text is reachable
  solely through the capture-window route. (Verified by a probe that seeded a
  unique sentinel body: absent from every read model, present only in the window.)
- No invented support or verification. Link DTOs keep the **raw stored**
  `relation` for diagnostics and add `effectiveRelation` from
  `relationship-policy-v1`; `supportCount`/`opposeCount` are the stored
  assessment-derived aggregates (E02 B3), never recomputed or inflated by a
  reader. `verificationProvenance` defaults to `"unknown"` and is labelled
  separately from source alignment; it never claims `model`/`human`/reviewer
  confirmation. `"legacy_unknown"` appears only when every attachment is provably
  pre-E02 shaped (no citation/capture, `not_provided`, no assessment provenance).
- No snapshot/historical selectors (R03), no comparison, run or search endpoints —
  those are P02/R03/S02. P01 source groups now live in the separate
  [source dependency groups](20261118-source-dependency-groups.md) read model.

## Verification

- `tests/test_e03_inspector_readers.py` — 59 tests: every alignment state
  (`exact`, `ambiguous`, `no_match`, `not_provided`, `source_unavailable`, legacy
  `opposes`), frozen-citation survival after claim/link deletion, code-point
  windows (emoji/CJK/combining), bounds and 422/404 matrices, DTO legacy
  defaults, "GET creates nothing" row-count checks and mutation-route absence.
- Parent gates: focused **146 passed**; full backend **409 passed, 9 deselected**;
  Ruff clean; frontend `npm run check` and `npm test -- --run` (72 tests) green.
  Logs: `/tmp/triangulate-e03-parent-{focused,full,ruff,frontend-check,frontend-test}.log`.
- Parent probes (safe-dir only): citation after live claim/link deletion (200,
  `liveClaimPresent=false`), codepoint window equality against the stored body,
  422 for bad ranges and snapshot selectors, sentinel body never leaking into a
  read model, and no non-GET route registered.

## Known limitations / follow-ups

- Timestamps are returned as persisted; SQLite drops `tzinfo`, and the reader
  does not invent an offset.
- `verificationProvenance` cannot be richer than stored data; a provenance column
  would be a schema change and is not part of E02/E03.
- E04 must use `effectiveRelation` (not raw `relation`) for labels, highlight with
  code points, and treat `liveClaimPresent=false` as an explanatory state.
