"""Pure fixtures for independent full-domain background paint measurement."""
import base64
from copy import deepcopy
import unittest
import zlib

from element_parity import delta_e
from paint_patterns import MeasurementError, compare_paint_patterns, decode_bitmap


def encoded(raw):
    return base64.b64encode(zlib.compress(bytes(raw))).decode("ascii")


def fixtures(width=32, height=32, color=(0, 0, 0, 255)):
    """Measured synthetic 16px checker: NE and SW quarters are painted."""
    raster = {"x": 0, "y": 0, "width": width, "height": height, "scale": 1,
              "clip_status": "measured", "occlusion_status": "measured",
              "visibility_source": "Synthetic full-area visibility fixture",
              "visibility": {"encoding": "base64-zlib", "format": "A8", "data": encoded([255] * (width * height))}}
    placement = {"coordinate_space": "content-window", "source": "Synthetic measured identity placement",
                 "local_to_window": [1, 0, 0, 1, 0, 0]}
    common = {"opacity": 1, "opacity_source": "Synthetic measured cumulative opacity", "raster": raster, "placement": placement}
    ref = deepcopy(common)
    ref.update(kind="css-conic", paint={"kind": "conic-gradient", "angle": 0, "center": [8, 8], "size": [16, 16],
                                       "position": [0, 0], "repeat": ["repeat", "repeat"], "repeating": True,
                                       "stops": [{"position": 0, "color": list(color)}, {"position": .25, "color": list(color)},
                                                 {"position": .25, "color": [0, 0, 0, 0]}, {"position": .5, "color": [0, 0, 0, 0]}]})
    ref["placement"]["origin"] = [0, 0]
    raw = bytearray()
    for y in range(height):
        for x in range(width):
            rgba = color if (x % 16 >= 8) != (y % 16 >= 8) else (0, 0, 0, 0)
            red, green, blue, alpha = rgba
            raw.extend((round(blue * alpha / 255), round(green * alpha / 255), round(red * alpha / 255), alpha))
    native = deepcopy(common)
    native.update(kind="image-brush", brush={"type": "Microsoft.UI.Xaml.Media.ImageBrush", "opacity": 1,
                  "image": {"source": "Synthetic captured source buffer", "type": "Microsoft.UI.Xaml.Media.Imaging.WriteableBitmap",
                            "stretch": "Fill", "alignment_x": "Left", "alignment_y": "Top",
                            "transform": None, "relative_transform": None,
                            "pixel_width": width, "pixel_height": height, "pixel_buffer_length": len(raw),
                            "pixel_format": "BGRA8-premultiplied", "pixel_buffer_encoding": "base64-zlib", "pixel_buffer": encoded(raw)}})
    native["placement"]["paint_box"] = {"x": 0, "y": 0, "width": width, "height": height}
    return ref, native


def change_pixel(native, x, y, bgra):
    image = native["brush"]["image"]
    raw = bytearray(zlib.decompress(base64.b64decode(image["pixel_buffer"])))
    offset = (y * image["pixel_width"] + x) * 4
    raw[offset:offset + 4] = bytes(bgra)
    image["pixel_buffer"] = encoded(raw)


def compare(ref, native):
    return compare_paint_patterns(ref, native, color_distance=delta_e)


class PaintPatterns(unittest.TestCase):
    def test_actual_bitmap_and_css_type_are_retained_and_all_pixels_are_compared(self):
        ref, native = fixtures(48, 32)
        before = deepcopy(native)
        result = compare(ref, native)
        self.assertEqual(result["status"], "match")
        self.assertTrue(result["complete"])
        self.assertEqual(result["visited_pixels"], 1536)
        self.assertEqual(result["compared_pixels"], 1536)
        self.assertEqual(result["mismatched_pixels"], 0)
        self.assertEqual(native, before)
        self.assertEqual(native["kind"], "image-brush")

    def test_single_pixel_far_from_old_probe_points_cannot_hide(self):
        ref, native = fixtures(64, 64)
        change_pixel(native, 63, 63, (0, 0, 255, 255))
        result = compare(ref, native)
        self.assertEqual(result["visited_pixels"], 4096)
        self.assertEqual(result["compared_pixels"], 4096)
        self.assertEqual(result["mismatched_pixels"], 1)
        self.assertEqual(result["alpha_mismatches"], 1)
        self.assertEqual(result["mismatch_runs"], [{"y": 63, "x0": 63, "x1": 64}])

    def test_alpha_is_exact_even_when_color_is_identical(self):
        ref, native = fixtures()
        change_pixel(native, 9, 0, (0, 0, 0, 254))
        result = compare(ref, native)
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["alpha_mismatches"], 1)
        self.assertEqual(result["color_mismatches"], 0)
        self.assertEqual(result["alpha_tolerance"], 0)

    def test_existing_delta_e_metric_and_three_unit_limit_are_used(self):
        ref, native = fixtures()
        change_pixel(native, 8, 0, (3, 3, 3, 255))
        change_pixel(native, 9, 0, (20, 20, 20, 255))
        result = compare(ref, native)
        self.assertLess(delta_e([0, 0, 0, 255], [3, 3, 3, 255]), 3)
        self.assertGreater(delta_e([0, 0, 0, 255], [20, 20, 20, 255]), 3)
        self.assertEqual(result["color_mismatches"], 1)
        self.assertEqual(result["mismatch_runs"], [{"y": 0, "x0": 9, "x1": 10}])
        self.assertEqual(result["color_tolerance"], 3)

    def test_zero_alpha_rgb_is_unobservable_but_nonzero_alpha_is_not_discarded(self):
        ref, native = fixtures()
        for stop in ref["paint"]["stops"]:
            if stop["color"][3] == 0: stop["color"] = [240, 20, 80, 0]
        self.assertEqual(compare(ref, native)["status"], "match")
        change_pixel(native, 0, 0, (0, 0, 0, 1))
        self.assertEqual(compare(ref, native)["alpha_mismatches"], 1)

    def test_actual_premultiplied_bytes_are_unassociated_without_invented_color(self):
        _, native = fixtures(1, 1)
        change_pixel(native, 0, 0, (20, 40, 80, 128))
        bitmap = decode_bitmap(native["brush"]["image"])
        self.assertEqual(bitmap.rgba(0, 0), (80 * 255 / 128, 40 * 255 / 128, 20 * 255 / 128, 128))

    def test_computed_css_translucency_cannot_be_compared_to_quantized_bitmap_as_actual_pixels(self):
        for color in ([27, 27, 30, 15.3], [27, 27, 30, 15], [27.5, 27, 30, 255]):
            ref, native = fixtures()
            ref["paint"]["stops"][0]["color"] = color
            ref["paint"]["stops"][1]["color"] = color
            result = compare(ref, native)
            self.assertEqual(result["status"], "unmeasured")
            self.assertFalse(result["complete"])
            self.assertIn("quantization", result["errors"][0]["reason"])

    def test_measured_translation_changes_window_domain_without_phase_reset(self):
        ref, native = fixtures()
        for record in (ref, native):
            record["placement"]["local_to_window"][4:6] = [8, 16]
            record["raster"]["x"], record["raster"]["y"] = 8, 16
        self.assertEqual(compare(ref, native)["status"], "match")
        ref["paint"]["position"] = [8, 0]
        result = compare(ref, native)
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["alpha_mismatches"], 1024)

    def test_partial_measured_visibility_and_opacity_are_retained(self):
        ref, native = fixtures()
        mask = [128] * 1024
        for record in (ref, native):
            record["opacity"] = .5
            record["raster"]["visibility"]["data"] = encoded(mask)
        self.assertEqual(compare(ref, native)["status"], "match")
        native["brush"]["opacity"] = .5
        self.assertEqual(compare(ref, native)["alpha_mismatches"], 512)

    def test_explicit_occlusion_mask_is_used_over_the_whole_domain(self):
        ref, native = fixtures()
        mask = [255] * 1024
        mask[-1] = 0
        for record in (ref, native): record["raster"]["visibility"]["data"] = encoded(mask)
        change_pixel(native, 31, 31, (0, 0, 255, 255))
        result = compare(ref, native)
        self.assertEqual(result["status"], "match")
        self.assertEqual(result["visited_pixels"], 1024)
        self.assertEqual(result["visible_pixels"], 1023)
        self.assertEqual(result["compared_pixels"], 1023)

    def test_missing_measurements_never_become_an_opaque_rectangle(self):
        mutations = [lambda x: x["raster"].pop("visibility"),
                     lambda x: x["raster"].update(occlusion_status="unknown"),
                     lambda x: x["raster"].update(clip_status="unknown"),
                     lambda x: x["placement"].pop("paint_box"),
                     lambda x: x["placement"].pop("local_to_window"),
                     lambda x: x["brush"]["image"].pop("transform"),
                     lambda x: x["brush"]["image"].pop("source"),
                     lambda x: x.pop("opacity")]
        for mutate in mutations:
            ref, native = fixtures(); mutate(native)
            result = compare(ref, native)
            self.assertEqual(result["status"], "unmeasured")
            self.assertFalse(result["complete"])
            self.assertTrue(result["errors"])

    def test_filtering_or_rotated_coverage_cannot_be_assumed(self):
        for field, value in (("local_to_window", [1, .1, 0, 1, 0, 0]),
                             ("local_to_window", [2, 0, 0, 2, 0, 0]),
                             ("local_to_window", [1, 0, 0, 1, .5, 0])):
            ref, native = fixtures(); native["placement"][field] = value
            self.assertEqual(compare(ref, native)["status"], "unmeasured")

    def test_continuous_gradient_and_unknown_repeat_need_renderer_evidence(self):
        for change in (lambda p: p["stops"][1].update(color=[255, 255, 255, 255]),
                       lambda p: p.update(angle=45), lambda p: p.update(repeat=["space", "repeat"])):
            ref, native = fixtures(); change(ref["paint"])
            self.assertEqual(compare(ref, native)["status"], "unmeasured")

    def test_bitmap_corruption_and_invalid_premultiplication_fail(self):
        ref, native = fixtures()
        image = native["brush"]["image"]
        for key, value in (("pixel_buffer", "not base64"), ("pixel_buffer_length", 4), ("pixel_format", "RGBA8")):
            broken = deepcopy(image); broken[key] = value
            with self.assertRaises(MeasurementError): decode_bitmap(broken)
        change_pixel(native, 0, 0, (20, 0, 0, 0))
        self.assertEqual(compare(ref, native)["status"], "unmeasured")

    def test_different_domains_and_no_visible_pixels_never_match(self):
        ref, native = fixtures(); native["raster"]["x"] = 1
        self.assertEqual(compare(ref, native)["status"], "unmeasured")
        ref, native = fixtures()
        for record in (ref, native): record["raster"]["visibility"]["data"] = encoded([0] * 1024)
        result = compare(ref, native)
        self.assertEqual(result["visited_pixels"], 1024)
        self.assertEqual(result["status"], "unmeasured")

    def test_outside_paint_box_is_unknown_and_does_not_stop_full_traversal(self):
        ref, native = fixtures()
        native["placement"]["paint_box"]["x"] = 1
        result = compare(ref, native)
        self.assertEqual(result["status"], "unmeasured")
        self.assertFalse(result["complete"])
        self.assertEqual(result["visited_pixels"], 1024)
        self.assertEqual(result["compared_pixels"], 992)
        self.assertEqual(len(result["errors"]), 32)

    def test_invalid_metric_result_does_not_claim_complete_measurement(self):
        ref, native = fixtures(16, 16)
        result = compare_paint_patterns(ref, native, color_distance=lambda a, b: float("nan"))
        self.assertEqual(result["status"], "unmeasured")
        self.assertFalse(result["complete"])
        self.assertEqual(result["visited_pixels"], 256)
        self.assertEqual(result["compared_pixels"], 128)
        self.assertEqual(len(result["errors"]), 128)

    def test_measured_device_scale_uses_device_pixels_not_window_units(self):
        ref, native = fixtures(64, 64)
        for record in (ref, native): record["raster"]["scale"] = 2
        ref["paint"]["size"] = [8, 8]
        ref["paint"]["center"] = [4, 4]
        native["placement"]["paint_box"].update(width=32, height=32)
        result = compare(ref, native)
        self.assertEqual(result["status"], "match")
        self.assertEqual(result["compared_pixels"], 4096)


if __name__ == "__main__":
    unittest.main()
