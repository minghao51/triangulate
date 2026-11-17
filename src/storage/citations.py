"""Exact-span quotation validation, relationship policy and immutable citations.

This module is the storage-layer seam for E02 quotation semantics. It lives in
``src.storage`` (next to :mod:`src.storage.captures`) so that neither the event
store nor the case-service package has to import ``src.cases``, avoiding the
existing package import cycle. ``src.cases.evidence`` re-exports the pieces the
case service needs.

Three separable concerns:

1. :func:`validate_quote_alignment` -- a small, pure, exact validator. It uses
   the *immutable capture text* plus the quotation proposal and an *explicit*
   recorded analysis-input scope. There is no fuzzy matching, casefolding, NFKC
   normalization, ellipsis synthesis or "assume the whole capture" fallback.
   Missing or malformed scope fails closed.
2. :func:`resolve_effective_relationship` -- the single versioned relationship
   policy. Collector-generated alignments are ``reported_by`` only when exact and
   ``uncertain`` otherwise; ``supports``/``contradicts`` require an explicit
   versioned assessment with a real origin/version and an exact anchored
   passage. Extraction confidence is never an assessment.
3. :func:`record_claim_citation` -- the append-only citation writer. It is
   caller-owned-session only: no commit, rollback or close, and no swallowed
   errors. Invalid proposals are returned as diagnostics and create no citation.

None of this performs verification, model calls or AI workflow transitions.
"""

from __future__ import annotations

import copy
import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.orm import Session

from src.storage.models import (
    AlignmentStatus,
    Claim,
    ClaimCitation,
    Event,
    EvidenceCapture,
    EvidenceItem,
    TopicCase,
    utc_now,
)

# ---------------------------------------------------------------------------
# Policy versions and vocabulary
# ---------------------------------------------------------------------------

# Version of the exact-span alignment algorithm. Stored with every validated
# citation so a later algorithm change can never silently reinterpret old spans.
ALIGNMENT_VERSION = "exact-codepoint-v1"

# Version of the relationship/eligibility policy below.
RELATIONSHIP_POLICY_VERSION = "relationship-policy-v1"

# The only effective relationship vocabulary. Anything else (including a raw
# legacy value) resolves to ``uncertain`` -- never to support.
RELATIONSHIP_VOCABULARY = ("reported_by", "supports", "contradicts", "uncertain")

# Documented legacy aliases. Mapping is diagnostic only: an unprovenanced legacy
# ``opposes`` row still resolves to ``uncertain`` because it has no assessment
# origin/version or exact anchored passage (see ``resolve_effective_relationship``).
LEGACY_RELATIONSHIP_ALIASES = {"opposes": "contradicts"}

# Relationships that may only ever be produced by an explicit, versioned
# assessment with an exact anchored passage.
ASSESSED_RELATIONSHIPS = ("supports", "contradicts")

# Relationships an explicit, versioned assessment is allowed to assert without
# turning them into corroboration.
NON_CORROBORATING_RELATIONSHIPS = ("reported_by", "uncertain")

# Known explicit-assessment origins for policy v1. The collector role is an
# *extractor*, not an assessor: it is deliberately absent here, and any missing,
# unknown, legacy, fallback or merely unrecognised non-empty string fails closed.
ASSESSMENT_ORIGINS = ("model", "human", "service")

# ``assessment_version`` is an OPAQUE, caller-supplied assessor/model/prompt
# version identifier -- NOT this module's relationship-policy version. Any
# non-empty, non-whitespace string is accepted and preserved with its original
# case in the frozen citation and in citation identity (for example ``v2``,
# ``model-V3`` or ``prompt.2026-11``). Only these explicit "no real version"
# sentinels are rejected, compared case-insensitively. There is deliberately no
# hardcoded allowlist registry of concrete versions.
UNKNOWN_ASSESSMENT_VERSION_MARKERS = frozenset(
    {
        "unknown",
        "legacy",
        "fallback",
        "unavailable",
        "none",
        "null",
        "n/a",
        "unversioned",
    }
)

# The trusted new-collector role. Frozen as the citation origin instead of
# pretending the passage was model/human assessed.
COLLECTOR_ORIGIN = "collector"

# Honest default for a link that never had a quote proposal.
DEFAULT_ALIGNMENT_STATUS = AlignmentStatus.NOT_PROVIDED.value


# ---------------------------------------------------------------------------
# Input records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisScope:
    """The actual body region supplied to the analysis/extraction step.

    ``start_char``/``end_char`` are zero-based Unicode code-point indices,
    end-exclusive, against the capture's stored text and denote the region
    actually supplied to the extractor (a prefix, in the common truncated-input
    case).

    ``body_sha256`` is the optional SHA-256 of the **full normalized source body**
    bound into the capture (the same value as ``EvidenceCapture.text_sha256``),
    not a hash of the supplied prefix alone. It exists to prove that the analysis
    input was derived from this exact capture body; it must never be read as
    evidence that the whole body was examined. When absent, the caller simply has
    no body-provenance check.

    There is no implicit "whole capture" default: callers must be explicit, and
    an absent scope fails closed.
    """

    start_char: int
    end_char: int
    body_sha256: str | None = None


@dataclass(frozen=True)
class QuoteProposal:
    """A proposed quotation and optional proposed offsets.

    Offsets are proposals only. They are accepted only when they are real ints
    inside both the capture and the recorded scope *and* ``text[s:e] == quote``.
    """

    quote: str | None = None
    start_char: int | None = None
    end_char: int | None = None


@dataclass(frozen=True)
class QuoteAlignment:
    """Outcome of validating one proposal.

    ``quote``/``start_char``/``end_char`` are populated **only** for
    ``status == "exact"``. The original proposal and the diagnostic reason are
    always retained separately so invalid proposals stay visible as diagnostics.
    """

    status: str
    proposed_quote: str | None = None
    proposed_start_char: int | None = None
    proposed_end_char: int | None = None
    quote: str | None = None
    start_char: int | None = None
    end_char: int | None = None
    diagnostic_reason: str | None = None
    alignment_version: str = ALIGNMENT_VERSION

    @property
    def is_exact(self) -> bool:
        """Whether a validated passage exists (the only trustworthy state)."""
        return self.status == AlignmentStatus.EXACT.value


@dataclass(frozen=True)
class RelationshipResolution:
    """Outcome of the central relationship policy.

    ``stored_relationship`` preserves the raw value for diagnostics.
    ``citation_eligible`` states whether this exact passage may become an
    immutable citation: only a trusted-collector anchored exact passage or an
    explicit known-versioned assessment qualifies.
    """

    effective_relationship: str
    stored_relationship: str | None = None
    assessed: bool = False
    reason: str = ""
    policy_version: str = RELATIONSHIP_POLICY_VERSION
    contribution: str | None = None
    citation_eligible: bool = False


@dataclass(frozen=True)
class CitationRecordResult:
    """Result of :func:`record_claim_citation`.

    ``citation`` is ``None`` for invalid/unavailable proposals: those never
    create validated citations and exist only as diagnostics on the current link.
    """

    citation: ClaimCitation | None
    alignment: QuoteAlignment
    relationship: RelationshipResolution
    created: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_validated(self) -> bool:
        """Whether an immutable citation was found or created."""
        return self.citation is not None


# ---------------------------------------------------------------------------
# Exact-span validation
# ---------------------------------------------------------------------------


def _is_real_int(value: Any) -> bool:
    """Return True for a genuine int (``bool`` is deliberately excluded)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _occurrences(haystack: str, needle: str) -> list[int]:
    """Return every (possibly overlapping) start index of ``needle``."""
    if not needle:
        return []
    found: list[int] = []
    index = haystack.find(needle)
    while index != -1:
        found.append(index)
        # Overlapping matches count: advance by one code point, not by len().
        index = haystack.find(needle, index + 1)
    return found


def _fail(
    status: AlignmentStatus,
    proposal: QuoteProposal,
    reason: str,
) -> QuoteAlignment:
    return QuoteAlignment(
        status=status.value,
        proposed_quote=proposal.quote,
        proposed_start_char=proposal.start_char,
        proposed_end_char=proposal.end_char,
        diagnostic_reason=reason,
    )


def validate_quote_alignment(
    capture_text: str | None,
    proposal: QuoteProposal | None,
    scope: AnalysisScope | None,
) -> QuoteAlignment:
    """Validate a quotation proposal against immutable capture text.

    Order of checks and outcomes:

    * missing capture text -> ``source_unavailable`` (``capture_text_missing``);
    * missing/empty quotation -> ``not_provided``;
    * unknown scope -> ``no_match`` (``scope_unknown``) -- never assume the whole
      capture was seen;
    * malformed scope (non-int/bool bounds, negative, reversed, beyond the
      capture) -> ``no_match`` (``scope_malformed``);
    * a supplied ``body_sha256`` that does not match the capture -> 
      ``source_unavailable`` (``body_sha256_mismatch``), because the analysed body
      is not the text we hold;
    * valid provided offsets inside capture *and* scope with an exactly equal
      slice -> ``exact``;
    * otherwise a unique exact occurrence inside the scope -> ``exact``;
    * several occurrences -> ``ambiguous``; none -> ``no_match``.

    The quote itself is never trimmed, casefolded, NFKC-normalized or
    ellipsis-expanded. Code points are Python string indices.
    """
    proposal = proposal or QuoteProposal()

    if capture_text is None:
        return _fail(AlignmentStatus.SOURCE_UNAVAILABLE, proposal, "capture_text_missing")
    if not isinstance(capture_text, str):
        raise TypeError("capture_text must be a str or None")

    if proposal.quote is None:
        return _fail(AlignmentStatus.NOT_PROVIDED, proposal, "quote_missing")
    if proposal.quote == "":
        return _fail(AlignmentStatus.NOT_PROVIDED, proposal, "quote_empty")

    if scope is None:
        # Fail closed: without a recorded analysis-input scope we cannot claim the
        # passage was inside what the extractor saw.
        return _fail(AlignmentStatus.NO_MATCH, proposal, "scope_unknown")

    if not _is_real_int(scope.start_char) or not _is_real_int(scope.end_char):
        return _fail(AlignmentStatus.NO_MATCH, proposal, "scope_malformed")
    if scope.start_char < 0 or scope.end_char < scope.start_char:
        return _fail(AlignmentStatus.NO_MATCH, proposal, "scope_malformed")
    if scope.end_char > len(capture_text):
        return _fail(AlignmentStatus.NO_MATCH, proposal, "scope_malformed")

    if scope.body_sha256 is not None:
        if not isinstance(scope.body_sha256, str):
            return _fail(AlignmentStatus.NO_MATCH, proposal, "scope_malformed")
        if scope.body_sha256 != compute_quote_text_sha256(capture_text):
            return _fail(
                AlignmentStatus.SOURCE_UNAVAILABLE, proposal, "body_sha256_mismatch"
            )

    quote = proposal.quote
    start = proposal.start_char
    end = proposal.end_char

    if _is_real_int(start) and _is_real_int(end) and start is not None and end is not None:
        if (
            0 <= start < end <= len(capture_text)
            and scope.start_char <= start
            and end <= scope.end_char
            and capture_text[start:end] == quote
        ):
            return QuoteAlignment(
                status=AlignmentStatus.EXACT.value,
                proposed_quote=quote,
                proposed_start_char=start,
                proposed_end_char=end,
                quote=quote,
                start_char=start,
                end_char=end,
                diagnostic_reason="provided_offsets_exact",
            )

    scoped_text = capture_text[scope.start_char : scope.end_char]
    matches = _occurrences(scoped_text, quote)

    if len(matches) == 1:
        absolute = scope.start_char + matches[0]
        return QuoteAlignment(
            status=AlignmentStatus.EXACT.value,
            proposed_quote=quote,
            proposed_start_char=proposal.start_char,
            proposed_end_char=proposal.end_char,
            quote=quote,
            start_char=absolute,
            end_char=absolute + len(quote),
            diagnostic_reason="unique_exact_occurrence_in_scope",
        )
    if len(matches) > 1:
        return _fail(AlignmentStatus.AMBIGUOUS, proposal, "repeated_exact_occurrence")
    return _fail(AlignmentStatus.NO_MATCH, proposal, "no_exact_occurrence_in_scope")


def compute_quote_text_sha256(text: str) -> str:
    """SHA-256 over the exact UTF-8 capture body (mirrors the capture helper)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Central relationship policy
# ---------------------------------------------------------------------------


def canonical_relationship(stored_relation: str | None) -> str:
    """Map a raw stored value into the effective relationship vocabulary.

    Unknown and missing values resolve to ``uncertain`` (never to support).
    Documented legacy aliases are mapped, but the mapping alone grants nothing:
    :func:`resolve_effective_relationship` still requires provenance before an
    aliased ``contradicts`` can be counted.
    """
    if not isinstance(stored_relation, str):
        return "uncertain"
    value = stored_relation.strip().lower()
    if value in LEGACY_RELATIONSHIP_ALIASES:
        return LEGACY_RELATIONSHIP_ALIASES[value]
    if value in RELATIONSHIP_VOCABULARY:
        return value
    return "uncertain"


def effective_relationship_for_alignment(alignment_status: str | None) -> str:
    """Collector-generated links: exact -> ``reported_by``, else ``uncertain``.

    The collector never generates ``supports``/``contradicts``, and an aligned
    quotation never certifies a claim.
    """
    if alignment_status == AlignmentStatus.EXACT.value:
        return "reported_by"
    return "uncertain"


def resolve_effective_relationship(
    *,
    stored_relation: str | None,
    alignment_status: str | None,
    assessment_origin: str | None = None,
    assessment_version: str | None = None,
    exact_anchor: bool = False,
    collector_generated: bool = False,
) -> RelationshipResolution:
    """Resolve one link's effective relationship under the versioned policy.

    Rules (``relationship-policy-v1``), evaluated in this order:

    1. **Trusted collector takes priority.** With ``collector_generated=True`` the
       collector is only ever an *extractor*: an anchored exact passage yields
       ``reported_by`` and nothing else; every other state yields ``uncertain``.
       Any requested raw ``supports``/``contradicts`` and any supplied
       origin/version are ignored, so a collector-originated link can never
       corroborate. ``collector_generated`` defaults to ``False`` (fail closed
       for legacy rows); a trusted new collector must say so explicitly.
    2. **Explicit assessment** requires a recognised origin
       (:data:`ASSESSMENT_ORIGINS`), a non-empty assessment version that is not
       an explicit unknown sentinel (:data:`UNKNOWN_ASSESSMENT_VERSION_MARKERS`)
       *and* an exact anchored passage. The version is an opaque assessor/model/
       prompt identifier, so any concrete non-empty value (``v2``, ``model-v2``)
       is eligible and keeps its original case when frozen.
       Only then are ``supports``/``contradicts`` eligible (a raw legacy
       ``opposes`` therefore only counts when explicitly assessed).
    3. Missing/empty/unrecognised origin, an empty/unknown-sentinel version, a
       non-exact/inconsistent anchor, or a non-boolean ``collector_generated``
       all fail closed to ``uncertain``.

    The anchor must be a genuine ``True`` *and* the status must be ``exact``;
    contradictory arguments (for example ``exact_anchor=True`` with a
    non-exact status) fail closed rather than guessing.

    Extraction confidence is intentionally not a parameter: it cannot act as an
    assessment. Explicit versioned ``reported_by``/``uncertain`` are allowed but
    never become corroboration.
    """
    stored = stored_relation
    canonical = canonical_relationship(stored)

    # ``exact_anchor is True`` rejects truthy non-bools; the status must agree.
    anchor_ok = exact_anchor is True and alignment_status == AlignmentStatus.EXACT.value

    # Only a real ``True`` marks the trusted new collector. A truthy non-bool
    # (for example the string ``"false"`` or ``1``) must not silently enable the
    # trusted branch or fall back to an implicit assessment.
    if not isinstance(collector_generated, bool):
        return RelationshipResolution(
            effective_relationship="uncertain",
            stored_relationship=stored,
            assessed=False,
            reason="invalid_collector_context_flag",
        )

    if collector_generated:
        # Priority branch: extractor role, never an assessor.
        if anchor_ok:
            return RelationshipResolution(
                effective_relationship="reported_by",
                stored_relationship=stored,
                assessed=False,
                reason="trusted_collector_exact_anchor",
                citation_eligible=True,
            )
        return RelationshipResolution(
            effective_relationship="uncertain",
            stored_relationship=stored,
            assessed=False,
            reason="collector_alignment_not_exact",
        )

    origin = (
        assessment_origin.strip().lower()
        if isinstance(assessment_origin, str)
        else ""
    )
    # The configured version is an opaque identifier: keep its original case and
    # only casefold for the unknown-sentinel check.
    version_marker = (
        assessment_version.strip().lower()
        if isinstance(assessment_version, str)
        else ""
    )

    if origin not in ASSESSMENT_ORIGINS:
        return RelationshipResolution(
            effective_relationship="uncertain",
            stored_relationship=stored,
            assessed=False,
            reason="assessment_origin_not_recognized",
        )
    if not version_marker or version_marker in UNKNOWN_ASSESSMENT_VERSION_MARKERS:
        return RelationshipResolution(
            effective_relationship="uncertain",
            stored_relationship=stored,
            assessed=False,
            reason="assessment_version_unknown",
        )
    if not anchor_ok:
        return RelationshipResolution(
            effective_relationship="uncertain",
            stored_relationship=stored,
            assessed=False,
            reason="assessment_passage_not_exact",
        )

    if canonical in ASSESSED_RELATIONSHIPS:
        return RelationshipResolution(
            effective_relationship=canonical,
            stored_relationship=stored,
            assessed=True,
            reason="explicit_versioned_assessment",
            contribution="support" if canonical == "supports" else "opposition",
            citation_eligible=True,
        )
    # Explicitly assessed reported_by/uncertain: allowed, never corroboration.
    candidate = canonical if canonical in NON_CORROBORATING_RELATIONSHIPS else "uncertain"
    return RelationshipResolution(
        effective_relationship=candidate,
        stored_relationship=stored,
        assessed=True,
        reason="explicit_versioned_assessment",
        citation_eligible=True,
    )


def link_contribution(resolution: RelationshipResolution) -> str | None:
    """Return ``support``/``opposition``/``None`` for aggregate counting.

    Only an explicit, versioned assessment with an exact anchored passage can
    contribute. ``reported_by``, ``uncertain``, invalid, unanchored and legacy
    unprovenanced links never increment support/opposition. Repeated link
    contributions must additionally be deduplicated by the caller.
    """
    if not resolution.assessed:
        return None
    if resolution.effective_relationship == "supports":
        return "support"
    if resolution.effective_relationship == "contradicts":
        return "opposition"
    return None


# ---------------------------------------------------------------------------
# Immutable citation writer
# ---------------------------------------------------------------------------

# Explicit identity allowlist. The canonical citation ID is a UUID5 over a JSON
# document containing exactly these fields. Deliberately *not* a recursive
# strip: volatile values are simply never copied into the identity payload.
#
# Excluded by construction: recording timestamps, stage/run IDs, generated
# link/citation IDs and the (historical, mutable) claim ID.
CITATION_IDENTITY_FIELDS = (
    "case_id",
    "capture_id",
    "claim_signature",
    "claim_text",
    "quote",
    "start_char",
    "end_char",
    "scope_start_char",
    "scope_end_char",
    "scope_body_sha256",
    "relationship",
    "alignment_status",
    "alignment_version",
    "assessment_origin",
    "assessment_version",
    "assessment_content",
)

# Assessment-metadata keys that are volatile provenance/identity rather than
# meaningful assessment content. Only these explicit top-level keys are dropped
# from citation *identity*; everything else is kept, nothing is stripped
# recursively, and the first full raw metadata is still retained in the frozen
# row under a namespaced key.
#
# Deliberately does NOT include ambiguous keys such as ``timestamp``: a semantic
# event time is meaningful content and must create a new citation when it changes.
VOLATILE_ASSESSMENT_METADATA_KEYS = frozenset(
    {
        "origin_stage_attempt_id",
        "origin_stage_id",
        "origin_run_id",
        "stage_run_id",
        "run_id",
        "event_id",
        "claim_id",
        "citation_id",
        "link_id",
        "evidence_id",
        "recorded_at",
        "created_at",
        "generated_at",
    }
)

# Reserved generated namespaces inside ``ClaimCitation.metadata_json``. Caller
# assessment metadata is stored under its own key so these reserved keys can
# never overwrite or lose caller content.
RAW_ASSESSMENT_METADATA_KEY = "assessment_metadata"
GENERATED_ALIGNMENT_METADATA_KEY = "alignment"
GENERATED_RELATIONSHIP_METADATA_KEY = "relationship"

_CITATION_ID_NAMESPACE = uuid.UUID("6f2f8a3a-53ae-5b3b-9c0d-2f0f2a5b7c11")


def _canonical_json(value: Any) -> str:
    """Deterministic JSON with sorted keys and no incidental whitespace."""
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def assessment_identity_content(
    assessment_metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Select the meaningful assessment content for citation identity.

    Explicit allowlist at the top level: only documented volatile provenance keys
    are dropped. Arbitrary nested fields are not recursively stripped, so a
    caller cannot hide meaningful content inside a container to force a reuse.
    """
    if not assessment_metadata:
        return {}
    return {
        key: copy.deepcopy(value)
        for key, value in assessment_metadata.items()
        if key not in VOLATILE_ASSESSMENT_METADATA_KEYS
    }


def _normalize_recorded_at(recorded_at: datetime | None) -> datetime:
    if recorded_at is None:
        return utc_now()
    if not isinstance(recorded_at, datetime):
        raise TypeError("recorded_at must be a datetime or None")
    if recorded_at.tzinfo is None:
        return recorded_at.replace(tzinfo=UTC)
    return recorded_at.astimezone(UTC)


def compute_citation_id(identity: Mapping[str, Any]) -> str:
    """Deterministic citation ID over the explicit identity allowlist."""
    payload = {field: identity.get(field) for field in CITATION_IDENTITY_FIELDS}
    return str(uuid.uuid5(_CITATION_ID_NAMESPACE, _canonical_json(payload)))


def record_claim_citation(
    session: Session,
    *,
    case_id: str,
    capture_id: str,
    claim_signature: str | None,
    claim_text: str,
    scope: AnalysisScope | None,
    proposal: QuoteProposal | None = None,
    evidence_id: str | None = None,
    original_claim_id: str | None = None,
    stored_relation: str | None = None,
    assessment_origin: str | None = None,
    assessment_version: str | None = None,
    assessment_metadata: Mapping[str, Any] | None = None,
    collector_generated: bool = False,
    recorded_at: datetime | None = None,
) -> CitationRecordResult:
    """Validate a passage and append (or reuse) its immutable citation.

    Caller-owned session: never commits, rolls back or closes; errors propagate.
    The new citation is flushed before being returned so a pointer/reference can
    be set immediately, and a caller rollback removes it.

    Ownership is checked directly against saved rows rather than trusting FK
    enforcement: the case must exist, the capture must exist, the owning
    ``EvidenceItem`` must belong to that case (and to ``evidence_id`` when
    given). A historical claim ID is *not* required to exist, but if a live row
    with that ID exists it must belong to the same case.

    Only a validated passage creates a citation. Invalid, missing, ambiguous or
    out-of-scope proposals return diagnostics with ``citation=None``.

    Identity: deterministic and content-based over the explicit allowlist in
    :data:`CITATION_IDENTITY_FIELDS`. Recording times, stage/run IDs and
    generated link/citation IDs are excluded; ``original_claim_id`` is excluded
    too, so a generated historical claim ID cannot cause a rerun churn. On reuse
    the first row's historical claim ID and metadata are retained, not
    overwritten.
    """
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("case_id is required")
    if not isinstance(capture_id, str) or not capture_id:
        raise ValueError("capture_id is required")
    if not isinstance(claim_text, str):
        raise TypeError("claim_text must be a str")

    # Ownership/existence reads run with autoflush disabled: a caller session may
    # carry unrelated pending rows (for example an incomplete Event), and this
    # helper must never flush them as a side effect of a validation query. The
    # only flush performed is the explicit ``flush([citation])`` below.
    with session.no_autoflush:
        case = session.query(TopicCase).filter(TopicCase.id == case_id).first()
        if case is None:
            raise LookupError(f"Case {case_id!r} does not exist")

        capture = (
            session.query(EvidenceCapture)
            .filter(EvidenceCapture.id == capture_id)
            .first()
        )
        if capture is None:
            raise LookupError(f"Capture {capture_id!r} does not exist")

        # ORM columns are typed as ``Column[str]`` by the checker; at runtime these
        # are the stored values used for ownership checks.
        owning_evidence_id = cast(str, capture.evidence_id)
        evidence = (
            session.query(EvidenceItem)
            .filter(EvidenceItem.id == owning_evidence_id)
            .first()
        )
        if evidence is None:
            raise LookupError(f"Capture {capture_id!r} has no owning evidence item")
        if cast(str | None, evidence.case_id) != case_id:
            raise ValueError(
                "Capture does not belong to the requested case; refusing to invent a "
                "case/citation pair"
            )
        if evidence_id is not None and cast(str, evidence.id) != evidence_id:
            raise ValueError("Capture does not belong to the supplied evidence item")

        if original_claim_id is not None:
            live_claim = (
                session.query(Claim).filter(Claim.id == original_claim_id).first()
            )
            if live_claim is not None:
                live_event = (
                    session.query(Event)
                    .filter(Event.id == live_claim.event_id)
                    .first()
                )
                if live_event is None or cast(str | None, live_event.case_id) != case_id:
                    raise ValueError(
                        "Historical claim ID belongs to a different case; refusing a "
                        "cross-case citation"
                    )

    alignment = validate_quote_alignment(
        cast(str | None, capture.text), proposal, scope
    )
    resolution = resolve_effective_relationship(
        stored_relation=stored_relation,
        alignment_status=alignment.status,
        assessment_origin=assessment_origin,
        assessment_version=assessment_version,
        exact_anchor=alignment.is_exact,
        collector_generated=collector_generated,
    )

    # Gating: only an exact passage that the policy declares citation-eligible may
    # become an immutable citation. Unprovenanced/unknown-origin proposals stay
    # diagnostics with the raw proposal and alignment reason retained.
    if not alignment.is_exact or not resolution.citation_eligible:
        notes = (
            ("exact_passage_not_citation_eligible",)
            if alignment.is_exact
            else ("invalid_proposal_diagnostic_only",)
        )
        return CitationRecordResult(
            citation=None,
            alignment=alignment,
            relationship=resolution,
            created=False,
            notes=notes,
        )

    assert alignment.quote is not None  # exact implies a frozen passage

    # Freeze the *actual* known provenance. A trusted collector is recorded as the
    # extractor role (never falsely as model/human); an unknown specific
    # model/version stays unknown instead of being fabricated.
    collector_context = collector_generated is True
    if collector_context:
        frozen_origin: str | None = COLLECTOR_ORIGIN
        frozen_version: str | None = (
            assessment_version.strip() if isinstance(assessment_version, str) else None
        )
    else:
        # The gate above already required ``citation_eligible``, which for an
        # explicit assessment means a recognised origin string and a concrete
        # opaque version string. Assert those precise types (fail closed) instead
        # of suppressing the checker; origin is normalized policy vocabulary while
        # the version keeps its actual casing.
        if not isinstance(assessment_origin, str) or not isinstance(
            assessment_version, str
        ):
            raise ValueError(
                "citation-eligible assessment is missing a string origin or version"
            )
        frozen_origin = assessment_origin.strip().lower()
        frozen_version = assessment_version.strip()

    assessment_content = assessment_identity_content(assessment_metadata)
    identity = {
        "case_id": case_id,
        "capture_id": capture_id,
        "claim_signature": claim_signature,
        "claim_text": claim_text,
        "quote": alignment.quote,
        "start_char": alignment.start_char,
        "end_char": alignment.end_char,
        "scope_start_char": scope.start_char if scope else None,
        "scope_end_char": scope.end_char if scope else None,
        "scope_body_sha256": scope.body_sha256 if scope else None,
        "relationship": resolution.effective_relationship,
        "alignment_status": alignment.status,
        "alignment_version": alignment.alignment_version,
        "assessment_origin": frozen_origin,
        "assessment_version": frozen_version,
        "assessment_content": assessment_content,
    }
    citation_id = compute_citation_id(identity)

    with session.no_autoflush:
        existing = (
            session.query(ClaimCitation)
            .filter(ClaimCitation.id == citation_id)
            .first()
        )
    if existing is not None:
        # Frozen: never overwrite the first historical claim ID or metadata.
        return CitationRecordResult(
            citation=existing,
            alignment=alignment,
            relationship=resolution,
            created=False,
            notes=("reused_existing_citation",),
        )

    # The first full raw caller assessment metadata is retained verbatim (deep
    # copy) in its own namespace, so reserved generated keys can never overwrite or
    # lose caller content. Only citation *identity* filters volatile keys.
    frozen_metadata = {
        RAW_ASSESSMENT_METADATA_KEY: copy.deepcopy(dict(assessment_metadata or {})),
        GENERATED_ALIGNMENT_METADATA_KEY: {
            "version": alignment.alignment_version,
            "status": alignment.status,
            "diagnostic": alignment.diagnostic_reason,
            "scope": {
                "start_char": identity["scope_start_char"],
                "end_char": identity["scope_end_char"],
                "body_sha256": identity["scope_body_sha256"],
            },
            "proposal": {
                "quote": alignment.proposed_quote,
                "start_char": alignment.proposed_start_char,
                "end_char": alignment.proposed_end_char,
            },
        },
        GENERATED_RELATIONSHIP_METADATA_KEY: {
            "effective": resolution.effective_relationship,
            "stored": stored_relation,
            "policy_version": resolution.policy_version,
            "reason": resolution.reason,
            "assessed": resolution.assessed,
        },
    }

    citation = ClaimCitation(
        id=citation_id,
        case_id=case_id,
        capture_id=capture_id,
        original_claim_id=original_claim_id,
        claim_signature=claim_signature,
        text=claim_text,
        relationship=resolution.effective_relationship,
        quote=alignment.quote,
        start_char=alignment.start_char,
        end_char=alignment.end_char,
        alignment_status=alignment.status,
        alignment_version=alignment.alignment_version,
        assessment_origin=frozen_origin,
        assessment_version=frozen_version,
        metadata_json=copy.deepcopy(frozen_metadata),
        recorded_at=_normalize_recorded_at(recorded_at),
    )
    session.add(citation)
    # Flush only this row so a caller can reference it immediately; unrelated
    # pending parents must not be flushed out of order.
    session.flush([citation])
    return CitationRecordResult(
        citation=citation,
        alignment=alignment,
        relationship=resolution,
        created=True,
        notes=("created_new_citation",),
    )


__all__ = [
    "ALIGNMENT_VERSION",
    "ASSESSED_RELATIONSHIPS",
    "ASSESSMENT_ORIGINS",
    "UNKNOWN_ASSESSMENT_VERSION_MARKERS",
    "CITATION_IDENTITY_FIELDS",
    "COLLECTOR_ORIGIN",
    "DEFAULT_ALIGNMENT_STATUS",
    "GENERATED_ALIGNMENT_METADATA_KEY",
    "GENERATED_RELATIONSHIP_METADATA_KEY",
    "LEGACY_RELATIONSHIP_ALIASES",
    "NON_CORROBORATING_RELATIONSHIPS",
    "RAW_ASSESSMENT_METADATA_KEY",
    "RELATIONSHIP_POLICY_VERSION",
    "RELATIONSHIP_VOCABULARY",
    "VOLATILE_ASSESSMENT_METADATA_KEYS",
    "AnalysisScope",
    "CitationRecordResult",
    "QuoteAlignment",
    "QuoteProposal",
    "RelationshipResolution",
    "assessment_identity_content",
    "canonical_relationship",
    "compute_citation_id",
    "compute_quote_text_sha256",
    "effective_relationship_for_alignment",
    "link_contribution",
    "record_claim_citation",
    "resolve_effective_relationship",
    "validate_quote_alignment",
]
