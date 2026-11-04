"""Pure loaded-resource regressions. CI only; no UI, server, or fetching."""
import base64
from copy import deepcopy
from pathlib import Path
import unittest

from image_paint import ImagePaintError, decode_svg_bytes, svg_paint_evidence, validate_vector_paint


ICON = Path(__file__).resolve().parents[2] / "plugins/relic/app/static/icon.svg"


def svg(body, view_box="0 0 64 64"):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}">{body}</svg>'.encode()


class ImagePaintTests(unittest.TestCase):
    def test_actual_packaged_bytes_decode_all_three_paint_layers(self):
        raw = ICON.read_bytes()
        paint = decode_svg_bytes(raw)
        self.assertEqual("vector-image-v1", paint["source"])
        self.assertEqual([0, 0, 64, 64], paint["glyph"]["view_box"])
        rect, letter, circle = paint["glyph"]["layers"]
        self.assertEqual({"kind": "rounded-rect", "bounds": [0, 0, 64, 64], "radii": [15, 15],
                          "fill": {"kind": "linear-gradient", "start": [0, 0], "end": [0, 64],
                                   "spread": "pad", "color_space": "srgb", "stops": [
                                       {"offset": 0, "color": [46, 44, 41, 255]},
                                       {"offset": 1, "color": [27, 26, 24, 255]}]}}, rect)
        self.assertEqual("path", letter["kind"])
        self.assertEqual("nonzero", letter["fill_rule"])
        self.assertEqual({"kind": "solid", "color": [255, 255, 255, 255]}, letter["fill"])
        self.assertIn(('d="' + letter["d"] + '"').encode(), raw)
        self.assertEqual({"kind": "circle", "center": [47.5, 46.5], "radius": 4.2,
                          "fill": {"kind": "solid", "color": [217, 119, 87, 255]}}, circle)

    def test_object_bounds_and_percent_coordinates_resolve_without_icon_constants(self):
        content = svg('<defs><linearGradient id="other" x1="25%" y1="0" x2="25%" y2="100%">'
                      '<stop offset="0%" stop-color="#123"/><stop offset="100%" stop-color="#456"/>'
                      '</linearGradient></defs><rect x="12" y="7" width="20" height="40" ry="30" fill="url(#other)"/>')
        layer = decode_svg_bytes(content)["glyph"]["layers"][0]
        self.assertEqual([10, 20], layer["radii"])
        self.assertEqual([17, 7], layer["fill"]["start"])
        self.assertEqual([17, 47], layer["fill"]["end"])
        self.assertEqual([17, 34, 51, 255], layer["fill"]["stops"][0]["color"])

    def test_transport_changes_do_not_supply_identity_or_binding_proof(self):
        content = ICON.read_bytes()
        first = svg_paint_evidence(content, {"uri": "http://127.0.0.1:123/icon.svg"})
        second = svg_paint_evidence(content, {"uri": "ms-appx:///Assets/Relic.svg"})
        self.assertEqual(first["paint"], second["paint"])
        self.assertNotEqual(first["source_evidence"], second["source_evidence"])
        self.assertEqual(content, base64.b64decode(first["content_bytes"]))
        self.assertEqual(len(content), first["byte_length"])
        self.assertEqual("unverified-by-parser", first["content_binding_status"])
        self.assertFalse(first["presentation_identity_proven"])
        # An actual failed binding remains failed even though the bytes decode.
        failed = svg_paint_evidence(content, {"content_binding_complete": False})
        self.assertFalse(failed["source_evidence"]["content_binding_complete"])

    def test_changed_content_and_layer_order_remain_different(self):
        raw = ICON.read_bytes()
        original = decode_svg_bytes(raw)
        changed = decode_svg_bytes(raw.replace(b'#D97757', b'#D97758'))
        self.assertNotEqual(original, changed)
        a = '<circle cx="1" cy="2" r="1" fill="#123"/>'
        b = '<rect width="2" height="2" fill="#456"/>'
        self.assertNotEqual(decode_svg_bytes(svg(a + b)), decode_svg_bytes(svg(b + a)))

    def test_unknown_elements_attributes_and_rendering_features_fail_whole_resource(self):
        variants = ['<g><rect width="2" height="2"/></g>', '<text>R</text>',
                    '<rect width="2" height="2" transform="translate(1)"/>',
                    '<rect width="2" height="2" style="fill:red"/>',
                    '<rect width="2" height="2" filter="url(#f)"/>',
                    '<rect width="2" height="2" opacity="0.5"/>',
                    '<rect width="2" height="2" stroke="#000"/>',
                    '<foreignObject/>', '<style>rect{fill:red}</style>']
        for body in variants:
            with self.subTest(body=body), self.assertRaises(ImagePaintError):
                decode_svg_bytes(svg(body))

    def test_unknown_and_external_references_preserve_failure_and_original_bytes(self):
        for fill in ("url(#missing)", "url(https://example.com/image.svg#g)", "currentColor"):
            raw = svg(f'<rect width="2" height="2" fill="{fill}"/>')
            result = svg_paint_evidence(raw)
            self.assertEqual("error", result["status"])
            self.assertIsNone(result["paint"])
            self.assertIn("message", result["error"])
            self.assertEqual(raw, base64.b64decode(result["content_bytes"]))

    def test_invalid_numbers_dimensions_and_incomplete_paths_fail(self):
        variants = ['<circle r="NaN"/>', '<circle r="1e999"/>', '<circle r="-1"/>',
                    '<rect width="10px" height="2"/>', '<rect width="0" height="2"/>',
                    '<path d="M0 0C1 2 3"/>', '<path d="M0 0L1 2,"/>',
                    '<path d="M0,,0"/>', '<path d="M0 0A1 1 0 0 0 2 3"/>',
                    '<path d="M0 0Z1 2"/>']
        for body in variants:
            with self.subTest(body=body), self.assertRaises(ImagePaintError):
                decode_svg_bytes(svg(body))
        with self.assertRaises(ImagePaintError):
            decode_svg_bytes(svg('<circle r="1"/>', "0 0 NaN 64"))

    def test_unrepresented_gradient_semantics_fail_instead_of_approximating(self):
        stops = '<stop offset="0"/><stop offset="1"/>'
        variants = [f'<linearGradient id="g" gradientTransform="rotate(10)">{stops}</linearGradient>',
                    f'<linearGradient id="g" gradientUnits="userSpaceOnUse">{stops}</linearGradient>',
                    f'<linearGradient id="g" spreadMethod="reflect">{stops}</linearGradient>',
                    f'<linearGradient id="g" href="#other">{stops}</linearGradient>',
                    '<linearGradient id="g"><stop offset="1"/><stop offset="0"/></linearGradient>',
                    '<linearGradient id="g"><stop offset="0" stop-opacity="0.5"/><stop offset="1"/></linearGradient>',
                    f'<linearGradient id="g" x2="1" y2="1">{stops}</linearGradient>']
        for definition in variants:
            with self.subTest(definition=definition), self.assertRaises(ImagePaintError):
                decode_svg_bytes(svg(f'<defs>{definition}</defs><rect width="10" height="20" fill="url(#g)"/>'))
        duplicate = f'<linearGradient id="g">{stops}</linearGradient>' * 2
        with self.assertRaises(ImagePaintError):
            decode_svg_bytes(svg(f'<defs>{duplicate}</defs><circle r="1"/>'))

    def test_xml_external_instructions_and_malformed_documents_fail(self):
        for raw in (b'<!DOCTYPE svg [<!ENTITY x "payload">]>' + svg('<circle r="1"/>'),
                    b'<?xml-stylesheet href="external.css"?>' + svg('<circle r="1"/>'),
                    b'<?xml version="1.0" encoding="iso-8859-1"?>' + svg('<circle r="1"/>'),
                    b'<svg>', b'\xff', b'<svg viewBox="0 0 1 1"><circle r="1"/></svg>'):
            with self.subTest(raw=raw), self.assertRaises(ImagePaintError):
                decode_svg_bytes(raw)

    def test_path_source_and_supported_fill_rule_are_not_rewritten(self):
        data = "M1 2 h3 v4 c1 2 3 4 5 6 s7 8 9 10 q1 2 3 4 t5 6 z"
        path = decode_svg_bytes(svg(f'<path d="{data}" fill-rule="evenodd" fill="#abc"/>'))["glyph"]["layers"][0]
        self.assertEqual(data, path["d"])
        self.assertEqual("evenodd", path["fill_rule"])
        self.assertEqual([170, 187, 204, 255], path["fill"]["color"])

    def test_canonical_validator_accepts_complete_actual_description_without_mutation(self):
        paint = decode_svg_bytes(ICON.read_bytes())
        original = deepcopy(paint)
        self.assertIsNone(validate_vector_paint(paint))
        self.assertEqual(original, paint)

    def test_canonical_validator_rejects_unknown_missing_and_invalid_measurements(self):
        good = decode_svg_bytes(ICON.read_bytes())
        cases = []
        for path, value in [
            (("glyph", "view_box"), [0, 0, 0, 64]),
            (("glyph", "view_box"), [0, 0, True, 64]),
            (("glyph", "view_box"), [0, 0, float("inf"), 64]),
            (("glyph", "view_box"), [0, 0, 10 ** 400, 64]),
            (("glyph", "layers"), []),
            (("glyph", "layers", 0, "radii"), [33, 15]),
            (("glyph", "layers", 0, "bounds"), [0, 0, -1, 64]),
            (("glyph", "layers", 0, "fill", "color_space"), "unknown"),
            (("glyph", "layers", 0, "fill", "spread"), "repeat"),
            (("glyph", "layers", 0, "fill", "start"), [0, 64]),
            (("glyph", "layers", 0, "fill", "stops", 0, "offset"), -0.1),
            (("glyph", "layers", 0, "fill", "stops", 0, "color"), [0, 0, 0, 128]),
            (("glyph", "layers", 1, "d"), "M0 0C1"),
            (("glyph", "layers", 1, "fill_rule"), None),
            (("glyph", "layers", 2, "radius"), float("nan")),
            (("glyph", "layers", 2, "center"), ["47.5", 46.5]),
            (("glyph", "layers", 2, "fill", "color"), [256, 0, 0, 255]),
        ]:
            invalid = deepcopy(good)
            parent = invalid
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = value
            cases.append(invalid)
        for path in [(), ("glyph",), ("glyph", "layers", 0),
                     ("glyph", "layers", 0, "fill"), ("glyph", "layers", 0, "fill", "stops", 0)]:
            invalid = deepcopy(good)
            parent = invalid
            for key in path:
                parent = parent[key]
            parent["unexpected"] = "unmodeled paint"
            cases.append(invalid)
        for key in ("view_box", "layers"):
            invalid = deepcopy(good)
            del invalid["glyph"][key]
            cases.append(invalid)
        for index, invalid in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ImagePaintError):
                validate_vector_paint(invalid)


if __name__ == "__main__":
    unittest.main()
