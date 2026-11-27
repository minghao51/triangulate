# Case-scoped search read API (S02)

Date: 2026-11-20. Status: **implemented (backend `0ae9359`/`b92c453`, workspace
UI `ff838cc`/`3594d1c`), reviewed and verified locally in the V01 pass; not
pushed**. Consumes the [S01 transactional case search index](20261120-search-index.md);
adds no migration and no writer. Contract authority: [specification](../plans/20261114-evidence-workbench-specification.md)
§8/§9 and the [Release C completion map](../archive/20261120-release-c-completion-map.md) §5.

## Route

```
GET /api/cases/{case_id}/search
    q            required, trimmed, 1..256 code points, literal all-term
    type         claim | evidence                (optional)
    publisher    exact indexed publisher key     (evidence results only)
    status       claim verification-state label  (claim results only)
    publishedFrom, publishedTo  UTC ISO-8601, start-inclusive / end-exclusive
    limit        default 25, 1..100
    offset       default 0, 0..2,147,483,647 (larger values are 422)
```

`GET` only. The route is `src/http/app.py:get_case_search`, the read model is
`src/cases/search.py:read_case_search` (`SearchInvalid` / `SearchNotFound` /
`SearchIndexUnavailable`), the DTOs are `SearchResponseDTO`,
`SearchResultItemDTO` and `SearchAppliedFiltersDTO` in `src/http/schemas.py`,
and `src/http/mappers.py:map_search` maps snake_case to the pinned camelCase
shape. There is no mutation route; `POST`/`PUT`/`PATCH`/`DELETE` are 405/404.

200 payload (field names and shapes are pinned by the ticket; the frontend
workspace UI codes against them):

```json
{
  "caseId": "case-1", "query": "applied trimmed q", "total": 42,
  "limit": 25, "offset": 0,
  "appliedFilters": {"type": "claim", "publisher": null, "status": null,
                     "publishedFrom": null, "publishedTo": null},
  "items": [{"resultType": "claim", "id": "...", "claimId": "...",
             "evidenceId": null, "eventId": "...", "captureId": null,
             "title": null, "snippet": "plain text", "matchedField": "body",
             "publisher": null, "status": "alleged", "publishedAt": null}]
}
```

* `id` is the typed entity id; `claimId` is set only for claims, `evidenceId`
  only for evidence. `captureId` is the evidence row's current capture pointer
  (resolved from `evidence_items` for the returned page only) and is always
  `null` for claims.
* `title` is the indexed evidence title (`null` for claims and for evidence with
  no stored title); `publisher` is the indexed evidence publisher; `status` is
  the claim verification state in the API's existing label vocabulary
  (`confirmed|probable|alleged|contested|debunked`, `null` for evidence).
* `publishedAt` is the stored publication time normalized to UTC ISO-8601 when
  parseable, otherwise `null`. An unknown stored date is never invented.
* `eventId` is the indexed event reference (`null` when the source row has none).
* `eventId`, `captureId`, `title`, `publisher`, `status` and `publishedAt` are all
  nullable in the pinned DTO; the frontend types them `string | null`
  (`frontend/src/types/backend-models.ts:CaseSearchItem`) and clients must handle
  `null`. The result IDs feed inspector deep links whose URL keys are `claim`,
  `evidence`, `capture` and — for a historical selection — `snapshot`
  (specification §8, `frontend/src/services/deep-links.ts:INSPECTOR_PARAMS`).
  `snapshotId` is **not** a supported URL key.

## Literal all-term query semantics

`q` is trimmed and validated first: empty/whitespace-only, more than **256 code
points**, or a query with **no searchable terms** is `422` — never a full scan
and never an empty 200.

The query is interpreted as literal AND-ed words:

1. `tokenize_terms` extracts maximal runs of Unicode word code points
   (`[^\W_]+`), keeping the first spelling of each term after
   NFKD/casefold/diacritic normalization for deduplication.
2. `escape_fts_term` wraps each term in a double-quoted FTS5 string literal and
   doubles any internal `"`. Terms can never contain `"`, `*`, `-`, `:`, `(`,
   `)`, `^` or `;`, so escaping is defence in depth rather than the only guard.
3. `build_match_expression` joins the quoted terms with the **only** operator
   this module emits: ` AND `. Everything is bound as a SQL parameter
   (`case_search_index MATCH :match`); no user text is interpolated into SQL.

Consequences, all covered by `tests/test_s02_search_api.py`: `q="quoted
phrase"` matches documents containing both words (not an FTS phrase), `AND`,
`OR`, `NOT`, `NEAR(`, `body:quartz`, `"a" AND "b"` are searched as literal
words, `* - : " ( )` alone are `422`, and `'); DROP TABLE claims;--` and
`'; UPDATE case_search_index ...` are ordinary word queries that leave the index
and tables untouched.

## Filters

* `type=claim|evidence` narrows to the indexed `entity_type`. Any other value is
  `422` (FastAPI literal validation).
* `publisher` is an **exact** match on the indexed publisher key — S01 stores
  `EvidenceItem.publisher`, so the filter is the same value results echo, with
  no host inference, alias resolution, prefix or substring matching. It applies
  to evidence only; `publisher` with an effective claim type is `422`: the
  effective type is explicit `type`, or `claim` when `status` is supplied
  without `type`. `publisher` with `type=evidence` and `publisher` alone remain
  valid. Shorthand prefixes such as `Meridian` match nothing (`200`, `total: 0`). Claims carry an
  empty publisher, so a publisher filter never returns claims.
* `status` is the claim verification state, matched exactly after case
  normalization (`alleged`, `ALLEGED`). Any label outside the API vocabulary is
  `422`. A `status` filter combined with `type=evidence` is `422`; without
  `type` it narrows to claims and `appliedFilters.type` reports `"claim"`. The
  `unknown` label is accepted and matches nothing, because no claim stores an
  unknown verification state — it is not silently reinterpreted.
* `publishedFrom`/`publishedTo` are parsed as UTC ISO-8601 (`Z` accepted, naive
  input read as UTC, other offsets converted) and compared with
  `julianday(published_at)`: UTC start-inclusive, end-exclusive comparison;
  sub-second precision is not guaranteed. Rows whose stored date is empty or
  unparseable evaluate to `NULL` and are excluded whenever either bound is
  supplied. `publishedFrom >
  publishedTo` is `422`. `appliedFilters` echoes the resolved UTC instants.
* Nothing invents evidence-party semantics: there is no party filter and no
  status/verification inference for evidence.

## Paging, ordering, totals

`total` is `count(*)` under the **same** case scope, match expression and
filters, independent of `limit`/`offset`. Ordering is `bm25(case_search_index)
ASC, entity_type ASC, entity_id ASC` — rank first, then the pinned
`(resultType, id)` tie-break, so identical documents order deterministically by
id rather than insertion order. `limit` is bounded 1..100 (an explicit `> 100`
is a `422`, not a silent clamp) and `offset` is bounded 0..2,147,483,647
(inclusive; larger values are `422`). This documented ceiling keeps bound
integers within a sane range and is declared as the route's OpenAPI constraint.
Pages partition the matched set with no duplicates or gaps, and identical
requests return identical JSON.

## Snippet policy

`snippet` is always plain text. It is produced by FTS5 `snippet()` with **empty**
start/end markers and a `...` ellipsis (24-token window), then whitespace is
collapsed. No `<mark>`, `<em>` or any other markup is generated, forwarded or
stored: the payload never contains HTML from the index. `matchedField` is derived
per item — `title` only when every query term occurs in the stored title (so the
title alone explains the match), otherwise `body` — and the snippet is taken from
that field. A search snippet is evidence of a lexical match only; it is **not** a
validated quotation and must not be rendered as one.

## Failure states and read-only boundary

| Condition | Status |
|---|---|
| `q` missing, empty/whitespace, >256 code points, no searchable terms | 422 |
| `limit` outside 1..100, `offset` outside 0..2,147,483,647, invalid `type` | 422 |
| invalid `status`/`publisher`, malformed or reversed date bounds | 422 |
| `status` with `type=evidence` (or `publisher` with effective `type=claim`, including status-implied claim type) | 422 |
| unknown case, or a case the caller cannot see | 404 |
| S01 capability probe reports the index unusable | 503 |
| valid query with no matches | 200 with `items: []` and the real `total` |

Precedence is request validation (422) → case existence (404) → capability
(503) → read: an unknown case is still a `404` while the index is unavailable,
and a valid case with no indexed resources is an honest empty `200` (the pinned
"empty valid result" rule), never a `404` and never another case's rows.

The `503` detail names the operator remedy, e.g.

```
Case search is unavailable for case case-1: SQLite FTS5 module is not compiled
into this SQLite build. Operator remedy: run `triangulate case rebuild-search
case-1` and retry.
```

Both S01 reasons (module absent, `case_search_index` missing) reach that path;
`available: false` is never converted into an empty result and there is no
`LIKE` fallback. Unknown-case and harness errors are not masked by it.

Every SQL statement is scoped with `case_id = :case_id`, so wrong-case rows can
never be filtered out in Python after retrieval. The reader opens the caller's
session, issues only `SELECT`/`PRAGMA` reads through the S01 probe, and never
commits, rebuilds, repairs or synchronizes the index — `tests/test_s02_search_api.py`
captures the full index dump before/after a GET batch (including 404/422/503
probes) and replaces every S01 write helper with a raising stub during that
batch. `src/storage/search.py` remains the only index writer, and the only
repair path is the CLI `triangulate case rebuild-search CASE_ID`.

## Benchmark

`scripts/benchmark_search.py` builds a synthetic fixture in a **temporary**
database (`tempfile.mkdtemp`, never the application database) with the real ORM
models, the S01 capture helper and the S01 synchronization helpers, then times
warm `read_case_search` calls.

Fixture: 4 cases / 40 events / **10,000 evidence + 20,000 claims** (30,000 indexed
rows; 1 in 37 sources deliberately has an unknown publication date) and 320 warm
queries (20 warm-up calls discarded) over 8 single terms, 4 two-term queries and
4 filtered/date/paged variants. Recorded runs on 2026-11-20/21
(`uv run python scripts/benchmark_search.py`, SQLite 3.50.4) after the S01
rowid optimization (`5501842`), one host at recorded load:

| Metric | Value |
|---|---|
| cases / events / evidence / claims | 4 / 40 / 10,000 / 20,000 |
| indexed rows after incremental sync | 30,000 |
| indexed rows after a full case rebuild | 30,000 (identical) |
| index build, S01 `sync_event_index` per event (s) | 14.06–16.91 |
| full case-scoped rebuild, all four cases (s) | 26.18–26.65 |
| database size (MB) | 52.7 |
| warm queries | 320 |
| warm p50 (ms) | 34.7–38.3 |
| warm p95 (ms) | **173.97–207.16** |
| warm max (ms) | 316.98 |
| p95 target < 500 ms | PASS |

Pre-optimization figures on the identical fixture (per-row delete writer) were
index build **425.43 s**, full rebuild **773.12 s**, DB 46.2 MB and warm p50/p95
34.74/165.53 ms; the full before→after record is in the
[index doc](20261120-search-index.md). Per-query-shape breakdowns (single terms,
two-term AND, filtered and date-range variants) are kept in the benchmark JSON
artifacts; latency tracks the size of the matched set (rank + tie-break
ordering), not the returned page size.

Two environment facts are recorded with the numbers, because they dominate parts
of the result rather than the query itself:

* warm latency is host-load sensitive. The table above is from the runs at load
  ~8–19. An earlier run of the identical script while the same host carried a
  load average of ~70 with ~1 GB of 30 GB RAM available reported p95 2,038 ms
  (~2 s) / max 75 s for the same queries, and intermediate after-optimization
  runs at other loads recorded warm p50/p95/max of 46.67/210.42/291.35 ms
  (`/tmp/s01-search-after-final.json`) and 36.47/168.10/195.92 ms
  (`/tmp/s01-search-after.json`). The tail is page-cache/CPU contention, not
  query planning; this is one host at recorded load, not a load test.
* the pre-optimization S01 writer deleted each row before re-inserting it
  against a table with no secondary index, which made index building quadratic
  (probe: 0.16 / 0.60 / 2.39 s for 500 / 1,000 / 2,000 rows with the per-row
  delete versus 0.01-0.02 s without it). The deterministic-rowid change removed
  that scan; **query latency was never affected** — the delete only ran on
  writes, and the only bulk entry point is the operator CLI rebuild.

No timing assertion exists in the test suite.

## Not in this ticket

No cross-case or global search, no `LIKE` fallback, no semantic/vector search,
no filter DSL, no party filter, no snapshot/historical text search, no index
rebuild on `GET`, no mutation endpoint, no frontend code (the workspace UI is the
concurrent frontend half of S02), and no change to the S01 index schema or
writer.
