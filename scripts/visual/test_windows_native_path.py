"""Pure synthetic/recorded projection fixtures; no native process or browser."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from windows_elements import native_path_binding, project_native_paths


def box(x=10, y=20, width=30, height=14):
    return {"x": x, "y": y, "width": width, "height": height}


def identity(runtime, address):
    return {"runtime_type": runtime, "managed_reference_hash": int(address, 16), "iunknown_identity": address}


def synthetic():
    """Exact-shape synthetic binding contract, never recorded production proof."""
    text, pieces = "ab😀cd", [(0, 2, "ab"), (2, 6, "😀cd")]
    owner = {"id": "path", "parent": None, "type": "NativePathText", "region": "dialog", "accessible_name": text,
             "bounds": box(width=100, height=40), "state": {"enabled": True, "focused": False, "hovered": False},
             "interaction_evidence": {"is_control": True, "is_hit_test_visible": True, "is_tab_stop": True}}
    receipt = {"source": "Actual NativePathText production line selection and actual child line objects",
               "owner_id": "path", "owner_identity": identity("Relic.NativePathText", "10"), "status": "laid-out",
               "failure": None, "layout_revision": 1, "source_text": text, "source_utf16_length": 6,
               "actual_visual_bindings_complete": True, "actual_line_bindings": [],
               "layout": {"lines": [], "icu": {"source": "Actual system ICU ubrk iterators over the unchanged production source",
                                                "source_text": text, "iterators": [
                                                    {"type": 0, "open_status": 0, "boundaries_utf16": [0, 1, 2, 4, 5, 6]},
                                                    {"type": 2, "open_status": -128, "boundaries_utf16": [0, 2, 6]}]}}}
    owner["native_path_evidence"] = receipt
    raw = {"path": owner, "body": {"id": "body", "parent": "path", "type": "Surface"}}
    elements = []
    for index, (start, end, part) in enumerate(pieces):
        eid = "line-" + str(index)
        bounds = box(y=20 + index * 20)
        binding = {"source": "Actual NativePathText retained NativeLabel object identity and unchanged source interval",
                   "owner_identity": deepcopy(receipt["owner_identity"]), "label_identity": identity("Relic.NativeLabel", str(20 + index)),
                   "owner_id": "path", "line_id": eid, "layout_revision": 1, "line_index": index, "line_count": 2,
                   "start_utf16": start, "end_utf16": end, "complete_source_text": text, "actual_label_text": part,
                   "source_slice_matches": True, "same_retained_label_reference": True, "same_current_body_parent": True,
                   "same_content_body": True, "label_is_loaded": True, "line_in_actual_visual_walk": True,
                   "reaches_same_owner_object": True, "all_captured_edges_match": True,
                   "actual_line_y": index * 20, "actual_line_height": 20,
                   "actual_ancestor_edges": [
                       {"child_id": eid, "parent_id": "body", "actual_parent_in_visual_walk": True, "captured_parent_matches": True},
                       {"child_id": "body", "parent_id": "path", "actual_parent_in_visual_walk": True, "captured_parent_matches": True}]}
        receipt["actual_line_bindings"].append(binding)
        receipt["layout"]["lines"].append({"start_utf16": start, "end_utf16": end, "source_text": part,
                                           "label_y": index * 20, "line_height": 20, "emergency": False})
        raw[eid] = {"id": eid, "parent": "body", "type": "NativeLabel", "text": part,
                    "native_path_line_evidence": deepcopy(binding)}
        font = {"family_name": "Synthetic actual face", "postscript_name": "SyntheticFace", "glyph_count": len(part)}
        style = {"font_size": 11.5, "font_weight": 400, "foreground": [20, 20, 20, 255], "background": [0, 0, 0, 0],
                 "border_color": [0, 0, 0, 0], "border_width": 0, "corner_radius": 0, "border_widths": [0, 0, 0, 0],
                 "border_colors": [[0, 0, 0, 0]] * 4, "border_styles": ["none"] * 4, "corner_radii": [0] * 4,
                 "opacity": 1, "background_image": "none", "shadow": [], "outline": "none", "rendered_fonts": [font]}
        quantities = {"version": 1, "owner": eid, "applicable": True, "legacy": {"value": 400, "quantity": "configured"},
                      "configured": {"value": 400, "source": "synthetic configured request", "raw": {"value": 400}},
                      "resolved": {"source_span_complete": True, "faces": [{**font, "value": None, "source": "synthetic actual face", "raw": {}}]}}
        elements.append({"id": eid, "parent": "body", "region": "dialog", "order": index, "kind": "text", "text": part,
                         "name": "", "bounds": bounds, "visible_bounds": bounds, "style": style, "state": {},
                         "layout": {"line_count": 1, "truncation": "none"}, "evidence": {"font_weight_quantities": quantities,
                         "outline": {"absence_proven": True, "source": "synthetic actual absence"},
                         "native_label_geometry": {"font_metric_advance": [{"text_scope": "layout-source",
                             "description": {"text_position_utf16": 0, "text_length_utf16": end - start, "text": part},
                             "window": {"bounds": bounds, "visible_bounds": bounds}}]}}})
    provider = {"id": "uia-path", "control_type": "ControlType.Text", "name": text,
                "state": {"focusable": True, "focused": False, "enabled": True}, "supported_patterns": ["TextPattern"]}
    pairs = {"pairs": [{"xaml_id": "path", "uia_id": "uia-path", "runtime_id": [42, 123, 4, 5]}]}
    return raw, elements, [provider], pairs


def project_fixture(raw, elements, providers, pairs, issues=None):
    issues = [] if issues is None else issues
    used, projection = set(), []
    result = project_native_paths(elements, raw, providers, pairs, used, projection, issues)
    return result, used, projection, issues


class NativePathProjectionTests(unittest.TestCase):
    def test_exact_objects_and_utf16_spans_project_one_actual_source_owner(self):
        raw, elements, providers, pairs = synthetic()
        original = deepcopy((raw, elements, providers, pairs))
        result, used, projection, issues = project_fixture(raw, elements, providers, pairs)
        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertEqual((item["id"], item["text"], item["name"]), ("path", "ab😀cd", "ab😀cd"))
        self.assertEqual(item["bounds"], box(height=34))
        self.assertEqual(item["layout"]["line_count"], 2)
        self.assertEqual(item["layout"]["normal_break_strategy"], "word")
        self.assertEqual(item["layout"]["emergency_break_strategy"], "break-unbreakable")
        self.assertEqual(used, {"uia-path"})
        self.assertEqual(len(projection), 3)
        self.assertEqual(item["evidence"]["native_path_projection"]["independent_line_elements"], elements)
        self.assertTrue(any(issue["property"] == "native_path.font_weight.resolved" for issue in issues))
        self.assertEqual((raw, elements, providers, pairs), original)

    def test_bad_current_object_or_parent_receipt_does_not_merge(self):
        changes = ("status", "revision", "runtime", "identity", "owner", "line-id", "line-index", "line-count", "reference",
                   "body", "content", "loaded", "walk", "reach", "edge-flag", "captured-edge", "edge-parent", "raw-parent", "missing-edge",
                   "source-text", "source-length", "span-start", "span-end", "line-text", "layout-text", "layout-y", "missing-line", "extra-line")
        for change in changes:
            with self.subTest(change=change):
                raw, elements, providers, pairs = synthetic()
                receipt = raw["path"]["native_path_evidence"]; binding = receipt["actual_line_bindings"][0]
                if change == "status": receipt["status"] = "failed-or-not-laid-out"
                elif change == "revision": binding["layout_revision"] = 2
                elif change == "runtime": binding["label_identity"]["runtime_type"] = "TextBlock"
                elif change == "identity": binding["owner_identity"]["iunknown_identity"] = "99"
                elif change == "owner": binding["owner_id"] = "different"
                elif change == "line-id": binding["line_id"] = "line-1"
                elif change == "line-index": binding["line_index"] = False
                elif change == "line-count": binding["line_count"] = 3
                elif change == "reference": binding["same_retained_label_reference"] = False
                elif change == "body": binding["same_current_body_parent"] = False
                elif change == "content": binding["same_content_body"] = False
                elif change == "loaded": binding["label_is_loaded"] = False
                elif change == "walk": binding["line_in_actual_visual_walk"] = False
                elif change == "reach": binding["reaches_same_owner_object"] = False
                elif change == "edge-flag": binding["all_captured_edges_match"] = False
                elif change == "captured-edge": binding["actual_ancestor_edges"][0]["captured_parent_matches"] = False
                elif change == "edge-parent": binding["actual_ancestor_edges"][0]["parent_id"] = "path"
                elif change == "raw-parent": raw["line-0"]["parent"] = "path"
                elif change == "missing-edge": binding["actual_ancestor_edges"].pop()
                elif change == "source-text": receipt["source_text"] = "xx😀cd"
                elif change == "source-length": receipt["source_utf16_length"] = len(receipt["source_text"])
                elif change == "span-start": binding["start_utf16"] = 1
                elif change == "span-end": binding["end_utf16"] = 3
                elif change == "line-text": raw["line-0"]["text"] = "xx"
                elif change == "layout-text": receipt["layout"]["lines"][0]["source_text"] = "xx"
                elif change == "layout-y": receipt["layout"]["lines"][0]["label_y"] = 1
                elif change == "missing-line": raw.pop("line-1")
                elif change == "extra-line": raw["extra"] = {"id": "extra", "native_path_line_evidence": {"owner_id": "path"}}
                raw["line-0"]["native_path_line_evidence"] = deepcopy(binding)
                result, used, _, issues = project_fixture(raw, elements, providers, pairs)
                self.assertEqual([item["id"] for item in result], ["line-0", "line-1"])
                self.assertFalse(used)
                self.assertTrue(any(issue["property"] == "native_path.ownership" for issue in issues))

    def test_unknown_font_geometry_and_previous_errors_remain_failures(self):
        raw, elements, providers, pairs = synthetic()
        elements[1]["evidence"]["native_label_geometry"]["font_metric_advance"] = []
        elements[1]["style"]["rendered_fonts"] = None
        elements[1]["style"]["font_size"] = None
        old = {"id": "line-1", "property": "pixel.presentation", "reason": "unmeasured final screenshot attribution"}
        original_issue = deepcopy(old)
        result, _, _, issues = project_fixture(raw, elements, providers, pairs, [old])
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["bounds"])
        self.assertIsNone(result[0]["evidence"]["text_bounds"])
        self.assertIsNone(result[0]["style"]["font_size"])
        self.assertIsNone(result[0]["style"]["rendered_fonts"])
        self.assertEqual(issues[0], {**original_issue, "projected_owner_id": "path"})
        self.assertEqual(result[0]["evidence"]["owner_layout_bounds"], raw["path"]["bounds"])

    def test_selection_paint_and_menu_remain_independent(self):
        raw, elements, providers, pairs = synthetic()
        selection = {"id": "selection", "parent": "body", "region": "dialog", "order": 3, "kind": "card", "text": ""}
        menu = {"id": "menu", "parent": None, "region": "menu", "order": 0, "kind": "menu-item", "text": "Copy"}
        elements.extend([selection, menu])
        result, _, _, _ = project_fixture(raw, elements, providers, pairs)
        self.assertEqual([item["id"] for item in result], ["path", "selection", "menu"])
        self.assertEqual(result[1]["parent"], "body", "Final ancestry pass resolves the actual remaining ancestor; no guessed owner here")
        self.assertEqual(result[2], menu)

    def test_identical_provider_name_without_real_runtime_binding_is_not_claimed(self):
        raw, elements, providers, _ = synthetic()
        result, used, _, issues = project_fixture(raw, elements, providers, {"pairs": []})
        self.assertFalse(used)
        self.assertIsNone(result[0]["evidence"]["uia_id"])
        self.assertIsNone(result[0]["state"]["focused"])
        self.assertTrue(any(issue["property"] == "native_path.UIA_correspondence" for issue in issues))

    def test_partial_or_overlapping_geometry_never_becomes_whole_text_bounds(self):
        for change in ("partial", "overlap", "wrong-text", "missing-window", "selection-only"):
            with self.subTest(change=change):
                raw, elements, providers, pairs = synthetic()
                geometry = elements[1]["evidence"]["native_label_geometry"]
                metric = geometry["font_metric_advance"][0]
                if change == "partial": metric["description"].update(text="😀", text_length_utf16=2)
                elif change == "overlap": geometry["font_metric_advance"].append(deepcopy(metric))
                elif change == "wrong-text": metric["description"]["text"] = "else"
                elif change == "missing-window": metric["window"] = None
                elif change == "selection-only": geometry["advance_selection"] = geometry.pop("font_metric_advance")
                result, _, _, issues = project_fixture(raw, elements, providers, pairs)
                self.assertIsNone(result[0]["bounds"])
                self.assertTrue(any(issue["property"] == "native_path.text_bounds" for issue in issues))

    def test_missing_policy_or_line_measurement_is_not_filled_from_siblings(self):
        raw, elements, providers, pairs = synthetic()
        raw["path"]["native_path_evidence"]["layout"]["icu"]["iterators"] = []
        elements[1]["layout"]["line_count"] = None
        result, _, _, _ = project_fixture(raw, elements, providers, pairs)
        self.assertIsNone(result[0]["layout"]["normal_break_strategy"])
        self.assertIsNone(result[0]["layout"]["emergency_break_strategy"])
        self.assertIsNone(result[0]["layout"]["line_count"])

    def test_old_fallback_and_missing_line_do_not_get_a_successful_projection(self):
        for change in ("fallback", "missing-line", "independent-owner-paint"):
            with self.subTest(change=change):
                raw, elements, providers, pairs = synthetic()
                if change == "fallback": raw["path"]["native_path_evidence"]["status"] = "failed-or-not-laid-out"
                elif change == "missing-line": elements.pop()
                else: elements.append({"id": "path", "region": "dialog", "order": 2, "kind": "card", "text": ""})
                result, used, _, issues = project_fixture(raw, elements, providers, pairs)
                self.assertEqual([item["id"] for item in result], [item["id"] for item in elements])
                self.assertFalse(used)
                self.assertTrue(issues)

    def test_two_render_ids_cannot_claim_one_retained_native_label_object(self):
        raw, elements, providers, pairs = synthetic()
        bindings = raw["path"]["native_path_evidence"]["actual_line_bindings"]
        bindings[1]["label_identity"] = deepcopy(bindings[0]["label_identity"])
        raw["line-1"]["native_path_line_evidence"] = deepcopy(bindings[1])
        result, used, _, issues = project_fixture(raw, elements, providers, pairs)
        self.assertEqual([item["id"] for item in result], ["line-0", "line-1"])
        self.assertFalse(used)
        self.assertTrue(any("same actual NativeLabel" in issue["reason"] for issue in issues))

    def test_incomplete_or_ambiguous_actual_icu_boundaries_do_not_supply_policy(self):
        for change in ("start", "end", "unordered", "duplicate", "failed", "surrogate", "duplicate-iterator", "bool"):
            with self.subTest(change=change):
                raw, elements, providers, pairs = synthetic()
                rows = raw["path"]["native_path_evidence"]["layout"]["icu"]["iterators"]
                row = rows[0]
                if change == "start": row["boundaries_utf16"].pop(0)
                elif change == "end": row["boundaries_utf16"].pop()
                elif change == "unordered": row["boundaries_utf16"] = [0, 2, 1, 4, 5, 6]
                elif change == "duplicate": row["boundaries_utf16"].insert(1, 0)
                elif change == "failed": row["open_status"] = 1
                elif change == "surrogate": row["boundaries_utf16"] = [0, 1, 2, 3, 4, 5, 6]
                elif change == "duplicate-iterator": rows.append(deepcopy(row))
                elif change == "bool": row["boundaries_utf16"][0] = False
                result, _, _, issues = project_fixture(raw, elements, providers, pairs)
                self.assertEqual(len(result), 1, "Ownership remains independent of missing strategy evidence")
                self.assertIsNone(result[0]["layout"]["normal_break_strategy"])
                self.assertIsNone(result[0]["layout"]["emergency_break_strategy"])
                self.assertTrue(any(issue["property"] == "native_path.break_strategy" for issue in issues))

    def test_recorded_de8c4ff_actual_objects_and_metric_ranges_retain_all_prior_failures(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "native_path_recorded_de8c4ff.json").read_text(encoding="utf-8"))
        self.assertEqual(fixture["provenance"]["commit"], "de8c4ff")
        raw = {node["id"]: node for node in fixture["raw_nodes"]}
        source_owner = raw["xaml-1294"]
        bound, reason = native_path_binding(source_owner, raw)
        self.assertIsNone(reason)
        self.assertEqual([line["id"] for line in bound], ["xaml-1296", "xaml-1298", "xaml-1300"])
        self.assertEqual([(line["native_path_line_evidence"]["start_utf16"], line["native_path_line_evidence"]["end_utf16"])
                          for line in bound], [(0, 25), (25, 56), (56, 64)])
        original = deepcopy(fixture)
        issues = deepcopy(fixture["unmeasured"])
        result, used, projection, issues = project_fixture(raw, fixture["elements"], fixture["uia_nodes"],
                                                          fixture["identity_bindings"], issues)
        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertEqual(item["id"], "xaml-1294")
        self.assertEqual(item["text"], source_owner["native_path_evidence"]["source_text"])
        self.assertEqual(item["name"], fixture["uia_nodes"][0]["name"])
        self.assertEqual(used, {"uia-41"})
        self.assertEqual(len(projection), 4)
        self.assertEqual(item["layout"]["line_count"], 3)
        self.assertEqual(item["layout"]["normal_break_strategy"], "word")
        self.assertEqual(item["layout"]["emergency_break_strategy"], "break-unbreakable")
        self.assertAlmostEqual(item["bounds"]["y"], 488.6199951171875)
        self.assertAlmostEqual(item["bounds"]["height"], 54.1422119140625)
        self.assertAlmostEqual(item["bounds"]["width"], 208.88671720000002)
        expected_boxes = [element["evidence"]["native_label_geometry"]["font_metric_advance"][0]["window"]["bounds"]
                          for element in fixture["elements"]]
        self.assertEqual(item["evidence"]["text_bounds"], expected_boxes)
        self.assertNotEqual(item["bounds"], source_owner["bounds"], "Parent line-layout/strut box is not the actual face-metric box")
        self.assertEqual(item["evidence"]["font_weight_quantities"]["configured"]["value"], 400)
        self.assertEqual([face["value"] for face in item["evidence"]["font_weight_quantities"]["resolved"]["faces"]], [400, 400, 400])
        self.assertEqual([font["postscript_name"] for font in item["style"]["rendered_fonts"]],
                         ["CascadiaCodeRoman"] * 3)
        self.assertIsNone(item["style"]["outline"])
        self.assertEqual(len(fixture["unmeasured"]), 11)
        for index, before in enumerate(fixture["unmeasured"]):
            expected = dict(before)
            if before["id"] in {"xaml-1296", "xaml-1298", "xaml-1300"}:
                expected["projected_owner_id"] = "xaml-1294"
            self.assertEqual(issues[index], expected)
        self.assertTrue(any(issue["property"] == "native_path.style.outline" for issue in issues))
        self.assertEqual(len(fixture["extraction_errors"]), 3)
        self.assertTrue(all("final PNG contribution" in error for error in fixture["extraction_errors"]))
        self.assertEqual(item["evidence"]["native_path_projection"]["independent_line_elements"], fixture["elements"])
        self.assertEqual(fixture, original, "Recorded evidence and original extraction failures are never rewritten")


if __name__ == "__main__":
    unittest.main()
