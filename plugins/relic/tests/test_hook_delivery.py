"""Budgeting and rereading use private stores; hooks never dispatch a real wake-up."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "hooks"))
import relic_hook
from relic_core import api, wake
from relic_core.context import render_messages
from relic_core.store import OrgError, Store


class Delivery(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = Store(Path(temporary.name) / "fixture.sqlite3")
        self.org = self.store.create("lead", "Team", "repair", "lead")["id"]
        self.store.join("member-session", self.org, "member")
        patch = mock.patch.dict(os.environ, {"RELIC_HARNESS": "claude-code"})
        patch.start()
        self.addCleanup(patch.stop)

    def send(self, body):
        return self.store.send("lead", ["member"], body)["message_id"]

    def hook(self, event="UserPromptSubmit"):
        return relic_hook.respond({"hook_event_name": event, "session_id": "member-session"}, self.store
                                  ).get("hookSpecificOutput", {}).get("additionalContext", "")

    def test_long_context_delivers_only_whole_messages_and_inbox_recovers_the_rest(self):
        bodies = ["FIRST " + "甲" * 400, "SECOND " + "乙" * 5000, "THIRD " + "丙" * 5000]
        ids = [self.send(body) for body in bodies]
        with mock.patch.object(relic_hook, "render", return_value="ORGANIZATION " + "上下文" * 5000):
            text = self.hook()
        self.assertLessEqual(len(text), 9500)
        self.assertTrue(text.startswith("ORGANIZATION"))
        self.assertIn(bodies[0], text)
        self.assertIn("SECOND", text)
        self.assertNotIn(bodies[1], text)
        self.assertIn("cut here: read message %d in full with inbox" % ids[1], text)
        self.assertIn("2 more unread messages", text)
        self.assertIn(str(ids[2]), text)
        self.assertEqual([m["id"] for m in self.store.unread("member-session", mark=False)], ids[1:])
        got = api.inbox(self.store, "member-session")
        self.assertEqual([m["body"] for m in got["messages"]], bodies[1:])
        for body in bodies[1:]:
            self.assertIn(body, got["text"])

    def test_post_tool_preview_stays_unread_and_exact_boundary_is_delivered(self):
        mid = self.send("x" * 15000)
        text = self.hook("PostToolUse")
        self.assertEqual(len(text), 9500)
        self.assertIn("read message %d in full with inbox" % mid, text)
        self.assertEqual(self.store.unread("member-session", mark=False)[0]["id"], mid)
        api.inbox(self.store, "member-session")
        mid = self.send("x")
        initial = self.hook("PostToolUse")
        # Grow that message to fill the budget exactly, then make it unread again.
        with self.store.db() as db:
            db.execute("UPDATE messages SET body=? WHERE id=?", ("x" * (9501 - len(initial)), mid))
            db.execute("DELETE FROM reads WHERE message_id=?", (mid,))
        self.assertEqual(len(self.hook("PostToolUse")), 9500)
        self.assertEqual(self.store.unread("member-session", mark=False), [])

    def test_limit_notice_counts_every_remaining_message(self):
        ids = [self.send("small message") for _ in range(24)]
        text = self.hook("PostToolUse")
        self.assertLessEqual(len(text), 9500)
        self.assertIn("14 more unread messages", text)
        self.assertEqual([m["id"] for m in self.store.unread("member-session", mark=False)], ids[10:])

    def test_other_seat_is_acknowledged_in_its_own_organization(self):
        other = self.store.create("other-lead", "Other", "repair", "chief")["id"]
        self.store.join("member-session", other, "helper")
        mid = self.store.send("other-lead", ["helper"], "entire other-seat message")["message_id"]
        self.assertIn("entire other-seat message", self.hook("PostToolUse"))
        self.assertEqual(self.store.unread("member-session", mark=False), [])
        got = api.handle_call(self.store, "inbox", {"message_id": mid, "org": other}, "member-session")
        self.assertEqual(got["messages"][0]["org_id"], other)

    def test_empty_inbox_lists_only_open_tasks_assigned_to_each_seat(self):
        self.store.work("member-session", "task", {"title": "Repair inbox", "status": "working"})
        self.store.work("lead", "task", {"title": "Someone else's task"})
        self.store.work("member-session", "task", {"title": "Dropped", "status": "dropped"})
        self.store.work("member-session", "task", {"title": "Finished", "status": "done",
                                                    "evidence": ["fixture"], "report": "finished"})
        other = self.store.create("other-lead", "Other", "repair", "chief")["id"]
        self.store.join("member-session", other, "helper")
        self.store.work("member-session#" + other, "task", {"title": "Blocked repair", "status": "blocked"})
        got = api.inbox(self.store, "member-session")
        self.assertEqual({t["title"] for t in got["tasks"]}, {"Repair inbox", "Blocked repair"})
        for task in got["tasks"]:
            for key in ("id", "title", "status", "org_id", "org_name"):
                self.assertIn(task[key], got["text"])
        scoped = api.handle_call(self.store, "inbox", {"org": other}, "member-session")
        self.assertEqual([t["title"] for t in scoped["tasks"]], ["Blocked repair"])

    def test_reread_authorization_and_wait_are_independent_of_read_state(self):
        mid = self.send("full read message")
        api.inbox(self.store, "member-session")
        got = api.handle_call(self.store, "inbox", {"message_id": mid, "wait": 600}, "member-session")
        self.assertEqual(got["messages"][0]["body"], "full read message")
        for actor, message_id in (("lead", mid), ("member-session", mid + 1000)):
            with self.assertRaises(OrgError):
                api.inbox(self.store, actor, message_id=message_id)

    def test_wake_prompt_names_context_inbox_and_status(self):
        for main in (True, False):
            text = wake.prompt(self.store.get(self.org), "member", ["lead"], 3, main=main)
            self.assertIn("messages that started this turn are in the context or in inbox", text)
            self.assertIn("your open tasks are in status", text)

    def test_explicit_seat_above_main_wins_over_upward_reporting(self):
        upper = self.store.create("upper-lead", "研发部", "repair", "chief")["id"]
        cabinet = self.store.create("cabinet-lead", "秘书处", "coordinate", "chief")["id"]
        with self.store.change(self.org) as (org, _):
            org["parent"] = upper
        with self.store.change(upper) as (org, _):
            org["parent"] = cabinet
        self.store.join("member-session", upper, "researcher")
        self.store.join("member-session", cabinet, "representative")
        mid = self.store.send("cabinet-lead", ["researcher"], "repair request", org=upper)["message_id"]
        for ref, recipients in ((upper, {}), ("研发部", {"to": [cabinet + "/chief"]})):
            reply = api.handle_call(self.store, "message", dict(org=ref, reply_to=mid, body="repair evidence",
                                                                **recipients), "member-session")
            row = next(m for m in self.store.history(upper) if m["id"] == reply["message_id"])
            self.assertEqual((row["from"], row["reply_to"]), ("researcher", mid))
            self.assertEqual(self.store.whoami("member-session")[0]["id"], self.org)
            self.assertEqual(self.store.focused("member-session"), "member-session#" + upper)
            copy = self.store.unread("cabinet-lead")
            self.assertEqual([(m["from"], m["body"]) for m in copy], [(upper + "/researcher", "repair evidence")])
        with self.assertRaises(OrgError):
            api.handle_call(self.store, "message", {"org": upper, "reply_to": mid, "to": [cabinet + "/stranger"],
                                                    "body": "must not deliver"}, "member-session")


if __name__ == "__main__":
    unittest.main()
