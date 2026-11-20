"""Conservative source identity and dependency grouping (P01).

Contract: evidence-workbench specification §5. This module is deliberately a
**read-only, local** policy layer:

* URLs are canonicalized without fetching or rewriting anything;
* publisher identity comes only from explicit frozen metadata or an exact
  normalized host, never from name similarity;
* dependency edges are limited to identical normalized URLs, the same known
  publisher key, identical long text fingerprints and documented common origins;
* groups are connected components with deterministic IDs/order and honest
  unknown counts.

No function here commits, rolls back or closes a caller-owned session. No
external lookup, model call or near-duplicate/semantic matching is performed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import unicodedata
from typing import Any, Mapping
from urllib.parse import unquote_plus, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage import (
    Claim,
    ClaimEvidenceLink,
    EvidenceCapture,
    EvidenceItem,
    Event,
    TopicCase,
)

POLICY_VERSION = "source-dependency-policy-v1"
TEXT_FINGERPRINT_VERSION = "text-fingerprint-v1"
MIN_COPY_NON_WHITESPACE_CODE_POINTS = 200

REASON_SAME_SOURCE_URL = "same_source_url"
REASON_SAME_PUBLISHER = "same_publisher"
REASON_IDENTICAL_CAPTURE_TEXT = "identical_normalized_capture"
REASON_SAME_CASE_ARTICLE = "same_case_article"
REASON_DOCUMENTED_COMMON_ORIGIN = "documented_common_origin"

_TRACKING_PARAM_NAMES = frozenset({"fbclid", "gclid"})
_TRACKING_PARAM_PREFIXES = ("utm_",)
_EXPLICIT_PUBLISHER_FIELDS = ("publisher_key", "publisher_identity")
_EXPLICIT_ORIGIN_FIELDS = ("source_dependency_key", "dependency_key")

LIMITATIONS = [
    "Near-duplicate and semantic syndication detection is not implemented in v1.",
    "Absence of a detected dependency does not prove that sources are independent.",
    "A provisional host key identifies a domain, not common editorial control.",
    "Publisher display names alone are never used to infer ownership or aliases.",
]


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _metadata(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def normalize_source_url(value: str | None) -> str | None:
    """Canonicalize one HTTP(S) URL for exact-identity comparison.

    Host is lowercased/IDNA-normalized; fragment, userinfo and default ports are
    removed; an empty path becomes ``/``; only ``utm_*``, ``fbclid`` and
    ``gclid`` query parameters are dropped. Path case, trailing slashes, other
    query values and the HTTP/S distinction are preserved. Unsupported or
    malformed values return ``None`` rather than a guessed identity.
    """
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
        scheme = parts.scheme.lower()
        if scheme not in {"http", "https"}:
            return None
        host = parts.hostname
        if not host:
            return None
        host = host.lower()
        host = host.encode("idna").decode("ascii")
        port = parts.port
    except (UnicodeError, ValueError):
        return None

    if not host:
        return None
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = 80 if scheme == "http" else 443
    netloc = host if port in (None, default_port) else f"{host}:{port}"
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, _filter_tracking(parts.query), ""))


def _filter_tracking(query: str) -> str:
    """Drop only the documented tracking parameters, preserving raw values."""
    if not query:
        return ""
    kept: list[str] = []
    for part in query.split("&"):
        if not part:
            continue
        raw_key = part.split("=", 1)[0]
        key = unquote_plus(raw_key).lower()
        if key in _TRACKING_PARAM_NAMES or key.startswith(_TRACKING_PARAM_PREFIXES):
            continue
        kept.append(part)
    return "&".join(kept)


def _host_from_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return urlsplit(value).hostname or None
    except ValueError:
        return None


def _explicit_value(
    metadata_sources: tuple[Mapping[str, Any], ...], fields: tuple[str, ...]
) -> tuple[str | None, bool]:
    """Return the first explicit non-blank metadata value and whether it existed.

    The boolean distinguishes an explicit (non-provisional) identity from a
    host-derived fallback even when the value itself is into the fallback path.
    """
    for metadata in metadata_sources:
        for field_name in fields:
            value = metadata.get(field_name)
            if isinstance(value, str) and value.strip():
                return value.strip(), True
    return None, False


@dataclass(frozen=True)
class SourceMember:
    """One evidence/capture record participating in grouping."""

    evidence_id: str
    publisher: str | None
    publisher_key: str | None
    publisher_key_provisional: bool
    host: str | None
    origin_url: str | None
    canonical_url: str | None
    source_url: str | None
    case_article_id: str | None
    explicit_origin_key: str | None
    capture_id: str | None
    capture_kind: str | None
    capture_text_sha256: str | None
    capture_normalized_text_sha256: str | None
    capture_char_length: int | None
    recorded_at: str | None
    observed_at: str | None
    copy_fingerprint: str | None
    copy_non_whitespace_count: int
    dependency_reasons: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "publisher": self.publisher,
            "publisher_key": self.publisher_key,
            "publisher_key_provisional": self.publisher_key_provisional,
            "host": self.host,
            "origin_url": self.origin_url,
            "canonical_url": self.canonical_url,
            "source_url": self.source_url,
            "case_article_id": self.case_article_id,
            "explicit_origin_key": self.explicit_origin_key,
            "capture_id": self.capture_id,
            "capture_kind": self.capture_kind,
            "capture_text_sha256": self.capture_text_sha256,
            "capture_normalized_text_sha256": self.capture_normalized_text_sha256,
            "capture_char_length": self.capture_char_length,
            "recorded_at": self.recorded_at,
            "observed_at": self.observed_at,
            "copy_fingerprint": self.copy_fingerprint,
            "copy_non_whitespace_count": self.copy_non_whitespace_count,
            "dependency_reasons": list(self.dependency_reasons),
        }


@dataclass(frozen=True)
class PublisherIdentity:
    key: str | None
    provisional: bool
    host: str | None


def resolve_publisher_identity(
    *,
    publisher: str | None,
    source_url: str | None,
    metadata_sources: tuple[Mapping[str, Any], ...],
) -> PublisherIdentity:
    """Resolve a publisher key without inferring from display names.

    Explicit ``publisher_key``/``publisher_identity`` metadata wins. Otherwise
    the exact normalized host is a provisional key. A display name alone stays
    unknown. ``publisher`` is retained only for display in the caller.
    """
    del publisher  # display only; never an identity input
    explicit, found = _explicit_value(metadata_sources, _EXPLICIT_PUBLISHER_FIELDS)
    if found and explicit is not None:
        return PublisherIdentity(key=explicit.casefold(), provisional=False, host=_host_from_url(source_url))
    host = _host_from_url(source_url)
    if host:
        return PublisherIdentity(key=host, provisional=True, host=host)
    return PublisherIdentity(key=None, provisional=False, host=None)


def copy_fingerprint(text: str | None) -> tuple[str | None, int]:
    """Return ``(fingerprint, non_whitespace_count)`` for copy detection.

    v1 normalizes with NFKC, casefolds and collapses all whitespace. A fingerprint
    is returned only when at least
    :data:`MIN_COPY_NON_WHITESPACE_CODE_POINTS` non-whitespace code points
    remain, so short shared snippets can never merge two sources.
    """
    if not isinstance(text, str) or not text:
        return None, 0
    normalized = " ".join(
        unicodedata.normalize("NFKC", text).casefold().split()
    )
    non_whitespace = sum(1 for char in normalized if not char.isspace())
    if non_whitespace < MIN_COPY_NON_WHITESPACE_CODE_POINTS:
        return None, non_whitespace
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest, non_whitespace


class _UnionFind:
    """Small deterministic union-find over evidence IDs."""

    def __init__(self, ids: list[str]) -> None:
        self._parent = {member_id: member_id for member_id in ids}
        self._rank = {member_id: 0 for member_id in ids}

    def find(self, member_id: str) -> str:
        parent = self._parent[member_id]
        while parent != self._parent[parent]:
            self._parent[parent] = self._parent[self._parent[parent]]
            parent = self._parent[parent]
        self._parent[member_id] = parent
        return parent

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self._rank[left_root] < self._rank[right_root]:
            left_root, right_root = right_root, left_root
        self._parent[right_root] = left_root
        if self._rank[left_root] == self._rank[right_root]:
            self._rank[left_root] += 1


def _group_id(member_ids: list[str]) -> str:
    material = f"{POLICY_VERSION}:{','.join(sorted(member_ids))}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"source-group-{digest[:16]}"


def _member_sort_key(member: SourceMember) -> tuple[str, str, str]:
    return (
        member.publisher_key or "",
        member.source_url or "",
        member.evidence_id,
    )


def _bucket(keys: list[tuple[str, str | None]]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = defaultdict(list)
    for member_id, key in keys:
        if key:
            buckets[key].append(member_id)
    return buckets


def build_source_summary(
    *,
    case_id: str,
    scope: str,
    claim_id: str | None,
    claim_signature: str | None,
    members: list[SourceMember],
) -> dict[str, Any]:
    """Build the deterministic source summary from already-read members.

    Input order never affects the output: members, groups, reasons and publisher
    counts are all sorted/canonicalized before serialization.
    """
    unique: dict[str, SourceMember] = {}
    for member in sorted(
        members, key=lambda item: (item.evidence_id, item.capture_id or "")
    ):
        unique.setdefault(member.evidence_id, member)
    ordered = sorted(unique.values(), key=_member_sort_key)
    ids = [member.evidence_id for member in ordered]
    by_id = {member.evidence_id: member for member in ordered}

    union_find = _UnionFind(ids)
    reasons_by_member: dict[str, set[str]] = defaultdict(set)

    def union(left: str, right: str, reason: str) -> None:
        if left == right:
            return
        union_find.union(left, right)
        reasons_by_member[left].add(reason)
        reasons_by_member[right].add(reason)

    def union_buckets(
        pairs: list[tuple[str, str | None]], reason: str
    ) -> None:
        for bucket_ids in _bucket(pairs).values():
            ordered_ids = sorted(set(bucket_ids))
            for other in ordered_ids[1:]:
                union(ordered_ids[0], other, reason)

    union_buckets(
        [(member.evidence_id, member.source_url) for member in ordered],
        REASON_SAME_SOURCE_URL,
    )
    union_buckets(
        [(member.evidence_id, member.publisher_key) for member in ordered],
        REASON_SAME_PUBLISHER,
    )
    union_buckets(
        [(member.evidence_id, member.copy_fingerprint) for member in ordered],
        REASON_IDENTICAL_CAPTURE_TEXT,
    )
    union_buckets(
        [(member.evidence_id, member.case_article_id) for member in ordered],
        REASON_SAME_CASE_ARTICLE,
    )
    union_buckets(
        [(member.evidence_id, member.explicit_origin_key) for member in ordered],
        REASON_DOCUMENTED_COMMON_ORIGIN,
    )

    components: dict[str, list[str]] = defaultdict(list)
    for member_id in ids:
        components[union_find.find(member_id)].append(member_id)

    groups: list[dict[str, Any]] = []
    for member_ids in components.values():
        sorted_ids = sorted(member_ids)
        group_reasons = sorted(
            {
                reason
                for member_id in sorted_ids
                for reason in reasons_by_member.get(member_id, ())
            }
        )
        publisher_keys = sorted(
            {
                member.publisher_key
                for member_id in sorted_ids
                if (member := by_id[member_id]).publisher_key
            }
        )
        groups.append(
            {
                "id": _group_id(sorted_ids),
                "reasons": group_reasons,
                "publisher_keys": publisher_keys,
                "evidence_count": len(sorted_ids),
                "members": [
                    {
                        **by_id[member_id].to_dict(),
                        "dependency_reasons": sorted(
                            reasons_by_member.get(member_id, ())
                        ),
                    }
                    for member_id in sorted_ids
                ],
            }
        )
    groups.sort(key=lambda group: group["id"])

    publisher_members: dict[str, list[SourceMember]] = defaultdict(list)
    for member in ordered:
        if member.publisher_key:
            publisher_members[member.publisher_key].append(member)
    publisher_counts: list[dict[str, Any]] = []
    for publisher_key in sorted(publisher_members):
        keyed_members = publisher_members[publisher_key]
        display_publisher = next(
            (
                member.publisher
                for member in keyed_members
                if member.publisher
            ),
            None,
        )
        group_ids = sorted(
            {
                group["id"]
                for group in groups
                if publisher_key in group["publisher_keys"]
            }
        )
        publisher_counts.append(
            {
                "publisher_key": publisher_key,
                "publisher": display_publisher,
                "evidence_count": len(keyed_members),
                "dependency_group_count": len(group_ids),
                "provisional": all(
                    member.publisher_key_provisional for member in keyed_members
                ),
            }
        )

    dependency_detected = any(group["evidence_count"] > 1 for group in groups)
    return {
        "case_id": case_id,
        "scope": scope,
        "claim_id": claim_id,
        "claim_signature": claim_signature,
        "evidence_count": len(ordered),
        "distinct_publisher_count": len(publisher_counts),
        "dependency_group_count": len(groups),
        "unknown_publisher_count": sum(
            1 for member in ordered if not member.publisher_key
        ),
        "independence_status": (
            "dependency_detected" if dependency_detected else "unknown"
        ),
        "policy": {
            "version": POLICY_VERSION,
            "url_normalization": [
                "lowercase and IDNA-normalize the host",
                "remove fragment, userinfo and default port",
                "normalize an empty path to / and preserve path case/trailing slashes",
                "remove only utm_*, fbclid and gclid tracking parameters",
                "never equate HTTP with HTTPS or fetch the URL while reading",
            ],
            "publisher_identity": [
                "explicit publisher_key/publisher_identity metadata wins",
                "otherwise the normalized host is a provisional key",
                "publisher display names are never used to infer ownership",
            ],
            "dependency_edges": [
                REASON_SAME_SOURCE_URL,
                REASON_SAME_PUBLISHER,
                REASON_IDENTICAL_CAPTURE_TEXT,
                REASON_SAME_CASE_ARTICLE,
                REASON_DOCUMENTED_COMMON_ORIGIN,
            ],
            "text_fingerprint": TEXT_FINGERPRINT_VERSION,
            "text_fingerprint_normalization": "NFKC + casefold + collapsed whitespace",
            "min_copy_non_whitespace_code_points": (
                MIN_COPY_NON_WHITESPACE_CODE_POINTS
            ),
            "limitations": LIMITATIONS,
        },
        "publisher_counts": publisher_counts,
        "groups": groups,
    }


def _iso(value: Any) -> str | None:
    rendered = getattr(value, "isoformat", None)
    if not callable(rendered):
        return None
    result = rendered()
    return result if isinstance(result, str) else None


def _claim_belongs_to_case(session: Session, claim: Claim, case_id: str) -> bool:
    event_id = _as_str(claim.event_id)
    event = session.get(Event, event_id) if event_id else None
    return event is not None and _as_str(event.case_id) == case_id


def _capture_for(
    session: Session, evidence: EvidenceItem, requested_capture_id: str | None
) -> EvidenceCapture | None:
    """Resolve exactly the requested capture, or the current one when unspecified.

    A dangling/foreign explicit capture ID is not silently replaced by the
    current capture: that would misrepresent which text was grouped.
    """
    evidence_id = _as_str(evidence.id)
    if requested_capture_id is not None:
        capture = session.get(EvidenceCapture, requested_capture_id)
        if capture is None or _as_str(capture.evidence_id) != evidence_id:
            return None
        return capture
    current_capture_id = _as_str(evidence.current_capture_id)
    if current_capture_id is None:
        return None
    capture = session.get(EvidenceCapture, current_capture_id)
    if capture is None or _as_str(capture.evidence_id) != evidence_id:
        return None
    return capture


def _member_for(
    session: Session, evidence: EvidenceItem, capture_id: str | None
) -> SourceMember:
    capture = _capture_for(session, evidence, capture_id)
    return _member_from_values(
        evidence_id=_as_str(evidence.id) or "",
        publisher=_as_str(evidence.publisher),
        origin_url=_as_str(evidence.origin_url),
        canonical_url=_as_str(evidence.canonical_url),
        case_article_id=_as_str(evidence.case_article_id),
        metadata_sources=(
            _metadata(capture.metadata_json) if capture is not None else {},
            _metadata(evidence.capture_metadata),
        ),
        capture_id=_as_str(capture.id) if capture is not None else None,
        capture_kind=(
            _as_str(capture.capture_kind) if capture is not None else None
        ),
        capture_text_sha256=(
            _as_str(capture.text_sha256) if capture is not None else None
        ),
        capture_normalized_text_sha256=(
            _as_str(capture.normalized_text_sha256)
            if capture is not None
            else None
        ),
        capture_text=_as_str(capture.text) if capture is not None else None,
        recorded_at=_iso(capture.recorded_at) if capture is not None else None,
        observed_at=_iso(capture.observed_at) if capture is not None else None,
    )


def _member_from_values(
    *,
    evidence_id: str,
    publisher: str | None,
    origin_url: str | None,
    canonical_url: str | None,
    case_article_id: str | None,
    metadata_sources: tuple[Mapping[str, Any], Mapping[str, Any]],
    capture_id: str | None,
    capture_kind: str | None,
    capture_text_sha256: str | None,
    capture_normalized_text_sha256: str | None,
    capture_text: str | None,
    recorded_at: str | None,
    observed_at: str | None,
) -> SourceMember:
    """Build one member from already-read source values (no ORM/DB access).

    Shared by the live reader and the snapshot reader so the identity/fingerprint
    policy cannot drift between a current and a historical comparison.
    """
    source_url = normalize_source_url(canonical_url) or normalize_source_url(
        origin_url
    )
    identity = resolve_publisher_identity(
        publisher=publisher,
        source_url=source_url,
        metadata_sources=metadata_sources,
    )
    explicit_origin_key, _ = _explicit_value(
        metadata_sources, _EXPLICIT_ORIGIN_FIELDS
    )
    fingerprint: str | None = None
    non_whitespace = 0
    if capture_text is not None:
        fingerprint, non_whitespace = copy_fingerprint(capture_text)
    return SourceMember(
        evidence_id=evidence_id,
        publisher=publisher,
        publisher_key=identity.key,
        publisher_key_provisional=identity.provisional,
        host=identity.host,
        origin_url=origin_url,
        canonical_url=canonical_url,
        source_url=source_url,
        case_article_id=case_article_id,
        explicit_origin_key=explicit_origin_key,
        capture_id=capture_id,
        capture_kind=capture_kind,
        capture_text_sha256=capture_text_sha256,
        capture_normalized_text_sha256=capture_normalized_text_sha256,
        capture_char_length=len(capture_text) if capture_text is not None else None,
        recorded_at=recorded_at,
        observed_at=observed_at,
        copy_fingerprint=fingerprint,
        copy_non_whitespace_count=non_whitespace,
    )


def source_member_from_observation(
    *,
    evidence: Mapping[str, Any],
    capture: Mapping[str, Any] | None,
    capture_text: str | None,
) -> SourceMember:
    """Build a comparison member from a frozen snapshot observation.

    ``evidence``/``capture`` are snapshot payload rows (camelCase keys). Capture
    bodies are never copied into the snapshot, so ``capture_text`` must be the
    immutable capture body the caller verified against the recorded hash; pass
    ``None`` when that body is unavailable and the copy fingerprint stays
    explicitly unknown instead of being read from a different version.
    """
    capture_metadata = (
        capture.get("metadata") if capture is not None else None
    )
    return _member_from_values(
        evidence_id=_as_str(evidence.get("id")) or "",
        publisher=_as_str(evidence.get("publisher")),
        origin_url=_as_str(evidence.get("originUrl")),
        canonical_url=_as_str(evidence.get("canonicalUrl")),
        case_article_id=_as_str(evidence.get("caseArticleId")),
        metadata_sources=(
            _metadata(capture_metadata),
            _metadata(evidence.get("captureMetadata")),
        ),
        capture_id=_as_str(capture.get("id")) if capture is not None else None,
        capture_kind=(
            _as_str(capture.get("captureKind")) if capture is not None else None
        ),
        capture_text_sha256=(
            _as_str(capture.get("textSha256")) if capture is not None else None
        ),
        capture_normalized_text_sha256=(
            _as_str(capture.get("normalizedTextSha256"))
            if capture is not None
            else None
        ),
        capture_text=capture_text,
        recorded_at=(
            _as_str(capture.get("recordedAt")) if capture is not None else None
        ),
        observed_at=(
            _as_str(capture.get("observedAt")) if capture is not None else None
        ),
    )


def read_source_member(
    session: Session,
    *,
    case_id: str,
    evidence_id: str,
    capture_id: str | None = None,
) -> SourceMember | None:
    """Read one owned evidence/capture member for a comparison side.

    This is the same identity/fingerprint policy used by the source summary, so
    comparison warnings cannot drift from case/claim dependency groups.
    """
    evidence = session.get(EvidenceItem, evidence_id)
    if evidence is None or _as_str(evidence.case_id) != case_id:
        return None
    selected_capture_id = (
        capture_id
        if capture_id is not None
        else _as_str(evidence.current_capture_id)
    )
    return _member_for(session, evidence, selected_capture_id)


def _case_members(session: Session, case_id: str) -> list[SourceMember]:
    evidence_rows = list(
        session.scalars(
            select(EvidenceItem)
            .where(EvidenceItem.case_id == case_id)
            .order_by(EvidenceItem.id.asc())
        ).all()
    )
    return [
        _member_for(
            session,
            evidence,
            _as_str(evidence.current_capture_id),
        )
        for evidence in evidence_rows
    ]


def _claim_members(
    session: Session, claim: Claim, case_id: str
) -> list[SourceMember]:
    links = list(
        session.scalars(
            select(ClaimEvidenceLink)
            .where(ClaimEvidenceLink.claim_id == claim.id)
            .order_by(
                ClaimEvidenceLink.created_at.asc(), ClaimEvidenceLink.id.asc()
            )
        ).all()
    )
    # One member per evidence record; prefer the first link that names a capture.
    requested_captures: dict[str, str | None] = {}
    for link in links:
        evidence_id = _as_str(link.evidence_id)
        if not evidence_id:
            continue
        link_capture_id = _as_str(link.capture_id)
        if evidence_id not in requested_captures:
            requested_captures[evidence_id] = link_capture_id
        elif requested_captures[evidence_id] is None and link_capture_id:
            requested_captures[evidence_id] = link_capture_id

    if not requested_captures:
        return []
    evidence_rows = list(
        session.scalars(
            select(EvidenceItem)
            .where(
                EvidenceItem.case_id == case_id,
                EvidenceItem.id.in_(sorted(requested_captures)),
            )
            .order_by(EvidenceItem.id.asc())
        ).all()
    )
    return [
        _member_for(session, evidence, requested_captures[_as_str(evidence.id) or ""])
        for evidence in evidence_rows
    ]


def read_source_summary(
    session: Session, *, case_id: str, claim_id: str | None = None
) -> dict[str, Any] | None:
    """Read case-level or claim-scoped source groups for one owned case.

    ``None`` means the case or claim is unknown/not owned by ``case_id`` and maps
    to HTTP 404. A valid empty scope returns a summary with zero groups, zero
    publisher counts and ``independence_status="unknown"``.
    """
    case = session.get(TopicCase, case_id)
    if case is None:
        return None

    if claim_id is not None:
        claim = session.get(Claim, claim_id)
        if claim is None or not _claim_belongs_to_case(session, claim, case_id):
            return None
        members = _claim_members(session, claim, case_id)
        return build_source_summary(
            case_id=case_id,
            scope="claim",
            claim_id=_as_str(claim.id),
            claim_signature=_as_str(claim.claim_signature),
            members=members,
        )

    return build_source_summary(
        case_id=case_id,
        scope="case",
        claim_id=None,
        claim_signature=None,
        members=_case_members(session, case_id),
    )


__all__ = [
    "LIMITATIONS",
    "MIN_COPY_NON_WHITESPACE_CODE_POINTS",
    "POLICY_VERSION",
    "PublisherIdentity",
    "SourceMember",
    "TEXT_FINGERPRINT_VERSION",
    "build_source_summary",
    "copy_fingerprint",
    "normalize_source_url",
    "read_source_member",
    "read_source_summary",
    "resolve_publisher_identity",
    "source_member_from_observation",
]
