"""Codex chats open in the Codex desktop app: found through the app's tool pipe, given their turn there, followed to
the end; and the runner chooses that route only for a chat the app has loaded. The pipe is replaced by fakes that
answer the way the app's codex_app tools do (read_thread: thread.status.type and turns newest first)."""
import importlib.util
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

from relic_core import desktop, runner, wake  # noqa: E402
from relic_core.store import Store  # noqa: E402

spec = importlib.util.spec_from_file_location("relic_run", ROOT / "scripts" / "relic_run.py")
relic_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relic_run)

THREAD = "01a0e17f-0000-7000-8000-000000000001"
LEAD = "lead-session"


def thread(status, turns=()):
    return {"thread": {"id": THREAD, "status": {"type": status}}, "turns": list(turns)}


def turn(tid, status, reply="", person=False):
    """A turn as read_thread shows it: one Relic started opens with the send_message_to_thread output, one the person
    typed opens with their message."""
    first = ({"type": "userMessage", "content": [{"type": "text", "text": "what about Michigan?"}]} if person else
             {"type": "functionCallOutput", "id": "c1", "name": "send_message_to_thread", "namespace": "codex_app"})
    items = [first] + ([{"type": "agentMessage", "text": reply}] if reply else [])
    return {"id": tid, "status": status, "error": None, "items": items}


class FakeApp:
    """read() answers from a script of read_thread results; send() records the prompt."""

    def __init__(self, reads, send_error=None):
        self.reads, self.sent, self.send_error = list(reads), [], send_error

    def read(self, thread_id, turns=1, host="local", caller=None):
        value = self.reads.pop(0) if len(self.reads) > 1 else self.reads[0]
        if isinstance(value, Exception):
            raise value
        return value

    def send(self, thread_id, prompt, host="local", caller=None):
        self.sent.append((thread_id, prompt))  # counted even when the answer is lost: the app may have it
        if self.send_error:
            raise self.send_error
        return {"ok": True}


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


class RunTurn(unittest.TestCase):
    def run_turn(self, app, **kw):
        clock = Clock()
        return desktop.run_turn(app, THREAD, "[Relic auto-wake] read your inbox", sleep=clock.sleep, clock=clock, **kw)

    def test_turn_in_the_app_is_followed_to_its_reply(self):
        app = FakeApp([thread("idle", [turn("t1", "completed", "old")]),
                       thread("active", [turn("t1", "completed", "old")]),
                       thread("active", [turn("t2", "inProgress")]),
                       thread("idle", [turn("t2", "completed", "Read it; replied to lead.")])])
        self.assertEqual(self.run_turn(app), ("Read it; replied to lead.", False))
        self.assertEqual(app.sent, [(THREAD, "[Relic auto-wake] read your inbox")])

    def test_running_chat_is_not_interrupted(self):
        app = FakeApp([thread("active", [turn("t1", "inProgress")])])
        with self.assertRaises(desktop.DesktopError) as caught:
            self.run_turn(app)
        self.assertIn(desktop.BUSY, str(caught.exception))
        self.assertTrue(wake.no_turn(str(caught.exception)))
        self.assertEqual(app.sent, [])

    def test_failed_turn_is_reported_as_failed(self):
        app = FakeApp([thread("idle"), thread("idle", [turn("t2", "failed")])])
        self.assertEqual(self.run_turn(app)[1], True)

    def test_a_turn_the_person_starts_meanwhile_is_not_the_reply(self):
        app = FakeApp([thread("idle", [turn("t1", "completed", "old")]),
                       thread("idle", [turn("t2", "completed", "Michigan has two good fits.", person=True),
                                       turn("t1", "completed", "old")]),
                       thread("idle", [turn("t3", "completed", "Replied to lead through Relic."),
                                       turn("t2", "completed", "Michigan has two good fits.", person=True)])])
        self.assertEqual(self.run_turn(app), ("Replied to lead through Relic.", False))

    def test_reads_that_fail_while_the_turn_runs_are_waited_out(self):
        error = desktop.DesktopError("read_thread: Codex app tool request failed")
        app = FakeApp([thread("idle"), error, error, thread("idle", [turn("t2", "completed", "done")])])
        self.assertEqual(self.run_turn(app), ("done", False))

    def test_unconfirmed_prompt_is_followed_and_never_sent_again(self):
        lost = desktop.Uncertain("the Codex app did not answer on its tool pipe")
        app = FakeApp([thread("idle"), thread("idle", [turn("t2", "completed", "done")])], send_error=lost)
        self.assertEqual(self.run_turn(app), ("done", False))
        app = FakeApp([thread("idle"), thread("idle")], send_error=lost)
        reply, failed = self.run_turn(app, start_wait=30)
        self.assertIn("not sent again", reply)
        self.assertFalse(failed)
        self.assertEqual(len(app.sent), 1)

    def test_refused_prompt_is_left_for_a_retry(self):
        app = FakeApp([thread("idle")], send_error=desktop.DesktopError("send_message_to_thread: thread not found"))
        with self.assertRaises(desktop.DesktopError) as caught:
            self.run_turn(app)
        self.assertNotIsInstance(caught.exception, desktop.Uncertain)

    def test_a_prompt_is_never_sent_twice(self):
        app = FakeApp([thread("idle", [turn("t1", "completed")]), thread("idle", [turn("t1", "completed")])])
        reply, failed = self.run_turn(app, start_wait=30)
        self.assertIn("no turn started", reply)
        self.assertFalse(failed)
        app = FakeApp([thread("idle"), desktop.DesktopError("pipe closed")])
        reply, failed = self.run_turn(app)  # unreadable for longer than `blind`
        self.assertIn("lost sight", reply)
        self.assertEqual(len(app.sent), 1)


class Pipe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        os.environ.pop(desktop.PIPE_ENV, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def find(self, serving, names=()):
        asked = []

        def serves(pipe, timeout=3.0):
            asked.append(pipe)
            return pipe in serving

        with mock.patch.object(runner, "WINDOWS", True), mock.patch.object(desktop, "serves_codex_app", serves):
            return desktop.find_pipe(listdir=lambda _: list(names)), asked

    def test_pipe_found_by_probing_is_remembered(self):
        app = desktop.PIPE_DIR + "codex-browser-use-bbb"
        pipe, asked = self.find({app}, ["codex-ipc", "codex-computer-use-x", "codex-browser-use-aaa",
                                        "codex-browser-use-bbb", "codex-browser-use\\nested"])
        self.assertEqual(pipe, app)
        self.assertEqual(asked, [desktop.PIPE_DIR + "codex-browser-use-aaa", app])  # other pipes are never written to
        self.assertEqual(json.loads(desktop.cache_path().read_text())["pipe"], app)
        pipe, asked = self.find({app}, ["codex-browser-use-aaa", "codex-browser-use-bbb"])
        self.assertEqual(asked, [app])  # the remembered pipe is tried first

    def test_newer_pipe_names_are_probed_too(self):
        app = desktop.PIPE_DIR + "codex-app-tools-459859c0-4acd"
        pipe, asked = self.find({app}, ["codex-ipc", "codex-app-tools-459859c0-4acd"])
        self.assertEqual((pipe, asked), (app, [app]))

    def test_pipe_named_by_the_app_wins(self):
        os.environ[desktop.PIPE_ENV] = desktop.PIPE_DIR + "codex-browser-use-env"
        pipe, asked = self.find({os.environ[desktop.PIPE_ENV]}, ["codex-browser-use-aaa"])
        self.assertEqual((pipe, asked), (os.environ[desktop.PIPE_ENV], [os.environ[desktop.PIPE_ENV]]))
        desktop.remember_env()
        self.assertEqual(json.loads(desktop.cache_path().read_text())["pipe"], os.environ[desktop.PIPE_ENV])

    def test_a_codex_thread_busy_with_its_own_turn_is_not_the_caller(self):
        class App(desktop.Desktop):
            tried = []

            def call(self, tool, arguments, caller):
                self.tried.append(caller)
                if caller == "busy":
                    raise desktop.DesktopError("list_threads: Codex app tool request failed")
                return {"threads": []}
        app = App(desktop.PIPE_DIR + "codex-app-tools-1")
        self.assertEqual(app.find_caller(["busy", "idle", "other"]), "idle")
        App.tried.clear()
        self.assertEqual(app.find_caller(["busy", "idle"]), "idle")
        self.assertEqual(App.tried, ["idle"])  # the one that worked is tried first next time
        desktop.remember(desktop.PIPE_DIR + "codex-app-tools-2")
        self.assertEqual(json.loads(desktop.cache_path().read_text())["caller"], "idle")  # kept beside the pipe

    def test_a_stale_or_wrong_pipe_name_never_touches_a_file(self):
        victim = Path(self.tmp.name) / "notes.txt"
        victim.write_bytes(b"precious")
        os.environ[desktop.PIPE_ENV] = str(victim)
        desktop.cache_path().write_text(json.dumps({"pipe": str(victim)}), encoding="utf-8")
        with mock.patch.object(runner, "WINDOWS", True):
            self.assertIsNone(desktop.find_pipe(listdir=lambda _: []))
        with self.assertRaises(desktop.DesktopError):
            desktop.exchange(str(victim), {"id": 1, "jsonrpc": "2.0", "method": "tools/list"})
        good = desktop.PIPE_DIR + "codex-browser-use-0f1e"
        desktop.remember(good)
        desktop.remember(str(victim))  # never recorded
        self.assertEqual(json.loads(desktop.cache_path().read_text())["pipe"], good)
        self.assertEqual(victim.read_bytes(), b"precious")
        for path in ("\\\\server\\pipe\\codex-x", "C:\\temp\\codex-y", desktop.PIPE_DIR + "codex-a\\..\\b",
                     desktop.PIPE_DIR + "other-app"):
            self.assertFalse(desktop.is_codex_pipe(path), path)
        self.assertTrue(desktop.is_codex_pipe(desktop.PIPE_DIR + "codex-browser-use-684fad04-b7d2"))

    def test_no_app_no_pipe(self):
        self.assertEqual(self.find(set(), ["codex-browser-use-aaa"])[0], None)
        with mock.patch.object(runner, "WINDOWS", False):
            self.assertIsNone(desktop.find_pipe(listdir=lambda _: ["codex-browser-use-aaa"]))

    def test_tool_results_are_parsed_and_failures_raised(self):
        app = desktop.Desktop("pipe")
        ok = {"jsonrpc": "2.0", "id": 1, "result": {"success": True, "contentItems": [
            {"type": "inputText", "text": json.dumps(thread("idle"))}]}}
        with mock.patch.object(desktop, "exchange", return_value=ok) as sent:
            self.assertEqual(desktop.status(app.read(THREAD)), "idle")
        params = sent.call_args[0][1]["params"]
        self.assertEqual((params["tool"], params["namespace"], params["arguments"]["threadId"]),
                         ("read_thread", "codex_app", THREAD))
        refused = {"jsonrpc": "2.0", "id": 1, "result": {"success": False, "contentItems": [
            {"type": "inputText", "text": "thread not found"}]}}
        with mock.patch.object(desktop, "exchange", return_value=refused):
            with self.assertRaises(desktop.DesktopError):
                app.send(THREAD, "hi")


class FakeServer:
    """runner.CodexAppServer stand-in whose thread/resume finds the chat locked by the desktop app."""

    def __init__(self, *_, **__):
        self.notifications, self.answered, self.declined = [], [], []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def request(self, method, params):
        if method == "thread/resume":
            raise RuntimeError("thread/resume: thread %s already has an active writer" % params["threadId"])
        raise AssertionError("unexpected " + method)


class Route(unittest.TestCase):
    """relic_run.run_codex: the desktop app's chats go through the app, the others through an app-server."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        self.store = Store()
        self.oid = self.store.create(LEAD, "Lab", "ship", "lead")["id"]
        self.store.add_seat(self.oid, "cody", "ui", dict(runner.default_config("codex"), surface="gui"))
        self.store.join("codex:" + THREAD, self.oid, "cody")
        self.org = self.store.get(self.oid)
        self.config = self.org["members"]["cody"]["config"]

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def run_codex(self, app, server=FakeServer):
        with mock.patch.object(runner, "find_codex", return_value="codex"), \
                mock.patch.object(runner, "CodexAppServer", server), \
                mock.patch.object(desktop, "run_turn", lambda a, t, p: ("done in the app", False)):
            return relic_run.run_codex(self.store, self.org, "cody", self.config, "wake up", False,
                                       self.tmp.name, connect=lambda: app)

    def test_chat_open_in_the_app_runs_there(self):
        def no_server(*_, **__):
            raise AssertionError("an app-server must not be started for a chat the app has open")
        session, reply, failed, _ = self.run_codex(FakeApp([thread("idle")]), server=no_server)
        self.assertEqual((session, reply, failed), ("codex:" + THREAD, "done in the app", False))

    def test_lock_found_late_still_goes_through_the_app(self):
        # the first look says the app has not loaded the chat; by the time of thread/resume it has
        app = FakeApp([thread("notLoaded"), thread("idle")])
        self.assertEqual(self.run_codex(app)[1], "done in the app")

    def test_cli_worker_never_routes_a_locked_old_thread_to_gui(self):
        self.config = dict(self.config, surface="cli")
        connect = mock.Mock(side_effect=AssertionError("CLI worker must not connect to GUI"))
        with mock.patch.object(runner, "find_codex", return_value="fake-codex"), \
                mock.patch.object(runner, "CodexAppServer", FakeServer), \
                mock.patch.object(desktop, "run_turn") as send:
            with self.assertRaisesRegex(RuntimeError, "fresh CLI session"):
                relic_run.run_codex(self.store, self.org, "cody", self.config, "task", False,
                                    self.tmp.name, connect=connect)
            connect.assert_not_called()
            send.assert_not_called()

    def test_failed_turn_in_the_app_is_reported_not_retried(self):
        with mock.patch.object(runner, "find_codex", return_value="codex"), \
                mock.patch.object(desktop, "run_turn", lambda a, t, p: ("model overloaded", True)):
            _, reply, failed, _ = relic_run.run_codex(self.store, self.org, "cody", self.config, "wake up", False,
                                                      self.tmp.name, connect=lambda: FakeApp([thread("idle")]))
        self.assertFalse(failed)  # failed would give the claim back and send the same prompt again
        self.assertIn("not sent again", reply)
        self.assertIn("model overloaded", reply)

    def test_across_dispatches_a_prompt_that_may_have_arrived_is_sent_once(self):
        sent, clock, real = [], Clock(), desktop.run_turn
        follow = lambda app, t, p, **kw: real(app, t, p, sleep=clock.sleep, clock=clock, **kw)

        def start(org_id, member, prompt, wake_from, wake_hop):
            app = FakeApp([thread("idle")], send_error=desktop.Uncertain("timed out"))
            with mock.patch.object(runner, "find_codex", return_value="codex"), \
                    mock.patch.object(desktop, "run_turn", follow):
                _, reply, failed, _ = relic_run.run_codex(self.store, self.store.get(org_id), member, self.config,
                                                          prompt, False, self.tmp.name, connect=lambda: app)
            sent.extend(app.sent)
            wake.finish(self.store, org_id, member, reply if failed else None)

        self.store.send(LEAD, ["cody"], "please review the API")
        settle, wake.SETTLE = wake.SETTLE, 0
        try:
            dispatch = lambda at: wake.dispatch(self.store, self.oid, now=at, start=start, age=lambda seat: None,
                                                retry=lambda *_: None)
            self.assertEqual(dispatch(time.time()), ["cody"])
            self.assertEqual(dispatch(time.time() + 3600), [])
        finally:
            wake.SETTLE = settle
        self.assertEqual(len(sent), 1)

    def test_chat_held_by_a_terminal_session_is_retried_later(self):
        with self.assertRaises(RuntimeError) as caught:
            self.run_codex(FakeApp([thread("notLoaded")]))
        self.assertIn(wake.IN_USE, str(caught.exception))
        with self.assertRaises(RuntimeError):
            self.run_codex(None)  # no desktop app running at all


if __name__ == "__main__":
    unittest.main()
