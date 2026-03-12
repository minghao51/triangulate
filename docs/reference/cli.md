# CLI Reference

The CLI entrypoint is `triangulate`, defined in `src/cli/main.py`.

## Setup Commands

```bash
uv run triangulate init-db
uv run triangulate version
```

## Case-Oriented Commands

```bash
uv run triangulate fetch-topic "<query>"
uv run triangulate cases
uv run triangulate case show <case-id>
uv run triangulate case review <case-id>
uv run triangulate case rerun <case-id>
uv run triangulate run-pipeline
uv run triangulate monitor --start --topics ./topics.yaml --interval 30
uv run triangulate interactive
```

## Legacy Event Commands

```bash
uv run triangulate ingest
uv run triangulate process
uv run triangulate process-url <url>
uv run triangulate review
uv run triangulate query --days 7
```

## Notes

- Case commands read and write case artifacts under the configured output root, which defaults to `./output`.
- `review` can target either the legacy event flow or a case via `--case-id`.
- `process-url` is useful for single-article inspection through the AI pipeline.

For setup and common workflows, use [`../getting-started/quickstart.md`](../getting-started/quickstart.md).
