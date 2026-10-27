"""The tool layer: waiting in the inbox for a reply, friction notes that say what failed, and a server that picks up
an update of the plugin while its session stays open (run on a copy of the plugin, never on the plugin itself)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core import api  # noqa: E402
from relic_core.store import Store  # noqa: E402


class Clock:
    def __init__(self, on_sleep=None):
        self.t, self.slept, self.on_sleep = 0.0, 0.0, on_sleep

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds
        self.slept += seconds
        if self.on_sleep:
            self.on_sleep(self.t)


class Api(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = Store(Path(self.tmp.name) / "relic.sqlite3")
        self.oid = self.store.create("s1", "Team", "build", "lead")["id"]
        self.store.join("s2", self.oid, "ana")

    def tearDown(self):
        self.tmp.cleanup()

    def test_inbox_waits_for_the_reply(self):
        def reply_later(t):
            if t >= 30 and not self.store.history(self.oid, 5):
                self.store.send("s2", ["lead"], "here is my answer")
        clock = Clock(reply_later)
        out = api.inbox(self.store, "s1", wait=300, sleep=clock.sleep, clock=clock)
        self.assertEqual([m["body"] for m in out["messages"]], ["here is my answer"])
        self.assertLess(clock.t, 40)  # returned as soon as it arrived
        self.assertEqual(api.inbox(self.store, "s1")["messages"], [])  # marked read

    def test_inbox_wait_is_bounded(self):
        clock = Clock()
        out = api.inbox(self.store, "s1", wait=10 ** 6, sleep=clock.sleep, clock=clock)
        self.assertEqual(out["text"], "No unread messages.")
        self.assertEqual(clock.t, api.MAX_WAIT)

    def test_inbox_without_wait_returns_at_once(self):
        clock = Clock()
        api.inbox(self.store, "s1", sleep=clock.sleep, clock=clock)
        self.assertEqual(clock.slept, 0)

    def test_trajectory_defaults_ask_for_memory_and_redact(self):
        # the tool's defaults reach the store: memory on request, redaction on answer
        calls = {}

        class Spy:
            def request_trajectory(self, *a):
                calls["request"] = a
                return {}

            def answer_trajectory(self, *a):
                calls["answer"] = a
                return {}
        api.handle_call(Spy(), "trajectory", {"op": "request", "member": "ana", "reason": "why"}, "s1")
        api.handle_call(Spy(), "trajectory", {"op": "answer", "request_id": "TR1", "decision": "approve"}, "s2")
        self.assertIs(calls["request"][-1], True)
        self.assertIs(calls["answer"][-1], True)
        api.handle_call(Spy(), "trajectory", {"op": "answer", "request_id": "TR1", "decision": "approve",
                                              "redact": False}, "s2")
        self.assertIs(calls["answer"][-1], False)

    def test_failed_tool_says_what_failed(self):
        self.store.record_activity("s2", "WebFetch", {"url": "https://web.example.edu/~prof/"}, failed=True,
                                   output=" \nunable to verify the first certificate\nmore detail")
        org = self.store.get(self.oid)
        friction = org["episodes"][org["members"]["ana"]["turn_episode"]]["friction"]
        self.assertEqual(friction, ["tool failed: WebFetch https://web.example.edu/~prof/ "
                                    "(unable to verify the first certificate)"])


class LiveServer(unittest.TestCase):
    """server.py on a copy of the plugin: an edit to relic_core under a running server is picked up at the next call."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        base = Path(self.tmp.name)
        self.copy = base / "plugin"
        shutil.copytree(ROOT, self.copy, ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"))
        env = dict(os.environ, RELIC_HOME=str(base / "relic"), RELIC_ACTOR="s1", PYTHONDONTWRITEBYTECODE="1")
        env.pop("CODEX_THREAD_ID", None)
        env.pop("CODEX_APP_TOOLS_PIPE_PATH", None)
        self.proc = subprocess.Popen([sys.executable, "-X", "utf8", str(self.copy / "server.py")], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                     env=env)
        self.seq = 0

    def tearDown(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=20)
        self.proc.stdout.close()
        self.tmp.cleanup()

    def ask(self, method, params=None):
        self.seq += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.seq, "method": method,
                                          "params": params or {}}) + "\n")
        self.proc.stdin.flush()
        seen = []
        while True:
            message = json.loads(self.proc.stdout.readline())
            if message.get("id") == self.seq:
                return message, seen
            seen.append(message)

    def test_update_is_picked_up_without_a_restart(self):
        self.ask("initialize", {"protocolVersion": "2025-06-18"})
        self.ask("tools/call", {"name": "create", "arguments": {"name": "T", "purpose": "p", "member": "lead"}})
        api_file = self.copy / "relic_core" / "api.py"
        text = api_file.read_text(encoding="utf-8")
        api_file.write_text(text.replace("Your view of the organization:", "UPDATED. Your view of the organization:"),
                            encoding="utf-8")
        later = time.time() + 5  # a new mtime even on coarse file systems
        os.utime(api_file, (later, later))
        reply, seen = self.ask("tools/call", {"name": "status", "arguments": {}})
        self.assertFalse(reply["result"].get("isError"), reply)
        self.assertIn({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}, seen)
        tools, _ = self.ask("tools/list")
        status = next(t for t in tools["result"]["tools"] if t["name"] == "status")
        self.assertTrue(status["description"].startswith("UPDATED."))

    def touch(self, path, text):
        """Write a file of the plugin copy with a newer modification time than anything before it."""
        self.bump = getattr(self, "bump", 0) + 5
        path.write_text(text, encoding="utf-8")
        later = time.time() + self.bump
        os.utime(path, (later, later))

    def test_a_broken_update_keeps_the_loaded_version(self):
        self.ask("initialize", {"protocolVersion": "2025-06-18"})
        self.ask("tools/call", {"name": "create", "arguments": {"name": "T", "purpose": "p", "member": "lead"}})
        api_file, store_file = self.copy / "relic_core" / "api.py", self.copy / "relic_core" / "store.py"
        api_good, store_good = api_file.read_text(encoding="utf-8"), store_file.read_text(encoding="utf-8")
        # a module that fails half way through loading
        self.touch(api_file, api_good + "\nTOOLS = None\nraise RuntimeError('broken update')\n")
        reply, _ = self.ask("tools/call", {"name": "status", "arguments": {}})
        self.assertFalse(reply["result"].get("isError"), reply)
        tools, _ = self.ask("tools/list")
        self.assertIn("status", [t["name"] for t in tools["result"]["tools"]])
        # a store that cannot open
        self.touch(api_file, api_good)
        self.touch(store_file, store_good + "\n\nclass _Broken(Store):\n    def __init__(self, *a, **k):\n"
                                            "        raise RuntimeError('store cannot open')\n\n\nStore = _Broken\n")
        reply, _ = self.ask("tools/call", {"name": "status", "arguments": {}})
        self.assertFalse(reply["result"].get("isError"), reply)
        reply, _ = self.ask("ping")
        self.assertEqual(reply["result"], {})
        # the next good update is picked up
        self.touch(store_file, store_good)
        self.touch(api_file, api_good.replace("Your view of the organization:", "FIXED. Your view of the organization:"))
        tools, _ = self.ask("tools/list")
        status = next(t for t in tools["result"]["tools"] if t["name"] == "status")
        self.assertTrue(status["description"].startswith("FIXED."))

    def test_a_failing_call_never_ends_the_server(self):
        self.ask("initialize", {"protocolVersion": "2025-06-18"})
        reply, _ = self.ask("tools/call", {"name": "status", "arguments": {}})  # no organization yet
        self.assertTrue(reply["result"]["isError"])
        reply, _ = self.ask("tools/call", {"name": "no-such-tool", "arguments": {}})
        self.assertTrue(reply["result"]["isError"])
        reply, _ = self.ask("ping")
        self.assertEqual(reply["result"], {})


if __name__ == "__main__":
    unittest.main()
