"""P02: deterministic two-capture comparison read API (specification §6).

All databases, captures and claims are synthetic. No model, network or source
capture call is made; every read is local and deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.cases.comparison import (
    ComparisonInvalid,
    ComparisonNotFound,
    read_comparison,
)
from src.cases.service import TopicCaseService, _claim_signature
from src.http.app import app
from src.http.dependencies import get_case_service
from src.storage import (
    CaseStatus,
    Claim,
    ClaimEvidenceLink,
    EvidenceCapture,
    EvidenceItem,
    Event,
    FactAllegationType,
    TopicCase,
    VerificationStatus,
    get_database,
    init_database,
)
from src.storage.captures import record_evidence_capture

CASE_ID = "case-p02"
OTHER_CASE_ID = "case-p02-other"
EVENT_ID = "event-p02"
OTHER_EVENT_ID = "event-p02-other"

SHARED_TEXT = "The authority ordered an evacuation."
LEFT_TEXT = "Shelters opened before dawn."
RIGHT_TEXT = "The agency denied the evacuation order."
CONTRA_TEXT = "The evacuation began at 06:00 local time."
OLD_TEXT = "A claim extracted from the revised capture."

FILLER = (
    "Port Alden reporting continued through the morning with officials "
    "answering questions about shelters, transit and the harbour. "
) * 6
SHARED_BODY = f"{SHARED_TEXT} {LEFT_TEXT} {RIGHT_TEXT} {CONTRA_TEXT} {FILLER}"
OLD_BODY_OLD = f"{OLD_TEXT} Old capture context. {FILLER}"
OLD_BODY_CURRENT = f"{OLD_TEXT} Revised capture context. {FILLER}"


def db_session():
    return get_database().get_session_sync()


def _span(body: str, quote: str) -> tuple[int, int]:
    start = body.index(quote)
    return start, start + len(quote)


def _add_case(session, case_id: str, query: str) -> None:
    session.add(
        TopicCase(
            id=case_id,
            query=query,
            slug=f"{case_id}-slug",
            conflict="Civic response",
            status=CaseStatus.REVIEW_READY,
            metadata_json={},
        )
    )


def _add_claim(session, claim_id: str, event_id: str, text: str) -> Claim:
    claim = Claim(
        id=claim_id,
        event_id=event_id,
        claim_text=text,
        verification_status=VerificationStatus.ALLEGED,
        fact_allegation_type=FactAllegationType.ALLEGATION,
        claim_signature=_claim_signature(text),
    )
    session.add(claim)
    return claim


def _add_evidence(
    session,
    *,
    evidence_id: str,
    case_id: str,
    event_id: str,
    publisher: str,
    body: str,
    extraction: dict | None = None,
) -> tuple[EvidenceItem, EvidenceCapture]:
    evidence = EvidenceItem(
        id=evidence_id,
        case_id=case_id,
        event_id=event_id,
        evidence_type="article",
        source_type="rss",
        title=f"Source {evidence_id}",
        origin_url=f"https://{evidence_id}.example.com/story",
        canonical_url=f"https://{evidence_id}.example.com/story",
        publisher=publisher,
        capture_metadata={},
        verification_status="UNVERIFIED",
        credibility_tier="unknown",
        requires_human_review=0,
    )
    session.add(evidence)
    session.flush()
    capture = record_evidence_capture(
        session,
        evidence,
        text=body,
        observed_at=datetime(2026, 3, 3, 6, 25, tzinfo=UTC),
        metadata={"extraction": extraction} if extraction else {},
    )
    assert capture is not None
    return evidence, capture


def _link(
    session,
    *,
    link_id: str,
    claim: Claim,
    evidence: EvidenceItem,
    capture: EvidenceCapture,
    body: str,
    quote: str,
    relation: str = "reported_by",
    alignment: str = "exact",
    assessment_origin: str | None = "collector",
    assessment_version: str | None = "v1",
) -> ClaimEvidenceLink:
    start, end = _span(body, quote)
    link = ClaimEvidenceLink(
        id=link_id,
        claim_id=claim.id,
        evidence_id=evidence.id,
        relation=relation,
        source_diversity_rank=1,
        confidence_score=None,
        capture_id=capture.id,
        alignment_status=alignment,
        quote=quote if alignment == "exact" else None,
        start_char=start if alignment == "exact" else None,
        end_char=end if alignment == "exact" else None,
        assessment_origin=assessment_origin,
        assessment_version=assessment_version,
        assessment_metadata={},
    )
    session.add(link)
    session.flush()
    return link


@pytest.fixture
def workbench(tmp_path):
    init_database(str(tmp_path / "p02-comparison.sqlite3"))
    session = db_session()
    try:
        _add_case(session, CASE_ID, "Port Alden evacuation comparison")
        _add_case(session, OTHER_CASE_ID, "Other case")
        session.add(
            Event(
                id=EVENT_ID,
                timestamp=datetime(2026, 3, 3, 6, 30, tzinfo=UTC),
                title="Port Alden briefing",
                verification_status=VerificationStatus.ALLEGED,
                case_id=CASE_ID,
            )
        )
        session.add(
            Event(
                id=OTHER_EVENT_ID,
                timestamp=datetime(2026, 3, 3, 7, 0, tzinfo=UTC),
                title="Other event",
                verification_status=VerificationStatus.ALLEGED,
                case_id=OTHER_CASE_ID,
            )
        )
        session.flush()

        shared = _add_claim(session, "claim-p02-shared", EVENT_ID, SHARED_TEXT)
        left_only = _add_claim(session, "claim-p02-left", EVENT_ID, LEFT_TEXT)
        right_only = _add_claim(session, "claim-p02-right", EVENT_ID, RIGHT_TEXT)
        contra = _add_claim(session, "claim-p02-contra", EVENT_ID, CONTRA_TEXT)
        old = _add_claim(session, "claim-p02-old", EVENT_ID, OLD_TEXT)
        foreign = _add_claim(
            session, "claim-p02-foreign", OTHER_EVENT_ID, "Another case assertion."
        )
        session.flush()

        left_evidence, left_capture = _add_evidence(
            session,
            evidence_id="ev-p02-left",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Meridian Wire",
            body=SHARED_BODY,
            extraction={
                "status": "valid",
                "scope_start": 0,
                "scope_end": 200,
                "body_char_count": len(SHARED_BODY),
                "input_limit": 20000,
                "source_available": True,
            },
        )
        right_evidence, right_capture = _add_evidence(
            session,
            evidence_id="ev-p02-right",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Northern Post",
            body=SHARED_BODY,
        )
        old_evidence, old_capture = _add_evidence(
            session,
            evidence_id="ev-p02-old",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Old Wire",
            body=OLD_BODY_OLD,
        )
        current_capture = record_evidence_capture(
            session,
            old_evidence,
            text=OLD_BODY_CURRENT,
            observed_at=datetime(2026, 3, 4, 8, 15, tzinfo=UTC),
        )
        other_evidence, other_capture = _add_evidence(
            session,
            evidence_id="ev-p02-other",
            case_id=OTHER_CASE_ID,
            event_id=OTHER_EVENT_ID,
            publisher="Other Wire",
            body=f"Other case body. {FILLER}",
        )
        assert current_capture is not None

        _link(
            session,
            link_id="link-shared-left",
            claim=shared,
            evidence=left_evidence,
            capture=left_capture,
            body=SHARED_BODY,
            quote=SHARED_TEXT,
        )
        _link(
            session,
            link_id="link-shared-right",
            claim=shared,
            evidence=right_evidence,
            capture=right_capture,
            body=SHARED_BODY,
            quote=SHARED_TEXT,
        )
        _link(
            session,
            link_id="link-left",
            claim=left_only,
            evidence=left_evidence,
            capture=left_capture,
            body=SHARED_BODY,
            quote=LEFT_TEXT,
        )
        _link(
            session,
            link_id="link-right",
            claim=right_only,
            evidence=right_evidence,
            capture=right_capture,
            body=SHARED_BODY,
            quote=RIGHT_TEXT,
        )
        _link(
            session,
            link_id="link-contra-left",
            claim=contra,
            evidence=left_evidence,
            capture=left_capture,
            body=SHARED_BODY,
            quote=CONTRA_TEXT,
            relation="contradicts",
            assessment_origin="human",
            assessment_version="v1",
        )
        _link(
            session,
            link_id="link-contra-right",
            claim=contra,
            evidence=right_evidence,
            capture=right_capture,
            body=SHARED_BODY,
            quote=CONTRA_TEXT,
            relation="reported_by",
        )
        _link(
            session,
            link_id="link-old-current",
            claim=old,
            evidence=old_evidence,
            capture=current_capture,
            body=OLD_BODY_CURRENT,
            quote=OLD_TEXT,
        )
        # A link from another case must never be attributed to this comparison.
        _link(
            session,
            link_id="link-foreign",
            claim=foreign,
            evidence=left_evidence,
            capture=left_capture,
            body=SHARED_BODY,
            quote=SHARED_TEXT,
        )
        # A legacy link with no capture is recorded but cannot be attributed.
        legacy = _add_claim(
            session, "claim-p02-legacy", EVENT_ID, "A legacy assertion."
        )
        session.flush()
        session.add(
            ClaimEvidenceLink(
                id="link-legacy",
                claim_id=legacy.id,
                evidence_id=old_evidence.id,
                relation="reported_by",
                source_diversity_rank=1,
                confidence_score=None,
                capture_id=None,
                alignment_status="not_provided",
                assessment_metadata={},
            )
        )
        session.commit()
        return {
            "left_evidence": left_evidence.id,
            "right_evidence": right_evidence.id,
            "old_evidence": old_evidence.id,
            "other_evidence": other_evidence.id,
            "left_capture": left_capture.id,
            "right_capture": right_capture.id,
            "old_capture": old_capture.id,
            "current_capture": current_capture.id,
            "other_capture": other_capture.id,
            "left_body": SHARED_BODY,
        }
    finally:
        session.close()


def _row(comparison: dict, claim_text: str) -> dict:
    for row in comparison["claims"]["rows"]:
        if row["claim_text"] == claim_text:
            return row
    raise AssertionError(f"row {claim_text!r} not found")


class TestComparisonReadModel:
    def test_shared_left_right_and_explicit_contradiction(self, workbench):
        session = db_session()
        try:
            comparison = read_comparison(
                session,
                case_id=CASE_ID,
                left_evidence_id=workbench["left_evidence"],
                right_evidence_id=workbench["right_evidence"],
            )
        finally:
            session.close()

        assert comparison["left_capture_id"] == workbench["left_capture"]
        assert comparison["right_capture_id"] == workbench["right_capture"]
        assert comparison["claims"]["total"] == 4

        shared = _row(comparison, SHARED_TEXT)
        assert shared["status"] == "shared"
        assert shared["left"]["claim_signature"] == shared["right"]["claim_signature"]
        assert shared["left"]["passages"][0]["quote"] == SHARED_TEXT
        assert shared["right"]["passages"][0]["quote"] == SHARED_TEXT
        assert shared["left"]["passages"][0]["capture_id"] == workbench["left_capture"]
        assert shared["right"]["passages"][0]["capture_id"] == workbench["right_capture"]
        assert shared["contradiction"]["explicit"] is False
        assert shared["contradiction"]["conflict"] is False

        left_only = _row(comparison, LEFT_TEXT)
        assert left_only["status"] == "left_only"
        assert left_only["right"] is None
        assert left_only["caveat"]
        assert left_only["contradiction"]["explicit"] is False

        right_only = _row(comparison, RIGHT_TEXT)
        assert right_only["status"] == "right_only"
        assert right_only["left"] is None
        assert right_only["caveat"]

        contra = _row(comparison, CONTRA_TEXT)
        assert contra["status"] == "shared"
        assert contra["contradiction"]["explicit"] is True
        assert contra["contradiction"]["conflict"] is True
        assert contra["contradiction"]["left_relationships"] == ["contradicts"]
        assert contra["contradiction"]["right_relationships"] == ["reported_by"]

        # Copy warning comes from the identical long capture text.
        assert comparison["dependency"]["detected"] is True
        assert comparison["dependency"]["copy_detected"] is True
        assert "identical_normalized_capture" in comparison["dependency"]["reasons"]
        assert "not independent" in comparison["dependency"]["message"]

        # Extraction scope is exposed per side; no text body is inlined.
        assert comparison["left"]["analysis_scope"]["status"] == "valid"
        assert comparison["left"]["analysis_scope"]["end_char"] == 200
        assert comparison["left"]["coverage"]["attributed_claim_count"] == 3
        assert comparison["right"]["coverage"]["attributed_claim_count"] == 3
        assert workbench["left_body"] not in json.dumps(comparison)

    def test_pagination_is_deterministic_and_stable(self, workbench):
        session = db_session()
        try:
            first = read_comparison(
                session,
                case_id=CASE_ID,
                left_evidence_id=workbench["left_evidence"],
                right_evidence_id=workbench["right_evidence"],
                limit=2,
                offset=0,
            )
            second = read_comparison(
                session,
                case_id=CASE_ID,
                left_evidence_id=workbench["left_evidence"],
                right_evidence_id=workbench["right_evidence"],
                limit=2,
                offset=2,
            )
            repeat = read_comparison(
                session,
                case_id=CASE_ID,
                left_evidence_id=workbench["left_evidence"],
                right_evidence_id=workbench["right_evidence"],
                limit=2,
                offset=0,
            )
        finally:
            session.close()
        assert first["claims"]["total"] == 4
        assert len(first["claims"]["rows"]) == 2
        assert first["claims"]["has_more"] is True
        assert len(second["claims"]["rows"]) == 2
        assert second["claims"]["has_more"] is False
        assert first == repeat
        signatures = [
            row["claim_signature"]
            for row in first["claims"]["rows"] + second["claims"]["rows"]
        ]
        assert signatures == sorted(signatures)
        assert len(set(signatures)) == 4

    def test_old_capture_never_substitutes_current_links(self, workbench):
        session = db_session()
        try:
            historical = read_comparison(
                session,
                case_id=CASE_ID,
                left_evidence_id=workbench["left_evidence"],
                right_evidence_id=workbench["old_evidence"],
                right_capture_id=workbench["old_capture"],
            )
            current = read_comparison(
                session,
                case_id=CASE_ID,
                left_evidence_id=workbench["left_evidence"],
                right_evidence_id=workbench["old_evidence"],
            )
        finally:
            session.close()

        historical_right = historical["right"]
        assert historical_right["capture_id"] == workbench["old_capture"]
        assert historical_right["coverage"]["claim_linkage_status"] == "historical_unavailable"
        assert historical_right["coverage"]["historical_analysis_available"] is False
        assert historical_right["coverage"]["attributed_claim_count"] == 0
        assert historical_right["coverage"]["other_capture_link_count"] >= 1
        assert "not substituted" in historical_right["coverage"]["caveat"]
        all_texts = {
            row["claim_text"] for row in historical["claims"]["rows"]
        }
        assert OLD_TEXT not in all_texts

        assert current["right"]["capture_id"] == workbench["current_capture"]
        assert current["right"]["coverage"]["attributed_claim_count"] == 1
        assert _row(current, OLD_TEXT)["right"] is not None

    def test_legacy_unattributed_links_are_not_attributed(self, workbench):
        session = db_session()
        try:
            comparison = read_comparison(
                session,
                case_id=CASE_ID,
                left_evidence_id=workbench["left_evidence"],
                right_evidence_id=workbench["old_evidence"],
                right_capture_id=workbench["current_capture"],
            )
        finally:
            session.close()
        right = comparison["right"]
        assert right["coverage"]["unattributed_link_count"] == 1
        assert right["coverage"]["attributed_claim_count"] == 1
        assert "excluded" in right["coverage"]["caveat"]

    def test_validation_and_ownership(self, workbench):
        session = db_session()
        try:
            with pytest.raises(ComparisonInvalid):
                read_comparison(
                    session,
                    case_id=CASE_ID,
                    left_evidence_id=workbench["left_evidence"],
                    right_evidence_id=workbench["left_evidence"],
                )
            with pytest.raises(ComparisonNotFound):
                read_comparison(
                    session,
                    case_id=CASE_ID,
                    left_evidence_id=workbench["left_evidence"],
                    right_evidence_id=workbench["other_evidence"],
                )
            with pytest.raises(ComparisonNotFound):
                read_comparison(
                    session,
                    case_id="missing",
                    left_evidence_id=workbench["left_evidence"],
                    right_evidence_id=workbench["right_evidence"],
                )
            with pytest.raises(ComparisonNotFound):
                read_comparison(
                    session,
                    case_id=CASE_ID,
                    left_evidence_id=workbench["left_evidence"],
                    right_evidence_id=workbench["right_evidence"],
                    right_capture_id=workbench["other_capture"],
                )
            with pytest.raises(ComparisonInvalid):
                read_comparison(
                    session,
                    case_id=CASE_ID,
                    left_evidence_id=workbench["left_evidence"],
                    right_evidence_id=workbench["right_evidence"],
                    limit=101,
                )
        finally:
            session.close()

    def test_reads_do_not_mutate(self, workbench):
        session = db_session()
        try:
            before = (
                session.scalar(select(func.count()).select_from(EvidenceCapture)),
                session.scalar(select(func.count()).select_from(ClaimEvidenceLink)),
                session.scalar(select(func.count()).select_from(Claim)),
            )
            read_comparison(
                session,
                case_id=CASE_ID,
                left_evidence_id=workbench["left_evidence"],
                right_evidence_id=workbench["right_evidence"],
            )
            after = (
                session.scalar(select(func.count()).select_from(EvidenceCapture)),
                session.scalar(select(func.count()).select_from(ClaimEvidenceLink)),
                session.scalar(select(func.count()).select_from(Claim)),
            )
        finally:
            session.close()
        assert before == after


@pytest.fixture
def client(workbench, tmp_path):
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
    app.dependency_overrides[get_case_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


class TestComparisonHttpContract:
    def test_comparison_contract_and_default_captures(self, client, workbench):
        response = client.get(
            f"/api/cases/{CASE_ID}/comparison",
            params={
                "left": workbench["left_evidence"],
                "right": workbench["right_evidence"],
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["caseId"] == CASE_ID
        assert payload["leftCaptureId"] == workbench["left_capture"]
        assert payload["rightCaptureId"] == workbench["right_capture"]
        assert payload["left"]["captureId"] == workbench["left_capture"]
        assert payload["claims"]["total"] == 4
        assert payload["claims"]["limit"] == 25
        assert payload["claims"]["offset"] == 0
        assert payload["claims"]["hasMore"] is False
        assert payload["dependency"]["copyDetected"] is True
        assert payload["policy"]["version"] == "comparison-read-policy-v1"
        row = payload["claims"]["rows"][0]
        assert "claimSignature" in row
        assert "contradiction" in row
        assert "analysisScope" in payload["left"]
        assert "coverage" in payload["left"]

    def test_query_validation_and_snapshot_rejection(self, client, workbench):
        same = client.get(
            f"/api/cases/{CASE_ID}/comparison",
            params={
                "left": workbench["left_evidence"],
                "right": workbench["left_evidence"],
            },
        )
        assert same.status_code == 422

        snapshot = client.get(
            f"/api/cases/{CASE_ID}/comparison",
            params={
                "left": workbench["left_evidence"],
                "right": workbench["right_evidence"],
                "snapshotId": "snap-1",
            },
        )
        assert snapshot.status_code == 422

        bad_limit = client.get(
            f"/api/cases/{CASE_ID}/comparison",
            params={
                "left": workbench["left_evidence"],
                "right": workbench["right_evidence"],
                "limit": 101,
            },
        )
        assert bad_limit.status_code == 422

        missing = client.get(
            f"/api/cases/{CASE_ID}/comparison",
            params={"left": workbench["left_evidence"]},
        )
        assert missing.status_code == 422

        wrong_case = client.get(
            f"/api/cases/{CASE_ID}/comparison",
            params={
                "left": workbench["left_evidence"],
                "right": workbench["other_evidence"],
            },
        )
        assert wrong_case.status_code == 404

        wrong_capture = client.get(
            f"/api/cases/{CASE_ID}/comparison",
            params={
                "left": workbench["left_evidence"],
                "right": workbench["right_evidence"],
                "rightCapture": workbench["other_capture"],
            },
        )
        assert wrong_capture.status_code == 404

    def test_pagination_params_and_no_mutation_route(self, client, workbench):
        page = client.get(
            f"/api/cases/{CASE_ID}/comparison",
            params={
                "left": workbench["left_evidence"],
                "right": workbench["right_evidence"],
                "limit": 1,
                "offset": 1,
            },
        )
        assert page.status_code == 200
        assert page.json()["claims"]["limit"] == 1
        assert page.json()["claims"]["offset"] == 1
        assert len(page.json()["claims"]["rows"]) == 1
        assert page.json()["claims"]["hasMore"] is True

        for method in ("post", "put", "patch", "delete"):
            response = getattr(client, method)(
                f"/api/cases/{CASE_ID}/comparison",
                params={
                    "left": workbench["left_evidence"],
                    "right": workbench["right_evidence"],
                },
            )
            assert response.status_code in {404, 405}
