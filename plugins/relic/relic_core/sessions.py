"""Find the human-facing sessions of both harnesses on this machine, read-only.

Codex (desktop app and CLI) keeps its thread index in ~/.codex/state_*.sqlite; Claude Code (desktop Code tab and
CLI) keeps one transcript per session in ~/.claude/projects/<project>/<session-id>.jsonl. The ids found here are
the same ids the harnesses report to hooks, so binding a seat to one makes that chat a member on its next turn.
ChatGPT chats live in the cloud; while the ChatGPT desktop app runs, its tool pipe lists them (desktop.py), and a
seated one becomes a chat member (chat.py).
"""
import contextlib
import json
import os
import sqlite3
from pathlib import Path

CODEX_SOURCES = ("cli", "vscode", "appServer", "exec", "unknown")
# Where a session ran: Codex threads record a source, Claude Code transcripts an entrypoint.
CODEX_SURFACE = {"cli": "cli", "exec": "cli", "vscode": "gui", "appServer": "gui"}
CLAUDE_SURFACE = {"cli": "cli", "claude-desktop": "gui", "claude-vscode": "gui", "sdk-cli": "cli"}


def actor_for(session):
    prefix = {"codex": "codex:", "chatgpt": "chatgpt:"}.get(session["harness"], "")
    return prefix + session["id"]


def _clean_path(path):
    path = path or ""
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    return path[4:] if path.startswith("\\\\?\\") else path


def _epoch(value):
    if isinstance(value, (int, float)):
        return value / 1000 if value > 1e12 else value
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0


def codex_sessions(home=None, include_archived=False):
    root = Path(home or os.getenv("CODEX_HOME") or Path.home() / ".codex")
    dbs = sorted(root.glob("state_*.sqlite"),
                 key=lambda p: int(p.stem.rsplit("_", 1)[-1]) if p.stem.rsplit("_", 1)[-1].isdigit() else -1,
                 reverse=True)
    if not dbs:
        return []
    with contextlib.closing(sqlite3.connect(dbs[0].resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
        columns = {r[1] for r in db.execute("PRAGMA table_info(threads)")}
        if not {"id", "cwd", "updated_at"} <= columns:
            return []
        wanted = [c for c in ("id", "cwd", "updated_at", "archived", "source", "thread_source", "name", "title",
                              "preview", "first_user_message") if c in columns]
        rows = [dict(zip(wanted, r)) for r in db.execute("SELECT %s FROM threads" % ",".join(wanted))]
    out = []
    for row in rows:
        source = str(row.get("source") or "unknown").strip('"')
        if source not in CODEX_SOURCES or "subagent" in str(row.get("thread_source") or ""):
            continue  # spawned subagents and internal threads are not chats a human picks
        if row.get("archived") and not include_archived:
            continue
        title = next((str(row[k]) for k in ("name", "title", "preview", "first_user_message") if row.get(k)), row["id"])
        out.append({"harness": "codex", "id": row["id"], "title": " ".join(title.split())[:120],
                    "surface": CODEX_SURFACE.get(source, source),
                    "cwd": _clean_path(row.get("cwd")), "updated": _epoch(row.get("updated_at"))})
    return sorted(out, key=lambda s: s["updated"], reverse=True)


def _user_text(entry):
    message = entry.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = " ".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
    if not isinstance(content, str) or entry.get("isMeta"):
        return ""
    text = content.strip()
    # slash-command wrappers and harness notices are not what the person typed
    return "" if not text or text.startswith("<") or text.startswith("Caveat:") else text


def _latest_titles(path, tail=131072):
    """Claude Code appends custom-title (set by the person) and ai-title entries as a session goes; read the newest."""
    found = {}
    try:
        with path.open("rb") as handle:
            handle.seek(max(0, path.stat().st_size - tail))
            lines = handle.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return found
    for line in lines:
        if '"custom-title"' in line or '"ai-title"' in line:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            value = entry.get("customTitle") or entry.get("aiTitle")
            if value:
                found[entry.get("type")] = value
    return found


def claude_sessions(home=None, limit_lines=400):
    root = Path(home or os.getenv("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
    out = []
    for f in root.glob("*/*.jsonl"):
        cwd, title, custom, entry_point = "", "", "", ""
        try:
            with f.open(encoding="utf-8", errors="replace") as handle:
                for n, line in enumerate(handle):
                    if n >= limit_lines and cwd and title:
                        break
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    if entry.get("isSidechain"):
                        continue
                    cwd = cwd or entry.get("cwd", "")
                    entry_point = entry_point or entry.get("entrypoint", "")
                    if entry.get("type") == "custom-title" and entry.get("customTitle"):
                        custom = entry["customTitle"]
                    elif entry.get("type") == "summary" and entry.get("summary") and not title:
                        title = entry["summary"]
                    elif entry.get("type") == "user" and not title:
                        title = _user_text(entry)
        except OSError:
            continue
        named = _latest_titles(f)
        custom = named.get("custom-title") or custom
        title = named.get("ai-title") or title
        if not cwd and not title and not custom:
            continue
        out.append({"harness": "claude-code", "id": f.stem, "title": " ".join((custom or title or f.stem).split())[:120],
                    "surface": CLAUDE_SURFACE.get(entry_point, entry_point or "cli"),
                    "cwd": cwd, "updated": f.stat().st_mtime})
    return sorted(out, key=lambda s: s["updated"], reverse=True)


def chatgpt_sessions(connect=None, caller=None):
    """ChatGPT chats the running ChatGPT desktop app lists; none when the app is not running."""
    from . import desktop
    app = (connect or desktop.connect)()
    calling = (caller or (lambda found: found.find_caller()))(app) if app else None
    if not calling:
        return []
    out = []
    for t in app.threads(calling):
        if t.get("kind") != "chatgpt":
            continue
        title = " ".join(str(t.get("title") or t.get("summary") or t["id"]).split())[:120]
        out.append({"harness": "chatgpt", "id": t["id"], "title": title, "surface": "chat", "cwd": "",
                    "updated": _epoch(t.get("updatedAt") or 0)})
    return out


def all_sessions(codex_home=None, claude_home=None, include_archived=False):
    found, problems = [], []
    for name, read in (("Codex", lambda: codex_sessions(codex_home, include_archived)),
                       ("Claude Code", lambda: claude_sessions(claude_home)),
                       ("ChatGPT", chatgpt_sessions)):
        try:
            found += read()
        except (OSError, sqlite3.Error, RuntimeError) as error:  # desktop.DesktopError is a RuntimeError
            problems.append("%s: %s" % (name, error))
    return sorted(found, key=lambda s: s["updated"], reverse=True), problems
