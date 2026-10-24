"""JSON validation for immutable patch and scope revisions."""

import json
import math

from ..store import OrgError

SCOPE_KEY = "scope_evolution"
SCALAR_FIELDS = frozenset({"member_id", "role", "task_id", "task_family", "workflow", "tool",
                           "repository", "environment_version", "model", "runtime_version",
                           "carrier_id", "batch_id", "org_id", "time"})
SET_FIELDS = frozenset({"team_ids", "capabilities"})


def json_copy(value):
    def check(item, depth=0):
        if depth > 64:
            raise OrgError("JSON nesting exceeds the supported depth.")
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for child in item:
                check(child, depth + 1)
            return
        if type(item) is dict and all(type(k) is str for k in item):
            for child in item.values():
                check(child, depth + 1)
            return
        raise OrgError("Only finite JSON values with string object keys are supported.")
    check(value)
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def same_json(left, right):
    return (json.dumps(left, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            == json.dumps(right, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")))


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise OrgError(label + " must be a nonempty string.")
    return value


def strings(value, label):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise OrgError(label + " must be a list of nonempty strings.")
    if len(set(value)) != len(value):
        raise OrgError(label + " contains duplicates.")
    return list(value)


def ensure_state(org):
    state = org.setdefault(SCOPE_KEY, {})
    if (not isinstance(state, dict) or type(state.get("schema_version", 1)) is not int
            or state.get("schema_version", 1) != 1):
        raise OrgError("Unsupported SCOPE state schema.")
    state.setdefault("schema_version", 1)
    for name in ("patches", "patch_heads", "scopes", "scope_heads", "requests"):
        value = state.setdefault(name, {})
        if not isinstance(value, dict):
            raise OrgError("Invalid SCOPE registry field: " + name)
    if not isinstance(state.setdefault("history", []), list):
        raise OrgError("Invalid SCOPE registry history.")
    return state


def _ref(ref, field):
    if not isinstance(ref, dict) or set(ref) != {field, "revision"}:
        raise OrgError("An exact " + field + " and revision reference is required.")
    nonempty(ref[field], field)
    if type(ref["revision"]) is not int or ref["revision"] < 1:
        raise OrgError("Reference revision must be a positive integer.")
    return dict(ref)


def validate_patch_ref(ref):
    return _ref(ref, "patch_id")


def validate_scope_ref(ref):
    return _ref(ref, "scope_id")


def patch_ref(record):
    return validate_patch_ref({"patch_id": record["patch_id"], "revision": record["revision"]})


def scope_ref(record):
    return validate_scope_ref({"scope_id": record["scope_id"], "revision": record["revision"]})


def validate_predicate(predicate, depth=0):
    if depth > 32 or not isinstance(predicate, dict):
        raise OrgError("Predicate must be an object with supported nesting depth.")
    keys = set(predicate)
    if keys == {"const"}:
        if type(predicate["const"]) is not bool:
            raise OrgError("Predicate const must be boolean.")
    elif keys in ({"all"}, {"any"}):
        children = predicate[next(iter(keys))]
        if not isinstance(children, list) or not children:
            raise OrgError("Predicate all/any requires a nonempty list.")
        for child in children:
            validate_predicate(child, depth + 1)
    elif keys == {"not"}:
        validate_predicate(predicate["not"], depth + 1)
    elif keys == {"field", "op", "value"}:
        field, op, value = predicate["field"], predicate["op"], predicate["value"]
        if not isinstance(field, str) or field not in SCALAR_FIELDS | SET_FIELDS:
            raise OrgError("Unknown predicate field.")
        if field in SET_FIELDS:
            if op not in ("eq", "overlaps"):
                raise OrgError("Set fields support eq or overlaps with a string list.")
            choices = strings(value, "Predicate set")
            if op == "overlaps" and not choices:
                raise OrgError("Set overlaps requires a nonempty string list.")
        elif op == "eq":
            nonempty(value, "Predicate scalar")
        elif op == "in":
            if not strings(value, "Predicate choices"):
                raise OrgError("Predicate in requires choices.")
        else:
            raise OrgError("Scalar fields support eq or in.")
    else:
        raise OrgError("Unknown or ambiguous predicate structure.")
    return json_copy(predicate)


def _base(value):
    if value is not None and (type(value) not in (str, int) or value == "" or (type(value) is int and value < 0)):
        raise OrgError("base_version must be null, a version string or a nonnegative integer.")
    return value


def validate_patch(spec, actor):
    if not isinstance(spec, dict):
        raise OrgError("Patch specification must be an object.")
    allowed = {"patch_id", "kind", "payload", "base_version", "payload_ref", "rollback_ref",
               "dependencies", "conflicts", "evidence_refs", "affected_objects", "cost", "risk_level"}
    if set(spec) - allowed:
        raise OrgError("Unknown or registry-derived patch field.")
    nonempty(actor, "Proposer")
    result = {"patch_id": nonempty(spec.get("patch_id"), "patch_id"),
              "kind": nonempty(spec.get("kind"), "kind"), "proposer": actor}
    if not isinstance(spec.get("payload"), dict):
        raise OrgError("Patch payload must be an inline JSON object.")
    result["payload"] = json_copy(spec["payload"])
    result["base_version"] = _base(spec.get("base_version"))
    result["payload_ref"] = spec.get("payload_ref")
    if result["payload_ref"] is not None:
        nonempty(result["payload_ref"], "payload_ref")
    rollback = spec.get("rollback_ref")
    result["rollback_ref"] = validate_patch_ref(rollback) if rollback is not None else None
    for name in ("dependencies", "conflicts"):
        refs = spec.get(name, [])
        if not isinstance(refs, list):
            raise OrgError(name + " must be a list of exact references.")
        result[name] = [validate_patch_ref(ref) for ref in refs]
        if len({(ref["patch_id"], ref["revision"]) for ref in result[name]}) != len(refs):
            raise OrgError("Duplicate " + name + " reference.")
    for name in ("evidence_refs", "affected_objects"):
        result[name] = strings(spec.get(name, []), name)
    cost = spec.get("cost", 0)
    if type(cost) not in (int, float) or (type(cost) is float and not math.isfinite(cost)) or cost < 0:
        raise OrgError("Patch cost must be finite and nonnegative.")
    result["cost"] = cost
    risk = spec.get("risk_level", "low")
    if risk not in ("low", "medium", "high"):
        raise OrgError("risk_level must be low, medium or high.")
    result["risk_level"] = risk
    return result


def validate_scope(spec):
    if not isinstance(spec, dict) or set(spec) - {"scope_id", "include", "exclude", "evidence_refs", "base_version"}:
        raise OrgError("Unknown or registry-derived scope field.")
    return {"scope_id": nonempty(spec.get("scope_id"), "scope_id"),
            "include": validate_predicate(spec.get("include")),
            "exclude": validate_predicate(spec.get("exclude")),
            "evidence_refs": strings(spec.get("evidence_refs", []), "evidence_refs"),
            "base_version": _base(spec.get("base_version"))}
