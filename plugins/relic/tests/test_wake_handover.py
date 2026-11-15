"""Version skew between Relic processes: member turns and background checks start from the Relic installed last
(runner.entry); Desktop wake-ups an older Relic failed on its CLI route are handed over to the newer one
(wake.hand_over_desktop); and a session reaches an organization through whichever of its seats is above it
(Store.reach)."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core import api, runner, wake  # noqa: E402
from relic_core.store import OrgError, Store  # noqa: E402

LEAD, BENCH, CODY = "lead-h", "4bd471ba-0000-4000-8000-000000000001", "codex:th-cody"
OLD = wake.OLD_DESKTOP_ROUTE + "; API credentials are not used"


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"RELIC_HOME": str(Path(self.tmp.name) / "relic"), "RELIC_LANG": "en-US"})
        env.start()
        self.addCleanup(env.stop)
        self.store = Store()


class InstalledRelicStartsTheWork(Fixture):
    def setUp(self):
        super().setUp()
        self.plugin = Path(self.tmp.name) / "Relic-newer" / "plugins" / "relic"
        for name in ("relic_core/runner.py", "scripts/relic_run.py", "scripts/relic_dispatch.py"):
            (self.plugin / name).parent.mkdir(parents=True, exist_ok=True)
            (self.plugin / name).write_text("# the newer Relic\n", encoding="utf-8")
        self.record({"plugin": str(self.plugin)})
        self.own = ROOT / "scripts"

    def record(self, data):
        path = runner.data_home() / runner.CURRENT
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")

    def test_scripts_come_from_the_relic_installed_last(self):
        self.assertEqual(runner.entry("relic_run.py"), self.plugin / "scripts" / "relic_run.py")
        self.assertEqual(runner.entry("relic_dispatch.py"), self.plugin / "scripts" / "relic_dispatch.py")

    def test_this_copy_runs_when_nothing_usable_is_recorded(self):
        (self.plugin / "scripts" / "relic_dispatch.py").unlink()
        self.assertEqual(runner.entry("relic_dispatch.py"), self.own / "relic_dispatch.py")
        for broken in ("not json", json.dumps({"plugin": str(Path(self.tmp.name) / "gone")}), json.dumps({})):
            with self.subTest(broken=broken):
                self.record(broken)
                self.assertEqual(runner.entry("relic_run.py"), self.own / "relic_run.py")
        (runner.data_home() / runner.CURRENT).unlink()
        self.assertEqual(runner.entry("relic_run.py"), self.own / "relic_run.py")

    def test_a_test_run_without_a_data_root_of_its_own_never_reads_the_real_record(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("RELIC_HOME")
            self.assertIsNone(runner.installed_plugin())

    def test_member_turns_and_delayed_checks_start_the_installed_scripts(self):
        oid = self.store.create(LEAD, "Lab", "ship it", "lead")["id"]
        self.store.add_seat(oid, "cody", "ui", runner.default_config("codex"))
        self.store.join(CODY, oid, "cody")
        with mock.patch.object(runner.subprocess, "Popen") as popen:
            popen.return_value.pid = 4242
            runner.start_turn(oid, "cody", "hello")
        self.assertEqual(popen.call_args[0][0][3], str(self.plugin / "scripts" / "relic_run.py"))
        with mock.patch.object(wake.subprocess, "Popen") as popen:
            wake.schedule_retry(oid, 5)
            wake.schedule_drive(5)
        self.assertEqual([c[0][0][3] for c in popen.call_args_list],
                         [str(self.plugin / "scripts" / "relic_dispatch.py")] * 2)


class DesktopHandOver(Fixture):
    def setUp(self):
        super().setUp()
        self.oid = self.store.create(LEAD, "OrgBench", "build the bench", "lead")["id"]
        self.store.add_seat(self.oid, "bench", "builder",
                            dict(runner.default_config("claude-code"), surface="gui", model="sonnet"))
        self.store.join(BENCH, self.oid, "bench")
        self.store.add_seat(self.oid, "cody", "ui", runner.default_config("codex"))
        self.store.join(CODY, self.oid, "cody")
        self.message = self.store.send(LEAD, ["bench"], "T8 is in: take it from here")["message_id"]
        self.now = time.time() + 60  # past the settling time of the message
        self.started, self.arms = [], []

    def start(self, org_id, member, prompt, wake_from=None, wake_hop=0, wake_message_ids=None):
        self.started.append(member)
        runner.write_state(org_id, member, {"status": "running", "started": time.time(), "pid": os.getpid()})

    def failed(self, member="bench", error=OLD, gave_up=True):
        with self.store.change(self.oid) as (org, db):
            mine = org.setdefault("wake", {}).setdefault("members", {}).setdefault(member, {})
            if gave_up:
                mine.update(last_id=self.message, last_at=self.now - 600, failures=6, error=error,
                            retry_at=self.now - 900, gave_up_at=self.now - 600)
            else:  # a failure the old route will retry with back-off: its claim was given back
                mine.update(last_id=self.message - 1, last_at=self.now - 30, failures=2, error=error,
                            retry_at=self.now + 1800)

    def due(self, at):
        return wake.drive_due(self.store, at, start=self.start, age=lambda seat: None,
                              retry=lambda org_id, delay: None, arm=self.arms.append)

    def wake_state(self, member="bench"):
        return ((self.store.get(self.oid).get("wake") or {}).get("members") or {}).get(member, {})

    def test_a_wake_up_the_old_cli_route_gave_up_on_is_started_again(self):
        self.failed()
        self.due(self.now)
        self.assertEqual(self.started, ["bench"])
        mine = self.wake_state()
        for key in ("failures", "error", "retry_at", "gave_up_at"):
            self.assertNotIn(key, mine)
        self.assertEqual(mine["last_id"], self.message)  # claimed again by this wake-up
        handed = self.store.events(self.oid, ["member.wake_handed_over"])
        self.assertEqual([(e["member"], e["body"]["unread"]) for e in handed], [("bench", 1)])
        self.assertEqual(len(self.arms), 1)  # the background check comes back to keep looking
        self.assertAlmostEqual(self.arms[0], wake.HANDOVER_HEARTBEAT + 1, delta=2)

    def test_a_failure_still_in_back_off_is_started_now(self):
        self.failed(gave_up=False)
        self.due(self.now)
        self.assertEqual(self.started, ["bench"])
        self.assertNotIn("retry_at", self.wake_state())

    def test_only_desktop_seats_failed_by_the_old_route_are_handed_over(self):
        cases = {
            "this Relic's own failure": ("bench", "no live Claude Code session carries OrgBench · bench; the CLI "
                                                  "route: " + OLD),
            "another failure": ("bench", "Claude Desktop unavailable: the session is gone"),
            "not a Desktop seat": ("cody", OLD),
        }
        for label, (member, error) in cases.items():
            with self.subTest(label):
                self.failed(member, error)
                path = wake._handover_path()
                if path.exists():
                    path.unlink()
                self.due(self.now)
                self.assertEqual(self.started, [])
                self.assertEqual(self.wake_state(member).get("error"), error)
        self.assertEqual(self.store.events(self.oid, ["member.wake_handed_over"]), [])

    def test_a_seat_in_a_turn_is_left_to_its_turn(self):
        self.failed()
        runner.write_state(self.oid, "bench", {"status": "running", "started": time.time(), "pid": os.getpid()})
        self.due(self.now)
        self.assertEqual(self.store.events(self.oid, ["member.wake_handed_over"]), [])
        self.assertEqual(self.wake_state()["error"], OLD)

    def test_one_look_a_minute_and_a_background_look_while_failures_were_seen_lately(self):
        self.due(self.now)  # nothing to hand over: no background look is armed for it
        self.assertEqual(self.arms, [])
        self.failed()
        self.due(self.now + 30)  # within the minute: not looked at yet
        self.assertEqual(self.started, [])
        self.due(self.now + wake.HANDOVER_EVERY + 1)
        self.assertEqual(self.started, ["bench"])
        runner.write_state(self.oid, "bench", {"status": "done", "finished": time.time()})
        self.arms.clear()
        self.due(self.now + wake.HANDOVER_EVERY + wake.HANDOVER_WATCH - 600)
        self.assertEqual(len(self.arms), 1)
        self.arms.clear()
        self.due(self.now + wake.HANDOVER_EVERY + wake.HANDOVER_WATCH + 600)  # a quiet day: the looks stop
        self.assertEqual(self.arms, [])


class AnotherSeatReaches(Fixture):
    def setUp(self):
        super().setUp()
        s = self.store
        self.head = "dfd21864-0000-4000-8000-000000000002"
        self.cabinet = s.create("chief-h", "秘书处", "the secretariat", "chief")["id"]
        self.demo = s.create(self.head, "Relic 演示组", "demo", "lead")["id"]  # the session's main seat
        self.learning = s.create("coordinator-h", "Learning", "research", "coordinator")["id"]
        self.other = s.create("other-h", "Other", "unrelated", "o1")["id"]
        s.set_parent(self.demo, self.cabinet)
        s.set_parent(self.learning, self.cabinet)  # the demo's leader now also sits in the cabinet, ex officio
        self.assertEqual([(o["id"], m, main) for o, m, main in s.seats_of(self.head)],
                         [(self.demo, "lead", True), (self.cabinet, "lead", False)])

    def test_the_cabinet_seat_reaches_what_the_main_seat_cannot(self):
        own, member, target, way = self.store.reach(self.head, self.learning)
        self.assertEqual((own["id"], member, target["id"], way), (self.cabinet, "lead", self.learning, "down"))
        status = api.handle_call(self.store, "status", {"org": self.learning}, self.head)
        self.assertEqual(status["org_id"], self.learning)
        task = self.store.work(self.head, "task", {"org": self.learning, "title": "update the purpose",
                                                  "owner": "coordinator"})
        self.assertEqual(task["owner"], "coordinator")
        sent = self.store.send(self.head, ["coordinator"], "the model clause changed", org=self.learning)
        self.assertEqual(sent["org_id"], self.learning)
        unread = self.store.unread("coordinator-h", mark=False)
        self.assertEqual(unread[-1]["from"], "%s/lead" % self.cabinet)

    def test_the_main_seat_still_comes_first_and_a_scoped_call_stays_in_its_seat(self):
        sub = self.store.create("sub-h", "Demo part", "a part", "s1")["id"]
        self.store.set_parent(sub, self.demo)
        own, member, _, way = self.store.reach(self.head, sub)
        self.assertEqual((own["id"], member, way), (self.demo, "lead", "down"))
        with self.assertRaisesRegex(OrgError, "neither above nor below"):
            self.store.reach("%s#%s" % (self.head, self.demo), self.learning)
        with self.assertRaisesRegex(OrgError, "neither above nor below"):
            self.store.reach(self.head, self.other)

    def test_reporting_up_through_another_seat(self):
        outsider = "x-0000-4000-8000-000000000003"
        self.store.join(outsider, self.other, "o2")  # main seat in an unrelated organization
        self.store.join(outsider, self.learning, "helper")  # and a seat under the cabinet
        own, member, target, way = self.store.reach(outsider, self.cabinet, up=True)
        self.assertEqual((own["id"], member, target["id"], way), (self.learning, "helper", self.cabinet, "up"))
        with self.assertRaisesRegex(OrgError, "neither above nor below"):
            self.store.reach(outsider, self.cabinet)  # work in an organization above belongs to its members


if __name__ == "__main__":
    unittest.main()
