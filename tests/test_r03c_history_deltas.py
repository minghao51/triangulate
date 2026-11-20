"""R03c: change-origin honesty and consistent snapshot composition.

These are unit-level regressions for three review findings:

* a delta item must record the run that *observed* it separately from the entity's
  recorded origin, and must never attribute an entity to the observing run just
  because that run saw it;
* derived counts (claim support/oppose/diversity, narrative source count) are not
  semantic, so a count-only change cannot alter the semantic projection;
* snapshot composition must read one committed state, which needs an explicit
  SQLite read transaction because pysqlite does not open one for plain queries.

No model, network or source-capture call is made.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from src.cases.history import (
    COVERAGE_COMPLETE,
    build_snapshot_delta,
    semantic_hash_for_payload,
    semantic_view,
)
from src.storage import (
    CaseStatus,
    Claim,
    Event,
    TopicCase,
    VerificationStatus,
    begin_read_transaction,
    init_database,
)


def _payload(
    *,
    articles: list[dict] | None = None,
    events: list[dict] | None = None,
    claims: list[dict] | None = None,
    links: list[dict] | None = None,
    evidence: list[dict] | None = None,
    reviews: list[dict] | None = None,
    narratives: list[dict] | None = None,
) -> dict:
    return {
        "articles": articles or [],
        "events": events or [],
        "claims": claims or [],
        "links": links or [],
        "citations": [],
        "evidence": evidence or [],
        "captures": [],
        "reviews": reviews or [],
        "exceptions": [],
        "parties": [],
        "partyInvestigations": [],
        "narratives": narratives or [],
    }


def _event(event_id: str, *, origin: str | None) -> dict:
    return {
        "id": event_id,
        "timestamp": "2026-03-03T06:30:00",
        "title": f"Event {event_id}",
        "summary": None,
        "verificationStatus": "ALLEGED",
        "locationCountryCode": None,
        "locationLat": None,
        "locationLon": None,
        "workflowRoute": None,
        "sourceUrl": None,
        "investigationRunId": origin,
    }


def _claim(claim_id: str, event_id: str, text_value: str, **extra) -> dict:
    return {
        "id": claim_id,
        "eventId": event_id,
        "sourceId": None,
        "text": text_value,
        "claimSignature": f"signature-{claim_id}",
        "verificationStatus": "ALLEGED",
        "factAllegationType": "ALLEGATION",
        "partyPositions": {},
        "controversyScore": 0.1,
        "supportCount": 1,
        "opposeCount": 0,
        "sourceDiversityCount": 1,
        **extra,
    }


def _delta(
    baseline: dict,
    current: dict,
    *,
    run_id: str = "run-observed",
    authoritative_event_ids: set[str] | None = None,
) -> dict:
    return build_snapshot_delta(
        snapshot_id="snapshot-target",
        baseline_payload=baseline,
        baseline_snapshot_id="snapshot-baseline",
        current_payload=current,
        current_semantic=semantic_view(current),
        coverage=COVERAGE_COMPLETE,
        run_id=run_id,
        authoritative_event_ids=authoritative_event_ids,
        observed_at="2026-03-04T00:00:00",
    )


def _by_type(delta: dict) -> dict[str, dict]:
    return {item["type"]: item for item in delta["changes"]}


class TestChangeOriginAttribution:
    def test_entity_committed_by_an_earlier_run_keeps_that_origin(self):
        """A failed run's committed claim is not re-attributed to the observer."""
        baseline = _payload(
            events=[_event("event-1", origin="run-a")],
            claims=[_claim("claim-1", "event-1", "One assertion.")],
        )
        current = _payload(
            events=[
                _event("event-1", origin="run-a"),
                _event("event-2", origin="run-failed"),
            ],
            claims=[
                _claim("claim-1", "event-1", "One assertion."),
                _claim("claim-2", "event-2", "Added by an earlier failed run."),
            ],
        )

        added = _by_type(_delta(baseline, current))["claim_added"]

        assert added["entityId"] == "claim-2"
        assert added["originRunId"] == "run-failed"
        assert added["observedByRunId"] == "run-observed"

    def test_removed_claim_origin_comes_from_the_baseline_observation(self):
        baseline = _payload(
            events=[_event("event-1", origin="run-a")],
            claims=[_claim("claim-1", "event-1", "An assertion.")],
        )
        current = _payload(events=[_event("event-1", origin="run-a")])

        # A removal is only reportable for an event reprocessed in this run with
        # an authoritative extraction outcome; the origin still comes from the
        # baseline observation that recorded the entity.
        removed = _by_type(
            _delta(baseline, current, authoritative_event_ids={"event-1"})
        )["claim_no_longer_extracted"]

        assert removed["originRunId"] == "run-a"
        assert removed["observedByRunId"] == "run-observed"

    def test_article_origin_is_unknown_not_the_observer(self):
        """Articles carry no recorded run origin, so origin stays explicitly null."""
        current = _payload(
            articles=[
                {
                    "id": "article-1",
                    "url": "https://example.com/a",
                    "title": "Article A",
                    "source": "Example",
                    "publishedAt": None,
                    "fingerprint": "fp",
                    "status": "processed",
                    "sourceType": "rss",
                }
            ],
            events=[_event("event-1", origin="run-observed")],
        )

        added = _by_type(_delta(_payload(), current))["article_added"]

        assert added["originRunId"] is None
        assert added["observedByRunId"] == "run-observed"

    def test_link_change_origin_is_unknown_not_the_claim_origin(self):
        baseline = _payload(
            events=[_event("event-1", origin="run-a")],
            claims=[_claim("claim-1", "event-1", "An assertion.")],
            evidence=[
                {
                    "id": "evidence-1",
                    "eventId": "event-1",
                    "evidenceType": "article",
                    "sourceType": "rss",
                    "title": "Source",
                    "originUrl": "https://example.com/a",
                    "canonicalUrl": "https://example.com/a",
                    "publisher": "Example",
                    "publishedAt": None,
                    "currentCaptureId": "capture-1",
                    "verificationStatus": "UNVERIFIED",
                    "credibilityTier": "unknown",
                }
            ],
            links=[
                {
                    "id": "link-1",
                    "claimId": "claim-1",
                    "evidenceId": "evidence-1",
                    "captureId": "capture-1",
                    "citationId": None,
                    "relation": "reported_by",
                    "sourceDiversityRank": 1,
                    "confidenceScore": None,
                    "quote": "An assertion.",
                    "startChar": 0,
                    "endChar": 13,
                    "alignmentStatus": "exact",
                    "assessmentOrigin": "human",
                    "assessmentVersion": "v1",
                }
            ],
        )
        current = _payload(
            events=[_event("event-1", origin="run-a")],
            claims=[_claim("claim-1", "event-1", "An assertion.")],
            evidence=[dict(baseline["evidence"][0])],
            links=[
                {
                    **baseline["links"][0],
                    "relation": "contradicts",
                }
            ],
        )

        change = _by_type(_delta(baseline, current))["relationship_changed"]

        # A link row has no recorded run; the claim's older event run must not be
        # presented as the link's origin.
        assert change["originRunId"] is None
        assert change["observedByRunId"] == "run-observed"


class TestSemanticProjection:
    def test_derived_counts_are_not_semantic(self):
        """Count-only differences cannot change the projection, hash or delta."""
        first = _payload(
            events=[_event("event-1", origin="run-a")],
            claims=[_claim("claim-1", "event-1", "An assertion.")],
            narratives=[
                {
                    "id": "narrative-1",
                    "clusterId": "event-1:1",
                    "stanceSummary": "Mixed",
                    "sourceCount": 2,
                    "keyThemes": [],
                    "mainEntities": [],
                }
            ],
        )
        second = _payload(
            events=[_event("event-1", origin="run-a")],
            claims=[
                _claim(
                    "claim-1",
                    "event-1",
                    "An assertion.",
                    supportCount=9,
                    opposeCount=4,
                    sourceDiversityCount=7,
                )
            ],
            narratives=[
                {
                    "id": "narrative-1",
                    "clusterId": "event-1:1",
                    "stanceSummary": "Mixed",
                    "sourceCount": 5,
                    "keyThemes": [],
                    "mainEntities": [],
                }
            ],
        )

        assert semantic_view(first) == semantic_view(second)
        assert semantic_hash_for_payload(first) == semantic_hash_for_payload(second)
        delta = _delta(first, second)
        assert delta["availability"] == "ready"
        assert delta["changes"] == []


class TestConsistentObservation:
    def test_read_transaction_pins_one_committed_state(self, tmp_path):
        """A writer committing mid-observation must not appear in that observation."""
        database = init_database(str(tmp_path / "r03c-read-txn.sqlite3"))
        setup = database.get_session_sync()
        try:
            # WAL lets the writer commit while the reader holds its snapshot; the
            # isolation guarantee is the same under the default journal mode, where
            # the writer would simply wait for the reader instead.
            setup.connection().exec_driver_sql("PRAGMA journal_mode=WAL")
            setup.add(
                TopicCase(
                    id="case-r03c",
                    query="Read transaction",
                    slug="case-r03c",
                    status=CaseStatus.REVIEW_READY,
                    metadata_json={},
                )
            )
            setup.commit()
        finally:
            setup.close()

        reader = database.get_session_sync()
        try:
            begin_read_transaction(reader)
            before = reader.execute(select(func.count(Claim.id))).scalar_one()

            writer = database.get_session_sync()
            try:
                writer.add(
                    Event(
                        id="event-late",
                        timestamp=datetime(2026, 3, 4, 8, 0, tzinfo=UTC),
                        title="Late event",
                        verification_status=VerificationStatus.ALLEGED,
                        case_id="case-r03c",
                    )
                )
                writer.add(
                    Claim(
                        id="claim-late",
                        event_id="event-late",
                        claim_text="An assertion committed mid-read.",
                        verification_status=VerificationStatus.ALLEGED,
                    )
                )
                writer.commit()
            finally:
                writer.close()

            during = reader.execute(select(func.count(Claim.id))).scalar_one()
            assert during == before
        finally:
            reader.rollback()
            reader.close()

        observer = database.get_session_sync()
        try:
            after = observer.execute(select(func.count(Claim.id))).scalar_one()
            assert after == 1
        finally:
            observer.close()
