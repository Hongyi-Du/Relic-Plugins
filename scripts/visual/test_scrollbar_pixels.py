"""Pure recorded-shape pixel fixtures; no browser, app or screenshot is created."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scrollbar_pixels import append_scrollbar_pixels, measure_gutter_pixels


class ScrollbarPixelTests(unittest.TestCase):
    def fixture(self):
        background = (255, 255, 255, 255)
        rows = [[background] * 10 for _ in range(20)]
        # Explicit fixture pixel cells, not a thumb reconstructed from scroll.
        for y in range(5, 15):
            for x in range(3, 7):
                rows[y][x] = (216, 215, 213, 255)
        parts = []
        for pseudo in ("::-webkit-scrollbar", "::-webkit-scrollbar-button", "::-webkit-scrollbar-track", "::-webkit-scrollbar-track-piece",
                       "::-webkit-scrollbar-thumb", "::-webkit-scrollbar-corner", "::-webkit-resizer"):
            parts.append({"pseudo": pseudo, "computed_background_rgba": [143, 140, 134, 89.25] if pseudo.endswith("-thumb") else [0, 0, 0, 0],
                "background_image": "none", "box_shadow": "none", "content": "normal", "transform": "none", "filter": "none",
                "mix_blend_mode": "normal", "opacity": "1", "border_widths": ["3px"] * 4 if pseudo.endswith("-thumb") else ["0px"] * 4,
                "border_styles": ["solid"] * 4, "computed_border_rgba": [[0, 0, 0, 0]] * 4})
        evidence = {"axes": ["vertical"], "scroll_top": 209, "scroll_height": 907, "client_height": 698,
            "gutters": {"vertical": {"bounds": {"x": 1090, "y": 96, "width": 10, "height": 20}, "fully_visible": True}},
            "ancestry": [{"opacity": "1", "filter": "none", "backdrop_filter": "none", "mix_blend_mode": "normal", "clip_path": "none", "mask_image": "none", "background_image": "none"}],
            "parts": parts}
        return rows, evidence

    def test_only_actual_png_ink_is_measured_and_transparent_part_bounds_stay_unknown(self):
        rows, evidence = self.fixture()
        result = measure_gutter_pixels(rows, evidence, "vertical")
        self.assertEqual(result["status"], "measured-ink")
        self.assertEqual(result["ink_bounds"], {"x": 1093, "y": 101, "width": 4, "height": 10})
        self.assertIsNone(result["outer_bounds"]); self.assertIsNone(result["hit_bounds"])
        self.assertEqual(result["non_background_pixel_count"], 40)
        self.assertEqual(result["observed_background_rgba"], [255, 255, 255, 255])
        self.assertEqual(sum(run["width"] for run in result["pixel_runs"]), 200)
        rebuilt = [[None] * 10 for _ in range(20)]
        for run in result["pixel_runs"]:
            for x in range(run["x"] - 1090, run["x"] - 1090 + run["width"]):
                rebuilt[run["y"] - 96][x] = tuple(run["rgba"])
        self.assertEqual(rebuilt, rows, "All original pixel cells survive the run-length receipt exactly")

    def test_scroll_position_content_extent_and_css_border_width_never_determine_ink_bounds(self):
        rows, evidence = self.fixture()
        before = measure_gutter_pixels(rows, evidence, "vertical")
        evidence.update(scroll_top=0, scroll_height=90000, client_height=10)
        evidence["parts"][4]["border_widths"] = ["13px"] * 4
        after = measure_gutter_pixels(rows, evidence, "vertical")
        self.assertEqual(after["ink_bounds"], before["ink_bounds"])
        self.assertIsNone(after["outer_bounds"], "Ink is never expanded by a requested transparent CSS border")

    def test_horizontal_pixel_envelope_uses_original_cells_not_axis_ratio(self):
        rows, evidence = self.fixture()
        rows = [list(column) for column in zip(*rows)]
        evidence["gutters"] = {"horizontal": {"bounds": {"x": 100, "y": 300, "width": 20, "height": 10}, "fully_visible": True}}
        result = measure_gutter_pixels(rows, evidence, "horizontal")
        self.assertEqual(result["ink_bounds"], {"x": 105, "y": 303, "width": 10, "height": 4})
        self.assertEqual(result["orientation"], "horizontal")

    def test_no_gutter_or_fractional_gutter_stays_unknown_without_sampling_an_estimated_strip(self):
        rows, evidence = self.fixture()
        for bounds in (None, {"x": 1090.5, "y": 96, "width": 10, "height": 20}):
            with self.subTest(bounds=bounds):
                evidence["gutters"]["vertical"]["bounds"] = bounds
                result = measure_gutter_pixels(rows, evidence, "vertical")
                self.assertEqual(result["status"], "unknown"); self.assertIsNone(result["ink_bounds"])
                self.assertEqual(result["pixel_runs"], [])

    def test_occlusion_effects_or_other_part_paint_keep_raw_pixels_but_fail_attribution(self):
        for reason in ("occlusion", "opacity", "ancestor-background", "shadow", "track-fill", "border", "content"):
            with self.subTest(reason=reason):
                rows, evidence = self.fixture()
                if reason == "occlusion": evidence["gutters"]["vertical"]["fully_visible"] = False
                elif reason == "opacity": evidence["ancestry"][0]["opacity"] = ".5"
                elif reason == "ancestor-background": evidence["ancestry"][0]["background_image"] = "linear-gradient(white, gray)"
                elif reason == "shadow": evidence["parts"][4]["box_shadow"] = "rgb(0, 0, 0) 0px 0px 3px"
                elif reason == "track-fill": evidence["parts"][2]["computed_background_rgba"] = [100, 100, 100, 255]
                elif reason == "border":
                    evidence["parts"][4]["computed_border_rgba"] = [[0, 0, 0, 255]] * 4
                else: evidence["parts"][1]["content"] = '"arrow"'
                result = measure_gutter_pixels(rows, evidence, "vertical")
                self.assertEqual(result["status"], "unknown"); self.assertIsNone(result["ink_bounds"])
                self.assertTrue(result["reason"]); self.assertTrue(result["pixel_runs"])

    def test_multiple_components_do_not_choose_the_one_nearest_expected_scroll_position(self):
        rows, evidence = self.fixture()
        rows[2][4] = (216, 215, 213, 255)
        result = measure_gutter_pixels(rows, evidence, "vertical")
        self.assertEqual(result["status"], "unknown"); self.assertIsNone(result["ink_bounds"])
        self.assertEqual(len(result["components"]), 2)
        self.assertIn("ambiguous", result["reason"])

    def test_empty_crop_does_not_assert_absent_thumb_and_color_outlier_is_not_ignored(self):
        for empty in (True, False):
            with self.subTest(empty=empty):
                rows, evidence = self.fixture()
                if empty: rows = [[(255, 255, 255, 255)] * 10 for _ in range(20)]
                else: rows[8][4] = (20, 20, 20, 255)
                result = measure_gutter_pixels(rows, evidence, "vertical")
                self.assertEqual(result["status"], "unknown"); self.assertIsNone(result["ink_bounds"])
                self.assertTrue(result["pixel_runs"])

    def test_varying_background_perimeter_is_an_unresolved_measurement_not_a_new_tolerance(self):
        rows, evidence = self.fixture()
        rows[7][0] = (254, 255, 255, 255)
        result = measure_gutter_pixels(rows, evidence, "vertical")
        self.assertEqual(result["status"], "unknown")
        self.assertIn("uniform background", result["reason"])

    def test_source_transport_saves_original_pixels_but_never_promotes_ink_to_canonical_bounds(self):
        rows, evidence = self.fixture()
        image, raster = Mock(), Mock()
        image.format = "PNG"; image.mode = "RGB"; image.size = (1440, 900)
        image.convert.return_value = raster; raster.width = 1440; raster.height = 900
        raster.getpixel.side_effect = lambda point: rows[point[1] - 96][point[0] - 1090]
        raw = {"id": "dom-171", "scrollbar": evidence}
        thumb = {"id": "dom-171:scrollbar-thumb:vertical", "bounds": None, "visible_bounds": None,
            "style": {"background": None}, "evidence": {"outer_bounds": None, "hit_bounds": None, "ink_bounds": None}}
        elements = {"viewport": {"width": 1440, "height": 900, "scale": 1}, "raw_nodes": [raw], "elements": [thumb],
            "extraction_errors": [{"type": "ua_scrollbar_part_measurement_unavailable"}]}
        with tempfile.TemporaryDirectory() as folder, patch("PIL.Image.open", return_value=image):
            path = Path(folder) / "actual.scrollbar-pixels.json"
            append_scrollbar_pixels(elements, Path(folder) / "actual.png", path)
            receipt = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["parts"][0]["status"], "measured-ink")
        self.assertTrue(receipt["parts"][0]["pixel_runs"])
        self.assertIsNone(thumb["bounds"]); self.assertIsNone(thumb["visible_bounds"])
        self.assertIsNone(thumb["evidence"]["outer_bounds"]); self.assertIsNone(thumb["evidence"]["hit_bounds"])
        self.assertEqual(thumb["style"], {"background": None})
        self.assertEqual(thumb["evidence"]["ink_bounds"], {"x": 1093, "y": 101, "width": 4, "height": 10})
        self.assertEqual(elements["extraction_errors"], [{"type": "ua_scrollbar_part_measurement_unavailable"}])
        image.close.assert_called_once_with(); raster.close.assert_called_once_with()

    def test_missing_png_records_a_failure_without_replacing_unknown_measurements(self):
        _, evidence = self.fixture()
        elements = {"raw_nodes": [{"id": "dom-171", "scrollbar": evidence}], "elements": []}
        original = copy.deepcopy(elements["raw_nodes"])
        with tempfile.TemporaryDirectory() as folder, patch("PIL.Image.open", side_effect=FileNotFoundError("actual PNG missing")):
            path = Path(folder) / "failure.json"
            append_scrollbar_pixels(elements, Path(folder) / "missing.png", path)
            self.assertEqual(json.loads(path.read_text())["errors"], ["actual PNG missing"])
        self.assertEqual(elements["raw_nodes"], original)
        self.assertEqual(elements["extraction_errors"][0]["type"], "scrollbar_png_measurement_failed")


if __name__ == "__main__":
    unittest.main()
