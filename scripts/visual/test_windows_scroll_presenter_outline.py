"""Focused pure receipt regressions. No native UI is created by these tests."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from test_windows_outline import primitive
from windows_outline import (SCROLL_PRESENTER_CONTRACT, SCROLL_PRESENTER_RUNTIME,
                             SCROLL_PRESENTER_SDK_SOURCE, SCROLL_PRESENTER_SOURCE, native_outline)


def scroll_presenter(child_types=("StackPanel",)):
    """Synthetic new contract, deliberately separate from recorded old nulls."""
    node = primitive("presenter", "ScrollContentPresenter")
    children = [primitive("child-" + str(index), typ, "presenter") for index, typ in enumerate(child_types)]
    for index, child in enumerate(children): child["render_sibling_order"] = index
    node["outline_owner_evidence"].update(runtime_type=SCROLL_PRESENTER_RUNTIME, own_paint_contract=SCROLL_PRESENTER_CONTRACT,
        scroll_presenter={"source": SCROLL_PRESENTER_SOURCE, "status": "measured", "owner_id": "presenter",
                          "base_type": "Microsoft.UI.Xaml.Controls.ContentPresenter", "is_sealed": True,
                          "visual_child_count": len(children), "audited_sdk_source": SCROLL_PRESENTER_SDK_SOURCE})
    node["outline_owner_evidence"]["children"]["items"] = [
        {"id": child["id"], "index": index, "same_parent_object": True} for index, child in enumerate(children)]
    return [node, *children]


class ScrollPresenterOutlineTests(unittest.TestCase):
    def result(self, nodes, index=0):
        return native_outline(nodes[index], {node["id"]: node for node in nodes})

    def assert_unknown(self, nodes, index=0):
        value, evidence, gaps = self.result(nodes, index)
        self.assertIsNone(value)
        self.assertFalse(evidence["absence_proven"])
        self.assertTrue(gaps)
        self.assertEqual(evidence["raw"], nodes[index].get("outline_owner_evidence"))

    def test_exact_presenter_accepts_complete_zero_one_and_multiple_child_sets(self):
        for children in ((), ("StackPanel",), ("TextBlock",), ("FrameworkElement", "Grid", "Border")):
            with self.subTest(children=children):
                nodes = scroll_presenter(children)
                nodes[0]["style"] = {"background": [194, 65, 45, 255], "border_color": [255, 255, 255, 255], "border_width": 2}
                nodes[0]["clip"] = {"kind": "unknown", "error": "Actual clip remains unmeasured"}
                nodes[0]["scroll"] = {"horizontal_offset": None, "error": "Actual scroll remains unmeasured"}
                before = deepcopy(nodes)
                value, proof, gaps = self.result(nodes)
                self.assertEqual(value, "none"); self.assertEqual(gaps, [])
                self.assertIn("actual scroll/clip geometry", proof["scope"])
                self.assertEqual(nodes, before)

    def test_exact_presenter_requires_all_measured_runtime_and_child_count_fields(self):
        for key in tuple(scroll_presenter()[0]["outline_owner_evidence"]["scroll_presenter"]):
            with self.subTest(missing=key):
                nodes = scroll_presenter(); nodes[0]["outline_owner_evidence"]["scroll_presenter"].pop(key)
                self.assert_unknown(nodes)
        for change in ({"is_sealed": False}, {"is_sealed": 1}, {"base_type": "Microsoft.UI.Xaml.FrameworkElement"},
                       {"visual_child_count": True}, {"visual_child_count": 0}, {"visual_child_count": -1},
                       {"owner_id": "other"}, {"audited_sdk_source": "different SDK"}):
            with self.subTest(change=change):
                nodes = scroll_presenter(); nodes[0]["outline_owner_evidence"]["scroll_presenter"].update(change)
                self.assert_unknown(nodes)

    def test_other_presenters_and_derived_classes_cannot_borrow_the_contract(self):
        for runtime in ("Relic.ScrollContentPresenter", "Relic.DerivedScrollPresenter",
                        "Microsoft.UI.Xaml.Controls.ContentPresenter", "Microsoft.UI.Xaml.Controls.ItemsPresenter"):
            nodes = scroll_presenter(); nodes[0]["outline_owner_evidence"]["runtime_type"] = runtime
            self.assert_unknown(nodes)
        nodes = scroll_presenter(); nodes[0]["type"] = "ContentPresenter"
        self.assert_unknown(nodes)

    def test_exact_presenter_keeps_focus_composition_and_current_child_identity_requirements(self):
        for section, change in (("focus", {"state": "Keyboard"}), ("focus", {"owner_ancestry_complete": False}),
                                ("composition", {"child_visual_present": True}), ("composition", {"shadow_present": True}),
                                ("children", {"complete": False})):
            nodes = scroll_presenter(); nodes[0]["outline_owner_evidence"][section].update(change)
            self.assert_unknown(nodes)
        nodes = scroll_presenter(); nodes[1]["parent"] = None
        self.assert_unknown(nodes)
        nodes = scroll_presenter(); nodes[0]["outline_owner_evidence"]["children"]["items"][0]["same_parent_object"] = False
        self.assert_unknown(nodes)
        nodes = scroll_presenter(); nodes.append(primitive("extra", "Border", "presenter"))
        self.assert_unknown(nodes)

    def test_parent_own_paint_does_not_cover_childs_unknown_outline(self):
        nodes = scroll_presenter(("FrameworkElement",))
        self.assertEqual(self.result(nodes)[0], "none")
        self.assert_unknown(nodes, 1)
        nodes = scroll_presenter(("TextBlock",))
        nodes[1]["outline_owner_evidence"]["composition"].update(child_visual_present=True, child_visual_type="ActualVisual")
        self.assertEqual(self.result(nodes)[0], "none")
        self.assert_unknown(nodes, 1)

    def test_recorded_ca8_presenter_keeps_actual_clip_and_historical_unknown_parent_and_child(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "scroll_presenter_outline_recorded_ca8d997.json").read_text(encoding="utf-8"))
        self.assertEqual(fixture["provenance"]["commit"], "ca8d997")
        nodes = fixture["raw_nodes"]; before = deepcopy(nodes); by_id = {node["id"]: node for node in nodes}
        parent, child = by_id["xaml-158"], by_id["xaml-159"]
        self.assertIsNone(parent["outline_owner_evidence"]["own_paint_contract"])
        self.assertEqual(parent["outline_owner_evidence"]["runtime_type"], SCROLL_PRESENTER_RUNTIME)
        self.assertEqual(parent["clip"]["kind"], "rectangle")
        self.assertEqual(parent["clip"]["local_bounds"]["width"], 176)
        self.assertIsNone(native_outline(parent, by_id)[0])
        self.assertIsNone(native_outline(child, by_id)[0])
        self.assertEqual(nodes, before)


if __name__ == "__main__":
    unittest.main()
