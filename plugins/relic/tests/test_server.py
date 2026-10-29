"""server.py as a lead and its relic:member subagents use it: they share one server process, so an inbox call waiting
for a message must hold up nobody; a cancelled or abandoned wait must leave the messages unread; and an update of
relic_core must still be picked up while a member waits."""
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core.store import Store  # noqa: E402
from relic_core import api  # noqa: E402
from relic_core.process import creation_flags  # noqa: E402
import server as transport  # noqa: E402

# a lead and two of its subagents, named the way the hook names their actors
LEAD, ANA, BOB = "lead-session", "lead-session/agent-ana", "lead-session/agent-bob"
WAIT = 30  # seconds an inbox call below asks to wait
QUICK = 5.0  # seconds within which a call is answered while somebody else waits


class Server:
    """One server.py process with a reader thread, so its replies may come in any order."""

    def __init__(self, script, home):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("RELIC_", "CODEX_", "CLAUDE_"))
               and k not in ("CLAUDECODE", "PLUGIN_ROOT")}
        env.update(RELIC_HOME=str(home), RELIC_ORG_HOME=str(home / "organization"),
                   CODEX_HOME=str(home / "codex"), CLAUDE_CONFIG_DIR=str(home / "claude"),
                   PYTHONDONTWRITEBYTECODE="1")
        self.errors = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        self.proc = subprocess.Popen([sys.executable, "-X", "utf8", str(Path(__file__).with_name("server_fixture.py")),
                                      str(script)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=self.errors, text=True, encoding="utf-8",
                                     env=env, creationflags=creation_flags())
        self.lines, self.seen, self.closed, self.seq = queue.Queue(), [], False, 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.proc.stdout:
            self.lines.put(json.loads(line))
        self.lines.put(None)  # the server closed its output

    def write(self, message):
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params=None):
        self.seq += 1
        self.write({"jsonrpc": "2.0", "id": self.seq, "method": method, "params": params or {}})
        return self.seq

    def tool(self, which, actor, /, **arguments):  # positional-only: a tool may take an argument called name
        return self.request("tools/call", {"name": which, "arguments": dict(arguments, actor=actor)})

    def drain(self, timeout):
        """Read what arrives within timeout seconds (all of it once the server has closed its output)."""
        deadline = time.monotonic() + timeout
        while not self.closed and time.monotonic() < deadline:
            try:
                message = self.lines.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            if message is None:
                self.closed = True
            else:
                self.seen.append(message)

    def receive(self, predicate, description, timeout=QUICK):
        deadline = time.monotonic() + timeout
        while True:
            found = next((m for m in self.seen if predicate(m)), None)
            if found:
                return found
            if self.closed or time.monotonic() >= deadline:
                self.errors.seek(0)
                raise AssertionError("no %s within %.0f s (pid %s)\n%s" %
                                     (description, timeout, self.proc.pid, self.errors.read()))
            try:
                message = self.lines.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                continue
            if message is None:
                self.closed = True
            else:
                self.seen.append(message)

    def reply(self, rid, timeout):
        return self.receive(lambda m: m.get("id") == rid, "reply to request %s" % rid, timeout)

    def waiter(self, rid, state):
        return self.receive(lambda m: m.get("method") == "fixture/wait_" + state and
                            m.get("params", {}).get("requestId") == rid, "waiter %s %s" % (rid, state))

    def text(self, rid, timeout=QUICK):
        reply = self.reply(rid, timeout)
        if reply["result"].get("isError"):
            raise AssertionError(reply)
        return reply["result"]["content"][0]["text"]

    def close(self):
        if self.proc.poll() is None:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.proc.stdout.close()
        self.reader.join(timeout=QUICK)
        self.errors.close()


class SharedServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "relic"
        self.server = self.start(ROOT / "server.py", self.home)

    def start(self, script, home):
        """A server with an organization of three members: the lead and its subagents ana and bob."""
        # Arrange each private store before starting its server. Formation performs
        # many SQLite commits on Windows; it is not a concurrent-response latency
        # assertion and must not spend the QUICK budget of a running server call.
        store = Store(home / "relic.sqlite3")
        org = store.create(LEAD, "Team", "build", "lead")["id"]
        store.join(ANA, org, "ana")
        store.join(BOB, org, "bob")
        with store.change(org) as (record, _):
            record["auto_wake"] = False
        server = Server(script, home)
        self.addCleanup(server.close)
        server.reply(server.request("initialize", {"protocolVersion": "2025-06-18"}), 20)
        return server

    def test_a_member_waiting_in_its_inbox_holds_up_nobody(self):
        s = self.server
        waiting = s.tool("inbox", LEAD, wait=WAIT)
        s.waiter(waiting, "ready")
        started = time.monotonic()
        self.assertIn("member 'ana'", s.text(s.tool("status", ANA)))
        s.text(s.tool("message", ANA, to=["lead"], body="the answer is 42"))
        self.assertLess(time.monotonic() - started, QUICK)  # both answered while the lead still waited
        self.assertIn("the answer is 42", s.text(waiting))  # and the wait ends once the message is there
        self.assertLess(time.monotonic() - started, WAIT / 2)
        self.assertIn("No unread messages.", s.text(s.tool("inbox", LEAD)))  # the wait marked it read

    def test_members_can_wait_at_the_same_time(self):
        s = self.server
        lead_waits, ana_waits = s.tool("inbox", LEAD, wait=WAIT), s.tool("inbox", ANA, wait=WAIT)
        s.waiter(lead_waits, "ready")
        s.waiter(ana_waits, "ready")
        started = time.monotonic()
        s.text(s.tool("message", BOB, to=["lead", "ana"], body="build is green"))
        self.assertIn("build is green", s.text(lead_waits))
        self.assertIn("build is green", s.text(ana_waits))
        self.assertLess(time.monotonic() - started, WAIT / 2)

    def test_a_wait_without_a_message_ends_at_its_limit(self):
        s = self.server
        started = time.monotonic()
        waiting = s.tool("inbox", LEAD, wait=3)
        self.assertIn("No unread messages.", s.text(waiting, timeout=10))
        self.assertGreaterEqual(time.monotonic() - started, 2.5)

    def test_a_member_outside_the_organization_gets_the_error_at_once(self):
        s = self.server
        reply = s.reply(s.tool("inbox", "stranger", wait=WAIT), QUICK)
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("not in a Relic organization", reply["result"]["content"][0]["text"])

    def test_a_cancelled_wait_leaves_the_message_unread(self):
        s = self.server
        waiting = s.tool("inbox", LEAD, wait=WAIT)
        s.waiter(waiting, "ready")
        s.write({"jsonrpc": "2.0", "method": "notifications/cancelled",
                 "params": {"requestId": waiting, "reason": "the person stopped the turn"}})
        s.waiter(waiting, "finished")
        s.text(s.tool("message", ANA, to=["lead"], body="still here"))
        self.assertNotIn(waiting, [m.get("id") for m in s.seen])  # the cancelled call gets no reply
        self.assertIn("still here", s.text(s.tool("inbox", LEAD)))

    def test_a_wait_ends_with_its_client_and_reads_nothing(self):
        s = self.server
        waiting = s.tool("inbox", LEAD, wait=WAIT)
        s.waiter(waiting, "ready")
        started = time.monotonic()
        s.proc.stdin.close()
        s.waiter(waiting, "finished")  # EOF cancelled the active waiter; it cannot consume a later message
        store = Store(self.home / "relic.sqlite3")
        store.send(ANA, ["lead"], "nobody will read this answer")
        s.proc.wait(timeout=15)
        self.assertLess(time.monotonic() - started, 10)  # the server does not sit out the wait
        s.drain(5)
        self.assertNotIn(waiting, [m.get("id") for m in s.seen])
        unread = store.unread(LEAD, mark=False)
        self.assertEqual([m["body"] for m in unread], ["nobody will read this answer"])

    def test_an_update_is_picked_up_while_a_member_waits(self):
        copy = Path(self.tmp.name) / "plugin"
        shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"))
        s = self.start(copy / "server.py", Path(self.tmp.name) / "relic-copy")
        waiting = s.tool("inbox", LEAD, wait=WAIT)
        s.waiter(waiting, "ready")
        api_file = copy / "relic_core" / "api.py"
        api_file.write_text(api_file.read_text(encoding="utf-8").replace(
            "Your view of the organization:", "UPDATED. Your view of the organization:"), encoding="utf-8")
        later = time.time() + 5  # a new mtime even on coarse file systems
        os.utime(api_file, (later, later))
        s.text(s.tool("status", ANA))  # this call reloads relic_core while the lead waits
        self.assertIn({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}, s.seen)
        s.text(s.tool("message", ANA, to=["lead"], body="after the update"))
        self.assertIn("after the update", s.text(waiting))
        tools = s.reply(s.request("tools/list"), QUICK)["result"]["tools"]
        self.assertTrue(next(t for t in tools if t["name"] == "status")["description"].startswith("UPDATED."))

    def test_rereading_a_message_ignores_wait_on_the_transport(self):
        s = self.server
        sent = json.loads(s.text(s.tool("message", ANA, to=["lead"], body="read again")))["message_id"]
        s.text(s.tool("inbox", LEAD))
        self.assertIn("read again", s.text(s.tool("inbox", LEAD, message_id=sent, wait=WAIT)))


class Input:
    """Controllable stdio input: queue entries establish ordering, never sleeps."""

    def __init__(self):
        self.lines = queue.Queue()

    def put(self, value):
        self.lines.put(None if value is None else json.dumps(value) + "\n")

    def __iter__(self):
        return iter(self.lines.get, None)


class Cancellation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "relic.sqlite3")
        self.org = self.store.create(LEAD, "Fixture", "cancellation", "lead")["id"]
        self.store.join(ANA, self.org, "ana")
        self.plugin = SimpleNamespace(store=self.store, api=api)
        self.params = {"name": "inbox", "arguments": {"actor": LEAD, "wait": WAIT}}

    def start(self, stop=None, done=None):
        waiter = transport.Waiter(self.plugin, 1, self.params, WAIT, done or (lambda _: None), stop)
        def cleanup():
            waiter.stop.set()
            waiter.join(QUICK)
            self.assertFalse(waiter.is_alive())
        self.addCleanup(cleanup)
        waiter.start()
        return waiter

    def unread(self):
        return [m["body"] for m in self.store.unread(LEAD, mark=False)]

    def test_eof_and_cancellation_interrupt_a_waiter_blocked_on_code(self):
        for disconnect in (False, True):
            with self.subTest(disconnect=disconnect):
                stream = Input()
                requests = transport.Requests(stream)
                requests.reader.start()
                self.addCleanup(lambda stream=stream: stream.put(None))
                stream.put({"id": 1, "method": "tools/call", "params": self.params})
                _, stop = requests.queue.get(timeout=QUICK)
                # Simulates a slow ordinary call/reload owning CODE. The input
                # thread and the cancelled waiter must both finish before release.
                with transport.CODE, mock.patch.object(transport, "send") as sent:
                    waiter = self.start(stop, requests.finish)
                    stream.put(None if disconnect else {"method": "notifications/cancelled",
                                                        "params": {"requestId": 1}})
                    self.assertTrue(stop.wait(QUICK))
                    waiter.join(QUICK)
                    self.assertFalse(waiter.is_alive())
                    sent.assert_not_called()
                self.store.send(ANA, ["lead"], "after cancellation")
                self.assertIn("after cancellation", self.unread())
                if not disconnect:
                    stream.put({"id": 2, "method": "ping"})
                    req, later_stop = requests.queue.get(timeout=QUICK)
                    self.assertEqual(req["id"], 2)
                    self.assertFalse(later_stop.is_set())
                    stream.put(None)
                requests.reader.join(QUICK)
                self.assertFalse(requests.reader.is_alive())

    def test_cancel_after_snapshot_before_delivery_does_not_mark_any_message(self):
        self.store.send(ANA, ["lead"], "keep unread")
        prepared, release = threading.Event(), threading.Event()
        original = api.inbox
        def inbox(*args, **kwargs):
            result = original(*args, **kwargs)
            prepared.set()
            if not release.wait(QUICK):
                raise AssertionError("snapshot was never released")
            return result
        with mock.patch.object(api, "inbox", side_effect=inbox), mock.patch.object(transport.sys, "stdout") as output:
            waiter = self.start()
            try:
                self.assertTrue(prepared.wait(QUICK))
                waiter.stop.set()
            finally:
                release.set()
            waiter.join(QUICK)
            self.assertFalse(waiter.is_alive())
            output.write.assert_not_called()
        self.assertEqual(self.unread(), ["keep unread"])

    def test_broken_output_does_not_mark_messages_read(self):
        self.store.send(ANA, ["lead"], "keep unread")
        with mock.patch.object(transport.sys, "stdout") as output:
            output.write.side_effect = BrokenPipeError("client closed stdout")
            waiter = self.start()
            waiter.join(QUICK)
            self.assertFalse(waiter.is_alive())
        self.assertEqual(self.unread(), ["keep unread"])

    def test_disconnect_during_flush_does_not_mark_messages_read(self):
        self.store.send(ANA, ["lead"], "keep unread")
        stop = threading.Event()
        with mock.patch.object(transport.sys, "stdout") as output:
            output.flush.side_effect = stop.set
            waiter = self.start(stop)
            waiter.join(QUICK)
            self.assertFalse(waiter.is_alive())
            output.flush.assert_called_once()
        self.assertEqual(self.unread(), ["keep unread"])

    def test_cancel_while_output_is_busy_does_not_hold_code_or_mark_messages(self):
        self.store.send(ANA, ["lead"], "keep unread")
        ready = threading.Event()
        original = transport.send
        def send(*args, **kwargs):
            ready.set()
            return original(*args, **kwargs)
        with transport.OUT, mock.patch.object(transport, "send", side_effect=send):
            waiter = self.start()
            self.assertTrue(ready.wait(QUICK))
            self.assertTrue(transport.CODE.acquire(timeout=QUICK))
            transport.CODE.release()
            waiter.stop.set()
            waiter.join(QUICK)
            self.assertFalse(waiter.is_alive())
        self.assertEqual(self.unread(), ["keep unread"])

    def test_success_acknowledges_only_the_delivered_snapshot(self):
        self.store.send(ANA, ["lead"], "delivered")
        delivered = []
        def send(reply, stop):
            # Reply is fully written before acknowledgements, without CODE held.
            delivered.append(reply)
            self.assertEqual(self.unread(), ["delivered"])
            self.store.send(ANA, ["lead"], "arrived during delivery")
            return True
        with mock.patch.object(transport, "send", side_effect=send):
            waiter = self.start()
            waiter.join(QUICK)
            self.assertFalse(waiter.is_alive())
        self.assertEqual(len(delivered), 1)
        self.assertIn("delivered", delivered[0]["result"]["content"][0]["text"])
        self.assertEqual(self.unread(), ["arrived during delivery"])


if __name__ == "__main__":
    unittest.main()
