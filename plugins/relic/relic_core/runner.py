"""Create member sessions on either harness, configured per seat, and send them turns the person writes.

Hongyi's request (2026-10-16): the plugin creates sessions with a chosen model and environment; the work itself is
given after the session is open. So creating a seat's session runs one short introduction turn (sit in the seat, read
the organization, wait), and every later turn carries text the person wrote in the Relic App.

A seat's config:
  harness      "codex" | "claude-code"
  surface      "cli" | "gui": where the person works with the session (a terminal, or the desktop app)
  model        model id or alias; empty = the harness default
  effort       reasoning effort; empty = default
  folder       the member's workspace
  environment  "local" (work in folder) | "worktree" (a git worktree of folder, one per member)
  permission   Claude Code: permission mode (auto, acceptEdits, plan, dontAsk)
               Codex: sandbox (workspace-write, read-only)
  env          extra environment variables {NAME: value}

Both harnesses keep their own safety checks on these turns: Claude Code's permission mode decides what runs, and Codex
stays in its sandbox. Since 2026-10-16 (the organization must run without anyone clicking) a Codex turn routes approval
requests to Codex's own automatic reviewer (approvalsReviewer "auto_review") instead of declining them, and the
member's own Relic tools (MCP server relic_org) are allowed; any other request that still reaches the runner is
declined and listed in the run state. On Windows the app-server runs the unelevated sandbox: the default elevated one
fails to start processes on this machine (CreateProcessWithLogonW 1385), which left woken members unable to read a file.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import __version__, platform_support
from .store import Store, data_home

WINDOWS = os.name == "nt"
NO_WINDOW = platform_support.creation_flags()
CLAUDE_MODES = ["auto", "acceptEdits", "plan", "dontAsk"]
CODEX_SANDBOXES = ["workspace-write", "read-only"]
EFFORTS = ["", "low", "medium", "high", "xhigh", "max"]
CLAUDE_MODELS = ["", "opus", "sonnet", "haiku", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1"]


def introduction(org, member):
    role = org["members"][member].get("role")
    return ("You now hold the seat '%s'%s in the Relic organization '%s' (%s). Call the Relic status tool once to see "
            "the members and the organization's protocols, say in one or two sentences what you see, and stop there. "
            "Do not start any other work: the person will give you your task in this session."
            % (member, (" (role: %s)" % role) if role else "", org["name"], org["id"]))


def default_config(harness="codex"):
    if harness in ("chatgpt", "claude-chat"):  # chat members (chat.py): no folder, model or permission to choose
        return {"harness": harness, "surface": "chat"}
    return {"harness": harness, "surface": "cli", "model": "", "effort": "", "folder": str(Path.home()),
            "environment": "local", "permission": "auto" if harness == "claude-code" else "workspace-write", "env": {}}


def checked_model(config):
    """Each harness runs its own vendor's models only: Claude models in Claude Code, Codex's models in Codex."""
    model = (config.get("model") or "").strip()
    claude_model = model in CLAUDE_MODELS or model.startswith("claude")
    if config.get("harness") == "claude-code" and model and not claude_model:
        raise RuntimeError("Claude Code members use Claude models: " + ", ".join(m for m in CLAUDE_MODELS if m))
    if config.get("harness") == "codex" and claude_model and model:
        raise RuntimeError("Codex members use the models Codex offers, not Claude models.")
    if config.get("harness") == "claude-code" and "ANTHROPIC_BASE_URL" in (config.get("env") or {}):
        raise RuntimeError("Claude Code members talk to Anthropic directly; remove ANTHROPIC_BASE_URL.")
    return model


def checked_permission(config):
    allowed = CLAUDE_MODES if config.get("harness") == "claude-code" else CODEX_SANDBOXES
    value = config.get("permission") or allowed[0]
    if value not in allowed:
        raise RuntimeError("permission must be one of: " + ", ".join(allowed))
    return value


def find_claude():
    return platform_support.find_executable("claude")


RELIC_MCP_SERVERS = ("relic_org",)
CODEX_REVIEWER = "auto_review"


def codex_overrides():
    """Config overrides for the app-server process only (the person's config.toml is untouched).
    RELIC_CODEX_WINDOWS_SANDBOX picks the Windows sandbox; empty keeps Codex's own choice."""
    if not WINDOWS:
        return []
    choice = os.getenv("RELIC_CODEX_WINDOWS_SANDBOX", "unelevated").strip()
    return ["-c", 'windows.sandbox="%s"' % choice] if choice else []


def find_codex():
    return platform_support.find_executable("codex")


def runs_dir():
    d = data_home() / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_path(org_id, member):
    return runs_dir() / ("%s-%s.json" % (org_id, member))


def _retry_locked(action, attempts=40):
    """Windows refuses to open a file while another process is replacing it (PermissionError); wait it out."""
    for _ in range(attempts - 1):
        try:
            return action()
        except PermissionError:
            time.sleep(0.05)
    return action()


def run_state(org_id, member):
    try:
        return json.loads(_retry_locked(lambda: run_path(org_id, member).read_text(encoding="utf-8")))
    except (FileNotFoundError, ValueError):
        return None


def write_state(org_id, member, state):
    path = run_path(org_id, member)
    tmp = path.with_suffix(".%d.tmp" % os.getpid())  # the window, the runner and dispatchers may write at once
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    _retry_locked(lambda: tmp.replace(path))


STALE_RUN = 24 * 3600        # a recorded runner pid older than this is not trusted (pids get reused)
LEGACY_STALE_RUN = 3 * 3600  # states written before runners recorded their pid


def pid_alive(pid):
    """Whether a process is still running, without signalling it (os.kill(pid, 0) sends CTRL_C on Windows)."""
    if not pid:
        return False
    if WINDOWS:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def is_running(org_id, member, now=None):
    """A turn is running while its runner process is alive; a runner that died leaves a "running" state behind."""
    state = run_state(org_id, member)
    if not state or state.get("status") != "running":
        return False
    age = (time.time() if now is None else now) - (state.get("started") or 0)
    if state.get("pid"):
        return age < STALE_RUN and pid_alive(state["pid"])
    return age < LEGACY_STALE_RUN


def workspace(config, member):
    """The directory the member works in; a git worktree per member when asked."""
    folder = Path(config.get("folder") or Path.home()).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    if config.get("environment") != "worktree":
        return str(folder)
    git = platform_support.find_executable("git")
    if not git:
        raise RuntimeError("Git was not found; creating a worktree requires Git.")
    top = subprocess.run([git, "-C", str(folder), "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                         creationflags=NO_WINDOW)
    if top.returncode != 0:
        raise RuntimeError("worktree needs a git repository: %s" % folder)
    repo = Path(top.stdout.strip())
    tree = repo.parent / ("%s-relic-%s" % (repo.name, member))
    if not tree.exists():
        branch = "relic/" + member
        exists = subprocess.run([git, "-C", str(repo), "rev-parse", "--verify", "--quiet", branch],
                                capture_output=True, creationflags=NO_WINDOW).returncode == 0
        args = [git, "-C", str(repo), "worktree", "add", str(tree)] + ([branch] if exists else ["-b", branch])
        made = subprocess.run(args, capture_output=True, text=True, creationflags=NO_WINDOW)
        if made.returncode != 0:
            raise RuntimeError(made.stderr.strip() or "git worktree add failed")
    return str(tree)


def session_env(config):
    env = {k: v for k, v in os.environ.items() if k not in platform_support.SESSION_IDENTITY_ENV}
    env.update({str(k): str(v) for k, v in (config.get("env") or {}).items()})
    return platform_support.runtime_env(env, [platform_support.find_executable("node")])


def parse_env(text):
    env = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def start_turn(org_id, member, prompt, new_session=False, open_after=False, wake_from=None, wake_hop=0):
    """Run one turn of a seat in the background: the introduction of a new session, text the person wrote, or an
    automatic wake-up for unread messages (wake_from names the senders, who get a receipt when the turn ends;
    wake_hop is the turn's depth in a chain of wake-ups, carried by the messages it sends)."""
    if is_running(org_id, member):
        raise RuntimeError("%s is still working on its current turn." % member)
    store = Store()
    org = store.get(org_id)
    seat = org["members"][member]
    config = store.seat_config(org_id, member, org)
    if config.get("harness") == "claude-code" and config.get("surface") == "gui":
        if new_session or not seat.get("carrier") or seat.get("harness") != "claude-code" or "/" in seat["carrier"]:
            raise RuntimeError("Claude GUI turns require an existing main Desktop seat; GUI bootstrap is unsupported.")
    if not platform_support.can_auto_deliver(config.get("harness"), config.get("surface")):
        raise RuntimeError("Automatic desktop delivery is unavailable for this member. "
                           "Use a CLI or App-managed member, or read messages with inbox in the existing session.")
    if seat.get("carrier") and not new_session:
        # one turn at a time per session, whichever of its seats it is for
        for other, name in store.seat_keys(seat["carrier"]):
            if (other, name) != (org_id, member) and is_running(other, name):
                raise RuntimeError("%s is still working on a turn for another organization it sits in." % member)
        store.set_focus(seat["carrier"], org_id)  # the turn is this organization's work: its protocols bind it
    if config.get("surface") == "acp":
        return app_turn(org_id, member, prompt, wake_from, wake_hop)
    fd, prompt_file = tempfile.mkstemp(prefix="relic-prompt-", suffix=".txt", dir=str(runs_dir()))
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(prompt)
    started = time.time()
    write_state(org_id, member, {"status": "running", "started": started, "prompt": prompt[:300],
                                 "new_session": new_session, "wake_from": list(wake_from or []),
                                 "wake_hop": int(wake_hop or 0)})
    python = Path(sys.executable)
    if WINDOWS and python.with_name("pythonw.exe").exists():
        python = python.with_name("pythonw.exe")
    script = Path(__file__).resolve().parents[1] / "scripts" / "relic_run.py"
    args = [str(python), "-X", "utf8", str(script), "--org", org_id, "--member", member, "--prompt-file", prompt_file]
    if new_session:
        args.append("--new")
    if open_after and not wake_from and not wake_hop:
        args.append("--open")
    if wake_from:
        args += ["--wake-from", ",".join(wake_from)]
    flags = (NO_WINDOW | 0x00000200) if WINDOWS else 0  # no console, own process group
    try:
        with open(runs_dir() / ("%s-%s.log" % (org_id, member)), "a", encoding="utf-8") as log:
            proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=flags,
                                    start_new_session=not WINDOWS)
    except Exception as error:
        # nothing started: replace the "running" state written above (no other turn was running, checked first)
        write_state(org_id, member, {"status": "failed", "started": started, "prompt": prompt[:300],
                                     "error": "could not start the runner: %s" % error, "finished": time.time()})
        try:
            os.unlink(prompt_file)
        except OSError:
            pass
        raise
    state = run_state(org_id, member) or {}
    if state.get("status") == "running" and not state.get("pid"):
        state["pid"] = proc.pid  # the runner records itself too; this covers the moment before it starts
        write_state(org_id, member, state)
    return True


def app_turn(org_id, member, prompt, wake_from=None, wake_hop=0):
    """A seat the Relic App runs through ACP (config surface "acp"): the App hosts its session, so it takes the turn.
    Raises when the App is not open; the wake-up is then retried with back-off like any failed start."""
    import urllib.request
    try:
        info = json.loads((data_home() / "app.json").read_text(encoding="utf-8"))
        request = urllib.request.Request(
            "http://127.0.0.1:%d/api/org/%s/turn" % (int(info["port"]), org_id),
            data=json.dumps({"member": member, "prompt": prompt, "wake_from": list(wake_from or []),
                             "wake_hop": int(wake_hop or 0)}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Relic-Token": info["token"]}, method="POST")
        with urllib.request.urlopen(request, timeout=10) as reply:
            json.loads(reply.read().decode("utf-8"))
    except Exception as error:
        raise RuntimeError("%s runs inside the Relic App, which is not open (%s)." % (member, error)) from None
    return True


def open_window():
    """Open the Relic App on the person's screen (scripts/relic_app.py starts its server when it is not running), as a
    process of its own: it outlives the session that asked for it."""
    python = Path(sys.executable)
    if WINDOWS and python.with_name("pythonw.exe").exists():
        python = python.with_name("pythonw.exe")
    script = Path(__file__).resolve().parents[1] / "scripts" / "relic_app.py"
    subprocess.Popen([str(python), "-X", "utf8", str(script)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=(NO_WINDOW | 0x00000200) if WINDOWS else 0,
                     start_new_session=not WINDOWS, close_fds=True)
    return str(script)


def open_command(config, session_id, harness, cwd):
    """The command that opens a session where the person works with it: a terminal (cli) or the desktop app (gui)."""
    surface = config.get("surface") or "cli"
    if harness == "codex":
        if surface == "gui":
            return ["codex-url", "codex://threads/" + session_id]
        exe = find_codex()
        if not exe:
            raise RuntimeError("Codex CLI not found")
        args = [exe, "resume", session_id, "-C", cwd, "-s", checked_permission(dict(config, harness="codex")),
                "-a", "on-request"]
        if checked_model(dict(config, harness="codex")):
            args += ["-m", config["model"]]
        if config.get("effort"):
            args += ["-c", "model_reasoning_effort=" + config["effort"]]
        return args + codex_overrides()
    exe = find_claude()
    if not exe:
        raise RuntimeError("Claude Code CLI not found")
    if surface == "gui":
        # Claude Code 2.1.285+: hands the session to the Claude desktop app (Code tab) and exits.
        return [exe, "--desktop", "--resume", session_id]
    args = [exe, "--resume", session_id, "--permission-mode", checked_permission(dict(config, harness="claude-code"))]
    if checked_model(dict(config, harness="claude-code")):
        args += ["--model", config["model"]]
    if config.get("effort"):
        args += ["--effort", config["effort"]]
    return args


def codex_desktop_exe():
    """Codex.exe of the Store app, for when the codex:// protocol is not registered (openai/codex#14686)."""
    found = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-AppxPackage OpenAI.Codex).InstallLocation"],
                           capture_output=True, text=True, creationflags=NO_WINDOW)
    root = Path(found.stdout.strip()) if found.returncode == 0 and found.stdout.strip() else None
    if root and root.is_dir():
        for exe in sorted(root.rglob("Codex.exe")):
            return str(exe)
    return None


def open_session(config, session_id, harness, cwd):
    """Open a seat's session for the person: in a new terminal window, or in the Claude / Codex desktop app."""
    args = open_command(config, session_id, harness, cwd)
    env = session_env(config)
    if args[0] == "codex-url":
        url = args[1]
        if WINDOWS:
            try:
                os.startfile(url)  # noqa: S606
            except OSError:
                exe = codex_desktop_exe()
                if not exe:
                    raise RuntimeError("Could not open the Codex desktop app; open the chat from its sidebar.")
                subprocess.Popen([exe, url], env=env, creationflags=platform_support.creation_flags())
        else:
            platform_support.open_external(url)
        return args
    if (config.get("surface") or "cli") == "gui":
        # --desktop redirects a launch; it cannot establish that a task ran there.
        proc = subprocess.run(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW, timeout=30)
        if proc.returncode:
            raise RuntimeError("Claude Desktop launch failed; no GUI turn was delivered.")
        return {"status": "launch_requested", "turn_delivered": False, "command": args}
    elif WINDOWS:
        # Opening a terminal is an explicit person action. The launcher itself
        # still must not allocate a surprise console when Relic runs via pythonw.
        terminal = shutil.which("wt.exe")
        if not terminal:
            raise RuntimeError("Windows Terminal was not found; open the session from your terminal with: "
                               + subprocess.list2cmdline(args))
        subprocess.Popen([terminal, "-w", "new", "--", *args], cwd=cwd, env=env,
                         creationflags=platform_support.creation_flags())
    elif sys.platform == "darwin":
        platform_support.open_terminal(args, cwd, env, runs_dir())
    else:
        terminal = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal")
        subprocess.Popen(([terminal, "--"] if terminal else []) + args, cwd=cwd, env=env,
                         creationflags=platform_support.creation_flags())
    return args


def codex_models():
    """Model ids the local Codex offers (for the picker); empty when Codex is unavailable."""
    exe = find_codex()
    if not exe:
        return []
    try:
        with CodexAppServer(exe) as server:
            result = server.request("model/list", {"limit": 100})
        return [m.get("model") or m.get("id") for m in result.get("data", []) if not m.get("hidden")]
    except Exception:
        return []


def elicitation_defaults(schema):
    """Content for an accepted form elicitation: each field's default, else yes / the first option / an empty value."""
    content = {}
    for name, spec in ((schema or {}).get("properties") or {}).items():
        if not isinstance(spec, dict):
            continue
        if spec.get("default") is not None:
            content[name] = spec["default"]
        elif spec.get("type") == "boolean":
            content[name] = True
        elif spec.get("enum"):
            content[name] = spec["enum"][0]
        elif spec.get("oneOf") and isinstance(spec["oneOf"][0], dict):
            content[name] = spec["oneOf"][0].get("const")
        elif spec.get("type") in ("number", "integer"):
            content[name] = spec.get("minimum", 0)
        elif spec.get("type") == "array":
            content[name] = []
        else:
            content[name] = ""
    return content


def _about(params):
    for key in ("command", "serverName", "reason", "message"):
        if params.get(key):
            return str(params[key])[:200]
    return ", ".join(sorted(params))[:200]


class CodexAppServer:
    """A minimal client for `codex app-server` (JSON-RPC over stdio)."""

    def __init__(self, exe, env=None, cwd=None, overrides=None):
        self.exe, self.env, self.cwd, self.seq = exe, env, cwd, 0
        self.overrides = codex_overrides() if overrides is None else list(overrides)
        self.proc = None
        self.notifications = []
        self.answered, self.declined = [], []

    def __enter__(self):
        self.proc = subprocess.Popen([self.exe, "app-server"] + self.overrides, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                     env=self.env, cwd=self.cwd, creationflags=NO_WINDOW)
        self.request("initialize", {"clientInfo": {"name": "relic", "title": "Relic", "version": __version__}})
        self.notify("initialized")
        return self

    def __exit__(self, *exc):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def notify(self, method, params=None):
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}}) + "\n")
        self.proc.stdin.flush()

    def _reply(self, rid, result=None, error=None):
        reply = {"jsonrpc": "2.0", "id": rid}
        reply.update({"error": error} if error else {"result": result})
        self.proc.stdin.write(json.dumps(reply) + "\n")
        self.proc.stdin.flush()

    def _answer(self, message):
        """A request from the app-server during a turn. The member's own Relic tools are allowed; anything else that
        reaches the runner (rather than Codex's automatic reviewer) is declined and listed for the run state."""
        method, params = message.get("method"), message.get("params") or {}
        if (method == "mcpServer/elicitation/request" and params.get("serverName") in RELIC_MCP_SERVERS
                and params.get("mode") != "url"):
            self.answered.append({"method": method, "server": params.get("serverName"), "action": "accept"})
            self._reply(message["id"], result={"action": "accept",
                                               "content": elicitation_defaults(params.get("requestedSchema"))})
            return
        self.declined.append({"method": method, "about": _about(params)})
        self._reply(message["id"], error={"code": -32000, "message": "declined: approve in the Codex app"})

    def read(self):
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("codex app-server closed")
        try:
            return json.loads(line)
        except ValueError:
            return {}

    def request(self, method, params):
        self.seq += 1
        rid = self.seq
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}) + "\n")
        self.proc.stdin.flush()
        while True:
            message = self.read()
            if message.get("id") == rid and "method" not in message:
                if "error" in message:
                    raise RuntimeError("%s: %s" % (method, message["error"].get("message")))
                return message.get("result", {})
            if "method" in message and "id" in message:
                self._answer(message)
            elif "method" in message:
                self.notifications.append(message)

    def wait_turn(self, thread_id):
        pending, self.notifications = self.notifications, []
        while True:
            message = pending.pop(0) if pending else self.read()
            if "method" in message and "id" in message:
                self._answer(message)
                continue
            self.notifications.append(message)  # item/completed etc., read after the turn
            params = message.get("params") or {}
            if message.get("method") == "turn/completed" and params.get("threadId") == thread_id:
                return params.get("turn") or {}
