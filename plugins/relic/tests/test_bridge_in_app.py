"""The Relic App as the bridge: every session it runs gets Relic from the App (app/harness.py relic_for), whatever is
installed in its harness; a session is named by the seat it holds (relic_core.api.seat_actor); and for a harness
without Relic hooks the App allows the organization's own tools, checks strong protocols at permission requests,
records finished tool calls as activity and closes the turn (app/hub.py)."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import harness as harnesses  # noqa: E402
from app import hub as hubs  # noqa: E402
from relic_core import api  # noqa: E402
from relic_core.store import HUMAN, Store, harness_of  # noqa: E402

FAKE = Path(__file__).resolve().parent / "fake_acp_agent.py"
LEAD, ANA = "lead-session", "ana-session"
# A harness that speaks ACP itself and has no Relic hooks, as Kimi Code or CodeBuddy would be.
FAKE_SPEC = {"title": "Fake", "vendor": "Tests", "command": lambda: sys.executable, "args": ["-X", "utf8", str(FAKE)],
             "actor": lambda sid: "fakeh:" + sid, "relic": "mcp", "default_mode": ""}


def wait_for(check, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("timed out waiting")


class Isolated(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        for key in harnesses.INHERITED:
            os.environ.pop(key, None)
        self.home = Path(self.tmp.name)
        os.environ["RELIC_HOME"] = str(self.home / "relic")
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.home / "claude")
        os.environ["CODEX_HOME"] = str(self.home / "codex")
        self.store = Store()
        self.oid = self.store.create(LEAD, "Demo", "build a demo", "lead", "lead role")["id"]
        self.store.join(ANA, self.oid, "ana", "frontend")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def seat(self, member):
        return self.store.get(self.oid)["members"].get(member) or {}


class Identity(Isolated):
    def test_a_seat_server_speaks_for_the_seat_s_current_carrier(self):
        self.store.set_config(self.oid, "ana", {"harness": "codex", "surface": "acp", "seat_token": "t1"})
        os.environ.update(RELIC_SEAT=self.oid + "/ana", RELIC_SEAT_TOKEN="t1")
        self.assertEqual(api.actor_of({}, None, self.store), ANA)
        self.assertEqual(api.call(self.store, "status", {})["member"], "ana")
        self.assertEqual(api.actor_of({"actor": "s1/agent"}, None, self.store), "s1/agent")  # a hook stamp still wins
        self.assertEqual(api.actor_of({}, {"threadId": "th"}, self.store), "codex:th")  # so does a Codex thread
        # a new session of the seat has a new token: the old session's server speaks for nobody
        self.store.set_config(self.oid, "ana", {"harness": "codex", "surface": "acp", "seat_token": "t2"})
        self.assertEqual(api.actor_of({}, None, self.store), "local")
        os.environ["RELIC_SEAT"] = self.oid + "/nobody"
        self.assertEqual(api.actor_of({}, None, self.store), "local")

    def test_an_actor_s_prefix_names_its_harness(self):
        self.assertEqual(harness_of("kimi:abc"), "kimi")
        self.assertEqual(harness_of("codex:parent/child"), "codex")
        self.assertEqual(harness_of("claude-chat:helper"), "claude-chat")
        self.assertEqual(harness_of("4f0c2a52-5e0d-4d39-9e1a-1f2b3c4d5e6f"), "claude-code")
        self.assertEqual(harness_of("C:/work/session"), "claude-code")
        self.assertEqual(harness_of(""), "claude-code")


class Bringing(Isolated):
    def test_claude_code_sessions_load_this_plugin_and_turn_off_installed_copies(self):
        claude = self.home / "claude"
        (claude / "plugins").mkdir(parents=True)
        (claude / "settings.json").write_text(json.dumps(
            {"enabledPlugins": {"relic@relic-bridge": True, "other@market": True}}), encoding="utf-8")
        (claude / "plugins" / "installed_plugins.json").write_text(json.dumps(
            {"version": 2, "plugins": {"relic@relic-claude": [{"scope": "user"}], "other@market": []}}), encoding="utf-8")
        servers, meta = harnesses.relic_for("claude-code", self.oid, "ana", "tok")
        self.assertEqual(servers, [])
        options = meta["claudeCode"]["options"]
        self.assertEqual(options["plugins"], [{"type": "local", "path": str(harnesses.PLUGIN_ROOT)}])
        self.assertTrue((harnesses.PLUGIN_ROOT / ".claude-plugin" / "plugin.json").is_file())
        self.assertEqual(options["settings"]["enabledPlugins"], {"relic@relic-bridge": False, "relic@relic-claude": False})
        self.assertEqual((options["env"]["RELIC_SEAT"], options["env"]["RELIC_SEAT_TOKEN"]), (self.oid + "/ana", "tok"))
        self.assertTrue(harnesses.has_hooks("claude-code"))

    def test_other_harnesses_get_the_relic_server_named_for_their_seat(self):
        self.store.set_config(self.oid, "ana", {"harness": "codex", "surface": "acp", "seat_token": "tok"})
        servers, meta = harnesses.relic_for("codex", self.oid, "ana", "tok")
        self.assertIsNone(meta)
        server = servers[0]
        self.assertEqual(server["name"], "relic_org")  # tools mcp__relic_org__*, recognised as Relic's own
        self.assertEqual(Path(server["args"][-1]), harnesses.PLUGIN_ROOT / "server.py")
        env = {e["name"]: e["value"] for e in server["env"]}
        self.assertEqual((env["RELIC_SEAT"], env["RELIC_SEAT_TOKEN"]), (self.oid + "/ana", "tok"))
        self.assertEqual(Path(env["RELIC_HOME"]), self.home / "relic")
        # the server started exactly so answers as the seat
        lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                 {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "status", "arguments": {}}}]
        done = subprocess.run([server["command"]] + server["args"], input="\n".join(json.dumps(x) for x in lines) + "\n",
                              capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
        replies = {r["id"]: r for r in map(json.loads, done.stdout.splitlines()) if "id" in r}
        self.assertIn("Relic App runs it", replies[1]["result"]["instructions"])
        self.assertIn('"member": "ana"', replies[2]["result"]["content"][0]["text"])

    def test_a_codex_with_the_relic_plugin_serves_its_sessions_itself(self):
        self.assertFalse(harnesses.has_hooks("codex"))  # no plugin: the App gives the server and does the hooks' work
        (self.home / "codex").mkdir()
        (self.home / "codex" / "config.toml").write_text(
            '[plugins."relic@relic-bridge"]\nenabled = true\n\n'
            '[hooks.state."relic@relic-bridge:hooks/hooks.json:pre_tool_use:0:0"]\ntrusted_hash = "sha256:x"\n',
            encoding="utf-8")
        self.assertEqual(harnesses.relic_for("codex", self.oid, "ana", "tok"), ([], None))  # one relic_org server
        self.assertTrue(harnesses.has_hooks("codex"))
        (self.home / "codex" / "config.toml").write_text('[plugins."relic@relic-bridge"]\nenabled = false\n', encoding="utf-8")
        self.assertEqual(harnesses.relic_for("codex", self.oid, "ana", "tok")[0][0]["name"], "relic_org")

    def test_relic_s_own_calls_are_recognised_as_each_adapter_names_them(self):
        relic = hubs.relic_call
        self.assertTrue(relic({"title": "mcp__plugin_relic_org__message", "kind": "other"}))  # Claude Code, plugin
        self.assertTrue(relic({"title": "mcp__relic_org__status", "kind": "other"}))  # Claude Code, App's server
        self.assertTrue(relic({"kind": "execute", "title": "mcp.relic_org.inbox",  # Codex
                               "rawInput": {"server": "relic_org", "tool": "inbox", "arguments": {}}}))
        self.assertTrue(relic({"toolCallId": "elicitation:s1:relic_org:2", "kind": "execute"}))  # Codex approval
        self.assertFalse(relic({"kind": "execute", "title": "grep relic_org notes.txt",
                                "rawInput": {"command": "grep relic_org notes.txt"}}))
        self.assertFalse(relic({"kind": "edit", "title": "Write mcp__relic_org__notes.md"}))
        self.assertFalse(relic({"kind": "execute", "title": "mcp.other.run", "rawInput": {"server": "other"}}))
        self.assertEqual(hubs.acp_call({"kind": "execute", "rawInput": {"command": ["git", "push"]}})[0], "Bash")
        self.assertEqual(hubs.acp_call({"kind": "edit", "locations": [{"path": "a.py"}]}),
                         ("Edit", {"file_path": "a.py"}))

    def test_launch_names_the_seat_and_drops_what_names_another_session(self):
        os.environ.update(CODEX_THREAD_ID="leak", PLUGIN_ROOT="elsewhere", RELIC_ACTOR="someone", CLAUDECODE="1")
        with mock.patch.dict(harnesses.HARNESSES, {"fakeh": FAKE_SPEC}):
            argv, env = harnesses.launch("fakeh", harnesses.seat_env(self.oid, "ana", "tok"))
            self.assertTrue(harnesses.installed("fakeh"))
            self.assertFalse(harnesses.has_hooks("fakeh"))
        self.assertEqual(argv, [sys.executable, "-X", "utf8", str(FAKE)])
        for key in ("CODEX_THREAD_ID", "PLUGIN_ROOT", "RELIC_ACTOR", "CLAUDECODE"):
            self.assertNotIn(key, env)
        self.assertEqual((env["RELIC_SEAT"], env["RELIC_SEAT_TOKEN"]), (self.oid + "/ana", "tok"))


class Hookless(Isolated):
    """A harness without Relic hooks, run by the App's hub."""

    def setUp(self):
        super().setUp()
        self.log = self.home / "acp.log"
        os.environ["FAKE_ACP_LOG"] = str(self.log)
        self.spec = mock.patch.dict(harnesses.HARNESSES, {"fakeh": FAKE_SPEC})
        self.spec.start()
        self.hub = hubs.Hub(store=self.store)

    def tearDown(self):
        self.hub.shutdown()
        self.spec.stop()
        super().tearDown()

    def logged(self, method):
        if not self.log.is_file():
            return None
        entries = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line.strip()]
        return next((e for e in entries if e["method"] == method), None)

    def replies(self, text):
        return [m for m in self.store.history(self.oid, 200)
                if m["from"] == "helper" and m["to"] == [HUMAN] and text in m["body"]]

    def assistant_said(self, text):
        return [i for i in self.hub.items(self.oid, "helper") if i["type"] == "assistant" and text in i["text"]]

    def add_helper(self):
        self.hub.create_member(self.oid, "helper", "assistant", "fakeh")
        wait_for(lambda: self.replies("echo:"))  # the introduction turn is over

    def adopt_rule(self, rule):
        ep = self.store.episode(LEAD, "open", {"title": "notes", "participants": ["lead"]})
        self.store.episode(LEAD, "close", {"episode_id": ep["id"], "outcome": "failure", "summary": "notes overwritten"})
        self.store.episode(LEAD, "reflect", {"episode_id": ep["id"], "body": "someone wrote over the lead's notes"})
        p = self.store.protocol(LEAD, "propose", {"title": "notes", "rationale": "r", "strength": "strong",
                                                  "episode_id": ep["id"], "rules": [rule]})
        p = self.store.protocol(ANA, "vote", {"protocol_id": p["id"], "vote": "approve", "reason": "yes"})
        self.assertEqual(p["status"], "active")

    def test_the_session_gets_the_relic_server_and_holds_its_seat(self):
        os.environ["CODEX_THREAD_ID"] = "the-session-that-started-the-app"
        self.add_helper()
        seat = self.seat("helper")
        entry = self.logged("session/new")
        self.assertEqual([s["name"] for s in entry["params"]["mcpServers"]], ["relic_org"])
        env = {e["name"]: e["value"] for e in entry["params"]["mcpServers"][0]["env"]}
        self.assertEqual((env["RELIC_SEAT"], env["RELIC_SEAT_TOKEN"]), (self.oid + "/helper", seat["config"]["seat_token"]))
        self.assertEqual(entry["env"]["RELIC_SEAT"], self.oid + "/helper")  # the agent process knows its seat too
        self.assertIsNone(entry["env"]["CODEX_THREAD_ID"])
        self.assertEqual(harness_of(seat["carrier"]), "fakeh")
        self.assertEqual(seat["carrier"], "fakeh:" + seat["config"]["session"])

    def test_finished_tool_calls_become_activity_and_the_turn_closes(self):
        self.add_helper()
        with self.store.db() as db:
            rows = db.execute("SELECT tool, kind FROM activity WHERE org_id=? AND member=?",
                              (self.oid, "helper")).fetchall()
        self.assertIn(("Read", "other"), [tuple(r) for r in rows])

        def closed():  # the turn closes after its reply reaches the person
            turns = [e for e in self.store.get(self.oid)["episodes"].values()
                     if e.get("kind") == "turn" and e["owner"] == "helper"]
            return turns and all(e["status"] == "closed" for e in turns)
        self.assertTrue(wait_for(closed))

    def test_relic_tools_are_allowed_and_a_strong_protocol_blocks_an_edit(self):
        self.adopt_rule({"effect": "deny", "tools": ["Edit"], "path_glob": "*notes.txt",
                         "reason": "the notes belong to the lead"})
        self.add_helper()
        self.hub.prompt(self.oid, "helper", "relic permission please", {"kind": "human", "text": "relic permission"})
        wait_for(lambda: self.replies("[permission: allow]"))
        self.hub.prompt(self.oid, "helper", "needs permission to write", {"kind": "human", "text": "write notes"})
        wait_for(lambda: self.replies("[permission: reject]"))
        self.assertEqual(self.hub.permissions(self.oid), [])  # nothing waited for the person
        self.assertTrue(any(i["type"] == "error" and "Relic 协议拦下了" in i["text"]
                            for i in self.hub.items(self.oid, "helper")))
        # the session hears why at the start of its next turn (here the reflection the blocked action made due)
        said = wait_for(lambda: self.assistant_said("Relic protocol blocked Edit"))
        self.assertIn("the notes belong to the lead", said[0]["text"])
        self.assertTrue(wait_for(lambda: self.assistant_said("reflect on episode")))


if __name__ == "__main__":
    unittest.main()
