"""Recorded NativeLabel quantity regressions; pure file/measurement tests in CI.

The fixture is one actual 78c7f6b label and its bound surface/frame. A white PNG
used by projection tests is only a synthetic pixel-sampling input, never an
assertion about the captured application's visible glyphs or final pixels.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from native_label_fonts import native_label_fonts
from native_label_geometry import native_label_geometry
from windows_elements import native_label_submission, native_label_text_quantity, project
from test_windows_elements import xaml_node


def recorded():
    value = json.loads((Path(__file__).parent / "fixtures/native_label_quantity_recorded_78c7f6b.json").read_text(encoding="utf-8"))
    return value["node"], value["surface"], value["frame"]


def measured(node, surface, frame):
    geometry, geometry_issues = native_label_geometry(node, surface)
    fonts, font_issues = native_label_fonts(node, surface, frame)
    submission, submission_issues = native_label_submission(node, frame)
    return (native_label_text_quantity(node, geometry, fonts, submission),
            geometry_issues + font_issues + submission_issues, geometry, fonts, submission)


def synchronize_changed_draw(node, frame):
    """Counterfactual fixtures only: keep the duplicate draw truthful after a mutation."""
    frame["production_draws"][0]["production_receipt"] = deepcopy(node["native_label_evidence"])


class WindowsLabelQuantityTests(unittest.TestCase):
    def test_recorded_font_metric_advance_is_not_the_170px_allocation(self):
        node, surface, frame = recorded()
        before = deepcopy((node, surface, frame))
        result, issues, geometry, fonts, submission = measured(node, surface, frame)
        self.assertIsNotNone(result)
        self.assertEqual(node["id"], "xaml-356")
        self.assertEqual(node["text"], "验收与回归检查")
        self.assertEqual(result["quantity"], "font-metric-text-advance-range")
        self.assertEqual(result["bounds"], {"x": 80.0, "y": 458.03253173828125,
                                          "width": 84.0, "height": 15.240234375})
        self.assertEqual(result["element_allocation"]["bounds"]["width"], 170)
        self.assertEqual(result["text_bounds"], [geometry["font_metric_advance"][0]["window"]["bounds"]])
        self.assertEqual(result["source_ranges_utf16"], [[0, 7]])
        self.assertTrue(fonts["source_span_complete"])
        self.assertFalse(result["final_png_attribution_proven"])
        self.assertIsNone(result["visible_glyph_coverage"])
        self.assertFalse(submission["presentation_identity_proven"])
        self.assertIsNone(geometry["final_pixel_contribution"])
        self.assertTrue(any(issue["property"] == "evidence.native_label_visible_glyphs" for issue in issues))
        self.assertEqual((node, surface, frame), before)

    def test_stale_source_frame_or_surface_cannot_supply_the_quantity(self):
        mutations = {
            "different-source": lambda n, s, f: n.update(text="别的源文本"),
            "different-image-owner": lambda n, s, f: s["native_label_surface_evidence"].update(owner_id="another-label"),
            "different-image-reference": lambda n, s, f: s["native_label_surface_evidence"].update(same_image_object=False),
            "different-surface-com": lambda n, s, f: s["native_label_surface_evidence"].update(surface_binding_same_com_identity=False),
            "stale-image-revision": lambda n, s, f: s["native_label_surface_evidence"].update(draw_ordinal=0),
            "stale-label-revision": lambda n, s, f: n["native_label_evidence"].update(current_draw_ordinal=0),
            "changed-frame-state": lambda n, s, f: f["checkpoints"][0].update(same_observed_state=False),
            "missing-frame-stage": lambda n, s, f: f["checkpoints"].pop(),
            "wrong-case": lambda n, s, f: f.update(case_id="another-case"),
            "failed-frame": lambda n, s, f: f.update(failure="actual-capture-failure"),
        }
        for label, change in mutations.items():
            with self.subTest(label=label):
                node, surface, frame = recorded()
                change(node, surface, frame)
                result, issues, *_ = measured(node, surface, frame)
                self.assertIsNone(result)
                self.assertTrue(issues)

    def test_trimmed_missing_or_uncertain_line_state_keeps_original_unknown(self):
        for state in (True, None, "absent"):
            with self.subTest(state=state):
                node, surface, frame = recorded()
                line = node["native_label_evidence"]["draw"]["line_metrics"][0]
                if state == "absent":
                    line.pop("is_trimmed")
                else:
                    line["is_trimmed"] = state
                synchronize_changed_draw(node, frame)
                result, issues, *_ = measured(node, surface, frame)
                self.assertIsNone(result)
                self.assertTrue(any("trimmed" in issue["reason"] for issue in issues))

    def test_partial_overlapping_and_changed_source_callbacks_are_rejected(self):
        mutations = {
            "partial": lambda draw: draw["glyph_runs"][0]["description"].update(text="验收与回归检", text_length_utf16=6, cluster_map=list(range(6))),
            "outside-source": lambda draw: draw["glyph_runs"][0]["description"].update(text_position_utf16=1),
            "changed-text": lambda draw: draw["glyph_runs"][0]["description"].update(text="不同的真实源文"),
            "overlap": lambda draw: draw["glyph_runs"].append(dict(deepcopy(draw["glyph_runs"][0]), ordinal=1)),
            "absent": lambda draw: draw.update(glyph_runs=[]),
            "inline-object": lambda draw: draw["glyph_runs"][0].update(from_inline_object=True, inline_draw_ordinal=0),
        }
        for label, change in mutations.items():
            with self.subTest(label=label):
                node, surface, frame = recorded()
                change(node["native_label_evidence"]["draw"])
                synchronize_changed_draw(node, frame)
                self.assertIsNone(measured(node, surface, frame)[0])

    def test_missing_metric_cannot_fall_back_to_layout_selection_or_ink(self):
        node, surface, frame = recorded()
        _, _, geometry, fonts, submission = measured(node, surface, frame)
        self.assertTrue(geometry["advance_selection"])
        self.assertTrue(geometry["glyph_ink"])
        for change in (lambda g: g.update(font_metric_advance=[]),
                       lambda g: g["font_metric_advance"][0].update(window=None),
                       lambda g: g["font_metric_advance"][0].update(description={}),
                       lambda g: g["font_metric_advance"][0].update(quantity="glyph-ink")):
            candidate = deepcopy(geometry)
            change(candidate)
            self.assertIsNone(native_label_text_quantity(node, candidate, fonts, submission))

    def test_unknown_clip_remains_unknown_independent_of_source_geometry(self):
        node, surface, frame = recorded()
        surface["axis_aligned_transform"] = False
        result, issues, *_ = measured(node, surface, frame)
        self.assertIsNotNone(result)
        self.assertEqual(result["bounds"]["width"], 84)
        self.assertIsNone(result["visible_bounds"])
        self.assertTrue(any(issue["property"] == "evidence.native_label_visible_glyphs" for issue in issues))

    def test_native_path_retained_line_is_not_reprojected(self):
        node, surface, frame = recorded()
        node["native_path_line_evidence"] = {"owner_id": "actual-path-owner"}
        self.assertIsNone(measured(node, surface, frame)[0])

    def capture(self, node, surface, frame, *, composite=False):
        viewport = {"width": 1440, "height": 900, "scale": 1}
        raw = [node, surface]
        if composite:
            button = xaml_node("synthetic-button", "Button", bounds=deepcopy(node["bounds"]))
            node["parent"] = button["id"]
            raw.insert(0, button)
        data = {"schema_version": 1, "scene_id": frame["case_id"], "client": "windows", "viewport": viewport,
                "raw_nodes": raw, "extraction_errors": ["independent-error-sentinel"],
                "capture_evidence": {"native_label_frame": frame}}
        uia = {"schema_version": 1, "case_id": frame["case_id"], "viewport": viewport,
               "raw_nodes": [], "extraction_errors": []}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "case.xaml.json").write_text(json.dumps(data), encoding="utf-8")
            (root / "case.uia.json").write_text(json.dumps(uia), encoding="utf-8")
            Image.new("RGBA", (1440, 900), "white").save(root / "case.png")
            return project(root / "case.xaml.json", root / "case.uia.json", root / "case.png")

    def test_standalone_projection_keeps_independent_failures_and_raw_allocation(self):
        node, surface, frame = recorded()
        result = self.capture(node, surface, frame)
        item = next(element for element in result["elements"] if element["id"] == node["id"])
        self.assertEqual(item["bounds"]["width"], 84)
        self.assertEqual(item["evidence"]["native_label_text_quantity"]["element_allocation"]["bounds"]["width"], 170)
        self.assertEqual(item["evidence"]["text_bounds_quantity"], "font-metric-text-advance-range")
        self.assertEqual(len(item["evidence"]["text_bounds"]), 1)
        failures = [issue for issue in result["coverage"]["unmeasured"] if issue["id"] == node["id"]]
        self.assertFalse(any(issue["property"] == "evidence.text_bounds" for issue in failures))
        self.assertTrue(any(issue["property"] == "evidence.native_label_visible_glyphs" for issue in failures))
        self.assertIn("independent-error-sentinel", result["extraction_errors"])

    def test_composite_owner_keeps_its_original_control_geometry(self):
        node, surface, frame = recorded()
        result = self.capture(node, surface, frame, composite=True)
        item = next(element for element in result["elements"] if element["id"] == "synthetic-button")
        self.assertEqual(item["bounds"]["width"], 170)
        self.assertIsNone(item["evidence"]["native_label_text_quantity"])
        self.assertTrue(any(issue["property"] == "evidence.native_label_visible_glyphs"
                            for issue in result["coverage"]["unmeasured"]))


if __name__ == "__main__":
    unittest.main()
