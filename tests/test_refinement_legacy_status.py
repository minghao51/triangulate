"""An out-of-enum ``verification_status`` must not break the case read path.

SQLAlchemy's ``Enum`` result processor raises ``LookupError`` when the stored
string is not a declared member, so a single legacy value used to fail the whole
case detail (and therefore the timeline/claims/evidence slices derived from it).
The fix is read-side only: no schema or migration change is involved, an
out-of-enum value is read as the raw stored text, and writes stay validated.

These tests bypass the ORM with plain SQL to plant the out-of-enum values, then
assert every case read returns 200, the DTO keeps ``verificationStatus:
"unknown"`` plus the raw stored text, known values carry no raw text, and the
GET-only reads changed nothing in the database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import StatementError

from src.cases import TopicCaseService
from src.http.app import app
from src.http.dependencies import get_case_service
from src.storage import (
    CaseStatus,
    Claim,
    EvidenceItem,
    Event,
    TopicCase,
    get_database,
    init_database,
)

EVENT_TS = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)
# Deliberately not a member of ``VerificationStatus`` (and not ``UNVERIFIED``).
LEGACY_EVENT_STATUS = "PENDING_LEGACY"
LEGACY_CLAIM_STATUS = "awaiting-review"
LEGACY_EVIDENCE_STATUS = "LEGACY_UNREVIEWED"


def _service(tmp_path: Path) -> TopicCaseService:
    init_database(str(tmp_path / "triangulate.db"))
    return TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)


def _seed_case(tmp_path: Path) -> None:
    """Write valid rows through the ORM, then plant raw values with plain SQL.

    The ORM is not usable for the plant: assigning an out-of-enum member would be
    rejected by the bind processor (correctly — that is the write contract).
    """
    session = get_database().get_session_sync()
    try:
        session.add(
            TopicCase(
                id="case-1",
                query="Legacy status case",
                slug="legacy-status-case",
                conflict="trade",
                status=CaseStatus.REVIEW_READY,
                metadata_json={},
            )
        )
        session.add_all(
            [
                Event(
                    id="event-legacy",
                    timestamp=EVENT_TS,
                    title="Legacy event",
                    summary="Recorded event with a legacy status",
                    verification_status="ALLEGED",
                    case_id="case-1",
                ),
                Event(
                    id="event-known",
                    timestamp=EVENT_TS,
                    title="Known event",
                    summary="Recorded event with a known status",
                    verification_status="CONFIRMED",
                    case_id="case-1",
                ),
                Claim(
                    id="claim-legacy",
                    event_id="event-legacy",
                    claim_text="Legacy claim",
                    verification_status="ALLEGED",
                ),
                Claim(
                    id="claim-known",
                    event_id="event-known",
                    claim_text="Known claim",
                    verification_status="CONFIRMED",
                ),
                EvidenceItem(
                    id="evidence-legacy",
                    case_id="case-1",
                    event_id="event-legacy",
                    evidence_type="article",
                    source_type="rss",
                    title="Legacy evidence",
                    published_at="2026-03-08T00:00:00+00:00",
                    capture_metadata={},
                    verification_status="UNVERIFIED",
                ),
                EvidenceItem(
                    id="evidence-unverified",
                    case_id="case-1",
                    event_id="event-known",
                    evidence_type="article",
                    source_type="rss",
                    title="Unverified evidence",
                    published_at=None,
                    capture_metadata={},
                    verification_status="UNVERIFIED",
                ),
                EvidenceItem(
                    id="evidence-known",
                    case_id="case-1",
                    event_id="event-known",
                    evidence_type="article",
                    source_type="rss",
                    title="Known evidence",
                    published_at="2026-03-09T00:00:00+00:00",
                    capture_metadata={},
                    verification_status="CONFIRMED",
                ),
            ]
        )
        session.flush()
        # Plain SQL bypasses the ORM entirely: exactly what a legacy row or an
        # external writer leaves behind.
        session.execute(
            text("UPDATE events SET verification_status = :s WHERE id = 'event-legacy'"),
            {"s": LEGACY_EVENT_STATUS},
        )
        session.execute(
            text("UPDATE claims SET verification_status = :s WHERE id = 'claim-legacy'"),
            {"s": LEGACY_CLAIM_STATUS},
        )
        session.execute(
            text(
                "UPDATE evidence_items SET verification_status = :s "
                "WHERE id = 'evidence-legacy'"
            ),
            {"s": LEGACY_EVIDENCE_STATUS},
        )
        session.commit()
    finally:
        session.close()


def _stored_state() -> dict[str, list[tuple]]:
    """Every status value plus the case counts, read straight from SQLite."""
    session = get_database().get_session_sync()
    try:
        return {
            "events": [
                tuple(row)
                for row in session.execute(
                    text("SELECT id, verification_status FROM events ORDER BY id")
                )
            ],
            "claims": [
                tuple(row)
                for row in session.execute(
                    text("SELECT id, verification_status FROM claims ORDER BY id")
                )
            ],
            "evidence_items": [
                tuple(row)
                for row in session.execute(
                    text(
                        "SELECT id, verification_status FROM evidence_items ORDER BY id"
                    )
                )
            ],
            "case": [
                tuple(row)
                for row in session.execute(
                    text(
                        "SELECT event_count, open_review_items, updated_at "
                        "FROM topic_cases WHERE id = 'case-1'"
                    )
                )
            ],
        }
    finally:
        session.close()


@pytest.fixture()
def legacy_case(tmp_path: Path):
    service = _service(tmp_path)
    _seed_case(tmp_path)
    app.dependency_overrides[get_case_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_out_of_enum_status_keeps_every_case_read_available(legacy_case):
    client = legacy_case
    before = _stored_state()

    detail_response = client.get("/api/cases/case-1")
    timeline_response = client.get("/api/cases/case-1/timeline")
    claims_response = client.get("/api/cases/case-1/claims")
    evidence_response = client.get("/api/cases/case-1/evidence")

    for name, response in (
        ("detail", detail_response),
        ("timeline", timeline_response),
        ("claims", claims_response),
        ("evidence", evidence_response),
    ):
        assert response.status_code == 200, (name, response.text)

    # The raw stored values were only planted, never rewritten by the reads.
    assert _stored_state() == before
    assert before["events"] == [
        ("event-known", "CONFIRMED"),
        ("event-legacy", LEGACY_EVENT_STATUS),
    ]


def test_out_of_enum_status_carries_the_raw_value_on_the_timeline(legacy_case):
    timeline = legacy_case.get("/api/cases/case-1/timeline").json()
    by_id = {item["id"]: item for item in timeline}

    assert by_id["event-legacy"]["verificationStatus"] == "unknown"
    assert by_id["event-legacy"]["rawVerificationStatus"] == LEGACY_EVENT_STATUS
    # A recorded member keeps its mapping and carries no raw text.
    assert by_id["event-known"]["verificationStatus"] == "confirmed"
    assert by_id["event-known"]["rawVerificationStatus"] is None

    # The case detail timeline slice is the same DTO shape.
    detail = legacy_case.get("/api/cases/case-1").json()
    detail_by_id = {item["id"]: item for item in detail["tabs"]["timeline"]}
    assert detail_by_id["event-legacy"]["verificationStatus"] == "unknown"
    assert detail_by_id["event-legacy"]["rawVerificationStatus"] == LEGACY_EVENT_STATUS
    assert detail_by_id["event-known"]["rawVerificationStatus"] is None


def test_out_of_enum_status_carries_the_raw_value_on_evidence(legacy_case):
    evidence = legacy_case.get("/api/cases/case-1/evidence").json()
    by_id = {item["id"]: item for item in evidence}

    assert by_id["evidence-legacy"]["verificationStatus"] == "unknown"
    assert by_id["evidence-legacy"]["rawVerificationStatus"] == LEGACY_EVIDENCE_STATUS
    assert by_id["evidence-known"]["verificationStatus"] == "confirmed"
    assert by_id["evidence-known"]["rawVerificationStatus"] is None
    # ``UNVERIFIED`` is the evidence column's own default and maps to ``unknown``
    # deliberately, so it is a recognised value rather than an out-of-enum one.
    assert by_id["evidence-unverified"]["verificationStatus"] == "unknown"
    assert by_id["evidence-unverified"]["rawVerificationStatus"] is None


def test_claims_read_is_available_and_keeps_the_raw_claim_status(legacy_case):
    claims = legacy_case.get("/api/cases/case-1/claims").json()
    by_id = {item["id"]: item for item in claims}

    assert by_id["claim-legacy"]["verificationStatus"] == "unknown"
    assert by_id["claim-known"]["verificationStatus"] == "confirmed"


def test_invalid_verification_status_write_is_still_rejected(tmp_path: Path):
    """The lenient read must not relax the bind processor (write contract)."""
    _service(tmp_path)
    _seed_case(tmp_path)

    session = get_database().get_session_sync()
    try:
        event = session.execute(
            select(Event).where(Event.id == "event-known")
        ).scalars().one()
        # Not a member and not a string: ``Enum``'s bind validation still fires.
        event.verification_status = object()  # type: ignore[assignment]
        with pytest.raises(StatementError) as excinfo:
            session.flush()
        assert isinstance(excinfo.value.orig, LookupError)
    finally:
        session.rollback()
        session.close()

    assert dict(_stored_state()["events"])["event-known"] == "CONFIRMED"
