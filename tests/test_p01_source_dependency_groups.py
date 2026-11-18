"""P01: conservative source identity and dependency groups (specification §5).

The tests use synthetic temporary databases only. No network, provider or source
capture call is made; every read is a local deterministic query.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.cases.provenance import (
    MIN_COPY_NON_WHITESPACE_CODE_POINTS,
    SourceMember,
    build_source_summary,
    copy_fingerprint,
    normalize_source_url,
    read_source_summary,
    resolve_publisher_identity,
)
from src.cases.service import TopicCaseService, _claim_signature
from src.http.app import app
from src.http.dependencies import get_case_service
from src.storage import (
    CaseStatus,
    Claim,
    ClaimEvidenceLink,
    EvidenceCapture,
    EvidenceItem,
    Event,
    FactAllegationType,
    TopicCase,
    VerificationStatus,
    get_database,
    init_database,
)
from src.storage.captures import record_evidence_capture

CASE_ID = "case-p01"
OTHER_CASE_ID = "case-p01-other"
EVENT_ID = "event-p01"
OTHER_EVENT_ID = "event-p01-other"

LONG_BODY = ("Port Alden residents were told to leave before dawn. " * 20).strip()
LONG_BODY_REVISED = LONG_BODY + " Updated at 09:30 with shelter information."
SHORT_BODY = "Brief shared snippet."


def db_session():
    return get_database().get_session_sync()


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


def _add_claim(session, claim_id: str, event_id: str, text: str) -> Claim:
    claim = Claim(
        id=claim_id,
        event_id=event_id,
        claim_text=text,
        verification_status=VerificationStatus.ALLEGED,
        fact_allegation_type=FactAllegationType.ALLEGATION,
        claim_signature=_claim_signature(text),
    )
    session.add(claim)
    return claim


def _add_evidence(
    session,
    *,
    evidence_id: str,
    case_id: str,
    event_id: str,
    publisher: str | None,
    origin_url: str | None,
    canonical_url: str | None,
    body: str | None,
    capture_metadata: dict | None = None,
    metadata_extra: dict | None = None,
    case_article_id: str | None = None,
) -> tuple[EvidenceItem, EvidenceCapture | None]:
    evidence = EvidenceItem(
        id=evidence_id,
        case_id=case_id,
        event_id=event_id,
        case_article_id=case_article_id,
        evidence_type="article",
        source_type="rss",
        title=f"Source {evidence_id}",
        origin_url=origin_url,
        canonical_url=canonical_url,
        publisher=publisher,
        capture_metadata=capture_metadata or {},
        verification_status="UNVERIFIED",
        credibility_tier="unknown",
        requires_human_review=0,
    )
    session.add(evidence)
    session.flush()
    capture = None
    if body is not None:
        capture = record_evidence_capture(
            session,
            evidence,
            text=body,
            observed_at=datetime(2026, 3, 3, 6, 25, tzinfo=UTC),
            metadata=metadata_extra or {},
        )
    return evidence, capture


def _attach(
    session,
    *,
    link_id: str,
    claim: Claim,
    evidence: EvidenceItem,
    capture: EvidenceCapture | None,
) -> ClaimEvidenceLink:
    link = ClaimEvidenceLink(
        id=link_id,
        claim_id=claim.id,
        evidence_id=evidence.id,
        relation="reported_by",
        source_diversity_rank=1,
        confidence_score=None,
        capture_id=capture.id if capture is not None else None,
        alignment_status="not_provided",
        assessment_metadata={},
    )
    session.add(link)
    session.flush()
    return link


@pytest.fixture
def workbench(tmp_path):
    """Seed two cases with URL, publisher, copy, short-text and legacy variants."""
    init_database(str(tmp_path / "p01-sources.sqlite3"))
    session = db_session()
    try:
        _add_case(session, CASE_ID, "Port Alden evacuation order")
        _add_case(session, OTHER_CASE_ID, "Unrelated case")
        session.add(
            Event(
                id=EVENT_ID,
                timestamp=datetime(2026, 3, 3, 6, 30, tzinfo=UTC),
                title="Port Alden briefing",
                verification_status=VerificationStatus.ALLEGED,
                case_id=CASE_ID,
            )
        )
        session.add(
            Event(
                id=OTHER_EVENT_ID,
                timestamp=datetime(2026, 3, 3, 7, 0, tzinfo=UTC),
                title="Other case event",
                verification_status=VerificationStatus.ALLEGED,
                case_id=OTHER_CASE_ID,
            )
        )
        session.flush()

        claim_a = _add_claim(
            session, "claim-p01-a", EVENT_ID, "The authority ordered an evacuation."
        )
        claim_b = _add_claim(
            session, "claim-p01-b", EVENT_ID, "A second assertion about shelters."
        )
        claim_other = _add_claim(
            session, "claim-p01-other", OTHER_EVENT_ID, "Another case claim."
        )
        session.flush()

        shared_a, shared_a_capture = _add_evidence(
            session,
            evidence_id="ev-shared-a",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Meridian Wire",
            origin_url="https://wire.example.com/doc?utm_source=newsletter",
            canonical_url="https://wire.example.com/doc?utm_source=newsletter#top",
            body=LONG_BODY,
            capture_metadata={"publisher_key": "meridian-wire"},
            metadata_extra={
                "publisher_key": "meridian-wire",
                "source_dependency_key": "ported-alden-wire",
            },
        )
        shared_b, shared_b_capture = _add_evidence(
            session,
            evidence_id="ev-shared-b",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Meridian Wire",
            origin_url="https://wire.example.com/doc",
            canonical_url="https://wire.example.com/doc",
            body=LONG_BODY,
            capture_metadata={"publisher_key": "meridian-wire"},
            metadata_extra={
                "publisher_key": "meridian-wire",
                "source_dependency_key": "ported-alden-wire",
            },
        )
        copy_b, copy_b_capture = _add_evidence(
            session,
            evidence_id="ev-copy-b",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Northern Post",
            origin_url="https://northern.example.com/story",
            canonical_url="https://northern.example.com/story",
            body=LONG_BODY,
        )
        short_a, short_a_capture = _add_evidence(
            session,
            evidence_id="ev-short-a",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Alpha Desk",
            origin_url="https://alpha.example.com/a",
            canonical_url="https://alpha.example.com/a",
            body=SHORT_BODY,
        )
        short_b, short_b_capture = _add_evidence(
            session,
            evidence_id="ev-short-b",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Beta Desk",
            origin_url="https://beta.example.com/b",
            canonical_url="https://beta.example.com/b",
            body=SHORT_BODY,
        )
        unknown, unknown_capture = _add_evidence(
            session,
            evidence_id="ev-unknown",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Unconfigured Wire",
            origin_url=None,
            canonical_url=None,
            body="An unknown-origin body that is long enough to fingerprint but has no URL. " * 6,
        )
        legacy, _ = _add_evidence(
            session,
            evidence_id="ev-legacy",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Legacy Desk",
            origin_url="https://legacy.example.com/archive",
            canonical_url=None,
            body=None,
        )
        revised, revised_current = _add_evidence(
            session,
            evidence_id="ev-revised",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Revised Wire",
            origin_url="https://revised.example.com/story",
            canonical_url="https://revised.example.com/story",
            body=LONG_BODY_REVISED,
        )
        # Keep the old capture available for a claim link while the current
        # pointer moves to the revised body.
        old_capture = revised_current
        revised_current = record_evidence_capture(
            session,
            revised,
            text=LONG_BODY_REVISED + " Second update.",
            observed_at=datetime(2026, 3, 4, 8, 15, tzinfo=UTC),
        )

        assert shared_a_capture is not None
        assert shared_b_capture is not None
        assert copy_b_capture is not None
        assert short_a_capture is not None
        assert short_b_capture is not None
        assert unknown_capture is not None
        assert old_capture is not None
        assert revised_current is not None

        _attach(
            session,
            link_id="link-a-shared",
            claim=claim_a,
            evidence=shared_a,
            capture=shared_a_capture,
        )
        _attach(
            session,
            link_id="link-a-copy",
            claim=claim_a,
            evidence=copy_b,
            capture=copy_b_capture,
        )
        _attach(
            session,
            link_id="link-a-old",
            claim=claim_a,
            evidence=revised,
            capture=old_capture,
        )
        _attach(
            session,
            link_id="link-b-shared",
            claim=claim_b,
            evidence=shared_b,
            capture=shared_b_capture,
        )
        _attach(
            session,
            link_id="link-other",
            claim=claim_other,
            evidence=legacy,
            capture=None,
        )
        session.commit()
        return {
            "shared_a": shared_a_capture.id,
            "shared_b": shared_b_capture.id,
            "copy_b": copy_b_capture.id,
            "old_capture": old_capture.id,
            "current_capture": revised_current.id,
            "legacy": legacy.id,
            "unknown": unknown.id,
            "short_a": short_a.id,
            "short_b": short_b.id,
        }
    finally:
        session.close()


def group_of(summary: dict, evidence_id: str) -> dict:
    for group in summary["groups"]:
        if any(member["evidence_id"] == evidence_id for member in group["members"]):
            return group
    raise AssertionError(f"{evidence_id} is not in any group")


def member_of(summary: dict, evidence_id: str) -> dict:
    for group in summary["groups"]:
        for member in group["members"]:
            if member["evidence_id"] == evidence_id:
                return member
    raise AssertionError(f"{evidence_id} is not in any group")


class TestUrlNormalization:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (
                "HTTPS://Example.COM:443/a/B/?utm_source=x&utm_medium=y&b=2#frag",
                "https://example.com/a/B/?b=2",
            ),
            ("http://example.com:80", "http://example.com/"),
            (
                "http://example.com:8080/a/?FBCLID=1&GCLID=2&keep=Yes",
                "http://example.com:8080/a/?keep=Yes",
            ),
            ("https://bücher.example/pfad/", "https://xn--bcher-kva.example/pfad/"),
            ("https://example.com/a/", "https://example.com/a/"),
            ("http://example.com/a", "http://example.com/a"),
            ("javascript:alert(1)", None),
            ("ftp://example.com/a", None),
            ("not a url", None),
            ("", None),
            (None, None),
        ],
    )
    def test_canonicalization(self, raw, expected):
        assert normalize_source_url(raw) == expected

    def test_http_and_https_are_not_equated(self):
        assert normalize_source_url("http://example.com/a") != normalize_source_url(
            "https://example.com/a"
        )


class TestIdentityAndFingerprint:
    def test_explicit_publisher_key_wins_and_host_is_provisional(self):
        explicit = resolve_publisher_identity(
            publisher="Meridian Wire",
            source_url="https://wire.example.com/doc",
            metadata_sources=({"publisher_key": "Meridian-Wire"},),
        )
        assert explicit.key == "meridian-wire"
        assert explicit.provisional is False
        assert explicit.host == "wire.example.com"

        provisional = resolve_publisher_identity(
            publisher="Meridian Wire",
            source_url="https://wire.example.com/doc",
            metadata_sources=({},),
        )
        assert provisional.key == "wire.example.com"
        assert provisional.provisional is True

    def test_display_name_alone_stays_unknown(self):
        identity = resolve_publisher_identity(
            publisher="Meridian Wire",
            source_url=None,
            metadata_sources=({},),
        )
        assert identity.key is None
        assert identity.host is None

    def test_short_text_never_produces_a_copy_fingerprint(self):
        fingerprint, count = copy_fingerprint(SHORT_BODY)
        assert fingerprint is None
        assert count < MIN_COPY_NON_WHITESPACE_CODE_POINTS

    def test_fingerprint_requires_200_non_whitespace_code_points(self):
        below = "a" * (MIN_COPY_NON_WHITESPACE_CODE_POINTS - 1)
        at_threshold = "a" * MIN_COPY_NON_WHITESPACE_CODE_POINTS
        assert copy_fingerprint(below)[0] is None
        assert copy_fingerprint(at_threshold)[0] is not None

    def test_fingerprint_collapses_nfkc_case_and_whitespace(self):
        left = copy_fingerprint("STRASSE   " + "x " * 250)
        right = copy_fingerprint("strasse\n" + "X " * 250)
        assert left[0] is not None
        assert left[0] == right[0]


def _member(
    evidence_id: str,
    *,
    publisher_key: str | None = "pub",
    source_url: str | None = None,
    copy: str | None = None,
    case_article_id: str | None = None,
    explicit_origin_key: str | None = None,
) -> SourceMember:
    return SourceMember(
        evidence_id=evidence_id,
        publisher=publisher_key,
        publisher_key=publisher_key,
        publisher_key_provisional=True,
        host=publisher_key,
        origin_url=source_url,
        canonical_url=source_url,
        source_url=source_url,
        case_article_id=case_article_id,
        explicit_origin_key=explicit_origin_key,
        capture_id=f"capture-{evidence_id}",
        capture_kind="live",
        capture_text_sha256=None,
        capture_normalized_text_sha256=None,
        capture_char_length=None,
        recorded_at=None,
        observed_at=None,
        copy_fingerprint=copy,
        copy_non_whitespace_count=MIN_COPY_NON_WHITESPACE_CODE_POINTS,
    )


class TestGroupingDeterminism:
    def test_reordering_input_does_not_change_summary(self):
        members = [
            _member("ev-a", publisher_key="a-pub", source_url="https://a.example/x"),
            _member("ev-b", publisher_key="b-pub", source_url="https://b.example/x"),
            _member("ev-c", publisher_key="copy-pub", copy="copy-hash"),
            _member("ev-d", publisher_key="copy-pub", copy="copy-hash"),
            _member("ev-e", publisher_key=None),
        ]
        first = build_source_summary(
            case_id="case-1",
            scope="case",
            claim_id=None,
            claim_signature=None,
            members=members,
        )
        second = build_source_summary(
            case_id="case-1",
            scope="case",
            claim_id=None,
            claim_signature=None,
            members=list(reversed(members)),
        )
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
        assert first["dependency_group_count"] == 4
        assert first["unknown_publisher_count"] == 1
        assert first["independence_status"] == "dependency_detected"

    def test_documented_origin_and_case_article_edges(self):
        members = [
            _member("ev-a", publisher_key="a", explicit_origin_key="origin-1"),
            _member("ev-b", publisher_key="b", explicit_origin_key="origin-1"),
            _member("ev-c", publisher_key="c", case_article_id="article-1"),
            _member("ev-d", publisher_key="d", case_article_id="article-1"),
        ]
        summary = build_source_summary(
            case_id="case-1",
            scope="case",
            claim_id=None,
            claim_signature=None,
            members=members,
        )
        assert summary["dependency_group_count"] == 2
        assert group_of(summary, "ev-a")["id"] == group_of(summary, "ev-b")["id"]
        assert group_of(summary, "ev-a")["reasons"] == ["documented_common_origin"]
        assert group_of(summary, "ev-c")["id"] == group_of(summary, "ev-d")["id"]
        assert group_of(summary, "ev-c")["reasons"] == ["same_case_article"]

    def test_independence_stays_unknown_without_edges(self):
        summary = build_source_summary(
            case_id="case-1",
            scope="case",
            claim_id=None,
            claim_signature=None,
            members=[_member("ev-a"), _member("ev-b", publisher_key="other")],
        )
        assert summary["independence_status"] == "unknown"
        assert summary["dependency_group_count"] == 2


class TestDatabaseReadModels:
    def test_case_summary_groups_urls_publishers_and_long_copies(self, workbench):
        session = db_session()
        try:
            summary = read_source_summary(session, case_id=CASE_ID)
        finally:
            session.close()
        assert summary is not None
        assert summary["scope"] == "case"
        assert summary["independence_status"] == "dependency_detected"

        shared_group = group_of(summary, "ev-shared-a")
        assert {member["evidence_id"] for member in shared_group["members"]} == {
            "ev-shared-a",
            "ev-shared-b",
            "ev-copy-b",
        }
        assert "same_source_url" in shared_group["reasons"]
        assert "same_publisher" in shared_group["reasons"]
        assert "identical_normalized_capture" in shared_group["reasons"]
        assert "documented_common_origin" in shared_group["reasons"]

        # The explicit publisher key is not provisional and covers both records.
        meridian = next(
            item
            for item in summary["publisher_counts"]
            if item["publisher_key"] == "meridian-wire"
        )
        assert meridian["evidence_count"] == 2
        assert meridian["dependency_group_count"] == 1
        assert meridian["provisional"] is False

        # Short identical snippets never merge different publishers.
        assert group_of(summary, "ev-short-a")["id"] != group_of(
            summary, "ev-short-b"
        )["id"]

        # Unknown identity stays unknown; the legacy item gets a provisional host.
        unknown = member_of(summary, "ev-unknown")
        assert unknown["publisher_key"] is None
        assert unknown["host"] is None
        legacy = member_of(summary, "ev-legacy")
        assert legacy["publisher_key"] == "legacy.example.com"
        assert legacy["publisher_key_provisional"] is True
        assert legacy["capture_id"] is None
        assert legacy["copy_fingerprint"] is None

        assert summary["unknown_publisher_count"] == 1
        assert summary["evidence_count"] == 8
        assert summary["dependency_group_count"] == 6

    def test_claim_scope_uses_only_relevant_evidence_and_link_capture(self, workbench):
        session = db_session()
        try:
            summary = read_source_summary(
                session, case_id=CASE_ID, claim_id="claim-p01-a"
            )
            claim_b = read_source_summary(
                session, case_id=CASE_ID, claim_id="claim-p01-b"
            )
            wrong_case = read_source_summary(
                session, case_id=CASE_ID, claim_id="claim-p01-other"
            )
        finally:
            session.close()

        assert summary is not None
        assert summary["scope"] == "claim"
        assert summary["claim_id"] == "claim-p01-a"
        assert summary["claim_signature"]
        ids = {
            member["evidence_id"]
            for group in summary["groups"]
            for member in group["members"]
        }
        assert ids == {"ev-shared-a", "ev-copy-b", "ev-revised"}
        # The claim link names the older capture; the case summary uses current.
        assert member_of(summary, "ev-revised")["capture_id"] == workbench[
            "old_capture"
        ]
        case_summary = read_source_summary(session, case_id=CASE_ID)
        assert case_summary is not None
        assert member_of(case_summary, "ev-revised")["capture_id"] == workbench[
            "current_capture"
        ]

        # Claim B links only shared-b, so it must not inherit the case-wide copy.
        assert claim_b is not None
        assert {
            member["evidence_id"]
            for group in claim_b["groups"]
            for member in group["members"]
        } == {"ev-shared-b"}
        assert claim_b["independence_status"] == "unknown"

        assert wrong_case is None

    def test_unknown_case_is_none(self, workbench):
        session = db_session()
        try:
            assert read_source_summary(session, case_id="missing") is None
        finally:
            session.close()

    def test_get_reads_create_nothing(self, workbench):
        session = db_session()
        try:
            before = {
                "evidence": session.scalar(
                    select(func.count()).select_from(EvidenceItem)
                ),
                "captures": session.scalar(
                    select(func.count()).select_from(EvidenceCapture)
                ),
                "links": session.scalar(
                    select(func.count()).select_from(ClaimEvidenceLink)
                ),
            }
            first = read_source_summary(session, case_id=CASE_ID)
            second = read_source_summary(session, case_id=CASE_ID)
            after = {
                "evidence": session.scalar(
                    select(func.count()).select_from(EvidenceItem)
                ),
                "captures": session.scalar(
                    select(func.count()).select_from(EvidenceCapture)
                ),
                "links": session.scalar(
                    select(func.count()).select_from(ClaimEvidenceLink)
                ),
            }
        finally:
            session.close()
        assert first == second
        assert before == after


@pytest.fixture
def client(workbench, tmp_path):
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
    app.dependency_overrides[get_case_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


class TestHttpContract:
    def test_case_summary_contract(self, client):
        response = client.get(f"/api/cases/{CASE_ID}/sources")
        assert response.status_code == 200
        payload = response.json()
        assert payload["caseId"] == CASE_ID
        assert payload["scope"] == "case"
        assert payload["claimId"] is None
        assert payload["policy"]["version"] == "source-dependency-policy-v1"
        assert payload["policy"]["minCopyNonWhitespaceCodePoints"] == 200
        assert payload["dependencyGroupCount"] == 6
        assert payload["distinctPublisherCount"] == 6
        assert payload["unknownPublisherCount"] == 1
        assert payload["independenceStatus"] == "dependency_detected"
        assert payload["groups"]
        member = payload["groups"][0]["members"][0]
        assert "evidenceId" in member
        assert "publisherKeyProvisional" in member
        assert "dependencyReasons" in member

    def test_claim_selector_camel_snake_and_conflict(self, client):
        camel = client.get(
            f"/api/cases/{CASE_ID}/sources", params={"claimId": "claim-p01-a"}
        )
        snake = client.get(
            f"/api/cases/{CASE_ID}/sources", params={"claim_id": "claim-p01-a"}
        )
        assert camel.status_code == 200
        assert snake.status_code == 200
        assert camel.json()["scope"] == "claim"
        assert camel.json()["claimId"] == "claim-p01-a"
        assert camel.json() == snake.json()

        conflict = client.get(
            f"/api/cases/{CASE_ID}/sources",
            params={"claimId": "claim-p01-a", "claim_id": "claim-p01-b"},
        )
        assert conflict.status_code == 422

    def test_unknown_case_and_claim_are_404(self, client):
        assert client.get("/api/cases/missing/sources").status_code == 404
        assert (
            client.get(
                f"/api/cases/{CASE_ID}/sources",
                params={"claimId": "missing"},
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/cases/{CASE_ID}/sources",
                params={"claimId": "claim-p01-other"},
            ).status_code
            == 404
        )

    def test_empty_case_is_a_valid_empty_summary(self, client, tmp_path):
        session = db_session()
        try:
            _add_case(session, "case-p01-empty", "Empty case")
            session.commit()
        finally:
            session.close()
        response = client.get("/api/cases/case-p01-empty/sources")
        assert response.status_code == 200
        payload = response.json()
        assert payload["evidenceCount"] == 0
        assert payload["dependencyGroupCount"] == 0
        assert payload["distinctPublisherCount"] == 0
        assert payload["unknownPublisherCount"] == 0
        assert payload["independenceStatus"] == "unknown"
        assert payload["groups"] == []
        assert payload["publisherCounts"] == []

    def test_no_mutation_routes_for_sources(self, client):
        for method in ("post", "put", "patch", "delete"):
            response = getattr(client, method)(f"/api/cases/{CASE_ID}/sources")
            assert response.status_code in {404, 405}
