"""Synthetic measured-shape contracts; never launch a renderer or application."""
from copy import deepcopy
import unittest

from native_label_geometry import native_label_geometry


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


class NativeLabelGeometryTests(unittest.TestCase):
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
