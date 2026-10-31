"""Actual retained bubble inset path ownership; no reference-derived paint.

The native D2D boolean operation is production geometry. Its current XAML
path/brush do not establish a raster callback, antialiasing or final PNG pixels.
"""
from collections import defaultdict
from copy import deepcopy
import math

SOURCE = "Actual retained Border inset-shadow path and original content composition"
OPERATION = "Production ID2D1Geometry.CombineWithGeometry EXCLUDE into native geometry sink"
PRESENTATION_GAP = "Native inset path geometry and brush properties do not measure final raster, antialiasing or PNG contribution"


def number(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def vector(value, count):
    return isinstance(value, list) and len(value) == count and all(number(x) for x in value)


def commands(value, native_output=False):
    if not isinstance(value, list) or not value:
        return False
    opened = False
    for item in value:
        if not isinstance(item, dict) or set(item) != {"kind", "values"}:
            return False
        kind = item["kind"]
        if not isinstance(kind, str):
            return False
        count = {"M": 2, "L": 2, "C": 6, "A": 4, "Z": 0}.get(kind)
        if count is None or not vector(item["values"], count) or native_output and kind == "A":
            return False
        if kind == "M":
            if opened:
                return False
            opened = True
        elif not opened:
            return False
        elif kind == "Z":
            opened = False
        elif kind == "A" and any(v <= 0 for v in item["values"][2:]):
            return False
    return not opened


def windows_inset_shadows(raw):
    by_id, children = defaultdict(list), defaultdict(list)
    for node in raw:
        by_id[node.get("id")].append(node)
        children[node.get("parent")].append(node.get("id"))
    result = {"owners": {}, "audits": {}, "unmeasured": []}
    for owner in raw:
        receipt = owner.get("native_inset_shadow")
        if not isinstance(receipt, dict):
            continue
        oid = owner.get("id")
        failures = []

        def require(value, why):
            if not value:
                failures.append(why)

        def unique(eid, typ):
            found = by_id.get(eid, []) if isinstance(eid, str) else []
            require(len(found) == 1 and found[0].get("type") == typ, "Retained " + typ + " is not a unique actual object")
            return found[0] if len(found) == 1 else {}

        require(receipt.get("source") == SOURCE and receipt.get("owner_id") == oid,
                "Inset receipt has no actual owner identity")
        require(owner.get("type") == "Border" and len(by_id[oid]) == 1, "Inset owner is not one actual Border")
        layout = unique(receipt.get("layout_id"), "Grid")
        canvas = unique(receipt.get("canvas_id"), "Canvas")
        path = unique(receipt.get("path_id"), "Path")
        content_id = receipt.get("content_id")
        require(isinstance(content_id, str) and len(by_id.get(content_id, [])) == 1, "Original content is not a unique actual object")
        require(layout.get("parent") == oid and canvas.get("parent") == layout.get("id")
                and path.get("parent") == canvas.get("id")
                and children.get(layout.get("id")) == [canvas.get("id"), content_id]
                and children.get(canvas.get("id")) == [path.get("id")], "Retained shadow/content parentage or paint order changed")
        for key in ("owner_child_is_layout", "layout_children_are_retained_parts", "canvas_child_is_path",
                    "current_path_same_object", "same_xaml_root", "owner_is_loaded", "path_is_loaded",
                    "current_layout_matches_operation", "actual_path_matches_operation"):
            require(receipt.get(key) is True, "Actual inset binding is not true: " + key)
        for key in ("path_hit_test_visible", "canvas_hit_test_visible", "path_stroke_present", "path_geometry_transform_present"):
            require(receipt.get(key) is False, "Inset path has unknown or independent interaction/paint: " + key)
        require(receipt.get("path_accessibility_view") == "Raw" and receipt.get("path_name") == "",
                "Inset decoration has an independent accessible element")
        require(receipt.get("failure") is None and receipt.get("observation_failure") is None,
                "Production inset operation or actual observation failed")
        operation = receipt.get("operation") if isinstance(receipt.get("operation"), dict) else {}
        require(operation.get("source") == OPERATION and operation.get("operation") == "exclude-translated-self"
                and operation.get("failure") is None, "Inset has no successful production exclude operation")
        for key in ("create_path_hresult", "open_hresult", "close_hresult", "combine_hresult"):
            require(type(operation.get(key)) is int and operation[key] >= 0, "Native geometry API did not succeed: " + key)
        require(commands(operation.get("input_commands")) and commands(operation.get("output_commands"), True)
                and commands(receipt.get("actual_path_commands"), True)
                and operation.get("output_commands") == receipt.get("actual_path_commands"), "Actual path differs from its native operation output")
        require(type(operation.get("output_fill_mode")) is int and operation["output_fill_mode"] in (0, 1)
                and receipt.get("path_fill_rule") == ("EvenOdd" if operation.get("output_fill_mode") == 0 else "Nonzero"), "Actual native/XAML fill rule is not bound")
        bounds = owner.get("bounds") if isinstance(owner.get("bounds"), dict) else {}
        path_bounds = path.get("bounds") if isinstance(path.get("bounds"), dict) else {}
        local = owner.get("local_bounds") if isinstance(owner.get("local_bounds"), dict) else {}
        path_local = path.get("local_bounds") if isinstance(path.get("local_bounds"), dict) else {}
        size = receipt.get("actual_size")
        owner_local = [local.get(k) for k in ("x", "y", "width", "height")]
        path_local_box = [path_local.get(k) for k in ("x", "y", "width", "height")]
        # These are all actual local layout dimensions. TransformBounds returns
        # a different (window-space) quantity and can round its extents even for
        # a translation. Compare those actual window boxes to each other below.
        require(vector(size, 2) and min(size) > 0 and vector(owner_local, 4)
                and owner_local[:2] == [0, 0] and size == owner_local[2:]
                and vector(path_local_box, 4) and path_local_box == owner_local
                and vector(receipt.get("path_size"), 2) and receipt["path_size"] == size
                and receipt.get("path_stretch") == "None", "Inset dimensions are not the current actual owner/path dimensions")
        window_box = [bounds.get(k) for k in ("x", "y", "width", "height")]
        path_window_box = [path_bounds.get(k) for k in ("x", "y", "width", "height")]
        require(vector(window_box, 4) and min(window_box[2:]) > 0
                and vector(path_window_box, 4) and path_window_box == window_box,
                "Actual inset owner/path window bounds disagree or are unmeasured")
        require(vector(receipt.get("actual_path_to_owner"), 6) and receipt["actual_path_to_owner"] == [1, 0, 0, 1, 0, 0],
                "Actual inset geometry is not in its owner's coordinate space")
        owner_style = owner.get("style") if isinstance(owner.get("style"), dict) else {}
        require(vector(receipt.get("actual_radii"), 4) and receipt["actual_radii"] == owner_style.get("corner_radii")
                and vector(receipt.get("actual_border_widths"), 4) and receipt["actual_border_widths"] == owner_style.get("border_widths"),
                "Inset current corner/border geometry is not bound to actual owner style")
        widths, radii = receipt.get("actual_border_widths"), receipt.get("actual_radii")
        if vector(size, 2) and vector(widths, 4) and vector(radii, 4) and min(size) > 0 and min(widths + radii) >= 0:
            width, height = size; top, right, bottom, left = widths; tl, tr, br, bl = radii
            factor = min([1] + [extent / total for extent, total in
                              ((width, tl + tr), (width, bl + br), (height, tl + bl), (height, tr + br)) if total > 0])
            tl, tr, br, bl = [r * factor for r in radii]
            inner = [max(0, tl - left), max(0, tl - top), max(0, tr - right), max(0, tr - top),
                     max(0, br - right), max(0, br - bottom), max(0, bl - left), max(0, bl - bottom)]
            edge = [left, top, width - left - right, height - top - bottom]
            require(min(edge[2:]) > 0 and vector(operation.get("padding_edge"), 4)
                    and vector(operation.get("padding_radii"), 8)
                    and operation["padding_edge"] == edge and operation["padding_radii"] == inner,
                    "Native operation's padding contour is not derived from the actual current Border")
        else:
            require(False, "Actual padding contour inputs are missing or invalid")
        transform = owner.get("transform") if isinstance(owner.get("transform"), dict) else {}
        path_transform = path.get("transform") if isinstance(path.get("transform"), dict) else {}
        transform_keys = ("m11", "m12", "m21", "m22", "offset_x", "offset_y")
        owner_affine = [transform.get(k) for k in transform_keys]
        path_affine = [path_transform.get(k) for k in transform_keys]
        require(vector(owner_affine, 6) and owner_affine[:4] == [1, 0, 0, 1]
                and vector(path_affine, 6) and path_affine == owner_affine
                and owner_affine[4:] == window_box[:2]
                and owner.get("axis_aligned_transform") is True and path.get("axis_aligned_transform") is True,
                "Inset window-space style requires matching actual unit-axis owner/path transforms")
        color = receipt.get("path_fill_rgba8")
        opacity = receipt.get("path_fill_opacity")
        require(receipt.get("path_fill_type") == "SolidColorBrush" and vector(color, 4) and all(0 <= x <= 255 for x in color)
                and number(opacity) and 0 <= opacity <= 1 and number(receipt.get("path_opacity")) and receipt["path_opacity"] == 1
                and number(receipt.get("path_stroke_thickness")) and receipt["path_stroke_thickness"] == 0,
                "Inset current fill/stroke properties are unknown")
        if vector(color, 4) and number(opacity):
            rgba = list(color); rgba[3] *= opacity
            path_style = path.get("style") if isinstance(path.get("style"), dict) else {}
            brushes = path_style.get("brush_evidence") if isinstance(path_style.get("brush_evidence"), dict) else {}
            fill = brushes.get("background") if isinstance(brushes.get("background"), dict) else {}
            # CaptureStyle(Shape) records Stroke as foreground and Fill as
            # background. Only the latter measures this filled inset path.
            require(vector(path_style.get("background"), 4) and path_style["background"] == rgba
                    and fill.get("type") == "Microsoft.UI.Xaml.Media.SolidColorBrush"
                    and number(fill.get("opacity")) and fill["opacity"] == opacity
                    and vector(fill.get("solid_color_rgba8"), 4) and fill["solid_color_rgba8"] == color
                    and vector(fill.get("solid_rgba"), 4) and fill["solid_rgba"] == rgba,
                    "Actual Path Fill/background disagrees with its retained brush observation")
        require(all(number(node.get("opacity")) for node in (owner, path, canvas, layout))
                and 0 <= owner["opacity"] <= 1 and path.get("opacity") == owner["opacity"]
                and canvas.get("opacity") == owner["opacity"] and layout.get("opacity") == owner["opacity"],
                "Decorative ancestors change or do not expose the actual path opacity")
        require(number(operation.get("offset_x")) and number(operation.get("offset_y"))
                and number(operation.get("flattening_tolerance")) and operation["flattening_tolerance"] > 0,
                "Native exclude translation or production approximation is unknown")
        audit = {"owner_id": oid, "path_id": path.get("id"), "receipt": deepcopy(receipt),
                 "actual_path": deepcopy(path), "issues": failures,
                 "presentation_identity_proven": False, "paint_quantity": PRESENTATION_GAP}
        result["audits"][oid] = audit
        for why in [*failures, PRESENTATION_GAP]:
            result["unmeasured"].append({"id": oid, "property": "native_inset_shadow", "reason": why})
        if not failures:
            rgba = list(color); rgba[3] *= opacity
            audit["shadow"] = [{"inset": True, "offset_x": operation["offset_x"], "offset_y": operation["offset_y"],
                                "blur_radius": 0, "spread_radius": 0, "color": rgba}]
            result["owners"][oid] = audit
    return result
