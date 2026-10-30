"""Synthetic new-producer contracts and a separately labelled historic receipt.

These fixtures do not claim that a new capture has already run in CI.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest

import test_windows_elements as projection_fixtures
from windows_selector_labels import (CONTRACT, SOURCE, PAINT_CONTRACT, PAINT_SOURCE,
                                     selector_content_labels, selector_label_candidate, selector_paint_surfaces)


def fixture(extra=None):
    f = projection_fixtures
    nodes = [
        f.xaml_node("tab", "SelectorBarItem", "The API text is not used", bounds=f.box(10, 20, 80, 30)),
        f.xaml_node("root", "Grid", parent="tab", bounds=f.box(10, 20, 80, 30)),
        f.xaml_node("presenter", "ContentPresenter", parent="root", bounds=f.box(10, 20, 80, 30)),
        f.xaml_node("content", "NativeShadowPanel", parent="presenter", bounds=f.box(10, 20, 80, 30),
                    declared_content_owner="tab", declared_content_source="FrameworkElement.Tag UIElement in the actual visual tree"),
        f.xaml_node("surface", "Border", parent="content", bounds=f.box(10, 20, 80, 30)),
        f.xaml_node("label", text="Light", parent="surface", bounds=f.box(19, 22, 42, 19)),
    ]
    nodes[4]["style"]["background"] = [255, 255, 255, 255]
    if extra:
        nodes.extend(extra)
    nodes = f.measured(nodes)
    def runtime(node):
        return ("Relic." if node["type"] in {"NativeShadowPanel", "NativeLabel"}
                else "Microsoft.UI.Xaml.Controls.") + node["type"]
    nodes[0]["selector_content_evidence"] = {
        "contract": CONTRACT, "source": SOURCE, "owner_id": "tab",
        "owner_runtime_type": runtime(nodes[0]), "tag_content_id": "content", "presenter_ids": ["presenter"],
        "ui_thread_access": True, "template_present": True, "same_subtree_after": True,
        "same_tag_after": True, "same_template_after": True, "same_presenter_content_after": True,
        "tag_in_actual_subtree": True, "captured_subtree_complete": True, "status": "measured", "errors": [],
        "actual_subtree": [{"id": node["id"], "parent_id": node["parent"], "child_index": 0,
                            "runtime_type": runtime(node), "captured_parent_matches": True} for node in nodes],
        "text_sources": [{"id": node["id"], "text": node["text"], "runtime_type": runtime(node),
                          "captured_text_matches": True} for node in nodes if node["type"] in {"TextBlock", "NativeLabel"}],
    }
    return nodes


class SelectorLabelsTests(unittest.TestCase):
    def capture(self, nodes, **changes):
        f = projection_fixtures
        providers = [f.uia_node("uia-tab", "TabItem", "Light", bounds=nodes[0]["bounds"]),
                     f.uia_node("uia-label", "Text", "Light", parent="uia-tab", bounds=nodes[5]["bounds"])]
        return f.ProjectionTests.capture(self, nodes, providers, **changes)

    def test_unique_actual_label_has_no_dependency_on_tab_text_or_name(self):
        nodes = fixture()
        before = deepcopy(nodes)
        audit = selector_content_labels(nodes)
        self.assertEqual(audit["unmeasured"], [])
        self.assertEqual(audit["owners"]["tab"]["source_id"], "label")
        self.assertIs(selector_label_candidate(audit["owners"]["tab"], [nodes[5]], False), nodes[5])
        self.assertEqual(nodes, before)

    def test_projection_owns_only_text_and_retains_paint_raw_and_unknowns(self):
        nodes = fixture()
        before = deepcopy(nodes)
        result = self.capture(nodes, xaml_changes={"extraction_errors": ["actual shadow/frame unresolved"]})
        elements = {item["id"]: item for item in result["elements"]}
        self.assertEqual(elements["tab"]["text"], "Light")
        self.assertEqual(elements["tab"]["evidence"]["label_source"], "label")
        self.assertNotIn("label", elements)
        self.assertIn("surface", elements)
        self.assertEqual(elements["surface"]["style"]["background"], [255, 255, 255, 255])
        self.assertIn("actual shadow/frame unresolved", result["extraction_errors"])
        self.assertTrue(any(issue["id"] == "label" and issue["property"] == "style.outline"
                            for issue in result["coverage"]["unmeasured"]))
        self.assertEqual(nodes, before)
        self.assertEqual(result["raw_evidence"]["xaml"], "scene.xaml.json")

    def test_historic_recorded_tag_is_not_a_new_content_identity_receipt(self):
        path = Path(__file__).parent / "fixtures" / "selector_label_d59bede_recorded.json"
        recorded = json.loads(path.read_text(encoding="utf-8"))
        raw = recorded["raw_nodes"]
        self.assertEqual(raw[0]["text"], raw[-1]["text"])
        self.assertEqual(raw[3]["declared_content_owner"], raw[0]["id"])
        self.assertEqual(selector_content_labels(raw)["owners"], {})

    def test_nonunique_text_sources_keep_both_visible_labels(self):
        f = projection_fixtures
        nodes = fixture([f.xaml_node("second", text="Independent", parent="content", bounds=f.box(20, 24, 15, 16))])
        audit = selector_content_labels(nodes)
        self.assertEqual(audit["owners"], {})
        self.assertTrue(audit["unmeasured"])
        result = self.capture(nodes)
        elements = {item["id"]: item for item in result["elements"]}
        self.assertEqual(elements["tab"]["text"], "")
        self.assertIn("label", elements)
        self.assertIn("second", elements)

    def test_hidden_or_zero_area_label_is_not_claimed(self):
        for hidden, width in (("collapsed", 42), (None, 0)):
            with self.subTest(hidden=hidden, width=width):
                nodes = fixture()
                nodes[5]["hidden_reason"] = hidden
                nodes[5]["visible_bounds"]["width"] = width
                audit = selector_content_labels(nodes)
                self.assertEqual(audit["owners"], {})
                self.assertTrue(audit["unmeasured"])

    def test_wrong_tag_content_or_changed_template_cannot_use_heuristic_fallback(self):
        for change in ("foreign-tag", "two-presenters", "changed-content", "changed-template", "missing-descendant"):
            with self.subTest(change=change):
                nodes = fixture()
                proof = nodes[0]["selector_content_evidence"]
                if change == "foreign-tag":
                    proof["tag_content_id"] = "root"
                elif change == "two-presenters":
                    proof["presenter_ids"].append("presenter")
                elif change == "changed-content":
                    proof["same_presenter_content_after"] = False
                elif change == "changed-template":
                    proof["same_template_after"] = False
                else:
                    proof["actual_subtree"].pop()
                self.assertEqual(selector_content_labels(nodes)["owners"], {})
                result = self.capture(nodes)
                elements = {item["id"]: item for item in result["elements"]}
                self.assertEqual(elements["tab"]["text"], "")
                self.assertIn("label", elements)

    def test_nested_interactive_control_prevents_parent_label_ownership(self):
        f = projection_fixtures
        nodes = fixture([f.xaml_node("child-action", "Button", parent="content", bounds=f.box(63, 22, 20, 20))])
        audit = selector_content_labels(nodes)
        self.assertIn("tab", audit["owners"], "Object binding alone does not establish a simple label")
        self.assertIsNone(selector_label_candidate(audit["owners"]["tab"], [nodes[5]], True))
        result = self.capture(nodes)
        elements = {item["id"]: item for item in result["elements"]}
        self.assertEqual(elements["tab"]["text"], "")
        self.assertIn("label", elements)
        self.assertIn("child-action", elements)

    def test_only_same_source_full_run_can_be_the_bound_label(self):
        nodes = fixture()
        audit = selector_content_labels(nodes)["owners"]["tab"]
        run = {"id": "label:run:0", "text": "Light", "text_run_source": {"owner": "label"}}
        self.assertIs(selector_label_candidate(audit, [run], False), run)
        for modified in (dict(run, text="L"), dict(run, text_run_source={"owner": "foreign"})):
            self.assertIsNone(selector_label_candidate(audit, [modified], False))
        self.assertIsNone(selector_label_candidate(audit, [run, deepcopy(run)], False))

    def test_failed_or_malformed_proof_stays_unmeasured(self):
        for mutation in (None, [], {"contract": CONTRACT}, {"status": "measured"}):
            with self.subTest(mutation=mutation):
                nodes = fixture()
                nodes[0]["selector_content_evidence"] = mutation
                audit = selector_content_labels(nodes)
                self.assertEqual(audit["owners"], {})
                if mutation is not None:
                    self.assertTrue(audit["unmeasured"])


def paint_fixture(extra=None, direct=False):
    nodes = fixture(extra)
    by_id = {node["id"]: node for node in nodes}
    parent = nodes[0]["selector_content_evidence"]
    by_id["surface"]["style"]["corner_radius"] = 6
    by_id["surface"]["style"]["corner_radii"] = [6] * 4
    by_id["content"]["style"]["shadow"] = None
    by_id["content"]["composition_shadow_evidence"] = {
        "source": "Synthetic actual production Composition DropShadow receipt",
        "layers": [{"blur_radius": 2, "offset": [0, 1, 0], "opacity": .06}],
        "quantity": "Live Composition parameters; raster/CSS equivalence remains unknown",
    }
    if direct:
        nodes.remove(by_id["content"])
        parent["tag_content_id"] = "surface"
        by_id["surface"]["parent"] = "presenter"
        by_id["surface"]["declared_content_owner"] = "tab"
        by_id["surface"]["declared_content_source"] = "FrameworkElement.Tag UIElement in the actual visual tree"
        parent["actual_subtree"] = [entry for entry in parent["actual_subtree"] if entry["id"] != "content"]
        next(entry for entry in parent["actual_subtree"] if entry["id"] == "surface")["parent_id"] = "presenter"
    parent["paint_surface"] = {
        "contract": PAINT_CONTRACT, "source": PAINT_SOURCE, "status": "measured", "errors": [],
        "owner_id": "tab", "content_form": "direct-border" if direct else "shadow-surface",
        "tag_content_id": parent["tag_content_id"], "surface_id": "surface",
        "surface_runtime_type": "Microsoft.UI.Xaml.Controls.Border", "label_id": "label",
        "shadow_id": None if direct else "content",
        "shadow_runtime_type": None if direct else "Relic.NativeShadowPanel",
        "surface_child_is_unique_label": True, "current_child_parent_matches": True,
        "same_surface_after": True, "same_child_after": True,
    }
    return nodes


class SelectorPaintTests(unittest.TestCase):
    def audit(self, nodes):
        return selector_paint_surfaces(nodes, selector_content_labels(nodes))

    def capture(self, nodes, **changes):
        f = projection_fixtures
        by_id = {node["id"]: node for node in nodes}
        providers = [f.uia_node("uia-tab", "TabItem", "Light", bounds=by_id["tab"]["bounds"]),
                     f.uia_node("uia-label", "Text", "Light", parent="uia-tab", bounds=by_id["label"]["bounds"])]
        return f.ProjectionTests.capture(self, nodes, providers, **changes)

    def test_actual_surface_values_are_used_without_expected_color_or_radius(self):
        nodes = paint_fixture()
        surface = next(node for node in nodes if node["id"] == "surface")
        surface["style"]["background"] = [12, 34, 56, 200]
        surface["style"]["corner_radius"] = 3
        surface["style"]["corner_radii"] = [3] * 4
        before = deepcopy(nodes)
        audit = self.audit(nodes)
        self.assertEqual(audit["owners"]["tab"]["style"]["background"], [12, 34, 56, 200])
        self.assertEqual(audit["owners"]["tab"]["style"]["corner_radius"], 3)
        self.assertEqual(nodes, before)

    def test_projection_owns_surface_but_retains_shadow_and_outline_unknown(self):
        nodes = paint_fixture()
        result = self.capture(nodes, xaml_changes={"extraction_errors": ["actual shadow/clip unresolved"]})
        elements = {item["id"]: item for item in result["elements"]}
        self.assertEqual(elements["tab"]["text"], "Light")
        self.assertNotIn("surface", elements)
        self.assertIn("surface", elements["tab"]["evidence"]["paint_sources"])
        self.assertEqual(elements["tab"]["style"]["background"], [255, 255, 255, 255])
        self.assertEqual(elements["tab"]["style"]["corner_radii"], [6] * 4)
        self.assertIsNone(elements["tab"]["style"]["shadow"])
        self.assertEqual(elements["tab"]["evidence"]["selector_paint_surface"]["raw_shadow"]["id"], "content")
        self.assertIn("actual shadow/clip unresolved", result["extraction_errors"])
        self.assertTrue(any(issue["id"] == "surface" and issue["property"] == "style.outline"
                            for issue in result["coverage"]["unmeasured"]))
        retained = next(item for item in result["projection"] if item.get("source") == "surface")
        self.assertEqual(retained["paint_evidence"]["style"], next(n for n in nodes if n["id"] == "surface")["style"])

    def test_direct_tag_border_has_independent_binding_without_shadow_assumption(self):
        nodes = paint_fixture(direct=True)
        audit = self.audit(nodes)
        self.assertEqual(audit["unmeasured"], [])
        self.assertEqual(audit["owners"]["tab"]["surface_id"], "surface")
        self.assertIsNone(audit["owners"]["tab"]["raw_shadow"])
        self.assertEqual(audit["owners"]["tab"]["style"]["shadow"], [])
        result = self.capture(nodes)
        elements = {item["id"]: item for item in result["elements"]}
        self.assertNotIn("surface", elements)
        self.assertEqual(elements["tab"]["style"]["background"], [255, 255, 255, 255])

    def test_native_box_or_transform_difference_never_uses_nearby_paint_heuristic(self):
        for difference in ("bounds", "visible_bounds", "transform", "opacity", "unknown-box"):
            with self.subTest(difference=difference):
                nodes = paint_fixture()
                surface = next(node for node in nodes if node["id"] == "surface")
                if difference in ("bounds", "visible_bounds"):
                    surface[difference] = dict(surface[difference], x=surface[difference]["x"] + .01)
                elif difference == "transform":
                    surface["transform"]["offset_x"] += .01
                elif difference == "opacity":
                    surface["opacity"] = .5
                else:
                    surface["bounds"] = None
                self.assertEqual(self.audit(nodes)["owners"], {})

    def test_wrong_actual_child_surface_or_shadow_class_cannot_merge(self):
        for difference in ("label", "surface", "child", "subclass", "form"):
            with self.subTest(difference=difference):
                nodes = paint_fixture()
                proof = nodes[0]["selector_content_evidence"]["paint_surface"]
                if difference == "label":
                    proof["label_id"] = "foreign"
                elif difference == "surface":
                    proof["surface_id"] = "root"
                elif difference == "child":
                    proof["same_child_after"] = False
                elif difference == "subclass":
                    proof["shadow_runtime_type"] = "Relic.NativeToastNotice"
                else:
                    proof["content_form"] = "guessed-painted-descendant"
                self.assertEqual(self.audit(nodes)["owners"], {})
                result = self.capture(nodes)
                self.assertIn("surface", {item["id"] for item in result["elements"]})

    def test_hidden_surface_and_nested_interactive_content_are_not_absorbed(self):
        nodes = paint_fixture()
        next(node for node in nodes if node["id"] == "surface")["hidden_reason"] = "collapsed"
        self.assertEqual(self.audit(nodes)["owners"], {})
        f = projection_fixtures
        nodes = paint_fixture([f.xaml_node("action", "Button", parent="content", bounds=f.box(65, 25, 18, 15))])
        result = self.capture(nodes)
        elements = {item["id"]: item for item in result["elements"]}
        self.assertIn("surface", elements)
        self.assertIn("action", elements)

    def test_independent_painted_content_remains_separate(self):
        f = projection_fixtures
        extra = f.xaml_node("decoration", "Border", parent="content", bounds=f.box(65, 24, 12, 12))
        extra["style"]["background"] = [200, 60, 40, 255]
        nodes = paint_fixture([extra])
        result = self.capture(nodes)
        elements = {item["id"]: item for item in result["elements"]}
        self.assertNotIn("surface", elements)
        self.assertIn("decoration", elements)
        self.assertEqual(elements["decoration"]["style"]["background"], [200, 60, 40, 255])

    def test_label_v1_without_new_paint_receipt_keeps_surface_independent(self):
        nodes = fixture()
        self.assertEqual(self.audit(nodes)["owners"], {})
        result = self.capture(nodes)
        self.assertIn("surface", {item["id"] for item in result["elements"]})

    def test_additional_owner_background_is_not_flattened_behind_surface(self):
        nodes = paint_fixture()
        nodes[0]["style"]["background"] = [10, 20, 30, 255]
        self.assertEqual(self.audit(nodes)["owners"], {})
        result = self.capture(nodes)
        self.assertIn("surface", {item["id"] for item in result["elements"]})

    def test_unknown_surface_style_stays_unknown_instead_of_owner_defaults(self):
        nodes = paint_fixture()
        surface = next(node for node in nodes if node["id"] == "surface")
        surface["style"].update(background=None, border_width=None, corner_radius=None)
        style = self.audit(nodes)["owners"]["tab"]["style"]
        for key in ("background", "border_width", "corner_radius", "shadow"):
            self.assertIsNone(style[key])


if __name__ == "__main__":
    unittest.main()
