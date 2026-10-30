"""Synthetic retained-paint receipts only; these tests create no native windows."""
from copy import deepcopy
import unittest

from windows_inset_shadow import SOURCE, OPERATION, PRESENTATION_GAP, windows_inset_shadows


def fixture():
    path = [{"kind": "M", "values": [0, 0]}, {"kind": "L", "values": [3, 0]},
            {"kind": "L", "values": [3, 40]}, {"kind": "L", "values": [0, 40]}, {"kind": "Z", "values": []}]
    contour = [{"kind": "M", "values": [0, 0]}, {"kind": "L", "values": [100, 0]},
               {"kind": "L", "values": [100, 40]}, {"kind": "L", "values": [0, 40]}, {"kind": "Z", "values": []}]
    r = {"source": SOURCE, "owner_id": "bubble", "layout_id": "layout", "canvas_id": "canvas", "path_id": "shadow", "content_id": "content",
         **{key: True for key in ("owner_child_is_layout", "layout_children_are_retained_parts", "canvas_child_is_path",
             "current_path_same_object", "same_xaml_root", "owner_is_loaded", "path_is_loaded", "current_layout_matches_operation", "actual_path_matches_operation")},
         **{key: False for key in ("path_hit_test_visible", "canvas_hit_test_visible", "path_stroke_present", "path_geometry_transform_present")},
         "path_accessibility_view": "Raw", "path_name": "", "failure": None, "actual_size": [100, 40],
         "path_size": [100, 40], "actual_radii": [0, 0, 0, 0], "actual_border_widths": [0, 0, 0, 0],
         "path_fill_type": "SolidColorBrush", "path_fill_rgba8": [112, 88, 184, 255], "path_fill_opacity": 1,
         "path_opacity": 1, "path_stroke_thickness": 0, "path_stretch": "None", "path_fill_rule": "EvenOdd",
         "actual_path_to_owner": [1, 0, 0, 1, 0, 0], "actual_path_commands": deepcopy(path), "presentation_identity_proven": False,
         "operation": {"source": OPERATION, "operation": "exclude-translated-self", "failure": None, "offset_x": 3, "offset_y": 0,
             "flattening_tolerance": .01, "input_commands": contour, "output_commands": deepcopy(path), "output_fill_mode": 0,
             "padding_edge": [0, 0, 100, 40], "padding_radii": [0] * 8,
             "create_path_hresult": 0, "open_hresult": 0, "close_hresult": 0, "combine_hresult": 0}}
    return [
        {"id": "bubble", "type": "Border", "parent": None, "opacity": 1, "native_inset_shadow": r,
         "bounds": {"x": 20, "y": 30, "width": 100, "height": 40}, "axis_aligned_transform": True,
         "transform": {"m11": 1, "m12": 0, "m21": 0, "m22": 1, "offset_x": 20, "offset_y": 30},
         "style": {"border_widths": [0, 0, 0, 0], "corner_radii": [0, 0, 0, 0], "shadow": []}},
        {"id": "layout", "type": "Grid", "parent": "bubble", "opacity": 1},
        {"id": "canvas", "type": "Canvas", "parent": "layout", "opacity": 1},
        {"id": "shadow", "type": "Path", "parent": "canvas", "opacity": 1, "style": {"foreground": [112, 88, 184, 255]}},
        {"id": "content", "type": "StackPanel", "parent": "layout", "opacity": 1}]


class WindowsInsetShadowTests(unittest.TestCase):
    def test_actual_retained_path_is_owned_without_claiming_final_pixels(self):
        raw = fixture(); before = deepcopy(raw)
        result = windows_inset_shadows(raw)
        self.assertEqual(raw, before)
        owner = result["owners"]["bubble"]
        self.assertEqual(owner["path_id"], "shadow")
        self.assertEqual(owner["shadow"], [{"inset": True, "offset_x": 3, "offset_y": 0, "blur_radius": 0,
                                           "spread_radius": 0, "color": [112, 88, 184, 255]}])
        self.assertFalse(owner["presentation_identity_proven"])
        self.assertEqual([x["reason"] for x in result["unmeasured"]], [PRESENTATION_GAP])

    def test_old_border_is_never_relabelled_as_shadow(self):
        raw = fixture(); del raw[0]["native_inset_shadow"]
        raw[0]["style"]["border_widths"] = [0, 0, 0, 3]
        before = deepcopy(raw)
        self.assertEqual(windows_inset_shadows(raw)["owners"], {})
        self.assertEqual(raw, before)

    def test_missing_false_or_foreign_identity_is_not_owned(self):
        for field, value in (("owner_id", "foreign"), ("path_id", "foreign"), ("current_path_same_object", False),
                             ("same_xaml_root", None), ("owner_child_is_layout", False), ("actual_path_matches_operation", False)):
            with self.subTest(field=field):
                raw = fixture(); raw[0]["native_inset_shadow"][field] = value
                self.assertEqual(windows_inset_shadows(raw)["owners"], {})

    def test_extra_or_reparented_paint_is_not_swallowed(self):
        for mode in ("extra", "reparent", "duplicate"):
            raw = fixture()
            if mode == "extra": raw.append({"id": "other", "type": "Path", "parent": "canvas"})
            elif mode == "duplicate": raw.append(deepcopy(raw[3]))
            else: raw[3]["parent"] = "content"
            self.assertEqual(windows_inset_shadows(raw)["owners"], {})

    def test_stale_size_transform_radii_color_or_path_is_rejected(self):
        changes = [("actual_size", [101, 40]), ("actual_path_to_owner", [1, 0, 0, 1, 1, 0]),
                   ("actual_radii", [4, 4, 4, 4]), ("path_fill_rgba8", [255, 0, 0, 255]),
                   ("path_hit_test_visible", True), ("path_geometry_transform_present", True)]
        for field, value in changes:
            with self.subTest(field=field):
                raw = fixture(); raw[0]["native_inset_shadow"][field] = value
                self.assertEqual(windows_inset_shadows(raw)["owners"], {})
        raw = fixture(); raw[0]["native_inset_shadow"]["actual_path_commands"][1]["values"][0] = 4
        self.assertEqual(windows_inset_shadows(raw)["owners"], {})

    def test_native_error_unknown_path_and_nonfinite_are_not_zeroed(self):
        raw = fixture(); raw[0]["native_inset_shadow"]["operation"]["combine_hresult"] = -2147467259
        self.assertEqual(windows_inset_shadows(raw)["owners"], {})
        for bad in (float("nan"), float("inf"), True, 10**1000):
            raw = fixture(); raw[0]["native_inset_shadow"]["operation"]["offset_x"] = bad
            self.assertEqual(windows_inset_shadows(raw)["owners"], {})
        raw = fixture(); raw[0]["native_inset_shadow"]["actual_path_commands"][1]["kind"] = {"unknown": True}
        self.assertEqual(windows_inset_shadows(raw)["owners"], {})
        raw = fixture(); raw[0]["native_inset_shadow"]["operation"]["padding_radii"][0] = False
        self.assertEqual(windows_inset_shadows(raw)["owners"], {})
        raw = fixture(); raw[3]["opacity"] = True
        self.assertEqual(windows_inset_shadows(raw)["owners"], {})

    def test_plain_border_remains_a_real_border(self):
        raw = fixture(); receipt = raw[0]["native_inset_shadow"]
        receipt["actual_border_widths"] = raw[0]["style"]["border_widths"] = [1, 1, 1, 1]
        receipt["operation"]["padding_edge"] = [1, 1, 98, 38]
        receipt["operation"]["input_commands"] = [{"kind": "M", "values": [1, 1]}, {"kind": "L", "values": [99, 1]},
            {"kind": "L", "values": [99, 39]}, {"kind": "L", "values": [1, 39]}, {"kind": "Z", "values": []}]
        inner = [{"kind": "M", "values": [1, 1]}, {"kind": "L", "values": [4, 1]},
                 {"kind": "L", "values": [4, 39]}, {"kind": "L", "values": [1, 39]}, {"kind": "Z", "values": []}]
        receipt["operation"]["output_commands"] = deepcopy(inner); receipt["actual_path_commands"] = inner
        self.assertIn("bubble", windows_inset_shadows(raw)["owners"])
        self.assertEqual(raw[0]["style"]["border_widths"], [1, 1, 1, 1])
