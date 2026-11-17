# Setup, repository, and maintenance audit

Date: 2026-11-14. Status: **audit delivered; cleanup, dependency changes, and database repairs require approval**.

Companion documents:

- [Architecture as inspected](../architecture/20261114-current-architecture.md)
- [Comparable products and prioritized enhancements](../plans/20261114-product-enhancement-roadmap.md)

## Executive assessment

Triangulate has a useful Python/SQLite investigation core and an API-backed React reader. The immediate priority is **data integrity and honest product behavior**, not adding more dashboards. Repository clutter is real, but indiscriminate deletion would risk losing the only record of historical ingestion and repair work.

The audit did not delete, move, or modify application code, existing plans, source data, or the live database. New dated documentation records the findings. Dependency checks used the existing Python environment; frontend workaround verification used an isolated `/tmp` copy. No production ingestion or migrations were run.

## 1. Scope and verification

Reviewed: setup manifests/lockfiles, configuration, active architecture and planning docs, backend ingestion/AI/case/storage/API paths, frontend routes/services/stores/pages/tests, scratch-file inventory and references, accessible local scheduler definitions, and read-only local database metadata/integrity. Three independent review tasks covered backend, frontend, and cleanup/documentation; significant findings were checked against source bodies or runtime probes.

| Check | Result | Interpretation |
|---|---|---|
| `uv sync --frozen --all-extras` | Passed | Existing Python lock installs; this is not a security scan |
| `uv run pytest -q --disable-warnings` with LLM credentials cleared and tracing disabled | **116 passed; 9 deselected** | Default suite, not live-provider or production-data validation |
| `uv run ruff check src tests --output-format concise` | Passed | Scoped to maintained source/tests, not hundreds of scratch scripts |
| Normal `npm ci --ignore-scripts --no-fund` | **Failed** | Vitest 3.2.4 conflicts with coverage-v8 4.1.0 |
| `npm ci ... --legacy-peer-deps` | **Failed** | Lockfile lacks platform-native esbuild/Rollup entries required by clean installation |
| Repository `npm run check` and `npm test -- --run` | Blocked | Missing `eslint`/`vitest` because installation failed; not application-code test failures |
| Isolated copy: `npm install --legacy-peer-deps --ignore-scripts`, then `npm run check` | Passed | Lint, typecheck, production build pass under a workaround; source lockfile remains unrepaired |
| Same isolated copy: `npm test -- --run` | **13 passed in 2 files** | Component tests, not full feature coverage |
| Browser: monitoring with mocked `GET /api/cases -> []` | Confirmed defects | Zero monitors still show three alerts and 98% health; missing button styles reproduced |
| Local SQLite `PRAGMA quick_check` via URI `mode=ro`, `query_only=ON` | `ok` | File structurally readable; does not mean relationships/application data are correct |
| Local SQLite `PRAGMA foreign_key_check` | **227 violations** | All in `case_articles` |
| Scratch SQLite connection using application `Database` | `PRAGMA foreign_keys = 0` | ORM foreign keys are not enforced |

Node 24.13.0, npm 11.6.2, uv 0.9.7 were used. The isolated production build emitted a roughly 266 kB main JavaScript chunk (85 kB gzip), plus lazy/shared chunks; this is not a Lighthouse or full transfer-budget result.

### Dependency security snapshot

- `npm audit --package-lock-only --json`: **28 affected package entries**: 2 critical, 14 high, 10 moderate, 2 low. The critical entries include `vitest` and its transitive `tinypool`; other entries include Vite, React Router, parsers and build tooling.
- Python lock export including optional dev extras, scanned with `pip-audit --no-deps --disable-pip`: **21 affected packages**, 164 raw advisory records / 108 distinct package-and-advisory-ID pairs. Duplicate advisory records exist; these are not 164 independently verified application exploits. Reported packages include LiteLLM, aiohttp, Starlette, LangChain components, urllib3, and parsers.
- Reachability matters: many LiteLLM findings concern its separately deployed proxy/admin endpoints, which are not the same as this application's use of the library; React Router SSR/RSC advisories likewise do not automatically apply to a client-only SPA. Dev-server findings require corresponding exposure. Nevertheless, stale libraries processing untrusted sources and exposed development tools need prioritized review.
- Do not run `npm audit fix --force` or broadly upgrade the AI stack without a reviewed version plan and regression tests.

Raw command evidence is retained outside the repository in `/tmp/triangulate-audit-{pytest,ruff,frontend-check,frontend-test,isolated-check,isolated-test}.txt`, `/tmp/triangulate-audit-npm.json`, and `/tmp/triangulate-audit-python.json`. These are temporary evidence files, not committed deliverables.

## 2. Findings by priority

### P0 — Protect and reconcile the historical data before cleanup

Observed in `triangulate.db` using strictly read-only SQLite access:

| Table/state | Observation |
|---|---|
| Database size | 26,054,656 bytes |
| `topic_cases` | **0 rows** |
| Official ORM `case_articles` | **227 rows**, all with missing case parents |
| Separate table `CaseArticle` | **4,786 rows**, not the table mapped by the application |
| `events`, `claims`, `evidence_items`, `intake_items`, `sources` | 0 rows in each |
| `_migrations` | Absent |

`src/storage/models.py:292–315` maps `CaseArticle` to **`case_articles`**, not `CaseArticle`. The local ingestion history is therefore split from the case-oriented application read model. This explains why article collection alone does not imply that the app has browseable investigations. The audit does not establish why every historical row was written or that all 5,013 rows are unique.

Sampled helpers confirm the split: `_cron_tmp/step5_manifest_db.py:39–50` directly writes `CaseArticle`; `scripts/backfill_ingestion_2026-04-04_to_2026-04-10.py` targets `case_articles`. Several helpers hardcode `/home/howt/Work/triangulate`, whereas the inspected checkout is under lowercase `work`.

**Smallest safe next step:** stop competing writers during a consistent backup; inspect/repair a copy; define URL/fingerprint deduplication and original provenance; import historical unassigned material through a canonical intake path or explicitly reconstruct valid case associations. Rehearse restoration and compare row/content counts before touching the original. Do not fabricate case ownership, delete orphans, drop `CaseArticle`, or run migration initialization merely to make the schema look tidy.

### P1 — Event persistence failure can be reported as stage success

`src/cases/service.py:1357–1371` ignores the Boolean return of `store_event_in_db()`. The store catches exceptions, rolls back and returns `False` (`src/storage/event_store.py:363–370`), while `_execute_stage()` marks the stage completed when its callback returns (`src/cases/service.py:1684–1703`). A failed event write can leave a nominally successful stage with incomplete persisted output.

**Fix:** propagate the failure or record an explicit per-event failed outcome. Add a forced-store-failure regression test before changing behavior. This problem is specifically in the stage callback; the intake path already checks the return value.

### P1 — Source attachment is presented as claim support without passage validation

`_build_event_evidence()` assigns `relation='supports'` and confidence 0.5 to the captured article (`src/cases/service.py:1269–1318`). `_augment_claims_with_evidence()` attaches the same evidence list to every extracted claim and derives support/diversity counts from it (`:1320–1355`). An ingestion check saying “captured” is not claim verification. Baseline verification also initially uses `source_count=1` (`src/ai/workflow.py:173–183`).

**Fix:** distinguish reported assertion, supporting passage, independent corroboration, contradiction and reviewer determination. Store a quotation/location and provenance for claim links. Keep unsupported relationships unverified rather than upgrading labels from model confidence.

### P1 — Operational screens contain fabricated data

- `frontend/src/pages/MonitoringCenter.tsx:29–82`: fixed clock, schedules and alerts; additional fixed health/performance values later in the component. Controls for creating/running/editing/deleting monitors are not backed by operations.
- `frontend/src/pages/PipelineMonitor.tsx:34–49`: six hardcoded log messages under a “real-time” description, although stages/history elsewhere are API-backed.
- Browser reproduction with **no cases** still displayed alerts for 15 new articles, three changed claims, and successful checks for “Unknown Monitor”.

**Fix:** remove or clearly segregate demo content immediately. Show measured values or explicit unavailable/empty states. Under the current architecture, read-only scheduler/run projections and CLI guidance are appropriate; adding mutation APIs is a separate decision.

### P1 — Source/narrative analysis overstates heuristics

`SourceAnalysis.tsx:42–82` guesses region/bias using publisher-name substrings and supplies hardcoded baseline metrics. `NarrativeLandscape.tsx:40–96` uses keyword buckets/stance guesses, not backend narrative analysis, and labels verification share as sentiment. Its empty-data percentages can divide by zero (`:353–372`).

**Fix:** remove misleading labels/baselines, explain methodology and unknowns, and consume persisted analytical outputs when available. Do not equate source-level political orientation with factual accuracy of a claim.

### P1 — Clean frontend setup and dependency remediation are blocked

`frontend/package.json` mixes Vitest 3 and its version-4 coverage provider; native optional packages are missing from `package-lock.json`. The workaround build does not repair reproducibility.

**Fix:** choose a supported, security-reviewed matching test/coverage version, resolve other peer constraints, regenerate the lockfile with a documented Node/npm version, then prove a fresh `npm ci`, `npm run check`, `npm test -- --run`, and browser tests. No dependency files were changed in this audit.

### P2 — Database enforcement and queue concurrency need explicit guarantees

- `src/storage/database.py:27–35` does not enable SQLite foreign keys. A scratch database confirmed enforcement is off. Repair existing data **before** enabling enforcement.
- `src/cases/service.py:294–331,707–718` selects queue IDs then independently marks each item processing, without an atomic pending-only claim. Explicit IDs can select previously processed items.

**Fix:** atomic claims, retry/reprocessing semantics and a concurrency test; then per-connection foreign-key enforcement with integrity tests after data reconciliation.

### P2 — Retrieval failures can resemble an empty successful feed

`src/ingester/rss.py` catches feed failures and returns empty lists. The topic-fetch path can interpret these as successful empty acquisition; `_persist_retrieved_articles()` sets a successful monitor checkpoint timestamp unconditionally (`src/cases/service.py:998–1019`).

**Fix:** distinguish empty feed, failed fetch, partial success and full success. Preserve source-level failure status and prevent false-success checkpoints; add all-feeds-failed and partial-failure tests.

### P2 — Trust boundaries must precede network exposure

There is no authentication/authorization in `src/http/app.py`. It exposes case data and report files to reachable callers. `serve` defaults to loopback, so this is a deployment-boundary risk rather than proof of an internet-exposed instance.

`src/ingester/url_capture.py:9–47` fetches supplied URLs without destination-IP/protocol/redirect validation; the trafilatura path is synchronous and does not inherit the fallback HTTP client's timeout. This is an SSRF/availability concern if URLs are supplied by untrusted people or automation. It is **not** currently an unauthenticated web mutation endpoint.

**Fix:** retain loopback/trusted deployment until access controls exist; validate capture destinations/redirects and bound extraction work before expanding input surfaces. Constrain report file roots when strengthening the download boundary.

### P2 — Frontend failures and incomplete styling escape current tests

- `CaseIntelligenceCenter.tsx:51–61,102–124` omits the React Query error and relies on a separate unset error state, resulting in a blank detail page after failed loading.
- `CorroborationNetwork.tsx` and `NarrativeLandscape.tsx` hardcode an error value to null; some tab effects retain stale state across case changes.
- `Button.tsx:22–35` uses Tailwind-style arbitrary-color, padding, hover and focus classes, but the app only ships a partial handwritten utility set in `index.css`, with no Tailwind generator configured. Browser inspection found the primary “New Monitor” button had **0px padding and browser-default gray background**, despite its cyan/padded class names. A passing TypeScript build cannot detect missing CSS rules.
- Keyboard-inaccessible case-card containers, unassociated filter labels, missing accessible names, and absent general reduced-motion/focus treatment remain.
- Specialized pipeline/network/source/narrative routes exist in `app/routes.tsx:18–22`, but normal case tabs do not link to them.

**Fix:** query-driven error/retry states, route-change tests, one supported styling strategy, keyboard/label fixes, and visual/accessibility smoke tests. Decide whether incomplete specialized pages should be linked, explicitly labeled demo, or hidden.

### P2/P3 — Setup and documentation do not fully match runtime

- `TopicFetcher` reads catalogs from `data/source/<conflict>/*.csv`; no CSV catalog exists in this checkout, and the entire `data/` directory is ignored. The existing topic directories (`middle-east`, `trump-news`) also differ from examples using `gaza_war`. Document/provide a small supported catalog and accepted domain mapping rather than assuming arbitrary folders work.
- `src/cli/commands/pipeline.py` imports `yaml`, but PyYAML is not a direct project dependency; it currently arrives transitively.
- `.env.example`, TOML and hardcoded initialization/logging defaults are not a single coherent configuration contract. Make provider/base URL/model and database-path precedence explicit.
- No checked-in CI workflow was found. Add locked-environment backend/frontend gates after fixing clean installation.
- The root README and frontend README still describe `/` as a case index; actual `/` redirects to `/dashboard`.
- `docs/project_roadmap.md` references `backend/http/`, whereas the implementation is `src/http/`; its proposed mutations/collaboration need an explicit boundary decision.

## 3. Cleanup inventory and disposition

Initial snapshot, before new audit docs and generated test caches: **188 tracked files** (1,833,472 bytes) and **382 untracked files** (2,490,841 bytes). Existing tracked content was unchanged. Ignored content was about 579 MB apparent size, mostly the virtual environment and source data; ignored counts are time-sensitive.

| Group | Count / approximate bytes | Disposition |
|---|---:|---|
| Root untracked Python, including `.verify_db.py` | 293 / 1,802,914 | Preserve pending ownership and canonical ingestion/recovery plan |
| Untracked `scripts/*.py` | 20 / 206,986 | Preserve; includes backfill/data helpers |
| `_cron_tmp/*.py` and shell helper | 19 Python + 1 shell / 35,591 | Preserve together with related input artifacts |
| Root backfill Markdown | 10 / 39,120 | Low-risk **relocation** candidates; historical run evidence, not successful-coverage certificates |
| Untracked JSON/XML/HTML, including root result JSON | 39 / 406,230 | Preserve; not proven reproducible temporary files |
| Initial root/source bytecode caches | 49 / 519,822 | Reproducible; optional deletion after approval; counts increased during tests |
| `.venv/` | About 510 MB | Keep for routine cleanup; removable/rebuildable only as a deliberate environment reset |
| `data/` | 7,288 files / about 42 MB | Preserve: captured material/config/manifests, not disposable cache |
| `triangulate.db`, logs, generated reports | Local state | Preserve and back up; do not include in broad clean commands |

That is **332 untracked Python helpers plus one shell helper**, not 333 Python files. No `git clean -fdx`, blanket `rm _*.py`, deletion by age, or execution of old cleanup scripts is appropriate.

### Operational reference checks

No literal tracked-to-untracked filename references were found in the scanned tracked text. Scratch helpers do reference one another: the October diagnostics import the October ingestion helper; `process_source_nyt.py` depends on `process_source.py`; `_cron_tmp` scripts consume saved JSON inputs. Filename scans cannot exclude dynamic or external references.

The current user had no crontab; user/system timer listings had no Triangulate-labelled entries; 592 readable cron/systemd files had no relevant project matches. Other users, external agents/services and manual launchers were not ruled out. A `cron` filename is neither proof of active scheduling nor proof of obsolescence.

### Verified unreferenced frontend candidates

These have no source consumers (except `CaseIndex.tsx` importing its own CSS), and are candidates for a small follow-up removal commit, not deleted in this audit:

```text
frontend/src/pages/CaseIndex.tsx
frontend/src/pages/CaseIndex.css
frontend/src/pages/CaseDetail.css
frontend/src/pages/InvestigationComposer.css
frontend/src/pages/NewInvestigation.css
frontend/src/components/data-visualization/MetricsGrid.tsx
frontend/src/components/data-visualization/StatusHeatmap.tsx
frontend/src/components/design-system/ProgressBar.tsx
frontend/src/components/design-system/Tooltip.tsx
frontend/public/vite.svg
```

Dependency candidates with no source imports: `react-simple-maps`, `topojson-client`, their two type packages, and `framer-motion`. The animation package is also referenced by an unfinished plan: removing it should explicitly retain/defer the requirement rather than pretend the feature was completed. Keep live visualization pages, active CSS, CLI commands and compatibility surfaces unless separately justified.

### Plans and archival decisions

| Material | Decision | Evidence |
|---|---|---|
| `frontend/20250319-phase5-implementation-plan.md` | **Keep active/partial**, not completed | Top-level lazy loading exists; animations, shared refresh, error boundaries, keyboard/focus work and validation are incomplete |
| `docs/project_roadmap.md` | **Keep open; reconcile with new roadmap** | Collaboration, annotations, OSINT ingestion and real alerts are not established; proposed OSINT CLI module absent |
| `docs/landscape.md` | Reference/research, not completion proof | Contains aspirational tools/frameworks and broad claims; not an authoritative installed-feature list |
| Existing `docs/archive/` | Keep historical | Superseded Postgres/ArchiveBox/object-store designs need not be marked implemented |
| Ten root backfill reports | Archive as historical run evidence | Generated 2026-04-11; zero-result/error runs and live-RSS historical limitations are explicitly recorded |

The ten report filenames are `backfill_{middle-east,trump-news}_{RANGE}.md`, for each of:

- `2026-03-11_to_2026-03-16`
- `2026-03-17_to_2026-03-22`
- `2026-03-23_to_2026-03-28`
- `2026-03-29_to_2026-04-03`
- `2026-04-04_to_2026-04-10`

Proposed destination: `docs/archive/root-reports/20260411-backfill-<topic>-<range>.md`, preserving contents and adding an archive inventory/limitation note. Several date-labelled runs contain later publication URLs; archive them without certifying historical completeness.

Tracked Markdown relative-file-link checks found no missing targets; anchors and external-link health were not comprehensively checked. Some archived prose names missing old demo scripts; preserve history and annotate replacements only when equivalence is verified.

## 4. Proposed approval-gated sequence

1. **Preserve and establish ownership:** inventory/hash existing scratch files, take a consistent database/data backup, identify canonical ingestion and external launchers. Do not replay helpers.
2. **Conservative housekeeping:** move the ten historical reports with an archive index; remove only known bytecode/test caches; add a designated ignored scratch directory for future temporary work. Do not hide arbitrary root files through broad ignore patterns.
3. **Small frontend pruning/setup commit:** remove the ten confirmed unused frontend files and agreed unused packages; repair matching test dependencies/lockfile; document Node/npm; require a genuinely clean install and checks/tests. Keep dependency upgrades reviewable rather than mixing them with a feature rewrite.
4. **Correctness patches:** fail on event-store failures, fix empty/failure UI states, remove synthetic operational claims, and add focused regressions. Repair the styling contract without redesigning the app.
5. **Separate data-reconciliation project:** reconcile the two article tables on a backup, preserve provenance, validate content/row parity, restore real cases/intake where appropriate, then enable database enforcement. Retire old ingestion helpers only after the replacement is exercised and operational references are updated.
6. **Feature work:** follow the evidence-first roadmap. Decide explicitly whether the website remains read-only before planning web editing or execution.

Success criteria for cleanup: no loss of source/data/history; reversible moves; no unexplained scratch-file deletion; one documented authoritative ingestion path; clean install; backend/frontend tests and checks passing; honest empty/error states; and a tested backup/restore procedure. None of these repairs is claimed complete by this audit.
