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
import re
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


HUMAN = "human"  # the person, as a message sender and recipient (not a seat)


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def short_id(prefix):
    return prefix + uuid.uuid4().hex[:6]


def data_home():
    env = os.getenv("RELIC_HOME")
    # One store per machine, shared by every harness (Claude Code, Codex) whose members belong to the org.
    return Path(env) if env else Path.home() / ".relic"


# --------------------------------------------------------------------------
# The person's language: members write task titles, task reports and anything addressed to the person in it.
# --------------------------------------------------------------------------
LANGUAGE_NAMES = {"ar": "Arabic", "cs": "Czech", "da": "Danish", "de": "German", "el": "Greek", "en": "English",
                  "es": "Spanish", "fa": "Persian", "fi": "Finnish", "fr": "French", "he": "Hebrew", "hi": "Hindi",
                  "hu": "Hungarian", "id": "Indonesian", "it": "Italian", "ja": "Japanese", "ko": "Korean",
                  "ms": "Malay", "nb": "Norwegian", "nl": "Dutch", "no": "Norwegian", "pl": "Polish",
                  "pt": "Portuguese", "ro": "Romanian", "ru": "Russian", "sv": "Swedish", "th": "Thai",
                  "tr": "Turkish", "uk": "Ukrainian", "vi": "Vietnamese", "zh": "Chinese"}
LANGUAGE_TAG = re.compile(r"[a-z]{2,3}(-[a-z0-9]{1,8})*", re.I)


def _language_tag(value):
    """value as a language tag in its usual spelling ("zh_cn.UTF-8" -> "zh-CN"), or None when it is not one."""
    text = str(value or "").strip().split(".")[0].split("@")[0].replace("_", "-")
    if len(text) > 35 or not LANGUAGE_TAG.fullmatch(text):
        return None  # "", "C", "POSIX", "Chinese (Simplified)_China" ...
    head, *rest = text.split("-")
    return "-".join([head.lower()] + [p.upper() if len(p) == 2 and p.isalpha() else
                                      p.title() if len(p) == 4 and p.isalpha() else p.lower() for p in rest])


def _windows_language(langid):
    """A Windows LANGID (GetUserDefaultUILanguage) as a tag: 0x0804 -> zh-CN, 0x0404 -> zh-TW, 0x0409 -> en-US. An
    unknown variant of a language counts as that language's main variant; None when the language is unknown."""
    import locale
    table = getattr(locale, "windows_locale", {})
    name = table.get(langid) or table.get((langid & 0x3FF) | 0x400)
    return _language_tag({"zh_CHS": "zh-Hans", "zh_CHT": "zh-Hant"}.get(name, name))


def _system_language():
    """The language of the system's user interface, en-US when it cannot be told."""
    if os.name == "nt":
        try:
            import ctypes
            tag = _windows_language(ctypes.windll.kernel32.GetUserDefaultUILanguage())
        except Exception:
            tag = None
        if tag:
            return tag
    names = [os.environ.get(var) for var in ("LC_ALL", "LC_MESSAGES", "LANG")]
    try:
        import locale
        names.append(locale.getlocale()[0])
    except Exception:
        pass
    return next((tag for tag in map(_language_tag, names) if tag), "en-US")


def person_language():
    """The language the person reads, as a tag such as "zh-CN": RELIC_LANG; else the language chosen in the Relic App
    ("lang" in ~/.relic/app/prefs.json; empty there means the system's); else the system's user interface language."""
    tag = _language_tag(os.getenv("RELIC_LANG"))
    if tag:
        return tag
    prefs = None
    for attempt in range(3):
        try:
            prefs = json.loads((data_home() / "app" / "prefs.json").read_text(encoding="utf-8"))
            break
        except PermissionError:  # Windows: the App is replacing the file this instant
            time.sleep(0.05)
        except (OSError, ValueError):  # no App settings yet (the usual case), or a file being written
            break
    return (_language_tag(prefs.get("lang")) if isinstance(prefs, dict) else None) or _system_language()


def language_name(tag=None):
    """A language as members read it, e.g. "Simplified Chinese (zh-CN)"; without a tag, the person's language."""
    tag = person_language() if tag is None else (_language_tag(tag) or str(tag))
    parts = tag.lower().split("-")
    name = LANGUAGE_NAMES.get(parts[0])
    if parts[0] == "zh":
        traditional = "hant" in parts or ("hans" not in parts and bool({"tw", "hk", "mo"} & set(parts)))
        simplified = "hans" in parts or bool({"cn", "sg", "my"} & set(parts))
        name = "Traditional Chinese" if traditional else "Simplified Chinese" if simplified else name
    return "%s (%s)" % (name, tag) if name else tag


# A task marked done carries a short report the person reads: what it achieved and how it turned out.
REPORT_MAX = 1000


def task_report(value):
    """The report given with a task update, stripped ("" when there is none)."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise OrgError("report is text: a short Markdown report of at most %d characters." % REPORT_MAX)
    value = value.strip()
    if len(value) > REPORT_MAX:
        raise OrgError("A task report is at most %d characters; this one has %d. Keep to what the task achieved and "
                       "how it turned out." % (REPORT_MAX, len(value)))
    return value


def report_needed():
    """What to write when a task becomes done (the person's language named)."""
    return ("a report: a short report of what the task achieved and how it turned out (Markdown, at most %d "
            "characters), written in %s, the language the person reads" % (REPORT_MAX, language_name()))


def short_tool(tool):
    return tool.rsplit("__", 1)[-1] if tool.startswith("mcp__") else tool


RELIC_TOOLS = {"create", "join", "status", "message", "inbox", "work", "episode", "protocol", "review", "trajectory", "panel"}
# Chat members (relic_core/chat.py) discuss but have no files or commands: a ChatGPT chat ("chatgpt:<chat id>") and a
# Claude chat of the Claude desktop app ("claude-chat:<name>").
CHAT_HARNESSES = ("chatgpt", "claude-chat")
HARNESSES = ("claude-code", "codex") + CHAT_HARNESSES


def is_relic_tool(tool):
    # Claude Code names plugin tools mcp__plugin_relic_org__<tool>, Codex mcp__relic_org__<tool>.
    return tool.startswith("mcp__") and "relic_org__" in tool and short_tool(tool) in RELIC_TOOLS


def harness_of(actor):
    """Actors carry their harness as a prefix ("codex:<session>", "kimi:<session>" for a harness the Relic App runs
    through ACP); unprefixed actors are Claude Code."""
    head, sep, _ = (actor or "").partition(":")
    return head if sep and re.fullmatch(r"[a-z][a-z0-9-]*", head) else "claude-code"


# --------------------------------------------------------------------------
# One tool vocabulary across harnesses. Rules are written once (Bash, Edit, Write, Read ...) and
# hold for every member: Codex shell calls arrive as Bash or exec_command, Codex file edits as
# apply_patch with the patch text in command.
# --------------------------------------------------------------------------
SHELL_TOOLS = {"Bash", "exec_command", "shell", "local_shell", "container.exec", "unified_exec"}
PATCH_HEADERS = ("*** Add File: ", "*** Update File: ", "*** Delete File: ", "*** Move to: ")


def patch_paths(patch):
    return [line.split(": ", 1)[1].strip().replace("\\", "/") for line in str(patch).splitlines()
            if line.startswith(PATCH_HEADERS)]


def normalize(tool, tool_input):
    """Map a harness-specific tool call to the shared vocabulary: (tool, input)."""
    tool_input = tool_input if isinstance(tool_input, dict) else {"value": tool_input}
    if tool in SHELL_TOOLS:
        cmd = tool_input.get("command", tool_input.get("cmd", ""))
        if isinstance(cmd, list):
            cmd = " ".join(str(c) for c in cmd)
        return "Bash", dict(tool_input, command=str(cmd))
    if tool == "apply_patch":
        patch = tool_input.get("command", tool_input.get("input", tool_input.get("patch", "")))
        if isinstance(patch, list):
            patch = "\n".join(str(c) for c in patch)
        paths = patch_paths(patch)
        out = dict(tool_input, command=str(patch), paths=paths)
        if paths:
            out["file_path"] = paths[0]
        return "Edit", out
    return tool, tool_input


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def snippet(text, width=60):
    """The start of a message on one line, at most `width` characters (names the thread a reply belongs to)."""
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= width else flat[:width - 3].rstrip() + "..."


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
        if any(is_relic_tool(t) or "relic_org" in t for t in tools):
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


def _paths_of(tool_input):
    if isinstance(tool_input.get("paths"), list) and tool_input["paths"]:
        return [str(p).replace("\\", "/") for p in tool_input["paths"]]
    for key in ("file_path", "notebook_path", "path"):
        if isinstance(tool_input.get(key), str):
            return [tool_input[key].replace("\\", "/")]
    return []


def _path_of(tool_input):
    paths = _paths_of(tool_input)
    return paths[0] if paths else None


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
        glob = rule["path_glob"]
        if not any(fnmatch.fnmatch(p, glob) or fnmatch.fnmatch(p, "*/" + glob.lstrip("/")) for p in _paths_of(tool_input)):
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
            # hop: how many automatic wake-ups led to this message (0 = sent outside an automatically started turn)
            if "hop" not in {r[1] for r in db.execute("PRAGMA table_info(messages)")}:
                try:
                    db.execute("ALTER TABLE messages ADD COLUMN hop INTEGER DEFAULT 0")
                except sqlite3.OperationalError:
                    pass  # another process added it a moment ago
            # reply_to: the id of the thread's root message, for a reply inside a thread (NULL for every other message,
            # including the rows older processes keep inserting without this column)
            if "reply_to" not in {r[1] for r in db.execute("PRAGMA table_info(messages)")}:
                try:
                    db.execute("ALTER TABLE messages ADD COLUMN reply_to INTEGER")
                except sqlite3.OperationalError:
                    pass  # another process added it a moment ago

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

    def found(self, name, purpose="", governance="leader"):
        """The human founds an organization from the Relic App; the first seat added becomes the leader."""
        if not name.strip():
            raise OrgError("Give the organization a name.")
        if governance not in ("leader", "peer"):
            raise OrgError("governance must be leader or peer.")
        org = {"id": short_id("org_"), "name": name.strip(), "purpose": purpose, "governance": governance,
               "leader": None, "status": "active", "created_at": now(), "revision": 0, "members": {}, "documents": {},
               "tasks": {}, "episodes": {}, "protocols": {}, "reviews": {}, "automatic_reflection": True,
               "counters": {"task": 0, "episode": 0, "protocol": 0, "review": 0}}
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO orgs VALUES(?,?)", (org["id"], json.dumps(org, ensure_ascii=False)))
            self._event(db, org["id"], "human", "organization.created", {"name": name, "governance": governance})
        return org

    def join(self, actor, org_id, member, role=""):
        member = member.strip()
        if not member or any(c in member for c in " /\\:"):
            raise OrgError("Member names are short words without spaces, e.g. alice or release.")
        replaced = None
        with self.change(org_id) as (org, db):
            if org["status"] != "active":
                raise OrgError("Organization is not active.")
            harness = harness_of(actor)
            seat = org["members"].get(member)
            if seat is None:
                seat = org["members"][member] = {"role": role, "joined_at": now(), "carrier": actor,
                                                 "carriers": 1, "notes": [], "open_episode": None,
                                                 "harness": harness, "harness_history": [harness]}
                self._event(db, org_id, member, "member.joined", {"role": role, "harness": harness})
                for ep in org["episodes"].values():
                    if ep.get("all_members") and ep["status"] == "open" and member not in ep["participants"]:
                        ep["participants"].append(member)
            elif not seat.get("carrier"):
                # A seat prepared by the human (Relic App) gets its first carrier.
                seat.update(carrier=actor, harness=harness, carriers=seat.get("carriers", 0) + 1)
                seat.setdefault("harness_history", []).append(harness)
                self._event(db, org_id, member, "member.seated", {"harness": harness})
                if role:
                    seat["role"] = role
            else:
                if seat["carrier"] != actor:
                    # Carrier turnover: the seat, its role, tasks and protocols persist;
                    # the previous carrier's private notes do not.
                    replaced = seat["carrier"]
                    previous = seat.get("harness", "claude-code")
                    seat.setdefault("past_carriers", []).append(replaced)  # their trajectories stay readable
                    seat.update(carrier=actor, carriers=seat.get("carriers", 1) + 1, notes=[], harness=harness)
                    seat.setdefault("harness_history", [previous]).append(harness)
                    # A seat can pass between harnesses: a Codex carrier can succeed a Claude Code one.
                    self._event(db, org_id, member, "member.carrier_replaced",
                                {"carriers": seat["carriers"], "from_harness": previous, "to_harness": harness})
                if role:
                    seat["role"] = role
            db.execute("INSERT OR REPLACE INTO actors VALUES(?,?,?,?)", (actor, org_id, member, now()))
            if replaced:
                db.execute("DELETE FROM actors WHERE actor=? AND org_id=?", (replaced, org_id))
        return {"org_id": org_id, "member": member, "role": self.get(org_id)["members"][member]["role"],
                "carrier_replaced": bool(replaced)}

    # ---------------- human operations (Relic App) ----------------
    def add_seat(self, org_id, member, role="", config=None):
        """Prepare a seat before any session sits in it; config says how Relic starts its sessions."""
        member = member.strip()
        if not member or any(c in member for c in " /\\:"):
            raise OrgError("Member names are short words without spaces, e.g. alice or release.")
        with self.change(org_id) as (org, db):
            seat = org["members"].get(member)
            if seat is None:
                seat = org["members"][member] = {"role": role, "joined_at": now(), "carrier": None, "carriers": 0,
                                                 "notes": [], "open_episode": None, "harness": (config or {}).get("harness", ""),
                                                 "harness_history": []}
                self._event(db, org_id, member, "member.prepared", {"role": role})
                if org["governance"] == "leader" and not org.get("leader"):
                    org["leader"] = member
            if role:
                seat["role"] = role
            if config is not None:
                seat["config"] = config
                self._event(db, org_id, member, "member.configured", {k: v for k, v in config.items() if k not in ("env", "seat_token")})
        return seat

    def set_config(self, org_id, member, config):
        with self.change(org_id) as (org, db):
            if member not in org["members"]:
                raise OrgError("Unknown member " + member)
            org["members"][member]["config"] = config
            self._event(db, org_id, member, "member.configured", {k: v for k, v in config.items() if k not in ("env", "seat_token")})

    def send_from_human(self, org_id, to, body, channel=None, reply_to=None):
        """channel: where the person wrote it in the Relic App ("group" or "private"), kept on the event so the App
        shows a group-chat message to one member in the group chat. reply_to: a reply inside the thread of that message
        (see send); without `to`, the members in the thread get it."""
        org = self.get(org_id)
        with self.db() as db:
            root = self._thread_root(db, org_id, reply_to)
            if root and not to:
                recipients = [m for m in self._thread_people(db, org_id, root) if m in org["members"]]
                if not recipients:
                    raise OrgError("No member is in thread #%d; pick members." % root)
            else:
                recipients = list(org["members"]) if not to or to == ["all"] else list(to)
            if not body.strip() or set(recipients) - set(org["members"]):
                raise OrgError("Pick members and write a message.")
            cur = db.execute("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at,reply_to) "
                             "VALUES(?,?,?,?,?,?,?)", (org_id, "human", json.dumps(recipients), body, None, now(), root))
            self._event(db, org_id, "human", "message.sent", dict({"id": cur.lastrowid, "to": recipients},
                                                                  **({"channel": channel} if channel else {}),
                                                                  **({"reply_to": root} if root else {})))
        return cur.lastrowid

    def pending_count(self, org_id, member):
        with self.db() as db:
            rows = db.execute("""SELECT m.recipients FROM messages m WHERE m.org_id=? AND m.sender<>? AND NOT EXISTS
                (SELECT 1 FROM reads r WHERE r.org_id=m.org_id AND r.message_id=m.id AND r.member=?)""",
                              (org_id, member, member)).fetchall()
        return sum(member in json.loads(r[0]) for r in rows)

    # ---------------- trajectories (read only with the owner's consent) ----------------
    def _carrier_chain(self, org, member):
        seat = org["members"].get(member)
        if not seat:
            raise OrgError("Unknown member " + str(member))
        chain = [c for c in [seat.get("carrier")] + list(reversed(seat.get("past_carriers", []))) if c]
        if not chain:
            raise OrgError(member + " has no session yet.")
        return chain

    def request_trajectory(self, actor, member, carrier=0, reason="", memory=True):
        """Ask to read a member's trajectory, and with memory also what its harness remembers about that session. The
        member decides; your own seat's earlier carriers are decided by the human."""
        org, me = self.require(actor)
        chain = self._carrier_chain(org, member)
        carrier = int(carrier or 0)
        if not 0 <= carrier < len(chain):
            raise OrgError("carrier is 0 (current) to %d (oldest)." % (len(chain) - 1))
        if harness_of(chain[carrier]) in CHAT_HARNESSES:
            raise OrgError("%s is a chat: its conversation lives in its chat app, not in a transcript on this machine, "
                           "so there is no trajectory to export. Ask it in a message instead." % member)
        if member == me and carrier == 0:
            raise OrgError("That is your own session; its history is already yours.")
        if not (reason or "").strip():
            raise OrgError("Say why you need it; the member decides based on your reason.")
        approver = "human" if member == me else member
        with self.change(org["id"]) as (org, db):
            requests = org.setdefault("trajectory_requests", {})
            for r in requests.values():
                if (r["requester"], r["member"], r["carrier"], r["status"]) == (me, member, carrier, "pending"):
                    return {k: r[k] for k in ("id", "member", "carrier", "approver", "status")}
            org["counters"]["trajectory"] = org["counters"].get("trajectory", 0) + 1
            rid = "TR%d" % org["counters"]["trajectory"]
            requests[rid] = {"id": rid, "requester": me, "member": member, "carrier": carrier,
                             "harness": harness_of(chain[carrier]), "reason": reason.strip()[:500],
                             "memory": bool(memory), "approver": approver, "status": "pending", "at": now()}
            self._event(db, org["id"], me, "trajectory.requested", {"id": rid, "member": member, "carrier": carrier,
                                                                   "approver": approver, "memory": bool(memory)})
            if approver != "human":
                which = "your current session" if carrier == 0 else "the session of your seat's carrier #%d back" % carrier
                what = ("the trajectory of %s and what your harness remembers about it (its memory)" % which
                        if memory else "the trajectory of %s" % which)
                body = ("Trajectory request %s: %s asks to read %s. Reason: %s\nOnly you decide. Answer with the trajectory "
                        "tool: op=answer request_id=%s decision=approve or deny. API keys, tokens and passwords are "
                        "masked in the exported copy unless you pass redact=false." % (rid, me, what, reason.strip(), rid))
                db.execute("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at,hop) VALUES(?,?,?,?,?,?,?)",
                           (org["id"], me, json.dumps([member]), body, None, now(), self._sender_hop(org["id"], me)))
        return {"id": rid, "member": member, "carrier": carrier, "approver": approver, "status": "pending",
                "memory": bool(memory),
                "note": "You will get a message when %s answers." % ("the human" if approver == "human" else member)}

    # Exports are redacted unless the one who approves says otherwise: a transcript easily holds keys and passwords.
    def answer_trajectory(self, actor, request_id, decision, note="", redact=True):
        org, me = self.require(actor)
        return self._answer_trajectory(org["id"], me, request_id, decision, note, redact)

    def answer_trajectory_as_human(self, org_id, request_id, decision, note="", redact=True):
        return self._answer_trajectory(org_id, "human", request_id, decision, note, redact)

    def _answer_trajectory(self, org_id, who, request_id, decision, note, redact=True):
        from .trajectory import export
        if decision not in ("approve", "deny"):
            raise OrgError("decision is approve or deny.")
        org = self.get(org_id)
        r = org.get("trajectory_requests", {}).get(request_id)
        if not r or r["status"] != "pending":
            raise OrgError("No pending trajectory request " + str(request_id))
        if r["approver"] != who:
            raise OrgError("Only %s can answer %s." % (r["approver"], request_id))
        path = memory_file = None
        if decision == "approve":
            from .trajectory import memory_path
            source = self._carrier_chain(org, r["member"])[r["carrier"]]
            path = self.path.parent / "trajectories" / org_id / ("%s-%s-carrier%d.md" % (request_id, r["member"], r["carrier"]))
            try:
                export(source, path, title="%s / %s (carrier %d back), requested by %s" % (
                    org["name"], r["member"], r["carrier"], r["requester"]), redact=bool(redact),
                    memory=bool(r.get("memory")), verbatim=not redact)
            except FileNotFoundError as error:
                raise OrgError(str(error) + " Deny the request, or answer again once the transcript exists.")
            memory_file = memory_path(path) if r.get("memory") else None
        with self.change(org_id) as (org, db):
            r = org["trajectory_requests"][request_id]
            r.update(status="approved" if path else "denied", answered_by=who, answer_note=(note or "")[:300],
                     answered_at=now(), file=str(path) if path else None, redacted=bool(path and redact),
                     memory_file=str(memory_file) if memory_file else None)
            self._event(db, org_id, who, "trajectory." + r["status"], {"id": request_id, "member": r["member"],
                                                                      "requester": r["requester"]})
            if path:
                body = ("Trajectory request %s approved by %s. The full trajectory of %s is in this file: %s\n"
                        "The %s transcript files are in %s.%s None of it is in your context; open the files with "
                        "your own tools if and when you need them.%s" % (
                            request_id, who, r["member"], path, "redacted copies of the" if redact else "original",
                            path.with_suffix(""),
                            (" Its memory (what its harness remembers about that session) is in %s." % memory_file)
                            if memory_file else "",
                            " API keys and passwords are masked as [REDACTED]." if redact else ""))
            else:
                body = "Trajectory request %s denied by %s.%s" % (request_id, who, (" " + note) if note else "")
            db.execute("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at,hop) VALUES(?,?,?,?,?,?,?)",
                       (org_id, who, json.dumps([r["requester"]]), body, None, now(),
                        0 if who == "human" else self._sender_hop(org_id, who)))
            return {k: r.get(k) for k in ("id", "requester", "member", "carrier", "status", "file", "memory_file",
                                          "redacted")}

    def trajectory_requests(self, actor=None, org_id=None):
        """Pending requests waiting on this member (or on the human), and this member's own requests."""
        if actor:
            org, me = self.require(actor)
        else:
            org, me = self.get(org_id), "human"
        rows = list(org.get("trajectory_requests", {}).values())
        return {"to_answer": [r for r in rows if r["approver"] == me and r["status"] == "pending"],
                "mine": [{k: r.get(k) for k in ("id", "member", "carrier", "status", "file")}
                         for r in rows if r["requester"] == me][-10:]}

    def bindings(self):
        """Which actor sits in which seat, for every organization (used by the Relic App)."""
        with self.db() as db:
            return {r[0]: (r[1], r[2]) for r in db.execute("SELECT actor, org_id, member FROM actors")}

    def unbind(self, actor):
        """Take a session out of its seat. The seat, its role, tasks and the protocols stay with the organization."""
        org, member = self.whoami(actor)
        with self.db() as db:
            db.execute("DELETE FROM actors WHERE actor=?", (actor,))
            if org:
                self._event(db, org["id"], member, "member.unbound", {"harness": harness_of(actor)})
        return {"org_id": org["id"] if org else None, "member": member}

    def bind_alias(self, actor, org_id, member):
        """Bind an additional actor key to an existing seat without turnover (used for resumed sessions)."""
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO actors VALUES(?,?,?,?)", (actor, org_id, member, now()))

    # ---------------- messages ----------------
    # Threads work like Slack's, one level deep: a reply's reply_to is always the thread's root message, so answering a
    # reply joins the same thread. Without explicit recipients a reply goes to everyone in the thread so far.
    def _thread_root(self, db, org_id, reply_to):
        """The root id of the thread that a reply to message `reply_to` belongs to; None when it answers no message."""
        text = "" if reply_to is None else str(reply_to).strip().lstrip("#")
        if text in ("", "0"):
            return None
        try:
            parent = int(text)
        except ValueError:
            raise OrgError("reply_to is the id of the message you answer, e.g. 12.")
        row = db.execute("SELECT org_id, reply_to FROM messages WHERE id=?", (parent,)).fetchone()
        if not row or row[0] != org_id:
            raise OrgError("There is no message #%d in this organization to reply to." % parent)
        return row[1] or parent

    def _thread_people(self, db, org_id, root):
        """Everyone in a thread so far: the senders and recipients of its root and of each reply, in order of appearance
        ("human" too when the person took part)."""
        people = []
        for sender, recipients in db.execute("SELECT sender, recipients FROM messages WHERE org_id=? AND (id=? OR "
                                             "reply_to=?) ORDER BY id", (org_id, root, root)):
            people += [sender] + json.loads(recipients or "[]")
        return list(dict.fromkeys(people))

    def _thread_heads(self, db, org_id, messages):
        """Give each reply among `messages` the start of its thread: "thread": {id, from, snippet} of the root."""
        roots = sorted({m["reply_to"] for m in messages if m.get("reply_to")})
        if not roots:
            return messages
        heads = {r[0]: {"id": r[0], "from": r[1], "snippet": snippet(r[2])} for r in db.execute(
            "SELECT id, sender, body FROM messages WHERE org_id=? AND id IN (%s)" % ",".join("?" * len(roots)),
            [org_id] + roots)}
        for m in messages:
            if m.get("reply_to") in heads:
                m["thread"] = heads[m["reply_to"]]
        return messages

    def send(self, actor, to, body, episode_id=None, reply_to=None):
        """reply_to: answer inside the thread of that message; without `to`, everyone in the thread gets it."""
        org, member = self.require(actor)
        if not body or not body.strip():
            raise OrgError("Empty message.")
        with self.db() as db:
            root = self._thread_root(db, org["id"], reply_to)
            if root and not to:
                recipients = [m for m in self._thread_people(db, org["id"], root)
                              if m != member and (m in org["members"] or m == HUMAN)]
                if not recipients:
                    raise OrgError("Nobody else is in thread #%d; name the recipients with to." % root)
            elif not to or to == ["all"] or to == "all":
                recipients = [m for m in org["members"] if m != member]
            else:
                recipients = list(dict.fromkeys(to if isinstance(to, list) else [to]))
                # "human" is the person: they read and answer in the Relic App 
                unknown = set(recipients) - set(org["members"]) - {HUMAN}
                if unknown:
                    raise OrgError("Unknown members: " + ", ".join(sorted(unknown)))
            if not recipients:
                raise OrgError("No other members yet.")
            cur = db.execute("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at,hop,reply_to) "
                             "VALUES(?,?,?,?,?,?,?,?)", (org["id"], member, json.dumps(recipients), body, episode_id,
                                                         now(), self._sender_hop(org["id"], member), root))
            thread = {"reply_to": root} if root else {}
            self._event(db, org["id"], member, "message.sent", dict({"id": cur.lastrowid, "to": recipients}, **thread))
            return dict({"message_id": cur.lastrowid, "to": recipients}, **thread)

    def _sender_hop(self, org_id, member):
        """A message sent during an automatically started turn carries that turn's wake depth (wake.MAX_HOPS)."""
        path = self.path.parent / "runs" / ("%s-%s.json" % (org_id, member))
        for attempt in range(20):
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
                break
            except PermissionError:  # Windows: the runner is replacing the file this instant
                time.sleep(0.05)
            except (OSError, ValueError):
                return 0
        else:
            return 0
        return int(state.get("wake_hop") or 0) if state.get("status") == "running" else 0

    def unread(self, actor, mark=True, limit=20):
        org, member = self.whoami(actor)
        if not org:
            return []
        with self.db() as db:
            # Filter by recipient before taking `limit`: messages to other members are never marked read by this one,
            # so a LIMIT in SQL could fill up with them and hide this member's own messages.
            rows = db.execute("""SELECT m.id, m.sender, m.recipients, m.body, m.episode_id, m.at, m.reply_to
                FROM messages m WHERE m.org_id=? AND m.sender<>? AND m.recipients LIKE ? AND NOT EXISTS
                (SELECT 1 FROM reads r WHERE r.org_id=m.org_id AND r.message_id=m.id AND r.member=?)
                ORDER BY m.id""", (org["id"], member, "%" + json.dumps(member) + "%", member)).fetchall()
            out = []
            for mid, sender, recipients, body, ep, at, reply_to in rows:
                rec = json.loads(recipients)
                if member not in rec:
                    continue
                out.append({"id": mid, "from": sender, "to": rec, "body": body, "episode_id": ep, "at": at,
                            "reply_to": reply_to})
                if mark:
                    db.execute("INSERT OR IGNORE INTO reads VALUES(?,?,?,?)", (org["id"], mid, member, now()))
                if len(out) >= limit:
                    break
            if mark and out:
                self._event(db, org["id"], member, "message.read", {"ids": [m["id"] for m in out]})
            self._thread_heads(db, org["id"], out)  # a reply says which thread it answers
        return out

    def history(self, org_id, limit=30, after=0):
        """The latest `limit` messages, oldest first; with `after`, the first `limit` messages after that id (the
        Relic App adds them as they come). reply_to: the thread's root for a reply, else None."""
        with self.db() as db:
            if after:
                rows = db.execute("SELECT id,sender,recipients,body,at,reply_to FROM messages WHERE org_id=? AND id>? "
                                  "ORDER BY id LIMIT ?", (org_id, after, limit)).fetchall()
            else:
                rows = list(reversed(db.execute("SELECT id,sender,recipients,body,at,reply_to FROM messages WHERE "
                                                "org_id=? ORDER BY id DESC LIMIT ?", (org_id, limit)).fetchall()))
        return [{"id": r[0], "from": r[1], "to": json.loads(r[2]), "body": r[3], "at": r[4], "reply_to": r[5]}
                for r in rows]

    def unread_by_member(self, org_id, skip_prefix=None):
        """{member: [{id, sender, hop, at, reply_to}, ...]} over unread messages, oldest first; bodies starting with
        skip_prefix (automatic receipts) are left out."""
        with self.db() as db:
            rows = db.execute("SELECT id, sender, recipients, body, COALESCE(hop, 0), at, reply_to FROM messages "
                              "WHERE org_id=? ORDER BY id", (org_id,)).fetchall()
            read = {(r[0], r[1]) for r in db.execute("SELECT message_id, member FROM reads WHERE org_id=?", (org_id,))}
        out = {}
        for mid, sender, recipients, body, hop, at, reply_to in rows:
            if skip_prefix and (body or "").startswith(skip_prefix):
                continue
            for member in json.loads(recipients):
                if member != sender and (mid, member) not in read:
                    out.setdefault(member, []).append({"id": mid, "sender": sender, "hop": hop, "at": at,
                                                       "reply_to": reply_to})
        return out

    def sent_since(self, org_id, member, since, skip_prefix=None):
        """Recipients of the messages a member sent at or after `since` (an ISO time from now()); bodies starting with
        skip_prefix (automatic receipts) are left out."""
        with self.db() as db:
            rows = db.execute("SELECT recipients, body FROM messages WHERE org_id=? AND sender=? AND at>=?",
                              (org_id, member, since)).fetchall()
        return {m for r in rows if not (skip_prefix and (r[1] or "").startswith(skip_prefix)) for m in json.loads(r[0])}

    def send_as(self, org_id, member, to, body, hop=0, relayed=False, via=None, reply_to=None):
        """A message written on a seat's behalf by the plugin itself: an automatic receipt after a woken turn, or
        (relayed) the reply of a chat member that has no Relic tools, carrying the depth of the turn that wrote it.
        via="human": the person brought the reply over (forward_reply). reply_to: a reply inside the thread of that
        message (see send); without `to`, everyone in the thread gets it."""
        org = self.get(org_id)
        if not (body or "").strip():
            return None
        with self.db() as db:
            root = self._thread_root(db, org_id, reply_to)
            if root and not to:
                to = self._thread_people(db, org_id, root)
            recipients = [m for m in dict.fromkeys(to or []) if (m in org["members"] or m == HUMAN) and m != member]
            if not recipients:
                return None
            cur = db.execute("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at,hop,reply_to) "
                             "VALUES(?,?,?,?,?,?,?,?)", (org_id, member, json.dumps(recipients), body, None, now(),
                                                         int(hop or 0), root))
            self._event(db, org_id, member, "message.sent", dict(
                {"id": cur.lastrowid, "to": recipients}, **({"relayed": True} if relayed else {"automatic": True}),
                **({"via": via} if via else {}), **({"reply_to": root} if root else {})))
            return cur.lastrowid

    def mark_read(self, org_id, member, ids):
        """Messages the plugin handed to a member that cannot call inbox (a chat member's turn carried their text)."""
        ids = [int(i) for i in ids]
        if not ids:
            return
        with self.db() as db:
            for mid in ids:
                db.execute("INSERT OR IGNORE INTO reads VALUES(?,?,?,?)", (org_id, mid, member, now()))
            self._event(db, org_id, member, "message.read", {"ids": ids, "relayed": True})

    def set_seat_fields(self, org_id, member, **fields):
        """Bookkeeping the plugin keeps on a seat (a chat member's introduction having been given, for one)."""
        with self.change(org_id) as (org, db):
            if member not in org["members"]:
                raise OrgError("Unknown member " + member)
            org["members"][member].update(fields)

    # A ChatGPT chat's replies stay in the ChatGPT window (chat.py): each one waits on its seat until the person
    # forwards it in the Relic App.
    WAITING = "replies_waiting"

    def note_hidden_reply(self, org_id, member, to, ids, hop=0):
        """Record a reply only the person can see, with the members it answers (to) and the depth of its turn."""
        with self.change(org_id) as (org, db):
            seat = org["members"][member]
            waiting = seat.setdefault(self.WAITING, [])
            waiting.append({"to": list(to), "ids": list(ids), "hop": int(hop or 0), "at": time.time()})
            del waiting[:-20]
            self._event(db, org_id, member, "message.reply_waiting", {"answers": list(ids), "to": list(to)})

    def forward_reply(self, org_id, member, to, body):
        """The person forwards a chat member's reply they copied from its chat: it becomes the member's message to `to`,
        at the depth of the oldest reply waiting on the seat, which it settles. Returns the message id."""
        org = self.get(org_id)
        if member not in org["members"]:
            raise OrgError("Unknown member " + member)
        waiting = org["members"][member].get(self.WAITING) or []
        mid = self.send_as(org_id, member, to, body, hop=waiting[0]["hop"] if waiting else 0, relayed=True, via="human")
        if mid is None:
            raise OrgError("Paste the reply and pick who gets it.")
        if waiting:
            with self.change(org_id) as (org, db):
                seat = org["members"][member]
                seat[self.WAITING] = (seat.get(self.WAITING) or [])[1:]
        return mid

    def set_auto_wake(self, org_id, on):
        """Organization-wide switch for automatic wake-ups (on unless the person turns it off in the Relic App)."""
        with self.change(org_id) as (org, db):
            org["auto_wake"] = bool(on)
            self._event(db, org_id, "human", "organization.auto_wake", {"on": bool(on)})

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
                was_done = task["status"] == "done"
                for key in ("title", "owner", "status"):
                    if a.get(key):
                        task[key] = a[key]
                if task["owner"] not in org["members"]:
                    raise OrgError("Task owner must be a member.")
                if task["status"] not in ("open", "working", "blocked", "done", "dropped"):
                    raise OrgError("status: open, working, blocked, done or dropped.")
                if a.get("evidence"):
                    task["evidence"] = list(task["evidence"]) + list(a["evidence"])
                report = task_report(a.get("report"))
                # Becoming done takes evidence and a report written in this call; a task done before (tasks stored
                # before reports existed included) needs none, and its report can be added or replaced later.
                done_now = task["status"] == "done" and not was_done
                needs = []
                if task["status"] == "done" and not task["evidence"]:
                    needs.append("evidence (commit, test output, file)")
                if done_now and not report:
                    needs.append(report_needed())
                if needs:
                    raise OrgError("Mark done with %s." % " and ".join(needs))
                if report and task["status"] != "done":
                    raise OrgError("A report belongs to a done task: pass it with status done, or later on a task "
                                   "that is already done.")
                if done_now:
                    task["done_at"] = now()
                if report:
                    task["report"] = report
                task["at"] = now()
                self._event(db, org["id"], member, "task.updated", dict(
                    {"id": tid, "status": task["status"], "owner": task["owner"]},
                    **({"report": True} if task.get("report") else {})))
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
                                "propose a protocol so the lesson becomes organization-owned instead of staying in one carrier. "
                                "Decide its strength first: if a rule (deny, require_before or require_review on a tool call) "
                                "can carry the lesson and it should hold even when a member forgets, propose it strong from "
                                "this episode; if it needs judgment, propose it weak. State the choice and why in the rationale."}
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
        tool, tool_input = normalize(tool, tool_input)
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
        tool, tool_input = normalize(tool, tool_input)
        org, member = self.whoami(actor)
        if not org or is_relic_tool(tool):
            return
        kind = "edit" if short_tool(tool) in EDIT_TOOLS else ("run" if tool == "Bash" else "other")
        summary = ((", ".join(_paths_of(tool_input)) if kind == "edit" else tool_input.get("command")) or _path_of(tool_input)
                   or next((str(tool_input[k]) for k in ("url", "query", "pattern", "description") if tool_input.get(k)), ""))
        # friction markers count only in the output of git commands: the same words inside files an agent reads
        # (a patch, a ticket) are not friction between members
        is_git = tool == "Bash" and "git " in str(tool_input.get("command", ""))
        signals = [m for m in FRICTION_MARKERS if m in (output or "")] if is_git else []
        with self.db() as db:
            db.execute("INSERT INTO activity(org_id,member,tool,kind,summary,failed,at) VALUES(?,?,?,?,?,?,?)",
                       (org["id"], member, tool, kind, str(summary)[:500], int(bool(failed)), time.time()))
        if failed:
            # which tool, on what, and the first line of what went wrong
            why = next((line.strip() for line in str(output or "").splitlines() if line.strip()), "")
            friction = "tool failed: %s %s%s" % (short_tool(tool), " ".join(str(summary).split())[:120],
                                                 (" (%s)" % why[:160]) if why else "")
        else:
            friction = ("friction (%s): %s" % (", ".join(signals), str(summary)[:120])) if signals else None
        self.turn_note(actor, friction=friction)

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
