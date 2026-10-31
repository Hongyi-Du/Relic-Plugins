"""No real programs or servers are started by these native-host contract tests."""
import contextlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("native_host", SCRIPTS / "native_host.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class NativeHostTests(unittest.TestCase):
    def test_borrowed_server_is_never_stopped(self):
        info = {"port": 12345, "pid": 111, "instance": "existing", "token": "fixture"}
        with patch.object(native, "LifecycleLock", return_value=contextlib.nullcontext()), \
                patch.object(native.launcher, "running", return_value=info), \
                patch.object(native.subprocess, "Popen") as spawn, \
                patch.object(native.launcher, "endpoint") as endpoint:
            host = native.NativeHost()
            self.assertFalse(host.start()["owned"])
            host.close()
            spawn.assert_not_called()
            endpoint.assert_not_called()

    def test_spawn_has_no_console_and_shutdown_authenticates_instance(self):
        info = {"port": 12345, "pid": 222, "instance": "ours", "token": "fixture"}
        child = Mock(pid=222)
        child.poll.side_effect = [None, 0]
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(native, "data_home", return_value=Path(temp)), \
                patch.object(native, "LifecycleLock", return_value=contextlib.nullcontext()), \
                patch.object(native, "creation_flags", return_value=0x08000000), \
                patch.object(native.launcher, "running", side_effect=[None, info, info]), \
                patch.object(native.launcher, "unverified_server", return_value=False), \
                patch.object(native.subprocess, "Popen", return_value=child) as spawn, \
                patch.object(native.launcher, "endpoint") as endpoint:
            host = native.NativeHost()
            self.assertTrue(host.start()["owned"])
            host.close()
            self.assertEqual(spawn.call_args.kwargs["creationflags"], 0x08000000)
            self.assertEqual(spawn.call_args.args[0][-1], "--serve")
            endpoint.assert_called_once_with(info, "/api/shutdown", {"instance": "ours"})
            child.terminate.assert_not_called()

    def test_changed_instance_never_receives_shutdown(self):
        child = Mock(pid=222)
        child.poll.return_value = None
        host = native.NativeHost(); host.child = child
        host.info = {"pid": 222, "instance": "old"}
        with patch.object(native.launcher, "running", return_value={"pid": 333, "instance": "new"}), \
                patch.object(native.launcher, "endpoint") as endpoint:
            host.close()
            endpoint.assert_not_called()
            child.terminate.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
