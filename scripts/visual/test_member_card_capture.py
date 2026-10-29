"""Pure capture action fixtures: no page, app, server or subprocess runs."""
import copy
import unittest
from unittest.mock import Mock

from capture import MEMBER_CARD_SCENES, open_member_card_scene


class MemberCardCaptureTests(unittest.TestCase):
    def page(self, scene):
        page = Mock()
        card = page.locator.return_value
        card.count.return_value = 1
        control = card.locator.return_value
        control.count.return_value = 1
        control.evaluate.return_value = {"tag": "DIV" if scene.endswith("hover") else "BUTTON",
                                         "text": "Actual control label", "title": "Actual title", "disabled": False,
                                         "bounds": {"x": 14, "y": 26, "width": 24, "height": 24}}
        before = {"member_text": "secretary", "rename": None, "model": None,
                  "avatar": {"hovered": False, "overlay": {"text": "Actual change label", "opacity": "0"}}}
        after = copy.deepcopy(before)
        if scene == "member-card-rename":
            after["rename"] = {"focused": True, "value": "Actual current name", "placeholder": "Actual placeholder"}
        elif scene == "member-card-model":
            after["model"] = {"selects": [{"value": "actual-model"}, {"value": "actual-effort"}], "save_text": "Actual save label"}
        else:
            after["avatar"]["hovered"] = True
            after["avatar"]["overlay"]["opacity"] = "1"
        card.evaluate.side_effect = [before, after]
        return page, card, control, before, after

    def test_rename_uses_real_button_click_and_retains_actual_input_readback(self):
        scene = "member-card-rename"
        page, card, control, before, after = self.page(scene)
        receipt = open_member_card_scene(page, scene)
        page.locator.assert_called_once_with(".card[role='dialog']")
        card.locator.assert_any_call(MEMBER_CARD_SCENES[scene])
        card.locator.assert_any_call(".rename input")
        control.click.assert_called_once_with()
        control.hover.assert_not_called()
        page.wait_for_function.assert_called_once_with(
            "selector => document.querySelector(selector)===document.activeElement",
            arg=".card[role='dialog'] .rename input")
        self.assertIs(receipt["before"], before)
        self.assertIs(receipt["after"], after)
        self.assertEqual(receipt["control"]["text"], "Actual control label")
        self.assertEqual(receipt["navigation_scene"], "member-card")
        page.evaluate.assert_not_called()
        control.fill.assert_not_called()

    def test_model_uses_change_button_and_keeps_both_real_selected_values(self):
        scene = "member-card-model"
        page, card, control, before, after = self.page(scene)
        receipt = open_member_card_scene(page, scene)
        card.locator.assert_any_call(".kv dd > div > button.btn.sm.ghost")
        card.locator.assert_any_call(".model-edit")
        control.click.assert_called_once_with()
        self.assertEqual(receipt["after"]["model"]["selects"], [{"value": "actual-model"}, {"value": "actual-effort"}])
        control.select_option.assert_not_called()
        page.evaluate.assert_not_called()

    def test_hover_uses_pointer_action_without_opening_file_picker(self):
        scene = "member-card-avatar-hover"
        page, card, control, before, after = self.page(scene)
        receipt = open_member_card_scene(page, scene)
        control.hover.assert_called_once_with()
        control.click.assert_not_called()
        self.assertEqual(page.wait_for_function.call_args.kwargs["arg"], ".card[role='dialog'] .avatar-wrap")
        self.assertTrue(receipt["after"]["avatar"]["hovered"])
        self.assertEqual(receipt["after"]["avatar"]["overlay"]["opacity"], "1")
        self.assertEqual(receipt["before"]["avatar"]["overlay"]["opacity"], "0")
        page.evaluate.assert_not_called()

    def test_ambiguous_member_card_or_control_fails_instead_of_selecting_arbitrary_one(self):
        for ambiguous in ("card", "control"):
            with self.subTest(ambiguous=ambiguous):
                page, card, control, before, after = self.page("member-card-rename")
                (card if ambiguous == "card" else control).count.return_value = 2
                with self.assertRaisesRegex(RuntimeError, "Expected one production"):
                    open_member_card_scene(page, "member-card-rename")
                control.click.assert_not_called()
                control.hover.assert_not_called()

    def test_disabled_button_cannot_be_reported_as_a_successful_action(self):
        page, card, control, before, after = self.page("member-card-model")
        control.evaluate.return_value["disabled"] = True
        with self.assertRaisesRegex(RuntimeError, "control is disabled"):
            open_member_card_scene(page, "member-card-model")
        control.click.assert_not_called()

    def test_closed_or_unfocused_state_fails_after_the_real_action(self):
        for scene, message in (("member-card-rename", "receive focus"),
                               ("member-card-model", "both model and effort"),
                               ("member-card-avatar-hover", "hover overlay")):
            with self.subTest(scene=scene):
                page, card, control, before, after = self.page(scene)
                card.evaluate.side_effect = [before, copy.deepcopy(before)]
                with self.assertRaisesRegex(RuntimeError, message):
                    open_member_card_scene(page, scene)

    def test_model_requires_both_controls_and_hover_requires_finished_real_transition(self):
        page, card, control, before, after = self.page("member-card-model")
        after["model"]["selects"].pop()
        with self.assertRaisesRegex(RuntimeError, "both model and effort"):
            open_member_card_scene(page, "member-card-model")
        page, card, control, before, after = self.page("member-card-avatar-hover")
        after["avatar"]["overlay"]["opacity"] = "0.99"
        with self.assertRaisesRegex(RuntimeError, "hover overlay"):
            open_member_card_scene(page, "member-card-avatar-hover")


if __name__ == "__main__":
    unittest.main()
