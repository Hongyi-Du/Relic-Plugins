"""What the person reads, in their language.

Each language has one word list, relic_core/locales/<code>.json: a flat map from key to text, plus "@name", the
language's name in itself (for the language menu). The Relic App's page and its server read the same lists, so a new
language is one new file, and it appears in the App's language menu by itself.

A text may hold {name} placeholders. A text that depends on a count is a map from plural form to text ("one", "other":
the CLDR names), chosen by the number named n. A list given for a placeholder reads as a list in the language
("a, b and c"; the list.* texts). What a word list lacks comes from English (en-US), so a partial list still works.
"""
import json
import re
import threading
from pathlib import Path

LOCALES = Path(__file__).resolve().parent / "locales"
FALLBACK = "en-US"
# languages whose words do not change with a count (CLDR: "other" only)
NO_PLURAL = {"zh", "ja", "ko", "th", "vi", "id", "ms", "lo", "my", "km", "yue"}
HOLE = re.compile(r"\{(\w+)\}")

_lock = threading.Lock()
_cache = {}  # code -> (mtime, word list)


def _read(code):
    path = LOCALES / ("%s.json" % code)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    with _lock:
        hit = _cache.get(code)
        if hit and hit[0] == mtime:
            return hit[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    with _lock:
        _cache[code] = (mtime, data)
    return data


def codes():
    """The languages with a word list, e.g. ["en-US", "ja-JP", "zh-CN", "zh-TW"]."""
    return sorted(p.stem for p in LOCALES.glob("*.json"))


def languages():
    """[{"code", "name"}] for every language with a word list, each named in itself."""
    return [{"code": code, "name": _read(code).get("@name") or code} for code in codes()]


def resolve(tag):
    """The word list for a language tag: the same tag; else the same language (Traditional Chinese for zh-HK, zh-MO
    and zh-Hant, Simplified for other Chinese); else English."""
    available = codes()
    lower = {code.lower(): code for code in available}
    tag = str(tag or "").strip().replace("_", "-").lower()
    if tag in lower:
        return lower[tag]
    parts = tag.split("-")
    if parts[0] == "zh":
        traditional = "hant" in parts or ("hans" not in parts and bool({"tw", "hk", "mo"} & set(parts)))
        wanted = "zh-tw" if traditional else "zh-cn"
        if wanted in lower:
            return lower[wanted]
    same = [code for code in available if code.lower().split("-")[0] == parts[0]]
    if same:
        return same[0]
    return FALLBACK


def strings(tag):
    """(code, texts): the word list the tag resolves to, with what it lacks taken from English; no "@" entries."""
    code = resolve(tag)
    words = {k: v for k, v in _read(FALLBACK).items() if not k.startswith("@")}
    if code != FALLBACK:
        words.update((k, v) for k, v in _read(code).items() if not k.startswith("@"))
    return code, words


def plural(code, n):
    """The plural form a count takes in a language: "one" or "other" (enough for the languages the App ships)."""
    lang = code.lower().split("-")[0]
    if lang in NO_PLURAL:
        return "other"
    if lang in ("fr", "pt") and n in (0, 1):
        return "one"
    return "one" if n == 1 else "other"


def _fill(words, text, args):
    return HOLE.sub(lambda m: _value(words, args[m.group(1)]) if m.group(1) in args else m.group(0), text)


def _value(words, value):
    if isinstance(value, (list, tuple)):
        items = [str(v) for v in value]
        if len(items) < 2:
            return items[0] if items else ""
        if len(items) == 2:
            return _fill(words, words.get("list.pair", "{a}, {b}"), {"a": items[0], "b": items[1]})
        text = _fill(words, words.get("list.end", "{a}, {b}"), {"a": items[-2], "b": items[-1]})
        for item in reversed(items[:-2]):
            text = _fill(words, words.get("list.middle", "{a}, {b}"), {"a": item, "b": text})
        return text
    return "" if value is None else str(value)


def t(key, lang=None, **args):
    """The text for key in a language (default: the person's), with {name} placeholders filled from args."""
    if lang is None:
        from .store import person_language
        lang = person_language()
    code, words = strings(lang)
    text = words.get(key, key)
    if isinstance(text, dict):
        n = args.get("n")
        form = plural(code, n) if isinstance(n, (int, float)) else "other"
        text = text.get(form) or text.get("other") or ""
    return _fill(words, str(text), args)
