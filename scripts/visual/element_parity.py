"""Strict, auditable element parity for the real reference and native captures.

This consumes independently extracted trees; it never manufactures native
elements from the reference. Unknown measurements, incomplete matrices and
missing captures fail the gate. Pixel differences are a second signal only.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import difflib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
from typing import Any


PLATFORMS = ("windows", "macos")
CLIENTS = ("reference",) + PLATFORMS
REGIONS = {"window", "header", "sidebar", "conversation", "composer", "right-pane", "dialog", "menu"}
KINDS = {"region", "text", "button", "icon-button", "input", "toggle", "checkbox", "tab", "menu-item", "dropdown", "chip", "badge", "avatar", "state-dot", "card", "list-row", "divider", "code", "chart-node", "chart-edge", "icon", "image", "link"}
STYLE_FIELDS = ("font_size", "font_weight", "foreground", "background", "border_color", "border_width", "corner_radius")
STATE_FIELDS = ("enabled", "selected", "checked", "expanded", "focused", "hovered", "unread")
LAYOUT_FIELDS = ("wrap", "truncation", "line_count")
INTERACTIVE = {"button", "icon-button", "input", "toggle", "checkbox", "tab", "menu-item", "dropdown", "link"}
CATEGORIES = ("missing", "extra", "text_mismatch", "geometry_out_of_tolerance", "style_out_of_tolerance", "state_mismatch", "kind_mismatch", "region_mismatch", "order_mismatch", "layout_mismatch", "icon_mismatch", "extraction_errors")
SMOKE_SCENES = ("group", "private", "overview", "settings-appearance", "new-org", "copies", "chart")
TOLERANCES = {"geometry_small_px": 4, "geometry_large_threshold_px": 130, "geometry_large_fraction": .03, "font_size_px": .5, "font_weight": 0, "color_delta_e_76": 3, "alpha": 0, "corner_radius_px": 1, "border_width_px": 0}


def number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def expected_cases(spec: dict, matrix: str) -> dict[str, dict]:
    languages = spec["languages"] if matrix == "full" else ["zh-CN"]
    themes = spec["themes"] if matrix == "full" else ["light"]
    sizes = spec["sizes"] if matrix == "full" else [[1440, 900]]
    scenes = spec["scenes"] if matrix == "full" else SMOKE_SCENES
    return {f"{lang}-{theme}-{width}x{height}-{scene}": {"width": width, "height": height, "scale": 1}
            for lang in languages for theme in themes for width, height in sizes for scene in scenes}


def rgba(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 4 and all(number(v) and 0 <= v <= 255 for v in value)


def lab(color: list[float]) -> tuple[float, float, float]:
    """sRGB/D65 -> CIE Lab; alpha is compared independently, never discarded."""
    rgb = [v / 255 for v in color[:3]]
    r, g, b = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
    x = (r * .4124564 + g * .3575761 + b * .1804375) / .95047
    y = r * .2126729 + g * .7151522 + b * .0721750
    z = (r * .0193339 + g * .1191920 + b * .9503041) / 1.08883
    f = lambda v: v ** (1 / 3) if v > 216 / 24389 else (24389 / 27 * v + 16) / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(left: list[float], right: list[float]) -> float:
    return math.dist(lab(left), lab(right))


def geometry_tolerance(size: float) -> float:
    return size * .03 if size > 130 else 4


def validate_capture(data: Any, client: str, scene: str, viewport: dict) -> list[dict]:
    errors = []
    def error(message, element=None):
        if element is not None and not isinstance(element, (str, int)): element = repr(element)
        errors.append({"client": client, "element": element, "reason": message})
    if not isinstance(data, dict):
        error("Capture is not a JSON object")
        return errors
    for key, expected in (("schema_version", 1), ("client", client), ("scene_id", scene), ("viewport", viewport)):
        if data.get(key) != expected:
            error(f"Invalid {key}: expected {expected!r}, got {data.get(key)!r}")
    for field in ("errors", "extraction_errors"):
        supplied_errors = data.get(field, [])
        if not isinstance(supplied_errors, list):
            error(field + " must be an array")
        else:
            for supplied in supplied_errors: error("Extractor reported: " + str(supplied))
    elements = data.get("elements")
    if not isinstance(elements, list) or not elements:
        error("Capture has no element array or an empty element array")
        return errors
    coverage = data.get("coverage")
    if not isinstance(coverage, dict):
        error("Missing extraction coverage")
    else:
        if coverage.get("emitted_elements") != len(elements):
            error("coverage.emitted_elements does not match the element array")
        if not isinstance(coverage.get("raw_nodes"), int) or coverage["raw_nodes"] < 1:
            error("coverage.raw_nodes must record the inspected source tree")
        if not isinstance(coverage.get("unmeasured"), list):
            error("coverage.unmeasured must explicitly list measurement gaps")
        else:
            for gap in coverage["unmeasured"]: error("Unmeasured: " + str(gap))
    ids = set()
    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            error("Element must be an object", index)
            continue
        eid = element.get("id", index)
        if not isinstance(eid, str) or not eid or eid in ids:
            error("Element id must be a unique non-empty string", index)
        elif isinstance(eid, str):
            ids.add(eid)
        for key in ("parent", "region", "order", "kind", "text", "name", "bounds", "style", "state", "layout", "icon", "evidence"):
            if key not in element:
                error("Missing field: " + key, eid)
        if not isinstance(element.get("region"), str) or element.get("region") not in REGIONS:
            error("Unrecognized region", eid)
        if not isinstance(element.get("kind"), str) or element.get("kind") not in KINDS:
            error("Unrecognized kind", eid)
        if not isinstance(element.get("order"), int) or isinstance(element.get("order"), bool) or element["order"] < 0:
            error("order must be a nonnegative integer", eid)
        for field in ("text", "name"):
            if not isinstance(element.get(field), str):
                error(field + " must preserve an exact string", eid)
        bounds = element.get("bounds", {})
        if not isinstance(bounds, dict) or not all(number(bounds.get(k)) for k in ("x", "y", "width", "height")):
            error("Invalid or unmeasured bounds", eid)
        elif bounds["width"] < 0 or bounds["height"] < 0 or bounds["width"] == bounds["height"] == 0:
            error("Visible bounds cannot be empty or negative", eid)
        if "visible_bounds" in element:
            visible = element["visible_bounds"]
            if not isinstance(visible, dict) or not all(number(visible.get(k)) for k in ("x", "y", "width", "height")):
                error("Invalid visible bounds", eid)
        for group, fields in (("style", STYLE_FIELDS), ("state", STATE_FIELDS), ("layout", LAYOUT_FIELDS)):
            values = element.get(group)
            if not isinstance(values, dict):
                error("Missing measurement object: " + group, eid)
                continue
            for field in fields:
                if field not in values:
                    error("Missing measurement: " + group + "." + field, eid)
                    continue
                value = values[field]
                if group == "style" and value is not None and not (rgba(value) if field in ("foreground", "background", "border_color") else number(value)):
                    error("Invalid measurement: " + group + "." + field, eid)
                if group == "state" and value is not None and not isinstance(value, bool):
                    error("State must be boolean or null: " + field, eid)
                if group == "layout" and value is not None and not (isinstance(value, int) and not isinstance(value, bool) and value >= 0 if field == "line_count" else isinstance(value, str)):
                    error("Invalid layout: " + field, eid)
                if group == "layout" and field == "wrap" and value is not None and value not in ("none", "word", "character"):
                    error("Unknown wrapping measurement", eid)
                if group == "layout" and field == "truncation" and value is not None and value not in ("none", "clip", "ellipsis"):
                    error("Unknown truncation measurement", eid)
        # Explicit null means inapplicable, not an invitation to skip a missing
        # font, input state, or visual measurement on both clients.
        style = element.get("style") if isinstance(element.get("style"), dict) else {}
        state = element.get("state") if isinstance(element.get("state"), dict) else {}
        layout = element.get("layout") if isinstance(element.get("layout"), dict) else {}
        if element.get("text") or element.get("kind") in ("text", "code"):
            for key in ("font_size", "font_weight", "foreground"):
                if style.get(key) is None:
                    error("Visible text has no measured " + key, eid)
            for key in LAYOUT_FIELDS:
                if layout.get(key) is None:
                    error("Visible text has no measured layout." + key, eid)
            if layout.get("line_count") == 0:
                error("Visible text cannot have zero measured lines", eid)
        if isinstance(element.get("kind"), str) and element.get("kind") in INTERACTIVE and state.get("enabled") is None:
            error("Interactive element has no enabled state", eid)
        for kind, key in (("input", "focused"), ("tab", "selected"), ("toggle", "checked"), ("checkbox", "checked")):
            if element.get("kind") == kind and state.get(key) is None:
                error(kind + " has no " + key + " state", eid)
        if element.get("kind") == "icon" and not element.get("icon"):
            error("Icon has no independently extracted glyph/vector identity", eid)
        icon = element.get("icon")
        if icon is not None and (not isinstance(icon, dict) or not isinstance(icon.get("source"), str) or not isinstance(icon.get("glyph"), str) or not icon.get("glyph")):
            error("Invalid icon identity", eid)
        if not isinstance(element.get("evidence"), dict):
            error("Evidence must be an object", eid)
    for element in elements:
        if isinstance(element, dict) and element.get("parent") is not None and (not isinstance(element.get("parent"), str) or element.get("parent") not in ids):
            error("parent does not refer to an extracted element", element.get("id"))
    for region in REGIONS:
        orders = [e.get("order") for e in elements if isinstance(e, dict) and e.get("region") == region]
        if any(not isinstance(order, int) for order in orders) or sorted(orders) != list(range(len(orders))):
            error("Reading order must be unique and contiguous from zero within region " + region)
    return errors


def identity(element: dict) -> tuple:
    return element.get("region"), element.get("kind"), element.get("text", ""), element.get("name", "")


def match_elements(reference: list[dict], native: list[dict]) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """One-to-one semantic pairing without ids or screenshot geometry.

    Exact nonempty text/name anchors are paired in reading order. Remaining
    same-region elements are sequence aligned, with text similarity only a
    pairing cost (never a passing tolerance). Unique moved anchors are retained
    so that region errors are reported instead of being hidden as unmatched.
    """
    refs, natives = set(range(len(reference))), set(range(len(native)))
    pairs = []
    def ordered(indices, elements):
        return sorted(indices, key=lambda i: (elements[i].get("order", i), i))
    rkeys, nkeys = defaultdict(list), defaultdict(list)
    for i, element in enumerate(reference):
        if element.get("text") or element.get("name"):
            rkeys[identity(element)].append(i)
    for i, element in enumerate(native):
        if element.get("text") or element.get("name"):
            nkeys[identity(element)].append(i)
    for key in sorted(rkeys.keys() & nkeys.keys()):
        for r, n in zip(ordered(rkeys[key], reference), ordered(nkeys[key], native)):
            pairs.append((r, n)); refs.remove(r); natives.remove(n)
    # Unique same-name/text anchors that moved to another region.
    moved_r, moved_n = defaultdict(list), defaultdict(list)
    for r in refs:
        if reference[r].get("text") or reference[r].get("name"):
            moved_r[identity(reference[r])[1:]].append(r)
    for n in natives:
        if native[n].get("text") or native[n].get("name"):
            moved_n[identity(native[n])[1:]].append(n)
    for key in sorted(moved_r.keys() & moved_n.keys()):
        if len(moved_r[key]) == len(moved_n[key]) == 1:
            r, n = moved_r[key][0], moved_n[key][0]
            pairs.append((r, n)); refs.remove(r); natives.remove(n)
    for region in sorted({reference[r].get("region", "") for r in refs} | {native[n].get("region", "") for n in natives}):
        ri = ordered([r for r in refs if reference[r].get("region") == region], reference)
        ni = ordered([n for n in natives if native[n].get("region") == region], native)
        # Needleman-Wunsch with deterministic tie breaking. Gap cost makes a
        # truly unrelated node remain missing/extra; no many-to-one matches.
        previous = list(range(len(ni) + 1)); choices = [bytearray(len(ni) + 1) for _ in range(len(ri) + 1)]
        for j in range(1, len(ni) + 1): choices[0][j] = 2
        for i, r in enumerate(ri, 1):
            current = [float(i)] + [0.] * len(ni); choices[i][0] = 1
            for j, n in enumerate(ni, 1):
                a, b = reference[r], native[n]
                atext, btext = a.get("text", ""), b.get("text", "")
                similarity = difflib.SequenceMatcher(None, atext, btext, autojunk=False).ratio()
                same_kind = a.get("kind") == b.get("kind")
                same_name = bool(a.get("name")) and a.get("name") == b.get("name")
                cost = (0 if same_kind else 1.25) + (0 if atext == btext else .9 * (1 - similarity))
                if not same_kind and not same_name and (not atext or not btext or similarity < .5): cost = 2.1
                options = (previous[j - 1] + cost, previous[j] + 1, current[j - 1] + 1)
                choice = min(range(3), key=lambda c: (options[c], c))
                current[j] = options[choice]; choices[i][j] = choice
            previous = current
        i, j = len(ri), len(ni)
        while i or j:
            choice = choices[i][j]
            if choice == 0:
                r, n = ri[i - 1], ni[j - 1]; pairs.append((r, n)); refs.remove(r); natives.remove(n); i -= 1; j -= 1
            elif choice == 1: i -= 1
            else: j -= 1
    return sorted(pairs), sorted(refs), sorted(natives)


def compare_elements(reference: list[dict], native: list[dict]) -> dict:
    result = {category: [] for category in CATEGORIES}
    pairs, missing, extra = match_elements(reference, native)
    description = lambda element: {key: element.get(key) for key in ("id", "kind", "text", "name", "region", "order", "bounds")}
    result["missing"] = [{"reference": reference[r]["id"], "element": description(reference[r])} for r in missing]
    result["extra"] = [{"native": native[n]["id"], "element": description(native[n])} for n in extra]
    pair_results = []
    for r, n in pairs:
        a, b = reference[r], native[n]; failures = []
        def mismatch(category, field, expected, actual, **more):
            result[category].append({"reference": a["id"], "native": b["id"], "field": field, "expected": expected, "actual": actual, **more})
            if category not in failures: failures.append(category)
        for field, category in (("kind", "kind_mismatch"), ("region", "region_mismatch"), ("text", "text_mismatch"), ("name", "text_mismatch")):
            if a.get(field) != b.get(field): mismatch(category, field, a.get(field), b.get(field))
        for axis in ("x", "y", "width", "height"):
            av, bv = a.get("bounds", {}).get(axis), b.get("bounds", {}).get(axis)
            size = a.get("bounds", {}).get("width" if axis in ("x", "width") else "height")
            tolerance = geometry_tolerance(size) if number(size) else None
            if not number(av) or not number(bv) or tolerance is None or abs(av - bv) > tolerance + 1e-8:
                mismatch("geometry_out_of_tolerance", axis, av, bv, tolerance=tolerance)
        if "visible_bounds" in a or "visible_bounds" in b:
            for axis in ("x", "y", "width", "height"):
                av = (a.get("visible_bounds") if isinstance(a.get("visible_bounds"), dict) else a.get("bounds", {})).get(axis)
                bv = (b.get("visible_bounds") if isinstance(b.get("visible_bounds"), dict) else b.get("bounds", {})).get(axis)
                size = a.get("bounds", {}).get("width" if axis in ("x", "width") else "height")
                tolerance = geometry_tolerance(size) if number(size) else None
                if not number(av) or not number(bv) or tolerance is None or abs(av - bv) > tolerance + 1e-8:
                    mismatch("geometry_out_of_tolerance", "visible_bounds." + axis, av, bv, tolerance=tolerance)
        for field in STYLE_FIELDS:
            av, bv = a.get("style", {}).get(field), b.get("style", {}).get(field)
            if av is None or bv is None:
                if av != bv: mismatch("style_out_of_tolerance", field, av, bv, reason="A measured property is missing")
                continue
            if field in ("foreground", "background", "border_color"):
                distance = delta_e(av, bv) if rgba(av) and rgba(bv) else None
                if distance is None or distance > 3 + 1e-8 or av[3] != bv[3]:
                    mismatch("style_out_of_tolerance", field, av, bv, delta_e_76=distance, tolerance=3, alpha_tolerance=0)
            else:
                tolerance = .5 if field == "font_size" else 1 if field == "corner_radius" else 0
                if not number(av) or not number(bv) or abs(av - bv) > tolerance + 1e-8:
                    mismatch("style_out_of_tolerance", field, av, bv, tolerance=tolerance)
        for group, fields, category in (("state", STATE_FIELDS, "state_mismatch"), ("layout", LAYOUT_FIELDS, "layout_mismatch")):
            for field in fields:
                av, bv = a.get(group, {}).get(field), b.get(group, {}).get(field)
                if av != bv: mismatch(category, field, av, bv)
        if a.get("icon") != b.get("icon"):
            mismatch("icon_mismatch", "icon", a.get("icon"), b.get("icon"), reason="No person-approved icon equivalence is configured")
        pair_results.append({"reference": a["id"], "native": b["id"], "status": "mismatch" if failures else "match", "categories": failures})
    # Reading order is relative to counterparts, not the number of internal
    # template wrappers. Missing/extra objects are already separate failures.
    indexed_pairs = {(p["reference"], p["native"]): p for p in pair_results}
    for region in REGIONS:
        same_region = [(r, n) for r, n in pairs if reference[r].get("region") == native[n].get("region") == region]
        ordered = sorted(same_region, key=lambda pair: (reference[pair[0]].get("order", pair[0]), pair[0]))
        native_order = sorted(same_region, key=lambda pair: (native[pair[1]].get("order", pair[1]), pair[1]))
        positions = {pair: i for i, pair in enumerate(native_order)}
        for rank, (r, n) in enumerate(ordered):
            if positions[(r, n)] != rank:
                rid, nid = reference[r]["id"], native[n]["id"]
                result["order_mismatch"].append({"reference": rid, "native": nid, "field": "reading_order", "expected": rank, "actual": positions[(r, n)], "region": region})
                paired = indexed_pairs[(rid, nid)]; paired["status"] = "mismatch"; paired["categories"].append("order_mismatch")
    result["pairs"] = pair_results
    result["reference_elements"] = len(reference); result["native_elements"] = len(native)
    result["paired_elements"] = len(pairs)
    result["matched_elements"] = sum(p["status"] == "match" for p in pair_results)
    return result


def read_capture(path: Path, client: str, scene: str, viewport: dict) -> tuple[dict, list[dict]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return {}, [{"client": client, "reason": f"Cannot read {path.name}: {exc}"}]
    errors = validate_capture(data, client, scene, viewport)
    return data if isinstance(data, dict) else {}, errors


def valid_elements(data: dict) -> list[dict]:
    # Malformed elements are recorded by validation, never silently accepted.
    elements = data.get("elements")
    return [e for e in elements if isinstance(e, dict) and isinstance(e.get("id"), str)
            and isinstance(e.get("style"), dict) and isinstance(e.get("state"), dict) and isinstance(e.get("layout"), dict)
            and isinstance(e.get("bounds"), dict) and isinstance(e.get("order"), int)
            and isinstance(e.get("text"), str) and isinstance(e.get("name"), str)
            and isinstance(e.get("region"), str) and e.get("region") in REGIONS
            and isinstance(e.get("kind"), str) and e.get("kind") in KINDS] if isinstance(elements, list) else []


def raw_element_count(data: dict) -> int:
    elements = data.get("elements")
    return len(elements) if isinstance(elements, list) else 0


def copy_raw_evidence(source: Path, output: Path, scene: str, client: str, data: dict) -> list[dict]:
    """Keep the actual trees beside their JSON's relative basename references."""
    errors = []
    destination = output / "elements" / client
    destination.mkdir(parents=True, exist_ok=True)
    suffixes = (".uia.json", ".xaml.json", ".dom.json", ".ax.json", ".input-text.json")
    # Also keep a sidecar whose producer did not add raw_evidence metadata yet.
    # Only this case's files are included in this case's copy operation.
    copied = set()
    for candidate in sorted(source.glob(scene + ".*.json")):
        if candidate.name.endswith(suffixes):
            shutil.copyfile(candidate, destination / candidate.name)
            copied.add(candidate.name)
    references = data.get("raw_evidence", {})
    if not isinstance(references, dict):
        return [{"client": client, "reason": "raw_evidence must map source kinds to local sidecar basenames"}]
    for kind, filename in references.items():
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.startswith(scene + "."):
            errors.append({"client": client, "reason": f"Invalid raw_evidence reference {kind}: {filename!r}"})
        elif filename not in copied:
            errors.append({"client": client, "reason": f"Raw evidence sidecar unavailable in report: {filename}"})
    return errors


def image_info(path: Path, client: str, viewport: dict) -> list[dict]:
    from PIL import Image
    try:
        with Image.open(path) as image:
            image.load()
            if image.size != (viewport["width"], viewport["height"]):
                return [{"client": client, "reason": f"Screenshot dimensions {image.size} do not match {viewport}"}]
    except (OSError, ValueError) as exc:
        return [{"client": client, "reason": f"Cannot read screenshot {path.name}: {exc}"}]
    return []


def heat_map(reference: Path, native: Path, output: Path) -> dict:
    from PIL import Image, ImageChops, ImageOps, ImageStat
    with Image.open(reference) as ref, Image.open(native) as app:
        ref, app = ref.convert("RGB"), app.convert("RGB")
        if ref.size != app.size:
            return {"available": False, "reason": "Different screenshot dimensions"}
        difference = ImageChops.difference(ref, app)
        channels = difference.split()
        maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
        changed = ref.width * ref.height - maximum.histogram()[0]
        # No denoising, alignment, mask or perceptual threshold: preserve every
        # changed pixel, including antialiasing, as an independent second signal.
        ImageOps.colorize(maximum, (0, 0, 0), (255, 255, 0), mid=(255, 0, 0)).save(output)
        return {"available": True, "file": output.name, "changed_pixels": changed, "total_pixels": ref.width * ref.height,
                "changed_fraction": changed / (ref.width * ref.height), "mean_absolute_channel_difference": sum(ImageStat.Stat(difference).mean) / 3,
                "gate": False, "description": "Unaligned absolute RGB pixel difference; black identical, red/yellow increasing difference"}


def outlines(elements: list[dict], statuses: dict, viewport: dict, image: str | None, label: str) -> str:
    colors = {"match": "#159447", "missing": "#e02020", "mismatch": "#ef8b00", "extra": "#9b38dd"}
    shapes = []
    for element in elements:
        box = element.get("bounds", {})
        if not all(number(box.get(k)) for k in ("x", "y", "width", "height")): continue
        status = statuses.get(element["id"], "mismatch")
        title = html.escape(f"{status}: {element['id']} | {element.get('kind')} | {element.get('text', '')} | {element.get('name', '')}")
        shapes.append(f'<rect x="{box["x"]}" y="{box["y"]}" width="{box["width"]}" height="{box["height"]}" fill="none" stroke="{colors[status]}" stroke-width="1.5" vector-effect="non-scaling-stroke"><title>{title}</title></rect>')
    width, height = viewport["width"], viewport["height"]
    background = f'<image href="{html.escape(image, quote=True)}" width="{width}" height="{height}"/>' if image else f'<rect width="{width}" height="{height}" fill="#eee"/><text x="20" y="40" fill="red">MISSING SCREENSHOT</text>'
    return f'<figure><figcaption>{html.escape(label)}</figcaption><svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">{background}<g class="outlines">{"".join(shapes)}</g></svg></figure>'


PAGE_STYLE = """body{font:14px system-ui,sans-serif;margin:24px;color:#252525;background:#fafafa}a{color:#245ba8}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px;text-align:left}figure{margin:0;min-width:0}figcaption{padding:8px 0;font-weight:600}.screens{display:grid;grid-template-columns:1fr 1fr;gap:16px}svg{width:100%;background:white}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eee;padding:12px}img.heat{max-width:100%}.good{color:#167d37}.bad{color:#b11313}details{margin:12px 0}.legend span{margin-right:18px}body.hide-outlines .outlines{display:none}summary{cursor:pointer}li{margin:6px 0}"""


def write_scene_html(output: Path, scene: str, viewport: dict, captures: dict, results: dict, images: dict) -> None:
    chunks = [f'<!doctype html><meta charset="utf-8"><title>{html.escape(scene)}</title><style>{PAGE_STYLE}</style>',
              f'<p><a href="index.html">All scenes</a> · <a href="summary.json">Summary JSON</a> · <a href="{html.escape(scene, quote=True)}.parity.json">This scene: complete machine report</a></p><h1>{html.escape(scene)}</h1>',
              '<p class="legend"><span style="color:#159447">Green: match</span><span style="color:#e02020">Red: missing</span><span style="color:#ef8b00">Orange: mismatch</span><span style="color:#9b38dd">Purple: extra</span></p>',
              '<label><input type="checkbox" checked onchange="document.body.classList.toggle(\'hide-outlines\', !this.checked)"> Show every extracted element</label>']
    ref_elements = valid_elements(captures["reference"])
    base_chunks = list(chunks)
    combined_chunks = list(chunks)
    for platform in PLATFORMS:
        chunks = list(base_chunks)
        result = results[platform]; native_elements = valid_elements(captures[platform])
        ref_status = {p["reference"]: p["status"] for p in result["pairs"]}
        native_status = {p["native"]: p["status"] for p in result["pairs"]}
        ref_status.update({item["reference"]: "missing" for item in result["missing"]})
        native_status.update({item["native"]: "extra" for item in result["extra"]})
        chunks += [f'<h2>{platform}</h2><p class="{"good" if result["passed"] else "bad"}">{"PASS" if result["passed"] else "FAIL"} · {result["matched_elements"]}/{result["reference_elements"]} elements match</p>',
                   f'<p>Native extraction: {result["raw_native_elements"]} raw elements; {result["valid_native_elements"]} structurally comparable; {result["invalid_native_elements"]} unusable. Reference: {result["raw_reference_elements"]} raw; {result["valid_reference_elements"]} structurally comparable; {result["invalid_reference_elements"]} unusable. Structural comparability does not imply valid measurements or parity.</p>', '<div class="screens">',
                   outlines(ref_elements, ref_status, viewport, images.get("reference"), "Reference"),
                   outlines(native_elements, native_status, viewport, images.get(platform), platform), '</div>']
        for category in CATEGORIES:
            entries = result[category]
            if entries:
                chunks.append(f'<details open><summary>{category}: {len(entries)}</summary><pre>{html.escape(json.dumps(entries, ensure_ascii=False, indent=2))}</pre></details>')
        pixel = result.get("pixel_difference", {})
        if pixel.get("available"):
            chunks.append(f'<details><summary>Pixel heat map — {pixel["changed_pixels"]} changed pixels ({pixel["changed_fraction"]:.2%})</summary><p>No masks, alignment or noise threshold; not a substitute for element checks.</p><img class="heat" src="{html.escape(pixel["file"], quote=True)}"></details>')
        else:
            chunks.append('<p class="bad">Pixel heat map unavailable: ' + html.escape(pixel.get("reason", "Missing captures")) + '</p>')
        (output / f"{scene}-{platform}.html").write_text("\n".join(chunks), encoding="utf-8")
        combined_chunks.extend(chunks[len(base_chunks):])
    (output / f"{scene}.html").write_text("\n".join(combined_chunks), encoding="utf-8")


def run(source: Path, output: Path, matrix: str = "full", spec: dict | None = None) -> dict:
    if spec is None:
        spec = json.loads((Path(__file__).parent / "scenes.json").read_text(encoding="utf-8"))
    cases = expected_cases(spec, matrix)
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "commit": os.environ.get("GITHUB_SHA"), "matrix": matrix, "expected_scenes_per_platform": len(cases),
              "tolerances": TOLERANCES, "exceptions": [], "approved_icon_mappings": [], "unexpected_captures": [], "scenes": [], "summary": {}, "passed": False}
    report["element_count_definitions"] = {
        "raw_reference_elements / raw_native_elements": "Number of entries in the extractor's original elements array, before structural filtering.",
        "valid_reference_elements / valid_native_elements": "Structurally comparable entries accepted by the matcher; missing or invalid measurements can still fail extraction validation.",
        "invalid_reference_elements / invalid_native_elements": "Original entries excluded from pairing because their structure is unreadable; retained in the copied source JSON and reported as extraction errors.",
        "reference_elements / native_elements": "Compatibility aliases for valid_reference_elements / valid_native_elements.",
        "matched_elements": "Paired elements with no mismatch or applicable extraction error."
    }
    for client in CLIENTS:
        present = {p.name.removesuffix(".elements.json") for p in (source / client).glob("*.elements.json")}
        present |= {p.stem for p in (source / client).glob("*.png")}
        for unexpected in sorted(present - cases.keys()):
            report["unexpected_captures"].append({"client": client, "scene_id": unexpected})
    for platform in PLATFORMS:
        report["summary"][platform] = {"scenes_expected": len(cases), "scenes_checked": 0, "scenes_passed": 0,
            "reference_elements": 0, "native_elements": 0, "paired_elements": 0, "matched_elements": 0,
            "raw_reference_elements": 0, "valid_reference_elements": 0, "invalid_reference_elements": 0,
            "raw_native_elements": 0, "valid_native_elements": 0, "invalid_native_elements": 0,
            "counts": {category: 0 for category in CATEGORIES}}
    index_rows = []
    for scene, viewport in sorted(cases.items()):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", scene):
            raise ValueError("Unsafe scene filename in specification: " + scene)
        captures, errors, images = {}, {}, {}
        for client in CLIENTS:
            capture_path = source / client / f"{scene}.elements.json"
            captures[client], errors[client] = read_capture(capture_path, client, scene, viewport)
            image_path = source / client / f"{scene}.png"
            errors[client] += image_info(image_path, client, viewport)
            if image_path.is_file():
                image_copy = output / "images" / client / image_path.name
                image_copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(image_path, image_copy)
                images[client] = image_copy.relative_to(output).as_posix()
            if capture_path.is_file():
                tree_copy = output / "elements" / client / capture_path.name
                tree_copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(capture_path, tree_copy)
            errors[client] += copy_raw_evidence(source / client, output, scene, client, captures[client])
        results = {}
        for platform in PLATFORMS:
            result = compare_elements(valid_elements(captures["reference"]), valid_elements(captures[platform]))
            result["raw_reference_elements"] = raw_element_count(captures["reference"])
            result["valid_reference_elements"] = result["reference_elements"]
            result["invalid_reference_elements"] = result["raw_reference_elements"] - result["valid_reference_elements"]
            result["raw_native_elements"] = raw_element_count(captures[platform])
            result["valid_native_elements"] = result["native_elements"]
            result["invalid_native_elements"] = result["raw_native_elements"] - result["valid_native_elements"]
            result["extraction_errors"] = errors["reference"] + errors[platform]
            bad_reference = {e.get("element") for e in errors["reference"]}
            bad_native = {e.get("element") for e in errors[platform]}
            for pair in result["pairs"]:
                if None in bad_reference or None in bad_native or pair["reference"] in bad_reference or pair["native"] in bad_native:
                    pair["status"] = "mismatch"
                    pair["categories"].append("extraction_errors")
            result["matched_elements"] = sum(pair["status"] == "match" for pair in result["pairs"])
            if not errors["reference"] and not errors[platform]: report["summary"][platform]["scenes_checked"] += 1
            result["counts"] = {category: len(result[category]) for category in CATEGORIES}
            result["passed"] = not any(result["counts"].values())
            if result["passed"]: report["summary"][platform]["scenes_passed"] += 1
            for key in ("reference_elements", "native_elements", "paired_elements", "matched_elements",
                        "raw_reference_elements", "valid_reference_elements", "invalid_reference_elements",
                        "raw_native_elements", "valid_native_elements", "invalid_native_elements"):
                report["summary"][platform][key] += result[key]
            for category in CATEGORIES: report["summary"][platform]["counts"][category] += result["counts"][category]
            if "reference" in images and platform in images:
                try:
                    result["pixel_difference"] = heat_map(source / "reference" / f"{scene}.png", source / platform / f"{scene}.png", output / f"{scene}-{platform}-heat.png")
                except (OSError, ValueError) as exc:
                    result["pixel_difference"] = {"available": False, "reason": str(exc)}
            else: result["pixel_difference"] = {"available": False, "reason": "Missing screenshot"}
            results[platform] = result
        scene_report = {"scene_id": scene, "viewport": viewport, "platforms": results}
        report["scenes"].append(scene_report)
        (output / f"{scene}.parity.json").write_text(json.dumps(scene_report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        write_scene_html(output, scene, viewport, captures, results, images)
        index_rows.append('<tr><td><a href="' + scene + '.html">' + html.escape(scene) + '</a></td>' + ''.join(f'<td class="{"good" if results[p]["passed"] else "bad"}">{"PASS" if results[p]["passed"] else "FAIL"}: {sum(results[p]["counts"].values())} findings; {results[p]["matched_elements"]}/{results[p]["reference_elements"]} matched</td>' for p in PLATFORMS) + '</tr>')
    report["passed"] = not report["unexpected_captures"] and all(s["scenes_passed"] == len(cases) and len(cases) > 0 for s in report["summary"].values())
    report["reported_scenes"] = len(report["scenes"])
    report["expected_platform_comparisons"] = len(cases) * len(PLATFORMS)
    report["reported_platform_comparisons"] = sum(len(scene["platforms"]) for scene in report["scenes"])
    (output / "parity-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    summary_report = {key: value for key, value in report.items() if key != "scenes"}
    (output / "summary.json").write_text(json.dumps(summary_report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    (output / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Relic element parity</title><style>' + PAGE_STYLE + '</style><h1>Relic element parity — ' + ("PASS" if report["passed"] else "FAIL") + '</h1><p><a href="summary.json">Lightweight summary JSON</a> · <a href="parity-report.json">Full machine-readable report (large)</a></p><p>Each scene page links its complete scene JSON. The summary and per-scene files preserve the same values as the full report; they do not change the gate.</p><p>Every requested scene and both platforms are required. No exceptions or icon equivalents are approved. Extraction errors fail the gate. Green requires kind, exact text/name, region/order, geometry, style, layout, icon and state to match.</p><pre>' + html.escape(json.dumps(report["summary"], ensure_ascii=False, indent=2)) + '</pre><h2>Exceptions</h2><p>None. No native-control differences are exempted.</p><table><thead><tr><th>Scene</th><th>Windows</th><th>macOS</th></tr></thead><tbody>' + '\n'.join(index_rows) + '</tbody></table>', encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--matrix", choices=("full", "smoke"), default="full")
    args = parser.parse_args()
    report = run(args.source, args.output, args.matrix)
    print(json.dumps({"passed": report["passed"], "summary": report["summary"], "exceptions": report["exceptions"], "unexpected_captures": report["unexpected_captures"]}, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
