"""Keep-going (持续推进): an organization with keep-going on, whose subtree has gone quiet with work unfinished, gets one
notice to its driver; nothing while anyone works or a wake-up is under way; a second notice only after progress; a
question to the person holds them for a while; a daily cap; a driver that cannot be woken is reported to the person
once. Turns are recorded by a fake starter that writes run states the way runner.start_turn does."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core import context, runner, wake  # noqa: E402
from relic_core.store import HUMAN, SYSTEM, OrgError, Store  # noqa: E402

LEAD, CODY, ANA, BOB = "lead-session", "codex:th-cody", "sess-ana", "sess-bob"
GOAL = "Keep the research going until it has a result."


class Drive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        os.environ["RELIC_LANG"] = "en-US"
        self.store = Store()
        self.oid = self.store.create(LEAD, "Lab", "research", "lead")["id"]  # leader-led; lead has no config
        self.store.add_seat(self.oid, "cody", "head", runner.default_config("codex"))
        self.store.join(CODY, self.oid, "cody")
        self.store.add_seat(self.oid, "ana", "api", runner.default_config("claude-code"))
        self.store.join(ANA, self.oid, "ana")
        self.child = self.store.found("Bench", "benchmarks")["id"]
        self.store.set_parent(self.child, self.oid)
        self.store.add_seat(self.child, "bob", "bench", runner.default_config("claude-code"))
        self.store.join(BOB, self.child, "bob")
        self.started, self.retries, self.ages = [], [], {}
        self.settle, wake.SETTLE = wake.SETTLE, 0

    def tearDown(self):
        wake.SETTLE = self.settle
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    # ------------------------------------------------------------------ helpers
    def start(self, org_id, member, prompt, wake_from, wake_hop, wake_message_ids=None):
        self.started.append((org_id, member, wake_from, prompt, wake_hop))
        runner.write_state(org_id, member, {"status": "running", "started": time.time(), "pid": os.getpid(),
                                            "wake_hop": wake_hop, "wake_message_ids": wake_message_ids})

    def finish(self, member, org_id=None):
        org_id = org_id or self.oid
        runner.write_state(org_id, member, {"status": "done", "started": time.time()})
        wake.finish(self.store, org_id, member)

    def check(self, at=None):
        return wake.drive_check(self.store, self.oid, now=time.time() + 700 if at is None else at,
                                age=lambda seat: self.ages.get(seat["carrier"]), start=self.start,
                                retry=lambda org_id, delay: self.retries.append(delay))

    def drive(self, driver="cody", goal=GOAL):
        return self.store.set_drive(self.oid, True, goal=goal, driver=driver)

    def notices(self, to=None):
        with self.store.db() as db:
            rows = db.execute("SELECT id, recipients, body, hop FROM messages WHERE sender=? ORDER BY id",
                              (SYSTEM,)).fetchall()
        return [r for r in rows if to is None or to in r[1]]

    # ------------------------------------------------------------------ the notice
    def test_nothing_happens_without_keep_going(self):
        self.assertEqual(self.store.drive_checks(), {})
        self.assertEqual(wake.drive_due(self.store, time.time() + 10_000), [])
        self.assertEqual(self.notices(), [])

    def test_a_quiet_organization_wakes_its_driver_with_the_goal(self):
        self.drive()
        outcome = self.check()
        self.assertEqual(outcome["state"], "nudged")
        [(mid, recipients, body, hop)] = self.notices()
        self.assertEqual((recipients, hop), ('["cody"]', 0))
        self.assertIn("[Relic keep-going]", body)
        self.assertIn(GOAL, body)
        self.assertIn("set by the person", body)
        [(org_id, member, senders, prompt, wake_hop)] = self.started
        self.assertEqual((org_id, member, senders, wake_hop), (self.oid, "cody", [SYSTEM], 1))
        self.assertIn("[Relic keep-going]", prompt)
        self.assertIn("As the driver, decide the next step", prompt)
        self.assertNotIn("reply_to=<id>", prompt)  # nobody wrote it: there is nobody to answer
        drive = self.store.get(self.oid)["drive"]
        self.assertEqual(drive["last"]["id"], mid)
        self.assertEqual(len(drive["nudges"]), 1)

    def test_the_notice_lists_unfinished_work_below_and_speaks_the_persons_language(self):
        os.environ["RELIC_LANG"] = "zh-CN"
        self.store.work(BOB, "task", {"title": "找更难的基准", "status": "working"})
        self.store.work(ANA, "task", {"title": "finished one", "status": "done", "evidence": ["x"],
                                      "report": "done"})
        self.drive(goal="人的原话：一步做完接着做下一步。")
        self.assertEqual(self.check()["state"], "nudged")
        body = self.notices()[0][2]
        self.assertIn("[Relic 持续推进]", body)
        self.assertIn("人的原话：一步做完接着做下一步。", body)
        self.assertIn("Bench T1 [working] bob: 找更难的基准", body)
        self.assertNotIn("finished one", body)

    def test_a_notice_starts_a_new_exchange_after_the_hop_limit(self):
        self.drive()
        with self.store.db() as db:  # a reply deep in an exchange wakes nobody
            db.execute("INSERT INTO messages(org_id,sender,recipients,body,at,hop) VALUES(?,?,?,?,?,?)",
                       (self.oid, "ana", '["cody"]', "done with step 6", "2000-01-01T00:00:00Z", wake.MAX_HOPS))
        self.assertEqual(self.check()["state"], "nudged")
        self.assertEqual([s[4] for s in self.started], [1])

    # ------------------------------------------------------------------ not while work goes on
    def test_no_notice_while_a_turn_runs_anywhere_below(self):
        self.drive()
        runner.write_state(self.child, "bob", {"status": "running", "started": time.time(), "pid": os.getpid()})
        at = time.time() + 700
        outcome = self.check(at)
        self.assertEqual(outcome["state"], "busy")
        self.assertIn("bob", outcome["why"])
        self.assertEqual(outcome["next"], at + wake.DRIVE_RECHECK)
        self.assertEqual(self.store.drive_checks()[self.oid], at + wake.DRIVE_RECHECK)
        self.assertEqual(self.notices(), [])

    def test_no_notice_during_an_open_turn_unless_its_transcript_went_stale(self):
        self.drive()
        self.store.record_activity(ANA, "Read", {"file_path": "x.py"})  # opens ana's turn episode
        self.assertEqual(self.check(time.time() + 7200)["state"], "busy")
        self.ages[ANA] = wake.DRIVE_STALE + 60  # interrupted: the Stop never came, the transcript is still
        self.assertEqual(self.check(time.time() + 7200)["state"], "nudged")

    def test_no_notice_while_a_wake_up_is_due(self):
        self.drive()
        with self.store.change(self.oid) as (org, db):
            org.setdefault("wake", {}).setdefault("members", {})["ana"] = {"retry_at": time.time() + 900}
        self.assertEqual(self.check(time.time() + 60)["state"], "busy")

    def test_recent_work_or_messages_below_make_it_wait(self):
        self.drive()
        self.store.record_activity(BOB, "Bash", {"command": "pytest"})
        self.store.end_turn(BOB)
        outcome = self.check(time.time() + 60)
        self.assertEqual(outcome["state"], "wait")
        self.assertGreater(outcome["next"], time.time() + wake.DRIVE_QUIET - 5)
        self.ages[CODY] = 30  # the driver's transcript changed half a minute ago (the person is talking to it)
        self.assertEqual(self.check()["state"], "wait")

    # ------------------------------------------------------------------ one notice per progress
    def test_a_second_notice_needs_progress(self):
        self.drive()
        self.assertEqual(self.check(time.time())["state"], "nudged")  # nothing has happened here yet: quiet already
        self.finish("cody")
        at = time.time() + 1400
        outcome = self.check(at)  # the driver looked around and did nothing
        self.assertEqual(outcome["state"], "idle")
        self.assertEqual(outcome["next"], at + wake.DRIVE_IDLE)  # a stopped organization is looked at seldom
        self.store.record_activity(ANA, "Read", {"file_path": "notes.md"})  # reading is not progress
        self.store.end_turn(ANA)
        self.assertEqual(self.check(time.time() + 1400)["state"], "idle")
        self.store.record_activity(BOB, "Bash", {"command": "python run.py"})  # a command below is
        self.store.end_turn(BOB)
        self.assertEqual(self.check(time.time() + 1400)["state"], "nudged")
        self.assertEqual(len(self.notices("cody")), 2)

    def test_a_message_between_members_is_progress_but_a_report_to_the_person_is_not(self):
        self.drive()
        self.check()
        self.finish("cody")
        self.store.send(CODY, [HUMAN], "Goal reached: here is the summary.")
        self.assertEqual(self.check(time.time() + 1400)["state"], "idle")
        self.store.send(CODY, ["ana"], "Next step: run the harder set.")
        self.store.unread(ANA)  # ana read it (no wake-up pending in this test)
        self.assertEqual(self.check(time.time() + 1400)["state"], "nudged")

    def test_a_question_to_the_person_holds_the_notices_for_an_hour(self):
        self.drive()
        mid = self.store.send(ANA, [HUMAN], "Should we spend more than the approved budget?")["message_id"]
        outcome = self.check()
        self.assertEqual((outcome["state"], outcome["question"]), ("asked", mid))
        self.assertEqual(self.notices(), [])
        self.assertEqual(self.check(time.time() + wake.DRIVE_ASK_WAIT + 60)["state"], "nudged")

    def test_the_persons_answer_releases_the_question(self):
        self.drive()
        self.store.send(ANA, [HUMAN], "A or B?")
        self.store.send_from_human(self.oid, ["ana"], "B.")
        self.store.unread(ANA)
        self.assertEqual(self.check()["state"], "nudged")

    def test_a_daily_cap(self):
        self.drive()
        with self.store.change(self.oid) as (org, db):
            org["drive"]["nudges"] = [time.time() - 3600 + i for i in range(wake.DRIVE_DAILY)]
        outcome = self.check()
        self.assertEqual(outcome["state"], "capped")
        self.assertEqual(self.notices(), [])

    # ------------------------------------------------------------------ switches
    def test_a_driver_that_cannot_be_woken_is_reported_to_the_person_once(self):
        self.drive(driver="lead")
        self.assertEqual(self.check()["state"], "unreachable")
        self.assertEqual(self.check(time.time() + 2000)["state"], "unreachable")
        [(mid, recipients, body, hop)] = self.notices()
        self.assertEqual(recipients, '["human"]')
        self.assertIn("lead cannot be woken", body)

    def test_stop_all_pauses_keep_going(self):
        self.drive()
        self.store.set_auto_wake(self.oid, False, reason="stopped with Stop all in the Relic window")
        self.assertEqual(self.check()["state"], "paused")
        self.assertEqual(self.notices(), [])

    def test_off_removes_the_check(self):
        self.drive()
        self.assertIn(self.oid, self.store.drive_checks())
        self.store.set_drive(self.oid, False)
        self.assertEqual(self.store.drive_checks(), {})
        self.assertEqual(wake.drive_due(self.store, time.time() + 10_000), [])

    def test_a_due_check_is_claimed_once(self):
        self.drive()
        at = time.time() + 5
        self.assertEqual(self.store.drive_due(at), [self.oid])
        self.assertEqual(self.store.drive_due(at), [])  # another process, the same moment
        self.assertEqual(self.store.drive_due(at + 61), [self.oid])

    def test_any_dispatch_runs_the_checks_that_are_due(self):
        self.drive()
        wake.dispatch(self.store, self.child, now=time.time() + 700, start=self.start,
                      age=lambda seat: None, retry=lambda org_id, delay: None)
        self.assertEqual([(s[0], s[1]) for s in self.started], [(self.oid, "cody")])

    def test_the_next_check_always_has_a_retry_coming(self):
        """Whoever runs the checks arms a delayed dispatch for the earliest next one, so the checks go on with the
        Relic App closed and no hook of this version running."""
        self.drive()
        armed = []
        runner.write_state(self.child, "bob", {"status": "running", "started": time.time(), "pid": os.getpid()})
        at = time.time() + 700
        [(org_id, outcome)] = wake.drive_due(self.store, at, start=self.start, age=lambda seat: None,
                                             retry=lambda org_id, delay: armed.append((org_id, delay)))
        self.assertEqual((org_id, outcome["state"]), (self.oid, "busy"))
        self.assertEqual(armed, [(self.oid, wake.DRIVE_RECHECK + 1)])
        self.assertEqual(wake.drive_due(self.store, at + 1, retry=lambda org_id, delay: armed.append(delay)), [])
        self.assertEqual(armed[-1], wake.DRIVE_RECHECK)  # nothing due yet: the same retry is armed again

    def test_the_leader_or_an_organization_above_switches_it(self):
        with self.assertRaises(OrgError):
            self.store.work(ANA, "drive", {"on": True, "goal": GOAL})  # not the leader
        with self.assertRaises(OrgError):
            self.store.work(LEAD, "drive", {"on": True})  # no goal yet
        result = self.store.work(LEAD, "drive", {"on": True, "goal": GOAL, "driver": "cody"})
        self.assertEqual((result["on"], result["driver"], result["set_by"]), (True, "cody", "lead"))
        with self.assertRaises(OrgError):
            self.store.work(LEAD, "drive", {"on": False})  # off needs a reason
        self.store.work(LEAD, "drive", {"on": False, "reason": "the goal is reached"})
        with self.store.db() as db:
            told = db.execute("SELECT body FROM messages WHERE recipients=?", ('["human"]',)).fetchall()
        self.assertEqual(told, [("lead switched keep-going off in Lab: the goal is reached",)])
        below = self.store.work(LEAD, "drive", {"on": True, "goal": GOAL, "org": self.child})
        self.assertEqual((below["driver"], below["set_by"]), ("bob", "%s/lead" % self.oid))
        self.assertIn(self.child, self.store.drive_checks())

    def test_members_below_are_told_who_drives(self):
        self.drive()
        bench = self.store.get(self.child)
        text = context.render(self.store, bench, "bob")
        self.assertIn("Keep-going (持续推进) is on for Lab", text)
        self.assertIn("the driver is cody", text)
        self.assertIn(GOAL, text)
        self.assertIn("the driver is you", context.render(self.store, self.store.get(self.oid), "cody"))

    def test_reserved_names(self):
        for name in (HUMAN, SYSTEM):
            with self.assertRaises(OrgError):
                self.store.add_seat(self.oid, name)
            with self.assertRaises(OrgError):
                self.store.join("sess-x-" + name, self.oid, name)


if __name__ == "__main__":
    unittest.main()
