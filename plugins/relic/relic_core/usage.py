"""Token use over time, per session, counted from the sessions' own transcripts on this computer.

Claude Code writes each assistant message's usage into the session's transcript, once per content block, so a message
counts once by its id; subagents write their own files and count with their session. Codex writes token_count events
into its rollout files, with the plan's rate limits. The Relic App reads each file once, from where the last read
stopped, and keeps only sums in usage.sqlite3 in the Relic data folder: per minute for the last two days (the live
monitor) and per hour for 400 days (the charts). Never transcript text: a row per active session-minute or -hour.
"""
import collections
import contextlib
import json
import os
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

from .store import data_home

DAY = 24 * 3600
MINUTES_KEPT = 2 * DAY
HOURS_KEPT = 400 * DAY
BACKFILL = 30 * DAY     # how far back the first read goes
CODEX_FOLDERS = 90      # a resumed Codex session keeps writing to the rollout folder of the day it started
CHUNK = 4 * 1024 * 1024
RECENT = 64
SCHEMA = """
CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, session TEXT NOT NULL, kind TEXT NOT NULL,
  sub INTEGER NOT NULL DEFAULT 0, offset INTEGER NOT NULL DEFAULT 0, mtime REAL NOT NULL DEFAULT 0,
  recent TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS minutes(session TEXT NOT NULL, minute INTEGER NOT NULL, kind TEXT NOT NULL,
  fresh INTEGER NOT NULL DEFAULT 0, cache_read INTEGER NOT NULL DEFAULT 0, cache_write INTEGER NOT NULL DEFAULT 0,
  output INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(session, minute));
CREATE TABLE IF NOT EXISTS hours(session TEXT NOT NULL, hour INTEGER NOT NULL, kind TEXT NOT NULL,
  fresh INTEGER NOT NULL DEFAULT 0, cache_read INTEGER NOT NULL DEFAULT 0, cache_write INTEGER NOT NULL DEFAULT 0,
  output INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(session, hour));
CREATE TABLE IF NOT EXISTS sessions(session TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT, cwd TEXT,
  last_at REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
_UUID = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$")


def claude_root():
    return Path(os.getenv("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def codex_root():
    return Path(os.getenv("CODEX_HOME") or Path.home() / ".codex")


def db_path():
    return data_home() / "usage.sqlite3"


def _epoch(text):
    if not isinstance(text, str) or not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _entries(folder, suffix=None, dirs=False):
    try:
        with os.scandir(folder) as found:
            for entry in found:
                try:
                    if dirs and entry.is_dir():
                        yield entry
                    elif not dirs and entry.is_file() and (suffix is None or entry.name.endswith(suffix)):
                        yield entry
                except OSError:
                    continue
    except OSError:
        return


def transcripts(now, since):
    """[(path, kind, session, mtime, subagent)] of transcripts changed since `since`."""
    found = []
    for project in _entries(claude_root() / "projects", dirs=True):
        for entry in _entries(project.path, ".jsonl"):
            mtime = entry.stat().st_mtime
            if mtime >= since:
                found.append((Path(entry.path), "claude", entry.name[:-6], mtime, False))
        for session in _entries(project.path, dirs=True):
            for entry in _entries(os.path.join(session.path, "subagents"), ".jsonl"):
                mtime = entry.stat().st_mtime
                if mtime >= since:
                    found.append((Path(entry.path), "claude", session.name, mtime, True))
    root = codex_root() / "sessions"
    for back in range(CODEX_FOLDERS):
        day = time.localtime(now - back * DAY)
        folder = root / ("%04d" % day.tm_year) / ("%02d" % day.tm_mon) / ("%02d" % day.tm_mday)
        for entry in _entries(folder, ".jsonl"):
            match = _UUID.search(entry.name)
            mtime = entry.stat().st_mtime
            if match and entry.name.startswith("rollout-") and mtime >= since:
                found.append((Path(entry.path), "codex", "codex:" + match.group(1), mtime, False))
    return found


def _claude(record, recent, limits):
    if record.get("type") != "assistant":
        return None
    message = record.get("message") or {}
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    key = message.get("id") or record.get("requestId")
    if key:
        if key in recent:
            return None
        recent.append(key)
    return (_epoch(record.get("timestamp")), int(usage.get("input_tokens") or 0),
            int(usage.get("cache_read_input_tokens") or 0), int(usage.get("cache_creation_input_tokens") or 0),
            int(usage.get("output_tokens") or 0))


def _codex(record, recent, limits):
    payload = record.get("payload") or {}
    if payload.get("type") != "token_count":
        return None
    at = _epoch(record.get("timestamp"))
    if isinstance(payload.get("rate_limits"), dict) and at and at >= limits.get("at", 0):
        limits.update(at=at, value=payload["rate_limits"])
    info = payload.get("info") or {}
    last = info.get("last_token_usage") or {}
    total = (info.get("total_token_usage") or {}).get("total_tokens")
    if not last or (total is not None and total in recent):  # the same count reported again
        return None
    if total is not None:
        recent.append(total)
    sent, cached = int(last.get("input_tokens") or 0), int(last.get("cached_input_tokens") or 0)
    return at, max(sent - cached, 0), cached, 0, int(last.get("output_tokens") or 0)


class Ledger:
    """usage.sqlite3 and the scan that keeps it current. One per process: Ledger.shared()."""
    _shared = None
    _shared_lock = threading.Lock()

    @classmethod
    def shared(cls):
        with cls._shared_lock:
            if cls._shared is None or cls._shared.path != db_path():
                cls._shared = cls()
            return cls._shared

    def __init__(self, path=None):
        self.path = Path(path or db_path())
        self.lock = threading.Lock()
        self.limits = {"at": 0.0, "value": None}
        self.scanned_at = 0.0
        self.scanning = False

    @contextlib.contextmanager
    def db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(self.path), timeout=30)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            yield db
        finally:
            db.close()

    # ---------------- reading the transcripts ----------------
    def scan(self, now=None, blocking=True, fresh_for=0.0):
        """Read what changed. Returns False when another scan is running (blocking=False) or the last one is fresh."""
        if fresh_for and time.time() - self.scanned_at < fresh_for:
            return False
        if not self.lock.acquire(blocking=blocking):
            return False
        try:
            self.scanning = True
            now = time.time() if now is None else now
            with self.db() as db:
                known = {row[0]: row for row in db.execute("SELECT path, offset, mtime, recent FROM files")}
                if self.limits["value"] is None:
                    row = db.execute("SELECT value FROM meta WHERE key='codex_limits'").fetchone()
                    if row:
                        self.limits.update(json.loads(row[0]))
                for path, kind, session, mtime, sub in transcripts(now, now - BACKFILL):
                    row = known.get(str(path))
                    if row and row[2] == mtime:
                        continue
                    self._read(db, path, kind, session, row, mtime, sub, now)
                db.execute("DELETE FROM minutes WHERE minute < ?", (int((now - MINUTES_KEPT) // 60),))
                db.execute("DELETE FROM hours WHERE hour < ?", (int((now - HOURS_KEPT) // 3600),))
                db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('codex_limits', ?)", (json.dumps(self.limits),))
                db.commit()
            self.scanned_at = time.time()
            return True
        finally:
            self.scanning = False
            self.lock.release()

    def _read(self, db, path, kind, session, row, mtime, sub, now):
        start = row[1] if row else 0
        recent = collections.deque(json.loads(row[3]) if row else [], maxlen=RECENT)
        try:
            size = path.stat().st_size
        except OSError:
            return
        if size < start:  # rewritten: start over
            start, recent = 0, collections.deque(maxlen=RECENT)
        marker, parse = (b'"usage"', _claude) if kind == "claude" else (b'"token_count"', _codex)
        minutes, hours = {}, {}
        first, read, rest = None, 0, b""
        floor = now - MINUTES_KEPT
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
                    if end < 0:
                        rest = data
                        continue
                    lines, rest = data[:end].split(b"\n"), data[end + 1:]
                    if start == 0 and first is None and lines:
                        try:
                            first = json.loads(lines[0])
                        except ValueError:
                            first = {}
                    for line in lines:
                        if marker not in line:
                            continue
                        try:
                            found = parse(json.loads(line), recent, self.limits)
                        except (ValueError, TypeError, AttributeError):
                            continue
                        if not found or found[0] is None:
                            continue
                        at, counts = found[0], found[1:]
                        cell = hours.setdefault(int(at // 3600), [0, 0, 0, 0])
                        for i in range(4):
                            cell[i] += counts[i]
                        if at >= floor:
                            cell = minutes.setdefault(int(at // 60), [0, 0, 0, 0])
                            for i in range(4):
                                cell[i] += counts[i]
        except OSError:
            return
        offset = start + read - len(rest)
        add = ("INSERT INTO %s(session, %s, kind, fresh, cache_read, cache_write, output) VALUES(?,?,?,?,?,?,?) "
               "ON CONFLICT(session, %s) DO UPDATE SET fresh=fresh+excluded.fresh, cache_read=cache_read+excluded.cache_read, "
               "cache_write=cache_write+excluded.cache_write, output=output+excluded.output")
        db.executemany(add % ("minutes", "minute", "minute"), [(session, m, kind, *c) for m, c in minutes.items()])
        db.executemany(add % ("hours", "hour", "hour"), [(session, h, kind, *c) for h, c in hours.items()])
        db.execute("INSERT OR REPLACE INTO files(path, session, kind, sub, offset, mtime, recent) VALUES(?,?,?,?,?,?,?)",
                   (str(path), session, kind, int(sub), offset, mtime, json.dumps(list(recent))))
        title, cwd = None, None
        if kind == "claude" and not sub:
            try:
                title = json.loads((path.parent / session / "custom-title.json").read_text(encoding="utf-8")).get("customTitle")
            except (OSError, ValueError, AttributeError):
                title = None
        if kind == "codex" and isinstance(first, dict):
            cwd = (first.get("payload") or {}).get("cwd")
        db.execute("INSERT INTO sessions(session, kind, title, cwd, last_at) VALUES(?,?,?,?,?) ON CONFLICT(session) DO UPDATE "
                   "SET title=COALESCE(excluded.title, title), cwd=COALESCE(excluded.cwd, cwd), last_at=MAX(last_at, excluded.last_at)",
                   (session, kind, title, cwd, mtime))
        db.commit()

    # ---------------- reading the sums ----------------
    def sessions(self, now=None, active=150):
        """{session: {"kind", "title", "cwd", "last_at", "subagents"}}: subagents = subagent files changed within `active` s."""
        now = time.time() if now is None else now
        with self.db() as db:
            found = {s: {"kind": k, "title": t, "cwd": c, "last_at": a, "subagents": 0}
                     for s, k, t, c, a in db.execute("SELECT session, kind, title, cwd, last_at FROM sessions")}
            for session, count in db.execute("SELECT session, COUNT(*) FROM files WHERE sub=1 AND mtime>=? GROUP BY session",
                                             (now - active,)):
                if session in found:
                    found[session]["subagents"] = count
        return found

    def windows(self, now=None, spans=None, rate_span=600):
        """{session: {"spans": {name: [fresh, read, write, out]}, "rate": tokens per minute over the last rate_span s}}."""
        now = time.time() if now is None else now
        spans = spans or {"hour": 3600, "five_hours": 5 * 3600, "day": DAY}
        longest = max(spans.values())
        found = {}
        with self.db() as db:
            rows = db.execute("SELECT session, minute, fresh, cache_read, cache_write, output FROM minutes WHERE minute>=?",
                              (int((now - longest) // 60),)).fetchall()
        for session, minute, *counts in rows:
            entry = found.setdefault(session, {"spans": {name: [0, 0, 0, 0] for name in spans}, "rate": 0})
            age = now - minute * 60
            for name, span in spans.items():
                if age <= span:
                    cell = entry["spans"][name]
                    for i in range(4):
                        cell[i] += counts[i]
            if age <= rate_span:
                entry["rate"] += sum(counts)
        for entry in found.values():
            entry["rate"] = round(entry["rate"] * 60 / rate_span)
        return found

    def hours(self, since, until):
        """[(session, kind, hour, fresh, read, write, out)] for hours that start in [since, until)."""
        with self.db() as db:
            return db.execute("SELECT session, kind, hour, fresh, cache_read, cache_write, output FROM hours "
                              "WHERE hour>=? AND hour<?", (int(since // 3600), int(-(-until // 3600)))).fetchall()
