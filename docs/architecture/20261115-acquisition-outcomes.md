# Acquisition outcomes and retrieval checkpoints

Date: 2026-11-15. Status: B02 implemented and independently accepted.

This supplements the [current architecture](20261114-current-architecture.md).
The [database incident and test safety boundary](../reference/20261115-test-database-incident.md)
remain separate from application correctness; no restoration or production repair
is implied by passing tests.

## Data flow and ownership

```text
RSSFeed.fetch_with_outcome()
  -> FeedAcquisitionOutcome
TopicFetcher._fetch_from_sources()
  -> SourceAcquisitionOutcome for each planned source
TopicFetcher.fetch_articles_by_topic()
  -> filtered articles + full source outcomes + requested-plan count
retrieval_acquisition_observation()
  -> canonical coverage/counts derived from source observations
TopicCaseService._persist_retrieved_articles()
  -> case metadata + retrieval artifact + checkpoint observation
_execute_stage()
  -> same-transaction COMPLETED or recorded FAILED stage/case
```

There is no new HTTP mutation endpoint or schema migration. CLI/service workflows
remain the writers. Source acquisition is not evidence verification, independent
publisher analysis, or a guarantee of exhaustive real-world coverage.

## Feed classification and compatibility

`src/ingester/rss.py` provides four outcome statuses:

| Status | Meaning |
| --- | --- |
| `success_with_items` | Usable parsed items, possibly with disclosed degradation |
| `success_empty` | Recognized RSS/Atom/RDF feed with no entries and no parser warning |
| `failed` | Transport/parser/HTTP failure, unrecognized empty response, or no usable parsed entries |
| `skipped` | No fresh acquisition, such as HTTP 304 |

An empty body, well-formed HTML or an XML maintenance message is not a healthy
empty feed merely because the parser has no warning. Recognized feed-version
evidence is required. Recovered bozo feeds and mixed valid/invalid entry sets
retain usable items but report degradation. Deliberately selecting only the
first `max_articles` entries is not itself a parse failure.

Feed outcomes carry HTTP/version and entry-selection/parse diagnostics. Topic
source outcomes retain source identity, strategy, attempted flag, status,
article count, error/warning/reason, degradation and parse-failure count. Article
counts describe acquisition before relevance filtering, not confirmed claims.

`RSSFeed.fetch()` and `ContentFetcher` keep their list-returning interfaces.
The RSS wrapper returns an empty list for failure/skips, including classification
errors. RSS `Source.last_fetched` advances only on a genuine acquisition success;
NewsAPI behavior is unchanged. This ticket does not introduce a feed transport
deadline, cancellation, retry system or scheduling guarantees. Full-article
extraction and its existing timeout/fallback behavior remain a separate concern.

## Canonical source coverage

`src/ingester/topic_fetcher.py` validates outcomes before counting successes:
source identity, attempted state, known status and consistent article count are
required. Duplicate identities, missing requested records, invalid records,
skips and degradation prevent complete coverage. Caller-supplied `succeeded`,
coverage and aggregate-count fields cannot certify success.

Counts distinguish requested versus observed source records, unaccounted
requests, attempts, successful item/empty acquisitions, failures, skips,
invalid/duplicate records and degradation/warnings. An explicit trustworthy
attempt flag remains counted even when the rest of its record is invalid.

Coverage values:

- `complete_requested_scope`: every requested source is uniquely and cleanly
  accounted for by a genuine acquisition, including healthy empty feeds.
- `partial`: some success, but also missing, invalid, duplicated, skipped,
  failed or degraded acquisition.
- `failed`: no successes and explicit source failures.
- `not_attempted`: no acquisition attempt, including seed-only context.
- `unknown`: incomplete/untrustworthy observation or legacy unobserved output.

The displayed source plan may stop at 20 entries. Full source outcomes and the
requested count are retained, so that display limit cannot silently turn missing
coverage into completion. `sources_used` is derived from validated acquisitions,
not the old prioritized top-10 list; it is not an independence/support score.

Manual/social plan entries remain sparse context without claiming a network
fetch. A seed can make a no-acquisition result reviewable only when a positive,
unattempted skipped outcome has a matching actual manual/social article by URL
and kind, with nonempty context. A fabricated RSS skip or an unmatched seed
outcome is insufficient. If relevance filtering removes all seed context, the
no-acquisition result is conservatively fatal.

## Persistence and stage outcomes

`src/cases/service.py` recomputes canonical acquisition observations. Coverage
and counts normalize the result before retrieval-artifact and stage-metric
persistence as well as case/checkpoint metadata. Caller summary claims, when
present, remain explicitly untrusted under `reported_acquisition_summary`;
contradictory reported source lists are kept separately.

`MonitorCheckpoint.last_checked_at` records the observation. Only canonical
`complete_requested_scope` advances `last_successful_run_at`; partial, failed,
unattempted and unknown observations retain the prior value. This timestamp
means successful **retrieval**, not successful completion of later investigation
or reporting. The pipeline still uses stage-owned transactions, not one atomic
whole-case transaction.

All-source failure and observed no-acquisition/no-usable-seed results set
`CaseRunContext.stage_failure`. `_execute_stage` commits their articles/context,
artifact, diagnostics and checkpoint observation together with FAILED stage and
case status, then the case loop stops before later stages. It does not first
publish a COMPLETED stage and repair it afterward. The failure marker is reset
per stage. Partial acquisitions preserve their data; seed-only context remains
explicitly unattempted. Legacy results without trustworthy outcomes remain
unknown/unobserved for compatibility, never a successful checkpoint.

## Verification boundary

Tests use mocked sources, in-memory feed bytes and temporary SQLite databases.
Application database calls during pytest fixture execution receive a temporary
default and reject checkout-local paths; raw connections, import-time I/O and
subprocesses are not sandboxed by that fixture. Backend gates run from a
disposable project copy, with live providers disabled. Final parent verification: **60 focused tests; 203 passed, 9 deselected overall;
Ruff and diff checks passed**. Independent re-review found no remaining blocker
in the reviewed corrections. Logs:
`/tmp/triangulate-b02-parent-final-{focused,full,ruff}.log`.

Active LSP is not globally clean: classic ORM descriptor/optional-row inference
and optional-import findings remain. The pre-existing trafilatura
`fetch_url(..., timeout=...)` signature mismatch is tracked separately as task
#16; no extraction/transport repair is claimed here. Acceptance and residual
gates are recorded in the
[worker plan](../plans/20261114-evidence-workbench-worker-plan.md).
