# Documentation Index

The active documentation tree is organized by purpose instead of by date.

## Safety gate (2026-11-15)

- [Test database write incident and isolation controls](reference/20261115-test-database-incident.md): production byte hash changed during B02; owner authorized resuming isolated B02 review. No restoration is claimed and no database repair is authorized.

## Current Audit and Proposals (2026-11-14)

- [Setup and maintenance audit](reference/20261114-setup-and-maintenance-audit.md): verified findings, cleanup candidates, and approval gates
- [Architecture as inspected](architecture/20261114-current-architecture.md): runtime flow, persistence, frontend boundaries, and limitations
- [Delivered review invalidation and transaction ownership](architecture/20261115-review-invalidation.md): B01 implementation, migration 7 and hash semantics
- [Delivered acquisition outcomes and checkpoints](architecture/20261115-acquisition-outcomes.md): B02 source coverage, durable failures and successful-checkpoint rules
- [Delivered read-only UI states](architecture/20261115-read-only-ui-states.md): B03 operational truth, case-scoped readers, accessible controls and safe mocked browser verification
- [Delivered immutable evidence captures](architecture/20261115-immutable-evidence-captures.md): E01 source versions, normalization, transaction/FK ordering and explicit legacy materialization
- [Delivered inspector read models](architecture/20261115-inspector-read-models.md): E03 citation/claim/evidence GET readers, code-point text windows, ownership and 404/422 rules, additive DTOs
- [Delivered comparison read API](architecture/20261118-comparison-read-api.md): P02 two-capture alignment, historical no-substitution, dependency warnings and GET-only contract
- [Delivered comparison UI](architecture/20261118-comparison-ui.md): P03 Compare tab, URL-pinned selection, panels/alignment, error/mobile/keyboard states; Release B accepted
- [Delivered grouped investigation runs](architecture/20261118-investigation-runs.md): R01 invocation identity, status/coverage derivation, origin references and migration 12 (internal foundation)
- [Delivered case writer admission and fencing](architecture/20261118-case-writer-fencing.md): R02 owner-token admission, protected-path validation, CLI interrupt, migration 13 and residual risks
- [Delivered case snapshots and run reports](architecture/20261118-case-snapshots.md): R03 snapshot/delta composition, guarded run finalization, run-specific reports, run/snapshot/changes GETs and the R03b snapshot-aware claim/evidence/comparison readers
- [Delivered changes and grouped history UI](architecture/20261120-changes-ui.md): R04 case-scoped changes tab, truthful initial/pending/unavailable/unchanged states, coverage warnings, origin/observed provenance and snapshot-aware historical links
- [Delivered transactional case search index](architecture/20261120-search-index.md): S01 migration 15 FTS5 index, transactional sync with deterministic rowids, capability reasons and the `triangulate case rebuild-search CASE_ID` repair command
- [Delivered case search read API](architecture/20261120-search-api.md): S02 `GET /api/cases/{case_id}/search` — literal all-term semantics, type/publisher/status/date filters, deterministic paging, plain-text snippets, 404/422/503 contract and the recorded benchmark
- [Release C completion map](plans/20261120-release-c-completion-map.md): single brief for S01 (transactional FTS index), S02 (search API + UI) and V01 (Release C verification) — all three complete locally as of 2026-11-21; D01 and deployment are owner gates
- [E02 pass B handoff](plans/20261115-e02-pass-b-handoff.md): self-contained continuation brief for quotation integration, fallback protection, aggregates and review hashes
- [E04 handoff](plans/20261115-e04-handoff.md): self-contained brief for the evidence inspector and deep links (Release A gate) — what exists from E03, scope, acceptance, gates, safety rules
- [Product comparison and enhancement roadmap](plans/20261114-product-enhancement-roadmap.md): comparable web apps and proposed priorities; not approved implementation
- [Evidence workbench specification](plans/20261114-evidence-workbench-specification.md): proposed feature behavior, storage/API contracts, safety and acceptance criteria
- [DeepSeek v4.1 worker plan](plans/20261114-evidence-workbench-worker-plan.md): dependency-ordered implementation tickets and review gates; B00/B01/B02/B03/E01–E04/P01–P03/R01–R04 accepted; S01/S02/V01 delivered, reviewed and verified locally (§7 final entries), pending owner push

## Active Docs

- [`getting-started/`](getting-started/quickstart.md): setup, local environment, and first run
- [`architecture/`](architecture/system-overview.md): current system layout and runtime boundaries
- [`features/`](features/topic-based-retrieval.md): feature-specific behavior and operator notes
- [`technical_roadmap.md`](technical_roadmap.md): canonical technical roadmap from the current implementation forward
- [`reference/`](reference/cli.md): CLI and HTTP interface reference
  Key operator docs:
  [`reference/cli.md`](reference/cli.md),
  [`reference/cli-operations.md`](reference/cli-operations.md),
  [`reference/http-api.md`](reference/http-api.md)

## Historical Material

- [`archive/`](archive/README.md): dated reports, superseded designs, implementation notes, and archived plans retained for context

## Future Planning

- [`plans/`](plans/README.md): design proposals that are still forward-looking and not yet implemented

## Naming Rules

- Do not add dated files at repository root.
- Put dated or historical docs in `docs/archive/`.
- Put active operational docs in `docs/getting-started/`, `docs/architecture/`, `docs/features/`, or `docs/reference/`.
- Put future-looking proposals in `docs/plans/`.
- Update links when moving docs so `README.md` and active docs never point at archived filenames.
