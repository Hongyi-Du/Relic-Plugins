"""Pure process/clock/receipt fixtures; no UIA or native executable runs."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import uia_observer


class UIAObserverTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"GITHUB_ACTIONS": "true"})
        environment.start(); self.addCleanup(environment.stop)

    def fixture(self, directory):
        request = directory / "case.json"
        request.write_text(json.dumps({"case_id": "case", "pid": 1234, "hwnd": 5678}))
        output = directory / "case.uia.json"
        client = Mock(pid=1234); client.poll.return_value = None
        worker = Mock(pid=4321); worker.poll.return_value = None; worker.wait.return_value = 0
        return request, output, client, worker

    def test_actual_observer_is_alive_until_native_observation_and_original_error_survives(self):
        for code in (0, 1):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); request, output, client, worker = self.fixture(root)
                worker.wait.return_value = code
                original = '{"raw_nodes":[],"extraction_errors":["actual fixture failure"]}'
                clock = [100.0]
                def launch(command, **kwargs):
                    self.assertEqual(command[:5], ["observer.exe", "--request", str(request), "--output", str(output)])
                    output.write_text(original)
                    ready = Path(command[command.index("--hold-ready") + 1])
                    ready.write_text(json.dumps({"case_id": "case", "app_pid": 1234,
                        "observer_pid": worker.pid, "exit_code": code}))
                    kwargs["stdout"].write("actual observer output")
                    clock[0] += 4
                    return worker
                def observed(receipt, deadline):
                    self.assertEqual(receipt["observer_pid"], worker.pid)
                    self.assertEqual(deadline, 175)
                    self.assertFalse(output.with_name(output.name + ".observer-release.json").exists())
                    worker.wait.assert_not_called(); worker.kill.assert_not_called()
                    clock[0] += 6
                with patch.object(uia_observer.subprocess, "Popen", side_effect=launch), \
                        patch.object(uia_observer.time, "monotonic", side_effect=lambda: clock[0]):
                    result = uia_observer.observe("observer.exe", request, output, client, observed)
                self.assertEqual(result.returncode, code)
                self.assertEqual(result.stdout, "actual observer output")
                self.assertEqual(output.read_text(), original)
                worker.wait.assert_called_once_with(timeout=65)
                released = json.loads(output.with_name(output.name + ".observer-release.json").read_text())
                self.assertEqual(released, {"case_id": "case", "observer_pid": 4321,
                                          "action": "release", "status": "observed"})

    def test_foreign_ready_cannot_trigger_native_observation_and_worker_is_released(self):
        for changed in ({"case_id": "other"}, {"app_pid": 999}, {"observer_pid": 999}, {"exit_code": False}):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); request, output, client, worker = self.fixture(root)
                def launch(command, **kwargs):
                    output.write_text("{}")
                    value = {"case_id": "case", "app_pid": 1234, "observer_pid": 4321, "exit_code": 0}
                    value.update(changed)
                    Path(command[command.index("--hold-ready") + 1]).write_text(json.dumps(value))
                    return worker
                callback = Mock()
                with patch.object(uia_observer.subprocess, "Popen", side_effect=launch):
                    with self.assertRaisesRegex(RuntimeError, "not bound"):
                        uia_observer.observe("observer.exe", request, output, client, callback)
                callback.assert_not_called(); worker.wait.assert_called_once()
                self.assertEqual(json.loads(output.with_name(output.name + ".observer-release.json").read_text())["status"], "failed")

    def test_deadline_is_not_restarted_when_waiting_for_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); request, output, client, worker = self.fixture(root)
            clock = [0]
            def sleep(_): clock[0] += 25
            callback = Mock()
            with patch.object(uia_observer.subprocess, "Popen", return_value=worker), \
                    patch.object(uia_observer.time, "monotonic", side_effect=lambda: clock[0]), \
                    patch.object(uia_observer.time, "sleep", side_effect=sleep):
                with self.assertRaises(subprocess.TimeoutExpired) as failed:
                    uia_observer.observe("observer.exe", request, output, client, callback)
            self.assertEqual(failed.exception.timeout, 75)
            self.assertEqual(clock[0], 75); callback.assert_not_called()
            worker.kill.assert_called_once(); worker.wait.assert_called_once_with(timeout=10)

    def test_native_receipt_requires_both_actual_processes_and_observed_status(self):
        for changed in ({}, {"case_id": "other"}, {"app_pid": 999}, {"observer_pid": 999}, {"status": "failed"}):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "native.json"
                value = {"case_id": "case", "app_pid": 1234, "observer_pid": 4321, "status": "observed"}
                value.update(changed); path.write_text(json.dumps(value))
                client = Mock(pid=1234); client.poll.return_value = None
                with patch.object(uia_observer.time, "monotonic", return_value=5):
                    if changed:
                        with self.assertRaisesRegex(RuntimeError, "not bound"):
                            uia_observer.wait_native_probe_receipt(path, {"case_id": "case"}, 4321, client, 75)
                    else:
                        self.assertEqual(uia_observer.wait_native_probe_receipt(path, {"case_id": "case"}, 4321, client, 75), value)

    def test_local_entry_refuses_before_any_process_or_file_read(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), \
                patch.object(uia_observer.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(SystemExit, "CI-only"):
                uia_observer.observe("unused", "unused", "unused", Mock(), Mock())
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
