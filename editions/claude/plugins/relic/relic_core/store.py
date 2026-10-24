"""Relic organization state for Claude Code.

Three kinds of state are kept apart, following the Relic paper:
  * member-local state  -> private notes of the current carrier of a seat
  * shared work state   -> documents, tasks, messages, episodes
  * protocol state      -> organization-owned weak/strong protocols and role mappings

A *member* is an organizational seat (name + role). A *carrier* is the agent
instance currently occupying the seat (a Claude Code session or subagent).
Replacing a carrier resets member-local state and keeps everything else.
"""
import contextlib
import fnmatch
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
# Output fragments that signal friction between members' work (rejected pushes, conflicting changes).
FRICTION_MARKERS = ("[rejected]", "non-fast-forward", "CONFLICT", "could not apply", "Merge conflict",
                    "error: failed to push", "Your branch and 'origin/", "have diverged")


class OrgError(ValueError):
    pass


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def short_id(prefix):
    return prefix + uuid.uuid4().hex[:6]


def data_home():
    env = os.getenv("RELIC_HOME")
    return Path(env) if env else Path.home() / ".claude" / "relic"


def short_tool(tool):
    return tool.rsplit("__", 1)[-1] if tool.startswith("mcp__") else tool


def is_relic_tool(tool):
    return tool.startswith("mcp__plugin_relic_org__")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# --------------------------------------------------------------------------
# Strong protocol rules: a small, bounded rule language bound to PreToolUse.
# --------------------------------------------------------------------------
RULE_FIELDS = {"effect", "tools", "input_contains", "path_glob", "members", "roles",
               "except_members", "except_roles", "before", "reason"}


def validate_rules(rules):
    if not isinstance(rules, list) or not rules:
        raise OrgError("A strong protocol needs at least one rule. Prose alone belongs in a weak protocol.")
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) - RULE_FIELDS:
            raise OrgError("Unknown rule field. Allowed: " + ", ".join(sorted(RULE_FIELDS)))
        if rule.get("effect") not in ("deny", "require_review", "require_before"):
            raise OrgError("Rule effect must be deny, require_review or require_before.")
        tools = rule.get("tools")
        if not isinstance(tools, list) or not tools or not all(isinstance(t, str) and t for t in tools):
            raise OrgError("Each rule needs tool name patterns, e.g. [\"Bash\"] or [\"Edit\", \"Write\"].")
        if any(t.startswith("mcp__plugin_relic_org__") for t in tools):
            raise OrgError("Rules cannot gate the organization's own governance tools.")
        broad = all(t in ("*", "**") for t in tools)
        if broad and not (rule.get("input_contains") or rule.get("path_glob")):
            # Bounded binding: no universal veto over every action.
            raise OrgError("A rule matching every tool must be narrowed by input_contains or path_glob.")
        for key in ("input_contains", "members", "roles", "except_members", "except_roles"):
            if key in rule and (not isinstance(rule[key], list) or not all(isinstance(x, str) and x for x in rule[key])):
                raise OrgError(key + " must be a list of strings.")
        if "path_glob" in rule and not isinstance(rule["path_glob"], str):
            raise OrgError("path_glob must be a string.")
        if rule["effect"] == "require_before":
            before = rule.get("before")
            if not isinstance(before, dict) or not before.get("tools"):
                raise OrgError("require_before needs before: {tools: [...], input_contains?: [...]}.")


def _tool_matches(patterns, tool):
    names = {tool, short_tool(tool)}
    return any(fnmatch.fnmatchcase(n, p) for n in names for p in patterns)


def _contains(needles, tool_input):
    body = canonical(tool_input).casefold()
    return all(n.casefold() in body for n in needles)


def _path_of(tool_input):
    for key in ("file_path", "notebook_path", "path"):
        if isinstance(tool_input.get(key), str):
            return tool_input[key].replace("\\", "/")
    return None


def rule_applies(rule, member, role, tool, tool_input):
    if rule.get("members") and member not in rule["members"]:
        return False
    if rule.get("roles") and role not in rule["roles"]:
        return False
    if member in rule.get("except_members", []) or (role and role in rule.get("except_roles", [])):
        return False
    if not _tool_matches(rule["tools"], tool):
        return False
    if rule.get("input_contains") and not _contains(rule["input_contains"], tool_input):
        return False
    if rule.get("path_glob"):
        path = _path_of(tool_input)
        if not path or not (fnmatch.fnmatch(path, rule["path_glob"]) or fnmatch.fnmatch(path, "*/" + rule["path_glob"].lstrip("/"))):
            return False
    return True


# --------------------------------------------------------------------------
class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_home() / "relic.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS orgs(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS actors(actor TEXT PRIMARY KEY, org_id TEXT, member TEXT, bound_at TEXT);
                CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT, sender TEXT,
                    recipients TEXT, body TEXT, episode_id TEXT, at TEXT);
                CREATE TABLE IF NOT EXISTS reads(org_id TEXT, message_id INTEGER, member TEXT, at TEXT,
                    PRIMARY KEY(org_id, message_id, member));
                CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT, member TEXT,
                    tool TEXT, kind TEXT, summary TEXT, failed INTEGER, at REAL);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT, member TEXT,
                    kind TEXT, body TEXT, at TEXT);
            """)

    @contextlib.contextmanager
    def db(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # ---------------- organization records ----------------
    def _load(self, db, org_id):
        row = db.execute("SELECT body FROM orgs WHERE id=?", (org_id,)).fetchone()
        if not row:
            raise OrgError("Unknown organization " + str(org_id))
        return json.loads(row[0])

    def _save(self, db, org):
        org["revision"] = org.get("revision", 0) + 1
        db.execute("UPDATE orgs SET body=? WHERE id=?", (json.dumps(org, ensure_ascii=False), org["id"]))

    def _event(self, db, org_id, member, kind, body=None):
        db.execute("INSERT INTO events(org_id,member,kind,body,at) VALUES(?,?,?,?,?)",
                   (org_id, member, kind, json.dumps(body or {}, ensure_ascii=False), now()))

    @contextlib.contextmanager
    def change(self, org_id):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            org = self._load(db, org_id)
            yield org, db
            self._save(db, org)

    def get(self, org_id):
        with self.db() as db:
            return self._load(db, org_id)

    def list_orgs(self):
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT body FROM orgs")]

    def whoami(self, actor):
        if not actor:
            return None, None
        with self.db() as db:
            row = db.execute("SELECT org_id, member FROM actors WHERE actor=?", (actor,)).fetchone()
            if not row:
                return None, None
            org = self._load(db, row[0])
        if org["status"] != "active" or row[1] not in org["members"]:
            return None, None
        return org, row[1]

    def require(self, actor):
        org, member = self.whoami(actor)
        if not org:
            raise OrgError("You are not in a Relic organization yet. Call create or join first.")
        return org, member

    # ---------------- formation and membership ----------------
    def create(self, actor, name, purpose, member, role="", governance="leader"):
        if not name.strip() or not member.strip():
            raise OrgError("Give the organization a name and yourself a member name.")
        if governance not in ("leader", "peer"):
            raise OrgError("governance must be leader or peer.")
        org = {"id": short_id("org_"), "name": name.strip(), "purpose": purpose, "governance": governance,
               "leader": member if governance == "leader" else None, "status": "active", "created_at": now(),
               "revision": 0, "members": {}, "documents": {}, "tasks": {}, "episodes": {}, "protocols": {},
               "reviews": {}, "automatic_reflection": True,
               "counters": {"task": 0, "episode": 0, "protocol": 0, "review": 0}}
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO orgs VALUES(?,?)", (org["id"], json.dumps(org, ensure_ascii=False)))
            self._event(db, org["id"], member, "organization.created", {"name": name, "governance": governance})
        self.join(actor, org["id"], member, role)
        return self.get(org["id"])

    def join(self, actor, org_id, member, role=""):
        member = member.strip()
        if not member or any(c in member for c in " /\\:"):
            raise OrgError("Member names are short words without spaces, e.g. alice or release.")
        replaced = None
        with self.change(org_id) as (org, db):
            if org["status"] != "active":
                raise OrgError("Organization is not active.")
            seat = org["members"].get(member)
            if seat is None:
                seat = org["members"][member] = {"role": role, "joined_at": now(), "carrier": actor,
                                                 "carriers": 1, "notes": [], "open_episode": None}
                self._event(db, org_id, member, "member.joined", {"role": role})
                for ep in org["episodes"].values():
                    if ep.get("all_members") and ep["status"] == "open" and member not in ep["participants"]:
                        ep["participants"].append(member)
            else:
                if seat["carrier"] != actor:
                    # Carrier turnover: the seat, its role, tasks and protocols persist;
                    # the previous carrier's private notes do not.
                    replaced = seat["carrier"]
                    seat.update(carrier=actor, carriers=seat.get("carriers", 1) + 1, notes=[])
                    self._event(db, org_id, member, "member.carrier_replaced", {"carriers": seat["carriers"]})
                if role:
                    seat["role"] = role
            db.execute("INSERT OR REPLACE INTO actors VALUES(?,?,?,?)", (actor, org_id, member, now()))
            if replaced:
                db.execute("DELETE FROM actors WHERE actor=? AND org_id=?", (replaced, org_id))
        return {"org_id": org_id, "member": member, "role": self.get(org_id)["members"][member]["role"],
                "carrier_replaced": bool(replaced)}

    def bind_alias(self, actor, org_id, member):
        """Bind an additional actor key to an existing seat without turnover (used for resumed sessions)."""
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO actors VALUES(?,?,?,?)", (actor, org_id, member, now()))

    # ---------------- messages ----------------
    def send(self, actor, to, body, episode_id=None):
        org, member = self.require(actor)
        if not body or not body.strip():
            raise OrgError("Empty message.")
        if not to or to == ["all"] or to == "all":
            recipients = [m for m in org["members"] if m != member]
        else:
            recipients = list(dict.fromkeys(to if isinstance(to, list) else [to]))
            unknown = set(recipients) - set(org["members"])
            if unknown:
                raise OrgError("Unknown members: " + ", ".join(sorted(unknown)))
        if not recipients:
            raise OrgError("No other members yet.")
        with self.db() as db:
            cur = db.execute("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at) VALUES(?,?,?,?,?,?)",
                             (org["id"], member, json.dumps(recipients), body, episode_id, now()))
            self._event(db, org["id"], member, "message.sent", {"id": cur.lastrowid, "to": recipients})
            return {"message_id": cur.lastrowid, "to": recipients}

    def unread(self, actor, mark=True, limit=20):
        org, member = self.whoami(actor)
        if not org:
            return []
        with self.db() as db:
            rows = db.execute("""SELECT m.id, m.sender, m.recipients, m.body, m.episode_id, m.at FROM messages m
                WHERE m.org_id=? AND m.sender<>? AND NOT EXISTS
                (SELECT 1 FROM reads r WHERE r.org_id=m.org_id AND r.message_id=m.id AND r.member=?)
                ORDER BY m.id LIMIT ?""", (org["id"], member, member, limit)).fetchall()
            out = []
            for mid, sender, recipients, body, ep, at in rows:
                rec = json.loads(recipients)
                if member not in rec:
                    continue
                out.append({"id": mid, "from": sender, "to": rec, "body": body, "episode_id": ep, "at": at})
                if mark:
                    db.execute("INSERT OR IGNORE INTO reads VALUES(?,?,?,?)", (org["id"], mid, member, now()))
            if mark and out:
                self._event(db, org["id"], member, "message.read", {"ids": [m["id"] for m in out]})
        return out

    def history(self, org_id, limit=30):
        with self.db() as db:
            rows = db.execute("SELECT id,sender,recipients,body,at FROM messages WHERE org_id=? ORDER BY id DESC LIMIT ?",
                              (org_id, limit)).fetchall()
        return [{"id": r[0], "from": r[1], "to": json.loads(r[2]), "body": r[3], "at": r[4]} for r in reversed(rows)]

    # ---------------- shared work ----------------
    def work(self, actor, op, a):
        org, member = self.require(actor)
        with self.change(org["id"]) as (org, db):
            if op == "doc_write":
                key = a.get("key")
                if not key or not isinstance(a.get("body"), str):
                    raise OrgError("doc_write needs key and body.")
                old = org["documents"].get(key)
                revision = old["revision"] if old else 0
                if a.get("expected_revision", revision) != revision:
                    raise OrgError("Document '%s' changed (now revision %d). Read it and merge before writing." % (key, revision))
                org["documents"][key] = {"body": a["body"], "revision": revision + 1, "author": member, "at": now()}
                self._event(db, org["id"], member, "document.written", {"key": key, "revision": revision + 1})
                return {"key": key, "revision": revision + 1}
            if op == "doc_read":
                key = a.get("key")
                if key:
                    if key not in org["documents"]:
                        raise OrgError("No document " + key)
                    return {"key": key, **org["documents"][key]}
                return {"documents": {k: {"revision": v["revision"], "author": v["author"], "at": v["at"]}
                                      for k, v in org["documents"].items()}}
            if op == "task":
                tid = a.get("task_id")
                if tid and tid not in org["tasks"]:
                    raise OrgError("Unknown task " + tid)
                if not tid:
                    if not a.get("title"):
                        raise OrgError("A new task needs a title.")
                    org["counters"]["task"] += 1
                    tid = "T%d" % org["counters"]["task"]
                    org["tasks"][tid] = {"id": tid, "title": a["title"], "owner": a.get("owner") or member,
                                         "status": "open", "evidence": [], "created_by": member, "at": now()}
                task = org["tasks"][tid]
                for key in ("title", "owner", "status"):
                    if a.get(key):
                        task[key] = a[key]
                if task["owner"] not in org["members"]:
                    raise OrgError("Task owner must be a member.")
                if task["status"] not in ("open", "working", "blocked", "done", "dropped"):
                    raise OrgError("status: open, working, blocked, done or dropped.")
                if a.get("evidence"):
                    task["evidence"] = list(task["evidence"]) + list(a["evidence"])
                if task["status"] == "done" and not task["evidence"]:
                    raise OrgError("Mark done with evidence (commit, test output, file).")
                task["at"] = now()
                self._event(db, org["id"], member, "task.updated", {"id": tid, "status": task["status"], "owner": task["owner"]})
                return task
            if op == "role":
                target = a.get("member") or member
                if target not in org["members"]:
                    raise OrgError("Unknown member " + target)
                if target != member and org.get("leader") not in (None, member):
                    raise OrgError("Only the leader assigns roles to others; members set their own.")
                org["members"][target]["role"] = a.get("role", "")
                self._event(db, org["id"], member, "role.set", {"member": target, "role": a.get("role", "")})
                return {"member": target, "role": a.get("role", "")}
            if op == "note":
                if not a.get("body"):
                    raise OrgError("note needs body.")
                org["members"][member]["notes"] = (org["members"][member].get("notes", []) + [a["body"]])[-30:]
                return {"private_notes": len(org["members"][member]["notes"])}
            raise OrgError("Unknown work op " + str(op))

    # ---------------- episodes and reflection ----------------
    def episode(self, actor, op, a):
        org, member = self.require(actor)
        with self.change(org["id"]) as (org, db):
            if op == "open":
                if not a.get("title"):
                    raise OrgError("open needs a title.")
                everyone = not a.get("participants")
                participants = list(org["members"]) if everyone else list(dict.fromkeys([member] + list(a["participants"])))
                if set(participants) - set(org["members"]):
                    raise OrgError("Participants must be members.")
                org["counters"]["episode"] += 1
                eid = "E%d" % org["counters"]["episode"]
                # Without an explicit list the episode belongs to the whole organization, including members who join later.
                org["episodes"][eid] = {"id": eid, "title": a["title"], "owner": member, "participants": participants,
                                        "all_members": everyone, "status": "open", "opened_at": now(), "reflections": {}}
                self._event(db, org["id"], member, "episode.opened", {"id": eid})
                return org["episodes"][eid]
            ep = org["episodes"].get(a.get("episode_id"))
            if not ep:
                raise OrgError("Unknown episode.")
            if op == "close":
                if member not in (ep["owner"], org.get("leader")):
                    raise OrgError("The episode owner or leader closes it.")
                if a.get("outcome") not in ("success", "failure", "partial", "cancelled"):
                    raise OrgError("outcome: success, failure, partial or cancelled.")
                if not a.get("summary"):
                    raise OrgError("close needs a short summary of what happened.")
                ep.update(status="closed", outcome=a["outcome"], summary=a["summary"],
                          evidence=a.get("evidence", []), closed_at=now())
                self._event(db, org["id"], member, "episode.closed", {"id": ep["id"], "outcome": a["outcome"]})
                return ep
            if op == "reflect":
                if member not in ep["participants"]:
                    raise OrgError("Reflect on episodes you took part in.")
                if not a.get("body"):
                    raise OrgError("reflect needs body.")
                ep["reflections"][member] = {"body": a["body"], "at": now()}
                self._event(db, org["id"], member, "episode.reflected", {"id": ep["id"]})
                others = []
                for other in org["episodes"].values():
                    for who, r in other["reflections"].items():
                        if who != member:
                            others.append({"episode": other["id"], "by": who, "body": r["body"][:400]})
                return {"recorded": True, "friction_in_this_episode": ep.get("friction", [])[-6:],
                        "recent_reflections_by_others": others[-6:],
                        "hint": "If the friction you described also appears in others' reflections or recurred in your own work, "
                                "propose a protocol so the lesson becomes organization-owned instead of staying in one carrier."}
            raise OrgError("Unknown episode op " + str(op))

    def reflection_due(self, org, member):
        # Turn episodes ask for reflection only when friction was observed; shared episodes always do.
        return [e["id"] for e in org["episodes"].values()
                if e["status"] == "closed" and member in e["participants"] and member not in e["reflections"]
                and (e.get("kind") != "turn" or e.get("friction"))]

    # ---------------- protocols and governance ----------------
    def _threshold(self, org):
        n = len(org["members"])
        return min(2, n) if org["governance"] == "leader" else n // 2 + 1

    def _maybe_activate(self, org, db, p):
        approvals = {m for m, v in p["votes"].items() if v["vote"] == "approve" and m in org["members"]}
        rejects = {m for m, v in p["votes"].items() if v["vote"] == "reject" and m in org["members"]}
        need = self._threshold(org)
        leader_ok = org["governance"] != "leader" or org["leader"] in approvals
        if leader_ok and len(approvals) >= need:
            if p.get("retire_target"):
                target = org["protocols"].get(p["retire_target"])
                if target and target["status"] == "active":
                    target.update(status="retired", retired_at=now(), retired_by=p["id"])
                p.update(status="enacted", activated_at=now())
            else:
                if p.get("supersedes"):
                    parent = org["protocols"].get(p["supersedes"])
                    if parent and parent["status"] == "active":
                        parent.update(status="superseded", superseded_by=p["id"])
                p.update(status="active", activated_at=now())
            self._event(db, org["id"], p["author"], "protocol.activated", {"id": p["id"], "strength": p["strength"]})
        elif len(rejects) > len(org["members"]) - need or (org["governance"] == "leader" and org["leader"] in rejects):
            p.update(status="rejected")
            self._event(db, org["id"], p["author"], "protocol.rejected", {"id": p["id"]})

    def protocol(self, actor, op, a):
        org, member = self.require(actor)
        if op == "list":
            return {pid: {k: p[k] for k in ("title", "strength", "status", "version", "author") if k in p}
                    for pid, p in org["protocols"].items()}
        with self.change(org["id"]) as (org, db):
            if op == "propose":
                strength = a.get("strength", "weak")
                if strength not in ("weak", "strong"):
                    raise OrgError("strength: weak (guidance) or strong (executable rules).")
                if not a.get("title") or not a.get("rationale"):
                    raise OrgError("A proposal needs a title and a rationale grounded in what happened.")
                evidence = a.get("evidence") or []
                retire_target = a.get("retire_target")
                if retire_target:
                    if org["protocols"].get(retire_target, {}).get("status") != "active":
                        raise OrgError("Retirement proposals target an active protocol.")
                elif strength == "weak":
                    if a.get("rules"):
                        raise OrgError("Weak protocols carry guidance only; use strength strong for rules.")
                    if not all(isinstance(a.get(k), str) and a[k].strip() for k in ("guidance", "trigger")):
                        raise OrgError("A weak protocol needs guidance and a trigger (when it applies).")
                    if not evidence:
                        raise OrgError("Point to the evidence behind it: episode ids, message ids, task ids, files or commits.")
                else:
                    ep = org["episodes"].get(a.get("episode_id"))
                    if not ep or ep["status"] != "closed" or member not in ep["reflections"]:
                        raise OrgError("A strong protocol is proposed from a closed episode after you reflected on it.")
                    validate_rules(a.get("rules"))
                parent = org["protocols"].get(a.get("supersedes")) if a.get("supersedes") else None
                if a.get("supersedes") and (not parent or parent["status"] != "active"):
                    raise OrgError("A revision must supersede an active protocol.")
                org["counters"]["protocol"] += 1
                pid = "P%d" % org["counters"]["protocol"]
                p = {"id": pid, "title": a["title"], "rationale": a["rationale"], "strength": strength,
                     "guidance": a.get("guidance", ""), "trigger": a.get("trigger", ""), "scope": a.get("scope", ""),
                     "rules": a.get("rules", []) if strength == "strong" else [], "evidence": evidence,
                     "episode_id": a.get("episode_id"), "supersedes": a.get("supersedes"), "retire_target": retire_target,
                     "version": (parent["version"] + 1) if parent else 1, "author": member, "status": "proposed",
                     "votes": {member: {"vote": "approve", "reason": "author", "at": now()}}, "uses": [], "created_at": now()}
                org["protocols"][pid] = p
                self._event(db, org["id"], member, "protocol.proposed", {"id": pid, "strength": strength})
                self._maybe_activate(org, db, p)
                return p
            p = org["protocols"].get(a.get("protocol_id"))
            if not p:
                raise OrgError("Unknown protocol.")
            if op == "vote":
                if p["status"] != "proposed":
                    raise OrgError("Only proposals take votes; this one is " + p["status"] + ".")
                if a.get("vote") not in ("approve", "reject") or not a.get("reason"):
                    raise OrgError("vote approve or reject, with a reason.")
                p["votes"][member] = {"vote": a["vote"], "reason": a["reason"], "at": now()}
                self._event(db, org["id"], member, "protocol.voted", {"id": p["id"], "vote": a["vote"]})
                self._maybe_activate(org, db, p)
                return p
            if op == "use":
                if p["status"] != "active":
                    raise OrgError("Record use of active protocols only.")
                if a.get("outcome") not in ("followed", "deviated", "inapplicable") or not a.get("note"):
                    raise OrgError("use needs outcome (followed, deviated, inapplicable) and a note on the concrete work.")
                p["uses"].append({"by": member, "outcome": a["outcome"], "note": a["note"][:500], "at": now()})
                self._event(db, org["id"], member, "protocol.used", {"id": p["id"], "outcome": a["outcome"]})
                return {"id": p["id"], "uses": len(p["uses"])}
            raise OrgError("Unknown protocol op " + str(op))

    # ---------------- runtime binding (called from PreToolUse) ----------------
    def gate(self, actor, tool, tool_input):
        """Return (allowed, reasons). Records review requests for require_review rules."""
        org, member = self.whoami(actor)
        if not org or is_relic_tool(tool):
            return True, []
        role = org["members"][member].get("role", "")
        reasons, consumed = [], []
        last_edit = None
        for p in org["protocols"].values():
            if p["status"] != "active" or p["strength"] != "strong":
                continue
            for rule in p["rules"]:
                if not rule_applies(rule, member, role, tool, tool_input):
                    continue
                label = "%s %s" % (p["id"], p["title"])
                if rule["effect"] == "deny":
                    reasons.append("%s: %s" % (label, rule.get("reason", "blocked by an adopted protocol.")))
                elif rule["effect"] == "require_before":
                    if last_edit is None:
                        last_edit = self._last_activity(org["id"], member, kind="edit") or 0.0
                    if not self._has_activity_since(org["id"], member, rule["before"], last_edit):
                        reasons.append("%s: %s" % (label, rule.get("reason") or
                                       "first run %s after your latest edit." % rule["before"]["tools"]))
                else:
                    approved = self._approved_review(org, member, tool, tool_input)
                    if approved:
                        consumed.append(approved)
                    else:
                        rid = self._request_review(org["id"], member, p["id"], tool, tool_input)
                        reasons.append("%s: another member must approve this exact action. Review request %s is open; "
                                       "ask a member to run review approve %s, then retry the same call." % (label, rid, rid))
        if not reasons and consumed:
            with self.change(org["id"]) as (o, db):
                for rid in consumed:
                    o["reviews"][rid]["status"] = "used"
        if reasons:
            self.turn_note(actor, friction="blocked by protocol: " + reasons[0][:120])
        with self.db() as db:
            if reasons:
                self._event(db, org["id"], member, "protocol.blocked", {"tool": tool, "reasons": reasons})
            elif consumed:
                self._event(db, org["id"], member, "protocol.review_used", {"tool": tool, "reviews": consumed})
        return not reasons, reasons

    def _approved_review(self, org, member, tool, tool_input):
        key = canonical([tool, tool_input])
        for rid, r in org["reviews"].items():
            if r["subject"] == member and r["status"] == "approved" and r["action"] == key:
                return rid
        return None

    def _request_review(self, org_id, member, pid, tool, tool_input):
        key = canonical([tool, tool_input])
        with self.change(org_id) as (org, db):
            for rid, r in org["reviews"].items():
                if r["subject"] == member and r["status"] == "pending" and r["action"] == key:
                    return rid
            org["counters"]["review"] += 1
            rid = "R%d" % org["counters"]["review"]
            summary = tool_input.get("command") or tool_input.get("file_path") or canonical(tool_input)[:200]
            org["reviews"][rid] = {"id": rid, "protocol_id": pid, "subject": member, "tool": tool, "summary": str(summary)[:300],
                                   "action": key, "status": "pending", "at": now()}
            self._event(db, org_id, member, "review.requested", {"id": rid, "protocol_id": pid})
            return rid

    def review(self, actor, op, a):
        org, member = self.require(actor)
        if op == "list":
            return [{k: r[k] for k in ("id", "protocol_id", "subject", "tool", "summary", "status")}
                    for r in org["reviews"].values() if r["status"] == "pending"]
        if op != "approve":
            raise OrgError("review ops: list, approve.")
        with self.change(org["id"]) as (org, db):
            r = org["reviews"].get(a.get("request_id"))
            if not r or r["status"] != "pending":
                raise OrgError("No pending review with that id.")
            if r["subject"] == member:
                raise OrgError("Another member has to approve your action.")
            if not a.get("note"):
                raise OrgError("Say what you checked.")
            r.update(status="approved", reviewer=member, note=a["note"][:500], approved_at=now())
            self._event(db, org["id"], member, "review.approved", {"id": r["id"], "subject": r["subject"]})
            return r

    # ---------------- activity (called from PostToolUse) ----------------
    def record_activity(self, actor, tool, tool_input, failed=False, output=""):
        org, member = self.whoami(actor)
        if not org or is_relic_tool(tool):
            return
        kind = "edit" if short_tool(tool) in EDIT_TOOLS else ("run" if tool == "Bash" else "other")
        summary = tool_input.get("command") or _path_of(tool_input) or ""
        signals = [m for m in FRICTION_MARKERS if m in (output or "")]
        with self.db() as db:
            db.execute("INSERT INTO activity(org_id,member,tool,kind,summary,failed,at) VALUES(?,?,?,?,?,?,?)",
                       (org["id"], member, tool, kind, str(summary)[:500], int(bool(failed)), time.time()))
        self.turn_note(actor, friction=("tool failed: " + str(summary)[:120]) if failed else
                       (("friction (%s): %s" % (", ".join(signals), str(summary)[:120])) if signals else None))

    # Automatic turn episodes: each carrier's stretch of work is an episode. A turn with friction signals
    # (failed calls, blocked actions, rejected pushes, conflicts) asks its member for a reflection.
    def turn_note(self, actor, friction=None):
        org, member = self.whoami(actor)
        if not org or not org.get("automatic_reflection", True):
            return
        with self.change(org["id"]) as (org, db):
            seat = org["members"][member]
            ep = org["episodes"].get(seat.get("turn_episode") or "")
            if not ep or ep["status"] != "open":
                org["counters"]["episode"] += 1
                eid = "E%d" % org["counters"]["episode"]
                ep = org["episodes"][eid] = {"id": eid, "title": "%s's work turn" % member, "kind": "turn", "owner": member,
                                             "participants": [member], "status": "open", "opened_at": now(),
                                             "reflections": {}, "friction": []}
                seat["turn_episode"] = eid
            if friction:
                ep.setdefault("friction", []).append(friction)

    def end_turn(self, actor):
        org, member = self.whoami(actor)
        if not org:
            return None
        with self.change(org["id"]) as (org, db):
            seat = org["members"][member]
            ep = org["episodes"].get(seat.get("turn_episode") or "")
            if not ep or ep["status"] != "open":
                return None
            ep.update(status="closed", outcome="observed", closed_at=now(),
                      summary="%d friction signal(s) observed" % len(ep.get("friction", [])))
            seat["turn_episode"] = None
            self._event(db, org["id"], member, "episode.closed", {"id": ep["id"], "kind": "turn",
                                                                   "friction": len(ep.get("friction", []))})
            return ep

    def _last_activity(self, org_id, member, kind):
        with self.db() as db:
            row = db.execute("SELECT MAX(at) FROM activity WHERE org_id=? AND member=? AND kind=?",
                             (org_id, member, kind)).fetchone()
        return row[0] if row else None

    def _has_activity_since(self, org_id, member, before, since):
        with self.db() as db:
            rows = db.execute("SELECT tool, summary FROM activity WHERE org_id=? AND member=? AND at>=? AND failed=0",
                              (org_id, member, since)).fetchall()
        for tool, summary in rows:
            if _tool_matches(before["tools"], tool) and all(n.casefold() in (summary or "").casefold()
                                                           for n in before.get("input_contains", [])):
                return True
        return False

    def events(self, org_id, kinds=None):
        with self.db() as db:
            rows = db.execute("SELECT seq, member, kind, body, at FROM events WHERE org_id=? ORDER BY seq", (org_id,)).fetchall()
        out = [{"seq": r[0], "member": r[1], "kind": r[2], "body": json.loads(r[3]), "at": r[4]} for r in rows]
        return [e for e in out if not kinds or e["kind"] in kinds]
