"""CI-only pure failure-attribution fixtures; no UI, server or subprocess."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from element_parity import native_path_failure_owners, validate_capture
from windows_elements import project_native_paths


OWNER = "xaml-1294"
LINES = ["xaml-1296", "xaml-1298", "xaml-1300"]


def recorded_capture(line_outline_none=False):
    fixture = json.loads((Path(__file__).parent / "fixtures" / "native_path_recorded_de8c4ff.json").read_text(encoding="utf-8"))
    raw = {item["id"]: item for item in fixture["raw_nodes"]}
    if line_outline_none:
        # Explicit synthetic mutation: child absence does not measure the
        # actual recorded parent's unknown own/focus outline.
        for item in fixture["elements"]:
            item["style"]["outline"] = "none"
            item["evidence"]["outline"] = {"absence_proven": True, "source": "synthetic child-only absence"}
    issues = deepcopy(fixture["unmeasured"])
    elements = project_native_paths(fixture["elements"], raw, fixture["uia_nodes"], fixture["identity_bindings"],
                                    set(), [], issues)
    # The focused fixture omits ancestors outside NativePathText. This is the
    # same final ancestor resolution as project(): no absent parent is emitted.
    for element in elements:
        element["parent"] = None
    return {"schema_version": 1, "client": "windows", "scene_id": fixture["provenance"]["case_id"],
            "viewport": {"width": 1440, "height": 900, "scale": 1}, "elements": elements,
            "coverage": {"raw_nodes": len(raw) + len(fixture["uia_nodes"]), "emitted_elements": len(elements), "unmeasured": issues},
            "extraction_errors": deepcopy(fixture["extraction_errors"])}, fixture


def validate(data):
    return validate_capture(data, data["client"], data["scene_id"], data["viewport"])


def coverage_errors(data):
    return [issue for issue in validate(data) if issue["reason"].startswith("Unmeasured: ")]


class NativePathFailureOwnershipTests(unittest.TestCase):
    def test_recorded_failures_keep_original_id_count_and_reason_with_proven_owner(self):
        data, fixture = recorded_capture()
        original = deepcopy(data)
        ownership = native_path_failure_owners(data["elements"])
        self.assertEqual(set(ownership), set(LINES))
        self.assertTrue(all(item["owner"] == OWNER for item in ownership.values()))
        errors = coverage_errors(data)
        self.assertEqual(len(errors), len(data["coverage"]["unmeasured"]))
        for gap, error in zip(data["coverage"]["unmeasured"], errors):
            self.assertEqual(error["reason"], "Unmeasured: " + str(gap))
            self.assertEqual(error["element"], OWNER)
            if gap["id"] in LINES:
                self.assertEqual(error["source_element"], gap["id"])
                self.assertEqual(error["failure_ownership"]["source_element"], gap["id"])
                self.assertEqual(error["failure_ownership"]["owner"], OWNER)
        global_errors = [issue for issue in validate(data) if issue["reason"].startswith("Extractor reported: ")]
        self.assertEqual([issue["reason"] for issue in global_errors],
                         ["Extractor reported: " + error for error in fixture["extraction_errors"]])
        self.assertTrue(all(issue["element"] is None for issue in global_errors))
        self.assertEqual(len(global_errors), 3, "The original final-presentation failures are not resolved")
        self.assertEqual(data, original)

    def test_arbitrary_projected_owner_id_cannot_localize_without_actual_proof(self):
        data, _ = recorded_capture()
        data["elements"][0]["evidence"].pop("native_path_projection")
        self.assertEqual(native_path_failure_owners(data["elements"]), {})
        errors = coverage_errors(data)
        for gap, error in zip(data["coverage"]["unmeasured"], errors):
            if gap["id"] in LINES:
                self.assertEqual(gap["projected_owner_id"], OWNER)
                self.assertIsNone(error["element"])
                self.assertNotIn("failure_ownership", error)

    def test_conflicting_owner_hint_and_conflicting_source_ids_stay_global(self):
        for mutation in ("owner-hint", "two-source-fields"):
            with self.subTest(mutation=mutation):
                data, _ = recorded_capture()
                gap = next(gap for gap in data["coverage"]["unmeasured"] if gap["id"] == LINES[0])
                if mutation == "owner-hint": gap["projected_owner_id"] = "not-the-owner"
                else: gap["element"] = "another-source"
                data["coverage"]["unmeasured"] = [gap]
                errors = coverage_errors(data)
                self.assertEqual(len(errors), 1)
                self.assertIsNone(errors[0]["element"])
                self.assertNotIn("failure_ownership", errors[0])

    def test_missing_or_changed_retained_receipts_cannot_localize(self):
        changes = ("source", "kind", "merged-paint", "raw-owner-id", "receipt-copy", "status", "zero-identity",
                   "wrong-revision", "missing-ancestor", "changed-ancestor", "extra-ancestor", "raw-line-parent",
                   "raw-line-text", "missing-raw-line", "extra-raw-line", "line-order", "duplicate-line-id",
                   "missing-independent-line", "independent-kind", "independent-text", "independent-region",
                   "binding-flag", "binding-owner", "incomplete-source", "owner-text", "same-label-object")
        for change in changes:
            with self.subTest(change=change):
                data, _ = recorded_capture()
                owner = data["elements"][0]
                proof = owner["evidence"]["native_path_projection"]
                receipt = proof["source_receipt"]
                bindings = receipt["actual_line_bindings"]
                if change == "source": owner["evidence"]["source"] = "claimed by name"
                elif change == "kind": owner["kind"] = "card"
                elif change == "merged-paint": proof["other_child_paint_merged"] = True
                elif change == "raw-owner-id": proof["raw_owner"]["id"] = "foreign"
                elif change == "receipt-copy": proof["raw_owner"]["native_path_evidence"] = {}
                elif change == "status": receipt["status"] = "failed-or-not-laid-out"
                elif change == "zero-identity": receipt["owner_identity"]["iunknown_identity"] = "0"
                elif change == "wrong-revision": receipt["layout_revision"] += 1
                elif change == "missing-ancestor": proof["raw_ancestors"] = []
                elif change == "changed-ancestor": proof["raw_ancestors"][0]["parent"] = "foreign"
                elif change == "extra-ancestor": proof["raw_ancestors"].append({"id": "foreign", "parent": OWNER})
                elif change == "raw-line-parent": proof["raw_lines"][0]["parent"] = OWNER
                elif change == "raw-line-text": proof["raw_lines"][0]["text"] = "unchanged name does not prove ownership"
                elif change == "missing-raw-line": proof["raw_lines"].pop()
                elif change == "extra-raw-line": proof["raw_lines"].append(deepcopy(proof["raw_lines"][0]))
                elif change == "line-order": proof["source_line_ids"].reverse()
                elif change == "duplicate-line-id": proof["source_line_ids"][1] = proof["source_line_ids"][0]
                elif change == "missing-independent-line": proof["independent_line_elements"].pop()
                elif change == "independent-kind": proof["independent_line_elements"][0]["kind"] = "card"
                elif change == "independent-text": proof["independent_line_elements"][0]["text"] = "foreign"
                elif change == "independent-region": proof["independent_line_elements"][0]["region"] = "sidebar"
                elif change == "binding-flag": bindings[0]["same_retained_label_reference"] = False
                elif change == "binding-owner": bindings[0]["owner_id"] = "foreign"
                elif change == "incomplete-source": receipt["source_utf16_length"] -= 1
                elif change == "owner-text": owner["text"] = "foreign"
                elif change == "same-label-object": bindings[1]["label_identity"] = deepcopy(bindings[0]["label_identity"])
                if change in {"status", "zero-identity", "wrong-revision", "binding-flag", "binding-owner", "incomplete-source", "same-label-object"}:
                    # Mutate all receipt copies so rejection must inspect real
                    # identity/parent/source invariants, not merely dict equality.
                    proof["raw_owner"]["native_path_evidence"] = deepcopy(receipt)
                    for line, binding in zip(proof["raw_lines"], bindings):
                        line["native_path_line_evidence"] = deepcopy(binding)
                self.assertEqual(native_path_failure_owners(data["elements"]), {})
                issues = coverage_errors(data)
                self.assertEqual(len(issues), len(data["coverage"]["unmeasured"]))
                for gap, error in zip(data["coverage"]["unmeasured"], issues):
                    if gap["id"] in LINES:
                        self.assertIsNone(error["element"])

    def test_duplicate_emitted_owner_or_independent_line_does_not_gain_owner_mapping(self):
        for what in ("owner", "line"):
            with self.subTest(what=what):
                data, _ = recorded_capture()
                added = deepcopy(data["elements"][0] if what == "owner" else
                                 data["elements"][0]["evidence"]["native_path_projection"]["independent_line_elements"][0])
                added["parent"] = None
                data["elements"].append(added)
                data["coverage"]["emitted_elements"] += 1
                self.assertEqual(native_path_failure_owners(data["elements"]), {})
                errors = coverage_errors(data)
                for gap, error in zip(data["coverage"]["unmeasured"], errors):
                    if gap["id"] in LINES:
                        self.assertEqual(error["element"], LINES[0] if what == "line" and gap["id"] == LINES[0] else None)
                        self.assertNotIn("failure_ownership", error)

    def test_ownership_proof_does_not_localize_non_line_or_non_windows_gap(self):
        data, _ = recorded_capture()
        data["coverage"]["unmeasured"] = [{"id": "xaml-1295", "projected_owner_id": OWNER,
                                           "property": "paint", "reason": "Independent Surface paint unknown"}]
        self.assertIsNone(coverage_errors(data)[0]["element"])
        data["coverage"]["unmeasured"][0]["id"] = LINES[0]
        data["client"] = "reference"
        self.assertIsNone(coverage_errors(data)[0]["element"])

    def test_child_outline_absence_does_not_prove_actual_owner_outline_absence(self):
        data, _ = recorded_capture(line_outline_none=True)
        owner = data["elements"][0]
        children = owner["evidence"]["native_path_projection"]["independent_line_elements"]
        self.assertTrue(all(child["style"]["outline"] == "none" for child in children))
        self.assertIsNone(owner["style"]["outline"], "A child-only proof cannot cover NativePathText own/system focus paint")
        self.assertTrue(any(issue["id"] == OWNER and "outline" in issue["property"]
                            for issue in data["coverage"]["unmeasured"]))


if __name__ == "__main__":
    unittest.main()
