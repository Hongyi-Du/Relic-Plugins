"""Real localhost/process lifecycle fixtures using private stores and a fake ACP agent; no native windows or models."""
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import relic_app  # noqa: E402
from app import hub, web  # noqa: E402
from relic_core.process import creation_flags

ENTRY = ROOT / "scripts/relic_app.py"
WRAPPER = REPOSITORY / "scripts/open_app.py"


def wait_for(check, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError("lifecycle fixture timed out")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# Only this local fixture knows a fake harness. The production launcher never enables one from an environment flag.
FAKE_SERVER = r'''
import faulthandler, os, sys
faulthandler.dump_traceback_later(8)
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from app import harness, hub, web
from app.acp import AcpAgent
fake = Path(sys.argv[1]) / "tests/fake_acp_agent.py"
harness.HARNESSES["fixture"] = {"title":"Fixture", "vendor":"Tests", "command":lambda:sys.executable,
    "args":["-B", str(fake)], "actor":lambda sid:"fixture:"+sid, "relic":"mcp", "default_mode":""}
original_start = AcpAgent.start
def start(self, *args, **kwargs):
    result = original_start(self, *args, **kwargs)
    Path(os.environ["FIXTURE_AGENT_PID"]).write_text(str(self.proc.pid))
    return result
AcpAgent.start = start
web.main(int(sys.argv[2]))
'''

SERVER = r'''
import faulthandler, runpy, sys
faulthandler.dump_traceback_later(8)
entry, sys.argv = sys.argv[1], sys.argv[1:]
runpy.run_path(entry, run_name="__main__")
'''


class Isolated(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="relic-lifecycle-")
        self.root = Path(self.temp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("RELIC_", "CODEX_", "CLAUDE_"))}
        self.env.update(RELIC_HOME=str(self.root / "relic"), RELIC_ORG_HOME=str(self.root / "organizations"),
                        CODEX_HOME=str(self.root / "codex"), CLAUDE_CONFIG_DIR=str(self.root / "claude"),
                        RELIC_LANG="en-US", PYTHONDONTWRITEBYTECODE="1", FIXTURE_AGENT_PID=str(self.root / "agent.pid"))
        self.environment = mock.patch.dict(os.environ, self.env, clear=True)
        self.environment.start()
        self.processes = []
        self.logs = []

    def tearDown(self):
        try:
            if relic_app.verified_info():
                relic_app.stop_server(timeout=20)
        finally:
            for process in self.processes:
                if process.poll() is None:
                    # These exact Popen objects belong to this fixture, never a PID read from app.json.
                    process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream:
                        stream.close()
            for handle in self.logs:
                handle.close()
            self.environment.stop()
            # On Windows the server lease is released just before interpreter
            # exit closes inherited log handles. Bound that brief exit race;
            # a real leaked server still fails cleanup instead of being ignored.
            deadline = time.monotonic() + 5
            while True:
                try:
                    self.temp.cleanup()
                    break
                except PermissionError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)

    def start(self, port=None, fake=False):
        port = port or free_port()
        log = open(self.root / ("server-%d.log" % len(self.processes)), "w+", encoding="utf-8")
        self.logs.append(log)
        command = ([sys.executable, "-B", "-c", FAKE_SERVER, str(ROOT), str(port)] if fake else
                   [sys.executable, "-B", "-c", SERVER, str(ENTRY), "--serve", "--port", str(port)])
        process = subprocess.Popen(command, env=self.env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   creationflags=creation_flags())
        self.processes.append(process)
        try:
            def ready():
                if process.poll() is not None:
                    raise AssertionError("server exited with code %s" % process.returncode)
                return relic_app.running()
            info = wait_for(ready)
        except AssertionError as error:
            log.flush()
            log.seek(0)
            detail = log.read()[-12000:]
            record = relic_app.saved_info()
            if record:
                try:
                    relic_app.endpoint(record, "/api/lifecycle")
                except Exception as failure:
                    detail += "\nLifecycle request: %s: %s" % (type(failure).__name__, failure)
            self.fail("%s\nServer output:\n%s" % (error, detail))
        return process, info

    def cli(self, *args):
        if not WRAPPER.is_file():
            self.skipTest("Release-layout scripts/open_app.py is not present in this development checkout")
        done = subprocess.run([sys.executable, "-B", str(WRAPPER), *args], env=self.env,
                              capture_output=True, text=True, timeout=35, creationflags=creation_flags())
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()


class RecordsAndLocks(Isolated):
    def test_empty_file_owned_by_another_handle_is_not_written_before_locking(self):
        with web.LifecycleLock("app-control.lock", timeout=0) as owner:
            owner.handle.seek(0)
            owner.handle.truncate()
            owner.handle.flush()
            with self.assertRaisesRegex(RuntimeError, "owns app-control.lock"):
                with web.LifecycleLock("app-control.lock", timeout=0.05):
                    self.fail("a second handle acquired the owner's lock")

    def test_stale_owner_record_is_not_a_live_lock(self):
        path = Path(self.env["RELIC_HOME"]) / "app-server.lock"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"pid": os.getpid(), "acquired": 0}), encoding="utf-8")
        with web.LifecycleLock("app-server.lock", timeout=0) as lease:
            # Windows byte-range locks deny a second handle even in this process.
            lease.handle.seek(0)
            self.assertEqual(json.load(lease.handle)["pid"], os.getpid())
        self.assertTrue(path.exists())  # keeping the inode avoids two independent lock owners

    def test_live_owner_blocks_with_a_bounded_wait(self):
        code = ("import sys;sys.path.insert(0,sys.argv[1]);from app.web import LifecycleLock;"
                "lock=LifecycleLock('app-control.lock',timeout=0);lock.__enter__();"
                "print('locked',flush=True);sys.stdin.readline();lock.__exit__()")
        process = subprocess.Popen([sys.executable, "-B", "-c", code, str(ROOT)], env=self.env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   creationflags=creation_flags())
        self.processes.append(process)
        self.assertEqual(process.stdout.readline().strip(), "locked")
        start = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, "owns app-control.lock"):
            with web.LifecycleLock("app-control.lock", timeout=0.15):
                self.fail("a second process acquired the active lease")
        self.assertLess(time.monotonic() - start, 1)
        process.stdin.write("release\n")
        process.stdin.flush()
        process.wait(timeout=5)
        with web.LifecycleLock("app-control.lock", timeout=0):
            pass

    def test_an_old_server_cannot_delete_its_successors_record(self):
        old = SimpleNamespace(instance="old-instance", token="old-token")
        record = {"pid": os.getpid(), "instance": "new-instance", "token": "new-token", "port": 39321}
        web.atomic_json(web.info_path(), record)
        web.remove_own_info(old)
        self.assertEqual(json.loads(web.info_path().read_text()), record)
        web.remove_own_info(SimpleNamespace(instance="new-instance", token="new-token"))
        self.assertFalse(web.info_path().exists())

    def test_port_preference_survives_stop_and_invalid_records_are_ignored(self):
        path = Path(self.env["RELIC_HOME"]) / "app-port.json"
        web.atomic_json(path, {"port": 40567})
        self.assertEqual(relic_app.preferred_port(), 40567)
        self.assertEqual(relic_app.preferred_port(40568), 40568)
        for invalid in ("bad json", "null", '{"port":99999}'):
            path.write_text(invalid, encoding="utf-8")
            self.assertEqual(relic_app.preferred_port(), web.DEFAULT_PORT)


class Authentication(Isolated):
    def test_shutdown_requires_token_and_matching_instance(self):
        if not WRAPPER.is_file():
            self.skipTest("Release-layout scripts/open_app.py is not present")
        process, info = self.start()
        for changed, body, expected in ((dict(info, token="wrong"), {"instance": info["instance"]}, 403),
                                         (info, {"instance": "old-instance"}, 409)):
            with self.subTest(expected=expected):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    relic_app.endpoint(changed, "/api/shutdown", body)
                self.assertEqual(caught.exception.code, expected)
                caught.exception.close()
                self.assertIsNone(process.poll())
                self.assertIsNotNone(relic_app.running())
        with self.assertRaises(urllib.error.HTTPError) as caught:
            relic_app.endpoint(info, "/api/lifecycle", authenticated=False)
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()
        public = json.loads(self.cli("--status"))
        self.assertTrue(public["running"])
        self.assertNotIn("token", public)
        self.assertNotIn(info["token"], json.dumps(public))
        self.assertNotIn("instance", public)

    def test_unverified_relic_is_never_stopped_or_replaced(self):
        requests = []

        class OtherRelic(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                requests.append(("GET", self.path))
                payload = json.dumps({"app": "relic", "pid": 123, "instance": "different-instance", "port": self.server.server_port}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self):
                requests.append(("POST", self.path))
                self.send_error(500)

        server = ThreadingHTTPServer(("127.0.0.1", 0), OtherRelic)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            web.atomic_json(web.info_path(), {"pid": 123, "port": server.server_port, "instance": "saved-instance", "token": "saved-token"})
            self.assertEqual(relic_app.status(), {"running": False, "state": "unverified"})
            with self.assertRaisesRegex(RuntimeError, "cannot be authenticated"):
                relic_app.stop_server()
            with mock.patch.object(relic_app.subprocess, "Popen") as spawn:
                with self.assertRaisesRegex(RuntimeError, "ownership cannot be verified"):
                    relic_app.start_server()
                spawn.assert_not_called()
            self.assertFalse(any(method == "POST" for method, _ in requests))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            web.info_path().unlink(missing_ok=True)


class ServerLifecycle(Isolated):
    def test_loopback_bind_does_not_depend_on_reverse_dns(self):
        with mock.patch.object(socket, "getfqdn", side_effect=AssertionError("reverse DNS is unavailable")):
            server = web.bind(0)
        try:
            self.assertEqual(server.server_name, "127.0.0.1")
            self.assertEqual(server.server_port, server.server_address[1])
        finally:
            server.server_close()

    def test_startup_timeout_reaps_its_own_child(self):
        spawn = subprocess.Popen
        children = []

        def stalled(*args, **kwargs):
            child = spawn([sys.executable, "-B", "-c", "import time; time.sleep(30)"], **kwargs)
            children.append(child)
            self.processes.append(child)
            return child

        with mock.patch.object(relic_app.subprocess, "Popen", side_effect=stalled):
            with self.assertRaisesRegex(RuntimeError, "server did not start"):
                relic_app.start_server(timeout=0.05)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())

    def test_duplicate_direct_serve_is_rejected_and_stop_cleans_metadata(self):
        if not WRAPPER.is_file():
            self.skipTest("Release-layout scripts/open_app.py is not present")
        process, info = self.start()
        duplicate = subprocess.run([sys.executable, "-B", str(ENTRY), "--serve", "--port", str(info["port"])],
                                   env=self.env, capture_output=True, text=True, timeout=10, creationflags=creation_flags())
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn("app-server.lock", duplicate.stderr)
        self.assertEqual(relic_app.running()["instance"], info["instance"])
        result = json.loads(self.cli("--stop"))
        self.assertTrue(result["stopped"])
        self.assertEqual(process.wait(timeout=10), 0)
        self.assertFalse(web.info_path().exists())
        self.assertEqual(json.loads(self.cli("--status")), {"running": False, "state": "stopped"})
        self.assertFalse(json.loads(self.cli("--stop"))["stopped"])

    @unittest.skipIf(os.name == "nt", "POSIX SIGTERM/SIGINT graceful shutdown")
    def test_signals_use_the_graceful_cleanup_path(self):
        for sig in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=sig):
                process, _ = self.start()
                process.send_signal(sig)
                self.assertEqual(process.wait(timeout=15), 0)
                self.assertFalse(web.info_path().exists())
                with web.LifecycleLock("app-server.lock", timeout=0):
                    pass

    def test_concurrent_start_restart_and_stop_serialize_and_reuse_port(self):
        if not WRAPPER.is_file():
            self.skipTest("Release-layout scripts/open_app.py is not present")
        port = free_port()

        def concurrent(arguments, count=3):
            processes = [subprocess.Popen([sys.executable, "-B", str(WRAPPER), *arguments], env=self.env,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                           creationflags=creation_flags()) for _ in range(count)]
            self.processes.extend(processes)
            output = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=35)
                if process.returncode:
                    log = Path(self.env["RELIC_HOME"]) / "runs/relic-app.log"
                    if log.exists():
                        stderr += "\nServer output:\n" + log.read_text(encoding="utf-8", errors="replace")[-12000:]
                self.assertEqual(process.returncode, 0, stderr)
                output.append(stdout.strip())
            return output

        first = concurrent(["--no-window", "--port", str(port)])
        self.assertEqual(set(first), {"http://127.0.0.1:%d/" % port})
        initial = relic_app.running()
        restarted = concurrent(["--restart", "--no-window"])
        self.assertEqual(set(restarted), set(first))
        self.assertNotEqual(relic_app.running()["instance"], initial["instance"])
        stops = [json.loads(value) for value in concurrent(["--stop"])]
        self.assertEqual(sum(value["stopped"] for value in stops), 1)
        self.assertIsNone(relic_app.running())
        self.assertEqual(self.cli("--no-window"), first[0])

    def test_shutdown_cancels_waiting_permissions_and_closes_fake_acp(self):
        process, info = self.start(fake=True)
        oid = relic_app.endpoint(info, "/api/orgs", {"name": "Fixture"})["org_id"]
        relic_app.endpoint(info, "/api/org/%s/members" % oid, {"name": "helper", "role": "fixture", "harness": "fixture"})

        def state():
            return (relic_app.endpoint(info, "/api/org/%s/live?member=helper" % oid).get("status") or {}).get("state")

        wait_for(lambda: state() == "idle")
        agent_pid = int((self.root / "agent.pid").read_text())
        relic_app.endpoint(info, "/api/org/%s/send" % oid, {"to": ["helper"], "body": "needs permission"})
        wait_for(lambda: state() == "waiting")
        self.assertTrue(relic_app.stop_server()["stopped"])
        self.assertEqual(process.wait(timeout=15), 0)
        self.assertFalse(web.info_path().exists())
        if os.name != "nt":
            with self.assertRaises(ProcessLookupError):
                os.kill(agent_pid, 0)


class HubShutdown(Isolated):
    def test_shutdown_during_initialize_closes_the_starting_adapter(self):
        with tempfile.TemporaryDirectory(prefix="relic-initialize-stop-") as directory:
            org = {"id": "fixture", "name": "Fixture", "members": {"member": {"config": {
                "surface": "acp", "harness": "fixture", "folder": directory}}}}
            store = SimpleNamespace(get=lambda _: org, set_config=lambda *args: None)
            instance = hub.Hub(store=store)
            errors = []

            def start():
                try:
                    instance.ensure("fixture", "member")
                except Exception as error:
                    errors.append(error)

            command = [sys.executable, "-B", "-c", "import sys; sys.stdin.read()"]
            with mock.patch.dict(hub.harnesses.HARNESSES, {"fixture": {"title": "Fixture"}}), \
                    mock.patch.object(hub.harnesses, "launch", return_value=(command, dict(os.environ))), \
                    mock.patch.object(hub.harnesses, "relic_for", return_value=([], None)):
                starter = threading.Thread(target=start)
                starter.start()
                live = wait_for(lambda: (instance._live.get(("fixture", "member")) or SimpleNamespace(agent=None)).agent)
                wait_for(lambda: live.proc is not None)
                instance.shutdown()
                starter.join(timeout=3)
            self.assertFalse(starter.is_alive())
            self.assertTrue(errors)
            self.assertFalse(live.alive)
            self.assertIsNotNone(live.proc.poll())

    def test_pending_permission_is_cancelled_and_no_new_session_can_start(self):
        instance = hub.Hub(store=object())
        live = hub.Live("fixture", "member", "fixture")
        instance._live[("fixture", "member")] = live
        result = []
        with mock.patch.object(instance, "_permit", return_value=None):
            waiter = threading.Thread(target=lambda: result.append(instance._request(
                ("fixture", "member"), "session/request_permission", {"toolCall": {"title": "fixture"}, "options": []})))
            waiter.start()
            wait_for(lambda: instance.permissions("fixture"))
            instance.shutdown()
            waiter.join(timeout=2)
        self.assertFalse(waiter.is_alive())
        self.assertEqual(result, [{"outcome": {"outcome": "cancelled"}}])
        self.assertEqual(instance.permissions("fixture"), [])
        with self.assertRaisesRegex(RuntimeError, "stopping"):
            instance.ensure("fixture", "member")
        self.assertEqual(instance._request(("fixture", "member"), "session/request_permission", {}), result[0])


if __name__ == "__main__":
    unittest.main()
