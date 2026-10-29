"""Open the Relic App: start its local server when it is not running, then open its window.

    python scripts/relic_app.py               open the native App (it owns its server)
    python scripts/relic_app.py --no-window   only make sure the server runs
    python scripts/relic_app.py --serve       run the server in this process (what the background start runs)
    python scripts/relic_app.py --status      print JSON status without starting anything
    python scripts/relic_app.py --stop        stop this data folder's authenticated server
    python scripts/relic_app.py --restart     stop and restart, retaining its port when available

The window is the installed WinUI or SwiftUI application. There is no browser fallback.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core.store import data_home  # noqa: E402
from relic_core import platform_support  # noqa: E402

WINDOWS = os.name == "nt"
NO_WINDOW = platform_support.creation_flags()


def saved_info():
    try:
        info = json.loads((data_home() / "app.json").read_text(encoding="utf-8"))
        if isinstance(info, dict) and 0 < int(info.get("port", 0)) < 65536:
            return info
    except (OSError, ValueError, TypeError):
        pass
    return None


def endpoint(info, path, body=None, authenticated=True):
    headers = {"X-Relic-Token": info.get("token") or ""} if authenticated else {}
    data = None if body is None else json.dumps(body).encode("utf-8")
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request("http://127.0.0.1:%d%s" % (int(info["port"]), path), data=data, headers=headers)
    # A loopback lifecycle request must not pass through a configured HTTP proxy.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=2) as reply:
        return json.loads(reply.read().decode("utf-8"))


def verified_info():
    info = saved_info()
    if not info or not info.get("instance") or not info.get("token"):
        return None
    try:
        state = endpoint(info, "/api/lifecycle")
        if (state.get("app") == "relic" and state.get("instance") == info["instance"]
                and state.get("pid") == info.get("pid") and state.get("port") == int(info["port"])):
            return dict(info, state=state.get("state"))
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def running():
    info = verified_info()
    return info if info and info.get("state") == "running" else None


def unverified_server():
    """Recognize an older/mismatched Relic without acquiring authority to stop it."""
    info = saved_info()
    if info:
        try:
            return endpoint(info, "/api/ping", authenticated=False).get("app") == "relic"
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    return False


def status():
    info = verified_info()
    if info:
        return {"running": info["state"] == "running", "state": info["state"], "port": int(info["port"]),
                "pid": info["pid"], "version": info.get("version")}
    return {"running": False, "state": "unverified" if unverified_server() else "stopped"}


def preferred_port(port=0):
    if port:
        return port
    try:
        previous = json.loads((data_home() / "app-port.json").read_text(encoding="utf-8"))
        port = int(previous.get("port", 0))
        if 0 < port < 65536:
            return port
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    from app.web import DEFAULT_PORT
    return DEFAULT_PORT


def _start_server(port=0, timeout=20):
    info = running()
    if info:
        return info
    from app.web import LifecycleLock
    if unverified_server() and not verified_info():
        raise RuntimeError("A Relic App is responding but its ownership cannot be verified. "
                           "Close that older instance before starting this one; no process was killed.")
    # A preceding shutdown/start may still own the lease. The OS, not the saved PID, validates stale ownership.
    with LifecycleLock("app-server.lock", timeout=timeout):
        pass
    info = running()
    if info:
        return info
    port = preferred_port(port)
    python = Path(sys.executable)
    if WINDOWS and python.with_name("pythonw.exe").exists():
        python = python.with_name("pythonw.exe")
    log_dir = data_home() / "runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "relic-app.log", "a", encoding="utf-8") as log:
        process = subprocess.Popen([str(python), "-X", "utf8", str(Path(__file__).resolve()), "--serve", "--port", str(port)],
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True,
                                   start_new_session=not WINDOWS, creationflags=(NO_WINDOW | 0x00000200) if WINDOWS else 0)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        info = running()
        if info:
            return info
        if process.poll() is not None:
            # A concurrent direct --serve may have won the lifetime lease; allow it to publish its record.
            time.sleep(0.1)
            info = running()
            if info:
                return info
            break
        time.sleep(0.1)
    # This exact child was created above. A failed readiness check must not leave
    # it running or holding the log open; never terminate a PID from app.json.
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    raise RuntimeError("The Relic App server did not start; see %s" % (log_dir / "relic-app.log"))


def start_server(port=0, timeout=20):
    from app.web import LifecycleLock
    with LifecycleLock("app-control.lock", timeout=timeout):
        return _start_server(port, timeout)


def _stop_server(timeout=20):
    from app.web import LifecycleLock
    info = verified_info()
    if not info:
        if unverified_server():
            raise RuntimeError("The responding Relic App cannot be authenticated; no process was killed.")
        with LifecycleLock("app-server.lock", timeout=timeout):
            return {"stopped": False, "state": "stopped"}
    result = endpoint(info, "/api/shutdown", {"instance": info["instance"]})
    if result.get("instance") != info["instance"] or not result.get("stopping"):
        raise RuntimeError("The Relic App did not acknowledge shutdown.")
    # The lifetime lease is released only after ACP cleanup and metadata cleanup finish.
    with LifecycleLock("app-server.lock", timeout=timeout):
        pass
    return {"stopped": True, "state": "stopped", "port": int(info["port"])}


def stop_server(timeout=20):
    from app.web import LifecycleLock
    with LifecycleLock("app-control.lock", timeout=timeout):
        return _stop_server(timeout)


def restart_server(port=0, timeout=20):
    from app.web import LifecycleLock
    with LifecycleLock("app-control.lock", timeout=timeout):
        previous = _stop_server(timeout)
        return _start_server(port or previous.get("port", 0), timeout)


def native_executable():
    """Find a compiled native App; never treat the former shell/Finder launcher as one."""
    override = os.getenv("RELIC_NATIVE_APP")
    candidates = [Path(override)] if override else []
    if WINDOWS:
        candidates.extend([ROOT.parents[1] / "Relic.exe",
                           Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Programs/Relic/Relic.exe"])
    elif sys.platform == "darwin":
        candidates.extend(parent for parent in ROOT.parents if parent.suffix == ".app")
        candidates.extend([Path.home() / "Applications/Relic.app", Path("/Applications/Relic.app")])
    for candidate in candidates:
        executable = candidate / "Contents/MacOS/Relic" if candidate.suffix == ".app" else candidate
        try:
            with executable.open("rb") as stream:
                header = stream.read(4)
            if (WINDOWS and header[:2] == b"MZ") or (not WINDOWS and header in (
                    b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf")):
                return executable
        except OSError:
            continue
    raise RuntimeError("The native Relic App is not installed. Install the WinUI Windows package or the SwiftUI "
                       "Relic.app, or set RELIC_NATIVE_APP to its executable. No browser was opened.")


def open_native_app():
    executable = native_executable()
    bundle = executable.parent.parent.parent
    args = (["/usr/bin/open", str(bundle)] if not WINDOWS and bundle.suffix == ".app" else [str(executable)])
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True, start_new_session=not WINDOWS,
                     creationflags=platform_support.creation_flags(0x00000200))
    return str(bundle if not WINDOWS and bundle.suffix == ".app" else executable)

def main():
    parser = argparse.ArgumentParser()
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--serve", action="store_true")
    operation.add_argument("--stop", action="store_true")
    operation.add_argument("--restart", action="store_true")
    operation.add_argument("--status", action="store_true")
    parser.add_argument("--no-window", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    a = parser.parse_args()
    if not 0 <= a.port < 65536:
        parser.error("--port must be between 0 and 65535")
    platform_support.require_supported_python()
    from app import web
    if a.serve:
        web.main(preferred_port(a.port))
        return
    if a.status:
        print(json.dumps(status()))
        return
    if a.stop:
        print(json.dumps(stop_server()))
        return
    if not a.no_window and not a.restart and not a.port:
        print(open_native_app())
        return
    if not a.no_window:
        native_executable()  # fail before creating a headless server when no native App is installed
    info = restart_server(a.port) if a.restart else start_server(a.port)
    url = "http://127.0.0.1:%d/" % int(info["port"])
    if not a.no_window:
        open_native_app()
    print(url)


if __name__ == "__main__":
    main()
