"""The Relic window's discussion room, on a hidden Tk window: every message in full as it comes, the chat members'
state, the person's messages waking the members they are for, and a ChatGPT chat's reply forwarded by the person."""
import os
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core import runner, wake, window  # noqa: E402
from relic_core.store import Store  # noqa: E402

CHAT = "6ad5171d-0000-83ea-a5fc-000000000001"
CLAUDE_CHAT = "claude-chat:desktop"


class DiscussionRoom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.tk_root = tk.Tk()
            cls.tk_root.withdraw()
        except tk.TclError as error:
            raise unittest.SkipTest(str(error))

    @classmethod
    def tearDownClass(cls):
        cls.tk_root.destroy()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        self.store = Store()
        self.oid = self.store.create(CLAUDE_CHAT, "Debate", "compare two plans", "claude-chat")["id"]
        self.store.join("chatgpt:" + CHAT, self.oid, "gpt-chat")
        self.store.set_config(self.oid, "gpt-chat", runner.default_config("chatgpt"))
        patcher = mock.patch.object(runner, "codex_models", lambda: [])  # the window asks the Codex CLI otherwise
        patcher.start()
        self.addCleanup(patcher.stop)
        try:
            top = tk.Toplevel(self.tk_root)
            with mock.patch.object(window.tk, "Tk", return_value=top):
                self.app = window.App(store=self.store)
        except tk.TclError as error:  # no display
            self.skipTest(str(error))
        self.app.root.withdraw()
        self.app.background = lambda work, done: done(work())  # run in this thread

    def tearDown(self):
        try:
            for callback in self.app.root.tk.call("after", "info"):
                self.app.root.after_cancel(callback)
            self.app.root.destroy()
        except (AttributeError, tk.TclError):
            pass
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def room(self):
        return self.app.room_text.get("1.0", "end")

    def test_the_room_shows_each_message_in_full_and_adds_new_ones(self):
        long = "方案 A 更稳。" + "理由很长。" * 80
        self.store.send(CLAUDE_CHAT, ["gpt-chat"], long)
        self.app.refresh()
        self.assertEqual(self.app.tabs.tab(self.app.tabs.select(), "text"), "讨论室")
        self.assertIn("claude-chat → gpt-chat", self.room())
        self.assertIn(long, self.room())  # not shortened
        self.store.send_as(self.oid, "gpt-chat", ["claude-chat"], wake.RECEIPT_MARK + " gpt-chat answered msg 1.")
        self.store.send_from_human(self.oid, ["all"], "两位都说说开头段。")
        self.app.fill_room(self.store.get(self.oid))
        text = self.room()
        self.assertEqual(text.count(long), 1)  # added, not drawn again
        self.assertIn("自动回执 gpt-chat → claude-chat", text)
        self.assertIn("· 你 → claude-chat, gpt-chat\n两位都说说开头段。", text)

    def test_the_room_says_what_the_chat_members_are_doing(self):
        self.store.send(CLAUDE_CHAT, ["gpt-chat"], "你怎么看？")
        self.app.refresh()
        self.assertIn("gpt-chat：1 条消息正在送进它的 ChatGPT 聊天", self.app.room_status.cget("text"))
        self.store.mark_read(self.oid, "gpt-chat", [1])
        self.store.note_hidden_reply(self.oid, "gpt-chat", ["claude-chat"], [1], hop=1)
        self.store.send_from_human(self.oid, ["claude-chat"], "先等等 GPT。")
        self.app.refresh()
        status = self.app.room_status.cget("text")
        self.assertIn("gpt-chat：1 条回复只在 ChatGPT 窗口里，等你转发（最早一条回的是 msg 1）", status)
        self.assertIn("claude-chat：1 条未读", status)

    def test_the_persons_message_wakes_the_members_it_is_for(self):
        self.app.refresh()
        self.app.room_input.insert("1.0", "两位好。")
        woken = []
        with mock.patch.object(wake, "dispatch", lambda store, org_id: woken.append(org_id)):
            self.app.room_send()
        self.assertEqual(woken, [self.oid])
        self.assertEqual(self.app.room_input.get("1.0", "end").strip(), "")
        self.assertEqual([(m["from"], m["to"]) for m in self.store.history(self.oid)],
                         [("human", ["claude-chat", "gpt-chat"])])

    def test_a_copied_reply_is_forwarded_as_the_members_message(self):
        asked = self.store.send(CLAUDE_CHAT, ["gpt-chat"], "第二点你同意吗？")["message_id"]
        self.store.mark_read(self.oid, "gpt-chat", [asked])
        self.store.note_hidden_reply(self.oid, "gpt-chat", ["claude-chat"], [asked], hop=3)
        org = self.store.get(self.oid)
        with mock.patch.object(self.app.root, "clipboard_get", lambda: "  同意，但要补一个反例。\n"):
            dialog = window.ForwardDialog(self.app, org, ["gpt-chat"])
        self.assertEqual(dialog.text.get("1.0", "end").strip(), "同意，但要补一个反例。")
        self.assertEqual(dialog.to.get(), "claude-chat")
        woken = []
        with mock.patch.object(wake, "dispatch", lambda store, org_id: woken.append(org_id)):
            dialog.send()
        self.assertEqual(woken, [self.oid])
        last = self.store.history(self.oid, 1)[-1]
        self.assertEqual((last["from"], last["to"], last["body"]), ("gpt-chat", ["claude-chat"], "同意，但要补一个反例。"))
        self.assertEqual(self.store.unread_by_member(self.oid)["claude-chat"][-1]["hop"], 3)
        self.assertEqual(self.store.get(self.oid)["members"]["gpt-chat"][Store.WAITING], [])
        self.assertIn("同意，但要补一个反例。", self.room())


if __name__ == "__main__":
    unittest.main()
