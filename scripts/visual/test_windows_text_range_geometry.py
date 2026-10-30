"""Actual 35ac04a receipt regression and deliberately corrupted negative copies.

Pure JSON tests only; CI discovers this file without opening native windows.
The fixture retains the historical capture wrapper as an unresolved error.
"""
import copy
import json
import struct
import unittest
from pathlib import Path

from windows_text_range_geometry import SOURCE, select_observed_text_geometry


FIXTURE = Path(__file__).with_name("fixtures") / "windows-text-range-geometry-35ac04a.json"


def fixture(before_capture_wrapper=False):
    source = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if before_capture_wrapper:
        # This test models the existing call site before capture.py adds its
        # exit wrapper; it does not change or claim new captured evidence.
        wrapper = source["uia"]["extraction_errors"].pop()
        assert wrapper.startswith("UIA extractor exited 1:")
    return source


def select(source):
    return select_observed_text_geometry(*(source[key] for key in ("xaml", "uia", "probe", "frame")))


def owner(source):
    return source["probe"]["owners"][0]


def last_range(source):
    return owner(source)["com"]["visible_ranges"][2]


def bits(values):
    return [struct.pack(">d", float(value)).hex().upper() for value in values]


class ObservedTextRangeGeometryTests(unittest.TestCase):
    def test_actual_three_zero_diagnostics_are_resolved_but_capture_wrapper_is_not(self):
        source = fixture()
        before = copy.deepcopy(source)
        result = select(source)
        audit = result["audit"]
        self.assertEqual(source, before, "Original capture JSON must remain unchanged")
        self.assertEqual([entry["path"] for entry in audit["selections"]], [
            "document_range", "visible_ranges[2]", "visible_ranges[2].format_runs[0]"])
        self.assertEqual(sum(entry["occurrences"] for entry in audit["resolved_diagnostics"]), 3)
        self.assertEqual(result["effective_uia"]["extraction_errors"], [source["uia"]["extraction_errors"][-1]])
        self.assertFalse(result["all_original_failures_resolved"])
        self.assertEqual(audit["original_extraction_errors"], source["uia"]["extraction_errors"])
        self.assertFalse(audit["original_uia_rewritten"])
        self.assertFalse(audit["font_or_final_pixel_evidence_promoted"])

    def test_observed_float_geometry_uses_its_own_actual_screen_to_client_origin(self):
        source = fixture(before_capture_wrapper=True)
        result = select(source)
        self.assertTrue(result["all_original_failures_resolved"], result["audit"])
        self.assertEqual(result["effective_uia"]["extraction_errors"], [])
        self.assertEqual(result["effective_uia"]["raw_nodes"][0]["measurement_errors"], [])
        for entry in result["audit"]["selections"]:
            self.assertEqual(entry["source"], SOURCE)
            self.assertEqual(entry["owner_binding"]["runtime_id"], [42, 917616, 4, 230])
            self.assertEqual(entry["owner_binding"]["state_checkpoints_equal"], 6)
            self.assertEqual(entry["owner_binding"]["origin"], {"x": 8, "y": 31})
            self.assertFalse(entry["owner_binding"]["global_composition_continuity_proven"])
            self.assertFalse(entry["owner_binding"]["font_or_final_pixel_evidence_promoted"])
            self.assertEqual(entry["selected_client_bounds"][-1],
                             {"x": 1117, "y": 899, "width": 180, "height": 0.4000244140625})
            self.assertEqual(entry["original_external_range"]["bounds_raw"][-4:], [1125, 930, 180, 0])
            self.assertEqual(entry["observed_inprocess_range"]["bounding_rectangle_values"][-4:],
                             [1125, 930, 180, 0.4000244140625])
            self.assertEqual(entry["observed_inprocess_range"]["bounding_rectangle_value_bits_hex"][-1], "3FD99A0000000000")
        pattern = result["effective_uia"]["raw_nodes"][0]["text_pattern"]
        for pattern in (pattern, pattern["native_com"]):
            self.assertEqual(pattern["visible_ranges"][2]["bounds"][-1]["y"], 899)
            self.assertEqual(pattern["visible_ranges"][2]["format_runs"][0]["bounds"][-1]["height"], 0.4000244140625)

    def test_unknown_first_visible_endpoint_is_not_inferred_from_document_start(self):
        source = fixture(before_capture_wrapper=True)
        result = select(source)
        first = owner(source)["com"]["visible_ranges"][0]
        self.assertIsNone(first["start"]["verified_prefix_utf16_length"])
        self.assertEqual(first["start"]["prefix_start_to_end_compare"], -2)
        unavailable = {entry.get("path") for entry in result["audit"]["unavailable_ranges"]}
        self.assertIn("visible_ranges[0]", unavailable)
        self.assertIn("visible_ranges[0].format_runs[0]", unavailable)
        self.assertEqual(result["effective_uia"]["raw_nodes"][0]["text_pattern"]["visible_ranges"][0],
                         source["uia"]["raw_nodes"][0]["text_pattern"]["visible_ranges"][0])

    def test_foreign_owner_runtime_id_observer_or_ambiguous_owner_cannot_resolve(self):
        def change_runtime(source):
            source["uia"]["raw_nodes"][0]["runtime_id"] = "42.917616.4.231"
        def change_held_identity(source):
            owner(source)["held_identity_before"]["process_id"] += 1
        def change_current_runtime(source):
            owner(source)["native_identity"]["core_runtime_id"]["values"][-1] += 1
        def change_observer(source):
            source["uia"]["observer_hold"]["observer_pid"] += 1
        def change_probe_app_pid(source):
            source["probe"]["observer"]["app_pid"] += 1
        def change_probe_observer_pid(source):
            source["probe"]["observer"]["observer_pid"] += 1
        def duplicate_owner(source):
            source["probe"]["owners"].append(copy.deepcopy(owner(source)))
        for mutation in (change_runtime, change_held_identity, change_current_runtime, change_observer,
                         change_probe_app_pid, change_probe_observer_pid, duplicate_owner):
            with self.subTest(mutation=mutation.__name__):
                source = fixture(before_capture_wrapper=True)
                mutation(source)
                result = select(source)
                self.assertFalse(result["all_original_failures_resolved"])
                self.assertEqual(result["audit"]["selections"], [])
                self.assertEqual(result["effective_uia"]["extraction_errors"], source["uia"]["extraction_errors"])

    def test_foreign_origin_frame_revision_state_time_and_scale_cannot_resolve(self):
        def change_origin(source):
            source["uia"]["origin"]["y"] += 1
        def change_frame_state(source):
            source["frame"]["checkpoints"][2]["owners"][0]["client_origin"][1] += 1
        def change_revision(source):
            owner(source)["frame_after"]["revision"] += 1
        def missing_frame(source):
            source["frame"]["checkpoints"].pop()
        def change_frame_time(source):
            source["frame"]["checkpoints"][-1]["started_qpc"] = source["probe"]["started_qpc"] - 1
        def change_scale(source):
            source["uia"]["viewport"]["scale"] = 2
        for mutation in (change_origin, change_frame_state, change_revision, missing_frame, change_frame_time, change_scale):
            with self.subTest(mutation=mutation.__name__):
                source = fixture(before_capture_wrapper=True)
                mutation(source)
                result = select(source)
                self.assertFalse(result["all_original_failures_resolved"])
                self.assertEqual(result["audit"]["selections"], [])

    def test_wrong_endpoint_source_span_and_category_leave_exact_range_unresolved(self):
        def change_source(source):
            last_range(source)["start"]["source"] = "inferred text search"
        def change_span(source):
            last_range(source)["start"]["verified_prefix_utf16_length"] = 47
        def change_comparison(source):
            last_range(source)["start"]["start_compare"] = 1
        def change_category(source):
            last_range(source)["range_path"] = "document_range"
        def change_range_time(source):
            last_range(source)["started_qpc"] = owner(source)["frame_before"]["qpc"] - 1
        for mutation in (change_source, change_span, change_comparison, change_category, change_range_time):
            with self.subTest(mutation=mutation.__name__):
                source = fixture(before_capture_wrapper=True)
                mutation(source)
                result = select(source)
                self.assertFalse(result["all_original_failures_resolved"])
                self.assertNotIn("visible_ranges[2]", [entry["path"] for entry in result["audit"]["selections"]])
                self.assertEqual(len(result["effective_uia"]["extraction_errors"]), 2,
                                 "Identical original visible/format diagnostics need two independently bound measurements")

    def test_missing_actual_format_measurement_does_not_borrow_visible_rectangle(self):
        source = fixture(before_capture_wrapper=True)
        last_range(source)["format_runs"] = []
        result = select(source)
        self.assertFalse(result["all_original_failures_resolved"])
        self.assertEqual([entry["path"] for entry in result["audit"]["selections"]], ["document_range", "visible_ranges[2]"])
        self.assertEqual(len(result["effective_uia"]["extraction_errors"]), 2)

    def test_unknown_or_wrong_original_client_conversion_is_not_replaced(self):
        for failure in ("unknown", "wrong-origin", "actual-error"):
            with self.subTest(failure=failure):
                source = fixture(before_capture_wrapper=True)
                managed = source["uia"]["raw_nodes"][0]["text_pattern"]["visible_ranges"][2]
                if failure == "unknown":
                    managed["bounds"] = None
                elif failure == "wrong-origin":
                    managed["bounds"][0]["y"] += 1
                else:
                    managed["bounds_error"] = "actual failed observation"
                result = select(source)
                self.assertFalse(result["all_original_failures_resolved"])
                self.assertNotIn("visible_ranges[2]", [entry["path"] for entry in result["audit"]["selections"]])

    def test_failed_actual_com_call_or_incomplete_format_enumeration_is_not_success(self):
        for failure in ("failed-call", "incomplete-enumeration"):
            with self.subTest(failure=failure):
                source = fixture(before_capture_wrapper=True)
                if failure == "failed-call":
                    call = next(call for call in owner(source)["com"]["calls"]
                                if call["api"] == "visible_ranges[2].format_runs[0].MoveEndpointByUnit(End,Format,1)")
                    call["hresult"] = -2147467259
                    call["succeeded"] = False
                else:
                    last_range(source)["format_enumeration"]["complete"] = False
                result = select(source)
                self.assertFalse(result["all_original_failures_resolved"])
                self.assertNotIn("visible_ranges[2].format_runs[0]", [entry["path"] for entry in result["audit"]["selections"]])

    def test_zero_negative_wrong_coordinate_or_missing_bits_are_not_filled(self):
        for failure in ("actual-zero", "actual-negative", "different-coordinate", "missing-bits"):
            with self.subTest(failure=failure):
                source = fixture(before_capture_wrapper=True)
                precise = last_range(source)
                if failure == "missing-bits":
                    del precise["bounding_rectangle_value_bits_hex"]
                else:
                    values = precise["bounding_rectangle_values"]
                    if failure == "different-coordinate":
                        values[1] -= 0.4000244140625  # No mixing this channel with the WinRT coordinate.
                    else:
                        values[-1] = 0 if failure == "actual-zero" else -0.4
                    precise["bounding_rectangle_value_bits_hex"] = bits(values)
                result = select(source)
                self.assertFalse(result["all_original_failures_resolved"])
                self.assertNotIn("visible_ranges[2]", [entry["path"] for entry in result["audit"]["selections"]])

    def test_unrelated_failure_and_raw_fields_remain_after_geometry_selection(self):
        source = fixture(before_capture_wrapper=True)
        source["uia"]["extraction_errors"].append("uia-233: actual font provider failure")
        source["uia"]["raw_nodes"][0]["measurement_errors"].append("actual font provider failure")
        original = copy.deepcopy(source)
        result = select(source)
        self.assertFalse(result["all_original_failures_resolved"])
        self.assertEqual(result["effective_uia"]["extraction_errors"], ["uia-233: actual font provider failure"])
        self.assertEqual(source, original)
        effective = result["effective_uia"]["raw_nodes"][0]["text_pattern"]
        original_pattern = source["uia"]["raw_nodes"][0]["text_pattern"]
        for pattern, original_pattern in ((effective, original_pattern), (effective["native_com"], original_pattern["native_com"])):
            for key in original_pattern["visible_ranges"][2]:
                if key not in {"bounds", "bounds_status", "format_runs"}:
                    self.assertEqual(pattern["visible_ranges"][2][key], original_pattern["visible_ranges"][2][key])
        self.assertEqual(result["effective_uia"]["raw_extraction_errors"], source["uia"]["raw_extraction_errors"])


if __name__ == "__main__":
    unittest.main()
