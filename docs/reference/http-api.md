# HTTP API Reference

The frontend-facing API lives in `src/http/app.py` and exposes case data over JSON.

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
POST /api/cases
```

`POST /api/cases` accepts:

```json
{
  "query": "Gaza ceasefire negotiations",
  "conflictDomain": "gaza_war",
  "confirmedParties": ["Hamas", "Israel"],
  "manualLinks": ["https://example.com/source"],
  "automationMode": "safe",
  "maxArticles": 50,
  "relevanceThreshold": 0.3
}
```

### Case Detail and Tabs

```text
GET /api/cases/{case_id}
GET /api/cases/{case_id}/claims
GET /api/cases/{case_id}/evidence
GET /api/cases/{case_id}/exceptions
GET /api/cases/{case_id}/parties
GET /api/cases/{case_id}/timeline
GET /api/cases/{case_id}/run-history
GET /api/cases/{case_id}/report
```

## Schema Source

The request and response DTOs are defined in `src/http/schemas.py`. The frontend TypeScript models live in `frontend/src/types/backend-models.ts`.

## Consumption Pattern

The React client calls these endpoints through `frontend/src/services/api.ts` and reads the base URL from `VITE_API_BASE_URL`.
