"""FastAPI application for the frontend-facing HTTP API."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from src.cases import TopicCaseService
from .dependencies import get_case_service
from .mappers import (
    map_case_detail,
    map_case_list_item,
    map_claims_overview,
    map_evaluation_summary,
    map_monitoring_summary,
    map_review_activity,
)
from .schemas import (
    AnnotationCreateRequest,
    CaseDetailResponse,
    CaseListItem,
    ClaimsOverviewResponse,
    EvaluationSummaryDTO,
    ExceptionActionRequest,
    HealthResponse,
    MonitoringSummaryDTO,
    ReviewActionRequest,
    ReviewActivityDTO,
    ReviewAnnotationDTO,
    WorkflowDiagnosticsDTO,
)


router = APIRouter()


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


@router.get("/api/cases/{case_id}/evidence")
def get_case_evidence(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.evidence


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


@router.get("/api/cases/{case_id}/workflow", response_model=WorkflowDiagnosticsDTO)
def get_case_workflow(case_id: str, service: TopicCaseService = Depends(get_case_service)):
    return _load_case_detail_or_404(service, case_id).tabs.workflow


@router.get("/api/cases/{case_id}/review-activity", response_model=ReviewActivityDTO)
def get_case_review_activity(
    case_id: str,
    service: TopicCaseService = Depends(get_case_service),
) -> ReviewActivityDTO:
    return map_review_activity(service.get_case_review_activity(case_id))


@router.post("/api/cases/{case_id}/review-actions/review", response_model=CaseListItem)
def post_case_review_action(
    case_id: str,
    request: ReviewActionRequest,
    service: TopicCaseService = Depends(get_case_service),
) -> CaseListItem:
    updated = service.review_case(case_id, request.decision, request.notes)
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
    updated = service.update_exception_status(
        case_id,
        exception_id,
        action=request.action,
        notes=request.notes,
    )
    return map_case_list_item(updated)


@router.post("/api/cases/{case_id}/annotations", response_model=ReviewAnnotationDTO)
def post_case_annotation(
    case_id: str,
    request: AnnotationCreateRequest,
    service: TopicCaseService = Depends(get_case_service),
) -> ReviewAnnotationDTO:
    item = service.add_review_annotation(
        case_id,
        target_type=request.targetType,
        target_id=request.targetId,
        annotation_type=request.annotationType,
        content=request.content,
        author=request.author,
        metadata=request.metadata,
    )
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


@router.get("/api/cases/{case_id}/evaluation", response_model=EvaluationSummaryDTO)
def get_case_evaluation(
    case_id: str,
    service: TopicCaseService = Depends(get_case_service),
) -> EvaluationSummaryDTO:
    return map_evaluation_summary(service.get_case_evaluation_summary(case_id))


@router.get("/api/monitoring/summary", response_model=MonitoringSummaryDTO)
def get_monitoring_summary(
    service: TopicCaseService = Depends(get_case_service),
) -> MonitoringSummaryDTO:
    return map_monitoring_summary(service.get_monitoring_summary())


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
