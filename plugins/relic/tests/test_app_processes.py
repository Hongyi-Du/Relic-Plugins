"""Owned naming/digest/install jobs: fake local processes only, no models or package downloads."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import acp, explain, naming, processes, web  # noqa: E402


TREE = r'''
import json, os, signal, subprocess, sys, time
from pathlib import Path
folder, role, mode = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
signal.signal(signal.SIGTERM, lambda *_: None)
(folder / (role + ".pid")).write_text(str(os.getpid()))
if role == "parent":
    child = subprocess.Popen([sys.executable, "-B", __file__, str(folder), "child", mode])
    while not (folder / "child.pid").exists(): time.sleep(.01)
    print("ready", flush=True)
    if mode == "exit-parent": os._exit(0)
while True: time.sleep(.05)
'''


def wait_for(check, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("job fixture timed out")


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    if sys.platform == "darwin":
        state = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True, timeout=1)
        return state.returncode == 0 and bool(state.stdout.strip()) and not state.stdout.strip().startswith("Z")
    if sys.platform.startswith("linux"):
        try:
            return Path("/proc/%d/stat" % pid).read_text().split(")", 1)[1].split()[0] != "Z"
        except FileNotFoundError:
            return False
    return True


class GroupSignals(unittest.TestCase):
    def test_successful_probe_only_finishes_for_confirmed_zombie_group(self):
        for output, stopped in (("4321 Z\n9876 S\n", True), ("4321 S\n", False), ("unknown\n", False)):
            with self.subTest(output=output), \
                    mock.patch.object(processes.os, "killpg", create=True), \
                    mock.patch.object(processes.os, "getpgrp", create=True, return_value=9876), \
                    mock.patch.object(processes.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=output)):
                process = mock.Mock(pid=4321)
                process.poll.return_value = 0
                child = processes._Child(process)
                child.group = 4321
                self.assertEqual(child.wait(0), stopped)
                agent = acp.AcpAgent(["fixture"])
                agent.proc, agent._owned_pgid = process, 4321
                self.assertEqual(agent._wait_for_exit(0), stopped)

    def test_darwin_zombie_only_or_disappeared_group_is_not_alive(self):
        for output in ("4321 Z\n4321 Z+\n9876 S\n", "9876 S\n"):
            for sig in (0, signal.SIGTERM, 9):
                with self.subTest(output=output, signal=sig), \
                        mock.patch.object(processes.sys, "platform", "darwin"), \
                        mock.patch.object(processes.os, "killpg", create=True, side_effect=PermissionError(1, "denied")), \
                        mock.patch.object(processes.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=output)):
                    self.assertFalse(processes.signal_group(4321, sig))

    def test_denied_live_group_and_inconclusive_snapshot_still_raise(self):
        snapshots = [SimpleNamespace(returncode=0, stdout="4321 Z\n4321 S\n"),
                     SimpleNamespace(returncode=0, stdout="unparseable\n"),
                     SimpleNamespace(returncode=0, stdout=""),
                     SimpleNamespace(returncode=1, stdout=""),
                     OSError("cannot inspect"), subprocess.TimeoutExpired("ps", 1)]
        for snapshot in snapshots:
            with self.subTest(snapshot=snapshot), \
                    mock.patch.object(processes.sys, "platform", "darwin"), \
                    mock.patch.object(processes.os, "killpg", create=True, side_effect=PermissionError(1, "denied")), \
                    mock.patch.object(processes.subprocess, "run") as inspect:
                if isinstance(snapshot, Exception):
                    inspect.side_effect = snapshot
                else:
                    inspect.return_value = snapshot
                with self.assertRaises(PermissionError):
                    processes.signal_group(4321, 9)

    @unittest.skipUnless(sys.platform == "darwin", "XNU zombie-only process group behavior")
    def test_real_unreaped_zombie_group_can_finish_cleanup(self):
        # Keep the zombie's parent outside the owned group, so it deliberately
        # remains unreaped until we have exercised Darwin's EPERM behavior.
        code = ("import subprocess,sys; "
                "child=subprocess.Popen([sys.executable,'-B','-c','pass'],start_new_session=True); "
                "print(child.pid,flush=True); sys.stdin.readline(); child.wait()")
        parent = subprocess.Popen([sys.executable, "-B", "-c", code], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            pgid = int(parent.stdout.readline())
            wait_for(lambda: processes.group_has_live_members(pgid) is False)
            with self.assertRaises(PermissionError):
                os.killpg(pgid, 0)
            for sig in (0, signal.SIGTERM, signal.SIGKILL):
                self.assertFalse(processes.signal_group(pgid, sig))
        finally:
            parent.communicate("reap\n", timeout=5)


class Registry(unittest.TestCase):
    def setUp(self):
        self.registry = processes.ProcessRegistry()
        self.addCleanup(self.registry.shutdown)

    def test_run_preserves_output_input_and_exit_checks(self):
        result = self.registry.run([sys.executable, "-B", "-c", "import sys;print(sys.stdin.read().upper());print('err',file=sys.stderr)"],
                                   input="fixture", capture_output=True, text=True, timeout=5, check=True)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "FIXTURE\n", "err\n"))
        self.assertEqual(self.registry._children, {})
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.registry.run([sys.executable, "-B", "-c", "import sys;print('failed');sys.exit(7)"],
                              capture_output=True, text=True, check=True)
        self.assertEqual((caught.exception.returncode, caught.exception.stdout), (7, "failed\n"))
        self.assertEqual(self.registry._children, {})

    def test_shutdown_forbids_new_jobs_without_spawning(self):
        self.registry.begin_shutdown()
        with mock.patch.object(processes.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(RuntimeError, "stopping"):
                self.registry.popen(["never-started"])
            popen.assert_not_called()

    def test_spawn_failure_leaves_no_owned_job(self):
        with mock.patch.object(processes.subprocess, "Popen", side_effect=OSError("not found")):
            with self.assertRaises(OSError):
                self.registry.popen(["missing"])
        self.assertEqual(self.registry._children, {})

    @unittest.skipIf(os.name == "nt", "POSIX owned process groups")
    def test_failed_group_shutdown_keeps_job_open_for_retry(self):
        process = mock.Mock(pid=4321)
        child = processes._Child(process)
        with mock.patch.object(child, "active", return_value=True), \
                mock.patch.object(child, "signal_group") as signal_group, \
                mock.patch.object(child, "wait", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "process group.*shutdown deadline"):
                child.close()
        self.assertFalse(child.closed)
        process.wait.assert_not_called()
        self.assertEqual(signal_group.call_args_list, [mock.call(signal.SIGTERM), mock.call(signal.SIGKILL)])
        with mock.patch.object(child, "active", return_value=False):
            child.close()
        self.assertTrue(child.closed)

    def test_windows_cleanup_targets_only_a_live_owned_child(self):
        process = mock.Mock(pid=4321)
        process.poll.return_value = None
        process.wait.return_value = 0
        with mock.patch.object(processes, "os", SimpleNamespace(name="nt")), \
                mock.patch.object(processes.subprocess, "run", return_value=SimpleNamespace(returncode=1)) as run:
            child = processes._Child(process)
            child.close()
            child.close()
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["taskkill", "/T", "/F", "/PID", "4321"])
        process.kill.assert_called_once_with()
        exited = mock.Mock(pid=4322)
        exited.poll.return_value = 0
        with mock.patch.object(processes, "os", SimpleNamespace(name="nt")), \
                mock.patch.object(processes.subprocess, "run") as run:
            processes._Child(exited).close()
        run.assert_not_called()
        exited.kill.assert_not_called()

    @unittest.skipIf(os.name == "nt", "POSIX spawn/shutdown race fixture")
    def test_shutdown_during_spawn_cannot_miss_the_new_child(self):
        entered, release = threading.Event(), threading.Event()
        real_popen = subprocess.Popen
        children = []

        def delayed(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(3))
            return real_popen(*args, **kwargs)

        with mock.patch.object(processes.subprocess, "Popen", side_effect=delayed):
            starter = threading.Thread(target=lambda: children.append(self.registry.popen(
                [sys.executable, "-B", "-c", "import time;time.sleep(30)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)))
            starter.start()
            self.assertTrue(entered.wait(2))
            closer = threading.Thread(target=self.registry.shutdown)
            closer.start()
            release.set()
            starter.join(5)
            closer.join(5)
        self.assertFalse(starter.is_alive() or closer.is_alive())
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.registry.release(children[0])


@unittest.skipIf(os.name == "nt", "POSIX owned process groups")
class ProcessTrees(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="relic-app-jobs-")
        self.addCleanup(self.temp.cleanup)
        self.registry = processes.ProcessRegistry()
        self.addCleanup(self.registry.shutdown)
        self.folder = Path(self.temp.name)
        self.script = self.folder / "fake jobs.py"
        self.script.write_text(TREE, encoding="utf-8")

    def command(self, mode="stall"):
        return [sys.executable, "-B", str(self.script), str(self.folder), "parent", mode]

    def pids(self):
        return [int((self.folder / (role + ".pid")).read_text()) for role in ("parent", "child")]

    def test_shutdown_terminates_stalled_job_tree_and_unblocks_run(self):
        results = []
        worker = threading.Thread(target=lambda: results.append(self.registry.run(self.command(), capture_output=True, text=True)))
        worker.start()
        wait_for(lambda: (self.folder / "child.pid").exists())
        pids = self.pids()
        self.assertEqual(os.getpgid(pids[0]), pids[0])
        self.assertNotEqual(pids[0], os.getpgrp())
        unrelated = subprocess.Popen([sys.executable, "-B", "-c", "import time;time.sleep(30)"], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        try:
            started = time.monotonic()
            self.registry.shutdown()
            worker.join(3)
            self.assertLess(time.monotonic() - started, 5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(results[0].returncode, -signal.SIGKILL)
            wait_for(lambda: all(not alive(pid) for pid in pids))
            self.assertIsNone(unrelated.poll())
            self.assertEqual(self.registry._children, {})
        finally:
            unrelated.kill()
            unrelated.wait(timeout=5)

    def test_timeout_cleans_descendants_after_parent_already_exited(self):
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            self.registry.run(self.command("exit-parent"), capture_output=True, text=True, timeout=0.5)
        self.assertLess(time.monotonic() - started, 5)
        pids = self.pids()
        wait_for(lambda: all(not alive(pid) for pid in pids))
        self.assertEqual(self.registry._children, {})

    def test_streamed_install_style_child_is_tracked_until_release(self):
        child = self.registry.popen(self.command(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.assertEqual(child.stdout.readline().strip(), "ready")
        pids = self.pids()
        self.registry.shutdown()
        child.wait(timeout=3)
        self.registry.release(child)
        self.assertTrue(child.stdout.closed)
        wait_for(lambda: all(not alive(pid) for pid in pids))


class AppInjection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="relic-job-injection-")
        self.addCleanup(self.temp.cleanup)
        self.environment = mock.patch.dict(os.environ, {"RELIC_HOME": self.temp.name, "RELIC_LANG": "en-US"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_app_default_namer_and_explainer_use_its_registry(self):
        app = web.App(store=object())
        with mock.patch.object(naming.runner, "find_claude", return_value="/fixture/claude"), \
                mock.patch.object(app.processes, "run", side_effect=[
                    subprocess.CompletedProcess([], 0, '{"member":"Writer"}', ""),
                    subprocess.CompletedProcess([], 0, "digest fixture", "")]) as run:
            self.assertEqual(app.namer.ask("Team", {"member": "write"}, "en-US"), {"member": "Writer"})
            self.assertEqual(app.explainer.ask("prompt"), "digest fixture")
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0][0], "/fixture/claude")
        self.assertEqual(run.call_args_list[1].args[0][0], "/fixture/claude")

    def test_explicit_fake_models_remain_usable(self):
        registry = processes.ProcessRegistry()
        fake = mock.Mock(return_value="fixture")
        self.assertEqual(naming.Namer(object(), ask=fake, processes=registry).ask("x"), "fixture")
        self.assertEqual(explain.Explainer(object(), ask=fake, processes=registry).ask("x"), "fixture")
        self.assertEqual(fake.call_args_list, [mock.call("x"), mock.call("x")])

    def test_app_passes_registry_to_adapter_installer(self):
        app = web.App(store=object())
        finished = threading.Event()
        passed = []

        def install(harness, log, processes=None):
            passed.append(processes)
            finished.set()
            return 0

        with mock.patch.object(web.harnesses, "install", side_effect=install):
            self.assertTrue(app.install("codex")["started"])
            self.assertTrue(finished.wait(2))
            wait_for(lambda: not app.installing)
        self.assertEqual(passed, [app.processes])

    def test_app_shutdown_stops_a_running_job_and_rejects_followup_work(self):
        app = web.App(store=object())
        child = app.processes.popen([sys.executable, "-B", "-c", "import time;time.sleep(30)"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            app.request_shutdown()
            wait_for(lambda: child.poll() is not None)
            self.assertTrue(app.stopping.is_set())
            with self.assertRaisesRegex(RuntimeError, "stopping"):
                app.processes.popen(["never-started"])
        finally:
            app.processes.shutdown()
            app.processes.release(child)


if __name__ == "__main__":
    unittest.main()
