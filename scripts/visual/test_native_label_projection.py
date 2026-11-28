"""Synthetic production-receipt regressions; CI only, no application launched."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from windows_elements import native_label_submission, project
from test_windows_elements import SCENE, VIEWPORT, measured, uia_node, xaml_node


def submitted_label():
    fmt = {"source": "IDWriteTextFormat getters on the same production IDWriteTextLayout passed to Draw",
           "font_size": 12, "font_weight": 400, "word_wrapping": 1}
    rgba = [84, 82, 77, 17.85]
    draw = {"layout_revision": 2, "surface_revision": 3, "draw_ordinal": 4,
            "layout_com_identity": "fixture-layout", "draw_hresult": 0, "surface_end_draw_hresult": 0,
            "surface_end_draw_succeeded": True, "actual_text_format": fmt,
            "brush_input_srgb_unpremultiplied_0_255": rgba,
            "glyph_runs": [{"ordinal": 0, "submitted_to_d2d": True,
                            "face": {"family_names": [{"locale": "en-US", "value": "Actual Fixture Face"}]}}]}
    receipt = {"source": "NativeLabel production SurfaceImageSource / DirectWrite renderer", "text": "完整预览。",
               "requested_family_list": "Unverified Declared Font", "current_layout_revision": 2,
               "current_surface_revision": 3, "current_draw_ordinal": 4, "last_failure": None,
               "current_submission": {"source": "Actual NativeLabel state at receipt capture", "is_loaded": True,
                                      "queued": False, "rendering": False, "surface_binding_same_com_identity": True},
               "draw": draw,
               "capture_binding": {"source": "Actual NativeLabel object ReferenceEquals against the capture observer label array",
                                   "capture_label_index": 0, "same_object_reference": True, "case_id": SCENE}}
    style = {"font_size": 12, "font_weight": 400, "foreground": deepcopy(rgba),
             "background": [0, 0, 0, 0], "border_color": [0, 0, 0, 0], "border_width": 0, "corner_radius": 0,
             "native_label_style_evidence": {
                 "source": "Current bound NativeLabel production draw, actual TextFormat getters and D2D brush inputs",
                 "current_submission_verified": True, "layout_revision": 2, "surface_revision": 3, "draw_ordinal": 4,
                 "actual_text_format": deepcopy(fmt), "brush_input_srgb_unpremultiplied_0_255": deepcopy(rgba)}}
    node = xaml_node("label", "NativeLabel", text=receipt["text"], style=style, native_label_evidence=receipt,
                     paint_kind="glyphs", render_type_evidence={"is_panel": True, "is_control": False, "control_template_present": None})
    frame = {"source": "Actual NativeLabel object references observed around desktop readback", "case_id": SCENE,
             "baseline": [{"capture_label_index": 0, "state": {"layout_revision": 2, "surface_revision": 3,
                            "draw_ordinal": 4, "surface_binding_same_com_identity": True}}],
             "production_draws": [{"capture_label_index": 0, "production_receipt": deepcopy(receipt)}],
             "checkpoints": [], "presentation_identity_proven": False}
    return node, frame


class NativeLabelProjectionTests(unittest.TestCase):
    def test_real_quantity_style_is_retained_without_claiming_visible_fonts_or_geometry(self):
        node, frame = submitted_label()
        before = deepcopy(node), deepcopy(frame)
        result, issues = native_label_submission(node, frame)
        self.assertEqual(result["style"], {"font_size": 12, "font_weight": 400, "foreground": [84, 82, 77, 17.85]})
        self.assertEqual(result["submitted_glyph_runs"], node["native_label_evidence"]["draw"]["glyph_runs"])
        self.assertTrue(result["frame_binding"]["production_draw_matches"])
        self.assertFalse(result["presentation_identity_proven"])
        self.assertIsNone(result["visible_glyph_coverage"])
        self.assertEqual([row["property"] for row in issues], ["evidence.native_label_visible_glyphs"])
        self.assertEqual((node, frame), before)

    def test_missing_empty_or_stale_actual_receipts_never_use_declared_style(self):
        for receipt in (None, {}, {"source": "NativeLabel production SurfaceImageSource / DirectWrite renderer"}):
            with self.subTest(receipt=receipt):
                node, frame = submitted_label()
                node["native_label_evidence"] = receipt
                result, issues = native_label_submission(node, frame)
                self.assertIsNone(result["style"])
                self.assertTrue(issues)
        for key, value in (("current_draw_ordinal", 8), ("current_layout_revision", None), ("last_failure", "EndDraw failed")):
            node, frame = submitted_label()
            node["native_label_evidence"][key] = value
            result, issues = native_label_submission(node, frame)
            self.assertIsNone(result["style"])
            self.assertEqual(issues[0]["property"], "style.native_label_submission")

    def test_pending_unbound_or_failed_draw_does_not_supply_style(self):
        for key, value in (("queued", True), ("rendering", True), ("surface_binding_same_com_identity", False)):
            node, frame = submitted_label()
            node["native_label_evidence"]["current_submission"][key] = value
            self.assertIsNone(native_label_submission(node, frame)[0]["style"])
        node, frame = submitted_label()
        node["native_label_evidence"]["draw"]["surface_end_draw_hresult"] = -2147467259
        self.assertIsNone(native_label_submission(node, frame)[0]["style"])

    def test_style_must_agree_with_actual_getters_and_brush_receipt(self):
        for mutate in (lambda node: node["style"].update(font_size=13),
                       lambda node: node["style"].update(foreground=[84, 82, 77, 18]),
                       lambda node: node["style"]["native_label_style_evidence"].update(draw_ordinal=2),
                       lambda node: node["native_label_evidence"]["draw"]["actual_text_format"].update(source="requested values")):
            node, frame = submitted_label()
            mutate(node)
            result, issues = native_label_submission(node, frame)
            self.assertIsNone(result["style"])
            self.assertTrue(any(row["property"] == "style.native_label_submission" for row in issues))

    def test_null_duplicate_or_wrong_index_frame_evidence_is_not_text_matched(self):
        for mutate in (lambda frame: frame.update(baseline=None), lambda frame: frame.update(production_draws=None),
                       lambda frame: frame["baseline"].append(deepcopy(frame["baseline"][0])),
                       lambda frame: frame["baseline"][0].update(capture_label_index=1)):
            node, frame = submitted_label()
            mutate(frame)
            result, issues = native_label_submission(node, frame)
            self.assertIsNotNone(result["style"])
            self.assertIsNone(result["frame_binding"])
            self.assertTrue(any(row["property"] == "evidence.native_label_frame_binding" for row in issues))

    def test_canonical_element_keeps_text_peer_and_unknown_text_geometry(self):
        node, frame = submitted_label()
        raw = measured([node])
        raw[0]["paint_kind"] = "glyphs"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xaml = {"schema_version": 1, "scene_id": SCENE, "platform": "windows", "viewport": VIEWPORT,
                    "raw_nodes": raw, "extraction_errors": [], "capture_evidence": {"native_label_frame": frame}}
            uia = {"case_id": SCENE, "viewport": VIEWPORT,
                   "raw_nodes": [uia_node("text-peer", "Text", name=node["text"], bounds=node["bounds"])], "measurement_errors": []}
            (root / "xaml.json").write_text(json.dumps(xaml), encoding="utf-8")
            (root / "uia.json").write_text(json.dumps(uia), encoding="utf-8")
            Image.new("RGBA", (VIEWPORT["width"], VIEWPORT["height"]), "white").save(root / "shot.png")
            result = project(root / "xaml.json", root / "uia.json", root / "shot.png")
        element = next(item for item in result["elements"] if item["id"] == "label")
        self.assertEqual(element["kind"], "text")
        self.assertEqual(element["text"], node["text"])
        self.assertEqual(element["style"]["foreground"], [84, 82, 77, 17.85])
        self.assertIsNone(element["style"]["rendered_fonts"])
        self.assertIsNone(element["evidence"]["text_bounds"])
        self.assertIsNotNone(element["evidence"]["native_label_submission"])


if __name__ == "__main__":
    unittest.main()
