"""Plain-language explanations of what the agents say to each other, for the person: each message rewritten so that
someone outside the work can follow it (who tells whom what, why, what happens next), and a short digest of what the
group has been doing. One Claude call (`claude -p`, no session saved) handles a batch; results are kept in
~/.relic/app/plain/<org>.json, so each message is explained once."""
import json
import functools
import os
import re
import subprocess
import threading
import time

from relic_core import runner
from relic_core.store import data_home

from . import naming, views

MODEL = "sonnet"

PLAIN = """You explain the internal messages of a team of AI agents to the person who owns the team. The person finds
them hard to follow: they do not know the context, the jargon, the file names or what each agent is doing.
For each message under "Explain these", write a plain version in {language}, 1 to 3 short sentences: who tells whom
what, why it matters, and what happens next. Turn ids, file names and jargon into what they mean when the context
shows it; keep numbers that matter; never invent facts; if a message only acknowledges something, say so in a few words.
Reply with one JSON object only, mapping each message id (as a string) to its plain version.

Team: {org} ({purpose})
Members (id, name, role):
{members}

Earlier messages, for context (oldest first):
{context}

Explain these:
{targets}"""

DIGEST = """Summarize for the person who owns this team of AI agents, in {language}, what the team has been doing in
the messages below. Plain words, no jargon, at most about {limit} characters, Markdown allowed:
- **现在在做什么** (what they are working on now, who does what)
- **最近的结果** (what was finished or decided)
- **需要你注意** (only if something needs the person: a decision, a problem, a question)
Translate the bold headings into {language} if it is not Chinese. Never invent facts.

Team: {org} ({purpose})
Members (id, name, role):
{members}

Messages (oldest first):
{messages}"""


def _path(org_id):
    return data_home() / "app" / "plain" / ("%s.json" % org_id)


def load(org_id):
    try:
        return json.loads(_path(org_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"items": {}, "digest": None}


def _save(org_id, data):
    path = _path(org_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def ask(prompt, model=MODEL, timeout=240, processes=None):
    exe = runner.find_claude()
    if not exe:
        raise RuntimeError("Claude Code was not found on this computer.")
    folder = data_home() / "naming"
    folder.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    run = processes.run if processes is not None else subprocess.run
    done = run([exe, "-p", prompt, "--model", model, "--no-session-persistence", "--setting-sources", "",
                           "--output-format", "text"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, cwd=str(folder), env=env, stdin=subprocess.DEVNULL, creationflags=runner.NO_WINDOW)
    if done.returncode != 0 and not (done.stdout or "").strip():
        raise RuntimeError((done.stderr or "claude -p failed").strip()[-300:])
    return done.stdout or ""


def _members(org, lang):
    return "\n".join("%s, %s: %s" % (name, naming.display(seat, name, lang), (seat.get("role") or "")[:160])
                     for name, seat in (org.get("members") or {}).items())


def _line(m, limit):
    body = re.sub(r"\s+", " ", m["body"] or "").strip()
    return "[#%s %s -> %s] %s" % (m["id"], m["from"], ",".join(m["to"]), body[:limit])


DEFAULT_ASK = ask


class Explainer:
    """At most one Claude call at a time per organization; ids asked for meanwhile join the next batch."""

    def __init__(self, store, publish=None, ask=ask, processes=None):
        self.store, self.publish = store, publish or (lambda event: None)
        self.ask = functools.partial(ask, processes=processes) if processes is not None and ask is DEFAULT_ASK else ask
        self.lock = threading.Lock()
        self.wanted, self.running, self.digesting = {}, set(), set()

    def plain(self, org_id, ids, lang):
        data = load(org_id)
        have = {i: v["text"] for i, v in (data.get("items") or {}).items() if v.get("lang") == lang}
        out = {str(i): have[str(i)] for i in ids if str(i) in have}
        missing = [int(i) for i in ids if str(i) not in have]
        if missing:
            with self.lock:
                self.wanted.setdefault((org_id, lang), set()).update(missing)
                start = (org_id, lang) not in self.running
                if start:
                    self.running.add((org_id, lang))
            if start:
                threading.Thread(target=self._run, args=(org_id, lang), daemon=True).start()
        return {"items": out, "pending": missing}

    def _messages(self, org_id, ids=None, last=None):
        cols = views._columns(self.store)
        if ids:
            rows = views._rows(self.store, "SELECT %s FROM messages WHERE org_id=? AND id IN (%s) ORDER BY id"
                               % (cols, ",".join("?" * len(ids))), [org_id] + list(ids))
        else:
            rows = list(reversed(views._rows(self.store, "SELECT %s FROM messages WHERE org_id=? ORDER BY id DESC LIMIT ?"
                                             % cols, (org_id, last or 40))))
        return [views._message(r) for r in rows]

    def _run(self, org_id, lang):
        try:
            while True:
                with self.lock:
                    batch = sorted(self.wanted.get((org_id, lang)) or [])[:24]
                    if not batch:
                        self.running.discard((org_id, lang))
                        return
                    self.wanted[(org_id, lang)].difference_update(batch)
                org = self.store.get(org_id)
                targets = self._messages(org_id, batch)
                first = min(batch)
                context = list(reversed(views._rows(self.store, "SELECT %s FROM messages WHERE org_id=? AND id<? ORDER BY id DESC "
                                                    "LIMIT 12" % views._columns(self.store), (org_id, first))))
                prompt = PLAIN.format(language=naming.language_name(lang), org=org["name"], purpose=(org.get("purpose") or "")[:400],
                                      members=_members(org, lang),
                                      context="\n".join(_line(views._message(r), 300) for r in context) or "(none)",
                                      targets="\n\n".join(_line(m, 3000) for m in targets))
                try:
                    reply = self.ask(prompt)
                    match = re.search(r"\{.*\}", reply, re.S)
                    found = json.loads(match.group(0)) if match else {}
                except Exception as error:
                    self.publish({"type": "plain", "org": org_id, "error": str(error)[:300], "ids": batch})
                    continue
                got = {}
                for key, text in (found.items() if isinstance(found, dict) else []):
                    key = str(key).lstrip("#")
                    if key.isdigit() and int(key) in batch and str(text).strip():
                        got[key] = str(text).strip()
                if got:
                    data = load(org_id)
                    items = data.setdefault("items", {})
                    for key, text in got.items():
                        items[key] = {"text": text, "lang": lang, "at": time.time()}
                    _save(org_id, data)
                # every id of the batch is reported: one without a text was skipped by the model
                self.publish({"type": "plain", "org": org_id, "items": got, "ids": batch})
        except Exception:
            with self.lock:
                self.running.discard((org_id, lang))

    def digest(self, org_id, lang, refresh=False, last=40):
        """The kept digest, or a new one. Without `refresh` a kept digest is returned as it is (the page shows how many
        messages came after it); with `refresh` a new one is made only when there are newer messages."""
        data = load(org_id)
        top = (views._rows(self.store, "SELECT MAX(id) FROM messages WHERE org_id=?", (org_id,))[0][0]) or 0
        current = data.get("digest")
        if current and current.get("lang") != lang:
            current = None
        if current and (not refresh or current.get("last_id") == top):
            return {"digest": current, "pending": org_id in self.digesting}
        with self.lock:
            start = org_id not in self.digesting
            self.digesting.add(org_id)
        if start:
            threading.Thread(target=self._digest, args=(org_id, lang, last, top), daemon=True).start()
        return {"digest": current, "pending": True}

    def _digest(self, org_id, lang, last, top):
        try:
            org = self.store.get(org_id)
            messages = self._messages(org_id, last=last)
            prompt = DIGEST.format(language=naming.language_name(lang), limit=500, org=org["name"],
                                   purpose=(org.get("purpose") or "")[:400], members=_members(org, lang),
                                   messages="\n".join(_line(m, 900) for m in messages) or "(no messages)")
            text = self.ask(prompt).strip()
            data = load(org_id)
            data["digest"] = {"text": text, "lang": lang, "last_id": top, "at": time.time(), "count": len(messages)}
            _save(org_id, data)
            self.publish({"type": "digest", "org": org_id, "digest": data["digest"]})
        except Exception as error:
            self.publish({"type": "digest", "org": org_id, "error": str(error)[:300]})
        finally:
            with self.lock:
                self.digesting.discard(org_id)
