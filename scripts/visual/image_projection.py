"""Project independently bound, actually loaded SVG bytes into image content.

No asset path, URI or icon name supplies content. Element layout, clipping and
style stay separate from resource paint; a decode never proves final pixels.
"""
import base64
import binascii
import copy

from image_paint import svg_paint_evidence
from image_resource_capture import bind_loaded_response, same_image_state


REFERENCE_SOURCE = "actual image Response body + retained CDP img object"
WINDOWS_SOURCE = "Actual production Image and SvgImageSource.SetSourceAsync packaged-byte binding"
REFERENCE_CONTENT_GAP = "Actual resource bytes are preserved separately; decoded vector/raster paint is not measured by the URI or this transport collector."


class ImageBindingError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise ImageBindingError(reason)


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def actual_bytes(encoded, length):
    require(isinstance(encoded, str), "Actual source has no base64 content bytes")
    require(integer(length) and length > 0, "Actual source byte length is missing or nonpositive")
    try:
        content = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (ValueError, UnicodeError, binascii.Error) as error:
        raise ImageBindingError("Actual source base64 is invalid: " + str(error)) from error
    require(len(content) == length, "Decoded actual byte count disagrees with the captured source length")
    return content


def reference_bytes(element, observation, stability):
    resource = element.get("evidence", {}).get("image_resource")
    require(isinstance(resource, dict), "Actual DOM image has no loaded resource receipt")
    require(resource.get("source") == REFERENCE_SOURCE and resource.get("status") == "loaded-response-bytes"
        and resource.get("errors") == [], "Actual DOM image resource binding is incomplete or failed")
    require(isinstance(observation, dict) and observation.get("errors") == [], "Actual response observation is absent or failed")
    require(isinstance(stability, dict) and stability.get("stable") is True
        and integer(stability.get("event_revision")) and stability.get("event_revision") == stability.get("binding_event_revision")
        and stability["event_revision"] == observation.get("binding_event_revision"), "Actual image responses were not stable through element extraction")
    require(isinstance(resource.get("receipt_file"), str) and resource["receipt_file"]
        and resource["receipt_file"] == observation.get("file"), "DOM resource evidence is not linked to the actual response receipt")
    owner = resource.get("owner")
    require(isinstance(owner, dict) and integer(owner.get("backend_node_id")) and owner["backend_node_id"] > 0,
        "Actual DOM backend image identity is unavailable")
    backend = owner["backend_node_id"]
    actual_node, resolved = owner.get("actual_node"), owner.get("resolved_object")
    require(isinstance(actual_node, dict) and actual_node.get("backendNodeId") == backend
        and actual_node.get("nodeName") == "IMG" and actual_node.get("nodeType") == 1,
        "Actual described DOM image does not match the retained backend identity")
    require(isinstance(resolved, dict) and resolved.get("subtype") == "node" and isinstance(owner.get("remote_object_id"), str)
        and owner["remote_object_id"] and resolved.get("objectId") == owner["remote_object_id"],
        "Actual retained DOM remote object is not the described image")
    observed = observation.get("images", {}).get(str(backend))
    require(isinstance(observed, dict) and isinstance(observed.get("owner"), dict), "No source observation exists for this actual backend node")
    for key in ("backend_node_id", "actual_node", "remote_object_id", "resolved_object", "before_screenshot", "after_source_evidence", "errors"):
        require(owner.get(key) == observed["owner"].get(key), "DOM image receipt differs from its actual source observation: " + key)
    require(same_image_state(owner.get("after_source_evidence"), owner.get("at_extraction")),
        "Actual DOM image changed between source evidence and element extraction")
    responses = observation.get("responses")
    require(isinstance(responses, list), "Actual image response list is missing")
    rebound = bind_loaded_response(owner, responses)
    require(rebound["status"] == "loaded-response-bytes" and rebound["errors"] == [],
        "Independent recheck of actual loaded image binding failed: " + " ".join(rebound["errors"]))
    for key in ("binding", "media_type", "byte_length", "body_base64", "body_file"):
        require(resource.get(key) == rebound.get(key), "Actual DOM resource binding disagrees with response evidence: " + key)
    require(resource.get("media_type") == "image/svg+xml", "Actual loaded image format is unsupported; only independently bound SVG bytes are decoded")
    content = actual_bytes(resource.get("body_base64"), resource.get("byte_length"))
    ids = rebound["binding"]["response_ids"]
    matched = [row for row in responses if row.get("id") in ids]
    require(len(matched) == len(ids) and len(set(ids)) == len(ids), "Actual response identities are duplicated or incomplete")
    for row in matched:
        require(row.get("headers", {}).get("content-type", "").split(";", 1)[0].strip().lower() == "image/svg+xml",
            "Actual response headers do not establish SVG media type")
        require(actual_bytes(row.get("body_base64"), row.get("byte_length")) == content,
            "Actual matching responses do not contain identical resource bytes")
    return content, {"platform": "reference", "resource": copy.deepcopy(resource), "actual_responses": copy.deepcopy(matched),
        "after_extraction": copy.deepcopy(stability)}


def windows_bytes(element):
    source = element.get("evidence", {}).get("image_source_evidence")
    require(isinstance(source, dict) and source.get("type") == "Microsoft.UI.Xaml.Media.Imaging.SvgImageSource",
        "Actual current native image source is missing or is an unsupported non-SVG format")
    asset = source.get("svg_asset")
    require(isinstance(asset, dict) and asset.get("source") == WINDOWS_SOURCE,
        "Actual native SetSourceAsync byte binding receipt is absent")
    for field in ("content_binding_complete", "registered_image_same_object", "bound_source_same_com_identity", "image_is_loaded", "exact_byte_stream"):
        require(asset.get(field) is True, "Actual native image binding is not independently confirmed: " + field)
    require(asset.get("phase") == "decoded" and asset.get("load_status") == "Success", "Actual current SvgImageSource decode did not complete successfully")
    for field in ("identity_error", "source_failed_status", "image_failed_message", "exception_type", "exception_message", "exception_hresult"):
        require(field in asset and asset[field] is None, "Actual native image failure/exception evidence is missing or nonempty: " + field)
    require(asset.get("mime_type") == "image/svg+xml" and asset.get("content_encoding") == "base64",
        "Actual native content type or encoding is unsupported")
    content = actual_bytes(asset.get("content_bytes"), asset.get("byte_length"))
    for field in ("stream_bytes_written", "stream_length"):
        require(integer(asset.get(field)) and asset[field] == len(content), "Actual submitted native stream length does not match content bytes: " + field)
    return content, {"platform": "windows", "image_source_evidence": copy.deepcopy(source)}


def apply_decoded_image(element, read_content, unmeasured, errors):
    """Keep raw transport identity; only measured content may become icon identity."""
    evidence = element.setdefault("evidence", {})
    evidence["transport_icon"] = copy.deepcopy(element.get("icon"))
    element["icon"] = None
    try:
        content, source = read_content()
        parsed = svg_paint_evidence(content, source)
        evidence["image_paint"] = parsed
        parsed["binding_verification"] = {"status": "verified-loaded-content", "source": source["platform"],
            "quantity": "Actual image/current-source byte binding; element transform, clipping, opacity and screenshot presentation remain separately measured"}
        require(parsed.get("status") == "decoded" and isinstance(parsed.get("paint"), dict),
            "Actual loaded SVG paint is unsupported or invalid: " + str(parsed.get("error")))
        element["icon"] = copy.deepcopy(parsed["paint"])
        # This exact collector-owned gap is the only failure a successful decode
        # can resolve. Other image/layout/style/state errors remain untouched.
        unmeasured[:] = [gap for gap in unmeasured if not (gap.get("element") == element["id"]
            and gap.get("property") == "image.rendered_content" and gap.get("reason") == REFERENCE_CONTENT_GAP)]
        return True
    except (ImageBindingError, TypeError, KeyError, AttributeError) as error:
        reason = str(error)
        if "image_paint" not in evidence:
            evidence["image_paint"] = {"status": "binding-unavailable", "paint": None, "decoded_paint": None,
                "content_binding_status": "unverified", "presentation_identity_proven": False,
                "error": {"type": type(error).__name__, "message": reason}}
        unmeasured.append({"element": element["id"], "property": "image.rendered_content", "reason": reason})
        errors.append({"type": "image_content_projection_unavailable", "node": element["id"], "reason": reason})
        return False


def project_reference_images(elements, observation):
    unmeasured = elements.setdefault("coverage", {}).setdefault("unmeasured", [])
    errors = elements.setdefault("extraction_errors", [])
    stability = (elements.get("capture_evidence", {}).get("image_resources") or {}).get("after_extraction")
    for element in elements.get("elements", []):
        if element.get("kind") == "image" and element.get("evidence", {}).get("tag") == "img":
            apply_decoded_image(element, lambda: reference_bytes(element, observation, stability), unmeasured, errors)


def project_windows_image(element, unmeasured, errors):
    if element.get("kind") == "image":
        apply_decoded_image(element, lambda: windows_bytes(element), unmeasured, errors)
