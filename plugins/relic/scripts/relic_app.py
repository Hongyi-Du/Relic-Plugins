"""Open the Relic App: start its local server when it is not running, then open its window.

    python scripts/relic_app.py               server (in the background) + window
    python scripts/relic_app.py --no-window   only make sure the server runs
    python scripts/relic_app.py --serve       run the server in this process (what the background start runs)
    python scripts/relic_app.py --status      print JSON status without starting anything
    python scripts/relic_app.py --stop        stop this data folder's authenticated server
    python scripts/relic_app.py --restart     stop and restart, retaining its port when available

The window is the Relic App installed as an application (its Start menu shortcut, or the app Edge records as
installed for this address); otherwise Microsoft Edge (or Chrome) in app mode with its own profile under ~/.relic, so
it opens as a separate app window; without either browser the default browser opens the page.
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


def browser():
    return platform_support.browser_executable()


def installed_shortcut():
    """The Start menu shortcut the browser made when the person installed the Relic App as an application, if any."""
    if not WINDOWS:
        return None
    menu = Path(os.getenv("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"
    for link in sorted(menu.rglob("Relic*.lnk")) if menu.is_dir() else []:
        try:
            data = link.read_bytes()
        except OSError:
            continue
        if "--app-id".encode("utf-16-le") in data or b"--app-id" in data:
            return link
    return None


def installed_edge_app(port):
    """(profile, app id) of the Relic App installed in Microsoft Edge for this port, read from Edge's own record of its
    installed web apps (Edge does not always make a Start menu shortcut). None when it is not installed."""
    if not WINDOWS:
        return None
    root = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft/Edge/User Data"
    start = ("http://127.0.0.1:%d/" % port).encode()
    for prefs in sorted(root.glob("*/Preferences")) if root.is_dir() else []:
        profile = prefs.parent
        for record in sorted((profile / "Sync Data" / "LevelDB").glob("*")):
            try:
                data = record.read_bytes()
            except OSError:
                continue
            for match in re.finditer(rb"web_apps-dt-([a-p]{32})", data):
                app_id = match.group(1).decode()
                # the record's start URL follows its key; an app removed since then has no resources left
                if start in data[match.end():match.end() + 80] and (profile / "Web Applications" / "Manifest Resources" / app_id).is_dir():
                    return profile.name, app_id
    return None


def open_window(url):
    shortcut = installed_shortcut()
    if shortcut:  # the installed application: its own window and title bar, no browser frame
        try:
            platform_support.open_external(str(shortcut))
            return
        except (OSError, RuntimeError):
            pass  # a stale installed shortcut must not prevent the page from opening
    edge_app = installed_edge_app(int(url.split(":")[2].split("/")[0]))
    exe = browser()
    if exe:
        if edge_app and Path(exe).name.lower() == "msedge.exe":
            profile, app_id = edge_app
            args = [exe, "--profile-directory=" + profile, "--app-id=" + app_id]
        else:
            profile = data_home() / "app-window"
            args = [exe, "--app=" + url, "--user-data-dir=" + str(profile), "--window-size=1480,940",
                    "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"]
        try:
            subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             close_fds=True, start_new_session=not WINDOWS,
                             creationflags=platform_support.creation_flags(0x00000200))
            return
        except OSError:
            pass  # the browser may have moved or been removed after discovery
    platform_support.open_external(url)


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
    info = restart_server(a.port) if a.restart else start_server(a.port)
    url = "http://127.0.0.1:%d/" % int(info["port"])
    if not a.no_window:
        open_window(url)
    print(url)


if __name__ == "__main__":
    main()
