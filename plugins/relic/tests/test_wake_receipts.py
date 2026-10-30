"""Trigger-bound wake delivery and receipts; no real sessions, processes or App server."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "hooks"))
from app import hub  # noqa: E402
from relic_core import runner, wake  # noqa: E402
from relic_core.store import Store  # noqa: E402
import relic_hook  # noqa: E402

spec = importlib.util.spec_from_file_location("wake_receipt_runner", ROOT / "scripts/relic_run.py")
relic_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relic_run)


class WakeReceipts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, RELIC_HOME=self.tmp.name)
        self.env.start()
        self.store = Store()
        self.org = self.store.create("lead-session", "Lab", "work", "lead", governance="peer")["id"]
        self.store.add_seat(self.org, "worker", "notes", runner.default_config("claude-code"))
        self.store.join("worker-session", self.org, "worker")
        self.store.join("other-session", self.org, "other")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def send(self, actor, to, body, reply_to=None):
        return self.store.send(actor, to, body, reply_to=reply_to)["message_id"]

    def last_receipt(self, org=None):
        return [m for m in self.store.history(org or self.org, 100)
                if m["body"].startswith(wake.RECEIPT_MARK)][-1]

    def test_resume_carries_new_task_even_after_hook_marks_it_read(self):
        body = "New meeting SEC013: prepare notes/progress.json; do not repeat the previous standby answer."
        mid = self.send("lead-session", ["worker"], body)
        observed = {}

        def start(oid, member, prompt, **kwargs):
            context = relic_hook.respond({"hook_event_name": "UserPromptSubmit", "session_id": "worker-session"}, self.store)
            self.assertIn(body, str(context))
            self.assertEqual(self.store.unread("worker-session", mark=False), [])
            observed.update(prompt=prompt, **kwargs)
            with mock.patch.object(runner, "find_claude", return_value="fixture-claude"), \
                    mock.patch.object(relic_run.subprocess, "run", return_value=mock.Mock(
                        returncode=0, stdout='{"result":"Old tools delivered; standing by."}', stderr="")) as launch:
                result = relic_run.run_claude(self.store, self.store.get(oid), member,
                                              runner.default_config("claude-code"), prompt, False, self.tmp.name)
            args = launch.call_args.args[0]
            self.assertEqual(args[args.index("--resume") + 1], "worker-session")
            self.assertIn(body, args[args.index("-p") + 1])
            relic_run.receipt(self.store, oid, member, kwargs["wake_from"], mid,
                              dict(status="done", reply=result[1], wake_message_ids=kwargs["wake_message_ids"]))

        self.assertEqual(wake.dispatch(self.store, self.org, now=10**12, age=lambda _: None,
                                        start=start, retry=mock.Mock()), ["worker"])
        self.assertEqual(observed["wake_message_ids"], [mid])
        self.assertIn("inbox message_id=<id>", observed["prompt"])
        self.assertIn("check status", observed["prompt"])
        self.assertIn(str(mid), observed["prompt"])
        receipt = self.last_receipt()
        self.assertIn("the turn finished", receipt["body"])
        self.assertNotIn("Old tools delivered", receipt["body"])
        self.assertEqual(receipt["reply_to"], mid)

    def test_preview_keeps_exact_id_and_does_not_mark_message_read(self):
        mid = self.send("lead-session", ["worker"], "x" * 10000)
        messages = self.store.unread_by_member(self.org)["worker"]
        text = wake.prompt(self.store.get(self.org), "worker", ["lead"], 1, messages=messages)
        self.assertIn("inbox message_id=%d" % mid, text)
        self.assertLess(len(text), 9500)
        self.assertEqual(self.store.unread("worker-session", mark=False)[0]["body"], "x" * 10000)

    def test_redirect_quotes_only_new_replies_in_trigger_thread_on_both_routes(self):
        # Freeze time: an earlier reply in the same second must still be excluded by its id.
        with mock.patch("relic_core.store.now", return_value="2026-10-29T21:21:00Z"):
            root = self.send("lead-session", ["worker"], "Check startup policy")
            self.send("worker-session", ["lead"], "Earlier reply", reply_to=root)
            trigger = self.send("lead-session", ["worker"], "Please finish", reply_to=root)
            after = wake.message_checkpoint(self.store, self.org)
            reply = self.send("worker-session", ["lead"], "Do not add startup tasks", reply_to=trigger)
            self.send("worker-session", ["lead"], "Unrelated meeting answer")
            other = self.send("lead-session", ["worker"], "Another task")
            self.send("worker-session", ["lead"], "Another thread's answer", reply_to=other)
            self.store.send_as(self.org, "worker", ["lead"], wake.RECEIPT_MARK + " previous receipt", reply_to=root)
        for receive in (relic_run.receipt, hub._receipt):
            with self.subTest(route=receive.__module__):
                receive(self.store, self.org, "worker", ["lead"], after,
                        dict(status="done", reply="The person's later meeting answer", wake_message_ids=[trigger]))
                text = self.last_receipt()["body"]
                self.assertIn("Do not add startup tasks", text)
                self.assertIn("[msg %d, thread %d]" % (reply, root), text)
                for excluded in ("Earlier reply", "Unrelated meeting answer", "Another thread's answer",
                                 "previous receipt", "The person's later meeting answer", "final words"):
                    self.assertNotIn(excluded, text)

    def test_cross_org_waker_gets_thread_reply_without_unrelated_final(self):
        other = self.store.create("external-session", "Other", "work", "benchlead", governance="peer")["id"]
        # A cross-org incoming message lives in the receiving seat's organization, as in #4034.
        with self.store.db() as db:
            mid = db.execute("INSERT INTO messages(org_id,sender,recipients,body,at) VALUES(?,?,?,?,?)",
                             (self.org, other + "/benchlead", '["worker","lead"]', "Startup policy?", "now")).lastrowid
        self.send("worker-session", ["lead"], "No new startup tasks", reply_to=mid)
        for receive in (relic_run.receipt, hub._receipt):
            receive(self.store, self.org, "worker", [other + "/benchlead"], mid,
                    dict(status="done", reply="Unrelated meeting", wake_message_ids=[mid]))
            receipt = self.last_receipt(other)
            self.assertEqual(receipt["to"], ["benchlead"])
            self.assertIsNone(receipt["reply_to"])  # a foreign org's id cannot become a local thread root
            self.assertIn("No new startup tasks", receipt["body"])
            self.assertNotIn("Unrelated meeting", receipt["body"])

    def test_each_waker_sees_only_its_trigger_threads(self):
        first = self.send("lead-session", ["worker"], "First task")
        second = self.send("other-session", ["worker"], "Second task")
        after = wake.message_checkpoint(self.store, self.org)
        self.send("worker-session", ["lead"], "First result", reply_to=first)
        self.send("worker-session", ["other"], "Second result", reply_to=second)
        wake.receipt(self.store, self.org, "worker", ["lead", "other"], after,
                     dict(status="done", wake_message_ids=[first, second]))
        receipts = [m for m in self.store.history(self.org) if m["body"].startswith(wake.RECEIPT_MARK)]
        self.assertEqual(len(receipts), 2)
        for message, included, excluded in zip(receipts, ("First result", "Second result"), ("Second result", "First result")):
            self.assertIn(included, message["body"])
            self.assertNotIn(excluded, message["body"])

    def test_missing_binding_or_failed_turn_never_falls_back_to_final_words(self):
        mid = self.send("lead-session", ["worker"], "New task")
        self.send("worker-session", ["lead"], "Thread reply", reply_to=mid)
        for status in ("done", "failed", "incomplete"):
            for receive in (relic_run.receipt, hub._receipt):
                receive(self.store, self.org, "worker", ["lead"], mid,
                        dict(status=status, reply="Stale final words"))
                text = self.last_receipt()["body"]
                self.assertNotIn("Stale final words", text)
                self.assertNotIn("Thread reply", text)
                self.assertIn("No reply in the triggering thread", text)


if __name__ == "__main__":
    unittest.main()
