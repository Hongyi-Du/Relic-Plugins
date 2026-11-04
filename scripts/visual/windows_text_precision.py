"""Audit actual WinRT/COM text-range precision without replacing either capture.

Owner association uses the existing full RuntimeId validator. Range association
uses observed document-prefix UTF-16 endpoints, never a name/box/text search.
The probe observes document/visible ranges, not format ranges. Matching source
spans do not establish identical internal provider endpoints or an atomic frame.
No result from this module resolves an extraction error or proves visibility.
"""
import base64
import copy
import math
import struct
from collections import defaultdict

from windows_automation_identity import bind_automation_identities


PROBE_SOURCE = "Actual retained TextBlock owner and its existing AutomationPeer WinRT ITextProvider"
PROBE_PHASE = "after-independent-uia-and-provider-probe"
WINRT_ENDPOINTS = "DocumentRange.Clone + MoveEndpointByRange + CompareEndpoints + actual prefix GetText(-1) UTF16 lengths"
COM_ENDPOINTS = "Actual document clone endpoints moved to this range by MoveEndpointByRange; GetText prefixes, not text search"
COM_SOURCE = "IUIAutomationTextRange.GetBoundingRectangles COM SAFEARRAY<double>; before the .NET Rect[] projection"
COM_COORDINATES = "UI Automation screen coordinates before window-origin subtraction"


class EvidenceError(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise EvidenceError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def utf16(value):
    need(isinstance(value, str), "Source text is not a string")
    return value.encode("utf-16-le", errors="surrogatepass")


def text_record(value):
    need(isinstance(value, dict), "Actual UTF-16 text record is missing")
    data = utf16(value.get("value"))
    need(type(value.get("utf16_length")) is int and value["utf16_length"] == len(data) // 2,
         "Actual UTF-16 text length is inconsistent")
    try:
        raw = base64.b64decode(value.get("utf16_le_base64", ""), validate=True)
    except (ValueError, TypeError) as error:
        raise EvidenceError("Actual UTF-16 base64 is malformed") from error
    need(raw == data, "Actual UTF-16 bytes differ from the recorded text")
    return data


def observed_call(record, api):
    calls = record.get("calls")
    need(isinstance(calls, list), "WinRT API call journal is missing")
    found = [call for call in calls if isinstance(call, dict) and call.get("api") == api]
    need(len(found) == 1, "WinRT API call is absent or ambiguous: " + api)
    call = found[0]
    need(call.get("status") == "returned" and call.get("returned_normally") is True
         and call.get("hresult") is None
         and call.get("successful_hresult_not_exposed_by_projection") is True,
         "WinRT API call did not return an observed projected result: " + api)
    need(type(call.get("started_qpc")) is int and type(call.get("completed_qpc")) is int
         and record.get("started_qpc", -1) <= call["started_qpc"] <= call["completed_qpc"]
         <= record.get("completed_qpc", -1), "WinRT API call falls outside its recorded observation")
    return call


def rectangle_values(values, bits):
    need(isinstance(values, list) and len(values) % 4 == 0 and all(finite(v) for v in values),
         "Bounding rectangle values are missing, nonfinite or not quadruples")
    need(isinstance(bits, list) and bits == [struct.pack(">d", float(v)).hex().upper() for v in values],
         "Bounding rectangle IEEE754 evidence is missing or differs")
    return [values[i:i + 4] for i in range(0, len(values), 4)]


def winrt_range(record, document):
    need(isinstance(record, dict) and record.get("is_null") is False,
         "WinRT range is missing or null")
    rid = record.get("range_id")
    need(isinstance(rid, str) and record.get("endpoint_source") == WINRT_ENDPOINTS,
         "WinRT endpoint observation source is missing")
    data = text_record(record.get("text"))
    need(observed_call(record, rid + ".GetText(-1)").get("returned_value") == record["text"],
         "WinRT range text differs from its API result")
    values = record.get("bounding_rectangle_values")
    need(observed_call(record, rid + ".GetBoundingRectangles").get("returned_value") == values,
         "WinRT rectangle values differ from their API result")
    rectangles = rectangle_values(values, record.get("bounding_rectangle_value_bits_hex"))
    need(record.get("all_rectangle_values_finite") is True
         and type(record.get("rectangle_count")) is int and record["rectangle_count"] == len(rectangles)
         and type(record.get("rectangle_value_count")) is int and record["rectangle_value_count"] == len(values),
         "WinRT rectangle count/finiteness evidence is inconsistent")
    offsets = []
    for key, label in (("start", "Start"), ("end", "End")):
        endpoint = record.get(key)
        need(isinstance(endpoint, dict) and endpoint.get("endpoint") == label,
             "WinRT actual endpoint is missing")
        need(type(endpoint.get("prefix_start_to_document_start")) is int
             and endpoint["prefix_start_to_document_start"] == 0
             and type(endpoint.get("prefix_end_to_range_endpoint")) is int
             and endpoint["prefix_end_to_range_endpoint"] == 0,
             "WinRT clone endpoint comparisons are not equal")
        prefix = text_record(endpoint.get("actual_prefix_text"))
        offset = endpoint.get("verified_prefix_utf16_length")
        need(type(offset) is int and offset >= 0 and offset * 2 == len(prefix)
             and prefix == document[:offset * 2], "WinRT actual prefix is not this document prefix")
        offsets.append(offset)
    start, end = offsets
    need(start <= end <= len(document) // 2 and document[start * 2:end * 2] == data
         and record.get("offsets_within_document_snapshot") is True
         and record.get("text_matches_document_snapshot_slice") is True,
         "WinRT source span is not verified within the actual document")
    return tuple(offsets), rectangles


def com_range(record, document):
    need(isinstance(record, dict), "COM range is missing")
    identity = record.get("range_identity")
    need(isinstance(identity, dict) and identity.get("source") == COM_ENDPOINTS
         and identity.get("within_document") is True and identity.get("text_partition_valid") is True,
         "COM actual prefix endpoint identity is missing")
    start, end = identity.get("start_utf16"), identity.get("end_utf16")
    need(type(start) is int and type(end) is int and 0 <= start <= end <= len(document) // 2,
         "COM source span is outside the document")
    need(utf16(identity.get("start_prefix")) == document[:start * 2]
         and utf16(identity.get("end_prefix")) == document[:end * 2]
         and utf16(record.get("text")) == document[start * 2:end * 2],
         "COM prefix/text bytes do not describe the observed source span")
    need(record.get("raw_coordinate_space") == COM_COORDINATES,
         "COM raw coordinate space is unknown")
    return (start, end), rectangle_values(record.get("bounds_raw"), record.get("bounds_raw_ieee754_bits"))


def owner_document(node, owner, probe):
    need(owner.get("owner_type") == "Microsoft.UI.Xaml.Controls.TextBlock"
         and node.get("type") == "TextBlock" and owner.get("status") == "observed"
         and owner.get("peer_is_null") is False, "Actual TextBlock/provider observation is unavailable")
    for key in ("peer_owner_same_object", "peer_same_object_after", "peer_owner_same_object_after",
                "events_source_same_object_after", "document_text_same_before_after", "owner_text_same_before_after"):
        need(owner.get(key) is True, "Actual owner/provider stability is missing: " + key)
    need(type(owner.get("error_count")) is int and owner["error_count"] == 0
         and type(owner.get("contract_issue_count")) is int and owner["contract_issue_count"] == 0,
         "Owner probe has actual errors or contract issues")
    need(not any(issue.get("owner_id") == owner["owner_id"] for key in ("errors", "contract_issues")
                 for issue in probe[key]), "Probe journal contains an owner failure")
    identity = node["automation_identity_evidence"]
    need(owner.get("peer_type") == identity.get("peer_type"), "Observed owner peer type changed")
    before, after = owner.get("owner_before"), owner.get("owner_after")
    need(isinstance(before, dict) and isinstance(after, dict), "Actual owner state snapshots are missing")
    clocks = [probe.get("started_qpc"), owner.get("started_qpc"), before.get("qpc"),
              after.get("qpc"), owner.get("completed_qpc"), probe.get("completed_qpc")]
    need(all(type(value) is int for value in clocks) and clocks == sorted(clocks)
         and type(probe.get("qpc_frequency")) is int and probe["qpc_frequency"] > 0,
         "Actual probe/owner observation clocks are missing or inconsistent")
    state_fields = ("is_loaded", "visibility", "actual_width", "actual_height", "opacity", "root_origin_x",
                    "root_origin_y", "root_origin_source", "content_start_offset", "content_end_offset",
                    "is_text_trimmed", "text_trimming", "text_wrapping", "line_height")
    need(all(key in before and key in after and before[key] == after[key] for key in state_fields),
         "Owner layout/trimming/state changed during the actual probe")
    for key in ("actual_width", "actual_height", "opacity", "root_origin_x", "root_origin_y", "line_height"):
        need(finite(before[key]), "Actual owner state contains an unknown number: " + key)
    need(type(before["is_text_trimmed"]) is bool, "Actual trimming state is unknown")
    document = text_record(owner.get("document_text_before"))
    need(document == text_record(owner.get("document_text_after"))
         == text_record(before.get("text")) == text_record(after.get("text")) == utf16(node.get("text")),
         "Owner/XAML/document UTF-16 source changed")
    need(observed_call(owner, "DocumentRange.GetText(-1) before").get("returned_value") == owner["document_text_before"]
         and observed_call(owner, "DocumentRange.GetText(-1) after").get("returned_value") == owner["document_text_after"],
         "Document snapshots do not match the actual API journal")
    need(observed_call(owner, "owner state before").get("returned_value") == before
         and observed_call(owner, "owner state after").get("returned_value") == after,
         "Owner state does not match its actual API journal")
    events = owner.get("events_source_before")
    need(isinstance(events, dict) and events == owner.get("events_source_after"),
         "Actual EventsSource observation changed")
    need((events.get("is_null") is True and identity.get("events_source_is_null") is True)
         or (events.get("is_null") is False and events.get("same_object_as_observed_peer") is True
             and identity.get("events_source_same_peer") is True), "Actual EventsSource redirects away from the bound peer")
    return document


def differences(winrt, com):
    # Width and height need no screen/client translation. x/y remain in their
    # original API spaces; the window origin is exposed separately for audit.
    need(len(winrt) == len(com), "Actual WinRT/COM rectangle cardinality differs")
    result = []
    for index, (precise, native) in enumerate(zip(winrt, com)):
        pw, ph, nw, nh = precise[2], precise[3], native[2], native[3]
        if pw < 0 or ph < 0 or nw < 0 or nh < 0:
            category = "negative-provider-extent"
        elif pw == 0 or ph == 0:
            category = "winrt-already-zero-area"
        elif nw == 0 or nh == 0:
            category = ("positive-subpixel-extent-to-com-zero" if
                        ((nw != 0 or 0 < pw < 1) and (nh != 0 or 0 < ph < 1))
                        else "positive-extent-to-com-zero-unexplained")
        elif pw == nw and ph == nh:
            category = "equal-extents"
        else:
            category = "different-positive-extents"
        result.append({"rectangle_index": index, "category": category,
                       "width_delta_winrt_minus_com": pw - nw,
                       "height_delta_winrt_minus_com": ph - nh,
                       "extent_values_equal_integer_truncation": nw == math.trunc(pw) and nh == math.trunc(ph)})
    return result


def analyze_text_precision(xaml, uia, probe):
    """Return independently associated raw measurements; do not mutate inputs.

    ``range_associations`` contain direct document/visible source-span pairs.
    ``format_source_span_links`` only link format source spans to an already
    observed visible span; no WinRT format rectangle has been measured.
    ``unresolved`` retains missing/ambiguous observations, including true zeros.
    """
    result = {"source": "Actual full-RuntimeId owner and document-prefix UTF16 range precision audit",
              "case_id": uia.get("case_id"), "owners": [], "unresolved": [],
              "canonical_geometry_supplied": False, "visibility_supplied": False,
              "provider_errors_resolved": False,
              "frame_continuity_proven": False, "ancestor_clip_continuity_proven": False,
              "limitations": ["Observations are not atomic across independent API phases",
                  "Owner state snapshots do not observe continuous ancestor clip/scroll/transform state or the PNG frame",
                  "Source-span equality does not prove equal internal provider endpoints",
                  "Provider rectangles do not prove glyph ink or final PNG contribution",
                  "A zero provider extent never proves that text is hidden"],
              "original_uia_errors": copy.deepcopy(uia.get("extraction_errors")),
              "original_probe_errors": copy.deepcopy(probe.get("errors")),
              "original_probe_contract_issues": copy.deepcopy(probe.get("contract_issues"))}
    def unresolved(owner_id, reason, path=None):
        item = {"xaml_id": owner_id, "reason": reason}
        if path is not None:
            item["range_path"] = path
        result["unresolved"].append(item)
    try:
        need(probe.get("source") == PROBE_SOURCE and probe.get("phase") == PROBE_PHASE
             and probe.get("capture_completed") is True and probe.get("metadata_modified") is False
             and probe.get("create_peer_for_element_called") is False,
             "Actual completed read-only WinRT probe is unavailable")
        need(isinstance(uia.get("case_id"), str) and bool(uia["case_id"])
             and xaml.get("scene_id") == uia["case_id"] == probe.get("case_id"), "Capture case IDs differ")
        need(isinstance(probe.get("owners"), list) and isinstance(probe.get("errors"), list)
             and isinstance(probe.get("contract_issues"), list), "Probe owner/error journal is malformed")
        need(isinstance(xaml.get("raw_nodes"), list) and isinstance(uia.get("raw_nodes"), list),
             "Actual raw owner/provider trees are missing")
        need(all(isinstance(item, dict) for items in (xaml["raw_nodes"], uia["raw_nodes"],
                 probe["owners"], probe["errors"], probe["contract_issues"]) for item in items),
             "Actual owner/provider/probe records are malformed")
        binding = bind_automation_identities(xaml["raw_nodes"], uia)
        result["identity_binding"] = binding
    except (EvidenceError, TypeError, KeyError, AttributeError) as error:
        unresolved(None, str(error))
        return result
    owners, nodes, providers = defaultdict(list), defaultdict(list), defaultdict(list)
    for owner in probe["owners"]:
        if isinstance(owner, dict):
            owners[owner.get("owner_id")].append(owner)
    for node in xaml["raw_nodes"]:
        nodes[node.get("id")].append(node)
    for node in uia["raw_nodes"]:
        providers[node.get("id")].append(node)
    bound_ids = {pair["xaml_id"] for pair in binding["pairs"]}
    for owner_id in owners:
        if owner_id not in bound_ids:
            unresolved(owner_id, "No strict full-RuntimeId owner/provider binding")
    for pair in binding["pairs"]:
        owner_id, uia_id = pair["xaml_id"], pair["uia_id"]
        if owner_id not in owners:
            continue
        try:
            need(len(owners[owner_id]) == len(nodes[owner_id]) == len(providers[uia_id]) == 1,
                 "Actual owner/probe/provider ID is ambiguous")
            owner, node, provider = owners[owner_id][0], nodes[owner_id][0], providers[uia_id][0]
            document = owner_document(node, owner, probe)
            native = provider.get("text_pattern", {}).get("native_com")
            need(isinstance(native, dict) and native.get("source") == COM_SOURCE
                 and native.get("status") == "matched-to-managed-ranges"
                 and isinstance(native.get("runtime_id"), list)
                 and all(type(part) is int for part in native["runtime_id"])
                 and native.get("runtime_id") == pair["runtime_id"], "Independent COM range owner is not verified")
            need(utf16(native.get("document_text_before")) == document
                 == utf16(native.get("document_text_after")) == utf16(native.get("managed_document_text_after")),
                 "Independent native/managed document changed")
            need(isinstance(owner.get("visible_ranges"), list) and isinstance(native.get("visible_ranges"), list),
                 "Actual visible range inventories are missing")
            entry = {"xaml_id": owner_id, "uia_id": uia_id, "runtime_id": pair["runtime_id"],
                     "source_utf16_length": len(document) // 2,
                     "is_text_trimmed": owner["owner_before"]["is_text_trimmed"],
                     "window_origin": copy.deepcopy(uia.get("origin")),
                     "winrt_coordinate_space": probe.get("coordinate_space"),
                     "owner_probe_qpc": [owner.get("started_qpc"), owner.get("completed_qpc")],
                     "range_associations": [], "format_source_span_links": [],
                     "original_provider_errors": copy.deepcopy(provider.get("measurement_errors"))}
            result["owners"].append(entry)
            precise_visible = defaultdict(list)
            for index, observed in enumerate(owner["visible_ranges"]):
                try:
                    span, rectangles = winrt_range(observed, document)
                    need(observed["range_id"] == "visible-" + str(index), "WinRT visible range source order differs")
                    precise_visible[span].append((index, observed, rectangles))
                except EvidenceError as error:
                    unresolved(owner_id, str(error), "winrt.visible_ranges/" + str(index))
            observed_com_spans = defaultdict(list)
            for index, observed in enumerate(native["visible_ranges"]):
                try:
                    span, _ = com_range(observed, document)
                    observed_com_spans[span].append(index)
                except EvidenceError as error:
                    unresolved(owner_id, str(error), "com.visible_ranges/" + str(index))
            candidates = [("document", native.get("document"), owner.get("document_range"), None)]
            for index, observed in enumerate(native["visible_ranges"]):
                try:
                    span, _ = com_range(observed, document)
                    matches = precise_visible[span]
                    need(len(matches) == 1 and len(observed_com_spans[span]) == 1,
                         "Visible source span is missing or ambiguous in the actual inventories")
                    precise_index, precise, _ = matches[0]
                    need(precise_index == index, "Actual visible source order differs")
                    candidates.append(("visible_ranges/" + str(index), observed, precise, index))
                except EvidenceError as error:
                    unresolved(owner_id, str(error), "com.visible_ranges/" + str(index))
            for path, com, precise, visible_index in candidates:
                try:
                    span, raw_com = com_range(com, document)
                    precise_span, raw_winrt = winrt_range(precise, document)
                    need(span == precise_span, "Actual source spans differ")
                    if path == "document":
                        need(span == (0, len(document) // 2) and precise["range_id"] == "document",
                             "Document range does not cover the actual document")
                    comparison = differences(raw_winrt, raw_com)
                    record = {"com_range_path": path, "winrt_range_id": precise["range_id"],
                              "source_span_utf16": list(span), "text": com["text"],
                              "winrt_values": copy.deepcopy(precise["bounding_rectangle_values"]),
                              "winrt_value_bits_hex": copy.deepcopy(precise["bounding_rectangle_value_bits_hex"]),
                              "com_screen_values": copy.deepcopy(com["bounds_raw"]),
                              "com_value_bits_hex": copy.deepcopy(com["bounds_raw_ieee754_bits"]),
                              "rectangle_diagnostics": comparison,
                              "native_internal_endpoint_identity_proven": False}
                    entry["range_associations"].append(record)
                    for diagnostic in comparison:
                        if diagnostic["category"] in ("winrt-already-zero-area", "negative-provider-extent",
                                                       "positive-extent-to-com-zero-unexplained"):
                            unresolved(owner_id, diagnostic["category"] + "; no visibility/geometry resolution", path)
                    if visible_index is not None:
                        for fi, formatted in enumerate(com.get("format_runs", [])):
                            format_path = path + "/format_runs/" + str(fi)
                            try:
                                fspan, _ = com_range(formatted, document)
                                need(fspan == span, "No separately measured WinRT format subrange with these endpoints")
                                entry["format_source_span_links"].append({"com_range_path": format_path,
                                    "source_span_utf16": list(fspan), "observed_winrt_range_id": precise["range_id"],
                                    "winrt_format_range_measured": False,
                                    "com_screen_values": copy.deepcopy(formatted["bounds_raw"]),
                                    "reason": "Only the source span is equal; no WinRT format range was queried"})
                            except EvidenceError as error:
                                unresolved(owner_id, str(error), format_path)
                except EvidenceError as error:
                    unresolved(owner_id, str(error), path)
            for span, matches in precise_visible.items():
                if span not in observed_com_spans:
                    for _, precise, _ in matches:
                        unresolved(owner_id, "WinRT source span has no independently observed COM counterpart", precise["range_id"])
        except (EvidenceError, TypeError, KeyError, AttributeError) as error:
            unresolved(owner_id, str(error))
    return result
