"""Validate the final AppKit icon renderer's actual CoreGraphics draw receipt.

This checks one production draw and its live view binding, not presentation,
compositor equivalence, outline absence, or final PNG contribution. It never
supplies canonical values from the reference, an icon name, or a previous draw.
"""
from __future__ import annotations

import json
import math
from typing import Any


SOURCE = "live-CoreGraphics-icon-draw"
PROVIDER = "production PaintView.draw / CGContext.strokePath"
STRUCTURE_SOURCE = "production parent environment and current NSView.subviews ancestry"
POINT_COUNTS = {0: 1, 1: 1, 2: 2, 3: 3, 4: 0}


def _number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _integer(value: Any, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _rect(value: Any, *, positive: bool = False) -> bool:
    return (isinstance(value, dict) and all(_number(value.get(key)) for key in ("x", "y", "width", "height"))
            and value["width"] >= 0 and value["height"] >= 0
            and (not positive or value["width"] > 0 and value["height"] > 0))


def _rgba(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 4 and all(_number(x) and 0 <= x <= 255 for x in value)


def icon_draw_measurement(element: Any) -> dict:
    """Return a bounded audit; only the exact producer source is applicable.

    PaintView.currentDraw independently checks its current revision, view and
    window objects, local bounds and effective color. The exporter preserves
    that result, the previous receipt and a separate mounted-view identity.
    We cross-check those receipts and the canonical values without promoting
    the producer's explicit false presentation claim.
    """
    evidence = element.get("evidence") if isinstance(element, dict) else None
    applicable = isinstance(evidence, dict) and evidence.get("source") == SOURCE
    result = {"applicable": applicable, "draw_binding_valid": False,
              "presentation_identity_proven": False, "measurements": None, "issues": []}
    if not applicable:
        return result
    issues = result["issues"]

    def require(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(reason)

    projection = evidence.get("projection")
    if not isinstance(projection, dict):
        issues.append("Missing production icon draw projection")
        return result
    require(element.get("kind") == "icon" and evidence.get("kind") == "icon", "Draw receipt is not attached to an icon")
    require(_string(element.get("id")) and evidence.get("id") == element["id"]
            and evidence.get("raw_node_id") == element["id"], "Canonical icon is not bound to the same raw node")
    require(projection.get("source") == "production CoreGraphics icon draw"
            and projection.get("renderer") == "final native PaintView.draw", "Unexpected icon production renderer")
    require(projection.get("presentation_identity_proven") is False,
            "Icon projection must preserve its unproven presentation identity")
    require(projection.get("draw_binding_valid") is True, "No current live production icon draw binding")
    draw = projection.get("current_draw")
    result["raw"] = {"projection": projection, "native_structure": evidence.get("native_structure")}
    if not isinstance(draw, dict):
        issues.append("Current icon draw is absent; last_draw cannot replace it")
        return result
    require(draw.get("provider") == PROVIDER and draw.get("draw_returned") is True,
            "No returned production CGContext.strokePath callback")
    require(draw.get("presentation_identity_proven") is False,
            "Draw receipt must preserve its unproven presentation identity")
    require(_integer(draw.get("revision"), 1) and _integer(draw.get("sequence"), 1),
            "Draw revision or sequence is missing or invalid")
    require(isinstance(projection.get("last_draw"), dict) and projection["last_draw"] == draw,
            "Current draw does not agree with the retained last draw")

    structure = evidence.get("native_structure")
    if not isinstance(structure, dict):
        issues.append("Missing current mounted NSView identity")
    else:
        require(structure.get("source") == STRUCTURE_SOURCE, "Unexpected native view identity source")
        for key in ("view_identity", "window_identity"):
            require(_string(structure.get(key)) and structure[key] == draw.get(key),
                    "Draw " + key + " differs from the current native view")
        path = structure.get("native_subview_path")
        require(isinstance(path, list) and all(_integer(index) for index in path),
                "Current icon has no measured mounted NSView ancestry")
        require("parent_identifier" in structure and "owner_accessibility_identifier" in projection
                and structure["parent_identifier"] == projection["owner_accessibility_identifier"],
                "Draw owner identifier differs from the actual native structure")

    require(_string(projection.get("resource")) and projection["resource"] == draw.get("resource"),
            "Current resource differs from the drawn resource")
    source_path = projection.get("path")
    require(_string(source_path) and source_path == draw.get("source_path"),
            "Current SVG path differs from the source used by the draw")
    require(projection.get("viewBox") == "0 0 24 24", "Unknown production icon viewBox")
    local, bounds = draw.get("local_bounds"), element.get("bounds")
    require(_rect(local, positive=True), "No finite positive drawn local bounds")
    require(_rect(bounds, positive=True) and evidence.get("rect") == bounds,
            "Canonical icon bounds differ from the actual native view rectangle")
    if _rect(local, positive=True) and _rect(bounds, positive=True):
        require(local["width"] == bounds["width"] and local["height"] == bounds["height"],
                "Draw and native view sizes differ; no transformed-size equivalence is assumed")
    require(_rect(draw.get("rendered_path_bounds")), "No finite actual CGPath bounds")
    commands = draw.get("rendered_path_commands")
    commands_valid = isinstance(commands, list) and bool(commands)
    if commands_valid:
        for index, command in enumerate(commands):
            if not isinstance(command, dict) or not _integer(command.get("type")) or command["type"] not in POINT_COUNTS:
                commands_valid = False
                break
            points = command.get("points")
            if (not isinstance(points, list) or len(points) != POINT_COUNTS[command["type"]]
                    or not all(isinstance(p, list) and len(p) == 2 and all(_number(v) for v in p) for p in points)
                    or index == 0 and command["type"] != 0):
                commands_valid = False
                break
    require(commands_valid, "Missing, nonfinite or malformed actual CGPath command sequence")

    icon = element.get("icon")
    require(isinstance(icon, dict) and evidence.get("icon") == icon, "Canonical icon differs from its raw icon identity")
    tree = None
    try:
        if isinstance(icon, dict) and icon.get("source") == "svg" and isinstance(icon.get("glyph"), str):
            tree = json.loads(icon["glyph"])
    except (ValueError, TypeError):
        pass
    if not isinstance(tree, dict) or tree.get("tag") != "svg" or not isinstance(tree.get("attributes"), dict):
        issues.append("No parsed canonical SVG identity for the actual icon draw")
    else:
        attributes, children = tree["attributes"], tree.get("children")
        require(set(tree) == {"tag", "attributes", "children"}
                and set(attributes) == {"width", "height", "viewBox"}
                and attributes.get("viewBox") == projection.get("viewBox"), "Canonical SVG root differs from the drawn resource contract")
        require(children == [{"tag": "path", "attributes": {"d": source_path}, "children": []}],
                "Canonical SVG path differs from the actual draw source")
        for key in ("width", "height"):
            try:
                dimension = float(attributes[key]) if isinstance(attributes.get(key), str) else None
            except (TypeError, ValueError, OverflowError):
                dimension = None
            require(_number(dimension) and dimension > 0 and _rect(local, positive=True) and dimension == local[key],
                    "Canonical SVG " + key + " differs from the actual drawn local bounds")

    style = element.get("style") if isinstance(element.get("style"), dict) else {}
    raw_style = evidence.get("style") if isinstance(evidence.get("style"), dict) else {}
    foreground = draw.get("foreground")
    require(_rgba(foreground) and style.get("foreground") == foreground and raw_style.get("color") == foreground,
            "Canonical foreground differs from the actual draw's sRGB color")
    width = draw.get("stroke_width")
    require(_number(width) and width > 0, "No finite positive actual stroke width")
    for canonical, raw in (("stroke_width", "stroke_width"), ("stroke_dash", "stroke_dash"),
                           ("stroke_dash_offset", "stroke_dash_offset"), ("stroke_linecap", "line_cap"),
                           ("stroke_linejoin", "line_join")):
        require(raw in draw and canonical in style and canonical in raw_style
                and style[canonical] == draw[raw] and raw_style[canonical] == draw[raw],
                "Canonical " + canonical + " differs from the actual stroke operation")
    require(draw.get("stroke_dash") == [] and _number(draw.get("stroke_dash_offset")) and draw["stroke_dash_offset"] == 0
            and draw.get("line_cap") == "round" and draw.get("line_join") == "round"
            and draw.get("should_antialias") is True, "Unknown production icon stroke operation")
    if not issues:
        result["draw_binding_valid"] = True
        result["measurements"] = {key: draw[key] for key in (
            "resource", "source_path", "local_bounds", "rendered_path_bounds", "rendered_path_commands",
            "foreground", "stroke_width", "stroke_dash", "stroke_dash_offset", "line_cap", "line_join")}
    return result


def icon_draw_issues(element: Any) -> list[str]:
    return icon_draw_measurement(element)["issues"]
