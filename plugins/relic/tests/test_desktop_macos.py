"""macOS bridge contracts against private fixture sockets; no real application or chat is contacted."""
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_core import desktop, runner


def read_exact(connection, size):
    data = b""
    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            raise RuntimeError("fixture client disconnected")
        data += chunk
    return data


@unittest.skipIf(os.name == "nt", "real Unix socket contract fixture")
class UnixDesktop(unittest.TestCase):
    def setUp(self):
        # A short private path also fits Darwin's 104-byte sockaddr_un.sun_path.
        self.tmp = tempfile.TemporaryDirectory(prefix="relic-sock-", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "host.sock"
        patch = mock.patch.dict(os.environ, {"RELIC_HOME": str(self.root / "data"), desktop.PIPE_ENV: str(self.path)})
        patch.start()
        self.addCleanup(patch.stop)
        platform = mock.patch.object(desktop, "sys", SimpleNamespace(platform="darwin"))
        platform.start()
        self.addCleanup(platform.stop)
        windows = mock.patch.object(runner, "WINDOWS", False)
        windows.start()
        self.addCleanup(windows.stop)
        self.received, self.errors = [], []

    def bridge(self, reply, fragmented=False):
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.path))
        self.path.chmod(0o600)
        listener.listen(1)
        listener.settimeout(2)
        self.addCleanup(listener.close)

        def serve():
            try:
                with listener.accept()[0] as connection:
                    connection.settimeout(2)
                    size = struct.unpack("<I", read_exact(connection, 4))[0]
                    request = json.loads(read_exact(connection, size))
                    self.received.append(request)
                    value = reply(request) if callable(reply) else reply
                    if value is None:
                        return
                    wire = value if isinstance(value, bytes) else json.dumps(dict(value, id=request["id"])).encode("utf-8")
                    if not isinstance(value, bytes):
                        wire = struct.pack("<I", len(wire)) + wire
                    if fragmented:
                        for start in range(0, len(wire), 3):
                            connection.sendall(wire[start:start + 3])
                    else:
                        connection.sendall(wire)
            except (OSError, RuntimeError) as error:
                self.errors.append(error)
            finally:
                listener.close()

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 3)
        return worker

    @staticmethod
    def tools(request):
        return {"jsonrpc": "2.0", "result": {"tools": [
            {"name": name, "namespace": desktop.NAMESPACE} for name in desktop.REQUIRED_TOOLS]}}

    def test_fragmented_tools_list_confirms_framing_and_caches_inode_proof(self):
        worker = self.bridge(self.tools, fragmented=True)
        self.assertFalse(desktop.transport_capability()["available"])
        status = desktop.transport_capability(probe=True)
        self.assertTrue(status["available"], status)
        worker.join(2)
        self.assertEqual([r["method"] for r in self.received], ["tools/list"])
        with mock.patch.object(desktop, "exchange", side_effect=AssertionError("ordinary capability read must not probe")):
            self.assertTrue(desktop.transport_capability()["available"])
        desktop.reset_transport_verification()
        self.assertFalse(desktop.transport_capability()["available"])

    def test_socket_replacement_invalidates_positive_proof(self):
        worker = self.bridge(self.tools)
        self.assertTrue(desktop.transport_capability(probe=True)["available"])
        worker.join(2)
        old = desktop._socket_identity(str(self.path))
        self.path.unlink()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as replacement:
            replacement.bind(str(self.path))
            self.path.chmod(0o600)
            # A new endpoint must never inherit the old handshake, even if its pathname is unchanged.
            self.assertNotEqual(old, desktop._socket_identity(str(self.path)))
            self.assertFalse(desktop.transport_capability()["available"])

    def test_host_peer_refusal_is_reported_and_not_claimed_as_support(self):
        self.bridge(None)
        result = desktop.transport_capability(probe=True)
        self.assertFalse(result["available"])
        self.assertIn("closed", result["reason"])
        self.assertFalse(desktop.transport_capability()["available"])

    def test_missing_required_tool_does_not_enable_delivery(self):
        self.bridge({"result": {"tools": [{"name": desktop.SEND, "namespace": desktop.NAMESPACE}]}})
        self.assertFalse(desktop.transport_capability(probe=True)["available"])

    def test_regular_files_symlinks_and_public_sockets_are_never_contacted(self):
        self.path.write_bytes(b"private file")
        with mock.patch.object(desktop.socket, "socket") as connect:
            with self.assertRaises(desktop.DesktopError):
                desktop.exchange(str(self.path), {"id": 1})
            connect.assert_not_called()
        self.assertEqual(self.path.read_bytes(), b"private file")
        self.path.unlink()
        other = self.root / "target.sock"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as endpoint:
            endpoint.bind(str(other))
            other.chmod(0o600)
            self.path.symlink_to(other)
            self.assertIsNone(desktop._socket_identity(str(self.path)))
            other.chmod(0o666)
            self.assertIsNone(desktop._socket_identity(str(other)))

    def test_timeout_after_write_is_uncertain_and_has_no_retry_thread(self):
        def wait(request):
            time.sleep(.3)
            return None
        self.bridge(wait)
        start = time.monotonic()
        with self.assertRaises(desktop.Uncertain):
            desktop.exchange(str(self.path), {"id": 1, "method": "tools/call"}, timeout=.05)
        self.assertLess(time.monotonic() - start, .25)
        self.assertEqual(len(self.received), 1)

    def test_invalid_reply_size_is_bounded_and_uncertain(self):
        self.bridge(struct.pack("<I", desktop.MAX_FRAME + 1))
        with self.assertRaisesRegex(desktop.Uncertain, "frame length"):
            desktop.exchange(str(self.path), {"id": 1}, timeout=1)

    def test_nonexistent_socket_and_no_candidates_do_not_scan(self):
        with mock.patch.object(desktop.os, "listdir", side_effect=AssertionError("no scanning")):
            self.assertIsNone(desktop.find_pipe())
        self.assertFalse(self.received)


if __name__ == "__main__":
    unittest.main()
