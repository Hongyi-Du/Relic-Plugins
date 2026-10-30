"""Capture coordination fixtures. No browser, native app or server is started."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import capture


class ComponentCaptureTests(unittest.TestCase):
    def manifest(self, root):
        return {"client": "windows", "output": str(root / "native"),
                "fixture": {"home": "same-actual-fixture"},
                "cases": [{"id": "case-a", "scene": "group"}, {"id": "case-b", "scene": "private"}]}

    def test_native_is_attempted_before_reference_and_reference_failure_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            root = Path(folder); manifest = self.manifest(root)
            observer = Mock()
            observer.native.return_value = {"count": 2, "errors": []}
            observer.reference.side_effect = RuntimeError("actual reference capture failed")
            with patch.object(capture, "native", observer.native), patch.object(capture, "reference", observer.reference):
                result = capture.capture_components(root / "manifest.json", manifest, Path("Relic.exe"), root / "reference")
            self.assertEqual([call[0] for call in observer.mock_calls], ["native", "reference"])
            self.assertEqual([row["count"] for row in result["components"]], [2, 0])
            self.assertEqual([row["status"] for row in result["components"]], ["completed", "failed"])
            self.assertEqual(result["errors"], ["reference: actual reference capture failed"])
            self.assertEqual(observer.reference.call_args.args[0]["fixture"], manifest["fixture"])
            self.assertEqual(json.loads((root / "components.json").read_text()), result)
            self.assertTrue((root / "reference-component-exception.log").is_file())

    def test_native_failure_does_not_suppress_reference_or_claim_expected_native_count(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            root = Path(folder); manifest = self.manifest(root)
            with patch.object(capture, "native", side_effect=RuntimeError("provider timeout")), \
                    patch.object(capture, "reference") as reference:
                result = capture.capture_components(root / "manifest.json", manifest, Path("Relic.exe"), root / "reference")
            reference.assert_called_once()
            self.assertEqual([row["count"] for row in result["components"]], [0, 2])
            self.assertEqual(result["errors"], ["windows: provider timeout"])
            self.assertEqual(result["components"][0]["status"], "failed")
            self.assertEqual(result["components"][1]["status"], "completed")
            self.assertEqual(result["components"][1]["errors"], [], "A failed native component is not a reference execution failure")

    def test_partial_files_and_receipts_cannot_erase_native_errors(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            root = Path(folder); manifest = self.manifest(root)
            def partial(*args):
                (root / "native" / "case-b.png").write_bytes(b"fixture placeholder, not a validated capture")
                return {"count": 1, "errors": ["case-b: incomplete UIA"]}
            with patch.object(capture, "native", side_effect=partial), patch.object(capture, "reference"):
                result = capture.capture_components(root / "manifest.json", manifest, Path("Relic.exe"), root / "reference")
            native = result["components"][0]
            self.assertEqual(native["status"], "failed")
            self.assertEqual(native["count"], 1)
            self.assertEqual(native["artifacts_present"], {".png": 1, ".elements.json": 0})
            self.assertEqual(result["errors"], ["windows: case-b: incomplete UIA"])

    def test_coordinator_refuses_local_capture(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), patch.object(capture, "native") as native, \
                patch.object(capture, "reference") as reference:
            with self.assertRaisesRegex(SystemExit, "CI-only"):
                capture.capture_components(Path("unused"), {})
            native.assert_not_called(); reference.assert_not_called()


if __name__ == "__main__":
    unittest.main()
