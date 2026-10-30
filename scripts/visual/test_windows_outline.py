"""Pure synthetic receipt regressions; CI only, no native UI or subprocesses."""
from copy import deepcopy
import unittest

from windows_outline import (CONTRACTS, LOCAL_LAYOUT_CONTRACTS, LOCAL_LAYOUT_SOURCE,
                             RUN_SOURCE, SOURCE, VECTOR_CONTRACT, VECTOR_RUNTIME,
                             VECTOR_SOURCE, native_outline)


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


def vector_icon():
    """Synthetic live-object receipt matching the production icon's actual tree."""
    icon = primitive("icon")
    icon["type"] = "ReferenceVectorIcon"
    raw = icon["outline_owner_evidence"]
    raw.update(runtime_type=VECTOR_RUNTIME, own_paint_contract=VECTOR_CONTRACT)
    children = [primitive("viewbox", "Viewbox", "icon"), primitive("container", "Border", "viewbox"),
                primitive("canvas", "Canvas", "container"), primitive("path", "Path", "canvas")]
    nodes = [icon, *children]
    by_id = {node["id"]: node for node in nodes}
    for node in nodes:
        path, current = [], node
        while current is not None:
            path.append(current["id"])
            current = by_id.get(current.get("parent"))
        node["outline_owner_evidence"]["focus"]["owner_ancestry"] = path
        node["outline_owner_evidence"]["children"]["items"] = [
            {"id": child["id"], "index": index, "same_parent_object": True}
            for index, child in enumerate(item for item in nodes if item.get("parent") == node["id"])]
    raw["vector_content"] = {
        "source": VECTOR_SOURCE, "status": "measured", "owner_id": "icon", "template_is_null": True,
        "content_id": "viewbox", "canvas_id": "canvas", "path_id": "path",
        "content_is_current_visual_child": True, "viewbox_child_is_vector_canvas": True,
        "canvas_children_are_vector_path": True, "canvas_visual_path_complete": True,
        "canvas_visual_path": ["canvas", "container", "viewbox", "icon"]}
    return icon, children


def local_layout(runtime="Relic.ActionRow", eid="layout"):
    """Synthetic receipt, including the separately measured CLR type facts."""
    contract, base, audited_source = LOCAL_LAYOUT_CONTRACTS[runtime]
    node = primitive(eid, runtime.rsplit(".", 1)[-1])
    node["outline_owner_evidence"].update(runtime_type=runtime, own_paint_contract=contract,
        local_layout={"source": LOCAL_LAYOUT_SOURCE, "owner_id": eid,
                      "base_type": base, "is_sealed": True, "audited_source": audited_source})
    return node


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

    def test_exact_viewbox_owns_only_transform_and_preserves_internal_border_obligation(self):
        viewbox = primitive("viewbox", "Viewbox")
        border = primitive("container", "Border", "viewbox")
        viewbox["outline_owner_evidence"]["children"]["items"] = [
            {"id": "container", "index": 0, "same_parent_object": True}]
        self.assertEqual(self.result(viewbox, [border])[0], "none")
        border["outline_owner_evidence"]["composition"].update(
            child_visual_present=True, child_visual_type="Microsoft.UI.Composition.SpriteVisual")
        # A child remains independently unknown; its parent contract does not
        # erase or inherit any paint proof for that child's actual operation.
        self.assertEqual(self.result(viewbox, [border])[0], "none")
        self.assertUnknown(border, [viewbox])
        self.assertUnknown(viewbox)
        viewbox["outline_owner_evidence"]["runtime_type"] = "Relic.CustomViewbox"
        self.assertUnknown(viewbox, [border])

    def test_exact_reference_vector_binds_real_path_without_treating_stroke_as_owner_outline(self):
        icon, children = vector_icon()
        before = deepcopy([icon, *children])
        self.assertEqual(self.result(icon, children)[0], "none")
        self.assertEqual([icon, *children], before)
        children[-1]["outline_owner_evidence"]["composition"].update(
            shadow_present=True, shadow_type="Microsoft.UI.Xaml.Media.ThemeShadow")
        self.assertEqual(self.result(icon, children)[0], "none")
        self.assertUnknown(children[-1], [icon, *children[:-1]])

    def test_reference_vector_requires_exact_current_fields_and_visual_chain(self):
        for key in ("source", "status", "owner_id", "template_is_null", "content_id", "canvas_id", "path_id",
                    "content_is_current_visual_child", "viewbox_child_is_vector_canvas", "canvas_children_are_vector_path",
                    "canvas_visual_path", "canvas_visual_path_complete"):
            with self.subTest(missing=key):
                icon, children = vector_icon()
                icon["outline_owner_evidence"]["vector_content"].pop(key)
                self.assertUnknown(icon, children)
        for mutate in (
            lambda icon, children: children[2].update(parent="viewbox"),
            lambda icon, children: children[3].update(parent="container"),
            lambda icon, children: icon["outline_owner_evidence"]["vector_content"].update(path_id="canvas"),
            lambda icon, children: icon["outline_owner_evidence"]["vector_content"].update(template_is_null=False),
            lambda icon, children: icon["outline_owner_evidence"].update(runtime_type="Relic.OtherVectorIcon"),
        ):
            icon, children = vector_icon()
            mutate(icon, children)
            self.assertUnknown(icon, children)
        icon, children = vector_icon()
        children.append(primitive("unaccounted-path", "Path", "canvas"))
        self.assertUnknown(icon, children)

    def test_reference_vector_keeps_original_focus_composition_and_direct_child_checks(self):
        for section, updates in (
            ("focus", {"state": "Keyboard"}),
            ("composition", {"child_visual_present": True, "child_visual_type": "Microsoft.UI.Composition.ContainerVisual"}),
            ("composition", {"shadow_present": True, "shadow_type": "Microsoft.UI.Xaml.Media.ThemeShadow"}),
            ("children", {"complete": False}),
        ):
            icon, children = vector_icon()
            icon["outline_owner_evidence"][section].update(updates)
            self.assertUnknown(icon, children)

    def test_exact_sealed_local_layouts_prove_only_their_native_own_paint(self):
        for runtime in LOCAL_LAYOUT_CONTRACTS:
            with self.subTest(runtime=runtime):
                node = local_layout(runtime)
                # A nonempty native background is still background, not an
                # outline. This proof never replaces or removes that paint.
                node["style"] = {"background": [248, 247, 245, 255]}
                before = deepcopy(node)
                value, evidence, gaps = self.result(node)
                self.assertEqual(value, "none")
                self.assertTrue(evidence["absence_proven"])
                self.assertEqual(gaps, [])
                self.assertEqual(node, before)
                self.assertEqual(evidence["raw"], before["outline_owner_evidence"])

    def test_local_layout_requires_exact_source_base_sealed_and_owner_binding(self):
        for runtime in LOCAL_LAYOUT_CONTRACTS:
            for key in ("source", "owner_id", "base_type", "is_sealed", "audited_source"):
                with self.subTest(runtime=runtime, missing=key):
                    node = local_layout(runtime)
                    node["outline_owner_evidence"]["local_layout"].pop(key)
                    self.assertUnknown(node)
            for updates in ({"base_type": "Relic.OtherPanel"}, {"is_sealed": False},
                            {"is_sealed": 1}, {"owner_id": "other"},
                            {"audited_source": "native/windows/Relic/NativeLabel.cs#NativeLabel"}):
                with self.subTest(runtime=runtime, changed=updates):
                    node = local_layout(runtime)
                    node["outline_owner_evidence"]["local_layout"].update(updates)
                    self.assertUnknown(node)
            node = local_layout(runtime)
            node["outline_owner_evidence"]["own_paint_contract"] = "native-panel-background"
            self.assertUnknown(node)
        for runtime in ("Relic.OtherLayout", "Relic.NativeShadowPanel", "Relic.NativeLabel"):
            node = local_layout()
            node["type"] = runtime.rsplit(".", 1)[-1]
            node["outline_owner_evidence"]["runtime_type"] = runtime
            self.assertUnknown(node)

    def test_local_layout_keeps_focus_composition_and_actual_child_completeness_checks(self):
        for runtime in LOCAL_LAYOUT_CONTRACTS:
            for section, updates in (
                ("focus", {"state": "Keyboard"}),
                ("focus", {"owner_ancestry_complete": False}),
                ("composition", {"child_visual_present": True, "child_visual_type": "Microsoft.UI.Composition.ContainerVisual"}),
                ("composition", {"shadow_present": True, "shadow_type": "Microsoft.UI.Xaml.Media.ThemeShadow"}),
                ("children", {"complete": False}),
            ):
                with self.subTest(runtime=runtime, section=section, changed=updates):
                    node = local_layout(runtime)
                    node["outline_owner_evidence"][section].update(updates)
                    self.assertUnknown(node)

    def test_local_layout_neither_inherits_nor_erases_a_childs_unknown_outline(self):
        for runtime in LOCAL_LAYOUT_CONTRACTS:
            with self.subTest(runtime=runtime):
                node = local_layout(runtime)
                child = primitive("child", "Button", "layout")
                node["outline_owner_evidence"]["children"]["items"] = [
                    {"id": "child", "index": 0, "same_parent_object": True}]
                self.assertEqual(self.result(node, [child])[0], "none")
                self.assertUnknown(child, [node])
                node["outline_owner_evidence"]["children"]["items"][0]["same_parent_object"] = False
                self.assertUnknown(node, [child])
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
