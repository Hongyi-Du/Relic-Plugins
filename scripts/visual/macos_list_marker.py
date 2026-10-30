"""Read one current native disc draw without inventing reference paint or an icon.

The returned measurements distinguish the actual CGContext user/device rectangles,
the AppKit screen conversion and the optional independently recorded content origin.
This helper is read-only. It does not fill canonical geometry or clear any unknown.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

SOURCE = "live-AppKit-AX-selectors"
OBSERVATION_SOURCE = "production native disc observation"
PROVIDER = "production NativeListMarkerView.draw / CGContext.fillEllipse"
STRUCTURE_SOURCE = "production parent environment and current NSView.subviews ancestry"
CONTENT_FRAME_SOURCE = "actual NSWindow.contentView convert(bounds,to:nil) then window.convertToScreen"
SCREEN_SPACE = "AppKit screen coordinates (bottom-left)"
RECT_KEYS = ("x", "y", "width", "height")


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


def _rect(value: Any, *, positive: bool = True) -> bool:
    return (isinstance(value, dict) and all(_number(value.get(key)) for key in RECT_KEYS)
            and value["width"] >= 0 and value["height"] >= 0
            and (not positive or value["width"] > 0 and value["height"] > 0))


def _vector(value: Any, count: int) -> bool:
    return isinstance(value, list) and len(value) == count and all(_number(n) for n in value)


def _rgba(value: Any) -> bool:
    return _vector(value, 4) and all(0 <= component <= 255 for component in value)


def _top_left(rect: dict, content: dict) -> dict | None:
    converted = {"x": rect["x"] - content["x"],
                 "y": (content["y"] + content["height"]) - (rect["y"] + rect["height"]),
                 "width": rect["width"], "height": rect["height"]}
    return converted if _rect(converted) else None


def list_marker_measurement(element: Any) -> dict:
    evidence = element.get("evidence") if isinstance(element, dict) else None
    applicable = isinstance(evidence, dict) and ("native_list_marker" in evidence or
                  evidence.get("source") == SOURCE and evidence.get("class") == "NativeListMarkerView")
    result = {"applicable": applicable, "draw_binding_valid": False, "coordinate_binding_valid": False,
              "presentation_identity_proven": False, "measurements": None,
              "viewport_ellipse": None,
              "viewport_ellipse_quantity": "actual AppKit converted ellipse rectangle in content-top-left coordinates; not sampled ink, exact clip coverage, or a canonical icon",
              "issues": [], "binding_issues": [], "coordinate_issues": []}
    if not applicable:
        return result
    issues, binding_issues = result["issues"], result["binding_issues"]

    def require(condition: bool, reason: str, *, binding: bool = True) -> None:
        if not condition:
            issues.append(reason)
            if binding:
                binding_issues.append(reason)

    require(evidence.get("source") == SOURCE and evidence.get("class") == "NativeListMarkerView",
            "Unexpected native list-marker owner/provider")
    require(element.get("kind") == "icon" and evidence.get("kind") == "icon" and evidence.get("role") == "AXImage",
            "Native list marker must retain its actual AX image and icon kind", binding=False)
    require(_string(element.get("id")) and evidence.get("id") == element["id"]
            and evidence.get("raw_node_id") == element["id"], "Marker is not bound to the same retained raw node")
    observation = evidence.get("native_list_marker")
    result["raw"] = {"native_list_marker": deepcopy(observation), "object_identity": evidence.get("object_identity"),
                     "canonical_icon": deepcopy(element.get("icon")), "state": deepcopy(element.get("state")),
                     "raw_state": deepcopy(evidence.get("state"))}
    if not isinstance(observation, dict):
        require(False, "Missing production native disc observation")
        return result
    require(observation.get("source") == OBSERVATION_SOURCE, "Unexpected list-marker observation source")
    require(observation.get("errors") == [], "Production list-marker observation reports missing/failed evidence")
    draw = observation.get("current_draw")
    if not isinstance(draw, dict):
        require(False, "No current mounted marker draw; a last draw or AX bullet cannot replace it")
        return result
    require(draw.get("provider") == PROVIDER and draw.get("draw_returned") is True,
            "No returned production CGContext.fillEllipse callback")
    require(draw.get("presentation_identity_proven") is False,
            "Marker draw must retain its unproven presentation identity")
    require(draw.get("symbol") == "disc", "Unsupported actual native list-symbol operation")
    require(_integer(draw.get("revision")) and _integer(draw.get("sequence"), 1),
            "Missing/invalid actual marker revision or draw sequence")
    require(_string(draw.get("view_identity")) and draw["view_identity"] == evidence.get("object_identity"),
            "Current marker draw differs from the actual AX object identity")
    structure = observation.get("native_structure")
    if not isinstance(structure, dict):
        require(False, "Missing current mounted marker NSView identity")
    else:
        require(structure.get("source") == STRUCTURE_SOURCE, "Unexpected native marker structure source")
        for key in ("view_identity", "window_identity"):
            require(_string(structure.get(key)) and structure[key] == draw.get(key),
                    "Marker draw " + key + " differs from its currently mounted view")
        path = structure.get("native_subview_path")
        require(isinstance(path, list) and all(_integer(index) for index in path),
                "Marker has no measured mounted NSView ancestry")
    for key in ("local_bounds", "local_ellipse", "device_ellipse"):
        require(_rect(draw.get(key)), "Missing/invalid actual marker " + key)
    require(_rect(draw.get("context_clip"), positive=False), "Missing/invalid actual CGContext clip envelope")
    require(_vector(draw.get("context_ctm"), 6), "Missing/invalid actual CGContext transform")
    require(_rgba(draw.get("foreground")), "Missing/invalid actual marker fill color")
    require(_number(draw.get("font_size")) and draw["font_size"] > 0 and _string(draw.get("font_postscript_name")),
            "Missing actual marker primary font identity/size")
    require(_number(draw.get("native_ascent")) and draw["native_ascent"] > 0
            and _number(draw.get("native_descent")) and draw["native_descent"] <= 0,
            "Missing/invalid actual primary font ascent/descent")
    require(_integer(draw.get("layout_ascent")) and _integer(draw.get("layout_descent")),
            "Missing actual integer layout ascent/descent")
    # These are retained actual inputs/results; do not regenerate the ellipse from the font metrics.
    for key in ("screen_bounds", "screen_ellipse"):
        require(_rect(observation.get(key)), "Missing/invalid actual marker " + key)

    alternative = draw.get("alternative_text")
    require(_string(alternative) and element.get("name") == alternative and evidence.get("name") == alternative
            and evidence.get("native_ax_label") == alternative,
            "Canonical marker name does not preserve the actual generated AX alternative", binding=False)
    require(element.get("text") == "" and evidence.get("text") == "",
            "Generated AX alternative is not painted text; retain its name without exporting a font glyph", binding=False)
    style = element.get("style") if isinstance(element.get("style"), dict) else {}
    raw_style = evidence.get("style") if isinstance(evidence.get("style"), dict) else {}
    require(style.get("foreground") == draw.get("foreground") == raw_style.get("color"),
            "Canonical marker fill color differs from its actual draw receipt", binding=False)
    result["draw_binding_valid"] = not binding_issues
    if result["draw_binding_valid"]:
        result["measurements"] = {
            "source": PROVIDER, "primitive": "ellipse", "operation": "fill",
            "quantity": "Actual returned fillEllipse rectangle and supplied color; not final pixel coverage",
            "local_ellipse": deepcopy(draw["local_ellipse"]), "device_ellipse": deepcopy(draw["device_ellipse"]),
            "screen_ellipse": deepcopy(observation["screen_ellipse"]),
            "screen_rectangle_quantity": "actual NSView.convert then NSWindow.convertToScreen rectangle; not a sampled ink mask",
            "owner_local_bounds": deepcopy(draw["local_bounds"]), "owner_screen_bounds": deepcopy(observation["screen_bounds"]),
            "foreground": deepcopy(draw["foreground"]), "context_ctm": deepcopy(draw["context_ctm"]),
            "context_clip_envelope": deepcopy(draw["context_clip"]),
            "font_metrics": {key: deepcopy(draw[key]) for key in ("font_size", "font_postscript_name", "native_ascent",
                                                                  "native_descent", "layout_ascent", "layout_descent")},
            "visible_bounds": None, "reference_ellipse": None,
        }

    # Same independent content-origin contract already used by the native field editor.
    # No origin is reconstructed from the known AX allocation or a reference rectangle.
    basis = observation.get("content_screen_frame")
    coordinate_issues = result["coordinate_issues"]
    if not (isinstance(basis, dict) and basis.get("source") == CONTENT_FRAME_SOURCE
            and basis.get("coordinate_space") == SCREEN_SPACE
            and _string(draw.get("window_identity")) and basis.get("window_identity") == draw["window_identity"]
            and _rect(basis.get("bounds"))):
        coordinate_issues.append("Missing actual current content_screen_frame source/window/coordinate basis; screen ellipse is not a viewport ellipse")
    elif not result["draw_binding_valid"]:
        coordinate_issues.append("Marker screen conversion has no valid current draw/owner binding")
    else:
        owner = _top_left(observation["screen_bounds"], basis["bounds"])
        ellipse = _top_left(observation["screen_ellipse"], basis["bounds"])
        if owner is None or ellipse is None:
            coordinate_issues.append("Actual content-origin conversion produced nonfinite/invalid rectangles")
        elif evidence.get("rect") != owner:
            coordinate_issues.append("Actual screen-owner conversion differs from the retained AX owner rectangle")
        else:
            result["coordinate_binding_valid"] = True
            result["viewport_ellipse"] = ellipse
    result["issues"].extend(coordinate_issues)
    return result


def list_marker_issues(element: Any) -> list[str]:
    return list_marker_measurement(element)["issues"]
