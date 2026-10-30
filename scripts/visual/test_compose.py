"""Synthetic temporary PNG/receipt fixtures; no UI, browser or process is run."""
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

import compose
from element_parity import SMOKE_SCENES


SPEC = {"languages": ["zh-CN"], "themes": ["light"], "sizes": [[32, 20]], "scenes": ["first", "second"]}
NAMES = [f"zh-CN-light-32x20-{scene}.png" for scene in SPEC["scenes"]]
COLORS = {"reference": (1, 71, 133), "windows": (51, 123, 17), "macos": (192, 33, 81)}


class DiagnosticComposeTests(unittest.TestCase):
    def fixture(self, directory):
        source, output = Path(directory) / "captures", Path(directory) / "report"
        for client in compose.CLIENTS:
            folder = source / client
            folder.mkdir(parents=True)
            for name in NAMES:
                with Image.new("RGB", (32, 20), COLORS[client]) as image:
                    image.putpixel((3, 4), (21, 22, 23))
                    image.save(folder / name)
            self.receipt(source, client, count=2)
        return source, output

    def receipt(self, source, client, **changes):
        receipt = {"matrix": "full", "count": 2, "errors": []}
        receipt.update(changes)
        (source / client / "capture-complete.json").write_text(json.dumps(receipt), encoding="utf-8")

    def failed_output(self, source, output):
        with self.assertRaisesRegex(ValueError, "Diagnostic comparisons were written"):
            compose.compose(source, output, SPEC)
        coverage = json.loads((output / "coverage.json").read_text(encoding="utf-8"))
        self.assertFalse(coverage["capture_validation_passed"])
        self.assertEqual(coverage["visual_acceptance"], "requires human review")
        self.assertTrue(set(NAMES) <= {path.name for path in output.glob("*.png")}, "Required scenes cannot disappear after a capture failure")
        self.assertIn("CAPTURE VALIDATION FAILED", (output / "index.html").read_text(encoding="utf-8"))
        return coverage

    def test_success_preserves_every_original_pixel_at_original_size(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = self.fixture(directory)
            before = {(client, name): (source / client / name).read_bytes() for client in compose.CLIENTS for name in NAMES}
            coverage = compose.compose(source, output, SPEC)
            self.assertTrue(coverage["capture_validation_passed"])
            self.assertEqual(coverage["comparisons"], 2)
            self.assertEqual(coverage["complete_actual_capture_comparisons"], 2)
            self.assertEqual(coverage["visual_acceptance"], "requires human review")
            for name in NAMES:
                with Image.open(output / name) as combined:
                    self.assertEqual(combined.size, (128, 64))
                    for index, client in enumerate(compose.CLIENTS):
                        with Image.open(source / client / name) as original:
                            self.assertEqual(combined.crop((index * 48, 44, index * 48 + 32, 64)).tobytes(), original.tobytes())
                        self.assertEqual((source / client / name).read_bytes(), before[(client, name)])

    def test_receipt_count_failure_still_writes_all_real_composites_and_error(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = self.fixture(directory)
            self.receipt(source, "windows", count=1)
            coverage = self.failed_output(source, output)
            self.assertEqual(coverage["complete_actual_capture_comparisons"], 2)
            self.assertEqual(coverage["receipt_errors"][0]["receipt_count"], 1)
            self.assertEqual(coverage["receipt_errors"][0]["png_count"], 2)
            self.assertTrue(all(not column["placeholder"] for scene in coverage["scenes"] for column in scene["columns"]))

    def test_missing_client_slot_is_labeled_and_never_counted_as_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = self.fixture(directory)
            (source / "windows" / NAMES[1]).unlink()
            self.receipt(source, "windows", count=1)
            coverage = self.failed_output(source, output)
            self.assertEqual(coverage["required_comparisons"], 2)
            self.assertEqual(coverage["complete_actual_capture_comparisons"], 1)
            self.assertEqual(coverage["missing"]["windows"], [NAMES[1]])
            slot = next(scene for scene in coverage["scenes"] if scene["file"] == NAMES[1])["columns"][1]
            self.assertEqual(slot["status"], "missing")
            self.assertTrue(slot["placeholder"])
            self.assertEqual(slot["placeholder_label"], "CAPTURE MISSING — windows")
            with Image.open(output / NAMES[1]) as combined:
                self.assertEqual(combined.getpixel((4, 49)), COLORS["reference"])
                self.assertEqual(combined.getpixel((100, 49)), COLORS["macos"])
            self.assertIn("not screenshots or acceptance evidence", (output / "index.html").read_text(encoding="utf-8"))

    def test_wrong_dimensions_and_corrupt_png_receive_invalid_placeholders(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = self.fixture(directory)
            wrong = source / "windows" / NAMES[0]
            with Image.new("RGB", (31, 20), COLORS["windows"]) as image:
                image.save(wrong)
            corrupt = source / "macos" / NAMES[1]
            corrupt.write_bytes(b"actual invalid PNG fixture")
            before = wrong.read_bytes()
            coverage = self.failed_output(source, output)
            self.assertEqual(len(coverage["image_errors"]), 2)
            self.assertTrue(all(item["status"] == "invalid" and item["placeholder"] for item in coverage["image_errors"]))
            self.assertTrue(any(item["actual_size"] == [31, 20] for item in coverage["image_errors"]))
            self.assertEqual(coverage["complete_actual_capture_comparisons"], 0)
            self.assertEqual(wrong.read_bytes(), before)
            self.assertEqual(corrupt.read_bytes(), b"actual invalid PNG fixture")

    def test_extra_files_are_reported_and_rendered_without_replacing_required_scenes(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = self.fixture(directory)
            extras = ["zh-CN-light-32x20-extra.png", "unmeasured-name.png"]
            for name in extras:
                with Image.new("RGB", (32, 20), COLORS["reference"]) as image:
                    image.save(source / "reference" / name)
            self.receipt(source, "reference", count=4)
            coverage = self.failed_output(source, output)
            self.assertEqual(set(coverage["extra"]["reference"]), set(extras))
            self.assertEqual(coverage["comparisons"], 4)
            self.assertEqual(coverage["required_comparisons"], 2)
            self.assertEqual({row["file"] for row in coverage["scenes"] if not row["required"]}, set(extras))
            self.assertEqual({path.name for path in output.glob("*.png")}, set(NAMES + extras))

    def test_malformed_missing_or_conflicting_matrix_receipts_keep_full_diagnostic_target(self):
        for problem in ("malformed", "missing", "conflicting", "unknown"):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as directory:
                source, output = self.fixture(directory)
                path = source / "windows/capture-complete.json"
                if problem == "malformed":
                    path.write_text("not JSON", encoding="utf-8")
                elif problem == "missing":
                    path.unlink()
                else:
                    self.receipt(source, "windows", matrix="smoke" if problem == "conflicting" else "invented")
                coverage = self.failed_output(source, output)
                self.assertIsNone(coverage["matrix"])
                self.assertEqual(coverage["diagnostic_matrix"], "full")
                self.assertEqual(coverage["required_comparisons"], 2)
                self.assertTrue(coverage["receipt_errors"])

    def test_producer_errors_do_not_disappear_when_png_count_happens_to_match(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = self.fixture(directory)
            errors = ["Actual UIA extraction failed after this PNG was saved"]
            self.receipt(source, "windows", errors=errors)
            coverage = self.failed_output(source, output)
            self.assertEqual(coverage["receipt_errors"][0]["errors"], errors)
            self.assertEqual(coverage["complete_actual_capture_comparisons"], 2)

    def test_actual_full_and_smoke_targets_retain_all_672_and_21_scenes(self):
        spec = json.loads((Path(compose.__file__).parent / "scenes.json").read_text(encoding="utf-8"))
        matrix, diagnostic, targets = compose.comparison_targets(spec, {"full"})
        self.assertEqual((matrix, diagnostic), ("full", "full"))
        self.assertEqual(len(targets), 672)
        self.assertEqual(set(targets), {f"{lang}-{theme}-{width}x{height}-{scene}.png"
            for lang in spec["languages"] for theme in spec["themes"] for width, height in spec["sizes"] for scene in spec["scenes"]})
        matrix, diagnostic, targets = compose.comparison_targets(spec, {"smoke"})
        self.assertEqual((matrix, diagnostic), ("smoke", "smoke"))
        self.assertEqual(len(targets), 21)
        self.assertEqual(set(targets), {"zh-CN-light-1440x900-" + scene + ".png" for scene in SMOKE_SCENES})
        matrix, diagnostic, targets = compose.comparison_targets(spec, {"smoke"}, matrix_unknown=True)
        self.assertEqual((matrix, diagnostic, len(targets)), (None, "full", 672))


if __name__ == "__main__":
    unittest.main()
