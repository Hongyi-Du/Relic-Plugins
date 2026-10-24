"""Use the installed Codex app-tools MCP server, without copying its implementation."""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading


class BridgeUnavailable(RuntimeError):
    pass


class DesktopBridge:
    def __init__(self):
        self.process = None
        self.responses = queue.Queue()
        self.lock = threading.Lock()
        self.seq = 0
        self.actor = os.getenv("CODEX_THREAD_ID")
        self.inventory_info = {}

    def _start(self):
        if self.process and self.process.poll() is None:
            return
        if not os.getenv("CODEX_APP_TOOLS_PIPE_PATH"):
            raise BridgeUnavailable("Codex desktop context is unavailable; use the host chat tools as transport.")
        root = Path(os.getenv("CODEX_HOME", str(Path.home() / ".codex")))
        candidates = list((root / "plugins/cache/openai-bundled/codex-app-tools").glob("*/server.mjs"))
        def version(p):
            try:
                return tuple(int(n) for n in p.parent.name.split("."))
            except ValueError:
                return (0,)
        candidates.sort(key=version, reverse=True)
        server = os.getenv("RELIC_CODEX_APP_SERVER") or (str(candidates[0]) if candidates else None)
        node = os.getenv("CODEX_MCP_NODE_PATH") or shutil.which("node")
        if not server or not node:
            raise BridgeUnavailable("Installed codex-app-tools and Node runtime are required for direct desktop transport.")
        self.process = subprocess.Popen([node, server], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.responses = queue.Queue()
        def read(proc, inbox):
            for line in proc.stdout:
                try:
                    inbox.put(json.loads(line))
                except ValueError:
                    continue
            inbox.put({"bridge_closed": True})
        threading.Thread(target=read, args=(self.process, self.responses), daemon=True).start()
        self._rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                 "clientInfo": {"name": "relic-organization", "version": "0.1.0"}})
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.process.stdin.flush()

    def _rpc(self, method, params, timeout=25):
        self.seq += 1
        request_id = self.seq
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id,
                                             "method": method, "params": params}) + "\n")
        self.process.stdin.flush()
        while True:
            try:
                reply = self.responses.get(timeout=timeout)
            except queue.Empty:
                # A timeout after send is uncertain. Never silently resend a mutation.
                raise BridgeUnavailable("Desktop bridge timed out; delivery may be uncertain.")
            if reply.get("bridge_closed"):
                raise BridgeUnavailable("Desktop bridge closed.")
            if reply.get("id") != request_id:
                continue
            if "error" in reply:
                raise BridgeUnavailable(str(reply["error"].get("message", "Desktop bridge error")))
            return reply.get("result", {})

    def call(self, name, arguments):
        with self.lock:
            self._start()
            thread_id = self.actor
            if not thread_id:
                raise BridgeUnavailable("Current Codex session identity is missing.")
            result = self._rpc("tools/call", {"name": name, "arguments": arguments,
                              "_meta": {"openai/threadId": thread_id}})
            if result.get("isError"):
                raise BridgeUnavailable("; ".join(c.get("text", "") for c in result.get("content", [])))
            for content in result.get("content", []):
                if content.get("type") == "text":
                    try:
                        return json.loads(content["text"])
                    except ValueError:
                        return {"text": content["text"]}
            return result

    def inventory(self, include_archived=False):
        from .inventory import SessionIndex
        recent = []
        native_error = None
        try:
            result = self.call("list_threads", {"limit": 50})
            threads = result.get("pinnedThreads", []) + result.get("threads", [])
            recent = [dict(t, archived=False) for t in threads
                      if t.get("kind") == "codex" and t.get("hostId") == "local"]
        except BridgeUnavailable as error:
            native_error = str(error)
        try:
            with SessionIndex() as index:
                sessions, pages = index.list(include_archived)
                supplement = getattr(index, "supplement_count", 0)
            by_id = {t["id"]: t for t in sessions}
            # Preserve exact desktop titles and current runtime status for recent chats.
            for thread in recent:
                by_id[thread["id"]] = dict(by_id.get(thread["id"], {}), **thread)
            self.inventory_info = {"catalog": "complete_local", "pages": pages,
                                   "agent_created_supplement": supplement if isinstance(supplement, int) else 0,
                                   "include_archived": include_archived,
                                   "transport_available": native_error is None}
            if native_error:
                self.inventory_info["reason"] = native_error
            return sorted(by_id.values(), key=lambda t: t.get("updatedAt", 0), reverse=True)
        except (BridgeUnavailable, OSError) as error:
            if native_error:
                raise BridgeUnavailable(f"{native_error}; catalog: {error}")
            self.inventory_info = {"catalog": "recent_only", "transport_available": True,
                                   "reason": str(error), "include_archived": False}
            return recent

    def send(self, member, prompt):
        return self.call("send_message_to_thread", {"threadId": member["thread_id"],
                         "hostId": member.get("host_id", "local"), "prompt": prompt})

    def close(self):
        if self.process:
            self.process.terminate()
