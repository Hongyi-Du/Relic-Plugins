"""Synthetic measured-shape contracts; never launch a renderer or application."""
from copy import deepcopy
import unittest

from native_label_geometry import empty_native_glyph_outline, native_label_geometry


def box(x, y, width, height):
    return dict(x=x, y=y, width=width, height=height)


def fixture():
    context = {"source": "Actual ID2D1DeviceContext getters at the production draw callback",
               "world_transform": {"m11": 1, "m12": 0, "m21": 0, "m22": 1, "dx": 5, "dy": 7},
               "dpi": {"x": 96, "y": 96}, "unit_mode": 0}
    face = {"source": "DWRITE_GLYPH_RUN.fontFace passed to the actual D2D DrawGlyphRun",
            "metrics_design_units": {"units_per_em": 1000, "ascent": 800, "descent": 200}}
    runs = []
    for ordinal, text, glyphs, advances, x, ink in ((0, "AB", [12, 13], [10, 10], 0, [5, 15, 24, 23]),
                                                   (1, "…", [99], [8], 20, [26, 19, 32, 23])):
        runs.append({"source": "IDWriteTextLayout.Draw -> IDWriteTextRenderer.DrawGlyphRun -> ID2D1RenderTarget.DrawGlyphRun",
                     "ordinal": ordinal, "submitted_to_d2d": True, "sideways": False, "bidi_level": 0,
                     "baseline_x": x, "baseline_y": 15, "em_size": 10, "glyph_indices": glyphs, "glyph_advances": advances,
                     "face": deepcopy(face), "actual_d2d_context": deepcopy(context),
                     "from_inline_object": ordinal == 1, "inline_draw_ordinal": 0 if ordinal == 1 else None,
                     "ink_bounds_world_dip": dict(zip(("left", "top", "right", "bottom"), ink)),
                     "description": {"text": text, "text_position_utf16": 0, "text_length_utf16": len(text),
                                     "cluster_map": list(range(len(text)))}})
    draw = {"layout_revision": 1, "surface_revision": 2, "draw_ordinal": 3,
            "draw_hresult": 0, "surface_end_draw_hresult": 0, "surface_end_draw_succeeded": True,
            "surface_pixels": {"width": 40, "height": 20}, "surface_begin_draw_offset_pixels": {"x": 5, "y": 7},
            "image_actual_dip": {"width": 40, "height": 20, "stretch": "Fill"},
            "line_metrics": [{"length_utf16": 4, "height": 20, "baseline": 15, "is_trimmed": True}],
            "actual_text_format": {"word_wrapping": 1}, "trimming": {"granularity": 1, "same_sign_com_identity": True},
            "glyph_runs": runs,
            "hit_test_range_metrics": [dict(text_position_utf16=0, text_length_utf16=2, left=0, top=0, width=20, height=20, is_text=True, is_trimmed=False),
                                       dict(text_position_utf16=2, text_length_utf16=2, left=20, top=15, width=8, height=0, is_text=False, is_trimmed=True)],
            "inline_object_draws": [{"ordinal": 0, "is_configured_trimming_sign": True, "inline_com_identity": "actual-fixture-sign",
                                     "origin_x": 20, "origin_y": 15, "draw_succeeded": True,
                                     "inline_metrics": {"width": 8, "height": 0, "baseline": 0}, "actual_d2d_context": deepcopy(context)}]}
    node = {"id": "label", "type": "NativeLabel", "bounds": box(100, 50, 40, 20), "visible_bounds": box(100, 50, 40, 20),
            "native_label_evidence": {"source": "NativeLabel production SurfaceImageSource / DirectWrite renderer", "text": "ABCD",
                                      "current_layout_revision": 1, "current_surface_revision": 2, "current_draw_ordinal": 3,
                                      "current_submission": {"is_loaded": True, "queued": False, "rendering": False, "surface_binding_same_com_identity": True},
                                      "last_failure": None, "draw": draw}}
    image = {"id": "surface", "parent": "label", "type": "Image", "local_bounds": box(0, 0, 40, 20),
             "transform": {"m11": 1, "m12": 0, "m21": 0, "m22": 1, "offset_x": 100, "offset_y": 50},
             "axis_aligned_transform": True, "ancestor_clip": box(100, 50, 40, 20),
             "native_label_surface_evidence": {"source": "actual NativeLabel production Image object identity and SurfaceImageSource COM binding",
                 "owner_id": "label", "same_image_object": True, "surface_binding_same_com_identity": True,
                 "source_type": "Microsoft.UI.Xaml.Media.Imaging.SurfaceImageSource", "layout_revision": 1, "surface_revision": 2, "draw_ordinal": 3}}
    return node, image


def empty_outline_fixture():
    """Synthetic outline proof plus the recorded db91b1b space run raw values.

    No actual GetGlyphRunOutline result was available in db91b1b. These success
    fields test the new contract only and are not evidence that CI measured it.
    """
    node, image = fixture()
    node["native_label_evidence"]["text"] = " ABC"
    run = node["native_label_evidence"]["draw"]["glyph_runs"][0]
    run.update(description={"text": " ", "text_position_utf16": 0, "text_length_utf16": 1, "cluster_map": [0]},
               glyph_indices=[2], glyph_advances=[3.2871094], glyph_offsets=[{"advance": 0, "ascender": 0}],
               callback_run_pointer="1100", font_face_process_pointer="2200", ink_bounds_world_dip=None)
    run["face"]["color_font"] = False
    binding = {key: deepcopy(run[key]) for key in ("font_face_process_pointer", "em_size", "glyph_indices", "glyph_advances", "glyph_offsets", "sideways", "bidi_level")}
    binding.update(glyph_count=1, right_to_left=False)
    run["ink_bounds_evidence"] = {
        "source": "Actual GetGlyphRunWorldBounds result and same-callback glyph outline observation",
        "bounds_hresult": 0, "bounds_hresult_hex": "0x00000000", "classification": "outline-empty", "failure": None,
        "raw_bounds_classification": "nonfinite",
        "raw_bounds": {key: {"value": None if key in ("left", "top") else 3.4028235e38,
                             "raw_value": "Infinity" if key in ("left", "top") else "3.4028235E+38",
                             "ieee754_format": "binary32", "ieee754_bits": "7F800000" if key in ("left", "top") else "7F7FFFFF"}
                       for key in ("left", "top", "right", "bottom")},
        "outline": {"source": "Actual same-run IDWriteFontFace.GetGlyphRunOutline into ID2D1PathGeometry",
                    "glyph_run_ordinal": 0, "callback_run_pointer": "1100", "color_font": False, "binding": binding,
                    "failure": None, "figure_count": 0, "segment_count": 0,
                    "create_path_hresult": 0, "open_hresult": 0, "outline_hresult": 0, "close_hresult": 0,
                    "figure_count_hresult": 0, "segment_count_hresult": 0}}
    return node, image, run


class NativeLabelGeometryTests(unittest.TestCase):
    def test_proven_empty_outline_has_no_fake_rect_and_keeps_nonzero_advance(self):
        node, image, run = empty_outline_fixture()
        before = deepcopy(node)
        data, issues = native_label_geometry(node, image)
        self.assertTrue(empty_native_glyph_outline(run))
        self.assertEqual(issues, [])
        self.assertTrue(data["glyph_ink"][0]["outline_empty"])
        self.assertIsNone(data["glyph_ink"][0]["world_bounds"])
        self.assertIsNone(data["glyph_ink"][0]["window"])
        self.assertEqual(data["font_metric_advance"][0]["local_bounds"]["width"], 3.2871094)
        self.assertIsNone(data["final_pixel_contribution"])
        self.assertEqual(node, before)

    def test_old_nonfinite_receipt_without_outline_proof_still_fails(self):
        node, image, run = empty_outline_fixture()
        del run["ink_bounds_evidence"]
        data, issues = native_label_geometry(node, image)
        self.assertFalse(data["glyph_ink"][0]["outline_empty"])
        self.assertTrue(any(row["property"].endswith("glyph_ink") for row in issues))

    def test_each_failed_or_missing_actual_outline_result_cannot_prove_empty(self):
        for key in ("create_path_hresult", "open_hresult", "outline_hresult", "close_hresult", "figure_count_hresult", "segment_count_hresult"):
            for value in (None, -1, True):
                with self.subTest(key=key, value=value):
                    _, _, run = empty_outline_fixture()
                    run["ink_bounds_evidence"]["outline"][key] = value
                    self.assertFalse(empty_native_glyph_outline(run))

    def test_nonempty_or_unmeasured_outline_keeps_coverage_failure(self):
        for change in ({"figure_count": 1}, {"segment_count": 1}, {"figure_count": None}, {"segment_count": False},
                       {"failure": "actual failure"}, {"cleanup_failure": "actual cleanup failure"}, {"color_font": None}, {"color_font": True}):
            with self.subTest(change=change):
                node, image, run = empty_outline_fixture()
                run["ink_bounds_evidence"]["outline"].update(change)
                _, issues = native_label_geometry(node, image)
                self.assertTrue(any(row["property"].endswith("glyph_ink") for row in issues))

    def test_cross_run_face_or_glyph_binding_cannot_supply_empty_outline(self):
        for change in ({"font_face_process_pointer": "3300"}, {"glyph_indices": [3]}, {"glyph_advances": [0]},
                       {"glyph_offsets": None}, {"em_size": 11}, {"glyph_count": 2}, {"right_to_left": True}):
            with self.subTest(change=change):
                _, _, run = empty_outline_fixture()
                run["ink_bounds_evidence"]["outline"]["binding"].update(change)
                self.assertFalse(empty_native_glyph_outline(run))
        for key, value in (("glyph_run_ordinal", 1), ("callback_run_pointer", "1200")):
            _, _, run = empty_outline_fixture()
            run["ink_bounds_evidence"]["outline"][key] = value
            self.assertFalse(empty_native_glyph_outline(run))

    def test_raw_bits_must_match_classification_and_preserved_finite_value(self):
        for change in ({"ieee754_bits": "broken"}, {"ieee754_format": "binary64"}, {"value": 0}, {"ieee754_bits": "00000000"}):
            with self.subTest(change=change):
                _, _, run = empty_outline_fixture()
                run["ink_bounds_evidence"]["raw_bounds"]["right"].update(change)
                self.assertFalse(empty_native_glyph_outline(run))
        _, _, run = empty_outline_fixture()
        run["ink_bounds_evidence"]["raw_bounds_classification"] = "reversed"
        self.assertFalse(empty_native_glyph_outline(run))

    def test_success_flag_does_not_override_failed_original_bounds_api(self):
        _, _, run = empty_outline_fixture()
        run["ink_bounds_evidence"]["bounds_hresult"] = -1
        self.assertFalse(empty_native_glyph_outline(run))

    def test_empty_outline_does_not_erase_independent_transform_or_font_gaps(self):
        node, image, run = empty_outline_fixture()
        run["description"]["cluster_map"] = None
        image["native_label_surface_evidence"]["owner_id"] = "other-label"
        data, issues = native_label_geometry(node, image)
        self.assertTrue(data["glyph_ink"][0]["outline_empty"])
        self.assertTrue(any(row["property"].endswith("font_metric_advance") for row in issues))
        self.assertTrue(any(row["property"].endswith("image_placement") for row in issues))
        self.assertTrue(any(row["property"].endswith("run_transform") for row in issues))

    def test_distinct_measured_quantities_and_zero_height_ellipsis_are_retained(self):
        node, image = fixture()
        before = deepcopy(node), deepcopy(image)
        data, issues = native_label_geometry(node, image)
        self.assertEqual(issues, [])
        self.assertEqual(data["element_layout"]["bounds"], box(100, 50, 40, 20))
        self.assertEqual(data["advance_selection"][0]["window"]["bounds"], box(100, 50, 20, 20))
        self.assertEqual(data["font_metric_advance"][0]["window"]["bounds"], box(100, 57, 20, 10))
        self.assertEqual(data["glyph_ink"][0]["window"]["bounds"], box(100, 58, 19, 8))
        self.assertEqual(data["ellipsis_layout"][0]["window"]["bounds"], box(120, 65, 8, 0))
        self.assertEqual(data["ellipsis_ink"][0]["bounds"], box(121, 62, 6, 4))
        self.assertTrue(data["ellipsis_ink"][0]["complete"])
        self.assertIsNone(data["final_pixel_contribution"])
        self.assertEqual((node, image), before)

    def test_actual_dpi_atlas_offset_and_image_scale_are_not_assumed_identical(self):
        node, image = fixture()
        draw = node["native_label_evidence"]["draw"]
        draw["surface_pixels"] = {"width": 80, "height": 40}
        draw["surface_begin_draw_offset_pixels"] = {"x": 10, "y": 14}
        for row in draw["glyph_runs"] + draw["inline_object_draws"]:
            row["actual_d2d_context"]["dpi"] = {"x": 192, "y": 192}
        data, issues = native_label_geometry(node, image)
        self.assertEqual(issues, [])
        self.assertEqual(data["font_metric_advance"][0]["window"]["bounds"], box(100, 57, 20, 10))
        self.assertEqual(data["glyph_ink"][0]["window"]["inverse_world_transform"], [1, 0, 0, 1, -5, -7])

    def test_singular_transform_keeps_element_local_selection_and_world_ink(self):
        node, image = fixture()
        for row in node["native_label_evidence"]["draw"]["glyph_runs"] + node["native_label_evidence"]["draw"]["inline_object_draws"]:
            row["actual_d2d_context"]["world_transform"]["m11"] = 0
        data, issues = native_label_geometry(node, image)
        self.assertEqual(data["element_layout"]["bounds"], node["bounds"])
        self.assertEqual(data["advance_selection"][1]["local_bounds"], box(20, 15, 8, 0))
        self.assertIsNone(data["advance_selection"][1]["window"])
        self.assertEqual(data["glyph_ink"][0]["world_bounds"], box(5, 15, 19, 8))
        self.assertTrue(any(row["property"].endswith("run_transform") for row in issues))

    def test_missing_cluster_or_wrong_source_text_does_not_erase_measured_ink(self):
        for change in ({"cluster_map": None}, {"text": "XY"}):
            node, image = fixture()
            node["native_label_evidence"]["draw"]["glyph_runs"][0]["description"].update(change)
            data, issues = native_label_geometry(node, image)
            self.assertEqual(len(data["font_metric_advance"]), 1)
            self.assertEqual(len(data["glyph_ink"]), 2)
            self.assertIsNotNone(data["glyph_ink"][0]["window"])
            self.assertTrue(any(row["property"].endswith("font_metric_advance") for row in issues))

    def test_wrong_image_binding_cannot_supply_window_geometry(self):
        node, image = fixture()
        image["native_label_surface_evidence"]["owner_id"] = "unrelated"
        data, issues = native_label_geometry(node, image)
        self.assertIsNotNone(data["font_metric_advance"][0]["local_bounds"])
        self.assertIsNone(data["font_metric_advance"][0]["window"])
        self.assertEqual(data["element_layout"]["bounds"], node["bounds"])
        self.assertTrue(any(row["property"].endswith("image_placement") for row in issues))

    def test_rtl_advance_uses_actual_bidi_level_and_measured_baseline(self):
        node, image = fixture()
        run = node["native_label_evidence"]["draw"]["glyph_runs"][0]
        run["bidi_level"], run["baseline_x"] = 1, 20
        data, _ = native_label_geometry(node, image)
        self.assertEqual(data["font_metric_advance"][0]["local_bounds"], box(0, 7, 20, 10))


if __name__ == "__main__":
    unittest.main()
