"""Pure synthetic receipt regressions; CI only, no native UI or subprocesses."""
from copy import deepcopy
import unittest

from windows_outline import CONTRACTS, RUN_SOURCE, SOURCE, native_outline


def primitive(eid="paint", typ="Border", parent=None):
    runtime = ("Microsoft.UI.Xaml.Shapes." if typ in {"Rectangle", "Ellipse", "Line", "Path", "Polygon", "Polyline"}
               else "Microsoft.UI.Xaml.Controls.") + typ
    return {"id": eid, "type": typ, "parent": parent, "render_sibling_order": 0,
            "outline_owner_evidence": {"source": SOURCE, "status": "measured", "owner_id": eid,
                "runtime_type": runtime, "own_paint_contract": CONTRACTS.get(runtime),
                "composition": {"status": "measured", "api": "ElementCompositionPreview.GetElementChildVisual(actual owner)",
                                "child_visual_present": False, "child_visual_type": None, "shadow_present": False, "shadow_type": None},
                "children": {"status": "measured", "complete": True, "items": []},
                "focus": {"status": "measured", "state": "Unfocused", "use_system_focus_visuals": True,
                          "is_template_focus_target": False, "relationship": "no-focused-object",
                          "owner_ancestry": [eid] + ([parent] if parent else []), "owner_ancestry_complete": True,
                          "global": {"source": SOURCE, "status": "measured", "focused_object_is_null": True,
                                     "focused_object_id": None, "focused_object_type": None,
                                     "focused_object_focus_state": None, "focused_object_use_system_focus_visuals": None}}}}


class WindowsOutlineTests(unittest.TestCase):
    def result(self, node, others=()):
        return native_outline(node, {n["id"]: n for n in [node, *others]})

    def assertUnknown(self, node, others=()):
        value, evidence, gaps = self.result(node, others)
        self.assertIsNone(value)
        self.assertFalse(evidence["absence_proven"])
        self.assertTrue(gaps)
        self.assertEqual(evidence["raw"], node.get("outline_owner_evidence"))

    def test_exact_native_primitive_proves_only_own_paint_and_never_mutates_receipt(self):
        for runtime in CONTRACTS:
            node = primitive(typ=runtime.rsplit(".", 1)[-1])
            before = deepcopy(node)
            value, evidence, gaps = self.result(node)
            self.assertEqual(value, "none")
            self.assertTrue(evidence["absence_proven"])
            self.assertEqual(gaps, [])
            self.assertEqual(node, before)

    def test_missing_or_failed_fields_are_not_absence(self):
        for section in ("source", "status", "runtime_type", "owner_id", "own_paint_contract", "children", "focus", "composition"):
            node = primitive()
            node["outline_owner_evidence"].pop(section)
            self.assertUnknown(node)
        for field in ("child_visual_present", "child_visual_type", "shadow_present", "shadow_type"):
            node = primitive()
            node["outline_owner_evidence"]["composition"].pop(field)
            self.assertUnknown(node)

    def test_derived_or_compound_type_cannot_borrow_native_contract(self):
        for runtime, typ in (("Relic.CustomBorder", "Border"), ("Microsoft.UI.Xaml.Controls.Button", "Button"),
                             ("Relic.NativeShadowPanel", "NativeShadowPanel")):
            node = primitive()
            node["type"] = typ
            node["outline_owner_evidence"]["runtime_type"] = runtime
            self.assertUnknown(node)

    def test_hand_in_and_shadow_are_unknown_even_when_transparent_or_named_shadow(self):
        for field, typ in (("child_visual_present", "child_visual_type"), ("shadow_present", "shadow_type")):
            node = primitive()
            receipt = node["outline_owner_evidence"]["composition"]
            receipt[field] = True
            receipt[typ] = "ActualNativeVisual"
            receipt["opacity"] = 0
            self.assertUnknown(node)

    def test_non_system_focus_does_not_prove_no_template_focus(self):
        node = primitive()
        focus = node["outline_owner_evidence"]["focus"]
        focus.update(state="Keyboard", use_system_focus_visuals=False, relationship="same-object")
        focus["global"].update(focused_object_is_null=False, focused_object_id="paint",
                               focused_object_type="Microsoft.UI.Xaml.Controls.Border",
                               focused_object_focus_state="Keyboard", focused_object_use_system_focus_visuals=False)
        self.assertUnknown(node)

    def test_focused_ancestor_keeps_template_target_unknown(self):
        parent = primitive("button", "Button")
        node = primitive(parent="button")
        focus = node["outline_owner_evidence"]["focus"]
        focus.update(relationship="focused-object-is-ancestor", focused_ancestry=["button"],
                     focused_ancestry_complete=True, is_template_focus_target=True)
        focus["global"].update(focused_object_is_null=False, focused_object_id="button",
                               focused_object_type="Microsoft.UI.Xaml.Controls.Button",
                               focused_object_focus_state="Keyboard", focused_object_use_system_focus_visuals=True)
        self.assertUnknown(node, [parent])

    def test_unrelated_actual_focus_does_not_require_whole_window_paint_proof(self):
        sibling = primitive("sibling", "Button")
        node = primitive()
        focus = node["outline_owner_evidence"]["focus"]
        focus.update(relationship="unrelated-in-captured-visual-tree", focused_ancestry=["sibling"], focused_ancestry_complete=True)
        focus["global"].update(focused_object_is_null=False, focused_object_id="sibling",
                               focused_object_type="Microsoft.UI.Xaml.Controls.Button",
                               focused_object_focus_state="Pointer", focused_object_use_system_focus_visuals=True)
        self.assertEqual(self.result(node, [sibling])[0], "none")
        focus["global"]["focused_object_id"] = "outside-unmeasured-tree"
        self.assertUnknown(node, [sibling])

    def test_unrelated_claim_cannot_replace_actual_parentage(self):
        parent = primitive("button", "Button")
        node = primitive(parent="button")
        focus = node["outline_owner_evidence"]["focus"]
        focus.update(relationship="unrelated-in-captured-visual-tree", focused_ancestry=["button"], focused_ancestry_complete=True)
        focus["global"].update(focused_object_is_null=False, focused_object_id="button",
                               focused_object_type="Microsoft.UI.Xaml.Controls.Button",
                               focused_object_focus_state="Keyboard", focused_object_use_system_focus_visuals=True)
        self.assertUnknown(node, [parent])

    def test_known_children_keep_separate_owned_paint_without_recursive_inference(self):
        node = primitive()
        child = primitive("child", "Button", "paint")
        node["outline_owner_evidence"]["children"]["items"] = [{"id": "child", "index": 0, "same_parent_object": True}]
        self.assertEqual(self.result(node, [child])[0], "none")
        self.assertUnknown(child, [node])
        node["outline_owner_evidence"]["children"]["items"] = []
        self.assertUnknown(node, [child])

    def test_real_text_run_does_not_copy_its_owners_outline_proof(self):
        owner = primitive("text", "TextBlock")
        owner["outline_owner_evidence"]["composition"]["child_visual_present"] = True
        record = {"type": "Run", "text": "actual", "start_offset": 1, "end_offset": 7,
                  "own_paint_evidence": {"source": RUN_SOURCE, "runtime_type": "Microsoft.UI.Xaml.Documents.Run",
                                         "exact_run_type": True, "owner_id": "text", "start_offset": 1, "end_offset": 7}}
        owner["layout"] = {"rich_text_runs": [record]}
        leaf = {"id": "text:run:0", "type": "Run", "parent": "text", "text": "actual",
                "text_run_source": {"owner": "text", "index": 0, "start_offset": 1, "end_offset": 7}}
        value, proof, issues = self.result(leaf, [owner])
        self.assertEqual(value, "none")
        self.assertTrue(proof["absence_proven"])
        self.assertEqual(issues, [])
        self.assertUnknown(owner, [leaf])
        record["own_paint_evidence"]["exact_run_type"] = False
        self.assertUnknown(leaf, [owner])


if __name__ == "__main__":
    unittest.main()
