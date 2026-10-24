"""Read the complete local session catalog through Codex's paginated public API."""
import contextlib
import json
import os
from pathlib import Path
import queue
import shutil
import sqlite3
import subprocess
import threading
import time

from .bridge import BridgeUnavailable


class SessionIndex:
    def __init__(self, command=None):
        self.command = command or os.getenv("CODEX_CLI_PATH") or shutil.which("codex")
        self.process = None
        self.responses = queue.Queue()
        self.seq = 0
        self.supplement_count = 0

    def rpc(self, method, params):
        self.seq += 1
        request_id = self.seq
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id,
                                             "method": method, "params": params}) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + 30
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BridgeUnavailable("Local session index timed out.")
            try:
                reply = self.responses.get(timeout=remaining)
            except queue.Empty:
                raise BridgeUnavailable("Local session index timed out.")
            if reply is None:
                raise BridgeUnavailable("Local session index closed.")
            if reply.get("id") != request_id:
                continue
            if "error" in reply:
                raise BridgeUnavailable(reply["error"].get("message", "Session index error"))
            return reply.get("result", {})

    def __enter__(self):
        if not self.command:
            raise BridgeUnavailable("Codex CLI is required to read the complete local catalog.")
        self.process = subprocess.Popen([self.command, "app-server"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        def read():
            for line in self.process.stdout:
                try:
                    self.responses.put(json.loads(line))
                except ValueError:
                    pass
            self.responses.put(None)
        threading.Thread(target=read, daemon=True).start()
        try:
            self.rpc("initialize", {"clientInfo": {"name": "relic_catalog", "version": "0.2.0"}})
            self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "initialized"}) + "\n")
            self.process.stdin.flush()
        except Exception:
            self.close()
            raise
        return self

    def list(self, include_archived=False):
        sessions = {}
        pages = 0
        # Exclude internal subagent/compaction sessions. These are not human chats.
        for archived in ([False, True] if include_archived else [False]):
            cursor = None
            seen_cursors = set()
            while True:
                params = {"limit": 100, "sortKey": "updated_at", "archived": archived,
                          "sourceKinds": ["cli", "vscode", "appServer", "unknown"],
                          "useStateDbOnly": True}
                if cursor:
                    params["cursor"] = cursor
                result = self.rpc("thread/list", params)
                pages += 1
                for thread in result.get("data", []):
                    if thread.get("ephemeral"):
                        continue
                    status = thread.get("status", {})
                    sessions[thread["id"]] = {"id": thread["id"], "kind": "codex", "hostId": "local",
                        "title": thread.get("name") or thread.get("preview") or thread["id"],
                        "cwd": thread.get("cwd", ""), "updatedAt": thread.get("updatedAt", 0),
                        "status": status.get("type", "notLoaded") if isinstance(status, dict) else status,
                        "archived": archived, "source": thread.get("source", ""),
                        "isPinned": thread.get("isPinned", False)}
                cursor = result.get("nextCursor")
                if not cursor:
                    break
                if cursor in seen_cursors:
                    raise BridgeUnavailable("Local session index repeated a pagination cursor.")
                seen_cursors.add(cursor)
        # Current Codex omits freshly agent-created user-owned chats until a human
        # user event is persisted. They still have valid thread/read identities.
        # Supplement only that specific class from read-only metadata, never
        # internal spawned subagents, transcripts, or credentials.
        extra = agent_created_sessions(include_archived)
        self.supplement_count = sum(t["id"] not in sessions for t in extra)
        for thread in extra:
            sessions.setdefault(thread["id"], thread)
        return sorted(sessions.values(), key=lambda t: t["updatedAt"], reverse=True), pages

    def close(self):
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process.stdin.close()
            self.process.stdout.close()

    def __exit__(self, *args):
        self.close()


def agent_created_sessions(include_archived=False, state_path=None):
    root = Path(os.getenv("CODEX_HOME", str(Path.home() / ".codex")))
    if state_path is None:
        candidates = list(root.glob("state_*.sqlite"))
        candidates.sort(key=lambda p: int(p.stem.rsplit("_", 1)[-1]) if p.stem.rsplit("_", 1)[-1].isdigit() else -1, reverse=True)
        state_path = candidates[0] if candidates else None
    if state_path is None:
        return []
    with contextlib.closing(sqlite3.connect(Path(state_path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        columns = {r[1] for r in db.execute("PRAGMA table_info(threads)")}
        required = {"id", "source", "cwd", "archived", "thread_source", "updated_at"}
        if not required <= columns:
            raise BridgeUnavailable("Local metadata format changed; agent-created chat discovery is unavailable.")
        keys = sorted(required | ({"name", "title", "is_pinned"} & columns))
        sql = "SELECT " + ",".join(keys) + " FROM threads WHERE thread_source = ? AND source IN (?,?,?,?)"
        params = ["agent_created_thread", "cli", "vscode", "appServer", "unknown"]
        if not include_archived:
            sql += " AND archived = 0"
        rows = [dict(zip(keys, row)) for row in db.execute(sql, params)]
    result = []
    for row in rows:
        cwd = row["cwd"] or ""
        if cwd.startswith("\\\\?\\UNC\\"):
            cwd = "\\\\" + cwd[8:]
        elif cwd.startswith("\\\\?\\"):
            cwd = cwd[4:]
        result.append({"id": row["id"], "kind": "codex", "hostId": "local",
                       "title": row.get("name") or row.get("title") or row["id"],
                       "cwd": cwd, "updatedAt": row["updated_at"], "status": "notLoaded",
                       "archived": bool(row["archived"]), "source": row["source"],
                       "isPinned": bool(row.get("is_pinned")), "threadSource": "agent_created_thread"})
    return result
