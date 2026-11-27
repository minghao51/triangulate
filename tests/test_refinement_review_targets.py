"""F05 — case-owned annotation targets and case-owned reader contracts.

Covers the refinement contract for review targets (contracts §9, R04):

* annotation targets must provably belong to the case; a missing target and a
  wrong-case target return the same uniform 422 (no existence leak),
* a missing case is a 404 at the HTTP route level for the annotation POST, the
  review-activity GET and the evaluation GET,
* the service readers keep raising ``ValueError`` for direct/CLI callers,
* a genuine (non-missing-case) reader failure is never masked as a 404,
* writer admission (409) still wins over target validation (422),
* narrative targets are accepted iff reachable via the case-scoped claims
  overview cluster association,
* an invalid target writes no annotation and no audit row.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.cases import TopicCaseService
from src.http.app import app
from src.http.dependencies import get_case_service
from src.storage import (
    CaseStatus,
    Claim,
    Event,
    EvidenceItem,
    Narrative,
    ReviewAnnotation,
    ReviewAuditEntry,
    TopicCase,
    VerificationStatus,
    claim_case_ownership,
    get_database,
    init_database,
    release_case_ownership,
)

CASE_A = "case-alpha"
CASE_B = "case-beta"
MISSING_CASE = "case-missing"

TARGET_TYPES = ["case", "claim", "evidence", "exception", "narrative"]

#: ``(target_type, target id owned by CASE_A, target id owned by CASE_B, ghost)``
TARGET_CASES = [
    ("case", CASE_A, CASE_B, "case-ghost"),
    ("claim", "claim-alpha", "claim-beta", "claim-ghost"),
    ("evidence", "evidence-alpha", "evidence-beta", "evidence-ghost"),
    ("exception", "exc-alpha", "exc-beta", "exc-ghost"),
    ("narrative", "narrative-alpha", "narrative-beta", "narrative-ghost"),
]


def _exception_item(exception_id: str) -> dict:
    return {
        "id": exception_id,
        "type": "needs_more_sources",
        "severity": "high",
        "stage": "RETRIEVE",
        "status": "open",
        "message": "Need more sources",
    }


def _seed_cases() -> None:
    """Two cases with one event/claim/evidence/narrative each, plus an orphan cluster."""
    session = get_database().get_session_sync()
    try:
        session.add(
            TopicCase(
                id=CASE_A,
                query="Alpha case",
                slug="alpha-case",
                status=CaseStatus.REVIEW_READY,
                metadata_json={"exception_queue": [_exception_item("exc-alpha")]},
            )
        )
        session.add(
            TopicCase(
                id=CASE_B,
                query="Beta case",
                slug="beta-case",
                status=CaseStatus.REVIEW_READY,
                metadata_json={"exception_queue": [_exception_item("exc-beta")]},
            )
        )
        for case_id in (CASE_A, CASE_B):
            session.add(
                Event(
                    id=f"event-{case_id}",
                    case_id=case_id,
                    timestamp=datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
                    title="Event",
                    summary="Summary",
                    verification_status=VerificationStatus.PROBABLE,
                )
            )
        session.add(
            Claim(
                id="claim-alpha",
                event_id=f"event-{CASE_A}",
                claim_text="Alpha claim",
                verification_status=VerificationStatus.PROBABLE,
                narrative_cluster_id="cluster-alpha",
            )
        )
        session.add(
            Claim(
                id="claim-beta",
                event_id=f"event-{CASE_B}",
                claim_text="Beta claim",
                verification_status=VerificationStatus.PROBABLE,
                narrative_cluster_id="cluster-beta",
            )
        )
        session.add(
            Narrative(
                id="narrative-alpha",
                cluster_id="cluster-alpha",
                stance_summary="Alpha narrative",
            )
        )
        session.add(
            Narrative(
                id="narrative-beta",
                cluster_id="cluster-beta",
                stance_summary="Beta narrative",
            )
        )
        session.add(
            Narrative(
                id="narrative-orphan",
                cluster_id="cluster-orphan",
                stance_summary="Cluster with no case-scoped claim",
            )
        )
        session.add(
            EvidenceItem(
                id="evidence-alpha",
                case_id=CASE_A,
                evidence_type="article",
                source_type="news",
            )
        )
        session.add(
            EvidenceItem(
                id="evidence-beta",
                case_id=CASE_B,
                evidence_type="article",
                source_type="news",
            )
        )
        session.commit()
    finally:
        session.close()


@pytest.fixture
def service(tmp_path: Path) -> TopicCaseService:
    init_database(str(tmp_path / "triangulate.db"))
    seeded = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
    _seed_cases()
    return seeded


def _post_annotation(service, case_id: str, **overrides):
    payload = {
        "targetType": "case",
        "targetId": case_id,
        "annotationType": "comment",
        "content": "Operator note",
    }
    payload.update(overrides)
    app.dependency_overrides[get_case_service] = lambda: service
    try:
        return TestClient(app).post(f"/api/cases/{case_id}/annotations", json=payload)
    finally:
        app.dependency_overrides.clear()


def _get(service, path: str, *, raise_server_exceptions: bool = True):
    app.dependency_overrides[get_case_service] = lambda: service
    try:
        client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
        return client.get(path)
    finally:
        app.dependency_overrides.clear()


def _annotation_audit_counts(case_id: str) -> tuple[int, int]:
    session = get_database().get_session_sync()
    try:
        annotations = session.scalars(
            select(ReviewAnnotation).where(ReviewAnnotation.case_id == case_id)
        ).all()
        audit_entries = session.scalars(
            select(ReviewAuditEntry).where(ReviewAuditEntry.case_id == case_id)
        ).all()
        return len(annotations), len(audit_entries)
    finally:
        session.close()


def _case_owner(case_id: str) -> tuple[str | None, str | None]:
    session = get_database().get_session_sync()
    try:
        row = session.get(TopicCase, case_id)
        assert row is not None
        return row.owner_token, row.owner_kind
    finally:
        session.close()


# ---------------------------------------------------------------------------
# AC1/AC6 — uniform 422 parity, membership, and the narrative reachability rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target_type", "owned_id", "wrong_case_id", "ghost_id"), TARGET_CASES
)
def test_annotation_target_membership_and_422_parity(
    service, target_type, owned_id, wrong_case_id, ghost_id
):
    accepted = _post_annotation(service, CASE_A, targetType=target_type, targetId=owned_id)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["targetId"] == owned_id

    wrong_case = _post_annotation(
        service, CASE_A, targetType=target_type, targetId=wrong_case_id
    )
    missing = _post_annotation(
        service, CASE_A, targetType=target_type, targetId=ghost_id
    )

    assert wrong_case.status_code == 422
    assert missing.status_code == 422
    # Byte-equivalent bodies: the response cannot reveal whether the id exists.
    assert wrong_case.content == missing.content
    assert wrong_case.json() == missing.json()


def test_annotation_missing_case_target_id_is_422_for_case_type(service):
    response = _post_annotation(service, CASE_A, targetType="case", targetId="case-ghost")

    assert response.status_code == 422
    assert response.json()["detail"] == f"Annotation target is not part of case {CASE_A}"


def test_narrative_target_rejected_when_cluster_unreachable_in_case(service):
    """A stored narrative whose cluster has no case-scoped claim is unprovable."""
    response = _post_annotation(
        service, CASE_A, targetType="narrative", targetId="narrative-orphan"
    )

    assert response.status_code == 422
    assert response.json()["detail"] == f"Annotation target is not part of case {CASE_A}"


def test_wrong_case_claim_target_is_rejected_for_direct_callers(service):
    with pytest.raises(ValueError, match="is not part of case"):
        service.add_review_annotation(
            CASE_A,
            target_type="claim",
            target_id="claim-beta",
            annotation_type="comment",
            content="Operator note",
        )


# ---------------------------------------------------------------------------
# AC2 — missing case is a 404 at the HTTP route level
# ---------------------------------------------------------------------------


def test_annotation_post_missing_case_returns_404(service):
    response = _post_annotation(service, MISSING_CASE, targetType="case")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Case {MISSING_CASE} not found"
    assert _annotation_audit_counts(MISSING_CASE) == (0, 0)


def test_review_activity_missing_case_returns_404(service):
    response = _get(service, f"/api/cases/{MISSING_CASE}/review-activity")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Case {MISSING_CASE} not found"


def test_evaluation_missing_case_returns_404(service):
    response = _get(service, f"/api/cases/{MISSING_CASE}/evaluation")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Case {MISSING_CASE} not found"


# ---------------------------------------------------------------------------
# AC3 — the service readers keep raising ValueError for direct callers
# ---------------------------------------------------------------------------


def test_service_readers_still_raise_value_error_for_direct_callers(service):
    with pytest.raises(ValueError):
        service.get_case_review_activity(MISSING_CASE)
    with pytest.raises(ValueError):
        service.get_case_evaluation_summary(MISSING_CASE)


def test_service_annotation_write_missing_case_still_raises_value_error(service):
    with pytest.raises(ValueError, match=f"Case {MISSING_CASE} not found"):
        service.add_review_annotation(
            MISSING_CASE,
            target_type="case",
            target_id=MISSING_CASE,
            annotation_type="comment",
            content="Operator note",
        )


# ---------------------------------------------------------------------------
# AC4 — only a missing-case failure maps to 404; genuine read faults do not
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("router_attr", "path"),
    [
        ("get_case_review_activity", "review-activity"),
        ("get_case_evaluation_summary", "evaluation"),
    ],
)
@pytest.mark.parametrize(
    "failure",
    [RuntimeError("evaluation store unavailable"), ValueError("database is locked")],
    ids=["runtime-error", "non-missing-value-error"],
)
def test_genuine_reader_failure_is_not_masked_as_404(
    service, monkeypatch, router_attr, path, failure
):
    def _fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(service, router_attr, _fail)

    response = _get(
        service, f"/api/cases/{CASE_A}/{path}", raise_server_exceptions=False
    )

    assert response.status_code not in (200, 404)


# ---------------------------------------------------------------------------
# AC5 — writer admission (409) is decided before target validation (422)
# ---------------------------------------------------------------------------


def test_writer_conflict_wins_over_invalid_target(service):
    token = "test-owner-token"
    session = get_database().get_session_sync()
    try:
        claim_case_ownership(session, CASE_A, token=token, kind="run", ref_id="run-conflict")
        session.commit()
    finally:
        session.close()

    try:
        response = _post_annotation(
            service, CASE_A, targetType="claim", targetId="claim-beta"
        )
    finally:
        session = get_database().get_session_sync()
        try:
            release_case_ownership(session, CASE_A, token)
            session.commit()
        finally:
            session.close()

    assert response.status_code == 409
    assert "currently owned" in response.json()["detail"]
    assert _annotation_audit_counts(CASE_A) == (0, 0)


# ---------------------------------------------------------------------------
# AC7 — an invalid target writes no annotation and no audit row
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target_type", "target_id"),
    [
        ("case", "case-ghost"),
        ("claim", "claim-beta"),
        ("claim", "claim-ghost"),
        ("evidence", "evidence-beta"),
        ("exception", "exc-ghost"),
        ("narrative", "narrative-beta"),
        ("narrative", "narrative-orphan"),
        ("narrative", "narrative-ghost"),
    ],
)
def test_invalid_target_writes_no_annotation_and_no_audit_row(
    service, target_type, target_id
):
    before = _annotation_audit_counts(CASE_A)

    response = _post_annotation(service, CASE_A, targetType=target_type, targetId=target_id)

    assert response.status_code == 422
    assert _annotation_audit_counts(CASE_A) == before
    # The rejected write must not leave the case claimed by a dead writer.
    assert _case_owner(CASE_A) == (None, None)
