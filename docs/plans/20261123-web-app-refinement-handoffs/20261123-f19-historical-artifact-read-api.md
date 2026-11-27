---
id: F19
status: implemented-and-tested
tier: optional
depends_on: [F16]
---

# F19 — Historical artifact read API (PROPOSED, requires owner approval)

**Size: L · Risk: path traversal / symlink / check-then-follow races.**

[Specification](../20261123-web-app-refinement-specification.md) · [Shared contracts](../20261123-web-app-refinement-contracts.md) · [Implementation hub](../20261123-web-app-refinement-implementation.md)

## Goal
Read-only artifact-descriptor list and allowlisted file-download GETs over immutable stored run artifacts, with strict ownership, containment and honest checksum semantics. Endpoints do **not** exist today; implement only after explicit owner approval. Not D01.

## Read before edit (existing)
- `src/storage/models.py` — `CaseArtifact` :463 (`case_id` :469, `stage_run_id` :470; **no direct grouped-run FK**), `CaseStageRun` :431 (`investigation_run_id` :457)
- `src/cases/service.py` — `_publish_successful_run` :3156 (saved types `report_json→topic_analysis.json`, `report_markdown→topic_report.md`, `execution_manifest→manifest.json`), `_payload_checksum` :267 (**payload checksum, not file bytes**); writer directory helpers that mkdir at :3091/:3218 — **MUST NOT be reused by readers**
- `src/http/app.py` route/mapper patterns

## Proposed NEW paths
- PROPOSED `src/cases/artifact_reader.py` — **pure path resolution only** (no mkdir/write helpers)
- PROPOSED `tests/test_refinement_artifact_reader.py`

## Implementation steps
1. `GET .../investigation-runs/{run_id}/artifacts` (descriptors) and `.../artifacts/{artifact_id}` (bytes) per contracts §13. Ownership proof: `artifact.case_id`, `stage_run.case_id`, and `stage_run.investigation_run_id == run_id`.
2. Types allowlist: `report_markdown|report_json|execution_manifest`. Descriptor: `artifactId`, type, safe display name, download URL, `recordedChecksum` + `checksumKind: payload_json|unknown` — never a filesystem path; stored checksum is not file proof; no list-time existence claim; missing path/bytes → 404; no inline/latest fallback ever.
3. Download hardening: no client path input; run-root containment; reject traversal, symlink components, escapes, wrong owner, temporary unpublished artifacts; fixed allowlisted filenames per type; max 50 MiB → 413 `too_large`; `Content-Disposition: attachment` (safe constant + encoded ids, no CRLF); correct `text/markdown`/`application/json`; `nosniff`. Verify the **opened file handle** is the checked file (race guard). No HTTP/S3/remote paths.
4. GETs never generate, repair, create reports or publish unreferenced files. No migration needed.

## Non-goals
No PDF/ZIP, no chain-of-custody claims, no writer refactors, no new schema.

## Acceptance criteria (testable)
1. Wrong case / wrong run / missing artifact each return uniform 404 (parity tests).
2. Symlinked file, `../` traversal and wrong-owner artifact are all rejected (parametrized security tests).
3. Oversize file returns 413 `too_large`; permission failure is redacted and non-leaky.
4. Batch test proves zero writes on GET (output-dir hash unchanged) and no writer mkdir helper is reachable from the reader (source grep).
5. Descriptor exposes `checksumKind ∈ {payload_json, unknown}` and never a filesystem path (schema assertion).

## Focused tests and commands
PROPOSED `tests/test_refinement_artifact_reader.py`; `uv run pytest -q tests/test_refinement_artifact_reader.py`; full gates in the disposable copy per contracts §1.

## Rollback and compatibility
Additive modules/routes; delete to roll back. Existing report reader (F14) unaffected.

## Worker brief (copy-paste)
You are the single code worker for F19 (this card). One application code writer globally. **PROPOSED endpoints — implement only with explicit owner approval recorded first.** Read contracts §13 and specification X02. Pure path resolution only — never reuse writer directory helpers; handle-based race guard; checksumKind honesty. Disposable-copy gates per contracts §1. No commits. Return hub §5 format.