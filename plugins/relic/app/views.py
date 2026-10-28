"""What the Relic App shows, computed from the organization store and the App's embedded sessions.

Everything comes from the records the plugin keeps (~/.relic/relic.sqlite3): seats, messages, tasks, episodes,
protocols, events and tool activity, plus each session's own transcript for its context and trajectory. Nothing here
writes to the store.
"""
import calendar
import json
import os
import time
from pathlib import Path

from relic_core import i18n, runner, trajectory
from relic_core.store import has_check, inherits, kind_of

from . import harness as harnesses
from . import naming, prefs

HUMAN = "human"
RECEIPT = "[Relic auto-receipt]"
CHAT_HARNESSES = ("chatgpt", "claude-chat")


# ---------------------------------------------------------------- small helpers
def epoch(at):
    try:
        return calendar.timegm(time.strptime(at, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return 0


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else None


def long_path(path):
    """Windows refuses paths over 260 characters unless they carry the \\\\?\\ prefix (Claude Code names its
    project folders after the full working directory, so transcripts can be that long)."""
    text = str(path)
    if os.name == "nt" and len(text) > 240 and not text.startswith("\\\\?\\"):
        return Path("\\\\?\\" + str(Path(text).resolve()))
    return Path(text)


def _rows(store, sql, args=()):
    with store.db() as db:
        return db.execute(sql, args).fetchall()


# ---------------------------------------------------------------- sessions behind the seats
_LOCATE = {}   # actor -> (time, (harness, session, path))
_META = {}     # path -> (mtime, meta)


def _long_dir(path):
    """A directory to search with glob even when the files below it pass 260 characters (Windows)."""
    path = Path(path)
    if os.name == "nt" and path.exists():
        return Path("\\\\?\\" + str(path.resolve()))
    return path


def _plain(path):
    text = str(path)
    return Path(text[4:]) if text.startswith("\\\\?\\") else Path(text)


def locate(actor):
    """(harness, session, transcript path or None). Unlike trajectory.locate, a Claude Code subagent whose own
    transcript is not found gets None, not its parent session's transcript, and long Windows paths are searched."""
    hit = _LOCATE.get(actor)
    if hit and time.time() - hit[0] < 120 and (hit[1][2] is None or long_path(hit[1][2]).exists()):
        return hit[1]
    head = actor.split("/", 1)[0]
    if ":" in head:  # codex:<thread>, or a chat member (no transcript on this computer)
        if actor.startswith("codex:") and "/" in actor:  # a Codex subagent is a thread of its own: codex:<parent>/<child>
            found = trajectory.locate("codex:" + actor.rsplit("/", 1)[1])
        else:
            found = trajectory.locate(actor) if actor.startswith("codex:") else (head.split(":", 1)[0], actor, None)
    else:
        session, _, agent = actor.partition("/")
        projects = _long_dir(trajectory.claude_home() / "projects")
        if agent:
            hits = list(projects.glob("*/%s/subagents/agent-%s.jsonl" % (session, agent)))
        else:
            hits = list(projects.glob("*/%s.jsonl" % session))
        found = ("claude-code", session, _plain(hits[0]) if hits else None)
    _LOCATE[actor] = (time.time(), found)
    return found


def _tail_lines(path, size=262144):
    with open(long_path(path), "rb") as handle:
        handle.seek(0, os.SEEK_END)
        end = handle.tell()
        handle.seek(max(0, end - size))
        data = handle.read().decode("utf-8", "replace")
    lines = data.splitlines()
    return lines[1:] if end > size else lines


def session_meta(actor):
    """Where a seat's session runs and with which model, from the tail of its transcript (cached by mtime)."""
    if not actor:
        return {}
    harness, session, path = locate(actor)
    if path is None:
        return {"harness": harness, "session": session}
    try:
        mtime = long_path(path).stat().st_mtime
    except OSError:
        return {"harness": harness, "session": session}
    cached = _META.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    meta = {"harness": harness, "session": session, "path": str(path), "updated": mtime}
    try:
        lines = _tail_lines(path)
    except OSError:
        lines = []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if harness == "codex":
            p = e.get("payload") or {}
            if e.get("type") == "session_meta":
                meta.update(originator=p.get("originator"), source=p.get("source"), cwd=p.get("cwd"),
                            version=p.get("cli_version"))
            elif e.get("type") == "turn_context" and p.get("model"):
                meta["model"] = p.get("model")
                meta["effort"] = p.get("effort") or meta.get("effort")
                meta["cwd"] = p.get("cwd") or meta.get("cwd")
        else:
            if e.get("entrypoint"):
                meta["entrypoint"] = e["entrypoint"]
            if e.get("cwd"):
                meta["cwd"] = e["cwd"]
            if e.get("version"):
                meta["version"] = e["version"]
            message = e.get("message") or {}
            if e.get("type") == "assistant" and message.get("model") and not str(message["model"]).startswith("<"):
                meta["model"] = message["model"]
    if harness == "codex" and not meta.get("originator"):
        try:
            with open(long_path(path), encoding="utf-8", errors="replace") as handle:
                first = json.loads(handle.readline() or "{}")
            p = first.get("payload") or {}
            meta.update(originator=p.get("originator"), source=p.get("source"), cwd=meta.get("cwd") or p.get("cwd"),
                        version=p.get("cli_version"))
        except (OSError, ValueError):
            pass
    _META[str(path)] = (mtime, meta)
    return meta


def surface_of(seat, meta):
    """desktop | cli | subagent | acp | chat | sdk | unknown: where the seat's session is used."""
    config = seat.get("config") or {}
    carrier = seat.get("carrier") or ""
    if config.get("surface") == "acp":
        return "acp"
    if seat.get("harness") in CHAT_HARNESSES:
        return "chat"
    if "/" in carrier:
        return "subagent"
    entry = (meta.get("entrypoint") or "").lower()
    origin = ("%s %s" % (meta.get("originator") or "", meta.get("source") or "")).lower()
    if "desktop" in entry or "desktop" in origin or config.get("surface") == "gui":
        return "desktop"
    if entry in ("cli", "claude-vscode") or "cli" in origin or "exec" in origin or config.get("surface") == "cli":
        return "cli"
    if entry.startswith("sdk"):
        return "sdk"
    return "unknown"


SURFACE_KEYS = {"desktop": "view.surface.desktop", "cli": "view.surface.cli", "acp": "view.surface.acp",
                "chat": "view.surface.chat"}
SURFACE_NAMES = {"subagent": "subagent", "sdk": "SDK", "unknown": ""}
HARNESS_LABEL = {"claude-code": "Claude Code", "codex": "Codex", "chatgpt": "ChatGPT"}


def surface_label(surface, lang=None):
    """Where a member's session runs, in the person's language (product words stay as they are)."""
    if surface in SURFACE_KEYS:
        return i18n.t(SURFACE_KEYS[surface], lang)
    return SURFACE_NAMES.get(surface, surface)


def harness_label(harness, lang=None):
    if harness == "claude-chat":
        return i18n.t("view.harness.claude_chat", lang)
    return HARNESS_LABEL.get(harness, harness)


# ---------------------------------------------------------------- organizations
def org_list(store):
    last = dict(_rows(store, "SELECT org_id, MAX(at) FROM events GROUP BY org_id"))
    out = []
    for org in store.list_orgs():
        members = org.get("members") or {}
        out.append({"id": org["id"], "name": org["name"], "purpose": org.get("purpose", ""),
                    "governance": org.get("governance"), "status": org.get("status"), "created_at": org.get("created_at"),
                    "parent": org.get("parent"), "members": len(members), "member_names": list(members)[:9], "last_at": last.get(org["id"]),
                    "kind": kind_of(org), "cabinet": bool(org.get("cabinet")), "leader": org.get("leader")})
    out.sort(key=lambda o: o.get("last_at") or o.get("created_at") or "", reverse=True)
    return out


def secretary_of(org):
    """The seat that speaks for the organization to the person: one marked as secretary, else the leader's seat when a
    main session (not a subagent, not a chat) sits in it, which is the conversation the organization was formed in.
    An organization the person founded in the App was formed in no member's conversation: it has a secretary only
    when one is set."""
    members = org.get("members") or {}
    for name, seat in members.items():
        if seat.get("secretary"):
            return name
    if org.get("founder") == "human":
        return None
    leader = org.get("leader")
    seat = members.get(leader or "")
    if seat and seat.get("carrier") and "/" not in seat["carrier"] and seat.get("harness") not in CHAT_HARNESSES:
        return leader
    return None


def latest_activity(store, org_id):
    rows = _rows(store, """SELECT member, tool, kind, summary, failed, at FROM activity WHERE id IN
                           (SELECT MAX(id) FROM activity WHERE org_id=? GROUP BY member)""", (org_id,))
    return {r[0]: {"tool": r[1], "kind": r[2], "summary": r[3], "failed": bool(r[4]), "at": r[5]} for r in rows}


def recent_activity(store, org_id, member, limit=12):
    rows = _rows(store, "SELECT tool, kind, summary, failed, at FROM activity WHERE org_id=? AND member=? "
                        "ORDER BY id DESC LIMIT ?", (org_id, member, limit))
    return [{"tool": r[0], "kind": r[1], "summary": r[2], "failed": bool(r[3]), "at": r[4]} for r in rows]


def _short_tool(tool):
    return tool.rsplit("__", 1)[-1] if (tool or "").startswith("mcp__") else (tool or "")


def doing_text(act):
    if not act:
        return ""
    summary = " ".join(str(act.get("summary") or "").split())
    return ("%s %s" % (_short_tool(act["tool"]), summary[:140])).strip()


def member_status(org, name, seat, live, act, now, lang=None):
    """(state, detail). state: running | waiting | working | active | idle | vacant | error."""
    if live:
        return live.get("state") or "idle", live.get("detail") or ""
    wake = ((org.get("wake") or {}).get("members") or {}).get(name) or {}
    if not seat.get("carrier") and not (seat.get("config") or {}).get("surface") == "acp":
        return "vacant", i18n.t("view.state.vacant", lang)
    if runner.is_running(org["id"], name, now):
        return "running", i18n.t("view.state.running", lang)
    if wake.get("gave_up_at"):
        return "error", i18n.t("view.state.wake_failed", lang)
    turn = (org.get("episodes") or {}).get(seat.get("turn_episode") or "")
    age = now - act["at"] if act else None
    if turn and turn.get("status") == "open" and age is not None and age < 600:
        return "working", i18n.t("view.state.working", lang)
    if age is not None and age < 900:
        return "active", i18n.t("view.state.active", lang, n=max(1, int(age // 60)))
    return "idle", i18n.t("view.state.idle", lang)


CLAUDE_EFFORTS = ["low", "medium", "high", "xhigh", "max"]
CODEX_EFFORTS = ["low", "medium", "high", "xhigh", "max", "ultra"]
CODEX_MODELS = ["gpt-6.1-sol", "gpt-6-astra", "gpt-6.1-terra", "gpt-6-sol", "gpt-6-luna", "gpt-5.6-sol", "gpt-5.6-terra",
                "gpt-5.6-luna"]


def model_info(harness, surface, config, live, agent, lang=None):
    """Whether the App can change a member's model, where the change applies, and the choices."""
    known = harnesses.remembered(harness)
    if harness == "claude-code":
        models = known.get("models") or [m for m in runner.CLAUDE_MODELS if m]
        efforts = known.get("efforts") or CLAUDE_EFFORTS
    elif harness == "codex":
        models, efforts = known.get("models") or CODEX_MODELS, known.get("efforts") or CODEX_EFFORTS
    else:
        models, efforts = [], []
    if live and live.get("models"):
        models = live["models"]
    info = {"models": models, "efforts": efforts, "editable": False, "applies": "", "note": ""}
    if surface == "acp":
        info.update(editable=True, applies="now", note=i18n.t("view.model.embedded", lang))
    elif agent:
        info["note"] = i18n.t("view.model.subagent", lang)
    elif surface == "chat" or harness in CHAT_HARNESSES:
        info["note"] = i18n.t("view.model.chat", lang)
    elif config.get("harness") == harness and config.get("surface") == "cli":
        info.update(editable=True, applies="next", note=i18n.t("view.model.next", lang))
    elif harness == "claude-code":
        info["note"] = i18n.t("view.model.claude", lang)
    elif harness == "codex":
        info["note"] = i18n.t("view.model.codex", lang)
    return info


def member_view(store, org, name, seat, hub=None, act=None, unread=0, secretary=None, now=None, lang=None):
    now = now or time.time()
    carrier = seat.get("carrier") or ""
    meta = session_meta(carrier) if carrier and seat.get("harness") not in CHAT_HARNESSES else {}
    config = seat.get("config") or {}
    live = hub.status(org["id"], name) if hub else None
    state, detail = member_status(org, name, seat, live, act, now, lang)
    surface = surface_of(seat, meta)
    harness = seat.get("harness") or config.get("harness") or ""
    tasks = [t for t in (org.get("tasks") or {}).values() if t.get("owner") == name]
    session, _, agent = carrier.partition("/")  # a subagent: "<parent session>/<agent id>"
    parent = next((n for n, s in (org.get("members") or {}).items() if agent and s.get("carrier") == session), None)
    model = (live or {}).get("model") or config.get("model") or meta.get("model") or ""
    doing = (live or {}).get("doing") or (doing_text(act) if act and now - act["at"] < 1800 else "")
    info = model_info(harness, surface, config, live, agent, lang)
    return {
        "name": name, "display": naming.display(seat, name, lang), "display_custom": bool(seat.get("display_name")),
        "avatar": prefs.avatar_url(org["id"], name),
        "role": seat.get("role", ""), "harness": harness, "harness_label": harness_label(harness, lang),
        "surface": surface, "surface_label": surface_label(surface, lang), "model": model,
        "effort": (live or {}).get("effort") or config.get("effort") or meta.get("effort") or "",
        "model_editable": info["editable"], "model_applies": info["applies"], "model_note": info["note"],
        "models": info["models"], "efforts": info["efforts"],
        "state": state, "detail": detail, "doing": doing,
        "doing_at": iso(act["at"]) if act else None, "session": session.split(":", 1)[-1] if carrier else "",
        "agent": agent, "parent": parent,
        "carriers": seat.get("carriers", 0), "joined_at": seat.get("joined_at"), "leader": org.get("leader") == name,
        "secretary": secretary == name, "unread": unread, "cwd": meta.get("cwd") or config.get("folder") or "",
        "version": meta.get("version") or "", "embedded": bool(live) or config.get("surface") == "acp",
        "tasks": [{"id": t["id"], "title": t["title"], "status": t["status"]} for t in tasks],
        "has_transcript": bool(meta.get("path")),
        "also_in": also_in(store, org["id"], carrier), "ex_officio": ex_officio(store, seat),
    }


def also_in(store, org_id, carrier):
    """The other seats the member's session holds: [{org, org_name, member, role, kind, main}] (the card's "also in")."""
    if not carrier:
        return []
    out = []
    for org, member, main in store.seats_of(carrier):
        if org["id"] != org_id:
            out.append({"org": org["id"], "org_name": org["name"], "member": member,
                        "role": (org["members"].get(member) or {}).get("role", ""), "kind": kind_of(org),
                        "cabinet": bool(org.get("cabinet")), "main": main})
    return out


def ex_officio(store, seat):
    """{org, org_name} of the department whose leader holds this seat ex officio, else None."""
    office = seat.get("ex_officio") or {}
    if not office.get("org"):
        return None
    try:
        name = store.get(office["org"])["name"]
    except Exception:
        name = office["org"]
    return {"org": office["org"], "org_name": name, "member": office.get("member")}


def unread_counts(store, org_id):
    """Unread messages per member (what each member has not read yet)."""
    out = {}
    for member, messages in store.unread_by_member(org_id).items():
        out[member] = len(messages)
    return out


def decisions(store, org, hub=None, lang=None):
    """Items that wait on the person: permission requests of embedded sessions, trajectory requests only the person
    can answer, wake-ups that gave up, blocked tasks."""
    items = []
    if hub:
        for p in hub.permissions(org["id"]):
            items.append(dict(p, kind="permission"))
    try:  # {"to_answer": [...], "mine": [...]}; asked without an actor, it lists what waits on the person
        pending = store.trajectory_requests(org_id=org["id"]).get("to_answer") or []
    except Exception:
        pending = []
    for r in pending:
        items.append({"kind": "trajectory", "id": r.get("id"), "member": r.get("member"), "carrier": r.get("carrier"),
                      "requester": r.get("requester"), "reason": r.get("reason", "")})
    for member, w in ((org.get("wake") or {}).get("members") or {}).items():
        if w.get("gave_up_at") or w.get("waiting_since"):
            items.append({"kind": "wake", "member": member, "error": (w.get("error") or "")[-300:]})
    for t in (org.get("tasks") or {}).values():
        if t.get("status") == "blocked":
            items.append({"kind": "task", "id": t["id"], "title": t["title"], "member": t.get("owner")})
    for r in (org.get("requests") or {}).values():  # changes to formal organizations waiting for a decision
        if r.get("status") == "pending":
            items.append(approval_item(store, org, r, lang))
    return items


def approval_item(store, org, r, lang=None):
    """A request kept in org (the cabinet, else the requester's organization) as the App shows it: the person can
    approve or deny it (POST /api/org/<org>/request). label: what it asks, in the person's language."""
    who = r.get("requester") or {}
    return {"kind": "approval", "id": r["id"], "request": r["kind"], "args": r.get("args") or {},
            "label": request_label(r, lang), "text": store.request_text(r), "reason": r.get("reason", ""),
            "at": r.get("at"), "org": org["id"], "status": r.get("status"), "requester": who.get("member"),
            "requester_org": who.get("org"), "requester_org_name": who.get("org_name"), "approver": r.get("approver"),
            "decided_by": r.get("decided_by"), "decided_at": r.get("decided_at"), "note": r.get("note"),
            "error": r.get("error")}


def copies(store, lang=None):
    """What was copied to the person (GET /api/cc): protocols with a check program, each with its note for the person,
    who proposed it (author_display, by display name) and how it stands now; unread counts every unread copy."""
    items = store.copies()
    orgs = {o["id"]: o for o in store.list_orgs()}
    for c in items:
        seats = (orgs.get(c.get("org")) or {}).get("members") or {}
        shown = lambda m, seats=seats: naming.display(seats[m], m, lang) if m in seats else m  # noqa: E731
        issued = c.get("issued_by") or {}
        if issued.get("member"):  # issued from an organization above
            c["author_display"] = i18n.t("common.member_of_org", lang, member=issued["member"],
                                         org=issued.get("name") or issued.get("org") or "")
        else:
            c["author_display"] = shown(c.get("author") or "")
        c["approved_display"] = [shown(m) for m in c.get("approved_by") or []]
    return {"items": items, "unread": store.unread_copies()}


def snapshot(store, org_id, hub=None, lang=None):
    org = store.get(org_id)
    now = time.time()
    acts = latest_activity(store, org_id)
    unread = unread_counts(store, org_id)
    secretary = secretary_of(org)
    members = [member_view(store, org, name, seat, hub, acts.get(name), unread.get(name, 0), secretary, now, lang)
               for name, seat in (org.get("members") or {}).items()]
    tasks = sorted((org.get("tasks") or {}).values(), key=lambda t: int(t["id"][1:]) if t["id"][1:].isdigit() else 0)
    protocols = [{"id": p["id"], "title": p["title"], "strength": p["strength"], "status": p["status"],
                  "version": p.get("version"), "author": p.get("author"), "votes": len(p.get("votes") or {}),
                  "uses": len(p.get("uses") or []), "guidance": p.get("guidance", ""), "rules": p.get("rules", []),
                  "trigger": p.get("trigger", ""), "retire_target": p.get("retire_target"),
                  "issued_by": p.get("issued_by"), "downward": bool(p.get("downward")), "inherit": inherits(p),
                  "supersedes": p.get("supersedes"), "replaces_above": "/" in str(p.get("supersedes") or p.get("retire_target") or ""),
                  "check": has_check(p), "summary_for_person": p.get("summary_for_person", ""),
                  "retired_by_person": p.get("retired_by") == HUMAN}
                 for p in sorted((org.get("protocols") or {}).values(), key=lambda p: int(p["id"][1:]))]
    episodes = [{"id": e["id"], "title": e["title"], "status": e["status"], "outcome": e.get("outcome"),
                 "owner": e.get("owner"), "reflections": len(e.get("reflections") or {}),
                 "participants": len(e.get("participants") or []), "opened_at": e.get("opened_at"),
                 "closed_at": e.get("closed_at"), "summary": e.get("summary", "")}
                for e in sorted((org.get("episodes") or {}).values(), key=lambda e: int(e["id"][1:]))
                if e.get("kind") != "turn"]
    # the organizations around this one: the chain above it, and the ones right below it with what waits there
    above = store.ancestors(org)
    children = []
    for child in store.descendants(org_id):
        if child.get("parent") != org_id:
            continue
        child_tasks = list((child.get("tasks") or {}).values())
        children.append({"id": child["id"], "name": child["name"], "members": len(child.get("members") or {}),
                         "kind": kind_of(child), "leader": child.get("leader"),
                         "decisions": len([d for d in decisions(store, child, hub) if d["kind"] != "task"]),
                         "blocked": sum(1 for t in child_tasks if t.get("status") == "blocked"),
                         "working": sum(1 for t in child_tasks if t.get("status") in ("open", "working"))})
    lineage = store.inheritance(org)
    inherited = [{"id": p["id"], "title": p["title"], "strength": p["strength"], "status": p["status"],
                  "version": p.get("version"), "guidance": p.get("guidance", ""), "rules": p.get("rules", []),
                  "trigger": p.get("trigger", ""), "uses": len(p.get("uses") or []), "from": a["name"],
                  "from_id": a["id"], "issued_by": p.get("issued_by"), "check": has_check(p),
                  "summary_for_person": p.get("summary_for_person", "")} for a, p in lineage["inherited"]]
    # protocols of the organizations above that this organization or one between overrode or stopped
    replaced = [{"id": p["id"], "title": p["title"], "strength": p["strength"], "from": a["name"], "from_id": a["id"],
                 "how": how, "by": by, "at": level["name"], "at_id": level["id"]}
                for a, p, level, by, how in lineage["replaced"]]
    subgroups = [{"id": o["id"], "name": o["name"], "status": o.get("status"), "leader": o.get("leader"),
                  "members": len(o.get("members") or {}), "created_at": o.get("created_at"),
                  "ended_at": o.get("ended_at")}
                 for o in store.list_orgs() if o.get("parent") == org_id and kind_of(o) == "subgroup"]
    return {
        "chats": chat_heads(store, org_id),
        "org": {"id": org["id"], "name": org["name"], "purpose": org.get("purpose", ""), "governance": org.get("governance"),
                "leader": org.get("leader"), "status": org.get("status"), "auto_wake": org.get("auto_wake", True),
                "created_at": org.get("created_at"), "secretary": secretary,
                "parent": {"id": above[0]["id"], "name": above[0]["name"]} if above else None,
                "above": [{"id": a["id"], "name": a["name"]} for a in above], "children": children,
                "kind": kind_of(org), "cabinet": bool(org.get("cabinet")), "subgroups": subgroups,
                "home": org.get("home"), "ended_at": org.get("ended_at")},
        "members": members,
        "tasks": [{k: t.get(k) for k in ("id", "title", "owner", "status", "evidence", "at", "created_by", "report", "done_at")}
                  for t in tasks],
        "protocols": protocols, "inherited_protocols": inherited, "replaced_protocols": replaced,
        "requests": [approval_item(store, org, r, lang) for r in
                     sorted((org.get("requests") or {}).values(), key=lambda r: r.get("at") or "", reverse=True)[:30]],
        "episodes": episodes,
        "decisions": decisions(store, org, hub, lang),
        "documents": [{"key": k, "revision": d["revision"], "author": d["author"], "at": d["at"]}
                      for k, d in (org.get("documents") or {}).items()],
        "stamp": change_stamp(store, org_id),
    }


def change_stamp(store, org_id):
    row = _rows(store, "SELECT (SELECT MAX(seq) FROM events WHERE org_id=?), (SELECT MAX(id) FROM messages WHERE org_id=?), "
                       "(SELECT MAX(id) FROM activity WHERE org_id=?)", (org_id, org_id, org_id))[0]
    return "%s.%s.%s" % tuple(x or 0 for x in row)


# ---------------------------------------------------------------- messages and chats
_REPLY = {"has": False, "checked": 0.0}


def has_reply_to(store):
    """Whether messages carry reply_to (threads). Another process may add the column at any time."""
    if not _REPLY["has"] and time.time() - _REPLY["checked"] > 20:
        _REPLY["checked"] = time.time()
        _REPLY["has"] = "reply_to" in {r[1] for r in _rows(store, "PRAGMA table_info(messages)")}
    return _REPLY["has"]


def _columns(store):
    return "id, sender, recipients, body, episode_id, at, COALESCE(hop, 0)" + (", reply_to" if has_reply_to(store) else "")


def _message(row):
    mid, sender, recipients, body, episode, at, hop = row[:7]
    to = json.loads(recipients)
    kind = "receipt" if (body or "").startswith(RECEIPT) else "message"
    return {"id": mid, "type": kind, "from": sender, "to": to, "body": body, "episode": episode, "at": at, "hop": hop or 0,
            "reply_to": row[7] if len(row) > 7 else None}


def chat_heads(store, org_id, depth=600):
    """For the contact list: each chat's latest message and the ids (with senders) of its recent messages, so the page
    can count what the person has not seen. Keys: "group", "member:<name>"."""
    rows = _rows(store, "SELECT %s FROM messages WHERE org_id=? ORDER BY id DESC LIMIT ?" % _columns(store), (org_id, depth))
    messages = [_message(row) for row in rows]
    where = classify(reversed(messages), group_sent(store, org_id))
    heads = {}
    for m in messages:
        head = heads.setdefault(where[m["id"]], {"last": {"id": m["id"], "from": m["from"], "body": m["body"][:140],
                                                          "at": m["at"], "type": m["type"]}, "ids": []})
        if len(head["ids"]) < 99:
            head["ids"].append([m["id"], m["from"]])
    return heads


def group_sent(store, org_id):
    """Ids of the person's messages written in the App's group chat (kept on their message.sent event)."""
    ids = set()
    for (body,) in _rows(store, "SELECT body FROM events WHERE org_id=? AND member=? AND kind='message.sent'",
                         (org_id, HUMAN)):
        try:
            b = json.loads(body or "{}")
        except ValueError:
            continue
        if b.get("channel") == "group":
            ids.add(b.get("id"))
    return ids


def classify(messages, group_ids):
    """{message id: "group" or "member:<name>" (a private chat with the person)}, for messages oldest first.
    A reply belongs to its thread's chat. The person's message to one member is private unless it was written in the
    group chat. A member's message to the person alone goes where the person last wrote to that member: an answer to
    a group message stays in the group."""
    last = {}
    out = {}
    for m in messages:
        to = m["to"]
        if m.get("reply_to") in out:
            out[m["id"]] = out[m["reply_to"]]
        elif m["from"] == HUMAN:
            if len(to) == 1 and m["id"] not in group_ids:
                out[m["id"]] = last[to[0]] = "member:" + to[0]
            else:
                out[m["id"]] = "group"
                for member in to:
                    last[member] = "group"
        elif to == [HUMAN]:
            out[m["id"]] = "group" if last.get(m["from"]) == "group" else "member:" + m["from"]
        else:
            out[m["id"]] = "group"
    return out


def _add_reads(store, org_id, messages):
    """read_by on the person's messages: which recipients have read them."""
    mine = [m["id"] for m in messages if m["from"] == HUMAN]
    reads = {}
    for i in range(0, len(mine), 400):
        chunk = mine[i:i + 400]
        for mid, who in _rows(store, "SELECT message_id, member FROM reads WHERE org_id=? AND message_id IN (%s)"
                              % ",".join("?" * len(chunk)), [org_id] + chunk):
            reads.setdefault(mid, []).append(who)
    for m in messages:
        if m["from"] == HUMAN:
            m["read_by"] = reads.get(m["id"], [])


NOTICE_KINDS = ("organization.created", "member.joined", "member.prepared", "member.carrier_replaced", "episode.opened",
                "episode.closed", "protocol.proposed", "protocol.activated", "protocol.rejected", "task.updated",
                "member.wake_gave_up", "organization.parent_set", "organization.parent_removed",
                "organization.child_added", "organization.child_removed", "organization.reached",
                "organization.cabinet_set", "organization.cabinet_unset", "organization.leader_set",
                "organization.group_created", "organization.closed", "organization.dissolved",
                "organization.child_closed", "organization.child_dissolved", "member.office_ended", "request.filed",
                "request.approved", "request.denied", "request.failed", "protocol.copied", "protocol.retired_by_person",
                "protocol.check_alert")
# how a check program failed (protocol.check_alert), in the person's words
CHECK_ERRORS = {"timeout": "view.check.timeout", "raised": "view.check.raised", "load": "view.check.load",
                "invalid": "view.check.invalid", "crashed": "view.check.crashed",
                "unavailable": "view.check.unavailable", "tampered": "view.check.tampered"}
TASK_KEYS = {"open": "task.open", "working": "task.working", "blocked": "task.blocked", "done": "task.done",
             "dropped": "task.dropped"}


def _status(status, lang):
    return i18n.t(TASK_KEYS[status], lang) if status in TASK_KEYS else str(status or "")


def notice_text(org, e, lang=None, store=None):
    b, who = e["body"] or {}, e["member"] or ""
    k = e["kind"]
    episodes = org.get("episodes") or {}
    if "/" in who:  # a member of another organization ("<org id>/<member>"), by its organization's name
        place, _, name = who.partition("/")
        try:
            there = store.get(place)["name"] if store else place
        except Exception:
            there = place
        who = i18n.t("common.member_of_org", lang, member=name, org=there)
    if k == "organization.parent_set":
        return i18n.t("view.notice.parent_set", lang, name=b.get("name") or "")
    if k in ("organization.cabinet_set", "organization.cabinet_unset"):
        return i18n.t("view.notice.cabinet_set" if k.endswith("_set") else "view.notice.cabinet_unset", lang)
    if k == "organization.leader_set":
        return i18n.t("view.notice.leader_set", lang, member=b.get("leader") or "")
    if k == "organization.group_created":
        return i18n.t("view.notice.group_created", lang, who=who, name=b.get("name") or "", leader=b.get("leader") or "")
    if k in ("organization.closed", "organization.dissolved"):
        return i18n.t("view.notice.closed" if k.endswith("closed") else "view.notice.dissolved", lang)
    if k in ("organization.child_closed", "organization.child_dissolved"):
        return i18n.t("view.notice.child_closed" if k.endswith("closed") else "view.notice.child_dissolved", lang,
                      name=b.get("name") or "")
    if k == "member.office_ended":
        return i18n.t("view.notice.office_ended", lang, who=who)
    if k.startswith("request."):
        r = (org.get("requests") or {}).get(b.get("id")) or {}
        key = {"request.filed": "view.notice.request_filed", "request.approved": "view.notice.request_approved",
               "request.denied": "view.notice.request_denied", "request.failed": "view.notice.request_failed"}[k]
        return i18n.t(key, lang, who=who, id=b.get("id") or "", what=request_label(r, lang) if r else b.get("kind", ""))
    if k == "organization.parent_removed":
        return i18n.t("view.notice.parent_removed", lang)
    if k == "organization.child_added":
        return i18n.t("view.notice.child_added", lang, name=b.get("name") or "")
    if k == "organization.child_removed":
        return i18n.t("view.notice.child_removed", lang, name=b.get("name") or "")
    if k == "organization.reached":  # a member of this organization acted in another one
        there = b.get("name") or b.get("org") or ""
        if b.get("what") == "message":
            return i18n.t("view.notice.reached_message", lang, who=who, org=there, to=b.get("to") or [])
        if b.get("what") == "task":
            return i18n.t("view.notice.reached_task", lang, who=who, org=there, id=b.get("id"),
                          title=(b.get("title") or "")[:40], owner=b.get("owner", ""), status=_status(b.get("status"), lang))
        if b.get("what") == "protocol" and b.get("retire_target"):
            return i18n.t("view.notice.reached_retire", lang, who=who, org=there, id=b["retire_target"])
        if b.get("what") == "protocol":
            return i18n.t("view.notice.reached_protocol", lang, who=who, org=there, id=b.get("id"),
                          title=b.get("title") or "")
        return None
    if k == "protocol.activated" and b.get("issued_by"):  # issued by an organization above: in effect directly
        protocols = org.get("protocols") or {}
        if b.get("retire_target"):
            gone = protocols.get(b["retire_target"]) or {}
            return i18n.t("view.notice.protocol_retired_by", lang, who=who, id=b["retire_target"],
                          title=gone.get("title") or b["retire_target"])
        return i18n.t("view.notice.protocol_issued", lang, who=who, id=b.get("id"),
                      title=(protocols.get(b.get("id")) or {}).get("title") or b.get("id"))
    if k == "protocol.copied":  # a protocol with a check program took effect: the person has a copy with a note
        title = ((org.get("protocols") or {}).get(b.get("id")) or {}).get("title") or b.get("id")
        return i18n.t("view.notice.copied", lang, id=b.get("id"), title=title)
    if k == "protocol.retired_by_person":
        if b.get("from"):  # inherited from an organization above, which the notice names ("<org id>/P3" -> P3)
            return i18n.t("view.notice.retired_by_person_above", lang, id=str(b.get("id") or "").rsplit("/", 1)[-1],
                          title=b.get("title") or "", org=b.get("from_name") or b.get("from"))
        return i18n.t("view.notice.retired_by_person", lang, id=b.get("id"), title=b.get("title") or "")
    if k == "protocol.check_alert":  # announced once a day per protocol and kind of failure
        outcome = "view.check.blocked" if b.get("on_error") == "deny" else "view.check.allowed"
        return i18n.t("view.notice.check_alert", lang, id=b.get("id"), title=b.get("title") or "",
                      kind=i18n.t(CHECK_ERRORS.get(b.get("kind"), "view.check.failed"), lang),
                      outcome=i18n.t(outcome, lang))
    if k == "organization.created":
        return i18n.t("view.notice.created", lang, who=who, name=b.get("name") or org["name"])
    if k in ("member.joined", "member.prepared"):
        if b.get("role"):
            return i18n.t("view.notice.joined_role", lang, who=who, role=b["role"])
        return i18n.t("view.notice.joined", lang, who=who)
    if k == "member.carrier_replaced":
        return i18n.t("view.notice.carrier", lang, who=who, n=b.get("carriers", "?"))
    if k in ("episode.opened", "episode.closed"):
        ep = episodes.get(b.get("id")) or {}
        if ep.get("kind") == "turn" or b.get("kind") == "turn":
            return None
        title = ep.get("title") or b.get("id")
        if k == "episode.opened":
            return i18n.t("view.notice.episode_opened", lang, who=who, id=b.get("id"), title=title)
        return i18n.t("view.notice.episode_closed", lang, who=who, id=b.get("id"), title=title,
                      outcome=b.get("outcome") or ep.get("outcome") or "")
    if k.startswith("protocol."):
        p = (org.get("protocols") or {}).get(b.get("id")) or {}
        title = p.get("title") or b.get("id")
        key = {"protocol.proposed": "view.notice.protocol_proposed", "protocol.activated": "view.notice.protocol_activated",
               "protocol.rejected": "view.notice.protocol_rejected"}[k]
        return i18n.t(key, lang, who=who, id=b.get("id"), title=title)
    if k == "task.updated":
        status = b.get("status")
        task = (org.get("tasks") or {}).get(b.get("id")) or {}
        if status == "done":
            return i18n.t("view.notice.task_done", lang, who=who, id=b.get("id"), title=task.get("title", "")[:40])
        if status == "blocked":
            return i18n.t("view.notice.task_blocked", lang, who=who, id=b.get("id"))
        if "/" in (e["member"] or ""):  # set by a member of an organization above
            return i18n.t("view.notice.task_set", lang, who=who, id=b.get("id"), title=task.get("title", "")[:40],
                          owner=b.get("owner", ""), status=_status(status, lang))
        return None
    if k == "member.wake_gave_up":
        return i18n.t("view.notice.wake_failed", lang, who=who)
    return None


REQUEST_KEYS = {"create": "view.request.create", "parent": "view.request.parent", "leader": "view.request.leader",
                "dissolve": "view.request.dissolve"}


def request_label(r, lang=None):
    """What a request asks, in the person's language."""
    a = r.get("args") or {}
    return i18n.t(REQUEST_KEYS.get(r.get("kind"), "view.request.dissolve"), lang, name=a.get("name") or "",
                  org=a.get("org_name") or a.get("org") or "", parent=a.get("parent_name") or "-",
                  member=a.get("member") or "")


def orgchart(store, hub=None, lang=None):
    """The organization chart: every organization with its parent, kind, leader, members and what waits on the
    person, and the sessions that hold seats in several organizations (GET /api/orgchart)."""
    orgs = store.list_orgs()
    nodes = []
    for org in sorted(orgs, key=lambda o: o.get("created_at") or ""):
        members = org.get("members") or {}
        leader = members.get(org.get("leader") or "") or {}
        nodes.append({"id": org["id"], "name": org["name"], "parent": org.get("parent"), "kind": kind_of(org),
                      "purpose": org.get("purpose", ""), "ended_at": org.get("ended_at"),
                      "cabinet": bool(org.get("cabinet")), "status": org.get("status"), "governance": org.get("governance"),
                      "leader": org.get("leader"),
                      "leader_display": naming.display(leader, org["leader"], lang) if org.get("leader") and leader else "",
                      "members": len(members),
                      "decisions": len([d for d in decisions(store, org, hub, lang) if d["kind"] != "task"])
                      if org.get("status") == "active" else 0,
                      "ex_officio": [n for n, s in members.items() if s.get("ex_officio")]})
    sessions = {}
    with store.db() as db:
        mains = db.execute("SELECT actor, org_id, member FROM actors").fetchall()
        others = db.execute("SELECT actor, org_id, member FROM seats").fetchall()
    active = {o["id"]: o for o in orgs if o.get("status") == "active"}
    # seats as Store.seats_of counts them: a session's main seat, and a seat beside it while the session still carries
    # it (an older plugin may have handed that seat to another session without clearing the row)
    for rows, main in ((mains, True), (others, False)):
        for actor, org_id, member in rows:
            seat = ((active.get(org_id) or {}).get("members") or {}).get(member)
            if seat is not None and (main or seat.get("carrier") == actor):
                sessions.setdefault(actor, {}).setdefault(org_id, member)
    shared = [{"session": actor.split(":", 1)[-1].split("/", 1)[0][:8], "harness": harness_of(actor),
               "seats": [{"org": o, "member": m} for o, m in seats.items()]}
              for actor, seats in sorted(sessions.items()) if len(seats) > 1]
    cab = store.cabinet()
    return {"orgs": nodes, "shared": shared, "cabinet": cab["id"] if cab else None,
            "secretary_general": {"org": cab["id"], "member": cab.get("leader")} if cab else None}


def harness_of(actor):
    head, sep, _ = (actor or "").partition(":")
    return head if sep else "claude-code"


def chat(store, org_id, kind="group", member=None, limit=400, before=None, lang=None):
    """Items of one chat, oldest first. group: every message between members and what the person wrote to several
    members, with organization notices in between; private: the person and one member. Replies stay in their thread:
    a thread's first message carries thread {count, last_at, people}."""
    org = store.get(org_id)
    sql = "SELECT %s FROM messages WHERE org_id=?" % _columns(store)
    args = [org_id]
    if before:
        sql += " AND id<?"
        args.append(int(before))
    messages = [_message(r) for r in _rows(store, sql + " ORDER BY id DESC LIMIT 5000", args)]
    where = classify(reversed(messages), group_sent(store, org_id))
    key = "group" if kind == "group" else "member:%s" % member
    in_chat = [m for m in messages if where[m["id"]] == key]
    replies = {}
    for m in reversed(in_chat):
        if m.get("reply_to"):
            replies.setdefault(m["reply_to"], []).append(m)
    matching = [m for m in in_chat if not m.get("reply_to")]
    picked = list(reversed(matching[:limit]))
    more = len(matching) > limit
    for m in picked:
        thread = replies.get(m["id"])
        if thread:
            m["thread"] = {"count": len(thread), "last_at": thread[-1]["at"],
                           "people": list(dict.fromkeys(r["from"] for r in thread))[:5]}
    _add_reads(store, org_id, picked)
    if kind != "group":
        return {"items": picked, "more": more}
    # organization notices between the messages (all of them when the whole history fits)
    since = picked[0]["at"] if picked and (before or more) else ""
    until = picked[-1]["at"] if picked and before else None
    events = _rows(store, "SELECT seq, member, kind, body, at FROM events WHERE org_id=? AND at>=? ORDER BY seq",
                   (org_id, since))
    notices = []
    for seq, who, k, body, at in events:
        if k not in NOTICE_KINDS or (until and at > until):
            continue
        text = notice_text(org, {"member": who, "kind": k, "body": json.loads(body or "{}")}, lang, store)
        if text:
            notices.append({"id": "e%d" % seq, "type": "notice", "text": text, "at": at, "seq": seq})
    merged = sorted(picked + notices, key=lambda x: (x["at"], 0 if x["type"] == "notice" else 1))
    return {"items": merged, "more": more}


def thread(store, org_id, root_id):
    """A thread: its first message and every reply, oldest first."""
    root_id = int(root_id)
    threads = has_reply_to(store)
    where = "id=? OR reply_to=?" if threads else "id=?"
    args = (org_id, root_id, root_id) if threads else (org_id, root_id)
    items = [_message(r) for r in _rows(store, "SELECT %s FROM messages WHERE org_id=? AND (%s) ORDER BY id"
                                        % (_columns(store), where), args)]
    _add_reads(store, org_id, items)
    root = next((m for m in items if m["id"] == root_id), None)
    return {"root": root, "replies": [m for m in items if m["id"] != root_id]}


# ---------------------------------------------------------------- transcripts (context and trajectory)
_STEPS = {}  # (path, full) -> (mtime, size, steps): a transcript is parsed again only after it changed
STEP_CLIP = 20000


def _steps(harness, actor, path, full=False):
    key = (str(path), bool(full))
    stat = long_path(path).stat()
    hit = _STEPS.get(key)
    if hit and hit[0] == stat.st_mtime and hit[1] == stat.st_size:
        return hit[2]
    reader = trajectory.codex_steps if harness == "codex" else trajectory.claude_steps
    subagent = harness != "codex" and "/" in actor
    # a Claude Code subagent's own file marks every entry as a side chain, which the reader skips unless full
    steps = list(reader(long_path(path), STEP_CLIP, full or subagent))
    if subagent and not full:
        steps = [s for s in steps if s["role"] not in ("thinking", "context")]
    while len(_STEPS) >= 24:
        _STEPS.pop(next(iter(_STEPS)))
    _STEPS[key] = (stat.st_mtime, stat.st_size, steps)
    return steps


def transcript(actor, limit=300, before=None, full=False):
    """A session's own record, as steps (user / assistant / tool_call / tool_result ...), newest `limit` before an index."""
    harness, session, path = locate(actor)
    if path is None:
        return {"harness": harness, "session": session, "steps": [], "total": 0, "path": None}
    try:
        steps = _steps(harness, actor, path, full)
    except OSError as error:
        return {"harness": harness, "session": session, "steps": [], "total": 0, "path": str(path), "error": str(error)}
    end = len(steps) if before is None else max(0, min(len(steps), int(before)))
    start = max(0, end - limit)
    picked = [dict(s, i=i) for i, s in enumerate(steps[start:end], start)]
    return {"harness": harness, "session": session, "path": str(path), "steps": picked, "total": len(steps), "start": start}


def convo(actor, brief=240):
    """A session's whole conversation for its chat: what was said, in full, and each tool call and result as a short
    line (step() gives its full text)."""
    harness, session, path = locate(actor)
    if path is None:
        return {"harness": harness, "session": session, "steps": [], "total": 0, "path": None}
    try:
        steps = _steps(harness, actor, path)
    except OSError as error:
        return {"harness": harness, "session": session, "steps": [], "total": 0, "path": str(path), "error": str(error)}
    out = []
    for i, s in enumerate(steps):
        if s["role"] in ("user", "assistant"):
            out.append(dict(s, i=i))
        elif s["role"] in ("tool_call", "tool_result"):
            text = s.get("text") or ""
            out.append({"i": i, "role": s["role"], "tool": s.get("tool", ""), "at": s.get("at", ""),
                        "error": bool(s.get("error")), "text": text[:brief], "cut": len(text) > brief})
    return {"harness": harness, "session": session, "path": str(path), "steps": out, "total": len(steps)}


def step(actor, index):
    """One step of a session's record with its full text."""
    harness, session, path = locate(actor)
    if path is None:
        return {"missing": True}
    steps = _steps(harness, actor, path)
    index = int(index)
    return dict(steps[index], i=index) if 0 <= index < len(steps) else {"missing": True}
