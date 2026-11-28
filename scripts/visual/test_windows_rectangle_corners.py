"""Pure synthetic input tests; actual native captures remain a separate CI check."""
import copy
import unittest

from windows_rectangle_corners import STROKE_SOURCE, project_rectangle_corners


def rectangle():
    return {
        "id": "shape", "type": "Rectangle", "paint_kind": "rounded-rectangle",
        "render_type_evidence": {"is_shape": True},
        "shape_corner_radius": {"x": 4, "y": 4},
        "shape_geometry_evidence": {
            "source": "actual Rectangle layout and Shape inputs", "owner_id": "shape",
            "runtime_type": "Microsoft.UI.Xaml.Shapes.Rectangle", "stretch": "Fill", "stretch_value": 1,
            "actual_width": 18, "actual_height": 12, "stroke_is_null": False, "stroke_thickness": 1,
            "radius_x": 4, "radius_y": 4,
        },
        "local_bounds": {"x": 0, "y": 0, "width": 18, "height": 12},
        "bounds": {"x": 100, "y": 20, "width": 18, "height": 12},
        "visible_bounds": {"x": 100, "y": 20, "width": 18, "height": 12},
        "transform": {"m11": 1, "m12": 0, "m21": 0, "m22": 1, "offset_x": 100, "offset_y": 20},
        "axis_aligned_transform": True,
        "stroke_evidence": {"source": STROKE_SOURCE, "raw_width": 1, "scale_x": 1, "scale_y": 1,
                            "basis_x": {"x": 1, "y": 0}, "basis_y": {"x": 0, "y": 1},
                            "source_extent": {"x": 18, "y": 12}, "origin": {"x": 100, "y": 20},
                            "axis_endpoint_x": {"x": 118, "y": 20}, "axis_endpoint_y": {"x": 100, "y": 32},
                            "raw_pattern": {"dash_array": []}},
        "style": {"stroke_width": 1, "corner_radius": 0, "corner_radii": [0, 0, 0, 0],
                  "background": [255, 255, 255, 255], "border_width": 0, "shadow": None},
    }


class RectangleCornerTests(unittest.TestCase):
    def project(self, node):
        element = {"style": copy.deepcopy(node["style"]), "evidence": {}}
        issues = []
        project_rectangle_corners(element, node, issues)
        return element, issues

    def test_actual_centerline_radius_and_stroke_produce_outer_not_reference_radius(self):
        node = rectangle()
        original = copy.deepcopy(node)
        element, issues = self.project(node)
        self.assertEqual(issues, [])
        self.assertEqual(node, original)
        self.assertEqual(element["style"]["corner_radius"], 4.5)
        self.assertEqual(element["style"]["corner_radii"], [4.5] * 4)
        proof = element["evidence"]["rectangle_corners"]
        self.assertEqual(proof["geometry"]["centerline_bounds"], {"x": 100.5, "y": 20.5, "width": 17, "height": 11})
        self.assertEqual(proof["raw"]["style"]["corner_radius"], 0)
        self.assertFalse(proof["occlusion_promoted"])
        self.assertIsNone(proof["raster_equivalence"])
        for key in original["style"]:
            if key not in ("corner_radius", "corner_radii"):
                self.assertEqual(element["style"][key], original["style"][key])

    def test_another_actual_radius_is_measured_without_a_fixed_output(self):
        node = rectangle()
        node["shape_corner_radius"] = {"x": 2, "y": 2}
        node["shape_geometry_evidence"].update(radius_x=2, radius_y=2)
        element, issues = self.project(node)
        self.assertEqual(issues, [])
        self.assertEqual(element["style"]["corner_radius"], 2.5)

    def test_dashes_and_partial_visibility_do_not_become_opaque_contour_evidence(self):
        node = rectangle()
        node["stroke_evidence"]["raw_pattern"]["dash_array"] = [4.5, 4.5]
        node["visible_bounds"]["width"] = 5
        node["clip"] = {"type": "UnmeasuredActualGeometry"}
        element, issues = self.project(node)
        self.assertEqual(issues, [])
        proof = element["evidence"]["rectangle_corners"]
        self.assertEqual(proof["geometry"]["outer_radius"], 4.5)
        self.assertEqual(proof["raw"]["stroke_evidence"]["raw_pattern"]["dash_array"], [4.5, 4.5])
        self.assertEqual(proof["raw"]["clip"], node["clip"])
        self.assertFalse(proof["occlusion_promoted"])

    def test_missing_stretch_receipt_and_wrong_owner_do_not_retrofit_old_captures(self):
        for change in ("missing", "owner", "runtime", "stretch", "stretch_enum", "shape_type", "stroke_absent"):
            with self.subTest(change=change):
                node = rectangle()
                geometry = node["shape_geometry_evidence"]
                if change == "missing": del node["shape_geometry_evidence"]
                elif change == "owner": geometry["owner_id"] = "another"
                elif change == "runtime": geometry["runtime_type"] = "Relic.RectangleSubclass"
                elif change == "stretch": geometry["stretch"] = "None"
                elif change == "stretch_enum": geometry["stretch_value"] = True
                elif change == "shape_type": node["render_type_evidence"]["is_shape"] = False
                elif change == "stroke_absent": geometry["stroke_is_null"] = True
                element, issues = self.project(node)
                self.assertIsNone(element["style"]["corner_radius"])
                self.assertIsNone(element["style"]["corner_radii"])
                self.assertTrue(issues)

    def test_unmeasured_or_unsupported_corner_inputs_never_fall_back_to_zero(self):
        for change in ("missing_radius", "changed_radius", "ellipse", "clamped", "nan", "degenerate", "negative", "float_precision"):
            with self.subTest(change=change):
                node = rectangle()
                geometry = node["shape_geometry_evidence"]
                if change == "missing_radius": del node["shape_corner_radius"]
                elif change == "changed_radius": geometry["radius_x"] = 3
                elif change == "ellipse": node["shape_corner_radius"]["y"] = geometry["radius_y"] = 3
                elif change == "clamped": node["shape_corner_radius"] = {"x": 6, "y": 6}; geometry.update(radius_x=6, radius_y=6)
                elif change == "nan": geometry["actual_width"] = float("nan")
                elif change == "degenerate": geometry["stroke_thickness"] = 12
                elif change == "negative": geometry["stroke_thickness"] = -1
                elif change == "float_precision": node["shape_corner_radius"] = {"x": .1, "y": .1}; geometry.update(radius_x=.1, radius_y=.1)
                element, issues = self.project(node)
                self.assertIsNone(element["style"]["corner_radius"])
                self.assertTrue(issues)

    def test_actual_transform_and_local_dimensions_must_agree(self):
        for change in ("scaled", "skew", "missing_transform", "bounds", "local", "axis", "stroke"):
            with self.subTest(change=change):
                node = rectangle()
                if change == "scaled": node["transform"]["m11"] = 2
                elif change == "skew": node["transform"]["m12"] = .25
                elif change == "missing_transform": del node["transform"]
                elif change == "bounds": node["bounds"]["width"] = 17
                elif change == "local": node["local_bounds"]["width"] = 17
                elif change == "axis": node["stroke_evidence"]["axis_endpoint_y"]["y"] = 33
                elif change == "stroke": node["style"]["stroke_width"] = 2
                element, issues = self.project(node)
                self.assertIsNone(element["style"]["corner_radius"])
                self.assertTrue(issues)

    def test_other_shapes_are_unchanged(self):
        node = rectangle(); node["type"] = "Ellipse"
        element, issues = self.project(node)
        self.assertEqual(element["style"], node["style"])
        self.assertEqual(element["evidence"], {})
        self.assertEqual(issues, [])
