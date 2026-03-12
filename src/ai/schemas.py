"""Pydantic schemas for structured LLM agent outputs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ClaimSchema(BaseModel):
    """Structured claim extracted from an article."""

    claim: str
    who: list[str] = Field(default_factory=list)
    when: str = ""
    where: str = ""
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"


class ClaimCollectionSchema(BaseModel):
    """Structured collector response."""

    claims: list[ClaimSchema] = Field(default_factory=list)


class NarrativeSchema(BaseModel):
    """Structured narrative summary for a cluster."""

    stance_summary: str
    key_themes: list[str] = Field(default_factory=list)
    main_entities: list[str] = Field(default_factory=list)


class PartySchema(BaseModel):
    """Canonical party grouping."""

    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    reasoning: str = ""


class PartyClassificationSchema(BaseModel):
    """Party classifier output."""

    parties: list[PartySchema] = Field(default_factory=list)


class SupportedClaimSchema(BaseModel):
    """Party-supported claim shape."""

    claim_id: str
    claim_text: str
    position: Literal["SUPPORTS"] = "SUPPORTS"
    evidence_from_party: str = ""
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"


class ContestedClaimSchema(BaseModel):
    """Party-contested claim shape."""

    claim_id: str
    claim_text: str
    position: Literal["CONTESTS"] = "CONTESTS"
    counter_argument: str = ""
    alternative_perspective: str = ""
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"


class UniqueClaimSchema(BaseModel):
    """Party-unique claim."""

    claim_text: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    sources: list[str] = Field(default_factory=list)


class PartyStanceSchema(BaseModel):
    """High-level party stance."""

    overall_position: str
    key_concerns: list[str] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)


class PartyInvestigationSchema(BaseModel):
    """Party investigation result."""

    claims_supported: list[SupportedClaimSchema] = Field(default_factory=list)
    claims_contested: list[ContestedClaimSchema] = Field(default_factory=list)
    unique_claims: list[UniqueClaimSchema] = Field(default_factory=list)
    party_stance: PartyStanceSchema


class PartyConsensusSchema(BaseModel):
    """Party consensus information for an arbiter determination."""

    unanimous: bool = False
    supporting_parties: list[str] = Field(default_factory=list)
    opposing_parties: list[str] = Field(default_factory=list)
    neutral_parties: list[str] = Field(default_factory=list)


class ArbiterReasoningSchema(BaseModel):
    """Detailed arbiter reasoning."""

    is_fact: str = ""
    verification_rationale: str = ""
    party_consensus: PartyConsensusSchema = Field(default_factory=PartyConsensusSchema)


class ArbiterDeterminationSchema(BaseModel):
    """Per-claim arbiter output."""

    claim_id: str
    claim_text: str
    fact_allegation_classification: Literal["FACT", "ALLEGATION"] = "ALLEGATION"
    verification_status: Literal[
        "CONFIRMED", "PROBABLE", "ALLEGED", "CONTESTED", "DEBUNKED"
    ] = "ALLEGED"
    arbiter_reasoning: ArbiterReasoningSchema = Field(
        default_factory=ArbiterReasoningSchema
    )


class EventSummarySchema(BaseModel):
    """Arbiter event summary."""

    total_claims: int = 0
    facts_count: int = 0
    allegations_count: int = 0
    verification_distribution: dict[str, int] = Field(default_factory=dict)
    party_agreement_level: Literal["HIGH", "MEDIUM", "LOW", "NONE"] = "NONE"
    controversy_score: float = 0.0


class ArbiterResultSchema(BaseModel):
    """Arbiter response shape."""

    final_determinations: list[ArbiterDeterminationSchema] = Field(default_factory=list)
    event_summary: EventSummarySchema = Field(default_factory=EventSummarySchema)


class QueryGenerationSchema(BaseModel):
    """Generated search queries."""

    queries: list[str] = Field(default_factory=list)


class SourcePrioritySchema(BaseModel):
    """Structured source priority output."""

    scores: dict[str, float] = Field(default_factory=dict)


class DateRangeSchema(BaseModel):
    """Date range extraction output."""

    start: str | None = None
    end: str | None = None


class FactAllegationIndicatorsSchema(BaseModel):
    """Signals used for fact/allegation classification."""

    factual_elements: list[str] = Field(default_factory=list)
    allegation_elements: list[str] = Field(default_factory=list)


class FactAllegationResultSchema(BaseModel):
    """Fact/allegation classifier output."""

    claim: str
    classification: Literal["FACT", "ALLEGATION"] = "ALLEGATION"
    reasoning: str = ""
    confidence: float = 0.0
    indicators: FactAllegationIndicatorsSchema = Field(
        default_factory=FactAllegationIndicatorsSchema
    )
