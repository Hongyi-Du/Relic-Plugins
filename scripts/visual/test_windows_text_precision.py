"""Pure fixtures for observed precision, executed in CI only.

The two clipping geometries below are transcribed from 778c96b. Process IDs,
owner IDs and call clocks are synthetic; no fixture pretends to be a live run.
"""
import base64
import copy
import struct
import unittest

from test_windows_automation_identity import actual_pair
from windows_text_precision import (COM_COORDINATES, COM_ENDPOINTS, COM_SOURCE, PROBE_PHASE,
                                    PROBE_SOURCE, WINRT_ENDPOINTS, analyze_text_precision)


def encoded(text):
    raw = text.encode("utf-16-le", errors="surrogatepass")
    return {"value": text, "utf16_length": len(raw) // 2,
            "utf16_le_base64": base64.b64encode(raw).decode("ascii")}


def bits(values):
    return [struct.pack(">d", float(value)).hex().upper() for value in values]


def slice16(text, start, end):
    return text.encode("utf-16-le", errors="surrogatepass")[start * 2:end * 2].decode("utf-16-le", errors="surrogatepass")


def call(api, value):
    start = value.get("qpc", 20) if isinstance(value, dict) else 20
    return {"api": api, "status": "returned", "returned_normally": True, "hresult": None,
            "successful_hresult_not_exposed_by_projection": True, "returned_value": copy.deepcopy(value),
            "started_qpc": start, "completed_qpc": start + 1}


def owner_calls(owner):
    return [call("owner state before", owner["owner_before"]), call("owner state after", owner["owner_after"]),
            call("DocumentRange.GetText(-1) before", owner["document_text_before"]),
            call("DocumentRange.GetText(-1) after", owner["document_text_after"])]


def wrange(rid, text, start, end, values):
    part = encoded(slice16(text, start, end))
    return {"range_id": rid, "is_null": False, "endpoint_source": WINRT_ENDPOINTS,
            "started_qpc": 10, "completed_qpc": 40, "text": part,
            "calls": [call(rid + ".GetText(-1)", part), call(rid + ".GetBoundingRectangles", values)],
            "bounding_rectangle_values": values, "bounding_rectangle_value_bits_hex": bits(values),
            "rectangle_count": len(values) // 4, "rectangle_value_count": len(values),
            "all_rectangle_values_finite": True,
            "start": {"endpoint": "Start", "prefix_start_to_document_start": 0,
                      "prefix_end_to_range_endpoint": 0, "actual_prefix_text": encoded(slice16(text, 0, start)),
                      "verified_prefix_utf16_length": start},
            "end": {"endpoint": "End", "prefix_start_to_document_start": 0,
                    "prefix_end_to_range_endpoint": 0, "actual_prefix_text": encoded(slice16(text, 0, end)),
                    "verified_prefix_utf16_length": end},
            "offsets_within_document_snapshot": True, "text_matches_document_snapshot_slice": True}


def crange(text, start, end, values):
    return {"text": slice16(text, start, end), "range_identity": {"source": COM_ENDPOINTS,
            "within_document": True, "text_partition_valid": True, "start_utf16": start, "end_utf16": end,
            "start_prefix": slice16(text, 0, start), "end_prefix": slice16(text, 0, end)},
            "bounds_raw": values, "bounds_raw_ieee754_bits": bits(values),
            "raw_coordinate_space": COM_COORDINATES, "is_hidden": False}


def fixture(text="reviewer 加入了组织，角色「验收与回归检查」", precise=None, native=None, spans=None):
    if precise is None:
        precise = [467.1083984375, 96, 251.783203125, 0.8499908447265625]
    if native is None:
        native = [475, 127, 251, 0]
    length = encoded(text)["utf16_length"]
    spans = spans if spans is not None else [(0, length)]
    nodes, uia = actual_pair()
    nodes[0].update(type="TextBlock", text=text)
    nodes[0]["automation_identity_evidence"]["peer_type"] = "Microsoft.UI.Xaml.Automation.Peers.TextBlockAutomationPeer"
    xaml = {"scene_id": uia["case_id"], "raw_nodes": nodes}
    state = {"qpc": 5, "text": encoded(text), "is_loaded": True, "visibility": "Visible",
             "actual_width": 251.783203125, "actual_height": 19.200000762939453,
             "opacity": 1, "root_origin_x": 467.1083984375, "root_origin_y": 77.64999389648438,
             "root_origin_source": "Actual owner.TransformToVisual(null).TransformPoint(0,0)",
             "content_start_offset": 0, "content_end_offset": length + 4,
             "is_text_trimmed": False, "text_trimming": "None", "text_wrapping": "Wrap", "line_height": 19.2}
    owner = {"owner_id": nodes[0]["id"], "owner_type": "Microsoft.UI.Xaml.Controls.TextBlock",
             "status": "observed", "started_qpc": 0, "completed_qpc": 100,
             "owner_before": state, "owner_after": copy.deepcopy(state), "peer_is_null": False,
             "peer_type": nodes[0]["automation_identity_evidence"]["peer_type"],
             "peer_owner_same_object": True, "peer_same_object_after": True,
             "peer_owner_same_object_after": True, "events_source_same_object_after": True,
             "document_text_same_before_after": True, "owner_text_same_before_after": True,
             "events_source_before": {"is_null": True}, "events_source_after": {"is_null": True},
             "error_count": 0, "contract_issue_count": 0,
             "document_text_before": encoded(text), "document_text_after": encoded(text),
             "document_range": wrange("document", text, 0, length, precise),
             "visible_ranges": [wrange("visible-" + str(i), text, start, end, precise[i * 4:i * 4 + 4])
                                for i, (start, end) in enumerate(spans)]}
    owner["owner_after"]["qpc"] = 90
    owner["calls"] = owner_calls(owner)
    native_capture = {"source": COM_SOURCE, "status": "matched-to-managed-ranges", "runtime_id": [42, 91, 4, 7],
                      "document_text_before": text, "document_text_after": text, "managed_document_text_after": text,
                      "document": crange(text, 0, length, native),
                      "visible_ranges": [crange(text, start, end, native[i * 4:i * 4 + 4])
                                         for i, (start, end) in enumerate(spans)]}
    for item in native_capture["visible_ranges"]:
        item["format_runs"] = [copy.deepcopy(item)]
    uia["raw_nodes"][0].update(text_pattern={"native_com": native_capture},
                               measurement_errors=["COM text rectangle is zero-area; retained"])
    uia["origin"] = {"x": 8, "y": 31}
    uia["extraction_errors"] = [{"id": "uia-92", "error": "Actual zero-area range"}]
    probe = {"source": PROBE_SOURCE, "phase": PROBE_PHASE, "case_id": uia["case_id"],
             "started_qpc": 0, "completed_qpc": 100, "qpc_frequency": 10000000,
             "capture_completed": True, "metadata_modified": False, "create_peer_for_element_called": False,
             "coordinate_space": "Unmodified WinRT provider API values; no inferred or applied client/screen conversion",
             "owners": [owner], "errors": [], "contract_issues": []}
    return xaml, uia, probe


class TextPrecisionTests(unittest.TestCase):
    def test_fractional_reviewer_clip_links_actual_spans_and_preserves_errors(self):
        inputs = fixture()
        original = copy.deepcopy(inputs)
        report = analyze_text_precision(*inputs)
        self.assertEqual(report["unresolved"], [])
        entry = report["owners"][0]
        self.assertEqual(entry["runtime_id"], [42, 91, 4, 7])
        self.assertEqual(len(entry["range_associations"]), 2)
        for item in entry["range_associations"]:
            self.assertEqual(item["source_span_utf16"], [0, 26])
            self.assertEqual(item["rectangle_diagnostics"][0]["category"], "positive-subpixel-extent-to-com-zero")
            self.assertFalse(item["native_internal_endpoint_identity_proven"])
        self.assertFalse(entry["format_source_span_links"][0]["winrt_format_range_measured"])
        self.assertEqual(report["original_uia_errors"], original[1]["extraction_errors"])
        self.assertFalse(report["canonical_geometry_supplied"])
        self.assertFalse(report["visibility_supplied"])
        self.assertFalse(report["provider_errors_resolved"])
        self.assertEqual(inputs, original)

    def test_cabinet_last_line_clipping_keeps_all_three_real_rectangles(self):
        text = "全库只有一个秘书处，它的负责人就是秘书长：成员新建或调整正式组织，要秘书长批准；各正式组织的负责人也会自动在秘书处有一个席位。"
        precise = [1117, 862.4000244140625, 288, 18.5999755859375,
                   1117, 881, 288, 18.5999755859375,
                   1117, 899.5999755859375, 180, 0.4000244140625]
        native = [1125, 893, 288, 18, 1125, 912, 288, 18, 1125, 930, 180, 0]
        report = analyze_text_precision(*fixture(text, precise, native, [(0, 24), (24, 48), (48, 63)]))
        self.assertEqual(report["unresolved"], [])
        ranges = report["owners"][0]["range_associations"]
        self.assertEqual(len(ranges), 4)
        self.assertEqual(ranges[-1]["source_span_utf16"], [48, 63])
        self.assertEqual(ranges[-1]["winrt_values"][-1], 0.4000244140625)
        self.assertEqual(ranges[0]["winrt_values"], precise)

    def test_true_trimmed_zero_is_not_a_precision_recovery_or_hidden_proof(self):
        # Actual 7df sidebar terminal 's' also has an all-zero WinRT rectangle.
        text = "Acceptance and regression checks"
        precise = [80, 439.2650146484375, 153.28118896484375, 17.95501708984375,
                   233.28118896484375, 439.2650146484375, 10.819244384765625, 17.95501708984375,
                   0, 0, 0, 0]
        native = [88, 470, 153, 17, 241, 470, 10, 17, 8, 31, 0, 0]
        inputs = fixture(text, precise, native, [(0, 24), (31, 32)])
        owner = inputs[2]["owners"][0]
        owner["visible_ranges"][1] = wrange("visible-1", text, 31, 32, [0, 0, 0, 0])
        com = inputs[1]["raw_nodes"][0]["text_pattern"]["native_com"]
        com["visible_ranges"][1] = crange(text, 31, 32, [8, 31, 0, 0])
        com["visible_ranges"][1]["format_runs"] = [crange(text, 31, 32, [8, 31, 0, 0])]
        for state in (owner["owner_before"], owner["owner_after"]):
            state.update(is_text_trimmed=True, text_trimming="CharacterEllipsis", text_wrapping="NoWrap")
        owner["calls"] = owner_calls(owner)
        report = analyze_text_precision(*inputs)
        self.assertTrue(report["unresolved"])
        ranges = report["owners"][0]["range_associations"]
        self.assertEqual(ranges[0]["rectangle_diagnostics"][-1]["category"], "winrt-already-zero-area")
        self.assertEqual(ranges[-1]["source_span_utf16"], [31, 32])
        self.assertEqual(ranges[-1]["rectangle_diagnostics"][0]["category"], "winrt-already-zero-area")
        self.assertFalse(any(d["category"] == "positive-subpixel-extent-to-com-zero"
                             for r in ranges for d in r["rectangle_diagnostics"]))
        self.assertFalse(report["visibility_supplied"])

    def test_same_text_and_bounds_never_replace_missing_complete_identity(self):
        for alter in ("missing", "foreign", "duplicate", "failed-release"):
            with self.subTest(alter=alter):
                xaml, uia, probe = fixture()
                if alter == "missing":
                    del xaml["raw_nodes"][0]["automation_identity_evidence"]
                elif alter == "foreign":
                    uia["raw_nodes"][0]["runtime_id"] = "42.91.4.999"
                elif alter == "duplicate":
                    uia["raw_nodes"].append(copy.deepcopy(uia["raw_nodes"][0]))
                else:
                    uia["observer_hold"]["release"]["status"] = "failed"
                result = analyze_text_precision(xaml, uia, probe)
                self.assertEqual(result["owners"], [])
                self.assertTrue(result["unresolved"])

    def test_changed_peer_source_state_or_document_blocks_owner_association(self):
        for key, value in (("peer_same_object_after", False), ("peer_owner_same_object", False),
                           ("events_source_same_object_after", False), ("error_count", 1)):
            xaml, uia, probe = fixture()
            probe["owners"][0][key] = value
            self.assertEqual(analyze_text_precision(xaml, uia, probe)["owners"], [])
        xaml, uia, probe = fixture()
        probe["owners"][0]["owner_after"]["root_origin_y"] += 0.25
        self.assertEqual(analyze_text_precision(xaml, uia, probe)["owners"], [])
        xaml, uia, probe = fixture()
        uia["raw_nodes"][0]["text_pattern"]["native_com"]["document_text_after"] += "!"
        self.assertEqual(analyze_text_precision(xaml, uia, probe)["owners"], [])

    def test_unknown_malformed_or_false_finite_geometry_cannot_be_associated(self):
        for values in (None, [1, 2, 3], [1, 2, 3, float("nan")], [1, 2, 3, True]):
            xaml, uia, probe = fixture()
            for r in [probe["owners"][0]["document_range"], *probe["owners"][0]["visible_ranges"]]:
                r["bounding_rectangle_values"] = values
                r["calls"][1]["returned_value"] = values
            result = analyze_text_precision(xaml, uia, probe)
            self.assertEqual(result["owners"][0]["range_associations"], [])
            self.assertTrue(result["unresolved"])

    def test_api_failure_or_inconsistent_ieee_bits_does_not_use_numbers(self):
        for field, value in (("status", "failed"), ("hresult", -2147418113)):
            xaml, uia, probe = fixture()
            probe["owners"][0]["document_range"]["calls"][1][field] = value
            result = analyze_text_precision(xaml, uia, probe)
            self.assertNotIn("document", [r["com_range_path"] for r in result["owners"][0]["range_associations"]])
        xaml, uia, probe = fixture()
        probe["owners"][0]["visible_ranges"][0]["bounding_rectangle_value_bits_hex"][-1] = "0000000000000000"
        self.assertTrue(analyze_text_precision(xaml, uia, probe)["unresolved"])

    def test_utf16_offsets_and_format_subranges_are_not_inferred_from_text(self):
        report = analyze_text_precision(*fixture("A😀中"))
        self.assertEqual(report["owners"][0]["range_associations"][0]["source_span_utf16"], [0, 4])
        xaml, uia, probe = fixture()
        native = uia["raw_nodes"][0]["text_pattern"]["native_com"]
        text = native["document_text_before"]
        native["visible_ranges"][0]["format_runs"] = [crange(text, 0, 3, [475, 127, 20, 0])]
        report = analyze_text_precision(xaml, uia, probe)
        self.assertEqual(report["owners"][0]["format_source_span_links"], [])
        self.assertTrue(report["unresolved"])

    def test_ambiguous_visible_spans_are_not_chosen_by_geometry_or_index(self):
        xaml, uia, probe = fixture()
        duplicate = copy.deepcopy(probe["owners"][0]["visible_ranges"][0])
        duplicate["range_id"] = "visible-1"
        duplicate["calls"][0]["api"] = "visible-1.GetText(-1)"
        duplicate["calls"][1]["api"] = "visible-1.GetBoundingRectangles"
        probe["owners"][0]["visible_ranges"].append(duplicate)
        report = analyze_text_precision(xaml, uia, probe)
        self.assertEqual([r["com_range_path"] for r in report["owners"][0]["range_associations"]], ["document"])
        self.assertTrue(report["unresolved"])

    def test_non_subpixel_zero_is_unexplained_not_quantization(self):
        report = analyze_text_precision(*fixture(precise=[467, 96, 251, 2], native=[475, 127, 251, 0]))
        self.assertEqual(report["owners"][0]["range_associations"][0]["rectangle_diagnostics"][0]["category"],
                         "positive-extent-to-com-zero-unexplained")
        self.assertTrue(report["unresolved"])

    def test_unrelated_probe_failures_stay_visible_without_erasing_bound_owner(self):
        xaml, uia, probe = fixture()
        probe["contract_issues"].append({"owner_id": "xaml-other", "message": "Null GetVisibleRanges"})
        report = analyze_text_precision(xaml, uia, probe)
        self.assertEqual(len(report["owners"]), 1)
        self.assertEqual(report["original_probe_contract_issues"], probe["contract_issues"])

    def test_failed_capture_exit_does_not_erase_observed_identity_or_errors(self):
        xaml, uia, probe = fixture()
        uia["observer_hold"]["capture_exit_code"] = 1
        report = analyze_text_precision(xaml, uia, probe)
        self.assertEqual(len(report["owners"]), 1)
        self.assertEqual(report["original_uia_errors"], uia["extraction_errors"])


if __name__ == "__main__":
    unittest.main()
