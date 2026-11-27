# Product comparison and evidence-first enhancement roadmap

Date: 2026-11-14. Status: **proposal for discussion, not approved implementation**.

Based on the [maintenance audit](../reference/20261114-setup-and-maintenance-audit.md) and [inspected architecture](../architecture/20261114-current-architecture.md). Detailed proposed contracts now live in the [evidence workbench specification](20261114-evidence-workbench-specification.md), with a [DeepSeek v4.1 task handoff](20261114-evidence-workbench-worker-plan.md); both await implementation approval. Cleanup has been classified, but no files have been deleted or archived pending approval. The comparison is provided now to inform the next phase; it is not a claim that cleanup is complete.

## 1. Product position

Triangulate is best positioned as a **topic-oriented evidence investigation workbench**: turn a question into traceable claims, source material, party perspectives, a timeline, explicit uncertainty, and a reviewable report.

Its strongest potential distinction is not “more AI agents” or a general RSS reader. It is showing **what each source actually supports, what independent sources disagree about, what changed, and what a human decided**. The existing case/evidence/run models are useful foundations, but current source attachment and synthetic UI data do not yet deliver that promise reliably.

The website is intentionally read-only. It can become a strong evidence reader without adding a web execution backend. As implemented it already carries one narrow human-in-the-loop review surface: three POST routes for review decisions, exception actions and review annotations (2026-11-22 amendment to the [specification](20261114-evidence-workbench-specification.md)). Creation, reruns, ingestion or monitor editing in the browser require a separate decision to change that boundary.

## 2. Comparison method and limits

Compared four adjacent web products across news comparison, intelligence monitoring, content research and investigative workspaces. Official product/documentation pages were retrieved on 2026-11-14. These establish **advertised/documented features**, not independent accuracy, hands-on usability, pricing or performance. Paid/account-only behavior was not tested. An unlisted competitor feature should be treated as **not evaluated**, not proven absent.

Triangulate's column is grounded in source inspection, automated checks, local-data metadata and a limited mocked browser check—not marketing or old plans.

| Comparable app | Verified advertised/documented strengths | Triangulate today | Useful enhancement to borrow |
|---|---|---|---|
| **Ground News** | Story coverage comparison, source-level bias/factuality/ownership context, and a Blindspot feed with an explained methodology [1–2] | Claims/evidence/parties and a source-analysis screen exist, but publisher-name guesses and hardcoded baselines are not a valid rating system | Side-by-side coverage, transparent source metadata, coverage gaps and “unknown” categories; show methodology and provenance |
| **Feedly Market Intelligence** | Curated source monitoring, AI feeds, emerging-trend dashboards, cited article synthesis, fact extraction, newsletters and integrations [3] | Topic retrieval, relevance scoring, CLI monitor cycles, reports and run history exist; real scheduler/alert projections and article-level analytical traceability are incomplete | Saved topic/source profiles, measured freshness/failures, cited summaries and automated change digests |
| **Inoreader** | Monitoring feeds, global search, rules/filters, annotations, tags, article archive/edit history, translations, notifications, email digests, teams and API [4–5] | Basic case search/filter and evidence browsing exist; no equivalent comprehensive research inbox, source manager, archive-version UI or collaboration workflow | Full-text search, useful filters/tags, saved views, source history, annotations and lightweight distribution |
| **OCCRP Aleph** | Search across datasets, document uploads/OCR, person/company cross-reference, relationship diagrams, timelines and investigation workspaces with managed access [6–7] | Parties, evidence, timelines and a partial corroboration graph exist; arbitrary document ingestion/OCR, entity cross-dataset search and managed team workspaces are not established | Persistent entity/evidence navigation, meaningful graph relationships, later document import and role-aware review |

### Important methodological distinction

Ground News explicitly describes its ratings as **publication-level**, based on external rating organizations, and assessed in a U.S. political context. These are not per-article truth scores. Triangulate should not replace its current simplistic publisher-name heuristics with a different opaque “bias score”, nor apply U.S. left/right categories uncritically to international conflicts.

Feedly's inline citations offer a relevant UX pattern, but a citation alone is still not independent corroboration. Aleph's entity/document workflow is useful inspiration, not a reason to adopt its entire deployment stack or promise broad data access.

## 3. Current capability baseline

| Capability | Actual state | Implication |
|---|---|---|
| Topic bootstrap and article acquisition | Implemented in CLI/service; depends on local source catalogs/provider configuration | Supply reproducible setup/catalogs before onboarding improvements |
| Durable intake and stage history | Implemented, with concurrency and failure-propagation gaps | Repair before adding workers or more schedules |
| Case discovery and detail browsing | API-backed; client-side search/filter | Improve search, empty/error states and keyboard use |
| Evidence/claims/parties/timeline/report tabs | Implemented read surfaces | Improve evidentiary semantics and navigation, not duplicate screens |
| Markdown and manifest export | Implemented | Add provenance/review context and stable sharing/export formats incrementally |
| Claim-specific supporting passages | Not established; same captured article attached to all extracted claims | Highest-value analytical enhancement |
| Independent corroboration/contradiction | Existing link/count concepts; actual grounding and independence need work | Do not market current counts as verified triangulation |
| Corroboration network | Partial API-backed visualization with placeholder actions | Make relationships actionable before adding graph complexity |
| Narrative/source analytical screens | Partial/demo heuristics and hardcoded values | Replace with persisted results or clearly label/remove them |
| Monitoring and pipeline observation | Real run/case data mixed with invented alerts/logs/metrics | Make the UI truthful before expanding alerts |
| Browser creation, rerun, approval and exception resolution | Deliberately not exposed | Keep CLI guidance unless a new authenticated control plane is approved |
| Collaboration, annotations, assignments, RBAC | Not established end-to-end | Requires identity, persistence and audit policy first |
| Document OCR, multimedia verification, broad OSINT connectors | Future/proposed | Defer until source integrity and core workflows are dependable |

## 4. Prioritized enhancement backlog

Effort is relative (**S**: localized; **M**: several related modules; **L**: new subsystem/boundary). These are not delivery estimates. Ship small changes with focused regression tests rather than treating a priority as one large rewrite.

### P0 — Make the current product trustworthy and reproducible

| Enhancement | Why / minimal first increment | Effort | Acceptance evidence |
|---|---|---:|---|
| Data reconciliation and backup/restore | Preserve original SQLite/capture history; reconcile `CaseArticle` vs `case_articles` on a copy and import through a documented path | M–L | Restore rehearsal, dedup/provenance report, no unexplained content loss; valid parent relationships |
| Fail-closed persistence and accurate acquisition status | Check event-write results, retain feed failures, stop false-success checkpoints | S–M | Forced-write-failure, all-feeds-failed and partial-fetch tests |
| Honest dashboards | Remove invented alerts/logs/health values and disable inert controls with explanation | S | Empty case list yields no invented activity; every displayed metric has a real source or unavailable state |
| Clean install and dependency triage | Align test/coverage peers, repair lockfile, review reachable advisories and pin the supported toolchain | M | Fresh `uv sync`, fresh `npm ci`, backend/frontend gates; reviewed advisory disposition |
| Working error/styling/accessibility basics | React Query errors/retries, supported CSS rules, semantic controls and keyboard access | S–M | API-error/route-change tests, visible focus, operable case navigation and browser/visual checks |

**Do not skip this tier to build new AI features.** Current passing unit tests do not establish trustworthy claim grounding or healthy historical data.

### P1 — Build the differentiated evidence-reading experience

#### 1. Claim → passage → source inspector

Select a claim and show its exact supporting or contradicting quotation, position within captured content, original/canonical URL, publisher, publication and capture times, model/run provenance and reviewer determination. A link can be `reported_by`, `supports`, `contradicts` or `uncertain`; do not use support as the default for every extracted assertion.

Start with existing text captures and a small, human-labeled evaluation set. Require “no supporting passage found” behavior. This is more useful than adding another narrative dashboard or generic chatbot.

**Effort:** M. **Gate:** quotations are present in the saved source; an unrelated/hallucinated claim cannot appear independently corroborated merely because an article was captured.

#### 2. Side-by-side source comparison

Compare two reports on the same event/claim. Show shared assertions, differing assertions, attributed statements, missing coverage, dates and citations. Separate editorial framing from evidence for a factual proposition.

**Effort:** M. **Gate:** an analyst can follow each comparison back to its source passage; unavailable/unknown facts are explicit. This remains a read-only frontend feature.

#### 3. Source independence and provenance

Normalize publishers and canonical URLs; identify syndicated/reposted material so several copies do not count as independent confirmation. Store where source metadata came from, when it was reviewed, and whether an assertion is unknown. Prefer interpretable counts and source lineage over a single credibility score.

**Effort:** M. **Gate:** duplicated wire copy does not inflate independent-source count; source-level metadata never masquerades as claim-level verification.

#### 4. “What changed since the last run?”

Provide a persisted/read-only delta: new articles, added/removed/reclassified claims, changes in evidence/review status and new exceptions. Make each item link to the relevant claim/source/run. Begin with explicit refresh/polling; WebSockets are not required.

**Effort:** M. **Gate:** repeated identical ingestion produces an empty delta and no duplicate alert; every displayed change has before/after provenance.

#### 5. Useful evidence search and navigation

Full-text search over captured source text, titles and claims; filters for case, source, date, verification/review state and party; stable shareable URLs for a claim/evidence item; links between graph, timeline and evidence.

Start with SQLite full-text search if its supported build provides FTS5. A vector database is not a prerequisite for this use case.

**Effort:** M. **Gate:** known words/phrases reliably find the corresponding evidence, keyboard navigation works, and links survive reloads.

### P2 — Improve the operator loop without premature platform expansion

1. **Read-only source/monitor health:** actual last attempt, last success, failures, next schedule only when supplied by a real scheduler, source coverage and capture completeness. Keep configuration in CLI until the boundary changes. **M**.
2. **CLI-configured digests/webhooks:** notify on meaningful case deltas or unresolved failures; persist delivery/dedup status, retries and a minimum alert threshold. Do not email entire private source captures by default. **M**.
3. **Annotations and reviewer audit history:** persist actor, action, target, reason and timestamp; show human decisions separately from model output. CLI-authored notes/read-only browser first, or explicitly approve authenticated web editing. Existing review metadata is not an immutable multiuser audit log. **M–L**.
4. **Reproducible evidence bundles:** export captured text, checksums, source/capture metadata, run/model/prompt version information, citations and review decisions. Respect content rights, retention and access boundaries; do not promise legal chain of custody from a checksum alone. **M**.
5. **Saved source/topic profiles and catalog import:** one documented source schema, validation, safe defaults and a small public sample catalog. Avoid adding a hundred feeds before failures and provenance are observable. **S–M**.
6. **Small import adapter:** a documented JSON/CSV evidence import format before custom adapters for every OSINT product. Import through service/intake boundaries rather than direct SQL. **M**.

### P3 — Reassess only after the core loop is validated

- Authenticated multiuser web review, assignments and role-based case access.
- PDF/document upload, OCR and cross-case entity resolution.
- Multilingual retrieval/translation with original-text citations.
- Multimedia verification and external archive integrations.
- Large-scale semantic retrieval, extensive OSINT connectors and richer realtime collaboration.

Each should have a concrete user need, data/security policy and measurable success criterion. They are not necessary to fix today's reliability problems.

## 5. Recommended small delivery sequence

1. **Housekeeping and reproducible setup:** approve conservative archive/cache cleanup and frontend pruning, repair installation, add CI; preserve historical data/scripts.
2. **Reliability patches and data recovery:** separate small code fixes from the backup-based migration/reconciliation work. Demonstrate the restored/real case reader against representative data.
3. **Evidence inspector MVP:** source passages and explicit relationships, plus regression/evaluation fixtures.
4. **Comparison + independence:** side-by-side reading, normalized provenance and syndicated-source handling.
5. **Run diffs + search:** actionable changes, stable deep links and full-text retrieval.
6. **Choose the collaboration boundary:** keep read-only web with CLI operators, or design a narrow authenticated control plane. Do not let inert UI buttons make this decision accidentally.

Defer animations, another dashboard, a generic chat assistant, Postgres/vector infrastructure, microservices and broad connector expansion until evidence quality and the operator loop justify them. No major stack rewrite is required for the first increments.

## 6. Existing-plan handling

- Keep the frontend phase-5 plan **partial**, not archived as completed. Its lazy-route work exists, but accessibility, error boundaries and several UX/documentation tasks do not. Reprioritize it toward correctness/accessibility before animations.
- Keep `docs/project_roadmap.md` open until its items are reconciled with this proposal. If the owner adopts this roadmap, archive the older one as **superseded**, not as implemented.
- Treat `docs/landscape.md` as research context, not a verified capability matrix or authoritative competitor benchmark.
- Historical backfill reports can be archived as evidence of runs; their date ranges and completion claims must not be taken as proof of historical coverage.

## 7. Official sources

Retrieved 2026-11-14:

1. Ground News, Blindspot feed: <https://ground.news/blindspot>
2. Ground News, rating system/methodology: <https://ground.news/rating-system>
3. Feedly Market Intelligence product page: <https://feedly.com/market-intelligence>
4. Inoreader product overview: <https://www.inoreader.com/>
5. Inoreader feature index: <https://www.inoreader.com/features/>
6. OCCRP Aleph documentation overview: <https://docs.aleph.occrp.org/>
7. OCCRP Aleph user guide: <https://docs.aleph.occrp.org/users/>

No competitor login, paid trial, personal account, pricing assumption or destructive interaction was used. Vendor feature descriptions are not evidence that those vendors' AI outputs are reliably verified.
