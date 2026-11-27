"""FastAPI application for the frontend-facing HTTP API."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.exc import DatabaseError, InternalError, OperationalError
from sqlalchemy.orm import Session

from src.cases import TopicCaseService
from src.runtime import configured_database_path
from src.settings import resolve_database_path, resolve_output_root
from src.storage import (
    Base,
    CaseWriterConflict,
    begin_read_transaction,
    open_read_only_session,
)
from src.cases.artifact_reader import (
    ArtifactNotFound,
    ArtifactTooLarge,
    list_run_artifacts,
    read_run_artifact,
)
from src.cases.comparison import (
    DEFAULT_COMPARISON_LIMIT,
    MAX_COMPARISON_LIMIT,
    ComparisonInvalid,
    ComparisonNotFound,
)
from src.cases.readers import CaptureRangeError, SnapshotNotFound
from src.cases.snapshot_comparison import (
    SnapshotComparisonInvalid,
    SnapshotComparisonNotFound,
    read_snapshot_comparison,
)
from src.cases.search import (
    DEFAULT_SEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
    MAX_SEARCH_OFFSET,
    SearchIndexUnavailable,
    SearchInvalid,
    SearchNotFound,
)
from .dependencies import get_case_service
from .mappers import (
    map_artifact_descriptor,
    map_comparison,
    map_capture_window,
    map_case_detail,
    map_case_list_item,
    map_citation_detail,
    map_claim_detail,
    map_claims_overview,
    map_evidence_detail,
    map_evaluation_summary,
    map_investigation_run_detail,
    map_investigation_run_list,
    map_monitoring_summary,
    map_review_activity,
    map_run_changes,
    map_search,
    map_snapshot_comparison,
    map_snapshot_summary,
    map_source_summary,
)
from .schemas import (
    AnnotationCreateRequest,
    ArtifactDescriptorDTO,
    CaptureWindowDTO,
    CaseDetailResponse,
    CaseListItem,
    CitationDTO,
    ClaimDetailDTO,
    ComparisonDTO,
    ClaimsOverviewResponse,
    EvidenceDetailDTO,
    EvaluationSummaryDTO,
    ExceptionActionRequest,
    HealthResponse,
    InvestigationRunDetailDTO,
    InvestigationRunListDTO,
    MonitoringSummaryDTO,
    ReviewActionRequest,
    ReviewActivityDTO,
    ReviewAnnotationDTO,
    RunChangesDTO,
    SearchResponseDTO,
    SnapshotComparisonDTO,
    SnapshotSummaryDTO,
    SourceSummaryDTO,
    WorkflowDiagnosticsDTO,
)


router = APIRouter()

# Historical readers are opt-in per route. A route that reads current committed
# state rejects a supplied snapshot selector explicitly instead of silently
# ignoring it, so a caller can never believe it is reading historical state when
# it is reading the latest rows.
UNSUPPORTED_SNAPSHOT_SELECTOR_MESSAGE = (
    "This reader does not support snapshot selection; omit snapshotId/snapshot_id "
    "or use the snapshot-aware claim, evidence or comparison reader."
)

_DEFAULT_CAPTURE_WINDOW_LENGTH = 20000
_MAX_CAPTURE_WINDOW_LENGTH = 50000

_SNAPSHOT_SELECTOR_NAMES = ("snapshotId", "snapshot_id")


def reject_snapshot_selector(request: Request) -> None:
    """422 when an unsupported reader route is given a snapshot selector.

    FastAPI ignores unknown query parameters, so an unguarded current-state
    reader would answer with live rows while the caller believed it had pinned a
    historical observation.
    """
    for name in _SNAPSHOT_SELECTOR_NAMES:
        if name in request.query_params:
            raise HTTPException(
                status_code=422, detail=UNSUPPORTED_SNAPSHOT_SELECTOR_MESSAGE
            )


def _resolve_snapshot_selector(
    snapshot_id: str | None, snapshot_id_snake: str | None
) -> str | None:
    """Resolve an optional snapshot selector or reject a malformed/ambiguous one."""
    if (
        snapshot_id is not None
        and snapshot_id_snake is not None
        and snapshot_id != snapshot_id_snake
    ):
        raise HTTPException(
            status_code=422,
            detail="Conflicting snapshotId and snapshot_id selectors were supplied",
        )
    selector = snapshot_id if snapshot_id is not None else snapshot_id_snake
    if selector is not None and not selector.strip():
        raise HTTPException(status_code=422, detail="snapshotId must not be empty")
    return selector


def _entity_not_found_detail(
    entity: str,
    entity_id: str,
    case_id: str,
    snapshot_id: str | None,
) -> str:
    if snapshot_id is None:
        return f"{entity} {entity_id} not found for case {case_id}"
    return (
        f"{entity} {entity_id} is not present in snapshot {snapshot_id} for case "
        f"{case_id}"
    )


def _load_case_detail_or_404(service: TopicCaseService, case_id: str) -> CaseDetailResponse:
    detail = service.get_case_details(case_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return map_case_detail(detail)


def _load_raw_case_detail_or_404(service: TopicCaseService, case_id: str) -> dict:
    detail = service.get_case_details(case_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return detail


def _post_write_error(exc: ValueError) -> HTTPException:
    """Map the narrow HITL POST writers' ``ValueError`` to an explicit status.

    Scoped to the three review/exception/annotation handlers only: a missing
    case or exception is a 404, while every other domain validation error
    (unresolved exceptions, unsupported action, blank content) is a 422. This is
    deliberately not a global ``ValueError`` handler, and writer conflicts keep
    their existing ``CaseWriterConflict`` -> 409 response.
    """
    detail = str(exc)
    if detail.startswith(("Case ", "Exception ")) and " not found" in detail:
        return HTTPException(status_code=404, detail=detail)
    return HTTPException(status_code=422, detail=detail)


def _reader_missing_case_error(exc: ValueError, case_id: str) -> Exception:
    """Return the exception a case-owned GET reader should raise for ``exc``.

    Only the exact missing-case ``ValueError`` from the service readers becomes
    a 404; every other reader failure is returned unchanged so a genuine
    evaluation/activity read fault keeps propagating instead of being disguised
    as "case not found". The service layer keeps raising ``ValueError`` for
    direct/CLI callers.
    """
    if str(exc) == f"Case {case_id} not found":
        return HTTPException(status_code=404, detail=str(exc))
    return exc


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/api/cases", response_model=list[CaseListItem])
def list_cases(service: TopicCaseService = Depends(get_case_service)) -> list[CaseListItem]:
    return [map_case_list_item(case) for case in service.list_cases()]


@router.get(
    "/api/cases/{case_id}",
    response_model=CaseDetailResponse,
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_case(case_id: str, service: TopicCaseService = Depends(get_case_service)) -> CaseDetailResponse:
    return _load_case_detail_or_404(service, case_id)


@router.get(
    "/api/cases/{case_id}/claims",
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_case_claims(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.claims


@router.get(
    "/api/cases/{case_id}/claims/overview",
    response_model=ClaimsOverviewResponse,
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_case_claims_overview(
    case_id: str, service: TopicCaseService = Depends(get_case_service)
) -> ClaimsOverviewResponse:
    detail = _load_raw_case_detail_or_404(service, case_id)
    return map_claims_overview(detail)


# Registered *after* ``/claims/overview`` so the static route keeps winning.
@router.get("/api/cases/{case_id}/claims/{claim_id}", response_model=ClaimDetailDTO)
def get_case_claim_detail(
    case_id: str,
    claim_id: str,
    snapshot_id: str | None = Query(default=None, alias="snapshotId"),
    snapshot_id_snake: str | None = Query(default=None, alias="snapshot_id"),
    service: TopicCaseService = Depends(get_case_service),
) -> ClaimDetailDTO:
    """One claim with its evidence passages (GET-only; creates nothing).

    ``snapshotId`` resolves the claim from that immutable observation. An
    unknown/wrong-case snapshot is 404, as is a claim the snapshot does not
    contain; current rows are never substituted.
    """
    selector = _resolve_snapshot_selector(snapshot_id, snapshot_id_snake)
    try:
        payload = service.get_claim_detail(
            case_id, claim_id, snapshot_id=selector
        )
    except SnapshotNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=_entity_not_found_detail("Claim", claim_id, case_id, selector),
        )
    return map_claim_detail(payload)


def _resolve_claim_selector(
    claim_id: str | None, claim_id_snake: str | None
) -> str | None:
    """Resolve the optional claim selector or reject conflicting aliases."""
    if claim_id is not None and claim_id_snake is not None and claim_id != claim_id_snake:
        raise HTTPException(
            status_code=422,
            detail="Conflicting claimId and claim_id selectors were supplied",
        )
    return claim_id if claim_id is not None else claim_id_snake


@router.get(
    "/api/cases/{case_id}/sources",
    response_model=SourceSummaryDTO,
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_case_sources(
    case_id: str,
    claim_id: str | None = Query(default=None, alias="claimId"),
    claim_id_snake: str | None = Query(default=None, alias="claim_id"),
    service: TopicCaseService = Depends(get_case_service),
) -> SourceSummaryDTO:
    """Observed publishers and dependency groups (P01, read-only)."""
    selector = _resolve_claim_selector(claim_id, claim_id_snake)
    payload = service.get_source_summary(case_id, claim_id=selector)
    if payload is None:
        if selector is not None:
            raise HTTPException(
                status_code=404,
                detail=f"Claim {selector} not found for case {case_id}",
            )
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return map_source_summary(payload)


@router.get("/api/cases/{case_id}/comparison", response_model=ComparisonDTO)
def get_case_comparison(
    case_id: str,
    left: str = Query(..., description="Left evidence ID"),
    right: str = Query(..., description="Right evidence ID"),
    left_capture_id: str | None = Query(default=None, alias="leftCapture"),
    right_capture_id: str | None = Query(default=None, alias="rightCapture"),
    snapshot_id: str | None = Query(default=None, alias="snapshotId"),
    snapshot_id_snake: str | None = Query(default=None, alias="snapshot_id"),
    limit: int = Query(
        default=DEFAULT_COMPARISON_LIMIT,
        ge=1,
        le=MAX_COMPARISON_LIMIT,
    ),
    offset: int = Query(default=0, ge=0),
    service: TopicCaseService = Depends(get_case_service),
) -> ComparisonDTO:
    """Deterministic two-capture comparison (P02, read-only)."""
    selector = _resolve_snapshot_selector(snapshot_id, snapshot_id_snake)
    try:
        payload = service.get_comparison(
            case_id,
            left_evidence_id=left,
            right_evidence_id=right,
            left_capture_id=left_capture_id,
            right_capture_id=right_capture_id,
            limit=limit,
            offset=offset,
            snapshot_id=selector,
        )
    except ComparisonNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ComparisonInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return map_comparison(payload)


@router.get(
    "/api/cases/{case_id}/search",
    response_model=SearchResponseDTO,
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_case_search(
    case_id: str,
    q: str = Query(..., description="Literal all-term search query"),
    result_type: str | None = Query(default=None, alias="type"),
    publisher: str | None = Query(default=None),
    status: str | None = Query(default=None),
    published_from: str | None = Query(default=None, alias="publishedFrom"),
    published_to: str | None = Query(default=None, alias="publishedTo"),
    limit: int = Query(default=DEFAULT_SEARCH_LIMIT, ge=1, le=MAX_SEARCH_LIMIT),
    offset: int = Query(
        default=0,
        ge=0,
        le=MAX_SEARCH_OFFSET,
        description=f"Result offset, 0..{MAX_SEARCH_OFFSET}",
    ),
    service: TopicCaseService = Depends(get_case_service),
) -> SearchResponseDTO:
    """Case-scoped lexical search over the current-state FTS index (S02).

    Read-only: the handler never writes, rebuilds or repairs the index. Unknown
    case → 404, malformed query/filter → 422, unusable index capability → 503
    with the operator rebuild remedy. An empty valid result is a 200 with
    ``items: []`` and the real ``total``.
    """
    try:
        payload = service.search_case(
            case_id,
            q=q,
            result_type=result_type,
            publisher=publisher,
            status=status,
            published_from=published_from,
            published_to=published_to,
            limit=limit,
            offset=offset,
        )
    except SearchNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SearchInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SearchIndexUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Case search is unavailable for case {case_id}: {exc.reason} "
                "Operator remedy: run "
                f"`triangulate case rebuild-search {case_id}` and retry."
            ),
        ) from exc
    return map_search(payload)


@router.get(
    "/api/cases/{case_id}/investigation-runs",
    response_model=InvestigationRunListDTO,
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_investigation_runs(
    case_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: TopicCaseService = Depends(get_case_service),
) -> InvestigationRunListDTO:
    """Grouped investigation invocations, newest sequence first (read-only)."""
    payload = service.get_investigation_runs(case_id, limit=limit, offset=offset)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return map_investigation_run_list(payload)


@router.get(
    "/api/cases/{case_id}/investigation-runs/{run_id}",
    response_model=InvestigationRunDetailDTO,
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_investigation_run(
    case_id: str,
    run_id: str,
    service: TopicCaseService = Depends(get_case_service),
) -> InvestigationRunDetailDTO:
    payload = service.get_investigation_run(case_id, run_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation run {run_id} not found for case {case_id}",
        )
    return map_investigation_run_detail(payload)


@router.get(
    "/api/cases/{case_id}/investigation-runs/{run_id}/changes",
    response_model=RunChangesDTO,
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_investigation_run_changes(
    case_id: str,
    run_id: str,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: TopicCaseService = Depends(get_case_service),
) -> RunChangesDTO:
    """Stored delta for one run; pending/unavailable are distinct from empty."""
    payload = service.get_run_changes(
        case_id, run_id, limit=limit, offset=offset
    )
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation run {run_id} not found for case {case_id}",
        )
    return map_run_changes(payload)


#: One uniform miss body for the historical artifact reader. It never reveals
#: whether the case, run, artifact or file exists, nor which ownership check
#: failed, and never carries a filesystem path or OS error text.
ARTIFACT_NOT_FOUND_DETAIL = "Artifact not found for this case and run"
ARTIFACT_TOO_LARGE_DETAIL = "too_large"


def get_artifact_output_root(request: Request) -> Path:
    """Case output root captured once when the app was created.

    The value comes from the ``TRIANGULATE_OUTPUT_ROOT`` operator setting
    (default ``./output``) resolved against the startup working directory. It is
    never taken from a query, body or header, and never from an artifact row.
    """
    return request.app.state.output_root


#: One sanitized body for every storage-level historical-read failure. It never
#: carries a path, SQL text, driver message or a case/run/artifact existence hint.
HISTORICAL_STORAGE_UNAVAILABLE_DETAIL = "Historical storage is unavailable"

#: App-owned constant: the readiness probe never runs caller SQL, so a driver
#: failure it raises can only describe the configured store itself.
_SCHEMA_PRESENCE_SQL = "SELECT name FROM sqlite_master WHERE type = 'table'"


def _storage_unavailable() -> HTTPException:
    """The sanitized 503 for a readiness/connection failure of the store."""
    return HTTPException(status_code=503, detail=HISTORICAL_STORAGE_UNAVAILABLE_DETAIL)


def _is_store_damage(exc: DatabaseError) -> bool:
    """True only for driver errors that can only mean the store is unusable.

    pysqlite reports corruption (``SQLITE_CORRUPT``/``SQLITE_NOTADB``) as a bare
    ``DatabaseError``; every subclass -- ``OperationalError`` (bad SQL text or a
    bad column), ``ProgrammingError``, ``IntegrityError`` -- can be a defect in
    caller code, so it is classified by phase instead. No message matching.
    """
    return type(exc) is DatabaseError


def _missing_declared_tables(session: Session) -> frozenset[str]:
    """Declared model tables this store does not have (readiness, not data).

    Pure read-only inspection of ``sqlite_master``: an absent or partial schema is
    an unusable store, which is readiness, while a present schema with no matching
    row is simply data not found (the route's scoped 404).
    """
    present = {
        str(row[0])
        for row in session.connection().exec_driver_sql(_SCHEMA_PRESENCE_SQL)
    }
    return frozenset(Base.metadata.tables).difference(present)


def _historical_read_session(request: Request) -> Iterator[Session]:
    """One narrow read-only session for every historical GET.

    The path is the app's startup-captured canonical database; this dependency
    never consults the mutable global ``Database`` binding, so request order can
    not select storage. Opening is SQLite ``mode=ro`` on the existing file: no
    directory, database file, table, index, migration marker or domain row is
    created, and no service/taxonomy builder runs. A missing, uninitialized or
    unreadable store becomes a sanitized 503; unknown resources remain the
    route's scoped 404. Programming errors are not swallowed.

    The two phases are handled separately. Only the readiness phase -- open the
    connection, begin the read transaction, confirm the declared schema exists,
    all with app-owned constant SQL -- may turn a driver error into the sanitized
    503, because nothing a caller wrote runs there. The route's own reads run in
    the domain phase below, outside that mapping: a query-time defect (malformed
    SQL, a bad column reference) surfaces as the app's ordinary 500 instead of
    masquerading as "storage is unavailable".
    """
    database_path = getattr(request.app.state, "database_path", None)
    if database_path is None:
        raise _storage_unavailable()
    with open_read_only_session(database_path) as session:
        # Readiness phase: connection, read transaction, declared schema.
        try:
            begin_read_transaction(session)
            missing_tables = _missing_declared_tables(session)
        except DatabaseError as exc:
            if isinstance(exc, (OperationalError, InternalError)) or (
                _is_store_damage(exc)
            ):
                raise _storage_unavailable() from exc
            raise
        if missing_tables:
            raise _storage_unavailable()
        # Domain phase: the route's reads, deliberately outside the 503 mapping.
        try:
            yield session
        except DatabaseError as exc:
            # Store damage is never a reader defect; everything else (in
            # particular OperationalError/ProgrammingError) stays actionable.
            if not _is_store_damage(exc):
                raise
            raise _storage_unavailable() from exc


def _artifact_download_headers(
    filename: str, case_id: str, run_id: str, artifact_id: str
) -> dict[str, str]:
    """Attachment headers with a constant filename and percent-encoded ids.

    ``quote`` cannot emit a raw CR/LF, so no header-injection sequence can be
    constructed from the stored identifiers. ``nosniff`` keeps the browser from
    reinterpreting the declared media type.
    """
    encoded = quote(f"{case_id}-{run_id}-{artifact_id}-{filename}", safe="")
    return {
        "Content-Disposition": (
            f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded}'
        ),
        "X-Content-Type-Options": "nosniff",
    }


@router.get(
    "/api/cases/{case_id}/investigation-runs/{run_id}/artifacts",
    response_model=list[ArtifactDescriptorDTO],
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_investigation_run_artifacts(
    case_id: str,
    run_id: str,
    session: Session = Depends(_historical_read_session),
) -> list[ArtifactDescriptorDTO]:
    """Published report-artifact descriptors for one grouped run (read-only).

    Descriptors are sorted by type then artifact ID and never expose a
    filesystem path. An unknown or wrong-case run is a uniform 404; an existing
    run without eligible published reports is ``200 []``. This is not a
    file-existence claim.
    """
    payload = list_run_artifacts(session, case_id=case_id, run_id=run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=ARTIFACT_NOT_FOUND_DETAIL)
    return [map_artifact_descriptor(item) for item in payload]


@router.get(
    "/api/cases/{case_id}/investigation-runs/{run_id}/artifacts/{artifact_id}",
    dependencies=[Depends(reject_snapshot_selector)],
)
def download_investigation_run_artifact(
    case_id: str,
    run_id: str,
    artifact_id: str,
    request: Request,
    output_root: Path = Depends(get_artifact_output_root),
    session: Session = Depends(_historical_read_session),
) -> Response:
    """Checked bytes of one allowlisted published report artifact (read-only).

    No client path input, no inline/latest/nearby-run fallback: every ownership,
    containment, symlink or missing-bytes refusal is the same uniform 404, and a
    file above 50 MiB is ``413 too_large``. The checked descriptor is the one
    that is read.
    """
    try:
        download = read_run_artifact(
            session,
            case_id=case_id,
            run_id=run_id,
            artifact_id=artifact_id,
            output_root=output_root,
            cwd=request.app.state.output_cwd,
        )
    except ArtifactTooLarge as exc:
        raise HTTPException(
            status_code=413, detail=ARTIFACT_TOO_LARGE_DETAIL
        ) from exc
    except ArtifactNotFound as exc:
        raise HTTPException(
            status_code=404, detail=ARTIFACT_NOT_FOUND_DETAIL
        ) from exc
    return Response(
        content=download.content,
        media_type=download.media_type,
        headers=_artifact_download_headers(
            download.filename, case_id, run_id, artifact_id
        ),
    )


@router.get(
    "/api/cases/{case_id}/snapshots/{snapshot_id}",
    response_model=SnapshotSummaryDTO,
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_case_snapshot(
    case_id: str,
    snapshot_id: str,
    service: TopicCaseService = Depends(get_case_service),
) -> SnapshotSummaryDTO:
    """Snapshot metadata/counts; entity bodies use snapshot-aware detail readers."""
    payload = service.get_snapshot_summary(case_id, snapshot_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Snapshot {snapshot_id} not found for case {case_id}",
        )
    return map_snapshot_summary(payload)


# A snapshot-comparison miss must not reveal which side failed, whether the
# snapshot id exists at all, or whether it belongs to another case.
SNAPSHOT_COMPARISON_NOT_FOUND_DETAIL = (
    "Snapshot comparison is not available for this case"
)
SNAPSHOT_COMPARISON_THIRD_CONTEXT_DETAIL = (
    "snapshotId/snapshot_id must name the baseline or target snapshot; this "
    "reader does not accept a third snapshot context"
)


def _reject_third_snapshot_context(
    request: Request, *, baseline: str, target: str
) -> None:
    """422 when an unrelated snapshot selector is smuggled onto this route.

    ``baseline``/``target`` are the only API query names for this reader. A
    supplied ``snapshotId``/``snapshot_id`` is tolerated only when it repeats one
    of those two pinned snapshots; anything else would be a hidden third snapshot
    context.
    """
    supplied = [
        request.query_params[name]
        for name in _SNAPSHOT_SELECTOR_NAMES
        if name in request.query_params
    ]
    if len(set(supplied)) > 1:
        raise HTTPException(
            status_code=422,
            detail=(
                "Conflicting snapshotId and snapshot_id selectors were supplied"
            ),
        )
    allowed = {baseline, target}
    if any(value not in allowed for value in supplied):
        raise HTTPException(
            status_code=422, detail=SNAPSHOT_COMPARISON_THIRD_CONTEXT_DETAIL
        )


@router.get(
    "/api/cases/{case_id}/snapshot-comparison",
    response_model=SnapshotComparisonDTO,
)
def get_snapshot_comparison(
    case_id: str,
    request: Request,
    baseline: str = Query(..., min_length=1),
    target: str = Query(..., min_length=1),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=2147483647),
    session: Session = Depends(_historical_read_session),
) -> SnapshotComparisonDTO:
    """Ad-hoc comparison of two snapshots of one case (read-only, zero writes).

    Distinct from the recorded-run ``/changes`` surface: this delta is computed on
    request and is never stored. Ordering is strict by the owning run sequence, so
    an identical or reversed pair is **422**; unknown/cross-case snapshots are a
    uniform **404**. An unsupported or incompatible pair is **200** with
    ``availability: "unavailable"`` and a reason -- never an empty ready delta.
    """
    _reject_third_snapshot_context(request, baseline=baseline, target=target)
    try:
        payload = read_snapshot_comparison(
            session,
            case_id=case_id,
            baseline_snapshot_id=baseline,
            target_snapshot_id=target,
            limit=limit,
            offset=offset,
        )
    except SnapshotComparisonNotFound as exc:
        raise HTTPException(
            status_code=404, detail=SNAPSHOT_COMPARISON_NOT_FOUND_DETAIL
        ) from exc
    except SnapshotComparisonInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return map_snapshot_comparison(payload)


@router.get(
    "/api/cases/{case_id}/evidence",
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_case_evidence(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.evidence


@router.get("/api/cases/{case_id}/evidence/{evidence_id}", response_model=EvidenceDetailDTO)
def get_case_evidence_detail(
    case_id: str,
    evidence_id: str,
    snapshot_id: str | None = Query(default=None, alias="snapshotId"),
    snapshot_id_snake: str | None = Query(default=None, alias="snapshot_id"),
    service: TopicCaseService = Depends(get_case_service),
) -> EvidenceDetailDTO:
    """Source metadata, capture list and claim references. Never capture text.

    ``snapshotId`` resolves the item, its capture references and its related
    claims from that immutable observation; live rows are never substituted.
    """
    selector = _resolve_snapshot_selector(snapshot_id, snapshot_id_snake)
    try:
        payload = service.get_evidence_detail(
            case_id, evidence_id, snapshot_id=selector
        )
    except SnapshotNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=_entity_not_found_detail(
                "Evidence", evidence_id, case_id, selector
            ),
        )
    return map_evidence_detail(payload)


@router.get(
    "/api/cases/{case_id}/evidence/{evidence_id}/captures/{capture_id}",
    response_model=CaptureWindowDTO,
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_case_capture_window(
    case_id: str,
    evidence_id: str,
    capture_id: str,
    start: int = Query(default=0, ge=0),
    length: int = Query(
        default=_DEFAULT_CAPTURE_WINDOW_LENGTH,
        ge=1,
        le=_MAX_CAPTURE_WINDOW_LENGTH,
    ),
    service: TopicCaseService = Depends(get_case_service),
) -> CaptureWindowDTO:
    """One bounded code-point window of an immutable capture (read-only)."""
    try:
        payload = service.get_capture_window(
            case_id,
            evidence_id,
            capture_id,
            start=start,
            length=length,
        )
    except CaptureRangeError as exc:
        # Malformed range (for example start beyond the stored body). 422, never
        # a silently clamped window.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Capture {capture_id} not found for evidence {evidence_id} "
                f"in case {case_id}"
            ),
        )
    return map_capture_window(payload)


@router.get(
    "/api/cases/{case_id}/citations/{citation_id}",
    response_model=CitationDTO,
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_case_citation(
    case_id: str,
    citation_id: str,
    service: TopicCaseService = Depends(get_case_service),
) -> CitationDTO:
    """Frozen validated passage, resolvable without a live claim or link."""
    payload = service.get_citation_detail(case_id, citation_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Citation {citation_id} not found for case {case_id}",
        )
    return map_citation_detail(payload)


@router.get("/api/cases/{case_id}/exceptions", dependencies=[Depends(reject_snapshot_selector)])
def get_case_exceptions(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.exceptions


@router.get("/api/cases/{case_id}/parties", dependencies=[Depends(reject_snapshot_selector)])
def get_case_parties(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.parties


@router.get("/api/cases/{case_id}/timeline", dependencies=[Depends(reject_snapshot_selector)])
def get_case_timeline(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.timeline


@router.get("/api/cases/{case_id}/run-history", dependencies=[Depends(reject_snapshot_selector)])
def get_case_run_history(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.runHistory


@router.get(
    "/api/cases/{case_id}/workflow",
    response_model=WorkflowDiagnosticsDTO,
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_case_workflow(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.workflow


@router.get(
    "/api/cases/{case_id}/review-activity",
    response_model=ReviewActivityDTO,
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_case_review_activity(
    case_id: str,
    service: TopicCaseService = Depends(get_case_service),
) -> ReviewActivityDTO:
    try:
        activity = service.get_case_review_activity(case_id)
    except ValueError as exc:
        raise _reader_missing_case_error(exc, case_id) from exc
    return map_review_activity(activity)


@router.post("/api/cases/{case_id}/review-actions/review", response_model=CaseListItem)
def post_case_review_action(
    case_id: str,
    request: ReviewActionRequest,
    service: TopicCaseService = Depends(get_case_service),
) -> CaseListItem:
    try:
        updated = service.review_case(case_id, request.decision, request.notes)
    except ValueError as exc:
        raise _post_write_error(exc) from exc
    return map_case_list_item(updated)


@router.post(
    "/api/cases/{case_id}/review-actions/exceptions/{exception_id}",
    response_model=CaseListItem,
)
def post_case_exception_action(
    case_id: str,
    exception_id: str,
    request: ExceptionActionRequest,
    service: TopicCaseService = Depends(get_case_service),
) -> CaseListItem:
    try:
        updated = service.update_exception_status(
            case_id,
            exception_id,
            action=request.action,
            notes=request.notes,
        )
    except ValueError as exc:
        raise _post_write_error(exc) from exc
    return map_case_list_item(updated)


@router.post("/api/cases/{case_id}/annotations", response_model=ReviewAnnotationDTO)
def post_case_annotation(
    case_id: str,
    request: AnnotationCreateRequest,
    service: TopicCaseService = Depends(get_case_service),
) -> ReviewAnnotationDTO:
    try:
        item = service.add_review_annotation(
            case_id,
            target_type=request.targetType,
            target_id=request.targetId,
            annotation_type=request.annotationType,
            content=request.content,
            author=request.author,
            metadata=request.metadata,
        )
    except ValueError as exc:
        raise _post_write_error(exc) from exc
    return ReviewAnnotationDTO(
        id=item["id"],
        targetType=item["target_type"],
        targetId=item["target_id"],
        annotationType=item["annotation_type"],
        author=item["author"],
        content=item["content"],
        metadata=item.get("metadata", {}),
        createdAt=item.get("created_at"),
    )


@router.get(
    "/api/cases/{case_id}/evaluation",
    response_model=EvaluationSummaryDTO,
    dependencies=[Depends(reject_snapshot_selector)],
)
def get_case_evaluation(
    case_id: str,
    service: TopicCaseService = Depends(get_case_service),
) -> EvaluationSummaryDTO:
    try:
        summary = service.get_case_evaluation_summary(case_id)
    except ValueError as exc:
        raise _reader_missing_case_error(exc, case_id) from exc
    return map_evaluation_summary(summary)


@router.get("/api/monitoring/summary", response_model=MonitoringSummaryDTO)
def get_monitoring_summary(
    service: TopicCaseService = Depends(get_case_service),
) -> MonitoringSummaryDTO:
    return map_monitoring_summary(service.get_monitoring_summary())


@router.get("/api/cases/{case_id}/report", dependencies=[Depends(reject_snapshot_selector)])
def get_case_report(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.report


@router.get(
    "/api/cases/{case_id}/report/markdown",
    dependencies=[Depends(reject_snapshot_selector)],
)
def download_case_report_markdown(
    case_id: str,
    service: TopicCaseService = Depends(get_case_service),
):
    detail = _load_raw_case_detail_or_404(service, case_id)
    report_path = detail["case"].get("report_path")
    if not report_path:
        raise HTTPException(status_code=404, detail="Markdown report not found")
    path = Path(report_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Markdown report not found")
    return FileResponse(path, media_type="text/markdown", filename=path.name)


@router.get(
    "/api/cases/{case_id}/report/manifest",
    dependencies=[Depends(reject_snapshot_selector)],
)
def download_case_report_manifest(
    case_id: str,
    service: TopicCaseService = Depends(get_case_service),
):
    detail = _load_raw_case_detail_or_404(service, case_id)
    manifest_path = detail["case"].get("latest_manifest_path")
    if manifest_path:
        path = Path(manifest_path)
        if path.exists():
            return FileResponse(path, media_type="application/json", filename=path.name)

    report_bundle = detail.get("report_bundle")
    if report_bundle is not None:
        return JSONResponse(content=json.loads(json.dumps(report_bundle, default=str)))
    raise HTTPException(status_code=404, detail="Manifest not found")


def create_app() -> FastAPI:
    app = FastAPI(title="Triangulate API", version="0.1.0")
    # Operator output-root and database settings are captured once per app
    # instance, against the documented startup working directory. Requests,
    # headers and artifact rows can never supply or override them, and the
    # database path is resolved without consulting the mutable global binding.
    app.state.output_cwd = Path.cwd()
    app.state.output_root = resolve_output_root(cwd=app.state.output_cwd)
    app.state.database_path = resolve_database_path(
        configured_database_path(), cwd=app.state.output_cwd
    )

    @app.exception_handler(CaseWriterConflict)
    async def _case_writer_conflict(
        _request: Request, exc: CaseWriterConflict
    ) -> JSONResponse:
        # A conflicting case-bound write is a state conflict, not a server error.
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    app.include_router(router)
    return app


app = create_app()
