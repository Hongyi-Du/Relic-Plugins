"""Measure a narrow native Rectangle outer-corner quantity, never reference data.

The captured RadiusX/Y describe the centerline geometry. A nondegenerate,
circular, centered stroke has a nominal outer radius increased by half its
width. This is a style parameter, not an ink/occlusion or screenshot proof.
"""
import copy
import math
import struct


SDK_COMMIT = "da699b040bddc2a6adf660512a7c6db8a96bfbe3"
SDK_BASE = "https://github.com/microsoft/microsoft-ui-xaml/blob/" + SDK_COMMIT
STROKE_SOURCE = "Shape.StrokeThickness and full actual Shape.TransformToVisual(content-root) layout-axis endpoints; unit-difference diagnostics retained"


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def rectangle_outer_corner(node):
    geometry = node.get("shape_geometry_evidence")
    if not isinstance(geometry, dict):
        return None, "Actual Rectangle geometry input receipt is missing; the native default CornerRadius is not its contour"
    radius = node.get("shape_corner_radius") or {}
    width, height = geometry.get("actual_width"), geometry.get("actual_height")
    stroke, rx, ry = geometry.get("stroke_thickness"), radius.get("x"), radius.get("y")
    if (geometry.get("source") != "actual Rectangle layout and Shape inputs"
            or geometry.get("owner_id") != node.get("id")
            or geometry.get("runtime_type") != "Microsoft.UI.Xaml.Shapes.Rectangle"
            or (node.get("render_type_evidence") or {}).get("is_shape") is not True
            or node.get("paint_kind") != "rounded-rectangle"
            or geometry.get("stretch") != "Fill" or type(geometry.get("stretch_value")) is not int
            or geometry["stretch_value"] != 1 or geometry.get("stroke_is_null") is not False):
        return None, "Actual same-owner exact Rectangle, Fill stretch or present Stroke is unmeasured or unsupported"
    if (not all(finite(value) for value in (width, height, stroke, rx, ry))
            or min(width, height) <= 0 or not 0 < stroke < min(width, height)
            or not 0 < rx == ry or geometry.get("radius_x") != rx or geometry.get("radius_y") != ry):
        return None, "Actual Rectangle needs matching positive circular radii and a nondegenerate centered stroke"

    def f32(value):
        return struct.unpack("<f", struct.pack("<f", value))[0]

    try:
        if any(f32(value) != value for value in (width, height, stroke, rx, ry)):
            return None, "Recorded inputs are not exactly representable by the pinned SDK's XFLOAT geometry"
        inset = f32(stroke * .5)
        center_width, center_height = f32(width - stroke), f32(height - stroke)
        # The selected domain does not require interpreting radius clamping,
        # elliptic parallel curves, zero-radius joins or degenerate strokes.
        if not rx < min(f32(center_width * .5), f32(center_height * .5)):
            return None, "Radius reaches the centerline half-size; clamped or degenerate corners are not measured here"
        outer = f32(rx + inset)
    except (OverflowError, struct.error):
        return None, "Actual Rectangle inputs exceed the pinned SDK XFLOAT range"
    if not all(finite(value) and value > 0 for value in (inset, center_width, center_height, outer)):
        return None, "Native outline arithmetic does not yield a finite positive outer corner"

    transform = node.get("transform") or {}
    keys = ("m11", "m12", "m21", "m22", "offset_x", "offset_y")
    if (not all(finite(transform.get(key)) for key in keys)
            or [transform[key] for key in keys[:4]] != [1, 0, 0, 1]
            or node.get("axis_aligned_transform") is not True):
        return None, "Actual Rectangle requires a measured unit-translation transform; other transforms remain unknown"
    x, y = transform["offset_x"], transform["offset_y"]
    axes = node.get("stroke_evidence") or {}
    if (node.get("local_bounds") != {"x": 0, "y": 0, "width": width, "height": height}
            or node.get("bounds") != {"x": x, "y": y, "width": width, "height": height}
            or axes.get("source") != STROKE_SOURCE or axes.get("raw_width") != stroke
            or axes.get("scale_x") != 1 or axes.get("scale_y") != 1
            or axes.get("basis_x") != {"x": 1, "y": 0} or axes.get("basis_y") != {"x": 0, "y": 1}
            or axes.get("source_extent") != {"x": width, "y": height}
            or axes.get("origin") != {"x": x, "y": y}
            or axes.get("axis_endpoint_x") != {"x": x + width, "y": y}
            or axes.get("axis_endpoint_y") != {"x": x, "y": y + height}
            or (node.get("style") or {}).get("stroke_width") != stroke):
        return None, "Actual local/window dimensions and observed stroke-axis endpoints are inconsistent or missing"
    return {
        "sdk_source_commit": SDK_COMMIT,
        "sdk_sources": [SDK_BASE + "/src/dxaml/xcp/core/core/elements/rectangle.cpp#L194",
                        SDK_BASE + "/src/dxaml/xcp/core/core/elements/shape.cpp#L775",
                        SDK_BASE + "/src/dxaml/xcp/core/core/elements/rectangle.cpp#L878"],
        "coordinate_space": "window", "centerline_radius": rx, "stroke_inset": inset,
        "centerline_bounds": {"x": x + inset, "y": y + inset, "width": center_width, "height": center_height},
        "outer_radius": outer,
        "arithmetic": "Pinned XFLOAT GetOutlineRect inset=stroke/2, dimensions=actual-stroke; circular nominal outer radius=RadiusX+inset",
        "quantity": "Nominal circular outer boundary radius of the actual Rectangle centered stroke; not visible ink, dash coverage, clipping, antialiasing or frame equivalence",
    }, None


def project_rectangle_corners(element, node, unmeasured):
    if node.get("type") != "Rectangle":
        return
    original = {key: copy.deepcopy(node.get(key)) for key in (
        "shape_corner_radius", "shape_geometry_evidence", "stroke_evidence", "style", "transform",
        "local_bounds", "bounds", "visible_bounds", "clip", "ancestor_clip", "render_type_evidence")}
    proof = {"source": "Actual captured Rectangle inputs interpreted by the pinned native primitive geometry",
             "raw": original, "status": "unmeasured", "projected_fields": [],
             "occlusion_promoted": False, "raster_equivalence": None}
    element["evidence"]["rectangle_corners"] = proof
    element["style"]["corner_radius"] = element["style"]["corner_radii"] = None
    measured, reason = rectangle_outer_corner(node)
    if measured is None:
        proof["reason"] = reason
        unmeasured.append({"id": node["id"], "property": "style.corner_radius", "reason": reason})
        return
    proof.update(status="measured", geometry=measured, projected_fields=["corner_radius", "corner_radii"])
    element["style"]["corner_radius"] = measured["outer_radius"]
    element["style"]["corner_radii"] = [measured["outer_radius"]] * 4
