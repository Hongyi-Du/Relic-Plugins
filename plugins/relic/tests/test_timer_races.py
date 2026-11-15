"""chief's four counter-examples to the first draft (秘书处, 2026-11-14), each kept as a test:

1. The same question asked twice made two messages, two timers and two notices: Falcon's repeated asking. A question is
   asked once under its key (across seats that take over), in one transaction; the first deadline stands.
2. Answering one question settled every open question of the seat. An answer settles only the question it answers:
   a reply in its thread, or its id named (A2, #<message id>); a message that names none settles none.
3. A notice that failed to be written left the question ran_out with no timer and nobody told, for good. The question's
   new state, the notice and the timer's end are one transaction; a failure leaves all as it was and the timer comes
   again when its lease runs out, once.
4. A pause set anew while the old timer was being handled was switched on and its new timer deleted. A timer acts only
   while it is still the one in the store (its ref is the record's id): a new pause, the person's switch or a restart
   in between leaves it nothing to do; the person's Stop goes first."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core import monitor  # noqa: E402
from relic_core.store import Store  # noqa: E402

CHIEF, LEAD, DEV, OPS = "chief-s", "lead-s", "dev-s", "ops-s"


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
        s.join(OPS, self.team, "ops", "operations")
        s.set_parent(self.team, self.top)
        self.chief = "%s/chief" % self.top

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def notices(self, actor):
        return [m for m in self.store.unread(actor) if m["from"] == "relic"]

    def timer(self, kind, key):
        with self.store.db() as db:
            return db.execute("SELECT due, ref FROM timers WHERE kind=? AND key=?", (kind, key)).fetchone()

    def messages_to_human(self):
        with self.store.db() as db:
            return db.execute("SELECT id FROM messages WHERE org_id=? AND recipients LIKE '%human%'",
                              (self.team,)).fetchall()

    def claim(self, now_ts):
        """fire_timers' first step alone: claim what is due, as another process would."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT kind, key, ref FROM timers WHERE due<=?", (now_ts,)).fetchall()
            db.execute("UPDATE timers SET due=? WHERE due<=?", (now_ts + Store.LEASE, now_ts))
        return rows


class AskedOnce(Base):
    def test_the_same_question_twice_is_one_question_with_the_first_deadline(self):
        first = self.store.send(DEV, ["human"], "Falcon 现在开跑吗？", recommend="开跑")
        time.sleep(1.1)
        again = self.store.send(DEV, ["human"], "Falcon 现在开跑吗？", recommend="开跑")
        self.assertTrue(again["already_asked"])
        self.assertEqual(again["ask"]["id"], first["ask"]["id"])
        self.assertEqual(again["ask"]["due"], first["ask"]["due"], "the first deadline stands")
        self.assertEqual(len(self.messages_to_human()), 1)
        due, _ = self.timer("ask", "%s/%s" % (self.team, first["ask"]["id"]))
        self.store.fire_timers(due)
        self.assertEqual(len(self.notices(DEV)), 1)

    def test_a_seat_that_takes_over_asks_under_the_same_key(self):
        first = self.store.send(DEV, ["human"], "T 阶段开吗？", recommend="开", ask_key="falcon-T")
        again = self.store.send(OPS, ["human"], "接手：T 阶段开吗？", recommend="开", ask_key="falcon-T")
        self.assertTrue(again["already_asked"])
        self.assertEqual(again["ask"]["id"], first["ask"]["id"])
        self.assertEqual(len(self.messages_to_human()), 1)

    def test_a_different_question_is_asked(self):
        self.store.send(DEV, ["human"], "Falcon 开跑吗？", recommend="开跑")
        other = self.store.send(DEV, ["human"], "换下一题吗？", recommend="换 mko")
        self.assertNotIn("already_asked", other)
        self.assertEqual(len(self.messages_to_human()), 2)


class AnswersBindToTheirQuestion(Base):
    def two(self):
        a = self.store.send(DEV, ["human"], "问题一：开跑吗？", recommend="开跑")["ask"]
        b = self.store.send(DEV, ["human"], "问题二：换题吗？", recommend="换")["ask"]
        return a, b

    def status(self, aid):
        return self.store.get(self.team)["asks"][aid]["status"]

    def test_a_reply_in_one_questions_thread_settles_only_that_one(self):
        a, b = self.two()
        self.store.send_from_human(self.team, ["dev"], "换", reply_to=b["message_id"])
        self.assertEqual((self.status(a["id"]), self.status(b["id"])), ("open", "answered"))
        self.assertIsNotNone(self.timer("ask", "%s/%s" % (self.team, a["id"])), "the first one still runs")

    def test_naming_a_question_anywhere_settles_it(self):
        a, b = self.two()
        self.store.send_from_human(self.team, ["ops"], "%s 先不跑" % a["id"])
        self.assertEqual((self.status(a["id"]), self.status(b["id"])), ("answered", "open"))
        self.store.send_from_human(self.team, ["lead"], "#%d 换吧" % b["message_id"])
        self.assertEqual(self.status(b["id"]), "answered")

    def test_a_message_that_names_no_question_settles_none(self):
        a, b = self.two()
        self.store.send_from_human(self.team, ["dev"], "跑")
        self.assertEqual((self.status(a["id"]), self.status(b["id"])), ("open", "open"))

    def test_a_late_answer_changes_nothing(self):
        a, _ = self.two()
        due, _ = self.timer("ask", "%s/%s" % (self.team, a["id"]))
        self.store.fire_timers(due)
        self.store.send_from_human(self.team, ["dev"], "先不跑", reply_to=a["message_id"])
        self.assertEqual(self.status(a["id"]), "ran_out")


class NoticesAreNeverLost(Base):
    def test_a_failed_notice_leaves_all_as_it_was_and_comes_again_once(self):
        ask = self.store.send(DEV, ["human"], "开跑吗？", recommend="开跑")["ask"]
        key = "%s/%s" % (self.team, ask["id"])
        due, _ = self.timer("ask", key)
        real_post = Store._post
        calls = {"n": 0}

        def failing(store, db, org_id, sender, recipients, body, hop=0):
            if sender == "relic":
                calls["n"] += 1
                raise OSError("disk full for a moment")
            return real_post(store, db, org_id, sender, recipients, body, hop)
        with mock.patch.object(Store, "_post", failing):
            done = self.store.fire_timers(due)
        self.assertEqual(calls["n"], 1)
        self.assertIn("error", done[0])
        self.assertEqual(self.store.get(self.team)["asks"][ask["id"]]["status"], "open", "nothing half done")
        self.assertEqual(self.notices(DEV), [])
        self.assertEqual(self.store.fire_timers(due + 1), [], "leased: not again at once")
        again = Store()  # a restart in between
        again.fire_timers(due + Store.LEASE)
        self.assertEqual(again.get(self.team)["asks"][ask["id"]]["status"], "ran_out")
        self.assertEqual(len(self.notices(DEV)), 1)
        again.fire_timers(due + 10 * Store.LEASE)
        self.assertEqual(len(self.notices(DEV)), 0, "once")

    def test_a_failed_pause_end_comes_again(self):
        self.store.set_auto_wake(self.team, False, reason="heavy job", until="90m", by=self.chief)
        due, _ = self.timer("wake", self.team)
        with mock.patch.object(Store, "_tell_pauser", side_effect=OSError("locked")):
            self.store.fire_timers(due)
        self.assertFalse(self.store.get(self.team)["auto_wake"], "rolled back")
        self.store.fire_timers(due + Store.LEASE)
        self.assertTrue(self.store.get(self.team)["auto_wake"])
        self.assertEqual(len(self.notices(CHIEF)), 1)


class TimersActOnlyOnTheirOwnRecord(Base):
    def test_a_new_pause_set_meanwhile_keeps_its_own_timer(self):
        self.store.set_auto_wake(self.team, False, reason="first", until="90m", by=self.chief)
        due, old_ref = self.timer("wake", self.team)
        claimed = self.claim(due)
        self.assertEqual(claimed, [("wake", self.team, old_ref)])
        self.store.set_auto_wake(self.team, False, reason="Codex 额度又满了", until="6h", by=self.chief)
        new_due, new_ref = self.timer("wake", self.team)
        self.assertNotEqual(new_ref, old_ref)
        self.assertIsNone(self.store._fire("wake", self.team, old_ref, due))
        self.assertFalse(self.store.get(self.team)["auto_wake"], "the new pause stands")
        self.assertEqual(self.timer("wake", self.team), (new_due, new_ref), "its timer is untouched")
        self.store.fire_timers(new_due)
        self.assertTrue(self.store.get(self.team)["auto_wake"])

    def test_the_person_switching_it_on_meanwhile(self):
        self.store.set_auto_wake(self.team, False, reason="x", until="90m", by=self.chief)
        due, ref = self.timer("wake", self.team)
        self.claim(due)
        self.store.set_auto_wake(self.team, True)  # the person, in the Relic App
        self.assertIsNone(self.store._fire("wake", self.team, ref, due))
        self.assertTrue(self.store.get(self.team)["auto_wake"])
        self.assertEqual(self.notices(CHIEF), [])

    def test_the_person_switching_it_off_meanwhile_stays_off(self):
        self.store.set_auto_wake(self.team, False, reason="x", until="90m", by=self.chief)
        due, ref = self.timer("wake", self.team)
        self.claim(due)
        self.store.set_auto_wake(self.team, False)  # the person's own switch: no timer
        self.assertIsNone(self.store._fire("wake", self.team, ref, due))
        self.assertFalse(self.store.get(self.team)["auto_wake"])
        self.assertIsNone(self.timer("wake", self.team))

    def test_the_persons_stop_goes_first(self):
        self.store.set_auto_wake(self.team, False, reason="x", until="90m", by=self.chief)
        due, ref = self.timer("wake", self.team)
        with mock.patch.object(monitor, "stopped", return_value=True):
            done = self.store.fire_timers(due)
        self.assertEqual(done[0]["outcome"], "held by the person's stop")
        self.assertFalse(self.store.get(self.team)["auto_wake"])
        self.assertEqual(self.timer("wake", self.team)[1], ref, "it waits, not lost")
        self.store.fire_timers(due + 601)
        self.assertTrue(self.store.get(self.team)["auto_wake"])

    def test_two_processes_fire_each_timer_once(self):
        self.store.set_auto_wake(self.team, False, reason="x", until="90m", by=self.chief)
        due, _ = self.timer("wake", self.team)
        other = Store()
        first = [d for d in self.store.fire_timers(due) if d.get("kind") == "wake"]
        second = [d for d in other.fire_timers(due) if d.get("kind") == "wake"]
        self.assertEqual((len(first), len(second)), (1, 0))
        self.assertEqual(len(self.notices(CHIEF)), 1)


class NoEndlessBackgroundChecks(Base):
    def test_the_scan_never_arms_the_background_check_by_itself(self):
        self.store.fire_timers()  # first run: the scan, which writes its own marker row
        with self.store.db() as db:
            self.assertIsNotNone(db.execute("SELECT 1 FROM timers WHERE kind='scan'").fetchone())
        self.assertIsNone(self.store.next_timer(), "nothing to arm a background check for")
        self.store.set_auto_wake(self.team, False, reason="x", until="90m", by=self.chief)
        self.assertIsNotNone(self.store.next_timer())

    def test_an_older_timers_table_gets_its_ref_column(self):
        path = Path(os.environ["RELIC_HOME"]) / "old" / "relic.sqlite3"
        path.parent.mkdir(parents=True)
        import sqlite3
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE timers(kind TEXT, key TEXT, due REAL, PRIMARY KEY(kind, key))")
            db.execute("INSERT INTO timers VALUES('scan', 'all', 1)")
        os.environ["RELIC_HOME"] = str(path.parent)
        store = Store()
        with store.db() as db:
            self.assertIn("ref", [r[1] for r in db.execute("PRAGMA table_info(timers)")])
        store.fire_timers()  # works on the migrated table


if __name__ == "__main__":
    unittest.main()
