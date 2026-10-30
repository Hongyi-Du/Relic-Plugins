"""Synthetic new-producer contracts and a separately labelled historic receipt.

These fixtures do not claim that a new capture has already run in CI.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest

import test_windows_elements as projection_fixtures
from windows_selector_labels import CONTRACT, SOURCE, selector_content_labels, selector_label_candidate


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


if __name__ == "__main__":
    unittest.main()
