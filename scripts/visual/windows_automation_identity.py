"""Join independently read complete UIA RuntimeIds, never text or geometry.

This receipt is supplementary audit evidence. It does not suppress provider
errors or make a source tree/paint measurement complete.
"""
from collections import defaultdict
import re


OWNER_SOURCE = "Actual FrameworkElementAutomationPeer.FromElement owner binding"
NATIVE_SOURCE = "Actual AutomationPeer QI to native UIA fragment and UIA core node"
TRANSPORT_SOURCE = "Actual COM inter-apartment marshal stream and MTA UIA core read"
COLLECTION_PHASE = "while-independent-uia-observer-held"


def held_observer_binding(evidence, uia):
    """Validate the actual hold receipt, not its capture/test success.

    An observer may finish with exit code 1 because other text/paint evidence
    failed, while still retaining the real objects used for this identity read.
    Those original errors remain owned by the independent capture and gate.
    """
    if evidence.get("collection_phase") != COLLECTION_PHASE:
        return "Actual peer identity was not collected while the independent UIA observer was held"
    observer, hold = evidence.get("observer"), uia.get("observer_hold")
    if not isinstance(observer, dict) or not isinstance(hold, dict):
        return "Actual independent UIA observer identity or hold receipt is missing"
    case_id, app_pid = uia.get("case_id"), uia.get("pid")
    if (not isinstance(case_id, str) or not case_id
            or type(app_pid) is not int or app_pid <= 0
            or observer.get("case_id") != case_id or hold.get("case_id") != case_id
            or type(observer.get("app_pid")) is not int or observer["app_pid"] != app_pid
            or type(hold.get("app_pid")) is not int or hold["app_pid"] != app_pid
            or type(observer.get("observer_pid")) is not int or observer["observer_pid"] <= 0
            or type(hold.get("observer_pid")) is not int
            or hold["observer_pid"] != observer["observer_pid"]):
        return "Actual observer case/app/observer process binding is missing or foreign"
    if hold.get("status") != "released":
        return "Independent UIA observer did not complete the held-object release handshake"
    release = hold.get("release")
    if (hold.get("errors") != [] or not isinstance(release, dict)
            or release.get("action") != "release" or release.get("status") != "observed"
            or release.get("case_id") != case_id
            or type(release.get("observer_pid")) is not int
            or release["observer_pid"] != observer["observer_pid"]):
        return "Observer release was failed cleanup, foreign, malformed or accompanied by hold errors"
    retained = hold.get("retained_owners")
    required = ("capture_instance_retained", "retention_requested", "primary_root_retained",
                "native_text_evidence_retained")
    if (not isinstance(retained, dict) or any(retained.get(key) is not True for key in required)
            or type(retained.get("retained_element_reference_count")) is not int
            or retained["retained_element_reference_count"] <= 0):
        return "Actual independent UIA owners/native text objects were not proven retained"
    return None


def measured_id(array):
    if not isinstance(array, dict) or array.get("status") != "measured":
        return None
    if any(type(array.get(key)) is not int or array[key] != value
           for key, value in (("dimensions", 1), ("vartype", 3), ("element_size", 4))):
        return None
    values, bounds = array.get("values"), array.get("dimension_bounds")
    if (not isinstance(values, list) or not values
            or any(type(value) is not int or not -(2 ** 31) <= value < 2 ** 31 for value in values)
            or type(array.get("element_count")) is not int or array["element_count"] != len(values)
            or not isinstance(bounds, list) or len(bounds) != 1 or not isinstance(bounds[0], dict)):
        return None
    bound = bounds[0]
    if (type(bound.get("dimension")) is not int or bound["dimension"] != 1
            or type(bound.get("lower")) is not int or type(bound.get("upper")) is not int
            or bound["upper"] - bound["lower"] + 1 != len(values)):
        return None
    return tuple(values)


def provider_id(node):
    # Program.cs records string.Join(".", element.GetRuntimeId()). Decode the
    # entire signed Int32 sequence, without interpreting any prefix or suffix.
    value = node.get("runtime_id")
    if not isinstance(value, str) or not re.fullmatch(r"-?\d+(?:\.-?\d+)*", value):
        return None
    values = tuple(int(part) for part in value.split("."))
    return values if all(-(2 ** 31) <= part < 2 ** 31 for part in values) else None


def bind_automation_identities(raw_nodes, uia):
    providers, owners = defaultdict(list), defaultdict(list)
    result = {"source": "Exact full RuntimeId equality between actual XAML peer/UIA core and independent UIA walk",
              "pairs": [], "unresolved": [], "observed_owner_receipts": 0,
              "does_not_resolve": "Paint, text-range visibility, frame continuity and provider failures remain independent"}
    for node in uia.get("raw_nodes", []):
        identity = provider_id(node)
        if identity is not None:
            providers[identity].append(node)
    for node in raw_nodes:
        evidence = node.get("automation_identity_evidence")
        if evidence is None:
            continue
        result["observed_owner_receipts"] += 1
        def unknown(reason):
            result["unresolved"].append({"xaml_id": node.get("id"), "reason": reason})
        if not isinstance(evidence, dict):
            unknown("Malformed actual peer receipt")
            continue
        if (evidence.get("source") != OWNER_SOURCE or evidence.get("status") != "measured"
                or evidence.get("owner_id") != node.get("id") or evidence.get("peer_owner_id") != node.get("id")
                or evidence.get("same_owner_object") is not True or evidence.get("peer_same_object_after") is not True
                or evidence.get("events_source_same_object_after") is not True
                or evidence.get("metadata_modified") is not False or evidence.get("peer_is_null") is not False
                or type(evidence.get("process_id")) is not int or type(uia.get("pid")) is not int
                or evidence["process_id"] != uia["pid"]):
            unknown("Actual peer owner, current identity or process binding is not measured")
            continue
        hold_error = held_observer_binding(evidence, uia)
        if hold_error is not None:
            unknown(hold_error)
            continue
        events_null, events_same, events_type = (evidence.get("events_source_is_null"),
            evidence.get("events_source_same_peer"), evidence.get("events_source_type"))
        absent_source = (events_null is True and events_same is False
                         and "events_source_type" in evidence and events_type is None)
        same_source = events_null is False and events_same is True and isinstance(events_type, str) and bool(events_type)
        if not (absent_source or same_source):
            unknown("Automation EventsSource redirects to another unbound peer")
            continue
        transport = evidence.get("apartment_transport")
        if (not isinstance(transport, dict) or transport.get("source") != TRANSPORT_SOURCE
                or transport.get("status") != "measured" or transport.get("failures") != []
                or transport.get("returned_to_origin_thread") is not True
                or transport.get("worker_read_completed") is not True
                or transport.get("stream_consumed_by_unmarshal") is not True
                or transport.get("stream_consumption_unknown") is not False):
            unknown("COM apartment transfer, actual read or release is incomplete")
            continue
        native = evidence.get("native")
        if (not isinstance(native, dict) or native.get("source") != NATIVE_SOURCE
                or native.get("status") != "measured" or native.get("failures") != []
                or native.get("core_runtime_id_stable") is not True):
            unknown("Native UIA core identity read is incomplete or failed")
            continue
        identity = measured_id(native.get("core_runtime_id"))
        if identity is None or identity != measured_id(native.get("core_runtime_id_recheck")):
            unknown("Complete native RuntimeId arrays are malformed or changed")
            continue
        # fragment_runtime_id is deliberately not read here. In particular,
        # UiaAppendRuntimeId never licenses construction of a complete identity.
        owners[identity].append(node)
    for identity, nodes in owners.items():
        observed = providers.get(identity, [])
        if len(nodes) != 1 or len(observed) != 1:
            for node in nodes:
                result["unresolved"].append({"xaml_id": node.get("id"), "runtime_id": list(identity),
                    "reason": "Complete RuntimeId must have exactly one owner and one independent provider",
                    "xaml_candidates": [candidate.get("id") for candidate in nodes],
                    "uia_candidates": [candidate.get("id") for candidate in observed]})
            continue
        evidence = nodes[0]["automation_identity_evidence"]
        result["pairs"].append({"xaml_id": nodes[0]["id"], "uia_id": observed[0]["id"], "runtime_id": list(identity),
                               "method": "Full opaque RuntimeId equality; no name, bounds or suffix inference",
                               "collection_phase": evidence["collection_phase"],
                               "observer": {key: evidence["observer"][key]
                                            for key in ("case_id", "app_pid", "observer_pid")}})
    return result
