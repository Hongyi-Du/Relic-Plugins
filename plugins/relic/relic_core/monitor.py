"""Who is working, what it costs, and a brake the person can pull from the Relic window.

Working: a seat's runner process is alive, or a session's transcript changed in the last ACTIVE seconds.
Cost: tokens per session from the transcripts on this machine (Claude Code: assistant usage, once per message id,
subagents counted with their session; Codex: token_count events), summed per minute for the last day, and the Codex
plan's rate-limit percentages as Codex last reported them.
Stop: ends Relic's own runner for the session, makes the Relic hook refuse the session's next tool calls so its turn
ends, turns off automatic wake-ups for every seat it holds and pauses the Codex automations that would start it again.
The person typing to that session releases the hook brake; Resume turns back on what Stop turned off.

Light on disk: transcripts are read incrementally and summed in memory by the long-running App server. The only
file written here is brakes.json in the Relic data folder (a few hundred bytes per stopped session); Stop and Resume
also edit the status line of the Codex automation files they pause or resume.
"""
import collections
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from . import process, runner
from .store import data_home

ACTIVE = 150            # seconds since a session's transcript changed for it to count as working
DAY = 24 * 3600
SPANS = {"hour": 3600, "five_hours": 5 * 3600, "day": DAY}
RATE_SPAN = 600         # the per-minute rate looks at the last ten minutes
CODEX_DAYS = 21         # a resumed Codex session keeps writing to the rollout file of the day it started
CHUNK = 4 * 1024 * 1024
AUTOMATIC = ("[Relic auto-wake]", "[Relic GUI nonce:")
MEASURED = ("claude-code", "codex")


def claude_root():
    return Path(os.getenv("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def codex_root():
    return Path(os.getenv("CODEX_HOME") or Path.home() / ".codex")


def brakes_path():
    return data_home() / "brakes.json"


# ---------------- token ledger (in memory, incremental) ----------------

class _Ledger:
    __slots__ = ("offset", "mtime", "buckets", "recent", "first")

    def __init__(self):
        self.offset = 0
        self.mtime = 0.0
        self.buckets = {}                            # minute -> [fresh input, cache read, cache write, output]
        self.recent = collections.deque(maxlen=64)   # Claude logs a message once per content block: count it once
        self.first = None                            # the first line's data (Codex: session_meta)


_ledgers = {}
_lock = threading.Lock()
_codex_limits = {"at": 0.0, "value": None}


def _epoch(text):
    if not isinstance(text, str) or not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _add(ledger, at, fresh, read, write, out):
    if at is None:
        return
    row = ledger.buckets.setdefault(int(at // 60), [0, 0, 0, 0])
    row[0] += fresh
    row[1] += read
    row[2] += write
    row[3] += out


def _claude_line(ledger, record):
    if record.get("type") != "assistant":
        return
    message = record.get("message") or {}
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return
    key = message.get("id") or record.get("requestId")
    if key:
        if key in ledger.recent:
            return
        ledger.recent.append(key)
    _add(ledger, _epoch(record.get("timestamp")), int(usage.get("input_tokens") or 0),
         int(usage.get("cache_read_input_tokens") or 0), int(usage.get("cache_creation_input_tokens") or 0),
         int(usage.get("output_tokens") or 0))


def _codex_line(ledger, record):
    payload = record.get("payload") or {}
    if payload.get("type") != "token_count":
        return
    at = _epoch(record.get("timestamp"))
    limits = payload.get("rate_limits")
    if isinstance(limits, dict) and at and at >= _codex_limits["at"]:
        _codex_limits.update(at=at, value=limits)
    info = payload.get("info") or {}
    last = info.get("last_token_usage") or {}
    total = (info.get("total_token_usage") or {}).get("total_tokens")
    if not last or (total is not None and total in ledger.recent):  # the same count reported again
        return
    if total is not None:
        ledger.recent.append(total)
    sent = int(last.get("input_tokens") or 0)
    cached = int(last.get("cached_input_tokens") or 0)
    _add(ledger, at, max(sent - cached, 0), cached, 0, int(last.get("output_tokens") or 0))


def _read(path, kind, now):
    """The file's ledger, brought up to date with the lines written since the last read."""
    key = str(path)
    try:
        stat = path.stat()
    except OSError:
        return None
    with _lock:
        ledger = _ledgers.get(key)
        if ledger is None or stat.st_size < ledger.offset:
            ledger = _ledgers[key] = _Ledger()
        if stat.st_size == ledger.offset:
            ledger.mtime = stat.st_mtime
            return ledger
        marker = b'"usage"' if kind == "claude" else b'"token_count"'
        parse = _claude_line if kind == "claude" else _codex_line
        start, read, rest = ledger.offset, 0, b""
        try:
            with open(path, "rb") as f:
                f.seek(start)
                while True:
                    block = f.read(CHUNK)
                    if not block:
                        break
                    read += len(block)
                    data = rest + block
                    end = data.rfind(b"\n")
                    if end < 0:  # no complete line yet
                        rest = data
                        continue
                    lines, rest = data[:end].split(b"\n"), data[end + 1:]
                    if start == 0 and ledger.first is None and lines:
                        try:
                            ledger.first = json.loads(lines[0])
                        except ValueError:
                            ledger.first = {}
                    for line in lines:
                        if marker in line:
                            try:
                                parse(ledger, json.loads(line))
                            except (ValueError, TypeError, AttributeError):
                                continue
        except OSError:
            return ledger
        ledger.offset = start + read - len(rest)  # an unfinished last line is read again next time
        ledger.mtime = stat.st_mtime
        floor = int((now - DAY) // 60) - 1
        for minute in [m for m in ledger.buckets if m < floor]:
            del ledger.buckets[minute]
        return ledger


def _sum(ledgers, now):
    spans = {name: [0, 0, 0, 0] for name in SPANS}
    rate = 0
    for ledger in ledgers:
        for minute, row in ledger.buckets.items():
            age = now - minute * 60
            for name, span in SPANS.items():
                if age <= span:
                    for i in range(4):
                        spans[name][i] += row[i]
            if age <= RATE_SPAN:
                rate += sum(row)
    return ({name: {"total": sum(row), "fresh": row[0], "cache_read": row[1], "cache_write": row[2], "output": row[3]}
             for name, row in spans.items()}, round(rate * 60 / RATE_SPAN))


# ---------------- sessions on this machine ----------------

def _recent_files(paths, now):
    found = []
    for path in paths:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime >= now - DAY:
            found.append((path, mtime))
    return found


def _claude_sessions(now):
    """{session id: {"files": [(path, mtime)], "title": str or None}} for Claude Code sessions active in the last day."""
    root = claude_root() / "projects"
    sessions = {}
    if not root.is_dir():
        return sessions
    for project in root.iterdir():
        if not project.is_dir():
            continue
        for path, mtime in _recent_files(project.glob("*.jsonl"), now):
            sessions.setdefault(path.stem, {"files": [], "folder": project})["files"].append((path, mtime))
        for path, mtime in _recent_files(project.glob("*/subagents/*.jsonl"), now):
            sessions.setdefault(path.parent.parent.name, {"files": [], "folder": project})["files"].append((path, mtime))
    for session, info in sessions.items():
        try:
            title = json.loads((info["folder"] / session / "custom-title.json").read_text(encoding="utf-8"))
            info["title"] = title.get("customTitle") or None
        except (OSError, ValueError, AttributeError):
            info["title"] = None
        info["subagents"] = sum(1 for path, mtime in info["files"]
                                if path.parent.name == "subagents" and now - mtime <= ACTIVE)
    return sessions


_UUID = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$")


def _codex_sessions(now):
    """{thread id: {"files": [(path, mtime)]}} for Codex sessions active in the last day."""
    root = codex_root() / "sessions"
    sessions = {}
    for back in range(CODEX_DAYS):
        day = time.localtime(now - back * DAY)
        folder = root / ("%04d" % day.tm_year) / ("%02d" % day.tm_mon) / ("%02d" % day.tm_mday)
        if not folder.is_dir():
            continue
        for path, mtime in _recent_files(folder.glob("rollout-*.jsonl"), now):
            found = _UUID.search(path.name)
            if found:
                sessions.setdefault(found.group(1), {"files": []})["files"].append((path, mtime))
    return sessions


# ---------------- scheduled starts ----------------

_FIELD = re.compile(r'^(\w+)\s*=\s*"((?:[^"\\]|\\.)*)"\s*$', re.M)


def codex_automations():
    root = codex_root() / "automations"
    found = []
    if not root.is_dir():
        return found
    for path in sorted(root.glob("*/automation.toml")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fields = dict(_FIELD.findall(text))
        found.append({"id": fields.get("id") or path.parent.name, "name": fields.get("name") or path.parent.name,
                      "kind": fields.get("kind") or "", "status": fields.get("status") or "", "rrule": fields.get("rrule") or "",
                      "target": fields.get("target_thread_id") or "", "path": path})
    return found


def _set_automation(path, status):
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    new = re.sub(r'^status\s*=\s*"[^"]*"', 'status = "%s"' % status, text, count=1, flags=re.M)
    new = re.sub(r"^updated_at\s*=\s*\d+", "updated_at = %d" % int(time.time() * 1000), new, count=1, flags=re.M)
    tmp = path.with_suffix(".relic.tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    os.replace(tmp, path)


def claude_tasks():
    """The Claude desktop app's scheduled tasks, read only: the app keeps their switches itself."""
    root = claude_root() / "scheduled-tasks"
    found = []
    if not root.is_dir():
        return found
    for path in sorted(root.glob("*/SKILL.md")):
        try:
            head = path.read_text(encoding="utf-8")[:2000]
        except OSError:
            continue
        description = re.search(r"^description:\s*(.+)$", head, re.M)
        found.append({"id": path.parent.name, "description": description.group(1).strip() if description else ""})
    return found


# ---------------- brakes ----------------

def _load_brakes():
    try:
        value = json.loads(brakes_path().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_brakes(value):
    path = brakes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".%d.tmp" % os.getpid())
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _base(actor):
    """The session a hook actor belongs to: "<session>/<subagent>" and "<session>#<org>" both stop with the session."""
    actor = str(actor or "").split("#", 1)[0]
    return actor.split("/", 1)[0]


def brake_for(actor):
    """The active brake on this actor's session, or None. Called by the hook on every tool call: one small read."""
    path = brakes_path()
    if not path.exists():
        return None
    brake = (_load_brakes().get("agents") or {}).get(_base(actor))
    return brake if brake and not brake.get("released_at") else None


def automatic(prompt):
    """Whether a submitted prompt was started by Relic rather than typed by the person."""
    text = str(prompt or "").lstrip()
    return text.startswith(AUTOMATIC[0]) or AUTOMATIC[1] in text


def release(actor, why="the person typed to the session"):
    """The person typed to a stopped session: let its tools work again. Its wake-ups stay off until Resume."""
    brakes = _load_brakes()
    brake = (brakes.get("agents") or {}).get(_base(actor))
    if brake and not brake.get("released_at"):
        brake.update(released_at=time.time(), released_because=why)
        _save_brakes(brakes)
        return True
    return False


def _kill_tree(pid):
    if not runner.pid_alive(pid):
        return False
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, timeout=20,
                           creationflags=process.creation_flags())
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except OSError:
                os.kill(pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def _thread(key):
    return key.split(":", 1)[1] if key.startswith("codex:") else None


def stop(store, key, why="stopped by the person in the Relic window"):
    """Stop one session: end its Relic runners, brake its hooks, turn off its wake-ups and pause the Codex automations
    that would start it. Returns what was done."""
    key = _base(key)
    brakes = _load_brakes()
    agents = brakes.setdefault("agents", {})
    previous = agents.get(key) or {}
    done = {"key": key, "killed": [], "wake_off": list(previous.get("wake_off") or []),
            "paused": dict(previous.get("paused") or {})}
    for org_id, member in store.seat_keys(key):
        state = runner.run_state(org_id, member) or {}
        if state.get("status") == "running" and state.get("pid") and _kill_tree(state["pid"]):
            done["killed"].append(state["pid"])
            runner.write_state(org_id, member, dict(state, status="stopped", error=why, ended=time.time()))
        org = store.get(org_id)
        seat = org["members"].get(member) or {}
        if seat.get("auto_wake", True):
            store.set_seat_auto_wake(org_id, member, False, reason=why)
            done["wake_off"].append([org_id, member])
    thread = _thread(key)
    for automation in codex_automations():
        if thread and automation["target"] == thread and automation["status"] != "PAUSED":
            _set_automation(automation["path"], "PAUSED")
            done["paused"][automation["id"]] = automation["status"]
    agents[key] = {"at": time.time(), "why": why, "wake_off": done["wake_off"], "paused": done["paused"],
                   "killed": done["killed"]}
    _save_brakes(brakes)
    return done


def resume(store, key):
    """Undo one Stop: release the brake, turn back on the wake-ups it turned off, resume the automations it paused."""
    key = _base(key)
    brakes = _load_brakes()
    brake = (brakes.get("agents") or {}).pop(key, None)
    if brake is None:
        return {"key": key, "resumed": False}
    for org_id, member in brake.get("wake_off") or []:
        try:
            store.set_seat_auto_wake(org_id, member, True, reason="resumed by the person in the Relic window")
        except Exception:  # the seat may be gone; resume the rest
            pass
    _resume_automations(brake.get("paused") or {})
    _save_brakes(brakes)
    return {"key": key, "resumed": True}


def _resume_automations(paused):
    for automation in codex_automations():
        before = paused.get(automation["id"])
        if before and automation["status"] == "PAUSED":
            _set_automation(automation["path"], before)


def stop_all(store, now=None):
    """Stop every session that is working, turn off automatic wake-ups in every organization and pause every Codex
    automation. Resume all turns back on exactly what this turned off."""
    snap = snapshot(store, now)
    stopped = [stop(store, agent["key"], "stopped with Stop all in the Relic window")["key"]
               for agent in snap["agents"] + snap["others"] if agent["working"] and agent["can_stop"]]
    brakes = _load_brakes()
    record = brakes.setdefault("all", {"orgs": [], "paused": {}})
    record["at"] = time.time()
    for org in store.list_orgs():
        if org.get("status") == "active" and org.get("auto_wake", True):
            store.set_auto_wake(org["id"], False)
            record["orgs"].append(org["id"])
    for automation in codex_automations():
        if automation["status"] != "PAUSED":
            _set_automation(automation["path"], "PAUSED")
            record["paused"][automation["id"]] = automation["status"]
    _save_brakes(brakes)
    return {"stopped": stopped, "orgs": record["orgs"], "paused": list(record["paused"])}


def resume_all(store):
    brakes = _load_brakes()
    for key in list((brakes.get("agents") or {})):
        resume(store, key)
    brakes = _load_brakes()
    record = brakes.pop("all", None) or {}
    for org_id in record.get("orgs") or []:
        try:
            store.set_auto_wake(org_id, True)
        except Exception:
            pass
    _resume_automations(record.get("paused") or {})
    _save_brakes(brakes)
    return {"orgs": record.get("orgs") or [], "resumed": list((record.get("paused") or {}))}


# ---------------- the snapshot the Relic window shows ----------------

def snapshot(store, now=None):
    now = time.time() if now is None else now
    claude = _claude_sessions(now)
    codex = _codex_sessions(now)
    brakes = _load_brakes()
    automations = codex_automations()
    orgs = store.list_orgs()
    names = {org["id"]: org["name"] for org in orgs}
    seated = collections.OrderedDict()
    for org in orgs:
        if org.get("status") not in (None, "active"):
            continue
        for member, seat in org["members"].items():
            carrier = seat.get("carrier")
            if not carrier or seat.get("harness") not in MEASURED:
                continue
            seated.setdefault(_base(carrier), {"harness": seat["harness"], "seats": []})["seats"].append({
                "org": org["id"], "org_name": org["name"], "member": member,
                "auto_wake": bool(seat.get("auto_wake", True)), "org_auto_wake": bool(org.get("auto_wake", True)),
                "running": runner.is_running(org["id"], member, now)})

    def entry(key, harness, files, title, seats, subagents=0):
        kind = "codex" if harness == "codex" else "claude"
        ledgers = [ledger for ledger in (_read(path, kind, now) for path, _ in files) if ledger]
        tokens, rate = _sum(ledgers, now)
        last = max([mtime for _, mtime in files] or [0]) or None
        running = any(seat["running"] for seat in seats)
        active = last is not None and now - last <= ACTIVE
        brake = (brakes.get("agents") or {}).get(key)
        thread = _thread(key)
        cwd = None
        if kind == "codex" and ledgers and isinstance(ledgers[0].first, dict):
            cwd = (ledgers[0].first.get("payload") or {}).get("cwd")
        return {"key": key, "harness": harness, "title": title or (seats and "%s · %s" % (seats[0]["org_name"], seats[0]["member"]))
                or (Path(cwd).name if cwd else None) or key[-12:],
                "seats": seats, "working": running or active, "reason": "runner" if running else ("active" if active else None),
                "last_active": last, "tokens": tokens, "rate": rate, "subagents": subagents,
                "stopped": {"at": brake["at"], "released": bool(brake.get("released_at"))} if brake else None,
                "can_stop": True,
                "can_interrupt": running or harness == "claude-code",  # Codex desktop turns need trusted Relic hooks
                "automations": [a["id"] for a in automations if thread and a["target"] == thread]}

    agents, others = [], []
    for key, info in seated.items():
        thread = _thread(key)
        files = (codex.pop(thread, {}).get("files") if thread else (claude.get(key) or {}).get("files")) or []
        meta = claude.pop(key, {}) if not thread else {}
        agents.append(entry(key, info["harness"], files, meta.get("title"), info["seats"], meta.get("subagents", 0)))
    for session, info in claude.items():
        others.append(entry(session, "claude-code", info["files"], info.get("title"), [], info.get("subagents", 0)))
    for thread, info in codex.items():
        others.append(entry("codex:" + thread, "codex", info["files"], None, []))
    others = [o for o in others if o["working"] or o["tokens"]["day"]["total"]]
    order = lambda a: (not a["working"], -a["rate"], -a["tokens"]["hour"]["total"])
    agents.sort(key=order)
    others.sort(key=order)
    totals = {}
    for harness, kind in (("claude-code", "claude"), ("codex", "codex")):
        rows = [a for a in agents + others if a["harness"] == harness]
        totals[kind] = {name: sum(a["tokens"][name]["total"] for a in rows) for name in SPANS}
        totals[kind]["rate"] = sum(a["rate"] for a in rows)
        totals[kind]["working"] = sum(1 for a in rows if a["working"])
    limits = _codex_limits["value"]
    return {"at": now, "agents": agents, "others": others, "totals": totals,
            "plans": {"codex": dict(limits, observed_at=_codex_limits["at"]) if limits else None},
            "automations": [{k: v for k, v in a.items() if k != "path"} for a in automations],
            "claude_tasks": claude_tasks(),
            "orgs": [{"id": o["id"], "name": o["name"], "auto_wake": bool(o.get("auto_wake", True))}
                     for o in orgs if o.get("status") in (None, "active")],
            "stopped_all": brakes.get("all")}
