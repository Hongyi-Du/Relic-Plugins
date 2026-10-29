"""Platform boundary fixtures: no installed hosts, shell profiles, or native UI are used."""
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_core import platform_support as platforms  # noqa: E402
from app import harness  # noqa: E402


class Discovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="relic-platform-")
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def executable(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture only\n", encoding="utf-8")
        path.chmod(0o700)
        return path

    def test_explicit_path_wins_and_invalid_override_fails_closed(self):
        chosen = self.executable("chosen bin/node")
        with mock.patch.dict(os.environ, {"RELIC_NODE_PATH": str(self.root / "missing")}), \
                mock.patch.object(platforms.shutil, "which", return_value="/path/node") as which:
            self.assertEqual(platforms.find_executable("node", explicit=str(chosen)), str(chosen))
            self.assertIsNone(platforms.find_executable("node"))
            self.assertIsNone(platforms.find_executable("node", explicit=str(self.root / "also-missing")))
            which.assert_not_called()

    @unittest.skipIf(os.name == "nt", "POSIX executable permission check")
    def test_non_executable_override_is_rejected(self):
        chosen = self.executable("node")
        chosen.chmod(0o600)
        with mock.patch.object(platforms.shutil, "which") as which:
            self.assertIsNone(platforms.find_executable("node", explicit=str(chosen)))
            which.assert_not_called()

    def test_path_is_used_before_mac_fallbacks(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(platforms.sys, "platform", "darwin"), \
                mock.patch.object(platforms.Path, "home", return_value=self.root), \
                mock.patch.object(platforms.shutil, "which", return_value="/custom/bin/node"), \
                mock.patch.object(platforms, "_mac_bin_dirs") as directories:
            self.assertEqual(platforms.find_executable("node"), "/custom/bin/node")
            directories.assert_not_called()

    def test_path_discovery_survives_an_unavailable_home_directory(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(platforms.Path, "home", side_effect=RuntimeError("Could not determine home directory")), \
                mock.patch.object(platforms.shutil, "which", return_value="/custom/bin/node"):
            self.assertEqual(platforms.find_executable("node"), "/custom/bin/node")

    def test_sparse_path_finds_homebrew_without_shell_startup(self):
        expected = str(Path("/opt/homebrew/bin/node"))
        with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True), \
                mock.patch.object(platforms.sys, "platform", "darwin"), \
                mock.patch.object(platforms.Path, "home", return_value=self.root), \
                mock.patch.object(platforms.shutil, "which", return_value=None), \
                mock.patch.object(platforms, "_executable", side_effect=lambda p: str(p) if str(p) == expected else None), \
                mock.patch.object(platforms.subprocess, "run") as run:
            self.assertEqual(platforms.find_executable("node"), expected)
            run.assert_not_called()

    def test_nvm_fallback_orders_versions_numerically(self):
        for version in ("v9.10.0", "v22.2.0", "v22.10.0", "v22.8.1", "vcurrent"):
            (self.root / ".nvm/versions/node" / version).mkdir(parents=True)
        with mock.patch.object(platforms.Path, "home", return_value=self.root):
            nvm = [p for p in platforms._mac_bin_dirs() if ".nvm" in p.parts]
        self.assertEqual([p.parent.name for p in nvm], ["v22.10.0", "v22.8.1", "v22.2.0", "v9.10.0"])

    def test_windows_bundled_codex_prefers_cli_over_newer_helpers(self):
        cli = self.executable("local/OpenAI/Codex/bin/version/codex.exe")
        helper = self.executable("local/OpenAI/Codex/bin/version/codex-command-runner.exe")
        os.utime(cli, (100, 100))
        os.utime(helper, (200, 200))
        env = {"LOCALAPPDATA": str(self.root / "local")}
        # Replace this module's OS facade, not global os.name: pathlib remains host-native.
        windows = SimpleNamespace(name="nt", environ=env, getenv=lambda k, default=None: env.get(k, default),
                                  access=os.access, X_OK=os.X_OK)
        with mock.patch.object(platforms, "os", windows), mock.patch.object(platforms.sys, "platform", "win32"), \
                mock.patch.object(platforms.shutil, "which", return_value=None):
            self.assertEqual(platforms.find_executable("codex"), str(cli))

    def test_runtime_path_preserves_env_and_prioritizes_selected_runtime(self):
        node = self.root / "Node Runtime/bin/node"
        npm = node.with_name("npm")
        initial = {"PATH": os.pathsep.join(("/usr/bin", str(node.parent))), "TEST_VALUE": "a=b\n' $literal"}
        result = platforms.runtime_env(initial, [str(node), str(npm)])
        self.assertEqual(result["PATH"].split(os.pathsep), [str(node.parent), "/usr/bin"])
        self.assertEqual(result["TEST_VALUE"], initial["TEST_VALUE"])
        self.assertEqual(initial["PATH"].split(os.pathsep)[0], "/usr/bin")

    @unittest.skipIf(os.name == "nt", "POSIX env shebang fixture")
    def test_selected_runtime_makes_an_env_shebang_work_with_sparse_path(self):
        interpreter = self.executable("runtime bin/relic-fixture-python")
        interpreter.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + ' -B "$@"\n', encoding="utf-8")
        shim = self.executable("shim bin/fixture")
        shim.write_text("#!/usr/bin/env relic-fixture-python\nimport json,os,sys\n"
                        "print(json.dumps([sys.argv[1], os.getenv('FIXTURE_VALUE')]))\n", encoding="utf-8")
        env = platforms.runtime_env({"PATH": "/no-existing-runtime", "FIXTURE_VALUE": "fixture"}, [str(interpreter)])
        done = subprocess.run([str(shim), "argument with spaces"], capture_output=True, text=True, env=env, timeout=10)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), ["argument with spaces", "fixture"])

    def test_browser_discovery_finds_a_user_app_bundle(self):
        expected = self.root / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        with mock.patch.object(platforms.sys, "platform", "darwin"), \
                mock.patch.object(platforms.Path, "home", return_value=self.root), \
                mock.patch.object(platforms.shutil, "which", return_value=None), \
                mock.patch.object(platforms, "_executable", side_effect=lambda p: str(p) if Path(p) == expected else None):
            self.assertEqual(platforms.browser_executable(), str(expected))


class RuntimeChecks(unittest.TestCase):
    def test_python_guard_accepts_native_arm_and_rejects_rosetta(self):
        with mock.patch.object(platforms.sys, "platform", "darwin"), \
                mock.patch.object(platforms.sys, "version_info", (3, 11, 0)), \
                mock.patch.object(platforms.platform, "machine", return_value="arm64") as machine:
            platforms.require_supported_python()
            machine.return_value = "x86_64"
            with self.assertRaisesRegex(RuntimeError, "arm64.*Rosetta"):
                platforms.require_supported_python()

    def test_python_version_guard_and_non_mac_architecture(self):
        with mock.patch.object(platforms.sys, "platform", "win32"), \
                mock.patch.object(platforms.sys, "version_info", (3, 11, 0)), \
                mock.patch.object(platforms.platform, "machine", return_value="AMD64"):
            platforms.require_supported_python()
        with mock.patch.object(platforms.sys, "version_info", (3, 10, 9)):
            with self.assertRaisesRegex(RuntimeError, "3.11"):
                platforms.require_supported_python()

    def test_node_requires_22_and_native_arm_only_on_macos(self):
        for system, version, arch, supported in (("darwin", "22.0.0", "arm64", True),
                                                 ("darwin", "24.1.0", "arm64", True),
                                                 ("darwin", "20.19.0", "arm64", False),
                                                 ("darwin", "24.1.0", "x64", False),
                                                 ("win32", "22.0.0", "x64", True)):
            with self.subTest(system=system, version=version, arch=arch), \
                    mock.patch.object(platforms.sys, "platform", system), \
                    mock.patch.object(platforms.subprocess, "run", return_value=SimpleNamespace(
                        returncode=0, stdout=json.dumps({"version": version, "arch": arch}))) as run:
                result = platforms.node_runtime("/selected node/bin/node")
                self.assertEqual(result["supported"], supported)
                self.assertEqual((result["version"], result["architecture"]), (version, arch))
                self.assertEqual(run.call_args.args[0][0], "/selected node/bin/node")
                self.assertNotIn("shell", run.call_args.kwargs)

    def test_bad_node_output_and_launch_errors_are_diagnostics(self):
        for output in ("not JSON", "null", "[]", '"bad"', "{}", '{"version":"bad","arch":"arm64"}'):
            with self.subTest(output=output), mock.patch.object(platforms.subprocess, "run", return_value=SimpleNamespace(
                    returncode=0, stdout=output)):
                result = platforms.node_runtime("/fixture/node")
                self.assertFalse(result["supported"])
                self.assertIn("problem", result)
        for error in (OSError("cannot execute"), subprocess.TimeoutExpired("node", 5)):
            with self.subTest(error=error), mock.patch.object(platforms.subprocess, "run", side_effect=error):
                self.assertFalse(platforms.node_runtime("/fixture/node")["supported"])

    def test_missing_node_is_not_executed(self):
        with mock.patch.object(platforms, "find_executable", return_value=None), \
                mock.patch.object(platforms.subprocess, "run") as run:
            self.assertFalse(platforms.node_runtime()["supported"])
            run.assert_not_called()

    def test_harness_install_stops_before_npm_when_node_is_unsupported(self):
        logs = []
        with mock.patch.object(harness, "node", return_value="/fixture/node"), \
                mock.patch.object(platforms, "node_runtime", return_value={"path": "/fixture/node", "supported": False,
                                                                            "problem": "Node 22 required"}), \
                mock.patch.object(harness.subprocess, "Popen") as popen:
            self.assertEqual(harness.install("codex", logs.append), 1)
            self.assertEqual(logs, ["Node 22 required"])
            popen.assert_not_called()

    def test_harness_launch_prepares_runtime_path_and_drops_parent_identity(self):
        with tempfile.TemporaryDirectory(prefix="relic-harness-platform-") as directory:
            root = Path(directory)
            entry = root / "node_modules/@fixture/adapter/dist/index.js"
            entry.parent.mkdir(parents=True)
            entry.write_text("// never executed\n", encoding="utf-8")
            node = str(root / "runtime bin/node")
            spec = {"package": "@fixture/adapter@1.0.0", "env": lambda: {"CODEX_PATH": "/fixture/codex"}}
            with mock.patch.object(harness, "acp_home", return_value=root), \
                    mock.patch.object(harness, "node", return_value=node), \
                    mock.patch.dict(harness.HARNESSES, {"fixture": spec}), \
                    mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin", "CODEX_THREAD_ID": "parent", "CLAUDECODE": "1"}, clear=True), \
                    mock.patch.object(platforms, "node_runtime", return_value={"supported": True}):
                argv, env = harness.launch("fixture", {"RELIC_SEAT": "org/member"})
            self.assertEqual(argv, [node, str(entry)])
            self.assertEqual(env["PATH"].split(os.pathsep)[0], str(Path(node).parent))
            self.assertEqual((env["CODEX_PATH"], env["RELIC_SEAT"]), ("/fixture/codex", "org/member"))
            self.assertNotIn("CODEX_THREAD_ID", env)
            self.assertNotIn("CLAUDECODE", env)


class NativeOpen(unittest.TestCase):
    def test_mac_open_uses_literal_argument_after_options(self):
        target = "/Users/test/Work ' Files/$(literal);报告.md"
        with mock.patch.object(platforms.sys, "platform", "darwin"), \
                mock.patch.object(platforms.subprocess, "run", return_value=SimpleNamespace(returncode=0, stderr="")) as run:
            platforms.open_external(target)
            self.assertEqual(run.call_args.args[0], ["/usr/bin/open", "--", target])
            self.assertNotIn("shell", run.call_args.kwargs)

    def test_mac_open_errors_are_reported(self):
        with mock.patch.object(platforms.sys, "platform", "darwin"), \
                mock.patch.object(platforms.subprocess, "run", return_value=SimpleNamespace(returncode=1, stderr="not found")):
            with self.assertRaisesRegex(RuntimeError, "not found"):
                platforms.open_external("/missing")
        with mock.patch.object(platforms.sys, "platform", "darwin"), \
                mock.patch.object(platforms.subprocess, "run", side_effect=subprocess.TimeoutExpired("open", 15)):
            with self.assertRaises(subprocess.TimeoutExpired):
                platforms.open_external("/missing")

    def test_windows_open_still_delegates_to_startfile(self):
        startfile = mock.Mock()
        with mock.patch.object(platforms.sys, "platform", "win32"), \
                mock.patch.object(platforms, "os", SimpleNamespace(name="nt", startfile=startfile)), \
                mock.patch.object(platforms.subprocess, "run") as run:
            platforms.open_external("C:\\Work Files\\report.txt")
            startfile.assert_called_once_with("C:\\Work Files\\report.txt")
            run.assert_not_called()


@unittest.skipIf(os.name == "nt", "POSIX Terminal launcher fixture")
class TerminalLauncher(unittest.TestCase):
    def test_launcher_preserves_arguments_environment_cwd_and_deletes_itself(self):
        real_run = subprocess.run
        with tempfile.TemporaryDirectory(prefix="relic-terminal-test-") as directory:
            root = Path(directory)
            cwd = root / "工作 ' $folder"
            cwd.mkdir()
            output = root / "result.json"
            sentinel = root / "must-not-exist"
            dangerous = "$(touch " + str(sentinel) + ")"
            arguments = ["space value", "single'quote", 'double"quote', "line\nbreak", dangerous,
                         "`touch " + str(sentinel) + "`", "semi;colon", ""]
            value = "secret ' \" = value\n" + dangerous
            code = ("import json,os,pathlib,sys; pathlib.Path(sys.argv[1]).write_text(json.dumps("
                    "{'args':sys.argv[2:],'cwd':os.getcwd(),'value':os.getenv('FIXTURE_VALUE'),"
                    "'leak':os.getenv('TERMINAL_LEAK')}),encoding='utf-8')")
            launchers = []

            def launch(command, **kwargs):
                self.assertEqual(command[:3], ["/usr/bin/open", "-a", "Terminal"])
                launcher = Path(command[3])
                launchers.append(launcher)
                self.assertEqual(stat.S_IMODE(launcher.stat().st_mode), 0o700)
                self.assertNotIn(value, " ".join(command))
                completed = real_run(["/bin/sh", str(launcher)], capture_output=True, text=True,
                                     env={"PATH": "/usr/bin:/bin", "TERMINAL_LEAK": "must not survive"}, timeout=10)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                return SimpleNamespace(returncode=0, stderr="")

            with mock.patch.object(platforms.subprocess, "run", side_effect=launch):
                platforms.open_terminal([sys.executable, "-B", "-c", code, str(output)] + arguments, str(cwd),
                                        {"PATH": "/usr/bin:/bin", "FIXTURE_VALUE": value}, root / "runs")
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result, {"args": arguments, "cwd": str(cwd.resolve()), "value": value, "leak": None})
            self.assertFalse(sentinel.exists())
            self.assertEqual(len(launchers), 1)
            self.assertFalse(launchers[0].exists())

    def test_failed_native_launch_cleans_the_private_script(self):
        with tempfile.TemporaryDirectory(prefix="relic-terminal-failure-") as directory:
            for outcome in (SimpleNamespace(returncode=1, stderr="Terminal unavailable"),
                            subprocess.TimeoutExpired("open", 15)):
                with self.subTest(outcome=outcome):
                    def launch(*args, **kwargs):
                        if isinstance(outcome, Exception):
                            raise outcome
                        return outcome
                    with mock.patch.object(platforms.subprocess, "run", side_effect=launch):
                        with self.assertRaises((RuntimeError, subprocess.TimeoutExpired)):
                            platforms.open_terminal(["/fixture/cli"], directory, {}, directory)
                    self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
