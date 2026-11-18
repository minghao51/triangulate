# Scratch-file cleanup (2026-11-18)

Status: completed with owner approval. This records the removal of the
pre-existing untracked scratch artifacts from the working tree. It is not a
product feature and no tracked application code depended on them.

## What was removed

382 untracked artifacts at the repository root, `_cron_tmp/` and `scripts/`:

- 293 root Python helpers (ad-hoc check/verify/ingest/backfill/cron/fix/process
  scripts with fixed dates or duplicated one-off logic).
- 10 backfill Markdown reports (`backfill_middle-east_*`,
  `backfill_trump-news_*`).
- `me_news_results.json`.
- 58 `_cron_tmp/` scripts, raw HTML/XML captures and intermediate JSON.
- 17 untracked `scripts/` one-offs (date-specific backfills, CNBC/Bloomberg
  fixes, step scripts, trump/mideast ingestion helpers).

## Safety checks

- The set matched the previously audited ~382 pre-existing untracked files.
- No tracked file referenced the filenames except the audit document itself;
  scratch scripts referenced one another, so they were archived together.
- No user crontab, systemd timer or `/etc/cron*` entry referenced the checkout.
- `data/`, `triangulate.db`, `.env`, `logs/`, `config.toml`,
  `bias_taxonomy.toml`, tracked scripts and the P01/P02 changes were untouched.

## Archive and restore

Everything was archived **before** removal:

```text
/tmp/triangulate-scratch-archive-20261118T005339Z.tar.gz
sha256 6a38b51c41a7542819f30d23bddc0a83ebb07f8b9eda943df69e554314bad4e5
entries 382 / 382 verified
restore: tar -xzf /tmp/triangulate-scratch-archive-20261118T005339Z.tar.gz -C /home/howt/work/triangulate
```

The archive lives outside the repository and is intentionally not committed.
If any one-off script is still needed, restore it explicitly and propose it as a
reviewed, tracked tool rather than leaving it untracked.
