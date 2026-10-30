"""Pure tests only. Never compile, launch a renderer, or execute an SKP inspector here."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from contract import (CHROMIUM_REVISION, DEPENDENCIES, SKIA_REVISION, browser_binding,
                      require_ci, select_picture, selected_dependencies)
from source_contract import check_source_contract


class SkpContracts(unittest.TestCase):
    # Browser fields recorded from paint-diagnostic-81e93ac / Windows Chromium group.
    BROWSER = {"playwright_browser_version": "156.0.8078.4", "host_platform": "win32",
               "cdp": {"product": "Chrome/156.0.8078.4", "revision": "@" + CHROMIUM_REVISION}}
    DEPS = "'skia_revision': '" + SKIA_REVISION + "',\n"

    def test_recorded_browser_revision_requires_actual_official_deps_value(self):
        binding = browser_binding(self.BROWSER, self.DEPS)
        self.assertEqual(binding["skia_revision"], SKIA_REVISION)
        self.assertEqual(binding["chromium_revision"], CHROMIUM_REVISION)

    def test_other_browser_revision_cannot_use_our_decoder(self):
        browser = {**self.BROWSER, "cdp": {"revision": "@" + "0" * 40}}
        with self.assertRaisesRegex(ValueError, "browser revision"):
            browser_binding(browser, self.DEPS)

    def test_other_skia_or_ambiguous_deps_is_not_accepted(self):
        for deps in (self.DEPS.replace(SKIA_REVISION, "0" * 40), self.DEPS * 2, ""):
            with self.subTest(deps=deps), self.assertRaises(ValueError):
                browser_binding(self.BROWSER, deps)

    def test_macos_capture_does_not_silently_use_windows_font_factory(self):
        with self.assertRaisesRegex(ValueError, "Windows capture"):
            browser_binding({**self.BROWSER, "host_platform": "darwin"}, self.DEPS)

    def test_entrypoint_refuses_non_ci_before_any_process(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, "only in GitHub Actions"):
            require_ci()

    def test_only_exact_official_literal_dependency_entries_are_selected(self):
        source = "\n".join(f'"{name}": "https://skia.googlesource.com/example@{SKIA_REVISION}",' for name in DEPENDENCIES)
        source += '\n"third_party/externals/dawn": "https://example.invalid/large@' + SKIA_REVISION + '",'
        self.assertEqual(tuple(selected_dependencies(source)), DEPENDENCIES)

    def test_missing_or_duplicate_dependency_is_explicit_error(self):
        source = "\n".join(f'"{name}": "https://skia.googlesource.com/example@{SKIA_REVISION}",' for name in DEPENDENCIES)
        with self.assertRaises(ValueError):
            selected_dependencies(source + "\n" + source.splitlines()[0])
        with self.assertRaises(ValueError):
            selected_dependencies("\n".join(source.splitlines()[1:]))

    def picture_fixture(self, directory):
        root = Path(directory)
        (root / "pictures").mkdir()
        data = b"skiapict" + bytes.fromhex("6e00000000000000") + b"mock-no-decoding"
        (root / "pictures/one.skp").write_bytes(data)
        entry = {"file": "pictures/one.skp", "byte_count": len(data), "first_16_bytes_hex": data[:16].hex(),
                 "trace_json_pointer": "/traceEvents/334/args/snapshot/skp64", "final_scene_attribution": None}
        (root / "pictures.json").write_text(json.dumps({"pictures": [entry], "errors": ["retained trace problem"]}))
        return root, entry

    def test_exact_original_picture_receipt_does_not_imply_final_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            root, entry = self.picture_fixture(directory)
            path, receipt = select_picture(root, "pictures/one.skp")
            self.assertEqual(path.name, "one.skp")
            self.assertEqual(receipt["entry"], entry)
            self.assertIsNone(receipt["final_png_attribution"])
            self.assertEqual(receipt["picture_extraction_errors"], ["retained trace problem"])
            self.assertFalse(receipt["canonical_output"])

    def test_tampered_picture_byte_count_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.picture_fixture(directory)
            (root / "pictures/one.skp").write_bytes(b"skiapictbad")
            with self.assertRaisesRegex(ValueError, "do not match"):
                select_picture(root, "pictures/one.skp")

    def test_ambiguous_picture_receipt_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root, entry = self.picture_fixture(directory)
            (root / "pictures.json").write_text(json.dumps({"pictures": [entry, entry]}))
            with self.assertRaisesRegex(ValueError, "unique"):
                select_picture(root, "pictures/one.skp")

    def test_picture_cannot_escape_actual_case(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "inside"):
            select_picture(Path(directory), "../other.skp")

    def test_missing_source_checkout_cannot_claim_private_api_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            result = check_source_contract(Path(directory))
            self.assertEqual(result["status"], "failed")
            self.assertTrue(result["errors"])
            self.assertTrue(all(not check["matched"] for check in result["checks"]))

    def test_observer_keeps_positional_forms_and_never_uses_experimental_point_view(self):
        source = Path(__file__).with_name("probe.cpp").read_text(encoding="utf-8")
        self.assertIn("SkTextBlobRunIterator it(blob)", source)
        self.assertIn("mode==0?0:mode==1?1:mode==2?2:mode==3?4:99", source)
        self.assertIn("it.pos()[i]", source)
        self.assertNotIn("experimentalNext", source)
        self.assertNotIn("it.points()", source)
        self.assertNotIn("getWidths", source)

    def test_actual_decode_failure_blocks_playback_and_no_font_fallback_is_requested(self):
        source = Path(__file__).with_name("probe.cpp").read_text(encoding="utf-8")
        self.assertIn("SkTypeface::MakeDeserialize(&stream,nullptr)", source)
        self.assertIn("tf->countGlyphs()<=0", source)
        self.assertIn("if(picture && ctx.errors.empty())", source)
        self.assertNotIn("SkTypeface::MakeEmpty(", source)
        self.assertNotIn("makeFromName", source)
        self.assertIn("SkCanvas::onDrawPicture(picture,matrix,paint)", source)


if __name__ == "__main__":
    unittest.main()
