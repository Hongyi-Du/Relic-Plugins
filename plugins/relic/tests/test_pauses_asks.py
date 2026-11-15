"""Pauses that end and questions that run out (the person, 2026-11-12/14: 「你得先知道我为什么停然后再根据我的痛点做处理」
「我不是所有时间全都在电脑前面的，我不看就不动」「如果我一个小时没反应你的继续，你就直接开干」; chief's acceptance list in
秘书处's 《去官僚方案》, 2026-11-14).

A member's pause names its end (a time, quota:codex, idle) and Relic ends it then, after checking the reason really
went away; a pause without an end is never restarted blindly: its pauser is asked every two hours. The person's own
switches end with the person's next message, never with a timer. A question to the person (message to human with
recommend) runs out after an hour at most: one notice to the executor to go ahead, none when the person answered or
stopped the work meanwhile. Timers live in the store: a restart keeps them, two processes fire each once. Members read
the person's own words (typed into seats' sessions) with work op=said instead of asking each other for them."""
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core import store as store_module  # noqa: E402
from relic_core.context import render  # noqa: E402
from relic_core.store import PAUSE_DEFAULT, OrgError, Store, epoch, mask_secrets  # noqa: E402

CHIEF, LEAD, DEV = "chief-s", "lead-s", "dev-s"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        os.environ["CODEX_HOME"] = str(Path(self.tmp.name) / "codex")
        self.store = s = Store()
        self.top = s.create(CHIEF, "Cabinet", "the person's work", "chief", "secretary-general")["id"]
        self.team = s.create(LEAD, "Research", "run the study", "lead", "lead")["id"]
        s.join(DEV, self.team, "dev", "experiments")
        s.set_parent(self.team, self.top)
        self.chief = "%s/chief" % self.top

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def notices(self, actor):
        return [m for m in self.store.unread(actor) if m["from"] == "relic"]

    def due(self, kind, key):
        with self.store.db() as db:
            row = db.execute("SELECT due FROM timers WHERE kind=? AND key=?", (kind, key)).fetchone()
        return row[0] if row else None

    def codex_limits(self, used, resets_at):
        path = Path(os.environ["RELIC_HOME"]) / "usage.sqlite3"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("INSERT OR REPLACE INTO meta VALUES('codex_limits', ?)", (json.dumps(
                {"at": time.time(), "value": {"primary": {"used_percent": used, "resets_at": resets_at}}}),))


class MemberPauses(Base):
    def test_a_pause_with_an_end_ends_then_and_tells_its_pauser(self):
        end = time.time() + 3600
        self.store.set_auto_wake(self.team, False, reason="Learning runs a heavy job", until=end, by=self.chief)
        org = self.store.get(self.team)
        self.assertFalse(org["auto_wake"])
        self.assertIn("Learning runs a heavy job", "\n".join(render(self.store, org, "dev").splitlines()))
        due = self.due("wake", self.team)
        self.assertEqual(self.store.fire_timers(due - 1), [])
        self.assertFalse(self.store.get(self.team)["auto_wake"])
        done = self.store.fire_timers(due)
        self.assertEqual([d["outcome"] for d in done if d["kind"] == "wake"], ["ended"])
        self.assertTrue(self.store.get(self.team)["auto_wake"])
        self.assertNotIn("pause", self.store.get(self.team))
        told = self.notices(CHIEF)
        self.assertEqual(len(told), 1)
        self.assertIn("Research", told[0]["body"])
        self.assertEqual([d for d in self.store.fire_timers(due + 10) if d["kind"] == "wake"], [], "fires once")

    def test_a_pause_without_an_end_is_reviewed_never_restarted_blindly(self):
        self.store.set_auto_wake(self.team, False, reason="old queue", by=self.chief)
        due = self.due("wake", self.team)
        self.assertAlmostEqual(due, time.time() + PAUSE_DEFAULT, delta=5)
        done = self.store.fire_timers(due)
        self.assertEqual([d["outcome"] for d in done if d["kind"] == "wake"], ["review"])
        self.assertFalse(self.store.get(self.team)["auto_wake"], "still off: only its pauser decides")
        self.assertEqual(len(self.notices(CHIEF)), 1)
        self.assertAlmostEqual(self.due("wake", self.team), due + PAUSE_DEFAULT, delta=1)

    def test_an_older_plugins_reason_only_switch_off_is_a_reviewed_pause(self):
        self.store.set_auto_wake(self.team, False, reason="11-12 Netty done; pausing the old queue")
        self.assertTrue(self.store.get(self.team)["pause"]["review"])

    def test_the_persons_own_switches_never_end_by_a_timer(self):
        self.store.set_auto_wake(self.team, False)  # the Relic App's switch
        self.store.set_seat_auto_wake(self.team, "dev", False, reason="stopped by the person in the Relic window")
        self.store.set_auto_wake(self.top, False, reason="stopped with Stop all in the Relic window")
        self.assertIsNone(self.store.next_timer())
        self.store.fire_timers(time.time() + 30 * 24 * 3600)
        self.assertFalse(self.store.get(self.team)["auto_wake"])
        self.assertFalse(self.store.get(self.team)["members"]["dev"]["auto_wake"])

    def test_turning_it_back_on_cancels_the_timer(self):
        self.store.set_auto_wake(self.team, False, reason="x", until="6h", by=self.chief)
        self.store.set_auto_wake(self.team, True)
        self.assertIsNone(self.due("wake", self.team))

    def test_until_forms(self):
        now = time.time()
        self.assertAlmostEqual(store_module.pause_end("90m", now), now + 5400)
        self.assertAlmostEqual(store_module.pause_end("6h", now), now + 6 * 3600)
        self.assertEqual(store_module.pause_end("2026-11-16T15:13:00Z", epoch("2026-11-14T15:13:00Z")),
                         epoch("2026-11-16T15:13:00Z"))
        self.assertEqual(store_module.pause_end("30d", now) if False else store_module.pause_end(now + 30 * 86400, now),
                         now + store_module.PAUSE_MAX)
        with self.assertRaises(OrgError):
            store_module.pause_end("when it feels right", now)

    def test_a_seat_pause_and_a_restart_of_the_store(self):
        self.store.set_seat_auto_wake(self.team, "dev", False, reason="dev's laptop job", until="90m", by=self.chief)
        due = self.due("seat", "%s/dev" % self.team)
        again = Store()  # another process, or the App restarted: the timer is in the store
        again.fire_timers(due)
        self.assertTrue(again.get(self.team)["members"]["dev"]["auto_wake"])

    def test_quota_waits_for_a_real_reset(self):
        self.codex_limits(97, time.time() + 3600)
        self.store.set_drive(self.team, True, goal="keep the study going", driver="lead")
        self.store.set_drive(self.team, False, by=self.chief, reason="Codex 周额度 97%", until="quota:codex")
        due = self.due("drive", self.team)
        self.assertFalse(self.store.get(self.team)["drive"]["on"])
        done = self.store.fire_timers(due)
        self.assertEqual([d["outcome"] for d in done if d["kind"] == "drive"], ["quota not reset yet"])
        self.assertFalse(self.store.get(self.team)["drive"]["on"], "no reset in the usage data yet")
        self.codex_limits(4, time.time() + 8 * 86400)  # reset seen: a later reset time and low use
        self.store.fire_timers(self.due("drive", self.team))
        drive = self.store.get(self.team)["drive"]
        self.assertTrue(drive["on"])
        self.assertEqual(drive["goal"], "keep the study going")

    def test_the_fresher_of_the_apps_copy_and_codexs_own_session_file_decides(self):
        stale_reset = time.time() - 5 * 86400
        path = Path(os.environ["RELIC_HOME"]) / "usage.sqlite3"  # the App's usage reader stopped five days ago
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("INSERT OR REPLACE INTO meta VALUES('codex_limits', ?)", (json.dumps(
                {"at": time.time() - 5 * 86400, "value": {"primary": {"used_percent": 98, "resets_at": stale_reset}}}),))
        day = Path(os.environ["CODEX_HOME"]) / "sessions" / "2026" / "11" / "14"
        day.mkdir(parents=True)
        fresh_reset = time.time() + 40 * 3600
        record = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                  "type": "event_msg", "payload": {"type": "token_count", "rate_limits": {
                      "primary": {"used_percent": 86.0, "window_minutes": 10080, "resets_at": fresh_reset}}}}
        (day / "rollout-2026-11-14T10-00-00-0000.jsonl").write_text(json.dumps(record) + chr(10), encoding="utf-8")
        limits = store_module.codex_limits()
        self.assertEqual((limits["used_percent"], limits["resets_at"]), (86.0, fresh_reset))
        self.assertEqual(store_module.codex_reset(), fresh_reset)
        self.assertEqual(store_module.pause_end("quota:codex", time.time()), fresh_reset)

    def test_idle_waits_for_the_person_to_leave_the_computer(self):
        self.store.set_auto_wake(self.team, False, reason="the person is playing", until="idle", by=self.chief)
        due = self.due("wake", self.team)
        with mock.patch.object(store_module, "presence", return_value={"at_computer": True, "game": "PBZ"}):
            self.store.fire_timers(due)
        self.assertFalse(self.store.get(self.team)["auto_wake"])
        with mock.patch.object(store_module, "presence", return_value={"at_computer": False, "game": None}):
            self.store.fire_timers(self.due("wake", self.team))
        self.assertTrue(self.store.get(self.team)["auto_wake"])

    def test_legacy_scan_gives_old_switch_offs_a_review(self):
        with self.store.change(self.team) as (org, db):
            org["auto_wake"] = False  # an older plugin wrote it without a pause record
            self.store._event(db, self.team, "human", "organization.auto_wake",
                              {"on": False, "reason": "pausing the old queue"})
        found = self.store.fire_timers()
        self.assertTrue(any(f.get("key") == self.team for f in found))
        self.assertTrue(self.store.get(self.team)["pause"]["review"])
        self.assertFalse(self.store.get(self.team)["auto_wake"], "a review, not a blind restart")


class QuestionsToThePerson(Base):
    def ask(self, **extra):
        r = self.store.send(DEV, ["human"], "Falcon 这一轮现在开跑吗？", recommend="开跑 S，S 原评后接 T", **extra)
        return r["ask"]

    def test_the_question_says_until_when_and_runs_out_once_after_an_hour(self):
        ask = self.ask()
        with self.store.db() as db:
            body = db.execute("SELECT body FROM messages WHERE id=?", (ask["message_id"],)).fetchone()[0]
        self.assertIn("开跑 S，S 原评后接 T", body)
        self.assertIn("芝加哥时间", body)
        due = self.due("ask", "%s/%s" % (self.team, ask["id"]))
        self.assertAlmostEqual(due, time.time() + 3600, delta=5)
        self.assertEqual(self.store.fire_timers(due - 1), [], "59:59: nothing yet")
        done = self.store.fire_timers(due)
        self.assertEqual([d["outcome"] for d in done if d["kind"] == "ask"], ["ran out"])
        told = self.notices(DEV)
        self.assertEqual(len(told), 1)
        self.assertIn("开跑 S，S 原评后接 T", told[0]["body"])
        self.assertEqual([d for d in self.store.fire_timers(due + 60) if d["kind"] == "ask"], [], "once")

    def test_the_executor_hears_it(self):
        ask = self.ask(executor="lead")
        self.store.fire_timers(self.due("ask", "%s/%s" % (self.team, ask["id"])))
        self.assertEqual(len(self.notices(LEAD)), 1)
        self.assertEqual(len(self.notices(DEV)), 1)

    def test_an_answer_before_the_hour_settles_it(self):
        ask = self.ask()
        due = self.due("ask", "%s/%s" % (self.team, ask["id"]))
        self.store.send_from_human(self.team, ["dev"], "跑", reply_to=ask["message_id"])
        self.assertIsNone(self.due("ask", "%s/%s" % (self.team, ask["id"])))
        self.assertEqual(self.store.fire_timers(due + 1), [])
        self.assertEqual(self.store.get(self.team)["asks"][ask["id"]]["status"], "answered")

    def test_a_late_answer_after_the_hour_is_just_a_message(self):
        ask = self.ask()
        self.store.fire_timers(self.due("ask", "%s/%s" % (self.team, ask["id"])))
        self.store.send_from_human(self.team, ["dev"], "先不跑")
        self.assertEqual(self.store.get(self.team)["asks"][ask["id"]]["status"], "ran_out")

    def test_the_persons_stop_before_the_hour_holds_it(self):
        ask = self.ask()
        self.store.set_auto_wake(self.team, False)  # the person switched the organization off in the Relic App
        self.store.fire_timers(self.due("ask", "%s/%s" % (self.team, ask["id"])))
        self.assertEqual(self.store.get(self.team)["asks"][ask["id"]]["status"], "held")
        self.assertEqual(self.notices(DEV), [])

    def test_within_is_an_hour_at_most(self):
        ask = self.store.send(DEV, ["human"], "q", recommend="r", within=600)["ask"]
        self.assertAlmostEqual(epoch(ask["due"]), time.time() + 3600, delta=5)
        ask = self.store.send(DEV, ["human"], "q2", recommend="r", within=20)["ask"]
        self.assertAlmostEqual(epoch(ask["due"]), time.time() + 1200, delta=5)

    def test_recommend_goes_with_a_question_to_the_person(self):
        with self.assertRaises(OrgError):
            self.store.send(DEV, ["lead"], "q", recommend="r")
        with self.assertRaises(OrgError):
            self.store.send(DEV, ["human"], "q", recommend="r", executor="nobody")

    def test_the_context_shows_the_running_question(self):
        self.ask()
        text = render(self.store, self.store.get(self.team), "dev")
        self.assertIn("Question to the person", text)
        self.assertIn("开跑 S，S 原评后接 T", text)


class ThePersonsWords(Base):
    def test_members_read_the_words_typed_into_seats_of_their_organization_and_below(self):
        s = self.store
        s.person_said("claude-code", "sess-1", "%s/dev" % self.team, "跑")
        s.person_said("codex", "sess-2", "%s/chief" % self.top, "秘书处的事")
        s.person_said("claude-code", "sess-3", None, "a private chat")
        above = s.work(CHIEF, "said", {})["said"]
        self.assertEqual([w["text"] for w in above], ["秘书处的事", "跑"])
        below = s.work(DEV, "said", {})["said"]
        self.assertEqual([w["text"] for w in below], ["跑"], "the cabinet's words stay above")
        self.assertEqual(s.work(CHIEF, "said", {"query": "跑"})["said"][0]["place"], "%s/dev" % self.team)

    def test_secrets_are_masked(self):
        self.assertNotIn("sk-TESTabcdefghijklmnopqr", mask_secrets("key sk-TESTabcdefghijklmnopqr please"))
        self.assertNotIn("hunter2", mask_secrets("密码：hunter2"))
        self.assertEqual(mask_secrets("跑啊 为什么我不回复就这么保守呢"), "跑啊 为什么我不回复就这么保守呢")

    def test_the_hook_keeps_only_what_the_person_typed(self):
        sys.path.insert(0, str(ROOT / "hooks"))
        import importlib
        hook = importlib.import_module("relic_hook")
        for prompt in ("你继续调吧", "<task-notification>x</task-notification>", "[Relic auto-wake] go",
                       "<cross-session-message from=x>hi</cross-session-message>"):
            hook.person_typed({"hook_event_name": "UserPromptSubmit", "prompt": prompt, "session_id": "s"},
                              "UserPromptSubmit", DEV, self.store)
        self.assertEqual([w["text"] for w in self.store.work(LEAD, "said", {})["said"]], ["你继续调吧"])


if __name__ == "__main__":
    unittest.main()
