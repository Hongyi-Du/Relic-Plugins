"""Pure malformed-capture/report regressions; CI only, no UI or subprocesses."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from element_parity import compare_elements, outlines, run, validate_capture
from test_element_parity import capture, element
from test_pattern_integration import measured_pair


class ReportFailureTests(unittest.TestCase):
    def test_null_or_malformed_style_records_errors_instead_of_aborting_validation(self):
        for malformed in (None, [], "missing", 0):
            with self.subTest(style=malformed):
                data = capture()
                data["elements"][0]["style"] = malformed
                errors = validate_capture(data, "reference", data["scene_id"], data["viewport"])
                self.assertTrue(any(row["reason"] == "Missing measurement object: style" for row in errors))
                self.assertTrue(any("rendered_fonts" in row["reason"] for row in errors))

    def test_unknown_bounds_and_malformed_evidence_do_not_invent_or_crash_outlines(self):
        for evidence in (None, [], "missing", {}):
            item = element()
            item["bounds"] = {key: None for key in ("x", "y", "width", "height")}
            item["evidence"] = evidence
            result = outlines([item], {}, {"width": 1440, "height": 900}, "actual.png", "Reference")
            self.assertIn('href="actual.png"', result)
            self.assertIn('<g class="outlines"></g>', result)
            self.assertNotIn('x="None"', result)

    def test_reference_missing_or_malformed_pattern_evidence_never_reaches_pixel_comparison(self):
        for evidence in (None, [], "missing", {}):
            ref, native = measured_pair()
            # Break only the paint measurement under test. This synthetic
            # object still has an independently declared absent outline.
            ref["evidence"] = {"outline": {"absence_proven": True,
                                            "source": "synthetic fixture with no outline"},
                               "background_pattern_measurement": evidence}
            with patch("element_parity.compare_paint_patterns") as compare:
                result = compare_elements([ref], [native])
                compare.assert_not_called()
            self.assertEqual(len(result["extraction_errors"]), 1)
            self.assertEqual(result["matched_elements"], 0)

    def test_only_unambiguous_emitted_coverage_sources_are_attributed(self):
        cases = [({"id": "r0", "reason": "missing paint"}, "r0"),
                 ({"element": "r0", "reason": "missing paint"}, "r0"),
                 ({"id": "r0", "element": "r0"}, "r0"),
                 ({"id": "r0", "element": "other"}, None),
                 ({"id": "raw-node-not-emitted"}, None),
                 ({"id": []}, None), ("unknown capture-level geometry", None)]
        for gap, expected in cases:
            data = capture()
            data["coverage"]["unmeasured"] = [gap]
            errors = validate_capture(data, "reference", data["scene_id"], data["viewport"])
            unmeasured = [row for row in errors if row["reason"].startswith("Unmeasured:")]
            self.assertEqual(len(unmeasured), 1)
            self.assertEqual(unmeasured[0]["element"], expected)
            self.assertEqual(unmeasured[0]["reason"], "Unmeasured: " + str(gap))

    def test_coverage_error_counts_and_outlines_keep_actual_element_scope(self):
        spec = {"languages": ["en-US"], "themes": ["light"], "sizes": [[160, 80]], "scenes": ["group"]}
        scene, viewport = "en-US-light-160x80-group", {"width": 160, "height": 80, "scale": 1}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for client in ("reference", "reference-macos", "windows", "macos"):
                path = root / "source" / client
                path.mkdir(parents=True)
                items = [element(client + "-0", "Affected", 0), element(client + "-1", "Unaffected", 1)]
                items[1]["bounds"]["y"] = 42
                items[1]["evidence"]["text_bounds"][0]["y"] = 42
                data = capture(client, items, scene, viewport)
                if client == "windows":
                    data["coverage"]["unmeasured"] = [{"id": "windows-0", "property": "fixture.paint", "reason": "Known test-only source lacks paint evidence"}]
                (path / f"{scene}.elements.json").write_text(json.dumps(data), encoding="utf-8")
                Image.new("RGBA", (160, 80), (255, 255, 255, 255)).save(path / f"{scene}.png")
            result = run(root / "source", root / "report", spec=spec)
            windows = result["scenes"][0]["platforms"]["windows"]
            html = (root / "report" / f"{scene}-windows.html").read_text(encoding="utf-8")
        self.assertFalse(result["passed"])
        self.assertEqual(windows["counts"]["extraction_errors"], 1)
        self.assertEqual(windows["matched_elements"], 1)
        self.assertEqual(windows["raw_native_elements"], 2)
        self.assertEqual(windows["valid_native_elements"], 2)
        self.assertEqual(windows["invalid_native_elements"], 0)
        self.assertEqual(result["summary"]["windows"]["scenes_checked"], 0)
        self.assertIn("mismatch: windows-0", html)
        self.assertIn("match: windows-1", html)
        self.assertIn('x="10.0" y="42" width="100.0" height="20.0"', html)


if __name__ == "__main__":
    unittest.main()
