"""Pure Windows capture lifecycle mocks. No app, reader or server is launched."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import capture


class WindowsCaptureProcessTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"GITHUB_ACTIONS": "true"})
        environment.start()
        self.addCleanup(environment.stop)

    def manifest(self, root, scenes=("group",)):
        return {"client": "windows", "output": str(root / "images"),
                "fixture": {"home": str(root / "shared-fixture"), "clock": "2026-10-29T11:02:00Z"},
                "uia_exe": "actual-reader.exe",
                "cases": [{"id": f"en-US-light-1440x900-{scene}", "scene": scene,
                           "width": 1440, "height": 900, "file": f"en-US-light-1440x900-{scene}.png"} for scene in scenes]}

    def test_all_50_cases_get_fresh_process_inputs_and_continue_after_menu_crash(self):
        scenes = json.loads((Path(capture.HERE) / "scenes.json").read_text(encoding="utf-8"))["scenes"]
        self.assertEqual(len(scenes), 50)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = self.manifest(root, scenes)
            original = copy.deepcopy(manifest)
            calls = []
            def run(path, per_case, exe):
                self.assertEqual(len(per_case["cases"]), 1)
                case = per_case["cases"][0]
                calls.append(case["scene"])
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")), per_case)
                self.assertEqual(per_case["fixture"]["home"], original["fixture"]["home"])
                self.assertEqual(per_case["output"], original["output"])
                state = Path(per_case["state_directory"])
                self.assertEqual(list(state.iterdir()), [], "No other case's seen/history/chat data is inherited")
                (state / "native-ui.json").write_text('{"seen":{"fixture":"one-case"}}')
                (path.parent / "current-case.txt").write_text("startup: loading organization and conversation")
                if case["scene"] == "menu-file":
                    (path.parent / "app-unhandled.jsonl").write_text('{"hresult":-2146500608}\n')
                    raise RuntimeError("real client crashed before completion")
                return {"count": 1, "errors": []}
            with patch.object(capture, "native_process", side_effect=run):
                result = capture.native(root / "manifest.json", manifest, Path("Relic.exe"))
            self.assertEqual(calls, scenes)
            self.assertEqual(calls[-1], "live-typing")
            self.assertEqual(result["expected_count"], 50)
            self.assertEqual(result["attempted_count"], 50)
            self.assertEqual(result["count"], 49)
            self.assertEqual(len(result["errors"]), 1)
            failed = next(row for row in result["cases"] if row["status"] == "failed")
            self.assertIn("loading organization", failed["last_progress"])
            self.assertTrue((Path(failed["directory"]) / "app-unhandled.jsonl").exists())
            self.assertIn("RuntimeError", (Path(failed["directory"]) / "capture-exception.log").read_text())
            self.assertEqual(json.loads((root / "complete.json").read_text()), result)
            self.assertEqual(manifest, original)

    def test_macos_keeps_one_existing_multi_case_process(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = self.manifest(root, ["group", "private"])
            manifest["client"] = "macos"
            with patch.object(capture, "native_process", return_value={"count": 2, "errors": []}) as run:
                capture.native(root / "manifest.json", manifest, Path("Relic"))
            run.assert_called_once_with(root / "manifest.json", manifest, Path("Relic"))
            self.assertFalse((root / "cases").exists())

    def test_direct_capture_entrypoints_refuse_local_launch(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), patch.object(capture.subprocess, "Popen") as launch:
            for entry in (capture.native, capture.native_process):
                with self.assertRaisesRegex(SystemExit, "CI-only"):
                    entry(Path("unused"), {}, Path("Relic.exe"))
            launch.assert_not_called()

    def test_owned_client_shutdown_escalates_to_kill_then_wait(self):
        process = Mock(pid=42, returncode=1)
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("Relic.exe", 20), 1]
        result = capture.stop_native_process(process)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual([call.kwargs["timeout"] for call in process.wait.call_args_list], [20, 10])
        self.assertTrue(result["forced_kill"])

    def run_single_mock(self, root, wrong_pid=False, reader_error=False):
        manifest = self.manifest(root)
        work = root / "one-process"
        work.mkdir()
        state = work / "state"
        state.mkdir()
        manifest["state_directory"] = str(state)
        output = Path(manifest["output"])
        output.mkdir()
        case = manifest["cases"][0]
        process = Mock(pid=4321, returncode=0)
        process.poll.return_value = None
        process.wait.return_value = 0
        def wait(path, actual_process, timeout, on_tick):
            self.assertIs(actual_process, process)
            self.assertEqual(timeout, 240)
            self.assertEqual((work / "current-case.txt").read_text(), "startup: launching native executable")
            queue = work / "element-requests"
            queue.mkdir()
            request = {"case_id": case["id"], "pid": 999 if wrong_pid else process.pid,
                       "hwnd": 123456, "origin": {"x": 0, "y": 0}, "width": 1440, "height": 900}
            (queue / (case["id"] + ".json")).write_text(json.dumps(request))
            (output / case["file"]).write_bytes(b"synthetic transport fixture")
            (output / (case["id"] + ".xaml.json")).write_text("{}")
            on_tick()
            return {"count": 1, "errors": []}
        def observe(arguments, **kwargs):
            request = json.loads(Path(arguments[arguments.index("--request") + 1]).read_text())
            self.assertEqual(request["pid"], process.pid)
            self.assertEqual(request["hwnd"], 123456, "Never replace the actual native HWND")
            Path(arguments[arguments.index("--output") + 1]).write_text('{"raw_nodes":[]}')
            return SimpleNamespace(returncode=1 if reader_error else 0, stdout="real reader stdout fixture", stderr="provider error" if reader_error else "")
        projector = Mock(return_value={"elements": [], "extraction_errors": []})
        with patch.object(capture.subprocess, "Popen", return_value=process) as launch, \
                patch.object(capture.subprocess, "run", side_effect=observe) as observer, \
                patch.object(capture, "wait_file", side_effect=wait), \
                patch.dict("sys.modules", {"windows_elements": SimpleNamespace(project=projector)}):
            if wrong_pid or reader_error:
                with self.assertRaisesRegex(RuntimeError, "not bound" if wrong_pid else "UIA capture failed"):
                    capture.native_process(work / "manifest.json", manifest, Path("Relic.exe"))
            else:
                self.assertEqual(capture.native_process(work / "manifest.json", manifest, Path("Relic.exe"))["count"], 1)
            self.assertEqual(launch.call_args.kwargs["env"]["RELIC_VISUAL_STATE_DIR"], str(state))
            self.assertEqual(launch.call_args.kwargs["env"]["RELIC_HOME"], manifest["fixture"]["home"])
            process.terminate.assert_called_once()
            process.wait.assert_called_once_with(timeout=20)
            if wrong_pid:
                observer.assert_not_called()
                projector.assert_not_called()
            else:
                observer.assert_called_once()
                self.assertTrue((work / "element-receipts" / (case["id"] + ".json")).exists())
                self.assertTrue((output / (case["id"] + ".elements.json")).exists())
            self.assertEqual(json.loads((work / "process-exit.json").read_text())["pid"], process.pid)

    def test_actual_case_pid_and_hwnd_remain_bound_to_independent_reader(self):
        with tempfile.TemporaryDirectory() as folder:
            self.run_single_mock(Path(folder))

    def test_foreign_request_cannot_be_acknowledged_or_observed(self):
        with tempfile.TemporaryDirectory() as folder:
            self.run_single_mock(Path(folder), wrong_pid=True)

    def test_reader_failure_preserves_evidence_and_receipt_but_fails_case(self):
        with tempfile.TemporaryDirectory() as folder:
            self.run_single_mock(Path(folder), reader_error=True)

    def test_main_writes_failed_aggregate_then_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "capture"
            fixture = {"home": str(Path(folder) / "server"), "port": 5555, "token": "fixture-token"}
            server = Mock()
            args = ["capture.py", "--client", "windows", "--matrix", "smoke", "--lang", "en-US", "--theme", "light",
                    "--exe", "Relic.exe", "--uia-exe", "reader.exe", "--output", str(output)]
            with patch("sys.argv", args), patch.object(capture.subprocess, "Popen", return_value=server), \
                    patch.object(capture, "wait_file", return_value=fixture), patch.object(capture, "configure"), \
                    patch.object(capture, "native", return_value={"count": 6, "errors": ["copies: actual crash"]}) as native_runner:
                with self.assertRaisesRegex(RuntimeError, "Windows capture failed"):
                    capture.main()
            receipt = json.loads((output / "capture-complete-en-US-light.json").read_text())
            cases = native_runner.call_args.args[1]["cases"]
            self.assertTrue({"copies", "menu-file", "file-code", "live-tool-output", "live-typing"}
                            <= {case["scene"] for case in cases})
            self.assertEqual(receipt["count"], 6)
            self.assertEqual(receipt["expected_count"], len(cases))
            self.assertGreater(receipt["expected_count"], receipt["count"])
            self.assertEqual(receipt["errors"], ["copies: actual crash"])
            server.terminate.assert_called_once()
            server.wait.assert_called_once_with(timeout=20)


if __name__ == "__main__":
    unittest.main()
