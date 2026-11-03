"""The person's monitor: who is working on this machine, the tokens each session used (from its own records), and the
Stop that ends a session's turn and turns off what would start it again, with Resume undoing exactly that.
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
from relic_core import monitor, runner, wake  # noqa: E402
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
        monitor._ledgers.clear()
        monitor._codex_limits.update(at=0.0, value=None)
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

    def test_the_person_typing_releases_the_brake_but_wake_ups_stay_off_until_resume(self):
        monitor.stop(self.store, SESSION)
        out = self.hook("UserPromptSubmit", prompt="继续修 App")
        self.assertNotIn("Stopped by the person", json.dumps(out, ensure_ascii=False))
        self.assertIsNone(monitor.brake_for(SESSION))
        allowed = self.hook("PreToolUse", tool_name="Bash", tool_input={"command": "ls"})
        self.assertNotEqual((allowed.get("hookSpecificOutput") or {}).get("permissionDecision"), "deny")
        self.assertFalse(self.store.get(self.org)["members"]["head"]["auto_wake"])
        self.assertTrue(self.agent(monitor.snapshot(self.store, self.now), SESSION)["stopped"]["released"])
        self.assertTrue(monitor.resume(self.store, SESSION)["resumed"])
        self.assertTrue(self.store.get(self.org)["members"]["head"]["auto_wake"])
        self.assertTrue(self.store.get(self.cabinet)["members"]["head"]["auto_wake"])
        self.assertNotIn(SESSION, monitor._load_brakes().get("agents", {}))

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


if __name__ == "__main__":
    unittest.main()
