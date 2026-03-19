# CLI Reference

The CLI entrypoint is `triangulate`, defined in `src/cli/main.py`.
This is the canonical operator trigger surface for ingestion, execution, reruns, reviews, and exception handling.
GitHub Actions or other worker runtimes may also trigger Triangulate, but they should do so by invoking the same CLI commands rather than the website.

## Setup Commands

```bash
uv run triangulate init-db
uv run triangulate version
```

## Server Commands

```bash
uv run triangulate serve                    # Start FastAPI server on 127.0.0.1:8000
uv run triangulate serve --host 0.0.0.0 --port 8000 --reload
```

## Case-Oriented Commands

```bash
uv run triangulate fetch-topic "<query>"
uv run triangulate cases
uv run triangulate case show <case-id>
uv run triangulate case review <case-id>
uv run triangulate case rerun <case-id>
uv run triangulate case exception <case-id> <exception-id> --action resolve
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
- The website is presentation-only and does not trigger these workflows.
- GitHub Actions is an allowed trigger surface when it runs the CLI or shared service-layer workflows.
- `review` can target either the legacy event flow or a case via `--case-id`.
- `process-url` is useful for single-article inspection through the AI pipeline and can persist to the intake queue with `--save`.

For setup and common workflows, use [`../getting-started/quickstart.md`](../getting-started/quickstart.md).
For the operator workflow in Markdown form, use [`./cli-operations.md`](./cli-operations.md).
