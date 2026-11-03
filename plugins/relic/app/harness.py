"""The coding harnesses the Relic App runs through ACP, how to start each one, and how the App brings Relic into it.

The App is the bridge: every session it runs gets Relic from the App itself, whatever is installed in the harness.
  * Claude Code loads this plugin folder for the session (the adapter's _meta.claudeCode.options.plugins, i.e.
    --plugin-dir): the Relic MCP server, hooks, skill and member agent, exactly as an installed plugin. A Relic plugin
    installed in Claude Code is switched off in that session, so nothing runs twice.
  * Every other harness gets the Relic MCP server in session/new (relic_server, named relic_org like Codex's own
    entry, so tool names contain relic_org__ everywhere). Its environment names the seat (RELIC_SEAT and the seat
    token, relic_core.api.seat_actor), so calls come from the seat's carrier without Relic hooks. A Codex that has the
    Relic plugin enabled already gives its sessions that server (host_plugin), so the App adds none. Where a session
    has no Relic hooks, the App checks the organization's strong protocols when the session asks for permission and
    records the session's tool calls as activity (app/hub.py).

Adding a harness is one entry in HARNESSES:
  title, vendor     shown in the App
  package | command how to start its ACP agent: an npm ACP adapter installed under ~/.relic/acp (package), or a
                    program that speaks ACP itself (command: a function finding it; args: its ACP arguments)
  launch            optional function taking that program and returning (argv, extra env), for a native launcher
  program           a function finding the harness program on this computer (shown in settings)
  env               a function returning extra environment variables (raises RuntimeError naming what is missing)
  actor             the session's Relic actor from its ACP session id: "<harness id>:" + id for new harnesses
  default_mode      the ACP session mode new members start in ("" keeps the agent's default)
  relic             "plugin" (load this plugin folder, Claude Code only) or "mcp" (the Relic MCP server)
  hooks             whether its sessions run the Relic hooks (default: only with relic "plugin"); without them the
                    App checks protocols at permission requests, records activity and closes turns (has_hooks)
  host_plugin       for a harness that can have the Relic plugin installed itself: a function returning
                    (plugin enabled, hooks trusted); then the plugin serves the session and decides has_hooks
LATER lists harnesses in the ACP registry that are not entries yet, with the command that starts each one.

A harness also decides a session's Relic identity (actor): Claude Code uses its session id, Codex "codex:" + its thread
id, so hooks, transcripts and wake-ups find the session.
"""
import json
import hashlib
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from relic_core import i18n, runner, platform_support
from relic_core.store import data_home

from . import native

PLUGIN_ROOT = Path(__file__).resolve().parents[1]  # the Relic plugin folder this App runs from
# Never passed on to a session the App runs: they would make it look like the session that started the App (a Codex
# thread, a Claude Code session, a plugin hook) or like another seat.
INHERITED = platform_support.SESSION_IDENTITY_ENV
# What a Relic MCP server started for a session needs from the environment (a stdio server may get nothing else).
SERVER_ENV = ("PATH", "PATHEXT", "SYSTEMROOT", "SystemRoot", "WINDIR", "COMSPEC", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
              "HOME", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "TEMP", "TMP", "TMPDIR", "LANG", "USERNAME", "USER",
              "CODEX_HOME", "CLAUDE_CONFIG_DIR", "RELIC_MAX_WAIT", "RELIC_CODEX_WINDOWS_SANDBOX", "PYTHONUTF8")

REGISTRY_URL = "https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json"
ADAPTER_LOCK = Path(__file__).resolve().parent / "adapters"
LOCKED_PACKAGES = ("@agentclientprotocol/claude-agent-acp", "@agentclientprotocol/codex-acp")
_INSTALL_LOCK = threading.Lock()


def acp_home():
    return Path(os.getenv("RELIC_ACP_HOME") or data_home() / "acp")


def locked_home():
    digest = hashlib.sha256((ADAPTER_LOCK / "package-lock.json").read_bytes()).hexdigest()[:16]
    return acp_home() / "adapters" / digest


def _package_entry(package):
    suffix = Path("node_modules") / Path(*package.split("/")) / "dist" / "index.js"
    locked = locked_home() / suffix if package in LOCKED_PACKAGES else None
    return locked if locked and locked.is_file() and _locked_ready() else acp_home() / suffix


def _locked_ready():
    home = locked_home()
    try:
        return (home / ".relic-ready").read_text().strip() == home.name and _locked_contents_valid(home)
    except (OSError, ValueError):
        return False


def _locked_contents_valid(home):
    try:
        expected = json.loads((ADAPTER_LOCK / "package.json").read_text())["dependencies"]
        for package, version in expected.items():
            folder = home / "node_modules" / Path(*package.split("/"))
            if not (folder / "dist/index.js").is_file() or json.loads((folder / "package.json").read_text())["version"] != version:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def chosen_path(harness, existing=True):
    """A program path the person set in the App's settings, if it still exists."""
    try:
        from . import prefs
        path = (prefs.load().get("paths") or {}).get(harness) or ""
    except Exception:
        path = ""
    return path if path and (not existing or Path(path).is_file()) else ""


def claude_program():
    return chosen_path("claude-code") or runner.find_claude()


def codex_program():
    return chosen_path("codex") or runner.find_codex()


def kimi_program():
    return native.find_kimi(chosen_path("kimi-code", existing=False))


def deepseek_program():
    return native.find_deepseek(chosen_path("deepseek-harness", existing=False))


def _claude_env():
    exe = claude_program()
    if not exe or not exe.lower().endswith(".exe") and os.name == "nt":
        raise RuntimeError("Claude Code was not found on this computer. Install Claude Code or choose its executable in Settings.")
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


def codex_relic_plugin():
    """The Relic plugin as Codex has it: (enabled, hooks trusted), from ~/.codex/config.toml. With it enabled, a Codex
    session already has the Relic MCP server (relic_org) from the plugin, so the App gives it none of its own: two
    servers of that name would give the session every Relic tool twice."""
    try:
        import tomllib
        with open(codex_home() / "config.toml", "rb") as handle:
            config = tomllib.load(handle)
    except Exception:
        return False, False
    plugins = config.get("plugins") or {}
    enabled = any(isinstance(v, dict) and k.split("@", 1)[0] == "relic" and v.get("enabled", True)
                  for k, v in plugins.items())
    state = ((config.get("hooks") or {}).get("state") or {}) if isinstance(config.get("hooks"), dict) else {}
    trusted = any(k.split("@", 1)[0] == "relic" and ":pre_tool_use:" in k for k in state)
    hooks_on = (config.get("features") or {}).get("codex_hooks", True)
    return enabled, bool(enabled and trusted and hooks_on)


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
        "program": claude_program, "env": _claude_env, "actor": lambda sid: sid, "relic": "plugin",
        "default_mode": "auto", "modes_note": "auto: Claude decides permissions itself",
    },
    "codex": {
        "title": "Codex", "vendor": "OpenAI", "package": "@agentclientprotocol/codex-acp@2.3.0",
        "program": codex_program, "env": _codex_env, "actor": lambda sid: "codex:" + sid, "relic": "mcp",
        "host_plugin": codex_relic_plugin, "default_mode": _codex_mode,
        "modes_note": "follows sandbox_mode in your Codex config",
    },
    "kimi-code": {
        "title": "Kimi Code", "vendor": "Moonshot AI", "command": kimi_program, "args": ["acp"],
        "actor": lambda sid: "kimi-code:" + sid, "relic": "mcp", "default_mode": "",
    },
    "deepseek-harness": {
        "title": "DeepSeek Harness", "vendor": "DeepSeek", "command": deepseek_program,
        "launch": native.deepseek_launch,
        "actor": lambda sid: "deepseek-harness:" + sid, "relic": "mcp", "default_mode": "",
    },
}


# ---------------------------------------------------------------- how the App brings Relic into a session
def claude_home():
    return Path(os.getenv("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def installed_relic_plugins():
    """The Relic plugins installed in Claude Code ("relic@<marketplace>"). Sessions the App runs load this plugin
    folder instead, so these are switched off there: one Relic server and one set of hooks per session."""
    found = set()
    try:
        enabled = json.loads((claude_home() / "settings.json").read_text(encoding="utf-8")).get("enabledPlugins") or {}
        found.update(enabled)
    except (OSError, ValueError, AttributeError):
        pass
    try:
        data = json.loads((claude_home() / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        found.update((data.get("plugins") if isinstance(data.get("plugins"), dict) else data) or {})
    except (OSError, ValueError, AttributeError):
        pass
    return sorted(k for k in found if isinstance(k, str) and k.split("@", 1)[0] == "relic")


def seat_env(org_id, member, token):
    """The environment naming the seat a session holds (relic_core.api.seat_actor)."""
    return {"RELIC_SEAT": "%s/%s" % (org_id, member), "RELIC_SEAT_TOKEN": token, "RELIC_HOME": str(data_home())}


def python_program():
    """The Python that runs this App, as a console program (a stdio server needs no window)."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").is_file():
        return str(exe.parent / "python.exe")
    return str(exe)


def relic_server(org_id, member, token):
    """The Relic MCP server for one session the App runs, as an ACP McpServer (stdio). Named relic_org, as in Codex's
    own configuration, so its tools are mcp__relic_org__* and the hooks and protocols recognise them."""
    env = {k: os.environ[k] for k in SERVER_ENV if os.environ.get(k)}
    env.update(seat_env(org_id, member, token))
    # an inbox wait must end before the harness gives up on the call: Codex allows an MCP call 60 s unless its own
    # configuration says otherwise, and ACP cannot pass that setting
    try:
        wait = min(int(env.get("RELIC_MAX_WAIT") or 50), 50)
    except ValueError:
        wait = 50
    env["RELIC_MAX_WAIT"] = str(wait)
    return {"name": "relic_org", "command": python_program(),
            "args": ["-X", "utf8", str(PLUGIN_ROOT / "server.py")],
            "env": [{"name": k, "value": v} for k, v in env.items()]}


def relic_for(harness, org_id, member, token):
    """(mcpServers, _meta) for session/new, session/resume and session/load: how this session gets Relic."""
    spec = HARNESSES[harness]
    if spec.get("relic") == "plugin":
        options = {"plugins": [{"type": "local", "path": str(PLUGIN_ROOT)}], "env": seat_env(org_id, member, token)}
        installed = installed_relic_plugins()
        if installed:
            options["settings"] = {"enabledPlugins": {key: False for key in installed}}
        return [], {"claudeCode": {"options": options}}
    if spec.get("host_plugin") and spec["host_plugin"]()[0]:
        return [], None  # the harness's own Relic plugin serves the session (its server, its hooks)
    return [relic_server(org_id, member, token)], None


def has_hooks(harness):
    """Whether sessions of this harness run the Relic hooks, which check strong protocols before each tool call,
    record activity after it and close the turn. Claude Code does, from the plugin folder the App loads; Codex does
    when the Relic plugin is enabled in Codex and its hooks are trusted (host_plugin). For any other harness, and for
    Codex without them, the App does that work itself from the session's ACP tool calls (app/hub.py)."""
    spec = HARNESSES[harness]
    if spec.get("relic") == "plugin":
        return True
    if spec.get("host_plugin"):
        return spec["host_plugin"]()[1]
    return bool(spec.get("hooks", False))


def default_mode(harness):
    mode = HARNESSES[harness]["default_mode"]
    return (mode() if callable(mode) else mode) or ""

# In the ACP registry but not installed here yet; shown so the person knows what can join later.
LATER = [
    {"id": "codebuddy", "title": "CodeBuddy / WorkBuddy", "vendor": "Tencent", "launch": "npx @tencent-ai/codebuddy-code --acp"},
    {"id": "glm", "title": "GLM Agent", "vendor": "Zhipu AI", "launch": "npx glm-acp-agent"},
    {"id": "qwen-code", "title": "Qwen Code", "vendor": "Alibaba", "launch": "npx @qwen-code/qwen-code --acp"},
    {"id": "gemini", "title": "Gemini CLI", "vendor": "Google", "launch": "npx @google/gemini-cli --acp"},
    {"id": "opencode", "title": "OpenCode", "vendor": "anomalyco", "launch": "opencode acp"},
]


def node():
    return platform_support.find_executable("node")


def installed(harness):
    """Whether the App can start this harness's ACP agent: its adapter is installed, or its own program is found."""
    spec = HARNESSES.get(harness)
    if not spec:
        return False
    if spec.get("package"):
        return _package_entry(spec["package"].rsplit("@", 1)[0]).is_file()
    return bool(spec["command"]())


def launch(harness, extra_env=None):
    """(argv, env) that start the harness's ACP agent; raises RuntimeError with what is missing. extra_env names the
    seat the session will hold (seat_env); nothing that names another session or seat is passed on (INHERITED)."""
    spec = HARNESSES.get(harness)
    if not spec:
        raise RuntimeError("Unknown harness %s." % harness)
    native_env = {}
    if spec.get("package"):
        entry = _package_entry(spec["package"].rsplit("@", 1)[0])
        if not entry.is_file():
            raise RuntimeError("The ACP adapter for %s is not installed (npm install --prefix %s --omit=optional %s)."
                               % (spec["title"], acp_home(), spec["package"]))
        exe = node()
        if not exe:
            raise RuntimeError("Node.js 22 or newer was not found; the ACP adapters need it.")
        runtime = platform_support.node_runtime(exe)
        if not runtime["supported"]:
            raise RuntimeError(runtime["problem"])
        argv = [exe, str(entry)]
    else:
        program = spec["command"]()
        if not program:
            raise RuntimeError("%s was not found on this computer. Install it first." % spec["title"])
        if spec.get("launch"):
            argv, native_env = spec["launch"](program)
        else:
            argv = [program] + list(spec.get("args") or [])
    env = {k: v for k, v in os.environ.items() if k not in INHERITED}
    env.update(spec["env"]() if spec.get("env") else {})
    env.update(native_env)
    env.update(extra_env or {})
    return argv, platform_support.runtime_env(env, [node(), argv[0]])


def actor_for(harness, session_id):
    return HARNESSES[harness]["actor"](session_id)


def program(harness):
    finder = HARNESSES[harness].get("program") or HARNESSES[harness].get("command")
    return (finder() if finder else "") or ""


def adapter_version(harness):
    if not HARNESSES[harness].get("package"):
        return ""
    package = HARNESSES[harness]["package"].rsplit("@", 1)[0]
    try:
        manifest = _package_entry(package).parents[1] / "package.json"
        return json.loads(manifest.read_text(encoding="utf-8")).get("version") or ""
    except (OSError, ValueError):
        return ""


def install_command(harness):
    if HARNESSES[harness]["package"].rsplit("@", 1)[0] in LOCKED_PACKAGES:
        return ["npm", "ci", "--prefix", str(locked_home()), "--ignore-scripts", "--omit=optional", "--no-audit", "--no-fund"]
    return ["npm", "install", "--prefix", str(acp_home()), "--omit=optional", "--no-audit", "--no-fund",
            HARNESSES[harness]["package"]]


def install(harness, log, processes=None):
    """Install a harness's ACP adapter with npm; `log` gets each output line. Returns npm's exit code."""
    if not HARNESSES[harness].get("package"):
        log(i18n.t("harness.native_acp"))
        return 1
    with _INSTALL_LOCK:
        return _install(harness, log, processes)


def _install(harness, log, processes):
    runtime = platform_support.node_runtime(node())
    if not runtime["supported"]:
        log(i18n.t("harness.need_node") if not runtime["path"] else runtime["problem"])
        return 1
    npm = platform_support.find_executable("npm")
    if not npm:
        log(i18n.t("harness.need_npm"))
        return 1
    command = install_command(harness)
    if command[1] == "ci":
        destination = locked_home()
        if _locked_ready():
            log("The pinned ACP adapters are already installed.")
            return 0
        destination.mkdir(parents=True, exist_ok=True)
        (destination / ".relic-ready").unlink(missing_ok=True)
        for name in ("package.json", "package-lock.json"):
            shutil.copyfile(ADAPTER_LOCK / name, destination / name)
    else:
        acp_home().mkdir(parents=True, exist_ok=True)
    spawn = processes.popen if processes is not None else subprocess.Popen
    proc = spawn([npm] + command[1:], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                            creationflags=runner.NO_WINDOW, env=platform_support.runtime_env(executables=[runtime["path"], npm]))
    try:
        for line in proc.stdout:
            if line.strip():
                log(line.rstrip())
        result = proc.wait()
        if result == 0 and command[1] == "ci":
            if not _locked_contents_valid(destination):
                log("npm finished without a complete pinned adapter pair; installation is not ready.")
                return 1
            (destination / ".relic-ready").write_text(destination.name + "\n")
        return result
    finally:
        if processes is not None:
            processes.release(proc)


def catalog():
    """Every harness with what it needs: the ACP adapter, the program it drives, Node.js."""
    out = []
    runtime = platform_support.node_runtime(node())
    for key, spec in HARNESSES.items():
        found, adapter = "", False
        try:
            found = program(key)
            adapter = installed(key)
            if spec.get("env"):
                spec["env"]()
            if found and spec.get("launch"):
                spec["launch"](found)
            problem = ""
        except RuntimeError as error:
            problem = str(error)
        if not problem and not adapter:
            problem = (i18n.t("harness.not_installed") if spec.get("package")
                       else i18n.t("harness.not_found", title=spec["title"]))
        if not problem and spec.get("package") and not runtime["supported"]:
            problem = i18n.t("harness.need_node") if not runtime["path"] else runtime["problem"]
        known = remembered(key)
        out.append({"id": key, "title": spec["title"], "vendor": spec["vendor"], "available": not problem,
                    "problem": problem, "adapter": spec.get("package") or "", "adapter_installed": adapter,
                    "adapter_version": adapter_version(key) if adapter else "", "program": found,
                    "program_chosen": bool(chosen_path(key)), "node": runtime["path"] or "",
                    "node_version": runtime["version"], "node_architecture": runtime["architecture"], "mode": default_mode(key),
                    "note": spec.get("modes_note") or "",
                    "install": " ".join(install_command(key)) if spec.get("package") else "",
                    "models": known.get("models") or [], "efforts": known.get("efforts") or []})
    for item in LATER:
        out.append(dict(item, available=False, later=True))
    return out
