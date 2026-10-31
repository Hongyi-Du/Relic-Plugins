"""Pure configured-request fixtures; no UI, font resolution or native processes."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from font_weights import (WINDOWS_XAML_SOURCE, WINDOWS_XAML_BINDING_SOURCE,
                          font_weight_issues, project_font_weights)
from windows_elements import project_text_leaves
from windows_selector_labels import selector_content_labels


def recorded_samples():
    return json.loads((Path(__file__).parent / "fixtures" / "xaml_font_weight_recorded_ca8d997.json")
                      .read_text(encoding="utf-8"))["samples"]


def recorded_selector_samples():
    return json.loads((Path(__file__).parent / "fixtures" / "xaml_selector_font_weight_recorded_35ac04a.json")
                      .read_text(encoding="utf-8"))["samples"]


def synthetic_run_receipt(sample):
    """New contract over recorded inputs, NOT a receipt produced by old CI."""
    owner, run, index = sample["node"]["id"], sample["run"], sample["run_index"]
    return {"version": 1, "source": WINDOWS_XAML_SOURCE, "property": "Run.FontWeight.Weight",
            "value": run["font_weight"], "runtime_type": "Microsoft.UI.Xaml.Documents.Run",
            "source_id": owner + ":run:" + str(index), "owner_id": owner, "text": run["text"],
            "raw_style_font_weight": run["font_weight"], "run_index": index,
            "start_offset": run["start_offset"], "end_offset": run["end_offset"]}


def run_element(sample):
    item, run = deepcopy(sample["canonical"]), deepcopy(sample["run"])
    receipt = synthetic_run_receipt(sample)
    run["font_weight_configuration"] = deepcopy(receipt)
    projection = sample["projection"]
    ownership = ({"source_id": projection["source"], "owner_id": projection["owner"], "reason": projection["reason"]}
                 if projection.get("owner") else None)
    item["evidence"] = {
        "xaml_font_weight_configuration": receipt,
        "xaml_font_weight_binding": {"source": WINDOWS_XAML_BINDING_SOURCE, "canonical_owner_id": item["id"],
                                     "source_id": receipt["source_id"], "source_type": "Run", "text": run["text"],
                                     "style_font_weight": run["font_weight"], "rich_text_runs": [run],
                                     "text_run_source": deepcopy(sample["text_run_source"]), "ownership": ownership}}
    return item


def direct_element(typ):
    """Synthetic plain text owner without separately projected inline leaves."""
    item = {"id": "actual-text-owner", "kind": "text", "text": "plain", "style": {"font_weight": 550}}
    receipt = {"version": 1, "source": WINDOWS_XAML_SOURCE, "property": typ + ".FontWeight.Weight", "value": 550,
               "runtime_type": "Microsoft.UI.Xaml.Controls." + typ, "source_id": item["id"], "owner_id": item["id"],
               "text": item["text"], "raw_style_font_weight": 550}
    item["evidence"] = {"xaml_font_weight_configuration": receipt,
                        "xaml_font_weight_binding": {"source": WINDOWS_XAML_BINDING_SOURCE,
                                                     "canonical_owner_id": item["id"], "source_id": item["id"],
                                                     "source_type": typ, "text": item["text"], "style_font_weight": 550,
                                                     "text_run_source": None, "rich_text_runs": [], "ownership": None}}
    return item


class XamlConfiguredWeightTests(unittest.TestCase):
    def assert_unknown(self, item):
        result = project_font_weights(item)
        self.assertIsNone(result["configured"]["value"])
        self.assertIn("font_weight.configured", {issue["field"] for issue in font_weight_issues(item)})

    def test_actual_recording_has_request_values_but_no_new_receipt(self):
        for sample in recorded_samples():
            with self.subTest(owner=sample["node"]["id"]):
                self.assertNotIn("font_weight_configuration", sample["run"])
                self.assertEqual(sample["run"]["font_weight"], sample["canonical"]["style"]["font_weight"])
                self.assertEqual(sample["run"]["text"], sample["canonical"]["text"])
                self.assert_unknown(sample["canonical"])

    def test_versioned_receipt_over_recorded_leaf_and_actual_ownership_only_resolves_request(self):
        for sample in recorded_samples():
            with self.subTest(owner=sample["node"]["id"]):
                item = run_element(sample)
                before = deepcopy(item)
                actual = project_font_weights(item)
                self.assertEqual(actual["configured"]["value"], sample["run"]["font_weight"])
                self.assertEqual(actual["configured"]["source"], WINDOWS_XAML_SOURCE)
                self.assertEqual(actual["legacy"]["quantity"], "configured")
                self.assertIsNone(actual["resolved"]["faces"])
                self.assertEqual({issue["field"] for issue in font_weight_issues(item)}, {"font_weight.resolved"})
                self.assertEqual(item, before)

    def test_plain_textblock_and_richtextblock_actual_getter_request(self):
        for typ in ("TextBlock", "RichTextBlock"):
            with self.subTest(typ=typ):
                item = direct_element(typ)
                self.assertEqual(project_font_weights(item)["configured"]["value"], 550)
                self.assertEqual({issue["field"] for issue in font_weight_issues(item)}, {"font_weight.resolved"})

    def test_receipt_cannot_cross_owner_source_span_text_or_property(self):
        changes = {
            "version": ("version", 2), "version-bool": ("version", True), "source": ("source", "UIA FontWeightAttribute"),
            "getter": ("property", "Control.FontWeight.Weight"), "runtime": ("runtime_type", "Microsoft.UI.Xaml.Controls.Button"),
            "source-id": ("source_id", "different:run:0"), "owner": ("owner_id", "different"), "text": ("text", "other"),
            "value": ("value", 700), "bool": ("value", True), "zero": ("value", 0), "string": ("value", "400"),
            "nan": ("value", float("nan")), "raw-style": ("raw_style_font_weight", 700), "raw-style-bool": ("raw_style_font_weight", True),
            "index": ("run_index", 1), "index-bool": ("run_index", False), "start": ("start_offset", 3), "end": ("end_offset", 11),
        }
        for name, (key, value) in changes.items():
            with self.subTest(change=name):
                item = run_element(recorded_samples()[1])
                item["evidence"]["xaml_font_weight_configuration"][key] = value
                # Keep the duplicated raw receipt consistent; independent
                # actual leaf/text/style/span must still reject the mismatch.
                item["evidence"]["xaml_font_weight_binding"]["rich_text_runs"][0]["font_weight_configuration"][key] = value
                self.assert_unknown(item)

    def test_missing_configuration_binding_and_real_run_evidence_fail(self):
        for change in ("receipt", "binding", "binding-owner", "binding-source", "binding-type", "binding-text", "binding-style",
                       "run-source", "run-owner", "run-index", "run-start", "run-end", "runs", "duplicate-run", "raw-run-text",
                       "raw-run-style", "raw-run-receipt", "own-paint", "own-owner", "own-range", "own-exact", "own-runtime",
                       "projected-style", "projected-text"):
            with self.subTest(change=change):
                item = run_element(recorded_samples()[1])
                evidence = item["evidence"]
                binding = evidence["xaml_font_weight_binding"]
                run = binding["rich_text_runs"][0]
                if change == "receipt": evidence.pop("xaml_font_weight_configuration")
                elif change == "binding": evidence.pop("xaml_font_weight_binding")
                elif change == "binding-owner": binding["canonical_owner_id"] = "other-element"
                elif change == "binding-source": binding["source"] = "parent control default"
                elif change == "binding-type": binding["source_type"] = "Control"
                elif change == "binding-text": binding["text"] = "other"
                elif change == "binding-style": binding["style_font_weight"] = 700
                elif change == "run-source": binding["text_run_source"] = None
                elif change == "run-owner": binding["text_run_source"]["owner"] = "other"
                elif change == "run-index": binding["text_run_source"]["index"] = True
                elif change == "run-start": binding["text_run_source"]["start_offset"] = -1
                elif change == "run-end": binding["text_run_source"]["end_offset"] = 2
                elif change == "runs": binding["rich_text_runs"] = []
                elif change == "duplicate-run": binding["rich_text_runs"].append(deepcopy(run))
                elif change == "raw-run-text": run["text"] = "other"
                elif change == "raw-run-style": run["font_weight"] = 700
                elif change == "raw-run-receipt": run.pop("font_weight_configuration")
                elif change == "own-paint": run.pop("own_paint_evidence")
                elif change == "own-owner": run["own_paint_evidence"]["owner_id"] = "other"
                elif change == "own-range": run["own_paint_evidence"]["end_offset"] = 11
                elif change == "own-exact": run["own_paint_evidence"]["exact_run_type"] = False
                elif change == "own-runtime": run["own_paint_evidence"]["runtime_type"] = "Span"
                elif change == "projected-style": item["style"]["font_weight"] = 700
                elif change == "projected-text": item["text"] = "other"
                self.assert_unknown(item)

    def test_badge_uses_the_recorded_actual_single_label_not_its_composite_defaults(self):
        sample = recorded_samples()[0]
        self.assertEqual(sample["projection"]["reason"], "single simple control label")
        for change in ("missing", "source", "owner", "reason"):
            with self.subTest(change=change):
                item = run_element(sample)
                binding = item["evidence"]["xaml_font_weight_binding"]
                if change == "missing": binding["ownership"] = None
                else: binding["ownership"][{"source": "source_id", "owner": "owner_id", "reason": "reason"}[change]] = "other"
                self.assert_unknown(item)
        for typ in ("Control", "Button", "ContentPresenter", "FontIcon", "OverviewBadgeView"):
            with self.subTest(typ=typ):
                item = direct_element(typ)
                self.assert_unknown(item)

    def test_parent_request_does_not_replace_independent_rich_text_leaf_requests(self):
        item = direct_element("RichTextBlock")
        item["evidence"]["xaml_font_weight_binding"]["rich_text_runs"] = [deepcopy(recorded_samples()[1]["run"])]
        self.assert_unknown(item)

    def test_text_leaf_projection_keeps_new_receipt_on_its_actual_run_and_no_other_owner(self):
        sample = recorded_samples()[1]
        node, run = deepcopy(sample["node"]), deepcopy(sample["run"])
        run["font_weight_configuration"] = synthetic_run_receipt(sample)
        node.update(region="conversation", opacity=1, hidden_reason=None,
                    layout={"rich_text_runs": [run], "character_boxes_coordinate_space": "content-window"})
        original = deepcopy(node)
        projected = project_text_leaves([node], [], None)
        leaf = next(record for record in projected if record["type"] == "Run")
        self.assertEqual(leaf["id"], run["font_weight_configuration"]["source_id"])
        self.assertEqual(leaf["font_weight_configuration"], run["font_weight_configuration"])
        self.assertEqual(leaf["text_run_source"], sample["text_run_source"])
        self.assertEqual(leaf["style"]["font_weight"], run["font_weight"])
        self.assertEqual(node, original)


    def test_recorded_selector_audit_matches_raw_objects_and_the_actual_run_getter(self):
        for sample in recorded_selector_samples():
            item = sample["canonical"]
            with self.subTest(owner=item["id"]):
                audit = selector_content_labels(sample["raw_nodes"])
                self.assertEqual(audit["unmeasured"], [])
                self.assertEqual(audit["owners"][item["id"]], item["evidence"]["selector_content_label"])
                binding = item["evidence"]["xaml_font_weight_binding"]
                source = next(node for node in sample["raw_nodes"] if node["id"] == binding["text_run_source"]["owner"])
                self.assertEqual(source["layout"]["rich_text_runs"], binding["rich_text_runs"])
                self.assertEqual(source["layout"]["rich_text_runs"][0]["font_weight_configuration"],
                                 item["evidence"]["xaml_font_weight_configuration"])

    def test_recorded_selector_configuration_resolves_without_resolving_actual_fonts(self):
        for sample in recorded_selector_samples():
            item = sample["canonical"]
            with self.subTest(owner=item["id"]):
                before = deepcopy(item)
                measured = project_font_weights(item)
                self.assertEqual(measured["configured"]["value"], 400)
                self.assertEqual(measured["configured"]["source"], WINDOWS_XAML_SOURCE)
                self.assertEqual(measured["configured"]["raw"]["selector_content_label"],
                                 item["evidence"]["selector_content_label"])
                self.assertIsNone(measured["resolved"]["faces"])
                self.assertFalse(measured["resolved"]["source_span_complete"])
                self.assertIsNone(item["style"]["rendered_fonts"])
                self.assertEqual({issue["field"] for issue in font_weight_issues(item)}, {"font_weight.resolved"})
                self.assertEqual(item, before)

    def test_selector_reason_alone_or_cross_owner_source_is_not_configured_evidence(self):
        for change in ("missing-audit", "measured-only", "wrong-kind", "wrong-type", "label-source",
                       "binding-owner", "ownership-source", "ownership-owner", "ownership-reason",
                       "audit-owner", "audit-source", "audit-text", "audit-status", "audit-source-type"):
            with self.subTest(change=change):
                item = deepcopy(recorded_selector_samples()[0]["canonical"])
                evidence = item["evidence"]
                binding = evidence["xaml_font_weight_binding"]
                audit = evidence["selector_content_label"]
                if change == "missing-audit": evidence.pop("selector_content_label")
                elif change == "measured-only": evidence["selector_content_label"] = {"status": "measured"}
                elif change == "wrong-kind": item["kind"] = "button"
                elif change == "wrong-type": evidence["type"] = "Button"
                elif change == "label-source": evidence["label_source"] = "other:run:0"
                elif change == "binding-owner": binding["canonical_owner_id"] = "other"
                elif change == "ownership-source": binding["ownership"]["source_id"] = "other:run:0"
                elif change == "ownership-owner": binding["ownership"]["owner_id"] = "other"
                elif change == "ownership-reason": binding["ownership"]["reason"] = "selector label by matching name"
                elif change == "audit-owner": audit["evidence"]["owner_id"] = "other"
                elif change == "audit-source": audit["source_id"] = "other"
                elif change == "audit-text": audit["text"] = "other"
                elif change == "audit-status": audit["status"] = "incomplete"
                elif change == "audit-source-type": audit["source_id"] = binding["text_run_source"]["owner"] = []
                self.assert_unknown(item)

    def test_selector_receipt_requires_actual_current_stable_content_observations(self):
        values = {"contract": "other", "source": "matched by tab name", "status": "failed",
                  "owner_runtime_type": "Microsoft.UI.Xaml.Controls.Button", "errors": ["actual failure"]}
        values.update({key: False for key in ("ui_thread_access", "template_present", "same_subtree_after",
                      "same_tag_after", "same_template_after", "same_presenter_content_after",
                      "tag_in_actual_subtree", "captured_subtree_complete")})
        for key, value in values.items():
            with self.subTest(field=key):
                item = deepcopy(recorded_selector_samples()[0]["canonical"])
                item["evidence"]["selector_content_label"]["evidence"][key] = value
                self.assert_unknown(item)

    def test_selector_subtree_and_text_identity_cannot_be_missing_changed_or_ambiguous(self):
        for change in ("missing-tree", "duplicate-id", "missing-owner", "owner-runtime", "owner-parent",
                       "parent-mismatch", "unknown-parent", "cycle", "child-index", "label-runtime",
                       "foreign-tag", "tag-is-label", "label-outside-tag", "missing-presenter", "two-presenters",
                       "presenter-runtime", "presenter-not-ancestor", "missing-text", "two-text-sources",
                       "source-id", "source-text", "source-runtime", "source-not-observed", "second-text-node"):
            with self.subTest(change=change):
                item = deepcopy(recorded_selector_samples()[0]["canonical"])
                audit = item["evidence"]["selector_content_label"]
                proof = audit["evidence"]
                entries = proof["actual_subtree"]
                by_id = {entry["id"]: entry for entry in entries}
                owner, label = by_id[item["id"]], by_id[audit["source_id"]]
                presenter = by_id[proof["presenter_ids"][0]]
                source = proof["text_sources"][0]
                if change == "missing-tree": proof["actual_subtree"] = []
                elif change == "duplicate-id": entries.append(deepcopy(label))
                elif change == "missing-owner": entries.remove(owner)
                elif change == "owner-runtime": owner["runtime_type"] = "OtherSelector"
                elif change == "owner-parent": owner["parent_id"] = "foreign"
                elif change == "parent-mismatch": label["captured_parent_matches"] = False
                elif change == "unknown-parent": label["parent_id"] = "foreign"
                elif change == "cycle": label["parent_id"] = label["id"]
                elif change == "child-index": label["child_index"] = True
                elif change == "label-runtime": label["runtime_type"] = "OtherTextBlock"
                elif change == "foreign-tag": proof["tag_content_id"] = "foreign"
                elif change == "tag-is-label": proof["tag_content_id"] = label["id"]
                elif change == "label-outside-tag": label["parent_id"] = owner["id"]
                elif change == "missing-presenter": proof["presenter_ids"] = []
                elif change == "two-presenters": proof["presenter_ids"].append(presenter["id"])
                elif change == "presenter-runtime": presenter["runtime_type"] = "Microsoft.UI.Xaml.Controls.Grid"
                elif change == "presenter-not-ancestor": by_id[proof["tag_content_id"]]["parent_id"] = owner["id"]
                elif change == "missing-text": proof["text_sources"] = []
                elif change == "two-text-sources": proof["text_sources"].append(deepcopy(source))
                elif change == "source-id": source["id"] = "foreign"
                elif change == "source-text": source["text"] = "different"
                elif change == "source-runtime": source["runtime_type"] = "Microsoft.UI.Xaml.Controls.RichTextBlock"
                elif change == "source-not-observed": source["captured_text_matches"] = False
                elif change == "second-text-node":
                    extra = deepcopy(label)
                    extra["id"] = "second-label"
                    extra["child_index"] = 1
                    entries.append(extra)
                self.assert_unknown(item)

    def test_selector_binding_does_not_bypass_existing_getter_and_full_run_checks(self):
        for change in ("getter-value", "projected-value", "run-owner", "run-span", "run-receipt",
                       "own-paint", "partial-text", "parent-getter"):
            with self.subTest(change=change):
                item = deepcopy(recorded_selector_samples()[0]["canonical"])
                evidence = item["evidence"]
                receipt = evidence["xaml_font_weight_configuration"]
                binding = evidence["xaml_font_weight_binding"]
                run = binding["rich_text_runs"][0]
                if change == "getter-value":
                    receipt["value"] = 700
                    run["font_weight_configuration"]["value"] = 700
                elif change == "projected-value": item["style"]["font_weight"] = 700
                elif change == "run-owner": binding["text_run_source"]["owner"] = "other"
                elif change == "run-span": binding["text_run_source"]["end_offset"] += 1
                elif change == "run-receipt": run.pop("font_weight_configuration")
                elif change == "own-paint": run["own_paint_evidence"]["exact_run_type"] = False
                elif change == "partial-text":
                    partial = item["text"][:1]
                    item["text"] = binding["text"] = receipt["text"] = run["text"] = partial
                    run["font_weight_configuration"]["text"] = partial
                elif change == "parent-getter":
                    receipt["property"] = "TextBlock.FontWeight.Weight"
                    receipt["runtime_type"] = "Microsoft.UI.Xaml.Controls.TextBlock"
                    binding["source_type"] = "TextBlock"
                self.assert_unknown(item)


if __name__ == "__main__":
    unittest.main()
