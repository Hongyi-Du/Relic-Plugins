"""Pure synthetic/recorded receipt regressions; CI only, no native UI or subprocesses."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from windows_outline import (CONTRACTS, LOCAL_LAYOUT_CONTRACTS, LOCAL_LAYOUT_SOURCE,
                             RUN_SOURCE, SOURCE, VECTOR_CONTRACT, VECTOR_RUNTIME,
                             VECTOR_SOURCE, TEMPLATE_CONTROL_TYPES, LABEL_RUNTIME,
                             LABEL_CONTRACT, LABEL_SOURCE, LABEL_SURFACE_SOURCE,
                             PERSON_RUNTIME, PERSON_CONTRACT, PERSON_SOURCE, PERSON_SDK_SOURCE,
                             SELECTOR_ITEM_RUNTIME, SELECTOR_ITEM_CONTRACT, SELECTOR_ITEM_SOURCE,
                             SELECTOR_ITEM_SDK_SOURCE, native_outline)


def primitive(eid="paint", typ="Border", parent=None):
    runtime = ("Microsoft.UI.Xaml.Shapes." if typ in {"Rectangle", "Ellipse", "Line", "Path", "Polygon", "Polyline"}
               else "Microsoft.UI.Xaml.Controls.Primitives." if typ in {"RepeatButton", "ToggleButton", "ScrollBar", "Thumb"}
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


def native_label():
    """Synthetic new-contract receipt, not a relabelled historical capture."""
    node = primitive("label", "NativeLabel")
    image = primitive("surface", "Image", "label")
    binding = {"source": LABEL_SURFACE_SOURCE, "owner_id": "label",
               "same_image_object": True, "surface_binding_same_com_identity": True,
               "source_type": "Microsoft.UI.Xaml.Media.Imaging.SurfaceImageSource",
               "layout_revision": 7, "surface_revision": 1, "draw_ordinal": 4}
    image["native_label_surface_evidence"] = deepcopy(binding)
    raw = node["outline_owner_evidence"]
    raw.update(runtime_type=LABEL_RUNTIME, own_paint_contract=LABEL_CONTRACT,
        native_label_content={"source": LABEL_SOURCE, "status": "measured", "owner_id": "label",
                              "base_type": "Microsoft.UI.Xaml.Controls.Panel", "is_sealed": True,
                              "audited_source": "native/windows/Relic/NativeLabel.cs#NativeLabel",
                              "visual_child_count": 1, "panel_child_count": 1, "image_id": "surface",
                              "production_image_is_current_only_child": True,
                              "production_image_binding": deepcopy(binding)})
    raw["children"]["items"] = [{"id": "surface", "index": 0, "same_parent_object": True}]
    return node, image


def person_picture():
    """Synthetic new SDK contract; not a replacement for the recorded null."""
    node = primitive("avatar", "PersonPicture")
    child = primitive("template-child", "ContentPresenter", "avatar")
    node["render_type_evidence"] = {"source": "Actual runtime XAML base types",
                                    "is_control": True, "control_template_present": True}
    node["outline_owner_evidence"].update(runtime_type=PERSON_RUNTIME, own_paint_contract=PERSON_CONTRACT,
        person_picture_template={"source": PERSON_SOURCE, "status": "measured", "owner_id": "avatar",
                                 "base_type": "Microsoft.UI.Xaml.Controls.Control", "is_sealed": False,
                                 "template_present": True, "template_type": "Microsoft.UI.Xaml.Controls.ControlTemplate",
                                 "visual_child_count": 1, "audited_sdk_source": PERSON_SDK_SOURCE})
    node["outline_owner_evidence"]["children"]["items"] = [
        {"id": "template-child", "index": 0, "same_parent_object": True}]
    return node, child


def selector_item():
    """Synthetic new exact-type receipt; historical missing receipts stay unknown."""
    node = primitive("item", "SelectorBarItem")
    child = primitive("template-root", "Grid", "item")
    node["render_type_evidence"] = {"source": "Actual runtime XAML base types",
                                    "is_control": True, "control_template_present": True}
    node["outline_owner_evidence"].update(runtime_type=SELECTOR_ITEM_RUNTIME, own_paint_contract=SELECTOR_ITEM_CONTRACT,
        selector_item_template={"source": SELECTOR_ITEM_SOURCE, "status": "measured", "owner_id": "item",
                                "base_type": "Microsoft.UI.Xaml.Controls.ItemContainer",
                                "base_base_type": "Microsoft.UI.Xaml.Controls.Control", "is_sealed": False,
                                "template_present": True, "template_type": "Microsoft.UI.Xaml.Controls.ControlTemplate",
                                "visual_child_count": 1, "audited_sdk_source": SELECTOR_ITEM_SDK_SOURCE})
    node["outline_owner_evidence"]["children"]["items"] = [
        {"id": child["id"], "index": 0, "same_parent_object": True}]
    return node, child


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

    def test_exact_template_control_contract_never_covers_derived_or_special_renderers(self):
        for runtime in TEMPLATE_CONTROL_TYPES:
            node = primitive(typ=runtime.rsplit(".", 1)[-1])
            self.assertEqual(self.result(node)[0], "none")
            node["outline_owner_evidence"]["runtime_type"] = "Relic.Derived" + node["type"]
            self.assertUnknown(node)
        for typ in ("ContentControl", "ListViewItemPresenter", "TextBoxView"):
            node = primitive(typ=typ)
            node["outline_owner_evidence"]["own_paint_contract"] = "native-core-control-template-children-only"
            self.assertUnknown(node)

    def test_template_control_receipt_cannot_hide_its_unmeasured_text_view(self):
        node = primitive("textbox", "TextBox")
        child = primitive("textview", "TextBoxView", "textbox")
        node["outline_owner_evidence"]["children"]["items"] = [
            {"id": "textview", "index": 0, "same_parent_object": True}]
        # Own template container paint is separate from glyphs/caret/selection.
        self.assertEqual(self.result(node, [child])[0], "none")
        self.assertUnknown(child, [node])
        node["outline_owner_evidence"]["children"]["items"] = []
        self.assertUnknown(node, [child])

    def test_template_control_keeps_focus_and_composition_obligations(self):
        for runtime in TEMPLATE_CONTROL_TYPES:
            typ = runtime.rsplit(".", 1)[-1]
            node = primitive(typ=typ)
            node["outline_owner_evidence"]["composition"].update(
                child_visual_present=True, child_visual_type="ActualAttachedVisual")
            self.assertUnknown(node)
            node = primitive(typ=typ)
            node["outline_owner_evidence"]["focus"].update(state="Keyboard", relationship="same-object")
            self.assertUnknown(node)

    def test_exact_selector_item_parent_proof_preserves_raw_and_independent_child_paint(self):
        node, child = selector_item()
        child["outline_owner_evidence"]["composition"].update(
            child_visual_present=True, child_visual_type="ActualChildVisual")
        before = deepcopy([node, child])
        value, proof, gaps = self.result(node, [child])
        self.assertEqual(value, "none")
        self.assertEqual(gaps, [])
        self.assertEqual(proof["raw"], before[0]["outline_owner_evidence"])
        self.assertUnknown(child, [node])
        self.assertEqual([node, child], before)

    def test_selector_item_requires_exact_runtime_base_template_and_child_receipts(self):
        for key in selector_item()[0]["outline_owner_evidence"]["selector_item_template"]:
            with self.subTest(missing=key):
                node, child = selector_item()
                node["outline_owner_evidence"]["selector_item_template"].pop(key)
                self.assertUnknown(node, [child])
        for updates in ({"base_type": "Microsoft.UI.Xaml.Controls.Control"},
                        {"base_base_type": "Microsoft.UI.Xaml.Controls.ContentControl"},
                        {"is_sealed": True}, {"owner_id": "other"}, {"template_present": False},
                        {"visual_child_count": 0}, {"visual_child_count": True},
                        {"audited_sdk_source": "unverified SDK"}):
            with self.subTest(updates=updates):
                node, child = selector_item()
                node["outline_owner_evidence"]["selector_item_template"].update(updates)
                self.assertUnknown(node, [child])
        for runtime in ("Relic.CustomSelectorBarItem", "Microsoft.UI.Xaml.Controls.ItemContainer",
                        "Microsoft.UI.Xaml.Controls.Control", "Microsoft.UI.Xaml.Controls.ContentControl"):
            node, child = selector_item()
            node["type"] = runtime.rsplit(".", 1)[-1]
            node["outline_owner_evidence"]["runtime_type"] = runtime
            self.assertUnknown(node, [child])

    def test_selector_item_keeps_historical_unknown_and_focus_composition_child_obligations(self):
        node, child = selector_item()
        node["outline_owner_evidence"]["own_paint_contract"] = None
        node["outline_owner_evidence"].pop("selector_item_template")
        self.assertUnknown(node, [child])
        for section, updates in (("focus", {"state": "Keyboard"}),
                                 ("composition", {"child_visual_present": True, "child_visual_type": "ActualVisual"}),
                                 ("composition", {"shadow_present": True, "shadow_type": "ActualShadow"}),
                                 ("children", {"complete": False})):
            with self.subTest(section=section):
                node, child = selector_item()
                node["outline_owner_evidence"][section].update(updates)
                self.assertUnknown(node, [child])
        node, child = selector_item()
        self.assertUnknown(node)
        node["render_type_evidence"]["control_template_present"] = False
        self.assertUnknown(node, [child])

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
        child = primitive("child", "PersonPicture", "paint")
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
                child = primitive("child", "PersonPicture", "layout")
                node["outline_owner_evidence"]["children"]["items"] = [
                    {"id": "child", "index": 0, "same_parent_object": True}]
                self.assertEqual(self.result(node, [child])[0], "none")
                self.assertUnknown(child, [node])
                node["outline_owner_evidence"]["children"]["items"][0]["same_parent_object"] = False
                self.assertUnknown(node, [child])
                node["outline_owner_evidence"]["children"]["items"] = []
                self.assertUnknown(node, [child])

    def test_exact_native_label_proves_only_parent_panel_paint_without_mutating_receipts(self):
        node, image = native_label()
        before = deepcopy([node, image])
        value, proof, gaps = self.result(node, [image])
        self.assertEqual(value, "none")
        self.assertTrue(proof["absence_proven"])
        self.assertIn("native Panel paint only", proof["scope"])
        self.assertEqual(gaps, [])
        self.assertEqual([node, image], before)
        self.assertEqual(proof["raw"], before[0]["outline_owner_evidence"])
        self.assertEqual(self.result(image, [node])[0], "none")

    def test_native_label_requires_complete_exact_runtime_and_child_contract(self):
        keys = tuple(native_label()[0]["outline_owner_evidence"]["native_label_content"])
        for key in keys:
            with self.subTest(missing=key):
                node, image = native_label()
                node["outline_owner_evidence"]["native_label_content"].pop(key)
                self.assertUnknown(node, [image])
        for changed in ({"base_type": "Relic.OtherPanel"}, {"is_sealed": False}, {"is_sealed": 1},
                        {"audited_source": "native/windows/Relic/Design.cs#ActionRow"}, {"owner_id": "other"},
                        {"image_id": "label"}, {"visual_child_count": 2}, {"panel_child_count": True},
                        {"production_image_is_current_only_child": False}):
            with self.subTest(changed=changed):
                node, image = native_label()
                node["outline_owner_evidence"]["native_label_content"].update(changed)
                self.assertUnknown(node, [image])
        for changed in ({"runtime_type": "Relic.OtherLabel"}, {"own_paint_contract": None},
                        {"own_paint_contract": "native-panel-background"}):
            node, image = native_label()
            node["outline_owner_evidence"].update(changed)
            self.assertUnknown(node, [image])

    def test_native_label_binds_both_actual_surface_observations_and_current_revisions(self):
        for side in ("parent", "image"):
            for key in tuple(native_label()[1]["native_label_surface_evidence"]):
                with self.subTest(side=side, missing=key):
                    node, image = native_label()
                    binding = (node["outline_owner_evidence"]["native_label_content"]["production_image_binding"]
                               if side == "parent" else image["native_label_surface_evidence"])
                    binding.pop(key)
                    self.assertUnknown(node, [image])
            for changed in ({"same_image_object": False}, {"surface_binding_same_com_identity": False},
                            {"source_type": "Microsoft.UI.Xaml.Media.Imaging.BitmapImage"},
                            {"owner_id": "other"}, {"layout_revision": 8}, {"surface_revision": 0},
                            {"draw_ordinal": True}, {"draw_ordinal": 5}):
                with self.subTest(side=side, changed=changed):
                    node, image = native_label()
                    binding = (node["outline_owner_evidence"]["native_label_content"]["production_image_binding"]
                               if side == "parent" else image["native_label_surface_evidence"])
                    binding.update(changed)
                    self.assertUnknown(node, [image])

    def test_native_label_rejects_changed_visual_identity_or_an_additional_actual_child(self):
        node, image = native_label()
        self.assertUnknown(node)
        image["parent"] = None
        self.assertUnknown(node, [image])
        node, image = native_label()
        image["outline_owner_evidence"]["runtime_type"] = "Relic.OtherImage"
        self.assertUnknown(node, [image])
        node, image = native_label()
        extra = primitive("unaccounted", "Border", "label")
        extra["render_sibling_order"] = 1
        # Even mutually complete children receipts cannot change the audited
        # production renderer's requirement of one actual bound Image.
        node["outline_owner_evidence"]["children"]["items"].append(
            {"id": "unaccounted", "index": 1, "same_parent_object": True})
        self.assertUnknown(node, [image, extra])

    def test_native_label_retains_focus_composition_shadow_and_children_failures(self):
        for section, updates in (
            ("focus", {"state": "Keyboard"}),
            ("focus", {"owner_ancestry_complete": False}),
            ("composition", {"child_visual_present": True, "child_visual_type": "ActualAttachedVisual"}),
            ("composition", {"shadow_present": True, "shadow_type": "Microsoft.UI.Xaml.Media.ThemeShadow"}),
            ("children", {"complete": False}),
        ):
            with self.subTest(section=section, changed=updates):
                node, image = native_label()
                node["outline_owner_evidence"][section].update(updates)
                self.assertUnknown(node, [image])

    def test_native_label_never_proves_the_child_images_own_outline(self):
        node, image = native_label()
        image["outline_owner_evidence"]["composition"].update(
            shadow_present=True, shadow_type="Microsoft.UI.Xaml.Media.ThemeShadow")
        self.assertEqual(self.result(node, [image])[0], "none")
        self.assertUnknown(image, [node])
        image["outline_owner_evidence"]["status"] = "error"
        self.assertEqual(self.result(node, [image])[0], "none")
        self.assertUnknown(image, [node])

    def test_recorded_a374_label_null_contract_stays_unknown_and_image_remains_independent(self):
        path = Path(__file__).parent / "fixtures" / "native_label_outline_recorded_a37467a.json"
        fixture = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(fixture["provenance"]["commit"], "a37467a")
        nodes = fixture["raw_nodes"]
        by_id = {node["id"]: node for node in nodes}
        node, image = by_id["xaml-31"], by_id["xaml-32"]
        before = deepcopy(nodes)
        self.assertIsNone(node["outline_owner_evidence"]["own_paint_contract"])
        self.assertTrue(image["native_label_surface_evidence"]["same_image_object"])
        self.assertTrue(image["native_label_surface_evidence"]["surface_binding_same_com_identity"])
        self.assertUnknown(node, [other for other in nodes if other is not node])
        self.assertEqual(native_outline(image, by_id)[0], "none")
        self.assertEqual(nodes, before)

    def test_exact_person_picture_parent_contract_does_not_clear_nonzero_template_brushes(self):
        node, child = person_picture()
        node["style"] = {"background": [255, 255, 255, 18], "border_color": [0, 0, 0, 25]}
        before = deepcopy([node, child])
        value, proof, gaps = self.result(node, [child])
        self.assertEqual(value, "none")
        self.assertTrue(proof["absence_proven"])
        self.assertIn("Control container only", proof["scope"])
        self.assertEqual(gaps, [])
        self.assertEqual([node, child], before)
        self.assertEqual(proof["raw"], before[0]["outline_owner_evidence"])

    def test_person_picture_requires_exact_unsealed_runtime_and_actual_template_receipts(self):
        keys = tuple(person_picture()[0]["outline_owner_evidence"]["person_picture_template"])
        for key in keys:
            with self.subTest(missing=key):
                node, child = person_picture()
                node["outline_owner_evidence"]["person_picture_template"].pop(key)
                self.assertUnknown(node, [child])
        for changed in ({"base_type": "Relic.OtherControl"}, {"is_sealed": True}, {"is_sealed": 0},
                        {"owner_id": "other"}, {"template_present": False},
                        {"template_type": "Microsoft.UI.Xaml.DataTemplate"}, {"visual_child_count": True},
                        {"audited_sdk_source": "another SDK revision"}):
            with self.subTest(changed=changed):
                node, child = person_picture()
                node["outline_owner_evidence"]["person_picture_template"].update(changed)
                self.assertUnknown(node, [child])
        for changed in ({"runtime_type": "Relic.CustomPersonPicture"}, {"runtime_type": "Microsoft.UI.Xaml.Controls.Control"},
                        {"own_paint_contract": None}, {"own_paint_contract": "native-core-control-template-children-only"}):
            node, child = person_picture()
            node["outline_owner_evidence"].update(changed)
            self.assertUnknown(node, [child])
        for key in ("source", "is_control", "control_template_present"):
            node, child = person_picture()
            node["render_type_evidence"].pop(key)
            self.assertUnknown(node, [child])
        node, child = person_picture()
        node["render_type_evidence"]["control_template_present"] = False
        self.assertUnknown(node, [child])

    def test_person_picture_requires_current_nonempty_complete_children_without_name_or_geometry_matching(self):
        node, child = person_picture()
        self.assertUnknown(node)
        node["outline_owner_evidence"]["children"]["items"] = []
        node["outline_owner_evidence"]["person_picture_template"]["visual_child_count"] = 0
        self.assertUnknown(node)  # Complete but empty is outside this contract.
        node, child = person_picture()
        child["parent"] = None
        self.assertUnknown(node, [child])
        node, child = person_picture()
        node["outline_owner_evidence"]["children"]["items"][0]["same_parent_object"] = False
        self.assertUnknown(node, [child])
        node, child = person_picture()
        extra = primitive("extra", "Ellipse", "avatar")
        extra["render_sibling_order"] = 1
        self.assertUnknown(node, [child, extra])

    def test_person_picture_retains_all_focus_composition_shadow_and_child_checks(self):
        for section, updates in (
            ("focus", {"state": "Keyboard"}),
            ("focus", {"owner_ancestry_complete": False}),
            ("composition", {"child_visual_present": True, "child_visual_type": "ActualAttachedVisual"}),
            ("composition", {"shadow_present": True, "shadow_type": "Microsoft.UI.Xaml.Media.ThemeShadow"}),
            ("children", {"complete": False}),
        ):
            with self.subTest(section=section, changed=updates):
                node, child = person_picture()
                node["outline_owner_evidence"][section].update(updates)
                self.assertUnknown(node, [child])

    def test_person_picture_parent_does_not_cover_child_image_or_ellipse_failures(self):
        for typ in ("Image", "Ellipse"):
            node, _ = person_picture()
            child = primitive("template-child", typ, "avatar")
            child["outline_owner_evidence"]["composition"].update(
                shadow_present=True, shadow_type="Microsoft.UI.Xaml.Media.ThemeShadow")
            self.assertEqual(self.result(node, [child])[0], "none")
            self.assertUnknown(child, [node])

    def test_recorded_a374_person_picture_keeps_historical_null_and_actual_child_paint(self):
        path = Path(__file__).parent / "fixtures" / "person_picture_outline_recorded_a37467a.json"
        fixture = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(fixture["provenance"]["commit"], "a37467a")
        nodes = fixture["raw_nodes"]
        by_id = {node["id"]: node for node in nodes}
        node, child = by_id["xaml-205"], by_id["xaml-206"]
        before = deepcopy(nodes)
        self.assertIsNone(node["outline_owner_evidence"]["own_paint_contract"])
        self.assertTrue(node["render_type_evidence"]["control_template_present"])
        self.assertEqual(node["style"]["background"], [255, 255, 255, 18])
        self.assertUnknown(node, [other for other in nodes if other is not node])
        self.assertEqual(native_outline(child, by_id)[0], "none")
        self.assertEqual(nodes, before)

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
