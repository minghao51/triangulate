#!/usr/bin/env python3
"""Generate the 2026-11-23 product wireframe set (stdlib only, deterministic).

Writes 198 standalone SVG wireframes (66 definitions x desktop/tablet/mobile),
10 desktop flow boards, a manifest and the dated index/coverage/annotations doc.
No network, no database, no runtime. Run from anywhere:

    uv run --no-sync python docs/plans/20261123-product-wireframes/generate.py

Every case id, host, quote and count below is synthetic. The drawings are
proposals; they are not evidence that any capability is implemented.
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATE = "2026-11-23"
FOLDER = "20261123-product-wireframes"
DEFAULT_OUT = Path(__file__).resolve().parent
DEFAULT_DOC = ROOT / "docs/plans/20261123-product-wireframe-set.md"

SIZES = (12, 14, 20, 28)
WHITE, GREY, INK, MUTED, ACCENT = "#fff", "#e6e6e6", "#000", "#666", "#d33"
FAMILY = "-apple-system, system-ui, sans-serif"
LANE = {12: 24, 14: 32, 20: 40, 28: 48}
BASE = {12: 16, 14: 24, 20: 32, 28: 40}
GAPX, GAPY, PAD = 24, 24, 16

VP = {
    "desktop": dict(w=1280, h=800, x0=32, y0=32, x1=1256, y1=776, rail=240, topbar=False, caps=50),
    "tablet": dict(w=768, h=1024, x0=32, y0=32, x1=736, y1=992, rail=0, topbar=True, caps=50),
    "mobile": dict(w=375, h=812, x0=16, y0=32, x1=344, y1=776, rail=0, topbar=True, caps=50),
}

NAV_ITEMS = ["Dashboard", "Cases", "Network", "Sources", "Narratives", "Monitoring", "AI info"]


# --------------------------------------------------------------------------- geometry helpers
def r8(value: float) -> int:
    return int(round(value / 8.0)) * 8


def aligned(value, name: str) -> int:
    ivalue = int(value)
    assert ivalue == value and ivalue % 8 == 0, f"off-grid {name}={value}"
    return ivalue


def fit(text: str, width: int, size: int = 12) -> str:
    """Conservative single-line fit (0.62 em per character)."""
    if not text:
        return ""
    limit = max(1, int(width // (size * 0.62)))
    if len(text) <= limit:
        return text
    if limit <= 2:
        return text[:limit]
    return text[: limit - 1].rstrip(" ,;:-") + "\u2026"


def wrap(text: str, width: int, size: int = 12, max_lines: int = 2) -> list[str]:
    limit = max(1, int(width // (size * 0.62)))
    words, lines, cur = text.split(), [], ""
    for word in words:
        cand = word if not cur else cur + " " + word
        if len(cand) <= limit:
            cur = cand
            continue
        lines.append(cur)
        cur = word
        if len(lines) == max_lines:
            break
    if len(lines) < max_lines:
        lines.append(cur)
    consumed = sum(len(line) for line in lines)
    if len(lines) == max_lines and consumed < len(" ".join(words)):
        lines[-1] = fit(lines[-1], width, size)
    return [fit(line, width, size) for line in lines]


def split_widths(avail: int, weights) -> list[int]:
    n = len(weights)
    total = avail - GAPX * (n - 1)
    raw = [total * w / float(sum(weights)) for w in weights]
    widths = [r8(v) for v in raw[:-1]]
    widths.append(total - sum(widths))
    assert all(w >= 48 and w % 8 == 0 for w in widths), widths
    return widths


# --------------------------------------------------------------------------- svg canvas
class Svg:
    def __init__(self, vp: str):
        self.vp = vp
        self.items: list[tuple[str, dict]] = []
        self.regions: list[dict] = []

    def rect(self, x, y, w, h, fill=WHITE, stroke=False, dash=False, **_):
        attrs: dict[str, object] = {
            "x": aligned(x, "x"),
            "y": aligned(y, "y"),
            "width": aligned(w, "width"),
            "height": aligned(h, "height"),
            "fill": fill,
        }
        if stroke:
            attrs["stroke"] = INK
            attrs["stroke-width"] = 1.5
        if dash:
            attrs["stroke"] = ACCENT
            attrs["stroke-width"] = 1.5
            attrs["stroke-dasharray"] = "8 8"
            attrs["fill"] = "none"
        self.items.append(("rect", attrs))

    def line(self, x1, y1, x2, y2, color=INK):
        attrs: dict[str, object] = {
            "x1": aligned(x1, "x1"),
            "y1": aligned(y1, "y1"),
            "x2": aligned(x2, "x2"),
            "y2": aligned(y2, "y2"),
            "stroke": color,
            "stroke-width": 1.5,
        }
        self.items.append(("line", attrs))

    def text(self, x, y, s, size=12, color=INK, weight=None, anchor=None):
        if not str(s):
            return
        assert size in SIZES, f"unsupported font-size {size}"
        attrs: dict[str, object] = {"x": aligned(x, "x"), "y": aligned(y, "y")}
        if anchor:
            attrs["text-anchor"] = anchor
        attrs["font-size"] = size
        attrs["fill"] = color
        if weight:
            attrs["font-weight"] = 600
        attrs["_text"] = s
        self.items.append(("text", attrs))

    def pane(self, pane_id):
        self.items.append(("#open", {"data-pane": pane_id}))

    def end_pane(self):
        self.items.append(("#close", {}))

    def region(self, x, y, w, h, desc):
        v = VP[self.vp]
        cx, cy, cw, ch = x - 8, y - 8, w + 16, h + 16
        assert cx >= 0 and cy >= 0, f"region clips left/top: {desc}"
        assert cx + cw <= v["w"] and cy + ch <= v["h"], f"region clips right/bottom: {desc}"
        if desc.startswith("Transition "):
            assert cx >= 0 and cy - 16 >= 8, f"transition label would clip: {desc}"
        else:
            assert cx - 8 >= 0 and cy + 24 >= 16, f"region label would clip: {desc}"
        for other in self.regions:
            if cx < other["x"] + other["w"] and other["x"] < cx + cw:
                if cy < other["y"] + other["h"] and other["y"] < cy + ch:
                    raise AssertionError(f"region overlap: {desc} vs {other['desc']}")
        self.regions.append(dict(number=len(self.regions) + 1, x=cx, y=cy, w=cw, h=ch, desc=desc))


def frame(c: Svg):
    v = VP[c.vp]
    if c.vp == "mobile":
        c.rect(0, 0, 368, 808)
        c.rect(8, 8, 352, 792, stroke=True)
    else:
        c.rect(0, 0, v["w"], v["h"])
        c.rect(8, 8, v["w"] - 16, v["h"] - 16, stroke=True)


# --------------------------------------------------------------------------- pane kinds
LINE_CAP = {"desktop": 40, "tablet": 40, "mobile": 40}


def _pane_lines(c: Svg, p, x, y, w, inner, vp):
    prepared = []
    for item in p["lines"]:
        text = item[0] if isinstance(item, tuple) else item
        size = item[1] if isinstance(item, tuple) and len(item) > 1 else 12
        color = item[2] if isinstance(item, tuple) and len(item) > 2 else INK
        for line in wrap(text, inner, size, 2):
            prepared.append((line, size, color))
    cy = y
    for line, size, color in prepared[: LINE_CAP[vp]]:
        c.text(x + PAD, cy + BASE[size], line, size, color)
        cy += LANE[size]
    note = f"+{len(prepared) - LINE_CAP[vp]} more lines \u00b7 scrolls below" if len(prepared) > LINE_CAP[vp] else None
    return cy, note


def _pane_note(c: Svg, p, x, y, w, inner, vp):
    return _pane_lines(c, dict(lines=[(t, 12, MUTED) for t in p["lines"]]), x, y, w, inner, vp)


def _pane_list(c: Svg, p, x, y, w, inner, vp):
    rows, cap = p["rows"], VP[vp]["caps"]
    shown = rows[:cap]
    cy = y
    for left, right in shown:
        c.text(x + PAD, cy + BASE[14], fit(left, inner - 168, 14), 14, INK)
        if right:
            c.text(x + w - PAD, cy + BASE[12], fit(right, 144, 12), 12, INK, anchor="end")
        cy += LANE[14]
    note = None
    if len(rows) > cap:
        note = f"+{len(rows) - cap} more rows \u00b7 scrolls below"
    return cy, note


def _pane_table(c: Svg, p, x, y, w, inner, vp):
    cols, rows = p["columns"], p["rows"]
    labels = [col[0] for col in cols]
    weights = [col[1] for col in cols]
    cy = y
    if vp == "mobile":
        for row in rows:
            c.text(x + PAD, cy + BASE[14], fit(row[0], inner, 14), 14, INK)
            cy += LANE[14]
            for i in range(1, min(len(row), len(labels))):
                for line in wrap(f"{labels[i]}: {row[i]}", inner, 12, 2):
                    c.text(x + PAD, cy + BASE[12], line, 12, MUTED)
                    cy += LANE[12]
            c.line(x + PAD, cy, x + w - PAD, cy)
            cy += 8
        return cy, None
    widths = split_widths(inner, weights)
    cx = x + PAD
    for label, cw in zip(labels, widths):
        c.text(cx, cy + BASE[12], fit(label, cw - 8, 12), 12, INK, 600)
        cx += cw
    cy += LANE[12]
    c.line(x + PAD, cy, x + w - PAD, cy)
    cy += 8
    cap = VP[vp]["caps"] + 2
    for row in rows[:cap]:
        cx = x + PAD
        for cell, cw in zip(row, widths):
            c.text(cx, cy + BASE[14], fit(cell, cw - 8, 12), 12, INK)
            cx += cw
        cy += LANE[14]
    note = None
    if len(rows) > cap:
        note = f"+{len(rows) - cap} more rows \u00b7 scrolls below"
    return cy, note


def _pane_fields(c: Svg, p, x, y, w, inner, vp):
    cy = y
    for label, value, state in p["fields"]:
        c.text(x + PAD, cy + BASE[12], fit(label, inner, 12), 12, INK)
        cy += LANE[12]
        c.rect(x + PAD, cy, inner, LANE[14], GREY if state != "live" else WHITE, stroke=True)
        c.text(x + PAD + 8, cy + BASE[14], fit(value, inner - 16, 12), 12, MUTED if state != "live" else INK)
        cy += LANE[14]
    cy, note = _pane_buttons(c, dict(buttons=p.get("buttons", [])), x, cy, w, inner, vp)
    return cy, note


def _pane_buttons(c: Svg, p, x, y, w, inner, vp):
    cy = y
    cx = x + PAD
    for label, disabled in p["buttons"]:
        bw = max(96, r8(len(label) * 7.4 + 32))
        if cx + bw > x + w - PAD:
            cy += LANE[14]
            cx = x + PAD
        c.rect(cx, cy, bw, LANE[14], GREY if disabled else WHITE, stroke=True)
        shown = label if not disabled else label + " (disabled)"
        c.text(cx + 8, cy + BASE[14], fit(shown, bw - 16, 12), 12, MUTED if disabled else INK)
        cx += bw + 8
    cy += LANE[14]
    return cy, None


def _pane_filters(c: Svg, p, x, y, w, inner, vp):
    cy = y
    n = len(p["fields"])
    weights = [1] * n
    if vp == "mobile" or inner < n * 160:
        for label, value in p["fields"]:
            c.text(x + PAD, cy + BASE[12], label, 12, INK)
            cy += LANE[12]
            c.rect(x + PAD, cy, inner, LANE[14], WHITE, stroke=True)
            c.text(x + PAD + 8, cy + BASE[14], fit(value or "any", inner - 16, 12), 12, INK)
            cy += LANE[14]
    else:
        widths = split_widths(inner, weights)
        cx = x + PAD
        for (label, value), cw in zip(p["fields"], widths):
            c.text(cx, cy + BASE[12], label, 12, INK)
            c.rect(cx, cy + LANE[12], cw - 8, LANE[14], WHITE, stroke=True)
            c.text(cx + 8, cy + LANE[12] + BASE[14], fit(value or "any", cw - 24, 12), 12, INK)
            cx += cw
        cy += LANE[12] + LANE[14]
    return _pane_buttons(c, dict(buttons=p.get("buttons", [])), x, cy, w, inner, vp)


def _pane_quote(c: Svg, p, x, y, w, inner, vp):
    cy = y
    lines = wrap(p["text"], inner - 16, 12, 3)
    block_h = len(lines) * LANE[12] + 16
    c.rect(x + PAD, cy, inner, block_h, GREY)
    for line in lines:
        c.text(x + PAD + 8, cy + 8 + BASE[12], line, 12, INK)
        cy += LANE[12]
    cy += 8
    if p.get("note"):
        pass
    return cy, None


def _pane_graph(c: Svg, p, x, y, w, inner, vp):
    area = r8(p.get("height", 200))
    nw = 112 if inner >= 152 else inner
    nodes = []
    for label, fx, fy in p["nodes"]:
        nx = x + PAD + r8(fx * (inner - nw))
        ny = y + r8(fy * (area - LANE[14]))
        nodes.append((label, nx, ny))
    for a, b in p["edges"]:
        ax, ay = nodes[a][1] + nw // 2, nodes[a][2] + 16
        bx, by = nodes[b][1] + nw // 2, nodes[b][2] + 16
        c.line(ax, ay, bx, by)
    for label, nx, ny in nodes:
        c.rect(nx, ny, nw, LANE[14], WHITE, stroke=True)
        c.text(nx + 8, ny + BASE[14], fit(label, nw - 16, 12), 12, INK)
    return y + area, None


def _pane_map(c: Svg, p, x, y, w, inner, vp):
    area = r8(p.get("height", 240))
    c.rect(x + PAD, y, inner, area, GREY, stroke=True)
    c.line(x + PAD + 24, y + 24, x + w - PAD - 24, y + area - 24)
    c.line(x + w - PAD - 24, y + 24, x + PAD + 24, y + area - 24)
    for fx, fy in p["markers"]:
        mx = x + PAD + r8(fx * (inner - 24))
        my = y + r8(fy * (area - 40))
        c.rect(mx, my, 16, 16, WHITE, stroke=True)
    c.text(x + PAD + 8, y + area - 16, fit(p.get("label", "Map placeholder \u00b7 no tiles"), inner - 16, 12), 12, INK)
    return y + area, None


def _pane_timeline(c: Svg, p, x, y, w, inner, vp):
    entries, cap = p["entries"], VP[vp]["caps"] - 1
    cy = y
    for idx, (when, what, status) in enumerate(entries[:cap]):
        c.rect(x + PAD, cy, 8, 8, INK)
        c.line(x + PAD + 8, cy + 8, x + PAD + 8, cy + 48)
        c.text(x + PAD + 32, cy + BASE[12], fit(when, inner - 56, 12), 12, MUTED)
        c.text(x + PAD + 32, cy + LANE[12] + BASE[14], fit(what, inner - 64 - 120, 14), 14, INK)
        c.text(x + w - PAD, cy + LANE[12] + BASE[12], fit(status, 112, 12), 12, INK, anchor="end")
        cy += 56
    return cy, None


def _pane_pipeline(c: Svg, p, x, y, w, inner, vp):
    cy = y
    cap = VP[vp]["caps"] + 1
    for stage, status in p["rows"][:cap]:
        c.text(x + PAD, cy + BASE[14], fit(stage, inner - 160, 14), 14, INK)
        recorded = status not in ("unrecorded", "not recorded")
        c.rect(x + w - PAD - 128, cy, 128, LANE[14], GREY if not recorded else WHITE, stroke=True)
        c.text(x + w - PAD - 64, cy + BASE[14], fit(status, 112, 12), 12, MUTED if not recorded else INK, anchor="middle")
        cy += LANE[14] + 8
    return cy, None


def _pane_report(c: Svg, p, x, y, w, inner, vp):
    cy = y
    box_h = 160
    c.rect(x + PAD, cy, inner, box_h, GREY)
    for i, frac in enumerate((0.8, 0.6, 0.7, 0.5)):
        c.rect(x + PAD + 8, cy + 16 + i * 32, r8((inner - 16) * frac), 8, INK)
    cy += box_h + 8
    buttons = [(label, disabled) for label, disabled in p["downloads"]]
    cy, _ = _pane_buttons(c, dict(buttons=buttons), x, cy, w, inner, vp)
    return cy, None


def _pane_skeleton(c: Svg, p, x, y, w, inner, vp):
    cy = y
    if p.get("msg"):
        c.text(x + PAD, cy + BASE[14], fit(p["msg"], inner, 14), 14, INK)
        cy += LANE[14]
    for width in p["bars"]:
        c.rect(x + PAD, cy, min(r8(width), inner), 24, GREY)
        cy += 32
    return cy, None


def _pane_empty(c: Svg, p, x, y, w, inner, vp):
    cy = y
    c.rect(x + PAD, cy, inner, 96, WHITE, stroke=True)
    c.text(x + PAD + 16, cy + 40, fit(p["msg"], inner - 32, 14), 14, INK)
    c.text(x + PAD + 16, cy + 64, fit(p["meta"], inner - 32, 12), 12, MUTED)
    cy += 96
    return cy, None


def _pane_errorbox(c: Svg, p, x, y, w, inner, vp):
    cy = y
    c.rect(x + PAD, cy, inner, 120, WHITE, stroke=True)
    c.text(x + PAD + 16, cy + 32, fit(p["msg"], inner - 32, 14), 14, INK, 600)
    yy = cy + 56
    for line in p.get("detail", [])[:2]:
        c.text(x + PAD + 16, yy, fit(line, inner - 32, 12), 12, MUTED)
        yy += LANE[12]
    cy += 120
    if p.get("buttons"):
        cy += 8
        cy, _ = _pane_buttons(c, dict(buttons=p["buttons"]), x, cy, w, inner, vp)
    return cy, None


def _pane_selectors(c: Svg, p, x, y, w, inner, vp):
    cy = y
    slots = p["slots"]
    if inner >= 480 and len(slots) > 1:
        rows = [slots[i:i + 2] for i in range(0, len(slots), 2)]
        for pair in rows:
            widths = split_widths(inner, [1] * len(pair))
            cx = x + PAD
            for (label, value), cw in zip(pair, widths):
                c.text(cx, cy + BASE[12], label, 12, INK)
                c.rect(cx, cy + LANE[12], cw - 8, LANE[14], WHITE, stroke=True)
                c.text(cx + 8, cy + LANE[12] + BASE[14], fit(value, cw - 24, 12), 12, INK)
                cx += cw
            cy += LANE[12] + LANE[14]
    else:
        for label, value in slots:
            c.text(x + PAD, cy + BASE[12], label, 12, INK)
            cy += LANE[12]
            c.rect(x + PAD, cy, inner, LANE[14], WHITE, stroke=True)
            c.text(x + PAD + 8, cy + BASE[14], fit(value, inner - 16, 12), 12, INK)
            cy += LANE[14]
    return _pane_buttons(c, dict(buttons=p["buttons"]), x, cy, w, inner, vp)


def _pane_banner(c: Svg, p, x, y, w, inner, vp):
    c.rect(x + PAD, y, inner, 64, WHITE, stroke=True)
    c.text(x + PAD + 16, y + 24, fit(p["msg"], inner - 32, 14), 14, INK, 600)
    c.text(x + PAD + 16, y + 48, fit(p["meta"], inner - 32, 12), 12, MUTED)
    return y + 64, None


KINDS = {
    "lines": _pane_lines,
    "note": _pane_note,
    "list": _pane_list,
    "table": _pane_table,
    "fields": _pane_fields,
    "buttons": _pane_buttons,
    "filters": _pane_filters,
    "quote": _pane_quote,
    "graph": _pane_graph,
    "map": _pane_map,
    "timeline": _pane_timeline,
    "pipeline": _pane_pipeline,
    "report": _pane_report,
    "skeleton": _pane_skeleton,
    "empty": _pane_empty,
    "errorbox": _pane_errorbox,
    "selectors": _pane_selectors,
    "banner": _pane_banner,
}


def pane_content(c: Svg, p, x, y, w, vp):
    inner = w - 2 * PAD
    cy = y + PAD
    if p.get("title"):
        c.text(x + PAD, cy + BASE[14], fit(p["title"], inner, 14), 14, INK, 600)
        cy += LANE[14]
    if p.get("sub"):
        c.text(x + PAD, cy + BASE[12], fit(p["sub"], inner, 12), 12, MUTED)
        cy += LANE[12]
    cy, auto_note = KINDS[p["kind"]](c, p, x, cy, w, inner, vp)
    note = p.get("note") or auto_note
    if note:
        c.text(x + PAD, cy + BASE[12], fit(note, inner, 12), 12, MUTED)
        cy += LANE[12]
    return cy - y + PAD


def pane_height(p, w, vp) -> int:
    return pane_content(Svg(vp), p, 0, 0, w, vp)


def draw_pane(c: Svg, p, x, y, w, vp):
    h = pane_height(p, w, vp)
    c.rect(x, y, w, h, WHITE, stroke=True)
    pane_content(c, p, x, y, w, vp)
    return h


# --------------------------------------------------------------------------- chrome
def draw_rail(c: Svg, x, y, w, h, active):
    c.rect(x, y, w, h, WHITE, stroke=True)
    c.text(x + PAD, y + BASE[14], "TRIANGULATE", 14, INK, 600)
    c.text(x + PAD, y + LANE[14] + BASE[12], "Evidence workbench \u00b7 proposal", 12, MUTED)
    cy = y + 56
    c.line(x + PAD, cy, x + w - PAD, cy)
    cy += LANE[12]
    c.text(x + PAD, cy + BASE[12], "NAVIGATE", 12, INK, 600)
    cy += LANE[12]
    for item in NAV_ITEMS:
        c.text(x + PAD, cy + BASE[14], item, 14, INK, 600 if item == active else None)
        cy += LANE[14]
    cy += 8
    c.line(x + PAD, cy, x + w - PAD, cy)
    cy += LANE[12]
    c.text(x + PAD, cy + BASE[12], "RECENT CASES", 12, INK, 600)
    cy += LANE[12]
    for case in ("case-2201-0417", "case-2199-1180", "case-2198-0922"):
        c.text(x + PAD, cy + BASE[12], case, 12, INK)
        cy += LANE[12]
    cy += 8
    c.line(x + PAD, cy, x + w - PAD, cy)
    cy += LANE[12]
    c.text(x + PAD, cy + BASE[12], "READ-ONLY BY DEFAULT", 12, INK, 600)
    cy += LANE[12]
    for line in ("GET reads only", "local / trusted", "ingest + runs via CLI"):
        c.text(x + PAD, cy + BASE[12], line, 12, INK if line[0].isupper() else MUTED)
        cy += LANE[12]
    c.text(x + PAD, y + h - PAD, "Wireframe \u00b7 synthetic data", 12, MUTED)
    c.region(x, y, w, h, "Primary navigation \u2014 GET reads only; ingest, rerun, rebuild and recovery stay CLI-only.")


def draw_topbar(c: Svg, x, y, w, active):
    h = 48
    c.rect(x, y, w, h, WHITE, stroke=True)
    c.text(x + PAD, y + BASE[14], "TRIANGULATE", 14, INK, 600)
    if c.vp == "tablet":
        cx = x + PAD + r8(len("TRIANGULATE") * 8.6 + 24)
        for item in NAV_ITEMS:
            if cx + len(item) * 7 > x + w - PAD:
                break
            c.text(cx, y + 24, item, 12, INK, 600 if item == active else None)
            cx += r8(len(item) * 7.4 + 16)
        c.region(x, y, w, h, "Primary navigation (top bar) \u2014 GET reads only; CLI owns ingest and runs.")
    else:
        c.rect(x + w - PAD - 64, y + 8, 64, 32, WHITE, stroke=True)
        c.text(x + w - PAD - 32, y + 8 + BASE[12], "Menu", 12, INK, anchor="middle")
        c.region(x, y, w, h, "Primary navigation (menu) \u2014 all seven destinations remain reachable; CLI owns ingest.")


def header_parts(defn, vp, w):
    metas = defn.get("meta", [])[:2]
    actions = defn.get("actions", []) if vp == "desktop" and w >= 700 else []
    tsize = 14 if vp == "mobile" else 20
    ax_total = sum(max(88, r8(len(a) * 7.4 + 24)) + 8 for a in actions)
    title_lines = wrap(defn["title"], w - 2 * PAD - ax_total - 24, tsize, 2 if vp == "mobile" else 1)
    h = PAD + LANE[tsize] * len(title_lines) + LANE[12] * len(metas) + 8
    return metas, actions, tsize, title_lines, h


def header_height(defn, vp, w, meta_count=None):
    metas, _actions, tsize, title_lines, _h = header_parts(defn, vp, w)
    return PAD + LANE[tsize] * len(title_lines) + LANE[12] * (len(metas) if meta_count is None else meta_count) + 8


def draw_header(c: Svg, spec, x, y, w, vp):
    metas, actions, tsize, title_lines, h = header_parts(spec, vp, w)
    c.rect(x, y, w, h, WHITE, stroke=True)
    cy = y + PAD
    for line in title_lines:
        c.text(x + PAD, cy + BASE[tsize], line, tsize, INK, 600)
        cy += LANE[tsize]
    for meta in metas:
        c.text(x + PAD, cy + BASE[12], fit(meta, w - 2 * PAD, 12), 12, MUTED)
        cy += LANE[12]
    cx = x + w - PAD
    for label in reversed(actions):
        bw = max(88, r8(len(label) * 7.4 + 24))
        cx -= bw
        c.rect(cx, y + PAD, bw, LANE[14], WHITE, stroke=True)
        c.text(cx + 8, y + PAD + BASE[14], fit(label, bw - 16, 12), 12, INK)
        cx -= 8
    c.region(x, y, w, h, spec.get("header_desc") or f"{spec['title']} header \u2014 title, synthetic context and available actions.")
    return h


def draw_frame_header(c: Svg, defn, x, y, w, vp, idx, total, prev_file, next_file):
    label = f"Part {idx} of {total} \u00b7 companion frames carry the rest"
    navs = []
    if prev_file:
        navs.append(f"previous: {prev_file}")
    if next_file:
        navs.append(f"next: {next_file}")
    spec = dict(defn)
    spec["meta"] = [label, " \u00b7 ".join(navs) if navs else "single frame"]
    spec["actions"] = []
    spec["header_desc"] = f"{defn['title']} \u2014 frame {idx} of {total}; full coverage continues in the named companion frame."
    return draw_header(c, spec, x, y, w, vp)


def tabs_height(defn, vp, w):
    name = defn["tabs"]
    if vp == "mobile":
        return 56
    widths = [len(n) * 7.4 for n in name]
    total = sum(widths) + 24 * (len(name) - 1) + 2 * PAD
    return PAD + LANE[12] * (1 if total <= w else 2) + 8


def draw_tabs(c: Svg, spec, x, y, w, vp):
    names = spec["tabs"]
    active = spec.get("tab_active", names[0])
    if vp == "mobile":
        h = 56
        c.rect(x, y, w, h, WHITE, stroke=True)
        c.text(x + PAD, y + BASE[14], active, 14, INK, 600)
        c.text(x + PAD, y + LANE[14] + BASE[12], f"{len(names)} tabs \u00b7 tab strip scrolls horizontally", 12, MUTED)
        c.region(x, y, w, h, f"Case tabs ({len(names)}) \u2014 active {active}; the strip scrolls, no tab is removed.")
        return h
    h = tabs_height(spec, vp, w)
    lines = 1 if h == PAD + LANE[12] + 8 else 2
    c.rect(x, y, w, h, WHITE, stroke=True)
    cy = y + PAD
    per = (len(names) + lines - 1) // lines if lines > 1 else len(names)
    for line_no in range(lines):
        cx = x + PAD
        for name in names[line_no * per : (line_no + 1) * per]:
            c.text(cx, cy + BASE[12], name, 12 if lines > 1 else 14, INK, 600 if name == active else None)
            cx += r8(len(name) * 7.4 + 20)
        cy += LANE[12]
    c.region(x, y, w, h, f"Case tabs ({len(names)}) \u2014 active {active}; tabs are navigation, not state changes.")
    return h


# --------------------------------------------------------------------------- screen assembly
COMPACT_TOP = 48


def pane_items(defn):
    out = []
    for row in defn["body"]:
        for _wt, pane in row:
            out.append(pane)
    return out


def _main_xw(vp):
    v = VP[vp]
    if vp == "desktop":
        x = v["x0"] + v["rail"] + GAPX
        return x, v["x1"] - x
    return v["x0"], v["x1"] - v["x0"]


def frame1_body_y(defn, vp, w):
    v = VP[vp]
    y = v["y0"] if vp == "desktop" else v["y0"] + COMPACT_TOP + GAPY
    y += header_height(defn, vp, w) + GAPY
    if defn.get("tabs"):
        y += tabs_height(defn, vp, w) + GAPY
    return y


def compact_body_y(defn, vp, w):
    v = VP[vp]
    return v["y0"] + COMPACT_TOP + GAPY + header_height(defn, vp, w, meta_count=2) + GAPY


def split_pane(pid, p, cap, w, vp):
    kind = p["kind"]
    key = {"fields": "fields", "lines": "lines", "note": "lines", "table": "rows",
           "list": "rows", "timeline": "entries", "pipeline": "rows"}.get(kind)
    if key is None:
        raise AssertionError(f"pane {pid} is {pane_height(p, w, vp)} tall, over {cap}, and not fragmentable")
    source = p[key]

    def make(sub, last):
        q = dict(p)
        q[key] = sub
        q["note"] = p.get("note") if last else None
        if kind == "fields" and not last:
            q["buttons"] = []
        if kind == "lines" and not last:
            q["lines"] = sub
        return q

    def fits(items, last):
        return pane_height(make(items, last), w, vp) <= cap

    def refine(items, last):
        if fits(items, last):
            return [items]
        if len(items) <= 1:
            raise AssertionError(f"pane {pid} of kind {kind}: a single {key} item exceeds the "
                                 f"{cap}px frame capacity")
        mid = len(items) // 2
        return refine(items[:mid], False) + refine(items[mid:], last)

    chunks = refine(list(source), True)
    units = []
    for i, sub in enumerate(chunks):
        unit = make(sub, i == len(chunks) - 1)
        height = pane_height(unit, w, vp)
        assert height <= cap, f"pane {pid} fragment {i + 1} measures {height} over {cap}"
        units.append((f"{pid}.{i + 1}", unit))
    return units


def plan_frames(defn, vp):
    """Return (frames, pane ids in body order). Each frame lists rendered pane units."""
    v = VP[vp]
    panes = pane_items(defn)
    ids = [f"p{i + 1}" for i in range(len(panes))]
    w = _main_xw(vp)[1]
    frames = []
    if vp == "desktop":
        rows = defn["body"]
        y = frame1_body_y(defn, vp, w)
        cap = v["y1"] - y
        used, first = 0, []
        for row in rows:
            widths = split_widths(w, [wt for wt, _ in row])
            h = max(pane_height(p, pw, vp) for (wt, p), pw in zip(row, widths))
            need = h + (GAPY if first else 0)
            if used + need > cap:
                break
            first.append(row)
            used += need
        if first:
            frames.append(dict(layout="rows", rows=first, compact=False))
            prefix = sum(len(row) for row in first)
            rest = [(ids[i], panes[i]) for i in range(prefix, len(panes))]
        else:
            row0 = rows[0]
            stack, carry = [], []
            for idx, pane in enumerate(p for _wt, p in row0):
                chunks = split_pane(ids[idx], pane, cap, w, vp)
                stack.append(chunks[0])
                carry += chunks[1:]
            frames.append(dict(layout="stack", units=stack, compact=False))
            rest = carry + [(ids[i], panes[i]) for i in range(len(row0), len(panes))]
    else:
        y = frame1_body_y(defn, vp, w)
        cap = v["y1"] - y
        used, first, rest = 0, [], []
        for i, pane in enumerate(panes):
            need = pane_height(pane, w, vp) + (GAPY if first else 0)
            if used + need <= cap:
                first.append((ids[i], pane))
                used += need
                continue
            if not first:
                chunks = split_pane(ids[i], pane, cap, w, vp)
                first.append(chunks[0])
                rest = chunks[1:] + [(ids[j], panes[j]) for j in range(i + 1, len(panes))]
            else:
                rest = [(ids[j], panes[j]) for j in range(i, len(panes))]
            break
        assert first, f"{defn['id']}/{vp}: frame 1 body is empty"
        frames.append(dict(layout="stack", units=first, compact=False))
    if not rest:
        return frames, ids
    cap2 = v["y1"] - compact_body_y(defn, vp, w)
    while rest:
        units, used = [], 0
        while rest:
            pid, pane = rest[0]
            h = pane_height(pane, w, vp)
            need = h + (GAPY if units else 0)
            if used + need <= cap2:
                units.append((pid, pane))
                used += need
                rest.pop(0)
                continue
            if not units:
                chunks = split_pane(pid, pane, cap2, w, vp)
                assert chunks and all(pane_height(u, w, vp) <= cap2 for _p, u in chunks), \
                    f"{defn['id']}/{vp}: {pid} fragments exceed the compact frame"
                units.append(chunks[0])
                rest = chunks[1:] + rest[1:]
            break
        used = sum(pane_height(u, w, vp) for _p, u in units) + GAPY * (len(units) - 1)
        assert used <= cap2, f"{defn['id']}/{vp}: compact frame body {used} over {cap2}"
        frames.append(dict(layout="stack", units=units, compact=True))
    return frames, ids


def rendered_panes(frame):
    if frame["layout"] == "rows":
        out = []
        for row in frame["rows"]:
            out += [p for _wt, p in row]
        return out
    return [p for _pid, p in frame["units"]]


def render_frame(defn, vp, fr, idx, total, files, id_map):
    v, c = VP[vp], Svg(vp)
    frame(c)
    compact = fr["compact"]
    if not compact and vp == "desktop":
        draw_rail(c, v["x0"], v["y0"], v["rail"], v["y1"] - v["y0"], defn.get("nav", "Cases"))
        x, w = _main_xw(vp)
        y = v["y0"]
    else:
        draw_topbar(c, v["x0"], v["y0"], v["x1"] - v["x0"], defn.get("nav", "Cases"))
        x, w = _main_xw(vp)
        y = v["y0"] + COMPACT_TOP + GAPY
    if compact:
        h = draw_frame_header(c, defn, x, y, w, vp, idx, total, files.get(idx - 1), files.get(idx + 1))
        y += h + GAPY
    else:
        h = draw_header(c, defn, x, y, w, vp)
        y += h + GAPY
        if defn.get("tabs"):
            h = draw_tabs(c, defn, x, y, w, vp)
            y += h + GAPY

    def emit(pane, px, pw, pid=None):
        pid = pid or id_map[id(pane)]
        part = f" \u00b7 frame {idx} of {total}"
        c.pane(pid)
        ph = draw_pane(c, pane, px, y, pw, vp)
        c.end_pane()
        c.region(px, y, pw, ph, pane["desc"] + part)
        return ph

    if fr["layout"] == "rows":
        for row in fr["rows"]:
            widths = split_widths(w, [wt for wt, _ in row])
            cx, heights = x, []
            for (wt, pane), pw in zip(row, widths):
                heights.append(emit(pane, cx, pw))
                cx += pw + GAPX
            y += max(heights) + GAPY
        y -= GAPY
    else:
        for unit_pid, pane in fr["units"]:
            ph = emit(pane, x, w, unit_pid)
            y += ph + GAPY
        y -= GAPY
    assert y <= v["y1"], f"{defn['id']}/{vp} frame {idx} overflows by {y - v['y1']}"
    return c


# --------------------------------------------------------------------------- pane shorthands
def L(title, rows, desc, note=None, sub=None, **kw):
    return dict(kind="list", title=title, rows=rows, desc=desc, note=note, sub=sub, **kw)


def TB(title, columns, rows, desc, note=None, **kw):
    return dict(kind="table", title=title, columns=columns, rows=rows, desc=desc, note=note, **kw)


def LN(title, lines, desc, note=None, **kw):
    return dict(kind="lines", title=title, lines=lines, desc=desc, note=note, **kw)


def NT(title, lines, desc):
    return dict(kind="note", title=title, lines=lines, desc=desc)


def BT(buttons, desc, title=None, **kw):
    return dict(kind="buttons", title=title, buttons=buttons, desc=desc, **kw)


def FLD(title, fields, buttons, desc, note=None, **kw):
    return dict(kind="fields", title=title, fields=fields, buttons=buttons, desc=desc, note=note, **kw)


def FLT(fields, buttons, desc, **kw):
    return dict(kind="filters", fields=fields, buttons=buttons, desc=desc, **kw)


def QTE(title, text, desc, note=None, **kw):
    return dict(kind="quote", title=title, text=text, desc=desc, note=note, **kw)


def GRP(title, nodes, edges, desc, note=None, height=200):
    return dict(kind="graph", title=title, nodes=nodes, edges=edges, desc=desc, note=note, height=height)


def MAP(title, markers, desc, note=None, label="Map placeholder \u00b7 no tiles"):
    return dict(kind="map", title=title, markers=markers, desc=desc, note=note, label=label)


def TML(title, entries, desc, note=None, **kw):
    return dict(kind="timeline", title=title, entries=entries, desc=desc, note=note, **kw)


def PPL(title, rows, desc, note=None, **kw):
    return dict(kind="pipeline", title=title, rows=rows, desc=desc, note=note, **kw)


def RPT(title, downloads, desc, note=None):
    return dict(kind="report", title=title, downloads=downloads, desc=desc, note=note)


def EMP(title, msg, meta, desc, note=None):
    return dict(kind="empty", title=title, msg=msg, meta=meta, desc=desc, note=note)


def SKL(title, msg, bars, desc, note=None):
    return dict(kind="skeleton", title=title, msg=msg, bars=bars, desc=desc, note=note)


def ERR(title, msg, detail, buttons, desc, note=None):
    return dict(kind="errorbox", title=title, msg=msg, detail=detail, buttons=buttons, desc=desc, note=note)


def SEL(title, slots, buttons, desc, note=None, **kw):
    return dict(kind="selectors", title=title, slots=slots, buttons=buttons, desc=desc, note=note, **kw)


def BAN(msg, meta, desc):
    return dict(kind="banner", msg=msg, meta=meta, desc=desc)


PROPOSAL = "Proposal \u00b7 synthetic \u00b7 not built"


# --------------------------------------------------------------------------- 24 primary screens
SCREENS = [
    dict(
        id="dashboard", kind="screen", title="Dashboard \u2014 case portfolio", nav="Dashboard",
        route="/dashboard", context="top-level route",
        meta=[f"Observed case rows only \u00b7 {PROPOSAL}", "No KPI tiles, scores or health metrics"],
        actions=["Refresh"],
        body=[
            [(2, TB("Cases", [("Case", 3), ("Status", 2), ("Coverage", 2)],
                   [("case-2201-0417", "active", "partial"), ("case-2199-1180", "active", "complete"),
                    ("case-2198-0922", "failed", "failed"), ("case-2197-0733", "closed", "complete")],
                   "Case portfolio \u2014 observed status and acquisition coverage per case, not a truth score.")),
             (1, LN("Observed totals", ["4 cases \u00b7 12 articles", "31 events \u00b7 7 review items", "Counts are observed rows, not health"],
                    "Observed totals \u2014 row counts only; no confidence, health or trend claim."))],
            [(1, L("Recent runs", [("run-0007 \u00b7 case-2201-0417", "succeeded"), ("run-0006 \u00b7 case-2199-1180", "partial"),
                                   ("run-0005 \u00b7 case-2198-0922", "failed")],
                   "Recent grouped runs \u2014 recorded status and coverage across cases.")),
             (1, NT("Entry points", ["Monitoring: recorded status only", "AI info: capabilities, no chat"],
                    "Navigation entry points \u2014 monitoring and AI info are readers, not control planes."))],
        ],
    ),
    dict(
        id="case-explorer", kind="screen", title="Case explorer", nav="Cases",
        route="/cases", context="top-level route",
        meta=[f"Browse cases \u00b7 GET only \u00b7 {PROPOSAL}"],
        body=[
            [(1, FLT([("Query", ""), ("Status", "all"), ("Sort", "updated")], [("Apply", False), ("Clear", False)],
                     "Case filters \u2014 literal query, status and sort; no hidden full-text index is claimed."))],
            [(1, TB("Cases", [("Case", 3), ("Status", 2), ("Coverage", 2), ("Updated", 3)],
                   [("case-2201-0417", "active", "partial", "2026-11-20"), ("case-2199-1180", "active", "complete", "2026-11-19"),
                    ("case-2198-0922", "failed", "failed", "2026-11-18"), ("case-2197-0733", "closed", "complete", "2026-11-16")],
                   "Case table \u2014 per-case observed status, coverage and update time."))],
            [(1, BT([("Previous page", True), ("Next page", False)],
                    "Pagination \u2014 disabled Previous on the first page; no synthetic totals."))],
        ],
    ),
    dict(
        id="operator-launch", kind="screen", title="Operator launch guide", nav="Cases",
        route="/cases/new", context="operator guide (CLI, not a browser form)",
        meta=[f"CLI guide \u2014 no browser ingestion form \u00b7 {PROPOSAL}", "Commands run locally under the local/trusted assumption"],
        body=[
            [(2, LN("Launch steps (CLI)", ["1. uv run triangulate ingest", "2. uv run triangulate process",
                                            "3. uv run triangulate fetch-topic \"quartz tender\""],
                   "Launch steps \u2014 the only ingestion path is a local CLI command, not this page.")),
             (1, TB("Prerequisites", [("Check", 3), ("State", 2)],
                    [("Database", "local"), ("Writer", "single"), ("Network", "operator")],
                    "Prerequisites \u2014 local database, single writer, operator-run network access."))],
            [(1, NT("Why no form", ["Ingest, rerun, rebuild and recovery are CLI-only", "This page never posts a case or a run"],
                    "Scope note \u2014 the browser exposes reads and three narrow review POSTs only."))],
        ],
    ),
    dict(
        id="case-overview", kind="screen", tabs=[
            "Overview", "Evidence", "Claims", "Compare", "Parties", "Map", "Timeline",
            "Exceptions", "Report", "Changes", "Search", "Run history"],
        tab_active="Overview", route="/cases/:id/", context="case index tab (overview), path ''",
        title="Case overview", nav="Cases",
        meta=["case-2201-0417 · query 'quartz tender' · example.invalid", f"status review ready · stage extraction · automation off · {PROPOSAL}"],
        actions=["Refresh"],
        body=[
            [(2, TB("Observed counts", [("Item", 3), ("Observed", 2), ("Note", 4)],
                    [("Articles", "12", "observed rows"), ("Events", "31", "observed rows"),
                     ("Review items", "7", "observed rows"), ("Exceptions", "2", "1 unresolved")],
                    "Observed counts — only observed rows; a failed read is unavailable, never zero.")),
             (1, LN("Case status", ["Status: review ready", "Stage: extraction", "Automation: off", "Claim states: per claim"],
                    "Case status — review readiness, stage and automation; claim verification states are separate per claim."))],
            [(1, FLD("Review decision", [("Rationale", "", "empty")],
                     [("Approve", False), ("Action Required", False), ("Reject", False)],
                     "Review decision — rationale plus Approve, Action Required or Reject; no extra decision dropdown.",
                     note="API also accepts defer/exception; this browser form offers only these three decision values."))],
        ],
    ),
    dict(
        id="review-annotation", kind="screen", tabs=[
            "Overview", "Evidence", "Claims", "Compare", "Parties", "Map", "Timeline",
            "Exceptions", "Report", "Changes", "Search", "Run history"],
        tab_active="Overview", route="/cases/:id/", context="review decision + annotation form",
        title="Review and annotation", nav="Cases",
        meta=[f"Two narrow human review POSTs · {PROPOSAL}"],
        body=[
            [(1, FLD("Review decision", [("Rationale", "", "empty")],
                     [("Approve", False), ("Action Required", False), ("Reject", False)],
                     "Review decision form — rationale plus the three decision buttons; decision value is the pressed control, not a dropdown.",
                     required=["Rationale", "Approve", "Action Required", "Reject"])),
             (1, FLD("New annotation", [("Type", "comment", "live"), ("Target", "claim", "live"),
                                        ("Target ID", "claim-8898", "live"), ("Content", "", "empty")],
                     [("Save annotation", True)],
                     "Annotation form — type comment/flag/context, target case/claim/evidence/exception/narrative, target ID and content; save disabled while empty or pending.",
                     required=["Type", "Target", "Target ID", "Content", "Save annotation"]))],
            [(1, L("Existing annotations", [("annotation-1041 \u00b7 comment", "claim-8898"), ("annotation-1038 \u00b7 flag", "ev-c71a"),
                                            ("annotation-1031 \u00b7 context", "exc-2310")],
                   "Recorded annotations — stored rows with type and target; no attribution beyond the stored record.")),
             (1, NT("Reader rule", ["An annotation is a human note, not a claim verdict", "Saving writes to the reader DB; ingest stays CLI-only"],
                    "Reader-rule note — the annotation POST is an explicit, labelled exception to the GET-only reader rule."))],
        ],
    ),
    dict(
        id="evidence-gallery", kind="screen", tabs=[
            "Overview", "Evidence", "Claims", "Compare", "Parties", "Map", "Timeline",
            "Exceptions", "Report", "Changes", "Search", "Run history"],
        tab_active="Evidence", route="/cases/:id/evidence", context="case tab 2 of 12",
        title="Evidence gallery", nav="Cases",
        meta=[f"Provided extraction tier, not truth \u00b7 {PROPOSAL}"],
        body=[
            [(1, FLT([("Tier", "All"), ("Captured", "any"), ("Publisher", "any")], [("Apply", False), ("Clear", False)],
                     "Evidence filters \u2014 All/High/Medium/Low/Unknown are provided extraction tiers, not truth levels."))],
            [(1, TB("Evidence", [("Source", 4), ("Publisher", 3), ("Tier", 2), ("Captured", 2)],
                   [("Regional Herald (synthetic)", "example.invalid", "High", "yes"),
                    ("Wire Desk (synthetic)", "example.invalid", "Medium", "yes"),
                    ("Civic Ledger (synthetic)", "example.invalid", "Unknown", "no"),
                    ("Trade Bulletin (synthetic)", "example.invalid", "Low", "yes")],
                   "Evidence table \u2014 source, publisher and provided tier; missing capture says unavailable.",
                   note="Tiers: All/High/Medium/Low/Unknown are provided metadata, not truth."))],
            [(1, L("Selected source", [("Regional Herald (synthetic)", "ev-c71a"), ("Captured cap-9f31 \u00b7 tier High", "provided"), ("Verification: model \u00b7 legacy_unknown", "recorded")],
                   "Selected source pane \u2014 title, capture pointer, provided tier and stored verification metadata labelled model/legacy_unknown; never certified truth.")),
             (1, BT([("Inspect source", False), ("Open source", False), ("Verification details", False)],
                    "Selected-source actions \u2014 Inspect source, safe HTTP(S) Open source and Verification details.",
                    required=["Inspect source", "Open source", "Verification details"]))],
            [(1, BT([("Previous page", True), ("Next page", False)],
                    "Pagination \u2014 filter and page state is URL-persisted; no synthetic total."))],
        ],
    ),
    dict(
        id="claims", kind="screen", tabs=[
            "Overview", "Evidence", "Claims", "Compare", "Parties", "Map", "Timeline",
            "Exceptions", "Report", "Changes", "Search", "Run history"],
        tab_active="Claims", route="/cases/:id/claims", context="case tab 3 of 12",
        title="Claims", nav="Cases",
        meta=[f"reported_by / uncertain only for generated links \u00b7 {PROPOSAL}"],
        body=[
            [(2, TB("Claims", [("Claim", 5), ("Sources", 2), ("Alignment", 2)],
                   [("claim-8898 \u00b7 tender notice", "2", "exact"), ("claim-8897 \u00b7 budget line", "1", "uncertain"),
                    ("claim-8896 \u00b7 award date", "3", "exact"), ("claim-8895 \u00b7 official denial", "1", "not_provided")],
                   "Claims list \u2014 cluster text, linked source count and alignment state; generated relations are reported_by or uncertain.")),
             (1, LN("Selected claim", ["claim-8898 \u00b7 tender notice", "Relation: reported_by", "Frozen citation: citation-3312", "Model assessment: unknown origin"],
                    "Selected claim detail \u2014 frozen citation reference, effective relation and assessment provenance."))],
            [(1, BT([("Inspect evidence", False), ("Open frozen citation", False)],
                    "Claim actions \u2014 Inspect evidence opens the inspector; Open frozen citation opens the immutable citation reader.",
                    required=["Inspect evidence", "Open frozen citation"]))],
            [(1, LN("Expanded claim detail", ["Arbiter Analysis (model-labelled)", "Classification: allegation \u00b7 rationale recorded",
                                                "Party positions: for 2 \u00b7 against 1 \u00b7 neutral 1", "Consensus: divided \u00b7 not truth"],
                    "Expanded claim detail \u2014 model-labelled Arbiter classification, rationale and recorded for/against/neutral party positions; consensus is not truth.")),
             (1, NT("Provenance", ["Assessment origin: model \u00b7 version unrecorded", "No confidence or truth score", "Frozen citation link opens the inspector"],
                    "Detail provenance \u2014 model origin stays visible and the frozen citation links to the inspector."))],
        ],
    ),
    dict(
        id="capture-inspector", kind="screen", tabs=[
            "Overview", "Evidence", "Claims", "Compare", "Parties", "Map", "Timeline",
            "Exceptions", "Report", "Changes", "Search", "Run history"],
        tab_active="Evidence", route="/cases/:id/evidence?claim=&evidence=&capture=", context="inspector split view",
        title="Capture inspector", nav="Cases",
        meta=[f"Immutable capture reads only · {PROPOSAL}"],
        body=[
            [(1, LN("Claim and citation", ["claim-8898 · tender notice", "Relation: reported_by · alignment: exact", "citation-3312 · frozen claim text", "Assessment origin: model · version unrecorded"],
                    "Claim and immutable citation — frozen claim text, relationship and model assessment provenance.")),
             (1, LN("Capture metadata", ["observed: 2026-11-20 · recorded: 2026-11-20", "published: unavailable", "text_sha256: 4f1c…a9 (short prefix)", "extraction scope: body prefix, recorded"],
                    "Capture metadata — publisher host, observation and recording times, hash, published-unavailable and recorded extraction scope."))],
            [(1, QTE("Captured passage (synthetic)", "Mock example only: \"the tender was announced in the regional gazette\" — drawn to show the passage box; no stored capture text is used and no validated offsets are claimed.",
                    "Synthetic passage block — grey box stands for captured text; labelled mock example, so no validated code-point range is claimed.",
                    required=["Capture version", "Open source"])),
             (1, FLD("Capture version", [("Capture", "cap-9f31 (current) · cap-9d02 (older)", "live")],
                     [("Open source", False)],
                     "Capture version selector and Open source control — an actual field plus a safe HTTP(S) link control; both are visible, not prose only.",
                     required=["Capture version", "Open source"]))],
            [(1, LN("Provenance", ["Publisher: example.invalid (provisional host)", "Independence: unknown · no verified claim", "Dependency groups: unavailable", "URLs: original + canonical · example.invalid"],
                    "Provenance — provisional publisher host, unknown independence and both source URLs.")),
             (1, NT("Reader notes", ["Quotation highlighted only when a validated range exists", "Historical snapshot keeps its own capture", "No verified offset is claimed in this drawing"],
                    "Reader notes — quotation validation rules and the synthetic-passage limitation."))],
        ],
    ),
    dict(
        id="comparison", kind="screen", tabs=[
            "Overview", "Evidence", "Claims", "Compare", "Parties", "Map", "Timeline",
            "Exceptions", "Report", "Changes", "Search", "Run history"],
        tab_active="Compare", route="/cases/:id/compare?left=&right=&leftCapture=&rightCapture=", context="case tab 4 of 12",
        title="Comparison", nav="Cases",
        meta=[f"Two different evidence records and captures \u00b7 {PROPOSAL}"],
        body=[
            [(1, SEL("Source and capture selection",
                     [("Left source", "ev-c71a \u00b7 Regional Herald"), ("Left capture", "cap-9f31 (current)"),
                      ("Right source", "ev-b320 \u00b7 Wire Desk"), ("Right capture", "cap-9d02 (older)")],
                     [("Compare", False), ("Swap", False), ("Clear", False)],
                     "Selection controls \u2014 four visible fields (left/right source and capture) plus Compare, Swap and Clear; selections stay in the URL.",
                     required=["Left source", "Left capture", "Right source", "Right capture", "Compare", "Swap", "Clear"]))],
            [(1, LN("Left source panel", ["Regional Herald (synthetic) \u00b7 ev-c71a", "capture cap-9f31 \u00b7 observed 2026-11-20", "hash 4f1c\u2026a9 \u00b7 scope body prefix", "Open passage (navigates to inspector)"],
                    "Left source panel \u2014 its own capture time, hash and Open passage navigation.")),
             (1, LN("Right source panel", ["Wire Desk (synthetic) \u00b7 ev-b320", "capture cap-9d02 \u00b7 observed 2026-11-18", "hash 8b02\u20263e \u00b7 scope body prefix", "Open passage (navigates to inspector)"],
                    "Right source panel \u2014 its own capture time, hash and Open passage navigation; desktop side by side, tablet and mobile stack."))],
            [(1, TB("Aligned extractions", [("Row", 4), ("Status", 4)],
                    [("tender notice", "Reported in both extractions"), ("budget line", "Extracted only on left"), ("award date", "Extracted only on right")],
                    "Alignment rows \u2014 explicit 'Reported in both extractions' and 'Extracted only on left/right' labels, never omission or disagreement.",
                    note="One-sided extraction is coverage, not omission or disagreement; the copy warning below is dependency, not corroboration."))],
            [(1, NT("Dependency warning", ["Same normalized text detected across both captures", "Not independent evidence \u00b7 copy edge", "Absence of an edge is not proof of independence"],
                    "Dependency warning \u2014 detected copy edge reasons; never presented as corroboration or independence."))],
            [(1, BT([("Previous page", True), ("Next page", False)],
                    "Pagination controls \u2014 actual previous/next controls; offset stays in the URL."))],
        ],
    ),
    dict(
        id="source-provenance", kind="screen", tabs=[
            "Overview", "Evidence", "Claims", "Compare", "Parties", "Map", "Timeline",
            "Exceptions", "Report", "Changes", "Search", "Run history"],
        tab_active="Evidence", route="/cases/:id/sources", context="provenance reader",
        title="Source provenance", nav="Sources",
        meta=[f"Observed groups only \u00b7 {PROPOSAL}"],
        body=[
            [(1, TB("Dependency groups", [("Group", 2), ("Sources", 2), ("Method", 3), ("Status", 3)],
                   [("group-1", "2", "identical normalized text", "dependency_detected"),
                    ("group-2", "1", "no detected edge", "unknown"),
                    ("group-3", "1", "no detected edge", "unknown")],
                   "Dependency groups \u2014 connected components with method and status; a singleton group has no detected edge.",
                   note="No detected edge is not proven independence; repeated wire copies count once for breadth."))],
            [(1, LN("Group detail", ["group-1 \u00b7 dependency_detected", "Copy edge: identical normalized text (2 sources)", "Not independent evidence \u00b7 copy warning", "group-2/3: no detected edge \u00b7 independence unknown"],
                    "Group detail \u2014 the copy edge is labelled dependency_detected and explicitly not independent; groups without an edge stay unknown.")),
             (1, NT("Coverage limits", ["Exact text and documented origin only", "Near-duplicate syndication is not detected", "Publisher key stays provisional unless configured"],
                    "Coverage limits \u2014 v1 detection scope, disclosed rather than implied."))],
        ],
    ),
    dict(
        id="runs-changes", kind="screen", tabs=[
            "Overview", "Evidence", "Claims", "Compare", "Parties", "Map", "Timeline",
            "Exceptions", "Report", "Changes", "Search", "Run history"],
        tab_active="Changes", route="/cases/:id/changes?run=&offset=", context="case tab 10 of 12",
        title="Runs and changes", nav="Cases",
        meta=[f"Typed delta on stored snapshots \u00b7 {PROPOSAL}"],
        body=[
            [(1, FLD("Grouped run", [("Grouped run", "run-0007 \u00b7 sequence 7 \u00b7 partial coverage (run-0006 selectable)", "live")],
                     [("Refresh", False), ("Permalink", False)],
                     "Grouped run selector \u2014 an actual selector field listing run-0007 (run-0006 selectable), plus Refresh and Permalink; the selection is pinned in the URL.",
                     required=["Grouped run", "Refresh", "Permalink"]))],
            [(1, LN("Baseline and target", ["Baseline: snapshot-s002 \u00b7 target: snapshot-s003", "Coverage: partial \u00b7 2 of 3 sources succeeded", "Empty delta means no changes in observed data"],
                    "Baseline and target snapshot ids with the coverage warning.")),
             (1, NT("Run semantics", ["Pending runs are not final", "Failed runs never advance the baseline", "Origin run is shown separately from observed-by run"],
                    "Run semantics \u2014 pending, failed and attribution rules stated next to the selector."))],
            [(1, TB("Typed changes", [("Type", 3), ("Entity", 2), ("Before", 2), ("After", 2)],
                   [("claim_added", "claim-8898", "\u2014", "tender notice"),
                    ("capture_changed", "ev-c71a", "hash 4f1c", "hash 8b02"),
                    ("claim_no_longer_extracted", "claim-8897", "budget line", "\u2014"),
                    ("review_state_changed", "case-2201-0417", "review ready", "action required")],
                   "Typed before/after rows \u2014 review_state_changed carries the case review state, not a claim verification state.",
                   required=["claim_added", "capture_changed", "review_state_changed"]))],
            [(1, TB("Per-item run facts", [("Item", 3), ("originRunId", 3), ("observedByRunId", 3)],
                   [("claim-8898", "run-0007", "run-0007"), ("case-2201-0417", "origin not recorded", "run-0007"),
                    ("ev-c71a", "run-0006", "run-0007")],
                   "Per-item run facts \u2014 origin run and observer run as separate recorded values; neither implies who caused a change."))],
            [(1, BT([("Previous page", True), ("Next page", False)],
                    "Delta pagination \u2014 offset lives in the URL; the selected run stays pinned."))],
        ],
    ),
    dict(
        id="historical-snapshot", kind="screen", title="Historical snapshot", nav="Cases",
        route="/cases/:id/changes?run=&claim=&snapshot=", context="frozen claim panel (changes tab)",
        meta=[f"Reads the stored snapshot, never the latest row \u00b7 {PROPOSAL}"],
        body=[
            [(1, LN("Snapshot", ["snapshot-s002 \u00b7 case-2201-0417", "run-0006 \u00b7 succeeded \u00b7 complete scope", "schema v3 \u00b7 identity v1 \u00b7 policy v1", "Created 2026-11-19 \u00b7 immutable"],
                    "Snapshot metadata \u2014 frozen identifiers, versions and creation time.")),
             (1, QTE("Frozen claim (baseline snapshot)", "claim-8897 \u00b7 budget line was recorded in this snapshot and does not resolve to the live claim row.",
                     "Frozen claim \u2014 claim text from the baseline snapshot, retrieved by immutable reference."))],
            [(1, LN("Immutable passage", ["citation-3308 \u00b7 cap-9a11", "Quotation range: synthetic placeholder", "Source: Wire Desk (synthetic) \u00b7 observed 2026-11-18"],
                    "Immutable passage \u2014 frozen quotation range and its capture; no latest-capture substitution.")),
             (1, NT("Live-state line", ["Live case no longer contains this claim", "Not a retraction or a truth determination", "Historical claim stays inspectable"],
                    "Live-state note \u2014 distinguishes gone/rewritten from unchanged without attribution."))],
        ],
    ),
    dict(
        id="search", kind="screen", tabs=[
            "Overview", "Evidence", "Claims", "Compare", "Parties", "Map", "Timeline",
            "Exceptions", "Report", "Changes", "Search", "Run history"],
        tab_active="Search", route="/cases/:id/search?q=&type=&offset=", context="case tab 11 of 12",
        title="Case search", nav="Cases",
        meta=[f"Literal all-term, case-scoped \u00b7 {PROPOSAL}"],
        body=[
            [(1, FLT([("Query", "quartz tender"), ("Type", "All"), ("Publisher", "any"), ("Status", "any"),
                      ("Published from", "2026-01-01"), ("Published before", "2026-12-01")],
                     [("Search", False), ("Clear", False)],
                     "Search filters \u2014 six visible fields: literal all-term query, type All/claim/evidence, publisher, claim status, and UTC published-from/before (before is end-exclusive).",
                     required=["Query", "Type", "Publisher", "Status", "Published from", "Published before", "Search", "Clear"]))],
            [(1, L("3 examples / 42 results", [("claim-8898 \u00b7 tender notice \u2014 \u201c\u2026tender published in the regional gazette\u2026\u201d", "claim \u00b7 body"),
                                                         ("ev-c71a \u00b7 Regional Herald \u2014 \u201c\u2026tender notice lodged\u2026\u201d", "evidence \u00b7 body"),
                                                         ("claim-8896 \u00b7 award date \u2014 \u201c\u2026award due in March\u2026\u201d", "claim \u00b7 body")],
                   "Results \u2014 plain-text mock snippets with the matched field; each row has Open result navigation. Snippets never imply a validated quotation.",
                   note="Open result navigates by claim/evidence/capture id; publisher and status filters are disabled for incompatible result types.",
                   sub="offset: 0"))],
            [(1, BT([("Previous page", True), ("Next page", False), ("Permalink", False)],
                    "Pagination and permalink controls \u2014 result count and offset are shown with the results; offset is URL-persisted.",
                    required=["Previous page", "Next page", "Permalink"]))],
        ],
    ),
    dict(
        id="stage-history", kind="screen", title="Run history (stage-oriented)", nav="Cases", tabs=[
            "Overview", "Evidence", "Claims", "Compare", "Parties", "Map", "Timeline",
            "Exceptions", "Report", "Changes", "Search", "Run history"],
        tab_active="Run history", route="/cases/:id/run-history", context="case tab 12 of 12",
        meta=[f"Stage-oriented view, not grouped runs \u00b7 {PROPOSAL}"],
        body=[
            [(1, TB("Stage attempts", [("Stage", 2), ("Model", 2), ("Duration", 2), ("Fallback", 2), ("Status", 2), ("Recorded", 3)],
                   [("extraction", "qwen", "41s", "no", "succeeded", "2026-11-20 09:02"),
                    ("classification", "qwen", "12s", "yes", "fallback", "2026-11-20 09:03"),
                    ("party_classifier", "qwen", "9s", "no", "succeeded", "2026-11-20 09:03"),
                    ("arbiter", "\u2014", "unrecorded", "no", "failed", "2026-11-20 09:04"),
                    ("report", "\u2014", "3s", "no", "succeeded", "2026-11-20 09:04")],
                   "Stage attempts \u2014 per-stage model, duration, fallback flag, status and recorded time; not grouped investigation runs."))],
            [(1, NT("Interpretation", ["Duration and status are recorded values", "Fallback stays visible as fallback", "Grouped runs live on the Changes tab"],
                    "Interpretation \u2014 this tab remains stage-oriented; grouped runs and deltas are a separate reader."))],
        ],
    ),
    dict(
        id="pipeline", kind="screen", title="Pipeline monitor", nav="Cases",
        route="/cases/:id/pipeline", context="route-level pipeline reader",
        meta=[f"Configured stages vs recorded attempts \u00b7 {PROPOSAL}"],
        body=[
            [(1, TB("Configured stages", [("Stage", 4), ("Order", 2), ("Enabled", 2)],
                   [("extraction", "1", "yes"), ("party_classifier", "2", "yes"), ("party_investigators", "3", "yes"), ("arbiter", "4", "yes")],
                   "Configured stages \u2014 configuration order and enabled flag; configuration is not an attempt."))],
            [(1, TB("Recorded attempts", [("Stage", 4), ("Attempt", 2), ("Status", 3)],
                   [("extraction", "attempt-11", "succeeded"), ("party_classifier", "attempt-12", "succeeded"),
                    ("party_investigators", "attempt-13", "running"), ("arbiter", "\u2014", "unrecorded")],
                   "Recorded attempts \u2014 only actually recorded attempts; an unrecorded stage is not a success.",
                   note="Unrecorded is not success and not failure; no attempt row exists."))],
        ],
    ),
    dict(
        id="exception-queue", kind="screen", title="Exception queue", nav="Cases", tabs=[
            "Overview", "Evidence", "Claims", "Compare", "Parties", "Map", "Timeline",
            "Exceptions", "Report", "Changes", "Search", "Run history"],
        tab_active="Exceptions", route="/cases/:id/exceptions", context="case tab 8 of 12",
        meta=[f"Resolve / Defer / Reopen with CLI fallback \u00b7 {PROPOSAL}"],
        body=[
            [(1, TB("Exceptions", [("Exception", 3), ("Kind", 3), ("State", 2), ("Allowed", 3)],
                   [("exc-2310", "missing quotation", "pending", "all disabled"),
                    ("exc-2309", "source unavailable", "open", "resolve/defer"),
                    ("exc-2308", "ambiguous alignment", "closed", "reopen")],
                   "Exception table \u2014 pending disables all row actions; an open row enables Resolve/Defer, a closed row enables Reopen.",
                   note="Resolve/Defer/Reopen post the exception route; CLI fallback exists for recovery."))],
            [(1, FLD("Exception action", [("Exception", "exc-2310 \u00b7 pending \u00b7 all actions disabled", "live")],
                     [("Resolve", True), ("Defer", True), ("Reopen", True)],
                     "Exception actions \u2014 the pending row disables Resolve, Defer and Reopen; open and closed rows enable their listed actions.",
                     required=["Resolve", "Defer", "Reopen"],
                     note="A failed action shows the recorded error inline and never claims success."))],
        ],
    ),
    dict(
        id="parties", kind="screen", title="Parties", nav="Cases", tabs=[
            "Overview", "Evidence", "Claims", "Compare", "Parties", "Map", "Timeline",
            "Exceptions", "Report", "Changes", "Search", "Run history"],
        tab_active="Parties", route="/cases/:id/parties", context="case tab 5 of 12",
        meta=[f"Recorded vs inferred vs confirmed \u00b7 {PROPOSAL}"],
        body=[
            [(1, TB("Parties", [("Party", 3), ("Basis", 2), ("Supported", 2), ("Contested", 2)],
                   [("party-01 \u00b7 ministry", "recorded", "4", "1"), ("party-02 \u00b7 vendor", "inferred", "2", "3"),
                    ("party-03 \u00b7 regulator", "confirmed", "1", "0")],
                   "Party table \u2014 recorded, inferred or confirmed basis; counts are recorded rows, never guessed stance.",
                   note="Missing investigation data stays explicitly unavailable."))],
            [(1, LN("Expanded party detail", ["party-01 \u00b7 model position: concerned", "Key concerns: procurement timing", "Priorities: compliance review", "Claims supported 4 \u00b7 contested 1 \u00b7 unique 2", "Investigation data: recorded \u00b7 missing fields unavailable"],
                    "Expanded party accordion \u2014 recorded/model position, concerns, priorities, supported/contested/unique claim counts and explicit unavailable fields.")),
             (1, NT("Honesty rules", ["Party stance is model-labelled, not truth", "No stance is inferred from a name", "Unavailable investigation data renders as unavailable"],
                    "Honesty rules \u2014 recorded/model party position only; missing data is shown, never invented."))],
        ],
    ),
    dict(
        id="geographic-map", kind="screen", title="Geographic map", nav="Cases", tabs=[
            "Overview", "Evidence", "Claims", "Compare", "Parties", "Map", "Timeline",
            "Exceptions", "Report", "Changes", "Search", "Run history"],
        tab_active="Map", route="/cases/:id/map", context="case tab 6 of 12",
        meta=[f"Geotagged placeholders, no tiles \u00b7 {PROPOSAL}"],
        body=[
            [(2, MAP("Map", [(0.2, 0.3), (0.55, 0.5), (0.7, 0.25)],
                    "Map area \u2014 placeholder X and geotagged markers; no map tiles are loaded or implied.")),
             (1, L("Events by place", [("event-501 \u00b7 example.invalid", "geotagged"), ("event-500 \u00b7 capital region", "geotagged"),
                                       ("event-499 \u00b7 unknown place", "untagged")],
                   "Event list \u2014 geotagged events only; untagged events are listed as unknown place."))],
            [(1, NT("Place data", ["Untagged events are unknown, not elsewhere", "Markers are placeholders, not a real basemap", "No geocoding runs on GET"],
                    "Place data \u2014 untagged stays unknown; the map is a placeholder, not a live basemap."))],
        ],
    ),
    dict(
        id="timeline", kind="screen", tabs=[
            "Overview", "Evidence", "Claims", "Compare", "Parties", "Map", "Timeline",
            "Exceptions", "Report", "Changes", "Search", "Run history"],
        tab_active="Timeline", title="Timeline", nav="Cases", route="/cases/:id/timeline", context="case tab 7 of 12",
        meta=[f"Verification states; timestamps kept separate · {PROPOSAL}"],
        body=[
            [(1, TML("Events", [("2026-11-18 · 09:12", "Tender notice published", "confirmed"),
                                ("date unknown", "Budget line observed", "alleged")],
                    "Timeline entries — each row shows a verification state; a missing timestamp is shown as unknown and never inferred."))],
            [(1, TB("Verification states", [("State", 2), ("Meaning", 5)],
                   [("confirmed", "recorded as confirmed"), ("probable", "recorded as probable"),
                    ("alleged", "recorded as alleged"), ("contested", "recorded as contested"),
                    ("debunked", "recorded as debunked"), ("unknown", "no stored state")],
                   "Verification vocabulary — the six stored states; an unexpected raw value renders as 'Unrecognized status', and an unknown date stays distinct from the state.",
                   note="Unknown date is not unknown verification state."))],
        ],
    ),
    dict(
        id="report", kind="screen", title="Report", nav="Cases", tabs=[
            "Overview", "Evidence", "Claims", "Compare", "Parties", "Map", "Timeline",
            "Exceptions", "Report", "Changes", "Search", "Run history"],
        tab_active="Report", route="/cases/:id/report", context="case tab 9 of 12",
        meta=[f"Stored Markdown and Raw JSON only \u00b7 {PROPOSAL}"],
        body=[
            [(1, RPT("Stored report", [("Download Markdown", False), ("Download Raw JSON", True)],
                    "Report pane \u2014 document preview plus Markdown/JSON downloads; a missing artifact keeps its control disabled.")),
             (1, LN("Report facts", ["Run: run-0007 \u00b7 path reports/run-0007/", "Format: stored Markdown \u00b7 raw JSON", "Download failure is not an empty report"],
                    "Report facts \u2014 run-specific paths and formats; the report is stored, not regenerated on read."))],
            [(1, NT("Historical reports", ["Older runs resolve their own snapshot", "No latest-data substitution", "Failed report writing does not mark a run succeeded"],
                    "Historical reports \u2014 report documents bind to their run and snapshot."))],
        ],
    ),
    dict(
        id="corroboration-network", kind="screen", title="Corroboration network", nav="Network",
        route="/cases/:id/network", context="route-level network reader",
        meta=[f"Claim\u2013source edges, not independent proof \u00b7 {PROPOSAL}"],
        body=[
            [(2, GRP("Claim and source graph", [("claim-8898", 0.0, 0.1), ("Region Herald", 0.62, 0.0), ("Wire Desk", 0.62, 0.45),
                                               ("claim-8897", 0.0, 0.65), ("Civic Ledger", 0.62, 0.8)],
                    [(0, 1), (0, 2), (3, 4)], "Claim and source graph \u2014 rect nodes and line edges; a shared edge is not independent proof.",
                    height=240)),
             (1, PPL("Adversarial investigation flow", [("Collector", "recorded"), ("Party classifier", "recorded"),
                                                        ("Party investigators", "recorded"), ("Arbiter", "recorded")],
                     "Adversarial investigation flow \u2014 Collector, classifier, investigators, Arbiter; only recorded outcomes are shown, never completed merely because configured."))],
            [(1, L("Edges and outcomes", [("edge-1 \u00b7 claim-8898 \u2192 Region Herald", "reported_by"), ("edge-2 \u00b7 claim-8898 \u2192 Wire Desk", "uncertain"),
                                          ("arbiter \u00b7 2 facts, 1 allegation", "prior run-0006")],
                   "Edge and outcome list \u2014 relationship per edge plus the prior run's recorded Arbiter counts; facts and allegations are model classifications, not certification.")),
             (1, NT("Reading rule", ["Edges are generated links, not verification", "Configured is not completed", "Copy edges mean not independent"],
                    "Reading rule \u2014 no independence or completion claim from graph shape alone."))],
        ],
    ),
    dict(
        id="narratives", kind="screen", title="Narratives", nav="Narratives",
        route="/cases/:id/narratives", context="route-level narrative reader",
        meta=[f"Persisted clusters, not generated stance \u00b7 {PROPOSAL}"],
        body=[
            [(1, L("Persisted clusters", [("cluster-07 \u00b7 procurement", "3 claims"), ("cluster-06 \u00b7 pricing", "2 claims"),
                                          ("cluster-05 \u00b7 compliance", "4 claims")],
                   "Persisted clusters \u2014 stored cluster rows with their claim counts; no stance is generated on read."))],
            [(1, LN("Cluster detail", ["cluster-07 \u00b7 procurement", "Members: claim-8898, claim-8896", "Shared terms: tender, award", "Stance: not generated"],
                    "Cluster detail \u2014 member claims and shared terms; the reader never invents a narrative position.")),
             (1, NT("Reader rule", ["Clustering is persisted, not computed on GET", "No sentiment or stance generation", "Empty means no stored clusters"],
                    "Reader rule \u2014 persisted data only; empty is distinct from unavailable."))],
        ],
    ),
    dict(
        id="monitoring", kind="screen", title="Monitoring", nav="Monitoring",
        route="/monitoring", context="top-level route",
        meta=[f"Recorded status and times only \u00b7 {PROPOSAL}"],
        body=[
            [(1, TB("Recorded checks", [("Case", 3), ("Last observed", 3), ("Status", 2), ("Next run", 2)],
                   [("case-2201-0417", "2026-11-20 09:12", "partial", "not recorded"), ("case-2199-1180", "2026-11-19 18:40", "succeeded", "not recorded"),
                    ("case-2198-0922", "2026-11-18 07:05", "failed", "not recorded")],
                   "Recorded checks \u2014 stored observation time and status only; no health, scheduler or alert state.",
                   note="No telemetry is synthesized: missing scheduler data reads 'not recorded'."))],
            [(1, NT("Not shown here", ["No health score, uptime or throughput", "No alerting or paging", "Scheduler state is not recorded"],
                    "Scope note \u2014 monitoring is a recorded-status reader, not an operations dashboard."))],
        ],
    ),
    dict(
        id="ai-info", kind="screen", title="AI integration info", nav="AI info",
        route="/ai-info", context="top-level route",
        meta=[f"Capabilities vs unavailable, no chat \u00b7 {PROPOSAL}"],
        body=[
            [(1, TB("Capabilities", [("Capability", 4), ("State", 2), ("Detail", 4)],
                   [("claim extraction", "available", "collector, recorded provenance"), ("party classification", "available", "model-labelled"),
                    ("arbiter analysis", "unavailable", "no saved evaluation"), ("chat", "unavailable", "no chat surface")],
                   "Capabilities \u2014 available and unavailable features stated explicitly; no general chatbot."))],
            [(1, NT("Provenance", ["Model assessments are labelled model-assessed", "No prompt or confidence score is invented", "Unavailable means no saved result"],
                    "Provenance note \u2014 model assessment origin stays visible and unknown origin stays unknown.")),
             (1, L("Unavailable", [("chat", "not offered"), ("semantic search", "deferred")],
                   "Unavailable features \u2014 listed rather than hidden."))],
        ],
    ),
]


# --------------------------------------------------------------------------- 42 states
PARENT_NAV = {
    "dashboard": "Dashboard", "case-explorer": "Cases", "operator-launch": "Cases",
    "case-overview": "Cases", "review-annotation": "Cases", "evidence-gallery": "Cases",
    "claims": "Cases", "capture-inspector": "Cases", "comparison": "Cases",
    "source-provenance": "Sources", "runs-changes": "Cases", "historical-snapshot": "Cases",
    "search": "Cases", "stage-history": "Cases", "pipeline": "Cases", "exception-queue": "Cases",
    "parties": "Cases", "geographic-map": "Cases", "timeline": "Cases", "report": "Cases",
    "corroboration-network": "Network", "narratives": "Narratives", "monitoring": "Monitoring",
    "ai-info": "AI info",
}


def ST(sid, parent, title, body, applies, meta=None):
    return dict(id=sid, kind="state", parent=parent, applies=applies, title=title,
                nav=PARENT_NAV[parent], route="", context=f"selected state of {parent}",
                meta=meta or [PROPOSAL], body=body)


STATE_NOTE = "What this is not"


def state_note(lines, desc="State scope note \u2014 what the state does and does not assert."):
    return NT(STATE_NOTE, lines, desc)


STATES = [
    ST("shared-loading", "case-explorer", "Loading \u2014 cases", [
        [(1, SKL("Cases", "Loading cases\u2026", [272, 224, 304, 192],
                 "Loading skeleton \u2014 pending request; no partial rows or totals are asserted.")),
         (1, state_note(["Pending read, not empty", "Totals are not zero", "No stale rows are shown"]))],
        [(1, LN("Bounded wait", ["Skeleton clears on success, empty, 404 or error", "Retry appears only after failure"],
                "Bounded wait note \u2014 the skeleton is replaced by a resolved state, never left silently."))],
    ], "every list, tab and detail reader"),
    ST("shared-empty", "case-explorer", "Empty \u2014 no cases", [
        [(1, EMP("Cases", "No cases recorded", "HTTP 200 \u00b7 zero rows \u00b7 valid empty result",
                 "Empty state \u2014 a valid empty result is not an error and not a failed read.")),
         (1, state_note(["Empty is not failure", "No placeholder cases invented", "CLI creates cases"]))],
        [(1, LN("Next step", ["uv run triangulate ingest", "Then reload this list"],
                "Next step \u2014 case creation stays an operator CLI action, not a browser form."))],
    ], "all case and evidence lists"),
    ST("shared-not-found", "case-overview", "Not found \u2014 unknown case or tab", [
        [(1, ERR("Not found", "Unknown case or tab for this link",
                 ["No silent redirect to another case", "Wrong-case ids never resolve cross-case"],
                 [("Back to cases", False)], "404 state \u2014 unknown case id or unknown tab route; no substitution.")),
         (1, state_note(["Covers an unrecognized case tab route", "Deep links fail closed", "404 is not an empty case"]))],
        [(1, NT("Deep links", ["claim, evidence, capture, citation, snapshot and tab are explicit", "A missing item stays missing"],
                "Deep-link note \u2014 selection parameters never fall back to another item."))],
    ], "case routes, tab routes and deep links (includes unknown-tab fallback)"),
    ST("shared-network-error", "dashboard", "Network error \u2014 dashboard", [
        [(1, ERR("Read failed", "Network error while loading",
                 ["Failed read is not an empty result", "No partial portfolio is claimed"],
                 [("Retry", False)], "Network error \u2014 retryable failed read, visually distinct from empty.")),
         (1, state_note(["No cached totals shown", "Retry repeats the same GET", "No write is attempted"]))],
        [(1, NT("Generic pattern", ["Also covers a generic submission transport failure", "Distinct from 409 writer conflict"],
                "Generic pattern note \u2014 transport failure is shared by reads and the review form."))],
    ], "all readers; generic submission failure pattern"),
    ST("inspector-missing-quotation", "capture-inspector", "Inspector \u2014 missing quotation", [
        [(1, L("Linked sources", [("Regional Herald (synthetic)", "not_provided"), ("Wire Desk (synthetic)", "exact")],
               "Source list \u2014 one link has no quotation proposal; the reason is stated per row.")),
         (1, QTE("Quotation", "No quotation provided for this claim/source link (not_provided).",
                 "No-quotation block \u2014 nothing is highlighted and no offsets are claimed."))],
        [(1, state_note(["Missing quotation is not an empty capture", "Reason recorded: not_provided", "No generated highlight"]))],
    ], "claim/evidence inspector links"),
    ST("inspector-source-unavailable", "capture-inspector", "Inspector \u2014 source unavailable", [
        [(1, ERR("Capture text unavailable", "The stored capture could not be read",
                 ["Reason: source_unavailable", "Hash and metadata still shown"],
                 [("Open source", False)], "Unavailable capture \u2014 the quotation cannot be highlighted; reason stated.")),
         (1, LN("Metadata", ["cap-9f31 \u00b7 live", "observed 2026-11-20", "text_sha256: recorded"],
                "Metadata pane \u2014 capture identity remains visible even when the body is unavailable."))],
        [(1, state_note(["Unavailable is not zero-length text", "No fabricated quotation", "Retry only rereads"]))],
    ], "capture inspector"),
    ST("inspector-ambiguous", "capture-inspector", "Inspector \u2014 ambiguous quotation", [
        [(1, L("Candidate occurrences", [("offset 412", "occurrence 1 of 2"), ("offset 980", "occurrence 2 of 2")],
               "Ambiguity list \u2014 repeated exact matches without disambiguating offsets; nothing is highlighted.")),
         (1, state_note(["Reason: ambiguous", "No fuzzy or casefold match used", "A validated range is required"]))],
        [(1, NT("Resolution", ["Offsets must match the exact quotation", "Ambiguity stays visible until disambiguated"],
                "Resolution note \u2014 only a unique exact occurrence becomes exact."))],
    ], "capture inspector"),
    ST("inspector-no-match", "capture-inspector", "Inspector \u2014 quotation not in scope", [
        [(1, ERR("Quotation not found in recorded scope", "No exact occurrence inside the analysis scope",
                 ["Reason: no_match", "Scope limit is recorded with the capture"],
                 [], "No-match state \u2014 no highlight and no scope widening on read.")),
         (1, LN("Recorded scope", ["body prefix \u00b7 20,000 code points", "Extraction scope frozen with capture"],
                "Recorded scope \u2014 the reader does not search outside the recorded scope."))],
        [(1, state_note(["Out-of-scope is no_match", "No latest capture substitution", "No synthesized ellipsis"]))],
    ], "capture inspector"),
    ST("inspector-legacy", "capture-inspector", "Inspector \u2014 legacy snapshot", [
        [(1, L("Capture metadata", [("cap-9a11 \u00b7 legacy_snapshot", "imported"), ("observed_at", "unknown"), ("recorded_at", "2026-11-10")],
               "Legacy capture \u2014 imported text is labelled legacy_snapshot with unknown observation time.")),
         (1, state_note(["Not labelled as newly fetched", "Observation history unknown", "No invented timestamp"]))],
        [(1, NT("Quotation", ["Legacy links may carry diagnostics only", "No validated range is manufactured"],
                "Legacy quotation note \u2014 imported text never gains validated offsets by reading."))],
    ], "capture inspector"),
    ST("comparison-selection", "comparison", "Comparison \u2014 selection required", [
        [(1, SEL("Source and capture selection",
                 [("Left source", "Select a source"), ("Left capture", "Select a capture"),
                  ("Right source", "Select a second source"), ("Right capture", "Select a capture")],
                 [("Compare", True), ("Swap", True), ("Clear", True)],
                 "Selection prompt \u2014 Compare stays disabled until two different evidence captures are chosen.")),
         (1, state_note(["No comparison is guessed", "URL is the selection authority", "Default capture pins only after load"]))],
        [(1, LN("Pinned URL", ["/cases/case-2201-0417/compare?left=&right=", "Reload keeps the empty selection"],
                "Pinned URL \u2014 an empty selection is honest and reproducible."))],
    ], "comparison tab"),
    ST("comparison-same-source", "comparison", "Comparison \u2014 same source rejected", [
        [(1, SEL("Source and capture selection",
                 [("Left source", "ev-c71a \u00b7 Regional Herald"), ("Left capture", "cap-9f31 (current)"),
                  ("Right source", "ev-c71a \u00b7 Regional Herald"), ("Right capture", "cap-9f31 (current)")],
                 [("Compare", True), ("Swap", False), ("Clear", False)],
                 "Same-source validation \u2014 the opposite source and capture are disabled; Compare stays disabled.")),
         (1, ERR("Same source selected", "Choose two distinct evidence records",
                 ["Comparison needs different evidence ids", "No self-comparison is rendered"],
                 [], "Validation state \u2014 the same evidence cannot be compared with itself."))],
        [(1, state_note(["Both ids must belong to this case", "Invalid ids are 422, not guessed"]))],
    ], "comparison tab"),
    ST("comparison-no-second-source", "comparison", "Comparison \u2014 no second source", [
        [(1, EMP("Second source", "This case has only one evidence record", "Comparison needs two sources \u00b7 no second source recorded",
                 "No-second-source state \u2014 distinct from a selection error or an empty comparison.")),
         (1, LN("Next step", ["uv run triangulate ingest", "Ingest stays CLI-only"],
                "Next step \u2014 a second source arrives through the operator CLI, never a browser form."))],
        [(1, state_note(["Not an empty alignment table", "No synthetic second source invented"]))],
    ], "comparison tab"),
    ST("comparison-empty", "comparison", "Comparison \u2014 no aligned rows", [
        [(1, SEL("Source and capture selection",
                 [("Left source", "ev-c71a \u00b7 Regional Herald"), ("Left capture", "cap-9f31 (current)"),
                  ("Right source", "ev-b320 \u00b7 Wire Desk"), ("Right capture", "cap-9d02 (older)")],
                 [("Compare", False), ("Swap", False), ("Clear", False)],
                 "Selection summary \u2014 both captures are pinned and readable.")),
         (1, EMP("Alignment", "No shared or one-sided extraction rows", "HTTP 200 \u00b7 valid empty row set",
                 "Empty comparison \u2014 a valid empty alignment is not an unavailable historical capture."))],
        [(1, state_note(["Empty rows mean no extracted passages", "Not omission and not disagreement"]))],
    ], "comparison tab"),
    ST("comparison-historical-unavailable", "comparison", "Comparison \u2014 historical unavailable", [
        [(1, BAN("Historical alignment unavailable for this capture", "No saved snapshot retains the older claim links \u00b7 latest links are not substituted",
                 "Historical banner \u2014 an old capture without retained alignment stays unavailable.")),
         (1, LN("Capture", ["cap-9a11 \u00b7 legacy_snapshot \u00b7 2026-11-10", "Both sides still read their own immutable captures"],
                "Capture context \u2014 each side reads its stored capture; no latest links."))],
        [(1, state_note(["Unavailable is not an empty delta", "No latest-claim substitution", "Use a retained snapshot if available; never substitute current"]))],
    ], "comparison tab"),
    ST("comparison-dependency-warning", "comparison", "Comparison \u2014 dependency warning", [
        [(1, BAN("Detected copy: same normalized text in both captures", "Not independent evidence \u00b7 absence of an edge does not prove independence",
                 "Dependency warning \u2014 reasons and limitation shown before the rows.")),
         (1, TB("Rows", [("Row", 4), ("Left", 2), ("Right", 2)],
                [("tender notice", "exact", "exact"), ("budget line", "exact", "uncertain")],
                "Rows under warning \u2014 alignment states remain extraction coverage, not endorsement."))],
        [(1, state_note(["Copy edge is a dependency, not corroboration", "Publisher identity stays provisional"]))],
    ], "comparison tab"),
    ST("changes-initial", "runs-changes", "Changes \u2014 first observation", [
        [(1, BAN("First observation \u2014 no earlier successful observation", "This is not a surge of new changes",
                 "Initial banner \u2014 the first snapshot has no baseline and is not a change surge.")),
         (1, LN("Snapshot", ["snapshot-s001 \u00b7 sequence 1", "Coverage: complete_requested_scope", "Baseline: none"],
                "Snapshot facts \u2014 first snapshot identifiers and coverage."))],
        [(1, state_note(["No baseline exists", "Not an all-changed case", "Rows would be observed entities only"]))],
    ], "changes tab"),
    ST("changes-pending", "runs-changes", "Changes \u2014 run in progress", [
        [(1, BAN("Run in progress \u2014 changes are not final", "run-0008 \u00b7 status running \u00b7 no delta published yet",
                 "Pending banner \u2014 pending is not an empty delta.")),
         (1, SKL("Delta", "Waiting for the run to finish", [320, 240, 280],
                 "Pending skeleton \u2014 no partial before/after rows are shown."))],
        [(1, state_note(["Pending is not final", "No polling on GET", "Refresh rereads runs and delta"]))],
    ], "changes tab"),
    ST("changes-unavailable", "runs-changes", "Changes \u2014 no snapshot published", [
        [(1, BAN("Historical change data unavailable", "run-0005 \u00b7 failed \u00b7 no snapshot was published \u00b7 this is not an empty delta",
                 "Unavailable banner \u2014 failed or interrupted runs never advance the baseline.")),
         (1, LN("Recorded error", ["Run status: failed", "Coverage: failed", "Baseline: unchanged"],
                "Recorded error \u2014 the stored failure is shown; recovery stays CLI-only."))],
        [(1, state_note(["Unavailable is not unchanged", "No fabricated empty list", "Baseline not advanced"]))],
    ], "changes tab"),
    ST("changes-unchanged-partial", "runs-changes", "Changes \u2014 unchanged with partial coverage", [
        [(1, EMP("Delta", "Unchanged \u2014 no changes in observed data", "Between snapshot-s002 and snapshot-s003",
                 "Unchanged state \u2014 a valid delta with zero typed rows.")),
         (1, BAN("Coverage: partial \u00b7 2 of 3 sources", "An empty list means no changes in observed data \u2014 not that every source was unchanged",
                 "Coverage warning \u2014 persistent alongside an empty delta."))],
        [(1, state_note(["Partial coverage limits the claim", "Scope is recorded per run", "No surge wording"]))],
    ], "changes tab"),
    ST("search-no-results", "search", "Search \u2014 no results", [
        [(1, FLT([("Query", "quarz tender"), ("Type", "claim")], [("Search", False), ("Clear", False)],
                 "Filters remain visible \u2014 the applied query and filters are printed with the empty result.")),
         (1, EMP("Results", "No matching claims or evidence", "HTTP 200 \u00b7 total 0 \u00b7 filters applied",
                 "No-results state \u2014 a valid empty result, not an unavailable index."))],
        [(1, state_note(["Zero matches is not index failure", "Plain snippets, never quotations", "Offset resets on a new query"]))],
    ], "search tab"),
    ST("search-index-unavailable", "search", "Search \u2014 index unavailable", [
        [(1, ERR("Search index unavailable", "The case search index is not available",
                 ["HTTP 503 \u00b7 operator remedy required", "No GET-side rebuild and no LIKE fallback"],
                 [("Retry", False)], "503 state \u2014 index capability absent; explicit unavailable, not empty.")),
         (1, LN("Operator remedy", ["uv run triangulate case rebuild-search case-2201-0417", "Rebuild is a CLI command scoped to the case"],
                "Operator remedy \u2014 printed remediation, not a browser rebuild button."))],
        [(1, state_note(["Unavailable is not zero results", "No silent fallback query"]))],
    ], "search tab"),
    ST("search-invalid-filters", "search", "Search \u2014 invalid filters", [
        [(1, FLT([("Query", "quartz"), ("Type", "evidence"), ("Status", "alleged")], [("Search", True), ("Clear", False)],
                 "Invalid filter combination \u2014 status applies to claims only and conflicts with evidence-only type.")),
         (1, ERR("Invalid filters", "422 \u00b7 incompatible type and status",
                 ["Status narrows to claim results", "Rejected before any index query"],
                 [], "422 state \u2014 invalid combination is explained inline."))],
        [(1, state_note(["422 is not an empty result", "Query/filters echo the applied input", "Unsupported offset 2,147,483,648 is also 422"]))],
    ], "search tab"),
    ST("search-out-of-range", "search", "This page is beyond the last result", [
        [(1, FLT([("Query", "quartz"), ("Offset", "50"), ("Limit", "25"), ("Total", "42")],
                 [("Return first page", False)],
                 "Paging controls \u2014 a valid offset past the last row with the query preserved; Return first page clears offset and keeps the query.",
                 required=["Query", "Offset", "Limit", "Total", "Return first page"])),
         (1, EMP("This page is beyond the last result", "HTTP 200 \u00b7 no rows at this offset \u00b7 total 42",
                 "Manual control clears offset and preserves the query",
                 "Beyond-last-page state \u2014 a valid empty page, not a 422 and not an unavailable index."))],
        [(1, state_note(["No automatic correction to page one", "Unsupported offset 2,147,483,648 is a 422 (documented under invalid filters)", "Offset stays in the URL"]))],
    ], "search tab"),
    ST("review-saving", "review-annotation", "Review \u2014 saving", [
        [(1, FLD("Review decision", [("Rationale", "pending write", "empty")],
                 [("Approve", True), ("Action Required", True), ("Reject", True)],
                 "Saving state \u2014 rationale only plus the three decision buttons; all controls disabled while the review POST is in flight and no success is claimed yet.",
                 required=["Rationale", "Approve", "Action Required", "Reject"])),
         (1, state_note(["Saving is not saved", "Controls disabled while pending", "Notes are retained in the field"]))],
        [(1, NT("Write scope", ["One narrow review POST", "No retry storm on GET", "Failure returns an explicit error"],
                "Write-scope note \u2014 a single narrow review write, explicit failure and no client retry loop."))],
    ], "review decision form"),
    ST("review-failed", "review-annotation", "Review \u2014 writer conflict", [
        [(1, ERR("Submission not saved \u00b7 409", "Active case writer conflict",
                 ["Another case-bound writer holds the case", "Decision not saved \u00b7 entered notes retained"],
                 [("Refresh case", False)], "409 conflict \u2014 active case writer conflict; the decision is explicitly not saved.")),
         (1, state_note(["409 is not a generic network failure", "No success wording", "Refresh rereads the case"]))],
        [(1, LN("Recovery", ["Wait for writer release, then retry chosen review action", "Browser review retry uses its narrow POST; CLI recovery is separate"],
                "Recovery note \u2014 retry the chosen review action after writer release; browser review retry and CLI recovery are separate."))],
    ], "review decision form"),
    ST("review-stale", "review-annotation", "Review \u2014 case data changed", [
        [(1, BAN("Case data changed since this decision was loaded", "Reload before saving \u00b7 the stale decision is not posted",
                 "Stale banner \u2014 the form is frozen rather than silently overwriting newer data.")),
         (1, FLD("Review decision", [("Rationale", "loaded 09:12", "empty")],
                 [("Approve", True), ("Action Required", True), ("Reject", True), ("Reload case", False)],
                 "Frozen form \u2014 the three decision buttons are disabled until the newer case state is reloaded; Reload case is the only enabled control.",
                 required=["Rationale", "Approve", "Action Required", "Reject", "Reload case"]))],
        [(1, state_note(["Stale is not saved", "No automatic approval", "Reload is a GET"]))],
    ], "review decision form"),
    ST("review-saved", "review-annotation", "Review \u2014 decision recorded", [
        [(1, BAN("Decision recorded", "action_required \u00b7 observed in the case record",
                 "Saved confirmation \u2014 recorded decision is reported as observed, without actor attribution.")),
         (1, LN("Recorded review", ["Decision: action_required", "Rationale stored with the decision", "Reviewer identity: not recorded"],
                "Recorded review \u2014 fields as stored; no human audit trail is implied."))],
        [(1, state_note(["Saved is not a truth verdict", "No confidence score", "No reviewer identity is invented"]))],
    ], "review decision form"),
    ST("review-blocked", "review-annotation", "Review \u2014 blocked by exceptions", [
        [(1, ERR("Approval blocked \u00b7 422", "Unresolved exceptions must be resolved first",
                 ["exceptions: exc-2310, exc-2309", "No decision was saved"],
                 [("Open exception queue", False)], "Blocked state \u2014 422 approval blocked by unresolved exceptions; links the queue.")),
         (1, L("Unresolved exceptions", [("exc-2310 \u00b7 missing quotation", "pending"), ("exc-2309 \u00b7 source unavailable", "deferred")],
               "Unresolved exception list \u2014 the blocking rows with their recorded states."))],
        [(1, state_note(["Blocked is not saved", "No override control in the browser", "CLI fallback is documented"]))],
    ], "review decision form (approval path)"),
    ST("annotation-invalid", "review-annotation", "Annotation \u2014 invalid input", [
        [(1, FLD("New annotation", [("Type", "flag", "live"), ("Target", "unknown", "empty"),
                                    ("Target ID", "", "empty"), ("Content", "", "empty")],
                 [("Save annotation", True)], "Invalid annotation \u2014 bad target and blank content are rejected block-side with 422.",
                 required=["Type", "Target", "Target ID", "Content", "Save annotation"])),
         (1, ERR("Validation failed", "422 \u00b7 target must be case/claim/evidence/exception/narrative",
                 ["Target ID is required", "Content must not be blank"],
                 [], "422 validation \u2014 inline field errors; Save stays disabled."))],
        [(1, state_note(["Invalid input is not a saved note", "Errors are text, not colour alone"]))],
    ], "annotation form"),
    ST("evaluation-unavailable", "claims", "Evaluation \u2014 no saved evaluation", [
        [(1, EMP("Evaluation", "No saved evaluation for this case", "The reader found no stored evaluation \u00b7 never shown as zero",
                 "Unavailable evaluation \u2014 absence of a saved result, not a score of zero.")),
         (1, state_note(["Missing evaluation is not 0", "No computed-on-read evaluation", "Claim list stays readable"]))],
        [(1, LN("What remains", ["Claims and citations still readable", "Arbiter analysis stays model-labelled", "No verdict is inferred"],
                "What remains \u2014 claim reading is independent of a saved evaluation."))],
    ], "claims/evaluation reader"),
    ST("evaluation-failed", "claims", "Evaluation \u2014 read failed", [
        [(1, ERR("Evaluation read failed", "The stored evaluation could not be read",
                 ["Failure is not an empty evaluation", "No pending or zero value is shown"],
                 [("Retry", False)], "Failed evaluation \u2014 retryable read error, distinct from unavailable and empty.")),
         (1, state_note(["Failed read is not zero", "Retry repeats the same GET", "No partial evaluation"]))],
        [(1, NT("Distinct states", ["No saved evaluation \u2260 failed read", "Both are distinct from a zero score"],
                "Distinct-state note \u2014 unavailable, failed and zero never collapse."))],
    ], "claims/evaluation reader"),
    ST("exception-pending", "exception-queue", "Exception \u2014 pending row", [
        [(1, TB("Exceptions", [("Exception", 3), ("State", 2), ("Allowed", 2)],
                [("exc-2310 \u00b7 missing quotation", "pending", "all disabled"), ("exc-2309 \u00b7 source unavailable", "open", "resolve/defer")],
                "Pending exception \u2014 a pending row disables every row action, including Reopen, until its prerequisite clears.")),
         (1, FLD("Exception action", [("Exception", "exc-2310 \u00b7 pending", "live")],
                 [("Resolve", True), ("Defer", True), ("Reopen", True)],
                 "Pending action controls \u2014 Resolve, Defer and Reopen are all disabled for the pending row.",
                 required=["Resolve", "Defer", "Reopen"]))],
        [(1, LN("Blocked by", ["Quotation validation still running", "CLI fallback available for recovery"],
                "Blocked-by note \u2014 the reason is stated; recovery stays CLI-only."))],
    ], "exception queue"),
    ST("exception-failed", "exception-queue", "Exception \u2014 action failed", [
        [(1, ERR("Exception action failed", "The recorded action did not complete",
                 ["State unchanged \u00b7 no success claimed", "Error shown inline with the row"],
                 [("Retry", False)], "Failed action \u2014 inline error, row state unchanged.")),
         (1, TB("Row state", [("Exception", 3), ("State", 2)], [("exc-2309", "deferred")],
                "Row state \u2014 still deferred; the failed action is not reflected as applied."))],
        [(1, state_note(["Failure is not a state change", "No alert banner substituted", "Retry is explicit"]))],
    ], "exception queue"),
    ST("exception-empty", "exception-queue", "Exception \u2014 none recorded", [
        [(1, EMP("Exceptions", "No exceptions recorded for this case", "HTTP 200 \u00b7 zero rows \u00b7 valid empty queue",
                 "Empty queue \u2014 not a failed read and not an unavailable capability."))],
        [(1, NT("Interpretation", ["Empty means no exception rows", "A pending run may add rows later", "No synthetic exception"],
                "Interpretation note \u2014 an empty queue is a valid read, not a failure."))],
    ], "exception queue"),
    ST("report-pending", "report", "Report \u2014 pending", [
        [(1, BAN("Report pending", "run-0008 is running \u00b7 no stored artifact yet",
                 "Pending report \u2014 downloads stay disabled until the run finalizes.")),
         (1, RPT("Stored report", [("Download Markdown", True), ("Download Raw JSON", True)],
                 "Disabled downloads \u2014 pending report has no stored Markdown or JSON."))],
        [(1, state_note(["Pending is not an empty report", "No on-demand generation", "Run-specific path appears on success"]))],
    ], "report tab"),
    ST("report-download-error", "report", "Report \u2014 download error", [
        [(1, ERR("Download failed", "The stored report file could not be read",
                 ["No partial file is served", "Nested status page is refused"],
                 [("Retry", False)], "Download error \u2014 explicit failure, no empty document rendered.")),
         (1, LN("Artifact", ["run-0007 \u00b7 reports/run-0007/", "Markdown stored \u00b7 Raw JSON stored"],
                "Artifact note \u2014 the run-specific directory and stored formats."))],
        [(1, state_note(["Failed download is not an empty report", "No regeneration on GET"]))],
    ], "report tab"),
    ST("map-empty", "geographic-map", "Map \u2014 no geotagged events", [
        [(1, MAP("Map", [], "Empty map \u2014 placeholder area with no geotagged markers.",
                 label="No geotagged events \u00b7 placeholder only")),
         (1, EMP("Events by place", "No geotagged events", "Untagged events are unknown place \u00b7 not elsewhere",
                 "Empty map \u2014 untagged events stay unknown; no invented coordinates."))],
        [(1, state_note(["No markers means no geotagged rows", "Geocoding never runs on GET", "No basemap tiles"]))],
    ], "map tab"),
    ST("timeline-unknown", "timeline", "Timeline \u2014 unknown date and raw status", [
        [(1, TML("Events", [("date unknown", "Tender notice (no stored time)", "alleged"),
                            ("2026-11-19 \u00b7 14:05", "Budget line observed", "Unrecognized status")],
                 "Timeline with an unknown date and an unexpected raw status \u2014 both labelled explicitly.")),
         (1, state_note(["Unknown date is distinct from verification state", "Unexpected raw value renders as 'Unrecognized status'", "No 1970 placeholder and no inferred ordering"]))],
        [(1, LN("Status keys", ["States: confirmed/probable/alleged/contested/debunked/unknown", "Unrecognized status is a raw stored value, not a seventh state", "Ordering among unknown dates is not claimed"],
                "Status keys \u2014 the six states plus the unrecognized-raw-value label."))],
    ], "timeline tab"),
    ST("pipeline-unrecorded", "pipeline", "Pipeline \u2014 stage unrecorded", [
        [(1, PPL("Recorded attempts", [("extraction", "recorded"), ("party_classifier", "recorded"),
                                       ("party_investigators", "unrecorded"), ("arbiter", "unrecorded")],
                 "Unrecorded stages \u2014 no attempt row exists; unrecorded is not success and not failure.")),
         (1, state_note(["Configured is not completed", "No elapsed-time inference", "No fake progress"]))],
        [(1, LN("Configuration", ["Configured stages: 4", "Recorded attempts: 2", "Difference is unrecorded, shown as such"],
                "Configuration note \u2014 the configured count and recorded count differ honestly."))],
    ], "pipeline route"),
    ST("monitoring-unavailable", "monitoring", "Monitoring \u2014 unavailable", [
        [(1, EMP("Recorded checks", "No recorded status for this case", "No observation time or scheduler state stored",
                 "Unavailable monitoring \u2014 absence of recorded status, not a healthy or unhealthy verdict.")),
         (1, state_note(["Unavailable is not healthy", "No scheduler or alert state", "No telemetry synthesized"]))],
        [(1, LN("What would appear", ["Last observed time", "Recorded run status", "Coverage as stored"],
                "What would appear \u2014 the reader's actual fields, none of which are health scores."))],
    ], "monitoring route"),
    ST("evidence-filter-empty", "evidence-gallery", "Evidence \u2014 filter empty", [
        [(1, FLT([("Tier", "Unknown"), ("Captured", "no")], [("Apply", False), ("Clear", False)],
                 "Active filters \u2014 the applied tier and capture filters that produced the empty result.")),
         (1, EMP("Evidence", "No evidence rows match these filters", "Filters applied \u00b7 sources are not absent",
                 "Filter-empty state \u2014 no rows match, which is not a case without sources."))],
        [(1, state_note(["Filter empty is not case empty", "Clear restores the unfiltered list", "Tier is not truth"]))],
    ], "evidence gallery"),
    ST("narratives-empty", "narratives", "Narratives \u2014 none persisted", [
        [(1, EMP("Persisted clusters", "No narrative clusters persisted", "Empty list \u00b7 no clusters generated on read",
                 "Empty narratives \u2014 no stored clusters; the reader does not generate stance."))],
        [(1, state_note(["Empty is not unavailable", "No generated narrative", "Clusters arrive from the pipeline"]))],
    ], "narratives route"),
]


# --------------------------------------------------------------------------- flows
FLOWS = [
    dict(id="flow", title="Primary evidence-workbench flow",
         screens=["case-explorer", "claims", "capture-inspector"], labels=["open claim", "inspect"]),
    dict(id="flow-claims-review", title="Claims, review and evidence flow",
         screens=["capture-inspector", "review-annotation", "evidence-gallery"], labels=["annotate", "sources"]),
    dict(id="flow-compare-provenance", title="Comparison and provenance flow",
         screens=["evidence-gallery", "comparison", "source-provenance"], labels=["compare", "deps"]),
    dict(id="flow-changes-history", title="Runs, snapshots and stage history flow",
         screens=["runs-changes", "historical-snapshot", "stage-history"], labels=["snapshot", "stages"]),
    dict(id="flow-search-snapshot", title="Search and snapshot flow",
         screens=["search", "historical-snapshot", "case-overview"], labels=["open", "context"]),
    dict(id="flow-operator-pipeline", title="Operator, pipeline and monitoring flow",
         screens=["operator-launch", "pipeline", "runs-changes", "monitoring"], labels=["run CLI", "observe", "status"]),
    dict(id="flow-review-exceptions", title="Review, exceptions and timeline flow",
         screens=["review-annotation", "exception-queue", "timeline"], labels=["resolve", "in time"]),
    dict(id="flow-geography-parties", title="Parties, map and timeline flow",
         screens=["parties", "geographic-map", "timeline"], labels=["map party", "date"]),
    dict(id="flow-network-report", title="Network, narratives and report flow",
         screens=["corroboration-network", "narratives", "report"], labels=["cluster", "report"]),
    dict(id="flow-dashboard-ai", title="Dashboard, AI info, case and search flow",
         screens=["dashboard", "ai-info", "case-overview", "search"], labels=["capability", "open case", "search"]),
]

NS = "{http://www.w3.org/2000/svg}"
SCALE = 224 / 1280.0


def mini_prims(path: Path):
    root = ET.parse(path).getroot()
    ui = None
    for child in root:
        if child.tag == NS + "g" and child.get("id") == "ui":
            ui = child
    assert ui is not None, f"no ui group in {path}"
    prims = []
    for el in ui.iter():
        if el.tag == NS + "rect":
            x, y = float(el.get("x", 0)), float(el.get("y", 0))
            w, h = float(el.get("width", 0)), float(el.get("height", 0))
            if w >= 1264 and h >= 784:
                continue  # canvas background and outer frame
            prims.append(("rect", x, y, w, h, el.get("fill", WHITE), el.get("stroke")))
        elif el.tag == NS + "line":
            prims.append(("line", float(el.get("x1", 0)), float(el.get("y1", 0)),
                          float(el.get("x2", 0)), float(el.get("y2", 0)), INK, INK))
    return prims


def draw_thumb(c: Svg, tx, ty, sid, num, prims, title):
    fw, fh = 240, 168
    c.rect(tx, ty, fw, fh, WHITE, stroke=True)
    for prim in prims:
        if prim[0] == "rect":
            _, x, y, w, h, fill, stroke = prim
            x0, y0 = r8(x * SCALE), r8(y * SCALE)
            x1, y1 = r8((x + w) * SCALE), r8((y + h) * SCALE)
            if x0 >= 224 or y0 >= 144:
                continue
            sw = min(max(8, x1 - x0), 224 - x0)
            sh = min(max(8, y1 - y0), 144 - y0)
            c.rect(tx + 8 + x0, ty + 8 + y0, sw, sh, GREY if fill == GREY else WHITE, stroke=bool(stroke))
        else:
            _, x1, y1, x2, y2, _, _ = prim
            pts = [min(224, max(0, r8(v * SCALE))) for v in (x1, y1, x2, y2)]
            if pts[0] == pts[2] and pts[1] == pts[3]:
                continue
            c.line(tx + 8 + pts[0], ty + 8 + pts[1], tx + 8 + pts[2], ty + 8 + pts[3])
    c.text(tx, ty + fh + 32, f"{num} \u00b7 {sid}", 12, INK)
    c.region(tx, ty, fw, fh + 40,
             f"Thumbnail {num} \u2014 {title} ({sid}); geometry-derived miniature, source text omitted.")


def build_flow(fspec, out: Path) -> Svg:
    c, fw, fh, gap = Svg("desktop"), 240, 168, 64
    frame(c)
    c.text(32, 80, str(fspec["title"]), 28, INK, 600)
    c.text(32, 112, "Left-to-right order is a navigation/review path \u2014 not automatic execution or a causal state transition.", 12, MUTED)
    c.text(32, 136, "Thumbnails are geometry-derived from each screen's desktop SVG; source text is omitted as illegible at this scale.", 12, MUTED)
    c.region(32, 32, 1224, 112, "Flow title \u2014 reading rule stated before any transition; order is navigation, not execution.")
    screens = [str(s) for s in fspec["screens"]]
    labels = [str(s) for s in fspec["labels"]]
    n = len(screens)
    total = n * fw + (n - 1) * gap
    start = r8(32 + (1224 - total) / 2.0)
    ty = 200
    for idx, sid in enumerate(screens):
        tx = start + idx * (fw + gap)
        draw_thumb(c, tx, ty, sid, idx + 1, mini_prims(out / f"{sid}-desktop.svg"), SCREEN_TITLES[sid])
        if idx < n - 1:
            ax1, ax2, ay = tx + fw + 8, tx + fw + 56, ty + 88
            c.line(ax1, ay, ax2, ay)
            c.line(ax2, ay, ax2 - 8, ay - 8)
            c.line(ax2, ay, ax2 - 8, ay + 8)
            c.text(tx + fw + 32, ay + 24, labels[idx], 12, MUTED, anchor="middle")
            c.region(tx + fw + 24, ay - 8, 16, 64,
                     f"Transition {idx + 1} \u2014 '{labels[idx]}': navigation/review path only.")
    ly = 448
    c.text(32, ly + 32, "Legend", 14, INK, 600)
    c.text(32, ly + 64, "Screens are numbered in reading order; arrows are navigation or review transitions.", 12, INK)
    c.text(32, ly + 88, "Geometry is snapped to the 8 px grid; text, icons, images and external references are omitted.", 12, MUTED)
    c.region(32, ly, 1224, 120, "Legend \u2014 thumbnail abstraction and grid rules; no automatic transition is implied.")
    return c


SCREEN_TITLES = {d["id"]: d["title"] for d in SCREENS}


# --------------------------------------------------------------------------- serialization
def render_svg(c: Svg, title: str) -> str:
    v = VP[c.vp]
    desc = (f"{title} ({c.vp}, {v['w']}x{v['h']}). Proposal wireframe with synthetic data, not implementation "
            f"evidence. Numbered regions: " + "; ".join(f"{r['number']} {r['desc'].rstrip('.')}" for r in c.regions) + ".")
    out = [f"<!-- viewport: {v['w']}\u00d7{v['h']} {c.vp} -->",
           f'<svg xmlns="http://www.w3.org/2000/svg" width="{v["w"]}" height="{v["h"]}" '
           f'viewBox="0 0 {v["w"]} {v["h"]}" role="img" aria-labelledby="wf-title wf-desc">',
           f'  <title id="wf-title">{escape(title, quote=False)}</title>',
           f'  <desc id="wf-desc">{escape(desc, quote=False)}</desc>',
           f'  <g id="ui" font-family="{FAMILY}">']
    for tag, attrs in c.items:
        if tag == "#open":
            out.append(f'    <g data-pane="{attrs["data-pane"]}">')
        elif tag == "#close":
            out.append("    </g>")
        else:
            out.append("    " + _element(tag, attrs))
    out.append("  </g>")
    out.append('  <g id="annotations" font-family="' + FAMILY + '">')
    for r in c.regions:
        out.append(f'    <rect data-region="{r["number"]}" x="{r["x"]}" y="{r["y"]}" width="{r["w"]}" '
                   f'height="{r["h"]}" fill="none" stroke="{ACCENT}" stroke-width="1.5" stroke-dasharray="8 8"/>')
    for r in c.regions:
        if r["desc"].startswith("Transition "):
            label_x, label_y = r["x"], r["y"] - 16
        else:
            label_x, label_y = r["x"] - 8, r["y"] + 24
        out.append(f'    <text x="{label_x}" y="{label_y}" font-size="12" font-weight="600" '
                   f'fill="{INK}">{r["number"]}</text>')
    out.append("  </g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _element(tag: str, attrs: dict) -> str:
    parts = [tag]
    for key, value in attrs.items():
        if key == "_text":
            continue
        parts.append(f'{key}="{value}"')
    body = f"<{' '.join(parts)}"
    if "_text" in attrs:
        return body + ">" + escape(attrs["_text"], quote=False) + f"</{tag}>"
    return body + "/>"


# --------------------------------------------------------------------------- manifest and doc
def manifest_entry(defn, vp, fname, regions) -> dict:
    entry = dict(id=defn["id"], kind=defn["kind"], viewport=vp, file=fname, title=defn["title"],
                 route=defn.get("route", ""), context=defn.get("context", ""))
    if defn["kind"] == "state":
        entry["parentScreen"] = defn["parent"]
        entry["stateAppliesTo"] = defn["applies"]
    else:
        entry["parentScreen"] = None
        entry["stateAppliesTo"] = None
    entry["regions"] = [dict(number=r["number"], description=r["desc"]) for r in regions]
    entry["status"] = "proposal"
    return entry


def build_all(out: Path) -> dict:
    entries, flows, pane_plan = [], [], {}
    for defn in SCREENS + STATES:
        panes = pane_items(defn)
        ids = [f"p{i + 1}" for i in range(len(panes))]
        id_map = {id(pane): pid for pane, pid in zip(panes, ids)}
        required = []
        for pane in panes:
            required += list(pane.get("required") or [])
        pane_plan[defn["id"]] = {}
        for vp in ("desktop", "tablet", "mobile"):
            frames, order = plan_frames(defn, vp)
            files = {i + 1: (f"{defn['id']}-{vp}.svg" if i == 0 else f"{defn['id']}-{vp}-part-{i + 1}.svg")
                     for i in range(len(frames))}
            rendered = []
            for i, frame in enumerate(frames):
                c = render_frame(defn, vp, frame, i + 1, len(frames), files, id_map)
                fname = files[i + 1]
                title = defn["title"] + (f" \u2014 part {i + 1} of {len(frames)}" if i else "") + f" \u2014 {vp}"
                (out / fname).write_text(render_svg(c, title), encoding="utf-8")
                units = ([id_map[id(p)] for row in frame["rows"] for _wt, p in row]
                         if frame["layout"] == "rows" else [pid for pid, _p in frame["units"]])
                rendered += units
                entry = manifest_entry(defn, vp, fname, c.regions)
                entry["frameIndex"] = i + 1
                entry["frameCount"] = len(frames)
                entry["renderedPanes"] = units
                entry["previousFrame"] = files.get(i) if i > 0 else None
                entry["nextFrame"] = files.get(i + 2)
                entries.append(entry)
            pane_plan[defn["id"]][vp] = dict(panes=rendered, required=sorted(set(required)))
    for fspec in FLOWS:
        for sid in fspec["screens"]:
            assert (out / f"{sid}-desktop.svg").exists(), f"flow thumb missing {sid}"
        c = build_flow(fspec, out)
        fname = str(fspec["id"]) + ".svg"
        (out / fname).write_text(render_svg(c, str(fspec["title"]) + " \u2014 desktop flow"), encoding="utf-8")
        entries.append(dict(id=str(fspec["id"]), kind="flow", viewport="desktop", file=fname,
                            title=str(fspec["title"]), route="", context="desktop flow board",
                            parentScreen=None, stateAppliesTo=None,
                            flowScreens=[str(s) for s in fspec["screens"]],
                            regions=[dict(number=r["number"], description=r["desc"]) for r in c.regions],
                            status="proposal", frameIndex=1, frameCount=1,
                            renderedPanes=[], previousFrame=None, nextFrame=None))
        flows.append(fspec)
    screen_files = sum(1 for entry in entries if entry["kind"] in ("screen", "state"))
    base = 3 * (len(SCREENS) + len(STATES))
    counts = dict(screens=len(SCREENS), states=len(STATES), definitions=len(SCREENS) + len(STATES),
                  viewports=3, base_frame_files=base,
                  screen_state_files=screen_files, continuation_files=screen_files - base,
                  flows=len(FLOWS), files=screen_files + len(FLOWS))
    return dict(document="20261123-product-wireframe-set.md", date=DATE, generator=FOLDER + "/generate.py",
                validator=FOLDER + "/validate.py", status="proposal", counts=counts,
                screen_ids=[d["id"] for d in SCREENS], state_ids=[d["id"] for d in STATES],
                flow_files=[str(f["id"]) + ".svg" for f in FLOWS],
                pane_plan=pane_plan, entries=entries)


def render_doc(manifest) -> str:
    e = manifest["entries"]
    by_file = {entry["file"]: entry for entry in e}
    out = ["# Product wireframe set (proposal)", "",
           f"Date: {DATE}. Status: **proposal wireframes, not shipped and not implementation evidence.** "
           "Static design artifacts only: no application code, runtime, database, schema or API changed. "
           "All case ids, hosts, quotes and counts are synthetic (`example.invalid`).", "",
           "This set illustrates the five workbench capabilities in "
           "[the evidence workbench specification](20261114-evidence-workbench-specification.md) \u00a7\u00a74\u20138, "
           "[comparison UI](../architecture/20261118-comparison-ui.md), "
           "[changes UI](../architecture/20261120-changes-ui.md) and "
           "[search API](../architecture/20261120-search-api.md). The original single-screen artifact is retained: "
           "[20261123-evidence-workbench-wireframe.md](20261123-evidence-workbench-wireframe.md) / "
           "[.svg](20261123-evidence-workbench-wireframe.svg).", "",
           "## 1. Inventory and shape", "",
           f"- **{manifest['counts']['definitions']} definitions** = {manifest['counts']['screens']} primary screens + "
           f"{manifest['counts']['states']} states, each drawn at **all three viewports** "
           "(desktop 1280\u00d7800, tablet 768\u00d71024, mobile 375\u00d7812).",
           f"- **{manifest['counts']['base_frame_files']} base frame files** plus **{manifest['counts']['continuation_files']} continuation frames** "
           f"= **{manifest['counts']['screen_state_files']} screen/state SVG files**, and **{manifest['counts']['flows']} desktop flow boards** "
           f"= **{manifest['counts']['files']} SVG files** plus `manifest.json`.",
           "- Continuation frames are real screens at the same sanctioned viewport (`-part-2.svg`, `-part-3.svg`) carrying the "
           "remaining panes with compact repeated navigation and a `Part k of N` header; nothing is reduced to a title list.",
           "- Coverage is **bounded and complete for the current routes/tabs plus the documented states below**. "
           "It is not every Cartesian state \u00d7 module permutation and not a claim of implementation coverage.",
           "- Shared state patterns represent multiple applicable modules explicitly in \u00a76; only the named frames exist.",
           "- Each file is standalone SVG, immediately previewable in a browser, with no HTML viewer and no external references.",
           "", "## 2. Scope boundaries and explicit exclusions", "",
           "In scope: low-fidelity layout proposals for the current product surfaces listed in \u00a73 and \u00a74, the five "
           "workbench capabilities, the documented reader states, and navigation/review flow boards.", "",
           "Out of scope, and **not authorized by this artifact**: authentication and RBAC, public ingestion or a browser "
           "ingestion form, real-time collaboration, notifications, OCR, semantic/vector search, automated truth "
           "certification, production data recovery or repair, new API/schema fields, and any change to CI or app code. "
           "These remain separate proposals; drawing a placeholder for them would invent scope.", "",
           "Navigation is browse-GET only. The only browser writes drawn are the three narrow human review POST families "
           "(review decision, exception action, review annotation). Ingest, rerun, rebuild and recovery stay CLI-only, "
           "local/trusted and unauthenticated. The annotation form is labelled as an explicit exception to the reader rule. "
           "The review API also accepts `defer`/`exception`; the current browser controls are Approve, action_required and "
           "Reject only, so no extra browser control is drawn.", "",
           "## 3. Route to screen mapping (10 routes)", ""]
    route_rows = [
        ("/dashboard", "dashboard"), ("/cases", "case-explorer"), ("/cases/new", "operator-launch"),
        ("/cases/:id/*", "case-overview + 12 case tabs"), ("/cases/:id/pipeline", "pipeline"),
        ("/cases/:id/network", "corroboration-network"), ("/cases/:id/sources", "source-provenance"),
        ("/cases/:id/narratives", "narratives"), ("/monitoring", "monitoring"), ("/ai-info", "ai-info"),
    ]
    out += ["| Route | Screens |", "|---|---|"]
    out += [f"| `{r}` | {s} |" for r, s in route_rows]
    out += ["", "Tab paths: overview and the review/annotation form are the index route `/cases/:id/` (path `''`); the "
            "canonical inspector is `/cases/:id/evidence?claim=&evidence=&capture=`; the frozen claim panel is on "
            "`/cases/:id/changes?run=&claim=&snapshot=`.", "",
            "## 4. Case tab to screen mapping (12 tabs)", "",
            "| Tab | Screens |", "|---|---|",
            "| Overview | case-overview, review-annotation |",
            "| Evidence | evidence-gallery, source-provenance |",
            "| Claims | claims, capture-inspector, historical-snapshot |",
            "| Compare | comparison |", "| Parties | parties |", "| Map | geographic-map |",
            "| Timeline | timeline |", "| Exceptions | exception-queue |", "| Report | report |",
            "| Changes | runs-changes |", "| Search | search |", "| Run history | stage-history |", "",
            "## 5. Five-capability matrix", "",
            "| Capability | Primary screens |", "|---|---|",
            "| E1 claim \u2192 quotation \u2192 capture inspector | claims, capture-inspector, historical-snapshot, review-annotation |",
            "| E2 provenance and dependency grouping | source-provenance, comparison |",
            "| E3 side-by-side comparison | comparison |",
            "| E4 durable runs and changes | runs-changes, stage-history, historical-snapshot, pipeline |",
            "| E5 case search and stable links | search, case-overview |", "",
            "## 6. State applicability matrix (42 states)", "",
            "Each state exists as three files. `applies` lists the modules the shared pattern represents; only the parent "
            "screen's frame exists. A generic network failure is a shared pattern in addition to the named frames.", "",
            "| State | Parent screen | Applies to | Files |", "|---|---|---|---|"]
    for defn in STATES:
        links = ", ".join(f"[{vp}]({FOLDER}/{defn['id']}-{vp}.svg)" for vp in ("desktop", "tablet", "mobile"))
        out.append(f"| {defn['id']} | {defn['parent']} | {defn['applies']} | {links} |")
    out += ["", "## 7. Pagination and full render coverage", "",
            "Every definition is drawn at all three viewports: desktop 1280\u00d7800 with a 240 px navigation rail, tablet "
            "768\u00d71024 and mobile 375\u00d7812 with a top bar (mobile uses a menu control). Panes that sit side by side on "
            "desktop stack on tablet and mobile; tables become labelled blocks on mobile. All regions use 24 px horizontal "
            "and vertical gutters; the mobile canvas uses a 368\u00d7808 drawing rect with a 375\u00d7812 root viewport "
            "(the only non-8 multiple).", "",
            "When the body does not fit one viewport, the **remaining panes are rendered in continuation frames** at the same "
            "viewport (`<id>-<viewport>-part-2.svg`, ...). Each frame repeats compact navigation and carries a `Part k of N` "
            "header with previous/next frame labels; every pane is wrapped in `<g data-pane=\"pN\">` and the manifest records "
            "`renderedPanes`, `frameIndex` and `frameCount` per file. The validator asserts that, for every definition and "
            "viewport, the union of rendered pane ids equals the declared pane inventory exactly once \u2014 no pane, control, "
            "field group, status vocabulary or metadata row is dropped. A pane too tall for one compact frame is split into "
            "real parts, and field groups keep their actions after the last group.", "",
            "Frame counts below are derived by the generator, not fixed. Every definition at every viewport is base frame 1 "
            "plus the listed continuations.", "",
            "| Definition | desktop | tablet | mobile |", "|---|---|---|---|"]
    for defn in SCREENS + STATES:
        counts = [str(sum(1 for entry in e if entry["id"] == defn["id"] and entry["viewport"] == vp))
                  for vp in ("desktop", "tablet", "mobile")]
        if any(count != "1" for count in counts):
            out.append(f"| {defn['id']} | {counts[0]} | {counts[1]} | {counts[2]} |")
    out += ["", "## 8. Flow boards (10)", "",
            "Flow order labels are **navigation and review paths, not automatic execution or causal state transitions**. "
            "Thumbnails are geometry-derived miniatures of the desktop SVGs (rect/line primitives, snapped to 8 px); "
            "source text is omitted below the 12 px legibility floor and every thumbnail is captioned outside the frame. "
            "Annotations number each thumbnail and each transition. Annotation style exception: normal region numbers sit in "
            "the left gutter (24 px horizontal and vertical gutters, 8 px callout offset); the ten flow boards' narrow 16 px "
            "transition regions put their number immediately above the region instead, clear of the arrow and its caption.", "",
            "| Board | Screens (left to right) | File |", "|---|---|---|"]
    for fspec in FLOWS:
        ftitle, fsid = str(fspec["title"]), str(fspec["id"])
        screens = " \u2192 ".join(str(s) for s in fspec["screens"])
        out.append(f"| {ftitle} | {screens} | [{fsid}.svg]({FOLDER}/{fsid}.svg) |")
    out += ["", "## 9. Proposal status and honesty rules", "",
            "Every SVG is a proposal: `<desc>` states it, headers/captions carry `Proposal \u00b7 synthetic data`, and the "
            "status is recorded per manifest entry. Nothing here is evidence that a capability exists. Drawings must not "
            "contradict implemented invariants: capture is not verification; an exact quotation is not entailment; "
            "generated relations are `reported_by` or `uncertain`; model assessment provenance stays visible; a missing "
            "value is `unavailable`, never zero; independence is `unknown` unless a dependency edge is detected; configured "
            "is not completed; pending is not final; an empty delta with partial coverage is not \"all sources unchanged\"; "
            "party stance and Arbiter consensus are not truth.", "",
            "Review-specific: `review-failed` is an explicit **409 active case writer conflict** with a read/refresh action; "
            "it does not claim the decision was saved and retains entered notes. Generic transport failure is a shared "
            "pattern, distinct from 409. `review-blocked` is **422 approval blocked by unresolved exceptions** and links the "
            "exception queue without saving. `annotation-invalid` covers a bad target and blank content (422). "
            "`evaluation-unavailable` is no saved evaluation (never 0); `evaluation-failed` is a failed evaluation read "
            "(retry, not pending and not empty). An unrecognized case tab route falls back to `shared-not-found` "
            "(\"Tab not found\"); it has no separate frame.", "",
            "## 10. Interaction intent (SVG files are static)", "",
            "Keyboard and focus intent is documented, not implemented: selection survives reload/back/forward through URL "
            "parameters (`claim`, `evidence`, `capture`, `citation`, `snapshot`, `tab`, `run`, `offset`, query/filters); the "
            "selected inspector or results heading receives focus once per selection; native select and button semantics "
            "are assumed; tab strips scroll horizontally on mobile. No SVG is interactive: no scripts, styles, links or "
            "`<a>` elements exist here.", "",
            "## 11. Regenerate and validate", "",
            "```bash",
            "uv run --no-sync python docs/plans/20261123-product-wireframes/generate.py",
            "uv run --no-sync python docs/plans/20261123-product-wireframes/validate.py",
            "```", "",
            "Generation is deterministic (no timestamps in output); running it twice produces byte-identical files. "
            "The validator holds the authoritative non-computed inventory (24 screen ids, 42 state ids, 10 flow files), "
            "re-runs generation in temporary directories, and checks XML, geometry, palette, fonts, strokes, annotation "
            "mapping, doc links, manifest bijection, counts, flow coverage and the mobile canvas exception. Source-of-truth "
            "context: `frontend/src/app/routes.tsx`, `frontend/src/pages/CaseIntelligenceCenter.tsx`, "
            "`frontend/src/pages/tabs/`, `docs/plans/20261114-evidence-workbench-specification.md` \u00a7\u00a74\u20138, "
            "`docs/architecture/20261118-comparison-ui.md`, `docs/architecture/20261120-changes-ui.md`, "
            "`docs/architecture/20261120-search-api.md`, `docs/reference/http-api.md`.", "",
            "## 12. Per-file numbered annotations", "",
            "Region numbers match `data-region` in each SVG and the manifest `regions` array one-to-one. Empty list means "
            "the file failed generation; the validator rejects that.", ""]
    for entry in e:
        out += [f"### {entry['file']}", "",
                f"[Open SVG]({FOLDER}/{entry['file']}) \u00b7 {entry['kind']} \u00b7 {entry['viewport']} \u00b7 "
                f"{entry['title']}" + (f" \u00b7 frame {entry.get('frameIndex')} of {entry.get('frameCount')}" if entry.get("frameCount", 1) > 1 else "")
                + (f" \u00b7 route `{entry['route']}`" if entry.get("route") else "")
                + (f" \u00b7 parent `{entry['parentScreen']}`" if entry.get("parentScreen") else "")
                + (f" \u00b7 screens: {', '.join(entry['flowScreens'])}" if entry.get("flowScreens") else ""), ""]
        for region in entry["regions"]:
            out.append(f"{region['number']} \u2014 {region['description']}")
        out.append("")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description="Generate the product wireframe set.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="directory for SVG files and manifest.json")
    parser.add_argument("--doc", default=str(DEFAULT_DOC), help="path of the dated index/coverage doc")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict = build_all(out)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(args.doc).write_text(render_doc(manifest), encoding="utf-8")
    print(f"wrote {int(manifest['counts']['files'])} SVG files + manifest.json to {out}")
    print(f"wrote {args.doc}")


if __name__ == "__main__":
    main()
