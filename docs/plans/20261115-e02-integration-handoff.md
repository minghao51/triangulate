# E02 integration preparation

Date: 2026-11-15. Planning notes, **not delivered behavior**. E02 foundation
code is unaccepted and integration must wait for its correction/tests/review.
The approved [specification](20261114-evidence-workbench-specification.md) remains
the contract; this is an internal split of the same ticket, not new scope.

## Inspected AI and case seams

- `src/ai/agents/collector.py:collect_claims` currently supplies title plus only
  `content[:5000]`. `_fallback_claims` combines title/body into coarse sentences;
  it provides no validated quotation. The no-key and error paths explicitly set
  `fallback_used=True` in metadata envelopes.
- `ClaimCollectionSchema` currently defaults missing `claims` to `[]`.
  `call_structured_llm` validates that schema then dumps defaults, so an absent
  collection and an explicit valid empty collection become indistinguishable.
  Integration must not treat a defaulted/malformed absence as authoritative zero.
- `AIWorkflow.process_article` currently returns `None` for every empty collection
  and otherwise retains only four collector metadata fields. Distinguish actual
  validated empty output from unknown/fallback, and carry the recorded input
  scope into the event. No additional model/verification call is needed.
- `_process_case_article` already shares canonical LF source text between analysis
  and captures, including a case-bound `None` fallback. Its AI-compatible empty
  string must not erase the distinction between unavailable and actual-empty
  source text. The fallback currently has no extraction-validity declaration.
- `_augment_claims_with_evidence` currently attaches the same source dictionaries
  to every claim and initializes attachment-based support counts. Integration
  needs claim-specific proposal/context copies and policy-derived counts.
- `_merge_party_results` currently copies baseline claims by **position** while
  replacing their text, retaining old IDs/signatures/evidence. This must not carry
  an unrelated quotation onto a rewritten/reordered assertion. Match an actual
  unambiguous claim identity/text; otherwise discard inherited quote proposals.
  Recompute final IDs/signatures from final text using the existing identity rule.
  Party collector/arbiter metadata is available in `party_state.llm_metadata`.
- `_stage_investigate` currently calls every zero-claim output a parse failure,
  while nonempty fallback output escapes that branch. Valid empty versus failed
  extraction must remain distinguishable in persisted diagnostics/artifacts.

## Integration invariants

1. Optional collector quote/offset fields must preserve old non-quote payloads.
   Scope means the **actual body prefix**, not title, summary or full-body coverage.
   The foundation `AnalysisScope.body_sha256` binds the full normalized capture
   body; it is not the SHA of just the supplied prefix. Keep these meanings clear.
2. Missing/no-key/fallback/invalid extraction is never validated analysis. Its
   proposals cannot produce validated citations or counted support. Check the
   authoritative outcome before destructive claim/link/narrative replacement;
   retain prior valid analysis and still persist legitimate new source captures.
   Explicit valid empty output is different from unknown `None` or schema defaults.
   Valid prefix analysis must state its limited coverage, not claim full reading.
3. Known failed/fallback party extraction/arbitration must not replace a valid
   baseline with fabricated determinations. Positional quote inheritance is unsafe
   even when all outputs happen to be syntactically valid.
4. Source relationships and claim verification provenance are separate. A trusted
   collector exact span is `reported_by`, never support or truth certification.
   Legacy provenance stays unknown. Do not infer human verification from a source
   assessment, review label or an existing verification enum.
5. Count eligible explicit anchored assessments only, deduplicated by logical
   source/claim signature/relation. A source may contain conflicting assessed
   passages; that is not two independent sources. Existing diversity fields are
   observed compatibility values, not assertions of independence. P01 is deferred.
6. Hash pinned capture/quote/assessment semantics, not the latest source pointer
   or generated citation/capture/stage IDs/times. Preserve B01 unchanged-review
   behavior through the hash transition; a version bump alone is not a new finding.
   A changed passage/alignment/meaningful assessment must invalidate appropriately.
7. Retain raw legacy relations diagnostically while presenting effective uncertain
   values. Do not fabricate historical citations or materialize during reads.
   E03 owns new citation/inspector endpoints; E04 owns browser inspector behavior.

## Foundation checkpoints (passes A, B1, B2, B3) — verified, E02 complete pending acceptance

Pass A, pass B1, pass B2 and pass B3 are complete and independently verified, so
every E02 acceptance-matrix row is met. **E02 as a whole is complete pending the
owner's acceptance**; no production case has been re-run, so no real citation
exists yet.

- Checkpoint 1 added the models/helper/migration 9 but no fixture/tests. Parent
  precheck was **24 passed, 6 failed** (schema 9 versus still-8 expectations), and
  it reproduced three unsafe policy paths: collector metadata granting support,
  unknown origin granting support, and a non-exact status plus `exact_anchor=True`
  granting support. Independent review confirmed those, plus lost first origin
  metadata and implicit caller-session autoflush.
- Checkpoint 2 corrected them and added the fixture/regression matrix. Parent gates:
  **87 focused, 286 passed / 9 deselected**, Ruff passed.
  Logs: `/tmp/triangulate-e02a-parent-final-{focused,full,ruff}.log`.
- Independent re-review then found a contract blocker: only the literal `v1` was an
  accepted assessment version, and the changed-version test exercised the collector
  default instead of an assessed change. Checkpoint 3 made assessment versions an
  opaque identifier (empty/whitespace and explicit unknown sentinels only are
  rejected, original case preserved), required a real boolean for the trusted
  collector flag, corrected the `AnalysisScope.body_sha256` documentation, and
  replaced two `type: ignore` lines with explicit fail-closed assertions.
- Final parent verification of checkpoint 3: **96 focused passed; 295 passed, 9
  deselected overall; Ruff passed**. Logs:
  `/tmp/triangulate-e02a-parent-version-{focused,full,ruff}.log`.
  Parent probes confirmed `v2` assessed support, unversioned/unknown sentinels,
  collector-origin priority, string-`"false"` context and status/flag mismatch all
  behave as the policy requires. Reviewer findings are resolved in code and tests;
  this thread's review did not re-run the suite itself.

Pass B1 (collector quote proposals, recorded analysis scope, honest extraction
outcomes) is delivered and independently verified separately: **116 focused
passed; 321 passed, 9 deselected overall; Ruff passed**. Logs:
`/tmp/triangulate-e02b1-parent-{focused,full,ruff}.log`.

Pass B3 (per-claim writer wiring and citations, effective relationships on stored
links, aggregate eligibility/dedup, pinned review hash with a non-invalidating
version transition) is delivered and independently verified: **206 focused passed;
350 passed, 9 deselected overall; Ruff passed**. Logs:
`/tmp/triangulate-e02b3-parent-{focused,full,ruff}.log`. Details for all passes live
in [the pass B handoff](20261115-e02-pass-b-handoff.md) §4.

Status: the storage/citation seam, collector proposals and recorded scope, the
fallback replacement guard, and now the writer/aggregate/review-hash wiring all
exist and are tested. New runs write validated `ClaimCitation`s and
policy-derived relationships (`reported_by`/`uncertain` for collector output;
`supports`/`contradicts` only from an explicit versioned assessment with an exact
anchor), support/opposition counts only eligible deduplicated contributions, and a
meaningful passage/alignment change invalidates a review while an unchanged rerun
and the algorithm-version transition preserve it. E03 (typed inspector read API)
and E04 (browser inspector) remain unstarted; `src/http/mappers.py` and
`schemas.py` are untouched, so existing payload keys keep working.

No production database, data recovery, cleanup, deployment or automatic verifier
is authorized by either pass. All application verification stays in the disposable
copy, with temporary synthetic databases and provider keys disabled.
