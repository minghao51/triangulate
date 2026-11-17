"""FastAPI application for the frontend-facing HTTP API."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from src.cases import TopicCaseService
from src.cases.readers import CaptureRangeError
from .dependencies import get_case_service
from .mappers import (
    map_capture_window,
    map_case_detail,
    map_case_list_item,
    map_citation_detail,
    map_claim_detail,
    map_claims_overview,
    map_evidence_detail,
)
from .schemas import (
    CaptureWindowDTO,
    CaseDetailResponse,
    CaseListItem,
    CitationDTO,
    ClaimDetailDTO,
    ClaimsOverviewResponse,
    EvidenceDetailDTO,
    HealthResponse,
)


router = APIRouter()

# Deliberately explicit: E03 reads committed state only. A supplied snapshot
# selector is rejected instead of being silently ignored, so a caller can never
# believe it is reading historical state when it is reading the latest rows.
UNSUPPORTED_SNAPSHOT_SELECTOR_MESSAGE = (
    "Snapshot selectors are not supported yet; omit snapshotId/snapshot_id to "
    "read the current committed state."
)

_DEFAULT_CAPTURE_WINDOW_LENGTH = 20000
_MAX_CAPTURE_WINDOW_LENGTH = 50000


def _reject_snapshot_selector(*selectors: str | None) -> None:
    """422 on any supplied (even empty) snapshot selector argument."""
    for selector in selectors:
        if selector is not None:
            raise HTTPException(
                status_code=422, detail=UNSUPPORTED_SNAPSHOT_SELECTOR_MESSAGE
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


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/api/cases", response_model=list[CaseListItem])
def list_cases(service: TopicCaseService = Depends(get_case_service)) -> list[CaseListItem]:
    return [map_case_list_item(case) for case in service.list_cases()]


@router.get("/api/cases/{case_id}", response_model=CaseDetailResponse)
def get_case(case_id: str, service: TopicCaseService = Depends(get_case_service)) -> CaseDetailResponse:
    return _load_case_detail_or_404(service, case_id)


@router.get("/api/cases/{case_id}/claims")
def get_case_claims(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.claims


@router.get("/api/cases/{case_id}/claims/overview", response_model=ClaimsOverviewResponse)
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
    """One claim with its evidence passages (GET-only; creates nothing)."""
    _reject_snapshot_selector(snapshot_id, snapshot_id_snake)
    payload = service.get_claim_detail(case_id, claim_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Claim {claim_id} not found for case {case_id}",
        )
    return map_claim_detail(payload)


@router.get("/api/cases/{case_id}/evidence")
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
    """Source metadata, capture list and claim references. Never capture text."""
    _reject_snapshot_selector(snapshot_id, snapshot_id_snake)
    payload = service.get_evidence_detail(case_id, evidence_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence {evidence_id} not found for case {case_id}",
        )
    return map_evidence_detail(payload)


@router.get(
    "/api/cases/{case_id}/evidence/{evidence_id}/captures/{capture_id}",
    response_model=CaptureWindowDTO,
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


@router.get("/api/cases/{case_id}/citations/{citation_id}", response_model=CitationDTO)
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


@router.get("/api/cases/{case_id}/exceptions")
def get_case_exceptions(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.exceptions


@router.get("/api/cases/{case_id}/parties")
def get_case_parties(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.parties


@router.get("/api/cases/{case_id}/timeline")
def get_case_timeline(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.timeline


@router.get("/api/cases/{case_id}/run-history")
def get_case_run_history(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.runHistory


@router.get("/api/cases/{case_id}/report")
def get_case_report(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.report


@router.get("/api/cases/{case_id}/report/markdown")
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


@router.get("/api/cases/{case_id}/report/manifest")
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
    app.include_router(router)
    return app


app = create_app()
