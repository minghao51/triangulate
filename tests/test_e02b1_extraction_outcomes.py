"""E02 pass B1: honest collector extraction outcomes and real analysis scope.

Covers specification §4 "Quotation and relationship contract" for the collector
size of the seam:

* optional quote proposals on ``ClaimSchema`` (old payloads still validate);
* a *required* ``claims`` key, so an absent/malformed payload can never be
  mistaken for a validated empty collection;
* the recorded analysis scope is the exact body region supplied to the model
  (a prefix when truncated), measured on the LF-normalized body, with the title
  excluded so a headline sentence can never validate a body passage;
* the honest outcome statuses (``valid | empty | fallback | unavailable``) and a
  ``quote_proposals_trusted`` flag that is only ever true for a real validated
  structured parse;
* the existing agent envelope/return contracts are unchanged.

Everything here is offline: no provider, network or database access.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from src.ai.agents import collector as collector_module
from src.ai.agents.collector import (
    COLLECTOR_CONTENT_LIMIT,
    AnalysisWindow,
    _analysis_input,
    _normalize_body,
    collect_claims,
)
from src.ai.schemas import (
    ClaimCollectionSchema,
    ClaimSchema,
    ExtractionOutcomeSchema,
    ExtractionStatus,
)
from src.ai.workflow import AIWorkflow
from src.ai.workflow import (
    _collector_outcome,
)  # noqa: PLC2701 - deliberate: the compat path is the behaviour under test
from src.ai.workflows import party_investigation_workflow as party_flow_module
from src.ai.workflows.party_investigation_workflow import collector_node
from src.storage.captures import normalize_capture_text
from src.storage.citations import AnalysisScope, QuoteProposal, validate_quote_alignment

ARTICLE: dict[str, Any] = {
    "title": "Test Article",
    "content": "The US and Iran are in conflict over a disputed strait.",
    "timestamp": "2026-02-01T00:00:00+00:00",
    "link": "https://example.com/a1",
    "source_name": "example",
}

ONE_CLAIM: dict[str, Any] = {
    "claim": "The US and Iran are in conflict",
    "who": ["US", "Iran"],
    "when": "",
    "where": "",
    "confidence": "HIGH",
}


def _ok_envelope(claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Minimal envelope shape returned by ``call_structured_llm`` on success."""
    return {
        "output": {"claims": claims},
        "parse_status": "ok",
        "structured_output_used": True,
        "fallback_used": False,
        "raw_response_excerpt": "",
    }


def _fallback_envelope(claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Envelope shape returned by ``call_structured_llm`` when parsing failed."""
    return {
        "output": {"claims": claims},
        "parse_status": "fallback",
        "structured_output_used": True,
        "fallback_used": True,
        "raw_response_excerpt": "",
    }


async def _collect_envelope(
    article: dict[str, Any], *, include_metadata: bool = True
) -> dict[str, Any]:
    """Call the collector in metadata mode, narrowing the union return type."""
    result = await collect_claims(article, include_metadata=include_metadata)
    assert isinstance(result, dict)
    return result


def _collector_envelope(
    claims: list[dict[str, Any]],
    *,
    status: ExtractionStatus,
    trusted: bool = False,
    scope_end: int = 0,
    body_char_count: int = 0,
) -> dict[str, Any]:
    """A collector envelope carrying an explicit ``extraction_outcome``."""
    envelope = _ok_envelope(claims)
    envelope["extraction_outcome"] = ExtractionOutcomeSchema(
        status=status,
        quote_proposals_trusted=trusted,
        scope_start=0,
        scope_end=scope_end,
        body_char_count=body_char_count,
        input_limit=COLLECTOR_CONTENT_LIMIT,
        source_available=bool(body_char_count),
        reason="",
    ).model_dump()
    return envelope


async def _patch_parties_and_clustering(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the downstream agents so only the collector outcome is under test."""

    async def fake_classify_parties(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"parties": []}

    async def fake_cluster_claims(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"clusters": {}}

    monkeypatch.setattr(
        "src.ai.workflow.classify_parties", fake_classify_parties
    )
    monkeypatch.setattr("src.ai.workflow.cluster_claims", fake_cluster_claims)


# ---------------------------------------------------------------------------
# 1. Optional quotation proposals on ClaimSchema
# ---------------------------------------------------------------------------


def test_claim_schema_accepts_legacy_payload_without_quote_fields():
    claim = ClaimSchema.model_validate(
        {
            "claim": "A legacy claim",
            "who": ["Entity A"],
            "when": "March 1st",
            "where": "Berlin",
            "confidence": "HIGH",
        }
    )

    assert claim.source_quote is None
    assert claim.source_quote_start is None
    assert claim.source_quote_end is None


def test_claim_schema_round_trips_quote_and_offsets():
    payload = {
        "claim": "A claim with a quotation",
        "who": ["Entity A"],
        "when": "March 1st",
        "where": "Berlin",
        "confidence": "MEDIUM",
        "source_quote": "exact body passage",
        "source_quote_start": 7,
        "source_quote_end": 25,
    }

    assert ClaimSchema.model_validate(payload).model_dump() == payload


# ---------------------------------------------------------------------------
# 2. ``claims`` is required: absent is not a validated empty result
# ---------------------------------------------------------------------------


def test_claim_collection_rejects_a_missing_claims_key():
    with pytest.raises(ValidationError):
        ClaimCollectionSchema.model_validate({})
    with pytest.raises(ValidationError):
        # A well-formed object that simply lacks the required key.
        ClaimCollectionSchema.model_validate({"items": []})


def test_claim_collection_accepts_an_explicit_empty_list():
    collection = ClaimCollectionSchema.model_validate({"claims": []})

    assert collection.claims == []
    assert collection.model_dump() == {"claims": []}


# ---------------------------------------------------------------------------
# 3. The recorded scope is the prefix actually supplied to the model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collector_records_only_the_supplied_prefix_as_analysis_scope(
    monkeypatch: pytest.MonkeyPatch,
):
    seen: dict[str, str] = {}

    async def fake_structured(prompt: str, **kwargs: Any) -> dict[str, Any]:
        seen["prompt"] = prompt
        return _ok_envelope([dict(ONE_CLAIM)])

    monkeypatch.setattr(collector_module, "call_structured_llm", fake_structured)
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    marker = "TAIL-MARKER-NEVER-SUPPLIED"
    body = "a" * COLLECTOR_CONTENT_LIMIT + marker
    envelope = await _collect_envelope({"title": "Title", "content": body})

    outcome = envelope["extraction_outcome"]
    assert outcome["status"] == "valid"
    assert outcome["scope_start"] == 0
    assert outcome["scope_end"] == 5000
    assert outcome["input_limit"] == 5000
    assert outcome["body_char_count"] == len(body)
    assert outcome["body_char_count"] == 5000 + len(marker)
    assert outcome["source_available"] is True

    assert body[:COLLECTOR_CONTENT_LIMIT] in seen["prompt"]
    assert marker not in seen["prompt"]

    # The supplied text and window are exactly what was recorded.
    normalized, supplied, window = _analysis_input({"content": body})
    assert normalized == body
    assert supplied == body[:COLLECTOR_CONTENT_LIMIT]
    assert window == AnalysisWindow(start_char=0, end_char=5000)
    assert supplied[window.start_char : window.end_char] == supplied


# ---------------------------------------------------------------------------
# 4. CRLF/CR normalization and the drift guard against the capture store
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("a\r\nb", "a\nb"), ("a\rb", "a\nb"), ("a\nb", "a\nb"), ("", "")],
)
def test_normalize_body_matches_capture_normalization(raw: str, expected: str):
    assert _normalize_body(raw) == expected
    # Drift guard: the AI layer and the capture store must normalize identically,
    # otherwise recorded quotation offsets would not be code points of the body
    # the validator checks.
    assert _normalize_body(raw) == normalize_capture_text(raw)


@pytest.mark.asyncio
async def test_crlf_body_scope_is_measured_on_the_normalized_body(
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_structured(prompt: str, **kwargs: Any) -> dict[str, Any]:
        return _ok_envelope([dict(ONE_CLAIM)])

    monkeypatch.setattr(collector_module, "call_structured_llm", fake_structured)
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    raw = "line one\r\nline two\rline three\nline four"
    normalized = "line one\nline two\nline three\nline four"
    envelope = await _collect_envelope({"title": "T", "content": raw})

    outcome = envelope["extraction_outcome"]
    assert outcome["body_char_count"] == len(normalized)
    # One CRLF pair collapses to a single LF; the lone CR is already one char.
    assert outcome["body_char_count"] == len(raw) - 1
    assert outcome["scope_end"] == len(normalized)


# ---------------------------------------------------------------------------
# 5. Title text is never analysis-scope evidence
# ---------------------------------------------------------------------------


def test_title_only_text_cannot_validate_a_body_passage():
    title = "Headline sentence that never appears in the body"
    body = "The body reports something else entirely."
    scope = AnalysisScope(start_char=0, end_char=len(body))

    alignment = validate_quote_alignment(body, QuoteProposal(quote=title), scope)

    assert alignment.status == "no_match"
    assert alignment.diagnostic_reason == "no_exact_occurrence_in_scope"

    # And the collector's recorded window only ever covers the body.
    normalized, supplied, window = _analysis_input({"title": title, "content": body})
    assert title not in supplied
    assert window.start_char == 0
    assert window.end_char == len(supplied) == len(body)
    assert window.end_char <= len(normalized)
    assert normalized[window.start_char : window.end_char] == supplied


# ---------------------------------------------------------------------------
# 6. No API key: unavailable, untrusted, and no invented quotations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_api_key_is_unavailable_and_untrusted(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    text = "Headline about a thing. Body sentence about the thing. Another one."
    envelope = await _collect_envelope(
        {"title": "Headline about a thing", "content": text}
    )

    outcome = envelope["extraction_outcome"]
    assert outcome["status"] == "unavailable"
    assert outcome["quote_proposals_trusted"] is False
    assert outcome["reason"] == "no_api_key"
    assert outcome["source_available"] is True
    assert outcome["body_char_count"] == len(text)
    assert outcome["input_limit"] == COLLECTOR_CONTENT_LIMIT

    # Existing envelope keys are unchanged.
    assert envelope["parse_status"] == "no_api_key"
    assert envelope["structured_output_used"] is False
    assert envelope["fallback_used"] is True
    assert envelope["raw_response_excerpt"] == ""

    coarse = envelope["output"]["claims"]
    assert coarse, "fallback claims are still produced for diagnostics"
    for claim in coarse:
        assert "source_quote" not in claim
        assert "source_quote_start" not in claim
        assert "source_quote_end" not in claim
        assert set(claim) == {"claim", "who", "when", "where", "confidence"}

    # Untrusted fallback still short-circuits the plain-list contract.
    assert await collect_claims({"title": "Headline", "content": text}) == []


# ---------------------------------------------------------------------------
# 7. Status mapping across the provider paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_parse_failure_is_fallback_and_untrusted(
    monkeypatch: pytest.MonkeyPatch,
):
    coarse = [
        {
            "claim": "Coarse sentence from title and body",
            "who": [],
            "when": "",
            "where": "",
            "confidence": "LOW",
        }
    ]

    async def fake_structured(prompt: str, **kwargs: Any) -> dict[str, Any]:
        return _fallback_envelope(coarse)

    monkeypatch.setattr(collector_module, "call_structured_llm", fake_structured)
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    envelope = await _collect_envelope(ARTICLE)

    outcome = envelope["extraction_outcome"]
    assert outcome["status"] == "fallback"
    assert outcome["quote_proposals_trusted"] is False
    assert outcome["reason"] == "structured_parse_failed"
    assert outcome["scope_end"] == len(ARTICLE["content"])
    # Substituted coarse claims are never trusted, so the plain-list contract
    # keeps returning an empty list.
    assert await collect_claims(ARTICLE) == []


@pytest.mark.asyncio
async def test_absent_claims_key_from_provider_is_a_fallback_not_a_valid_empty(
    monkeypatch: pytest.MonkeyPatch,
):
    """The real ``call_structured_llm`` path must reject a payload without claims."""

    async def fake_completion(**kwargs: Any) -> dict[str, Any]:
        return {"choices": [{"message": {"content": '{"items": []}'}}]}

    monkeypatch.setattr(collector_module, "acompletion", fake_completion)
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    envelope = await _collect_envelope(ARTICLE)

    outcome = envelope["extraction_outcome"]
    assert outcome["status"] == "fallback"
    assert outcome["quote_proposals_trusted"] is False
    assert envelope["fallback_used"] is True
    assert envelope["parse_status"] == "fallback"


@pytest.mark.asyncio
async def test_explicit_empty_structured_output_is_empty_and_untrusted(
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_structured(prompt: str, **kwargs: Any) -> dict[str, Any]:
        envelope = _ok_envelope([])
        envelope["raw_response_excerpt"] = '{"claims": []}'
        return envelope

    monkeypatch.setattr(collector_module, "call_structured_llm", fake_structured)
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    envelope = await _collect_envelope(ARTICLE)

    outcome = envelope["extraction_outcome"]
    assert outcome["status"] == "empty"
    assert outcome["quote_proposals_trusted"] is False
    assert outcome["reason"] == "explicit_empty_claims"
    assert envelope["output"] == {"claims": []}
    assert envelope["fallback_used"] is False
    # A validated empty collection is still an empty plain list.
    assert await collect_claims(ARTICLE) == []


@pytest.mark.asyncio
async def test_valid_structured_output_is_trusted(monkeypatch: pytest.MonkeyPatch):
    async def fake_structured(prompt: str, **kwargs: Any) -> dict[str, Any]:
        return _ok_envelope([dict(ONE_CLAIM)])

    monkeypatch.setattr(collector_module, "call_structured_llm", fake_structured)
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    envelope = await _collect_envelope(ARTICLE)

    outcome = envelope["extraction_outcome"]
    assert outcome["status"] == "valid"
    assert outcome["quote_proposals_trusted"] is True
    assert outcome["reason"] == ""
    assert outcome["scope_start"] == 0
    assert outcome["scope_end"] == len(ARTICLE["content"])
    assert outcome["body_char_count"] == len(ARTICLE["content"])


@pytest.mark.asyncio
async def test_valid_claim_without_any_body_is_never_trusted(
    monkeypatch: pytest.MonkeyPatch,
):
    """No body means nothing a quotation could match: never vest proposals."""

    async def fake_structured(prompt: str, **kwargs: Any) -> dict[str, Any]:
        return _ok_envelope([dict(ONE_CLAIM)])

    monkeypatch.setattr(collector_module, "call_structured_llm", fake_structured)
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    envelope = await _collect_envelope({"title": "Headline only", "content": None})

    outcome = envelope["extraction_outcome"]
    assert outcome["status"] == "valid"
    assert outcome["source_available"] is False
    assert outcome["body_char_count"] == 0
    assert outcome["scope_end"] == 0
    assert outcome["quote_proposals_trusted"] is False


# ---------------------------------------------------------------------------
# 8. The existing return contracts are preserved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plain_list_contract_is_preserved(monkeypatch: pytest.MonkeyPatch):
    async def fake_structured(prompt: str, **kwargs: Any) -> dict[str, Any]:
        return _ok_envelope([dict(ONE_CLAIM)])

    monkeypatch.setattr(collector_module, "call_structured_llm", fake_structured)
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    claims = await collect_claims(ARTICLE)

    assert isinstance(claims, list)
    assert claims == [ONE_CLAIM]


# ---------------------------------------------------------------------------
# 9. Workflow: honest zero-claim events, unchanged shape otherwise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_empty_collection_yields_a_zero_claim_event(
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_collect(article: dict[str, Any], *, include_metadata: bool = False):
        assert include_metadata is True
        return _collector_envelope(
            [],
            status="empty",
            scope_end=len(ARTICLE["content"]),
            body_char_count=len(ARTICLE["content"]),
        )

    monkeypatch.setattr("src.ai.workflow.collect_claims", fake_collect)

    event = await AIWorkflow({"llm": {"model": "gpt-4"}}).process_article(ARTICLE)

    assert event is not None
    assert event["claims"] == []
    assert event["narratives"] == []
    assert event["parties"] == []
    assert event["title"] == ARTICLE["title"]
    assert event["summary"] == ARTICLE["content"][:500]
    assert event["verification_status"] == "ALLEGED"
    assert event["source_url"] == ARTICLE["link"]
    assert event["source_name"] == ARTICLE["source_name"]
    assert event["location_country_code"] is None
    assert event["location_lat"] is None
    assert event["location_lon"] is None
    assert event["timestamp"] == ARTICLE["timestamp"]
    # The case service owns routing; the workflow must not invent it.
    assert "workflow_route" not in event
    assert "routing_reason" not in event
    assert event["extraction_outcome"]["status"] == "empty"
    assert event["extraction_outcome"]["quote_proposals_trusted"] is False
    assert (
        event["llm_metadata"]["collector"]["extraction_outcome"]["status"] == "empty"
    )
    assert event["llm_metadata"]["collector"]["parse_status"] == "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["fallback", "unavailable"])
async def test_untrusted_zero_claim_outcomes_still_return_none(
    monkeypatch: pytest.MonkeyPatch, status: ExtractionStatus
):
    async def fake_collect(article: dict[str, Any], *, include_metadata: bool = False):
        return _collector_envelope([], status=status, trusted=False)

    monkeypatch.setattr("src.ai.workflow.collect_claims", fake_collect)

    assert await AIWorkflow({"llm": {"model": "gpt-4"}}).process_article(ARTICLE) is None


@pytest.mark.asyncio
async def test_valid_envelope_records_the_outcome_on_the_event(
    monkeypatch: pytest.MonkeyPatch,
):
    await _patch_parties_and_clustering(monkeypatch)

    async def fake_collect(article: dict[str, Any], *, include_metadata: bool = False):
        return _collector_envelope(
            [dict(ONE_CLAIM)],
            status="valid",
            trusted=True,
            scope_end=len(ARTICLE["content"]),
            body_char_count=len(ARTICLE["content"]),
        )

    monkeypatch.setattr("src.ai.workflow.collect_claims", fake_collect)

    event = await AIWorkflow({"llm": {"model": "gpt-4"}}).process_article(ARTICLE)

    assert event is not None
    assert len(event["claims"]) == 1
    assert event["claims"][0]["claim"] == ONE_CLAIM["claim"]
    # Old keys and shape intact.
    for key in (
        "id",
        "timestamp",
        "title",
        "summary",
        "verification_status",
        "claims",
        "narratives",
        "parties",
        "source_url",
        "source_name",
        "llm_metadata",
        "location_country_code",
        "location_lat",
        "location_lon",
    ):
        assert key in event
    assert event["llm_metadata"]["collector"]["parse_status"] == "ok"
    assert event["llm_metadata"]["collector"]["structured_output_used"] is True
    # The outcome is readable both nested (legacy metadata location) and at the
    # top level (so the event store does not have to dig for it).
    assert (
        event["llm_metadata"]["collector"]["extraction_outcome"]
        == event["extraction_outcome"]
    )
    assert event["extraction_outcome"]["status"] == "valid"
    assert event["extraction_outcome"]["quote_proposals_trusted"] is True
    assert event["extraction_outcome"]["scope_end"] == len(ARTICLE["content"])
    assert event["extraction_outcome"]["body_char_count"] == len(ARTICLE["content"])


# ---------------------------------------------------------------------------
# 10. Compat path: a raw claim list proves nothing about the body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compat_raw_claim_list_is_never_trusted(
    monkeypatch: pytest.MonkeyPatch,
):
    await _patch_parties_and_clustering(monkeypatch)

    async def fake_collect(article: dict[str, Any], *, include_metadata: bool = False):
        return [dict(ONE_CLAIM)]

    monkeypatch.setattr("src.ai.workflow.collect_claims", fake_collect)

    event = await AIWorkflow({"llm": {"model": "gpt-4"}}).process_article(ARTICLE)

    assert event is not None
    assert len(event["claims"]) == 1
    outcome = event["extraction_outcome"]
    assert outcome["status"] == "valid"
    assert outcome["quote_proposals_trusted"] is False
    assert outcome["scope_start"] == 0
    assert outcome["scope_end"] == 0
    assert outcome["body_char_count"] == 0
    assert outcome["input_limit"] == 0
    assert outcome["source_available"] is False
    assert outcome["reason"] == "compat_collector_result"
    assert event["llm_metadata"]["collector"]["extraction_outcome"] == outcome


def test_collector_outcome_prefers_the_recorded_envelope():
    recorded = _collector_envelope([dict(ONE_CLAIM)], status="valid", trusted=True)
    recorded["extraction_outcome"]["scope_end"] = 42

    outcome = _collector_outcome(recorded, [dict(ONE_CLAIM)])

    assert outcome["status"] == "valid"
    assert outcome["scope_end"] == 42
    assert outcome["quote_proposals_trusted"] is True
    # A copy, not the caller's dict.
    assert outcome is not recorded["extraction_outcome"]


def test_collector_outcome_derives_a_conservative_compat_outcome():
    compat = {
        "output": {"claims": []},
        "parse_status": "compat_raw",
        "structured_output_used": False,
        "fallback_used": False,
        "raw_response_excerpt": "",
    }

    empty = _collector_outcome(compat, [])
    assert empty["status"] == "unavailable"
    assert empty["quote_proposals_trusted"] is False
    assert empty["scope_start"] == 0
    assert empty["scope_end"] == 0

    with_claims = _collector_outcome(compat, [dict(ONE_CLAIM)])
    assert with_claims["status"] == "valid"
    assert with_claims["quote_proposals_trusted"] is False
    assert with_claims["reason"] == "compat_collector_result"


# ---------------------------------------------------------------------------
# 11. The party-investigation collector node propagates the outcome unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collector_node_propagates_the_outcome(monkeypatch: pytest.MonkeyPatch):
    envelope = _collector_envelope(
        [dict(ONE_CLAIM)],
        status="valid",
        trusted=True,
        scope_end=len(ARTICLE["content"]),
        body_char_count=len(ARTICLE["content"]),
    )

    async def fake_collect(article: dict[str, Any], *, include_metadata: bool = False):
        assert include_metadata is True
        return envelope

    monkeypatch.setattr(party_flow_module, "collect_claims", fake_collect)

    state = await collector_node(
        {
            "article": ARTICLE,
            "claims": [],
            "parties": {},
            "party_investigations": [],
            "final_determinations": [],
            "event_summary": {},
            "llm_metadata": {},
            "error": "",
        }
    )

    assert state["claims"] == [ONE_CLAIM]
    stored = state["llm_metadata"]["collector"]
    assert stored["extraction_outcome"]["status"] == "valid"
    assert stored["extraction_outcome"]["quote_proposals_trusted"] is True
    assert stored["extraction_outcome"]["scope_end"] == len(ARTICLE["content"])
