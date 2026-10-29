"""Read-only diagnostics must report the adapters the App will actually launch."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "plugins/relic"))
import install
from app import harness
from relic_core import platform_support


class Doctor(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = mock.patch.dict(os.environ, {
            "RELIC_HOME": str(self.root / "data"), "RELIC_ACP_HOME": str(self.root / "ACP 中文"),
            "CODEX_HOME": str(self.root / "codex"), "CLAUDE_CONFIG_DIR": str(self.root / "claude"),
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.plugin = self.root / "fixture-plugin"
        (self.plugin / ".claude-plugin").mkdir(parents=True)
        (self.plugin / ".claude-plugin/plugin.json").write_text('{"version":"test-fixture"}')
        (self.plugin / "server.py").write_text("# fixture server is never executed\n")
        (self.plugin / "codex.mcp.json").write_text(json.dumps({"mcpServers": {"relic_org": {
            "command": sys.executable, "args": ["-X", "utf8", str(self.plugin / "server.py")],
        }}}))
        self.expected = json.loads((harness.ADAPTER_LOCK / "package.json").read_text())["dependencies"]

    def package(self, home, name, version):
        folder = home / "node_modules" / Path(*name.split("/"))
        (folder / "dist").mkdir(parents=True, exist_ok=True)
        (folder / "dist/index.js").write_text("// fixture\n")
        (folder / "package.json").write_text(json.dumps({"name": name, "version": version}))

    def report(self, *arguments):
        capabilities = {"macos_supported": True, "codex_desktop_wake": False,
                        "desktop_transport": "fixture transport"}
        runtime = {"path": "/fixture/node", "supported": True, "problem": "",
                   "version": "22.16.0", "architecture": "arm64"}
        output = io.StringIO()
        with mock.patch.object(install, "plugin_dir", return_value=self.plugin), \
                mock.patch.object(install, "cli", return_value=None), \
                mock.patch.object(platform_support, "capabilities", return_value=capabilities) as capability_probe, \
                mock.patch.object(platform_support, "node_runtime", return_value=runtime), \
                mock.patch.object(platform_support, "find_executable", return_value=None), \
                mock.patch.object(sys, "argv", ["doctor.py", *arguments]), contextlib.redirect_stdout(output):
            runpy.run_path(str(ROOT / "scripts/doctor.py"), run_name="__main__")
        capability_probe.assert_called_once_with(probe="--probe-desktop" in arguments)
        return json.loads(output.getvalue())

    def test_reports_the_ready_locked_installation_without_legacy_node_modules(self):
        destination = harness.locked_home()
        for name, version in self.expected.items():
            self.package(destination, name, version)
        (destination / ".relic-ready").write_text(destination.name + "\n")
        report = self.report()
        self.assertEqual(report["acp_adapters"], {"claude-agent-acp": True, "codex-acp": True})
        for key, package in (("claude-code", harness.LOCKED_PACKAGES[0]), ("codex", harness.LOCKED_PACKAGES[1])):
            self.assertEqual(report["adapter_installation"][key]["version"], self.expected[package])
            entry = destination / "node_modules" / Path(*package.split("/")) / "dist/index.js"
            self.assertEqual(report["adapter_installation"][key]["entry"], str(entry))
        self.assertEqual(report["version"], "test-fixture")
        self.assertEqual(report["mcp_servers"]["relic_org"], {"interpreter_exists": True, "script_exists": True})

    def test_reports_legacy_fallback_and_does_not_mistake_partial_pair_for_a_ready_install(self):
        package = harness.LOCKED_PACKAGES[0]
        self.package(harness.acp_home(), package, "0.96.0")
        other = harness.LOCKED_PACKAGES[1]
        self.package(harness.locked_home(), other, self.expected[other])
        report = self.report()
        self.assertEqual(report["acp_adapters"], {"claude-agent-acp": True, "codex-acp": False})

    def test_missing_adapters_are_reported_without_creating_an_installation_or_store(self):
        report = self.report()
        self.assertEqual(report["acp_adapters"], {"claude-agent-acp": False, "codex-acp": False})
        self.assertFalse(harness.acp_home().exists())
        self.assertFalse((self.root / "data").exists())

    def test_desktop_probe_is_explicit_and_report_keeps_the_detected_transport(self):
        report = self.report("--probe-desktop")
        self.assertEqual(report["desktop_transport"], "fixture transport")

    def test_relative_mcp_script_is_resolved_from_the_plugin_not_the_working_directory(self):
        (self.plugin / "codex.mcp.json").write_text(json.dumps({"mcpServers": {"relic_org": {
            "command": sys.executable, "args": ["-X", "utf8", "server.py"],
        }}}))
        self.assertTrue(self.report()["mcp_servers"]["relic_org"]["script_exists"])


if __name__ == "__main__":
    unittest.main()
