"""F17 / X01: ad-hoc snapshot comparison read API.

Every fixture is synthetic. Snapshots are published through the real
``compose_case_snapshot`` projection, then the live rows are changed to produce a
genuine baseline/target pair. No model, network, report or index call is made.

The endpoint is an *additive read*: one case, two explicit immutable snapshot ids,
strictly chronological by owning run sequence, an ``ad_hoc`` DTO distinct from
recorded run changes and zero writes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from src.cases import snapshot_comparison as comparison_module
from src.cases.history import (
    SNAPSHOT_IDENTITY_VERSION,
    SNAPSHOT_POLICY_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    compose_case_snapshot,
    semantic_hash_for_payload,
)
from src.cases.service import _claim_signature
from src.http.app import (
    SNAPSHOT_COMPARISON_NOT_FOUND_DETAIL,
    SNAPSHOT_COMPARISON_THIRD_CONTEXT_DETAIL,
    app,
)
from src.storage import (
    CaseSnapshot,
    CaseStatus,
    Claim,
    ClaimEvidenceLink,
    Event,
    EvidenceItem,
    FactAllegationType,
    InvestigationCoverage,
    InvestigationRun,
    InvestigationRunStatus,
    InvestigationRunTrigger,
    TopicCase,
    VerificationStatus,
    get_database,
    init_database,
)
from src.storage.captures import record_evidence_capture
from src.storage.models import Base

CASE_ID = "case-f17"
OTHER_CASE_ID = "case-f17-other"
EVENT_ID = "event-f17"
OTHER_EVENT_ID = "event-f17-other"
RUN_BASELINE_ID = "run-f17-baseline"
RUN_TARGET_ID = "run-f17-target"
SNAPSHOT_BASELINE_ID = "snapshot-f17-baseline"
SNAPSHOT_TARGET_ID = "snapshot-f17-target"
OTHER_SNAPSHOT_ID = "snapshot-f17-other"
CLAIM_CHANGED_ID = "claim-f17-changed"
CLAIM_ABSENT_ID = "claim-f17-absent"
CLAIM_ADDED_ID = "claim-f17-added"
EVIDENCE_ID = "evidence-f17"
LINK_ID = "link-f17"

ORIGINAL_CLAIM_TEXT = "The council approved the harbour plan."
UPDATED_CLAIM_TEXT = "The council approved the harbour plan with amendments."
ABSENT_CLAIM_TEXT = "The council postponed the harbour plan."
ADDED_CLAIM_TEXT = "A claim that only exists in the later observation."
CAPTURE_BODY = (
    "The council approved the harbour plan with amendments. Port Alden reporting "
    "continued through the morning with officials answering questions about the "
    "harbour, shelters and transit."
)

DTO_FIELDS = {
    "mode",
    "comparisonPolicyVersion",
    "baselineSnapshotId",
    "targetSnapshotId",
    "baselineRunId",
    "targetRunId",
    "baselineCoverage",
    "targetCoverage",
    "baselineMetadata",
    "targetMetadata",
    "availability",
    "unavailableReason",
    "items",
    "total",
    "limit",
    "offset",
    "hasMore",
}
METADATA_FIELDS = {
    "sequence",
    "createdAt",
    "schemaVersion",
    "identityVersion",
    "policyVersion",
}
ITEM_FIELDS = {
    "entityType",
    "entityId",
    "changeKind",
    "changedFields",
    "before",
    "after",
    "refs",
}
REF_FIELDS = {"snapshotId", "claimId", "evidenceId", "captureId", "citationId"}


def _db_path(tmp_path: Path) -> Path:
    return tmp_path / "f17.sqlite3"


def db_session():
    return get_database().get_session_sync()


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


def _add_event(session, event_id: str, case_id: str) -> None:
    session.add(
        Event(
            id=event_id,
            timestamp=datetime(2026, 3, 3, 6, 30, tzinfo=UTC),
            title=f"Event {event_id}",
            verification_status=VerificationStatus.ALLEGED,
            case_id=case_id,
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
        party_positions={"Alpha": "disputes"},
        support_count=1,
        oppose_count=0,
        source_diversity_count=1,
    )
    session.add(claim)
    return claim


def _add_evidence_with_capture(session):
    evidence = EvidenceItem(
        id=EVIDENCE_ID,
        case_id=CASE_ID,
        event_id=EVENT_ID,
        evidence_type="article",
        source_type="rss",
        title="Source evidence",
        origin_url="https://evidence-f17.example.com/story",
        canonical_url="https://evidence-f17.example.com/story",
        publisher="Meridian Wire",
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
        text=CAPTURE_BODY,
        observed_at=datetime(2026, 3, 3, 6, 25, tzinfo=UTC),
    )
    assert capture is not None
    return evidence, capture


def seed(tmp_path: Path) -> None:
    """Seed one case (plus a foreign case) and publish the baseline snapshot."""
    init_database(str(_db_path(tmp_path)))
    session = db_session()
    try:
        _add_case(session, CASE_ID, "Port Alden harbour plan")
        _add_case(session, OTHER_CASE_ID, "Another case")
        _add_event(session, EVENT_ID, CASE_ID)
        _add_event(session, OTHER_EVENT_ID, OTHER_CASE_ID)
        session.flush()

        _add_claim(session, CLAIM_CHANGED_ID, EVENT_ID, ORIGINAL_CLAIM_TEXT)
        _add_claim(session, CLAIM_ABSENT_ID, EVENT_ID, ABSENT_CLAIM_TEXT)
        session.flush()

        evidence, capture = _add_evidence_with_capture(session)
        quote = "The council approved the harbour plan"
        start = CAPTURE_BODY.index(quote)
        session.add(
            ClaimEvidenceLink(
                id=LINK_ID,
                claim_id=CLAIM_ABSENT_ID,
                evidence_id=evidence.id,
                relation="reported_by",
                source_diversity_rank=1,
                capture_id=capture.id,
                alignment_status="exact",
                quote=quote,
                start_char=start,
                end_char=start + len(quote),
                assessment_origin="collector",
                assessment_version="v1",
                assessment_metadata={},
            )
        )
        session.commit()
    finally:
        session.close()

    publish_snapshot(
        tmp_path,
        run_id=RUN_BASELINE_ID,
        snapshot_id=SNAPSHOT_BASELINE_ID,
        sequence=1,
        trigger=InvestigationRunTrigger.INITIAL,
    )
    mutate_live_rows(tmp_path)
    publish_snapshot(
        tmp_path,
        run_id=RUN_TARGET_ID,
        snapshot_id=SNAPSHOT_TARGET_ID,
        sequence=2,
        trigger=InvestigationRunTrigger.RERUN,
    )


def publish_snapshot(
    tmp_path: Path,
    *,
    run_id: str,
    snapshot_id: str,
    sequence: int,
    trigger: InvestigationRunTrigger = InvestigationRunTrigger.RERUN,
    case_id: str = CASE_ID,
) -> None:
    session = db_session()
    try:
        session.add(
            InvestigationRun(
                id=run_id,
                case_id=case_id,
                sequence=sequence,
                trigger=trigger,
                parameter_snapshot={},
                status=InvestigationRunStatus.SUCCEEDED,
                coverage=InvestigationCoverage.COMPLETE_REQUESTED_SCOPE,
                coverage_details={},
            )
        )
        session.flush()
        composed = compose_case_snapshot(session, case_id=case_id)
        payload = json.loads(json.dumps(composed["payload"], default=str))
        session.add(
            CaseSnapshot(
                id=snapshot_id,
                case_id=case_id,
                investigation_run_id=run_id,
                baseline_snapshot_id=None,
                schema_version=SNAPSHOT_SCHEMA_VERSION,
                identity_version=SNAPSHOT_IDENTITY_VERSION,
                policy_version=SNAPSHOT_POLICY_VERSION,
                semantic_hash=composed["semanticHash"],
                payload_json=payload,
                delta_json={"availability": "initial", "changes": []},
            )
        )
        session.commit()
    finally:
        session.close()


def mutate_live_rows(tmp_path: Path) -> None:
    """Change the live case between the two observations."""
    session = db_session()
    try:
        changed = session.get(Claim, CLAIM_CHANGED_ID)
        assert changed is not None
        changed.claim_text = UPDATED_CLAIM_TEXT
        changed.claim_signature = _claim_signature(UPDATED_CLAIM_TEXT)
        absent = session.get(Claim, CLAIM_ABSENT_ID)
        assert absent is not None
        _add_claim(session, CLAIM_ADDED_ID, EVENT_ID, ADDED_CLAIM_TEXT)
        session.flush()
        session.delete(absent)
        session.commit()
    finally:
        session.close()


def other_case_snapshot(tmp_path: Path) -> None:
    publish_snapshot(
        tmp_path,
        run_id="run-f17-other",
        snapshot_id=OTHER_SNAPSHOT_ID,
        sequence=9,
        case_id=OTHER_CASE_ID,
    )


@pytest.fixture()
def client(tmp_path: Path):
    seed(tmp_path)
    other_case_snapshot(tmp_path)
    # The app's canonical read path is startup-captured, so bind this test's
    # disposable database explicitly instead of relying on the global binding.
    app.state.database_path = _db_path(tmp_path)
    with TestClient(app) as test_client:
        yield test_client


def comparison_url(case_id: str = CASE_ID, **params: object) -> str:
    query = "&".join(
        f"{key}={value}" for key, value in params.items() if value is not None
    )
    base = f"/api/cases/{case_id}/snapshot-comparison"
    return f"{base}?{query}" if query else base


def get_comparison(
    client: TestClient,
    *,
    baseline: str = SNAPSHOT_BASELINE_ID,
    target: str = SNAPSHOT_TARGET_ID,
    limit: int | None = None,
    offset: int | None = None,
    case_id: str = CASE_ID,
):
    params: dict[str, object] = {"baseline": baseline, "target": target}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    return client.get(comparison_url(case_id, **params))


# -- 1. request shape: 422 / 404 parity ---------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"baseline": SNAPSHOT_BASELINE_ID},
        {"target": SNAPSHOT_TARGET_ID},
        {"baseline": "", "target": SNAPSHOT_TARGET_ID},
        {"baseline": "   ", "target": SNAPSHOT_TARGET_ID},
        {"baseline": SNAPSHOT_TARGET_ID, "target": SNAPSHOT_TARGET_ID},
        {"baseline": SNAPSHOT_TARGET_ID, "target": SNAPSHOT_BASELINE_ID},
    ],
)
def test_missing_same_or_reversed_params_are_422(client: TestClient, params):
    response = client.get(comparison_url(CASE_ID, **params))
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "limit,offset",
    [(0, 0), (101, 0), (25, -1), (25, 2147483648)],
)
def test_out_of_range_paging_is_422(client: TestClient, limit, offset):
    response = client.get(
        comparison_url(
            CASE_ID,
            baseline=SNAPSHOT_BASELINE_ID,
            target=SNAPSHOT_TARGET_ID,
            limit=limit,
            offset=offset,
        )
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "params",
    [
        {
            "baseline": SNAPSHOT_BASELINE_ID,
            "target": SNAPSHOT_TARGET_ID,
            "snapshotId": OTHER_SNAPSHOT_ID,
        },
        {
            "baseline": SNAPSHOT_BASELINE_ID,
            "target": SNAPSHOT_TARGET_ID,
            "snapshot_id": "snapshot-unknown",
        },
        {
            "baseline": SNAPSHOT_BASELINE_ID,
            "target": SNAPSHOT_TARGET_ID,
            "snapshotId": SNAPSHOT_BASELINE_ID,
            "snapshot_id": SNAPSHOT_TARGET_ID,
        },
    ],
)
def test_unrelated_snapshot_selector_is_422(client: TestClient, params):
    response = client.get(comparison_url(CASE_ID, **params))
    assert response.status_code == 422, response.text
    if "snapshotId" in params and "snapshot_id" in params:
        return
    assert response.json()["detail"] == SNAPSHOT_COMPARISON_THIRD_CONTEXT_DETAIL


def test_repeated_selector_naming_a_pinned_snapshot_is_tolerated(client: TestClient):
    response = client.get(
        comparison_url(
            CASE_ID,
            baseline=SNAPSHOT_BASELINE_ID,
            target=SNAPSHOT_TARGET_ID,
            snapshotId=SNAPSHOT_TARGET_ID,
        )
    )
    assert response.status_code == 200, response.text
    assert response.json()["targetSnapshotId"] == SNAPSHOT_TARGET_ID


@pytest.mark.parametrize(
    "baseline,target,case_id",
    [
        ("snapshot-unknown", SNAPSHOT_TARGET_ID, CASE_ID),
        (SNAPSHOT_BASELINE_ID, "snapshot-unknown", CASE_ID),
        (OTHER_SNAPSHOT_ID, SNAPSHOT_TARGET_ID, CASE_ID),
        (SNAPSHOT_BASELINE_ID, OTHER_SNAPSHOT_ID, CASE_ID),
        (SNAPSHOT_BASELINE_ID, SNAPSHOT_TARGET_ID, OTHER_CASE_ID),
        (SNAPSHOT_BASELINE_ID, SNAPSHOT_TARGET_ID, "case-f17-missing"),
    ],
)
def test_unknown_and_wrong_case_are_a_uniform_404(
    client: TestClient, baseline, target, case_id
):
    response = get_comparison(
        client, baseline=baseline, target=target, case_id=case_id
    )
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": SNAPSHOT_COMPARISON_NOT_FOUND_DETAIL}


# -- 2. availability before any delta ----------------------------------------


def _set_snapshot_fields(snapshot_id: str, **fields) -> None:
    session = db_session()
    try:
        snapshot = session.get(CaseSnapshot, snapshot_id)
        assert snapshot is not None
        for name, value in fields.items():
            setattr(snapshot, name, value)
        session.commit()
    finally:
        session.close()


@pytest.mark.parametrize(
    "reason,mutation",
    [
        (
            "incompatible_schema",
            lambda: _set_snapshot_fields(
                SNAPSHOT_TARGET_ID, schema_version="case-snapshot-v2"
            ),
        ),
        (
            "incompatible_identity",
            lambda: _set_snapshot_fields(
                SNAPSHOT_TARGET_ID,
                identity_version="claim-signature-sha512-v1",
            ),
        ),
        (
            "incompatible_policy",
            lambda: _set_snapshot_fields(
                SNAPSHOT_TARGET_ID, policy_version="case-history-policy-v2"
            ),
        ),
        (
            "unknown_version",
            lambda: (
                _set_snapshot_fields(
                    SNAPSHOT_BASELINE_ID, policy_version="case-history-policy-v2"
                ),
                _set_snapshot_fields(
                    SNAPSHOT_TARGET_ID, policy_version="case-history-policy-v2"
                ),
            ),
        ),
        (
            "payload_unreadable",
            lambda: _set_snapshot_fields(SNAPSHOT_TARGET_ID, payload_json=[]),
        ),
    ],
)
def test_each_unavailable_reason_has_no_ready_delta(
    client: TestClient, reason, mutation
):
    mutation()
    response = get_comparison(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["availability"] == "unavailable"
    assert body["unavailableReason"] == reason
    assert body["items"] == []
    assert body["total"] is None
    assert body["hasMore"] is False
    # Coverage, times and run ids are still recorded independently per side.
    assert body["baselineRunId"] == RUN_BASELINE_ID
    assert body["targetRunId"] == RUN_TARGET_ID
    assert body["baselineMetadata"]["sequence"] == 1
    assert body["targetMetadata"]["sequence"] == 2
    assert body["limit"] == 25
    assert body["offset"] == 0


def test_malformed_entity_group_is_payload_unreadable(client: TestClient):
    session = db_session()
    try:
        snapshot = session.get(CaseSnapshot, SNAPSHOT_TARGET_ID)
        assert snapshot is not None
        payload = json.loads(json.dumps(snapshot.payload_json))
    finally:
        session.close()
    payload["claims"] = "not-a-list"
    _set_snapshot_fields(SNAPSHOT_TARGET_ID, payload_json=payload)
    body = get_comparison(client).json()
    assert body["availability"] == "unavailable"
    assert body["unavailableReason"] == "payload_unreadable"
    assert body["items"] == []


def test_payload_describing_another_case_is_payload_unreadable(client: TestClient):
    session = db_session()
    try:
        snapshot = session.get(CaseSnapshot, SNAPSHOT_TARGET_ID)
        assert snapshot is not None
        payload = json.loads(json.dumps(snapshot.payload_json))
    finally:
        session.close()
    payload["caseId"] = OTHER_CASE_ID
    _set_snapshot_fields(SNAPSHOT_TARGET_ID, payload_json=payload)
    body = get_comparison(client).json()
    assert body["availability"] == "unavailable"
    assert body["unavailableReason"] == "payload_unreadable"


# -- 3. ready DTO: field-for-field, ordering, paging -------------------------


def test_ready_dto_matches_the_contract_field_for_field(client: TestClient):
    response = get_comparison(client)
    assert response.status_code == 200, response.text
    body = response.json()

    assert set(body) == DTO_FIELDS
    assert body["mode"] == "ad_hoc"
    assert body["comparisonPolicyVersion"] == (
        "snapshot-comparison-policy-v1"
    )
    assert body["baselineSnapshotId"] == SNAPSHOT_BASELINE_ID
    assert body["targetSnapshotId"] == SNAPSHOT_TARGET_ID
    assert body["baselineRunId"] == RUN_BASELINE_ID
    assert body["targetRunId"] == RUN_TARGET_ID
    assert body["baselineCoverage"] == "complete_requested_scope"
    assert body["targetCoverage"] == "complete_requested_scope"
    assert body["availability"] == "ready"
    assert body["unavailableReason"] is None
    assert isinstance(body["total"], int)
    assert body["total"] >= 1
    assert body["limit"] == 25
    assert body["offset"] == 0
    assert body["hasMore"] is False

    for side, sequence in (
        ("baselineMetadata", 1),
        ("targetMetadata", 2),
    ):
        metadata = body[side]
        assert set(metadata) == METADATA_FIELDS
        assert metadata["sequence"] == sequence
        assert isinstance(metadata["sequence"], int)
        assert metadata["schemaVersion"] == SNAPSHOT_SCHEMA_VERSION
        assert metadata["identityVersion"] == SNAPSHOT_IDENTITY_VERSION
        assert metadata["policyVersion"] == SNAPSHOT_POLICY_VERSION
        # Snapshot-save time, not source-observation time.
        assert isinstance(metadata["createdAt"], str)
        assert datetime.fromisoformat(metadata["createdAt"]) is not None

    for item in body["items"]:
        assert set(item) == ITEM_FIELDS
        assert item["changeKind"] in {
            "entity_added",
            "entity_absent",
            "field_changed",
        }
        assert item["changedFields"] == sorted(item["changedFields"])
        assert set(item["refs"]) == {"baseline", "target"}
        assert set(item["refs"]["baseline"]) <= REF_FIELDS
        assert set(item["refs"]["target"]) <= REF_FIELDS
        assert item["refs"]["baseline"]["snapshotId"] == SNAPSHOT_BASELINE_ID
        assert item["refs"]["target"]["snapshotId"] == SNAPSHOT_TARGET_ID
        assert "observedByRunId" not in item
        assert "actor" not in item
        for side in ("before", "after"):
            value = item[side]
            assert value is None or isinstance(value, dict)
            if isinstance(value, dict):
                assert "text" not in value or item["entityType"] != "captures"

    by_key = {
        (item["entityType"], item["entityId"], item["changeKind"]): item
        for item in body["items"]
    }
    assert ("claims", CLAIM_ADDED_ID, "entity_added") in by_key
    assert ("claims", CLAIM_ABSENT_ID, "entity_absent") in by_key
    assert ("claims", CLAIM_CHANGED_ID, "field_changed") in by_key
    assert ("links", LINK_ID, "entity_absent") in by_key

    added = by_key[("claims", CLAIM_ADDED_ID, "entity_added")]
    assert added["before"] is None
    assert added["after"]["text"] == ADDED_CLAIM_TEXT

    absent = by_key[("claims", CLAIM_ABSENT_ID, "entity_absent")]
    assert absent["after"] is None
    assert absent["before"]["text"] == ABSENT_CLAIM_TEXT
    # Refs are frozen side-specific ids, not fabricated inspector links.
    assert absent["refs"]["baseline"]["claimId"] == CLAIM_ABSENT_ID
    # The side that never observed the claim records no claim id at all.
    assert absent["refs"]["target"]["claimId"] is None

    changed = by_key[("claims", CLAIM_CHANGED_ID, "field_changed")]
    assert changed["changedFields"] == ["claimSignature", "text"]
    assert changed["before"]["text"] == ORIGINAL_CLAIM_TEXT
    assert changed["after"]["text"] == UPDATED_CLAIM_TEXT

    link = by_key[("links", LINK_ID, "entity_absent")]
    assert link["refs"]["baseline"]["claimId"] == CLAIM_ABSENT_ID
    assert link["refs"]["baseline"]["evidenceId"] == EVIDENCE_ID
    assert link["refs"]["baseline"]["captureId"]
    assert set(link["refs"]["target"]) == REF_FIELDS
    assert all(
        link["refs"]["target"][field] is None
        for field in REF_FIELDS - {"snapshotId"}
    )

    # Absence wording: never deletion / retraction / "no longer extracted".
    rendered = json.dumps(body).lower()
    for forbidden in ("delet", "retract", "no longer extracted", "removed"):
        assert forbidden not in rendered


def test_item_ordering_and_paging_are_deterministic(client: TestClient):
    first = get_comparison(client, limit=100).json()
    second = get_comparison(client, limit=100).json()
    assert first == second

    keys = [
        (item["entityType"], item["entityId"], item["changeKind"])
        for item in first["items"]
    ]
    assert keys == sorted(keys)
    assert first["total"] == len(first["items"])

    pages = []
    offset = 0
    while True:
        page = get_comparison(client, limit=2, offset=offset).json()
        pages.extend(page["items"])
        assert page["total"] == first["total"]
        if not page["hasMore"]:
            break
        offset += 2
    assert pages == first["items"]


def test_offset_beyond_a_ready_result_keeps_the_true_total(client: TestClient):
    full = get_comparison(client, limit=100).json()
    response = get_comparison(client, limit=25, offset=100)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["availability"] == "ready"
    assert body["items"] == []
    assert body["total"] == full["total"]
    assert body["offset"] == 100
    assert body["hasMore"] is False


def test_ready_zero_change_pair_keeps_an_integer_total(
    tmp_path: Path, client: TestClient
):
    """A genuinely empty delta is ready with ``total: 0``, not unavailable."""
    publish_snapshot(
        tmp_path,
        run_id="run-f17-third",
        snapshot_id="snapshot-f17-third",
        sequence=3,
    )
    response = get_comparison(
        client,
        baseline=SNAPSHOT_TARGET_ID,
        target="snapshot-f17-third",
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["availability"] == "ready"
    assert body["unavailableReason"] is None
    assert body["items"] == []
    assert body["total"] == 0
    assert body["hasMore"] is False


# -- 4. the ad-hoc reader never uses publication writers ---------------------


def test_publication_writers_are_never_called(client: TestClient, monkeypatch):

    def boom(*args, **kwargs):
        raise AssertionError("publication writer must not run on an ad-hoc read")

    from src.cases import history as history_module
    from src.cases import service as service_module

    for module, name in (
        (history_module, "build_snapshot_delta"),
        (history_module, "compose_case_snapshot"),
        (service_module, "build_snapshot_delta"),
        (service_module, "compose_case_snapshot"),
        (comparison_module, "build_snapshot_delta"),
        (comparison_module, "compose_case_snapshot"),
    ):
        monkeypatch.setattr(module, name, boom, raising=False)
    for name in (
        "_publish_successful_run",
        "_finalize_investigation_run",
        "run_case",
    ):
        monkeypatch.setattr(
            service_module.TopicCaseService, name, boom, raising=False
        )

    body = get_comparison(client).json()
    assert body["availability"] == "ready"
    assert any(
        item["entityType"] == "claims"
        and item["changeKind"] == "entity_absent"
        for item in body["items"]
    )


# -- 5. no writes ------------------------------------------------------------


def _table_counts() -> dict[str, int]:
    session = db_session()
    try:
        return {
            table.name: session.execute(
                select(func.count()).select_from(table)
            ).scalar_one()
            for table in sorted(
                Base.metadata.tables.values(), key=lambda item: item.name
            )
        }
    finally:
        session.close()


def _migration_state() -> list[tuple]:
    session = db_session()
    try:
        snapshot_rows = session.execute(
            select(func.count()).select_from(
                Base.metadata.tables["case_snapshots"]
            )
        ).scalar_one()
        tables = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        ).all()
        return [(row[0], snapshot_rows) for row in tables]
    finally:
        session.close()


def test_comparison_batch_leaves_raw_state_unchanged(tmp_path: Path, client: TestClient):
    db_file = Path(get_database().db_path)
    assert db_file.parent == tmp_path
    digest_before = hashlib.sha256(db_file.read_bytes()).hexdigest()
    directory_before = sorted(entry.name for entry in db_file.parent.iterdir())
    counts_before = _table_counts()
    schema_before = _migration_state()

    responses = [
        get_comparison(client),
        get_comparison(client, limit=2, offset=1),
        get_comparison(client, limit=100, offset=500),
        get_comparison(client, baseline=SNAPSHOT_TARGET_ID, target=SNAPSHOT_BASELINE_ID),
        get_comparison(client, baseline="snapshot-unknown"),
        get_comparison(client, baseline=SNAPSHOT_BASELINE_ID, target=SNAPSHOT_BASELINE_ID),
        get_comparison(client, case_id=OTHER_CASE_ID),
    ]
    assert {response.status_code for response in responses} == {200, 404, 422}
    assert get_comparison(client).status_code == 200

    digest_after = hashlib.sha256(db_file.read_bytes()).hexdigest()
    assert digest_after == digest_before
    assert sorted(entry.name for entry in db_file.parent.iterdir()) == directory_before
    assert _table_counts() == counts_before
    assert _migration_state() == schema_before


# -- 6. frozen v1 payload integrity ------------------------------------------


REQUIRED_ENTITY_GROUPS = (
    "articles",
    "events",
    "claims",
    "links",
    "citations",
    "evidence",
    "captures",
    "reviews",
    "exceptions",
    "parties",
    "partyInvestigations",
    "narratives",
)


def _copy_payload(snapshot_id: str) -> dict[str, Any]:
    session = db_session()
    try:
        snapshot = session.get(CaseSnapshot, snapshot_id)
        assert snapshot is not None
        return json.loads(json.dumps(snapshot.payload_json))
    finally:
        session.close()


def _stored_fingerprint(snapshot_id: str) -> tuple[Any, Any]:
    session = db_session()
    try:
        snapshot = session.get(CaseSnapshot, snapshot_id)
        assert snapshot is not None
        return json.loads(json.dumps(snapshot.payload_json)), snapshot.semantic_hash
    finally:
        session.close()


def _store_payload(
    snapshot_id: str, payload: Any, *, recompute_hash: bool = False
) -> None:
    """Plant a frozen payload, optionally with the canonical writer hash."""
    fields: dict[str, Any] = {"payload_json": payload}
    if recompute_hash:
        fields["semantic_hash"] = semantic_hash_for_payload(payload)
    _set_snapshot_fields(snapshot_id, **fields)


def _empty_mapping(payload: dict[str, Any]) -> Any:
    return {}


def _drop_group(payload: dict[str, Any]) -> Any:
    payload.pop("narratives")
    return payload


def _null_group(payload: dict[str, Any]) -> Any:
    payload["claims"] = None
    return payload


def _wrong_group_type(payload: dict[str, Any]) -> Any:
    payload["claims"] = {"id": "claim-f17-changed"}
    return payload


def _non_mapping_row(payload: dict[str, Any]) -> Any:
    payload["claims"].append("not-a-row")
    return payload


def _missing_id(payload: dict[str, Any]) -> Any:
    payload["claims"][0].pop("id")
    return payload


def _blank_id(payload: dict[str, Any]) -> Any:
    payload["claims"][0]["id"] = "   "
    return payload


def _non_string_id(payload: dict[str, Any]) -> Any:
    payload["claims"][0]["id"] = 7
    return payload


def _duplicate_id(payload: dict[str, Any]) -> Any:
    payload["claims"].append(json.loads(json.dumps(payload["claims"][0])))
    return payload


def _wrong_embedded_case(payload: dict[str, Any]) -> Any:
    payload["caseId"] = OTHER_CASE_ID
    return payload


def _missing_embedded_case(payload: dict[str, Any]) -> Any:
    payload.pop("caseId")
    return payload


def _wrong_embedded_schema(payload: dict[str, Any]) -> Any:
    payload["schemaVersion"] = "case-snapshot-v2"
    return payload


def _missing_embedded_policy(payload: dict[str, Any]) -> Any:
    payload.pop("policyVersion")
    return payload


def _missing_query(payload: dict[str, Any]) -> Any:
    payload.pop("query")
    return payload


def _missing_review_notes(payload: dict[str, Any]) -> Any:
    payload.pop("reviewNotes")
    return payload


def _truncate_claims(payload: dict[str, Any]) -> Any:
    payload["claims"] = payload["claims"][:-1]
    return payload


def _change_claim_text(payload: dict[str, Any]) -> Any:
    payload["claims"][0]["text"] = "Edited after the observation."
    return payload


#: ``(id, mutation, recomputed hash?)``. A recomputed hash isolates the shape
#: check: the semantic hash alone cannot make these payloads comparable.
CORRUPTIONS = (
    ("empty-mapping", _empty_mapping, True),
    ("missing-group", _drop_group, True),
    ("null-group", _null_group, True),
    ("wrong-group-type", _wrong_group_type, False),
    ("non-mapping-row", _non_mapping_row, False),
    ("missing-id", _missing_id, True),
    ("blank-id", _blank_id, True),
    ("non-string-id", _non_string_id, True),
    ("duplicate-id", _duplicate_id, True),
    ("wrong-embedded-case", _wrong_embedded_case, True),
    ("missing-embedded-case", _missing_embedded_case, True),
    ("wrong-embedded-schema", _wrong_embedded_schema, True),
    ("missing-embedded-policy", _missing_embedded_policy, True),
    ("missing-query", _missing_query, True),
    ("missing-review-notes", _missing_review_notes, True),
    ("truncated-claims-stale-hash", _truncate_claims, False),
    ("changed-claim-text-stale-hash", _change_claim_text, False),
)


def test_empty_target_payload_is_never_a_ready_delta(client: TestClient):
    """Regression: ``{}`` used to look like seven observed removals."""
    _store_payload(SNAPSHOT_TARGET_ID, {}, recompute_hash=True)
    stored_before = _stored_fingerprint(SNAPSHOT_TARGET_ID)

    response = get_comparison(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["availability"] == "unavailable"
    assert body["unavailableReason"] == "payload_unreadable"
    assert body["items"] == []
    assert body["total"] is None
    assert body["hasMore"] is False
    assert _stored_fingerprint(SNAPSHOT_TARGET_ID) == stored_before


@pytest.mark.parametrize("side", ["baseline", "target"])
@pytest.mark.parametrize(
    "name,mutate,recompute_hash",
    CORRUPTIONS,
    ids=[case[0] for case in CORRUPTIONS],
)
def test_corrupt_frozen_payload_is_unavailable_without_a_delta(
    client: TestClient,
    side: str,
    name: str,
    mutate,
    recompute_hash: bool,
):
    snapshot_id = (
        SNAPSHOT_BASELINE_ID if side == "baseline" else SNAPSHOT_TARGET_ID
    )
    payload = mutate(_copy_payload(snapshot_id))
    _store_payload(snapshot_id, payload, recompute_hash=recompute_hash)
    stored_before = _stored_fingerprint(snapshot_id)
    other_id = (
        SNAPSHOT_TARGET_ID if side == "baseline" else SNAPSHOT_BASELINE_ID
    )
    other_before = _stored_fingerprint(other_id)

    response = get_comparison(client, limit=7, offset=1)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["availability"] == "unavailable"
    assert body["unavailableReason"] == "payload_unreadable"
    assert body["items"] == []
    assert body["total"] is None
    assert body["hasMore"] is False
    # Selected ids, per-side metadata and paging survive the refusal.
    assert body["baselineSnapshotId"] == SNAPSHOT_BASELINE_ID
    assert body["targetSnapshotId"] == SNAPSHOT_TARGET_ID
    assert body["baselineRunId"] == RUN_BASELINE_ID
    assert body["targetRunId"] == RUN_TARGET_ID
    assert body["baselineMetadata"]["sequence"] == 1
    assert body["targetMetadata"]["sequence"] == 2
    assert body["limit"] == 7
    assert body["offset"] == 1
    # The reader neither repairs the payload nor rewrites either stored row.
    assert _stored_fingerprint(snapshot_id) == stored_before
    assert _stored_fingerprint(other_id) == other_before


def test_real_writer_payload_keeps_required_empty_groups_ready(
    client: TestClient,
):
    """The canonical writer always emits all arrays, including empty ones."""
    for snapshot_id in (SNAPSHOT_BASELINE_ID, SNAPSHOT_TARGET_ID):
        payload = _copy_payload(snapshot_id)
        for name in REQUIRED_ENTITY_GROUPS:
            assert isinstance(payload[name], list)
        assert payload["articles"] == []
        assert payload["citations"] == []
        assert payload["reviews"] == []
        assert payload["exceptions"] == []
        assert payload["parties"] == []
        assert payload["partyInvestigations"] == []
        assert payload["narratives"] == []

    response = get_comparison(client, limit=100)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["availability"] == "ready"
    assert body["unavailableReason"] is None
    assert body["total"] == len(body["items"])
    assert body["total"] >= 1


def test_intentional_absence_and_zero_change_stay_ready(
    client: TestClient, tmp_path: Path
):
    """Corruption handling must not hide a real observation delta."""
    body = get_comparison(client, limit=100).json()
    assert body["availability"] == "ready"
    keys = {
        (item["entityType"], item["entityId"], item["changeKind"])
        for item in body["items"]
    }
    assert ("claims", CLAIM_ABSENT_ID, "entity_absent") in keys
    assert ("claims", CLAIM_ADDED_ID, "entity_added") in keys

    publish_snapshot(
        tmp_path,
        run_id="run-f17-fourth",
        snapshot_id="snapshot-f17-fourth",
        sequence=4,
    )
    same = get_comparison(
        client,
        baseline=SNAPSHOT_TARGET_ID,
        target="snapshot-f17-fourth",
        limit=100,
    ).json()
    assert same["availability"] == "ready"
    assert same["items"] == []
    assert same["total"] == 0


@pytest.mark.parametrize("side", ["baseline", "target"])
def test_undecodable_stored_json_is_unavailable_payload(
    client: TestClient, side: str
):
    """A JSON column holding non-JSON text is unreadable, not a miss/500."""
    snapshot_id = (
        SNAPSHOT_BASELINE_ID if side == "baseline" else SNAPSHOT_TARGET_ID
    )
    session = db_session()
    try:
        session.execute(
            text("UPDATE case_snapshots SET payload_json = '{' WHERE id = :id"),
            {"id": snapshot_id},
        )
        session.commit()
    finally:
        session.close()

    response = get_comparison(client, limit=7, offset=1)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["availability"] == "unavailable"
    assert body["unavailableReason"] == "payload_unreadable"
    assert body["items"] == []
    assert body["total"] is None
    assert body["hasMore"] is False
    assert body["baselineSnapshotId"] == SNAPSHOT_BASELINE_ID
    assert body["targetSnapshotId"] == SNAPSHOT_TARGET_ID
    assert body["baselineMetadata"]["sequence"] == 1
    assert body["targetMetadata"]["sequence"] == 2
    assert isinstance(body["baselineMetadata"]["createdAt"], str)
    assert isinstance(body["targetMetadata"]["createdAt"], str)
    assert body["limit"] == 7
    assert body["offset"] == 1

    session = db_session()
    try:
        raw = session.execute(
            text("SELECT payload_json FROM case_snapshots WHERE id = :id"),
            {"id": snapshot_id},
        ).scalar_one()
    finally:
        session.close()
    assert raw == "{"
