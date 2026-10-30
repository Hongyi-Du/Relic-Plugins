"""Synthetic 1097cdf/f462776 v2 contracts, not recorded AppKit captures.

The tests launch no application. Actual producer tests/captures remain in CI.
"""
from copy import deepcopy
import unittest

from element_parity import validate_capture
from macos_field_editor import (CELL_FRAME_SOURCE, CONTENT_FRAME_SOURCE, CONTRACT, PROVIDER, SCREEN_SPACE,
                               SOURCE, field_editor_aliases, retained_editor_measurements)


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
    owner = raw_input("synthetic-owner", "synthetic-cell-object", "PaddedCell", "AXTextField", box, True)
    del owner["native_view_geometry"]  # The actual AX owner is an NSCell, not an NSView.
    editor = raw_input("synthetic-editor", "synthetic-editor-object", editor_class, "AXTextArea", edit_box, False)
    owner["identifier"] = "relic-input/member-rename"
    owner["raw_node_id"] = owner["id"]
    owner["native_field_editor"] = {
        "contract": CONTRACT, "provider": PROVIDER, "owner_identity": owner["object_identity"],
        "owner_class": owner["class"], "owner_identifier": owner["identifier"],
        "control_identity": "synthetic-control-object", "owner_control_view_identity": "synthetic-control-object",
        "control_cell_identity": owner["object_identity"],
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


def synthetic_measured_screen_alias():
    """Synthetic d2fdff1 measurement shape, not a recorded AppKit observation."""
    item = synthetic_alias()
    raw = item["evidence"]
    receipt = raw["native_field_editor"]
    box = {"x": 40, "y": 50, "width": 195, "height": 32.5}
    item["bounds"] = deepcopy(box)
    item["visible_bounds"] = deepcopy(box)
    raw["rect"] = deepcopy(box)
    raw["visibleRect"] = deepcopy(box)
    screen = {"x": 1040, "y": 2817.5, "width": 195, "height": 32.5}
    receipt["owner_screen_bounds"] = deepcopy(screen)
    receipt["owner_ax_frame"] = {
        "source": CELL_FRAME_SOURCE, "owner_identity": raw["object_identity"],
        "coordinate_space": SCREEN_SPACE, "bounds": deepcopy(screen)}
    receipt["content_screen_frame"] = {
        "source": CONTENT_FRAME_SOURCE, "window_identity": receipt["window_identity"],
        "bounds": {"x": 1000, "y": 2000, "width": 1440, "height": 900}}
    editor_screen = {"x": 1049, "y": 2824, "width": 151, "height": 20}
    receipt["editor_screen_bounds"] = deepcopy(editor_screen)
    raw["owned_editor_evidence"]["native_view_geometry"]["screen_bounds"] = deepcopy(editor_screen)
    return item


class MacFieldEditorTests(unittest.TestCase):
    def test_complete_actual_cell_and_content_frames_prove_only_position(self):
        item = synthetic_measured_screen_alias()
        original = deepcopy(item)
        result, = field_editor_aliases([item])
        self.assertTrue(result["binding_valid"], result["issues"])
        self.assertEqual(result["measurement_issues"], [])
        proof = result["cell_screen_position"]
        self.assertTrue(proof["screen_position_relation_proven"])
        self.assertEqual(proof["converted_cell_frame"], item["evidence"]["rect"])
        self.assertFalse(result["retained_measurements"]["state"]["focused"])
        self.assertIsNone(result["retained_measurements"]["style"]["background"])
        self.assertEqual(item, original)

    def test_actual_negative_display_origin_uses_content_frame_not_display_size(self):
        item = synthetic_measured_screen_alias()
        receipt = item["evidence"]["native_field_editor"]
        receipt["content_screen_frame"]["bounds"].update(x=-1440, y=-900)
        receipt["owner_ax_frame"]["bounds"].update(x=-1400, y=-82.5)
        receipt["owner_screen_bounds"].update(x=-1400, y=-82.5)
        receipt["editor_screen_bounds"].update(x=-1391, y=-76)
        item["evidence"]["owned_editor_evidence"]["native_view_geometry"]["screen_bounds"].update(x=-1391, y=-76)
        result, = field_editor_aliases([item])
        self.assertEqual(result["measurement_issues"], [])
        self.assertEqual(result["cell_screen_position"]["converted_cell_frame"], item["bounds"])

    def test_missing_or_foreign_measurement_frames_keep_the_position_failure(self):
        mutations = [
            ("owner_ax_frame", None, None), ("content_screen_frame", None, None),
            ("owner_ax_frame", "source", "copied control position"),
            ("owner_ax_frame", "owner_identity", "foreign-cell"),
            ("owner_ax_frame", "coordinate_space", "window coordinates (top-left)"),
            ("owner_ax_frame", "bounds", None),
            ("content_screen_frame", "source", "NSScreen.frame"),
            ("content_screen_frame", "window_identity", "foreign-window"),
            ("content_screen_frame", "coordinate_space", "AX global top-left"),
            ("content_screen_frame", "bounds", None),
        ]
        for frame, field, value in mutations:
            with self.subTest(frame=frame, field=field):
                item = synthetic_measured_screen_alias()
                receipt = item["evidence"]["native_field_editor"]
                if field is None:
                    del receipt[frame]
                else:
                    receipt[frame][field] = value
                original = deepcopy(item)
                result, = field_editor_aliases([item])
                self.assertFalse(result["cell_screen_position"]["screen_position_relation_proven"])
                self.assertEqual(len(result["measurement_issues"]), 1)
                self.assertEqual(item, original)

    def test_each_cell_and_control_coordinate_is_independently_checked(self):
        for frame in ("owner_ax_frame", "owner_screen_bounds"):
            for coordinate in ("x", "y", "width", "height"):
                with self.subTest(frame=frame, coordinate=coordinate):
                    item = synthetic_measured_screen_alias()
                    receipt = item["evidence"]["native_field_editor"]
                    bounds = receipt[frame]["bounds"] if frame == "owner_ax_frame" else receipt[frame]
                    bounds[coordinate] += 1
                    self.assertTrue(field_editor_aliases([item])[0]["measurement_issues"])

    def test_actual_content_origin_and_max_y_must_reproduce_raw_rect(self):
        for coordinate in ("x", "y", "height"):
            with self.subTest(coordinate=coordinate):
                item = synthetic_measured_screen_alias()
                item["evidence"]["native_field_editor"]["content_screen_frame"]["bounds"][coordinate] += 1
                result, = field_editor_aliases([item])
                self.assertTrue(result["measurement_issues"])
                self.assertTrue(any("converted" in failure for failure in result["cell_screen_position"]["failures"]))

    def test_raw_and_canonical_owner_boxes_cannot_be_filled_from_the_receipt(self):
        for coordinate in ("x", "y", "width", "height"):
            for field in ("raw", "canonical"):
                with self.subTest(coordinate=coordinate, field=field):
                    item = synthetic_measured_screen_alias()
                    bounds = item["evidence"]["rect"] if field == "raw" else item["bounds"]
                    bounds[coordinate] += 1
                    original = deepcopy(item)
                    self.assertTrue(field_editor_aliases([item])[0]["measurement_issues"])
                    self.assertEqual(item, original)

    def test_nonfinite_boolean_or_zero_frame_measurements_remain_unknown(self):
        for frame in ("owner_ax_frame", "content_screen_frame"):
            for coordinate, value in (("x", float("inf")), ("y", True), ("width", 0), ("height", -1)):
                with self.subTest(frame=frame, coordinate=coordinate, value=value):
                    item = synthetic_measured_screen_alias()
                    item["evidence"]["native_field_editor"][frame]["bounds"][coordinate] = value
                    self.assertTrue(field_editor_aliases([item])[0]["measurement_issues"])

    def test_matching_frames_cannot_override_a_foreign_alias_binding(self):
        item = synthetic_measured_screen_alias()
        item["evidence"]["native_field_editor"]["control_cell_identity"] = "other-cell"
        result, = field_editor_aliases([item])
        self.assertFalse(result["binding_valid"])
        self.assertFalse(result["cell_screen_position"]["screen_position_relation_proven"])

    def test_reader_removes_only_the_measured_cell_position_error(self):
        item = synthetic_measured_screen_alias()
        data = capture(item)
        original = deepcopy(data)
        errors = validate_capture(data, "macos", data["scene_id"], data["viewport"])
        self.assertFalse(any("Cell screen-position cross-check is unmeasured" in error["reason"] for error in errors))
        owned = [error for error in errors if error.get("source_element") == "synthetic-editor"]
        self.assertTrue(any("Missing measured paint: background" in error["reason"] for error in owned))
        self.assertTrue(any("outline" in error["reason"].lower() for error in owned))
        self.assertTrue(any("font families" in error["reason"] for error in owned))
        self.assertEqual(data, original)
        self.assertEqual(len(data["elements"]), 1)

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
            ("control_identity", ""), ("control_identity", "synthetic-cell-object"),
            ("control_identity", "synthetic-editor-object"), ("owner_control_view_identity", "foreign-control"),
            ("control_cell_identity", "foreign-cell"),
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

    def test_v1_control_binding_is_explicitly_rejected(self):
        item = synthetic_alias()
        item["evidence"]["native_field_editor"]["contract"] = "appkit-current-field-editor-v1"
        result, = field_editor_aliases([item])
        self.assertFalse(result["binding_valid"])
        self.assertTrue(any("contract" in issue for issue in result["issues"]))
        item = synthetic_alias()
        item["evidence"]["class"] = "Control"
        item["evidence"]["native_field_editor"]["owner_class"] = "Control"
        self.assertFalse(field_editor_aliases([item])[0]["binding_valid"])

    def test_cell_geometry_keeps_its_real_coordinate_quantity_without_inventing_a_view(self):
        item = synthetic_alias()
        self.assertNotIn("native_view_geometry", item["evidence"])
        # Actual AX topLeft(window) and control screen positions differ. No
        # screen origin is inferred from a fixture or a reference screenshot.
        screen = item["evidence"]["native_field_editor"]["owner_screen_bounds"]
        screen.update(x=1000, y=2000)
        result, = field_editor_aliases([item])
        self.assertTrue(result["binding_valid"])
        self.assertEqual(len(result["measurement_issues"]), 1)
        quantities = result["measurement_issues"][0]["quantities"]
        self.assertFalse(quantities["screen_position_relation_proven"])
        self.assertEqual(quantities["control_screen_frame"]["bounds"], screen)
        self.assertEqual(quantities["cell_ax_window_frame"]["bounds"], item["evidence"]["rect"])
        screen["width"] += 1
        self.assertFalse(field_editor_aliases([item])[0]["binding_valid"])

    def test_each_actual_cell_control_link_is_required(self):
        for key in ("control_identity", "owner_control_view_identity", "control_cell_identity"):
            with self.subTest(key=key):
                item = synthetic_alias()
                del item["evidence"]["native_field_editor"][key]
                self.assertFalse(field_editor_aliases([item])[0]["binding_valid"])

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
        self.assertTrue(any("Cell screen-position cross-check is unmeasured" in error["reason"] for error in errors))
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
