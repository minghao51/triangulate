"""Case-scoped lexical search read model (S02).

Contract: evidence-workbench specification §8 and the S02 ticket brief. This
module is a **session-in, plain-dict-out reader** over the S01 FTS5 index
(``src/storage/search.py`` / ``case_search_index``):

* every SQL statement is case-scoped (``case_id = :case``) — case isolation is
  never applied in Python after the fact;
* the caller's ``q`` is tokenized into deterministic Unicode word terms and each
  term is quoted/escaped for FTS5 before binding, so no raw FTS operator
  (``*``, ``-``, ``:``, ``AND``, ``NEAR(``, ``"``, ``;``) can reach ``MATCH``;
* the index is only read: no row is created, deleted, rebuilt or repaired;
* ``None``-free dicts are returned for the HTTP layer to map onto camelCase DTOs.

Failure signalling matches the rest of the read API:

* :class:`SearchNotFound` — unknown case (404);
* :class:`SearchInvalid` — malformed query/filter/range (422);
* :class:`SearchIndexUnavailable` — the S01 capability probe reports the index
  unusable (503, carrying the operator remedy). It is never degraded to an empty
  success state and there is no ``LIKE`` fallback.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from typing import Any, Iterable

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from src.storage.models import TopicCase
from src.storage.search import TABLE, probe_search_capability

DEFAULT_SEARCH_LIMIT = 25
MAX_SEARCH_LIMIT = 100
MAX_QUERY_CODE_POINTS = 256
MAX_SEARCH_OFFSET = 2**31 - 1

#: FTS5 ``snippet()`` context budget, in tokens, for the plain-text excerpt.
SNIPPET_TOKEN_BUDGET = 24
#: Ellipsis marker inserted by ``snippet()``. Plain text; never HTML.
SNIPPET_ELLIPSIS = "..."

RESULT_TYPES = ("claim", "evidence")

#: Claim verification-state labels, as used by the rest of the HTTP API
#: (``verificationStatus``). The index stores the stored enum value
#: (``ALLEGED``); filtering normalizes case only, never fuzzy-matches.
_CLAIM_STATUS_LABELS = {
    "confirmed": "CONFIRMED",
    "probable": "PROBABLE",
    "alleged": "ALLEGED",
    "contested": "CONTESTED",
    "debunked": "DEBUNKED",
    # ``unknown`` is a real API label but no claim stores it: the filter is
    # accepted and matches nothing rather than being invented as a 422.
    "unknown": "UNVERIFIED",
}

#: FTS5 column ordinals used by ``snippet()`` (see migration 15's column list).
_TITLE_COLUMN = 3
_BODY_COLUMN = 4

_TOKEN_PATTERN = r"[^\W_]+"


class SearchNotFound(LookupError):
    """The requested case does not exist (404)."""


class SearchInvalid(ValueError):
    """The query/filter/range is malformed even for an existing case (422)."""


class SearchIndexUnavailable(RuntimeError):
    """The S01 index capability probe reports the index unusable (503)."""

    def __init__(self, case_id: str, reason: str) -> None:
        self.case_id = case_id
        self.reason = reason
        super().__init__(reason)


# --------------------------------------------------------------------------
# Query interpretation: literal all-term semantics
# --------------------------------------------------------------------------


def _normalize_for_compare(value: str) -> str:
    """Mirror ``unicode61``: compatibility-decompose, drop marks, casefold."""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(
        char for char in decomposed if not unicodedata.combining(char)
    ).casefold()


def tokenize_terms(query: str) -> list[str]:
    """Return the deterministic Unicode word terms of ``query``, in order.

    A term is a maximal run of Unicode word code points excluding underscore.
    Duplicates are dropped (repeating a term cannot change ``AND`` semantics),
    and the original order is preserved for a stable ``MATCH`` expression.
    """
    terms: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(_TOKEN_PATTERN, query):
        term = match.group(0)
        normalized = _normalize_for_compare(term)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        terms.append(term)
    return terms


def escape_fts_term(term: str) -> str:
    """Quote one term as an FTS5 string literal (internal quotes doubled)."""
    return '"' + term.replace('"', '""') + '"'


def build_match_expression(terms: Iterable[str]) -> str:
    """AND the quoted terms; only our own operator separators reach ``MATCH``."""
    return " AND ".join(escape_fts_term(term) for term in terms)


def _validate_query(query: str) -> tuple[str, list[str], str]:
    """Return ``(trimmed_query, terms, match_expression)`` or raise 422."""
    if not isinstance(query, str):
        raise SearchInvalid("q is required")
    trimmed = query.strip()
    if not trimmed:
        raise SearchInvalid("q must contain at least one non-whitespace character")
    if len(trimmed) > MAX_QUERY_CODE_POINTS:
        raise SearchInvalid(
            f"q must be at most {MAX_QUERY_CODE_POINTS} code points "
            f"(received {len(trimmed)})"
        )
    terms = tokenize_terms(trimmed)
    if not terms:
        raise SearchInvalid(
            "q contains no searchable word terms; literal punctuation and FTS "
            "operators are not a query"
        )
    return trimmed, terms, build_match_expression(terms)


# --------------------------------------------------------------------------
# Filter validation
# --------------------------------------------------------------------------


def _parse_utc_bound(value: str, field: str) -> datetime:
    """Parse a UTC ISO-8601 bound; naive values are read as UTC, then converted."""
    raw = value.strip()
    if not raw:
        raise SearchInvalid(f"{field} must be a non-empty ISO-8601 timestamp")
    candidate = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise SearchInvalid(
            f"{field} must be an ISO-8601 UTC timestamp (received {raw!r})"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _sql_bound(value: datetime) -> str:
    """Render a UTC bound for SQLite's ``julianday()`` comparison."""
    return value.strftime("%Y-%m-%d %H:%M:%S.%f")


def _normalize_status_filter(status: str) -> str:
    raw = status.strip()
    if not raw:
        raise SearchInvalid("status must not be empty")
    stored = _CLAIM_STATUS_LABELS.get(raw.casefold())
    if stored is None:
        raise SearchInvalid(
            "status must be one of "
            + ", ".join(sorted(_CLAIM_STATUS_LABELS))
        )
    return stored


def _normalize_publisher_filter(publisher: str) -> str:
    raw = publisher.strip()
    if not raw:
        raise SearchInvalid("publisher must not be empty")
    return raw


def _status_label(stored: str | None) -> str | None:
    """Render a stored claim verification state in the API's label vocabulary."""
    if not stored:
        return None
    label = stored.strip().casefold()
    return label if label in _CLAIM_STATUS_LABELS else "unknown"


def _normalize_published_at(stored: str | None) -> str | None:
    """Render a stored publication time as ISO UTC; unknown stays ``None``."""
    if not stored:
        return None
    raw = stored.strip()
    if not raw:
        return None
    candidate = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


# --------------------------------------------------------------------------
# Row assembly
# --------------------------------------------------------------------------


def _plain_snippet(raw: str | None) -> str:
    """Collapse whitespace in a ``snippet()`` window; never emit HTML/markers."""
    if not raw:
        return ""
    return " ".join(raw.replace("\x00", " ").split())


def _title_matches(title: str, terms: list[str]) -> bool:
    """True when every query term occurs in the stored title (honest matchedField)."""
    normalized_title = _normalize_for_compare(title or "")
    title_terms = {
        _normalize_for_compare(match.group(0))
        for match in re.finditer(_TOKEN_PATTERN, normalized_title)
    }
    return all(_normalize_for_compare(term) in title_terms for term in terms)


def _current_capture_ids(
    session: Session, case_id: str, evidence_ids: list[str]
) -> dict[str, str | None]:
    """Resolve ``current_capture_id`` for one page of evidence rows, case-scoped."""
    if not evidence_ids:
        return {}
    statement = text(
        "SELECT id, current_capture_id FROM evidence_items "
        "WHERE case_id = :case_id AND id IN :ids"
    ).bindparams(bindparam("ids", expanding=True))
    rows = session.execute(statement, {"case_id": case_id, "ids": evidence_ids})
    return {row[0]: row[1] for row in rows}


def _build_where(
    *,
    match_expression: str,
    case_id: str,
    result_type: str | None,
    publisher: str | None,
    status: str | None,
    published_from: datetime | None,
    published_to: datetime | None,
) -> tuple[str, dict[str, Any]]:
    """Compose the shared WHERE clause; every clause is case-scoped."""
    clauses = [f"{TABLE} MATCH :match", "case_id = :case_id"]
    params: dict[str, Any] = {"match": match_expression, "case_id": case_id}
    if result_type is not None:
        clauses.append("entity_type = :entity_type")
        params["entity_type"] = result_type
    if publisher is not None:
        clauses.append("publisher = :publisher")
        params["publisher"] = publisher
    if status is not None:
        clauses.append("upper(status) = :status")
        params["status"] = status
    if published_from is not None:
        # An unknown/unparseable stored date is NULL here and therefore excluded
        # whenever a date filter applies (specification §8).
        clauses.append(
            "julianday(published_at) IS NOT NULL "
            "AND julianday(published_at) >= julianday(:published_from)"
        )
        params["published_from"] = _sql_bound(published_from)
    if published_to is not None:
        clauses.append(
            "julianday(published_at) IS NOT NULL "
            "AND julianday(published_at) < julianday(:published_to)"
        )
        params["published_to"] = _sql_bound(published_to)
    return " AND ".join(clauses), params


def _select_rows(
    session: Session, where: str, params: dict[str, Any], *, limit: int, offset: int
) -> list[Any]:
    """One page of results: bm25 rank, then the ``(resultType, id)`` tie-break."""
    sql = (
        "SELECT entity_type, entity_id, title, event_id, publisher, status, "
        f"published_at, snippet({TABLE}, {_TITLE_COLUMN}, '', '', "
        f"'{SNIPPET_ELLIPSIS}', {SNIPPET_TOKEN_BUDGET}) AS title_snippet, "
        f"snippet({TABLE}, {_BODY_COLUMN}, '', '', "
        f"'{SNIPPET_ELLIPSIS}', {SNIPPET_TOKEN_BUDGET}) AS body_snippet "
        f"FROM {TABLE} WHERE {where} "
        f"ORDER BY bm25({TABLE}) ASC, entity_type ASC, entity_id ASC "
        "LIMIT :limit OFFSET :offset"
    )
    return list(
        session.execute(
            text(sql),
            {**params, "limit": limit, "offset": offset},
        )
    )


def _count_rows(session: Session, where: str, params: dict[str, Any]) -> int:
    total = session.execute(
        text(f"SELECT count(*) FROM {TABLE} WHERE {where}"), params
    ).scalar()
    return int(total or 0)


def _item(
    row: Any,
    *,
    terms: list[str],
    capture_ids: dict[str, str | None],
) -> dict[str, Any]:
    entity_type, entity_id, title, event_id, publisher, status, published_at = row[:7]
    title_snippet, body_snippet = row[7], row[8]
    is_evidence = entity_type == "evidence"
    matched_field = (
        "title" if is_evidence and _title_matches(title or "", terms) else "body"
    )
    snippet = _plain_snippet(title_snippet if matched_field == "title" else body_snippet)
    if not snippet:
        snippet = _plain_snippet(body_snippet if matched_field == "title" else title_snippet)
    return {
        "result_type": entity_type,
        "id": entity_id,
        "claim_id": None if is_evidence else entity_id,
        "evidence_id": entity_id if is_evidence else None,
        "event_id": event_id or None,
        "capture_id": capture_ids.get(entity_id) if is_evidence else None,
        "title": (title or None) if is_evidence else None,
        "snippet": snippet,
        "matched_field": matched_field,
        "publisher": (publisher or None) if is_evidence else None,
        "status": None if is_evidence else _status_label(status),
        "published_at": _normalize_published_at(published_at) if is_evidence else None,
    }


# --------------------------------------------------------------------------
# Public reader
# --------------------------------------------------------------------------


def read_case_search(
    session: Session,
    *,
    case_id: str,
    q: str,
    result_type: str | None = None,
    publisher: str | None = None,
    status: str | None = None,
    published_from: str | None = None,
    published_to: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """Read one page of case-scoped lexical search results.

    Raises :class:`SearchInvalid` (422) for a malformed query/filter/range,
    :class:`SearchNotFound` (404) for an unknown case and
    :class:`SearchIndexUnavailable` (503) when the S01 probe reports the index
    unusable. Nothing is written; the index is only read.
    """
    trimmed, terms, match_expression = _validate_query(q)

    if result_type is not None and result_type not in RESULT_TYPES:
        raise SearchInvalid("type must be 'claim' or 'evidence'")
    if limit < 1 or limit > MAX_SEARCH_LIMIT:
        raise SearchInvalid(f"limit must be between 1 and {MAX_SEARCH_LIMIT}")
    if offset < 0 or offset > MAX_SEARCH_OFFSET:
        raise SearchInvalid(f"offset must be between 0 and {MAX_SEARCH_OFFSET}")

    normalized_status = (
        _normalize_status_filter(status) if status is not None else None
    )
    normalized_publisher = (
        _normalize_publisher_filter(publisher) if publisher is not None else None
    )
    parsed_from = (
        _parse_utc_bound(published_from, "publishedFrom")
        if published_from is not None
        else None
    )
    parsed_to = (
        _parse_utc_bound(published_to, "publishedTo")
        if published_to is not None
        else None
    )
    if parsed_from is not None and parsed_to is not None and parsed_from > parsed_to:
        raise SearchInvalid("publishedFrom must not be after publishedTo")

    # A status filter applies only to claim results: an explicit evidence-only
    # request is contradictory, and an omitted type narrows to claims rather
    # than inventing evidence-party/status semantics.
    effective_type = (
        result_type if result_type is not None
        else "claim" if normalized_status is not None
        else None
    )
    if normalized_status is not None:
        if result_type == "evidence":
            raise SearchInvalid(
                "status applies to claim results only; it cannot be combined "
                "with type=evidence"
            )
    if normalized_publisher is not None and effective_type == "claim":
        raise SearchInvalid(
            "publisher applies to evidence results only; it cannot be combined "
            "with type=claim"
        )

    if session.get(TopicCase, case_id) is None:
        raise SearchNotFound(f"Case {case_id} not found")

    capability = probe_search_capability(session)
    if not capability.available:
        raise SearchIndexUnavailable(
            case_id, capability.reason or "the case search index is unavailable"
        )

    where, params = _build_where(
        match_expression=match_expression,
        case_id=case_id,
        result_type=effective_type,
        publisher=normalized_publisher,
        status=normalized_status,
        published_from=parsed_from,
        published_to=parsed_to,
    )
    total = _count_rows(session, where, params)
    rows = _select_rows(session, where, params, limit=limit, offset=offset)

    evidence_ids = [row[1] for row in rows if row[0] == "evidence"]
    capture_ids = _current_capture_ids(session, case_id, evidence_ids)
    items = [_item(row, terms=terms, capture_ids=capture_ids) for row in rows]

    return {
        "case_id": case_id,
        "query": trimmed,
        "total": total,
        "limit": limit,
        "offset": offset,
        "applied_filters": {
            "type": effective_type,
            "publisher": normalized_publisher,
            "status": (
                _status_label(normalized_status)
                if normalized_status is not None
                else None
            ),
            "published_from": (
                parsed_from.isoformat() if parsed_from is not None else None
            ),
            "published_to": (
                parsed_to.isoformat() if parsed_to is not None else None
            ),
        },
        "items": items,
    }


__all__ = [
    "DEFAULT_SEARCH_LIMIT",
    "MAX_QUERY_CODE_POINTS",
    "MAX_SEARCH_LIMIT",
    "RESULT_TYPES",
    "SearchIndexUnavailable",
    "SearchInvalid",
    "SearchNotFound",
    "build_match_expression",
    "escape_fts_term",
    "read_case_search",
    "tokenize_terms",
]
