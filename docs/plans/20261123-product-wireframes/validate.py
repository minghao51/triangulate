#!/usr/bin/env python3
"""Validate the 2026-11-23 product wireframe set (stdlib only, no network).

    uv run --no-sync python docs/plans/20261123-product-wireframes/validate.py

Authoritative, literal inventory: 24 screen ids, 42 state ids, 10 flow files,
three viewports. Every definition must have a base frame per viewport; any
further frames are continuations named <id>-<viewport>-part-<k>.svg, linked by
the manifest previous/next chain. Coverage is proven by <g data-pane> groups:
for every definition and viewport the union of rendered pane ids must equal the
declared pane plan exactly once, and every required control label declared by
the generator's source specs must appear in rendered UI text (never in <desc>).
"""

from __future__ import annotations

import hashlib
import json
import re
import runpy
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DOC = ROOT / "docs/plans/20261123-product-wireframe-set.md"
MANIFEST = HERE / "manifest.json"
GENERATE = HERE / "generate.py"
FOLDER = HERE.name

SCREEN_IDS = [
    "dashboard", "case-explorer", "operator-launch", "case-overview", "review-annotation",
    "evidence-gallery", "claims", "capture-inspector", "comparison", "source-provenance",
    "runs-changes", "historical-snapshot", "search", "stage-history", "pipeline",
    "exception-queue", "parties", "geographic-map", "timeline", "report",
    "corroboration-network", "narratives", "monitoring", "ai-info",
]
STATE_IDS = [
    "shared-loading", "shared-empty", "shared-not-found", "shared-network-error",
    "inspector-missing-quotation", "inspector-source-unavailable", "inspector-ambiguous",
    "inspector-no-match", "inspector-legacy",
    "comparison-selection", "comparison-same-source", "comparison-no-second-source",
    "comparison-empty", "comparison-historical-unavailable", "comparison-dependency-warning",
    "changes-initial", "changes-pending", "changes-unavailable", "changes-unchanged-partial",
    "search-no-results", "search-index-unavailable", "search-invalid-filters", "search-out-of-range",
    "review-saving", "review-failed", "review-stale", "review-saved", "review-blocked",
    "annotation-invalid", "evaluation-unavailable", "evaluation-failed",
    "exception-pending", "exception-failed", "exception-empty",
    "report-pending", "report-download-error", "map-empty", "timeline-unknown",
    "pipeline-unrecorded", "monitoring-unavailable", "evidence-filter-empty", "narratives-empty",
]
FLOW_FILES = [
    "flow.svg", "flow-claims-review.svg", "flow-compare-provenance.svg",
    "flow-changes-history.svg", "flow-search-snapshot.svg", "flow-operator-pipeline.svg",
    "flow-review-exceptions.svg", "flow-geography-parties.svg", "flow-network-report.svg",
    "flow-dashboard-ai.svg",
]
VIEWPORTS = ("desktop", "tablet", "mobile")
VP_SIZE = {"desktop": (1280, 800), "tablet": (768, 1024), "mobile": (375, 812)}
SIZES = {12, 14, 20, 28}
COLORS = {"#fff", "#e6e6e6", "#000", "#666", "#d33"}
FAMILY = "-apple-system, system-ui, sans-serif"
ALLOWED_TAGS = {"rect", "line", "text", "g", "title", "desc", "svg"}
GEOM = {"x", "y", "width", "height", "x1", "y1", "x2", "y2"}
ROOT_ATTRS = {"xmlns", "width", "height", "viewBox", "role", "aria-labelledby"}
ATTRS = {
    "svg": ROOT_ATTRS,
    "g": {"id", "font-family", "data-pane"},
    "title": {"id"},
    "desc": {"id"},
    "rect": {"x", "y", "width", "height", "fill", "stroke", "stroke-width",
             "stroke-dasharray", "data-region"},
    "line": {"x1", "y1", "x2", "y2", "stroke", "stroke-width"},
    "text": {"x", "y", "font-size", "fill", "font-weight", "text-anchor"},
}
DOC_ANCHORS = [
    "Scope boundaries", "Route to screen mapping", "Case tab to screen mapping",
    "Five-capability matrix", "State applicability matrix", "Pagination and full render coverage",
    "Flow boards", "Per-file numbered annotations",
    "uv run --no-sync python docs/plans/20261123-product-wireframes/validate.py",
    "not implementation evidence",
]
DEFINITION_IDS = SCREEN_IDS + STATE_IDS

errors: list[str] = []


def fail(where: str, message: str):
    errors.append(f"{where}: {message}")


def local(tag: str) -> str:
    return tag.split("}")[-1]


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def base_files() -> list[str]:
    return [f"{sid}-{vp}.svg" for sid in DEFINITION_IDS for vp in VIEWPORTS]


def inspect_svg(path: Path, vp: str):
    """Return (region count, pane ids in document order, ui text list)."""
    rel = path.name
    raw = path.read_text(encoding="utf-8")
    first = raw.splitlines()[0] if raw else ""
    match = re.fullmatch(r"<!-- viewport: (\d+)\u00d7(\d+) (desktop|tablet|mobile) -->", first)
    if not match:
        fail(rel, f"first line is not the viewport comment: {first!r}")
        return 0, [], []
    if (int(match.group(1)), int(match.group(2)), match.group(3)) != (VP_SIZE[vp][0], VP_SIZE[vp][1], vp):
        fail(rel, "viewport comment does not match its viewport")
    wid, hei = VP_SIZE[vp]
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        fail(rel, f"XML parse error: {exc}")
        return 0, [], []
    if local(root.tag) != "svg":
        fail(rel, "root element is not svg")
    if 'xmlns="http://www.w3.org/2000/svg"' not in raw:
        fail(rel, "missing svg namespace")
    if root.get("role") != "img":
        fail(rel, "root role is not img")
    if root.get("aria-labelledby") != "wf-title wf-desc":
        fail(rel, "aria-labelledby does not reference wf-title wf-desc")
    if vp == "mobile":
        if (root.get("width"), root.get("height")) != ("375", "812"):
            fail(rel, "mobile root canvas must be 375x812")
    else:
        if (root.get("width"), root.get("height")) != (str(wid), str(hei)):
            fail(rel, "root width/height do not match the viewport")
        for dim in ("width", "height"):
            if int(root.get(dim, "0")) % 8:
                fail(rel, f"root {dim} is not a multiple of 8 outside mobile")
    if root.get("viewBox") != f"0 0 {wid} {hei}":
        fail(rel, "viewBox does not match the viewport")

    children = list(root)
    ids = {child.get("id"): child for child in children if local(child.tag) in ("title", "desc")}
    if set(ids) != {"wf-title", "wf-desc"}:
        fail(rel, "title/desc ids are not wf-title/wf-desc")
    desc_el = ids.get("wf-desc")
    desc_text = (desc_el.text or "") if desc_el is not None else ""
    if "Proposal" not in desc_text or "synthetic" not in desc_text:
        fail(rel, "desc does not state proposal status and synthetic data")
    groups = [child for child in children if local(child.tag) == "g"]
    if not groups or groups[0].get("id") != "ui":
        fail(rel, "first group is not g#ui")
    if not groups or groups[-1].get("id") != "annotations":
        fail(rel, "last group is not g#annotations")
    annotation_group = groups[-1] if groups and groups[-1].get("id") == "annotations" else None
    if children and children[-1] is not annotation_group:
        fail(rel, "annotation group is not the last child of svg")
    ui = groups[0] if groups and groups[0].get("id") == "ui" else None

    def check_attrs(el):
        name = local(el.tag)
        if name not in ALLOWED_TAGS:
            fail(rel, f"element <{name}> is not allowed")
            return
        for key, value in el.attrib.items():
            if key not in ATTRS[name]:
                fail(rel, f"attribute {key} is not allowed on <{name}>")
            if key == "fill" and value not in COLORS | {"none"}:
                fail(rel, f"fill {value} is outside the palette")
            if key == "stroke" and value not in ("#000", "#d33"):
                fail(rel, f"stroke {value} is outside the palette")
            if key == "stroke-width" and value != "1.5":
                fail(rel, f"stroke-width {value} is not 1.5")
            if key == "stroke-dasharray" and value != "8 8":
                fail(rel, f"stroke-dasharray {value} is not 8 8")
            if key == "font-family" and value != FAMILY:
                fail(rel, "unexpected font-family")
            if key == "font-size" and int(value) not in SIZES:
                fail(rel, f"font-size {value} is not 12/14/20/28")
            if key == "font-weight" and value != "600":
                fail(rel, f"font-weight {value} is not 600")

    pane_ids: list[str] = []
    ui_texts: list[str] = []
    for el in root.iter():
        if local(el.tag) == "svg":
            continue
        check_attrs(el)
        name = local(el.tag)
        for key, value in el.attrib.items():
            if key in GEOM:
                try:
                    ival = int(value)
                except ValueError:
                    fail(rel, f"<{name}>: non-integer geometry {key}={value}")
                    continue
                if ival % 8:
                    fail(rel, f"<{name}>: off-grid {key}={value}")
        if name == "rect":
            x, y = int(el.get("x", 0)), int(el.get("y", 0))
            w, h = int(el.get("width", 0)), int(el.get("height", 0))
            if x < 0 or y < 0 or x + w > wid or y + h > hei:
                fail(rel, f"rect outside viewBox ({x},{y},{w},{h})")
            if el.get("stroke-dasharray") and el.get("data-region") is None:
                fail(rel, "dashed stroke outside the annotation layer")
            if (el.get("stroke") == "#d33" or el.get("fill") == "none") and el.get("data-region") is None:
                fail(rel, "accent colour or fill=none outside the annotation layer")
        if name == "line":
            xs = [int(el.get(k, 0)) for k in ("x1", "x2")]
            ys = [int(el.get(k, 0)) for k in ("y1", "y2")]
            if min(xs) < 0 or max(xs) > wid or min(ys) < 0 or max(ys) > hei:
                fail(rel, "line outside viewBox")
        if name == "text":
            if not (el.text or "").strip():
                fail(rel, "empty text element")
            if el.get("font-size") is None:
                fail(rel, "text without font-size")
            if el.get("data-region") is None:
                ui_texts.append(el.text or "")
        if name == "g" and el.get("data-pane") and el is not annotation_group:
            if el.get("id") is not None or el.get("font-family") is not None:
                fail(rel, "pane group must carry only data-pane")
            pane_ids.append(el.get("data-pane") or "")
    if ui is not None:
        for child in ui:
            if local(child.tag) == "g" and child.get("data-pane") is None:
                fail(rel, "g inside ui without data-pane")
    if pane_ids and len(set(pane_ids)) != len(pane_ids):
        fail(rel, f"duplicate data-pane keys: {pane_ids}")

    region_count = 0
    if annotation_group is not None:
        annotations = list(annotation_group)
        rects = [el for el in annotations if local(el.tag) == "rect"]
        labels = [el for el in annotations if local(el.tag) == "text"]
        for el in annotations:
            if local(el.tag) not in ("rect", "text"):
                fail(rel, f"annotation layer contains <{local(el.tag)}>")
        region_count = len(rects)
        numbers, boxes = [], []
        for el in rects:
            region = el.get("data-region")
            if region is None or not region.isdigit():
                fail(rel, "annotation rect without a numeric data-region")
                continue
            numbers.append(int(region))
            if el.get("stroke") != "#d33" or el.get("stroke-dasharray") != "8 8":
                fail(rel, f"region {region} is not dashed accent")
            if el.get("fill") != "none":
                fail(rel, f"region {region} fill is not none")
            x, y = int(el.get("x", 0)), int(el.get("y", 0))
            w, h = int(el.get("width", 0)), int(el.get("height", 0))
            if x < 0 or y < 0 or x + w > wid or y + h > hei:
                fail(rel, f"region {region} clips the viewBox")
            boxes.append((int(region), x, y, w, h))
        if sorted(numbers) != list(range(1, len(rects) + 1)):
            fail(rel, f"data-region values are not 1..N: {numbers}")
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                _, ax, ay, aw, ah = boxes[i]
                _, bx, by, bw, bh = boxes[j]
                if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                    fail(rel, f"annotation regions {boxes[i][0]} and {boxes[j][0]} overlap")
        label_values = []
        for el in labels:
            value = (el.text or "").strip()
            if not value.isdigit():
                fail(rel, f"annotation label {value!r} is not numeric")
                continue
            label_values.append(int(value))
            if el.get("fill") != "#000":
                fail(rel, f"annotation label {value} is not black")
            if el.get("font-weight") != "600" or el.get("font-size") != "12":
                fail(rel, f"annotation label {value} is not 12px bold")
            lx, ly = int(el.get("x", 0)), int(el.get("y", 0))
            if ly < 16:
                fail(rel, f"annotation label {value} baseline {ly} < 16 (glyph would clip)")
            if lx < 0:
                fail(rel, f"annotation label {value} starts outside the canvas")
            box = next((b for b in boxes if b[0] == int(value)), None)
            if box is None:
                fail(rel, f"annotation label {value} has no region")
                continue
            transition = rel.startswith("flow") and box[3] == 32
            expected = (box[1], box[2] - 16) if transition else (box[1] - 8, box[2] + 24)
            if (lx, ly) != expected:
                fail(rel, f"annotation label {value} is not in its expected gutter")
        if sorted(label_values) != list(range(1, len(rects) + 1)):
            fail(rel, "annotation labels do not match region numbers one-to-one")
    return region_count, pane_ids, ui_texts


def check_manifest(manifest, svg_regions):
    if manifest.get("status") != "proposal":
        fail("manifest", "status is not proposal")
    if manifest.get("screen_ids") != SCREEN_IDS:
        fail("manifest", "screen_ids do not match the inventory")
    if manifest.get("state_ids") != STATE_IDS:
        fail("manifest", "state_ids do not match the inventory")
    if manifest.get("flow_files") != FLOW_FILES:
        fail("manifest", "flow_files do not match the inventory")
    entries = manifest.get("entries", [])
    files = [entry.get("file") for entry in entries]
    if len(files) != len(set(files)):
        fail("manifest", "duplicate manifest files")
    bases, flows = set(base_files()), set(FLOW_FILES)
    missing_bases = sorted(bases - set(files))
    if missing_bases:
        fail("manifest", f"missing base files: {missing_bases[:6]}")
    if not flows <= set(files):
        fail("manifest", f"missing flow files: {sorted(flows - set(files))}")
    names = set(files)
    for name in sorted(names - bases - flows):
        entry = next(en for en in entries if en["file"] == name)
        stem = name[:-4]
        match = re.fullmatch(r"(.+)-(desktop|tablet|mobile)-part-(\d+)", stem)
        if not match:
            fail("manifest", f"unexpected file name {name}")
            continue
        sid, vp, part = match.group(1), match.group(2), int(match.group(3))
        if part < 2 or sid != entry.get("id") or vp != entry.get("viewport"):
            fail("manifest", f"{name} does not encode id/viewport/part correctly")
    # per definition/viewport frame chains
    frames = {}
    for entry in entries:
        if entry.get("kind") in ("screen", "state", "flow"):
            frames.setdefault((entry.get("id"), entry.get("viewport")), []).append(entry)
    for sid in DEFINITION_IDS:
        for vp in VIEWPORTS:
            chain = sorted(frames.get((sid, vp), []), key=lambda en: en.get("frameIndex", 0))
            if not chain:
                fail("manifest", f"{sid}/{vp}: no frames")
                continue
            if [en.get("frameIndex") for en in chain] != list(range(1, len(chain) + 1)):
                fail("manifest", f"{sid}/{vp}: frameIndex is not 1..N")
            if chain[0].get("file") != f"{sid}-{vp}.svg":
                fail("manifest", f"{sid}/{vp}: first frame is not the base file")
            for i, en in enumerate(chain):
                if en.get("frameCount") != len(chain):
                    fail("manifest", f"{en.get('file')}: frameCount is not {len(chain)}")
                want = f"{sid}-{vp}-part-{i + 1}.svg" if i else f"{sid}-{vp}.svg"
                if en.get("file") != want:
                    fail("manifest", f"{en.get('file')}: expected {want}")
                prev = chain[i - 1]["file"] if i else None
                nxt = chain[i + 1]["file"] if i + 1 < len(chain) else None
                if en.get("previousFrame") != prev or en.get("nextFrame") != nxt:
                    fail("manifest", f"{en.get('file')}: previous/next frame links are wrong")
    plan = manifest.get("pane_plan") or {}
    for sid in DEFINITION_IDS:
        if sid not in plan:
            fail("manifest", f"pane_plan misses {sid}")
            continue
        for vp in VIEWPORTS:
            chain = sorted(frames.get((sid, vp), []), key=lambda en: en.get("frameIndex", 0))
            rendered = [pid for en in chain for pid in en.get("renderedPanes", [])]
            expected = (plan[sid].get(vp) or {}).get("panes") or []
            if rendered != expected:
                fail("manifest", f"{sid}/{vp}: renderedPanes union {rendered} != pane_plan {expected}")
            if len(rendered) != len(set(rendered)):
                fail("manifest", f"{sid}/{vp}: a pane id is rendered in more than one frame")
            for en in chain:
                if en.get("renderedPanes"):
                    delta = svg_regions.get(en["file"])
                    del delta
    counts = manifest.get("counts") or {}
    screen_entries = [en for en in entries if en.get("kind") in ("screen", "state")]
    expect = dict(screens=len(SCREEN_IDS), states=len(STATE_IDS), definitions=len(DEFINITION_IDS),
                  viewports=3, base_frame_files=len(base_files()),
                  screen_state_files=len(screen_entries),
                  continuation_files=len(screen_entries) - len(base_files()),
                  flows=len(FLOW_FILES), files=len(entries))
    for key, value in expect.items():
        if counts.get(key) != value:
            fail("manifest", f"count {key}={counts.get(key)} but expected {value}")
    for entry in entries:
        rel = str(entry.get("file"))
        if entry.get("status") != "proposal":
            fail("manifest", f"{rel}: status is not proposal")
        regions = entry.get("regions") or []
        if [r.get("number") for r in regions] != list(range(1, len(regions) + 1)):
            fail("manifest", f"{rel}: region numbers are not 1..N")
        if any(not str(r.get("description", "")).strip() for r in regions):
            fail("manifest", f"{rel}: empty region description")
        if rel in svg_regions and len(regions) != svg_regions[rel]:
            fail("manifest", f"{rel}: {len(regions)} regions in manifest but {svg_regions[rel]} in SVG")
        if entry.get("kind") == "flow":
            screens = entry.get("flowScreens") or []
            if entry.get("viewport") != "desktop" or not 2 <= len(screens) <= 4:
                fail("manifest", f"{rel}: flow needs desktop viewport and 2-4 screens")
            for screen in screens:
                if screen not in SCREEN_IDS:
                    fail("manifest", f"{rel}: unknown flow screen {screen}")
        if entry.get("kind") in ("screen", "state") and rel.endswith(".svg") and "part-" not in rel:
            pass
    covered = set()
    for entry in entries:
        if entry.get("kind") == "flow":
            covered.update(entry.get("flowScreens") or [])
    if covered != set(SCREEN_IDS):
        fail("manifest", f"flow coverage missing {sorted(set(SCREEN_IDS) - covered)} extra {sorted(covered - set(SCREEN_IDS))}")
    return frames


def check_plan_against_source(manifest):
    module = runpy.run_path(str(GENERATE))
    pane_items = module["pane_items"]
    defs = {d["id"]: d for d in list(module["SCREENS"]) + list(module["STATES"])}
    plan = manifest.get("pane_plan") or {}
    if sorted(plan) != sorted(DEFINITION_IDS):
        fail("plan", "pane_plan keys do not match the definitions")
    for sid, defn in defs.items():
        panes = pane_items(defn)
        ids = [f"p{i + 1}" for i in range(len(panes))]
        required = sorted({label for pane in panes for label in (pane.get("required") or [])})
        for vp in VIEWPORTS:
            slot = (plan.get(sid) or {}).get(vp) or {}
            rendered = slot.get("panes") or []
            base_order = []
            for pid in rendered:
                base = pid.split(".")[0]
                if base not in base_order:
                    base_order.append(base)
            parts_ok = all(re.fullmatch(r"p\d+(\.\d+)?", pid) for pid in rendered)
            if base_order != ids or not parts_ok:
                fail("plan", f"{sid}/{vp}: pane ids {rendered} do not cover source panes {ids}")
            if sorted(slot.get("required") or []) != required:
                fail("plan", f"{sid}/{vp}: required labels {slot.get('required')} != source {required}")


def normalize(text: str) -> str:
    return (text.replace("\u2026", "").replace(" (disabled)", "").replace("(", " ").replace(")", " ")
            .strip().lower())


def check_required_labels(manifest, frames, ui_texts):
    plan = manifest.get("pane_plan") or {}
    for sid in DEFINITION_IDS:
        for vp in VIEWPORTS:
            required = (plan.get(sid, {}).get(vp) or {}).get("required") or []
            if not required:
                continue
            texts = []
            for entry in sorted(frames.get((sid, vp), []), key=lambda en: en.get("frameIndex", 0)):
                texts += [normalize(t) for t in ui_texts.get(entry["file"], [])]
            haystack = "\n".join(texts)
            for label in required:
                needle = normalize(label)
                found = any(t == needle or t.startswith(needle) or needle in t for t in texts)
                if not found:
                    fail("coverage", f"{sid}/{vp}: required control {label!r} is not rendered in UI text")
            if "required" in haystack:
                pass


def check_doc(manifest):
    if not DOC.exists():
        fail("doc", "dated doc is missing")
        return
    lines = DOC.read_text(encoding="utf-8").splitlines()
    for anchor in DOC_ANCHORS:
        if not any(anchor in line for line in lines):
            fail("doc", f"required anchor missing: {anchor}")
    sections, current = {}, None
    for line in lines:
        if line.startswith("### "):
            current = line[4:].strip()
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    for entry in manifest.get("entries", []):
        rel = str(entry.get("file"))
        if rel not in sections:
            fail("doc", f"missing annotation section for {rel}")
            continue
        body = sections[rel]
        if f"[Open SVG]({FOLDER}/{rel})" not in "\n".join(body):
            fail("doc", f"section for {rel} does not link the SVG")
        parsed = []
        for line in body:
            m = re.fullmatch(r"(\d+) \u2014 (.+)", line)
            if m:
                parsed.append((int(m.group(1)), m.group(2)))
        expected = [(r["number"], r["description"]) for r in entry.get("regions", [])]
        if parsed != expected:
            fail("doc", f"annotation list for {rel} does not match the manifest one-to-one")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_reproducible():
    with tempfile.TemporaryDirectory() as tmp:
        runs = []
        for name in ("one", "two"):
            out = Path(tmp) / name
            out.mkdir()
            doc = out / "doc.md"
            proc = subprocess.run([sys.executable, str(GENERATE), "--out", str(out), "--doc", str(doc)],
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                fail("generate", f"generator failed ({name}): {proc.stderr.strip()[-400:]}")
                return
            runs.append((out, doc))
        (a, doc_a), (b, doc_b) = runs
        files_a = sorted(p.name for p in a.glob("*.svg"))
        files_b = sorted(p.name for p in b.glob("*.svg"))
        if files_a != files_b:
            fail("generate", "two runs produced different file sets")
        for name in files_a:
            if digest(a / name) != digest(b / name):
                fail("generate", f"two runs differ for {name}")
        if digest(doc_a) != digest(doc_b):
            fail("generate", "two runs produced different docs")
        manifest_tmp, manifest_disk = load_json(a / "manifest.json"), load_json(MANIFEST)
        if manifest_tmp is None or manifest_disk is None:
            fail("generate", "generated or checked-in manifest.json is not valid JSON")
        elif manifest_tmp != manifest_disk:
            fail("generate", "checked-in manifest.json is stale")
        if doc_a.read_text(encoding="utf-8") != DOC.read_text(encoding="utf-8"):
            fail("generate", "checked-in dated doc is stale")
        for name in files_a:
            if digest(a / name) != digest(HERE / name):
                fail("generate", f"checked-in {name} is stale")
                break


def main() -> int:
    manifest = load_json(MANIFEST)
    if manifest is None:
        print("manifest.json missing or invalid")
        return 1
    disk = sorted(p.name for p in HERE.glob("*.svg"))
    manifest_files = sorted(str(entry.get("file")) for entry in manifest.get("entries", []))
    if disk != manifest_files:
        fail("files", f"disk vs manifest mismatch; missing {sorted(set(manifest_files) - set(disk))[:5]} "
                      f"extra {sorted(set(disk) - set(manifest_files))[:5]}")
    svg_regions, ui_texts, svg_panes = {}, {}, {}
    for rel in manifest_files:
        path = HERE / rel
        if not path.exists():
            continue
        stem = rel[:-4] if rel.endswith(".svg") else rel
        vp = "desktop" if rel in FLOW_FILES else stem.rsplit("-part-", 1)[0].rsplit("-", 1)[-1]
        if vp not in VIEWPORTS:
            vp = "desktop"
        regions, pane_ids, texts = inspect_svg(path, vp)
        svg_regions[rel] = regions
        svg_panes[rel] = pane_ids
        ui_texts[rel] = texts
    frames = check_manifest(manifest, svg_regions)
    for entry in manifest.get("entries", []):
        rel = str(entry.get("file"))
        if entry.get("kind") == "flow":
            continue
        want = list(entry.get("renderedPanes") or [])
        got = svg_panes.get(rel, [])
        if got != want:
            fail(rel, f"data-pane keys {got} != manifest renderedPanes {want}")
    check_plan_against_source(manifest)
    check_required_labels(manifest, frames, ui_texts)
    check_doc(manifest)
    check_reproducible()

    if errors:
        print(f"FAILED: {len(errors)} issue(s)")
        for message in errors[:100]:
            print(f"  - {message}")
        return 1
    counts = manifest["counts"]
    print(f"OK: {counts['files']} SVG files validated")
    print(f"  screens={len(SCREEN_IDS)} states={len(STATE_IDS)} definitions={len(DEFINITION_IDS)}")
    print(f"  base frames={counts['base_frame_files']} continuations={counts['continuation_files']} "
          f"flows={counts['flows']} screen/state files={counts['screen_state_files']}")
    print("  pane coverage, required controls, label baselines >=16, frame chains, doc mapping, "
          "flow coverage and reproducibility verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
