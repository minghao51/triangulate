# Immutable evidence captures

Date: 2026-11-15. Status: E01 implemented and independently accepted.

This supplements the [current architecture](20261114-current-architecture.md).
E02 quotation alignment, immutable claim citations, relationship eligibility and
fallback-analysis replacement policy are **not** delivered by E01.

## Records and identity

`EvidenceItem` remains the logical source record. Its nullable
`current_capture_id` selects an `EvidenceCapture`; `content` is a compatibility
projection of that selected capture's normalized text, not historical truth.

Capture rows hold:

- A stable ID and owning `evidence_id`, with unique `(evidence_id, text_sha256)`.
- Exact stored `text` and its UTF-8 SHA-256 after CRLF/CR → LF normalization only.
- A separate `normalized_text_sha256` and normalization version `v1`, computed
  using NFKC, casefold and whitespace collapse. This fingerprint is not quotation
  text or an offset reference. The future copy-detection minimum-length rule is
  not applied when computing a fingerprint.
- UTC recording time, nullable known observation time, and `live` or
  `legacy_snapshot` capture kind. Publication times never supply observation
  times. Explicit known observations require an aware datetime and normalize to
  UTC; naive observations are rejected. SQLite may return naive UTC datetimes,
  which readers must not reinterpret as local wall time.
- Deep-copied metadata for provided URLs, title, publisher, source/publication
  fields, extraction information and origin stage-attempt ID when available.
  A stage-attempt ID is not a future grouped invocation ID.

Same evidence/body reuses the existing ID and first metadata/times. Changed text
adds a version and moves the current pointer without editing earlier captures.
Reobservation does not overwrite a first observation. Capture creation is not a
claim verification or proof of a fresh fetch when observation time is unknown.

## Shared write boundary

`src/storage/captures.py` owns normalization, hashes, metadata freezing,
get-or-create capture writes, pointer/projection synchronization and explicit
legacy materialization. `src/cases/evidence.py` re-exports that service-facing
seam without creating the case-service/event-store import cycle.

These helpers use a caller-owned session: no inner commit, rollback or close.
A pending evidence parent is flushed before the capture; the capture is flushed
before assigning its current pointer. ORM instance updates and deletes of
captures are rejected. This is an application/ORM boundary, **not** a raw-SQL or
bulk-operation ACL: unsupported administrative scripts can bypass ORM guards.
No automatic cascade from claim/link deletion removes captures.

Missing incoming text (`None`) creates no version and preserves an existing
pointer/projection. Explicit `""` is an exact empty capture, not fabricated from
missing text; it still cannot support a nonempty quotation.

## Event and case integration

`src/storage/event_store.py` uses one `_upsert_evidence` path for top-level event
sources and claim attachments. Top-level sources persist even with zero claims;
links are only created for actual claims. Pending caches preserve shared-source
identity. Canonical fallback requires a known nonempty URL, so anonymous sources
are not merged merely because both URLs are null. Explicit cross-case evidence
IDs are rejected rather than silently reparented. New versions freeze supplied
publication/archive metadata while older captures keep their original values.

Writes explicitly flush event and party parents before dependent claims,
evidence before captures/checks, and claims/evidence before links. These flushes
remain inside the existing transaction: a later event failure rolls back the
investigation batch, including new captures and pointer changes. B01 cumulative
verification-check and review-preserving equivalent-write behavior remains.

`TopicCaseService._process_case_article` selects one optional source body from
raw payload or the stored case-article projection, normalizes it and supplies the
same body to analysis and evidence persistence. When neither body exists, only
the AI-compatible input uses an empty string; evidence remains unavailable.
The baseline-`None` case-bound fallback now goes through common source finalization
and retains its source even with no extracted claims. This does not redesign the
unassigned-intake or CLI preview/no-event early-return flows.

## Migration and explicit legacy operation

Migration **8** creates the capture table/indexes and nullable pointer, with no
content copying, historical observation invention or review reset. On legacy
SQLite tables, the new nullable column includes an inline
`REFERENCES evidence_captures(id)`; no table rebuild is needed. Fresh and legacy
paths both expose/enforce that FK when enforcement is enabled on a scratch
connection. This does not enable global FK enforcement or reconcile old data.

`materialize_legacy_capture(session, evidence_id)` is an explicit offline
service operation, not a GET/startup/backfill. If no version exists, it snapshots
existing content as `legacy_snapshot` with unknown observation time and an actual
recording time. Repetition reuses the existing body/hash version and first
metadata; it does not relabel an already existing capture. Normalized content
becomes the selected compatibility projection. Nothing is created for `None`.

No production migration or materialization has been performed. The earlier
[database incident](../reference/20261115-test-database-incident.md) remains
disclosed; original byte-identical restoration is not claimed.

## Verification

Parent verification in the disposable project copy:

- **30 focused tests passed**.
- **229 backend tests passed; 9 integration tests deselected**.
- Ruff and diff checks passed.
- New migration regressions inspect pointer FKs, reject invalid references and
  accept valid targets under FK enforcement for both fresh and legacy schemas,
  after repeated schema-only migration runs.
- Independent re-review found no remaining E01 blocker. Active checks confirmed
  the capture helper/service seam and migration test file clean; the overall
  project still has inherited ORM/static findings, not a universal clean verdict.
  Five migration SQL audit warnings were individually reviewed: their interpolated
  column/type names come from fixed internal dictionaries, not untrusted input.

Logs: `/tmp/triangulate-e01-parent-final-{focused,full,ruff}.log`.
Production DB hash/size/mtime match the post-incident observation, and all 382
original user paths remain present. This is scratch verification, not production
rollout approval.
