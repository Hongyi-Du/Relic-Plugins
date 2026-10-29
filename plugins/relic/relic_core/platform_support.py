"""Small OS integration boundary shared by the installer, runners and browser App.

Discovery never sources shell startup files or starts a host session. macOS support
targets native Apple-silicon processes; desktop delivery is qualified separately.
"""
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import webbrowser


OVERRIDES = {"codex": "CODEX_CLI_PATH", "claude": "CLAUDE_CODE_EXECUTABLE",
             "node": "RELIC_NODE_PATH", "npm": "RELIC_NPM_PATH"}
NODE_MINIMUM = 22
SESSION_IDENTITY_ENV = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT", "CLAUDE_PLUGIN_ROOT",
                        "PLUGIN_ROOT", "CODEX_THREAD_ID", "CODEX_APP_TOOLS_PIPE_PATH", "RELIC_ACTOR",
                        "RELIC_ORG", "RELIC_MEMBER", "RELIC_ROLE", "RELIC_HARNESS", "RELIC_SEAT", "RELIC_SEAT_TOKEN")


def capabilities(probe=False):
    mac = sys.platform == "darwin"
    result = {"platform": sys.platform, "architecture": platform.machine(),
            "macos_supported": mac and platform.machine().lower() == "arm64",
            "codex_desktop_wake": os.name == "nt", "chatgpt_delivery": os.name == "nt",
            "claude_desktop_wake": not mac}
    if mac:
        from . import desktop, claude_desktop
        codex = desktop.transport_capability(probe=probe)
        claude = claude_desktop.transport_capability(probe=probe)
        result.update(codex_desktop_wake=bool(codex["available"]), chatgpt_delivery=bool(codex["available"]),
                      claude_desktop_wake=bool(claude["available"]), desktop_transport=codex, claude_desktop=claude)
    return result


def configure_capabilities(options):
    """Explicit local UI action; ordinary capability reads do not probe host IPC."""
    if not isinstance(options, dict) or set(options) - {"probe", "claude_desktop_enabled"}:
        raise ValueError("Unknown desktop capability setting.")
    for value in options.values():
        if not isinstance(value, bool):
            raise ValueError("Desktop capability settings must be booleans.")
    if "claude_desktop_enabled" in options:
        from . import claude_desktop
        claude_desktop.set_enabled(options["claude_desktop_enabled"])
    return capabilities(probe=options.get("probe", False))


def can_auto_deliver(harness, surface):
    if harness == "claude-chat":
        return False
    if harness == "chatgpt":
        return capabilities()["chatgpt_delivery"]
    if surface == "gui":
        return capabilities().get({"codex": "codex_desktop_wake",
                                   "claude-code": "claude_desktop_wake"}.get(harness, ""), False)
    return True


def require_supported_python():
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required.")
    if sys.platform == "darwin" and platform.machine().lower() != "arm64":
        raise RuntimeError("Relic on macOS requires native arm64 Python on Apple silicon. "
                           "Choose an arm64 Python installation and restart without Rosetta.")


def preferred_language():
    """The first macOS UI language; never change preferences or inspect unrelated settings."""
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(["/usr/bin/defaults", "read", "-g", "AppleLanguages"],
                                capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            match = re.search(r'(?<![A-Za-z])[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*(?![A-Za-z])', result.stdout)
            return match.group(0) if match else None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _executable(path):
    try:
        candidate = Path(path).expanduser()
        return str(candidate.absolute()) if candidate.is_file() and os.access(candidate, os.X_OK) else None
    except (OSError, ValueError):
        return None


def _mac_bin_dirs():
    home = Path.home()
    paths = [home / ".local/bin", Path("/opt/homebrew/bin"), home / ".volta/bin",
             home / ".fnm/current/bin", Path("/usr/local/bin")]
    # A Finder launch does not load nvm's shell function. Prefer the configured
    # executable/PATH above; otherwise use the newest installed numeric version.
    versions = home / ".nvm/versions/node"
    try:
        found = [p for p in versions.glob("v*") if re.fullmatch(r"v\d+\.\d+\.\d+", p.name)]
        paths += [p / "bin" for p in sorted(found, key=lambda p: tuple(map(int, p.name[1:].split("."))), reverse=True)]
    except OSError:
        pass
    return paths


def find_executable(name, explicit=None):
    """Resolve a program without a shell. An invalid explicit override fails closed."""
    override = explicit if explicit is not None else os.getenv(OVERRIDES.get(name, ""))
    if not override:
        try:
            home = Path(os.getenv("RELIC_HOME") or Path.home() / ".relic")
            settings = json.loads((home / "app/prefs.json").read_text(encoding="utf-8"))
            override = (settings.get("paths") or {}).get({"claude": "claude-code"}.get(name, name))
        except (OSError, ValueError, AttributeError):
            pass
    if override:
        return _executable(override)
    found = shutil.which(name)
    if found:
        return found
    if sys.platform == "darwin":
        for directory in _mac_bin_dirs():
            found = _executable(directory / name)
            if found:
                return found
    if os.name == "nt":
        candidates = []
        if name == "claude":
            candidates += [Path.home() / ".local/bin/claude.exe"]
        if name in ("claude", "codex", "npm"):
            if os.getenv("APPDATA"):
                candidates += [Path(os.environ["APPDATA"]) / "npm" / (name + ".cmd")]
        if name in ("node", "npm") and os.getenv("ProgramFiles"):
            candidates += [Path(os.environ["ProgramFiles"]) / "nodejs" / ("node.exe" if name == "node" else "npm.cmd")]
        if name == "codex" and os.getenv("LOCALAPPDATA"):
            root = Path(os.environ["LOCALAPPDATA"]) / "OpenAI/Codex/bin"
            try:
                matches = list(root.glob("**/codex.exe")) or list(root.glob("**/codex*.exe"))
                candidates = sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True) + candidates
            except OSError:
                pass
        for candidate in candidates:
            found = _executable(candidate)
            if found:
                return found
    return None


def runtime_env(env=None, executables=()):
    """Put selected executable directories on PATH for env-based CLI/npm shims."""
    result = dict(os.environ if env is None else env)
    paths = [str(Path(p).expanduser().absolute().parent) for p in executables if p]
    paths += result.get("PATH", os.defpath).split(os.pathsep)
    result["PATH"] = os.pathsep.join(dict.fromkeys(p for p in paths if p))
    return result


def node_runtime(executable=None):
    exe = executable or find_executable("node")
    result = {"path": exe, "version": None, "architecture": None, "supported": False}
    if not exe:
        result["problem"] = "Node.js 22 or newer is required for ACP members."
        return result
    try:
        proc = subprocess.run([exe, "-p", "JSON.stringify({version:process.versions.node,arch:process.arch})"],
                              capture_output=True, text=True, timeout=5,
                              creationflags=0x08000000 if os.name == "nt" else 0)
        data = json.loads(proc.stdout) if proc.returncode == 0 else {}
        if not isinstance(data, dict):
            data = {}
        result.update(version=data.get("version"), architecture=data.get("arch"))
        result["supported"] = (int(str(result["version"]).split(".")[0]) >= NODE_MINIMUM and
                               (sys.platform != "darwin" or result["architecture"] == "arm64"))
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        pass
    if not result["supported"]:
        result["problem"] = "ACP members require Node.js 22 or newer" + (
            " running natively as arm64 on macOS." if sys.platform == "darwin" else ".")
    return result


def browser_executable():
    candidates = [shutil.which(name) for name in ("msedge", "chrome")]
    if sys.platform == "darwin":
        for root in (Path("/Applications"), Path.home() / "Applications"):
            for app, binary in (("Microsoft Edge", "Microsoft Edge"), ("Google Chrome", "Google Chrome")):
                candidates.append(root / (app + ".app") / "Contents/MacOS" / binary)
    elif os.name == "nt":
        for variable in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
            if os.getenv(variable):
                root = Path(os.environ[variable])
                candidates += [root / "Microsoft/Edge/Application/msedge.exe",
                               root / "Google/Chrome/Application/chrome.exe"]
    return next((found for p in candidates if p for found in [_executable(p)] if found), None)


def open_external(target):
    """Request a native file/URL launch and surface launch failures to the caller."""
    target = str(target)
    if sys.platform == "darwin":
        command = ["/usr/bin/open", "--", target]
    elif os.name == "nt":
        os.startfile(target)
        return
    elif target.startswith(("http://", "https://")):
        if not webbrowser.open(target):
            raise RuntimeError("No browser could open the Relic App.")
        return
    else:
        command = ["xdg-open", target]
    proc = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or "The system could not open the requested item.")


def open_terminal(argv, cwd, env, directory):
    """Open a private, self-removing .command launcher in Terminal on macOS.

    Values stay in a mode-0700 file, not an AppleScript/Terminal command string.
    env -i prevents an existing Terminal process from leaking host identity into
    the new session. The launcher removes itself before starting the CLI.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="relic-terminal-", suffix=".command", dir=directory)
    try:
        os.fchmod(fd, 0o700)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write('#!/bin/sh\n/bin/rm -f -- "$0"\n')
            handle.write("cd -- %s || exit 1\n" % shlex.quote(str(cwd)))
            assignments = ["%s=%s" % (k, v) for k, v in env.items()]
            handle.write("exec /usr/bin/env -i -- %s\n" % shlex.join(assignments + list(argv)))
        proc = subprocess.run(["/usr/bin/open", "-a", "Terminal", name], capture_output=True, text=True, timeout=15)
        if proc.returncode:
            raise RuntimeError(proc.stderr.strip() or "Terminal could not open the session.")
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
