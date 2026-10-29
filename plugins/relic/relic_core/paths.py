"""Filesystem-aware protocol paths and exact paths recorded by tool calls.

Relative globs retain Relic's suffix matching. Absolute globs stay anchored. On macOS, canonically equivalent
Unicode is compared in NFC and case is folded only when the target volume reports case-insensitive names. Both
the spelling supplied by the tool and its resolved symlink target are checked; resolving a glob never expands it.
"""
import fnmatch
import ntpath
import os
import re
import sys
import unicodedata
from pathlib import Path


def path_text(value):
    """Keep POSIX filenames intact (a backslash is legal); normalize Windows separators as before."""
    text = str(value)
    return text.replace("\\", "/") if os.name == "nt" or re.match(r"^[A-Za-z]:[\\/]", text) else text


def absolute(path, cwd=None):
    """Anchor a native path only with a known absolute cwd; never borrow the server's working directory.

    Do not normpath before resolving: ``link/../file`` follows the link before applying ``..`` on disk.
    """
    if not isinstance(path, str) or not path or "\0" in path:
        return None
    try:
        text = os.path.expanduser(path)
        if os.name != "nt" and ntpath.isabs(text) and not text.startswith("/"):
            return None  # a Windows path imported on macOS is not a relative local filename
        if not os.path.isabs(text):
            base = os.path.expanduser(cwd) if isinstance(cwd, str) and cwd else ""
            if not os.path.isabs(base):
                return None
            text = os.path.join(base, text)
        return str(Path(text))
    except (OSError, RuntimeError, ValueError):
        return None


def resolved(path):
    try:
        return str(Path(path).resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        return None


def records(values, cwd=None):
    """The original absolute spelling and the target at the time of the edit, including every patched file."""
    out, seen = [], set()
    for value in values:
        path = absolute(value, cwd)
        target = resolved(path) if path else None
        if path and target and path not in seen:
            seen.add(path)
            out.append({"path": path, "resolved": target})
    return out


def case_sensitive(path, platform=None):
    """Whether the existing ancestor's volume distinguishes case; None when macOS cannot tell.

    Darwin's _PC_CASE_SENSITIVE is 11 (sys/unistd.h). Python accepts the numeric pathconf selector even though it
    omits this Darwin-specific name from os.pathconf_names. This query is read-only and works for new files too.
    """
    platform = platform or sys.platform
    if platform == "win32":
        return False
    if platform != "darwin":
        return True
    if not path:
        return None
    parent = Path(path)
    while True:
        try:
            value = os.pathconf(parent, 11)
            return bool(value) if value in (0, 1) else None
        except (FileNotFoundError, NotADirectoryError):
            if parent == parent.parent:
                return None
            parent = parent.parent
        except (OSError, ValueError):
            return None


def _resolved_glob(pattern, cwd):
    """Resolve only the literal directory prefix; wildcard components remain patterns, never filenames."""
    parts = pattern.split("/")
    first_magic = next((n for n, part in enumerate(parts) if any(c in part for c in "*?[")), len(parts))
    prefix = "/".join(parts[:first_magic])
    if not prefix and pattern.startswith("/"):
        prefix = "/"
    base = absolute(prefix or ".", cwd)
    real = resolved(base) if base else None
    if real is None:
        return None
    return real.rstrip("/") + "/" + "/".join(parts[first_magic:]) if first_magic < len(parts) else real


def matches(path, pattern, cwd=None, platform=None):
    """Match a protocol glob without assuming all Darwin volumes have the same case behavior."""
    platform = platform or sys.platform
    path, pattern = path_text(path), str(pattern)
    if platform == "win32":
        # Keep the existing Windows fnmatch semantics, including slash normalization and relative suffixes.
        candidate = ntpath.normcase(path)
        return any(fnmatch.fnmatchcase(candidate, ntpath.normcase(p))
                   for p in (pattern, "*/" + pattern.lstrip("/")))
    anchored = absolute(path, cwd)
    real = resolved(anchored) if anchored else None
    candidates = list(dict.fromkeys(p for p in (path, anchored, real) if p))
    patterns = [pattern]
    if not pattern.startswith("/"):
        patterns.append("*/" + pattern)
    canonical = _resolved_glob(pattern, cwd)
    if canonical and canonical not in patterns:
        patterns.append(canonical)
    for candidate in candidates:
        sensitive = case_sensitive(absolute(candidate, cwd), platform)
        def comparable(text):
            text = unicodedata.normalize("NFC", text) if platform == "darwin" else text
            return text.casefold() if sensitive is False else text
        if any(fnmatch.fnmatchcase(comparable(candidate), comparable(p)) for p in patterns):
            return True
    return False
