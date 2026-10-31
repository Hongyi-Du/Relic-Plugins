"""Pure capture orchestration fixtures; no HTTP/browser/process actually runs."""
import io
import json
import unittest
from unittest.mock import Mock, patch

from capture import open_live_tool_output, prepare_animation_capture, prepare_scene


class LiveCaptureTests(unittest.TestCase):
    def test_every_scene_posts_to_fixture_endpoint_including_nonlive_reset(self):
        fixture = {"port": 5555, "token": "fixture-token", "scene_endpoint": "/api/visual/scene"}
        for scene, live in [("live-busy", True), ("group", False)]:
            returned = {"scene": scene, "live": live, "org": "actual-org", "member": "actual-member"}
            with self.subTest(scene=scene), patch("capture.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(returned).encode())) as send:
                self.assertEqual(prepare_scene(fixture, scene), returned)
                request = send.call_args.args[0]
                self.assertEqual(request.get_method(), "POST")
                self.assertEqual(request.full_url, "http://127.0.0.1:5555/api/visual/scene")
                self.assertEqual(json.loads(request.data), {"scene": scene})
                self.assertEqual(request.get_header("X-relic-token"), "fixture-token")

    def test_wrong_or_unprepared_live_response_fails_before_client_navigation(self):
        fixture = {"port": 5555, "token": "fixture-token", "scene_endpoint": "/api/visual/scene"}
        for returned in [{"scene": "group", "live": False, "org": "o", "member": "m"},
                         {"scene": "live-typing", "live": False, "org": "o", "member": "m"},
                         {"scene": "live-typing", "live": True, "org": "o", "member": ""}]:
            with self.subTest(returned=returned), patch("capture.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(returned).encode())):
                with self.assertRaisesRegex(RuntimeError, "did not prepare"):
                    prepare_scene(fixture, "live-typing")

    def test_tool_output_uses_returned_title_and_real_disclosure_click(self):
        page = Mock()
        row = page.locator.return_value.filter.return_value
        row.count.return_value = 1
        row.evaluate.return_value = True
        row.locator.return_value.inner_text.return_value = "Actual tool output\n\tfrom the production control"
        result = open_live_tool_output(page, {"tool": {"title": "Read README.md"}})
        page.get_by_text.assert_called_once_with("Read README.md", exact=True)
        row.locator.assert_any_call(":scope > summary")
        row.locator.return_value.click.assert_called_once()
        row.evaluate.assert_called_once_with("el => el.open")
        self.assertTrue(result["open"])
        self.assertEqual(result["visible_output"], "Actual tool output\n\tfrom the production control")
        page.evaluate.assert_not_called()

    def test_ambiguous_tool_row_is_a_capture_failure_not_an_arbitrary_selection(self):
        page = Mock()
        page.locator.return_value.filter.return_value.count.return_value = 2
        with self.assertRaisesRegex(RuntimeError, "Expected one"):
            open_live_tool_output(page, {"tool": {"title": "Read README.md"}})
        page.locator.return_value.filter.return_value.locator.assert_not_called()

    def test_animation_hook_preserves_actual_framework_receipt_and_skips_other_scenes(self):
        page, cdp = Mock(), Mock()
        self.assertIsNone(prepare_animation_capture(page, cdp, "group"))
        page.evaluate.assert_not_called()
        receipt = {"source": "actual Web Animations API", "before": [{"current_time": 91}],
                   "after": [{"animation_name": "blink", "current_time": 0, "play_state": "paused"}]}
        page.evaluate.return_value = receipt
        self.assertIs(prepare_animation_capture(page, cdp, "live-typing"), receipt)
        cdp.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
