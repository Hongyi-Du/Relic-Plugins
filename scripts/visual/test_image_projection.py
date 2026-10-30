"""Pure loaded-byte projection regressions; no application or network starts."""
import base64
import copy
import unittest

from image_projection import (REFERENCE_CONTENT_GAP, REFERENCE_SOURCE, WINDOWS_SOURCE,
    project_reference_images, project_windows_image)
from image_resource_capture import bind_loaded_response


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 30"><rect x="2" y="3" width="20" height="10" fill="#123456"/></svg>'


def reference_fixture(content=SVG, media="image/svg+xml"):
    uri = "http://127.0.0.1:7777/actual-resource"
    state = {"tag": "img", "connected": True, "owner_document_url": "http://127.0.0.1:7777/", "in_current_document": True,
        "src": uri, "current_src": uri, "src_attribute": "/actual-resource", "srcset_attribute": None, "sizes_attribute": None,
        "complete": True, "natural_width": 40, "natural_height": 30, "bounds": {"x": 10, "y": 20, "width": 26, "height": 26}}
    owner = {"backend_node_id": 42, "node_id": 2, "remote_object_id": "actual-object",
        "actual_node": {"backendNodeId": 42, "nodeId": 2, "nodeType": 1, "nodeName": "IMG"},
        "resolved_object": {"objectId": "actual-object", "subtype": "node", "type": "object"},
        "before_screenshot": copy.deepcopy(state), "after_source_evidence": copy.deepcopy(state), "errors": []}
    row = {"id": "image-response-1", "url": uri, "resource_type": "image", "status": 200, "finished": True,
        "failure": None, "errors": [], "media_type": media, "headers": {"content-type": media + "; charset=utf-8"},
        "byte_length": len(content), "body_base64": base64.b64encode(content).decode(), "body_file": "actual.body"}
    resource = bind_loaded_response(owner, [row])
    observation = {"file": "case.image-resources.json", "images": {"42": copy.deepcopy(resource)}, "responses": [row], "errors": [], "binding_event_revision": 3}
    resource["receipt_file"] = observation["file"]; resource["owner"]["at_extraction"] = copy.deepcopy(state)
    image = {"id": "image-42", "kind": "image", "bounds": state["bounds"], "visible_bounds": state["bounds"],
        "style": {"opacity": .7, "corner_radius": 5}, "icon": {"source": "image", "glyph": uri},
        "evidence": {"tag": "img", "image_resource": resource}}
    gap = {"element": image["id"], "property": "image.rendered_content", "reason": REFERENCE_CONTENT_GAP}
    elements = {"elements": [image], "extraction_errors": [], "coverage": {"unmeasured": [gap]},
        "capture_evidence": {"image_resources": {"after_extraction": {"stable": True, "event_revision": 3, "binding_event_revision": 3}}}}
    return elements, observation, image


def windows_fixture(content=SVG):
    asset = {"source": WINDOWS_SOURCE, "content_binding_complete": True, "registered_image_same_object": True,
        "bound_source_same_managed_object": False, "bound_source_same_com_identity": True, "identity_error": None,
        "image_is_loaded": True, "exact_byte_stream": True, "phase": "decoded", "load_status": "Success",
        "source_failed_status": None, "image_failed_message": None, "exception_type": None, "exception_message": None, "exception_hresult": None,
        "mime_type": "image/svg+xml", "content_encoding": "base64", "content_bytes": base64.b64encode(content).decode(),
        "byte_length": len(content), "stream_bytes_written": len(content), "stream_length": len(content),
        "resource_path": "Assets/actual-resource.svg", "uri_source": None, "source_opened_events": 1, "image_opened_events": 1}
    image = {"id": "native-image", "kind": "image", "icon": None, "bounds": {"x": 10, "y": 20, "width": 26, "height": 26},
        "style": {"opacity": .7, "corner_radius": 5}, "evidence": {"type": "Image", "image_source_evidence": {
            "type": "Microsoft.UI.Xaml.Media.Imaging.SvgImageSource", "uri": None, "stretch": "Uniform", "svg_asset": asset}}}
    return image, asset


class ImageProjectionTests(unittest.TestCase):
    def test_reference_decodes_only_verified_loaded_bytes_and_keeps_transport_and_raw_sources(self):
        elements, observation, image = reference_fixture()
        original, original_observation = copy.deepcopy(image), copy.deepcopy(observation)
        project_reference_images(elements, observation)
        self.assertEqual(image["icon"]["source"], "vector-image-v1")
        self.assertEqual(image["icon"]["glyph"]["layers"][0]["fill"], {"kind": "solid", "color": [18, 52, 86, 255]})
        self.assertEqual(image["evidence"]["transport_icon"], original["icon"])
        self.assertEqual(image["evidence"]["image_resource"], original["evidence"]["image_resource"])
        self.assertEqual(observation, original_observation)
        parsed = image["evidence"]["image_paint"]
        self.assertEqual(base64.b64decode(parsed["content_bytes"]), SVG)
        self.assertEqual(parsed["binding_verification"]["status"], "verified-loaded-content")
        self.assertEqual(parsed["content_binding_status"], "unverified-by-parser")
        self.assertFalse(parsed["presentation_identity_proven"])
        self.assertEqual(image["bounds"], original["bounds"]); self.assertEqual(image["style"], original["style"])
        self.assertEqual(elements["coverage"]["unmeasured"], []); self.assertEqual(elements["extraction_errors"], [])

    def test_success_removes_only_its_exact_collector_gap_and_keeps_all_other_failures(self):
        elements, observation, image = reference_fixture()
        other = [{"element": image["id"], "property": "image.rendered_content", "reason": "Independent screenshot paint remains unknown"},
            {"element": "different-image", "property": "image.rendered_content", "reason": REFERENCE_CONTENT_GAP},
            {"element": image["id"], "property": "style.corner_radius", "reason": "Actual corner unavailable"}]
        elements["coverage"]["unmeasured"] += copy.deepcopy(other)
        elements["extraction_errors"] = ["Actual unrelated extraction failure"]
        project_reference_images(elements, observation)
        self.assertEqual(elements["coverage"]["unmeasured"], other)
        self.assertEqual(elements["extraction_errors"], ["Actual unrelated extraction failure"])

    def test_reference_transport_port_is_not_identity_and_actual_changed_paint_remains_different(self):
        values = []
        for port, content in ((7777, SVG), (9999, SVG), (7777, SVG.replace(b"#123456", b"#654321"))):
            elements, observation, image = reference_fixture(content)
            for source in (image["evidence"]["image_resource"], observation["images"]["42"]):
                source["binding"]["current_src"] = source["binding"]["current_src"].replace(":7777/", f":{port}/")
                for phase in ("before_screenshot", "after_source_evidence", "at_extraction"):
                    if phase in source["owner"]:
                        for field in ("src", "current_src", "owner_document_url"):
                            source["owner"][phase][field] = source["owner"][phase][field].replace(":7777/", f":{port}/")
            observation["responses"][0]["url"] = observation["responses"][0]["url"].replace(":7777/", f":{port}/")
            image["icon"]["glyph"] = image["icon"]["glyph"].replace(":7777/", f":{port}/")
            project_reference_images(elements, observation); values.append(image["icon"])
        self.assertIsNotNone(values[0]); self.assertEqual(values[0], values[1]); self.assertNotEqual(values[0], values[2])

    def test_reference_revalidates_actual_responses_object_identity_and_live_checkpoint(self):
        for failure in ("backend", "actual-node", "remote-object", "state", "receipt", "late-event", "event-revision", "response-status", "response-header", "response-body", "response-length", "duplicated-response", "resource-error"):
            with self.subTest(failure=failure):
                elements, observation, image = reference_fixture()
                resource, row = image["evidence"]["image_resource"], observation["responses"][0]
                if failure == "backend": resource["owner"]["backend_node_id"] = 99
                elif failure == "actual-node": resource["owner"]["actual_node"]["nodeName"] = "DIV"
                elif failure == "remote-object": resource["owner"]["resolved_object"]["objectId"] = "different-object"
                elif failure == "state": resource["owner"]["at_extraction"]["complete"] = False
                elif failure == "receipt": resource["receipt_file"] = "different.image-resources.json"
                elif failure == "late-event": elements["capture_evidence"]["image_resources"]["after_extraction"]["stable"] = False
                elif failure == "event-revision": observation["binding_event_revision"] = 10
                elif failure == "response-status": row["status"] = 500
                elif failure == "response-header": row["headers"]["content-type"] = "text/plain"
                elif failure == "response-body": row["body_base64"] = base64.b64encode(b"different bytes").decode()
                elif failure == "response-length": row["byte_length"] += 1
                elif failure == "duplicated-response": observation["responses"].append(copy.deepcopy(row))
                else: resource["errors"].append("Actual resource failure")
                project_reference_images(elements, observation)
                self.assertIsNone(image["icon"]); self.assertTrue(elements["extraction_errors"])
                self.assertTrue(any(gap.get("reason") == REFERENCE_CONTENT_GAP for gap in elements["coverage"]["unmeasured"]))
                self.assertEqual(image["evidence"]["transport_icon"]["source"], "image")

    def test_success_boolean_alone_cannot_supply_reference_content_or_binding(self):
        elements, observation, image = reference_fixture()
        image["evidence"]["image_resource"] = {"source": REFERENCE_SOURCE, "status": "loaded-response-bytes", "errors": [],
            "body_base64": base64.b64encode(SVG).decode(), "byte_length": len(SVG)}
        project_reference_images(elements, observation)
        self.assertIsNone(image["icon"]); self.assertTrue(elements["extraction_errors"])

    def test_windows_actual_byte_stream_and_current_com_binding_decode_independently(self):
        image, asset = windows_fixture(); original = copy.deepcopy(image)
        gaps, errors = [], []
        project_windows_image(image, gaps, errors)
        self.assertEqual(image["icon"]["source"], "vector-image-v1")
        self.assertEqual(gaps, []); self.assertEqual(errors, [])
        self.assertEqual(image["evidence"]["image_source_evidence"], original["evidence"]["image_source_evidence"])
        self.assertFalse(asset["bound_source_same_managed_object"], "Actual COM identity, not wrapper identity, establishes the current source")
        self.assertFalse(image["evidence"]["image_paint"]["presentation_identity_proven"])
        self.assertEqual(base64.b64decode(image["evidence"]["image_paint"]["content_bytes"]), SVG)

    def test_windows_never_trusts_aggregate_binding_boolean_over_missing_or_failed_evidence(self):
        failures = {"source": "some other loader", "registered_image_same_object": False, "bound_source_same_com_identity": None,
            "content_binding_complete": False, "image_is_loaded": False, "exact_byte_stream": False, "phase": "decoding-actual-source",
            "load_status": "InvalidFormat", "identity_error": {}, "source_failed_status": "Other",
            "image_failed_message": "failed", "exception_type": "COMException", "exception_message": "actual exception",
            "exception_hresult": 0x80004005, "stream_length": len(SVG) + 1, "stream_bytes_written": len(SVG) - 1,
            "byte_length": True, "content_encoding": "uri", "mime_type": "image/png"}
        for field, value in failures.items():
            with self.subTest(field=field):
                image, asset = windows_fixture(); asset[field] = value
                gaps, errors = [], []; project_windows_image(image, gaps, errors)
                self.assertIsNone(image["icon"]); self.assertTrue(gaps); self.assertTrue(errors)
        image, asset = windows_fixture(); del asset["exception_hresult"]
        gaps, errors = [], []; project_windows_image(image, gaps, errors)
        self.assertIsNone(image["icon"]); self.assertTrue(errors, "Missing negative failure evidence is not assumed clear")

    def test_base64_corruption_or_length_disagreement_never_produces_partial_paint(self):
        for encoded, length in (("%%not base64%%", len(SVG)), (base64.b64encode(SVG).decode(), len(SVG) + 1), ("", 0)):
            for platform in ("reference", "windows"):
                with self.subTest(platform=platform, encoded=encoded):
                    if platform == "windows":
                        image, asset = windows_fixture(); asset.update(content_bytes=encoded, byte_length=length)
                        gaps, errors = [], []; project_windows_image(image, gaps, errors)
                    else:
                        elements, observation, image = reference_fixture()
                        for row in (image["evidence"]["image_resource"], observation["images"]["42"], observation["responses"][0]):
                            row.update(body_base64=encoded, byte_length=length)
                        project_reference_images(elements, observation); errors = elements["extraction_errors"]
                    self.assertIsNone(image["icon"]); self.assertTrue(errors)

    def test_unsupported_svg_and_raster_keep_raw_bytes_and_cannot_clear_content_failure(self):
        unsupported = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 30"><text>Unsupported text paint</text></svg>'
        for content, media in ((unsupported, "image/svg+xml"), (b"actual PNG body", "image/png")):
            elements, observation, image = reference_fixture(content, media)
            original = copy.deepcopy(image["evidence"]["image_resource"])
            project_reference_images(elements, observation)
            self.assertIsNone(image["icon"]); self.assertTrue(elements["extraction_errors"])
            self.assertEqual(image["evidence"]["image_resource"], original)
            if media == "image/svg+xml":
                parsed = image["evidence"]["image_paint"]
                self.assertEqual(parsed["status"], "error"); self.assertEqual(base64.b64decode(parsed["content_bytes"]), unsupported)
                self.assertTrue(parsed["error"])

    def test_windows_final_element_projector_invokes_actual_loaded_byte_projection(self):
        import test_windows_elements as fixtures
        image, _ = windows_fixture()
        node = fixtures.xaml_node("native-image", "Image", image_source_evidence=image["evidence"]["image_source_evidence"])
        result = fixtures.ProjectionTests().capture(fixtures.measured([node]), [fixtures.uia_node("actual-uia", "Image")])
        actual = next(row for row in result["elements"] if row["id"] == "native-image")
        self.assertEqual(actual["icon"]["source"], "vector-image-v1")
        self.assertIn("image_paint", actual["evidence"])

    def test_unbound_native_raster_stays_visible_and_retains_uri_only_as_raw_evidence(self):
        image, _ = windows_fixture()
        image["icon"] = {"source": "image", "glyph": "http://127.0.0.1:9999/api/avatar/image.png"}
        image["evidence"]["image_source_evidence"] = {"type": "Microsoft.UI.Xaml.Media.Imaging.BitmapImage", "uri": image["icon"]["glyph"]}
        original = copy.deepcopy(image)
        gaps, errors = [], []; project_windows_image(image, gaps, errors)
        self.assertEqual(image["kind"], "image"); self.assertIsNone(image["icon"])
        self.assertEqual(image["evidence"]["transport_icon"], original["icon"])
        self.assertEqual(image["evidence"]["image_source_evidence"], original["evidence"]["image_source_evidence"])
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
