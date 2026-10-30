"""Keep the actual CI UIA observer alive through the owner's diagnostic reads.

The original 75-second process deadline includes startup, extraction, the
handshake and exit. This changes no UIA measurement or parity requirement.
"""
import json
import os
from pathlib import Path
import subprocess
import time


def observe(executable, request_path, output_path, client_process, on_ready):
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("UI Automation observer is CI-only")
    request_path, output_path = Path(request_path), Path(output_path)
    request = json.loads(request_path.read_text(encoding="utf-8-sig"))
    if request.get("pid") != client_process.pid:
        raise ValueError("UIA request does not belong to the actual owned native process")
    ready = output_path.with_name(output_path.name + ".observer-ready.json")
    release = output_path.with_name(output_path.name + ".observer-release.json")
    if ready.exists() or release.exists():
        raise ValueError("Stale UIA observer handshake for " + str(request.get("case_id")))
    stdout_path = output_path.with_name(output_path.name + ".stdout.log")
    stderr_path = output_path.with_name(output_path.name + ".stderr.log")
    command = [str(executable), "--request", str(request_path), "--output", str(output_path),
               "--hold-ready", str(ready), "--hold-release", str(release)]
    deadline = time.monotonic() + 75
    process = None
    failure = None
    result = None
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        try:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
            while True:
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command, 75)
                if ready.exists():
                    receipt = json.loads(ready.read_text(encoding="utf-8-sig"))
                    if (receipt.get("case_id") != request.get("case_id")
                            or receipt.get("app_pid") != client_process.pid
                            or receipt.get("observer_pid") != process.pid
                            or type(receipt.get("exit_code")) is not int
                            or receipt["exit_code"] not in (0, 1)):
                        raise RuntimeError("UIA observer readiness is not bound to this scene and both actual processes")
                    if not output_path.exists():
                        raise RuntimeError("UIA observer became ready without its original measurement output")
                    if process.poll() is not None:
                        raise RuntimeError("UIA observer exited before the native owner could be observed while held")
                    on_ready(receipt, deadline)
                    if process.poll() is not None:
                        raise RuntimeError("UIA observer exited during the native owner's held observation")
                    break
                code = process.poll()
                if code is not None:
                    raise RuntimeError(f"UIA observer exited {code} without its readiness receipt")
                if client_process.poll() is not None:
                    raise RuntimeError("Native client exited before UIA observer readiness")
                time.sleep(.02)
        except BaseException as error:
            failure = error
        finally:
            if process is not None:
                # Release even a failed capture; never leave an owned observer
                # holding providers until a second, freshly restarted timeout.
                try:
                    temporary = release.with_suffix(".tmp")
                    temporary.write_text(json.dumps({"case_id": request["case_id"], "observer_pid": process.pid,
                        "action": "release", "status": "failed" if failure else "observed"}), encoding="utf-8")
                    temporary.replace(release)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(command, 75)
                    result = process.wait(timeout=remaining)
                except BaseException as error:
                    if failure is None:
                        failure = error
                    if process.poll() is None:
                        process.kill()
                    # Bounded reap after failure is cleanup, not capture time.
                    process.wait(timeout=10)
    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    if failure is not None:
        raise failure
    return subprocess.CompletedProcess(command, result, stdout_text, stderr_text)


def wait_native_probe_receipt(path, request, observer_pid, client_process, deadline):
    """Observe the native process's completed reads; no identity is inferred."""
    path = Path(path)
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError("Native provider observation exceeded the existing UIA process deadline")
        if path.exists():
            receipt = json.loads(path.read_text(encoding="utf-8-sig"))
            if (receipt.get("case_id") != request.get("case_id")
                    or receipt.get("app_pid") != client_process.pid
                    or receipt.get("observer_pid") != observer_pid
                    or receipt.get("status") != "observed"):
                raise RuntimeError("Native provider observation failed or is not bound to the held observer: " + str(receipt))
            return receipt
        if client_process.poll() is not None:
            raise RuntimeError("Native client exited without completing its held provider observation")
        time.sleep(.02)
