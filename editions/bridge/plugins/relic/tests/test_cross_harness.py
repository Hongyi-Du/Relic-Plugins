"""One organization, members on Claude Code and Codex. Hook events below follow each harness's real contract:
Codex reports shell as Bash with tool_input.command, file edits as apply_patch with the patch in command,
and exports PLUGIN_ROOT to plugin hooks."""
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "hooks"))

from relic_core.store import Store, normalize  # noqa: E402
import relic_hook  # noqa: E402


@contextlib.contextmanager
def codex():
    os.environ["PLUGIN_ROOT"] = str(ROOT)
    try:
        yield
    finally:
        del os.environ["PLUGIN_ROOT"]


def patch(*paths):
    body = ["*** Begin Patch"]
    for p in paths:
        body += ["*** Update File: " + p, "@@", "-old", "+new"]
    return "\n".join(body + ["*** End Patch"])


class CrossHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "relic.sqlite3")
        # Claude Code lead with a Claude Code subagent member; a Codex chat takes the seat "cody".
        org = self.store.create("cc-1", "Mixed", "ship the API", "lead", "coordinator")
        self.oid = org["id"]
        self.store.join("cc-1/a1", self.oid, "alice", "api")
        ws = Path(self.tmp.name) / "codex-workspace" / "repo"
        ws.mkdir(parents=True)
        (ws.parent / ".relic-seat.json").write_text(json.dumps({"org": self.oid, "member": "cody", "role": "ui"}))
        with codex():
            self.start = self.hook({"hook_event_name": "SessionStart", "session_id": "th-9", "cwd": str(ws)})

    def tearDown(self):
        self.tmp.cleanup()

    def hook(self, event):
        return relic_hook.handle(event, self.store)

    def codex_call(self, tool, command, post=True):
        with codex():
            pre = self.hook({"hook_event_name": "PreToolUse", "session_id": "th-9", "turn_id": "t1",
                             "tool_name": tool, "tool_input": {"command": command}})
            denied = pre.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
            if post and not denied:
                self.hook({"hook_event_name": "PostToolUse", "session_id": "th-9", "turn_id": "t1",
                           "tool_name": tool, "tool_input": {"command": command}, "tool_response": {"exit_code": 0}})
        return pre

    def strong(self, rules):
        ep = self.store.episode("cc-1", "open", {"title": "release"})
        self.store.episode("cc-1", "close", {"episode_id": ep["id"], "outcome": "partial", "summary": "clash"})
        self.store.episode("cc-1", "reflect", {"episode_id": ep["id"], "body": "cody edited the API"})
        p = self.store.protocol("cc-1", "propose", {"title": "rule", "rationale": "r", "strength": "strong",
                                                    "episode_id": ep["id"], "rules": rules})
        p = self.store.protocol("cc-1/a1", "vote", {"protocol_id": p["id"], "vote": "approve", "reason": "y"})
        self.assertEqual(p["status"], "active")

    def test_codex_seat_from_workspace_file(self):
        org = self.store.get(self.oid)
        self.assertEqual(org["members"]["cody"]["harness"], "codex")
        self.assertEqual(org["members"]["alice"]["harness"], "claude-code")
        self.assertEqual(self.store.whoami("codex:th-9")[1], "cody")
        ctx = self.start["hookSpecificOutput"]["additionalContext"]
        self.assertIn("cody[ui](codex)", ctx)
        self.assertIn("mcp__relic_org__", ctx)
        self.assertIn("apply_patch counts as Edit", ctx)

    def test_claude_rule_blocks_codex_patch(self):
        self.strong([{"effect": "deny", "tools": ["Edit", "Write"], "path_glob": "src/api/*",
                      "except_roles": ["api"], "reason": "API belongs to alice"}])
        out = self.codex_call("apply_patch", patch("src/ui/app.py", "src/api/routes.py"))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("alice", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(self.codex_call("apply_patch", patch("src/ui/app.py")), {})
        # The owner on Claude Code is not blocked by the same rule.
        self.assertEqual(self.hook({"hook_event_name": "PreToolUse", "session_id": "cc-1", "agent_id": "a1",
                                    "tool_name": "Edit", "tool_input": {"file_path": "/r/src/api/routes.py"}}), {})

    def test_require_before_on_codex(self):
        self.strong([{"effect": "require_before", "tools": ["Bash"], "input_contains": ["git commit"],
                      "before": {"tools": ["Bash"], "input_contains": ["pytest"]}}])
        self.codex_call("apply_patch", patch("src/ui/app.py"))
        time.sleep(0.01)
        self.assertEqual(self.codex_call("Bash", "git commit -m ui", post=False)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.codex_call("Bash", "pytest -q")
        self.assertEqual(self.codex_call("Bash", "git commit -m ui", post=False), {})
        # Codex unified exec arrives as exec_command with cmd: same vocabulary.
        self.assertEqual(normalize("exec_command", {"cmd": "pytest"}), ("Bash", {"cmd": "pytest", "command": "pytest"}))

    def test_claude_member_reviews_codex_push(self):
        self.strong([{"effect": "require_review", "tools": ["Bash"], "input_contains": ["git push"]}])
        out = self.codex_call("Bash", "git push origin ui", post=False)
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        rid = reason.split("Review request ")[1].split(" ")[0]
        self.store.review("cc-1/a1", "approve", {"request_id": rid, "note": "diff checked"})
        self.assertEqual(self.codex_call("Bash", "git push origin ui", post=False), {})

    def test_messages_cross_both_ways(self):
        self.store.send("codex:th-9", ["alice"], "ui needs /v2/items")
        out = self.hook({"hook_event_name": "PostToolUse", "session_id": "cc-1", "agent_id": "a1",
                         "tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertIn("/v2/items", out["hookSpecificOutput"]["additionalContext"])
        self.store.send("cc-1/a1", ["cody"], "shipped /v2/items")
        out = self.codex_call("Bash", "ls")
        with codex():
            out = self.hook({"hook_event_name": "UserPromptSubmit", "session_id": "th-9"})
        self.assertIn("member 'cody'", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.store.unread("codex:th-9"), [])  # delivered at the PostToolUse above

    def test_seat_passes_from_claude_to_codex(self):
        info = self.store.join("codex:th-42", self.oid, "alice")
        self.assertTrue(info["carrier_replaced"])
        seat = self.store.get(self.oid)["members"]["alice"]
        self.assertEqual((seat["role"], seat["harness"], seat["harness_history"]), ("api", "codex", ["claude-code", "codex"]))
        ev = self.store.events(self.oid, ["member.carrier_replaced"])[-1]["body"]
        self.assertEqual((ev["from_harness"], ev["to_harness"]), ("claude-code", "codex"))

    def test_codex_actor_stamped_on_relic_tools(self):
        with codex():
            out = self.hook({"hook_event_name": "PreToolUse", "session_id": "th-9", "tool_name": "mcp__relic_org__status",
                             "tool_input": {}})
        self.assertEqual(out["hookSpecificOutput"]["updatedInput"]["actor"], "codex:th-9")

    def test_codex_subagent_stays_in_parent_seat(self):
        with codex():
            out = self.hook({"hook_event_name": "SubagentStart", "session_id": "th-9", "agent_id": "x1"})
        self.assertIn("seat 'cody'", out["hookSpecificOutput"]["additionalContext"])

    def test_server_identity_from_codex_thread(self):
        env = dict(os.environ, RELIC_HOME=self.tmp.name)
        lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                 {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                  "params": {"name": "status", "arguments": {}, "_meta": {"openai/threadId": "th-9"}}}]
        proc = subprocess.run([sys.executable, str(ROOT / "server.py")], input="\n".join(json.dumps(l) for l in lines),
                              capture_output=True, text=True, env=env, timeout=30)
        replies = {r["id"]: r for r in map(json.loads, proc.stdout.splitlines())}
        self.assertIn("member 'cody'", replies[2]["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
