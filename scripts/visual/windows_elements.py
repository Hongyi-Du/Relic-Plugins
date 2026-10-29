"""Project independently measured UIA + XAML evidence; never read reference data.

Raw records and projection ownership are retained for audit. Incomplete paint,
visibility or typography measurements fail coverage instead of being guessed.
"""
import copy
import json
import math
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
}
TEXT_TYPES = {"TextBlock", "RichTextBlock"}
ICON_TYPES = {"FontIcon", "SymbolIcon", "PathIcon", "BitmapIcon", "AnimatedIcon", "ReferenceVectorIcon"}
STATE_KEYS = ("enabled", "selected", "checked", "expanded", "focused", "hovered", "unread")
UIA_KINDS = {"Button": {"button", "icon-button"}, "Text": {"text"}, "Edit": {"input"}, "CheckBox": {"checkbox"},
             "RadioButton": {"checkbox"}, "ComboBox": {"dropdown"}, "TabItem": {"tab"}, "MenuItem": {"menu-item"},
             "ListItem": {"list-row"}, "TreeItem": {"list-row"}, "Image": {"image", "avatar", "icon"},
             "Hyperlink": {"link"}, "Separator": {"divider"}, "Group": {"region", "card"}, "Pane": {"region", "card"},
             "Custom": {"region", "card"}, "Window": {"region"}}


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
        sx, sy = abs(matrix["m11"]), abs(matrix["m22"])
        if kind == "rectangle":
            radii = [{"x": 0, "y": 0} for _ in range(4)]
        elif node["type"] == "Rectangle":
            radius = node.get("shape_corner_radius") or {}
            if not all(finite(radius.get(k)) and radius[k] >= 0 for k in ("x", "y")):
                unknown.append(node)
                continue
            radii = [{"x": radius["x"] * sx, "y": radius["y"] * sy} for _ in range(4)]
        else:
            actual = style.get("corner_radii")
            if not isinstance(actual, list) or len(actual) != 4 or not all(finite(r) and r >= 0 for r in actual):
                unknown.append(node)
                continue
            radii = [{"x": r * sx, "y": r * sy} for r in actual]
        if matrix["m11"] < 0:
            radii = [radii[1], radii[0], radii[3], radii[2]]
            widths = [widths[0], widths[3], widths[2], widths[1]]
        if matrix["m22"] < 0:
            radii = [radii[3], radii[2], radii[1], radii[0]]
            widths = [widths[2], widths[1], widths[0], widths[3]]
        if node["type"] == "Border" and node.get("background_sizing") == "InnerBorderEdge" and not (has_stroke and border[3] == 255):
            top, right, bottom, left = widths[0] * sy, widths[1] * sx, widths[2] * sy, widths[3] * sx
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
    if control_type == "Button" and kind == "toggle":
        return node.get("class_name") in {"ToggleButton", "ToggleSwitch"} and any("Toggle" in p for p in node.get("supported_patterns", []))
    return kind in UIA_KINDS.get(control_type, set())


def project(xaml_path, uia_path, png_path):
    xaml = json.loads(Path(xaml_path).read_text(encoding="utf-8-sig"))
    uia = json.loads(Path(uia_path).read_text(encoding="utf-8-sig"))
    image = Image.open(png_path).convert("RGBA")
    errors = list(xaml.get("extraction_errors", [])) + list(uia.get("extraction_errors", []))
    unmeasured = []
    if xaml["viewport"]["scale"] != 1:
        errors.append("XAML rasterization scale differs from the required 1:1 screenshot")
    if uia.get("case_id") != xaml.get("scene_id"):
        errors.append("UIA and XAML scene identifiers differ")
    if uia.get("viewport") != xaml.get("viewport"):
        errors.append("UIA and XAML viewports differ")
    if image.size != (xaml["viewport"]["width"], xaml["viewport"]["height"]):
        errors.append("Screenshot size differs from measured viewport")
    raw = xaml["raw_nodes"]
    if not raw or not uia.get("raw_nodes"):
        errors.append("Independent UIA and XAML source trees must both be nonempty")
    by_id = {n["id"]: n for n in raw}
    fragments, occlusion_masks, occlusion_gaps = measured_occlusion(raw, by_id)
    unmeasured.extend(occlusion_gaps)
    children = defaultdict(list)
    for node in raw:
        children[node.get("parent")].append(node)
    projection = []
    elements = []
    owned = {}
    semantic = {n["id"] for n in raw if n["type"] in CONTROL_KINDS}
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
        for child in descendants(node):
            nearest = ancestor(child, semantic)
            if not nearest or nearest["id"] != node["id"] or not visible(child):
                continue
            if child["type"] in TEXT_TYPES and child.get("text") and not ancestor(child, {n["id"] for n in raw if n["type"] in ICON_TYPES}):
                labels.append(child)
            if child["type"] in {"Border", "Grid", "Rectangle", "ContentPresenter"} and not user_content(child, node["id"]):
                control_paint[node["id"]].append(child)
                owned[child["id"]] = (node["id"], "semantic control template paint")
        if len(labels) == 1 and CONTROL_KINDS[node["type"]] not in {"card", "list-row"}:
            control_label[node["id"]] = labels[0]
            owned[labels[0]["id"]] = (node["id"], "single simple control label")
    icons = {n["id"] for n in raw if n["type"] in ICON_TYPES}
    for node in raw:
        owner = ancestor(node, icons)
        if owner:
            owned[node["id"]] = (owner["id"], "icon implementation glyph")

    used_uia = set()
    uia_nodes = [n for n in uia.get("raw_nodes", []) if positive(n.get("bounds")) and not n.get("state", {}).get("offscreen")]
    for node in uia.get("raw_nodes", []):
        for error in node.get("measurement_errors", []):
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
        kind = CONTROL_KINDS.get(typ)
        text = node.get("text", "")
        if typ in TEXT_TYPES:
            kind = "text" if text else None
        elif typ in ICON_TYPES:
            kind = "icon"
        elif typ in {"Image", "PersonPicture"}:
            kind = "avatar" if typ == "PersonPicture" else "image"
        elif typ in {"Line", "Path", "Polyline"}:
            kind = "chart-edge" if ancestor(node, {n["id"] for n in raw if n["type"] == "Canvas"}) else "divider"
        elif typ == "Ellipse":
            kind = "state-dot" if node["bounds"]["width"] <= 10 else "image"
        elif typ in {"Border", "Rectangle", "Grid", "StackPanel", "Canvas", "ContentPresenter"}:
            if painted(style.get("background")) or painted(style.get("border_color")) and finite(style.get("border_width")) and style["border_width"] > 0:
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
            kind = "icon-button" if any(c["type"] in ICON_TYPES for c in descendants(node)) else "button"
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
            if painted(ps.get("border_color")) and finite(ps.get("border_width")) and ps["border_width"] > 0:
                for key in ("border_color", "border_width", "border_widths", "border_colors", "corner_radius", "corner_radii"):
                    style[key] = ps.get(key)
            break
        state = {k: node.get("state", {}).get(k) for k in STATE_KEYS}
        matching = [n for n in uia_nodes if n["id"] not in used_uia and uia_kind_matches(n, kind) and distance(n["bounds"], node["bounds"]) <= 8]
        matching.sort(key=lambda n: (n.get("name", "") not in (text, node.get("accessible_name", "")), distance(n["bounds"], node["bounds"])))
        witness = matching[0] if matching else None
        if witness:
            used_uia.add(witness["id"])
            for key in STATE_KEYS:
                if key in witness.get("state", {}) and witness["state"][key] is not None:
                    state[key] = witness["state"][key]
            if layout.get("line_count") is None:
                ranges = (witness.get("text_pattern") or {}).get("visible_ranges", [])
                rectangles = [b for r in ranges for b in r.get("bounds", []) if positive(b)]
                if rectangles:
                    layout["line_count"] = len({round(b["y"], 1) for b in rectangles})
        if node["id"] in semantic and not witness:
            unmeasured.append({"id": node["id"], "property": "UIA correspondence", "reason": "No independent UIA control box at the rendered position"})
        actual_text_boxes = [copy.deepcopy(b) for b in layout.get("character_boxes", [])
                             if isinstance(b, dict) and all(finite(b.get(k)) for k in ("x", "y", "width", "height"))
                             and b["width"] >= 0 and b["height"] > 0] if layout.get("character_boxes_coordinate_space") == "content-window" else []
        if not actual_text_boxes and witness:
            actual_text_boxes = [copy.deepcopy(b) for r in (witness.get("text_pattern") or {}).get("visible_ranges", [])
                                 for b in r.get("bounds", []) if positive(b)]
        font_witnesses = [witness] if witness else []
        if label:
            font_witnesses += [n for n in uia_nodes if n.get("control_type") == "ControlType.Text"
                               and n.get("name") == text and distance(n["bounds"], label["bounds"]) <= 8]
        rendered_fonts = []
        for font_source in font_witnesses:
            for text_range in (font_source.get("text_pattern") or {}).get("visible_ranges", []):
                for run in text_range.get("format_runs") or [text_range]:
                    family = run.get("attributes", {}).get("font_family")
                    if run.get("attribute_status", {}).get("font_family") != "measured" or not isinstance(family, str) or not family:
                        continue
                    identity = {"family_name": family, "postscript_name": None, "is_custom_font": None, "glyph_count": None,
                                "source": "UIA.TextPattern.FontNameAttribute", "uia_id": font_source["id"]}
                    if not any(f["family_name"] == family for f in rendered_fonts):
                        rendered_fonts.append(identity)
        style["rendered_fonts"] = rendered_fonts if text and rendered_fonts else None
        if text and not actual_text_boxes:
            unmeasured.append({"id": node["id"], "property": "evidence.text_bounds", "reason": "Actual window-relative text rectangles are unavailable"})
        if text and not rendered_fonts:
            unmeasured.append({"id": node["id"], "property": "style.rendered_fonts", "reason": "UIA did not measure the rendered font; declared XAML family is not substituted"})
        rich_runs = layout.get("rich_text_runs", [])
        rich_styles = {json.dumps({k: r.get(k) for k in ("font_size", "font_weight", "foreground")}, sort_keys=True) for r in rich_runs if r.get("text", "").strip()}
        if len(rich_styles) > 1:
            unmeasured.append({"id": node["id"], "property": "rich_text_runs", "reason": "Actual mixed run typography retained; separate visible run projection is still required"})
        if not text:
            layout = {"wrap": None, "truncation": None, "line_count": None}
            style["font_size"] = style["font_weight"] = None
            if kind not in {"icon", "chart-edge"}:
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
        element = {"id": node["id"], "parent": node.get("parent"), "region": region, "order": order[region], "kind": kind,
                   "text": text, "name": witness.get("name", "") if witness else node.get("accessible_name", ""),
                   "bounds": bounds, "visible_bounds": node["visible_bounds"], "style": style, "state": state,
                   "layout": {k: layout.get(k) for k in ("wrap", "truncation", "line_count")}, "icon": node.get("icon"),
                   "evidence": {"source": "XAML render tree + independent UIA", "type": typ, "uia_id": witness["id"] if witness else None,
                                "label_source": label["id"] if label else None, "paint_sources": [p["id"] for p in paints],
                                "font_family": node.get("font_family"), "pixel_samples": samples, "value": value,
                                "placeholder": node.get("layout", {}).get("placeholder"),
                                "text_bounds": actual_text_boxes, "text_coordinate_space": "content-window",
                                "rich_text_runs": rich_runs, "visible_fragments": fragments.get(node["id"]),
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
            "coverage": {"raw_nodes": len(raw) + len(uia.get("raw_nodes", [])), "emitted_elements": len(elements), "unmeasured": unmeasured},
            "projection": projection, "raw_evidence": {"xaml": Path(xaml_path).name, "uia": Path(uia_path).name}}
