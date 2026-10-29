"""Turns for Codex chats that the Codex desktop app has open, through the app's own tool pipe.

The desktop app loads a chat when the person opens it and keeps it loaded, which locks the chat for writing: the
runner's own `codex app-server` then cannot start a turn there ("already has an active writer"). The app serves its
own tools (namespace codex_app) to the MCP servers of its chats over a named pipe, whose name it passes to them in
CODEX_APP_TOOLS_PIPE_PATH; the older relic-organization plugin reached desktop chats through the same pipe. Relic uses
two of those tools:
  read_thread             whether the app has the chat loaded, whether a turn is running there, and how a turn ended
  send_message_to_thread  the wake-up prompt, as a message the person sees in that chat; the app runs the turn
The app's description of send_message_to_thread asks for the person's authorization to message a chat. Relic sends one
only for a seat the person configured in the Relic App, in an organization whose auto-wake switch is on (Hongyi's
decision of 2026-10-17: everything automatic); switching auto-wake off stops these messages with every other wake-up.

The endpoint changes every time the app starts. A Relic MCP server inside a desktop chat remembers the endpoint the
host supplied. Windows can also probe its named pipes. macOS uses only that explicit endpoint or its remembered copy,
validates a private same-user Unix socket, and requires a successful tools/list handshake. Framing was confirmed in
the installed macOS host; its peer authorizer can still refuse Relic. This bridge is separate from app-server.

The same app holds ChatGPT chats (kind "chatgpt", no host), which these tools reach too. A tool call names the thread
that makes it; a ChatGPT chat cannot be that caller, so calls about one are made in the name of a local Codex thread
(Desktop.find_caller, remembered next to the pipe).
"""
import json
import os
import re
import socket
import stat
import struct
import sys
import threading
import time
import uuid
from pathlib import Path

from . import runner

PIPE_ENV = "CODEX_APP_TOOLS_PIPE_PATH"
PIPE_DIR = "\\\\.\\pipe\\"
PROBE_PREFIXES = ("codex-app-tools-", "codex-browser-use-")  # how the desktop app names its tool pipes
CODEX_PIPE = re.compile(r"\\\\\.\\pipe\\codex-[A-Za-z0-9][A-Za-z0-9_.\-]*")  # a local named pipe of the Codex app
NAMESPACE = "codex_app"
SEND = "send_message_to_thread"
NOT_LOADED = "notLoaded"
IDLE = "idle"
FINISHED = ("completed", "failed", "interrupted")
BUSY = "is busy in the Codex desktop app"  # a turn is running in the chat: wait for it, never interject
MAX_FRAME = 8 * 1024 * 1024  # the desktop tools bridge's documented-by-installed-host frame limit
REQUIRED_TOOLS = {"read_thread", "send_message_to_thread", "list_threads"}


class DesktopError(RuntimeError):
    """The request did not reach the app (or the app refused it): nothing happened, trying again later is safe."""


class Uncertain(DesktopError):
    """The request was written but no complete answer came back: the app may have acted on it."""


def is_codex_pipe(path):
    """Only local named pipes of the Codex app are ever opened: a stale or wrong name must never reach a file."""
    return bool(path) and CODEX_PIPE.fullmatch(str(path)) is not None


def _socket_identity(path):
    """Validate an explicitly supplied local socket; never discover endpoints by scanning directories.

    /tmp itself is a system symlink on macOS. The socket must not be a symlink, and its immediate parent must be
    owned by this user without group/other write permission. The socket is private to that same user.
    """
    if sys.platform != "darwin" or not path:
        return None
    try:
        target = Path(path)
        if not target.is_absolute() or target.suffix != ".sock" or ".." in target.parts:
            return None
        info, parent = target.lstat(), target.parent.stat()
        if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or
                not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or parent.st_mode & 0o022):
            return None
        return {"device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid, "ctime_ns": info.st_ctime_ns}
    except (OSError, TypeError, ValueError):
        return None


def cache_path():
    return runner.runs_dir() / "codex-desktop.json"


def _cached():
    try:
        data = json.loads(cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _cache(**fields):
    try:
        cache_path().write_text(json.dumps(dict(_cached(), seen=time.time(), **fields)), encoding="utf-8")
    except OSError:
        pass


def remember(pipe):
    if is_codex_pipe(pipe) or _socket_identity(pipe):
        _cache(pipe=pipe)


def remember_env():
    """Inside a desktop chat the app names its pipe in the environment; a Relic MCP server records it at start."""
    remember((os.getenv(PIPE_ENV) or "").strip())


def _read(handle, size):
    data = b""
    while len(data) < size:
        chunk = handle.read(size - len(data))
        if not chunk:
            raise DesktopError("the Codex app closed its tool pipe")
        data += chunk
    return data


def _open(pipe, tries=20):
    """Open the pipe; right after another client connects, Windows briefly has no free instance of it."""
    for _ in range(tries - 1):
        try:
            return open(pipe, "r+b", buffering=0)
        except OSError:
            time.sleep(0.1)
    return open(pipe, "r+b", buffering=0)


def exchange(pipe, message, timeout=10.0):
    """One request on the app's tool pipe: a uint32 little-endian length, then UTF-8 JSON, in each direction.
    Raises DesktopError when the request surely did not reach the app, Uncertain when it may have."""
    if _socket_identity(pipe):
        return _unix_exchange(pipe, message, timeout)
    if not runner.WINDOWS or not is_codex_pipe(pipe):
        raise DesktopError("not a local Codex pipe: %r" % (pipe,))
    box = {}

    def run():
        try:
            with _open(pipe) as handle:
                body = json.dumps(message, ensure_ascii=False).encode("utf-8")
                if not 0 < len(body) <= MAX_FRAME:
                    raise DesktopError("Codex request exceeds the bridge frame limit")
                box["writing"] = True
                handle.write(struct.pack("<I", len(body)) + body)
                size = struct.unpack("<I", _read(handle, 4))[0]
                if not 0 < size <= MAX_FRAME:
                    raise DesktopError("Codex returned an invalid bridge frame length")
                box["reply"] = json.loads(_read(handle, size).decode("utf-8"))
        except Exception as error:  # reported below, in the caller's thread
            box["error"] = error

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout)
    if "reply" in box:
        return box["reply"]
    problem = str(box.get("error") or "the Codex app did not answer on its tool pipe")
    # still running (it may write yet) or failed after it started writing: the app may have the request
    raise (Uncertain if worker.is_alive() or box.get("writing") else DesktopError)(problem)


def _unix_exchange(path, message, timeout):
    """Confirmed macOS bridge framing: uint32 little-endian size plus UTF-8 JSON (not app-server WebSockets).

    A host may reject an otherwise valid local peer. This client never changes its identity or circumvents that
    authorization. Any error after a write starts is uncertain; callers must not resend a tool call automatically.
    """
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    if not 0 < len(body) <= MAX_FRAME:
        raise DesktopError("Codex request exceeds the bridge frame limit")
    writing = False
    deadline = time.monotonic() + timeout
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            def remaining():
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("the Codex desktop bridge did not answer before its deadline")
                connection.settimeout(left)

            def receive(size):
                data = bytearray()
                while len(data) < size:
                    remaining()
                    chunk = connection.recv(size - len(data))
                    if not chunk:
                        raise DesktopError("the host closed the desktop bridge connection (peer access may be refused)")
                    data.extend(chunk)
                return data

            remaining()
            connection.connect(path)
            remaining()
            writing = True
            connection.sendall(struct.pack("<I", len(body)) + body)
            size = struct.unpack("<I", receive(4))[0]
            if not 0 < size <= MAX_FRAME:
                raise DesktopError("Codex returned an invalid bridge frame length")
            reply = json.loads(receive(size).decode("utf-8"))
            if not isinstance(reply, dict) or reply.get("id") != message.get("id"):
                raise DesktopError("Codex returned an unmatched bridge response")
            return reply
    except (OSError, ValueError, DesktopError) as error:
        raise (Uncertain if writing else DesktopError)(str(error)) from None


def serves_codex_app(pipe, timeout=3.0):
    reply = exchange(pipe, {"id": 1, "jsonrpc": "2.0", "method": "tools/list", "params": {"threadStartKind": "all"}},
                     timeout)
    tools = (reply.get("result") or {}).get("tools") or []
    names = {t.get("name") for t in tools if isinstance(t, dict) and t.get("namespace") == NAMESPACE}
    return REQUIRED_TOOLS <= names if _socket_identity(pipe) else SEND in names


def find_pipe(listdir=os.listdir):
    """Find the Windows bridge, or verify only a host-supplied/cached Unix endpoint on macOS."""
    if not runner.WINDOWS:
        status = transport_capability(probe=True)
        return status.get("endpoint") if status["available"] else None
    known = [(os.getenv(PIPE_ENV) or "").strip(), str(_cached().get("pipe") or "")]
    try:
        names = listdir(PIPE_DIR)
    except OSError:
        names = []
    probed = [PIPE_DIR + n for n in names if n.startswith(PROBE_PREFIXES)]
    tried = set()
    for pipe in [p for p in known + probed if is_codex_pipe(p)]:
        if pipe in tried:
            continue
        tried.add(pipe)
        try:
            if serves_codex_app(pipe):
                remember(pipe)
                return pipe
        except DesktopError:
            continue
    return None


def transport_capability(probe=False):
    """Read verified bridge availability; opt-in probes call tools/list only, never chat tools.

    A successful probe is tied to the socket inode. Replacing/removing the socket invalidates the proof. API/UI
    reads use probe=False, so polling capabilities never opens connections or starts account/model operations.
    """
    if sys.platform != "darwin":
        return {"available": runner.WINDOWS, "transport": "windows-named-pipe" if runner.WINDOWS else "none",
                "reason": "Windows desktop bridge" if runner.WINDOWS else "No desktop bridge on this platform"}
    cached = _cached()
    candidates = list(dict.fromkeys(p for p in ((os.getenv(PIPE_ENV) or "").strip(), cached.get("pipe")) if isinstance(p, str) and p))
    valid = [(path, _socket_identity(path)) for path in candidates]
    valid = [(path, identity) for path, identity in valid if identity]
    for path, identity in valid:
        proof = cached.get("verification") or {}
        if not isinstance(proof, dict):
            proof = {}
        if not probe and proof.get("endpoint") == path and proof.get("identity") == identity and proof.get("available"):
            return dict(proof, transport="unix-socket", reason="Host bridge handshake verified; delivery still requires host authorization")
        if probe:
            try:
                available = serves_codex_app(path, timeout=3.0)
                reason = "Host bridge handshake verified" if available else "Host bridge lacks the required Relic desktop tools"
            except DesktopError as error:
                available, reason = False, str(error)
            proof = {"available": available, "endpoint": path, "identity": identity, "checked_at": time.time(), "reason": reason}
            _cache(pipe=path, verification=proof)
            if available:
                return dict(proof, transport="unix-socket")
    last = _cached().get("verification") or {}
    if not isinstance(last, dict):
        last = {}
    reason = (last.get("reason") if any(last.get("endpoint") == path and last.get("identity") == identity for path, identity in valid)
              else "Desktop endpoint is not verified; run doctor.py --probe-desktop" if valid
              else "No private host-supplied desktop socket; open a chat with the Relic plugin loaded")
    return {"available": False, "transport": "unix-socket", "reason": reason, "checked_at": last.get("checked_at")}


def reset_transport_verification():
    """Forget a local handshake result without changing the host or its supplied endpoint."""
    _cache(verification={})


class Desktop:
    """The codex_app tools of the running Codex desktop app."""

    def __init__(self, pipe):
        self.pipe = pipe

    def call(self, tool, arguments, caller):
        params = {"arguments": arguments, "callerSource": "codex", "callId": "relic-" + uuid.uuid4().hex,
                  "hostId": "local", "namespace": NAMESPACE, "threadId": caller, "tool": tool,
                  "turnId": "relic-" + uuid.uuid4().hex}
        reply = exchange(self.pipe, {"id": 1, "jsonrpc": "2.0", "method": "tools/call", "params": params}, 30.0)
        if "error" in reply:
            raise DesktopError("%s: %s" % (tool, (reply.get("error") or {}).get("message")))
        result = reply.get("result") or {}
        texts = [i.get("text", "") for i in result.get("contentItems") or [] if i.get("type") == "inputText"]
        if not result.get("success"):
            raise DesktopError("%s: %s" % (tool, " ".join(texts)[:500] or "failed"))
        for text in texts:
            try:
                return json.loads(text)
            except ValueError:
                return {"text": text}
        return {}

    def read(self, thread_id, turns=1, host="local", caller=None):
        """The chat's status and its newest turns, newest first. A ChatGPT chat has no host (host=None) and needs a
        Codex thread as the caller."""
        args = {"threadId": thread_id, "turnLimit": turns, "includeOutputs": False}
        if host:
            args["hostId"] = host
        return self.call("read_thread", args, caller or thread_id)

    def send(self, thread_id, prompt, host="local", caller=None):
        args = {"threadId": thread_id, "prompt": prompt}
        if host:
            args["hostId"] = host
        return self.call(SEND, args, caller or thread_id)

    def threads(self, caller, limit=50):
        """The app's chats and threads, pinned first: [{id, kind, hostId, title, status, updatedAt, ...}]."""
        data = self.call("list_threads", {"limit": limit}, caller)
        return (data.get("pinnedThreads") or []) + (data.get("threads") or [])

    def find_caller(self, candidates=None):
        """A local Codex thread the app accepts as the caller of tool calls about ChatGPT chats: the one that worked
        last time, else the most recent Codex threads in turn (the app refuses a thread busy with a turn of its own)."""
        remembered = _cached().get("caller")
        ordered = ([remembered] if remembered else []) + [t for t in (candidates or codex_threads()) if t != remembered]
        for thread in ordered[:8]:
            try:
                self.call("list_threads", {"limit": 1}, thread)
            except DesktopError:
                continue
            _cache(caller=thread)
            return thread
        return None


def connect(find=find_pipe):
    pipe = find()
    return Desktop(pipe) if pipe else None


def codex_threads():
    """Local Codex threads, most recently used first (callers for tool calls about ChatGPT chats)."""
    from .sessions import codex_sessions
    try:
        return [s["id"] for s in codex_sessions()]
    except Exception:  # an unreadable thread index: no callers
        return []


def status(data):
    return ((data.get("thread") or {}).get("status") or {}).get("type")


def reply_of(turn):
    text = ""
    for item in (turn or {}).get("items") or []:
        if item.get("type") == "agentMessage" and item.get("text"):
            text = item["text"]
    return text


def started_by(turn, prompt):
    """Whether the turn is the one a send_message_to_thread started. In the receiving chat such a turn opens with the
    call's output item, while a turn the person types opens with their user message; a user message that carries the
    prompt itself also counts."""
    items = (turn or {}).get("items") or []
    first = items[0] if items else {}
    if first.get("type") == "functionCallOutput" and first.get("name") == SEND:
        return True
    head = " ".join(str(prompt).split())[:60]
    for item in items:
        if item.get("type") == "userMessage":
            text = "".join(p.get("text", "") for p in item.get("content") or [] if isinstance(p, dict))
            return bool(head) and " ".join(text.split()).startswith(head)
    return False


def run_turn(app, thread_id, prompt, poll=5.0, start_wait=180.0, blind=600.0, limit=6 * 3600, sleep=time.sleep,
             clock=time.time, host="local", caller=None):
    """Send the prompt into a chat the app has open and follow the turn it starts until it ends.
    Returns (final reply, failed). Raises DesktopError(BUSY) without sending when a turn is already running there.
    Turns the person starts in that chat meanwhile are told apart (started_by) and not reported as the reply. Reads
    that fail now and then while a turn runs are waited out for up to `blind` seconds. A prompt is never sent twice:
    when the turn cannot be followed to its end, the reply says so instead.
    host and caller: None and a Codex thread for a ChatGPT chat (see the module docstring)."""
    before = app.read(thread_id, 3, host, caller)
    if status(before) != IDLE:
        raise DesktopError("the chat %s (%s)" % (BUSY, status(before)))
    known = {t.get("id") for t in before.get("turns") or []}
    unconfirmed = None
    try:
        app.send(thread_id, prompt, host, caller)  # a refusal (DesktopError) means nothing was sent: retry is safe
    except Uncertain as error:
        unconfirmed = error  # the app may have it: look for its turn, never send again
    sent = last_read = clock()
    while clock() - sent < limit:
        sleep(poll)
        try:
            data = app.read(thread_id, 3, host, caller)
        except DesktopError as error:
            if clock() - last_read > blind:
                return "Delivered in the Codex desktop app; Relic lost sight of the turn there (%s)." % error, False
            continue
        last_read = clock()
        mine = [t for t in data.get("turns") or [] if t.get("id") not in known and started_by(t, prompt)]
        if mine:
            turn = mine[0]
            if turn.get("status") in FINISHED:
                error = turn.get("error")
                if isinstance(error, dict):
                    error = error.get("message")
                return reply_of(turn) or str(error or ""), turn.get("status") != "completed"
        elif clock() - sent > start_wait and status(data) == IDLE:
            if unconfirmed:
                return ("The Codex desktop app did not confirm the prompt (%s) and no turn of it appeared; it is not "
                        "sent again." % unconfirmed), False
            return "Delivered in the Codex desktop app, but no turn started there.", False
    return "Delivered in the Codex desktop app; the turn was still running when Relic stopped following it.", False
