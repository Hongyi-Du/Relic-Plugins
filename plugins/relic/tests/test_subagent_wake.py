"""A Codex subagent that holds a seat of its own ("codex:<session>/<agent>").

Only the session that spawned it can give it input (followup_task): the Codex desktop app refuses direct input to
multi-agent v2 sub-agents, and while the app holds the subagent's thread no other process can write there (2026-11-16,
Learning's astra-systems-lead). So Relic never wakes such a seat or starts anything on its thread. Its transcript and
trajectory are its own thread's. A turn's runner, always the Relic installed last, ends by dispatching every
organization written during the turn with its own rules. Synthetic store and fake starter: no live Codex."""
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core import desktop, monitor, runner, trajectory, wake  # noqa: E402
from relic_core.store import Store, codex_parent, codex_thread  # noqa: E402

spec = importlib.util.spec_from_file_location("relic_run", ROOT / "scripts" / "relic_run.py")
relic_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relic_run)

PARENT = "codex:01a179c9-0000-7000-8000-000000000001"
CHILD = "01a179cb-0000-7000-8000-000000000002"
SUB = PARENT + "/" + CHILD
LEAD = "lead-session"


class Carriers(unittest.TestCase):
    def test_thread_and_spawning_session_of_a_carrier(self):
        self.assertEqual(codex_thread(SUB), CHILD)
        self.assertEqual(codex_parent(SUB), PARENT)
        self.assertEqual(codex_thread(PARENT), PARENT.split(":", 1)[1])
        self.assertIsNone(codex_parent(PARENT))
        for claude in ("sess-1/agent-2", "sess-1"):  # Claude Code sessions and subagents are not Codex threads
            self.assertIsNone(codex_thread(claude))
            self.assertIsNone(codex_parent(claude))
        self.assertEqual(monitor._thread(SUB), CHILD)


class SubagentSeat(unittest.TestCase):
    def setUp(self):
        platform = mock.patch.object(wake, "sys", SimpleNamespace(platform="win32", executable=sys.executable))
        platform.start()  # the Windows desktop bridge (macOS adds its own capability checks)
        self.addCleanup(platform.stop)
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        os.environ["CODEX_HOME"] = str(Path(self.tmp.name) / "codex")
        s = self.store = Store()
        self.oid = s.create(LEAD, "Learning", "research", "lead", governance="peer")["id"]
        self.config = dict(runner.default_config("codex"), surface="gui")
        s.add_seat(self.oid, "coordinator", "lead", self.config)  # the spawning session's seat, set up by the person
        s.join(PARENT, self.oid, "coordinator")
        s.add_seat(self.oid, "systems", "source writer")  # the subagent's own seat
        s.join(SUB, self.oid, "systems")
        self.started, self.retries = [], []
        self.settle, wake.SETTLE = wake.SETTLE, 0

    def tearDown(self):
        wake.SETTLE = self.settle
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def start(self, org_id, member, prompt, wake_from, wake_hop, wake_message_ids=None):
        self.started.append(member)
        runner.write_state(org_id, member, {"status": "running", "started": time.time(), "pid": os.getpid()})

    def dispatch(self, at=None):
        def no_app():
            raise AssertionError("waking a subagent never asks the desktop app: it refuses input to sub-agents")
        with mock.patch.object(desktop, "connect", no_app):
            return wake.dispatch(self.store, self.oid, now=at or time.time(), start=self.start, age=lambda seat: None,
                                 retry=lambda org_id, delay: self.retries.append(delay))

    def test_it_is_never_woken_even_when_set_up(self):
        self.store.send(PARENT, ["systems"], "wire the new tool")
        self.assertEqual(self.store.seat_config(self.oid, "systems"), {})  # it does not inherit its spawner's config
        self.assertEqual(self.dispatch(), [])
        self.store.set_seat_fields(self.oid, "systems", config=self.config)  # even a seat someone set up by hand
        self.assertEqual(self.dispatch(), [])
        self.assertEqual(self.started, [])
        self.assertEqual(self.retries, [])  # nothing scheduled, nothing counted as a failure
        self.assertEqual(self.store.events(self.oid, ["member.woken", "member.wake_failed"]), [])

    def test_the_session_that_spawned_it_is_still_woken(self):
        self.store.send(SUB, ["coordinator"], "wired; tests pass")
        self.assertEqual(self.dispatch(), ["coordinator"])

    def test_a_turn_started_for_it_by_hand_starts_nothing(self):
        def nothing(*_, **__):
            raise AssertionError("nothing may be started on a subagent's thread")
        with mock.patch.object(runner, "CodexAppServer", nothing), mock.patch.object(desktop, "run_turn", nothing), \
                mock.patch.object(runner, "find_codex", return_value="codex"):
            with self.assertRaisesRegex(RuntimeError, "only that session gives it a turn") as caught:
                relic_run.run_codex(self.store, self.store.get(self.oid), "systems", self.config, "wake up", False,
                                    self.tmp.name, connect=nothing)
        self.assertIn(PARENT, str(caught.exception))
        self.assertIn(wake.SUBAGENT_INPUT, str(caught.exception))
        # no turn reached the member: its wakers (an older copy may still wake it) get no failure receipt
        self.assertTrue(wake.no_turn(str(caught.exception)))
        self.assertFalse(relic_run.needs_receipt("codex", str(caught.exception)))
        self.assertTrue(wake.no_turn("send_message_to_thread: " + wake.SUBAGENT_INPUT))  # the app's own refusal

    def test_a_turn_ends_by_dispatching_what_was_written_meanwhile(self):
        # The runner is the Relic installed last; an older copy that wrote a message (a Codex plugin waiting for the
        # person's hook trust) may lack its rules. The turn's end dispatches again with them.
        other = self.store.create("boss-session", "Elsewhere", "other work", "boss")["id"]
        self.store.add_seat(other, "peer", "helper")
        self.store.add_seat(self.oid, "worker", "builder", runner.default_config("codex"))
        self.store.join("codex:th-worker", self.oid, "worker")
        prompt = Path(self.tmp.name) / "prompt.txt"
        prompt.write_text("wake up", encoding="utf-8")
        dispatched = []

        def turn(store, org, member, config, text, new, cwd):
            store.send(PARENT, ["systems"], "next step")  # in Learning, during the turn
            store.send("boss-session", ["peer"], "unrelated work elsewhere")
            return "codex:th-worker", "done", False, None
        argv = ["relic_run.py", "--org", self.oid, "--member", "worker", "--prompt-file", str(prompt)]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(relic_run, "run_codex", turn), \
                mock.patch.object(wake, "dispatch", lambda store, org_id, **kw: dispatched.append(org_id)):
            relic_run.main()
        self.assertEqual(dispatched, [self.oid, other])
        self.assertEqual(runner.run_state(self.oid, "worker")["status"], "done")

    def test_its_transcript_and_trajectory_are_its_own_thread(self):
        rollout = Path(os.environ["CODEX_HOME"]) / "sessions" / "2026" / "11" / "16"
        rollout.mkdir(parents=True)
        mine = rollout / ("rollout-2026-11-16T05-07-04-%s.jsonl" % CHILD)
        mine.write_text("{}\n", encoding="utf-8")
        (rollout / ("rollout-2026-11-16T05-00-00-%s.jsonl" % PARENT.split(":", 1)[1])).write_text("{}\n", encoding="utf-8")
        seat = self.store.get(self.oid)["members"]["systems"]
        self.assertEqual(wake.transcripts(seat), [mine])
        self.assertEqual(trajectory.locate(SUB), ("codex", CHILD, mine))


if __name__ == "__main__":
    unittest.main()
