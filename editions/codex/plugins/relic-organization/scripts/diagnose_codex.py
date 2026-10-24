"""Read-only actual Codex plugin and MCP loader inspection; never starts a model turn."""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading


def inspect():
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("Codex is not on PATH")
    proc = subprocess.Popen([codex, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    inbox = queue.Queue()
    def reader():
        for line in proc.stdout:
            try:
                inbox.put(json.loads(line))
            except ValueError:
                pass
    threading.Thread(target=reader, daemon=True).start()
    seq = 0
    def rpc(method, params):
        nonlocal seq
        seq += 1
        request_id = seq
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": seq, "method": method, "params": params})+"\n")
        proc.stdin.flush()
        while True:
            reply = inbox.get(timeout=45)
            if reply.get("id") == request_id:
                return reply
    try:
        init = rpc("initialize", {"clientInfo": {"name": "relic_diagnostics", "version": "0.1.0"},
                                   "capabilities": {"experimentalApi": True}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "initialized"})+"\n")
        proc.stdin.flush()
        plugin = rpc("plugin/read", {"pluginName": "relic-organization", "marketplacePath": str(Path(__file__).resolve().parents[3] / ".agents/plugins/marketplace.json")})
        mcp = rpc("mcpServerStatus/list", {"serverName": "relic_organization", "detail": "full"})
        hooks = rpc("hooks/list", {"cwds": [str(Path(__file__).resolve().parents[3])]})
        return {"initialize": init, "plugin": plugin, "mcp": mcp, "hooks": hooks}
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    print(json.dumps(inspect(), ensure_ascii=False, indent=2))
