"""The person's Slack, read-only, as background for the members' work.

The person creates an internal Slack app in their own workspace from MANIFEST (read scopes only: no bot user, nothing
that posts), installs it, and pastes its User OAuth Token (xoxp-...) into the Relic App (Settings, Slack). Relic keeps
the token encrypted for this Windows user (DPAPI; on other systems in a file only this user can read), never shows it
again, and calls the Slack Web API in real time when a member asks. No message is kept: Slack's API terms forbid
indexes and long-term copies of workspace data for apps offered to others, and one person's own app does not need
them either.

What an organization may read is the person's choice, kept in slack.json: every channel the person can see, with or
without direct messages, a list of conversations, or nothing. An organization without its own choice follows the
nearest organization above it, then the default, which lets every organization read every channel and direct message
until the person narrows it. Every read is logged with the seat that made it, what it asked for and how many messages
came back (slack.sqlite3, 90 days), never the messages themselves.

An internal app keeps Slack's higher rate limits (conversations.history and .replies: 50+ calls a minute, up to 1,000
messages a page). Search uses the Real-Time Search API (assistant.search.context: at most 20 results a call, about 10
calls a minute per user) and falls back to the legacy search.messages for a token that only has search:read.
"""
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from .store import OrgError, data_home

API = "https://slack.com/api/"
TIMEOUT = 20  # seconds for one Slack call
USER_SCOPES = ("channels:history", "groups:history", "im:history", "mpim:history",
               "channels:read", "groups:read", "im:read", "mpim:read", "users:read", "team:read",
               "search:read.public", "search:read.private", "search:read.im", "search:read.mpim",
               "search:read.files", "search:read.users")
MANIFEST = {
    "display_information": {"name": "Relic Reader",
                            "description": "Lets the members of your Relic organizations read your Slack. Read-only."},
    "oauth_config": {"scopes": {"user": list(USER_SCOPES)}},
    "settings": {"org_deploy_enabled": False, "socket_mode_enabled": False, "token_rotation_enabled": False},
}
CREATE_URL = "https://api.slack.com/apps?new_app=1"
OPS = ("search", "history", "thread", "channels")
MODES = ("all", "list", "none")
DEFAULT = {"mode": "all", "dms": True}
LOG_DAYS = 90
TTL = 3600  # seconds a user's name or a conversation's details stay cached in this process
LIST_TTL = 600  # seconds the person's conversation list stays cached
SEARCH_LIMIT = 20  # assistant.search.context returns at most 20 results a call
HISTORY_LIMIT = 200
TEXT_LIMIT = 1500  # characters of one message shown to a member
OUTPUT_LIMIT = 30000  # characters of one answer; a member narrows it with limit, oldest and latest
LEGACY_FALLBACK = {"missing_scope", "not_allowed_token_type", "unknown_method", "feature_not_enabled",
                   "assistant_search_context_disabled"}
BROKEN_TOKEN = {"invalid_auth", "not_authed", "token_revoked", "token_expired", "account_inactive"}
NOISE = {"channel_join", "channel_leave", "group_join", "group_leave"}
CHANNEL_ID = re.compile(r"^[CDG][A-Z0-9]{6,}$")
SLACK_TS = re.compile(r"^\d{9,11}(\.\d{1,6})?$")
ENTROPY = b"relic-slack-token"

_LOCK = threading.Lock()
_CACHE = {}  # (kind, key) -> (value, cached at)


class SlackError(OrgError):
    """A Slack Web API error, by Slack's own code (missing_scope, channel_not_found, ratelimited, ...)."""

    def __init__(self, code, method=""):
        self.code, self.method = code, method
        super().__init__(("Slack %s: %s" % (method, code)) if method else ("Slack: " + code))


# ---------------- the token ----------------

def token_path():
    return data_home() / "slack.token"


def _dpapi(data, protect):
    """Windows DPAPI for this Windows user: only the same user on the same computer can decrypt it."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(raw):
        buffer = ctypes.create_string_buffer(raw, len(raw))
        return Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer

    crypt32, kernel32 = ctypes.WinDLL("crypt32", use_last_error=True), ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source, keep = blob(data)
    entropy, keep_entropy = blob(ENTROPY)
    out = Blob()
    if not function(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 0x1, ctypes.byref(out)):
        raise OSError(ctypes.get_last_error(), "DPAPI failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def save_token(token):
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = token.encode("utf-8")
    body = (b"RELIC-DPAPI1\n" + _dpapi(raw, True)) if os.name == "nt" else (b"RELIC-PLAIN1\n" + raw)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(body)
    os.replace(tmp, path)


def load_token():
    try:
        body = token_path().read_bytes()
    except OSError:
        return None
    head, _, rest = body.partition(b"\n")
    try:
        if head == b"RELIC-DPAPI1" and os.name == "nt":
            return _dpapi(rest, False).decode("utf-8")
        if head == b"RELIC-PLAIN1":
            return rest.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return None


def forget_token():
    try:
        token_path().unlink()
    except FileNotFoundError:
        pass


# ---------------- the person's choices ----------------

def config_path():
    return data_home() / "slack.json"


def load_config():
    try:
        value = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def save_config(value):
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def connected(config=None):
    config = load_config() if config is None else config
    return bool(config.get("team")) and token_path().exists()


def _entry(value):
    if not isinstance(value, dict) or value.get("mode") not in MODES:
        return None
    entry = {"mode": value["mode"], "dms": bool(value.get("dms"))}
    if value["mode"] == "list":
        entry["conversations"] = [c for c in value.get("conversations") or [] if CHANNEL_ID.match(str(c))]
    return entry


def org_scope(store, org, config=None):
    """What org may read: its own choice, else the nearest organization above with one, else the default."""
    config = load_config() if config is None else config
    own = config.get("orgs") or {}
    for place in [org] + store.ancestors(org):
        entry = _entry(own.get(place["id"]))
        if entry:
            return dict(entry, source=place["id"])
    return dict(_entry(config.get("default")) or DEFAULT, source="default")


def allowed(scope, conversation):
    mode = scope.get("mode")
    if mode == "list":
        return conversation["id"] in (scope.get("conversations") or [])
    if mode == "all":
        return conversation["kind"] in ("public", "private") or bool(scope.get("dms"))
    return False


def channel_types(scope):
    if scope.get("mode") == "list" or scope.get("dms"):
        return "public_channel,private_channel,mpim,im"
    return "public_channel,private_channel"


def describe(scope):
    if scope.get("mode") == "list":
        return "%d chosen conversations" % len(scope.get("conversations") or [])
    if scope.get("mode") == "all":
        return "every channel and direct message the person can see" if scope.get("dms") else \
            "every channel the person can see, no direct messages"
    return "nothing"


# ---------------- calling Slack ----------------

def base():
    return os.getenv("RELIC_SLACK_API") or API


def call_api(method, params=None, token=None, retry=True):
    """One Slack Web API call (form-encoded POST). Returns (body, headers); raises SlackError when ok is false."""
    token = token or load_token()
    if not token:
        raise SlackError("not_connected")
    form = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    request = urllib.request.Request(base() + method, data=urllib.parse.urlencode(form).encode("utf-8"), method="POST",
                                     headers={"Authorization": "Bearer " + token, "User-Agent": "Relic",
                                              "Content-Type": "application/x-www-form-urlencoded; charset=utf-8"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as reply:
            body = json.loads(reply.read().decode("utf-8") or "{}")
            headers = reply.headers
    except urllib.error.HTTPError as error:
        with error:
            wait = str(error.headers.get("Retry-After") or "")
        if error.code == 429 and retry and wait.isdigit() and int(wait) <= 30:
            time.sleep(int(wait))
            return call_api(method, params, token, retry=False)
        raise SlackError("ratelimited" if error.code == 429 else "http_%d" % error.code, method)
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise SlackError("network (%s)" % getattr(error, "reason", error), method)
    if not isinstance(body, dict) or not body.get("ok"):
        raise SlackError(str((body or {}).get("error") or "unknown_error") if isinstance(body, dict) else "bad_reply",
                         method)
    return body, headers


def _fp(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def _cached(kind, key, ttl, make):
    now = time.time()
    with _LOCK:
        hit = _CACHE.get((kind, key))
    if hit and now - hit[1] < ttl:
        return hit[0]
    value = make()
    with _LOCK:
        _CACHE[(kind, key)] = (value, now)
    return value


def clear_cache():
    with _LOCK:
        _CACHE.clear()


def _person(member):
    profile = member.get("profile") or {}
    return {"name": profile.get("display_name") or profile.get("real_name") or member.get("real_name")
            or member.get("name") or member.get("id") or "?",
            "handle": member.get("name") or "", "real": profile.get("real_name") or member.get("real_name") or ""}


def user(token, uid):
    if not uid:
        return {"name": "?", "handle": "", "real": ""}

    def make():
        try:
            body, _ = call_api("users.info", {"user": uid}, token)
        except SlackError:
            return {"name": uid, "handle": "", "real": ""}
        return _person(body.get("user") or {})
    return _cached("user", _fp(token) + uid, TTL, make)


def user_name(token, uid):
    return user(token, uid)["name"]


def warm_users(token, ids):
    """Fill the name cache with one users.list walk when many names are unknown (a call per name otherwise)."""
    fp = _fp(token)
    with _LOCK:
        missing = {i for i in ids if i and ("user", fp + i) not in _CACHE}
    if len(missing) <= 15:
        return
    cursor, pages, now = None, 0, time.time()
    while pages < 10:
        try:
            body, _ = call_api("users.list", {"limit": 200, "cursor": cursor}, token)
        except SlackError:
            return
        with _LOCK:
            for member in body.get("members") or []:
                if member.get("id"):
                    _CACHE[("user", fp + member["id"])] = (_person(member), now)
        cursor, pages = (body.get("response_metadata") or {}).get("next_cursor"), pages + 1
        if not cursor:
            return


def _kind(info):
    if info.get("is_im"):
        return "im"
    if info.get("is_mpim"):
        return "mpim"
    if info.get("is_private") or info.get("is_group"):
        return "private"
    return "public"


def _mpim_label(name):
    core = re.sub(r"-\d+$", "", re.sub(r"^mpdm-", "", name or ""))
    return ", ".join("@" + part for part in core.split("--") if part) or name


def _conversation(token, raw):
    kind = _kind(raw)
    if kind == "im":
        label = "@" + user_name(token, raw.get("user"))
    elif kind == "mpim":
        label = _mpim_label(raw.get("name") or raw.get("id"))
    else:
        label = "#" + (raw.get("name") or raw.get("id"))
    return {"id": raw.get("id"), "kind": kind, "label": label, "name": raw.get("name") or "", "user": raw.get("user") or ""}


def conversation(token, cid):
    def make():
        body, _ = call_api("conversations.info", {"channel": cid}, token)
        return _conversation(token, body.get("channel") or {"id": cid})
    return _cached("conversation", _fp(token) + cid, TTL, make)


def _walk(token, method, params, key, pages):
    found, cursor = [], None
    for _ in range(pages):
        body, _ = call_api(method, dict(params, cursor=cursor), token)
        found.extend(body.get(key) or [])
        cursor = (body.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break
    return found


def member_conversations(token):
    """Every conversation the person is in: channels, private channels, group and direct messages (not archived)."""
    def make():
        raw = _walk(token, "users.conversations", {"types": "public_channel,private_channel,mpim,im",
                                                   "exclude_archived": "true", "limit": 200}, "channels", 20)
        warm_users(token, [c.get("user") for c in raw if c.get("is_im")])
        return [_conversation(token, c) for c in raw if c.get("id")]
    return _cached("mine", _fp(token), LIST_TTL, make)


def public_channels(token):
    def make():
        raw = _walk(token, "conversations.list", {"types": "public_channel", "exclude_archived": "true", "limit": 200},
                    "channels", 15)
        return [_conversation(token, c) for c in raw if c.get("id")]
    return _cached("public", _fp(token), LIST_TTL, make)


def resolve(token, channel):
    """A conversation by id (C0123...), #name, or @person for a direct message."""
    text = (channel or "").strip()
    if not text:
        raise OrgError("channel is required: an id like C0123ABCD, #name, or @person for a direct message.")
    link = re.match(r"^<#([CDG][A-Z0-9]+)(?:\|[^>]*)?>$", text)
    if link:
        text = link.group(1)
    if CHANNEL_ID.match(text):
        return conversation(token, text)
    name = text.lstrip("#@").strip().lower()
    mine = member_conversations(token)
    if text.startswith("@"):
        for c in mine:
            if c["kind"] == "im":
                who = user(token, c["user"])
                if name in {who["name"].lower(), who["handle"].lower(), who["real"].lower()}:
                    return c
        for c in mine:
            if c["kind"] == "mpim" and c["label"].lower() == "@" + name:
                return c
        raise OrgError("The person has no direct message with %s." % text)
    for c in mine:
        if c["kind"] in ("public", "private") and c["name"].lower() == name:
            return c
    for c in public_channels(token):
        if c["name"].lower() == name:
            return c
    raise OrgError("No channel named %s that the person can see." % text)


def _check(scope, conv, org):
    if not allowed(scope, conv):
        raise OrgError("The person has not let %s read %s (Relic App: Settings, Slack)." % (org["name"], conv["label"]))


# ---------------- what members read ----------------

MENTION = re.compile(r"<@([UW][A-Z0-9]+)(?:\|([^>]*))?>")
CHANNEL = re.compile(r"<#([CDG][A-Z0-9]+)(?:\|([^>]*))?>")
SPECIAL = re.compile(r"<!(here|channel|everyone)(?:\|[^>]*)?>")
GROUP = re.compile(r"<!subteam\^[A-Z0-9]+(?:\|([^>]*))?>")
DATE = re.compile(r"<!date\^[^|>]*\|([^>]*)>")
LINK = re.compile(r"<((?:https?|mailto|tel):[^|>]+)(?:\|([^>]*))?>")


def plain(token, text):
    """Slack's message markup as plain text: names for mentions, labels with their links."""
    if not text:
        return ""
    text = MENTION.sub(lambda m: "@" + (m.group(2) or user_name(token, m.group(1))), text)
    text = CHANNEL.sub(lambda m: "#" + (m.group(2) or m.group(1)), text)
    text = SPECIAL.sub(lambda m: "@" + m.group(1), text)
    text = GROUP.sub(lambda m: m.group(1) or "@group", text)
    text = DATE.sub(lambda m: m.group(1), text)
    text = LINK.sub(lambda m: ("%s (%s)" % (m.group(2), m.group(1))) if m.group(2) and m.group(2) != m.group(1)
                    else m.group(1), text)
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def when(ts):
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return "?"


def _shorten(text, limit=TEXT_LIMIT):
    return text if len(text) <= limit else text[:limit].rstrip() + " ... (%d more characters)" % (len(text) - limit)


def _indent(text, pad="    "):
    return pad + text.replace("\n", "\n" + pad)


def _author(token, m):
    if m.get("user"):
        return user_name(token, m["user"])
    return m.get("username") or (m.get("bot_profile") or {}).get("name") or "bot"


def render_message(token, m):
    parts = [when(m.get("ts")), _author(token, m), "ts=" + str(m.get("ts"))]
    if m.get("reply_count") and m.get("thread_ts") == m.get("ts"):
        parts.append("thread: %d replies" % m["reply_count"])
    elif m.get("thread_ts") and m.get("thread_ts") != m.get("ts"):
        parts.append("reply in thread " + m["thread_ts"])
    text = plain(token, m.get("text") or "")
    files = [f.get("title") or f.get("name") for f in m.get("files") or [] if f.get("title") or f.get("name")]
    if files:
        text = (text + "\n" if text else "") + "[files: " + ", ".join(files) + "]"
    return " · ".join(parts) + "\n" + _indent(_shorten(text) or "(no text)")


def _date_ts(value, end=False):
    """A Slack timestamp from a Slack ts, seconds since 1970, or a local date (YYYY-MM-DD) or date and time."""
    text = str(value or "").strip()
    if not text:
        return None
    if SLACK_TS.match(text):
        return text
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            moment = datetime.strptime(text, pattern)
        except ValueError:
            continue
        stamp = moment.timestamp() + (86399.999 if end and pattern == "%Y-%m-%d" else 0)
        return "%.6f" % stamp
    raise OrgError("Times are a Slack ts (1730812345.123456) or a date like 2026-11-05 (or 2026-11-05 14:30).")


def _rts(token, m):
    return {"channel_id": m.get("channel_id") or "", "channel": m.get("channel_name") or "",
            "author": m.get("author_name") or user_name(token, m.get("author_user_id")),
            "ts": str(m.get("message_ts") or ""), "thread_ts": str(m.get("thread_ts") or ""),
            "text": m.get("content") or "", "permalink": m.get("permalink") or ""}


def _legacy(token, query, limit, cursor):
    page = int(cursor) if str(cursor or "").isdigit() else 1
    body, _ = call_api("search.messages", {"query": query, "count": limit, "page": page, "sort": "score"}, token)
    block = body.get("messages") or {}
    found = []
    for m in block.get("matches") or []:
        channel = m.get("channel") or {}
        found.append({"channel_id": channel.get("id") or "", "channel": channel.get("name") or "",
                      "author": m.get("username") or user_name(token, m.get("user")), "ts": str(m.get("ts") or ""),
                      "thread_ts": "", "text": m.get("text") or "", "permalink": m.get("permalink") or "",
                      "kind": _kind(channel)})
    paging = block.get("paging") or block.get("pagination") or {}
    pages = paging.get("pages") or paging.get("page_count") or 1
    return found, (str(page + 1) if page < pages else "")


def _result_allowed(scope, item):
    cid = item.get("channel_id") or ""
    if scope.get("mode") == "list":
        return cid in (scope.get("conversations") or [])
    if scope.get("mode") != "all":
        return False
    kind = item.get("kind") or ("im" if cid.startswith("D") else "")
    return scope.get("dms") or kind not in ("im", "mpim")


def search(token, scope, query, limit=None, cursor=None, config=None):
    query = " ".join(str(query or "").split())
    if not query:
        raise OrgError("search needs a query.")
    limit = max(1, min(int(limit or SEARCH_LIMIT), SEARCH_LIMIT))
    try:
        body, _ = call_api("assistant.search.context", {
            "query": query, "channel_types": channel_types(scope), "content_types": "messages", "limit": limit,
            "cursor": cursor, "include_bots": "true"}, token)
        found = [_rts(token, m) for m in (body.get("results") or {}).get("messages") or []]
        more = (body.get("response_metadata") or {}).get("next_cursor") or ""
    except SlackError as error:
        granted = (load_config() if config is None else config).get("scopes") or []
        if error.code not in LEGACY_FALLBACK or "search:read" not in granted:
            raise
        found, more = _legacy(token, query, limit, cursor)
    return [m for m in found if _result_allowed(scope, m)], more


def render_search(token, query, found, more):
    lines = ["Slack search for \"%s\": %d message%s, best matches first." % (query, len(found), "" if len(found) == 1 else "s")]
    used = len(lines[0])
    for n, m in enumerate(found, 1):
        if used > OUTPUT_LIMIT:
            lines.append("(%d more not shown: search with more precise words.)" % (len(found) - n + 1))
            break
        where = ("#" + m["channel"]) if m["channel"] and not m["channel_id"].startswith("D") else \
            ("direct message" + (" with " + m["channel"] if m["channel"] else ""))
        head = "[%d] %s · %s · %s (channel %s, ts=%s%s)" % (n, where, when(m["ts"]), m["author"], m["channel_id"] or "?",
                                                         m["ts"], (", thread " + m["thread_ts"]) if m["thread_ts"] else "")
        lines.append(head + "\n" + _indent(_shorten(plain(token, m["text"])) or "(no text)")
                     + (("\n    " + m["permalink"]) if m["permalink"] else ""))
        used += len(lines[-1]) + 1
    if more:
        lines.append("More results: call search again with the same query and cursor=%s." % more)
    if not found:
        lines.append("Nothing found. Try other words, a person's name, or a channel's history.")
    return "\n".join(lines)


def history(token, scope, org, channel, limit=None, oldest=None, latest=None):
    conv = resolve(token, channel)
    _check(scope, conv, org)
    params = {"channel": conv["id"], "limit": max(1, min(int(limit or 50), HISTORY_LIMIT)),
              "oldest": _date_ts(oldest), "latest": _date_ts(latest, end=True)}
    if params["oldest"] or params["latest"]:
        params["inclusive"] = "true"
    body, _ = call_api("conversations.history", params, token)
    messages = [m for m in reversed(body.get("messages") or []) if m.get("subtype") not in NOISE]
    return conv, messages, bool(body.get("has_more"))


def thread(token, scope, org, channel, ts, limit=None):
    conv = resolve(token, channel)
    _check(scope, conv, org)
    ts = str(ts or "").strip()
    if not SLACK_TS.match(ts):
        raise OrgError("thread needs ts: the Slack timestamp of the thread's first message, like 1730812345.123456.")
    body, _ = call_api("conversations.replies", {"channel": conv["id"], "ts": ts,
                                                 "limit": max(1, min(int(limit or 200), 1000))}, token)
    return conv, [m for m in body.get("messages") or [] if m.get("subtype") not in NOISE], bool(body.get("has_more"))


KIND_NAMES = {"public": "channel", "private": "private channel", "mpim": "group direct message", "im": "direct message"}


def render_messages(token, title, messages, more, hint, newest=True):
    """Messages oldest first. An answer longer than OUTPUT_LIMIT keeps the newest messages (newest=False: the first
    ones, for a thread) and says how many were left out."""
    warm_users(token, [m.get("user") for m in messages])
    shown = [render_message(token, m) for m in messages]
    used, kept = len(title), []
    for text in (reversed(shown) if newest else shown):
        if kept and used + len(text) + 1 > OUTPUT_LIMIT:
            break
        kept.append(text)
        used += len(text) + 1
    left = len(shown) - len(kept)
    if newest:
        kept.reverse()
    lines = [title]
    if left and newest:
        lines.append("(%d earlier message%s not shown: call history again with latest=%s.)" % (
            left, "" if left == 1 else "s", messages[left - 1]["ts"]))
    lines += kept
    if left and not newest:
        lines.append("(%d later message%s not shown: pass a smaller limit.)" % (left, "" if left == 1 else "s"))
    if more:
        lines.append(hint)
    return "\n".join(lines)


def channels(token, scope, query=None):
    mine = member_conversations(token)
    if scope.get("mode") == "list":
        known = {c["id"] for c in mine}
        extra = []
        for cid in scope.get("conversations") or []:
            if cid not in known:
                try:
                    extra.append(conversation(token, cid))
                except SlackError:
                    continue
        mine = mine + extra
    words = str(query or "").strip().lower().lstrip("#@")
    return [c for c in mine if allowed(scope, c) and (not words or words in c["label"].lower())]


def render_channels(found, scope):
    lines = ["Conversations this organization may read (%s): %d%s." % (describe(scope), len(found),
                                                                       ", the person's own" if found else "")]
    order = {"public": 0, "private": 1, "mpim": 2, "im": 3}
    for c in sorted(found, key=lambda c: (order.get(c["kind"], 9), c["label"].lower()))[:400]:
        lines.append("%s  %s  %s" % (c["label"], c["id"], KIND_NAMES.get(c["kind"], c["kind"])))
    if len(found) > 400:
        lines.append("... and %d more; pass query to narrow the list." % (len(found) - 400))
    if scope.get("mode") == "all":
        lines.append("Public channels the person has not joined can be read too: history with #name.")
    return "\n".join(lines)


def explain(error):
    code = getattr(error, "code", "")
    if code in BROKEN_TOKEN:
        return "Slack no longer accepts Relic's token (%s). The person reconnects in the Relic App: Settings, Slack." % code
    if code == "missing_scope":
        return ("The person's Slack app lacks a permission for this. The person reinstalls it with the manifest shown "
                "in the Relic App: Settings, Slack.")
    if code in ("channel_not_found", "not_in_channel", "thread_not_found", "message_not_found"):
        return "Slack has no such conversation or message that the person can read (%s)." % code
    if code in ("ratelimited", "rate_limited"):
        return "Slack is limiting how fast it answers; try again in a minute."
    if code.startswith("network"):
        return "Relic could not reach Slack: " + code
    return str(error)


def tool_call(store, actor, args):
    """The members' slack tool. Reads only, within what the person lets the caller's organization read."""
    org, member = store.require(actor)
    op = args.get("op")
    if op not in OPS:
        raise OrgError("slack ops: search, history, thread, channels.")
    config, token = load_config(), load_token()
    if not config.get("team") or not token:
        raise OrgError("Slack is not connected. The person connects it in the Relic App: Settings, Slack.")
    scope = org_scope(store, org, config)
    if scope["mode"] == "none":
        raise OrgError("The person has not let %s read Slack (Relic App: Settings, Slack)." % org["name"])
    target = {"search": args.get("query"), "history": args.get("channel"),
              "thread": "%s %s" % (args.get("channel") or "", args.get("ts") or ""), "channels": args.get("query")}[op]
    try:
        if op == "search":
            found, more = search(token, scope, args.get("query"), args.get("limit"), args.get("cursor"), config)
            text, count = render_search(token, " ".join(str(args.get("query")).split()), found, more), len(found)
        elif op == "history":
            conv, messages, more = history(token, scope, org, args.get("channel"), args.get("limit"),
                                           args.get("oldest"), args.get("latest"))
            target, count = "%s %s" % (conv["label"], conv["id"]), len(messages)
            oldest = messages[0]["ts"] if messages else ""
            text = render_messages(token, "%s (%s, %s): %d message%s, oldest first." % (
                conv["label"], conv["id"], KIND_NAMES[conv["kind"]], count, "" if count == 1 else "s"), messages, more,
                "Older messages exist: call history again with latest=%s." % oldest)
        elif op == "thread":
            conv, messages, more = thread(token, scope, org, args.get("channel"), args.get("ts"), args.get("limit"))
            target, count = "%s %s %s" % (conv["label"], conv["id"], args.get("ts")), len(messages)
            text = render_messages(token, "Thread in %s (%s), %d message%s." % (
                conv["label"], conv["id"], count, "" if count == 1 else "s"), messages, more,
                "The thread goes on; pass a larger limit.", newest=False)
        else:
            found = channels(token, scope, args.get("query"))
            text, count = render_channels(found, scope), len(found)
    except SlackError as error:
        log_read(org, member, op, target, 0, error.code)
        raise OrgError(explain(error))
    except OrgError as error:
        log_read(org, member, op, target, 0, str(error)[:200])
        raise
    log_read(org, member, op, target, count)
    return {"text": text, "text_only": True}


def context_note(store, org):
    """One line for the organization's context while Slack is connected and the organization may read it."""
    config = load_config()
    if not config.get("team") or not token_path().exists():
        return ""
    scope = org_scope(store, org, config)
    if scope["mode"] == "none":
        return ""
    return ("Slack: the person's workspace %s is connected; this organization may read %s. When you lack background "
            "the person would otherwise have to explain, look in Slack first with the slack tool (op=search, history, "
            "thread, channels). It is read-only and every read is logged with your seat."
            % ((config.get("team") or {}).get("name") or "?", describe(scope)))


# ---------------- the read log ----------------

def log_path():
    return data_home() / "slack.sqlite3"


def _log_db():
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=10)
    db.execute("CREATE TABLE IF NOT EXISTS reads(id INTEGER PRIMARY KEY, at REAL NOT NULL, org_id TEXT, org_name TEXT, "
               "member TEXT, op TEXT, target TEXT, count INTEGER NOT NULL DEFAULT 0, error TEXT)")
    db.execute("CREATE INDEX IF NOT EXISTS reads_at ON reads(at)")
    return db


def log_read(org, member, op, target, count, error=None):
    now = time.time()
    try:
        db = _log_db()
        try:
            with db:
                db.execute("INSERT INTO reads(at, org_id, org_name, member, op, target, count, error) "
                           "VALUES(?, ?, ?, ?, ?, ?, ?, ?)", (now, org["id"], org.get("name") or "", member, op,
                                                              str(target or "")[:300], int(count or 0), error))
                db.execute("DELETE FROM reads WHERE at < ?", (now - LOG_DAYS * 86400,))
        finally:
            db.close()
    except sqlite3.Error:
        pass


def reads(limit=50):
    if not log_path().exists():
        return []
    try:
        db = _log_db()
        try:
            rows = db.execute("SELECT at, org_id, org_name, member, op, target, count, error FROM reads "
                              "ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 500)),)).fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        return []
    return [{"at": at, "org": org_id, "org_name": org_name, "member": member, "op": op, "target": target,
             "count": count, "error": error} for at, org_id, org_name, member, op, target, count, error in rows]


# ---------------- the Relic App's settings ----------------

def _org_rows(store, config):
    """The organizations as a tree in the sidebar's order (app/views.org_list): the latest event first, else the
    newest created, among roots and among each organization's children."""
    orgs = [o for o in store.list_orgs() if o.get("status", "active") == "active"]
    by_id = {o["id"]: o for o in orgs}
    with store.db() as db:
        last = dict(db.execute("SELECT org_id, MAX(at) FROM events GROUP BY org_id").fetchall())

    def recent(org):
        return last.get(org["id"]) or org.get("created_at") or ""
    children, roots = {}, []
    for o in orgs:
        (children.setdefault(o["parent"], []) if o.get("parent") in by_id else roots).append(o)
    rows, own = [], config.get("orgs") or {}

    def walk(org, depth):
        effective = org_scope(store, org, config)
        source = effective.get("source")
        rows.append({"id": org["id"], "name": org["name"], "depth": depth, "own": _entry(own.get(org["id"])),
                     "effective": {k: v for k, v in effective.items() if k != "source"}, "source": source,
                     "source_name": by_id[source]["name"] if source in by_id else ""})
        for child in sorted(children.get(org["id"], []), key=recent, reverse=True):
            walk(child, depth + 1)
    for org in sorted(roots, key=recent, reverse=True):
        walk(org, 0)
    return rows


def status(store):
    """The settings page: the connection (never the token), each organization's choice, the latest reads."""
    config = load_config()
    linked = connected(config)
    granted = set(config.get("scopes") or [])
    return {"connected": linked, "team": config.get("team") if linked else None,
            "user": config.get("user") if linked else None, "connected_at": config.get("connected_at") if linked else None,
            "ai_search": config.get("ai_search") if linked else None, "scopes": sorted(granted) if linked else [],
            "missing_scopes": [s for s in USER_SCOPES if linked and s not in granted],
            "default": _entry(config.get("default")) or dict(DEFAULT), "orgs": _org_rows(store, config),
            "manifest": json.dumps(MANIFEST, ensure_ascii=False, indent=2), "create_url": CREATE_URL,
            "reads": reads(50)}


def connect(store, token):
    """Check a token the person pasted with Slack and keep it. Raises ValueError with a word-list key."""
    token = str(token or "").strip()
    if token.startswith("xoxb-"):
        raise ValueError("slack.error.bot_token")
    if not token.startswith("xoxp-"):
        raise ValueError("slack.error.not_user_token")
    try:
        body, headers = call_api("auth.test", {}, token)
    except SlackError as error:
        if error.code in BROKEN_TOKEN:
            raise ValueError("slack.error.invalid_token")
        if error.code.startswith("network"):
            raise ValueError("slack.error.unreachable")
        raise ValueError("Slack: " + error.code)
    scopes = sorted({s.strip() for s in (headers.get("X-OAuth-Scopes") or "").split(",") if s.strip()})
    team = {"id": body.get("team_id") or "", "name": body.get("team") or "", "url": body.get("url") or "", "domain": ""}
    try:
        info, _ = call_api("team.info", {"team": team["id"]}, token)
        team.update(name=(info.get("team") or {}).get("name") or team["name"],
                    domain=(info.get("team") or {}).get("domain") or "")
    except SlackError:
        pass
    ai = None
    try:
        info, _ = call_api("assistant.search.info", {}, token)
        ai = bool(info.get("is_ai_search_enabled"))
    except SlackError:
        pass
    save_token(token)
    config = load_config()
    config.update(team=team, user={"id": body.get("user_id") or "", "name": body.get("user") or ""}, scopes=scopes,
                  ai_search=ai, connected_at=datetime.now().astimezone().isoformat(timespec="seconds"))
    config.setdefault("default", dict(DEFAULT))
    save_config(config)
    clear_cache()
    return status(store)


def disconnect(store):
    """Forget the token on this computer. The person's choices of what each organization may read stay."""
    forget_token()
    config = load_config()
    for key in ("team", "user", "scopes", "ai_search", "connected_at"):
        config.pop(key, None)
    save_config(config)
    clear_cache()
    return status(store)


def set_scope(store, org_id, mode, conversations=None, dms=False):
    """The person's choice for one organization, or for the default (org_id empty). mode inherit drops the choice."""
    if mode not in MODES + ("inherit",):
        raise ValueError("mode is all, list, none or inherit")
    config = load_config()
    entry = {"mode": mode, "dms": bool(dms)}
    if mode == "list":
        entry["conversations"] = sorted({str(c) for c in conversations or [] if CHANNEL_ID.match(str(c))})
    if not org_id or org_id == "default":
        if mode == "inherit":
            raise ValueError("the default has nothing to follow")
        config["default"] = entry
    else:
        store.get(org_id)  # a real organization
        own = config.setdefault("orgs", {})
        if mode == "inherit":
            own.pop(org_id, None)
        else:
            own[org_id] = entry
    save_config(config)
    return status(store)


def picker(store):
    """The conversations the person can choose from for an organization's list."""
    token = load_token()
    if not token or not load_config().get("team"):
        raise ValueError("slack.error.not_connected")
    try:
        mine = member_conversations(token)
    except SlackError as error:
        raise ValueError("Slack: " + explain(error))
    order = {"public": 0, "private": 1, "mpim": 2, "im": 3}
    return {"conversations": [{"id": c["id"], "kind": c["kind"], "label": c["label"]}
                              for c in sorted(mine, key=lambda c: (order.get(c["kind"], 9), c["label"].lower()))]}
