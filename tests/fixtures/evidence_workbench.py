"""Shared synthetic evidence-workbench fixture (E02).

Five fictional sources about one fictional event, provided so that later
quotation, citation, API and browser contract tests can share one dataset:

* ``A`` -- the original first-hand bulletin (Unicode: emoji, CJK, combining mark);
* ``B`` -- a verbatim copy of ``A`` on a different publisher/URL;
* ``C`` -- an independent account in different words;
* ``D`` -- a weak partial/paraphrase that omits the time and the district;
* ``E`` -- an account that spans a contradiction of the central claim.

``UNAVAILABLE`` is a source whose body is missing entirely.

This module is **data only**. It deliberately contains no copy/dependency-group
algorithm (that is P01), no claim extraction, no truth or independence
assertions and no network/provider access. Nothing here calls a model.

Sources always describe fictional people/places; do not treat any text as a real
report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# The central assertion used by quotation/citation tests. ``CENTRAL_QUOTE`` is an
# exact substring of the A body (and therefore of the verbatim copy B).
CENTRAL_CLAIM = (
    "The Port Alden Authority ordered an evacuation of the northern district "
    "at 06:00 local time."
)
CENTRAL_QUOTE = (
    "ordered an evacuation of the northern district at 06:00 local time"
)

# A separate claim that source E contradicts in its own words.
CONTRADICTION_CLAIM = (
    "The Port Alden Authority issued an evacuation order for the northern district."
)

# Non-ASCII material deliberately embedded in the A body so that code-point
# handling is exercised: emoji, CJK and a combining acute accent (``e`` + U+0301).
UNICODE_MARKERS = {
    "emoji": "\U0001f6a8",  # 🚨
    "cjk": "\u6e2f\u53e3\u7ba1\u7406\u5c40",  # 港口管理局
    "combining_name": "Jose\u0301",  # José written with a combining accent
}

_A_BODY = (
    "PORT ALDEN \u2014 The Port Alden Authority ordered an evacuation of the "
    "northern district at 06:00 local time, according to its duty officer.\n"
    "\n"
    "The order, confirmed in a brief written statement, covers roughly 4,200 "
    "residents. The original bulletin carries the marker \U0001f6a8 and the "
    "agency name \u6e2f\u53e3\u7ba1\u7406\u5c40 in its header, and is signed "
    "by Jose\u0301 Alvarez.\n"
)

# The same source after a later edit: the central passage is unchanged, so an
# older citation must stay valid while a new capture version is created.
_A_REVISED_BODY = _A_BODY + (
    "\n"
    "Update, 09:30 local time: the authority said the order remained in force "
    "while shelters stayed open.\n"
)

_B_BODY = _A_BODY  # verbatim copy, byte-identical body

_C_BODY = (
    "PORT ALDEN \u2014 Residents in the north of the city were told to leave "
    "their homes before dawn on Tuesday, a city spokesperson said. Officials "
    "put the number of people in the affected area at roughly 4,200, though "
    "they did not confirm an exact start time.\n"
    "\n"
    "Separate reporting from the harbour side describes queues at the ferry "
    "terminal and a school being used as a shelter.\n"
)

_D_BODY = (
    "PORT ALDEN \u2014 A local official said people in part of the city had "
    "been asked to move to safer ground. No time and no specific area were "
    "given in the briefing.\n"
)

_E_BODY = (
    "PORT ALDEN \u2014 The Port Alden Authority said it did not order an "
    "evacuation of the northern district on Tuesday, contradicting earlier "
    "accounts. A spokesperson said the northern district was never under an "
    "evacuation order and that an earlier bulletin had been withdrawn.\n"
)


@dataclass(frozen=True)
class WorkbenchSource:
    """One synthetic source record plus its capture-relevant metadata."""

    key: str
    label: str
    publisher: str | None
    origin_url: str | None
    canonical_url: str | None
    title: str | None
    published_at: str | None
    body: str | None
    capture_metadata: dict[str, Any] = field(default_factory=dict)

    def capture_kwargs(self) -> dict[str, Any]:
        """Metadata mapping accepted by the capture helpers (known fields only)."""
        meta: dict[str, Any] = {}
        for key in ("title", "publisher", "origin_url", "canonical_url", "published_at"):
            value = getattr(self, key)
            if value is not None:
                meta[key] = value
        meta.update(self.capture_metadata)
        return meta


SOURCE_A = WorkbenchSource(
    key="A",
    label="original_bulletin",
    publisher="Meridian Wire",
    origin_url="https://wire.example.com/port-alden-evacuation",
    canonical_url="https://wire.example.com/port-alden-evacuation",
    title="Port Alden orders northern district evacuation",
    published_at="2026-03-03T06:20:00+00:00",
    body=_A_BODY,
    capture_metadata={"source_type": "rss", "extraction_method": "article_body"},
)

SOURCE_B = WorkbenchSource(
    key="B",
    label="verbatim_copy",
    publisher="Daily Echo Mirror",
    origin_url="https://mirror.example.net/port-alden-order",
    canonical_url="https://mirror.example.net/port-alden-order",
    title="Port Alden orders northern district evacuation",
    published_at="2026-03-03T07:05:00+00:00",
    body=_B_BODY,
    capture_metadata={"source_type": "rss", "extraction_method": "syndicated_body"},
)

SOURCE_C = WorkbenchSource(
    key="C",
    label="independent_account",
    publisher="Harbour Ledger",
    origin_url="https://ledger.example.org/port-alden-north",
    canonical_url="https://ledger.example.org/port-alden-north",
    title="Northern Port Alden residents told to leave before dawn",
    published_at="2026-03-03T09:10:00+00:00",
    body=_C_BODY,
    capture_metadata={"source_type": "rss", "extraction_method": "article_body"},
)

SOURCE_D = WorkbenchSource(
    key="D",
    label="weak_partial",
    publisher="City Desk Notes",
    origin_url="https://notes.example.io/port-alden-briefing",
    canonical_url="https://notes.example.io/port-alden-briefing",
    title="Briefing mentions people moving to safer ground",
    published_at="2026-03-03T11:40:00+00:00",
    body=_D_BODY,
    capture_metadata={"source_type": "rss", "extraction_method": "summary_only"},
)

SOURCE_E = WorkbenchSource(
    key="E",
    label="spans_contradiction",
    publisher="Civic Record",
    origin_url="https://record.example.co/port-alden-denial",
    canonical_url="https://record.example.co/port-alden-denial",
    title="Authority denies northern district evacuation order",
    published_at="2026-03-03T14:00:00+00:00",
    body=_E_BODY,
    capture_metadata={"source_type": "rss", "extraction_method": "article_body"},
)

UNAVAILABLE = WorkbenchSource(
    key="U",
    label="unavailable_source",
    publisher="Archive Placeholder",
    origin_url="https://unavailable.example.com/port-alden",
    canonical_url=None,
    title=None,
    published_at=None,
    body=None,
    capture_metadata={"extraction_method": "failed"},
)

WORKBENCH_SOURCES: tuple[WorkbenchSource, ...] = (
    SOURCE_A,
    SOURCE_B,
    SOURCE_C,
    SOURCE_D,
    SOURCE_E,
)

# An "old" variant: same bodies, but metadata missing (legacy rows predate
# publisher/URL/publication capture). This exists so tests can exercise absent
# versus unknown metadata without inventing values.
LEGACY_WORKBENCH_SOURCES: tuple[WorkbenchSource, ...] = tuple(
    WorkbenchSource(
        key=source.key,
        label=source.label,
        publisher=None,
        origin_url=None,
        canonical_url=None,
        title=None,
        published_at=None,
        body=source.body,
        capture_metadata={"legacy": True},
    )
    for source in WORKBENCH_SOURCES
)

REVISED_BODY_A = _A_REVISED_BODY


def source_by_key(key: str) -> WorkbenchSource:
    """Return the workbench source with ``key`` (A/B/C/D/E/U)."""
    for source in (*WORKBENCH_SOURCES, UNAVAILABLE):
        if source.key == key:
            return source
    raise KeyError(f"Unknown workbench source key: {key!r}")


def bodies() -> dict[str, str | None]:
    """Map source key -> body (``None`` for the unavailable placeholder)."""
    return {source.key: source.body for source in (*WORKBENCH_SOURCES, UNAVAILABLE)}


__all__ = [
    "CENTRAL_CLAIM",
    "CENTRAL_QUOTE",
    "CONTRADICTION_CLAIM",
    "LEGACY_WORKBENCH_SOURCES",
    "REVISED_BODY_A",
    "SOURCE_A",
    "SOURCE_B",
    "SOURCE_C",
    "SOURCE_D",
    "SOURCE_E",
    "UNAVAILABLE",
    "UNICODE_MARKERS",
    "WORKBENCH_SOURCES",
    "WorkbenchSource",
    "bodies",
    "source_by_key",
]
