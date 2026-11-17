# Review invalidation and event-write transaction ownership

Date: 2026-11-15. Status: implemented by ticket B01. Contract:
[evidence workbench specification](../plans/20261114-evidence-workbench-specification.md),
[B01 task card](../plans/20261114-evidence-workbench-worker-plan.md). Supersedes
the stale "event storage uses its own session" note in the
[current architecture](20261114-current-architecture.md) case-lifecycle section.

## Transaction ownership

`src/storage/event_store.py` exposes one public writer,
`store_event_in_db(..., session=None)`, backed by the private
`_write_event(session, ...)`:

- **Standalone (no `session`):** the writer opens, commits, rolls back and closes
  its own short-lived session and keeps the legacy `True`/`False` return
  contract. This path is used by legacy CLI/ingestion callers such as
  `_process_intake_item`.
- **Caller-owned (`session=` given):** the caller owns the transaction. The
  writer only flushes — never commits, rolls back or closes — and write errors
  propagate. The caller decides rollback.

`_write_event` flushes at the start (so writes from an earlier event in the same
batch are visible to its queries), flushes pending narrative deletes before
re-inserting rewritten narratives (unique `cluster_id`), and performs a final
flush so a `create_review=False` caller can immediately query the rows it wrote.
Pending evidence/link/verification-check rows are cached in-memory per event so
two claims sharing the same evidence payload cannot attempt duplicate
deterministic primary keys while autoflush is disabled.

The INVESTIGATE stage (`TopicCaseService._persist_investigation_outputs`) passes
its stage session to every event write and then writes the investigation
artifact, event count, claim aggregates and review counts in that same session.
One failed event write therefore rolls back the entire stage batch and
`_execute_stage` marks the stage and case `FAILED`; `run_case` stops before later
stages (`ARBITRATE`, `REPORT`). **This is stage-transactional, not whole-case
atomic:** artifacts committed by earlier successful stages remain valid, and no
claim is made that the whole multi-stage case committed atomically.

## Analysis hash

`src/storage/review_state.py` computes a versioned deterministic fingerprint,
`b01.v1:<sha256>`, of the persisted analysis for one event. Included:
determination fields (title, summary, verification status, location), claim text
/signature/status/fact-allegation type/representative party/narrative cluster
reference/reasoning/party positions/controversy, each claim's evidence semantics
(URLs, title, publisher, published at, content, type/source type, verification
status, credibility tier, `requires_human_review`, relation, confidence, notes),
persisted `EvidenceVerificationCheck` semantics (`check_type`, `result`, `method`,
`notes`, `verified_by`), the bounded stable capture-metadata subset described
below, narrative summaries and party-investigation payloads.

Excluded so equivalent reruns do not reset a human review:

- generated claim/evidence/link/party/investigation row identifiers, including
  generated verification-check IDs;
- ordering of claims, evidence, narratives and investigations; order of the three
  documented unordered nested claim-set fields (see below). Other nested list
  order is **not** ignored;
- run/stage IDs and generated/observed timestamps (`created_at`, check
  `verified_at`, capture `fetched_at`/`observed_at`);
- case-level derived aggregates (`support_count`, `oppose_count`,
  `source_diversity_count`); and
- volatile capture-metadata and session-scoring keys (`queries`,
  `confirmed_parties`, `relevance_score`, `source_plan_score`, timestamps).

### Bounded normalization

Equal semantics are enforced by a small deterministic projection rather than a
general canonicalization framework:

- Party names are resolved for the **union** of claim-representative and
  investigation party IDs, so an investigated party that is not a claim's
  representative still resolves to its canonical name instead of a generated
  row UUID.
- Any string exactly equal to a known generated claim/evidence/party ID inside
  nested payloads (for example `claims_supported[].claim_id`) is replaced with
  the stable claim signature/text, evidence URL or party canonical name.
- Generated identity **dictionary keys** are normalized the same way, so
  `party_positions` keyed by party row ID projects onto the canonical party name.
  Explicit collision policy: two keys that project onto the same canonical key
  with equal values merge; with different values `AnalysisCanonicalizationError`
  is raised instead of silently discarding a position.
- Nested lists are **ordered by default**; only `claims_supported`,
  `claims_contested` and `unique_claims` are documented unordered claim sets and
  sorted. Reordering an arbitrary reasoning/timeline sequence therefore changes
  the hash and invalidates a decision, while reordering one of those three claim
  sets does not.
- `capture_metadata` is projected onto a bounded semantic subset
  (`country`, `language`, `affiliation`, `party_affiliation`, `perspective`,
  `fetch_strategy`, `source_type`, `credibility_tier`, `name`, `publisher`,
  `publisher_key`, `domain`, `host`, `submitted_via`, `capture_status`,
  `content_status`, `capture_kind`, `extraction_method`, `is_fallback`).
  Generated observation times and session/plan scoring are excluded.
- Narrative cluster identity is normalized by stripping an event-ID prefix so a
  regenerated/event-scoped cluster identifier is not compared as substantive
  text.

This is a documented, versioned projection — not a claim of full ID or ordering
independence for arbitrary future payloads. A future analysis field that is
meaningful but not included here requires a new hash version.

### Verification-check retained history

Verification checks are **cumulative observations**, not an authoritative
full-replacement list. Their deterministic ID is derived from
`(evidence, check_type, result)`, so a rewrite that changes only `method`,
`notes` or `verified_by` targets the existing row: the writer performs a bounded
upsert of those supplied semantic fields before the final flush/hash computation.
An omitted key keeps its stored value; an explicit `null` clears it. A new
`check_type`/`result` pair adds another record as before, and other existing
checks are never blanket-deleted. This preserves independent/human verification
history while making supplied check metadata part of the analysis hash.

## Review reconciliation

`reconcile_review_with_analysis` runs inside the event write:

- identical stored/incoming hash → status, `reviewed_at` and human `notes` are
  untouched;
- no decision yet (`pending`/unset) → the current hash is adopted as the baseline;
- a decision (`approved`, `rejected`, `action_required`, `edited`) with a
  different hash → the review becomes `pending`, `reviewed_at` is cleared and
  `previous_decision_json` records the prior `status`, `reviewed_at`, `notes`,
  prior `analysis_hash`, a `reason` and `invalidated_at`/`new_analysis_hash`.
  Human `notes` are never overwritten and no fabricated reviewer rejection is
  recorded.

### Conservative legacy policy

Rows created before this migration have a `NULL` `analysis_hash`. Their baseline
is unknown, so the first rewrite cannot prove the analysis is unchanged:

- a legacy **pending** row adopts the new hash and stays pending;
- a legacy **decided** row is invalidated to `pending` with reason
  `analysis_hash_unavailable`, retaining the prior decision metadata above.

Explicit decisions bind the hash that was actually reviewed:
`TopicCaseService.review_case` and the legacy CLI `review` approve/reject paths
both call `bind_review_decision` (current `compute_event_analysis_hash`) before
commit, which also clears stale invalidation metadata.

## Schema

Migration version 7 adds two nullable columns to the existing `reviews` table:
`analysis_hash` (versioned fingerprint string) and `previous_decision_json`
(prior-decision metadata). The migration is additive and idempotent; it is tested
for a fresh database, a raw legacy version-6 database (old `reviews` table
without the columns) and repeated runs, preserving existing review status,
timestamp and notes and leaving new fields `NULL` where history is unknown.
Development and tests use temporary databases only; no production database
migration is performed or authorized by this ticket, and no immutable audit
subsystem is introduced.
