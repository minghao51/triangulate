# Documentation Index

The active documentation tree is organized by purpose instead of by date.

## Active Docs

- [`getting-started/`](getting-started/quickstart.md): setup, local environment, and first run
- [`architecture/`](architecture/system-overview.md): current system layout and runtime boundaries
- [`features/`](features/topic-based-retrieval.md): feature-specific behavior and operator notes
- [`reference/`](reference/cli.md): CLI and HTTP interface reference

## Historical Material

- [`archive/`](archive/README.md): dated reports, superseded designs, and implementation notes retained for context

## Future Planning

- [`plans/`](plans/README.md): design proposals that are still forward-looking and not yet implemented

## Naming Rules

- Do not add dated files at repository root.
- Put dated or historical docs in `docs/archive/`.
- Put active operational docs in `docs/getting-started/`, `docs/architecture/`, `docs/features/`, or `docs/reference/`.
- Put future-looking proposals in `docs/plans/`.
- Update links when moving docs so `README.md` and active docs never point at archived filenames.
