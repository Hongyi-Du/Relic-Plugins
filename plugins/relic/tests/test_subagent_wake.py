"""A Codex subagent that holds a seat of its own ("codex:<session>/<agent>").

The session that spawned it drives it with its own tools. Once the Codex desktop app has loaded the subagent's thread,
nothing else can write there: the spawning session, running its turns in a Relic runner, then fails with "already has
an active writer" (2026-11-16, Learning's astra-systems-lead). Relic then gives the subagent its turn through the app,
the thread's writer, and nowhere else: a thread the app does not hold is left to the spawning session, and no second
writer is ever started on it. Synthetic store, a fake app pipe and a fake starter: no live Codex."""
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

from app import overview  # noqa: E402
from relic_core import desktop, monitor, runner, trajectory, wake  # noqa: E402
from relic_core.store import Store, codex_parent, codex_thread  # noqa: E402

spec = importlib.util.spec_from_file_location("relic_run", ROOT / "scripts" / "relic_run.py")
relic_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relic_run)

PARENT = "codex:01a179c9-0000-7000-8000-000000000001"
CHILD = "01a179cb-0000-7000-8000-000000000002"
SUB = PARENT + "/" + CHILD
LEAD = "lead-session"


class App:
    """The app's codex_app tools: read_thread answers with the status the test sets; send records the prompt."""

    def __init__(self, status):
        self.status, self.reads = status, []

    def read(self, thread_id, turns=1, host="local", caller=None, timeout=30.0):
        self.reads.append((thread_id, caller, timeout))
        return {"thread": {"id": thread_id, "status": {"type": self.status}}, "turns": []}


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
        s.add_seat(self.oid, "systems", "source writer")  # the subagent's own seat: nobody set it up
        s.join(SUB, self.oid, "systems")
        self.started, self.retries = [], []
        self.settle, wake.SETTLE = wake.SETTLE, 0
        wake._subagent_looks.clear()

    def tearDown(self):
        wake.SETTLE = self.settle
        wake._subagent_looks.clear()
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def start(self, org_id, member, prompt, wake_from, wake_hop, wake_message_ids=None):
        self.started.append((member, wake_from))
        runner.write_state(org_id, member, {"status": "running", "started": time.time(), "pid": os.getpid()})

    def dispatch(self, app, at=None):
        with mock.patch.object(desktop, "connect", return_value=app):
            return wake.dispatch(self.store, self.oid, now=at or time.time(), start=self.start, age=lambda seat: None,
                                 retry=lambda org_id, delay: self.retries.append(delay))

    def test_its_turns_start_like_the_session_that_spawned_it(self):
        self.assertEqual(self.store.seat_config(self.oid, "systems"), self.config)
        self.assertEqual(self.store.config_source(self.oid, "systems")[1], "coordinator")
        configs = overview._configs([self.store.get(self.oid)], {})
        self.assertEqual(configs[(self.oid, "systems")], self.config)

    def test_held_by_the_desktop_app_it_is_woken_there(self):
        self.store.send(PARENT, ["systems"], "wire the new tool")
        app = App("idle")
        self.assertEqual(self.dispatch(app), ["systems"])
        self.assertEqual(self.started, [("systems", ["coordinator"])])
        self.assertEqual(app.reads, [(CHILD, CHILD, wake.SUBAGENT_TIMEOUT)])  # its own thread, asked briefly

    def test_not_held_by_the_app_it_is_left_to_the_session_that_spawned_it(self):
        self.store.send(PARENT, ["systems"], "wire the new tool")
        for app in (App("notLoaded"), None):
            wake._subagent_looks.clear()
            self.assertEqual(self.dispatch(app), [])
        self.assertEqual(self.started, [])
        self.assertEqual(self.retries, [])  # nothing scheduled, nothing counted as a failure
        self.assertEqual(self.store.events(self.oid, ["member.woken", "member.wake_failed"]), [])

    def test_a_look_at_the_app_is_reused_for_a_minute(self):
        self.store.send(PARENT, ["systems"], "wire the new tool")
        t = time.time()
        app = App("notLoaded")
        self.assertEqual(self.dispatch(app, t), [])
        self.assertEqual(self.dispatch(app, t + 10), [])
        self.assertEqual(len(app.reads), 1)
        app.status = "idle"
        self.assertEqual(self.dispatch(app, t + wake.SUBAGENT_LOOK + 1), ["systems"])

    def test_its_turn_runs_in_the_app_on_its_own_thread(self):
        ran = []

        def in_app(app, thread, prompt):
            ran.append(thread)
            return "wired; replied to coordinator", False

        def no_server(*_, **__):
            raise AssertionError("a subagent's thread never gets a second writer")
        with mock.patch.object(runner, "CodexAppServer", no_server), mock.patch.object(desktop, "run_turn", in_app):
            session, reply, failed, _ = relic_run.run_codex(self.store, self.store.get(self.oid), "systems",
                                                           self.config, "wake up", False, self.tmp.name,
                                                           connect=lambda: App("idle"))
        self.assertEqual((session, reply, failed), (SUB, "wired; replied to coordinator", False))
        self.assertEqual(ran, [CHILD])

    def test_no_turn_anywhere_else_when_the_app_does_not_hold_it(self):
        def no_server(*_, **__):
            raise AssertionError("a subagent's thread never gets a second writer")
        for app in (App("notLoaded"), None):
            with self.subTest(app=app), mock.patch.object(runner, "CodexAppServer", no_server), \
                    mock.patch.object(runner, "find_codex", return_value="codex"):
                with self.assertRaisesRegex(desktop.DesktopError, "does not hold"):
                    relic_run.run_codex(self.store, self.store.get(self.oid), "systems", self.config, "wake up",
                                        False, self.tmp.name, connect=lambda: app)

    def test_a_turn_ends_by_dispatching_what_was_written_meanwhile(self):
        # The runner is the Relic installed last; an older copy that wrote a message (a Codex plugin waiting for the
        # person's hook trust) does not know a subagent can be woken. The turn's end dispatches again with its rules.
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
