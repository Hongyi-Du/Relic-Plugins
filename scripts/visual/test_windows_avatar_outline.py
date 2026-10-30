"""Synthetic subclass contracts; actual child paint remains independent."""
import unittest

from test_windows_outline import person_picture
from windows_outline import LOCAL_AVATAR_RUNTIME, LOCAL_AVATAR_CONTRACT, LOCAL_AVATAR_SOURCE, native_outline


def retained_picture():
    owner, child = person_picture()
    owner["type"] = "NativeAvatarPicture"
    owner["outline_owner_evidence"].update(runtime_type=LOCAL_AVATAR_RUNTIME, own_paint_contract=LOCAL_AVATAR_CONTRACT)
    owner["outline_owner_evidence"]["person_picture_template"].update(
        source=LOCAL_AVATAR_SOURCE, base_type="Microsoft.UI.Xaml.Controls.PersonPicture", is_sealed=True,
        audited_local_source="native/windows/Relic/NativeAvatarParts.cs#NativeAvatarPicture", current_paint_same_object=True)
    return owner, {owner["id"]: owner, child["id"]: child}


class RetainedAvatarOutlineTests(unittest.TestCase):
    def test_sealed_retained_template_has_only_container_proof(self):
        owner, nodes = retained_picture()
        value, evidence, errors = native_outline(owner, nodes)
        self.assertEqual("none", value)
        self.assertEqual([], errors)
        self.assertIn("container only", evidence["scope"])
        self.assertIn("independent obligations", evidence["scope"])

    def test_changed_type_template_source_or_retained_parts_cannot_inherit_proof(self):
        for field, bad in (("source", "unknown"), ("is_sealed", False),
                           ("base_type", "Microsoft.UI.Xaml.Controls.Control"),
                           ("audited_local_source", None), ("current_paint_same_object", False),
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

    def test_old_native_picture_remains_a_separate_contract(self):
        owner, child = person_picture()
        self.assertEqual("none", native_outline(owner, {owner["id"]: owner, child["id"]: child})[0])
        owner["type"] = "NativeAvatarPicture"
        self.assertIsNone(native_outline(owner, {owner["id"]: owner, child["id"]: child})[0])


if __name__ == "__main__":
    unittest.main()
