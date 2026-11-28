"""Pure actual-contract validation fixtures; CI only, no native launch."""
from copy import deepcopy
import unittest

from test_windows_outline import primitive
from windows_outline import TOGGLE_RUNTIME, TOGGLE_CONTRACT, TOGGLE_SOURCE, native_outline


def controlled_toggle():
    owner = primitive("toggle", "ToggleButton")
    owner["type"] = "NativeOverviewToggle"
    owner["render_type_evidence"] = {"is_control": True, "control_template_present": True}
    owner["outline_owner_evidence"].update(runtime_type=TOGGLE_RUNTIME, own_paint_contract=TOGGLE_CONTRACT,
        local_toggle={"source": TOGGLE_SOURCE, "owner_id": "toggle", "is_sealed": True,
                      "base_type": "Microsoft.UI.Xaml.Controls.Primitives.ToggleButton",
                      "audited_source": "native/windows/Relic/NativeOverviewToggle.cs#NativeOverviewToggle",
                      "current_parts_same_objects": True, "template_present": True,
                      "template_type": "Microsoft.UI.Xaml.Controls.ControlTemplate"})
    child = primitive("presenter", "ContentPresenter", "toggle")
    owner["outline_owner_evidence"]["children"]["items"] = [{"id": "presenter", "index": 0, "same_parent_object": True}]
    return owner, {"toggle": owner, "presenter": child}


class ToggleOutlineTests(unittest.TestCase):
    def test_exact_container_does_not_claim_child_paint(self):
        owner, nodes = controlled_toggle()
        nodes["presenter"]["outline_owner_evidence"] = None
        value, evidence, issues = native_outline(owner, nodes)
        self.assertEqual("none", value)
        self.assertEqual([], issues)
        self.assertIn("own container only", evidence["scope"])
        self.assertIsNone(native_outline(nodes["presenter"], nodes)[0])

    def test_missing_or_changed_contract_never_inherits_base_type_absence(self):
        for key, bad in (("source", "guessed"), ("owner_id", "another"), ("is_sealed", False),
                         ("base_type", "Microsoft.UI.Xaml.Controls.Control"), ("audited_source", "another.cs"),
                         ("current_parts_same_objects", False), ("template_present", False),
                         ("template_type", None)):
            for remove in (False, True):
                with self.subTest(key=key, remove=remove):
                    owner, nodes = controlled_toggle()
                    if remove:
                        owner["outline_owner_evidence"]["local_toggle"].pop(key)
                    else:
                        owner["outline_owner_evidence"]["local_toggle"][key] = bad
                    self.assertIsNone(native_outline(owner, nodes)[0])

    def test_focus_composition_and_tree_failures_survive(self):
        for failure in ("focus", "composition", "tree", "runtime", "type"):
            with self.subTest(failure=failure):
                owner, nodes = controlled_toggle()
                if failure == "focus":
                    owner["outline_owner_evidence"]["focus"]["state"] = "Keyboard"
                elif failure == "composition":
                    owner["outline_owner_evidence"]["composition"]["child_visual_present"] = True
                elif failure == "tree":
                    nodes["presenter"]["parent"] = None
                elif failure == "runtime":
                    owner["outline_owner_evidence"]["runtime_type"] = "Relic.OtherToggle"
                else:
                    owner["render_type_evidence"]["control_template_present"] = False
                self.assertIsNone(native_outline(owner, nodes)[0])

    def test_unknown_old_receipt_cannot_acquire_current_contract(self):
        owner, nodes = controlled_toggle()
        before = deepcopy(owner)
        owner["outline_owner_evidence"].pop("local_toggle")
        self.assertIsNone(native_outline(owner, nodes)[0])
        self.assertNotEqual(before, owner)


if __name__ == "__main__":
    unittest.main()
