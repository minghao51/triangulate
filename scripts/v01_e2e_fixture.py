#!/usr/bin/env python3
"""Materialize the deterministic V01 browser fixture in an isolated directory.

Example: ``uv run python scripts/v01_e2e_fixture.py --out /tmp/v01-e2e``
The output path is explicit and never points at the checkout's application DB.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, text

from src.cases import TopicCaseService
from src.ingester.topic_fetcher import describe_source_outcomes
from src.storage import CaseSnapshot, Claim, EvidenceCapture, EvidenceItem, Event, InvestigationRun, get_database, init_database
from src.storage.migrations import run_migrations

TITLE_TERM = "Harbour"
BODY_TERM = "quartz"
CLAIM_TERM = "evacuation"
FILTER_QUERY = "quartz"
CLAIM_TEXT = "The authority ordered an evacuation near the harbour."
BODY = (
    "The authority ordered an evacuation near the harbour. "
    "Quartz inspections continue along the northern pier."
)
ARTICLES = [
    {
        "url": "https://example.com/harbour-a",
        "title": "Harbour wire report",
        "source": "Harbour",
        "published_at": "2026-03-08T12:00:00+00:00",
        "content": BODY,
        "relevance_score": 0.9,
    },
    {
        "url": "https://example.net/harbour-b",
        "title": "Harbour dispatch",
        "source": "Harbour",
        "published_at": "2026-03-08T12:00:00+00:00",
        "content": BODY,
        "relevance_score": 0.9,
    },
]
OUTCOME = {
    "source_name": "Harbour",
    "source_url": "https://example.com/feed.xml",
    "source_type": "rss",
    "fetch_strategy": "rss",
    "status": "success_with_items",
    "attempted": True,
    "article_count": 1,
    "error": None,
    "warning": None,
    "reason": None,
}


@contextmanager
def deterministic_uuids(start: int = 1):
    original = uuid.uuid4
    counter = iter(range(start, start + 10000))
    uuid.uuid4 = lambda: uuid.UUID(int=next(counter))
    try:
        yield
    finally:
        uuid.uuid4 = original


def _payload(articles: list[dict] = ARTICLES) -> dict:
    outcomes = [
        {**OUTCOME, "source_name": article["source"], "article_count": 1}
        for article in articles
    ]
    summary = describe_source_outcomes(outcomes, requested_count=len(outcomes))
    return {
        "articles": [dict(article) for article in articles],
        "conflict": "ukraine_war",
        "queries_generated": ["harbour"],
        "source_plan": [{"name": item["source_name"]} for item in outcomes],
        "source_plan_total": len(outcomes),
        "source_outcomes": outcomes,
        "sources_used": [item["source_name"] for item in outcomes],
        "articles_fetched": len(articles),
        "articles_processed": len(articles),
        "acquisition_coverage": summary["coverage"],
        "acquisition_counts": summary["counts"],
    }


def install_fakes(
    service: TopicCaseService,
    *,
    articles: list[dict] = ARTICLES,
    claim_text: str = CLAIM_TEXT,
) -> None:
    async def fake_fetch(*_args, **_kwargs):
        return _payload(articles)

    async def fake_process(article: dict[str, object]):
        return {
            "id": "temporary",
            "timestamp": datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
            "title": "Harbour evacuation briefing",
            "summary": "Synthetic deterministic event",
            "verification_status": "ALLEGED",
            "claims": [
                {
                    "claim": claim_text,
                    "who": ["Authority", "Harbour residents"],
                    "verification_status": "ALLEGED",
                }
            ],
            "narratives": [],
            "parties": [
                {"canonical_name": "Authority", "aliases": ["Authority"]},
                {"canonical_name": "Harbour residents", "aliases": ["Harbour residents"]},
            ],
        }

    service.topic_fetcher.fetch_articles_by_topic = fake_fetch
    service.ai_workflow.process_article = fake_process


def materialize(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    db_path = out / "triangulate.db"
    if db_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing fixture database: {db_path}")
    config_path = out / "config.toml"
    config_path.write_text('[ai]\nmodel = "test-model"\n', encoding="utf-8")

    init_database(str(db_path))
    run_migrations(str(db_path))
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=out)
    install_fakes(service)

    async def ingest():
        return await service.run_case(
            query="V01 Harbour evacuation fixture",
            output_dir=out,
            conflict="ukraine_war",
        )

    with deterministic_uuids():
        case = asyncio.run(ingest())

    # Freeze a claim in the initial snapshot, then move its live row on. The
    # browser inspector uses the spec's `snapshot` query key (not `snapshotId`).
    session = get_database().get_session_sync()
    try:
        sources = list(
            session.execute(
                select(EvidenceItem).where(EvidenceItem.case_id == case.id)
            ).scalars()
        )
        captures = list(
            session.execute(
                select(EvidenceCapture).where(
                    EvidenceCapture.evidence_id.in_([source.id for source in sources])
                )
            ).scalars()
        )
        claims = list(
            session.execute(
                select(Claim)
                .join(Event, Claim.event_id == Event.id)
                .where(Event.case_id == case.id)
            ).scalars()
        )
        historical_claim = next(
            claim for claim in claims if CLAIM_TERM in claim.claim_text.lower()
        )
        historical_claim_id = historical_claim.id
        historical_claim.claim_text = "Rewritten current claim; historical text remains frozen."
        session.commit()
        run = session.execute(
            select(InvestigationRun).where(InvestigationRun.case_id == case.id)
        ).scalar_one()
        snapshot = session.execute(
            select(CaseSnapshot).where(CaseSnapshot.case_id == case.id)
        ).scalar_one()
        version = session.execute(text("SELECT MAX(version) FROM _migrations")).scalar_one()
    finally:
        session.close()

    changed_articles = [
        {
            **article,
            "content": article["content"] + " Updated evacuation context was confirmed at noon.",
        }
        for article in ARTICLES
    ]
    install_fakes(
        service,
        articles=changed_articles,
        claim_text="Officials revised the evacuation order near the harbour.",
    )

    async def ingest_change():
        return await service.run_case(
            query="V01 Harbour evacuation fixture",
            output_dir=out,
            conflict="ukraine_war",
        )

    with deterministic_uuids(start=5000):
        asyncio.run(ingest_change())

    session = get_database().get_session_sync()
    try:
        runs = list(
            session.execute(
                select(InvestigationRun)
                .where(InvestigationRun.case_id == case.id)
                .order_by(InvestigationRun.sequence)
            ).scalars()
        )
        snapshots = list(
            session.execute(
                select(CaseSnapshot)
                .where(CaseSnapshot.case_id == case.id)
                .order_by(CaseSnapshot.created_at)
            ).scalars()
        )
        changes = service.get_run_changes(case.id, runs[-1].id)
        version = session.execute(text("SELECT MAX(version) FROM _migrations")).scalar_one()
        indexed = session.execute(
            text(
                "SELECT COUNT(*) FROM case_search_index "
                "WHERE case_id = :case_id AND body LIKE :term"
            ),
            {"case_id": case.id, "term": f"%{BODY_TERM}%"},
        ).scalar_one()
    finally:
        session.close()
    change_run = runs[-1]
    change_snapshot = snapshots[-1]
    assert len(runs) == 2 and len(snapshots) == 2
    assert changes is not None
    assert changes["availability"] == "ready" and changes["total"] > 0
    assert version == 15 and indexed > 0
    frozen_change_claim = next(
        item for item in changes["items"] if item["type"] == "claim_added"
    )
    frozen_change_claim_id = frozen_change_claim["entityId"]
    frozen_change_claim_text = frozen_change_claim["after"]["text"]
    session = get_database().get_session_sync()
    try:
        live_change_claim = session.get(Claim, frozen_change_claim_id)
        assert live_change_claim is not None
        live_change_claim.claim_text = "Current live claim text differs from the frozen observation."
        session.commit()
    finally:
        session.close()

    foreign_article = {
        "url": "https://foreign.example/tungsten",
        "title": "Tungsten briefing",
        "source": "Foreign Wire",
        "published_at": "2026-03-09T12:00:00+00:00",
        "content": "Tungsten assay details unique to the foreign case.",
        "relevance_score": 0.8,
    }
    install_fakes(
        service,
        articles=[foreign_article],
        claim_text="Tungsten figures were reported by the foreign office.",
    )

    async def ingest_foreign():
        return await service.run_case(
            query="Foreign tungsten case",
            output_dir=out,
            conflict="ukraine_war",
        )

    with deterministic_uuids(start=10000):
        foreign_case = asyncio.run(ingest_foreign())

    change_type_labels = {
        "article_added": "Article added",
        "capture_changed": "Capture changed",
        "claim_added": "Claim added",
        "claim_no_longer_extracted": "No longer extracted",
        "classification_changed": "Classification changed",
        "relationship_changed": "Relationship changed",
        "review_state_changed": "Review state changed",
        "exception_changed": "Exception changed",
    }
    manifest = {
        "caseId": case.id,
        "snapshotId": snapshot.id,
        "runId": run.id,
        "changeRunId": change_run.id,
        "changeSnapshotId": change_snapshot.id,
        "baselineSnapshotId": change_run.baseline_snapshot_id,
        "historicalClaimId": historical_claim_id,
        "historicalClaimText": CLAIM_TEXT,
        "currentClaimText": "Rewritten current claim; historical text remains frozen.",
        "frozenChangeClaimId": frozen_change_claim_id,
        "frozenChangeClaimText": frozen_change_claim_text,
        "currentChangeClaimText": "Current live claim text differs from the frozen observation.",
        "evidenceIds": [source.id for source in sources],
        "captureIds": [source.current_capture_id for source in sources],
        "otherCaseId": foreign_case.id,
        "knownTerms": {
            "evidenceTitleTerm": TITLE_TERM,
            "captureBodyTerm": BODY_TERM,
            "claimTerm": CLAIM_TERM,
            "filteredQuery": FILTER_QUERY,
        },
        "expectedDeltaRows": [
            {
                "type": item["type"],
                "entityId": item["entityId"],
                "labels": [
                    change_type_labels.get(item["type"], item["type"].replace("_", " ")),
                    {
                        "article": "Article",
                        "claim": "Claim",
                        "evidence": "Evidence",
                        "link": "Claim/evidence link",
                        "review": "Review",
                        "exception": "Exception",
                    }.get(item["entityType"], item["entityType"]),
                ],
            }
            for item in changes["items"]
        ],
        "expectedCounts": {
            "evidence": len(sources),
            "captures": len(captures),
            "claims": len(claims),
            "runs": 2,
            "snapshots": 2,
            "searchMigration": version,
            "searchMatches": indexed,
            "cases": 2,
        },
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("/tmp/v01-e2e"))
    args = parser.parse_args()
    manifest = materialize(args.out.expanduser().resolve())
    print(
        "V01 fixture ready\n"
        f"  output: {args.out.expanduser().resolve()}\n"
        f"  case: {manifest['caseId']}\n"
        f"  snapshot: {manifest['snapshotId']}\n"
        f"  run: {manifest['runId']}\n"
        f"  evidence/captures/claims: "
        f"{manifest['expectedCounts']['evidence']}/"
        f"{manifest['expectedCounts']['captures']}/"
        f"{manifest['expectedCounts']['claims']} (migration {manifest['expectedCounts']['searchMigration']})\n"
        f"  manifest: {args.out.expanduser().resolve() / 'manifest.json'}"
    )


if __name__ == "__main__":
    main()
