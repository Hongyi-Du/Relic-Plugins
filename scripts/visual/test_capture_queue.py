"""CI fixtures for capture hand-off; no subprocess, server or UI is launched."""
import json
from pathlib import Path
import tempfile
import unittest

from capture import pending_element_request


class CaptureQueueTests(unittest.TestCase):
    def test_published_scene_requests_are_independent_and_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            queue = folder / "element-requests"
            queue.mkdir()
            first = queue / "one.json"
            first.write_text(json.dumps({"case_id": "one", "width": 1440}), encoding="utf-8")
            original = first.read_bytes()
            path, request = pending_element_request(folder, set())
            self.assertEqual((path, request["case_id"]), (first, "one"))
            self.assertIsNone(pending_element_request(folder, {"one"}))
            # An unfinished write is never read, and the old published request
            # is never overwritten when the next one becomes available.
            staging = queue / "two.json.tmp"
            staging.write_text('{"case_id": "two"}', encoding="utf-8")
            self.assertIsNone(pending_element_request(folder, {"one"}))
            staging.rename(queue / "two.json")
            _, next_request = pending_element_request(folder, {"one"})
            self.assertEqual(next_request["case_id"], "two")
            self.assertEqual(first.read_bytes(), original)

    def test_wrong_scene_identity_fails_instead_of_acknowledging_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            queue = folder / "element-requests"
            queue.mkdir()
            (queue / "one.json").write_text('{"case_id": "other"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                pending_element_request(folder, set())
