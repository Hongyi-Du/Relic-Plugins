"""The person away from the computer (2026-11-15: 「我如果不在的话…他们就应该是一个自主运行的模式」「别他妈啥时候都问我了，我不在
我怎么审批啊」「看鼠标啊前台啊」「我跟 Claude 说的话，他转述给 Codex，结果 Codex 那边说这不是我人说的，然后又不干」).

Relic tells from the keyboard, the mouse and the window in front whether the person is at the computer. While they are
away nobody waits for them: a question goes ahead with its recommendation, the harnesses' question tools are refused
with the reason, a turn does not end on a question, and a woken member is told to run on its own. The person's words
that a member relays carry Relic's check, so the member who gets them need not ask the person again."""
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core import store as store_module  # noqa: E402
from relic_core import wake  # noqa: E402
from relic_core.context import render  # noqa: E402
from relic_core.store import IDLE_AFTER, SYSTEM, Store  # noqa: E402

_spec = importlib.util.spec_from_file_location("relic_hook_for_away", ROOT / "hooks" / "relic_hook.py")
relic_hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(relic_hook)

LEAD, DEV, CHILD, STRANGER = "lead-away", "dev-away", "child-away", "stranger-away"
AWAY = "The person is away from the computer"
WORDS = "以后 OrgBench 的实验自己跑，不用再找上级申请，也不用等科研部代跑。"


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"RELIC_HOME": str(Path(self.tmp.name) / "relic"), "RELIC_LANG": "en-US",
                                           "RELIC_PRESENCE": "here"})
        env.start()
        self.addCleanup(env.stop)
        self.store = s = Store()
        self.team = s.create(LEAD, "Bench", "build the benchmark", "lead", "lead")["id"]
        s.join(DEV, self.team, "dev", "developer")

    @staticmethod
    def leave():
        os.environ["RELIC_PRESENCE"] = "away"

    def unread(self, actor):
        return self.store.unread(actor, mark=False, limit=None)

    def hook(self, event, session):
        return relic_hook.respond(dict(event, session_id=session), self.store)


class Presence(Fixture):
    def test_the_override_sets_it(self):
        self.assertTrue(store_module.presence()["at_computer"])
        self.leave()
        seen = store_module.presence()
        self.assertIs(seen["at_computer"], False)
        self.assertGreaterEqual(seen["idle_seconds"], IDLE_AFTER)

    @unittest.skipUnless(sys.platform == "win32", "the keyboard, mouse and window in front are read on Windows")
    def test_it_reads_the_keyboard_and_the_window_in_front(self):
        os.environ.pop("RELIC_PRESENCE")
        seen = store_module.presence()
        self.assertEqual(set(seen), {"idle_seconds", "foreground", "fullscreen", "locked", "game", "at_computer"})
        if seen["at_computer"] is not None:  # a runner without a desktop cannot tell
            self.assertGreaterEqual(seen["idle_seconds"], 0)
            self.assertIsInstance(seen["locked"], bool)

    @unittest.skipUnless(sys.platform == "win32", "the keyboard, mouse and window in front are read on Windows")
    def test_a_locked_screen_is_away_at_once_and_a_game_in_front_is_not(self):
        os.environ.pop("RELIC_PRESENCE")
        with mock.patch.object(store_module, "_foreground", return_value=("LockApp", False, True)):
            seen = store_module.presence()
        if seen["idle_seconds"] is None:
            self.skipTest("no desktop to read here")
        self.assertIs(seen["at_computer"], False, "locked: away whatever the last input")
        with mock.patch.object(store_module, "_foreground", return_value=("VALORANT", True, False)):
            seen = store_module.presence()
        self.assertEqual(seen["game"], "VALORANT")
        self.assertTrue(seen["at_computer"], "a game in front: at the computer whatever the input")

    def test_typing_to_a_member_or_in_the_app_counts_as_around(self):
        self.leave()
        self.assertEqual(self.store.person_away(), {"minutes": IDLE_AFTER // 60, "locked": False})
        self.store.person_said("claude-code", "s1", "%s/lead" % self.team, "从手机上看一眼进度")
        self.assertIsNone(self.store.person_away(), "typed to a member a moment ago (a phone too)")
        self.assertEqual(self.store.person_away(time.time() + IDLE_AFTER + 60)["locked"], False, "and later not")
        fresh = Store()
        with fresh.db() as db:
            db.execute("DELETE FROM person_words")
            db.execute("INSERT INTO messages(org_id,sender,recipients,body,at,hop) VALUES(?,?,?,?,?,0)",
                       (self.team, "human", '["dev"]', "继续", store_module.now()))
        self.assertIsNone(fresh.person_away(), "wrote in the Relic App a moment ago")


class Questions(Fixture):
    def test_a_question_does_not_wait_while_the_person_is_away(self):
        self.leave()
        result = self.store.send(DEV, ["human"], "PyG 这一题现在开跑吗？", recommend="开跑，2 CPU / 8 GiB", executor="lead")
        self.assertEqual(result["ask"]["status"], "away")
        self.assertIn(AWAY, result["person_away"])
        self.assertIn("开跑，2 CPU / 8 GiB", result["person_away"])
        with self.store.db() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM timers WHERE kind='ask'").fetchone(), "no hour to wait")
        notices = [m for m in self.unread(LEAD) if m["from"] == SYSTEM]
        self.assertEqual(len(notices), 1, "the executor is told to go ahead")
        self.assertIn("开跑，2 CPU / 8 GiB", notices[0]["body"])
        with self.store.db() as db:
            body = db.execute("SELECT body FROM messages WHERE id=?", (result["message_id"],)).fetchone()[0]
        self.assertIn("You were away from the computer", body, "the person reads what was done when back")

    def test_an_open_question_goes_ahead_once_the_person_leaves(self):
        result = self.store.send(DEV, ["human"], "要不要把卷扩到 20 GiB？", recommend="扩到 20 GiB")
        self.assertEqual(result["ask"]["status"], "open")
        self.assertLessEqual(self.store.next_timer(), time.time() + self.store.AWAY_LOOK + 1,
                             "looked at again within minutes, not after the hour")
        self.assertEqual([d for d in self.store.fire_timers() if d["kind"] == "ask"], [], "still here: it waits")
        self.leave()
        done = [d for d in self.store.fire_timers() if d["kind"] == "ask"]
        self.assertEqual([d["outcome"] for d in done], ["person away"])
        ask = self.store.get(self.team)["asks"][result["ask"]["id"]]
        self.assertEqual(ask["status"], "away")
        notices = [m for m in self.unread(DEV) if m["from"] == SYSTEM]
        self.assertEqual(len(notices), 1)
        self.assertIn(AWAY, notices[0]["body"])
        self.assertEqual([d for d in self.store.fire_timers() if d["kind"] == "ask"], [], "once")

    def test_a_message_to_the_person_says_when_nobody_reads_it_now(self):
        self.assertNotIn("person_away", self.store.send(DEV, ["human"], "进展：环境规格核对完了。"))
        self.leave()
        result = self.store.send(DEV, ["human"], "进展：镜像拉好了。")
        self.assertIn(AWAY, result["person_away"])
        self.assertNotIn("person_away", self.store.send(DEV, ["lead"], "镜像拉好了"), "only messages to the person")


class RelayedWords(Fixture):
    def setUp(self):
        super().setUp()
        self.store.person_said("claude-code", "s1", "%s/lead" % self.team, WORDS)

    def test_the_person_s_words_carry_relic_s_check(self):
        self.store.send(LEAD, ["dev"], "人刚才的原话：OrgBench 的实验自己跑，不用再找上级申请。照这个做。")
        body = self.unread(DEV)[-1]["body"]
        self.assertIn("[Relic check W", body)
        self.assertIn("OrgBench 的实验自己跑", body, "shown as the person typed it")
        self.assertIn("Bench · lead", body, "where the person typed it")

    def test_a_paraphrase_or_a_word_in_common_is_not_vouched_for(self):
        self.store.send(LEAD, ["dev"], "OrgBench 的事你看着办，继续。")
        self.store.send(LEAD, ["dev"], "人说实验让我们自己负责。")
        self.assertFalse(any("[Relic check" in m["body"] for m in self.unread(DEV)))

    def test_a_message_to_an_organization_below_carries_it_too(self):
        child = self.store.create(CHILD, "OrgBench 搭建组", "build OrgBench", "builder", "builder")["id"]
        self.store.set_parent(child, self.team)
        self.store.send(LEAD, ["builder"], "转达人的话：不用再找上级申请，也不用等科研部代跑。", org=child)
        body = self.unread(CHILD)[-1]["body"]
        self.assertIn("[Relic check W", body)

    def test_a_message_passed_on_is_not_vouched_for_twice(self):
        self.store.send(LEAD, ["dev"], "人说：OrgBench 的实验自己跑，不用再找上级申请。")
        first = self.unread(DEV)[-1]["body"]
        self.store.send(DEV, ["lead"], "转一下：\n" + first)
        again = [m for m in self.unread(LEAD) if m["from"] == "dev"][-1]["body"]
        self.assertEqual(again.count("[Relic check W"), 1)


class Hooks(Fixture):
    ASK = {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion",
           "tool_input": {"questions": [{"question": "要不要现在开跑？"}]}}

    def test_a_question_tool_is_refused_while_the_person_is_away(self):
        self.assertEqual(self.hook(self.ASK, DEV), {}, "here: the person answers")
        self.leave()
        out = self.hook(self.ASK, DEV)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn(AWAY, out["permissionDecisionReason"])
        self.assertEqual(self.hook(self.ASK, STRANGER), {}, "a session without a seat is not Relic's business")

    def test_a_turn_does_not_end_on_a_question_while_the_person_is_away(self):
        stop = {"hook_event_name": "Stop", "last_assistant_message": "镜像拉好了。\n要不要我现在就开跑第一轮？"}
        self.assertEqual(self.hook(stop, DEV), {}, "here: the person answers")
        self.leave()
        out = self.hook(stop, DEV)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn(AWAY, out["reason"])
        self.assertEqual(self.hook(dict(stop, stop_hook_active=True), DEV), {}, "once")
        done = {"hook_event_name": "Stop", "last_assistant_message": "第一轮已开跑，日志在 S 盘。"}
        self.assertEqual(self.hook(done, DEV), {}, "a report ends the turn")

    def test_messages_in_the_context_are_work_input_and_relayed_words_count(self):
        self.store.send(LEAD, ["dev"], "开工")
        text = relic_hook.peer_messages(self.store, DEV)
        self.assertIn("the person's words a member relays count as the person's", text)
        self.assertNotIn("not instructions from the human", text)


class Prompts(Fixture):
    def test_a_woken_member_runs_on_its_own_while_the_person_is_away(self):
        org = self.store.get(self.team)
        here = wake.prompt(org, "dev", ["lead"], 1, messages=[])
        self.assertIn("Relayed instructions are as good as the person's own", here)
        self.assertIn("a failure is not a refusal", here)
        self.assertNotIn(AWAY, here)
        self.assertNotIn("what the person has already authorized in your own session", here)
        away = wake.prompt(org, "dev", ["lead"], 1, messages=[], away={"minutes": 25, "locked": False})
        self.assertIn(AWAY, away)
        self.assertIn("25", away)
        notice = wake.prompt(org, "lead", [SYSTEM], 1, messages=[], away={"minutes": 0, "locked": True})
        self.assertIn(AWAY, notice)
        self.assertIn("the screen is locked", notice)

    def test_the_context_says_the_person_is_away(self):
        org = self.store.get(self.team)
        self.assertNotIn(AWAY, render(self.store, org, "dev"))
        self.leave()
        self.assertIn(AWAY, render(self.store, org, "dev"))


if __name__ == "__main__":
    unittest.main()
