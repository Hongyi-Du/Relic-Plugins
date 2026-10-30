"""Recorded-tree/image projection regressions; run in CI without UI or processes."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from windows_elements import (host_container_ownership, project, transformed_box_edges,
                              transparent_uia_ownership, uia_identity_rejection, measured_dialog_surfaces,
                              project_ellipse_border)
from windows_automation_identity import bind_automation_identities


SCENE = "zh-CN-light-1024x700-group"
VIEWPORT = {"width": 1024, "height": 700, "scale": 1}


def box(x=10, y=20, width=100, height=30):
    return {"x": x, "y": y, "width": width, "height": height}


def xaml_node(eid, typ="TextBlock", text="", parent=None, bounds=None, **changes):
    # Synthetic runtime receipts. Tests of absent/false proof explicitly replace
    # these fields; the production projector never infers them from class names.
    control = typ in {"Button", "AppBarButton", "RepeatButton", "TextBox", "ComposerInput", "NativeTextarea",
                      "SelectorBarItem", "ToggleButton", "ToggleSwitch", "ComboBox", "CheckBox", "RadioButton",
                      "PersonPicture", "ScrollBar", "Thumb", "ScrollViewer", "ContentDialog", "Expander",
                      "MenuFlyoutItem", "MenuFlyoutSubItem", "ToggleMenuFlyoutItem", "MenuBarItem",
                      "OverviewChipView", "OverviewBadgeView"}
    node = {
        "id": eid, "parent": parent, "type": typ, "region": "conversation",
        "text": text, "accessible_name": "", "bounds": bounds or box(),
        "visible_bounds": deepcopy(bounds or box()), "hidden_reason": None,
        "style": {"font_size": 13, "font_weight": 400, "foreground": [27, 27, 26, 255],
                  "background": [0, 0, 0, 0], "border_color": [0, 0, 0, 0],
                  "border_width": 0, "corner_radius": 0},
        "state": {"enabled": True, "selected": None, "checked": None,
                  "expanded": None, "focused": False, "hovered": False, "unread": None},
        "interaction_evidence": {"is_control": typ in {"Button", "TextBox", "SelectorBarItem", "ToggleButton"},
                                 "is_tab_stop": typ in {"Button", "TextBox", "SelectorBarItem", "ToggleButton"},
                                 "is_hit_test_visible": True},
        "render_type_evidence": {"is_control": control, "control_template_present": True if control else None},
        "layout": {"wrap": "none", "truncation": "none", "line_count": 1, "break_strategy_version": 1,
                   "normal_break_strategy": "none", "emergency_break_strategy": "none",
                   "line_break_configuration": {"source": "synthetic live WinUI enum fixture", "owner": eid,
                                                "raw": {"text_wrapping": "NoWrap", "text_wrapping_value": 1}}},
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
                  "focusable": control_type not in {"Text", "Image", "Separator", "Pane", "Group"},
                  "selected": None, "checked": None, "expanded": None},
        "value": None, "text_pattern": None, "supported_patterns": [],
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
    @staticmethod
    def recorded_ellipse_border():
        return json.loads((Path(__file__).parent / "fixtures" / "ellipse_border_recorded_0545cf0.json").read_text(encoding="utf-8"))

    @staticmethod
    def recorded_ellipse_circle():
        return json.loads((Path(__file__).parent / "fixtures" / "ellipse_circle_recorded_75fddb6.json").read_text(encoding="utf-8"))

    def test_recorded_ellipse_circle_uses_actual_stretch_and_centered_stroke_geometry(self):
        fixture = self.recorded_ellipse_circle()
        self.assertNotIn("reference", fixture)
        node = fixture["native"]
        original = deepcopy(node)
        viewport = {"width": 1440, "height": 900, "scale": 1}
        result = self.capture([node], [], xaml_changes={"viewport": viewport},
                              uia_changes={"viewport": viewport}, image_size=(1440, 900))
        element = self.by_id(result)[node["id"]]
        self.assertEqual(element["kind"], "state-dot")
        proof = element["evidence"]["ellipse_border"]
        self.assertTrue(proof["stroke_fields_measured"])
        self.assertTrue(proof["contour_measured"])
        self.assertEqual(proof["shape_geometry_evidence"], node["shape_geometry_evidence"])
        self.assertEqual(proof["geometry_derivation"]["centerline_radius"],
                         (node["shape_geometry_evidence"]["actual_width"] - node["stroke_evidence"]["raw_width"]) / 2)
        expected_outer = proof["geometry_derivation"]["centerline_radius"] + node["stroke_evidence"]["raw_width"] / 2
        self.assertEqual(element["style"]["corner_radius"], expected_outer)
        self.assertEqual(element["style"]["corner_radii"], [expected_outer] * 4)
        self.assertEqual(proof["geometry_derivation"]["outer_bounds"], node["bounds"])
        self.assertFalse(any(issue["id"] == node["id"] and issue["property"] == "style.corner_radius"
                             for issue in result["coverage"]["unmeasured"]))
        self.assertTrue(result["extraction_errors"], "Other missing scene/UIA measurements are not resolved by a circle radius")
        self.assertEqual(node, original)

    def test_circle_radius_changes_with_actual_inputs_in_both_supported_stretch_modes(self):
        # Synthetic variations of the recorded inputs exercise SDK geometry,
        # rather than hardcoding the fixture's ten-pixel state-dot diameter.
        for stretch, enum_value in (("Fill", 1), ("Uniform", 2)):
            for diameter, thickness in ((8, 1), (12, 2), (16.5, 1.25), (40, 6)):
                with self.subTest(stretch=stretch, diameter=diameter, thickness=thickness):
                    node = self.recorded_ellipse_circle()["native"]
                    x, y = node["bounds"]["x"], node["bounds"]["y"]
                    node["shape_geometry_evidence"].update(actual_width=diameter, actual_height=diameter,
                                                           stroke_thickness=thickness, stretch=stretch, stretch_value=enum_value)
                    for key in ("bounds", "visible_bounds", "local_bounds"):
                        node[key].update(width=diameter, height=diameter)
                    node["transformed_corners"] = [{"x": x, "y": y}, {"x": x + diameter, "y": y},
                                                    {"x": x + diameter, "y": y + diameter}, {"x": x, "y": y + diameter}]
                    node["stroke_evidence"].update(raw_width=thickness, source_extent={"x": diameter, "y": diameter},
                                                  axis_endpoint_x={"x": x + diameter, "y": y},
                                                  axis_endpoint_y={"x": x, "y": y + diameter})
                    node["style"]["stroke_width"] = thickness
                    element = {"style": deepcopy(node["style"]), "evidence": {}}
                    issues = []
                    project_ellipse_border(element, node, issues)
                    self.assertEqual(issues, [])
                    self.assertEqual(element["style"]["corner_radius"], diameter / 2)
                    contour = element["evidence"]["ellipse_border"]["geometry_derivation"]
                    self.assertEqual(contour["inner_radius"], diameter / 2 - thickness)
                    self.assertEqual(contour["centerline_bounds"]["x"], x + thickness / 2)

    def test_circle_missing_misbound_or_unsupported_actual_geometry_stays_unknown(self):
        changes = ("missing", "source", "owner", "runtime", "stretch-missing", "stretch-enum", "stretch-bool",
                   "stretch-none", "stretch-crop", "stroke-null", "thickness", "width-missing", "nonsquare",
                   "zero", "infinite", "float-rounding", "owner-id", "owner-paint", "composition", "children",
                   "local", "visible", "clip", "clip-missing", "hidden", "ancestor-missing", "ancestor-crop",
                   "extent", "origin", "endpoint", "axis-aligned", "scaled", "skewed", "dashed")
        for change in changes:
            with self.subTest(change=change):
                node = self.recorded_ellipse_circle()["native"]
                geometry = node["shape_geometry_evidence"]
                if change == "missing": node.pop("shape_geometry_evidence")
                elif change == "source": geometry["source"] = "estimated layout bounds"
                elif change == "owner": geometry["owner_id"] = "other-owner"
                elif change == "runtime": geometry["runtime_type"] = "Fixture.EllipseSubclass"
                elif change == "stretch-missing": geometry.pop("stretch")
                elif change == "stretch-enum": geometry["stretch_value"] = 2
                elif change == "stretch-bool": geometry["stretch_value"] = True
                elif change == "stretch-none": geometry.update(stretch="None", stretch_value=0)
                elif change == "stretch-crop": geometry.update(stretch="UniformToFill", stretch_value=3)
                elif change == "stroke-null": geometry["stroke_is_null"] = True
                elif change == "thickness": geometry["stroke_thickness"] = 3
                elif change == "width-missing": geometry.pop("actual_width")
                elif change == "nonsquare": geometry["actual_height"] = 12
                elif change == "zero": geometry.update(actual_width=0, actual_height=0)
                elif change == "infinite": geometry.update(actual_width=float("inf"), actual_height=float("inf"))
                elif change == "float-rounding": geometry.update(actual_width=10.1, actual_height=10.1)
                elif change == "owner-id": node["outline_owner_evidence"]["owner_id"] = "other-owner"
                elif change == "owner-paint": node["outline_owner_evidence"]["own_paint_contract"] = "unmeasured"
                elif change == "composition": node["outline_owner_evidence"]["composition"]["child_visual_present"] = True
                elif change == "children": node["outline_owner_evidence"]["children"]["complete"] = False
                elif change == "local": node["local_bounds"]["x"] = 1
                elif change == "visible": node["visible_bounds"]["width"] = 9
                elif change == "clip": node["clip"] = {"x": 1, "y": 0, "width": 9, "height": 10}
                elif change == "clip-missing": node.pop("clip")
                elif change == "hidden": node["hidden_reason"] = "collapsed"
                elif change == "ancestor-missing": node.pop("ancestor_clip")
                elif change == "ancestor-crop": node["ancestor_clip"]["height"] = 75
                elif change == "extent": node["stroke_evidence"]["source_extent"]["x"] = 9
                elif change == "origin": node["stroke_evidence"]["origin"]["x"] += 1
                elif change == "endpoint": node["stroke_evidence"]["axis_endpoint_x"]["x"] += 1
                elif change == "axis-aligned": node["axis_aligned_transform"] = False
                elif change == "scaled": node["transform"]["m11"] = 2
                elif change == "skewed": node["transform"]["m21"] = 0.1
                elif change == "dashed": node["stroke_evidence"]["raw_pattern"]["dash_array"] = [1, 1]
                element = {"style": deepcopy(node["style"]), "evidence": {}}
                issues = []
                project_ellipse_border(element, node, issues)
                self.assertIsNone(element["style"]["corner_radius"])
                self.assertIsNone(element["style"]["corner_radii"])
                self.assertFalse(element["evidence"]["ellipse_border"]["contour_measured"])
                self.assertTrue(any(issue["property"] == "style.corner_radius" for issue in issues))

    def test_circle_degenerate_inner_contour_or_stroke_stays_unknown(self):
        for thickness in (0, 5, 10, 12):
            with self.subTest(thickness=thickness):
                node = self.recorded_ellipse_circle()["native"]
                node["shape_geometry_evidence"]["stroke_thickness"] = thickness
                node["stroke_evidence"]["raw_width"] = thickness
                node["style"]["stroke_width"] = thickness
                element = {"style": deepcopy(node["style"]), "evidence": {}}
                issues = []
                project_ellipse_border(element, node, issues)
                self.assertIsNone(element["style"]["corner_radius"])
                self.assertTrue(any(issue["property"] == "style.corner_radius" for issue in issues))

    def test_circle_radius_projection_preserves_other_coverage_errors_and_raw_inputs(self):
        node = self.recorded_ellipse_circle()["native"]
        original = deepcopy(node)
        issues = [{"id": node["id"], "property": "frame", "reason": "independent unresolved frame evidence"}]
        before = deepcopy(issues)
        element = {"style": deepcopy(node["style"]), "evidence": {}}
        project_ellipse_border(element, node, issues)
        self.assertEqual(issues, before)
        self.assertEqual(node, original)
        self.assertEqual(element["evidence"]["ellipse_border"]["raw_style"], original["style"])
        self.assertEqual(element["evidence"]["ellipse_border"]["shape_geometry_evidence"], original["shape_geometry_evidence"])

    def test_recorded_header_state_dot_maps_actual_stroke_without_claiming_unknown_radius(self):
        fixture = self.recorded_ellipse_border()
        node, reference = fixture["native"], fixture["reference"]
        original = deepcopy(node)
        viewport = {"width": 1440, "height": 900, "scale": 1}
        result = self.capture([node], [], xaml_changes={"viewport": viewport},
                              uia_changes={"viewport": viewport}, image_size=(1440, 900))
        element = self.by_id(result)[node["id"]]
        self.assertEqual(element["kind"], "state-dot")
        for field in ("background", "border_color", "border_width", "border_widths", "border_colors", "border_styles"):
            self.assertEqual(element["style"][field], reference["style"][field])
        self.assertEqual(element["style"]["foreground"], node["style"]["foreground"])
        self.assertEqual(element["style"]["stroke_width"], node["style"]["stroke_width"])
        self.assertIsNone(element["style"]["corner_radius"])
        self.assertIsNone(element["style"]["corner_radii"])
        proof = element["evidence"]["ellipse_border"]
        self.assertTrue(proof["stroke_fields_measured"])
        self.assertFalse(proof["contour_measured"])
        self.assertEqual(proof["raw_style"], node["style"])
        self.assertTrue(any(issue["id"] == node["id"] and issue["property"] == "style.corner_radius"
                            for issue in result["coverage"]["unmeasured"]))
        self.assertTrue(result["extraction_errors"], "This isolated recorded node is not a complete independent UIA scene")
        self.assertEqual(node, original)

    def test_ellipse_border_does_not_fill_a_transparent_interior(self):
        node = self.recorded_ellipse_border()["native"]
        node["style"]["background"] = [0, 0, 0, 0]
        node["style"]["brush_evidence"]["background"]["solid_rgba"] = [0, 0, 0, 0]
        element = {"style": deepcopy(node["style"]), "evidence": {}}
        issues = []
        project_ellipse_border(element, node, issues)
        self.assertEqual(element["style"]["background"], [0, 0, 0, 0])
        self.assertEqual(element["style"]["border_color"], [255, 255, 255, 255])
        self.assertTrue(issues, "Missing actual contour remains a failure even when stroke fields are known")

    def test_nonellipse_path_line_rectangle_and_font_glyph_keep_their_own_stroke_meaning(self):
        for typ in ("Path", "Line", "Polyline", "Rectangle", "FontIcon", "ReferenceVectorIcon"):
            with self.subTest(type=typ):
                node = self.recorded_ellipse_border()["native"]
                node["type"] = typ
                element = {"style": deepcopy(node["style"]), "evidence": {}}
                original = deepcopy(element)
                issues = []
                project_ellipse_border(element, node, issues)
                self.assertEqual(element, original)
                self.assertEqual(issues, [])

    def test_missing_or_unsupported_ellipse_stroke_cannot_be_declared_a_css_border(self):
        for change in ("runtime", "primitive", "brush", "color", "opacity", "stroke", "source", "width", "basis", "scale", "matrix", "dash"):
            with self.subTest(change=change):
                node = self.recorded_ellipse_border()["native"]
                if change == "runtime": node["render_type_evidence"]["is_shape"] = None
                elif change == "primitive": node["paint_kind"] = "path"
                elif change == "brush": node["style"]["brush_evidence"]["foreground"]["type"] = "Microsoft.UI.Xaml.Media.LinearGradientBrush"
                elif change == "color": node["style"]["brush_evidence"]["foreground"]["solid_rgba"] = [0, 0, 0, 255]
                elif change == "opacity": node["style"]["brush_evidence"]["foreground"]["opacity"] = None
                elif change == "stroke": node.pop("stroke_evidence")
                elif change == "source": node["stroke_evidence"]["source"] = "guessed boundary"
                elif change == "width": node["style"]["stroke_width"] = 3
                elif change == "basis": node["stroke_evidence"]["basis_x"]["y"] = 1
                elif change == "scale": node["stroke_evidence"]["scale_y"] = 2
                elif change == "matrix": node["transform"]["m11"] = 2
                elif change == "dash": node["stroke_evidence"]["raw_pattern"]["dash_array"] = [1, 1]
                element = {"style": deepcopy(node["style"]), "evidence": {}}
                issues = []
                project_ellipse_border(element, node, issues)
                self.assertIsNone(element["style"]["border_color"])
                self.assertIsNone(element["style"]["border_width"])
                self.assertFalse(element["evidence"]["ellipse_border"]["stroke_fields_measured"])
                self.assertTrue(any(issue["property"] == "style.ellipse_border" for issue in issues))

    def test_absent_ellipse_stroke_is_not_replaced_by_fill_or_reference_border(self):
        node = self.recorded_ellipse_border()["native"]
        node["style"]["brush_evidence"]["foreground"] = {"type": None, "opacity": None, "solid_rgba": [0, 0, 0, 0]}
        node["style"]["foreground"] = [0, 0, 0, 0]
        element = {"style": deepcopy(node["style"]), "evidence": {}}
        original = deepcopy(element)
        project_ellipse_border(element, node, [])
        self.assertEqual(element, original)

    def capture(self, nodes, uia_nodes=None, *, xaml_changes=None, uia_changes=None,
                image_size=None, text_probe=None):
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
            if text_probe is not None:
                (root / "scene.text-range-provider-probe.json").write_text(json.dumps(text_probe), encoding="utf-8")
            Image.new("RGBA", image_size or (1024, 700), (248, 247, 245, 255)).save(root / "scene.png")
            return project(root / "scene.xaml.json", root / "scene.uia.json", root / "scene.png")

    @staticmethod
    def by_id(result):
        return {element["id"]: element for element in result["elements"]}

    @staticmethod
    def recorded_menu_group():
        return json.loads((Path(__file__).parent / "fixtures" / "menu_group_identity_recorded_75fddb6.json").read_text(encoding="utf-8"))

    def project_recorded_menu_group(self, fixture):
        xaml, uia = fixture["xaml"], fixture["uia"]
        return self.capture(xaml["raw_nodes"], uia["raw_nodes"], xaml_changes=xaml,
                            uia_changes=uia, image_size=(1440, 900))

    def test_recorded_full_identity_group_keeps_menu_region_and_actual_child(self):
        fixture = self.recorded_menu_group()
        result = self.project_recorded_menu_group(fixture)
        elements = self.by_id(result)
        menu, child = elements["xaml-28"], elements["xaml-29"]
        actual_owner = fixture["xaml"]["raw_nodes"][0]
        actual_provider = fixture["uia"]["raw_nodes"][0]
        self.assertEqual(menu["kind"], "region")
        self.assertEqual(menu["name"], actual_provider["name"])
        self.assertEqual(menu["bounds"], actual_owner["bounds"])
        self.assertEqual(menu["parent"], actual_owner["parent"])
        self.assertEqual(menu["region"], actual_owner["region"])
        self.assertEqual(menu["evidence"]["uia_id"], "uia-9")
        self.assertEqual(menu["evidence"]["uia_group_region"]["runtime_id"], [42, 131466, 4, 6])
        self.assertEqual(child["parent"], menu["id"])
        self.assertEqual(child["kind"], "button")
        self.assertEqual(child["name"], fixture["uia"]["raw_nodes"][1]["name"])
        self.assertLess(menu["order"], child["order"])
        # The scoped fixture intentionally omits other paint/ancestor evidence.
        # Proving this role cannot resolve those independent coverage failures.
        self.assertTrue(result["coverage"]["unmeasured"])

    def test_group_role_requires_unique_complete_actual_owner_identity(self):
        cases = ("missing", "no-peer", "different-runtime-id", "duplicate-provider",
                 "duplicate-owner", "different-role", "foreign-observer", "failed-release")
        for case in cases:
            with self.subTest(case=case):
                fixture = self.recorded_menu_group()
                owner = fixture["xaml"]["raw_nodes"][0]
                provider = fixture["uia"]["raw_nodes"][0]
                if case == "missing":
                    owner.pop("automation_identity_evidence")
                elif case == "no-peer":
                    owner["automation_identity_evidence"].update(status="no-peer", peer_is_null=True)
                elif case == "different-runtime-id":
                    provider["runtime_id"] = "42.131466.4.999"
                elif case == "duplicate-provider":
                    duplicate = deepcopy(provider)
                    duplicate["id"] = "synthetic-duplicate-provider"
                    fixture["uia"]["raw_nodes"].append(duplicate)
                elif case == "duplicate-owner":
                    duplicate = deepcopy(owner)
                    duplicate["id"] = "synthetic-duplicate-owner"
                    duplicate["automation_identity_evidence"].update(
                        owner_id=duplicate["id"], peer_owner_id=duplicate["id"])
                    fixture["xaml"]["raw_nodes"].append(duplicate)
                elif case == "different-role":
                    provider["control_type"] = "ControlType.Pane"
                elif case == "foreign-observer":
                    fixture["uia"]["observer_hold"]["observer_pid"] += 1
                elif case == "failed-release":
                    fixture["uia"]["observer_hold"]["release"]["status"] = "failed"
                result = self.project_recorded_menu_group(fixture)
                self.assertNotIn("xaml-28", self.by_id(result))
                self.assertTrue(any(record["source"] == "xaml-28"
                                    and record["reason"].startswith("layout wrapper")
                                    for record in result["projection"]))

    def test_group_identity_not_name_or_geometry_selects_provider_and_keeps_errors(self):
        fixture = self.recorded_menu_group()
        provider = fixture["uia"]["raw_nodes"][0]
        decoy = deepcopy(provider)
        decoy.update(id="synthetic-geometry-decoy", runtime_id="42.131466.4.999")
        fixture["uia"]["raw_nodes"].append(decoy)
        # Synthetic variation of the recorded receipt: only the complete owner
        # identity may choose a provider, even when another name/box is closer.
        provider["name"] = "Synthetic actual-provider name"
        provider["bounds"]["x"] += 20
        fixture["uia"]["extraction_errors"].append("Synthetic independent provider failure")
        result = self.project_recorded_menu_group(fixture)
        menu = self.by_id(result)["xaml-28"]
        self.assertEqual(menu["name"], provider["name"])
        self.assertEqual(menu["bounds"], fixture["xaml"]["raw_nodes"][0]["bounds"])
        self.assertEqual(menu["evidence"]["uia_id"], "uia-9")
        self.assertIn("Synthetic independent provider failure", result["extraction_errors"])

    @staticmethod
    def recorded_dialog_identity():
        return json.loads((Path(__file__).parent / "fixtures" / "dialog_identity_recorded_2e42376.json").read_text(encoding="utf-8"))

    def test_recorded_dialog_no_peer_cannot_borrow_scrollviewer_provider(self):
        fixture = self.recorded_dialog_identity()
        xaml, uia = fixture["xaml"], fixture["uia"]
        result = self.capture(xaml["raw_nodes"], uia["raw_nodes"], xaml_changes=xaml,
                              uia_changes=uia, image_size=(1440, 900))
        elements = self.by_id(result)
        # The new identity constraint does not fix the separate dialog paint/
        # geometry problem, remove authored content, or invent a replacement peer.
        self.assertEqual(elements["xaml-1192"]["bounds"], box(0, 0, 1440, 900))
        self.assertEqual(elements["xaml-1192"]["kind"], "card")
        self.assertEqual(elements["xaml-1192"]["evidence"]["uia_id"], "uia-6")
        self.assertEqual(elements["xaml-1205"]["bounds"], box(260, 130, 920, 640))
        self.assertIsNone(elements["xaml-1205"]["evidence"]["uia_id"])
        pairs = result["capture_evidence"]["automation_identity_bindings"]["pairs"]
        self.assertIn(("xaml-1197", "uia-7"), [(p["xaml_id"], p["uia_id"]) for p in pairs])
        rejected = result["capture_evidence"]["uia_pairing_rejections"]
        self.assertTrue(any(p["xaml_id"] == "xaml-1205" and p["uia_id"] == "uia-7" for p in rejected))
        self.assertTrue(any(p["id"] == "uia-7" and p["property"] == "render correspondence"
                            for p in result["coverage"]["unmeasured"]))
        for error in xaml["extraction_errors"]:
            self.assertIn(error, result["extraction_errors"])
        # The independently observed no-peer receipt is still unresolved by the
        # positive RuntimeId binder; rejecting a false match does not erase it.
        self.assertTrue(any(p["xaml_id"] == "xaml-1205" for p in
                            result["capture_evidence"]["automation_identity_bindings"]["unresolved"]))

    def test_recorded_unique_provider_is_reserved_even_when_other_owner_identity_is_unknown(self):
        fixture = self.recorded_dialog_identity()
        raw, uia = fixture["xaml"]["raw_nodes"], fixture["uia"]
        bindings = bind_automation_identities(raw, uia)
        owner_by_provider = {p["uia_id"]: p["xaml_id"] for p in bindings["pairs"]}
        provider_by_owner = {p["xaml_id"]: p["uia_id"] for p in bindings["pairs"]}
        nodes = {n["id"]: n for n in raw}
        # Counterfactual variants are explicit: the recorded input remains intact.
        unknown = deepcopy(nodes["xaml-1205"])
        unknown.pop("automation_identity_evidence")
        self.assertIn("another actual XAML owner: xaml-1197",
                      uia_identity_rejection(unknown, "uia-7", owner_by_provider, provider_by_owner))
        # Exercise the actual projector as well: losing this Grid's negative
        # receipt cannot make an already-owned ScrollViewer provider borrowable.
        fixture["xaml"]["raw_nodes"] = [unknown if n["id"] == unknown["id"] else n for n in raw]
        result = self.capture(fixture["xaml"]["raw_nodes"], uia["raw_nodes"],
                              xaml_changes=fixture["xaml"], uia_changes=uia, image_size=(1440, 900))
        self.assertIsNone(self.by_id(result)["xaml-1205"]["evidence"]["uia_id"])
        self.assertTrue(any(p["xaml_id"] == "xaml-1205" and p["uia_id"] == "uia-7"
                            and "another actual XAML owner: xaml-1197" in p["reason"]
                            for p in result["capture_evidence"]["uia_pairing_rejections"]))
        self.assertIsNone(uia_identity_rejection(nodes["xaml-1197"], "uia-7", owner_by_provider, provider_by_owner))
        self.assertIsNone(uia_identity_rejection(nodes["xaml-1192"], "uia-6", owner_by_provider, provider_by_owner))
        for eid in ("xaml-1195", "xaml-1205"):
            self.assertIn("no AutomationPeer", uia_identity_rejection(nodes[eid], "uia-7", {}, {}))
        # An actual known owner cannot borrow an otherwise-unclaimed provider,
        # even when its name and layout rectangle are a perfect heuristic match.
        self.assertIn("another independent provider: uia-7",
                      uia_identity_rejection(nodes["xaml-1197"], "unclaimed", owner_by_provider, provider_by_owner))
        self.assertIsNone(uia_identity_rejection(unknown, "unclaimed", {}, {}))

    def test_no_peer_rejection_keeps_provider_errors_and_unknown_owner_fallback(self):
        receipt = deepcopy(next(n for n in self.recorded_dialog_identity()["xaml"]["raw_nodes"]
                                if n["id"] == "xaml-1205")["automation_identity_evidence"])
        receipt["owner_id"] = "synthetic-button"
        button = xaml_node("synthetic-button", "Button", automation_identity_evidence=receipt)
        provider = uia_node("provider", "Button")
        error = "Original independently observed provider transport failure"
        rejected = self.capture(measured([button]), [provider], uia_changes={"extraction_errors": [error]})
        self.assertIsNone(self.by_id(rejected)["synthetic-button"]["evidence"]["uia_id"])
        self.assertIn(error, rejected["extraction_errors"])
        self.assertTrue(any(p["id"] == "provider" and p["property"] == "render correspondence"
                            for p in rejected["coverage"]["unmeasured"]))
        button.pop("automation_identity_evidence")
        unknown = self.capture(measured([button]), [provider])
        self.assertEqual(self.by_id(unknown)["synthetic-button"]["evidence"]["uia_id"], "provider")
        self.assertEqual(unknown["capture_evidence"]["uia_pairing_rejections"], [])

    def test_native_content_dialog_keeps_existing_card_geometry_until_surface_projection(self):
        dialog = xaml_node("dialog", "NativeContentDialog", bounds=box(0, 0, 300, 200),
                           render_type_evidence={"is_control": True, "control_template_present": True})
        result = self.capture(measured([dialog]), [uia_node("provider", "Group", bounds=dialog["bounds"])])
        self.assertEqual(self.by_id(result)["dialog"]["kind"], "card")
        self.assertEqual(self.by_id(result)["dialog"]["bounds"], dialog["bounds"])

    @staticmethod
    def recorded_dialog_surface():
        return json.loads((Path(__file__).parent / "fixtures" / "dialog_surface_recorded_e5f092b.json").read_text(encoding="utf-8"))

    def test_recorded_dialog_projects_actual_surface_but_keeps_host_identity_and_independent_paint(self):
        fixture = self.recorded_dialog_surface()
        xaml, uia = fixture["xaml"], fixture["uia"]
        raw = {n["id"]: n for n in xaml["raw_nodes"]}
        original = deepcopy(xaml)
        result = self.capture(xaml["raw_nodes"], uia["raw_nodes"], xaml_changes=xaml,
                              uia_changes=uia, image_size=(1440, 900))
        elements = self.by_id(result)
        dialog = elements["xaml-1192"]
        self.assertEqual(dialog["kind"], "region")
        self.assertEqual(dialog["name"], "设置")
        self.assertEqual(dialog["text"], "")
        self.assertEqual(dialog["bounds"], raw["xaml-1195"]["bounds"])
        self.assertEqual(dialog["visible_bounds"], raw["xaml-1195"]["visible_bounds"])
        self.assertEqual(dialog["evidence"]["uia_id"], "uia-6")
        self.assertEqual(dialog["evidence"]["paint_sources"], ["xaml-1195"])
        # The authored opaque content is a true descendant of the surface.
        # It must not erase the ancestor modal region's semantic visibility.
        self.assertEqual(dialog["evidence"]["visible_fragments"], [raw["xaml-1195"]["visible_bounds"]])
        self.assertNotIn("xaml-1205", [mask["source"] for mask in dialog["evidence"]["occlusion_masks"]])
        proof = dialog["evidence"]["dialog_surface"]
        self.assertFalse(proof["host_layout_projected_as_paint"])
        self.assertEqual(proof["host"]["bounds"], box(0, 0, 1440, 900))
        self.assertEqual(proof["host"]["uia_bounds"], box(0, 0, 1440, 900))
        self.assertEqual(proof["surface"]["raw"], raw["xaml-1195"])
        self.assertEqual(proof["template_receipt"], raw["xaml-1192"]["dialog_surface_evidence"])
        self.assertFalse(proof["other_template_paint_and_authored_content_merged"])
        self.assertFalse(proof["smoke_layer_merged"])
        self.assertNotIn("xaml-1195", elements)
        # These are actual separate white layers and an independently hosted
        # smoke layer; matching bounds do not license their disappearance.
        for eid in ("xaml-1201", "xaml-1205", "xaml-1425"):
            self.assertIn(eid, elements)
            self.assertEqual(elements[eid]["style"]["background"], raw[eid]["style"]["background"])
        self.assertIsNone(elements["xaml-1205"]["evidence"]["uia_id"])
        self.assertIsNone(dialog["style"]["shadow"])
        self.assertIsNone(dialog["style"]["outline"])
        self.assertTrue(any(issue["id"] == "xaml-1192" and issue["property"] == "style.shadow"
                            for issue in result["coverage"]["unmeasured"]))
        self.assertTrue(any(issue["id"] == "xaml-1195" and issue["property"] == "style.outline"
                            for issue in result["coverage"]["unmeasured"]))
        for error in xaml["extraction_errors"]:
            self.assertIn(error, result["extraction_errors"])
        self.assertEqual(xaml, original)

    def test_dialog_surface_binding_rejects_changed_template_parts_paths_and_authored_content(self):
        for change in ("missing", "source", "owner", "revision", "boolean-revision", "thread", "template",
                       "part-reference", "part-type", "part-error", "part-id", "path", "path-id", "raw-parent", "path-cycle",
                       "authored-surface", "authored-owner", "authored-id", "missing-bounds"):
            with self.subTest(change=change):
                raw = self.recorded_dialog_surface()["xaml"]["raw_nodes"]
                by_id = {n["id"]: n for n in raw}
                owner = by_id["xaml-1192"]
                proof = owner["dialog_surface_evidence"]
                part = proof["parts"]["BackgroundElement"]
                if change == "missing": owner.pop("dialog_surface_evidence")
                elif change == "source": proof["source"] = "inferred named descendant"
                elif change == "owner": proof["owner_id"] = "another-owner"
                elif change == "revision": proof["template_revision_after"] += 1
                elif change == "boolean-revision": proof["template_revision"] = proof["template_revision_after"] = True
                elif change == "thread": proof["ui_thread_access"] = False
                elif change == "template": proof["same_applied_template_reference_after"] = False
                elif change == "part-reference": part["same_applied_part_reference"] = False
                elif change == "part-type": part["runtime_type"] = "Microsoft.UI.Xaml.Controls.Grid"
                elif change == "part-error": part["error"] = "actual GetTemplateChild failure"
                elif change == "part-id": part["id"] = ["xaml-1195"]
                elif change == "path": part["actual_parent_path_to_owner"][0]["id"] = "xaml-1205"
                elif change == "path-id": part["actual_parent_path_to_owner"][0]["id"] = ["xaml-1195"]
                elif change == "raw-parent": by_id["xaml-1195"]["parent"] = "xaml-1193"
                elif change == "path-cycle": part["actual_parent_path_to_owner"].insert(1, deepcopy(part["actual_parent_path_to_owner"][0]))
                elif change == "authored-surface": proof["authored_content_id"] = "xaml-1195"
                elif change == "authored-owner": by_id["xaml-1205"]["declared_content_owner"] = "other-dialog"
                elif change == "authored-id": proof["authored_content_id"] = ["xaml-1205"]
                elif change == "missing-bounds": by_id["xaml-1195"]["bounds"] = None
                issues = []
                self.assertEqual(measured_dialog_surfaces(raw, by_id, issues), {})
                self.assertTrue(any(issue["id"] == "xaml-1192" and issue["property"] == "dialog.surface" for issue in issues))

    def test_unproven_surface_does_not_consume_real_border_or_use_same_geometry_authored_grid(self):
        fixture = self.recorded_dialog_surface()
        xaml, uia = fixture["xaml"], fixture["uia"]
        raw = {n["id"]: n for n in xaml["raw_nodes"]}
        raw["xaml-1192"]["dialog_surface_evidence"]["parts"]["BackgroundElement"]["id"] = "xaml-1205"
        result = self.capture(xaml["raw_nodes"], uia["raw_nodes"], xaml_changes=xaml,
                              uia_changes=uia, image_size=(1440, 900))
        elements = self.by_id(result)
        self.assertEqual(elements["xaml-1192"]["bounds"], raw["xaml-1192"]["bounds"])
        self.assertNotIn("dialog_surface", elements["xaml-1192"]["evidence"])
        self.assertIn("xaml-1195", elements)
        self.assertIn("xaml-1205", elements)
        self.assertTrue(any(issue["property"] == "dialog.surface" for issue in result["coverage"]["unmeasured"]))

    def test_precision_diagnostic_does_not_replace_bounds_or_erase_provider_errors(self):
        nodes = measured([xaml_node("text", text="Actual captured source")])
        failure = "Observed zero-area native COM text rectangle"
        kwargs = {"uia_changes": {"extraction_errors": [failure]}}
        baseline = self.capture(nodes, **kwargs)
        result = self.capture(nodes, text_probe={"source": "unbound probe", "owners": [], "errors": []}, **kwargs)
        for field in ("elements", "extraction_errors", "coverage", "projection", "nonvisible_diagnostics"):
            self.assertEqual(result[field], baseline[field])
        diagnostic = result["capture_evidence"]["text_range_precision"]
        self.assertFalse(diagnostic["canonical_geometry_supplied"])
        self.assertFalse(diagnostic["provider_errors_resolved"])
        self.assertEqual(diagnostic["original_uia_errors"], [failure])
        self.assertTrue(diagnostic["unresolved"])

    def test_malformed_optional_precision_diagnostic_keeps_original_capture(self):
        nodes = measured([xaml_node("text", text="Original")])
        baseline = self.capture(nodes)
        for malformed in ([], "not an object"):
            result = self.capture(nodes, text_probe=malformed)
            for field in ("elements", "extraction_errors", "coverage", "projection"):
                self.assertEqual(result[field], baseline[field])
            diagnostic = result["capture_evidence"]["text_range_precision"]
            self.assertEqual(diagnostic["status"], "unavailable")
            self.assertFalse(diagnostic["provider_errors_resolved"])

    def test_actual_region_grid_preserves_each_independent_child_paint(self):
        region = xaml_node("region", "NativeRegionGrid", bounds=box(0, 0, 400, 200),
                           render_type_evidence={"is_panel": True, "is_control": False, "control_template_present": None})
        card = xaml_node("card", "Border", parent="region", bounds=box(10, 10, 140, 80))
        grid = xaml_node("grid", "Grid", parent="region", bounds=box(170, 10, 140, 80))
        for painted_node in (card, grid): painted_node["style"]["background"] = [240, 238, 235, 255]
        result = self.capture(measured([region, card, grid]), [uia_node("uia-region", "Group", bounds=region["bounds"])])
        self.assertEqual(set(self.by_id(result)), {"region", "card", "grid"})
        self.assertEqual(self.by_id(result)["region"]["kind"], "region")
        self.assertFalse(any(row.get("reason") == "semantic control template paint" for row in result["projection"]))

    def test_missing_or_absent_real_control_template_never_owns_child_paint(self):
        for proof in (None, {}, {"is_control": True}, {"is_control": True, "control_template_present": False}):
            with self.subTest(proof=proof):
                owner = xaml_node("button", "Button", render_type_evidence=proof)
                paint = xaml_node("paint", "Border", parent="button")
                paint["style"]["background"] = [240, 238, 235, 255]
                result = self.capture(measured([owner, paint]), [uia_node("uia-button", "Button")])
                self.assertIn("paint", self.by_id(result))
                self.assertEqual(self.by_id(result)["button"]["evidence"]["render_type_evidence"], proof)
                if not isinstance(proof, dict) or proof.get("control_template_present") is not False:
                    self.assertTrue(any(row.get("id") == "button" and row["property"] == "template.paint_ownership"
                                        for row in result["coverage"]["unmeasured"]))

    def test_real_scrollviewer_template_owns_template_paint_but_keeps_declared_content_paint(self):
        owner = xaml_node("viewer", "ScrollViewer", bounds=box(0, 0, 300, 200),
                          region_container_evidence={"source": "actual MainWindow.chatScroll object identity"})
        template = xaml_node("template", "Border", parent="viewer", bounds=owner["bounds"])
        content = xaml_node("content", "Border", parent="template", bounds=box(10, 10, 100, 100),
                            declared_content_owner="viewer", declared_content_source="ContentControl.Content")
        template["style"]["background"] = [248, 247, 245, 255]
        content["style"]["background"] = [230, 225, 220, 255]
        result = self.capture(measured([owner, template, content]), [uia_node("uia-viewer", "Pane", bounds=owner["bounds"])])
        self.assertNotIn("template", self.by_id(result))
        self.assertIn("content", self.by_id(result))
        self.assertTrue(any(row.get("source") == "template" and row.get("owner") == "viewer" for row in result["projection"]))

    def test_person_picture_measured_background_ownership_is_independent_of_template_proof(self):
        avatar = xaml_node("avatar", "PersonPicture", render_type_evidence=None)
        background = xaml_node("avatar-background", "Border", parent="avatar")
        background["style"]["background"] = [230, 225, 220, 255]
        result = self.capture(measured([avatar, background]), [uia_node("uia-avatar", "Image")])
        self.assertNotIn("avatar-background", self.by_id(result))
        self.assertEqual(self.by_id(result)["avatar"]["evidence"]["paint_sources"], ["avatar-background"])
        self.assertFalse(any(row["property"] == "template.paint_ownership" for row in result["coverage"]["unmeasured"]))

    def test_native_region_runtime_types_keep_region_with_painted_panel_and_real_provider(self):
        for typ, provider_type in (("NativeRegionGrid", "Group"), ("ScrollViewer", "Pane")):
            with self.subTest(typ=typ):
                region = measured([xaml_node("region", typ, accessible_name="Conversation", bounds=box(20, 20, 300, 400),
                                             render_type_evidence={"is_panel": typ == "NativeRegionGrid"})])[0]
                region["style"]["background"] = [250, 250, 250, 255]
                if typ == "ScrollViewer":
                    region["region_container_evidence"] = {"source": "actual MainWindow.chatScroll object identity", "owner_type": "MainWindow"}
                result = self.capture([region], [uia_node("uia-region", provider_type, name="Conversation", bounds=region["bounds"])])
                self.assertEqual(self.by_id(result)["region"]["kind"], "region")
                self.assertEqual(self.by_id(result)["region"]["evidence"]["uia_id"], "uia-region")
                missing = self.capture([region])
                self.assertTrue(any(row.get("id") == "region" and row["property"] == "UIA correspondence"
                                    for row in missing["coverage"]["unmeasured"]))
                if typ == "ScrollViewer":
                    region.pop("region_container_evidence")
                    ordinary = self.capture([region], [uia_node("uia-region", "Pane", name="Conversation", bounds=region["bounds"])])
                    self.assertNotIn("region", self.by_id(ordinary))
                    self.assertTrue(any(row.get("id") == "uia-region" and row["property"] == "render correspondence"
                                        for row in ordinary["coverage"]["unmeasured"]))

    @staticmethod
    def scrollbar_fixture():
        bar = xaml_node("scrollbar", "ScrollBar", bounds=box(400, 30, 10, 200),
                        interaction_evidence={"is_control": True, "is_tab_stop": False, "is_hit_test_visible": True})
        root = xaml_node("scroll-template", "Grid", parent="scrollbar", bounds=bar["bounds"])
        thumb = xaml_node("scroll-thumb", "Thumb", parent="scroll-template", bounds=box(400, 62, 10, 50),
                          interaction_evidence={"is_control": True, "is_tab_stop": False, "is_hit_test_visible": True})
        paint = xaml_node("thumb-paint", "Border", parent="scroll-thumb", bounds=thumb["bounds"])
        unrelated = xaml_node("panel-drag", "Thumb", bounds=box(270, 40, 5, 500), name="VerticalThumb",
                              automation_id="VerticalThumb")
        nodes = measured([bar, root, thumb, paint, unrelated])
        for node in nodes[1:4]: node["render_sibling_order"] = 0
        nodes[0]["paint_kind"] = nodes[2]["paint_kind"] = "template"
        nodes[3]["background_sizing"] = "InnerBorderEdge"
        nodes[3]["style"].update(background=[143, 140, 134, 89.25], border_width=3,
                                  border_widths=[3, 3, 3, 3], corner_radius=8, corner_radii=[8, 8, 8, 8])
        edges = [{"id": eid, "parent_id": parent, "child_index": 0,
                  "same_parent_object": True, "captured_parent_matches": True}
                 for eid, parent in (("scroll-template", "scrollbar"), ("scroll-thumb", "scroll-template"),
                                     ("thumb-paint", "scroll-thumb"))]
        nodes[0]["scrollbar_evidence"] = {
            "source": "actual ScrollBar runtime properties and current visual subtree", "complete": True,
            "template_present": True, "orientation": "vertical",
            "range": {"minimum": 0, "maximum": 100, "value": 25, "viewport_size": 80,
                      "small_change": 0.1, "large_change": 1},
            "template_roots": ["scroll-template"], "visual_subtree": edges,
            "thumb_ids": ["scroll-thumb"], "paint_ids": ["scroll-template", "thumb-paint"]}
        nodes[2]["scrollbar_thumb_evidence"] = {
            "source": "actual Thumb visual ancestry to ScrollBar and current template subtree identities",
            "complete": True, "owner_id": "scrollbar", "path": deepcopy(edges[:2]), "dragging": False}
        providers = [uia_node("uia-bar", "ScrollBar", bounds=bar["bounds"],
                              range_value={"minimum": 0, "maximum": 100, "value": 25},
                              supported_patterns=["RangeValuePatternIdentifiers.Pattern"]),
                     uia_node("uia-thumb", "Thumb", parent="uia-bar", bounds=thumb["bounds"]),
                     uia_node("uia-panel", "Thumb", name="VerticalThumb", bounds=unrelated["bounds"])]
        return nodes, providers

    def test_scrollbar_uses_actual_template_thumb_and_keeps_hit_box_separate_from_paint(self):
        nodes, providers = self.scrollbar_fixture()
        original = deepcopy(nodes)
        result = self.capture(nodes, providers)
        elements = self.by_id(result)
        self.assertEqual(elements["scrollbar"]["kind"], "scrollbar")
        thumb = elements["scroll-thumb"]
        self.assertEqual(thumb["kind"], "scrollbar-thumb")
        self.assertEqual(thumb["state"]["orientation"], "vertical")
        self.assertEqual(thumb["state"]["scroll_position"], .25)
        self.assertEqual(thumb["evidence"]["uia_id"], "uia-thumb")
        self.assertEqual(thumb["bounds"], box(400, 62, 10, 50))
        self.assertEqual(thumb["evidence"]["scrollbar_paint"]["hit_bounds"], thumb["bounds"])
        self.assertEqual(thumb["evidence"]["scrollbar_paint"]["layers"][0]["raw"], nodes[3])
        self.assertIsNone(thumb["evidence"]["scrollbar_paint"]["css_paint_equivalence"])
        self.assertTrue(any(row["property"] == "style.scrollbar_paint" for row in result["coverage"]["unmeasured"]))
        self.assertNotIn("panel-drag", elements)
        self.assertTrue(any(row.get("id") == "uia-panel" and row["property"] == "render correspondence"
                            for row in result["coverage"]["unmeasured"]))
        self.assertEqual(nodes, original)

    def test_scrollbar_thumb_requires_current_reciprocal_object_tree_not_name(self):
        for problem in ("source", "complete", "roots", "parent", "index", "identity", "path", "owner", "thumb-list", "extra-child"):
            with self.subTest(problem=problem):
                nodes, providers = self.scrollbar_fixture()
                evidence = nodes[0]["scrollbar_evidence"]
                if problem == "source": evidence["source"] = "expected VerticalThumb template"
                elif problem == "complete": evidence["complete"] = False
                elif problem == "roots": evidence["template_roots"] = []
                elif problem == "parent": nodes[2]["parent"] = "scrollbar"
                elif problem == "index": evidence["visual_subtree"][1]["child_index"] = 1
                elif problem == "identity": evidence["visual_subtree"][1]["same_parent_object"] = False
                elif problem == "path": nodes[2]["scrollbar_thumb_evidence"]["path"] = []
                elif problem == "owner": nodes[2]["scrollbar_thumb_evidence"]["owner_id"] = "panel-drag"
                elif problem == "thumb-list": evidence["thumb_ids"] = []
                elif problem == "extra-child": nodes.append(measured([xaml_node("new-child", "Grid", parent="scroll-template")])[0])
                nodes[2]["name"] = nodes[2]["automation_id"] = "VerticalThumb"
                result = self.capture(nodes, providers)
                self.assertFalse(any(element["kind"] == "scrollbar-thumb" for element in result["elements"]))
                self.assertTrue(any(row["property"].startswith("scrollbar.") for row in result["coverage"]["unmeasured"]))

    def test_scrollbar_missing_or_conflicting_range_is_unknown_and_never_changes_geometry(self):
        for problem in ("absent", "mismatch", "invalid", "orientation"):
            with self.subTest(problem=problem):
                nodes, providers = self.scrollbar_fixture()
                if problem == "absent": providers[0].pop("range_value")
                elif problem == "mismatch": providers[0]["range_value"]["value"] = 30
                elif problem == "invalid":
                    providers[0]["range_value"]["value"] = nodes[0]["scrollbar_evidence"]["range"]["value"] = 101
                else: nodes[0]["scrollbar_evidence"]["orientation"] = None
                result = self.capture(nodes, providers)
                thumb = self.by_id(result)["scroll-thumb"]
                self.assertIsNone(thumb["state"]["orientation" if problem == "orientation" else "scroll_position"])
                self.assertEqual(thumb["bounds"], nodes[2]["bounds"])
                self.assertEqual(thumb["evidence"]["scrollbar_range"]["uia_range"], providers[0].get("range_value"))

    def test_scrollbar_zero_length_actual_range_is_zero_not_missing(self):
        nodes, providers = self.scrollbar_fixture()
        nodes[0]["scrollbar_evidence"]["range"].update(minimum=8, maximum=8, value=8)
        providers[0]["range_value"].update(minimum=8, maximum=8, value=8)
        result = self.capture(nodes, providers)
        self.assertEqual(self.by_id(result)["scroll-thumb"]["state"]["scroll_position"], 0)

    def test_scrollbar_thumb_provider_must_belong_to_corresponding_scrollbar(self):
        nodes, providers = self.scrollbar_fixture()
        providers[1]["parent"] = "uia-panel"
        result = self.capture(nodes, providers)
        self.assertIsNone(self.by_id(result)["scroll-thumb"]["evidence"]["uia_id"])
        self.assertTrue(any(row.get("id") == "scroll-thumb" and row["property"] == "UIA correspondence"
                            for row in result["coverage"]["unmeasured"]))

    def test_panel_resize_requires_actual_field_object_identity(self):
        nodes, providers = self.scrollbar_fixture()
        nodes[4]["resize_handle_evidence"] = {"source": "actual MainWindow.panelResize object identity",
                                               "owner_type": "MainWindow", "handle_type": "Thumb", "dragging": True}
        result = self.capture(nodes, providers, xaml_changes={"capture_evidence": {"panel_resize_action": {"dragging": True}}})
        self.assertEqual(self.by_id(result)["panel-drag"]["kind"], "resize-handle")
        self.assertEqual(result["capture_evidence"]["panel_resize_action"], {"dragging": True})

    def test_scrollbar_internal_page_region_requires_nonpainted_current_template_and_keeps_uia(self):
        for alteration in (None, "paint", "label", "tab-stop", "ownership", "unknown-paint"):
            with self.subTest(alteration=alteration):
                nodes, providers = self.scrollbar_fixture()
                region = xaml_node("page-region", "RepeatButton", parent="scroll-template", bounds=box(400, 112, 10, 118),
                                   interaction_evidence={"is_control": True, "is_tab_stop": False, "is_hit_test_visible": True})
                background = xaml_node("page-background", "Border", parent="page-region", bounds=region["bounds"])
                page_nodes = measured([region, background]); page_nodes[0]["paint_kind"] = "template"
                page_nodes[0]["render_sibling_order"] = 1; page_nodes[1]["render_sibling_order"] = 0
                edges = [{"id": "page-region", "parent_id": "scroll-template", "child_index": 1,
                          "same_parent_object": True, "captured_parent_matches": True},
                         {"id": "page-background", "parent_id": "page-region", "child_index": 0,
                          "same_parent_object": True, "captured_parent_matches": True}]
                evidence = nodes[0]["scrollbar_evidence"]
                evidence["visual_subtree"].extend(deepcopy(edges))
                evidence["paint_ids"].append("page-background")
                page_nodes[0]["scrollbar_page_hit_evidence"] = {
                    "source": "Actual RepeatButton object in current ScrollBar template subtree",
                    "owner_id": "scrollbar", "path": [deepcopy(evidence["visual_subtree"][0]), deepcopy(edges[0])],
                    "is_pressed": False, "delay": 250, "interval": 50}
                if alteration == "paint": page_nodes[1]["style"]["background"] = [1, 2, 3, 255]
                elif alteration == "label": page_nodes[0]["text"] = "Visible action"
                elif alteration == "tab-stop": page_nodes[0]["interaction_evidence"]["is_tab_stop"] = True
                elif alteration == "ownership": page_nodes[0]["scrollbar_page_hit_evidence"]["path"] = []
                elif alteration == "unknown-paint": page_nodes[1]["style"]["background"] = None
                nodes.extend(page_nodes)
                providers.append(uia_node("uia-page", "Button", parent="uia-bar", class_name="RepeatButton",
                                          bounds=region["bounds"], supported_patterns=["InvokePatternIdentifiers.Pattern"]))
                result = self.capture(nodes, providers)
                if alteration is None:
                    self.assertNotIn("page-region", self.by_id(result))
                    record = next(row for row in result["projection"] if row.get("source") == "page-region")
                    self.assertEqual(record["owner"], "scrollbar")
                    self.assertEqual(record["actual_input_region"], page_nodes[0])
                    self.assertEqual(record["uia_input_region"], providers[-1])
                    self.assertEqual(record["template_layers"], [page_nodes[1]])
                else:
                    self.assertEqual(self.by_id(result)["page-region"]["kind"], "button")

    def test_scrollbar_thumb_missing_actual_bounds_never_borrows_provider_box(self):
        nodes, providers = self.scrollbar_fixture()
        nodes[2]["bounds"] = nodes[2]["visible_bounds"] = None
        result = self.capture(nodes, providers)
        self.assertNotIn("scroll-thumb", self.by_id(result))
        self.assertTrue(any(row.get("id") == "scroll-thumb" and row["property"] == "bounds"
                            for row in result["coverage"]["unmeasured"]))

    @staticmethod
    def complete_scrollbar_paint_fixture():
        nodes, providers = ProjectionTests.scrollbar_fixture()
        for node in (nodes[1], nodes[3]):
            style = node["style"]
            style["brush_evidence"] = {
                "background": {"type": "Microsoft.UI.Xaml.Media.SolidColorBrush", "solid_rgba": deepcopy(style["background"])},
                "border": {"type": "Microsoft.UI.Xaml.Media.SolidColorBrush", "solid_rgba": deepcopy(style["border_color"])}}
            style["border_colors"] = [deepcopy(style["border_color"]) for _ in range(4)]
            style["border_styles"] = ["solid" if width else "none" for width in style["border_widths"]]
            node["local_bounds"] = box(0, 0, node["bounds"]["width"], node["bounds"]["height"])
            node["scrollbar_layout_evidence"] = {"use_layout_rounding": False}
        return nodes, providers

    def test_measured_simple_thumb_projects_actual_paint_box_and_keeps_distinct_hit_box(self):
        nodes, providers = self.complete_scrollbar_paint_fixture()
        paint = nodes[3]
        paint["bounds"] = paint["visible_bounds"] = box(403, 65, 4, 44)
        paint["local_bounds"] = box(0, 0, 4, 44)
        paint["transform"].update(offset_x=403, offset_y=65)
        paint["style"].update(border_width=0, border_widths=[0] * 4, border_styles=["none"] * 4,
                               corner_radius=0, corner_radii=[0] * 4)
        result = self.capture(nodes, providers)
        thumb = self.by_id(result)["scroll-thumb"]
        receipt = thumb["evidence"]["scrollbar_paint"]
        self.assertEqual(thumb["bounds"], box(403, 65, 4, 44))
        self.assertEqual(receipt["hit_bounds"], box(400, 62, 10, 50))
        self.assertEqual(receipt["bounds_quantity"], "paint-primitive-border-box")
        self.assertEqual(thumb["style"]["background"], [143, 140, 134, 89.25])
        self.assertEqual(thumb["style"]["corner_radius"], 0)
        self.assertEqual(receipt["style_status"], "measured-simple-rectangle-properties")
        self.assertFalse(any(row["property"] == "style.scrollbar_paint" for row in result["coverage"]["unmeasured"]))
        track = self.by_id(result)["scrollbar"]
        self.assertEqual(track["evidence"]["scrollbar_paint"]["bounds_quantity"], "transparent-usable-track-region")
        self.assertEqual(track["bounds"], nodes[0]["bounds"])

    def test_measured_inner_background_keeps_border_box_and_fill_envelope_as_different_quantities(self):
        nodes, providers = self.complete_scrollbar_paint_fixture()
        nodes[3]["style"].update(corner_radius=0, corner_radii=[0] * 4)
        result = self.capture(nodes, providers)
        thumb = self.by_id(result)["scroll-thumb"]
        receipt = thumb["evidence"]["scrollbar_paint"]
        self.assertEqual(thumb["bounds"], box(400, 62, 10, 50))
        self.assertEqual(receipt["fill_envelope"]["bounds"], box(403, 65, 4, 44))
        self.assertEqual(thumb["style"]["border_width"], 3)
        self.assertEqual(thumb["style"]["border_widths"], [3] * 4)

    def test_actual_rounded_thumb_keeps_box_and_brush_but_never_relabels_native_radius_as_css(self):
        nodes, providers = self.complete_scrollbar_paint_fixture()
        result = self.capture(nodes, providers)
        thumb = self.by_id(result)["scroll-thumb"]
        receipt = thumb["evidence"]["scrollbar_paint"]
        self.assertEqual(receipt["native_corner_radii"], [8] * 4)
        self.assertEqual(receipt["fill_envelope"]["bounds"], box(403, 65, 4, 44))
        self.assertIsNone(thumb["style"]["corner_radius"])
        self.assertIsNone(receipt["css_paint_equivalence"])
        self.assertTrue(any(row.get("id") == "scroll-thumb" and row["property"] == "style.corner_radius"
                            for row in result["coverage"]["unmeasured"]))
        self.assertFalse(any(row.get("id") == "scrollbar" and row["property"] == "style.scrollbar_paint"
                             for row in result["coverage"]["unmeasured"]))

    def test_scrollbar_paint_unknowns_keep_failure_instead_of_using_hit_box_as_paint(self):
        for problem in ("brush", "rounding", "transform", "local-box", "clip", "shadow", "partial-clip"):
            with self.subTest(problem=problem):
                nodes, providers = self.complete_scrollbar_paint_fixture()
                paint = nodes[3]
                if problem == "brush": paint["style"].pop("brush_evidence")
                elif problem == "rounding": paint["scrollbar_layout_evidence"]["use_layout_rounding"] = True
                elif problem == "transform": paint["transform"]["m12"] = .1
                elif problem == "local-box": paint.pop("local_bounds")
                elif problem == "clip": paint["clip"] = {"kind": "PathGeometry"}
                elif problem == "shadow": paint["style"]["shadow"] = None
                elif problem == "partial-clip": paint["visible_bounds"] = box(400, 70, 10, 42)
                result = self.capture(nodes, providers)
                receipt = self.by_id(result)["scroll-thumb"]["evidence"]["scrollbar_paint"]
                self.assertIsNone(receipt["canonical_bounds"])
                self.assertIsNone(receipt["css_paint_equivalence"])
                self.assertEqual(receipt["hit_bounds"], nodes[2]["bounds"])
                self.assertTrue(any(row.get("id") == "scroll-thumb" and row["property"] == "style.scrollbar_paint"
                                    for row in result["coverage"]["unmeasured"]))

    @staticmethod
    def state_dot_fixture():
        frame = xaml_node("avatar-frame", "Grid", bounds=box(41, 440, 28, 28))
        owner = xaml_node("vacant-dot", "NativeStateDotView", parent="avatar-frame", bounds=box(61, 460, 10, 10),
                          render_type_evidence={"is_panel": True, "is_shape": False, "is_content_control": False},
                          state_dot_evidence={
                              "source": "actual NativeStateDotView owned paint objects and current Children order",
                              "complete": True, "current_children_same_objects": True,
                              "current_children": ["surround", "vacancy-ring"],
                              "layers": [{"id": "surround", "property": "Surround", "child_index": 0},
                                         {"id": "vacancy-ring", "property": "VacancyRing", "child_index": 1}]})
        outer = xaml_node("surround", "Ellipse", parent="vacant-dot", bounds=box(61, 460, 10, 10))
        inner = xaml_node("vacancy-ring", "Ellipse", parent="vacant-dot", bounds=box(63, 462, 6, 6))
        for index, (layer, prop, stroke, width) in enumerate((
                (outer, "Surround", [248, 247, 245, 255], 2),
                (inner, "VacancyRing", [184, 181, 175, 255], 1.5))):
            layer["state_dot_layer_evidence"] = {
                "source": "actual NativeStateDotView owned Ellipse object identity", "owner_id": "vacant-dot",
                "property": prop, "child_index": index}
            layer["style"].update(foreground=stroke, stroke_width=width)
            layer["render_type_evidence"] = {"is_shape": True, "is_panel": False, "is_content_control": False}
        unrelated = xaml_node("other-dot", "Ellipse", parent="avatar-frame", bounds=box(90, 460, 6, 6))
        unrelated["style"].update(background=[62, 155, 94, 255])
        nodes = measured([frame, owner, outer, inner, unrelated])
        for node in nodes[2:]: node["paint_kind"] = "ellipse"
        return nodes

    def test_state_dot_owns_only_its_two_actual_layers_without_claiming_shadow_equivalence(self):
        nodes = self.state_dot_fixture()
        result = self.capture(nodes)
        elements = self.by_id(result)
        self.assertEqual(set(elements), {"vacant-dot", "other-dot"})
        dot = elements["vacant-dot"]
        self.assertEqual(dot["kind"], "state-dot")
        self.assertEqual(dot["bounds"], nodes[1]["bounds"])
        self.assertEqual(dot["evidence"]["paint_sources"], ["surround", "vacancy-ring"])
        evidence = dot["evidence"]["compound_paint"]
        self.assertEqual([layer["raw"] for layer in evidence["layers"]], nodes[2:4])
        self.assertIsNone(evidence["css_paint_equivalence"])
        self.assertIsNone(dot["style"]["shadow"])
        self.assertIsNone(dot["style"]["border_width"])
        self.assertTrue(any(row["id"] == "vacant-dot" and row["property"] == "style.compound_paint"
                            for row in result["coverage"]["unmeasured"]))
        for layer in nodes[2:4]:
            ownership = [row for row in result["projection"] if row.get("source") == layer["id"]]
            self.assertEqual(len(ownership), 1)
            self.assertEqual(ownership[0]["owner"], "vacant-dot")
            self.assertEqual(ownership[0]["paint_evidence"], layer)

    def test_unverified_state_dot_does_not_absorb_any_actual_ellipse(self):
        for problem in ("missing", "source", "incomplete", "children-identity", "current-order",
                        "layer-order", "reciprocal", "detached", "extra-child"):
            with self.subTest(problem=problem):
                nodes = self.state_dot_fixture()
                evidence = nodes[1]["state_dot_evidence"]
                if problem == "missing": nodes[1].pop("state_dot_evidence")
                elif problem == "source": evidence["source"] = "Tag vacant"
                elif problem == "incomplete": evidence["complete"] = False
                elif problem == "children-identity": evidence["current_children_same_objects"] = False
                elif problem == "current-order": evidence["current_children"].reverse()
                elif problem == "layer-order": evidence["layers"].reverse()
                elif problem == "reciprocal": nodes[3]["state_dot_layer_evidence"]["owner_id"] = "avatar-frame"
                elif problem == "detached": nodes[3]["parent"] = "avatar-frame"
                elif problem == "extra-child": nodes[4]["parent"] = "vacant-dot"
                result = self.capture(nodes)
                elements = self.by_id(result)
                self.assertNotIn("vacant-dot", elements)
                self.assertTrue({"surround", "vacancy-ring", "other-dot"} <= set(elements))
                self.assertTrue(any(row["id"] == "vacant-dot" and row["property"] == "ownership.state_dot_paint"
                                    for row in result["coverage"]["unmeasured"]))

    @staticmethod
    def fenced_code_fixture():
        root = xaml_node("body", "StackPanel", bounds=box(20, 20, 400, 200))
        block = xaml_node("pre", "Border", parent="body", bounds=box(30, 40, 250, 60),
                          markdown_code_evidence={
                              "source": "actual MarkdownSemantic.RegisterFencedCode object identities",
                              "kind": "fenced-code", "complete": True, "scroller_id": "scroll", "text_id": "code-text",
                              "border_child_is_registered_scroller": True, "scroller_content_is_registered_text": True})
        block["style"].update(background=[246, 245, 242, 255], border_color=[220, 218, 212, 255],
                              border_width=1, corner_radius=8)
        scroll = xaml_node("scroll", "ScrollViewer", parent="pre", bounds=box(42, 50, 226, 40),
                           markdown_code_scroller_evidence={
                               "source": "actual MarkdownSemantic.RegisterFencedCode scroller object identity",
                               "owner_id": "pre", "text_id": "code-text"})
        presenter = xaml_node("presenter", "ScrollContentPresenter", parent="scroll", bounds=scroll["bounds"])
        code = xaml_node("code-text", "TextBlock", "review('Windows')\nreview('macOS')", parent="presenter", bounds=scroll["bounds"],
                         declared_content_owner="scroll", declared_content_source="ContentControl.Content",
                         markdown_code_text_evidence={
                             "source": "actual MarkdownSemantic.RegisterFencedCode text object identity",
                             "owner_id": "pre", "scroller_id": "scroll"})
        code["layout"].update(line_count=2, character_boxes_coordinate_space="content-window", rich_text_runs=[{
            "type": "Run", "text": code["text"], "bounds": [box(42, 50, 140, 18), box(42, 68, 128, 18)],
            "coordinate_space": "content-window", "geometry_complete": True,
            "font_size": 12.5, "font_weight": 400, "foreground": [27, 27, 26, 255],
            "font_family": "Cascadia Code", "start_offset": 0, "end_offset": len(code["text"])}])
        ordinary = xaml_node("ordinary", "Border", "", parent="body", bounds=box(30, 120, 250, 60))
        ordinary["style"] = deepcopy(block["style"])
        ordinary["tag"] = "fenced-code"
        return measured([root, block, scroll, presenter, code, ordinary])

    def test_registered_fenced_container_is_code_and_keeps_actual_code_run_once(self):
        nodes = self.fenced_code_fixture()
        result = self.capture(nodes)
        elements = self.by_id(result)
        self.assertEqual(elements["pre"]["kind"], "code")
        self.assertEqual(elements["pre"]["text"], "")
        self.assertEqual(elements["pre"]["bounds"], nodes[1]["bounds"])
        self.assertEqual(elements["pre"]["style"]["background"], nodes[1]["style"]["background"])
        self.assertEqual(elements["pre"]["evidence"]["markdown_code_evidence"], nodes[1]["markdown_code_evidence"])
        code = elements["code-text:run:0"]
        self.assertEqual(code["kind"], "text")
        self.assertEqual(code["text"], "review('Windows')\nreview('macOS')")
        self.assertEqual(code["evidence"]["text_run_source"]["owner"], "code-text")
        self.assertEqual(sum(element["text"] == code["text"] for element in result["elements"]), 1)
        self.assertEqual(elements["ordinary"]["kind"], "card")
        self.assertFalse(any(row["property"] == "semantic.markdown_fenced_code" for row in result["coverage"]["unmeasured"]))

    def test_unregistered_border_does_not_gain_code_semantics_from_paint_tag_or_text(self):
        nodes = self.fenced_code_fixture()
        nodes[1].pop("markdown_code_evidence")
        nodes[1]["tag"] = "fenced-code"
        elements = self.by_id(self.capture(nodes))
        self.assertEqual(elements["pre"]["kind"], "card")
        self.assertEqual(elements["ordinary"]["kind"], "card")
        self.assertEqual(elements["code-text:run:0"]["text"], "review('Windows')\nreview('macOS')")

    def test_incomplete_or_detached_fenced_code_identity_keeps_paint_and_fails_coverage(self):
        for problem in ("source", "complete", "child", "content", "missing-text", "wrong-type",
                        "reciprocal-text", "reciprocal-scroll", "declared-content", "ancestry"):
            with self.subTest(problem=problem):
                nodes = self.fenced_code_fixture()
                evidence = nodes[1]["markdown_code_evidence"]
                if problem == "source": evidence["source"] = "Tag fenced-code"
                elif problem == "complete": evidence["complete"] = False
                elif problem == "child": evidence["border_child_is_registered_scroller"] = False
                elif problem == "content": evidence["scroller_content_is_registered_text"] = False
                elif problem == "missing-text": evidence["text_id"] = "absent"
                elif problem == "wrong-type": nodes[1]["type"] = "Grid"
                elif problem == "reciprocal-text": nodes[4]["markdown_code_text_evidence"]["owner_id"] = "ordinary"
                elif problem == "reciprocal-scroll": nodes[2].pop("markdown_code_scroller_evidence")
                elif problem == "declared-content": nodes[4]["declared_content_owner"] = "ordinary"
                elif problem == "ancestry": nodes[4]["parent"] = "body"
                result = self.capture(nodes)
                elements = self.by_id(result)
                self.assertEqual(elements["pre"]["kind"], "card")
                self.assertIn("code-text:run:0", elements)
                self.assertTrue(any(row["id"] == "pre" and row["property"] == "semantic.markdown_fenced_code"
                                    for row in result["coverage"]["unmeasured"]))

    def test_editable_document_is_one_input_and_keeps_actual_ranges_without_inventing_fonts(self):
        bounds = box(30, 600, 300, 50)
        node = xaml_node("composer", "ComposerInput", "First\nSecond", bounds=bounds,
                         interaction_evidence={"is_control": True, "is_tab_stop": True, "is_hit_test_visible": True})
        ranges = [{"type": "RichEditTextRange", "text": "First", "bounds": [box(30, 600, 40, 22)],
                   "geometry_complete": True, "font_family": "Declared family"},
                  {"type": "RichEditTextRange", "text": "Second", "bounds": [box(30, 622, 50, 22)],
                   "geometry_complete": True, "font_family": "Declared family"}]
        node["layout"].update(wrap="character", normal_break_strategy="word", emergency_break_strategy="break-unbreakable",
                              line_break_configuration={"source": "synthetic live ComposerInput.TextWrapping fixture", "owner": "composer",
                                                        "raw": {"text_wrapping": "Wrap", "text_wrapping_value": 2}},
                              line_count=2, rich_text_runs=ranges,
                              character_boxes=[box(30, 600, 40, 22), box(30, 622, 50, 22)],
                              character_boxes_coordinate_space="content-window", placeholder="Message")
        provider = uia_node("editor-uia", "Edit", bounds=bounds, class_name="ComposerInput", value="First\nSecond",
                            supported_patterns=["ValuePattern", "TextPattern"])
        result = self.capture(measured([node]), [provider])
        elements = self.by_id(result)
        self.assertEqual(set(elements), {"composer"})
        self.assertEqual(elements["composer"]["kind"], "input")
        self.assertEqual(elements["composer"]["text"], "First\nSecond")
        self.assertEqual(elements["composer"]["evidence"]["uia_id"], "editor-uia")
        self.assertEqual(elements["composer"]["layout"]["line_count"], 2)
        self.assertEqual(elements["composer"]["layout"]["normal_break_strategy"], "word")
        self.assertEqual(elements["composer"]["layout"]["emergency_break_strategy"], "break-unbreakable")
        self.assertEqual(elements["composer"]["evidence"]["line_break_configuration"]["raw"]["text_wrapping"], "Wrap")
        self.assertEqual(elements["composer"]["evidence"]["rich_text_runs"], ranges)
        self.assertIsNone(elements["composer"]["style"]["rendered_fonts"])

    @staticmethod
    def textarea_fixture():
        editor = xaml_node("editor", "NativeTextarea", "Purpose", bounds=box(30, 100, 300, 120),
                           interaction_evidence={"is_control": True, "is_tab_stop": True, "is_hit_test_visible": True})
        wrapper = xaml_node("grip-wrapper", "NativeTextareaResizeGrip", parent="editor", bounds=box(315, 205, 14, 14),
                            render_type_evidence={"is_panel": True})
        grip = xaml_node("grip", "Thumb", parent="grip-wrapper", bounds=wrapper["bounds"], accessible_name="Resize purpose",
                         interaction_evidence={"is_control": True, "is_tab_stop": False, "is_hit_test_visible": True},
                         resize_handle_evidence={"source": "actual NativeTextarea.ResizeGrip.Handle object identity",
                                                 "owner_id": "editor", "owner_type": "NativeTextarea", "handle_type": "Thumb",
                                                 "dragging": True, "resize_sequence": 1, "resize_delta_count": 4})
        template = xaml_node("grip-template", "Grid", parent="grip", bounds=grip["bounds"])
        path = xaml_node("grip-path", "Path", parent="grip-template", bounds=grip["bounds"])
        path["style"]["stroke_width"] = 1
        nodes = measured([editor, wrapper, grip, template, path])
        providers = [uia_node("uia-editor", "Edit", bounds=editor["bounds"], class_name="NativeTextarea", value="Purpose",
                              supported_patterns=["ValuePattern", "TextPattern"]),
                     uia_node("uia-grip", "Thumb", name="Resize purpose", parent="uia-editor", bounds=grip["bounds"],
                              automation_id="textarea-resize-handle")]
        return nodes, providers

    def test_textarea_and_identity_measured_resize_thumb_keep_input_and_independent_uia(self):
        nodes, providers = self.textarea_fixture()
        providers[1]["state"].update(enabled=False, focused=False, focusable=False)
        result = self.capture(nodes, providers)
        elements = self.by_id(result)
        self.assertEqual(elements["editor"]["kind"], "input")
        self.assertEqual(elements["editor"]["text"], "Purpose")
        grip = elements["grip"]
        self.assertEqual(grip["kind"], "resize-handle")
        self.assertEqual(grip["bounds"], nodes[2]["bounds"])
        self.assertEqual(grip["evidence"]["uia_id"], "uia-grip")
        self.assertIs(grip["state"]["enabled"], False)
        self.assertIs(grip["state"]["focused"], False)
        self.assertTrue(grip["evidence"]["interaction_applicability"]["applicable"])
        self.assertEqual(grip["evidence"]["resize_handle_evidence"], nodes[2]["resize_handle_evidence"])
        self.assertIn("grip-path", elements)
        self.assertNotIn("grip-template", elements)
        self.assertTrue(any(row.get("source") == "grip-template" and row.get("owner") == "grip" for row in result["projection"]))

    def test_resize_wrapper_own_paint_is_not_deleted_by_its_class_name(self):
        nodes, providers = self.textarea_fixture()
        nodes[1]["style"]["background"] = [140, 140, 140, 60]
        nodes[1]["paint_kind"] = "rectangle"
        result = self.capture(nodes, providers)
        elements = self.by_id(result)
        self.assertEqual(elements["grip-wrapper"]["kind"], "card")
        self.assertEqual(elements["grip-wrapper"]["style"]["background"], [140, 140, 140, 60])
        self.assertIn("grip-path", elements)

    def test_named_thumb_without_production_identity_is_not_invented_as_resize_handle(self):
        for evidence in (None, {}, {"source": "AutomationId textarea-resize-handle"}):
            with self.subTest(evidence=evidence):
                nodes, providers = self.textarea_fixture()
                nodes[2]["resize_handle_evidence"] = evidence
                nodes[2]["automation_id"] = "textarea-resize-handle"
                result = self.capture(nodes, providers)
                self.assertFalse(any(element["kind"] == "resize-handle" for element in result["elements"]))
                self.assertTrue(any(row.get("id") == "uia-grip" and row.get("property") == "render correspondence"
                                    for row in result["coverage"]["unmeasured"]))

    def test_resize_handle_without_measured_box_never_borrows_uia_geometry(self):
        nodes, providers = self.textarea_fixture()
        nodes[2]["bounds"] = nodes[2]["visible_bounds"] = None
        result = self.capture(nodes, providers)
        self.assertNotIn("grip", self.by_id(result))
        self.assertTrue(any(row.get("id") == "grip" and row.get("property") == "bounds"
                            for row in result["coverage"]["unmeasured"]))

    def test_resize_handle_without_independent_thumb_provider_keeps_coverage_failure(self):
        nodes, providers = self.textarea_fixture()
        result = self.capture(nodes, providers[:1])
        self.assertEqual(self.by_id(result)["grip"]["kind"], "resize-handle")
        self.assertIsNone(self.by_id(result)["grip"]["evidence"]["uia_id"])
        self.assertTrue(any(row.get("id") == "grip" and row.get("property") == "UIA correspondence"
                            for row in result["coverage"]["unmeasured"]))

    def test_native_label_draw_receipt_is_forwarded_even_when_its_button_owns_the_text(self):
        button = xaml_node("button", "Button")
        label = xaml_node("label", "NativeLabel", "File", parent="button", bounds=box(20, 25, 40, 18))
        receipt = {"source": "NativeLabel production SurfaceImageSource / DirectWrite renderer",
                   "coverage_complete": False, "presentation_frame": None,
                   "draw": {"surface_end_draw_succeeded": True, "glyph_runs": [{"glyph_indices": [12, 14]}]}}
        label["native_label_evidence"] = deepcopy(receipt)
        result = self.capture(measured([button, label]), [uia_node("uia-button", "Button", "File")])
        actual = self.by_id(result)["button"]
        self.assertEqual(actual["evidence"]["native_label_evidence"], receipt)
        self.assertEqual(actual["evidence"]["label_source"], "label")
        self.assertNotIn("label", self.by_id(result))
        self.assertIsNone(actual["style"]["rendered_fonts"])
        self.assertTrue(any(row.get("property") == "style.rendered_fonts" for row in result["coverage"]["unmeasured"]))

    def test_only_identity_bound_native_label_image_is_owned_as_text_paint(self):
        for verified in (True, False, None):
            with self.subTest(verified=verified):
                button = xaml_node("button", "Button")
                label = xaml_node("label", "NativeLabel", "File", parent="button", bounds=box(20, 25, 40, 18))
                surface = xaml_node("surface", "Image", parent="label", bounds=box(20, 25, 40, 19),
                                    interaction_evidence={"is_control": False, "is_tab_stop": None, "is_hit_test_visible": False})
                if verified is not None:
                    surface["native_label_surface_evidence"] = {
                        "source": "actual NativeLabel production Image object identity and SurfaceImageSource COM binding",
                        "owner_id": "label", "same_image_object": True, "surface_binding_same_com_identity": verified,
                        "source_type": "Microsoft.UI.Xaml.Media.Imaging.SurfaceImageSource", "surface_revision": 1}
                result = self.capture(measured([button, label, surface]), [uia_node("uia-button", "Button", "File")])
                elements = self.by_id(result)
                if verified is True:
                    self.assertNotIn("surface", elements)
                    proof = next(row for row in result["projection"] if row.get("source") == "surface")
                    self.assertEqual(proof["owner"], "label")
                    self.assertEqual(proof["ownership_evidence"], surface["native_label_surface_evidence"])
                    self.assertEqual(elements["button"]["text"], "File")
                    self.assertIsNone(elements["button"]["style"]["rendered_fonts"])
                else:
                    self.assertEqual(elements["surface"]["kind"], "image")
                    if verified is False:
                        self.assertTrue(any(row.get("property") == "ownership.native_label_surface" for row in result["coverage"]["unmeasured"]))

    @staticmethod
    def inline_sequence_fixture():
        owner = xaml_node("paragraph", "RichTextBlock", "Before  after", bounds=box(10, 20, 180, 20))
        before = {"type": "Run", "text": "Before ", "start_offset": 2, "end_offset": 9,
                  "font_size": 13, "font_weight": 400, "foreground": [27, 27, 26, 255],
                  "font_family": "Fixture Sans", "bounds": [box(10, 20, 50, 20)], "geometry_complete": True}
        after = dict(before, text=" after", start_offset=13, end_offset=19, bounds=[box(110, 20, 40, 20)])
        owner["layout"].update(rich_text_runs=[before, after], character_boxes_coordinate_space="content-window")
        owner["inline_order_evidence"] = {"source": "actual InlineCollection order and InlineUIContainer.Child object identity", "complete": True,
            "entries": [
                {"ordinal": 0, "type": "Run", "collection_path": [0, 0], "start_offset": 2, "end_offset": 9, "run_index": 0},
                {"ordinal": 1, "type": "InlineUIContainer", "collection_path": [0, 1], "start_offset": 9, "end_offset": 13,
                 "child_id": "code-card", "child_source": "actual InlineUIContainer.Child object identity"},
                {"ordinal": 2, "type": "Run", "collection_path": [0, 2], "start_offset": 13, "end_offset": 19, "run_index": 1}]}
        code = xaml_node("code-card", "Border", parent="paragraph", bounds=box(60, 20, 50, 20),
                         inline_child_evidence={"source": "actual InlineUIContainer.Child object identity", "owner_id": "paragraph",
                                                "ordinal": 1, "collection_path": [0, 1], "start_offset": 9, "end_offset": 13})
        code["style"]["background"] = [27, 27, 26, 18]
        text = xaml_node("code-text", text="code", parent="code-card", bounds=box(65, 21, 40, 18))
        return measured([owner, code, text])

    def test_actual_inline_collection_interleaves_ui_child_between_text_runs_once(self):
        nodes = self.inline_sequence_fixture()
        result = self.capture(nodes, [uia_node("uia-paragraph", name="Before code after", bounds=nodes[0]["bounds"])])
        ids = [element["id"] for element in result["elements"]]
        self.assertEqual(ids, ["paragraph:run:0", "code-card", "code-text", "paragraph:run:1"])
        self.assertEqual(len(ids), len(set(ids)))
        after = self.by_id(result)["paragraph:run:1"]
        self.assertEqual(after["text"], " after")
        self.assertEqual(after["evidence"]["inline_sequence_evidence"]["entry"]["collection_path"], [0, 2])
        self.assertFalse(any(row.get("property") == "reading_order.inline_collection" for row in result["coverage"]["unmeasured"]))

    def test_incomplete_or_repeated_inline_identity_keeps_original_order_and_fails_coverage(self):
        for change in ("missing-child-proof", "wrong-owner", "wrong-offset", "repeated-run", "incomplete"):
            with self.subTest(change=change):
                nodes = self.inline_sequence_fixture()
                if change == "missing-child-proof":
                    nodes[1].pop("inline_child_evidence")
                elif change == "wrong-owner":
                    nodes[1]["inline_child_evidence"]["owner_id"] = "other"
                elif change == "wrong-offset":
                    nodes[0]["inline_order_evidence"]["entries"][0]["start_offset"] = 999
                elif change == "repeated-run":
                    nodes[0]["inline_order_evidence"]["entries"][2].update(run_index=0, start_offset=2, end_offset=9)
                else:
                    nodes[0]["inline_order_evidence"]["complete"] = False
                result = self.capture(nodes, [uia_node("uia-paragraph", name="Before code after", bounds=nodes[0]["bounds"])])
                ids = [element["id"] for element in result["elements"]]
                self.assertEqual(ids, ["paragraph:run:0", "paragraph:run:1", "code-card", "code-text"])
                self.assertEqual(len(ids), len(set(ids)))
                self.assertTrue(any(row.get("property") == "reading_order.inline_collection" for row in result["coverage"]["unmeasured"]))

    def test_actual_trimming_is_raw_evidence_and_does_not_invent_an_ellipsis_box(self):
        label = xaml_node("label", text="Long label")
        trimming = {"is_text_trimmed": True, "source": "Live TextBlock.IsTextTrimmed", "ellipsis_bounds": None}
        label["layout"].update(truncation="character-ellipsis", actual_trimming=deepcopy(trimming))
        result = self.capture(measured([label]), [uia_node("uia-label", name="Long label")])
        actual = self.by_id(result)["label"]
        self.assertEqual(actual["evidence"]["actual_trimming"], trimming)
        self.assertEqual(actual["layout"]["truncation"], "character-ellipsis")
        self.assertEqual(len(result["elements"]), 1)

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

    def test_chart_node_uses_button_provider_and_preserves_actual_current_and_labels(self):
        node = xaml_node("node", "ChartNodeButton", bounds=box(10, 20, 236, 80))
        node["state"].update(current=True, selected=None)
        node["state_evidence"] = {"current": {"value": True, "source": "ChartNodeButton.IsCurrent"}}
        content = xaml_node("content", "Grid", parent="node", bounds=node["bounds"], declared_content_owner="node")
        title = xaml_node("title", text="Design", parent="content", bounds=box(30, 25, 80, 20))
        subtitle = xaml_node("subtitle", text="Lead: Sam", parent="content", bounds=box(30, 50, 80, 18))
        result = self.capture([node, content, title, subtitle], [uia_node("provider", "Button", "Design Lead: Sam", bounds=node["bounds"])])
        elements = self.by_id(result)
        self.assertEqual(elements["node"]["kind"], "chart-node")
        self.assertEqual(elements["node"]["evidence"]["uia_id"], "provider")
        self.assertTrue(elements["node"]["state"]["current"])
        self.assertIsNone(elements["node"]["state"]["selected"])
        self.assertEqual(elements["node"]["evidence"]["state_evidence"]["current"]["source"], "ChartNodeButton.IsCurrent")
        self.assertEqual(elements["node"]["text"], "")
        self.assertEqual(elements["title"]["text"], "Design")
        self.assertEqual(elements["subtitle"]["text"], "Lead: Sam")

    def test_menu_tag_content_keeps_checkbox_avatar_and_independent_labels(self):
        item = xaml_node("item", "MenuFlyoutItem", "A Alice alice", bounds=box(10, 20, 220, 36))
        presenter = xaml_node("presenter", "ContentPresenter", parent="item", bounds=item["bounds"])
        presenter["style"]["background"] = [245, 245, 245, 255]
        row = xaml_node("row", "StackPanel", parent="presenter", bounds=box(20, 27, 190, 22),
                        declared_content_owner="item", declared_content_source="FrameworkElement.Tag UIElement in the actual visual tree")
        check = xaml_node("check", "CheckBox", parent="row", bounds=box(20, 30, 13, 13))
        check["state"]["checked"] = True
        avatar = xaml_node("avatar", "Border", parent="row", bounds=box(40, 27, 20, 20))
        avatar["style"]["background"] = [220, 180, 200, 255]
        initial = xaml_node("initial", text="A", parent="avatar", bounds=box(44, 28, 12, 18))
        primary = xaml_node("primary", text="Alice", parent="row", bounds=box(70, 27, 50, 20))
        secondary = xaml_node("secondary", text="alice", parent="row", bounds=box(130, 29, 40, 18))
        secondary["style"]["font_size"] = 11.96
        result = self.capture([item, presenter, row, check, avatar, initial, primary, secondary], [
            uia_node("uia-item", "MenuItem", "A Alice alice", bounds=item["bounds"]),
            uia_node("uia-check", "CheckBox", parent="uia-item", bounds=check["bounds"]),
        ])
        elements = self.by_id(result)
        self.assertEqual(elements["item"]["text"], "")
        self.assertNotIn("presenter", elements)
        self.assertIn("check", elements)
        self.assertTrue(elements["check"]["state"]["checked"])
        self.assertIn("avatar", elements)
        self.assertEqual(elements["initial"]["text"], "A")
        self.assertEqual(elements["primary"]["text"], "Alice")
        self.assertEqual(elements["secondary"]["style"]["font_size"], 11.96)

    def test_menu_single_label_is_not_collapsed_when_checkbox_is_separate(self):
        item = xaml_node("item", "MenuFlyoutItem", "All")
        check = xaml_node("check", "CheckBox", parent="item", bounds=box(12, 24, 13, 13))
        label = xaml_node("label", text="All", parent="item", bounds=box(30, 22, 50, 18))
        result = self.capture([item, check, label], [uia_node("provider", "MenuItem", "All")])
        self.assertEqual(self.by_id(result)["item"]["text"], "")
        self.assertEqual(self.by_id(result)["label"]["text"], "All")

    def test_zero_opacity_actual_control_owns_only_its_unique_provider(self):
        # Recorded 1e3 group: UIA uia-136 stays onscreen for XAML xaml-574,
        # although the rendered Quote action's cumulative opacity is exactly 0.
        action = xaml_node("xaml-574", "Button", accessible_name="Quote", bounds=box(940, 272, 30, 30),
                           opacity=0, hidden_reason="zero opacity")
        provider = uia_node("uia-136", "Button", "Quote", bounds=action["bounds"])
        popup = xaml_node("popup", "Button", accessible_name="Open", bounds=box(900, 350, 80, 30))
        popup_provider = uia_node("uia-popup", "Button", "Open", parent="uia-136", bounds=popup["bounds"])
        result = self.capture([action, popup], [provider, popup_provider])
        ownership = [record for record in result["projection"] if record.get("source") == "uia-136"]
        self.assertEqual(len(ownership), 1)
        self.assertEqual(ownership[0]["owner"], "xaml-574")
        self.assertEqual(ownership[0]["visibility_evidence"]["opacity"], 0)
        self.assertFalse(ownership[0]["visibility_evidence"]["uia_offscreen"])
        self.assertNotIn("xaml-574", self.by_id(result))
        self.assertEqual(self.by_id(result)["popup"]["evidence"]["uia_id"], "uia-popup")
        self.assertFalse(any(gap["id"] == "uia-136" and gap["property"] == "render correspondence"
                             for gap in result["coverage"]["unmeasured"]))

    def test_transparent_provider_requires_unique_exact_native_identity(self):
        action = xaml_node("hidden", "Button", accessible_name="Quote", opacity=0, hidden_reason="zero opacity")
        provider = uia_node("provider", "Button", "Quote")
        self.assertEqual(len(transparent_uia_ownership([provider], [action])), 1)
        duplicate = deepcopy(action)
        duplicate["id"] = "other-hidden"
        self.assertEqual(transparent_uia_ownership([provider], [action, duplicate]), [])
        duplicate.update(id="visible", opacity=1, hidden_reason=None)
        self.assertEqual(transparent_uia_ownership([provider], [action, duplicate]), [])
        second_provider = deepcopy(provider)
        second_provider["id"] = "second-provider"
        self.assertEqual(transparent_uia_ownership([provider, second_provider], [action]), [])
        wrong_name = deepcopy(provider)
        wrong_name["name"] = "Copy"
        self.assertEqual(transparent_uia_ownership([wrong_name], [action]), [])
        near_box = deepcopy(provider)
        near_box["bounds"]["x"] += .5
        self.assertEqual(transparent_uia_ownership([near_box], [action]), [])
        opacity_unknown = deepcopy(action)
        opacity_unknown["opacity"] = None
        self.assertEqual(transparent_uia_ownership([provider], [opacity_unknown]), [])

    def test_transparent_ambiguous_providers_keep_coverage_failure(self):
        action = xaml_node("hidden", "Button", accessible_name="Quote", opacity=0, hidden_reason="zero opacity")
        result = self.capture([action], [uia_node("first", "Button", "Quote"), uia_node("second", "Button", "Quote")])
        failures = {gap["id"] for gap in result["coverage"]["unmeasured"] if gap["property"] == "render correspondence"}
        self.assertTrue({"first", "second"} <= failures)

    def test_actual_panel_subclass_and_stroked_rectangle_are_not_lost(self):
        legend = xaml_node("legend", "ChartFlexPanel", bounds=box(10, 20, 400, 34),
                           render_type_evidence={"is_panel": True, "is_shape": False})
        legend["style"]["background"] = [239, 238, 234, 255]
        swatch = xaml_node("swatch", "ChartLegendSwatch", parent="legend", bounds=box(30, 30, 18, 12),
                           render_type_evidence={"is_panel": True, "is_shape": False})
        outline = xaml_node("outline", "Rectangle", parent="swatch", bounds=swatch["bounds"],
                            render_type_evidence={"is_panel": False, "is_shape": True})
        outline["style"].update(stroke_width=1.5, stroke_dash=[4.5, 4.5], stroke_dash_offset=0,
                                stroke_linecap="butt", stroke_linejoin="miter")
        outline["stroke_evidence"] = {"raw_pattern": {"dash_array": [3, 3], "dash_offset": 0}}
        result = self.capture([legend, swatch, outline], [uia_node("unused", "Text", "", bounds=box(900, 600, 10, 10))])
        elements = self.by_id(result)
        self.assertEqual(elements["legend"]["kind"], "region")
        self.assertIsNone(elements["legend"]["state"]["enabled"])
        self.assertNotIn("swatch", elements)
        self.assertEqual(elements["outline"]["style"]["stroke_dash"], [4.5, 4.5])
        self.assertEqual(elements["outline"]["style"]["foreground"], [27, 27, 26, 255])
        self.assertEqual(elements["outline"]["evidence"]["stroke_evidence"]["raw_pattern"]["dash_array"], [3, 3])

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

    def test_background_corner_radius_is_measured_without_requiring_a_border(self):
        control = xaml_node("button", "Button")
        paint = xaml_node("paint", "ContentPresenter", parent="button")
        paint["style"].update(background=[40, 50, 60, 255], border_width=0, corner_radius=9)
        result = self.capture(measured([control, paint]), [uia_node("uia-button", "Button")])
        self.assertEqual(self.by_id(result)["button"]["style"]["corner_radius"], 9)

    def test_quarter_turn_maps_actual_individual_edges_and_corner_radii(self):
        surface = measured([xaml_node("surface", "Border")])[0]
        surface["transform"].update(m11=0, m12=2, m21=-3, m22=0)
        surface["style"]["corner_radii"] = [1, 2, 3, 4]
        radii, widths = transformed_box_edges(surface, [1, 2, 3, 4])
        self.assertEqual(widths, [8, 3, 4, 9])
        self.assertEqual(radii, [{"x": 12, "y": 8}, {"x": 3, "y": 2}, {"x": 6, "y": 4}, {"x": 9, "y": 6}])

    def test_axis_swapped_reflection_and_diagonal_reflection_keep_corner_identity(self):
        surface = measured([xaml_node("surface", "Border")])[0]
        surface["style"]["corner_radii"] = [1, 2, 3, 4]
        surface["transform"].update(m11=0, m12=1, m21=1, m22=0)
        radii, widths = transformed_box_edges(surface, [1, 2, 3, 4])
        self.assertEqual(widths, [4, 3, 2, 1])
        self.assertEqual([r["x"] for r in radii], [1, 4, 3, 2])
        surface["transform"].update(m11=-1, m12=0, m21=0, m22=1)
        radii, widths = transformed_box_edges(surface, [1, 2, 3, 4])
        self.assertEqual(widths, [1, 4, 3, 2])
        self.assertEqual([r["x"] for r in radii], [2, 1, 4, 3])

    def test_non_axis_rotation_is_not_treated_as_a_quarter_turn(self):
        surface = measured([xaml_node("surface", "Border")])[0]
        surface["transform"].update(m11=.707, m12=.707, m21=-.707, m22=.707)
        self.assertIsNone(transformed_box_edges(surface, [1, 1, 1, 1]))

    def test_avatar_owns_one_letter_background_but_keeps_image_icon_and_state_dot(self):
        face = xaml_node("face", "PersonPicture", bounds=box(10, 20, 28, 28))
        paint = xaml_node("paint", "Border", parent="face", bounds=face["bounds"])
        paint["style"].update(background=[230, 200, 210, 255], corner_radius=8)
        initial = xaml_node("initial", text="R", parent="paint", bounds=box(18, 25, 10, 18))
        dot = xaml_node("dot", "Ellipse", bounds=box(32, 42, 10, 10))
        dot["style"]["background"] = [0, 120, 0, 255]
        result = self.capture(measured([face, paint, initial, dot]), [uia_node("uia-face", "Image", bounds=face["bounds"])])
        elements = self.by_id(result)
        self.assertEqual((elements["face"]["kind"], elements["face"]["text"]), ("avatar", "R"))
        self.assertEqual(elements["face"]["style"]["corner_radius"], 8)
        self.assertNotIn("paint", elements)
        self.assertNotIn("initial", elements)
        self.assertIn("dot", elements)
        photo = xaml_node("photo", "Image", parent="face", bounds=face["bounds"])
        photo["icon"] = {"source": "image", "glyph": "http://127.0.0.1:39321/api/avatar/member.png"}
        result = self.capture(measured([face, photo]), [uia_node("uia-face", "Image", bounds=face["bounds"])])
        self.assertIn("photo", self.by_id(result))

    def test_avatar_decorative_border_ring_is_not_silently_discarded(self):
        face = xaml_node("face", "PersonPicture", bounds=box(10, 20, 28, 28))
        paint = xaml_node("paint", "Border", parent="face", bounds=face["bounds"])
        paint["style"]["background"] = [230, 200, 210, 255]
        ring = xaml_node("ring", "Border", parent="face", bounds=face["bounds"])
        ring["style"].update(border_color=[150, 50, 50, 255], border_width=2)
        result = self.capture(measured([face, paint, ring]), [uia_node("uia-face", "Image", bounds=face["bounds"])])
        self.assertIn("ring", self.by_id(result))

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
        self.assertEqual(element["evidence"]["provider_fonts"][0]["family_name"], "Microsoft YaHei UI")
        self.assertIsNone(element["evidence"]["provider_fonts"][0]["postscript_name"])
        self.assertNotEqual(element["evidence"]["provider_fonts"][0]["family_name"], text["font_family"])
        self.assertIsNone(element["style"]["rendered_fonts"], "UIA's declared name is not an observed physical glyph-run face")

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

    @staticmethod
    def rich_fixture():
        owner = xaml_node("rich", "RichTextBlock", "标题正文", bounds=box(10, 20, 110, 20))
        runs = [
            {"type": "Run", "text": "标题", "start_offset": 1, "end_offset": 3,
             "font_size": 14, "font_weight": 700, "foreground": [27, 27, 26, 255],
             "font_family": "Configured family", "bounds": [box(10, 20, 30, 20)],
             "coordinate_space": "content-window", "geometry_complete": True},
            {"type": "Run", "text": "正文", "start_offset": 5, "end_offset": 7,
             "font_size": 13, "font_weight": 400, "foreground": [90, 88, 83, 255],
             "font_family": "Configured family", "bounds": [box(40, 20, 30, 18)],
             "coordinate_space": "content-window", "geometry_complete": True},
        ]
        owner["layout"].update(rich_text_runs=runs, character_boxes_coordinate_space="content-window")
        witness = uia_node("uia-rich", "Document", "标题正文", bounds=owner["bounds"])
        witness["text_pattern"] = {"visible_ranges": [{
            "format_runs": [
                {"text": "标题", "bounds": runs[0]["bounds"], "attributes": {"font_family": "Segoe UI Variable"},
                 "attribute_status": {"font_family": "measured"}},
                {"text": "正文", "bounds": runs[1]["bounds"], "attributes": {"font_family": "Microsoft YaHei UI"},
                 "attribute_status": {"font_family": "measured"}},
            ],
        }]}
        return owner, witness

    def test_measured_rich_runs_are_independent_visible_elements(self):
        owner, witness = self.rich_fixture()
        result = self.capture(measured([owner]), [witness])
        elements = self.by_id(result)
        self.assertNotIn("rich", elements, "The glyph-only RichTextBlock is a layout owner, not an extra card")
        first, second = elements["rich:run:0"], elements["rich:run:1"]
        self.assertEqual((first["text"], second["text"]), ("标题", "正文"))
        self.assertEqual((first["style"]["font_weight"], second["style"]["font_weight"]), (700, 400))
        self.assertEqual((first["style"]["font_size"], second["style"]["font_size"]), (14, 13))
        self.assertEqual(first["bounds"], box(10, 20, 30, 20))
        self.assertEqual(second["style"]["foreground"], [90, 88, 83, 255])
        self.assertFalse(any(issue.get("property") == "rich_text_runs" for issue in result["coverage"]["unmeasured"]))
        self.assertEqual(first["evidence"]["text_run_source"]["start_offset"], 1)
        self.assertEqual(result["coverage"]["recorded_text_leaves"], 2)

    def test_real_readonly_code_document_keeps_owner_and_measured_ranges(self):
        owner, witness = self.rich_fixture()
        owner["type"] = "WorkspaceCodeView"
        owner["interaction_evidence"] = {"is_control": True, "is_tab_stop": True, "is_hit_test_visible": True}
        witness["class_name"] = "WorkspaceCodeView"
        owner["layout"]["document_evidence"] = {"whole_story": owner["text"] + "\r", "whole_story_use_lf": owner["text"] + "\n"}
        witness["name"] = ""
        witness["text_pattern"]["document"] = {"text": owner["text"] + "\r"}
        for run in owner["layout"]["rich_text_runs"]:
            run["type"] = "RichEditTextRange"
        result = self.capture(measured([owner]), [witness])
        elements = self.by_id(result)
        self.assertEqual(elements["rich"]["kind"], "code")
        self.assertEqual(elements["rich"]["text"], "")
        self.assertEqual(elements["rich:run:0"]["text"], "标题")
        self.assertEqual(elements["rich:run:1"]["bounds"], box(40, 20, 30, 18))
        self.assertIsNone(elements["rich:run:0"]["style"]["rendered_fonts"],
                          "TOM/UIA requested font properties are not actual fallback-face evidence")
        self.assertEqual(result["coverage"]["recorded_text_leaves"], 2)

    def test_incomplete_native_code_range_still_fails_measurement_coverage(self):
        owner, witness = self.rich_fixture()
        owner["type"] = "WorkspaceCodeView"
        owner["layout"]["rich_text_runs"][0]["geometry_complete"] = False
        result = self.capture(measured([owner]), [witness])
        self.assertTrue(any(issue.get("id") == "rich:run:0" and issue.get("property") == "rich_text_runs"
                            for issue in result["coverage"]["unmeasured"]))

    def test_rich_run_font_identity_uses_only_intersecting_actual_uia_range(self):
        owner, witness = self.rich_fixture()
        result = self.capture(measured([owner]), [witness])
        elements = self.by_id(result)
        self.assertEqual([f["family_name"] for f in elements["rich:run:0"]["evidence"]["provider_fonts"]], ["Segoe UI Variable"])
        self.assertEqual([f["family_name"] for f in elements["rich:run:1"]["evidence"]["provider_fonts"]], ["Microsoft YaHei UI"])
        self.assertIsNone(elements["rich:run:0"]["style"]["rendered_fonts"])
        self.assertTrue(any(p.get("source") == "uia-rich" and "TextElement Run" in p["reason"] for p in result["projection"]))
        self.assertFalse(any(issue.get("id") == "uia-rich" and issue.get("property") == "render correspondence"
                             for issue in result["coverage"]["unmeasured"]))

    def test_stretched_uia_layout_slot_uses_its_measured_text_range_for_correspondence(self):
        owner, witness = self.rich_fixture()
        witness["bounds"] = box(10, 20, 400, 60)
        witness["text_pattern"]["document"] = {"text": owner["text"], "bounds": [deepcopy(owner["bounds"])]}
        result = self.capture(measured([owner]), [witness])
        first = self.by_id(result)["rich:run:0"]
        self.assertEqual(first["evidence"]["provider_fonts"][0]["family_name"], "Segoe UI Variable")
        self.assertEqual(first["evidence"]["uia_font_ranges"][0]["uia_id"], "uia-rich")

    def test_wrong_text_in_matching_uia_range_cannot_supply_a_font(self):
        owner, witness = self.rich_fixture()
        witness["name"] = "unrelated"
        witness["text_pattern"]["document"] = {"text": "unrelated", "bounds": [deepcopy(owner["bounds"])]}
        result = self.capture(measured([owner]), [witness])
        self.assertIsNone(self.by_id(result)["rich:run:0"]["style"]["rendered_fonts"])
        self.assertEqual(self.by_id(result)["rich:run:0"]["evidence"]["provider_fonts"], [])

    def test_uia_provider_family_cannot_be_used_when_actual_cmap_cannot_cover_text(self):
        owner, witness = self.rich_fixture()
        coverage = {"status": "provider-family-cannot-cover-text", "provider_family_name": "Segoe UI Variable",
                    "missing_scalars": ["U+6807", "U+9898"], "proves_actual_render_face": False,
                    "reason": "Actual physical family has no glyph for the visible characters"}
        witness["text_pattern"]["visible_ranges"][0]["format_runs"][0]["font_family_coverage"] = coverage
        result = self.capture(measured([owner]), [witness])
        self.assertIsNone(self.by_id(result)["rich:run:0"]["style"]["rendered_fonts"])
        self.assertEqual(self.by_id(result)["rich:run:0"]["evidence"]["provider_fonts"], [])
        self.assertTrue(any(issue.get("font_family_coverage", {}).get("missing_scalars") == coverage["missing_scalars"]
                            for issue in result["coverage"]["unmeasured"]))
        self.assertEqual(self.by_id(result)["rich:run:0"]["evidence"]["font_family_evidence"][0], coverage)

    def test_supported_character_coverage_is_not_claimed_as_actual_glyph_run_identity(self):
        owner, witness = self.rich_fixture()
        coverage = {"status": "family-can-cover-scalars", "proves_actual_render_face": False,
                    "provider_family_name": "Segoe UI Variable", "missing_scalars": []}
        witness["text_pattern"]["visible_ranges"][0]["format_runs"][0]["font_family_coverage"] = coverage
        result = self.capture(measured([owner]), [witness])
        font = self.by_id(result)["rich:run:0"]["evidence"]["provider_fonts"][0]
        self.assertEqual(font["family_name"], "Segoe UI Variable")
        self.assertFalse(font["proves_actual_render_face"])
        self.assertIsNone(self.by_id(result)["rich:run:0"]["style"]["rendered_fonts"])
        self.assertTrue(any(issue.get("id") == "rich:run:0" and issue.get("property") == "style.rendered_fonts.actual_face"
                            for issue in result["coverage"]["unmeasured"]))

    def test_unreadable_font_metadata_does_not_fall_back_to_declared_xaml_family(self):
        owner, witness = self.rich_fixture()
        witness["text_pattern"]["visible_ranges"][0]["format_runs"][0]["font_family_coverage"] = {
            "status": "unresolved", "reason": "Physical font metadata is unavailable", "proves_actual_render_face": False}
        result = self.capture(measured([owner]), [witness])
        self.assertIsNone(self.by_id(result)["rich:run:0"]["style"]["rendered_fonts"])
        self.assertEqual(self.by_id(result)["rich:run:0"]["evidence"]["provider_fonts"], [])
        self.assertTrue(any("Physical font metadata" in issue.get("reason", "") for issue in result["coverage"]["unmeasured"]))

    def test_rich_owner_own_background_retained_without_duplicating_leaf_paint(self):
        owner, witness = self.rich_fixture()
        owner["style"]["background"] = [240, 240, 240, 255]
        result = self.capture(measured([owner]), [witness])
        elements = self.by_id(result)
        self.assertEqual(elements["rich"]["kind"], "card")
        self.assertEqual(elements["rich"]["text"], "")
        self.assertIsNone(elements["rich"]["style"]["font_weight"])
        self.assertEqual(elements["rich:run:0"]["parent"], "rich")
        self.assertEqual(elements["rich:run:0"]["style"]["background"], [0, 0, 0, 0])

    def test_rich_runs_retain_the_actual_text_owners_independent_break_policies(self):
        owner, witness = self.rich_fixture()
        owner["layout"].update(wrap="character", normal_break_strategy="word", emergency_break_strategy="break-unbreakable",
                               line_break_configuration={"source": "synthetic live RichTextBlock.TextWrapping fixture", "owner": "rich",
                                                         "raw": {"text_wrapping": "Wrap", "text_wrapping_value": 2}})
        result = self.by_id(self.capture(measured([owner]), [witness]))
        for rid in ("rich:run:0", "rich:run:1"):
            self.assertEqual(result[rid]["layout"]["normal_break_strategy"], "word")
            self.assertEqual(result[rid]["layout"]["emergency_break_strategy"], "break-unbreakable")
            self.assertEqual(result[rid]["evidence"]["line_break_configuration"]["owner"], "rich")
            self.assertEqual(result[rid]["evidence"]["text_run_source"]["owner"], "rich")
        for key in ("normal_break_strategy", "emergency_break_strategy", "line_break_configuration"):
            owner["layout"].pop(key)
        unknown = self.capture(measured([owner]), [witness])
        self.assertTrue(any(row["id"] == "rich:run:0" and row["property"] == "layout.break_strategy"
                            for row in unknown["coverage"]["unmeasured"]))
        self.assertIsNone(self.by_id(unknown)["rich:run:0"]["layout"]["normal_break_strategy"])

    def test_missing_rich_run_font_does_not_borrow_adjacent_run_font(self):
        owner, witness = self.rich_fixture()
        witness["text_pattern"]["visible_ranges"][0]["format_runs"][1]["attribute_status"]["font_family"] = "unsupported"
        result = self.capture(measured([owner]), [witness])
        self.assertIsNone(self.by_id(result)["rich:run:1"]["style"]["rendered_fonts"])
        self.assertTrue(any(issue.get("id") == "rich:run:1" and issue.get("property") == "style.rendered_fonts"
                            for issue in result["coverage"]["unmeasured"]))

    def test_ambiguous_same_box_rich_provider_is_not_used_as_font_fallback(self):
        owner, witness = self.rich_fixture()
        second = deepcopy(witness)
        second["id"] = "uia-unrelated"
        second["text_pattern"]["visible_ranges"][0]["format_runs"][0]["attributes"]["font_family"] = "Unrelated family"
        result = self.capture(measured([owner]), [witness, second])
        self.assertIsNone(self.by_id(result)["rich:run:0"]["style"]["rendered_fonts"])
        self.assertTrue(any(issue.get("property") == "UIA text-owner correspondence" for issue in result["coverage"]["unmeasured"]))
        self.assertFalse(any(item.get("source") in {"uia-rich", "uia-unrelated"} and "TextElement Run" in item.get("reason", "")
                             for item in result["projection"]))

    def test_incomplete_rich_run_geometry_remains_an_explicit_gap(self):
        owner, witness = self.rich_fixture()
        owner["layout"]["rich_text_runs"][0]["geometry_complete"] = False
        result = self.capture(measured([owner]), [witness])
        self.assertTrue(any(issue.get("id") == "rich:run:0" and issue.get("property") == "rich_text_runs"
                            for issue in result["coverage"]["unmeasured"]))

    def test_single_measured_text_run_can_be_owned_by_its_real_button_label(self):
        button = xaml_node("button", "Button")
        label = xaml_node("label", text="发送", parent="button", bounds=box(20, 25, 40, 18))
        glyph_box = box(20, 25, 26, 18)
        label["layout"]["rich_text_runs"] = [{
            "type": "Run", "text": "发送", "font_size": 12, "font_weight": 600,
            "foreground": [27, 27, 26, 255], "font_family": "Configured family", "bounds": [glyph_box],
            "coordinate_space": "content-window", "geometry_complete": True,
        }]
        uia_label = uia_node("uia-label", "Text", "发送", parent="uia-button", bounds=label["bounds"])
        uia_label["text_pattern"] = {"visible_ranges": [{
            "text": "发送", "bounds": [glyph_box], "attributes": {"font_family": "Segoe UI Variable"},
            "attribute_status": {"font_family": "measured"},
        }]}
        result = self.capture(measured([button, label]), [uia_node("uia-button", "Button", "发送"), uia_label])
        elements = self.by_id(result)
        self.assertEqual(elements["button"]["text"], "发送")
        self.assertEqual(elements["button"]["style"]["font_size"], 12)
        self.assertNotIn("label:run:0", elements)
        self.assertEqual(elements["button"]["evidence"]["text_bounds"], [glyph_box])

    def test_single_run_retains_its_unambiguous_actual_uia_text_owner_name(self):
        owner = xaml_node("owner", text="Organizations", bounds=box(18, 144, 75.3984375, 15.9609375))
        owner["layout"]["rich_text_runs"] = [{
            "type": "Run", "text": "Organizations", "font_size": 12, "font_weight": 400,
            "foreground": [143, 140, 134, 255], "bounds": [box(18, 144, 75.3984375, 15.9609375)],
            "coordinate_space": "content-window", "geometry_complete": True}]
        witness = uia_node("uia-owner", name="Organizations", bounds=box(18, 144, 224, 16))
        witness["text_pattern"] = {"document": {"text": "Organizations", "bounds": [box(18, 144, 75, 15)]}}
        result = self.capture(measured([owner]), [witness])
        actual = self.by_id(result)["owner:run:0"]
        self.assertEqual(actual["name"], "Organizations")
        self.assertEqual(actual["evidence"]["accessible_name_evidence"]["uia_id"], "uia-owner")
        self.assertEqual(actual["evidence"]["accessible_name_evidence"]["ownership"], "whole text owner represented by one measured Run")
        # Keep an actual custom name, even when it differs from visible text.
        witness["name"] = "Organization summary"
        result = self.capture(measured([owner]), [witness])
        self.assertEqual(self.by_id(result)["owner:run:0"]["name"], "Organization summary")

    def test_rich_parent_name_is_not_fabricated_for_each_text_fragment(self):
        owner, witness = self.rich_fixture()
        result = self.capture(measured([owner]), [witness])
        self.assertEqual(self.by_id(result)["rich:run:0"]["name"], "")
        self.assertEqual(self.by_id(result)["rich:run:1"]["name"], "")

    def test_ambiguous_text_owner_names_are_not_resolved_by_copying_visible_text(self):
        owner, witness = self.rich_fixture()
        owner["text"] = "标题"
        owner["layout"]["rich_text_runs"] = [owner["layout"]["rich_text_runs"][0]]
        witness["name"] = "标题"
        duplicate = deepcopy(witness); duplicate["id"] = "uia-other"
        result = self.capture(measured([owner]), [witness, duplicate])
        self.assertEqual(self.by_id(result)["rich:run:0"]["name"], "")

    def test_multiline_measured_run_keeps_exact_text_and_line_geometry(self):
        owner, witness = self.rich_fixture()
        owner["text"] = "一\n二"
        owner["layout"]["rich_text_runs"] = [{
            "type": "Run", "text": "一\n二", "font_size": 13, "font_weight": 400,
            "foreground": [27, 27, 26, 255], "bounds": [box(10, 20, 15, 18), box(10, 40, 15, 18)],
            "coordinate_space": "content-window", "geometry_complete": True,
        }]
        owner["bounds"] = owner["visible_bounds"] = box(10, 20, 110, 50)
        result = self.capture(measured([owner]), [witness])
        actual = self.by_id(result)["rich:run:0"]
        self.assertEqual(actual["text"], "一\n二")
        self.assertEqual(actual["layout"]["line_count"], 2)
        self.assertEqual(actual["bounds"], box(10, 20, 15, 38))

    def test_proven_offscreen_uia_diagnostics_are_preserved_as_nonvisible(self):
        hidden = uia_node("uia-hidden", name="Hidden")
        hidden["bounds"] = None
        hidden["state"]["offscreen"] = True
        message = "BoundingRectangle is empty; raw x=Infinity, y=Infinity, width=-Infinity, height=-Infinity"
        hidden["measurement_errors"] = [message]
        result = self.capture(measured([xaml_node("text", text="内容")]), [hidden, uia_node("uia-text", name="内容")],
                              uia_changes={"extraction_errors": ["uia-hidden: " + message]})
        self.assertFalse(result["extraction_errors"])
        self.assertFalse(any(issue.get("id") == "uia-hidden" for issue in result["coverage"]["unmeasured"]))
        self.assertTrue(any(diagnostic.get("id") == "uia-hidden" and "Infinity" in diagnostic["diagnostic"]
                            for diagnostic in result["nonvisible_diagnostics"]))

    @staticmethod
    def failed_text_range():
        # Actual 38af737 file-code HRESULT/type/API (progress seq 9993/10038,
        # uia-196/197). Text is synthetic: the old capture did not retain the
        # failed format range's real text/endpoints, so none are invented here.
        return {"text": "fixture range", "bounds": None, "managed_bounds": None, "bounds_status": "error",
                "bounds_error": {"api": "Managed TextRange.GetBoundingRectangles",
                                 "exception_type": "System.Runtime.InteropServices.COMException",
                                 "hresult": -2147418113, "hresult_hex": "0x8000FFFF", "message": "发生意外。",
                                 "exception": "System.Runtime.InteropServices.COMException (0x8000FFFF): 发生意外。\n"
                                              "at MS.Internal.Automation.UiaCoreApi.TextRange_GetBoundingRectangles(SafeTextRangeHandle hobj)"},
                "attributes": {"font_family": "Fixture font"}, "attribute_status": {"font_family": "measured"}}

    def test_failed_uia_range_bounds_remain_null_with_original_hresult_and_no_projection_crash(self):
        owner = xaml_node("text", text="fixture range")
        owner["layout"].update(line_count=None, character_boxes=None, character_boxes_coordinate_space="content-window")
        provider = uia_node("uia-text", name=owner["text"])
        failed = self.failed_text_range()
        visible_range = deepcopy(failed)
        visible_range["format_runs"] = [deepcopy(failed)]
        provider["text_pattern"] = {"document": deepcopy(failed), "visible_ranges": [visible_range]}
        original_error = "uia-text: Managed TextRange.GetBoundingRectangles: 0x8000FFFF COMException: 发生意外。"
        result = self.capture(measured([owner]), [provider], uia_changes={"extraction_errors": [original_error]})
        self.assertIn(original_error, result["extraction_errors"])
        failures = result["capture_evidence"]["uia_text_range_failures"]
        self.assertEqual({row["range_path"] for row in failures}, {
            "text_pattern.document", "text_pattern.visible_ranges[0]", "text_pattern.visible_ranges[0].format_runs[0]"})
        for failure in failures:
            self.assertIsNone(failure["range_evidence"]["bounds"])
            self.assertIsNone(failure["range_evidence"]["managed_bounds"])
            self.assertEqual(failure["range_evidence"]["bounds_error"], failed["bounds_error"])
            self.assertIn(failure, result["coverage"]["unmeasured"])
        self.assertIsNone(self.by_id(result)["text"]["layout"]["line_count"])
        self.assertTrue(any(row["property"] == "evidence.text_bounds" for row in result["coverage"]["unmeasured"]))

    def test_successful_native_com_bounds_do_not_replace_failed_managed_range(self):
        owner = xaml_node("text", text="fixture range")
        owner["layout"].update(line_count=None, character_boxes=None, character_boxes_coordinate_space="content-window")
        provider = uia_node("uia-text", name=owner["text"])
        failed = self.failed_text_range()
        native_range = {"text": owner["text"], "bounds": [box(12, 22, 70, 18)], "bounds_status": "measured"}
        provider["text_pattern"] = {
            "document": deepcopy(failed), "visible_ranges": [deepcopy(failed)],
            "native_com": {"status": "incomplete", "document": deepcopy(native_range), "visible_ranges": [deepcopy(native_range)],
                           "error": "Managed range bounds failed; the independent COM observation is retained but cannot prove the missing managed projection."}}
        result = self.capture(measured([owner]), [provider])
        actual = self.by_id(result)["text"]
        self.assertIsNone(actual["evidence"]["text_bounds"])
        self.assertIsNone(actual["layout"]["line_count"])
        failures = result["capture_evidence"]["uia_text_range_failures"]
        self.assertEqual(len(failures), 2)
        self.assertTrue(all(row["range_path"].startswith("text_pattern.") and "native_com" not in row["range_path"] for row in failures))
        self.assertTrue(all(row["range_evidence"]["bounds"] is None for row in failures))
        self.assertTrue(any(row["property"] == "UIA text_range.bounds" for row in result["coverage"]["unmeasured"]))

    def test_failed_uia_format_run_does_not_erase_independent_xaml_text_bounds_or_its_failure(self):
        owner, provider = self.rich_fixture()
        provider["text_pattern"]["document"] = self.failed_text_range()
        provider["text_pattern"]["document"]["text"] = owner["text"]
        provider["text_pattern"]["visible_ranges"][0]["format_runs"][0] = self.failed_text_range()
        result = self.capture(measured([owner]), [provider])
        actual = self.by_id(result)["rich:run:0"]
        self.assertEqual(actual["bounds"], box(10, 20, 30, 20))
        self.assertTrue(any(row["range_path"] == "text_pattern.visible_ranges[0].format_runs[0]"
                            for row in result["capture_evidence"]["uia_text_range_failures"]))
        self.assertTrue(any(row["property"] == "UIA text_range.bounds" for row in result["coverage"]["unmeasured"]))

    def test_null_xaml_run_geometry_fails_coverage_without_crashing_text_helpers(self):
        owner, provider = self.rich_fixture()
        owner["layout"]["rich_text_runs"][0]["bounds"] = None
        owner["layout"]["rich_text_runs"][0]["geometry_complete"] = False
        result = self.capture(measured([owner]), [provider])
        self.assertTrue(any(row["id"] == "rich:run:0" and row["property"] == "rich_text_runs"
                            for row in result["coverage"]["unmeasured"]))
        self.assertNotIn("rich:run:0", self.by_id(result))
        self.assertIn("rich:run:1", self.by_id(result))

    def test_successful_empty_range_array_is_distinct_from_unknown_null(self):
        provider = uia_node("uia-text", name="fixture range")
        provider["text_pattern"] = {"document": {"text": "", "bounds": [], "managed_bounds": []}, "visible_ranges": []}
        result = self.capture(measured([xaml_node("text", text="fixture range")]), [provider])
        self.assertNotIn("uia_text_range_failures", result["capture_evidence"])
        self.assertFalse(any(row["property"] == "UIA text_range.bounds" for row in result["coverage"]["unmeasured"]))

    def test_unknown_or_visible_uia_rect_errors_are_not_exempted(self):
        for offscreen in (None, False):
            with self.subTest(offscreen=offscreen):
                bad = uia_node("uia-bad", name="内容")
                bad["bounds"] = None
                bad["state"]["offscreen"] = offscreen
                bad["measurement_errors"] = ["BoundingRectangle is empty; raw x=Infinity"]
                result = self.capture(measured([xaml_node("text", text="内容")]), [bad],
                                      uia_changes={"extraction_errors": ["uia-bad: BoundingRectangle is empty; raw x=Infinity"]})
                self.assertTrue(result["extraction_errors"])
                self.assertTrue(any(issue.get("id") == "uia-bad" for issue in result["coverage"]["unmeasured"]))

    def test_offscreen_parent_tree_failure_is_not_a_nonvisible_measurement(self):
        hidden = uia_node("uia-hidden", name="Hidden")
        hidden["state"]["offscreen"] = True
        hidden["measurement_errors"] = ["BoundingRectangle is empty; raw x=Infinity"]
        own_error = "uia-hidden: " + hidden["measurement_errors"][0]
        for traversal_error in ("uia-hidden: tree traversal/identity: ElementNotAvailableException: child unavailable",
                                "uia-hidden: ElementNotAvailableException: child unavailable"):
            with self.subTest(error=traversal_error):
                result = self.capture(measured([xaml_node("text", text="内容")]),
                                      [hidden, uia_node("uia-text", name="内容")],
                                      uia_changes={"extraction_errors": [own_error, traversal_error]})
                self.assertEqual(result["extraction_errors"], [traversal_error])
                self.assertTrue(any(item["diagnostic"] == own_error for item in result["nonvisible_diagnostics"]))
                self.assertFalse(any(item["diagnostic"] == traversal_error for item in result["nonvisible_diagnostics"]))

    def test_offscreen_numeric_json_path_keeps_raw_reason_without_failing_visible_nodes(self):
        hidden = uia_node("uia-hidden", name="Hidden")
        hidden["state"]["offscreen"] = True
        result = self.capture(measured([xaml_node("text", text="内容")]), [hidden, uia_node("uia-text", name="内容")],
                              uia_changes={"extraction_errors": ["/raw_nodes/0/bounds/x: non-finite actual UIA measurement Infinity"]})
        self.assertFalse(result["extraction_errors"])
        self.assertEqual(result["nonvisible_diagnostics"][0]["id"], "uia-hidden")

    def test_actual_scaled_vector_stroke_not_overwritten_by_source_width(self):
        icon = xaml_node("vector", "ReferenceVectorIcon", bounds=box(10, 20, 16, 16))
        icon["icon"] = {"source": "svg", "glyph": "fixture actual path"}
        icon["style"]["stroke_width"] = 1.7 * 16 / 24
        icon["vector_stroke_width"] = 1.7
        icon["stroke_evidence"] = {"raw_width": 1.7, "scale_x": 16 / 24, "scale_y": 16 / 24,
                                   "source": "Shape.StrokeThickness and actual Shape.TransformToVisual(content-root)"}
        result = self.capture(measured([icon]), [uia_node("uia-icon", "Image", bounds=icon["bounds"])])
        actual = self.by_id(result)["vector"]
        self.assertAlmostEqual(actual["style"]["stroke_width"], 1.7 * 16 / 24)
        self.assertEqual(actual["evidence"]["stroke_evidence"]["raw_width"], 1.7)

    def test_actual_selectorbar_listitem_provider_is_a_tab_witness(self):
        tab = xaml_node("tab", "SelectorBarItem", "Overview")
        witness = uia_node("uia-tab", "ListItem", "Overview", class_name="Microsoft.UI.Xaml.Controls.SelectorBarItem")
        witness["state"]["selected"] = True
        result = self.capture(measured([tab]), [witness])
        actual = self.by_id(result)["tab"]
        self.assertEqual(actual["kind"], "tab")
        self.assertEqual(actual["evidence"]["uia_id"], "uia-tab")
        self.assertTrue(actual["state"]["selected"])

    def test_ordinary_listitem_is_not_a_tab_by_position_alone(self):
        tab = xaml_node("tab", "SelectorBarItem", "Overview")
        witness = uia_node("uia-listitem", "ListItem", "Overview", class_name="ListViewItem")
        result = self.capture(measured([tab]), [witness])
        self.assertIsNone(self.by_id(result)["tab"]["evidence"]["uia_id"])

    def test_noninteractive_text_does_not_inherit_uia_default_enabled_or_focus_state(self):
        result = self.capture(measured([xaml_node("text", text="内容")]), [uia_node("uia-text", name="内容")])
        actual = self.by_id(result)["text"]
        self.assertIsNone(actual["state"]["enabled"])
        self.assertIsNone(actual["state"]["focused"])
        self.assertFalse(actual["evidence"]["interaction_applicability"]["applicable"])
        self.assertTrue(actual["evidence"]["interaction_applicability"]["uia_state"]["enabled"])

    def test_interactive_native_button_retains_measured_disabled_and_focus_state(self):
        witness = uia_node("uia-button", "Button", "发送")
        witness["state"].update(enabled=False, focused=False, focusable=False)
        result = self.capture(measured([xaml_node("button", "Button", "发送")]), [witness])
        actual = self.by_id(result)["button"]
        self.assertFalse(actual["state"]["enabled"])
        self.assertFalse(actual["state"]["focused"])

    def test_native_checkable_control_keeps_measured_indeterminate_state(self):
        for indeterminate in (False, True):
            with self.subTest(indeterminate=indeterminate):
                control = xaml_node("check", "CheckBox", "选项")
                witness = uia_node("uia-check", "CheckBox", "选项")
                witness["state"].update(checked=None if indeterminate else False, indeterminate=indeterminate)
                result = self.capture(measured([control]), [witness])
                self.assertIs(self.by_id(result)["check"]["state"]["indeterminate"], indeterminate)

    def test_text_with_actual_action_pattern_is_not_declared_noninteractive(self):
        witness = uia_node("uia-text", name="行动")
        witness["supported_patterns"] = ["InvokePatternIdentifiers.Pattern"]
        witness["state"]["focused"] = True
        result = self.capture(measured([xaml_node("text", text="行动")]), [witness])
        actual = self.by_id(result)["text"]
        self.assertTrue(actual["state"]["enabled"])
        self.assertTrue(actual["state"]["focused"])

    def test_unknown_text_focus_applicability_remains_a_coverage_gap(self):
        witness = uia_node("uia-text", name="内容")
        witness["state"]["focusable"] = None
        result = self.capture(measured([xaml_node("text", text="内容")]), [witness])
        self.assertTrue(any(item.get("property") == "state.interaction_applicability"
                            for item in result["coverage"]["unmeasured"]))
        self.assertIsNone(self.by_id(result)["text"]["evidence"]["interaction_applicability"]["applicable"])

    def test_no_reported_accessible_name_is_empty_without_copying_visible_label(self):
        witness = uia_node("uia-button", "Button", None)
        witness["unsupported_properties"] = ["AutomationElementIdentifiers.NameProperty"]
        result = self.capture(measured([xaml_node("button", "Button", "发送")]), [witness])
        actual = self.by_id(result)["button"]
        self.assertEqual(actual["text"], "发送")
        self.assertEqual(actual["name"], "")
        self.assertIsNone(actual["evidence"]["accessible_name_evidence"]["reported"])
        self.assertEqual(actual["evidence"]["accessible_name_evidence"]["status"], "not-provided")

    def test_native_status_token_owns_its_single_label_and_template_paint_once(self):
        for native_type, kind in (("OverviewChipView", "chip"), ("OverviewBadgeView", "badge")):
            with self.subTest(native_type=native_type):
                token = xaml_node("token", native_type)
                token["interaction_evidence"].update(is_control=True, is_tab_stop=False, is_hit_test_visible=False)
                paint = xaml_node("paint", "ContentPresenter", parent="token")
                paint["style"]["background"] = [240, 240, 240, 255]
                label = xaml_node("label", text="批准", parent="paint", bounds=box(20, 25, 40, 18))
                result = self.capture(measured([token, paint, label]), [uia_node("uia-label", name="批准", bounds=label["bounds"])])
                actual = self.by_id(result)["token"]
                self.assertEqual((actual["kind"], actual["text"]), (kind, "批准"))
                self.assertEqual(actual["style"]["background"], [240, 240, 240, 255])
                self.assertEqual(len(result["elements"]), 1)
                self.assertFalse(any(item.get("id") == "token" and item.get("property") == "UIA correspondence"
                                     for item in result["coverage"]["unmeasured"]))

    @staticmethod
    def host_fixture():
        viewport = box(0, 0, 1024, 700)
        root = xaml_node("root", "Grid", bounds=viewport, region="window")
        primary = uia_node("primary", "Window", bounds=box(-8, -31, 1040, 739),
                           class_name="WinUIDesktopWin32WindowClass", root_kind="primary-window", native_window_handle=12345)
        bridge = uia_node("bridge", "Pane", parent="primary", bounds=viewport,
                          class_name="Microsoft.UI.Content.DesktopChildSiteBridge")
        site = uia_node("site", "Pane", parent="bridge", bounds=viewport, class_name="InputSiteWindowClass")
        return {"primary_hwnd": 12345, "viewport": deepcopy(VIEWPORT), "raw_nodes": [primary, bridge, site]}, [root]

    def test_exact_main_window_host_chain_owns_the_single_content_root(self):
        uia, roots = self.host_fixture()
        ownership = host_container_ownership(uia, roots)
        self.assertEqual([entry["source"] for entry in ownership], ["primary", "bridge", "site"])
        self.assertTrue(all(entry["owner"] == "root" for entry in ownership))
        self.assertEqual(ownership[0]["host_evidence"]["bounds"]["x"], -8)

    def test_unrelated_popup_or_wrong_host_geometry_is_not_implicitly_owned(self):
        for change in ("popup", "wrong-hwnd", "wrong-bounds", "wrong-parent", "ambiguous"):
            with self.subTest(change=change):
                uia, roots = self.host_fixture()
                if change == "popup":
                    uia["raw_nodes"][0]["root_kind"] = "process-popup-or-window"
                elif change == "wrong-hwnd":
                    uia["primary_hwnd"] = 999
                elif change == "wrong-bounds":
                    uia["raw_nodes"][1]["bounds"]["width"] -= 1
                elif change == "wrong-parent":
                    uia["raw_nodes"][2]["parent"] = "primary"
                else:
                    duplicate = deepcopy(uia["raw_nodes"][1])
                    duplicate["id"] = "second-bridge"
                    uia["raw_nodes"].append(duplicate)
                self.assertEqual(host_container_ownership(uia, roots), [])


if __name__ == "__main__":
    unittest.main()
