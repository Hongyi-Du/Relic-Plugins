"""Synthetic real-API-shaped Composition clip receipts; CI only, no UI."""
from copy import deepcopy
import unittest

from windows_composition_clip import (SOURCE, PREFIX, IDENTITY3, IDENTITY4,
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


class CompositionClipTests(unittest.TestCase):
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
