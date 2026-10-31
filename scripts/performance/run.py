"""CI-only large-store responsiveness measurement for the real native client."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins" / "relic"))
from relic_core.process import creation_flags

UI_LIMIT_MS = 250
RSS_LIMIT = 1024 * 1024 * 1024
THREAD_LIMIT = 160


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def action_plan(fixture):
    plan = []
    def add(kind, **fields):
        plan.append(dict(id=f"action-{len(plan):04}", kind=kind, **fields))
    for org in fixture["orgs"]:
        add("group", org=org["id"])
        for member in org["members"]:
            add("private", org=org["id"], member=member)
        add("group", org=org["id"])
        for pane in ("overview", "workspace", "files"):
            add("pane", pane=pane)
    for name in ("file", "edit", "view", "help"):
        add("menu", name=name)
    for name in ("settings", "about", "neworg", "member"):
        add("dialog", name=name)
    for width, height in ((1440, 900), (1180, 800), (1024, 700), (960, 640), (1440, 900)):
        add("resize", width=width, height=height)
    for org in fixture["orgs"]:
        if org["group_messages"] >= 1000:
            add("scroll-history", org=org["id"], first_message_id=org["first_group_message_id"])
    return plan


def coverage_errors(receipt, manifest):
    actions = receipt.get("actions") or []
    actual = {str(action.get("id")): action for action in actions if action.get("id") is not None}
    errors = []
    for expected in manifest["plan"]:
        observed = actual.get(expected["id"])
        if not observed or observed.get("passed") is not True:
            errors.append(f"Incomplete production action: {expected}")
        elif expected["kind"] == "scroll-history":
            if not observed.get("history_complete") or int(observed.get("oldest_message_id") or 0) != expected["first_message_id"]:
                errors.append(f"History did not reach its actual first message: {expected['org']}")
    if float(receipt.get("random_seconds") or 0) < manifest["seconds"]:
        errors.append("The seeded monkey phase did not run for the full requested duration")
    if int(receipt.get("random_actions") or 0) < 1:
        errors.append("The seeded monkey phase did not execute an action")
    if receipt.get("seed") != manifest["seed"]:
        errors.append("The native interaction seed does not match its manifest")
    return errors


def resource_summary(samples):
    if not samples:
        return {"errors": ["No native process resource observations"]}
    peak_rss = max(s["rss_bytes"] for s in samples)
    peak_threads = max(s["threads"] for s in samples)
    errors = []
    if peak_rss > RSS_LIMIT:
        errors.append(f"Native RSS exceeded 1 GiB: {peak_rss}")
    if peak_threads > THREAD_LIMIT:
        errors.append(f"Native thread count exceeded {THREAD_LIMIT}: {peak_threads}")
    monkey = [s for s in samples if s.get("phase") == "monkey"]
    windows = []
    if monkey:
        origin = monkey[0]["elapsed_seconds"]
        # The first 60 monkey seconds permit caches to settle. Subsequent
        # complete 30-second windows retain their raw median values.
        for offset in (60, 90, 120):
            chunk = [s for s in monkey if origin + offset <= s["elapsed_seconds"] < origin + offset + 30]
            if len(chunk) >= 25:
                windows.append({"start_seconds": offset, "samples": len(chunk),
                                "rss_bytes": statistics.median(s["rss_bytes"] for s in chunk),
                                "threads": statistics.median(s["threads"] for s in chunk)})
    if len(windows) == 3:
        if all(windows[i + 1]["rss_bytes"] - windows[i]["rss_bytes"] > 32 * 1024 * 1024 for i in (0, 1)):
            errors.append("Native RSS keeps climbing across three warmed 30-second windows")
        if all(windows[i + 1]["threads"] - windows[i]["threads"] >= 4 for i in (0, 1)):
            errors.append("Native thread count keeps climbing across three warmed 30-second windows")
    return {"peak_rss_bytes": peak_rss, "peak_rss_mib": peak_rss / 1048576, "peak_threads": peak_threads,
            "cpu_seconds": samples[-1]["cpu_seconds"] - samples[0]["cpu_seconds"],
            "steady_windows": windows, "errors": errors}


class WindowsProbe:
    def __init__(self, pid):
        self.pid, self.handle = pid, 0
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        self.user.IsWindowVisible.argtypes = [ctypes.c_void_p]
        self.user.IsHungAppWindow.argtypes = [ctypes.c_void_p]
        self.user.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        self.user.SendMessageTimeoutW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
                                                 ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t)]
        self.user.SendMessageTimeoutW.restype = ctypes.c_size_t

    def sample(self):
        if not self.handle:
            def visit(handle, _):
                pid = ctypes.c_ulong()
                self.user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
                if pid.value == self.pid and self.user.IsWindowVisible(handle):
                    self.handle = handle
                    return False
                return True
            self.user.EnumWindows(self.callback_type(visit), 0)
        if not self.handle:
            return {"window_found": False}
        started = time.monotonic()
        result = ctypes.c_size_t()
        responded = bool(self.user.SendMessageTimeoutW(self.handle, 0, 0, 0, 0x0002 | 0x0020, UI_LIMIT_MS, ctypes.byref(result)))
        return {"window_found": True, "hwnd": int(self.handle), "not_responding": bool(self.user.IsHungAppWindow(self.handle)),
                "wm_null_responded": responded, "wm_null_ms": (time.monotonic() - started) * 1000}


def stop_owned(process):
    import psutil
    children = []
    if process.poll() is None:
        try:
            children = psutil.Process(process.pid).children(recursive=True)
        except psutil.Error:
            pass
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    for child in children:
        try:
            if child.is_running():
                child.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(children, timeout=3)
    for child in alive:
        try:
            child.kill()
        except psutil.Error:
            pass


def wait_json(path, process, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = read_json(path)
        if value is not None:
            return value
        if process.poll() is not None:
            raise RuntimeError(f"Owned process exited {process.returncode} before {path.name}")
        time.sleep(.05)
    raise TimeoutError(f"No {path.name} after {seconds} seconds")


def measure(exe, output, fixture, client, seconds, seed_value, mode):
    import psutil
    state = output / "native-state"
    state.mkdir()
    plan = action_plan(fixture)
    monkey = list(plan)
    random.Random(seed_value).shuffle(monkey)
    manifest = {"version": 1, "client": client, "output": str(output), "fixture": fixture,
                "seconds": seconds, "seed": seed_value, "max_ui_stall_ms": UI_LIMIT_MS,
                "plan": plan, "monkey": monkey}
    manifest_path = output / "manifest.json"
    atomic_json(manifest_path, manifest)
    env = dict(os.environ, RELIC_PERF_MANIFEST=str(manifest_path), RELIC_PERF_OUTPUT=str(output),
               RELIC_HOME=fixture["home"], RELIC_ENGINE_ROOT=str(ROOT), RELIC_PYTHON=sys.executable,
               RELIC_VISUAL_STATE_DIR=str(state), CLAUDE_CONFIG_DIR=str(output / "claude"),
               CODEX_HOME=str(output / "codex"), RELIC_LANG="zh-CN", TZ="UTC")
    env.pop("RELIC_VISUAL_MANIFEST", None)
    errors, samples, windows, heartbeats = [], [], [], []
    native_receipt = None
    with (output / "native.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(exe)], env=env, stdout=log, stderr=log, creationflags=creation_flags())
        started = time.monotonic()
        first_failure = None
        last_sample, last_window_probe = -1., -1.
        previous_sequence = None
        native = psutil.Process(process.pid)
        window_probe = WindowsProbe(process.pid) if client == "windows" else None
        try:
            ready = wait_json(output / "performance-ready.json", process)
            if ready.get("pid") != process.pid:
                raise RuntimeError("Native readiness identifies a different process")
            while time.monotonic() - started < seconds + 600:
                elapsed = time.monotonic() - started
                heartbeat = read_json(output / "heartbeat.json")
                native_receipt = read_json(output / "performance-complete.json")
                if heartbeat:
                    if heartbeat.get("sequence") != previous_sequence:
                        heartbeats.append(heartbeat)
                        previous_sequence = heartbeat.get("sequence")
                    maximum = float(heartbeat.get("max_ui_stall_ms") or 0)
                    if maximum > UI_LIMIT_MS and not any("UI thread" in e for e in errors):
                        errors.append(f"UI thread probe exceeded {UI_LIMIT_MS} ms: {maximum:.3f} ms during {heartbeat.get('action')}")
                    if time.time() * 1000 - float(heartbeat.get("unix_ms") or 0) > 2000 and native_receipt is None:
                        if "Native heartbeat stopped for more than 2 seconds" not in errors:
                            errors.append("Native heartbeat stopped for more than 2 seconds")
                elif elapsed > 5:
                    if "No native heartbeat after readiness" not in errors:
                        errors.append("No native heartbeat after readiness")
                if elapsed - last_sample >= 1 and process.poll() is None:
                    with native.oneshot():
                        cpu = native.cpu_times()
                        row = {"elapsed_seconds": elapsed, "rss_bytes": native.memory_info().rss,
                               "threads": native.num_threads(), "cpu_seconds": cpu.user + cpu.system,
                               "action": (heartbeat or {}).get("action", "startup")}
                    row["phase"] = "monkey" if row["action"].lower().startswith(("random", "monkey")) else "exhaustive"
                    children = []
                    for child in native.children(recursive=True):
                        try:
                            children.append({"pid": child.pid, "name": child.name(), "rss_bytes": child.memory_info().rss,
                                             "threads": child.num_threads()})
                        except psutil.Error:
                            pass
                    row["children"] = children
                    samples.append(row)
                    last_sample = elapsed
                    if row["rss_bytes"] > RSS_LIMIT and "Native RSS exceeded 1 GiB" not in errors:
                        errors.append("Native RSS exceeded 1 GiB")
                    if row["threads"] > THREAD_LIMIT and "Native thread count exceeded 160" not in errors:
                        errors.append("Native thread count exceeded 160")
                if window_probe and elapsed - last_window_probe >= 1:
                    observed = dict(elapsed_seconds=elapsed, **window_probe.sample())
                    windows.append(observed)
                    last_window_probe = elapsed
                    if observed.get("not_responding") or observed.get("wm_null_responded") is False:
                        if "Native window stopped responding" not in errors:
                            errors.append("Native window stopped responding")
                if native_receipt is not None:
                    break
                if process.poll() is not None:
                    errors.append(f"Native process exited {process.returncode} before its completion receipt")
                    break
                if errors:
                    first_failure = first_failure or time.monotonic()
                    if time.monotonic() - first_failure >= 2:
                        break
                time.sleep(.025)
            else:
                errors.append("Native exhaustive/monkey scenario exceeded its bounded runtime")
        except Exception as error:
            errors.append(str(error))
        finally:
            stop_owned(process)
    resources = resource_summary(samples)
    errors.extend(resources["errors"])
    if native_receipt:
        errors.extend(str(e) for e in native_receipt.get("errors", []))
        errors.extend(coverage_errors(native_receipt, manifest))
        if float(native_receipt.get("max_ui_stall_ms") or 0) > UI_LIMIT_MS:
            errors.append("Final native UI stall exceeds 250 ms")
    else:
        errors.append("The native scenario did not complete")
    worst = max([float(h.get("max_ui_stall_ms") or 0) for h in heartbeats]
                + [float((native_receipt or {}).get("max_ui_stall_ms") or 0)], default=0)
    report = {"version": 1, "commit": os.environ.get("GITHUB_SHA"), "client": client, "mode": mode,
              "fixture_counts": fixture["counts"], "fixture_seed": seed_value, "duration_seconds": seconds,
              "passed": not errors, "errors": list(dict.fromkeys(errors)), "worst_ui_stall_ms": worst,
              "resources": resources, "native_receipt": native_receipt, "limits": {
                  "ui_stall_ms": UI_LIMIT_MS, "peak_rss_bytes": RSS_LIMIT, "peak_threads": THREAD_LIMIT},
              "samples": samples, "heartbeats": heartbeats, "window_probes": windows}
    atomic_json(output / "responsiveness-report.json", report)
    print(json.dumps({k: report[k] for k in ("client", "mode", "passed", "worst_ui_stall_ms", "resources", "errors")}, ensure_ascii=False), flush=True)
    return report


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Native responsiveness measurement is CI-only; no app is launched locally.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=("windows", "macos"), required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--mode", choices=("baseline", "candidate"), default="candidate")
    args = parser.parse_args()
    if args.seconds < 180:
        raise SystemExit("The responsiveness monkey phase must run for at least 180 seconds")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    fixture_output = output / "fixture"
    with (output / "fixture.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen([sys.executable, "-X", "utf8", str(Path(__file__).with_name("fixture.py")),
                                   "--output", str(fixture_output), "--seed", str(args.seed)],
                                  stdout=log, stderr=log, creationflags=creation_flags())
        try:
            fixture = wait_json(fixture_output / "fixture.json", server, seconds=120)
            report = measure(args.exe.resolve(), output, fixture, args.client, args.seconds, args.seed, args.mode)
        finally:
            stop_owned(server)
    if not report["passed"]:
        raise SystemExit("Native responsiveness gate failed; see responsiveness-report.json")


if __name__ == "__main__":
    main()
