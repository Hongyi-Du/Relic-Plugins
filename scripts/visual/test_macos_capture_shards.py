"""Pure macOS viewport/receipt fixtures. Every process and timer is mocked."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import capture
import macos_capture_shards as shards


class MacOSCaptureShardTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"GITHUB_ACTIONS": "true"})
        environment.start()
        self.addCleanup(environment.stop)

    def manifest(self, root, scenes=("group", "private"), sizes=((1440, 900), (1280, 800), (1024, 700))):
        output = root / "images"
        output.mkdir()
        return {"client": "macos", "lang": "zh-CN", "theme": "light", "output": str(output),
                "fixture": {"home": str(root / "fixture"), "clock": "2026-10-29T11:02:00Z", "port": 5555},
                "cases": [{"id": f"zh-CN-light-{w}x{h}-{scene}", "file": f"zh-CN-light-{w}x{h}-{scene}.png",
                           "scene": scene, "width": w, "height": h} for w, h in sizes for scene in scenes]}

    def receipt(self, path, manifest, rows=None, errors=None):
        cases = manifest["cases"]
        rows = [{"id": case["id"], "file": case["file"], "status": "captured"} for case in cases] if rows is None else rows
        for case in cases:
            (Path(manifest["output"]) / case["file"]).write_bytes(b"transport fixture only, not pixel validation")
            (Path(manifest["output"]) / (case["id"] + ".elements.json")).write_text("{}", encoding="utf-8")
        result = {"count": len(rows), "errors": errors or [], "cases": rows}
        (path.parent / "complete.json").write_text(json.dumps(result), encoding="utf-8")
        (path.parent / "process-exit.json").write_text('{"pid":1234,"returncode":0,"forced_kill":false}', encoding="utf-8")
        return result

    def test_full_165_cases_use_three_fresh_55_case_processes_and_original_order(self):
        scenes = json.loads((capture.HERE / "scenes.json").read_text(encoding="utf-8"))["scenes"]
        self.assertEqual(len(scenes), 55)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); manifest = self.manifest(root, scenes); original = copy.deepcopy(manifest)
            calls = []
            def run(path, per_shard, exe):
                calls.append(path)
                self.assertEqual(len(per_shard["cases"]), 55)
                self.assertEqual(per_shard["fixture"], original["fixture"])
                self.assertEqual(per_shard["output"], original["output"])
                self.assertEqual(json.loads(path.read_text()), per_shard)
                self.assertEqual([p.name for p in path.parent.iterdir()], ["manifest.json"])
                return self.receipt(path, per_shard)
            with patch.object(capture, "native_process", side_effect=run):
                result = capture.native(root / "manifest.json", manifest, Path("Relic"))
            self.assertEqual([path.parent.name for path in calls], ["1440x900", "1280x800", "1024x700"])
            self.assertEqual(result["expected_count"], 165)
            self.assertEqual(result["attempted_count"], 165)
            self.assertEqual(result["count"], 165)
            self.assertEqual(result["errors"], [])
            self.assertEqual([case["case_id"] for case in result["cases"]], [case["id"] for case in original["cases"]])
            self.assertEqual(json.loads((root / "complete.json").read_text()), result)
            self.assertEqual(manifest, original)

    def test_failed_state_is_not_success_even_with_both_files_and_native_count(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); manifest = self.manifest(root)
            def run(path, per_shard, exe):
                cases = per_shard["cases"]
                if cases[0]["width"] != 1440:
                    return self.receipt(path, per_shard)
                rows = [{"id": case["id"], "file": case["file"], "status": "captured"} for case in cases]
                rows[1].update(status="failed-state-captured", error="real scene failure fixture")
                source = self.receipt(path, per_shard, rows, [cases[1]["id"] + ": real scene failure fixture"])
                self.assertEqual(source["count"], 2)
                raise RuntimeError(str(source["errors"]))
            result = shards.capture_shards(root / "manifest.json", manifest, Path("Relic"), run)
            self.assertEqual(result["count"], 5)
            self.assertEqual(result["attempted_count"], 6)
            self.assertEqual(result["cases"][1]["status"], "failed-state-captured")
            self.assertEqual(result["shards"][0]["native_receipt"]["count"], 2)
            self.assertEqual(len(result["shards"]), 3)
            self.assertTrue(result["errors"])
            self.assertEqual(result["shards"][2]["status"], "captured")

    def test_aggregation_restores_original_case_order_even_if_viewports_are_interleaved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); manifest = self.manifest(root)
            cases = manifest["cases"]
            manifest["cases"] = [cases[index] for index in (0, 2, 4, 1, 3, 5)]
            result = shards.capture_shards(root / "manifest.json", manifest, Path("Relic"),
                lambda path, per_shard, exe: self.receipt(path, per_shard))
            self.assertEqual([row["case_id"] for row in result["cases"]], [case["id"] for case in manifest["cases"]])
            self.assertEqual(result["errors"], [])

    def test_timeout_partial_files_are_diagnostic_only_and_later_viewports_continue(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); manifest = self.manifest(root)
            def run(path, per_shard, exe):
                if per_shard["cases"][0]["width"] != 1440:
                    return self.receipt(path, per_shard)
                case = per_shard["cases"][0]
                (Path(per_shard["output"]) / case["file"]).write_bytes(b"partial actual transport fixture")
                (Path(per_shard["output"]) / (case["id"] + ".elements.json")).write_text("{}")
                (path.parent / "current-case.txt").write_text(case["id"])
                (path.parent / "progress-observations.json").write_text(json.dumps([
                    {"text": case["id"], "case_id": case["id"], "pid": 1234, "observed_monotonic": 1.0}]))
                (path.parent / "process-exit.json").write_text('{"pid":1234,"returncode":-9,"forced_kill":true}')
                raise TimeoutError("actual unchanged 1200-second process deadline")
            result = shards.capture_shards(root / "manifest.json", manifest, Path("Relic"), run)
            self.assertEqual(result["count"], 4)
            self.assertEqual(result["attempted_count"], 5)
            self.assertEqual(result["expected_count"], 6)
            self.assertEqual(result["cases"][0]["status"], "failed")
            self.assertEqual(result["cases"][1]["status"], "not-attempted")
            self.assertEqual(result["cases"][0]["artifacts_present"], {"png": True, "elements": True})
            self.assertIsNone(result["shards"][0]["native_receipt"])
            self.assertTrue(result["shards"][0]["cleanup_receipt"]["forced_kill"])
            self.assertIn("TimeoutError", (Path(result["shards"][0]["directory"]) / "capture-exception.log").read_text())

    def test_duplicate_missing_wrong_id_and_wrong_file_are_failures(self):
        for mutation in ("duplicate", "missing", "wrong-id", "wrong-file", "out-of-order"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); manifest = self.manifest(root)
                def run(path, per_shard, exe):
                    cases = per_shard["cases"]
                    rows = [{"id": case["id"], "file": case["file"], "status": "captured"} for case in cases]
                    if cases[0]["width"] == 1440:
                        if mutation == "duplicate": rows.append(dict(rows[0]))
                        elif mutation == "missing": rows.pop()
                        elif mutation == "wrong-id": rows[0]["id"] = "other-viewport-group"
                        elif mutation == "wrong-file": rows[0]["file"] = "wrong.png"
                        else: rows.reverse()
                    return self.receipt(path, per_shard, rows)
                result = shards.capture_shards(root / "manifest.json", manifest, Path("Relic"), run)
                self.assertTrue(result["errors"])
                self.assertEqual(len(result["shards"]), 3)
                self.assertEqual(result["shards"][-1]["status"], "captured")
                if mutation != "out-of-order": self.assertLess(result["count"], 6)

    def test_stale_viewport_directory_is_not_read_or_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); manifest = self.manifest(root)
            stale = root / "viewports" / "1440x900"; stale.mkdir(parents=True)
            stale_receipt = '{"count":55,"errors":[],"cases":[]}'
            (stale / "complete.json").write_text(stale_receipt)
            calls = []
            def run(path, per_shard, exe):
                calls.append(path.parent.name)
                return self.receipt(path, per_shard)
            result = shards.capture_shards(root / "manifest.json", manifest, Path("Relic"), run)
            self.assertEqual(calls, ["1280x800", "1024x700"])
            self.assertEqual(result["count"], 4)
            self.assertEqual(result["attempted_count"], 4)
            self.assertEqual((stale / "complete.json").read_text(), stale_receipt)
            self.assertIsNone(result["shards"][0]["native_receipt"])

    def test_preexisting_png_never_becomes_new_process_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); manifest = self.manifest(root)
            first = manifest["cases"][0]
            (Path(manifest["output"]) / first["file"]).write_bytes(b"stale")
            runner = Mock(side_effect=lambda path, per_shard, exe: self.receipt(path, per_shard))
            result = shards.capture_shards(root / "manifest.json", manifest, Path("Relic"), runner)
            self.assertEqual(runner.call_count, 2)
            self.assertEqual(result["count"], 4)
            self.assertFalse(result["shards"][0]["process_invoked"])
            self.assertIn("stale native viewport output", " ".join(result["errors"]))

    def test_missing_elements_or_failed_cleanup_cannot_pass(self):
        for failure in ("elements", "cleanup"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); manifest = self.manifest(root)
                def run(path, per_shard, exe):
                    source = self.receipt(path, per_shard)
                    if per_shard["cases"][0]["width"] == 1440:
                        if failure == "elements":
                            (Path(manifest["output"]) / (per_shard["cases"][0]["id"] + ".elements.json")).unlink()
                        else:
                            (path.parent / "process-exit.json").write_text('{"pid":1234,"status":"failed","error":"kill did not reap"}')
                    return source
                result = shards.capture_shards(root / "manifest.json", manifest, Path("Relic"), run)
                self.assertTrue(result["errors"])
                self.assertEqual(result["count"], 5 if failure == "elements" else 6)

    def test_manifest_duplicate_case_ids_are_rejected_before_any_process(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); manifest = self.manifest(root)
            manifest["cases"].append(dict(manifest["cases"][0]))
            with patch.object(capture, "native_process") as run:
                with self.assertRaisesRegex(ValueError, "unique"):
                    capture.native(root / "manifest.json", manifest, Path("Relic"))
                run.assert_not_called()

    def test_malformed_complete_receipt_does_not_stop_later_viewports(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); manifest = self.manifest(root)
            def run(path, per_shard, exe):
                source = self.receipt(path, per_shard)
                if per_shard["cases"][0]["width"] == 1440:
                    (path.parent / "complete.json").write_text('{"unfinished":')
                    raise ValueError("actual receipt JSON is incomplete")
                return source
            result = shards.capture_shards(root / "manifest.json", manifest, Path("Relic"), run)
            self.assertEqual(result["count"], 4)
            self.assertEqual(result["attempted_count"], 4, "PNG presence cannot invent actual attempted IDs")
            self.assertEqual(len(result["shards"]), 3)
            self.assertIn("Invalid native complete receipt", " ".join(result["errors"]))

    def test_swift_count_is_preserved_and_never_substituted_for_success_count(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); manifest = self.manifest(root)
            def run(path, per_shard, exe):
                source = self.receipt(path, per_shard)
                if per_shard["cases"][0]["width"] == 1440:
                    source["count"] = 55
                    (path.parent / "complete.json").write_text(json.dumps(source))
                return source
            result = shards.capture_shards(root / "manifest.json", manifest, Path("Relic"), run)
            self.assertEqual(result["count"], 6)
            self.assertEqual(result["shards"][0]["native_receipt"]["count"], 55)
            self.assertIn("count differs", " ".join(result["errors"]))

    def test_shards_refuse_non_ci_before_calling_runner(self):
        runner = Mock()
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
            with self.assertRaisesRegex(SystemExit, "CI-only"):
                shards.capture_shards(Path("unused"), {}, Path("Relic"), runner)
        runner.assert_not_called()

    def test_mac_native_timeout_keeps_1200_and_kills_then_reaps_owned_process(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); manifest = self.manifest(root, sizes=((1440, 900),))
            process = Mock(pid=6789, returncode=-9)
            process.poll.return_value = None
            process.wait.side_effect = [subprocess.TimeoutExpired("Relic", 20), -9]
            def wait(path, actual, timeout, on_tick, on_stall):
                self.assertIs(actual, process)
                self.assertEqual(timeout, 1200)
                case_id = manifest["cases"][0]["id"]
                (root / "current-case.txt").write_text(case_id)
                on_tick()
                raise TimeoutError("actual timeout fixture")
            with patch.object(capture.sys, "platform", "darwin"), patch.object(capture.subprocess, "Popen", return_value=process), \
                    patch.object(capture, "wait_file", side_effect=wait):
                with self.assertRaisesRegex(TimeoutError, "actual timeout fixture"):
                    capture.native_process(root / "manifest.json", manifest, Path("Relic"))
            process.terminate.assert_called_once(); process.kill.assert_called_once()
            self.assertEqual([call.kwargs["timeout"] for call in process.wait.call_args_list], [20, 10])
            cleanup = json.loads((root / "process-exit.json").read_text())
            self.assertEqual(cleanup, {"pid": 6789, "returncode": -9, "forced_kill": True})
            observed = json.loads((root / "progress-observations.json").read_text())
            self.assertEqual(observed[0]["case_id"], manifest["cases"][0]["id"])
            self.assertEqual(observed[0]["pid"], process.pid)


if __name__ == "__main__":
    unittest.main()
