"""Display names for members: by default what each member is responsible for, in the person's language; the person
can rename any member, and the new name also goes to the member's own session (Claude Code or Codex).

A seat keeps three optional fields: display_name (the person's choice), auto_name with auto_name_for ([role, language]
it was made from). A role already written in the person's language gives its name directly (its first clause); a role
in another language is named by a short Claude call (`claude -p` with a small model, no session saved).
"""
import datetime
import functools
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from relic_core import i18n, runner
from relic_core.store import data_home

CJK = re.compile(r"[㐀-鿿]")
CHAT_HARNESSES = ("chatgpt", "claude-chat")
LANGUAGES = {"zh-tw": "Traditional Chinese", "zh-hk": "Traditional Chinese", "zh": "Simplified Chinese",
             "en": "English", "ja": "Japanese", "ko": "Korean", "fr": "French", "de": "German", "es": "Spanish"}


def language_name(lang):
    lang = (lang or "zh-CN").lower()
    return LANGUAGES.get(lang) or LANGUAGES.get(lang.split("-")[0]) or lang


def from_role(role, member):
    """The name a role gives when it is already in the person's language: its title or first clause."""
    role = " ".join((role or "").split())
    if not role:
        return member
    head = re.split(r"[：:]", role, maxsplit=1)
    if len(head) == 2 and 0 < len(head[0].strip()) <= 12:
        return head[0].strip()
    first = re.split(r"[，,、;；。（(]|\s[-–—]\s|\.\s", role, maxsplit=1)[0].strip(" .")
    limit = 12 if CJK.search(first) else 32
    return first if len(first) <= limit else first[:limit].rstrip() + "…"


def same_language(text, lang):
    return bool(CJK.search(text or "")) == (lang or "zh").lower().startswith(("zh", "ja"))


def display(seat, member, lang=None):
    """What the App calls a member."""
    if seat.get("display_name"):
        return seat["display_name"]
    if seat.get("auto_name"):
        return seat["auto_name"]
    role = seat.get("role") or ""
    if role and (lang is None or same_language(role, lang)):
        return from_role(role, member)
    return member


# ---------------------------------------------------------------- automatic names
PROMPT = """You name the members of a team of AI agents for the contact list of a chat app. Give each member a short
name that says what it is responsible for, written in {language}: 2 to 8 characters for Chinese or Japanese, 1 to 4
words otherwise. No member ids, quotes, emoji or punctuation at the end. Members with the same job get distinct names.
Reply with one JSON object only, mapping each member id to its name.

Team: {org}
Members (id: role):
{members}"""


def ask_claude(org_name, roles, lang, timeout=120, processes=None):
    """{member: name} from one short Claude call; {} when Claude Code is missing or the call fails."""
    exe = runner.find_claude()
    if not exe or not roles:
        return {}
    prompt = PROMPT.format(language=language_name(lang), org=org_name,
                           members="\n".join("%s: %s" % (m, (r or "(no role)")[:300]) for m, r in roles.items()))
    folder = data_home() / "naming"
    folder.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    try:
        run = processes.run if processes is not None else subprocess.run
        done = run([exe, "-p", prompt, "--model", "haiku", "--no-session-persistence", "--setting-sources", "",
                               "--output-format", "text"], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, cwd=str(folder), env=env, stdin=subprocess.DEVNULL,
                              creationflags=runner.NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    match = re.search(r"\{.*\}", done.stdout or "", re.S)
    try:
        names = json.loads(match.group(0)) if match else {}
    except ValueError:
        return {}
    return {m: " ".join(str(n).split())[:24] for m, n in names.items() if m in roles and str(n).strip()}


class Namer:
    """Fills in automatic names for an organization's seats, at most one Claude call at a time per organization."""

    def __init__(self, store, publish=None, ask=ask_claude, processes=None):
        self.store, self.publish = store, publish or (lambda event: None)
        self.ask = functools.partial(ask, processes=processes) if processes is not None and ask is ask_claude else ask
        self.running, self.failed = set(), {}
        self.lock = threading.Lock()

    def ensure(self, org_id, lang):
        org = self.store.get(org_id)
        lang = lang or "zh-CN"
        direct, ask = {}, {}
        for member, seat in (org.get("members") or {}).items():
            role = seat.get("role") or ""
            if seat.get("display_name") or seat.get("auto_name_for") == [role, lang]:
                continue
            name = from_role(role, member)
            if not role or (same_language(role, lang) and not name.endswith("…")):
                direct[member] = (name, role)
            else:  # another language, or too long to cut into a name: one short Claude call names them all
                ask[member] = role
        for member, (name, role) in direct.items():
            self.store.set_seat_fields(org_id, member, auto_name=name, auto_name_for=[role, lang])
        if direct:
            self.publish({"type": "org", "org": org_id})
        key = (org_id, lang)
        with self.lock:
            if not ask or key in self.running or time.time() - self.failed.get(key, 0) < 600:
                return bool(ask)
            self.running.add(key)
        threading.Thread(target=self._ask, args=(org_id, org["name"], ask, lang, key), daemon=True).start()
        return True

    def _ask(self, org_id, org_name, roles, lang, key):
        try:
            names = self.ask(org_name, roles, lang)
            for member, role in roles.items():
                if member in names:
                    self.store.set_seat_fields(org_id, member, auto_name=names[member], auto_name_for=[role, lang])
            if len(names) < len(roles):
                self.failed[key] = time.time()
            if names:
                self.publish({"type": "org", "org": org_id})
        except Exception:
            self.failed[key] = time.time()
        finally:
            with self.lock:
                self.running.discard(key)


# ---------------------------------------------------------------- the name in the member's own app
def rename_session(seat, name, locate, lang=None):
    """Give the member's session the new name where its harness keeps session names. Returns (renamed, note)."""
    carrier = seat.get("carrier") or ""
    if not carrier:
        return False, i18n.t("naming.vacant", lang)
    if seat.get("harness") in CHAT_HARNESSES or (carrier.split(":", 1)[0] in CHAT_HARNESSES and ":" in carrier):
        return False, i18n.t("naming.chat", lang)
    if carrier.startswith("codex:"):
        thread = carrier.split(":", 1)[1].split("/")[-1]
        return rename_codex(thread, name, lang)
    session, _, agent = carrier.partition("/")
    if agent:
        return False, i18n.t("naming.subagent", lang)
    return rename_claude(session, name, locate, lang)


def rename_claude(session, name, locate, lang=None):
    """Claude Code keeps a session's name as a custom-title entry in its transcript (what /rename writes)."""
    path = locate(session)
    if not path:
        return False, i18n.t("naming.no_claude_record", lang)
    from .views import long_path
    line = json.dumps({"type": "custom-title", "customTitle": name, "sessionId": session}, ensure_ascii=False)
    with open(long_path(path), "a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n" + line + "\n" if not _ends_with_newline(path) else line + "\n")
    return True, i18n.t("naming.claude_renamed", lang)


def _ends_with_newline(path):
    from .views import long_path
    try:
        with open(long_path(path), "rb") as handle:
            handle.seek(-1, os.SEEK_END)
            return handle.read(1) == b"\n"
    except OSError:
        return True


def rename_codex(thread, name, lang=None):
    """Codex names a thread through its app-server (thread/name/set); session_index.jsonl is the fallback."""
    exe = runner.find_codex()
    if exe:
        try:
            with runner.CodexAppServer(exe, cwd=str(Path.home())) as server:
                server.request("thread/name/set", {"threadId": thread, "name": name})
            return True, i18n.t("naming.codex_renamed", lang)
        except Exception:
            pass
    index = Path(os.getenv("CODEX_HOME") or Path.home() / ".codex") / "session_index.jsonl"
    if not index.parent.is_dir():
        return False, i18n.t("naming.no_codex_data", lang)
    at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    with open(index, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"id": thread, "thread_name": name, "updated_at": at}, ensure_ascii=False) + "\n")
    return True, i18n.t("naming.codex_renamed", lang)
