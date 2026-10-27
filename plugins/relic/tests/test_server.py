"""server.py as a lead and its relic:member subagents use it: they share one server process, so an inbox call waiting
for a message must hold up nobody; a cancelled or abandoned wait must leave the messages unread; and an update of
relic_core must still be picked up while a member waits."""
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core.store import Store  # noqa: E402

# a lead and two of its subagents, named the way the hook names their actors
LEAD, ANA, BOB = "lead-session", "lead-session/agent-ana", "lead-session/agent-bob"
WAIT = 30  # seconds an inbox call below asks to wait
QUICK = 5.0  # seconds within which a call is answered while somebody else waits


class Server:
    """One server.py process with a reader thread, so its replies may come in any order."""

    def __init__(self, script, home):
        env = dict(os.environ, RELIC_HOME=str(home), PYTHONDONTWRITEBYTECODE="1")
        for key in ("RELIC_ACTOR", "RELIC_MAX_WAIT", "CODEX_THREAD_ID", "CODEX_APP_TOOLS_PIPE_PATH"):
            env.pop(key, None)
        self.proc = subprocess.Popen([sys.executable, "-X", "utf8", str(script)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                     env=env)
        self.lines, self.seen, self.closed, self.seq = queue.Queue(), [], False, 0
        threading.Thread(target=self._read, daemon=True).start()

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

    def reply(self, rid, timeout):
        deadline = time.monotonic() + timeout
        while True:
            found = next((m for m in self.seen if m.get("id") == rid), None)
            if found:
                return found
            if self.closed or time.monotonic() >= deadline:
                raise AssertionError("no reply to request %s within %.0f s" % (rid, timeout))
            self.drain(min(0.2, max(0.01, deadline - time.monotonic())))

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


class SharedServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "relic"
        self.server = self.start(ROOT / "server.py", self.home)

    def start(self, script, home):
        """A server with an organization of three members: the lead and its subagents ana and bob."""
        server = Server(script, home)
        self.addCleanup(server.close)
        server.reply(server.request("initialize", {"protocolVersion": "2025-06-18"}), 20)
        created = server.text(server.tool("create", LEAD, name="Team", purpose="build", member="lead"), 20)
        org = re.search(r"\((org_[0-9a-f]+)\)", created).group(1)
        server.text(server.tool("join", ANA, org_id=org, member="ana"))
        server.text(server.tool("join", BOB, org_id=org, member="bob"))
        return server

    def test_a_member_waiting_in_its_inbox_holds_up_nobody(self):
        s = self.server
        waiting = s.tool("inbox", LEAD, wait=WAIT)
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
        s.write({"jsonrpc": "2.0", "method": "notifications/cancelled",
                 "params": {"requestId": waiting, "reason": "the person stopped the turn"}})
        s.text(s.tool("message", ANA, to=["lead"], body="still here"))
        s.drain(3)  # longer than one look into the inbox: a wait still running would have read the message by now
        self.assertNotIn(waiting, [m.get("id") for m in s.seen])  # the cancelled call gets no reply
        self.assertIn("still here", s.text(s.tool("inbox", LEAD)))

    def test_a_wait_ends_with_its_client_and_reads_nothing(self):
        s = self.server
        waiting = s.tool("inbox", LEAD, wait=WAIT)
        time.sleep(0.5)  # the wait has had its first look into the inbox
        s.text(s.tool("message", ANA, to=["lead"], body="nobody will read this answer"))
        started = time.monotonic()
        s.proc.stdin.close()
        s.proc.wait(timeout=15)
        self.assertLess(time.monotonic() - started, 10)  # the server does not sit out the wait
        s.drain(5)
        self.assertNotIn(waiting, [m.get("id") for m in s.seen])
        unread = Store(self.home / "relic.sqlite3").unread(LEAD, mark=False)
        self.assertEqual([m["body"] for m in unread], ["nobody will read this answer"])

    def test_an_update_is_picked_up_while_a_member_waits(self):
        copy = Path(self.tmp.name) / "plugin"
        shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"))
        s = self.start(copy / "server.py", Path(self.tmp.name) / "relic-copy")
        waiting = s.tool("inbox", LEAD, wait=WAIT)
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


if __name__ == "__main__":
    unittest.main()
