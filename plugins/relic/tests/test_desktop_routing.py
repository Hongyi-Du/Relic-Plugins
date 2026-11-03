"""One Claude Desktop session holding seats in several organizations, and seat replies across organizations.

Every seat of the session reaches it at the one configured address and keeps its own organization; the session
takes one Relic request at a time; an unanswered request expires without ever being sent again, and a late Stop
that quotes its nonce still answers it. Synthetic router and hook records only: no live model, peer or CLI.
"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "hooks"))
from relic_core import claude_desktop as gui, gui_receipt, runner, wake
from relic_core.store import OrgError, Store
import relic_hook

SID = "dfd21864-9275-4625-8873-000000000001"
ADDRESS = "Relic 研发部 · relic-head"


class Base(unittest.TestCase):
    def setUp(self):
        for module in (gui, wake):  # the native route's Windows contract (macOS adds its own capability checks)
            patch = mock.patch.object(module, "sys", SimpleNamespace(platform="win32", executable=sys.executable))
            patch.start()
            self.addCleanup(patch.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"RELIC_HOME": self.tmp.name, "CLAUDE_CODE_ENTRYPOINT": "claude-desktop"})
        env.start()
        self.addCleanup(env.stop)
        s = self.store = Store()
        self.cabinet = s.create("chief", "秘书处", "cabinet", "chief")["id"]
        self.dept = s.create("dept-founder", "Relic 研发部", "kernel", "dept-founder")["id"]
        self.demo = s.create("demo-founder", "Relic 演示组", "demo", "demo-founder")["id"]
        self.other = s.create("stranger", "无关组织", "unrelated", "stranger")["id"]
        s.set_parent(self.dept, self.cabinet)
        s.set_parent(self.demo, self.dept)
        s.join("supervisor", self.cabinet, "progress-supervisor")
        self.config = dict(runner.default_config("claude-code"), surface="gui")
        s.add_seat(self.dept, "relic-head", config=self.config)  # the one seat configured for the Desktop session
        s.add_seat(self.cabinet, "relic-head")
        s.add_seat(self.demo, "lead")
        for org_id, member in ((self.dept, "relic-head"), (self.cabinet, "relic-head"), (self.demo, "lead")):
            s.join(SID, org_id, member)
        self.seats = [(self.dept, "relic-head"), (self.cabinet, "relic-head"), (self.demo, "lead")]

    def handle(self, name, **fields):
        event = dict(hook_event_name=name, session_id=SID, **fields)
        with mock.patch.object(relic_hook, "respond", return_value={}), mock.patch.object(wake, "dispatch_for_actor"):
            return relic_hook.handle(event, self.store)

    def run_turn(self, org_id, member, route, prompt=None):
        org = self.store.get(org_id)
        config = self.store.seat_config(org_id, member, org)
        return gui.run_turn(self.store, org, member, config, prompt or "task for %s/%s" % (org_id, member), False,
                            self.tmp.name, route_message=route, timeout=0)

    @staticmethod
    def queued(request, config, folder):
        gui._write(folder / "delivery.json", {"outcome": "queued", "records": []})
        return "queued"

    @staticmethod
    def folder(request):
        return runner.runs_dir() / ("claude-gui-" + request["nonce"])

    def age(self, request, seconds):
        aged = dict(request, created=time.time() - seconds)
        gui._write(gui.request_path(request["org_id"], request["member"]), aged)
        gui._write(self.folder(request) / "request.json", aged)
        return aged


class OneSessionManySeats(Base):
    def test_every_seat_reaches_the_configured_desktop_title_and_keeps_its_organization(self):
        for org_id, member in self.seats:
            org = self.store.get(org_id)
            self.assertEqual(gui.address(self.store, org, member), ADDRESS)
            self.assertEqual(self.store.seat_config(org_id, member, org).get("surface"), "gui")
        sent = []

        def route(request, config, folder):
            sent.append(request)
            self.queued(request, config, folder)
            self.handle("Stop", last_assistant_message="done " + gui.marker(request))
            return "queued"

        for org_id, member in self.seats:  # one after another: each turn ends with its own Stop receipt
            session, reply, failed, _ = self.run_turn(org_id, member, route)
            self.assertEqual((session, failed), (SID, False))
        self.assertEqual([r["expected"] for r in sent], [ADDRESS] * 3)
        self.assertEqual([(r["org_id"], r["member"]) for r in sent], self.seats)
        for request in sent:
            self.assertTrue(gui.receipt_matches(gui._read(self.folder(request) / "receipt.json"), request))

    def test_one_unanswered_request_holds_every_seat_and_nothing_more_is_sent(self):
        route = mock.Mock(side_effect=self.queued)
        with self.assertRaises(gui.TransportError) as first:
            self.run_turn(self.dept, "relic-head", route)  # queued, but no Stop yet
        self.assertTrue(first.exception.possible)
        for org_id, member in self.seats:
            with self.subTest(seat="%s/%s" % (org_id, member)):
                with self.assertRaises(gui.TransportError) as caught:
                    self.run_turn(org_id, member, route)
                self.assertEqual(caught.exception.outcome, "blocked")
                self.assertFalse(caught.exception.possible)  # nothing was sent: wake.py retries it later
                self.assertTrue(wake.no_turn(caught.exception))  # quietly: no failure count, no receipt
        self.assertEqual(route.call_count, 1)
        self.assertGreater(gui.hold(self.store, SID), gui.PENDING_EXPIRY - 60)

    def test_refused_or_targetless_requests_never_hold_the_session(self):
        for outcome in ("refused", "unavailable"):
            with self.subTest(outcome=outcome):
                def route(request, config, folder):
                    gui._write(folder / "delivery.json", {"outcome": outcome, "records": []})
                    return outcome
                with self.assertRaises(gui.TransportError) as caught:
                    self.run_turn(self.cabinet, "relic-head", route)
                self.assertEqual(caught.exception.outcome, outcome)
                self.assertEqual(gui.hold(self.store, SID), 0)

    def test_an_expired_request_is_never_sent_again_and_a_late_stop_still_answers_it(self):
        with self.assertRaises(gui.TransportError):
            self.run_turn(self.cabinet, "relic-head", self.queued, prompt="the old task")
        old = self.age(gui._read(gui.request_path(self.cabinet, "relic-head")), gui.PENDING_EXPIRY + 60)
        self.assertEqual(gui.hold(self.store, SID), 0)
        sent = []

        def route(request, config, folder):
            sent.append(request)
            return self.queued(request, config, folder)

        with self.assertRaises(gui.TransportError):
            self.run_turn(self.cabinet, "relic-head", route, prompt="a newer task")
        self.assertEqual([r["prompt"] for r in sent], ["a newer task"])  # the old task's intent is not resent
        self.assertNotEqual(sent[0]["nonce"], old["nonce"])
        self.assertEqual(gui._read(self.folder(old) / "expired.json")["outcome"], "queued")
        expired = self.store.events(self.cabinet, kinds=["member.desktop_request_expired"])
        self.assertEqual([e["body"]["nonce"] for e in expired], [old["nonce"]])
        # A late Stop that quotes the old nonce answers the old request, never the newer one.
        self.handle("Stop", last_assistant_message="finally finished " + gui.marker(old))
        self.assertTrue(gui.receipt_matches(gui._read(self.folder(old) / "receipt.json"), old))
        self.assertFalse((self.folder(sent[0]) / "receipt.json").exists())
        self.assertGreater(gui.hold(self.store, SID), 0)  # the newer request still holds the session
        self.handle("Stop", last_assistant_message="newer done " + gui.marker(sent[0]))
        self.assertTrue(gui.receipt_matches(gui._read(self.folder(sent[0]) / "receipt.json"), sent[0]))
        self.assertEqual(gui.hold(self.store, SID), 0)

    def test_a_router_prompt_binds_only_its_own_request(self):
        with self.assertRaises(gui.TransportError):
            self.run_turn(self.dept, "relic-head", self.queued)
        old = self.age(gui._read(gui.request_path(self.dept, "relic-head")), gui.PENDING_EXPIRY + 60)
        sent = []

        def route(request, config, folder):
            sent.append(request)
            return self.queued(request, config, folder)

        with self.assertRaises(gui.TransportError):
            self.run_turn(self.demo, "lead", route)
        new = sent[0]
        self.handle("UserPromptSubmit", prompt="Message from a peer session:\n" + gui.payload(new))
        self.handle("Stop", last_assistant_message="plain final words")
        self.assertEqual(gui._read(self.folder(new) / "receipt.json")["matched_by"], "prompt")
        self.assertFalse((self.folder(old) / "receipt.json").exists())
        # A human prompt afterwards stops the old request from being answered by a quote of its nonce.
        self.handle("UserPromptSubmit", prompt="a human question")
        self.handle("Stop", last_assistant_message="mentions " + gui.marker(old))
        self.assertFalse((self.folder(old) / "receipt.json").exists())

    def prompt_bound_after_an_expired_request(self):
        """An old request expired unanswered, a newer one of another seat was sent, and its router prompt arrived."""
        with self.assertRaises(gui.TransportError):
            self.run_turn(self.cabinet, "relic-head", self.queued, prompt="the old task")
        old = self.age(gui._read(gui.request_path(self.cabinet, "relic-head")), gui.PENDING_EXPIRY + 3600)
        sent = []

        def route(request, config, folder):
            sent.append(request)
            return self.queued(request, config, folder)

        with self.assertRaises(gui.TransportError):
            self.run_turn(self.dept, "relic-head", route, prompt="a newer task")
        new = sent[0]
        self.handle("UserPromptSubmit", prompt="Message from a peer session:\n" + gui.payload(new))
        self.assertEqual(gui._read(self.folder(new) / "binding.json"), {"matched_by": "prompt"})
        self.assertEqual(gui._read(self.folder(old) / "binding.json"), {"matched_by": None})
        return old, new

    def answered(self, *requests):
        return [gui._read(self.folder(r) / "receipt.json").get("matched_by") for r in requests]

    def test_a_late_stop_that_quotes_only_the_old_nonce_never_answers_the_prompt_bound_newer_request(self):
        # The secretariat's reproduction: the reply quotes only the old nonce, so it is the old request's reply.
        old, new = self.prompt_bound_after_an_expired_request()
        self.handle("Stop", last_assistant_message="old finished " + gui.marker(old))
        self.assertEqual(self.answered(old, new), ["public", None])
        self.assertTrue(gui.receipt_matches(gui._read(self.folder(old) / "receipt.json"), old))
        self.assertEqual([r["nonce"] for r, _ in gui_receipt.unresolved(self.store, SID)], [new["nonce"]])
        self.assertGreater(gui.hold(self.store, SID), 0)  # the newer request still holds the session
        self.handle("Stop", last_assistant_message="newer done " + gui.marker(new))
        receipt = gui._read(self.folder(new) / "receipt.json")
        self.assertTrue(gui.receipt_matches(receipt, new))
        self.assertEqual((receipt["matched_by"], receipt["last_assistant_message"]), ("public", "newer done " + gui.marker(new)))
        self.assertEqual(gui.hold(self.store, SID), 0)

    def test_without_a_conflicting_nonce_the_prompt_binding_still_answers(self):
        old, new = self.prompt_bound_after_an_expired_request()
        self.handle("Stop", last_assistant_message="plain final words")
        self.assertEqual(self.answered(old, new), [None, "prompt"])
        self.assertTrue(gui.receipt_matches(gui._read(self.folder(new) / "receipt.json"), new))

    def test_a_reply_that_quotes_both_nonces_answers_both(self):
        old, new = self.prompt_bound_after_an_expired_request()
        self.handle("Stop", last_assistant_message="both done %s %s" % (gui.marker(old), gui.marker(new)))
        self.assertEqual(self.answered(old, new), ["public", "public"])
        self.assertEqual(gui.hold(self.store, SID), 0)

    def test_a_relic_message_that_quotes_the_new_nonce_still_answers_it_beside_an_old_quote(self):
        old, new = self.prompt_bound_after_an_expired_request()
        self.handle("PostToolUse", tool_name="mcp__plugin_relic_org__message",
                    tool_input={"to": ["chief"], "body": "done " + gui.marker(new)})
        self.handle("Stop", last_assistant_message="old finished " + gui.marker(old))
        self.assertEqual(self.answered(old, new), ["public", "relic"])
        self.assertEqual(gui.hold(self.store, SID), 0)

    def test_wake_keeps_the_message_organization_and_waits_while_the_session_owes_a_stop(self):
        later = time.time() + 3600  # past SETTLE and GAP
        self.store.send("chief", ["relic-head"], "please check the build")  # in the cabinet: not the main seat
        start, retry = mock.Mock(), mock.Mock()
        started = wake.dispatch(self.store, self.cabinet, now=later, start=start, age=lambda seat: None, retry=retry)
        self.assertEqual(started, ["relic-head"])
        self.assertIn("pass org=%s" % self.cabinet, start.call_args[0][2])
        wake.finish(self.store, self.cabinet, "relic-head")  # that turn ended
        # The Desktop session now owes another seat's request its Stop: the next message waits, quietly.
        with self.assertRaises(gui.TransportError):
            self.run_turn(self.dept, "relic-head", self.queued)
        self.store.send("chief", ["relic-head"], "one more thing")
        start.reset_mock()
        self.assertEqual(wake.dispatch(self.store, self.cabinet, now=later + 3600, start=start,
                                       age=lambda seat: None, retry=retry), [])
        start.assert_not_called()
        self.assertTrue(retry.called)
        self.assertNotIn("failures", (self.store.get(self.cabinet).get("wake") or {}).get("members", {}).get("relic-head", {}))

    def test_after_expiry_the_session_still_waits_while_it_is_busy(self):
        with self.assertRaises(gui.TransportError):
            self.run_turn(self.dept, "relic-head", self.queued)
        self.age(gui._read(gui.request_path(self.dept, "relic-head")), gui.PENDING_EXPIRY + 60)
        self.store.send("chief", ["relic-head"], "after the expiry")
        later = time.time() + 3600
        start, retry = mock.Mock(), mock.Mock()
        # Another seat of the session still has a runner: one turn at a time per session.
        runner.write_state(self.demo, "lead", {"status": "running", "started": time.time(), "pid": os.getpid()})
        self.assertEqual(wake.dispatch(self.store, self.cabinet, now=later, start=start, age=lambda seat: None,
                                       retry=retry), [])
        runner.write_state(self.demo, "lead", {"status": "done"})
        # The Desktop session is still writing its transcript (the person, or the old turn): wait for it to settle.
        self.assertEqual(wake.dispatch(self.store, self.cabinet, now=later, start=start, age=lambda seat: 5,
                                       retry=retry), [])
        start.assert_not_called()
        self.assertEqual(wake.dispatch(self.store, self.cabinet, now=later, start=start, age=lambda seat: None,
                                       retry=retry), ["relic-head"])


class SeatReplies(Base):
    def test_a_seat_reply_reaches_members_above_that_are_not_in_the_thread(self):
        root = self.store.send("chief", ["relic-head"], "status of the fix?", org=self.dept)["message_id"]
        reply = self.store.send(SID, ["%s/chief" % self.cabinet, "%s/progress-supervisor" % self.cabinet],
                                "fixed in the kernel branch", reply_to=root, org=self.dept)
        self.assertEqual(reply["reply_to"], root)  # the reply stays in this seat's thread
        self.assertEqual(reply["delivered_orgs"], [self.cabinet])
        here = [m for m in self.store.history(self.dept) if m["id"] == reply["message_id"]][0]
        self.assertEqual((here["from"], here["reply_to"]), ("relic-head", root))
        copies = [m for m in self.store.history(self.cabinet) if m["body"] == "fixed in the kernel branch"]
        self.assertEqual(sorted(m["to"][0] for m in copies), ["chief", "progress-supervisor"])
        self.assertEqual({m["from"] for m in copies}, {"%s/relic-head" % self.dept})

    def test_unreachable_organizations_and_unknown_members_are_still_refused(self):
        root = self.store.send("chief", ["relic-head"], "status?", org=self.dept)["message_id"]
        with self.assertRaisesRegex(OrgError, "neither above nor below"):
            self.store.send(SID, ["%s/stranger" % self.other], "hello", reply_to=root, org=self.dept)
        with self.assertRaisesRegex(OrgError, "has no member nobody"):
            self.store.send(SID, ["%s/nobody" % self.cabinet], "hello", reply_to=root, org=self.dept)
        with self.assertRaisesRegex(OrgError, "Unknown members"):
            self.store.send(SID, ["nobody"], "hello", reply_to=root, org=self.dept)


if __name__ == "__main__":
    unittest.main()
