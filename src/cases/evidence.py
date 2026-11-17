"""Service-facing immutable evidence capture helpers.

The implementation lives in :mod:`src.storage.captures` (a storage-layer module)
so the event store can use it without the ``src.cases`` package's eager service
import creating a cycle. This module is the documented service-facing seam:
normalization, exact-body hashing, the separate dependency fingerprint, the
session-owned capture upsert/pointer helper and the explicit offline legacy
materialization operation.

No function here commits, rolls back or closes a caller-owned session, and no
read or migration path materializes captures automatically.
"""

from src.storage.captures import (
    CAPTURE_NORMALIZATION_VERSION,
    build_capture_metadata,
    compute_normalized_text_sha256,
    compute_text_sha256,
    fingerprint_text,
    get_capture,
    materialize_legacy_capture,
    normalize_capture_text,
    record_evidence_capture,
    upsert_evidence_capture,
)
from src.storage.citations import (
    ALIGNMENT_VERSION,
    RELATIONSHIP_POLICY_VERSION,
    RELATIONSHIP_VOCABULARY,
    AnalysisScope,
    CitationRecordResult,
    QuoteAlignment,
    QuoteProposal,
    RelationshipResolution,
    canonical_relationship,
    effective_relationship_for_alignment,
    link_contribution,
    record_claim_citation,
    resolve_effective_relationship,
    validate_quote_alignment,
)

__all__ = [
    "ALIGNMENT_VERSION",
    "RELATIONSHIP_POLICY_VERSION",
    "RELATIONSHIP_VOCABULARY",
    "CAPTURE_NORMALIZATION_VERSION",
    "AnalysisScope",
    "CitationRecordResult",
    "QuoteAlignment",
    "QuoteProposal",
    "RelationshipResolution",
    "build_capture_metadata",
    "canonical_relationship",
    "compute_normalized_text_sha256",
    "compute_text_sha256",
    "effective_relationship_for_alignment",
    "fingerprint_text",
    "get_capture",
    "link_contribution",
    "materialize_legacy_capture",
    "normalize_capture_text",
    "record_claim_citation",
    "record_evidence_capture",
    "resolve_effective_relationship",
    "upsert_evidence_capture",
    "validate_quote_alignment",
]
