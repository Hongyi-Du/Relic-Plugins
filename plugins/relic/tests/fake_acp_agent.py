"""A small ACP agent for tests: JSON-RPC 2.0 over stdio, one message per line (Agent Client Protocol v1).

session/prompt reports one tool call (pending, then completed), asks for permission to edit notes.txt when the prompt
contains "needs permission" and for a call of the Relic server when it contains "relic permission", waits for
session/cancel when it contains "slow", and replies "echo: <prompt>" in two chunks (with the permission outcome
appended). With FAKE_ACP_LOG set, it appends each session/new, session/resume and session/load (its params and the
environment variables that name a session or seat) to that file as one JSON line.
"""
import json
import os
import sys
import threading
import uuid

SEEN_ENV = ("RELIC_SEAT", "RELIC_SEAT_TOKEN", "RELIC_HOME", "CODEX_THREAD_ID", "PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT",
            "RELIC_ACTOR")


def log(method, params):
    path = os.getenv("FAKE_ACP_LOG")
    if path:
        with _lock, open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"method": method, "params": params,
                                     "env": {k: os.environ.get(k) for k in SEEN_ENV}}) + "\n")

_lock = threading.Lock()
_waiting = {}
_next = [1000]
_cancel = {}


def send(obj):
    with _lock:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()


def ask(method, params):
    with _lock:
        _next[0] += 1
        rid = _next[0]
    slot = _waiting[rid] = [threading.Event(), None]
    send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
    slot[0].wait(60)
    return _waiting.pop(rid)[1]


def update(sid, body):
    send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": sid, "update": body}})


def prompt(params):
    sid = params["sessionId"]
    text = "".join(p.get("text", "") for p in params.get("prompt") or [] if isinstance(p, dict))
    update(sid, {"sessionUpdate": "tool_call", "toolCallId": "t1", "title": "Read notes", "kind": "read", "status": "pending"})
    update(sid, {"sessionUpdate": "tool_call_update", "toolCallId": "t1", "status": "completed",
                 "content": [{"type": "content", "content": {"type": "text", "text": "notes ok"}}]})
    if "slow" in text:
        if _cancel.setdefault(sid, threading.Event()).wait(30):
            _cancel[sid].clear()
            return {"stopReason": "cancelled"}
    chosen = ""
    asked = None
    if "needs permission" in text:
        asked = {"toolCallId": "t2", "title": "Write notes.txt", "kind": "edit", "locations": [{"path": "notes.txt"}],
                 "rawInput": {"file_path": "notes.txt", "content": "hi"}}
    elif "relic permission" in text:
        asked = {"toolCallId": "elicitation:%s:relic_org:1" % sid, "title": "Allow relic_org to run message?",
                 "kind": "other", "rawInput": {"serverName": "relic_org"}}
    if asked:
        answer = ask("session/request_permission", {
            "sessionId": sid, "toolCall": asked,
            "options": [{"optionId": "allow", "name": "Allow", "kind": "allow_once"},
                        {"optionId": "reject", "name": "Reject", "kind": "reject_once"}]})
        outcome = (answer or {}).get("outcome") or {}
        chosen = " [permission: %s]" % (outcome.get("optionId") or outcome.get("outcome"))
    update(sid, {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "echo: "}})
    update(sid, {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text[-1500:] + chosen}})
    return {"stopReason": "end_turn"}


def handle(msg):
    method, params, mid = msg.get("method"), msg.get("params") or {}, msg.get("id")
    if method == "initialize":
        result = {"protocolVersion": 1, "authMethods": [],
                  "agentCapabilities": {"loadSession": True, "sessionCapabilities": {"resume": {}}}}
    elif method == "session/new":
        log(method, params)
        result = {"sessionId": "fake-" + uuid.uuid4().hex[:10],
                  "modes": {"currentModeId": "default", "availableModes": [{"id": "default", "name": "Default"},
                                                                            {"id": "auto", "name": "Auto"}]}}
    elif method in ("session/resume", "session/load", "session/set_mode"):
        if method != "session/set_mode":
            log(method, params)
        result = {}
    elif method == "session/prompt":
        result = prompt(params)
    elif method == "session/cancel":
        _cancel.setdefault(params.get("sessionId"), threading.Event()).set()
        return
    else:
        if mid is not None:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "unknown method %s" % method}})
        return
    if mid is not None:
        send({"jsonrpc": "2.0", "id": mid, "result": result})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if "method" not in msg:  # the client's answer to one of our requests
            slot = _waiting.get(msg.get("id"))
            if slot:
                slot[1] = msg.get("result")
                slot[0].set()
            continue
        threading.Thread(target=handle, args=(msg,), daemon=True).start()


if __name__ == "__main__":
    main()
