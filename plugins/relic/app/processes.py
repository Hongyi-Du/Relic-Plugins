"""Ownership of short-lived App jobs such as naming, explanations and adapter installation.

Every POSIX job starts in its own session. Shutdown signals only those recorded
process groups; Windows tree cleanup targets a still-live Popen child. No PID
from persistent state, process-name search, or inherited process group is used.
"""
import os
import signal
import subprocess
import sys
import threading
import time


def group_has_live_members(pgid):
    """Inspect state, never command lines; None means absence could not be established."""
    try:
        result = subprocess.run(["/bin/ps", "-axo", "pgid=,stat="], capture_output=True, text=True,
                                timeout=1, env=dict(os.environ, LC_ALL="C"))
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode or not result.stdout.strip():
        return None
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2 or not fields[0].isdigit():
            return None
        if int(fields[0]) == pgid and not fields[1].startswith("Z"):
            return True
    return False


def signal_group(pgid, sig):
    """Signal an already-owned group; return False only when no live members remain.

    XNU's killpg1 excludes zombies and can return EPERM for a zombie-only group.
    Do not confuse that with denied permission to terminate a living process. A
    failed or incomplete state inspection preserves the original permission error.
    Callers must validate group ownership before entering this helper.
    """
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        return False
    except PermissionError:
        if sys.platform == "darwin" and group_has_live_members(pgid) is False:
            return False
        raise
    return True


class _Child:
    def __init__(self, process):
        self.process = process
        self.group = process.pid if os.name != "nt" else None
        self.lock = threading.Lock()
        self.closed = False

    def active(self):
        if self.group is None:
            return self.process.poll() is None
        return signal_group(self.group, 0)

    def signal_group(self, sig):
        if self.group is None or self.group <= 1 or self.group != self.process.pid or self.group == os.getpgrp():
            raise RuntimeError("The App does not own this process group.")
        return signal_group(self.group, sig)

    def wait(self, duration):
        deadline = time.monotonic() + duration
        while True:
            self.process.poll()  # reap our child even while descendants keep the group alive
            if not self.active():
                return True
            if time.monotonic() >= deadline:
                # Some POSIX kernels also report successful killpg(0) for
                # zombie-only groups. Do not wait for another process to reap them.
                return self.group is not None and group_has_live_members(self.group) is False
            time.sleep(min(0.02, max(0, deadline - time.monotonic())))

    def close(self):
        with self.lock:
            if self.closed:
                return
            if self.active():
                if self.group is not None:
                    self.signal_group(signal.SIGTERM)
                    if not self.wait(0.75):
                        self.signal_group(signal.SIGKILL)
                        if not self.wait(0.75):
                            raise RuntimeError("An App-owned process group did not stop within its shutdown deadline.")
                elif self.process.poll() is None:
                    try:
                        subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.process.pid)],
                                       capture_output=True, creationflags=0x08000000, timeout=2)
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                    if self.process.poll() is None:
                        self.process.kill()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                raise RuntimeError("An App-owned job did not stop within its shutdown deadline.") from None
            self.closed = True


class ProcessRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._children = {}
        self._closing = False

    def begin_shutdown(self):
        with self._lock:
            self._closing = True

    def popen(self, args, **kwargs):
        """Spawn and register a child atomically with respect to shutdown."""
        if os.name != "nt":
            kwargs["start_new_session"] = True
        with self._lock:
            if self._closing:
                raise RuntimeError("The Relic App is stopping; no new job can start.")
            process = subprocess.Popen(args, **kwargs)
            self._children[process] = _Child(process)
            return process

    def release(self, process):
        """Finish ownership after the caller has consumed its pipes; clean any surviving children."""
        with self._lock:
            child = self._children.get(process)
        if child is None:
            return
        child.close()
        with self._lock:
            self._children.pop(process, None)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()

    def run(self, args, *, input=None, capture_output=False, timeout=None, check=False, **kwargs):
        """The subprocess.run interface needed by App jobs, with owned-tree timeout cleanup."""
        if input is not None:
            if "stdin" in kwargs:
                raise ValueError("stdin and input arguments may not both be used")
            kwargs["stdin"] = subprocess.PIPE
        if capture_output:
            if "stdout" in kwargs or "stderr" in kwargs:
                raise ValueError("stdout and stderr arguments may not be used with capture_output")
            kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process = self.popen(args, **kwargs)
        try:
            try:
                stdout, stderr = process.communicate(input, timeout=timeout)
            except subprocess.TimeoutExpired as error:
                with self._lock:
                    child = self._children[process]
                child.close()
                try:
                    stdout, stderr = process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    stdout, stderr = error.output, error.stderr
                raise subprocess.TimeoutExpired(args, timeout, output=stdout, stderr=stderr) from None
            result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
            if check:
                result.check_returncode()
            return result
        finally:
            self.release(process)

    def shutdown(self):
        self.begin_shutdown()
        with self._lock:
            children = list(self._children.values())
        failures = []

        def close(child):
            try:
                child.close()
            except Exception as error:
                failures.append(error)

        closers = [threading.Thread(target=close, args=(child,), daemon=True) for child in children]
        for closer in closers:
            closer.start()
        deadline = time.monotonic() + 5
        for closer in closers:
            closer.join(max(0, deadline - time.monotonic()))
        if any(closer.is_alive() for closer in closers):
            raise RuntimeError("App-owned jobs exceeded the shutdown deadline.")
        if failures:
            raise RuntimeError("Could not stop an App-owned job: %s" % failures[0])
