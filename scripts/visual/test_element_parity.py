"""Pure fixture tests for the strict element gate. Run in CI only.

No subprocess, UI, application server, network or desktop automation is used.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from element_parity import (CATEGORIES, STATE_FIELDS, compare_elements, delta_e,
                            expected_cases, geometry_tolerance, match_elements,
                            run, validate_capture)


def element(eid="r0", text="今天 11:00", order=0, kind="text", region="conversation"):
    return {"id": eid, "parent": None, "region": region, "order": order, "kind": kind,
            "text": text, "name": "", "bounds": {"x": 10., "y": 12., "width": 100., "height": 20.},
            "style": {"font_size": 13., "font_weight": 400, "foreground": [27, 27, 26, 255],
                      "background": [0, 0, 0, 0], "border_color": [0, 0, 0, 0], "border_width": 0, "corner_radius": 0,
                      "border_widths": [0, 0, 0, 0], "border_colors": [[0, 0, 0, 0] for _ in range(4)], "corner_radii": [0, 0, 0, 0],
                      "opacity": 1, "background_image": "none", "shadow": [],
                      "rendered_fonts": [{"family_name": "Fixture Sans", "postscript_name": "FixtureSans-Regular", "glyph_count": 8, "is_custom_font": False}]},
            "state": {key: None for key in STATE_FIELDS},
            "layout": {"wrap": "none", "truncation": "none", "line_count": 1}, "icon": None,
            "evidence": {"source": "test-only fixture", "text_bounds": [{"x": 10., "y": 12., "width": 100., "height": 20.}]}}


def capture(client="reference", elements=None, scene="zh-CN-light-1440x900-group", viewport=None):
    elements = elements if elements is not None else [element()]
    data = {"schema_version": 1, "client": "reference" if client == "reference-macos" else client, "scene_id": scene,
            "viewport": viewport or {"width": 1440, "height": 900, "scale": 1},
            "extraction_errors": [], "coverage": {"raw_nodes": len(elements), "emitted_elements": len(elements), "unmeasured": []},
            "elements": elements}
    if client in ("reference", "reference-macos"):
        data["reference_environment"] = {"platform": "macos" if client == "reference-macos" else "windows",
                                         "browser": {"name": "fixture-browser", "version": "1"}, "fonts": ["fixture font evidence"]}
    return data


class ElementComparisonTests(unittest.TestCase):
    def test_identical_independent_ids_match(self):
        a, b = element(), element("unrelated-native-id")
        result = compare_elements([a], [b])
        self.assertEqual(result["matched_elements"], 1)
        self.assertTrue(all(not result[key] for key in CATEGORIES))

    def test_missing_extra_and_duplicate_text_are_one_to_one(self):
        refs = [element("r0", "same", 0), element("r1", "same", 1), element("r2", "third", 2)]
        natives = [element("n0", "same", 0)]
        pairs, missing, extra = match_elements(refs, natives)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(len(missing), 2)
        self.assertEqual(extra, [])
        result = compare_elements(natives, refs)
        self.assertEqual(len(result["extra"]), 2)

    def test_exact_text_not_whitespace_or_date_normalized(self):
        for changed in ("今天  11:00", "2026/10/29 11:00", "今天 11:00 ", "Today 11:00"):
            with self.subTest(changed=changed):
                result = compare_elements([element()], [element("n", changed)])
                self.assertTrue(result["text_mismatch"])
                self.assertEqual(result["matched_elements"], 0)

    def test_accessible_name_preserved(self):
        a, b = element(), element("n")
        a["name"], b["name"] = "Send", "Submit"
        self.assertTrue(compare_elements([a], [b])["text_mismatch"])

    def test_small_geometry_inclusive_threshold(self):
        a, b = element(), element("n")
        b["bounds"]["x"] += 4
        self.assertFalse(compare_elements([a], [b])["geometry_out_of_tolerance"])
        b["bounds"]["x"] += .001
        self.assertTrue(compare_elements([a], [b])["geometry_out_of_tolerance"])

    def test_large_geometry_uses_reference_axis_not_native_axis(self):
        a, b = element(), element("n")
        a["bounds"]["width"] = b["bounds"]["width"] = 200
        b["bounds"]["x"] += 6
        self.assertFalse(compare_elements([a], [b])["geometry_out_of_tolerance"])
        b["bounds"]["x"] += .001
        self.assertTrue(compare_elements([a], [b])["geometry_out_of_tolerance"])
        self.assertEqual(geometry_tolerance(130), 4)
        self.assertAlmostEqual(geometry_tolerance(131), 3.93)

    def test_font_radius_and_weight_thresholds(self):
        a, b = element(), element("n")
        b["style"]["font_size"] += .5
        b["style"]["corner_radius"] += 1
        self.assertFalse(compare_elements([a], [b])["style_out_of_tolerance"])
        b["style"]["font_size"] += .001
        b["style"]["corner_radius"] += .001
        b["style"]["font_weight"] += 1
        result = compare_elements([a], [b])
        self.assertEqual({x["field"] for x in result["style_out_of_tolerance"]}, {"font_size", "corner_radius", "font_weight"})

    def test_lab_distance_known_endpoints_and_alpha_not_ignored(self):
        self.assertAlmostEqual(delta_e([0, 0, 0, 255], [255, 255, 255, 255]), 100, places=3)
        self.assertEqual(delta_e([12, 30, 200, 255], [12, 30, 200, 255]), 0)
        a, b = element(), element("n")
        b["style"]["foreground"][3] = 254
        self.assertTrue(compare_elements([a], [b])["style_out_of_tolerance"])
        b["style"]["foreground"] = [255, 255, 255, 255]
        self.assertGreater(compare_elements([a], [b])["style_out_of_tolerance"][0]["delta_e_76"], 3)

    def test_color_distance_boundary(self):
        a, b = element(), element("n")
        a["style"]["foreground"] = [0, 0, 0, 255]
        # A neutral sRGB channel yielding Lab L*=3 sits exactly at DeltaE=3.
        # Solve using bisection against the actual sRGB matrix, then test both
        # sides independently of comparison's pass/fail decision.
        low, high = 0., 255.
        for _ in range(50):
            mid = (low + high) / 2
            if delta_e([0, 0, 0, 255], [mid, mid, mid, 255]) < 3: low = mid
            else: high = mid
        b["style"]["foreground"] = [low - .0001] * 3 + [255]
        self.assertFalse(compare_elements([a], [b])["style_out_of_tolerance"])
        b["style"]["foreground"] = [high + .0001] * 3 + [255]
        self.assertTrue(compare_elements([a], [b])["style_out_of_tolerance"])

    def test_states_and_layout_are_exact(self):
        for field in STATE_FIELDS:
            with self.subTest(state=field):
                a, b = element(), element("n")
                a["state"][field], b["state"][field] = False, True
                self.assertTrue(compare_elements([a], [b])["state_mismatch"])
        for field, changed in (("wrap", "word"), ("truncation", "ellipsis"), ("line_count", 2)):
            a, b = element(), element("n"); b["layout"][field] = changed
            self.assertTrue(compare_elements([a], [b])["layout_mismatch"])

    def test_region_kind_and_order_cannot_pass_by_text(self):
        a, b = element(), element("n", region="sidebar")
        self.assertTrue(compare_elements([a], [b])["region_mismatch"])
        b["region"], b["kind"] = "conversation", "link"
        self.assertTrue(compare_elements([a], [b])["kind_mismatch"])
        refs = [element("r0", "first", 0), element("r1", "second", 1)]
        natives = [element("n0", "second", 0), element("n1", "first", 1)]
        self.assertEqual(len(compare_elements(refs, natives)["order_mismatch"]), 2)

    def test_unapproved_icon_difference_fails(self):
        a, b = element(), element("n")
        a["icon"] = {"source": "svg", "glyph": "M0,0L10,10"}
        b["icon"] = {"source": "font", "glyph": "E123"}
        self.assertTrue(compare_elements([a], [b])["icon_mismatch"])

    def test_svg_identity_compares_parsed_tree_without_json_serialization_noise(self):
        a, b = element(), element("n")
        shape = {"tag": "svg", "attributes": {"viewBox": "0 0 24 24", "data-label": "<>&中文"},
                 "children": [{"tag": "path", "attributes": {"d": "M4 5h16v14H4z"}, "children": []}]}
        a["icon"] = {"source": "svg", "glyph": json.dumps(shape, ensure_ascii=False, separators=(",", ":"))}
        serialized = json.dumps(shape, ensure_ascii=True, sort_keys=True, indent=2).replace("<", "\\u003C").replace(">", "\\u003E").replace("&", "\\u0026")
        b["icon"] = {"source": "svg", "glyph": serialized}
        result = compare_elements([a], [b])
        self.assertFalse(result["icon_mismatch"])
        self.assertEqual(result["matched_elements"], 1)
        self.assertEqual(a["icon"]["glyph"], json.dumps(shape, ensure_ascii=False, separators=(",", ":")))
        self.assertEqual(b["icon"]["glyph"], serialized)  # Source evidence is not rewritten.

    def test_svg_path_values_and_child_order_remain_exact(self):
        a, b = element(), element("n")
        shape = {"tag": "svg", "attributes": {"viewBox": "0 0 24 24"},
                 "children": [{"tag": "path", "attributes": {"d": "M0 0L1 1"}, "children": []},
                              {"tag": "circle", "attributes": {"r": "2"}, "children": []}]}
        a["icon"] = {"source": "svg", "glyph": json.dumps(shape)}
        changed = deepcopy(shape); changed["children"][0]["attributes"]["d"] = "M0 0L2 2"
        b["icon"] = {"source": "svg", "glyph": json.dumps(changed)}
        self.assertTrue(compare_elements([a], [b])["icon_mismatch"])
        changed = deepcopy(shape); changed["children"].reverse()
        b["icon"]["glyph"] = json.dumps(changed)
        self.assertTrue(compare_elements([a], [b])["icon_mismatch"])
        b["icon"] = {"source": "font", "glyph": a["icon"]["glyph"]}
        self.assertTrue(compare_elements([a], [b])["icon_mismatch"])

    def test_invisible_rgb_and_unpainted_border_color_do_not_create_false_mismatches(self):
        a, b = element(), element("n")
        b["style"]["background"] = [255, 255, 255, 0]
        b["style"]["border_color"] = [255, 0, 0, 255]
        b["style"]["border_colors"] = [[255, 0, 0, 255] for _ in range(4)]
        self.assertFalse(compare_elements([a], [b])["style_out_of_tolerance"])
        # Even one alpha unit remains observable and cannot use that rule.
        b["style"]["background"][3] = 1
        self.assertTrue(compare_elements([a], [b])["style_out_of_tolerance"])

    def test_border_directions_and_corner_positions_cannot_hide_behind_scalar_maximum(self):
        a, b = element(), element("n")
        a["style"]["border_width"] = b["style"]["border_width"] = 1
        a["style"]["border_color"] = b["style"]["border_color"] = [0, 0, 0, 255]
        a["style"]["border_colors"] = b["style"]["border_colors"] = [[0, 0, 0, 255] for _ in range(4)]
        a["style"]["border_widths"] = [1, 0, 0, 0]
        b["style"]["border_widths"] = [0, 0, 1, 0]
        a["style"]["corner_radius"] = b["style"]["corner_radius"] = 8
        a["style"]["corner_radii"] = [8, 0, 0, 0]
        b["style"]["corner_radii"] = [0, 8, 0, 0]
        fields = {entry["field"] for entry in compare_elements([a], [b])["style_out_of_tolerance"]}
        self.assertIn("border_widths[0]", fields)
        self.assertIn("border_widths[2]", fields)
        self.assertIn("corner_radii[0]", fields)
        self.assertIn("corner_radii[1]", fields)

    def test_opacity_shadow_and_stroke_differences_are_checked(self):
        a, b = element(), element("n")
        b["style"]["opacity"] = .5
        a["style"]["stroke_width"], b["style"]["stroke_width"] = 1.2, 2.0
        shadow = {"inset": True, "offset_x": 3, "offset_y": 0, "blur_radius": 0, "spread_radius": 0, "color": [168, 148, 224, 255]}
        a["style"]["shadow"] = [deepcopy(shadow)]
        b["style"]["shadow"] = [deepcopy(shadow)]
        b["style"]["shadow"][0]["color"] = [0, 0, 0, 255]
        fields = {entry["field"] for entry in compare_elements([a], [b])["style_out_of_tolerance"]}
        self.assertTrue({"opacity", "stroke_width", "shadow[0].color"}.issubset(fields))

    def test_gradient_stops_are_not_ignored_or_compared_as_a_css_string(self):
        a, b = element(), element("n")
        gradient = {"kind": "conic-gradient", "repeating": True, "angle": 0, "center": [8, 8],
                    "size": [16, 16], "position": [0, 0], "repeat": ["repeat", "repeat"],
                    "stops": [{"position": 0, "color": [27, 27, 26, 255]}, {"position": .5, "color": [0, 0, 0, 0]}]}
        a["style"]["background_image"] = deepcopy(gradient)
        b["style"]["background_image"] = deepcopy(gradient)
        self.assertFalse(compare_elements([a], [b])["style_out_of_tolerance"])
        b["style"]["background_image"]["stops"][0]["color"] = [255, 255, 255, 255]
        self.assertTrue(compare_elements([a], [b])["style_out_of_tolerance"])

    def test_unused_container_text_properties_are_not_rendered_text(self):
        a, b = element(text="", kind="code"), element("n", text="", kind="code")
        a["layout"] = {"wrap": "word", "truncation": "none", "line_count": 0}
        b["layout"] = {"wrap": None, "truncation": None, "line_count": None}
        b["style"]["font_size"] = b["style"]["font_weight"] = b["style"]["foreground"] = None
        result = compare_elements([a], [b])
        self.assertEqual(result["matched_elements"], 1)
        # The separately emitted real text still must match exactly.
        b["text"] = "visible child text incorrectly folded into parent"
        self.assertTrue(compare_elements([a], [b])["text_mismatch"])

    def test_text_alignment_checks_actual_lines_inside_equal_control_boxes(self):
        a, b = element(kind="button"), element("n", kind="button")
        b["evidence"]["text_bounds"][0]["x"] += 20
        result = compare_elements([a], [b])
        self.assertTrue(any(entry["field"] == "text_bounds[0].x" for entry in result["geometry_out_of_tolerance"]))
        b["evidence"].pop("text_bounds")
        self.assertTrue(compare_elements([a], [b])["layout_mismatch"])

    def test_rich_text_fragments_form_same_line_without_changing_reading_order(self):
        a, b = element(), element("n")
        a["evidence"]["text_bounds"] = [{"x": 10, "y": 12, "width": 40, "height": 20}, {"x": 50, "y": 12, "width": 60, "height": 20}]
        self.assertEqual(compare_elements([a], [b])["matched_elements"], 1)

    def test_indeterminate_check_state_is_not_equivalent_to_unchecked(self):
        a, b = element(kind="checkbox"), element("n", kind="checkbox")
        a["state"]["checked"] = b["state"]["checked"] = False
        a["state"]["indeterminate"], b["state"]["indeterminate"] = False, True
        self.assertTrue(compare_elements([a], [b])["state_mismatch"])

    def test_actual_fonts_compare_identity_not_provider_glyph_counter_or_loading_mode(self):
        a, b = element(), element("n")
        b["style"]["rendered_fonts"][0].update(glyph_count=30, is_custom_font=True)
        self.assertFalse(compare_elements([a], [b])["style_out_of_tolerance"])
        b["style"]["rendered_fonts"][0]["postscript_name"] = None
        self.assertFalse(compare_elements([a], [b])["style_out_of_tolerance"])
        b["style"]["rendered_fonts"][0]["family_name"] = "Different Actual Font"
        self.assertTrue(compare_elements([a], [b])["style_out_of_tolerance"])
        b["style"]["rendered_fonts"][0].update(family_name="Fixture Sans", postscript_name="FixtureSans-OtherFace")
        self.assertTrue(compare_elements([a], [b])["style_out_of_tolerance"])


class ExtractionContractTests(unittest.TestCase):
    def validate(self, data):
        return validate_capture(data, "reference", data["scene_id"], {"width": 1440, "height": 900, "scale": 1})

    def test_complete_capture_is_valid(self):
        self.assertEqual(self.validate(capture()), [])

    def test_missing_measurements_even_on_both_clients_are_errors(self):
        for field in ("font_size", "font_weight", "foreground"):
            data = capture(); data["elements"][0]["style"][field] = None
            self.assertTrue(self.validate(data))
        data = capture(); del data["elements"][0]["style"]["border_color"]
        self.assertTrue(self.validate(data))
        data = capture(); data["elements"][0]["layout"]["line_count"] = None
        self.assertTrue(self.validate(data))

    def test_coverage_unknown_measurements_and_extractor_errors_fail(self):
        data = capture(); data["coverage"]["unmeasured"] = ["opaque overlay intersection"]
        self.assertTrue(self.validate(data))
        data = capture(); data["extraction_errors"] = ["UIA unavailable"]
        self.assertTrue(self.validate(data))
        data = capture(); data.pop("coverage")
        self.assertTrue(self.validate(data))

    def test_empty_or_malformed_arrays_do_not_pass(self):
        data = capture(elements=[])
        self.assertTrue(self.validate(data))
        data["elements"] = None
        self.assertTrue(self.validate(data))
        data = capture(); data["elements"] = ["bad-node"]
        self.assertTrue(self.validate(data))

    def test_duplicate_ids_invalid_parent_or_invalid_order_fail(self):
        for mutation in ("duplicate", "parent", "order"):
            data = capture(elements=[element("r0", "first", 0), element("r1", "second", 1)])
            if mutation == "duplicate": data["elements"][1]["id"] = "r0"
            if mutation == "parent": data["elements"][1]["parent"] = "missing"
            if mutation == "order": data["elements"][1]["order"] = 4
            self.assertTrue(self.validate(data))

    def test_interactive_state_unknown_fails(self):
        for kind, state in (("button", "enabled"), ("input", "focused"), ("tab", "selected"), ("checkbox", "checked"), ("toggle", "checked")):
            data = capture(elements=[element(kind=kind)])
            errors = self.validate(data)
            self.assertTrue(any(state in e["reason"] for e in errors))

    def test_unmeasured_paint_fonts_lines_and_unparsed_css_cannot_pass(self):
        for field in ("background", "border_width", "corner_radius", "border_widths", "border_colors", "corner_radii", "opacity", "shadow", "background_image", "rendered_fonts"):
            with self.subTest(field=field):
                data = capture(); data["elements"][0]["style"][field] = None
                self.assertTrue(self.validate(data))
        for field, raw_css in (("shadow", "rgba(0,0,0,.1) 0px 1px 2px"), ("background_image", "linear-gradient(red,blue)")):
            data = capture(); data["elements"][0]["style"][field] = raw_css
            self.assertTrue(self.validate(data))
        data = capture(); data["elements"][0]["evidence"].pop("text_bounds")
        self.assertTrue(self.validate(data))

    def test_missing_glyphs_cannot_pass_as_empty_icons_or_icon_buttons(self):
        for kind in ("icon", "chart-edge", "image", "icon-button"):
            data = capture(elements=[element(text="", kind=kind)])
            data["elements"][0]["state"]["enabled"] = True
            self.assertTrue(any("identity" in error["reason"] or "owned icon" in error["reason"] for error in self.validate(data)))

    def test_unparseable_svg_does_not_pass_even_if_both_bad_strings_are_equal(self):
        a, b = element(), element("n")
        for value in ("not JSON", '{"tag":"path","attributes":{"d":"M0 0"}}'):
            a["icon"] = b["icon"] = {"source": "svg", "glyph": value}
            self.assertTrue(compare_elements([a], [b])["icon_mismatch"])
            self.assertTrue(any("SVG glyph" in error["reason"] for error in self.validate(capture(elements=[a]))))

    def test_textless_code_container_does_not_require_nonexistent_font_or_lines(self):
        item = element(text="", kind="code")
        item["style"]["font_size"] = item["style"]["font_weight"] = item["style"]["foreground"] = None
        item["layout"] = {"wrap": None, "truncation": None, "line_count": None}
        item["evidence"].pop("text_bounds")
        self.assertEqual(self.validate(capture(elements=[item])), [])


class MatrixReportTests(unittest.TestCase):
    def test_full_matrix_requires_exact_504_cases(self):
        spec = json.loads((Path(__file__).parent / "scenes.json").read_text(encoding="utf-8"))
        cases = expected_cases(spec, "full")
        self.assertEqual(len(cases), 504)
        self.assertIn("en-US-dark-1024x700-menu-help", cases)
        self.assertIn("zh-CN-light-1440x900-quick-start", cases)
        self.assertEqual(len(expected_cases(spec, "smoke")), 7)

    def test_missing_native_capture_writes_failure_report_and_html(self):
        spec = {"languages": ["en-US"], "themes": ["dark"], "sizes": [[20, 20]], "scenes": ["group"]}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); output = root / "report"
            result = run(root / "source", output, spec=spec)
            self.assertFalse(result["passed"])
            self.assertEqual(result["summary"]["macos"]["scenes_checked"], 0)
            self.assertGreater(result["summary"]["macos"]["counts"]["extraction_errors"], 0)
            self.assertTrue((output / "parity-report.json").exists())
            self.assertTrue((output / "en-US-dark-20x20-group-windows.html").exists())
            self.assertTrue((output / "en-US-dark-20x20-group-macos.html").exists())
            self.assertEqual(result["exceptions"], [])

    def test_complete_fixture_reports_success_but_truncated_matrix_fails(self):
        from PIL import Image
        spec = {"languages": ["en-US"], "themes": ["dark"], "sizes": [[20, 20]], "scenes": ["group"]}
        scene = "en-US-dark-20x20-group"; viewport = {"width": 20, "height": 20, "scale": 1}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / "source"
            for client in ("reference", "reference-macos", "windows", "macos"):
                path = source / client; path.mkdir(parents=True)
                item = element(client); item["bounds"] = {"x": 1, "y": 1, "width": 10, "height": 10}
                data = capture(client, [item], scene, viewport)
                (path / f"{scene}.elements.json").write_text(json.dumps(data), encoding="utf-8")
                Image.new("RGB", (20, 20), "white").save(path / f"{scene}.png")
            result = run(source, root / "complete", spec=spec)
            self.assertTrue(result["passed"])
            self.assertEqual(result["summary"]["windows"]["matched_elements"], 1)
            self.assertEqual(result["scenes"][0]["platforms"]["windows"]["pixel_difference"]["changed_pixels"], 0)
            self.assertTrue((root / "complete" / "images" / "windows" / f"{scene}.png").exists())
            expanded = deepcopy(spec); expanded["scenes"].append("private")
            result = run(source, root / "truncated", spec=expanded)
            self.assertFalse(result["passed"])
            self.assertEqual(result["summary"]["windows"]["scenes_expected"], 2)
            self.assertEqual(result["summary"]["windows"]["scenes_passed"], 1)

    def test_raw_tree_sidecars_are_copied_next_to_element_json(self):
        from PIL import Image
        spec = {"languages": ["en-US"], "themes": ["dark"], "sizes": [[20, 20]], "scenes": ["group"]}
        scene = "en-US-dark-20x20-group"; viewport = {"width": 20, "height": 20, "scale": 1}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / "source"; output = root / "report"
            for client in ("reference", "reference-macos", "windows", "macos"):
                path = source / client; path.mkdir(parents=True)
                data = capture(client, [element(client)], scene, viewport)
                if client == "windows":
                    data["raw_evidence"] = {kind: f"{scene}.{kind}.json" for kind in ("uia", "xaml", "dom", "ax", "input-text")}
                    for kind, filename in data["raw_evidence"].items():
                        (path / filename).write_text(json.dumps({"tree_kind": kind, "raw_nodes": ["independent capture"]}), encoding="utf-8")
                (path / f"{scene}.elements.json").write_text(json.dumps(data), encoding="utf-8")
                Image.new("RGB", (20, 20), "white").save(path / f"{scene}.png")
            # An independently saved sidecar must survive even if an extractor
            # has not yet added a raw_evidence key to its projected JSON.
            raw_dom = source / "reference" / f"{scene}.dom.json"
            raw_dom.write_text('{"documents": ["unprojected reference"]}', encoding="utf-8")
            result = run(source, output, spec=spec)
            self.assertTrue(result["passed"])
            copied_json = output / "elements" / "windows" / f"{scene}.elements.json"
            references = json.loads(copied_json.read_text(encoding="utf-8"))["raw_evidence"]
            for filename in references.values():
                self.assertEqual((copied_json.parent / filename).read_bytes(), (source / "windows" / filename).read_bytes())
            self.assertEqual((output / "elements" / "reference" / raw_dom.name).read_bytes(), raw_dom.read_bytes())
            # A dangling raw evidence reference fails even when the projected
            # elements and screenshots otherwise all match.
            (source / "windows" / f"{scene}.uia.json").unlink()
            result = run(source, root / "missing-sidecar", spec=spec)
            self.assertFalse(result["passed"])
            errors = result["scenes"][0]["platforms"]["windows"]["extraction_errors"]
            self.assertTrue(any(f"{scene}.uia.json" in error["reason"] for error in errors))

    def test_raw_invalid_native_elements_are_counted_and_reported(self):
        from PIL import Image
        spec = {"languages": ["en-US"], "themes": ["dark"], "sizes": [[20, 20]], "scenes": ["group"]}
        scene = "en-US-dark-20x20-group"; viewport = {"width": 20, "height": 20, "scale": 1}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / "source"; output = root / "report"
            for client in ("reference", "reference-macos", "windows", "macos"):
                path = source / client; path.mkdir(parents=True)
                items = [element(client)]
                if client == "macos":
                    items = [{"legacy_text": "First extracted element"}, {"legacy_text": "Second extracted element"}]
                data = capture(client, items, scene, viewport)
                (path / f"{scene}.elements.json").write_text(json.dumps(data), encoding="utf-8")
                Image.new("RGB", (20, 20), "white").save(path / f"{scene}.png")
            result = run(source, output, spec=spec)
            self.assertFalse(result["passed"])
            for values in (result["summary"]["macos"], result["scenes"][0]["platforms"]["macos"]):
                self.assertEqual(values["raw_native_elements"], 2)
                self.assertEqual(values["valid_native_elements"], 0)
                self.assertEqual(values["invalid_native_elements"], 2)
                self.assertEqual(values["native_elements"], 0)  # backward-compatible field
                self.assertGreater(values["counts"]["extraction_errors"], 0)
            self.assertEqual(result["summary"]["windows"]["raw_native_elements"], 1)
            self.assertEqual(result["summary"]["windows"]["valid_native_elements"], 1)
            self.assertEqual(result["summary"]["windows"]["invalid_native_elements"], 0)
            scene_html = (output / f"{scene}-macos.html").read_text(encoding="utf-8")
            self.assertIn("2 raw elements; 0 structurally comparable; 2 unusable", scene_html)
            copied = json.loads((output / "elements" / "macos" / f"{scene}.elements.json").read_text(encoding="utf-8"))
            self.assertEqual(len(copied["elements"]), 2)

    def test_lightweight_reports_preserve_full_report_values_and_failures(self):
        spec = {"languages": ["en-US"], "themes": ["dark"], "sizes": [[20, 20]], "scenes": ["group", "private"]}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); output = root / "report"
            result = run(root / "source", output, spec=spec)
            complete = json.loads((output / "parity-report.json").read_text(encoding="utf-8"))
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(complete, result)
            self.assertEqual(summary, {key: value for key, value in complete.items() if key != "scenes"})
            self.assertFalse(summary["passed"])
            self.assertEqual(summary["expected_scenes_per_platform"], 2)
            self.assertEqual(summary["reported_scenes"], 2)
            self.assertEqual(summary["expected_platform_comparisons"], 4)
            self.assertEqual(summary["reported_platform_comparisons"], 4)
            self.assertNotIn("scenes", summary)
            self.assertIn('href="summary.json"', (output / "index.html").read_text(encoding="utf-8"))
            for scene in complete["scenes"]:
                filename = scene["scene_id"] + ".parity.json"
                self.assertEqual(json.loads((output / filename).read_text(encoding="utf-8")), scene)
                for suffix in ("", "-windows", "-macos"):
                    page = (output / (scene["scene_id"] + suffix + ".html")).read_text(encoding="utf-8")
                    self.assertIn(f'href="{filename}"', page)
                    self.assertIn('href="summary.json"', page)

    def test_each_platform_uses_its_actual_reference_without_key_normalization(self):
        from PIL import Image
        spec = {"languages": ["en-US"], "themes": ["dark"], "sizes": [[20, 20]], "scenes": ["group"]}
        scene = "en-US-dark-20x20-group"; viewport = {"width": 20, "height": 20, "scale": 1}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / "source"; output = root / "report"
            for client in ("reference", "reference-macos", "windows", "macos"):
                path = source / client; path.mkdir(parents=True)
                mac = client in ("reference-macos", "macos")
                data = capture(client, [element(client, "⌘B" if mac else "Ctrl+B")], scene, viewport)
                (path / f"{scene}.elements.json").write_text(json.dumps(data), encoding="utf-8")
                Image.new("RGB", (20, 20), "white" if mac else "black").save(path / f"{scene}.png")
            result = run(source, output, spec=spec, reference_root=source / "reference", macos_reference_root=source / "reference-macos")
            self.assertTrue(result["passed"])
            platforms = result["scenes"][0]["platforms"]
            self.assertEqual(platforms["macos"]["reference_platform"], "macos")
            self.assertEqual(platforms["windows"]["reference_platform"], "windows")
            self.assertEqual(platforms["macos"]["pixel_difference"]["changed_pixels"], 0)
            self.assertEqual(platforms["windows"]["pixel_difference"]["changed_pixels"], 0)
            self.assertTrue((output / "elements" / "reference-macos" / f"{scene}.elements.json").exists())
            self.assertIn("images/reference-macos/", (output / f"{scene}-macos.html").read_text(encoding="utf-8"))
            (source / "reference-macos" / f"{scene}.elements.json").unlink()
            result = run(source, root / "missing-mac", spec=spec)
            self.assertFalse(result["passed"])
            self.assertGreater(result["summary"]["macos"]["counts"]["extraction_errors"], 0)
            self.assertEqual(result["summary"]["macos"]["raw_reference_elements"], 0)
            self.assertEqual(result["summary"]["windows"]["scenes_passed"], 1)


if __name__ == "__main__":
    unittest.main()
