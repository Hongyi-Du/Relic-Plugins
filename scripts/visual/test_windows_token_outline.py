"""Synthetic and recorded own-paint receipts; tests run in CI, without a UI."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from test_windows_outline import primitive
from windows_outline import (DOT_CONTRACT, DOT_LAYER_SOURCE, DOT_LAYERS_SOURCE,
                             DOT_RUNTIME, DOT_SOURCE, TOKEN_CONTRACT, TOKEN_RUNTIMES,
                             TOKEN_SOURCE, native_outline)


def bind_tree(nodes):
    """Synthetic object-tree observations; never applied to recorded fixtures."""
    by_id = {node["id"]: node for node in nodes}
    for node in nodes:
        path, current = [], node
        while current is not None:
            path.append(current["id"])
            current = by_id.get(current.get("parent"))
        node["outline_owner_evidence"]["focus"]["owner_ancestry"] = path
        node["outline_owner_evidence"]["children"]["items"] = [
            {"id": child["id"], "index": index, "same_parent_object": True}
            for index, child in enumerate(child for child in nodes if child.get("parent") == node["id"])]
    return nodes


def token(runtime="Relic.OverviewChipView"):
    """New-contract synthetic receipt, not a promoted historical null."""
    node = primitive("token", runtime.rsplit(".", 1)[-1])
    presenter = primitive("presenter", "ContentPresenter", "token")
    content = primitive("content", "TextBlock", "presenter")
    node["render_type_evidence"] = {"source": "Actual runtime XAML base types", "is_control": True,
                                    "is_content_control": True, "control_template_present": True}
    node["outline_owner_evidence"].update(runtime_type=runtime, own_paint_contract=TOKEN_CONTRACT,
        overview_token_content={
            "source": TOKEN_SOURCE, "status": "measured", "owner_id": "token",
            "base_type": "Relic.OverviewTokenView", "base_base_type": "Microsoft.UI.Xaml.Controls.ContentControl",
            "is_sealed": True, "audited_source": "native/windows/Relic/OverviewStyles.cs#OverviewTokenView",
            "template_present": True, "template_type": "Microsoft.UI.Xaml.Controls.ControlTemplate",
            "visual_child_count": 1, "presenter_id": "presenter",
            "presenter_runtime_type": "Microsoft.UI.Xaml.Controls.ContentPresenter",
            "presenter_is_current_only_child": True, "content_id": "content", "content_type": "TextBlock",
            "presenter_content_same_object": True, "content_is_current_presenter_child": True})
    return bind_tree([node, presenter, content])


def state_dot():
    node = primitive("dot", "NativeStateDotView")
    surround = primitive("surround", "Ellipse", "dot")
    ring = primitive("ring", "Ellipse", "dot"); ring["render_sibling_order"] = 1
    node["render_type_evidence"] = {"source": "Actual runtime XAML base types", "is_panel": True, "is_control": False}
    node["outline_owner_evidence"].update(runtime_type=DOT_RUNTIME, own_paint_contract=DOT_CONTRACT,
        state_dot_grid={"source": DOT_SOURCE, "status": "measured", "owner_id": "dot",
                        "base_type": "Microsoft.UI.Xaml.Controls.Grid", "is_sealed": True,
                        "audited_source": "native/windows/Relic/NativeStateDotView.cs#NativeStateDotView",
                        "visual_child_count": 2, "panel_child_count": 2, "surround_id": "surround", "vacancy_ring_id": "ring",
                        "production_layers_are_current_children": True})
    node["state_dot_evidence"] = {"source": DOT_LAYERS_SOURCE, "complete": True,
                                  "current_children_same_objects": True, "current_children": ["surround", "ring"],
                                  "layers": []}
    for index, (child, role) in enumerate(((surround, "Surround"), (ring, "VacancyRing"))):
        node["state_dot_evidence"]["layers"].append({"id": child["id"], "property": role, "child_index": index})
        child["state_dot_layer_evidence"] = {"source": DOT_LAYER_SOURCE, "owner_id": "dot", "property": role, "child_index": index}
    return bind_tree([node, surround, ring])


class WindowsTokenOutlineTests(unittest.TestCase):
    def result(self, nodes, index=0):
        return native_outline(nodes[index], {node["id"]: node for node in nodes})

    def assert_unknown(self, nodes, index=0):
        value, evidence, gaps = self.result(nodes, index)
        self.assertIsNone(value)
        self.assertFalse(evidence["absence_proven"])
        self.assertTrue(gaps)
        self.assertEqual(evidence["raw"], nodes[index].get("outline_owner_evidence"))

    def test_exact_tokens_keep_actual_background_border_and_child_paint(self):
        for runtime in TOKEN_RUNTIMES:
            with self.subTest(runtime=runtime):
                nodes = token(runtime)
                nodes[0]["style"] = {"background": [194, 65, 45, 255], "border_color": [0, 0, 0, 25]}
                nodes[1]["style"] = deepcopy(nodes[0]["style"])
                before = deepcopy(nodes)
                value, proof, gaps = self.result(nodes)
                self.assertEqual(value, "none"); self.assertEqual(gaps, [])
                self.assertIn("ContentControl parent only", proof["scope"])
                self.assertEqual(nodes, before)
                self.assertEqual(self.result(nodes, 1)[0], "none")

    def test_tokens_require_every_actual_class_template_and_content_binding_field(self):
        for runtime in TOKEN_RUNTIMES:
            for key in tuple(token(runtime)[0]["outline_owner_evidence"]["overview_token_content"]):
                with self.subTest(runtime=runtime, missing=key):
                    nodes = token(runtime)
                    nodes[0]["outline_owner_evidence"]["overview_token_content"].pop(key)
                    self.assert_unknown(nodes)
        for changes in ({"is_sealed": False}, {"base_type": "Microsoft.UI.Xaml.Controls.ContentControl"},
                        {"base_base_type": "Microsoft.UI.Xaml.Controls.ListViewItem"}, {"template_present": False},
                        {"visual_child_count": True}, {"presenter_id": "token"}, {"content_id": "presenter"},
                        {"presenter_runtime_type": "Relic.OtherPresenter"}, {"presenter_is_current_only_child": False},
                        {"presenter_content_same_object": False}, {"content_is_current_presenter_child": False}):
            with self.subTest(changes=changes):
                nodes = token(); nodes[0]["outline_owner_evidence"]["overview_token_content"].update(changes)
                self.assert_unknown(nodes)
        for runtime in ("Relic.OtherToken", "Relic.OverviewTokenView", "Microsoft.UI.Xaml.Controls.ContentControl"):
            nodes = token(); nodes[0]["outline_owner_evidence"]["runtime_type"] = runtime
            self.assert_unknown(nodes)

    def test_tokens_cannot_substitute_geometry_text_or_changed_tree_for_object_bindings(self):
        for changed in ("missing-content", "content-parent", "presenter-type", "extra-child", "render-template", "binding-owner"):
            with self.subTest(changed=changed):
                nodes = token()
                if changed == "missing-content": nodes.pop()
                elif changed == "content-parent": nodes[2]["parent"] = "token"
                elif changed == "presenter-type": nodes[1]["type"] = "Grid"
                elif changed == "extra-child": nodes.append(primitive("extra", "Border", "presenter"))
                elif changed == "render-template": nodes[0]["render_type_evidence"]["control_template_present"] = False
                else: nodes[0]["outline_owner_evidence"]["overview_token_content"]["owner_id"] = "other"
                self.assert_unknown(nodes)

    def test_token_parent_keeps_focus_composition_and_independent_child_failures(self):
        for section, change in (("focus", {"state": "Keyboard"}), ("composition", {"shadow_present": True}),
                                ("composition", {"child_visual_present": True}), ("children", {"complete": False})):
            nodes = token(); nodes[0]["outline_owner_evidence"][section].update(change)
            self.assert_unknown(nodes)
        for child_index in (1, 2):
            nodes = token(); nodes[child_index]["outline_owner_evidence"]["own_paint_contract"] = None
            self.assertEqual(self.result(nodes)[0], "none")
            self.assert_unknown(nodes, child_index)

    def test_state_dot_parent_is_separate_from_actual_ellipse_strokes_and_shadow_equivalence(self):
        nodes = state_dot()
        nodes[1]["style"] = {"background": [255, 255, 255, 0], "foreground": [255, 255, 255, 255]}
        nodes[2]["style"] = {"foreground": [184, 181, 175, 255], "stroke_thickness": 1.5}
        before = deepcopy(nodes)
        value, proof, gaps = self.result(nodes)
        self.assertEqual(value, "none"); self.assertEqual(gaps, [])
        self.assertIn("No CSS inset-shadow", proof["scope"])
        self.assertEqual(nodes, before)
        for index in (1, 2): self.assertEqual(self.result(nodes, index)[0], "none")

    def test_state_dot_requires_new_runtime_and_both_existing_layer_identity_receipts(self):
        for key in tuple(state_dot()[0]["outline_owner_evidence"]["state_dot_grid"]):
            with self.subTest(missing=key):
                nodes = state_dot(); nodes[0]["outline_owner_evidence"]["state_dot_grid"].pop(key)
                self.assert_unknown(nodes)
        for key in tuple(state_dot()[0]["state_dot_evidence"]):
            nodes = state_dot(); nodes[0]["state_dot_evidence"].pop(key)
            self.assert_unknown(nodes)
        for index in (1, 2):
            for key in tuple(state_dot()[index]["state_dot_layer_evidence"]):
                nodes = state_dot(); nodes[index]["state_dot_layer_evidence"].pop(key)
                self.assert_unknown(nodes)
        for changes in ({"is_sealed": False}, {"base_type": "Microsoft.UI.Xaml.Controls.Panel"},
                        {"panel_child_count": True}, {"surround_id": "ring"}, {"production_layers_are_current_children": False}):
            nodes = state_dot(); nodes[0]["outline_owner_evidence"]["state_dot_grid"].update(changes)
            self.assert_unknown(nodes)
        for index in (0, 1):
            nodes = state_dot(); nodes[0]["state_dot_evidence"]["layers"][index]["child_index"] = bool(index)
            self.assert_unknown(nodes)

    def test_state_dot_keeps_current_child_order_types_focus_and_composition_checks(self):
        for changed in ("swapped", "reparented", "other-paint", "extra", "subclass", "focus", "shadow", "child-visual"):
            with self.subTest(changed=changed):
                nodes = state_dot()
                if changed == "swapped": nodes[0]["state_dot_evidence"]["current_children"].reverse()
                elif changed == "reparented": nodes[2]["parent"] = None
                elif changed == "other-paint": nodes[2]["type"] = "Rectangle"
                elif changed == "extra": nodes.append(primitive("extra", "Border", "dot"))
                elif changed == "subclass": nodes[0]["outline_owner_evidence"]["runtime_type"] = "Relic.OtherStateDot"
                elif changed == "focus": nodes[0]["outline_owner_evidence"]["focus"]["state"] = "Keyboard"
                elif changed == "shadow": nodes[0]["outline_owner_evidence"]["composition"]["shadow_present"] = True
                else: nodes[0]["outline_owner_evidence"]["composition"]["child_visual_present"] = True
                self.assert_unknown(nodes)

    def test_state_dot_parent_never_clears_a_layers_unknown_outline(self):
        for index in (1, 2):
            nodes = state_dot(); nodes[index]["outline_owner_evidence"]["own_paint_contract"] = None
            self.assertEqual(self.result(nodes)[0], "none")
            self.assert_unknown(nodes, index)

    def test_recorded_ca8_token_and_state_dot_null_contracts_stay_unknown(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "token_outline_recorded_ca8d997.json").read_text(encoding="utf-8"))
        self.assertEqual(fixture["provenance"]["commit"], "ca8d997")
        nodes = fixture["raw_nodes"]; before = deepcopy(nodes); by_id = {node["id"]: node for node in nodes}
        for eid in ("xaml-66", "xaml-843", "xaml-349"):
            self.assertIsNone(by_id[eid]["outline_owner_evidence"]["own_paint_contract"])
            self.assertIsNone(native_outline(by_id[eid], by_id)[0])
        self.assertEqual(by_id["xaml-66"]["style"]["background"], [194, 65, 45, 255])
        self.assertTrue(by_id["xaml-349"]["state_dot_evidence"]["current_children_same_objects"])
        for eid in ("xaml-67", "xaml-844", "xaml-350", "xaml-351"):
            self.assertEqual(native_outline(by_id[eid], by_id)[0], "none")
        self.assertEqual(nodes, before)


if __name__ == "__main__":
    unittest.main()
