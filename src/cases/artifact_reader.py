"""Read-only historical run artifacts (F19 / X02).

This is a focused, **pure** reader for the report files the writer published for
a successfully finalized grouped investigation run (``InvestigationRun``). It
resolves descriptors and file bytes; it never creates, repairs, publishes or
re-indexes anything. No writer directory-creation or report-writing helper from
``src/cases/service.py`` is imported or called here, so a GET can never create a
directory or a file.

Ownership is proved through the persisted join, not assumed:

* ``artifact.case_id == case_id`` and ``stage_run.case_id == case_id``;
* ``stage_run.investigation_run_id == run_id`` (``CaseArtifact`` has no direct
  grouped-run FK, so the bridge is ``artifact.stage_run_id == stage_run.id``);
* the owning grouped run is ``SUCCEEDED`` -- only a successfully published run
  can have published report artifacts. A temporary/unpublished stage attempt
  (``investigation_run_id`` null) is never served.

Honest checksum semantics: the stored ``CaseArtifact.checksum`` is the canonical
JSON **payload** checksum computed by the writer at publication
(``_payload_checksum``), never a checksum of the file bytes. A descriptor labels
it ``payload_json`` only when the stored payload is present and re-hashes to the
recorded value, and ``unknown`` otherwise. The markdown artifact stores no
payload, so its recorded value (a path-descriptor hash) is ``unknown``.

File resolution never takes a client path:

* the approved run root is ``output_root/cases/{case.slug}/runs/{run_id}``;
* the filename per type is a fixed constant (``ARTIFACT_FILENAMES``);
* the recorded ``CaseArtifact.path`` must lexically equal that run root's fixed
  file after relative paths are joined to the documented working directory
  (``cwd``). There are no ``..`` components and no same-basename shortcut --
  anything else is a uniform miss (no nearby-run or latest fallback);
* the run root is opened once and every component below the case directory is
  then opened *relative to the previous directory descriptor* with ``O_NOFOLLOW``
  (``O_DIRECTORY`` for intermediates) -- the portable ``openat`` equivalent of a
  ``RESOLVE_BENEATH`` walk. A component swapped to a symlink after the
  containment check is refused by the kernel (``ELOOP``/``ENOTDIR``) instead of
  being followed, so there is no check-then-follow window;
* the served bytes come from the descriptor whose ``fstat`` proved a regular
  file inside the size cap, so the checked file is the served file.

Every OS-level failure (missing file, permission denied, wrong file type, a
changed size) is redacted: callers see one uniform miss and never the path or
the exception text.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage import (
    CaseArtifact,
    CaseStageRun,
    InvestigationRun,
    InvestigationRunStatus,
    TopicCase,
)

ARTIFACT_TYPE_EXECUTION_MANIFEST = "execution_manifest"
ARTIFACT_TYPE_REPORT_JSON = "report_json"
ARTIFACT_TYPE_REPORT_MARKDOWN = "report_markdown"

#: The only artifact types a successful publication writes; nothing else is
#: eligible, even if some legacy row carries another type.
ALLOWED_ARTIFACT_TYPES: tuple[str, ...] = (
    ARTIFACT_TYPE_EXECUTION_MANIFEST,
    ARTIFACT_TYPE_REPORT_JSON,
    ARTIFACT_TYPE_REPORT_MARKDOWN,
)

#: Fixed filename per published type (the writer's publication step). A
#: download never accepts a filename from the request or from the recorded path.
ARTIFACT_FILENAMES: dict[str, str] = {
    ARTIFACT_TYPE_EXECUTION_MANIFEST: "manifest.json",
    ARTIFACT_TYPE_REPORT_JSON: "topic_analysis.json",
    ARTIFACT_TYPE_REPORT_MARKDOWN: "topic_report.md",
}

ARTIFACT_MEDIA_TYPES: dict[str, str] = {
    ARTIFACT_TYPE_EXECUTION_MANIFEST: "application/json",
    ARTIFACT_TYPE_REPORT_JSON: "application/json",
    ARTIFACT_TYPE_REPORT_MARKDOWN: "text/markdown",
}

CHECKSUM_KIND_PAYLOAD_JSON = "payload_json"
CHECKSUM_KIND_UNKNOWN = "unknown"

#: Hard cap; a larger recorded artifact is refused rather than partially served.
MAX_ARTIFACT_BYTES = 50 * 1024 * 1024

#: Uniform, non-leaky miss message. Never include a filesystem path here.
ARTIFACT_NOT_FOUND_MESSAGE = "artifact not found"


class ArtifactNotFound(Exception):
    """Any ownership/path/OS miss; deliberately carries no path or OS error."""

    def __init__(self) -> None:
        super().__init__(ARTIFACT_NOT_FOUND_MESSAGE)


class ArtifactTooLarge(Exception):
    """The recorded file exceeds :data:`MAX_ARTIFACT_BYTES`."""

    def __init__(self) -> None:
        super().__init__("too_large")


@dataclass(frozen=True)
class ArtifactDownload:
    """Checked bytes plus the fixed metadata a download response needs."""

    content: bytes
    media_type: str
    filename: str
    size: int


def _canonical_payload_checksum(payload: Any) -> str:
    """Mirror the writer's canonical payload checksum without importing it.

    The publication step stores a canonical JSON payload checksum; this is the
    same canonicalization (sorted keys, ``str`` fallback) so a descriptor can say
    honestly whether the recorded value really is the payload checksum.
    """
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _checksum_kind(artifact: CaseArtifact) -> str:
    if artifact.payload_json is None or not artifact.checksum:
        return CHECKSUM_KIND_UNKNOWN
    if _canonical_payload_checksum(artifact.payload_json) != artifact.checksum:
        return CHECKSUM_KIND_UNKNOWN
    return CHECKSUM_KIND_PAYLOAD_JSON


def _download_url(case_id: str, run_id: str, artifact_id: str) -> str:
    """Relative API URL for one descriptor; identifiers are percent-encoded."""
    return (
        f"/api/cases/{quote(case_id, safe='')}"
        f"/investigation-runs/{quote(run_id, safe='')}"
        f"/artifacts/{quote(artifact_id, safe='')}"
    )


def _descriptor(artifact: CaseArtifact, case_id: str, run_id: str) -> dict[str, Any]:
    artifact_type = artifact.artifact_type
    return {
        "artifactId": artifact.id,
        "type": artifact_type,
        "displayName": ARTIFACT_FILENAMES[artifact_type],
        "downloadUrl": _download_url(case_id, run_id, artifact.id),
        "recordedChecksum": artifact.checksum,
        "checksumKind": _checksum_kind(artifact),
    }


def _published_run(session: Session, case_id: str, run_id: str) -> InvestigationRun | None:
    """The owning grouped run, or ``None`` for an unknown/wrong-case run."""
    run = session.get(InvestigationRun, run_id)
    if run is None or run.case_id != case_id:
        return None
    return run


def list_run_artifacts(
    session: Session, *, case_id: str, run_id: str
) -> list[dict[str, Any]] | None:
    """Descriptors of one run's published report artifacts, sorted stably.

    ``None`` means an unknown or wrong-case run (the route answers a uniform
    404). An existing run without eligible published reports -- including a run
    that never succeeded -- is an empty list (``200 []``). Listing is not a
    file-existence claim: bytes are checked when downloading.
    """
    run = _published_run(session, case_id, run_id)
    if run is None:
        return None
    if run.status != InvestigationRunStatus.SUCCEEDED:
        return []

    artifacts = (
        session.execute(
            select(CaseArtifact)
            .join(CaseStageRun, CaseArtifact.stage_run_id == CaseStageRun.id)
            .where(
                CaseArtifact.case_id == case_id,
                CaseStageRun.case_id == case_id,
                CaseStageRun.investigation_run_id == run_id,
                CaseArtifact.artifact_type.in_(ALLOWED_ARTIFACT_TYPES),
            )
        )
        .scalars()
        .all()
    )
    return [
        _descriptor(artifact, case_id, run_id)
        for artifact in sorted(artifacts, key=lambda item: (item.artifact_type, item.id))
    ]


def _is_safe_component(value: str) -> bool:
    """Reject a stored identifier that could turn a path join into an escape."""
    if not value or value in {".", ".."}:
        return False
    if "/" in value or "\\" in value or "\x00" in value:
        return False
    return Path(value).name == value


def _run_directory(output_root: Path, slug: str, run_id: str) -> tuple[Path, Path]:
    """Approved ``(case_dir, run_dir)``; never created, only addressed."""
    if not _is_safe_component(slug) or not _is_safe_component(run_id):
        raise ArtifactNotFound
    case_dir = Path(output_root) / "cases" / slug
    return case_dir, case_dir / "runs" / run_id


#: Fixed descendant chain from the case directory to a published report file.
_RUNS_COMPONENT = "runs"


def _lexically_resolved(path: Path, cwd: Path) -> Path:
    """Join a relative path to ``cwd`` and normalize it without resolving links.

    ``Path.resolve`` would consult the filesystem (and follow a symlink planted
    between the check and the open), so containment is decided lexically: the
    recorded path is attributed to the documented working directory, nothing
    else. A legacy path recorded from a different working directory therefore
    fails closed instead of being matched by guesswork.
    """
    if path.is_absolute():
        return Path(os.path.normpath(path))
    return Path(os.path.normpath(cwd / path))


def _checked_artifact_location(
    *,
    output_root: Path,
    cwd: Path,
    run_id: str,
    slug: str,
    artifact: CaseArtifact,
    filename: str,
) -> tuple[Path, tuple[str, ...]]:
    """Validate the recorded path; return the case root and the chain below it.

    The result is ``(case_dir, ("runs", run_id, filename))``. Nothing below the
    case root is resolved again by path: each of those components is opened one
    at a time against its parent's directory descriptor, so this check and the
    open cannot disagree about which entry is read.
    """
    recorded = artifact.path
    if not recorded:
        raise ArtifactNotFound
    recorded_path = Path(recorded)
    if ".." in recorded_path.parts:
        raise ArtifactNotFound
    if recorded_path.name != filename:
        raise ArtifactNotFound

    case_dir, run_dir = _run_directory(output_root, slug, run_id)
    # The recorded path must name exactly this run's fixed file. Comparing the
    # expected path is stricter than a containment check and never infers a
    # different root from the record. A path that names another run, escapes,
    # or was recorded under a different working directory is a uniform miss.
    expected = _lexically_resolved(run_dir / filename, cwd)
    if _lexically_resolved(recorded_path, cwd) != expected:
        raise ArtifactNotFound

    return case_dir, (_RUNS_COMPONENT, run_id, filename)


def _open_checked_handle(case_dir: Path, parts: tuple[str, ...]) -> int:
    """Open ``parts`` below ``case_dir`` one descriptor-relative step at a time.

    Opening each component with ``dir_fd`` plus ``O_NOFOLLOW`` (and
    ``O_DIRECTORY`` for every intermediate component) is the portable ``openat``
    equivalent of a beneath-root walk: the kernel resolves exactly one component
    against an already-open directory, so a component swapped to a symlink
    between the containment check and the open is refused (``ELOOP`` or
    ``ENOTDIR``) rather than followed. ``case_dir`` is the operator-configured
    case directory and may itself be a symlink; every component below it is
    opened ``O_NOFOLLOW``.

    Returns the descriptor of the final component (the caller owns it) and
    leaves no descriptor open on any failure path.
    """
    if not parts:
        raise ArtifactNotFound
    try:
        parent_fd = os.open(case_dir, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as exc:
        raise ArtifactNotFound from exc
    handle_fd = -1
    try:
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            flags = os.O_RDONLY | os.O_NOFOLLOW
            if not last:
                flags |= os.O_DIRECTORY
            next_fd = os.open(part, flags, dir_fd=parent_fd)
            os.close(parent_fd)
            if last:
                parent_fd = -1
                handle_fd = next_fd
            else:
                parent_fd = next_fd
    except OSError as exc:
        raise ArtifactNotFound from exc
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)
    return handle_fd


def _read_checked_file(case_dir: Path, parts: tuple[str, ...]) -> bytes:
    """Read the file opened by :func:`_open_checked_handle` from that handle.

    ``fstat`` inspects the very descriptor the bytes come from, so a swap
    between check and read cannot redirect the response to another file. A size
    change observed while reading is refused rather than served unchecked, and
    the descriptor is closed on every path.
    """
    descriptor = _open_checked_handle(case_dir, parts)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ArtifactNotFound
        size = info.st_size
        if size > MAX_ARTIFACT_BYTES:
            raise ArtifactTooLarge
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            content = handle.read(size)
            grew = handle.read(1)
    except ArtifactTooLarge:
        raise
    except OSError as exc:
        raise ArtifactNotFound from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(content) != size or grew:
        raise ArtifactNotFound
    return content


def read_run_artifact(
    session: Session,
    *,
    case_id: str,
    run_id: str,
    artifact_id: str,
    output_root: Path,
    cwd: Path | None = None,
) -> ArtifactDownload:
    """Checked bytes of one published report artifact.

    ``cwd`` is the documented working directory a relative recorded path is
    attributed to (the app passes the directory captured at startup). Every
    refusal -- unknown/wrong-case run, wrong-run or wrong-owner artifact,
    unlisted type, missing/oversized/unreadable file, symlink or traversal --
    raises :class:`ArtifactNotFound` (or :class:`ArtifactTooLarge` for the size
    cap). There is never an inline, latest or nearby-run fallback.
    """
    working_dir = Path.cwd() if cwd is None else Path(cwd)
    run = _published_run(session, case_id, run_id)
    if run is None or run.status != InvestigationRunStatus.SUCCEEDED:
        raise ArtifactNotFound

    row = session.execute(
        select(CaseArtifact, CaseStageRun)
        .join(CaseStageRun, CaseArtifact.stage_run_id == CaseStageRun.id)
        .where(CaseArtifact.id == artifact_id)
    ).first()
    if row is None:
        raise ArtifactNotFound
    artifact, stage_run = row
    if artifact.case_id != case_id:
        raise ArtifactNotFound
    if stage_run.case_id != case_id or stage_run.investigation_run_id != run_id:
        raise ArtifactNotFound
    filename = ARTIFACT_FILENAMES.get(artifact.artifact_type)
    if filename is None:
        raise ArtifactNotFound

    case = session.get(TopicCase, case_id)
    if case is None:
        raise ArtifactNotFound
    case_dir, parts = _checked_artifact_location(
        output_root=output_root,
        cwd=working_dir,
        run_id=run_id,
        slug=case.slug,
        artifact=artifact,
        filename=filename,
    )
    content = _read_checked_file(case_dir, parts)
    return ArtifactDownload(
        content=content,
        media_type=ARTIFACT_MEDIA_TYPES[artifact.artifact_type],
        filename=filename,
        size=len(content),
    )
