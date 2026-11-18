# Deterministic comparison read API (P02)

Date: 2026-11-18. Status: **implemented, pending owner review**. Contract:
[specification](../plans/20261114-evidence-workbench-specification.md) §6, ticket
[P02](../plans/20261114-evidence-workbench-worker-plan.md). Depends on P01 and
E03; no migration, no model call and no mutation route.

## Route

`GET /api/cases/{case_id}/comparison?left={evidence_id}&right={evidence_id}`
returns one pinned two-capture comparison.

Optional pinned captures: `leftCapture`, `rightCapture` (aliases of
`left_capture_id` / `right_capture_id` are not exposed; use the camelCase names).
When omitted, each side uses that evidence item's current capture and returns the
resolved `leftCaptureId` / `rightCaptureId` so the UI can pin them in the URL.

Pagination: `limit` (default 25, max 100) and `offset` (≥ 0) apply to rows sorted
by exact claim signature. The response reports `total`, `limit`, `offset` and
`hasMore`.

Status mapping:

| Condition | Status |
|---|---|
| Unknown case, unknown/wrong-case evidence, unknown/wrong-evidence capture | 404 |
| Same evidence ID on both sides, empty capture selector, bad limit/offset | 422 |
| `snapshotId` / `snapshot_id` supplied | 422 (snapshots arrive in R03) |
| Valid comparison with zero rows | 200 with an empty page |

## Pairing and rows

- Claims are paired only by the existing exact `claim_signature` policy
  (SHA-256 of lowercased, stripped text). Paraphrases are never merged and the
  identity algorithm is unchanged.
- A side includes only claims whose `ClaimEvidenceLink.capture_id` equals the
  selected capture **and** whose claim belongs to the requested case. A link from
  another case is never attributed.
- Row status is `shared`, `left_only` or `right_only`. One-sided rows carry a
  caveat: extraction on one side only is not proof that the other source omitted,
  lied or disagreed.
- Each side exposes all persisted passages for that signature, with quote,
  code-point range, citation/link/capture IDs, effective relationship, raw stored
  relation, alignment status, assessment origin/version and diagnostics.
- `contradiction.explicit` is true only when a validated effective relationship
  is `contradicts`. `contradiction.conflict` additionally requires the other side
  to have an assessed `supports` or `reported_by` relationship. Textual
  difference alone never produces a contradiction.

## Historical capture rule

Selecting an older capture never falls back to the latest live claim links. The
response reports per-side coverage:

- `linkedClaimCount`: distinct case-owned claims linked to the evidence.
- `attributedClaimCount` / `attributedLinkCount`: links naming the selected capture.
- `otherCaptureLinkCount`: links naming another capture version.
- `unattributedLinkCount`: legacy links with no capture.
- `claimLinkageStatus`: `available`, `historical_unavailable`,
  `unattributed_legacy` or `empty`.
- `historicalAnalysisAvailable`: false when links exist only for other captures
  or only as unattributed legacy links.
- `caveat`: an explicit explanation of the exclusion or unavailability.

Individual citation IDs on persisted passages remain inspectable; the comparison
does not invent a historical analysis version or merge old assessments into the
current one.

## Evidence, extraction and dependency context

Each side exposes source metadata, capture kind/times, SHA-256, code-point length,
the recorded collector analysis scope (`scope_start`, `scope_end`,
`body_char_count`, `input_limit`, `status`, availability) and P01 publisher/copy
identity. Capture **bodies** are not included.

`dependency` reuses `source-dependency-policy-v1` on the two selected
evidence/capture members: detected edges, reasons, publisher keys and
`copyDetected` (identical long normalized capture text). A missing edge is
reported as “no dependency detected”, never as proven independence.

## Tests and gates

`tests/test_p02_comparison_api.py` covers shared/left-only/right-only rows,
explicit assessed contradiction vs textual difference, old-capture
unavailability without current-link substitution, legacy unattributed links,
copy/dependency warnings, analysis scope, pagination determinism, default pinned
captures, different-ID validation, 404/422 mapping, GET-creates-nothing and the
absence of mutation routes. Focused **9 passed**; full backend **456 passed, 9
deselected**; Ruff clean.

## Known limitations / deferred

- No semantic/paraphrase alignment; only exact signatures.
- No saved snapshot selector until R03; historical availability is limited to
  persisted capture-linked assessments.
- No comparison UI until P03.
- Dependency coverage is exactly the P01 v1 edges; near-duplicate/semantic
  syndication detection is deferred.
