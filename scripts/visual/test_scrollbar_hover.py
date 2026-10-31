"""Pure mock transport/pixel fixtures. No browser, process or UI is launched."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import scrollbar_hover as hover
import test_scrollbar_pixels as pixel_fixtures


def fixture():
    _, evidence = pixel_fixtures.ScrollbarPixelTests().fixture()
    evidence.update(owner_backend_node_id=6, owner_bounds={"x": 0, "y": 10, "width": 20, "height": 80},
        client_width=10, client_height=80, client_left=0, client_top=0, offset_width=20, offset_height=80,
        scroll_width=10, scroll_height=100, scroll_left=0, scroll_top=20)
    evidence["ancestry"][0].update(transform="none", perspective="none", zoom="1")
    evidence["gutters"]["vertical"]["bounds"] = {"x": 10, "y": 10, "width": 10, "height": 80}
    evidence["original_png"] = {"vertical": {"status": "measured-ink",
        "ink_bounds": {"x": 13, "y": 28, "width": 4, "height": 54}}}
    viewport = {"width": 100, "height": 120, "scale": 1}
    raw = {"id": "dom-synthetic", "scrollbar": evidence}
    state = {"owner_connected": True, "owner_bounds": copy.deepcopy(evidence["owner_bounds"]),
        "device_pixel_ratio": 1, "viewport": {"width": 100, "height": 120},
        "visual_viewport": {"scale": 1, "offset_left": 0, "offset_top": 0},
        "owner_metrics": {key: evidence[key] for key in ("client_width", "client_height", "client_left", "client_top",
            "offset_width", "offset_height", "scroll_width", "scroll_height", "scroll_left", "scroll_top")},
        "owner_coordinate_style": {"transform": "none", "perspective": "none", "zoom": "1"},
        "focus": {"same_retained_element": True, "document_has_focus": True, "tag": "BODY", "id": ""},
        "scrollables": [{"index": 0, "connected": True, "x": 0, "y": 20}]}
    pointer = {"source": "synthetic completed move fixture", "scope": "group-without-subsequent-pointer-actions",
        "returned_normally": True, "x": 120, "y": 140}
    return raw, viewport, state, pointer


class MockSurface:
    """Synthetic hit rectangle is independent of the explicit ink pixel cells."""
    def __init__(self, state, pointer):
        self.state = copy.deepcopy(state)
        self.original_state = copy.deepcopy(state)
        self.pointer = [pointer["x"], pointer["y"]]
        self.inputs, self.shots = [], []
        self.mode = None
        self.release = []

    def send(self, method, params):
        if method == "Browser.getVersion":
            return {"product": "HeadlessChrome/" + hover.VERSION, "revision": "@" + hover.REVISION}
        if method == "DOM.resolveNode":
            return {"object": {"objectId": "actual-owner-fixture"}}
        if method == "Runtime.releaseObject":
            self.release.append(params["objectId"])
            return {}
        if method == "Input.dispatchMouseEvent":
            self.inputs.append(copy.deepcopy(params))
            self.pointer = [params["x"], params["y"]]
            if self.mode == "input-failure" and len(self.inputs) == 1:
                raise RuntimeError("synthetic CDP input failure")
            if self.mode == "changed-scroll" and len(self.inputs) == 1:
                self.state["owner_metrics"]["scroll_top"] += 1
            return {}
        if method == "Runtime.callFunctionOn":
            function = params["functionDeclaration"]
            if function == hover.INSTALL:
                return {"result": {"objectId": "retained-context-fixture"}}
            if function == hover.STATE:
                return {"result": {"value": copy.deepcopy(self.state)}}
            if function == hover.RESTORE_STATE:
                actions = [] if self.state == self.original_state else [{"action": "restore_changed_scroll"}]
                self.state = copy.deepcopy(self.original_state)
                return {"result": {"value": actions}}
        raise AssertionError("Unexpected browser method in pure mock: " + method)

    def pixels(self):
        hit = 10 <= self.pointer[0] < 20 and 25 <= self.pointer[1] < 85
        image = Image.new("RGBA", (10, 80), (255, 255, 255, 255))
        color = (160, 160, 160, 255) if hit else (210, 210, 210, 255)
        if self.mode == "no-hover-response":
            color = (210, 210, 210, 255)
        if self.mode == "third-response" and len(self.inputs) >= 4 and self.pointer != [120, 140]:
            color = (175, 175, 175, 255)
        for y in range(18, 72):
            for x in range(3, 7):
                image.putpixel((x, y), color)
        if self.mode == "wrong-paint-region" and hit:
            image.putpixel((0, 0), (100, 100, 100, 255))
        return image

    def screenshot(self, **kwargs):
        self.shots.append(copy.deepcopy(kwargs))
        if self.mode == "screenshot-failure" and len(self.shots) == 2:
            raise RuntimeError("synthetic screenshot failure")
        image = self.pixels()
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        data = stream.getvalue()
        Path(kwargs["path"]).write_bytes(data)
        return data


class ScrollbarHoverTests(unittest.TestCase):
    def observe(self, folder, mode=None, budget=None):
        raw, viewport, state, pointer = fixture()
        surface = MockSurface(state, pointer)
        original_image = surface.pixels()
        original = (original_image.size, original_image.tobytes())
        surface.mode = mode
        observation = hover.HoverObservation(surface, surface, raw, viewport, original, folder, pointer)
        if budget is None:
            result = observation.run()
        else:
            with patch.object(hover, "MAX_OBSERVATIONS", budget):
                result = observation.run()
        return result, surface, raw

    def test_actual_mock_input_and_png_membership_retains_raw_crop_evidence_without_promotion(self):
        with tempfile.TemporaryDirectory() as folder:
            result, surface, _ = self.observe(folder)
            self.assertEqual(result["status"], "diagnostic-observed", result["errors"])
            self.assertEqual(result["diagnostic_observed_hit_bounds"], {"x": 10, "y": 25, "width": 10, "height": 60})
            self.assertIsNone(result["canonical_hit_bounds"])
            self.assertIsNone(result["canonical_outer_bounds"])
            self.assertTrue(result["restoration"]["original_png_equal"])
            self.assertEqual(surface.pointer, [120, 140])
            self.assertLessEqual(len(result["observations"]), hover.MAX_OBSERVATIONS)
            self.assertEqual(surface.release, ["retained-context-fixture", "actual-owner-fixture"])
            for shot in surface.shots:
                self.assertEqual(shot["clip"], {"x": 10, "y": 10, "width": 10, "height": 80})
                self.assertEqual(shot["animations"], "allow")
                self.assertTrue(Path(shot["path"]).exists())
            self.assertTrue(all(item["type"] == "mouseMoved" and item["buttons"] == 0 for item in surface.inputs))

    def test_scroll_metrics_do_not_determine_the_observed_rectangle(self):
        with tempfile.TemporaryDirectory() as folder:
            raw, viewport, state, pointer = fixture()
            raw["scrollbar"].update(scroll_top=700, scroll_height=90000)
            state["owner_metrics"].update(scroll_top=700, scroll_height=90000)
            surface = MockSurface(state, pointer)
            image = surface.pixels()
            result = hover.HoverObservation(surface, surface, raw, viewport, (image.size, image.tobytes()), folder, pointer).run()
            self.assertEqual(result["status"], "diagnostic-observed", result["errors"])
            self.assertEqual(result["diagnostic_observed_hit_bounds"], {"x": 10, "y": 25, "width": 10, "height": 60})

    def test_errors_third_pixels_and_scroll_change_stay_unknown_and_pointer_is_restored(self):
        for mode in ("input-failure", "screenshot-failure", "third-response", "changed-scroll", "no-hover-response", "wrong-paint-region"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                result, surface, _ = self.observe(folder, mode)
                self.assertEqual(result["status"], "unknown")
                self.assertTrue(result["errors"])
                self.assertEqual(surface.pointer, [120, 140])
                self.assertIsNone(result["canonical_hit_bounds"])
                self.assertIsNone(result["canonical_outer_bounds"])
                self.assertEqual(result["observations"][-1]["phase"], "restore")
                if mode == "changed-scroll":
                    self.assertEqual(result["restoration"]["state_actions"], [{"action": "restore_changed_scroll"}])

    def test_small_budget_keeps_reserved_restoration_and_does_not_guess_remaining_edge(self):
        with tempfile.TemporaryDirectory() as folder:
            result, surface, _ = self.observe(folder, budget=5)
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(len(result["observations"]), 5)
            self.assertEqual(result["observations"][-1]["phase"], "restore")
            self.assertEqual(surface.pointer, [120, 140])
            self.assertIsNone(result["diagnostic_observed_hit_bounds"])

    def test_unknown_binary_response_is_never_a_negative_hit(self):
        with self.assertRaisesRegex(hover.UnknownObservation, "Unknown observation"):
            hover.search_edge(lambda point: "unknown", [15, 50], 10, 90, 1, True)
        with self.assertRaisesRegex(hover.UnknownObservation, "neither"):
            hover.classify_response(((1, 1), b"third"), ((1, 1), b"baseline"), ((1, 1), b"hover"))

    def test_source_binding_requires_both_browser_version_and_exact_actual_revision(self):
        actual = {"product": "HeadlessChrome/" + hover.VERSION, "revision": "@" + hover.REVISION}
        self.assertTrue(hover.browser_matches(actual))
        for changed in ({**actual, "revision": "different"}, {**actual, "product": "HeadlessChrome/157.0"},
                        {"product": actual["product"]}, {}):
            self.assertFalse(hover.browser_matches(changed))

    def test_fractional_occluded_missing_ink_or_transformed_candidate_is_unsupported(self):
        for failure in ("fractional", "occluded", "ink", "transform", "scale"):
            with self.subTest(failure=failure):
                raw, viewport, _, _ = fixture()
                if failure == "fractional":
                    raw["scrollbar"]["gutters"]["vertical"]["bounds"]["x"] = 10.2
                elif failure == "occluded":
                    raw["scrollbar"]["gutters"]["vertical"]["fully_visible"] = False
                elif failure == "ink":
                    raw["scrollbar"]["original_png"] = {}
                elif failure == "transform":
                    raw["scrollbar"]["ancestry"][0]["transform"] = "matrix(1,0,0,1,0,0)"
                else:
                    viewport["scale"] = 2
                self.assertIsNotNone(hover.candidate_issue(raw, viewport))
        raw, viewport, _, _ = fixture()
        self.assertIsNone(hover.candidate_issue(raw, viewport))

    def test_unknown_capture_pointer_preserves_every_owner_and_never_calls_browser(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}):
            raw, viewport, _, _ = fixture()
            elements = {"raw_nodes": [raw], "viewport": viewport, "elements": [{"id": "thumb", "bounds": None}],
                        "extraction_errors": ["existing UA part failure"]}
            before = copy.deepcopy(elements)
            page, cdp = Mock(), Mock()
            receipt = Path(folder) / "hover.json"
            result = hover.capture_scrollbar_hover(page, cdp, elements, Path(folder) / "original.png", receipt)
            self.assertEqual(elements, before)
            page.screenshot.assert_not_called()
            cdp.send.assert_not_called()
            self.assertFalse(result["canonical_geometry_supplied"])
            recorded = json.loads(receipt.read_text())
            self.assertEqual(recorded["parts"][0]["owner"], raw["id"])
            self.assertEqual(recorded["parts"][0]["status"], "unsupported")

    def test_original_png_and_elements_are_byte_and_value_unchanged_by_diagnostic(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}):
            raw, viewport, state, pointer = fixture()
            surface = MockSurface(state, pointer)
            image = Image.new("RGBA", (100, 120), (255, 255, 255, 255))
            image.paste(surface.pixels(), (10, 10))
            original = Path(folder) / "original.png"
            image.save(original)
            original_bytes = original.read_bytes()
            elements = {"raw_nodes": [raw], "viewport": viewport, "elements": [{"id": "thumb", "bounds": None}],
                        "extraction_errors": ["existing UA part failure"]}
            before = copy.deepcopy(elements)
            receipt = Path(folder) / "hover.json"
            result = hover.capture_scrollbar_hover(surface, surface, elements, original, receipt, pointer)
            recorded = json.loads(receipt.read_text())
            self.assertEqual(recorded["parts"][0]["status"], "diagnostic-observed", recorded)
            self.assertEqual(original.read_bytes(), original_bytes)
            self.assertEqual(elements, before)
            self.assertFalse(result["existing_gate_errors_removed"])
            self.assertEqual(recorded["browser_get_version"]["revision"], "@" + hover.REVISION)


if __name__ == "__main__":
    unittest.main()
