"""Creating and running seat sessions from the Relic App, against fake claude / codex executables that follow
the real CLI flags and the codex app-server JSON-RPC contract."""
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core import claude_desktop, desktop, runner  # noqa: E402
from relic_core.store import Store  # noqa: E402

FAKE_CLAUDE = r'''#!PYTHON
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps({"bin": "claude", "args": sys.argv[1:], "cwd": os.getcwd()}) + "\n")
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "Seated; waiting for my task."}))
'''

FAKE_CODEX = r'''#!PYTHON
import json, os, sys
def log(entry):
    with open(os.environ["FAKE_LOG"], "a") as f:
        f.write(json.dumps(dict(entry, bin="codex", foo=os.environ.get("FOO"), cwd=os.getcwd())) + "\n")
def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n"); sys.stdout.flush()
assert sys.argv[1] == "app-server"
log({"argv": sys.argv[1:]})
def ask(rid, method, params):
    send({"id": rid, "method": method, "params": params})
    log({"reply_to_server_request": json.loads(sys.stdin.readline()), "asked": method, "server": params.get("serverName")})
for line in sys.stdin:
    msg = json.loads(line)
    method, params = msg.get("method"), msg.get("params") or {}
    if "method" not in msg:
        log({"reply_to_server_request": msg})
        continue
    log({"method": method, "params": params})
    if "id" not in msg:
        continue
    if method in ("thread/start", "thread/resume") and os.environ.get("FAKE_NO_REVIEWER") and "approvalsReviewer" in params:
        send({"id": msg["id"], "error": {"code": -32602, "message": "unknown field `approvalsReviewer`"}})
    elif method == "thread/start":
        send({"id": msg["id"], "result": {"thread": {"id": "th-fake-1"}, "model": params.get("model", "gpt-6.1-sol")}})
    elif method == "thread/resume":
        send({"id": msg["id"], "result": {"thread": {"id": params["threadId"]}}})
    elif method == "turn/start":
        tid = params["threadId"]
        send({"id": msg["id"], "result": {"turn": {"id": "u1", "status": "inProgress", "items": []}}})
        ask("srv-1", "item/commandExecution/requestApproval", {"threadId": tid, "command": "rm -rf x"})
        ask("srv-2", "mcpServer/elicitation/request", {"threadId": tid, "serverName": "relic_org", "mode": "form",
            "message": "Allow the relic_org tool status?", "requestedSchema": {"type": "object", "properties": {}}})
        ask("srv-3", "mcpServer/elicitation/request", {"threadId": tid, "serverName": "other_server", "mode": "form",
            "message": "Allow?", "requestedSchema": {"type": "object", "properties": {}}})
        send({"method": "item/completed", "params": {"threadId": tid, "turnId": "u1",
              "item": {"type": "agentMessage", "id": "m1", "text": "Seated as a Codex member."}}})
        send({"method": "turn/completed", "params": {"threadId": tid, "turn": {"id": "u1", "status": "completed", "items": []}}})
    else:
        send({"id": msg["id"], "result": {}})
'''


class Runner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # Windows: a runner log may still be open
        base = Path(self.tmp.name)
        bin_dir = base / "bin"
        bin_dir.mkdir()
        exes = {}
        for name, body in (("claude", FAKE_CLAUDE), ("codex", FAKE_CODEX)):
            if os.name == "nt":
                script = bin_dir / (name + "_fake.py")
                script.write_text(body.replace("PYTHON", sys.executable))
                exe = bin_dir / (name + ".cmd")
                exe.write_text('@"%s" "%s" %%*\r\n' % (sys.executable, script))
            else:
                exe = bin_dir / name
                exe.write_text(body.replace("PYTHON", sys.executable))
                exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
            exes[name] = exe
        self.saved = dict(os.environ)
        os.environ.update(RELIC_HOME=str(base / "relic"), FAKE_LOG=str(base / "calls.jsonl"),
                          PATH=str(bin_dir) + os.pathsep + os.environ["PATH"], CODEX_CLI_PATH=str(exes["codex"]))
        self.log = base / "calls.jsonl"
        self.store = Store()
        self.oid = self.store.found("Lab", "ship the API", "leader")["id"]
        self.ws = base / "ws"
        self.store.add_seat(self.oid, "alice", "api", dict(runner.default_config("claude-code"), model="sonnet",
                                                          effort="high", folder=str(self.ws), permission="acceptEdits"))
        self.store.add_seat(self.oid, "bob", "ui", dict(runner.default_config("codex"), model="gpt-6-sol",
                                                       effort="low", folder=str(self.ws), permission="read-only",
                                                       env={"FOO": "bar"}))

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def calls(self, binary):
        if not self.log.exists():
            return []
        return [c for c in map(json.loads, self.log.read_text().splitlines()) if c["bin"] == binary]

    def turn(self, member, prompt, new=False):
        runner.start_turn(self.oid, member, prompt, new_session=new)
        deadline = time.time() + 30
        while runner.is_running(self.oid, member):
            self.assertLess(time.time(), deadline, "turn did not finish")
            time.sleep(0.1)
        state = runner.run_state(self.oid, member)
        self.assertEqual(state["status"], "done", state)
        return state

    def test_first_seat_leads_a_human_founded_org(self):
        self.assertEqual(self.store.get(self.oid)["leader"], "alice")

    def test_session_environment_drops_parent_identity_and_keeps_configuration(self):
        inherited = dict.fromkeys(runner.platform_support.SESSION_IDENTITY_ENV, "parent-session")
        with mock.patch.dict(os.environ, dict(inherited, RELIC_HOME=self.tmp.name, CUSTOM_VALUE="kept")):
            env = runner.session_env({"env": {"FOO": "seat-value"}})
        self.assertTrue(all(key not in env for key in inherited))
        self.assertEqual((env["RELIC_HOME"], env["CUSTOM_VALUE"], env["FOO"]),
                         (self.tmp.name, "kept", "seat-value"))

    def test_unsupported_desktop_turn_does_not_change_session_focus(self):
        self.store.join("existing-session", self.oid, "alice")
        other = self.store.found("Other", "other work", "leader")["id"]
        self.store.join("existing-session", other, "reviewer")
        self.store.set_focus("existing-session", other)
        before = self.store.focused("existing-session")
        self.store.set_seat_fields(self.oid, "alice", config=dict(runner.default_config("claude-code"), surface="gui"))
        # Change the shared platform value so capability checks see the same OS
        # as the runner, and do not depend on installed desktop applications.
        with mock.patch.object(sys, "platform", "darwin"), \
                mock.patch.object(runner.platform_support.platform, "machine", return_value="arm64"), \
                mock.patch.object(desktop, "transport_capability", return_value={"available": False}), \
                mock.patch.object(claude_desktop, "transport_capability", return_value={"available": False}), \
                mock.patch.object(runner.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(RuntimeError, "desktop delivery is unavailable"):
                runner.start_turn(self.oid, "alice", "must stay manual")
            launch.assert_not_called()
        self.assertEqual(self.store.focused("existing-session"), before)
        self.assertIsNone(runner.run_state(self.oid, "alice"))

    def test_claude_session_created_then_resumed(self):
        org = self.store.get(self.oid)
        state = self.turn("alice", runner.introduction(org, "alice"), new=True)
        session = state["session"]
        self.assertEqual(self.store.get(self.oid)["members"]["alice"]["carrier"], session)
        first = self.calls("claude")[0]["args"]
        self.assertEqual(first[first.index("--session-id") + 1], session)
        for flag, value in (("--model", "sonnet"), ("--effort", "high"), ("--permission-mode", "acceptEdits"),
                            ("--name", "Lab · alice")):
            self.assertEqual(first[first.index(flag) + 1], value)
        self.assertIn("Do not start any other work", first[first.index("-p") + 1])
        self.assertEqual(state["reply"], "Seated; waiting for my task.")

        self.turn("alice", "Add a /health endpoint")
        second = self.calls("claude")[1]["args"]
        self.assertEqual(second[second.index("--resume") + 1], session)
        self.assertEqual(second[second.index("-p") + 1], "Add a /health endpoint")

    def test_codex_thread_created_then_resumed(self):
        org = self.store.get(self.oid)
        state = self.turn("bob", runner.introduction(org, "bob"), new=True)
        self.assertEqual(state["session"], "codex:th-fake-1")
        self.assertEqual(self.store.get(self.oid)["members"]["bob"]["carrier"], "codex:th-fake-1")
        self.assertEqual(self.store.get(self.oid)["members"]["bob"]["harness"], "codex")
        calls = self.calls("codex")
        start = next(c["params"] for c in calls if c.get("method") == "thread/start")
        self.assertEqual((start["sandbox"], start["approvalPolicy"], start["model"], start["approvalsReviewer"]),
                         ("read-only", "on-request", "gpt-6-sol", "auto_review"))
        self.assertEqual(next(c["argv"] for c in calls if "argv" in c), ["app-server"] + runner.codex_overrides())
        named = next(c["params"] for c in calls if c.get("method") == "thread/name/set")
        self.assertEqual(named["name"], "Lab · bob")
        turn = next(c["params"] for c in calls if c.get("method") == "turn/start")
        self.assertEqual(turn["effort"], "low")
        replies = {(c["asked"], c["server"]): c["reply_to_server_request"] for c in calls if "asked" in c}
        self.assertIn("declined", replies[("item/commandExecution/requestApproval", None)]["error"]["message"])
        self.assertEqual(replies[("mcpServer/elicitation/request", "relic_org")]["result"]["action"], "accept")
        self.assertIn("declined", replies[("mcpServer/elicitation/request", "other_server")]["error"]["message"])
        self.assertEqual([d["method"] for d in state["approvals"]["declined"]],
                         ["item/commandExecution/requestApproval", "mcpServer/elicitation/request"])
        self.assertEqual(state["approvals"]["accepted"][0]["server"], "relic_org")
        self.assertEqual(calls[0]["foo"], "bar")
        self.assertEqual(state["reply"], "Seated as a Codex member.")

        self.turn("bob", "Build the settings page")
        resumed = [c["params"] for c in self.calls("codex") if c.get("method") == "thread/resume"]
        self.assertEqual(resumed[0]["threadId"], "th-fake-1")

    def test_new_session_is_a_turnover(self):
        org = self.store.get(self.oid)
        first = self.turn("alice", runner.introduction(org, "alice"), new=True)["session"]
        second = self.turn("alice", runner.introduction(org, "alice"), new=True)["session"]
        seat = self.store.get(self.oid)["members"]["alice"]
        self.assertNotEqual(first, second)
        self.assertEqual((seat["carrier"], seat["past_carriers"], seat["carriers"]), (second, [first], 2))

    def test_open_commands_for_cli_and_gui(self):
        claude = dict(runner.default_config("claude-code"), model="opus", effort="high", permission="plan")
        args = runner.open_command(claude, "sid-1", "claude-code", "/w")
        self.assertEqual(args[1:], ["--resume", "sid-1", "--permission-mode", "plan", "--model", "opus", "--effort", "high"])
        args = runner.open_command(dict(claude, surface="gui"), "sid-1", "claude-code", "/w")
        self.assertEqual(args[1:], ["--desktop", "--resume", "sid-1"])
        codex = dict(runner.default_config("codex"), model="gpt-6-sol", effort="low")
        args = runner.open_command(codex, "th-1", "codex", "/w")
        self.assertEqual(args[1:], ["resume", "th-1", "-C", "/w", "-s", "workspace-write", "-a", "on-request",
                                    "-m", "gpt-6-sol", "-c", "model_reasoning_effort=low"] + runner.codex_overrides())
        self.assertEqual(runner.open_command(dict(codex, surface="gui"), "th-1", "codex", "/w"),
                         ["codex-url", "codex://threads/th-1"])

    def test_created_session_opens_for_the_person(self):
        state = self.turn("alice", "Introduce yourself", new=True)
        config = self.store.seat_config(self.oid, "alice")
        # Test the explicit open action without ever starting a native terminal.
        with mock.patch.object(runner.platform_support, "open_terminal") as terminal, \
                mock.patch.object(runner.subprocess, "Popen") as launch, \
                mock.patch.object(runner.shutil, "which", return_value="wt.exe"):
            args = runner.open_session(config, state["session"], "claude-code", str(self.ws))
        self.assertEqual(args[1:3], ["--resume", state["session"]])
        if sys.platform == "darwin":
            terminal.assert_called_once()
            self.assertEqual(terminal.call_args.args[:2], (args, str(self.ws)))
        else:
            launch.assert_called_once()

    def test_each_harness_keeps_its_own_models(self):
        for config in ({"harness": "claude-code", "model": "gpt-6-sol"},
                       {"harness": "codex", "model": "claude-opus-5-5"},
                       {"harness": "codex", "model": "opus"},
                       {"harness": "claude-code", "env": {"ANTHROPIC_BASE_URL": "http://localhost:4000"}}):
            with self.assertRaises(RuntimeError):
                runner.checked_model(config)
        self.assertEqual(runner.checked_model({"harness": "claude-code", "model": "claude-opus-5-5"}), "claude-opus-5-5")
        self.assertEqual(runner.checked_model({"harness": "codex", "model": "gpt-6-sol"}), "gpt-6-sol")

    def test_older_codex_without_the_automatic_reviewer(self):
        os.environ["FAKE_NO_REVIEWER"] = "1"
        org = self.store.get(self.oid)
        self.turn("bob", runner.introduction(org, "bob"), new=True)
        starts = [c["params"] for c in self.calls("codex") if c.get("method") == "thread/start"]
        self.assertEqual(["approvalsReviewer" in s for s in starts], [True, False])

    def test_silent_woken_turn_sends_a_receipt(self):
        from relic_core import wake
        org = self.store.get(self.oid)
        self.turn("bob", runner.introduction(org, "bob"), new=True)
        runner.start_turn(self.oid, "bob", wake.prompt(org, "bob", ["alice"], 1), wake_from=["alice"])
        deadline = time.time() + 30
        while runner.is_running(self.oid, "bob") or not any(
                m["body"].startswith(wake.RECEIPT_MARK) for m in self.store.history(self.oid)):
            self.assertLess(time.time(), deadline, "no receipt")
            time.sleep(0.1)
        receipt = [m for m in self.store.history(self.oid) if m["body"].startswith(wake.RECEIPT_MARK)][-1]
        self.assertEqual((receipt["from"], receipt["to"]), ("bob", ["alice"]))
        self.assertIn("the turn finished", receipt["body"])
        self.assertNotIn("Seated as a Codex member.", receipt["body"])
        self.assertEqual(runner.run_state(self.oid, "bob")["wake_from"], ["alice"])

    def test_unsafe_permissions_refused(self):
        for config in ({"harness": "claude-code", "permission": "bypassPermissions"},
                       {"harness": "codex", "permission": "danger-full-access"}):
            with self.assertRaises(RuntimeError):
                runner.checked_permission(config)


if __name__ == "__main__":
    unittest.main()
