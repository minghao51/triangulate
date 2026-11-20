#!/usr/bin/env python
"""S02 case-search benchmark on a synthetic fixture in a temporary database.

Specification §8 asks for a documented synthetic fixture (10k evidence / 20k
claims) and a measured warm p95, without hardware-dependent timing assertions in
unit tests. This script is the harness behind those recorded numbers:

* it never opens the application's configured database (``get_database()`` /
  ``init_database()`` are deliberately not used), only a fresh
  ``tempfile.mkdtemp()`` SQLite file;
* the fixture is written with the real ORM models and the S01 capture helper,
  and the FTS index is built with the S01 synchronization helper
  ``sync_event_index`` — the same seam the application uses;
* the measured queries call the real read model, ``read_case_search``, which is
  what ``GET /api/cases/{case_id}/search`` calls.

Usage::

    uv run python scripts/benchmark_search.py
    uv run python scripts/benchmark_search.py --evidence 2000 --claims 4000 --queries 100
    uv run python scripts/benchmark_search.py --json /tmp/s02-search-bench.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # allow `python scripts/benchmark_search.py`
    sys.path.insert(0, str(REPO_ROOT))

from src.cases.search import read_case_search  # noqa: E402
from src.storage.captures import record_evidence_capture  # noqa: E402
from src.storage.database import Database  # noqa: E402
from src.storage.migrations import run_migrations  # noqa: E402
from src.storage.models import (  # noqa: E402
    CaseStatus,
    Claim,
    Event,
    EvidenceItem,
    TopicCase,
    VerificationStatus,
)
from src.storage.search import (  # noqa: E402
    indexed_counts,
    probe_search_capability,
    rebuild_case_search_index,
    sync_event_index,
)

CASE_COUNT = 4
EVENTS_PER_CASE = 10
PUBLISHERS = ["Meridian Wire", "Northern Post", "Harbour Gazette", "Delta Review"]
STATUSES = [
    VerificationStatus.ALLEGED,
    VerificationStatus.CONFIRMED,
    VerificationStatus.CONTESTED,
    VerificationStatus.PROBABLE,
]

#: Common terms the warm queries search for (all guaranteed present in bodies).
COMMON_TERMS = [
    "harbour",
    "levy",
    "council",
    "quartz",
    "convoy",
    "granite",
    "tribunal",
    "annex",
]
TWO_TERM_QUERIES = [
    "harbour levy",
    "council quartz",
    "convoy granite",
    "tribunal annex",
]

FILLER_WORDS = (
    "port alden officials briefing transit shelter morning report authority "
    "agency statement review reading committee session record archive notice "
    "harbour district northern delta meridian post gazette survey inspection"
).split()


@dataclass(frozen=True)
class QueryPattern:
    """One measured query shape (all justification is optional)."""

    label: str
    q: str
    result_type: str | None = None
    publisher: str | None = None
    status: str | None = None
    published_from: str | None = None
    published_to: str | None = None


@dataclass
class PatternStats:
    """Per-query-shape warm latency and hit count."""

    p50_ms: float
    p95_ms: float
    total: int


@dataclass
class Measurement:
    """Warm-latency result of the measured query batch."""

    queries: int
    p50_ms: float
    p95_ms: float
    max_ms: float
    per_pattern: dict[str, PatternStats] = field(default_factory=dict)


@dataclass
class Fixture:
    """Fixture facts returned by :func:`build_fixture`."""

    db_path: str
    case_ids: list[str]
    events: int
    evidence: int
    claims: int
    counts_after_sync: dict[str, dict[str, int]] = field(default_factory=dict)
    counts_after_rebuild: dict[str, dict[str, int]] = field(default_factory=dict)
    insert_seconds: float = 0.0
    sync_seconds: float = 0.0
    rebuild_seconds: float = 0.0
    db_bytes: int = 0


def _body(rng: random.Random, index: int) -> str:
    """Deterministic body text of roughly 60-90 words with recurring terms."""
    term = COMMON_TERMS[index % len(COMMON_TERMS)]
    second = COMMON_TERMS[(index * 7 + 3) % len(COMMON_TERMS)]
    sentences = [f"The {term} file records observation {index} for the {second} review."]
    for _ in range(3):
        words = [rng.choice(FILLER_WORDS) for _ in range(14)]
        sentences.append(" ".join(words).capitalize() + ".")
    return " ".join(sentences)


def build_fixture(
    db_path: str, evidence_count: int, claim_count: int, seed: int = 20261120
) -> Fixture:
    """Insert synthetic rows and build the FTS index; return fixture facts."""
    rng = random.Random(seed)
    database = Database(db_path)
    database.init_db()
    run_migrations(db_path)

    case_ids = [f"bench-case-{index}" for index in range(CASE_COUNT)]
    event_ids: list[str] = []
    evidence_by_event: dict[str, list[str]] = {case_id: [] for case_id in case_ids}
    claims_per_event: dict[str, int] = {}

    insert_start = time.perf_counter()
    session = database.get_session_sync()
    try:
        for case_index, case_id in enumerate(case_ids):
            session.add(
                TopicCase(
                    id=case_id,
                    query=f"benchmark case {case_index}",
                    slug=f"{case_id}-slug",
                    conflict="Synthetic benchmark",
                    status=CaseStatus.REVIEW_READY,
                    metadata_json={},
                )
            )
        session.flush()
        for case_index, case_id in enumerate(case_ids):
            for event_index in range(EVENTS_PER_CASE):
                event_id = f"bench-event-{case_index}-{event_index}"
                session.add(
                    Event(
                        id=event_id,
                        timestamp=datetime(2026, 3, 1, tzinfo=UTC)
                        + timedelta(hours=case_index * 24 + event_index),
                        title=f"Benchmark event {case_index}-{event_index}",
                        summary="Synthetic benchmark event",
                        verification_status=VerificationStatus.ALLEGED,
                        case_id=case_id,
                    )
                )
                event_ids.append(event_id)
                evidence_by_event[case_id].append(event_id)
        session.flush()

        per_event_evidence = math.ceil(evidence_count / len(event_ids))
        per_event_claims = math.ceil(claim_count / len(event_ids))
        written_evidence = 0
        for round_index in range(per_event_evidence):
            for event_id in event_ids:
                if written_evidence >= evidence_count:
                    continue
                case_id = event_id.split("-")[2]
                index = written_evidence
                evidence = EvidenceItem(
                    id=f"bench-evidence-{index:06d}",
                    case_id=f"bench-case-{case_id}",
                    event_id=event_id,
                    evidence_type="article",
                    source_type="rss",
                    title=f"Benchmark source {index} {COMMON_TERMS[index % len(COMMON_TERMS)]}",
                    origin_url=f"https://bench-{index}.example.com/story",
                    canonical_url=f"https://bench-{index}.example.com/story",
                    publisher=PUBLISHERS[index % len(PUBLISHERS)],
                    # Every 37th row has an unknown publication date on purpose.
                    published_at=(
                        ""
                        if index % 37 == 0
                        else (
                            datetime(2026, 2, 1, tzinfo=UTC) + timedelta(hours=index)
                        ).isoformat()
                    ),
                    capture_metadata={},
                    verification_status="UNVERIFIED",
                    credibility_tier="unknown",
                    requires_human_review=0,
                )
                session.add(evidence)
                record_evidence_capture(session, evidence, text=_body(rng, index))
                written_evidence += 1
                if written_evidence % 500 == 0:
                    session.flush()

        written_claims = 0
        for round_index in range(per_event_claims):
            for event_id in event_ids:
                if written_claims >= claim_count:
                    continue
                index = written_claims
                term = COMMON_TERMS[(index * 3 + 1) % len(COMMON_TERMS)]
                session.add(
                    Claim(
                        id=f"bench-claim-{index:06d}",
                        event_id=event_id,
                        claim_text=(
                            f"The {term} record asserts benchmark claim {index} "
                            "about the harbour review."
                        ),
                        verification_status=STATUSES[index % len(STATUSES)],
                        claim_signature=f"bench-signature-{index:06d}",
                    )
                )
                written_claims += 1
                if written_claims % 1000 == 0:
                    session.flush()
        for event_id in event_ids:
            claims_per_event[event_id] = per_event_claims
        session.commit()
    finally:
        session.close()
    insert_seconds = time.perf_counter() - insert_start

    sync_start = time.perf_counter()
    session = database.get_session_sync()
    try:
        capability = probe_search_capability(session)
        if not capability.available:
            raise SystemExit(
                "FTS5 search index is unavailable in this runtime: "
                f"{capability.reason} The benchmark needs the S01 index."
            )
        for event_id in event_ids:
            sync_event_index(session, event_id)
        session.commit()
        counts_after_sync = {
            case_id: indexed_counts(session, case_id) for case_id in case_ids
        }
    finally:
        session.close()
    sync_seconds = time.perf_counter() - sync_start

    rebuild_start = time.perf_counter()
    session = database.get_session_sync()
    try:
        rebuild_counts = {}
        for case_id in case_ids:
            result = rebuild_case_search_index(session, case_id)
            rebuild_counts[case_id] = result["counts"]
        session.commit()
        counts_after_rebuild = {
            case_id: indexed_counts(session, case_id) for case_id in case_ids
        }
    finally:
        session.close()
    rebuild_seconds = time.perf_counter() - rebuild_start

    db_bytes = os.path.getsize(db_path)
    for suffix in ("-wal", "-shm"):
        extra = Path(db_path + suffix)
        if extra.exists():
            db_bytes += extra.stat().st_size

    assert rebuild_counts == counts_after_rebuild, (
        "the case-scoped rebuild must reproduce the incremental index counts"
    )
    database.engine.dispose()
    return Fixture(
        db_path=db_path,
        case_ids=case_ids,
        events=len(event_ids),
        evidence=evidence_count,
        claims=claim_count,
        counts_after_sync=counts_after_sync,
        counts_after_rebuild=counts_after_rebuild,
        insert_seconds=insert_seconds,
        sync_seconds=sync_seconds,
        rebuild_seconds=rebuild_seconds,
        db_bytes=db_bytes,
    )


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def measure_queries(
    db_path: str, case_ids: list[str], queries: int, warmup: int = 20
) -> Measurement:
    """Time warm ``read_case_search`` calls over several common terms (ms)."""
    database = Database(db_path)
    session = database.get_session_sync()
    patterns: list[QueryPattern] = [
        QueryPattern(label=term, q=term) for term in COMMON_TERMS
    ]
    patterns.extend(
        QueryPattern(label=term, q=term) for term in TWO_TERM_QUERIES
    )
    patterns.extend(
        [
            QueryPattern(label="levy + type=claim", q="levy", result_type="claim"),
            QueryPattern(
                label="council + status=alleged", q="council", status="alleged"
            ),
            QueryPattern(
                label="quartz + publisher",
                q="quartz",
                publisher="Meridian Wire",
            ),
            QueryPattern(
                label="harbour + date range",
                q="harbour",
                published_from="2026-02-10T00:00:00Z",
                published_to="2026-02-25T00:00:00Z",
            ),
        ]
    )

    def run(pattern: QueryPattern, case_id: str, offset: int) -> int:
        payload = read_case_search(
            session,
            case_id=case_id,
            q=pattern.q,
            result_type=pattern.result_type,
            publisher=pattern.publisher,
            status=pattern.status,
            published_from=pattern.published_from,
            published_to=pattern.published_to,
            limit=25,
            offset=offset,
        )
        return int(payload["total"])

    timings: list[float] = []
    per_pattern: dict[str, list[float]] = {pattern.label: [] for pattern in patterns}
    totals: dict[str, int] = {}
    try:
        for index in range(warmup):
            pattern = patterns[index % len(patterns)]
            run(pattern, case_ids[index % len(case_ids)], 0)
        for index in range(queries):
            pattern = patterns[index % len(patterns)]
            offset = 25 if index % 7 == 0 else 0
            started = time.perf_counter()
            totals[pattern.label] = run(
                pattern, case_ids[index % len(case_ids)], offset
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            timings.append(elapsed_ms)
            per_pattern[pattern.label].append(elapsed_ms)
    finally:
        session.close()
        database.engine.dispose()

    return Measurement(
        queries=len(timings),
        p50_ms=_percentile(timings, 0.50),
        p95_ms=_percentile(timings, 0.95),
        max_ms=max(timings) if timings else 0.0,
        per_pattern={
            label: PatternStats(
                p50_ms=_percentile(values, 0.50),
                p95_ms=_percentile(values, 0.95),
                total=totals.get(label, 0),
            )
            for label, values in per_pattern.items()
        },
    )


def _row(label: str, value: str) -> str:
    return f"{label:<38}{value:>16}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=int, default=10_000)
    parser.add_argument("--claims", type=int, default=20_000)
    parser.add_argument("--queries", type=int, default=320)
    parser.add_argument("--seed", type=int, default=20261120)
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Optional path to write the raw numbers as JSON",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep the temporary database directory instead of deleting it",
    )
    args = parser.parse_args(argv)

    workdir = tempfile.mkdtemp(prefix="triangulate-s02-bench-")
    db_path = str(Path(workdir) / "search-benchmark.sqlite3")
    try:
        fixture = build_fixture(db_path, args.evidence, args.claims, seed=args.seed)
        measurement = measure_queries(db_path, fixture.case_ids, args.queries)

        indexed_rows = sum(
            counts["evidence"] + counts["claim"]
            for counts in fixture.counts_after_sync.values()
        )
        rebuilt_rows = sum(
            counts["evidence"] + counts["claim"]
            for counts in fixture.counts_after_rebuild.values()
        )
        payload = {
            "fixture": {
                "cases": len(fixture.case_ids),
                "events": fixture.events,
                "evidence": fixture.evidence,
                "claims": fixture.claims,
                "indexed_rows_after_sync": indexed_rows,
                "indexed_rows_after_rebuild": rebuilt_rows,
            },
            "timings": {
                "fixture_insert_seconds": fixture.insert_seconds,
                "index_sync_seconds": fixture.sync_seconds,
                "full_rebuild_seconds": fixture.rebuild_seconds,
            },
            "database": {"size_bytes": fixture.db_bytes},
            "queries": {
                "queries": measurement.queries,
                "p50_ms": measurement.p50_ms,
                "p95_ms": measurement.p95_ms,
                "max_ms": measurement.max_ms,
                "per_pattern": {
                    label: {
                        "p50_ms": stats.p50_ms,
                        "p95_ms": stats.p95_ms,
                        "total": stats.total,
                    }
                    for label, stats in measurement.per_pattern.items()
                },
            },
            "environment": {
                "sqlite": _sqlite_version(),
                "target_p95_ms": 500.0,
            },
        }

        print("S02 case-search benchmark (synthetic fixture, temporary database)")
        print("-" * 54)
        print(_row("cases", str(payload["fixture"]["cases"])))
        print(_row("events", str(payload["fixture"]["events"])))
        print(_row("evidence rows", str(payload["fixture"]["evidence"])))
        print(_row("claim rows", str(payload["fixture"]["claims"])))
        print(
            _row(
                "indexed rows (sync)",
                str(payload["fixture"]["indexed_rows_after_sync"]),
            )
        )
        print(
            _row(
                "indexed rows (rebuild)",
                str(payload["fixture"]["indexed_rows_after_rebuild"]),
            )
        )
        print(
            _row(
                "fixture insert (s)",
                f"{payload['timings']['fixture_insert_seconds']:.2f}",
            )
        )
        print(
            _row(
                "index build, S01 sync (s)",
                f"{payload['timings']['index_sync_seconds']:.2f}",
            )
        )
        print(
            _row(
                "full case rebuild (s)",
                f"{payload['timings']['full_rebuild_seconds']:.2f}",
            )
        )
        print(
            _row(
                "database size (MB)",
                f"{payload['database']['size_bytes'] / 1_048_576:.1f}",
            )
        )
        print(_row("SQLite", str(payload["environment"]["sqlite"])))
        print(_row("warm queries", str(measurement.queries)))
        print(_row("warm p50 (ms)", f"{measurement.p50_ms:.2f}"))
        print(_row("warm p95 (ms)", f"{measurement.p95_ms:.2f}"))
        print(_row("warm max (ms)", f"{measurement.max_ms:.2f}"))
        within_target = measurement.p95_ms < 500.0
        print(_row("p95 target < 500 ms", "PASS" if within_target else "FAIL"))
        print()
        print("per-query p50/p95 (ms) and total hits")
        print("-" * 54)
        for label, stats in measurement.per_pattern.items():
            print(
                f"{label:<28}{stats.p50_ms:>8.2f}{stats.p95_ms:>8.2f}"
                f"{stats.total:>10}"
            )
        print()
        print(f"temporary database: {db_path}")

        if args.json is not None:
            args.json.write_text(json.dumps(payload, indent=2) + "\n")
            print(f"raw numbers written to {args.json}")
        return 0
    finally:
        if args.keep:
            print(f"kept fixture at {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


def _sqlite_version() -> str:
    import sqlite3

    return sqlite3.sqlite_version


if __name__ == "__main__":
    raise SystemExit(main())
