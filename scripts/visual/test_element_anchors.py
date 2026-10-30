"""Recorded correspondence regressions; no app, browser or capture is started."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from element_anchors import anonymous_anchor_pairs
from element_parity import compare_elements, match_elements


class AnonymousAnchorTests(unittest.TestCase):
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
        self.assertIn("dom-525", [reference[index]["id"] for index in missing], "The missing divider must remain missing")

    def test_recorded_recipient_avatar_is_paired_with_its_actual_row(self):
        reference, native = self.recorded("recipients")
        mapped, missing, extra = self.mapping(reference, native)
        self.assertEqual(mapped.get("dom-497"), "surface-paint/274")
        self.assertIn("dom-496", [reference[index]["id"] for index in missing], "No avatar may absorb the missing checkbox")
        self.assertTrue(extra, "The extra native menu wrapper cannot disappear")

    def test_pairing_does_not_change_or_accept_recorded_measurements(self):
        reference, native = self.recorded("chart")
        original = deepcopy((reference, native))
        report = compare_elements(reference, native)
        self.assertEqual((reference, native), original)
        self.assertTrue(report["style_out_of_tolerance"], "Omitted paint evidence stays unknown after correspondence is repaired")
        self.assertTrue(report["state_mismatch"], "Omitted state evidence is not supplied by anchors")
        self.assertTrue(report["missing"], "The actual missing divider still fails")

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
