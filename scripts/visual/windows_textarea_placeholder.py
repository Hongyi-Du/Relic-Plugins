"""Read actual already-applied NativeTextarea placeholder properties, not paint.

The text-part getter and retained visual parent identities bind this quantity.
It does not measure glyph faces, final pixels, text rectangles or other parts.
"""
from collections import Counter
from copy import deepcopy
import math


SOURCE = "Actual NativeTextarea.GetTemplateChild on its already-applied template"
STYLE_FIELDS = ("font_size", "font_weight", "foreground")


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def visible(node):
    box = node.get("visible_bounds")
    return (node.get("hidden_reason") is None and isinstance(box, dict)
            and all(finite(box.get(key)) for key in ("x", "y", "width", "height"))
            and box["width"] > 0 and box["height"] > 0
            and finite(node.get("opacity")) and node["opacity"] > 0)


def textarea_placeholder_styles(nodes):
    """Return only bound visible empty-input text styles; retain every raw node.

    Missing/changed proof leaves the measured text style unknown. No configured
    TextBox foreground substitutes for its currently displayed placeholder.
    """
    counts = Counter(node.get("id") for node in nodes)
    by_id = {node.get("id"): node for node in nodes if counts[node.get("id")] == 1}
    audits, styles, unmeasured = {}, {}, []
    for owner in nodes:
        if owner.get("type") != "NativeTextarea":
            continue
        owner_id = owner.get("id")
        receipt = owner.get("textarea_placeholder_evidence")
        placeholder = owner.get("layout", {}).get("placeholder")
        applicable = visible(owner) and owner.get("text") == "" and isinstance(placeholder, str) and bool(placeholder)
        audit = {"applicable": applicable, "owner_id": owner_id,
                 "owner_configured_style": {key: deepcopy(owner.get("style", {}).get(key)) for key in STYLE_FIELDS},
                 "raw_receipt": deepcopy(receipt), "source_id": None, "status": "not-applicable",
                 "quantity": "actual current placeholder TextBlock properties; not glyph/final-pixel measurement"}
        audits[owner_id] = audit
        if not applicable:
            continue

        def fail(reason):
            audit["status"] = "unmeasured"
            audit["reason"] = reason
            unmeasured.append({"id": owner_id, "property": "input.placeholder_style", "reason": reason})

        if (counts[owner_id] != 1 or not isinstance(receipt, dict) or receipt.get("source") != SOURCE
                or type(receipt.get("version")) is not int or receipt["version"] != 1
                or receipt.get("owner_id") != owner_id or receipt.get("status") != "measured"
                or receipt.get("read_only") is not True
                or receipt.get("template_part_name") != "PlaceholderTextContentPresenter"
                or receipt.get("part_runtime_type") != "Microsoft.UI.Xaml.Controls.TextBlock"
                or receipt.get("errors") != []
                or any(receipt.get(key) is not True for key in ("same_part_object_in_capture", "part_same_object_after",
                                                               "template_same_object_after", "getters_unchanged"))):
            fail("No complete stable actual already-applied placeholder object binding")
            continue
        part_id = receipt.get("part_id")
        part = by_id.get(part_id)
        state = receipt.get("before")
        if (not isinstance(state, dict) or state != receipt.get("after") or part is None
                or part.get("type") != "TextBlock" or part.get("text") != placeholder
                or state.get("value") != "" or state.get("placeholder") != placeholder
                or state.get("part_text") != placeholder or not visible(part)
                or any(state.get(key) is not True for key in ("owner_is_loaded", "part_is_loaded", "same_xaml_root"))
                or any(state.get(key) != "Visible" for key in ("owner_visibility", "part_visibility"))
                or any(not finite(state.get(key)) or state[key] <= 0 for key in ("owner_opacity", "part_opacity"))):
            fail("Current empty input, actual visible placeholder or window/getter state is missing or changed")
            continue
        edges = receipt.get("actual_ancestor_edges")
        current, seen, valid = part_id, set(), isinstance(edges, list) and bool(edges)
        for edge in edges if isinstance(edges, list) else []:
            child = by_id.get(current)
            if (not isinstance(edge, dict) or current in seen or child is None or edge.get("child_id") != current
                    or edge.get("parent_id") != child.get("parent") or edge.get("parent_id") not in by_id
                    or edge.get("actual_parent_in_visual_walk") is not True or edge.get("captured_parent_matches") is not True):
                valid = False
                break
            seen.add(current)
            current = edge["parent_id"]
            if current != owner_id and by_id[current].get("render_type_evidence", {}).get("is_control") is not False:
                valid = False
                break
        if not valid or current != owner_id:
            fail("Actual placeholder parent chain does not reach this owner without another control")
            continue
        part_style = part.get("style", {})
        snapshot = state.get("part_style")
        brush = snapshot.get("foreground_brush") if isinstance(snapshot, dict) else None
        color = part_style.get("foreground")
        if (not isinstance(snapshot, dict) or any(snapshot.get(key) != part_style.get(key) for key in STYLE_FIELDS)
                or not finite(part_style.get("font_size")) or part_style["font_size"] <= 0
                or not finite(part_style.get("font_weight")) or not 1 <= part_style["font_weight"] <= 1000
                or not isinstance(color, list) or len(color) != 4
                or any(not finite(component) or not 0 <= component <= 255 for component in color)
                or not isinstance(brush, dict) or brush.get("type") != "Microsoft.UI.Xaml.Media.SolidColorBrush"
                or brush.get("solid_rgba") != color):
            fail("Actual placeholder style/brush is unmeasured or differs from its retained current getter values")
            continue
        audit.update(status="measured", source_id=part_id, part_raw_style=deepcopy(part_style))
        styles[owner_id] = {key: deepcopy(part_style[key]) for key in STYLE_FIELDS}
    return {"audits": audits, "styles": styles, "unmeasured": unmeasured}


def apply_textarea_placeholder_style(style, audit, measured_style, visible_part):
    """Only three text-style fields change; container/geometry/parts stay intact."""
    if not audit or audit.get("applicable") is not True:
        return
    if audit.get("status") == "measured" and visible_part:
        style.update(deepcopy(measured_style))
    else:
        for field in STYLE_FIELDS:
            style[field] = None
