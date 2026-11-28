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
import signal
import subprocess
import threading
import time

from .processes import group_has_live_members, signal_group
from relic_core.process import creation_flags

PROTOCOL_VERSION = 1
CLIENT_INFO = {"name": "relic-app", "title": "Relic", "version": "0.1.0"}
NO_WINDOW = creation_flags()
TERMINATE_WAIT = 1.0
KILL_WAIT = 1.0
READER_WAIT = 1.0


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
        self._close_lock = threading.Lock()
        self._close_complete = False
        self._owned_pgid = None
        self._readers = []

    # ---------------- process and connection ----------------
    def start(self, timeout=90):
        attempted = False
        try:
            with self._close_lock:
                if self.proc is not None or self.closed.is_set():
                    raise AcpError("%s has already been started or closed" % self.name)
                attempted = True
                # Publish process ownership atomically with respect to close(). A shutdown during Popen must
                # wait for this handle, rather than conclude that there is nothing to stop.
                self.proc = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                             cwd=self.cwd, env=self.env, creationflags=NO_WINDOW,
                                             start_new_session=os.name != "nt", bufsize=0)
                if os.name != "nt":
                    self._owned_pgid = self.proc.pid
                for target, label in ((self._read, "read"), (self._read_stderr, "err")):
                    reader = threading.Thread(target=target, name="acp-%s-%s" % (label, self.name), daemon=True)
                    self._readers.append(reader)
                    reader.start()
            self.info = self.request("initialize", {
                "protocolVersion": PROTOCOL_VERSION,
                "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False},
                "clientInfo": CLIENT_INFO}, timeout=timeout) or {}
        except BaseException:
            if attempted:
                self.close(wait=0)
            raise
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
        """Close input gracefully, then terminate our owned adapter process tree within bounded waits.

        A POSIX adapter can exit before its children, which may still hold our pipes open. Its new process group
        remains ours until cleanup finishes, so group cleanup must not depend on the adapter still being alive.
        """
        with self._close_lock:
            if self._close_complete:
                return
            self.closed.set()
            self._fail_pending("%s connection closed" % self.name)
            if self.proc is None:
                self._close_complete = True
                return
            try:
                # Unbuffered pipes avoid waiting on a buffered writer's lock if a request is still writing.
                self.proc.stdin.close()
            except (OSError, ValueError):
                pass
            if not self._wait_for_exit(max(0, wait)):
                if self._owned_pgid is not None:
                    self._signal_group(signal.SIGTERM)
                    if not self._wait_for_exit(TERMINATE_WAIT):
                        self._signal_group(signal.SIGKILL)
                        if not self._wait_for_exit(KILL_WAIT):
                            raise AcpError("%s process group did not stop within its shutdown deadline" % self.name)
                elif self.proc.poll() is None:
                    if os.name == "nt":
                        try:
                            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True,
                                           creationflags=NO_WINDOW, timeout=5)
                        except (OSError, subprocess.TimeoutExpired):
                            self.proc.kill()
                    else:
                        # No owned group: only terminate the exact child, never infer a group from its PID.
                        self.proc.kill()
                    try:
                        self.proc.wait(timeout=KILL_WAIT)
                    except subprocess.TimeoutExpired:
                        pass
            deadline = time.monotonic() + READER_WAIT
            for reader in self._readers:
                if reader is not threading.current_thread() and reader.ident is not None:
                    reader.join(max(0, deadline - time.monotonic()))
            # Readers close their own streams in finally. Avoid closing a stream beneath a live reader.
            for index, stream in enumerate((self.proc.stdout, self.proc.stderr)):
                if index >= len(self._readers) or not self._readers[index].is_alive():
                    stream.close()
            self._owned_pgid = None
            self._close_complete = True

    def _signal_group(self, sig):
        pgid = self._owned_pgid
        if pgid is None or pgid != self.proc.pid or pgid <= 1 or pgid == os.getpgrp():
            return False
        return signal_group(pgid, sig)

    def _wait_for_exit(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            running = self.proc.poll() is None  # also reap the adapter if it has exited
            if self._owned_pgid is not None:
                running = self._signal_group(0)
            if not running:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if self._owned_pgid is None or group_has_live_members(self._owned_pgid) is not False:
                    return False
                break
            time.sleep(min(0.05, remaining))
        # The leader may exit between poll() and group inspection. Group absence
        # (or zombie-only state) does not reap our Popen child or set returncode.
        try:
            self.proc.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            return False
        return True

    def _fail_pending(self, message):
        with self._lock:
            pending, self._pending = list(self._pending.values()), {}
        for slot in pending:
            slot[1] = {"error": {"code": -32000, "message": message}}
            slot[0].set()

    def _send(self, message):
        data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        with self._write_lock:
            if not self.alive:
                raise AcpError("%s is not running" % self.name)
            try:
                remaining = memoryview(data)
                while remaining:
                    written = self.proc.stdin.write(remaining)
                    if not written:
                        raise OSError("incomplete write")
                    remaining = remaining[written:]
            except (OSError, ValueError) as error:
                raise AcpError("%s closed its input: %s" % (self.name, error)) from None

    @staticmethod
    def _lines(stream):
        """Read unbuffered pipes in chunks without a buffered stream's cross-thread close lock."""
        pending = b""
        while True:
            chunk = stream.read(65536)
            if not chunk:
                if pending:
                    yield pending
                return
            parts = (pending + chunk).split(b"\n")
            pending = parts.pop()
            yield from parts

    def _read(self):
        try:
            for raw in self._lines(self.proc.stdout):
                self._handle_line(raw)
        except (OSError, ValueError):  # the pipe was closed by close()
            pass
        finally:
            self.proc.stdout.close()
            self.closed.set()
            self._fail_pending("%s exited: %s" % (self.name, self.last_error()))

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
            for raw in self._lines(self.proc.stderr):
                line = raw.decode("utf-8", "replace").rstrip()
                if line:
                    self.stderr_tail.append(line[:500])
        except (OSError, ValueError):
            pass
        finally:
            self.proc.stderr.close()

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
