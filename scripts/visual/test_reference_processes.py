"""Reference worker lifecycle fixtures; every process/browser operation is mocked."""
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


class ReferenceProcessTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"GITHUB_ACTIONS": "true"})
        environment.start(); self.addCleanup(environment.stop)

    def manifest(self, root, scenes=("group",)):
        return {"client": "reference", "output": str(root / "images"), "lang": "zh-CN", "theme": "light",
            "fixture": {"home": "same-server-fixture", "port": 7777, "token": "fixture-token"},
            "cases": [{"id": "case-" + scene, "scene": scene, "file": "case-" + scene + ".png", "width": 1440, "height": 900} for scene in scenes]}

    def write_manifest(self, root):
        manifest = self.manifest(root)
        Path(manifest["output"]).mkdir()
        path = root / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path, manifest

    def test_every_manifest_case_is_attempted_after_copy_timeout_without_inventing_count(self):
        scenes = json.loads((capture.HERE / "scenes.json").read_text(encoding="utf-8"))["scenes"]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); manifest = self.manifest(root, scenes); original = copy.deepcopy(manifest)
            calls = []
            def run(path, per_case):
                self.assertEqual(len(per_case["cases"]), 1)
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")), per_case)
                self.assertEqual(per_case["fixture"], original["fixture"])
                self.assertEqual(per_case["output"], original["output"])
                case = per_case["cases"][0]; calls.append(case["scene"])
                if case["scene"] == "message-copy-toast":
                    return {"case": case["id"], "status": "failed", "count": 0,
                        "errors": ["Actual screenshot deadline"], "timed_out": True}
                return {"case": case["id"], "status": "captured", "count": 1, "errors": []}
            with patch.object(capture, "reference_process", side_effect=run):
                result = capture.reference(manifest)
            self.assertEqual(calls, scenes)
            self.assertGreater(calls.index("panel-resized"), calls.index("message-copy-toast"))
            self.assertEqual(result["count"], len(scenes) - 1)
            self.assertEqual(result["attempted_count"], len(scenes))
            self.assertEqual(result["expected_count"], len(scenes))
            self.assertEqual(result["errors"], ["case-message-copy-toast: Actual screenshot deadline"])
            self.assertEqual(json.loads((root / "images/data/zh-CN/light/complete.json").read_text(encoding="utf-8")), result)
            self.assertEqual(manifest, original)

    def test_timeout_keeps_exact_pending_step_before_tree_cleanup_and_is_not_a_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); path, manifest = self.write_manifest(root)
            action_path = Path(manifest["output"]) / "case-group.scene-action.json"
            step = {"step": "screenshot:Page.captureScreenshot", "status": "started", "host_monotonic": 2156.078}
            action_path.write_text(json.dumps({"steps": [step], "checkpoints": [{"stage": "before_screenshot"}]}))
            process = Mock(pid=1234, returncode=None)
            process.wait.side_effect = subprocess.TimeoutExpired("actual worker", 90)
            def cleanup(actual):
                self.assertIs(actual, process)
                saved = json.loads((root / "process-receipt.json").read_text(encoding="utf-8"))
                self.assertTrue(saved["timed_out"]); self.assertEqual(saved["last_action_step"], step)
                self.assertEqual(saved["deadline_host_monotonic"] - saved["started_host_monotonic"], 90)
                return {"pid": 1234, "returncode": -1, "tree_termination": True, "errors": []}
            with patch.object(capture.subprocess, "Popen", return_value=process) as launch, \
                    patch.object(capture, "stop_reference_worker", side_effect=cleanup) as stop, \
                    patch.object(capture, "creation_flags", return_value=0x08000000):
                result = capture.reference_process(path, manifest)
            self.assertEqual(result["count"], 0); self.assertEqual(result["status"], "failed")
            self.assertTrue(result["timed_out"]); self.assertTrue(result["cleanup"]["tree_termination"])
            self.assertEqual(result["completed_checkpoints"], ["before_screenshot"])
            self.assertEqual(launch.call_args.kwargs["creationflags"], 0x08000000)
            self.assertEqual(launch.call_args.args[0][-2:], ["--reference-worker", str(path)])
            self.assertLessEqual(process.wait.call_args.kwargs["timeout"], 90)
            stop.assert_called_once_with(process)
            self.assertEqual(json.loads(action_path.read_text())["steps"], [step], "Timeout never rewrites completed action evidence")

    def test_only_actual_matching_worker_pid_case_and_completion_count_are_accepted(self):
        for wrong in (None, "pid", "case", "count", "status", "errors"):
            with self.subTest(wrong=wrong), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); path, manifest = self.write_manifest(root)
                worker = {"pid": 1234, "case": "case-group", "status": "captured", "count": 1, "errors": []}
                if wrong is not None:
                    worker[wrong] = {"pid": 999, "case": "stale-case", "count": 0, "status": "started", "errors": ["actual failure"]}[wrong]
                (root / "worker-complete.json").write_text(json.dumps(worker))
                process = Mock(pid=1234, returncode=0)
                with patch.object(capture.subprocess, "Popen", return_value=process), \
                        patch.object(capture, "stop_reference_worker", return_value={"pid": 1234, "errors": []}):
                    result = capture.reference_process(path, manifest)
                self.assertEqual(result["count"], 1 if wrong is None else 0)
                self.assertEqual(result["status"], "captured" if wrong is None else "failed")

    def test_missing_worker_receipt_cannot_pass_due_to_existing_png(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); path, manifest = self.write_manifest(root)
            (Path(manifest["output"]) / "case-group.png").write_bytes(b"partial artifact fixture")
            process = Mock(pid=1234, returncode=0)
            with patch.object(capture.subprocess, "Popen", return_value=process), \
                    patch.object(capture, "stop_reference_worker", return_value={"pid": 1234, "errors": []}):
                result = capture.reference_process(path, manifest)
            self.assertEqual(result["count"], 0); self.assertTrue(result["errors"])

    def test_windows_cleanup_targets_only_actual_owned_pid_and_reaps(self):
        process = Mock(pid=4578, returncode=1); process.poll.return_value = None
        with patch.object(capture.sys, "platform", "win32"), \
                patch.object(capture.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="Actual termination", stderr="")) as run, \
                patch.object(capture, "creation_flags", return_value=0x08000000):
            result = capture.stop_reference_worker(process)
        run.assert_called_once_with(["taskkill.exe", "/PID", "4578", "/T", "/F"],
            capture_output=True, text=True, timeout=10, creationflags=0x08000000)
        process.wait.assert_called_once_with(timeout=10)
        self.assertTrue(result["tree_termination"]); self.assertEqual(result["errors"], [])

    def test_posix_cleanup_kills_only_the_owned_new_session_group(self):
        process = Mock(pid=4578, returncode=-9); process.poll.return_value = None
        with patch.object(capture.sys, "platform", "darwin"), patch.object(capture.os, "killpg", create=True) as killpg:
            result = capture.stop_reference_worker(process)
        killpg.assert_called_once_with(4578, getattr(capture.signal, "SIGKILL", 9))
        process.wait.assert_called_once_with(timeout=10)
        self.assertEqual(result["signal"], "SIGKILL owned new session")

    def test_already_exited_worker_is_reaped_without_killing_a_reused_pid(self):
        process = Mock(pid=4578, returncode=0); process.poll.return_value = 0
        with patch.object(capture.subprocess, "run") as run, patch.object(capture.os, "killpg", create=True) as killpg:
            result = capture.stop_reference_worker(process)
        run.assert_not_called(); killpg.assert_not_called()
        process.wait.assert_called_once_with(timeout=10)
        self.assertFalse(result["tree_termination"])

    def test_failed_tree_cleanup_is_recorded_and_root_fallback_does_not_claim_tree_success(self):
        process = Mock(pid=4578, returncode=1); process.poll.return_value = None
        with patch.object(capture.sys, "platform", "win32"), patch.object(capture.subprocess, "run", side_effect=FileNotFoundError("taskkill unavailable")):
            result = capture.stop_reference_worker(process)
        self.assertEqual(result["errors"], ["taskkill unavailable"])
        self.assertTrue(result["root_only_fallback"])
        process.kill.assert_called_once_with()

    def test_worker_success_or_exception_has_explicit_case_receipt(self):
        for failed in (False, True):
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); path, _ = self.write_manifest(root)
                with patch.object(capture, "reference_browser", side_effect=RuntimeError("actual browser error") if failed else None):
                    result = capture.reference_worker(path)
                self.assertEqual(result["status"], "failed" if failed else "captured")
                self.assertEqual(result["count"], 0 if failed else 1)
                self.assertEqual(result["pid"], os.getpid())
                self.assertEqual(json.loads((root / "worker-complete.json").read_text(encoding="utf-8")), result)
                self.assertEqual((root / "worker-exception.log").exists(), failed)

    def test_all_reference_launch_and_cleanup_entrypoints_refuse_local_use(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), patch.object(capture.subprocess, "Popen") as launch, \
                patch.object(capture.subprocess, "run") as run:
            for action in (lambda: capture.reference({}), lambda: capture.reference_browser({}),
                           lambda: capture.reference_worker(Path("unused")), lambda: capture.reference_process(Path("unused"), {}),
                           lambda: capture.stop_reference_worker(Mock())):
                with self.assertRaisesRegex(SystemExit, "CI-only"):
                    action()
            launch.assert_not_called(); run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
