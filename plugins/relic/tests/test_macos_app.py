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


class BrowserWindows(unittest.TestCase):
    URL = "http://127.0.0.1:39321/"
    BROWSER = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    def test_unsupported_python_is_rejected_before_starting_the_server(self):
        with mock.patch.object(sys, "argv", ["relic_app.py", "--no-window"]), \
                mock.patch.object(platform_support, "require_supported_python", side_effect=RuntimeError("native arm64 required")), \
                mock.patch.object(relic_app, "running") as running, \
                mock.patch.object(relic_app, "start_server") as start:
            with self.assertRaisesRegex(RuntimeError, "native arm64 required"):
                relic_app.main()
            running.assert_not_called()
            start.assert_not_called()

    def test_app_mode_uses_the_discovered_bundle_executable(self):
        with mock.patch.object(relic_app, "WINDOWS", False), \
                mock.patch.object(process, "WINDOWS", False), \
                mock.patch.object(relic_app, "installed_shortcut", return_value=None), \
                mock.patch.object(relic_app, "installed_edge_app", return_value=None), \
                mock.patch.object(relic_app, "data_home", return_value=Path("/Users/test/Relic Data")), \
                mock.patch.object(platform_support, "browser_executable", return_value=self.BROWSER), \
                mock.patch.object(platform_support, "open_external") as opened, \
                mock.patch.object(relic_app.subprocess, "Popen") as popen:
            relic_app.open_window(self.URL)
            args = popen.call_args.args[0]
            self.assertEqual(args[0], self.BROWSER)
            self.assertIn("--app=" + self.URL, args)
            self.assertIn("--user-data-dir=" + str(Path("/Users/test/Relic Data") / "app-window"), args)
            self.assertTrue(popen.call_args.kwargs["start_new_session"])
            self.assertEqual(popen.call_args.kwargs["creationflags"], 0)
            opened.assert_not_called()

    def test_missing_browser_uses_the_default_application(self):
        with mock.patch.object(relic_app, "installed_shortcut", return_value=None), \
                mock.patch.object(relic_app, "installed_edge_app", return_value=None), \
                mock.patch.object(platform_support, "browser_executable", return_value=None), \
                mock.patch.object(platform_support, "open_external") as opened:
            relic_app.open_window(self.URL)
            opened.assert_called_once_with(self.URL)
            opened.side_effect = RuntimeError("no browser")
            with self.assertRaisesRegex(RuntimeError, "no browser"):
                relic_app.open_window(self.URL)

    def test_stale_browser_falls_back_to_the_default_application(self):
        with mock.patch.object(relic_app, "installed_shortcut", return_value=None), \
                mock.patch.object(relic_app, "installed_edge_app", return_value=None), \
                mock.patch.object(platform_support, "browser_executable", return_value=self.BROWSER), \
                mock.patch.object(relic_app.subprocess, "Popen", side_effect=FileNotFoundError("removed")), \
                mock.patch.object(platform_support, "open_external") as opened:
            relic_app.open_window(self.URL)
            opened.assert_called_once_with(self.URL)

    def test_stale_installed_shortcut_falls_back_to_the_page(self):
        shortcut = Path("Relic.lnk")
        with mock.patch.object(relic_app, "installed_shortcut", return_value=shortcut), \
                mock.patch.object(relic_app, "installed_edge_app", return_value=None), \
                mock.patch.object(platform_support, "browser_executable", return_value=None), \
                mock.patch.object(platform_support, "open_external", side_effect=[OSError("stale shortcut"), None]) as opened:
            relic_app.open_window(self.URL)
            self.assertEqual(opened.call_args_list, [mock.call(str(shortcut)), mock.call(self.URL)])

    def test_existing_windows_edge_app_is_still_reused(self):
        with mock.patch.object(relic_app, "WINDOWS", True), \
                mock.patch.object(process, "WINDOWS", True), \
                mock.patch.object(relic_app, "installed_shortcut", return_value=None), \
                mock.patch.object(relic_app, "installed_edge_app", return_value=("Profile 1", "app-id")), \
                mock.patch.object(platform_support, "browser_executable", return_value="msedge.exe"), \
                mock.patch.object(relic_app.subprocess, "Popen") as popen:
            relic_app.open_window(self.URL)
            self.assertEqual(popen.call_args.args[0], ["msedge.exe", "--profile-directory=Profile 1", "--app-id=app-id"])
            self.assertFalse(popen.call_args.kwargs["start_new_session"])
            self.assertEqual(popen.call_args.kwargs["creationflags"], 0x08000200)

    def test_install_window_opens_a_regular_bundle_browser_window(self):
        with mock.patch.object(platform_support, "browser_executable", return_value=self.BROWSER), \
                mock.patch.object(relic_app.subprocess, "Popen") as popen:
            result = web.open_install_window(39321)
            self.assertEqual(popen.call_args.args[0], [self.BROWSER, "--new-window", self.URL + "#install"])
            self.assertEqual(result, {"opened": self.URL + "#install", "browser": self.BROWSER})

    def test_install_window_falls_back_and_reports_failure(self):
        with mock.patch.object(platform_support, "browser_executable", return_value=None), \
                mock.patch.object(platform_support, "open_external") as opened:
            self.assertEqual(web.open_install_window(39321), {"opened": self.URL + "#install", "browser": "default"})
            opened.assert_called_once_with(self.URL + "#install")
            opened.side_effect = OSError("no browser")
            with self.assertRaisesRegex(OSError, "no browser"):
                web.open_install_window(39321)

    def test_install_window_falls_back_when_discovered_browser_disappears(self):
        with mock.patch.object(platform_support, "browser_executable", return_value=self.BROWSER), \
                mock.patch.object(relic_app.subprocess, "Popen", side_effect=FileNotFoundError("removed")), \
                mock.patch.object(platform_support, "open_external") as opened:
            self.assertEqual(web.open_install_window(39321)["browser"], "default")
            opened.assert_called_once_with(self.URL + "#install")


if __name__ == "__main__":
    unittest.main()
