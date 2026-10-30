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

from paint_patterns import MeasurementError, captured_pattern, pattern_measurement_issue


CONTROL_KINDS = {
    "Button": "button", "AppBarButton": "button", "RepeatButton": "button",
    "HyperlinkButton": "link", "TextBox": "input", "ComposerInput": "input", "NativeTextarea": "input", "PasswordBox": "input",
    "CheckBox": "checkbox", "RadioButton": "checkbox", "ToggleSwitch": "toggle",
    "ToggleButton": "toggle", "ComboBox": "dropdown", "SelectorBarItem": "tab",
    "TabViewItem": "tab", "MenuBarItem": "menu-item", "MenuFlyoutItem": "menu-item",
    "MenuFlyoutSubItem": "menu-item", "ToggleMenuFlyoutItem": "menu-item",
    "ListViewItem": "list-row", "TreeViewItem": "list-row", "Expander": "card",
    "ContentDialog": "card", "MenuFlyoutSeparator": "divider", "ScrollBar": "scrollbar",
    "NativeRegionGrid": "region",
    "ChartNodeButton": "chart-node", "ChartSurface": "region", "WorkspaceCodeView": "code",
}
PAINT_CONTROL_KINDS = {"OverviewChipView": "chip", "OverviewBadgeView": "badge", "PersonPicture": "avatar"}
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
        if node.get("text") != "" or node.get("icon") or node.get("type") in ICON_TYPES | {"Image", "PersonPicture"}:
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
        return class_name in {"ToggleButton", "ToggleSwitch"} and any(isinstance(p, str) and "Toggle" in p for p in node.get("supported_patterns", []))
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
                        text_run_source={"owner": node["id"], "index": index, "start_offset": run.get("start_offset"),
                                         "end_offset": run.get("end_offset")},
                        layout={"wrap": node["layout"].get("wrap"), "truncation": node["layout"].get("truncation"),
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
    if not source_raw or not uia.get("raw_nodes"):
        errors.append("Independent UIA and XAML source trees must both be nonempty")
    raw = project_inline_reading_order(project_text_leaves(source_raw, unmeasured, xaml.get("pointer")), unmeasured)
    by_id = {n["id"]: n for n in raw}
    fenced_blocks = markdown_fenced_blocks(raw, by_id, unmeasured)
    state_dot_layers = state_dot_paint_layers(raw, by_id, unmeasured)
    scrollbars, scrollbar_thumbs = scrollbar_templates(raw, by_id, unmeasured)
    scrollbar_page_hits = scrollbar_page_hit_regions(raw, scrollbars, by_id)
    def control_kind(node):
        return semantic_control_kind(node, scrollbar_thumbs)
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
                if node["type"] == "PersonPicture":
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
        compound = distinct_semantics or distinct_content_paint and node["type"] != "PersonPicture"
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

    host_ownership = host_container_ownership(uia, raw)
    projection.extend(host_ownership)
    used_uia = {record["source"] for record in host_ownership}
    uia_nodes = [n for n in uia.get("raw_nodes", []) if positive(n.get("bounds")) and not n.get("state", {}).get("offscreen")]
    transparent_ownership = transparent_uia_ownership(uia_nodes, raw, scrollbar_thumbs)
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
        if control_kind(node) in {"resize-handle", "scrollbar", "scrollbar-thumb"} and not node.get("hidden_reason"):
            measured_box = node.get("bounds")
            if not isinstance(measured_box, dict) or not all(finite(measured_box.get(k)) for k in ("x", "y", "width", "height")):
                unmeasured.append({"id": node["id"], "property": "bounds", "reason": "Production control has no finite measured XAML bounds; no box is synthesized"})
        if not visible(node):
            reason = node.get("hidden_reason") or ("fully occluded by measured opaque paint" if positive(node.get("visible_bounds")) and not fragments.get(node["id"]) else "not a visible rendered box")
            projection.append({"source": node["id"], "reason": reason, "occlusion_masks": occlusion_masks.get(node["id"], [])})
            continue
        if node["id"] in owned:
            owner, why = owned[node["id"]]
            record = {"source": node["id"], "owner": owner, "reason": why}
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
                             and distance(n["bounds"], node["bounds"]) <= 8]
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
        style = copy.deepcopy(node.get("style", {}))
        kind = control_kind(node) or PAINT_CONTROL_KINDS.get(typ)
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
        elif typ in {"Image", "PersonPicture"}:
            kind = "avatar" if typ == "PersonPicture" else "image"
        elif typ in {"Line", "Path", "Polyline"}:
            kind = "chart-edge" if ancestor(node, {n["id"] for n in raw if n["type"] == "Canvas"}) else "divider"
        elif typ == "Ellipse":
            kind = "state-dot" if node["bounds"]["width"] <= 10 else "image"
        elif not kind and (typ in {"Border", "Rectangle", "Grid", "StackPanel", "Canvas", "ContentPresenter"} or node.get("render_type_evidence", {}).get("is_panel") is True):
            if (painted(style.get("background"))
                    or painted(style.get("border_color")) and finite(style.get("border_width")) and style["border_width"] > 0
                    or node.get("render_type_evidence", {}).get("is_shape") is True
                    and painted(style.get("foreground")) and finite(style.get("stroke_width")) and style["stroke_width"] > 0):
                kind = "divider" if min(node["bounds"]["width"], node["bounds"]["height"]) <= 2 else "card"
                if node.get("parent") is None or typ == "Border" and node["region"] != by_id.get(node.get("parent"), {}).get("region"):
                    kind = "region"
        if node["id"] in fenced_blocks:
            kind = "code"
        if node["id"] in state_dot_layers:
            kind = "state-dot"
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
                               for b in measured_text_boxes(record.get("bounds"))]
            if any(b["width"] > 0 and not any(intersection(b, font_box) for font_box in font_rectangles) for b in actual_text_boxes):
                unmeasured.append({"id": node["id"], "property": "style.rendered_fonts",
                                   "reason": "Some measured Run glyph positions have no independent UIA font-range correspondence"})
        rich_runs = layout.get("rich_text_runs", [])
        if not text:
            layout = {"wrap": None, "truncation": None, "line_count": None}
            style["font_size"] = style["font_weight"] = None
            if kind not in {"icon", "chart-edge"} and node.get("render_type_evidence", {}).get("is_shape") is not True:
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
            # A Grid's absent border/shadow is not the appearance of its two
            # Ellipse layers. Keep their real paint, and leave aggregate CSS
            # quantities unknown rather than inventing an inset shadow.
            for prop in ("background", "border_color", "border_width", "border_widths", "border_colors",
                         "border_styles", "corner_radius", "corner_radii", "shadow"):
                style[prop] = None
            unmeasured.append({"id": node["id"], "property": "style.compound_paint",
                               "reason": "Actual indicator layers are retained; their aggregate CSS border/radius/inset-shadow equivalence has not been independently measured"})
        bounds = scrollbar_bounds or node["bounds"]
        points = [(bounds["x"] + bounds["width"] * x, bounds["y"] + bounds["height"] * y) for x, y in ((.5,.5), (.1,.1), (.9,.1), (.1,.9), (.9,.9))]
        samples = [{"x": int(x), "y": int(y), "rgba": list(image.getpixel((int(x), int(y))))} for x, y in points if 0 <= x < image.width and 0 <= y < image.height]
        for key in ("wrap", "truncation", "line_count"):
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
                   "bounds": bounds, "visible_bounds": scrollbar_visible_bounds or node["visible_bounds"], "style": style, "state": state,
                   "layout": {k: layout.get(k) for k in ("wrap", "truncation", "line_count")}, "icon": node.get("icon"),
                   "evidence": {"source": "XAML render tree + independent UIA", "type": typ, "uia_id": witness["id"] if witness else None,
                                "label_source": label["id"] if label else None,
                                "paint_sources": [p["id"] for p in paints] + [layer["id"] for layer in state_dot_layers.get(node["id"], [])],
                                "font_family": node.get("font_family"), "pixel_samples": samples, "value": value,
                                "placeholder": node.get("layout", {}).get("placeholder"),
                                "text_bounds": actual_text_boxes if actual_text_boxes or not text else None,
                                "text_coordinate_space": "content-window",
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
                                "resize_handle_evidence": copy.deepcopy(node.get("resize_handle_evidence")),
                                "region_container_evidence": copy.deepcopy(node.get("region_container_evidence")),
                                "scrollbar_evidence": copy.deepcopy(node.get("scrollbar_evidence")),
                                "scrollbar_thumb_evidence": copy.deepcopy(node.get("scrollbar_thumb_evidence")),
                                "scrollbar_page_hit_evidence": copy.deepcopy(node.get("scrollbar_page_hit_evidence")),
                                "scrollbar_range": scrollbar_range_evidence, "scrollbar_paint": scrollbar_paint,
                                "native_label_evidence": copy.deepcopy(text_source.get("native_label_evidence")),
                                "actual_trimming": copy.deepcopy(layout.get("actual_trimming")),
                                "inline_sequence_evidence": copy.deepcopy(node.get("inline_sequence_evidence")),
                                "inline_order_evidence": copy.deepcopy(node.get("inline_order_evidence")),
                                "markdown_code_evidence": copy.deepcopy(node.get("markdown_code_evidence")),
                                "markdown_code_text_evidence": copy.deepcopy(node.get("markdown_code_text_evidence")),
                                "compound_paint": compound_paint,
                                "state_evidence": copy.deepcopy(node.get("state_evidence")),
                                "render_type_evidence": copy.deepcopy(node.get("render_type_evidence")),
                                "declared_content_source": node.get("declared_content_source"),
                                "brush_evidence": copy.deepcopy(node.get("style", {}).get("brush_evidence")),
                                "animated_icon_evidence": copy.deepcopy(node.get("animated_icon_evidence")),
                                "image_source_evidence": copy.deepcopy(node.get("image_source_evidence")),
                                "occlusion_masks": occlusion_masks.get(node["id"], []),
                                "visible_fragments_are_envelopes": True}}
        project_background_pattern(element, node)
        for key in ("background", "border_color", "corner_radius", "opacity", "shadow", "background_image"):
            if style.get(key) is None:
                unmeasured.append({"id": node["id"], "property": "style." + key, "reason": "Unsupported rendered brush/property"})
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
                        and uia_kind_matches(n, control_kind(r) or ("text" if r["type"] in TEXT_TYPES else ""))
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
    capture_evidence = copy.deepcopy(xaml.get("capture_evidence", {}))
    if range_failures:
        capture_evidence["uia_text_range_failures"] = range_failures
    return {"schema_version": 1, "scene_id": xaml["scene_id"], "client": "windows", "viewport": xaml["viewport"],
            "elements": elements, "extraction_errors": errors,
            "coverage": {"raw_nodes": len(source_raw) + len(uia.get("raw_nodes", [])), "recorded_text_leaves": len(raw) - len(source_raw),
                         "emitted_elements": len(elements), "unmeasured": unmeasured},
            "projection": projection, "nonvisible_diagnostics": nonvisible_diagnostics,
            "capture_evidence": capture_evidence,
            "raw_evidence": {"xaml": Path(xaml_path).name, "uia": Path(uia_path).name}}
