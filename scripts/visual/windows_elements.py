"""Project independently measured UIA + XAML evidence; never read reference data.

Raw records and projection ownership are retained for audit. Incomplete paint,
visibility or typography measurements fail coverage instead of being guessed.
"""
import copy
import json
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
    return bool(box and box.get("width", 0) > 0 and box.get("height", 0) > 0)


def distance(a, b):
    return sum(abs(a.get(k, 0) - b.get(k, 0)) for k in ("x", "y", "width", "height"))


def painted(color):
    return isinstance(color, list) and len(color) == 4 and color[3] > 0


def uia_kind_matches(node, kind):
    control_type = node.get("control_type", "").removeprefix("ControlType.")
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
        return not node.get("hidden_reason") and positive(node.get("visible_bounds"))

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
    order = defaultdict(int)
    for node in raw:
        if not visible(node):
            projection.append({"source": node["id"], "reason": node.get("hidden_reason", "not a visible rendered box")})
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
            if painted(style.get("background")) or painted(style.get("border_color")) and style.get("border_width", 0) > 0:
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
            if not painted(ps.get("background")) and not (painted(ps.get("border_color")) and ps.get("border_width", 0) > 0):
                continue
            if painted(ps.get("background")):
                style["background"] = ps["background"]
            if painted(ps.get("border_color")) and ps.get("border_width", 0) > 0:
                for key in ("border_color", "border_width", "corner_radius"):
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
        for key in ("background", "border_color", "corner_radius"):
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
                                "placeholder": node.get("layout", {}).get("placeholder")}}
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
        # A UIA text child can already be represented by the owning control's
        # label. Preserve the measured ownership instead of silently losing it.
        owner = next((e for e in elements if n.get("control_type") == "ControlType.Text" and n.get("name") and n.get("name") == e["text"] and e["bounds"]["x"] <= b["x"] and e["bounds"]["y"] <= b["y"] and b["x"] + b["width"] <= e["bounds"]["x"] + e["bounds"]["width"] + 1 and b["y"] + b["height"] <= e["bounds"]["y"] + e["bounds"]["height"] + 1), None)
        if owner:
            projection.append({"source": n["id"], "owner": owner["id"], "reason": "UIA label owned by corresponding rendered control"})
        elif n.get("is_control_element") or n.get("is_content_element"):
            unmeasured.append({"id": n["id"], "property": "render correspondence", "reason": "Visible UIA node not represented in XAML projection", "control_type": n.get("control_type"), "name": n.get("name")})
    # Rectangular ancestor clipping is measured. Arbitrary overlay paint/rounded
    # occlusion still needs a verified visibility mask; surface this gap now.
    unmeasured.append({"property": "occlusion", "reason": "Exact opaque overlay paint masks not yet measured; raw trees retained"})
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
