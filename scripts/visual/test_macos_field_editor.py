"""Synthetic c40e136/be16164 field-editor contracts, not recorded AppKit captures.

The tests launch no application. Actual producer tests/captures remain in CI.
"""
from copy import deepcopy
import unittest

from element_parity import validate_capture
from macos_field_editor import CONTRACT, PROVIDER, SOURCE, field_editor_aliases, retained_editor_measurements


def synthetic_alias(editor_class="ObservedFieldEditor", value="人😀"):
    def raw_input(eid, identity, native_class, role, box, focused):
        return {"id": eid, "parent": None, "region": "dialog", "order": 1, "kind": "input",
                "role": role, "source": SOURCE, "object_identity": identity, "class": native_class,
                "identifier": "", "text": value, "value": value, "name": "", "visible": True,
                "rect": deepcopy(box), "visibleRect": deepcopy(box),
                "style": {"fontSize": 14, "fontWeight": 400, "color": [0, 0, 0, 255],
                          "backgroundColor": None, "borderColor": None, "borderWidth": None,
                          "borderRadius": None, "rendered_fonts": None},
                "state": {"enabled": True, "focused": focused, "selected": None, "checked": None,
                          "expanded": None, "hovered": None, "unread": None},
                "selectorEvidence": {"errors": {}, "child_count": 0, "navigation_child_count": 0},
                "native_view_geometry": {"screen_bounds": deepcopy(box)}}
    box = {"x": 40, "y": 50, "width": 195, "height": 32.4}
    edit_box = {"x": 49, "y": 56, "width": 151, "height": 20}
    owner = raw_input("synthetic-owner", "synthetic-field-object", "Control", "AXTextField", box, True)
    editor = raw_input("synthetic-editor", "synthetic-editor-object", editor_class, "AXTextArea", edit_box, False)
    owner["identifier"] = "relic-input/member-rename"
    owner["raw_node_id"] = owner["id"]
    owner["native_field_editor"] = {
        "contract": CONTRACT, "provider": PROVIDER, "owner_identity": owner["object_identity"],
        "owner_class": owner["class"], "owner_identifier": owner["identifier"],
        "editor_identity": editor["object_identity"], "editor_class": editor["class"],
        "current_editor_identity": editor["object_identity"], "window_identity": "synthetic-window",
        "is_field_editor": True, "same_window": True, "first_responder_is_editor": True,
        "owner_value": value, "editor_value": value, "selection": {"location": 1, "length": 2} if value else {"location": 0, "length": 0},
        "owner_screen_bounds": deepcopy(box), "editor_screen_bounds": deepcopy(edit_box)}
    owner["owned_editor_evidence"] = editor
    return {"id": owner["id"], "parent": None, "region": "dialog", "order": 0, "kind": "input",
            "text": value, "name": "Rename", "bounds": deepcopy(box), "visible_bounds": deepcopy(box),
            "style": {"font_size": 14, "font_weight": 400, "foreground": [0, 0, 0, 255],
                      "background": [255, 255, 255, 255], "border_color": [1, 1, 1, 255], "border_width": 1,
                      "corner_radius": 7, "outline": None},
            "state": deepcopy(owner["state"]), "layout": None, "icon": None, "evidence": owner}


def capture(item):
    return {"schema_version": 1, "client": "macos", "scene_id": "synthetic-field-editor",
            "viewport": {"width": 400, "height": 300, "scale": 1}, "extraction_errors": [],
            "coverage": {"raw_nodes": 2, "emitted_elements": 1, "unmeasured": []}, "elements": [item]}


class MacFieldEditorTests(unittest.TestCase):
    def test_exact_current_binding_does_not_substitute_ax_focus_or_paint(self):
        for native_class in ("ObservedFieldEditor", "_SystemTextFieldFieldEditor"):
            with self.subTest(native_class=native_class):
                item = synthetic_alias(native_class)
                original = deepcopy(item)
                result, = field_editor_aliases([item])
                self.assertTrue(result["binding_valid"], result["issues"])
                self.assertEqual(result["issues"], [])
                self.assertFalse(result["retained_measurements"]["state"]["focused"])
                self.assertIsNone(result["retained_measurements"]["style"]["background"])
                self.assertEqual(item, original)

    def test_unknown_or_unproven_alias_never_passes(self):
        mutations = [
            ("contract", "unknown"), ("provider", "guessed from AX name"),
            ("owner_identity", "other"), ("editor_identity", "other"),
            ("current_editor_identity", "stale"), ("owner_class", "OtherControl"),
            ("editor_class", "OtherEditor"), ("owner_identifier", "foreign-input"),
            ("window_identity", ""), ("same_window", False), ("is_field_editor", 1),
            ("first_responder_is_editor", False), ("owner_value", "different"),
            ("editor_value", "different"), ("selection", {"location": 0, "length": 4}),
            ("selection", {"location": True, "length": 0}),
            ("owner_screen_bounds", None), ("editor_screen_bounds", {"x": 0}),
        ]
        for key, value in mutations:
            with self.subTest(key=key):
                item = synthetic_alias()
                item["evidence"]["native_field_editor"][key] = value
                result, = field_editor_aliases([item])
                self.assertFalse(result["binding_valid"])
                self.assertTrue(result["issues"])

    def test_raw_identity_role_value_and_geometry_cannot_be_replaced_by_receipt(self):
        mutations = [("object_identity", "foreign"), ("role", "AXButton"), ("role", []),
                     ("kind", "text"), ("value", "other"), ("source", "copied expected input"),
                     ("class", "OtherEditor"), ("style", None), ("state", None),
                     ("selectorEvidence", None), ("visible", False), ("visibleRect", None),
                     ("native_view_geometry", None)]
        for key, value in mutations:
            with self.subTest(key=key):
                item = synthetic_alias()
                item["evidence"]["owned_editor_evidence"][key] = value
                result, = field_editor_aliases([item])
                self.assertFalse(result["binding_valid"])
                self.assertTrue(result["issues"])

    def test_raw_editor_missing_or_partial_is_not_accepted(self):
        for value in (None, {}, [], {"id": "synthetic-editor", "kind": "input"}):
            with self.subTest(value=value):
                item = synthetic_alias()
                item["evidence"]["owned_editor_evidence"] = value
                result, = field_editor_aliases([item])
                self.assertFalse(result["binding_valid"])
                self.assertTrue(result["issues"])
        item = synthetic_alias()
        del item["evidence"]["native_field_editor"]
        self.assertFalse(field_editor_aliases([item])[0]["binding_valid"])

    def test_duplicate_owner_or_editor_identity_cannot_be_consumed_twice(self):
        item = synthetic_alias()
        duplicate = deepcopy(item)
        duplicate["id"] = "second-owner"
        self.assertTrue(all(not x["binding_valid"] for x in field_editor_aliases([item, duplicate])))
        emitted_editor = retained_editor_measurements(item["evidence"]["owned_editor_evidence"])
        self.assertFalse(field_editor_aliases([item, emitted_editor])[0]["binding_valid"])

    def test_current_window_conflict_remains_failure(self):
        item = synthetic_alias()
        item["evidence"]["owned_editor_evidence"]["native_structure"] = {
            "source": "production parent environment and current NSView.subviews ancestry",
            "view_identity": "synthetic-editor-object", "window_identity": "other-window"}
        self.assertFalse(field_editor_aliases([item])[0]["binding_valid"])

    def test_visible_child_is_retained_and_dangling_editor_parent_fails(self):
        item = synthetic_alias()
        child = {"id": "actual-child", "parent": "synthetic-owner", "kind": "image", "evidence": {}}
        original = deepcopy([item, child])
        self.assertTrue(field_editor_aliases([item, child])[0]["binding_valid"])
        self.assertEqual([item, child], original)
        child["parent"] = "synthetic-editor"
        self.assertFalse(field_editor_aliases([item, child])[0]["binding_valid"])

    def test_empty_value_has_a_real_zero_length_utf16_selection(self):
        item = synthetic_alias(value="")
        self.assertTrue(field_editor_aliases([item])[0]["binding_valid"])
        item["evidence"]["native_field_editor"]["selection"]["length"] = 1
        self.assertFalse(field_editor_aliases([item])[0]["binding_valid"])

    def test_current_draw_measurements_are_preserved_without_owner_inheritance(self):
        item = synthetic_alias()
        raw = item["evidence"]["owned_editor_evidence"]
        raw["layout"] = {"line_count": 1, "normal_break_strategy": "none", "truncation": "none"}
        raw["text_bounds"] = [{"x": 49, "y": 57, "width": 30, "height": 16}]
        raw["projection"] = {"line_break_configuration": {"source": "synthetic actual editor layout"},
                             "native_font_drawing": {"status": "unmeasured", "fonts": None}}
        audit = retained_editor_measurements(raw)
        self.assertEqual(audit["layout"], raw["layout"])
        self.assertEqual(audit["evidence"]["text_bounds"], raw["text_bounds"])
        self.assertEqual(audit["evidence"]["line_break_configuration"], raw["projection"]["line_break_configuration"])
        self.assertIsNone(audit["style"]["background"])
        self.assertNotEqual(audit["bounds"], item["bounds"])

    def test_reader_audits_retained_editor_unknowns_without_adding_a_counterpart(self):
        item = synthetic_alias()
        data = capture(item)
        original = deepcopy(data)
        errors = validate_capture(data, "macos", data["scene_id"], data["viewport"])
        owned = [error for error in errors if error.get("source_element") == "synthetic-editor"]
        self.assertTrue(any("Missing measured paint: background" in error["reason"] for error in owned))
        self.assertTrue(any("outline" in error["reason"].lower() for error in owned))
        self.assertTrue(any("font families" in error["reason"] for error in owned))
        self.assertTrue(all(error["element"] == "synthetic-owner" for error in owned))
        self.assertEqual(data, original)
        self.assertEqual(data["coverage"]["emitted_elements"], 1)
        self.assertEqual(len(data["elements"]), 1)

    def test_reader_keeps_original_errors_and_independent_child_paint_unknowns(self):
        item = synthetic_alias()
        item["evidence"]["owned_editor_evidence"]["native_measurement_errors"] = [
            {"path": "$.text_bounds.x", "reason": "Actual TextKit value was nonfinite"}]
        child = {"id": "actual-child", "parent": "synthetic-owner", "region": "dialog", "order": 1,
                 "kind": "image", "text": "", "name": "", "style": {"outline": None}, "evidence": {}}
        data = capture(item)
        data["elements"].append(child)
        data["coverage"]["emitted_elements"] = 2
        data["extraction_errors"] = ["Original capture failed"]
        errors = validate_capture(data, "macos", data["scene_id"], data["viewport"])
        self.assertTrue(any("Actual TextKit value was nonfinite" in error["reason"] for error in errors))
        self.assertTrue(any("Original capture failed" in error["reason"] for error in errors))
        self.assertTrue(any(error["element"] == "actual-child" and "outline" in error["reason"].lower() for error in errors))

    def test_nonaliases_and_malformed_top_level_are_untouched(self):
        for elements in (None, {}, [], [None], [{"evidence": {}}]):
            self.assertEqual(field_editor_aliases(elements), [])


if __name__ == "__main__":
    unittest.main()
