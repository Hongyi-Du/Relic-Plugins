"""Viewport job partition fixtures; every process/browser/server call is mocked."""
from collections import Counter
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch

import capture
from download_comparison_inputs import artifact_client


class CaptureViewportShardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((capture.HERE / "scenes.json").read_text(encoding="utf-8"))
        cls.workflow = (capture.ROOT / ".github/workflows/native-visual.yml").read_text(encoding="utf-8")
        cls.windows_job = cls.workflow.split("  windows:\n", 1)[1].split("  macos:\n", 1)[0]
        expression = re.search(r"include: \$\{\{ fromJSON\(inputs\.matrix == 'full' && '([^']+)' \|\| '([^']+)'\) \}\}", cls.windows_job)
        if expression is None:
            raise AssertionError("Windows workflow must expose its full and smoke job matrices")
        cls.full_jobs, cls.smoke_jobs = (json.loads(value) for value in expression.groups())

    def test_twelve_actual_workflow_shards_exactly_reproduce_all_672_cases(self):
        # This is the original unsplit Cartesian product, independent of the
        # new helpers and of the workflow's explicit shard list.
        original = [{"id": f"{lang}-{theme}-{width}x{height}-{scene}", "scene": scene,
                     "width": width, "height": height,
                     "file": f"{lang}-{theme}-{width}x{height}-{scene}.png"}
                    for lang in self.spec["languages"] for theme in self.spec["themes"]
                    for width, height in self.spec["sizes"] for scene in self.spec["scenes"]]
        self.assertEqual(len(original), 672)
        self.assertEqual(len(self.full_jobs), 12)
        merged = []
        for job in self.full_jobs:
            with self.subTest(job=job):
                sizes = capture.capture_sizes(self.spec, "full", job["viewport"])
                cases = capture.capture_cases(self.spec["scenes"], sizes, job["lang"], job["theme"])
                self.assertEqual(len(cases), 56)
                self.assertEqual([case["scene"] for case in cases], self.spec["scenes"])
                merged.extend(cases)
        self.assertEqual(merged, original)
        self.assertEqual(Counter(case["id"] for case in merged), Counter(case["id"] for case in original))
        self.assertTrue(all(count == 1 for count in Counter(case["id"] for case in merged).values()))

    def test_smoke_stays_one_original_language_theme_viewport_job(self):
        self.assertEqual(self.smoke_jobs, [{"lang": "zh-CN", "theme": "light", "viewport": "1440x900"}])
        self.assertEqual(capture.capture_sizes(self.spec, "smoke", "1440x900"), [[1440, 900]])
        with self.assertRaisesRegex(ValueError, "smoke remains 1440x900"):
            capture.capture_sizes(self.spec, "smoke", "1280x800")

    def test_only_exact_existing_spec_viewports_are_accepted(self):
        for viewport in ("800x600", "1440X900", "01440x900", "1440x900/../other", "1440x900 ", ""):
            with self.subTest(viewport=viewport), self.assertRaisesRegex(ValueError, "existing scenes.json sizes"):
                capture.capture_sizes(self.spec, "full", viewport)
        self.assertEqual(capture.capture_sizes(self.spec, "full"), self.spec["sizes"])

    def test_focused_diagnostic_does_not_change_the_default_scene_contract(self):
        original = list(self.spec["scenes"])
        self.assertEqual(capture.capture_scenes(self.spec, "full"), original)
        self.assertEqual(len(capture.capture_scenes(self.spec, "smoke")), 22)
        for scene in ("settings-profile", "settings-appearance", "settings-about"):
            self.assertEqual(capture.capture_scenes(self.spec, "smoke", scene), [scene])
        self.assertEqual(self.spec["scenes"], original)
        self.assertEqual(capture.capture_scenes(self.spec, "full"), original)
        for scene in ("", "settings-fake", "../settings-profile"):
            with self.assertRaisesRegex(ValueError, "existing scenes.json scene"):
                capture.capture_scenes(self.spec, "full", scene)

    def test_merge_multiple_cannot_overwrite_other_shards_metadata(self):
        native_metadata, reference_metadata, receipts = [], [], []
        for job in self.full_jobs:
            lang, theme, viewport = job["lang"], job["theme"], job["viewport"]
            work = capture.capture_metadata_directory(Path("visual/windows"), lang, theme, viewport)
            reference = capture.capture_metadata_directory(Path("visual/reference"), lang, theme, viewport)
            self.assertEqual(work, Path("visual/windows/data") / lang / theme / viewport)
            self.assertEqual(capture.capture_fixture_groups(Path("visual/windows"), [lang], [theme], viewport),
                             [(lang, [theme], work)])
            native_metadata.extend(work / name for name in ("manifest.json", "server.log", "fixture.json", "components.json", "complete.json"))
            reference_metadata.append(reference / "complete.json")
            receipts.append(capture.capture_receipt_name(lang, theme, viewport))
        for paths in (native_metadata, reference_metadata, receipts):
            self.assertEqual(len(paths), len(set(paths)))
        for prefix in ("visual-windows", "reference-windows"):
            self.assertIn("name: " + prefix + "-${{ matrix.lang }}-${{ matrix.theme }}-${{ matrix.viewport }}", self.windows_job)

    def test_unfiltered_macos_and_reference_paths_and_deadlines_stay_unchanged(self):
        output = Path("visual/macos")
        self.assertEqual(capture.capture_metadata_directory(output, "en-US", "dark"), output / "data/en-US/dark")
        self.assertEqual(capture.capture_fixture_groups(output, ["en-US"], ["light", "dark"]),
                         [("en-US", ["light", "dark"], output / "data/en-US")])
        self.assertEqual(capture.capture_receipt_name("en-US", "dark"), "capture-complete-en-US-dark.json")
        macos = self.workflow.split("  macos:\n", 1)[1].split("  compare:\n", 1)[0]
        self.assertNotIn("--viewport", macos)
        self.assertNotIn("matrix.viewport", macos)
        self.assertIn("timeout-minutes: 45", self.windows_job)
        self.assertIn("timeout-minutes: 45", macos)
        compare = self.workflow.split("  compare:\n", 1)[1]
        self.assertIn("--output visual/parity --matrix ${{ inputs.matrix || 'smoke' }} --report-only", compare)
        self.assertIn("python scripts/visual/download_comparison_inputs.py --output visual", compare)
        self.assertIn("--report-output visual/parity --report-output visual/comparisons", compare)
        self.assertIn("--reference-root visual/reference --macos-reference-root visual/reference-macos", compare)

    def test_actual_capture_artifact_names_route_all_four_complete_input_families(self):
        # Exercise the production downloader against every actual producer shard,
        # rather than asserting the retired download-artifact YAML implementation.
        routes = []
        for job in self.full_jobs:
            suffix = f"{job['lang']}-{job['theme']}-{job['viewport']}"
            for prefix, expected in (("visual-windows", "windows"), ("reference-windows", "reference")):
                name = prefix + "-" + suffix
                with self.subTest(artifact=name):
                    self.assertEqual(artifact_client(name), expected)
                routes.append(artifact_client(name))
        macos = self.workflow.split("  macos:\n", 1)[1].split("  compare:\n", 1)[0]
        expression = re.search(r"include: \$\{\{ fromJSON\(inputs\.matrix == 'full' && '([^']+)' \|\| '([^']+)'\) \}\}", macos)
        self.assertIsNotNone(expression, "Every macOS producer shard must remain in the transport inventory")
        macos_jobs = json.loads(expression.group(1))
        self.assertEqual(macos_jobs, [{"lang": lang, "theme": theme}
                                     for lang in self.spec["languages"] for theme in self.spec["themes"]])
        for prefix in ("visual-macos", "reference-macos"):
            self.assertIn("name: " + prefix + "-${{ matrix.lang }}-${{ matrix.theme }}", macos)
        for job in macos_jobs:
            for prefix, expected in (("visual-macos", "macos"), ("reference-macos", "reference-macos")):
                name = f"{prefix}-{job['lang']}-{job['theme']}"
                with self.subTest(artifact=name):
                    self.assertEqual(artifact_client(name), expected)
                routes.append(artifact_client(name))
        self.assertEqual(Counter(routes), {"windows": 12, "reference": 12, "macos": 4, "reference-macos": 4})

    def test_main_threads_viewport_through_manifest_fixture_and_both_completion_receipts(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            output = Path(folder) / "windows"
            reference = Path(folder) / "reference"
            fixture = {"home": str(Path(folder) / "fixture-home"), "port": 5555, "token": "mock-only"}
            server = Mock()
            argv = ["capture.py", "--client", "windows", "--matrix", "full", "--lang", "zh-CN", "--theme", "light",
                    "--viewport", "1280x800", "--exe", "Relic.exe", "--uia-exe", "reader.exe", "--reference", "--output", str(output)]

            def components(path, manifest, exe, reference_output):
                self.assertEqual(path, output / "data/zh-CN/light/1280x800/manifest.json")
                self.assertEqual(manifest["viewport_filter"], "1280x800")
                self.assertEqual(manifest["output"], str(output))
                self.assertEqual(len(manifest["cases"]), 56)
                self.assertEqual({(case["width"], case["height"]) for case in manifest["cases"]}, {(1280, 800)})
                self.assertEqual(reference_output, reference)
                reference.mkdir(parents=True)
                return {"errors": [], "components": [{"client": "windows", "count": 56}, {"client": "reference", "count": 56}]}

            with patch("sys.argv", argv), patch.object(capture.subprocess, "Popen", return_value=server) as launch, \
                    patch.object(capture, "wait_file", return_value=fixture), patch.object(capture, "configure"), \
                    patch.object(capture, "capture_components", side_effect=components) as run:
                capture.main()
            run.assert_called_once()
            self.assertEqual(launch.call_args.args[0][-3:], [str(output / "data/zh-CN/light/1280x800"), "--lang", "zh-CN"])
            for root in (output, reference):
                receipt = json.loads((root / "capture-complete-zh-CN-light-1280x800.json").read_text(encoding="utf-8"))
                self.assertEqual(receipt["viewport_filter"], "1280x800")
                self.assertEqual(receipt["count"], 56)
                self.assertEqual(receipt["expected_count"], 56)
                self.assertEqual(receipt["errors"], [])
                self.assertFalse((root / "capture-complete-zh-CN-light.json").exists())
            server.terminate.assert_called_once()
            server.wait.assert_called_once_with(timeout=20)

    def test_reference_worker_aggregate_uses_viewport_directory(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            output = Path(folder) / "reference"
            cases = capture.capture_cases(["group", "file-code"], [[1024, 700]], "en-US", "dark")
            manifest = {"client": "reference", "output": str(output), "lang": "en-US", "theme": "dark",
                        "viewport_filter": "1024x700", "cases": cases, "fixture": {"home": "unchanged-fixture"}}
            paths = []

            def run(path, per_case):
                paths.append(path)
                self.assertEqual(per_case["viewport_filter"], "1024x700")
                self.assertEqual(per_case["fixture"], manifest["fixture"])
                return {"status": "captured", "count": 1, "errors": []}

            with patch.object(capture, "reference_process", side_effect=run):
                receipt = capture.reference(manifest)
            self.assertEqual(receipt["count"], 2)
            work = output / "data/en-US/dark/1024x700"
            self.assertEqual(paths, [work / "cases" / case["id"] / "manifest.json" for case in cases])
            self.assertEqual(json.loads((work / "complete.json").read_text(encoding="utf-8")), receipt)
            self.assertFalse((output / "data/en-US/dark/complete.json").exists())

    def test_invalid_cli_viewport_fails_before_any_process_or_output(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            output = Path(folder) / "must-not-be-created"
            argv = ["capture.py", "--client", "windows", "--viewport", "999x999", "--output", str(output)]
            with patch("sys.argv", argv), patch("sys.stderr", io.StringIO()), patch.object(capture.subprocess, "Popen") as launch:
                with self.assertRaises(SystemExit) as error:
                    capture.main()
            self.assertEqual(error.exception.code, 2)
            launch.assert_not_called()
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
