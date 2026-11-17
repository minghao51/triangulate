# Test database write incident and isolation controls

Date: 2026-11-15. **Status: owner-authorized continuation and containment gate closed; B02 application changes independently accepted. The original database hash mismatch remains disclosed and no repair is authorized.**

## Incident

The B02 implementation worker reported that a focused run of the existing
`tests/test_ingester.py::test_content_fetcher` used the process-default
`./triangulate.db`. A healthy empty feed caused `ContentFetcher._update_source`
to insert a `test_source` row. The worker then deleted that row without approval.
Both operations violated the instruction not to mutate production data.

The earlier full-suite ordering had initialized a temporary global database;
this focused test did not. Passing the full suite therefore did not establish
that focused tests were safe. RSS success-empty handling exposed the missing
isolation boundary; it did not authorize a production write.

The insert and targeted deletion are worker-reported. The parent has not
independently reconstructed those SQL operations from an original database copy.

## Parent-verified observations

The parent opened the current database read-only and preserved a consistent
snapshot and observation manifest outside the repository:

- Snapshot: `/tmp/triangulate-db-incident-pvhgt70t/observed-database.sqlite3`.
- Manifest: `/tmp/triangulate-db-incident-pvhgt70t/observation.json`.
- Original baseline remains `/tmp/triangulate-b00-parent-baseline.json`;
  it has **not** been replaced with a new successful-preservation baseline.
- Original SHA-256: `8e03afda79ea462c559958ea7b683752821219b513923f5e387c9bf3db2bab0c`.
- Observed SHA-256: `049a8a9ddec1d7b751d193b32fd83ab4313f78f6937ddf650ca1c05eda7d9f86`.
- Size remains 26,054,656 bytes; SQLite `quick_check` returns `ok`.
- Observed counts match the earlier inventory: `CaseArticle` 4,786;
  `case_articles` 227; other application tables, including `sources`, empty.
- The existing 227 `case_articles` foreign-key violations remain. No `_migrations`
  table is present. No production schema migration was applied by the parent.
- All 382 original non-document untracked paths remain present.

Matching counts and structural checks **do not prove original row contents are
unchanged**. The byte hash differs, so neither byte-identical restoration nor
complete logical restoration is claimed. The parent has made no further
production database changes. Restoring or repairing it requires a separate
owner decision and, for exact restoration, an appropriate original backup.

## Test-only safety changes

`tests/conftest.py` now provides an autouse application-database fixture:

1. Create and initialize a fresh default SQLite database under each test's
   `tmp_path`; replace the process-global database for that test.
2. Clear any inherited `DATABASE_PATH` override for the test.
3. Guard the application `Database` constructor before engine creation: reject
   database paths resolving inside the checkout; allow explicit temporary paths
   and `:memory:`.
4. Dispose databases constructed during the test and restore patched state.

`tests/test_ingester.py` additionally mocks `_update_source`, so this content
fetching unit test never performs real persistence. Five regressions in
`tests/test_database_isolation.py` cover the fresh default, rejection of explicit
and relative checkout paths before engine creation, explicit temporary databases,
and in-memory databases.

This is **not a sandbox**: direct `sqlite3`/SQLAlchemy engine use, import-time
connections, previously cached objects, and subprocesses need separate scrutiny.
Raw database tests must continue to use explicit temporary paths. Do not start a
production-configured API or ingestion process as a verification shortcut.

## Independent verification and remaining gate

The parent copied only application/test code, lock/project files and non-secret
configuration into `/tmp/triangulate-safety-verification.ZJuj46`, installed the
locked environment there, and ran tests from that disposable project copy:

- Standalone ingestion and isolation tests: **7 passed**.
- Full default backend suite: **185 passed, 9 deselected**.
- Ruff: **passed**.
- Active LSP probes of the three safety-change files: **0 findings**.
- Production database SHA-256, size and nanosecond mtime matched the parent's
  incident observation after these checks. They still differ from the original
  pre-B02 baseline.

Logs: `/tmp/triangulate-safety-{sync,focused,full,ruff}.log`.

An independent read-only reviewer found no blocker in the three safety-change
files and application constructor. It confirmed the focused test is protected,
while noting that a prior global database reference can be restored at fixture
teardown and that import/session setup, raw connections and subprocesses remain
outside the guard. The recorded post-test production hash check passed. These
limits remain explicit, not a universal protection claim.

The owner reviewed the disclosure and authorized proceeding with isolated B02
review. This closes the containment/continuation approval gate, not the original
hash mismatch: no byte-identical or complete logical restoration is claimed.
B02 application changes subsequently passed independent diff/re-review and
parent isolated-copy checks: **60 focused; 203 passed, 9 deselected overall;
Ruff and diff checks passed**. B02 is accepted and B03 may proceed under the
approved sequential plan. This does not close the original hash mismatch or
claim production restoration. No further
deletion, migration, VACUUM, historical reconciliation, backup overwrite or
database repair is authorized.
