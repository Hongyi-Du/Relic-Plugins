"""UI localization preserves desktop capability facts; no process or server runs."""
import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import harness, views


class NativeDiagnostics(unittest.TestCase):
    def test_localizes_fixed_reasons_without_mutating_transport_proof(self):
        source = {"platform": "darwin", "desktop_transport": {"available": False,
                  "reason": "No private host-supplied desktop socket; open a chat with the Relic plugin loaded",
                  "endpoint": "/private/a.sock", "checked_at": 42},
                  "claude_desktop": {"enabled": False, "reason":
                  "Enable Claude Desktop delivery explicitly in Relic settings; Choose Claude Code 2.1.224+ and run the desktop capability probe (observed 2.1.100)"}}
        original = copy.deepcopy(source)
        result = views.platform_info(source, "zh-CN")
        self.assertEqual(source, original)
        self.assertEqual(result["desktop_transport"]["endpoint"], "/private/a.sock")
        self.assertEqual(result["desktop_transport"]["checked_at"], 42)
        self.assertFalse(result["desktop_transport"]["available"])
        self.assertIn("宿主提供", result["desktop_transport"]["reason"])
        self.assertIn("检测到 2.1.100", result["claude_desktop"]["reason"])
        self.assertEqual(views.platform_info(source, "en-US"), source)

    def test_preserves_unknown_provider_errors_verbatim(self):
        error = "Provider error 53: /private/custom.sock"
        self.assertEqual(views.platform_info({"desktop_transport": {"reason": error}}, "zh-CN")["desktop_transport"]["reason"], error)

    def test_missing_provider_messages_use_the_selected_language(self):
        with mock.patch("relic_core.store.person_language", return_value="zh-CN"), mock.patch.object(harness, "claude_program", return_value=""), mock.patch.object(harness, "codex_program", return_value=""):
            with self.assertRaisesRegex(RuntimeError, "未找到 Claude Code"):
                harness._claude_env()
            with self.assertRaisesRegex(RuntimeError, "未找到 Codex"):
                harness._codex_env()
