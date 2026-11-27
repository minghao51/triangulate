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
from typing import Any

from sqlalchemy import select, text

from src.cases import TopicCaseService
from src.cases.service import _payload_checksum
from src.ingester.topic_fetcher import describe_source_outcomes
from src.storage import (
    CaptureKind,
    CaseArtifact,
    CaseSnapshot,
    CaseStageName,
    CaseStatus,
    Claim,
    EvidenceCapture,
    EvidenceItem,
    Event,
    InvestigationRun,
    TopicCase,
    VerificationStatus,
    get_database,
    init_database,
)
from src.storage.migrations import run_migrations
from src.storage.captures import upsert_evidence_capture

# Additive refinement states (F00 step 2). Opt-in only: ``materialize`` and the
# baseline ``manifest.json`` keep their exact bytes.
REFINEMENT_VARIANTS_FILENAME = "refinement_variants.json"
# Deterministic IDs outside every sequence used while materializing the baseline.
MISSING_CASE_ID = "00000000-0000-0000-0000-0000000000ff"
ABSENT_REPORT_CASE_ID = "00000000-0000-0000-0000-0000000000fe"
ZERO_COORDINATE_EVENT_ID = "00000000-0000-0000-0000-0000000000fd"
UNRECOGNIZED_TIMELINE_STATUS = "UNRECOGNIZED_ALERT"
LEGACY_CAPTURE_KIND = CaptureKind.LEGACY_SNAPSHOT.value
# A distinct body: identical text for the same evidence reuses the existing
# immutable capture row by design, so a legacy version must be a real version.
LEGACY_CAPTURE_TEXT = (
    "The authority ordered an evacuation near the harbour. "
    "Quartz inspections continue along the northern pier. "
    "Legacy snapshot body retained without an observation time."
)

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


def _sorted_by_id(rows: list[Any]) -> list[Any]:
    """Return fixture rows in a deterministic order independent of insertion."""
    return sorted(rows, key=lambda row: str(row.id))


def _rewrite_report_timeline_status(
    report_path: Path, out: Path, entry_index: int, raw_status: str
) -> None:
    """Apply the same raw status to the exported JSON file of a report.

    ``report_path`` is a stored artifact path from this scratch fixture, so it
    is first contained under ``out`` and only then read; a missing or malformed
    file is an explicit fixture error rather than a silent partial state.
    """
    resolved = report_path.expanduser().resolve()
    if not resolved.is_relative_to(out.expanduser().resolve()):
        raise RuntimeError(f"Report path {report_path} is outside the fixture output")
    try:
        document = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Refinement fixture report {resolved} is unreadable: {exc}") from exc
    timeline = document.get("timeline") or []
    if entry_index >= len(timeline):
        raise RuntimeError(
            f"Report timeline has {len(timeline)} entries; cannot rewrite {entry_index}"
        )
    timeline[entry_index]["status"] = raw_status
    document["timeline"] = timeline
    try:
        resolved.write_text(
            json.dumps(document, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        raise RuntimeError(f"Refinement fixture report {resolved} is unwritable: {exc}") from exc


def materialize_refinement_states(out: Path) -> dict[str, Any]:
    """Materialize the baseline fixture, then add the refinement failure states.

    Returns ``{"baseline": <baseline manifest>, "variants": <variant map>}``.
    Additive and opt-in: :func:`materialize` still writes the byte-identical
    baseline ``manifest.json``. This function keeps that baseline database and
    adds the states later refinement tasks need, describing them in
    ``refinement_variants.json`` next to the baseline manifest:

    * a missing case id (never created),
    * a claim/evidence annotation target owned by another case,
    * out-of-range, missing and exactly-zero (0,0) event coordinates,
    * an out-of-enum timeline status preserved as raw text,
    * a case without report artifacts,
    * a legacy capture version with unknown provenance.

    The unrecognized timeline status is stored in a frozen report bundle
    (``report_json`` payload and its exported file) because
    ``events.verification_status`` is an ORM enum: an out-of-enum value there
    makes every ORM read of the case raise ``LookupError``, so the only honest
    place for the raw value is a JSON payload whose readers preserve it.
    """
    baseline = materialize(out)
    case_id = baseline["caseId"]
    other_case_id = baseline["otherCaseId"]
    session = get_database().get_session_sync()
    try:
        case = session.get(TopicCase, case_id)
        if case is None:
            raise RuntimeError(f"Baseline case {case_id!r} is missing")

        # 1. Coordinate states on the baseline case's live events.
        events = _sorted_by_id(
            list(session.execute(select(Event).where(Event.case_id == case_id)).scalars())
        )
        if len(events) < 2:
            raise RuntimeError("Baseline case needs two events for coordinate states")
        out_of_range, missing = events[0], events[1]
        out_of_range.location_country_code = "ZZ"
        out_of_range.location_lat = 120.5
        out_of_range.location_lon = 245.0
        missing.location_country_code = None
        missing.location_lat = None
        missing.location_lon = None
        session.add(
            Event(
                id=ZERO_COORDINATE_EVENT_ID,
                timestamp=datetime(2026, 3, 8, 13, 0, tzinfo=UTC),
                title="Harbour datum marker",
                summary="Synthetic event whose recorded coordinates are exactly 0,0.",
                verification_status=VerificationStatus.ALLEGED,
                location_country_code=None,
                location_lat=0.0,
                location_lon=0.0,
                case_id=case_id,
            )
        )
        case.event_count = int(case.event_count or 0) + 1

        # 2. A case that never produced report artifacts.
        session.add(
            TopicCase(
                id=ABSENT_REPORT_CASE_ID,
                query="Synthetic refinement case without a report",
                slug="refinement-absent-report",
                conflict="ukraine_war",
                status=CaseStatus.REVIEW_READY,
                priority=0,
                current_stage=CaseStageName.REPORT,
                metadata_json={},
            )
        )

        # 3. A legacy capture version with unknown provenance on live evidence.
        evidence = _sorted_by_id(
            list(
                session.execute(
                    select(EvidenceItem).where(EvidenceItem.case_id == case_id)
                ).scalars()
            )
        )[0]
        with deterministic_uuids(start=20000):
            legacy_capture = upsert_evidence_capture(
                session,
                evidence_id=evidence.id,
                text=LEGACY_CAPTURE_TEXT,
                observed_at=None,
                capture_kind=CaptureKind.LEGACY_SNAPSHOT,
                metadata={},
            )
        if legacy_capture.metadata_json:
            raise RuntimeError("Legacy capture metadata must remain unknown (empty)")

        # 4. Wrong-case annotation targets: entities owned by the other case.
        foreign_claim = _sorted_by_id(
            list(
                session.execute(
                    select(Claim)
                    .join(Event, Claim.event_id == Event.id)
                    .where(Event.case_id == other_case_id)
                ).scalars()
            )
        )[0]
        foreign_evidence = _sorted_by_id(
            list(
                session.execute(
                    select(EvidenceItem).where(EvidenceItem.case_id == other_case_id)
                ).scalars()
            )
        )[0]

        # 5. Unrecognized timeline status preserved raw in a frozen report bundle.
        artifact = (
            session.execute(
                select(CaseArtifact)
                .where(
                    CaseArtifact.case_id == case_id,
                    CaseArtifact.artifact_type == "report_json",
                )
                .order_by(CaseArtifact.created_at.asc(), CaseArtifact.id.asc())
            )
            .scalars()
            .first()
        )
        if artifact is None or not artifact.path:
            raise RuntimeError("Baseline case has no report_json artifact to extend")
        payload = dict(artifact.payload_json or {})
        stored_timeline = [dict(entry) for entry in payload.get("timeline") or []]
        if not stored_timeline:
            raise RuntimeError("report_json payload has no timeline entries")
        entry_index = len(stored_timeline) - 1
        stored_timeline[entry_index]["status"] = UNRECOGNIZED_TIMELINE_STATUS
        payload["timeline"] = stored_timeline
        artifact.payload_json = payload
        artifact.checksum = _payload_checksum(payload)
        artifact_id = artifact.id
        artifact_stage_run_id = artifact.stage_run_id
        artifact_path = Path(artifact.path)
        session.commit()
    finally:
        session.close()

    _rewrite_report_timeline_status(
        artifact_path, out, entry_index, UNRECOGNIZED_TIMELINE_STATUS
    )

    variants: dict[str, Any] = {
        "baselineManifest": "manifest.json",
        "caseId": case_id,
        "otherCaseId": other_case_id,
        "additions": {"cases": 1, "events": 1, "captureVersions": 1},
        "missingCase": {
            "caseId": MISSING_CASE_ID,
            "expectedLookup": None,
        },
        "wrongCaseAnnotationTarget": {
            "caseId": case_id,
            "targetType": "claim",
            "targetId": foreign_claim.id,
            "targetOwnerCaseId": other_case_id,
            "evidenceTarget": {
                "targetType": "evidence",
                "targetId": foreign_evidence.id,
                "targetOwnerCaseId": other_case_id,
            },
        },
        "coordinates": {
            "caseId": case_id,
            "outOfRange": {
                "eventId": out_of_range.id,
                "locationLat": 120.5,
                "locationLon": 245.0,
            },
            "missing": {
                "eventId": missing.id,
                "locationLat": None,
                "locationLon": None,
            },
            "recordedAtZero": {
                "eventId": ZERO_COORDINATE_EVENT_ID,
                "locationLat": 0.0,
                "locationLon": 0.0,
            },
        },
        "unrecognizedTimelineStatus": {
            "caseId": case_id,
            "artifactId": artifact_id,
            "stageRunId": artifact_stage_run_id,
            "path": str(artifact_path),
            "entryIndex": entry_index,
            "rawStatus": UNRECOGNIZED_TIMELINE_STATUS,
        },
        "absentReport": {
            "caseId": ABSENT_REPORT_CASE_ID,
            "reportPath": None,
            "manifestPath": None,
        },
        "legacyCapture": {
            "captureId": legacy_capture.id,
            "evidenceId": evidence.id,
            "caseId": case_id,
            "captureKind": LEGACY_CAPTURE_KIND,
            "observedAt": None,
            "metadata": {},
        },
    }
    (out / REFINEMENT_VARIANTS_FILENAME).write_text(
        json.dumps(variants, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"baseline": baseline, "variants": variants}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("/tmp/v01-e2e"))
    parser.add_argument(
        "--refinement-variants",
        action="store_true",
        help=(
            "Also add the refinement fixture states (missing case, wrong-case "
            "annotation target, coordinate states, unrecognized timeline status, "
            "absent report, legacy capture) and write "
            f"{REFINEMENT_VARIANTS_FILENAME}"
        ),
    )
    args = parser.parse_args()
    out = args.out.expanduser().resolve()
    if args.refinement_variants:
        states = materialize_refinement_states(out)
        manifest = states["baseline"]
    else:
        manifest = materialize(out)
    print(
        "V01 fixture ready\n"
        f"  output: {out}\n"
        f"  case: {manifest['caseId']}\n"
        f"  snapshot: {manifest['snapshotId']}\n"
        f"  run: {manifest['runId']}\n"
        f"  evidence/captures/claims: "
        f"{manifest['expectedCounts']['evidence']}/"
        f"{manifest['expectedCounts']['captures']}/"
        f"{manifest['expectedCounts']['claims']} (migration {manifest['expectedCounts']['searchMigration']})\n"
        f"  manifest: {out / 'manifest.json'}"
    )
    if args.refinement_variants:
        print(f"  refinement variants: {out / REFINEMENT_VARIANTS_FILENAME}")


if __name__ == "__main__":
    main()
