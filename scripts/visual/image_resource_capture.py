"""Actual loaded image response bytes and retained DOM-object receipts.

The observer attaches before navigation. It never fetches a resource itself,
decodes a URI as image content, draws an image or changes the production DOM.
Only completed responses observed for this page can supply resource bytes.
"""
import base64
import json
from pathlib import Path
import time


IMAGE_STATE = """function() {
  const r=this.getBoundingClientRect();
  return {tag:this.localName,connected:this.isConnected,owner_document_url:this.ownerDocument.URL,
    in_current_document:this.ownerDocument===document,src:this.src,current_src:this.currentSrc,
    src_attribute:this.getAttribute('src'),srcset_attribute:this.getAttribute('srcset'),
    sizes_attribute:this.getAttribute('sizes'),complete:this.complete,
    natural_width:this.naturalWidth,natural_height:this.naturalHeight,
    bounds:{x:r.x,y:r.y,width:r.width,height:r.height}};
}"""


def same_image_state(before, after):
    """Identity is separately bound by the retained backend/remote object."""
    fields = ("tag", "connected", "owner_document_url", "in_current_document", "src", "current_src",
        "src_attribute", "srcset_attribute", "sizes_attribute", "complete", "natural_width", "natural_height", "bounds")
    return isinstance(before, dict) and isinstance(after, dict) and all(before.get(key) == after.get(key) for key in fields)


def bind_loaded_response(owner, responses):
    """Bind a stable, loaded owner to actual same-URL response bytes only.

    Multiple observations are allowed only when every completed successful
    response has identical bytes and media type. There is no most-recent guess.
    Redirects, fragments, unobserved cache/blob/data resources and missing or
    failed responses remain explicit unknowns rather than extra network reads.
    """
    result = {"source": "actual image Response body + retained CDP img object", "status": "unknown",
        "owner": owner, "binding": {"current_src": None, "response_ids": [],
            "rule": "stable actual DOM object/currentSrc; all observed matching image responses completed successfully with identical bytes and media type"},
        "media_type": None, "byte_length": None, "body_base64": None, "body_file": None,
        "decoded_paint": None, "errors": list(owner.get("errors", []))}
    before, after = owner.get("before_screenshot"), owner.get("after_source_evidence")
    if not same_image_state(before, after):
        result["errors"].append("Actual retained image state changed or lacks a before/after screenshot receipt")
    if not isinstance(after, dict) or after.get("tag") != "img" or after.get("connected") is not True or after.get("in_current_document") is not True:
        result["errors"].append("The retained object is not a connected image in the actual current document")
    elif after.get("complete") is not True or not isinstance(after.get("natural_width"), (int, float)) or after["natural_width"] <= 0 or not isinstance(after.get("natural_height"), (int, float)) or after["natural_height"] <= 0:
        result["errors"].append("Actual image decode has not completed with nonzero intrinsic dimensions")
    current = after.get("current_src") if isinstance(after, dict) else None
    result["binding"]["current_src"] = current
    matches = [row for row in responses if current and row.get("url") == current and row.get("resource_type") == "image"]
    result["binding"]["response_ids"] = [row["id"] for row in matches]
    if not matches:
        result["errors"].append("No actual observed Image response matches this currentSrc; URI content is not fetched or decoded as a substitute")
    elif any(row.get("finished") is not True or row.get("failure") or row.get("errors")
            or not isinstance(row.get("status"), int) or not 200 <= row["status"] < 300
            or row.get("body_base64") is None or not row.get("byte_length") for row in matches):
        result["errors"].append("A matching actual response is missing, unfinished, unsuccessful or has no readable body")
    elif len({(row["body_base64"], row.get("media_type")) for row in matches}) != 1:
        result["errors"].append("The same actual URI has multiple different image resources; DOM-to-response content binding is ambiguous")
    else:
        source = matches[0]
        if not source.get("media_type", "").startswith("image/"):
            result["errors"].append("The actual matching response has no image media type; bytes remain raw evidence")
        elif not result["errors"]:
            result.update(status="loaded-response-bytes", media_type=source["media_type"], byte_length=source["byte_length"],
                body_base64=source["body_base64"], body_file=source["body_file"])
    return result


class ImageResourceCapture:
    def __init__(self, page, output, case_id):
        self.page, self.output, self.case_id = page, Path(output), case_id
        self.path = self.output / (case_id + ".image-resources.json")
        self.responses, self.owners, self.retained, self.requests = [], {}, {}, []
        self.bindings = {}
        self.event_revision, self.binding_event_revision = 0, None
        self.errors, self.steps = [], []
        self.cdp = None
        self.listeners = [("request", self.on_request), ("response", self.on_response),
            ("requestfinished", self.on_finished), ("requestfailed", self.on_failed)]
        for event, callback in self.listeners:
            page.on(event, callback)
        self.save()

    def save(self):
        self.path.write_text(json.dumps({"source": "page image response events registered before navigation; retained actual CDP image objects",
            "responses": self.responses, "images": list(self.owners.values()), "bindings": self.bindings, "steps": self.steps, "errors": self.errors,
            "event_revision": self.event_revision, "binding_event_revision": self.binding_event_revision,
            "measurement_limit": "Resource bytes are not decoded vector/raster paint or proof of canonical image parity. No extra fetch or canvas render."},
            ensure_ascii=False, indent=2), encoding="utf-8")

    def entry(self, request):
        for actual, row in self.requests:
            if actual is request:
                return row
        if request.resource_type != "image":
            return None
        row = {"id": "image-response-" + str(len(self.responses) + 1), "url": request.url, "request_url": request.url,
            "resource_type": request.resource_type, "method": request.method, "finished": False, "failure": None,
            "status": None, "status_text": None, "headers": None, "media_type": None,
            "body_base64": None, "byte_length": None, "body_file": None, "errors": [],
            "request_observed_host_monotonic": time.monotonic()}
        self.requests.append((request, row)); self.responses.append(row)
        return row

    def on_request(self, request):
        if self.entry(request) is not None:
            self.event_revision += 1
            self.save()

    def on_response(self, response):
        row = self.entry(response.request)
        if row is None:
            return
        self.event_revision += 1
        self.retained[row["id"]] = response
        try:
            headers = response.headers
            row.update(url=response.url, status=response.status, status_text=response.status_text, headers=headers,
                media_type=headers.get("content-type", "").split(";", 1)[0].strip().lower(),
                response_observed_host_monotonic=time.monotonic())
        except Exception as error:
            row["errors"].append("Response metadata: " + str(error))
        self.save()

    def on_finished(self, request):
        row = self.entry(request)
        if row is not None:
            self.event_revision += 1
            row.update(finished=True, finished_host_monotonic=time.monotonic()); self.save()

    def on_failed(self, request):
        row = self.entry(request)
        if row is not None:
            self.event_revision += 1
            row.update(failure=request.failure or "Actual requestfailed event", failed_host_monotonic=time.monotonic()); self.save()

    def read_object(self, object_id):
        result = self.cdp.send("Runtime.callFunctionOn", {"objectId": object_id, "functionDeclaration": IMAGE_STATE,
            "returnByValue": True, "awaitPromise": False})
        if result.get("exceptionDetails") or not isinstance(result.get("result", {}).get("value"), dict):
            raise RuntimeError("Actual image state read failed: " + json.dumps(result, ensure_ascii=False))
        return result["result"]["value"]

    def before_screenshot(self, cdp):
        self.cdp = cdp
        self.steps.append({"stage": "actual_dom_images_before_screenshot", "status": "started", "host_monotonic": time.monotonic()}); self.save()
        try:
            root = cdp.send("DOM.getDocument", {"depth": 0})["root"]["nodeId"]
            node_ids = cdp.send("DOM.querySelectorAll", {"nodeId": root, "selector": "img"})["nodeIds"]
            for node_id in node_ids:
                node = cdp.send("DOM.describeNode", {"nodeId": node_id})["node"]
                backend = node["backendNodeId"]
                owner = {"backend_node_id": backend, "node_id": node_id, "actual_node": node,
                    "before_screenshot": None, "after_source_evidence": None, "errors": []}
                self.owners[backend] = owner
                try:
                    resolved = cdp.send("DOM.resolveNode", {"backendNodeId": backend})
                    object_id = resolved["object"]["objectId"]
                    owner["resolved_object"] = resolved["object"]
                    owner["remote_object_id"] = object_id
                    owner["before_screenshot"] = self.read_object(object_id)
                except Exception as error:
                    owner["errors"].append(str(error))
        except Exception as error:
            self.errors.append("Before-screenshot DOM image capture: " + str(error))
        self.steps.append({"stage": "actual_dom_images_before_screenshot", "status": "completed", "host_monotonic": time.monotonic()}); self.save()

    def collect(self):
        self.steps.append({"stage": "actual_image_resources_after_source_evidence", "status": "started", "host_monotonic": time.monotonic()}); self.save()
        for owner in self.owners.values():
            try:
                owner["after_source_evidence"] = self.read_object(owner["remote_object_id"])
            except Exception as error:
                owner["errors"].append("Retained object: " + str(error))
        for row in self.responses:
            response = self.retained.get(row["id"])
            if response is None or row["finished"] is not True or row["failure"] or not isinstance(row["status"], int) or not 200 <= row["status"] < 300:
                continue  # Never wait for an unfinished network body on a paused clock.
            self.steps.append({"stage": "response_body", "response": row["id"], "status": "started", "host_monotonic": time.monotonic()}); self.save()
            try:
                body = response.body()
                if not isinstance(body, bytes):
                    raise TypeError("Actual response.body did not return bytes")
                path = self.output / (self.case_id + "." + row["id"] + ".body")
                path.write_bytes(body)
                row.update(body_base64=base64.b64encode(body).decode("ascii"), byte_length=len(body), body_file=path.name)
            except Exception as error:
                row["errors"].append("Actual completed response body: " + str(error))
            self.steps.append({"stage": "response_body", "response": row["id"], "status": "completed", "host_monotonic": time.monotonic()}); self.save()
        images = {}
        for backend, owner in self.owners.items():
            images[str(backend)] = bind_loaded_response(owner, self.responses)
        self.bindings = images
        self.binding_event_revision = self.event_revision
        self.steps.append({"stage": "actual_image_resources_after_source_evidence", "status": "completed", "host_monotonic": time.monotonic()}); self.save()
        return {"source": "actual loaded image response observation", "file": self.path.name,
            "images": images, "responses": self.responses, "errors": list(self.errors), "binding_event_revision": self.binding_event_revision}

    def after_extraction(self, elements):
        stable = self.binding_event_revision is not None and self.binding_event_revision == self.event_revision
        receipt = {"stage": "image_response_stability_after_extraction", "binding_event_revision": self.binding_event_revision,
            "event_revision": self.event_revision, "stable": stable, "host_monotonic": time.monotonic()}
        self.steps.append(receipt)
        if not stable:
            reason = "Actual image request/response events changed after resource binding and before extraction completed"
            self.errors.append(reason)
            for row in elements.get("elements", []):
                resource = row.get("evidence", {}).get("image_resource")
                if resource is not None:
                    resource["status"] = "unknown"; resource.setdefault("errors", []).append(reason)
                    elements.setdefault("coverage", {}).setdefault("unmeasured", []).append({"element": row["id"], "property": "image.loaded_resource", "reason": reason})
                    elements.setdefault("extraction_errors", []).append({"type": "image_resource_binding_changed", "node": row["id"], "reason": reason})
            for raw in elements.get("raw_nodes", []):
                if raw.get("image_resource") is not None:
                    raw["image_resource"]["status"] = "unknown"; raw["image_resource"].setdefault("errors", []).append(reason)
        elements.setdefault("capture_evidence", {}).setdefault("image_resources", {}).update(receipt= self.path.name, after_extraction=receipt)
        self.save()

    def close(self):
        for owner in self.owners.values():
            if owner.get("remote_object_id"):
                try:
                    self.cdp.send("Runtime.releaseObject", {"objectId": owner["remote_object_id"]})
                    owner["remote_object_released"] = True
                except Exception as error:
                    owner["errors"].append("Release actual image object: " + str(error))
        for event, callback in self.listeners:
            self.page.remove_listener(event, callback)
        self.save()
