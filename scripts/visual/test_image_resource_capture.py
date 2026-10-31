"""Pure response/DOM-object fixtures; no browser, image decode or network starts."""
import base64
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from image_resource_capture import ImageResourceCapture, bind_loaded_response


class ImageResourceTests(unittest.TestCase):
    def state(self, url="http://127.0.0.1:7777/static/icon.svg"):
        return {"tag": "img", "connected": True, "owner_document_url": "http://127.0.0.1:7777/", "in_current_document": True,
            "src": url, "current_src": url, "src_attribute": "/static/icon.svg", "srcset_attribute": None, "sizes_attribute": None,
            "complete": True, "natural_width": 256, "natural_height": 256, "bounds": {"x": 18, "y": 17, "width": 26, "height": 26}}

    def owner(self):
        return {"backend_node_id": 42, "remote_object_id": "actual-object", "before_screenshot": self.state(),
            "after_source_evidence": self.state(), "errors": []}

    def response(self, body=b'<svg viewBox="0 0 256 256"><circle cx="128" cy="128" r="8"/></svg>', response_id="image-response-1"):
        return {"id": response_id, "url": self.state()["current_src"], "resource_type": "image", "status": 200,
            "finished": True, "failure": None, "errors": [], "media_type": "image/svg+xml", "byte_length": len(body),
            "body_base64": base64.b64encode(body).decode("ascii"), "body_file": "case." + response_id + ".body"}

    def test_stable_actual_loaded_object_binds_completed_response_bytes_not_transport_uri(self):
        response = self.response()
        result = bind_loaded_response(self.owner(), [response])
        self.assertEqual(result["status"], "loaded-response-bytes")
        self.assertEqual(result["binding"]["response_ids"], ["image-response-1"])
        self.assertEqual(result["body_base64"], response["body_base64"])
        self.assertEqual(result["byte_length"], response["byte_length"])
        self.assertIsNone(result["decoded_paint"], "Obtaining loaded bytes does not establish rendered paint")
        self.assertEqual(result["errors"], [])

    def test_same_url_different_observed_bodies_fail_without_selecting_last_response(self):
        first, second = self.response(), self.response(b"different actual resource", "image-response-2")
        for rows in ([first, second], [second, first]):
            result = bind_loaded_response(self.owner(), rows)
            self.assertEqual(result["status"], "unknown"); self.assertIsNone(result["body_base64"])
            self.assertIn("ambiguous", " ".join(result["errors"]))
            self.assertEqual(result["binding"]["response_ids"], [row["id"] for row in rows])

    def test_repeated_identical_actual_responses_preserve_all_source_ids(self):
        first = self.response(); second = dict(first, id="image-response-2", body_file="case.second.body")
        result = bind_loaded_response(self.owner(), [first, second])
        self.assertEqual(result["status"], "loaded-response-bytes")
        self.assertEqual(result["binding"]["response_ids"], ["image-response-1", "image-response-2"])

    def test_missing_unfinished_failed_empty_and_nonimage_responses_remain_unknown(self):
        for variation in ("missing", "pending", "http", "failure", "body", "type", "read-error"):
            with self.subTest(variation=variation):
                response = self.response()
                if variation == "pending": response["finished"] = False
                elif variation == "http": response["status"] = 404
                elif variation == "failure": response["failure"] = "net::ERR_FAILED"
                elif variation == "body": response.update(body_base64="", byte_length=0)
                elif variation == "type": response["media_type"] = "text/plain"
                elif variation == "read-error": response["errors"] = ["Actual completed response body failed"]
                result = bind_loaded_response(self.owner(), [] if variation == "missing" else [response])
                self.assertEqual(result["status"], "unknown"); self.assertIsNone(result["body_base64"])
                self.assertTrue(result["errors"])

    def test_changed_actual_src_decode_state_connection_or_geometry_is_not_rebound(self):
        for change in ("current_src", "complete", "connected", "natural_width", "bounds", "in_current_document"):
            with self.subTest(change=change):
                owner = self.owner()
                owner["after_source_evidence"][change] = {"current_src": "http://127.0.0.1:7777/other.svg", "complete": False,
                    "connected": False, "natural_width": 0, "bounds": {"x": 19, "y": 17, "width": 26, "height": 26}, "in_current_document": False}[change]
                result = bind_loaded_response(owner, [self.response()])
                self.assertEqual(result["status"], "unknown"); self.assertIsNone(result["body_base64"])
                self.assertTrue(result["errors"])

    def test_unobserved_data_blob_fragment_and_redirect_uris_are_not_content_fallbacks(self):
        for url in ("data:image/svg+xml,%3Csvg/%3E", "blob:http://127.0.0.1:7777/actual", self.state()["current_src"] + "#view", "http://127.0.0.1:7777/redirect.svg"):
            owner = self.owner()
            for phase in ("before_screenshot", "after_source_evidence"):
                owner[phase].update(src=url, current_src=url)
            result = bind_loaded_response(owner, [self.response()])
            self.assertEqual(result["status"], "unknown"); self.assertIsNone(result["body_base64"])
            self.assertIn("No actual observed", " ".join(result["errors"]))

    def test_actual_raster_or_unimplemented_image_format_bytes_are_kept_without_claiming_decode(self):
        for media in ("image/png", "image/avif", "image/x-new-format"):
            response = dict(self.response(b"opaque actual body"), media_type=media)
            result = bind_loaded_response(self.owner(), [response])
            self.assertEqual(result["body_base64"], response["body_base64"])
            self.assertIsNone(result["decoded_paint"])

    def setup_observer(self, root, body=b"actual loaded SVG bytes"):
        page = Mock()
        capture = ImageResourceCapture(page, root, "actual-case")
        request = SimpleNamespace(resource_type="image", url=self.state()["current_src"], method="GET", failure=None)
        response = Mock(request=request, url=request.url, status=200, status_text="OK", headers={"content-type": "image/svg+xml; charset=utf-8"})
        response.body.return_value = body
        state = self.state()
        def send(method, params):
            if method == "DOM.getDocument": return {"root": {"nodeId": 1}}
            if method == "DOM.querySelectorAll": return {"nodeIds": [2]}
            if method == "DOM.describeNode": return {"node": {"nodeId": 2, "backendNodeId": 42, "nodeName": "IMG", "attributes": ["src", "/static/icon.svg"]}}
            if method == "DOM.resolveNode": return {"object": {"objectId": "actual-object", "type": "object", "subtype": "node"}}
            if method == "Runtime.callFunctionOn": return {"result": {"value": copy.deepcopy(state)}}
            if method == "Runtime.releaseObject": return {}
            raise AssertionError("Unexpected operation: " + method)
        return capture, page, request, response, Mock(send=Mock(side_effect=send)), state

    def test_observer_records_exact_response_body_and_live_object_without_fetch_or_canvas(self):
        body = b'\xef\xbb\xbf<svg xmlns="http://www.w3.org/2000/svg"><!-- preserved bytes --></svg>'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); observer, page, request, response, cdp, state = self.setup_observer(root, body)
            self.assertEqual([call.args[0] for call in page.on.call_args_list], ["request", "response", "requestfinished", "requestfailed"])
            observer.on_request(request); observer.on_response(response); observer.on_finished(request)
            observer.before_screenshot(cdp)
            result = observer.collect(); observer.close()
            bound = result["images"]["42"]
            self.assertEqual(bound["status"], "loaded-response-bytes")
            self.assertEqual((root / bound["body_file"]).read_bytes(), body)
            self.assertEqual(base64.b64decode(bound["body_base64"]), body)
            self.assertEqual(bound["owner"]["before_screenshot"], state)
            self.assertEqual(bound["owner"]["after_source_evidence"], state)
            receipt = json.loads(observer.path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["responses"][0]["status"], 200)
            self.assertTrue(receipt["responses"][0]["finished"])
            self.assertEqual(receipt["bindings"]["42"]["body_base64"], bound["body_base64"])
            self.assertTrue(receipt["images"][0]["remote_object_released"])
            response.body.assert_called_once_with()
            page.request.get.assert_not_called(); page.evaluate.assert_not_called(); page.goto.assert_not_called()
            self.assertEqual([call.args[0] for call in page.remove_listener.call_args_list], ["request", "response", "requestfinished", "requestfailed"])

    def test_pending_response_never_waits_for_body_and_remains_a_failed_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            observer, _, request, response, cdp, _ = self.setup_observer(Path(folder))
            observer.on_response(response); observer.before_screenshot(cdp)
            result = observer.collect(); observer.close()
            response.body.assert_not_called()
            self.assertEqual(result["images"]["42"]["status"], "unknown")
            self.assertFalse(result["responses"][0]["finished"])

    def test_body_read_failure_has_durable_pending_step_and_preserves_actual_response(self):
        with tempfile.TemporaryDirectory() as folder:
            observer, _, request, response, cdp, _ = self.setup_observer(Path(folder))
            def fail_body():
                receipt = json.loads(observer.path.read_text())
                self.assertEqual(receipt["steps"][-1]["stage"], "response_body")
                self.assertEqual(receipt["steps"][-1]["status"], "started")
                raise RuntimeError("Actual response body unavailable")
            response.body.side_effect = fail_body
            observer.on_response(response); observer.on_finished(request); observer.before_screenshot(cdp)
            result = observer.collect(); observer.close()
            self.assertEqual(result["images"]["42"]["status"], "unknown")
            self.assertEqual(result["responses"][0]["status"], 200)
            self.assertIn("Actual response body unavailable", result["responses"][0]["errors"][0])

    def test_removed_actual_img_fails_even_when_the_same_url_still_has_response_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            observer, _, request, response, cdp, state = self.setup_observer(Path(folder))
            observer.on_response(response); observer.on_finished(request); observer.before_screenshot(cdp)
            state["connected"] = False
            result = observer.collect(); observer.close()
            self.assertEqual(result["images"]["42"]["status"], "unknown")
            self.assertTrue(result["responses"][0]["body_base64"], "Actual bytes survive a failed DOM binding")

    def test_late_actual_image_response_invalidates_binding_without_erasing_original_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            observer, _, request, response, cdp, _ = self.setup_observer(Path(folder))
            observer.on_response(response); observer.on_finished(request); observer.before_screenshot(cdp)
            result = observer.collect()
            bound = copy.deepcopy(result["images"]["42"])
            elements = {"elements": [{"id": "actual-img", "evidence": {"image_resource": bound}}], "raw_nodes": []}
            observer.after_extraction(elements)
            self.assertEqual(bound["status"], "loaded-response-bytes")
            observer.on_response(response)
            observer.after_extraction(elements); observer.close()
            self.assertEqual(bound["status"], "unknown"); self.assertTrue(bound["body_base64"])
            self.assertEqual(elements["extraction_errors"][0]["type"], "image_resource_binding_changed")
            self.assertFalse(elements["capture_evidence"]["image_resources"]["after_extraction"]["stable"])


if __name__ == "__main__":
    unittest.main()
