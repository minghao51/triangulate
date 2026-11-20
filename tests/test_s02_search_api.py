"""S02: case-scoped search read API (specification §8).

Everything here runs against a temporary database and synthetic text. The seed
rows go through the S01 index helpers, so the tests exercise the real FTS5 index
and the real HTTP app that the other read-API tests use. No model, network or
source-capture call is made and no timing is asserted.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import src.storage.search as storage_search
from src.cases.search import (
    MAX_QUERY_CODE_POINTS,
    MAX_SEARCH_OFFSET,
    build_match_expression,
    escape_fts_term,
    read_case_search,
    tokenize_terms,
)
from src.cases.service import TopicCaseService
from src.http.app import app
from src.http.dependencies import get_case_service
from src.storage import (
    CaseStatus,
    Claim,
    Event,
    EvidenceItem,
    TopicCase,
    VerificationStatus,
    get_database,
    init_database,
)
from src.storage.captures import record_evidence_capture
from src.storage.migrations import run_migrations
from src.storage.search import sync_event_index

CASE_ID = "case-s02"
OTHER_CASE_ID = "case-s02-other"
EMPTY_CASE_ID = "case-s02-empty"
EVENT_ID = "event-s02"
OTHER_EVENT_ID = "event-s02-other"

LONG_BOUNDARY_TERM = "boundary" + "x" * 248

ALPHA_BODY = (
    "The council approved the harbour levy after the second reading. "
    "Quartz surveys were cited in the annex. A quoted amber lantern was displayed."
)
BETA_BODY = (
    "Storm damage closed the north pier overnight; the council said quartz "
    "inspections continue through the week."
)
GAMMA_BODY = (
    "An operator note reads: the quoted phrase and 100% * 3 - 4 : 5 ; "
    'DROP TABLE claims; -- trailing " text. Quartz appears once here and the '
    "note is undated. Amber drifted through the report before lantern appeared. "
    + LONG_BOUNDARY_TERM
)
OTHER_BODY = (
    "A tungsten assay is reported elsewhere and does not belong to this case."
)


def db_session():
    return get_database().get_session_sync()


def _add_case(session, case_id: str, query: str) -> None:
    session.add(
        TopicCase(
            id=case_id,
            query=query,
            slug=f"{case_id}-slug",
            conflict="Harbour levy",
            status=CaseStatus.REVIEW_READY,
            metadata_json={},
        )
    )


def _add_event(session, event_id: str, case_id: str, title: str) -> Event:
    event = Event(
        id=event_id,
        timestamp=datetime(2026, 3, 3, 6, 30, tzinfo=UTC),
        title=title,
        summary="Synthetic event",
        verification_status=VerificationStatus.ALLEGED,
        case_id=case_id,
    )
    session.add(event)
    return event


def _add_claim(
    session,
    claim_id: str,
    event_id: str,
    claim_text: str,
    status: VerificationStatus = VerificationStatus.ALLEGED,
) -> Claim:
    claim = Claim(
        id=claim_id,
        event_id=event_id,
        claim_text=claim_text,
        verification_status=status,
        claim_signature=f"sig-{claim_id}",
    )
    session.add(claim)
    return claim


def _add_evidence(
    session,
    *,
    evidence_id: str,
    case_id: str,
    event_id: str | None,
    publisher: str,
    title: str,
    body: str,
    published_at: str,
) -> EvidenceItem:
    evidence = EvidenceItem(
        id=evidence_id,
        case_id=case_id,
        event_id=event_id,
        evidence_type="article",
        source_type="rss",
        title=title,
        origin_url=f"https://{evidence_id}.example.com/story",
        canonical_url=f"https://{evidence_id}.example.com/story",
        publisher=publisher,
        published_at=published_at,
        capture_metadata={},
        verification_status="UNVERIFIED",
        credibility_tier="unknown",
        requires_human_review=0,
    )
    session.add(evidence)
    session.flush()
    record_evidence_capture(session, evidence, text=body)
    return evidence


def seed_search(tmp_path) -> dict[str, str]:
    """Seed two cases (plus one empty case) and synchronize the FTS index."""
    db_path = str(tmp_path / "s02-search.sqlite3")
    init_database(db_path)
    # Migration 15 creates the additive FTS5 virtual table; the ORM metadata
    # alone does not, exactly like a fresh deployment.
    run_migrations(db_path)
    session = db_session()
    try:
        _add_case(session, CASE_ID, "Harbour levy search")
        _add_case(session, OTHER_CASE_ID, "Other case search")
        _add_case(session, EMPTY_CASE_ID, "Empty case search")
        session.flush()
        _add_event(session, EVENT_ID, CASE_ID, "Harbour briefing")
        _add_event(session, OTHER_EVENT_ID, OTHER_CASE_ID, "Other briefing")
        session.flush()

        alpha = _add_evidence(
            session,
            evidence_id="ev-alpha",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Meridian Wire",
            title="Harbour levy briefing",
            body=ALPHA_BODY,
            published_at="2026-03-03T06:00:00+00:00",
        )
        beta = _add_evidence(
            session,
            evidence_id="ev-beta",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Northern Post",
            title="Pier closure report",
            body=BETA_BODY,
            published_at="2026-03-05T12:00:00+00:00",
        )
        gamma = _add_evidence(
            session,
            evidence_id="ev-gamma",
            case_id=CASE_ID,
            event_id=EVENT_ID,
            publisher="Meridian Wire",
            title="Undated wire note",
            body=GAMMA_BODY,
            published_at="",
        )
        other = _add_evidence(
            session,
            evidence_id="ev-other",
            case_id=OTHER_CASE_ID,
            event_id=OTHER_EVENT_ID,
            publisher="Other Wire",
            title="Tungsten note",
            body=OTHER_BODY,
            published_at="2026-03-04T00:00:00+00:00",
        )
        assert {alpha.id, beta.id, gamma.id, other.id}

        _add_claim(
            session,
            "claim-quartz-1",
            EVENT_ID,
            "Quartz surveys were cited at the harbour levy reading",
            VerificationStatus.ALLEGED,
        )
        _add_claim(
            session,
            "claim-quartz-2",
            EVENT_ID,
            "Quartz claim that the council approved the levy",
            VerificationStatus.CONFIRMED,
        )
        # Inserted deliberately out of id order: the tie-break must be
        # (resultType, id), not insertion/rowid order.
        _add_claim(
            session,
            "claim-tie-b",
            EVENT_ID,
            "Tiebreak zircon statement",
            VerificationStatus.CONTESTED,
        )
        _add_claim(
            session,
            "claim-tie-a",
            EVENT_ID,
            "Tiebreak zircon statement",
            VerificationStatus.CONTESTED,
        )
        _add_claim(
            session,
            "claim-other",
            OTHER_EVENT_ID,
            "Tungsten other case claim",
            VerificationStatus.ALLEGED,
        )
        session.flush()
        sync_event_index(session, EVENT_ID)
        sync_event_index(session, OTHER_EVENT_ID)
        session.commit()
        capture = session.execute(
            text("SELECT id, current_capture_id FROM evidence_items WHERE id='ev-alpha'")
        ).first()
        assert capture is not None and capture[1]
        return {
            "alpha_capture": capture[1],
        }
    finally:
        session.close()


@pytest.fixture
def seeded(tmp_path):
    return seed_search(tmp_path)


@pytest.fixture
def client(seeded, tmp_path):
    service = TopicCaseService({"ai": {"model": "test-model"}}, output_root=tmp_path)
    app.dependency_overrides[get_case_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def search(client, **params):
    return client.get(f"/api/cases/{CASE_ID}/search", params=params)


def ids(payload: dict) -> list[str]:
    return [item["id"] for item in payload["items"]]


def _index_dump() -> tuple[tuple, ...]:
    session = db_session()
    try:
        return tuple(
            tuple(row)
            for row in session.execute(
                text(
                    "SELECT case_id, entity_type, entity_id, title, body, "
                    "signature, event_id, party_id, publisher, status, "
                    "published_at FROM case_search_index "
                    "ORDER BY case_id, entity_type, entity_id"
                )
            )
        )
    finally:
        session.close()


class TestQueryInterpretation:
    def test_tokenizer_and_escaping_are_literal(self):
        assert tokenize_terms("council harbour") == ["council", "harbour"]
        assert tokenize_terms('"quoted phrase"') == ["quoted", "phrase"]
        assert tokenize_terms("AND OR NEAR(a b)") == ["AND", "OR", "NEAR", "a", "b"]
        assert tokenize_terms("body:quartz") == ["body", "quartz"]
        assert tokenize_terms("* - : ; ( ) { } [ ]") == []
        assert tokenize_terms("café") == ["café"]
        assert tokenize_terms("Quartz quartz QUARTZ") == ["Quartz"]
        assert build_match_expression(["a", "b"]) == '"a" AND "b"'
        # Internal quotes are doubled, so a term can never close our literal.
        assert escape_fts_term('a"b') == '"a""b"'

    def test_two_term_query_requires_both_terms(self, client):
        response = search(client, q="council harbour")
        assert response.status_code == 200
        payload = response.json()
        # Only ev-alpha contains both terms; a document with one term each in
        # title and body still has to satisfy every term.
        assert ids(payload) == ["ev-alpha"]
        assert payload["total"] == 1

    def test_quoted_phrase_is_terms_not_fts_phrase(self, client):
        # The terms are non-adjacent in gamma and adjacent in alpha. Both
        # orderings must perform literal AND-of-terms matching, not phrase search.
        forward = search(client, q='"amber lantern"')
        reverse = search(client, q='"lantern amber"')
        assert forward.status_code == reverse.status_code == 200
        assert set(ids(forward.json())) == {"ev-alpha", "ev-gamma"}
        assert set(ids(reverse.json())) == {"ev-alpha", "ev-gamma"}

    @pytest.mark.parametrize(
        "query",
        [
            "*",
            "-",
            ":",
            '"',
            "()",
            ";;;",
            "***",
        ],
    )
    def test_operator_only_queries_are_422_not_a_scan(self, client, query):
        response = search(client, q=query)
        assert response.status_code == 422
        assert "no searchable word terms" in response.text

    def test_and_is_a_literal_word_not_an_operator(self, client):
        response = search(client, q="AND")
        assert response.status_code == 200
        # Literal all-term: only the document containing the word "and" matches.
        # A raw FTS "AND" would be a syntax error or an empty operator query.
        assert ids(response.json()) == ["ev-gamma"]

    @pytest.mark.parametrize(
        "query",
        ["OR", "NEAR(", "AND OR NEAR(", "body:quartz", '"a" AND "b"', "NOT quartz"],
    )
    def test_raw_fts_operators_cannot_escape_semantics(self, client, query):
        response = search(client, q=query)
        assert response.status_code == 200
        # Nothing in the corpus contains the literal operator tokens as words.
        assert response.json()["total"] == 0
        assert response.json()["items"] == []

    def test_sql_like_input_is_literal_and_never_500(self, client):
        before = _index_dump()
        for query in (
            "'); DROP TABLE claims;--",
            "claims WHERE 1=1 --",
            "quartz' OR '1'='1",
            "'; UPDATE case_search_index SET body='x'; --",
        ):
            response = search(client, q=query)
            assert response.status_code in {200, 422}
            assert response.status_code != 500
        assert _index_dump() == before
        session = db_session()
        try:
            assert session.execute(text("SELECT count(*) FROM claims")).scalar() >= 1
        finally:
            session.close()

    def test_length_and_emptiness_validation(self, client):
        assert search(client, q="   ").status_code == 422
        assert search(client, q="").status_code == 422
        assert search(client).status_code == 422
        over = "a " * (MAX_QUERY_CODE_POINTS // 2 + 1)
        assert len(over.strip()) > MAX_QUERY_CODE_POINTS
        response = search(client, q=over)
        assert response.status_code == 422
        assert "at most 256 code points" in response.text
        assert len(LONG_BOUNDARY_TERM) == MAX_QUERY_CODE_POINTS
        boundary = search(client, q=LONG_BOUNDARY_TERM)
        assert boundary.status_code == 200
        assert ids(boundary.json()) == ["ev-gamma"]
        assert boundary.json()["total"] == 1
        assert search(client, q=LONG_BOUNDARY_TERM + "x").status_code == 422


class TestFilters:
    def test_type_filter_narrows(self, client):
        evidence_only = search(client, q="quartz", type="evidence")
        claim_only = search(client, q="quartz", type="claim")
        assert evidence_only.status_code == 200
        assert claim_only.status_code == 200
        assert set(ids(evidence_only.json())) == {"ev-alpha", "ev-beta", "ev-gamma"}
        assert set(ids(claim_only.json())) == {"claim-quartz-1", "claim-quartz-2"}
        assert all(
            item["resultType"] == "evidence" for item in evidence_only.json()["items"]
        )
        assert evidence_only.json()["appliedFilters"]["type"] == "evidence"

    def test_publisher_filter_is_exact_and_evidence_only(self, client):
        response = search(client, q="quartz", publisher="Meridian Wire")
        assert response.status_code == 200
        assert set(ids(response.json())) == {"ev-alpha", "ev-gamma"}
        assert response.json()["total"] == 2
        assert response.json()["appliedFilters"]["publisher"] == "Meridian Wire"

        # Exact key: no prefix/substring matching.
        partial = search(client, q="quartz", publisher="Meridian")
        assert partial.status_code == 200
        assert partial.json()["total"] == 0

        # Publisher applies to evidence only; an explicit claim type conflicts.
        conflict = search(client, q="quartz", publisher="Meridian Wire", type="claim")
        assert conflict.status_code == 422

    def test_status_filter_narrows_to_claims(self, client):
        response = search(client, q="quartz", status="alleged")
        assert response.status_code == 200
        payload = response.json()
        assert ids(payload) == ["claim-quartz-1"]
        # A status filter without type narrows to claims and says so.
        assert payload["appliedFilters"] == {
            "type": "claim",
            "publisher": None,
            "status": "alleged",
            "publishedFrom": None,
            "publishedTo": None,
        }
        explicit = search(client, q="quartz", status="alleged", type="claim")
        assert ids(explicit.json()) == ["claim-quartz-1"]

    def test_publisher_validation_uses_effective_result_type(self, client):
        status_conflict = search(
            client, q="quartz", status="alleged", publisher="Meridian Wire"
        )
        assert status_conflict.status_code == 422

        evidence_and_publisher = search(
            client, q="quartz", type="evidence", publisher="Meridian Wire"
        )
        assert evidence_and_publisher.status_code == 200
        assert set(ids(evidence_and_publisher.json())) == {"ev-alpha", "ev-gamma"}

        publisher_alone = search(client, q="quartz", publisher="Meridian Wire")
        assert publisher_alone.status_code == 200
        assert set(ids(publisher_alone.json())) == {"ev-alpha", "ev-gamma"}

        status_with_evidence = search(
            client, q="quartz", status="alleged", type="evidence"
        )
        assert status_with_evidence.status_code == 422

    def test_status_with_evidence_type_is_422(self, client):
        response = search(client, q="quartz", status="alleged", type="evidence")
        assert response.status_code == 422
        assert "claim results only" in response.text

    def test_status_unknown_label_matches_nothing_not_an_error(self, client):
        response = search(client, q="quartz", status="unknown")
        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_date_filters_exclude_unknown_dates(self, client):
        unfiltered = search(client, q="quartz", type="evidence")
        assert unfiltered.json()["total"] == 3  # includes the undated row

        from_only = search(
            client, q="quartz", type="evidence", publishedFrom="2026-03-04T00:00:00Z"
        )
        assert from_only.status_code == 200
        assert ids(from_only.json()) == ["ev-beta"]

        to_only = search(
            client, q="quartz", type="evidence", publishedTo="2026-03-04T00:00:00Z"
        )
        assert ids(to_only.json()) == ["ev-alpha"]

        both = search(
            client,
            q="quartz",
            type="evidence",
            publishedFrom="2026-03-01T00:00:00Z",
            publishedTo="2026-03-31T00:00:00Z",
        )
        # Order is rank-first; the undated row is excluded by the range.
        assert set(ids(both.json())) == {"ev-alpha", "ev-beta"}
        assert both.json()["total"] == 2
        assert both.json()["appliedFilters"]["publishedFrom"] == (
            "2026-03-01T00:00:00+00:00"
        )

    def test_date_bounds_are_start_inclusive_end_exclusive(self, client):
        inclusive = search(
            client,
            q="harbour",
            type="evidence",
            publishedFrom="2026-03-03T06:00:00Z",
        )
        assert ids(inclusive.json()) == ["ev-alpha"]
        exclusive = search(
            client,
            q="harbour",
            type="evidence",
            publishedTo="2026-03-03T06:00:00Z",
        )
        assert exclusive.status_code == 200
        assert exclusive.json()["items"] == []
        assert exclusive.json()["total"] == 0

    def test_offsets_are_converted_to_utc(self, client):
        # 13:00+01:00 is the same instant as 12:00Z, the publication time of
        # ev-beta: the start bound is inclusive, the end bound exclusive.
        inclusive = search(
            client,
            q="quartz",
            type="evidence",
            publishedFrom="2026-03-05T13:00:00+01:00",
        )
        assert inclusive.status_code == 200
        assert inclusive.json()["appliedFilters"]["publishedFrom"] == (
            "2026-03-05T12:00:00+00:00"
        )
        assert ids(inclusive.json()) == ["ev-beta"]

        exclusive = search(
            client,
            q="quartz",
            type="evidence",
            publishedTo="2026-03-05T13:00:00+01:00",
        )
        assert exclusive.json()["appliedFilters"]["publishedTo"] == (
            "2026-03-05T12:00:00+00:00"
        )
        assert ids(exclusive.json()) == ["ev-alpha"]


class TestPaginationAndOrdering:
    def test_pages_partition_the_total_without_gaps(self, client):
        full = search(client, q="quartz", limit=100)
        assert full.status_code == 200
        total = full.json()["total"]
        assert total == 5
        collected: list[str] = []
        for offset in range(0, total, 2):
            page = search(client, q="quartz", limit=2, offset=offset)
            assert page.status_code == 200
            assert page.json()["total"] == total
            assert page.json()["limit"] == 2
            assert page.json()["offset"] == offset
            collected.extend(ids(page.json()))
        assert len(collected) == total
        assert len(set(collected)) == total
        assert collected == ids(full.json())

    def test_identical_requests_return_identical_order(self, client):
        first = search(client, q="quartz", limit=2, offset=0).json()
        repeat = search(client, q="quartz", limit=2, offset=0).json()
        assert first == repeat
        beyond = search(client, q="quartz", limit=2, offset=99).json()
        assert beyond["items"] == []
        assert beyond["total"] == 5

    def test_rank_then_result_type_and_id_tie_break(self, client):
        response = search(client, q="zircon")
        assert response.status_code == 200
        payload = response.json()
        # Identical documents tie on bm25, so the deterministic (resultType, id)
        # tie-break decides — not insertion order.
        assert ids(payload) == ["claim-tie-a", "claim-tie-b"]

    def test_default_page_size_and_limit_bounds(self, client):
        default = search(client, q="quartz")
        assert default.json()["limit"] == 25
        assert default.json()["offset"] == 0
        assert search(client, q="quartz", limit=101).status_code == 422
        assert search(client, q="quartz", limit=0).status_code == 422
        assert search(client, q="quartz", offset=-1).status_code == 422

    def test_offset_upper_bound_is_422_and_maximum_is_safe(self, client):
        too_large = search(client, q="not-present", offset=MAX_SEARCH_OFFSET + 1)
        assert too_large.status_code == 422

        at_maximum = search(client, q="not-present", offset=MAX_SEARCH_OFFSET)
        assert at_maximum.status_code == 200
        assert at_maximum.json()["offset"] == MAX_SEARCH_OFFSET
        assert at_maximum.json()["items"] == []


class TestOwnershipAndFailureStates:
    def test_unknown_case_is_404(self, client):
        response = client.get("/api/cases/case-does-not-exist/search", params={"q": "quartz"})
        assert response.status_code == 404
        assert "not found" in response.text

    def test_case_without_matching_resources_is_empty_200(self, client):
        # A valid case with no indexed resources is an honest empty result, not
        # a 404 and never another case's rows.
        response = client.get(
            f"/api/cases/{EMPTY_CASE_ID}/search", params={"q": "quartz"}
        )
        assert response.status_code == 200
        assert response.json()["total"] == 0
        assert response.json()["items"] == []

    def test_wrong_case_terms_never_leak(self, client):
        foreign = client.get(
            f"/api/cases/{OTHER_CASE_ID}/search", params={"q": "tungsten"}
        )
        assert foreign.status_code == 200
        assert foreign.json()["total"] == 2
        assert set(ids(foreign.json())) == {"ev-other", "claim-other"}

        scoped = search(client, q="tungsten")
        assert scoped.status_code == 200
        assert scoped.json()["total"] == 0
        assert scoped.json()["items"] == []
        assert "ev-other" not in scoped.text
        assert "claim-other" not in scoped.text

    def test_invalid_filters_and_ranges_are_422(self, client):
        assert search(client, q="quartz", type="claim|evidence").status_code == 422
        assert search(client, q="quartz", status="bogus").status_code == 422
        assert search(client, q="quartz", status="").status_code == 422
        assert search(client, q="quartz", publisher="").status_code == 422
        assert search(client, q="quartz", publishedFrom="not-a-date").status_code == 422
        assert search(client, q="quartz", publishedTo="2026-13-40").status_code == 422
        assert search(client, q="quartz", publishedFrom=" ").status_code == 422
        reversed_range = search(
            client,
            q="quartz",
            publishedFrom="2026-04-01T00:00:00Z",
            publishedTo="2026-03-01T00:00:00Z",
        )
        assert reversed_range.status_code == 422
        assert "must not be after" in reversed_range.text

    def test_unavailable_index_is_503_with_cli_remedy(self, client, monkeypatch):
        def unavailable(_session):
            return False

        assert search(client, q="quartz").status_code == 200
        with monkeypatch.context() as absent:
            absent.setattr(storage_search, "_fts5_module_available", unavailable)
            response = search(client, q="quartz")
            assert response.status_code == 503
            assert f"triangulate case rebuild-search {CASE_ID}" in response.text
            assert "SQLite FTS5 module is not compiled" in response.text
            # Never an empty 200 fallback and no partial result payload.
            assert "items" not in response.json()

            # Unknown cases still 404 before the capability state is reported.
            missing = client.get(
                "/api/cases/case-does-not-exist/search", params={"q": "quartz"}
            )
            assert missing.status_code == 404

        assert search(client, q="quartz").status_code == 200

    def test_missing_index_table_is_also_503(self, client):
        session = db_session()
        try:
            session.execute(text("DROP TABLE case_search_index"))
            session.commit()
        finally:
            session.close()
        response = search(client, q="quartz")
        assert response.status_code == 503
        assert "migration 15 is not applied" in response.text
        assert f"triangulate case rebuild-search {CASE_ID}" in response.text


class TestItemShapeAndSnippets:
    def test_items_carry_typed_ids_and_plain_text_snippets(
        self, client, seeded
    ):
        response = search(client, q="quartz", limit=100)
        assert response.status_code == 200
        payload = response.json()
        assert "<mark>" not in response.text
        assert "<em>" not in response.text
        html_free = payload["items"]
        assert html_free

        by_id = {item["id"]: item for item in payload["items"]}
        alpha = by_id["ev-alpha"]
        assert alpha["resultType"] == "evidence"
        assert alpha["evidenceId"] == "ev-alpha"
        assert alpha["claimId"] is None
        assert alpha["eventId"] == EVENT_ID
        assert alpha["captureId"] == seeded["alpha_capture"]
        assert alpha["title"] == "Harbour levy briefing"
        assert alpha["publisher"] == "Meridian Wire"
        assert alpha["status"] is None
        assert alpha["publishedAt"] == "2026-03-03T06:00:00+00:00"
        assert alpha["matchedField"] == "body"
        assert "quartz" in alpha["snippet"].lower()
        assert "Quartz surveys were cited" in alpha["snippet"]

        gamma = by_id["ev-gamma"]
        assert gamma["captureId"] is not None
        # An unknown stored publication time stays null, it is never invented.
        assert gamma["publishedAt"] is None

        claim = by_id["claim-quartz-2"]
        assert claim["resultType"] == "claim"
        assert claim["claimId"] == "claim-quartz-2"
        assert claim["evidenceId"] is None
        assert claim["captureId"] is None
        assert claim["title"] is None
        assert claim["publisher"] is None
        assert claim["status"] == "confirmed"
        assert claim["publishedAt"] is None
        assert claim["eventId"] == EVENT_ID
        assert claim["matchedField"] == "body"
        assert "quartz" in claim["snippet"].lower()

    def test_matched_field_is_derived_from_the_matched_terms(self, client):
        title_match = search(client, q="harbour levy", type="evidence")
        assert title_match.status_code == 200
        item = title_match.json()["items"][0]
        assert item["id"] == "ev-alpha"
        assert item["matchedField"] == "title"
        assert "Harbour levy briefing" in item["snippet"]

        body_match = search(client, q="annex", type="evidence")
        assert body_match.status_code == 200
        assert body_match.json()["items"][0]["matchedField"] == "body"

    def test_empty_result_shape(self, client):
        response = search(client, q="tungsten")
        payload = response.json()
        assert response.status_code == 200
        assert payload["caseId"] == CASE_ID
        assert payload["query"] == "tungsten"
        assert payload["total"] == 0
        assert payload["items"] == []
        assert payload["appliedFilters"] == {
            "type": None,
            "publisher": None,
            "status": None,
            "publishedFrom": None,
            "publishedTo": None,
        }


class TestReadOnlyBoundary:
    def test_get_batch_never_writes_the_index(self, client, monkeypatch):
        before = _index_dump()

        def forbidden(*_args, **_kwargs):
            raise AssertionError("a GET must not rebuild or synchronize the index")

        for name in (
            "rebuild_case_search_index",
            "sync_event_index",
            "sync_evidence_index",
            "upsert_index_row",
            "delete_index_row",
        ):
            monkeypatch.setattr(storage_search, name, forbidden)

        responses = [
            search(client, q="quartz"),
            search(client, q="quartz", type="claim", status="alleged"),
            search(client, q="quartz", publisher="Meridian Wire"),
            search(client, q="quartz", publishedFrom="2026-03-01T00:00:00Z"),
            search(client, q="*"),
            search(client, q="quartz", limit=101),
            client.get("/api/cases/case-does-not-exist/search", params={"q": "x"}),
        ]
        assert [response.status_code for response in responses] == [
            200,
            200,
            200,
            200,
            422,
            422,
            404,
        ]
        assert _index_dump() == before

    def test_reader_is_session_in_and_read_only(self, seeded):
        session = db_session()
        try:
            before = _index_dump()
            payload = read_case_search(session, case_id=CASE_ID, q="quartz")
            assert payload["total"] == 5
            assert _index_dump() == before
            assert not session.new and not session.dirty
        finally:
            session.close()

    def test_snapshot_selector_is_rejected_explicitly(self, client):
        # Search reads current indexed state only; a caller must never believe
        # it pinned a historical observation.
        response = client.get(
            f"/api/cases/{CASE_ID}/search",
            params={"q": "quartz", "snapshotId": "snap-1"},
        )
        assert response.status_code == 422
        assert "does not support snapshot selection" in response.text

    def test_query_echo_is_the_trimmed_query(self, client):
        response = search(client, q="  quartz  ")
        assert response.status_code == 200
        assert response.json()["query"] == "quartz"

    def test_no_mutation_route_for_search(self, client):
        for method in ("post", "put", "patch", "delete"):
            response = getattr(client, method)(
                f"/api/cases/{CASE_ID}/search", params={"q": "quartz"}
            )
            assert response.status_code in {404, 405}
