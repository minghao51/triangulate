"""Pydantic schemas for structured LLM agent outputs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ClaimSchema(BaseModel):
    """Structured claim extracted from an article.

    ``source_quote`` and its offsets are *proposals* only. They are validated
    later against the immutable capture body and the recorded analysis-input
    scope (see :mod:`src.storage.citations`); nothing here is trusted. All three
    fields are optional so payloads produced before quotations existed keep
    validating unchanged.
    """

    claim: str
    who: list[str] = Field(default_factory=list)
    when: str = ""
    where: str = ""
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    source_quote: str | None = None
    source_quote_start: int | None = None
    source_quote_end: int | None = None


class ClaimCollectionSchema(BaseModel):
    """Structured collector response.

    ``claims`` is deliberately **required** (no default). ``call_structured_llm``
    validates the parsed payload and then dumps defaults, so a defaulted empty
    list made an absent/malformed ``claims`` key indistinguishable from a real
    validated empty result. With the field required, an absent key is a
    validation failure (which takes the existing fallback path), while an
    explicit ``{"claims": []}`` remains a truthfully valid empty collection.
    """

    claims: list[ClaimSchema]


ExtractionStatus = Literal["valid", "empty", "fallback", "unavailable"]


class ExtractionOutcomeSchema(BaseModel):
    """What the collector actually did with the supplied article body.

    Statuses:

    * ``valid`` -- structured parsing succeeded and yielded >= 1 claim. Only this
      status may set ``quote_proposals_trusted``: the claims came from a real
      validated structured parse, so their optional quote proposals are worth
      validating.
    * ``empty`` -- structured parsing succeeded with an explicit empty list. This
      is a real, validated empty result, but it validated nothing, so quote
      proposals are not trusted.
    * ``fallback`` -- the provider call happened but parsing/validation failed, so
      local coarse fallback claims were substituted. Those sentences are invented
      from title+body and are never trusted.
    * ``unavailable`` -- extraction could not run or errored (no API key, an
      exception, or no usable body). Nothing was analysed; never trusted.

    ``scope_start``/``scope_end`` are zero-based Unicode code-point indices,
    end-exclusive, into the **normalized body** and describe the exact region
    supplied to the model (a prefix when the body was truncated). The title is
    never part of that region. ``body_char_count`` is the length of the full
    normalized body (0 when there is no usable body), ``input_limit`` the
    configured truncation limit, and ``source_available`` says whether a
    non-empty body was available at all. ``reason`` is a short factual code.
    """

    status: ExtractionStatus
    quote_proposals_trusted: bool = False
    scope_start: int = 0
    scope_end: int = 0
    body_char_count: int = 0
    input_limit: int = 0
    source_available: bool = False
    reason: str = ""


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
