# Release A acceptance and P01 handoff

Date: 2026-11-18. Status: **Release A is accepted** (B00–B03, E01–E04). E04
landed as `8ee32eb` on `main`. The next ticket is **P01 — conservative source
dependency groups**, the first Release B ticket. P01 does not start P02/P03 and
does not require a schema migration.

## 1. What Release A delivers

| Ticket | Delivered |
|---|---|
| B00–B03 | Reproducible frontend toolchain, atomic case/review persistence, honest acquisition outcomes, truthful reader states |
| E01 | Immutable `EvidenceCapture` versions with nullable current pointer |
| E02 | Validated quotations, append-only `ClaimCitation`, policy-derived relationships/counts |
| E03 | Typed GET readers for citations, claims, evidence and code-point capture windows |
| E04 | Evidence inspector inside the existing tabs, code-point highlighting, capture/window navigation, frozen `?citation=` deep links, safe metadata and distinct states |

Release A gate evidence:

- Frontend: `npm run check` green; `npm test -- --run` = **93 passed in 11 files**.
- Backend: **418 passed, 9 deselected** in the disposable copy; Ruff clean.
- Browser: Playwright isolated session against a temporary DB/config; 0 console
  errors; inspector requests GET-only; reload/back/forward, keyboard activation,
  404, ambiguous/legacy passages, long-window paging and HTML/URL safety checked.
- No backend behaviour, production data, `data/`, `triangulate.db`, `.env` or the
  pre-existing scratch files were changed.

## 2. P01 contract (specification §5)

Implement **observed publisher counts and dependency groups**, never an
independence score or a “verified independent” state.

### Identity and normalization

- Canonicalize HTTP(S) URLs locally: lowercase/IDNA host, drop fragment/default
  port/userinfo, normalize empty path to `/`, remove only `utm_*`, `fbclid` and
  `gclid` tracking parameters. Preserve path case, trailing slashes, HTTP vs
  HTTPS and all other query values. Never fetch or rewrite stored URLs.
- `publisher_key` comes from explicit frozen metadata (`publisher_key` /
  `publisher_identity`) when present; otherwise the normalized host is a
  **provisional** key. A publisher display name alone never establishes identity.
  Missing host and metadata stay unknown.

### Dependency edges (v1 only)

1. Same normalized source URL.
2. Same publisher key (explicit or provisional host).
3. Identical text copy fingerprint: NFKC + casefold + collapsed whitespace,
   required on **at least 200 non-whitespace code points**; short snippets never
   merge sources.
4. Documented common origin: same non-null `case_article_id`, or the same explicit
   `source_dependency_key` / `dependency_key` metadata value.

Groups are connected components of those edges. Near-duplicate/semantic
syndication detection is explicitly deferred and must be disclosed as a coverage
limitation.

### Counts and scope

- Expose `distinctPublisherCount` (distinct known keys), `dependencyGroupCount`,
  `unknownPublisherCount`, and `independenceStatus` (`unknown` or
  `dependency_detected`). Absence of a detected dependency never proves
  independence.
- Groups expose deterministic IDs, reasons, publisher keys and evidence/capture
  membership, including older capture versions used by a claim link.
- Case-level groups use all case evidence and each item's current capture.
- Claim-level groups use only that claim's linked evidence (deduplicated, with the
  link's validated capture when present). A copy relationship about another claim
  must not imply dependence for every publisher in the case. Same-publisher edges
  are applied inside the selected scope.
- Repeated wire copies remain separately inspectable evidence records but count
  once as a dependency group for observed source breadth.

### Surface

- One case-scoped reader with an optional claim selector, exposed as
  `GET /api/cases/{case_id}/sources` and
  `GET /api/cases/{case_id}/sources?claimId=...` (snake_case alias accepted;
  conflicting selectors rejected with 422).
- Unknown case/claim and wrong-case claims → 404; valid empty scope → 200 with an
  empty summary and explicit unknown independence. GET creates nothing.
- New DTOs/mappers/service reader + `src/cases/provenance.py`; no migration, no
  separate publisher service, no frontend page in P01.
- Existing `sourceDiversityCount` stays a documented compatibility field; do not
  reinterpret it as independently verified sources.

## 3. Commands

```bash
# backend (disposable copy only)
SAFE_DIR=$(head -1 /tmp/triangulate-safety-verification-dir)
tar --exclude='__pycache__' --exclude='*.pyc' -cf - src tests | tar -C "$SAFE_DIR" -xf -
cp bias_taxonomy.toml "$SAFE_DIR"/ 2>/dev/null || true
cd "$SAFE_DIR"
env LLM_API_KEY= OPENAI_API_KEY= LANGSMITH_TRACING=false uv run pytest -q --disable-warnings
uv run ruff check src tests --output-format concise
```

## 4. Out of scope

P02 comparison API, P03 comparison UI, snapshots (R03), search (S01/S02),
near-duplicate/semantic copy detection, publisher-ownership inference, external
lookups, production data and any new mutation endpoint.
