"""A background job a task waits on (work op=task job=<pid>) is work going on (research-head, 2026-11-16: keep-going
told 科研部 three times that nobody worked while the Glaze S model and its controller ran for hours).

While the job's process runs, keep-going holds the organization's next check until the job's horizon (so an older
Relic process cannot claim it meanwhile) and sends no notice; watch_jobs looks at the process and makes the check due
once it is gone; the end counts as progress and the next notice says the job ended. The end is also told to the task's
owner at once, in a message that wakes them (research-head, 2026-11-17: the OrgBench replay batch tells nobody when it
ends, and keep-going waits until the whole subtree is quiet). Processes are faked except where process_start itself is
tested."""
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

from relic_core import context, runner, wake  # noqa: E402
from relic_core.store import SYSTEM, OrgError, Store  # noqa: E402

LEAD, CODY, BOB = "lead-session", "codex:th-cody", "sess-bob"
JOB = 4242


class ProcessStart(unittest.TestCase):
    def test_a_running_process_and_its_start(self):
        alive, started = runner.process_start(os.getpid())
        self.assertTrue(alive)
        self.assertIsNotNone(started)
        self.assertLess(started, time.time() + 1)
        self.assertGreater(started, time.time() - 7 * 86400)

    def test_an_exited_process_and_no_process(self):
        done = subprocess.Popen([sys.executable, "-c", "pass"])
        done.wait()
        self.assertEqual(runner.process_start(done.pid), (False, None))
        for nothing in (0, -3, None, "x"):
            self.assertEqual(runner.process_start(nothing), (False, None))


class Jobs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        os.environ["RELIC_LANG"] = "en-US"
        s = self.store = Store()
        self.oid = s.create(LEAD, "Lab", "research", "lead")["id"]
        s.add_seat(self.oid, "cody", "head", runner.default_config("codex"))
        s.join(CODY, self.oid, "cody")
        self.child = s.found("Bench", "benchmarks")["id"]
        s.set_parent(self.child, self.oid)
        s.add_seat(self.child, "bob", "bench", runner.default_config("claude-code"))
        s.join(BOB, self.child, "bob")
        self.started, self.retries, self.armed = [], [], []
        self.processes = {JOB: 1000.0}  # pid -> start time of the processes that run
        fake = mock.patch.object(runner, "process_start", lambda pid: (
            (True, self.processes[pid]) if pid in self.processes else (False, None)))
        fake.start()
        self.addCleanup(fake.stop)
        self.settle, wake.SETTLE = wake.SETTLE, 0

    def tearDown(self):
        wake.SETTLE = self.settle
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def start(self, org_id, member, prompt, wake_from, wake_hop, wake_message_ids=None):
        self.started.append(member)
        runner.write_state(org_id, member, {"status": "running", "started": time.time(), "pid": os.getpid()})

    def check(self, at):
        return wake.drive_check(self.store, self.oid, now=at, age=lambda seat: None, start=self.start,
                                retry=lambda org_id, delay: self.retries.append(delay))

    def due(self, at):
        return wake.drive_due(self.store, at, start=self.start, age=lambda seat: None,
                              retry=lambda org_id, delay: self.retries.append(delay), arm=self.armed.append)

    def notices(self):
        """The keep-going notices (the plugin's other messages left out)."""
        with self.store.db() as db:
            return [r[0] for r in db.execute("SELECT body FROM messages WHERE sender=? AND body LIKE ? ORDER BY id",
                                             (SYSTEM, "[Relic keep-going]%"))]

    def told(self):
        """[(recipients, body)] of the plugin's messages saying that a task's background job ended."""
        with self.store.db() as db:
            return [(json.loads(r[0]), r[1]) for r in db.execute(
                "SELECT recipients, body FROM messages WHERE sender=? AND body LIKE ? ORDER BY id",
                (SYSTEM, "[Relic background job]%"))]

    def task_with_job(self, pid=JOB, **extra):
        task = self.store.work(BOB, "task", dict({"title": "Glaze S formal run", "status": "working"}, **extra))
        return self.store.work(BOB, "task", {"task_id": task["id"], "job": pid})

    def job(self, task_id="T1"):
        return self.store.get(self.child)["tasks"][task_id].get("job")

    # ------------------------------------------------------------------ attaching a job
    def test_a_task_names_the_running_process_it_waits_on(self):
        task = self.task_with_job()
        self.assertEqual({k: task["job"][k] for k in ("pid", "started", "by")}, {"pid": JOB, "started": 1000.0,
                                                                                "by": "bob"})
        self.assertEqual(self.store.events(self.child, ["task.job"])[-1]["body"], {"id": "T1", "pid": JOB})
        self.assertIn("waits on its background job, process %d" % JOB, context.task_state(task))
        with self.assertRaisesRegex(OrgError, "No process 77 runs"):
            self.store.work(BOB, "task", {"task_id": "T1", "job": 77})
        for wrong in (True, "abc", [1]):
            with self.assertRaisesRegex(OrgError, "process id"):
                self.store.work(BOB, "task", {"task_id": "T1", "job": wrong})
        self.assertNotIn("job", self.store.work(BOB, "task", {"task_id": "T1", "job": 0}))  # 0 detaches it
        done = self.store.work(BOB, "task", {"title": "finished", "status": "done", "evidence": ["x"],
                                             "report": "done"})
        with self.assertRaisesRegex(OrgError, "unfinished task"):
            self.store.work(BOB, "task", {"task_id": done["id"], "job": JOB})

    def test_a_member_above_can_attach_it(self):
        self.store.work(BOB, "task", {"title": "Glaze S formal run", "status": "working"})
        task = self.store.work(CODY, "task", {"org": self.child, "task_id": "T1", "job": JOB})
        self.assertEqual((task["job"]["pid"], task["job"]["by"]), (JOB, "%s/cody" % self.oid))

    # ------------------------------------------------------------------ keep-going while it runs
    def test_a_running_job_holds_keep_going_without_a_notice(self):
        self.store.set_drive(self.oid, True, goal="go on", driver="cody")
        self.task_with_job()
        attached = wake._epoch(self.job()["at"])
        at = int(time.time()) + 3600
        outcome = self.check(at)
        self.assertEqual(outcome["state"], "busy")
        self.assertIn("process %d" % JOB, outcome["why"])
        self.assertEqual(outcome["next"], attached + wake.JOB_HORIZON)  # an older Relic cannot claim it meanwhile
        self.assertEqual(self.store.drive_checks()[self.oid], attached + wake.JOB_HORIZON)
        self.assertEqual(self.store.get(self.oid)["drive"]["held"], ["%s/T1" % self.child])
        self.assertEqual((self.notices(), self.started), ([], []))

    def test_its_end_makes_the_check_due_and_the_notice_says_so(self):
        self.store.set_drive(self.oid, True, goal="go on", driver="cody")
        self.task_with_job()
        at = int(time.time()) + 3600
        self.assertEqual(self.check(at)["state"], "busy")
        self.assertEqual(wake.watch_jobs(self.store, at + 300), at + 300 + wake.JOB_LOOK)  # still runs
        self.assertEqual(wake.watch_jobs(self.store, at + 330), at + 300 + wake.JOB_LOOK)  # one look a minute
        del self.processes[JOB]  # the controller exits
        end = at + 600
        self.assertIsNone(wake.watch_jobs(self.store, end))
        self.assertEqual(self.store.drive_checks()[self.oid], end)  # due now
        self.assertNotIn("held", self.store.get(self.oid)["drive"])
        self.assertEqual(self.job()["ended_at"], wake.iso(end))
        self.assertIn("ended by", context.task_state(self.store.get(self.child)["tasks"]["T1"]))
        outcome = self.check(end)
        self.assertEqual((outcome["state"], outcome["next"]), ("wait", end + wake.DRIVE_QUIET))
        self.assertEqual(self.check(end + wake.DRIVE_QUIET + 5)["state"], "nudged")
        [body] = self.notices()
        self.assertIn("Background jobs that ended:", body)
        self.assertIn("Bench T1 Glaze S formal run: its background job (process %d) was found ended at %s" % (
            JOB, wake.iso(end)), body)
        self.assertEqual(self.started, ["cody"])
        self.assertEqual([to for to, _ in self.told()], [["bob"]])  # the owner heard of it when it was found

    def test_its_end_is_progress_after_an_earlier_notice(self):
        self.store.set_drive(self.oid, True, goal="go on", driver="cody")
        first = int(time.time()) + 3600
        self.assertEqual(self.check(first)["state"], "nudged")  # nobody worked: the driver was told
        runner.write_state(self.oid, "cody", {"status": "done", "started": time.time()})  # its turn ended
        wake.finish(self.store, self.oid, "cody")
        self.store.work(BOB, "task", {"title": "Glaze S formal run", "status": "working"})
        with self.store.change(self.child) as (org, db):  # attached before the notice, so no message moved since
            org["tasks"]["T1"]["job"] = {"pid": JOB, "started": 1000.0, "by": "bob", "at": wake.iso(first - 60)}
        self.assertEqual(self.check(first + 1800)["state"], "busy")
        del self.processes[JOB]
        end = first + 7200
        self.assertIsNone(wake.watch_jobs(self.store, end))
        self.assertEqual(self.check(end)["state"], "wait")
        self.assertEqual(self.check(end + wake.DRIVE_QUIET + 5)["state"], "nudged")  # not "idle"
        self.assertEqual(len(self.notices()), 2)
        self.assertIn("process %d" % JOB, self.notices()[1])

    def test_a_later_process_with_the_same_id_is_not_the_job(self):
        self.store.set_drive(self.oid, True, goal="go on", driver="cody")
        self.task_with_job()
        self.processes[JOB] = 5000.0  # the controller exited and another process got its id
        at = int(time.time()) + 3600
        self.assertEqual(self.check(at)["state"], "wait")
        self.assertEqual(self.job()["ended_at"], wake.iso(at))
        self.assertFalse(wake.job_runs({"pid": JOB, "started": 1000.0}))
        self.assertTrue(wake.job_runs({"pid": JOB, "started": 5000.5}))
        self.assertTrue(wake.job_runs({"pid": JOB, "started": None}))  # a start Windows would not let us read

    def test_no_hold_past_the_horizon_or_on_a_finished_task(self):
        self.store.set_drive(self.oid, True, goal="go on", driver="cody")
        self.task_with_job()
        attached = wake._epoch(self.job()["at"])
        self.assertEqual(self.check(attached + wake.JOB_HORIZON + 10)["state"], "nudged")  # a job that never ends
        self.assertEqual(self.job().get("ended_at"), None)  # it was not seen to end
        self.store.work(BOB, "task", {"task_id": "T1", "status": "dropped"})
        self.assertEqual(wake._running_jobs(self.store, [self.store.get(self.child)], time.time()), [])

    def test_drive_due_keeps_looking_while_a_job_holds(self):
        self.store.set_drive(self.oid, True, goal="go on", driver="cody")
        self.task_with_job()
        at = int(time.time()) + 3600
        [(org_id, outcome)] = self.due(at)
        self.assertEqual((org_id, outcome["state"], outcome["held"]), (self.oid, "busy", 1))
        self.assertEqual(self.armed[-1], wake.JOB_LOOK + 1)  # the jobs are looked at again soon, not at the horizon
        later = at + wake.JOB_LOOK + 1
        self.assertEqual(self.due(later), [])  # nothing due: the check is held
        self.assertEqual(json.loads(wake._jobs_look_path().read_text())["next"], later + wake.JOB_LOOK)
        del self.processes[JOB]
        gone = later + wake.JOB_LOOK + 1
        [(org_id, outcome)] = self.due(gone)  # the look makes the check due, and the same pass runs it
        self.assertEqual((outcome["state"], outcome["next"]), ("wait", gone + wake.DRIVE_QUIET))
        self.assertEqual(self.notices(), [])

    # ------------------------------------------------------------------ telling the task's owner
    def test_its_end_is_told_to_the_task_owner_once_and_wakes_them(self):
        self.store.set_drive(self.oid, True, goal="go on", driver="cody")
        self.task_with_job()  # bob owns Bench T1
        at = int(time.time()) + 3600
        self.assertEqual(self.due(at)[0][1]["state"], "busy")
        self.assertEqual((self.told(), self.started), ([], []))  # nothing while it runs
        del self.processes[JOB]  # the batch exits and tells nobody itself
        gone = at + wake.JOB_LOOK + 1
        [(org_id, outcome)] = self.due(gone)
        self.assertEqual(outcome["state"], "wait")  # keep-going would wait for 10 quiet minutes
        [(to, body)] = self.told()
        self.assertEqual(to, ["bob"])
        self.assertIn("Bench T1 Glaze S formal run: its background job (process %d) was found ended at %s" % (
            JOB, wake.iso(gone)), body)
        self.assertEqual(self.started, ["bob"])  # the message wakes the owner at once
        self.assertEqual(self.notices(), [])
        self.check(gone + 120)  # later checks and looks do not tell it again
        self.due(gone + wake.JOB_LOOK + 1)
        self.assertEqual(len(self.told()), 1)

    def test_an_end_an_older_relic_recorded_is_told_by_the_next_check(self):
        self.store.set_drive(self.oid, True, goal="go on", driver="cody")
        self.task_with_job()
        at = int(time.time()) + 3600
        with self.store.change(self.child) as (org, db):  # an older Relic saw it end and told nobody
            org["tasks"]["T1"]["job"]["ended_at"] = wake.iso(at)
        del self.processes[JOB]
        self.assertEqual(self.check(at + 60)["state"], "wait")
        [(to, body)] = self.told()
        self.assertEqual(to, ["bob"])
        self.assertIn("was found ended at %s" % wake.iso(at), body)
        self.check(at + 120)
        self.assertEqual(len(self.told()), 1)
        with self.store.change(self.child) as (org, db):  # an end from long ago is not told
            org["tasks"]["T1"]["job"] = {"pid": JOB, "started": 1000.0, "by": "bob", "at": wake.iso(at - 2 * 86400),
                                         "ended_at": wake.iso(at - 2 * 86400 + 60)}
        self.check(at + 180)
        self.assertEqual(len(self.told()), 1)

    def test_with_no_seated_owner_its_leaders_are_told(self):
        self.store.set_drive(self.oid, True, goal="go on", driver="cody")
        task = self.store.work(CODY, "task", {"title": "Glaze T replay", "status": "working"})
        self.store.work(CODY, "task", {"task_id": task["id"], "job": JOB})
        with self.store.change(self.oid) as (org, db):
            org["tasks"][task["id"]]["owner"] = "someone-who-left"
        del self.processes[JOB]
        self.assertEqual(self.check(int(time.time()) + 3600)["state"], "wait")
        [(to, body)] = self.told()
        self.assertEqual(to, ["lead"])
        self.assertIn("Lab %s Glaze T replay: its background job (process %d)" % (task["id"], JOB), body)
        self.assertEqual(self.started, [])  # a check outside drive_due leaves the waking to drive_due


if __name__ == "__main__":
    unittest.main()
