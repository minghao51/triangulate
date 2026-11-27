"""F19 / X02: historical artifact descriptor list and allowlisted downloads.

Every fixture is synthetic: one case with a successfully published grouped run
whose ``output_root/cases/{slug}/runs/{run_id}`` directory holds the three report
files the writer publishes. No model, network, report composition or index call
is made, and the reader is a pure read: it resolves paths and bytes only.

Covered here: sorted path-free descriptors with honest ``checksumKind``; an
existing run without published artifacts answering ``200 []``; uniform 404
parity for unknown case/run, wrong run, wrong artifact owner and missing bytes;
symlinked files, an intermediate directory symlink, ``../`` traversal and
cross-run escapes; the 50 MiB ``413 too_large`` cap; redacted permission/OS
errors; no descriptor leak across rejected reads; a before/after output-tree
hash proving a mixed GET batch writes nothing; and a source-level check that the
reader module contains no directory-creating helper, no write-mode ``open`` and
no import of writer helpers.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from scripts.v01_e2e_fixture import materialize
from src.cases import artifact_reader
from src.cases.artifact_reader import (
    ARTIFACT_FILENAMES,
    ARTIFACT_MEDIA_TYPES,
    MAX_ARTIFACT_BYTES,
)
from src.http.app import (
    ARTIFACT_NOT_FOUND_DETAIL,
    ARTIFACT_TOO_LARGE_DETAIL,
    app,
    create_app,
    get_artifact_output_root,
)
from src.settings import (
    DEFAULT_OUTPUT_ROOT,
    OUTPUT_ROOT_ENV_VAR,
    resolve_output_root,
)
from src.storage import (
    CaseArtifact,
    CaseStageName,
    CaseStageRun,
    CaseStatus,
    InvestigationCoverage,
    InvestigationRun,
    InvestigationRunStatus,
    InvestigationRunTrigger,
    StageStatus,
    TopicCase,
    get_database,
    init_database,
)

CASE_ID = "case-f19"
CASE_SLUG = "case-f19-slug"
OTHER_CASE_ID = "case-f19-other"
OTHER_CASE_SLUG = "case-f19-other-slug"
RUN_ID = "run-f19"
OTHER_RUN_ID = "run-f19-other"
FOREIGN_CASE_RUN_ID = "run-f19-foreign-case"
FAILED_RUN_ID = "run-f19-failed"
STAGE_RUN_ID = "stage-f19"
OTHER_STAGE_RUN_ID = "stage-f19-other"
TEMPORARY_STAGE_RUN_ID = "stage-f19-temporary"
FOREIGN_STAGE_RUN_ID = "stage-f19-foreign"
FAILED_STAGE_RUN_ID = "stage-f19-failed"

ARTIFACT_IDS = {
    "report_markdown": "artifact-f19-md",
    "report_json": "artifact-f19-json",
    "execution_manifest": "artifact-f19-manifest",
}
TEMPORARY_ARTIFACT_ID = "artifact-f19-temporary"
FOREIGN_ARTIFACT_ID = "artifact-f19-foreign"
FAILED_ARTIFACT_ID = "artifact-f19-failed"

REPORT_JSON_PAYLOAD = {"results": [], "synthetic": True}
MANIFEST_PAYLOAD = {"run": RUN_ID, "synthetic": True}
FILE_BYTES = {
    "report_markdown": b"# Synthetic report\n\nNo script here.\n",
    "report_json": json.dumps(REPORT_JSON_PAYLOAD).encode("utf-8"),
    "execution_manifest": json.dumps(MANIFEST_PAYLOAD).encode("utf-8"),
}
DESCRIPTOR_FIELDS = {
    "artifactId",
    "type",
    "displayName",
    "downloadUrl",
    "recordedChecksum",
    "checksumKind",
}


def db_session():
    return get_database().get_session_sync()


def payload_checksum(payload) -> str:
    """The writer's canonical payload checksum (payload, never file bytes)."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def run_directory(output_root: Path, slug: str = CASE_SLUG, run_id: str = RUN_ID) -> Path:
    return output_root / "cases" / slug / "runs" / run_id


def write_run_files(
    output_root: Path, slug: str = CASE_SLUG, run_id: str = RUN_ID
) -> Path:
    directory = run_directory(output_root, slug, run_id)
    directory.mkdir(parents=True, exist_ok=True)
    for artifact_type, filename in ARTIFACT_FILENAMES.items():
        (directory / filename).write_bytes(FILE_BYTES[artifact_type])
    return directory


def add_case(session, case_id: str, slug: str) -> None:
    session.add(
        TopicCase(
            id=case_id,
            query=f"Query for {case_id}",
            slug=slug,
            conflict="Synthetic domain",
            status=CaseStatus.REVIEW_READY,
            metadata_json={},
        )
    )


def add_run(
    session,
    run_id: str,
    case_id: str,
    sequence: int,
    status: InvestigationRunStatus = InvestigationRunStatus.SUCCEEDED,
) -> None:
    session.add(
        InvestigationRun(
            id=run_id,
            case_id=case_id,
            sequence=sequence,
            trigger=InvestigationRunTrigger.INITIAL,
            parameter_snapshot={},
            status=status,
            coverage=InvestigationCoverage.COMPLETE_REQUESTED_SCOPE,
            coverage_details={},
        )
    )


def add_stage(
    session,
    stage_run_id: str,
    case_id: str,
    investigation_run_id: str | None,
    status: StageStatus = StageStatus.COMPLETED,
) -> None:
    session.add(
        CaseStageRun(
            id=stage_run_id,
            case_id=case_id,
            stage_name=CaseStageName.REPORT,
            status=status,
            attempt=1,
            investigation_run_id=investigation_run_id,
        )
    )


def add_artifact(
    session,
    artifact_id: str,
    *,
    case_id: str,
    stage_run_id: str,
    artifact_type: str,
    path: str | None,
    payload_json=None,
    checksum: str | None = None,
) -> None:
    session.add(
        CaseArtifact(
            id=artifact_id,
            case_id=case_id,
            stage_run_id=stage_run_id,
            artifact_type=artifact_type,
            path=path,
            payload_json=payload_json,
            checksum=checksum,
        )
    )


def seed_workspace(output_root: Path) -> None:
    """One successful published run plus the non-eligible neighbours."""
    directory = write_run_files(output_root)
    # Bytes also exist for a different run of the same case: a wrong-run request
    # must still be a miss, never a nearby-run substitution.
    write_run_files(output_root, run_id=OTHER_RUN_ID)
    failed_dir = write_run_files(output_root, run_id=FAILED_RUN_ID)
    foreign_dir = write_run_files(
        output_root, slug=OTHER_CASE_SLUG, run_id=FOREIGN_CASE_RUN_ID
    )

    session = db_session()
    try:
        add_case(session, CASE_ID, CASE_SLUG)
        add_case(session, OTHER_CASE_ID, OTHER_CASE_SLUG)
        add_run(session, RUN_ID, CASE_ID, 1)
        add_run(session, OTHER_RUN_ID, CASE_ID, 2)
        add_run(session, FOREIGN_CASE_RUN_ID, OTHER_CASE_ID, 1)
        add_run(
            session,
            FAILED_RUN_ID,
            CASE_ID,
            3,
            status=InvestigationRunStatus.FAILED,
        )
        add_stage(session, STAGE_RUN_ID, CASE_ID, RUN_ID)
        add_stage(session, OTHER_STAGE_RUN_ID, CASE_ID, OTHER_RUN_ID)
        add_stage(session, FOREIGN_STAGE_RUN_ID, OTHER_CASE_ID, FOREIGN_CASE_RUN_ID)
        add_stage(session, TEMPORARY_STAGE_RUN_ID, CASE_ID, None)
        add_stage(session, FAILED_STAGE_RUN_ID, CASE_ID, FAILED_RUN_ID)

        markdown_path = directory / "topic_report.md"
        # Insertion order is deliberately not the contract sort order.
        add_artifact(
            session,
            ARTIFACT_IDS["report_markdown"],
            case_id=CASE_ID,
            stage_run_id=STAGE_RUN_ID,
            artifact_type="report_markdown",
            path=str(markdown_path),
            payload_json=None,
            checksum=payload_checksum({"path": str(markdown_path)}),
        )
        add_artifact(
            session,
            ARTIFACT_IDS["report_json"],
            case_id=CASE_ID,
            stage_run_id=STAGE_RUN_ID,
            artifact_type="report_json",
            path=str(directory / "topic_analysis.json"),
            payload_json=REPORT_JSON_PAYLOAD,
            checksum=payload_checksum(REPORT_JSON_PAYLOAD),
        )
        add_artifact(
            session,
            ARTIFACT_IDS["execution_manifest"],
            case_id=CASE_ID,
            stage_run_id=STAGE_RUN_ID,
            artifact_type="execution_manifest",
            path=str(directory / "manifest.json"),
            payload_json=MANIFEST_PAYLOAD,
            checksum=payload_checksum(MANIFEST_PAYLOAD),
        )
        # A temporary/unpublished stage attempt has no grouped-run reference.
        add_artifact(
            session,
            TEMPORARY_ARTIFACT_ID,
            case_id=CASE_ID,
            stage_run_id=TEMPORARY_STAGE_RUN_ID,
            artifact_type="report_markdown",
            path=str(markdown_path),
            payload_json=None,
            checksum=None,
        )
        # An artifact owned by another case must never be served under this one.
        add_artifact(
            session,
            FOREIGN_ARTIFACT_ID,
            case_id=OTHER_CASE_ID,
            stage_run_id=FOREIGN_STAGE_RUN_ID,
            artifact_type="report_markdown",
            path=str(foreign_dir / "topic_report.md"),
            payload_json=None,
            checksum=None,
        )
        # Artifacts recorded for a run that did not succeed are not eligible.
        add_artifact(
            session,
            FAILED_ARTIFACT_ID,
            case_id=CASE_ID,
            stage_run_id=FAILED_STAGE_RUN_ID,
            artifact_type="report_markdown",
            path=str(failed_dir / "topic_report.md"),
            payload_json=None,
            checksum=None,
        )
        session.commit()
    finally:
        session.close()


def update_artifact(artifact_id: str, **fields) -> None:
    session = db_session()
    try:
        artifact = session.get(CaseArtifact, artifact_id)
        assert artifact is not None
        for name, value in fields.items():
            setattr(artifact, name, value)
        session.commit()
    finally:
        session.close()


@pytest.fixture
def output_root(tmp_path: Path) -> Path:
    return tmp_path / "output"


@pytest.fixture
def workspace(tmp_path: Path, output_root: Path) -> Path:
    init_database(str(tmp_path / "f19.sqlite3"))
    # Historical GETs read the app's startup-captured path, not the global
    # binding, so this test's disposable database must be bound explicitly.
    app.state.database_path = tmp_path / "f19.sqlite3"
    seed_workspace(output_root)
    return output_root


@pytest.fixture
def client(workspace: Path):
    app.dependency_overrides[get_artifact_output_root] = lambda: workspace
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def list_url(case_id: str = CASE_ID, run_id: str = RUN_ID) -> str:
    return f"/api/cases/{case_id}/investigation-runs/{run_id}/artifacts"


def download_url(
    artifact_id: str, *, case_id: str = CASE_ID, run_id: str = RUN_ID
) -> str:
    return f"{list_url(case_id, run_id)}/{artifact_id}"


def tree_digest(root: Path) -> dict[str, str]:
    """Content + metadata fingerprint of the whole output tree."""
    digest: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            digest[relative] = f"symlink:{os.readlink(path)}"
        elif path.is_file():
            info = path.stat()
            digest[relative] = ":".join(
                (
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    str(info.st_size),
                    str(info.st_mtime_ns),
                    str(info.st_ino),
                )
            )
        else:
            digest[relative] = "directory"
    return digest


# ---------------------------------------------------------------------------
# AC5: descriptor contract
# ---------------------------------------------------------------------------


def test_list_descriptors_are_sorted_and_path_free(client: TestClient):
    response = client.get(list_url())
    assert response.status_code == 200, response.text
    body = response.json()

    assert [item["type"] for item in body] == [
        "execution_manifest",
        "report_json",
        "report_markdown",
    ]
    serialized = json.dumps(body).lower()
    assert "filesystem" not in serialized
    for descriptor in body:
        assert set(descriptor) == DESCRIPTOR_FIELDS
        assert "path" not in json.dumps(descriptor).lower()
        assert descriptor["displayName"] == ARTIFACT_FILENAMES[descriptor["type"]]
        assert descriptor["downloadUrl"] == download_url(descriptor["artifactId"])
        assert descriptor["checksumKind"] in {"payload_json", "unknown"}


def test_checksum_kind_is_honest(client: TestClient):
    by_type = {item["type"]: item for item in client.get(list_url()).json()}

    # Payload artifacts carry the writer's canonical payload checksum.
    assert by_type["report_json"]["checksumKind"] == "payload_json"
    assert by_type["report_json"]["recordedChecksum"] == payload_checksum(
        REPORT_JSON_PAYLOAD
    )
    assert by_type["execution_manifest"]["checksumKind"] == "payload_json"
    assert by_type["execution_manifest"]["recordedChecksum"] == payload_checksum(
        MANIFEST_PAYLOAD
    )

    # The markdown row stores no payload, so its recorded value is not the
    # payload checksum of anything stored and stays honestly "unknown".
    assert by_type["report_markdown"]["checksumKind"] == "unknown"
    assert by_type["report_markdown"]["recordedChecksum"] is not None


def test_mismatched_recorded_checksum_is_unknown(client: TestClient):
    update_artifact(ARTIFACT_IDS["report_json"], checksum="0" * 64)
    by_type = {item["type"]: item for item in client.get(list_url()).json()}
    assert by_type["report_json"]["checksumKind"] == "unknown"
    assert by_type["report_json"]["recordedChecksum"] == "0" * 64


def test_null_recorded_checksum_is_unknown(client: TestClient):
    update_artifact(ARTIFACT_IDS["execution_manifest"], checksum=None)
    by_type = {item["type"]: item for item in client.get(list_url()).json()}
    assert by_type["execution_manifest"]["checksumKind"] == "unknown"
    assert by_type["execution_manifest"]["recordedChecksum"] is None


def test_existing_run_without_published_artifacts_is_empty_list(client: TestClient):
    response = client.get(list_url(run_id=OTHER_RUN_ID))
    assert response.status_code == 200, response.text
    assert response.json() == []


def test_temporary_and_failed_and_foreign_artifacts_are_not_listed(
    client: TestClient,
):
    artifact_ids = {
        item["artifactId"] for item in client.get(list_url()).json()
    }
    assert artifact_ids == set(ARTIFACT_IDS.values())
    assert TEMPORARY_ARTIFACT_ID not in artifact_ids
    assert FOREIGN_ARTIFACT_ID not in artifact_ids
    assert FAILED_ARTIFACT_ID not in artifact_ids


def test_failed_run_lists_nothing(client: TestClient):
    response = client.get(list_url(run_id=FAILED_RUN_ID))
    assert response.status_code == 200, response.text
    assert response.json() == []


# ---------------------------------------------------------------------------
# AC1: uniform 404 parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case_id,run_id",
    [
        (CASE_ID, "run-f19-unknown"),
        (OTHER_CASE_ID, RUN_ID),
        ("case-f19-unknown", RUN_ID),
    ],
)
def test_unknown_case_or_run_is_uniform_404(
    client: TestClient, case_id: str, run_id: str
):
    list_response = client.get(list_url(case_id, run_id))
    download_response = client.get(
        download_url(ARTIFACT_IDS["report_markdown"], case_id=case_id, run_id=run_id)
    )
    assert list_response.status_code == 404, list_response.text
    assert download_response.status_code == 404, download_response.text
    assert list_response.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}
    assert download_response.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}


@pytest.mark.parametrize(
    "case_id,run_id,artifact_id",
    [
        # The artifact belongs to a different run of the same case.
        (CASE_ID, OTHER_RUN_ID, ARTIFACT_IDS["report_markdown"]),
        # The artifact belongs to another case.
        (CASE_ID, RUN_ID, FOREIGN_ARTIFACT_ID),
        # Temporary/unpublished stage attempt.
        (CASE_ID, RUN_ID, TEMPORARY_ARTIFACT_ID),
        # Artifact of a run that did not succeed.
        (CASE_ID, FAILED_RUN_ID, FAILED_ARTIFACT_ID),
        # Unknown artifact id.
        (CASE_ID, RUN_ID, "artifact-f19-unknown"),
    ],
)
def test_wrong_run_or_owner_artifact_is_uniform_404(
    client: TestClient, case_id: str, run_id: str, artifact_id: str
):
    response = client.get(download_url(artifact_id, case_id=case_id, run_id=run_id))
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}


def test_artifact_wrong_case_id_is_404_but_other_artifacts_still_work(
    client: TestClient,
):
    update_artifact(ARTIFACT_IDS["report_markdown"], case_id=OTHER_CASE_ID)
    response = client.get(download_url(ARTIFACT_IDS["report_markdown"]))
    assert response.status_code == 404
    assert response.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}
    assert len(client.get(list_url()).json()) == 2


def test_missing_file_and_missing_recorded_path_are_uniform_404(
    client: TestClient, workspace: Path
):
    (run_directory(workspace) / "topic_report.md").unlink()
    missing_file = client.get(download_url(ARTIFACT_IDS["report_markdown"]))
    assert missing_file.status_code == 404, missing_file.text
    assert missing_file.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}
    # Listing is not a file-existence claim: the descriptor is still listed.
    assert len(client.get(list_url()).json()) == 3

    update_artifact(ARTIFACT_IDS["report_json"], path=None)
    missing_path = client.get(download_url(ARTIFACT_IDS["report_json"]))
    assert missing_path.status_code == 404
    assert missing_path.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}


def test_unknown_artifact_type_is_not_served(client: TestClient):
    update_artifact(ARTIFACT_IDS["report_json"], artifact_type="stage_output")
    response = client.get(download_url(ARTIFACT_IDS["report_json"]))
    assert response.status_code == 404
    assert response.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}
    assert len(client.get(list_url()).json()) == 2


# ---------------------------------------------------------------------------
# AC2: traversal, symlink and cross-run escapes
# ---------------------------------------------------------------------------


def test_symlinked_file_is_rejected(client: TestClient, workspace: Path, tmp_path):
    outside = tmp_path / "outside-secret.md"
    outside.write_bytes(b"# secret that must never be served\n")
    target = run_directory(workspace) / "topic_report.md"
    target.unlink()
    target.symlink_to(outside)

    response = client.get(download_url(ARTIFACT_IDS["report_markdown"]))
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}
    assert b"secret that must never be served" not in response.content


def test_symlinked_run_component_is_rejected(client: TestClient, workspace: Path, tmp_path):
    real = run_directory(workspace)
    escaped = tmp_path / "escaped-run"
    real.rename(escaped)
    real.symlink_to(escaped, target_is_directory=True)

    response = client.get(download_url(ARTIFACT_IDS["report_json"]))
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}


@pytest.mark.parametrize("artifact_type", sorted(ARTIFACT_IDS))
def test_intermediate_directory_symlink_is_rejected(
    client: TestClient, workspace: Path, tmp_path: Path, artifact_type: str
):
    """A symlink swapped in *between* the root and the file is refused.

    The link target is a directory that stays inside the container (and inside
    the disposable test tree) and holds the very bytes requested, so only an
    open-time ``O_NOFOLLOW`` walk can reject this: a lexical check would have
    passed and a plain ``open`` would have followed the link.
    """
    case_dir = workspace / "cases" / CASE_SLUG
    relocated = tmp_path / "relocated-runs"
    (case_dir / "runs").rename(relocated)
    (case_dir / "runs").symlink_to(relocated, target_is_directory=True)
    served_copy = relocated / RUN_ID / ARTIFACT_FILENAMES[artifact_type]
    assert served_copy.read_bytes() == FILE_BYTES[artifact_type]

    response = client.get(download_url(ARTIFACT_IDS[artifact_type]))
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}
    assert response.content != FILE_BYTES[artifact_type]


@pytest.mark.parametrize("artifact_type", sorted(ARTIFACT_IDS))
def test_final_component_symlink_inside_container_is_rejected(
    client: TestClient, workspace: Path, artifact_type: str
):
    """A final-component link to an in-container regular file is refused."""
    target = run_directory(workspace) / ARTIFACT_FILENAMES[artifact_type]
    decoy = run_directory(workspace) / "decoy.bin"
    decoy.write_bytes(b"decoy bytes that must never be served\n")
    target.unlink()
    target.symlink_to(decoy)

    response = client.get(download_url(ARTIFACT_IDS[artifact_type]))
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}
    assert b"decoy bytes" not in response.content


@pytest.mark.parametrize("mutation", ["parent_traversal", "cross_run", "other_name"])
def test_traversal_and_cross_run_paths_are_rejected(
    client: TestClient, workspace: Path, mutation: str
):
    run_dir = run_directory(workspace)
    if mutation == "parent_traversal":
        recorded = run_dir / ".." / ".." / "runs" / OTHER_RUN_ID / "topic_report.md"
    elif mutation == "cross_run":
        recorded = run_directory(workspace, run_id=OTHER_RUN_ID) / "topic_report.md"
    else:
        recorded = run_dir / "topic_analysis.json"
    update_artifact(ARTIFACT_IDS["report_markdown"], path=str(recorded))

    response = client.get(download_url(ARTIFACT_IDS["report_markdown"]))
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}


def test_unsafe_identifier_components_never_reach_the_filesystem(client: TestClient):
    # A tampered case slug must not turn the approved run root into an escape.
    session = db_session()
    try:
        case = session.get(TopicCase, CASE_ID)
        assert case is not None
        case.slug = "../../etc"
        session.commit()
    finally:
        session.close()

    response = client.get(download_url(ARTIFACT_IDS["report_markdown"]))
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}


# ---------------------------------------------------------------------------
# AC3: size cap and redacted OS errors
# ---------------------------------------------------------------------------


def test_oversize_artifact_returns_413_too_large(client: TestClient, workspace: Path):
    target = run_directory(workspace) / "topic_report.md"
    os.truncate(target, MAX_ARTIFACT_BYTES + 1)

    response = client.get(download_url(ARTIFACT_IDS["report_markdown"]))
    assert response.status_code == 413, response.text
    assert response.json() == {"detail": ARTIFACT_TOO_LARGE_DETAIL}
    assert response.content == b'{"detail":"too_large"}'
    assert str(workspace) not in response.text


def test_permission_failure_is_redacted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    secret_path = "/srv/secret/case/report.md"
    real_open = os.open

    def fake_open(path, flags, *args, **kwargs):
        if str(path).endswith("topic_report.md"):
            raise PermissionError(13, "Permission denied", secret_path)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(artifact_reader.os, "open", fake_open)

    response = client.get(download_url(ARTIFACT_IDS["report_markdown"]))
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}
    assert secret_path not in response.text
    assert "PermissionError" not in response.text
    assert "Permission denied" not in response.text


def test_non_regular_file_is_rejected(client: TestClient, workspace: Path):
    target = run_directory(workspace) / "topic_report.md"
    target.unlink()
    target.mkdir()  # a directory is not a servable artifact

    response = client.get(download_url(ARTIFACT_IDS["report_markdown"]))
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}


def descriptor_count() -> int:
    """Number of descriptors this process currently holds (Linux only)."""
    return len(os.listdir("/proc/self/fd"))


@pytest.mark.skipif(
    not Path("/proc/self/fd").is_dir(), reason="needs /proc/self/fd (Linux)"
)
@pytest.mark.parametrize("mutation", ["final_symlink", "runs_symlink"])
def test_rejected_reads_do_not_leak_descriptors(workspace: Path, mutation: str):
    """Every descriptor opened by a rejected walk is closed again.

    Covers both a failure at the last component and a failure at an
    intermediate component (the case-directory descriptor has to be closed by
    the error path). A leak would grow the count by one per call.
    """
    run_dir = run_directory(workspace)
    if mutation == "final_symlink":
        target = run_dir / "topic_report.md"
        target.unlink()
        target.symlink_to(workspace / "cases" / CASE_SLUG / "absent.md")
    else:
        case_dir = workspace / "cases" / CASE_SLUG
        (case_dir / "runs").rename(case_dir / "runs-relocated")
        (case_dir / "runs").symlink_to(
            case_dir / "runs-relocated", target_is_directory=True
        )

    session = db_session()
    try:

        def attempt() -> None:
            with pytest.raises(artifact_reader.ArtifactNotFound):
                artifact_reader.read_run_artifact(
                    session,
                    case_id=CASE_ID,
                    run_id=RUN_ID,
                    artifact_id=ARTIFACT_IDS["report_markdown"],
                    output_root=workspace,
                )

        for _ in range(3):  # warm any lazily opened descriptor first
            attempt()
        before = descriptor_count()
        for _ in range(100):
            attempt()
        after = descriptor_count()
    finally:
        session.close()
    assert after <= before, (before, after)


# ---------------------------------------------------------------------------
# Download contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("artifact_type", sorted(ARTIFACT_IDS))
def test_each_type_serves_its_checked_regular_file(
    workspace: Path, artifact_type: str
):
    """Positive control: a regular file per type is served byte-for-byte."""
    filename = ARTIFACT_FILENAMES[artifact_type]
    on_disk = (run_directory(workspace) / filename).read_bytes()
    assert on_disk == FILE_BYTES[artifact_type]

    session = db_session()
    try:
        download = artifact_reader.read_run_artifact(
            session,
            case_id=CASE_ID,
            run_id=RUN_ID,
            artifact_id=ARTIFACT_IDS[artifact_type],
            output_root=workspace,
        )
    finally:
        session.close()
    assert download.filename == filename
    assert download.content == on_disk
    assert download.size == len(on_disk) == len(download.content)


@pytest.mark.parametrize(
    "artifact_type,media_type",
    [
        ("report_markdown", "text/markdown"),
        ("report_json", "application/json"),
        ("execution_manifest", "application/json"),
    ],
)
def test_download_bytes_media_type_and_headers(
    client: TestClient, artifact_type: str, media_type: str
):
    response = client.get(download_url(ARTIFACT_IDS[artifact_type]))
    assert response.status_code == 200, response.text
    assert response.content == FILE_BYTES[artifact_type]
    assert response.headers["content-type"].startswith(media_type)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-length"] == str(len(FILE_BYTES[artifact_type]))
    assert len(response.content) == len(FILE_BYTES[artifact_type])

    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert ARTIFACT_FILENAMES[artifact_type] in disposition
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert ARTIFACT_IDS[artifact_type] in disposition


# ---------------------------------------------------------------------------
# AC4: GET makes no writes; reader has no write helpers
# ---------------------------------------------------------------------------


def test_mixed_get_batch_leaves_output_tree_unchanged(
    client: TestClient, workspace: Path
):
    before = tree_digest(workspace)

    mixed_requests = [
        list_url(),
        list_url(run_id=OTHER_RUN_ID),
        list_url(run_id=FAILED_RUN_ID),
        list_url(case_id=OTHER_CASE_ID, run_id=RUN_ID),
        download_url(ARTIFACT_IDS["report_markdown"]),
        download_url(ARTIFACT_IDS["report_json"]),
        download_url(ARTIFACT_IDS["execution_manifest"]),
        download_url(ARTIFACT_IDS["report_markdown"], run_id=OTHER_RUN_ID),
        download_url("artifact-f19-unknown"),
        download_url(TEMPORARY_ARTIFACT_ID),
        download_url(FOREIGN_ARTIFACT_ID),
    ]
    statuses = [client.get(url).status_code for url in mixed_requests]
    assert statuses == [200, 200, 200, 404, 200, 200, 200, 404, 404, 404, 404]

    after = tree_digest(workspace)
    assert after == before


READER_PATH = Path(artifact_reader.__file__)
READER_SOURCE = READER_PATH.read_text(encoding="utf-8")


def test_reader_source_has_no_directory_or_file_creators():
    for forbidden in ("mkdir", "makedirs", "touch", "write_bytes", "write_text"):
        assert forbidden not in READER_SOURCE, forbidden
    assert "rmtree" not in READER_SOURCE
    assert "unlink" not in READER_SOURCE


def test_reader_source_has_no_write_mode_open():
    """No ``open``/``fdopen`` call may pass a writable mode string."""
    tree = ast.parse(READER_SOURCE)
    calls = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else (
            func.id if isinstance(func, ast.Name) else ""
        )
        if name not in {"open", "fdopen"}:
            continue
        calls += 1
        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                assert not any(flag in argument.value for flag in "wax+"), (
                    argument.value
                )
        for keyword in node.keywords:
            if isinstance(keyword.value, ast.Constant) and isinstance(
                keyword.value.value, str
            ):
                assert not any(flag in keyword.value.value for flag in "wax+"), (
                    keyword.value.value
                )
    # The reader must still open its own descriptor read-only.
    assert calls >= 1


def test_reader_source_does_not_import_writer_helpers():
    tree = ast.parse(READER_SOURCE)
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)

    assert not any(
        module.startswith("src.cases.service") for module in imported_modules
    ), imported_modules
    for helper in (
        "_publish_successful_run",
        "_write_report_bundle",
        "_run_report_dir",
        "_assert_report_path_contained",
        "CaseRunContext",
    ):
        assert helper not in READER_SOURCE, helper


def test_reader_walks_components_relative_to_open_descriptors():
    """The symlink guard must be the open itself, not a lexical pre-check.

    A lexical ``is_symlink`` walk still passes the behavioural tests above (a
    statically planted link is caught either way) yet leaves the
    check-then-open window open, so assert the descriptor-relative walk -- the
    portable ``openat`` semantics -- is what the reader really uses.
    """
    assert "dir_fd=" in READER_SOURCE
    assert "os.O_NOFOLLOW" in READER_SOURCE
    assert "os.O_DIRECTORY" in READER_SOURCE
    assert "is_symlink" not in READER_SOURCE


# ---------------------------------------------------------------------------
# Snapshot selector consistency
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("selector", ["snapshotId=snap-x", "snapshot_id=snap-x"])
def test_snapshot_selector_is_rejected(client: TestClient, selector: str):
    response = client.get(f"{list_url()}?{selector}")
    assert response.status_code == 422, response.text
    download = client.get(f"{download_url(ARTIFACT_IDS['report_markdown'])}?{selector}")
    assert download.status_code == 422, download.text


# ---------------------------------------------------------------------------
# AC6: the HTTP readers use the operator-configured output root
#
# These tests publish through the real writer (``materialize`` runs the case
# service and its publication step), then read the same run back through an app
# built from ``create_app()``. Only ``TRIANGULATE_OUTPUT_ROOT`` is configured;
# ``get_artifact_output_root`` is never overridden, so a mismatch between the
# writer's root and the reader's root would fail here.
# ---------------------------------------------------------------------------


def published_artifact_rows(case_id: str, run_id: str):
    """(artifact id, type, recorded path) for one run's publishable artifacts."""
    session = db_session()
    try:
        rows = session.execute(
            select(CaseArtifact)
            .join(CaseStageRun, CaseArtifact.stage_run_id == CaseStageRun.id)
            .where(
                CaseArtifact.case_id == case_id,
                CaseStageRun.case_id == case_id,
                CaseStageRun.investigation_run_id == run_id,
                CaseArtifact.artifact_type.in_(tuple(ARTIFACT_FILENAMES)),
            )
        ).scalars()
        return [
            (artifact.id, artifact.artifact_type, artifact.path or "")
            for artifact in rows
        ]
    finally:
        session.close()


def configured_app(monkeypatch, root: str | Path | None):
    """Build a fresh app after configuring the single operator setting."""
    if root is None:
        monkeypatch.delenv(OUTPUT_ROOT_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(OUTPUT_ROOT_ENV_VAR, str(root))
    fresh = create_app()
    # Historical readers use the app's startup-captured database path; bind the
    # test fixture's disposable database explicitly.
    fresh.state.database_path = Path(get_database().db_path)
    return fresh


@pytest.fixture(scope="module")
def published_workspace(tmp_path_factory):
    """Real-writer publication into a non-default scratch root (once)."""
    out = tmp_path_factory.mktemp("r04-published") / "scratch-output"
    manifest = materialize(out)
    return out, manifest


@pytest.fixture
def published(published_workspace):
    """Re-point the shared application database at the published fixture DB."""
    out, manifest = published_workspace
    init_database(str(out / "triangulate.db"))
    return out, manifest


def test_published_run_round_trips_under_absolute_configured_root(
    published, monkeypatch
):
    out, manifest = published
    case_id, run_id = manifest["caseId"], manifest["runId"]
    rows = published_artifact_rows(case_id, run_id)
    assert {artifact_type for _id, artifact_type, _path in rows} == set(
        ARTIFACT_FILENAMES
    )
    recorded = {kind: (artifact_id, path) for artifact_id, kind, path in rows}
    assert all(Path(path).is_absolute() for _id, _kind, path in rows)

    with TestClient(configured_app(monkeypatch, out)) as client:
        listing = client.get(list_url(case_id, run_id))
        assert listing.status_code == 200, listing.text
        assert str(out) not in listing.text
        descriptors = listing.json()
        assert {item["type"] for item in descriptors} == set(ARTIFACT_FILENAMES)

        for descriptor in descriptors:
            artifact_id, recorded_path = recorded[descriptor["type"]]
            assert descriptor["artifactId"] == artifact_id
            assert run_id in descriptor["downloadUrl"]
            download = client.get(descriptor["downloadUrl"])
            assert download.status_code == 200, download.text
            assert download.content == Path(recorded_path).read_bytes()
            assert download.headers["content-type"].startswith(
                ARTIFACT_MEDIA_TYPES[descriptor["type"]]
            )
            assert download.headers["x-content-type-options"] == "nosniff"
            disposition = download.headers["content-disposition"]
            assert disposition.startswith("attachment;")
            assert ARTIFACT_FILENAMES[descriptor["type"]] in disposition


def test_default_and_relative_roots_resolve_from_startup_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manifest = materialize(Path("output"))
    case_id, run_id = manifest["caseId"], manifest["runId"]
    rows = published_artifact_rows(case_id, run_id)
    assert rows
    # The writer recorded paths relative to the shared working directory.
    assert all(not Path(path).is_absolute() for _id, _kind, path in rows)

    # Unset (compatibility default ./output), an explicit relative custom root,
    # and the absolute representation of that same root must all agree.
    for configured in (None, "output", str(tmp_path / "output")):
        with TestClient(configured_app(monkeypatch, configured)) as client:
            listing = client.get(list_url(case_id, run_id))
            assert listing.status_code == 200, (configured, listing.text)
            assert "scratch" not in listing.text
            for descriptor in listing.json():
                download = client.get(descriptor["downloadUrl"])
                assert download.status_code == 200, (configured, download.text)


def test_artifact_under_a_different_configured_root_is_a_uniform_miss(
    published, tmp_path, monkeypatch
):
    out, manifest = published
    case_id, run_id = manifest["caseId"], manifest["runId"]
    unrelated_root = tmp_path / "unrelated-root"

    with TestClient(configured_app(monkeypatch, unrelated_root)) as client:
        listing = client.get(list_url(case_id, run_id))
        # The row still lists (listing is metadata), but no bytes resolve there.
        assert listing.status_code == 200, listing.text
        descriptors = listing.json()
        assert descriptors
        for descriptor in descriptors:
            response = client.get(descriptor["downloadUrl"])
            assert response.status_code == 404
            assert response.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}
            assert str(out) not in response.text
            assert str(unrelated_root) not in response.text

    # A read path never creates the configured root.
    assert not unrelated_root.exists()


def test_absolute_record_matches_relative_configured_root(
    workspace: Path, tmp_path: Path, monkeypatch
):
    """The inverse representation pair: absolute stored path, relative setting."""
    monkeypatch.chdir(tmp_path)
    assert workspace == tmp_path / "output"

    with TestClient(configured_app(monkeypatch, "output")) as client:
        download = client.get(download_url(ARTIFACT_IDS["report_markdown"]))
        assert download.status_code == 200, download.text
        assert download.content == FILE_BYTES["report_markdown"]


def test_reads_do_not_create_an_absent_configured_root(tmp_path, monkeypatch):
    absent = tmp_path / "absent-root"
    with TestClient(configured_app(monkeypatch, absent)) as client:
        response = client.get(list_url(case_id="case-r04-missing", run_id="run-r04"))
        assert response.status_code == 404
        assert response.json() == {"detail": ARTIFACT_NOT_FOUND_DETAIL}
        assert str(absent) not in response.text
    assert not absent.exists()


class TestOutputRootResolution:
    """The operator setting resolves lexically, once, and without file access."""

    def test_precedence_and_blank_default(self, tmp_path, monkeypatch):
        startup = tmp_path / "startup-cwd"
        monkeypatch.setenv(OUTPUT_ROOT_ENV_VAR, "from-env")
        assert resolve_output_root(cwd=startup) == startup / "from-env"
        # An explicit value (used by app construction) beats the environment.
        assert resolve_output_root("explicit", cwd=startup) == startup / "explicit"
        # But the app itself passes only the captured cwd, so env is the input.
        for blank in ("", "   "):
            monkeypatch.setenv(OUTPUT_ROOT_ENV_VAR, blank)
            assert resolve_output_root(cwd=startup) == startup / "output"
        monkeypatch.delenv(OUTPUT_ROOT_ENV_VAR, raising=False)
        assert resolve_output_root(cwd=startup) == startup / "output"
        assert DEFAULT_OUTPUT_ROOT == Path("./output")
        assert not startup.exists()

    def test_absolute_and_redundant_forms_normalize_lexically(
        self, tmp_path, monkeypatch
    ):
        startup = tmp_path / "startup-cwd"
        absolute = tmp_path / "elsewhere" / "root"
        assert resolve_output_root(absolute, cwd=startup) == absolute
        assert resolve_output_root(str(absolute), cwd=startup) == absolute
        assert resolve_output_root("nested/./root", cwd=startup) == (
            startup / "nested" / "root"
        )
        monkeypatch.setenv(OUTPUT_ROOT_ENV_VAR, "./output/")
        assert resolve_output_root(cwd=startup) == startup / "output"
        assert not startup.exists()
        assert not absolute.exists()

    @pytest.mark.parametrize("unsafe", ["../escape", "cases/../../escape", "a/\x00b"])
    def test_unsafe_configuration_is_rejected_before_normalization(
        self, unsafe, tmp_path
    ):
        with pytest.raises(ValueError):
            resolve_output_root(unsafe, cwd=tmp_path / "startup")
