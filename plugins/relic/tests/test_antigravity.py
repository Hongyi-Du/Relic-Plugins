"""Antigravity (Google's agent app) as a Relic harness: its plugin, its hooks translated to Relic's (identity on Relic
tool calls, context and messages before model calls, the Stop that goes on), and wake-ups through the app's local
endpoint. No real Antigravity is reached: RELIC_GEMINI_DIR points at a folder of the test's own."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core import antigravity, runner, wake  # noqa: E402
from relic_core.store import Store  # noqa: E402

spec = importlib.util.spec_from_file_location("antigravity_hook", ROOT / "hooks" / "antigravity_hook.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

CID = "7b9adeca-6444-48fe-a73c-a5a140404c13"
ACTOR = "antigravity:" + CID


class Antigravity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.gemini = Path(self.tmp.name) / ".gemini"
        env = mock.patch.dict(os.environ, {"RELIC_HOME": str(Path(self.tmp.name) / "relic"),
                                           "RELIC_GEMINI_DIR": str(self.gemini), "RELIC_HARNESS": "antigravity"})
        env.start()
        self.addCleanup(env.stop)
        away = mock.patch.object(hook.relic_hook, "away_member", lambda store, actor: None)
        away.start()
        self.addCleanup(away.stop)
        self.store = Store()
        self.oid = self.store.create("lead-s", "Team", "build", "lead")["id"]
        self.store.add_seat(self.oid, "hajimi", config=runner.default_config("antigravity"))
        self.store.join(ACTOR, self.oid, "hajimi")
        self.path = antigravity.transcript_path(CID)
        self.path.parent.mkdir(parents=True)

    def steps(self, *steps):
        with open(self.path, "a", encoding="utf-8") as f:
            for step in steps:
                f.write(json.dumps(step, ensure_ascii=False) + "\n")

    def hook(self, name, **fields):
        event = dict({"hookEventName": name, "conversationId": CID, "transcriptPath": str(self.path), "cwd": ""},
                     **fields)
        return hook.answer(event, hook.relic_event(event), self.store)

    # ---------------- the plugin ----------------

    def test_the_plugin_brings_the_relic_server_and_hooks_and_asks_nothing_of_other_tools(self):
        files = antigravity.plugin_files(ROOT, "1.2.3")
        hooks = json.loads(files["hooks.json"])["relic"]
        self.assertEqual([g["matcher"] for g in hooks["PreToolUse"]], ["call_mcp_tool"])
        self.assertEqual(set(hooks), {"SessionStart", "PreInvocation", "PreToolUse", "PostToolUse", "Stop"})
        self.assertIn("antigravity_hook.py", hooks["SessionStart"][0]["command"])
        server = json.loads(files["mcp_config.json"])["mcpServers"]["relic_org"]
        self.assertTrue(server["args"][-1].endswith("server.py"))
        self.assertEqual(server["env"], {"RELIC_HARNESS": "antigravity", "RELIC_ACTOR": "antigravity:unhooked"})
        self.assertEqual(json.loads(files["plugin.json"])["version"], "1.2.3")
        self.assertIn("call_mcp_tool", files["rules/AGENTS.md"])
        folder = antigravity.install_plugin(ROOT, "1.2.3")
        self.assertEqual(folder, self.gemini / "config" / "plugins" / "relic")
        self.assertEqual((folder / "hooks.json").read_text(encoding="utf-8"), files["hooks.json"])
        self.assertTrue((folder / "rules" / "AGENTS.md").is_file())

    def test_a_test_run_never_reaches_the_persons_antigravity(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("RELIC_GEMINI_DIR")
            self.assertIsNone(antigravity.gemini_dir())
            self.assertFalse(antigravity.installed())
            self.assertIsNone(antigravity.hub())
            with self.assertRaises(RuntimeError):
                antigravity.install_plugin(ROOT)

    # ---------------- the hooks ----------------

    def test_a_relic_tool_call_is_allowed_with_the_conversations_actor_and_others_keep_the_apps_rule(self):
        relic = {"name": "call_mcp_tool", "args": {"ServerName": "relic_relic_org", "ToolName": "status",
                                                   "Arguments": {"org": "Team"}}}
        out = self.hook("PreToolUse", toolCall=relic)
        self.assertEqual(out["decision"], "allow")
        self.assertEqual(out["overwrite"], {"Arguments": {"org": "Team", "actor": ACTOR}})
        other = {"name": "call_mcp_tool", "args": {"ServerName": "github_github", "ToolName": "list_prs",
                                                   "Arguments": {}}}
        self.assertEqual(self.hook("PreToolUse", toolCall=other), {"decision": "ask"})
        # a conversation without a seat gets its own actor too, so that its join takes the seat for it
        out = self.hook("PreToolUse", conversationId="new-conv", toolCall=relic)
        self.assertEqual(out["overwrite"]["Arguments"]["actor"], "antigravity:new-conv")

    def test_tools_reach_relics_vocabulary(self):
        self.assertEqual(hook.relic_tool({"name": "run_command", "args": {"CommandLine": "git push", "Cwd": "x"}}),
                         ("Bash", {"command": "git push", "Cwd": "x"}))
        self.assertEqual(hook.relic_tool({"name": "call_mcp_tool", "args": {"ServerName": "relic_relic_org",
                                                                            "ToolName": "inbox", "Arguments": {}}}),
                         ("mcp__relic_org__inbox", {}))
        self.assertEqual(hook.relic_tool({"name": "call_mcp_tool", "args": {"ServerName": "a_b", "ToolName": "c"}})[0],
                         "mcp__a_b__c")

    def test_the_persons_prompt_starts_a_turn_with_context_and_is_kept_as_their_words(self):
        self.steps({"step_index": 0, "type": "USER_INPUT",
                    "content": "<USER_REQUEST>\n给大家报一下进度\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nt\n</ADDITIONAL_METADATA>"})
        self.store.send("lead-s", ["hajimi"], "the API contract is in the docs")
        out = self.hook("PreInvocation", invocationNum=0, initialNumSteps=1, lastUserInput="给大家报一下进度")
        text = out["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("Team", text)
        self.assertIn("the API contract is in the docs", text)
        self.assertEqual([w["text"] for w in self.store.said(self.oid)], ["给大家报一下进度"])
        self.assertEqual(self.store.unread(ACTOR, mark=False), [])  # delivered: marked read

    def test_a_wake_up_starts_a_turn_but_is_not_the_persons_words(self):
        self.steps({"step_index": 0, "type": "USER_INPUT", "content": "<USER_REQUEST>\nhello\n</USER_REQUEST>"},
                   {"step_index": 1, "type": "PLANNER_RESPONSE", "content": "hi"},
                   {"step_index": 2, "type": "SYSTEM_MESSAGE", "content": "<SYSTEM_MESSAGE>\nReminder: work efficiently."
                                                                          "\n</SYSTEM_MESSAGE>"},
                   {"step_index": 3, "type": "SYSTEM_MESSAGE", "content": "<SYSTEM_MESSAGE>\n[Message] timestamp=t "
                    "sender=system priority=MESSAGE_PRIORITY_HIGH content=[Relic auto-wake] You hold the seat 'hajimi'"
                    "\n</SYSTEM_MESSAGE>"})
        relic = hook.relic_event({"hookEventName": "PreInvocation", "conversationId": CID, "invocationNum": 0,
                                  "initialNumSteps": 4, "transcriptPath": str(self.path), "lastUserInput": "hello"})
        self.assertEqual(relic["hook_event_name"], "UserPromptSubmit")
        self.assertIn("[Relic auto-wake] You hold the seat 'hajimi'", relic["prompt"])
        self.assertNotIn("hello", relic["prompt"])  # the last thing the person typed did not start this turn
        self.hook("PreInvocation", invocationNum=0, initialNumSteps=4, lastUserInput="hello")
        self.assertEqual(self.store.said(self.oid), [])

    def test_messages_that_arrive_during_a_turn_come_before_the_next_model_call(self):
        self.assertEqual(self.hook("PreInvocation", invocationNum=2), {})
        self.store.send("lead-s", ["hajimi"], "stop editing the schema")
        out = self.hook("PreInvocation", invocationNum=3)
        self.assertIn("stop editing the schema", out["injectSteps"][0]["systemMessage"]["systemMessage"])
        self.assertEqual(self.hook("PreInvocation", invocationNum=4), {})

    def test_after_a_tool_the_activity_is_kept_and_no_message_is_taken(self):
        self.store.send("lead-s", ["hajimi"], "keep me for the next model call")
        self.assertEqual(self.hook("PostToolUse", toolCall={"name": "run_command", "args": {"CommandLine": "ls"}}), {})
        self.assertEqual(len(self.store.unread(ACTOR, mark=False)), 1)
        with self.store.db() as db:
            tools = [row[0] for row in db.execute("SELECT tool FROM activity WHERE member='hajimi'")]
        self.assertIn("Bash", tools)

    def test_a_stop_goes_on_for_a_direct_message_and_ends_the_second_time(self):
        self.steps({"step_index": 0, "type": "PLANNER_RESPONSE", "content": "完成了"})
        self.store.send("lead-s", ["hajimi"], "one more thing")
        out = self.hook("Stop", continuationActive=False, terminationReason="NO_TOOL_CALL")
        self.assertEqual(out["decision"], "continue")
        self.assertIn("relic_relic_org/inbox", out["reason"])
        self.assertEqual(self.hook("Stop", continuationActive=True), {})
        relic = hook.relic_event({"hookEventName": "Stop", "conversationId": CID, "transcriptPath": str(self.path)})
        self.assertEqual(relic["last_assistant_message"], "完成了")  # the rules on Reply judge the last reply

    def test_a_conversation_without_a_seat_gets_nothing_injected(self):
        self.assertEqual(self.hook("SessionStart", conversationId="other"), {})
        self.assertEqual(self.hook("PreInvocation", conversationId="other", invocationNum=1), {})

    # ---------------- wake-ups ----------------

    def server(self, states):
        """A fake language server: run states in turn, and a transcript that grows when a message comes in."""
        calls = []

        def call(method, body, timeout=30, opener=None):
            calls.append((method.rsplit("/", 1)[-1], body))
            if method.endswith("GetConversation"):
                return {"state": {"runState": states.pop(0) if len(states) > 1 else states[0]}}
            if method.endswith("SendAgentMessage"):
                index = antigravity.last_step_index(self.path)
                self.steps({"step_index": index + 1, "type": "SYSTEM_MESSAGE", "content": "[Message] content=x"},
                           {"step_index": index + 2, "type": "PLANNER_RESPONSE", "content": "收到，已处理"})
                return {}
            if method.endswith("CreateConversation"):
                return {"conversation": {"id": "fresh-conv"}}
            raise AssertionError(method)
        return calls, call

    def test_a_wake_up_goes_into_the_seats_conversation_and_waits_for_its_turn(self):
        calls, call = self.server(["RUN_STATE_IDLE", "RUN_STATE_RUNNING", "RUN_STATE_IDLE"])
        org = self.store.get(self.oid)
        with mock.patch.object(antigravity, "call", call):
            carrier, reply, failed, _ = antigravity.run_turn(self.store, org, "hajimi", {}, "[Relic auto-wake] 你好",
                                                              sleep=lambda s: None)
        self.assertEqual((carrier, reply, failed), (ACTOR, "收到，已处理", False))
        sent = [body for name, body in calls if name == "SendAgentMessage"]
        self.assertEqual(sent, [{"recipient": CID, "content": "[Relic auto-wake] 你好"}])

    def test_a_conversation_in_a_turn_is_not_interrupted(self):
        calls, call = self.server(["RUN_STATE_RUNNING"])
        with mock.patch.object(antigravity, "call", call), self.assertRaises(RuntimeError) as caught:
            antigravity.run_turn(self.store, self.store.get(self.oid), "hajimi", {}, "x", sleep=lambda s: None)
        self.assertTrue(wake.no_turn(caught.exception))  # the wake-up waits a gap, as for a busy chat
        self.assertNotIn("SendAgentMessage", [name for name, _ in calls])

    def test_a_new_session_is_a_new_conversation_that_takes_the_seat(self):
        calls, call = self.server(["RUN_STATE_IDLE"])
        fresh = antigravity.transcript_path("fresh-conv")
        fresh.parent.mkdir(parents=True)
        fresh.write_text(json.dumps({"step_index": 0, "type": "USER_INPUT", "content": "x"}) + "\n" +
                         json.dumps({"step_index": 1, "type": "PLANNER_RESPONSE", "content": "我看到了组织"}) + "\n",
                         encoding="utf-8")
        with mock.patch.object(antigravity, "call", call):
            carrier, reply, _, _ = antigravity.run_turn(self.store, self.store.get(self.oid), "hajimi", {"model": "pro"},
                                                        "introduce yourself", new=True, sleep=lambda s: None)
        self.assertEqual((carrier, reply), ("antigravity:fresh-conv", "我看到了组织"))
        created = [body for name, body in calls if name == "CreateConversation"][0]
        self.assertEqual(created, {"title": "Team · hajimi", "prompt": [{"text": "introduce yourself"}], "model": "pro"})
        self.assertEqual(self.store.get(self.oid)["members"]["hajimi"]["carrier"], "antigravity:fresh-conv")

    def test_the_running_server_is_found_from_its_daemon_file(self):
        daemon = self.gemini / "antigravity" / "daemon"
        daemon.mkdir(parents=True)
        (daemon / "hub_1.json").write_text(json.dumps({"pid": 2 ** 22 + 7, "httpPort": 1, "csrfToken": "dead"}))
        (daemon / "hub_2.json").write_text(json.dumps({"pid": os.getpid(), "httpPort": 55214, "csrfToken": "tok"}))
        self.assertEqual(antigravity.hub(), {"address": "127.0.0.1:55214", "token": "tok"})
        (daemon / "hub_2.json").unlink()
        self.assertIsNone(antigravity.hub())
        with self.assertRaises(RuntimeError) as caught:
            antigravity.call("x/Y", {})
        self.assertIn(antigravity.UNREACHABLE, str(caught.exception))

    def test_an_antigravity_seat_is_woken_like_the_others(self):
        seat = self.store.get(self.oid)["members"]["hajimi"]
        self.assertEqual(seat["harness"], "antigravity")
        self.assertTrue(wake.wakeable(seat, self.store.seat_config(self.oid, "hajimi")))


if __name__ == "__main__":
    unittest.main()
