"""E01 regression tests: immutable evidence captures.

Covers specification §4 capture semantics (normalization, exact hashes, separate
fingerprint, reuse/append, frozen metadata, honest times), event-store capture
persistence independent of claims, caller-transaction rollback safety, the
case-service canonical source body / fallback path, explicit legacy
materialization and migration-8 schema-only upgrades.

All application databases are tmp_path/memory databases; no production data or
network/provider calls are used.
"""

from __future__ import annotations

import copy
import hashlib
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event as sqlalchemy_event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.cases.evidence import (
    build_capture_metadata,
    compute_normalized_text_sha256,
    compute_text_sha256,
    fingerprint_text,
    materialize_legacy_capture,
    normalize_capture_text,
    record_evidence_capture,
    upsert_evidence_capture,
)
from src.cases.service import TopicCaseService
from src.storage import (
    Base,
    CaseArticle,
    CaseStageName,
    CaseStageRun,
    CaseStatus,
    Claim,
    ClaimEvidenceLink,
    EvidenceCapture,
    EvidenceItem,
    Event,
    StageStatus,
    Party,
    TopicCase,
    init_database,
)
from src.storage.event_store import store_event_in_db

EVENT_TS = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)
OBSERVED_1 = datetime(2026, 3, 8, 12, 5, tzinfo=UTC)
OBSERVED_2 = datetime(2026, 3, 8, 12, 6, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def db_session(tmp_path):
    db = init_database(str(tmp_path / "triangulate.db"))
    return db.get_session_sync()


def ensure_case(tmp_path, case_id: str = "case-1") -> None:
    session = db_session(tmp_path)
    try:
        if session.query(TopicCase).filter(TopicCase.id == case_id).first() is None:
            session.add(
                TopicCase(
                    id=case_id,
                    query="Capture case",
                    slug=f"{case_id}-slug",
                    status=CaseStatus.INVESTIGATING,
                    metadata_json={},
                )
            )
            session.commit()
    finally:
        session.close()


def evidence_payload(
    *,
    evidence_id: str = "evidence-1",
    content: str | None = "Source body",
    title: str = "Source title",
    url: str = "https://example.com/source-1",
    publisher: str = "Outlet One",
    observed_at: datetime | None = None,
    capture_metadata: dict | None = None,
) -> dict:
    return {
        "id": evidence_id,
        "evidence_type": "article",
        "source_type": "rss",
        "title": title,
        "origin_url": url,
        "canonical_url": url,
        "publisher": publisher,
        "published_at": "2026-03-08T00:00:00+00:00",
        "content": content,
        "observed_at": observed_at,
        "capture_metadata": capture_metadata or {},
        "verification_status": "UNVERIFIED",
        "credibility_tier": "unknown",
        "requires_human_review": False,
        "verification_checks": [],
    }


def claim_payload(claim: str, *, evidence: list[dict], signature: str | None = None) -> dict:
    return {
        "claim": claim,
        "verification_status": "ALLEGED",
        "claim_signature": signature or claim.lower().replace(" ", "-"),
        "evidence": evidence,
        "support_count": len(evidence),
        "oppose_count": 0,
        "source_diversity_count": 1,
    }


def build_event(
    event_id: str = "event-1",
    *,
    title: str = "Fallback source event",
    claims: list[dict] | None = None,
    evidence: list[dict] | None = None,
    source_url: str = "https://example.com/source-1",
    verification_status: str = "PROBABLE",
) -> dict:
    return {
        "id": event_id,
        "timestamp": EVENT_TS,
        "title": title,
        "summary": "Source summary.",
        "verification_status": verification_status,
        "source_url": source_url,
        "source_name": "Example",
        "claims": claims if claims is not None else [],
        "narratives": [],
        "parties": [],
        "party_investigations": [],
        "evidence": evidence if evidence is not None else [],
    }


def read_captures(tmp_path):
    session = db_session(tmp_path)
    try:
        capture = (
            session.query(EvidenceCapture)
            .order_by(EvidenceCapture.recorded_at.asc())
            .first()
        )
        if capture is not None:
            session.expunge(capture)
        return capture
    finally:
        session.close()


def capture_rows(tmp_path) -> list[EvidenceCapture]:
    session = db_session(tmp_path)
    try:
        rows = session.query(EvidenceCapture).order_by(EvidenceCapture.recorded_at).all()
        for row in rows:
            session.expunge(row)
        return rows
    finally:
        session.close()


def fingerprint_digest(text: str) -> str:
    return hashlib.sha256(fingerprint_text(text).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Normalization, exact hash and separate fingerprint
# ---------------------------------------------------------------------------


def test_normalization_only_folds_line_endings_and_hashes_exact_utf8(tmp_path):
    session = db_session(tmp_path)
    try:
        capture = upsert_evidence_capture(
            session,
            evidence_id="evidence-1",
            text="Fullwidth Ｃａｆｅ\r\nSecond\rThird",
        )
        assert capture.text == "Fullwidth Ｃａｆｅ\nSecond\nThird"
        assert capture.text_sha256 == hashlib.sha256(
            "Fullwidth Ｃａｆｅ\nSecond\nThird".encode("utf-8")
        ).hexdigest()
        assert capture.normalized_text_sha256 == fingerprint_digest(capture.text)
        assert capture.text_sha256 != capture.normalized_text_sha256
        # Raw body is not NFKC-normalized: the fullwidth characters survive.
        assert "Ｃａｆｅ" in capture.text
        assert capture.normalization_version == "v1"
        assert capture.capture_kind == "live"
        assert capture.observed_at is None
        assert capture.recorded_at is not None
    finally:
        session.close()


def test_fingerprint_uses_nfkc_casefold_whitespace_without_touching_body():
    raw = "  Ｃａｆｅ\u00a0 東京 😀\r\nStraße  "
    assert fingerprint_text(raw) == "cafe 東京 😀 strasse"
    assert compute_normalized_text_sha256(raw) == hashlib.sha256(
        "cafe 東京 😀 strasse".encode("utf-8")
    ).hexdigest()
    # The exact-body hash is over different (LF-only) text, so the two hashes
    # are independent and the raw quotation body is never NFKC-rewritten.
    assert compute_text_sha256(normalize_capture_text(raw)) == hashlib.sha256(
        "  Ｃａｆｅ\u00a0 東京 😀\nStraße  ".encode("utf-8")
    ).hexdigest()
    assert normalize_capture_text(raw).startswith("  Ｃａｆｅ\u00a0")


# ---------------------------------------------------------------------------
# Reuse, append-only versions and frozen metadata
# ---------------------------------------------------------------------------


def test_identical_normalized_text_reuses_capture_and_metadata_is_frozen(tmp_path):
    session = db_session(tmp_path)
    try:
        metadata = {"title": "first", "nested": {"value": 1}}
        first = upsert_evidence_capture(
            session,
            evidence_id="evidence-1",
            text="Line A\r\nLine B",
            observed_at=OBSERVED_1,
            metadata=metadata,
        )
        first_id = first.id
        first_recorded = first.recorded_at

        # Caller mutation after the write must not rewrite the frozen record.
        metadata["title"] = "mutated"
        metadata["nested"]["value"] = 99

        reuse = upsert_evidence_capture(
            session,
            evidence_id="evidence-1",
            text="Line A\nLine B",  # LF-equivalent to the stored body
            observed_at=OBSERVED_2,
            metadata={"title": "second"},
        )
        assert reuse.id == first_id
        assert reuse.text == "Line A\nLine B"
        assert reuse.observed_at == OBSERVED_1
        assert reuse.recorded_at == first_recorded
        assert reuse.metadata_json == {"title": "first", "nested": {"value": 1}}

        changed = upsert_evidence_capture(
            session,
            evidence_id="evidence-1",
            text="Line A\nLine B\nLine C",
            observed_at=OBSERVED_2,
        )
        assert changed.id != first_id
        assert session.query(EvidenceCapture).filter_by(evidence_id="evidence-1").count() == 2
    finally:
        session.close()


def test_capture_rows_are_append_only_at_the_orm_boundary(tmp_path):
    session = db_session(tmp_path)
    try:
        capture = upsert_evidence_capture(
            session, evidence_id="evidence-1", text="Original body"
        )
        capture.text = "Tampered body"
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()
    finally:
        session.close()


def test_none_skips_capture_while_explicit_empty_string_is_a_real_capture(tmp_path):
    session = db_session(tmp_path)
    try:
        evidence = EvidenceItem(
            id="evidence-1",
            case_id="case-1",
            evidence_type="article",
            source_type="rss",
            content="Existing projection",
        )
        session.add(evidence)
        session.flush()

        assert record_evidence_capture(session, evidence, text=None) is None
        assert evidence.current_capture_id is None
        assert evidence.content == "Existing projection"

        capture = record_evidence_capture(session, evidence, text="")
        assert capture is not None
        assert capture.text == ""
        assert evidence.current_capture_id == capture.id
        assert evidence.content == ""
        assert session.query(EvidenceCapture).count() == 1
    finally:
        session.close()


def test_build_capture_metadata_includes_known_fields_only():
    metadata = build_capture_metadata(
        {
            "title": "Title",
            "publisher": None,
            "source_type": "rss",
            "origin_url": "https://example.com/a",
            "canonical_url": None,
            "published_at": "2026-03-08T00:00:00+00:00",
            "capture_metadata": {"credibility_tier": "unknown"},
        }
    )
    assert metadata["title"] == "Title"
    assert "publisher" not in metadata
    assert metadata["source_type"] == "rss"
    assert metadata["origin_url"] == "https://example.com/a"
    assert "canonical_url" not in metadata
    assert metadata["capture_metadata"] == {"credibility_tier": "unknown"}


# ---------------------------------------------------------------------------
# Event-store persistence independent of claims
# ---------------------------------------------------------------------------


def test_zero_claim_event_persists_source_capture_and_no_links(tmp_path):
    ensure_case(tmp_path)
    event = build_event(
        evidence=[evidence_payload(content="Body\r\nfirst")],
        title="Zero claim source",
    )
    session = db_session(tmp_path)
    try:
        assert (
            store_event_in_db(event, case_id="case-1", create_review=False) is True
        )

        assert session.query(Event).count() == 1
        assert session.query(Claim).count() == 0
        assert session.query(ClaimEvidenceLink).count() == 0
        evidence = session.query(EvidenceItem).one()
        capture = session.query(EvidenceCapture).one()
        assert evidence.content == "Body\nfirst"
        assert evidence.current_capture_id == capture.id
        assert capture.text == "Body\nfirst"
        assert capture.text_sha256 == hashlib.sha256(b"Body\nfirst").hexdigest()
        assert capture.metadata_json["title"] == "Source title"
        assert capture.metadata_json["canonical_url"] == "https://example.com/source-1"
        assert capture.metadata_json["published_at"] == "2026-03-08T00:00:00+00:00"
        # Publication metadata is not used as an observation time.
        assert capture.observed_at is None
    finally:
        session.close()


def test_claims_create_links_but_share_one_immutable_capture(tmp_path):
    ensure_case(tmp_path)
    shared = evidence_payload(evidence_id="evidence-shared", content="Shared body")
    event = build_event(
        claims=[
            claim_payload("Alpha", evidence=[copy.deepcopy(shared)]),
            claim_payload("Beta", evidence=[copy.deepcopy(shared)]),
        ],
        evidence=[copy.deepcopy(shared)],
    )
    session = db_session(tmp_path)
    try:
        assert store_event_in_db(event, case_id="case-1", create_review=False) is True
        assert session.query(Claim).count() == 2
        assert session.query(ClaimEvidenceLink).count() == 2
        assert session.query(EvidenceItem).count() == 1
        assert session.query(EvidenceCapture).count() == 1
    finally:
        session.close()


def test_reobservation_preserves_first_capture_and_missing_body_keeps_projection(tmp_path):
    ensure_case(tmp_path)
    first = build_event(
        title="First title",
        evidence=[
            evidence_payload(
                content="Stable body", title="First title", observed_at=OBSERVED_1
            )
        ],
    )
    assert store_event_in_db(first, case_id="case-1", create_review=False) is True
    original = read_captures(tmp_path)
    assert original is not None
    original_id = original.id
    original_recorded = original.recorded_at
    original_metadata = copy.deepcopy(original.metadata_json)

    # Same body on a rerun: reuse the version, keep the first observation and
    # metadata even though the incoming title/observation time differ.
    rerun = build_event(
        title="Second title",
        evidence=[
            evidence_payload(
                content="Stable body", title="Second title", observed_at=OBSERVED_2
            )
        ],
    )
    assert store_event_in_db(rerun, case_id="case-1", create_review=False) is True
    reused = read_captures(tmp_path)
    assert reused.id == original_id
    assert reused.recorded_at == original_recorded
    assert reused.observed_at == OBSERVED_1.replace(tzinfo=None)
    assert reused.metadata_json == original_metadata
    assert reused.metadata_json["title"] == "First title"

    # A later run with no supplied body must not clear the known projection.
    missing = build_event(
        title="Third title",
        evidence=[evidence_payload(content=None, title="Third title")],
    )
    assert store_event_in_db(missing, case_id="case-1", create_review=False) is True
    assert len(capture_rows(tmp_path)) == 1
    session = db_session(tmp_path)
    try:
        evidence = session.query(EvidenceItem).one()
        assert evidence.current_capture_id == original_id
        assert evidence.content == "Stable body"
    finally:
        session.close()

    # A genuinely changed body appends a new version and moves the pointer.
    changed = build_event(
        title="Fourth title",
        evidence=[evidence_payload(content="Changed body", title="Fourth title")],
    )
    assert store_event_in_db(changed, case_id="case-1", create_review=False) is True
    rows = capture_rows(tmp_path)
    assert len(rows) == 2
    assert rows[0].id == original_id
    assert rows[0].text == "Stable body"
    session = db_session(tmp_path)
    try:
        evidence = session.query(EvidenceItem).one()
        assert evidence.content == "Changed body"
        assert evidence.current_capture_id == rows[1].id
    finally:
        session.close()


def test_capture_and_pointer_rollback_with_failed_second_event(tmp_path):
    ensure_case(tmp_path)
    session = db_session(tmp_path)
    try:
        first = build_event(
            event_id="event-1",
            evidence=[evidence_payload(evidence_id="evidence-1", content="First body")],
        )
        store_event_in_db(first, case_id="case-1", session=session, create_review=False)
        assert session.query(EvidenceCapture).count() == 1
        assert session.query(EvidenceItem).count() == 1

        second = build_event(
            event_id="event-2",
            evidence=[evidence_payload(evidence_id="evidence-2", content="Second body")],
        )
        second["verification_status"] = "NOT_A_REAL_STATUS"
        with pytest.raises(KeyError):
            store_event_in_db(second, case_id="case-1", session=session, create_review=False)

        session.rollback()
        assert session.query(Event).count() == 0
        assert session.query(EvidenceItem).count() == 0
        assert session.query(EvidenceCapture).count() == 0
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Case service: one canonical body and the baseline fallback path
# ---------------------------------------------------------------------------


def make_service(tmp_path) -> TopicCaseService:
    return TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)


def seed_case_article(tmp_path, *, raw_content="Raw\r\nbody", projection="Projection body"):
    ensure_case(tmp_path)
    session = db_session(tmp_path)
    try:
        case = session.query(TopicCase).filter(TopicCase.id == "case-1").one()
        article = CaseArticle(
            id="article-1",
            case_id="case-1",
            url="https://example.com/article",
            title="Article title",
            source="Example",
            published_at="2026-03-08T12:00:00+00:00",
            fingerprint="fingerprint-1",
            content=projection,
            raw_payload={"content": raw_content}
            if raw_content is not None
            else {},
        )
        session.add(article)
        session.commit()
        session.expunge(case)
        session.expunge(article)
        return case, article
    finally:
        session.close()


@pytest.mark.asyncio
async def test_fallback_zero_claim_event_uses_one_normalized_body_and_keeps_capture(
    tmp_path, monkeypatch
):
    case, article = seed_case_article(
        tmp_path, raw_content="Raw\r\nbody", projection="Projection body"
    )
    service = make_service(tmp_path)
    seen: dict[str, str] = {}

    async def fake_process(article_data):
        seen["content"] = article_data["content"]
        return None

    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)

    event = await service._process_case_article(case, article)

    assert seen["content"] == "Raw\nbody"
    assert event["claims"] == []
    assert event["workflow_route"] == "baseline_only"
    assert event["source_type"] == "rss"
    assert event["case_article_id"] == "article-1"
    assert event["evidence"][0]["content"] == "Raw\nbody"

    assert store_event_in_db(event, case_id=case.id, create_review=False) is True
    session = db_session(tmp_path)
    try:
        assert session.query(Claim).count() == 0
        evidence = session.query(EvidenceItem).one()
        capture = session.query(EvidenceCapture).one()
        assert evidence.content == "Raw\nbody"
        assert capture.text == "Raw\nbody"
        assert capture.text_sha256 == hashlib.sha256(b"Raw\nbody").hexdigest()
    finally:
        session.close()


@pytest.mark.asyncio
async def test_projection_body_is_used_when_raw_payload_has_none(tmp_path, monkeypatch):
    case, article = seed_case_article(
        tmp_path, raw_content=None, projection="Projection\r\nbody"
    )
    service = make_service(tmp_path)
    seen: dict[str, str] = {}

    async def fake_process(article_data):
        seen["content"] = article_data["content"]
        return {
            "id": "temporary",
            "timestamp": EVENT_TS,
            "title": article_data["title"],
            "summary": "No claims extracted.",
            "verification_status": "ALLEGED",
            "claims": [],
            "narratives": [],
            "parties": [],
            "party_investigations": [],
        }

    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)

    event = await service._process_case_article(case, article)

    assert seen["content"] == "Projection\nbody"
    assert event["claims"] == []
    assert event["workflow_route"] == "baseline_only"
    assert event["evidence"][0]["content"] == "Projection\nbody"
    assert store_event_in_db(event, case_id=case.id, create_review=False) is True
    assert capture_rows(tmp_path)[0].text == "Projection\nbody"


# ---------------------------------------------------------------------------
# Explicit offline legacy materialization
# ---------------------------------------------------------------------------


def test_legacy_materialization_is_explicit_idempotent_and_unknown(tmp_path):
    ensure_case(tmp_path)
    session = db_session(tmp_path)
    try:
        evidence = EvidenceItem(
            id="evidence-legacy",
            case_id="case-1",
            evidence_type="article",
            source_type="rss",
            title="Legacy title",
            canonical_url="https://example.com/legacy",
            published_at="2020-01-01T00:00:00+00:00",
            content="Legacy\r\nbody",
            capture_metadata={"legacy": True},
        )
        session.add(evidence)
        session.commit()

        # Reading/existing schema state never creates captures automatically.
        assert session.query(EvidenceCapture).count() == 0

        capture = materialize_legacy_capture(session, "evidence-legacy")
        assert capture is not None
        assert capture.capture_kind == "legacy_snapshot"
        assert capture.text == "Legacy\nbody"
        assert capture.observed_at is None
        assert capture.recorded_at is not None
        assert capture.metadata_json["title"] == "Legacy title"
        assert capture.metadata_json["canonical_url"] == "https://example.com/legacy"
        assert capture.metadata_json["capture_metadata"] == {"legacy": True}
        assert evidence.current_capture_id == capture.id
        assert evidence.content == "Legacy\nbody"

        first_id = capture.id
        first_recorded = capture.recorded_at
        first_metadata = copy.deepcopy(capture.metadata_json)

        repeat = materialize_legacy_capture(session, "evidence-legacy")
        assert repeat.id == first_id
        assert repeat.recorded_at == first_recorded
        assert repeat.metadata_json == first_metadata
        assert session.query(EvidenceCapture).count() == 1
    finally:
        session.close()


def test_legacy_materialization_without_content_creates_nothing(tmp_path):
    ensure_case(tmp_path)
    session = db_session(tmp_path)
    try:
        session.add(
            EvidenceItem(
                id="evidence-empty",
                case_id="case-1",
                evidence_type="article",
                source_type="rss",
                content=None,
            )
        )
        session.commit()
        assert materialize_legacy_capture(session, "evidence-empty") is None
        assert session.query(EvidenceCapture).count() == 0
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Foreign-key enforcement scratch database
# ---------------------------------------------------------------------------


def test_fk_enforced_scratch_keeps_capture_history_after_claim_deletion(tmp_path):
    db_path = tmp_path / "fk-enforced.db"
    engine = create_engine(f"sqlite:///{db_path}")

    @sqlalchemy_event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session = sessionmaker(
        autocommit=False, autoflush=False, expire_on_commit=False, bind=engine
    )()
    try:
        case = TopicCase(
            id="case-fk",
            query="FK case",
            slug="fk-case",
            status=CaseStatus.INVESTIGATING,
            metadata_json={},
        )
        stage_run = CaseStageRun(
            id="stage-run-1",
            case_id="case-fk",
            stage_name=CaseStageName.INVESTIGATE,
            status=StageStatus.RUNNING,
        )
        session.add(case)
        session.flush()
        session.add(stage_run)
        session.flush()

        event = build_event(
            event_id="event-fk",
            claims=[
                claim_payload(
                    "FK claim",
                    evidence=[
                        evidence_payload(evidence_id="evidence-fk", content="FK body")
                    ],
                )
            ],
        )
        store_event_in_db(
            event,
            case_id="case-fk",
            case_run_id="stage-run-1",
            session=session,
            create_review=False,
        )
        session.commit()

        capture = session.query(EvidenceCapture).one()
        assert capture.metadata_json["origin_stage_attempt_id"] == "stage-run-1"
        assert session.query(ClaimEvidenceLink).count() == 1
        assert session.query(EvidenceItem).one().current_capture_id == capture.id

        # An orphan capture cannot be written while FK enforcement is on.
        session.add(
            EvidenceCapture(
                id="orphan-capture",
                evidence_id="missing-evidence",
                text="orphan",
                text_sha256=compute_text_sha256("orphan"),
                normalized_text_sha256=compute_normalized_text_sha256("orphan"),
                normalization_version="v1",
                metadata_json={},
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

        # Deleting the live link/claim must never delete the immutable capture.
        link = session.query(ClaimEvidenceLink).one()
        claim = session.query(Claim).one()
        session.delete(link)
        session.flush()
        session.delete(claim)
        session.flush()
        session.commit()
        assert session.query(EvidenceCapture).count() == 1
        assert session.query(EvidenceItem).one().current_capture_id == capture.id
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Parent-review regressions: provenance freezing, anonymous IDs, cross-case
# ---------------------------------------------------------------------------


def _capture_by_text(rows, text):
    return next(row for row in rows if row.text == text)


def test_changed_body_freezes_new_publication_archive_metadata_per_version(tmp_path):
    ensure_case(tmp_path)

    def store(content, *, published_at, archived_url, include=True):
        payload = evidence_payload(
            evidence_id="evidence-1", content=content, title="Stable title"
        )
        if include:
            payload["published_at"] = published_at
            payload["archived_url"] = archived_url
        else:
            payload.pop("published_at", None)
            payload.pop("archived_url", None)
        event = build_event(evidence=[payload])
        assert store_event_in_db(event, case_id="case-1", create_review=False) is True

    store("Body v1", published_at="2020-01-01T00:00:00+00:00", archived_url="https://archive/1")
    store("Body v2", published_at="2022-02-02T00:00:00+00:00", archived_url="https://archive/2")
    store("Body v3", published_at=None, archived_url=None, include=False)
    store("Body v4", published_at=None, archived_url=None)

    rows = capture_rows(tmp_path)
    assert len(rows) == 4
    v1 = _capture_by_text(rows, "Body v1")
    v2 = _capture_by_text(rows, "Body v2")
    v3 = _capture_by_text(rows, "Body v3")
    v4 = _capture_by_text(rows, "Body v4")

    # Old version keeps its first metadata forever.
    assert v1.metadata_json["published_at"] == "2020-01-01T00:00:00+00:00"
    assert v1.metadata_json["archived_url"] == "https://archive/1"
    # Changed body freezes the newly supplied provenance, not stale values.
    assert v2.metadata_json["published_at"] == "2022-02-02T00:00:00+00:00"
    assert v2.metadata_json["archived_url"] == "https://archive/2"
    # Omitted keys retain the evidence row's stored values.
    assert v3.metadata_json["published_at"] == "2022-02-02T00:00:00+00:00"
    assert v3.metadata_json["archived_url"] == "https://archive/2"
    # Explicit None clears them before freezing (unknown stays absent).
    assert "published_at" not in v4.metadata_json
    assert "archived_url" not in v4.metadata_json


def test_two_anonymous_evidence_ids_do_not_merge_without_url(tmp_path):
    ensure_case(tmp_path)
    first = evidence_payload(evidence_id="anon-a", content="Anonymous A")
    first.update({"canonical_url": None, "origin_url": None})
    second = evidence_payload(evidence_id="anon-b", content="Anonymous B")
    second.update({"canonical_url": None, "origin_url": None})
    event = build_event(evidence=[first, second], source_url=None)

    assert store_event_in_db(event, case_id="case-1", create_review=False) is True
    session = db_session(tmp_path)
    try:
        items = session.query(EvidenceItem).order_by(EvidenceItem.id).all()
        assert [item.id for item in items] == ["anon-a", "anon-b"]
        assert [item.content for item in items] == ["Anonymous A", "Anonymous B"]
        assert session.query(EvidenceCapture).count() == 2
    finally:
        session.close()


def test_cross_case_evidence_id_is_rejected_not_reparented(tmp_path):
    ensure_case(tmp_path, "case-1")
    ensure_case(tmp_path, "case-2")
    session = db_session(tmp_path)
    try:
        first = build_event(
            event_id="event-1",
            evidence=[evidence_payload(evidence_id="shared-evidence", content="Case one")],
        )
        store_event_in_db(first, case_id="case-1", session=session, create_review=False)
        session.commit()

        cross = build_event(
            event_id="event-2",
            evidence=[evidence_payload(evidence_id="shared-evidence", content="Case two")],
        )
        with pytest.raises(ValueError, match="different case"):
            store_event_in_db(cross, case_id="case-2", session=session, create_review=False)
        session.rollback()

        evidence = session.query(EvidenceItem).filter_by(id="shared-evidence").one()
        assert evidence.case_id == "case-1"
        assert evidence.content == "Case one"
    finally:
        session.close()


def test_observed_at_normalizes_offset_to_utc_and_first_observation_survives(tmp_path):
    session = db_session(tmp_path)
    try:
        plus_eight = timezone(timedelta(hours=8))
        observed = datetime(2026, 3, 8, 12, 5, tzinfo=plus_eight)
        capture = upsert_evidence_capture(
            session, evidence_id="evidence-tz", text="TZ body", observed_at=observed
        )
        expected = datetime(2026, 3, 8, 4, 5, tzinfo=UTC)
        assert capture.observed_at == expected
        session.commit()

        reloaded = (
            session.query(EvidenceCapture).filter_by(id=capture.id).one()
        )
        # SQLite returns a naive value representing the persisted UTC instant.
        assert reloaded.observed_at.replace(tzinfo=UTC) == expected

        reuse = upsert_evidence_capture(
            session,
            evidence_id="evidence-tz",
            text="TZ body",
            observed_at=datetime(2026, 3, 9, 0, 0, tzinfo=plus_eight),
        )
        assert reuse.id == capture.id
        assert reuse.observed_at.replace(tzinfo=UTC) == expected

        with pytest.raises(ValueError, match="timezone-aware"):
            upsert_evidence_capture(
                session,
                evidence_id="evidence-tz",
                text="Naive body",
                observed_at=datetime(2026, 3, 8, 4, 5),
            )
    finally:
        session.close()


def test_orm_delete_of_old_non_current_capture_is_rejected(tmp_path):
    session = db_session(tmp_path)
    try:
        old = upsert_evidence_capture(
            session, evidence_id="evidence-history", text="Old body"
        )
        upsert_evidence_capture(
            session, evidence_id="evidence-history", text="New body"
        )
        session.delete(old)
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()
    finally:
        session.close()


@pytest.mark.asyncio
async def test_case_none_body_stays_unknown_and_explicit_empty_is_a_capture(
    tmp_path, monkeypatch
):
    case, article = seed_case_article(
        tmp_path, raw_content=None, projection=None
    )
    service = make_service(tmp_path)
    seen: dict[str, str] = {}

    async def fake_process(article_data):
        seen["content"] = article_data["content"]
        return None

    monkeypatch.setattr(service.ai_workflow, "process_article", fake_process)
    event = await service._process_case_article(case, article)

    assert seen["content"] == ""
    assert event["summary"] == ""
    assert event["evidence"][0]["content"] is None
    assert store_event_in_db(event, case_id=case.id, create_review=False) is True
    session = db_session(tmp_path)
    try:
        evidence = session.query(EvidenceItem).one()
        assert evidence.current_capture_id is None
        assert session.query(EvidenceCapture).count() == 0
    finally:
        session.close()

    # Explicit empty body is a real (empty) capture, not None. Reuse the same
    # case/article/event/evidence IDs by updating the stored article body.
    session = db_session(tmp_path)
    try:
        stored_article = session.query(CaseArticle).one()
        stored_article.raw_payload = {"content": ""}
        stored_article.content = None
        session.commit()
        session.expunge(stored_article)
        article = stored_article
    finally:
        session.close()

    event = await service._process_case_article(case, article)
    assert seen["content"] == ""
    assert event["evidence"][0]["content"] == ""
    # Reuse the same deterministic event/evidence IDs deterministically.
    assert store_event_in_db(event, case_id=case.id, create_review=False) is True
    session = db_session(tmp_path)
    try:
        capture = session.query(EvidenceCapture).one()
        assert capture.text == ""
        assert session.query(EvidenceItem).one().current_capture_id == capture.id
    finally:
        session.close()


def _fk_session(tmp_path):
    db_path = tmp_path / "fk-extra.db"
    engine = create_engine(f"sqlite:///{db_path}")

    @sqlalchemy_event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session = sessionmaker(
        autocommit=False, autoflush=False, expire_on_commit=False, bind=engine
    )()
    return session, engine


def test_fk_enforced_party_referenced_claim_and_zero_claim_source(tmp_path):
    session, engine = _fk_session(tmp_path)
    try:
        session.add(
            TopicCase(
                id="case-fk-2",
                query="FK party case",
                slug="fk-party-case",
                status=CaseStatus.INVESTIGATING,
                metadata_json={},
            )
        )
        session.flush()

        party_event = build_event(
            event_id="event-fk-party",
            claims=[
                claim_payload(
                    "Party claim",
                    evidence=[evidence_payload(evidence_id="ev-fk-party", content="P1")],
                )
            ],
        )
        party_event["parties"] = [
            {"canonical_name": "Alpha", "aliases": ["Alpha"]}
        ]
        party_event["claims"][0]["party_name"] = "Alpha"
        store_event_in_db(
            party_event, case_id="case-fk-2", session=session, create_review=False
        )
        session.flush()
        claim = session.query(Claim).filter_by(claim_text="Party claim").one()
        assert claim.party_id is not None
        assert session.query(Party).filter_by(canonical_name="Alpha").count() == 1

        zero_event = build_event(
            event_id="event-fk-zero",
            source_url="https://example.com/zero",
            evidence=[
                evidence_payload(
                    evidence_id="ev-fk-zero",
                    content="Z1",
                    url="https://example.com/zero",
                )
            ],
        )
        store_event_in_db(
            zero_event, case_id="case-fk-2", session=session, create_review=False
        )
        session.flush()
        zero_evidence = session.query(EvidenceItem).filter_by(id="ev-fk-zero").one()
        assert zero_evidence.current_capture_id is not None
        session.commit()
    finally:
        session.close()
        engine.dispose()

