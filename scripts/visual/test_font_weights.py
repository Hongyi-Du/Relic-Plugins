"""Independent recorded-shape font fixtures; no fonts, windows or processes run."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from font_weights import (MAC_DRAW_SOURCE, WINDOWS_FACE_SOURCE, WINDOWS_FORMAT_SOURCE,
                          compare_font_weights, font_weight_issues, project_font_weights)


def mac_element(configured=700, actual=600):
    font = {"family_name": "PingFang SC", "postscript_name": "PingFangSC-Semibold", "glyph_count": 1,
            "provider": MAC_DRAW_SOURCE, "actual_variations": {"2003265652": actual}}
    return {"id": "actual-mac-text", "kind": "text", "text": "2", "style": {"font_weight": 600, "rendered_fonts": [font]},
            "evidence": {"projection": {
                "text": "2",
                "native_font_weight_configuration": {"value": configured, "source": "actual native attributed text style input",
                                                     "quantity": "configured weight, not resolved font weight or synthetic paint"},
                "native_font_drawing": {"provider": MAC_DRAW_SOURCE, "status": "measured-current-draw", "fonts": [deepcopy(font)]}}}}


def reference_element():
    return {"id": "actual-dom-text", "kind": "text", "text": "2", "style": {"font_weight": 700,
            "rendered_fonts": [{"family_name": "蘋方-簡", "postscript_name": "PingFangSC-Semibold", "glyph_count": 1}]},
            "evidence": {"font_request": {"source": "getComputedStyle", "weight": 700, "weight_css": "700",
                                          "variation_settings": "normal"}}}


class FontWeightTests(unittest.TestCase):
    def test_actual_css700_and_same_semibold_face_do_not_prove_resolved700_or600(self):
        reference, native = reference_element(), mac_element()
        before = deepcopy((reference, native))
        configured = project_font_weights(reference)
        actual = project_font_weights(native)
        self.assertEqual(configured["configured"]["value"], 700)
        self.assertIsNone(configured["resolved"]["faces"])
        self.assertEqual(actual["configured"]["value"], 700)
        self.assertEqual(actual["resolved"]["faces"][0]["value"], 600)
        differences = compare_font_weights(reference, native)
        self.assertEqual([row["field"] for row in differences], ["font_weight.resolved"])
        self.assertIn("Missing comparable", differences[0]["reason"])
        self.assertEqual(font_weight_issues(native), [])
        self.assertEqual((reference, native), before, "Projection cannot overwrite original configured or descriptor values")

    def test_same_actual_resolved_weight_does_not_waive_different_requests(self):
        self.assertEqual([row["field"] for row in compare_font_weights(mac_element(700, 600), mac_element(600, 600))],
                         ["font_weight.configured"])

    def test_same_request_does_not_waive_different_actual_axis(self):
        result = compare_font_weights(mac_element(700, 600), mac_element(700, 601))
        self.assertEqual([row["field"] for row in result], ["font_weight.resolved"])
        self.assertEqual(result[0]["tolerance"], 0)

    def test_legacy_descriptor_conversion_is_preserved_not_compared_as_axis(self):
        a, b = mac_element(), mac_element()
        b["style"]["font_weight"] = 611
        self.assertEqual(compare_font_weights(a, b), [])
        self.assertEqual(project_font_weights(b)["legacy"]["value"], 611)
        self.assertIn("descriptor-trait", project_font_weights(b)["legacy"]["quantity"])

    def test_owned_label_projection_retains_configuration_and_actual_draw_binding(self):
        item = mac_element()
        item["evidence"]["identifier"] = "actual-component"
        item["evidence"]["owned_text_id"] = "actual-owned-text"
        item["evidence"]["owned_text_evidence"] = {"id": "actual-owned-text", "production_owner": "actual-component", "text": "2",
                                                  "projection": item["evidence"].pop("projection")}
        self.assertEqual(font_weight_issues(item), [])
        self.assertEqual(project_font_weights(item)["resolved"]["faces"][0]["value"], 600)

    def recorded_owned_element(self):
        source = Path(__file__).with_name("fixtures") / "font_weights_recorded_a3ca2a3.json"
        return json.loads(source.read_text(encoding="utf-8"))["native"]

    def test_recorded_a3ca2a3_actual_owned_badge_keeps600_and_missing_configuration(self):
        item = self.recorded_owned_element()
        measured = project_font_weights(item)
        self.assertEqual(item["id"], "window/0/7")
        self.assertEqual(measured["source_evidence_path"], "evidence.owned_text_evidence.projection")
        self.assertEqual(measured["resolved"]["faces"][0]["value"], 600)
        self.assertIsNone(measured["configured"]["value"], "This actual older capture did not measure the new configuration field")
        self.assertEqual([issue["field"] for issue in font_weight_issues(item)], ["font_weight.configured"])

    def test_unrelated_root_projection_cannot_hide_recorded_owned_font_evidence(self):
        item = self.recorded_owned_element()
        item["evidence"]["projection"] = {"text": "", "kind": "card", "unrelated_shape_probe": True}
        self.assertEqual(project_font_weights(item)["resolved"]["faces"][0]["value"], 600)

    def test_parent_request_is_never_combined_with_the_recorded_child_font(self):
        item = self.recorded_owned_element()
        item["evidence"]["projection"] = {"text": item["text"], "native_font_weight_configuration": {
            "value": 700, "source": "actual native attributed text style input"}}
        measured = project_font_weights(item)
        self.assertEqual(len(measured["native_font_projection_paths"]), 2)
        self.assertIsNone(measured["configured"]["value"])
        self.assertIsNone(measured["resolved"]["faces"])
        self.assertEqual(len(font_weight_issues(item)), 2)

    def test_broken_recorded_production_owner_binding_remains_unknown(self):
        item = self.recorded_owned_element()
        item["evidence"]["owned_text_evidence"]["production_owner"] = "different-production-control"
        self.assertIsNone(project_font_weights(item)["resolved"]["faces"])
        self.assertTrue(font_weight_issues(item))

    def test_stale_partial_or_different_draw_cannot_establish_actual_face_weights(self):
        for change in ("unmeasured", "wrong-fonts", "wrong-provider"):
            with self.subTest(change=change):
                item = mac_element()
                drawing = item["evidence"]["projection"]["native_font_drawing"]
                if change == "unmeasured": drawing["status"] = "unmeasured"
                if change == "wrong-fonts": drawing["fonts"][0]["actual_variations"]["2003265652"] = 599
                if change == "wrong-provider": drawing["provider"] = "newly reshaped font"
                self.assertIsNone(project_font_weights(item)["resolved"]["faces"])
                self.assertTrue(font_weight_issues(item))

    def test_name_and_descriptor_variations_do_not_replace_actual_variations(self):
        item = mac_element()
        for font in (item["style"]["rendered_fonts"][0], item["evidence"]["projection"]["native_font_drawing"]["fonts"][0]):
            font["variations"] = font.pop("actual_variations")
        measured = project_font_weights(item)
        self.assertIsNone(measured["resolved"]["faces"][0]["value"])
        self.assertTrue(font_weight_issues(item))

    def test_every_actual_fallback_face_needs_its_own_weight(self):
        item = mac_element()
        fallback = {"family_name": "Fallback", "postscript_name": "Fallback-Regular", "glyph_count": 1,
                    "provider": MAC_DRAW_SOURCE, "actual_variations": None}
        item["style"]["rendered_fonts"].append(fallback)
        item["evidence"]["projection"]["native_font_drawing"]["fonts"].append(deepcopy(fallback))
        self.assertEqual(len(project_font_weights(item)["resolved"]["faces"]), 2)
        self.assertTrue(font_weight_issues(item))

    def test_unknown_on_both_sides_is_still_a_style_failure(self):
        result = compare_font_weights(reference_element(), reference_element())
        self.assertEqual([row["field"] for row in result], ["font_weight.resolved"])

    def test_nontext_counterpart_does_not_crash_or_acquire_invented_font_values(self):
        item = {"id": "empty-button", "kind": "button", "text": "", "style": {}, "evidence": {}}
        result = compare_font_weights(mac_element(), item)
        self.assertEqual({row["field"] for row in result}, {"font_weight.configured", "font_weight.resolved"})
        self.assertFalse(project_font_weights(item)["applicable"])

    def test_windows_actual_textformat_and_actual_face_axis_are_independent(self):
        font = {"family_name": "Actual Face", "postscript_name": "ActualPS", "source": WINDOWS_FACE_SOURCE,
                "axes": [{"tag": "wght", "value": 600}], "glyph_count": 1}
        fmt = {"source": WINDOWS_FORMAT_SOURCE, "font_weight": 700}
        item = {"id": "actual-label", "kind": "text", "text": "x", "style": {"font_weight": 700, "rendered_fonts": [font]},
                "evidence": {"native_label_submission": {"style": {"font_weight": 700}},
                             "native_label_evidence": {"draw": {"actual_text_format": fmt}},
                             "native_label_fonts": {"status": "measured-current-submission", "source_span_complete": True,
                                                    "fonts": [deepcopy(font)]}}}
        measured = project_font_weights(item)
        self.assertEqual(measured["configured"]["value"], 700)
        self.assertEqual(measured["resolved"]["faces"][0]["value"], 600)
        self.assertEqual(font_weight_issues(item), [])
        item["evidence"]["native_label_submission"]["style"] = None
        self.assertIsNone(project_font_weights(item)["configured"]["value"])
        self.assertTrue(font_weight_issues(item))

    def test_raw_uia_or_legacy_weight_cannot_be_reclassified_without_source_evidence(self):
        item = {"id": "actual-text", "kind": "text", "text": "x", "style": {"font_weight": 700},
                "evidence": {"provider_fonts": [{"font_weight": 700}]}}
        measured = project_font_weights(item)
        self.assertIsNone(measured["configured"]["value"])
        self.assertIsNone(measured["resolved"]["faces"])
        self.assertEqual({row["field"] for row in font_weight_issues(item)}, {"font_weight.configured", "font_weight.resolved"})

    def test_bad_numeric_axis_and_unbound_contract_fail(self):
        for actual in (None, True, 0, 1001, "600", float("nan")):
            with self.subTest(actual=actual):
                self.assertTrue(font_weight_issues(mac_element(actual=actual)))
        item = mac_element()
        item["evidence"]["font_weight_quantities"] = project_font_weights(item)
        item["evidence"]["font_weight_quantities"]["owner"] = "other-node"
        self.assertTrue(font_weight_issues(item))


if __name__ == "__main__":
    unittest.main()
