"""Native app integration without launching browsers, accessing live stores, or requiring a listening socket."""
import io
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import relic_app  # noqa: E402
from app import files, web  # noqa: E402
from relic_core import platform_support, process  # noqa: E402


class Request(web.Handler):
    """Exercise real HTTP routing and guards while capturing responses in memory."""

    def __init__(self, path, body=None, token=True, host="127.0.0.1:39321"):
        self.server = SimpleNamespace(app=SimpleNamespace(port=39321, token="test-token", store=object(), hub=None))
        self.path = path
        raw = json.dumps(body or {}).encode("utf-8")
        self.headers = {"Host": host, "Content-Length": str(len(raw))}
        if token:
            self.headers["X-Relic-Token"] = "test-token"
        self.rfile = io.BytesIO(raw)
        self.response = None

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        self.response = code, json.loads(body)


class NativeOpen(unittest.TestCase):
    def test_allowed_file_is_opened_and_failure_is_reported(self):
        path = Path("/Users/test/Work Files/报告.md")
        with mock.patch.object(files, "allowed", return_value=path), \
                mock.patch.object(platform_support, "open_external") as opened:
            self.assertEqual(files.open_path(object(), str(path)), {"opened": str(path)})
            opened.assert_called_once_with(str(path))
            opened.side_effect = OSError("application unavailable")
            with self.assertRaisesRegex(OSError, "application unavailable"):
                files.open_path(object(), str(path))

    def test_disallowed_path_never_reaches_the_native_opener(self):
        with mock.patch.object(files, "allowed", return_value=None), \
                mock.patch.object(platform_support, "open_external") as opened:
            with self.assertRaises(PermissionError):
                files.open_path(object(), "/private/outside.txt")
            opened.assert_not_called()

    def test_data_and_logs_routes_open_the_requested_folder(self):
        home = Path("/Users/test/.relic")
        with mock.patch.object(web, "data_home", return_value=home), \
                mock.patch.object(platform_support, "open_external") as opened:
            for what, target in (("data", home), ("logs", home / "runs")):
                with self.subTest(what=what):
                    request = Request("/api/open", {"what": what})
                    request.do_POST()
                    self.assertEqual(request.response, (200, {"opened": str(target)}))
                    opened.assert_called_with(str(target))

    def test_native_open_http_errors_are_not_success_responses(self):
        home = Path("/Users/test/.relic")
        for error, status in ((OSError("open failed"), 500), (RuntimeError("no default app"), 400)):
            with self.subTest(error=error), mock.patch.object(web, "data_home", return_value=home), \
                    mock.patch.object(platform_support, "open_external", side_effect=error):
                request = Request("/api/open", {"what": "data"})
                request.do_POST()
                self.assertEqual(request.response[0], status)
                self.assertIn(str(error), request.response[1]["error"])
                self.assertNotIn("opened", request.response[1])

    def test_native_open_routes_still_require_the_write_token(self):
        with mock.patch.object(platform_support, "open_external") as opened:
            for path, body in (("/api/open", {"what": "data"}), ("/api/fs/open", {"path": "/tmp/a"}),
                               ("/api/install-window", {})):
                with self.subTest(path=path):
                    request = Request(path, body, token=False)
                    request.do_POST()
                    self.assertEqual(request.response[0], 403)
            opened.assert_not_called()

    def test_platform_endpoint_is_guarded_and_has_no_store_dependency(self):
        caps = {"platform": "darwin", "architecture": "arm64", "macos_supported": True,
                "codex_desktop_wake": False, "chatgpt_delivery": False, "claude_desktop_wake": False}
        with mock.patch.object(platform_support, "capabilities", return_value=caps) as capabilities:
            request = Request("/api/platform")
            request.do_GET()
            self.assertEqual(request.response, (200, caps))
            capabilities.assert_called_once_with()
            request = Request("/api/platform", host="other.example:39321")
            request.do_GET()
            self.assertEqual(request.response[0], 403)
            capabilities.assert_called_once_with()


class NativeWindows(unittest.TestCase):
    def test_panel_uses_the_same_native_launcher_and_reports_missing_installation(self):
        from relic_core import runner
        with mock.patch("scripts.relic_app.open_native_app", return_value="Relic.exe") as launch:
            self.assertEqual(runner.open_window(), "Relic.exe")
            launch.assert_called_once_with()
            launch.side_effect = RuntimeError("native Relic App is not installed")
            with self.assertRaisesRegex(RuntimeError, "native Relic App is not installed"):
                runner.open_window()

    def test_unsupported_python_is_rejected_before_starting_the_server(self):
        with mock.patch.object(sys, "argv", ["relic_app.py", "--no-window"]), \
                mock.patch.object(platform_support, "require_supported_python", side_effect=RuntimeError("native arm64 required")), \
                mock.patch.object(relic_app, "running") as running, \
                mock.patch.object(relic_app, "start_server") as start:
            with self.assertRaisesRegex(RuntimeError, "native arm64 required"):
                relic_app.main()
            running.assert_not_called()
            start.assert_not_called()

    def test_default_open_delegates_server_ownership_to_the_native_app(self):
        with mock.patch.object(sys, "argv", ["relic_app.py"]), \
                mock.patch.object(platform_support, "require_supported_python"), \
                mock.patch.object(relic_app, "open_native_app", return_value="Relic.exe") as opened, \
                mock.patch.object(relic_app, "start_server") as start, \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            relic_app.main()
            opened.assert_called_once_with()
            start.assert_not_called()

    def test_windows_launch_is_console_free_and_never_opens_a_url(self):
        executable = Path("Relic.exe")
        with mock.patch.object(relic_app, "WINDOWS", True), \
                mock.patch.object(process, "WINDOWS", True), \
                mock.patch.object(relic_app, "native_executable", return_value=executable), \
                mock.patch.object(relic_app.subprocess, "Popen") as popen:
            self.assertEqual(relic_app.open_native_app(), str(executable))
            self.assertEqual(popen.call_args.args[0], [str(executable)])
            self.assertEqual(popen.call_args.kwargs["creationflags"], 0x08000200)
            self.assertEqual(popen.call_args.kwargs["stdin"], relic_app.subprocess.DEVNULL)

    def test_mac_bundle_opens_as_a_native_dock_application(self):
        bundle = Path("/Users/test/Applications/Relic.app")
        with mock.patch.object(relic_app, "WINDOWS", False), \
                mock.patch.object(process, "WINDOWS", False), \
                mock.patch.object(relic_app, "native_executable", return_value=bundle / "Contents/MacOS/Relic"), \
                mock.patch.object(relic_app.subprocess, "Popen") as popen:
            self.assertEqual(relic_app.open_native_app(), str(bundle))
            self.assertEqual(popen.call_args.args[0], ["/usr/bin/open", str(bundle)])
            self.assertEqual(popen.call_args.kwargs["creationflags"], 0)

    def test_browser_install_route_is_retired_without_opening_anything(self):
        with mock.patch.object(platform_support, "open_external") as opened, \
                mock.patch.object(relic_app.subprocess, "Popen") as popen:
            request = Request("/api/install-window")
            request.do_POST()
            self.assertEqual(request.response[0], 410)
            self.assertIn("native Relic App", request.response[1]["error"])
            opened.assert_not_called()
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
