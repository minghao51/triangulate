# Transactional case search index (S01)

Date: 2026-11-20. Status: **implemented (`3096c0f`, `5501842`), reviewed and
verified locally in the V01 pass; not pushed**.
Migration **15**. This documents the index contract consumed by the
[search read API](20261120-search-api.md) (S02); it does not add a
search HTTP route or frontend.

## Shape and capability

`case_search_index` is one SQLite FTS5 virtual table using `unicode61`. `case_id`,
`entity_type`, `entity_id` and the S02 filtering metadata (`signature`, `event_id`,
`party_id`, `publisher`, `status`, `published_at`) are `UNINDEXED`; `title` and
`body` are indexed and stored for retrieval/snippets. Each logical evidence has
one row: title plus only its selected `EvidenceCapture.text`. Each current claim
has one row with `claim_text` in body. Events, narratives, articles, citations,
snapshots, capture history and unowned legacy evidence are not indexed.

`probe_search_capability` is read-only and constant-work: it checks module registration through `pragma_module_list` (with a read-only `PRAGMA compile_options` fallback on older SQLite), checks `sqlite_master`, and resolves the table with `LIMIT 0`; it does not count or scan indexed rows. Capability is resolved once per sync/rebuild and once per explicit public row upsert/delete, then threaded through private helpers without hidden global state. Only genuine module absence or a missing migration table is unavailable; database errors, locked/I/O failures and table errors propagate so the owning transaction can roll back. Exact reasons are `SQLite FTS5 module is not compiled into this SQLite build.` when module registration is absent, and `FTS5 module is available, but case_search_index is missing (migration 15 is not applied).` when FTS5 exists but the table is absent. There is no LIKE fallback.

Migration 15 is additive. It attempts virtual-table creation and records the migration only when creation succeeds or SQLite explicitly reports `no such module` for FTS5. Every other DDL error propagates and the migration is not recorded as applied. See the capability section for precise reasons.

## Synchronization and rollback

There is exactly one synchronization mechanism: application-level synchronization
through `sync_event_index` / `sync_evidence_index`, called by the owning write path.
After the complete event rewrite is flushed, `store_event_in_db` calls
`sync_event_index` in the same caller-owned session, before owner validation and
commit (or within the event batch's caller-owned transaction). The helper removes
rows by event metadata once, then rebuilds current persisted claims and evidence.
Each entity uses a deterministic positive 63-bit BLAKE2b-derived FTS rowid from
`(entity_type, entity_id)`; the source tables enforce globally unique IDs within
each entity type. A rowid-scoped replacement avoids scanning UNINDEXED identity
columns for each row. A 63-bit digest has an approximate 4.9e-11 birthday
collision probability at 30,000 distinct rows; collisions remain a theoretical
risk. Stable IDs replace deleted/re-written claims and
move evidence to its current capture text without changing rank/tie ordering,
and the event-wide delete clears rows when an event becomes unowned. Case-bound OSINT evidence has
no event row, so `ingest_osint_artifact` persists its capture and calls
`sync_evidence_index` before validating/releasing its existing R02 `evidence`
owner. `record_evidence_capture` itself remains a storage primitive; it has no
independent index write path. Intake/review-driven event writes use the event-store
seam. No ORM trigger or asynchronous mechanism can diverge from these owner
transactions.

All helpers take a caller-owned `Session` and never commit. SQLite FTS virtual-table
DML participates in the same transaction: rollback of the event write rolls back
both index deletion and insertion. `upsert_index_row` and `delete_index_row` are
provided for targeted use; `indexed_counts` reports per-case evidence/claim counts.

## Explicit repair

`triangulate case rebuild-search CASE_ID` claims the case with a short R02
`evidence` owner, performs one case-scoped FTS delete, then inserts only current
owned EvidenceItem rows and claims joined through events in that case. It
validates and releases the owner, then commits once. Event sync similarly performs
one event-metadata delete followed by rowid replacements; standalone evidence
sync deletes/replaces only its deterministic rowid. Repeated synchronization and
rebuilds preserve the row identity and rows/counts. A foreign active writer prevents admission;
there is no force/steal path. Repeating a rebuild yields the same rows and counts.
When unavailable, the command reports the reason and does not claim an index was
built. Rebuild is CLI-only; no GET creates, repairs or rebuilds index state.

## Verification and limitations

Focused tests drive both real `store_event_in_db` modes (standalone and caller-owned), OSINT ingestion, title/body/claim matching, rewrites/deletion, rollback equality, case isolation, unowned-event cleanup, signature metadata backfill, idempotent rebuild, foreign-owner refusal, and fresh/legacy-v14 migrations. A denied virtual-table creation is treated as a real migration failure (not mislabeled as absent FTS5); capability tests pin both exact unavailable reasons and DB-error propagation. Runtime SQLite FTS5 probe reports SQLite 3.50.4 in the disposable environment. The S01 optimization was measured against the documented S02 fixture (4 cases, 40 events, 10,000 evidence, 20,000 claims; 30,000 rows) in a temporary database: index sync improved from **425.43 s to 14.06–16.91 s**, full rebuild from **773.12 s to 26.18–26.65 s**, while DB size changed from **46.2 MB to 52.7 MB**. Warm query p50/p95 was **34.74/165.53 ms before** and **34.7–38.3 / 173.97–207.16 ms after** (max 316.98 ms; same 320-query workload, recorded runs at load ~8–19; an intermediate after-run at higher host load recorded 46.67/210.42 ms, and an earlier heavy-load run reported p95 ≈ 2 s — the [search read API benchmark](20261120-search-api.md#benchmark) records the load caveat in full). Query SQL/order is unchanged and p95 stays below 500 ms. The focused S01/S02 tests passed **60**; the full disposable-copy suite passed **613 tests, 9 deselected** at the S01-perf checkpoint and **614 passed, 9 deselected** at the final Release C gate (V01 adds `tests/test_v01_e2e.py`); Ruff clean (`All checks passed!`, final gate scope `src tests scripts`). See the S01 worker-plan entry for commands and limitations. Direct SQL, bulk updates/deletes, and any future evidence writer bypassing the
synchronization helper can drift until a case-scoped rebuild; those are unsupported
writers, not silently covered by the application fence. Current synchronization depends on `event_id` metadata being
present on indexed entities. This index intentionally does not preserve historical
capture text or deleted-claim history.
