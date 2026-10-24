"""Three-valued scope predicates and deterministic dependency admission."""

from enum import Enum

from ..store import OrgError
from .models import (SCALAR_FIELDS, SET_FIELDS, SCOPE_KEY, json_copy, nonempty,
                     patch_ref, validate_predicate, validate_scope_ref)
from .registry import get_patch_in, get_scope_in


class Truth(Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"

    def __bool__(self):
        raise TypeError("Compare Truth values explicitly; UNKNOWN is not permission.")


def _evaluate(predicate, context):
    if "const" in predicate:
        return Truth.TRUE if predicate["const"] else Truth.FALSE
    if "not" in predicate:
        value = _evaluate(predicate["not"], context)
        return {Truth.TRUE: Truth.FALSE, Truth.FALSE: Truth.TRUE, Truth.UNKNOWN: Truth.UNKNOWN}[value]
    if "all" in predicate or "any" in predicate:
        conjunction = "all" in predicate
        values = [_evaluate(p, context) for p in predicate["all" if conjunction else "any"]]
        decisive = Truth.FALSE if conjunction else Truth.TRUE
        if decisive in values:
            return decisive
        if Truth.UNKNOWN in values:
            return Truth.UNKNOWN
        return Truth.TRUE if conjunction else Truth.FALSE
    field = predicate["field"]
    actual = context.get(field)
    if field in SET_FIELDS:
        if not isinstance(actual, list) or any(not isinstance(v, str) or not v for v in actual):
            return Truth.UNKNOWN
        matched = (set(actual) == set(predicate["value"]) if predicate["op"] == "eq"
                   else bool(set(actual) & set(predicate["value"])))
    else:
        if not isinstance(actual, str) or not actual:
            return Truth.UNKNOWN
        matched = actual == predicate["value"] if predicate["op"] == "eq" else actual in predicate["value"]
    return Truth.TRUE if matched else Truth.FALSE


def evaluate(predicate, context):
    validate_predicate(predicate)
    if not isinstance(context, dict):
        raise OrgError("Scope context must be a trusted mapping.")
    return _evaluate(predicate, context)


def matches_scope(scope_record, context):
    if not isinstance(scope_record, dict) or "include" not in scope_record or "exclude" not in scope_record:
        raise OrgError("Scope requires explicit include and exclude predicates.")
    included = evaluate(scope_record["include"], context)
    excluded = evaluate(scope_record["exclude"], context)
    if included == Truth.FALSE or excluded == Truth.TRUE:
        return Truth.FALSE
    if included == Truth.TRUE and excluded == Truth.FALSE:
        return Truth.TRUE
    return Truth.UNKNOWN


PROTECTED_FIELDS = frozenset({"member_id", "org_id", "role", "team_ids", "model", "carrier_id",
                              "capabilities", "runtime_version"})


def trusted_context(org, actor, *, attributes=None):
    if actor not in org.get("members", {}):
        raise OrgError("Context requires the actual organization member.")
    attributes = {} if attributes is None else attributes
    if not isinstance(attributes, dict) or set(attributes) - (SCALAR_FIELDS | SET_FIELDS):
        raise OrgError("Unknown context attributes.")
    if set(attributes) & PROTECTED_FIELDS:
        raise OrgError("Caller attributes cannot override authoritative context.")
    member = org["members"][actor]
    metadata = member.get("scope_context", {})
    if not isinstance(metadata, dict) or set(metadata) - ((SCALAR_FIELDS | SET_FIELDS) - {"member_id", "org_id"}):
        raise OrgError("Invalid governed member scope context.")
    context = json_copy(metadata)
    if member.get("workspace") and "repository" not in context:
        context["repository"] = member["workspace"]
    context.update(json_copy(attributes))
    context.update(member_id=actor, org_id=org["id"])
    for field, value in context.items():
        if field in SET_FIELDS:
            if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value):
                raise OrgError("Set context values must be string lists.")
        elif not isinstance(value, str) or not value:
            raise OrgError("Scalar context values must be nonempty strings.")
    return context


def _key(ref):
    return (ref["patch_id"], ref["revision"])


def resolve(org, context, deployments=None):
    if not isinstance(context, dict):
        raise OrgError("Scope context must be a trusted mapping.")
    if deployments is None:
        deployments = org.get(SCOPE_KEY, {}).get("deployments", {})
    if isinstance(deployments, dict):
        deployments = list(deployments.values())
    if not isinstance(deployments, list):
        raise OrgError("Deployments must be a mapping or list.")
    candidates, rejected = {}, []

    def reject(deployment, reason):
        rejected.append({"deployment_id": deployment.get("deployment_id"),
                         "patch_ref": json_copy(deployment.get("patch_ref")), "reason": reason})

    ordered = sorted(deployments, key=lambda d: str(d.get("deployment_id", "")) if isinstance(d, dict) else "")
    for deployment in ordered:
        if not isinstance(deployment, dict):
            raise OrgError("Each deployment must be an object.")
        if deployment.get("status") != "active":
            continue
        try:
            nonempty(deployment.get("deployment_id"), "deployment_id")
            patch = get_patch_in(org, deployment.get("patch_ref"))
            scope = get_scope_in(org, validate_scope_ref(deployment.get("scope_ref")))
            applicability = matches_scope(scope, context)
            if applicability != Truth.TRUE:
                reject(deployment, "scope_" + applicability.value)
                continue
            key = _key(patch_ref(patch))
            if key in candidates:
                reject(deployment, "duplicate_patch")
                continue
            candidates[key] = {**json_copy(deployment), "patch": patch, "scope": scope}
        except OrgError as error:
            reject(deployment, "invalid_candidate: " + str(error))

    removed = {}
    keys = sorted(candidates)
    for i, left in enumerate(keys):
        left_conflicts = {_key(ref) for ref in candidates[left]["patch"]["conflicts"]}
        for right in keys[i + 1:]:
            right_conflicts = {_key(ref) for ref in candidates[right]["patch"]["conflicts"]}
            if left[0] == right[0] or right in left_conflicts or left in right_conflicts:
                removed[left] = removed[right] = "conflict"

    def suppress_missing():
        changed = True
        while changed:
            changed = False
            for key in keys:
                if key in removed:
                    continue
                deps = [_key(ref) for ref in candidates[key]["patch"]["dependencies"]]
                if any(dep not in candidates or dep in removed for dep in deps):
                    removed[key] = "dependency_unavailable"
                    changed = True

    suppress_missing()
    active = set(candidates) - set(removed)
    dependencies = {key: {_key(ref) for ref in candidates[key]["patch"]["dependencies"]} for key in active}
    ordered_keys = []
    while dependencies:
        ready = sorted(key for key, deps in dependencies.items() if not deps)
        if not ready:
            for key in dependencies:
                removed[key] = "dependency_cycle_or_blocked"
            break
        ordered_keys.extend(ready)
        for key in ready:
            del dependencies[key]
        for deps in dependencies.values():
            deps.difference_update(ready)
    for key, reason in sorted(removed.items()):
        reject(candidates[key], reason)
    selected = [candidates[key] for key in ordered_keys if key not in removed]
    rejected.sort(key=lambda r: (str(r["deployment_id"]), r["reason"]))
    return {"selected": selected, "rejected": rejected, "snapshot_revision": org.get("revision")}
