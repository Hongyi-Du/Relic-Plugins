"""Check rules: a strong protocol's rule that runs a small judgment program its members wrote (effect "check").

A rule with effect "check" names the calls it judges like every rule (tools, and optionally path_glob, input_contains
and who it applies to) and carries:
  code       Python that uses the standard library only and defines check(call), returning
             {"decision": "allow" | "deny" | "review", "reason": "..."}
  examples   2 to 12 {"call": {...}, "expect": "allow" | "deny" | "review", "note"?}: at least one allow and one deny or
             review. Every one runs when the protocol is proposed and has to come out as expected.
  on_error   "allow" (the default) or "deny": what happens to the call when the program fails
The store (relic_core/store.py) records the code's sha256 when the protocol is proposed, runs the program before every
tool call the rule covers (Store.gate) and copies the protocol to the person, with its summary_for_person, when it takes
effect.

This module runs programs and looks at their code. A program runs in a process of its own: this Python with -I -S -X utf8
(isolated and without site-packages, so only the standard library can be imported), the code and the call on stdin as
JSON, at most TIMEOUT seconds and OUTPUT_CAP bytes of answer, a temporary working folder and almost no environment.
Whatever the program starts ends with the run (on Windows a job object, which also caps memory at MEMORY_CAP; elsewhere
its process group). That keeps a slow, noisy or crashing program away from the member's session. It is not a security
boundary: the program can use the whole standard library. That is why the members review its code and examples before
they vote, and why the person can retire the protocol at once.
"""
import ast
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TIMEOUT = 3.0           # seconds a program has for one call, its start included
OUTPUT_CAP = 8 * 1024   # bytes of answer read from a program; a program that writes more gives no answer
MEMORY_CAP = 512 * 1024 * 1024  # bytes of memory a program and what it starts may commit (Windows: a job object)
ERROR_CAP = 4 * 1024    # bytes of a program's error output kept (the start of a crash report)
CODE_MAX = 20000        # characters of code
INPUT_CLIP = 100000     # characters of one string in the input of a call (a Write can hold a whole file)
EXAMPLES = (2, 12)      # how many examples a check rule has
RECENT = 20             # the member's latest tool calls given with a call
REASON_MAX = 500        # characters of a reason
PARALLEL = 4            # programs run side by side (several rules on one call, a proposal's examples)
DECISIONS = ("allow", "deny", "review")
ON_ERROR = ("allow", "deny")
ERRORS = ("timeout", "raised", "load", "invalid", "crashed", "unavailable", "tampered")
WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if WINDOWS else 0

# Runs in the child: read {"code", "call"} from stdin, load the code, call check(call) and write one JSON answer:
# {"result": <what check returned>} or {"error": "load" | "raised" | "invalid", "detail": "..."}. What the program
# prints goes to stderr, so it cannot be taken for the answer.
RUNNER = """
import json, sys, traceback

answer_to = sys.stdout
sys.stdout = sys.stderr


def answer():
    task = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    space = {"__name__": "relic_check"}
    try:
        exec(compile(task["code"], "check.py", "exec"), space)
    except BaseException as error:
        return {"error": "load", "detail": "".join(traceback.format_exception_only(type(error), error)).strip()}
    check = space.get("check")
    if not callable(check):
        return {"error": "load", "detail": "the code defines no function check(call)"}
    try:
        return {"result": check(task["call"])}
    except BaseException as error:  # the traceback from the program's own lines on
        lines = traceback.format_exception(type(error), error, error.__traceback__.tb_next)
        return {"error": "raised", "detail": "".join(lines[-6:]).strip()}


try:
    text = json.dumps(answer(), ensure_ascii=False)
except BaseException as error:
    text = json.dumps({"error": "invalid", "detail": "check() returned something that is not JSON (%s)" % type(error).__name__})
answer_to.write(text)
answer_to.flush()
"""


def sha256(code):
    return hashlib.sha256(str(code or "").encode("utf-8")).hexdigest()


def python():
    """This Python as a console program (the Relic App may run under pythonw.exe, which has no standard streams)."""
    exe = Path(sys.executable or "python")
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").is_file():
        return str(exe.parent / "python.exe")
    return str(exe)


def problems(code):
    """Why code cannot be a check program, or None: empty or too long, a syntax error, an import from outside the
    standard library, no top-level check function."""
    if not isinstance(code, str) or not code.strip():
        return "code is empty: write Python that defines check(call)."
    if len(code) > CODE_MAX:
        return "code has %d characters; keep it under %d." % (len(code), CODE_MAX)
    try:
        tree = ast.parse(code, "check.py")
        compile(tree, "check.py", "exec")
    except SyntaxError as error:
        return "syntax error on line %s: %s." % (error.lineno, error.msg)
    except ValueError as error:  # null bytes, for one
        return "the code cannot be compiled: %s." % error
    outside = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                return "relative imports are not available: import from the standard library only."
            names = [node.module or ""]
        else:
            continue
        outside.update(top for top in (name.split(".")[0] for name in names) if top not in sys.stdlib_module_names)
    if outside:
        return "only the Python standard library is available; these are not part of it: %s." % ", ".join(sorted(outside))
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "check":
            return "check must be a plain function (def check(call)), not async."
        if isinstance(node, ast.FunctionDef) and node.name == "check":
            return None
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "check" for t in node.targets):
            return None
    return "the code defines no top-level function check(call)."


def verdict(result):
    """{"decision", "reason"} from what check() returned, or {"error": "invalid", "detail"} when it is not a decision:
    a dict whose decision is allow, deny or review, with a reason (text) that a deny or a review must have."""
    if not isinstance(result, dict):
        return {"error": "invalid", "detail": "check() must return a dict {\"decision\": ..., \"reason\": ...}; it "
                                              "returned %s" % type(result).__name__}
    decision = result.get("decision")
    if decision not in DECISIONS:
        return {"error": "invalid", "detail": "decision must be allow, deny or review; it was %s"
                                              % json.dumps(decision, ensure_ascii=False)[:80]}
    reason = result.get("reason")
    if reason is not None and not isinstance(reason, str):
        return {"error": "invalid", "detail": "reason must be text; it was %s" % type(reason).__name__}
    reason = " ".join((reason or "").split())[:REASON_MAX]
    if decision != "allow" and not reason:
        return {"error": "invalid", "detail": "a %s needs a reason: the member reads it to know what to do" % decision}
    return {"decision": decision, "reason": reason}


def _environment(folder):
    if WINDOWS:  # Python on Windows wants SYSTEMROOT; nothing else of the member's environment is passed on
        return {"SYSTEMROOT": os.environ.get("SYSTEMROOT") or "C:\\Windows", "TEMP": folder, "TMP": folder}
    return {"TMPDIR": folder}


def _feed(stream, data):
    try:
        stream.write(data)
        stream.close()
    except (OSError, ValueError):  # the program ended or closed its input
        pass


def _pump(stream, cap, chunks, proc=None, over=None):
    """Read a stream to its end, keeping its first `cap` bytes; with proc, stop the program once it writes more."""
    size = 0
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            if size < cap:
                chunks.append(chunk[:cap - size])
            size += len(chunk)
            if size > cap and proc is not None:
                over.set()
                _kill(proc)
    except (OSError, ValueError):
        pass


def _kill(proc):
    try:
        proc.kill()
    except OSError:
        pass


def _contain(proc):
    """Hold the program's process, and every process it starts, so that they all end with the run: on Windows a job
    object that is closed after the run (KILL_ON_JOB_CLOSE) and caps their memory (MEMORY_CAP); elsewhere the process
    group the program leads. Returns what _release takes; None when the system does not allow it."""
    if not WINDOWS:
        return ("group", proc.pid)
    try:
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", ctypes.c_uint64 * 6),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            return None
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x200  # KILL_ON_JOB_CLOSE | JOB_MEMORY
        limits.JobMemoryLimit = MEMORY_CAP
        if not (kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))  # extended limits
                and kernel.AssignProcessToJobObject(job, int(proc._handle))):
            kernel.CloseHandle(job)
            return None
        return ("job", (kernel, job))
    except Exception:  # an older Windows, a parent job that forbids it: the program's own process is still stopped
        return None


def _release(held):
    """End whatever the program started and left running."""
    if not held:
        return
    how, what = held
    try:
        if how == "job":
            what[0].CloseHandle(what[1])
        else:
            import signal
            os.killpg(what, signal.SIGKILL)
    except (OSError, AttributeError):  # nothing left to end
        pass


def run(code, call, timeout=None):
    """Run a check program on one call. {"decision", "reason"} as it answered, or {"error": kind, "detail": text}: kind
    is timeout, raised (check raised an exception), load (the code does not load), invalid (an answer that is not a
    decision, or too much output), crashed (the process ended without an answer) or unavailable (it could not start)."""
    timeout = TIMEOUT if timeout is None else float(timeout)
    try:
        task = json.dumps({"code": code, "call": call}, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        return {"error": "invalid", "detail": "the call cannot be passed as JSON: %s" % error}
    with tempfile.TemporaryDirectory(prefix="relic-check-", ignore_cleanup_errors=True) as folder:
        try:
            proc = subprocess.Popen([python(), "-I", "-S", "-X", "utf8", "-c", RUNNER], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=folder,
                                    env=_environment(folder), creationflags=NO_WINDOW, start_new_session=not WINDOWS)
        except OSError as error:
            return {"error": "unavailable", "detail": "the program could not start: %s" % error}
        held = _contain(proc)  # before the program gets its input, so nothing it starts escapes
        out, err, over = [], [], threading.Event()
        threads = [threading.Thread(target=_feed, args=(proc.stdin, task), daemon=True),
                   threading.Thread(target=_pump, args=(proc.stdout, OUTPUT_CAP, out, proc, over), daemon=True),
                   threading.Thread(target=_pump, args=(proc.stderr, ERROR_CAP, err), daemon=True)]
        for thread in threads:
            thread.start()
        timed_out = False
        try:
            proc.wait(timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill(proc)
            try:
                proc.wait(2)
            except subprocess.TimeoutExpired:
                pass
        _release(held)  # what the program started ends with it (and lets go of the output streams)
        for thread in threads:
            thread.join(1.0)
        if not any(thread.is_alive() for thread in threads):  # a stream still read by a thread is left to it
            for stream in (proc.stdout, proc.stderr):
                stream.close()
    if over.is_set():
        return {"error": "invalid", "detail": "the program wrote more than %d bytes" % OUTPUT_CAP}
    if timed_out:
        return {"error": "timeout", "detail": "no answer within %g seconds" % timeout}
    text = b"".join(out).decode("utf-8", "replace").strip()
    if not text:
        tail = b"".join(err).decode("utf-8", "replace").strip()
        return {"error": "crashed", "detail": tail[-600:] or "the program ended without an answer (exit code %s)"
                                                            % proc.returncode}
    try:
        reply = json.loads(text)
    except ValueError:
        return {"error": "invalid", "detail": "an answer that is not JSON: %s" % text[:200]}
    if not isinstance(reply, dict) or not ("result" in reply or "error" in reply):
        return {"error": "invalid", "detail": "an answer that is not JSON from the runner: %s" % text[:200]}
    if "error" in reply:
        kind = reply["error"] if reply["error"] in ("load", "raised", "invalid") else "invalid"
        return {"error": kind, "detail": str(reply.get("detail") or "")[:1500]}
    return verdict(reply["result"])


def run_many(jobs, timeout=None):
    """run() for each (code, call), side by side: several programs take about as long as the slowest one."""
    jobs = list(jobs)
    if len(jobs) < 2:
        return [run(code, call, timeout) for code, call in jobs]
    with ThreadPoolExecutor(max_workers=min(PARALLEL, len(jobs))) as pool:
        return list(pool.map(lambda job: run(job[0], job[1], timeout), jobs))


# ---------------------------------------------------------------- the call a program gets
def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts is not None else None


def seconds(text):
    """Seconds since the epoch for an ISO 8601 time ("2026-10-28T08:30:00Z"; without an offset, UTC), else None."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        value = datetime.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.timestamp()


def both_times(record, text_key, number_key, default=None):
    """Give a record one time in both forms, ISO text (text_key) and seconds since the epoch (number_key), from
    whichever it has; without either, from default (seconds), else None."""
    number = record.get(number_key)
    if isinstance(number, bool) or not isinstance(number, (int, float)):
        number = seconds(record.get(text_key))
    if number is None:
        number = default
    record[number_key] = round(float(number), 3) if number is not None else None
    record[text_key] = iso(number) if number is not None else None
    return record


def clip(value, limit=INPUT_CLIP):
    """(value, clipped): value with every string longer than limit cut to it."""
    if isinstance(value, str):
        return (value[:limit], True) if len(value) > limit else (value, False)
    if isinstance(value, dict):
        out, cut = {}, False
        for key, item in value.items():
            out[key], hit = clip(item, limit)
            cut = cut or hit
        return out, cut
    if isinstance(value, list):
        out, cut = [], False
        for item in value:
            item, hit = clip(item, limit)
            out.append(item)
            cut = cut or hit
        return out, cut
    return value, False
