"""Pure recorded-evidence integration regressions; run only in CI."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from element_parity import CATEGORIES, compare_elements, run, validate_capture
from paint_patterns import MeasurementError, captured_pattern
from test_element_parity import capture, element
from test_paint_patterns import change_pixel, encoded, fixtures
from windows_elements import project_background_pattern


def measured_pair():
    """Independent synthetic opaque paints; no app/reference output is invented."""
    reference, native = fixtures()
    result = []
    for eid, record in (("ref", reference), ("native", native)):
        item = element(eid, text="", kind="card")
        item["bounds"] = {"x": 0, "y": 0, "width": 32, "height": 32}
        item["evidence"]["background_pattern_measurement"] = {
            "source_id": eid, "placement": deepcopy(record["placement"]),
            "raster": deepcopy(record["raster"]), "opacity_source": record["opacity_source"]}
        if eid == "ref":
            item["style"]["background_image"] = deepcopy(record["paint"])
        else:
            item["style"]["background_image"] = {"kind": "image-brush", "source_id": eid}
            item["evidence"]["brush_evidence"] = {"background": deepcopy(record["brush"])}
        result.append(item)
    return result


class PatternIntegrationTests(unittest.TestCase):
    def test_complete_independent_measurements_replace_only_descriptor_equality(self):
        ref, native = measured_pair()
        before = deepcopy(native)
        result = compare_elements([ref], [native])
        self.assertTrue(all(not result[key] for key in CATEGORIES))
        self.assertEqual(result["matched_elements"], 1)
        self.assertEqual(native, before)
        self.assertEqual(native["style"]["background_image"]["kind"], "image-brush")
        data = capture("windows", [native])
        self.assertEqual(validate_capture(data, "windows", data["scene_id"], data["viewport"]), [])

    def test_other_style_and_state_failures_survive_a_matching_pattern(self):
        ref, native = measured_pair()
        # Make actual text/typography independently applicable to both records.
        ref["text"] = native["text"] = "Independent label"
        native["style"].update(font_size=19, border_width=2, background=[255, 255, 255, 255])
        native["state"]["selected"] = True
        result = compare_elements([ref], [native])
        fields = {row["field"] for row in result["style_out_of_tolerance"]}
        self.assertTrue({"font_size", "border_width", "background"} <= fields)
        self.assertNotIn("background_image", fields)
        self.assertTrue(result["state_mismatch"])
        self.assertEqual(result["matched_elements"], 0)

    def test_current_imagebrush_evidence_keeps_null_and_original_failure(self):
        ref, native = measured_pair()
        native["style"]["background_image"] = None
        native["evidence"].pop("background_pattern_measurement")
        old_brush = deepcopy(native["evidence"]["brush_evidence"])
        project_background_pattern(native, {"id": native["id"]})
        self.assertIsNone(native["style"]["background_image"])
        self.assertEqual(native["evidence"]["brush_evidence"], old_brush)
        with patch("element_parity.compare_paint_patterns") as compare:
            result = compare_elements([ref], [native])
            compare.assert_not_called()
        self.assertEqual(len(result["extraction_errors"]), 1)
        self.assertEqual(result["style_out_of_tolerance"][0]["reason"], "Required paint measurement is unknown")
        data = capture("windows", [native])
        errors = validate_capture(data, "windows", data["scene_id"], data["viewport"])
        self.assertTrue(any(row["reason"] == "Missing measured paint: background_image" for row in errors))

    def test_missing_mask_is_not_completed_from_bounds_or_pixel_samples(self):
        ref, native = measured_pair()
        native["evidence"]["background_pattern_measurement"]["raster"].pop("visibility")
        native["evidence"]["pixel_samples"] = [{"x": 16, "y": 16, "rgba": [0, 0, 0, 0]}]
        native["evidence"]["visible_fragments"] = [deepcopy(native["bounds"])]
        with patch("element_parity.compare_paint_patterns") as compare:
            result = compare_elements([ref], [native])
            compare.assert_not_called()
        self.assertEqual(len(result["extraction_errors"]), 1)
        self.assertIn("A8", result["extraction_errors"][0]["measurements"][0]["reason"])

    def test_tiny_complete_crop_cannot_prove_full_element_coverage(self):
        _, native = measured_pair()
        raster = native["evidence"]["background_pattern_measurement"]["raster"]
        raster.update(width=1, height=1)
        raster["visibility"]["data"] = encoded([255])
        with self.assertRaisesRegex(MeasurementError, "entire measured visible"):
            captured_pattern(native)

    def test_current_six_percent_css_requires_real_quantization_evidence(self):
        ref, native = measured_pair()
        for stop in ref["style"]["background_image"]["stops"][:2]: stop["color"] = [27, 27, 30, 15.3]
        with patch("element_parity.compare_paint_patterns") as compare:
            result = compare_elements([ref], [native])
            compare.assert_not_called()
        self.assertEqual(len(result["extraction_errors"]), 1)
        self.assertIn("quantization", result["extraction_errors"][0]["measurements"][0]["reason"])

    def test_actual_bitmap_bytes_cannot_be_replaced_by_a_supplied_gradient(self):
        ref, native = measured_pair()
        actual = {"brush": native["evidence"]["brush_evidence"]["background"]}
        change_pixel(actual, 31, 31, (0, 0, 255, 255))
        native["evidence"]["background_pattern_measurement"]["paint"] = deepcopy(ref["style"]["background_image"])
        result = compare_elements([ref], [native])
        rows = [r for r in result["style_out_of_tolerance"] if r["field"] == "background_image"]
        self.assertEqual(rows[0]["measurement"]["mismatched_pixels"], 1)
        self.assertEqual(rows[0]["measurement"]["compared_pixels"], 1024)
        native["style"]["background_image"] = deepcopy(ref["style"]["background_image"])
        with patch("element_parity.compare_paint_patterns") as compare:
            result = compare_elements([ref], [native])
            compare.assert_not_called()
        self.assertTrue(result["extraction_errors"])

    def test_measurements_are_bound_to_the_actual_source_id(self):
        ref, native = measured_pair()
        native["evidence"]["background_pattern_measurement"]["source_id"] = ref["id"]
        result = compare_elements([ref], [native])
        self.assertTrue(result["extraction_errors"])
        self.assertIn("actual element source", result["extraction_errors"][0]["measurements"][0]["reason"])

    def test_windows_projection_promotes_only_complete_captured_imagebrush(self):
        _, native = measured_pair()
        node = {"id": native["id"], "background_pattern_measurement": native["evidence"].pop("background_pattern_measurement")}
        native["style"]["background_image"] = None
        before = deepcopy(native["style"])
        project_background_pattern(native, node)
        self.assertEqual(native["style"]["background_image"], {"kind": "image-brush", "source_id": "native"})
        for key in before:
            if key != "background_image": self.assertEqual(native["style"][key], before[key])
        self.assertEqual(native["evidence"]["background_pattern_measurement"], node["background_pattern_measurement"])
        native["style"]["background_image"] = None
        node["background_pattern_measurement"]["raster"].pop("visibility")
        project_background_pattern(native, node)
        self.assertIsNone(native["style"]["background_image"])

    def test_pair_measurement_failure_survives_full_report_aggregation(self):
        spec = {"languages": ["en-US"], "themes": ["light"], "sizes": [[32, 32]], "scenes": ["group"]}
        scene = "en-US-light-32x32-group"
        viewport = {"width": 32, "height": 32, "scale": 1}
        ref, native = measured_pair()
        # Each capture has well-formed independent measurements, but every
        # visible native pixel is marked covered. It cannot prove a matching
        # visible background: the real comparison emits an extraction failure.
        for item in (ref, native):
            item["evidence"]["background_pattern_measurement"]["raster"]["visibility"]["data"] = encoded([0] * 1024)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for client in ("reference", "reference-macos", "windows", "macos"):
                path = root / "source" / client
                path.mkdir(parents=True)
                item = deepcopy(native if client == "windows" else ref)
                data = capture(client, [item], scene, viewport)
                self.assertEqual(validate_capture(data, data["client"], scene, viewport), [])
                (path / f"{scene}.elements.json").write_text(json.dumps(data), encoding="utf-8")
                Image.new("RGBA", (32, 32), (255, 255, 255, 255)).save(path / f"{scene}.png")
            result = run(root / "source", root / "report", spec=spec)
        windows = result["scenes"][0]["platforms"]["windows"]
        self.assertFalse(result["passed"])
        self.assertEqual(len(windows["extraction_errors"]), 1)
        self.assertFalse(windows["passed"])
        self.assertEqual(result["summary"]["windows"]["scenes_checked"], 0)
        self.assertEqual(result["summary"]["windows"]["counts"]["extraction_errors"], 1)


if __name__ == "__main__":
    unittest.main()
