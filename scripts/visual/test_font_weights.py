"""Independent recorded-shape font fixtures; no fonts, windows or processes run."""
from copy import deepcopy
import base64
import json
from pathlib import Path
import unittest

from font_weights import (MAC_DRAW_SOURCE, MAC_WEIGHT_SOURCE, OS2_TABLE_TAG, FVAR_TABLE_TAG,
                          WINDOWS_FACE_SOURCE, WINDOWS_FORMAT_SOURCE, WINDOWS_SUBMITTED_SCOPE,
                          compare_font_weights, font_weight_issues, project_font_weights)
from native_label_fonts import native_label_fonts
from test_native_label_fonts import trimmed_fixture, update_production


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


def synthetic_os2(value=400, version=0, length=68):
    """Parser fixture, not a downloaded/loaded font or measured production face."""
    table = bytearray(length)
    table[0:2] = version.to_bytes(2, "big")
    table[4:6] = value.to_bytes(2, "big")
    return base64.b64encode(table).decode("ascii")


def static_mac_element(value=400, version=0, length=68):
    item = mac_element(configured=value, actual=None)
    font = item["style"]["rendered_fonts"][0]
    font.update(family_name="Synthetic Static Fixture", postscript_name="SyntheticStaticFixture-Regular",
                actual_variations=None)
    font["weight_measurement"] = {
        "version": 1, "source": MAC_WEIGHT_SOURCE, "status": "measured", "postscript_name": font["postscript_name"],
        "quantity": "static-face-os2-usWeightClass", "value": value, "available_table_tags": [OS2_TABLE_TAG],
        "variation_axes": None, "actual_variations": None, "os2_base64": synthetic_os2(value, version, length)}
    item["evidence"]["projection"]["native_font_drawing"]["fonts"] = deepcopy(item["style"]["rendered_fonts"])
    return item


def sync_drawing_fonts(item):
    item["evidence"]["projection"]["native_font_drawing"]["fonts"] = deepcopy(item["style"]["rendered_fonts"])


def submitted_windows_element(actual=400, case=None):
    """Synthetic binding unless an unmodified recorded fixture case is supplied."""
    if case is None:
        node, image, frame = trimmed_fixture()
        draw = node["native_label_evidence"]["draw"]
        draw["actual_text_format"] = {"source": WINDOWS_FORMAT_SOURCE, "font_weight": 400}
        for run in draw["glyph_runs"]:
            run["face"]["axes"] = [{"tag": "wght", "value": actual}]
        update_production(node, frame)
    else:
        node, image, frame = (deepcopy(case[key]) for key in ("node", "image", "frame"))
    rendered, issues = native_label_fonts(node, image, frame)
    if issues:
        raise AssertionError(issues)
    evidence = {"type": "NativeLabel", "native_label_evidence": deepcopy(node["native_label_evidence"]),
                "native_label_fonts": rendered}
    if case is None:
        evidence["native_label_submission"] = {"style": {"font_weight": 400}}
    return {"id": node["id"], "kind": "text", "text": node["text"],
            "style": {"font_weight": 400, "rendered_fonts": deepcopy(rendered["fonts"])}, "evidence": evidence}


class FontWeightTests(unittest.TestCase):
    def test_bound_static_face_os2_is_decoded_without_rewriting_configured_or_legacy_weights(self):
        item = static_mac_element(400)
        original = deepcopy(item)
        result = project_font_weights(item)
        face = result["resolved"]["faces"][0]
        self.assertEqual(face["value"], 400)
        self.assertEqual(face["quantity"], "static-face-os2-usWeightClass")
        self.assertEqual(face["parsed_os2"], {"version": 0, "byte_length": 68, "usWeightClass": 400,
                                             "offset": 4, "byte_order": "big"})
        self.assertEqual(face["raw"], item["style"]["rendered_fonts"][0])
        self.assertEqual(result["configured"]["value"], 400)
        self.assertEqual(result["legacy"]["value"], 600)
        self.assertEqual(font_weight_issues(item), [])
        self.assertEqual(item, original)
        self.assertEqual([row["field"] for row in compare_font_weights(reference_element(), item)],
                         ["font_weight.configured", "font_weight.resolved"])

    def test_known_os2_versions_and_weight_range_endpoints_use_the_actual_big_endian_bytes(self):
        for version in range(6):
            for value in (1, 400, 700, 1000):
                with self.subTest(version=version, value=value):
                    item = static_mac_element(value, version, 100)
                    face = project_font_weights(item)["resolved"]["faces"][0]
                    self.assertEqual(face["value"], value)
                    self.assertEqual(face["parsed_os2"]["version"], version)
                    self.assertEqual(font_weight_issues(item), [])

    def test_static_face_rejects_unknown_variable_inconsistent_or_corrupt_table_receipts(self):
        changes = ("missing-inventory", "null-inventory", "missing-os2", "fvar", "bad-table-tag", "bool-table-tag",
                   "axes-missing", "axes-nonempty", "axes-wrong-type", "coordinates-missing", "coordinates-nonempty",
                   "font-coordinates-missing", "font-coordinates-nonempty", "wrong-ps", "missing-ps",
                   "source", "receipt-version", "receipt-version-bool", "status", "quantity", "missing-bytes",
                   "bad-base64", "truncated", "unknown-version", "zero-weight", "excess-weight", "different-value", "bool-value")
        for change in changes:
            with self.subTest(change=change):
                item = static_mac_element()
                font = item["style"]["rendered_fonts"][0]
                receipt = font["weight_measurement"]
                if change == "missing-inventory": receipt.pop("available_table_tags")
                elif change == "null-inventory": receipt["available_table_tags"] = None
                elif change == "missing-os2": receipt["available_table_tags"] = [int.from_bytes(b"name", "big")]
                elif change == "fvar": receipt["available_table_tags"].append(FVAR_TABLE_TAG)
                elif change == "bad-table-tag": receipt["available_table_tags"].append("fvar")
                elif change == "bool-table-tag": receipt["available_table_tags"].append(True)
                elif change == "axes-missing": receipt.pop("variation_axes")
                elif change == "axes-nonempty": receipt["variation_axes"] = [{"tag": 2003265652}]
                elif change == "axes-wrong-type": receipt["variation_axes"] = {}
                elif change == "coordinates-missing": receipt.pop("actual_variations")
                elif change == "coordinates-nonempty": receipt["actual_variations"] = {"1869640570": 12}
                elif change == "font-coordinates-missing": font.pop("actual_variations")
                elif change == "font-coordinates-nonempty": font["actual_variations"] = {"2003265652": 600}
                elif change == "wrong-ps": receipt["postscript_name"] = "AnotherActualFace"
                elif change == "missing-ps": font.pop("postscript_name")
                elif change == "source": receipt["source"] = "separately resolved replacement font"
                elif change == "receipt-version": receipt["version"] = 2
                elif change == "receipt-version-bool": receipt["version"] = True
                elif change == "status": receipt["status"] = "unmeasured"
                elif change == "quantity": receipt["quantity"] = "configured weight"
                elif change == "missing-bytes": receipt.pop("os2_base64")
                elif change == "bad-base64": receipt["os2_base64"] = "%%invalid%%"
                elif change == "truncated": receipt["os2_base64"] = synthetic_os2(length=67)
                elif change == "unknown-version": receipt["os2_base64"] = synthetic_os2(version=6)
                elif change == "zero-weight": receipt["os2_base64"] = synthetic_os2(value=0)
                elif change == "excess-weight": receipt["os2_base64"] = synthetic_os2(value=1001)
                elif change == "different-value": receipt["value"] = 700
                elif change == "bool-value": receipt["value"] = True
                sync_drawing_fonts(item)
                self.assertIsNone(project_font_weights(item)["resolved"]["faces"][0]["value"])
                self.assertTrue(any(issue["field"] == "font_weight.resolved" for issue in font_weight_issues(item)))

    def test_static_face_requires_actual_draw_and_source_owner_before_parsing_table(self):
        for change in ("source-text", "status", "provider", "callback-fonts"):
            with self.subTest(change=change):
                item = static_mac_element()
                projection = item["evidence"]["projection"]
                drawing = projection["native_font_drawing"]
                if change == "source-text": projection["text"] = "unrelated source"
                elif change == "status": drawing["status"] = "stale-draw"
                elif change == "provider": drawing["provider"] = "new independent font layout"
                elif change == "callback-fonts": drawing["fonts"][0]["weight_measurement"]["value"] = 700
                self.assertIsNone(project_font_weights(item)["resolved"]["faces"])

    def test_empty_explicit_variations_allow_static_face_but_never_fill_a_missing_variable_coordinate(self):
        item = static_mac_element()
        font = item["style"]["rendered_fonts"][0]
        receipt = font["weight_measurement"]
        receipt["variation_axes"] = []
        font["actual_variations"] = receipt["actual_variations"] = {}
        sync_drawing_fonts(item)
        self.assertEqual(project_font_weights(item)["resolved"]["faces"][0]["value"], 400)
        receipt["available_table_tags"].append(FVAR_TABLE_TAG)
        sync_drawing_fonts(item)
        self.assertIsNone(project_font_weights(item)["resolved"]["faces"][0]["value"])

    def test_variable_receipt_uses_actual_coordinate_not_static_os2_value(self):
        item = static_mac_element(400)
        font = item["style"]["rendered_fonts"][0]
        receipt = font["weight_measurement"]
        font["actual_variations"] = {"2003265652": 650}
        receipt.update(quantity="actual-wght-coordinate", value=650, actual_variations={"2003265652": 650},
                       available_table_tags=[OS2_TABLE_TAG, FVAR_TABLE_TAG], variation_axes=[{"tag": 2003265652}])
        sync_drawing_fonts(item)
        face = project_font_weights(item)["resolved"]["faces"][0]
        self.assertEqual(face["value"], 650)
        self.assertEqual(face["quantity"], "actual-wght-coordinate")
        self.assertNotIn("parsed_os2", face)
        for change in ("value", "coordinate", "no-coordinate"):
            with self.subTest(change=change):
                broken = deepcopy(item)
                bad = broken["style"]["rendered_fonts"][0]["weight_measurement"]
                if change == "value": bad["value"] = 400
                elif change == "coordinate": bad["actual_variations"]["2003265652"] = 400
                else: bad["actual_variations"] = {}
                sync_drawing_fonts(broken)
                self.assertIsNone(project_font_weights(broken)["resolved"]["faces"][0]["value"])

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

    def test_trimmed_resolved_faces_cover_actual_submission_without_claiming_original_suffix(self):
        item = submitted_windows_element()
        before = deepcopy(item)
        measured = project_font_weights(item)
        self.assertEqual(font_weight_issues(item), [])
        self.assertIs(measured["resolved"]["source_span_complete"], False)
        self.assertEqual(measured["resolved"]["coverage"], {
            "quantity": WINDOWS_SUBMITTED_SCOPE, "complete": True,
            "source_evidence_path": "evidence.native_label_fonts", "original_source_span_complete": False,
            "run_ordinals": [0, 1]})
        self.assertEqual([face["value"] for face in measured["resolved"]["faces"]], [400, 400])
        self.assertEqual([face["raw"] for face in measured["resolved"]["faces"]], item["style"]["rendered_fonts"])
        self.assertFalse(item["evidence"]["native_label_fonts"]["final_png_attribution_proven"])
        self.assertFalse(item["evidence"]["native_label_fonts"]["source_span_complete"])
        self.assertEqual(item, before)

    def test_trimmed_coverage_does_not_accept_completion_flags_without_actual_run_bindings(self):
        for mutation in ("flag-only", "missing-draw", "different-owner", "different-source", "different-layout",
                         "wrong-ordinal", "missing-ellipsis-font", "changed-axis", "missing-original-status"):
            with self.subTest(mutation=mutation):
                item = submitted_windows_element()
                rendered = item["evidence"]["native_label_fonts"]
                if mutation == "flag-only":
                    item["evidence"]["native_label_fonts"] = {key: rendered[key] for key in (
                        "status", "fonts", "source_span_complete", "original_source_span_complete", "submitted_glyph_runs_complete")}
                elif mutation == "missing-draw": item["evidence"]["native_label_evidence"].pop("draw")
                elif mutation == "different-owner": rendered["binding"]["image"]["owner_id"] = "other"
                elif mutation == "different-source": item["evidence"]["native_label_evidence"]["text"] = "changed"
                elif mutation == "different-layout": rendered["binding"]["layout_com_identity"] = "other"
                elif mutation == "wrong-ordinal": rendered["fonts"][0]["run_ordinal"] = 1
                elif mutation == "missing-ellipsis-font":
                    rendered["fonts"].pop(); rendered["run_font_evidence"].pop()
                elif mutation == "changed-axis": rendered["fonts"][0]["axes"][0]["value"] = 600
                else: rendered.pop("original_source_span_complete")
                if mutation in ("wrong-ordinal", "missing-ellipsis-font", "changed-axis"):
                    item["style"]["rendered_fonts"] = deepcopy(rendered["fonts"])
                self.assertTrue(any(row["field"] == "font_weight.resolved" for row in font_weight_issues(item)))

    def test_cached_trimmed_weights_require_exact_face_record_axis_and_coverage_quantity(self):
        for mutation in ("weight", "raw-face", "face-name", "missing-face", "duplicate-face", "run-order",
                         "coverage-flag", "coverage-run", "coverage-quantity", "original-complete"):
            with self.subTest(mutation=mutation):
                item = submitted_windows_element()
                measured = project_font_weights(item)
                resolved = measured["resolved"]
                if mutation == "weight": resolved["faces"][-1]["value"] = 600
                elif mutation == "raw-face": resolved["faces"][-1]["raw"]["axes"][0]["value"] = 600
                elif mutation == "face-name": resolved["faces"][-1]["family_name"] = "Requested family"
                elif mutation == "missing-face": resolved["faces"].pop()
                elif mutation == "duplicate-face": resolved["faces"].append(deepcopy(resolved["faces"][-1]))
                elif mutation == "run-order": resolved["faces"].reverse()
                elif mutation == "coverage-flag": resolved["coverage"] = {"complete": True}
                elif mutation == "coverage-run": resolved["coverage"]["run_ordinals"] = [0]
                elif mutation == "coverage-quantity": resolved["coverage"]["quantity"] = "visible-final-png-fonts"
                else: resolved["source_span_complete"] = True
                item["evidence"]["font_weight_quantities"] = measured
                self.assertTrue(any(row["field"] == "font_weight.resolved" for row in font_weight_issues(item)))

    def test_trimmed_missing_or_ambiguous_actual_wght_cannot_use_configured_weight(self):
        for axes in ([], [{"tag": "wdth", "value": 100}],
                     [{"tag": "wght", "value": 400}, {"tag": "wght", "value": 400}]):
            node, image, frame = trimmed_fixture()
            node["native_label_evidence"]["draw"]["glyph_runs"][-1]["face"]["axes"] = axes
            update_production(node, frame)
            item = submitted_windows_element(case={"node": node, "image": image, "frame": frame})
            self.assertTrue(any(row["field"] == "font_weight.resolved" for row in font_weight_issues(item)))

    def test_trimmed_weight_comparison_keeps_zero_tolerance_and_unknown_reference_failure(self):
        records = compare_font_weights(submitted_windows_element(400), submitted_windows_element(400.1))
        self.assertEqual([row["field"] for row in records], ["font_weight.resolved"])
        self.assertEqual(records[0]["tolerance"], 0)
        records = compare_font_weights(reference_element(), submitted_windows_element())
        resolved = next(row for row in records if row["field"] == "font_weight.resolved")
        self.assertTrue(any(side == "reference" for side, _ in resolved["measurement_errors"]))

    def test_recorded_trimmed_faces_use_each_actual_axis_without_promoting_png_coverage(self):
        recorded = json.loads((Path(__file__).parent / "fixtures" / "native-label-trimmed-67ed20d.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded["provenance"]["commit"], "67ed20d")
        for case in recorded["cases"]:
            item = submitted_windows_element(case=case)
            before = deepcopy(item)
            measured = project_font_weights(item)
            self.assertFalse(any(row["field"] == "font_weight.resolved" for row in font_weight_issues(item)))
            self.assertEqual(measured["resolved"]["coverage"]["run_ordinals"], [0, 1, 2, 3])
            self.assertIs(measured["resolved"]["source_span_complete"], False)
            self.assertEqual([face["value"] for face in measured["resolved"]["faces"]], [400] * 4)
            self.assertFalse(item["evidence"]["native_label_fonts"]["final_png_attribution_proven"])
            self.assertEqual(item, before)

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
