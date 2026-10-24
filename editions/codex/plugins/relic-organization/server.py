"""Dependency-free MCP stdio endpoint. stdout contains JSON-RPC only."""
import json
from pathlib import Path
import sys

from relic_org.service import Service, TOOLS


def main():
    version = json.loads((Path(__file__).parent / '.codex-plugin/plugin.json').read_text(encoding='utf-8'))['version']
    service = Service()
    services = {service.actor or "__default__": service}
    known = {t["name"]: t for t in TOOLS}
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if "id" not in request:
                    continue
                method = request.get("method")
                params = request.get("params", {})
                if method == "initialize":
                    result = {"protocolVersion": params.get("protocolVersion", "2024-11-05"),
                              "capabilities": {"tools": {}}, "serverInfo": {"name": "relic-organization", "version": version},
                              "instructions": "Use $relic-organization for session organizations. org_panel opens a standalone native desktop window, not a browser. No SDL."}
                elif method == "tools/list":
                    result = {"tools": TOOLS}
                elif method == "ping":
                    result = {}
                elif method == "tools/call":
                    try:
                        name = params["name"]
                        if name not in known:
                            raise ValueError("Unknown tool.")
                        args = params.get("arguments", {})
                        spec = known[name]["inputSchema"]
                        if not isinstance(args, dict) or set(spec["required"]) - set(args) or set(args) - set(spec["properties"]):
                            raise ValueError("Invalid tool arguments.")
                        meta = params.get("_meta", {})
                        turn = meta.get("x-codex-turn-metadata", {})
                        if isinstance(turn, str):
                            try:
                                turn = json.loads(turn)
                            except ValueError:
                                turn = {}
                        if not isinstance(turn, dict):
                            turn = {}
                        session = (meta.get("openai/threadId") or meta.get("openai/thread_id") or meta.get("codexThreadId")
                                   or meta.get("codex_thread_id") or meta.get("threadId") or meta.get("thread_id")
                                   or turn.get("thread_id") or service.actor)
                        key = session or "__default__"
                        if key not in services:
                            services[key] = Service(store=service.store, actor=session)
                            services[key].bridge.actor = session
                        result_data = services[key].call(name, args)
                        result = {"content": [{"type": "text", "text": json.dumps(result_data, ensure_ascii=False)}],
                                  "structuredContent": result_data if isinstance(result_data, dict) else {"items": result_data}}
                    except Exception as error:
                        result = {"isError": True, "content": [{"type": "text", "text": str(error)}]}
                else:
                    reply = {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32601, "message": "Method not found"}}
                    print(json.dumps(reply), flush=True)
                    continue
                print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}, ensure_ascii=False), flush=True)
            except (ValueError, KeyError, TypeError):
                print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid JSON-RPC input"}}), flush=True)
    finally:
        for active in services.values():
            active.close()


if __name__ == "__main__":
    main()
