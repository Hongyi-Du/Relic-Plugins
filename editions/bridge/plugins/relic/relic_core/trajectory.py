"""Read a member's trajectory from its harness's own transcript, in one shape for both harnesses.

Claude Code: ~/.claude/projects/<project>/<session-id>.jsonl (user / assistant entries, tool_use and tool_result parts).
Codex: the thread's rollout file (path in ~/.codex/state_*.sqlite, threads.rollout_path), response_item entries
(message, function_call, custom_tool_call, *_output).
Each step: {"at", "role": user | assistant | thinking | tool_call | tool_result | context, "text", "tool"?}.
Both CLI and desktop app of each harness write the same files, so any member can read any other.

A session's memory is what its harness keeps about that session besides the transcript, and nothing that belongs to
other sessions. Codex: the memory summaries of the thread (memories/rollout_summaries/*.md whose front matter names the
thread_id) and the tasks of memories/MEMORY.md whose sources cite the thread; a task group's shared sections (user
preferences, reusable knowledge, failures) are distilled from several chats and stay out. Claude Code keeps its memory
per project, shared by every session there, so none of it is exported as one session's memory.
"""
import contextlib
import json
import os
import re
import sqlite3
from pathlib import Path

CLIP = 1200


def _clip(text, n=CLIP):
    text = str(text or "")
    return text if not n or len(text) <= n else text[:n] + " …[%d more chars]" % (len(text) - n)


def codex_home():
    return Path(os.getenv("CODEX_HOME") or Path.home() / ".codex")


def claude_home():
    return Path(os.getenv("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def locate(actor):
    """(harness, session id, transcript path or None) for an actor key."""
    if actor.startswith("codex:"):
        thread = actor.split(":", 1)[1]
        root = codex_home()
        for db_path in sorted(root.glob("state_*.sqlite"), reverse=True):
            try:
                with contextlib.closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
                    row = db.execute("SELECT rollout_path FROM threads WHERE id=?", (thread,)).fetchone()
            except sqlite3.Error:
                continue
            if row and row[0] and Path(row[0]).is_file():
                return "codex", thread, Path(row[0])
        for folder in ("sessions", "archived_sessions"):
            hits = list((root / folder).rglob("rollout-*%s.jsonl" % thread)) if (root / folder).is_dir() else []
            if hits:
                return "codex", thread, hits[0]
        return "codex", thread, None
    session, _, agent = actor.partition("/")  # a Claude Code subagent actor is <session>/<agent>
    projects = claude_home() / "projects"
    hits = list(projects.glob("*/%s/subagents/agent-%s.jsonl" % (session, agent))) if agent else []
    hits = hits or list(projects.glob("*/%s.jsonl" % session))
    return "claude-code", session, hits[0] if hits else None


def _lines(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def _harness_text(text):
    # Injected context blocks (<environment_context>, <session-context>, <system-reminder> ...) are not what anyone said.
    return text.lstrip().startswith("<")


def _join(parts):
    return "\n".join(p.get("text", "") for p in parts or [] if isinstance(p, dict) and p.get("text"))


def claude_steps(path, clip=CLIP, full=False):
    """full=True keeps everything: thinking, injected context, compaction summaries and in-file subagent turns."""
    for e in _lines(path):
        kind, side = e.get("type"), bool(e.get("isSidechain"))
        if side and not full:
            continue
        at = e.get("timestamp", "")
        if kind == "summary" and full and e.get("summary"):
            yield {"at": at, "role": "context", "text": _clip("[summary] " + e["summary"], clip)}
            continue
        if kind not in ("user", "assistant"):
            continue
        extra = {"sidechain": True} if side else {}
        content = (e.get("message") or {}).get("content")
        if isinstance(content, str):
            if kind == "user":
                injected = e.get("isMeta") or e.get("isCompactSummary") or _harness_text(content)
                if not injected:
                    yield dict(extra, at=at, role="user", text=_clip(content, clip))
                elif full:
                    yield dict(extra, at=at, role="context", text=_clip(content, clip))
            elif content:
                yield dict(extra, at=at, role="assistant", text=_clip(content, clip))
            continue
        for part in content or []:
            if not isinstance(part, dict):
                continue
            t = part.get("type")
            if t == "text" and part.get("text"):
                said = "assistant" if kind == "assistant" else "user"
                if kind == "user" and (e.get("isMeta") or _harness_text(part["text"])):
                    said = "context"
                if said != "context" or full:
                    yield dict(extra, at=at, role=said, text=_clip(part["text"], clip))
            elif t == "thinking" and full and part.get("thinking"):
                yield dict(extra, at=at, role="thinking", text=_clip(part["thinking"], clip))
            elif t == "tool_use":
                yield dict(extra, at=at, role="tool_call", tool=part.get("name", ""),
                           text=_clip(json.dumps(part.get("input"), ensure_ascii=False, indent=1 if full else None), clip))
            elif t == "tool_result":
                body = part.get("content")
                if isinstance(body, list):
                    body = "\n".join(p.get("text", "") if p.get("type") == "text" else "[%s]" % p.get("type")
                                     for p in body if isinstance(p, dict))
                yield dict(extra, at=at, role="tool_result", error=bool(part.get("is_error")), text=_clip(body, clip))
            elif t == "image" and full:
                yield dict(extra, at=at, role=kind if kind == "user" else "assistant", text="[image]")


def codex_steps(path, clip=CLIP, full=False):
    """full=True keeps everything: base and developer instructions, injected context, reasoning, compactions."""
    for e in _lines(path):
        p, at, kind = e.get("payload") or {}, e.get("timestamp", ""), e.get("type")
        if kind == "session_meta" and full:
            base = p.get("base_instructions")
            base = base.get("text") if isinstance(base, dict) else base
            if base:
                yield {"at": at, "role": "context", "text": _clip("[base instructions]\n" + str(base), clip)}
            continue
        if kind == "compacted" and full:
            yield {"at": at, "role": "context", "text": _clip("[compacted]\n" + str(p.get("message") or ""), clip)}
            continue
        if kind != "response_item":
            continue
        t = p.get("type")
        if t == "message":
            text = _join(p.get("content"))
            if not text:
                continue
            role = p.get("role")
            if role in ("user", "assistant") and not (role == "user" and _harness_text(text)):
                yield {"at": at, "role": role, "text": _clip(text, clip)}
            elif full:
                yield {"at": at, "role": "context", "text": _clip("[%s]\n%s" % (role, text), clip)}
        elif t == "reasoning" and full:
            text = _join(p.get("summary")) or _join(p.get("content"))
            if text:
                yield {"at": at, "role": "thinking", "text": _clip(text, clip)}
        elif t in ("function_call", "custom_tool_call"):
            yield {"at": at, "role": "tool_call", "tool": p.get("name", ""),
                   "text": _clip(p.get("arguments") or p.get("input") or "", clip)}
        elif t == "local_shell_call":
            yield {"at": at, "role": "tool_call", "tool": "shell",
                   "text": _clip(json.dumps((p.get("action") or {}).get("command"), ensure_ascii=False), clip)}
        elif t in ("web_search_call", "tool_search_call", "image_generation_call") and full:
            yield {"at": at, "role": "tool_call", "tool": t[:-5], "text": _clip(json.dumps(p.get("action") or p, ensure_ascii=False), clip)}
        elif t in ("function_call_output", "custom_tool_call_output", "tool_search_output"):
            out = p.get("output")
            if isinstance(out, dict):
                out = out.get("content") or out.get("output") or json.dumps(out, ensure_ascii=False)
            elif isinstance(out, list):
                out = _join(out) or json.dumps(out, ensure_ascii=False)
            yield {"at": at, "role": "tool_result", "text": _clip(out, clip)}


def surface(path, harness):
    """Where the session ran, as the harness recorded it (Claude Code entrypoint; Codex originator and source)."""
    for e in _lines(path):
        if harness == "codex" and e.get("type") == "session_meta":
            p = e.get("payload") or {}
            return "originator %s, source %s, Codex %s" % (p.get("originator"), p.get("source"), p.get("cli_version"))
        if harness != "codex" and e.get("entrypoint"):
            return "entrypoint %s, Claude Code %s" % (e["entrypoint"], e.get("version"))
    return "unknown"


def claude_subagents(path):
    """Newer Claude Code keeps each subagent's transcript in <session>/subagents/agent-<id>.jsonl."""
    folder = path.with_suffix("") / "subagents"
    return sorted(folder.glob("agent-*.jsonl")) if folder.is_dir() else []


def steps(actor, clip=CLIP, full=False):
    harness, session, path = locate(actor)
    if path is None:
        return harness, session, None, []
    return harness, session, path, list((codex_steps if harness == "codex" else claude_steps)(path, clip, full))


LABEL = {"user": "User", "assistant": "Assistant", "thinking": "Thinking", "tool_call": "Tool call",
         "tool_result": "Tool result", "context": "Injected context"}


def _render(items, out):
    for n, s in enumerate(items, 1):
        name = (" `%s`" % s["tool"]) if s.get("tool") else ""
        flags = (" (subagent)" if s.get("sidechain") else "") + (" (error)" if s.get("error") else "")
        out += ["## %d. %s%s%s  %s" % (n, LABEL.get(s["role"], s["role"]), name, flags, s.get("at", "")), "",
                "`````", s["text"], "`````", ""]


MASK = "[REDACTED]"
SECRETS = [
    re.compile(r"sk-(?:ant-|proj-|svcacct-)?[A-Za-z0-9_\-]{16,}"),  # OpenAI / Anthropic style API keys
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}"),      # GitHub tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                             # AWS access key ids
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}"),                        # Google API keys
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),                 # Slack tokens
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-~+/]{20,}=*"),
]
CREDENTIAL = r"(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|密码)"
# A credential named in text: "password: x", "token=x", "密码：`x`", JSON "password": "x" and escaped \"password\":\"x\";
# and a code of 6+ characters right after the word ("密码保护，123456").
PASSWORDS = [
    re.compile(r"(?i)(" + CREDENTIAL + r")(\\?[\"']?\s*(?:[:：=]|是|为)\s*\\?)([`'\"“]?)([^\s`'\"”\\，。,;；)）]{4,})"),
    re.compile(r"(?i)(password|passwd|密码)([^\n\d]{0,10}?)()(\d[\w\-]{5,})"),
]
# A JSON field whose name says it holds a credential: everything under it is masked.
SENSITIVE_KEY = re.compile(r"(?i)(?:^|[_\-. ])(?:password|passwd|pass|pwd|secret|token|api[_-]?key|apikey|"
                           r"access[_-]?key|private[_-]?key|authorization|cookie|credentials?)$|密码$")


def redact_text(text):
    """Mask obvious credentials: API keys and tokens by their shape, passwords by the word in front of them."""
    for pattern in SECRETS:
        text = pattern.sub(MASK, text)
    for pattern in PASSWORDS:
        text = pattern.sub(lambda m: m.group(1) + m.group(2) + m.group(3) + MASK, text)
    return text


def _redact_value(value, sensitive=False):
    """Mask credentials inside a parsed JSON value: values under credential-named fields, credential-shaped strings,
    and JSON documents carried inside strings (tool arguments)."""
    if isinstance(value, str):
        if sensitive and value:
            return MASK
        if value.strip()[:1] in ("{", "["):
            try:
                inner = json.loads(value)
            except ValueError:
                inner = None
            if isinstance(inner, (dict, list)):
                masked = _redact_value(inner)
                if masked != inner:
                    return json.dumps(masked, ensure_ascii=False)
        return redact_text(value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return MASK if sensitive else value
    if isinstance(value, list):
        return [_redact_value(v, sensitive) for v in value]
    if isinstance(value, dict):
        return {k: _redact_value(v, sensitive or bool(SENSITIVE_KEY.search(str(k)))) for k, v in value.items()}
    return value


def redact_jsonl(source, dest):
    """Copy a JSONL transcript with credentials masked inside its strings; every line stays valid JSON."""
    with open(source, encoding="utf-8", errors="replace", newline="") as src, \
            open(dest, "w", encoding="utf-8", newline="") as out:
        for line in src:
            body = line.rstrip("\r\n")
            ending = line[len(body):]
            if body.strip():
                try:
                    body = json.dumps(_redact_value(json.loads(body)), ensure_ascii=False)
                except ValueError:
                    body = redact_text(body)
            out.write(body + ending)


def _text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def memory(actor):
    """[(source, text)]: what the session's harness remembers about that session only (see the module docstring)."""
    found = []
    if not actor.startswith("codex:"):
        return found  # Claude Code: project memory, not this session's
    thread = actor.split(":", 1)[1]
    root = codex_home() / "memories"
    summaries = root / "rollout_summaries"
    named = re.compile(r"(?m)^thread_id:\s*%s\s*$" % re.escape(thread))
    for f in sorted(summaries.glob("*.md")) if summaries.is_dir() else []:
        text = _text(f)
        if named.search(text[:3000]):
            found.append(("memories/rollout_summaries/" + f.name, text))
    tasks = []
    for group in re.split(r"(?m)^(?=# Task Group:)", _text(root / "MEMORY.md")):
        if not group.startswith("# Task Group:"):
            continue
        sections = re.split(r"(?m)^(?=## )", group)
        cited = [s.strip() for s in sections[1:] if s.startswith("## Task") and "thread_id=" + thread in s]
        if cited:
            tasks.append(group.splitlines()[0] + "\n\n" + "\n\n".join(cited))
    if tasks:
        found.append(("memories/MEMORY.md, tasks whose sources cite this thread", "\n\n".join(tasks)))
    return found


def memory_path(dest):
    dest = Path(dest)
    return dest.with_name(dest.stem + "-memory.md")


def write_memory(actor, dest, title="", redact=False):
    """The session's memory as one Markdown file next to the trajectory (redacted like it)."""
    harness = "codex" if actor.startswith("codex:") else "claude-code"
    parts = memory(actor)
    out = ["# Memory: " + (title or actor), "",
           "- harness: %s" % harness,
           "- what this is: %s" % ("Codex's memory summaries of this thread and the MEMORY.md tasks whose sources cite "
                                   "it; shared sections distilled from several chats are left out" if harness == "codex"
                                   else "nothing: Claude Code keeps memory per project, shared by every session there, "
                                   "so none of it is this session's to give"),
           "- sources: %d" % len(parts), ""]
    if not parts:
        out.append("No memory is recorded for this session.")
    for source, text in parts:
        out += ["## " + source, "", "`````", text.strip(), "`````", ""]
    path = memory_path(dest)
    text = "\n".join(out)
    path.write_text(redact_text(text) if redact else text, encoding="utf-8")
    return path


def export(actor, dest, title="", redact=True, memory=False, verbatim=False):
    """Write the whole trajectory, nothing left out or shortened, to a Markdown file, and copy the harness's own
    transcript files next to it. The requester opens them itself; nothing enters anyone's context.
    The Markdown and every copied transcript (subagent files too) have API keys and passwords masked; the member's own
    transcript files are never touched. Only verbatim=True (the approver asked for redact=false) copies byte for byte:
    redact=False alone still masks, because Relic processes started before 0.10.0 pass it by default.
    With memory, the session's memory goes to <name>-memory.md beside it (write_memory). It is off unless the request
    asked for it: a caller from before 0.10.0 answers requests whose consent never covered memory."""
    import shutil
    redact = redact or not verbatim
    harness, session, path, items = steps(actor, clip=None, full=True)
    if path is None:
        raise FileNotFoundError("No transcript of %s session %s on this machine." % (harness, session))
    if memory:
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        write_memory(actor, dest, title, redact)
    dest = Path(dest)
    raw = dest.with_suffix("")  # folder with the original transcript files
    raw.mkdir(parents=True, exist_ok=True)
    sources = [path] + (claude_subagents(path) if harness == "claude-code" else [])
    for source in sources:
        if redact:
            redact_jsonl(source, raw / source.name)
        else:
            shutil.copyfile(source, raw / source.name)
    subs = sources[1:]
    if redact:  # render from the masked copies, so a field masked by its name is masked in the Markdown too
        items = list((codex_steps if harness == "codex" else claude_steps)(raw / path.name, None, True))
        subs = [raw / s.name for s in subs]
    out = ["# Trajectory: " + (title or session), "",
           "- harness: %s (%s)" % (harness, surface(path, harness)), "- session: %s" % session,
           "- transcript: %s" % path,
           ("- redacted copies of the original files (API keys and passwords masked): %s" if redact
            else "- original files: %s") % raw, "- steps: %d" % len(items), ""]
    _render(items, out)
    for sub in subs:
        sub_items = list(claude_steps(sub, None, True))
        out += ["# Subagent %s (%d steps)" % (sub.stem, len(sub_items)), ""]
        _render(sub_items, out)
    text = "\n".join(out)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(redact_text(text) if redact else text, encoding="utf-8")
    os.replace(tmp, dest)
    return dest
