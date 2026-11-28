"""Synthetic native-fill contract tests, not recorded AppKit draw evidence.

Only JSON and temporary files are used. Run in CI; no application, screenshot,
server or drawing process is started by this suite.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from element_parity import read_capture, validate_capture
from macos_surface_fill import (FRAME_SOURCE, PROVIDER, SCREEN_SPACE, SOURCE,
                                STRUCTURE, fill_observation, path_commands,
                                read_fill_observations)
from test_element_parity import capture


SCENE = "zh-CN-light-1440x900-settings-appearance"
VIEWPORT = {"width": 1440, "height": 900, "scale": 1}


def synthetic_fill():
    """The producer's exported shape, with explicitly synthetic object identities."""
    return {
        "source": SOURCE, "owner_identifier": "synthetic-dialog", "region": "dialog",
        "native_structure": {"source": STRUCTURE, "parent_identifier": "synthetic-dialog",
            "native_subview_path": [0, 3, 1], "view_identity": "synthetic-fill-view",
            "window_identity": "synthetic-window"},
        "opacity_ancestry": [{"identity": "synthetic-fill-view", "class": "NativeSurfaceFillView", "alpha": 1},
            {"identity": "synthetic-parent", "class": "NSView", "alpha": 0.75}],
        "occlusion_proven": False,
        "measurement_limit": "A current actual fill is not proof of final screenshot compositing order or covered-element invisibility",
        "current_draw": {"provider": PROVIDER, "draw_returned": True, "sequence": 4, "revision": 2,
            "view_identity": "synthetic-fill-view", "window_identity": "synthetic-window",
            "local_bounds": {"x": 0, "y": 0, "width": 920, "height": 640},
            "local_path": "M0 0 L920 0 L920 640 L0 640 Z",
            "fill": [246, 245, 241, 255], "fill_rule": "nonzero", "global_alpha": 1,
            "blend_mode": "normal", "antialias": True,
            "context_ctm": [2, 0, 0, -2, 0, 1280],
            "context_clip": {"x": 0, "y": 0, "width": 920, "height": 640}},
        "screen_bounds": {"x": 350, "y": 240, "width": 920, "height": 640},
        "screen_clip": {"x": 350, "y": 240, "width": 920, "height": 640},
        "content_screen_frame": {"source": FRAME_SOURCE, "coordinate_space": SCREEN_SPACE,
            "window_identity": "synthetic-window",
            "bounds": {"x": 90, "y": 110, "width": 1440, "height": 900}},
        "errors": [],
    }


def synthetic_capture(draws=None):
    data = capture("macos", scene=SCENE)
    data["raw_tree"] = SCENE + ".ax.json"
    data["coverage"]["unmeasured"] = ["Exact opaque-overlay occlusion"]
    data["extraction_errors"] = [{"type": "fixture_existing_failure", "detail": "Retain this actual capture failure"}]
    if draws is not None:
        data["capture_evidence"] = {"native_fill_draws": draws}
    return data


def sidecar(draws):
    return {"client": "macos", "caseId": SCENE,
            "viewport": {"width": 1440, "height": 900}, "native_fill_draws": draws}


class MacSurfaceFillTests(unittest.TestCase):
    def test_current_submitted_draw_preserves_all_raw_inputs_but_never_proves_occlusion(self):
        item = synthetic_fill()
        original = deepcopy(item)
        result = fill_observation(item)
        self.assertTrue(result["draw_observation_valid"], result["issues"])
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["raw"], original)
        self.assertEqual(result["measurements"]["draw"], original["current_draw"])
        self.assertEqual(result["measurements"]["opacity_ancestry"], original["opacity_ancestry"])
        self.assertEqual(result["measurements"]["content_screen_frame"], original["content_screen_frame"])
        self.assertEqual(result["measurements"]["screen_bounds"], original["screen_bounds"])
        self.assertEqual(item, original)
        for key in ("occlusion_proven", "presentation_identity_proven", "relative_compositing_order_proven"):
            self.assertFalse(result[key])
        # Neither alpha ancestry nor a fully opaque submitted fill makes an
        # independently captured element behind this painter disappear.
        self.assertNotIn("covered_elements", result)
        self.assertNotIn("effective_alpha", result["measurements"])

    def test_path_parser_preserves_actual_line_quadratic_cubic_commands(self):
        commands = path_commands("M1e-2 -3 L4 5 Q6 7 8 9 C10 11 12 13 14 15 Z")
        self.assertEqual([item["command"] for item in commands], ["M", "L", "Q", "C", "Z"])
        self.assertEqual(commands[0]["coordinates"], [0.01, -3])
        self.assertEqual(commands[3]["coordinates"], [10, 11, 12, 13, 14, 15])
        for invalid in (None, [], "", "L0 0", "M0", "M0 0 A2 2 0 0 1 4 4", "M0 0 ?", "M1e999 0", "M0 0 NaN 2", "M0 0 2 3"):
            with self.subTest(invalid=invalid):
                self.assertIsNone(path_commands(invalid))

    def test_stale_or_unmounted_current_draw_never_borrows_last_draw(self):
        item = synthetic_fill()
        item["last_draw"] = deepcopy(item["current_draw"])
        item["current_draw"] = None
        item["errors"] = ["No current mounted native fill draw"]
        result = fill_observation(item)
        self.assertFalse(result["draw_observation_valid"])
        self.assertIsNone(result["measurements"])
        self.assertEqual(result["raw"]["last_draw"], item["last_draw"])
        self.assertTrue(any("No current mounted" in issue for issue in result["issues"]))

    def test_foreign_missing_and_malformed_draw_sources_fail_without_inference(self):
        mutations = [
            lambda d: d.update(source="other painter"),
            lambda d: d.update(region=[]),
            lambda d: d.update(occlusion_proven=True),
            lambda d: d.update(errors=["producer failure"]),
            lambda d: d["current_draw"].update(provider="expected reference path"),
            lambda d: d["current_draw"].update(draw_returned=False),
            lambda d: d["current_draw"].update(sequence=True),
            lambda d: d["current_draw"].update(revision=-1),
            lambda d: d["native_structure"].update(view_identity="another-view"),
            lambda d: d["native_structure"].update(window_identity=None),
            lambda d: d["native_structure"].update(parent_identifier="another-owner"),
            lambda d: d["native_structure"].update(native_subview_path=[True]),
            lambda d: d["native_structure"].update(native_subview_path=None),
            lambda d: d.update(opacity_ancestry=[]),
            lambda d: d["opacity_ancestry"][0].update(identity="other-view"),
            lambda d: d["opacity_ancestry"][0].update(alpha=None),
            lambda d: d["opacity_ancestry"].append(deepcopy(d["opacity_ancestry"][0])),
            lambda d: d["current_draw"].update(local_path="M0 0 ?"),
            lambda d: d["current_draw"].update(fill=[0, 0, 0, 256]),
            lambda d: d["current_draw"].update(global_alpha=0.5),
            lambda d: d["current_draw"].update(context_ctm=[1, 0, 0, 1, 0, float("nan")]),
            lambda d: d["current_draw"].update(context_clip=None),
            lambda d: d.update(screen_clip=None),
            lambda d: d["content_screen_frame"].update(window_identity="another-window"),
            lambda d: d["content_screen_frame"].update(coordinate_space="content top-left"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                item = synthetic_fill()
                mutate(item)
                result = fill_observation(item)
                self.assertFalse(result["draw_observation_valid"])
                self.assertIsNone(result["measurements"])
                self.assertTrue(result["issues"])
                self.assertFalse(result["occlusion_proven"])

    def test_unnamed_production_parent_is_not_assigned_to_a_guessed_canonical_owner(self):
        item = synthetic_fill()
        item["owner_identifier"] = None
        item["native_structure"]["parent_identifier"] = None
        result = fill_observation(item)
        self.assertTrue(result["draw_observation_valid"], result["issues"])
        self.assertIsNone(result["measurements"]["owner_identifier"])

    def test_initial_unchanged_configuration_can_have_real_revision_zero(self):
        item = synthetic_fill()
        item["current_draw"]["revision"] = 0
        result = fill_observation(item)
        self.assertTrue(result["draw_observation_valid"], result["issues"])
        self.assertEqual(result["measurements"]["draw"]["revision"], 0)

    def test_embedded_evidence_needs_no_sidecar_or_artifact_link_read_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            data = synthetic_capture([synthetic_fill()])
            audit = read_fill_observations(data, Path(directory) / (SCENE + ".elements.json"), SCENE, VIEWPORT)
        self.assertEqual(audit["status"], "observed")
        self.assertEqual(audit["observed_draw_count"], 1)
        self.assertEqual(audit["inputs_read"], ["elements.capture_evidence.native_fill_draws"])

    def test_actual_local_sidecar_is_read_with_exact_scene_and_coordinate_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / (SCENE + ".elements.json")
            raw_path = path.with_name(SCENE + ".ax.json")
            raw_path.write_text(json.dumps(sidecar([synthetic_fill()])), encoding="utf-8")
            audit = read_fill_observations(synthetic_capture(), path, SCENE, VIEWPORT)
            self.assertEqual(audit["status"], "observed")
            self.assertEqual(audit["inputs_read"], [raw_path.name])
            self.assertEqual(audit["observations"][0]["raw"], synthetic_fill())
            for key, wrong in (("client", "windows"), ("caseId", "other-scene"), ("viewport", {"width": 1280, "height": 800})):
                with self.subTest(key=key):
                    raw = sidecar([synthetic_fill()]); raw[key] = wrong
                    raw_path.write_text(json.dumps(raw), encoding="utf-8")
                    bad = read_fill_observations(synthetic_capture(), path, SCENE, VIEWPORT)
                    self.assertEqual(bad["observations"], [])
                    self.assertTrue(any("case/client/viewport" in issue for issue in bad["issues"]))

    def test_embedded_and_raw_must_preserve_the_same_observation_not_two_capture_instants(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / (SCENE + ".elements.json")
            raw_path = path.with_name(SCENE + ".ax.json")
            draws = [synthetic_fill()]
            raw_path.write_text(json.dumps(sidecar(draws)), encoding="utf-8")
            data = synthetic_capture(draws)
            self.assertEqual(read_fill_observations(data, path, SCENE, VIEWPORT)["issues"], [])
            different = deepcopy(draws); different[0]["current_draw"]["sequence"] += 1
            raw_path.write_text(json.dumps(sidecar(different)), encoding="utf-8")
            audit = read_fill_observations(data, path, SCENE, VIEWPORT)
            self.assertEqual(audit["status"], "observed-with-errors")
            self.assertEqual(audit["observations"][0]["raw"], draws[0])
            self.assertEqual(audit["conflicting_raw_observations"], different)
            self.assertTrue(any("differ from" in issue for issue in audit["issues"]))

    def test_missing_receipt_stays_unavailable_and_cannot_be_supplied_by_link(self):
        with tempfile.TemporaryDirectory() as directory:
            data = synthetic_capture()
            data["raw_evidence"] = [{"name": SCENE + ".ax.json", "artifact_url": "https://example.invalid/raw.zip"}]
            audit = read_fill_observations(data, Path(directory) / (SCENE + ".elements.json"), SCENE, VIEWPORT)
        self.assertEqual(audit["status"], "unavailable")
        self.assertEqual(audit["inputs_read"], [])
        self.assertEqual(audit["observations"], [])
        self.assertFalse(audit["occlusion_proven"])

    def test_duplicate_actual_view_and_malformed_array_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / (SCENE + ".elements.json")
            for value in (None, {}, "fill", [synthetic_fill(), synthetic_fill()]):
                with self.subTest(value=type(value).__name__):
                    data = synthetic_capture()
                    data["capture_evidence"] = {"native_fill_draws": value}
                    audit = read_fill_observations(data, path, SCENE, VIEWPORT)
                    self.assertTrue(audit["issues"])
                    self.assertFalse(audit["occlusion_proven"])

    def test_empty_actual_array_is_observed_without_inventing_global_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = read_fill_observations(synthetic_capture([]), Path(directory) / (SCENE + ".elements.json"), SCENE, VIEWPORT)
        self.assertEqual(audit["status"], "observed")
        self.assertEqual(audit["observed_draw_count"], 0)
        self.assertFalse(audit["occlusion_proven"])

    def test_read_capture_exposes_audit_but_preserves_elements_unknowns_and_previous_errors(self):
        data = synthetic_capture([synthetic_fill()])
        prior_errors = validate_capture(data, "macos", SCENE, VIEWPORT)
        self.assertTrue(prior_errors)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / (SCENE + ".elements.json")
            path.write_text(json.dumps(data), encoding="utf-8")
            result, errors = read_capture(path, "macos", SCENE, VIEWPORT)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), data)
        self.assertEqual(result["elements"], data["elements"])
        self.assertEqual(result["coverage"], data["coverage"])
        self.assertEqual(result["extraction_errors"], data["extraction_errors"])
        self.assertEqual(result["capture_evidence"], data["capture_evidence"])
        self.assertEqual(errors, prior_errors)
        self.assertEqual(result["_native_fill_audit"]["observed_draw_count"], 1)
        self.assertFalse(result["_native_fill_audit"]["occlusion_proven"])

    def test_read_capture_keeps_original_failure_and_adds_malformed_receipt_error(self):
        data = synthetic_capture([synthetic_fill()])
        data["capture_evidence"]["native_fill_draws"][0]["current_draw"] = None
        prior_errors = validate_capture(data, "macos", SCENE, VIEWPORT)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / (SCENE + ".elements.json")
            path.write_text(json.dumps(data), encoding="utf-8")
            result, errors = read_capture(path, "macos", SCENE, VIEWPORT)
        self.assertEqual(errors[:len(prior_errors)], prior_errors)
        self.assertTrue(any("Native surface fill evidence" in error["reason"] for error in errors[len(prior_errors):]))
        self.assertEqual(result["elements"], data["elements"])


if __name__ == "__main__":
    unittest.main()
