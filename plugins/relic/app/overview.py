"""The overview the Relic App opens from its toolbar: the whole organization tree on one page.

For every active organization, in the order of the tree (the cabinet first, each organization under its parent):
- what it is doing: its purpose, its latest message and its latest tool call;
- its open tasks, with owner and status;
- each member: working, working in another organization (a session that holds seats in several), idle, stopped
  (the monitor's Stop), or a seat without a session; with the time it last did something;
- what can start members on their own: automatic wake-ups (the organization's switch, the seat's switch, and whether
  Relic can actually start the seat's session), the Codex automations that start a member's thread, and the Claude
  desktop app's scheduled tasks (listed on their own: each run is a new session, not a seat).

Working is decided exactly as the monitor decides it (monitor.snapshot): a seat's runner is alive, or its session's
transcript changed in the last monitor.ACTIVE seconds.

Cheap to read every few seconds: one read of the organizations, the monitor's snapshot, and a few grouped queries;
the latest tool call and message are then read incrementally (only rows added since the last read)."""
import json
import re
import threading
import time

from relic_core import i18n, monitor, runner, wake
from relic_core.store import kind_of

from . import naming, views

OPEN = ("working", "blocked", "open")  # open tasks, in the order shown
LIVE_STATES = ("running", "waiting", "working")  # an embedded session's states that mean it is in a turn
RECENT = 600  # seconds: a tool call this recent shows where a session in several seats is working
DOING = 1800  # seconds: a tool call this recent is what the member is doing
WEEKDAYS = ("view.schedule.sun", "view.schedule.mon", "view.schedule.tue", "view.schedule.wed",
            "view.schedule.thu", "view.schedule.fri", "view.schedule.sat")
RRULE_DAYS = {"SU": 0, "MO": 1, "TU": 2, "WE": 3, "TH": 4, "FR": 5, "SA": 6}
CRON_DAYS = {"SUN": 0, "MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6}


# ---------------------------------------------------------------- schedules in the person's words

def _clock(hour, minute):
    try:
        hour, minute = int(hour), int(minute)
    except (TypeError, ValueError):
        return None
    return "%02d:%02d" % (hour, minute) if 0 <= hour < 24 and 0 <= minute < 60 else None


def _days(values, names):
    """Sorted weekday numbers (0 = Sunday) from rrule BYDAY or cron day-of-week values; None when one is not plain."""
    days = set()
    for value in values:
        value = value.strip().upper()
        if value in names:
            days.add(names[value])
        elif value.isdigit() and int(value) <= 7:
            days.add(int(value) % 7)
        else:
            return None
    return sorted(days) or None


def _weekly(days, at, lang):
    if days == [1, 2, 3, 4, 5]:
        return i18n.t("view.schedule.weekdays", lang, time=at)
    return i18n.t("view.schedule.weekly", lang, days=[i18n.t(WEEKDAYS[d], lang) for d in days], time=at)


def rrule_text(rule, lang=None):
    """A Codex automation's rrule ("FREQ=HOURLY;INTERVAL=2") in the person's words; the rule itself when unusual."""
    fields = {}
    for part in str(rule or "").split(";"):
        key, _, value = part.partition("=")
        fields[key.strip().upper()] = value.strip()
    freq = fields.get("FREQ", "").upper()
    try:
        n = max(1, int(fields.get("INTERVAL") or 1))
    except ValueError:
        n = 1
    if freq == "MINUTELY":
        return i18n.t("view.schedule.minutes", lang, n=n)
    if freq == "HOURLY":
        return i18n.t("view.schedule.hours", lang, n=n)
    at = _clock(fields.get("BYHOUR"), fields.get("BYMINUTE") or "0")
    if freq == "DAILY":
        return i18n.t("view.schedule.daily", lang, time=at) if at and n == 1 else i18n.t("view.schedule.days", lang, n=n)
    if freq == "WEEKLY" and at and n == 1 and fields.get("BYDAY"):
        days = _days(fields["BYDAY"].split(","), RRULE_DAYS)
        if days:
            return _weekly(days, at, lang)
    return str(rule or "")


def cron_text(expression, lang=None):
    """A 5-field cron expression (local time) in the person's words; the expression itself when unusual."""
    parts = str(expression or "").split()
    if len(parts) != 5 or parts[2] != "*" or parts[3] != "*":
        return str(expression or "")
    minute, hour, dow = parts[0], parts[1], parts[4]
    every = re.fullmatch(r"\*/(\d+)", minute)
    if every and hour == "*" and dow == "*":
        return i18n.t("view.schedule.minutes", lang, n=max(1, int(every.group(1))))
    if minute.isdigit():
        every = re.fullmatch(r"\*/(\d+)", hour)
        if every and dow == "*" and int(minute) == 0:
            return i18n.t("view.schedule.hours", lang, n=max(1, int(every.group(1))))
        if hour == "*" and dow == "*":
            return i18n.t("view.schedule.hourly_at", lang, minute="%02d" % int(minute))
        at = _clock(hour, minute)
        if at and dow == "*":
            return i18n.t("view.schedule.daily", lang, time=at)
        if at:
            span = re.fullmatch(r"(\d)-(\d)", dow)
            days = (list(range(int(span.group(1)), int(span.group(2)) + 1)) if span
                    else _days(dow.split(","), CRON_DAYS))
            if days and all(0 <= d <= 7 for d in days):
                return _weekly(sorted({d % 7 for d in days}), at, lang)
    return str(expression or "")


def once_text(at, lang=None):
    local = time.localtime(at)
    return i18n.t("view.schedule.once", lang, time="%d/%d %02d:%02d" % (local.tm_mon, local.tm_mday, local.tm_hour,
                                                                         local.tm_min))


# ---------------------------------------------------------------- the latest tool call and message, read incrementally

class _Latest:
    """The latest tool call of every seat and the latest message of every organization. The first read takes them
    with two grouped queries; later reads only look at the rows added since (both tables only grow)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.path = None
        self.acts, self.act_id = {}, 0
        self.messages, self.message_id = {}, 0

    def read(self, store):
        with self.lock:
            if self.path != str(store.path):
                self.path, self.acts, self.act_id, self.messages, self.message_id = str(store.path), {}, 0, {}, 0
            with store.db() as db:
                if not self.act_id:
                    ids = [r[0] for r in db.execute("SELECT MAX(id) FROM activity GROUP BY org_id, member")]
                    rows = self._rows(db, "SELECT id, org_id, member, tool, summary, failed, at FROM activity "
                                          "WHERE id IN (%s)", ids)
                else:
                    rows = db.execute("SELECT id, org_id, member, tool, summary, failed, at FROM activity WHERE id > ? "
                                      "ORDER BY id", (self.act_id,)).fetchall()
                for mid, org_id, member, tool, summary, failed, at in rows:
                    self.acts[(org_id, member)] = {"tool": views._short_tool(tool), "failed": bool(failed), "at": at or 0,
                                                   "summary": " ".join(str(summary or "").split())[:160]}
                    self.act_id = max(self.act_id, mid)
                if not self.act_id:
                    self.act_id = db.execute("SELECT COALESCE(MAX(id), 0) FROM activity").fetchone()[0]
                # a receipt only says that a message arrived
                plain = "substr(COALESCE(body, ''), 1, %d) != ?" % len(views.RECEIPT)
                if not self.message_id:
                    ids = [r[0] for r in db.execute("SELECT MAX(id) FROM messages WHERE %s GROUP BY org_id" % plain,
                                                    (views.RECEIPT,))]
                    rows = self._rows(db, "SELECT id, org_id, sender, recipients, body, at FROM messages WHERE id IN (%s)",
                                      ids)
                else:
                    rows = db.execute("SELECT id, org_id, sender, recipients, body, at FROM messages WHERE id > ? AND %s "
                                      "ORDER BY id" % plain, (self.message_id, views.RECEIPT)).fetchall()
                for mid, org_id, sender, recipients, body, at in rows:
                    try:
                        to = json.loads(recipients or "[]")
                    except ValueError:
                        to = []
                    self.messages[org_id] = {"id": mid, "from": sender, "to": to if isinstance(to, list) else [],
                                             "body": " ".join(str(body or "").split())[:200], "at": views.epoch(at)}
                    self.message_id = max(self.message_id, mid)
                if not self.message_id:
                    self.message_id = db.execute("SELECT COALESCE(MAX(id), 0) FROM messages").fetchone()[0]
                focus = dict(db.execute("SELECT actor, org_id FROM focus").fetchall())
                mains = {actor: (org_id, member) for actor, org_id, member in
                         db.execute("SELECT actor, org_id, member FROM actors").fetchall()}
            return dict(self.acts), dict(self.messages), focus, mains

    @staticmethod
    def _rows(db, sql, ids):
        out = []
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            out += db.execute(sql % ",".join("?" * len(chunk)), chunk).fetchall()
        return out


_latest = _Latest()


# ---------------------------------------------------------------- the overview

def _tree(orgs):
    """[(organization, depth)] depth first: the cabinet first, then by creation; an organization whose parent is not
    active, or whose chain of parents loops, starts its own branch."""
    ids = {o["id"] for o in orgs}
    below = {}
    for org in orgs:
        below.setdefault(org.get("parent") if org.get("parent") in ids else None, []).append(org)
    order = lambda o: (not o.get("cabinet"), kind_of(o) == "subgroup", o.get("created_at") or "", o["name"])
    out, seen = [], set()

    def walk(parent, depth):
        stack = [(o, depth) for o in sorted(below.get(parent, []), key=order, reverse=True)]
        while stack:
            org, level = stack.pop()
            if org["id"] in seen:
                continue
            seen.add(org["id"])
            out.append((org, level))
            stack += [(o, level + 1) for o in sorted(below.get(org["id"], []), key=order, reverse=True)]

    walk(None, 0)
    for org in sorted(orgs, key=order):
        if org["id"] not in seen:
            seen.add(org["id"])
            out.append((org, 0))
            walk(org["id"], 1)
    return out


def _configs(orgs, mains):
    """{(org id, member): how Relic starts the seat's turns}: the seat's own config, else the config of a seat its
    session holds elsewhere, its main seat first (as Store.seat_config, without reading the store per seat)."""
    held = {}
    for org in orgs:
        for name, seat in (org.get("members") or {}).items():
            if seat.get("carrier"):
                held.setdefault(seat["carrier"], []).append((org, name))
    out = {}
    for org in orgs:
        for name, seat in (org.get("members") or {}).items():
            if seat.get("config") or not seat.get("carrier"):
                out[(org["id"], name)] = seat.get("config") or {}
                continue
            main = mains.get(seat["carrier"])
            others = sorted(held.get(seat["carrier"], []), key=lambda place: (place[0]["id"], place[1]) != main)
            out[(org["id"], name)] = next(((place["members"][member].get("config") or {}) for place, member in others
                                           if place["id"] != org["id"] and place["members"][member].get("config")), {})
    return out


def _running(orgs, now):
    """{(org id, member)} whose Relic runner is alive, reading only the runner states that exist."""
    try:
        present = {path.stem for path in runner.runs_dir().glob("*.json")}
    except OSError:
        return set()
    return {(org["id"], name) for org in orgs for name in (org.get("members") or {})
            if "%s-%s" % (org["id"], name) in present and runner.is_running(org["id"], name, now)}


def overview(store, hub=None, lang=None, now=None):
    now = time.time() if now is None else now
    orgs = [o for o in store.list_orgs() if o.get("status") in (None, "active")]
    snap = monitor.snapshot(store, now, orgs=orgs)
    sessions = {agent["key"]: agent for agent in snap["agents"]}
    acts, messages, focus, mains = _latest.read(store)
    configs = _configs(orgs, mains)
    running = _running(orgs, now)
    names = {o["id"]: o["name"] for o in orgs}

    # where each working session works now: its running runner's seat, else the organization it works for (focus),
    # else the seat of its latest recent tool call, else its main seat
    here = {}
    for key, agent in sessions.items():
        seats = [(s["org"], s["member"]) for s in agent["seats"]]
        if not agent["working"] or not seats:
            continue
        place = next((seat for seat in seats if seat in running), None)
        if place is None and focus.get(key):
            place = next((seat for seat in seats if seat[0] == focus[key]), None)
        if place is None:
            recent = [(acts[seat]["at"], seat) for seat in seats if seat in acts and now - acts[seat]["at"] < RECENT]
            place = max(recent)[1] if recent else None
        if place is None and mains.get(key) in seats:
            place = mains[key]
        here[key] = place or seats[0]

    latest_action = {}
    for (org_id, member), act in acts.items():
        if act["at"] >= latest_action.get(org_id, {}).get("at", -1):
            latest_action[org_id] = dict(act, member=member)

    automations = snap["automations"]
    threads = {}
    for automation in automations:
        if automation.get("target"):
            threads.setdefault(automation["target"], []).append(automation)
    attached = set()

    def schedule(automation):
        return {"id": automation["id"], "name": automation["name"], "status": automation["status"] or "ACTIVE",
                "kind": automation["kind"], "schedule": rrule_text(automation["rrule"], lang)}

    out, busy = [], {"working": set(), "stopped": set()}  # sessions, each counted once across its seats
    for org, depth in _tree(orgs):
        org_id = org["id"]
        org_wake = bool(org.get("auto_wake", True))
        secretary = views.secretary_of(org)
        members = []
        for name, seat in (org.get("members") or {}).items():
            carrier = seat.get("carrier") or ""
            config = configs.get((org_id, name)) or {}
            key = monitor._base(carrier) if carrier else ""
            agent = sessions.get(key) if key else None
            live = hub.status(org_id, name) if hub and (seat.get("config") or {}).get("surface") == "acp" else None
            brake = (agent or {}).get("stopped")
            act = acts.get((org_id, name))
            last = max([t for t in ((act or {}).get("at"), (agent or {}).get("last_active")) if t] or [0]) or None
            working_in = None
            embedded = (seat.get("config") or {}).get("surface") == "acp"  # the App runs it, with or without a session yet
            if not carrier and not embedded and not live:
                state = "vacant"
            elif brake and not brake.get("released"):
                state = "stopped"
            elif (org_id, name) in running or (live and live.get("state") in LIVE_STATES):
                state = "working"
            elif agent and agent["working"]:
                place = here.get(key)
                state = "working" if place in (None, (org_id, name)) else "elsewhere"
                if state == "elsewhere":
                    working_in = {"org": place[0], "org_name": names.get(place[0], place[0]), "member": place[1]}
            else:
                state = "idle"
            thread = monitor._thread(key) if key else None
            own = [schedule(a) for a in threads.get(thread, [])] if thread else []
            attached.update(a["id"] for a in own)
            if not carrier and not embedded:
                wake_state = "vacant"
            elif not seat.get("auto_wake", True):
                wake_state = "off"
            elif not wake.wakeable(seat, config):
                wake_state = "cannot"  # the switch is on, but Relic has no way to start this seat's session
            else:
                wake_state = "on" if org_wake else "org_off"
            members.append({
                "name": name, "display": naming.display(seat, name, lang), "role": seat.get("role", ""),
                "harness": seat.get("harness") or config.get("harness") or "",
                "leader": org.get("leader") == name, "secretary": secretary == name,
                "state": state, "working_in": working_in, "last_at": last,
                "doing": ("%s %s" % (act["tool"], act["summary"])).strip() if act and now - act["at"] < DOING else "",
                "session": key, "can_stop": bool(key and agent), "stopped": bool(brake), "released": bool(brake and brake.get("released")),
                "auto_wake": bool(seat.get("auto_wake", True)), "wake": wake_state, "automations": own,
                "starts_itself": wake_state == "on" or any(a["status"] != "PAUSED" for a in own)})
        rank = {"working": 0, "elsewhere": 1, "stopped": 2, "idle": 3, "vacant": 4}
        members.sort(key=lambda m: (not m["leader"], not m["secretary"], rank[m["state"]], m["name"]))
        tasks = sorted((t for t in (org.get("tasks") or {}).values() if t.get("status") in OPEN),
                       key=lambda t: (OPEN.index(t["status"]), int(t["id"][1:]) if t["id"][1:].isdigit() else 0))
        unique = {a["id"]: a for m in members for a in m["automations"]}
        for m in members:
            if m["state"] in ("working", "stopped"):
                busy[m["state"]].add(m["session"] or "%s/%s" % (org_id, m["name"]))
        out.append({
            "id": org_id, "name": org["name"], "purpose": org.get("purpose", ""), "kind": kind_of(org),
            "cabinet": bool(org.get("cabinet")), "parent": org.get("parent"), "depth": depth,
            "leader": org.get("leader"), "auto_wake": org_wake,
            "latest_message": messages.get(org_id),
            "latest_action": latest_action.get(org_id),
            "tasks": [{"id": t["id"], "title": t.get("title", ""), "owner": t.get("owner") or "", "status": t["status"],
                       "at": t.get("at")} for t in tasks],
            "done": sum(1 for t in (org.get("tasks") or {}).values() if t.get("status") == "done"),
            "members": members,
            "counts": {"members": len(members), "working": sum(m["state"] == "working" for m in members),
                       "elsewhere": sum(m["state"] == "elsewhere" for m in members),
                       "stopped": sum(m["state"] == "stopped" for m in members), "open_tasks": len(tasks),
                       "wakeable": sum(m["wake"] == "on" for m in members),
                       "automations": len(unique), "automations_on": sum(a["status"] != "PAUSED" for a in unique.values())},
            "starts_itself": any(m["starts_itself"] for m in members)})

    loose = [dict(schedule(a), target=a.get("target") or "") for a in automations if a["id"] not in attached]
    claude = []
    for task in snap["claude_tasks"]:
        when = (cron_text(task["cron"], lang) if task.get("cron")
                else once_text(task["fire_at"], lang) if task.get("fire_at") else "")
        claude.append({"id": task["id"], "name": task.get("name") or task["id"], "description": task.get("description", ""),
                       "enabled": task.get("enabled"), "schedule": when, "cwd": task.get("cwd", "")})
    return {
        "at": now, "scanning": snap["scanning"], "stopped_all": bool(snap.get("stopped_all")),
        "orgs": out, "automations": loose, "claude_tasks": claude,
        "totals": {"orgs": len(out), "members": sum(org["counts"]["members"] for org in out),
                   "working": len(busy["working"]), "stopped": len(busy["stopped"]),
                   "open_tasks": sum(org["counts"]["open_tasks"] for org in out),
                   "orgs_auto_wake": sum(org["auto_wake"] for org in out),
                   "automations": len(automations), "automations_on": sum(a["status"] != "PAUSED" for a in automations),
                   "claude_tasks": len(claude), "claude_tasks_on": sum(task["enabled"] is True for task in claude)}}
