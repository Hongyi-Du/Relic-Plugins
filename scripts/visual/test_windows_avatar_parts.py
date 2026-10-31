"""Pure CI fixtures; no native process, UIA provider, or window is started."""
import copy
import json
from pathlib import Path
import unittest

from windows_avatar_parts import SOURCE, windows_avatar_parts


def recorded():
    return json.loads((Path(__file__).with_name("fixtures") / "avatar_parts_recorded_de8c4ff.json").read_text(encoding="utf-8"))


def current_contract():
    """Controlled new production contract atop old measured parts, not new CI evidence."""
    data = recorded()
    nodes = {node["id"]: node for node in data["raw_nodes"]}
    nodes["xaml-413"]["type"] = "NativeOrganizationAvatarPaint"
    for owner_id, kind, roles, edges in (
        ("xaml-411", "organization-outline",
         {"paint": "xaml-413", "surface": "xaml-414", "initial": "xaml-415", "outline": "xaml-416"},
         {"xaml-413": "xaml-412", "xaml-412": "xaml-411", "xaml-414": "xaml-413",
          "xaml-415": "xaml-414", "xaml-416": "xaml-413"}),
        ("xaml-569", "reply-border", {"paint": "xaml-571", "frame": "xaml-567", "layout": "xaml-568"},
         {"xaml-571": "xaml-570", "xaml-570": "xaml-569", "xaml-569": "xaml-568", "xaml-568": "xaml-567"}),
    ):
        owner = nodes[owner_id]
        state = {"owner_tag_is_paint": True, "owner_template_is_retained": True,
                 "owner_is_loaded": True, "owner_is_tab_stop": False,
                 "composition_picture_is_owner": True, "retained_composition_same_object": True,
                 "organization_current_parts": True if kind == "organization-outline" else None,
                 "organization_has_cabinet_ring": False if kind == "organization-outline" else None,
                 "reply_current_parts": True if kind == "reply-border" else None,
                 "reply_frame_count": 1 if kind == "reply-border" else 0,
                 "reply_frame_contract_type": "Relic.NativeReplyAvatarFrame" if kind == "reply-border" else None}
        rows = []
        for role, part_id in roles.items():
            typ = nodes[part_id]["type"]
            runtime = ("Relic." if typ.startswith("Native") else
                       "Microsoft.UI.Xaml.Shapes." if typ == "Rectangle" else "Microsoft.UI.Xaml.Controls.") + typ
            rows.append({"role": role, "id": part_id, "runtime_type": runtime, "same_retained_object_in_capture": True})
        owner["native_avatar_parts"] = {
            "source": SOURCE, "version": 2, "status": "measured", "kind": kind,
            "owner_id": owner_id, "owner_runtime_type": "Microsoft.UI.Xaml.Controls.PersonPicture",
            "composition_runtime_type": "Relic.NativeAvatarPicture",
            "parts": rows, "actual_ancestor_edges": [{"child_id": child, "parent_id": parent,
                "actual_parent_in_visual_walk": True, "captured_parent_matches": True} for child, parent in edges.items()],
            "before": copy.deepcopy(state), "after": copy.deepcopy(state), "getters_unchanged": True,
            "errors": [], "observed_at_utc": "controlled-fixture-not-a-runtime-observation",
        }
    return data, nodes


class AvatarPartsTests(unittest.TestCase):
    def test_old_real_de8_parts_are_not_grouped_by_name_color_or_coordinates(self):
        data = recorded()
        before = copy.deepcopy(data)
        result = windows_avatar_parts(data["raw_nodes"], data["uia"])
        self.assertEqual({}, result["owners"])
        self.assertEqual(before, data)

    def test_only_real_retained_decorations_are_owned_and_all_raw_data_remains(self):
        data, nodes = current_contract()
        before = copy.deepcopy(data)
        result = windows_avatar_parts(data["raw_nodes"], data["uia"])
        self.assertEqual([], result["unresolved"])
        self.assertEqual({"xaml-411", "xaml-569"}, set(result["owners"]))
        outline, reply = result["owners"]["xaml-411"], result["owners"]["xaml-569"]
        self.assertEqual(["xaml-416"], outline["owned_ids"])
        self.assertEqual(["xaml-567"], reply["owned_ids"])
        self.assertEqual("xaml-411", outline["bounds_source"])
        self.assertEqual("xaml-567", reply["bounds_source"])
        self.assertEqual("xaml-567", reply["border_source"])
        self.assertEqual([2, 2, 2, 2], reply["border_style"]["border_widths"])
        self.assertEqual(nodes["xaml-567"]["style"]["border_colors"], reply["border_style"]["border_colors"])
        self.assertEqual([42, 262496, 4, 129], reply["evidence"]["owner_identity"]["runtime_id"])
        self.assertEqual("设计师", reply["evidence"]["raw_owner_name"])
        self.assertNotIn("name", reply)
        self.assertNotIn("text", reply)
        self.assertNotIn("state", reply)
        self.assertIsNone(reply["evidence"]["final_pixel_equivalence"])
        self.assertEqual(before, data)

    def test_native_outline_keeps_its_real_stroke_and_does_not_become_a_border(self):
        data, _ = current_contract()
        result = windows_avatar_parts(data["raw_nodes"], data["uia"])
        owner = result["owners"]["xaml-411"]
        self.assertIsNone(owner["border_source"])
        self.assertEqual({"style": "dashed", "color": [120, 54, 65, 255], "width": 1.5,
                          "offset": None, "contour": None, "dash": [3, 3], "dash_offset": 0}, owner["outline"])
        self.assertEqual({"style.outline.offset", "style.outline.contour"},
                         {issue["property"] for issue in result["unmeasured"]})
        self.assertEqual([2, 2], owner["evidence"]["raw_decoration"]["stroke_evidence"]["raw_pattern"]["dash_array"])

    def test_measured_missing_values_remain_unknown_without_brush_or_width_defaults(self):
        data, nodes = current_contract()
        for field in ("foreground", "stroke_width", "stroke_dash", "stroke_dash_offset"):
            nodes["xaml-416"]["style"][field] = None
        nodes["xaml-567"]["style"]["border_colors"] = None
        result = windows_avatar_parts(data["raw_nodes"], data["uia"])
        self.assertTrue(all(value is None for value in result["owners"]["xaml-411"]["outline"].values()))
        self.assertEqual(7, len(result["unmeasured"]))
        self.assertIsNone(result["owners"]["xaml-569"]["border_style"]["border_colors"])

    def test_bad_retained_contract_or_parent_never_consumes_a_matching_rectangle(self):
        mutations = {
            "no-receipt": lambda d, n: n["xaml-411"].pop("native_avatar_parts"),
            "old-derived-type": lambda d, n: n["xaml-411"].update(type="NativeAvatarPicture"),
            "boolean-version": lambda d, n: n["xaml-411"]["native_avatar_parts"].update(version=True),
            "unknown-parts": lambda d, n: n["xaml-411"]["native_avatar_parts"].update(parts=None),
            "wrong-tag": lambda d, n: n["xaml-411"]["native_avatar_parts"]["before"].update(owner_tag_is_paint=False),
            "detached": lambda d, n: n["xaml-411"]["native_avatar_parts"]["before"].update(owner_is_loaded=False),
            "changed-parent": lambda d, n: n["xaml-416"].update(parent="xaml-568"),
            "missing-live-edge": lambda d, n: n["xaml-411"]["native_avatar_parts"]["actual_ancestor_edges"][0].update(captured_parent_matches=False),
            "unknown-peer": lambda d, n: n["xaml-416"].pop("automation_identity_evidence"),
            "independent-control": lambda d, n: n["xaml-416"]["interaction_evidence"].update(is_control=True),
            "extra-child": lambda d, n: d["raw_nodes"].append({"id": "extra", "parent": "xaml-413", "type": "Button"}),
            "duplicate-id": lambda d, n: d["raw_nodes"].append(copy.deepcopy(n["xaml-416"])),
            "unbound-owner": lambda d, n: n["xaml-411"].pop("automation_identity_evidence"),
            "foreign-case": lambda d, n: d["uia"].update(case_id="another-scene"),
            "failed-release": lambda d, n: d["uia"]["observer_hold"]["release"].update(status="failed"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                data, nodes = current_contract()
                mutate(data, nodes)
                before = copy.deepcopy(data)
                result = windows_avatar_parts(data["raw_nodes"], data["uia"])
                self.assertNotIn("xaml-411", result["owners"])
                self.assertEqual(before, data)

    def test_reply_frame_cannot_consume_an_unrelated_or_compound_parent(self):
        for mutation in ("wrong-owner", "extra-layout-child", "extra-frame-child", "actionable-owner", "unknown-frame-peer"):
            with self.subTest(mutation=mutation):
                data, nodes = current_contract()
                if mutation == "wrong-owner":
                    nodes["xaml-569"]["parent"] = "xaml-413"
                elif mutation == "extra-layout-child":
                    data["raw_nodes"].append({"id": "dot", "parent": "xaml-568", "type": "Ellipse"})
                elif mutation == "extra-frame-child":
                    data["raw_nodes"].append({"id": "another-avatar", "parent": "xaml-567", "type": "PersonPicture"})
                elif mutation == "actionable-owner":
                    data["uia"]["raw_nodes"][1]["supported_patterns"] = ["InvokePatternIdentifiers.Pattern"]
                else:
                    nodes["xaml-567"].pop("automation_identity_evidence")
                result = windows_avatar_parts(data["raw_nodes"], data["uia"])
                self.assertNotIn("xaml-569", result["owners"])

    def test_v2_requires_actual_native_owner_and_stable_retained_composition(self):
        for owner_id in ("xaml-411", "xaml-569"):
            for mutation in ("missing-composition-type", "wrong-composition-type", "old-native-owner-type",
                             "missing-owner-reference", "wrong-owner-reference", "missing-retained-reference",
                             "replaced-retained-reference", "unstable-after", "numeric-reference"):
                with self.subTest(owner_id=owner_id, mutation=mutation):
                    data, nodes = current_contract()
                    receipt = nodes[owner_id]["native_avatar_parts"]
                    if mutation == "missing-composition-type":
                        receipt.pop("composition_runtime_type")
                    elif mutation == "wrong-composition-type":
                        receipt["composition_runtime_type"] = "Relic.UnrelatedComposition"
                    elif mutation == "old-native-owner-type":
                        receipt["owner_runtime_type"] = "Relic.NativeAvatarPicture"
                    elif mutation == "unstable-after":
                        receipt["after"]["retained_composition_same_object"] = False
                    else:
                        key = "composition_picture_is_owner" if mutation in {
                            "missing-owner-reference", "wrong-owner-reference", "numeric-reference"} else "retained_composition_same_object"
                        for snapshot in (receipt["before"], receipt["after"]):
                            if mutation.startswith("missing-"):
                                snapshot.pop(key)
                            else:
                                snapshot[key] = 1 if mutation == "numeric-reference" else False
                    before = copy.deepcopy(data)
                    result = windows_avatar_parts(data["raw_nodes"], data["uia"])
                    self.assertNotIn(owner_id, result["owners"])
                    self.assertTrue(any(issue["owner_id"] == owner_id for issue in result["unresolved"]))
                    self.assertEqual(before, data)

    def test_v1_derived_owner_receipts_are_not_silently_upgraded(self):
        data, nodes = current_contract()
        for owner_id in ("xaml-411", "xaml-569"):
            owner = nodes[owner_id]
            owner["type"] = "NativeAvatarPicture"
            receipt = owner["native_avatar_parts"]
            receipt.update(version=1, owner_runtime_type="Relic.NativeAvatarPicture")
            receipt.pop("composition_runtime_type")
            for snapshot in (receipt["before"], receipt["after"]):
                snapshot.pop("composition_picture_is_owner")
                snapshot.pop("retained_composition_same_object")
        before = copy.deepcopy(data)
        result = windows_avatar_parts(data["raw_nodes"], data["uia"])
        self.assertEqual({}, result["owners"])
        self.assertEqual({"xaml-411", "xaml-569"}, {issue["owner_id"] for issue in result["unresolved"]})
        self.assertEqual(before, data)

    def test_ownership_does_not_clear_existing_capture_or_paint_failures(self):
        data, nodes = current_contract()
        data["uia"]["extraction_errors"] = ["actual-provider-failure"]
        nodes["xaml-416"]["measurement_errors"] = ["actual-contour-unmeasured"]
        before = copy.deepcopy(data)
        result = windows_avatar_parts(data["raw_nodes"], data["uia"])
        self.assertEqual({"xaml-411", "xaml-569"}, set(result["owners"]))
        self.assertEqual(["actual-contour-unmeasured"], result["owners"]["xaml-411"]["evidence"]["raw_decoration"]["measurement_errors"])
        self.assertEqual(before, data)


if __name__ == "__main__":
    unittest.main()
