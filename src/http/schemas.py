"""HTTP DTOs for the frontend-facing API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


AutomationMode = Literal["autonomous", "blocked", "safe"]
CaseStatus = Literal[
    "discovering",
    "processing",
    "investigating",
    "review ready",
    "approved",
    "rejected",
    "monitoring",
    "failed",
]
CaseStage = Literal[
    "BOOTSTRAP",
    "RETRIEVE",
    "TRIAGE",
    "INVESTIGATE",
    "ARBITRATE",
    "REPORT",
    "REVIEW",
]
VerificationStatus = Literal[
    "confirmed",
    "probable",
    "alleged",
    "contested",
    "debunked",
    "unknown",
]


class CaseCounts(BaseModel):
    articles: int
    events: int
    reviewItems: int


class CaseListItem(BaseModel):
    id: str
    query: str
    conflictDomain: str
    status: CaseStatus
    stage: CaseStage
    counts: CaseCounts
    reportPath: str | None = None
    automationMode: AutomationMode
    hasNewMaterial: bool
    openExceptionsCount: int
    lastUpdated: str | None = None


class CaseBanner(BaseModel):
    id: str
    query: str
    conflictDomain: str
    status: CaseStatus
    stage: CaseStage
    counts: CaseCounts
    reportPath: str | None = None
    automationMode: AutomationMode
    hasNewMaterial: bool
    openExceptionsCount: int
    reviewNotes: str | None = None
    lastUpdated: str | None = None


class ClaimEvidenceLinkDTO(BaseModel):
    id: str
    relation: str
    confidenceScore: float | None = None
    sourceDiversityRank: int | None = None
    title: str | None = None
    publisher: str | None = None
    originUrl: str | None = None
    sourceType: str | None = None


class ClaimDTO(BaseModel):
    id: str
    text: str
    verificationStatus: VerificationStatus
    type: Literal["fact", "allegation"]
    controversyScore: float | None = None
    supportCount: int
    opposeCount: int
    sourceDiversityCount: int
    claimSignature: str
    narrativeClusterId: str | None = None
    evidence: list[ClaimEvidenceLinkDTO] = Field(default_factory=list)


class EvidenceVerificationCheckDTO(BaseModel):
    id: str
    checkType: str
    result: str
    method: str | None = None
    notes: str | None = None
    verifiedBy: str | None = None
    verifiedAt: str | None = None


class EvidenceDTO(BaseModel):
    id: str
    title: str | None = None
    originUrl: str | None = None
    canonicalUrl: str | None = None
    publisher: str | None = None
    sourceType: str
    verificationStatus: VerificationStatus
    credibilityTier: str | None = None
    requiresHumanReview: bool
    linkedClaims: list[str] = Field(default_factory=list)
    verificationChecks: list[EvidenceVerificationCheckDTO] = Field(default_factory=list)


class ExceptionDTO(BaseModel):
    id: str
    type: str
    message: str
    severity: Literal["high", "medium", "low"]
    status: Literal["open", "deferred", "resolved"]
    recommendedAction: str
    isOpen: bool


class PartyDTO(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str
    overallStance: Literal["for", "against", "neutral", "mixed"]
    isModelInferred: bool
    associatedClaimsCount: int


class TimelineEventDTO(BaseModel):
    id: str
    timestamp: str | None = None
    title: str
    summary: str | None = None
    verificationStatus: VerificationStatus
    linkedEvidenceCount: int
    locationCountryCode: str | None = None
    locationLat: float | None = None
    locationLon: float | None = None


class RunHistoryItemDTO(BaseModel):
    id: str
    stage: str
    model: str | None = None
    durationMs: int | None = None
    status: Literal["success", "error", "running", "pending", "skipped"]
    fallbackCount: int
    parseFailureCount: int
    timestamp: str | None = None
    message: str | None = None


class NarrativeDTO(BaseModel):
    id: str
    clusterId: str
    stanceSummary: str
    sourceCount: int
    claimCount: int = 0


class ReportDTO(BaseModel):
    status: Literal["generated", "pending"]
    markdownPath: str | None = None
    markdownContent: str | None = None
    manifestPath: str | None = None


class CaseTabs(BaseModel):
    claims: list[ClaimDTO] = Field(default_factory=list)
    evidence: list[EvidenceDTO] = Field(default_factory=list)
    exceptions: list[ExceptionDTO] = Field(default_factory=list)
    parties: list[PartyDTO] = Field(default_factory=list)
    timeline: list[TimelineEventDTO] = Field(default_factory=list)
    runHistory: list[RunHistoryItemDTO] = Field(default_factory=list)
    narratives: list[NarrativeDTO] = Field(default_factory=list)
    report: ReportDTO


class CaseDetailResponse(BaseModel):
    case: CaseBanner
    tabs: CaseTabs


class ClaimsOverviewResponse(BaseModel):
    claims: list[ClaimDTO] = Field(default_factory=list)
    narratives: list[NarrativeDTO] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"]
