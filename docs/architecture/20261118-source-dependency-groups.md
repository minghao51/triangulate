# Source dependency groups (P01)

Date: 2026-11-18. Status: **delivered and accepted as the P02 baseline.** Contract:
[specification](../plans/20261114-evidence-workbench-specification.md) §5, ticket
[P01](../plans/20261114-evidence-workbench-worker-plan.md), handoff
[Release A acceptance and P01](../plans/20261118-release-a-acceptance-and-p01-handoff.md).
Depends on E02/E03; no migration and no separate publisher service.

## Route

`GET /api/cases/{case_id}/sources` returns case-level observed publishers and
dependency groups. `GET /api/cases/{case_id}/sources?claimId=...` (also accepts
`claim_id`) restricts the same policy to one claim's linked evidence. Conflicting
selectors return 422; unknown cases, wrong-case claims and unknown claims return
404. A valid empty scope returns 200 with zero groups and
`independenceStatus="unknown"`. Every request is GET-only and creates nothing.

## Identity and normalization

- HTTP(S) URLs are canonicalized locally: lowercase/IDNA host, fragment/userinfo
  and default port removed, empty path normalized to `/`, only `utm_*`,
  `fbclid` and `gclid` parameters dropped. Path case, trailing slashes, other
  query values and HTTP vs HTTPS are preserved. Stored URLs are never rewritten
  and are never fetched while reading.
- `publisherKey` comes from explicit frozen metadata (`publisher_key` /
  `publisher_identity`) when present. Otherwise the normalized host is a
  **provisional** key. A publisher display name alone stays unknown; names are
  never used to infer ownership or aliases.
- Text copy fingerprint v1 is NFKC + casefold + collapsed whitespace, used only
  with at least 200 non-whitespace code points. Short shared snippets cannot
  merge sources.

## Dependency edges

Groups are connected components of exactly these documented v1 edges:

| Reason | Edge |
|---|---|
| `same_source_url` | Identical normalized source URL (canonical when present, else original) |
| `same_publisher` | Identical known publisher key (explicit or provisional host) |
| `identical_normalized_capture` | Identical long text fingerprint |
| `same_case_article` | Same non-null `case_article_id` |
| `documented_common_origin` | Same explicit `source_dependency_key` / `dependency_key` metadata |

`independenceStatus` is `dependency_detected` when any component has more than
one member, otherwise `unknown`. There is deliberately no
“verified-independent” state: absence of a detected edge proves nothing.

## Counts and membership

- `distinctPublisherCount`: distinct known publisher keys.
- `dependencyGroupCount`: connected components, including singleton groups.
- `unknownPublisherCount`: evidence records with neither an explicit key nor a
  normalized host (not a claim about independent publishers).
- `publisherCounts`: observed evidence count and group count per known key,
  with the provisional flag.
- Every group carries deterministic IDs, sorted reasons, publisher keys and
  individually inspectable evidence/capture members. Repeated wire copies remain
  separate members but count once as a dependency group.
- Claim scope uses only that claim's links, deduplicated by evidence, and the
  link's validated capture when present (falling back to no capture rather than a
  different version). Case scope uses each item's current capture. A copy edge
  about another claim therefore cannot make every publisher in the case dependent.
- Existing `sourceDiversityCount` / stored diversity fields remain compatibility
  fields; they are not reinterpreted as independently verified-source counts.

## Tests and gates

`tests/test_p01_source_dependency_groups.py` covers URL canonicalization,
explicit/provisional/unknown identity, the 200-code-point threshold, each edge
reason, deterministic output under reordered input, short-snippet non-merging,
case/claim scoping, old-vs-current capture membership, GET-creates-nothing,
404/422 and the empty case. Focused **29 passed**; full backend **447 passed, 9
deselected**; Ruff clean.

## Known limitations / deferred

- Near-duplicate and semantic syndication detection is not implemented; coverage
  is exactly the edges above.
- Provisional host identity groups a domain, not proven common editorial control.
- No external URL resolution, publisher ownership lookup or alias inference.
- No frontend consumes the endpoint yet; P03 comparison UI is later.
- Snapshot-aware grouping is deferred to R03.
