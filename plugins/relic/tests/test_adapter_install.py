"""Locked ACP installation fixtures; no npm download, host account, or model is used."""
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import harness


class FakeNpm:
    def __init__(self, result=0, wait=None):
        self.stdout = io.StringIO("installing fixture\n\ninstalled fixture\n")
        self.result = result
        self.on_wait = wait

    def wait(self):
        if self.on_wait:
            self.on_wait()
        return self.result


class AdapterInstall(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = mock.patch.dict(os.environ, {
            "RELIC_HOME": str(self.root / "data"), "RELIC_ACP_HOME": str(self.root / "ACP 中文 adapters"),
            "CODEX_HOME": str(self.root / "codex"), "CLAUDE_CONFIG_DIR": str(self.root / "claude"), "RELIC_LANG": "en-US",
        })
        environment.start()
        self.addCleanup(environment.stop)
        runtime = mock.patch.object(harness.platform_support, "node_runtime", return_value={
            "path": str(self.root / "node"), "supported": True, "version": "22.16.0",
            "architecture": "arm64", "problem": "",
        })
        self.runtime = runtime.start()
        self.addCleanup(runtime.stop)
        discovery = mock.patch.object(harness.platform_support, "find_executable",
                                      side_effect=lambda name: str(self.root / name))
        discovery.start()
        self.addCleanup(discovery.stop)
        self.expected = json.loads((harness.ADAPTER_LOCK / "package.json").read_text())["dependencies"]
        self.logs = []

    def package(self, home, name, version):
        folder = home / "node_modules" / Path(*name.split("/"))
        (folder / "dist").mkdir(parents=True, exist_ok=True)
        (folder / "dist/index.js").write_text("// fixture\n")
        (folder / "package.json").write_text(json.dumps({"name": name, "version": version}))
        return folder / "dist/index.js"

    def pair(self, home=None, ready=False):
        home = home or harness.locked_home()
        for name, version in self.expected.items():
            self.package(home, name, version)
        if ready:
            (home / ".relic-ready").write_text(home.name + "\n")
        return home

    def test_install_either_harness_uses_same_locked_pair_and_exact_checked_in_lock(self):
        calls = []

        def npm(argv, **kwargs):
            calls.append((argv, kwargs))
            destination = Path(argv[argv.index("--prefix") + 1])
            self.assertEqual(destination, harness.locked_home())
            for name in ("package.json", "package-lock.json"):
                self.assertEqual((destination / name).read_bytes(), (harness.ADAPTER_LOCK / name).read_bytes())
            self.pair(destination)
            return FakeNpm()

        with mock.patch.object(harness.subprocess, "Popen", side_effect=npm):
            self.assertEqual(harness.install("claude-code", self.logs.append), 0)
            self.assertEqual(harness.install("codex", self.logs.append), 0)
        self.assertEqual(len(calls), 1)
        argv, options = calls[0]
        self.assertEqual(argv[1], "ci")
        for argument in ("--ignore-scripts", "--omit=optional", "--no-audit", "--no-fund"):
            self.assertIn(argument, argv)
        self.assertEqual(Path(argv[0]), self.root / "npm")
        self.assertIn(str(self.root), options["env"]["PATH"].split(os.pathsep))
        self.assertEqual(self.logs[:2], ["installing fixture", "installed fixture"])
        self.assertTrue(harness._locked_ready())
        self.assertTrue(harness.installed("claude-code"))
        self.assertTrue(harness.installed("codex"))
        self.assertEqual(harness.adapter_version("claude-code"), self.expected[harness.LOCKED_PACKAGES[0]])

    def test_legacy_install_remains_available_until_a_complete_locked_pair_exists(self):
        package = harness.LOCKED_PACKAGES[0]
        legacy = self.package(harness.acp_home(), package, "0.96.0")
        self.assertEqual(harness._package_entry(package), legacy)
        destination = self.pair()
        self.assertEqual(harness._package_entry(package), legacy, "npm output is not usable before completion")
        (destination / ".relic-ready").write_text(destination.name + "\n")
        self.assertEqual(harness._package_entry(package), destination / legacy.relative_to(harness.acp_home()))

    def test_partial_directory_without_a_ready_marker_is_not_selected(self):
        package = harness.LOCKED_PACKAGES[0]
        self.package(harness.locked_home(), package, self.expected[package])
        self.assertFalse(harness.installed("claude-code"))
        self.assertFalse(harness.installed("codex"))

    def test_stale_ready_marker_does_not_make_an_incomplete_pair_available(self):
        package = harness.LOCKED_PACKAGES[0]
        destination = harness.locked_home()
        self.package(destination, package, self.expected[package])
        (destination / ".relic-ready").write_text(destination.name + "\n")
        self.assertFalse(harness._locked_ready())
        self.assertFalse(harness.installed("claude-code"))

    def test_mismatched_version_does_not_make_a_locked_pair_available(self):
        destination = self.pair(ready=True)
        self.package(destination, harness.LOCKED_PACKAGES[1], "0.0.0")
        self.assertFalse(harness._locked_ready())

    def test_nonzero_npm_exit_preserves_legacy_fallback_and_never_marks_ready(self):
        package = harness.LOCKED_PACKAGES[0]
        legacy = self.package(harness.acp_home(), package, "0.96.0")
        with mock.patch.object(harness.subprocess, "Popen", return_value=FakeNpm(result=7)):
            self.assertEqual(harness.install("codex", self.logs.append), 7)
        self.assertFalse((harness.locked_home() / ".relic-ready").exists())
        self.assertEqual(harness._package_entry(package), legacy)

    def test_repair_invalidates_the_old_ready_marker_before_npm_starts(self):
        destination = self.pair(ready=True)
        self.package(destination, harness.LOCKED_PACKAGES[1], "0.0.0")

        def npm(*args, **kwargs):
            self.assertFalse((destination / ".relic-ready").exists())
            return FakeNpm(result=1)

        with mock.patch.object(harness.subprocess, "Popen", side_effect=npm):
            self.assertNotEqual(harness.install("codex", self.logs.append), 0)
        self.assertFalse(harness._locked_ready())

    def test_npm_success_with_missing_adapter_is_reported_as_failure(self):
        def npm(*args, **kwargs):
            package = harness.LOCKED_PACKAGES[0]
            self.package(harness.locked_home(), package, self.expected[package])
            return FakeNpm()

        with mock.patch.object(harness.subprocess, "Popen", side_effect=npm):
            self.assertNotEqual(harness.install("claude-code", self.logs.append), 0)
        self.assertFalse(harness._locked_ready())

    def test_concurrent_pair_installers_wait_and_share_one_completed_install(self):
        first_started, second_requested, finish_first = threading.Event(), threading.Event(), threading.Event()
        calls = []

        def complete():
            self.assertTrue(finish_first.wait(5), "fixture did not release npm")
            self.pair()

        def npm(*args, **kwargs):
            calls.append(args)
            first_started.set()
            return FakeNpm(wait=complete)

        def second():
            second_requested.set()
            return harness.install("codex", self.logs.append)

        with mock.patch.object(harness.subprocess, "Popen", side_effect=npm), ThreadPoolExecutor(2) as workers:
            first = workers.submit(harness.install, "claude-code", self.logs.append)
            try:
                self.assertTrue(first_started.wait(5))
                other = workers.submit(second)
                self.assertTrue(second_requested.wait(5))
                self.assertFalse(other.done())
                self.assertEqual(len(calls), 1)
            finally:
                finish_first.set()
            self.assertEqual(first.result(timeout=5), 0)
            self.assertEqual(other.result(timeout=5), 0)
        self.assertEqual(len(calls), 1)

    def test_process_registry_releases_npm_on_success_failure_and_log_exception(self):
        for result, log_error in ((0, False), (9, False), (0, True)):
            with self.subTest(result=result, log_error=log_error):
                shutil.rmtree(harness.locked_home(), ignore_errors=True)
                process = FakeNpm(result=result)
                registry = mock.Mock()
                def npm(*args, **kwargs):
                    self.pair()
                    return process
                registry.popen.side_effect = npm
                log = mock.Mock(side_effect=RuntimeError("consumer closed") if log_error else None)
                with mock.patch.object(harness.subprocess, "Popen") as unowned:
                    if log_error:
                        with self.assertRaisesRegex(RuntimeError, "consumer closed"):
                            harness.install("codex", log, processes=registry)
                    else:
                        self.assertEqual(harness.install("codex", log, processes=registry), result)
                registry.popen.assert_called_once()
                registry.release.assert_called_once_with(process)
                unowned.assert_not_called()

    def test_missing_npm_stops_before_creating_an_installation(self):
        with mock.patch.object(harness.platform_support, "find_executable", return_value=None), \
                mock.patch.object(harness.subprocess, "Popen") as npm:
            self.assertEqual(harness.install("codex", self.logs.append), 1)
        npm.assert_not_called()
        self.assertFalse(harness.acp_home().exists())

    def test_unsupported_node_stops_before_installation_or_directory_creation(self):
        for path, problem in (("", "Node missing"), ("/fixture/node", "Node 22 required"),
                              ("/fixture/node", "arm64 Node required")):
            with self.subTest(problem=problem):
                self.runtime.return_value = {"path": path, "supported": False, "problem": problem}
                with mock.patch.object(harness.subprocess, "Popen") as npm:
                    self.assertEqual(harness.install("codex", self.logs.append), 1)
                npm.assert_not_called()
                self.assertFalse(harness.acp_home().exists())
                if path:
                    self.assertIn(problem, self.logs)


if __name__ == "__main__":
    unittest.main()
