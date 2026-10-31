"""Select bound, actually observed in-process UIA text-range geometry.

Original external UIA JSON/values/errors are never rewritten. The effective
copy records every selection and the precise diagnostic it resolves. This
does not certify fonts, ink coverage or continuous Composition/PNG identity.
"""
import base64
import copy
import json
import math
from collections import Counter
from pathlib import Path

from windows_automation_identity import bind_automation_identities, measured_id
from windows_text_precision import EvidenceError, need, com_range, rectangle_values, utf16


CONTRACT = "actual-inprocess-com-text-range-diagnostic-v1"
SOURCE = "Observed in-process public ITextRangeProvider screen-coordinate doubles, bound to the same retained peer and source range"
ENDPOINT_SOURCE = "DocumentRange.Clone + MoveEndpointByRange + CompareEndpoints + actual prefix GetText UTF16 length"
PLAIN_TEXT_LENGTH_SOURCE = "S_OK ITextRangeProvider.GetText(-1) + SysStringLen(actual BSTR); logical-flow UTF16 code units"
ZERO_ERROR = "COM text rectangle {index} is zero-area; original values retained, no inference that its text is hidden or covered."


def text_bytes(record):
    need(isinstance(record, dict) and record.get("is_null") is False, "Actual UTF16 value is absent or null")
    try:
        data = base64.b64decode(record.get("utf16_le_base64", ""), validate=True)
    except (ValueError, TypeError) as error:
        raise EvidenceError("Actual UTF16 base64 is malformed") from error
    need(type(record.get("utf16_length")) is int and len(data) == 2 * record["utf16_length"], "Actual UTF16 length differs")
    return data


def successful_call(com, name):
    calls = [call for call in com.get("calls", []) if call.get("api") == name]
    need(len(calls) == 1 and type(calls[0].get("hresult")) is int and calls[0]["hresult"] >= 0
         and calls[0].get("succeeded") is True, "Actual COM call was failed, missing or ambiguous: " + name)
    return calls[0]


def observed_prefix(point, com, document, path, index):
    """Read the logical plaintext projection, not structural endpoint distance."""
    need(isinstance(point, dict) and point.get("source") == ENDPOINT_SOURCE and point.get("endpoint") == index
         and point.get("start_compare") == point.get("end_compare") == 0 and "error" not in point,
         "Actual in-process endpoint comparisons are unavailable")
    for operation in ("Clone", "MoveEndpointByRange", "CompareEnd", "CompareStart", "ComparePrefixStartToEnd", "prefix.GetText(-1)"):
        call = successful_call(com, path + "." + operation)
        need(call["hresult"] == 0, "Actual prefix operation did not return S_OK: " + path + "." + operation)
    offset = point.get("verified_prefix_utf16_length")
    need(type(offset) is int and 0 <= offset <= len(document) // 2, "Actual prefix UTF16 endpoint remains unknown")
    comparison = point.get("prefix_start_to_end_compare")
    need(type(comparison) is int, "Actual prefix structural endpoint comparison is absent")
    measured_length = "plain_text_utf16_length" in point or "plain_text_length_source" in point
    if measured_length:
        # New collector receipts explicitly separate these two API quantities.
        # Do not manufacture the fields in historical captures.
        need(point.get("plain_text_length_source") == PLAIN_TEXT_LENGTH_SOURCE
             and type(point.get("plain_text_utf16_length")) is int
             and point["plain_text_utf16_length"] == offset
             and type(point.get("get_text_hresult")) is int and point["get_text_hresult"] == 0
             and point.get("prefix_structurally_collapsed") is (comparison == 0),
             "Actual plaintext length receipt differs from the prefix call or structural state")
    if (point.get("text") or {}).get("is_null") is True:
        bstr = point.get("bstr") or {}
        need(offset == 0 and bstr.get("pointer_is_null") is True
             and type(bstr.get("sys_string_len")) is int and bstr["sys_string_len"] == 0
             and bstr.get("source") == "SysStringLen on the actual successful GetText BSTR"
             and point["text"].get("utf16_length") is None and point["text"].get("utf16_le_base64") is None
             and point.get("null_bstr_collapsed_prefix") is (comparison == 0),
             "Actual null BSTR or separately measured structural state is inconsistent")
        need(measured_length or comparison == 0,
             "Historical noncollapsed null prefix has no explicit logical plaintext length receipt")
        prefix = b""
    else:
        prefix = text_bytes(point.get("text"))
    need(prefix == document[:offset * 2], "Actual prefix differs from the retained document")
    return offset


def observed_range(record, com, document, path):
    need(isinstance(record, dict) and record.get("range_path") == path and "error" not in record,
         "Actual in-process range is missing, failed or belongs to another path")
    successful_call(com, path + ".GetText(-1)")
    successful_call(com, path + ".GetBoundingRectangles")
    data = text_bytes(record.get("text"))
    offsets = []
    for index, label in enumerate(("start", "end")):
        offsets.append(observed_prefix(record.get(label), com, document, path + "." + label, index))
    start, end = offsets
    need(start <= end and document[start * 2:end * 2] == data
         and record.get("offsets_within_document_snapshot") is True
         and record.get("text_matches_document_snapshot_slice") is True,
         "Actual range text does not match its observed document endpoints")
    boxes = rectangle_values(record.get("bounding_rectangle_values"), record.get("bounding_rectangle_value_bits_hex"))
    metadata = record.get("safearray") or {}
    need(metadata.get("dimensions") == 1 and metadata.get("element_size") == 8 and metadata.get("vartype") == 5
         and type(metadata.get("lower_bound")) is int and type(metadata.get("upper_bound")) is int
         and metadata["upper_bound"] - metadata["lower_bound"] + 1 == 4 * len(boxes)
         and metadata.get("element_count") == 4 * len(boxes)
         and record.get("rectangle_count") == len(boxes) and record.get("rectangle_value_count") == 4 * len(boxes)
         and record.get("all_rectangle_values_finite") is True,
         "Actual in-process SAFEARRAY shape or rectangle count differs")
    return (start, end), boxes


def stable_owner(node, owner, pair, uia, probe, frame):
    need(owner.get("owner_type") == "Microsoft.UI.Xaml.Controls.TextBlock" and node.get("type") == "TextBlock"
         and owner.get("status") == "observed" and owner.get("peer_is_null") is False,
         "Actual in-process TextBlock owner is unavailable")
    for key in ("same_owner_object", "peer_same_object_after", "events_source_same_object_after",
                "core_runtime_id_matches_held_identity", "stream_consumed_by_api"):
        need(owner.get(key) is True, "Actual retained peer identity is not established: " + key)
    need(owner.get("held_identity_before") == node.get("automation_identity_evidence"), "Held peer receipt differs from the captured owner")
    need(probe.get("observer") == pair.get("observer") == owner["held_identity_before"].get("observer"),
         "Actual in-process probe belongs to another case/app/observer process")
    native = owner.get("native_identity") or {}
    need(native.get("status") == "measured" and native.get("failures") == [] and native.get("core_runtime_id_stable") is True
         and measured_id(native.get("core_runtime_id")) == tuple(pair["runtime_id"])
         == measured_id(native.get("core_runtime_id_recheck")), "Actual public-provider full RuntimeId differs")
    entry = owner.get("public_provider_entry") or {}
    need(entry.get("status") == "acquired-through-actual-fragment", "Actual Fragment-to-Simple provider route is unavailable")
    for name in ("QI(IRawElementProviderFragment, actual peer)", "QI(IRawElementProviderSimple, actual fragment)"):
        successful_call(entry, name)
    need(not any("error" in call or (type(call.get("hresult")) is int and call["hresult"] < 0)
                 for call in owner.get("lifecycle", [])), "Actual COM transport/lifecycle failed")
    com = owner.get("com") or {}
    need(com.get("status") == "observed" and com.get("errors") == []
         and com.get("coordinate_space") == "Unmodified ITextRangeProvider.GetBoundingRectangles screen-coordinate doubles"
         and com.get("document_text_same_before_after") is True, "Actual COM document read failed or changed")
    for operation in ("IRawElementProviderSimple.GetPatternProvider(Text)", "QI(ITextProvider)", "ITextProvider.DocumentRange",
                      "document-before.GetText(-1)", "ITextProvider.GetVisibleRanges", "document-after.GetText(-1)"):
        successful_call(com, operation)
    document = text_bytes(owner.get("owner_text_before"))
    need(document == text_bytes(owner.get("owner_text_after")) == utf16(node.get("text"))
         == text_bytes((com.get("document_text_before") or {}).get("text"))
         == text_bytes((com.get("document_text_after") or {}).get("text")), "Actual owner/document UTF16 differs")
    need(frame.get("case_id") == uia.get("case_id") == probe.get("case_id") and frame.get("app_pid") == uia.get("pid")
         and frame.get("errors") == [] and frame.get("changes") == [] and frame.get("disposed") is True,
         "Actual frame observations failed, changed or belong to another capture")
    binding = [item for item in frame.get("owners", []) if item.get("xaml_id") == node["id"]]
    need(len(binding) == 1 and binding[0].get("same_object_reference") is True, "Actual frame owner reference is ambiguous")
    object_id = binding[0].get("owner_object_id")
    states, phases = [], []
    for checkpoint in frame.get("checkpoints", []):
        need(checkpoint.get("same_owner_references") is True
             and type(frame.get("final_revision")) is int
             and checkpoint.get("revision") == checkpoint.get("revision_after") == frame.get("final_revision"), "Observed frame reference or revision changed")
        actual = [item for item in checkpoint.get("owners", []) if item.get("owner_object_id") == object_id]
        need(len(actual) == 1, "Actual frame owner snapshot is missing or ambiguous")
        states.append(actual[0]); phases.append(checkpoint.get("stage"))
    need(phases == ["begin_before_desktop_readback", "before_desktop_readback", "after_desktop_readback", "after_text_range_provider_probe"],
         "Actual desktop-readback frame observations are incomplete")
    for label in ("frame_before", "frame_after"):
        point = owner.get(label) or {}
        need(point.get("xaml_id") == node["id"] and point.get("owner_object_id") == object_id
             and point.get("same_retained_owner") is True and point.get("same_identity_peer") is True
             and point.get("same_identity_events_source") is True
             and point.get("revision") == point.get("revision_after") == frame.get("final_revision"),
             "Actual in-process frame owner/state is unbound")
        states.append(point.get("state"))
    need(states and all(state == states[0] for state in states), "Actual retained object state changed between measurements")
    clocks = [frame.get("started_qpc")]
    for checkpoint in frame["checkpoints"][:3]:
        clocks.extend((checkpoint.get("started_qpc"), checkpoint.get("completed_qpc")))
    clocks.extend((probe.get("started_qpc"), owner.get("started_qpc"), owner["frame_before"].get("qpc"),
                   owner["frame_before"].get("completed_qpc"), owner["frame_after"].get("qpc"),
                   owner["frame_after"].get("completed_qpc"), owner.get("completed_qpc"), probe.get("completed_qpc")))
    clocks.extend((frame["checkpoints"][-1].get("started_qpc"), frame["checkpoints"][-1].get("completed_qpc"), frame.get("ended_qpc")))
    need(all(type(clock) is int for clock in clocks) and clocks == sorted(clocks)
         and type(probe.get("qpc_frequency")) is int and probe["qpc_frequency"] > 0
         and probe["qpc_frequency"] == frame.get("qpc_frequency"), "Actual measurement/frame clock binding differs")
    origin = uia.get("origin") or {}
    need(all(type(origin.get(k)) in (int, float) and math.isfinite(origin[k]) for k in ("x", "y"))
         and states[0].get("client_origin") == [origin["x"], origin["y"]]
         and states[0].get("rasterization_scale") == 1 and uia.get("viewport", {}).get("scale") == 1,
         "Actual screen/client origin or unit rasterization scale is unavailable or differs")
    return document, origin, {"runtime_id": pair["runtime_id"], "owner_object_id": object_id,
        "state_checkpoints_equal": len(states), "origin": copy.deepcopy(origin), "rasterization_scale": 1,
        "observed_frame_qpc": clocks,
        "global_composition_continuity_proven": frame.get("continuity_proven"),
        "frame_limitations": copy.deepcopy(frame.get("limitations")), "font_or_final_pixel_evidence_promoted": False}


def ranges(pattern, precise=False):
    yield "document_range", pattern.get("document_range" if precise else "document"), None
    for index, visible in enumerate(pattern.get("visible_ranges", [])):
        path = "visible_ranges[" + str(index) + "]"
        yield path, visible, None
        for fi, run in enumerate(visible.get("format_runs", [])):
            yield path + ".format_runs[" + str(fi) + "]", run, visible.get("format_enumeration") if precise else None


def select_observed_text_geometry(xaml, uia, probe, frame):
    effective = copy.deepcopy(uia)
    audit = {"source": SOURCE, "selections": [], "unavailable_ranges": [], "resolved_diagnostics": [],
             "original_extraction_errors": copy.deepcopy(uia.get("extraction_errors", [])),
             "original_uia_rewritten": False, "font_or_final_pixel_evidence_promoted": False}
    result = {"effective_uia": effective, "audit": audit, "all_original_failures_resolved": False}
    try:
        need(isinstance(probe, dict) and probe.get("contract") == CONTRACT and probe.get("capture_completed") is True,
             "Actual completed in-process COM observation is missing")
        need(xaml.get("scene_id") == uia.get("case_id") == probe.get("case_id")
             and xaml.get("viewport") == uia.get("viewport"), "Actual capture scene or viewport differs")
        binding = bind_automation_identities(xaml["raw_nodes"], uia)
        nodes = {node["id"]: node for node in xaml["raw_nodes"]}
        providers = {node["id"]: node for node in uia["raw_nodes"]}
        selected_providers = {node["id"]: node for node in effective["raw_nodes"]}
        resolved = Counter()
        for pair in binding["pairs"]:
            owners = [item for item in probe.get("owners", []) if item.get("owner_id") == pair["xaml_id"]]
            if not owners:
                continue
            try:
                need(len(owners) == 1, "Actual in-process owner observation is ambiguous")
                owner, node, provider = owners[0], nodes[pair["xaml_id"]], providers[pair["uia_id"]]
                document, origin, owner_proof = stable_owner(node, owner, pair, uia, probe, frame)
                external = (provider.get("text_pattern") or {}).get("native_com") or {}
                need(external.get("status") == "matched-to-managed-ranges" and external.get("runtime_id") == pair["runtime_id"],
                     "External COM range owner is not independently bound")
                need(utf16(external.get("document_text_before")) == document == utf16(external.get("document_text_after"))
                     == utf16(external.get("managed_document_text_after")), "External source document changed")
                observed = {path: (record, enumeration) for path, record, enumeration in ranges(owner["com"], precise=True)}
                effective_pattern = selected_providers[provider["id"]]["text_pattern"]
                effective_native = {path: record for path, record, _ in ranges(effective_pattern["native_com"])}
                effective_managed = {path: record for path, record, _ in ranges(effective_pattern)}
                for path, original, _ in ranges(external):
                    try:
                        need(path in observed and path in effective_managed, "Matching actual range category/order is unavailable")
                        precise, enumeration = observed[path]
                        span, actual = observed_range(precise, owner["com"], document, path)
                        need(type(precise.get("started_qpc")) is int and type(precise.get("completed_qpc")) is int
                             and owner["frame_before"]["completed_qpc"] <= precise["started_qpc"] <= precise["completed_qpc"]
                             <= owner["frame_after"]["qpc"], "Actual range read lies outside its bound frame observations")
                        external_span, raw = com_range(original, document)
                        need(span == external_span and len(raw) == len(actual), "Actual source endpoints or rectangle cardinality differ")
                        # A zero plaintext prefix can contain reserved structural
                        # positions. External receipts record plaintext offsets,
                        # not cross-channel CompareEndpoints results. Measuring
                        # its length does not fill that independent identity gap.
                        need(not any((precise.get(label, {}).get("text") or {}).get("is_null") is True
                                     and precise[label].get("prefix_start_to_end_compare") != 0
                                     for label in ("start", "end")),
                             "Noncollapsed empty plaintext prefix has no cross-channel structural endpoint identity")
                        if ".format_runs[" in path:
                            step = precise.get("format_step") or {}
                            for operation in ("ClonePrevious", "MoveEndpointByUnit(End,Format,1)", "CompareEndToParentEndBeforeClamp",
                                              "CompareStartToPreviousStart", "CompareEndToPreviousEnd", "CompareStartToEnd",
                                              "CompareEndToParentEndAfterClamp"):
                                successful_call(owner["com"], path + "." + operation)
                            need(isinstance(enumeration, dict) and enumeration.get("complete") is True
                                 and step.get("units_moved", 0) > 0 and step.get("start_vs_previous_start") == 0
                                 and step.get("end_vs_previous_end", 0) > 0 and step.get("start_vs_end", 0) < 0
                                 and step.get("end_vs_parent_end_after_clamp", 1) <= 0,
                                 "Actual format enumeration/endpoint step is incomplete")
                        zero = [i for i, box in enumerate(raw) if box[2] == 0 or box[3] == 0]
                        if not zero:
                            continue
                        need(raw and all(box[2] >= 0 and box[3] >= 0 for box in raw)
                             and all(box[2] > 0 and box[3] > 0 for box in actual), "Actual precise geometry is still empty, negative or zero-area")
                        # Same screen coordinates/cardinality and an exact
                        # observed integer projection identify this narrow loss.
                        # This never rounds the replacement measurement.
                        need(all(a[:2] == b[:2] and b[2:] == [math.trunc(a[2]), math.trunc(a[3])]
                                 for a, b in zip(actual, raw)), "Channels do not show the measured integer-extent loss")
                        managed = effective_managed[path]
                        need(managed.get("native_bounds_raw") == original.get("bounds_raw")
                             and managed.get("range_identity") == original.get("range_identity"),
                             "Managed/external original range relationship differs")
                        original_boxes = [{"x": b[0] - origin["x"], "y": b[1] - origin["y"], "width": b[2], "height": b[3]} for b in raw]
                        need(all(item.get("bounds") == original_boxes and item.get("bounds_status") == "contains-zero-area"
                                 and item.get("bounds_error") is None for item in (managed, original)),
                             "Original range bounds/source coordinate conversion is unknown, failed or differs")
                        boxes = [{"x": b[0] - origin["x"], "y": b[1] - origin["y"], "width": b[2], "height": b[3]} for b in actual]
                        selection = {"xaml_id": node["id"], "uia_id": provider["id"], "path": path,
                            "source_span_utf16": list(span), "source": SOURCE, "owner_binding": owner_proof,
                            "original_external_range": copy.deepcopy(original), "original_managed_range": copy.deepcopy(managed),
                            "observed_inprocess_range": copy.deepcopy(precise), "selected_client_bounds": boxes,
                            "diagnostics": [ZERO_ERROR.format(index=i) for i in zero]}
                        audit["selections"].append(selection)
                        for target in (managed, effective_native[path]):
                            target["bounds"] = copy.deepcopy(boxes)
                            target["bounds_status"] = "observed-inprocess-positive-area"
                            target["bounds_source"] = SOURCE
                            target["observed_geometry_selection"] = {"index": len(audit["selections"]) - 1, "source": SOURCE}
                        for diagnostic in selection["diagnostics"]:
                            resolved[(provider["id"], diagnostic)] += 1
                    except (EvidenceError, TypeError, KeyError, ValueError) as error:
                        audit["unavailable_ranges"].append({"xaml_id": node["id"], "path": path, "reason": str(error)})
            except (EvidenceError, TypeError, KeyError, ValueError) as error:
                audit["unavailable_ranges"].append({"xaml_id": pair["xaml_id"], "reason": str(error)})
        # Resolve only a complete multiset of these precise original messages.
        # Every unrelated/unknown/provider exception remains an active error.
        top_counts = Counter(uia.get("extraction_errors", []))
        for provider_id, provider in selected_providers.items():
            originals = Counter(provider.get("measurement_errors", []))
            for diagnostic, count in list(originals.items()):
                if count > 0 and resolved[(provider_id, diagnostic)] == count and top_counts[provider_id + ": " + diagnostic] == count:
                    provider["measurement_errors"] = [value for value in provider["measurement_errors"] if value != diagnostic]
                    effective["extraction_errors"] = [value for value in effective["extraction_errors"] if value != provider_id + ": " + diagnostic]
                    audit["resolved_diagnostics"].append({"uia_id": provider_id, "diagnostic": diagnostic, "occurrences": count,
                        "resolution": "Same actual bound range has positive observed floating-point geometry; original external measurement retained"})
        # The observer computes exit 1 from extraction_errors after separating
        # independently measured offscreen diagnostics. Keep that same scope:
        # a retained offscreen title bar's empty rectangle is not an unresolved
        # visible failure. Require its existing exact per-node UIA receipt;
        # offscreen alone cannot conceal a new/unknown or tree traversal error.
        nonvisible = Counter((item.get("id"), item.get("diagnostic"))
            for item in uia.get("nonvisible_diagnostics", [])
            if isinstance(item, dict) and item.get("source") == "UIA")
        remaining = []
        audit["retained_nonvisible_diagnostics"] = []
        for node in effective.get("raw_nodes", []):
            messages = Counter(node.get("measurement_errors", []))
            if not messages:
                continue
            known = node.get("state", {}).get("offscreen") is True and all(
                nonvisible[(node.get("id"), str(node.get("id")) + ": " + message)] == count
                for message, count in messages.items())
            if known:
                audit["retained_nonvisible_diagnostics"].append({"uia_id": node.get("id"),
                    "measurement_errors": copy.deepcopy(node["measurement_errors"]),
                    "source": "Existing observer IsOffscreen and exact nonvisible_diagnostics receipts; not resolved or deleted"})
            else:
                remaining.append(node.get("id"))
        result["all_original_failures_resolved"] = (bool(audit["original_extraction_errors"])
            and not effective.get("extraction_errors") and not remaining)
    except (EvidenceError, TypeError, KeyError, ValueError) as error:
        audit["unavailable_ranges"].append({"reason": str(error)})
    effective["observed_text_geometry_selection"] = audit
    return result


def load_observed_text_geometry(xaml_path, uia_path, xaml=None, uia=None):
    xaml_path, uia_path = Path(xaml_path), Path(uia_path)
    xaml = xaml if xaml is not None else json.loads(xaml_path.read_text(encoding="utf-8-sig"))
    uia = uia if uia is not None else json.loads(uia_path.read_text(encoding="utf-8-sig"))
    stem = xaml_path.name.removesuffix(".xaml.json")
    probe_file = xaml_path.with_name(stem + ".inprocess-text-range-provider-probe.json")
    frame_file = xaml_path.with_name(stem + ".text-range-frame-final.json")
    if not probe_file.exists() or not frame_file.exists():
        return {"effective_uia": uia, "audit": {"source": SOURCE, "status": "actual-supplementary-files-unavailable", "selections": []},
                "all_original_failures_resolved": False}
    try:
        selected = select_observed_text_geometry(xaml, uia,
            json.loads(probe_file.read_text(encoding="utf-8-sig")), json.loads(frame_file.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, TypeError, KeyError) as error:
        return {"effective_uia": uia, "audit": {"source": SOURCE, "status": "unavailable", "error": str(error), "selections": []},
                "all_original_failures_resolved": False}
    selected["audit"]["source_files"] = {"external_uia": uia_path.name, "xaml": xaml_path.name,
        "inprocess_com": probe_file.name, "frame": frame_file.name}
    return selected
