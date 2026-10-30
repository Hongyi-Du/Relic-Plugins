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

    def test_full_chromium_diagnostic_is_explicit_and_keeps_headless_scrollbar_capture(self):
        playwright = Mock()
        paint_trace.launch_browser(playwright, "chromium")
        playwright.chromium.launch.assert_called_once_with(headless=True, channel="chromium",
            args=["--disable-dev-shm-usage"], ignore_default_args=["--hide-scrollbars"])
        with self.assertRaises(ValueError):
            paint_trace.launch_browser(playwright, "unrecognized")
        self.assertEqual(playwright.chromium.launch.call_count, 1)

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
                        callbacks["LayerTree.layerTreeDidChange"]({"layers": [{"layerId": "fixture-layer",
                            "drawsContent": True, "paintCount": 2, "offsetX": 0, "offsetY": 0,
                            "width": 1440, "height": 900, "backendNodeId": 17}]})
                    if method == "DOM.getDocument":
                        return {"root": {"nodeId": 1, "backendNodeId": 2, "nodeType": 9}}
                    if method == "LayerTree.makeSnapshot":
                        return {"snapshotId": "fixture-snapshot"}
                    if method == "LayerTree.snapshotCommandLog":
                        return {"commandLog": [{"method": "fixture-paint-record"}]}
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
                progress = json.loads((Path(folder) / "scene" / "progress.json").read_text())
                self.assertEqual(progress[-1]["operation"], "page/protocol-cleanup")
                self.assertEqual(progress[-1]["state"], "completed")
                starts = [row["operation"] for row in progress if row["state"] == "started"]
                self.assertIn("Tracing.start", starts)
                self.assertIn("Tracing.end", starts)
                self.assertIn("trace-stream", starts)
                self.assertLess(starts.index("page/navigation-and-real-scene"), starts.index("DOM.getDocument"))
                self.assertLess(starts.index("DOM.getDocument"),
                                [index for index, value in enumerate(starts) if value == "LayerTree.enable"][-1])
                if fixture.get("has_layers", True):
                    self.assertLess(starts.index("page/screenshot"), starts.index("LayerTree.makeSnapshot"))
                    self.assertLess(starts.index("LayerTree.makeSnapshot"), starts.index("LayerTree.snapshotCommandLog"))
                    self.assertLess(starts.index("LayerTree.snapshotCommandLog"), starts.index("LayerTree.releaseSnapshot"))
                    layer_receipt = json.loads((Path(folder) / "scene" / "layer-snapshots.json").read_text())
                    self.assertIsNone(layer_receipt["final_scene_attribution"])
                    self.assertEqual(layer_receipt["status"], "raw_records_collected")
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


class LayerSnapshotTests(unittest.TestCase):
    @staticmethod
    def event(layer_id="actual-layer", **values):
        return {"method": "LayerTree.layerTreeDidChange", "phase": "post_navigation_layer_enable",
            "received_monotonic": 12.5, "params": {"layers": [{"layerId": layer_id,
                "drawsContent": True, "paintCount": 3, "backendNodeId": 71,
                "offsetX": 1.25, "offsetY": 2.5, "width": 789, "height": 456,
                "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 12, 24, 0, 1], **values}]}}

    @staticmethod
    def reader(session, method, parameters):
        if method == "LayerTree.makeSnapshot":
            return {"snapshotId": "actual-snapshot"}
        if method == "LayerTree.snapshotCommandLog":
            return {"commandLog": [{"method": "drawRect", "params": {"fixture": True}}]}
        if method == "LayerTree.releaseSnapshot":
            return {}
        raise AssertionError("Unexpected protocol method " + method)

    def collect(self, root, events, read=None, first_event=0):
        boundaries = []
        result = paint_trace.collect_layer_snapshots(Mock(), read or Mock(side_effect=self.reader),
            root, events, first_event, boundaries)
        return result, boundaries

    def test_boundary_retains_event_identity_clip_and_offsets_without_synchronous_claim(self):
        events = [self.event(), {"method": "LayerTree.layerPainted", "phase": "before_screenshot",
            "received_monotonic": 13.0, "params": {"layerId": "actual-layer",
                "clip": {"x": 4, "y": 5, "width": 6, "height": 7}}}]
        original = copy.deepcopy(events)
        with tempfile.TemporaryDirectory() as folder:
            result = paint_trace.layer_boundary(events, 0, "before_screenshot", Path(folder), [])
        self.assertEqual(result["latest_tree_event_index"], 0)
        self.assertEqual(result["latest_tree_event"], original[0])
        self.assertEqual(result["paint_events_since_previous_boundary"], [{"event_index": 1, "event": original[1]}])
        self.assertIsNone(result["final_scene_attribution"])
        events[0]["params"]["layers"][0]["paintCount"] = 99
        self.assertEqual(result["latest_tree_event"]["params"]["layers"][0]["paintCount"], 3)

    def test_pre_navigation_layers_cannot_be_used_as_current_layers(self):
        read = Mock()
        with tempfile.TemporaryDirectory() as folder:
            result, boundaries = self.collect(Path(folder), [self.event("old-document-layer")], read, first_event=1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["layers"], [])
        self.assertIn("post-navigation", result["errors"][0]["reason"])
        self.assertIsNone(boundaries[0]["latest_tree_event"])
        read.assert_not_called()

    def test_latest_empty_tree_does_not_fall_back_to_previous_content_layers(self):
        events = [self.event(), {"method": "LayerTree.layerTreeDidChange", "params": {}}]
        read = Mock()
        with tempfile.TemporaryDirectory() as folder:
            result, boundaries = self.collect(Path(folder), events, read)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(boundaries[0]["latest_tree_event_index"], 1)
        read.assert_not_called()

    def test_snapshot_uses_only_actual_layer_and_snapshot_ids_and_keeps_entire_responses(self):
        events = [self.event()]
        original = copy.deepcopy(events)
        read = Mock(side_effect=self.reader)
        with tempfile.TemporaryDirectory() as folder:
            result, boundaries = self.collect(Path(folder), events, read)
            entry = json.loads((Path(folder) / result["layers"][0]["file"]).read_text())
        self.assertEqual(result["status"], "raw_records_collected")
        self.assertEqual([call.args[1:] for call in read.call_args_list], [
            ("LayerTree.makeSnapshot", {"layerId": "actual-layer"}),
            ("LayerTree.snapshotCommandLog", {"snapshotId": "actual-snapshot"}),
            ("LayerTree.releaseSnapshot", {"snapshotId": "actual-snapshot"})])
        self.assertEqual(entry["source_layer"], original[0]["params"]["layers"][0])
        self.assertEqual(entry["requests"][1]["response"], self.reader(None, "LayerTree.snapshotCommandLog", {}))
        self.assertTrue(all(request["status"] == "completed" for request in entry["requests"]))
        self.assertTrue(all(row["final_scene_attribution"] is None for row in boundaries))
        self.assertIsNone(entry["final_scene_attribution"])
        self.assertEqual(events, original)

    def test_zero_paint_count_keeps_actual_logs_but_remains_failed(self):
        with tempfile.TemporaryDirectory() as folder:
            result, _ = self.collect(Path(folder), [self.event(paintCount=0)])
            entry = json.loads((Path(folder) / result["layers"][0]["file"]).read_text())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(entry["source_layer"]["paintCount"], 0)
        self.assertEqual(entry["requests"][1]["response"]["commandLog"][0]["method"], "drawRect")
        self.assertTrue(any(error["source"] == "LayerTree.paintCount" for error in result["errors"]))

    def test_failed_command_log_still_releases_actual_snapshot_and_retains_failure(self):
        def reader(session, method, parameters):
            return None if method == "LayerTree.snapshotCommandLog" else self.reader(session, method, parameters)
        read = Mock(side_effect=reader)
        with tempfile.TemporaryDirectory() as folder:
            result, _ = self.collect(Path(folder), [self.event()], read)
            entry = json.loads((Path(folder) / result["layers"][0]["file"]).read_text())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(read.call_args.args[1:], ("LayerTree.releaseSnapshot", {"snapshotId": "actual-snapshot"}))
        self.assertEqual(entry["requests"][1]["status"], "failed")

    def test_failed_make_snapshot_does_not_invent_id_or_request_command_log(self):
        read = Mock(return_value=None)
        with tempfile.TemporaryDirectory() as folder:
            result, _ = self.collect(Path(folder), [self.event()], read)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(read.call_count, 1)
        self.assertEqual(read.call_args.args[1], "LayerTree.makeSnapshot")

    def test_failed_release_is_retained_even_when_log_was_collected(self):
        def reader(session, method, parameters):
            return None if method == "LayerTree.releaseSnapshot" else self.reader(session, method, parameters)
        with tempfile.TemporaryDirectory() as folder:
            result, _ = self.collect(Path(folder), [self.event()], Mock(side_effect=reader))
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any(error["source"] == "LayerTree.releaseSnapshot" for error in result["errors"]))

    def test_actual_non_content_layer_retained_without_inventing_paint(self):
        read = Mock()
        with tempfile.TemporaryDirectory() as folder:
            result, _ = self.collect(Path(folder), [self.event(drawsContent=False, paintCount=0)], read)
            entry = json.loads((Path(folder) / result["layers"][0]["file"]).read_text())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(entry["status"], "not_requested_non_content_layer")
        self.assertEqual(entry["source_layer"]["paintCount"], 0)
        read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
