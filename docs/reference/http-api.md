# HTTP API Reference

The frontend-facing API lives in `src/http/app.py` and exposes persisted case data over JSON.
It is read-only by design.

## Endpoints

### Health

```text
GET /health
```

Returns:

```json
{ "status": "ok" }
```

### Case Collection

```text
GET /api/cases
```

### Case Detail and Tabs

```text
GET /api/cases/{case_id}
GET /api/cases/{case_id}/claims
GET /api/cases/{case_id}/claims/overview
GET /api/cases/{case_id}/evidence
GET /api/cases/{case_id}/exceptions
GET /api/cases/{case_id}/parties
GET /api/cases/{case_id}/timeline
GET /api/cases/{case_id}/run-history
GET /api/cases/{case_id}/report
GET /api/cases/{case_id}/search
```

### Case Search

```text
GET /api/cases/{case_id}/search
```

Case-scoped lexical search over the optional FTS5 index (migration 15). `GET`
only; the route never writes, rebuilds or repairs the index. Full contract:
[`../architecture/20261120-search-api.md`](../architecture/20261120-search-api.md).

Query parameters:

| Parameter | Meaning |
|---|---|
| `q` | required; trimmed, 1..256 code points, literal all-term words (AND-ed; no FTS operators) |
| `type` | optional; `claim` or `evidence` |
| `publisher` | optional; exact indexed publisher key (evidence results only) |
| `status` | optional; claim verification-state label (claim results only) |
| `publishedFrom`, `publishedTo` | optional; UTC ISO-8601, start-inclusive / end-exclusive |
| `limit` | default 25, 1..100 |
| `offset` | default 0, 0..2,147,483,647 |

Response DTOs (`src/http/schemas.py`): `SearchResponseDTO` with `caseId`,
`query`, `total`, `limit`, `offset`, `appliedFilters` and `items[]` of
`SearchResultItemDTO` (`resultType`, `id`, `claimId`, `evidenceId`, `eventId`,
`captureId`, `title`, `snippet`, `matchedField`, `publisher`, `status`,
`publishedAt`). `snippet` is always plain text — never HTML. `eventId`,
`captureId`, `title`, `publisher`, `status` and `publishedAt` may be `null`.

Failure semantics:

| Condition | Status |
|---|---|
| unknown case | 404 |
| malformed query/filter/range (including `status` with `type=evidence`, `publisher` with an effective claim type, `offset` > 2,147,483,647) | 422 |
| search index capability unavailable (FTS5 absent, or `case_search_index` missing because migration 15 is not applied) | 503 |
| valid query with no matches | 200, `items: []`, real `total` |

The 503 detail names the operator remedy, for example:

```text
Case search is unavailable for case <case_id>: <capability reason> Operator remedy: run `triangulate case rebuild-search <case_id>` and retry.
```

There is no `LIKE` fallback and no GET-side repair; `triangulate case
rebuild-search <case_id>` is the only repair path.

## Schema Source

The request and response DTOs are defined in `src/http/schemas.py`. The frontend TypeScript models live in `frontend/src/types/backend-models.ts`.

## Consumption Pattern

The React client calls these endpoints through `frontend/src/services/api.ts` and reads the base URL from `VITE_API_BASE_URL`.
Use the CLI or background operators to create cases, rerun stages, resolve exceptions, or review cases.
