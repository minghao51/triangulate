"""R03b: snapshot-aware claim, evidence and comparison readers.

Every fixture is synthetic. A snapshot is composed from committed rows, then the
live rows are rewritten/removed/advanced to prove that a historical read never
falls back to current state. No model or network call is made.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from src.cases.comparison import ComparisonNotFound, read_comparison
from src.cases.history import (
    SNAPSHOT_IDENTITY_VERSION,
    SNAPSHOT_POLICY_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    compose_case_snapshot,
)
from src.cases.readers import (
    SnapshotNotFound,
    read_claim_detail,
    read_evidence_detail,
)
from src.cases.service import _claim_signature
from src.http.app import app
from src.storage import (
    CaseSnapshot,
    CaseStatus,
    Claim,
    ClaimEvidenceLink,
    Event,
    EvidenceCapture,
    EvidenceItem,
    FactAllegationType,
    InvestigationCoverage,
    InvestigationRun,
    InvestigationRunStatus,
    InvestigationRunTrigger,
    TopicCase,
    VerificationStatus,
    get_database,
    init_database,
)
from src.storage.captures import record_evidence_capture

CASE_ID = "case-r03b"
OTHER_CASE_ID = "case-r03b-other"
EVENT_ID = "event-r03b"
OTHER_EVENT_ID = "event-r03b-other"
SNAPSHOT_ID = "snap-r03b"
OTHER_SNAPSHOT_ID = "snap-r03b-other"
RUN_ID = "run-r03b"
OTHER_RUN_ID = "run-r03b-other"

STABLE_TEXT = "The council approved the harbour plan."
STABLE_QUOTE = "The council approved the harbour plan."
CONTESTED_TEXT = "The council postponed the harbour plan."
CONTESTED_QUOTE_LEFT = "The council postponed the harbour plan."
CONTESTED_QUOTE_RIGHT = "The council denied any postponement."
REMOVED_TEXT = "An assertion that will be withdrawn."
REMOVED_QUOTE = "An assertion that will be withdrawn."

FROZEN_CONTESTED_TEXT = "The council rejected the harbour plan."
REWRITTEN_CONTESTED_TEXT = "The council rejected the harbour plan outright."

SHARED_BODY = (
    f"{STABLE_QUOTE} {CONTESTED_QUOTE_LEFT} {CONTESTED_QUOTE_RIGHT} "
    f"{REMOVED_QUOTE} Port Alden reporting continued through the morning "
    "with officials answering questions about shelters, transit and the "
    "harbour. Port Alden reporting continued through the morning with "
    "officials answering questions about shelters, transit and the harbour."
)
STABLE_BODY = (
    f"{STABLE_QUOTE} A second unconnected report about the same harbour plan "
    "and its budget, reviewed line by line by the desk, with the figures "
    "checked twice and read back to the editor before publication."
)
OLD_BODY = (
    f"{CONTESTED_QUOTE_LEFT} Old capture context for the revised source. "
    "Port Alden reporting continued through the morning with officials "
    "answering questions about shelters, transit and the harbour."
)
REVISED_BODY = (
    "A claim that only exists after the observation. Revised capture context "
    "for the same source. Port Alden reporting continued through the morning "
    "with officials answering questions about shelters, transit and the harbour."
)


def db_session():
    return get_database().get_session_sync()


def _span(body: str, quote: str) -> tuple[int, int]:
    start = body.index(quote)
    return start, start + len(quote)


def _add_case(session, case_id: str, query: str) -> None:
    session.add(
        TopicCase(
            id=case_id,
            query=query,
            slug=f"{case_id}-slug",
            conflict="Civic response",
            status=CaseStatus.REVIEW_READY,
            metadata_json={},
        )
    )


def _add_event(session, event_id: str, case_id: str) -> None:
    session.add(
        Event(
            id=event_id,
            timestamp=datetime(2026, 3, 3, 6, 30, tzinfo=UTC),
            title=f"Event {event_id}",
            verification_status=VerificationStatus.ALLEGED,
            case_id=case_id,
        )
    )


def _add_claim(session, claim_id: str, event_id: str, text: str) -> Claim:
    claim = Claim(
        id=claim_id,
        event_id=event_id,
        claim_text=text,
        verification_status=VerificationStatus.ALLEGED,
        fact_allegation_type=FactAllegationType.ALLEGATION,
        claim_signature=_claim_signature(text),
        party_positions={"Alpha": "disputes"},
        support_count=1,
        oppose_count=2,
        source_diversity_count=3,
    )
    session.add(claim)
    return claim


def _add_evidence(
    session,
    *,
    evidence_id: str,
    case_id: str,
    event_id: str,
    publisher: str,
    body: str,
    title: str | None = None,
    capture_metadata: dict | None = None,
    extraction: dict | None = None,
) -> tuple[EvidenceItem, EvidenceCapture]:
    evidence = EvidenceItem(
        id=evidence_id,
        case_id=case_id,
        event_id=event_id,
        evidence_type="article",
        source_type="rss",
        title=title or f"Source {evidence_id}",
        origin_url=f"https://{evidence_id}.example.com/story",
        canonical_url=f"https://{evidence_id}.example.com/story",
        publisher=publisher,
        capture_metadata=capture_metadata or {},
        verification_status="UNVERIFIED",
        credibility_tier="unknown",
        requires_human_review=0,
    )
    session.add(evidence)
    session.flush()
    capture = record_evidence_capture(
        session,
        evidence,
        text=body,
        observed_at=datetime(2026, 3, 3, 6, 25, tzinfo=UTC),
        metadata={"extraction": extraction} if extraction else {},
    )
    assert capture is not None
    return evidence, capture


def _link(
    session,
    *,
    link_id: str,
    claim: Claim,
    evidence: EvidenceItem,
    capture: EvidenceCapture,
    body: str,
    quote: str,
    relation: str = "reported_by",
    assessment_origin: str = "collector",
) -> ClaimEvidenceLink:
    start, end = _span(body, quote)
    link = ClaimEvidenceLink(
        id=link_id,
        claim_id=claim.id,
        evidence_id=evidence.id,
        relation=relation,
        source_diversity_rank=1,
        confidence_score=None,
        capture_id=capture.id,
        alignment_status="exact",
        quote=quote,
        start_char=start,
        end_char=end,
        assessment_origin=assessment_origin,
        assessment_version="v1",
        assessment_metadata={"diagnostic_reason": "quote_matched"},
    )
    session.add(link)
    session.flush()
    return link


def _write_snapshot(
    session,
    *,
    case_id: str,
    snapshot_id: str,
    run_id: str,
    sequence: int = 1,
) -> None:
    session.add(
        InvestigationRun(
            id=run_id,
            case_id=case_id,
            sequence=sequence,
            trigger=InvestigationRunTrigger.INITIAL,
            parameter_snapshot={},
            status=InvestigationRunStatus.SUCCEEDED,
            coverage=InvestigationCoverage.COMPLETE_REQUESTED_SCOPE,
            coverage_details={},
        )
    )
    session.flush()
    composed = compose_case_snapshot(session, case_id=case_id)
    payload = json.loads(json.dumps(composed["payload"], default=str))
    session.add(
        CaseSnapshot(
            id=snapshot_id,
            case_id=case_id,
            investigation_run_id=run_id,
            baseline_snapshot_id=None,
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            identity_version=SNAPSHOT_IDENTITY_VERSION,
            policy_version=SNAPSHOT_POLICY_VERSION,
            semantic_hash=composed["semanticHash"],
            payload_json=payload,
            delta_json={"availability": "initial", "changes": []},
        )
    )
    session.flush()


def _derived_snapshot(
    session,
    *,
    snapshot_id: str,
    run_id: str,
    sequence: int,
    mutate,
) -> None:
    """Publish a snapshot derived from SNAPSHOT_ID with a mutated payload."""
    source = session.get(CaseSnapshot, SNAPSHOT_ID)
    assert source is not None
    payload = json.loads(json.dumps(source.payload_json))
    mutate(payload)
    session.add(
        InvestigationRun(
            id=run_id,
            case_id=CASE_ID,
            sequence=sequence,
            trigger=InvestigationRunTrigger.RERUN,
            parameter_snapshot={},
            status=InvestigationRunStatus.SUCCEEDED,
            coverage=InvestigationCoverage.COMPLETE_REQUESTED_SCOPE,
            coverage_details={},
        )
    )
    session.flush()
    session.add(
        CaseSnapshot(
            id=snapshot_id,
            case_id=CASE_ID,
            investigation_run_id=run_id,
            baseline_snapshot_id=SNAPSHOT_ID,
            schema_version=source.schema_version,
            identity_version=source.identity_version,
            policy_version=source.policy_version,
            semantic_hash=source.semantic_hash,
            payload_json=payload,
            delta_json={"availability": "ready", "changes": []},
        )
    )
    session.flush()


def seed(tmp_path):
    """Seed the case, publish a snapshot, then mutate the live rows."""
    init_database(str(tmp_path / "r03b.sqlite3"))
    session = db_session()
    ids: dict[str, str] = {}
    try:
        _add_case(session, CASE_ID, "Port Alden harbour plan")
        _add_case(session, OTHER_CASE_ID, "Other case")
        _add_event(session, EVENT_ID, CASE_ID)
        _add_event(session, OTHER_EVENT_ID, OTHER_CASE_ID)
        session.flush()

        stable = _add_claim(session, "claim-r03b-stable", EVENT_ID, STABLE_TEXT)
        contested = _add_claim(
            session, "claim-r03b-contested", EVENT_ID, FROZEN_CONTESTED_TEXT
        )
        removed = _add_claim(session, "claim-r03b-removed", EVENT_ID, REMOVED_TEXT)
        foreign = _add_claim(
            session, "claim-r03b-foreign", OTHER_EVENT_ID, "Another case assertion."
        )
        session.flush()

        stable_evidence, stable_capture = _add_evidence(
            session,
            evidence_id="ev-r03b-stable",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Meridian Wire",
            body=STABLE_BODY,
            capture_metadata={"lineage": {"origin": "rss"}},
        )
        left_evidence, left_capture = _add_evidence(
            session,
            evidence_id="ev-r03b-left",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Meridian Wire",
            body=SHARED_BODY,
            extraction={
                "status": "valid",
                "scope_start": 0,
                "scope_end": 200,
                "body_char_count": len(SHARED_BODY),
                "input_limit": 20000,
                "source_available": True,
            },
        )
        right_evidence, right_capture = _add_evidence(
            session,
            evidence_id="ev-r03b-right",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Northern Post",
            body=SHARED_BODY,
        )
        old_evidence, old_capture = _add_evidence(
            session,
            evidence_id="ev-r03b-old",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Old Wire",
            body=OLD_BODY,
        )
        other_evidence, other_capture = _add_evidence(
            session,
            evidence_id="ev-r03b-other",
            case_id=OTHER_CASE_ID,
            event_id=OTHER_EVENT_ID,
            publisher="Other Wire",
            body=f"Other case body. {STABLE_BODY}",
        )
        # A second, untouched pair: live and snapshot reads must agree exactly.
        pair_evidence, pair_capture = _add_evidence(
            session,
            evidence_id="ev-r03b-pair",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Meridian Wire",
            body=STABLE_BODY,
        )
        stable_right_evidence, stable_right_capture = _add_evidence(
            session,
            evidence_id="ev-r03b-stable-right",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Northern Post",
            body=STABLE_BODY,
        )
        nolink_evidence, _nolink_capture = _add_evidence(
            session,
            evidence_id="ev-r03b-nolink",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Quiet Desk",
            body=f"No links recorded here. {STABLE_BODY}",
        )

        _link(
            session,
            link_id="link-stable",
            claim=stable,
            evidence=stable_evidence,
            capture=stable_capture,
            body=STABLE_BODY,
            quote=STABLE_QUOTE,
        )
        _link(
            session,
            link_id="link-stable-right",
            claim=stable,
            evidence=stable_right_evidence,
            capture=stable_right_capture,
            body=STABLE_BODY,
            quote=STABLE_QUOTE,
        )
        _link(
            session,
            link_id="link-contested-left",
            claim=contested,
            evidence=left_evidence,
            capture=left_capture,
            body=SHARED_BODY,
            quote=CONTESTED_QUOTE_LEFT,
            relation="contradicts",
            assessment_origin="human",
        )
        _link(
            session,
            link_id="link-contested-right",
            claim=contested,
            evidence=right_evidence,
            capture=right_capture,
            body=SHARED_BODY,
            quote=CONTESTED_QUOTE_RIGHT,
            relation="reported_by",
        )
        _link(
            session,
            link_id="link-removed",
            claim=removed,
            evidence=left_evidence,
            capture=left_capture,
            body=SHARED_BODY,
            quote=REMOVED_QUOTE,
        )
        _link(
            session,
            link_id="link-old",
            claim=contested,
            evidence=old_evidence,
            capture=old_capture,
            body=OLD_BODY,
            quote=CONTESTED_QUOTE_LEFT,
        )
        # Another case's link must never be attributed to this case's comparison.
        _link(
            session,
            link_id="link-foreign",
            claim=foreign,
            evidence=other_evidence,
            capture=other_capture,
            body=f"Other case body. {STABLE_BODY}",
            quote=STABLE_QUOTE,
        )
        session.flush()

        ids.update(
            {
                "stable_claim": stable.id,
                "contested_claim": contested.id,
                "removed_claim": removed.id,
                "stable_evidence": stable_evidence.id,
                "left_evidence": left_evidence.id,
                "right_evidence": right_evidence.id,
                "old_evidence": old_evidence.id,
                "pair_evidence": pair_evidence.id,
                "stable_right_evidence": stable_right_evidence.id,
                "nolink_evidence": nolink_evidence.id,
                "left_capture": left_capture.id,
                "right_capture": right_capture.id,
                "old_capture": old_capture.id,
                "pair_capture": pair_capture.id,
                "stable_right_capture": stable_right_capture.id,
            }
        )

        _write_snapshot(
            session, case_id=CASE_ID, snapshot_id=SNAPSHOT_ID, run_id=RUN_ID
        )
        _write_snapshot(
            session,
            case_id=OTHER_CASE_ID,
            snapshot_id=OTHER_SNAPSHOT_ID,
            run_id=OTHER_RUN_ID,
            sequence=1,
        )
        session.commit()

        # ---- mutate the live rows after the observation -------------------
        contested.claim_text = REWRITTEN_CONTESTED_TEXT
        contested.claim_signature = _claim_signature(REWRITTEN_CONTESTED_TEXT)
        contested.verification_status = VerificationStatus.CONFIRMED

        # The "removed" claim disappears from the live rows entirely.
        for link in session.execute(
            select(ClaimEvidenceLink).where(
                ClaimEvidenceLink.claim_id == removed.id
            )
        ).scalars():
            session.delete(link)
        session.flush()
        session.delete(removed)
        session.flush()

        # The old source advances to a new capture and gains a new claim/link.
        revised_capture = record_evidence_capture(
            session,
            old_evidence,
            text=REVISED_BODY,
            observed_at=datetime(2026, 3, 4, 8, 15, tzinfo=UTC),
        )
        assert revised_capture is not None
        ids["revised_capture"] = revised_capture.id
        live_only = _add_claim(
            session, "claim-r03b-live-only", EVENT_ID, "A claim added after the run."
        )
        session.flush()
        _link(
            session,
            link_id="link-live-only",
            claim=live_only,
            evidence=old_evidence,
            capture=revised_capture,
            body=REVISED_BODY,
            quote="A claim that only exists after the observation.",
        )
        # A live-only link on a frozen capture must not appear in the snapshot.
        _link(
            session,
            link_id="link-late-left",
            claim=live_only,
            evidence=left_evidence,
            capture=left_capture,
            body=SHARED_BODY,
            quote=STABLE_QUOTE,
        )

        # Live source metadata also moves; the observation must stay frozen.
        right_evidence.title = "Source renamed after the run"
        right_evidence.publisher = "Northern Post (renamed)"
        right_evidence.verification_status = "VERIFIED"

        session.commit()
        ids["live_only_claim"] = live_only.id
        return ids, session
    finally:
        session.close()


@pytest.fixture
def workbench(tmp_path):
    ids, _session = seed(tmp_path)
    return ids


def _normalized(payload):
    """Drop the tz-suffix formatting difference between payload and live rows.

    Snapshot composition serializes the in-memory observation time while a live
    read serializes SQLite's normalized value; the stored instants are equal.
    """
    rendered = json.loads(json.dumps(payload))
    for side in ("left", "right"):
        for key in ("recorded_at", "observed_at"):
            value = rendered[side].get(key)
            if isinstance(value, str):
                rendered[side][key] = value.replace("+00:00", "")
    return rendered


def _row(payload, claim_text):
    for row in payload["claims"]["rows"]:
        if (row.get("claim_text") or row.get("claimText")) == claim_text:
            return row
    raise AssertionError(f"row {claim_text!r} not found")


# ---------------------------------------------------------------------------
# Claim reader
# ---------------------------------------------------------------------------


class TestSnapshotClaimReader:
    def test_frozen_claim_survives_a_live_rewrite(self, workbench):
        session = db_session()
        try:
            payload = read_claim_detail(
                session,
                case_id=CASE_ID,
                claim_id=workbench["contested_claim"],
                snapshot_id=SNAPSHOT_ID,
            )
            live = read_claim_detail(
                session, case_id=CASE_ID, claim_id=workbench["contested_claim"]
            )
        finally:
            session.close()

        assert payload is not None and live is not None
        assert payload["claim_text"] == FROZEN_CONTESTED_TEXT
        assert payload["claim_signature"] == _claim_signature(FROZEN_CONTESTED_TEXT)
        assert payload["verification_status"] == "ALLEGED"
        assert payload["snapshot_id"] == SNAPSHOT_ID
        # Frozen party positions and counts, not the live aggregates.
        assert payload["party_positions"] == {"Alpha": "disputes"}
        assert payload["counts"] == {
            "support_count": 1,
            "oppose_count": 2,
            "source_diversity_count": 3,
            "evidence_count": len(payload["passages"]),
        }
        assert payload["counts"]["evidence_count"] == 3

        # The live row moved on and the reader says so factually.
        assert payload["live_state"] == {
            "present": True,
            "claim_signature": _claim_signature(REWRITTEN_CONTESTED_TEXT),
            "text_matches_snapshot": False,
        }
        assert live["claim_text"] == REWRITTEN_CONTESTED_TEXT
        assert live["verification_status"] == "CONFIRMED"
        assert "snapshot_id" not in live
        assert "live_state" not in live

    def test_removed_live_claim_stays_viewable_with_frozen_passages(self, workbench):
        session = db_session()
        try:
            payload = read_claim_detail(
                session,
                case_id=CASE_ID,
                claim_id=workbench["removed_claim"],
                snapshot_id=SNAPSHOT_ID,
            )
            live = read_claim_detail(
                session, case_id=CASE_ID, claim_id=workbench["removed_claim"]
            )
        finally:
            session.close()

        assert live is None
        assert payload is not None
        assert payload["claim_text"] == REMOVED_TEXT
        assert payload["live_state"]["present"] is False
        assert payload["live_state"]["text_matches_snapshot"] is None
        assert len(payload["passages"]) == 1
        passage = payload["passages"][0]
        assert passage["quote"] == REMOVED_QUOTE
        assert passage["capture_id"] == workbench["left_capture"]
        assert passage["alignment_status"] == "exact"
        assert passage["effective_relation"] == "reported_by"

    def test_unknown_and_cross_case_snapshots_raise(self, workbench):
        session = db_session()
        try:
            with pytest.raises(SnapshotNotFound):
                read_claim_detail(
                    session,
                    case_id=CASE_ID,
                    claim_id=workbench["stable_claim"],
                    snapshot_id="snap-missing",
                )
            # The other case's snapshot is invisible from this case.
            with pytest.raises(SnapshotNotFound):
                read_claim_detail(
                    session,
                    case_id=CASE_ID,
                    claim_id=workbench["stable_claim"],
                    snapshot_id=OTHER_SNAPSHOT_ID,
                )
        finally:
            session.close()

    def test_entities_absent_from_the_snapshot_are_not_found(self, workbench):
        session = db_session()
        try:
            assert (
                read_claim_detail(
                    session,
                    case_id=CASE_ID,
                    claim_id=workbench["live_only_claim"],
                    snapshot_id=SNAPSHOT_ID,
                )
                is None
            )
            assert (
                read_claim_detail(
                    session,
                    case_id=CASE_ID,
                    claim_id="claim-r03b-missing",
                    snapshot_id=SNAPSHOT_ID,
                )
                is None
            )
            assert (
                read_evidence_detail(
                    session,
                    case_id=CASE_ID,
                    evidence_id="ev-r03b-missing",
                    snapshot_id=SNAPSHOT_ID,
                )
                is None
            )
        finally:
            session.close()

    def test_historical_claim_never_invents_attribution(self, workbench):
        session = db_session()
        try:
            payload = read_claim_detail(
                session,
                case_id=CASE_ID,
                claim_id=workbench["removed_claim"],
                snapshot_id=SNAPSHOT_ID,
            )
        finally:
            session.close()

        assert payload is not None
        assert payload["verification_provenance"] == "unknown"
        rendered = json.dumps(payload).lower()
        for invented in ("actor", "reviewer", "corroborat", "is_true", "confirmed_by"):
            assert invented not in rendered


# ---------------------------------------------------------------------------
# Evidence reader
# ---------------------------------------------------------------------------


class TestSnapshotEvidenceReader:
    def test_historical_metadata_and_capture_references(self, workbench):
        session = db_session()
        try:
            payload = read_evidence_detail(
                session,
                case_id=CASE_ID,
                evidence_id=workbench["old_evidence"],
                snapshot_id=SNAPSHOT_ID,
            )
            live = read_evidence_detail(
                session, case_id=CASE_ID, evidence_id=workbench["old_evidence"]
            )
        finally:
            session.close()

        assert payload is not None and live is not None
        assert payload["snapshot_id"] == SNAPSHOT_ID
        # The frozen pointer, not today's current capture.
        assert payload["current_capture_id"] == workbench["old_capture"]
        assert live["current_capture_id"] == workbench["revised_capture"]
        assert payload["unavailable_capture_ids"] == []
        assert payload["live_state"] == {
            "present": True,
            "current_capture_id": workbench["revised_capture"],
            "current_capture_matches_snapshot": False,
        }

        capture_ids = [capture["id"] for capture in payload["captures"]]
        assert capture_ids == [workbench["old_capture"]]
        capture = payload["captures"][0]
        assert capture["is_current"] is True
        assert capture["char_length"] == len(OLD_BODY)
        assert capture["text_sha256"]

        # Claim references use the frozen claim text, never the rewritten row.
        related = payload["related_claims"]
        assert len(related) == 1
        assert related[0]["claim_id"] == workbench["contested_claim"]
        assert related[0]["claim_text"] == FROZEN_CONTESTED_TEXT
        assert related[0]["quote"] == CONTESTED_QUOTE_LEFT
        # The live-only claim and its new capture are not part of the observation.
        assert workbench["live_only_claim"] not in {
            item["claim_id"] for item in related
        }
        assert workbench["revised_capture"] not in capture_ids

    def test_frozen_source_metadata_is_not_read_from_live_rows(self, workbench):
        session = db_session()
        try:
            payload = read_evidence_detail(
                session,
                case_id=CASE_ID,
                evidence_id=workbench["right_evidence"],
                snapshot_id=SNAPSHOT_ID,
            )
            live = read_evidence_detail(
                session, case_id=CASE_ID, evidence_id=workbench["right_evidence"]
            )
        finally:
            session.close()

        assert payload is not None and live is not None
        assert payload["publisher"] == "Northern Post"
        assert payload["title"] == "Source ev-r03b-right"
        assert payload["verification_status"] == "UNVERIFIED"
        assert live["publisher"] == "Northern Post (renamed)"
        assert live["verification_status"] == "VERIFIED"
        assert payload["live_state"]["present"] is True
        assert payload["live_state"]["current_capture_matches_snapshot"] is True

    def test_frozen_capture_metadata_is_served(self, workbench):
        session = db_session()
        try:
            payload = read_evidence_detail(
                session,
                case_id=CASE_ID,
                evidence_id=workbench["stable_evidence"],
                snapshot_id=SNAPSHOT_ID,
            )
        finally:
            session.close()

        assert payload is not None
        assert payload["capture_metadata"] == {"lineage": {"origin": "rss"}}

    def test_unresolvable_capture_body_is_explicitly_unavailable(self, workbench):
        session = db_session()
        try:
            # Simulate a lost/corrupted immutable body: the stored hash no longer
            # matches the hash the snapshot recorded. Raw SQL bypasses the ORM
            # append-only guard on purpose; the temporary DB is rolled back below.
            session.execute(
                text(
                    "UPDATE evidence_captures SET text_sha256 = :hash WHERE id = :id"
                ),
                {"hash": "0" * 64, "id": workbench["right_capture"]},
            )
            session.flush()
            payload = read_evidence_detail(
                session,
                case_id=CASE_ID,
                evidence_id=workbench["right_evidence"],
                snapshot_id=SNAPSHOT_ID,
            )
            assert payload is not None
            assert payload["unavailable_capture_ids"] == [
                workbench["right_capture"]
            ]
            assert payload["captures"] == []
            # A comparison cannot show a text comparison for that capture.
            with pytest.raises(ComparisonNotFound):
                read_comparison(
                    session,
                    case_id=CASE_ID,
                    left_evidence_id=workbench["left_evidence"],
                    right_evidence_id=workbench["right_evidence"],
                    snapshot_id=SNAPSHOT_ID,
                )
        finally:
            session.rollback()
            session.close()

    def test_unknown_and_cross_case_snapshots_raise(self, workbench):
        session = db_session()
        try:
            with pytest.raises(SnapshotNotFound):
                read_evidence_detail(
                    session,
                    case_id=CASE_ID,
                    evidence_id=workbench["stable_evidence"],
                    snapshot_id="snap-missing",
                )
            with pytest.raises(SnapshotNotFound):
                read_evidence_detail(
                    session,
                    case_id=CASE_ID,
                    evidence_id=workbench["stable_evidence"],
                    snapshot_id=OTHER_SNAPSHOT_ID,
                )
        finally:
            session.close()

    def test_payload_without_the_additive_fields_still_reads(self, workbench):
        """A snapshot published before R03b reads unknown, never from live rows."""

        def mutate(payload):
            for link in payload.get("links", []):
                link.pop("assessmentMetadata", None)
            for evidence_row in payload.get("evidence", []):
                evidence_row.pop("captureMetadata", None)
            for claim in payload.get("claims", []):
                claim.pop("narrativeClusterId", None)

        session = db_session()
        try:
            _derived_snapshot(
                session,
                snapshot_id="snap-r03b-older-payload",
                run_id="run-r03b-older-payload",
                sequence=2,
                mutate=mutate,
            )
            claim = read_claim_detail(
                session,
                case_id=CASE_ID,
                claim_id=workbench["contested_claim"],
                snapshot_id="snap-r03b-older-payload",
            )
            evidence = read_evidence_detail(
                session,
                case_id=CASE_ID,
                evidence_id=workbench["stable_evidence"],
                snapshot_id="snap-r03b-older-payload",
            )
        finally:
            session.rollback()
            session.close()

        assert claim is not None and evidence is not None
        # Absent additive fields stay unknown; nothing is filled from live rows.
        assert claim["narrative_cluster_id"] is None
        assert claim["verification_provenance"] == "unknown"
        assert all(
            passage["diagnostic_reason"] is None for passage in claim["passages"]
        )
        assert evidence["capture_metadata"] == {}

    def test_capture_without_a_recorded_hash_is_unavailable(self, workbench):
        """A body that cannot be tied to the observation fails closed."""

        def mutate(payload):
            for capture in payload.get("captures", []):
                if capture.get("id") == workbench["right_capture"]:
                    capture.pop("textSha256", None)

        session = db_session()
        try:
            _derived_snapshot(
                session,
                snapshot_id="snap-r03b-no-hash",
                run_id="run-r03b-no-hash",
                sequence=3,
                mutate=mutate,
            )
            evidence = read_evidence_detail(
                session,
                case_id=CASE_ID,
                evidence_id=workbench["right_evidence"],
                snapshot_id="snap-r03b-no-hash",
            )
            with pytest.raises(ComparisonNotFound):
                read_comparison(
                    session,
                    case_id=CASE_ID,
                    left_evidence_id=workbench["left_evidence"],
                    right_evidence_id=workbench["right_evidence"],
                    snapshot_id="snap-r03b-no-hash",
                )
        finally:
            session.rollback()
            session.close()

        assert evidence is not None
        assert evidence["unavailable_capture_ids"] == [workbench["right_capture"]]
        assert evidence["captures"] == []

    def test_no_capture_body_is_duplicated_into_the_snapshot(self, workbench):
        session = db_session()
        try:
            snapshot = session.get(CaseSnapshot, SNAPSHOT_ID)
            assert snapshot is not None
            payload = json.dumps(snapshot.payload_json)
        finally:
            session.close()

        assert SHARED_BODY not in payload
        assert OLD_BODY not in payload
        # Capture bodies stay reachable through the immutable captures.
        assert workbench["left_capture"] in payload


# ---------------------------------------------------------------------------
# Comparison reader
# ---------------------------------------------------------------------------


class TestSnapshotComparison:
    def test_pins_the_frozen_captures_and_links(self, workbench):
        session = db_session()
        try:
            historical = read_comparison(
                session,
                case_id=CASE_ID,
                left_evidence_id=workbench["left_evidence"],
                right_evidence_id=workbench["old_evidence"],
                snapshot_id=SNAPSHOT_ID,
            )
            live = read_comparison(
                session,
                case_id=CASE_ID,
                left_evidence_id=workbench["left_evidence"],
                right_evidence_id=workbench["old_evidence"],
            )
        finally:
            session.close()

        assert historical["snapshot_id"] == SNAPSHOT_ID
        assert historical["left_capture_id"] == workbench["left_capture"]
        assert historical["right_capture_id"] == workbench["old_capture"]
        # The live read defaults to the advanced capture and its new claim.
        assert live["right_capture_id"] == workbench["revised_capture"]
        # The frozen left capture also carries the later-removed assertion.
        assert historical["claims"]["total"] == 2
        row = _row(historical, FROZEN_CONTESTED_TEXT)
        assert row["status"] == "shared"
        assert {passage["capture_id"] for passage in row["left"]["passages"]} == {
            workbench["left_capture"]
        }
        # A link added after the observation is never used historically.
        assert workbench["live_only_claim"] not in json.dumps(historical)
        assert any("pinned snapshot observation" in caveat for caveat in historical["caveats"])

    def test_contradiction_and_copy_caveats_are_preserved(self, workbench):
        session = db_session()
        try:
            payload = read_comparison(
                session,
                case_id=CASE_ID,
                left_evidence_id=workbench["left_evidence"],
                right_evidence_id=workbench["right_evidence"],
                snapshot_id=SNAPSHOT_ID,
            )
        finally:
            session.close()

        row = _row(payload, FROZEN_CONTESTED_TEXT)
        assert row["contradiction"]["explicit"] is True
        assert row["contradiction"]["conflict"] is True
        # Both sides recorded the same body, so P01 copy detection still applies.
        assert payload["dependency"]["detected"] is True
        assert payload["dependency"]["copy_detected"] is True
        assert payload["left"]["coverage"]["claim_linkage_status"] == "available"
        assert payload["left"]["publisher_key"] == "ev-r03b-left.example.com"
        assert payload["left"]["publisher_key_provisional"] is True

    def test_capture_recorded_only_after_the_observation_is_not_found(self, workbench):
        session = db_session()
        try:
            with pytest.raises(ComparisonNotFound):
                read_comparison(
                    session,
                    case_id=CASE_ID,
                    left_evidence_id=workbench["left_evidence"],
                    right_evidence_id=workbench["old_evidence"],
                    right_capture_id=workbench["revised_capture"],
                    snapshot_id=SNAPSHOT_ID,
                )
            with pytest.raises(ComparisonNotFound):
                read_comparison(
                    session,
                    case_id=CASE_ID,
                    left_evidence_id=workbench["left_evidence"],
                    right_evidence_id="ev-r03b-missing",
                    snapshot_id=SNAPSHOT_ID,
                )
            with pytest.raises(ComparisonNotFound):
                read_comparison(
                    session,
                    case_id=CASE_ID,
                    left_evidence_id=workbench["left_evidence"],
                    right_evidence_id=workbench["right_evidence"],
                    snapshot_id="snap-missing",
                )
            with pytest.raises(ComparisonNotFound):
                read_comparison(
                    session,
                    case_id=CASE_ID,
                    left_evidence_id=workbench["left_evidence"],
                    right_evidence_id=workbench["right_evidence"],
                    snapshot_id=OTHER_SNAPSHOT_ID,
                )
        finally:
            session.close()

    def test_historical_capture_without_links_is_unavailable(self, workbench):
        session = db_session()
        try:
            # Neither evidence has recorded any claim link at all.
            payload = read_comparison(
                session,
                case_id=CASE_ID,
                left_evidence_id=workbench["pair_evidence"],
                right_evidence_id=workbench["nolink_evidence"],
                snapshot_id=SNAPSHOT_ID,
            )
        finally:
            session.close()

        assert payload["claims"]["total"] == 0
        assert payload["left"]["coverage"]["claim_linkage_status"] == "empty"
        assert payload["left"]["coverage"]["historical_analysis_available"] is True

    def test_live_and_snapshot_agree_on_unchanged_rows(self, workbench):
        session = db_session()
        try:
            historical = read_comparison(
                session,
                case_id=CASE_ID,
                left_evidence_id=workbench["pair_evidence"],
                right_evidence_id=workbench["stable_right_evidence"],
                snapshot_id=SNAPSHOT_ID,
            )
            live = read_comparison(
                session,
                case_id=CASE_ID,
                left_evidence_id=workbench["pair_evidence"],
                right_evidence_id=workbench["stable_right_evidence"],
            )
        finally:
            session.close()

        assert historical["snapshot_id"] == SNAPSHOT_ID
        assert live["snapshot_id"] is None
        historical.pop("snapshot_id")
        live.pop("snapshot_id")
        # Identical data, identical deterministic comparison besides the extra
        # historical caveat.
        assert historical.pop("caveats")[:-1] == live.pop("caveats")
        historical.pop("policy")
        live.pop("policy")
        assert _normalized(historical) == _normalized(live)


# ---------------------------------------------------------------------------
# HTTP contract
# ---------------------------------------------------------------------------


class TestSnapshotHttpContract:
    @pytest.fixture
    def api(self, monkeypatch, tmp_path):
        seed(tmp_path)
        # The app selects storage once at startup; bind this test's disposable
        # database instead of inheriting the module-level default.
        app.state.database_path = tmp_path / "r03b.sqlite3"
        return TestClient(app)

    @pytest.mark.parametrize("selector", ["snapshotId", "snapshot_id"])
    def test_claim_and_evidence_readers_accept_the_selector(self, api, selector):
        claim = api.get(
            f"/api/cases/{CASE_ID}/claims/{'claim-r03b-removed'}",
            params={selector: SNAPSHOT_ID},
        )
        assert claim.status_code == 200, claim.text
        body = claim.json()
        assert body["snapshotId"] == SNAPSHOT_ID
        assert body["claimText"] == REMOVED_TEXT
        assert body["liveState"]["present"] is False

        evidence = api.get(
            f"/api/cases/{CASE_ID}/evidence/ev-r03b-old",
            params={selector: SNAPSHOT_ID},
        )
        assert evidence.status_code == 200, evidence.text
        payload = evidence.json()
        assert payload["snapshotId"] == SNAPSHOT_ID
        assert isinstance(payload["currentCaptureId"], str)
        assert [entry["id"] for entry in payload["captures"]] == [
            payload["currentCaptureId"]
        ]
        assert payload["unavailableCaptureIds"] == []
        assert payload["relatedClaims"][0]["claimText"] == FROZEN_CONTESTED_TEXT

    def test_comparison_accepts_the_selector(self, api):
        response = api.get(
            f"/api/cases/{CASE_ID}/comparison",
            params={
                "left": "ev-r03b-left",
                "right": "ev-r03b-old",
                "snapshotId": SNAPSHOT_ID,
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["snapshotId"] == SNAPSHOT_ID
        assert _row(payload, FROZEN_CONTESTED_TEXT)["status"] == "shared"

    def test_unknown_snapshot_and_absent_entities_are_404(self, api):
        missing_snapshot = api.get(
            f"/api/cases/{CASE_ID}/claims/claim-r03b-stable",
            params={"snapshotId": "snap-missing"},
        )
        assert missing_snapshot.status_code == 404
        assert "Snapshot snap-missing not found" in missing_snapshot.text

        absent = api.get(
            f"/api/cases/{CASE_ID}/claims/claim-r03b-live-only",
            params={"snapshotId": SNAPSHOT_ID},
        )
        assert absent.status_code == 404
        assert "not present in snapshot" in absent.text

        cross_case = api.get(
            f"/api/cases/{CASE_ID}/evidence/ev-r03b-stable",
            params={"snapshotId": OTHER_SNAPSHOT_ID},
        )
        assert cross_case.status_code == 404
        assert "not found for case" in cross_case.text

    def test_malformed_selectors_are_422(self, api):
        conflicting = api.get(
            f"/api/cases/{CASE_ID}/claims/claim-r03b-stable",
            params={"snapshotId": SNAPSHOT_ID, "snapshot_id": OTHER_SNAPSHOT_ID},
        )
        assert conflicting.status_code == 422
        assert "Conflicting" in conflicting.text

        empty = api.get(
            f"/api/cases/{CASE_ID}/claims/claim-r03b-stable",
            params={"snapshotId": ""},
        )
        assert empty.status_code == 422
        assert "must not be empty" in empty.text

    def test_live_reads_are_unchanged_without_a_selector(self, api):
        claim = api.get(f"/api/cases/{CASE_ID}/claims/claim-r03b-contested")
        assert claim.status_code == 200
        body = claim.json()
        assert body["claimText"] == REWRITTEN_CONTESTED_TEXT
        assert body["snapshotId"] is None
        assert body["liveState"] is None

        evidence = api.get(f"/api/cases/{CASE_ID}/evidence/ev-r03b-old")
        assert evidence.status_code == 200
        payload = evidence.json()
        assert payload["snapshotId"] is None
        assert payload["unavailableCaptureIds"] == []
        assert OLD_BODY not in evidence.text
        assert REVISED_BODY not in evidence.text
