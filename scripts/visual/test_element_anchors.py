"""Recorded correspondence regressions; no app, browser or capture is started."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from element_anchors import anonymous_anchor_pairs, descendant_anchor_pairs
from element_parity import compare_elements, match_elements


class AnonymousAnchorTests(unittest.TestCase):
    @staticmethod
    def settings_layers():
        # Reduced d59bede settings tree topology. These are synthetic style-free
        # records using the actual layer ids/parent relationships, not a golden
        # paint measurement or a passing scene fixture.
        def node(eid, parent, kind="card", text="", name=""):
            return {"id": eid, "parent": parent, "region": "dialog", "kind": kind, "text": text, "name": name}
        reference = [node("dom-494", None, "region", name="设置"), node("dom-495", "dom-494"),
                     node("dom-496:text-0", "dom-495", "text", "设置"),
                     node("dom-497", "dom-495", "tab", "个人资料"),
                     node("dom-500", "dom-495", "tab", "外观"),
                     node("dom-522:text-0", "dom-494", "text", "外观")]
        native = [node("xaml-1242", None, "region", name="设置"), node("xaml-1251", "xaml-1242"),
                  node("xaml-1255", "xaml-1251"), node("xaml-1256", "xaml-1255"),
                  node("xaml-1258:run:0", "xaml-1256", "text", "设置"),
                  node("xaml-1265", "xaml-1256", "tab", "个人资料"),
                  node("xaml-1277", "xaml-1256", "tab", "外观"),
                  node("xaml-1360:run:0", "xaml-1255", "text", "外观")]
        for elements in reference, native:
            for order, element in enumerate(elements): element["order"] = order
        return reference, native

    def test_unique_descendant_anchors_find_nav_without_consuming_real_white_layers(self):
        reference, native = self.settings_layers(); original = deepcopy((reference, native))
        mapped, missing, extra = self.mapping(reference, native)
        self.assertEqual(mapped["dom-495"], "xaml-1256")
        self.assertEqual([native[index]["id"] for index in extra], ["xaml-1251", "xaml-1255"])
        self.assertEqual(missing, [])
        self.assertEqual((reference, native), original)

    def test_descendant_anchors_never_consider_box_color_or_child_reading_order(self):
        reference, native = self.settings_layers()
        for index, node in enumerate(native):
            node.update(bounds={"x": index * 200, "width": 7}, style={"background": [1, 2, 3, 4]})
        native[5]["order"], native[6]["order"] = native[6]["order"], native[5]["order"]
        mapped, _, extra = self.mapping(reference, native)
        self.assertEqual(mapped["dom-495"], "xaml-1256")
        report = compare_elements(reference, native)
        self.assertTrue(report["geometry_out_of_tolerance"])
        self.assertTrue(report["order_mismatch"])
        self.assertTrue(extra)

    def test_identical_nested_wrapper_signatures_remain_ambiguous(self):
        reference, native = self.settings_layers()
        # Remove the matched main-pane descendant. All three native layers
        # then enclose the same anchors; there is no unique actual nav owner.
        pairs = [(0, 0), (2, 4), (3, 5), (4, 6)]
        self.assertEqual(descendant_anchor_pairs(reference, native, pairs, {1}, {1, 2, 3}), [])

    def test_one_anchor_and_its_nested_icon_do_not_supply_independent_support(self):
        reference, native = self.settings_layers()
        reference[4].update(parent=reference[3]["id"], kind="icon", text="")
        native[6].update(parent=native[5]["id"], kind="icon", text="")
        self.assertEqual(descendant_anchor_pairs(reference, native, [(0, 0), (3, 5), (4, 6), (5, 7)], {1}, {1, 2, 3}), [])

    def test_foreign_region_known_parent_or_incomplete_descendant_set_never_pairs(self):
        for change in ("region", "parent", "extra-anchor"):
            with self.subTest(change=change):
                reference, native = self.settings_layers()
                pairs = [(0, 0), (2, 4), (3, 5), (4, 6), (5, 7)]
                if change == "region": native[3]["region"] = "menu"
                elif change == "parent": native[3]["parent"] = native[7]["id"]
                else: native[7]["parent"] = native[3]["id"]
                self.assertEqual(descendant_anchor_pairs(reference, native, pairs, {1}, {1, 2, 3}), [])

    def test_duplicate_ids_and_cyclic_parent_chain_cannot_supply_ownership(self):
        for change in ("duplicate", "cycle"):
            reference, native = self.settings_layers()
            if change == "duplicate": native.append(deepcopy(native[3]))
            else: native[3]["parent"] = native[5]["id"]
            self.assertEqual(descendant_anchor_pairs(reference, native, [(0, 0), (2, 4), (3, 5), (4, 6), (5, 7)], {1}, {1, 2, 3}), [])

    def recorded(self, scene):
        data = json.loads((Path(__file__).parent / "fixtures" / "anonymous_anchors_15581b1.json").read_text(encoding="utf-8"))
        return data["scenes"][scene]["reference-macos"], data["scenes"][scene]["macos"]

    def mapping(self, reference, native):
        pairs, missing, extra = match_elements(reference, native)
        self.assertEqual(len({r for r, _ in pairs}), len(pairs))
        self.assertEqual(len({n for _, n in pairs}), len(pairs))
        return {reference[r]["id"]: native[n]["id"] for r, n in pairs}, missing, extra

    def test_recorded_chart_header_tracks_legend_and_canvas_keep_their_anchors(self):
        reference, native = self.recorded("chart")
        mapped, missing, extra = self.mapping(reference, native)
        expected = {"dom-495": "window/3/0", "dom-509::after": "window/3/0/5",
                    "dom-511::after": "window/3/0/8", "dom-515": "window/3/2",
                    "dom-517": "window/3/2/0", "dom-519": "window/3/2/2",
                    "dom-521": "window/3/2/4", "dom-523": "window/3/2/6", "dom-527": "window/3/3"}
        for left, right in expected.items():
            self.assertEqual(mapped.get(left), right, left)
        self.assertEqual(mapped.get("dom-525"), "surface-paint/294", "The actual divider is emitted later in the native traversal")
        self.assertTrue(any(issue["reference"] == "dom-525" for issue in compare_elements(reference, native)["order_mismatch"]))

    def test_recorded_recipient_avatar_is_paired_with_its_actual_row(self):
        reference, native = self.recorded("recipients")
        mapped, missing, extra = self.mapping(reference, native)
        self.assertEqual(mapped.get("dom-497"), "surface-paint/274")
        self.assertEqual(mapped.get("dom-496"), "window/1/0/view-0/view-0/view-0/view-0/0", "The actual checkbox is emitted later in the native traversal")
        self.assertTrue(extra, "The extra native menu wrapper cannot disappear")

    def test_pairing_does_not_change_or_accept_recorded_measurements(self):
        reference, native = self.recorded("chart")
        original = deepcopy((reference, native))
        report = compare_elements(reference, native)
        self.assertEqual((reference, native), original)
        self.assertTrue(report["style_out_of_tolerance"], "Omitted paint evidence stays unknown after correspondence is repaired")
        self.assertTrue(report["state_mismatch"], "Omitted state evidence is not supplied by anchors")
        self.assertTrue(report["order_mismatch"], "The actual late divider still fails reading order")

    def test_removing_a_real_divider_does_not_shift_the_recorded_cards(self):
        reference, native = self.recorded("chart")
        native = [item for item in native if item["id"] != "surface-paint/294"]
        mapped, missing, extra = self.mapping(reference, native)
        self.assertEqual(mapped.get("dom-495"), "window/3/0")
        self.assertEqual(mapped.get("dom-527"), "window/3/3")
        self.assertIn("dom-525", [reference[index]["id"] for index in missing])

    def test_removing_real_checkboxes_does_not_consume_the_recorded_avatar(self):
        reference, native = self.recorded("recipients")
        native = [item for item in native if item["kind"] != "checkbox"]
        mapped, missing, extra = self.mapping(reference, native)
        self.assertEqual(mapped.get("dom-497"), "surface-paint/274")
        self.assertIn("dom-496", [reference[index]["id"] for index in missing])

    def test_no_shared_anchors_does_not_establish_identity_from_geometry(self):
        left = [{"id": "a", "region": "dialog", "kind": "card", "bounds": {"x": 1}}]
        right = [{"id": "b", "region": "dialog", "kind": "card", "bounds": {"x": 1}}]
        self.assertEqual(anonymous_anchor_pairs(left, right, [], {0}, {0}), [])

    def test_known_parents_separate_otherwise_identical_anonymous_nodes(self):
        left = [{"id": "row-a", "name": "A", "region": "menu", "order": 0},
                {"id": "row-b", "name": "B", "region": "menu", "order": 1},
                {"id": "avatar-a", "parent": "row-a", "kind": "avatar", "region": "menu", "order": 2}]
        right = [{"id": "row-c", "name": "A", "region": "menu", "order": 0},
                 {"id": "row-d", "name": "B", "region": "menu", "order": 1},
                 {"id": "avatar-d", "parent": "row-d", "kind": "avatar", "region": "menu", "order": 2}]
        self.assertEqual(anonymous_anchor_pairs(left, right, [(0, 0), (1, 1)], {2}, {2}), [])

    def test_unequal_anonymous_groups_remain_ambiguous(self):
        left = [{"id": "title", "text": "title", "region": "dialog", "order": 0},
                {"id": "a", "kind": "card", "region": "dialog", "order": 1}]
        right = deepcopy(left) + [{"id": "b", "kind": "card", "region": "dialog", "order": 2}]
        self.assertEqual(anonymous_anchor_pairs(left, right, [(0, 0)], {1}, {1, 2}), [])


if __name__ == "__main__":
    unittest.main()
