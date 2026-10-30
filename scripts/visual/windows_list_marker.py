"""Retained WinUI list-disc identity and actual Ellipse layout/property evidence.

An Ellipse is not a bullet glyph. Its property/arrange receipt is also not a
framework raster callback, a final-PNG observation, or measured reference paint.
"""
from copy import deepcopy
from collections import defaultdict
import math


SOURCE = "Actual retained native list-disc owner and Ellipse child"
ARRANGE = "Production NativeListMarker.ArrangeOverride -> actual Ellipse.Arrange"
TRANSFORM = "actual retained Ellipse.TransformToVisual(windowContent)"
FONT = "Actual production disc primary font: system collection FindFamilyName/GetFirstMatchingFont/CreateFontFace/GetMetrics"
AXIS = ("m11", "m12", "m21", "m22", "offset_x", "offset_y")
RECT = ("x", "y", "width", "height")
PRESENTATION_GAP = "Native Ellipse properties/current arrangement do not measure the framework raster callback, antialiasing, or final-PNG contribution"


def number(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def vector(value, size):
    return isinstance(value, list) and len(value) == size and all(number(x) for x in value)


def rect(value):
    return isinstance(value, dict) and all(number(value.get(k)) for k in RECT) and value["width"] > 0 and value["height"] > 0


def rgba(value):
    return vector(value, 4) and all(0 <= x <= 255 for x in value)


def mapping(value):
    return value if isinstance(value, dict) else {}


def _read(owner, by_id, children):
    receipt = owner.get("native_list_marker_evidence")
    result = {"owner_id": owner.get("id"), "identity_valid": False, "geometry_valid": False,
              "style_valid": False, "draw_callback_observed": False, "presentation_identity_proven": False,
              "ellipse_id": None, "alternative_text": None, "measurements": None,
              "foreground": None, "opacity": None, "binding_issues": [], "measurement_issues": [], "issues": []}
    bindings, measurements = result["binding_issues"], result["measurement_issues"]

    def require(condition, reason, target=bindings):
        if not condition:
            target.append(reason)

    def unique(eid, typ, label):
        values = by_id.get(eid, []) if isinstance(eid, str) else []
        require(len(values) == 1 and values[0].get("type") == typ, label + " is not a unique actual " + typ)
        return values[0] if len(values) == 1 else {}

    require(owner.get("type") == "NativeListMarker", "Marker owner is not the actual production NativeListMarker type")
    require(isinstance(receipt, dict) and receipt.get("source") == SOURCE, "Missing actual retained marker/Ellipse receipt")
    if not isinstance(receipt, dict):
        result["issues"] = bindings[:]
        return result
    require(receipt.get("owner_id") == owner.get("id"), "Marker receipt belongs to a different rendered owner")
    ellipse = unique(receipt.get("ellipse_id"), "Ellipse", "Retained disc")
    item = unique(receipt.get("item_text_id"), "RichTextBlock", "Actual list item text")
    window_id = receipt.get("window_content_id")
    window_values = by_id.get(window_id, []) if isinstance(window_id, str) else []
    require(len(window_values) == 1 and window_values[0].get("parent") is None, "Actual window content root is missing or ambiguous")
    window = window_values[0] if len(window_values) == 1 else {}
    parent_id = owner.get("parent")
    parent_values = by_id.get(parent_id, []) if isinstance(parent_id, str) else []
    require(len(parent_values) == 1 and parent_values[0].get("type") == "NativeListItemPanel", "Marker has no actual list-item layout parent")
    parent = parent_values[0] if len(parent_values) == 1 else {}
    require(item.get("parent") == owner.get("parent"), "Retained item text is outside the actual marker row")
    require(receipt.get("same_direct_child") is True and ellipse.get("parent") == owner.get("id")
            and receipt.get("ellipse_parent_id") == owner.get("id"), "Disc is not the retained direct child of this owner")
    require([node.get("id") for node in children.get(owner.get("id"), [])] == [receipt.get("ellipse_id")],
            "Marker has extra or ambiguous child paint; it cannot be absorbed into one disc")
    require(all(receipt.get(k) is True for k in ("owner_is_loaded", "ellipse_is_loaded", "same_window_xaml_root")),
            "Marker/disc is unmounted or belongs to another actual XamlRoot")
    alternative = receipt.get("alternative_text")
    require(isinstance(alternative, str) and bool(alternative) and owner.get("accessible_name") == alternative,
            "Marker spoken alternative differs from its actual AutomationProperties.Name")
    require(owner.get("text") == "", "Native disc has unexpected visible text; an AX alternative is not glyph paint")
    require(receipt.get("symbol") == "disc" and receipt.get("ellipse_is_hit_test_visible") is False,
            "The retained shape is not the noninteractive disc decoration")
    require(receipt.get("draw_callback_observed") is False and receipt.get("presentation_identity_proven") is False,
            "Native property receipt cannot claim a framework draw callback or final presentation")
    result["identity_valid"] = not bindings
    result["ellipse_id"] = ellipse.get("id"); result["alternative_text"] = alternative
    # Retain precisely the actual records used here. The complete original tree
    # also remains in the capture artifact; no coordinates or labels are synthesized.
    result["raw_nodes"] = [deepcopy(n) for n in (owner, parent, window) if n]
    # Unexpected direct children must survive revalidation too. A failed
    # ownership check must not become valid merely by exporting a smaller tree.
    result["raw_nodes"].extend(deepcopy(children.get(owner.get("id"), [])))
    if ellipse and ellipse.get("parent") != owner.get("id"):
        result["raw_nodes"].append(deepcopy(ellipse))
    if item:
        result["raw_nodes"].append({key: deepcopy(item.get(key)) for key in ("id", "parent", "type")})

    arranged = receipt.get("current_arrangement")
    require(isinstance(arranged, dict) and arranged.get("source") == ARRANGE, "No production Ellipse.Arrange receipt", measurements)
    if not isinstance(arranged, dict):
        arranged = {}
    require(receipt.get("failure") is None and receipt.get("coordinate_failure") is None
            and arranged.get("failure") is None, "Native marker reports a layout/coordinate failure", measurements)
    require(arranged.get("presentation_identity_proven") is False,
            "Current arrangement cannot assert final presentation identity", measurements)
    require(isinstance(arranged.get("sequence"), int) and not isinstance(arranged.get("sequence"), bool) and arranged["sequence"] > 0,
            "Missing actual arrangement sequence", measurements)
    require(receipt.get("current_arrangement_matches_actual_geometry") is True,
            "Last marker arrangement is not bound to its current actual Ellipse geometry", measurements)
    local = receipt.get("actual_local_ellipse"); window_box = receipt.get("ellipse_window_bounds")
    require(rect(local) and local == arranged.get("arranged_local_ellipse"), "Actual local ellipse differs from its current production arrangement", measurements)
    require(rect(owner.get("local_bounds")) and vector(arranged.get("owner_size"), 2)
            and arranged["owner_size"] == [owner.get("local_bounds", {}).get("width"), owner.get("local_bounds", {}).get("height")],
            "Actual marker allocation changed since its arrangement", measurements)
    size = receipt.get("ellipse_actual_size")
    require(vector(size, 2) and rect(local) and size == [local["width"], local["height"]], "Actual Ellipse size differs from its recorded local shape", measurements)
    transform = receipt.get("ellipse_to_window")
    require(isinstance(transform, dict) and transform.get("source") == TRANSFORM
            and all(number(transform.get(k)) for k in AXIS), "Missing actual Ellipse-to-window coordinate conversion", measurements)
    require(rect(window_box) and window_box == ellipse.get("bounds"), "Actual window ellipse differs from the retained raw Ellipse bounds", measurements)
    if isinstance(transform, dict) and all(number(transform.get(k)) for k in AXIS) and vector(size, 2):
        points = [(transform["offset_x"] + x * transform["m11"] + y * transform["m21"],
                   transform["offset_y"] + x * transform["m12"] + y * transform["m22"])
                  for x, y in ((0, 0), (size[0], 0), (0, size[1]), (size[0], size[1]))]
        converted = {"x": min(x for x, _ in points), "y": min(y for _, y in points),
                     "width": max(x for x, _ in points) - min(x for x, _ in points),
                     "height": max(y for _, y in points) - min(y for _, y in points)}
        require(rect(converted) and converted == window_box, "Recorded actual Ellipse transform does not produce its window envelope", measurements)
        require(isinstance(ellipse.get("transform"), dict) and all(transform[k] == ellipse["transform"].get(k) for k in AXIS),
                "Independent raw Ellipse transform differs from the marker receipt", measurements)
    basis = mapping(arranged.get("coordinate_basis"))
    require(basis.get("source") == "actual marker.TransformToVisual(XamlRoot.Content) and XamlRoot.RasterizationScale"
            and all(vector(basis.get(k), 2) for k in ("origin", "unit_x", "unit_y"))
            and number(basis.get("rasterization_scale")) and basis["rasterization_scale"] > 0
            and receipt.get("actual_rasterization_scale") == basis["rasterization_scale"], "Actual device-space snapping basis is missing or changed", measurements)
    font = mapping(receipt.get("actual_primary_font"))
    require(font.get("source") == FONT and isinstance(font.get("selected_family"), str)
            and bool(font["selected_family"]) and number(font.get("requested_size")) and font["requested_size"] > 0
            and number(font.get("units_per_em")) and font["units_per_em"] > 0
            and number(font.get("native_ascent")) and font["native_ascent"] > 0
            and number(font.get("native_descent")) and font["native_descent"] >= 0,
            "Missing actual primary metrics used by the native disc layout", measurements)
    result["geometry_valid"] = result["identity_valid"] and not measurements

    style_issues = []
    style = mapping(ellipse.get("style"))
    fill, opacity = receipt.get("ellipse_fill_rgba8"), receipt.get("ellipse_fill_opacity")
    require(receipt.get("ellipse_fill_type") == "Microsoft.UI.Xaml.Media.SolidColorBrush" and rgba(fill)
            and number(opacity) and 0 <= opacity <= 1, "Disc has no measured current SolidColorBrush fill", style_issues)
    require(receipt.get("ellipse_has_stroke") is False and number(receipt.get("ellipse_stroke_thickness"))
            and receipt["ellipse_stroke_thickness"] == 0 and style.get("stroke_width") == 0,
            "Native disc has additional or unknown stroke paint", style_issues)
    require(receipt.get("ellipse_visibility") == "Visible" and number(receipt.get("ellipse_opacity"))
            and 0 <= receipt["ellipse_opacity"] <= 1 and number(style.get("opacity")) and 0 <= style["opacity"] <= 1,
            "Disc visibility/opacity is not actually measured", style_issues)
    if rgba(fill) and number(opacity):
        actual = fill[:3] + [fill[3] * opacity]
        require(style.get("foreground") == actual, "Actual shape foreground differs from retained fill/brush opacity", style_issues)
        brush = mapping(mapping(style.get("brush_evidence")).get("foreground"))
        require(brush.get("type") == receipt.get("ellipse_fill_type") and brush.get("solid_color_rgba8") == fill
                and brush.get("opacity") == opacity, "Raw Ellipse brush is not the same observed fill quantity", style_issues)
        if not style_issues and result["identity_valid"]:
            result["foreground"] = actual; result["opacity"] = style["opacity"]
    result["style_valid"] = result["identity_valid"] and not style_issues
    result["measurement_issues"].extend(style_issues)
    if result["geometry_valid"]:
        result["measurements"] = {"local_ellipse": deepcopy(local), "window_ellipse_envelope": deepcopy(window_box),
            "ellipse_to_window": deepcopy(transform), "device_basis": deepcopy(basis),
            "quantity": "Current retained native Ellipse geometry properties and transforms; not sampled paint/ink"}
    result["issues"] = bindings + result["measurement_issues"] + [PRESENTATION_GAP]
    return result


def windows_list_markers(raw_nodes):
    by_id, children = defaultdict(list), defaultdict(list)
    for node in raw_nodes:
        if not isinstance(node, dict):
            continue
        if isinstance(node.get("id"), str):
            by_id[node["id"]].append(node)
        if isinstance(node.get("parent"), str):
            children[node["parent"]].append(node)
    owners, audits, issues = {}, {}, []
    for owner in raw_nodes:
        if not isinstance(owner, dict):
            continue
        if owner.get("type") != "NativeListMarker" and "native_list_marker_evidence" not in owner:
            continue
        if not isinstance(owner.get("id"), str) or not owner["id"]:
            issues.append({"id": None, "property": "native_list_marker", "reason": "Marker owner has no usable actual render ID"})
            continue
        audit = _read(owner, by_id, children)
        if len(by_id[owner.get("id")]) != 1:
            audit["identity_valid"] = False; audit["issues"].append("Duplicate marker owner ID")
        audits[owner.get("id")] = audit
        if audit["identity_valid"]:
            owners[owner["id"]] = audit
        for reason in audit["issues"]:
            issues.append({"id": owner.get("id"), "property": "native_list_marker", "reason": reason})
    return {"owners": owners, "audits": audits, "unmeasured": issues}


def windows_list_marker_issues(element):
    evidence = mapping(element.get("evidence"))
    if evidence.get("type") != "NativeListMarker" and "native_list_marker" not in evidence:
        return []
    audit = evidence.get("native_list_marker")
    if not isinstance(audit, dict) or not isinstance(audit.get("raw_nodes"), list):
        return ["Native marker has no retained owner/Ellipse raw evidence"]
    measured = windows_list_markers(audit["raw_nodes"])
    actual = measured["audits"].get(element.get("id"))
    if actual is None:
        return ["Native marker evidence belongs to another actual owner"]
    issues = actual["issues"][:]
    if element.get("kind") != "icon" or element.get("text") != "" or element.get("name") != actual["alternative_text"]:
        issues.append("Native marker must keep icon kind, empty painted text and its actual spoken alternative")
    owner = next((n for n in actual.get("raw_nodes", []) if n.get("id") == element.get("id")), {})
    if element.get("bounds") != owner.get("bounds"):
        issues.append("Native marker allocation must remain its actual owner bounds, separate from the ellipse envelope")
    if actual["style_valid"]:
        style = mapping(element.get("style"))
        if style.get("foreground") != actual["foreground"] or style.get("opacity") != actual["opacity"]:
            issues.append("Native marker style differs from its actual retained Ellipse brush/opacity")
    if actual["identity_valid"] and element.get("icon") != {"source": "geometry", "primitive": "ellipse", "glyph": None, "path": None}:
        issues.append("Actual native disc properties do not supply a glyph or a measured raster/vector paint identity")
    if audit.get("draw_callback_observed") is not False or audit.get("presentation_identity_proven") is not False:
        issues.append("Retained property/layout evidence cannot be promoted to observed draw/presentation")
    return issues
