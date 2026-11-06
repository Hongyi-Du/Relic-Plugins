"""Who is working, what it costs, and a brake the person can pull from the Relic window.

Working: a seat's runner process is alive, or a session's transcript changed in the last ACTIVE seconds.
Cost: tokens per session, counted by usage.py from the sessions' own transcripts (Claude Code and Codex), with the
Codex plan's rate limits as Codex last reported them. report() turns them into per-period and cumulative series by
session, by agent (a Relic seat, across the sessions that carried it) or by organization.
Stop: ends Relic's own runner for the session, makes the Relic hook refuse the session's next tool calls so its turn
ends, turns off automatic wake-ups for every seat it holds and pauses the Codex automations that would start it again.
The person typing to that session releases the hook brake; Resume turns back on what Stop turned off.

Light on disk: usage.sqlite3 keeps only sums; brakes.json holds a few hundred bytes per stopped session; Stop and
Resume also edit the status line of the Codex automation files they pause or resume.
"""
import bisect
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import process, runner, usage
from .store import data_home

ACTIVE = 150            # seconds since a session's transcript changed for it to count as working
DAY = 24 * 3600
SPANS = {"hour": 3600, "five_hours": 5 * 3600, "day": DAY}
RANGES = {"24h": DAY, "7d": 7 * DAY, "30d": 30 * DAY, "90d": 90 * DAY}  # and "today": since local midnight
GROUPS = ("session", "agent", "org")
TOP = 30                # series kept by name; the rest are summed into one
FRESH_FOR = 3           # seconds a scan stays current for the views
AUTOMATIC = ("[Relic auto-wake]", "[Relic GUI nonce:")
MEASURED = ("claude-code", "codex")
claude_root = usage.claude_root
codex_root = usage.codex_root


def brakes_path():
    return data_home() / "brakes.json"


def _counts(cell):
    cell = cell or [0, 0, 0, 0]
    return {"total": sum(cell), "fresh": cell[0], "cache_read": cell[1], "cache_write": cell[2], "output": cell[3]}


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


def set_automation(automation_id, status):
    """The person pauses (PAUSED) or resumes (ACTIVE) one Codex automation from the Relic window. Stop and Resume keep
    their own record of what they paused, so a later Resume never undoes the person's own choice."""
    if status not in ("ACTIVE", "PAUSED"):
        raise ValueError("status must be ACTIVE or PAUSED")
    for automation in codex_automations():
        if automation["id"] == automation_id:
            if automation["status"] != status:
                _set_automation(automation["path"], status)
            return {"id": automation_id, "status": status, "before": automation["status"]}
    raise ValueError("No Codex automation %s" % automation_id)


def _claude_app_folders():
    """Where the Claude desktop app may keep its own record of the scheduled tasks (their switches and times)."""
    folders = []
    for name in ("LOCALAPPDATA", "APPDATA"):
        if os.environ.get(name):
            folders += [Path(os.environ[name]) / "Claude-Data", Path(os.environ[name]) / "Claude"]
    if sys.platform == "darwin":
        support = Path.home() / "Library" / "Application Support"
        folders += [support / "Claude-Data", support / "Claude"]
    return folders


def _claude_app_tasks():
    """{task id: the Claude desktop app's entry for it} from its scheduled-tasks.json files, newest file first. Read only
    and best effort: the file belongs to the app, and a task it does not list just shows without a switch or time."""
    files = []
    for folder in _claude_app_folders():
        for pattern in ("claude-code-sessions/*/*/scheduled-tasks.json", "*/claude-code-sessions/*/*/scheduled-tasks.json"):
            try:
                files += [(path.stat().st_mtime, path) for path in folder.glob(pattern)]
            except OSError:
                continue
    found = {}
    for _, path in sorted(files, key=lambda item: item[0], reverse=True):
        try:
            tasks = json.loads(path.read_text(encoding="utf-8")).get("scheduledTasks") or []
        except (OSError, ValueError, AttributeError):
            continue
        for task in tasks if isinstance(tasks, list) else []:
            if isinstance(task, dict) and task.get("id") and task["id"] not in found:
                found[task["id"]] = task
    return found


def claude_tasks():
    """The Claude desktop app's scheduled tasks, read only: the app keeps their switches itself. Each with its
    description (from its SKILL.md) and, where the app's own record has it, its name, switch, schedule and folder."""
    root = claude_root() / "scheduled-tasks"
    found = []
    if not root.is_dir():
        return found
    kept = None
    for path in sorted(root.glob("*/SKILL.md")):
        try:
            head = path.read_text(encoding="utf-8")[:2000]
        except OSError:
            continue
        description = re.search(r"^description:\s*(.+)$", head, re.M)
        kept = _claude_app_tasks() if kept is None else kept
        entry = kept.get(path.parent.name) or {}
        fire_at = entry.get("fireAt")
        found.append({"id": path.parent.name, "description": description.group(1).strip() if description else "",
                      "name": str(entry.get("displayName") or entry.get("title") or ""),
                      "enabled": entry["enabled"] if isinstance(entry.get("enabled"), bool) else None,
                      "cron": str(entry.get("cronExpression") or entry.get("cron") or ""),
                      "fire_at": fire_at / 1000 if isinstance(fire_at, (int, float)) and fire_at > 0 else None,
                      "cwd": str(entry.get("cwd") or "")})
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


def _in_app(state):
    """A turn the Relic App runs itself records the App's own process (via relic-app). Ending that process would end
    the App and every member it runs; the App cancels such a turn instead."""
    return state.get("via") == "relic-app" or state.get("pid") == os.getpid()


def stop(store, key, why="stopped by the person in the Relic window", cancel_turn=None):
    """Stop one session: end its Relic runners, brake its hooks, turn off its wake-ups and pause the Codex automations
    that would start it. A turn the App runs is cancelled through cancel_turn(org_id, member). Returns what was done."""
    key = _base(key)
    brakes = _load_brakes()
    agents = brakes.setdefault("agents", {})
    previous = agents.get(key) or {}
    done = {"key": key, "killed": [], "cancelled": [], "wake_off": list(previous.get("wake_off") or []),
            "paused": dict(previous.get("paused") or {})}
    for org_id, member in store.seat_keys(key):
        state = runner.run_state(org_id, member) or {}
        if state.get("status") == "running" and _in_app(state):
            if cancel_turn is not None:
                try:
                    cancel_turn(org_id, member)
                    done["cancelled"].append([org_id, member])
                except Exception:  # the turn may have ended meanwhile; stop the rest
                    pass
        elif state.get("status") == "running" and state.get("pid") and _kill_tree(state["pid"]):
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


def stop_all(store, now=None, cancel_turn=None):
    """Stop every session that is working, turn off automatic wake-ups in every organization and pause every Codex
    automation. Resume all turns back on exactly what this turned off."""
    snap = snapshot(store, now)
    stopped = [stop(store, agent["key"], "stopped with Stop all in the Relic window", cancel_turn)["key"]
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


# ---------------- the live view the Relic window shows ----------------

def _active_orgs(store):
    return [org for org in store.list_orgs() if org.get("status") in (None, "active")]


def _carried(orgs):
    """{session: [(org, member)]} of every seat a session carries now or carried before."""
    places = {}
    for org in orgs:
        for member, seat in org["members"].items():
            for carrier in [seat.get("carrier")] + list(seat.get("past_carriers") or []):
                if carrier:
                    places.setdefault(_base(carrier), []).append((org, member))
    return places


def _owner(store, session, places):
    """(org, member) a session's tokens count for: its main seat while it holds it, else the first seat it held."""
    try:
        org, member = store.whoami(session)
    except Exception:
        org, member = None, None
    for place, name in places:
        if org and place["id"] == org["id"] and name == member:
            return place, name
    return places[0]


def snapshot(store, now=None, orgs=None):
    """orgs: the active organizations when the caller has just read them (the overview), so they are read once."""
    now = time.time() if now is None else now
    ledger = usage.Ledger.shared()
    ledger.scan(now=now, blocking=False, fresh_for=FRESH_FOR)  # never waits for the first, long read
    sessions = ledger.sessions(now, ACTIVE)
    windows = ledger.windows(now, SPANS)
    brakes = _load_brakes()
    automations = codex_automations()
    orgs = _active_orgs(store) if orgs is None else orgs
    seated = {}
    for org in orgs:
        for member, seat in org["members"].items():
            carrier = seat.get("carrier")
            if not carrier or seat.get("harness") not in MEASURED:
                continue
            seated.setdefault(_base(carrier), {"harness": seat["harness"], "seats": []})["seats"].append({
                "org": org["id"], "org_name": org["name"], "member": member,
                "auto_wake": bool(seat.get("auto_wake", True)), "org_auto_wake": bool(org.get("auto_wake", True)),
                "running": runner.is_running(org["id"], member, now)})

    def entry(key, harness, seats):
        info = sessions.get(key) or {}
        window = windows.get(key) or {}
        last = info.get("last_at") or None
        running = any(seat["running"] for seat in seats)
        active = bool(last) and now - last <= ACTIVE
        brake = (brakes.get("agents") or {}).get(key)
        thread = _thread(key)
        cwd = info.get("cwd")
        title = (info.get("title") or (seats and "%s · %s" % (seats[0]["org_name"], seats[0]["member"]))
                 or info.get("prompt") or (Path(cwd).name if cwd else None) or key[-12:])
        return {"key": key, "harness": harness, "title": title, "seats": seats,
                "working": running or active, "reason": "runner" if running else ("active" if active else None),
                "last_active": last, "rate": window.get("rate", 0), "subagents": info.get("subagents", 0),
                "tokens": {name: _counts((window.get("spans") or {}).get(name)) for name in SPANS},
                "stopped": {"at": brake["at"], "released": bool(brake.get("released_at"))} if brake else None,
                "can_stop": True,
                "can_interrupt": running or harness == "claude-code",  # Codex desktop turns need trusted Relic hooks
                "automations": [a["id"] for a in automations if thread and a["target"] == thread]}

    agents = [entry(key, info["harness"], info["seats"]) for key, info in seated.items()]
    others = []
    for key, info in sessions.items():
        if key in seated:
            continue
        other = entry(key, "codex" if info["kind"] == "codex" else "claude-code", [])
        if other["working"] or other["tokens"]["day"]["total"]:
            others.append(other)
    order = lambda a: (not a["working"], -a["rate"], -a["tokens"]["hour"]["total"], a["title"])
    agents.sort(key=order)
    others.sort(key=order)
    totals = {}
    for harness, kind in (("claude-code", "claude"), ("codex", "codex")):
        rows = [a for a in agents + others if a["harness"] == harness]
        totals[kind] = {name: sum(a["tokens"][name]["total"] for a in rows) for name in SPANS}
        totals[kind].update(rate=sum(a["rate"] for a in rows), working=sum(1 for a in rows if a["working"]))
    limits = ledger.limits.get("value")
    return {"at": now, "agents": agents, "others": others, "totals": totals, "scanning": ledger.scanning,
            "plans": {"codex": dict(limits, observed_at=ledger.limits.get("at")) if limits else None},
            "automations": [{k: v for k, v in a.items() if k != "path"} for a in automations],
            "claude_tasks": claude_tasks(),
            "orgs": [{"id": o["id"], "name": o["name"], "auto_wake": bool(o.get("auto_wake", True))} for o in orgs],
            "stopped_all": brakes.get("all")}


# ---------------- the statistics: per period and cumulative, by session, agent or organization ----------------

def _starts(since, now, bucket):
    """Local-time bucket starts from the one holding `since` up to `now`."""
    if bucket == "hour":
        first = int(since // 3600) * 3600
        return list(range(first, int(now) + 1, 3600))
    day = datetime.fromtimestamp(since).replace(hour=0, minute=0, second=0, microsecond=0)
    starts = []
    while day.timestamp() <= now:
        starts.append(int(day.timestamp()))
        day = (day + timedelta(days=1, hours=2)).replace(hour=0)  # one local day on, across a clock change too
    return starts


def report(store, span="7d", group="agent", org=None, agent=None, bucket=None, now=None):
    """Tokens per period and cumulative for every session, agent or organization in the span, largest first.

    Agent: a Relic seat ("<org id>/<member>") across every session that carried it. A session holding several seats
    splits each hour's tokens between them by the tool calls it made in each seat that hour (all to its main seat in an
    hour without calls). Organization: the agent's organization. Sessions without a Relic seat count under their own
    key and under the organization "" (none). org= and agent= filter before grouping."""
    now = time.time() if now is None else now
    group = group if group in GROUPS else "agent"
    ledger = usage.Ledger.shared()
    ledger.scan(now=now, blocking=False, fresh_for=FRESH_FOR)
    if span == "today":
        since = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    else:
        span = span if span in RANGES else "7d"
        since = now - RANGES[span]
    bucket = bucket if bucket in ("hour", "day") else ("hour" if now - since <= 2 * DAY else "day")
    starts = _starts(since, now, bucket)
    orgs = _active_orgs(store)
    places = _carried(store.list_orgs())
    meta = ledger.sessions(now)
    owners = {}

    def named(session):
        info = meta.get(session) or {}
        seat = owner(session)[1] if session in places else None
        return (info.get("title") or seat or info.get("prompt") or (Path(info["cwd"]).name if info.get("cwd") else None)
                or session[-12:])

    def owner(session):  # its main seat, or the session itself when it holds no seat
        if session not in owners:
            if session in places:
                place, member = _owner(store, session, places[session])
                owners[session] = ("%s/%s" % (place["id"], member), "%s · %s" % (place["name"], member), place["id"], place["name"])
            else:
                info = meta.get(session) or {}
                owners[session] = (session, info.get("title") or info.get("prompt")
                                   or (Path(info["cwd"]).name if info.get("cwd") else None) or session[-12:], "", None)
        return owners[session]

    several = {session: {(place["id"], member): place for place, member in held}
               for session, held in places.items() if len({(place["id"], member) for place, member in held}) > 1}
    calls = {}
    if several:
        holders = {}
        for session, seats in several.items():
            for seat in seats:
                holders.setdefault(seat, []).append(session)
        with store.db() as db:
            for org_id, member, hour, count in db.execute(
                    "SELECT org_id, member, CAST(at / 3600 AS INTEGER), COUNT(*) FROM activity WHERE at >= ? GROUP BY 1, 2, 3",
                    (starts[0],)):
                for session in holders.get((org_id, member), []):
                    calls.setdefault((session, hour), {})[(org_id, member)] = count

    def shares(session, hour):
        weights = calls.get((session, hour))
        if not weights:
            return [owner(session) + (1.0,)]
        total = sum(weights.values())
        return [("%s/%s" % seat, "%s · %s" % (several[session][seat]["name"], seat[1]), seat[0],
                 several[session][seat]["name"], count / total) for seat, count in weights.items()]

    groups = {}
    for session, kind, hour, *counts in ledger.hours(starts[0], now + 3600):
        index = bisect.bisect_right(starts, hour * 3600) - 1
        if index < 0:
            continue
        for agent_key, agent_label, org_id, org_label, part in shares(session, hour):
            if (org is not None and org_id != org) or (agent and agent not in (agent_key, session)):
                continue
            if group == "session":
                key, label = session, named(session)
            elif group == "agent":
                key, label = agent_key, agent_label
            else:
                key, label = org_id, org_label
            entry = groups.setdefault(key, {"key": key, "label": label, "org": org_id, "kinds": set(),
                                            "values": [0.0] * len(starts), "cells": [0.0, 0.0, 0.0, 0.0]})
            entry["kinds"].add(kind)
            entry["values"][index] += sum(counts) * part
            for i in range(4):
                entry["cells"][i] += counts[i] * part
    for entry in groups.values():
        entry["values"] = [round(v) for v in entry["values"]]
        entry["cells"] = [round(v) for v in entry["cells"]]
    series = sorted(groups.values(), key=lambda g: (-sum(g["cells"]), str(g["label"])))
    if len(series) > TOP:
        rest = {"key": "*", "label": None, "org": None, "kinds": set(), "values": [0] * len(starts), "cells": [0, 0, 0, 0],
                "count": len(series) - TOP + 1}
        for g in series[TOP - 1:]:
            rest["kinds"] |= g["kinds"]
            rest["values"] = [a + b for a, b in zip(rest["values"], g["values"])]
            rest["cells"] = [a + b for a, b in zip(rest["cells"], g["cells"])]
        series = series[:TOP - 1] + [rest]
    totals = [sum(g["values"][i] for g in series) for i in range(len(starts))]
    for g in series:
        g["kinds"] = sorted(g["kinds"])
        g["total"] = _counts(g.pop("cells"))
        g["cumulative"] = _running(g["values"])
    agents = {}
    for held in places.values():
        for place, member in held:
            if place.get("status") in (None, "active"):
                key = "%s/%s" % (place["id"], member)
                agents.setdefault(key, {"key": key, "label": "%s · %s" % (place["name"], member), "org": place["id"]})
    limits = ledger.limits.get("value")
    return {"span": span, "bucket": bucket, "group": group, "from": starts[0], "to": now, "starts": starts,
            "series": series, "totals": totals, "cumulative": _running(totals),
            "total": sum(totals), "scanning": ledger.scanning,
            "filters": {"orgs": [{"id": o["id"], "name": o["name"]} for o in orgs],
                        "agents": sorted(agents.values(), key=lambda a: a["label"])},
            "plans": {"codex": dict(limits, observed_at=ledger.limits.get("at")) if limits else None}}


def _running(values):
    out, total = [], 0
    for value in values:
        total += value
        out.append(total)
    return out
