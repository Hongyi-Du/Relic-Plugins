"""Pure stall diagnostics fixtures. No sample, native app, server or process runs."""
import json
import subprocess
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import capture


class NativeStallCaptureTests(unittest.TestCase):
    def test_mac_without_lifecycle_progress_is_sampled_at_existing_progress_deadline(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder); clock = [0]; events = []
            marker = "startup: launching native executable"
            process = Mock(pid=8765, returncode=0); process.poll.return_value = None
            process.terminate.side_effect = lambda: events.append("terminate")
            manifest = {"client": "macos", "output": folder,
                        "fixture": {"home": folder, "clock": "2026-10-29T11:02:00Z"},
                        "cases": [{"id": "case", "file": "case.png"}]}
            def launch(*args, **kwargs):
                self.assertEqual((directory / "current-case.txt").read_text(), marker)
                events.append("launch")
                return process
            def sleep(_):
                clock[0] += 31
            def sample(actual, target, client, reason):
                self.assertIs(actual, process); self.assertEqual(target, directory)
                self.assertEqual(client, "macos"); self.assertEqual(clock[0], 93)
                self.assertIn(marker, reason); process.terminate.assert_not_called()
                events.append("sample")
                return {"status": "sample_collected", "capture_failed": True}
            with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}), \
                    patch.object(capture.sys, "platform", "darwin"), \
                    patch.object(capture.subprocess, "Popen", side_effect=launch), \
                    patch.object(capture.time, "monotonic", side_effect=lambda: clock[0]), \
                    patch.object(capture.time, "sleep", side_effect=sleep), \
                    patch.object(capture, "sample_native_stall", side_effect=sample):
                with self.assertRaisesRegex(TimeoutError, "did not advance for 90 seconds: startup"):
                    capture.native_process(directory / "manifest.json", manifest, Path("Relic"))
            self.assertEqual(events, ["launch", "sample", "terminate"])
            self.assertEqual(clock[0], 93)
            process.wait.assert_called_once_with(timeout=20)
            observations = json.loads((directory / "progress-observations.json").read_text())
            self.assertEqual(len(observations), 1)
            self.assertIsNone(observations[0]["case_id"], "A host startup marker is not a native scene attempt")
            self.assertFalse((directory / "complete.json").exists())

    def test_sample_never_starts_outside_ci_darwin_native_client(self):
        for ci, platform, client in (("false", "darwin", "macos"), ("true", "win32", "macos"),
                                     ("true", "linux", "macos"), ("true", "darwin", "windows")):
            with self.subTest(ci=ci, platform=platform, client=client), tempfile.TemporaryDirectory() as folder:
                process = Mock(pid=456)
                with patch.dict("os.environ", {"GITHUB_ACTIONS": ci}), patch.object(capture.sys, "platform", platform), \
                        patch.object(capture.subprocess, "run") as run:
                    result = capture.sample_native_stall(process, Path(folder), client, "timeout")
                self.assertEqual(result["status"], "not_applicable")
                run.assert_not_called(); process.poll.assert_not_called()
                self.assertEqual(list(Path(folder).iterdir()), [])

    def test_sample_uses_actual_owned_pid_three_seconds_and_eight_second_deadline(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder); process = Mock(pid=4321); process.poll.return_value = None
            original = "Actual sample fixture\nThread 0: real-stack-record\n"
            def run(command, **kwargs):
                self.assertEqual(command, ["/usr/bin/sample", "4321", "3", "-file", str(directory / "native-stall.sample.txt")])
                self.assertEqual(kwargs, {"timeout": 8, "capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace"})
                process.terminate.assert_not_called()
                (directory / "native-stall.sample.txt").write_text(original, encoding="utf-8")
                return SimpleNamespace(returncode=0, stdout="Actual tool stdout", stderr="Actual tool stderr")
            with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}), patch.object(capture.sys, "platform", "darwin"), \
                    patch.object(capture.subprocess, "run", side_effect=run):
                result = capture.sample_native_stall(process, directory, "macos", "90 seconds: live-tool-output")
            self.assertEqual(result["status"], "sample_collected")
            self.assertTrue(result["sample_written_by_tool"])
            self.assertTrue(result["capture_failed"], "A collected sample cannot repair the capture timeout")
            self.assertEqual(result["progress_timeout_seconds"], 90)
            self.assertEqual((directory / "native-stall.sample.txt").read_text(), original)
            self.assertEqual(json.loads((directory / "native-stall.sample.json").read_text()), result)
            process.terminate.assert_not_called()

    def test_sample_timeout_preserves_partial_real_report_and_remains_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder); process = Mock(pid=4321); process.poll.return_value = None
            def run(command, **kwargs):
                (directory / "native-stall.sample.txt").write_bytes(b"Partial actual stack\n")
                raise subprocess.TimeoutExpired(command, 8, output=b"partial stdout", stderr=b"partial stderr")
            with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}), patch.object(capture.sys, "platform", "darwin"), \
                    patch.object(capture.subprocess, "run", side_effect=run):
                result = capture.sample_native_stall(process, directory, "macos", "stalled")
            self.assertEqual(result["status"], "timeout")
            self.assertEqual(result["stdout"], "partial stdout")
            self.assertEqual(result["stderr"], "partial stderr")
            self.assertTrue(result["sample_written_by_tool"])
            self.assertEqual((directory / "native-stall.sample.txt").read_bytes(), b"Partial actual stack\n")

    def test_failed_sampler_output_is_not_mislabeled_as_a_stack_report(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder); process = Mock(pid=4321); process.poll.return_value = None
            with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}), patch.object(capture.sys, "platform", "darwin"), \
                    patch.object(capture.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout="", stderr="Actual sample permission failure\n")):
                result = capture.sample_native_stall(process, directory, "macos", "stalled")
            self.assertEqual(result["status"], "failed")
            self.assertFalse(result["sample_written_by_tool"])
            self.assertIn("no stack report", result["sample_file_quantity"])
            self.assertEqual((directory / "native-stall.sample.txt").read_text(), "Actual sample permission failure\n")

    def test_exited_process_is_not_sampled_by_reusing_its_pid(self):
        with tempfile.TemporaryDirectory() as folder:
            process = Mock(pid=4321); process.poll.return_value = 1
            with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}), patch.object(capture.sys, "platform", "darwin"), \
                    patch.object(capture.subprocess, "run") as run:
                result = capture.sample_native_stall(process, Path(folder), "macos", "stalled")
            run.assert_not_called()
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["process_returncode_before_sample"], 1)

    def test_progress_callback_does_not_reset_ninety_second_failure_even_if_progress_changes(self):
        for raises in (False, True):
            with self.subTest(raises=raises), tempfile.TemporaryDirectory() as folder:
                directory = Path(folder)
                (directory / "current-case.txt").write_text("case: actual-input")
                process = Mock(); process.poll.return_value = None
                clock = [0]
                def sleep(_):
                    clock[0] += 31
                def diagnostic(reason):
                    self.assertEqual(clock[0], 93)
                    self.assertIn("actual-input", reason)
                    (directory / "current-case.txt").write_text("case: changed-during-diagnostic")
                    if raises:
                        raise RuntimeError("sample failure fixture")
                callback = Mock(side_effect=diagnostic)
                with patch.object(capture.time, "monotonic", side_effect=lambda: clock[0]), patch.object(capture.time, "sleep", side_effect=sleep):
                    with self.assertRaisesRegex(TimeoutError, "did not advance for 90 seconds: case: actual-input") as error:
                        capture.wait_file(directory / "complete.json", process, timeout=1200, on_stall=callback)
                callback.assert_called_once()
                self.assertEqual(clock[0], 93)
                if raises:
                    self.assertIn("sample failure fixture", str(error.exception))

    def test_fixture_server_wait_has_no_native_progress_callback(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "current-case.txt").write_text("unrelated native progress")
            process = Mock(); process.poll.return_value = None
            clock = [0]
            def sleep(_):
                clock[0] += 100
            callback = Mock()
            with patch.object(capture.time, "monotonic", side_effect=lambda: clock[0]), patch.object(capture.time, "sleep", side_effect=sleep):
                with self.assertRaises(TimeoutError):
                    capture.wait_file(directory / "fixture.json", process, timeout=150, on_stall=callback)
            callback.assert_not_called()

    def test_native_mac_monitor_samples_before_termination_then_preserves_timeout(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder); events = []
            process = Mock(pid=8765, returncode=0); process.poll.return_value = None
            process.terminate.side_effect = lambda: events.append("terminate")
            manifest = {"client": "macos", "output": folder, "fixture": {"home": folder, "clock": "2026-10-29T11:02:00Z"},
                        "cases": [{"id": "case", "file": "case.png"}]}
            def wait(path, actual, timeout, on_tick, on_stall):
                self.assertIs(actual, process); self.assertEqual(timeout, 1200)
                events.append("timeout")
                on_stall("Native capture did not advance for 90 seconds: case")
                raise TimeoutError("Native capture did not advance for 90 seconds: case")
            def sample(actual, target, client, reason):
                self.assertIs(actual, process); self.assertEqual(target, directory); self.assertEqual(client, "macos")
                process.terminate.assert_not_called(); events.append("sample")
                return {"status": "timeout", "capture_failed": True}
            with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}), patch.object(capture.sys, "platform", "darwin"), \
                    patch.object(capture.subprocess, "Popen", return_value=process), patch.object(capture, "wait_file", side_effect=wait), \
                    patch.object(capture, "sample_native_stall", side_effect=sample):
                with self.assertRaisesRegex(TimeoutError, "90 seconds"):
                    capture.native_process(directory / "manifest.json", manifest, Path("Relic"))
            self.assertEqual(events, ["timeout", "sample", "terminate"])
            process.wait.assert_called_once_with(timeout=20)


if __name__ == "__main__":
    unittest.main()
