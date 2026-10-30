"""Pure hover/copy capture fixtures. No browser, clipboard, process or HTTP runs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import capture


class MessageCaptureTests(unittest.TestCase):
    def setup_capture(self, folder, scene="message-copy-toast"):
        page, cdp, row, toolbar, button, notice, message, toast, observer = [Mock() for _ in range(9)]
        row.count.return_value = toolbar.count.return_value = button.count.return_value = notice.count.return_value = 1
        row.locator.return_value = toolbar
        toolbar.get_by_title.return_value = button
        row.element_handle.return_value = message
        notice.element_handle.return_value = toast
        absent_notice = Mock(); absent_notice.count.return_value = 0
        page.locator.side_effect = lambda selector: row if selector == '.msg[data-id="17"]' else absent_notice if selector == ".toast" else notice
        page.evaluate_handle.return_value = observer
        pointer = [{"type": "pointermove", "trusted": True, "x": 700, "y": 450,
                    "target": {"message_id": "17"}, "timestamp": 42}]
        if scene == "message-copy-toast":
            pointer.append({"type": "click", "trusted": True, "x": 700, "y": 450,
                            "target": {"message_id": "17"}, "timestamp": 43})
        observer.evaluate.side_effect = lambda expression: copy.deepcopy(pointer) if expression == "capture => capture.events" else None
        message_state = {"connected": True, "same_node": True, "id": "17", "hovered": True,
            "bounds": {"x": 300, "y": 430, "width": 740, "height": 100}, "text": "Real rendered message and actions",
            "toolbar": {"display": "flex", "visibility": "visible", "opacity": "1", "buttons": [{"title": "Copy from API"}],
                        "bounds": {"x": 600, "y": 418, "width": 200, "height": 30}}}
        toast_state = {"connected": True, "same_node": True, "text": "Copied from API", "role": "status",
            "display": "block", "visibility": "visible", "opacity": "1",
            "bounds": {"x": 670, "y": 832, "width": 100, "height": 40}, "background": "rgb(1, 2, 3)", "color": "rgb(250, 251, 252)"}
        message.evaluate.side_effect = lambda *args: copy.deepcopy(message_state)
        toast.evaluate.side_effect = lambda expression: "Copied from API" if expression == "el => el.textContent" else copy.deepcopy(toast_state)
        clock = {"date_now": 1793271720000, "performance_now": 1700, "time_origin": 1793271718300}
        body = "**Actual API Markdown**\n\nNot rendered innerText"
        clipboard = ["Previous clipboard", body]
        def evaluate(expression):
            if "await document.fonts.ready" in expression:
                return {"status": "loaded", "count": 2}
            if expression == capture.MessageSceneCapture.READ_CLOCK:
                return dict(clock)
            if expression == "() => navigator.clipboard.readText()":
                return clipboard.pop(0) if len(clipboard) > 1 else clipboard[0]
            raise AssertionError("Unexpected evaluated page program: " + expression)
        page.evaluate.side_effect = evaluate
        cdp.send.return_value = {"virtualTimeTicksBase": 1500.25}
        fixture = {"thread": "17", "org": "fixture-org", "port": 7777, "token": "fixture-token"}
        action = capture.MessageSceneCapture(page, cdp, scene, fixture, "en-US", Path(folder) / "action.json")
        api = [{"lang": "en-US", "strings": {"common.copy": "Copy from API", "msg.copied": "Copied from API"}},
               {"items": [{"id": 17, "body": body}]}]
        return action, api, page, cdp, row, button, message_state, toast_state, pointer, clock, clipboard

    def test_hover_uses_real_pointer_and_keeps_actual_toolbar_without_clipboard_or_clock_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            action, api, page, cdp, row, button, *_ = self.setup_capture(folder, "message-hover")
            with patch.object(capture, "read_fixture_json", side_effect=api):
                action.open()
                action.checkpoint("after_screenshot")
                action.close()
            row.hover.assert_called_once_with()
            button.click.assert_not_called()
            cdp.send.assert_not_called()
            page.context.grant_permissions.assert_not_called()
            page.mouse.move.assert_not_called()
            self.assertEqual([row["stage"] for row in action.evidence["checkpoints"]], ["after_action", "after_screenshot"])
            self.assertTrue(action.evidence["checkpoints"][0]["state"]["message"]["hovered"])

    def test_copy_click_reads_actual_clipboard_and_pauses_then_resumes_original_timer_timeline(self):
        with tempfile.TemporaryDirectory() as folder:
            action, api, page, cdp, row, button, *_ = self.setup_capture(folder)
            with patch.object(capture, "read_fixture_json", side_effect=api) as read:
                action.open()
                action.checkpoint("after_element_extraction")
                action.close()
            self.assertEqual(read.call_args_list[1].args[1], "/api/org/fixture-org/chat?kind=group&limit=1000")
            row.hover.assert_called_once_with(); button.click.assert_called_once_with()
            row.locator.return_value.get_by_title.assert_called_once_with("Copy from API", exact=True)
            page.context.grant_permissions.assert_called_once_with(["clipboard-read", "clipboard-write"], origin="http://127.0.0.1:7777")
            self.assertEqual(cdp.send.call_args_list[0].args, ("Emulation.setVirtualTimePolicy", {"policy": "pause"}))
            self.assertEqual(cdp.send.call_args_list[1].args, ("Emulation.setVirtualTimePolicy", {"policy": "advance"}))
            self.assertEqual(action.evidence["clipboard_before"], "Previous clipboard")
            self.assertEqual(action.evidence["clipboard_after"], api[1]["items"][0]["body"])
            self.assertEqual(action.evidence["clock_pause"]["receipt"], {"virtualTimeTicksBase": 1500.25})
            self.assertIsNone(action.evidence["toast_remaining_ms"])
            self.assertEqual(json.loads(action.receipt_path.read_text()), action.evidence)
            page.context.clear_permissions.assert_called_once_with()

    def test_lost_hover_changed_pointer_expired_toast_or_changed_clock_fails(self):
        mutations = [
            lambda message, toast, pointer, clock: message.update(hovered=False),
            lambda message, toast, pointer, clock: pointer[0].update(x=701),
            lambda message, toast, pointer, clock: toast.update(connected=False),
            lambda message, toast, pointer, clock: toast.update(same_node=False),
            lambda message, toast, pointer, clock: toast["bounds"].update(width=101),
            lambda message, toast, pointer, clock: clock.update(performance_now=1701),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as folder:
                action, api, _, _, _, _, message, toast, pointer, clock, _ = self.setup_capture(folder)
                with patch.object(capture, "read_fixture_json", side_effect=api):
                    action.open()
                    mutate(message, toast, pointer, clock)
                    with self.assertRaises(RuntimeError):
                        action.checkpoint("after_source_evidence")
                    action.close()
                self.assertEqual(action.evidence["checkpoints"][-1]["stage"], "after_source_evidence", "Retain the failing actual observation")

    def test_wrong_clipboard_or_missing_real_virtual_clock_receipt_fails_and_cleanup_resumes(self):
        for problem in ("clipboard", "clock"):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as folder:
                action, api, _, cdp, _, button, _, _, _, _, clipboard = self.setup_capture(folder)
                if problem == "clipboard":
                    clipboard[1] = "Unrelated clipboard"
                else:
                    cdp.send.return_value = {}
                with patch.object(capture, "read_fixture_json", side_effect=api):
                    with self.assertRaises(RuntimeError):
                        action.open()
                    action.close()
                button.click.assert_called_once_with()
                self.assertEqual(cdp.send.call_args_list[-1].args, ("Emulation.setVirtualTimePolicy", {"policy": "advance"}))

    def test_untrusted_or_different_message_click_is_not_a_copy_action_witness(self):
        for change in ("untrusted", "other-message"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                action, api, _, _, _, _, _, _, pointer, _, _ = self.setup_capture(folder)
                if change == "untrusted":
                    pointer[-1]["trusted"] = False
                else:
                    pointer[-1]["target"]["message_id"] = "999"
                with patch.object(capture, "read_fixture_json", side_effect=api):
                    with self.assertRaisesRegex(RuntimeError, "trusted production Copy"):
                        action.open()
                    action.close()

    def test_capture_checks_same_state_across_png_source_collection_and_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            page, cdp, browser, action = Mock(), Mock(), Mock(), Mock()
            browser.version = "fixture-browser"
            cdp.send.return_value = {"actual": "DOM or AX fixture"}
            page.evaluate.side_effect = [{"navigator_platform": "fixture"}, {"elements": []}]
            action.evidence = {"source": "actual action fixture", "errors": []}
            case = {"id": "fixture-copy", "scene": "message-copy-toast", "file": "fixture-copy.png"}
            manifest = {"output": folder, "fixture": {}, "lang": "en-US", "theme": "light"}
            with patch.object(capture, "MessageSceneCapture", return_value=action), \
                    patch.object(capture, "input_text_evidence", return_value={"inputs": {}, "errors": []}), \
                    patch.object(capture, "font_evidence", return_value={"actual": "font fixture"}):
                capture.capture_reference_evidence(page, cdp, browser, manifest, case)
            action.open.assert_called_once_with()
            self.assertEqual([call.args[0] for call in action.checkpoint.call_args_list],
                ["before_screenshot", "after_screenshot", "after_dom_snapshot", "after_source_evidence", "after_element_extraction"])
            page.screenshot.assert_called_once_with(path=Path(folder) / "fixture-copy.png", animations="allow")
            action.close.assert_called_once_with(); page.close.assert_called_once_with(); cdp.detach.assert_called_once_with()
            actual = json.loads((Path(folder) / "fixture-copy.elements.json").read_text())
            self.assertEqual(actual["capture_evidence"]["message_action"], action.evidence)

    def test_failed_screenshot_keeps_failure_receipt_and_closes_observer_page_and_clock_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            page, cdp, browser, action = Mock(), Mock(), Mock(), Mock()
            page.screenshot.side_effect = RuntimeError("actual screenshot failed")
            action.evidence = {"errors": []}
            case = {"id": "fixture-copy", "scene": "message-copy-toast", "file": "fixture-copy.png"}
            manifest = {"output": folder, "fixture": {}, "lang": "en-US", "theme": "light"}
            with patch.object(capture, "MessageSceneCapture", return_value=action):
                with self.assertRaisesRegex(RuntimeError, "actual screenshot failed"):
                    capture.capture_reference_evidence(page, cdp, browser, manifest, case)
            self.assertEqual(action.evidence["errors"], ["actual screenshot failed"])
            action.save.assert_called_once_with(); action.close.assert_called_once_with()
            cdp.detach.assert_called_once_with(); page.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
