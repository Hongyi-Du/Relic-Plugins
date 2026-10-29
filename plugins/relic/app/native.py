"""Find installed native ACP programs without installing or changing their profiles.

Kimi Code and the DSH CLI are found through an App-selected path, an explicit
environment override, or the shared platform discovery (including macOS GUI
launches with a sparse PATH). DSH's Windows desktop executable can also run its
bundled CLI; other desktop distribution layouts have not been verified here.
"""
import os
from pathlib import Path
import re
import sys

from relic_core import platform_support


def _explicit_program(value, source):
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise RuntimeError("%s must name an executable file." % source)
    value = os.path.expandvars(os.path.expanduser(value.strip()))
    path = Path(value)
    # A bare program name is useful for environment overrides on every platform.
    # An existing path is still explicit, including a non-executable file: do not
    # silently use a different installation if that path cannot be executed.
    if path.name == value and not path.exists():
        found = platform_support.find_executable(value)
    else:
        found = platform_support.find_executable(path.name, explicit=value)
    if found:
        return found
    raise RuntimeError("%s does not name an existing executable: %s" % (source, value))


def _find(chosen, variable, command):
    if chosen:
        return _explicit_program(chosen, "The selected %s path" % command)
    if variable in os.environ:
        return _explicit_program(os.environ[variable], variable)
    return platform_support.find_executable(command)


def find_kimi(chosen=""):
    """Find Kimi Code: selected path, RELIC_KIMI_PATH, then platform discovery."""
    return _find(chosen, "RELIC_KIMI_PATH", "kimi")


def find_deepseek(chosen=""):
    """Find DSH: selected path, RELIC_DSH_PATH, then platform discovery.

    For the Windows desktop installation, select DeepSeek Harness.exe in the App
    or set RELIC_DSH_PATH to it. No installation directory is assumed.
    """
    return _find(chosen, "RELIC_DSH_PATH", "dsh")


def deepseek_launch(program):
    """Return (argv, extra_env) for an existing DSH CLI or Windows desktop app.

    RELIC_DSH_PROFILE defaults to acp. RELIC_DSH_PATCH optionally names a Cordis
    overlay file. Both are passed as separate arguments; this helper never edits
    profiles, chooses an account/model, or opens credential files.
    """
    executable = Path(_explicit_program(program, "DeepSeek Harness"))
    profile = os.getenv("RELIC_DSH_PROFILE", "acp")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", profile):
        raise RuntimeError("RELIC_DSH_PROFILE must be a profile name (letters, digits, dots, underscores or hyphens).")
    args = ["--profile", profile]
    if "RELIC_DSH_PATCH" in os.environ:
        value = os.environ["RELIC_DSH_PATCH"]
        if not value.strip() or "\0" in value:
            raise RuntimeError("RELIC_DSH_PATCH must name an existing overlay file.")
        patch = Path(os.path.expandvars(os.path.expanduser(value))).resolve()
        if not patch.is_file():
            raise RuntimeError("RELIC_DSH_PATCH does not name an existing overlay file: %s" % patch)
        args += ["--patch", str(patch)]

    # The CLI's own executable remains a CLI, even if the user keeps it alongside
    # a desktop installation. An explicitly selected wrapper is also a valid CLI.
    cli_name = executable.name.lower() in ("dsh", "dsh.exe", "dsh.cmd", "dsh.bat")
    archive = executable.parent / "resources" / "app.asar"
    desktop_name = executable.name.lower() == "deepseek harness.exe"
    if not cli_name and (desktop_name or archive.is_file()):
        if sys.platform != "win32":
            raise RuntimeError("This DSH desktop layout is supported on Windows only; select the dsh CLI on this platform.")
        if not archive.is_file():
            raise RuntimeError("The selected DSH desktop app is missing resources/app.asar; select the installed executable or the dsh CLI.")
        # Python cannot stat virtual files inside app.asar. Check the archive,
        # then let Electron resolve the bundled entry point.
        entry = archive / "dsh" / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
        return [str(executable), "--expose-internals", str(entry), *args], {"ELECTRON_RUN_AS_NODE": "1"}
    if executable.suffix.lower() == ".appimage" or any(p.suffix.lower() == ".app" for p in executable.parents):
        raise RuntimeError("This DSH desktop distribution has not been verified; select the dsh CLI instead.")
    return [str(executable), *args], {}
