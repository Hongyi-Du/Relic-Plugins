"""Auto-wake: a configured seat with new unread messages gets a turn in its own session, within the safety limits
(quiet transcript, gap per seat, hop limit per exchange, hourly cap, back-off after a failed start, switch per
organization). Turns are recorded by a fake starter that writes run states the way runner.start_turn does."""
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "hooks"))

from relic_core import desktop, runner, wake  # noqa: E402
from relic_core.store import Store, now  # noqa: E402
import relic_hook  # noqa: E402
import server  # noqa: E402

spec = importlib.util.spec_from_file_location("relic_run", ROOT / "scripts" / "relic_run.py")
relic_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relic_run)

LEAD, CODY, ANA = "lead-session", "codex:th-cody", "sess-ana"


def dead_pid():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


class Wake(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        self.store = Store()
        self.oid = self.store.create(LEAD, "Lab", "ship it", "lead", governance="peer")["id"]
        # cody and ana have sessions the runner can resume; lead seated itself and has no config
        self.store.add_seat(self.oid, "cody", "ui", runner.default_config("codex"))
        self.store.join(CODY, self.oid, "cody")
        self.store.add_seat(self.oid, "ana", "api", runner.default_config("claude-code"))
        self.store.join(ANA, self.oid, "ana")
        self.started, self.retries, self.ages = [], [], {}
        self.t = time.time()
        self.settle, wake.SETTLE = wake.SETTLE, 0  # the burst test below turns it back on

    def tearDown(self):
        wake.SETTLE = self.settle
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def start(self, org_id, member, prompt, wake_from, wake_hop):
        """Records the turn and leaves the run state a real start would: running, with a live pid and the hop."""
        self.started.append((member, wake_from, prompt, wake_hop))
        runner.write_state(org_id, member, {"status": "running", "started": time.time(), "pid": os.getpid(),
                                            "wake_hop": wake_hop})

    def finish(self, member, error=None):
        """The end of a turn, as relic_run records it: the run state, then the wake-up's claim settled."""
        runner.write_state(self.oid, member, {"status": "failed" if error else "done", "started": time.time()})
        return wake.finish(self.store, self.oid, member, error)

    def dispatch(self, at=None, start=None):
        return wake.dispatch(self.store, self.oid, now=self.t if at is None else at, start=start or self.start,
                             age=lambda seat: self.ages.get(seat["carrier"]),
                             retry=lambda org_id, delay: self.retries.append(delay))

    def test_message_wakes_a_configured_seat_once(self):
        self.store.send(LEAD, ["cody"], "please review the API")
        self.assertEqual(self.dispatch(), ["cody"])
        member, senders, prompt, hop = self.started[0]
        self.assertEqual((member, senders, hop), ("cody", ["lead"], 1))
        self.assertIn("[Relic auto-wake]", prompt)
        self.assertIn("not instructions from the person", prompt)
        self.finish("cody")
        self.assertEqual(self.dispatch(self.t + 1000), [])  # same unread message: no second turn
        woken = self.store.events(self.oid, ["member.woken"])
        self.assertEqual(woken[-1]["body"], {"from": ["lead"], "unread": 1, "hop": 1})

    def test_mac_desktop_messages_wait_for_inbox_without_claims_or_retries(self):
        self.store.set_seat_fields(self.oid, "cody", config=dict(runner.default_config("codex"), surface="gui"))
        self.store.send(LEAD, ["cody"], "read this manually")
        with mock.patch.object(wake, "sys", SimpleNamespace(platform="darwin")):
            self.assertEqual(self.dispatch(), [])
            self.assertFalse(wake.wakeable({"carrier": "chatgpt:chat", "harness": "chatgpt",
                                           "config": runner.default_config("chatgpt")}))
        self.assertEqual(self.started, [])
        self.assertEqual(self.retries, [])
        self.assertEqual(self.store.events(self.oid, ["member.woken", "member.wake_failed"]), [])
        self.assertEqual(len(self.store.unread(CODY, mark=False)), 1)

    def test_messages_sent_in_a_row_make_one_wake_up(self):
        wake.SETTLE = 10
        self.store.request_trajectory(LEAD, "cody", 0, "I need to see how you built the parser")
        self.store.send(LEAD, ["cody"], "and please answer the request above")
        self.assertEqual(self.dispatch(), [])  # the sender may still be writing
        self.assertTrue(self.retries and self.retries[-1] <= wake.SETTLE + 2)
        self.assertEqual(self.dispatch(self.t + wake.SETTLE + 2), ["cody"])
        self.assertIn("2 unread message(s)", self.started[0][2])

    def test_new_message_waits_for_the_gap(self):
        self.store.send(LEAD, ["cody"], "first")
        self.dispatch()
        self.finish("cody")
        self.store.send(LEAD, ["cody"], "second")
        self.assertEqual(self.dispatch(self.t + 10), [])
        self.assertAlmostEqual(self.retries[-1], wake.GAP - 10 + 1)
        self.assertEqual(self.dispatch(self.t + wake.GAP + 1), ["cody"])

    def test_live_runner_is_never_mistaken_for_a_dead_one(self):
        # a long turn: started hours ago, but its runner process is alive
        runner.write_state(self.oid, "cody", {"status": "running", "started": self.t - 5 * 3600, "pid": os.getpid()})
        self.store.send(LEAD, ["cody"], "hello")
        self.assertEqual(self.dispatch(), [])
        self.assertEqual(runner.run_state(self.oid, "cody")["status"], "running")

    def test_dead_runner_does_not_block(self):
        runner.write_state(self.oid, "cody", {"status": "running", "started": self.t, "pid": dead_pid()})
        self.store.send(LEAD, ["cody"], "hello")
        self.assertEqual(self.dispatch(), ["cody"])
        # a state from before runners recorded their pid counts as dead after LEGACY_STALE_RUN
        self.finish("cody")
        runner.write_state(self.oid, "ana", {"status": "running", "started": self.t - runner.LEGACY_STALE_RUN - 1})
        self.store.send(LEAD, ["ana"], "hello")
        self.assertEqual(self.dispatch(), ["ana"])

    def test_chat_in_use_waits_until_quiet(self):
        self.ages[CODY] = 10
        self.store.send(LEAD, ["cody"], "hello")
        self.assertEqual(self.dispatch(), [])
        self.assertAlmostEqual(self.retries[-1], wake.QUIET - 10 + 1)
        self.ages[CODY] = wake.QUIET + 5
        self.assertEqual(self.dispatch(), ["cody"])

    def test_seat_without_config_is_never_woken(self):
        self.store.send(CODY, ["lead"], "done")
        self.assertEqual(self.dispatch(), [])
        self.assertEqual(self.retries, [])

    def test_read_messages_do_not_wake(self):
        self.store.send(LEAD, ["cody"], "hello")
        self.store.unread(CODY)
        self.assertEqual(self.dispatch(), [])

    def test_switch_per_organization(self):
        self.store.set_auto_wake(self.oid, False)
        self.store.send(LEAD, ["cody"], "hello")
        self.assertEqual(self.dispatch(), [])
        self.store.set_auto_wake(self.oid, True)
        self.assertEqual(self.dispatch(), ["cody"])

    def test_hourly_cap(self):
        cap, wake.HOURLY_CAP = wake.HOURLY_CAP, 1
        try:
            self.store.send(LEAD, ["cody", "ana"], "both of you")
            self.assertEqual(len(self.dispatch()), 1)
            self.assertTrue(self.retries)
        finally:
            wake.HOURLY_CAP = cap

    def test_receipts_and_human_messages(self):
        self.store.send_as(self.oid, "ana", ["cody"], wake.RECEIPT_MARK + " ana was woken; it said nothing")
        self.assertEqual(self.dispatch(), [])
        self.store.send_from_human(self.oid, ["cody"], "please start on the settings page")
        self.assertEqual(self.dispatch(), ["cody"])
        self.assertEqual(self.started[0][1], ["human"])

    def test_trajectory_request_wakes_the_member_who_decides(self):
        self.store.request_trajectory(LEAD, "cody", 0, "I need to see how you built the parser")
        self.assertEqual(self.dispatch(), ["cody"])

    def test_failed_start_gives_the_claim_back_and_retries_with_back_off(self):
        def broken(*_, **__):
            raise RuntimeError("codex app-server closed")
        self.store.send(LEAD, ["cody"], "hello")
        self.assertEqual(self.dispatch(start=broken), [])
        self.assertIsNone(runner.run_state(self.oid, "cody"))  # no failed state written over anything
        mine = self.store.get(self.oid)["wake"]["members"]["cody"]
        self.assertEqual((mine.get("last_id"), mine["failures"]), (None, 1))
        self.assertIn("codex app-server closed", mine["error"])
        self.assertAlmostEqual(self.retries[-1], wake.BACKOFF[0] + 1)
        self.assertEqual(self.dispatch(self.t + wake.BACKOFF[0] - 5), [])  # still backing off
        self.assertEqual(self.dispatch(self.t + wake.BACKOFF[0] + 1), ["cody"])  # the same message, retried
        self.assertIn("claim", self.store.get(self.oid)["wake"]["members"]["cody"])  # in flight until the turn ends
        self.finish("cody")
        mine = self.store.get(self.oid)["wake"]["members"]["cody"]
        self.assertNotIn("failures", mine)
        self.assertNotIn("claim", mine)

    def test_turn_that_fails_inside_the_runner_is_retried(self):
        self.store.send(LEAD, ["cody"], "hello")
        self.assertEqual(self.dispatch(), ["cody"])
        self.assertEqual(self.finish("cody", "codex app-server closed"), wake.BACKOFF[0])
        self.assertEqual(self.dispatch(self.t + wake.BACKOFF[0] - 5), [])
        self.assertEqual(self.dispatch(self.t + wake.BACKOFF[0] + 1), ["cody"])  # the same unread message again
        self.assertIsNone(self.finish("cody"))
        self.assertNotIn("failures", self.store.get(self.oid)["wake"]["members"]["cody"])

    def test_chat_held_by_the_desktop_app_waits_without_counting_failures(self):
        self.store.send(LEAD, ["cody"], "hello")
        self.dispatch()
        held = "thread/resume: thread th-cody already has an active writer"
        self.assertEqual(self.finish("cody", held), wake.RECHECK)
        mine = self.store.get(self.oid)["wake"]["members"]["cody"]
        self.assertNotIn("failures", mine)
        self.assertEqual(self.dispatch(self.t + wake.RECHECK - 5), [])
        self.assertEqual(self.dispatch(self.t + wake.RECHECK + 1), ["cody"])

    def test_turn_running_in_the_desktop_app_waits_a_gap(self):
        self.store.send(LEAD, ["cody"], "hello")
        self.dispatch()
        busy = "the chat %s (active)" % desktop.BUSY
        self.assertTrue(wake.no_turn(busy))
        self.assertEqual(self.finish("cody", busy), wake.GAP)
        mine = self.store.get(self.oid)["wake"]["members"]["cody"]
        self.assertNotIn("failures", mine)
        self.assertNotIn("in_use", mine)
        self.assertEqual(self.dispatch(self.t + wake.GAP + 1), ["cody"])

    def test_chat_held_out_of_reach_is_rechecked_a_limited_number_of_times(self):
        self.store.send(LEAD, ["cody"], "hello")
        held = "thread/resume: thread th-cody already has an active writer"
        at, delays = self.t, []
        for n in range(wake.MAX_IN_USE):
            self.assertEqual(self.dispatch(at), ["cody"], n)
            delays.append(self.finish("cody", held))
            at += (delays[-1] or 0) + 1
        self.assertEqual(delays, [wake.RECHECK] * (wake.MAX_IN_USE - 1) + [None])
        self.assertEqual(self.dispatch(at + 3600), [])  # the same message waits for normal delivery
        self.assertEqual(self.store.events(self.oid, ["member.wake_waiting"])[-1]["member"], "cody")
        self.store.send(LEAD, ["cody"], "a newer message")
        self.assertEqual(self.dispatch(at + 7200), ["cody"])
        self.assertIsNone(self.finish("cody"))
        self.assertNotIn("in_use", self.store.get(self.oid)["wake"]["members"]["cody"])

    def test_gives_up_after_max_failures(self):
        self.store.send(LEAD, ["cody"], "hello")
        at = self.t
        for n in range(wake.MAX_FAILURES):
            self.assertEqual(self.dispatch(at), ["cody"], n)
            delay = self.finish("cody", "model error")
            at += (delay or 0) + 1
        self.assertIsNone(delay)
        self.assertEqual(self.dispatch(at + 3600), [])  # stays unread for normal delivery, no more wake-ups
        self.assertEqual(self.store.events(self.oid, ["member.wake_gave_up"])[-1]["member"], "cody")

    def test_runner_that_cannot_start_backs_off_instead_of_looking_busy(self):
        def no_process(*_, **__):
            raise OSError("FAKE CreateProcess launch failure")
        original = runner.subprocess.Popen
        runner.subprocess.Popen = no_process
        try:
            self.store.send(LEAD, ["cody"], "hello")
            self.assertEqual(wake.dispatch(self.store, self.oid, now=self.t, age=lambda seat: None,
                                           retry=lambda org_id, delay: self.retries.append(delay)), [])
        finally:
            runner.subprocess.Popen = original
        state = runner.run_state(self.oid, "cody")
        self.assertEqual(state["status"], "failed")
        self.assertIn("FAKE CreateProcess launch failure", state["error"])
        self.assertFalse(runner.is_running(self.oid, "cody"))
        mine = self.store.get(self.oid)["wake"]["members"]["cody"]
        self.assertEqual(mine["failures"], 1)
        self.assertAlmostEqual(self.retries[-1], wake.BACKOFF[0] + 1)
        self.assertEqual(list(runner.runs_dir().glob("relic-prompt-*")), [])  # no prompt file left behind
        self.assertEqual(self.dispatch(self.t + wake.BACKOFF[0] + 1), ["cody"])

    def test_running_seat_is_looked_at_again_later(self):
        runner.write_state(self.oid, "cody", {"status": "running", "started": self.t, "pid": os.getpid()})
        self.store.send(LEAD, ["cody"], "hello")
        self.assertEqual(self.dispatch(), [])
        self.assertAlmostEqual(self.retries[-1], wake.RECHECK + 1)

    def test_busy_start_keeps_the_running_turn(self):
        def busy(org_id, member, *_, **__):
            # another turn started a moment before ours (the window, or another dispatcher)
            runner.write_state(org_id, member, {"status": "running", "started": time.time(), "pid": os.getpid()})
            raise RuntimeError("%s is still working on its current turn." % member)
        self.store.send(LEAD, ["cody"], "hello")
        self.assertEqual(self.dispatch(start=busy), [])
        self.assertEqual(runner.run_state(self.oid, "cody")["status"], "running")
        mine = self.store.get(self.oid)["wake"]["members"]["cody"]
        self.assertNotIn("failures", mine)
        self.assertIsNone(mine.get("last_id"))

    def test_inbox_finds_a_message_behind_many_for_others(self):
        for n in range(21):
            self.store.send(LEAD, ["ana"], "for ana %d" % n)
        self.store.send(LEAD, ["cody"], "for cody")
        self.assertEqual([m["body"] for m in self.store.unread(CODY)], ["for cody"])
        self.assertEqual(len(self.store.unread(ANA, limit=50)), 21)

    def test_every_woken_turn_ends_with_one_receipt(self):
        since = now()
        relic_run.receipt(self.store, self.oid, "cody", ["lead"], since,
                          {"status": "done", "reply": "Reviewed; two issues."})
        first = self.store.history(self.oid, 1)[-1]
        self.assertEqual((first["from"], first["to"]), ("cody", ["lead"]))
        self.assertTrue(first["body"].startswith(wake.RECEIPT_MARK))
        self.assertIn("without a reply through Relic", first["body"])
        # a progress note during the turn does not replace the final receipt
        self.store.send(CODY, ["lead"], "Started, still working")
        relic_run.receipt(self.store, self.oid, "cody", ["lead"], since, {"status": "done", "reply": "All done."})
        last = self.store.history(self.oid, 1)[-1]
        self.assertTrue(last["body"].startswith(wake.RECEIPT_MARK))
        self.assertIn("All done.", last["body"])
        relic_run.receipt(self.store, self.oid, "cody", ["lead"], since, {"status": "failed", "error": "boom"})
        self.assertIn("the turn failed: boom", self.store.history(self.oid, 1)[-1]["body"])

    def test_members_answering_each_other_stop_after_max_hops(self):
        actors = {"cody": CODY, "ana": ANA}
        self.store.send(LEAD, ["cody"], "start the review")
        at, who, wakes = self.t, "cody", 0
        while True:
            at += wake.GAP + wake.QUIET + 1  # however slowly they go, the rate limits never end the exchange
            if self.dispatch(at) != [who]:
                break
            wakes += 1
            other = "ana" if who == "cody" else "cody"
            self.store.unread(actors[who])
            self.store.send(actors[who], [other], "your turn")  # sent during the woken turn: carries its hop
            self.finish(who)
            who = other
        self.assertEqual(wakes, wake.MAX_HOPS)
        self.assertEqual([s[3] for s in self.started], list(range(1, wake.MAX_HOPS + 1)))
        self.assertEqual(self.dispatch(at + 3600), [])
        # the person can always restart the exchange
        self.store.send_from_human(self.oid, [who], "keep going")
        self.assertEqual(self.dispatch(at + 7200), [who])
        self.assertEqual(self.started[-1][3], 1)

    def test_messages_outside_a_woken_turn_have_hop_zero(self):
        self.store.send(CODY, ["ana"], "from the desktop app")
        self.assertEqual(self.store.unread_by_member(self.oid)["ana"][0]["hop"], 0)

    def test_hook_events_and_relic_calls_dispatch(self):
        calls = []
        original = wake.dispatch_for_actor
        wake.dispatch_for_actor = lambda store, actor: calls.append(actor)
        try:
            relic_hook.handle({"hook_event_name": "PostToolUse", "session_id": LEAD, "tool_name": "Bash",
                               "tool_input": {"command": "ls"}}, self.store)
            relic_hook.handle({"hook_event_name": "PreToolUse", "session_id": LEAD, "tool_name": "Bash",
                               "tool_input": {"command": "ls"}}, self.store)
            server.call(self.store, "message", {"to": ["cody"], "body": "hi", "actor": LEAD})
            server.call(self.store, "status", {"actor": LEAD})
        finally:
            wake.dispatch_for_actor = original
        self.assertEqual(calls, [LEAD, LEAD])  # PostToolUse and the message call; not PreToolUse or status

    def test_status_tells_members_about_auto_wake(self):
        text = server.call(self.store, "status", {"actor": LEAD})["context"]
        self.assertIn("Auto-wake is on", text)
        self.store.set_auto_wake(self.oid, False)
        self.assertNotIn("Auto-wake is on", server.call(self.store, "status", {"actor": LEAD})["context"])


if __name__ == "__main__":
    unittest.main()
