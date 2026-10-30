"""Project independently measured UIA + XAML evidence; never read reference data.

Raw records and projection ownership are retained for audit. Incomplete paint,
visibility or typography measurements fail coverage instead of being guessed.
"""
import copy
import json
import math
import re
import struct
from collections import defaultdict
from pathlib import Path

from PIL import Image

from paint_patterns import MeasurementError, captured_pattern, pattern_measurement_issue
from image_projection import project_windows_image
from windows_outline import native_outline
from native_label_geometry import native_label_geometry
from native_label_fonts import native_label_fonts
from windows_automation_identity import OWNER_SOURCE, bind_automation_identities
from windows_text_precision import analyze_text_precision
from line_breaks import BREAK_FIELDS, break_strategy_issues
from font_weights import project_font_weights, font_weight_issues
from windows_toggle_parts import windows_toggle_parts
from windows_avatar_parts import windows_avatar_parts
from windows_composition_clip import composition_clip, apply_composition_clip
from native_path_source import native_path_source_contract, native_path_iterator


def project_line_break_strategies(layout, text, kind, owner):
    """Retain the actual text-owner policy, never derive it from legacy wrap."""
    applicable = bool(text) or kind == "text"
    original = copy.deepcopy(layout.get("line_break_configuration"))
    if not applicable:
        fields = {"break_strategy_version": 1, **{key: None for key in BREAK_FIELDS}}
        evidence = {"applicable": False, "source": "Actual XAML emitted text ownership", "owner": owner,
                    "raw": {"unused_text_owner_configuration": original},
                    "reason": "This emitted element has no text under the existing text applicability predicate."}
    else:
        fields = {key: copy.deepcopy(layout.get(key)) for key in ("break_strategy_version", *BREAK_FIELDS)}
        evidence = original if isinstance(original, dict) else {
            "source": "Actual XAML text owner; line-break policy unmeasured", "owner": owner, "raw": {},
            "errors": ["No live TextWrapping or current production text-layout configuration was captured."]}
        evidence["applicable"] = True
        evidence["projected_text_owner"] = owner
    return fields, evidence


CONTROL_KINDS = {
    "Button": "button", "AppBarButton": "button", "RepeatButton": "button",
    "HyperlinkButton": "link", "TextBox": "input", "ComposerInput": "input", "NativeTextarea": "input", "PasswordBox": "input",
    "CheckBox": "checkbox", "RadioButton": "checkbox", "ToggleSwitch": "toggle",
    "ToggleButton": "toggle", "NativeOverviewToggle": "toggle", "ComboBox": "dropdown", "SelectorBarItem": "tab",
    "TabViewItem": "tab", "MenuBarItem": "menu-item", "MenuFlyoutItem": "menu-item",
    "MenuFlyoutSubItem": "menu-item", "ToggleMenuFlyoutItem": "menu-item",
    "ListViewItem": "list-row", "TreeViewItem": "list-row", "Expander": "card",
    "ContentDialog": "card", "NativeContentDialog": "card", "MenuFlyoutSeparator": "divider", "ScrollBar": "scrollbar",
    "NativeRegionGrid": "region",
    "ChartNodeButton": "chart-node", "ChartSurface": "region", "WorkspaceCodeView": "code",
}
AVATAR_TYPES = {"PersonPicture"}
PAINT_CONTROL_KINDS = {"OverviewChipView": "chip", "OverviewBadgeView": "badge", **{typ: "avatar" for typ in AVATAR_TYPES}}
TEXT_TYPES = {"TextBlock", "RichTextBlock", "WorkspaceCodeView", "NativeLabel", "Run"}
ICON_TYPES = {"FontIcon", "SymbolIcon", "PathIcon", "BitmapIcon", "AnimatedIcon", "ReferenceVectorIcon"}
STATE_KEYS = ("enabled", "selected", "current", "checked", "indeterminate", "expanded", "focused", "hovered", "unread")
UIA_KINDS = {"Button": {"button", "icon-button", "chart-node"}, "Text": {"text"}, "Edit": {"input"}, "CheckBox": {"checkbox"},
             "RadioButton": {"checkbox"}, "ComboBox": {"dropdown"}, "TabItem": {"tab"}, "MenuItem": {"menu-item"},
             "ListItem": {"list-row"}, "TreeItem": {"list-row"}, "Image": {"image", "avatar", "icon"},
             "Hyperlink": {"link"}, "Separator": {"divider"}, "Group": {"region", "card"}, "Pane": {"region", "card"},
             "Custom": {"region", "card"}, "Window": {"region"}, "Document": {"code"},
             "ScrollBar": {"scrollbar"}, "Thumb": {"resize-handle", "scrollbar-thumb"}}
INTERACTIVE_KINDS = {"button", "icon-button", "chart-node", "link", "input", "checkbox", "toggle", "dropdown", "tab", "menu-item", "list-row", "resize-handle", "scrollbar", "scrollbar-thumb"}
ACTION_PATTERNS = ("InvokePattern", "TogglePattern", "SelectionItemPattern", "ExpandCollapsePattern", "ValuePattern", "RangeValuePattern")
PAINT_ONLY_TYPES = TEXT_TYPES | ICON_TYPES | set(PAINT_CONTROL_KINDS) | {"Image", "PersonPicture", "Border", "Rectangle", "Ellipse", "Line", "Path", "Polyline", "Grid", "StackPanel", "Canvas", "ContentPresenter"}


def semantic_control_kind(node, scrollbar_thumbs=None):
    """Use captured production object identity, not a Thumb name or guessed role."""
    region_evidence = node.get("region_container_evidence")
    if (node.get("type") == "ScrollViewer"
            and isinstance(region_evidence, dict)
            and region_evidence.get("source") == "actual MainWindow.chatScroll object identity"):
        return "region"
    evidence = node.get("resize_handle_evidence")
    if (node.get("type") == "Thumb" and isinstance(evidence, dict)
            and evidence.get("source") in {"actual NativeTextarea.ResizeGrip.Handle object identity",
                                           "actual MainWindow.panelResize object identity"}):
        return "resize-handle"
    if node.get("type") == "Thumb" and node.get("id") in (scrollbar_thumbs or {}):
        return "scrollbar-thumb"
    return CONTROL_KINDS.get(node.get("type"))


def measured_runtime_type(node, property_name):
    """Null or absent runtime receipts stay unknown, never inferred by name."""
    evidence = node.get("render_type_evidence")
    return evidence.get(property_name) if isinstance(evidence, dict) else None


SCROLLBAR_SOURCE = "actual ScrollBar runtime properties and current visual subtree"
SCROLLBAR_THUMB_SOURCE = "actual Thumb visual ancestry to ScrollBar and current template subtree identities"


def scrollbar_templates(raw, by_id, unmeasured):
    """Verify current object ancestry before assigning a Thumb's semantic owner."""
    bars, thumbs = {}, {}
    for node in raw:
        evidence = node.get("scrollbar_evidence")
        if node.get("type") != "ScrollBar":
            continue
        valid = (isinstance(evidence, dict) and evidence.get("source") == SCROLLBAR_SOURCE
                 and evidence.get("complete") is True and evidence.get("template_present") is True)
        edges = evidence.get("visual_subtree") if isinstance(evidence, dict) else None
        valid = valid and isinstance(edges, list) and bool(edges)
        observed, children = {node["id"]}, defaultdict(list)
        if valid:
            for edge in edges:
                child = by_id.get(edge.get("id")) if isinstance(edge, dict) else None
                parent = edge.get("parent_id") if isinstance(edge, dict) else None
                index = edge.get("child_index") if isinstance(edge, dict) else None
                if (not child or child["id"] in observed or parent not in observed
                        or child.get("parent") != parent or type(index) is not int or index < 0
                        or child.get("render_sibling_order") != index
                        or edge.get("same_parent_object") is not True or edge.get("captured_parent_matches") is not True):
                    valid = False
                    break
                observed.add(child["id"])
                children[parent].append(child["id"])
                if index != len(children[parent]) - 1:
                    valid = False
                    break
            roots = children.get(node["id"], [])
            actual_thumbs = [edge["id"] for edge in edges if by_id[edge["id"]]["type"] == "Thumb"] if valid else []
            valid = (valid and evidence.get("template_roots") == roots and bool(roots)
                     and evidence.get("thumb_ids") == actual_thumbs
                     and all([child["id"] for child in sorted((child for child in raw if child.get("parent") == parent),
                                                             key=lambda child: child.get("render_sibling_order", -1))] == ids
                             for parent, ids in children.items()))
        if not valid:
            if not node.get("hidden_reason"):
                unmeasured.append({"id": node["id"], "property": "scrollbar.template_ownership",
                                   "reason": "Current ScrollBar template object identities and render-tree ancestry are incomplete"})
            continue
        bars[node["id"]] = evidence
        edge_by_id = {edge["id"]: edge for edge in edges}
        for thumb_id in evidence["thumb_ids"]:
            thumb = by_id[thumb_id]
            proof = thumb.get("scrollbar_thumb_evidence")
            path, current = [], thumb_id
            while current != node["id"]:
                edge = edge_by_id[current]
                path.insert(0, edge)
                current = edge["parent_id"]
            if (isinstance(proof, dict) and proof.get("source") == SCROLLBAR_THUMB_SOURCE
                    and proof.get("complete") is True and proof.get("owner_id") == node["id"]
                    and proof.get("path") == path and not thumb.get("resize_handle_evidence")):
                thumbs[thumb_id] = node["id"]
            elif not thumb.get("hidden_reason"):
                unmeasured.append({"id": thumb_id, "property": "scrollbar.thumb_ownership",
                                   "reason": "Thumb has no reciprocal current ScrollBar template ancestry; no role is inferred from its name"})
    return bars, thumbs


def scrollbar_state(node, kind, bars, thumbs, witness, paired, unmeasured):
    owner_id = thumbs.get(node["id"]) if kind == "scrollbar-thumb" else node["id"]
    evidence = bars.get(owner_id, {})
    orientation = evidence.get("orientation")
    if orientation not in {"horizontal", "vertical"}:
        orientation = None
        unmeasured.append({"id": node["id"], "property": "state.orientation", "reason": "No measured ScrollBar Orientation"})
    provider = paired.get(owner_id) if kind == "scrollbar-thumb" else witness
    actual = provider.get("range_value") if provider else None
    native_range = evidence.get("range")
    valid = isinstance(actual, dict) and isinstance(native_range, dict)
    valid = valid and all(finite(actual.get(key)) and actual[key] == native_range.get(key)
                          for key in ("minimum", "maximum", "value"))
    valid = valid and actual["minimum"] <= actual["value"] <= actual["maximum"]
    normalized = None
    if valid:
        span = actual["maximum"] - actual["minimum"]
        if finite(span):
            normalized = (actual["value"] - actual["minimum"]) / span if span else 0
    if normalized is None:
        unmeasured.append({"id": node["id"], "property": "state.scroll_position",
                           "reason": "Independent UIA range and actual ScrollBar range are absent, invalid or disagree; no position is inferred"})
    return {"orientation": orientation, "scroll_position": normalized}, {
        "owner_id": owner_id, "xaml": copy.deepcopy(evidence),
        "uia_id": provider.get("id") if provider else None, "uia_range": copy.deepcopy(actual),
        "quantity": "Normalized actual range value, never a source for paint geometry"}


def scrollbar_page_hit_regions(raw, bars, by_id):
    """Nonpainted template RepeatButtons are input regions of the scrollbar."""
    children = defaultdict(list)
    for node in raw:
        children[node.get("parent")].append(node)

    def subtree(node):
        yield node
        for child in children[node["id"]]:
            yield from subtree(child)

    def no_visible_paint(node):
        if node.get("hidden_reason"):
            return True
        if node.get("text") != "" or node.get("icon") or node.get("type") in ICON_TYPES | {"Image"} | AVATAR_TYPES:
            return False
        if node.get("paint_kind") == "template":
            return bool(children[node["id"]])
        if node.get("paint_kind") not in {"rectangle", "rounded-rectangle"}:
            return False
        style = node.get("style", {})
        bg, border = style.get("background"), style.get("border_color")
        return (isinstance(bg, list) and len(bg) == 4 and all(finite(c) for c in bg) and bg[3] == 0
                and finite(style.get("border_width"))
                and (style["border_width"] == 0 or isinstance(border, list) and len(border) == 4
                     and all(finite(c) for c in border) and border[3] == 0)
                and style.get("shadow") == [] and style.get("background_image") == "none")

    result = {}
    for node in raw:
        proof = node.get("scrollbar_page_hit_evidence")
        if (node.get("type") != "RepeatButton" or not isinstance(proof, dict)
                or proof.get("source") != "Actual RepeatButton object in current ScrollBar template subtree"
                or proof.get("owner_id") not in bars or node.get("interaction_evidence", {}).get("is_tab_stop") is not False):
            continue
        owner = proof["owner_id"]
        edges = {edge["id"]: edge for edge in bars[owner]["visual_subtree"]}
        path, current = [], node["id"]
        while current in edges:
            edge = edges[current]
            path.insert(0, edge)
            current = edge["parent_id"]
        region_nodes = list(subtree(node))
        if current == owner and proof.get("path") == path and all(no_visible_paint(child) for child in region_nodes):
            result[node["id"]] = (owner, region_nodes)
    return result


def scrollbar_paint_measurement(node, kind, layers, fragments, masks, template_verified):
    """Project only simple actual template primitives; never infer a native curve.

    The canonical box is the measured paint primitive's border box (or the
    transparent usable track region), not its alpha/ink envelope. These are
    separately named quantities in the receipt. CornerRadius on a WinUI Border
    does not itself establish the corresponding CSS curve, so nonzero native
    radii remain unresolved, even when its box/brush are completely measured.
    """
    receipt = {"hit_bounds": copy.deepcopy(node.get("bounds")),
               "source": "Actual current ScrollBar/Thumb template render descendants",
               "layers": [{"raw": copy.deepcopy(p), "visible_fragments": copy.deepcopy(fragments.get(p["id"])),
                           "occlusion_masks": copy.deepcopy(masks.get(p["id"], []))} for p in layers],
               "canonical_bounds": None, "canonical_visible_bounds": None, "canonical_style": None,
               "bounds_quantity": None, "fill_envelope": None, "css_paint_equivalence": None,
               "measurement_scope": "Native simple primitive properties and geometry; no reference values or pixel equivalence are asserted"}
    issues = []

    def fail(reason, prop="style.scrollbar_paint"):
        issues.append({"id": node["id"], "property": prop, "reason": reason})

    if not template_verified or not layers:
        fail("Actual ScrollBar template ownership or its visible paint primitives are incomplete")
        return receipt, issues
    contributors, primitives = [], []
    for layer in layers:
        if layer.get("paint_kind") not in {"rectangle", "rounded-rectangle"} or layer.get("type") not in {"Grid", "Border", "ContentPresenter"}:
            fail("Scrollbar paint contains an unsupported actual primitive: " + str(layer.get("type")))
            continue
        style = layer.get("style", {})
        if (style.get("paint_diagnostics") or style.get("background_image") != "none"
                or style.get("shadow") != [] or not finite(layer.get("opacity")) or not 0 <= layer["opacity"] <= 1):
            fail("Scrollbar primitive has unknown brush, shadow or accumulated opacity")
            continue
        brush_proof = style.get("brush_evidence", {})
        if not isinstance(brush_proof, dict):
            fail("Scrollbar primitive has no actual brush evidence")
            continue
        solid = True
        for prop, role in (("background", "background"), ("border_color", "border")):
            color, proof = style.get(prop), brush_proof.get(role)
            solid = solid and (isinstance(color, list) and len(color) == 4 and all(finite(c) and 0 <= c <= 255 for c in color)
                              and isinstance(proof, dict) and proof.get("type") in {None, "Microsoft.UI.Xaml.Media.SolidColorBrush"}
                              and proof.get("solid_rgba") == color)
        widths, radii = style.get("border_widths"), style.get("corner_radii")
        if (not solid or not isinstance(widths, list) or len(widths) != 4 or not all(finite(w) and w >= 0 for w in widths)
                or not isinstance(radii, list) or len(radii) != 4 or not all(finite(r) and r >= 0 for r in radii)):
            fail("Scrollbar primitive has no complete actual solid-brush, border or radius properties")
            continue
        primitives.append(layer)
        if painted(style["background"]) or painted(style["border_color"]) and any(widths):
            contributors.append(layer)
    if issues:
        return receipt, issues
    if len(contributors) > 1:
        fail("Multiple actual scrollbar paint primitives cannot be collapsed into one canonical background/border")
        return receipt, issues
    if contributors:
        source = contributors[0]
        quantity = "paint-primitive-border-box"
    elif kind == "scrollbar":
        # A fully transparent track is still an actual usable scroll region.
        # Select its verified template root, not a bounding union or thumb ratio.
        roots = node.get("scrollbar_evidence", {}).get("template_roots", [])
        candidates = [p for p in primitives if p["id"] in roots and p.get("bounds") == node.get("bounds")]
        if len(candidates) != 1:
            fail("Transparent scrollbar has no unique actual template root at its usable region bounds")
            return receipt, issues
        source, quantity = candidates[0], "transparent-usable-track-region"
    else:
        fail("Thumb template has no measured nontransparent paint primitive")
        return receipt, issues
    style, bounds, transform = source["style"], source.get("bounds"), source.get("transform", {})
    local = source.get("local_bounds")
    receipt["paint_source"] = source["id"]
    receipt["primitive_outer_bounds"] = copy.deepcopy(bounds)
    receipt["native_corner_radii"] = copy.deepcopy(style["corner_radii"])
    # Limit this branch to actual translation-only geometry. Transformed strokes,
    # rounded clipping and partial occlusion need their own measured quantities.
    if (not positive(bounds) or not positive(local) or not all(finite(transform.get(k)) for k in ("m11", "m12", "m21", "m22", "offset_x", "offset_y"))
            or [transform[k] for k in ("m11", "m12", "m21", "m22")] != [1, 0, 0, 1]
            or bounds != {"x": local["x"] + transform["offset_x"], "y": local["y"] + transform["offset_y"],
                          "width": local["width"], "height": local["height"]}
            or source.get("axis_aligned_transform") is not True or source.get("visible_bounds") != bounds
            or source.get("clip") is not None or masks.get(source["id"])):
        fail("Scrollbar paint has transformed, clipped or occluded geometry outside the measured simple-primitive branch")
        return receipt, issues
    widths = style["border_widths"]
    layout_proof = source.get("scrollbar_layout_evidence")
    rounding = layout_proof.get("use_layout_rounding") if isinstance(layout_proof, dict) else None
    if rounding is not False and any(widths):
        fail("Actual layout rounding is enabled or unmeasured; effective border geometry is not substituted with requested widths")
        return receipt, issues
    sizing = source.get("background_sizing") if source["type"] != "Grid" else "OuterBorderEdge"
    if sizing not in {"OuterBorderEdge", "InnerBorderEdge"}:
        fail("Actual scrollbar primitive BackgroundSizing is not measured")
        return receipt, issues
    fill = copy.deepcopy(bounds)
    if sizing == "InnerBorderEdge":
        top, right, bottom, left = widths
        fill = {"x": bounds["x"] + left, "y": bounds["y"] + top,
                "width": max(0, bounds["width"] - left - right), "height": max(0, bounds["height"] - top - bottom)}
    receipt["fill_envelope"] = {"bounds": fill, "quantity": "Geometric background-fill envelope before rounded-corner clipping; not an observed alpha mask"}
    receipt["canonical_bounds"] = copy.deepcopy(bounds)
    receipt["canonical_visible_bounds"] = copy.deepcopy(source["visible_bounds"])
    receipt["bounds_quantity"] = quantity
    fields = ("background", "border_color", "border_width", "border_widths", "border_colors", "border_styles",
              "corner_radius", "corner_radii", "opacity", "shadow", "background_image")
    receipt["canonical_style"] = {key: copy.deepcopy(style.get(key)) for key in fields}
    if any(style["corner_radii"]):
        # Microsoft source distinguishes inner/outer radii and partitions
        # overlaps per edge, unlike CSS's common scaling factor. That source
        # explains why a property value is insufficient; it is not substituted
        # for an actual live-render geometry receipt:
        # https://github.com/microsoft/microsoft-ui-xaml/blob/0a03f68d586d1c100f753ca3221597c3ee550f4a/dxaml/xcp/core/core/elements/geometry.cpp
        receipt["canonical_style"]["corner_radius"] = receipt["canonical_style"]["corner_radii"] = None
        fail("Actual nonzero WinUI Border CornerRadius is retained; its live rendered curve and CSS radius equivalence are unmeasured", "style.corner_radius")
    else:
        receipt["css_paint_equivalence"] = "Simple native rectangle properties projected without native-radius conversion; equality remains for the matcher to test"
    receipt["geometry_status"] = "measured-simple-primitive-border-box"
    receipt["style_status"] = "partial-native-curve-unresolved" if issues else "measured-simple-rectangle-properties"
    return receipt, issues


def project_background_pattern(element, node):
    """Forward only an independently captured background raster measurement.

    Current ImageBrush captures have real pixels but not full clipping and
    foreground-transmission masks. Preserve their null background_image and
    existing unsupported-brush diagnostics. A complete future capture can use
    the explicit image-brush descriptor without pretending it is a gradient.
    """
    measurement = node.get("background_pattern_measurement")
    if measurement is None:
        return
    element["evidence"]["background_pattern_measurement"] = copy.deepcopy(measurement)
    brushes = element["evidence"].get("brush_evidence")
    brush = brushes.get("background") if isinstance(brushes, dict) else None
    if not isinstance(brush, dict) or brush.get("type") != "Microsoft.UI.Xaml.Media.ImageBrush":
        return
    candidate = copy.deepcopy(element)
    candidate["style"]["background_image"] = {"kind": "image-brush", "source_id": element["id"]}
    try:
        issue = pattern_measurement_issue(captured_pattern(candidate))
    except MeasurementError:
        return
    if issue is None:
        element["style"]["background_image"] = candidate["style"]["background_image"]


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
        return class_name in {"ToggleButton", "ToggleSwitch", "NativeOverviewToggle"} and any(isinstance(p, str) and "Toggle" in p for p in node.get("supported_patterns", []))
    if control_type == "ListItem" and kind == "tab":
        return class_name == "SelectorBarItem"
    return kind in UIA_KINDS.get(control_type, set())


def measured_text_boxes(boxes):
    # These are eligible measured rectangle candidates, not a replacement for
    # the source field. Explicit null/provider failures are retained separately
    # in range diagnostics and continue to fail extraction coverage.
    if not isinstance(boxes, list):
        return []
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
        if node["type"] not in {"TextBlock", "RichTextBlock", "WorkspaceCodeView"} or not isinstance(runs, list) or not runs or node.get("hidden_reason"):
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
                        font_weight_configuration=copy.deepcopy(run.get("font_weight_configuration")),
                        text_run_source={"owner": node["id"], "index": index, "start_offset": run.get("start_offset"),
                                         "end_offset": run.get("end_offset")},
                        layout={"wrap": node["layout"].get("wrap"), "truncation": node["layout"].get("truncation"),
                                **{key: copy.deepcopy(node["layout"].get(key)) for key in
                                   ("break_strategy_version", *BREAK_FIELDS, "line_break_configuration")},
                                "line_count": len(text_line_boxes(boxes)) if boxes else None,
                                "actual_trimming": copy.deepcopy(node["layout"].get("actual_trimming")),
                                "character_boxes": boxes, "character_boxes_coordinate_space": "content-window",
                                "rich_text_runs": [copy.deepcopy(run)]})
            if boxes and not positive(clipped):
                leaf["hidden_reason"] = "glyph rectangles fully outside the measured text-owner clip"
            result.append(leaf)
    return result


def project_inline_reading_order(raw, unmeasured):
    """Interleave measured Runs and real inline child subtrees in collection order.

    Paint order and source parentage remain unchanged. Missing/ambiguous object
    identity never causes a geometry-based sort or a partial guessed ordering.
    """
    by_id = {node["id"]: node for node in raw}
    children = defaultdict(list)
    for node in raw:
        children[node.get("parent")].append(node)
    ordered = {}
    for owner in raw:
        evidence = owner.get("inline_order_evidence")
        if evidence is None or owner.get("hidden_reason"):
            continue
        entries = evidence.get("entries") if isinstance(evidence, dict) else None
        if not isinstance(entries, list) or not any(isinstance(entry, dict) and entry.get("type") == "InlineUIContainer" for entry in entries):
            continue
        reason = None
        if evidence.get("source") != "actual InlineCollection order and InlineUIContainer.Child object identity" or evidence.get("complete") is not True:
            reason = "Actual inline collection/child identity evidence is incomplete"
        proposed, provenance = [], {}
        runs = owner.get("layout", {}).get("rich_text_runs", [])
        for ordinal, entry in enumerate(entries):
            if reason:
                break
            if not isinstance(entry, dict) or type(entry.get("ordinal")) is not int or entry["ordinal"] != ordinal:
                reason = "Actual inline ordinal is absent or inconsistent"; break
            path = entry.get("collection_path")
            if not isinstance(path, list) or not path or any(type(index) is not int or index < 0 for index in path):
                reason = "Actual InlineCollection index path is missing"; break
            if not all(type(entry.get(key)) is int for key in ("start_offset", "end_offset")) or entry["end_offset"] < entry["start_offset"]:
                reason = "Actual inline TextPointer offsets are missing"; break
            child = None
            if entry.get("type") in {"Run", "LineBreak"}:
                index = entry.get("run_index")
                if type(index) is not int or not isinstance(runs, list) or not 0 <= index < len(runs):
                    reason = "Inline Run has no corresponding measured text range"; break
                run = runs[index]
                if any(run.get(key) != entry.get(key) for key in ("type", "start_offset", "end_offset")):
                    reason = "Inline sequence does not describe the measured Run"; break
                if run.get("type") == "LineBreak" or not run.get("text"):
                    continue  # No separate painted text element is generated.
                child = by_id.get(owner["id"] + ":run:" + str(index))
            elif entry.get("type") == "InlineUIContainer":
                child = by_id.get(entry.get("child_id"))
                identity = child.get("inline_child_evidence") if child else None
                if (entry.get("child_source") != "actual InlineUIContainer.Child object identity" or not isinstance(identity, dict)
                        or identity.get("source") != "actual InlineUIContainer.Child object identity" or identity.get("owner_id") != owner["id"]
                        or any(identity.get(key) != entry.get(key) for key in ("ordinal", "collection_path", "start_offset", "end_offset"))):
                    reason = "Inline child has no matching actual object identity record"; break
            else:
                reason = "Unsupported actual inline element type"; break
            if not child or child.get("parent") != owner["id"] or child["id"] in provenance:
                reason = "Inline child is absent, repeated, or not a direct rendered child of its measured owner"; break
            proposed.append(child)
            provenance[child["id"]] = {"source": evidence["source"], "owner_id": owner["id"], "entry": copy.deepcopy(entry)}
        if reason is None and {node["id"] for node in proposed} != {node["id"] for node in children[owner["id"]]}:
            reason = "Actual rendered children are not completely accounted for by the inline collection"
        if reason:
            unmeasured.append({"id": owner["id"], "property": "reading_order.inline_collection", "reason": reason})
            continue
        ordered[owner["id"]] = proposed
        for node in proposed:
            node["inline_sequence_evidence"] = provenance[node["id"]]
    if not ordered:
        return raw
    result, visited = [], set()
    def walk(node):
        if node["id"] in visited:
            return
        visited.add(node["id"]); result.append(node)
        for child in ordered.get(node["id"], children[node["id"]]):
            walk(child)
    for node in raw:
        if node.get("parent") not in by_id:
            walk(node)
    for node in raw:
        walk(node)
    return result


def markdown_fenced_blocks(raw, by_id, unmeasured):
    """Recognize only production-registered fenced-code objects in this tree.

    This changes the containing block's semantic kind, never its measured
    geometry/paint or the independently emitted code text. A generic painted
    Border, monospaced font, Tag or matching source string is not a code block.
    """
    result = set()
    for node in raw:
        evidence = node.get("markdown_code_evidence")
        if evidence is None or node.get("hidden_reason"):
            continue
        valid = isinstance(evidence, dict)
        scroller_id = evidence.get("scroller_id") if valid else None
        text_id = evidence.get("text_id") if valid else None
        scroller = by_id.get(scroller_id) if isinstance(scroller_id, str) else None
        text = by_id.get(text_id) if isinstance(text_id, str) else None
        valid = (valid and node.get("type") == "Border"
                 and evidence.get("source") == "actual MarkdownSemantic.RegisterFencedCode object identities"
                 and evidence.get("kind") == "fenced-code" and evidence.get("complete") is True
                 and evidence.get("border_child_is_registered_scroller") is True
                 and evidence.get("scroller_content_is_registered_text") is True
                 and scroller is not None and scroller.get("type") == "ScrollViewer"
                 and scroller.get("parent") == node["id"]
                 and text is not None and text.get("type") == "TextBlock"
                 and text.get("declared_content_owner") == scroller_id
                 and text.get("declared_content_source") == "ContentControl.Content"
                 and scroller.get("markdown_code_scroller_evidence") == {
                     "source": "actual MarkdownSemantic.RegisterFencedCode scroller object identity",
                     "owner_id": node["id"], "text_id": text_id}
                 and text.get("markdown_code_text_evidence") == {
                     "source": "actual MarkdownSemantic.RegisterFencedCode text object identity",
                     "owner_id": node["id"], "scroller_id": scroller_id})
        if valid:
            current = text
            visited = set()
            while current and current["id"] != scroller_id and current["id"] not in visited:
                visited.add(current["id"])
                current = by_id.get(current.get("parent"))
            valid = current is not None and current["id"] == scroller_id
        if valid:
            result.add(node["id"])
        else:
            unmeasured.append({"id": node["id"], "property": "semantic.markdown_fenced_code",
                               "reason": "Production fenced-code registration lacks reciprocal actual content identities or its current rendered ancestry"})
    return result


def state_dot_paint_layers(raw, by_id, unmeasured):
    """Resolve a production indicator's exact current paint objects, not shapes nearby."""
    result = {}
    for node in raw:
        evidence = node.get("state_dot_evidence")
        if node.get("hidden_reason") or node.get("type") != "NativeStateDotView" and evidence is None:
            continue
        valid = isinstance(evidence, dict)
        layers = evidence.get("layers") if valid else None
        current = evidence.get("current_children") if valid else None
        valid = (valid and node.get("type") == "NativeStateDotView"
                 and evidence.get("source") == "actual NativeStateDotView owned paint objects and current Children order"
                 and evidence.get("complete") is True and evidence.get("current_children_same_objects") is True
                 and isinstance(layers, list) and len(layers) == 2
                 and isinstance(current, list) and len(current) == 2
                 and all(isinstance(eid, str) for eid in current) and len(set(current)) == 2)
        actual = []
        if valid:
            for index, (layer, prop) in enumerate(zip(layers, ("Surround", "VacancyRing"))):
                child = by_id.get(current[index])
                if (not isinstance(layer, dict) or layer != {"id": current[index], "property": prop, "child_index": index}
                        or child is None or child.get("type") != "Ellipse" or child.get("parent") != node["id"]
                        or child.get("state_dot_layer_evidence") != {
                            "source": "actual NativeStateDotView owned Ellipse object identity",
                            "owner_id": node["id"], "property": prop, "child_index": index}):
                    valid = False
                    break
                actual.append(child)
            # Additional current content is neither hidden nor silently absorbed.
            if {child["id"] for child in raw if child.get("parent") == node["id"]} != set(current):
                valid = False
        if valid:
            result[node["id"]] = actual
        else:
            unmeasured.append({"id": node["id"], "property": "ownership.state_dot_paint",
                               "reason": "The production indicator's exact current children, layer order or reciprocal object identities are unverified"})
    return result


def native_label_surfaces(raw, by_id, unmeasured):
    """Identify only the Image actually owned/bound by the production label."""
    result = {}
    for node in raw:
        evidence = node.get("native_label_surface_evidence")
        if evidence is None:
            continue
        owner = by_id.get(evidence.get("owner_id")) if isinstance(evidence, dict) else None
        if (not isinstance(evidence, dict)
                or evidence.get("source") != "actual NativeLabel production Image object identity and SurfaceImageSource COM binding"
                or evidence.get("same_image_object") is not True or evidence.get("surface_binding_same_com_identity") is not True
                or evidence.get("source_type") != "Microsoft.UI.Xaml.Media.Imaging.SurfaceImageSource"
                or node.get("type") != "Image" or not owner or owner.get("type") != "NativeLabel" or node.get("parent") != owner["id"]
                or node.get("interaction_evidence", {}).get("is_hit_test_visible") is not False):
            unmeasured.append({"id": node["id"], "property": "ownership.native_label_surface", "reason": "Actual production Image identity, noninteractive state or bound SurfaceImageSource is unverified"})
            continue
        result[node["id"]] = owner["id"]
    return result


def native_label_submission(node, frame):
    """Use the current actual draw's style; retain unknown final visibility.

    A successful submitted surface and its real font callbacks are not proof
    that every glyph contributed to the desktop PNG. No hit-test/ink rectangle
    is converted to DOM text geometry here, and no requested family is used.
    """
    issues = []
    result = {"style": None, "submitted_glyph_runs": None, "frame_binding": None,
              "presentation_identity_proven": False, "visible_glyph_coverage": None}

    def gap(prop, reason):
        issues.append({"id": node.get("id"), "property": prop, "reason": reason})

    receipt = node.get("native_label_evidence")
    if not isinstance(receipt, dict) or receipt.get("source") != "NativeLabel production SurfaceImageSource / DirectWrite renderer":
        gap("style.native_label_submission", "NativeLabel has no actual production draw receipt")
        return result, issues
    state, draw = receipt.get("current_submission"), receipt.get("draw")
    revisions = (("layout_revision", "current_layout_revision"), ("surface_revision", "current_surface_revision"),
                 ("draw_ordinal", "current_draw_ordinal"))
    current = (isinstance(state, dict) and state.get("source") == "Actual NativeLabel state at receipt capture"
               and state.get("is_loaded") is True and state.get("queued") is False and state.get("rendering") is False
               and state.get("surface_binding_same_com_identity") is True and receipt.get("last_failure") is None
               and isinstance(draw, dict) and draw.get("surface_end_draw_succeeded") is True
               and all(type(draw.get(k)) is int and draw[k] >= 0 for k in ("draw_hresult", "surface_end_draw_hresult"))
               and all(type(draw.get(a)) is int and draw[a] > 0 and type(receipt.get(b)) is int and draw[a] == receipt[b] for a, b in revisions)
               and isinstance(draw.get("layout_com_identity"), str) and bool(draw["layout_com_identity"])
               and receipt.get("text") == node.get("text"))
    if not current:
        gap("style.native_label_submission", "NativeLabel draw is missing, stale, failed, pending or not bound to this text surface")
        return result, issues
    fmt = draw.get("actual_text_format")
    rgba = draw.get("brush_input_srgb_unpremultiplied_0_255")
    source_style = node.get("style") if isinstance(node.get("style"), dict) else {}
    measured = source_style.get("native_label_style_evidence")
    valid_style = (isinstance(fmt, dict)
                   and fmt.get("source") == "IDWriteTextFormat getters on the same production IDWriteTextLayout passed to Draw"
                   and finite(fmt.get("font_size")) and fmt["font_size"] > 0
                   and type(fmt.get("font_weight")) is int and 1 <= fmt["font_weight"] <= 999
                   and isinstance(rgba, list) and len(rgba) == 4 and all(finite(c) and 0 <= c <= 255 for c in rgba)
                   and isinstance(measured, dict)
                   and measured.get("source") == "Current bound NativeLabel production draw, actual TextFormat getters and D2D brush inputs"
                   and measured.get("current_submission_verified") is True
                   and all(measured.get(a) == draw[a] for a, _ in revisions)
                   and measured.get("actual_text_format") == fmt
                   and measured.get("brush_input_srgb_unpremultiplied_0_255") == rgba)
    if valid_style:
        values = {"font_size": fmt["font_size"], "font_weight": fmt["font_weight"], "foreground": copy.deepcopy(rgba)}
        if all(source_style.get(key) == value for key, value in values.items()):
            result["style"] = values
        else:
            gap("style.native_label_submission", "NativeLabel extracted style disagrees with its actual production draw inputs")
    else:
        gap("style.native_label_submission", "Actual production TextFormat getters, brush inputs or matching style receipt are incomplete")

    # Preserve exact callback records (including localized names, face/axis
    # data, inline ownership and failures). They describe submitted glyphs;
    # they do not certify the visible subset or its canonical family set.
    runs = draw.get("glyph_runs")
    if isinstance(runs, list):
        result["submitted_glyph_runs"] = copy.deepcopy(runs)
    binding = receipt.get("capture_binding")
    index = binding.get("capture_label_index") if isinstance(binding, dict) else None
    bound = (isinstance(binding, dict)
             and binding.get("source") == "Actual NativeLabel object ReferenceEquals against the capture observer label array"
             and binding.get("same_object_reference") is True and type(index) is int and index >= 0
             and isinstance(frame, dict) and binding.get("case_id") == frame.get("case_id") and bool(binding.get("case_id"))
             and frame.get("source") == "Actual NativeLabel object references observed around desktop readback")
    if bound:
        baseline = [row for row in (frame.get("baseline") if isinstance(frame.get("baseline"), list) else [])
                    if isinstance(row, dict) and type(row.get("capture_label_index")) is int and row["capture_label_index"] == index]
        draws = [row for row in (frame.get("production_draws") if isinstance(frame.get("production_draws"), list) else [])
                 if isinstance(row, dict) and type(row.get("capture_label_index")) is int and row["capture_label_index"] == index]
        bound = (len(baseline) == len(draws) == 1 and isinstance(baseline[0].get("state"), dict)
                 and all(baseline[0]["state"].get(a) == draw[a] for a, _ in revisions)
                 and baseline[0]["state"].get("surface_binding_same_com_identity") is True
                 and isinstance(draws[0].get("production_receipt"), dict)
                 and draws[0]["production_receipt"].get("draw") == draw)
        if bound:
            result["frame_binding"] = {"source": copy.deepcopy(binding), "baseline_state": copy.deepcopy(baseline[0]["state"]),
                                       "production_draw_matches": True, "frame_failure": frame.get("failure"),
                                       "checkpoints": copy.deepcopy(frame.get("checkpoints")),
                                       "presentation_identity_proven": frame.get("presentation_identity_proven")}
    if not bound:
        gap("evidence.native_label_frame_binding", "No matching actual object-reference capture index, draw revision and baseline are available")
    gap("evidence.native_label_visible_glyphs", "Current production draw evidence does not establish final PNG contribution, visible glyph ownership or equivalent text-line geometry")
    return result, issues


def native_label_text_quantity(node, geometry, fonts, submission):
    """Select complete submitted font-metric advances, never layout/hit/ink.

    The three measurement arguments are produced from this actual node, its
    unique owned Image and its capture frame by the existing independent
    readers. This quantity is source geometry; final PNG visibility remains
    unknown and none of those independent failures is removed here.
    """
    if (node.get("type") != "NativeLabel" or not isinstance(node.get("text"), str) or not node["text"]
            or node.get("native_path_line_evidence") is not None):
        return None
    receipt = node.get("native_label_evidence")
    if not isinstance(receipt, dict) or receipt.get("text") != node["text"]:
        return None
    draw = receipt.get("draw")
    binding = fonts.get("binding") if isinstance(fonts, dict) else None
    frame = submission.get("frame_binding") if isinstance(submission, dict) else None
    if (not isinstance(draw, dict) or not isinstance(binding, dict) or not isinstance(frame, dict)
            or fonts.get("status") != "measured-current-submission" or fonts.get("source_span_complete") is not True
            or submission.get("style") is None or frame.get("production_draw_matches") is not True
            or frame.get("frame_failure") is not None
            or binding.get("capture") != receipt.get("capture_binding")
            or not isinstance(binding.get("image"), dict) or binding["image"].get("owner_id") != node.get("id")
            or binding.get("layout_com_identity") != draw.get("layout_com_identity")
            or binding.get("revisions") != {key: draw.get(key) for key in ("layout_revision", "surface_revision", "draw_ordinal")}
            or not isinstance(geometry, dict)
            or geometry.get("source") != "Actual NativeLabel layout, production DWrite callbacks and bound XAML Image placement"
            or geometry.get("coordinate_space") != "content-window"):
        return None
    source = node["text"].encode("utf-16-le", "surrogatepass")
    source_length = len(source) // 2
    state = geometry.get("layout_state")
    lines = draw.get("line_metrics")
    metrics, runs = geometry.get("font_metric_advance"), draw.get("glyph_runs")
    if (fonts.get("source_utf16_length") != source_length
            or not isinstance(state, dict) or state.get("is_trimmed") is not False
            or state.get("line_metrics") != lines or not isinstance(lines, list) or len(lines) != 1 or not isinstance(lines[0], dict)
            or lines[0].get("is_trimmed") is not False or lines[0].get("length_utf16") != source_length
            or draw.get("inline_object_draws") != []
            or not isinstance(metrics, list) or not metrics or not isinstance(runs, list) or len(metrics) != len(runs)):
        return None
    boxes, visible_boxes, spans = [], [], []
    for ordinal, (metric, run) in enumerate(zip(metrics, runs)):
        if (not isinstance(metric, dict) or not isinstance(run, dict)
                or metric.get("glyph_run_ordinal") != ordinal or run.get("ordinal") != ordinal
                or metric.get("text_scope") != "layout-source" or metric.get("inline_draw_ordinal") is not None
                or run.get("from_inline_object") is not False or run.get("submitted_to_d2d") is not True
                or metric.get("quantity") != "Actual rendered face ascent/descent around actual baseline, and actual glyph advance width; excludes line leading and glyph ink"
                or metric.get("description") != run.get("description")):
            return None
        description, window = metric.get("description"), metric.get("window")
        if not isinstance(description, dict) or not isinstance(window, dict) or not positive(window.get("bounds")):
            return None
        start, length = description.get("text_position_utf16"), description.get("text_length_utf16")
        if (type(start) is not int or start < 0 or type(length) is not int or length <= 0
                or start + length > source_length or not isinstance(description.get("text"), str)
                or description["text"].encode("utf-16-le", "surrogatepass") != source[start * 2:(start + length) * 2]):
            return None
        spans.append((start, start + length))
        boxes.append(copy.deepcopy(window["bounds"]))
        visible_boxes.append(copy.deepcopy(window.get("visible_bounds")))
    cursor = 0
    for start, end in sorted(spans):
        if start != cursor:
            return None
        cursor = end
    if cursor != source_length:
        return None
    return {"source": "Complete untrimmed actual NativeLabel production font-metric advances, bound to its source, Image and capture frame",
            "quantity": "font-metric-text-advance-range", "bounds": union_boxes(boxes), "text_bounds": boxes,
            "visible_bounds": union_boxes(visible_boxes) if all(positive(box) for box in visible_boxes) else None,
            "visible_bounds_quantity": "Font-metric advance envelopes intersected with measured XAML clips; not ink or final visible pixels",
            "element_allocation": copy.deepcopy(geometry.get("element_layout")),
            "clipped_element_allocation": copy.deepcopy(geometry.get("element_clipped_layout")),
            "source_span_complete": True, "source_utf16_length": source_length,
            "glyph_run_ordinals": list(range(len(runs))), "source_ranges_utf16": [[start, end] for start, end in spans],
            "binding_evidence": "evidence.native_label_fonts.binding",
            "final_png_attribution_proven": False, "visible_glyph_coverage": None}


def run_font_witnesses(uia_nodes, owner, glyph_boxes):
    """Match actual UIA format ranges to the measured leaf's glyph positions."""
    candidates = []
    original_text = owner.get("text_before_run_projection", owner.get("text", ""))
    document_evidence = owner.get("layout", {}).get("document_evidence", {})
    measured_documents = {value for value in (original_text, document_evidence.get("whole_story"),
                                               document_evidence.get("whole_story_use_lf"))
                          if isinstance(value, str) and value}
    for candidate in uia_nodes:
        if candidate.get("control_type") not in {"ControlType.Text", "ControlType.Document"} or not positive(owner.get("bounds")):
            continue
        document = (candidate.get("text_pattern") or {}).get("document") or {}
        if not original_text or not measured_documents.intersection((candidate.get("name"), document.get("text"))):
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


def uia_text_range_failures(nodes, unmeasured, nonvisible):
    """Retain failed managed/COM observations independently; neither repairs the other."""
    failures = []

    def visit_range(node, value, path):
        if not isinstance(value, dict):
            return
        unknown = [key for key in ("bounds", "managed_bounds")
                   if key in value and not isinstance(value[key], list)]
        if unknown or value.get("bounds_status") == "error" or value.get("bounds_error") is not None:
            issue = {"id": node["id"], "property": "UIA text_range.bounds", "range_path": path,
                     "reason": "Range rectangle measurement failed or is unknown; no empty measurement or independent COM replacement is inferred",
                     "unknown_fields": unknown, "range_evidence": copy.deepcopy(value)}
            failures.append(copy.deepcopy(issue))
            if node.get("state", {}).get("offscreen") is True:
                nonvisible.append(dict(issue, source="UIA", applicability="Provider measured this owning node IsOffscreen=true"))
            else:
                unmeasured.append(issue)
        runs = value.get("format_runs")
        for index, run in enumerate(runs if isinstance(runs, list) else []):
            visit_range(node, run, path + ".format_runs[" + str(index) + "]")

    def visit_pattern(node, pattern, path):
        if not isinstance(pattern, dict):
            return
        visit_range(node, pattern.get("document"), path + ".document")
        ranges = pattern.get("visible_ranges")
        for index, value in enumerate(ranges if isinstance(ranges, list) else []):
            visit_range(node, value, path + ".visible_ranges[" + str(index) + "]")

    for node in nodes:
        pattern = node.get("text_pattern")
        visit_pattern(node, pattern, "text_pattern")
        if isinstance(pattern, dict):
            visit_pattern(node, pattern.get("native_com"), "text_pattern.native_com")
    return failures


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
        if (node["type"] in PAINT_ONLY_TYPES or measured_runtime_type(node, "is_panel") is True) and focusable is False and isinstance(patterns, list):
            return False, "Paint-only XAML element; UIA reports no action pattern and IsKeyboardFocusable=false"
        return None, "UIA interaction applicability is not completely measured"
    interaction = node.get("interaction_evidence", {})
    if interaction.get("is_control") is False and (node["type"] in PAINT_ONLY_TYPES or measured_runtime_type(node, "is_panel") is True):
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


def transparent_uia_ownership(uia_nodes, raw, scrollbar_thumbs=None):
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
                      if semantic_control_kind(node, scrollbar_thumbs)
                      and node["type"] == native_class
                      and uia_kind_matches(provider, semantic_control_kind(node, scrollbar_thumbs))
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


DIALOG_SURFACE_SOURCE = "Actual NativeContentDialog protected GetTemplateChild objects from its applied native ControlTemplate"


def ellipse_circle_geometry(node, stroke_width):
    """Derive only the simple circular primitive from bound, actual SDK inputs.

    WinUI 1.6.9 GetOutlineRect deflates by half the centered stroke;
    CEllipse::UpdateRenderGeometry halves that box for the centerline radii.
    This is a native geometry parameter, not a sampled raster/visible-ink bound.
    Caller must first establish the actual solid, undashed, translation-only
    stroke. Unsupported geometry remains unknown instead of copying layout/2.
    """
    geometry = node.get("shape_geometry_evidence")
    if not isinstance(geometry, dict):
        return None, "Actual Shape.Stretch and Ellipse geometry input receipt is missing"
    if (geometry.get("source") != "actual Ellipse layout and Shape inputs"
            or geometry.get("owner_id") != node.get("id")
            or geometry.get("runtime_type") != "Microsoft.UI.Xaml.Shapes.Ellipse"
            or type(geometry.get("stretch_value")) is not int
            or (geometry.get("stretch"), geometry.get("stretch_value")) not in (("Fill", 1), ("Uniform", 2))
            or geometry.get("stroke_is_null") is not False
            or not finite(geometry.get("stroke_thickness"))
            or geometry.get("stroke_thickness") != stroke_width):
        return None, "Ellipse geometry inputs lack a same-owner exact primitive, supported Stretch enum or matching present Stroke"
    owner = node.get("outline_owner_evidence") or {}
    composition = owner.get("composition") or {}
    children = owner.get("children") or {}
    if (owner.get("source") != "winui-own-outline-v1" or owner.get("owner_id") != node.get("id")
            or owner.get("runtime_type") != "Microsoft.UI.Xaml.Shapes.Ellipse"
            or owner.get("own_paint_contract") != "native-shape-fill-and-stroke" or owner.get("status") != "measured"
            or composition.get("status") != "measured" or composition.get("child_visual_present") is not False
            or composition.get("shadow_present") is not False
            or children.get("status") != "measured" or children.get("complete") is not True or children.get("items") != []):
        return None, "Ellipse geometry owner is unbound or has unresolved/additional composition or child paint"
    diameter, height = geometry.get("actual_width"), geometry.get("actual_height")
    if (not finite(diameter) or not finite(height) or diameter != height
            or diameter <= 0 or not finite(stroke_width) or not 0 < stroke_width < diameter / 2):
        return None, "Ellipse circle requires a positive square and nondegenerate centered stroke/inner radius"

    # Core geometry uses XFLOAT. Preserve its arithmetic, and do not silently
    # treat an unrepresentable recorded Double as the actual native float input.
    def f32(value):
        return struct.unpack("<f", struct.pack("<f", value))[0]

    try:
        if f32(diameter) != diameter or f32(stroke_width) != stroke_width:
            return None, "Actual geometry inputs are not exactly representable by this SDK's XFLOAT geometry"
        inset = f32(stroke_width * 0.5)
        centerline_diameter = f32(diameter - stroke_width)
        centerline_radius = f32(centerline_diameter * 0.5)
        outer_radius = f32(centerline_radius + inset)
        inner_radius = f32(centerline_radius - inset)
    except (OverflowError, struct.error):
        return None, "Ellipse geometry inputs exceed the SDK XFLOAT range"
    if (not all(finite(v) and v > 0 for v in (inset, centerline_radius, inner_radius, outer_radius))
            or outer_radius * 2 != diameter):
        return None, "Rounded or degenerate native outline arithmetic does not establish this exact circular outer box"

    matrix = node.get("transform") or {}
    stroke = node.get("stroke_evidence") or {}
    x, y = matrix.get("offset_x"), matrix.get("offset_y")
    if not finite(x) or not finite(y):
        return None, "Ellipse window origin is unmeasured"
    expected_box = {"x": x, "y": y, "width": diameter, "height": diameter}
    if (node.get("bounds") != expected_box or node.get("visible_bounds") != expected_box
            or node.get("local_bounds") != {"x": 0, "y": 0, "width": diameter, "height": diameter}
            or node.get("axis_aligned_transform") is not True
            or "clip" not in node or node["clip"] is not None
            or "hidden_reason" not in node or node["hidden_reason"] is not None
            or stroke.get("source_extent") != {"x": diameter, "y": diameter}
            or stroke.get("origin") != {"x": x, "y": y}
            or stroke.get("axis_endpoint_x") != {"x": x + diameter, "y": y}
            or stroke.get("axis_endpoint_y") != {"x": x, "y": y + diameter}):
        return None, "Ellipse local/window extents, full visibility or actual transform-axis endpoints are not consistent"
    ancestor_clip = node.get("ancestor_clip")
    if (not isinstance(ancestor_clip, dict)
            or not all(finite(ancestor_clip.get(k)) for k in ("x", "y", "width", "height"))
            or ancestor_clip["x"] > x or ancestor_clip["y"] > y
            or ancestor_clip["x"] + ancestor_clip["width"] < x + diameter
            or ancestor_clip["y"] + ancestor_clip["height"] < y + diameter):
        return None, "Ellipse ancestor clip is missing or does not contain the full actual circular border box"
    return {
        "source": "Actual Ellipse inputs interpreted by fixed WinUI 1.6.9 primitive geometry",
        "sdk_source_commit": "da699b040bddc2a6adf660512a7c6db8a96bfbe3",
        "sdk_source": [
            "https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/core/elements/shape.cpp#L841",
            "https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/core/elements/ellipse.cpp#L101"],
        "arithmetic": "XFLOAT outline inset = stroke/2; centerline diameter = actual diameter-stroke; centerline radius = centerline diameter/2; outer radius = centerline radius+inset",
        "coordinate_space": "window", "center": {"x": x + outer_radius, "y": y + outer_radius},
        "centerline_bounds": {"x": x + inset, "y": y + inset,
                              "width": centerline_diameter, "height": centerline_diameter},
        "centerline_radius": centerline_radius, "outer_radius": outer_radius, "inner_radius": inner_radius,
        "outer_bounds": expected_box,
        "scope": "Native primitive circular outer border radius only; not sampled ink, antialiasing, same-frame or screenshot equivalence",
    }, None


def project_ellipse_border(element, node, unmeasured):
    """Classify a measured Ellipse boundary stroke without inventing its contour.

    Shape.Stroke is captured as foreground, whereas a closed state-dot boundary
    uses the border paint fields. This is not a rule for Paths, Lines or glyphs.
    Native default CornerRadius(0) is not a measured radius. Only a complete
    actual Ellipse geometry receipt can establish the supported circular case.
    """
    if node.get("type") != "Ellipse":
        return
    raw_style = node.get("style") or {}
    brushes = raw_style.get("brush_evidence")
    brush = brushes.get("foreground") if isinstance(brushes, dict) else None
    if isinstance(brush, dict) and "type" in brush and brush["type"] is None:
        return  # A measured absent Stroke does not create a boundary paint.
    stroke = node.get("stroke_evidence")
    style = element["style"]
    proof = {"source": "Actual Ellipse Shape.Stroke brush and measured stroke-axis receipt",
             "runtime_type": (node.get("outline_owner_evidence") or {}).get("runtime_type"),
             "raw_style": copy.deepcopy(raw_style), "stroke_evidence": copy.deepcopy(stroke),
             "shape_geometry_evidence": copy.deepcopy(node.get("shape_geometry_evidence")),
             "local_bounds": copy.deepcopy(node.get("local_bounds")),
             "visible_bounds": copy.deepcopy(node.get("visible_bounds")),
             "clip": copy.deepcopy(node.get("clip")), "ancestor_clip": copy.deepcopy(node.get("ancestor_clip")),
             "transform": copy.deepcopy(node.get("transform")),
             "bounds": copy.deepcopy(node.get("bounds")), "stroke_fields_measured": False,
             "contour_measured": False,
             "contour_reason": "Actual Shape.Stretch and current rendered Ellipse contour are not captured; layout extents do not establish a CSS radius"}
    element["evidence"]["ellipse_border"] = proof
    style["corner_radius"] = style["corner_radii"] = None
    color, width = raw_style.get("foreground"), raw_style.get("stroke_width")
    pattern = stroke.get("raw_pattern") if isinstance(stroke, dict) else None
    matrix = node.get("transform")
    supported = (
        measured_runtime_type(node, "is_shape") is True and node.get("paint_kind") == "ellipse"
        and proof["runtime_type"] == "Microsoft.UI.Xaml.Shapes.Ellipse"
        and isinstance(brush, dict) and brush.get("type") == "Microsoft.UI.Xaml.Media.SolidColorBrush"
        and isinstance(color, list) and len(color) == 4 and all(finite(c) and 0 <= c <= 255 for c in color)
        and brush.get("solid_rgba") == color and finite(brush.get("opacity")) and 0 <= brush["opacity"] <= 1
        and finite(width) and width >= 0 and isinstance(stroke, dict)
        and stroke.get("source") == "Shape.StrokeThickness and full actual Shape.TransformToVisual(content-root) layout-axis endpoints; unit-difference diagnostics retained"
        and finite(stroke.get("raw_width")) and stroke["raw_width"] >= 0
        and stroke.get("scale_x") == stroke.get("scale_y") == 1
        and stroke.get("basis_x") == {"x": 1, "y": 0} and stroke.get("basis_y") == {"x": 0, "y": 1}
        and width == stroke["raw_width"]
        and isinstance(matrix, dict) and all(finite(matrix.get(k)) for k in ("m11", "m12", "m21", "m22", "offset_x", "offset_y"))
        and [matrix[k] for k in ("m11", "m12", "m21", "m22")] == [1, 0, 0, 1]
        and isinstance(pattern, dict) and pattern.get("dash_array") == []
        and raw_style.get("stroke_dash") == [])
    fields = ("border_color", "border_width", "border_widths", "border_colors", "border_styles")
    if not supported:
        for field in fields:
            style[field] = None
        unmeasured.append({"id": node["id"], "property": "style.ellipse_border",
                           "reason": "Ellipse boundary lacks a bound solid undashed stroke with a measured translation-only width; no CSS border is inferred"})
        unmeasured.append({"id": node["id"], "property": "style.corner_radius", "reason": proof["contour_reason"]})
        return
    style.update(border_color=copy.deepcopy(color), border_width=width, border_widths=[width] * 4,
                 border_colors=[copy.deepcopy(color) for _ in range(4)],
                 border_styles=["solid" if width > 0 else "none"] * 4)
    proof["stroke_fields_measured"] = True
    proof["projected_fields"] = list(fields)
    proof["quantity"] = "Closed Ellipse boundary stroke color/thickness only; no outline placement, radius or raster equivalence asserted"
    contour, reason = ellipse_circle_geometry(node, width)
    proof["geometry_derivation"] = contour
    if contour is None:
        proof["contour_reason"] = reason
        unmeasured.append({"id": node["id"], "property": "style.corner_radius", "reason": reason})
        return
    style["corner_radius"] = contour["outer_radius"]
    style["corner_radii"] = [contour["outer_radius"]] * 4
    proof["contour_measured"] = True
    proof["contour_reason"] = None
    proof["projected_fields"].extend(("corner_radius", "corner_radii"))
    proof["quantity"] = "Actual native centered boundary stroke and circular outer border radius; no raster/frame equivalence asserted"


def state_dot_analytic_paint(node, by_id):
    """Interpret only the bound, concentric, opaque two-ring native primitive.

    The returned CSS quantities describe analytic paint, not sampled pixels.
    Inner-shadow spread contracts the padding-edge hole (CSS Backgrounds 3,
    https://drafts.csswg.org/css-backgrounds-3/#shadow-shape). No reference
    records, expected sizes/colors or screenshot-based fitting are inputs.
    """
    proof = {"source": "Actual owned Ellipse rings interpreted as analytic circular border and zero-blur inset paint",
             "owner_id": node.get("id"), "status": "unmeasured", "layers": [],
             "parameters": None, "raster_equivalence": None, "antialiasing_equivalence": None,
             "same_frame_contribution": None, "reasons": []}
    reasons = proof["reasons"]
    local_nodes = [node, *(child for child in by_id.values() if child.get("parent") == node.get("id"))]
    ownership_issues = []
    layers = state_dot_paint_layers(local_nodes, by_id, ownership_issues).get(node.get("id"), [])
    proof["ownership"] = copy.deepcopy(node.get("state_dot_evidence"))
    reasons.extend(issue["reason"] for issue in ownership_issues)
    if len(layers) != 2:
        reasons.append("Exactly two reciprocally bound current Surround/VacancyRing paint objects are required")
    owner_outline, owner_proof, owner_issues = native_outline(node, by_id)
    proof["owner_outline"] = owner_proof
    if (node.get("type") != "NativeStateDotView" or owner_outline != "none"
            or owner_proof.get("absence_proven") is not True or owner_issues
            or (node.get("outline_owner_evidence") or {}).get("own_paint_contract") != "relic-state-dot-grid-owned-ellipses"):
        reasons.append("Current exact state-dot Grid own-paint contract is incomplete; old null contracts cannot establish aggregate paint")

    def transparent_brush(style, property_name, color_name):
        brushes = style.get("brush_evidence")
        brush = brushes.get(property_name) if isinstance(brushes, dict) else None
        color = style.get(color_name)
        if (not isinstance(brush, dict) or "type" not in brush or not isinstance(color, list)
                or len(color) != 4 or not all(finite(v) and 0 <= v <= 255 for v in color) or color[3] != 0):
            return False
        if brush["type"] is None:
            return color == [0, 0, 0, 0] and brush.get("solid_rgba") == color
        return (brush["type"] == "Microsoft.UI.Xaml.Media.SolidColorBrush"
                and brush.get("solid_rgba") == color and finite(brush.get("opacity"))
                and 0 <= brush["opacity"] <= 1)

    owner_style = node.get("style") or {}
    owner_widths = owner_style.get("border_widths")
    if (not transparent_brush(owner_style, "background", "background")
            or not transparent_brush(owner_style, "border", "border_color")
            or not finite(owner_style.get("border_width")) or owner_style["border_width"] != 0
            or not isinstance(owner_widths, list) or len(owner_widths) != 4
            or not all(finite(width) and width == 0 for width in owner_widths)):
        reasons.append("The actual Grid must have measured transparent background and no independent border paint")
    for painted_node in [node, *layers]:
        actual_style = painted_node.get("style") or {}
        if (not finite(actual_style.get("opacity")) or actual_style["opacity"] != 1
                or not finite(painted_node.get("opacity")) or painted_node["opacity"] != 1
                or actual_style.get("shadow") != [] or actual_style.get("background_image") != "none"
                or actual_style.get("paint_diagnostics") != []):
            reasons.append(painted_node["id"] + ": opacity, effects or brush diagnostics do not establish the supported unmodified paint")
    contours = []
    for layer in layers:
        local_issues = []
        projected = {"style": copy.deepcopy(layer.get("style") or {}), "evidence": {}}
        project_ellipse_border(projected, layer, local_issues)
        ellipse = projected["evidence"].get("ellipse_border") or {}
        contour = ellipse.get("geometry_derivation")
        layer_outline, layer_proof, layer_issues = native_outline(layer, by_id)
        proof["layers"].append({"id": layer["id"], "ellipse": ellipse, "own_outline": layer_proof})
        if (local_issues or ellipse.get("stroke_fields_measured") is not True
                or ellipse.get("contour_measured") is not True or not isinstance(contour, dict)
                or layer_outline != "none" or layer_issues):
            reasons.append(layer["id"] + ": actual solid undashed circular stroke/geometry or own paint is incomplete")
        if not transparent_brush(layer.get("style") or {}, "background", "background"):
            reasons.append(layer["id"] + ": an opaque, unknown or unsupported Fill cannot be treated as an empty ring")
        color = projected["style"].get("border_color")
        if not isinstance(color, list) or len(color) != 4 or color[3] != 255:
            reasons.append(layer["id"] + ": this bounded analytic case requires an actual opaque stroke")
        contours.append(contour)
    if len(contours) == 2 and all(isinstance(contour, dict) for contour in contours):
        surround, vacancy = contours
        if (surround["center"] != vacancy["center"]
                or surround["inner_radius"] != vacancy["outer_radius"]):
            reasons.append("Actual rings are not concentric or the inner ring does not meet the padding edge")
        if (node.get("bounds") != surround["outer_bounds"] or node.get("visible_bounds") != node.get("bounds")
                or node.get("local_bounds") != layers[0].get("local_bounds")
                or node.get("transform") != layers[0].get("transform")
                or "clip" not in node or node["clip"] is not None
                or "hidden_reason" not in node or node["hidden_reason"] is not None):
            reasons.append("Actual Grid box/transform/visibility is not the complete Surround outer box")
        if not reasons:
            border_width = surround["outer_radius"] - surround["inner_radius"]
            spread = vacancy["outer_radius"] - vacancy["inner_radius"]
            border_color = copy.deepcopy(layers[0]["style"]["foreground"])
            parameters = {"background": copy.deepcopy(owner_style["background"]),
                          "border_color": border_color, "border_width": border_width,
                          "border_widths": [border_width] * 4, "border_colors": [copy.deepcopy(border_color) for _ in range(4)],
                          "border_styles": ["solid"] * 4, "corner_radius": surround["outer_radius"],
                          "corner_radii": [surround["outer_radius"]] * 4,
                          "shadow": [{"inset": True, "offset_x": 0, "offset_y": 0, "blur_radius": 0,
                                      "spread_radius": spread, "color": copy.deepcopy(layers[1]["style"]["foreground"])}]}
            proof.update(status="measured-analytic-parameters", parameters=copy.deepcopy(parameters),
                         quantity="Actual native annular paint parameters only; no pixel, antialiasing or frame-equivalence claim")
    issues = [{"id": node.get("id"), "property": "style.compound_paint", "reason": "; ".join(reasons)}] if reasons else []
    # Even complete primitive parameters do not bind this paint to the final PNG.
    # Keep this independent coverage failure rather than marking the dot passed.
    issues.append({"id": node.get("id"), "property": "paint.compound_raster",
                   "reason": "Actual ring parameters do not measure final PNG contribution, antialiasing or same-frame equivalence"})
    return proof["parameters"], proof, issues


def measured_dialog_surfaces(raw, by_id, unmeasured):
    """Bind an actual modal surface, not a same-sized/name-matched descendant.

    Template parts are validated against the original captured parent graph;
    inline/semantic projection must not supply or rewrite this object proof.
    Authored content and the separately hosted smoke layer remain independent.
    """
    surfaces = {}
    for owner in raw:
        if owner.get("type") != "NativeContentDialog":
            continue
        receipt = owner.get("dialog_surface_evidence")
        reason = None
        if not isinstance(receipt, dict):
            reason = "Actual applied ContentDialog template-part receipt is missing"
        elif (receipt.get("source") != DIALOG_SURFACE_SOURCE
                or receipt.get("owner_id") != owner.get("id")
                or receipt.get("owner_type") != "Relic.NativeContentDialog"
                or type(receipt.get("template_revision")) is not int or receipt["template_revision"] <= 0
                or type(receipt.get("template_revision_after")) is not int
                or receipt["template_revision_after"] != receipt["template_revision"]
                or receipt.get("template_is_nonnull") is not True
                or receipt.get("same_applied_template_reference") is not True
                or receipt.get("same_applied_template_reference_after") is not True
                or receipt.get("ui_thread_access") is not True
                or measured_runtime_type(owner, "is_control") is not True
                or measured_runtime_type(owner, "control_template_present") is not True):
            reason = "Actual dialog owner, applied template identity/revision or UI-thread receipt is incomplete or changed"
        parts = receipt.get("parts") if isinstance(receipt, dict) else None
        resolved = {}
        if reason is None:
            if not isinstance(parts, dict):
                reason = "Actual dialog template-part collection is missing"
            else:
                for name, expected_type in (("BackgroundElement", "Border"), ("Content", "ContentPresenter"),
                                            ("ContentScrollViewer", "ScrollViewer"), ("LayoutRoot", "Grid")):
                    part = parts.get(name)
                    part_id = part.get("id") if isinstance(part, dict) else None
                    target = by_id.get(part_id) if isinstance(part_id, str) else None
                    path = part.get("actual_parent_path_to_owner") if isinstance(part, dict) else None
                    if (not target or not isinstance(path, list) or len(path) < 2
                            or part.get("part_name") != name or part.get("is_null") is not False
                            or part.get("same_applied_part_reference") is not True
                            or part.get("path_reaches_owner") is not True
                            or part.get("error") or part.get("ancestry_cycle")
                            or part.get("runtime_type") != "Microsoft.UI.Xaml.Controls." + expected_type
                            or target.get("type") != expected_type):
                        reason = "Actual dialog template part has missing/changed object identity or type: " + name
                        break
                    ids = []
                    for step in path:
                        step_id = step.get("id") if isinstance(step, dict) else None
                        item = by_id.get(step_id) if isinstance(step_id, str) else None
                        runtime_type = step.get("runtime_type") if isinstance(step, dict) else None
                        if (not item or not isinstance(runtime_type, str)
                                or runtime_type.rsplit(".", 1)[-1] != item.get("type")
                                or item["id"] in ids):
                            reason = "Actual dialog template path has missing, changed or repeated objects: " + name
                            break
                        ids.append(item["id"])
                    if reason is not None:
                        break
                    if (ids[0] != target["id"] or ids[-1] != owner["id"]
                            or any(by_id[child].get("parent") != parent for child, parent in zip(ids, ids[1:]))):
                        reason = "Actual dialog template path does not match the captured parent-object chain: " + name
                        break
                    resolved[name] = target
        if reason is None:
            if len({part["id"] for part in resolved.values()}) != len(resolved):
                reason = "Distinct dialog template parts resolve to the same captured object"
            else:
                content_path = [step["id"] for step in parts["Content"]["actual_parent_path_to_owner"]]
                surface_path = [step["id"] for step in parts["BackgroundElement"]["actual_parent_path_to_owner"]]
                if (resolved["BackgroundElement"]["id"] not in content_path
                        or resolved["ContentScrollViewer"]["id"] not in content_path
                        or resolved["LayoutRoot"]["id"] not in surface_path):
                    reason = "Actual modal surface, content presenter and scroll viewer do not share the measured template path"
        if reason is None:
            authored_id = receipt.get("authored_content_id")
            authored = by_id.get(authored_id) if isinstance(authored_id, str) else None
            if (not authored or authored["id"] in {part["id"] for part in resolved.values()}
                    or authored.get("declared_content_owner") != owner["id"]
                    or authored.get("declared_content_source") != "ContentControl.Content"
                    or not isinstance(receipt.get("authored_content_type"), str)
                    or receipt["authored_content_type"].rsplit(".", 1)[-1] != authored.get("type")):
                reason = "Authored dialog Content is not independently bound to its actual owner"
            else:
                seen, current = set(), authored
                while current and current["id"] not in seen and current["id"] != resolved["Content"]["id"]:
                    seen.add(current["id"])
                    current = by_id.get(current.get("parent"))
                if not current or current["id"] != resolved["Content"]["id"]:
                    reason = "Actual authored Content does not reach its measured template ContentPresenter"
        if reason is None:
            surface = resolved["BackgroundElement"]
            if (surface.get("hidden_reason") or not positive(surface.get("bounds"))
                    or not positive(surface.get("visible_bounds")) or not isinstance(surface.get("style"), dict)):
                reason = "Actual modal Border has no finite visible layout/paint measurement"
        if reason is not None:
            unmeasured.append({"id": owner["id"], "property": "dialog.surface", "reason": reason})
        else:
            surfaces[owner["id"]] = resolved["BackgroundElement"]
    return surfaces


def uia_identity_rejection(node, provider_id, owner_by_provider, provider_by_owner):
    """Negative/unique actual identities constrain, never supply, a candidate.

    Missing identity evidence still follows the existing unresolved heuristics.
    A measured no-peer receipt is not evidence of noninteraction or invisibility;
    it only prohibits claiming a provider for that particular captured object.
    """
    evidence = node.get("automation_identity_evidence")
    if (isinstance(evidence, dict) and evidence.get("source") == OWNER_SOURCE
            and evidence.get("owner_id") == node.get("id")
            and evidence.get("status") == "no-peer" and evidence.get("peer_is_null") is True):
        return "Actual captured owner has no AutomationPeer; geometry/name cannot supply another object's provider"
    actual_owner = owner_by_provider.get(provider_id)
    if actual_owner is not None and actual_owner != node.get("id"):
        return "Complete RuntimeId binds this provider to another actual XAML owner: " + actual_owner
    actual_provider = provider_by_owner.get(node.get("id"))
    if actual_provider is not None and actual_provider != provider_id:
        return "Complete RuntimeId binds this actual XAML owner to another independent provider: " + actual_provider
    return None


def native_path_binding(owner, by_id):
    """Validate retained production objects/spans, independently of text matching.

    Text equality is a consistency check AFTER explicit object/parent binding.
    It never finds a line or a UIA provider. Invalid/fallback captures stay raw.
    """
    receipt = owner.get("native_path_evidence")
    if not isinstance(receipt, dict):
        return None, "No actual production path receipt"
    identity = receipt.get("owner_identity")
    def real_identity(value, runtime):
        return (isinstance(value, dict) and value.get("runtime_type") == runtime
                and type(value.get("managed_reference_hash")) is int
                and isinstance(value.get("iunknown_identity"), str)
                and re.fullmatch(r"[0-9a-fA-F]+", value["iunknown_identity"]) is not None
                and int(value["iunknown_identity"], 16) != 0)
    if (owner.get("type") != "NativePathText"
            or receipt.get("source") != "Actual NativePathText production line selection and actual child line objects"
            or receipt.get("owner_id") != owner.get("id") or receipt.get("status") != "laid-out"
            or receipt.get("failure") is not None or receipt.get("actual_visual_bindings_complete") is not True
            or not real_identity(identity, "Relic.NativePathText")
            or type(receipt.get("layout_revision")) is not int or receipt["layout_revision"] <= 0):
        return None, "Actual path owner/layout identity is missing, failed or incomplete"
    source = receipt.get("source_text")
    if not isinstance(source, str) or not source:
        return None, "Actual complete path source is missing"
    encoded = source.encode("utf-16-le", "surrogatepass")
    if type(receipt.get("source_utf16_length")) is not int or len(encoded) != 2 * receipt["source_utf16_length"]:
        return None, "Actual path UTF-16 length differs from its retained source"
    source_contract, source_error = native_path_source_contract(receipt)
    if source_error:
        return None, source_error
    layout = receipt.get("layout")
    layouts = layout.get("lines") if isinstance(layout, dict) else None
    bindings = receipt.get("actual_line_bindings")
    if (not isinstance(layouts, list) or not layouts or not isinstance(bindings, list) or len(layouts) != len(bindings)):
        return None, "Actual retained line objects and production line intervals are incomplete"
    result, seen, seen_labels = [], set(), set()
    position = 0
    for index, (binding, line_layout) in enumerate(zip(bindings, layouts)):
        if not isinstance(binding, dict) or not isinstance(line_layout, dict):
            return None, "A production line binding/interval is malformed"
        line_id = binding.get("line_id")
        line = by_id.get(line_id)
        if (not isinstance(line_id, str) or line_id in seen or not isinstance(line, dict)
                or line.get("type") != "NativeLabel" or line.get("native_path_line_evidence") != binding
                or binding.get("source") != "Actual NativePathText retained NativeLabel object identity and unchanged source interval"
                or binding.get("owner_id") != owner["id"] or binding.get("owner_identity") != identity
                or not real_identity(binding.get("label_identity"), "Relic.NativeLabel")
                or type(binding.get("layout_revision")) is not int or binding["layout_revision"] != receipt["layout_revision"]
                or type(binding.get("line_index")) is not int or binding["line_index"] != index
                or type(binding.get("line_count")) is not int or binding["line_count"] != len(bindings)
                or any(binding.get(key) is not True for key in
                       ("same_retained_label_reference", "same_current_body_parent", "same_content_body", "label_is_loaded",
                        "line_in_actual_visual_walk", "reaches_same_owner_object", "all_captured_edges_match"))
                or not source_contract["mapped"] and binding.get("source_slice_matches") is not True):
            return None, "A retained NativeLabel lacks exact current object/render-id binding"
        label_identity = int(binding["label_identity"]["iunknown_identity"], 16)
        if label_identity in seen_labels:
            return None, "Distinct production lines claim the same actual NativeLabel object"
        seen_labels.add(label_identity)
        edges = binding.get("actual_ancestor_edges")
        if not isinstance(edges, list) or not edges:
            return None, "Actual production line has no retained visual parent chain"
        current, ancestors = line_id, {line_id}
        for edge in edges:
            actual = by_id.get(current)
            if (not isinstance(edge, dict) or not isinstance(actual, dict) or edge.get("child_id") != current
                    or edge.get("parent_id") != actual.get("parent") or edge.get("parent_id") not in by_id
                    or edge.get("actual_parent_in_visual_walk") is not True or edge.get("captured_parent_matches") is not True
                    or edge["parent_id"] in ancestors):
                return None, "Actual line parent edges differ from the independently retained XAML tree"
            current = edge["parent_id"]; ancestors.add(current)
        if current != owner["id"]:
            return None, "Actual line parent chain does not end at the same path owner"
        if source_contract["mapped"]:
            actual = source_contract["line_contracts"][index]
            arrangement = receipt["arranged_lines"][index]
            local = line.get("local_bounds")
            if (line.get("text") != actual["paint_text"] or not positive(local)
                    or local["width"] != arrangement["actual_label_width"]
                    or local["height"] != arrangement["actual_label_height"]):
                return None, "Actual retained line paint text or local measured size differs from the arranged object receipt"
            result.append(line); seen.add(line_id)
            continue
        first, last = binding.get("start_utf16"), binding.get("end_utf16")
        if (type(first) is not int or type(last) is not int or first != position or last <= first or last * 2 > len(encoded)
                or type(line_layout.get("start_utf16")) is not int or line_layout["start_utf16"] != first
                or type(line_layout.get("end_utf16")) is not int or line_layout["end_utf16"] != last):
            return None, "Production path lines overlap, omit, reorder or exceed the original UTF-16 source"
        source_slice = encoded[first * 2:last * 2].decode("utf-16-le", "surrogatepass")
        if (last * 2 < len(encoded)
                and 0xD800 <= int.from_bytes(encoded[last * 2 - 2:last * 2], "little") <= 0xDBFF
                and 0xDC00 <= int.from_bytes(encoded[last * 2:last * 2 + 2], "little") <= 0xDFFF):
            return None, "A production line splits a source UTF-16 surrogate pair"
        if (binding.get("complete_source_text") != source or binding.get("actual_label_text") != source_slice
                or line.get("text") != source_slice or line_layout.get("source_text") != source_slice
                or any(not finite(binding.get(a)) or not finite(line_layout.get(b)) or binding[a] != line_layout[b]
                       for a, b in (("actual_line_y", "label_y"), ("actual_line_height", "line_height")))):
            return None, "The bound production line source or layout differs between actual receipts"
        result.append(line); seen.add(line_id); position = last
    if not source_contract["mapped"] and position * 2 != len(encoded):
        return None, "Bound production lines do not cover the complete path source"
    recorded = {node["id"] for node in by_id.values() if isinstance(node.get("native_path_line_evidence"), dict)
                and node["native_path_line_evidence"].get("owner_id") == owner["id"]}
    if recorded != seen:
        return None, "An actual retained path line is omitted or claimed more than once"
    return result, None


def project_native_paths(elements, by_id, uia_nodes, identity_bindings, used_uia, projection, unmeasured):
    """One source-owning selectable text control, with all line measurements raw.

    Only bound internal line elements are replaced. Independent selection paint,
    menus, unbound Images and every previous extraction/coverage error survive.
    """
    result = list(elements)
    for owner in by_id.values():
        if owner.get("type") != "NativePathText":
            continue
        lines, reason = native_path_binding(owner, by_id)
        def gap(prop, message):
            unmeasured.append({"id": owner["id"], "property": "native_path." + prop, "reason": message})
        if reason:
            gap("ownership", reason); continue
        line_ids = [line["id"] for line in lines]
        own_elements = {eid: [element for element in result if element["id"] == eid] for eid in line_ids}
        if any(len(values) != 1 or values[0].get("kind") != "text" for values in own_elements.values()):
            gap("visible_line_measurements", "Not every bound production line has one independently projected text measurement"); continue
        if any(element["id"] == owner["id"] for element in result):
            gap("owner_paint", "Owner also has independently projected paint/semantics; it cannot silently become only text"); continue
        measured = [own_elements[eid][0] for eid in line_ids]
        receipt = owner["native_path_evidence"]
        source_contract, source_error = native_path_source_contract(receipt)
        if source_error:
            gap("source_mapping", source_error); continue
        # Actual values must agree. An unmeasured/different line cannot inherit
        # its sibling's glyph font, paint or geometry to manufacture coverage.
        style = {}
        keys = ("font_size", "font_weight", "foreground", "background", "border_color", "border_width", "corner_radius",
                "border_widths", "border_colors", "border_styles", "corner_radii", "opacity", "background_image", "shadow", "outline")
        for key in keys:
            values = [element.get("style", {}).get(key) for element in measured]
            style[key] = copy.deepcopy(values[0]) if values[0] is not None and all(value == values[0] for value in values) else None
            if style[key] is None:
                gap("style." + key, "Actual bound line values differ or at least one line is unmeasured")
        owner_outline, owner_outline_evidence, owner_outline_issues = native_outline(owner, by_id)
        unmeasured.extend(owner_outline_issues)
        if owner_outline != "none" or style["outline"] != "none":
            style["outline"] = None
            gap("style.outline", "Path owner and every internal line require independent own/focus/Composition outline evidence")
        font_lists = [element.get("style", {}).get("rendered_fonts") for element in measured]
        fonts_complete = all(isinstance(fonts, list) and fonts and all(isinstance(font, dict) for font in fonts) for fonts in font_lists)
        style["rendered_fonts"] = [copy.deepcopy(font) for fonts in font_lists for font in fonts] if fonts_complete else None
        if not fonts_complete:
            gap("rendered_fonts", "At least one actual drawing line has no complete measured render-face evidence")
        geometry, visible_geometry = [], []
        geometry_complete = True
        for element in measured:
            entry = element.get("evidence", {}).get("native_label_geometry")
            metrics = entry.get("font_metric_advance") if isinstance(entry, dict) else None
            source = element["text"].encode("utf-16-le", "surrogatepass")
            covered = set()
            if not isinstance(metrics, list) or not metrics:
                geometry_complete = False; continue
            for metric in metrics:
                description = metric.get("description") if isinstance(metric, dict) else None
                window = metric.get("window") if isinstance(metric, dict) else None
                if not isinstance(description, dict) or not isinstance(window, dict) or metric.get("text_scope") != "layout-source":
                    geometry_complete = False; continue
                first, length = description.get("text_position_utf16"), description.get("text_length_utf16")
                text = description.get("text")
                if (type(first) is not int or type(length) is not int or first < 0 or length <= 0 or (first + length) * 2 > len(source)
                        or not isinstance(text, str) or source[first * 2:(first + length) * 2] != text.encode("utf-16-le", "surrogatepass")
                        or not positive(window.get("bounds")) or not positive(window.get("visible_bounds"))
                        or covered.intersection(range(first, first + length))):
                    geometry_complete = False; continue
                covered.update(range(first, first + length))
                geometry.append(copy.deepcopy(window["bounds"])); visible_geometry.append(copy.deepcopy(window["visible_bounds"]))
            if covered != set(range(len(source) // 2)):
                geometry_complete = False
        if not geometry_complete:
            gap("text_bounds", "Bound line font-metric advance rectangles/source coverage are incomplete; layout/hit/ink boxes are not substituted")
        pairs = [pair for pair in identity_bindings.get("pairs", []) if pair.get("xaml_id") == owner["id"]]
        witnesses = [provider for provider in uia_nodes if len(pairs) == 1 and provider.get("id") == pairs[0].get("uia_id")]
        witness = witnesses[0] if len(witnesses) == 1 and witnesses[0].get("control_type") == "ControlType.Text" else None
        if witness:
            used_uia.add(witness["id"])
        else:
            gap("UIA_correspondence", "No unique actual RuntimeId-bound Text provider; names/nearby boxes are not pairing evidence")
        state = {key: copy.deepcopy(owner.get("state", {}).get(key)) for key in STATE_KEYS}
        if witness:
            for key in STATE_KEYS:
                if witness.get("state", {}).get(key) is not None:
                    state[key] = witness["state"][key]
        interactive, interaction_reason = interaction_applicability(owner, "text", witness)
        if interactive is None:
            state["enabled"] = state["focused"] = None; gap("interaction", interaction_reason)
        name = witness.get("name") if witness else owner.get("accessible_name")
        if not isinstance(name, str):
            name = ""; gap("name", "Actual path owner accessible name was not measured")
        actual_layout = receipt.get("layout", {})
        icu = actual_layout.get("paint_icu" if source_contract["mapped"] else "icu")
        policy = all(native_path_iterator(icu, source_contract["paint_text"], typ) is not None for typ in (0, 2))
        measured_count = all(type(element.get("layout", {}).get("line_count")) is int and element["layout"]["line_count"] > 0 for element in measured)
        line_count = sum(element["layout"]["line_count"] for element in measured) if measured_count else None
        trims = [element.get("layout", {}).get("truncation") for element in measured]
        layout = {"wrap": None, "break_strategy_version": 1, "normal_break_strategy": "word" if policy else None,
                  "emergency_break_strategy": ("none" if source_contract["normal_whitespace"] else "break-unbreakable") if policy else None,
                  "line_count": line_count if measured_count else None,
                  "truncation": trims[0] if trims[0] is not None and all(value == trims[0] for value in trims) else None}
        if not policy:
            gap("break_strategy", "Actual ICU source-bound line/character iterator receipts are incomplete")
        gap("visible_text", "Complete production source and actual per-line drawing inputs are retained; final visible glyph text is not established by source-to-paint mapping")
        ancestor_ids = dict.fromkeys(part_id
            for binding in receipt["actual_line_bindings"]
            for edge in binding["actual_ancestor_edges"]
            for part_id in (edge["child_id"], edge["parent_id"])
            if part_id not in {owner["id"], *line_ids})
        element = {"id": owner["id"], "parent": owner.get("parent"), "region": owner["region"], "order": measured[0]["order"],
                   "kind": "text", "text": source_contract["source_text"], "name": name,
                   "bounds": union_boxes(geometry) if geometry_complete else None,
                   "visible_bounds": union_boxes(visible_geometry) if geometry_complete else None,
                   "style": style, "state": state, "layout": layout, "icon": None,
                   "evidence": {"source": "Actual NativePathText owner and independently measured retained NativeLabel drawing lines",
                                "type": owner["type"], "uia_id": witness["id"] if witness else None,
                                "uia_identity_binding": copy.deepcopy(pairs[0]) if witness else None,
                                "native_path_projection": {"source_receipt": copy.deepcopy(receipt), "source_line_ids": line_ids,
                                                           "validated_source_to_paint": copy.deepcopy(source_contract),
                                                           "independent_line_elements": copy.deepcopy(measured), "raw_owner": copy.deepcopy(owner),
                                                           "raw_lines": copy.deepcopy(lines),
                                                           "raw_ancestors": [copy.deepcopy(by_id[part_id]) for part_id in ancestor_ids],
                                                           "other_child_paint_merged": False},
                                "text_bounds": geometry if geometry_complete else None, "text_coordinate_space": "content-window",
                                "text_bounds_quantity": "Actual rendered-face font metrics around actual draw baselines plus actual glyph advances",
                                "text_quantity": {"canonical": "Complete actual NativePathText.SourceText; not a measured visible glyph string",
                                                  "source_text": source_contract["source_text"],
                                                  "shaping_input": source_contract["paint_text"],
                                                  "shaping_input_quantity": "Whole production unwrapped shaping input; may include undrawn line-edge whitespace",
                                                  "line_inputs": [{"line_id": line["id"], "text": line["text"],
                                                                   "source_binding": copy.deepcopy(line["native_path_line_evidence"])} for line in lines],
                                                  "line_inputs_quantity": "Actual retained NativeLabel strings in source order; no inferred joining separator",
                                                  "visible_text": None,
                                                  "visible_text_reason": "Source ownership and current line inputs do not establish final screen visibility, clipping, occlusion or pixel contribution"},
                                "owner_layout_bounds": copy.deepcopy(owner.get("bounds")),
                                "line_break_configuration": {"applicable": True, "source": "Actual NativePathText retained ICU/source-to-paint production policy",
                                                             "owner": owner["id"], "raw": copy.deepcopy(actual_layout),
                                                             "errors": [] if policy else ["Actual iterator source binding is incomplete"]},
                                "interaction_applicability": {"applicable": interactive, "reason": interaction_reason,
                                                              "xaml": copy.deepcopy(owner.get("interaction_evidence")),
                                                              "uia_state": copy.deepcopy(witness.get("state")) if witness else None},
                                "outline": {"source": "Independently measured actual source owner and retained drawing lines",
                                            "owner": owner_outline_evidence,
                                            "lines": [copy.deepcopy(item.get("evidence", {}).get("outline")) for item in measured],
                                            "absence_proven": style["outline"] == "none"}}}
        # Preserve configured and resolved independently, including every raw
        # source receipt. No line's request supplies another line's face weight.
        quantities = [item.get("evidence", {}).get("font_weight_quantities") for item in measured]
        quantities_bound = [isinstance(quantity, dict) and type(quantity.get("version")) is int and quantity["version"] == 1
                            and quantity.get("applicable") is True and quantity.get("owner") == item["id"]
                            and isinstance(quantity.get("legacy"), dict)
                            and quantity["legacy"].get("value") == item.get("style", {}).get("font_weight")
                            for item, quantity in zip(measured, quantities)]
        configured = [item.get("configured") if isinstance(item, dict) else None for item in quantities]
        configured_ok = all(quantities_bound) and all(isinstance(item, dict) and finite(item.get("value")) and 1 <= item["value"] <= 1000
                            and isinstance(item.get("source"), str) and item["source"] and isinstance(item.get("raw"), dict)
                            and item["value"] == style.get("font_weight") for item in configured)
        resolved = [item.get("resolved") if isinstance(item, dict) else None for item in quantities]
        resolved_ok = all(quantities_bound) and fonts_complete and all(isinstance(item, dict) and item.get("source_span_complete") is True
                                            and isinstance(item.get("faces"), list) and item["faces"] for item in resolved)
        element["evidence"]["font_weight_quantities"] = {
            "version": 1, "applicable": True, "owner": owner["id"],
            "legacy": {"value": style.get("font_weight"), "quantity": "configured" if configured_ok else "unclassified provider value"},
            "configured": {"value": style.get("font_weight") if configured_ok else None,
                           "source": "Actual source-bound production line requests", "raw": {"lines": copy.deepcopy(configured), "source_bindings": copy.deepcopy(receipt["actual_line_bindings"])}},
            "resolved": {"source_span_complete": bool(resolved_ok),
                         "faces": [copy.deepcopy(face) for item in resolved for face in item["faces"]] if resolved_ok else None,
                         "source": "Actual source-bound production line render-face measurements",
                         "raw": {"lines": copy.deepcopy(resolved), "source_bindings": copy.deepcopy(receipt["actual_line_bindings"])}}}
        for issue in font_weight_issues(element):
            gap(issue["field"], issue["reason"])
        for issue in unmeasured:
            if issue.get("id") in line_ids:
                issue.setdefault("projected_owner_id", owner["id"])
        insertion = min(result.index(item) for item in measured)
        result = [item for item in result if item["id"] not in line_ids]
        result.insert(insertion, element)
        for line_id in line_ids:
            projection.append({"source": line_id, "owner": owner["id"], "reason": "Actual retained production drawing line of one source-owning path text",
                               "binding": copy.deepcopy(by_id[line_id]["native_path_line_evidence"])})
        if witness:
            projection.append({"source": witness["id"], "owner": owner["id"], "reason": "Actual complete RuntimeId binding to production path text owner"})
    orders = defaultdict(int)
    ordered = []
    for element in result:
        ordered.append(dict(element, order=orders[element["region"]])); orders[element["region"]] += 1
    return ordered


def project(xaml_path, uia_path, png_path):
    xaml = json.loads(Path(xaml_path).read_text(encoding="utf-8-sig"))
    uia = json.loads(Path(uia_path).read_text(encoding="utf-8-sig"))
    image = Image.open(png_path).convert("RGBA")
    uia_errors, nonvisible_diagnostics = visible_uia_errors(uia)
    errors = list(xaml.get("extraction_errors", [])) + uia_errors
    unmeasured = []
    range_failures = uia_text_range_failures(uia.get("raw_nodes", []), unmeasured, nonvisible_diagnostics)
    if xaml["viewport"]["scale"] != 1:
        errors.append("XAML rasterization scale differs from the required 1:1 screenshot")
    if uia.get("case_id") != xaml.get("scene_id"):
        errors.append("UIA and XAML scene identifiers differ")
    if uia.get("viewport") != xaml.get("viewport"):
        errors.append("UIA and XAML viewports differ")
    if image.size != (xaml["viewport"]["width"], xaml["viewport"]["height"]):
        errors.append("Screenshot size differs from measured viewport")
    source_raw = xaml["raw_nodes"]
    source_by_id = {node["id"]: node for node in source_raw}
    composition_clips = {}
    for source_node in source_raw:
        if not isinstance(source_node.get("bounds"), dict):
            continue
        clip_audit, clip_issues = composition_clip(source_node)
        composition_clips[source_node["id"]] = clip_audit
        if not source_node.get("hidden_reason") and positive(source_node.get("visible_bounds")):
            unmeasured.extend(clip_issues)
    dialog_surfaces = measured_dialog_surfaces(source_raw, source_by_id, unmeasured)
    dialog_surface_owners = {surface["id"]: owner for owner, surface in dialog_surfaces.items()}
    identity_bindings = bind_automation_identities(source_raw, uia)
    toggle_parts = windows_toggle_parts(source_raw, uia)
    for issue in toggle_parts["unresolved"]:
        unmeasured.append({"id": issue["owner_id"], "property": "state.originating_toggle",
                           "reason": issue["reason"], "evidence": copy.deepcopy(issue["evidence"])})
    avatar_parts = windows_avatar_parts(source_raw, uia)
    unmeasured.extend(avatar_parts["unmeasured"])
    for issue in avatar_parts["unresolved"]:
        unmeasured.append({"id": issue["owner_id"], "property": "avatar.retained_parts",
                           "reason": issue["reason"], "evidence": copy.deepcopy(issue["evidence"])})
    owner_by_provider = {pair["uia_id"]: pair["xaml_id"] for pair in identity_bindings["pairs"]}
    provider_by_owner = {pair["xaml_id"]: pair["uia_id"] for pair in identity_bindings["pairs"]}
    provider_records = defaultdict(list)
    owner_records = defaultdict(list)
    for provider in uia.get("raw_nodes", []):
        provider_records[provider.get("id")].append(provider)
    for owner in source_raw:
        owner_records[owner.get("id")].append(owner)
    group_regions = {}
    for pair in identity_bindings["pairs"]:
        owners = owner_records[pair["xaml_id"]]
        providers = provider_records[pair["uia_id"]]
        # A Panel can own an actual accessibility Group without painting a
        # background. The complete, independently observed RuntimeId supplies
        # this role; neither its accessible name nor a nearby box supplies it.
        if (len(owners) == 1 and len(providers) == 1
                and measured_runtime_type(owners[0], "is_panel") is True
                and semantic_control_kind(owners[0]) is None
                and providers[0].get("control_type") == "ControlType.Group"):
            group_regions[pair["xaml_id"]] = copy.deepcopy(pair)
    rejected_identity_pairs = {}

    def identity_allows(node, provider):
        reason = uia_identity_rejection(node, provider["id"], owner_by_provider, provider_by_owner)
        if reason is None:
            return True
        key = (node["id"], provider["id"])
        if key not in rejected_identity_pairs:
            rejected_identity_pairs[key] = {"xaml_id": node["id"], "uia_id": provider["id"], "reason": reason}
        # Rejecting a wrong candidate is not itself a measurement failure. The
        # existing no-witness, unresolved-owner and unmatched-provider paths
        # retain their own errors; no field is filled from this rejected pair.
        return False
    if not source_raw or not uia.get("raw_nodes"):
        errors.append("Independent UIA and XAML source trees must both be nonempty")
    raw = project_inline_reading_order(project_text_leaves(source_raw, unmeasured, xaml.get("pointer")), unmeasured)
    by_id = {n["id"]: n for n in raw}
    fenced_blocks = markdown_fenced_blocks(raw, by_id, unmeasured)
    state_dot_layers = state_dot_paint_layers(raw, by_id, unmeasured)
    scrollbars, scrollbar_thumbs = scrollbar_templates(raw, by_id, unmeasured)
    scrollbar_page_hits = scrollbar_page_hit_regions(raw, scrollbars, by_id)
    def control_kind(node):
        return semantic_control_kind(node, scrollbar_thumbs) or ("region" if node["id"] in group_regions else None)
    fragments, occlusion_masks, occlusion_gaps = measured_occlusion(raw, by_id)
    unmeasured.extend(occlusion_gaps)
    children = defaultdict(list)
    for node in raw:
        children[node.get("parent")].append(node)
    projection = []
    elements = []
    owned = {}
    semantic = {n["id"] for n in raw if control_kind(n) or n["type"] in PAINT_CONTROL_KINDS}
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

    state_dot_layers = {owner: layers for owner, layers in state_dot_layers.items()
                        if visible(by_id[owner]) and any(visible(layer) for layer in layers)}
    semantic.update(state_dot_layers)

    def user_content(node, control_id):
        current = node
        while current and current["id"] != control_id:
            if current["id"] in fenced_blocks:
                return True  # Actual registered Markdown content, not a control template.
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
        if node["type"] == "NativeContentDialog":
            # Only the actual GetTemplateChild-bound surface is owned here.
            # Other template paint and authored Content stay independent; a
            # generic descendant/name/geometry rule cannot enlarge this scope.
            surface = dialog_surfaces.get(node["id"])
            if surface is not None:
                control_paint[node["id"]].append(surface)
                owned[surface["id"]] = (node["id"], "actual applied dialog BackgroundElement surface")
            continue
        labels = []
        avatar_backgrounds = []
        runtime = node.get("render_type_evidence")
        is_control = runtime.get("is_control") if isinstance(runtime, dict) else None
        has_template = runtime.get("control_template_present") if isinstance(runtime, dict) else None
        template_ownership_unknown = False
        for child in descendants(node):
            nearest = ancestor(child, semantic)
            if not nearest or nearest["id"] != node["id"] or not visible(child):
                continue
            if child["type"] in TEXT_TYPES and child.get("text") and not ancestor(child, {n["id"] for n in raw if n["type"] in ICON_TYPES}):
                labels.append(child)
            if child["type"] in {"Border", "Grid", "Rectangle", "ContentPresenter"}:
                if node["type"] in AVATAR_TYPES:
                    # A letter/avatar background is one semantic surface. Its
                    # decorative rings, image and icon content remain separate.
                    if distance(child["bounds"], node["bounds"]) <= 1e-6 and painted(child.get("style", {}).get("background")):
                        avatar_backgrounds.append(child)
                    continue
                if user_content(child, node["id"]):
                    continue
                if is_control is not True or has_template is not True:
                    # A semantic region can be a real Grid, not a templated
                    # Control. Its authored children are independent paint.
                    # Unknown runtime type/template evidence cannot own them.
                    if is_control is not False and not (is_control is True and has_template is False):
                        template_ownership_unknown = True
                    continue
                control_paint[node["id"]].append(child)
                owned[child["id"]] = (node["id"], "semantic control template paint")
        if template_ownership_unknown:
            unmeasured.append({"id": node["id"], "property": "template.paint_ownership",
                               "reason": "Actual Control type and nonnull Control.Template were not both measured; child paint remains independent"})
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
        compound = distinct_semantics or distinct_content_paint and node["type"] not in AVATAR_TYPES
        if len(labels) == 1 and not compound and (control_kind(node) or PAINT_CONTROL_KINDS.get(node["type"])) not in {"card", "list-row", "chart-node", "region"}:
            control_label[node["id"]] = labels[0]
            owned[labels[0]["id"]] = (node["id"], "single simple control label")
    icons = {n["id"] for n in raw if n["type"] in ICON_TYPES}
    for node in raw:
        owner = ancestor(node, icons)
        if owner:
            owned[node["id"]] = (owner["id"], "icon implementation glyph")
    label_surfaces = native_label_surfaces(raw, by_id, unmeasured)
    for surface, owner in label_surfaces.items():
        owned[surface] = (owner, "actual NativeLabel production text paint surface")
    dot_layer_owners = {layer["id"]: owner for owner, layers in state_dot_layers.items() for layer in layers}
    for layer, owner in dot_layer_owners.items():
        owned[layer] = (owner, "actual compound state-dot paint layer")
    for region_id, (owner, _) in scrollbar_page_hits.items():
        owned[region_id] = (owner, "actual nonpainted non-tab-stop ScrollBar template input region")
    avatar_owners = {}
    for owner, parts in avatar_parts["owners"].items():
        if not visible(by_id[owner]) or any(part in owned and owned[part][0] != owner for part in parts["owned_ids"]):
            unmeasured.append({"id": owner, "property": "avatar.retained_parts",
                               "reason": "Actual avatar is not visible or a retained decoration has conflicting ownership"})
            continue
        avatar_owners[owner] = parts
        for part in parts["owned_ids"]:
            owned[part] = (owner, "actual retained production avatar decoration")

    host_ownership = host_container_ownership(uia, raw)
    projection.extend(host_ownership)
    used_uia = {record["source"] for record in host_ownership}
    uia_nodes = [n for n in uia.get("raw_nodes", []) if positive(n.get("bounds")) and not n.get("state", {}).get("offscreen")]
    transparent_ownership = [record for record in transparent_uia_ownership(uia_nodes, raw, scrollbar_thumbs)
                             if identity_allows(by_id[record["owner"]], {"id": record["source"]})]
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
    paired_controls = {}
    uia_by_id = {n["id"]: n for n in uia.get("raw_nodes", [])}
    def uia_scrollbar_owner(provider):
        current = uia_by_id.get(provider.get("parent"))
        seen = set()
        while current and current["id"] not in seen:
            seen.add(current["id"])
            if current.get("control_type", "").removeprefix("ControlType.") == "ScrollBar":
                return current["id"]
            current = uia_by_id.get(current.get("parent"))
        return None
    for node in raw:
        dialog_surface = dialog_surfaces.get(node["id"])
        paint_node = dialog_surface if dialog_surface is not None else node
        if control_kind(node) in {"resize-handle", "scrollbar", "scrollbar-thumb"} and not node.get("hidden_reason"):
            measured_box = node.get("bounds")
            if not isinstance(measured_box, dict) or not all(finite(measured_box.get(k)) for k in ("x", "y", "width", "height")):
                unmeasured.append({"id": node["id"], "property": "bounds", "reason": "Production control has no finite measured XAML bounds; no box is synthesized"})
        if not visible(paint_node):
            reason = paint_node.get("hidden_reason") or ("fully occluded by measured opaque paint" if positive(paint_node.get("visible_bounds")) and not fragments.get(paint_node["id"]) else "not a visible rendered box")
            projection.append({"source": node["id"], "reason": reason, "occlusion_masks": occlusion_masks.get(node["id"], [])})
            continue
        # Check even template-owned or unpainted wrappers: unknown attached
        # Composition/focus paint must not disappear with the layout wrapper.
        outline_value, outline_evidence, outline_issues = native_outline(node, by_id)
        unmeasured.extend(outline_issues)
        if node["id"] in owned:
            owner, why = owned[node["id"]]
            record = {"source": node["id"], "owner": owner, "reason": why}
            record["outline_evidence"] = outline_evidence
            if node["id"] in dialog_surface_owners:
                record["ownership_evidence"] = copy.deepcopy(source_by_id[dialog_surface_owners[node["id"]]]["dialog_surface_evidence"])
                record["paint_evidence"] = copy.deepcopy(node)
            if node["id"] in label_surfaces:
                record["ownership_evidence"] = copy.deepcopy(node["native_label_surface_evidence"])
            if node["id"] in dot_layer_owners:
                record["ownership_evidence"] = copy.deepcopy(node["state_dot_layer_evidence"])
                record["paint_evidence"] = copy.deepcopy(node)
            if node["id"] in scrollbar_page_hits:
                owner, region_nodes = scrollbar_page_hits[node["id"]]
                owner_provider = paired_controls.get(owner)
                providers = [n for n in uia_nodes if n["id"] not in used_uia and n.get("class_name") == "RepeatButton"
                             and uia_kind_matches(n, "button") and owner_provider
                             and uia_scrollbar_owner(n) == owner_provider["id"]
                             and distance(n["bounds"], node["bounds"]) <= 8 and identity_allows(node, n)]
                record["ownership_evidence"] = copy.deepcopy(node["scrollbar_page_hit_evidence"])
                record["actual_input_region"] = copy.deepcopy(node)
                record["template_layers"] = copy.deepcopy(region_nodes[1:])
                if len(providers) == 1:
                    used_uia.add(providers[0]["id"])
                    record["uia_input_region"] = copy.deepcopy(providers[0])
                else:
                    unmeasured.append({"id": node["id"], "property": "UIA correspondence",
                                       "reason": "ScrollBar internal input region has no unique independent RepeatButton provider"})
            projection.append(record)
            continue
        typ = node["type"]
        style = copy.deepcopy(paint_node.get("style", {}))
        surface_outline_evidence = None
        if dialog_surface is not None:
            surface_outline, surface_outline_evidence, _ = native_outline(dialog_surface, source_by_id)
            style["outline"] = "none" if outline_value == "none" and surface_outline == "none" else None
        else:
            style["outline"] = outline_value
        kind = control_kind(node) or PAINT_CONTROL_KINDS.get(typ)
        if dialog_surface is not None:
            kind = "region"  # Actual modal dialog region, with the native host's semantic owner.
        text = node.get("text", "")
        if typ in TEXT_TYPES:
            if typ == "WorkspaceCodeView":
                kind = "code"
            elif node.get("text_container_projection"):
                kind = "card" if painted(style.get("background")) or painted(style.get("border_color")) and finite(style.get("border_width")) and style["border_width"] > 0 else None
            else:
                kind = "text" if text else None
        elif typ in ICON_TYPES:
            kind = "icon"
        elif typ == "Image" or typ in AVATAR_TYPES:
            kind = "avatar" if typ in AVATAR_TYPES else "image"
        elif typ in {"Line", "Path", "Polyline"}:
            kind = "chart-edge" if ancestor(node, {n["id"] for n in raw if n["type"] == "Canvas"}) else "divider"
        elif typ == "Ellipse":
            kind = "state-dot" if node["bounds"]["width"] <= 10 else "image"
        elif not kind and (typ in {"Border", "Rectangle", "Grid", "StackPanel", "Canvas", "ContentPresenter"} or measured_runtime_type(node, "is_panel") is True):
            if (painted(style.get("background"))
                    or painted(style.get("border_color")) and finite(style.get("border_width")) and style["border_width"] > 0
                    or measured_runtime_type(node, "is_shape") is True
                    and painted(style.get("foreground")) and finite(style.get("stroke_width")) and style["stroke_width"] > 0):
                kind = "divider" if min(node["bounds"]["width"], node["bounds"]["height"]) <= 2 else "card"
                if node.get("parent") is None or typ == "Border" and node["region"] != by_id.get(node.get("parent"), {}).get("region"):
                    kind = "region"
        if node["id"] in fenced_blocks:
            kind = "code"
        if node["id"] in state_dot_layers:
            kind = "state-dot"
        if not kind:
            projection.append({"source": node["id"], "reason": "layout wrapper with no own text, role, background or border",
                               "outline_evidence": outline_evidence})
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
        if dialog_surface is not None:
            state["hovered"] = dialog_surface.get("state", {}).get("hovered")
        if typ in AVATAR_TYPES and node["id"] in provider_by_owner:
            # PersonPicture's real provider can report Text while the actual
            # native control owns an avatar. Bind only by full RuntimeId here;
            # unrelated Text providers are never reclassified by proximity.
            provider_id = provider_by_owner[node["id"]]
            matching = [n for n in uia_nodes if n["id"] == provider_id and n["id"] not in used_uia]
        elif node["id"] in group_regions:
            # Keep the measured identity even if independent bounds/names
            # differ. Those values remain actual evidence, not pairing keys.
            provider_id = group_regions[node["id"]]["uia_id"]
            matching = [n for n in uia_nodes if n["id"] == provider_id and n["id"] not in used_uia]
        else:
            matching = [n for n in uia_nodes if n["id"] not in used_uia and uia_kind_matches(n, kind)
                        and distance(n["bounds"], node["bounds"]) <= 8 and identity_allows(node, n)]
        if isinstance(node.get("native_path_line_evidence"), dict):
            # The retained line is paint inside a separately accessible source
            # owner. It must not claim that owner's Text provider by proximity.
            matching = [n for n in matching if owner_by_provider.get(n["id"]) == node["id"]]
        if kind == "scrollbar-thumb":
            owner_provider = paired_controls.get(scrollbar_thumbs[node["id"]])
            matching = [n for n in matching if owner_provider and uia_scrollbar_owner(n) == owner_provider["id"]]
        matching.sort(key=lambda n: (n.get("name", "") not in (text, node.get("accessible_name", "")), distance(n["bounds"], node["bounds"])))
        witness = matching[0] if matching else None
        interactive, interaction_reason = interaction_applicability(node, kind, witness)
        if witness:
            used_uia.add(witness["id"])
            paired_controls[node["id"]] = witness
            for key in STATE_KEYS:
                if key in {"enabled", "focused"} and interactive is not True:
                    continue
                if key in witness.get("state", {}) and witness["state"][key] is not None:
                    state[key] = witness["state"][key]
            if layout.get("line_count") is None:
                ranges = (witness.get("text_pattern") or {}).get("visible_ranges", [])
                rectangles = [b for r in ranges for b in measured_text_boxes(r.get("bounds")) if positive(b)]
                if rectangles:
                    layout["line_count"] = len({round(b["y"], 1) for b in rectangles})
        if interactive is False:
            state["enabled"] = state["focused"] = None
        elif interactive is None:
            unmeasured.append({"id": node["id"], "property": "state.interaction_applicability", "reason": interaction_reason})
        originating_toggle = toggle_parts["parts"].get(node["id"])
        if originating_toggle is not None:
            # This decorative part has no independent action. Its four live
            # originating-control fields are separately proven by retained
            # objects, the exact ancestor chain and a full RuntimeId binding.
            # Keep the raw part state and every paint/frame obligation below.
            state.update(originating_toggle["state"])
        if control_kind(node) and not witness:
            unmeasured.append({"id": node["id"], "property": "UIA correspondence", "reason": "No independent UIA control box at the rendered position"})
        scrollbar_range_evidence = None
        scrollbar_paint = None
        scrollbar_bounds = scrollbar_visible_bounds = None
        if kind in {"scrollbar", "scrollbar-thumb"}:
            scroll_state, scrollbar_range_evidence = scrollbar_state(node, kind, scrollbars, scrollbar_thumbs,
                                                                    witness, paired_controls, unmeasured)
            state.update(scroll_state)
            layer_nodes = [p for p in descendants(node) if visible(p) and p["id"] not in semantic and ancestor(p, semantic) == node]
            scrollbar_paint, paint_issues = scrollbar_paint_measurement(
                node, kind, layer_nodes, fragments, occlusion_masks,
                node["id"] in scrollbars if kind == "scrollbar" else node["id"] in scrollbar_thumbs)
            unmeasured.extend(paint_issues)
            if scrollbar_paint["canonical_style"] is not None:
                style.update(scrollbar_paint["canonical_style"])
                scrollbar_bounds = scrollbar_paint["canonical_bounds"]
                scrollbar_visible_bounds = scrollbar_paint["canonical_visible_bounds"]
        actual_text_boxes = measured_text_boxes(layout.get("character_boxes")) if layout.get("character_boxes_coordinate_space") == "content-window" else []
        if not actual_text_boxes and witness:
            actual_text_boxes = [copy.deepcopy(b) for r in (witness.get("text_pattern") or {}).get("visible_ranges", [])
                                 for b in measured_text_boxes(r.get("bounds")) if positive(b)]
        text_source = label or node
        submitted_label = None
        submitted_label_geometry = None
        submitted_label_fonts = None
        submitted_label_text = None
        if text_source.get("type") == "NativeLabel":
            captured_frame = xaml.get("capture_evidence")
            frame = captured_frame.get("native_label_frame") if isinstance(captured_frame, dict) else None
            submitted_label, label_issues = native_label_submission(text_source, frame)
            unmeasured.extend(label_issues)
            actual_surfaces = [candidate for candidate in raw if candidate.get("type") == "Image"
                               and isinstance(candidate.get("native_label_surface_evidence"), dict)
                               and candidate["native_label_surface_evidence"].get("owner_id") == text_source["id"]]
            submitted_label_geometry, geometry_issues = native_label_geometry(
                text_source, actual_surfaces[0] if len(actual_surfaces) == 1 else None)
            unmeasured.extend(geometry_issues)
            submitted_label_fonts, font_issues = native_label_fonts(
                text_source, actual_surfaces[0] if len(actual_surfaces) == 1 else None, frame)
            unmeasured.extend(font_issues)
            # Only a standalone text leaf owns this quantity. Composite control
            # owners and retained NativePath lines keep their existing projection.
            if typ == "NativeLabel" and kind == "text" and label is None:
                submitted_label_text = native_label_text_quantity(
                    node, submitted_label_geometry, submitted_label_fonts, submitted_label)
                if submitted_label_text is not None:
                    actual_text_boxes = copy.deepcopy(submitted_label_text["text_bounds"])
            for key in ("font_size", "font_weight", "foreground"):
                style[key] = submitted_label["style"].get(key) if submitted_label["style"] is not None else None
        run_source = text_source.get("text_run_source")
        run_name_witness = None
        actual_run_font_records = []
        font_witnesses = [] if run_source else [witness] if witness else []
        if run_source:
            text_owner = by_id[run_source["owner"]]
            run_providers, actual_run_font_records = run_font_witnesses(uia_nodes, text_owner, actual_text_boxes)
            run_candidates = [n for n in run_providers if identity_allows(text_owner, n)]
            if len(run_candidates) != len(run_providers):
                run_providers, actual_run_font_records = run_font_witnesses(run_candidates, text_owner, actual_text_boxes)
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
                               and n.get("name") == text and distance(n["bounds"], label["bounds"]) <= 8
                               and identity_allows(label, n)]
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
        if text and provider_fonts and submitted_label is None:
            unmeasured.append({"id": node["id"], "property": "style.rendered_fonts.actual_face",
                               "reason": "UIA font-name attributes are retained as provider evidence; actual DirectWrite glyph-run/fallback face identity is not exposed by this capture",
                               "provider_families": [font["family_name"] for font in provider_fonts]})
        # WinUI's UIA adapter reads TextElement.FontFamily.Source, not the
        # physical fallback face. Never put that requested family into the
        # canonical actual-font field, even when a cmap supports the text.
        # Independently measured current production glyph faces are distinct
        # from UIA's configured family and from final PNG/glyph visibility.
        # Filling this field does not clear any presentation/geometry failure.
        style["rendered_fonts"] = submitted_label_fonts.get("fonts") if submitted_label_fonts else None
        if text and not actual_text_boxes:
            unmeasured.append({"id": node["id"], "property": "evidence.text_bounds", "reason": "Actual window-relative text rectangles are unavailable"})
        if text and not provider_fonts and style["rendered_fonts"] is None:
            reason = ("Actual NativeLabel submitted glyph callbacks are retained, but the visible glyph subset/final PNG contribution is not established"
                      if submitted_label is not None and submitted_label["submitted_glyph_runs"] is not None
                      else "UIA did not measure the rendered font; declared XAML family is not substituted")
            unmeasured.append({"id": node["id"], "property": "style.rendered_fonts", "reason": reason})
        if run_source and actual_text_boxes:
            font_rectangles = [b for record in actual_run_font_records
                               if record.get("attribute_status", {}).get("font_family") == "measured"
                               and isinstance(record.get("attributes", {}).get("font_family"), str)
                               and record["attributes"]["font_family"]
                               for b in measured_text_boxes(record.get("bounds"))]
            if any(b["width"] > 0 and not any(intersection(b, font_box) for font_box in font_rectangles) for b in actual_text_boxes):
                unmeasured.append({"id": node["id"], "property": "style.rendered_fonts",
                                   "reason": "Some measured Run glyph positions have no independent UIA font-range correspondence"})
        rich_runs = layout.get("rich_text_runs", [])
        if not text:
            layout = {"wrap": None, "truncation": None, "line_count": None}
            style["font_size"] = style["font_weight"] = None
            if kind not in {"icon", "chart-edge"} and measured_runtime_type(node, "is_shape") is not True:
                style["foreground"] = None
        compound_paint = None
        if node["id"] in state_dot_layers:
            compound_paint = {
                "source": copy.deepcopy(node["state_dot_evidence"]),
                "owner_style": copy.deepcopy(node.get("style")),
                "layers": [{"raw": copy.deepcopy(layer), "visible_fragments": copy.deepcopy(fragments.get(layer["id"])),
                            "occlusion_masks": copy.deepcopy(occlusion_masks.get(layer["id"], []))}
                           for layer in state_dot_layers[node["id"]]],
                "css_paint_equivalence": None,
            }
            parameters, analytic_evidence, paint_issues = state_dot_analytic_paint(node, by_id)
            compound_paint["analytic_parameters"] = analytic_evidence
            # The old Grid defaults are not the appearance of its children.
            # Only independently bound analytic quantities replace these nulls;
            # pixel/AA/frame equivalence remains unknown even on that path.
            for prop in ("background", "border_color", "border_width", "border_widths", "border_colors",
                         "border_styles", "corner_radius", "corner_radii", "shadow"):
                style[prop] = copy.deepcopy(parameters[prop]) if parameters is not None else None
            unmeasured.extend(paint_issues)
        avatar_parts_evidence = avatar_owners.get(node["id"])
        avatar_surface = by_id[avatar_parts_evidence["bounds_source"]] if avatar_parts_evidence else None
        if avatar_parts_evidence is not None:
            if avatar_parts_evidence["border_source"] is not None:
                style.update(copy.deepcopy(avatar_parts_evidence["border_style"]))
            if avatar_parts_evidence["outline_source"] is not None:
                style["outline"] = copy.deepcopy(avatar_parts_evidence["outline"])
        bounds = avatar_surface["bounds"] if avatar_surface is not None else scrollbar_bounds or paint_node["bounds"]
        if submitted_label_text is not None:
            bounds = submitted_label_text["bounds"]
        points = [(bounds["x"] + bounds["width"] * x, bounds["y"] + bounds["height"] * y) for x, y in ((.5,.5), (.1,.1), (.9,.1), (.1,.9), (.9,.9))]
        samples = [{"x": int(x), "y": int(y), "rgba": list(image.getpixel((int(x), int(y))))} for x, y in points if 0 <= x < image.width and 0 <= y < image.height]
        break_fields, break_evidence = project_line_break_strategies(layout, text, kind, (label or node)["id"])
        layout.update(break_fields)
        for issue in break_strategy_issues({"text": text, "kind": kind, "layout": layout,
                                           "evidence": {"line_break_configuration": break_evidence}}):
            unmeasured.append({"id": node["id"], "property": "layout.break_strategy", "reason": issue})
        for key in (*BREAK_FIELDS, "truncation", "line_count"):
            if text and layout.get(key) is None:
                unmeasured.append({"id": node["id"], "property": "layout." + key, "reason": "No rendered text measurement"})
        if state["hovered"] is None:
            unmeasured.append({"id": node["id"], "property": "state.hovered", "reason": "Pointer hit-test evidence missing"})
        if kind == "icon" and not node.get("icon"):
            unmeasured.append({"id": node["id"], "property": "icon", "reason": "No actual glyph/vector measurement"})
        region = node["region"]
        name_witness = witness or run_name_witness
        reported_name = name_witness.get("name") if name_witness else node.get("accessible_name")
        element = {"id": node["id"], "parent": node.get("parent"), "region": region, "order": order[region], "kind": kind,
                   "text": text, "name": reported_name if isinstance(reported_name, str) else "",
                   "bounds": bounds, "visible_bounds": submitted_label_text["visible_bounds"] if submitted_label_text is not None else avatar_surface["visible_bounds"] if avatar_surface is not None else scrollbar_visible_bounds or paint_node["visible_bounds"], "style": style, "state": state,
                   "layout": {k: layout.get(k) for k in ("wrap", "truncation", "line_count", "break_strategy_version", *BREAK_FIELDS)}, "icon": node.get("icon"),
                   "evidence": {"source": "XAML render tree + independent UIA", "type": typ, "uia_id": witness["id"] if witness else None,
                                "uia_group_region": copy.deepcopy(group_regions.get(node["id"])),
                                "line_break_configuration": break_evidence,
                                "outline": outline_evidence,
                                "native_label_geometry": submitted_label_geometry,
                                "native_label_text_quantity": submitted_label_text,
                                "native_label_fonts": submitted_label_fonts,
                                "label_source": label["id"] if label else None,
                                "paint_sources": [p["id"] for p in paints] + [layer["id"] for layer in state_dot_layers.get(node["id"], [])],
                                "font_family": node.get("font_family"), "pixel_samples": samples, "value": value,
                                "placeholder": node.get("layout", {}).get("placeholder"),
                                "text_bounds": actual_text_boxes if actual_text_boxes or not text else None,
                                "text_bounds_quantity": submitted_label_text["quantity"] if submitted_label_text is not None else None,
                                "text_coordinate_space": "content-window",
                                "rich_text_runs": rich_runs, "visible_fragments": fragments.get(paint_node["id"]),
                                "text_run_source": copy.deepcopy(run_source), "uia_font_ranges": actual_run_font_records,
                                "xaml_font_weight_configuration": copy.deepcopy(text_source.get("font_weight_configuration")),
                                "xaml_font_weight_binding": {
                                    "source": "actual XAML text_source selected by existing projection",
                                    "canonical_owner_id": node["id"], "source_id": text_source["id"],
                                    "source_type": text_source.get("type"), "text": text_source.get("text"),
                                    "style_font_weight": text_source.get("style", {}).get("font_weight"),
                                    "text_run_source": copy.deepcopy(run_source),
                                    "rich_text_runs": copy.deepcopy(text_source.get("layout", {}).get("rich_text_runs")),
                                    "ownership": ({"source_id": text_source["id"], "owner_id": owned[text_source["id"]][0],
                                                   "reason": owned[text_source["id"]][1]}
                                                  if text_source["id"] in owned else None)
                                } if text_source.get("font_weight_configuration") is not None else None,
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
                                "resize_handle_evidence": copy.deepcopy(node.get("resize_handle_evidence")),
                                "region_container_evidence": copy.deepcopy(node.get("region_container_evidence")),
                                "scrollbar_evidence": copy.deepcopy(node.get("scrollbar_evidence")),
                                "scrollbar_thumb_evidence": copy.deepcopy(node.get("scrollbar_thumb_evidence")),
                                "scrollbar_page_hit_evidence": copy.deepcopy(node.get("scrollbar_page_hit_evidence")),
                                "scrollbar_range": scrollbar_range_evidence, "scrollbar_paint": scrollbar_paint,
                                "native_label_evidence": copy.deepcopy(text_source.get("native_label_evidence")),
                                "native_label_submission": submitted_label,
                                "actual_trimming": copy.deepcopy(layout.get("actual_trimming")),
                                "inline_sequence_evidence": copy.deepcopy(node.get("inline_sequence_evidence")),
                                "inline_order_evidence": copy.deepcopy(node.get("inline_order_evidence")),
                                "markdown_code_evidence": copy.deepcopy(node.get("markdown_code_evidence")),
                                "markdown_code_text_evidence": copy.deepcopy(node.get("markdown_code_text_evidence")),
                                "compound_paint": compound_paint,
                                "state_evidence": copy.deepcopy(node.get("state_evidence")),
                                "originating_toggle": copy.deepcopy(originating_toggle),
                                "avatar_retained_parts": copy.deepcopy(avatar_parts_evidence),
                                "render_type_evidence": copy.deepcopy(node.get("render_type_evidence")),
                                "declared_content_source": node.get("declared_content_source"),
                                "brush_evidence": copy.deepcopy(paint_node.get("style", {}).get("brush_evidence")),
                                "animated_icon_evidence": copy.deepcopy(node.get("animated_icon_evidence")),
                                "image_source_evidence": copy.deepcopy(node.get("image_source_evidence")),
                                "occlusion_masks": occlusion_masks.get(paint_node["id"], []),
                                "visible_fragments_are_envelopes": True}}
        if dialog_surface is not None:
            element["evidence"]["dialog_surface"] = {
                "source": "Actual applied NativeContentDialog surface; native host semantics remain separate from its layout box",
                "template_receipt": copy.deepcopy(node["dialog_surface_evidence"]),
                "host_layout_projected_as_paint": False, "canonical_geometry_supplied": True,
                "geometry_quantity": "Actual BackgroundElement layout rectangle transformed to content-window coordinates",
                "host": {"id": node["id"], "bounds": copy.deepcopy(node["bounds"]),
                         "visible_bounds": copy.deepcopy(node["visible_bounds"]), "style": copy.deepcopy(node.get("style")),
                         "uia_id": witness["id"] if witness else None,
                         "uia_bounds": copy.deepcopy(witness.get("bounds")) if witness else None,
                         "identity": copy.deepcopy(node.get("automation_identity_evidence"))},
                "surface": {"id": dialog_surface["id"], "raw": copy.deepcopy(dialog_surface),
                            "outline_evidence": surface_outline_evidence},
                "other_template_paint_and_authored_content_merged": False,
                "smoke_layer_merged": False,
            }
        project_ellipse_border(element, node, unmeasured)
        element["evidence"]["font_weight_quantities"] = project_font_weights(element)
        for issue in font_weight_issues(element):
            unmeasured.append({"id": node["id"], "property": "style." + issue["field"], "reason": issue["reason"]})
        project_background_pattern(element, paint_node)
        project_windows_image(element, unmeasured, errors)
        if node["id"] in composition_clips:
            apply_composition_clip(element, composition_clips[node["id"]])
        for key in ("background", "border_color", "corner_radius", "opacity", "shadow", "background_image"):
            if style.get(key) is None:
                unmeasured.append({"id": node["id"], "property": "style." + key, "reason": "Unsupported rendered brush/property"})
        order[region] += 1
        projection.append({"source": node["id"], "element": node["id"], "reason": "visible rendered element"})
        # Collection is deliberately independent of the reference element count.
        elements.append(element)
    elements = project_native_paths(elements, by_id, uia_nodes, identity_bindings, used_uia, projection, unmeasured)
    for n in uia_nodes:
        if n["id"] in used_uia:
            continue
        b = n["bounds"]
        if b["x"] + b["width"] <= 0 or b["y"] + b["height"] <= 0 or b["x"] >= image.width or b["y"] >= image.height:
            continue
        covered = next((r for r in raw if positive(r.get("bounds")) and positive(r.get("visible_bounds"))
                        and not r.get("hidden_reason") and not fragments.get(r["id"])
                        and uia_kind_matches(n, control_kind(r) or ("text" if r["type"] in TEXT_TYPES else ""))
                        and distance(b, r["bounds"]) <= 8 and identity_allows(r, n)), None)
        if covered:
            projection.append({"source": n["id"], "owner": covered["id"], "reason": "UIA box corresponds to measured fully occluded render node",
                               "occlusion_masks": occlusion_masks.get(covered["id"], [])})
            continue
        # A UIA text child can already be represented by the owning control's
        # label. Preserve the measured ownership instead of silently losing it.
        owner = next((e for e in elements if not isinstance(e.get("evidence", {}).get("native_path_projection"), dict)
                      and positive(e.get("bounds")) and n.get("control_type") == "ControlType.Text" and n.get("name") and n.get("name") == e["text"] and e["bounds"]["x"] <= b["x"] and e["bounds"]["y"] <= b["y"] and b["x"] + b["width"] <= e["bounds"]["x"] + e["bounds"]["width"] + 1 and b["y"] + b["height"] <= e["bounds"]["y"] + e["bounds"]["height"] + 1
                      and identity_allows(by_id[e["id"]], n)), None)
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
    capture_evidence = copy.deepcopy(xaml.get("capture_evidence", {}))
    # Raw object receipts remain in XAML and each emitted owner's evidence.
    # Keep non-emitted layout owners in this audit so ancestor clips cannot vanish.
    capture_evidence["composition_clips"] = {
        key: {field: copy.deepcopy(value.get(field)) for field in ("owner_id", "status", "window_geometry", "image_corner_radius", "presentation_identity_proven")}
        for key, value in composition_clips.items()}
    capture_evidence["automation_identity_bindings"] = identity_bindings
    capture_evidence["uia_pairing_rejections"] = list(rejected_identity_pairs.values())
    # Optional supplementary diagnostic. Keep the original UIA errors, bounds
    # and canonical element measurements unchanged until actual frame/range
    # continuity is independently established.
    probe_path = Path(xaml_path).with_name(Path(xaml_path).name.removesuffix(".xaml.json") + ".text-range-provider-probe.json")
    if probe_path.exists():
        try:
            probe = json.loads(probe_path.read_text(encoding="utf-8-sig"))
            capture_evidence["text_range_precision"] = analyze_text_precision(xaml, uia, probe)
        except (ValueError, TypeError, KeyError, AttributeError, OSError) as error:
            capture_evidence["text_range_precision"] = {
                "source": probe_path.name, "status": "unavailable", "error": str(error),
                "canonical_geometry_supplied": False, "provider_errors_resolved": False}
    if range_failures:
        capture_evidence["uia_text_range_failures"] = range_failures
    return {"schema_version": 1, "scene_id": xaml["scene_id"], "client": "windows", "viewport": xaml["viewport"],
            "elements": elements, "extraction_errors": errors,
            "coverage": {"raw_nodes": len(source_raw) + len(uia.get("raw_nodes", [])), "recorded_text_leaves": len(raw) - len(source_raw),
                         "emitted_elements": len(elements), "unmeasured": unmeasured},
            "projection": projection, "nonvisible_diagnostics": nonvisible_diagnostics,
            "capture_evidence": capture_evidence,
            "raw_evidence": {"xaml": Path(xaml_path).name, "uia": Path(uia_path).name}}
