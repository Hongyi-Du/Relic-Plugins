"""Private pipe between either native client and the unchanged local HTTP engine.

One JSON readiness record is written to stdout. Keeping stdin open leases the
server; EOF (including a client crash) closes only the server this host created.
An already running, authenticated server is borrowed and never stopped here.
No window, shell, browser, or global installation is involved.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relic_app as launcher
from app.web import LifecycleLock
from relic_core.store import data_home
from relic_core.process import creation_flags


class NativeHost:
    def __init__(self):
        self.child = None
        self.info = None

    def start(self, timeout=25):
        with LifecycleLock("app-control.lock", timeout=timeout):
            self.info = launcher.running()
            if self.info:
                return dict(self.info, owned=False)
            if launcher.unverified_server():
                raise RuntimeError("Close the older Relic App before opening this version.")
            log_dir = data_home() / "runs"
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "relic-app.log").open("a", encoding="utf-8") as log:
                self.child = subprocess.Popen(
                    [sys.executable, "-X", "utf8", str(Path(launcher.__file__)), "--serve"],
                    stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                    creationflags=creation_flags(), start_new_session=os.name != "nt")
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                info = launcher.running()
                if info:
                    self.info = info
                    return dict(info, owned=info["pid"] == self.child.pid)
                if self.child.poll() is not None:
                    break
                time.sleep(0.1)
            raise RuntimeError("The Relic App server did not become ready; see runs/relic-app.log.")

    def close(self):
        child = self.child
        if child is None or child.poll() is not None:
            return
        # Compare the live authenticated instance, never kill a saved PID.
        try:
            current = launcher.running()
            if (self.info and current and current["pid"] == child.pid
                    and current["instance"] == self.info["instance"]):
                launcher.endpoint(current, "/api/shutdown", {"instance": current["instance"]})
                child.wait(timeout=20)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


def main():
    host = NativeHost()
    try:
        info = host.start()
        print(json.dumps(info), flush=True)
        sys.stdin.buffer.read()  # native client holds the write end, without polling
    finally:
        host.close()


if __name__ == "__main__":
    main()
