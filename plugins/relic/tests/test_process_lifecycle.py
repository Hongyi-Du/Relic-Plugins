"""Real local ACP process trees; no installed adapter, model, account, or host IPC is used."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import acp
from app.hub import Hub, Live


TREE = r'''
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

role, mode, folder = sys.argv[1], sys.argv[2], Path(sys.argv[3])
def record(name, value):
    (folder / name).write_text(json.dumps(value), encoding="utf-8")

def term(signum, frame):
    record(role + ".term", True)
    if mode == "tree":
        sys.exit(0)

signal.signal(signal.SIGTERM, term)
record(role + ".pid", {"pid": os.getpid(), "pgid": os.getpgrp()})
if role in ("adapter", "child") and mode != "graceful":
    child = subprocess.Popen([sys.executable, "-u", __file__,
                              "child" if role == "adapter" else "grandchild", mode, str(folder)])
if role != "adapter":
    while True:
        time.sleep(.05)

if mode != "graceful":
    deadline = time.monotonic() + 5
    while not (folder / "grandchild.pid").exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("grandchild did not start")
        time.sleep(.01)

for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if method == "initialize" and mode == "timeout":
        continue
    if method == "initialize" and mode == "fail":
        reply = {"error": {"code": -32000, "message": "fixture initialization failed"}}
    elif method == "wait":
        record("waiting", True)
        continue
    else:
        reply = {"result": {"protocolVersion": 1}}
    print(json.dumps(dict(reply, jsonrpc="2.0", id=message["id"])), flush=True)
    if method == "initialize" and mode == "blocked-input":
        record("input-blocked", True)
        while True:
            time.sleep(.05)
    if method == "exit_adapter":
        os._exit(0)
record("eof", True)
if mode != "graceful":
    while True:
        time.sleep(.05)
'''


def running(pid):
    """A killed orphan can briefly remain a zombie until the system reaps it."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    if sys.platform == "darwin":
        state = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True, timeout=1)
        return state.returncode == 0 and bool(state.stdout.strip()) and not state.stdout.strip().startswith("Z")
    if sys.platform.startswith("linux"):
        try:
            return Path("/proc/%s/stat" % pid).read_text().split(")", 1)[1].split()[0] != "Z"
        except FileNotFoundError:
            return False
    return True


@unittest.skipIf(os.name == "nt", "POSIX process groups are not used on Windows")
class ProcessLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.script = self.folder / "fake process tree.py"
        self.script.write_text(TREE, encoding="utf-8")

    def agent(self, mode):
        agent = acp.AcpAgent([sys.executable, "-u", str(self.script), "adapter", mode, str(self.folder)], name=mode)
        self.addCleanup(agent.close, wait=0)
        return agent

    def wait_for(self, condition, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(.02)
        self.fail("fixture condition did not become true")

    def tree(self):
        return [json.loads((self.folder / (role + ".pid")).read_text(encoding="utf-8"))
                for role in ("adapter", "child", "grandchild")]

    def assert_closed(self, agent, tree):
        self.wait_for(lambda: all(not running(row["pid"]) for row in tree))
        self.assertIsNotNone(agent.proc.poll())
        self.assertTrue(agent.closed.is_set())
        self.assertTrue(all(not thread.is_alive() for thread in agent._readers))
        self.assertTrue(all(stream.closed for stream in (agent.proc.stdin, agent.proc.stdout, agent.proc.stderr)))
        self.assertFalse(agent._pending)

    def test_graceful_eof_exits_without_a_termination_signal(self):
        agent = self.agent("graceful")
        agent.start(timeout=5)
        self.assertEqual(os.getpgid(agent.proc.pid), agent.proc.pid)
        self.assertNotEqual(agent.proc.pid, os.getpgrp())
        agent.close(wait=2)
        self.assertTrue((self.folder / "eof").exists())
        self.assertFalse((self.folder / "adapter.term").exists())
        self.assert_closed(agent, [{"pid": agent.proc.pid}])
        agent.close(wait=0)  # idempotent: it must not signal an old, possibly reused PID

    def test_term_reaches_children_and_grandchildren_without_touching_other_processes(self):
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(unrelated.wait, timeout=3)
        self.addCleanup(unrelated.kill)
        agent = self.agent("tree")
        agent.start(timeout=5)
        tree = self.tree()
        self.assertTrue(all(row["pgid"] == agent.proc.pid for row in tree))
        agent.close(wait=.05)
        self.assert_closed(agent, tree)
        self.assertTrue(all((self.folder / (role + ".term")).exists() for role in ("adapter", "child", "grandchild")))
        self.assertIsNone(unrelated.poll())

    def test_kill_escalation_unblocks_pending_rpc_and_pipe_readers(self):
        agent = self.agent("resistant")
        agent.start(timeout=5)
        tree = self.tree()
        errors = []

        def wait_request():
            try:
                agent.request("wait", {})  # intentionally has no timeout
            except acp.AcpError as error:
                errors.append(str(error))

        request = threading.Thread(target=wait_request, daemon=True)
        request.start()
        self.wait_for(lambda: (self.folder / "waiting").exists())
        started = time.monotonic()
        agent.close(wait=.05)
        self.assertLess(time.monotonic() - started, 5)
        request.join(1)
        self.assertFalse(request.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIn("closed", errors[0])
        self.assertEqual(agent.proc.returncode, -signal.SIGKILL)
        self.assert_closed(agent, tree)

    def test_exited_adapter_does_not_leave_children_holding_pipes_open(self):
        agent = self.agent("resistant")
        agent.start(timeout=5)
        tree = self.tree()
        agent.request("exit_adapter", {}, timeout=5)
        self.wait_for(lambda: agent.proc.poll() is not None)
        self.assertTrue(all(running(row["pid"]) for row in tree[1:]))
        self.assertTrue(any(thread.is_alive() for thread in agent._readers))
        agent.close(wait=0)
        self.assert_closed(agent, tree)

    def test_hub_shutdown_closes_tree_when_prompt_cannot_write_to_adapter(self):
        agent = self.agent("blocked-input")
        agent.start(timeout=5)
        tree = self.tree()
        self.wait_for(lambda: (self.folder / "input-blocked").exists())
        hub = Hub(store=object())
        live = Live("fixture-org", "fixture-member", "codex")
        live.agent, live.session_id, live.turn = agent, "fixture-session", {"running": True}
        hub._live[(live.org_id, live.member)] = live
        errors = []

        def prompt():
            try:
                agent.prompt(live.session_id, "x" * 2_000_000)
            except acp.AcpError as error:
                errors.append(str(error))

        writer = threading.Thread(target=prompt, daemon=True)
        writer.start()
        self.wait_for(agent._write_lock.locked)
        started = time.monotonic()
        hub.shutdown()
        self.assertLess(time.monotonic() - started, 8)
        writer.join(2)
        self.assertFalse(writer.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertFalse(hub._live)
        self.assert_closed(agent, tree)

    def test_hub_replacement_reaps_descendants_of_an_exited_adapter_first(self):
        agent = self.agent("resistant")
        agent.start(timeout=5)
        tree = self.tree()
        agent.request("exit_adapter", {}, timeout=5)
        self.wait_for(lambda: agent.proc.poll() is not None)
        self.assertTrue(all(running(row["pid"]) for row in tree[1:]))
        hub = Hub(store=object())
        live = Live("fixture-org", "fixture-member", "codex")
        live.agent = agent
        key = (live.org_id, live.member)
        hub._live[key] = live
        replacement = object()

        def replace(*args):
            self.assert_closed(agent, tree)
            hub._live[key] = replacement
            return replacement

        with mock.patch.object(hub, "_start", side_effect=replace):
            self.assertIs(hub.ensure(*key), replacement)
        self.assertIs(hub._live[key], replacement)

    def test_failed_initialization_reaps_the_entire_started_tree(self):
        agent = self.agent("fail")
        with self.assertRaisesRegex(acp.AcpError, "fixture initialization failed"):
            agent.start(timeout=5)
        self.assert_closed(agent, self.tree())

    def test_initialization_timeout_cleans_up_inherited_pipes(self):
        agent = self.agent("timeout")
        with self.assertRaisesRegex(acp.AcpError, "no answer"):
            agent.start(timeout=1)
        self.assert_closed(agent, self.tree())

    def test_spawn_failure_can_be_closed_without_any_process_group(self):
        agent = acp.AcpAgent([str(self.folder / "missing executable")])
        with self.assertRaises(FileNotFoundError):
            agent.start()
        self.assertIsNone(agent.proc)
        self.assertIsNone(agent._owned_pgid)
        self.assertTrue(agent.closed.is_set())
        agent.close(wait=0)

    def test_failed_group_shutdown_retains_ownership_for_retry(self):
        agent = acp.AcpAgent(["fixture"])
        agent.proc = mock.Mock(pid=4321)
        agent._owned_pgid = 4321
        with mock.patch.object(agent, "_wait_for_exit", return_value=False), \
                mock.patch.object(agent, "_signal_group") as signal_group:
            with self.assertRaisesRegex(acp.AcpError, "shutdown deadline"):
                agent.close(wait=0)
        self.assertFalse(agent._close_complete)
        self.assertEqual(agent._owned_pgid, 4321)
        self.assertEqual(signal_group.call_args_list, [mock.call(signal.SIGTERM), mock.call(signal.SIGKILL)])
        with mock.patch.object(agent, "_wait_for_exit", return_value=True):
            agent.close(wait=0)
        self.assertTrue(agent._close_complete)
        self.assertIsNone(agent._owned_pgid)

    def test_shutdown_during_spawn_waits_for_ownership_and_reaps_the_child(self):
        agent = self.agent("graceful")
        entered, release = threading.Event(), threading.Event()
        real_popen = subprocess.Popen
        failures = []

        def delayed_spawn(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("spawn fixture was not released")
            return real_popen(*args, **kwargs)

        def start():
            try:
                agent.start(timeout=3)
            except acp.AcpError as error:
                failures.append(error)

        with mock.patch.object(acp.subprocess, "Popen", side_effect=delayed_spawn):
            starter = threading.Thread(target=start)
            starter.start()
            self.assertTrue(entered.wait(1))
            closer = threading.Thread(target=lambda: agent.close(wait=0))
            closer.start()
            release.set()
            starter.join(5)
            closer.join(5)
        self.assertFalse(starter.is_alive())
        self.assertFalse(closer.is_alive())
        self.assert_closed(agent, [{"pid": agent.proc.pid}])


if __name__ == "__main__":
    unittest.main()
