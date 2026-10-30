"""Pure tests; run by CI, never start a native window or UIA provider."""
import copy
import json
from pathlib import Path
import unittest

from windows_toggle_parts import CONTRACT, SOURCE, windows_toggle_parts


def recorded():
    path = Path(__file__).with_name("fixtures") / "toggle_parts_recorded_e469311.json"
    return json.loads(path.read_text(encoding="utf-8"))


def current_contract():
    """Controlled new contract atop old measured identities, not a new CI run."""
    data = recorded()
    nodes = {node["id"]: node for node in data["raw_nodes"]}
    owner, thumb = nodes[data["owner_id"]], nodes[data["thumb_id"]]
    owner["type"] = "NativeOverviewToggle"
    thumb["interaction_evidence"]["is_hit_test_visible"] = False
    state = {"is_checked": False, "is_three_state": False, "is_enabled": True,
             "focus_state": "Unfocused", "is_loaded": True,
             "thumb_is_hit_test_visible": False, "thumb_child_is_null": True}
    chain = ["xaml-864", "xaml-862", "xaml-861", "xaml-860", "xaml-859"]
    owner["native_toggle_parts"] = {
        "source": SOURCE, "version": 1, "status": "measured", "owner_id": owner["id"],
        "owner_runtime_type": "Relic.NativeOverviewToggle", "track_id": "xaml-861",
        "shadow_id": "xaml-862", "thumb_id": thumb["id"],
        "owner_content_is_track": True, "track_child_is_shadow": True, "shadow_surface_is_thumb": True,
        "current_parts_same_objects": True, "part_contract": CONTRACT,
        "actual_ancestor_edges": [{"child_id": child, "parent_id": parent,
            "actual_parent_in_visual_walk": True, "captured_parent_matches": True}
            for child, parent in zip(chain, chain[1:])],
        "reaches_same_owner_object": True, "all_captured_edges_match": True,
        "before": copy.deepcopy(state), "after": copy.deepcopy(state), "getters_unchanged": True,
        "observed_at_utc": "controlled-fixture-not-a-runtime-observation", "errors": [],
    }
    return data, nodes, owner["native_toggle_parts"]


def current_track_contract():
    """Synthetic paint measurements extending the recorded state-only fixture."""
    data, nodes, receipt = current_contract()
    owner, track = nodes[data["owner_id"]], nodes[receipt["track_id"]]
    bounds = {"x": 1117, "y": 289.79998779296875, "width": 32, "height": 18}
    transform = {"m11": 1, "m12": 0, "m21": 0, "m22": 1,
                 "offset_x": bounds["x"], "offset_y": bounds["y"]}
    for node in (owner, track):
        node.update(bounds=copy.deepcopy(bounds), visible_bounds=copy.deepcopy(bounds),
                    transform=copy.deepcopy(transform), opacity=1)
    owner["style"] = {"background": [255, 255, 255, 0], "background_image": "none",
                      "border_widths": [0, 0, 0, 0], "corner_radius": 4}
    track["style"] = {"background": [222, 219, 212, 255], "background_image": "none",
                      "background_brush_type": "SolidColorBrush", "border_color": [0, 0, 0, 0],
                      "border_width": 0, "border_widths": [0, 0, 0, 0],
                      "border_colors": [[0, 0, 0, 0]] * 4, "border_styles": ["none"] * 4,
                      "corner_radius": 9, "corner_radii": [9] * 4,
                      "shadow": None, "brush_evidence": {"background": {"type": "synthetic-live-brush"}}}
    return data, nodes, receipt


class TogglePartStateTests(unittest.TestCase):
    def test_old_recorded_toggle_never_acquires_a_new_part_contract(self):
        data = recorded()
        before = copy.deepcopy(data)
        result = windows_toggle_parts(data["raw_nodes"], data["uia"])
        self.assertEqual({}, result["parts"])
        self.assertEqual(before, data)

    def test_only_owned_thumb_gets_originating_state_and_raw_nulls_remain(self):
        data, nodes, receipt = current_contract()
        before = copy.deepcopy(data)
        result = windows_toggle_parts(data["raw_nodes"], data["uia"])
        self.assertEqual([], result["unresolved"])
        self.assertEqual({data["thumb_id"]}, set(result["parts"]))
        part = result["parts"][data["thumb_id"]]
        self.assertEqual({"enabled": True, "checked": False, "focused": False, "indeterminate": False}, part["state"])
        self.assertIsNone(part["evidence"]["thumb_raw_state"]["checked"])
        self.assertEqual([42, 196938, 4, 202], part["evidence"]["owner_identity"]["runtime_id"])
        self.assertIsNone(part["evidence"]["final_frame_contribution"])
        self.assertEqual(before, data)

    def test_live_values_are_not_defaulted_to_enabled_unchecked_unfocused(self):
        data, nodes, receipt = current_contract()
        for snapshot in (receipt["before"], receipt["after"]):
            snapshot.update(is_enabled=False, is_checked=True, focus_state="Keyboard")
        state = {"enabled": False, "checked": True, "focused": True, "indeterminate": False}
        nodes[data["owner_id"]]["state"].update(state)
        data["uia"]["raw_nodes"][0]["state"].update(state, toggle="On")
        result = windows_toggle_parts(data["raw_nodes"], data["uia"])
        self.assertEqual(state, result["parts"][data["thumb_id"]]["state"])

    def test_independent_text_never_receives_a_button_or_toggle_state(self):
        data, nodes, receipt = current_contract()
        child = {"id": "independent-text", "parent": data["owner_id"], "type": "TextBlock",
                 "text": "synthetic independent label", "state": {"enabled": None, "focused": None}}
        data["raw_nodes"].append(child)
        result = windows_toggle_parts(data["raw_nodes"], data["uia"])
        self.assertNotIn(child["id"], result["parts"])
        self.assertEqual({data["thumb_id"]}, set(result["parts"]))

    def test_invalid_or_changed_ownership_and_state_is_not_projected(self):
        cases = ["missing-contract", "wrong-runtime-type", "bad-version", "old-content-owner", "missing-thumb",
                 "duplicate-thumb", "changed-parent", "foreign-owner", "stale-edge", "independent-control",
                 "hit-testable-thumb", "thumb-child", "changed-getter", "unknown-checked", "three-state",
                 "provider-state-conflict", "owner-state-conflict", "missing-toggle-pattern", "wrong-provider-kind",
                 "thumb-own-state", "failed-held-release", "duplicate-runtime-id", "foreign-peer", "unloaded",
                 "unknown-part-peer", "missing-part-state", "null-owner-state", "numeric-after-getter"]
        for case in cases:
            with self.subTest(case=case):
                data, nodes, receipt = current_contract()
                owner, thumb = nodes[data["owner_id"]], nodes[data["thumb_id"]]
                provider = data["uia"]["raw_nodes"][0]
                if case == "missing-contract": owner.pop("native_toggle_parts")
                elif case == "wrong-runtime-type": receipt["owner_runtime_type"] = "Relic.OtherToggle"
                elif case == "bad-version": receipt["version"] = True
                elif case == "old-content-owner": nodes["xaml-861"]["declared_content_owner"] = "old-owner"
                elif case == "missing-thumb": data["raw_nodes"].remove(thumb)
                elif case == "duplicate-thumb": data["raw_nodes"].append(copy.deepcopy(thumb))
                elif case == "changed-parent": thumb["parent"] = "xaml-861"
                elif case == "foreign-owner": receipt["owner_id"] = "another-owner"
                elif case == "stale-edge": receipt["actual_ancestor_edges"][0]["captured_parent_matches"] = False
                elif case == "independent-control": nodes["xaml-862"]["interaction_evidence"]["is_control"] = True
                elif case == "hit-testable-thumb": thumb["interaction_evidence"]["is_hit_test_visible"] = True
                elif case == "thumb-child": data["raw_nodes"].append({"id": "child", "parent": thumb["id"], "type": "Button"})
                elif case == "changed-getter": receipt["after"]["is_checked"] = True
                elif case == "unknown-checked":
                    for state in (receipt["before"], receipt["after"]): state["is_checked"] = None
                elif case == "three-state":
                    for state in (receipt["before"], receipt["after"]): state["is_three_state"] = True
                elif case == "provider-state-conflict": provider["state"]["checked"] = True
                elif case == "owner-state-conflict": owner["state"]["focused"] = True
                elif case == "missing-toggle-pattern": provider["supported_patterns"] = []
                elif case == "wrong-provider-kind": provider["control_type"] = "ControlType.Text"
                elif case == "thumb-own-state": thumb["state"]["checked"] = True
                elif case == "failed-held-release": data["uia"]["observer_hold"]["release"]["status"] = "failed"
                elif case == "duplicate-runtime-id":
                    other = copy.deepcopy(provider); other["id"] = "duplicate-provider"; data["uia"]["raw_nodes"].append(other)
                elif case == "foreign-peer": owner["automation_identity_evidence"]["same_owner_object"] = False
                elif case == "unloaded":
                    for state in (receipt["before"], receipt["after"]): state["is_loaded"] = False
                elif case == "unknown-part-peer": thumb["automation_identity_evidence"]["status"] = "failed"
                elif case == "missing-part-state": thumb.pop("state")
                elif case == "null-owner-state": owner["state"] = None
                elif case == "numeric-after-getter": receipt["after"]["is_enabled"] = 1
                before = copy.deepcopy(data)
                result = windows_toggle_parts(data["raw_nodes"], data["uia"])
                self.assertEqual({}, result["parts"])
                self.assertTrue(result["unresolved"])
                self.assertEqual(before, data)

    def test_provider_errors_remain_even_with_a_valid_identity_and_part(self):
        data, nodes, receipt = current_contract()
        error = {"type": "controlled-provider-error", "message": "synthetic unrelated provider failure"}
        data["uia"]["extraction_errors"] = [error]
        result = windows_toggle_parts(data["raw_nodes"], data["uia"])
        self.assertIn(data["thumb_id"], result["parts"])
        self.assertEqual([error], data["uia"]["extraction_errors"])

    def test_actual_content_track_paint_belongs_to_toggle_but_thumb_is_independent(self):
        data, nodes, receipt = current_track_contract()
        before = copy.deepcopy(data)
        result = windows_toggle_parts(data["raw_nodes"], data["uia"])
        self.assertEqual([], result["track_unresolved"])
        self.assertEqual({data["owner_id"]}, set(result["tracks"]))
        track = result["tracks"][data["owner_id"]]
        self.assertEqual(receipt["track_id"], track["track_id"])
        self.assertEqual([222, 219, 212, 255], track["style"]["background"])
        self.assertEqual(9, track["style"]["corner_radius"])
        self.assertEqual(data["thumb_id"], track["thumb_id"])
        self.assertEqual({data["thumb_id"]}, set(result["parts"]))
        self.assertTrue(track["evidence"]["thumb_remains_independent"])
        self.assertIsNone(track["evidence"]["raw_track"]["style"]["shadow"])
        self.assertNotIn("shadow", track["style"])
        self.assertIsNone(track["evidence"]["final_frame_contribution"])
        self.assertEqual(before, data)

    def test_state_only_fixture_does_not_acquire_invented_track_paint(self):
        data, nodes, receipt = current_contract()
        result = windows_toggle_parts(data["raw_nodes"], data["uia"])
        self.assertEqual({}, result["tracks"])
        self.assertTrue(result["track_unresolved"])
        self.assertIn(data["thumb_id"], result["parts"])

    def test_track_ownership_refuses_foreign_identity_or_modified_actual_content(self):
        for change in ("foreign-peer", "failed-release", "extra-content", "shared-track", "independent-track"):
            with self.subTest(change=change):
                data, nodes, receipt = current_track_contract()
                owner, track = nodes[data["owner_id"]], nodes[receipt["track_id"]]
                if change == "foreign-peer": owner["automation_identity_evidence"]["same_owner_object"] = False
                elif change == "failed-release": data["uia"]["observer_hold"]["release"]["status"] = "failed"
                elif change == "extra-content": data["raw_nodes"].append({"id": "extra", "parent": track["id"], "type": "Border"})
                elif change == "shared-track":
                    other = copy.deepcopy(owner); other["id"] = "other-toggle"; data["raw_nodes"].append(other)
                elif change == "independent-track": track["interaction_evidence"]["is_control"] = True
                self.assertEqual({}, windows_toggle_parts(data["raw_nodes"], data["uia"])["tracks"])

    def test_track_style_quantity_requires_actual_box_transform_and_clear_owner(self):
        for change in ("missing-bounds", "shifted-track", "transformed-track", "opacity", "extra-owner-fill", "owner-border", "missing-style", "bool-width"):
            with self.subTest(change=change):
                data, nodes, receipt = current_track_contract()
                owner, track = nodes[data["owner_id"]], nodes[receipt["track_id"]]
                if change == "missing-bounds": track["bounds"] = None
                elif change == "shifted-track": track["bounds"]["x"] += 1
                elif change == "transformed-track": track["transform"]["m11"] = 2
                elif change == "opacity": track["opacity"] = .5
                elif change == "extra-owner-fill": owner["style"]["background"][3] = 255
                elif change == "owner-border": owner["style"]["border_widths"][0] = 1
                elif change == "missing-style": track["style"] = None
                elif change == "bool-width": track["bounds"]["width"] = True
                before = copy.deepcopy(data)
                result = windows_toggle_parts(data["raw_nodes"], data["uia"])
                self.assertEqual({}, result["tracks"])
                self.assertTrue(result["track_unresolved"])
                self.assertIn(data["thumb_id"], result["parts"])
                self.assertEqual(before, data)

    def test_missing_track_color_stays_unknown_instead_of_copying_owner_or_reference(self):
        data, nodes, receipt = current_track_contract()
        nodes[receipt["track_id"]]["style"]["background"] = None
        result = windows_toggle_parts(data["raw_nodes"], data["uia"])
        self.assertIsNone(result["tracks"][data["owner_id"]]["style"]["background"])


if __name__ == "__main__":
    unittest.main()
