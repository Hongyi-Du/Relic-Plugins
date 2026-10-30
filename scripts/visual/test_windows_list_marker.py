"""Synthetic actual-receipt-shaped fixtures; no native UI is created by these tests.

The fixture is not a recorded successful paint or final-PNG measurement. Tests
exercise ownership and coordinate/property validation while retaining that gap.
"""
from copy import deepcopy
import unittest

from windows_list_marker import (ARRANGE, FONT, PRESENTATION_GAP, SOURCE, TRANSFORM,
                                 windows_list_markers, windows_list_marker_issues)


def box(x, y, width, height):
    return {"x": x, "y": y, "width": width, "height": height}


def fixture():
    local = box(1, 7, 5, 5)
    window = box(51, 107, 5, 5)
    transform = {"m11": 1, "m12": 0, "m21": 0, "m22": 1, "offset_x": 51, "offset_y": 107}
    color = [27, 27, 26, 255]
    brush = {"type": "Microsoft.UI.Xaml.Media.SolidColorBrush", "solid_color_rgba8": color[:], "opacity": 1}
    receipt = {
        "source": SOURCE, "owner_id": "marker", "ellipse_id": "ellipse", "ellipse_parent_id": "marker",
        "same_direct_child": True, "owner_is_loaded": True, "ellipse_is_loaded": True,
        "symbol": "disc", "alternative_text": "• ", "item_text_id": "body", "window_content_id": "root",
        "actual_primary_font": {"source": FONT, "selected_family": "Synthetic Primary", "requested_size": 13.5,
                                "units_per_em": 2048, "native_ascent": 13, "native_descent": 5},
        "current_arrangement": {"source": ARRANGE, "sequence": 3, "owner_size": [7, 18],
            "arranged_local_ellipse": deepcopy(local), "failure": None, "presentation_identity_proven": False,
            "coordinate_basis": {"source": "actual marker.TransformToVisual(XamlRoot.Content) and XamlRoot.RasterizationScale",
                "origin": [50, 100], "unit_x": [51, 100], "unit_y": [50, 101], "rasterization_scale": 1}},
        "ellipse_actual_size": [5, 5], "ellipse_stroke_thickness": 0, "ellipse_has_stroke": False,
        "ellipse_fill_type": brush["type"], "ellipse_fill_rgba8": color[:], "ellipse_fill_opacity": 1,
        "ellipse_opacity": 1, "ellipse_visibility": "Visible", "ellipse_is_hit_test_visible": False,
        "draw_callback_observed": False, "presentation_identity_proven": False, "failure": None,
        "actual_local_ellipse": deepcopy(local), "current_arrangement_matches_actual_geometry": True,
        "ellipse_to_window": {"source": TRANSFORM, **transform}, "ellipse_window_bounds": deepcopy(window),
        "actual_rasterization_scale": 1, "same_window_xaml_root": True,
    }
    return [
        {"id": "root", "type": "Grid", "parent": None, "bounds": box(0, 0, 500, 400)},
        {"id": "row", "type": "NativeListItemPanel", "parent": "root", "bounds": box(40, 95, 400, 25)},
        {"id": "marker", "type": "NativeListMarker", "parent": "row", "text": "", "accessible_name": "• ",
         "bounds": box(50, 100, 7, 18), "local_bounds": box(0, 0, 7, 18), "native_list_marker_evidence": receipt},
        {"id": "ellipse", "type": "Ellipse", "parent": "marker", "bounds": window, "transform": transform,
         "style": {"foreground": color, "stroke_width": 0, "opacity": 1, "brush_evidence": {"foreground": brush}}},
        {"id": "body", "type": "RichTextBlock", "parent": "row", "bounds": box(62, 95, 378, 25)},
    ]


def canonical(nodes):
    audit = windows_list_markers(nodes)["audits"]["marker"]
    return {"id": "marker", "kind": "icon", "text": "", "name": "• ", "bounds": deepcopy(nodes[2]["bounds"]),
            "icon": {"source": "geometry", "primitive": "ellipse", "glyph": None, "path": None},
            "style": {"foreground": deepcopy(audit["foreground"]), "opacity": audit["opacity"]},
            "evidence": {"type": "NativeListMarker", "native_list_marker": audit}}


class WindowsListMarkerTests(unittest.TestCase):
    def test_actual_properties_do_not_become_a_draw_or_presentation_receipt(self):
        nodes = fixture(); original = deepcopy(nodes)
        measured = windows_list_markers(nodes)
        audit = measured["owners"]["marker"]
        self.assertTrue(audit["identity_valid"])
        self.assertTrue(audit["geometry_valid"])
        self.assertTrue(audit["style_valid"])
        self.assertEqual(audit["measurements"]["window_ellipse_envelope"], nodes[3]["bounds"])
        self.assertEqual(audit["issues"], [PRESENTATION_GAP])
        self.assertFalse(audit["draw_callback_observed"])
        self.assertFalse(audit["presentation_identity_proven"])
        self.assertEqual(nodes, original)
        self.assertEqual(windows_list_marker_issues(canonical(nodes)), [PRESENTATION_GAP])
        from element_parity import icon_identity
        self.assertIsNotNone(icon_identity(canonical(nodes)["icon"])[1])

    def test_missing_foreign_unmounted_or_wrong_type_binding_is_not_owned(self):
        mutations = [
            lambda n: n[2].pop("native_list_marker_evidence"),
            lambda n: n[2]["native_list_marker_evidence"].update(owner_id="foreign"),
            lambda n: n[2]["native_list_marker_evidence"].update(window_content_id="missing"),
            lambda n: n[2]["native_list_marker_evidence"].update(same_window_xaml_root=False),
            lambda n: n[2]["native_list_marker_evidence"].update(ellipse_is_loaded=False),
            lambda n: n[3].update(parent="foreign"),
            lambda n: n[3].update(type="Rectangle"),
            lambda n: n[4].update(parent="foreign"),
            lambda n: n.append(deepcopy(n[3])),
            lambda n: n.append(deepcopy(n[2])),
        ]
        for mutate in mutations:
            nodes = fixture(); mutate(nodes)
            with self.subTest(mutation=mutations.index(mutate)):
                result = windows_list_markers(nodes)
                self.assertNotIn("marker", result["owners"])
                self.assertTrue(result["unmeasured"])

    def test_unexpected_visible_child_survives_and_fails_revalidation(self):
        nodes = fixture()
        child = {"id": "extra", "parent": "marker", "type": "TextBlock", "text": "unexpected paint"}
        nodes.append(child)
        element = canonical(nodes)
        audit = element["evidence"]["native_list_marker"]
        self.assertFalse(audit["identity_valid"])
        self.assertIn(child, audit["raw_nodes"])
        self.assertTrue(any("extra or ambiguous" in x for x in windows_list_marker_issues(element)))

    def test_stale_layout_and_changed_coordinate_measurements_remain_unknown(self):
        changes = [
            lambda r: r.update(current_arrangement=None),
            lambda r: r.update(current_arrangement_matches_actual_geometry=False),
            lambda r: r["current_arrangement"].update(owner_size=[8, 18]),
            lambda r: r["ellipse_to_window"].update(offset_x=52),
            lambda r: r["actual_local_ellipse"].update(width=6),
            lambda r: r.update(coordinate_failure={"hresult": -1}),
            lambda r: r.update(actual_rasterization_scale=2),
            lambda r: r["current_arrangement"].update(sequence=True),
            lambda r: r["ellipse_window_bounds"].update(x=float("inf")),
        ]
        for change in changes:
            nodes = fixture(); change(nodes[2]["native_list_marker_evidence"])
            with self.subTest(change=changes.index(change)):
                audit = windows_list_markers(nodes)["owners"]["marker"]
                self.assertFalse(audit["geometry_valid"])
                self.assertIsNone(audit["measurements"])
                self.assertIn(PRESENTATION_GAP, audit["issues"])

    def test_unknown_or_additional_brush_and_stroke_paint_is_not_filled(self):
        changes = [
            lambda n: n[2]["native_list_marker_evidence"].update(ellipse_fill_type="GradientBrush"),
            lambda n: n[2]["native_list_marker_evidence"].update(ellipse_fill_opacity=None),
            lambda n: n[2]["native_list_marker_evidence"].update(ellipse_has_stroke=True),
            lambda n: n[3]["style"].update(foreground=[255, 0, 0, 255]),
            lambda n: n[3]["style"]["brush_evidence"]["foreground"].update(opacity=0.5),
        ]
        for change in changes:
            nodes = fixture(); change(nodes)
            with self.subTest(change=changes.index(change)):
                audit = windows_list_markers(nodes)["owners"]["marker"]
                self.assertFalse(audit["style_valid"])
                self.assertIsNone(audit["foreground"])
                self.assertIsNone(audit["opacity"])

    def test_actual_color_alpha_and_opacity_are_preserved_without_raster_rounding(self):
        nodes = fixture(); receipt = nodes[2]["native_list_marker_evidence"]
        receipt.update(ellipse_fill_rgba8=[10, 20, 30, 127], ellipse_fill_opacity=0.5)
        nodes[3]["style"].update(foreground=[10, 20, 30, 63.5], opacity=0.7)
        nodes[3]["style"]["brush_evidence"]["foreground"].update(solid_color_rgba8=[10, 20, 30, 127], opacity=0.5)
        audit = windows_list_markers(nodes)["owners"]["marker"]
        self.assertTrue(audit["style_valid"])
        self.assertEqual(audit["foreground"], [10, 20, 30, 63.5])
        self.assertEqual(audit["opacity"], 0.7)

    def test_text_and_accessible_alternative_are_separate_actual_quantities(self):
        for field, value in (("text", "•"), ("accessible_name", "Bullet")):
            nodes = fixture(); nodes[2][field] = value
            self.assertNotIn("marker", windows_list_markers(nodes)["owners"])

    def test_false_draw_claims_cannot_pass_as_current_property_evidence(self):
        for key in ("draw_callback_observed", "presentation_identity_proven"):
            nodes = fixture(); nodes[2]["native_list_marker_evidence"][key] = True
            self.assertNotIn("marker", windows_list_markers(nodes)["owners"])
        element = canonical(fixture())
        element["evidence"]["native_list_marker"]["presentation_identity_proven"] = True
        self.assertTrue(any("promoted" in x for x in windows_list_marker_issues(element)))

    def test_fractional_actual_geometry_and_scale_are_not_replaced_by_font_prediction(self):
        nodes = fixture(); receipt = nodes[2]["native_list_marker_evidence"]
        receipt["actual_rasterization_scale"] = 2
        receipt["current_arrangement"]["coordinate_basis"]["rasterization_scale"] = 2
        receipt["actual_primary_font"]["native_ascent"] = 14.25
        # Independent metrics do not overwrite the actual retained Ellipse.
        audit = windows_list_markers(nodes)["owners"]["marker"]
        self.assertTrue(audit["geometry_valid"])
        self.assertEqual(audit["measurements"]["local_ellipse"], box(1, 7, 5, 5))

    def test_malformed_evidence_fails_closed_without_guessing(self):
        for key in ("ellipse_id", "window_content_id", "item_text_id", "actual_primary_font", "current_arrangement"):
            for value in (None, [], {"foreign": True}):
                nodes = fixture(); nodes[2]["native_list_marker_evidence"][key] = value
                result = windows_list_markers(nodes)
                self.assertTrue(result["unmeasured"])
                self.assertTrue(result["audits"]["marker"]["issues"])
        nodes = fixture(); nodes[2]["id"] = {}
        self.assertTrue(windows_list_markers(nodes)["unmeasured"])

    def test_canonical_values_must_match_observed_owner_and_shape_properties(self):
        changes = [lambda e: e.update(kind="state-dot"), lambda e: e.update(name="Bullet"),
                   lambda e: e.update(text="•"), lambda e: e["bounds"].update(width=5),
                   lambda e: e["style"].update(foreground=[0, 0, 0, 255]),
                   lambda e: e["style"].update(opacity=0.4)]
        for change in changes:
            element = canonical(fixture()); change(element)
            self.assertGreater(len(windows_list_marker_issues(element)), 1)

    def test_unrelated_native_icon_does_not_acquire_marker_obligations(self):
        self.assertEqual(windows_list_marker_issues({"evidence": {"type": "ReferenceVectorIcon"}}), [])

    def test_projection_owns_only_bound_ellipse_and_keeps_raw_and_unknowns(self):
        from test_windows_elements import ProjectionTests, measured, xaml_node
        nodes = []
        for raw in fixture():
            node = xaml_node(raw["id"], typ=raw["type"], **{k: deepcopy(v) for k, v in raw.items() if k not in {"id", "type", "style"}})
            node["style"].update(deepcopy(raw.get("style", {})))
            nodes.append(node)
        nodes = measured(nodes)
        # measured() provides synthetic general-tree fields; preserve the
        # independent current shape brush and geometry from the specific fixture.
        nodes[3]["style"].update(deepcopy(fixture()[3]["style"]))
        result = ProjectionTests().capture(nodes)
        emitted = {e["id"]: e for e in result["elements"]}
        self.assertEqual(emitted["marker"]["kind"], "icon")
        self.assertEqual(emitted["marker"]["text"], "")
        self.assertEqual(emitted["marker"]["name"], "• ")
        self.assertNotIn("ellipse", emitted)
        retained = next(r for r in result["projection"] if r.get("source") == "ellipse")
        self.assertEqual(retained["owner"], "marker")
        self.assertEqual(retained["paint_evidence"]["id"], "ellipse")
        self.assertIsNone(emitted["marker"]["icon"]["glyph"])
        self.assertTrue(any(i["reason"] == PRESENTATION_GAP for i in result["coverage"]["unmeasured"]))
        nodes[2]["native_list_marker_evidence"]["same_direct_child"] = False
        rejected = ProjectionTests().capture(nodes)
        self.assertIn("ellipse", {e["id"] for e in rejected["elements"]})


if __name__ == "__main__":
    unittest.main()
