"""Launch a detached native window; stdout remains reserved for MCP JSON-RPC."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from .store import data_home


CONTEXT_KEYS = ("CODEX_APP_TOOLS_PIPE_PATH", "CODEX_MCP_NODE_PATH", "CODEX_CLI_PATH", "CODEX_THREAD_ID")


def remember_context(actor=None):
    context = {key: os.environ[key] for key in CONTEXT_KEYS if os.environ.get(key)}
    if actor:
        context["CODEX_THREAD_ID"] = actor
    if context.get("CODEX_APP_TOOLS_PIPE_PATH"):
        folder = data_home()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "desktop-context.json").write_text(json.dumps(context), encoding="utf-8")


def restore_context(force=False):
    try:
        context = json.loads((data_home() / "desktop-context.json").read_text(encoding="utf-8"))
        for key in CONTEXT_KEYS:
            if key in context and (force or not os.environ.get(key)):
                os.environ[key] = context[key]
    except (FileNotFoundError, ValueError):
        pass


def launch(actor=None):
    remember_context(actor)
    root = Path(__file__).resolve().parents[1]
    python = Path(sys.executable)
    if os.name == "nt" and python.with_name("pythonw.exe").exists():
        python = python.with_name("pythonw.exe")
    fd, receipt_name = tempfile.mkstemp(prefix="relic-window-", suffix=".json")
    os.close(fd)
    receipt = Path(receipt_name)
    env = dict(os.environ)
    if actor:
        env["CODEX_THREAD_ID"] = actor
    proc = subprocess.Popen([str(python), "-X", "utf8", str(root / "scripts/desktop.py"),
                             "--receipt", str(receipt)], env=env, cwd=root,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            try:
                result = json.loads(receipt.read_text(encoding="utf-8"))
                if result.get("status") == "error":
                    raise RuntimeError(result["error"])
                return dict(result, surface="native_window", launcher_path=str(root / "Open Relic.cmd"),
                            instruction="Relic Organization is open in its own desktop window. Select chats and a leader there.")
            except (ValueError, FileNotFoundError):
                pass
            if proc.poll() is not None:
                raise RuntimeError("Relic desktop window could not start. Run scripts/desktop.py to see diagnostics.")
            time.sleep(0.08)
        raise RuntimeError("Relic desktop window did not report readiness.")
    finally:
        receipt.unlink(missing_ok=True)
