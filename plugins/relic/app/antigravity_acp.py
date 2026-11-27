"""ACP (Agent Client Protocol v1) adapter for Antigravity (Google's agent app).

The Relic App starts this script as a subprocess and talks JSON-RPC 2.0 over stdio (one JSON line per message).
It delegates all Antigravity local RPCs to relic_core.antigravity so transport, authentication and transcript
reading live in one place:
  * initialize             -> advertise protocolVersion 1 and session resume/load support
  * session/new            -> create and initialize an Antigravity conversation (antigravity.create_conversation)
                              and wait until idle so Hub._start() can seat it in Relic before its first turn
  * session/resume | load  -> attach to an existing Antigravity conversation without replaying history
  * session/prompt         -> send the prompt (antigravity.send_message), poll until RUN_STATE_IDLE, stream
                              newly appended transcript steps as ACP session/update notifications
  * session/cancel         -> stop waiting for the active prompt and return stopReason="cancelled"
  * session/set_model |
    session/set_config_option -> record the model chosen in the Relic App
"""
import importlib
import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROTOCOL_VERSION = 1
POLL_INTERVAL = 0.5
START_GRACE = 15.0
BUSY_WAIT = 30.0
BOOTSTRAP_TIMEOUT = 60.0
TURN_TIMEOUT = 3600.0
BOOTSTRAP_PROMPT = "Initializing Relic seat. Reply with OK and do not call any tools."

MODELS = [
    {"modelId": "flash", "name": "Flash"},
    {"modelId": "pro", "name": "Pro"},
    {"modelId": "flash_lite", "name": "Flash Lite"},
]
MODES = [{"id": "default", "name": "Default"}]

TOOL_KINDS = {
    "run_command": "execute",
    "edit_file": "edit",
    "write_file": "edit",
    "replace_file_content": "edit",
    "multi_replace_file_content": "edit",
    "write_to_file": "edit",
    "read_file": "read",
    "view_file": "read",
    "view_file_outline": "read",
    "view_code_item": "read",
    "grep_search": "search",
    "find_by_name": "search",
    "search_web": "search",
}


def load_backend():
    """Import relic_core.antigravity lazily so tests can inject a stub backend without touching ~/.gemini."""
    return importlib.import_module("relic_core.antigravity")


def _parse_arg_value(value):
    """Transcript tool_call args sometimes wrap string values in extra JSON quotes; unwrap cleanly."""
    if isinstance(value, str):
        text = value.strip()
        if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
            try:
                parsed = json.loads(text)
                if isinstance(parsed, str):
                    return parsed
            except ValueError:
                pass
        if text[:1] in ("{", "["):
            try:
                return json.loads(text)
            except ValueError:
                pass
    return value


def normalize_tool_call(tc, backend):
    """Convert one Antigravity transcript tool_calls entry into ACP (title, kind, raw_input, locations)."""
    name = str((tc or {}).get("name") or "tool")
    raw_args = (tc or {}).get("args")
    args = {k: _parse_arg_value(v) for k, v in raw_args.items()} if isinstance(raw_args, dict) else {}
    if name == "call_mcp_tool":
        server = str(args.get("ServerName") or args.get("serverName") or "")
        mcp_tool = str(args.get("ToolName") or args.get("toolName") or "")
        inner = args.get("Arguments") if "Arguments" in args else args.get("arguments")
        if not isinstance(inner, dict):
            inner = {}
        if backend.is_server(server) and mcp_tool:
            return "mcp__relic_org__" + mcp_tool, "other", {"serverName": "relic_org", "tool": mcp_tool, "arguments": inner}, []
        title = ("%s.%s" % (server, mcp_tool)).strip(".") or name
        return title, "other", {"serverName": server, "tool": mcp_tool, "arguments": inner}, []
    kind = TOOL_KINDS.get(name, "other")
    raw_input = dict(args)
    locations = []
    if kind == "execute":
        cmd = args.get("CommandLine") or args.get("command") or args.get("cmd") or ""
        if cmd:
            raw_input["command"] = str(cmd)
        title = ("%s: %s" % (name, str(cmd)[:80])) if cmd else name
    elif kind in ("edit", "read"):
        path = args.get("Path") or args.get("TargetFile") or args.get("AbsolutePath") or args.get("file_path") or ""
        if path:
            raw_input["file_path"] = str(path)
            locations = [{"path": str(path)}]
        title = ("%s %s" % (name, str(path))) if path else name
    else:
        title = name
    return title, kind, raw_input, locations


def _seat_defaults():
    """Read optional title and configured model for the Relic seat that launched this adapter."""
    seat_spec = (os.getenv("RELIC_SEAT") or "").strip()
    org_id, _, member = seat_spec.partition("/")
    if not (org_id and member):
        return "Relic · Antigravity", ""
    title = "%s · %s" % (org_id, member)
    model = ""
    try:
        from relic_core.store import Store
        org = Store().get(org_id)
        if org:
            title = "%s · %s" % (org.get("name") or org_id, member)
            seat = (org.get("members") or {}).get(member) or {}
            model = str(((seat.get("config") or {}).get("model")) or "").strip()
    except Exception:
        pass
    return title, model


class AntigravityAcpServer:
    """JSON-RPC 2.0 ACP v1 server backed by relic_core.antigravity."""

    def __init__(self, backend=None, send=None, poll=POLL_INTERVAL, start_grace=START_GRACE,
                 busy_wait=BUSY_WAIT, bootstrap_timeout=BOOTSTRAP_TIMEOUT, turn_timeout=TURN_TIMEOUT,
                 sleep=time.sleep, clock=time.monotonic):
        self._backend = backend
        self._send_fn = send
        self.poll = float(poll)
        self.start_grace = float(start_grace)
        self.busy_wait = float(busy_wait)
        self.bootstrap_timeout = float(bootstrap_timeout)
        self.turn_timeout = float(turn_timeout)
        self.sleep = sleep
        self.clock = clock
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._sessions = {}  # sid -> {"cwd": str, "model": str, "title": str, "cancel": Event}

    @property
    def backend(self):
        if self._backend is None:
            self._backend = load_backend()
        return self._backend

    def send(self, obj):
        if self._send_fn is not None:
            self._send_fn(obj)
            return
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        with self._write_lock:
            sys.stdout.write(line)
            sys.stdout.flush()

    def update(self, sid, body):
        self.send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": sid, "update": body}})

    def _available_models(self):
        """Query relic_core.antigravity.models() -> (default_model_id, availableModels); fall back to MODELS."""
        getter = getattr(self.backend, "models", None)
        info = None
        if callable(getter):
            try:
                info = getter()
            except Exception:
                info = None
        if isinstance(info, dict):
            choices = [
                {"modelId": str(item["id"]), "name": str(item.get("name") or item["id"])}
                for item in (info.get("choices") or [])
                if isinstance(item, dict) and item.get("id")
            ]
            default = str(info.get("default") or "")
            if choices:
                return default, choices
            if default:
                return default, list(MODELS)
        return "", list(MODELS)

    def _session_payload(self, sid, model="", available=None):
        return {
            "sessionId": sid,
            "models": {"currentModelId": model or "", "availableModels": list(MODELS if available is None else available)},
            "modes": {"currentModeId": "default", "availableModes": list(MODES)},
        }

    def _create_conversation(self, title, model="", cwd=""):
        """Create and initialize an Antigravity conversation through relic_core.antigravity.create_conversation.

        Antigravity's SendAgentMessage only triggers a turn on a conversation that has already completed an initial
        turn, so session/new creates it with a tiny bootstrap prompt and waits until RUN_STATE_IDLE before returning
        the conversation id for Hub._start() to seat in Relic.
        """
        prompt = (BOOTSTRAP_PROMPT + (" Working directory: %s" % cwd if cwd else ""))
        sid = str(self.backend.create_conversation(title, prompt, model or None))
        path = self.backend.transcript_path(sid)
        deadline = self.clock() + self.bootstrap_timeout
        grace_until = self.clock() + min(self.start_grace, self.bootstrap_timeout)
        saw_running = False
        while self.clock() < deadline:
            state = self.backend.run_state(sid)
            if state and state != self.backend.IDLE:
                saw_running = True
            idx = self.backend.last_step_index(path)
            if state == self.backend.IDLE and (idx >= 1 or saw_running or self.clock() >= grace_until):
                break
            self.sleep(min(self.poll, max(0.05, deadline - self.clock())))
        return sid

    def _wait_if_busy(self, sid, cancel):
        """Wait briefly if an earlier turn is still finishing before sending a new prompt."""
        deadline = self.clock() + self.busy_wait
        while self.clock() < deadline and not cancel.is_set():
            state = self.backend.run_state(sid)
            if not state or state == self.backend.IDLE:
                return True
            self.sleep(min(self.poll, max(0.05, deadline - self.clock())))
        return cancel.is_set() or self.backend.run_state(sid) in ("", self.backend.IDLE)

    def _stream_steps(self, sid, path, seen, open_tools, emitted_text):
        """Emit ACP updates for any new transcript steps beyond `seen` (set of step_index ints)."""
        steps = self.backend.transcript(path)
        max_idx = max(seen, default=-1)
        for step in steps:
            idx = step.get("step_index")
            if not isinstance(idx, int) or idx in seen:
                continue
            seen.add(idx)
            if idx > max_idx:
                max_idx = idx
            kind = step.get("type")
            if kind == "PLANNER_RESPONSE":
                tool_calls = step.get("tool_calls") or []
                for pos, tc in enumerate(tool_calls):
                    if not isinstance(tc, dict):
                        continue
                    call_id = "ag-%d-%d" % (idx, pos)
                    title, acp_kind, raw_input, locations = normalize_tool_call(tc, self.backend)
                    payload = {"sessionUpdate": "tool_call", "toolCallId": call_id, "title": title,
                               "kind": acp_kind, "status": "in_progress", "rawInput": raw_input}
                    if locations:
                        payload["locations"] = locations
                    self.update(sid, payload)
                    open_tools.append(call_id)
                content = step.get("content")
                if isinstance(content, str) and content.strip():
                    prefix = "\n\n" if emitted_text[0] else ""
                    emitted_text[0] = True
                    self.update(sid, {"sessionUpdate": "agent_message_chunk",
                                      "content": {"type": "text", "text": prefix + content}})
            elif kind == "GENERIC":
                failed = step.get("status") == "ERROR" or bool(step.get("error"))
                text = str(step.get("error") or step.get("content") or "")
                call_id = open_tools.pop(0) if open_tools else ("ag-step-%d" % idx)
                payload = {"sessionUpdate": "tool_call_update", "toolCallId": call_id,
                           "status": "failed" if failed else "completed"}
                if text:
                    payload["content"] = [{"type": "content", "content": {"type": "text", "text": text[-2000:]}}]
                self.update(sid, payload)
        return max_idx

    def _prompt(self, params):
        sid = str(params.get("sessionId") or "")
        if not sid:
            raise RuntimeError("session/prompt requires sessionId")
        blocks = params.get("prompt") or []
        text = "".join(p.get("text", "") for p in blocks if isinstance(p, dict) and p.get("type") == "text")
        if not text:
            text = "".join(str(p.get("text", "")) for p in blocks if isinstance(p, dict))
        with self._state_lock:
            session = self._sessions.setdefault(sid, {"cwd": "", "model": "", "title": "", "cancel": threading.Event()})
            cancel = session["cancel"]
            cancel.clear()

        if not self._wait_if_busy(sid, cancel):
            raise RuntimeError("Antigravity conversation %s %s" % (sid, self.backend.BUSY))
        if cancel.is_set():
            return {"stopReason": "cancelled"}

        path = self.backend.transcript_path(sid)
        existing = self.backend.transcript(path)
        seen = {s["step_index"] for s in existing if isinstance(s.get("step_index"), int)}
        before = max(seen, default=-1)
        open_tools = []
        emitted_text = [False]

        self.backend.send_message(sid, text)

        deadline = self.clock() + self.turn_timeout
        grace_until = self.clock() + self.start_grace
        saw_activity = False

        while self.clock() < deadline:
            if cancel.is_set():
                return {"stopReason": "cancelled"}
            self.sleep(self.poll)
            if cancel.is_set():
                return {"stopReason": "cancelled"}
            max_idx = self._stream_steps(sid, path, seen, open_tools, emitted_text)
            state = self.backend.run_state(sid)
            if state and state != self.backend.IDLE:
                saw_activity = True
            if max_idx > before:
                saw_activity = True
            if state == self.backend.IDLE:
                # Wait until at least the reply step is visible, or the start grace expires after activity.
                if emitted_text[0] or max_idx > before + 1 or (saw_activity and self.clock() >= grace_until):
                    break
                if self.clock() >= grace_until:
                    break

        self._stream_steps(sid, path, seen, open_tools, emitted_text)
        while open_tools:
            self.update(sid, {"sessionUpdate": "tool_call_update", "toolCallId": open_tools.pop(0),
                              "status": "completed"})
        return {"stopReason": "end_turn"}

    def handle(self, message):
        method = message.get("method")
        params = message.get("params") or {}
        mid = message.get("id")
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "authMethods": [],
                    "agentCapabilities": {"loadSession": True, "sessionCapabilities": {"resume": {}}},
                }
            elif method == "session/new":
                title, model = _seat_defaults()
                default_model, available = self._available_models()
                effective_model = model or default_model
                cwd = str(params.get("cwd") or "")
                sid = self._create_conversation(title=title, model=effective_model, cwd=cwd)
                with self._state_lock:
                    self._sessions[sid] = {"cwd": cwd, "model": effective_model,
                                           "title": title, "cancel": threading.Event()}
                result = self._session_payload(sid, effective_model, available)
            elif method in ("session/resume", "session/load"):
                sid = str(params.get("sessionId") or "")
                if not sid:
                    raise RuntimeError("%s requires sessionId" % method)
                # Verify Antigravity is reachable and knows the conversation.
                self.backend.run_state(sid)
                default_model, available = self._available_models()
                with self._state_lock:
                    session = self._sessions.setdefault(sid, {"cwd": "", "model": "", "title": "",
                                                              "cancel": threading.Event()})
                    session["cwd"] = str(params.get("cwd") or session["cwd"])
                    model = session["model"] or default_model
                result = self._session_payload(sid, model, available)
            elif method == "session/prompt":
                result = self._prompt(params)
            elif method == "session/cancel":
                sid = str(params.get("sessionId") or "")
                with self._state_lock:
                    session = self._sessions.get(sid)
                if session:
                    session["cancel"].set()
                return
            elif method == "session/set_mode":
                result = {}
            elif method == "session/set_model":
                sid = str(params.get("sessionId") or "")
                model = str(params.get("modelId") or "").strip()
                with self._state_lock:
                    if sid in self._sessions:
                        self._sessions[sid]["model"] = model
                result = {}
            elif method == "session/set_config_option":
                sid = str(params.get("sessionId") or "")
                if params.get("configId") == "model":
                    with self._state_lock:
                        if sid in self._sessions:
                            self._sessions[sid]["model"] = str(params.get("value") or "").strip()
                result = {}
            else:
                if mid is not None:
                    self.send({"jsonrpc": "2.0", "id": mid,
                               "error": {"code": -32601, "message": "Method not found: %s" % method}})
                return
            if mid is not None:
                self.send({"jsonrpc": "2.0", "id": mid, "result": result})
        except Exception as error:
            if mid is not None:
                self.send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32000, "message": str(error)}})

    def serve(self, stream=None):
        stream = sys.stdin if stream is None else stream
        workers = []
        for raw in stream:
            line = raw.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if not isinstance(message, dict) or "method" not in message:
                continue
            if message.get("method") == "session/cancel":
                self.handle(message)
                continue
            worker = threading.Thread(target=self.handle, args=(message,), daemon=True)
            worker.start()
            workers.append(worker)
            workers = [w for w in workers if w.is_alive()]
        with self._state_lock:
            for session in self._sessions.values():
                session["cancel"].set()


def main():
    AntigravityAcpServer().serve()


if __name__ == "__main__":
    main()
