"""Strict, auditable element parity for the real reference and native captures.

This consumes independently extracted trees; it never manufactures native
elements from the reference. Unknown measurements, incomplete matrices and
missing captures fail the gate. Pixel differences are a second signal only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import difflib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
from typing import Any

from image_paint import ImagePaintError, validate_vector_paint
from outline_paint import outline_measurement, compare_outlines
from line_breaks import BREAK_FIELDS, break_strategy_issues
from font_weights import compare_font_weights, font_weight_issues
from paint_patterns import (MeasurementError, background_pattern_kind,
                            captured_pattern, compare_paint_patterns,
                            pattern_measurement_issue)


PLATFORMS = ("windows", "macos")
CLIENTS = ("reference",) + PLATFORMS
REGIONS = {"window", "header", "sidebar", "conversation", "composer", "right-pane", "dialog", "menu"}
KINDS = {"region", "text", "button", "icon-button", "input", "toggle", "checkbox", "tab", "menu-item", "dropdown", "chip", "badge", "avatar", "state-dot", "card", "list-row", "divider", "code", "chart-node", "chart-edge", "icon", "image", "link", "resize-handle", "scrollbar", "scrollbar-thumb"}
SCROLL_KINDS = {"scrollbar", "scrollbar-thumb"}
STYLE_FIELDS = ("font_size", "font_weight", "foreground", "background", "border_color", "border_width", "corner_radius")
PAINT_FIELDS = ("border_widths", "border_colors", "border_styles", "corner_radii", "opacity", "background_image", "shadow")
STROKE_FIELDS = ("stroke_dash", "stroke_dash_offset", "stroke_linecap", "stroke_linejoin")
STATE_FIELDS = ("enabled", "selected", "checked", "expanded", "focused", "hovered", "unread")
LAYOUT_FIELDS = (*BREAK_FIELDS, "truncation", "line_count")
INTERACTIVE = {"button", "icon-button", "input", "toggle", "checkbox", "tab", "menu-item", "dropdown", "link", "resize-handle"} | SCROLL_KINDS
CATEGORIES = ("missing", "extra", "text_mismatch", "geometry_out_of_tolerance", "style_out_of_tolerance", "state_mismatch", "kind_mismatch", "region_mismatch", "order_mismatch", "layout_mismatch", "icon_mismatch", "extraction_errors")
SMOKE_SCENES = ("group", "private", "overview", "settings-appearance", "new-org", "copies", "chart", "menu-file", "file-code", "live-tool-output", "live-typing", "member-card-rename", "member-card-model", "member-card-avatar-hover", "message-hover", "message-copy-toast", "new-org-textarea-resized", "panel-resize-hover", "panel-resized")
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


def vector(value: Any, size: int, *, nonnegative: bool = False) -> bool:
    return isinstance(value, list) and len(value) == size and all(number(v) and (not nonnegative or v >= 0) for v in value)


def has_text(element: dict) -> bool:
    # A code/card container can own paint while its child text is emitted once.
    return bool(element.get("text")) or element.get("kind") == "text"


def has_font_glyph(element: dict) -> bool:
    icon = element.get("icon")
    return (element.get("kind") == "icon" and isinstance(icon, dict)
            and icon.get("source") not in ("svg", "image", "path", "geometry", "vector-image-v1"))


def paint_issues(style: dict) -> list[str]:
    """Canonical paint measurements cannot disappear behind scalar maxima."""
    issues = []
    for field in ("background", "border_width", "corner_radius") + PAINT_FIELDS:
        if field not in style or style[field] is None:
            issues.append("Missing measured paint: " + field)
    for field in ("border_width", "corner_radius"):
        if style.get(field) is not None and (not number(style[field]) or style[field] < 0):
            issues.append("Invalid nonnegative paint: " + field)
    for field in ("border_widths", "corner_radii"):
        if style.get(field) is not None and not vector(style[field], 4, nonnegative=True):
            issues.append("Expected four measured nonnegative values: " + field)
    if style.get("border_colors") is not None and not (isinstance(style["border_colors"], list) and len(style["border_colors"]) == 4 and all(rgba(c) for c in style["border_colors"])):
        issues.append("Expected four measured RGBA border colors in TRBL order")
    if style.get("border_styles") is not None and not (isinstance(style["border_styles"], list) and len(style["border_styles"]) == 4 and all(s in ("none", "hidden", "solid", "dashed", "dotted", "double", "groove", "ridge", "inset", "outset") for s in style["border_styles"])):
        issues.append("Expected four measured border styles in TRBL order")
    if number(style.get("stroke_width")) and style["stroke_width"] > 0:
        dash = style.get("stroke_dash")
        if not isinstance(dash, list) or not all(number(value) and value >= 0 for value in dash):
            issues.append("Visible stroke has no measured nonnegative window-pixel stroke_dash array")
        if not number(style.get("stroke_dash_offset")):
            issues.append("Visible stroke has no measured window-pixel stroke_dash_offset")
        if style.get("stroke_linecap") not in ("butt", "round", "square"):
            issues.append("Visible stroke has no measured stroke_linecap")
        if style.get("stroke_linejoin") not in ("miter", "round", "bevel"):
            issues.append("Visible stroke has no measured stroke_linejoin")
    for scalar, field in (("border_width", "border_widths"), ("corner_radius", "corner_radii")):
        if number(style.get(scalar)) and vector(style.get(field), 4) and abs(style[scalar] - max(style[field])) > 1e-8:
            issues.append(scalar + " must agree with the maximum of " + field)
    if style.get("opacity") is not None and (not number(style["opacity"]) or not 0 <= style["opacity"] <= 1):
        issues.append("opacity must be the measured cumulative opacity in [0,1]")
    shadows = style.get("shadow")
    if shadows is not None:
        if not isinstance(shadows, list):
            issues.append("shadow must be a canonical array, not an unparsed CSS string")
        else:
            for index, shadow in enumerate(shadows):
                if not isinstance(shadow, dict) or not isinstance(shadow.get("inset"), bool) or not rgba(shadow.get("color")) or not all(number(shadow.get(k)) for k in ("offset_x", "offset_y", "blur_radius", "spread_radius")) or shadow.get("blur_radius", -1) < 0:
                    issues.append("Invalid measured shadow at index " + str(index))
    background = style.get("background_image")
    if background is not None and background != "none":
        if isinstance(background, dict) and background.get("kind") == "image-brush":
            # Placement and pixels belong to this independently measured brush,
            # not to a made-up CSS size/repeat/gradient descriptor. The complete
            # source binding and raster contract is checked by validate_capture.
            if not isinstance(background.get("source_id"), str) or not background["source_id"]:
                issues.append("ImageBrush background has no actual source id")
        elif not isinstance(background, dict) or background.get("kind") not in ("image", "linear-gradient", "radial-gradient", "conic-gradient"):
            issues.append("background_image must be none or a canonical measured paint descriptor")
        else:
            for field in ("position", "size"):
                if not vector(background.get(field), 2, nonnegative=field == "size"):
                    issues.append("background_image has no measured " + field)
            repeat = background.get("repeat")
            if not isinstance(repeat, list) or len(repeat) != 2 or any(r not in ("repeat", "no-repeat", "round", "space") for r in repeat):
                issues.append("background_image has no measured repeat axes")
            kind = background["kind"]
            if kind == "image":
                digest = background.get("content_sha256")
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    issues.append("background image needs an actual content digest, not a path label")
            else:
                stops = background.get("stops")
                if not isinstance(stops, list) or len(stops) < 2 or any(not isinstance(stop, dict) or not number(stop.get("position")) or not rgba(stop.get("color")) for stop in stops):
                    issues.append("gradient has no complete measured stops")
                if not isinstance(background.get("repeating"), bool):
                    issues.append("gradient repeating state is unknown")
                if kind in ("linear-gradient", "conic-gradient") and not number(background.get("angle")):
                    issues.append("gradient angle is unknown")
                if kind in ("radial-gradient", "conic-gradient") and not vector(background.get("center"), 2):
                    issues.append("gradient center is unknown")
                if kind == "radial-gradient" and not vector(background.get("radius"), 2, nonnegative=True):
                    issues.append("radial gradient radii are unknown")
    return issues


def text_lines(element: dict) -> list[dict] | None:
    """Union actual fragments sharing a visual line, not template layout boxes."""
    evidence = element.get("evidence")
    boxes = evidence.get("text_bounds") if isinstance(evidence, dict) else None
    if not isinstance(boxes, list) or not boxes or any(not isinstance(b, dict) or not all(number(b.get(k)) for k in ("x", "y", "width", "height")) or b["width"] < 0 or b["height"] <= 0 for b in boxes):
        return None
    lines = []
    for box in sorted(boxes, key=lambda b: (b["y"], b["x"])):
        top, bottom = box["y"], box["y"] + box["height"]
        overlaps = [line for line in lines if min(bottom, line["y"] + line["height"]) > max(top, line["y"])]
        if not overlaps:
            lines.append(dict(box)); continue
        line = overlaps[0]
        left = min(line["x"], box["x"]); right = max(line["x"] + line["width"], box["x"] + box["width"])
        top = min(line["y"], top); bottom = max(line["y"] + line["height"], bottom)
        line.update(x=left, y=top, width=right - left, height=bottom - top)
    return sorted(lines, key=lambda b: (b["y"], b["x"]))


def rendered_fonts(element: dict) -> dict[str, set[str] | None] | None:
    """Actual render-run families; declared fallback lists are not evidence.

    PostScript names identify actual faces independently of localized family
    spellings when both APIs provide every face. Incomplete face evidence
    still requires exact measured family identity, never an alias table.
    Glyph counters and custom-font loading flags describe provider accounting,
    not a visible style property, so remain in the copied raw capture only.
    """
    style = element.get("style")
    fonts = style.get("rendered_fonts") if isinstance(style, dict) else None
    if not isinstance(fonts, list) or not fonts: return None
    families = {}
    for font in fonts:
        if not isinstance(font, dict) or not isinstance(font.get("family_name"), str) or not font["family_name"]:
            return None
        family, postscript = font["family_name"], font.get("postscript_name")
        if family not in families: families[family] = set()
        if not isinstance(postscript, str) or not postscript:
            families[family] = None
        elif families[family] is not None:
            families[family].add(postscript)
    return families


def icon_identity(icon: Any) -> tuple[Any, str | None]:
    """Compare the actual SVG tree, not JS/.NET JSON serialization choices.

    Attribute/path values and child order remain exact. No geometric rewriting,
    icon equivalence mapping, or tolerance is introduced; raw glyphs survive in
    the extraction file and every mismatch record.
    """
    if isinstance(icon, dict) and icon.get("source") == "vector-image-v1":
        try:
            validate_vector_paint(icon)
        except ImagePaintError as exc:
            return None, "Invalid vector-image-v1 identity: " + str(exc)
        # Dict key order is serialization detail; ordered layers, actual path
        # strings and every paint number remain exact, with no icon mapping.
        return icon, None
    if not isinstance(icon, dict) or icon.get("source") != "svg":
        return icon, None
    glyph = icon.get("glyph")
    try:
        tree = json.loads(glyph) if isinstance(glyph, str) else None
    except (ValueError, TypeError) as exc:
        return None, "SVG glyph is not a parseable canonical JSON tree: " + str(exc)
    def valid_tree(node):
        return (isinstance(node, dict) and isinstance(node.get("tag"), str)
                and isinstance(node.get("attributes"), dict)
                and isinstance(node.get("children"), list)
                and all(valid_tree(child) for child in node["children"]))
    if not valid_tree(tree):
        return None, "SVG glyph must preserve tag, attributes and ordered children"
    return dict(icon, glyph=tree), None


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
    source_ids = Counter(e["id"] for e in elements if isinstance(e, dict) and isinstance(e.get("id"), str))
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
            for gap in coverage["unmeasured"]:
                # Reference names its actual source `element`; XAML uses `id`.
                # Retain attribution only for one uniquely emitted element.
                # Unknown raw nodes or ambiguous/global gaps remain global
                # failures; no projection ownership or parent id is guessed.
                reported = [gap[key] for key in ("element", "id") if key in gap] if isinstance(gap, dict) else []
                target = (reported[0] if reported and all(isinstance(value, str) and value == reported[0] for value in reported)
                          and source_ids[reported[0]] == 1 else None)
                error("Unmeasured: " + str(gap), target)
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
                if group == "layout" and field == "truncation" and value is not None and value not in ("none", "clip", "ellipsis"):
                    error("Unknown truncation measurement", eid)
        # Explicit null means inapplicable, not an invitation to skip a missing
        # font, input state, or visual measurement on both clients.
        style = element.get("style") if isinstance(element.get("style"), dict) else {}
        state = element.get("state") if isinstance(element.get("state"), dict) else {}
        layout = element.get("layout") if isinstance(element.get("layout"), dict) else {}
        for issue in break_strategy_issues(element): error(issue, eid)
        for issue in paint_issues(style): error(issue, eid)
        _, outline_issues = outline_measurement(element)
        for issue in outline_issues: error("Unmeasured outline: " + issue, eid)
        # A typed bitmap descriptor is not proof of measured paint. Unknown
        # placement/occlusion retains one concrete failure instead of inventing
        # independent errors for every absent subfield. Null descriptors already
        # retain the older Missing measured paint diagnostic above.
        if (isinstance(style.get("background_image"), dict)
                and background_pattern_kind(element) == "image-brush"):
            try:
                issue = pattern_measurement_issue(captured_pattern(element))
            except MeasurementError as failure:
                issue = str(failure)
            if issue is not None: error("Unmeasured background pattern: " + issue, eid)
        if has_text(element):
            for key in ("font_size", "font_weight", "foreground"):
                if style.get(key) is None:
                    error("Visible text has no measured " + key, eid)
            for key in LAYOUT_FIELDS:
                if layout.get(key) is None:
                    error("Visible text has no measured layout." + key, eid)
            if layout.get("line_count") == 0:
                error("Visible text cannot have zero measured lines", eid)
            lines = text_lines(element)
            if lines is None:
                error("Visible text has no actual text-line rectangles in evidence.text_bounds", eid)
            elif number(layout.get("line_count")) and len(lines) != layout["line_count"]:
                error("Measured text-line rectangles disagree with layout.line_count", eid)
            if rendered_fonts(element) is None:
                error("Visible text has no measured actual font families in style.rendered_fonts; a configured fallback list is not proof", eid)
        for issue in font_weight_issues(element):
            error(issue["field"] + ": " + issue["reason"], eid)
        if (has_text(element) or element.get("kind") in ("icon", "chart-edge")) and style.get("foreground") is None:
            error("Visible foreground paint has no measured color", eid)
        if has_font_glyph(element):
            for key in ("font_size", "font_weight"):
                if style.get(key) is None: error("Font glyph has no measured " + key, eid)
        if isinstance(element.get("kind"), str) and element.get("kind") in INTERACTIVE and state.get("enabled") is None:
            error("Interactive element has no enabled state", eid)
        if isinstance(element.get("kind"), str) and element.get("kind") in SCROLL_KINDS:
            if state.get("orientation") not in ("horizontal", "vertical"):
                error("Scrollbar has no measured orientation", eid)
            position = state.get("scroll_position")
            if not number(position) or not 0 <= position <= 1:
                error("Scrollbar has no measured normalized scroll_position", eid)
        for kind, key in (("input", "focused"), ("tab", "selected"), ("toggle", "checked"), ("checkbox", "checked")):
            if element.get("kind") == kind and state.get(key) is None:
                error(kind + " has no " + key + " state", eid)
        if element.get("kind") in ("checkbox", "toggle") and not isinstance(state.get("indeterminate"), bool):
            error("Checkable element has no measured indeterminate state", eid)
        if element.get("kind") == "chart-node" and not isinstance(state.get("current"), bool):
            error("Chart node has no measured current-organization state", eid)
        if element.get("kind") in ("icon", "chart-edge", "image") and not element.get("icon"):
            error("Visible glyph/vector/image has no independently extracted identity", eid)
        icon = element.get("icon")
        vector_image = isinstance(icon, dict) and icon.get("source") == "vector-image-v1"
        if icon is not None and not vector_image and (not isinstance(icon, dict) or not isinstance(icon.get("source"), str) or not isinstance(icon.get("glyph"), str) or not icon.get("glyph")):
            error("Invalid icon identity", eid)
        _, icon_error = icon_identity(icon)
        if icon_error: error(icon_error, eid)
        if not isinstance(element.get("evidence"), dict):
            error("Evidence must be an object", eid)
    for element in elements:
        if isinstance(element, dict) and element.get("parent") is not None and (not isinstance(element.get("parent"), str) or element.get("parent") not in ids):
            error("parent does not refer to an extracted element", element.get("id"))
    nodes = {e["id"]: e for e in elements if isinstance(e, dict) and isinstance(e.get("id"), str)}
    for element in nodes.values():
        if element.get("kind") != "icon-button" or element.get("icon"): continue
        found = False
        for candidate in nodes.values():
            if candidate.get("kind") not in ("icon", "image") or not candidate.get("icon"): continue
            parent, visited = candidate.get("parent"), set()
            while isinstance(parent, str) and parent in nodes and parent not in visited:
                if parent == element["id"]: found = True; break
                visited.add(parent); parent = nodes[parent].get("parent")
            if found: break
        if not found: error("Icon button has no measured owned icon element", element["id"])
    for region in REGIONS:
        orders = [e.get("order") for e in elements if isinstance(e, dict) and e.get("region") == region]
        if any(not isinstance(order, int) for order in orders) or sorted(orders) != list(range(len(orders))):
            error("Reading order must be unique and contiguous from zero within region " + region)
    return errors


def identity(element: dict) -> tuple:
    return element.get("region"), element.get("kind"), element.get("text", ""), element.get("name", "")


def measured_icon_anchor(element: dict) -> Any:
    """Only decoded content can anchor a pair; URI/font/path labels cannot.

    Freeze JSON structure without changing its values: dict key order is
    irrelevant, list order is retained, and numeric equality is Python's
    existing canonical comparison (1 and 1.0 compare equally).
    """
    icon = element.get("icon")
    if not isinstance(icon, dict) or icon.get("source") not in ("svg", "vector-image-v1"):
        return None
    decoded, error = icon_identity(icon)
    if error or element.get("region") not in REGIONS:
        return None
    def freeze(value):
        if isinstance(value, dict):
            if not all(isinstance(key, str) for key in value): raise ValueError("non-JSON key")
            return ("object", tuple((key, freeze(value[key])) for key in sorted(value)))
        if isinstance(value, list): return ("array", tuple(freeze(item) for item in value))
        if isinstance(value, bool):
            # v1 already rejects bool numerics. Legacy SVG tree validation is
            # less strict; such values cannot become content anchors (True == 1
            # in Python), even though their raw evidence remains available.
            raise ValueError("boolean is not measured SVG/vector numeric content")
        if value is None or isinstance(value, str): return value
        if number(value): return value
        raise ValueError("unmeasured/nonfinite icon value")
    try:
        return element["region"], freeze(decoded)
    except (ValueError, OverflowError):
        return None


def match_elements(reference: list[dict], native: list[dict]) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """One-to-one semantic pairing without ids or screenshot geometry.

    Exact nonempty text/name anchors and decoded same-region icon content are
    paired in reading order. Unique icon content is anchored before duplicates.
    Remaining
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
    icon_r, icon_n = defaultdict(list), defaultdict(list)
    for indices, elements, groups in ((refs, reference, icon_r), (natives, native, icon_n)):
        for index in ordered(indices, elements):
            key = measured_icon_anchor(elements[index])
            if key is not None: groups[key].append(index)
    shared_icons = [key for key in icon_r if key in icon_n]
    # Group insertion follows actual reference reading order. Unique identities
    # take precedence; surplus repeated icons remain missing/extra candidates.
    shared_icons.sort(key=lambda key: (not (len(icon_r[key]) == len(icon_n[key]) == 1),
                                       reference[icon_r[key][0]].get("order", icon_r[key][0]), icon_r[key][0]))
    for key in shared_icons:
        for r, n in zip(ordered(icon_r[key], reference), ordered(icon_n[key], native)):
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
        def compare_color(field, av, bv):
            if not rgba(av) or not rgba(bv):
                mismatch("style_out_of_tolerance", field, av, bv, reason="Missing measured RGBA color"); return
            # RGB in a fully transparent brush is unobservable. This is exact
            # alpha semantics, not a tolerance/exception or pixel-color mask.
            distance = 0. if av[3] == bv[3] == 0 else delta_e(av, bv)
            if distance > 3 + 1e-8 or av[3] != bv[3]:
                mismatch("style_out_of_tolerance", field, av, bv, delta_e_76=distance, tolerance=3, alpha_tolerance=0)
        def compare_structured(field, av, bv):
            if field.endswith(".color"):
                compare_color(field, av, bv)
            elif isinstance(av, dict) and isinstance(bv, dict):
                for key in sorted(av.keys() | bv.keys()):
                    if key not in av or key not in bv:
                        mismatch("style_out_of_tolerance", field + "." + key, av.get(key), bv.get(key), reason="Missing measured paint parameter")
                    else: compare_structured(field + "." + key, av[key], bv[key])
            elif isinstance(av, list) and isinstance(bv, list):
                if len(av) != len(bv): mismatch("style_out_of_tolerance", field + ".length", len(av), len(bv))
                for index, (left, right) in enumerate(zip(av, bv)): compare_structured(field + f"[{index}]", left, right)
            elif av != bv:
                mismatch("style_out_of_tolerance", field, av, bv)
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
            # Keep the original provider value as evidence. Its meaning differs
            # between CSS requests, UIA attributes and native font descriptors.
            if field == "font_weight": continue
            if field in ("font_size", "font_weight") and not any(has_text(e) or has_font_glyph(e) for e in (a, b)): continue
            if field == "foreground" and not any(has_text(e) or e.get("kind") in ("icon", "chart-edge") for e in (a, b)): continue
            if field == "border_color" and a.get("style", {}).get("border_width") == b.get("style", {}).get("border_width") == 0: continue
            av, bv = a.get("style", {}).get(field), b.get("style", {}).get(field)
            if av is None or bv is None:
                if av != bv: mismatch("style_out_of_tolerance", field, av, bv, reason="A measured property is missing")
                continue
            if field in ("foreground", "background", "border_color"):
                compare_color(field, av, bv)
            else:
                tolerance = .5 if field == "font_size" else 1 if field == "corner_radius" else 0
                if not number(av) or not number(bv) or abs(av - bv) > tolerance + 1e-8:
                    mismatch("style_out_of_tolerance", field, av, bv, tolerance=tolerance)
        for issue in compare_font_weights(a, b):
            mismatch("style_out_of_tolerance", issue["field"], issue["expected"], issue["actual"],
                     **{key: value for key, value in issue.items() if key not in ("field", "expected", "actual")})
        for field in PAINT_FIELDS:
            av, bv = a.get("style", {}).get(field), b.get("style", {}).get(field)
            if (field == "background_image"
                    and {background_pattern_kind(a), background_pattern_kind(b)} == {"css-conic", "image-brush"}):
                records, issues = [], []
                for side, element in (("reference", a), ("native", b)):
                    try:
                        record = captured_pattern(element)
                        issue = pattern_measurement_issue(record)
                        if issue is None: records.append(record)
                        else: issues.append({"side": side, "reason": issue})
                    except MeasurementError as error:
                        issues.append({"side": side, "reason": str(error)})
                if issues:
                    mismatch("extraction_errors", field, background_pattern_kind(a), background_pattern_kind(b),
                             reason="Independent background pattern measurement is incomplete", measurements=issues)
                    if av is None or bv is None:
                        mismatch("style_out_of_tolerance", field, av, bv, reason="Required paint measurement is unknown")
                else:
                    measurement = compare_paint_patterns(*records, color_distance=delta_e)
                    if not measurement["complete"]:
                        mismatch("extraction_errors", field, background_pattern_kind(a), background_pattern_kind(b),
                                 reason="Background pattern raster comparison is incomplete", measurement=measurement)
                    elif measurement["status"] != "match":
                        mismatch("style_out_of_tolerance", field, background_pattern_kind(a), background_pattern_kind(b),
                                 measurement=measurement)
                # This replaces only bitmap-vs-gradient descriptor equality.
                # Font, flat background, borders, radius, opacity, and every
                # other element property continue through their ordinary checks.
                continue
            if av is None or bv is None:
                mismatch("style_out_of_tolerance", field, av, bv, reason="Required paint measurement is unknown")
                continue
            if field in ("border_widths", "corner_radii"):
                tolerance = 1 if field == "corner_radii" else 0
                if not vector(av, 4, nonnegative=True) or not vector(bv, 4, nonnegative=True):
                    mismatch("style_out_of_tolerance", field, av, bv, reason="Expected four measured axes")
                else:
                    for index, (left, right) in enumerate(zip(av, bv)):
                        if abs(left - right) > tolerance + 1e-8:
                            mismatch("style_out_of_tolerance", field + f"[{index}]", left, right, tolerance=tolerance)
            elif field == "border_colors":
                if not isinstance(av, list) or not isinstance(bv, list) or len(av) != 4 or len(bv) != 4:
                    mismatch("style_out_of_tolerance", field, av, bv, reason="Expected four measured edge colors")
                else:
                    aw, bw = a["style"].get("border_widths"), b["style"].get("border_widths")
                    for index, (left, right) in enumerate(zip(av, bv)):
                        if vector(aw, 4) and vector(bw, 4) and aw[index] == bw[index] == 0: continue
                        compare_color(field + f"[{index}]", left, right)
            elif field == "border_styles":
                if not isinstance(av, list) or not isinstance(bv, list) or len(av) != 4 or len(bv) != 4:
                    mismatch("style_out_of_tolerance", field, av, bv, reason="Expected four measured edge styles")
                else:
                    aw, bw = a["style"].get("border_widths"), b["style"].get("border_widths")
                    for index, (left, right) in enumerate(zip(av, bv)):
                        if vector(aw, 4) and vector(bw, 4) and aw[index] == bw[index] == 0: continue
                        if left != right: mismatch("style_out_of_tolerance", field + f"[{index}]", left, right)
            else:
                compare_structured(field, av, bv)
        for record in compare_outlines(a, b, color_distance=delta_e, geometry_tolerance=geometry_tolerance):
            mismatch(record["category"], record["field"], record["expected"], record["actual"],
                     **{key: value for key, value in record.items() if key not in ("category", "field", "expected", "actual")})
        if a.get("style", {}).get("stroke_width") is not None or b.get("style", {}).get("stroke_width") is not None:
            compare_structured("stroke_width", a.get("style", {}).get("stroke_width"), b.get("style", {}).get("stroke_width"))
        if any(number(e.get("style", {}).get("stroke_width")) and e["style"]["stroke_width"] > 0 for e in (a, b)):
            for field in STROKE_FIELDS:
                av, bv = a.get("style", {}).get(field), b.get("style", {}).get(field)
                if av is None or bv is None:
                    mismatch("style_out_of_tolerance", field, av, bv, reason="Visible stroke measurement is unknown")
                else: compare_structured(field, av, bv)
        for group, fields, category in (("state", STATE_FIELDS, "state_mismatch"), ("layout", LAYOUT_FIELDS, "layout_mismatch")):
            if group == "layout" and not has_text(a) and not has_text(b): continue
            for field in fields:
                av, bv = a.get(group, {}).get(field), b.get(group, {}).get(field)
                if group == "layout" and field in BREAK_FIELDS and (av is None or bv is None):
                    mismatch(category, field, av, bv, reason="Actual normal/emergency break strategy is unknown")
                elif av != bv: mismatch(category, field, av, bv)
        if any(e.get("kind") in ("checkbox", "toggle") for e in (a, b)):
            av, bv = a.get("state", {}).get("indeterminate"), b.get("state", {}).get("indeterminate")
            if not isinstance(av, bool) or not isinstance(bv, bool) or av != bv:
                mismatch("state_mismatch", "indeterminate", av, bv)
        if any(e.get("kind") == "chart-node" for e in (a, b)):
            av, bv = a.get("state", {}).get("current"), b.get("state", {}).get("current")
            if not isinstance(av, bool) or not isinstance(bv, bool) or av != bv:
                mismatch("state_mismatch", "current", av, bv)
        if any(e.get("kind") in SCROLL_KINDS for e in (a, b)):
            for key in ("orientation", "scroll_position"):
                av, bv = a.get("state", {}).get(key), b.get("state", {}).get(key)
                valid = (av in ("horizontal", "vertical") and bv in ("horizontal", "vertical")) if key == "orientation" else (number(av) and number(bv) and 0 <= av <= 1 and 0 <= bv <= 1)
                if not valid or av != bv:
                    mismatch("state_mismatch", key, av, bv)
        if has_text(a) or has_text(b):
            fonts_a, fonts_b = rendered_fonts(a), rendered_fonts(b)
            if fonts_a is None or fonts_b is None:
                mismatch("style_out_of_tolerance", "rendered_fonts", a.get("style", {}).get("rendered_fonts"), b.get("style", {}).get("rendered_fonts"), reason="Actual render-run font family is unmeasured")
            elif all(faces is not None for faces in (*fonts_a.values(), *fonts_b.values())):
                # CDP can expose a localized family (for example 蘋方-簡)
                # while CoreText names the same measured face PingFang SC.
                # Compare the complete actual PostScript identities, retaining
                # original family spellings in each capture. A different or
                # additional fallback face still fails exactly.
                faces_a = set().union(*fonts_a.values())
                faces_b = set().union(*fonts_b.values())
                if faces_a != faces_b:
                    mismatch("style_out_of_tolerance", "rendered_fonts.postscript_name", sorted(faces_a), sorted(faces_b))
            elif fonts_a.keys() != fonts_b.keys():
                mismatch("style_out_of_tolerance", "rendered_fonts.family_name", sorted(fonts_a), sorted(fonts_b))
            else:
                for family in sorted(fonts_a):
                    if fonts_a[family] is not None and fonts_b[family] is not None and fonts_a[family] != fonts_b[family]:
                        mismatch("style_out_of_tolerance", "rendered_fonts.postscript_name:" + family, sorted(fonts_a[family]), sorted(fonts_b[family]))
            lines_a, lines_b = text_lines(a), text_lines(b)
            if lines_a is None or lines_b is None:
                mismatch("layout_mismatch", "text_bounds", lines_a, lines_b, reason="Actual text-line geometry is unknown")
            elif len(lines_a) != len(lines_b):
                mismatch("layout_mismatch", "text_bounds.line_count", len(lines_a), len(lines_b))
            else:
                for index, (left, right) in enumerate(zip(lines_a, lines_b)):
                    for axis in ("x", "y", "width", "height"):
                        tolerance = geometry_tolerance(left["width" if axis in ("x", "width") else "height"])
                        if abs(left[axis] - right[axis]) > tolerance + 1e-8:
                            mismatch("geometry_out_of_tolerance", f"text_bounds[{index}].{axis}", left[axis], right[axis], tolerance=tolerance)
        icon_a, error_a = icon_identity(a.get("icon"))
        icon_b, error_b = icon_identity(b.get("icon"))
        if error_a or error_b or icon_a != icon_b:
            mismatch("icon_mismatch", "icon", a.get("icon"), b.get("icon"), reason=error_a or error_b or "No person-approved icon equivalence is configured")
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
            if image.convert("RGBA").getchannel("A").getextrema()[1] == 0:
                return [{"client": client, "reason": "Screenshot is fully transparent: no visible window pixels were captured; an accessibility tree cannot replace the rendered scene"}]
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
        measured = isinstance(box, dict) and all(number(box.get(k)) for k in ("x", "y", "width", "height"))
        if not measured:
            # This is a navigation aid only. A clipped CSS layout range cannot
            # establish the actual painted prefix/ellipsis glyph boundaries.
            evidence = element.get("evidence")
            box = evidence.get("clipped_range_envelope") if isinstance(evidence, dict) else None
            if not isinstance(box, dict) or not all(number(box.get(k)) for k in ("x", "y", "width", "height")): continue
        status = statuses.get(element["id"], "mismatch")
        title = html.escape(f"{status}: {element['id']} | {element.get('kind')} | {element.get('text', '')} | {element.get('name', '')}")
        if not measured: title += " | UNMEASURED: clipped layout envelope only; not actual glyph bounds"
        dash = '' if measured else ' stroke-dasharray="5 3"'
        shapes.append(f'<rect x="{box["x"]}" y="{box["y"]}" width="{box["width"]}" height="{box["height"]}" fill="none" stroke="{colors[status]}" stroke-width="1.5"{dash} vector-effect="non-scaling-stroke"><title>{title}</title></rect>')
    width, height = viewport["width"], viewport["height"]
    background = f'<image href="{html.escape(image, quote=True)}" width="{width}" height="{height}"/>' if image else f'<rect width="{width}" height="{height}" fill="#eee"/><text x="20" y="40" fill="red">MISSING SCREENSHOT</text>'
    return f'<figure><figcaption>{html.escape(label)}</figcaption><svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">{background}<g class="outlines">{"".join(shapes)}</g></svg></figure>'


PAGE_STYLE = """body{font:14px system-ui,sans-serif;margin:24px;color:#252525;background:#fafafa}a{color:#245ba8}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px;text-align:left}figure{margin:0;min-width:0}figcaption{padding:8px 0;font-weight:600}.screens{display:grid;grid-template-columns:1fr 1fr;gap:16px}svg{width:100%;background:white}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eee;padding:12px}img.heat{max-width:100%}.good{color:#167d37}.bad{color:#b11313}details{margin:12px 0}.legend span{margin-right:18px}body.hide-outlines .outlines{display:none}summary{cursor:pointer}li{margin:6px 0}"""


def write_scene_html(output: Path, scene: str, viewport: dict, captures: dict, results: dict, images: dict) -> None:
    chunks = [f'<!doctype html><meta charset="utf-8"><title>{html.escape(scene)}</title><style>{PAGE_STYLE}</style>',
              f'<p><a href="index.html">All scenes</a> · <a href="summary.json">Summary JSON</a> · <a href="{html.escape(scene, quote=True)}.parity.json">This scene: complete machine report</a></p><h1>{html.escape(scene)}</h1>',
              '<p class="legend"><span style="color:#159447">Green: match</span><span style="color:#e02020">Red: missing</span><span style="color:#ef8b00">Orange: mismatch</span><span style="color:#9b38dd">Purple: extra</span></p>',
              '<p>Dashed outlines locate a clipped layout envelope when actual glyph bounds are unknown. They are not accepted measurements; extraction and geometry failures remain in the report.</p>',
              '<label><input type="checkbox" checked onchange="document.body.classList.toggle(\'hide-outlines\', !this.checked)"> Show every extracted element</label>']
    base_chunks = list(chunks)
    combined_chunks = list(chunks)
    for platform in PLATFORMS:
        chunks = list(base_chunks)
        result = results[platform]; native_elements = valid_elements(captures[platform])
        reference_key = result["reference_artifact_client"]
        ref_elements = valid_elements(captures[reference_key])
        ref_status = {p["reference"]: p["status"] for p in result["pairs"]}
        native_status = {p["native"]: p["status"] for p in result["pairs"]}
        ref_status.update({item["reference"]: "missing" for item in result["missing"]})
        native_status.update({item["native"]: "extra" for item in result["extra"]})
        chunks += [f'<h2>{platform}</h2><p class="{"good" if result["passed"] else "bad"}">{"PASS" if result["passed"] else "FAIL"} · {result["matched_elements"]}/{result["reference_elements"]} elements match</p>',
                   f'<p>Native extraction: {result["raw_native_elements"]} raw elements; {result["valid_native_elements"]} structurally comparable; {result["invalid_native_elements"]} unusable. Reference: {result["raw_reference_elements"]} raw; {result["valid_reference_elements"]} structurally comparable; {result["invalid_reference_elements"]} unusable. Structural comparability does not imply valid measurements or parity.</p>', '<div class="screens">',
                   outlines(ref_elements, ref_status, viewport, images.get(reference_key), "Reference on " + platform),
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


def run(source: Path, output: Path, matrix: str = "full", spec: dict | None = None,
        reference_root: Path | None = None, macos_reference_root: Path | None = None) -> dict:
    if spec is None:
        spec = json.loads((Path(__file__).parent / "scenes.json").read_text(encoding="utf-8"))
    cases = expected_cases(spec, matrix)
    roots = {"reference": reference_root if reference_root is not None else source / "reference",
             "reference-macos": macos_reference_root if macos_reference_root is not None else source / "reference-macos",
             "windows": source / "windows", "macos": source / "macos"}
    references = {"windows": "reference", "macos": "reference-macos"}
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "commit": os.environ.get("GITHUB_SHA"), "matrix": matrix, "expected_scenes_per_platform": len(cases),
              "tolerances": TOLERANCES, "exceptions": [], "approved_icon_mappings": [], "unexpected_captures": [], "scenes": [], "summary": {}, "passed": False}
    report["reference_baselines"] = {platform: {"platform": platform, "source_root": str(roots[client]), "artifact_client": client}
                                     for platform, client in references.items()}
    report["font_identity_policy"] = "Actual render-run font evidence is required for visible text; size and weight are checked separately. Complete measured PostScript face sets are compared exactly when both providers expose every face, retaining original localized family spellings. Otherwise measured family sets must match exactly, with available faces compared per family. Additional fallback faces are never dropped. Glyph counters and custom-font loading flags remain evidence. Configured fallback lists and unverified UIA provider family properties cannot establish actual render-face identity."
    report["font_weight_policy"] = "Contract 1 compares actual configured requests and resolved render-face weights as separate exact quantities. Original style.font_weight values remain provider evidence, never compared across incompatible meanings. Unknown configured or resolved quantities, including missing reference wght axes, fail style and coverage even when both sides are unknown or share a PostScript name. No name-to-weight mapping or descriptor-trait estimate supplies an actual face axis."
    report["element_count_definitions"] = {
        "raw_reference_elements / raw_native_elements": "Number of entries in the extractor's original elements array, before structural filtering.",
        "valid_reference_elements / valid_native_elements": "Structurally comparable entries accepted by the matcher; missing or invalid measurements can still fail extraction validation.",
        "invalid_reference_elements / invalid_native_elements": "Original entries excluded from pairing because their structure is unreadable; retained in the copied source JSON and reported as extraction errors.",
        "reference_elements / native_elements": "Compatibility aliases for valid_reference_elements / valid_native_elements.",
        "matched_elements": "Paired elements with no mismatch or applicable extraction error."
    }
    for client, capture_root in roots.items():
        present = {p.name.removesuffix(".elements.json") for p in capture_root.glob("*.elements.json")}
        present |= {p.stem for p in capture_root.glob("*.png")}
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
        for client, capture_root in roots.items():
            capture_path = capture_root / f"{scene}.elements.json"
            producer = "reference" if client in references.values() else client
            captures[client], errors[client] = read_capture(capture_path, producer, scene, viewport)
            if producer == "reference":
                expected_platform = "macos" if client == "reference-macos" else "windows"
                environment = captures[client].get("reference_environment")
                if not isinstance(environment, dict) or environment.get("platform") != expected_platform:
                    errors[client].append({"client": client, "reason": "Missing or wrong real reference platform; expected " + expected_platform})
                elif not isinstance(environment.get("browser"), dict) or not environment["browser"].get("name") or not environment["browser"].get("version"):
                    errors[client].append({"client": client, "reason": "Reference browser identity/version is unmeasured"})
            image_path = capture_root / f"{scene}.png"
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
            errors[client] += copy_raw_evidence(capture_root, output, scene, client, captures[client])
        results = {}
        for platform in PLATFORMS:
            reference_client = references[platform]
            reference = captures[reference_client]
            result = compare_elements(valid_elements(reference), valid_elements(captures[platform]))
            result["reference_platform"] = platform
            result["reference_artifact_client"] = reference_client
            environment = reference.get("reference_environment") if isinstance(reference.get("reference_environment"), dict) else {}
            result["reference_environment"] = {
                "platform": environment.get("platform"), "browser": environment.get("browser"),
                "font_evidence": {"file": f"elements/{reference_client}/{scene}.elements.json", "field": "reference_environment.fonts"}}
            result["raw_reference_elements"] = raw_element_count(reference)
            result["valid_reference_elements"] = result["reference_elements"]
            result["invalid_reference_elements"] = result["raw_reference_elements"] - result["valid_reference_elements"]
            result["raw_native_elements"] = raw_element_count(captures[platform])
            result["valid_native_elements"] = result["native_elements"]
            result["invalid_native_elements"] = result["raw_native_elements"] - result["valid_native_elements"]
            result["extraction_errors"] += errors[reference_client] + errors[platform]
            bad_reference = {e.get("element") for e in errors[reference_client]}
            bad_native = {e.get("element") for e in errors[platform]}
            for pair in result["pairs"]:
                if None in bad_reference or None in bad_native or pair["reference"] in bad_reference or pair["native"] in bad_native:
                    pair["status"] = "mismatch"
                    pair["categories"].append("extraction_errors")
            result["matched_elements"] = sum(pair["status"] == "match" for pair in result["pairs"])
            if not result["extraction_errors"]: report["summary"][platform]["scenes_checked"] += 1
            result["counts"] = {category: len(result[category]) for category in CATEGORIES}
            result["passed"] = not any(result["counts"].values())
            if result["passed"]: report["summary"][platform]["scenes_passed"] += 1
            for key in ("reference_elements", "native_elements", "paired_elements", "matched_elements",
                        "raw_reference_elements", "valid_reference_elements", "invalid_reference_elements",
                        "raw_native_elements", "valid_native_elements", "invalid_native_elements"):
                report["summary"][platform][key] += result[key]
            for category in CATEGORIES: report["summary"][platform]["counts"][category] += result["counts"][category]
            if reference_client in images and platform in images:
                try:
                    result["pixel_difference"] = heat_map(roots[reference_client] / f"{scene}.png", source / platform / f"{scene}.png", output / f"{scene}-{platform}-heat.png")
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
    parser.add_argument("--reference-root", type=Path, help="Real Windows browser captures; defaults to SOURCE/reference")
    parser.add_argument("--macos-reference-root", type=Path, help="Real macOS browser captures; defaults to SOURCE/reference-macos; never falls back to Windows")
    args = parser.parse_args()
    report = run(args.source, args.output, args.matrix, reference_root=args.reference_root, macos_reference_root=args.macos_reference_root)
    print(json.dumps({"passed": report["passed"], "summary": report["summary"], "exceptions": report["exceptions"], "unexpected_captures": report["unexpected_captures"]}, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
