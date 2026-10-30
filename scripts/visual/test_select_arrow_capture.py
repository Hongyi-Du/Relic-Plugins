"""Pure transport fixtures for UA-select evidence; no browser/server starts."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import capture


class SelectArrowCaptureTests(unittest.TestCase):
    def test_existing_pierced_receipt_is_passed_unchanged_and_linked_to_actual_png_name(self):
        with tempfile.TemporaryDirectory() as folder:
            page, cdp, browser = Mock(), Mock(), Mock()
            browser.version = "fixture-Chromium"
            cdp.send.return_value = {"actual": "source receipt"}
            page.evaluate.side_effect = [
                {"caret_context": {"focused_editor_candidate": False}}, {"elements": []},
            ]
            pierced = {"root": {"nodeType": 1, "nodeName": "SELECT", "backendNodeId": 559,
                "shadowRoots": [{"nodeType": 11, "backendNodeId": 795, "shadowRootType": "user-agent"}]}}
            input_text = {"inputs": {}, "errors": [], "raw_document": pierced}
            case = {"id": "actual-group", "scene": "group", "file": "actual-group.png"}
            manifest = {"output": folder, "fixture": {}, "lang": "zh-CN", "theme": "light"}
            with patch.object(capture, "input_text_evidence", return_value=input_text), \
                    patch.object(capture, "font_evidence", return_value={}):
                capture.capture_reference_evidence(page, cdp, browser, manifest, case)
            metadata = page.evaluate.call_args_list[-1].args[1]
            self.assertIs(metadata["pierced_dom"], pierced, "Do not synthesize a separate UA arrow node or replacement DOM")
            self.assertEqual(metadata["screenshot_file"], "actual-group.png")
            self.assertEqual(metadata["scene_id"], "actual-group")
            page.screenshot.assert_called_once_with(path=Path(folder) / "actual-group.png", caret="initial", animations="disabled")
            self.assertEqual([call.args[0] for call in cdp.send.call_args_list],
                             ["DOMSnapshot.captureSnapshot", "Accessibility.getFullAXTree"],
                             "Arrow metadata reuses the existing real pierced receipt; no DOM mutation or clone query is introduced")
            saved = json.loads((Path(folder) / "actual-group.input-text.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["raw_document"], pierced)
            cdp.detach.assert_called_once_with(); page.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
