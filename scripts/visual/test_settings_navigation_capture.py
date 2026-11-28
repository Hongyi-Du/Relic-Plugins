"""Synthetic retained-DOM capture contracts; no browser or application is run."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import capture


class SettingsNavigationCaptureTests(unittest.TestCase):
    def setup_capture(self, folder):
        page, target, observer = Mock(), Mock(), Mock()
        target.count.return_value = 1
        page.locator.return_value = target
        page.evaluate.return_value = {"status": "loaded", "count": 2}
        page.evaluate_handle.return_value = observer
        node = {"connected": True, "bounds": {"x": 260, "y": 130, "width": 170, "height": 34},
                "style": {"display": "flex", "visibility": "visible", "opacity": "1",
                          "background": "rgba(0, 0, 0, 0)", "color": "rgb(22, 22, 22)"},
                "text": "actual fixture label", "hovered": False, "focused": False}
        appearance = dict(copy.deepcopy(node), key="appearance", selected=True, disabled=False)
        notify = dict(copy.deepcopy(node), key="notify", selected=False, disabled=False)
        state = {"closure": {"source": "actual production closure settingsPane.current; read-only snapshot", "current": "appearance"},
                 "same_root": True, "same_nav": True, "same_pane": True, "same_buttons": True, "same_target": True,
                 "root": copy.deepcopy(node), "nav": copy.deepcopy(node), "buttons": [appearance, notify],
                 "pane": dict(copy.deepcopy(node), html="<h4>Appearance fixture</h4>",
                              controls=[{"tag": "button", "text": "Dark fixture", "value": "", "disabled": False}]),
                 "pointer": None, "pointer_event_count": 0}
        events = []
        def hover():
            notify["hovered"] = True
            notify["style"]["background"] = "rgb(236, 234, 230)"
            state["pointer"] = {"x": 330, "y": 325, "trusted": True, "target_is_notify": True}
            events.append({"type": "pointermove", **state["pointer"], "timestamp": 100.25})
            state["pointer_event_count"] = len(events)
        target.hover.side_effect = hover
        observer.evaluate.side_effect = lambda expression: copy.deepcopy({"state": state, "pointer_events": events,
            "clock": {"date_now": 1793271720000, "performance_now": 100.5, "time_origin": 1793271719900}}) if expression == "capture => capture.read()" else None
        action = capture.SettingsNavigationCapture(page, "settings-navigation-hover", Path(folder) / "case.scene-action.json")
        return action, page, target, observer, state, events

    def test_real_hover_retains_appearance_and_saves_both_actual_states(self):
        with tempfile.TemporaryDirectory() as folder:
            action, page, target, observer, state, _ = self.setup_capture(folder)
            action.open()
            action.checkpoint("before_screenshot")
            action.checkpoint("after_element_extraction")
            action.close()
            page.locator.assert_called_once_with('.settings nav button[data-k="notify"]')
            target.hover.assert_called_once_with()
            target.click.assert_not_called()
            page.mouse.move.assert_not_called()
            page.clock.pause_at.assert_not_called()
            page.add_style_tag.assert_not_called()
            self.assertFalse(action.evidence["before_action"]["state"]["buttons"][1]["hovered"])
            self.assertTrue(action.evidence["checkpoints"][0]["state"]["buttons"][1]["hovered"])
            self.assertEqual(action.evidence["checkpoints"][0]["state"]["closure"]["current"], "appearance")
            self.assertFalse(action.evidence["checkpoints"][0]["state"]["buttons"][1]["selected"])
            self.assertEqual(json.loads(action.receipt_path.read_text(encoding="utf-8")), action.evidence)
            observer.evaluate.assert_any_call("capture => capture.dispose()")
            observer.dispose.assert_called_once_with()

    def test_foreign_nodes_wrong_selection_or_unmeasured_closure_fail(self):
        changes = [
            lambda state: state.update(same_root=False),
            lambda state: state.update(same_nav=False),
            lambda state: state.update(same_pane=False),
            lambda state: state.update(same_buttons=False),
            lambda state: state.update(same_target=False),
            lambda state: state["closure"].update(current="notify"),
            lambda state: state["closure"].update(source="guessed settings section"),
            lambda state: state["buttons"][0].update(selected=False),
            lambda state: state["buttons"][1].update(selected=True),
        ]
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                action, _, _, _, state, _ = self.setup_capture(folder)
                action.open()
                change(state)
                with self.assertRaisesRegex(RuntimeError, "selection|identity"):
                    action.checkpoint("after_screenshot")
                self.assertEqual(action.evidence["checkpoints"][-1]["state"], state)
                action.close()

    def test_geometry_style_content_selection_and_event_changes_are_not_hidden(self):
        def redundant_event(state, events):
            events.append(dict(events[-1], timestamp=100.75))
            state["pointer_event_count"] += 1
        changes = [
            lambda state, events: state["buttons"][1]["bounds"].update(x=261),
            lambda state, events: state["buttons"][1]["style"].update(background="rgb(240, 240, 240)"),
            lambda state, events: state["pane"]["controls"][0].update(text="Changed actual content"),
            lambda state, events: state["pane"].update(html="<h4>Changed actual page</h4>"),
            lambda state, events: state["pointer"].update(x=331),
            redundant_event,
        ]
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                action, _, _, _, state, events = self.setup_capture(folder)
                action.open()
                change(state, events)
                with self.assertRaisesRegex(RuntimeError, "changed during capture"):
                    action.checkpoint("after_element_extraction")
                self.assertEqual(action.evidence["checkpoints"][-1]["state"], state)
                action.close()

    def test_untrusted_or_foreign_pointer_and_navigation_click_fail(self):
        changes = [
            lambda state, events: state["pointer"].update(trusted=False),
            lambda state, events: state["pointer"].update(target_is_notify=False),
            lambda state, events: events.append({"type": "click", "trusted": True}),
        ]
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                action, _, _, _, state, events = self.setup_capture(folder)
                action.open()
                change(state, events)
                with self.assertRaisesRegex(RuntimeError, "actual hover without a navigation click"):
                    action.checkpoint("after_screenshot")
                action.close()

    def test_detached_or_invisible_target_does_not_supply_a_hover_witness(self):
        changes = [lambda target: target.update(connected=False),
                   lambda target: target["style"].update(display="none"),
                   lambda target: target["style"].update(visibility="hidden"),
                   lambda target: target["style"].update(opacity="0"),
                   lambda target: target["bounds"].update(width=0)]
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                action, _, _, _, state, _ = self.setup_capture(folder)
                action.open()
                change(state["buttons"][1])
                with self.assertRaisesRegex(RuntimeError, "detached or not visible"):
                    action.checkpoint("after_source_evidence")
                action.close()

    def test_scene_hook_opens_actual_appearance_before_generic_settings_dispatch(self):
        source = (capture.HERE / "reference-hook.js").read_text(encoding="utf-8")
        specific = "if (scene === 'settings-navigation-hover') { openSettings('appearance'); return; }"
        self.assertLess(source.index(specific), source.index("if (scene.startsWith('settings-'))"))
        self.assertIn("current: settingsPane?.current ?? null", source)
        self.assertNotIn("classList", capture.SettingsNavigationCapture.INSTALL_OBSERVER.replace("classList.contains", ""))
        self.assertNotIn("setAttribute", capture.SettingsNavigationCapture.INSTALL_OBSERVER)

    def test_capture_framework_retains_hover_across_png_and_all_extraction_checkpoints(self):
        with tempfile.TemporaryDirectory() as folder:
            page, cdp, browser, action = Mock(), Mock(), Mock(), Mock()
            browser.version = "synthetic-browser"
            cdp.send.return_value = {"synthetic": "DOM or AX response"}
            page.evaluate.side_effect = [{"navigator_platform": "synthetic"}, {"elements": []}]
            action.evidence = {"source": "synthetic action", "errors": []}
            case = {"id": "settings-hover", "scene": "settings-navigation-hover", "file": "settings-hover.png"}
            manifest = {"output": folder, "fixture": {}, "lang": "en-US", "theme": "light"}
            with patch.object(capture, "SettingsNavigationCapture", return_value=action), \
                    patch.object(capture, "input_text_evidence", return_value={"inputs": {}, "errors": []}), \
                    patch.object(capture, "panel_resize_listener_evidence", return_value={}), \
                    patch.object(capture, "font_evidence", return_value={}), \
                    patch("scrollbar_pixels.append_scrollbar_pixels"):
                capture.capture_reference_evidence(page, cdp, browser, manifest, case)
            action.open.assert_called_once_with()
            self.assertEqual([call.args[0] for call in action.checkpoint.call_args_list],
                ["before_screenshot", "after_screenshot", "after_dom_snapshot", "after_source_evidence", "after_element_extraction"])
            page.screenshot.assert_called_once_with(path=Path(folder) / "settings-hover.png", caret="initial", animations="allow")
            action.close.assert_called_once_with()
            page.close.assert_called_once_with()
            cdp.detach.assert_called_once_with()
            actual = json.loads((Path(folder) / "settings-hover.elements.json").read_text(encoding="utf-8"))
            self.assertEqual(actual["capture_evidence"]["settings_navigation_action"], action.evidence)

    def test_framework_failure_saves_error_and_still_cleans_observer(self):
        with tempfile.TemporaryDirectory() as folder:
            page, cdp, action = Mock(), Mock(), Mock()
            action.evidence = {"errors": []}
            action.checkpoint.side_effect = RuntimeError("actual hover changed")
            case = {"id": "settings-hover", "scene": "settings-navigation-hover", "file": "settings-hover.png"}
            manifest = {"output": folder, "fixture": {}, "lang": "en-US", "theme": "light"}
            with patch.object(capture, "SettingsNavigationCapture", return_value=action):
                with self.assertRaisesRegex(RuntimeError, "actual hover changed"):
                    capture.capture_reference_evidence(page, cdp, Mock(), manifest, case)
            self.assertEqual(action.evidence["errors"], ["actual hover changed"])
            action.save.assert_called_once_with()
            action.close.assert_called_once_with()
            page.screenshot.assert_not_called()
            page.close.assert_called_once_with()
            cdp.detach.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
