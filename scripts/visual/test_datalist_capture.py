"""Pure capture fixtures. No browser, server, subprocess or native window starts."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from capture import DATALIST_SCENES, LIVE_SCENES, MEMBER_CARD_SCENES, MESSAGE_SCENES, open_datalist_scene, record_datalist_coverage


class DatalistCaptureTests(unittest.TestCase):
    def input_record(self, focused=False):
        return {"tag": "INPUT", "list": "relic-claude-models", "value": "", "focused": focused,
                "disabled": False, "bounds": {"x": 482, "y": 300, "width": 200, "height": 32},
                "source_options": [{"value": "sonnet", "label": "sonnet", "text": "", "disabled": False}]}

    def test_action_uses_real_input_focus_and_down_without_creating_markup(self):
        page, cdp = Mock(), Mock()
        field = page.locator.return_value
        field.evaluate.side_effect = [self.input_record(), self.input_record(True)]
        cdp.send.return_value = {"nodes": [{"nodeId": "ax-1", "role": {"value": "combobox"}}]}
        result = open_datalist_scene(page, cdp, "member-host-model-suggestions")
        page.locator.assert_called_once_with("#layer input[list='relic-claude-models']")
        field.focus.assert_called_once_with()
        page.keyboard.press.assert_called_once_with("ArrowDown")
        page.evaluate.assert_not_called()
        self.assertEqual(result["after_input"]["source_options"][0]["value"], "sonnet")
        self.assertIsNone(result["popup_painted_presence"])
        self.assertIsNone(result["popup_painted_bounds"])
        self.assertIsNone(result["popup_painted_elements"])
        self.assertIsNone(result["screenshot_includes_browser_popup"])
        self.assertEqual(result["before_ax"], cdp.send.return_value)
        self.assertEqual(result["after_ax"], cdp.send.return_value)
        self.assertEqual(result["after_dom"], cdp.send.return_value)

    def test_empty_source_suggestions_cannot_silently_capture_closed_input(self):
        page, cdp = Mock(), Mock()
        source = self.input_record(); source["source_options"] = []
        page.locator.return_value.evaluate.return_value = source
        with self.assertRaisesRegex(RuntimeError, "real source suggestions"):
            open_datalist_scene(page, cdp, "member-host-model-suggestions")
        page.keyboard.press.assert_not_called()

    def test_failed_cdp_export_retains_error_and_unknown_popup_geometry(self):
        page, cdp = Mock(), Mock()
        page.locator.return_value.evaluate.side_effect = [self.input_record(), self.input_record(True)]
        cdp.send.side_effect = RuntimeError("browser UI not in page target")
        result = open_datalist_scene(page, cdp, "member-existing-seat-suggestions")
        self.assertEqual(len(result["errors"]), 5)
        self.assertIsNone(result["after_ax"])
        self.assertIsNone(result["popup_painted_elements"])

    def test_source_options_never_become_canonical_visible_elements(self):
        elements = {"elements": [{"id": "input-1", "kind": "input", "state": {"focused": True}}],
                    "coverage": {"raw_nodes": 1, "emitted_elements": 1, "unmeasured": []}}
        original = copy.deepcopy(elements["elements"])
        evidence = {"after_input": self.input_record(True), "popup_painted_elements": None}
        record_datalist_coverage(elements, evidence)
        self.assertEqual(elements["elements"], original)
        self.assertEqual(elements["coverage"]["emitted_elements"], 1)
        self.assertEqual({gap["property"] for gap in elements["coverage"]["unmeasured"]}, {
            "browser_popup.painted_presence", "browser_popup.painted_elements", "browser_popup.screenshot_coverage"})
        self.assertTrue(all(gap["element"] == "input-1" for gap in elements["coverage"]["unmeasured"]))
        self.assertIs(elements["capture_evidence"]["datalist_popup"], evidence)

    def test_two_suggestion_states_extend_all_original_scenes(self):
        original = {
            "group", "private", "thread", "overview", "workspace", "file-markdown", "file-code", "file-image",
            "copies", "copy-rules", "chart", "new-org", "member-app", "member-host", "member-existing",
            "member-card", "member-edit", "forward", "secretary", "tasks", "task-report", "protocols", "documents", "trajectory",
            "settings-profile", "settings-appearance", "settings-language", "settings-voice", "settings-notify", "settings-harness", "settings-about",
            "shortcuts", "recipients", "quote", "mention", "digest", "plain", "quick-start", "menu-file", "menu-edit", "menu-view", "menu-help",
        }
        spec = json.loads((Path(__file__).parent / "scenes.json").read_text(encoding="utf-8"))
        self.assertEqual(len(original), 42)
        original_47 = original | set(DATALIST_SCENES) | LIVE_SCENES
        self.assertEqual(len(original_47), 47)
        self.assertEqual(set(MEMBER_CARD_SCENES), {"member-card-rename", "member-card-model", "member-card-avatar-hover"})
        self.assertEqual(set(MESSAGE_SCENES), {"message-hover", "message-copy-toast"})
        self.assertEqual(set(spec["scenes"]), original_47 | set(MEMBER_CARD_SCENES) | MESSAGE_SCENES)
        self.assertEqual(len(spec["scenes"]), 52)


if __name__ == "__main__":
    unittest.main()
