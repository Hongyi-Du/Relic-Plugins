"""Pure activation-receipt checks; no browser or native process is launched."""
from copy import deepcopy
import unittest

from recipients_capture import validate_activation


class RecipientActivationTests(unittest.TestCase):
    def receipt(self):
        return {"same_button": True, "connected": True, "disabled": False,
                "visible_menu_count": 1, "menu_items": 6,
                "clicks": [{"trusted": True, "same_current_target": True, "x": 40, "y": 80}]}

    def test_actual_single_button_click_preserves_original_measurements(self):
        receipt = self.receipt()
        before = deepcopy(receipt)
        self.assertIs(receipt, validate_activation(receipt))
        self.assertEqual(before, receipt)

    def test_synthetic_click_or_foreign_button_cannot_open_an_accepted_scene(self):
        for field in ("trusted", "same_current_target"):
            with self.subTest(field=field):
                receipt = self.receipt()
                receipt["clicks"][0][field] = False
                with self.assertRaises(RuntimeError):
                    validate_activation(receipt)

    def test_missing_duplicate_or_unmounted_state_remains_failure(self):
        for field, bad in (("same_button", False), ("connected", False), ("disabled", True),
                           ("visible_menu_count", 0), ("visible_menu_count", 2), ("menu_items", 0),
                           ("clicks", []), ("clicks", self.receipt()["clicks"] * 2)):
            with self.subTest(field=field, bad=bad):
                receipt = self.receipt()
                receipt[field] = bad
                with self.assertRaises(RuntimeError):
                    validate_activation(receipt)


if __name__ == "__main__":
    unittest.main()
