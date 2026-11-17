"""Collector agent: Extract factual claims from articles."""

import logging
from dataclasses import dataclass
from typing import Any
import os
from litellm import acompletion

from src.ai.schemas import (
    ClaimCollectionSchema,
    ExtractionOutcomeSchema,
    ExtractionStatus,
)
from src.ai.utils import call_structured_llm, make_agent_envelope

logger = logging.getLogger(__name__)

# Hard truncation applied to the article body before it is sent to the model.
# Recorded on every extraction outcome so "saw a prefix" is never reported as
# "examined the capture".
COLLECTOR_CONTENT_LIMIT = 5000

COLLECTOR_PROMPT = """You are an expert analyst specializing in extracting factual claims from news articles.

Your task is to read an article and extract discrete, verifiable factual claims.

For each claim, extract:
1. The claim text (what is being asserted)
2. Who/what is involved (people, organizations, entities)
3. When it happened (timestamp or date)
4. Where it happened (location)
5. Confidence level (HIGH/MEDIUM/LOW based on source specificity)

Guidelines:
- Focus on objective facts, not opinions or predictions
- Extract multiple claims if they exist
- Be specific with names, dates, and locations
- If a claim is vague, assign LOW confidence
- Output as JSON array of claims

Article to analyze:
{title}

{content}

Output format (JSON array):
[
  {{
    "claim": "Specific factual assertion",
    "who": ["Entity1", "Entity2"],
    "when": "Date or time description",
    "where": "Location",
    "confidence": "HIGH|MEDIUM|LOW"
  }}
]

Extract claims:"""


@dataclass(frozen=True)
class AnalysisWindow:
    """Code-point window of the normalized body actually supplied to the model."""

    start_char: int
    end_char: int


def _normalize_body(text: str) -> str:
    """Normalize a body for analysis: CRLF/CR -> LF and nothing else.

    This deliberately mirrors :func:`src.storage.captures.normalize_capture_text`
    so that quotation offsets recorded here refer to the same text the capture
    store binds and the validator checks. It is duplicated (rather than imported)
    to keep the AI layer free of SQLAlchemy; a test pins the two helpers together
    so they cannot drift.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _analysis_input(article: dict[str, Any]) -> tuple[str, str, AnalysisWindow]:
    """Return ``(normalized_body, supplied_text, window)`` for one article.

    ``normalized_body`` is the full LF-normalized article body, ``supplied_text``
    the exact prefix handed to the model, and ``window`` the code-point span of
    that prefix on the normalized body. The title is never part of the recorded
    scope: a sentence that only exists in the title must not be able to validate
    a passage of the body.
    """
    content = article.get("content")
    body = _normalize_body(content) if isinstance(content, str) else ""
    supplied = body[:COLLECTOR_CONTENT_LIMIT]
    return body, supplied, AnalysisWindow(start_char=0, end_char=len(supplied))


def _extraction_outcome(
    status: ExtractionStatus,
    *,
    body: str,
    window: AnalysisWindow,
    reason: str = "",
) -> dict[str, Any]:
    """Build the honest extraction-outcome payload recorded on the envelope."""
    return ExtractionOutcomeSchema(
        status=status,
        # Only a real validated structured parse over a non-empty body may vest
        # quote proposals: with no body there is nothing a passage could match.
        quote_proposals_trusted=status == "valid" and bool(body),
        scope_start=window.start_char,
        scope_end=window.end_char,
        body_char_count=len(body),
        input_limit=COLLECTOR_CONTENT_LIMIT,
        source_available=bool(body),
        reason=reason,
    ).model_dump()


async def collect_claims(
    article: dict[str, Any], *, include_metadata: bool = False
) -> list[dict[str, Any]] | dict[str, Any]:
    """Extract claims from an article using LLM.

    Args:
        article: Article dictionary with title and content

    Returns:
        List of extracted claim dictionaries
    """
    body, supplied, window = _analysis_input(article)
    try:
        if not os.getenv("LLM_API_KEY"):
            logger.error("No LLM_API_KEY found")
            result = make_agent_envelope(
                {"claims": _fallback_claims(article)},
                parse_status="no_api_key",
                structured_output_used=False,
                fallback_used=True,
            )
            result["extraction_outcome"] = _extraction_outcome(
                "unavailable", body=body, window=window, reason="no_api_key"
            )
            return result if include_metadata else []

        prompt = COLLECTOR_PROMPT.format(
            title=article.get("title", ""),
            content=supplied,
        )

        logger.info(f"Extracting claims from article: {article.get('title', '')[:50]}")

        result = await call_structured_llm(
            prompt=prompt,
            schema=ClaimCollectionSchema,
            temperature=0.3,
            max_tokens=2000,
            fallback=lambda: {"claims": _fallback_claims(article)},
            completion_func=acompletion,
        )
        claims = result["output"].get("claims", [])
        logger.info("Extracted %s claims", len(claims))

        # ``call_structured_llm`` reports ``parse_status="fallback"`` together
        # with ``fallback_used=True``; anything else it returns parsed cleanly.
        if result.get("fallback_used") or result.get("parse_status") not in (None, "ok"):
            status, reason = "fallback", "structured_parse_failed"
        elif claims:
            status, reason = "valid", ""
        else:
            status, reason = "empty", "explicit_empty_claims"
        result["extraction_outcome"] = _extraction_outcome(
            status, body=body, window=window, reason=reason
        )

        if result.get("fallback_used") and not include_metadata and not result.get(
            "raw_response_excerpt"
        ):
            return []
        return result if include_metadata else claims
    except Exception as e:
        logger.error(f"Error extracting claims: {e}")
        result = make_agent_envelope(
            {"claims": _fallback_claims(article)},
            parse_status="error",
            structured_output_used=True,
            fallback_used=True,
        )
        result["extraction_outcome"] = _extraction_outcome(
            "unavailable",
            body=body,
            window=window,
            reason=f"extraction_error:{type(e).__name__}",
        )
        return result if include_metadata else []


def _fallback_claims(article: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract coarse claims from article text without an LLM.

    These claims deliberately carry no ``source_quote``/offset proposals: the
    sentences are cut from ``title + content`` joined together, so any offset
    would be meaningless and a title-only sentence must never be able to
    validate a passage of the body.
    """
    content = " ".join(
        part.strip()
        for part in [article.get("title", ""), article.get("content", "")]
        if part
    )
    sentences = [
        sentence.strip(" -\n\t")
        for sentence in content.replace("\n", " ").split(".")
        if sentence.strip()
    ]
    claims = []
    for sentence in sentences[:5]:
        if len(sentence) < 8:
            continue
        claims.append(
            {
                "claim": sentence,
                "who": [],
                "when": "",
                "where": "",
                "confidence": "LOW",
            }
        )
    return claims[:3]
