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
                      "background": [0, 0, 0, 0], "border_color": [0, 0, 0, 0], "border_width": 0, "corner_radius": 0},
            "state": {key: None for key in STATE_FIELDS},
            "layout": {"wrap": "none", "truncation": "none", "line_count": 1}, "icon": None, "evidence": {"source": "test-only fixture"}}


def capture(client="reference", elements=None, scene="zh-CN-light-1440x900-group", viewport=None):
    elements = elements if elements is not None else [element()]
    return {"schema_version": 1, "client": client, "scene_id": scene,
            "viewport": viewport or {"width": 1440, "height": 900, "scale": 1},
            "extraction_errors": [], "coverage": {"raw_nodes": len(elements), "emitted_elements": len(elements), "unmeasured": []},
            "elements": elements}


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
            for client in ("reference", "windows", "macos"):
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
            for client in ("reference", "windows", "macos"):
                path = source / client; path.mkdir(parents=True)
                data = capture(client, [element(client)], scene, viewport)
                if client == "windows":
                    data["raw_evidence"] = {kind: f"{scene}.{kind}.json" for kind in ("uia", "xaml", "dom", "ax")}
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
            for client in ("reference", "windows", "macos"):
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


if __name__ == "__main__":
    unittest.main()
