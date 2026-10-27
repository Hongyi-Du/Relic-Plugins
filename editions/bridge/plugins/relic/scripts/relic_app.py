"""Open the Relic App: start its local server when it is not running, then open its window.

    python scripts/relic_app.py               server (in the background) + window
    python scripts/relic_app.py --no-window   only make sure the server runs
    python scripts/relic_app.py --serve       run the server in this process (what the background start runs)

The window is the Relic App installed as an application (its Start menu shortcut, or the app Edge records as
installed for this address); otherwise Microsoft Edge (or Chrome) in app mode with its own profile under ~/.relic, so
it opens as a separate app window; without either browser the default browser opens the page.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relic_core.store import data_home  # noqa: E402

WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if WINDOWS else 0


def running():
    try:
        info = json.loads((data_home() / "app.json").read_text(encoding="utf-8"))
        with urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % int(info["port"]), timeout=2) as reply:
            if json.loads(reply.read().decode("utf-8")).get("app") == "relic":
                return info
    except Exception:
        return None
    return None


def start_server(port):
    python = Path(sys.executable)
    if WINDOWS and python.with_name("pythonw.exe").exists():
        python = python.with_name("pythonw.exe")
    log_dir = data_home() / "runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "relic-app.log", "a", encoding="utf-8") as log:
        subprocess.Popen([str(python), "-X", "utf8", str(Path(__file__).resolve()), "--serve", "--port", str(port)],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True, start_new_session=not WINDOWS,
                         creationflags=(NO_WINDOW | 0x00000200) if WINDOWS else 0)
    for _ in range(60):
        info = running()
        if info:
            return info
        time.sleep(0.25)
    raise SystemExit("The Relic App server did not start; see %s" % (log_dir / "relic-app.log"))


def browser():
    names = ["msedge", "chrome"]
    found = [shutil.which(n) for n in names]
    if WINDOWS:
        for base in (os.getenv("ProgramFiles(x86)"), os.getenv("ProgramFiles"), os.getenv("LOCALAPPDATA")):
            if base:
                found += [str(Path(base) / "Microsoft/Edge/Application/msedge.exe"),
                          str(Path(base) / "Google/Chrome/Application/chrome.exe")]
    return next((f for f in found if f and Path(f).is_file()), None)


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
        os.startfile(str(shortcut))
        return
    edge_app = installed_edge_app(int(url.split(":")[2].split("/")[0]))
    exe = browser()
    if edge_app and exe and Path(exe).name.lower() == "msedge.exe":
        profile, app_id = edge_app
        subprocess.Popen([exe, "--profile-directory=" + profile, "--app-id=" + app_id], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                         creationflags=0x00000200 if WINDOWS else 0)
        return
    if not exe:
        webbrowser.open(url)
        return
    profile = data_home() / "app-window"
    subprocess.Popen([exe, "--app=" + url, "--user-data-dir=" + str(profile), "--window-size=1480,940",
                      "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                     start_new_session=not WINDOWS, creationflags=0x00000200 if WINDOWS else 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--no-window", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    a = parser.parse_args()
    from app import web
    if a.serve:
        web.main(a.port or web.DEFAULT_PORT)
        return
    info = running() or start_server(a.port or web.DEFAULT_PORT)
    url = "http://127.0.0.1:%d/" % int(info["port"])
    if not a.no_window:
        open_window(url)
    print(url)


if __name__ == "__main__":
    main()
