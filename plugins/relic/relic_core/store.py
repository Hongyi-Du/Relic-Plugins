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

from . import checker

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
# Output fragments that signal friction between members' work (rejected pushes, conflicting changes).
FRICTION_MARKERS = ("[rejected]", "non-fast-forward", "CONFLICT", "could not apply", "Merge conflict",
                    "error: failed to push", "Your branch and 'origin/", "have diverged")


class OrgError(ValueError):
    pass


HUMAN = "human"  # the person, as a message sender and recipient (not a seat)


def qualified(org_id, member):
    """How a member of one organization is named in another: "<org id>/<member>" (member names have no slash)."""
    return "%s/%s" % (org_id, member)


def kind_of(org):
    """"formal" (a standing organization, a department; so is every organization older than kinds) or "subgroup" (a
    group made for one piece of work)."""
    return "subgroup" if (org or {}).get("kind") == "subgroup" else "formal"


def inherits(protocol):
    """Whether a protocol binds the organizations below its own too: inherit (older data says downward)."""
    p = protocol or {}
    return bool(p["inherit"] if "inherit" in p else p.get("downward"))


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


def activity_kind(tool):
    """What a tool call counts as in the activity record: edit (a file change), run (a shell command) or other."""
    return "edit" if short_tool(tool) in EDIT_TOOLS else ("run" if tool == "Bash" else "other")


RELIC_TOOLS = {"create", "join", "status", "message", "inbox", "work", "episode", "protocol", "review", "trajectory", "panel",
               "group"}
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
# Strong protocol rules: a small, bounded rule language bound to PreToolUse. A check rule runs a judgment program the
# members wrote (relic_core/checker.py) on the calls it covers; its code, examples and on_error come with it, and the
# store records the code's sha256 when the protocol is proposed (Store.prepare_rules).
# --------------------------------------------------------------------------
CHECK_FIELDS = ("code", "examples", "on_error", "code_sha256")
RULE_FIELDS = {"effect", "tools", "input_contains", "path_glob", "members", "roles",
               "except_members", "except_roles", "before", "reason"} | set(CHECK_FIELDS)
EFFECTS = ("deny", "require_review", "require_before", "check")
SUMMARY_MAX = 2000  # characters of a protocol's note for the person
# Chinese characters: CJK Unified Ideographs, Extension A and the Compatibility Ideographs
CHINESE = re.compile("[%s-%s%s-%s%s-%s]" % tuple(map(chr, (0x3400, 0x4DBF, 0x4E00, 0x9FFF, 0xF900, 0xFAFF))))
_ANY_TOOL = ("a", "Zq", "mcp__x__y", "relic_probe_tool")  # names no tool has: a pattern matching them all matches any tool


def has_check(protocol):
    """Whether a protocol has a check rule (a judgment program of its own)."""
    return any(isinstance(r, dict) and r.get("effect") == "check" for r in (protocol or {}).get("rules") or [])


def _validate_check(rule):
    """The shape of a check rule; its code loads and its examples run in Store.prepare_rules."""
    if not isinstance(rule.get("code"), str) or not rule["code"].strip():
        raise OrgError("A check rule needs code: Python (standard library only) that defines check(call) and returns "
                       "{\"decision\": \"allow\" | \"deny\" | \"review\", \"reason\": \"...\"}.")
    if rule.get("on_error", "allow") not in checker.ON_ERROR:
        raise OrgError("on_error is allow (the default: the call goes through when the program fails) or deny.")
    low, high = checker.EXAMPLES
    examples = rule.get("examples")
    if not isinstance(examples, list) or not low <= len(examples) <= high:
        raise OrgError("A check rule needs %d to %d examples, [{\"call\": {\"tool\": ..., \"input\": {...}}, \"expect\": "
                       "\"allow\" | \"deny\" | \"review\"}]: calls the rule covers and what its program must answer "
                       "for each, at least one allow and one deny or review." % (low, high))
    for n, example in enumerate(examples, 1):
        if not isinstance(example, dict) or set(example) - {"call", "expect", "note"}:
            raise OrgError("Example %d: an example is {\"call\": {...}, \"expect\": ..., \"note\"?}." % n)
        call = example.get("call")
        if not isinstance(call, dict) or not isinstance(call.get("tool"), str) or not call["tool"].strip():
            raise OrgError("Example %d needs call.tool (and usually call.input), like the calls the rule covers." % n)
        if not isinstance(call.get("input", {}), dict) or not isinstance(call.get("recent", []), list):
            raise OrgError("Example %d: call.input is an object (the tool's input) and call.recent a list." % n)
        if example.get("expect") not in checker.DECISIONS:
            raise OrgError("Example %d: expect is allow, deny or review." % n)
    expected = {example["expect"] for example in examples}
    if "allow" not in expected or not expected & {"deny", "review"}:
        raise OrgError("A check rule's examples need at least one call its program allows and one it denies or sends "
                       "for review.")


def person_summary(value):
    """A protocol's summary_for_person (needed with a check rule): the note copied to the person when the protocol
    takes effect, in the person's language; a person who reads Chinese gets Chinese."""
    tag = person_language()
    if not isinstance(value, str) or not value.strip():
        raise OrgError("A protocol with a check rule needs summary_for_person: a short note for the person, written in "
                       "%s, on what the protocol is for, what its check program judges and when it blocks a call. It "
                       "is copied to the person when the protocol takes effect." % language_name(tag))
    value = value.strip()
    if len(value) > SUMMARY_MAX:
        raise OrgError("summary_for_person has %d characters; keep it under %d." % (len(value), SUMMARY_MAX))
    if tag.lower().split("-")[0] == "zh" and not CHINESE.search(value):
        raise OrgError("summary_for_person is for the person, who reads %s: write it in that language (this one has "
                       "no Chinese characters)." % language_name(tag))
    return value


def validate_rules(rules):
    if not isinstance(rules, list) or not rules:
        raise OrgError("A strong protocol needs at least one rule. Prose alone belongs in a weak protocol.")
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) - RULE_FIELDS:
            raise OrgError("Unknown rule field. Allowed: " + ", ".join(sorted(RULE_FIELDS - {"code_sha256"})))
        if rule.get("effect") not in EFFECTS:
            raise OrgError("Rule effect must be deny, require_review, require_before or check.")
        tools = rule.get("tools")
        if not isinstance(tools, list) or not tools or not all(isinstance(t, str) and t for t in tools):
            raise OrgError("Each rule needs tool name patterns, e.g. [\"Bash\"] or [\"Edit\", \"Write\"].")
        if any(is_relic_tool(t) or "relic_org" in t for t in tools):
            raise OrgError("Rules cannot gate the organization's own governance tools.")
        if rule["effect"] == "check" and any(all(fnmatch.fnmatchcase(n, t) for n in _ANY_TOOL) for t in tools):
            raise OrgError("A check rule runs its program on the calls it covers, so it names their tools, e.g. "
                           "[\"Bash\"] or [\"Edit\", \"Write\"]; it cannot cover every tool.")
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
        if rule["effect"] == "check":
            _validate_check(rule)
        elif any(key in rule for key in CHECK_FIELDS):
            raise OrgError("code, examples and on_error belong to rules with effect check.")


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


def example_in_scope(rule, call):
    """Whether a check rule covers an example's call (tool and input in the shared vocabulary). Who the rule applies to
    counts only when the example names the member or the role."""
    probe = dict(rule)
    for given, keys in ((call.get("member"), ("members", "except_members")), (call.get("role"), ("roles", "except_roles"))):
        if not given:
            for key in keys:
                probe.pop(key, None)
    return rule_applies(probe, call.get("member") or "", call.get("role") or "", call["tool"], call["input"])


def scope_text(rule):
    """The calls a rule covers, in a few words: "Bash containing git push", "Edit/Write on src/api/*"."""
    what = "/".join(rule.get("tools") or [])
    if rule.get("path_glob"):
        what += " on " + rule["path_glob"]
    if rule.get("input_contains"):
        what += " containing " + ", ".join(rule["input_contains"])
    if rule.get("roles") or rule.get("members"):
        what += " by " + "/".join((rule.get("roles") or []) + (rule.get("members") or []))
    if rule.get("except_roles") or rule.get("except_members"):
        what += " except " + "/".join((rule.get("except_roles") or []) + (rule.get("except_members") or []))
    return what


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
                CREATE TABLE IF NOT EXISTS seats(actor TEXT, org_id TEXT, member TEXT, bound_at TEXT,
                    PRIMARY KEY(actor, org_id));
                CREATE TABLE IF NOT EXISTS focus(actor TEXT PRIMARY KEY, org_id TEXT, at TEXT);
                CREATE TABLE IF NOT EXISTS check_counts(org_id TEXT, protocol_id TEXT, outcome TEXT, n INTEGER,
                    last_at REAL, PRIMARY KEY(org_id, protocol_id, outcome));
                CREATE TABLE IF NOT EXISTS check_alerts(org_id TEXT, protocol_id TEXT, kind TEXT, at REAL,
                    PRIMARY KEY(org_id, protocol_id, kind));
                CREATE TABLE IF NOT EXISTS cc(id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT, protocol_id TEXT,
                    body TEXT, at TEXT, read_at TEXT);
            """)
            # check_counts: how often each protocol's check programs allowed, denied, sent for review or failed
            # ("error:<kind>"), kept by the organization the protocol belongs to; allowed calls are only counted.
            # check_alerts: when a failure of each kind was last announced (once a day per protocol and kind).
            # cc: protocols with a check rule copied to the person when they took effect (the Relic App's Copies).
            # A session holds one seat per organization it belongs to (seats); actors keeps its main seat, the one
            # its Relic calls use when they name no organization. Bindings written before seats existed, or by an older
            # plugin that knows only actors, are seats too.
            db.execute("INSERT OR IGNORE INTO seats SELECT actor, org_id, member, bound_at FROM actors")
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

    # ---------------- a session's seats ----------------
    # A session (actor) can hold a seat in several organizations: the leader of a department also sits in the
    # department above and in the cabinet, a member of a subgroup still sits in its own organization. Its main seat
    # (table actors) is the one its Relic calls use without org; "<actor>#<org id>" names its seat in that
    # organization, which is how a call with org=<an organization it sits in> acts as that seat's member. The
    # organization a session is working for right now (focus) decides which protocols bind its tool calls.
    SCOPED = re.compile(r"^(.+)#(org_[\w-]+)$")

    @classmethod
    def split_actor(cls, actor):
        """(session actor, organization id or None): "<actor>#<org id>" names the session's seat in that organization."""
        found = cls.SCOPED.match(str(actor or ""))
        return (found.group(1), found.group(2)) if found else (actor, None)

    @staticmethod
    def _seat_rows(db, actor):
        """[(organization id, member, main)] of a session's seats, its main seat first."""
        main = db.execute("SELECT org_id, member FROM actors WHERE actor=?", (actor,)).fetchone()
        rows = [(main[0], main[1], True)] if main else []
        for org_id, member in db.execute("SELECT org_id, member FROM seats WHERE actor=? ORDER BY bound_at, org_id",
                                         (actor,)):
            if not main or org_id != main[0]:
                rows.append((org_id, member, False))
        return rows

    def seats_of(self, actor, first=False):
        """[(organization, member, main)]: the seats a session holds in active organizations, its main seat first.
        For "<actor>#<org id>", only its seat there. first: stop at the first one."""
        base, scope = self.split_actor(actor)
        if not base:
            return []
        out = []
        with self.db() as db:
            for org_id, member, main in self._seat_rows(db, base):
                if scope and org_id != scope:
                    continue
                try:
                    org = self._load(db, org_id)
                except OrgError:
                    continue
                seat = (org.get("members") or {}).get(member)
                # a seat beside the main one counts while the session carries it (an older plugin that knows only
                # actors may have handed the seat to another session without clearing this row)
                if org.get("status") == "active" and seat is not None and (main or seat.get("carrier") == base):
                    out.append((org, member, main))
                    if first:
                        break
        return out

    def whoami(self, actor):
        """(organization, member) a call from this actor acts as: the session's main seat ("<actor>#<org id>": its
        seat there); when the main seat is gone, its next seat."""
        if not actor:
            return None, None
        seats = self.seats_of(actor, first=True)
        return (seats[0][0], seats[0][1]) if seats else (None, None)

    def scoped(self, actor, ref):
        """"<actor>#<org id>" when the session holds a seat in the organization ref names (id or exact name)."""
        base, _ = self.split_actor(actor)
        ref = str(ref or "").strip()
        if not base or not ref:
            return None
        for org, member, main in self.seats_of(base):
            if ref in (org["id"], org["name"]):
                return "%s#%s" % (base, org["id"])
        return None

    def set_focus(self, actor, org_id):
        """The session works for org_id now (a turn woken by a message there, or a Relic call with org=<it>)."""
        base, _ = self.split_actor(actor)
        if base and org_id:
            with self.db() as db:
                db.execute("INSERT OR REPLACE INTO focus VALUES(?,?,?)", (base, org_id, now()))

    def clear_focus(self, actor):
        """Back to the main seat (a turn ended: what the person asks in the session is its main organization's work)."""
        base, _ = self.split_actor(actor)
        with self.db() as db:
            db.execute("DELETE FROM focus WHERE actor=?", (base,))

    def focused(self, actor):
        """The actor whose seat the session works in right now: "<actor>#<focus org>" while it works for an
        organization it sits in, else the actor itself (its main seat)."""
        base, scope = self.split_actor(actor)
        if scope or not base:
            return actor
        with self.db() as db:
            row = db.execute("SELECT org_id FROM focus WHERE actor=?", (base,)).fetchone()
            if not row:
                return actor
            held = db.execute("SELECT 1 FROM seats WHERE actor=? AND org_id=? UNION SELECT 1 FROM actors WHERE "
                              "actor=? AND org_id=?", (base, row[0], base, row[0])).fetchone()
        return "%s#%s" % (base, row[0]) if held else actor

    def _bind(self, db, actor, org_id, member, main=False):
        """Seat a session in org_id as member (one seat per organization). It becomes the main seat when asked, when
        the session has none yet, or when its main seat already was in org_id."""
        db.execute("INSERT OR REPLACE INTO seats VALUES(?,?,?,?)", (actor, org_id, member, now()))
        row = db.execute("SELECT org_id FROM actors WHERE actor=?", (actor,)).fetchone()
        if main or not row or row[0] == org_id:
            db.execute("INSERT OR REPLACE INTO actors VALUES(?,?,?,?)", (actor, org_id, member, now()))

    def _unbind(self, db, actor, org_id):
        """Take a session out of its seat in org_id only; when that was its main seat, another of its seats is."""
        db.execute("DELETE FROM seats WHERE actor=? AND org_id=?", (actor, org_id))
        db.execute("DELETE FROM focus WHERE actor=? AND org_id=?", (actor, org_id))
        row = db.execute("SELECT org_id FROM actors WHERE actor=?", (actor,)).fetchone()
        if row and row[0] == org_id:
            db.execute("DELETE FROM actors WHERE actor=?", (actor,))
            other = db.execute("SELECT org_id, member FROM seats WHERE actor=? ORDER BY bound_at, org_id LIMIT 1",
                               (actor,)).fetchone()
            if other:
                db.execute("INSERT INTO actors VALUES(?,?,?,?)", (actor, other[0], other[1], now()))

    @staticmethod
    def _holds(db, actor, org_id):
        return bool(actor) and db.execute("SELECT 1 FROM seats WHERE actor=? AND org_id=? UNION SELECT 1 FROM actors "
                                          "WHERE actor=? AND org_id=?", (actor, org_id, actor, org_id)).fetchone() is not None

    def seat_config(self, org_id, member, org=None):
        """How Relic starts turns of a seat: its own config, else (an ex officio seat, a subgroup seat) the config of
        the seat its session holds elsewhere, its main seat first."""
        org = org or self.get(org_id)
        seat = (org.get("members") or {}).get(member) or {}
        if seat.get("config") or not seat.get("carrier"):
            return seat.get("config") or {}
        for other, name, main in self.seats_of(seat["carrier"]):
            config = (other["members"].get(name) or {}).get("config")
            if other["id"] != org_id and config:
                return config
        return {}

    def seat_keys(self, actor):
        """[(organization id, member)] of every seat a session holds, its main seat first."""
        base, _ = self.split_actor(actor)
        if not base:
            return []
        with self.db() as db:
            return [(o, m) for o, m, _ in self._seat_rows(db, base)]

    def require(self, actor):
        org, member = self.whoami(actor)
        if not org:
            raise OrgError("You are not in a Relic organization yet. Call create or join first.")
        return org, member

    # ---------------- organizations above and below ----------------
    # The person places an organization under another in the Relic App (set_parent). Members of an organization
    # above (at any depth) see one below, write to its members, assign and update its tasks and issue protocols that
    # take effect there directly; a protocol marked downward also binds every organization below its own. Members
    # of an organization below only report upward: they write to members of the organizations above, and record
    # their use of a protocol that binds them from above.
    @staticmethod
    def _ids_below(orgs, org_id):
        below, todo = [], [org_id]
        while todo:
            current = todo.pop()
            for o in orgs:
                if o.get("parent") == current and o["id"] != org_id and o["id"] not in below:
                    below.append(o["id"])
                    todo.append(o["id"])
        return below

    def ancestors(self, org):
        """The active organizations above org, nearest first (a broken or circular chain ends where it breaks)."""
        chain, seen, current = [], {org["id"]}, org
        while current.get("parent") and current["parent"] not in seen:
            try:
                current = self.get(current["parent"])
            except OrgError:
                break
            if current.get("status") != "active":
                break
            seen.add(current["id"])
            chain.append(current)
        return chain

    def descendants(self, org_id):
        """The active organizations below org_id, at any depth."""
        orgs = [o for o in self.list_orgs() if o.get("status") == "active"]
        below = self._ids_below(orgs, org_id)
        return [o for o in orgs if o["id"] in below]

    def set_parent(self, org_id, parent_id):
        """The person places org_id under parent_id (None: on its own). Only the Relic App calls this."""
        parent_id = parent_id or None
        org = self.get(org_id)
        parent = None
        if parent_id:
            parent = self.get(parent_id)
            if parent_id == org_id or parent_id in self._ids_below(self.list_orgs(), org_id):
                raise OrgError("An organization cannot be placed under itself or under an organization below it.")
            if parent.get("status") != "active":
                raise OrgError("Organization is not active.")
            if kind_of(org) == "formal" and kind_of(parent) == "subgroup":
                raise OrgError("A formal organization cannot be placed under a subgroup.")
        old = org.get("parent")
        if old == parent_id:
            return {"org_id": org_id, "parent": parent_id}
        with self.change(org_id) as (org, db):
            org["parent"] = parent_id
            if parent:
                self._event(db, org_id, HUMAN, "organization.parent_set", {"parent": parent_id, "name": parent["name"]})
                self._event(db, parent_id, HUMAN, "organization.child_added", {"child": org_id, "name": org["name"]})
            else:
                self._event(db, org_id, HUMAN, "organization.parent_removed", {"parent": old})
            if old:
                self._event(db, old, HUMAN, "organization.child_removed", {"child": org_id, "name": org["name"]})
        self.sync_offices(org_id)
        return {"org_id": org_id, "parent": parent_id}

    def find_org(self, ref):
        """An active organization by id or by exact name."""
        ref = str(ref or "").strip()
        orgs = [o for o in self.list_orgs() if o.get("status") == "active"]
        hit = [o for o in orgs if o["id"] == ref] or [o for o in orgs if o["name"] == ref]
        if not hit:
            raise OrgError("No organization " + ref)
        if len(hit) > 1:
            raise OrgError("Several organizations are called %s; name one by its id (%s)."
                           % (ref, ", ".join(o["id"] for o in hit)))
        return hit[0]

    def reach(self, actor, ref, up=False):
        """(your organization, you, the organization ref names, how it is related): "down" for one below yours at
        any depth; with up, "up" for one above it; None when ref is your own organization."""
        org, member = self.require(actor)
        if not ref or str(ref).strip() in (org["id"], org["name"]):
            return org, member, org, None
        target = self.find_org(ref)
        if target["id"] in self._ids_below([o for o in self.list_orgs() if o.get("status") == "active"], org["id"]):
            return org, member, target, "down"
        above = [a["id"] for a in self.ancestors(org)]
        if target["id"] in above:
            if up:
                return org, member, target, "up"
            raise OrgError("%s is above your organization: report to its members with message (org=%s); its work "
                           "belongs to them." % (target["name"], target["id"]))
        raise OrgError("%s is neither above nor below your organization (the person sets that in the Relic App), so "
                       "you cannot act in it." % target["name"])

    # Protocols are inherited like methods of a class. An organization's protocols bind it alone unless marked
    # inherit (older data: downward). Going down from the topmost organization above, each level takes what the level
    # above passes down, applies its own overrides (an active protocol with supersedes="<org id>/<P#>") and stops
    # (an enacted retirement with retire_target="<org id>/<P#>"), adds its own inheritable protocols and passes the
    # result on. The organization itself then adds all of its own active protocols. The nearest definition wins, and
    # an override or stop counts at its level and below. A protocol issued from above is never overridden or stopped
    # by the organizations below it.
    def inheritance(self, org):
        """{"inherited": [(owner, protocol)] in effect in org from the organizations above,
            "replaced": [(owner, protocol, organization that replaced it, its protocol id, "overridden" | "retired")]}."""
        passed, replaced = {}, []
        for level in list(reversed(self.ancestors(org))) + [org]:
            protocols = list((level.get("protocols") or {}).values())
            for p in protocols:
                for ref, how, status in ((p.get("supersedes"), "overridden", "active"),
                                         (p.get("retire_target"), "retired", "enacted")):
                    if p.get("status") == status and ref and "/" in str(ref) and ref in passed:
                        owner, gone = passed[ref]
                        if not gone.get("issued_by"):
                            del passed[ref]
                            replaced.append((owner, gone, level, p["id"], how))
            if level is org:
                break
            for p in protocols:
                if p.get("status") == "active" and inherits(p):
                    passed["%s/%s" % (level["id"], p["id"])] = (level, p)
        return {"inherited": list(passed.values()), "replaced": replaced}

    def inherited_protocols(self, org):
        """[(organization above, protocol)]: the protocols of the organizations above that are in effect in org."""
        return self.inheritance(org)["inherited"]

    def effective_protocols(self, org):
        """[(owner, protocol)]: every protocol in effect in org, its own active ones first."""
        own = [(org, p) for p in (org.get("protocols") or {}).values() if p.get("status") == "active"]
        return own + self.inherited_protocols(org)

    def org_names(self, db, names):
        """{"<org id>/<member>": organization name} for the names that belong to another organization."""
        out = {}
        for name in names:
            place, _, who = str(name).partition("/")
            if who and place not in out:
                try:
                    out[place] = self._load(db, place)["name"]
                except OrgError:
                    out[place] = place
        return {n: out[str(n).split("/", 1)[0]] for n in names if "/" in str(n)}

    # ---------------- formal organizations: the cabinet and ex officio seats ----------------
    # Formal organizations are standing ones (departments); subgroups are made for one piece of work. The person marks
    # one formal organization as the cabinet (the secretariat); its leader is the secretary-general. The leader of a
    # formal organization holds a seat ex officio in the formal organization right above it and in the cabinet,
    # carried by the session of its leader seat (seat["ex_officio"] = {"org": department, "member": leader}).
    def cabinet(self):
        """The active organization marked as the cabinet, or None."""
        found = [o for o in self.list_orgs() if o.get("cabinet") and o.get("status") == "active"]
        return min(found, key=lambda o: o.get("created_at") or "") if found else None

    def is_secretary_general(self, actor):
        """Whether the session holds the cabinet's leader seat."""
        cab = self.cabinet()
        if not cab or not cab.get("leader"):
            return False
        return any(o["id"] == cab["id"] and m == cab["leader"] for o, m, _ in self.seats_of(self.split_actor(actor)[0]))

    def set_cabinet(self, org_id, on=True):
        """The person marks a formal organization as the cabinet (there is one at most), or unmarks it."""
        org = self.get(org_id)
        if on and (kind_of(org) != "formal" or org.get("status") != "active"):
            raise OrgError("The cabinet is an active formal organization.")
        for other in self.list_orgs():
            if on and other["id"] != org_id and other.get("cabinet"):
                with self.change(other["id"]) as (o, db):
                    o.pop("cabinet", None)
                    self._event(db, o["id"], HUMAN, "organization.cabinet_unset", {})
        with self.change(org_id) as (org, db):
            if bool(org.get("cabinet")) != bool(on):
                if on:
                    org["cabinet"] = True
                else:
                    org.pop("cabinet", None)
                self._event(db, org_id, HUMAN, "organization.cabinet_set" if on else "organization.cabinet_unset", {})
        self.sync_offices(org_id)
        return {"org_id": org_id, "cabinet": bool(on)}

    def set_leader(self, org_id, member, by=HUMAN):
        """A new leader for a leader-led organization (the person in the Relic App, or an approved request)."""
        with self.change(org_id) as (org, db):
            if org.get("governance") != "leader":
                raise OrgError("%s decides by majority; it has no leader." % org["name"])
            if member not in org["members"]:
                raise OrgError("Unknown member " + str(member))
            previous = org.get("leader")
            org["leader"] = member
            if previous != member:
                self._event(db, org_id, by, "organization.leader_set", {"leader": member, "previous": previous})
        self.sync_offices(org_id)
        return {"org_id": org_id, "leader": member, "previous": previous}

    def dissolve(self, org_id, by=HUMAN):
        """End a formal organization: its sessions leave their seats there; its record stays."""
        return self._end(org_id, "dissolved", by)

    def _end(self, org_id, status, by):
        with self.change(org_id) as (org, db):
            if org.get("status") != "active":
                raise OrgError("%s is not active." % org["name"])
            org.update(status=status, ended_at=now(), ended_by=by)
            org.pop("cabinet", None)
            for (actor,) in db.execute("SELECT actor FROM seats WHERE org_id=? UNION SELECT actor FROM actors "
                                       "WHERE org_id=?", (org_id, org_id)).fetchall():
                self._unbind(db, actor, org_id)
            self._event(db, org_id, by, "organization." + status, {"name": org["name"]})
            if org.get("parent"):
                self._event(db, org["parent"], by, "organization.child_" + status, {"child": org_id,
                                                                                   "name": org["name"]})
        self.sync_offices(org_id)
        return {"org_id": org_id, "status": status}

    def sync_offices(self, org_id=None):
        """Bring every ex officio seat in line with the organizations as they are now (called after a change of
        leader, parent or cabinet, and when a leader's session takes its seat). org_id names the organization that
        changed; every one is brought in line, so a change elsewhere is never left behind. A leader without a session
        yet gets an empty seat, bound when its session takes the leader seat. A session the Relic App runs holds one
        seat only: its ex officio seats stay empty. Returns [(organization id, member, what)]."""
        orgs = {o["id"]: o for o in self.list_orgs() if o.get("status") == "active"}
        cab = next((o for o in sorted(orgs.values(), key=lambda o: o.get("created_at") or "") if o.get("cabinet")), None)
        wanted = {}  # (organization, department) -> (leader, carrier, harness, department)
        for dept in sorted(orgs.values(), key=lambda o: o.get("created_at") or ""):
            seat = (dept.get("members") or {}).get(dept.get("leader") or "")
            if kind_of(dept) != "formal" or dept.get("governance") != "leader" or not seat:
                continue
            targets = []
            parent = orgs.get(dept.get("parent"))
            if parent and kind_of(parent) == "formal":
                targets.append(parent["id"])
            if cab and cab["id"] != dept["id"] and cab["id"] not in targets:
                targets.append(cab["id"])
            carrier = seat.get("carrier") if (seat.get("config") or {}).get("surface") != "acp" else None
            for target in targets:
                wanted[(target, dept["id"])] = (dept["leader"], carrier, seat.get("harness") or "", dept)
        changes = []
        for target_id, target in orgs.items():
            stale = [name for name, s in (target.get("members") or {}).items() if s.get("ex_officio")
                     and (wanted.get((target_id, s["ex_officio"].get("org"))) or [None])[0] != s["ex_officio"].get("member")]
            missing = [k for k in wanted if k[0] == target_id and not any(
                (s.get("ex_officio") or {}).get("org") == k[1] and s["ex_officio"].get("member") == wanted[k][0]
                for s in target["members"].values())]
            moved = [name for name, s in target["members"].items() if s.get("ex_officio")
                     and (target_id, s["ex_officio"].get("org")) in wanted and name not in stale
                     and (s.get("carrier") != wanted[(target_id, s["ex_officio"]["org"])][1]
                          or s.get("role") != self._office_role(wanted[(target_id, s["ex_officio"]["org"])][3]))]
            if not (stale or missing or moved):
                continue
            with self.change(target_id) as (target, db):
                for name in stale:
                    s = target["members"].get(name)
                    if not s:
                        continue
                    if s.get("carrier"):
                        self._unbind(db, s["carrier"], target_id)
                    if target.get("leader") == name:
                        s.pop("ex_officio", None)  # it leads here now: the seat stays as an ordinary one
                        continue
                    del target["members"][name]
                    self._event(db, target_id, name, "member.office_ended", {"org": s["ex_officio"].get("org")})
                    changes.append((target_id, name, "removed"))
                for name in moved:
                    s = target["members"].get(name)
                    if not s or (target_id, (s.get("ex_officio") or {}).get("org")) not in wanted:
                        continue  # changed by someone else a moment ago: the next sync sees it
                    leader, carrier, harness, dept = wanted[(target_id, s["ex_officio"]["org"])]
                    s["role"] = self._office_role(dept)
                    if s.get("carrier") == carrier:
                        continue
                    if s.get("carrier"):
                        self._unbind(db, s["carrier"], target_id)
                    if carrier and self._holds(db, carrier, target_id):
                        carrier = None  # the session already sits here in a seat of its own
                    s.update(carrier=carrier, harness=harness or s.get("harness", ""),
                             carriers=s.get("carriers", 0) + (1 if carrier else 0))
                    if carrier:
                        self._bind(db, carrier, target_id, name)
                        self._event(db, target_id, name, "member.seated", {"harness": harness, "ex_officio": True})
                    changes.append((target_id, name, "bound"))
                for key in missing:
                    leader, carrier, harness, dept = wanted[key]
                    if carrier and self._holds(db, carrier, target_id):
                        continue  # the session already sits here in a seat of its own
                    name, n = leader, 1
                    while name in target["members"]:
                        n += 1
                        name = "%s-%s" % (leader, re.sub(r"[\s/\\:]+", "-", dept["name"]).strip("-") or dept["id"])
                        name += "" if n == 2 else "-%d" % (n - 1)
                    role = self._office_role(dept)
                    target["members"][name] = {"role": role, "joined_at": now(), "carrier": carrier,
                                               "carriers": 1 if carrier else 0, "notes": [], "open_episode": None,
                                               "harness": harness, "harness_history": [harness] if harness else [],
                                               "ex_officio": {"org": dept["id"], "member": leader}}
                    for ep in target["episodes"].values():
                        if ep.get("all_members") and ep["status"] == "open" and name not in ep["participants"]:
                            ep["participants"].append(name)
                    if carrier:
                        self._bind(db, carrier, target_id, name)
                    self._event(db, target_id, name, "member.joined", {"role": role, "harness": harness,
                                                                       "ex_officio": dept["id"]})
                    changes.append((target_id, name, "added"))
        return changes

    @staticmethod
    def _office_role(dept):
        from . import i18n
        return i18n.t("store.office_role", None, dept=dept["name"])

    # ---------------- subgroups ----------------
    def create_group(self, actor, name, purpose, leader, parent=None, members=None):
        """A subgroup for one piece of work, under parent (default: the organization the caller acts in), whose rules
        it inherits. Its members (default: every member of the first formal organization at or above parent) each
        take one more seat in it with the same session and name; leader leads it. No approval is needed."""
        org, me = self.require(actor)
        base, _ = self.split_actor(actor)
        under = self.find_org(parent) if parent else org
        held = {o["id"]: m for o, m, _ in self.seats_of(base)}
        if under["id"] not in held:
            raise OrgError("A subgroup is made under an organization you are a member of; %s is not one." % under["name"])
        home = under if kind_of(under) == "formal" else next(
            (a for a in self.ancestors(under) if kind_of(a) == "formal"), under)
        names = list(dict.fromkeys(members)) if members else list(home["members"])
        unknown = [n for n in names if n not in home["members"]]
        if unknown:
            raise OrgError("A subgroup's members come from %s; not members there: %s" % (home["name"], ", ".join(unknown)))
        if not (name or "").strip():
            raise OrgError("Give the subgroup a name.")
        if not leader or leader not in names:
            raise OrgError("The subgroup's leader is one of its members.")
        group = {"id": short_id("org_"), "name": name.strip(), "purpose": purpose or "", "governance": "leader",
                 "leader": leader, "status": "active", "created_at": now(), "kind": "subgroup", "parent": under["id"],
                 "home": home["id"], "created_by": qualified(under["id"], held[under["id"]]), "revision": 0,
                 "members": {}, "documents": {}, "tasks": {}, "episodes": {}, "protocols": {}, "reviews": {},
                 "automatic_reflection": True, "counters": {"task": 0, "episode": 0, "protocol": 0, "review": 0}}
        for n in names:
            seat = home["members"][n]
            carrier = seat.get("carrier") if (seat.get("config") or {}).get("surface") != "acp" else None
            harness = seat.get("harness") or ""
            group["members"][n] = {"role": seat.get("role", ""), "joined_at": now(), "carrier": carrier,
                                   "carriers": 1 if carrier else 0, "notes": [], "open_episode": None,
                                   "harness": harness, "harness_history": [harness] if harness else []}
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO orgs VALUES(?,?)", (group["id"], json.dumps(group, ensure_ascii=False)))
            self._event(db, group["id"], held[under["id"]], "organization.created",
                        {"name": group["name"], "governance": "leader", "kind": "subgroup", "parent": under["id"]})
            for n, seat in group["members"].items():
                if seat["carrier"]:
                    self._bind(db, seat["carrier"], group["id"], n)
                self._event(db, group["id"], n, "member.joined", {"role": seat["role"], "harness": seat["harness"]})
            self._event(db, under["id"], held[under["id"]], "organization.group_created",
                        {"child": group["id"], "name": group["name"], "leader": leader})
        return self.get(group["id"])

    def close_group(self, actor, ref=None):
        """Its leader closes a subgroup: the seats in it end, its record stays (subgroups below it close too)."""
        org, me = self.require(actor)
        group = self.find_org(ref) if ref else org
        if kind_of(group) != "subgroup":
            raise OrgError("%s is a formal organization: ask for its dissolution with group op=dissolve." % group["name"])
        if group["id"] != org["id"] or group.get("leader") != me:
            raise OrgError("Only the leader of %s closes it (the person can close it in the Relic App)." % group["name"])
        return self.close_group_as(group["id"], me)

    def close_group_as(self, group_id, by=HUMAN):
        group = self.get(group_id)
        if kind_of(group) != "subgroup":
            raise OrgError("Only a subgroup is closed; a formal organization is dissolved.")
        for below in self.descendants(group_id):
            if kind_of(below) == "subgroup" and below.get("parent") == group_id:
                self.close_group_as(below["id"], by)
        return self._end(group_id, "closed", by)

    # ---------------- approval of changes to formal organizations ----------------
    # Creating a formal organization, changing its parent or its leader and dissolving it wait for the secretary-
    # general when a member asks: the request is kept in the cabinet (without a cabinet, in the requester's
    # organization, for the person to decide in the Relic App). The person's own changes in the App take effect at once.
    REQUEST_KINDS = ("create", "parent", "leader", "dissolve")

    def approval_needed(self, actor, kind):
        """Whether a change asked by this session waits for a decision: always, unless the session is the
        secretary-general; creating an organization only once there is a cabinet."""
        if self.is_secretary_general(actor):
            return False
        return kind != "create" or self.cabinet() is not None

    def file_request(self, actor, kind, args, reason=""):
        if kind not in self.REQUEST_KINDS:
            raise OrgError("Request kinds: " + ", ".join(self.REQUEST_KINDS))
        base, _ = self.split_actor(actor)
        org, me = self.whoami(actor)
        cab = self.cabinet()
        home_id = cab["id"] if cab else (org["id"] if org else None)
        if not home_id:
            raise OrgError("There is no cabinet to decide this; ask the person to do it in the Relic App.")
        sender = (me if org["id"] == home_id else qualified(org["id"], me)) if org else "relic"
        with self.change(home_id) as (home, db):
            home["counters"]["request"] = home["counters"].get("request", 0) + 1
            rid = "Q%d" % home["counters"]["request"]
            r = {"id": rid, "kind": kind, "args": args, "reason": (reason or "").strip()[:500], "status": "pending",
                 "requester": {"actor": base, "org": org["id"] if org else None, "member": me,
                               "org_name": org["name"] if org else None},
                 "approver": "secretary-general" if cab else HUMAN, "at": now()}
            home.setdefault("requests", {})[rid] = r
            self._event(db, home_id, sender, "request.filed", {"id": rid, "kind": kind, "args": args})
            if cab and cab.get("leader") and cab["leader"] in home["members"] and sender != cab["leader"]:
                self._post(db, home_id, sender, [cab["leader"]],
                           "Approval request %s from %s: %s.%s\nDecide with the Relic group tool: op=approve or "
                           "op=deny, request_id=%s, note=<why>." % (rid, sender, self.request_text(r),
                                                                   (" Reason: " + r["reason"]) if r["reason"] else "", rid),
                           hop=self._sender_hop(org["id"], me) if org else 0)
        who = "the secretary-general (%s of %s)" % (cab["leader"], cab["name"]) if cab else "the person, in the Relic App"
        return {"request_id": rid, "status": "pending", "kind": kind, "approver": r["approver"],
                "text": "Request %s is filed and waits for %s; you get a message when it is decided." % (rid, who)}

    @staticmethod
    def request_text(r):
        a = r.get("args") or {}
        if r["kind"] == "create":
            return "create the formal organization '%s'" % a.get("name")
        if r["kind"] == "parent":
            return "place %s under %s" % (a.get("org_name") or a.get("org"), a.get("parent_name") or a.get("parent") or "nothing")
        if r["kind"] == "leader":
            return "make %s the leader of %s" % (a.get("member"), a.get("org_name") or a.get("org"))
        return "dissolve %s" % (a.get("org_name") or a.get("org"))

    def requests(self, org_id=None):
        """Every request kept in org_id (default: in any organization), newest first."""
        orgs = [self.get(org_id)] if org_id else self.list_orgs()
        rows = [dict(r, home=o["id"]) for o in orgs for r in (o.get("requests") or {}).values()]
        return sorted(rows, key=lambda r: (r.get("at") or "", r["id"]), reverse=True)

    def decide_request(self, actor, request_id, decision, note=""):
        """The secretary-general approves or denies a request kept in the cabinet."""
        cab = self.cabinet()
        if not cab:
            raise OrgError("There is no cabinet: the person decides requests in the Relic App.")
        if not self.is_secretary_general(actor):
            raise OrgError("Only the secretary-general (the leader of %s) decides requests." % cab["name"])
        return self._decide(cab["id"], request_id, decision, note, cab["leader"])

    def decide_request_as_human(self, org_id, request_id, decision, note=""):
        return self._decide(org_id, request_id, decision, note, HUMAN)

    def _decide(self, home_id, request_id, decision, note, by):
        if decision not in ("approve", "deny"):
            raise OrgError("decision is approve or deny.")
        r = (self.get(home_id).get("requests") or {}).get(request_id)
        if not r or r["status"] != "pending":
            raise OrgError("No pending request " + str(request_id))
        result, error = None, None
        if decision == "approve":
            try:
                result = self._carry_out(r)
            except OrgError as failure:
                error = str(failure)
        status = "denied" if decision == "deny" else "failed" if error else "approved"
        with self.change(home_id) as (home, db):
            r = home["requests"][request_id]
            r.update(status=status, decided_by=by, note=(note or "")[:300], decided_at=now(), result=result,
                     error=error)
            self._event(db, home_id, by, "request." + status, {"id": request_id, "kind": r["kind"]})
        self._tell_requester(home_id, r, by)
        return {k: r.get(k) for k in ("id", "kind", "status", "result", "error", "decided_by", "note")}

    def _carry_out(self, r):
        a, who = r.get("args") or {}, r["requester"]
        if r["kind"] == "create":
            org = self.create(who["actor"], a["name"], a.get("purpose", ""), a["member"], a.get("role", ""),
                              a.get("governance") or "leader")
            return {"org_id": org["id"], "member": a["member"]}
        if r["kind"] == "parent":
            return self.set_parent(a["org"], a.get("parent"))
        if r["kind"] == "leader":
            return self.set_leader(a["org"], a["member"], by=qualified(who["org"], who["member"]) if who.get("org") else HUMAN)
        return self.dissolve(a["org"], by=qualified(who["org"], who["member"]) if who.get("org") else HUMAN)

    def _tell_requester(self, home_id, r, by):
        """The requester learns the decision in its own organization (a created one: the new organization)."""
        who = r["requester"]
        place = (r.get("result") or {}).get("org_id") if r["kind"] == "create" and r["status"] == "approved" else who.get("org")
        member = (r.get("result") or {}).get("member") if place and place != who.get("org") else who.get("member")
        if not place or not member:
            return
        sender = HUMAN if by == HUMAN else (by if place == home_id else qualified(home_id, by))
        text = "Request %s (%s) was %s by %s.%s%s" % (
            r["id"], self.request_text(r), r["status"] if r["status"] != "failed" else "approved but could not be done",
            "the person" if by == HUMAN else by, (" Note: " + r["note"]) if r.get("note") else "",
            (" Error: " + r["error"]) if r.get("error") else "")
        with self.db() as db:
            try:
                there = self._load(db, place)
            except OrgError:
                return
            if member in there["members"]:
                self._post(db, place, sender, [member], text)

    def _post(self, db, org_id, sender, recipients, body, hop=0):
        cur = db.execute("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at,hop) VALUES(?,?,?,?,?,?,?)",
                         (org_id, sender, json.dumps(recipients), body, None, now(), int(hop or 0)))
        self._event(db, org_id, sender, "message.sent", {"id": cur.lastrowid, "to": recipients, "automatic": True})
        return cur.lastrowid

    def change_formal(self, actor, kind, a):
        """A member asks to change a formal organization (parent, leader, dissolve): the organization it acts in or
        one below it. Done at once for the secretary-general, otherwise filed as a request."""
        org, me = self.require(actor)
        target = org
        if a.get("org"):
            _, _, target, _ = self.reach(actor, a["org"])
        if kind_of(target) != "formal":
            raise OrgError("%s is a subgroup: its leader closes it with group op=close." % target["name"])
        args = {"org": target["id"], "org_name": target["name"]}
        if kind == "parent":
            parent = self.find_org(a["parent"]) if a.get("parent") else None
            args.update(parent=parent["id"] if parent else None, parent_name=parent["name"] if parent else None)
        elif kind == "leader":
            if not a.get("member") or a["member"] not in target["members"]:
                raise OrgError("Name the new leader: a member of %s." % target["name"])
            args["member"] = a["member"]
        if not self.approval_needed(actor, kind):
            return {"done": True, "result": self._carry_out({"kind": kind, "args": args,
                                                             "requester": {"org": org["id"], "member": me}})}
        return self.file_request(actor, kind, args, a.get("reason", ""))

    # ---------------- formation and membership ----------------
    def create(self, actor, name, purpose, member, role="", governance="leader"):
        if not name.strip() or not member.strip():
            raise OrgError("Give the organization a name and yourself a member name.")
        if governance not in ("leader", "peer"):
            raise OrgError("governance must be leader or peer.")
        org = {"id": short_id("org_"), "name": name.strip(), "purpose": purpose, "governance": governance,
               "leader": member if governance == "leader" else None, "status": "active", "created_at": now(),
               "kind": "formal",
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
               "leader": None, "founder": "human", "status": "active", "created_at": now(), "kind": "formal",
               "revision": 0, "members": {}, "documents": {},
               "tasks": {}, "episodes": {}, "protocols": {}, "reviews": {}, "automatic_reflection": True,
               "counters": {"task": 0, "episode": 0, "protocol": 0, "review": 0}}
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO orgs VALUES(?,?)", (org["id"], json.dumps(org, ensure_ascii=False)))
            self._event(db, org["id"], "human", "organization.created", {"name": name, "governance": governance})
        return org

    def join(self, actor, org_id, member, role=""):
        """Seat a session in org_id. Joining another organization adds a seat and keeps the session's other seats
        (the first one it holds is its main seat); joining an organization it already sits in makes that its main
        seat. A seat that gets a new carrier leaves only the previous carrier's seat in this organization."""
        member = member.strip()
        if not member or any(c in member for c in " /\\:"):
            raise OrgError("Member names are short words without spaces, e.g. alice or release.")
        actor, _ = self.split_actor(actor)
        for other, name, _ in self.seats_of(actor):
            config = (other["members"].get(name) or {}).get("config") or {}
            if other["id"] != org_id and config.get("surface") == "acp":
                raise OrgError("This session runs inside the Relic App as %s of %s; such a session holds one seat "
                               "only for now." % (name, other["name"]))
        target = (self.get(org_id)["members"].get(member) or {}).get("config") or {}
        if target.get("surface") == "acp" and any(o["id"] != org_id for o, _, _ in self.seats_of(actor)):
            raise OrgError("%s runs inside the Relic App; a session that holds another seat cannot take it." % member)
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
            self._bind(db, actor, org_id, member, main=self._holds(db, actor, org_id))
            if replaced and replaced != actor:
                self._unbind(db, replaced, org_id)
            leads = org.get("leader") == member
        if leads:
            self.sync_offices(org_id)  # the leader's session takes its ex officio seats too
        return {"org_id": org_id, "member": member, "role": self.get(org_id)["members"][member]["role"],
                "carrier_replaced": bool(replaced)}

    # ---------------- human operations (Relic App) ----------------
    def add_seat(self, org_id, member, role="", config=None):
        """Prepare a seat before any session sits in it; config says how Relic starts its sessions."""
        member = member.strip()
        if not member or any(c in member for c in " /\\:"):
            raise OrgError("Member names are short words without spaces, e.g. alice or release.")
        leads = False
        with self.change(org_id) as (org, db):
            seat = org["members"].get(member)
            if seat is None:
                seat = org["members"][member] = {"role": role, "joined_at": now(), "carrier": None, "carriers": 0,
                                                 "notes": [], "open_episode": None, "harness": (config or {}).get("harness", ""),
                                                 "harness_history": []}
                self._event(db, org_id, member, "member.prepared", {"role": role})
                if org["governance"] == "leader" and not org.get("leader"):
                    org["leader"] = member
                    leads = True
            if role:
                seat["role"] = role
            if config is not None:
                seat["config"] = config
                self._event(db, org_id, member, "member.configured", {k: v for k, v in config.items() if k not in ("env", "seat_token")})
        if leads:
            self.sync_offices(org_id)  # the new leader's ex officio seats (empty until its session sits)
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

    def unbind(self, actor, org_id=None):
        """Take a session out of its seat in org_id (without org_id: out of every seat it holds). The seat, its role,
        tasks and the protocols stay with the organization; the session keeps its seats elsewhere."""
        actor, _ = self.split_actor(actor)
        seats = [(o, m) for o, m, _ in self.seats_of(actor) if not org_id or o["id"] == org_id]
        with self.db() as db:
            if org_id:
                self._unbind(db, actor, org_id)
            else:
                db.execute("DELETE FROM actors WHERE actor=?", (actor,))
                db.execute("DELETE FROM seats WHERE actor=?", (actor,))
                db.execute("DELETE FROM focus WHERE actor=?", (actor,))
            for org, member in seats:
                self._event(db, org["id"], member, "member.unbound", {"harness": harness_of(actor)})
        org, member = seats[0] if seats else (None, None)
        return {"org_id": org["id"] if org else org_id, "member": member}

    def bind_alias(self, actor, org_id, member):
        """Bind an additional actor key to an existing seat without turnover (used for resumed sessions)."""
        with self.db() as db:
            self._bind(db, actor, org_id, member, main=True)

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

    def send(self, actor, to, body, episode_id=None, reply_to=None, org=None):
        """reply_to: answer inside the thread of that message; without `to`, everyone in the thread gets it.
        org: the organization to write in when it is not your own (one below yours, or one above it to report).
        Recipients named "<org id>/<member>", the way a message from another organization names its sender, say
        it too."""
        names = [str(n) for n in (to if isinstance(to, list) else ([to] if to else []))]
        if not org and names and all("/" in n for n in names):
            places = {n.split("/", 1)[0] for n in names}
            if len(places) != 1:
                raise OrgError("Write to one organization at a time.")
            org, to = places.pop(), [n.split("/", 1)[1] for n in names]
        elif any("/" in n for n in names):
            raise OrgError("Write to members of another organization in a message of its own (org=<its id>).")
        seated = self.scoped(actor, org) if org else None
        if seated:  # an organization the session sits in: write there as its member
            self.set_focus(actor, self.split_actor(seated)[1])
            actor, org = seated, None
        if org:
            own, member, target, way = self.reach(actor, org, up=True)
            if way:
                return self._send_across(own, member, target, way, to, body, episode_id, reply_to)
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

    def _send_across(self, own, member, target, way, to, body, episode_id, reply_to):
        """A message from a member of `own` to members of `target`, an organization below it (way "down") or above it
        (way "up": a report). It is kept in target, from "<own id>/<member>"; recipients there are woken as usual."""
        if not body or not body.strip():
            raise OrgError("Empty message.")
        if episode_id:
            raise OrgError("An episode belongs to one organization: leave episode_id out when you write to another one.")
        sender = qualified(own["id"], member)
        with self.db() as db:
            root = self._thread_root(db, target["id"], reply_to)
            if root and not to:
                recipients = [m for m in self._thread_people(db, target["id"], root) if m in target["members"]]
            elif not to or to == ["all"] or to == "all":
                recipients = list(target["members"])
            else:
                recipients = list(dict.fromkeys(to if isinstance(to, list) else [to]))
                if HUMAN in recipients:
                    raise OrgError("Write to the person (human) in your own organization.")
                unknown = set(recipients) - set(target["members"])
                if unknown:
                    raise OrgError("Unknown members of %s: %s" % (target["name"], ", ".join(sorted(unknown))))
            if not recipients:
                raise OrgError("%s has no members to write to." % target["name"])
            cur = db.execute("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at,hop,reply_to) "
                             "VALUES(?,?,?,?,?,?,?,?)", (target["id"], sender, json.dumps(recipients), body, None, now(),
                                                         self._sender_hop(own["id"], member), root))
            thread = {"reply_to": root} if root else {}
            self._event(db, target["id"], sender, "message.sent",
                        dict({"id": cur.lastrowid, "to": recipients, "from_org": own["id"]}, **thread))
            self._event(db, own["id"], member, "organization.reached",
                        {"what": "message", "org": target["id"], "name": target["name"], "way": way,
                         "id": cur.lastrowid, "to": recipients})
        return dict({"message_id": cur.lastrowid, "to": recipients, "org_id": target["id"]}, **thread)

    def _work_below(self, own, member, target, op, a):
        if op not in ("task", "doc_read"):
            raise OrgError("In an organization below yours you read documents (doc_read) and assign or update tasks "
                           "(task); the rest of its work belongs to its members.")
        if op == "task" and not a.get("task_id") and not a.get("owner"):
            raise OrgError("A task you assign in another organization needs an owner: one of its members.")
        result = self._work(target, qualified(own["id"], member), op, a)
        if op == "task":
            with self.db() as db:
                self._event(db, own["id"], member, "organization.reached",
                            {"what": "task", "org": target["id"], "name": target["name"], "way": "down",
                             "id": result["id"], "title": result["title"], "owner": result["owner"],
                             "status": result["status"]})
        return result

    def _protocol_below(self, own, member, target, op, a):
        """A protocol issued by a member of an organization above: it takes effect in target directly, and only an
        organization above can revise or retire it. downward=true binds the organizations below target too."""
        if op == "list":
            return self._protocol_detail(target, a["protocol_id"]) if a.get("protocol_id") else self._protocol_list(target)
        if op != "propose":
            raise OrgError("In an organization below yours you issue protocols (propose: they take effect there "
                           "directly) and list them; votes and use belong to its members.")
        strength = a.get("strength", "weak")
        if strength not in ("weak", "strong"):
            raise OrgError("strength: weak (guidance) or strong (executable rules).")
        if not a.get("title") or not a.get("rationale"):
            raise OrgError("A protocol needs a title and a rationale grounded in what happened.")
        evidence = a.get("evidence") or []
        retire_target, supersedes = a.get("retire_target"), a.get("supersedes")
        rules, summary = [], None
        if not retire_target:
            if strength == "weak":
                if a.get("rules"):
                    raise OrgError("Weak protocols carry guidance only; use strength strong for rules.")
                if not all(isinstance(a.get(k), str) and a[k].strip() for k in ("guidance", "trigger")):
                    raise OrgError("A weak protocol needs guidance and a trigger (when it applies).")
                if not evidence:
                    raise OrgError("Point to the evidence behind it: episode ids, message ids, task ids, files or commits.")
            else:
                ep = own["episodes"].get(a.get("episode_id"))
                if not ep or ep["status"] != "closed" or member not in ep["reflections"]:
                    raise OrgError("A strong protocol is issued from a closed episode of your own organization after "
                                   "you reflected on it.")
                rules, summary = self.prepare_rules(a.get("rules"), a.get("summary_for_person"), target, a["title"])
        sender = qualified(own["id"], member)
        issued = {"org": own["id"], "name": own["name"], "member": member}
        with self.change(target["id"]) as (org, db):
            if retire_target and org["protocols"].get(retire_target, {}).get("status") != "active":
                raise OrgError("Retiring needs an active protocol of %s." % target["name"])
            parent = org["protocols"].get(supersedes) if supersedes else None
            if supersedes and (not parent or parent["status"] != "active"):
                raise OrgError("A revision must supersede an active protocol of %s." % target["name"])
            org["counters"]["protocol"] += 1
            pid = "P%d" % org["counters"]["protocol"]
            p = {"id": pid, "title": a["title"], "rationale": a["rationale"], "strength": strength,
                 "guidance": a.get("guidance", ""), "trigger": a.get("trigger", ""), "scope": a.get("scope", ""),
                 "rules": rules if strength == "strong" else [], "evidence": evidence,
                 "episode_id": a.get("episode_id"), "supersedes": supersedes, "retire_target": retire_target,
                 "version": (parent["version"] + 1) if parent else 1, "author": sender, "issued_by": issued,
                 "inherit": bool(a.get("inherit", a.get("downward"))), "downward": bool(a.get("inherit", a.get("downward"))),
                 "status": "active", "votes": {}, "uses": [],
                 "created_at": now(), "activated_at": now()}
            if summary:
                p["summary_for_person"] = summary
            if retire_target:
                org["protocols"][retire_target].update(status="retired", retired_at=now(), retired_by=pid)
                p["status"] = "enacted"
            elif parent:
                parent.update(status="superseded", superseded_by=pid)
            org["protocols"][pid] = p
            self._event(db, target["id"], sender, "protocol.activated",
                        {"id": pid, "strength": strength, "issued_by": issued,
                         **({"retire_target": retire_target} if retire_target else {})})
            if p["status"] == "active":
                self._copy_to_person(db, org, p)
        with self.db() as db:
            self._event(db, own["id"], member, "organization.reached",
                        {"what": "protocol", "org": target["id"], "name": target["name"], "way": "down", "id": pid,
                         "title": p["title"], **({"retire_target": retire_target} if retire_target else {})})
        return p

    def _use_from_below(self, own, member, target, a):
        """A member records its use of a protocol that binds it from an organization above."""
        p = (target.get("protocols") or {}).get(a.get("protocol_id"))
        if not p or p.get("status") != "active" or not inherits(p):
            raise OrgError("From an organization below you record the use of an active protocol of %s that binds "
                           "downward." % target["name"])
        if a.get("outcome") not in ("followed", "deviated", "inapplicable") or not a.get("note"):
            raise OrgError("use needs outcome (followed, deviated, inapplicable) and a note on the concrete work.")
        with self.change(target["id"]) as (org, db):
            org["protocols"][p["id"]]["uses"].append({"by": qualified(own["id"], member), "outcome": a["outcome"],
                                                      "note": a["note"][:500], "at": now()})
            self._event(db, target["id"], qualified(own["id"], member), "protocol.used",
                        {"id": p["id"], "outcome": a["outcome"], "from_org": own["id"]})
            return {"id": p["id"], "uses": len(org["protocols"][p["id"]]["uses"])}

    def _protocol_list(self, org):
        listed = {pid: dict({k: p[k] for k in ("title", "strength", "status", "version", "author", "downward",
                                                "issued_by", "supersedes", "retire_target", "retired_by")
                             if p.get(k) is not None},
                            inherit=inherits(p), **({"check": True} if has_check(p) else {}))
                  for pid, p in org["protocols"].items()}
        lineage = self.inheritance(org)
        for above, p in lineage["inherited"]:
            listed["%s/%s" % (above["id"], p["id"])] = dict({"title": p["title"], "strength": p["strength"],
                                                              "status": p["status"], "version": p["version"],
                                                              "from": above["name"], "inherit": True},
                                                             **({"check": True} if has_check(p) else {}))
        for above, p, level, by, how in lineage["replaced"]:
            listed["%s/%s" % (above["id"], p["id"])] = {"title": p["title"], "strength": p["strength"],
                                                         "status": how, "version": p["version"], "from": above["name"],
                                                         "by": "%s/%s" % (level["id"], by), "at": level["name"]}
        return listed

    def _protocol_detail(self, org, ref):
        """One protocol in full, to review it before a vote: its rules with their code and examples, its note for the
        person, votes and uses. ref: one of this organization's (P3) or of an organization above ("<org id>/P3")."""
        ref = str(ref or "").strip()
        owner, pid = org, ref
        if "/" in ref:
            place, _, pid = ref.partition("/")
            owner = next((above for above in self.ancestors(org) if above["id"] == place), None)
            if owner is None:
                raise OrgError("%s is not a protocol of an organization above this one." % ref)
        p = (owner.get("protocols") or {}).get(pid)
        if not p:
            raise OrgError("Unknown protocol %s (protocol op=list shows them)." % ref)
        return dict(p, ref=ref, org=owner["id"], org_name=owner["name"], inherit=inherits(p))

    # ---------------- check rules: proposing one ----------------
    def prepare_rules(self, rules, summary, org, title):
        """A strong protocol's rules as they are kept, and its summary_for_person. A check rule is checked in full: its
        code loads (standard library only, a check function), every example is a call the rule covers and comes out as
        expected, and the code's sha256 is recorded. A protocol with a check rule needs summary_for_person in the
        person's language. Raises OrgError naming what to fix. Runs programs: call it outside a write transaction."""
        validate_rules(rules)
        if not any(rule["effect"] == "check" for rule in rules):
            return rules, (summary.strip() if isinstance(summary, str) and summary.strip() else None)
        summary = person_summary(summary)
        base = {"tool": "", "input": {}, "member": "", "role": "", "harness": "", "org_id": org["id"],
                "org_name": org["name"], "protocol_id": "P%d" % (org["counters"]["protocol"] + 1),
                "protocol_title": title, "recent": []}
        prepared, jobs, where = [], [], []
        for index, rule in enumerate(rules, 1):
            rule = {k: v for k, v in rule.items() if k != "code_sha256"}  # recorded here, never taken from the caller
            if rule["effect"] == "check":
                problem = checker.problems(rule["code"])
                if problem:
                    raise OrgError("Rule %d (check): %s" % (index, problem))
                rule.update(on_error=rule.get("on_error") or "allow", code_sha256=checker.sha256(rule["code"]))
                for n, example in enumerate(rule["examples"], 1):
                    call = self._example_call(example["call"], base)
                    if not example_in_scope(rule, call):
                        raise OrgError("Rule %d (check), example %d: the rule does not cover this call (it covers %s), "
                                       "so its program would never see it. Give examples of calls the rule covers."
                                       % (index, n, scope_text(rule)))
                    jobs.append((rule["code"], call))
                    where.append((index, n, example["expect"]))
            prepared.append(rule)
        wrong = []
        for (index, n, expect), result in zip(where, checker.run_many(jobs)):
            if "error" in result:
                wrong.append("rule %d, example %d: the program failed (%s): %s" % (index, n, result["error"],
                                                                                    result["detail"]))
            elif result["decision"] != expect:
                wrong.append("rule %d, example %d expects %s; check() answered %s%s" % (
                    index, n, expect, result["decision"], (" (reason: %s)" % result["reason"]) if result["reason"] else ""))
        if wrong:
            raise OrgError("The check program does not do what its examples say, so nothing was proposed:\n- %s\nFix "
                           "the code or the examples and propose it again." % "\n- ".join(wrong))
        return prepared, summary

    @staticmethod
    def _example_call(raw, base):
        """An example's call as the hook would give it: what it leaves out taken from base, tool and input in the shared
        vocabulary (normalize), recent calls in the hook's shape, every time in both forms (ISO text and seconds)."""
        call = dict(base, **raw)
        data = call.get("input") if isinstance(call.get("input"), dict) else {}
        call["tool"], call["input"] = normalize(str(call.get("tool") or ""), data)
        recent = []
        for item in call.get("recent") or []:
            if not isinstance(item, dict):
                continue
            tool, _ = normalize(str(item.get("tool") or ""), {})
            entry = dict(item, tool=short_tool(tool), summary=str(item.get("summary") or ""),
                         failed=bool(item.get("failed")), kind=item.get("kind") or activity_kind(tool))
            recent.append(checker.both_times(entry, "at", "ts"))
        call["recent"] = recent[:checker.RECENT]
        edits = [entry["ts"] for entry in recent if entry["kind"] == "edit" and entry["ts"] is not None]
        checker.both_times(call, "last_edit_at", "last_edit_ts", default=max(edits) if edits else None)
        return checker.both_times(call, "now", "now_ts", default=time.time())

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
        """Unread messages to the session in every seat it holds ("<actor>#<org id>": in that seat only), oldest
        first. A message that reached a seat other than the main one carries org_id and org_name: answer it there."""
        seats = self.seats_of(actor)
        if not seats:
            return []
        out = []
        with self.db() as db:
            for org, member, main in seats:
                # Filter by recipient before taking `limit`: messages to other members are never marked read by this
                # one, so a LIMIT in SQL could fill up with them and hide this member's own messages.
                rows = db.execute("""SELECT m.id, m.sender, m.recipients, m.body, m.episode_id, m.at, m.reply_to
                    FROM messages m WHERE m.org_id=? AND m.sender<>? AND m.recipients LIKE ? AND NOT EXISTS
                    (SELECT 1 FROM reads r WHERE r.org_id=m.org_id AND r.message_id=m.id AND r.member=?)
                    ORDER BY m.id""", (org["id"], member, "%" + json.dumps(member) + "%", member)).fetchall()
                found = 0
                for mid, sender, recipients, body, ep, at, reply_to in rows:
                    rec = json.loads(recipients)
                    if member not in rec:
                        continue
                    m = {"id": mid, "from": sender, "to": rec, "body": body, "episode_id": ep, "at": at,
                         "reply_to": reply_to, "_seat": (org["id"], member)}
                    if "/" in sender:  # a member of another organization: say which
                        m["from_org"] = self.org_names(db, [sender])[sender]
                    if not main:
                        m.update(org_id=org["id"], org_name=org["name"])
                    out.append(m)
                    found += 1
                    if found >= limit:
                        break
            out = sorted(out, key=lambda m: m["id"])[:limit]
            read = {}
            for m in out:
                read.setdefault(m["_seat"], []).append(m["id"])
            for (org_id, member), ids in read.items():
                if mark:
                    for mid in ids:
                        db.execute("INSERT OR IGNORE INTO reads VALUES(?,?,?,?)", (org_id, mid, member, now()))
                    self._event(db, org_id, member, "message.read", {"ids": ids})
                self._thread_heads(db, org_id, [m for m in out if m["_seat"][0] == org_id])  # a reply names its thread
            for m in out:
                m["seat"] = m.pop("_seat")[1]
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
            wanted = list(dict.fromkeys(to or []))
            recipients = [m for m in wanted if (m in org["members"] or m == HUMAN) and m != member]
            how = {"relayed": True} if relayed else {"automatic": True}
            first = None
            if recipients:
                cur = db.execute("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at,hop,reply_to) "
                                 "VALUES(?,?,?,?,?,?,?,?)", (org_id, member, json.dumps(recipients), body, None,
                                                             now(), int(hop or 0), root))
                self._event(db, org_id, member, "message.sent", dict(
                    {"id": cur.lastrowid, "to": recipients}, **how,
                    **({"via": via} if via else {}), **({"reply_to": root} if root else {})))
                first = cur.lastrowid
            # a member of another organization that wrote here (a receipt goes back to it) gets it in its own
            # organization, from "<this organization>/<member>"
            for name in wanted:
                place, _, other = str(name).partition("/")
                if not other or place == org_id:
                    continue
                try:
                    there = self._load(db, place)
                except OrgError:
                    continue
                if other not in there["members"]:
                    continue
                cur = db.execute("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at,hop,reply_to) "
                                 "VALUES(?,?,?,?,?,?,?,?)", (place, qualified(org_id, member), json.dumps([other]),
                                                             body, None, now(), int(hop or 0), None))
                self._event(db, place, qualified(org_id, member), "message.sent",
                            dict({"id": cur.lastrowid, "to": [other], "from_org": org_id}, **how))
                first = first or cur.lastrowid
            return first

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
        """Shared work in your organization; with org=<an organization below yours>, read its documents and
        assign or update its tasks."""
        if a.get("org"):
            own, me, target, way = self.reach(actor, a.pop("org"))
            if way:
                return self._work_below(own, me, target, op, a)
        org, member = self.require(actor)
        return self._work(org, member, op, a)

    def _work(self, org, member, op, a):
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
            if p["status"] == "active":
                self._copy_to_person(db, org, p)
        elif len(rejects) > len(org["members"]) - need or (org["governance"] == "leader" and org["leader"] in rejects):
            p.update(status="rejected")
            self._event(db, org["id"], p["author"], "protocol.rejected", {"id": p["id"]})

    def protocol(self, actor, op, a):
        if a.get("org"):
            own, me, target, way = self.reach(actor, a.pop("org"), up=op == "use")
            if way == "down":
                return self._protocol_below(own, me, target, op, a)
            if way == "up":
                return self._use_from_below(own, me, target, a)
        org, member = self.require(actor)
        if op == "list":
            return self._protocol_detail(org, a["protocol_id"]) if a.get("protocol_id") else self._protocol_list(org)
        rules, summary = [], None
        if op == "propose" and a.get("strength", "weak") == "strong" and not a.get("retire_target"):
            # before the write transaction: a check rule's examples run as programs, which takes a moment
            if not a.get("title") or not a.get("rationale"):
                raise OrgError("A proposal needs a title and a rationale grounded in what happened.")
            ep = org["episodes"].get(a.get("episode_id"))
            if not ep or ep["status"] != "closed" or member not in ep["reflections"]:
                raise OrgError("A strong protocol is proposed from a closed episode after you reflected on it.")
            rules, summary = self.prepare_rules(a.get("rules"), a.get("summary_for_person"), org, a["title"])
        with self.change(org["id"]) as (org, db):
            if op == "propose":
                strength = a.get("strength", "weak")
                if strength not in ("weak", "strong"):
                    raise OrgError("strength: weak (guidance) or strong (executable rules).")
                if not a.get("title") or not a.get("rationale"):
                    raise OrgError("A proposal needs a title and a rationale grounded in what happened.")
                evidence = a.get("evidence") or []
                retire_target, sup = a.get("retire_target"), a.get("supersedes")
                # "<org id>/<P#>": a protocol of an organization above, in effect here, that this one overrides or
                # stops for itself and the organizations below it (by this organization's own vote)
                inherited = {"%s/%s" % (o["id"], q["id"]): q for o, q in self.inherited_protocols(org)}
                for ref in (retire_target, sup):
                    if ref and ((org["protocols"].get(ref) or {}).get("issued_by")
                                or (inherited.get(ref) or {}).get("issued_by")):
                        raise OrgError("%s was issued by an organization above; only an organization above can "
                                       "revise or retire it." % ref)
                    if ref and "/" in str(ref) and ref not in inherited:
                        raise OrgError("%s is not a protocol of an organization above in effect here (protocol "
                                       "op=list shows them)." % ref)
                if retire_target:
                    if "/" not in str(retire_target) and org["protocols"].get(retire_target, {}).get("status") != "active":
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
                    validate_rules(rules)  # prepared above
                parent = (inherited.get(sup) if "/" in str(sup) else org["protocols"].get(sup)) if sup else None
                if sup and (not parent or parent["status"] != "active"):
                    raise OrgError("A revision must supersede an active protocol.")
                inherit = a.get("inherit", a.get("downward"))
                if inherit is None and sup and "/" in str(sup):
                    inherit = True  # an override passes on, in place of what it overrides
                org["counters"]["protocol"] += 1
                pid = "P%d" % org["counters"]["protocol"]
                p = {"id": pid, "title": a["title"], "rationale": a["rationale"], "strength": strength,
                     "guidance": a.get("guidance", ""), "trigger": a.get("trigger", ""), "scope": a.get("scope", ""),
                     "rules": rules if strength == "strong" else [], "evidence": evidence,
                     "episode_id": a.get("episode_id"), "supersedes": sup, "retire_target": retire_target,
                     "version": (parent["version"] + 1) if parent else 1, "author": member, "status": "proposed",
                     "inherit": bool(inherit), "downward": bool(inherit),
                     "votes": {member: {"vote": "approve", "reason": "author", "at": now()}}, "uses": [], "created_at": now()}
                if summary:
                    p["summary_for_person"] = summary
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
        """Return (allowed, reasons). Records review requests for require_review rules; runs the programs of the check
        rules that cover the call (side by side, each in a process of its own) and does what they answer."""
        tool, tool_input = normalize(tool, tool_input)
        actor = self.focused(actor)  # the organization the session works for now: its protocols bind this call
        org, member = self.whoami(actor)
        if not org or is_relic_tool(tool):
            return True, []
        role = org["members"][member].get("role", "")
        reasons, consumed, checks = [], [], []
        last_edit = None
        # this organization's own protocols and those in effect here from the organizations above
        for owner, p in self.effective_protocols(org):
            if p["status"] != "active" or p["strength"] != "strong":
                continue
            pid = p["id"] if owner["id"] == org["id"] else "%s/%s" % (owner["id"], p["id"])
            for rule in p["rules"]:
                if not rule_applies(rule, member, role, tool, tool_input):
                    continue
                label = "%s %s" % (pid, p["title"])
                if rule["effect"] == "deny":
                    reasons.append("%s: %s" % (label, rule.get("reason", "blocked by an adopted protocol.")))
                elif rule["effect"] == "check":
                    checks.append((owner, p, pid, label, rule))
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
                        rid = self._request_review(org["id"], member, pid, tool, tool_input)
                        reasons.append("%s: another member must approve this exact action. Review request %s is open; "
                                       "ask a member to run review approve %s, then retry the same call." % (label, rid, rid))
        outcomes = self._run_checks(org, member, role, checks, tool, tool_input)
        for (owner, p, pid, label, rule), outcome in zip(checks, outcomes):
            if outcome["decision"] == "deny":
                reasons.append("%s: %s" % (label, outcome["reason"]))
            elif outcome["decision"] == "review":
                approved = self._approved_review(org, member, tool, tool_input)
                if approved:
                    consumed.append(approved)
                else:
                    rid = self._request_review(org["id"], member, pid, tool, tool_input, why=outcome["reason"])
                    reasons.append("%s: %s. Another member must approve this exact action. Review request %s is open; "
                                   "ask a member to run review approve %s, then retry the same call."
                                   % (label, outcome["reason"].rstrip(". "), rid, rid))
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
            if checks:
                self._record_checks(db, org, member, tool, tool_input, checks, outcomes)
        return not reasons, reasons

    # ---------------- check rules: running them ----------------
    ALERT_EVERY = 24 * 3600  # a failure of one kind of one protocol's program is announced once a day

    def _run_checks(self, org, member, role, checks, tool, tool_input):
        """For each check rule that covers the call, what it does with it: {decision, reason, error, detail}. decision
        is the program's answer, or the rule's on_error when the program failed (error: its kind) or its code is not
        the code recorded when the protocol was proposed (error: tampered)."""
        if not checks:
            return []
        recent, last_edit = self._recent_calls(org["id"], member)
        results, jobs = [None] * len(checks), []
        for i, (owner, p, pid, label, rule) in enumerate(checks):
            code = rule.get("code") or ""
            if checker.sha256(code) != rule.get("code_sha256"):
                results[i] = {"error": "tampered", "detail": "the code is not the code that was proposed and voted on "
                                                             "(its sha256 differs from the one recorded)"}
            else:
                jobs.append((i, code, self._check_call(org, member, role, pid, p, tool, tool_input, recent, last_edit)))
        for (i, _, _), result in zip(jobs, checker.run_many([(code, call) for _, code, call in jobs])):
            results[i] = result
        return [self._check_outcome(rule, result) for (_, _, _, _, rule), result in zip(checks, results)]

    @staticmethod
    def _check_outcome(rule, result):
        if "error" not in result:
            return {"decision": result["decision"], "reason": result["reason"], "error": None, "detail": ""}
        on_error = rule.get("on_error") if rule.get("on_error") in checker.ON_ERROR else "allow"
        why = ("its check program is not the one voted on (the code changed after it was proposed)"
               if result["error"] == "tampered" else
               "its check program failed (%s: %s)" % (result["error"], " ".join(str(result.get("detail") or "").split())[:200]))
        return {"decision": on_error, "error": result["error"], "detail": str(result.get("detail") or ""),
                "reason": "%s, and this protocol %s the call when that happens (on_error %s). Tell the organization: a "
                          "revision (supersedes) fixes it" % (why, "blocks" if on_error == "deny" else "allows", on_error)}

    def _recent_calls(self, org_id, member):
        """([the member's latest tool calls here, newest first], time of its latest edit or None), as a check program
        gets them: tool, kind (edit, run, other), summary, failed, at (ISO) and ts (seconds)."""
        with self.db() as db:
            rows = db.execute("SELECT tool, kind, summary, failed, at FROM activity WHERE org_id=? AND member=? "
                              "ORDER BY id DESC LIMIT ?", (org_id, member, checker.RECENT)).fetchall()
            edit = db.execute("SELECT MAX(at) FROM activity WHERE org_id=? AND member=? AND kind='edit'",
                              (org_id, member)).fetchone()[0]
        recent = [checker.both_times({"tool": short_tool(tool or ""), "kind": kind,
                                      "summary": " ".join(str(summary or "").split())[:200], "failed": bool(failed)},
                                     "at", "ts", default=at) for tool, kind, summary, failed, at in rows]
        return recent, edit

    @staticmethod
    def _check_call(org, member, role, pid, p, tool, tool_input, recent, last_edit):
        """The call a check program gets (see relic_core/checker.py and the skill)."""
        data, clipped = checker.clip(tool_input)
        call = {"tool": tool, "input": data, "member": member, "role": role,
                "harness": (org["members"].get(member) or {}).get("harness") or "", "org_id": org["id"],
                "org_name": org["name"], "protocol_id": pid, "protocol_title": p["title"], "recent": recent}
        if clipped:
            call["input_clipped"] = True
        checker.both_times(call, "last_edit_at", "last_edit_ts", default=last_edit)
        return checker.both_times(call, "now", "now_ts", default=time.time())

    def _record_checks(self, db, org, member, tool, tool_input, checks, outcomes):
        """Allowed calls are only counted. A deny or a review is an event (protocol.checked) where the call was made; a
        failure is an event there too (protocol.check_failed) and is announced in the group chat of the protocol's
        organization (protocol.check_alert), once a day per protocol and kind of failure."""
        stamp = time.time()
        what = str(tool_input.get("command") or ", ".join(_paths_of(tool_input)) or canonical(tool_input))
        for (owner, p, pid, label, rule), outcome in zip(checks, outcomes):
            key = ("error:" + outcome["error"]) if outcome["error"] else outcome["decision"]
            db.execute("INSERT INTO check_counts VALUES(?,?,?,1,?) ON CONFLICT(org_id, protocol_id, outcome) DO UPDATE "
                       "SET n=n+1, last_at=excluded.last_at", (owner["id"], p["id"], key, stamp))
            if outcome["error"]:
                self._event(db, org["id"], member, "protocol.check_failed",
                            {"id": pid, "kind": outcome["error"], "detail": outcome["detail"][:300], "tool": tool,
                             "on_error": outcome["decision"]})
                fresh = db.execute("INSERT INTO check_alerts VALUES(?,?,?,?) ON CONFLICT(org_id, protocol_id, kind) DO "
                                   "UPDATE SET at=excluded.at WHERE excluded.at - check_alerts.at >= ?",
                                   (owner["id"], p["id"], outcome["error"], stamp, self.ALERT_EVERY)).rowcount
                if fresh:
                    away = {} if owner["id"] == org["id"] else {"org": org["id"], "org_name": org["name"]}
                    self._event(db, owner["id"], member if not away else qualified(org["id"], member),
                                "protocol.check_alert", dict({"id": p["id"], "title": p["title"],
                                                              "kind": outcome["error"], "detail": outcome["detail"][:300],
                                                              "on_error": outcome["decision"]}, **away))
            elif outcome["decision"] != "allow":
                self._event(db, org["id"], member, "protocol.checked",
                            {"id": pid, "decision": outcome["decision"], "reason": outcome["reason"], "tool": tool,
                             "input": what[:200]})

    def check_trouble(self, org):
        """[(protocol as named in org, title, {kind of failure: count}, time of the latest failure)] for the check rules
        in effect in org whose programs have failed."""
        wanted = {(owner["id"], p["id"]): (p["id"] if owner["id"] == org["id"] else "%s/%s" % (owner["id"], p["id"]),
                                           p["title"])
                  for owner, p in self.effective_protocols(org) if p.get("status") == "active" and has_check(p)}
        if not wanted:
            return []
        with self.db() as db:
            rows = db.execute("SELECT org_id, protocol_id, outcome, n, last_at FROM check_counts "
                              "WHERE outcome LIKE 'error:%'").fetchall()
        found = {}
        for org_id, pid, outcome, n, last in rows:
            if (org_id, pid) in wanted:
                kinds, latest = found.get((org_id, pid), ({}, 0.0))
                kinds[outcome.split(":", 1)[1]] = n
                found[(org_id, pid)] = (kinds, max(latest, last or 0.0))
        return [(wanted[key][0], wanted[key][1], kinds, latest) for key, (kinds, latest) in found.items()]

    # ---------------- copies to the person ----------------
    # A protocol with a check rule takes effect by the organization's vote alone (or as issued from above); the person
    # is sent a copy with its summary_for_person. The person reads it in the Relic App, marks it read or retires the
    # protocol at once: the person is above every organization and needs no vote.
    def _copy_to_person(self, db, org, p):
        if not has_check(p):
            return None
        votes = p.get("votes") or {}
        body = {"org": org["id"], "org_name": org["name"], "protocol_id": p["id"], "title": p["title"],
                "summary": p.get("summary_for_person") or "", "rationale": p.get("rationale") or "",
                "author": p.get("author"), "issued_by": p.get("issued_by"),
                "approved_by": [m for m, v in votes.items() if v.get("vote") == "approve" and m != p.get("author")],
                "activated_at": p.get("activated_at"), "supersedes": p.get("supersedes"), "version": p.get("version"),
                "inherit": inherits(p), "rules": p.get("rules") or []}
        cid = db.execute("INSERT INTO cc(org_id, protocol_id, body, at) VALUES(?,?,?,?)",
                         (org["id"], p["id"], json.dumps(body, ensure_ascii=False), now())).lastrowid
        self._event(db, org["id"], p.get("author") or HUMAN, "protocol.copied", {"id": p["id"], "cc": cid})
        return cid

    def copies(self, limit=200, cid=None):
        """What was copied to the person, newest first (with cid: that copy only): each copy as it was sent (org,
        org_name, protocol_id, title, summary, author, issued_by, approved_by, activated_at, supersedes, version,
        inherit, rules), with read and read_at, the protocol as it is now (status, retired_by, retired_at,
        superseded_by; org_status) and how its check programs answered so far (stats: allow, deny, review, error,
        total)."""
        with self.db() as db:
            if cid is None:
                rows = db.execute("SELECT id, org_id, protocol_id, body, at, read_at FROM cc ORDER BY id DESC LIMIT ?",
                                  (int(limit),)).fetchall()
            else:
                rows = db.execute("SELECT id, org_id, protocol_id, body, at, read_at FROM cc WHERE id=?",
                                  (int(cid),)).fetchall()
            counts = db.execute("SELECT org_id, protocol_id, outcome, n FROM check_counts").fetchall()
        stats = {}
        for org_id, pid, outcome, n in counts:
            s = stats.setdefault((org_id, pid), {"allow": 0, "deny": 0, "review": 0, "error": 0})
            key = "error" if outcome.startswith("error:") else outcome
            s[key] = s.get(key, 0) + (n or 0)
        orgs = {o["id"]: o for o in self.list_orgs()}
        out = []
        for row_id, org_id, pid, body, at, read_at in rows:
            item = json.loads(body)
            org = orgs.get(org_id) or {}
            p = (org.get("protocols") or {}).get(pid) or {}
            s = dict(stats.get((org_id, pid)) or {"allow": 0, "deny": 0, "review": 0, "error": 0})
            s["total"] = sum(s.values())
            item.update(id=row_id, at=at, read=bool(read_at), read_at=read_at, status=p.get("status"),
                        retired_by=p.get("retired_by"), retired_at=p.get("retired_at"),
                        superseded_by=p.get("superseded_by"), org_status=org.get("status"),
                        org_name=org.get("name") or item.get("org_name"), stats=s)
            out.append(item)
        return out

    def copy(self, cid):
        """One copy (as copies() gives it), or None."""
        return next(iter(self.copies(cid=cid)), None)

    def unread_copies(self):
        with self.db() as db:
            return db.execute("SELECT COUNT(*) FROM cc WHERE read_at IS NULL").fetchone()[0]

    def read_copy(self, cid):
        """The person read a copy ("got it")."""
        with self.db() as db:
            return db.execute("UPDATE cc SET read_at=? WHERE id=? AND read_at IS NULL", (now(), int(cid))).rowcount

    def retire_by_person(self, org_id, protocol_id):
        """The person retires a protocol (from the Relic App): it stops binding at once, and so does its inherited copy
        in every organization below. No vote: the person is above every organization. Both group chats get a notice and
        members see it in their status."""
        ref = "%s/%s" % (org_id, protocol_id)
        below = [d for d in self.descendants(org_id)
                 if any("%s/%s" % (o["id"], q["id"]) == ref for o, q in self.inherited_protocols(d))]
        with self.change(org_id) as (org, db):
            p = org["protocols"].get(protocol_id)
            if not p:
                raise OrgError("Unknown protocol " + str(protocol_id))
            if p["status"] != "active":
                raise OrgError("%s is not in effect (it is %s)." % (protocol_id, p["status"]))
            p.update(status="retired", retired_at=now(), retired_by=HUMAN)
            self._event(db, org_id, HUMAN, "protocol.retired_by_person", {"id": protocol_id, "title": p["title"]})
            name = org["name"]
        with self.db() as db:
            for d in below:
                self._event(db, d["id"], HUMAN, "protocol.retired_by_person",
                            {"id": ref, "title": p["title"], "from": org_id, "from_name": name})
        return {"org_id": org_id, "protocol_id": protocol_id, "status": "retired", "below": [d["id"] for d in below]}

    def retired_by_person(self, org, limit=5):
        """[(protocol as named in org, title, when)]: protocols the person retired, of this organization and the
        inheritable ones of the organizations above it, the latest first."""
        found = [(p["id"], p["title"], p.get("retired_at") or "") for p in org["protocols"].values()
                 if p.get("retired_by") == HUMAN]
        for above in self.ancestors(org):
            found += [("%s/%s" % (above["id"], p["id"]), p["title"], p.get("retired_at") or "")
                      for p in (above.get("protocols") or {}).values() if p.get("retired_by") == HUMAN and inherits(p)]
        return sorted(found, key=lambda item: item[2], reverse=True)[:limit]

    def _approved_review(self, org, member, tool, tool_input):
        key = canonical([tool, tool_input])
        for rid, r in org["reviews"].items():
            if r["subject"] == member and r["status"] == "approved" and r["action"] == key:
                return rid
        return None

    def _request_review(self, org_id, member, pid, tool, tool_input, why=None):
        """A review request for this exact action (why: the reason a check program gave for sending it to review)."""
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
            if why:
                org["reviews"][rid]["why"] = str(why)[:checker.REASON_MAX]
            self._event(db, org_id, member, "review.requested", {"id": rid, "protocol_id": pid})
            return rid

    def review(self, actor, op, a):
        org, member = self.require(actor)
        if op == "list":
            return [dict({k: r[k] for k in ("id", "protocol_id", "subject", "tool", "summary", "status")},
                         **({"why": r["why"]} if r.get("why") else {}))
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
        actor = self.focused(actor)  # work done for the organization the session works for now
        org, member = self.whoami(actor)
        if not org or is_relic_tool(tool):
            return
        kind = activity_kind(tool)
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
        """A turn ended: close the session's open turn episodes in every seat it holds and go back to its main seat
        (focus). Returns the first episode closed (None when there was none)."""
        seats = self.seats_of(actor)
        self.clear_focus(actor)
        closed = []
        for org, member, _ in seats:
            if not (org["members"][member].get("turn_episode")):
                continue
            with self.change(org["id"]) as (org, db):
                seat = org["members"].get(member) or {}
                ep = org["episodes"].get(seat.get("turn_episode") or "")
                if not ep or ep["status"] != "open":
                    continue
                ep.update(status="closed", outcome="observed", closed_at=now(),
                          summary="%d friction signal(s) observed" % len(ep.get("friction", [])))
                seat["turn_episode"] = None
                self._event(db, org["id"], member, "episode.closed", {"id": ep["id"], "kind": "turn",
                                                                       "friction": len(ep.get("friction", []))})
                closed.append(ep)
        return closed[0] if closed else None

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
