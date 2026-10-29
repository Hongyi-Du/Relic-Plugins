"""Pure fixtures for paint-trace export. No browser, server or process starts."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import paint_trace


class PaintTraceTests(unittest.TestCase):
    def test_ci_guard_precedes_manifest_read_import_or_process_creation(self):
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}), patch.object(paint_trace.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(SystemExit, "CI-only"):
                paint_trace.main(["--manifest", "does-not-exist.json", "--output", "unused"])
            launch.assert_not_called()

    def test_diagnostic_selects_existing_cases_without_editing_manifest(self):
        manifest = {"cases": [{"id": "group-1440", "scene": "group", "width": 1440, "height": 900},
                              {"id": "group-1024", "scene": "group", "width": 1024, "height": 700},
                              {"id": "file-1440", "scene": "file-code", "width": 1440, "height": 900}]}
        original = copy.deepcopy(manifest)
        selected = paint_trace.select_cases(manifest, ["file-code", "group"], 1440, 900)
        self.assertEqual([case["id"] for case in selected], ["file-1440", "group-1440"])
        selected[0]["id"] = "changed diagnostic copy"
        self.assertEqual(manifest, original)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            paint_trace.select_cases(manifest, ["unknown-scene"], 1440, 900)

    def test_stream_bytes_are_preserved_across_text_and_base64_chunks(self):
        cdp = Mock()
        original = b'{"traceEvents":[],"fixture":"' + "真实原始流".encode("utf-8") + b'"}'
        split = len(b'{"traceEvents":[],"fixture":"')
        cdp.send.side_effect = [
            {"data": original[:split].decode(), "eof": False},
            {"data": base64.b64encode(original[split:]).decode(), "base64Encoded": True, "eof": True}, {}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "trace.json"
            self.assertEqual(paint_trace.read_trace_stream(cdp, "stream-1", path), len(original))
            self.assertEqual(path.read_bytes(), original)
        self.assertEqual(cdp.send.call_args.args, ("IO.close", {"handle": "stream-1"}))

    def test_failed_stream_read_still_closes_handle(self):
        cdp = Mock()
        cdp.send.side_effect = [RuntimeError("trace stream disconnected"), {}]
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, "disconnected"):
                paint_trace.read_trace_stream(cdp, "stream-2", Path(folder) / "trace.json")
        self.assertEqual(cdp.send.call_args.args, ("IO.close", {"handle": "stream-2"}))

    def test_all_picture_payloads_keep_source_locations_and_unknown_attribution(self):
        # Synthetic serialized bytes test transport only, not valid Skia parsing.
        first, second = b"record-one-fixture", b"record-two-fixture"
        trace = {"traceEvents": [{"name": "cc::DisplayItemList:snapshot", "cat": "cc", "ts": 123,
            "pid": 7, "tid": 8, "args": {"layer_id": 11, "snapshot": {
                "skp64": base64.b64encode(first).decode(),
                "params": {"items": [{"skp64": base64.b64encode(second).decode()}]}}}},
            {"name": "unrelated", "args": {}}]}
        original = copy.deepcopy(trace)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = paint_trace.extract_pictures(trace, root / "pictures")
            self.assertEqual(result["trace_event_count"], 2)
            self.assertEqual(result["errors"], [])
            self.assertEqual([row["trace_json_pointer"] for row in result["pictures"]], [
                "/traceEvents/0/args/snapshot/skp64", "/traceEvents/0/args/snapshot/params/items/0/skp64"])
            for row, raw in zip(result["pictures"], [first, second]):
                self.assertEqual((root / row["file"]).read_bytes(), raw)
                self.assertEqual(row["layer_id"], 11)
                self.assertIsNone(row["parsed_skp"])
                self.assertIsNone(row["final_scene_attribution"])
        self.assertEqual(trace, original, "Never rewrite or filter original trace events")

    def test_absent_or_invalid_picture_data_cannot_be_fabricated(self):
        with tempfile.TemporaryDirectory() as folder:
            result = paint_trace.extract_pictures({"traceEvents": [{"args": {"skp64": "not base64!"}}]}, Path(folder))
            self.assertEqual(result["pictures"], [])
            self.assertEqual(len(result["errors"]), 1)
            self.assertEqual(result["errors"][0]["trace_json_pointer"], "/traceEvents/0/args/skp64")
            self.assertEqual(list(Path(folder).glob("*.skp")), [])

    def test_scene_receipt_distinguishes_raw_collection_from_measured_parity(self):
        for has_picture, data_loss, expected in [(True, False, "raw_records_collected"),
                                                  (False, False, "failed"), (True, True, "failed")]:
            with self.subTest(has_picture=has_picture, data_loss=data_loss), tempfile.TemporaryDirectory() as folder:
                browser, context, cdp, trace_cdp, page = Mock(), Mock(), Mock(), Mock(), Mock()
                browser.version = "fixture-version"
                browser.new_browser_cdp_session.return_value = trace_cdp
                context.new_cdp_session.return_value = cdp
                context.new_page.return_value = page
                page.evaluate.side_effect = [None, {"quantity": "fixture DOM layout metrics"}]
                cdp.send.return_value = {}
                callbacks = {}
                trace_cdp.on.side_effect = lambda event, handler: callbacks.update({event: handler})
                trace = {"traceEvents": [{"args": {"skp64": base64.b64encode(b"synthetic fixture bytes").decode()}}] if has_picture else []}
                def send(method, parameters=None):
                    if method == "Tracing.end":
                        callbacks["Tracing.tracingComplete"]({"stream": "fixture-stream", "dataLossOccurred": data_loss})
                    if method == "IO.read":
                        return {"data": json.dumps(trace), "eof": True}
                    return {}
                trace_cdp.send.side_effect = send
                manifest = {"fixture": {"clock": "2026-10-29T11:02:00Z", "port": 1}}
                case = {"id": "fixture-group", "scene": "group", "width": 1440, "height": 900}
                with patch.object(paint_trace, "input_text_evidence", return_value={"inputs": {}, "errors": []}), \
                        patch.object(paint_trace, "font_evidence", return_value={"errors": []}):
                    result = paint_trace.collect_scene(browser, context, manifest, case, Path(folder) / "scene", "fixture source")
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["measurement_status"], "unresolved")
                self.assertIsNone(result["glyph_bounds"])
                self.assertIsNone(result["scrollbar_parts"])
                self.assertEqual(json.loads((Path(folder) / "scene" / "trace.json").read_text()), trace)
                page.screenshot.assert_called_once()
                page.close.assert_called_once()
                if not has_picture:
                    self.assertTrue(any("No actual skp64" in row["reason"] for row in result["errors"]))
                if data_loss:
                    self.assertTrue(any("data loss" in row["reason"] for row in result["errors"]))


if __name__ == "__main__":
    unittest.main()
