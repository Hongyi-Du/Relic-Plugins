"""Pure sidebar row object-binding regressions; no native UI or subprocesses."""
from copy import deepcopy
import unittest

from test_windows_outline import primitive
from test_windows_token_outline import bind_tree
from windows_outline import SIDEBAR_CONTRACT, SIDEBAR_RUNTIME, SIDEBAR_SOURCE, native_outline


def sidebar_row():
    row = primitive("row", "NativeSidebarRow")
    presenter = primitive("presenter", "ContentPresenter", "row")
    content = primitive("content", "Grid", "presenter")
    row["render_type_evidence"] = {"source": "Actual runtime XAML base types", "is_control": True,
                                   "is_content_control": True, "control_template_present": True}
    row["outline_owner_evidence"].update(runtime_type=SIDEBAR_RUNTIME, own_paint_contract=SIDEBAR_CONTRACT,
        sidebar_row_content={
            "source": SIDEBAR_SOURCE, "status": "measured", "owner_id": "row",
            "base_type": "Microsoft.UI.Xaml.Controls.ListViewItem", "is_sealed": True,
            "audited_source": "native/windows/Relic/NativeSidebarRow.cs#NativeSidebarRow",
            "template_present": True, "template_type": "Microsoft.UI.Xaml.Controls.ControlTemplate",
            "same_template_after": True, "same_content_after": True, "visual_child_count": 1,
            "presenter_id": "presenter", "presenter_runtime_type": "Microsoft.UI.Xaml.Controls.ContentPresenter",
            "presenter_is_current_only_child": True, "content_id": "content", "content_type": "Grid",
            "presenter_content_same_object": True, "content_is_current_presenter_child": True})
    return bind_tree([row, presenter, content])


class WindowsSidebarOutlineTests(unittest.TestCase):
    def result(self, nodes, index=0):
        return native_outline(nodes[index], {node["id"]: node for node in nodes})

    def assert_unknown(self, nodes, index=0):
        value, proof, gaps = self.result(nodes, index)
        self.assertIsNone(value)
        self.assertFalse(proof["absence_proven"])
        self.assertTrue(gaps)
        self.assertEqual(proof["raw"], nodes[index].get("outline_owner_evidence"))

    def test_current_sealed_sidebar_row_owns_no_outline_but_keeps_child_paint(self):
        nodes = sidebar_row()
        nodes[0]["style"] = {"background": [231, 229, 223, 255], "corner_radius": 8}
        nodes[1]["style"] = deepcopy(nodes[0]["style"])
        before = deepcopy(nodes)
        value, proof, gaps = self.result(nodes)
        self.assertEqual(value, "none")
        self.assertEqual(gaps, [])
        self.assertIn("ListViewItem parent only", proof["scope"])
        self.assertEqual(nodes, before)

    def test_each_runtime_template_and_object_identity_observation_is_required(self):
        for key in tuple(sidebar_row()[0]["outline_owner_evidence"]["sidebar_row_content"]):
            with self.subTest(missing=key):
                nodes = sidebar_row()
                nodes[0]["outline_owner_evidence"]["sidebar_row_content"].pop(key)
                self.assert_unknown(nodes)

    def test_changed_template_content_class_or_sealed_type_cannot_supply_absence(self):
        for changed in ({"is_sealed": False}, {"base_type": "Microsoft.UI.Xaml.Controls.ContentControl"},
                        {"same_template_after": False}, {"same_content_after": False},
                        {"presenter_content_same_object": False}, {"presenter_is_current_only_child": False},
                        {"visual_child_count": True}, {"presenter_id": "row"}, {"content_id": "presenter"},
                        {"content_type": "TextBlock"}, {"presenter_runtime_type": "Relic.OtherPresenter"}):
            with self.subTest(changed=changed):
                nodes = sidebar_row()
                nodes[0]["outline_owner_evidence"]["sidebar_row_content"].update(changed)
                self.assert_unknown(nodes)
        for runtime in ("Relic.OtherSidebarRow", "Microsoft.UI.Xaml.Controls.ContentControl"):
            nodes = sidebar_row()
            nodes[0]["outline_owner_evidence"]["runtime_type"] = runtime
            self.assert_unknown(nodes)

    def test_missing_reparented_or_additional_template_content_is_not_absorbed(self):
        for changed in ("missing-content", "content-parent", "presenter-type", "extra-child", "render-template"):
            with self.subTest(changed=changed):
                nodes = sidebar_row()
                if changed == "missing-content": nodes.pop()
                elif changed == "content-parent": nodes[2]["parent"] = "row"
                elif changed == "presenter-type": nodes[1]["type"] = "Grid"
                elif changed == "extra-child": nodes.append(primitive("extra", "Border", "presenter"))
                else: nodes[0]["render_type_evidence"]["control_template_present"] = False
                self.assert_unknown(nodes)

    def test_focus_composition_shadow_and_child_identity_errors_still_fail(self):
        for section, changed in (("focus", {"state": "Keyboard"}),
                                 ("composition", {"shadow_present": True}),
                                 ("composition", {"child_visual_present": True}),
                                 ("children", {"complete": False})):
            with self.subTest(section=section, changed=changed):
                nodes = sidebar_row()
                nodes[0]["outline_owner_evidence"][section].update(changed)
                self.assert_unknown(nodes)

    def test_row_own_paint_never_clears_independent_descendant_unknowns(self):
        for index in (1, 2):
            nodes = sidebar_row()
            nodes[index]["outline_owner_evidence"]["own_paint_contract"] = None
            self.assertEqual(self.result(nodes)[0], "none")
            self.assert_unknown(nodes, index)

    def test_historical_null_contract_and_missing_new_receipt_stay_unknown(self):
        nodes = sidebar_row()
        nodes[0]["outline_owner_evidence"].pop("sidebar_row_content")
        nodes[0]["outline_owner_evidence"]["own_paint_contract"] = None
        before = deepcopy(nodes)
        self.assert_unknown(nodes)
        self.assertEqual(nodes, before)


if __name__ == "__main__":
    unittest.main()
