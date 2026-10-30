"""CI-only CC observer fixtures; no browser, server, HTTP call or subprocess."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from capture import ReferenceCcCapture, validate_reference_cc


def ready(unread=5):
    body = {"items": [{"id": 17, "title": "实际抄送", "read": False}], "unread": unread}
    cc = dict(deepcopy(body), loaded=True)
    state = {"source": "actual production closure S.cc and ccAsked; detached read-only snapshot",
        "asked": 1, "cc": cc, "copies_connected": False,
        "loads": [{"stage": "before-scene-controls", "status": "ready", "request_asked": 1,
                   "before": {"asked": 0}, "after": {"asked": 1, "cc": deepcopy(cc)}}]}
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    row = {"id": "cc-response-1", "ordinal": 1, "request_observed": True, "finished": True,
           "failure": None, "errors": [], "method": "GET", "status": 200,
           "request_url": "http://127.0.0.1:7777/api/cc", "url": "http://127.0.0.1:7777/api/cc",
           "body_base64": base64.b64encode(raw).decode("ascii"), "byte_length": len(raw), "json": body}
    return state, row, raw


class ReferenceCcCaptureTests(unittest.TestCase):
    def test_real_server_total_is_not_recomputed_from_returned_unread_items(self):
        state, row, _ = ready()
        before = deepcopy((state, row))
        receipt = validate_reference_cc(state, [row])
        self.assertEqual(receipt["unread"], 5)
        self.assertEqual(len(state["cc"]["items"]), 1)
        self.assertEqual((state, row), before)

    def test_missing_failed_or_superseded_closure_receipt_stays_unknown(self):
        changes = (
            lambda s: s.pop("source"),
            lambda s: s.update(asked=True),
            lambda s: s["cc"].update(loaded=False),
            lambda s: s.update(loads=[]),
            lambda s: s["loads"][-1].update(status="failed"),
            lambda s: s["loads"][-1].update(request_asked=2),
            lambda s: s["loads"][-1].update(after=None),
            lambda s: s["loads"][-1]["before"].update(asked=1),
            lambda s: s["cc"].update(unread=0),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                state, row, _ = ready()
                change(state)
                with self.assertRaises(RuntimeError):
                    validate_reference_cc(state, [row])

    def test_response_sequence_failure_or_different_payload_cannot_supply_readiness(self):
        for change in (
            {"ordinal": 2}, {"request_observed": False}, {"finished": False},
            {"failure": "actual request failure"}, {"errors": ["body unavailable"]},
            {"method": "POST"}, {"status": 500}, {"body_base64": None},
            {"url": "http://127.0.0.1:7777/other"}, {"json": {"items": [], "unread": 5}},
            {"json": {"items": [], "unread": True}},
        ):
            with self.subTest(change=change):
                state, row, _ = ready()
                row.update(change)
                with self.assertRaises(RuntimeError):
                    validate_reference_cc(state, [row])
        state, row, _ = ready()
        for rows in ([], [row, deepcopy(row)]):
            with self.assertRaises(RuntimeError):
                validate_reference_cc(state, rows)

    def observed(self, folder, raw=None):
        state, row, body = ready()
        page = Mock()
        page.evaluate.side_effect = lambda expression: deepcopy(state)
        observer = ReferenceCcCapture(page, folder, "actual-case")
        request = SimpleNamespace(method="GET", url=row["url"], failure=None)
        response = SimpleNamespace(request=request, url=row["url"], status=200,
                                   headers={"content-type": "application/json"}, body=Mock(return_value=body if raw is None else raw))
        observer.on_request(request)
        observer.on_response(response)
        observer.on_finished(request)
        return observer, page, state, response, body

    def test_observer_retains_actual_response_bytes_and_detached_state_at_every_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            observer, page, state, response, body = self.observed(folder)
            for stage in ("after_scene_controls", "before_screenshot", "after_screenshot", "after_element_extraction"):
                observer.checkpoint(stage)
            observer.close()
            saved = json.loads((Path(folder) / "actual-case.cc.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["errors"], [])
            self.assertEqual(len(saved["checkpoints"]), 4)
            self.assertTrue(all(point["state"] == state for point in saved["checkpoints"]))
            self.assertEqual(base64.b64decode(saved["responses"][0]["body_base64"]), body)
            self.assertEqual(saved["responses"][0]["json"]["unread"], 5)
            response.body.assert_called_once_with()
            self.assertEqual({call.args[0] for call in page.on.call_args_list},
                             {"request", "response", "requestfinished", "requestfailed"})
            self.assertEqual(page.remove_listener.call_args_list, page.on.call_args_list)
            self.assertTrue(all(call.args == ("window.__relicVisualCcState",) for call in page.evaluate.call_args_list))
            page.request.get.assert_not_called()
            page.route.assert_not_called()

    def test_closure_change_after_screenshot_is_retained_and_fails_without_resetting_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            observer, _, state, _, _ = self.observed(folder)
            observer.checkpoint("before_screenshot")
            original = deepcopy(observer.baseline)
            state["copies_connected"] = True
            with self.assertRaisesRegex(RuntimeError, "state changed"):
                observer.checkpoint("after_screenshot")
            self.assertEqual(observer.baseline, original)
            saved = json.loads(observer.path.read_text(encoding="utf-8"))
            self.assertTrue(saved["errors"])
            self.assertTrue(saved["checkpoints"][-1]["state"]["copies_connected"])
            observer.close()

    def test_invalid_actual_json_bytes_are_preserved_when_readiness_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = b'{"items":'
            observer, _, _, _, _ = self.observed(folder, bad)
            with self.assertRaises(RuntimeError):
                observer.checkpoint("after_scene_controls")
            row = json.loads(observer.path.read_text(encoding="utf-8"))["responses"][0]
            self.assertEqual(base64.b64decode(row["body_base64"]), bad)
            self.assertIsNone(row["json"])
            self.assertTrue(row["errors"])
            observer.close()

    def test_unobserved_request_start_and_unrelated_requests_are_not_invented(self):
        with tempfile.TemporaryDirectory() as folder:
            state, row, body = ready()
            page = Mock(); page.evaluate.return_value = state
            observer = ReferenceCcCapture(page, folder, "unobserved")
            observer.on_request(SimpleNamespace(method="GET", url="http://127.0.0.1/api/cc/1/read"))
            self.assertEqual(observer.evidence["responses"], [])
            request = SimpleNamespace(method="GET", url=row["url"])
            response = SimpleNamespace(request=request, url=row["url"], status=200,
                                       headers={}, body=lambda: body)
            observer.on_response(response); observer.on_finished(request)
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                observer.checkpoint("before_screenshot")
            self.assertFalse(observer.evidence["responses"][0]["request_observed"])
            observer.close()


if __name__ == "__main__":
    unittest.main()
