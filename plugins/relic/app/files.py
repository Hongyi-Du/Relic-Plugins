"""Members' workspaces for the Relic App: the folder each member works in, its git changes, the files the member
changed lately, and a preview of any file there. Only folders that belong to a member (its session's working directory
or its configured folder) and the Relic data folder can be listed or read."""
import json
import mimetypes
import os
import subprocess
import time
from pathlib import Path

from relic_core import i18n, platform_support, runner
from relic_core.store import data_home

from . import views

TEXT_LIMIT = 2 * 1024 * 1024
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch", "str_replace_based_edit_tool")
_ROOTS = {"at": 0.0, "roots": []}
_EDITED = {"at": 0.0, "files": set()}


def _norm(path):
    try:
        return Path(str(path)).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def member_folder(seat):
    carrier = seat.get("carrier") or ""
    meta = views.session_meta(carrier) if carrier and seat.get("harness") not in views.CHAT_HARNESSES else {}
    return meta.get("cwd") or (seat.get("config") or {}).get("folder") or ""


def roots(store):
    """Folders the App may show: every member's working folder, and the Relic data folder."""
    key = str(store.path.resolve())
    if _ROOTS.get("store") == key and time.time() - _ROOTS["at"] < 30:
        return _ROOTS["roots"]
    found = {_norm(data_home())}
    for org in store.list_orgs():
        for seat in (org.get("members") or {}).values():
            folder = member_folder(seat)
            if folder:
                found.add(_norm(folder))
    _ROOTS.update(at=time.time(), store=key, roots=[r for r in found if r])
    return _ROOTS["roots"]


def _activity_paths(encoded, summary):
    """Exact new records; old summaries are accepted only when they name complete, existing absolute files.

    A summary is not a path grammar: filenames can contain spaces, commas and newlines. First try its whole text;
    only then try the old comma-separated list. Never salvage an arbitrary pathname fragment from prose.
    """
    if encoded is not None:
        try:
            values = json.loads(encoded)
        except (TypeError, ValueError):
            return []
        if not isinstance(values, list):
            return []
        return [v for v in values if isinstance(v, dict) and all(
            isinstance(v.get(k), str) and "\0" not in v[k] and Path(v[k]).is_absolute() for k in ("path", "resolved"))]
    text = summary or ""
    if len(text) >= 500:
        return []  # old writers clipped here; a truncated filename is not evidence that its prefix was edited
    def existing(value):
        try:
            return bool(value) and Path(value).is_absolute() and Path(value).is_file()
        except (OSError, ValueError):
            return False
    candidates = [text] if existing(text) else text.split(", ")
    if not all(existing(value) for value in candidates):
        return []
    return [{"path": value, "resolved": str(target)} for value in candidates
            if existing(value) and (target := _norm(value)) is not None]


def edited_files(store):
    """Files members changed lately (from their tool calls): they can be previewed even outside the member's folder."""
    key = (str(store.path.resolve()), views._rows(store, "SELECT COALESCE(MAX(id), 0) FROM activity")[0][0])
    if _EDITED.get("key") == key and time.time() - _EDITED["at"] < 30:
        return _EDITED["files"]
    found = set()
    for tool, summary, encoded in views._rows(store, "SELECT tool, summary, paths FROM activity WHERE COALESCE(failed, 0)=0 "
                                                    "ORDER BY id DESC LIMIT 5000"):
        if (tool or "").rsplit("__", 1)[-1] not in EDIT_TOOLS:
            continue
        # This target was resolved when the edit was recorded. Do not resolve it again after a symlink retarget.
        found.update(Path(p["resolved"]) for p in _activity_paths(encoded, summary))
    _EDITED.update(at=time.time(), key=key, files=found)
    return _EDITED["files"]


def allowed(store, path):
    target = _norm(path)
    if target is None:
        return None
    for root in roots(store):
        if any(_same_file(parent, root) for parent in (target, *target.parents)):
            return target
    return target if any(_same_file(target, edited) for edited in edited_files(store)) else None


def _same_file(left, right):
    if left == right:
        return True
    try:
        return left.samefile(right)
    except (OSError, ValueError):
        return False


def _git(folder, *args):
    git = platform_support.find_executable("git")
    if not git:
        return None
    try:
        done = subprocess.run([git, "-C", str(folder)] + list(args), capture_output=True,
                              timeout=6, creationflags=runner.NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return os.fsdecode(done.stdout) if done.returncode == 0 else None


def _git_status(text, folder):
    """Porcelain v1 -z: NUL-delimited raw names; renames/copies carry destination first, then source."""
    fields = text.split("\0")
    branch, changes, index = "", [], 0
    while index < len(fields) and len(changes) < 200:
        field = fields[index]
        index += 1
        if field.startswith("## "):
            branch = field[3:].split("...", 1)[0]
            continue
        if len(field) < 4 or field[2] != " ":
            continue
        code, name = field[:2], field[3:]
        change = {"status": code.strip() or "?", "path": str(Path(folder) / name)}
        if "R" in code or "C" in code:
            if index >= len(fields) or not fields[index]:
                continue  # incomplete rename: do not turn the source into a second changed file
            change["old_path"] = str(Path(folder) / fields[index])
            index += 1
        changes.append(change)
    return branch, changes


def workspace(store, org_id, member):
    org = store.get(org_id)
    seat = (org.get("members") or {}).get(member)
    if seat is None:
        raise KeyError(member)
    folder = member_folder(seat)
    out = {"member": member, "folder": folder, "exists": bool(folder) and Path(folder).is_dir(), "git": None, "recent": []}
    if out["exists"]:
        status = _git(folder, "status", "--porcelain=v1", "-z", "-b", "--untracked-files=normal")
        if status is not None:
            top = (_git(folder, "rev-parse", "--show-toplevel") or "").removesuffix("\n")
            if os.name == "nt":
                top = top.removesuffix("\r")
            branch, changes = _git_status(status, top or folder)
            out["git"] = {"branch": branch, "root": top, "changes": changes}
    seen = set()
    for tool, summary, at, encoded in views._rows(store, "SELECT tool, summary, at, paths FROM activity WHERE org_id=? AND member=? "
                                                "ORDER BY id DESC LIMIT 400", (org_id, member)):
        short = (tool or "").rsplit("__", 1)[-1]
        if short not in EDIT_TOOLS:
            continue
        for record in _activity_paths(encoded, summary):
            path = record["path"]
            if record["resolved"] in seen:
                continue
            seen.add(record["resolved"])
            out["recent"].append({"path": path, "tool": short, "at": views.iso(at)})
            if len(out["recent"]) >= 40:
                break
        if len(out["recent"]) >= 40:
            break
    return out


def listdir(store, path):
    target = allowed(store, path)
    if target is None or not target.is_dir():
        raise PermissionError(i18n.t("fs.dir_outside"))
    entries = []
    try:
        with os.scandir(target) as it:
            for entry in it:
                try:
                    is_dir = entry.is_dir()
                    stat = entry.stat()
                except OSError:
                    continue
                entries.append({"name": entry.name, "path": str(Path(target) / entry.name), "dir": is_dir,
                                "size": 0 if is_dir else stat.st_size, "mtime": stat.st_mtime})
    except OSError as error:
        raise PermissionError(str(error))
    entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))
    return {"path": str(target), "parent": str(target.parent), "entries": entries[:800], "more": len(entries) > 800}


def read(store, path):
    target = allowed(store, path)
    if target is None or not target.is_file():
        raise PermissionError(i18n.t("fs.file_outside"))
    size = target.stat().st_size
    suffix = target.suffix.lower()
    info = {"path": str(target), "name": target.name, "size": size, "mtime": target.stat().st_mtime}
    if suffix in IMAGE_TYPES:
        return dict(info, kind="image", url="/api/fs/raw?path=" + _quote(str(target)))
    with open(target, "rb") as handle:
        raw = handle.read(TEXT_LIMIT)
    if b"\x00" in raw[:4096]:
        return dict(info, kind="binary")
    for encoding in ("utf-8", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        return dict(info, kind="binary")
    kind = "markdown" if suffix in (".md", ".markdown") else "json" if suffix == ".json" else "text"
    return dict(info, kind=kind, text=text, truncated=size > TEXT_LIMIT)


def raw(store, path):
    target = allowed(store, path)
    if target is None or not target.is_file():
        raise PermissionError(i18n.t("fs.file_outside"))
    return target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream"


def _quote(text):
    from urllib.parse import quote
    return quote(text, safe="")


def open_path(store, path):
    """Open an allowed file or folder with the system's default application."""
    target = allowed(store, path)
    if target is None:
        raise PermissionError(i18n.t("fs.path_outside"))
    platform_support.open_external(str(target))
    return {"opened": str(target)}


def roots_for_page(store):
    return [str(r) for r in roots(store)]
