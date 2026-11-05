"""The overview the Relic App opens from its toolbar: every organization in tree order with what it is doing, its open
tasks, each member's state and what can start it on its own, and the switches the person flips from there.
Synthetic stores, transcripts, automations and Claude app records in temporary folders; nothing is started."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import overview  # noqa: E402
from relic_core import monitor, runner, usage  # noqa: E402
from relic_core.store import Store  # noqa: E402

SESSION = "11111111-2222-4333-8444-555555555555"
THREAD = "01a19e4b-4e41-71d1-8a76-144ee2980f44"
CLI = {"harness": "claude-code", "surface": "cli"}
AUTOMATION = """version = 1
id = "%s"
kind = "heartbeat"
name = "%s"
status = "%s"
rrule = "%s"
target_thread_id = "%s"
created_at = 1793137492442
updated_at = 1793137492442
"""


def claude_usage(mid, at):
    stamp = datetime.fromtimestamp(at, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return json.dumps({"type": "assistant", "timestamp": stamp, "requestId": "req_" + mid, "message": {
        "id": mid, "model": "claude-test", "usage": {"input_tokens": 10, "cache_read_input_tokens": 100,
                                                       "cache_creation_input_tokens": 5, "output_tokens": 7}}})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        env = {"RELIC_HOME": str(root / "relic"), "CLAUDE_CONFIG_DIR": str(root / "claude"), "CODEX_HOME": str(root / "codex"),
               "LOCALAPPDATA": str(root / "local"), "APPDATA": str(root / "roaming"), "HOME": str(root / "home"),
               "USERPROFILE": str(root / "home")}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)
        usage.Ledger._shared = None
        fresh = mock.patch.object(monitor, "FRESH_FOR", 0)
        fresh.start()
        self.addCleanup(fresh.stop)
        self.root = root
        self.store = Store()
        # 秘书处 (cabinet) > 研发部 > 工具组; head of 研发部 also sits in 秘书处
        self.cabinet = self.store.create("chief", "秘书处", "coordinate", "chief")["id"]
        self.store.set_cabinet(self.cabinet)
        self.dept = self.store.create(SESSION, "研发部", "build Relic", "head")["id"]
        self.store.set_parent(self.dept, self.cabinet)
        self.store.add_seat(self.cabinet, "head")
        self.store.join(SESSION, self.cabinet, "head")
        self.team = self.store.create("codex:" + THREAD, "工具组", "tools", "builder")["id"]
        self.store.set_parent(self.team, self.dept)
        self.project = root / "claude" / "projects" / "C--work"
        self.project.mkdir(parents=True)

    def org(self, data, org_id):
        return next(o for o in data["orgs"] if o["id"] == org_id)

    def member(self, data, org_id, name):
        return next(m for m in self.org(data, org_id)["members"] if m["name"] == name)

    def working(self, session=SESSION):
        with open(self.project / ("%s.jsonl" % session), "a", encoding="utf-8") as f:
            f.write(claude_usage("m%d" % time.time_ns(), time.time() - 5) + "\n")

    def automation(self, aid, name, status="ACTIVE", rrule="FREQ=HOURLY;INTERVAL=2", target=THREAD):
        folder = self.root / "codex" / "automations" / aid
        folder.mkdir(parents=True)
        path = folder / "automation.toml"
        path.write_text(AUTOMATION % (aid, name, status, rrule, target), encoding="utf-8")
        return path

    def task(self, org_id, tid, title, owner, status):
        with self.store.change(org_id) as (org, db):
            org["tasks"][tid] = {"id": tid, "title": title, "owner": owner, "status": status, "at": "2026-11-05T10:00:00Z"}


class Tree(Base):
    def test_the_cabinet_comes_first_and_each_organization_follows_its_parent(self):
        lone = self.store.create("someone", "独立组", "alone", "solo")["id"]
        data = overview.overview(self.store)
        self.assertEqual([(o["name"], o["depth"]) for o in data["orgs"]],
                         [("秘书处", 0), ("研发部", 1), ("工具组", 2), ("独立组", 0)])
        self.assertTrue(self.org(data, self.cabinet)["cabinet"])
        self.assertEqual(self.org(data, lone)["parent"], None)
        self.assertEqual(data["totals"]["orgs"], 4)

    def test_open_tasks_in_progress_first_and_done_ones_counted(self):
        self.task(self.dept, "T1", "write tests", "head", "open")
        self.task(self.dept, "T2", "fix the hook", "head", "blocked")
        self.task(self.dept, "T3", "ship the panel", "head", "working")
        self.task(self.dept, "T4", "old work", "head", "done")
        self.task(self.dept, "T5", "abandoned", "head", "dropped")
        dept = self.org(overview.overview(self.store), self.dept)
        self.assertEqual([t["id"] for t in dept["tasks"]], ["T3", "T2", "T1"])
        self.assertEqual((dept["done"], dept["counts"]["open_tasks"]), (1, 3))

    def test_latest_message_skips_receipts_and_updates_as_rows_arrive(self):
        self.store.send("chief", ["head"], "please review the overview")
        self.store.send("chief", ["head"], "[Relic auto-receipt] head received message 1")
        cabinet = self.org(overview.overview(self.store), self.cabinet)
        self.assertEqual(cabinet["latest_message"]["body"], "please review the overview")
        self.assertEqual(cabinet["latest_message"]["from"], "chief")
        self.store.send(SESSION + "#" + self.cabinet, ["chief"], "done, it is in the toolbar")
        self.store.record_activity(SESSION + "#" + self.cabinet, "Bash", {"command": "python -m pytest"})
        cabinet = self.org(overview.overview(self.store), self.cabinet)
        self.assertEqual((cabinet["latest_message"]["from"], cabinet["latest_message"]["body"]),
                         ("head", "done, it is in the toolbar"))
        self.assertEqual((cabinet["latest_action"]["member"], cabinet["latest_action"]["summary"]),
                         ("head", "python -m pytest"))
        self.assertIsNone(self.org(overview.overview(self.store), self.team)["latest_message"])

    def test_one_read_of_the_organizations_and_nothing_read_per_member(self):
        for index in range(30):
            self.store.add_seat(self.dept, "m%02d" % index, config=dict(CLI))
        with mock.patch.object(self.store, "list_orgs", wraps=self.store.list_orgs) as orgs, \
                mock.patch.object(self.store, "get", wraps=self.store.get) as get, \
                mock.patch.object(self.store, "seats_of", wraps=self.store.seats_of) as seats:
            data = overview.overview(self.store)
        self.assertEqual(orgs.call_count, 1)
        self.assertEqual((get.call_count, seats.call_count), (0, 0))
        self.assertEqual(self.org(data, self.dept)["counts"]["members"], 32)  # head, builder ex officio, 30 seats


class Members(Base):
    def test_idle_vacant_and_who_leads(self):
        self.store.add_seat(self.dept, "reviewer", role="review")
        dept = self.org(overview.overview(self.store), self.dept)
        # the leader first; the leader of 工具组 sits here ex officio; a seat without a session last
        self.assertEqual([(m["name"], m["leader"], m["state"]) for m in dept["members"]],
                         [("head", True, "idle"), ("builder", False, "idle"), ("reviewer", False, "vacant")])
        reviewer = dept["members"][2]
        self.assertEqual((reviewer["wake"], reviewer["can_stop"], reviewer["session"]), ("vacant", False, ""))

    def test_a_working_session_works_where_it_last_acted_and_its_other_seat_says_where(self):
        self.working()
        self.store.record_activity(SESSION + "#" + self.cabinet, "Bash", {"command": "ls"})
        data = overview.overview(self.store)
        self.assertEqual(self.member(data, self.cabinet, "head")["state"], "working")
        elsewhere = self.member(data, self.dept, "head")
        self.assertEqual(elsewhere["state"], "elsewhere")
        self.assertEqual(elsewhere["working_in"], {"org": self.cabinet, "org_name": "秘书处", "member": "head"})
        self.assertEqual(data["totals"]["working"], 1)  # one session, counted once
        self.assertEqual(self.org(data, self.dept)["counts"]["elsewhere"], 1)
        # the organization the session works for now (focus) decides over its latest tool call
        self.store.set_focus(SESSION, self.dept)
        data = overview.overview(self.store)
        self.assertEqual((self.member(data, self.dept, "head")["state"], self.member(data, self.cabinet, "head")["state"]),
                         ("working", "elsewhere"))

    def test_a_running_relic_runner_marks_its_own_seat(self):
        runner.runs_dir().mkdir(parents=True, exist_ok=True)
        runner.write_state(self.team, "builder", {"status": "running", "pid": os.getpid(), "started": time.time()})
        self.assertEqual(self.member(overview.overview(self.store), self.team, "builder")["state"], "working")

    def test_stop_and_resume_show_on_every_seat_of_the_session(self):
        monitor.stop(self.store, SESSION)
        data = overview.overview(self.store)
        for org_id in (self.dept, self.cabinet):
            head = self.member(data, org_id, "head")
            self.assertEqual((head["state"], head["stopped"], head["wake"]), ("stopped", True, "off"))
        self.assertEqual(data["totals"]["stopped"], 1)
        monitor.resume(self.store, SESSION)
        head = self.member(overview.overview(self.store), self.dept, "head")
        self.assertEqual((head["state"], head["stopped"]), ("idle", False))

    def test_what_wakes_a_seat(self):
        self.store.set_config(self.dept, "head", dict(CLI))
        data = overview.overview(self.store)
        self.assertEqual(self.member(data, self.dept, "head")["wake"], "on")
        # the cabinet seat has no config of its own: it starts its turns like the seat its session holds elsewhere
        self.assertEqual(self.member(data, self.cabinet, "head")["wake"], "on")
        self.assertEqual(self.member(data, self.cabinet, "chief")["wake"], "cannot")  # no session registered
        self.assertFalse(self.member(data, self.cabinet, "chief")["starts_itself"])
        self.store.set_auto_wake(self.dept, False)
        self.store.set_seat_auto_wake(self.cabinet, "head", False)
        data = overview.overview(self.store)
        self.assertEqual(self.member(data, self.dept, "head")["wake"], "org_off")
        self.assertEqual(self.member(data, self.cabinet, "head")["wake"], "off")
        self.assertFalse(self.org(data, self.dept)["starts_itself"])
        self.assertEqual(data["totals"]["orgs_auto_wake"], 2)


class Schedules(Base):
    def test_codex_automations_hang_under_the_member_they_start_and_the_rest_stand_apart(self):
        self.automation("watch", "Watch the build")
        self.automation("digest", "Morning digest", status="PAUSED", rrule="FREQ=DAILY;BYHOUR=9;BYMINUTE=0",
                        target="01a1ffff-0000-7000-8000-000000000000")
        data = overview.overview(self.store, lang="en-US")
        builder = self.member(data, self.team, "builder")
        self.assertEqual([(a["id"], a["status"], a["schedule"]) for a in builder["automations"]],
                         [("watch", "ACTIVE", "every 2 hours")])
        self.assertTrue(builder["starts_itself"])
        self.assertEqual(self.org(data, self.team)["counts"]["automations_on"], 1)
        self.assertEqual([(a["id"], a["schedule"]) for a in data["automations"]], [("digest", "every day at 09:00")])
        self.assertEqual((data["totals"]["automations"], data["totals"]["automations_on"]), (2, 1))

    def test_pausing_one_automation(self):
        path = self.automation("watch", "Watch the build")
        self.assertEqual(monitor.set_automation("watch", "PAUSED"), {"id": "watch", "status": "PAUSED", "before": "ACTIVE"})
        self.assertIn('status = "PAUSED"', path.read_text(encoding="utf-8"))
        self.assertFalse(self.member(overview.overview(self.store), self.team, "builder")["starts_itself"])
        monitor.set_automation("watch", "ACTIVE")
        self.assertIn('status = "ACTIVE"', path.read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
            monitor.set_automation("watch", "OFF")
        with self.assertRaises(ValueError):
            monitor.set_automation("nobody", "PAUSED")

    def test_claude_app_tasks_with_their_switch_and_time_from_the_app_record(self):
        for name, text in (("daily-check", "Check the night's runs"), ("one-off", "Resume the build")):
            folder = self.root / "claude" / "scheduled-tasks" / name
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text("---\nname: %s\ndescription: %s\n---\n\nDo it." % (name, text), encoding="utf-8")
        record = self.root / "local" / "Claude-Data" / "claude_x" / "claude-code-sessions" / "acct" / "org"
        record.mkdir(parents=True)
        (record / "scheduled-tasks.json").write_text(json.dumps({"scheduledTasks": [
            {"id": "daily-check", "displayName": "每天检查", "cronExpression": "30 8 * * 1-5", "enabled": True,
             "cwd": "S:\\work"}]}), encoding="utf-8")
        data = overview.overview(self.store, lang="zh-CN")
        tasks = {task["id"]: task for task in data["claude_tasks"]}
        self.assertEqual((tasks["daily-check"]["name"], tasks["daily-check"]["enabled"], tasks["daily-check"]["schedule"]),
                         ("每天检查", True, "工作日 08:30"))
        self.assertEqual((tasks["one-off"]["name"], tasks["one-off"]["enabled"], tasks["one-off"]["schedule"]),
                         ("one-off", None, ""))
        self.assertEqual((data["totals"]["claude_tasks"], data["totals"]["claude_tasks_on"]), (2, 1))

    def test_schedules_in_the_persons_words(self):
        cases = [("FREQ=MINUTELY;INTERVAL=10", "every 10 minutes", "每 10 分钟"),
                 ("FREQ=HOURLY;INTERVAL=1", "every hour", "每 1 小时"),
                 ("FREQ=WEEKLY;BYDAY=MO,WE;BYHOUR=7;BYMINUTE=5", "every Monday and Wednesday at 07:05", "每周一、三 07:05"),
                 ("FREQ=YEARLY", "FREQ=YEARLY", "FREQ=YEARLY")]
        for rule, en, zh in cases:
            self.assertEqual((overview.rrule_text(rule, "en-US"), overview.rrule_text(rule, "zh-CN")), (en, zh))
        crons = [("*/15 * * * *", "every 15 minutes"), ("0 */3 * * *", "every 3 hours"), ("20 * * * *", "every hour at :20"),
                 ("0 9 * * *", "every day at 09:00"), ("0 9 * * 1-5", "weekdays at 09:00"),
                 ("0 18 * * 0", "every Sunday at 18:00"), ("0 9 1 * *", "0 9 1 * *")]
        for expression, words in crons:
            self.assertEqual(overview.cron_text(expression, "en-US"), words)
        self.assertTrue(overview.once_text(time.mktime((2026, 11, 4, 0, 55, 0, 0, 0, -1)), "zh-CN").endswith("11/4 00:55"))


class Api(Base):
    def setUp(self):
        super().setUp()
        from app import web
        self.app, self.server = web.serve(0, store=self.store, write_info=False)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.app.port

    def tearDown(self):
        self.app.stopping.set()
        self.app.hub.shutdown()
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def call(self, path, body=None, token=True):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Relic-Token"] = self.app.token
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(request, timeout=20) as reply:
                return reply.status, json.loads(reply.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read().decode("utf-8"))

    def test_the_overview_and_its_switches_through_the_app(self):
        path = self.automation("watch", "Watch the build")
        self.working()
        self.assertEqual(self.call("/api/overview", token=False)[0], 403)
        code, data = self.call("/api/overview")
        self.assertEqual(code, 200)
        self.assertEqual([o["id"] for o in data["orgs"]], [self.cabinet, self.dept, self.team])
        self.assertEqual(self.member(data, self.dept, "head")["session"], SESSION)

        self.assertEqual(self.call("/api/org/%s/seat_auto_wake" % self.dept, {"member": "head", "on": False})[0], 200)
        self.assertFalse(self.store.get(self.dept)["members"]["head"]["auto_wake"])
        self.assertEqual(self.member(self.call("/api/overview")[1], self.dept, "head")["wake"], "off")
        self.assertEqual(self.call("/api/org/%s/seat_auto_wake" % self.dept, {"member": "nobody", "on": True})[0], 400)
        self.call("/api/org/%s/seat_auto_wake" % self.dept, {"member": "head", "on": True})
        self.assertTrue(self.store.get(self.dept)["members"]["head"]["auto_wake"])

        code, done = self.call("/api/monitor/automation", {"id": "watch", "status": "PAUSED"})
        self.assertEqual((code, done["before"]), (200, "ACTIVE"))
        self.assertIn('status = "PAUSED"', path.read_text(encoding="utf-8"))
        self.assertEqual(self.call("/api/monitor/automation", {"id": "watch", "status": "OFF"})[0], 400)
        self.assertEqual(self.call("/api/monitor/automation", {"id": "watch", "status": "ACTIVE"})[0], 200)
        self.assertIn('status = "ACTIVE"', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
