"""Pure synthetic binding regressions for the audited sidebar organization path."""
from copy import deepcopy
import unittest

from windows_elements import sidebar_organization_avatar_name


def fixture():
    # Same production identities/shape observed in b611b4f group, with synthetic
    # ids and names. These tests do not load a reference or expected counterpart.
    avatar = {"id": "avatar", "parent": "content", "type": "PersonPicture",
              "text": "O", "native_avatar_lookup": {
                  "source": "Actual PersonPicture private attached DependencyProperty lifetime holder",
                  "status": "bound", "owner_id": "avatar", "composition_runtime_type": "Relic.NativeAvatarPicture",
                  "composition_picture_is_owner": True, "current_paint_and_template": True,
                  "lookup_modified_metadata": False},
              "outline_owner_evidence": {"runtime_type": "Microsoft.UI.Xaml.Controls.PersonPicture"}}
    row = {"id": "row", "parent": "list", "type": "NativeSidebarRow",
           "state_evidence": {"source": "Actual NativeSidebarRow organization binding and retained unread badge object",
                              "row_kind": "organization", "owner_id": "row"},
           "outline_owner_evidence": {"runtime_type": "Relic.NativeSidebarRow", "sidebar_row_content": {
               "source": "actual sealed NativeSidebarRow runtime, current template and ContentPresenter/Content object identities",
               "status": "measured", "owner_id": "row", "base_type": "Microsoft.UI.Xaml.Controls.ListViewItem",
               "is_sealed": True, "audited_source": "native/windows/Relic/NativeSidebarRow.cs#NativeSidebarRow",
               "template_type": "Microsoft.UI.Xaml.Controls.ControlTemplate", "template_present": True,
               "same_template_after": True, "same_content_after": True, "visual_child_count": 1,
               "presenter_id": "presenter", "presenter_runtime_type": "Microsoft.UI.Xaml.Controls.ContentPresenter",
               "presenter_is_current_only_child": True, "content_id": "content", "content_type": "Grid",
               "presenter_content_same_object": True, "content_is_current_presenter_child": True}}}
    nodes = [row, {"id": "presenter", "parent": "row", "type": "ContentPresenter"},
             {"id": "content", "parent": "presenter", "type": "Grid"}, avatar,
             {"id": "initial", "parent": "avatar", "type": "TextBlock", "text": "O"}]
    picture = {"id": "uia-avatar", "parent": "uia-row", "name": "Organization display name",
               "is_control_element": False, "is_content_element": False, "supported_patterns": [],
               "state": {"focusable": False, "focused": False, "enabled": True, "hovered": True}}
    providers = [picture, {"id": "uia-row", "parent": "uia-list", "control_type": "ControlType.ListItem",
                          "name": "O Organization display name 11:00", "is_control_element": True,
                          "is_content_element": True},
                 {"id": "uia-initial", "parent": "uia-avatar", "name": "O",
                  "is_control_element": True, "is_content_element": True}]
    bindings = {"pairs": [{"xaml_id": "avatar", "uia_id": "uia-avatar", "runtime_id": [42, 1, 4, 10]},
                           {"xaml_id": "row", "uia_id": "uia-row", "runtime_id": [42, 1, 4, 9]}]}
    return {node["id"]: node for node in nodes}, {node["id"]: node for node in providers}, bindings


class SidebarAvatarNameTests(unittest.TestCase):
    def setUp(self):
        self.nodes, self.providers, self.bindings = fixture()

    def result(self):
        return sidebar_organization_avatar_name(self.nodes["avatar"], self.providers["uia-avatar"],
                                                self.nodes, self.providers, self.bindings)

    def test_raw_name_and_children_are_preserved_with_explicit_semantic_scope(self):
        before = deepcopy((self.nodes, self.providers, self.bindings))
        result = self.result()
        self.assertFalse(result["applicable"])
        self.assertEqual(result["quantity"], "independently exposed accessible name")
        self.assertEqual(result["raw_provider_name"], "Organization display name")
        self.assertEqual(result["row_provider_name"], "O Organization display name 11:00")
        self.assertEqual(result["xaml_path"], ["avatar", "content", "presenter", "row"])
        self.assertEqual((self.nodes, self.providers, self.bindings), before)
        self.assertEqual(self.providers["uia-initial"]["name"], "O")

    def test_actual_control_content_focus_or_action_exposure_is_not_suppressed(self):
        for property_name in ("is_control_element", "is_content_element", "focusable", "focused", "supported_patterns"):
            with self.subTest(property=property_name):
                self.setUp()
                provider = self.providers["uia-avatar"]
                if property_name in ("focusable", "focused"): provider["state"][property_name] = True
                elif property_name == "supported_patterns": provider[property_name] = ["InvokePatternIdentifiers.Pattern"]
                else: provider[property_name] = True
                self.assertIsNone(self.result())
        self.setUp(); self.providers["uia-avatar"]["state"].pop("focusable")
        self.assertIsNone(self.result())

    def test_chat_rows_chat_avatars_and_text_providers_are_out_of_scope(self):
        self.nodes["row"]["state_evidence"]["row_kind"] = "chat"
        self.assertIsNone(self.result())
        self.setUp(); self.nodes["avatar"]["parent"] = "conversation"
        self.assertIsNone(self.result())
        self.setUp(); self.nodes["avatar"]["type"] = "TextBlock"
        self.assertIsNone(self.result())

    def test_missing_lifetime_template_or_current_object_relationship_stays_reported(self):
        for broken in ("lifetime", "template", "current-content", "fake-row", "extra-presenter", "intermediate-button"):
            with self.subTest(broken=broken):
                self.setUp()
                binding = self.nodes["row"]["outline_owner_evidence"]["sidebar_row_content"]
                if broken == "lifetime": self.nodes["avatar"]["native_avatar_lookup"]["current_paint_and_template"] = False
                elif broken == "template": binding["template_present"] = False
                elif broken == "current-content": binding["content_id"] = "replaced-content"
                elif broken == "fake-row": binding["is_sealed"] = False
                elif broken == "extra-presenter": self.nodes["extra"] = {"id": "extra", "parent": "row", "type": "ContentPresenter"}
                else: self.nodes["content"]["type"] = "Button"
                self.assertIsNone(self.result())

    def test_exact_provider_identity_and_parent_relationship_are_required(self):
        for broken in ("missing-avatar", "missing-row", "ambiguous-avatar", "wrong-provider", "uia-parent"):
            with self.subTest(broken=broken):
                self.setUp()
                if broken == "missing-avatar": self.bindings["pairs"].pop(0)
                elif broken == "missing-row": self.bindings["pairs"].pop()
                elif broken == "ambiguous-avatar": self.bindings["pairs"].append(deepcopy(self.bindings["pairs"][0]))
                elif broken == "wrong-provider": self.bindings["pairs"][0]["uia_id"] = "nearby-avatar"
                else: self.providers["uia-avatar"]["parent"] = "another-row"
                self.assertIsNone(self.result())

    def test_parent_must_have_its_own_real_exposed_nonempty_name(self):
        for property_name, value in (("name", ""), ("name", None), ("is_control_element", False), ("is_content_element", False)):
            with self.subTest(property=property_name, value=value):
                self.setUp(); self.providers["uia-row"][property_name] = value
                self.assertIsNone(self.result())

    def test_unrelated_actual_names_are_retained_without_reference_name_matching(self):
        self.providers["uia-avatar"]["name"] = "A different provider display name"
        self.providers["uia-row"]["name"] = "The row's actual accessible label"
        result = self.result()
        self.assertEqual(result["raw_provider_name"], "A different provider display name")
        self.assertEqual(result["row_provider_name"], "The row's actual accessible label")


if __name__ == "__main__":
    unittest.main()
