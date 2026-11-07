"""The person's monitor: who is working on this machine, the tokens each session used (from its own records), and the
Stop that ends a session's turn and turns off what would start it again, with Resume undoing exactly that, and the
person's next message turning the wake-ups (not the timers) back on.
Synthetic transcripts, automations and stores in temporary folders; no model, CLI or process is started."""
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
sys.path.insert(0, str(ROOT / "hooks"))
from relic_core import monitor, runner, usage, wake  # noqa: E402
from app import overview, views  # noqa: E402
from relic_core.store import Store  # noqa: E402
import relic_hook  # noqa: E402

SESSION = "11111111-2222-4333-8444-555555555555"
OTHER = "99999999-2222-4333-8444-555555555555"
THREAD = "01a19e4b-4e41-71d1-8a76-144ee2980f44"


def iso(at):
    return datetime.fromtimestamp(at, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def claude_usage(mid, at, fresh=10, read=100, write=5, out=7):
    return json.dumps({"type": "assistant", "timestamp": iso(at), "requestId": "req_" + mid, "message": {
        "id": mid, "model": "claude-test", "usage": {"input_tokens": fresh, "cache_read_input_tokens": read,
                                                       "cache_creation_input_tokens": write, "output_tokens": out}}})


def codex_count(at, sent, cached, out, total, limits=None):
    return json.dumps({"timestamp": iso(at), "type": "event_msg", "payload": {
        "type": "token_count", "info": {"last_token_usage": {"input_tokens": sent, "cached_input_tokens": cached,
                                                             "output_tokens": out}, "total_token_usage": {"total_tokens": total}},
        "rate_limits": limits}})


AUTOMATION = """version = 1\r
id = "watch"\r
kind = "heartbeat"\r
name = "Watch the build"\r
status = "ACTIVE"\r
rrule = "FREQ=HOURLY;INTERVAL=2"\r
target_thread_id = "%s"\r
created_at = 1793137492442\r
updated_at = 1793137492442\r
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"RELIC_HOME": str(root / "relic"), "CLAUDE_CONFIG_DIR": str(root / "claude"),
                                                "CODEX_HOME": str(root / "codex")})
        self.env.start()
        os.environ.pop("PLUGIN_ROOT", None)
        os.environ.pop("RELIC_HARNESS", None)
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)
        usage.Ledger._shared = None
        fresh = mock.patch.object(monitor, "FRESH_FOR", 0)  # every view reads what the test just wrote
        fresh.start()
        self.addCleanup(fresh.stop)
        self.root = root
        self.now = time.time()
        self.store = Store()
        self.org = self.store.create(SESSION, "研发部", "kernel", "head")["id"]
        self.cabinet = self.store.create("chief", "秘书处", "cabinet", "chief")["id"]
        self.store.add_seat(self.cabinet, "head")
        self.store.join(SESSION, self.cabinet, "head")
        self.project = root / "claude" / "projects" / "C--work"
        self.project.mkdir(parents=True)

    def transcript(self, session=SESSION, lines=(), sub=None):
        path = (self.project / session / "subagents" / ("agent-%s.jsonl" % sub)) if sub else (self.project / ("%s.jsonl" % session))
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
        return path

    def rollout(self, lines):
        day = time.localtime(self.now)
        folder = self.root / "codex" / "sessions" / ("%04d" % day.tm_year) / ("%02d" % day.tm_mon) / ("%02d" % day.tm_mday)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ("rollout-2026-11-02T16-04-58-%s.jsonl" % THREAD)
        with open(path, "a", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
        return path

    def automation(self):
        folder = self.root / "codex" / "automations" / "watch"
        folder.mkdir(parents=True)
        path = folder / "automation.toml"
        path.write_bytes((AUTOMATION % THREAD).encode("utf-8"))
        return path

    def agent(self, snap, key):
        return next(a for a in snap["agents"] + snap["others"] if a["key"] == key)

    def hook(self, name, session=SESSION, **fields):
        event = dict(hook_event_name=name, session_id=session, **fields)
        with mock.patch.object(wake, "dispatch_for_actor"):
            return relic_hook.handle(event, self.store)


class Usage(Base):
    def test_a_message_logged_once_per_content_block_counts_once_and_subagents_count_with_their_session(self):
        at = self.now - 600
        self.transcript(lines=[claude_usage("m1", at)] * 3 + [claude_usage("m2", at + 1, fresh=1, read=0, write=0, out=1)])
        self.transcript(lines=[claude_usage("s1", at, fresh=4, read=0, write=0, out=6)], sub="abc")
        (self.project / SESSION / "custom-title.json").write_text(json.dumps({"customTitle": "接手修 App"}), encoding="utf-8")
        agent = self.agent(monitor.snapshot(self.store, self.now), SESSION)
        self.assertEqual(agent["tokens"]["hour"], {"total": 122 + 2 + 10, "fresh": 15, "cache_read": 100, "cache_write": 5,
                                                   "output": 14})
        self.assertEqual(agent["title"], "接手修 App")
        self.assertEqual([s["member"] for s in agent["seats"]], ["head", "head"])
        self.assertEqual(agent["subagents"], 1)
        self.assertTrue(agent["working"])
        self.assertEqual(agent["reason"], "active")

    def test_reading_is_incremental_and_an_unfinished_line_waits(self):
        path = self.transcript(lines=[claude_usage("m1", self.now - 60)])
        with open(path, "a", encoding="utf-8") as f:
            f.write(claude_usage("m2", self.now - 30)[:40])  # the session is still writing this line
        first = self.agent(monitor.snapshot(self.store, self.now), SESSION)["tokens"]["hour"]["total"]
        self.assertEqual(first, 122)
        with open(path, "a", encoding="utf-8") as f:
            f.write(claude_usage("m2", self.now - 30)[40:] + "\n" + claude_usage("m3", self.now - 20) + "\n")
        second = self.agent(monitor.snapshot(self.store, self.now), SESSION)["tokens"]["hour"]["total"]
        self.assertEqual(second, 3 * 122)

    def test_windows_and_idle_sessions(self):
        path = self.transcript(session=OTHER, lines=[claude_usage("old", self.now - 3 * 3600), claude_usage("new", self.now - 120)])
        os.utime(path, (self.now - 1800, self.now - 1800))
        snap = monitor.snapshot(self.store, self.now)
        other = self.agent(snap, OTHER)
        self.assertIn(other, snap["others"])  # no Relic seat
        self.assertFalse(other["working"])
        self.assertEqual((other["tokens"]["hour"]["total"], other["tokens"]["five_hours"]["total"]), (122, 244))
        self.assertEqual(snap["totals"]["claude"]["five_hours"], 244)

    def test_codex_sessions_count_fresh_and_cached_input_and_report_the_plan(self):
        limits = {"primary": {"used_percent": 38.0, "window_minutes": 10080, "resets_at": 1794199750}, "plan_type": "pro"}
        self.rollout([json.dumps({"timestamp": iso(self.now - 900), "type": "session_meta", "payload": {"id": THREAD, "cwd": "S:/work/mod"}}),
                      codex_count(self.now - 600, 1000, 900, 50, 1050, limits),
                      codex_count(self.now - 599, 1000, 900, 50, 1050, limits),  # the same count again
                      codex_count(self.now - 300, 2000, 1500, 20, 3070)])
        snap = monitor.snapshot(self.store, self.now)
        agent = self.agent(snap, "codex:" + THREAD)
        self.assertEqual(agent["tokens"]["hour"], {"total": 3070, "fresh": 600, "cache_read": 2400, "cache_write": 0, "output": 70})
        self.assertEqual(agent["title"], "mod")
        self.assertEqual(snap["plans"]["codex"]["primary"]["used_percent"], 38.0)
        self.assertEqual(snap["totals"]["codex"]["hour"], 3070)


class Statistics(Base):
    OLD = "77777777-2222-4333-8444-555555555555"

    def setUp(self):
        super().setUp()
        with self.store.change(self.org) as (org, db):  # the seat was carried by an earlier session before this one
            org["members"]["head"].setdefault("past_carriers", []).append(self.OLD)
        self.transcript(session=self.OLD, lines=[claude_usage("o1", self.now - 2 * 86400 - 60, fresh=1000, read=0, write=0, out=0)])
        self.transcript(lines=[claude_usage("n1", self.now - 1800, fresh=200, read=0, write=0, out=0),
                               claude_usage("n2", self.now - 300, fresh=20, read=0, write=0, out=0)])
        self.transcript(session=OTHER, lines=[claude_usage("x1", self.now - 7200, fresh=5, read=0, write=0, out=0)])
        (self.project / OTHER).mkdir(exist_ok=True)
        (self.project / OTHER / "custom-title.json").write_text(json.dumps({"customTitle": "我自己的会话"}), encoding="utf-8")

    def series(self, result):
        return {s["key"]: (s["label"], s["total"]["total"]) for s in result["series"]}

    def test_an_agent_counts_every_session_that_carried_its_seat_and_unseated_sessions_count_on_their_own(self):
        week = monitor.report(self.store, span="7d", group="agent", now=self.now)
        self.assertEqual(week["bucket"], "day")
        self.assertEqual(self.series(week), {"%s/head" % self.org: ("研发部 · head", 1220), OTHER: ("我自己的会话", 5)})
        self.assertEqual(week["total"], 1225)
        self.assertEqual(week["cumulative"][-1], 1225)
        self.assertEqual(sum(week["totals"]), 1225)
        orgs = monitor.report(self.store, span="7d", group="org", now=self.now)
        self.assertEqual(self.series(orgs), {self.org: ("研发部", 1220), "": (None, 5)})
        sessions = monitor.report(self.store, span="7d", group="session", now=self.now)
        self.assertEqual({k: v[1] for k, v in self.series(sessions).items()}, {self.OLD: 1000, SESSION: 220, OTHER: 5})
        self.assertIn({"key": "%s/head" % self.org, "label": "研发部 · head", "org": self.org}, week["filters"]["agents"])

    def test_filters_and_periods(self):
        only_seated = monitor.report(self.store, span="7d", group="session", org=self.org, now=self.now)
        self.assertEqual(set(self.series(only_seated)), {self.OLD, SESSION})
        unseated = monitor.report(self.store, span="7d", group="session", org="", now=self.now)
        self.assertEqual(set(self.series(unseated)), {OTHER})
        agent = monitor.report(self.store, span="7d", group="session", agent="%s/head" % self.org, now=self.now)
        self.assertEqual(set(self.series(agent)), {self.OLD, SESSION})
        day = monitor.report(self.store, span="24h", group="agent", now=self.now)
        self.assertEqual(day["bucket"], "hour")
        self.assertEqual(self.series(day)["%s/head" % self.org][1], 220)  # the earlier session is two days back
        head = next(s for s in day["series"] if s["key"] == "%s/head" % self.org)
        # The last bucket is the current hour: n1 (30 min ago) and n2 (5 min ago) count there only if they fell in
        # it. Within five minutes after the hour even n2 belongs to the previous one.
        last = day["starts"][-1]
        expected = sum(tokens for at, tokens in ((self.now - 1800, 200), (self.now - 300, 20)) if last <= at < last + 3600)
        self.assertEqual(head["values"][-1], expected)
        self.assertEqual(head["cumulative"], monitor._running(head["values"]))
        self.assertEqual(len(day["starts"]), len(head["values"]))
        for i, start in enumerate(day["starts"][1:], 1):
            self.assertEqual(start - day["starts"][i - 1], 3600)

    def test_days_start_at_local_midnight(self):
        week = monitor.report(self.store, span="7d", group="agent", now=self.now)
        for start in week["starts"]:
            moment = datetime.fromtimestamp(start)
            self.assertEqual((moment.hour, moment.minute), (0, 0))
        head = next(s for s in week["series"] if s["key"] == "%s/head" % self.org)
        older = datetime.fromtimestamp(self.now - 2 * 86400 - 60).replace(hour=0, minute=0, second=0, microsecond=0)
        self.assertEqual(head["values"][week["starts"].index(int(older.timestamp()))], 1000)

    def test_a_session_in_several_seats_splits_each_hour_by_its_tool_calls(self):
        first, second = int((self.now - 1800) // 3600), int((self.now - 300) // 3600)
        with self.store.db() as db:  # three calls as the cabinet's head and one as the department's, in n1's hour
            for org_id, calls in ((self.cabinet, 3), (self.org, 1)):
                for i in range(calls):
                    db.execute("INSERT INTO activity(org_id, member, tool, kind, summary, failed, at) VALUES(?,?,?,?,?,?,?)",
                               (org_id, "head", "Bash", "run", "ls", 0, first * 3600 + 60 + i))
        later = 20 * (0.75 if second == first else 0)
        result = monitor.report(self.store, span="24h", group="org", now=self.now)
        totals = {k: v[1] for k, v in self.series(result).items()}
        self.assertEqual(totals[self.cabinet], round(200 * 0.75 + later))
        self.assertEqual(totals[self.org], round(200 * 0.25 + 20 - later))
        agents = self.series(monitor.report(self.store, span="24h", group="agent", now=self.now))
        self.assertEqual(agents["%s/head" % self.cabinet][0], "秘书处 · head")

    def test_an_unseated_session_is_named_by_its_first_prompt(self):
        third = "33333333-2222-4333-8444-555555555555"
        self.transcript(session=third, lines=[
            json.dumps({"type": "user", "isMeta": True, "message": {"role": "user", "content": "<command-name>/init</command-name>"}}),
            json.dumps({"type": "user", "message": {"role": "user", "content": [
                {"type": "text", "text": "<system-reminder>context</system-reminder>"},
                {"type": "text", "text": "帮我统计一下这周每个组织用了多少 token，按天画图"}]}}),
            claude_usage("t1", self.now - 100)])
        series = self.series(monitor.report(self.store, span="24h", group="session", now=self.now))
        self.assertEqual(series[third][0], "帮我统计一下这周每个组织用了多少 token，按天画图")
        snap = monitor.snapshot(self.store, self.now)
        self.assertEqual(self.agent(snap, third)["title"], "帮我统计一下这周每个组织用了多少 token，按天画图")

    def test_the_sums_survive_a_restart_and_are_not_read_twice(self):
        monitor.report(self.store, span="7d", now=self.now)
        usage.Ledger._shared = None  # the App restarted
        again = monitor.report(self.store, span="7d", now=self.now)
        self.assertEqual(again["total"], 1225)
        size = usage.db_path().stat().st_size
        self.assertLess(size, 512 * 1024)  # sums only


class StopAndResume(Base):
    def test_stop_brakes_the_session_and_its_subagents_and_turns_off_every_seat_wake_up(self):
        self.transcript(lines=[claude_usage("m1", self.now - 10)])
        done = monitor.stop(self.store, SESSION)
        self.assertEqual(sorted(done["wake_off"]), sorted([[self.org, "head"], [self.cabinet, "head"]]))
        for org_id in (self.org, self.cabinet):
            self.assertFalse(self.store.get(org_id)["members"]["head"]["auto_wake"])
            self.assertFalse(wake.wakeable(self.store.get(org_id)["members"]["head"], {"harness": "claude-code"}))
        for session in (SESSION, SESSION + "/agent42"):
            out = self.hook("PreToolUse", session=session, tool_name="Bash", tool_input={"command": "ls"})
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertIn("Stopped by the person", out["hookSpecificOutput"]["permissionDecisionReason"])
        relic_tool = self.hook("PreToolUse", tool_name="mcp__plugin_relic_org__message", tool_input={"body": "x"})
        self.assertEqual(relic_tool["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.agent(monitor.snapshot(self.store, self.now), SESSION)["stopped"]["released"], False)

    def test_a_stopped_session_is_never_held_in_its_turn_and_automatic_prompts_end_at_once(self):
        self.store.send("chief", ["head"], "a direct question")
        self.assertEqual(self.hook("Stop", last_assistant_message="done").get("decision"), "block")  # normally held
        monitor.stop(self.store, SESSION)
        self.assertEqual(self.hook("Stop", last_assistant_message="where I stopped"), {})
        out = self.hook("UserPromptSubmit", prompt="[Relic auto-wake] You hold the seat 'head' ...")
        self.assertIn("Stopped by the person", json.dumps(out, ensure_ascii=False))
        self.assertIsNotNone(monitor.brake_for(SESSION))

    def test_the_person_typing_to_a_stopped_member_puts_it_back_to_work_with_its_wake_ups(self):
        monitor.stop(self.store, SESSION)
        out = self.hook("UserPromptSubmit", prompt="继续修 App")
        self.assertNotIn("Stopped by the person", json.dumps(out, ensure_ascii=False))
        self.assertIsNone(monitor.brake_for(SESSION))
        allowed = self.hook("PreToolUse", tool_name="Bash", tool_input={"command": "ls"})
        self.assertNotEqual((allowed.get("hookSpecificOutput") or {}).get("permissionDecision"), "deny")
        self.assertTrue(self.store.get(self.org)["members"]["head"]["auto_wake"])
        self.assertTrue(self.store.get(self.cabinet)["members"]["head"]["auto_wake"])
        self.assertIsNone(self.agent(monitor.snapshot(self.store, self.now), SESSION)["stopped"])
        self.assertFalse(monitor.resume(self.store, SESSION)["resumed"])  # nothing left to resume
        self.assertEqual(monitor._load_brakes(), {"agents": {}})

    def test_typing_to_a_stopped_session_without_a_seat_releases_only_that_session(self):
        monitor.stop(self.store, OTHER)
        monitor.stop(self.store, SESSION)
        self.hook("UserPromptSubmit", session=OTHER, prompt="go on")
        self.assertIsNone(monitor.brake_for(OTHER))
        self.assertIsNotNone(monitor.brake_for(SESSION))  # not a member's session: Relic stays stopped
        self.assertFalse(self.store.get(self.org)["members"]["head"]["auto_wake"])

    def test_resume_turns_back_on_only_what_stop_turned_off(self):
        self.store.set_seat_auto_wake(self.cabinet, "head", False, reason="the person turned it off earlier")
        monitor.stop(self.store, SESSION)
        monitor.resume(self.store, SESSION)
        self.assertTrue(self.store.get(self.org)["members"]["head"]["auto_wake"])
        self.assertFalse(self.store.get(self.cabinet)["members"]["head"]["auto_wake"])

    def test_stopping_a_codex_session_pauses_the_automations_that_start_it_and_resume_restores_them(self):
        path = self.automation()
        done = monitor.stop(self.store, "codex:" + THREAD)
        self.assertEqual(done["paused"], {"watch": "ACTIVE"})
        text = path.read_bytes().decode("utf-8")
        self.assertIn('status = "PAUSED"\r\n', text)
        self.assertNotIn("updated_at = 1793137492442", text)
        self.assertEqual(text.count("\r\n"), text.count("\n"))  # the file keeps its line endings
        monitor.resume(self.store, "codex:" + THREAD)
        self.assertIn('status = "ACTIVE"\r\n', path.read_bytes().decode("utf-8"))

    def test_stop_ends_a_running_relic_runner(self):
        runner.runs_dir().mkdir(parents=True, exist_ok=True)
        runner.write_state(self.org, "head", {"status": "running", "pid": 424242, "started": time.time()})
        with mock.patch.object(monitor, "_kill_tree", return_value=True) as kill:
            done = monitor.stop(self.store, SESSION)
        kill.assert_called_once_with(424242)
        self.assertEqual(done["killed"], [424242])
        state = runner.run_state(self.org, "head")
        self.assertEqual(state["status"], "stopped")
        self.assertIn("stopped by the person", state["error"])

    def test_stop_cancels_a_turn_the_app_runs_instead_of_ending_the_app(self):
        # The App's hub records its own process for the turns it runs; ending that pid ended the App.
        runner.runs_dir().mkdir(parents=True, exist_ok=True)
        state = {"status": "running", "pid": os.getpid(), "started": time.time(), "via": "relic-app"}
        runner.write_state(self.org, "head", state)
        cancelled = []
        with mock.patch.object(monitor, "_kill_tree", return_value=True) as kill:
            done = monitor.stop(self.store, SESSION, cancel_turn=lambda org, member: cancelled.append((org, member)))
        kill.assert_not_called()
        self.assertEqual(cancelled, [(self.org, "head")])
        self.assertEqual(done["cancelled"], [[self.org, "head"]])
        self.assertEqual(done["killed"], [])
        self.assertEqual(runner.run_state(self.org, "head")["status"], "running")  # the App ends its own turn
        # Without a way to cancel, an App turn is still never ended by its process.
        with mock.patch.object(monitor, "_kill_tree", return_value=True) as kill:
            monitor.stop(self.store, SESSION)
        kill.assert_not_called()

    def test_stop_all_turns_off_every_organization_and_automation_and_resume_all_restores_them(self):
        path = self.automation()
        self.store.set_auto_wake(self.cabinet, False)  # already off: Resume all leaves it off
        self.transcript(lines=[claude_usage("m1", self.now - 10)])
        result = monitor.stop_all(self.store, self.now)
        self.assertEqual(result["stopped"], [SESSION])
        self.assertEqual(result["orgs"], [self.org])
        self.assertEqual(result["paused"], ["watch"])
        self.assertFalse(self.store.get(self.org)["auto_wake"])
        self.assertIn('status = "PAUSED"', path.read_text(encoding="utf-8"))
        monitor.resume_all(self.store)
        self.assertTrue(self.store.get(self.org)["auto_wake"])
        self.assertFalse(self.store.get(self.cabinet)["auto_wake"])
        self.assertIn('status = "ACTIVE"', path.read_text(encoding="utf-8"))
        self.assertEqual(monitor._load_brakes(), {"agents": {}})

    def test_nothing_is_written_until_someone_is_stopped(self):
        self.transcript(lines=[claude_usage("m1", self.now - 10)])
        monitor.snapshot(self.store, self.now)
        self.assertFalse(monitor.brakes_path().exists())
        self.assertIsNone(monitor.brake_for(SESSION))


class Served(Base):
    """The Relic App's server on a free port, with the store of the test."""

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


class Api(Served):
    def test_the_monitor_needs_the_token_and_stop_and_resume_work_through_it(self):
        self.transcript(lines=[claude_usage("m1", time.time() - 10)])
        self.assertEqual(self.call("/api/monitor", token=False)[0], 403)
        code, snap = self.call("/api/monitor")
        self.assertEqual(code, 200)
        self.assertEqual([(a["key"], a["working"]) for a in snap["agents"]], [(SESSION, True), ("chief", False)])  # working first
        self.assertEqual(self.call("/api/monitor/stop", {})[0], 400)
        code, done = self.call("/api/monitor/stop", {"key": SESSION})
        self.assertEqual((code, sorted(done["wake_off"])), (200, sorted([[self.org, "head"], [self.cabinet, "head"]])))
        self.assertTrue(self.call("/api/monitor")[1]["agents"][0]["stopped"])
        self.assertEqual(self.call("/api/monitor/resume", {"key": SESSION})[1]["resumed"], True)


class BackToWork(Served):
    """Stop all, then the person's next message: in the Relic App or typed into a member's session, it releases the
    brakes and turns every organization's wake-ups back on, so members wake each other with messages; the timers stay
    paused until Resume all."""

    def setUp(self):
        super().setUp()
        from app import web
        quiet = mock.patch.object(web.App, "_dispatch")  # wake-ups are dispatched below, by hand, with a fake start
        quiet.start()
        self.addCleanup(quiet.stop)
        self.store.add_seat(self.cabinet, "gpt", "codex member", runner.default_config("codex"))
        self.store.join("codex:th-gpt", self.cabinet, "gpt")
        self.started = []

    def start(self, org_id, member, prompt, wake_from, wake_hop, wake_message_ids=None):
        self.started.append((org_id, member, wake_from, wake_hop))

    def dispatch(self, org_id):
        return wake.dispatch(self.store, org_id, now=time.time() + 60, start=self.start, age=lambda seat: None,
                             retry=lambda org_id, delay: None)

    def wake_ups(self, org_id):
        org = self.store.get(org_id)
        return org.get("auto_wake", True), {m: s.get("auto_wake", True) for m, s in org["members"].items()}

    def resumed(self, org_id):
        return [e["body"] for e in self.store.events(org_id, ["organization.wake_resumed"])]

    def stop_everything(self):
        path = self.automation() if not (self.root / "codex" / "automations" / "watch").exists() else None
        self.stops = getattr(self, "stops", 0) + 1
        self.transcript(lines=[claude_usage("stop%d" % self.stops, time.time() - 10)])
        result = monitor.stop_all(self.store)
        self.assertEqual(result["stopped"], [SESSION])
        self.assertFalse(self.store.get(self.org)["auto_wake"])
        return path

    def test_after_stop_all_a_message_in_the_app_resumes_wake_ups_and_leaves_the_automations_paused(self):
        self.store.set_auto_wake(self.cabinet, False)  # switched off by the person before: it comes back on too
        self.store.add_seat(self.org, "quiet", "", runner.default_config("codex"))
        self.store.set_seat_auto_wake(self.org, "quiet", False, reason="set by the person in the Relic App")
        path = self.stop_everything()
        self.store.send(SESSION, ["gpt"], "piled up while everyone was stopped", org=self.cabinet)
        self.assertEqual(self.dispatch(self.cabinet), [])
        self.assertIsNotNone(monitor.brake_for(SESSION))

        code, sent = self.call("/api/org/%s/send" % self.org, {"to": ["head"], "body": "继续干活", "channel": "private"})
        self.assertEqual((code, sent["to"]), (200, ["head"]))
        self.assertIsNone(monitor.brake_for(SESSION))
        self.assertEqual(self.wake_ups(self.org), (True, {"head": True, "quiet": False}))  # quiet: the person's switch
        self.assertEqual(self.wake_ups(self.cabinet), (True, {"chief": True, "head": True, "gpt": True}))
        self.assertIn('status = "PAUSED"', path.read_text(encoding="utf-8"))  # timers stay off
        [event] = self.resumed(self.org)
        self.assertEqual(event["why"], "the person wrote to head in 研发部")
        self.assertEqual((event["via"], event["to"], event["sessions"], event["still_paused"]),
                         ("message", ["head"], [SESSION], ["watch"]))
        self.assertEqual(sorted(event["orgs"]), sorted([self.org, self.cabinet]))
        self.assertEqual(sorted(event["seats"]), sorted([[self.org, "head"], [self.cabinet, "head"]]))
        reasons = [e["body"].get("reason") for e in self.store.events(self.cabinet, ["organization.auto_wake"])]
        self.assertEqual(reasons[-1], "the person wrote to head in 研发部")
        notices = [i["text"] for i in views.chat(self.store, self.org, "group", lang="zh-CN")["items"]
                   if i["type"] == "notice"]
        self.assertIn("停止已解除", notices[-1])
        self.assertIn("全部恢复", notices[-1])
        # the monitor still offers Resume all for the paused automation; the overview no longer says everything stopped
        snap = self.call("/api/monitor")[1]
        self.assertIsNone(self.agent(snap, SESSION)["stopped"])
        self.assertEqual((snap["stopped_all"]["paused"], snap["stopped_all"]["woken"]["why"]),
                         ({"watch": "ACTIVE"}, "the person wrote to head in 研发部"))
        self.assertFalse(overview.overview(self.store)["stopped_all"])

        # the member the person talked to writes to a member of another organization, and that member wakes there
        self.store.send(SESSION, ["gpt"], "gpt, please take the API part", org=self.cabinet)
        self.assertEqual(self.dispatch(self.cabinet), ["gpt"])
        self.assertEqual(self.started, [(self.cabinet, "gpt", ["head"], 1)])

        # a second message changes nothing more; Resume all brings the automation back
        self.call("/api/org/%s/send" % self.org, {"to": ["head"], "body": "还有一件事", "channel": "private"})
        self.assertEqual(len(self.resumed(self.org)), 1)
        self.assertEqual(monitor.resume_all(self.store)["resumed"], ["watch"])
        self.assertIn('status = "ACTIVE"', path.read_text(encoding="utf-8"))
        self.assertEqual(monitor._load_brakes(), {"agents": {}})
        self.assertIsNone(self.call("/api/monitor")[1]["stopped_all"])

    def test_a_group_message_and_a_forwarded_reply_end_the_stop_too(self):
        self.stop_everything()
        code, sent = self.call("/api/org/%s/send" % self.cabinet, {"to": ["all"], "body": "大家继续", "channel": "group"})
        self.assertEqual(code, 200)
        self.assertEqual(self.resumed(self.cabinet)[0]["why"], "the person wrote to chief, head, gpt in 秘书处")
        self.assertTrue(self.store.get(self.org)["auto_wake"])
        self.stop_everything()
        self.store.add_seat(self.org, "chat", "", runner.default_config("chatgpt"))
        code, _ = self.call("/api/org/%s/forward" % self.org, {"member": "chat", "to": ["head"], "body": "the reply"})
        self.assertEqual(code, 200)
        self.assertEqual(self.resumed(self.org)[-1]["why"], "the person forwarded the reply of chat in 研发部")
        self.assertTrue(self.store.get(self.org)["auto_wake"])
        self.assertTrue(self.store.get(self.cabinet)["auto_wake"])

    def test_typing_in_a_members_session_does_the_same(self):
        path = self.stop_everything()
        self.store.send(SESSION, ["gpt"], "piled up while everyone was stopped", org=self.cabinet)
        self.store.clear_focus(SESSION)  # the turn that wrote it ended: the session works for its main seat again
        out = self.hook("UserPromptSubmit", prompt="你该干活了")
        self.assertNotIn("Stopped by the person", json.dumps(out, ensure_ascii=False))
        self.assertIsNone(monitor.brake_for(SESSION))
        self.assertEqual(self.wake_ups(self.org), (True, {"head": True}))
        self.assertEqual(self.wake_ups(self.cabinet), (True, {"chief": True, "head": True, "gpt": True}))
        self.assertIn('status = "PAUSED"', path.read_text(encoding="utf-8"))
        [event] = self.resumed(self.org)
        self.assertEqual((event["why"], event["via"]), ("the person typed in the session of head in 研发部", "session"))
        self.assertEqual(self.dispatch(self.cabinet), ["gpt"])  # what piled up wakes gpt in its organization now
        self.assertEqual(self.started[0][:2], (self.cabinet, "gpt"))

    def test_prompts_that_relic_or_a_timer_started_do_not_end_the_stop(self):
        self.stop_everything()
        for prompt in ("[Relic] protocol P2 blocked Bash\n\n[Relic auto-wake] You hold the seat 'head' ...",
                       "<heartbeat>\n  <automation_id>watch</automation_id>\n  <instructions>check</instructions>",
                       "[Relic GUI nonce:ab12] [Relic auto-wake] ...", "You now hold the seat 'head' in ..."):
            self.assertTrue(monitor.automatic(prompt), prompt)
            self.hook("UserPromptSubmit", prompt=prompt)
        self.assertFalse(monitor.automatic("[Relic App] The person (human) writes to you directly:\n\ngo on"))
        self.assertFalse(self.store.get(self.org)["auto_wake"])
        self.assertIsNotNone(monitor.brake_for(SESSION))
        self.assertEqual(self.resumed(self.org), [])

    def test_nothing_changes_when_nothing_was_stopped(self):
        self.store.set_auto_wake(self.cabinet, False)  # the person's own switches keep working
        self.store.set_seat_auto_wake(self.org, "head", False, reason="set by the person in the Relic App")
        self.call("/api/org/%s/send" % self.org, {"to": ["head"], "body": "hello", "channel": "private"})
        self.hook("UserPromptSubmit", prompt="hello")
        self.assertIsNone(monitor.back_to_work(self.store, self.org, "message", ["head"]))
        self.assertFalse(monitor.brakes_path().exists())
        self.assertFalse(self.store.get(self.cabinet)["auto_wake"])
        self.assertFalse(self.store.get(self.org)["members"]["head"]["auto_wake"])
        self.assertEqual(self.resumed(self.org) + self.resumed(self.cabinet), [])
        # nor after a stop has been lifted: a switch the person turns off then stays off
        self.stop_everything()
        self.hook("UserPromptSubmit", prompt="back to work")
        self.assertTrue(self.store.get(self.cabinet)["auto_wake"])
        self.assertFalse(self.store.get(self.org)["members"]["head"]["auto_wake"])  # switched off before the Stop
        self.store.set_auto_wake(self.cabinet, False)
        self.call("/api/org/%s/send" % self.org, {"to": ["head"], "body": "and this", "channel": "private"})
        self.hook("UserPromptSubmit", prompt="and this")
        self.assertFalse(self.store.get(self.cabinet)["auto_wake"])
        self.assertEqual(len(self.resumed(self.org)), 1)


if __name__ == "__main__":
    unittest.main()
