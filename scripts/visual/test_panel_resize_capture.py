"""Pure panel capture fixtures; no browser, window, process or real input starts."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call, patch

import capture


class PanelResizeCaptureTests(unittest.TestCase):
    def fixture(self, folder, scene="panel-resized", width=1440, hidden=False):
        page, cdp, locator, opener, observer = [Mock() for _ in range(5)]
        page.locator.side_effect = lambda selector: opener if selector == capture.PanelResizeCapture.OPEN_SELECTOR else locator
        locator.count.return_value = 1
        locator.is_visible.return_value = not hidden
        opener.count.return_value = 1
        opener.evaluate.return_value = {"tag": "button", "title": "Actual Overview title", "selected": False, "disabled": False}
        if hidden:
            opener.evaluate.side_effect = [{"tag": "button", "title": "Actual Overview title", "selected": False, "disabled": False},
                {"tag": "button", "title": "Actual Overview title", "selected": True, "disabled": False}]
        page.evaluate.return_value = {"status": "loaded", "count": 2}
        page.evaluate_handle.return_value = observer
        state = {"connected": True, "same_handle": True, "same_panel": True, "parent_matches": True,
            "handle": {"bounds": {"x": width - 340, "y": 36, "width": 5, "height": 864},
                "title": "Actual panel resize title", "pointer_handler_property_type": "object", "hovered": False,
                "active": False, "focused": False, "style": {"cursor": "col-resize", "background": "rgba(0, 0, 0, 0)"}},
            "panel": {"bounds": {"x": width - 340, "y": 36, "width": 340, "height": 864},
                "display": "block", "visibility": "visible", "pane": "org", "computed_panel_width": "340px"},
            "body_resizing": False, "viewport": {"width": width, "height": 900}, "pointer_events": []}
        observer.evaluate.side_effect = lambda expression: copy.deepcopy(state) if expression == capture.PanelResizeCapture.READ_STATE else None
        position = {"x": 0, "y": 0}

        def event(kind, buttons):
            state["pointer_events"].append({"type": kind, "trusted": True, **position, "buttons": buttons,
                "target_is_handle": True, "body_resizing": state["body_resizing"]})

        def move(x, y, **kwargs):
            position.update(x=x, y=y)
            state["handle"]["hovered"] = True
            state["handle"]["style"]["background"] = "rgba(131, 107, 69, 0.4)"
            if state["body_resizing"]:
                state["panel"]["bounds"].update(x=width - 404, width=404)
                state["handle"]["bounds"]["x"] = width - 404
                state["panel"]["computed_panel_width"] = "404px"
            event("pointermove", 1 if state["body_resizing"] else 0)

        def down(**kwargs):
            event("pointerdown", 1)
            state["body_resizing"] = True
            state["handle"]["active"] = True

        def up(**kwargs):
            event("pointerup", 0)
            state["body_resizing"] = False
            state["handle"]["active"] = False

        page.mouse.move.side_effect = move
        page.mouse.down.side_effect = down
        page.mouse.up.side_effect = up
        def cdp_request(method, parameters):
            if method == "Runtime.evaluate": return {"result": {"type": "object", "subtype": "node", "objectId": "actual-handle"}}
            if method == "DOM.describeNode": return {"node": {"nodeType": 1, "nodeName": "DIV", "backendNodeId": 902}}
            if method == "DOMDebugger.getEventListeners": return {"listeners": [{"type": "pointerdown", "backendNodeId": 902, "useCapture": False, "scriptId": "actual-script", "lineNumber": 1452}]}
            return {}
        cdp.send.side_effect = cdp_request
        action = capture.PanelResizeCapture(page, cdp, scene, Path(folder) / "panel.scene-action.json")
        return action, page, observer, opener, state

    def test_drag_uses_real_handle_and_keeps_actual_paint_geometry_and_pointer_receipts(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, observer, opener, state = self.fixture(folder)
            action.open(); action.checkpoint("after_screenshot"); action.checkpoint("after_element_extraction"); action.close()
            self.assertEqual(page.mouse.mock_calls, [call.move(1102.5, 468), call.down(button="left"),
                call.move(1038.5, 468, steps=8), call.up(button="left")])
            self.assertEqual(action.evidence["geometry_delta"], {"panel": {"x": -64, "y": 0, "width": 64, "height": 0},
                "handle": {"x": -64, "y": 0, "width": 0, "height": 0}})
            self.assertTrue(action.evidence["after_pointer_down"]["body_resizing"])
            self.assertFalse(action.evidence["after"]["body_resizing"])
            self.assertTrue(action.evidence["after"]["handle"]["hovered"])
            self.assertEqual(action.evidence["after"]["pointer_events"], state["pointer_events"])
            self.assertEqual(json.loads(action.receipt_path.read_text(encoding="utf-8")), action.evidence)
            opener.click.assert_not_called(); observer.dispose.assert_called_once_with()

    def test_hover_has_no_press_and_preserves_exact_panel_geometry(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, *_ = self.fixture(folder, "panel-resize-hover")
            action.open(); action.close()
            self.assertEqual(page.mouse.mock_calls, [call.move(1102.5, 468)])
            self.assertTrue(action.evidence["after"]["handle"]["hovered"])
            self.assertEqual(action.evidence["geometry_delta"]["panel"], {"x": 0, "y": 0, "width": 0, "height": 0})

    def test_post_gesture_renderer_events_are_kept_before_first_baseline_and_later_events_still_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, _, _, state = self.fixture(folder, "panel-resize-hover")
            def renderer(expression):
                if expression == capture.PanelResizeCapture.POST_GESTURE_SETTLE:
                    # Synthetic same-position trusted move arriving while the
                    # renderer completes. It must not be filtered as redundant.
                    state["pointer_events"].append(copy.deepcopy(state["pointer_events"][-1]))
                return {"status": "loaded", "count": 2}
            page.evaluate.side_effect = renderer
            action.open()
            settling = action.evidence["post_gesture_settling"]
            self.assertEqual(len(settling["state_before"]["pointer_events"]), 1)
            self.assertEqual(len(settling["state_after"]["pointer_events"]), 2)
            self.assertEqual(len(action.baseline["pointer_events"]), 2)
            self.assertTrue(settling["completed"])
            self.assertFalse(settling["baseline_established"])
            state["pointer_events"].append(copy.deepcopy(state["pointer_events"][-1]))
            with self.assertRaisesRegex(RuntimeError, "changed"):
                action.checkpoint("after_screenshot")
            self.assertEqual(len(action.evidence["checkpoints"][-1]["state"]["pointer_events"]), 3)
            action.close()

    def test_post_gesture_overrun_retains_receipt_and_does_not_establish_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            action, _, observer, *_ = self.fixture(folder)
            action.observer = observer
            with patch.object(capture.time, "monotonic", side_effect=[10, 11.001]):
                with self.assertRaisesRegex(RuntimeError, "1000 ms deadline"):
                    action.settle_post_gesture()
            self.assertIsNone(action.baseline)
            self.assertFalse(action.evidence["post_gesture_settling"]["completed"])
            self.assertGreater(action.evidence["post_gesture_settling"]["elapsed_ms"], 1000)
            self.assertIn("error", action.evidence["post_gesture_settling"])
            action.close()

    def test_post_gesture_renderer_failure_is_not_a_successful_observation(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, observer, *_ = self.fixture(folder)
            action.observer = observer
            page.evaluate.side_effect = RuntimeError("actual renderer promise failed")
            with self.assertRaisesRegex(RuntimeError, "actual renderer promise failed"):
                action.settle_post_gesture()
            self.assertEqual(action.evidence["post_gesture_settling"]["error"], "actual renderer promise failed")
            self.assertFalse(action.evidence["post_gesture_settling"]["completed"])
            self.assertIsNone(action.baseline)
            action.close()

    def test_post_gesture_cannot_reset_an_existing_continuity_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, observer, *_ = self.fixture(folder)
            action.observer = observer
            action.baseline = {"actual": "earlier observed baseline"}
            before = copy.deepcopy(action.baseline)
            with self.assertRaisesRegex(RuntimeError, "reset an established"):
                action.settle_post_gesture()
            self.assertEqual(action.baseline, before)
            page.evaluate.assert_not_called()
            action.close()

    def test_small_viewport_opens_hidden_panel_through_actual_overview_button(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, _, opener, _ = self.fixture(folder, width=1024, hidden=True)
            action.open(); action.close()
            opener.click.assert_called_once_with()
            self.assertEqual(action.evidence["open_button"]["title"], "Actual Overview title")
            self.assertFalse(action.evidence["initial_handle_visible"])
            self.assertTrue(action.evidence["open_button_after"]["selected"])
            self.assertEqual(action.evidence["after"]["panel"]["bounds"]["width"], 404)
            self.assertEqual(page.mouse.mock_calls[-2], call.move(622.5, 468, steps=8))

    def test_successful_mouse_commands_without_real_geometry_change_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, _, _, state = self.fixture(folder)
            original = page.mouse.move.side_effect
            def move(*args, **kwargs):
                original(*args, **kwargs)
                state["panel"]["bounds"].update(x=1100, width=340)
                state["handle"]["bounds"]["x"] = 1100
            page.mouse.move.side_effect = move
            with self.assertRaisesRegex(RuntimeError, "geometry did not follow"):
                action.open()
            action.close()
            self.assertEqual(action.evidence["geometry_delta"]["panel"]["width"], 0)

    def test_production_clamp_is_a_failure_before_any_pointer_input(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, *_ = self.fixture(folder, width=600)
            with self.assertRaisesRegex(RuntimeError, "viewport clamp"):
                action.open()
            action.close()
            self.assertEqual(page.mouse.mock_calls, [])

    def test_missing_production_pointer_handler_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, _, _, state = self.fixture(folder)
            original = action.cdp.send.side_effect
            action.cdp.send.side_effect = lambda method, parameters: {"listeners": []} if method == "DOMDebugger.getEventListeners" else original(method, parameters)
            with self.assertRaisesRegex(RuntimeError, "production column-resize"):
                action.open()
            action.close()
            self.assertEqual(page.mouse.mock_calls, [])

    def test_cdp_reads_actual_listener_owner_and_preserves_remote_request_receipts(self):
        with tempfile.TemporaryDirectory() as folder:
            action, *_ = self.fixture(folder)
            result = capture.panel_resize_listener_evidence(action.cdp)
            self.assertEqual(result["owner"]["backendNodeId"], 902)
            self.assertEqual(result["listeners"][0]["backendNodeId"], 902)
            self.assertEqual(result["errors"], [])
            self.assertEqual([item["method"] for item in result["requests"]],
                ["Runtime.evaluate", "DOM.describeNode", "DOMDebugger.getEventListeners", "Runtime.releaseObject"])
            action.cdp.send.assert_any_call("DOMDebugger.getEventListeners", {"objectId": "actual-handle", "depth": 1})
            self.assertTrue(all("result" in item for item in result["requests"]))

    def test_cdp_listener_failure_remains_unknown_and_releases_remote_object(self):
        with tempfile.TemporaryDirectory() as folder:
            action, *_ = self.fixture(folder)
            original = action.cdp.send.side_effect
            def read(method, parameters):
                if method == "DOMDebugger.getEventListeners": raise RuntimeError("actual CDP listener failure")
                return original(method, parameters)
            action.cdp.send.side_effect = read
            result = capture.panel_resize_listener_evidence(action.cdp)
            self.assertIsNone(result["listeners"])
            self.assertEqual(result["errors"], ["actual CDP listener failure"])
            self.assertEqual(result["requests"][-2]["error"], "actual CDP listener failure")
            action.cdp.send.assert_called_with("Runtime.releaseObject", {"objectId": "actual-handle"})

    def test_drag_input_error_releases_real_pressed_button_without_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, *_ = self.fixture(folder)
            original = page.mouse.move.side_effect
            def move(*args, **kwargs):
                if kwargs.get("steps") == 8:
                    raise RuntimeError("actual pointer move failed")
                original(*args, **kwargs)
            page.mouse.move.side_effect = move
            with self.assertRaisesRegex(RuntimeError, "actual pointer move failed"):
                action.open()
            action.close()
            page.mouse.up.assert_called_once_with(button="left")
            self.assertEqual(page.mouse.move.call_count, 2)

    def test_untrusted_event_and_stuck_production_drag_state_fail(self):
        for failure in ("untrusted", "stuck"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                action, page, _, _, state = self.fixture(folder)
                original = page.mouse.up.side_effect
                def up(**kwargs):
                    original(**kwargs)
                    if failure == "untrusted": state["pointer_events"][0]["trusted"] = False
                    else: state["body_resizing"] = True
                page.mouse.up.side_effect = up
                with self.assertRaisesRegex(RuntimeError, "trusted|hovered and idle"):
                    action.open()
                action.close()

    def test_geometry_paint_identity_or_pointer_changes_during_capture_fail(self):
        for quantity in ("geometry", "paint", "identity", "pointer"):
            with self.subTest(quantity=quantity), tempfile.TemporaryDirectory() as folder:
                action, _, _, _, state = self.fixture(folder)
                action.open()
                if quantity == "geometry": state["panel"]["bounds"]["width"] += 1
                elif quantity == "paint": state["handle"]["style"]["background"] = "transparent"
                elif quantity == "identity": state["same_handle"] = False
                else: state["pointer_events"].append({"type": "pointermove", "trusted": True, "x": 0, "y": 0})
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    action.checkpoint("after_element_extraction")
                action.close()
                self.assertEqual(action.evidence["checkpoints"][-1]["state"], state)

    def test_capture_checks_same_handle_across_png_and_all_source_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            page, cdp, browser, action = Mock(), Mock(), Mock(), Mock()
            browser.version = "fixture-browser"
            cdp.send.return_value = {"actual": "DOM or AX fixture"}
            page.evaluate.side_effect = [{"navigator_platform": "fixture"}, {"elements": []}]
            action.evidence = {"source": "actual panel action fixture", "errors": []}
            case = {"id": "fixture-panel", "scene": "panel-resized", "file": "fixture-panel.png"}
            manifest = {"output": folder, "fixture": {}, "lang": "en-US", "theme": "light"}
            with patch.object(capture, "PanelResizeCapture", return_value=action), \
                    patch.object(capture, "input_text_evidence", return_value={"inputs": {}, "errors": []}), \
                    patch.object(capture, "font_evidence", return_value={"actual": "font fixture"}):
                capture.capture_reference_evidence(page, cdp, browser, manifest, case)
            action.open.assert_called_once_with()
            self.assertEqual([entry.args[0] for entry in action.checkpoint.call_args_list],
                ["before_screenshot", "after_screenshot", "after_dom_snapshot", "after_source_evidence", "after_element_extraction"])
            page.screenshot.assert_called_once_with(path=Path(folder) / "fixture-panel.png", caret="initial", animations="allow")
            action.close.assert_called_once_with(); cdp.detach.assert_called_once_with(); page.close.assert_called_once_with()
            actual = json.loads((Path(folder) / "fixture-panel.elements.json").read_text(encoding="utf-8"))
            self.assertEqual(actual["capture_evidence"]["panel_resize_action"], action.evidence)


if __name__ == "__main__":
    unittest.main()
