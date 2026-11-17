"""Canonical analysis hashing and review invalidation helpers.

The hash is a deterministic, versioned fingerprint of the *meaningful* stored
analysis for one event: the event determination, its claims and their
relationships to evidence, narrative summaries and party investigations.

Deliberately excluded so that equivalent reruns do not invalidate a human
review:

* generated row identifiers (event-scoped claim/evidence/link UUIDs),
* ordering of claims/evidence/narratives,
* run IDs, stage IDs and generated timestamps (``created_at`` etc.),
* case-level derived aggregates (``support_count``, ``oppose_count``,
  ``source_diversity_count``), and
* volatile capture observation times and session-scoring metadata. The bounded
  stable metadata subset, verification checks and human-review flag are included.

The helpers only read the database and never commit; callers own the
transaction (and must flush pending writes before computing a hash).

ORM rows are annotated ``Any`` because the storage models use untyped classic
``Column`` declarations; that keeps instance attributes usable without
weakening runtime behavior.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from src.storage.citations import resolve_effective_relationship
from src.storage.models import (
    Claim,
    ClaimEvidenceLink,
    Event,
    EvidenceCapture,
    EvidenceItem,
    EvidenceVerificationCheck,
    Narrative,
    Party,
    PartyInvestigation,
    ReviewStatus,
)

# Current hash version (E02): pins validated quotation/alignment/assessment
# semantics and the cited capture body hash instead of the mutable content
# projection. The original B01 projection remains available for the transition
# (see ``LEGACY_ANALYSIS_HASH_VERSION``).
ANALYSIS_HASH_VERSION = "e02.v1"
LEGACY_ANALYSIS_HASH_VERSION = "b01.v1"
ANALYSIS_HASH_PROJECTIONS = ("e02", "b01")

# The honest default alignment status of a link that never had a passage.
NOT_PROVIDED_ALIGNMENT_STATUS = "not_provided"

# Stable subset of ``ClaimEvidenceLink.assessment_metadata`` hashed by the e02
# projection. The writer stores only these deterministic diagnostic keys; times,
# IDs and caller-specific blobs are deliberately excluded.
STABLE_ASSESSMENT_METADATA_KEYS = frozenset(
    {
        "alignment_version",
        "relationship_policy",
        "stored_relation",
        "diagnostic_reason",
    }
)

# Nested analysis arrays that are documented as unordered collections. All other
# nested lists are ordered by default: reordering them invalidates the hash.
UNORDERED_NESTED_LIST_FIELDS = frozenset(
    {"claims_supported", "claims_contested", "unique_claims"}
)

# Bounded subset of ``EvidenceItem.capture_metadata`` treated as semantic
# source/capture semantics. Generated observation times and plan/session scoring
# (``queries``, ``confirmed_parties``, ``relevance_score``, ``fetched_at``,
# ``observed_at`` etc.) are deliberately excluded.
STABLE_CAPTURE_METADATA_KEYS = frozenset(
    {
        "country",
        "language",
        "affiliation",
        "party_affiliation",
        "perspective",
        "fetch_strategy",
        "source_type",
        "credibility_tier",
        "name",
        "publisher",
        "publisher_key",
        "domain",
        "host",
        "submitted_via",
        "capture_status",
        "content_status",
        "capture_kind",
        "extraction_method",
        "is_fallback",
    }
)


class AnalysisCanonicalizationError(ValueError):
    """Raised when generated identity keys collide with conflicting semantics."""

# Statuses that represent an actual human decision which may be invalidated.
DECISION_STATUSES = frozenset(
    {
        ReviewStatus.APPROVED,
        ReviewStatus.REJECTED,
        ReviewStatus.ACTION_REQUIRED,
        ReviewStatus.EDITED,
    }
)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sorted_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(entries, key=_canonical_json)


def _normalize_references(
    value: Any,
    references: dict[str, str],
    *,
    field_name: str | None = None,
) -> Any:
    """Replace generated identity strings and normalize known collections.

    Bounded normalization for nested analysis payloads (party investigations
    in particular):

    * a string that exactly equals a known generated claim/evidence/party ID is
      replaced with its stable reference (claim signature/text, evidence URL,
      party canonical name); the same applies to dict **keys**, so
      ``party_positions`` keyed by party row ID projects onto the canonical name;
    * if two keys project onto the same canonical key with equal values they are
      merged, and with different values an ``AnalysisCanonicalizationError`` is
      raised instead of silently dropping data;
    * lists are ordered by default — only fields listed in
      ``UNORDERED_NESTED_LIST_FIELDS`` are sorted, so a reordered reasoning
      sequence still invalidates the hash while an equivalent claim-set reorder
      does not.

    See ``docs/architecture/20261115-review-invalidation.md``.
    """
    if isinstance(value, dict):
        normalized: dict[Any, Any] = {}
        for key, item in value.items():
            canonical_key = (
                references.get(key, key) if isinstance(key, str) else key
            )
            normalized_item = _normalize_references(
                item, references, field_name=canonical_key
            )
            if canonical_key in normalized:
                if _canonical_json(normalized[canonical_key]) != _canonical_json(
                    normalized_item
                ):
                    raise AnalysisCanonicalizationError(
                        "conflicting values for canonical analysis reference "
                        f"{canonical_key!r}"
                    )
                continue
            normalized[canonical_key] = normalized_item
        return normalized
    if isinstance(value, list):
        items = [
            _normalize_references(item, references, field_name=field_name)
            for item in value
        ]
        if field_name in UNORDERED_NESTED_LIST_FIELDS:
            return sorted(items, key=_canonical_json)
        return items
    if isinstance(value, str) and value in references:
        return references[value]
    return value


def _stable_capture_metadata(
    metadata: Any, references: dict[str, str]
) -> dict[str, Any]:
    """Project capture metadata onto the documented stable semantic subset."""
    if not isinstance(metadata, dict):
        return {}
    subset = {
        key: metadata[key]
        for key in sorted(STABLE_CAPTURE_METADATA_KEYS)
        if key in metadata
    }
    return _normalize_references(subset, references)


def _strip_event_prefix(cluster_id: Any, event_prefix: str) -> Any:
    if isinstance(cluster_id, str) and cluster_id.startswith(event_prefix):
        return cluster_id[len(event_prefix) :]
    return cluster_id


def _stored_relation_diagnostic(link: Any) -> Any:
    """Return the raw requested relation preserved as a diagnostic.

    The writer stores the *effective* relationship in ``relation`` and keeps the
    raw caller value in ``assessment_metadata["stored_relation"]``. The legacy
    (B01) projection hashes the raw value, exactly as pre-E02 rows stored it, so
    a version bump over an unchanged legacy rerun reconstructs the approved view.
    Rows without a diagnostic fall back to ``link.relation`` unchanged.
    """
    metadata = link.assessment_metadata
    if isinstance(metadata, dict) and "stored_relation" in metadata:
        return metadata["stored_relation"]
    return link.relation


def _link_has_citation_semantics(link: Any) -> bool:
    """Whether a link actually carries quotation/alignment/assessment semantics.

    A bare source attachment (no proposal, no alignment state, no provenance) has
    none: it contributes an entry identical to the B01 projection, so unchanged
    legacy data keeps an identical digest after the algorithm-version bump.
    """
    if link.citation_id:
        return True
    if link.quote is not None or link.start_char is not None or link.end_char is not None:
        return True
    status = link.alignment_status
    if isinstance(status, str) and status and status != NOT_PROVIDED_ALIGNMENT_STATUS:
        return True
    return link.assessment_origin is not None or link.assessment_version is not None


def _effective_relationship(link: Any) -> str:
    """Resolve one stored link through the single versioned policy."""
    return resolve_effective_relationship(
        stored_relation=link.relation,
        alignment_status=link.alignment_status,
        assessment_origin=link.assessment_origin,
        assessment_version=link.assessment_version,
        exact_anchor=(link.alignment_status == "exact"),
        collector_generated=(link.assessment_origin == "collector"),
    ).effective_relationship


def _stable_assessment_metadata(metadata: Any) -> dict[str, Any]:
    """Project persisted assessment metadata onto the documented stable subset."""
    if not isinstance(metadata, dict):
        return {}
    return {
        key: metadata[key]
        for key in sorted(STABLE_ASSESSMENT_METADATA_KEYS)
        if key in metadata
    }


def _content_fingerprint(content: Any) -> str:
    """Stable fallback for a semantics link that has no cited capture."""
    text = content if isinstance(content, str) else ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _evidence_entry(
    link: Any,
    evidence: Any,
    checks: list[dict[str, Any]],
    references: dict[str, str],
    *,
    projection: str,
    captures_by_id: dict[str, Any],
) -> dict[str, Any]:
    entry = {
        "evidence_type": evidence.evidence_type,
        "source_type": evidence.source_type,
        "title": evidence.title,
        "origin_url": evidence.origin_url,
        "canonical_url": evidence.canonical_url,
        "archived_url": evidence.archived_url,
        "publisher": evidence.publisher,
        "published_at": evidence.published_at,
        "content": evidence.content,
        "verification_status": evidence.verification_status,
        "credibility_tier": evidence.credibility_tier,
        "requires_human_review": (
            evidence.requires_human_review
            if evidence.requires_human_review is not None
            else 0
        ),
        "capture_metadata": _stable_capture_metadata(
            evidence.capture_metadata, references
        ),
        "verification_checks": _sorted_entries(checks),
        "relation": _stored_relation_diagnostic(link),
        "confidence_score": link.confidence_score,
        "notes": link.notes,
    }
    if projection == "b01" or not _link_has_citation_semantics(link):
        # The B01 projection, and every bare attachment under e02, hashes the raw
        # stored relation plus the mutable ``content`` projection. Identical
        # entries are required so a version bump over unchanged legacy data does
        # not change the digest.
        return entry

    # A link with real quotation/alignment/assessment semantics pins the
    # effective relationship and the cited capture body hash instead of the
    # mutable content projection. Capture/citation IDs, times and row order are
    # still excluded. A semantics link without a cited capture falls back to a
    # content fingerprint so the projection stays deterministic.
    capture = None
    if link.capture_id:
        capture = captures_by_id.get(str(link.capture_id))
    entry.pop("content", None)
    entry["relation"] = _effective_relationship(link)
    entry["capture_text_sha256"] = (
        capture.text_sha256 if capture is not None else _content_fingerprint(evidence.content)
    )
    entry["quotation"] = {
        "quote": link.quote,
        "start_char": link.start_char,
        "end_char": link.end_char,
        "alignment_status": link.alignment_status,
        "assessment_origin": link.assessment_origin,
        "assessment_version": link.assessment_version,
        "assessment_metadata": _stable_assessment_metadata(link.assessment_metadata),
    }
    return entry


def canonical_analysis_payload(
    db_session: Session, event_id: str, *, projection: str = "e02"
) -> dict[str, Any]:
    """Build the canonical (order- and ID-independent) analysis payload.

    ``projection`` selects the hash algorithm: ``e02`` (current) pins validated
    quotation/alignment/assessment semantics and the cited capture body hash;
    ``b01`` keeps the original projection for the review transition.
    """
    if projection not in ANALYSIS_HASH_PROJECTIONS:
        raise ValueError(
            f"Unknown analysis hash projection {projection!r}; "
            f"expected one of {ANALYSIS_HASH_PROJECTIONS}"
        )
    version = (
        ANALYSIS_HASH_VERSION if projection == "e02" else LEGACY_ANALYSIS_HASH_VERSION
    )
    event: Any = db_session.query(Event).filter(Event.id == event_id).first()
    if event is None:
        return {
            "version": version,
            "event": None,
            "claims": [],
            "narratives": [],
            "party_investigations": [],
        }

    claims: list[Any] = (
        db_session.query(Claim).filter(Claim.event_id == event_id).all()
    )
    investigations: list[Any] = (
        db_session.query(PartyInvestigation)
        .filter(PartyInvestigation.event_id == event_id)
        .all()
    )
    claim_ids = [claim.id for claim in claims]
    links: list[Any] = (
        db_session.query(ClaimEvidenceLink)
        .filter(ClaimEvidenceLink.claim_id.in_(claim_ids))
        .all()
        if claim_ids
        else []
    )
    evidence_ids = [link.evidence_id for link in links]
    captures_by_id: dict[str, Any] = {}
    if projection == "e02":
        capture_ids = sorted(
            {str(link.capture_id) for link in links if link.capture_id}
        )
        if capture_ids:
            captures_by_id = {
                str(capture.id): capture
                for capture in db_session.query(EvidenceCapture)
                .filter(EvidenceCapture.id.in_(capture_ids))
                .all()
            }
    evidence_by_id: dict[Any, Any] = {}
    checks_by_evidence: dict[Any, list[dict[str, Any]]] = {}
    if evidence_ids:
        evidence_by_id = {
            item.id: item
            for item in db_session.query(EvidenceItem)
            .filter(EvidenceItem.id.in_(evidence_ids))
            .all()
        }
        for check in (
            db_session.query(EvidenceVerificationCheck)
            .filter(EvidenceVerificationCheck.evidence_id.in_(evidence_ids))
            .all()
        ):
            checks_by_evidence.setdefault(check.evidence_id, []).append(
                {
                    "check_type": check.check_type,
                    "result": check.result,
                    "method": check.method,
                    "notes": check.notes,
                    "verified_by": check.verified_by,
                }
            )
    # Resolve the union of claim and investigation party IDs: an investigated
    # party need not be a claim's representative, and its generated row ID must
    # never leak into the hash.
    party_ids = {claim.party_id for claim in claims if claim.party_id}
    party_ids.update(
        investigation.party_id for investigation in investigations if investigation.party_id
    )
    party_names: dict[Any, Any] = {}
    if party_ids:
        party_names = {
            party.id: party.canonical_name
            for party in db_session.query(Party)
            .filter(Party.id.in_(sorted(party_ids)))
            .all()
        }

    # Stable references for any generated identity string buried in nested
    # analysis payloads such as party investigation JSON.
    references: dict[str, str] = {}
    for claim in claims:
        reference = claim.claim_signature or claim.claim_text or claim.id
        references[str(claim.id)] = str(reference)
    for evidence in evidence_by_id.values():
        reference = (
            evidence.canonical_url
            or evidence.origin_url
            or evidence.title
            or evidence.id
        )
        references[str(evidence.id)] = str(reference)
    for party_id, canonical_name in party_names.items():
        references[str(party_id)] = str(canonical_name)

    links_by_claim: dict[Any, list[Any]] = {}
    for link in links:
        links_by_claim.setdefault(link.claim_id, []).append(link)

    event_prefix = f"{event_id}:"
    claim_entries: list[dict[str, Any]] = []
    for claim in claims:
        evidence_entries: list[dict[str, Any]] = []
        seen_evidence: set[str] = set()
        for link in links_by_claim.get(claim.id, []):
            evidence = evidence_by_id.get(link.evidence_id)
            if evidence is None:
                continue
            entry = _evidence_entry(
                link,
                evidence,
                checks_by_evidence.get(evidence.id, []),
                references,
                projection=projection,
                captures_by_id=captures_by_id,
            )
            encoded = _canonical_json(entry)
            if encoded in seen_evidence:
                continue
            seen_evidence.add(encoded)
            evidence_entries.append(entry)
        claim_entries.append(
            {
                "claim_text": claim.claim_text,
                "claim_signature": claim.claim_signature,
                "verification_status": _enum_value(claim.verification_status),
                "fact_allegation_type": _enum_value(claim.fact_allegation_type),
                "party": party_names.get(claim.party_id),
                # Cluster IDs are generated analysis identity; strip any event
                # prefix so a regenerated cluster identity is not compared as
                # substantive text.
                "narrative_cluster_id": _normalize_references(
                    _strip_event_prefix(claim.narrative_cluster_id, event_prefix),
                    references,
                ),
                "arbiter_reasoning": claim.arbiter_reasoning,
                "party_positions": _normalize_references(
                    claim.party_positions, references
                ),
                "controversy_score": claim.controversy_score,
                "evidence": _sorted_entries(evidence_entries),
            }
        )

    narratives = []
    for narrative in (
        db_session.query(Narrative)
        .filter(Narrative.cluster_id.startswith(event_prefix, autoescape=True))
        .all()
    ):
        cluster_id = _strip_event_prefix(str(narrative.cluster_id or ""), event_prefix)
        narratives.append(
            {
                "cluster_id": cluster_id,
                "stance_summary": narrative.stance_summary,
                "source_count": narrative.source_count,
            }
        )

    investigation_entries: list[dict[str, Any]] = []
    for investigation in investigations:
        investigation_entries.append(
            {
                "party": party_names.get(investigation.party_id)
                or investigation.party_id,
                "investigation_data": _normalize_references(
                    investigation.investigation_data, references
                ),
                "party_stance": _normalize_references(
                    investigation.party_stance, references
                ),
            }
        )

    return {
        "version": version,
        "event": {
            "title": event.title,
            "summary": event.summary,
            "verification_status": _enum_value(event.verification_status),
            "location_country_code": event.location_country_code,
            "location_lat": event.location_lat,
            "location_lon": event.location_lon,
        },
        "claims": _sorted_entries(claim_entries),
        "narratives": _sorted_entries(narratives),
        "party_investigations": _sorted_entries(investigation_entries),
    }


def _hash_for_projection(
    db_session: Session, event_id: str, *, projection: str
) -> str:
    payload = canonical_analysis_payload(db_session, event_id, projection=projection)
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    version = (
        ANALYSIS_HASH_VERSION if projection == "e02" else LEGACY_ANALYSIS_HASH_VERSION
    )
    return f"{version}:{digest}"


def compute_event_analysis_hash(db_session: Session, event_id: str) -> str:
    """Return the current (``e02``) versioned canonical analysis hash."""
    return _hash_for_projection(db_session, event_id, projection="e02")


def compute_legacy_event_analysis_hash(db_session: Session, event_id: str) -> str:
    """Return the original B01 analysis hash (review-transition only)."""
    return _hash_for_projection(db_session, event_id, projection="b01")


def reconcile_review_with_analysis(
    review: Any,
    analysis_hash: str,
    *,
    legacy_analysis_hash: str | None = None,
    now: datetime | None = None,
) -> bool:
    """Preserve or invalidate a review after analysis was rewritten.

    Returns ``True`` when a stored decision was invalidated. Human notes are
    never overwritten: prior decision details are copied into
    ``previous_decision_json`` and the notes column is left untouched.

    ``legacy_analysis_hash`` is the B01 digest of the rows that are now stored.
    When the review's stored hash equals it, the stored rows are exactly the
    analysis that was approved; only the algorithm version changed, so the
    decision is kept, the hash is rebound to the current version and the prior
    decision/notes are left untouched. A ``NULL`` stored hash keeps the B01
    conservative legacy policy: an existing decision cannot be proven unchanged.
    """
    stored_hash = review.analysis_hash or None
    if stored_hash == analysis_hash:
        return False

    decided = review.status is not None and review.status in DECISION_STATUSES
    if legacy_analysis_hash is not None and stored_hash == legacy_analysis_hash:
        # Algorithm/version-only transition over unchanged stored analysis.
        if review.status is None:
            review.status = ReviewStatus.PENDING
        review.analysis_hash = analysis_hash
        return False

    if not decided:
        # No decision to protect: adopt the freshly recorded baseline.
        if review.status is None:
            review.status = ReviewStatus.PENDING
        review.analysis_hash = analysis_hash
        return False

    reviewed_at = review.reviewed_at
    review.previous_decision_json = {
        "status": _enum_value(review.status),
        "reviewed_at": reviewed_at.isoformat() if reviewed_at else None,
        "notes": review.notes,
        "analysis_hash": stored_hash,
        "reason": "analysis_changed" if stored_hash else "analysis_hash_unavailable",
        "invalidated_at": (now or datetime.now(UTC)).isoformat(),
        "new_analysis_hash": analysis_hash,
    }
    review.status = ReviewStatus.PENDING
    review.reviewed_at = None
    review.analysis_hash = analysis_hash
    return True


def bind_review_decision(review: Any, analysis_hash: str) -> None:
    """Bind an explicit human decision to the current analysis version."""
    review.analysis_hash = analysis_hash
    review.previous_decision_json = None


__all__ = [
    "ANALYSIS_HASH_PROJECTIONS",
    "ANALYSIS_HASH_VERSION",
    "DECISION_STATUSES",
    "LEGACY_ANALYSIS_HASH_VERSION",
    "STABLE_ASSESSMENT_METADATA_KEYS",
    "bind_review_decision",
    "canonical_analysis_payload",
    "compute_event_analysis_hash",
    "compute_legacy_event_analysis_hash",
    "reconcile_review_with_analysis",
]
