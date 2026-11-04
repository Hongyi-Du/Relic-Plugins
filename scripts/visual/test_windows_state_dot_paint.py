"""Pure analytic-paint receipt tests; no native window or capture is launched."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from windows_elements import state_dot_analytic_paint
from windows_outline import DOT_CONTRACT, DOT_SOURCE


def recorded_nodes():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "state_dot_rings_recorded_8767825.json").read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in [*fixture["ancestor_edges"], *fixture["raw_nodes"]]}
    return nodes[fixture["owner_id"]], nodes


def synthetic_current_contract():
    """Recorded geometry plus a synthetic new owner contract, not a CI receipt.

    The real old record remains unchanged on disk and must continue to fail.
    This controlled extension tests the exact new producer schema independently
    of whether the next actual Windows capture has established that schema.
    """
    owner, nodes = recorded_nodes()
    owner["outline_owner_evidence"].update(
        own_paint_contract=DOT_CONTRACT,
        state_dot_grid={"source": DOT_SOURCE, "status": "measured", "owner_id": owner["id"],
                        "base_type": "Microsoft.UI.Xaml.Controls.Grid", "is_sealed": True,
                        "audited_source": "native/windows/Relic/NativeStateDotView.cs#NativeStateDotView",
                        "visual_child_count": 2, "panel_child_count": 2,
                        "surround_id": "xaml-350", "vacancy_ring_id": "xaml-351",
                        "production_layers_are_current_children": True})
    return owner, nodes


class StateDotAnalyticPaintTests(unittest.TestCase):
    def assert_raster_unknown(self, proof, issues):
        for key in ("raster_equivalence", "antialiasing_equivalence", "same_frame_contribution"):
            self.assertIsNone(proof[key])
        self.assertTrue(any(issue["property"] == "paint.compound_raster" for issue in issues))

    def test_recorded_old_null_owner_contract_remains_incomplete(self):
        owner, nodes = recorded_nodes()
        before = deepcopy(nodes)
        self.assertIsNone(owner["outline_owner_evidence"]["own_paint_contract"])
        parameters, proof, issues = state_dot_analytic_paint(owner, nodes)
        self.assertIsNone(parameters)
        self.assertEqual(proof["status"], "unmeasured")
        self.assertTrue(any(issue["property"] == "style.compound_paint" for issue in issues))
        self.assert_raster_unknown(proof, issues)
        self.assertEqual(nodes, before)

    def test_complete_synthetic_contract_derives_annuli_but_not_raster_success(self):
        owner, nodes = synthetic_current_contract()
        before = deepcopy(nodes)
        parameters, proof, issues = state_dot_analytic_paint(owner, nodes)
        self.assertEqual(parameters["border_widths"], [2, 2, 2, 2])
        self.assertEqual(parameters["corner_radii"], [5, 5, 5, 5])
        self.assertEqual(parameters["border_color"], nodes["xaml-350"]["style"]["foreground"])
        self.assertEqual(parameters["background"], [0, 0, 0, 0])
        self.assertEqual(parameters["shadow"], [{"inset": True, "offset_x": 0, "offset_y": 0,
                         "blur_radius": 0, "spread_radius": 1.5,
                         "color": nodes["xaml-351"]["style"]["foreground"]}])
        rings = [layer["ellipse"]["geometry_derivation"] for layer in proof["layers"]]
        self.assertEqual([(ring["inner_radius"], ring["outer_radius"]) for ring in rings], [(3, 5), (1.5, 3)])
        self.assertEqual(proof["status"], "measured-analytic-parameters")
        self.assertFalse(any(issue["property"] == "style.compound_paint" for issue in issues))
        self.assert_raster_unknown(proof, issues)
        self.assertEqual(nodes, before)

    def test_colors_come_from_actual_strokes_not_the_recorded_palette(self):
        owner, nodes = synthetic_current_contract()
        for eid, color in (("xaml-350", [11, 22, 33, 255]), ("xaml-351", [44, 55, 66, 255])):
            style = nodes[eid]["style"]
            style["foreground"] = color
            style["brush_evidence"]["foreground"].update(solid_rgba=color, solid_color_rgba8=color)
        parameters, proof, issues = state_dot_analytic_paint(owner, nodes)
        self.assertEqual(parameters["border_color"], [11, 22, 33, 255])
        self.assertEqual(parameters["shadow"][0]["color"], [44, 55, 66, 255])
        self.assert_raster_unknown(proof, issues)

    def test_missing_or_changed_owner_and_layer_proofs_never_supply_parameters(self):
        cases = ("old-owner", "missing-owner-contract", "unsealed", "wrong-layer-id", "extra-child",
                 "layer-reparented", "child-composition", "owner-composition", "missing-geometry",
                 "unknown-stretch", "unknown-fill", "opaque-fill", "opacity", "dashed-stroke",
                 "nonfinite-width", "nonopaque-stroke", "clipped-layer", "boolean-opacity", "boolean-border")
        for case in cases:
            with self.subTest(case=case):
                owner, nodes = synthetic_current_contract()
                ring = nodes["xaml-351"]
                if case == "old-owner":
                    owner["outline_owner_evidence"]["own_paint_contract"] = None
                elif case == "missing-owner-contract":
                    owner["outline_owner_evidence"].pop("state_dot_grid")
                elif case == "unsealed":
                    owner["outline_owner_evidence"]["state_dot_grid"]["is_sealed"] = False
                elif case == "wrong-layer-id":
                    owner["outline_owner_evidence"]["state_dot_grid"]["vacancy_ring_id"] = "other"
                elif case == "extra-child":
                    nodes["extra"] = {"id": "extra", "parent": owner["id"], "type": "Ellipse", "render_sibling_order": 2}
                elif case == "layer-reparented":
                    ring["parent"] = "another-owner"
                elif case == "child-composition":
                    ring["outline_owner_evidence"]["composition"]["child_visual_present"] = True
                elif case == "owner-composition":
                    owner["outline_owner_evidence"]["composition"]["child_visual_present"] = True
                elif case == "missing-geometry":
                    ring.pop("shape_geometry_evidence")
                elif case == "unknown-stretch":
                    ring["shape_geometry_evidence"]["stretch"] = "Unknown"
                elif case == "unknown-fill":
                    ring["style"]["brush_evidence"].pop("background")
                elif case == "opaque-fill":
                    ring["style"]["background"] = [100, 100, 100, 255]
                    ring["style"]["brush_evidence"]["background"] = {
                        "type": "Microsoft.UI.Xaml.Media.SolidColorBrush", "opacity": 1,
                        "solid_rgba": [100, 100, 100, 255]}
                elif case == "opacity":
                    owner["opacity"] = owner["style"]["opacity"] = .5
                elif case == "dashed-stroke":
                    ring["stroke_evidence"]["raw_pattern"]["dash_array"] = [1]
                    ring["style"]["stroke_dash"] = [1.5]
                elif case == "nonfinite-width":
                    ring["style"]["stroke_width"] = float("nan")
                elif case == "nonopaque-stroke":
                    color = [184, 181, 175, 128]
                    ring["style"]["foreground"] = color
                    ring["style"]["brush_evidence"]["foreground"]["solid_rgba"] = color
                elif case == "clipped-layer":
                    ring["visible_bounds"]["width"] -= 1
                elif case == "boolean-opacity":
                    owner["opacity"] = owner["style"]["opacity"] = True
                elif case == "boolean-border":
                    owner["style"]["border_width"] = False
                    owner["style"]["border_widths"] = [False] * 4
                parameters, proof, issues = state_dot_analytic_paint(owner, nodes)
                self.assertIsNone(parameters)
                self.assertTrue(any(issue["property"] == "style.compound_paint" for issue in issues))
                self.assert_raster_unknown(proof, issues)

    def test_measured_offset_ring_is_not_recentered(self):
        owner, nodes = synthetic_current_contract()
        ring = nodes["xaml-351"]
        for key in ("bounds", "visible_bounds"):
            ring[key]["x"] += .25
        ring["transform"]["offset_x"] += .25
        for key in ("origin", "axis_endpoint_x", "axis_endpoint_y"):
            ring["stroke_evidence"][key]["x"] += .25
        for point in ring.get("transformed_corners", []):
            point["x"] += .25
        parameters, proof, issues = state_dot_analytic_paint(owner, nodes)
        self.assertIsNone(parameters)
        self.assertTrue(any("not concentric" in reason for reason in proof["reasons"]))
        self.assertEqual(proof["layers"][1]["ellipse"]["geometry_derivation"]["center"]["x"], 66.25)
        self.assert_raster_unknown(proof, issues)


if __name__ == "__main__":
    unittest.main()
