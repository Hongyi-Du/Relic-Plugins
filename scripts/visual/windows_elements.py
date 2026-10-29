"""Project independently measured UIA + XAML evidence; never read reference data.

Raw records and projection ownership are retained for audit. Incomplete paint,
visibility or typography measurements fail coverage instead of being guessed.
"""
import copy
import json
import math
import re
from collections import defaultdict
from pathlib import Path

from PIL import Image


CONTROL_KINDS = {
    "Button": "button", "AppBarButton": "button", "RepeatButton": "button",
    "HyperlinkButton": "link", "TextBox": "input", "PasswordBox": "input",
    "CheckBox": "checkbox", "RadioButton": "checkbox", "ToggleSwitch": "toggle",
    "ToggleButton": "toggle", "ComboBox": "dropdown", "SelectorBarItem": "tab",
    "TabViewItem": "tab", "MenuBarItem": "menu-item", "MenuFlyoutItem": "menu-item",
    "MenuFlyoutSubItem": "menu-item", "ToggleMenuFlyoutItem": "menu-item",
    "ListViewItem": "list-row", "TreeViewItem": "list-row", "Expander": "card",
    "ContentDialog": "card", "MenuFlyoutSeparator": "divider",
    "ChartNodeButton": "chart-node", "ChartSurface": "region",
}
PAINT_CONTROL_KINDS = {"OverviewChipView": "chip", "OverviewBadgeView": "badge", "PersonPicture": "avatar"}
TEXT_TYPES = {"TextBlock", "RichTextBlock", "Run"}
ICON_TYPES = {"FontIcon", "SymbolIcon", "PathIcon", "BitmapIcon", "AnimatedIcon", "ReferenceVectorIcon"}
STATE_KEYS = ("enabled", "selected", "current", "checked", "indeterminate", "expanded", "focused", "hovered", "unread")
UIA_KINDS = {"Button": {"button", "icon-button", "chart-node"}, "Text": {"text"}, "Edit": {"input"}, "CheckBox": {"checkbox"},
             "RadioButton": {"checkbox"}, "ComboBox": {"dropdown"}, "TabItem": {"tab"}, "MenuItem": {"menu-item"},
             "ListItem": {"list-row"}, "TreeItem": {"list-row"}, "Image": {"image", "avatar", "icon"},
             "Hyperlink": {"link"}, "Separator": {"divider"}, "Group": {"region", "card"}, "Pane": {"region", "card"},
             "Custom": {"region", "card"}, "Window": {"region"}}
INTERACTIVE_KINDS = {"button", "icon-button", "chart-node", "link", "input", "checkbox", "toggle", "dropdown", "tab", "menu-item", "list-row"}
ACTION_PATTERNS = ("InvokePattern", "TogglePattern", "SelectionItemPattern", "ExpandCollapsePattern", "ValuePattern", "RangeValuePattern")
PAINT_ONLY_TYPES = TEXT_TYPES | ICON_TYPES | set(PAINT_CONTROL_KINDS) | {"Image", "PersonPicture", "Border", "Rectangle", "Ellipse", "Line", "Path", "Polyline", "Grid", "StackPanel", "Canvas", "ContentPresenter"}


def positive(box):
    return bool(isinstance(box, dict) and all(
        isinstance(box.get(k), (int, float)) and not isinstance(box[k], bool)
        and math.isfinite(box[k]) for k in ("x", "y", "width", "height"))
        and box["width"] > 0 and box["height"] > 0)


def distance(a, b):
    return sum(abs(a.get(k, 0) - b.get(k, 0)) for k in ("x", "y", "width", "height"))


def painted(color):
    return isinstance(color, list) and len(color) == 4 and all(finite(c) for c in color) and color[3] > 0


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def intersection(a, b):
    if not positive(a) or not positive(b):
        return None
    x, y = max(a["x"], b["x"]), max(a["y"], b["y"])
    right = min(a["x"] + a["width"], b["x"] + b["width"])
    bottom = min(a["y"] + a["height"], b["y"] + b["height"])
    return {"x": x, "y": y, "width": right - x, "height": bottom - y} if right > x and bottom > y else None


def subtract_rect(a, b):
    cross = intersection(a, b)
    if not cross:
        return [a]
    parts = [
        {"x": a["x"], "y": a["y"], "width": a["width"], "height": cross["y"] - a["y"]},
        {"x": a["x"], "y": cross["y"] + cross["height"], "width": a["width"],
         "height": a["y"] + a["height"] - cross["y"] - cross["height"]},
        {"x": a["x"], "y": cross["y"], "width": cross["x"] - a["x"], "height": cross["height"]},
        {"x": cross["x"] + cross["width"], "y": cross["y"],
         "width": a["x"] + a["width"] - cross["x"] - cross["width"], "height": cross["height"]},
    ]
    return [part for part in parts if positive(part)]


def corners(box):
    return [(box["x"], box["y"]), (box["x"] + box["width"], box["y"]),
            (box["x"] + box["width"], box["y"] + box["height"]), (box["x"], box["y"] + box["height"])]


def rounded_contains_point(mask, x, y):
    b, radii, clip = mask["bounds"], mask["radii"], mask["clip"]
    if not (b["x"] <= x <= b["x"] + b["width"] and b["y"] <= y <= b["y"] + b["height"] and
            clip["x"] <= x <= clip["x"] + clip["width"] and clip["y"] <= y <= clip["y"] + clip["height"]):
        return False
    for index, (cx, cy) in enumerate(corners(b)):
        radius = radii[index]
        rx, ry = radius["x"], radius["y"]
        if rx <= 0 or ry <= 0:
            continue
        center_x = cx + rx if index in (0, 3) else cx - rx
        center_y = cy + ry if index in (0, 1) else cy - ry
        in_corner_x = x < center_x if index in (0, 3) else x > center_x
        in_corner_y = y < center_y if index in (0, 1) else y > center_y
        if in_corner_x and in_corner_y:
            return ((x - center_x) / rx) ** 2 + ((y - center_y) / ry) ** 2 <= 1
    return True


def rounded_contains_rect(mask, box):
    # The rounded rectangle and its rectangular clip are convex; containing
    # all four corners proves the entire rectangle is covered.
    return all(rounded_contains_point(mask, x, y) for x, y in corners(box))


def transformed_box_edges(node, widths):
    """Transform actual local edges/corners, including 90-degree turns."""
    matrix = node.get("transform") or {}
    straight = abs(matrix["m12"]) < 1e-8 and abs(matrix["m21"]) < 1e-8
    swapped = abs(matrix["m11"]) < 1e-8 and abs(matrix["m22"]) < 1e-8
    if not straight and not swapped:
        return None
    sx = math.hypot(matrix["m11"], matrix["m12"])
    sy = math.hypot(matrix["m21"], matrix["m22"])
    if sx == 0 or sy == 0:
        return None
    if node.get("paint_kind") == "rectangle":
        local_radii = [{"x": 0, "y": 0} for _ in range(4)]
    elif node["type"] == "Rectangle":
        radius = node.get("shape_corner_radius") or {}
        if not all(finite(radius.get(k)) and radius[k] >= 0 for k in ("x", "y")):
            return None
        local_radii = [dict(radius) for _ in range(4)]
    else:
        actual = node.get("style", {}).get("corner_radii")
        if not isinstance(actual, list) or len(actual) != 4 or not all(finite(r) and r >= 0 for r in actual):
            return None
        local_radii = [{"x": r, "y": r} for r in actual]
    screen_corner = {(False, False): 0, (True, False): 1, (True, True): 2, (False, True): 3}
    mapping = []
    for x, y in ((0, 0), (1, 0), (1, 1), (0, 1)):
        right = (x == 1) == (matrix["m11"] > 0) if straight else (y == 1) == (matrix["m21"] > 0)
        bottom = (y == 1) == (matrix["m22"] > 0) if straight else (x == 1) == (matrix["m12"] > 0)
        mapping.append(screen_corner[(right, bottom)])
    radii = [None] * 4
    for index, radius in enumerate(local_radii):
        radii[mapping[index]] = {"x": radius["x"] * sx, "y": radius["y"] * sy} if straight else {
            "x": radius["y"] * sy, "y": radius["x"] * sx}
    screen_edge = {frozenset((0, 1)): 0, frozenset((1, 2)): 1, frozenset((2, 3)): 2, frozenset((3, 0)): 3}
    transformed_widths = [None] * 4
    for index, width in enumerate(widths):
        edge = screen_edge[frozenset((mapping[index], mapping[(index + 1) % 4]))]
        transformed_widths[edge] = width * (sy if index in (0, 2) else sx)
    return radii, transformed_widths


def measured_occlusion(raw, by_id):
    """Subtract only measured opaque paint, retaining exact curved masks.

    The remaining rectangles are conservative envelopes, not a pretend raster
    mask. A union of curved masks that cannot be proved covered/visible remains
    an extraction gap. No geometry tolerance is used for visibility.
    """
    gaps, masks, unknown = [], [], []
    visible = [n for n in raw if not n.get("hidden_reason") and positive(n.get("visible_bounds"))]
    ancestry = {}
    for node in raw:
        parents, current = set(), by_id.get(node.get("parent"))
        while current and current["id"] not in parents:
            parents.add(current["id"])
            current = by_id.get(current.get("parent"))
        ancestry[node["id"]] = parents

    def gap(node, reason, prop="visibility.occlusion"):
        gaps.append({"id": node["id"], "property": prop, "reason": reason})

    for node in visible:
        if not finite(node.get("paint_order")):
            gap(node, "Actual render paint order is missing")
        if not finite(node.get("opacity")):
            gap(node, "Measured accumulated UIElement opacity is missing")
        if node.get("axis_aligned_transform") is not True:
            gap(node, "Axis-aligned transform is not measured; transformed shape is unsupported")
        clip = node.get("clip")
        if clip and clip.get("kind") != "rectangle":
            gap(node, "Actual nonrectangular clip needs a measured coverage shape")
        style = node.get("style", {})
        background, border = style.get("background"), style.get("border_color")
        kind = node.get("paint_kind")
        if kind is None:
            gap(node, "Actual render primitive paint kind is missing")
            continue
        if kind in {"none", "template", "glyphs"}:
            continue
        has_stroke = painted(border) and finite(style.get("border_width")) and style["border_width"] > 0
        if not painted(background) and not has_stroke and kind not in {"image", "path"}:
            continue
        if node.get("opacity") != 1 or painted(background) and background[3] != 255:
            # Translucent surfaces do not completely occlude underlying paint.
            continue
        supported = (kind in {"rectangle", "rounded-rectangle"} and painted(background) and background[3] == 255
                     and node.get("axis_aligned_transform") is True and finite(node.get("paint_order"))
                     and (not clip or clip.get("kind") == "rectangle" and clip.get("transform_supported") is not False))
        matrix = node.get("transform") or {}
        if not supported or not all(finite(matrix.get(k)) for k in ("m11", "m12", "m21", "m22", "offset_x", "offset_y")):
            unknown.append(node)
            continue
        b = copy.deepcopy(node["bounds"])
        widths = style.get("border_widths")
        if widths is None and style.get("border_width") == 0:
            widths = [0, 0, 0, 0]
        if not isinstance(widths, list) or len(widths) != 4 or not all(finite(w) and w >= 0 for w in widths):
            unknown.append(node)
            continue
        transformed = transformed_box_edges(node, widths)
        if transformed is None:
            unknown.append(node)
            continue
        radii, widths = transformed
        if node["type"] in {"Border", "ContentPresenter"} and node.get("background_sizing") == "InnerBorderEdge" and not (has_stroke and border[3] == 255):
            top, right, bottom, left = widths
            b = {"x": b["x"] + left, "y": b["y"] + top, "width": b["width"] - left - right, "height": b["height"] - top - bottom}
            radii = [{"x": max(0, r["x"] - (left if i in (0, 3) else right)),
                      "y": max(0, r["y"] - (top if i in (0, 1) else bottom))} for i, r in enumerate(radii)]
        if not positive(b):
            continue
        sums = [(radii[0]["x"] + radii[1]["x"], b["width"]), (radii[3]["x"] + radii[2]["x"], b["width"]),
                (radii[0]["y"] + radii[3]["y"], b["height"]), (radii[1]["y"] + radii[2]["y"], b["height"])]
        factor = min([1] + [length / total for total, length in sums if total > 0])
        radii = [{"x": r["x"] * factor, "y": r["y"] * factor} for r in radii]
        measured_clip = intersection(b, node["visible_bounds"])
        if not measured_clip:
            continue
        masks.append({"source": node["id"], "kind": "rounded-rectangle", "bounds": b, "clip": measured_clip,
                      "radii": radii, "paint_order": node["paint_order"], "opacity": node["opacity"]})

    fragments, used_masks = {}, {}
    for node in visible:
        nid, original = node["id"], node["visible_bounds"]
        parts, applied = [copy.deepcopy(original)], []
        if not finite(node.get("paint_order")):
            fragments[nid], used_masks[nid] = parts, applied
            continue
        for mask in masks:
            other = mask["source"]
            if (mask["paint_order"] <= node["paint_order"] or other == nid or
                    other in ancestry[nid] or nid in ancestry[other] or not intersection(original, mask["clip"])):
                continue
            applied.append(mask)
            b, r = mask["bounds"], mask["radii"]
            left, right = max(r[0]["x"], r[3]["x"]), max(r[1]["x"], r[2]["x"])
            top, bottom = max(r[0]["y"], r[1]["y"]), max(r[3]["y"], r[2]["y"])
            interiors = [
                intersection(mask["clip"], {"x": b["x"] + left, "y": b["y"], "width": b["width"] - left - right, "height": b["height"]}),
                intersection(mask["clip"], {"x": b["x"], "y": b["y"] + top, "width": b["width"], "height": b["height"] - top - bottom}),
            ]
            remaining = []
            for part in parts:
                if rounded_contains_rect(mask, part):
                    continue
                split = [part]
                for interior in interiors:
                    if interior:
                        split = [piece for fragment in split for piece in subtract_rect(fragment, interior)]
                remaining.extend(fragment for fragment in split if not rounded_contains_rect(mask, fragment))
            parts = remaining
            if not parts:
                break
        if parts and len(applied) > 1 and any(any(r["x"] or r["y"] for r in mask["radii"]) for mask in applied):
            has_visible_point = any(not any(rounded_contains_point(mask, x, y) for mask in applied)
                                    for part in parts for x, y in corners(part))
            if not has_visible_point:
                gap(node, "Overlapping curved paint masks require exact union coverage", "visibility.curved_mask_union")
        if parts:
            for other in unknown:
                oid = other["id"]
                if (finite(other.get("paint_order")) and other["paint_order"] > node["paint_order"] and
                        oid != nid and oid not in ancestry[nid] and nid not in ancestry[oid] and
                        any(intersection(part, other["visible_bounds"]) for part in parts)):
                    gap(node, "Actual later paint " + oid + " has an unsupported opaque shape")
        fragments[nid], used_masks[nid] = parts, applied
    return fragments, used_masks, gaps


def uia_kind_matches(node, kind):
    control_type = (node.get("control_type") or "").removeprefix("ControlType.")
    class_name = (node.get("class_name") or "").rsplit(".", 1)[-1]
    if control_type == "Button" and kind == "toggle":
        return class_name in {"ToggleButton", "ToggleSwitch"} and any(isinstance(p, str) and "Toggle" in p for p in node.get("supported_patterns", []))
    if control_type == "ListItem" and kind == "tab":
        return class_name == "SelectorBarItem"
    return kind in UIA_KINDS.get(control_type, set())


def measured_text_boxes(boxes):
    return [copy.deepcopy(b) for b in boxes if isinstance(b, dict)
            and all(finite(b.get(k)) for k in ("x", "y", "width", "height"))
            and b["width"] >= 0 and b["height"] > 0]


def union_boxes(boxes):
    if not boxes:
        return None
    x, y = min(b["x"] for b in boxes), min(b["y"] for b in boxes)
    right, bottom = max(b["x"] + b["width"] for b in boxes), max(b["y"] + b["height"] for b in boxes)
    return {"x": x, "y": y, "width": right - x, "height": bottom - y}


def text_line_boxes(boxes):
    lines = []
    for b in sorted(boxes, key=lambda item: (item["y"], item["x"])):
        overlapping = next((line for line in lines if min(line["y"] + line["height"], b["y"] + b["height"])
                            > max(line["y"], b["y"])), None)
        if overlapping is None:
            lines.append(copy.deepcopy(b))
        else:
            overlapping.update(union_boxes([overlapping, b]))
    return sorted(lines, key=lambda b: (b["y"], b["x"]))


def project_text_leaves(raw, unmeasured, pointer):
    """Expose actual TextElement Run records, not one guessed paragraph font."""
    result = []
    for source in raw:
        node = copy.deepcopy(source)
        runs = node.get("layout", {}).get("rich_text_runs")
        if node["type"] not in {"TextBlock", "RichTextBlock"} or not isinstance(runs, list) or not runs or node.get("hidden_reason"):
            result.append(node)
            continue
        leaves = [(index, run) for index, run in enumerate(runs) if run.get("type", "Run") != "LineBreak" and run.get("text")]
        if not leaves:
            result.append(node)
            continue
        node["text_before_run_projection"] = node.get("text", "")
        node["text"] = ""
        node["text_container_projection"] = True
        node["projected_run_ids"] = []
        result.append(node)
        for index, run in leaves:
            rid = node["id"] + ":run:" + str(index)
            node["projected_run_ids"].append(rid)
            boxes = measured_text_boxes(run.get("bounds", []))
            bounds = union_boxes(boxes)
            clipped = intersection(bounds, node.get("visible_bounds"))
            if not boxes:
                unmeasured.append({"id": rid, "property": "rich_text_runs", "reason": "The recorded visible Run has no finite measured glyph rectangles",
                                   "source_owner": node["id"], "run_index": index})
            if run.get("geometry_complete") is not True:
                unmeasured.append({"id": rid, "property": "rich_text_runs", "reason": "The actual Run reports incomplete glyph geometry",
                                   "source_owner": node["id"], "run_index": index})
            if run.get("coordinate_space", node.get("layout", {}).get("character_boxes_coordinate_space")) != "content-window":
                unmeasured.append({"id": rid, "property": "rich_text_runs", "reason": "The recorded Run's glyph coordinate space is not measured in content-window pixels"})
            style = {
                "font_size": run.get("font_size"), "font_weight": run.get("font_weight"), "foreground": run.get("foreground"),
                "background": [0, 0, 0, 0], "border_color": [0, 0, 0, 0], "border_width": 0,
                "border_widths": [0, 0, 0, 0], "border_colors": [[0, 0, 0, 0] for _ in range(4)],
                "border_styles": ["none", "none", "none", "none"],
                "corner_radius": 0, "corner_radii": [0, 0, 0, 0], "background_image": "none", "shadow": [],
                "opacity": node.get("opacity"),
            }
            # Run is an actual glyph-only TextElement. Its parent's background
            # is retained on the owner, never duplicated on every leaf.
            state = {key: None for key in STATE_KEYS}
            state["hovered"] = node.get("state", {}).get("hovered")
            if isinstance(pointer, dict) and all(finite(pointer.get(k)) for k in ("x", "y")):
                state["hovered"] = bool(state["hovered"] and clipped and
                                        clipped["x"] <= pointer["x"] < clipped["x"] + clipped["width"] and
                                        clipped["y"] <= pointer["y"] < clipped["y"] + clipped["height"])
            leaf = {key: copy.deepcopy(node.get(key)) for key in
                    ("region", "opacity", "paint_order", "paint_layer", "canvas_z_index", "transform",
                     "axis_aligned_transform", "ancestor_clip", "clip")}
            leaf.update(id=rid, parent=node["id"], type="Run", text=run["text"], accessible_name="",
                        bounds=bounds, visible_bounds=clipped, hidden_reason=node.get("hidden_reason"),
                        render_sibling_order=index, style=style, state=state, icon=None, paint_kind="glyphs",
                        font_family=run.get("font_family"),
                        text_run_source={"owner": node["id"], "index": index, "start_offset": run.get("start_offset"),
                                         "end_offset": run.get("end_offset")},
                        layout={"wrap": node["layout"].get("wrap"), "truncation": node["layout"].get("truncation"),
                                "line_count": len(text_line_boxes(boxes)) if boxes else None,
                                "character_boxes": boxes, "character_boxes_coordinate_space": "content-window",
                                "rich_text_runs": [copy.deepcopy(run)]})
            if boxes and not positive(clipped):
                leaf["hidden_reason"] = "glyph rectangles fully outside the measured text-owner clip"
            result.append(leaf)
    return result


def run_font_witnesses(uia_nodes, owner, glyph_boxes):
    """Match actual UIA format ranges to the measured leaf's glyph positions."""
    candidates = []
    original_text = owner.get("text_before_run_projection", owner.get("text", ""))
    for candidate in uia_nodes:
        if candidate.get("control_type") not in {"ControlType.Text", "ControlType.Document"} or not positive(owner.get("bounds")):
            continue
        document = (candidate.get("text_pattern") or {}).get("document", {})
        if not original_text or original_text not in (candidate.get("name"), document.get("text")):
            continue
        # UIA BoundingRectangle can be the stretched layout slot. Its measured
        # TextPattern ranges describe the actual rendered text inside that slot.
        text_boxes = measured_text_boxes(document.get("bounds", []))
        text_envelope = union_boxes(text_boxes)
        outer_matches = distance(candidate["bounds"], owner["bounds"]) <= 8
        text_matches = positive(text_envelope) and distance(text_envelope, owner["bounds"]) <= 8
        if outer_matches or text_matches:
            candidates.append(candidate)
    providers = candidates
    if len(providers) != 1:
        # Same-position unrelated provider data is not a font fallback. Preserve
        # the candidates as raw evidence, but require unambiguous correspondence.
        return providers, []
    records = []
    for candidate in providers:
        for visible_range in (candidate.get("text_pattern") or {}).get("visible_ranges", []):
            for run in visible_range.get("format_runs") or [visible_range]:
                run_boxes = measured_text_boxes(run.get("bounds", []))
                relevant = [b for b in glyph_boxes if any(intersection(b, measured) for measured in run_boxes)]
                if not relevant:
                    continue
                records.append({"uia_id": candidate["id"], "attributes": copy.deepcopy(run.get("attributes", {})),
                                "attribute_status": copy.deepcopy(run.get("attribute_status", {})),
                                "font_family_coverage": copy.deepcopy(run.get("font_family_coverage")),
                                "bounds": run_boxes, "glyph_boxes": relevant, "text": run.get("text")})
    return providers, records


def visible_uia_errors(uia):
    """Retain raw diagnostics, separating only nodes proven UIA-offscreen."""
    nodes = uia.get("raw_nodes", [])
    by_id = {n["id"]: n for n in nodes}
    errors, nonvisible = [], copy.deepcopy(uia.get("nonvisible_diagnostics", []))
    for error in uia.get("extraction_errors", []):
        text = str(error)
        source = by_id.get(text.split(":", 1)[0])
        path_match = re.match(r"^/raw_nodes/(\d+)(?:/|:)", text)
        numeric_measurement = False
        if source is None and path_match and int(path_match[1]) < len(nodes):
            source = nodes[int(path_match[1])]
            numeric_measurement = True
        own_measurement = source and (numeric_measurement or any(
            text == source["id"] + ": " + str(measurement) for measurement in source.get("measurement_errors", [])))
        # An offscreen parent's subtree may still contain visible controls.
        # Only its own measured property errors are known to be nonvisible.
        if own_measurement and source.get("state", {}).get("offscreen") is True:
            nonvisible.append({"source": "UIA", "id": source["id"], "diagnostic": error,
                               "reason": "The provider measured IsOffscreen=true; this node has no visible element"})
        else:
            errors.append(error)
    return errors, nonvisible


def interaction_applicability(node, kind, witness):
    """Distinguish nonapplicable UIA defaults from actual interactive state."""
    if kind in INTERACTIVE_KINDS:
        return True, "Native semantic interactive control"
    if node["type"] == "Run":
        return False, "A TextElement Run is glyph content, not an independent control"
    if witness:
        patterns = witness.get("supported_patterns")
        if isinstance(patterns, list) and any(any(action in pattern for action in ACTION_PATTERNS)
                                               for pattern in patterns if isinstance(pattern, str)):
            return True, "Actual UIA action pattern"
        focusable = witness.get("state", {}).get("focusable")
        if focusable is True:
            return True, "UIA measured IsKeyboardFocusable=true"
        if (node["type"] in PAINT_ONLY_TYPES or node.get("render_type_evidence", {}).get("is_panel") is True) and focusable is False and isinstance(patterns, list):
            return False, "Paint-only XAML element; UIA reports no action pattern and IsKeyboardFocusable=false"
        return None, "UIA interaction applicability is not completely measured"
    interaction = node.get("interaction_evidence", {})
    if interaction.get("is_control") is False and (node["type"] in PAINT_ONLY_TYPES or node.get("render_type_evidence", {}).get("is_panel") is True):
        return False, "Actual XAML non-Control paint element with no independent UIA interactive witness"
    if interaction.get("is_hit_test_visible") is False and interaction.get("is_tab_stop") is False:
        return False, "Actual XAML element is neither hit-testable nor a tab stop"
    if kind == "divider":
        return False, "Native divider has no independent interactive control"
    return None, "Actual native interaction applicability is unavailable"


def host_container_ownership(uia, raw):
    """Own only the measured main HWND / WinUI content-host chain once."""
    roots = [node for node in raw if node.get("parent") is None and node.get("region") == "window"
             and node.get("bounds") == {"x": 0, "y": 0, "width": uia["viewport"]["width"], "height": uia["viewport"]["height"]}]
    if len(roots) != 1 or not isinstance(uia.get("primary_hwnd"), int) or uia["primary_hwnd"] <= 0:
        return []
    viewport = roots[0]["bounds"]
    by_id = {node["id"]: node for node in uia.get("raw_nodes", [])}
    primaries = [node for node in by_id.values() if node.get("parent") is None
                 and node.get("root_kind") == "primary-window" and node.get("control_type") == "ControlType.Window"
                 and node.get("class_name") == "WinUIDesktopWin32WindowClass"
                 and node.get("native_window_handle") == uia["primary_hwnd"]
                 and intersection(node.get("bounds"), viewport) == viewport]
    if len(primaries) != 1:
        return []
    primary = primaries[0]
    bridges = [node for node in by_id.values() if node.get("parent") == primary["id"]
               and node.get("class_name") == "Microsoft.UI.Content.DesktopChildSiteBridge"
               and node.get("control_type") == "ControlType.Pane" and node.get("bounds") == viewport]
    if len(bridges) != 1:
        return []
    bridge = bridges[0]
    sites = [node for node in by_id.values() if node.get("parent") == bridge["id"]
             and node.get("class_name") == "InputSiteWindowClass" and node.get("control_type") == "ControlType.Pane"
             and node.get("bounds") == viewport]
    if len(sites) != 1:
        return []
    return [{"source": node["id"], "owner": roots[0]["id"], "reason": "Measured main HWND and WinUI content-host chain own the XAML content root",
             "host_evidence": {"primary_hwnd": uia["primary_hwnd"], "primary": primary["id"], "bridge": bridge["id"],
                               "input_site": sites[0]["id"], "bounds": copy.deepcopy(node["bounds"]), "content_bounds": copy.deepcopy(viewport)}}
            for node in (primary, bridge, sites[0])]


def transparent_uia_ownership(uia_nodes, raw):
    """Reconcile a provider which stays onscreen for an actually transparent control.

    IsOffscreen does not measure opacity. This owns only the individual raw
    render node, never a provider subtree. Exact native runtime class, reported
    name and box must establish a unique pair in both independent trees; any
    visible or duplicate candidate keeps the coverage failure.
    """
    pairs = []
    for provider in uia_nodes:
        if provider.get("measurement_errors") or provider.get("state", {}).get("offscreen") is not False:
            continue
        name = provider.get("name")
        native_class = (provider.get("class_name") or "").rsplit(".", 1)[-1]
        if not isinstance(name, str) or not name or not native_class:
            continue
        candidates = [node for node in raw
                      if node.get("type") in CONTROL_KINDS
                      and node["type"] == native_class
                      and uia_kind_matches(provider, CONTROL_KINDS[node["type"]])
                      and node.get("accessible_name") == name
                      and positive(node.get("bounds"))
                      and node["bounds"] == provider.get("bounds")]
        if len(candidates) != 1:
            continue
        rendered = candidates[0]
        if (rendered.get("hidden_reason") != "zero opacity"
                or not finite(rendered.get("opacity")) or rendered["opacity"] != 0
                or rendered.get("measurement_error")):
            continue
        pairs.append((provider, rendered))
    counts = defaultdict(int)
    for _, rendered in pairs:
        counts[rendered["id"]] += 1
    return [{"source": provider["id"], "owner": rendered["id"],
             "reason": "Unique native control has measured cumulative XAML opacity zero despite UIA IsOffscreen=false",
             "visibility_evidence": {"opacity": rendered["opacity"], "hidden_reason": rendered["hidden_reason"],
                                     "uia_offscreen": provider.get("state", {}).get("offscreen"),
                                     "native_class": rendered["type"], "accessible_name": rendered["accessible_name"],
                                     "xaml_bounds": copy.deepcopy(rendered["bounds"]), "uia_bounds": copy.deepcopy(provider["bounds"]),
                                     "scope": "this exact node only; no descendant or popup ownership"}}
            for provider, rendered in pairs if counts[rendered["id"]] == 1]


def project(xaml_path, uia_path, png_path):
    xaml = json.loads(Path(xaml_path).read_text(encoding="utf-8-sig"))
    uia = json.loads(Path(uia_path).read_text(encoding="utf-8-sig"))
    image = Image.open(png_path).convert("RGBA")
    uia_errors, nonvisible_diagnostics = visible_uia_errors(uia)
    errors = list(xaml.get("extraction_errors", [])) + uia_errors
    unmeasured = []
    if xaml["viewport"]["scale"] != 1:
        errors.append("XAML rasterization scale differs from the required 1:1 screenshot")
    if uia.get("case_id") != xaml.get("scene_id"):
        errors.append("UIA and XAML scene identifiers differ")
    if uia.get("viewport") != xaml.get("viewport"):
        errors.append("UIA and XAML viewports differ")
    if image.size != (xaml["viewport"]["width"], xaml["viewport"]["height"]):
        errors.append("Screenshot size differs from measured viewport")
    source_raw = xaml["raw_nodes"]
    if not source_raw or not uia.get("raw_nodes"):
        errors.append("Independent UIA and XAML source trees must both be nonempty")
    raw = project_text_leaves(source_raw, unmeasured, xaml.get("pointer"))
    by_id = {n["id"]: n for n in raw}
    fragments, occlusion_masks, occlusion_gaps = measured_occlusion(raw, by_id)
    unmeasured.extend(occlusion_gaps)
    children = defaultdict(list)
    for node in raw:
        children[node.get("parent")].append(node)
    projection = []
    elements = []
    owned = {}
    semantic = {n["id"] for n in raw if n["type"] in CONTROL_KINDS or n["type"] in PAINT_CONTROL_KINDS}
    def ancestor(node, choices):
        parent = by_id.get(node.get("parent"))
        while parent:
            if parent["id"] in choices:
                return parent
            parent = by_id.get(parent.get("parent"))
        return None

    def descendants(node):
        for child in children[node["id"]]:
            yield child
            yield from descendants(child)

    def visible(node):
        return not node.get("hidden_reason") and positive(node.get("visible_bounds")) and bool(fragments.get(node["id"]))

    def user_content(node, control_id):
        current = node
        while current and current["id"] != control_id:
            if current.get("declared_content_owner") == control_id:
                return True
            current = by_id.get(current.get("parent"))
        return False

    # Own a simple label once, while composite rows retain individual labels.
    control_label = {}
    control_paint = defaultdict(list)
    for node in raw:
        if node["id"] not in semantic or not visible(node):
            continue
        labels = []
        avatar_backgrounds = []
        for child in descendants(node):
            nearest = ancestor(child, semantic)
            if not nearest or nearest["id"] != node["id"] or not visible(child):
                continue
            if child["type"] in TEXT_TYPES and child.get("text") and not ancestor(child, {n["id"] for n in raw if n["type"] in ICON_TYPES}):
                labels.append(child)
            if child["type"] in {"Border", "Grid", "Rectangle", "ContentPresenter"}:
                if node["type"] == "PersonPicture":
                    # A letter/avatar background is one semantic surface. Its
                    # decorative rings, image and icon content remain separate.
                    if distance(child["bounds"], node["bounds"]) <= 1e-6 and painted(child.get("style", {}).get("background")):
                        avatar_backgrounds.append(child)
                    continue
                if user_content(child, node["id"]):
                    continue
                control_paint[node["id"]].append(child)
                owned[child["id"]] = (node["id"], "semantic control template paint")
        if len(avatar_backgrounds) == 1:
            child = avatar_backgrounds[0]
            control_paint[node["id"]].append(child)
            owned[child["id"]] = (node["id"], "single measured avatar background at the actual avatar bounds")
        elif len(avatar_backgrounds) > 1:
            unmeasured.append({"id": node["id"], "property": "avatar.paint_ownership",
                               "reason": "Multiple actual avatar background layers require independent paint composition",
                               "sources": [child["id"] for child in avatar_backgrounds]})
        distinct_semantics = any(child["id"] in semantic and visible(child) for child in descendants(node))
        distinct_content_paint = any(user_content(child, node["id"]) and visible(child)
                                     and child["type"] not in TEXT_TYPES
                                     and (painted(child.get("style", {}).get("background"))
                                          or painted(child.get("style", {}).get("border_color"))
                                          and finite(child.get("style", {}).get("border_width"))
                                          and child["style"]["border_width"] > 0)
                                     for child in descendants(node))
        compound = distinct_semantics or distinct_content_paint and node["type"] != "PersonPicture"
        if len(labels) == 1 and not compound and (CONTROL_KINDS.get(node["type"]) or PAINT_CONTROL_KINDS.get(node["type"])) not in {"card", "list-row", "chart-node", "region"}:
            control_label[node["id"]] = labels[0]
            owned[labels[0]["id"]] = (node["id"], "single simple control label")
    icons = {n["id"] for n in raw if n["type"] in ICON_TYPES}
    for node in raw:
        owner = ancestor(node, icons)
        if owner:
            owned[node["id"]] = (owner["id"], "icon implementation glyph")

    host_ownership = host_container_ownership(uia, raw)
    projection.extend(host_ownership)
    used_uia = {record["source"] for record in host_ownership}
    uia_nodes = [n for n in uia.get("raw_nodes", []) if positive(n.get("bounds")) and not n.get("state", {}).get("offscreen")]
    transparent_ownership = transparent_uia_ownership(uia_nodes, raw)
    projection.extend(transparent_ownership)
    used_uia.update(record["source"] for record in transparent_ownership)
    for node in uia.get("raw_nodes", []):
        for error in node.get("measurement_errors", []):
            if node.get("state", {}).get("offscreen") is True:
                nonvisible_diagnostics.append({"source": "UIA", "id": node["id"], "diagnostic": error,
                                               "reason": "The provider measured IsOffscreen=true; this node has no visible element"})
            else:
                unmeasured.append({"id": node["id"], "property": "UIA measurement", "reason": error})
        if node in uia_nodes and not node.get("control_type"):
            unmeasured.append({"id": node["id"], "property": "UIA control_type", "reason": "Visible provider node did not report its control type"})
    order = defaultdict(int)
    for node in raw:
        if not visible(node):
            reason = node.get("hidden_reason") or ("fully occluded by measured opaque paint" if positive(node.get("visible_bounds")) and not fragments.get(node["id"]) else "not a visible rendered box")
            projection.append({"source": node["id"], "reason": reason, "occlusion_masks": occlusion_masks.get(node["id"], [])})
            continue
        if node["id"] in owned:
            owner, why = owned[node["id"]]
            projection.append({"source": node["id"], "owner": owner, "reason": why})
            continue
        typ = node["type"]
        style = copy.deepcopy(node.get("style", {}))
        kind = CONTROL_KINDS.get(typ) or PAINT_CONTROL_KINDS.get(typ)
        text = node.get("text", "")
        if typ in TEXT_TYPES:
            if node.get("text_container_projection"):
                kind = "card" if painted(style.get("background")) or painted(style.get("border_color")) and finite(style.get("border_width")) and style["border_width"] > 0 else None
            else:
                kind = "text" if text else None
        elif typ in ICON_TYPES:
            kind = "icon"
        elif typ in {"Image", "PersonPicture"}:
            kind = "avatar" if typ == "PersonPicture" else "image"
        elif typ in {"Line", "Path", "Polyline"}:
            kind = "chart-edge" if ancestor(node, {n["id"] for n in raw if n["type"] == "Canvas"}) else "divider"
        elif typ == "Ellipse":
            kind = "state-dot" if node["bounds"]["width"] <= 10 else "image"
        elif typ in {"Border", "Rectangle", "Grid", "StackPanel", "Canvas", "ContentPresenter"} or node.get("render_type_evidence", {}).get("is_panel") is True:
            if (painted(style.get("background"))
                    or painted(style.get("border_color")) and finite(style.get("border_width")) and style["border_width"] > 0
                    or node.get("render_type_evidence", {}).get("is_shape") is True
                    and painted(style.get("foreground")) and finite(style.get("stroke_width")) and style["stroke_width"] > 0):
                kind = "divider" if min(node["bounds"]["width"], node["bounds"]["height"]) <= 2 else "card"
                if node.get("parent") is None or typ == "Border" and node["region"] != by_id.get(node.get("parent"), {}).get("region"):
                    kind = "region"
        if not kind:
            projection.append({"source": node["id"], "reason": "layout wrapper with no own text, role, background or border"})
            # Render types not accounted for must not disappear behind a generic
            # wrapper label. Their independent UIA nodes are also reconciled below.
            if typ in {"WebView", "SwapChainPanel", "MediaPlayerElement", "RichEditBox"}:
                unmeasured.append({"id": node["id"], "property": "paint", "reason": "uninstrumented rendered type " + typ})
            continue
        label = control_label.get(node["id"])
        layout = copy.deepcopy(node.get("layout", {}))
        if label:
            text = label.get("text", text)
            for key in ("font_size", "font_weight", "foreground"):
                style[key] = label.get("style", {}).get(key)
            layout = copy.deepcopy(label.get("layout", {}))
        elif node["id"] in semantic and any(c.get("text") for c in descendants(node)):
            text = ""  # Composite control: each independently styled label remains.
        if kind == "input":
            value = node.get("text", "")
            text = value or node.get("layout", {}).get("placeholder") or ""
        else:
            value = None
        if kind == "button" and not text:
            has_label = any(c["type"] in TEXT_TYPES and c.get("text") and visible(c)
                            and not ancestor(c, icons) for c in descendants(node))
            kind = "icon-button" if not has_label and any(c["type"] in ICON_TYPES for c in descendants(node)) else "button"
        # Measure template paint closest to the actual control box; retain every
        # source id. Do not substitute a reference color or a presumed theme value.
        paints = sorted(control_paint[node["id"]], key=lambda c: distance(c["bounds"], node["bounds"]))
        for paint in paints:
            if distance(paint["bounds"], node["bounds"]) > 4:
                continue
            ps = paint.get("style", {})
            if not painted(ps.get("background")) and not (painted(ps.get("border_color")) and finite(ps.get("border_width")) and ps["border_width"] > 0):
                continue
            if painted(ps.get("background")):
                style["background"] = ps["background"]
                style["corner_radius"] = ps.get("corner_radius")
                style["corner_radii"] = ps.get("corner_radii")
            if painted(ps.get("border_color")) and finite(ps.get("border_width")) and ps["border_width"] > 0:
                for key in ("border_color", "border_width", "border_widths", "border_colors", "border_styles", "corner_radius", "corner_radii"):
                    style[key] = ps.get(key)
            break
        state = {k: node.get("state", {}).get(k) for k in STATE_KEYS}
        matching = [n for n in uia_nodes if n["id"] not in used_uia and uia_kind_matches(n, kind) and distance(n["bounds"], node["bounds"]) <= 8]
        matching.sort(key=lambda n: (n.get("name", "") not in (text, node.get("accessible_name", "")), distance(n["bounds"], node["bounds"])))
        witness = matching[0] if matching else None
        interactive, interaction_reason = interaction_applicability(node, kind, witness)
        if witness:
            used_uia.add(witness["id"])
            for key in STATE_KEYS:
                if key in {"enabled", "focused"} and interactive is not True:
                    continue
                if key in witness.get("state", {}) and witness["state"][key] is not None:
                    state[key] = witness["state"][key]
            if layout.get("line_count") is None:
                ranges = (witness.get("text_pattern") or {}).get("visible_ranges", [])
                rectangles = [b for r in ranges for b in r.get("bounds", []) if positive(b)]
                if rectangles:
                    layout["line_count"] = len({round(b["y"], 1) for b in rectangles})
        if interactive is False:
            state["enabled"] = state["focused"] = None
        elif interactive is None:
            unmeasured.append({"id": node["id"], "property": "state.interaction_applicability", "reason": interaction_reason})
        if typ in CONTROL_KINDS and not witness:
            unmeasured.append({"id": node["id"], "property": "UIA correspondence", "reason": "No independent UIA control box at the rendered position"})
        actual_text_boxes = [copy.deepcopy(b) for b in layout.get("character_boxes", [])
                             if isinstance(b, dict) and all(finite(b.get(k)) for k in ("x", "y", "width", "height"))
                             and b["width"] >= 0 and b["height"] > 0] if layout.get("character_boxes_coordinate_space") == "content-window" else []
        if not actual_text_boxes and witness:
            actual_text_boxes = [copy.deepcopy(b) for r in (witness.get("text_pattern") or {}).get("visible_ranges", [])
                                 for b in r.get("bounds", []) if positive(b)]
        text_source = label or node
        run_source = text_source.get("text_run_source")
        run_name_witness = None
        actual_run_font_records = []
        font_witnesses = [] if run_source else [witness] if witness else []
        if run_source:
            text_owner = by_id[run_source["owner"]]
            run_providers, actual_run_font_records = run_font_witnesses(uia_nodes, text_owner, actual_text_boxes)
            # A single Run representing the whole measured text owner can
            # retain that owner's actual UIA Name. A parent name is not copied
            # into individual rich-text fragments or a containing button.
            if (typ == "Run" and len(run_providers) == 1 and len(text_owner.get("projected_run_ids", [])) == 1
                    and text == text_owner.get("text_before_run_projection")
                    and isinstance(run_providers[0].get("name"), str)):
                run_name_witness = run_providers[0]
            if len(run_providers) > 1:
                unmeasured.append({"id": node["id"], "property": "UIA text-owner correspondence",
                                   "reason": "Multiple independent UIA providers match the measured text owner; none is silently claimed",
                                   "candidates": [provider["id"] for provider in run_providers]})
            for provider in run_providers if len(run_providers) == 1 else []:
                if actual_text_boxes:
                    used_uia.add(provider["id"])
                    projection.append({"source": provider["id"], "owner": text_owner["id"], "element": node["id"],
                                       "reason": "UIA text owner represented by measured TextElement Run",
                                       "run_source": copy.deepcopy(run_source)})
        elif label:
            font_witnesses += [n for n in uia_nodes if n.get("control_type") == "ControlType.Text"
                               and n.get("name") == text and distance(n["bounds"], label["bounds"]) <= 8]
        provider_fonts = []
        font_records = list(actual_run_font_records)
        for font_source in font_witnesses:
            for text_range in (font_source.get("text_pattern") or {}).get("visible_ranges", []):
                for run in text_range.get("format_runs") or [text_range]:
                    font_records.append(dict(run, uia_id=font_source["id"]))
        for record in font_records:
            family = record.get("attributes", {}).get("font_family")
            if record.get("attribute_status", {}).get("font_family") != "measured" or not isinstance(family, str) or not family:
                continue
            coverage = record.get("font_family_coverage")
            if isinstance(coverage, dict) and coverage.get("status") in {"unresolved", "provider-family-cannot-cover-text"}:
                unmeasured.append({"id": node["id"], "property": "style.rendered_fonts",
                                   "reason": coverage.get("reason") or "Provider font family cannot establish the actual rendered glyph family",
                                   "uia_id": record["uia_id"], "font_family_coverage": copy.deepcopy(coverage)})
                continue
            identity = {"family_name": family, "postscript_name": None, "is_custom_font": None, "glyph_count": None,
                        "source": "UIA.TextPattern.FontNameAttribute", "uia_id": record["uia_id"],
                        "proves_actual_render_face": False, "font_family_coverage": copy.deepcopy(coverage)}
            if not any(f["family_name"] == family for f in provider_fonts):
                provider_fonts.append(identity)
        if text and provider_fonts:
            unmeasured.append({"id": node["id"], "property": "style.rendered_fonts.actual_face",
                               "reason": "UIA font-name attributes are retained as provider evidence; actual DirectWrite glyph-run/fallback face identity is not exposed by this capture",
                               "provider_families": [font["family_name"] for font in provider_fonts]})
        # WinUI's UIA adapter reads TextElement.FontFamily.Source, not the
        # physical fallback face. Never put that requested family into the
        # canonical actual-font field, even when a cmap supports the text.
        style["rendered_fonts"] = None
        if text and not actual_text_boxes:
            unmeasured.append({"id": node["id"], "property": "evidence.text_bounds", "reason": "Actual window-relative text rectangles are unavailable"})
        if text and not provider_fonts:
            unmeasured.append({"id": node["id"], "property": "style.rendered_fonts", "reason": "UIA did not measure the rendered font; declared XAML family is not substituted"})
        if run_source and actual_text_boxes:
            font_rectangles = [b for record in actual_run_font_records
                               if record.get("attribute_status", {}).get("font_family") == "measured"
                               and isinstance(record.get("attributes", {}).get("font_family"), str)
                               and record["attributes"]["font_family"]
                               for b in record.get("bounds", [])]
            if any(b["width"] > 0 and not any(intersection(b, font_box) for font_box in font_rectangles) for b in actual_text_boxes):
                unmeasured.append({"id": node["id"], "property": "style.rendered_fonts",
                                   "reason": "Some measured Run glyph positions have no independent UIA font-range correspondence"})
        rich_runs = layout.get("rich_text_runs", [])
        if not text:
            layout = {"wrap": None, "truncation": None, "line_count": None}
            style["font_size"] = style["font_weight"] = None
            if kind not in {"icon", "chart-edge"} and node.get("render_type_evidence", {}).get("is_shape") is not True:
                style["foreground"] = None
        bounds = node["bounds"]
        points = [(bounds["x"] + bounds["width"] * x, bounds["y"] + bounds["height"] * y) for x, y in ((.5,.5), (.1,.1), (.9,.1), (.1,.9), (.9,.9))]
        samples = [{"x": int(x), "y": int(y), "rgba": list(image.getpixel((int(x), int(y))))} for x, y in points if 0 <= x < image.width and 0 <= y < image.height]
        for key in ("wrap", "truncation", "line_count"):
            if text and layout.get(key) is None:
                unmeasured.append({"id": node["id"], "property": "layout." + key, "reason": "No rendered text measurement"})
        if state["hovered"] is None:
            unmeasured.append({"id": node["id"], "property": "state.hovered", "reason": "Pointer hit-test evidence missing"})
        if kind == "icon" and not node.get("icon"):
            unmeasured.append({"id": node["id"], "property": "icon", "reason": "No actual glyph/vector measurement"})
        for key in ("background", "border_color", "corner_radius", "opacity", "shadow", "background_image"):
            if style.get(key) is None:
                unmeasured.append({"id": node["id"], "property": "style." + key, "reason": "Unsupported rendered brush/property"})
        region = node["region"]
        name_witness = witness or run_name_witness
        reported_name = name_witness.get("name") if name_witness else node.get("accessible_name")
        element = {"id": node["id"], "parent": node.get("parent"), "region": region, "order": order[region], "kind": kind,
                   "text": text, "name": reported_name if isinstance(reported_name, str) else "",
                   "bounds": bounds, "visible_bounds": node["visible_bounds"], "style": style, "state": state,
                   "layout": {k: layout.get(k) for k in ("wrap", "truncation", "line_count")}, "icon": node.get("icon"),
                   "evidence": {"source": "XAML render tree + independent UIA", "type": typ, "uia_id": witness["id"] if witness else None,
                                "label_source": label["id"] if label else None, "paint_sources": [p["id"] for p in paints],
                                "font_family": node.get("font_family"), "pixel_samples": samples, "value": value,
                                "placeholder": node.get("layout", {}).get("placeholder"),
                                "text_bounds": actual_text_boxes, "text_coordinate_space": "content-window",
                                "rich_text_runs": rich_runs, "visible_fragments": fragments.get(node["id"]),
                                "text_run_source": copy.deepcopy(run_source), "uia_font_ranges": actual_run_font_records,
                                "font_family_evidence": [copy.deepcopy(record.get("font_family_coverage")) for record in font_records],
                                "provider_fonts": provider_fonts if text else [],
                                "interaction_applicability": {"applicable": interactive, "reason": interaction_reason,
                                                              "xaml": copy.deepcopy(node.get("interaction_evidence")),
                                                              "uia_state": copy.deepcopy(witness.get("state")) if witness else None,
                                                              "uia_patterns": copy.deepcopy(witness.get("supported_patterns")) if witness else None},
                                "accessible_name_evidence": {"reported": reported_name, "source": "UIA.NameProperty" if name_witness else "XAML.AutomationProperties.Name",
                                                             "uia_id": name_witness["id"] if name_witness else None,
                                                             "ownership": "whole text owner represented by one measured Run" if run_name_witness and not witness else "direct element",
                                                             "status": "reported" if isinstance(reported_name, str) else "not-provided",
                                                             "note": "No reported accessible name is represented by an empty string; visible text is retained separately"},
                                "stroke_evidence": copy.deepcopy(node.get("stroke_evidence")),
                                "state_evidence": copy.deepcopy(node.get("state_evidence")),
                                "render_type_evidence": copy.deepcopy(node.get("render_type_evidence")),
                                "declared_content_source": node.get("declared_content_source"),
                                "brush_evidence": copy.deepcopy(node.get("style", {}).get("brush_evidence")),
                                "animated_icon_evidence": copy.deepcopy(node.get("animated_icon_evidence")),
                                "image_source_evidence": copy.deepcopy(node.get("image_source_evidence")),
                                "occlusion_masks": occlusion_masks.get(node["id"], []),
                                "visible_fragments_are_envelopes": True}}
        order[region] += 1
        projection.append({"source": node["id"], "element": node["id"], "reason": "visible rendered element"})
        # Collection is deliberately independent of the reference element count.
        elements.append(element)
    for n in uia_nodes:
        if n["id"] in used_uia:
            continue
        b = n["bounds"]
        if b["x"] + b["width"] <= 0 or b["y"] + b["height"] <= 0 or b["x"] >= image.width or b["y"] >= image.height:
            continue
        covered = next((r for r in raw if positive(r.get("bounds")) and positive(r.get("visible_bounds"))
                        and not r.get("hidden_reason") and not fragments.get(r["id"])
                        and uia_kind_matches(n, CONTROL_KINDS.get(r["type"], "text" if r["type"] in TEXT_TYPES else ""))
                        and distance(b, r["bounds"]) <= 8), None)
        if covered:
            projection.append({"source": n["id"], "owner": covered["id"], "reason": "UIA box corresponds to measured fully occluded render node",
                               "occlusion_masks": occlusion_masks.get(covered["id"], [])})
            continue
        # A UIA text child can already be represented by the owning control's
        # label. Preserve the measured ownership instead of silently losing it.
        owner = next((e for e in elements if n.get("control_type") == "ControlType.Text" and n.get("name") and n.get("name") == e["text"] and e["bounds"]["x"] <= b["x"] and e["bounds"]["y"] <= b["y"] and b["x"] + b["width"] <= e["bounds"]["x"] + e["bounds"]["width"] + 1 and b["y"] + b["height"] <= e["bounds"]["y"] + e["bounds"]["height"] + 1), None)
        if owner:
            projection.append({"source": n["id"], "owner": owner["id"], "reason": "UIA label owned by corresponding rendered control"})
        elif n.get("is_control_element") or n.get("is_content_element"):
            unmeasured.append({"id": n["id"], "property": "render correspondence", "reason": "Visible UIA node not represented in XAML projection", "control_type": n.get("control_type"), "name": n.get("name")})
    emitted_ids = {e["id"] for e in elements}
    for element in elements:
        parent = element["parent"]
        element["evidence"]["raw_parent"] = parent
        while parent is not None and parent not in emitted_ids:
            parent = by_id.get(parent, {}).get("parent")
        element["parent"] = parent
    return {"schema_version": 1, "scene_id": xaml["scene_id"], "client": "windows", "viewport": xaml["viewport"],
            "elements": elements, "extraction_errors": errors,
            "coverage": {"raw_nodes": len(source_raw) + len(uia.get("raw_nodes", [])), "recorded_text_leaves": len(raw) - len(source_raw),
                         "emitted_elements": len(elements), "unmeasured": unmeasured},
            "projection": projection, "nonvisible_diagnostics": nonvisible_diagnostics,
            "raw_evidence": {"xaml": Path(xaml_path).name, "uia": Path(uia_path).name}}
