"""Synthetic replicas of actual receipt shapes; no renderer, server or UI runs."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from native_label_fonts import (BINDING_SOURCE, CHECKPOINTS, FACE_SOURCE, FRAME_SOURCE,
                                IMAGE_SOURCE, LABEL_SOURCE, READBACK_SOURCE, RUN_SOURCE,
                                STATE_SOURCE, INLINE_SOURCE, TRIMMING_SOURCE, native_label_fonts)


def utf16_length(text):
    return len(text.encode("utf-16-le", errors="surrogatepass")) // 2


def face(family="Measured Physical Face", postscript="MeasuredPhysicalFace"):
    # Names and file references are synthetic, not observations from a CI run.
    return {"source": FACE_SOURCE, "face_index": 1, "simulations": 0,
            "family_names": [{"locale": "en-us", "value": family}, {"locale": "zh-cn", "value": family}],
            "face_names": [{"locale": "en-us", "value": "Regular"}],
            "postscript_names": [{"locale": "en-us", "value": postscript}, {"locale": "zh-cn", "value": postscript + "Localized"}],
            "axes": [{"tag": "wght", "value": 400}], "color_font": False,
            "files": [{"reference_key_base64": "c3ludGhldGlj", "loader_process_identity": "fixture-loader"}],
            "weight": 400, "stretch": 5, "style": 0}


def fixture(text="文件AB", parts=None):
    parts = parts if parts is not None else [text]
    runs, position = [], 0
    for ordinal, part in enumerate(parts):
        length = utf16_length(part)
        runs.append({"ordinal": ordinal, "source": RUN_SOURCE, "submitted_to_d2d": True,
                     "from_inline_object": False, "inline_draw_ordinal": None, "sideways": False,
                     "description": {"text": part, "text_position_utf16": position, "text_length_utf16": length,
                                     "locale": "zh-cn", "cluster_map": list(range(length))},
                     "glyph_indices": list(range(10, 10 + length)), "glyph_advances": [12] * length,
                     "face": face("Measured Face " + str(ordinal), "MeasuredFace" + str(ordinal))})
        position += length
    draw = {"layout_revision": 7, "surface_revision": 1, "draw_ordinal": 4,
            "layout_com_identity": "fixture-actual-layout", "draw_hresult": 0,
            "surface_end_draw_hresult": 0, "surface_end_draw_succeeded": True,
            "line_metrics": [{"length_utf16": utf16_length(text), "is_trimmed": False, "height": 20.8}],
            "trimming": {"requested_character_ellipsis": True, "granularity": 1},
            "glyph_runs": runs, "inline_object_draws": [], "limitations": []}
    readback = {"source": READBACK_SOURCE, "status": "surface-pixels-read", "layout_revision": 7,
                "surface_revision": 1, "draw_ordinal": 4, "case_id": "synthetic-case", "capture_label_index": 0,
                "is_current_draw_at_export": True, "surface_submission_succeeded": True, "surface_end_draw_hresult": 0,
                "raw_sidecar": "synthetic-case.native-label-0.bgra", "target_process_identity": "fixture-target"}
    receipt = {"source": LABEL_SOURCE, "text": text, "requested_family_list": "Never Use This Declared Family",
               "current_layout_revision": 7, "current_surface_revision": 1, "current_draw_ordinal": 4,
               "current_submission": {"source": STATE_SOURCE, "is_loaded": True, "queued": False,
                                      "rendering": False, "surface_binding_same_com_identity": True},
               "last_failure": None, "draw": draw, "surface_readback": readback,
               "coverage_complete": False, "presentation_frame": None,
               "capture_binding": {"source": BINDING_SOURCE, "same_object_reference": True,
                                   "capture_label_index": 0, "case_id": "synthetic-case"}}
    node = {"id": "label", "type": "NativeLabel", "text": text, "bounds": None,
            "native_label_evidence": receipt}
    image = {"id": "image", "type": "Image", "parent": "label",
             "native_label_surface_evidence": {"source": IMAGE_SOURCE, "owner_id": "label", "same_image_object": True,
                 "surface_binding_same_com_identity": True, "source_type": "Microsoft.UI.Xaml.Media.Imaging.SurfaceImageSource",
                 "layout_revision": 7, "surface_revision": 1, "draw_ordinal": 4}}
    observed = {"text": text, "layout_revision": 7, "surface_revision": 1, "draw_ordinal": 4,
                "surface_binding_same_com_identity": True, "queued": False, "rendering": False, "bounds": None}
    frame = {"source": FRAME_SOURCE, "case_id": "synthetic-case", "presentation_identity_proven": False,
             "surface_readback_errors": [], "baseline": [{"capture_label_index": 0, "state": deepcopy(observed)}],
             "production_draws": [{"capture_label_index": 0, "production_receipt": deepcopy(receipt)}],
             "surface_readbacks": [dict(deepcopy(readback), directory="synthetic-case-directory")],
             "checkpoints": [{"stage": stage, "same_object_references": True, "same_observed_state": True,
                              "failure": None, "state": [{"capture_label_index": 0, "state": deepcopy(observed)}]}
                             for stage in CHECKPOINTS]}
    return node, image, frame


def update_production(node, frame):
    """Make a changed synthetic draw remain the same frame's actual fixture draw."""
    frame["production_draws"][0]["production_receipt"] = deepcopy(node["native_label_evidence"])


def trimmed_fixture():
    """Synthetic actual-callback shape; not an observation from a CI frame."""
    node, image, frame = fixture("ABCDEFG", ["ABC"])
    draw = node["native_label_evidence"]["draw"]
    draw["line_metrics"][0]["is_trimmed"] = True
    draw["trimming"] = {"source": TRIMMING_SOURCE, "requested_character_ellipsis": True,
                        "granularity": 1, "delimiter": 0, "delimiter_count": 0,
                        "configured_sign_com_identity": "synthetic-ellipsis", "layout_sign_com_identity": "synthetic-ellipsis",
                        "same_sign_com_identity": True}
    draw["inline_object_draws"] = [{"source": INLINE_SOURCE, "ordinal": 0, "parent_inline_draw_ordinal": None,
                                   "inline_com_identity": "synthetic-ellipsis", "is_configured_trimming_sign": True,
                                   "sideways": False, "right_to_left": False, "draw_succeeded": True, "draw_hresult": 0,
                                   "first_glyph_run_ordinal": 1, "glyph_run_count": 1}]
    sign = deepcopy(fixture("\u2026")[0]["native_label_evidence"]["draw"]["glyph_runs"][0])
    sign.update(ordinal=1, from_inline_object=True, inline_draw_ordinal=0, face=face("Actual Sign Face", "ActualSignFace"))
    draw["glyph_runs"].append(sign)
    for run in draw["glyph_runs"]:
        run["bidi_level"] = 0
    update_production(node, frame)
    return node, image, frame


class NativeLabelFontTests(unittest.TestCase):
    def assert_unknown(self, node, image, frame, reason=None):
        result, issues = native_label_fonts(node, image, frame)
        self.assertEqual(result["status"], "unmeasured")
        self.assertIsNone(result["fonts"])
        self.assertTrue(issues)
        self.assertFalse(result["final_png_attribution_proven"])
        self.assertNotIn("coverage_complete", result)
        if reason:
            self.assertIn(reason, issues[0]["reason"])
        return result

    def test_actual_complete_source_faces_do_not_claim_presentation_or_geometry(self):
        node, image, frame = fixture(parts=["文件", "AB"])
        before = deepcopy((node, image, frame))
        result, issues = native_label_fonts(node, image, frame)
        self.assertEqual(issues, [])
        self.assertEqual(result["status"], "measured-current-submission")
        self.assertEqual([row["family_name"] for row in result["fonts"]], ["Measured Face 0", "Measured Face 1"])
        self.assertEqual([row["glyph_count"] for row in result["fonts"]], [2, 2])
        self.assertTrue(result["source_span_complete"])
        self.assertTrue(result["original_source_span_complete"])
        self.assertTrue(result["submitted_glyph_runs_complete"])
        self.assertFalse(result["final_png_attribution_proven"])
        self.assertNotIn("coverage_complete", result)
        self.assertEqual((node, image, frame), before)
        self.assertIsNone(node["bounds"])  # font identity does not substitute geometry.
        self.assertFalse(node["native_label_evidence"]["coverage_complete"])

    def test_four_menu_and_four_untrimmed_preview_shapes_qualify_but_trimmed_without_sign_binding_does_not(self):
        examples = ["文件", "编辑", "视图", "帮助", "在做：Read layout.png", "在做：Read README.md", "验收与回归检查", "产品建议",
                    "设计师：三个窗口尺寸都会检查，长标题会换行或显示省略提示。", "秘书处负责人：目前有两项：确认权限设置，以及本轮集成负责人。任务和相关协议都在右侧概况中。"]
        accepted = 0
        for index, text in enumerate(examples):
            node, image, frame = fixture(text)
            if index >= 8:
                draw = node["native_label_evidence"]["draw"]
                draw["line_metrics"][0]["is_trimmed"] = True
                run = draw["glyph_runs"][0]
                run["description"].update(text=text[:11], text_length_utf16=11, cluster_map=list(range(11)))
                run["glyph_indices"] = run["glyph_indices"][:11]
                update_production(node, frame)
            result, issues = native_label_fonts(node, image, frame)
            accepted += result["fonts"] is not None
            self.assertEqual(bool(issues), index >= 8)
        self.assertEqual(accepted, 8)

    def test_pending_or_stale_submission_is_not_replaced_by_requested_family(self):
        for mutation in ("queued", "rendering", "surface", "revision", "end-draw", "source", "failure"):
            node, image, frame = fixture(); receipt = node["native_label_evidence"]
            if mutation in ("queued", "rendering"):
                receipt["current_submission"][mutation] = True
            elif mutation == "surface": receipt["current_submission"]["surface_binding_same_com_identity"] = False
            elif mutation == "revision": receipt["current_draw_ordinal"] += 1
            elif mutation == "end-draw": receipt["draw"]["surface_end_draw_hresult"] = -1
            elif mutation == "source": receipt["text"] = "different text"
            else: receipt["last_failure"] = "actual API failed"
            with self.subTest(mutation=mutation): self.assert_unknown(node, image, frame)

    def test_actual_image_owner_and_com_binding_are_required(self):
        for mutation in ("missing", "owner_id", "same_image_object", "surface_binding_same_com_identity", "draw_ordinal"):
            node, image, frame = fixture()
            if mutation == "missing": image = None
            else: image["native_label_surface_evidence"][mutation] = "other" if mutation == "owner_id" else False
            with self.subTest(mutation=mutation): self.assert_unknown(node, image, frame, "Image/SIS")

    def test_frame_baseline_draw_readback_and_unique_capture_index_are_required(self):
        for mutation in ("case", "baseline", "draw", "readback", "duplicate", "readback-error"):
            node, image, frame = fixture()
            if mutation == "case": frame["case_id"] = "different"
            elif mutation == "baseline": frame["baseline"][0]["state"]["draw_ordinal"] += 1
            elif mutation == "draw": frame["production_draws"][0]["production_receipt"]["draw"]["layout_revision"] += 1
            elif mutation == "readback": frame["surface_readbacks"][0]["is_current_draw_at_export"] = False
            elif mutation == "duplicate": frame["production_draws"].append(deepcopy(frame["production_draws"][0]))
            else: frame["surface_readback_errors"] = ["readback failed"]
            with self.subTest(mutation=mutation): self.assert_unknown(node, image, frame)

    def test_every_supplied_checkpoint_and_all_four_pre_export_checkpoints_are_required(self):
        for mutation in ("missing", "changed", "extra-failed", "reordered", "missing-stage", "boolean-revision"):
            node, image, frame = fixture()
            if mutation == "missing": frame["checkpoints"].pop()
            elif mutation == "changed": frame["checkpoints"][1]["state"][0]["state"]["text"] = "changed"
            elif mutation == "extra-failed":
                extra = deepcopy(frame["checkpoints"][-1]); extra.update(stage="after_element_extraction", same_observed_state=False)
                frame["checkpoints"].append(extra)
            elif mutation == "reordered": frame["checkpoints"].reverse()
            elif mutation == "missing-stage": frame["checkpoints"].append({"same_object_references": True, "same_observed_state": True, "state": deepcopy(frame["baseline"])})
            else: frame["checkpoints"][0]["state"][0]["state"]["surface_revision"] = True
            with self.subTest(mutation=mutation): self.assert_unknown(node, image, frame)
        node, image, frame = fixture()
        final = deepcopy(frame["checkpoints"][-1]); final["stage"] = "after_element_extraction"
        frame["checkpoints"].append(final)
        self.assertEqual(native_label_fonts(node, image, frame)[1], [])

    def test_exact_utf16_ranges_cannot_be_replaced_by_matching_names_or_partial_text(self):
        for mutation in ("text", "position", "length", "gap", "overlap"):
            node, image, frame = fixture(parts=["文件", "AB"])
            runs = node["native_label_evidence"]["draw"]["glyph_runs"]
            if mutation == "text": runs[0]["description"]["text"] = "XY"
            elif mutation == "position": runs[0]["description"]["text_position_utf16"] = True
            elif mutation == "length": runs[0]["description"]["text_length_utf16"] = 99
            elif mutation == "gap": runs.pop()
            else:
                runs[1] = deepcopy(runs[0]); runs[1]["ordinal"] = 1
            update_production(node, frame)
            with self.subTest(mutation=mutation): self.assert_unknown(node, image, frame)

    def test_cluster_maps_require_actual_valid_utf16_to_glyph_coverage(self):
        for clusters in (None, [], [0], [0, 1, 2, True], [0, 1, 2, 99], [1, 1, 2, 3]):
            node, image, frame = fixture()
            node["native_label_evidence"]["draw"]["glyph_runs"][0]["description"]["cluster_map"] = clusters
            update_production(node, frame)
            with self.subTest(clusters=clusters): self.assert_unknown(node, image, frame, "cluster")

    def test_surrogates_ligatures_and_rtl_do_not_require_one_glyph_per_character(self):
        for text, glyphs, clusters in (("😀A", [17, 22], [0, 0, 1]), ("ffi", [23], [0, 0, 0]), ("אב", [20, 21], [1, 0])):
            node, image, frame = fixture(text)
            run = node["native_label_evidence"]["draw"]["glyph_runs"][0]
            run["glyph_indices"] = glyphs; run["description"]["cluster_map"] = clusters
            update_production(node, frame)
            result, issues = native_label_fonts(node, image, frame)
            self.assertEqual(issues, [])
            self.assertEqual(result["source_utf16_length"], utf16_length(text))
            self.assertEqual(result["fonts"][0]["glyph_count"], len(glyphs))

    def test_inline_ellipsis_offset_zero_never_fills_original_source_coverage(self):
        for mutation in ("inline-row", "inline-run"):
            node, image, frame = fixture("AB")
            draw = node["native_label_evidence"]["draw"]
            if mutation == "inline-row": draw["inline_object_draws"] = [{"ordinal": 0, "is_configured_trimming_sign": True}]
            else: draw["glyph_runs"][0].update(from_inline_object=True, inline_draw_ordinal=0)
            update_production(node, frame)
            with self.subTest(mutation=mutation): self.assert_unknown(node, image, frame)

    def test_bound_trimmed_fonts_include_real_sign_face_without_filling_hidden_source(self):
        node, image, frame = trimmed_fixture()
        before = deepcopy((node, image, frame))
        result, issues = native_label_fonts(node, image, frame)
        self.assertEqual(issues, [])
        self.assertEqual(result["status"], "measured-current-submission")
        self.assertEqual([font["postscript_name"] for font in result["fonts"]], ["MeasuredFace0", "ActualSignFace"])
        self.assertTrue(result["submitted_glyph_runs_complete"])
        self.assertIs(result["source_span_complete"], False)
        self.assertIs(result["original_source_span_complete"], False)
        self.assertEqual(result["submitted_original_source_range_utf16"], {"start": 0, "length": 3})
        self.assertEqual(result["unsubmitted_original_source_range_utf16"], {"start": 3, "length": 4})
        self.assertIsNone(result["fonts"][-1]["source_range_utf16"])
        self.assertEqual(result["fonts"][-1]["inline_source_range_utf16"], {"start": 0, "length": 1})
        self.assertEqual(result["fonts"][-1]["inline_source_text"], "\u2026")
        self.assertFalse(result["final_png_attribution_proven"])
        self.assertNotIn("text_bounds", result)
        self.assertEqual((node, image, frame), before)

    def test_trimmed_font_reading_requires_every_sign_identity_and_nested_interval_observation(self):
        for section in ("trimming", "inline_object_draws"):
            node, _, _ = trimmed_fixture()
            row = node["native_label_evidence"]["draw"][section]
            row = row[0] if isinstance(row, list) else row
            for key in tuple(row):
                with self.subTest(section=section, missing=key):
                    node, image, frame = trimmed_fixture()
                    changed = node["native_label_evidence"]["draw"][section]
                    changed = changed[0] if isinstance(changed, list) else changed
                    changed.pop(key)
                    update_production(node, frame)
                    self.assert_unknown(node, image, frame)

    def test_changed_or_unobserved_inline_draws_never_hide_missing_font_callbacks(self):
        for mutation in ("foreign-sign", "nested-parent", "extra-inline", "missing-sign-run", "extra-run",
                         "wrong-count", "wrong-start", "failed-draw", "metadata-failure", "wrong-sign-text",
                         "missing-sign-face", "false-inline-owner", "rtl", "unknown-trimming"):
            with self.subTest(mutation=mutation):
                node, image, frame = trimmed_fixture()
                draw = node["native_label_evidence"]["draw"]
                inline, sign = draw["inline_object_draws"][0], draw["glyph_runs"][-1]
                if mutation == "foreign-sign": inline["inline_com_identity"] = "different-object"
                elif mutation == "nested-parent": inline["parent_inline_draw_ordinal"] = 0
                elif mutation == "extra-inline": draw["inline_object_draws"].append(deepcopy(inline))
                elif mutation == "missing-sign-run": draw["glyph_runs"].pop()
                elif mutation == "extra-run": draw["glyph_runs"].append(deepcopy(sign))
                elif mutation == "wrong-count": inline["glyph_run_count"] = 2
                elif mutation == "wrong-start": inline["first_glyph_run_ordinal"] = True
                elif mutation == "failed-draw": inline["draw_hresult"] = -1
                elif mutation == "metadata-failure": inline["metadata_failure"] = "actual COM query failed"
                elif mutation == "wrong-sign-text": sign["description"]["text"] = "A"
                elif mutation == "missing-sign-face": sign["face"] = None
                elif mutation == "false-inline-owner": sign["inline_draw_ordinal"] = True
                elif mutation == "rtl": draw["glyph_runs"][0]["bidi_level"] = 1
                else: draw["line_metrics"][0]["is_trimmed"] = None
                update_production(node, frame)
                self.assert_unknown(node, image, frame)

    def test_trimmed_source_must_be_one_actual_prefix_with_an_omitted_suffix(self):
        for mutation in ("wrong-text", "gap", "whole-source", "wrong-ordinal", "unknown-clusters"):
            with self.subTest(mutation=mutation):
                node, image, frame = trimmed_fixture()
                draw = node["native_label_evidence"]["draw"]
                first = draw["glyph_runs"][0]
                if mutation == "wrong-text": first["description"]["text"] = "XYZ"
                elif mutation == "gap": first["description"].update(text="BCD", text_position_utf16=1)
                elif mutation == "whole-source":
                    first["description"].update(text="ABCDEFG", text_length_utf16=7, cluster_map=list(range(7)))
                    first["glyph_indices"] = list(range(10, 17))
                elif mutation == "wrong-ordinal": first["ordinal"] = 1
                else: first["description"]["cluster_map"] = None
                update_production(node, frame)
                self.assert_unknown(node, image, frame)

    def test_recorded_trimmed_67ed20d_draws_measure_fonts_but_keep_original_span_and_png_unknown(self):
        recorded = json.loads((Path(__file__).parent / "fixtures" / "native-label-trimmed-67ed20d.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded["provenance"]["commit"], "67ed20d")
        self.assertEqual([case["node"]["id"] for case in recorded["cases"]], ["xaml-277", "xaml-300"])
        for case in recorded["cases"]:
            with self.subTest(node=case["node"]["id"]):
                before = deepcopy(case)
                result, issues = native_label_fonts(case["node"], case["image"], case["frame"])
                self.assertEqual(issues, [])
                self.assertEqual([font["postscript_name"] for font in result["fonts"]],
                                 ["MicrosoftYaHeiUI"] * 3 + ["Segoe-UI-Variable-Text"])
                self.assertTrue(result["submitted_glyph_runs_complete"])
                self.assertIs(result["source_span_complete"], False)
                self.assertIs(result["original_source_span_complete"], False)
                self.assertEqual(result["submitted_original_source_range_utf16"], {"start": 0, "length": 11})
                self.assertGreater(result["unsubmitted_original_source_range_utf16"]["length"], 0)
                self.assertIsNone(result["fonts"][3]["source_range_utf16"])
                self.assertEqual(result["fonts"][3]["inline_source_text"], "\u2026")
                self.assertFalse(result["final_png_attribution_proven"])
                self.assertEqual(case, before)

    def test_postscript_uses_only_unique_recorded_en_us_and_preserves_all_names(self):
        node, image, frame = fixture()
        result, issues = native_label_fonts(node, image, frame)
        self.assertEqual(issues, [])
        self.assertEqual(result["fonts"][0]["postscript_name"], "MeasuredFace0")
        self.assertEqual(len(result["run_font_evidence"][0]["actual_face"]["postscript_names"]), 2)
        for names in (None, [{"locale": "zh-cn", "value": "NotAnEnglishAlias"}],
                      [{"locale": "en-us", "value": "First"}, {"locale": "en-US", "value": "Second"}]):
            node, image, frame = fixture()
            node["native_label_evidence"]["draw"]["glyph_runs"][0]["face"]["postscript_names"] = names
            update_production(node, frame)
            result, issues = native_label_fonts(node, image, frame)
            self.assertEqual(issues, [])
            self.assertIsNone(result["fonts"][0]["postscript_name"])
            self.assertEqual(result["run_font_evidence"][0]["actual_face"]["postscript_names"], names)

    def test_missing_or_malformed_actual_face_is_not_repaired_from_declared_family(self):
        for key, value in (("source", "UIA.TextPattern.FontNameAttribute"), ("family_names", None),
                           ("face_index", True), ("measurement_failure", "actual GetFamilyNames failed"),
                           ("axes", [{"tag": "wght", "value": float("nan")}])):
            node, image, frame = fixture()
            node["native_label_evidence"]["draw"]["glyph_runs"][0]["face"][key] = value
            update_production(node, frame)
            with self.subTest(key=key): self.assert_unknown(node, image, frame)


if __name__ == "__main__":
    unittest.main()
