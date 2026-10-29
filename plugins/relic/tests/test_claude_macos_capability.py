"""Native Claude Desktop eligibility from explicit consent, version and sanitized public-hook evidence."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_core import claude_desktop as gui, gui_receipt, runner
from relic_core.store import Store


class ClaudeMacCapability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {"RELIC_HOME": str(self.root), "RELIC_CLAUDE_DESKTOP_ENABLED": "0",
                                           "CLAUDE_CODE_ENTRYPOINT": "claude-desktop"})
        env.start()
        self.addCleanup(env.stop)
        platform = mock.patch.object(gui, "sys", SimpleNamespace(platform="darwin", executable=sys.executable))
        platform.start()
        self.addCleanup(platform.stop)
        self.exe = self.root / "selected claude"
        self.exe.write_text("fixture executable never run")
        self.exe.chmod(0o700)
        finder = mock.patch.object(runner, "find_claude", return_value=str(self.exe))
        finder.start()
        self.addCleanup(finder.stop)
        self.store = Store()
        self.org_id = self.store.create("lead", "Desktop fixture", "test", "lead")["id"]
        self.config = dict(runner.default_config("claude-code"), surface="gui")
        self.store.add_seat(self.org_id, "member", config=self.config)
        self.store.join("fixture-carrier", self.org_id, "member")

    def observe(self, carrier="fixture-carrier", **fields):
        event = dict(hook_event_name="Stop", session_id=carrier, last_assistant_message="private fixture response")
        event.update(fields)
        gui_receipt.capture(event, {}, self.store, carrier)

    def probe(self, version="2.1.224"):
        with mock.patch.object(gui.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=version + " (Claude Code)")) as run:
            value = gui.transport_capability(probe=True)
            self.assertEqual(run.call_args.args[0], [str(self.exe), "--version"])
        return value

    def test_requires_opt_in_supported_version_and_real_public_hook_evidence(self):
        self.assertFalse(gui.transport_capability()["available"])
        self.assertFalse(self.probe()["available"])
        self.assertFalse(gui.set_enabled(True)["available"])
        self.observe()
        with mock.patch.object(gui.subprocess, "run", side_effect=AssertionError("capability reads do not run hosts")):
            self.assertTrue(gui.transport_capability()["available"])
        proof = gui_receipt.observation_path("fixture-carrier").read_text()
        self.assertNotIn("private fixture response", proof)
        self.assertNotIn("fixture-carrier", proof)
        gui._require_mac_transport("fixture-carrier")
        with self.assertRaisesRegex(gui.TransportError, "this GUI seat"):
            gui._require_mac_transport("another-carrier")
        self.assertFalse(gui.set_enabled(False)["available"])

    def test_old_cli_and_changed_executable_invalidate_support(self):
        gui.set_enabled(True)
        self.observe()
        old = self.probe("2.1.92")
        self.assertFalse(old["available"])
        self.assertIn("2.1.92", old["reason"])
        self.assertTrue(self.probe()["available"])
        self.exe.write_text("a different executable")
        self.assertFalse(gui.transport_capability()["available"])
        self.assertTrue(self.probe()["available"])
        gui.reset_transport_verification()
        self.assertFalse(gui.transport_capability()["available"])

    def test_non_desktop_subagents_and_missing_public_text_do_not_validate(self):
        gui.set_enabled(True)
        self.probe()
        self.observe(agent_id="subagent")
        self.observe(last_assistant_message=None)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_ENTRYPOINT": "cli"}):
            self.observe()
        self.assertFalse(gui.transport_capability()["available"])

    def test_stale_or_corrupt_observation_is_not_accepted(self):
        gui.set_enabled(True)
        self.probe()
        self.observe()
        path = gui_receipt.observation_path("fixture-carrier")
        proof = json.loads(path.read_text())
        for value in (dict(proof, at=time.time() - 86401), dict(proof, at="bad"), []):
            path.write_text(json.dumps(value))
            self.assertFalse(gui.transport_capability()["available"])

    def test_unverified_native_route_never_launches_router_or_changes_pending_request(self):
        folder = self.root / "router"
        folder.mkdir()
        with mock.patch.object(gui.subprocess, "run") as execute, self.assertRaises(gui.TransportError):
            gui.route({"carrier": "fixture-carrier"}, self.config, folder)
        execute.assert_not_called()
        self.assertEqual(list(folder.iterdir()), [])

    def test_explicit_disable_overrides_environment_activation(self):
        self.probe()
        self.observe()
        with mock.patch.dict(os.environ, {"RELIC_CLAUDE_DESKTOP_ENABLED": "1"}):
            self.assertTrue(gui.transport_capability()["available"])
            self.assertFalse(gui.set_enabled(False)["available"])

    def test_validated_macos_turn_uses_native_tool_proof_and_matching_public_stop(self):
        gui.set_enabled(True)
        self.probe()
        self.observe()
        invocations = []

        def route(request, config, folder):
            target = request["expected"] + " [aabbcc]"
            listing = '- "%s" [aabbcc] (Desktop, idle)' % request["expected"]

            def execute(args, **kwargs):
                invocations.append(args)
                if "auth" in args:
                    return SimpleNamespace(returncode=0, stdout='{"authMethod":"claude.ai"}')
                gui.router_hook({"hook_event_name": "PostToolUse", "tool_name": "ListAgents", "tool_response": listing}, folder)
                data = {"to": target, "message": gui.payload(request)}
                self.assertEqual(gui.router_hook({"hook_event_name": "PreToolUse", "tool_name": "SendMessage", "tool_input": data}, folder), {})
                events = [
                    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "l", "name": "ListAgents", "input": {}}]}},
                    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "l", "content": listing}]}},
                    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "s", "name": "SendMessage", "input": data}]}},
                    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "s", "content": "Message sent"}]}}
                ]
                return SimpleNamespace(returncode=0, stdout="\n".join(map(json.dumps, events)))

            outcome = gui.route(request, config, folder, execute=execute)
            self.observe(last_assistant_message="public result " + gui.marker(request))
            return outcome

        result = gui.run_turn(self.store, self.store.get(self.org_id), "member", self.config, "fixture task", False,
                              str(self.root), route_message=route, timeout=0)
        self.assertEqual(result[0], "fixture-carrier")
        self.assertIn("public result", result[1])
        self.assertFalse(result[2])
        self.assertEqual(len(invocations), 2)
        self.assertFalse(any("--resume" in args for args in invocations))


if __name__ == "__main__":
    unittest.main()
