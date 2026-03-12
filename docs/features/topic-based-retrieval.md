# Topic-Based Retrieval

The `fetch-topic` workflow is the current case bootstrap entrypoint for Triangulate.

## What It Does

Given a topic query, the workflow:

- detects or accepts a conflict domain
- generates and prioritizes search/retrieval queries
- fetches candidate articles
- scores article relevance
- runs downstream investigation stages
- writes a case bundle to `output/cases/<topic-slug>/`

## Main Command

```bash
uv run triangulate fetch-topic "Gaza ceasefire negotiations"
```

Common options:

```bash
uv run triangulate fetch-topic "Gaza ceasefire negotiations" \
  --output ./output \
  --max-articles 50 \
  --relevance-threshold 0.4 \
  --conflict gaza_war \
  --party Hamas \
  --party Israel \
  --manual-link https://example.com/context \
  --automation-mode safe
```

## Outputs

Each case bundle can include:

- `topic_analysis.json`: structured analysis output
- `topic_report.md`: operator-facing report
- `manifest.json`: bundle metadata and paths

The persisted case state also feeds the CLI case commands and the FastAPI endpoints.

## Monitor Usage

One-off configured cycle:

```bash
uv run triangulate run-pipeline
```

Recurring cycle:

```bash
uv run triangulate monitor --start --topics ./topics.yaml --interval 30
```

## Operator Notes

- `--party` pre-confirms parties and reduces party-confirmation exceptions.
- `--manual-link` injects article, social, or manually supplied evidence seeds.
- `--automation-mode` controls how aggressively automation is allowed to proceed for the case.
- Repeated runs are intended to reuse equivalent material where possible instead of duplicating case rows.

## Related Docs

- Setup and local execution: [`../getting-started/quickstart.md`](../getting-started/quickstart.md)
- Full CLI command list: [`../reference/cli.md`](../reference/cli.md)
- Current architecture: [`../architecture/system-overview.md`](../architecture/system-overview.md)
