"""A small Agent Client Protocol (ACP) client: run one ACP agent as a subprocess and talk JSON-RPC 2.0 over its stdio,
one JSON message per line (https://agentclientprotocol.com).

The Relic App uses it to embed the secretary and member sessions of any harness that speaks ACP: Claude Code through
@agentclientprotocol/claude-agent-acp, Codex through @agentclientprotocol/codex-acp, and later Gemini CLI, Qwen Code,
Kimi CLI, OpenCode, CodeBuddy, GLM and others from the ACP registry. Standard library only.

The client advertises no file system or terminal capability: agents use their own tools for both. Agent-to-client
requests (permission requests) go to `on_request`, which may block until the person decides; notifications
(session/update) go to `on_update`.
"""
import collections
import itertools
import json
import os
import subprocess
import threading

PROTOCOL_VERSION = 1
CLIENT_INFO = {"name": "relic-app", "title": "Relic", "version": "0.1.0"}
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class AcpError(RuntimeError):
    def __init__(self, message, code=None, data=None):
        super().__init__(message)
        self.code, self.data = code, data


class AcpAgent:
    """One running ACP agent and its connection."""

    def __init__(self, argv, env=None, cwd=None, on_update=None, on_request=None, name="agent"):
        self.argv, self.env, self.cwd, self.name = list(argv), env, cwd, name
        self.on_update = on_update or (lambda method, params: None)
        self.on_request = on_request
        self.proc = None
        self.info = {}
        self.closed = threading.Event()
        self.stderr_tail = collections.deque(maxlen=200)
        self._ids = itertools.count(1)
        self._pending = {}
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()

    # ---------------- process and connection ----------------
    def start(self, timeout=90):
        self.proc = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     cwd=self.cwd, env=self.env, creationflags=NO_WINDOW)
        threading.Thread(target=self._read, name="acp-read-%s" % self.name, daemon=True).start()
        threading.Thread(target=self._read_stderr, name="acp-err-%s" % self.name, daemon=True).start()
        self.info = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False},
            "clientInfo": CLIENT_INFO}, timeout=timeout) or {}
        return self.info

    @property
    def alive(self):
        return bool(self.proc) and self.proc.poll() is None and not self.closed.is_set()

    def capabilities(self):
        return (self.info or {}).get("agentCapabilities") or {}

    def request(self, method, params, timeout=None):
        rid = next(self._ids)
        slot = [threading.Event(), None]
        with self._lock:
            self._pending[rid] = slot
        try:
            self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        except AcpError:
            with self._lock:
                self._pending.pop(rid, None)
            raise
        if not slot[0].wait(timeout):
            with self._lock:
                self._pending.pop(rid, None)
            raise AcpError("%s: no answer from %s within %s s" % (method, self.name, timeout))
        reply = slot[1] or {}
        if "error" in reply:
            error = reply["error"] or {}
            raise AcpError(str(error.get("message") or "error"), error.get("code"), error.get("data"))
        return reply.get("result")

    def notify(self, method, params):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def close(self, wait=3):
        """End the agent: close its input (agents exit at the end of their input), then stop the agent and the
        programs it started (the adapter runs Claude Code or Codex as a child process) if it is still running."""
        if not self.proc:
            return
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True,
                               creationflags=NO_WINDOW)
            else:
                self.proc.kill()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        self.closed.set()
        for stream in (self.proc.stdout, self.proc.stderr):
            try:
                stream.close()
            except (OSError, ValueError):
                pass

    def _send(self, message):
        data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        with self._write_lock:
            if not self.alive:
                raise AcpError("%s is not running" % self.name)
            try:
                self.proc.stdin.write(data)
                self.proc.stdin.flush()
            except OSError as error:
                raise AcpError("%s closed its input: %s" % (self.name, error)) from None

    def _read(self):
        try:
            for raw in self.proc.stdout:
                self._handle_line(raw)
        except (OSError, ValueError):  # the pipe was closed by close()
            pass
        self.closed.set()
        with self._lock:
            pending, self._pending = list(self._pending.values()), {}
        for slot in pending:
            slot[1] = {"error": {"code": -32000, "message": "%s exited: %s" % (self.name, self.last_error())}}
            slot[0].set()

    def _handle_line(self, raw):
        line = raw.decode("utf-8", "replace").strip()
        if not line:
            return
        try:
            message = json.loads(line)
        except ValueError:
            self.stderr_tail.append("[stdout] " + line[:300])
            return
        if "method" in message:
            if "id" in message:  # a request from the agent: answered on its own thread, it may wait for the person
                threading.Thread(target=self._serve, args=(message,), daemon=True).start()
            else:
                try:
                    self.on_update(message["method"], message.get("params") or {})
                except Exception as error:  # a broken listener must not stop the connection
                    self.stderr_tail.append("[client] update handler failed: %s" % error)
        elif "id" in message:
            with self._lock:
                slot = self._pending.pop(message["id"], None)
            if slot:
                slot[1] = message
                slot[0].set()

    def _read_stderr(self):
        try:
            for raw in self.proc.stderr:
                line = raw.decode("utf-8", "replace").rstrip()
                if line:
                    self.stderr_tail.append(line[:500])
        except (OSError, ValueError):
            pass

    def last_error(self):
        lines = [l for l in self.stderr_tail if "error" in l.lower()]
        return (lines or list(self.stderr_tail) or ["no output"])[-1][:300]

    def _serve(self, message):
        method, params = message["method"], message.get("params") or {}
        try:
            result = self.on_request(method, params) if self.on_request else None
            if result is None:
                raise AcpError("Method not found: " + method, -32601)
            self._send({"jsonrpc": "2.0", "id": message["id"], "result": result})
        except AcpError as error:
            self._reply_error(message["id"], error.code or -32603, str(error))
        except Exception as error:
            self._reply_error(message["id"], -32603, "%s: %s" % (type(error).__name__, error))

    def _reply_error(self, rid, code, text):
        try:
            self._send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": text}})
        except AcpError:
            pass

    # ---------------- sessions ----------------
    def new_session(self, cwd, mcp_servers=(), meta=None, timeout=180):
        params = {"cwd": str(cwd), "mcpServers": list(mcp_servers)}
        if meta:
            params["_meta"] = meta
        return self.request("session/new", params, timeout=timeout) or {}

    def load_session(self, session_id, cwd, mcp_servers=(), meta=None, timeout=300):
        """Open an existing session; the agent replays its history as session/update notifications."""
        params = {"sessionId": session_id, "cwd": str(cwd), "mcpServers": list(mcp_servers)}
        if meta:
            params["_meta"] = meta
        return self.request("session/load", params, timeout=timeout) or {}

    def resume_session(self, session_id, cwd, mcp_servers=(), meta=None, timeout=300):
        """Open an existing session without replaying its history (sessionCapabilities.resume)."""
        params = {"sessionId": session_id, "cwd": str(cwd), "mcpServers": list(mcp_servers)}
        if meta:
            params["_meta"] = meta
        return self.request("session/resume", params, timeout=timeout) or {}

    def prompt(self, session_id, text, timeout=None):
        return self.request("session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]},
                            timeout=timeout) or {}

    def cancel(self, session_id):
        self.notify("session/cancel", {"sessionId": session_id})

    def set_mode(self, session_id, mode_id):
        return self.request("session/set_mode", {"sessionId": session_id, "modeId": mode_id}, timeout=60)

    def set_config_option(self, session_id, config_id, value):
        return self.request("session/set_config_option", {"sessionId": session_id, "configId": config_id, "value": value},
                            timeout=60)


def text_of(content):
    """The text of an ACP content block (text, or a resource / resource link shown by name)."""
    if not isinstance(content, dict):
        return ""
    kind = content.get("type")
    if kind == "text":
        return content.get("text") or ""
    if kind == "resource_link":
        return "[%s]" % (content.get("name") or content.get("uri") or "resource")
    if kind == "resource":
        resource = content.get("resource") or {}
        return resource.get("text") or "[%s]" % (resource.get("uri") or "resource")
    if kind == "image":
        return "[image]"
    return ""


def tool_text(content_list):
    """Readable text of a tool call's content list (text blocks and diffs)."""
    out = []
    for item in content_list or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "content":
            out.append(text_of(item.get("content")))
        elif item.get("type") == "diff":
            out.append("diff %s" % item.get("path", ""))
        elif item.get("type") == "terminal":
            out.append("[terminal %s]" % item.get("terminalId", ""))
    return "\n".join(t for t in out if t)
