"""Pure measured-outline fixtures; no browser or native UI is launched."""
import unittest

from element_parity import compare_elements, validate_capture, delta_e, geometry_tolerance
from outline_paint import outline_measurement, compare_outlines
from test_element_parity import capture, element


def outlined(eid="r0"):
    item = element(eid)
    item["style"]["outline"] = {"style": "dashed", "width": 1.5, "offset": -1.5,
        "color": [27, 27, 26, 255], "dash": [3, 3], "dash_offset": 0,
        "contour": {"coordinate_space": "window", "paths": [{"d": "M10 12L110 12L110 32L10 32Z"}]}}
    item["evidence"]["outline"] = {"source": "synthetic independently measured outline", "absence_proven": False}
    return item


class OutlinePaintTests(unittest.TestCase):
    def test_measured_outline_does_not_change_border(self):
        a, b = outlined(), outlined("n")
        self.assertEqual(0, a["style"]["border_width"])
        self.assertFalse(outline_measurement(a)[1])
        self.assertFalse(compare_elements([a], [b])["style_out_of_tolerance"])
        self.assertEqual([], validate_capture(capture(elements=[a]), "reference", "zh-CN-light-1440x900-group", {"width": 1440, "height": 900, "scale": 1}))

    def test_computed_dashed_style_does_not_prove_segments_phase_or_contour(self):
        a, b = outlined(), outlined("n")
        for item in (a, b):
            item["style"]["outline"].update(dash=None, dash_offset=None, contour=None)
        issues = outline_measurement(a)[1]
        self.assertTrue(any("segments" in issue for issue in issues))
        self.assertTrue(any("phase" in issue for issue in issues))
        self.assertTrue(any("contour" in issue for issue in issues))
        self.assertTrue(compare_elements([a], [b])["extraction_errors"])

    def test_legacy_native_outline_keeps_values_and_missing_phase(self):
        item = element()
        del item["style"]["outline"]
        raw = {"width": 1.5, "color": [27, 27, 26, 255], "offset": -1.5,
               "dash": [3, 3], "renderer": "actual native stroke"}
        item["style"]["native_outline"] = raw
        result, issues = outline_measurement(item)
        self.assertEqual(raw["dash"], result["dash"])
        self.assertEqual(raw["width"], result["width"])
        self.assertIsNone(result["dash_offset"])
        self.assertIsNone(result["contour"])
        self.assertTrue(issues)
        self.assertEqual(raw, item["style"]["native_outline"])

    def test_no_outline_needs_actual_absence_proof(self):
        for change in ("missing", "null", "unproven"):
            item = element()
            if change == "missing": del item["style"]["outline"]
            elif change == "null": item["style"]["outline"] = None
            else: del item["evidence"]["outline"]["absence_proven"]
            self.assertTrue(outline_measurement(item)[1])
        self.assertTrue(compare_elements([outlined()], [element("n")])["style_out_of_tolerance"])

    def test_outline_width_offset_pattern_and_phase_compare_exactly(self):
        for field, value in (("width", 1.6), ("offset", -1.4), ("dash", [3, 4]), ("dash_offset", .01)):
            a, b = outlined(), outlined("n")
            b["style"]["outline"][field] = value
            self.assertTrue(any(row["field"] == "outline." + field for row in compare_elements([a], [b])["style_out_of_tolerance"]))

    def test_outline_contour_geometry_uses_existing_box_tolerance(self):
        a, b = outlined(), outlined("n")
        b["style"]["outline"]["contour"]["paths"][0]["d"] = "M14 12L114 12L114 32L14 32Z"
        self.assertFalse(compare_elements([a], [b])["geometry_out_of_tolerance"])
        b["style"]["outline"]["contour"]["paths"][0]["d"] = "M14.001 12L114 12L114 32L14 32Z"
        self.assertTrue(compare_elements([a], [b])["geometry_out_of_tolerance"])

    def test_bad_outline_measurements_and_arbitrary_contours_do_not_pass(self):
        for key, value in (("width", float("inf")), ("offset", True), ("dash", [3, float("nan")]),
                           ("color", [0, 0, 0, None]), ("contour", {"expected_radius": 11}), ("style", "auto")):
            item = outlined(); item["style"]["outline"][key] = value
            self.assertTrue(outline_measurement(item)[1])
        item = outlined(); item["style"]["outline"]["contour"]["paths"][0]["d"] = "M0 0L1"
        self.assertTrue(outline_measurement(item)[1])

    def test_outline_color_keeps_current_delta_e_and_alpha_rules(self):
        a, b = outlined(), outlined("n")
        b["style"]["outline"]["color"] = [255, 255, 255, 255]
        self.assertTrue(any(row["field"] == "outline.color" for row in compare_elements([a], [b])["style_out_of_tolerance"]))
        b["style"]["outline"]["color"] = [27, 27, 26, 254]
        self.assertTrue(compare_elements([a], [b])["style_out_of_tolerance"])

    def test_null_or_nonobject_owner_bounds_report_geometry_unknown_without_crash(self):
        for bounds in (None, [], "unknown", {"width": None, "height": None}):
            a, b = outlined(), outlined("n")
            a["bounds"] = bounds
            with self.subTest(bounds=bounds):
                records = compare_outlines(a, b, color_distance=delta_e, geometry_tolerance=geometry_tolerance)
                failures = [record for record in records if record["category"] == "geometry_out_of_tolerance"]
                self.assertTrue(failures)
                self.assertTrue(all(record["tolerance"] is None and "owner extent" in record["reason"] for record in failures))
