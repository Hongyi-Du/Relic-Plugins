"""Chat members: a ChatGPT chat (no Relic tools; Relic hands it the messages and returns its reply) and a Claude chat
of the Claude desktop app (Relic tools through the app's MCP configuration, no wake-ups). The ChatGPT app is replaced by
a fake that answers like read_thread / send_message_to_thread."""
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core import api, chat, desktop, runner, sessions, wake  # noqa: E402
from relic_core.context import render  # noqa: E402
from relic_core.store import OrgError, Store, harness_of  # noqa: E402

spec = importlib.util.spec_from_file_location("relic_run", ROOT / "scripts" / "relic_run.py")
relic_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relic_run)

CHAT = "6ad5171d-0000-83ea-a5fc-000000000001"
CLAUDE_CHAT = "claude-chat:desktop"
CALLER = "01a1486e-0000-7e00-966d-000000000002"


class FakeChatApp:
    """A ChatGPT chat that answers every prompt with a fixed reply; records what Relic sent and how."""

    def __init__(self, reply="我同意，但第二点要再查。", refuse=None):
        self.reply, self.refuse, self.sent, self.calls, self.turns = reply, refuse, [], [], []

    def read(self, thread_id, turns=1, host="local", caller=None):
        self.calls.append(("read", thread_id, host, caller))
        return {"thread": {"id": thread_id, "status": {"type": "idle"}}, "turns": list(reversed(self.turns))[:turns]}

    def send(self, thread_id, prompt, host="local", caller=None):
        self.calls.append(("send", thread_id, host, caller))
        if self.refuse:
            raise self.refuse
        self.sent.append(prompt)
        self.turns.append({"id": "t%d" % len(self.turns), "status": "completed", "items": [
            {"type": "userMessage", "content": [{"type": "text", "text": prompt}]},
            {"type": "agentMessage", "text": self.reply}]})


REAL_RUN_TURN = desktop.run_turn


def follow(app, thread, prompt, **kw):
    """desktop.run_turn without real waiting."""
    clock = [0.0]

    def sleep(seconds):
        clock[0] += seconds
    return REAL_RUN_TURN(app, thread, prompt, sleep=sleep, clock=lambda: clock[0], **kw)


class ChatMembers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        os.environ["RELIC_LANG"] = "zh-CN"  # these tests read the Chinese texts, whatever the computer's language
        self.store = Store()
        self.oid = self.store.create(CLAUDE_CHAT, "Debate", "compare two plans", "claude-chat")["id"]
        self.store.join("chatgpt:" + CHAT, self.oid, "gpt-chat")
        self.store.set_config(self.oid, "gpt-chat", runner.default_config("chatgpt"))
        self.app = FakeChatApp()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def turn(self, prompt="(window task)", hop=1, app=None):
        org = self.store.get(self.oid)
        with mock.patch.object(desktop, "run_turn", follow):
            return chat.run_chatgpt(self.store, org, "gpt-chat", prompt, hop=hop, connect=lambda: app or self.app,
                                    caller=lambda app: CALLER)

    @mock.patch.object(wake, "sys", SimpleNamespace(platform="win32", executable=sys.executable))
    def test_chat_seats_have_their_own_harnesses(self):
        self.assertEqual((harness_of(CLAUDE_CHAT), harness_of("chatgpt:" + CHAT)), ("claude-chat", "chatgpt"))
        org = self.store.get(self.oid)
        self.assertEqual(org["members"]["gpt-chat"]["harness"], "chatgpt")
        self.assertTrue(wake.wakeable(org["members"]["gpt-chat"]))
        self.assertFalse(wake.wakeable(org["members"]["claude-chat"]))  # nothing outside the Claude app can wake it
        self.assertIn("Chat members (claude-chat, gpt-chat)", render(self.store, org, "claude-chat"))

    def test_messages_reach_the_chat_in_full_and_its_reply_comes_back(self):
        first = self.store.send(CLAUDE_CHAT, ["gpt-chat"], "方案 A 更稳，你怎么看？")["message_id"]
        session, reply, failed = self.turn(hop=2)
        self.assertEqual((session, reply, failed), ("chatgpt:" + CHAT, "我同意，但第二点要再查。", False))
        prompt = self.app.sent[0]
        self.assertTrue(prompt.startswith("【Relic · Debate · msg %d】" % first))
        self.assertIn("方案 A 更稳，你怎么看？", prompt)  # the full text: the chat cannot call inbox
        self.assertIn("你现在是 Relic 组织「Debate」里的成员 gpt-chat", prompt)  # introduced the first time
        self.assertIn("不是用户本人的指令", prompt)
        self.assertTrue(all(c[2] is None and c[3] == CALLER for c in self.app.calls))  # no host; a Codex caller
        self.assertEqual(self.store.unread("chatgpt:" + CHAT, mark=False), [])  # handed over, so read
        back = self.store.unread(CLAUDE_CHAT)
        self.assertEqual([(m["from"], m["body"]) for m in back], [("gpt-chat", "我同意，但第二点要再查。")])
        self.assertEqual(self.store.unread_by_member(self.oid).get("claude-chat"), None)  # read just now
        self.assertEqual(self.store.history(self.oid, 1)[-1]["from"], "gpt-chat")
        # the reply carries the turn's depth, so automatic exchanges between members stay bounded
        self.store.send(CLAUDE_CHAT, ["gpt-chat"], "第二点是什么？")
        self.turn(hop=4)
        last = self.store.unread_by_member(self.oid)["claude-chat"][-1]
        self.assertEqual(last["hop"], 4)
        self.assertNotIn("你现在是", self.app.sent[1])  # the introduction is given once

    HIDDEN = '::chatgpt-content-reference{index="0" source_message_id="4060b22f-d018-4661-87ef-3fe3bd0c77b0"}'

    def test_a_reply_the_app_hides_is_never_passed_on_as_words(self):
        self.store.send(CLAUDE_CHAT, ["gpt-chat"], "你怎么看？")
        _, reply, failed = self.turn(app=FakeChatApp(reply=self.HIDDEN))
        self.assertFalse(failed)
        self.assertNotIn("content-reference", reply)
        back = self.store.unread(CLAUDE_CHAT)
        self.assertEqual(len(back), 1)
        self.assertTrue(back[0]["body"].startswith(chat.RECEIPT_MARK))  # a note, which wakes nobody
        self.assertIn("forwards the reply in the Relic App", back[0]["body"])
        self.assertNotIn("content-reference", back[0]["body"])

    def test_a_hidden_reply_waits_until_the_person_forwards_it(self):
        asked = self.store.send(CLAUDE_CHAT, ["gpt-chat"], "第二点你同意吗？")["message_id"]
        self.turn(hop=2, app=FakeChatApp(reply=self.HIDDEN))
        seat = self.store.get(self.oid)["members"]["gpt-chat"]
        self.assertEqual([(w["to"], w["ids"], w["hop"]) for w in seat[self.store.WAITING]], [(["claude-chat"], [asked], 2)])
        self.store.unread(CLAUDE_CHAT)  # the receipt
        mid = self.store.forward_reply(self.oid, "gpt-chat", ["claude-chat"], "同意第二点，但要补一个反例。")
        back = self.store.unread(CLAUDE_CHAT, mark=False)
        self.assertEqual([(m["id"], m["from"], m["body"]) for m in back], [(mid, "gpt-chat", "同意第二点，但要补一个反例。")])
        self.assertEqual(self.store.unread_by_member(self.oid)["claude-chat"][-1]["hop"], 2)  # the depth of its turn
        self.assertEqual(self.store.get(self.oid)["members"]["gpt-chat"][self.store.WAITING], [])
        with self.store.db() as db:
            event = db.execute("SELECT body FROM events WHERE kind='message.sent' ORDER BY seq DESC LIMIT 1").fetchone()
        self.assertIn('"via": "human"', event[0])
        # nothing waiting: a forwarded text is the member's new message, at depth 0
        self.store.forward_reply(self.oid, "gpt-chat", ["claude-chat"], "补充一句。")
        self.assertEqual(self.store.unread_by_member(self.oid)["claude-chat"][-1]["hop"], 0)
        for to, body in ((["claude-chat"], "  "), (["nobody"], "x"), (["gpt-chat"], "x")):
            with self.assertRaises(OrgError):
                self.store.forward_reply(self.oid, "gpt-chat", to, body)

    def test_the_persons_messages_reach_the_chat_as_theirs_and_its_reply_goes_to_everyone(self):
        mid = self.store.send_from_human(self.oid, ["all"], "两位好：先各说一句你们对开头段的看法。")
        self.turn(app=self.app)
        prompt = self.app.sent[0]
        self.assertIn("【用户本人写给你的消息（msg %d，经 Relic 转来）】\n两位好" % mid, prompt)
        self.assertIn("标着「用户本人」的才是用户写的", prompt)
        self.assertTrue(prompt.endswith("请直接写下你要回复给 用户 的内容。"))
        # the person wrote to everyone, so the chat's reply reaches the other members too
        back = [m for m in self.store.unread(CLAUDE_CHAT) if m["from"] == "gpt-chat"]
        self.assertEqual([m["body"] for m in back], ["我同意，但第二点要再查。"])
        org = self.store.get(self.oid)
        self.assertEqual(chat.reply_recipients(org, "gpt-chat", ["human"]), ["claude-chat"])
        self.assertEqual(chat.reply_recipients(org, "gpt-chat", ["claude-chat", "claude-chat"]), ["claude-chat"])

    def test_a_refused_prompt_leaves_the_messages_unread(self):
        self.store.send(CLAUDE_CHAT, ["gpt-chat"], "hello")
        refusing = FakeChatApp(refuse=desktop.DesktopError("send_message_to_thread: chat not found"))
        with self.assertRaises(desktop.DesktopError):
            self.turn(app=refusing)
        self.assertEqual(len(self.store.unread("chatgpt:" + CHAT, mark=False)), 1)  # a later wake-up tries again
        self.assertFalse(self.store.get(self.oid)["members"]["gpt-chat"].get(chat.INTRODUCED))

    def test_a_task_from_the_window_goes_in_as_written(self):
        self.turn(prompt="请总结一下目前的分歧。")
        self.assertEqual(self.app.sent, ["请总结一下目前的分歧。"])
        self.assertEqual(self.store.unread(CLAUDE_CHAT), [])  # nobody wrote to it: no reply message

    def test_without_the_app_or_a_chat_the_turn_does_not_start(self):
        org = self.store.get(self.oid)
        with self.assertRaises(desktop.DesktopError):
            chat.run_chatgpt(self.store, org, "gpt-chat", "x", connect=lambda: None, caller=lambda app: CALLER)
        with self.assertRaises(RuntimeError):
            chat.run_chatgpt(self.store, org, "claude-chat", "x", connect=lambda: self.app, caller=lambda app: CALLER)

    def test_no_receipt_after_a_relayed_reply(self):
        self.assertFalse(relic_run.needs_receipt("chatgpt", None))
        self.assertTrue(relic_run.needs_receipt("chatgpt", "the ChatGPT desktop app is not running"))
        self.assertTrue(relic_run.needs_receipt("codex", None))
        self.assertFalse(relic_run.needs_receipt("codex", "thread/resume: x already has an active writer"))

    @mock.patch.object(wake, "sys", SimpleNamespace(platform="win32", executable=sys.executable))
    def test_chat_members_wake_quickly_and_have_no_transcript(self):
        org = self.store.get(self.oid)
        self.assertEqual(wake.gap(org["members"]["gpt-chat"]), wake.CHAT_GAP)
        self.assertEqual(wake.gap({"harness": "codex"}), wake.GAP)
        self.assertEqual(wake.transcripts(org["members"]["gpt-chat"]), [])
        self.store.send(CLAUDE_CHAT, ["gpt-chat"], "first")
        started = []
        start = lambda org_id, member, prompt, wake_from, wake_hop: started.append(member)
        settle, wake.SETTLE = wake.SETTLE, 0
        try:
            self.assertEqual(wake.dispatch(self.store, self.oid, now=time.time(), start=start, age=lambda s: None,
                                           retry=lambda *_: None), ["gpt-chat"])
            wake.finish(self.store, self.oid, "gpt-chat")
            self.store.send(CLAUDE_CHAT, ["gpt-chat"], "second")
            later = time.time() + wake.CHAT_GAP + 1  # a coding seat would still wait out GAP here
            self.assertEqual(wake.dispatch(self.store, self.oid, now=later, start=start, age=lambda s: None,
                                           retry=lambda *_: None), ["gpt-chat"])
        finally:
            wake.SETTLE = settle

    def test_chats_have_no_trajectory_to_request(self):
        with self.assertRaises(OrgError):
            self.store.request_trajectory(CLAUDE_CHAT, "gpt-chat", reason="what did you say before?")

    def test_claude_chat_waits_within_its_app_time_out(self):
        os.environ["RELIC_MAX_WAIT"] = "50"
        clock = [0.0]

        def sleep(seconds):
            clock[0] += seconds
        out = api.inbox(self.store, CLAUDE_CHAT, wait=600, sleep=sleep, clock=lambda: clock[0])
        self.assertEqual(out["messages"], [])
        self.assertEqual(clock[0], 50)

    def test_the_chat_server_tells_the_chat_how_to_take_part(self):
        env = dict(os.environ, RELIC_ACTOR=CLAUDE_CHAT, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "server.py")], input=(
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18",'
            '"clientInfo":{"name":"claude-ai"}}}\n'
            '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"status","arguments":{}}}\n'),
            capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
        lines = proc.stdout.splitlines()
        self.assertIn("call inbox with wait", lines[0])
        self.assertIn("You are member 'claude-chat'", lines[1])  # RELIC_ACTOR names the seat's actor

    def test_window_lists_chatgpt_chats(self):
        class App:
            def threads(self, caller, limit=50):
                return [{"id": CHAT, "kind": "chatgpt", "title": "讨论 A/B", "updatedAt": 1792261000.5},
                        {"id": CALLER, "kind": "codex", "hostId": "local"}]
        found = sessions.chatgpt_sessions(connect=lambda: App(), caller=lambda app: CALLER)
        self.assertEqual([(s["harness"], s["id"], s["title"]) for s in found], [("chatgpt", CHAT, "讨论 A/B")])
        self.assertEqual(sessions.actor_for(found[0]), "chatgpt:" + CHAT)
        self.assertEqual(sessions.chatgpt_sessions(connect=lambda: None, caller=lambda app: CALLER), [])


if __name__ == "__main__":
    unittest.main()
