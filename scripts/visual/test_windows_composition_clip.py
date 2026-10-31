"""Synthetic real-API-shaped Composition clip receipts; CI only, no UI."""
from copy import deepcopy
from pathlib import Path
import re
import unittest

from windows_composition_clip import (SOURCE, RETAINED_SOURCE, PREPARED_SOURCE, PREPARED_BINDING, PREFIX, IDENTITY3, IDENTITY4,
                                      composition_clip, apply_composition_clip)


def sample(radius=5):
    local = {"x": 0, "y": 0, "width": 18, "height": 18}
    matrix = {"m11": 1, "m12": 0, "m21": 0, "m22": 1, "offset_x": 12, "offset_y": 10.5}
    before = {
        "visual": {"type": PREFIX + "ContainerVisual", "size": [18, 18], "offset": [12, 10.5, 0],
                   "anchor_point": [0, 0], "center_point": [0, 0, 0], "scale": [1, 1, 1],
                   "rotation_angle": 0, "rotation_axis": [0, 0, 1], "transform_matrix": list(IDENTITY4)},
        "clip_present": True,
        "clip": {"type": PREFIX + "CompositionGeometricClip", "anchor_point": [0, 0], "center_point": [0, 0],
                 "offset": [0, 0], "scale": [1, 1], "rotation_angle": 0, "transform_matrix": list(IDENTITY3),
                 "geometry": {"type": PREFIX + "CompositionRoundedRectangleGeometry", "size": [18, 18],
                              "offset": [0, 0], "corner_radius": [radius, radius],
                              "trim_start": 0, "trim_end": 1, "trim_offset": 0}}}
    node = {"id": "image-1", "type": "Image", "local_bounds": local,
            "bounds": {"x": 12, "y": 10.5, "width": 18, "height": 18}, "transform": matrix, "clip": None}
    node["composition_clip_evidence"] = {
        "fixture": "synthetic actual-API shape, not a production observation",
        "source": SOURCE, "status": "measured", "owner_id": node["id"], "owner_is_loaded": True,
        "owner_type": "Image", "owner_runtime_type": "Microsoft.UI.Xaml.Controls.Image",
        "owner_local_bounds": deepcopy(local), "owner_to_window": deepcopy(matrix), "xaml_clip_present": False,
        "before": before, "after": deepcopy(before), "properties_stable": True, "presentation_identity_proven": False,
        "binding": {"source": "actual IUnknown identity comparison; acquired references released in finally",
                    "visual_same_object_after": True, "clip_same_object_after": True, "geometry_same_object_after": True}}
    return node


def change_snapshot(node, mutator):
    raw = node["composition_clip_evidence"]
    mutator(raw["before"])
    raw["after"] = deepcopy(raw["before"])


def retained_sample():
    node = sample()
    node["composition_clip_evidence"].update(
        source=RETAINED_SOURCE, backing_visual_read=True, production_backing_visual_binding_available=True,
        production_binding={
            "source": "Actual ClipToolbarLogo assignment and retained owner/root/Visual fields",
            "owner_same_object": True, "owner_is_current_logo": True, "same_xaml_root": True,
            "owner_is_loaded_after": True, "visual_same_retained_object": True,
            "clip_is_installed_production_object": True, "geometry_is_installed_production_object": True,
            "read_only": True, "revision_before": 7, "revision_after": 7})
    return node


def prepared_sample(absent=False):
    """Synthetic new preparation contract; not an observed native capture."""
    node = sample()
    if absent:
        change_snapshot(node, lambda snapshot: snapshot.update(clip_present=False, clip=None))
    raw = node["composition_clip_evidence"]
    raw.update(source=PREPARED_SOURCE, backing_visual_read=True, production_backing_visual_binding_available=False)
    raw["binding"]["source"] = PREPARED_BINDING
    state = {"owner_identity": "0x11", "root_identity": "0x22", "visual_identity": "0x33",
             "clip_identity": None if absent else "0x44", "geometry_identity": None if absent else "0x55",
             "retained_baseline_clip_identity": None if absent else "0x44",
             "retained_baseline_geometry_identity": None if absent else "0x55",
             "owner_is_loaded": True, "owner_unloaded_since_setup": False, "same_xaml_root": True,
             "same_retained_owner": True, "owner_local_bounds": deepcopy(node["local_bounds"]),
             "owner_to_window": deepcopy(node["transform"]), "xaml_clip_present": False,
             "properties": deepcopy(raw["before"])}
    receipt = {"capture_owner_same_object": True, "read_only_authoritative_window": True,
               "production_original_state_observed": False,
               "setup": {"case_id": "synthetic-scene", "started_qpc": 1, "completed_qpc": 4,
                         "qpc_frequency": 10000000, "may_create": True, "created_unknown": True,
                         "production_original_state_observed": False, "owner_count": 1},
               "owner_call": {"index": 0, "api": "ElementCompositionPreview.GetElementVisual(actual owner)",
                              "started_qpc": 2, "completed_qpc": 3, "may_create": True, "created_unknown": True,
                              "returned": True, "owner_identity": "0x11", "root_identity": "0x22", "visual_identity": "0x33"},
               "render_preparation": {"case_id": "synthetic-scene", "failure": None,
                   "render_cycle": {"redraw_request_started_qpc": 5, "redraw_request_completed_qpc": 6,
                                    "rendering": {"source": "CompositionTarget.Rendering", "qpc": 7},
                                    "rendered": {"source": "CompositionTarget.Rendered", "qpc": 8}},
                   "request_commit": {"source": "Window.Compositor.RequestCommitAsync", "started_qpc": 9,
                                      "completed_qpc": 10, "completed": True},
                   "dwm_flush": {"source": "DwmFlush", "started_qpc": 11, "completed_qpc": 12, "hresult": 0}}}
    for index, label in enumerate(("baseline", "before_desktop_readback", "after_desktop_readback", "before_getters", "after_getters")):
        receipt[label] = {"started_qpc": 13 + index * 2, "completed_qpc": 14 + index * 2, "state": deepcopy(state)}
    raw["diagnostic_preparation"] = receipt
    return node


class CompositionClipTests(unittest.TestCase):
    def test_authoritative_collection_without_retained_visual_is_unknown_not_absent(self):
        # Pure fixture of the new collector contract, not an SDK observation.
        # Even a missing UIElement.Clip says nothing about the backing Visual.
        for xaml_clip in (None, {"kind": "rectangle", "bounds": {"x": 12, "y": 10.5, "width": 18, "height": 18}}):
            with self.subTest(xaml_clip=xaml_clip):
                node = sample(); node["clip"] = deepcopy(xaml_clip)
                node["composition_clip_evidence"] = {
                    "source": "Actual XAML owner; backing Visual not read during authoritative capture",
                    "status": "not-measured", "owner_id": node["id"], "owner_type": "Image",
                    "owner_runtime_type": "Microsoft.UI.Xaml.Controls.Image", "owner_is_loaded": True,
                    "owner_local_bounds": deepcopy(node["local_bounds"]),
                    "owner_to_window": deepcopy(node["transform"]), "xaml_clip_present": xaml_clip is not None,
                    "backing_visual_read": False, "production_backing_visual_binding_available": False,
                    "before": None, "after": None, "binding": None, "properties_stable": None,
                    "reason": "No production-retained backing Visual/owner binding is available.",
                    "presentation_identity_proven": False}
                original = deepcopy(node)
                audit, gaps = composition_clip(node)
                self.assertEqual(audit["status"], "unavailable")
                self.assertEqual(audit["xaml_clip"], xaml_clip)
                self.assertIsNone(audit["window_geometry"])
                self.assertIsNone(audit["image_corner_radius"])
                self.assertTrue(any(g["property"] == "clip.composition" for g in gaps))
                self.assertEqual(audit["raw"], node["composition_clip_evidence"])
                self.assertEqual(node, original)

    def test_unmeasured_status_cannot_be_overridden_by_an_old_absent_snapshot(self):
        node = sample()
        change_snapshot(node, lambda s: s.update(clip_present=False, clip=None))
        node["composition_clip_evidence"].update(status="not-measured", backing_visual_read=False)
        audit, gaps = composition_clip(node)
        self.assertEqual(audit["status"], "unavailable")
        self.assertIsNone(audit["window_geometry"])
        self.assertTrue(gaps)

    def test_authoritative_clip_collector_does_not_create_a_handoff_visual(self):
        # A source-contract regression: running this test never loads WinUI or
        # an app. The SDK getter has creation side effects despite its name.
        root = Path(__file__).resolve().parents[2]
        for relative in ("native/windows/Relic/CompositionClipCapture.cs", "native/windows/Relic/ElementCapture.cs"):
            source = (root / relative).read_text(encoding="utf-8-sig")
            with self.subTest(source=relative):
                self.assertIsNone(re.search(r"\bGetElementVisual\s*\(", source))
                self.assertIsNone(re.search(r"\bSetElementChildVisual\s*\(", source))
        collector = (root / "native/windows/Relic/CompositionClipCapture.cs").read_text(encoding="utf-8-sig")
        self.assertIn('["status"] = "not-measured"', collector)
        self.assertIn('if (!ReferenceEquals(owner, toolbarLogoBackingOwner) || toolbarLogoBackingVisual == null)', collector)
        self.assertNotIn('["clip_present"] = false', collector)

    def test_preparation_is_explicitly_before_render_and_authoritative_capture(self):
        root = Path(__file__).resolve().parents[2]
        flow = (root / "native/windows/Relic/VisualCapture.cs").read_text(encoding="utf-8-sig")
        operations = ["PrepareCompositionClipCapture(shot.Text", "await BeginNativeLabelCaptureAsync(",
                      "EstablishCompositionClipBaseline();", "BeginTextRangeFrameCapture(", "await CaptureClient("]
        positions = [flow.index(operation) for operation in operations]
        self.assertEqual(positions, sorted(positions))
        preparation = (root / "native/windows/Relic/CompositionClipPreparation.cs").read_text(encoding="utf-8-sig")
        self.assertEqual(len(re.findall(r"\bGetElementVisual\s*\(", preparation)), 2,
                         "One actual call plus its receipt API name; no getter calls in authoritative checkpoints")
        after_setup = preparation.split("private void EstablishCompositionClipBaseline", 1)[1]
        self.assertIsNone(re.search(r"\bGetElementVisual\s*\(", after_setup))
        self.assertIsNone(re.search(r"\bSetElementChildVisual\s*\(", preparation))

    def test_prepared_absent_clip_is_measured_without_claiming_original_or_final_pixels(self):
        node = prepared_sample(absent=True); original = deepcopy(node)
        audit, gaps = composition_clip(node)
        self.assertEqual(audit["status"], "measured-absent")
        self.assertEqual(gaps, [])
        self.assertEqual(audit["observation_basis"]["basis"], "diagnostic-prepared")
        self.assertFalse(audit["observation_basis"]["production_original_state_observed"])
        self.assertTrue(audit["observation_basis"]["may_create"])
        self.assertTrue(audit["observation_basis"]["created_unknown"])
        self.assertTrue(audit["observation_basis"]["limitations"])
        self.assertFalse(audit["presentation_identity_proven"])
        self.assertEqual(node, original)

    def test_prepared_actual_geometry_still_has_independent_presentation_gap(self):
        audit, gaps = composition_clip(prepared_sample())
        self.assertEqual(audit["status"], "geometry-measured")
        self.assertEqual(audit["image_corner_radius"], 5)
        self.assertEqual([gap["property"] for gap in gaps], ["clip.presentation"])

    def test_failed_stale_replaced_or_mutating_preparation_is_not_measured_absence(self):
        for failure in ("missing-setup", "wrong-case", "failed-call", "setup-overlap", "missing-render",
                        "failed-flush", "missing-baseline", "unloaded", "wrong-root", "replaced-owner",
                        "changed-visual", "changed-clip", "original-claim", "created-claim", "geometry-change"):
            with self.subTest(failure=failure):
                node = prepared_sample(absent=True); raw = node["composition_clip_evidence"]
                receipt = raw["diagnostic_preparation"]
                if failure == "missing-setup": receipt.pop("setup")
                elif failure == "wrong-case": receipt["render_preparation"]["case_id"] = "other-scene"
                elif failure == "failed-call": receipt["owner_call"]["returned"] = False
                elif failure == "setup-overlap": receipt["owner_call"]["completed_qpc"] = 19
                elif failure == "missing-render": receipt["render_preparation"]["render_cycle"].pop("rendered")
                elif failure == "failed-flush": receipt["render_preparation"]["dwm_flush"]["hresult"] = -1
                elif failure == "missing-baseline": receipt.pop("baseline")
                elif failure == "replaced-owner": receipt["capture_owner_same_object"] = False
                elif failure == "original-claim": receipt["production_original_state_observed"] = True
                elif failure == "created-claim": receipt["setup"]["created_unknown"] = False
                else:
                    state = receipt["after_getters"]["state"]
                    if failure == "unloaded": state["owner_unloaded_since_setup"] = True
                    elif failure == "wrong-root": state["same_xaml_root"] = False
                    elif failure == "changed-visual": state["visual_identity"] = "0x99"
                    elif failure == "changed-clip": state["clip_identity"] = "0x99"
                    elif failure == "geometry-change": state["owner_to_window"]["offset_x"] += 1
                original = deepcopy(node)
                audit, gaps = composition_clip(node)
                self.assertEqual(audit["status"], "unavailable")
                self.assertTrue(gaps)
                self.assertIsNone(audit["window_geometry"])
                self.assertEqual(node, original)

    def test_retained_production_binding_measures_geometry_but_not_presentation(self):
        node = retained_sample(); original = deepcopy(node)
        audit, gaps = composition_clip(node)
        self.assertEqual(audit["image_corner_radius"], 5)
        self.assertEqual(audit["status"], "geometry-measured")
        self.assertEqual([gap["property"] for gap in gaps], ["clip.presentation"])
        self.assertFalse(audit["presentation_identity_proven"])
        self.assertEqual(node, original)

    def test_retained_owner_root_clip_and_unload_revision_must_be_proven(self):
        keys = ("owner_same_object", "owner_is_current_logo", "same_xaml_root", "owner_is_loaded_after",
                "visual_same_retained_object", "clip_is_installed_production_object",
                "geometry_is_installed_production_object", "read_only")
        for key in keys:
            for value in (False, None, 1, "true"):
                with self.subTest(key=key, value=value):
                    node = retained_sample()
                    node["composition_clip_evidence"]["production_binding"][key] = value
                    audit, gaps = composition_clip(node)
                    self.assertIsNone(audit["image_corner_radius"])
                    self.assertTrue(gaps)
        for before, after in ((7, 8), (0, 0), (None, None), (True, True), (7, 7.0)):
            node = retained_sample()
            node["composition_clip_evidence"]["production_binding"].update(revision_before=before, revision_after=after)
            self.assertTrue(composition_clip(node)[1])
            self.assertIsNone(composition_clip(node)[0]["image_corner_radius"])

    def test_retained_receipt_does_not_replace_actual_getters_or_unknown_absence(self):
        for mutate in (
            lambda raw: raw.update(backing_visual_read=False),
            lambda raw: raw.update(production_backing_visual_binding_available=False),
            lambda raw: raw.pop("production_binding"),
            lambda raw: raw.update(properties_stable=False),
            lambda raw: raw["binding"].update(geometry_same_object_after=False),
            lambda raw: raw["after"]["clip"]["geometry"].update(corner_radius=[4, 4]),
        ):
            node = retained_sample(); mutate(node["composition_clip_evidence"])
            audit, gaps = composition_clip(node)
            self.assertIsNone(audit["image_corner_radius"])
            self.assertTrue(gaps)

    def test_actual_radius_is_projected_without_resource_uri_or_reference(self):
        for radius in (0, 3.25, 5, 8):
            with self.subTest(radius=radius):
                node = sample(radius); original = deepcopy(node)
                audit, gaps = composition_clip(node)
                element = {"id": node["id"], "kind": "image", "style": {"corner_radius": 0, "corner_radii": [0] * 4}}
                apply_composition_clip(element, audit)
                self.assertEqual(element["style"]["corner_radii"], [radius] * 4)
                self.assertEqual(audit["window_geometry"]["bounds"], node["bounds"])
                self.assertFalse(audit["presentation_identity_proven"])
                self.assertEqual([gap["property"] for gap in gaps], ["clip.presentation"])
                self.assertEqual(node, original)

    def test_missing_foreign_unloaded_or_unstable_owner_fails(self):
        for mutate in (
            lambda n: n.pop("composition_clip_evidence"),
            lambda n: n["composition_clip_evidence"].update(owner_id="another"),
            lambda n: n["composition_clip_evidence"].update(owner_type="Border"),
            lambda n: n["composition_clip_evidence"].update(owner_is_loaded=False),
            lambda n: n["composition_clip_evidence"]["binding"].update(visual_same_object_after=False),
            lambda n: n["composition_clip_evidence"]["binding"].update(clip_same_object_after=False),
            lambda n: n["composition_clip_evidence"]["binding"].update(geometry_same_object_after=None),
            lambda n: n["composition_clip_evidence"].update(properties_stable=False),
            lambda n: n["composition_clip_evidence"]["after"]["clip"]["geometry"].update(corner_radius=[1, 1]),
        ):
            node = sample(); mutate(node); audit, gaps = composition_clip(node)
            self.assertIsNone(audit["image_corner_radius"])
            self.assertTrue(gaps)

    def test_measured_null_clip_is_distinct_from_missing_and_keeps_xaml(self):
        node = sample(); node["clip"] = {"kind": "rectangle", "bounds": deepcopy(node["bounds"])}
        node["composition_clip_evidence"]["xaml_clip_present"] = True
        change_snapshot(node, lambda s: s.update(clip_present=False, clip=None))
        audit, gaps = composition_clip(node)
        self.assertEqual(audit["status"], "measured-absent")
        self.assertEqual(audit["xaml_clip"], node["clip"])
        self.assertEqual(gaps, [])
        del node["composition_clip_evidence"]["before"]["clip_present"]
        node["composition_clip_evidence"]["after"] = deepcopy(node["composition_clip_evidence"]["before"])
        self.assertTrue(composition_clip(node)[1])

    def test_coordinate_or_nonfinite_inputs_never_supply_radius(self):
        for mutate in (
            lambda s: s["visual"].update(size=[19, 18]),
            lambda s: s["visual"].update(scale=[2, 2, 1]),
            lambda s: s["visual"].update(offset=[0, 0, 1]),
            lambda s: s["clip"].update(rotation_angle=.1),
            lambda s: s["clip"].update(anchor_point=[.5, .5]),
            lambda s: s["clip"]["geometry"].update(corner_radius=[float("inf"), 5]),
            lambda s: s["clip"]["geometry"].update(size=[True, 18]),
            lambda s: s["clip"]["geometry"].update(trim_start=.1),
        ):
            node = sample(); change_snapshot(node, mutate); audit, gaps = composition_clip(node)
            self.assertIsNone(audit["image_corner_radius"])
            self.assertTrue(gaps)
        node = sample(); node["transform"]["offset_x"] = 99
        self.assertTrue(composition_clip(node)[1])

    def test_noncoextensive_and_elliptical_clips_preserve_measured_geometry(self):
        for mutate in (
            lambda s: s["clip"].update(offset=[1, 0]),
            lambda s: s["clip"]["geometry"].update(corner_radius=[5, 4]),
            lambda s: s["clip"]["geometry"].update(size=[15, 18]),
        ):
            node = sample(); change_snapshot(node, mutate); audit, gaps = composition_clip(node)
            self.assertEqual(audit["status"], "geometry-measured")
            self.assertIsNotNone(audit["window_geometry"])
            self.assertIsNone(audit["image_corner_radius"])
            self.assertTrue(gaps)

    def test_independent_xaml_clip_cannot_be_overwritten(self):
        node = sample(); node["clip"] = {"kind": "rectangle", "bounds": {"x": 13, "y": 10.5, "width": 17, "height": 18}}
        node["composition_clip_evidence"]["xaml_clip_present"] = True
        audit, gaps = composition_clip(node)
        self.assertEqual(audit["xaml_clip"], node["clip"])
        self.assertIsNone(audit["image_corner_radius"])
        self.assertTrue(any("intersects" in g["reason"] for g in gaps))
        node["clip"]["bounds"] = deepcopy(node["bounds"])
        self.assertEqual(composition_clip(node)[0]["image_corner_radius"], 5)

    def test_actual_uniform_window_scale_not_hardcoded_one(self):
        node = sample(3); node["transform"]["m11"] = node["transform"]["m22"] = 2
        node["composition_clip_evidence"]["owner_to_window"] = deepcopy(node["transform"])
        node["bounds"]["width"] = node["bounds"]["height"] = 36
        self.assertEqual(composition_clip(node)[0]["image_corner_radius"], 6)

    def test_unsupported_type_and_collection_failure_stay_unknown(self):
        node = sample(); change_snapshot(node, lambda s: s["clip"].update(type=PREFIX + "InsetClip"))
        audit, gaps = composition_clip(node)
        self.assertIsNone(audit["window_geometry"]); self.assertTrue(gaps)
        node = sample(); node["composition_clip_evidence"].update(status="failed", failure={"hresult": -1})
        audit, gaps = composition_clip(node)
        self.assertEqual(audit["raw"]["failure"], {"hresult": -1}); self.assertTrue(gaps)

    def test_foreign_element_and_nonimage_style_do_not_inherit_radius(self):
        audit, _ = composition_clip(sample())
        for eid, kind in (("another", "image"), ("image-1", "card")):
            element = {"id": eid, "kind": kind, "style": {"corner_radius": 0}}
            apply_composition_clip(element, audit)
            self.assertEqual(element["style"]["corner_radius"], 0)


if __name__ == "__main__":
    unittest.main()
