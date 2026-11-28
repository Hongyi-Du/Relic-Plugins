"""Synthetic applied-template receipts; no native UI or process is launched."""
from copy import deepcopy
import unittest

from windows_textarea_placeholder import SOURCE, apply_textarea_placeholder_style, textarea_placeholder_styles


def fixture():
    def node(key, typ, parent, text=""):
        return {"id": key, "type": typ, "parent": parent, "text": text, "hidden_reason": None, "opacity": 1,
                "visible_bounds": {"x": 20, "y": 30, "width": 120, "height": 30},
                "render_type_evidence": {"is_control": typ == "NativeTextarea"}, "layout": {}, "style": {}}
    owner, grid, part, thumb = (node("owner", "NativeTextarea", None), node("grid", "Grid", "owner"),
                               node("placeholder", "TextBlock", "grid", "Synthetic placeholder"), node("thumb", "Thumb", "grid"))
    owner["layout"]["placeholder"] = part["text"]
    owner["style"] = {"font_size": 14, "font_weight": 600, "foreground": [90, 88, 83, 255],
                      "background": [255, 255, 255, 255], "border_width": 1, "corner_radius": 9}
    part["style"] = {"font_size": 12.5, "font_weight": 400, "foreground": [117, 117, 117, 255]}
    state = {"value": "", "placeholder": part["text"], "part_text": part["text"],
             "owner_is_loaded": True, "part_is_loaded": True, "same_xaml_root": True,
             "owner_visibility": "Visible", "part_visibility": "Visible", "owner_opacity": 1, "part_opacity": 1,
             "part_style": {**deepcopy(part["style"]), "foreground_brush": {
                 "type": "Microsoft.UI.Xaml.Media.SolidColorBrush", "solid_rgba": part["style"]["foreground"][:]}}}
    owner["textarea_placeholder_evidence"] = {
        "source": SOURCE, "version": 1, "owner_id": "owner", "part_id": "placeholder", "status": "measured",
        "template_part_name": "PlaceholderTextContentPresenter", "read_only": True,
        "part_runtime_type": "Microsoft.UI.Xaml.Controls.TextBlock", "same_part_object_in_capture": True,
        "part_same_object_after": True, "template_same_object_after": True, "getters_unchanged": True,
        "before": deepcopy(state), "after": deepcopy(state), "errors": [],
        "actual_ancestor_edges": [
            {"child_id": "placeholder", "parent_id": "grid", "actual_parent_in_visual_walk": True, "captured_parent_matches": True},
            {"child_id": "grid", "parent_id": "owner", "actual_parent_in_visual_walk": True, "captured_parent_matches": True}]}
    return [owner, grid, part, thumb]


class TextareaPlaceholderTests(unittest.TestCase):
    def test_actual_bound_style_overrides_only_text_properties(self):
        nodes = fixture(); original = deepcopy(nodes)
        result = textarea_placeholder_styles(nodes)
        self.assertEqual(result["unmeasured"], [])
        style = deepcopy(nodes[0]["style"])
        apply_textarea_placeholder_style(style, result["audits"]["owner"], result["styles"]["owner"], True)
        self.assertEqual(style, {**nodes[0]["style"], **nodes[2]["style"]})
        self.assertEqual(result["audits"]["owner"]["owner_configured_style"]["foreground"], [90, 88, 83, 255])
        self.assertEqual(nodes, original)  # Includes the independently interactive resize thumb.

    def test_real_nonempty_value_never_uses_placeholder_style(self):
        nodes = fixture(); nodes[0]["text"] = "Actual input"
        result = textarea_placeholder_styles(nodes); style = deepcopy(nodes[0]["style"])
        apply_textarea_placeholder_style(style, result["audits"]["owner"], None, True)
        self.assertEqual(result["styles"], {})
        self.assertEqual(style, nodes[0]["style"])

    def test_missing_foreign_duplicate_detached_or_changed_binding_fails(self):
        mutations = [lambda n: n[0].pop("textarea_placeholder_evidence"),
            lambda n: n[0]["textarea_placeholder_evidence"].update(owner_id="foreign"),
            lambda n: n[0]["textarea_placeholder_evidence"].update(part_id="thumb"),
            lambda n: n.append(deepcopy(n[2])),
            lambda n: n[2].update(parent="foreign"),
            lambda n: n[0]["textarea_placeholder_evidence"].update(part_same_object_after=False),
            lambda n: n[0]["textarea_placeholder_evidence"]["after"].update(value="Changed input"),
            lambda n: n[1]["render_type_evidence"].update(is_control=True)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                nodes = fixture(); mutate(nodes); result = textarea_placeholder_styles(nodes)
                self.assertEqual(result["styles"], {})
                self.assertTrue(result["unmeasured"])
                style = deepcopy(nodes[0]["style"])
                apply_textarea_placeholder_style(style, result["audits"]["owner"], None, True)
                self.assertIsNone(style["foreground"])
                self.assertEqual(style["background"], [255, 255, 255, 255])

    def test_hidden_zero_area_or_fully_occluded_part_cannot_fill_style(self):
        for mutate in [lambda n: n[2].update(hidden_reason="collapsed ancestor"),
                       lambda n: n[2]["visible_bounds"].update(height=0),
                       lambda n: n[2].update(opacity=0)]:
            nodes = fixture(); mutate(nodes)
            self.assertTrue(textarea_placeholder_styles(nodes)["unmeasured"])
        nodes = fixture(); result = textarea_placeholder_styles(nodes); style = deepcopy(nodes[0]["style"])
        apply_textarea_placeholder_style(style, result["audits"]["owner"], result["styles"]["owner"], False)
        self.assertIsNone(style["foreground"])

    def test_style_is_actual_and_unknown_brush_is_not_defaulted(self):
        nodes = fixture(); nodes[2]["style"]["foreground"] = [1, 2, 3, 127]
        for state in ("before", "after"):
            measured = nodes[0]["textarea_placeholder_evidence"][state]["part_style"]
            measured["foreground"] = [1, 2, 3, 127]
            measured["foreground_brush"]["solid_rgba"] = [1, 2, 3, 127]
        self.assertEqual(textarea_placeholder_styles(nodes)["styles"]["owner"]["foreground"], [1, 2, 3, 127])
        for state in ("before", "after"):
            nodes[0]["textarea_placeholder_evidence"][state]["part_style"]["foreground_brush"] = None
        self.assertTrue(textarea_placeholder_styles(nodes)["unmeasured"])

    def test_capture_hook_keeps_resize_thumb_and_existing_failures(self):
        from test_windows_elements import ProjectionTests, measured, xaml_node
        source = fixture()
        nodes = [xaml_node(n["id"], n["type"], n["text"], parent=n["parent"]) for n in source]
        for node, raw in zip(nodes, source):
            node["style"].update(raw["style"])
            node["layout"].update(raw["layout"])
            if "textarea_placeholder_evidence" in raw:
                node["textarea_placeholder_evidence"] = deepcopy(raw["textarea_placeholder_evidence"])
        nodes[-1]["resize_handle_evidence"] = {"source": "actual NativeTextarea.ResizeGrip.Handle object identity"}
        result = ProjectionTests().capture(measured(nodes))
        projected = ProjectionTests.by_id(result)
        self.assertEqual(projected["owner"]["style"]["foreground"], [117, 117, 117, 255])
        self.assertEqual(projected["owner"]["style"]["border_width"], 1)
        self.assertEqual(projected["thumb"]["kind"], "resize-handle")
        self.assertEqual(result["coverage"]["raw_nodes"], 4)
        self.assertIsNone(projected["owner"]["evidence"]["label_source"])
        self.assertIn("placeholder", projected)
        self.assertTrue(result["extraction_errors"])


if __name__ == "__main__":
    unittest.main()
