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
    def test_launch_keeps_production_scrollbars_without_replacing_default_arguments(self):
        playwright = Mock()
        self.assertIs(paint_trace.launch_browser(playwright), playwright.chromium.launch.return_value)
        playwright.chromium.launch.assert_called_once_with(headless=True,
            args=["--disable-dev-shm-usage"], ignore_default_args=["--hide-scrollbars"])

    def test_supported_trace_configuration_retains_all_paint_and_frame_sources(self):
        parameters = paint_trace.trace_parameters()
        self.assertNotIn("categories", parameters)
        self.assertNotIn("options", parameters)
        config = parameters["traceConfig"]
        self.assertEqual(config["recordMode"], "recordUntilFull")
        self.assertEqual(config["traceBufferSizeInKb"], 200 * 1024)
        self.assertEqual(parameters["bufferUsageReportingInterval"], 250)
        self.assertEqual(set(config["includedCategories"]), {
            "devtools.timeline", "disabled-by-default-devtools.timeline.frame",
            "disabled-by-default-devtools.timeline.picture",
            "disabled-by-default-cc.debug.picture", "disabled-by-default-cc.debug.display_items"})
        config["includedCategories"].clear()
        self.assertEqual(len(paint_trace.TRACE_CATEGORIES), 5)

    def test_recorded_writer_loss_is_preserved_even_when_central_buffer_is_not_full(self):
        # Scalar values transcribed from 05fe5cf group trace metadata. No SKP is
        # parsed, and these counters do not establish why a producer lost data.
        stats = {"packet_skipped_seq_needs_incremental_state_invalid": 59873,
            "traced_chunks_discarded": 0, "traced_buf": [{"buffer_size": 209715200,
                "bytes_written": 65708032, "bytes_read": 65675264, "bytes_overwritten": 0,
                "trace_writer_packet_loss": 14, "sequence_packet_loss": 14, "data_loss_smb_full": 0}]}
        trace = {"metadata": {"command_line": "fixture-browser --headless", "trace_processor_stats": stats},
            "traceEvents": [{"name": "clock_sync", "ts": 100, "args": {"sync_id": "fixture:before_screenshot"}},
                            {"name": "cc::DisplayItemList:snapshot", "ts": 50, "cat": "fixture"}]}
        original = copy.deepcopy(trace)
        result = paint_trace.trace_diagnostics(trace, {"pictures": [{"event_index": 1}, {"event_index": 1}]})
        self.assertEqual(result["trace_processor_stats"], stats)
        self.assertEqual([row["value"] for row in result["nonzero_loss_evidence"]], [59873, 14, 14])
        self.assertEqual(result["nonzero_loss_evidence"][1]["trace_json_pointer"],
                         "/metadata/trace_processor_stats/traced_buf/0/trace_writer_packet_loss")
        self.assertEqual(result["picture_events"][0]["event"]["ts"], 50)
        self.assertEqual(len(result["picture_events"]), 1)
        self.assertEqual(result["clock_sync_events"][0]["event"]["ts"], 100)
        self.assertIsNone(result["final_scene_attribution"])
        self.assertEqual(trace, original)

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
        cases = [
            {"has_picture": True, "expected": "raw_records_collected"},
            {"has_picture": False, "expected": "failed"},
            {"has_picture": True, "data_loss": True, "expected": "failed"},
            {"has_picture": True, "has_layers": False, "expected": "failed"},
            {"has_picture": True, "hidden_scrollbars": True, "expected": "failed"},
            {"has_picture": True, "missing_command_line": True, "expected": "failed"},
            {"has_picture": True, "writer_loss": 1, "expected": "failed"},
        ]
        for fixture in cases:
            has_picture, data_loss = fixture["has_picture"], fixture.get("data_loss", False)
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory() as folder:
                browser, context, cdp, trace_cdp, page = Mock(), Mock(), Mock(), Mock(), Mock()
                browser.version = "fixture-version"
                browser.new_browser_cdp_session.return_value = trace_cdp
                context.new_cdp_session.return_value = cdp
                context.new_page.return_value = page
                page.evaluate.side_effect = [None, {"quantity": "fixture DOM layout metrics"}]
                callbacks = {}
                trace_cdp.on.side_effect = lambda event, handler: callbacks.update({event: handler})
                cdp.on.side_effect = lambda event, handler: callbacks.update({event: handler})
                command_line = "fixture-browser --headless" + (" --hide-scrollbars" if fixture.get("hidden_scrollbars") else "")
                trace = {"metadata": {"command_line": None if fixture.get("missing_command_line") else command_line,
                            "trace_processor_stats": {"traced_buf": [{"trace_writer_packet_loss": fixture.get("writer_loss", 0)}]}},
                    "traceEvents": [{"args": {"skp64": base64.b64encode(b"synthetic fixture bytes").decode()}}] if has_picture else []}
                def page_send(method, parameters=None):
                    if method == "LayerTree.enable" and fixture.get("has_layers", True):
                        callbacks["LayerTree.layerTreeDidChange"]({"layers": [{"layerId": "fixture-layer"}]})
                    return {}
                cdp.send.side_effect = page_send
                def send(method, parameters=None):
                    if method == "Tracing.start":
                        callbacks["Tracing.bufferUsage"]({"percentFull": 0.25, "eventCount": 1})
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
                self.assertEqual(result["status"], fixture["expected"])
                self.assertEqual(result["measurement_status"], "unresolved")
                self.assertIsNone(result["glyph_bounds"])
                self.assertIsNone(result["scrollbar_parts"])
                self.assertEqual(json.loads((Path(folder) / "scene" / "trace.json").read_text()), trace)
                self.assertEqual(json.loads((Path(folder) / "scene" / "trace-config.json").read_text()), paint_trace.trace_parameters())
                self.assertEqual(json.loads((Path(folder) / "scene" / "buffer-usage.json").read_text())[0]["params"],
                                 {"percentFull": 0.25, "eventCount": 1})
                diagnostics = json.loads((Path(folder) / "scene" / "trace-diagnostics.json").read_text())
                self.assertEqual(diagnostics["command_line"], trace["metadata"]["command_line"])
                page.screenshot.assert_called_once()
                page.close.assert_called_once()
                if not has_picture:
                    self.assertTrue(any("No actual skp64" in row["reason"] for row in result["errors"]))
                if data_loss:
                    self.assertTrue(any("data loss" in row["reason"] for row in result["errors"]))
                if not fixture.get("has_layers", True):
                    self.assertTrue(any(row["source"] == "LayerTree" for row in result["errors"]))
                if fixture.get("hidden_scrollbars") or fixture.get("missing_command_line"):
                    self.assertTrue(any(row["source"] == "browser_command_line" for row in result["errors"]))
                if fixture.get("writer_loss"):
                    self.assertTrue(any(row["source"] == "trace_processor_stats" for row in result["errors"]))


if __name__ == "__main__":
    unittest.main()
