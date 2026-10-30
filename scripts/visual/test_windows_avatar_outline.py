"""Exact native PersonPicture only; a retained composition is not a UI type."""
import unittest

from test_windows_outline import person_picture
from windows_outline import native_outline


def retained_picture():
    owner, child = person_picture()
    return owner, {owner["id"]: owner, child["id"]: child}


class RetainedAvatarOutlineTests(unittest.TestCase):
    def test_exact_native_template_has_only_container_proof(self):
        owner, nodes = retained_picture()
        value, evidence, errors = native_outline(owner, nodes)
        self.assertEqual("none", value)
        self.assertEqual([], errors)
        self.assertIn("container only", evidence["scope"])
        self.assertIn("independent obligations", evidence["scope"])

    def test_changed_type_template_source_cannot_inherit_proof(self):
        for field, bad in (("source", "unknown"), ("is_sealed", True),
                           ("base_type", "Microsoft.UI.Xaml.Controls.PersonPicture"),
                           ("template_present", False), ("visual_child_count", 0)):
            with self.subTest(field=field):
                owner, nodes = retained_picture()
                owner["outline_owner_evidence"]["person_picture_template"][field] = bad
                self.assertIsNone(native_outline(owner, nodes)[0])

    def test_focus_and_hand_in_visuals_stay_unknown(self):
        for field in ("focus", "composition", "children"):
            with self.subTest(field=field):
                owner, nodes = retained_picture()
                owner["outline_owner_evidence"][field] = None
                self.assertIsNone(native_outline(owner, nodes)[0])

    def test_retired_ui_subclass_never_inherits_native_contract(self):
        owner, child = person_picture()
        self.assertEqual("none", native_outline(owner, {owner["id"]: owner, child["id"]: child})[0])
        owner["type"] = "NativeAvatarPicture"
        self.assertIsNone(native_outline(owner, {owner["id"]: owner, child["id"]: child})[0])
        owner["outline_owner_evidence"].update(runtime_type="Relic.NativeAvatarPicture",
                                             own_paint_contract="relic-native-avatar-personpicture-template-only")
        self.assertIsNone(native_outline(owner, {owner["id"]: owner, child["id"]: child})[0])


if __name__ == "__main__":
    unittest.main()
