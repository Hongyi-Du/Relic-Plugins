"""CI-only pure configuration/projection/matcher fixtures. Never starts a UI."""
from copy import deepcopy
import unittest

from element_parity import compare_elements, validate_capture
from line_breaks import BREAK_FIELDS, break_strategy_issues
from test_element_parity import capture, element
from windows_elements import project_line_break_strategies


def actual_windows_layout(mode, normal, emergency):
    return {"wrap": "character" if mode == "Wrap" else "word" if mode == "WrapWholeWords" else "none",
            "break_strategy_version": 1, "normal_break_strategy": normal, "emergency_break_strategy": emergency,
            "line_break_configuration": {"source": "synthetic fixture of actual WinUI TextWrapping", "owner": "measured-text-owner",
                                         "raw": {"text_wrapping": mode}}}


class LineBreakContractTests(unittest.TestCase):
    def test_complete_config_and_explicit_non_text_inapplicability(self):
        self.assertEqual(break_strategy_issues(element()), [])
        self.assertEqual(break_strategy_issues(element(text="", kind="card")), [])
        # An empty text-kind element remains applicable under the existing rule.
        self.assertEqual(break_strategy_issues(element(text="", kind="text")), [])

    def test_legacy_wrap_never_substitutes_for_either_new_quantity(self):
        for field in BREAK_FIELDS:
            for remove in (False, True):
                item = element()
                if remove: item["layout"].pop(field)
                else: item["layout"][field] = None
                self.assertTrue(any(field in issue for issue in break_strategy_issues(item)))
        item = element(); item["layout"].pop("break_strategy_version")
        self.assertTrue(break_strategy_issues(item))

    def test_configuration_binding_and_non_text_reason_are_required(self):
        for key in ("source", "owner", "raw", "applicable"):
            item = element(); item["evidence"]["line_break_configuration"].pop(key)
            self.assertTrue(break_strategy_issues(item), key)
        item = element(text="", kind="card")
        item["evidence"]["line_break_configuration"].pop("reason")
        self.assertTrue(break_strategy_issues(item))
        item = element(text="", kind="card"); item["layout"]["normal_break_strategy"] = "none"
        self.assertTrue(break_strategy_issues(item))

    def test_unknown_values_or_provider_errors_cannot_pass(self):
        for field, invalid in (("break_strategy_version", True), ("break_strategy_version", 2),
                               ("normal_break_strategy", "anywhere"), ("emergency_break_strategy", "word")):
            item = element(); item["layout"][field] = invalid
            self.assertTrue(break_strategy_issues(item))
        item = element(); item["evidence"]["line_break_configuration"]["errors"] = ["ambiguous actual owner"]
        self.assertTrue(break_strategy_issues(item))

    def test_matcher_compares_both_quantities_but_keeps_legacy_as_diagnostic(self):
        left, right = element(), element("native")
        for item in (left, right):
            item["layout"].update(normal_break_strategy="word", emergency_break_strategy="break-unbreakable")
        left["layout"]["wrap"], right["layout"]["wrap"] = "character", "word"
        self.assertEqual(compare_elements([left], [right])["layout_mismatch"], [])
        self.assertEqual(left["layout"]["wrap"], "character")
        self.assertEqual(right["layout"]["wrap"], "word")
        for field, changed in (("normal_break_strategy", "character"), ("emergency_break_strategy", "none")):
            altered = deepcopy(right); altered["layout"][field] = changed
            self.assertTrue(any(issue["field"] == field for issue in compare_elements([left], [altered])["layout_mismatch"]))

    def test_equal_unknown_strategies_still_fail_comparison_and_coverage(self):
        left, right = element(), element("native")
        left["layout"]["normal_break_strategy"] = right["layout"]["normal_break_strategy"] = None
        self.assertTrue(compare_elements([left], [right])["layout_mismatch"])
        data = capture(elements=[left])
        self.assertTrue(validate_capture(data, "reference", data["scene_id"], data["viewport"]))

    def test_equal_policies_do_not_waive_actual_lines_truncation_or_geometry(self):
        left, right = element(), element("native")
        right["evidence"]["text_bounds"][0]["y"] += 8
        self.assertTrue(compare_elements([left], [right])["geometry_out_of_tolerance"])
        right = element("native"); right["layout"]["line_count"] = 2
        self.assertTrue(compare_elements([left], [right])["layout_mismatch"])
        right = element("native"); right["layout"]["truncation"] = "ellipsis"
        self.assertTrue(compare_elements([left], [right])["layout_mismatch"])
        right = element("native"); right["evidence"]["text_bounds"] = None
        self.assertTrue(compare_elements([left], [right])["layout_mismatch"])

    def test_windows_projector_preserves_actual_owner_and_distinct_emergency_policy(self):
        for mode, normal, emergency in (("NoWrap", "none", "none"), ("Wrap", "word", "break-unbreakable"),
                                        ("WrapWholeWords", "word", "none")):
            layout = actual_windows_layout(mode, normal, emergency); before = deepcopy(layout)
            fields, evidence = project_line_break_strategies(layout, "actual text", "text", "measured-text-owner:run:0")
            self.assertEqual(fields["normal_break_strategy"], normal)
            self.assertEqual(fields["emergency_break_strategy"], emergency)
            self.assertEqual(evidence["owner"], "measured-text-owner")
            self.assertEqual(evidence["raw"]["text_wrapping"], mode)
            self.assertEqual(evidence["projected_text_owner"], "measured-text-owner:run:0")
            self.assertEqual(layout, before)

    def test_windows_legacy_or_partial_owner_is_not_promoted_to_measured(self):
        fields, evidence = project_line_break_strategies({"wrap": "character"}, "actual text", "text", "run")
        self.assertIsNone(fields["normal_break_strategy"])
        self.assertIsNone(fields["emergency_break_strategy"])
        self.assertTrue(break_strategy_issues({"text": "actual text", "kind": "text", "layout": fields,
                                              "evidence": {"line_break_configuration": evidence}}))

    def test_windows_non_text_projection_keeps_unused_actual_configuration(self):
        layout = actual_windows_layout("Wrap", "word", "break-unbreakable")
        fields, evidence = project_line_break_strategies(layout, "", "card", "owner")
        self.assertIsNone(fields["normal_break_strategy"])
        self.assertIsNone(fields["emergency_break_strategy"])
        self.assertFalse(evidence["applicable"])
        self.assertEqual(evidence["raw"]["unused_text_owner_configuration"], layout["line_break_configuration"])


if __name__ == "__main__":
    unittest.main()
