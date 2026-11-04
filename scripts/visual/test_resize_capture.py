"""Pure resize capture fixtures; no browser, native app, input, server or process runs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call, patch

import capture


class ResizeCaptureTests(unittest.TestCase):
    def fixture(self, folder):
        page, cdp, locator, field, observer = [Mock() for _ in range(5)]
        page.locator.return_value = locator
        locator.count.return_value = 1
        locator.element_handle.return_value = field
        page.evaluate.return_value = {"status": "loaded", "count": 0}
        page.evaluate_handle.return_value = observer
        state = {"connected": True, "same_node": True, "tag": "TEXTAREA", "disabled": False,
            "resize": "both", "writing_mode": "horizontal-tb", "direction": "ltr",
            "bounds": {"x": 482, "y": 416.09375, "width": 476, "height": 76},
            "value": "", "text_content": "", "placeholder": "Actual fixture placeholder", "focused": False}
        field.evaluate.side_effect = lambda *args: copy.deepcopy(state)
        events = [{"type": "pointermove", "trusted": True, "x": 955, "y": 489.09375}]
        observer.evaluate.side_effect = lambda expression: copy.deepcopy(events) if expression == "capture => capture.events" else None
        def resize(**kwargs):
            state["bounds"].update(y=384.09375, height=140)
            events.append({"type": "pointerup", "trusted": True, "x": 955, "y": 553.09375})
        page.mouse.up.side_effect = resize
        cdp.send.return_value = {"actual": "source fixture"}
        action = capture.TextareaResizeCapture(page, cdp, "new-org-textarea-resized", Path(folder) / "action.json")
        return action, page, cdp, locator, state, events

    def test_real_mouse_recipe_records_owner_geometry_and_never_invents_grip_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, cdp, locator, state, events = self.fixture(folder)
            action.open(); action.checkpoint("after_screenshot"); action.close()
            self.assertEqual(page.mouse.mock_calls, [call.move(955, 489.09375), call.down(button="left"),
                call.move(955, 553.09375, steps=8), call.up(button="left")])
            self.assertEqual(action.evidence["geometry_delta"], {"x": 0, "y": -32, "width": 0, "height": 64})
            self.assertEqual(action.evidence["before"]["value"], action.evidence["after"]["value"])
            self.assertEqual(action.evidence["pointer_events"], events)
            self.assertIn("not measured", action.evidence["action"]["quantity"])
            for key in ("painted_presence", "bounds", "style", "state"):
                self.assertIsNone(action.evidence["resize_handle"][key])
            self.assertEqual(action.evidence["resize_handle"]["kind"], "resize-handle")
            self.assertEqual(cdp.send.call_args_list, [call("DOM.getDocument", {"depth": -1, "pierce": True}),
                call("Accessibility.getFullAXTree", {})] * 2)
            locator.fill.assert_not_called(); locator.evaluate.assert_not_called()
            self.assertEqual(json.loads(action.receipt_path.read_text()), action.evidence)

    def test_no_actual_height_change_fails_even_when_all_mouse_commands_succeed(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, *_ = self.fixture(folder)
            page.mouse.up.side_effect = None
            with self.assertRaisesRegex(RuntimeError, "did not increase"):
                action.open()
            action.close()
            self.assertEqual(action.evidence["geometry_delta"]["height"], 0)
            self.assertTrue(action.receipt_path.exists(), "Failure retains the real observed geometry")

    def test_text_change_is_not_accepted_as_a_resize(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, _, _, state, _ = self.fixture(folder)
            original = page.mouse.up.side_effect
            def mutate(**kwargs):
                original(**kwargs); state["value"] = "Unexpected edit"
            page.mouse.up.side_effect = mutate
            with self.assertRaisesRegex(RuntimeError, "changed text"):
                action.open()
            action.close()

    def test_actual_nonresizable_control_never_receives_drag_commands(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, _, _, state, _ = self.fixture(folder)
            state["resize"] = "none"
            with self.assertRaisesRegex(RuntimeError, "vertical resize"):
                action.open()
            action.close()
            self.assertEqual(page.mouse.mock_calls, [])

    def test_changed_state_during_capture_fails_and_preserves_the_changed_observation(self):
        for quantity in ("geometry", "text", "pointer"):
            with self.subTest(quantity=quantity), tempfile.TemporaryDirectory() as folder:
                action, _, _, _, state, events = self.fixture(folder)
                action.open()
                if quantity == "geometry": state["bounds"]["height"] += 1
                elif quantity == "text": state["placeholder"] = "Changed"
                else: events.append({"type": "pointermove", "trusted": True, "x": 500, "y": 500})
                with self.assertRaisesRegex(RuntimeError, "changed during capture"):
                    action.checkpoint("after_element_extraction")
                action.close()
                self.assertEqual(action.evidence["checkpoints"][-1]["stage"], "after_element_extraction")

    def test_drag_failure_releases_pressed_button_without_retrying_or_editing_size(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, *_ = self.fixture(folder)
            page.mouse.move.side_effect = [None, RuntimeError("actual input failure")]
            with self.assertRaisesRegex(RuntimeError, "actual input failure"):
                action.open()
            action.close()
            page.mouse.up.assert_called_once_with(button="left")
            self.assertEqual(page.mouse.move.call_count, 2)

    def test_ua_consumed_events_are_preserved_as_absent_not_synthesized(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, _, _, state, events = self.fixture(folder)
            events.clear()
            page.mouse.up.side_effect = lambda **kwargs: state["bounds"].update(height=140)
            action.open(); action.close()
            self.assertEqual(action.evidence["pointer_events"], [])
            self.assertEqual(action.evidence["event_delivery"]["observed_types"], [])
            self.assertIsNone(action.evidence["resize_handle"]["state"])

    def test_capture_keeps_same_resized_state_across_png_dom_and_element_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            page, cdp, browser, action = Mock(), Mock(), Mock(), Mock()
            browser.version = "fixture-browser"
            cdp.send.return_value = {"actual": "DOM or AX fixture"}
            page.evaluate.side_effect = [{"navigator_platform": "fixture"}, {"elements": []}]
            action.evidence = {"source": "actual resize fixture", "errors": []}
            case = {"id": "fixture-resize", "scene": "new-org-textarea-resized", "file": "fixture-resize.png"}
            manifest = {"output": folder, "fixture": {}, "lang": "en-US", "theme": "light"}
            with patch.object(capture, "TextareaResizeCapture", return_value=action), \
                    patch.object(capture, "input_text_evidence", return_value={"inputs": {}, "errors": []}), \
                    patch.object(capture, "font_evidence", return_value={"actual": "font fixture"}):
                capture.capture_reference_evidence(page, cdp, browser, manifest, case)
            action.open.assert_called_once_with()
            self.assertEqual([entry.args[0] for entry in action.checkpoint.call_args_list],
                ["before_screenshot", "after_screenshot", "after_dom_snapshot", "after_source_evidence", "after_element_extraction"])
            page.screenshot.assert_called_once_with(path=Path(folder) / "fixture-resize.png", animations="allow", caret="initial")
            action.close.assert_called_once_with(); cdp.detach.assert_called_once_with(); page.close.assert_called_once_with()
            actual = json.loads((Path(folder) / "fixture-resize.elements.json").read_text())
            self.assertEqual(actual["capture_evidence"]["textarea_resize_action"], action.evidence)


if __name__ == "__main__":
    unittest.main()
