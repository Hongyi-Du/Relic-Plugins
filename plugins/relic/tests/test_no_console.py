"""Creation flags at launch boundaries. Every process launch here is mocked."""
import ast
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from relic_core import platform_support, process, runner, wake
from relic_core.store import Store
from app import acp, processes, web
import relic_app

spec = importlib.util.spec_from_file_location("no_console_relic_run", ROOT / "scripts/relic_run.py")
relic_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relic_run)


class NoConsole(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = mock.patch.dict(os.environ, {"RELIC_HOME": str(self.root / "data")})
        env.start()
        self.addCleanup(env.stop)

    def assert_hidden(self, launch):
        self.assertTrue(launch.call_args_list)
        for call in launch.call_args_list:
            flags = call.kwargs.get("creationflags", 0)
            self.assertEqual(flags & 0x08000000, 0x08000000)
            self.assertEqual(flags & (0x00000010 | 0x00000008), 0)

    def test_shared_flags_remove_console_overrides_and_preserve_process_groups(self):
        with mock.patch.object(process, "WINDOWS", True):
            self.assertEqual(process.creation_flags(0x218), 0x08000200)
        with mock.patch.object(process, "WINDOWS", False):
            self.assertEqual(process.creation_flags(0x218), 0)

    def test_registry_enforces_flags_even_for_a_caller_without_them(self):
        with mock.patch.object(process, "WINDOWS", True), mock.patch.object(processes.subprocess, "Popen") as launch:
            registry = processes.ProcessRegistry()
            registry.popen(["fixture-console"])
            registry.popen(["fixture-console"], creationflags=0x218)
            self.assert_hidden(launch)
            self.assertEqual(launch.call_args.kwargs["creationflags"], 0x08000200)

    def test_node_probe_and_codex_desktop_probe_are_hidden(self):
        with mock.patch.object(process, "WINDOWS", True), \
                mock.patch.object(platform_support.subprocess, "run", return_value=SimpleNamespace(
                    returncode=0, stdout='{"version":"22.0.0","arch":"arm64"}')) as launch:
            platform_support.node_runtime("fixture-node")
            self.assert_hidden(launch)
        with mock.patch.object(runner, "NO_WINDOW", 0x08000000), \
                mock.patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout="")) as launch:
            runner.codex_desktop_exe()
            self.assert_hidden(launch)

    def test_automatic_runner_retry_and_cli_children_are_hidden(self):
        store = Store()
        oid = store.create("lead", "Fixture", "repair", "lead")["id"]
        store.join("member-session", oid, "member")
        config = dict(runner.default_config("claude-code"), folder=str(self.root))
        store.set_config(oid, "member", config)
        with mock.patch.object(runner, "WINDOWS", True), mock.patch.object(runner, "NO_WINDOW", 0x08000000), \
                mock.patch.object(runner, "is_running", return_value=False), \
                mock.patch.object(runner.subprocess, "Popen", return_value=SimpleNamespace(pid=12345)) as launch:
            runner.start_turn(oid, "member", "fixture", open_after=True, wake_from=["lead"])
            self.assertNotIn("--open", launch.call_args.args[0])
            wake.schedule_retry(oid, 10)
            self.assert_hidden(launch)
        with mock.patch.object(runner, "NO_WINDOW", 0x08000000), \
                mock.patch.object(runner, "find_claude", return_value="fixture-claude"), \
                mock.patch.object(runner.subprocess, "run", return_value=SimpleNamespace(
                    returncode=0, stdout=json.dumps({"result": "done"}))) as launch:
            relic_run.run_claude(store, store.get(oid), "member", config, "fixture", False, str(self.root))
            self.assert_hidden(launch)
        with mock.patch.object(runner, "NO_WINDOW", 0x08000000), \
                mock.patch.object(runner.subprocess, "Popen") as launch, \
                mock.patch.object(runner.CodexAppServer, "request"), mock.patch.object(runner.CodexAppServer, "notify"):
            with runner.CodexAppServer("fixture-codex"):
                pass
            self.assert_hidden(launch)

    def test_app_server_and_acp_children_are_hidden(self):
        with mock.patch.object(relic_app, "WINDOWS", True), mock.patch.object(relic_app, "NO_WINDOW", 0x08000000), \
                mock.patch.object(relic_app, "running", side_effect=[None, None, {"port": 12345}]), \
                mock.patch.object(relic_app, "unverified_server", return_value=False), \
                mock.patch.object(web, "LifecycleLock"), mock.patch.object(relic_app.subprocess, "Popen") as launch:
            self.assertEqual(relic_app._start_server(12345), {"port": 12345})
            self.assert_hidden(launch)
        with mock.patch.object(acp, "NO_WINDOW", 0x08000000), mock.patch.object(acp.subprocess, "Popen") as launch, \
                mock.patch.object(acp.threading, "Thread"), mock.patch.object(acp.AcpAgent, "request", return_value={}):
            agent = acp.AcpAgent(["fixture-adapter"], cwd=str(self.root), env={})
            agent.start()
            self.assert_hidden(launch)

    def test_wake_command_cannot_open_a_session_even_if_open_is_passed(self):
        prompt = self.root / "prompt.txt"
        prompt.write_text("fixture", encoding="utf-8")
        store = Store()
        oid = store.create("lead", "Fixture", "repair", "lead")["id"]
        store.join("member-session", oid, "member")
        store.set_config(oid, "member", dict(runner.default_config("claude-code"), folder=str(self.root)))
        argv = ["relic_run.py", "--org", oid, "--member", "member", "--prompt-file", str(prompt),
                "--open", "--wake-from", "lead"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(relic_run, "run_claude", return_value=("member-session", "done", False, None)), \
                mock.patch.object(runner, "open_session") as opened, mock.patch.object(wake, "dispatch"), \
                mock.patch.object(wake, "finish"):
            relic_run.main()
            opened.assert_not_called()

    def test_every_production_subprocess_boundary_declares_creation_flags(self):
        # Catch new unprotected probes/children, including aliases in App jobs.
        roots = [ROOT / "relic_core", ROOT / "app", ROOT / "scripts"]
        repository_scripts = ROOT.parents[1] / "scripts"
        if (repository_scripts / "check.py").exists():
            roots.append(repository_scripts)
        for folder in roots:
            for path in folder.glob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    func = node.func
                    direct = (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                              and func.value.id == "subprocess" and func.attr in
                              ("Popen", "run", "call", "check_call", "check_output"))
                    alias = (path.name in ("naming.py", "explain.py", "harness.py", "claude_desktop.py")
                             and isinstance(func, ast.Name) and func.id in ("run", "spawn", "execute"))
                    if direct or alias:
                        keys = {kw.arg for kw in node.keywords}
                        # Registry normalizes kwargs immediately before its Popen.
                        if path.name == "processes.py" and None in keys:
                            continue
                        self.assertIn("creationflags", keys, "%s:%d" % (path, node.lineno))


if __name__ == "__main__":
    unittest.main()
