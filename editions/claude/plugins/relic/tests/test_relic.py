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

from relic_core.store import OrgError, Store  # noqa: E402
import relic_hook  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "relic.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def team(self, governance="leader"):
        org = self.store.create("s1", "Team", "build a thing", "lead", "coordinator", governance)
        self.store.join("s1/a1", org["id"], "alice", "api")
        self.store.join("s1/a2", org["id"], "bob", "ui")
        return org["id"]


class StoreTests(Base):
    def test_turnover_keeps_role_drops_notes(self):
        oid = self.team()
        self.store.work("s1/a1", "note", {"body": "secret approach"})
        self.store.work("s1/a1", "task", {"title": "endpoint"})
        info = self.store.join("s1/a9", oid, "alice")
        self.assertTrue(info["carrier_replaced"])
        org = self.store.get(oid)
        self.assertEqual(org["members"]["alice"]["role"], "api")
        self.assertEqual(org["members"]["alice"]["notes"], [])
        self.assertEqual(org["tasks"]["T1"]["owner"], "alice")
        self.assertEqual(self.store.whoami("s1/a1"), (None, None))
        self.assertEqual(self.store.whoami("s1/a9")[1], "alice")

    def test_org_episode_includes_later_joiners(self):
        oid = self.team()
        ep = self.store.episode("s1", "open", {"title": "release"})
        self.store.join("s1/a3", oid, "carol")
        self.assertIn("carol", self.store.get(oid)["episodes"][ep["id"]]["participants"])

    def test_messages_delivered_once_to_recipients_only(self):
        self.team()
        self.store.send("s1/a1", ["bob"], "interface v1 ready")
        self.assertEqual(self.store.unread("s1", mark=False), [])
        got = self.store.unread("s1/a2")
        self.assertEqual([m["body"] for m in got], ["interface v1 ready"])
        self.assertEqual(self.store.unread("s1/a2"), [])

    def test_document_revision_conflict(self):
        self.team()
        self.store.work("s1/a1", "doc_write", {"key": "api", "body": "v1"})
        with self.assertRaises(OrgError):
            self.store.work("s1/a2", "doc_write", {"key": "api", "body": "v2", "expected_revision": 0})
        self.store.work("s1/a2", "doc_write", {"key": "api", "body": "v2", "expected_revision": 1})

    def test_weak_protocol_needs_evidence_and_threshold(self):
        self.team()
        with self.assertRaises(OrgError):
            self.store.protocol("s1/a1", "propose", {"title": "t", "rationale": "r", "guidance": "g", "trigger": "x"})
        p = self.store.protocol("s1/a1", "propose", {"title": "Announce interface changes", "rationale": "bob broke",
                                                     "guidance": "message owners first", "trigger": "editing shared API",
                                                     "evidence": ["msg 1"]})
        self.assertEqual(p["status"], "proposed")
        p = self.store.protocol("s1/a2", "vote", {"protocol_id": p["id"], "vote": "approve", "reason": "yes"})
        self.assertEqual(p["status"], "proposed")  # leader governance needs the leader
        p = self.store.protocol("s1", "vote", {"protocol_id": p["id"], "vote": "approve", "reason": "ok"})
        self.assertEqual(p["status"], "active")

    def test_peer_majority(self):
        oid = self.store.create("p1", "Peers", "x", "a", "", "peer")["id"]
        self.store.join("p2", oid, "b")
        self.store.join("p3", oid, "c")
        p = self.store.protocol("p1", "propose", {"title": "t", "rationale": "r", "guidance": "g", "trigger": "x", "evidence": ["e"]})
        self.assertEqual(p["status"], "proposed")
        p = self.store.protocol("p2", "vote", {"protocol_id": p["id"], "vote": "approve", "reason": "y"})
        self.assertEqual(p["status"], "active")

    def strong(self, rules):
        ep = self.store.episode("s1", "open", {"title": "integration", "participants": ["alice"]})
        self.store.episode("s1", "close", {"episode_id": ep["id"], "outcome": "failure", "summary": "x broke y"})
        self.store.episode("s1", "reflect", {"episode_id": ep["id"], "body": "y edited x's files"})
        p = self.store.protocol("s1", "propose", {"title": "rule", "rationale": "r", "strength": "strong",
                                                  "episode_id": ep["id"], "rules": rules})
        return self.store.protocol("s1/a1", "vote", {"protocol_id": p["id"], "vote": "approve", "reason": "y"})

    def test_strong_requires_reflected_episode(self):
        self.team()
        ep = self.store.episode("s1", "open", {"title": "e"})
        with self.assertRaises(OrgError):
            self.store.protocol("s1", "propose", {"title": "t", "rationale": "r", "strength": "strong",
                                                  "episode_id": ep["id"], "rules": [{"effect": "deny", "tools": ["Bash"]}]})

    def test_no_universal_veto(self):
        self.team()
        with self.assertRaises(OrgError):
            self.strong([{"effect": "deny", "tools": ["*"]}])

    def test_ownership_rule(self):
        self.team()
        p = self.strong([{"effect": "deny", "tools": ["Edit", "Write"], "path_glob": "src/api/*",
                          "except_roles": ["api"], "reason": "API belongs to the api owner"}])
        self.assertEqual(p["status"], "active")
        ok, _ = self.store.gate("s1/a1", "Edit", {"file_path": "/repo/src/api/x.py"})
        self.assertTrue(ok)
        ok, reasons = self.store.gate("s1/a2", "Edit", {"file_path": "/repo/src/api/x.py"})
        self.assertFalse(ok)
        self.assertIn("api owner", reasons[0])
        ok, _ = self.store.gate("s1/a2", "Edit", {"file_path": "/repo/src/ui/x.py"})
        self.assertTrue(ok)

    def test_review_rule(self):
        self.team()
        self.strong([{"effect": "require_review", "tools": ["Bash"], "input_contains": ["git push"]}])
        call = {"command": "git push origin main"}
        ok, reasons = self.store.gate("s1/a2", "Bash", call)
        self.assertFalse(ok)
        rid = reasons[0].split("Review request ")[1].split(" ")[0]
        with self.assertRaises(OrgError):
            self.store.review("s1/a2", "approve", {"request_id": rid, "note": "self"})
        self.store.review("s1/a1", "approve", {"request_id": rid, "note": "tests pass"})
        ok, _ = self.store.gate("s1/a2", "Bash", call)
        self.assertTrue(ok)
        ok, _ = self.store.gate("s1/a2", "Bash", call)  # one approval, one use
        self.assertFalse(ok)

    def test_require_before(self):
        self.team()
        self.strong([{"effect": "require_before", "tools": ["Bash"], "input_contains": ["git commit"],
                      "before": {"tools": ["Bash"], "input_contains": ["pytest"]}}])
        self.store.record_activity("s1/a2", "Edit", {"file_path": "a.py"})
        time.sleep(0.01)
        ok, _ = self.store.gate("s1/a2", "Bash", {"command": "git commit -m x"})
        self.assertFalse(ok)
        self.store.record_activity("s1/a2", "Bash", {"command": "pytest -q"}, failed=True)
        ok, _ = self.store.gate("s1/a2", "Bash", {"command": "git commit -m x"})
        self.assertFalse(ok)
        self.store.record_activity("s1/a2", "Bash", {"command": "pytest -q"})
        ok, _ = self.store.gate("s1/a2", "Bash", {"command": "git commit -m x"})
        self.assertTrue(ok)

    def test_revision_and_retirement(self):
        self.team()
        p = self.store.protocol("s1", "propose", {"title": "v1", "rationale": "r", "guidance": "g", "trigger": "t", "evidence": ["e"]})
        p = self.store.protocol("s1/a1", "vote", {"protocol_id": p["id"], "vote": "approve", "reason": "y"})
        q = self.store.protocol("s1/a2", "propose", {"title": "v2", "rationale": "r", "guidance": "g2", "trigger": "t",
                                                     "evidence": ["e"], "supersedes": p["id"]})
        self.store.protocol("s1", "vote", {"protocol_id": q["id"], "vote": "approve", "reason": "y"})
        org = self.store.get(self.store.whoami("s1")[0]["id"])
        self.assertEqual(org["protocols"][p["id"]]["status"], "superseded")
        self.assertEqual(org["protocols"][q["id"]]["version"], 2)
        r = self.store.protocol("s1", "propose", {"title": "retire", "rationale": "obsolete", "retire_target": q["id"]})
        self.store.protocol("s1/a1", "vote", {"protocol_id": r["id"], "vote": "approve", "reason": "y"})
        org = self.store.get(org["id"])
        self.assertEqual(org["protocols"][q["id"]]["status"], "retired")


class HookTests(Base):
    def run_hook(self, event):
        return relic_hook.handle(event, self.store)

    def test_actor_injected_for_relic_tools(self):
        out = self.run_hook({"hook_event_name": "PreToolUse", "session_id": "s1", "agent_id": "a7",
                             "tool_name": "mcp__plugin_relic_org__status", "tool_input": {"actor": "forged"}})
        self.assertEqual(out["hookSpecificOutput"]["updatedInput"]["actor"], "s1/a7")

    def test_gate_and_message_delivery(self):
        oid = self.team()
        self.store.send("s1", ["alice"], "please rebase")
        out = self.run_hook({"hook_event_name": "PostToolUse", "session_id": "s1", "agent_id": "a1",
                             "tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertIn("please rebase", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.run_hook({"hook_event_name": "PostToolUse", "session_id": "s1", "agent_id": "a1",
                                        "tool_name": "Bash", "tool_input": {"command": "ls"}}), {})

    def test_env_join_and_context(self):
        oid = self.team()
        os.environ.update(RELIC_ORG=oid, RELIC_MEMBER="carol")
        try:
            out = self.run_hook({"hook_event_name": "SessionStart", "session_id": "peer-3", "source": "startup"})
        finally:
            del os.environ["RELIC_ORG"], os.environ["RELIC_MEMBER"]
        self.assertIn("member 'carol'", out["hookSpecificOutput"]["additionalContext"])

    def test_stop_asks_for_reflection_once(self):
        self.team()
        ep = self.store.episode("s1", "open", {"title": "e", "participants": ["alice"]})
        self.store.episode("s1", "close", {"episode_id": ep["id"], "outcome": "success", "summary": "ok"})
        out = self.run_hook({"hook_event_name": "SubagentStop", "session_id": "s1", "agent_id": "a1"})
        self.assertEqual(out["decision"], "block")
        self.assertEqual(self.run_hook({"hook_event_name": "SubagentStop", "session_id": "s1", "agent_id": "a1",
                                        "stop_hook_active": True}), {})

    def test_friction_turn_asks_for_reflection(self):
        self.team()
        self.run_hook({"hook_event_name": "PostToolUse", "session_id": "s1", "agent_id": "a1", "tool_name": "Bash",
                       "tool_input": {"command": "git push"}, "tool_response": {"stdout": "", "stderr": " ! [rejected] main -> main (fetch first)"}})
        out = self.run_hook({"hook_event_name": "SubagentStop", "session_id": "s1", "agent_id": "a1"})
        self.assertEqual(out["decision"], "block")
        self.assertIn("rejected", out["reason"])

    def test_quiet_turn_needs_no_reflection(self):
        self.team()
        self.run_hook({"hook_event_name": "PostToolUse", "session_id": "s1", "agent_id": "a2", "tool_name": "Bash",
                       "tool_input": {"command": "ls"}, "tool_response": {"stdout": "ok", "stderr": ""}})
        self.assertEqual(self.run_hook({"hook_event_name": "SubagentStop", "session_id": "s1", "agent_id": "a2"}), {})

    def test_non_member_is_untouched(self):
        self.assertEqual(self.run_hook({"hook_event_name": "PreToolUse", "session_id": "x", "tool_name": "Bash",
                                        "tool_input": {"command": "rm -rf /tmp/x"}}), {})


class ServerTests(Base):
    def test_stdio_roundtrip(self):
        env = dict(os.environ, RELIC_HOME=self.tmp.name)
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "create", "arguments": {
                "name": "T", "purpose": "p", "member": "lead", "actor": "s9"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "status", "arguments": {"actor": "s9"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "status", "arguments": {"actor": "nobody"}}},
        ]
        proc = subprocess.run([sys.executable, str(ROOT / "server.py")], input="\n".join(json.dumps(l) for l in lines),
                              capture_output=True, text=True, env=env, timeout=30)
        replies = {r["id"]: r for r in map(json.loads, proc.stdout.splitlines())}
        self.assertEqual(len(replies[2]["result"]["tools"]), 9)
        self.assertIn("member 'lead'", replies[4]["result"]["content"][0]["text"])
        self.assertTrue(replies[5]["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
