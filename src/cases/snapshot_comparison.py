"""Ad-hoc comparison of two immutable case snapshots (F17 / X01).

This module is a focused, read-only reader. It compares the frozen semantic
projection of two stored snapshots that belong to one case and returns a
paginated ``ad_hoc`` delta DTO. It is deliberately **not** the recorded-delta
writer: ``src.cases.history.build_snapshot_delta`` (publication semantics)
stamps ``observedByRunId``, needs authoritative event ids to report removals and
is written into a snapshot row during finalization. Calling it here would
manufacture run attribution and publication state for an operator question that
was never recorded, so this reader owns its own presence/field comparison.

Semantics that must stay honest:

* an entity present in the baseline observation and absent from the target one is
  reported as ``entity_absent`` -- absence from a later observation, never a
  deletion, retraction or "claim no longer extracted" verdict;
* ``before``/``after`` are frozen semantic-field objects from the stored
  projection, never live ORM rows and never capture bodies;
* ``refs.baseline``/``refs.target`` carry their own snapshot id plus only the
  claim/evidence/capture/citation ids recorded on that side of that observation;
  no inspector link is invented for an event that never carried a claim;
* ordering is deterministic: ``entityType``, then ``entityId``, then
  ``changeKind``; ``total`` counts entities, not changed fields.

Version handling order (see ``unavailableReason``): an unreadable recorded version
value is ``unknown_version``; a pair that records *different* schema/identity/
policy versions is ``incompatible_*``; a pair that agrees on a version this build
does not support is ``unknown_version``; an unreadable payload is
``payload_unreadable``. A supported pair is only compared after **both** frozen
payloads match the full writer shape and their stored semantic hash, so a missing
group can never masquerade as an empty observation. Availability is decided
**before** any delta is produced, so an unsupported pair never looks like an
empty (zero-change) result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.cases.history import (
    SNAPSHOT_IDENTITY_VERSION,
    SNAPSHOT_POLICY_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    get_case_snapshot,
    semantic_hash_for_view,
    semantic_view,
    snapshot_entities,
    snapshot_payload,
)
from src.storage import CaseSnapshot, InvestigationRun

MODE_AD_HOC = "ad_hoc"
SNAPSHOT_COMPARISON_POLICY_VERSION = "snapshot-comparison-policy-v1"

DEFAULT_COMPARISON_LIMIT = 25
MAX_COMPARISON_LIMIT = 100
MAX_SNAPSHOT_COMPARISON_OFFSET = 2**31 - 1

AVAILABILITY_READY = "ready"
AVAILABILITY_UNAVAILABLE = "unavailable"

REASON_INCOMPATIBLE_SCHEMA = "incompatible_schema"
REASON_INCOMPATIBLE_IDENTITY = "incompatible_identity"
REASON_INCOMPATIBLE_POLICY = "incompatible_policy"
REASON_UNKNOWN_VERSION = "unknown_version"
REASON_PAYLOAD_UNREADABLE = "payload_unreadable"

CHANGE_ENTITY_ADDED = "entity_added"
CHANGE_ENTITY_ABSENT = "entity_absent"
CHANGE_FIELD_CHANGED = "field_changed"

#: Entity groups of the existing semantic projection, in contract order.
CASE_ENTITY_TYPE = "case"
ENTITY_TYPES: tuple[str, ...] = (
    CASE_ENTITY_TYPE,
    "articles",
    "events",
    "claims",
    "links",
    "citations",
    "evidence",
    "captures",
    "reviews",
    "exceptions",
    "parties",
    "partyInvestigations",
    "narratives",
)

#: The reference ids a frozen observation may carry. Nothing else is invented.
REFERENCE_FIELDS: tuple[str, ...] = (
    "claimId",
    "evidenceId",
    "captureId",
    "citationId",
)

#: Case facts consumed by the semantic projection (values may be ``None``).
REQUIRED_CASE_FIELDS: tuple[str, ...] = ("query", "reviewNotes")

#: Every entity array the canonical ``case-snapshot-v1`` writer emits.
REQUIRED_ENTITY_GROUPS: tuple[str, ...] = tuple(
    name for name in ENTITY_TYPES if name != CASE_ENTITY_TYPE
)

_SUPPORTED_VERSIONS = (
    SNAPSHOT_SCHEMA_VERSION,
    SNAPSHOT_IDENTITY_VERSION,
    SNAPSHOT_POLICY_VERSION,
)


class SnapshotComparisonNotFound(LookupError):
    """A snapshot (or its owning run) is unknown or belongs to another case."""


class SnapshotComparisonInvalid(ValueError):
    """The comparison request is malformed even for existing snapshots (422)."""


@dataclass(frozen=True)
class _RawSnapshot:
    """Metadata of a stored snapshot whose frozen payload will not decode.

    ``payload_json`` and ``semantic_hash`` are deliberately ``None`` so the
    payload check reports ``payload_unreadable`` instead of a decoded empty
    observation. Only the scalar metadata needed for the 200 response is read.
    """

    id: str
    investigation_run_id: str
    schema_version: str
    identity_version: str
    policy_version: str
    created_at: Any
    payload_json: None = None
    semantic_hash: None = None


_Snapshot = CaseSnapshot | _RawSnapshot

_RAW_SNAPSHOT_SQL = text(
    "SELECT id, investigation_run_id, schema_version, identity_version, "
    "policy_version, created_at FROM case_snapshots "
    "WHERE id = :snapshot_id AND case_id = :case_id"
)


def _load_snapshot(
    session: Session, *, case_id: str, snapshot_id: str
) -> _Snapshot | None:
    """Load one snapshot, keeping an undecodable payload distinct from a miss."""
    try:
        return get_case_snapshot(session, case_id=case_id, snapshot_id=snapshot_id)
    except json.JSONDecodeError:
        # A JSON column holding non-JSON text fails while the row loads; its
        # scalar metadata can still be read, so it is an unreadable payload,
        # not a missing snapshot or a runtime failure.
        row = session.execute(
            _RAW_SNAPSHOT_SQL,
            {"snapshot_id": snapshot_id, "case_id": case_id},
        ).mappings().first()
        if row is None:
            return None
        return _RawSnapshot(payload_json=None, **row)


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _iso(value: Any) -> str | None:
    if isinstance(value, str):
        return value or None
    rendered = getattr(value, "isoformat", None)
    if not callable(rendered):
        return None
    result = rendered()
    return result if isinstance(result, str) else None


def _coverage(run: InvestigationRun) -> str:
    return str(getattr(run.coverage, "value", run.coverage))


def _metadata(snapshot: _Snapshot, run: InvestigationRun) -> dict[str, Any]:
    return {
        "sequence": run.sequence,
        "createdAt": _iso(snapshot.created_at),
        "schemaVersion": str(snapshot.schema_version),
        "identityVersion": str(snapshot.identity_version),
        "policyVersion": str(snapshot.policy_version),
    }


def _unavailability_reason(
    baseline: _Snapshot, target: _Snapshot
) -> str | None:
    """Return the version-level reason this pair is not comparable, if any."""
    recorded = (
        (baseline.schema_version, baseline.identity_version, baseline.policy_version),
        (target.schema_version, target.identity_version, target.policy_version),
    )
    for trio in recorded:
        if not all(isinstance(value, str) and value.strip() for value in trio):
            return REASON_UNKNOWN_VERSION
    if recorded[0][0] != recorded[1][0]:
        return REASON_INCOMPATIBLE_SCHEMA
    if recorded[0][1] != recorded[1][1]:
        return REASON_INCOMPATIBLE_IDENTITY
    if recorded[0][2] != recorded[1][2]:
        return REASON_INCOMPATIBLE_POLICY
    if recorded[0] != _SUPPORTED_VERSIONS:
        return REASON_UNKNOWN_VERSION
    return None


def _payload_semantic(
    snapshot: _Snapshot, *, case_id: str
) -> dict[str, Any] | None:
    """Return the semantic projection of an intact frozen payload, else ``None``.

    A missing, null or wrong-typed entity array must never be read as an empty
    observation: that turned a ``{}`` payload into seven synthetic removals. The
    payload must also agree with the stored semantic hash, so truncated groups or
    edited contents are rejected even when the outer shape still looks valid. This
    is a consistency check on a frozen observation, not authentication.
    """
    payload = snapshot.payload_json
    if not isinstance(payload, dict):
        return None
    if payload.get("caseId") != case_id:
        return None
    for name, expected in (
        ("schemaVersion", snapshot.schema_version),
        ("identityVersion", snapshot.identity_version),
        ("policyVersion", snapshot.policy_version),
    ):
        if payload.get(name) != expected:
            return None
    if any(name not in payload for name in REQUIRED_CASE_FIELDS):
        return None
    for name in REQUIRED_ENTITY_GROUPS:
        rows = payload.get(name)
        if not isinstance(rows, list):
            return None
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                return None
            entity_id = row.get("id")
            if not isinstance(entity_id, str) or not entity_id.strip():
                return None
            if entity_id in seen:
                return None
            seen.add(entity_id)
    semantic = semantic_view(payload)
    if semantic_hash_for_view(semantic) != snapshot.semantic_hash:
        return None
    return semantic


def _semantic_index(
    semantic: dict[str, Any], name: str
) -> dict[str, dict[str, Any]]:
    rows = semantic.get(name)
    if not isinstance(rows, list):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        entity_id = _as_str(row.get("id"))
        if entity_id is not None and entity_id not in index:
            index[entity_id] = row
    return index


def _reference(
    *,
    snapshot_id: str,
    entity_type: str,
    entity_id: str,
    recorded: dict[str, Any] | None,
) -> dict[str, Any]:
    """Frozen references for one side; only ids that side actually recorded."""
    reference: dict[str, Any] = {"snapshotId": snapshot_id}
    if recorded is None:
        return reference
    if entity_type == "claims":
        reference["claimId"] = _as_str(recorded.get("id")) or entity_id
    elif entity_type == "evidence":
        reference["evidenceId"] = _as_str(recorded.get("id")) or entity_id
        capture_id = _as_str(recorded.get("currentCaptureId"))
        if capture_id is not None:
            reference["captureId"] = capture_id
    elif entity_type == "captures":
        reference["captureId"] = _as_str(recorded.get("id")) or entity_id
    elif entity_type == "citations":
        reference["citationId"] = _as_str(recorded.get("id")) or entity_id
        capture_id = _as_str(recorded.get("captureId"))
        if capture_id is not None:
            reference["captureId"] = capture_id
        claim_id = _as_str(recorded.get("originalClaimId"))
        if claim_id is not None:
            reference["claimId"] = claim_id
    elif entity_type == "links":
        for field in REFERENCE_FIELDS:
            value = _as_str(recorded.get(field))
            if value is not None:
                reference[field] = value
    # Events and every non-reference entity carry no claim/evidence/capture/
    # citation id of their own; inventing one would fabricate an inspector link.
    return reference


def _field_changes(
    before: dict[str, Any], after: dict[str, Any]
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    fields = sorted(
        field
        for field in set(before) | set(after)
        if before.get(field) != after.get(field)
    )
    return (
        fields,
        {field: before.get(field) for field in fields},
        {field: after.get(field) for field in fields},
    )


def _item(
    *,
    entity_type: str,
    entity_id: str,
    change_kind: str,
    changed_fields: list[str],
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    baseline_snapshot_id: str,
    target_snapshot_id: str,
    baseline_recorded: dict[str, Any] | None,
    target_recorded: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "entityType": entity_type,
        "entityId": entity_id,
        "changeKind": change_kind,
        "changedFields": changed_fields,
        "before": before,
        "after": after,
        "refs": {
            "baseline": _reference(
                snapshot_id=baseline_snapshot_id,
                entity_type=entity_type,
                entity_id=entity_id,
                recorded=baseline_recorded,
            ),
            "target": _reference(
                snapshot_id=target_snapshot_id,
                entity_type=entity_type,
                entity_id=entity_id,
                recorded=target_recorded,
            ),
        },
    }


def _comparison_items(
    *,
    case_id: str,
    baseline: CaseSnapshot,
    target: CaseSnapshot,
    baseline_semantic: dict[str, Any],
    target_semantic: dict[str, Any],
) -> list[dict[str, Any]]:
    baseline_payload = snapshot_payload(baseline)
    target_payload = snapshot_payload(target)
    items: list[dict[str, Any]] = []

    baseline_case = baseline_semantic.get(CASE_ENTITY_TYPE)
    target_case = target_semantic.get(CASE_ENTITY_TYPE)
    if isinstance(baseline_case, dict) and isinstance(target_case, dict):
        fields, before, after = _field_changes(baseline_case, target_case)
        if fields:
            items.append(
                _item(
                    entity_type=CASE_ENTITY_TYPE,
                    entity_id=case_id,
                    change_kind=CHANGE_FIELD_CHANGED,
                    changed_fields=fields,
                    before=before,
                    after=after,
                    baseline_snapshot_id=baseline.id,
                    target_snapshot_id=target.id,
                    baseline_recorded=None,
                    target_recorded=None,
                )
            )

    for entity_type in ENTITY_TYPES:
        if entity_type == CASE_ENTITY_TYPE:
            continue
        before_index = _semantic_index(baseline_semantic, entity_type)
        after_index = _semantic_index(target_semantic, entity_type)
        before_recorded = snapshot_entities(baseline_payload, entity_type)
        after_recorded = snapshot_entities(target_payload, entity_type)
        for entity_id in sorted(set(before_index) | set(after_index)):
            before_row = before_index.get(entity_id)
            after_row = after_index.get(entity_id)
            if before_row is None:
                items.append(
                    _item(
                        entity_type=entity_type,
                        entity_id=entity_id,
                        change_kind=CHANGE_ENTITY_ADDED,
                        changed_fields=[],
                        before=None,
                        after=after_row,
                        baseline_snapshot_id=baseline.id,
                        target_snapshot_id=target.id,
                        baseline_recorded=None,
                        target_recorded=after_recorded.get(entity_id),
                    )
                )
                continue
            if after_row is None:
                items.append(
                    _item(
                        entity_type=entity_type,
                        entity_id=entity_id,
                        change_kind=CHANGE_ENTITY_ABSENT,
                        changed_fields=[],
                        before=before_row,
                        after=None,
                        baseline_snapshot_id=baseline.id,
                        target_snapshot_id=target.id,
                        baseline_recorded=before_recorded.get(entity_id),
                        target_recorded=None,
                    )
                )
                continue
            fields, before_fields, after_fields = _field_changes(
                before_row, after_row
            )
            if not fields:
                continue
            items.append(
                _item(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    change_kind=CHANGE_FIELD_CHANGED,
                    changed_fields=fields,
                    before=before_fields,
                    after=after_fields,
                    baseline_snapshot_id=baseline.id,
                    target_snapshot_id=target.id,
                    baseline_recorded=before_recorded.get(entity_id),
                    target_recorded=after_recorded.get(entity_id),
                )
            )

    items.sort(
        key=lambda item: (
            item["entityType"],
            item["entityId"],
            item["changeKind"],
        )
    )
    return items


def read_snapshot_comparison(
    session: Session,
    *,
    case_id: str,
    baseline_snapshot_id: str,
    target_snapshot_id: str,
    limit: int = DEFAULT_COMPARISON_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """Compare two stored snapshots of one case (read-only, zero writes).

    Raises ``SnapshotComparisonNotFound`` for an unknown/cross-case snapshot (or
    an owning run that cannot be attributed to the case) and
    ``SnapshotComparisonInvalid`` for a malformed or non-chronological request.
    """
    baseline_id = (baseline_snapshot_id or "").strip()
    target_id = (target_snapshot_id or "").strip()
    if not baseline_id or not target_id:
        raise SnapshotComparisonInvalid(
            "baseline and target snapshot ids are required"
        )
    if baseline_id == target_id:
        raise SnapshotComparisonInvalid(
            "baseline and target must be two distinct snapshots; baseline must "
            "precede target chronologically"
        )
    if not isinstance(limit, int) or isinstance(limit, bool) or not (
        1 <= limit <= MAX_COMPARISON_LIMIT
    ):
        raise SnapshotComparisonInvalid(
            f"limit must be between 1 and {MAX_COMPARISON_LIMIT}"
        )
    if not isinstance(offset, int) or isinstance(offset, bool) or not (
        0 <= offset <= MAX_SNAPSHOT_COMPARISON_OFFSET
    ):
        raise SnapshotComparisonInvalid(
            f"offset must be between 0 and {MAX_SNAPSHOT_COMPARISON_OFFSET}"
        )

    baseline = _load_snapshot(
        session, case_id=case_id, snapshot_id=baseline_id
    )
    target = _load_snapshot(session, case_id=case_id, snapshot_id=target_id)
    if baseline is None or target is None:
        raise SnapshotComparisonNotFound(
            "snapshot comparison is not available for this case"
        )

    baseline_run = session.get(InvestigationRun, baseline.investigation_run_id)
    target_run = session.get(InvestigationRun, target.investigation_run_id)
    if (
        baseline_run is None
        or target_run is None
        or baseline_run.case_id != case_id
        or target_run.case_id != case_id
    ):
        # Ownership of a stored observation cannot be proven from the owning run.
        raise SnapshotComparisonNotFound(
            "snapshot comparison is not available for this case"
        )
    if baseline_run.sequence >= target_run.sequence:
        raise SnapshotComparisonInvalid(
            "baseline must precede target chronologically by owning run sequence"
        )

    payload: dict[str, Any] = {
        "mode": MODE_AD_HOC,
        "comparisonPolicyVersion": SNAPSHOT_COMPARISON_POLICY_VERSION,
        "baselineSnapshotId": baseline.id,
        "targetSnapshotId": target.id,
        "baselineRunId": baseline_run.id,
        "targetRunId": target_run.id,
        "baselineCoverage": _coverage(baseline_run),
        "targetCoverage": _coverage(target_run),
        "baselineMetadata": _metadata(baseline, baseline_run),
        "targetMetadata": _metadata(target, target_run),
        "availability": AVAILABILITY_READY,
        "unavailableReason": None,
        "items": [],
        "total": 0,
        "limit": limit,
        "offset": offset,
        "hasMore": False,
    }

    # Availability is decided before any delta exists: an unsupported or
    # incompatible pair must never look like a ready zero-change result.
    reason = _unavailability_reason(baseline, target)
    baseline_semantic: dict[str, Any] | None = None
    target_semantic: dict[str, Any] | None = None
    if reason is None:
        # Both frozen payloads are validated before any item is constructed; a
        # malformed observation is never indexed as an empty one.
        baseline_semantic = _payload_semantic(baseline, case_id=case_id)
        target_semantic = _payload_semantic(target, case_id=case_id)
        if baseline_semantic is None or target_semantic is None:
            reason = REASON_PAYLOAD_UNREADABLE
    if reason is not None or baseline_semantic is None or target_semantic is None:
        payload["availability"] = AVAILABILITY_UNAVAILABLE
        payload["unavailableReason"] = reason or REASON_PAYLOAD_UNREADABLE
        payload["total"] = None
        return payload

    items = _comparison_items(
        case_id=case_id,
        # A validated payload proves the row decoded, so it is a real snapshot.
        baseline=cast(CaseSnapshot, baseline),
        target=cast(CaseSnapshot, target),
        baseline_semantic=baseline_semantic,
        target_semantic=target_semantic,
    )
    total = len(items)
    page = items[offset : offset + limit]
    payload["items"] = page
    payload["total"] = total
    payload["hasMore"] = offset + len(page) < total
    return payload


__all__ = [
    "MODE_AD_HOC",
    "SNAPSHOT_COMPARISON_POLICY_VERSION",
    "DEFAULT_COMPARISON_LIMIT",
    "MAX_COMPARISON_LIMIT",
    "MAX_SNAPSHOT_COMPARISON_OFFSET",
    "AVAILABILITY_READY",
    "AVAILABILITY_UNAVAILABLE",
    "REASON_INCOMPATIBLE_SCHEMA",
    "REASON_INCOMPATIBLE_IDENTITY",
    "REASON_INCOMPATIBLE_POLICY",
    "REASON_UNKNOWN_VERSION",
    "REASON_PAYLOAD_UNREADABLE",
    "CHANGE_ENTITY_ADDED",
    "CHANGE_ENTITY_ABSENT",
    "CHANGE_FIELD_CHANGED",
    "CASE_ENTITY_TYPE",
    "ENTITY_TYPES",
    "REFERENCE_FIELDS",
    "SnapshotComparisonNotFound",
    "SnapshotComparisonInvalid",
    "read_snapshot_comparison",
]
