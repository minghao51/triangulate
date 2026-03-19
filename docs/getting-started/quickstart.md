# Quickstart

This guide covers the current local workflow for the Python CLI, SQLite database, and case-oriented investigation flow.

## Prerequisites

- Python 3.11+
- `uv`
- An LLM API key compatible with the configured LiteLLM provider

## Setup

Clone the repo and install dependencies:

```bash
git clone https://github.com/minghao51/triangulate.git
cd triangulate
uv sync --all-extras
```

Configure environment variables:

```bash
cp .env.example .env
```

Set at least:

```bash
LLM_API_KEY=your_api_key
LLM_MODEL=qwen-plus
```

Initialize or upgrade the local database:

```bash
uv run triangulate init-db
```

## Create a Topic Case

Run the main case bootstrap flow:

```bash
uv run triangulate fetch-topic "Gaza ceasefire negotiations"
```

Useful options:

```bash
uv run triangulate fetch-topic "Gaza ceasefire negotiations" \
  --conflict gaza_war \
  --party Hamas \
  --party Israel \
  --manual-link https://example.com/source-1 \
  --manual-link https://x.com/example/status/123 \
  --automation-mode safe
```

This writes case artifacts under `./output/cases/<topic-slug>/`.

Primary outputs:

- `topic_analysis.json`
- `topic_report.md`
- `manifest.json`

## Review Existing Cases

List known cases:

```bash
uv run triangulate cases
```

Show one case:

```bash
uv run triangulate case show <case-id>
```

Review one case:

```bash
uv run triangulate case review <case-id>
```

## Monitor Mode

Create a `topics.yaml` file:

```yaml
topics:
  - query: Gaza ceasefire negotiations
    conflict: gaza_war
    confirmed_parties:
      - Hamas
      - Israel
    manual_links:
      - https://example.com/background-briefing
    max_articles: 20
    relevance_threshold: 0.4
    automation_mode: safe
```

Run one cycle:

```bash
uv run triangulate run-pipeline
```

Run the recurring monitor:

```bash
uv run triangulate monitor --start --topics ./topics.yaml --interval 30
```

## Run the Frontend

Start the FastAPI backend:

```bash
uv run triangulate serve
```

In a separate terminal, start the React frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:5173` and proxies `/api/*` requests to the backend at `http://localhost:8000`.

## Legacy Event Commands

The older event-oriented commands still exist:

```bash
uv run triangulate ingest
uv run triangulate process
uv run triangulate review
uv run triangulate query --days 7
```

Use them only if you need the earlier event pipeline. The current default workflow is case-oriented.

## Troubleshooting

- If the LLM provider is unavailable, several stages fall back and record the fallback in stage diagnostics.
- Generated runtime files live under `output/`, `logs/`, and the configured local database path.
- Manual and social links are stored as evidence seeds and often require human review.
- Re-running monitor cycles should reuse equivalent articles and evidence where possible.

For more detail on case bootstrap behavior, see [`../features/topic-based-retrieval.md`](../features/topic-based-retrieval.md).
