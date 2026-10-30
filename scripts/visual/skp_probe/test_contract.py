"""Pure tests only. Never compile, launch a renderer, or execute an SKP inspector here."""
from __future__ import annotations

import json
import base64
import copy
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from contract import (CHROMIUM_REVISION, DEPENDENCIES, EXISTING_BATCH, SKIA_REVISION, browser_binding,
                      inventory_pictures, require_ci, require_existing_batch, select_picture, selected_dependencies)
from source_contract import check_source_contract
import run_ci


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


class SkpBatchContracts(unittest.TestCase):
    """Synthetic trace/byte fixtures. No actual SKP inspector executes here."""

    def fixture(self, directory):
        case = Path(directory) / "case"
        (case / "pictures").mkdir(parents=True)
        bodies = [b"skiapict" + b"fixture-A-00000000", b"skiapict" + b"fixture-A-00000000",
                  b"skiapict" + b"fixture-B-00000000", b"skiapict" + b"fixture-C-00000000"]
        events = [{"name": "process_name", "ph": "M", "pid": 10, "tid": 1, "args": {"name": "Browser"}},
                  {"name": "process_name", "ph": "M", "pid": 20, "tid": 2, "args": {"name": "Renderer"}}]
        entries = []
        for i, data in enumerate(bodies):
            relative = f"pictures/picture-{i:05d}.skp"
            (case / relative).write_bytes(data)
            event_index = len(events)
            event = {"name": "cc::DisplayItemList:snapshot", "cat": "fixture-picture-category", "ph": "I",
                     "ts": 100 + i, "pid": 10 if i == 0 else 20, "tid": 1 if i == 0 else 2,
                     "args": {"snapshot": {"skp64": base64.b64encode(data).decode("ascii")}}}
            events.append(event)
            entries.append({"file": relative, "byte_count": len(data), "first_16_bytes_hex": data[:16].hex(),
                            "event_index": event_index, "trace_json_pointer": f"/traceEvents/{event_index}/args/snapshot/skp64",
                            "event": {key: event.get(key) for key in ("name", "cat", "ph", "ts", "pid", "tid", "id")},
                            "layer_id": None, "parsed_skp": None, "final_scene_attribution": None})
        events.append({"name": "cc::DisplayItemList:snapshot", "cat": "fixture-picture-category", "ph": "s",
                       "id": 7, "pid": 20, "tid": 2, "ts": 101, "args": {}})
        trace = {"traceEvents": events, "metadata": {"fixture": "not a recorded trace"}}
        loss = {"nonzero_loss_evidence": [{"trace_json_pointer": "/metadata/fixture_loss", "value": 19}],
                "final_scene_attribution": None}
        (case / "trace.json").write_text(json.dumps(trace))
        (case / "trace-diagnostics.json").write_text(json.dumps(loss))
        (case / "pictures.json").write_text(json.dumps({"trace_event_count": len(events), "pictures": entries, "errors": []}))
        return case, entries, trace, loss

    def test_every_alias_retains_exact_original_event_even_when_bytes_are_shared_across_pids(self):
        with tempfile.TemporaryDirectory() as directory:
            case, entries, _, loss = self.fixture(directory)
            inventory = inventory_pictures(case)
            self.assertEqual(inventory["input_errors"], [])
            self.assertEqual(inventory["counts"]["alias_count"], 4)
            self.assertEqual(inventory["counts"]["unique_count"], 3)
            self.assertEqual(inventory["unique_inputs"][0]["alias_indexes"], [0, 1])
            self.assertEqual([row["entry"] for row in inventory["aliases"]], entries)
            self.assertEqual([row["trace_event"]["pid"] for row in inventory["aliases"]], [10, 20, 20, 20])
            self.assertEqual(inventory["aliases"][1]["coincident_flow_event_indexes"], [6])
            self.assertEqual(inventory["trace_flow_events"][0]["event"]["id"], 7)
            self.assertEqual(inventory["trace_diagnostics"], loss)
            self.assertFalse(inventory["trace_completeness_proven"])
            self.assertIsNone(inventory["dom_source_attribution"])
            self.assertIsNone(inventory["final_png_attribution"])
            self.assertTrue(all(row["dom_source_attribution"] is None for row in inventory["aliases"]))

    def test_trace_payload_mismatch_retains_failed_alias_and_other_valid_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            case, _, trace, _ = self.fixture(directory)
            trace["traceEvents"][2]["args"]["snapshot"]["skp64"] = base64.b64encode(b"skiapict-different").decode("ascii")
            (case / "trace.json").write_text(json.dumps(trace))
            inventory = inventory_pictures(case)
            self.assertEqual(len(inventory["aliases"]), 4)
            self.assertEqual(inventory["aliases"][0]["status"], "input-error")
            self.assertIn("trace skp64 bytes differ", inventory["aliases"][0]["errors"][0])
            self.assertEqual(inventory["counts"]["verified_alias_count"], 3)
            with self.assertRaisesRegex(ValueError, "input bindings failed"):
                require_existing_batch(inventory)

    def test_event_pointer_metadata_and_file_escape_cannot_manufacture_source_identity(self):
        for fault in ("event", "pointer", "escape", "duplicate"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                case, entries, trace, _ = self.fixture(directory)
                if fault == "event": entries[0]["event"]["pid"] = 12345
                elif fault == "pointer": entries[0]["trace_json_pointer"] = "/traceEvents/3/args/snapshot/skp64"
                elif fault == "escape": entries[0]["file"] = "../outside.skp"
                else: entries[1] = copy.deepcopy(entries[0])
                (case / "pictures.json").write_text(json.dumps({"pictures": entries, "trace_event_count": len(trace["traceEvents"])}))
                inventory = inventory_pictures(case)
                self.assertEqual(len(inventory["aliases"]), 4)
                self.assertTrue(inventory["input_errors"])
                self.assertIsNone(inventory["final_png_attribution"])

    def test_missing_loss_receipt_is_unknown_not_a_claim_of_lossless_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            case, *_ = self.fixture(directory)
            (case / "trace-diagnostics.json").unlink()
            inventory = inventory_pictures(case)
            self.assertIsNone(inventory["trace_diagnostics"])
            self.assertFalse(inventory["trace_completeness_proven"])

    def test_fixed_existing_batch_rejects_any_size_count_or_partial_selection_change(self):
        valid = {"counts": dict(EXISTING_BATCH), "input_errors": []}
        require_existing_batch(valid)
        for key in EXISTING_BATCH:
            changed = copy.deepcopy(valid)
            changed["counts"][key] -= 1
            with self.subTest(quantity=key), self.assertRaisesRegex(ValueError, "existing 81e93ac inventory"):
                require_existing_batch(changed)

    def test_failed_unique_decode_does_not_stop_later_unique_or_discard_no_text_and_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            case, *_ = self.fixture(directory)
            inventory = inventory_pictures(case)
            output = Path(directory) / "output"
            calls = []
            def decoder(argv, **kwargs):
                calls.append(argv)
                attempt = len(calls)
                raw = {"status": "failed" if attempt == 2 else "decoded", "errors": ["fixture decode error"] if attempt == 2 else [],
                       "draw_text_blobs": [] if attempt == 1 else [{"fixture": True}], "typefaces": []}
                (Path(argv[2]) / "raw.json").write_text(json.dumps(raw))
                return SimpleNamespace(returncode=3 if attempt == 2 else 0)
            with patch.object(run_ci.subprocess, "run", side_effect=decoder):
                result = run_ci.decode_all_unique(case, Path("fixture-not-launched.exe"), output, inventory)
            self.assertEqual(len(calls), 3)
            self.assertEqual(result["decoder_call_attempt_count"], 3)
            self.assertEqual(result["decoded_count"], 2)
            self.assertEqual(result["failed_count"], 1)
            self.assertEqual(result["decoded_no_text_count"], 1)
            self.assertEqual(result["status"], "completed-with-decode-failures")
            self.assertEqual(result["unique_results"][0]["alias_indexes"], [0, 1])
            self.assertEqual(result["unique_results"][2]["status"], "decoded-diagnostic-only")
            self.assertTrue(result["completed"])
            self.assertFalse(result["canonical_output"])
            self.assertEqual(json.loads((output / "batch.json").read_text()), result)
            for item in result["unique_results"]:
                self.assertTrue((output / item["retained_input"]).is_file())
                self.assertTrue((output / item["output_directory"] / "raw.json").is_file())

    def test_timeout_keeps_partial_raw_output_and_attempts_remaining_uniques(self):
        with tempfile.TemporaryDirectory() as directory:
            case, *_ = self.fixture(directory)
            output = Path(directory) / "output"
            calls = []
            def decoder(argv, **kwargs):
                calls.append(argv)
                (Path(argv[2]) / "raw.json").write_text(json.dumps({"status": "decoded", "errors": [], "draw_text_blobs": [], "typefaces": []}))
                if len(calls) == 1:
                    raise run_ci.subprocess.TimeoutExpired(argv, 120)
                return SimpleNamespace(returncode=0)
            with patch.object(run_ci.subprocess, "run", side_effect=decoder):
                result = run_ci.decode_all_unique(case, Path("fixture-not-launched.exe"), output, inventory_pictures(case))
            self.assertEqual(len(calls), 3)
            self.assertEqual(result["failed_count"], 1)
            first = result["unique_results"][0]
            self.assertTrue((output / first["output_directory"] / "raw.json").exists())
            self.assertIn("TimeoutExpired", first["decode"]["errors"][0])
            self.assertEqual(result["unique_results"][-1]["status"], "decoded-diagnostic-only")

    def test_changed_retained_input_fails_before_decoder_and_does_not_skip_other_uniques(self):
        with tempfile.TemporaryDirectory() as directory:
            case, *_ = self.fixture(directory)
            inventory = inventory_pictures(case)
            (case / inventory["unique_inputs"][0]["representative_file"]).write_bytes(b"changed-after-inventory")
            def decoder(argv, **kwargs):
                (Path(argv[2]) / "raw.json").write_text(json.dumps({"status": "decoded", "errors": [], "draw_text_blobs": [], "typefaces": []}))
                return SimpleNamespace(returncode=0)
            with patch.object(run_ci.subprocess, "run", side_effect=decoder) as call:
                result = run_ci.decode_all_unique(case, Path("fixture-not-launched.exe"), Path(directory) / "output", inventory)
            self.assertEqual(call.call_count, 2)
            self.assertIn("input changed", result["unique_results"][0]["error"])
            self.assertEqual(result["failed_count"], 1)


if __name__ == "__main__":
    unittest.main()
