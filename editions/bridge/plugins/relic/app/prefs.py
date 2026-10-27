"""The person's settings for the Relic App (~/.relic/app/prefs.json) and the avatars they choose
(~/.relic/app/avatars/me.<ext>, ~/.relic/app/avatars/<org>/<member>.<ext>)."""
import base64
import json
import re
import threading
from pathlib import Path

from relic_core.store import data_home

DEFAULTS = {
    "name": "",             # how the App labels the person (empty: 你)
    "lang": "",             # language for member names and replies (empty: the system's)
    "theme": "system",      # system | light | dark
    "accent": "clay",       # clay | ink | indigo | rose | teal
    "font": "medium",       # small | medium | large
    "density": "comfortable",  # comfortable | compact
    "auto_names": True,     # name members by what they do, in the person's language
    "notify": True,         # desktop notifications for decisions and @-mentions
    "voice": "browser",     # browser (Edge speech recognition) | off
    "paths": {},            # harness id -> program path chosen by the person
}
TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}
MAX_AVATAR = 2 * 1024 * 1024
_lock = threading.Lock()


def folder():
    return data_home() / "app"


def path():
    return folder() / "prefs.json"


def load():
    try:
        stored = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    out = dict(DEFAULTS)
    out.update({k: v for k, v in stored.items() if k in DEFAULTS})
    return out


def save(changes):
    with _lock:
        current = load()
        for key, value in (changes or {}).items():
            if key not in DEFAULTS:
                continue
            if key == "paths" and isinstance(value, dict):
                current["paths"] = {k: str(v) for k, v in value.items() if v}
            elif isinstance(DEFAULTS[key], bool):
                current[key] = bool(value)
            else:
                current[key] = str(value or "")[:200]
        folder().mkdir(parents=True, exist_ok=True)
        tmp = path().with_suffix(".tmp")
        tmp.write_text(json.dumps(current, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path())
        return current


# ---------------------------------------------------------------- avatars
def _safe(part):
    if not re.fullmatch(r"[A-Za-z0-9_.\-㐀-鿿]{1,80}", part or "") or part in (".", ".."):
        raise ValueError("bad name")
    return part


def avatar_base(org_id=None, member=None):
    base = folder() / "avatars"
    return base / "me" if not org_id else base / _safe(org_id) / _safe(member)


def avatar_file(org_id=None, member=None):
    base = avatar_base(org_id, member)
    for ext in TYPES.values():
        candidate = base.with_suffix(ext)
        if candidate.is_file():
            return candidate
    return None


def avatar_url(org_id=None, member=None):
    try:
        found = avatar_file(org_id, member)
    except ValueError:
        return None
    if not found:
        return None
    version = int(found.stat().st_mtime)
    return ("/api/avatar?v=%d" % version) if not org_id else ("/api/avatar/%s/%s?v=%d" % (org_id, member, version))


def save_avatar(data_url, org_id=None, member=None):
    """data_url: "data:image/png;base64,..." (empty removes the avatar)."""
    base = avatar_base(org_id, member)
    for ext in TYPES.values():
        old = base.with_suffix(ext)
        if old.is_file():
            old.unlink()
    if not data_url:
        return None
    match = re.fullmatch(r"data:(image/[a-z+]+);base64,(.+)", data_url.strip(), re.S)
    if not match or match.group(1) not in TYPES:
        raise ValueError("Use a PNG, JPEG, WebP or GIF image.")
    raw = base64.b64decode(match.group(2), validate=False)
    if len(raw) > MAX_AVATAR:
        raise ValueError("The image is larger than 2 MB.")
    base.parent.mkdir(parents=True, exist_ok=True)
    target = base.with_suffix(TYPES[match.group(1)])
    target.write_bytes(raw)
    return target
