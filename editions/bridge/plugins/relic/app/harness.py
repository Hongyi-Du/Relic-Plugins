"""The coding harnesses the Relic App can embed through ACP, and how to start each one.

Claude Code and Codex run through the official ACP adapters installed under ~/.relic/acp (npm, without their bundled
binaries): the adapters drive the Claude Code and Codex programs already on this computer (CLAUDE_CODE_EXECUTABLE,
CODEX_PATH). Other harnesses from the ACP registry are listed with how to add them; the App starts only installed ones.

A harness also decides a session's Relic identity (actor), so the plugin's hooks and MCP server recognise the embedded
session as the seat's carrier: Claude Code uses its session id, Codex "codex:" + its thread id.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

from relic_core import runner
from relic_core.store import data_home

REGISTRY_URL = "https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json"


def acp_home():
    return Path(os.getenv("RELIC_ACP_HOME") or data_home() / "acp")


def _package_entry(package):
    return acp_home() / "node_modules" / Path(*package.split("/")) / "dist" / "index.js"


def chosen_path(harness):
    """A program path the person set in the App's settings, if it still exists."""
    try:
        from . import prefs
        path = (prefs.load().get("paths") or {}).get(harness) or ""
    except Exception:
        path = ""
    return path if path and Path(path).is_file() else ""


def claude_program():
    return chosen_path("claude-code") or runner.find_claude()


def codex_program():
    return chosen_path("codex") or runner.find_codex()


def _claude_env():
    exe = claude_program()
    if not exe or not exe.lower().endswith(".exe") and os.name == "nt":
        raise RuntimeError("Claude Code was not found on this computer (claude.exe). Install Claude Code first.")
    return {"CLAUDE_CODE_EXECUTABLE": exe}


def _codex_env():
    exe = codex_program()
    if not exe:
        raise RuntimeError("Codex was not found on this computer. Install the Codex app or CLI first.")
    return {"CODEX_PATH": _codex_program(exe)}


# ---------------------------------------------------------------- choices the harnesses reported
def _options_path():
    return acp_home() / "options.json"


def remembered(harness):
    """{"models": [...], "efforts": [...]} an embedded session of this harness reported last."""
    try:
        return (json.loads(_options_path().read_text(encoding="utf-8")) or {}).get(harness) or {}
    except (OSError, ValueError):
        return {}


def remember(harness, models=None, efforts=None):
    if not models and not efforts:
        return
    try:
        data = json.loads(_options_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    entry = data.setdefault(harness, {})
    if models:
        entry["models"] = [m for m in models if m]
    if efforts:
        entry["efforts"] = [e for e in efforts if e]
    try:
        _options_path().parent.mkdir(parents=True, exist_ok=True)
        _options_path().write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def _codex_program(exe):
    """The program the Codex adapter starts as `<program> app-server`. On Windows it gets the plugin runner's sandbox
    override (runner.codex_overrides, unelevated unless RELIC_CODEX_WINDOWS_SANDBOX says otherwise): the elevated
    sandbox fails to start commands on some machines (CreateProcessWithLogonW 1385), which leaves a member's shell
    commands hanging. The adapter only takes a program path, so a small .cmd file adds the override."""
    overrides = runner.codex_overrides()
    if os.name != "nt" or not overrides:
        return exe
    wrapper = acp_home() / "codex-app-server.cmd"
    text = "@echo off\r\n%s %%* %s\r\n" % (subprocess.list2cmdline([exe]), subprocess.list2cmdline(overrides))
    try:
        if not wrapper.is_file() or wrapper.read_text(encoding="utf-8") != text:
            wrapper.parent.mkdir(parents=True, exist_ok=True)
            wrapper.write_text(text, encoding="utf-8", newline="")
    except OSError:
        return exe
    return str(wrapper)


def codex_home():
    return Path(os.getenv("CODEX_HOME") or Path.home() / ".codex")


# Codex's sandbox_mode -> the Codex adapter's session mode
CODEX_MODES = {"danger-full-access": "agent-full-access", "workspace-write": "workspace-write", "read-only": "read-only"}


def _codex_mode():
    """The adapter mode matching the person's own Codex setting (sandbox_mode in config.toml), so an embedded Codex
    member may do what the person's Codex may do; None keeps the adapter's default (agent: automatic review)."""
    try:
        import tomllib
        with open(codex_home() / "config.toml", "rb") as handle:
            config = tomllib.load(handle)
    except Exception:
        return None
    return CODEX_MODES.get(config.get("sandbox_mode"))


HARNESSES = {
    "claude-code": {
        "title": "Claude Code", "vendor": "Anthropic", "package": "@agentclientprotocol/claude-agent-acp@0.97.0",
        "env": _claude_env, "actor": lambda sid: sid,
        "default_mode": "auto", "modes_note": "auto: Claude decides permissions itself",
    },
    "codex": {
        "title": "Codex", "vendor": "OpenAI", "package": "@agentclientprotocol/codex-acp@2.3.0",
        "env": _codex_env, "actor": lambda sid: "codex:" + sid,
        "default_mode": _codex_mode, "modes_note": "follows sandbox_mode in your Codex config",
    },
}


def default_mode(harness):
    mode = HARNESSES[harness]["default_mode"]
    return (mode() if callable(mode) else mode) or ""

# In the ACP registry but not installed here yet; shown so the person knows what can join later.
LATER = [
    {"id": "codebuddy", "title": "CodeBuddy / WorkBuddy", "vendor": "Tencent", "launch": "npx @tencent-ai/codebuddy-code --acp"},
    {"id": "glm", "title": "GLM Agent", "vendor": "Zhipu AI", "launch": "npx glm-acp-agent"},
    {"id": "kimi", "title": "Kimi CLI", "vendor": "Moonshot AI", "launch": "kimi acp"},
    {"id": "qwen-code", "title": "Qwen Code", "vendor": "Alibaba", "launch": "npx @qwen-code/qwen-code --acp"},
    {"id": "gemini", "title": "Gemini CLI", "vendor": "Google", "launch": "npx @google/gemini-cli --acp"},
    {"id": "opencode", "title": "OpenCode", "vendor": "anomalyco", "launch": "opencode acp"},
]


def node():
    found = shutil.which("node")
    if found:
        return found
    candidate = Path(os.getenv("ProgramFiles", r"C:\Program Files")) / "nodejs" / "node.exe"
    return str(candidate) if candidate.is_file() else None


def installed(harness):
    spec = HARNESSES.get(harness)
    if not spec:
        return False
    return _package_entry(spec["package"].rsplit("@", 1)[0]).is_file()


def launch(harness):
    """(argv, env) that start the harness's ACP agent; raises RuntimeError with what is missing."""
    spec = HARNESSES.get(harness)
    if not spec:
        raise RuntimeError("Unknown harness %s." % harness)
    entry = _package_entry(spec["package"].rsplit("@", 1)[0])
    if not entry.is_file():
        raise RuntimeError("The ACP adapter for %s is not installed (npm install --prefix %s --omit=optional %s)."
                           % (spec["title"], acp_home(), spec["package"]))
    exe = node()
    if not exe:
        raise RuntimeError("Node.js was not found; the ACP adapters need it.")
    env = dict(os.environ)
    env.update(spec["env"]())
    env.pop("CLAUDECODE", None)  # an embedded session is its own Claude Code session, not a child of this one
    return [exe, str(entry)], env


def actor_for(harness, session_id):
    return HARNESSES[harness]["actor"](session_id)


PROGRAMS = {"claude-code": claude_program, "codex": codex_program}


def adapter_version(harness):
    package = HARNESSES[harness]["package"].rsplit("@", 1)[0]
    try:
        manifest = acp_home() / "node_modules" / Path(*package.split("/")) / "package.json"
        return json.loads(manifest.read_text(encoding="utf-8")).get("version") or ""
    except (OSError, ValueError):
        return ""


def install_command(harness):
    return ["npm", "install", "--prefix", str(acp_home()), "--omit=optional", "--no-audit", "--no-fund",
            HARNESSES[harness]["package"]]


def install(harness, log):
    """Install a harness's ACP adapter with npm; `log` gets each output line. Returns npm's exit code."""
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        log("没找到 npm：先安装 Node.js（nodejs.org）。")
        return 1
    acp_home().mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([npm] + install_command(harness)[1:], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                            creationflags=runner.NO_WINDOW)
    for line in proc.stdout:
        if line.strip():
            log(line.rstrip())
    return proc.wait()


def catalog():
    """Every harness with what it needs: the ACP adapter, the program it drives, Node.js."""
    out = []
    for key, spec in HARNESSES.items():
        program = PROGRAMS[key]() or ""
        try:
            spec["env"]()
            problem = ""
        except RuntimeError as error:
            problem = str(error)
        adapter = installed(key)
        if not problem and not adapter:
            problem = "ACP 适配器还没安装。"
        if not problem and not node():
            problem = "没找到 Node.js，ACP 适配器需要它。"
        known = remembered(key)
        out.append({"id": key, "title": spec["title"], "vendor": spec["vendor"], "available": not problem,
                    "problem": problem, "adapter": spec["package"], "adapter_installed": adapter,
                    "adapter_version": adapter_version(key) if adapter else "", "program": program,
                    "program_chosen": bool(chosen_path(key)), "node": node() or "", "mode": default_mode(key),
                    "note": spec["modes_note"], "install": " ".join(install_command(key)),
                    "models": known.get("models") or [], "efforts": known.get("efforts") or []})
    for item in LATER:
        out.append(dict(item, available=False, later=True))
    return out
