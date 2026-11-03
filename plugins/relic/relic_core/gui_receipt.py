"""Public GUI response receipts, also compatible with pre-runner Claude hooks.

No transcript, memory, model invocation or history access. Only an outstanding
explicit request and its matching public Desktop Stop can produce a receipt.
"""
import json
import hashlib
import os
import time
import uuid
from pathlib import Path
from .store import data_home, is_relic_tool


def _retry(action):
    for attempt in range(40):
        try:
            return action()
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.05)


def _read(path):
    try:
        value = json.loads(_retry(lambda: path.read_text(encoding="utf-8")))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path, value):
    tmp = path.with_suffix(".%s.tmp" % uuid.uuid4().hex)
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    _retry(lambda: tmp.replace(path))


def runs_dir():
    return data_home() / "runs"


OBSERVATION_AGE = 24 * 3600


def _carrier_digest(carrier):
    return hashlib.sha256(carrier.encode("utf-8")).hexdigest()


def observation_path(carrier):
    return runs_dir() / ("claude-desktop-observed-" + _carrier_digest(carrier) + ".json")


def observed_carrier(carrier, at=None):
    proof = _read(observation_path(carrier))
    at = time.time() if at is None else at
    return proof.get("carrier_digest") == _carrier_digest(carrier) and _recent_observation(proof, at)


def _recent_observation(proof, at):
    timestamp = proof.get("at")
    return (proof.get("public_stop") is True and isinstance(timestamp, (int, float)) and
            at - OBSERVATION_AGE <= timestamp <= at + 300)


def observed_count(at=None):
    at = time.time() if at is None else at
    count = 0
    for path in runs_dir().glob("claude-desktop-observed-*.json"):
        proof = _read(path)
        if _recent_observation(proof, at):
            count += 1
    return count


def observe_desktop_stop(event, output, store, actor):
    """Record transport evidence from an existing configured GUI seat, never the reply's contents.

    A manual turn that reaches this public hook validates the receiver before automatic delivery is enabled.
    This record neither enables delivery nor replaces the per-request nonce receipt.
    """
    if (os.getenv("CLAUDE_CODE_ENTRYPOINT") != "claude-desktop" or event.get("hook_event_name") != "Stop" or
            event.get("agent_id") or event.get("session_id") != actor or output.get("decision") == "block" or
            (output.get("hookSpecificOutput") or {}).get("additionalContext") or
            not isinstance(event.get("last_assistant_message"), str) or not event["last_assistant_message"].strip()):
        return
    for org, member, _ in store.seats_of(actor):
        seat = org["members"][member]
        config = store.seat_config(org["id"], member, org)
        if seat.get("harness") == "claude-code" and config.get("harness") == "claude-code" and config.get("surface") == "gui":
            runs_dir().mkdir(parents=True, exist_ok=True)
            _write(observation_path(actor), {"carrier_digest": _carrier_digest(actor), "public_stop": True, "at": time.time()})
            return


def request_path(org_id, member):
    return runs_dir() / ("%s-%s.claude-gui.json" % (org_id, member))


def marker(request):
    return "[Relic GUI nonce:%s]" % request["nonce"]


def payload(request):
    return (marker(request) + "\n" + request["prompt"] + "\n\n" +
            "Relic transport receipt: include %s verbatim in your public final reply "
            "or in a Relic message reply for this request." % marker(request))


def receipt_matches(receipt, request):
    return (all(receipt.get(k) == request.get(k) for k in ("org_id", "member", "carrier", "nonce")) and
            receipt.get("session_id") == request["carrier"] and receipt.get("event") == "Stop" and
            receipt.get("entrypoint") == "claude-desktop" and receipt.get("matched_by") in ("prompt", "relic", "public") and
            isinstance(receipt.get("last_assistant_message"), str) and bool(receipt["last_assistant_message"].strip()) and
            receipt.get("at", 0) >= request["created"])


KEEP = 7 * 24 * 3600  # how long an unanswered request can still be answered by a late Stop that quotes its nonce
# The text of a refused start while a Desktop session still owes an earlier request its Stop: wake.py waits quietly,
# as for a busy chat (no failure, no receipt).
WAITING = "has an unanswered Relic request in the Claude desktop app"


def unresolved(store, carrier, now=None):
    """Requests sent, or possibly sent, to this Desktop session that no GUI Stop has answered yet, newest first.

    One session can hold seats in several organizations, and every one of them reaches it at one address, so it can
    owe more than one. They are found from each seat's request file and from the request folders: a newer request of
    the same seat replaces the seat's file, but a late Stop can still answer the older one.
    """
    now = time.time() if now is None else now
    found = {}

    def consider(request, folder):
        nonce = request.get("nonce")
        if (not isinstance(nonce, str) or nonce in found or request.get("carrier") != carrier or
                folder.name != "claude-gui-" + nonce or not folder.is_dir() or (folder / "receipt.json").exists() or
                not isinstance(request.get("created"), (int, float)) or request["created"] < now - KEEP):
            return
        found[nonce] = (request, folder)

    for org, member, _ in store.seats_of(carrier):
        request = _read(request_path(org["id"], member))
        if request.get("org_id") == org["id"] and request.get("member") == member:
            consider(request, runs_dir() / ("claude-gui-" + str(request.get("nonce"))))
    for folder in runs_dir().glob("claude-gui-*"):
        try:
            if folder.stat().st_mtime < now - KEEP:
                continue
        except OSError:
            continue
        consider(_read(folder / "request.json"), folder)
    return sorted(found.values(), key=lambda item: item[0]["created"], reverse=True)


def capture(event, output, store, actor):
    """Opt-in by an outstanding request; never parse transcripts or capture another turn's history.

    Every event is matched by nonce: a router prompt binds the request it carries and no other, a Relic message or a
    public final reply that quotes a nonce binds that request, and a human prompt invalidates every earlier binding.
    A late Stop for an older request answers that request, never a newer one: a quoted nonce outranks the router
    prompt of a request whose nonce the reply leaves out.
    """
    observe_desktop_stop(event, output, store, actor)
    if event.get("agent_id") or event.get("session_id") != actor:
        return
    for org, member, _ in store.seats_of(actor):  # only a session holding a GUI-configured seat takes receipts
        seat = org["members"][member]
        config = store.seat_config(org["id"], member, org)
        if (seat.get("carrier") == actor and seat.get("harness") == "claude-code" and
                config.get("harness") == "claude-code" and config.get("surface") == "gui"):
            break
    else:
        return
    requests = unresolved(store, actor)
    if not requests:
        return
    name = event.get("hook_event_name")
    _write(requests[0][1] / "hook-observed.json", {"event": name, "session_id": event.get("session_id"),
        "entrypoint": os.getenv("CLAUDE_CODE_ENTRYPOINT"), "at": time.time(),
        "public_stop_field": isinstance(event.get("last_assistant_message"), str)})
    if os.getenv("CLAUDE_CODE_ENTRYPOINT") != "claude-desktop":
        return
    if name == "UserPromptSubmit":
        prompt_text = event.get("prompt")
        carried = next((r["nonce"] for r, _ in requests
                        if isinstance(prompt_text, str) and prompt_text.count(payload(r)) == 1), None)
        for request, folder in requests:
            if request["nonce"] == carried:
                binding = {"matched_by": "prompt"}
            elif carried:
                # Another request's router prompt: this turn answers that one; this request keeps only its nonce.
                binding = {"matched_by": None}
            else:
                # Any later human prompt invalidates a previously observed prompt/tool binding.
                binding = {"matched_by": None, "human_prompt": True}
            _write(folder / "binding.json", binding)
    elif name == "PostToolUse" and is_relic_tool(event.get("tool_name", "")):
        data = event.get("tool_input") or {}
        if event["tool_name"].endswith("__message") and isinstance(data, dict):
            for request, folder in requests:
                if marker(request) in str(data.get("body", "")):
                    _write(folder / "binding.json", {"matched_by": "relic"})
    elif name == "Stop" and output.get("decision") != "block" and not (output.get("hookSpecificOutput") or {}).get("additionalContext"):
        text = event.get("last_assistant_message")
        if not isinstance(text, str) or not text.strip():
            return
        quoted = {request["nonce"] for request, _ in requests if marker(request) in text}
        for request, folder in requests:
            binding_path = folder / "binding.json"
            observed = _read(binding_path)
            binding = observed.get("matched_by")
            if marker(request) in text and not observed.get("human_prompt"):
                binding = "public"
            elif binding == "prompt" and quoted - {request["nonce"]}:
                # The reply quotes another request's nonce and not this one's: it is that request's (late) reply, and
                # this request's router prompt does not claim it too. This request is still owed its Stop; its binding
                # stays, and a Relic message that quotes its nonce (binding "relic") is evidence of its own.
                continue
            if binding not in ("prompt", "relic", "public"):
                continue
            receipt = {k: request[k] for k in ("org_id", "member", "carrier", "nonce")}
            receipt.update(session_id=event["session_id"], event="Stop", entrypoint="claude-desktop",
                           matched_by=binding, last_assistant_message=text, at=time.time())
            _write(folder / "receipt.json", receipt)
            binding_path.unlink(missing_ok=True)
