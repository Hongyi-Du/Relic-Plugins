"""A Claude Desktop seat is woken through its live session's own inbox (no CLI login, no model call); the CLI router
is only the fallback when no live session can be reached."""
import hashlib
import json
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

from relic_core import claude_desktop as gui, runner, wake
from relic_core.store import Store

NAME = "SCOPE development and pilot 2026-10-19 · claude-reviewer"
SID = "99bb1e11-21c6-437f-9933-f07432b1a7f7"
PIPE = "\\\\.\\pipe\\LOCAL\\cc-msg-1a2B3c"
TOKEN = "0123456789abcdef0123456789abcdef"


class InboxDelivery(unittest.TestCase):
    def setUp(self):
        native = mock.patch.object(gui, "sys", SimpleNamespace(platform="win32", executable=sys.executable))
        native.start()
        self.addCleanup(native.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config_dir = Path(self.tmp.name) / "claude-config"
        (self.config_dir / "sessions").mkdir(parents=True)
        env = mock.patch.dict(os.environ, {"RELIC_HOME": str(Path(self.tmp.name) / "relic"),
                                           "CLAUDE_CONFIG_DIR": str(self.config_dir),
                                           "CLAUDE_CODE_ENTRYPOINT": "claude-desktop"})
        env.start()
        self.addCleanup(env.stop)
        self.store = Store()
        self.oid = self.store.create("lead", "SCOPE development and pilot 2026-10-19", "transport", "lead")["id"]
        self.config = dict(runner.default_config("claude-code"), surface="gui", model="sonnet", effort="high")
        self.store.add_seat(self.oid, "claude-reviewer", config=self.config)
        self.store.join(SID, self.oid, "claude-reviewer")
        self.org = self.store.get(self.oid)
        self.folder = Path(self.tmp.name) / "request"
        self.folder.mkdir()
        self.request = {"org_id": self.oid, "member": "claude-reviewer", "carrier": SID, "expected": NAME,
                        "nonce": "abc123", "prompt": "Exact\n payload 中文", "created": time.time()}
        self.writes = []

    def register(self, pid=None, session=SID, name=NAME, pipe=PIPE, key=True, token=TOKEN):
        pid = os.getpid() if pid is None else pid
        record = {"pid": pid, "sessionId": session, "name": name, "messagingSocketPath": pipe, "kind": "interactive"}
        (self.config_dir / "sessions" / ("%d.json" % pid)).write_text(json.dumps(record), encoding="utf-8")
        if key:
            (self.config_dir / "sessions" / gui.key_name(pid, pipe)).write_text(
                json.dumps({"peerToken": token, "procStart": "x", "pidDomain": "win"}), encoding="utf-8")
        return record

    def writer(self, socket_path, data):
        self.writes.append((socket_path, data))

    def frames(self):
        self.assertEqual(len(self.writes), 1)
        path, data = self.writes[0]
        return path, [json.loads(line) for line in data.decode("utf-8").splitlines()]

    def test_peer_key_name_follows_the_canonical_pipe_path(self):
        canonical = "\\\\.\\pipe\\local\\cc-msg-1a2b3c"
        expected = "7.%s.key" % hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.assertEqual(gui.key_name(7, PIPE), expected)
        self.assertEqual(gui.key_name(7, "//?/pipe/local/CC-MSG-1A2B3C"), expected)
        self.assertNotEqual(gui.key_name(8, PIPE), expected)

    def test_one_auth_line_then_the_exact_request_as_a_user_message(self):
        self.register()
        self.assertEqual(gui.inbox_route(self.request, self.config, self.folder, writer=self.writer), "sent")
        path, frames = self.frames()
        self.assertEqual(path, PIPE)
        self.assertEqual(frames[0], {"type": "auth", "token": TOKEN})
        self.assertEqual(frames[1], {"type": "user", "message": {"role": "user", "content": gui.payload(self.request)}})
        self.assertIn(gui.marker(self.request), frames[1]["message"]["content"])
        delivery = gui._read(self.folder / "delivery.json")
        self.assertEqual((delivery["outcome"], delivery["via"], delivery["pid"]), ("sent", "inbox", os.getpid()))

    def test_session_found_by_its_title_when_its_id_changed(self):
        self.register(session="another-session-id")
        self.assertEqual(gui.inbox_route(self.request, self.config, self.folder, writer=self.writer), "sent")
        self.assertEqual(self.frames()[1][0]["token"], TOKEN)

    def test_the_only_key_of_the_process_is_used_when_the_path_hash_differs(self):
        record = self.register(key=False)
        (self.config_dir / "sessions" / ("%d.%s.key" % (record["pid"], "f" * 64))).write_text(
            json.dumps({"peerToken": TOKEN}), encoding="utf-8")
        self.assertEqual(gui.inbox_route(self.request, self.config, self.folder, writer=self.writer), "sent")

    def test_nothing_is_sent_without_one_live_session_and_its_key(self):
        cases = {
            "no session": lambda: None,
            "dead process": lambda: self.register(pid=2 ** 22 + 7),
            "no key": lambda: self.register(key=False),
            "malformed key": lambda: self.register(token="not-a-token"),
            "two sessions with the title": lambda: (self.register(session="a"),
                                                    self.register(pid=os.getppid(), session="b")),
        }
        for label, arrange in cases.items():
            with self.subTest(label):
                for path in (self.config_dir / "sessions").iterdir():
                    path.unlink()
                arrange()
                with self.assertRaises(gui.TransportError) as caught:
                    gui.inbox_route(self.request, self.config, self.folder, writer=self.writer)
                self.assertEqual(caught.exception.outcome, "unavailable")
                self.assertFalse(caught.exception.possible)
                self.assertEqual(self.writes, [])

    def test_a_busy_session_waits_without_interjecting_or_the_cli_router(self):
        record = self.register()
        record["status"] = "busy"
        (self.config_dir / "sessions" / ("%d.json" % record["pid"])).write_text(json.dumps(record), encoding="utf-8")
        route = mock.Mock()
        with mock.patch.object(gui, "write_inbox", self.writer), mock.patch.object(gui, "route", route),                 self.assertRaises(gui.TransportError) as caught:
            gui.run_turn(self.store, self.org, "claude-reviewer", self.config, "do exact task", False, self.tmp.name,
                         timeout=0)
        self.assertEqual(caught.exception.outcome, "unavailable")
        self.assertTrue(wake.no_turn(caught.exception))  # the wake-up waits a gap and tries again, quietly
        route.assert_not_called()
        self.assertEqual(self.writes, [])
        self.assertEqual(gui.blocking(self.store, SID), [])  # nothing was sent: the session is not held
        record["status"] = "idle"
        (self.config_dir / "sessions" / ("%d.json" % record["pid"])).write_text(json.dumps(record), encoding="utf-8")
        with mock.patch.object(gui, "write_inbox", self.writer), self.assertRaises(gui.TransportError) as sent:
            gui.run_turn(self.store, self.org, "claude-reviewer", self.config, "do exact task", False, self.tmp.name,
                         timeout=0)
        self.assertEqual(sent.exception.outcome, "sent")
        self.assertEqual(len(self.writes), 1)

    def test_an_unreachable_inbox_falls_back_to_the_cli_router_once(self):
        route = mock.Mock(return_value="sent")
        with mock.patch.object(gui, "route", route):
            self.assertEqual(gui.deliver(self.request, self.config, self.folder), "sent")
        route.assert_called_once_with(self.request, self.config, self.folder)

    def test_both_routes_unavailable_says_why_for_each(self):
        route = mock.Mock(side_effect=gui.TransportError("unavailable", "the CLI is not signed in"))
        with mock.patch.object(gui, "route", route), self.assertRaises(gui.TransportError) as caught:
            gui.deliver(self.request, self.config, self.folder)
        self.assertEqual(caught.exception.outcome, "unavailable")
        self.assertIn("no live Claude Code session", str(caught.exception))
        self.assertIn("the CLI is not signed in", str(caught.exception))

    def test_a_write_that_may_have_reached_the_session_is_never_sent_again(self):
        self.register()
        failing = mock.Mock(side_effect=gui.TransportError("unknown", "broken pipe", True))
        route = mock.Mock()
        with mock.patch.object(gui, "write_inbox", failing), mock.patch.object(gui, "route", route):
            with self.assertRaises(gui.TransportError) as caught:
                gui.deliver(self.request, self.config, self.folder)
        self.assertEqual(caught.exception.outcome, "unknown")
        self.assertTrue(caught.exception.possible)
        route.assert_not_called()

    def test_an_inbox_that_is_gone_fails_at_once_and_a_busy_one_is_tried_again(self):
        sleeps = []
        with self.assertRaises(gui.TransportError) as caught:
            gui.write_inbox(str(Path(self.tmp.name) / "missing" / "socket"), b"x", attempts=3, sleep=sleeps.append)
        self.assertEqual(caught.exception.outcome, "unavailable")
        self.assertEqual(sleeps, [])

        class Busy(OSError):
            winerror = 231
        stream = mock.Mock(spec=["write", "close"])
        opened = mock.Mock(side_effect=[Busy("busy"), Busy("busy"), stream])
        with mock.patch.object(gui, "_open_inbox", opened):
            gui.write_inbox(PIPE, b"frames", attempts=3, sleep=sleeps.append)
        stream.write.assert_called_once_with(b"frames")
        stream.close.assert_called_once_with()
        self.assertEqual(len(sleeps), 2)
        with mock.patch.object(gui, "_open_inbox", mock.Mock(side_effect=Busy("busy"))),                 self.assertRaises(gui.TransportError) as caught:
            gui.write_inbox(PIPE, b"frames", attempts=2, sleep=sleeps.append)
        self.assertEqual(caught.exception.outcome, "unavailable")
        self.assertFalse(caught.exception.possible)

    def test_a_failed_write_may_have_delivered_and_still_closes_the_inbox(self):
        stream = mock.Mock(spec=["write", "close"])
        stream.write.side_effect = BrokenPipeError("gone")
        with mock.patch.object(gui, "_open_inbox", return_value=stream),                 self.assertRaises(gui.TransportError) as caught:
            gui.write_inbox(PIPE, b"frames")
        self.assertEqual(caught.exception.outcome, "unknown")
        self.assertTrue(caught.exception.possible)
        stream.close.assert_called_once_with()

    def test_a_test_run_never_reads_the_persons_own_registry(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("CLAUDE_CONFIG_DIR")
            self.assertIsNone(gui.sessions_dir())
            with self.assertRaises(gui.TransportError) as caught:
                gui.inbox_route(self.request, self.config, self.folder, writer=self.writer)
            self.assertEqual(caught.exception.outcome, "unavailable")
            os.environ["CLAUDE_CONFIG_DIR"] = str(Path.home() / ".claude")
            self.assertIsNone(gui.sessions_dir())
        self.assertEqual(self.writes, [])

    def test_a_wake_goes_through_the_inbox_and_waits_for_the_sessions_stop(self):
        self.register()
        with mock.patch.object(gui, "write_inbox", self.writer), \
                mock.patch.object(gui, "route", side_effect=AssertionError("the CLI router must not run")):
            with self.assertRaises(gui.TransportError) as caught:
                gui.run_turn(self.store, self.org, "claude-reviewer", self.config, "do exact task", False,
                             self.tmp.name, timeout=0)
        # Delivered, but not complete until the session's own Stop receipt: never sent twice.
        self.assertEqual(caught.exception.outcome, "sent")
        self.assertTrue(caught.exception.possible)
        content = self.frames()[1][1]["message"]["content"]
        self.assertIn("do exact task", content)
        with self.assertRaises(gui.TransportError) as again:
            gui.run_turn(self.store, self.org, "claude-reviewer", self.config, "do exact task", False,
                         self.tmp.name, timeout=0)
        self.assertEqual(again.exception.outcome, "blocked")
        self.assertEqual(len(self.writes), 1)


if __name__ == "__main__":
    unittest.main()
