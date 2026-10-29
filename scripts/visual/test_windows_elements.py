"""Recorded-tree/image projection regressions; run in CI without UI or processes."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from windows_elements import project


SCENE = "zh-CN-light-1024x700-group"
VIEWPORT = {"width": 1024, "height": 700, "scale": 1}


def box(x=10, y=20, width=100, height=30):
    return {"x": x, "y": y, "width": width, "height": height}


def xaml_node(eid, typ="TextBlock", text="", parent=None, bounds=None, **changes):
    node = {
        "id": eid, "parent": parent, "type": typ, "region": "conversation",
        "text": text, "accessible_name": "", "bounds": bounds or box(),
        "visible_bounds": deepcopy(bounds or box()), "hidden_reason": None,
        "style": {"font_size": 13, "font_weight": 400, "foreground": [27, 27, 26, 255],
                  "background": [0, 0, 0, 0], "border_color": [0, 0, 0, 0],
                  "border_width": 0, "corner_radius": 0},
        "state": {"enabled": True, "selected": None, "checked": None,
                  "expanded": None, "focused": False, "hovered": False, "unread": None},
        "layout": {"wrap": "none", "truncation": "none", "line_count": 1},
        "icon": None, "font_family": "Fixture Sans",
    }
    node.update(changes)
    return node


def uia_node(eid, control_type="Text", name="", parent=None, bounds=None, **changes):
    node = {
        "id": eid, "parent": parent, "control_type": "ControlType." + control_type,
        "name": name, "bounds": bounds or box(), "class_name": control_type,
        "automation_id": "", "is_control_element": True, "is_content_element": True,
        "state": {"enabled": True, "focused": False, "offscreen": False,
                  "selected": None, "checked": None, "expanded": None},
        "value": None, "text_pattern": None,
    }
    node.update(changes)
    return node


def measured(nodes):
    """Add actual-style render evidence to a synthetic view-tree fixture."""
    result = deepcopy(nodes)
    for order, node in enumerate(result):
        node.update(paint_order=order, canvas_z_index=0, render_sibling_order=order,
                    opacity=1, axis_aligned_transform=True, clip=None,
                    transform={"m11": 1, "m12": 0, "m21": 0, "m22": 1,
                               "offset_x": node["bounds"]["x"], "offset_y": node["bounds"]["y"]},
                    background_sizing="OuterBorderEdge")
        node["paint_kind"] = {"Border": "rounded-rectangle", "Grid": "rectangle", "StackPanel": "rectangle",
                              "TextBlock": "glyphs", "RichTextBlock": "glyphs", "Button": "template"}.get(node["type"], "none")
        node["style"].update(opacity=1, shadow=[], background_image="none",
                              border_widths=[node["style"]["border_width"]] * 4,
                              corner_radii=[node["style"]["corner_radius"]] * 4)
    return result


class ProjectionTests(unittest.TestCase):
    def capture(self, nodes, uia_nodes=None, *, xaml_changes=None, uia_changes=None,
                image_size=None):
        xaml = {"schema_version": 1, "scene_id": SCENE, "client": "windows",
                "viewport": deepcopy(VIEWPORT), "raw_nodes": nodes, "extraction_errors": []}
        uia = {"schema_version": 1, "case_id": SCENE, "client": "windows",
               "viewport": deepcopy(VIEWPORT), "raw_nodes": uia_nodes or [], "extraction_errors": []}
        xaml.update(xaml_changes or {})
        uia.update(uia_changes or {})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "scene.xaml.json").write_text(json.dumps(xaml), encoding="utf-8")
            (root / "scene.uia.json").write_text(json.dumps(uia), encoding="utf-8")
            Image.new("RGBA", image_size or (1024, 700), (248, 247, 245, 255)).save(root / "scene.png")
            return project(root / "scene.xaml.json", root / "scene.uia.json", root / "scene.png")

    @staticmethod
    def by_id(result):
        return {element["id"]: element for element in result["elements"]}

    def test_simple_label_is_owned_once_with_rendered_typography(self):
        button = xaml_node("button", "Button")
        label = xaml_node("label", text="发送", parent="button", bounds=box(20, 25, 40, 18))
        label["style"].update(font_size=11, font_weight=600)
        result = self.capture([button, label], [
            uia_node("uia-button", "Button", "发送"),
            uia_node("uia-label", "Text", "发送", parent="uia-button", bounds=label["bounds"]),
        ])
        elements = self.by_id(result)
        self.assertEqual(elements["button"]["text"], "发送")
        self.assertEqual(elements["button"]["style"]["font_size"], 11)
        self.assertEqual(elements["button"]["style"]["font_weight"], 600)
        self.assertNotIn("label", elements)
        self.assertTrue(any(p.get("source") == "label" and p.get("owner") == "button"
                            for p in result["projection"]))

    def test_compound_button_keeps_separate_title_and_subtitle(self):
        nodes = [xaml_node("button", "Button"),
                 xaml_node("title", text="设计师", parent="button", bounds=box(15, 21, 80, 13)),
                 xaml_node("subtitle", text="正在工作", parent="button", bounds=box(15, 35, 80, 13))]
        nodes[2]["style"]["font_size"] = 11
        result = self.capture(nodes, [uia_node("uia-button", "Button", "设计师 正在工作")])
        elements = self.by_id(result)
        self.assertEqual(elements["button"]["text"], "")
        self.assertEqual(elements["title"]["text"], "设计师")
        self.assertEqual(elements["subtitle"]["text"], "正在工作")
        self.assertEqual(elements["subtitle"]["style"]["font_size"], 11)
        self.assertEqual(elements["title"]["parent"], "button")

    def test_painted_wrapper_cannot_steal_same_box_button_uia(self):
        surface = xaml_node("surface", "Border")
        surface["style"]["background"] = [255, 255, 255, 255]
        nodes = [surface, xaml_node("button", "Button", parent="surface"),
                 xaml_node("label", text="发送", parent="button", bounds=box(20, 25, 40, 18))]
        result = self.capture(nodes, [uia_node("uia-button", "Button", "发送")])
        elements = self.by_id(result)
        self.assertEqual(elements["button"]["evidence"]["uia_id"], "uia-button")
        self.assertIsNone(elements["surface"]["evidence"]["uia_id"])

    def test_wrong_kind_same_text_and_box_is_not_control_witness(self):
        nodes = [xaml_node("button", "Button"),
                 xaml_node("label", text="发送", parent="button", bounds=box(20, 25, 40, 18))]
        result = self.capture(nodes, [uia_node("uia-text", "Text", "发送")])
        self.assertIsNone(self.by_id(result)["button"]["evidence"]["uia_id"])
        self.assertTrue(any(item.get("id") == "button" and "UIA" in item.get("property", "")
                            for item in result["coverage"]["unmeasured"]))

    def test_nearest_transparent_template_does_not_hide_actual_paint(self):
        button = xaml_node("button", "Button")
        wrapper = xaml_node("wrapper", "Grid", parent="button")
        paint = xaml_node("paint", "Border", parent="wrapper")
        paint["style"].update(background=[200, 100, 63, 255],
                              border_color=[160, 80, 50, 255], border_width=1, corner_radius=7)
        label = xaml_node("label", text="发送", parent="paint", bounds=box(20, 25, 40, 18))
        result = self.capture([button, wrapper, paint, label], [uia_node("uia-button", "Button", "发送")])
        style = self.by_id(result)["button"]["style"]
        self.assertEqual(style["background"], [200, 100, 63, 255])
        self.assertEqual(style["border_color"], [160, 80, 50, 255])
        self.assertEqual(style["corner_radius"], 7)

    def test_toggle_button_and_switch_keep_real_button_uia_witness(self):
        # These native peers expose ControlType.Button plus TogglePattern,
        # rather than an imaginary ControlType.Toggle.
        for typ in ("ToggleButton", "ToggleSwitch"):
            with self.subTest(typ=typ):
                toggle = xaml_node("toggle", typ)
                witness = uia_node("uia-toggle", "Button", class_name=typ,
                                   supported_patterns=["TogglePatternIdentifiers.Pattern"])
                witness["state"]["checked"] = True
                result = self.capture([toggle], [witness])
                element = self.by_id(result)["toggle"]
                self.assertEqual(element["kind"], "toggle")
                self.assertEqual(element["evidence"]["uia_id"], "uia-toggle")
                self.assertTrue(element["state"]["checked"])

    def test_inset_badge_paint_is_not_owned_as_whole_button_template(self):
        button = xaml_node("button", "Button")
        content = xaml_node("content", "Grid", parent="button", declared_content_owner="button")
        title = xaml_node("title", text="抄送", parent="content", bounds=box(15, 25, 40, 18))
        badge = xaml_node("badge", "Border", parent="content", bounds=box(75, 25, 20, 18))
        badge["style"].update(background=[249, 238, 232, 255], corner_radius=5)
        counter = xaml_node("counter", text="3", parent="badge", bounds=box(80, 27, 10, 14))
        result = self.capture([button, content, title, badge, counter], [uia_node("uia-button", "Button", "抄送 3")])
        elements = self.by_id(result)
        self.assertIn("badge", elements, "A distinct visible badge must survive template normalization")
        self.assertEqual(elements["badge"]["style"]["background"], [249, 238, 232, 255])
        self.assertIn("counter", elements)

    def test_card_body_is_not_merged_into_card_label(self):
        dialog = xaml_node("dialog", "ContentDialog", bounds=box(0, 0, 200, 150))
        body = xaml_node("body", text="请先保存更改。", parent="dialog", bounds=box(20, 30, 150, 25),
                         declared_content_owner="dialog")
        result = self.capture([dialog, body], [
            uia_node("uia-dialog", "Group", "", bounds=dialog["bounds"]),
            uia_node("uia-body", "Text", "请先保存更改。", parent="uia-dialog", bounds=body["bounds"]),
        ])
        elements = self.by_id(result)
        self.assertEqual(elements["dialog"]["text"], "")
        self.assertIn("body", elements, "The card's content is a visible text element, not its single label")
        self.assertEqual(elements["body"]["bounds"], body["bounds"])

    def test_independent_uia_button_is_not_hidden_as_same_text_label(self):
        outer = xaml_node("button", "Button")
        label = xaml_node("label", text="打开", parent="button", bounds=box(15, 25, 80, 18))
        result = self.capture([outer, label], [
            uia_node("uia-outer", "Button", "打开"),
            uia_node("uia-independent", "Button", "打开", parent="uia-outer", bounds=box(30, 28, 25, 12)),
        ])
        self.assertTrue(any(item.get("id") == "uia-independent"
                            for item in result["coverage"]["unmeasured"]))
        self.assertFalse(any(item.get("source") == "uia-independent" and item.get("owner")
                             for item in result["projection"]))

    def test_parent_is_nearest_emitted_ancestor_not_discarded_wrapper(self):
        surface = xaml_node("surface", "Border", bounds=box(0, 0, 200, 150))
        surface["style"]["background"] = [255, 255, 255, 255]
        layout = xaml_node("layout", "StackPanel", parent="surface")
        text = xaml_node("text", text="内容", parent="layout")
        result = self.capture([surface, layout, text], [uia_node("uia-text", "Text", "内容")])
        elements = self.by_id(result)
        self.assertNotIn("layout", elements)
        self.assertEqual(elements["text"]["parent"], "surface")
        self.assertEqual(elements["text"]["evidence"]["raw_parent"], "layout")

    def test_empty_uia_is_an_explicit_extraction_error(self):
        result = self.capture([xaml_node("text", text="内容")], [])
        self.assertTrue(any("uia" in str(error).lower() for error in result["extraction_errors"]))

    def test_empty_xaml_is_an_explicit_extraction_error(self):
        result = self.capture([], [uia_node("uia-text", "Text", "内容")])
        self.assertTrue(any("xaml" in str(error).lower() for error in result["extraction_errors"]))

    def test_independent_sources_must_describe_the_same_case(self):
        result = self.capture([xaml_node("text", text="内容")], [uia_node("uia-text", "Text", "内容")],
                              uia_changes={"case_id": "en-US-dark-1024x700-private"})
        self.assertTrue(result["extraction_errors"], "Stale UIA must not witness a different scene")

    def test_image_dimensions_must_match_measured_viewport(self):
        result = self.capture([xaml_node("text", text="内容")], [uia_node("uia-text", "Text", "内容")],
                              image_size=(1025, 700))
        self.assertTrue(result["extraction_errors"])

    def test_native_sources_must_have_matching_viewports(self):
        result = self.capture([xaml_node("text", text="内容")], [uia_node("uia-text", "Text", "内容")],
                              uia_changes={"viewport": {"width": 1025, "height": 700, "scale": 1}})
        self.assertTrue(result["extraction_errors"])

    def test_unmeasured_overlay_mask_fails_closed(self):
        result = self.capture([xaml_node("text", text="内容")], [uia_node("uia-text", "Text", "内容")])
        # The fixture supplies no opaque mask; matching tree boxes cannot prove
        # visibility through overlapping surfaces.
        issues = result["extraction_errors"] + result["coverage"]["unmeasured"]
        self.assertTrue(any("occlusion" in str(issue).lower() or "mask" in str(issue).lower()
                            for issue in issues))

    def test_upstream_provider_errors_are_retained(self):
        result = self.capture([xaml_node("text", text="内容")], [uia_node("uia-text", "Text", "内容")],
                              uia_changes={"extraction_errors": ["uia-2: provider unavailable"]},
                              xaml_changes={"extraction_errors": ["xaml-3: unsupported brush"]})
        self.assertIn("uia-2: provider unavailable", result["extraction_errors"])
        self.assertIn("xaml-3: unsupported brush", result["extraction_errors"])

    def test_nullable_real_uia_control_type_is_a_gap_not_an_exception(self):
        unknown = uia_node("uia-unknown", name="内容")
        unknown["control_type"] = None
        result = self.capture([xaml_node("text", text="内容")], [unknown])
        self.assertTrue(any(issue.get("id") == "uia-unknown" and issue.get("property") == "UIA control_type"
                            for issue in result["coverage"]["unmeasured"]))

    def test_null_measured_rectangle_keeps_diagnostic_without_crashing(self):
        invalid = xaml_node("text", text="内容")
        invalid["bounds"]["x"] = None
        invalid["visible_bounds"]["x"] = None
        result = self.capture([invalid], [uia_node("uia-text", name="内容")],
                              xaml_changes={"extraction_errors": ["raw_nodes/0/bounds/x: Infinity"]})
        self.assertEqual(result["elements"], [])
        self.assertIn("raw_nodes/0/bounds/x: Infinity", result["extraction_errors"])

    def test_real_text_rectangles_and_uia_font_are_not_declared_font_fallback(self):
        text = xaml_node("text", text="内容")
        rectangles = [box(10, 20, 13, 18), box(23, 20, 13, 18)]
        text["layout"].update(character_boxes=rectangles, character_boxes_coordinate_space="content-window")
        witness = uia_node("uia-text", name="内容")
        witness["text_pattern"] = {"visible_ranges": [{
            "attributes": {"font_family": "Microsoft YaHei UI"},
            "attribute_status": {"font_family": "measured"}, "bounds": [box(10, 20, 26, 18)],
        }]}
        result = self.capture(measured([text]), [witness])
        element = self.by_id(result)["text"]
        self.assertEqual(element["evidence"]["text_bounds"], rectangles)
        self.assertEqual(element["style"]["rendered_fonts"][0]["family_name"], "Microsoft YaHei UI")
        self.assertIsNone(element["style"]["rendered_fonts"][0]["postscript_name"])
        self.assertNotEqual(element["style"]["rendered_fonts"][0]["family_name"], text["font_family"])

    def test_mixed_rich_run_typography_cannot_pass_as_one_uniform_font(self):
        text = xaml_node("text", text="标题正文")
        text["layout"]["rich_text_runs"] = [
            {"text": "标题", "font_size": 14, "font_weight": 700, "foreground": [27, 27, 26, 255]},
            {"text": "正文", "font_size": 13, "font_weight": 400, "foreground": [27, 27, 26, 255]},
        ]
        result = self.capture(measured([text]), [uia_node("uia-text", name="标题正文")])
        self.assertTrue(any(issue.get("property") == "rich_text_runs" for issue in result["coverage"]["unmeasured"]))

    @staticmethod
    def opaque(eid="cover", bounds=None, radius=0):
        cover = xaml_node(eid, "Border", bounds=bounds or box(0, 0, 200, 150))
        cover["style"].update(background=[255, 255, 255, 255], corner_radius=radius)
        return cover

    @staticmethod
    def occlusion_issues(result):
        return [issue for issue in result["coverage"]["unmeasured"]
                if "occlusion" in issue.get("property", "") or "curved_mask" in issue.get("property", "")]

    def test_opaque_later_rectangle_hides_element_and_its_uia_box(self):
        text = xaml_node("text", text="内容")
        nodes = measured([text, self.opaque()])
        result = self.capture(nodes, [uia_node("uia-text", name="内容")])
        self.assertNotIn("text", self.by_id(result))
        hidden = next(p for p in result["projection"] if p["source"] == "text")
        self.assertEqual(hidden["reason"], "fully occluded by measured opaque paint")
        self.assertEqual(hidden["occlusion_masks"][0]["source"], "cover")
        self.assertTrue(any(p["source"] == "uia-text" and "fully occluded" in p["reason"] for p in result["projection"]))
        self.assertFalse(self.occlusion_issues(result))

    def test_partial_occlusion_retains_element_and_remaining_fragment(self):
        text = xaml_node("text", text="内容", bounds=box(0, 10, 100, 20))
        result = self.capture(measured([text, self.opaque(bounds=box(50, 0, 100, 100))]),
                              [uia_node("uia-text", name="内容", bounds=text["bounds"])])
        actual = self.by_id(result)["text"]
        self.assertEqual(actual["bounds"], text["bounds"])
        self.assertEqual(actual["evidence"]["visible_fragments"], [box(0, 10, 50, 20)])
        self.assertTrue(actual["evidence"]["visible_fragments_are_envelopes"])
        self.assertFalse(self.occlusion_issues(result))

    def test_translucent_modal_dimmer_does_not_hide_underlying_content(self):
        nodes = measured([xaml_node("text", text="内容"), self.opaque()])
        nodes[1]["opacity"] = nodes[1]["style"]["opacity"] = .5
        result = self.capture(nodes, [uia_node("uia-text", name="内容")])
        self.assertIn("text", self.by_id(result))
        self.assertFalse(self.occlusion_issues(result))

    def test_paint_order_not_tree_array_order_decides_coverage(self):
        nodes = measured([xaml_node("text", text="内容"), self.opaque()])
        nodes[0]["paint_order"], nodes[1]["paint_order"] = 10, 2
        result = self.capture(nodes, [uia_node("uia-text", name="内容")])
        self.assertIn("text", self.by_id(result))

    def test_ancestor_background_does_not_occlude_own_descendant(self):
        surface = self.opaque()
        child = xaml_node("text", text="内容", parent="cover")
        result = self.capture(measured([surface, child]), [uia_node("uia-text", name="内容")])
        self.assertIn("text", self.by_id(result))
        self.assertFalse(self.occlusion_issues(result))

    def test_rounded_corner_keeps_visible_corner_and_exact_mask(self):
        text = xaml_node("text", text="角", bounds=box(0, 0, 3, 3))
        result = self.capture(measured([text, self.opaque(bounds=box(0, 0, 100, 100), radius=20)]),
                              [uia_node("uia-text", name="角", bounds=text["bounds"])])
        actual = self.by_id(result)["text"]
        self.assertEqual(actual["evidence"]["occlusion_masks"][0]["radii"][0], {"x": 20, "y": 20})
        self.assertFalse(self.occlusion_issues(result))

    def test_rounded_corner_containment_proves_hidden_rectangle(self):
        text = xaml_node("text", text="内", bounds=box(6, 10, 4, 4))
        result = self.capture(measured([text, self.opaque(bounds=box(0, 0, 100, 100), radius=20)]),
                              [uia_node("uia-text", name="内", bounds=text["bounds"])])
        self.assertNotIn("text", self.by_id(result))
        self.assertFalse(self.occlusion_issues(result))

    def test_curved_union_without_visibility_proof_keeps_gap(self):
        text = xaml_node("text", text="部分可见", bounds=box(0, 0, 100, 100))
        left = self.opaque("left", box(-50, 0, 100, 100), 50)
        right = self.opaque("right", box(50, 0, 100, 100), 50)
        left["visible_bounds"], right["visible_bounds"] = box(0, 0, 50, 100), box(50, 0, 50, 100)
        result = self.capture(measured([text, left, right]), [uia_node("uia-text", name="部分可见", bounds=text["bounds"])])
        self.assertIn("text", self.by_id(result))
        self.assertTrue(any(issue.get("property") == "visibility.curved_mask_union" and issue.get("id") == "text"
                            for issue in self.occlusion_issues(result)))

    def test_rotated_opaque_paint_is_not_treated_as_its_bounding_box(self):
        nodes = measured([xaml_node("text", text="内容"), self.opaque()])
        nodes[1]["axis_aligned_transform"] = False
        result = self.capture(nodes, [uia_node("uia-text", name="内容")])
        self.assertIn("text", self.by_id(result))
        self.assertTrue(self.occlusion_issues(result))


if __name__ == "__main__":
    unittest.main()
