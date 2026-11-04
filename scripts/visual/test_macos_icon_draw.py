"""Synthetic contract tests, not recorded CoreGraphics/CI draw evidence.

These fixtures mirror the new producer's exported shape. No AppKit renderer,
browser, screenshot, or production application is launched by this suite.
"""
from copy import deepcopy
import json
import math
import unittest

from element_parity import validate_capture
from macos_icon_draw import SOURCE, PROVIDER, STRUCTURE_SOURCE, icon_draw_measurement


def synthetic_icon():
    path = "M3 3L21 21"
    local = {"x": 0, "y": 0, "width": 16, "height": 16}
    rect = {"x": 40, "y": 60, "width": 16, "height": 16}
    color = [90, 88, 83, 255]
    draw = {
        "provider": PROVIDER, "draw_returned": True,
        "view_identity": "synthetic-view-1", "window_identity": "synthetic-window-1",
        "revision": 2, "sequence": 4, "resource": "synthetic-line", "source_path": path,
        "local_bounds": local, "rendered_path_bounds": {"x": 2, "y": 2, "width": 12, "height": 12},
        "rendered_path_commands": [{"type": 0, "points": [[2, 2]]}, {"type": 1, "points": [[14, 14]]}],
        "foreground": color, "stroke_width": 1.7 * 16 / 24,
        "stroke_dash": [], "stroke_dash_offset": 0, "line_cap": "round", "line_join": "round",
        "should_antialias": True, "presentation_identity_proven": False,
    }
    icon = {"source": "svg", "glyph": json.dumps({"tag": "svg", "attributes": {
        "height": "16", "viewBox": "0 0 24 24", "width": "16"}, "children": [
            {"tag": "path", "attributes": {"d": path}, "children": []}]})}
    raw_style = {"color": color, "stroke_width": draw["stroke_width"], "stroke_dash": [],
                 "stroke_dash_offset": 0, "stroke_linecap": "round", "stroke_linejoin": "round"}
    item = {"id": "paint/synthetic-uuid", "parent": None, "region": "header", "kind": "icon", "order": 0,
            "text": "", "name": "", "bounds": rect, "visible_bounds": rect.copy(), "icon": icon,
            "state": {key: None for key in ("enabled", "selected", "checked", "expanded", "focused", "hovered", "unread")},
            "layout": {"wrap": None, "truncation": None, "line_count": None},
            "style": {"font_size": None, "font_weight": None, "foreground": color, "background": [0, 0, 0, 0],
                      "border_color": [0, 0, 0, 0], "border_width": 0, "corner_radius": 0, "outline": None,
                      "shadow": [], "opacity": 1, "background_image": "none", **{k: v for k, v in raw_style.items() if k != "color"}},
            "evidence": {
                "id": "paint/synthetic-uuid", "raw_node_id": "paint/synthetic-uuid", "kind": "icon", "source": SOURCE,
                "rect": rect.copy(), "style": raw_style, "icon": deepcopy(icon),
                "native_structure": {"source": STRUCTURE_SOURCE, "view_identity": "synthetic-view-1",
                    "window_identity": "synthetic-window-1", "native_subview_path": [0, 3, 1], "parent_identifier": None},
                "projection": {"source": "production CoreGraphics icon draw", "renderer": "final native PaintView.draw",
                    "resource": "synthetic-line", "path": path, "viewBox": "0 0 24 24", "current_draw": draw,
                    "last_draw": deepcopy(draw), "draw_binding_valid": True, "presentation_identity_proven": False,
                    "owner_accessibility_identifier": None, "declared_swiftui_opacity": 1,
                    "native_opacity_ancestry": []}}}
    return deepcopy(item)


class MacIconDrawTests(unittest.TestCase):
    def test_synthetic_current_draw_checks_only_its_own_scope_without_mutation(self):
        item = synthetic_icon()
        original = deepcopy(item)
        result = icon_draw_measurement(item)
        self.assertTrue(result["applicable"])
        self.assertTrue(result["draw_binding_valid"], result["issues"])
        self.assertEqual(result["issues"], [])
        self.assertFalse(result["presentation_identity_proven"])
        self.assertEqual(result["measurements"]["rendered_path_commands"], item["evidence"]["projection"]["current_draw"]["rendered_path_commands"])
        self.assertEqual(item, original)
        self.assertIsNone(item["style"]["outline"])

    def test_other_producers_and_malformed_nonapplicable_inputs_are_not_reclassified(self):
        for value in (None, [], {}, {"evidence": None}, {"evidence": {"source": "live-swiftui-icon-probe"}}):
            with self.subTest(value=value):
                result = icon_draw_measurement(value)
                self.assertFalse(result["applicable"])
                self.assertEqual(result["issues"], [])

    def test_absent_current_draw_never_borrows_previous_draw(self):
        item = synthetic_icon()
        projection = item["evidence"]["projection"]
        projection["current_draw"] = None
        projection["draw_binding_valid"] = False
        result = icon_draw_measurement(item)
        self.assertFalse(result["draw_binding_valid"])
        self.assertIsNone(result["measurements"])
        self.assertTrue(any("last_draw cannot replace" in issue for issue in result["issues"]))
        self.assertIsNotNone(projection["last_draw"])

    def test_stale_foreign_and_unmounted_receipts_cannot_pass(self):
        mutations = [
            lambda e: e["projection"].update(draw_binding_valid=False),
            lambda e: e["projection"]["last_draw"].update(sequence=3),
            lambda e: e["native_structure"].update(view_identity="foreign-view"),
            lambda e: e["native_structure"].update(window_identity="foreign-window"),
            lambda e: e["native_structure"].update(window_identity=None),
            lambda e: e["native_structure"].update(native_subview_path=None),
            lambda e: e["native_structure"].update(native_subview_path=[0, True]),
            lambda e: e["native_structure"].update(parent_identifier="different-owner"),
            lambda e: e.update(raw_node_id="foreign-node"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                item = synthetic_icon()
                mutate(item["evidence"])
                result = icon_draw_measurement(item)
                self.assertFalse(result["draw_binding_valid"])
                self.assertTrue(result["issues"])

    def test_missing_or_invalid_draw_fields_fail_closed(self):
        mutations = [
            lambda d: d.pop("sequence"), lambda d: d.update(revision=True),
            lambda d: d.update(draw_returned=False), lambda d: d.update(provider="neighbor probe"),
            lambda d: d.update(resource="foreign-resource"), lambda d: d.update(source_path="M0 0L1 1"),
            lambda d: d.update(local_bounds=None),
            lambda d: d["local_bounds"].update(width=18),
            lambda d: d.update(rendered_path_bounds=None),
            lambda d: d["rendered_path_bounds"].update(width=math.inf),
            lambda d: d.update(rendered_path_commands=[]),
            lambda d: d["rendered_path_commands"][0].update(type=1),
            lambda d: d["rendered_path_commands"][1].update(type=99),
            lambda d: d["rendered_path_commands"][1].update(points=[[14, math.nan]]),
            lambda d: d["rendered_path_commands"][1].update(points=[]),
            lambda d: d.update(foreground=[90, 88, 83, 256]),
            lambda d: d.update(stroke_width=0), lambda d: d.update(stroke_dash=[2, 1]),
            lambda d: d.update(line_cap="butt"), lambda d: d.update(should_antialias=False),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                item = synthetic_icon()
                projection = item["evidence"]["projection"]
                mutate(projection["current_draw"])
                projection["last_draw"] = deepcopy(projection["current_draw"])
                result = icon_draw_measurement(item)
                self.assertFalse(result["draw_binding_valid"])
                self.assertTrue(result["issues"])

    def test_raw_svg_and_canonical_style_must_match_the_actual_draw(self):
        changes = [
            lambda i: i["style"].update(foreground=[91, 88, 83, 255]),
            lambda i: i["evidence"]["style"].update(color=[91, 88, 83, 255]),
            lambda i: i["style"].update(stroke_width=2),
            lambda i: i["style"].update(stroke_linejoin="miter"),
            lambda i: i.update(bounds={"x": 41, "y": 60, "width": 16, "height": 16}),
            lambda i: i["icon"].update(glyph="not JSON"),
        ]
        for index, mutate in enumerate(changes):
            with self.subTest(index=index):
                item = synthetic_icon()
                mutate(item)
                self.assertFalse(icon_draw_measurement(item)["draw_binding_valid"])
        for key, value in (("width", "18"), ("viewBox", "0 0 30 30")):
            item = synthetic_icon()
            tree = json.loads(item["icon"]["glyph"])
            tree["attributes"][key] = value
            item["icon"]["glyph"] = json.dumps(tree)
            item["evidence"]["icon"] = deepcopy(item["icon"])
            self.assertFalse(icon_draw_measurement(item)["draw_binding_valid"])

    def test_presentation_claim_cannot_be_promoted_by_this_receipt(self):
        for location in ("projection", "draw"):
            item = synthetic_icon()
            projection = item["evidence"]["projection"]
            target = projection if location == "projection" else projection["current_draw"]
            target["presentation_identity_proven"] = True
            projection["last_draw"] = deepcopy(projection["current_draw"])
            result = icon_draw_measurement(item)
            self.assertFalse(result["draw_binding_valid"])
            self.assertFalse(result["presentation_identity_proven"])

    def test_shared_validation_consumes_the_receipt_without_clearing_outline_failure(self):
        item = synthetic_icon()
        data = {"schema_version": 1, "client": "macos", "scene_id": "synthetic-scene",
                "viewport": {"width": 100, "height": 100, "scale": 1}, "elements": [item],
                "extraction_errors": [], "coverage": {"raw_nodes": 1, "emitted_elements": 1, "unmeasured": []}}
        issues = validate_capture(data, "macos", "synthetic-scene", data["viewport"])
        self.assertFalse(any(issue["reason"].startswith("Mac icon draw:") for issue in issues), issues)
        self.assertTrue(any("outline" in issue["reason"] for issue in issues), issues)
        item["evidence"]["projection"]["draw_binding_valid"] = False
        issues = validate_capture(data, "macos", "synthetic-scene", data["viewport"])
        self.assertTrue(any(issue["reason"].startswith("Mac icon draw:") for issue in issues))


if __name__ == "__main__":
    unittest.main()
