"""V01 backend journey: deterministic ingestion followed by read-only HTTP reads."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.http.app import app
from src.http.dependencies import get_case_service
from src.storage.migrations import run_migrations
from src.storage import (
    CaseSnapshot,
    Claim,
    EvidenceCapture,
    EvidenceItem,
    Event,
    InvestigationRun,
    get_database,
)
from tests.test_r03_snapshots import ARTICLE, install_fakes, make_service, run_full

BODY_TERM = "quartz"
CLAIM_TERM = "evacuation"
TITLE_TERM = "Harbour"
FILTER_QUERY = "quartz"
CLAIM_TEXT = "The authority ordered an evacuation near the harbour."
BODY = (
    "The authority ordered an evacuation near the harbour. "
    "Quartz inspections continue along the northern pier."
)
UPDATED_BODY = BODY + " Updated evacuation context was confirmed at noon."


class RecordingASGI:
    """ASGI-only request recorder; does not modify the application."""

    def __init__(self, app):
        self.app = app
        self.requests: list[tuple[str, str, int]] = []

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        status = 500

        async def recording_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, recording_send)
        finally:
            path = scope.get("path", "")
            method = scope.get("method", "")
            self.requests.append((method, path, status))


def _uuid_sequence(monkeypatch):
    values = iter(range(1, 10000))
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(int=next(values)))


def _article(url: str, title: str) -> dict:
    return {
        **ARTICLE,
        "url": url,
        "title": title,
        "source": title.split()[0],
        "content": BODY,
    }


def _db_session():
    return get_database().get_session_sync()


def _index_dump(db_path: Path) -> bytes:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT case_id, entity_type, entity_id, title, body, signature, event_id, "
            "party_id, publisher, status, published_at FROM case_search_index "
            "ORDER BY case_id, entity_type, entity_id"
        ).fetchall()
    return json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()


def _migration_dump(db_path: Path) -> bytes:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT version, name, applied_at FROM _migrations ORDER BY version"
        ).fetchall()
    return json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()


@pytest.mark.asyncio
async def test_v01_backend_fixture_journey(monkeypatch, tmp_path):
    db_path = tmp_path / "triangulate.db"
    _uuid_sequence(monkeypatch)
    service = make_service(tmp_path)
    run_migrations(str(db_path))
    primary_article = _article("https://example.com/harbour-a", "Harbour wire report")
    second_article = _article("https://example.net/harbour-b", "Harbour dispatch")
    install_fakes(monkeypatch, service, article=primary_article, claim_text=CLAIM_TEXT)

    # The approved fetch stub returns the same synthetic article shape. Replace
    # only its article list so the actual run_case writer produces two sources.
    from tests.test_r03_snapshots import structured_payload, SUCCESS_OUTCOME

    async def fetch_two(*args, **kwargs):
        return structured_payload(
            articles=[primary_article, second_article],
            outcomes=[SUCCESS_OUTCOME, {**SUCCESS_OUTCOME, "source_name": "Dispatch"}],
        )

    monkeypatch.setattr(service.topic_fetcher, "fetch_articles_by_topic", fetch_two)
    case = await run_full(service, tmp_path)

    session = _db_session()
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
        run = session.execute(
            select(InvestigationRun).where(InvestigationRun.case_id == case.id)
        ).scalar_one()
        snapshot = session.execute(
            select(CaseSnapshot).where(CaseSnapshot.case_id == case.id)
        ).scalar_one()
    finally:
        session.close()

    assert case.id and run.id and snapshot.id
    assert run.result_snapshot_id == snapshot.id
    assert len(sources) >= 2
    assert captures and claims
    assert all(source.current_capture_id for source in sources)
    assert any(CLAIM_TERM in claim.claim_text.lower() for claim in claims)
    # Search index is deployed at migration 15 before reads are exercised.
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT MAX(version) FROM _migrations").fetchone()[0] == 15

    # Remove the live claim only after the immutable snapshot has been committed.
    historical = next(
        claim for claim in claims if CLAIM_TERM in claim.claim_text.lower()
    )
    frozen_claim_text = historical.claim_text
    changed_article = {
        **primary_article,
        "content": UPDATED_BODY,
    }
    install_fakes(
        monkeypatch,
        service,
        article=changed_article,
        claim_text="Officials revised the evacuation order near the harbour.",
    )
    await run_full(service, tmp_path, case.id)
    session = _db_session()
    try:
        ordered_runs = list(
            session.execute(
                select(InvestigationRun)
                .where(InvestigationRun.case_id == case.id)
                .order_by(InvestigationRun.sequence)
            ).scalars()
        )
        ordered_snapshots = list(
            session.execute(
                select(CaseSnapshot)
                .where(CaseSnapshot.case_id == case.id)
                .order_by(CaseSnapshot.created_at)
            ).scalars()
        )
    finally:
        session.close()
    change_run = ordered_runs[-1]
    change_snapshot = ordered_snapshots[-1]
    assert change_run.id != run.id
    ids_path = Path("/tmp/v01-evidence/journey-identifiers.json")
    ids_path.parent.mkdir(parents=True, exist_ok=True)
    ids_path.write_text(
        json.dumps(
            {
                "caseId": case.id,
                "initialRunId": run.id,
                "initialSnapshotId": snapshot.id,
                "changeRunId": change_run.id,
                "changeSnapshotId": change_snapshot.id,
                "historicalClaimId": historical.id,
                "evidenceIds": [source.id for source in sources],
                "captureIds": [source.current_capture_id for source in sources],
                "terms": {
                    "evidenceTitle": TITLE_TERM,
                    "captureBody": BODY_TERM,
                    "claim": CLAIM_TERM,
                    "filteredQuery": FILTER_QUERY,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    assert change_run.baseline_snapshot_id == snapshot.id
    assert change_run.result_snapshot_id == change_snapshot.id

    session = _db_session()
    try:
        live_claim = session.get(Claim, historical.id)
        assert live_claim is not None
        live_claim.claim_text = "A rewritten live assertion, not the historical claim."
        session.commit()
    finally:
        session.close()

    foreign_article = {
        **_article("https://foreign.example/tungsten", "Tungsten briefing"),
        "content": "Tungsten assay details unique to the foreign case.",
    }
    install_fakes(
        monkeypatch,
        service,
        article=foreign_article,
        claim_text="Tungsten figures were reported by the foreign office.",
    )
    other = await service.run_case(
        query="Foreign tungsten case",
        output_dir=tmp_path,
        conflict="ukraine_war",
    )
    # This is another deterministic fake ingestion (not a network/model call).
    # The response must remain isolated even when its own indexed term is queried.
    recording = RecordingASGI(app)
    app.dependency_overrides[get_case_service] = lambda: service
    index_before = _index_dump(db_path)
    migrations_before = _migration_dump(db_path)
    try:
        with TestClient(recording) as client:
            # 1. inspect quotation, then request the exact immutable capture text.
            detail = client.get(f"/api/cases/{case.id}/claims/{historical.id}")
            assert detail.status_code == 200, detail.text
            assert detail.json()["claimText"] == "A rewritten live assertion, not the historical claim."
            passage = detail.json()["passages"][0]
            evidence_id = passage["id"]
            capture_id = passage["captureId"]
            capture = client.get(
                f"/api/cases/{case.id}/evidence/{evidence_id}/captures/{capture_id}",
                params={"start": 0, "length": len(BODY)},
            )
            assert capture.status_code == 200, capture.text
            capture_data = capture.json()
            assert capture_data["text"] == BODY
            assert capture_data["length"] == len(BODY)
            assert capture_data["totalLength"] == len(UPDATED_BODY)

            # 2. compare two sources pinned to their persisted current captures.
            source_captures = []
            for source in sources[:2]:
                source_captures.append((source.id, source.current_capture_id))
            comparison = client.get(
                f"/api/cases/{case.id}/comparison",
                params={
                    "left": source_captures[0][0],
                    "right": source_captures[1][0],
                    "leftCapture": source_captures[0][1],
                    "rightCapture": source_captures[1][1],
                },
            )
            assert comparison.status_code == 200, comparison.text
            assert comparison.json()["leftCaptureId"] == source_captures[0][1]
            assert comparison.json()["rightCaptureId"] == source_captures[1][1]
            assert comparison.json()["claims"]["rows"]

            # 3. history and delta preserve the actual run/snapshot availability.
            runs_response = client.get(f"/api/cases/{case.id}/investigation-runs")
            assert runs_response.status_code == 200
            assert any(row["id"] == run.id for row in runs_response.json()["items"])
            initial_changes = client.get(
                f"/api/cases/{case.id}/investigation-runs/{run.id}/changes"
            )
            assert initial_changes.status_code == 200
            assert initial_changes.json()["availability"] == "initial"
            assert initial_changes.json()["targetSnapshotId"] == snapshot.id
            changes = client.get(
                f"/api/cases/{case.id}/investigation-runs/{change_run.id}/changes"
            )
            assert changes.status_code == 200
            change_data = changes.json()
            assert change_data["availability"] == "ready"
            assert change_data["targetSnapshotId"] == change_snapshot.id
            assert change_data["total"] > 0
            added_claim = next(
                item for item in change_data["items"]
                if item["type"] == "claim_added"
            )
            assert added_claim["originRunId"] == change_run.id
            assert added_claim["observedByRunId"] == change_run.id

            # 4. typed search results and filters: evidence title, capture body,
            # claim text; snippets are plain text and filters narrow result types.
            def search(q, **params):
                return client.get(
                    f"/api/cases/{case.id}/search", params={"q": q, **params}
                )

            title_results = search(TITLE_TERM, type="evidence")
            body_results = search(BODY_TERM, type="evidence")
            claim_results = search(CLAIM_TERM, type="claim")
            filtered = search(TITLE_TERM, type="evidence", publisher="Harbour")
            for response in (title_results, body_results, claim_results, filtered):
                assert response.status_code == 200, response.text
                assert "<mark" not in response.text.lower()
                assert "<em" not in response.text.lower()
                assert all("<" not in item["snippet"] for item in response.json()["items"])
            assert {item["id"] for item in title_results.json()["items"]} == {
                source.id for source in sources
            }
            assert {item["id"] for item in body_results.json()["items"]} == {
                source.id for source in sources
            }
            assert historical.id in {item["id"] for item in claim_results.json()["items"]}
            assert filtered.json()["items"]
            assert all(item["resultType"] == "evidence" for item in filtered.json()["items"])

            # 5. snapshot selector resolves the frozen text after live mutation.
            snapshot_claim = client.get(
                f"/api/cases/{case.id}/claims/{historical.id}",
                params={"snapshotId": snapshot.id},
            )
            assert snapshot_claim.status_code == 200, snapshot_claim.text
            assert snapshot_claim.json()["claimText"] == frozen_claim_text
            assert snapshot_claim.json()["claimText"] != detail.json()["claimText"]
            assert snapshot_claim.json()["snapshotId"] == snapshot.id

            # 6. Wrong-case search/read never returns first-case resources.
            foreign_only = client.get(
                f"/api/cases/{other.id}/search", params={"q": "tungsten"}
            )
            assert foreign_only.status_code == 200
            assert foreign_only.json()["total"] > 0
            foreign_search = client.get(
                f"/api/cases/{case.id}/search", params={"q": "tungsten"}
            )
            assert foreign_search.status_code == 200
            assert foreign_search.json()["items"] == []
            assert foreign_search.json()["total"] == 0
            cross_case_claim = client.get(
                f"/api/cases/{other.id}/claims/{historical.id}"
            )
            assert cross_case_claim.status_code == 404
            cross_case_evidence = client.get(
                f"/api/cases/{other.id}/evidence/{evidence_id}"
            )
            assert cross_case_evidence.status_code == 404
    finally:
        app.dependency_overrides.clear()

    index_after = _index_dump(db_path)
    migrations_after = _migration_dump(db_path)
    assert index_after == index_before
    assert migrations_after == migrations_before
    proof_dir = Path("/tmp/v01-evidence")
    proof_dir.mkdir(parents=True, exist_ok=True)
    with (proof_dir / "index-migration-proof.txt").open("a", encoding="utf-8") as proof:
        proof.write(
            f"index before sha256={hashlib.sha256(index_before).hexdigest()} "
            f"after sha256={hashlib.sha256(index_after).hexdigest()} "
            f"bytes={len(index_before)} identical={index_before == index_after}\n"
            f"migrations before sha256={hashlib.sha256(migrations_before).hexdigest()} "
            f"after sha256={hashlib.sha256(migrations_after).hexdigest()} "
            f"bytes={len(migrations_before)} identical={migrations_before == migrations_after}\n"
        )
    assert recording.requests
    assert all(method == "GET" for method, _path, _status in recording.requests)
    log_dir = Path("/tmp/v01-evidence")
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "method-log.tsv").open("a", encoding="utf-8") as log:
        for method, path, status in recording.requests:
            log.write(f"{method}\t{path}\t{status}\n")

    assert len(recording.requests) > 0
