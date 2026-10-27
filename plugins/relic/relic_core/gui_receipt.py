"""Public GUI response receipts, also compatible with pre-runner Claude hooks.

No transcript, memory, model invocation or history access. Only an outstanding
explicit request and its matching public Desktop Stop can produce a receipt.
"""
import json
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
        return json.loads(_retry(lambda: path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def _write(path, value):
    tmp = path.with_suffix(".%s.tmp" % uuid.uuid4().hex)
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    _retry(lambda: tmp.replace(path))


def runs_dir():
    return data_home() / "runs"


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


def capture(event, output, store, actor):
    """Opt-in by a pending request; never parse transcripts or capture another turn's history."""
    if event.get("agent_id"):
        return
    org, member = store.whoami(actor)
    if not org:
        return
    seat = org["members"][member]
    config = seat.get("config") or {}
    if (seat.get("carrier") != actor or event.get("session_id") != actor or
            seat.get("harness") != "claude-code" or config.get("harness") != "claude-code" or config.get("surface") != "gui"):
        return
    request = _read(request_path(org["id"], member))
    if not request or request.get("carrier") != actor or request.get("org_id") != org["id"] or request.get("member") != member:
        return
    folder = runs_dir() / ("claude-gui-" + request["nonce"])
    if not folder.is_dir() or (folder / "receipt.json").exists():
        return
    name = event.get("hook_event_name")
    _write(folder / "hook-observed.json", {"event": name, "session_id": event.get("session_id"),
        "entrypoint": os.getenv("CLAUDE_CODE_ENTRYPOINT"), "at": time.time(),
        "public_stop_field": isinstance(event.get("last_assistant_message"), str)})
    if os.getenv("CLAUDE_CODE_ENTRYPOINT") != "claude-desktop":
        return
    binding_path = folder / "binding.json"
    if name == "UserPromptSubmit":
        # Any later human prompt invalidates a previously observed prompt/tool binding.
        prompt_text = event.get("prompt")
        exact = isinstance(prompt_text, str) and prompt_text.count(payload(request)) == 1
        _write(binding_path, {"matched_by": "prompt" if exact else None, "human_prompt": not exact})
    elif name == "PostToolUse" and is_relic_tool(event.get("tool_name", "")):
        data = event.get("tool_input") or {}
        if event["tool_name"].endswith("__message") and isinstance(data, dict) and marker(request) in str(data.get("body", "")):
            _write(binding_path, {"matched_by": "relic"})
    elif name == "Stop" and output.get("decision") != "block" and not (output.get("hookSpecificOutput") or {}).get("additionalContext"):
        text = event.get("last_assistant_message")
        if not isinstance(text, str) or not text.strip():
            return
        observed = _read(binding_path)
        binding = observed.get("matched_by")
        if marker(request) in text and not observed.get("human_prompt"):
            binding = "public"
        if binding not in ("prompt", "relic", "public"):
            return
        receipt = {k: request[k] for k in ("org_id", "member", "carrier", "nonce")}
        receipt.update(session_id=event["session_id"], event="Stop", entrypoint="claude-desktop",
                       matched_by=binding, last_assistant_message=text, at=time.time())
        _write(folder / "receipt.json", receipt)
        binding_path.unlink(missing_ok=True)
