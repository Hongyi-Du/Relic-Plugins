"""Organization-owned immutable revision persistence and replay."""

import json

from ..store import OrgError, now
from .models import (SCOPE_KEY, ensure_state, json_copy, nonempty, same_json, validate_patch,
                     validate_scope, validate_patch_ref, validate_scope_ref)


def _read(org, ref, entity):
    checked = validate_patch_ref(ref) if entity == "patch" else validate_scope_ref(ref)
    state = org.get(SCOPE_KEY, {})
    try:
        return json_copy(state[entity + "es" if entity == "patch" else "scopes"][checked[entity + "_id"]][str(checked["revision"])])
    except (KeyError, TypeError):
        raise OrgError("Unknown exact " + entity + " revision.") from None


def get_patch_in(org, ref):
    return _read(org, ref, "patch")


def get_scope_in(org, ref):
    return _read(org, ref, "scope")


def _authorize(org, actor):
    if actor not in org.get("members", {}):
        raise OrgError("Registry writes require the actual organization member.")
    if org.get("status") != "active":
        raise OrgError("Organization is paused.")


def _request_key(actor, request_id):
    nonempty(request_id, "request_id")
    return json.dumps([actor, request_id], ensure_ascii=False, separators=(",", ":"))


def _register(org, actor, spec, expected_revision, request_id, entity):
    _authorize(org, actor)
    if type(expected_revision) is not int or expected_revision < 0:
        raise OrgError("expected_revision must be a nonnegative integer.")
    normalized = validate_patch(spec, actor) if entity == "patch" else validate_scope(spec)
    key = _request_key(actor, request_id)
    request = {"entity": entity, "spec": normalized, "expected_revision": expected_revision}
    state = ensure_state(org)
    prior = state["requests"].get(key)
    if prior is not None:
        if not same_json(prior["request"], request):
            raise OrgError("request_id already identifies different registry arguments.")
        return {"record": json_copy(prior["record"]), "replayed": True, "event": json_copy(prior["event"])}
    identity = normalized[entity + "_id"]
    heads = state[entity + "_heads"]
    if heads.get(identity, 0) != expected_revision:
        raise OrgError("Registry revision conflict; read the current head.")
    record = dict(normalized, revision=expected_revision + 1, created_at=now())
    if entity == "scope":
        record["proposer"] = actor
    else:
        for ref in record["dependencies"] + record["conflicts"]:
            get_patch_in(org, ref)
        if record["rollback_ref"] is not None:
            get_patch_in(org, record["rollback_ref"])
        deps = {(r["patch_id"], r["revision"]) for r in record["dependencies"]}
        conflicts = {(r["patch_id"], r["revision"]) for r in record["conflicts"]}
        if deps & conflicts:
            raise OrgError("A required dependency cannot also be an explicit conflict.")
    event = {"sequence": len(state["history"]) + 1, "entity": entity, "actor": actor,
             "request_id": request_id, "request": request, "record": record}
    collection = "patches" if entity == "patch" else "scopes"
    state[collection].setdefault(identity, {})[str(record["revision"])] = json_copy(record)
    heads[identity] = record["revision"]
    state["history"].append(json_copy(event))
    state["requests"][key] = {"request": json_copy(request), "record": json_copy(record), "event": json_copy(event)}
    return {"record": json_copy(record), "replayed": False, "event": json_copy(event)}


def register_patch_in(org, actor, spec, *, expected_revision, request_id):
    return _register(org, actor, spec, expected_revision, request_id, "patch")


def register_scope_in(org, actor, spec, *, expected_revision, request_id):
    return _register(org, actor, spec, expected_revision, request_id, "scope")


def replay_registry(history):
    if not isinstance(history, list):
        raise OrgError("Replay requires a registry event list.")
    org = {"members": {}, "status": "active"}
    state = ensure_state(org)
    for index, supplied in enumerate(history, 1):
        event = json_copy(supplied)
        if not isinstance(event, dict) or set(event) != {"sequence", "entity", "actor", "request_id", "request", "record"}:
            raise OrgError("Invalid registry replay event.")
        entity, actor = event["entity"], event["actor"]
        if event["sequence"] != index or entity not in ("patch", "scope"):
            raise OrgError("Replay event sequence or entity is invalid.")
        request, record = event["request"], event["record"]
        if not isinstance(request, dict) or set(request) != {"entity", "spec", "expected_revision"} or request["entity"] != entity:
            raise OrgError("Invalid replay request.")
        nonempty(actor, "Replay actor")
        expected = request["expected_revision"]
        if type(expected) is not int or expected < 0 or not isinstance(record, dict):
            raise OrgError("Invalid replay revision.")
        if not isinstance(request["spec"], dict):
            raise OrgError("Invalid replay specification.")
        payload = {k: v for k, v in request["spec"].items() if k != "proposer"}
        normalized = validate_patch(payload, actor) if entity == "patch" else validate_scope(payload)
        expected_spec = normalized if entity == "patch" else dict(normalized)
        if not same_json(expected_spec, request["spec"]):
            raise OrgError("Replay request normalization mismatch.")
        identity = normalized[entity + "_id"]
        if state[entity + "_heads"].get(identity, 0) != expected:
            raise OrgError("Replay revision conflict.")
        if set(record) != set(normalized) | {"revision", "created_at", "proposer"}:
            raise OrgError("Replay record fields differ from the request.")
        nonempty(record.get("created_at"), "Replay timestamp")
        if not same_json(record, dict(normalized, revision=expected + 1, created_at=record["created_at"], proposer=actor)):
            raise OrgError("Replay record differs from the immutable request.")
        key = _request_key(actor, event["request_id"])
        if key in state["requests"]:
            raise OrgError("Duplicate replay request.")
        if entity == "patch":
            for ref in record["dependencies"] + record["conflicts"] + ([record["rollback_ref"]] if record["rollback_ref"] else []):
                get_patch_in(org, ref)
        collection = "patches" if entity == "patch" else "scopes"
        state[collection].setdefault(identity, {})[str(expected + 1)] = json_copy(record)
        state[entity + "_heads"][identity] = expected + 1
        state["history"].append(json_copy(event))
        state["requests"][key] = {"request": json_copy(request), "record": json_copy(record), "event": json_copy(event)}
    return json_copy(state)


class _Replay(Exception):
    def __init__(self, record):
        self.record = record


class PatchRegistry:
    def __init__(self, store):
        self.store = store

    def _write(self, org_id, actor, spec, expected_revision, request_id, entity):
        detail = {}
        try:
            with self.store.transaction(org_id, actor, "scope." + entity + "_registered", detail) as (org, _db):
                result = _register(org, actor, spec, expected_revision, request_id, entity)
                if result["replayed"]:
                    raise _Replay(result["record"])
                detail["scope_event"] = result["event"]
            return result["record"]
        except _Replay as replay:
            return replay.record

    def register_patch(self, org_id, actor, spec, *, expected_revision, request_id):
        return self._write(org_id, actor, spec, expected_revision, request_id, "patch")

    def register_scope(self, org_id, actor, spec, *, expected_revision, request_id):
        return self._write(org_id, actor, spec, expected_revision, request_id, "scope")

    def get_patch(self, org_id, actor, ref):
        return get_patch_in(self.store.get(org_id, actor), ref)

    def get_scope(self, org_id, actor, ref):
        return get_scope_in(self.store.get(org_id, actor), ref)

    def snapshot(self, org_id, actor):
        org = self.store.get(org_id, actor)
        return json_copy(ensure_state(org))
