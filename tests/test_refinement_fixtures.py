"""Focused assertions for the additive refinement fixture states (F00 step 2).

Each test proves one documented state that later refinement cards consume. The
fixture builder lives in ``scripts/v01_e2e_fixture.py``; it mocks the paid
providers, writes every database/report path under the explicit output root and
performs no external IO. Here every output root is a pytest temporary directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from scripts.v01_e2e_fixture import (
    REFINEMENT_VARIANTS_FILENAME,
    materialize_refinement_states,
)
from src.cases import TopicCaseService
from src.cases.service import _payload_checksum
from src.http.mappers import map_case_detail
from src.storage import (
    CaseArtifact,
    Claim,
    EvidenceCapture,
    EvidenceItem,
    Event,
    TopicCase,
    get_database,
    init_database,
)
from src.storage.migrations import run_migrations

# The six statuses the timeline contract exposes; the stored raw value must not
# be one of them for the "unrecognized" state to be meaningful.
VALID_TIMELINE_STATUSES = {
    "confirmed",
    "probable",
    "alleged",
    "contested",
    "debunked",
    "unknown",
}


@pytest.fixture(scope="module")
def refinement_state(tmp_path_factory):
    """Build the fixture database once; all paths stay under pytest temp dirs."""
    out = tmp_path_factory.mktemp("refinement-states")
    return {"out": out, **materialize_refinement_states(out)}


@pytest.fixture()
def fixture_env(refinement_state):
    """Point the guarded application database at the shared fixture copy."""
    out = refinement_state["out"]
    db_path = out / "triangulate.db"
    init_database(str(db_path))
    run_migrations(str(db_path))
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=out)
    return service, refinement_state["variants"]


def _session():
    return get_database().get_session_sync()


def test_missing_case_variant_is_absent(fixture_env):
    service, variants = fixture_env
    missing_case_id = variants["missingCase"]["caseId"]

    assert service.get_case(missing_case_id) is None
    assert service.get_case_details(missing_case_id) is None
    assert missing_case_id not in {case.id for case in service.list_cases()}


def test_wrong_case_annotation_target_belongs_to_other_case(fixture_env):
    service, variants = fixture_env
    target = variants["wrongCaseAnnotationTarget"]
    case_id = target["caseId"]
    owner_case_id = target["targetOwnerCaseId"]
    evidence_target = target["evidenceTarget"]

    assert case_id != owner_case_id
    session = _session()
    try:
        claim_owner = session.execute(
            select(Event.case_id)
            .join(Claim, Claim.event_id == Event.id)
            .where(Claim.id == target["targetId"])
        ).scalar_one()
        evidence_owner = session.execute(
            select(EvidenceItem.case_id).where(
                EvidenceItem.id == evidence_target["targetId"]
            )
        ).scalar_one()
    finally:
        session.close()

    assert claim_owner == owner_case_id
    assert evidence_owner == owner_case_id

    # The same targets are not reachable from the annotation case's own view.
    detail = service.get_case_details(case_id)
    assert target["targetId"] not in {claim["id"] for claim in detail["claims"]}
    assert evidence_target["targetId"] not in {
        item["id"] for item in detail["evidence"]
    }


def test_out_of_range_and_missing_coordinates_are_distinct(fixture_env):
    _, variants = fixture_env
    coordinates = variants["coordinates"]

    session = _session()
    try:
        out_of_range = session.get(Event, coordinates["outOfRange"]["eventId"])
        missing = session.get(Event, coordinates["missing"]["eventId"])
        recorded_at_zero = session.get(Event, coordinates["recordedAtZero"]["eventId"])
        assert out_of_range is not None
        assert missing is not None
        assert recorded_at_zero is not None
        stored = {
            "out_of_range": (
                out_of_range.case_id,
                out_of_range.location_lat,
                out_of_range.location_lon,
            ),
            "missing": (missing.location_lat, missing.location_lon),
            "recorded_at_zero": (
                recorded_at_zero.case_id,
                recorded_at_zero.location_lat,
                recorded_at_zero.location_lon,
            ),
        }
    finally:
        session.close()

    case_id, lat, lon = stored["out_of_range"]
    assert case_id == coordinates["caseId"]
    assert (lat, lon) == (120.5, 245.0)
    assert not -90.0 <= lat <= 90.0
    assert not -180.0 <= lon <= 180.0

    assert stored["missing"] == (None, None)

    zero_case_id, zero_lat, zero_lon = stored["recorded_at_zero"]
    assert zero_case_id == coordinates["caseId"]
    assert (zero_lat, zero_lon) == (0.0, 0.0)
    assert coordinates["recordedAtZero"]["eventId"] != coordinates["missing"]["eventId"]


def test_unrecognized_timeline_status_is_preserved_raw(fixture_env, refinement_state):
    _, variants = fixture_env
    entry = variants["unrecognizedTimelineStatus"]
    out = refinement_state["out"]

    assert entry["rawStatus"] not in VALID_TIMELINE_STATUSES

    session = _session()
    try:
        artifact = session.get(CaseArtifact, entry["artifactId"])
        assert artifact is not None
        assert isinstance(artifact.payload_json, dict)
        stored = (
            artifact.artifact_type,
            artifact.checksum,
            dict(artifact.payload_json),
        )
    finally:
        session.close()

    artifact_type, checksum, payload = stored
    assert artifact_type == "report_json"
    timeline = payload["timeline"]
    assert isinstance(timeline, list)
    assert timeline[entry["entryIndex"]]["status"] == entry["rawStatus"]
    # The frozen bundle's checksum is derived from the payload it now holds.
    assert checksum == _payload_checksum(payload)

    report_path = Path(entry["path"])
    assert report_path.is_relative_to(out)
    exported = json.loads(report_path.read_text(encoding="utf-8"))
    assert exported["timeline"][entry["entryIndex"]]["status"] == entry["rawStatus"]
    assert all(
        item["status"] != entry["rawStatus"]
        for index, item in enumerate(exported["timeline"])
        if index != entry["entryIndex"]
    )


def test_absent_report_case_has_no_report_artifacts(fixture_env):
    service, variants = fixture_env
    case_id = variants["absentReport"]["caseId"]

    session = _session()
    try:
        case = session.get(TopicCase, case_id)
        artifacts = list(
            session.execute(
                select(CaseArtifact).where(CaseArtifact.case_id == case_id)
            ).scalars()
        )
        stored = (case.report_path, case.latest_manifest_path) if case else None
    finally:
        session.close()

    assert stored == (None, None)
    assert artifacts == []

    detail = service.get_case_details(case_id)
    assert detail is not None
    assert detail["case"]["report_path"] is None
    assert detail["case"]["latest_manifest_path"] is None
    assert detail["artifacts"] == []
    assert map_case_detail(detail).tabs.report.status == "pending"


def test_legacy_capture_has_unknown_provenance(fixture_env):
    service, variants = fixture_env
    legacy = variants["legacyCapture"]

    session = _session()
    try:
        capture = session.get(EvidenceCapture, legacy["captureId"])
        evidence = session.get(EvidenceItem, legacy["evidenceId"])
        assert capture is not None
        assert evidence is not None
        stored = (
            capture.capture_kind,
            capture.observed_at,
            dict(capture.metadata_json),
            evidence.current_capture_id,
        )
    finally:
        session.close()

    capture_kind, observed_at, metadata, current_capture_id = stored
    assert capture_kind == "legacy_snapshot"
    assert observed_at is None
    assert metadata == {}
    assert current_capture_id != legacy["captureId"]

    detail = service.get_evidence_detail(legacy["caseId"], legacy["evidenceId"])
    summaries = {item["id"]: item for item in detail["captures"]}
    summary = summaries[legacy["captureId"]]
    assert summary["capture_kind"] == "legacy_snapshot"
    assert summary["observed_at"] is None
    assert summary["metadata"] == {}
    assert summary["is_current"] is False


def test_variants_are_additive_next_to_the_baseline_manifest(refinement_state):
    out = refinement_state["out"]
    baseline_on_disk = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    written = json.loads(
        (out / REFINEMENT_VARIANTS_FILENAME).read_text(encoding="utf-8")
    )

    # The baseline manifest keeps its documented shape and counts; the extra
    # states are described in their own file next to it.
    assert "refinementVariants" not in baseline_on_disk
    assert baseline_on_disk["caseId"] == refinement_state["baseline"]["caseId"]
    assert baseline_on_disk["expectedCounts"]["cases"] == 2
    assert written == refinement_state["variants"]
    assert written["baselineManifest"] == "manifest.json"
    assert written["additions"] == {"cases": 1, "events": 1, "captureVersions": 1}
