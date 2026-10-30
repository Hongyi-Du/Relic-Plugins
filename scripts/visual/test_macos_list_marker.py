"""Synthetic producer-contract tests, not a recorded AppKit draw or a passed scene."""
from copy import deepcopy
import math
import unittest

from element_parity import validate_capture
from macos_list_marker import (CONTENT_FRAME_SOURCE, OBSERVATION_SOURCE, PROVIDER, SCREEN_SPACE,
                               SOURCE, STRUCTURE_SOURCE, list_marker_measurement)


def synthetic_marker():
    # Deliberately not the reference fixture's 5x5 / 7x19 values.
    local = {"x": 0, "y": 0, "width": 11, "height": 24}
    local_ellipse = {"x": 2, "y": 9, "width": 6, "height": 6}
    color = [26, 25, 22, 255]
    draw = {"provider": PROVIDER, "draw_returned": True, "revision": 0, "sequence": 1,
            "view_identity": "synthetic-view", "window_identity": "synthetic-window",
            "local_bounds": local, "local_ellipse": local_ellipse,
            "device_ellipse": {"x": 4, "y": 18, "width": 12, "height": 12},
            "context_ctm": [2, 0, 0, 2, 0, 0], "context_clip": local,
            "foreground": color, "symbol": "disc", "alternative_text": "• ",
            "font_size": 15.25, "font_postscript_name": "synthetic-primary-face",
            "native_ascent": 17.6, "native_descent": -5.8, "layout_ascent": 18, "layout_descent": 6,
            "presentation_identity_proven": False}
    observation = {"source": OBSERVATION_SOURCE, "current_draw": draw, "errors": [],
                   "screen_bounds": {"x": -200, "y": 100, "width": 11, "height": 24},
                   "screen_ellipse": {"x": -198, "y": 109, "width": 6, "height": 6},
                   "native_structure": {"source": STRUCTURE_SOURCE, "view_identity": "synthetic-view",
                                        "window_identity": "synthetic-window", "native_subview_path": [0, 2], "parent_identifier": None}}
    rect = {"x": 100, "y": 576, "width": 11, "height": 24}
    state = {k: None for k in ("enabled", "selected", "checked", "expanded", "focused", "hovered", "unread")}
    return {"id": "window/marker", "parent": None, "region": "right-pane", "order": 0,
            "kind": "icon", "name": "• ", "text": "", "bounds": rect, "visible_bounds": rect.copy(), "icon": None,
            "style": {"foreground": color, "background": None, "font_size": None, "font_weight": None,
                      "border_width": None, "border_color": None, "corner_radius": None, "outline": None},
            "layout": {"wrap": None, "line_count": None, "truncation": None}, "state": state,
            "evidence": {"id": "window/marker", "raw_node_id": "window/marker", "source": SOURCE,
                         "class": "NativeListMarkerView", "object_identity": "synthetic-view", "kind": "icon", "role": "AXImage",
                         "text": "", "name": "• ", "native_ax_label": "• ", "rect": rect.copy(),
                         "style": {"color": color.copy()}, "state": state.copy(), "native_list_marker": observation}}


def with_content_basis(item):
    item["evidence"]["native_list_marker"]["content_screen_frame"] = {
        "source": CONTENT_FRAME_SOURCE, "coordinate_space": SCREEN_SPACE,
        "window_identity": "synthetic-window", "bounds": {"x": -300, "y": -100, "width": 1024, "height": 800}}
    return item


class NativeListMarkerTests(unittest.TestCase):
    def test_current_local_draw_is_retained_but_missing_origin_fails_without_mutating_icon(self):
        item = synthetic_marker()
        before = deepcopy(item)
        result = list_marker_measurement(item)
        self.assertTrue(result["draw_binding_valid"], result["issues"])
        self.assertFalse(result["coordinate_binding_valid"])
        self.assertIsNone(result["viewport_ellipse"])
        self.assertIsNone(result["measurements"]["visible_bounds"])
        self.assertIsNone(result["measurements"]["reference_ellipse"])
        self.assertEqual(result["measurements"]["local_ellipse"], {"x": 2, "y": 9, "width": 6, "height": 6})
        self.assertTrue(any("content_screen_frame" in issue for issue in result["issues"]))
        self.assertFalse(result["presentation_identity_proven"])
        self.assertEqual(item, before)
        self.assertIsNone(item["icon"])

    def test_other_producers_are_not_reclassified(self):
        for item in (None, {}, {"evidence": None}, {"evidence": {"source": SOURCE, "class": "NSImageView"}}):
            self.assertFalse(list_marker_measurement(item)["applicable"])

    def test_missing_or_wrong_source_receipt_is_not_silently_ignored(self):
        for mutate in (lambda e: e.pop("native_list_marker"), lambda e: e.update(native_list_marker=None),
                       lambda e: e.update(source="unknown-source"),
                       lambda e: e["native_list_marker"].update(source="previous-draw")):
            item = synthetic_marker()
            mutate(item["evidence"])
            result = list_marker_measurement(item)
            self.assertTrue(result["applicable"])
            self.assertFalse(result["draw_binding_valid"])
            self.assertTrue(result["issues"])

    def test_last_draw_cannot_replace_current_draw(self):
        item = synthetic_marker()
        observation = item["evidence"]["native_list_marker"]
        observation["last_draw"] = observation["current_draw"]
        observation["current_draw"] = None
        result = list_marker_measurement(item)
        self.assertFalse(result["draw_binding_valid"])
        self.assertIsNone(result["measurements"])
        self.assertTrue(any("last draw" in issue for issue in result["issues"]))

    def test_foreign_owner_or_unmounted_structure_cannot_bind_a_draw(self):
        mutations = [lambda e: e.update(object_identity="different-view"),
                     lambda e: e.update(raw_node_id="other-node"),
                     lambda e: e["native_list_marker"]["native_structure"].update(view_identity="other"),
                     lambda e: e["native_list_marker"]["native_structure"].update(window_identity="other"),
                     lambda e: e["native_list_marker"]["native_structure"].update(native_subview_path=None),
                     lambda e: e["native_list_marker"].update(errors=["not current"])]
        for mutate in mutations:
            item = synthetic_marker()
            mutate(item["evidence"])
            self.assertFalse(list_marker_measurement(item)["draw_binding_valid"])

    def test_missing_nonfinite_or_degenerate_actual_geometry_remains_failure(self):
        for key, value in (("local_ellipse", None), ("device_ellipse", {"x": 1, "y": 2, "width": 0, "height": 2}),
                           ("context_ctm", [1, 0, 0, math.nan, 0, 0]), ("context_clip", None)):
            item = synthetic_marker()
            item["evidence"]["native_list_marker"]["current_draw"][key] = value
            result = list_marker_measurement(item)
            self.assertFalse(result["draw_binding_valid"])
            self.assertIsNone(result["measurements"])

    def test_actual_metrics_are_preserved_without_recomputing_circle(self):
        item = synthetic_marker()
        draw = item["evidence"]["native_list_marker"]["current_draw"]
        draw.update(native_ascent=30.125, layout_ascent=30, font_size=22.5)
        result = list_marker_measurement(item)
        self.assertTrue(result["draw_binding_valid"])
        self.assertEqual(result["measurements"]["local_ellipse"]["width"], 6)
        self.assertEqual(result["measurements"]["font_metrics"]["native_ascent"], 30.125)

    def test_invalid_sequence_font_query_or_presentation_claim_fails(self):
        for changes in ({"sequence": 0}, {"revision": True}, {"font_postscript_name": None},
                        {"native_descent": 2}, {"presentation_identity_proven": True}):
            item = synthetic_marker()
            item["evidence"]["native_list_marker"]["current_draw"].update(changes)
            self.assertFalse(list_marker_measurement(item)["draw_binding_valid"])

    def test_name_and_painted_text_are_distinct_quantities(self):
        item = synthetic_marker()
        item["text"] = item["evidence"]["text"] = "• "
        result = list_marker_measurement(item)
        self.assertTrue(result["draw_binding_valid"])
        self.assertTrue(any("not painted text" in issue for issue in result["issues"]))
        self.assertEqual(item["text"], "• ")
        item = synthetic_marker()
        item["name"] = "different name"
        self.assertTrue(any("AX alternative" in issue for issue in list_marker_measurement(item)["issues"]))

    def test_canonical_color_does_not_override_actual_draw(self):
        item = synthetic_marker()
        item["style"]["foreground"] = [99, 1, 2, 255]
        result = list_marker_measurement(item)
        self.assertTrue(any("fill color differs" in issue for issue in result["issues"]))
        self.assertEqual(result["measurements"]["foreground"], [26, 25, 22, 255])

    def test_actual_content_origin_can_convert_only_its_own_screen_quantity(self):
        item = with_content_basis(synthetic_marker())
        before = deepcopy(item)
        result = list_marker_measurement(item)
        self.assertTrue(result["draw_binding_valid"])
        self.assertTrue(result["coordinate_binding_valid"], result["issues"])
        self.assertEqual(result["viewport_ellipse"], {"x": 102, "y": 585, "width": 6, "height": 6})
        self.assertEqual(result["issues"], [])
        self.assertEqual(item, before)
        self.assertEqual(item["bounds"]["width"], 11)
        self.assertIsNone(item["icon"])

    def test_missing_foreign_or_wrong_quantity_basis_cannot_be_inferred_from_owner(self):
        for changes in ({"source": "derived-from-owner"}, {"window_identity": "other-window"},
                        {"coordinate_space": "window"}, {"bounds": None}):
            item = with_content_basis(synthetic_marker())
            item["evidence"]["native_list_marker"]["content_screen_frame"].update(changes)
            result = list_marker_measurement(item)
            self.assertFalse(result["coordinate_binding_valid"])
            self.assertIsNone(result["viewport_ellipse"])
            self.assertTrue(result["coordinate_issues"])

    def test_actual_content_conversion_must_agree_with_independent_ax_owner(self):
        item = with_content_basis(synthetic_marker())
        item["evidence"]["native_list_marker"]["content_screen_frame"]["bounds"]["x"] += 1
        result = list_marker_measurement(item)
        self.assertFalse(result["coordinate_binding_valid"])
        self.assertIsNone(result["viewport_ellipse"])

    def test_owner_allocation_is_not_required_to_equal_a_separate_canonical_paint_quantity(self):
        item = with_content_basis(synthetic_marker())
        item["bounds"] = {"x": 102, "y": 585, "width": 6, "height": 6}
        result = list_marker_measurement(item)
        self.assertTrue(result["coordinate_binding_valid"], result["issues"])
        self.assertEqual(result["measurements"]["owner_local_bounds"]["width"], 11)
        self.assertEqual(result["viewport_ellipse"]["width"], 6)

    def test_matcher_adds_receipt_failure_and_retains_existing_unknown_icon_and_other_errors(self):
        item = synthetic_marker()
        data = {"schema_version": 1, "client": "macos", "scene_id": "synthetic-marker",
                "viewport": {"width": 1024, "height": 800, "scale": 1}, "elements": [item],
                "extraction_errors": [], "coverage": {"raw_nodes": 1, "emitted_elements": 1, "unmeasured": ["existing gap"]}}
        before = deepcopy(data)
        issues = validate_capture(data, "macos", "synthetic-marker", data["viewport"])
        self.assertTrue(any(issue["reason"].startswith("Mac list marker:") for issue in issues))
        self.assertTrue(any("no independently extracted identity" in issue["reason"] for issue in issues))
        self.assertTrue(any("outline" in issue["reason"] for issue in issues))
        self.assertTrue(any("existing gap" in str(issue) for issue in issues))
        self.assertEqual(data, before)


if __name__ == "__main__":
    unittest.main()
