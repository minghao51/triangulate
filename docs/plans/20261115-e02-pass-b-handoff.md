# E02 pass B: new-thread handoff

Date: 2026-11-15. Status: **E02 passes A, B1, B2 and B3 are implemented and
independently verified; every row of the E02 acceptance matrix below is met, so E02
is complete pending owner acceptance.** This document is self-contained so a fresh
agent thread can continue without the previous conversation. It is a handoff, not a new contract: the
authority remains [the specification](20261114-evidence-workbench-specification.md)
§4 and the [E02 ticket card](20261114-evidence-workbench-worker-plan.md#e02--add-validated-quotations-and-correct-relationship-counts).

## 1. Where things stand

Accepted, independently verified releases (all changes uncommitted):

| Ticket | Scope | Verified baseline |
|---|---|---|
| B00–B03 | toolchain, atomic writes/reviews, honest acquisition, truthful UI | frontend: `npm run check`, 72 component tests, 10 mocked Chrome tests |
| E01 | immutable evidence captures, migration 8 | 229 passed / 9 deselected, Ruff clean |
| E02 pass A | exact-span validator, relationship policy, `ClaimCitation`, migration 9 | 96 focused; 295 passed / 9 deselected; Ruff clean |
| E02 pass B1 | optional collector quote proposals, real analysis scope, honest extraction outcomes | 116 focused; 321 passed / 9 deselected; Ruff clean |
| E02 pass B2 | replacement guard, authoritative-outcome plumbing, identity-based party merge | 189 focused; 333 passed / 9 deselected; Ruff clean |
| E02 pass B3 | per-claim writer wiring + citations, effective relationships, aggregate eligibility, review hash | 206 focused; 350 passed / 9 deselected; Ruff clean |

**Important:** nothing in production has been migrated, and no captured evidence
carries a real quotation yet: no case has been re-run since B3, so existing rows
keep their legacy `supports` relation and no `ClaimCitation` rows exist. New runs
now write validated citations and policy-derived relationships; a production case
rerun is a separate, owner-authorized operation.

## 2. Non-negotiable safety rules

- Application Python/tests run **only** in the disposable copy recorded in
  `/tmp/triangulate-safety-verification-dir`
  (currently `/tmp/triangulate-safety-verification.ZJuj46`).
- Copy **only** `src/` and `tests/` into it, excluding `__pycache__`/`*.pyc`.
  **Never** copy `data/`, `triangulate.db`, `.env`, or `logs/`.
- Always `uv run`. Use `env LLM_API_KEY= OPENAI_API_KEY= LANGSMITH_TRACING=false`.
- Do **not** run ingestion, cleanup scripts, migrations against the repository's
  `triangulate.db`, or any server. No API/dev server, no browser backend.
- Do **not** weaken `tests/conftest.py` (its per-test temporary DB + checkout-DB
  guard is a deliberate isolation control, and is not a sandbox against raw SQL,
  import-time I/O or subprocesses).
- No commits, resets, branch operations, dependency changes, deletions of
  untracked/user files, or production repair.
- Preserve all uncommitted work and the **382 original non-document untracked
  paths** (baseline: `/tmp/triangulate-b00-parent-baseline.json`).
- The **B02 database incident** stays disclosed: a test once wrote to the
  production DB and a row was deleted without approval. The original file hash
  changed; byte-identical or complete logical restoration is **not** claimed and
  repair is **not** authorized. See
  [`../reference/20261115-test-database-incident.md`](../reference/20261115-test-database-incident.md).
  Post-incident hash/size/mtime must remain unchanged; the recorded observation is
  in `/tmp/triangulate-db-incident-pvhgt70t/observation.json`.
- Website/FastAPI stay read-only. No new mutation endpoints.

## 3. What pass A delivered (do not redo)

New/changed code:

- `src/storage/models.py` — `AlignmentStatus`; `ClaimEvidenceLink` gained nullable
  `capture_id`, `citation_id`, `quote`, `start_char`, `end_char`,
  `alignment_status` (default `not_provided`), `assessment_origin`,
  `assessment_version`, `assessment_metadata`; new append-only `ClaimCitation`
  (`original_claim_id` is a **plain value, not an FK**) with ORM update/delete
  guards.
- `src/storage/citations.py` — the seam:
  - `AnalysisScope(start_char, end_char, body_sha256=None)` — scope is the
    **actually supplied body region**; `body_sha256` is the **full normalized
    capture body hash** (not a prefix hash) and is not proof the whole body was read.
  - `QuoteProposal(quote=None, start_char=None, end_char=None)`.
  - `validate_quote_alignment(capture_text, proposal, scope)` → `QuoteAlignment`
    with statuses `exact | ambiguous | no_match | not_provided | source_unavailable`.
    Missing/unknown scope **fails closed**. No trim/casefold/NFKC/fuzzy/ellipsis.
    Zero-based Unicode code points, end-exclusive, Python slicing is the reference.
  - `resolve_effective_relationship(...)` → policy `relationship-policy-v1`:
    trusted collector (`collector_generated is True`) is **priority** and yields
    only `reported_by` (anchored exact) or `uncertain`; explicit assessment needs
    origin ∈ {`model`,`human`,`service`} + a non-empty non-sentinel **opaque**
    version + exact anchor/status agreement; `opposes`→`contradicts` only when
    assessed; confidence is not a parameter; `citation_eligible` gates citation
    creation.
  - `link_contribution(resolution)` → `support`/`opposition`/`None`.
  - `record_claim_citation(session, ...)` → `CitationRecordResult`; caller-owned
    session (reads inside `no_autoflush`, only `flush([citation])`), ownership
    checked against case/capture/evidence rows, deterministic UUID5 identity over
    an explicit allowlist, first metadata/historical ID frozen on reuse.
- `src/storage/migrations.py` — migration **9**, additive/idempotent, parent table
  first, inline FKs on the upgraded link table, no backfill/rewrite/review reset.
  `src/storage/__init__.py` and `src/cases/evidence.py` re-export the seam.
- `tests/fixtures/evidence_workbench.py` — shared synthetic A–E sources (+
  `UNAVAILABLE`, `LEGACY_WORKBENCH_SOURCES`, `REVISED_BODY_A`). Data only.
- `tests/test_e02_quote_alignment.py` — 40 tests; `tests/test_migrations.py` and
  `tests/test_runtime.py` — schema 9 + migration 9 FK/backfill tests.

Verified logs: `/tmp/triangulate-e02a-parent-version-{focused,full,ruff}.log`.

Known static-analysis noise: 59 Pyright findings in the new **test** file are the
classic SQLAlchemy `Column[...]` descriptor-inference class (plus optional
narrowing), and one deliberate `TypeError` probe with a targeted
`# type: ignore[call-arg]`. B1's four changed files probe clean. The remaining
pre-existing findings (including `party_investigation_workflow.py`'s
`result.get` on the `list | dict` return of `collect_claims`) are unchanged from
the E01 baseline.

Static-analysis status: **resolved by the owner-approved ORM typing migration**
(2026-11-15, after E03). `src/storage/models.py` now declares every column as
`name: Mapped[T] = mapped_column(...)` instead of a bare `Column(...)`, so stored
attributes are typed as their runtime values everywhere. Verified invariants:
the compiled SQLite DDL for all 18 tables and every index is **byte-identical**
before/after (`/tmp/triangulate-models-ddl-{before,after}.txt`, `diff` clean — no
schema, nullability, default, FK, enum or index change), and the full suite passes
unchanged. That removed the classic `Column[...]` class at its source rather than
per call site; the previously added identity helpers (`stored()` in tests,
`_runtime()` in `mappers.py`) are now redundant but harmless.

Alongside it, the genuinely small typing gaps this exposed were fixed properly:
`Database.__init__`/`init_database` accept `str | None`, `_execute_stage`,
`_mark_stage_running` and `_pause_case_for_manual_action` guard a missing
stage-run/case row explicitly, `_process_case_article` annotates its
`baseline`/`outcome` locals, `EvidenceItem.capture_metadata` is assigned through a
narrowed local, `_link_semantics` uses `session.get()` instead of a query chain,
`party_investigation_workflow.py` narrows `gather(return_exceptions=True)` on
`BaseException` (a cancelled run could previously reach `.get()`), and
`process_url.py` narrows intake ids.

Current probe state: `src/cases/service.py`, `src/storage/event_store.py`,
`src/storage/models.py`, `src/storage/database.py`, `src/cases/readers.py`,
`src/http/{app,schemas,mappers}.py`, `src/ai/workflows/party_investigation_workflow.py`,
`src/cli/commands/process_url.py` and all E02/E03 test files report **0 Pyright
findings**. Exactly one auxiliary ast-grep heuristic remains:
`service.py`'s report-manifest `open(...)` "call without try/except" — deliberate,
because a report that cannot be written must fail its stage and be recorded by
the stage error handler, which is the existing contract. No suppression comments
were added anywhere; the ticket gates are pytest and Ruff, both clean.

## 4. Pass B scope (the remaining work)

Split into three bounded, sequential worker handoffs. One application-code writer
at a time. Parent inspects the actual diff after each and runs the gates itself.

### B1 — Honest extraction outcomes and analysis scope ✅ done

Files: `src/ai/schemas.py`, `src/ai/agents/collector.py`, `src/ai/workflow.py`,
tests. `src/ai/workflows/party_investigation_workflow.py` needed no change (its
collector node already stores the whole envelope; a test pins the propagation).

Delivered:

- `ClaimSchema.source_quote`/`source_quote_start`/`source_quote_end`, optional, so
  old payloads still validate. `ClaimCollectionSchema.claims` is now **required**:
  a payload with the key absent is a validation failure (existing fallback path),
  while an explicit `{"claims": []}` remains a truthfully valid empty collection.
- `ExtractionOutcomeSchema` (`status: valid|empty|fallback|unavailable`,
  `quote_proposals_trusted`, `scope_start`, `scope_end`, `body_char_count`,
  `input_limit`, `source_available`, `reason`). Statuses: `ok`+claims → `valid`;
  `ok`+explicit empty list → `empty`; provider fallback → `fallback`; no key or an
  exception → `unavailable`. `quote_proposals_trusted` is true **only** for
  `valid` **and** a non-empty body.
- `COLLECTOR_CONTENT_LIMIT = 5000` and the recorded scope is the code-point window
  of the LF-normalized body actually supplied to the model (title excluded).
  `_normalize_body` duplicates `normalize_capture_text` deliberately (no
  `src.storage` import in the AI layer) and a test pins them together.
- `_fallback_claims` emits no quote/offset proposals (they are cut from
  title+body, so any offset would be meaningless and a headline could otherwise
  validate a passage).
- `AIWorkflow.process_article` records the outcome at
  `llm_metadata["collector"]["extraction_outcome"]` **and** top level
  `event_data["extraction_outcome"]`, and no longer overloads `None`: a validated
  `empty` collection returns an honest zero-claim event (no invented
  `workflow_route`; the service owns routing), while `fallback`/`unavailable`
  zero-claim results still return `None`. The compat path (a mocked collector
  returning a raw list) derives a conservative untrusted outcome.

**Carry-over for B2:** a valid-empty event now reaches `_process_case_article`
instead of returning `None`, so a high-importance case would run the party
workflow (a second extraction attempt) on zero claims. B2 should short-circuit
routing for `extraction_outcome["status"] == "empty"` while still treating
`fallback`/`unavailable`/`None` as non-authoritative.

Original B1 brief (kept for audit):

Files: `src/ai/schemas.py`, `src/ai/agents/collector.py`, `src/ai/workflow.py`,
`src/ai/workflows/party_investigation_workflow.py` (collector node), tests.

- Add optional `source_quote`, `source_quote_start`, `source_quote_end` to
  `ClaimSchema`; old payloads must still validate.
- The collector currently sends `content[:5000]` and `_fallback_claims` invents
  coarse sentences from title+body. Record the **actual supplied scope** (offset
  window of the normalized body) and never let title/summary text validate a
  passage.
- Distinguish a genuinely validated empty collection from a defaulted/malformed
  absence. `ClaimCollectionSchema.claims` currently defaults to `[]`, and
  `call_structured_llm` dumps defaults, so "absent" and "valid empty" are
  indistinguishable — fix that without breaking existing mocked payloads.
- Distinguish a parseable empty collection from failed/unavailable extraction, and
  record outcome metadata instead of overloading `None`.
- Do **not** add a second model/verification call.

Suggested shape: a small explicit `ExtractionOutcome` describing
`status` (e.g. `valid | empty | fallback | unavailable`), the observed scope, and
`quote_proposals_trusted`. Keep existing envelope keys intact for compatibility.

### B2 — Fallback must not erase valid analysis ✅ done

Files: `src/cases/service.py` (`_process_case_article`, `_merge_party_results`),
`src/storage/event_store.py` (replacement guard), tests.

Delivered:

- `_process_case_article` decides the authoritative outcome *before* anything
destructive and puts it on the event payload in both branches. A `process_article()
-> None` result is recorded as an explicit non-authoritative
`status="fallback"`, `reason="no_claims_extracted"` (never left absent, which the
store reads as legacy full replacement). A validated `empty` extraction returns
early with `routing_reason="validated_empty_extraction"` and never invokes the
party workflow, so an empty result cannot trigger a second extraction attempt.
- `event_store._payload_may_replace_analysis`: authority derives **only** from
`extraction_outcome.status` — absent/non-dict → replace (legacy/CLI compatibility),
`valid`/`empty` → replace, anything else (including forged/unknown) → preserve. No
separate boolean flag is trusted. On a guarded rewrite `_persist_source_evidence_only`
still persists/reuses the source evidence and its immutable capture, while claims,
links, narratives, party investigations, event analysis fields and reviews are left
untouched; first-time inserts and `valid`/`empty` reruns behave exactly as before.
- `_merge_party_results` matches determinations to baseline claims by
`_claim_signature` (consuming each baseline claim at most once) instead of by list
position. A quotation/offset/citation follows only the assertion it was made
against; unmatched text keeps the **event-level source attachment** (and the
attachment-derived counts/identity recomputed by `_augment_claims_with_evidence`)
but no assertion-specific fields; ids/signatures are always recomputed from the
final stored text; determinations without usable text are skipped rather than
stored as empty assertions.

**Correction made during parent review:** the first worker result dropped
`evidence` entirely on unmatched text, which silently removed the
`ClaimEvidenceLink` for every rephrased party-merged claim. Source attachment is
event-level, not assertion-specific, so it is retained while quotations are not; a
parent probe confirmed the rephrased claim keeps its link and creates no quotation.

**Carry-over for B3:** unmatched merged claims still receive attachment-based
`support_count`/`source_diversity_count` from `_augment_claims_with_evidence`, and
`event_store` still creates links with the default `relation="supports"` — B3 owns
making both policy-derived. Merged claim ids are now derived from
`(event_id, final claim_signature)`, so the review hash must hash the signature rather
than raw/text ids.

Original B2 brief (kept for audit):

Files: `src/cases/service.py` (`_process_case_article`, `_merge_party_results`),
`src/storage/event_store.py` (replacement guard), tests.

- Determine the authoritative outcome **before** the destructive rewrite.
  `_write_event` currently deletes links/claims/narratives for an existing event
  unconditionally; a failed/fallback extraction must not delete valid prior claims.
- Explicit valid empty output is different from unknown/`None`.
- Case-bound zero-claim events must still retain source capture (E01 behaviour).
- `_merge_party_results` merges baseline claims **by position** while replacing
  text; it must not transfer a quotation onto a different assertion. Match on real
  claim identity/text, else drop the proposal; recompute IDs/signatures from the
  final text with the existing `_claim_signature` rule
  (`sha256(text.lower().strip())`).
- Preserve `article_data["content"]=""` compatibility for AI input without turning
  unavailable source text into an invented empty capture.

### B3 — Writer wiring, effective relationships, aggregates, review hash ✅ done

Files: `src/storage/event_store.py`, `src/cases/service.py`,
`src/storage/review_state.py`, tests.

Delivered:

- `event_store._link_semantics` resolves every claim/evidence attachment through
  `src.storage.citations`: it builds the scope from the recorded
  `extraction_outcome` (`scope_start`/`scope_end`, `body_sha256` = the immutable
  capture's `text_sha256`; missing/non-int bounds mean **no scope**, never the
  whole capture), the claim's own `QuoteProposal`, and any explicit assessment
  provenance. Ordering is capture (already flushed) → `record_claim_citation`
  (flushes the citation) → link pointer; the caller-owned session is never
  committed/rolled back. Citations are only attempted when a case, a real
  `current_capture_id` and an actual proposal/assessment exist, so legacy/CLI
  events gain none. Stored on the link: `capture_id`, `citation_id` (only when a
  citation exists), quote/range (only when `exact`), `alignment_status`,
  `assessment_origin`/`version`/`metadata` (alignment version, policy version, raw
  `stored_relation` diagnostic, diagnostic reason) and
  `relation` = the policy's effective relationship — never a raw `supports`
  default. `collector_generated` is true only for a claim attachment whose recorded
  outcome is `quote_proposals_trusted` and which carries no explicit assessment.
- `_build_event_evidence` no longer invents `relation="supports"` or
  `confidence_score=0.5`; `_augment_claims_with_evidence` no longer derives
  support/opposition from attachments (both stay 0; observed publisher diversity
  is kept).
- `_recompute_case_claim_aggregates` counts only `link_contribution` results from
  `resolve_effective_relationship` (collector `reported_by`, `uncertain`, invalid
  and unanchored links contribute nothing), deduplicated per claim group by
  `(evidence_id, effective_relationship)`, and never writes
  `verification_status`.
- `review_state`: `ANALYSIS_HASH_VERSION = "e02.v1"` with the B01 projection kept
  as `LEGACY_ANALYSIS_HASH_VERSION = "b01.v1"`. Links **with** citation semantics
  pin quote/range/alignment/assessment, the policy-derived effective relationship
  and the cited capture's `text_sha256` (IDs, times, row order excluded); bare
  attachments produce an entry identical to B01 so unchanged legacy data keeps an
  identical digest. `reconcile_review_with_analysis(..., legacy_analysis_hash=...)`
  keeps a decision whose stored hash equals the B01 digest of the rows now stored,
  rebinding it to `e02.v1` without touching notes or `previous_decision_json`, and
  otherwise keeps B01 behaviour (pending adopts, decided invalidates, NULL hash
  stays conservative). Changed quotation/alignment/assessment invalidates.

Parent verification probes (safe-dir only, deleted afterwards): exact quote →
`exact`/`reported_by` + citation, support 0 after recompute; fabricated quote →
diagnostic only, no citation, support 0; explicit `model`/`v2` assessment with an
anchored quote → `supports` counted once across two duplicate events and
`verification_status` untouched; B01-hash approval over unchanged rows preserved
and rebound, then invalidated (`analysis_changed`) once the claim gained a
validated quotation.

**Residual risks:** pre-B3 rows carried invented `relation="supports"` and
`confidence_score=0.5`, so their first rewrite changes stored semantics and can
legitimately invalidate a pre-E02 approval; `source_diversity_count` remains an
observed publisher count (not an independence claim); no production case has been
re-run, so no real citation exists yet.

Original B3 brief (kept for audit):

Files: `src/storage/event_store.py`, `src/cases/service.py`
(`_build_event_evidence`, `_augment_claims_with_evidence`,
`_recompute_case_claim_aggregates`), `src/storage/review_state.py`, tests.

- `event_store` link creation currently defaults `relation="supports"`. Persist
  `capture_id`, `citation_id`, quote/range, `alignment_status`, assessment fields;
  resolve relationships through `citations.py` only.
- Call `record_claim_citation(...)` per claim/evidence attachment with the claim's
  own proposal and the recorded scope; keep caller-owned transaction semantics
  (no inner commit/rollback), capture flushed before citation, citation before the
  link pointer.
- `_build_event_evidence` currently invents support/confidence and
  `_augment_claims_with_evidence` initialises attachment-based support counts —
  both must become policy-derived, not attachment-based.
- `_recompute_case_claim_aggregates` currently counts every non-`opposes` link as
  support: count **only** eligible explicit anchored assessments, deduplicated per
  `(claim_signature, evidence_id, effective_relation)`; never promote
  `verification_status` from counts or alignment.
- `review_state._evidence_entry` hashes mutable `content` and raw `relation`; add
  pinned capture/quote/scope/assessment semantics so a meaningful passage or
  alignment change invalidates a review while IDs/times/order do not. Preserve B01
  behaviour: an algorithm-version bump alone must not invalidate unchanged legacy
  approvals.
- `src/http/mappers.py` / `schemas.py` field additions are **E03**, not here;
  this pass must nevertheless keep old payload keys working.

## 5. Acceptance matrix (from the E02 card)

| Requirement | Pass |
|---|---|
| valid/invalid/ambiguous/missing/out-of-scope quotation; emoji/CJK; CRLF; diagnostics | A ✅ |
| `opposes` alias; every relation's count semantics (policy level) | A ✅ |
| identical reruns reuse; changed version/quote/capture create another; frozen first metadata | A ✅ |
| rewritten/deleted live claims/links leave the citation resolvable | A ✅ |
| schema 9 fresh/legacy/repeat, no backfill, raw legacy relation preserved | A ✅ |
| collector proposals + real analysis scope | B1 ✅ |
| fallback and failed extraction cannot erase valid claims | B2 ✅ |
| per-claim writer wiring, effective relationships on stored links | B3 ✅ |
| aggregate eligibility/dedup, no false support | B3 ✅ |
| changed-analysis review hash incl. quotation/alignment; unchanged rerun preserved | B3 ✅ |
| full backend suite after focused tests | B1–B3 |

## 6. Verification commands

```bash
SAFE_DIR=$(head -1 /tmp/triangulate-safety-verification-dir)
tar --exclude='__pycache__' --exclude='*.pyc' -cf - src tests | tar -C "$SAFE_DIR" -xf -
cd "$SAFE_DIR"
env LLM_API_KEY= OPENAI_API_KEY= LANGSMITH_TRACING=false uv run pytest <focused paths> -q
env LLM_API_KEY= OPENAI_API_KEY= LANGSMITH_TRACING=false uv run pytest -q --disable-warnings
uv run ruff check src tests --output-format concise
```

Current expected baseline before the next ticket (E03): **350 passed, 9
deselected**; Ruff clean.
Any reduction in that count, or a weakened assertion, is a regression to
investigate — not a new baseline.

## 7. Available artifacts

- Worker (pass A, resumable but this thread is preferred to stay clean):
  `cd531c15-aa9b-4a7`; reviewer: `0df157a6-ecd3-40c`.
- Parent logs: `/tmp/triangulate-e02a-parent-version-{focused,full,ruff}.log`,
  B1 logs `/tmp/triangulate-e02b1-parent-{focused,full,ruff}.log` (worker
  `e230e31b-32c8-484`), B2 logs `/tmp/triangulate-e02b2-parent-{focused,full,ruff}.log`
  (worker `81ba8af4-9e71-4d3`), B3 logs
  `/tmp/triangulate-e02b3-parent-{focused,full,ruff}.log` (worker `a5d4a04a-f0da-4a5`),
  with status/md5 snapshots `…-parent-{status-before,status-after,predispatch-md5}.txt`.
  B3 changed exactly `src/storage/event_store.py`, `src/cases/service.py`,
  `src/storage/review_state.py` and the new `tests/test_e02b3_writer_wiring.py`,
  adjusting two existing assertions (`tests/test_e02b2_fallback_protection.py`
  attachment support `1 → 0`; `tests/test_review_command.py` hash prefix read from
  `ANALYSIS_HASH_VERSION`).
  earlier checkpoints `/tmp/triangulate-e02a-parent-{baseline,final}-*.log`.
- Production incident evidence: `/tmp/triangulate-db-incident-pvhgt70t/`
  (snapshot + manifest), `/tmp/triangulate-b00-parent-baseline.json`.

## 8. Explicitly out of scope / separately gated

- E03 inspector read API (GETs), E04 browser inspector/deep links — do not start
  them before E02 is accepted.
- P01 source dependency grouping; no copy-detection algorithm in E02.
- Historical production DB reconciliation/repair (`triangulate.db`),
  cleanup/archival of old reports or caches, dependency advisory remediation,
  broad ORM typing migration, deployment.
- Inherited known defect (task #16): `trafilatura.fetch_url(..., timeout=...)`
  API mismatch in `_fetch_full_article`, present in `git HEAD`, outside E02.
