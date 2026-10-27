"""Members' workspaces for the Relic App: the folder each member works in, its git changes, the files the member
changed lately, and a preview of any file there. Only folders that belong to a member (its session's working directory
or its configured folder) and the Relic data folder can be listed or read."""
import mimetypes
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from relic_core import runner
from relic_core.store import data_home

from . import views

TEXT_LIMIT = 2 * 1024 * 1024
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch", "str_replace_based_edit_tool")
PATH = re.compile(r"([A-Za-z]:[\\/][^\s\"'<>|*?]+|/[^\s\"'<>|*?]+\.[A-Za-z0-9]{1,8})")
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
    if time.time() - _ROOTS["at"] < 30:
        return _ROOTS["roots"]
    found = {_norm(data_home())}
    for org in store.list_orgs():
        for seat in (org.get("members") or {}).values():
            folder = member_folder(seat)
            if folder:
                found.add(_norm(folder))
    _ROOTS.update(at=time.time(), roots=[r for r in found if r])
    return _ROOTS["roots"]


def edited_files(store):
    """Files members changed lately (from their tool calls): they can be previewed even outside the member's folder."""
    if time.time() - _EDITED["at"] < 30:
        return _EDITED["files"]
    found = set()
    for tool, summary in views._rows(store, "SELECT tool, summary FROM activity ORDER BY id DESC LIMIT 5000"):
        if (tool or "").rsplit("__", 1)[-1] not in EDIT_TOOLS:
            continue
        match = PATH.search(summary or "")
        if match:
            found.add(match.group(1).rstrip(".,;:)"))
    _EDITED.update(at=time.time(), files={p for p in (_norm(x) for x in found) if p})
    return _EDITED["files"]


def allowed(store, path):
    target = _norm(path)
    if target is None:
        return None
    for root in roots(store):
        if target == root or root in target.parents:
            return target
    return target if target in edited_files(store) else None


def _git(folder, *args):
    git = shutil.which("git")
    if not git:
        return None
    try:
        done = subprocess.run([git, "-C", str(folder)] + list(args), capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=6, creationflags=runner.NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def workspace(store, org_id, member):
    org = store.get(org_id)
    seat = (org.get("members") or {}).get(member)
    if seat is None:
        raise KeyError(member)
    folder = member_folder(seat)
    out = {"member": member, "folder": folder, "exists": bool(folder) and Path(folder).is_dir(), "git": None, "recent": []}
    if out["exists"]:
        status = _git(folder, "status", "--porcelain=v1", "-b", "--untracked-files=normal")
        if status is not None:
            lines = status.splitlines()
            branch = lines[0][3:].split("...")[0] if lines and lines[0].startswith("## ") else ""
            top = (_git(folder, "rev-parse", "--show-toplevel") or "").strip()
            changes = []
            for line in lines[1:200]:
                code, rel = line[:2], line[3:].split(" -> ")[-1].strip().strip('"')
                changes.append({"status": code.strip() or "?", "path": str(Path(top or folder) / rel)})
            out["git"] = {"branch": branch, "root": top, "changes": changes}
    seen = set()
    for tool, summary, at in views._rows(store, "SELECT tool, summary, at FROM activity WHERE org_id=? AND member=? "
                                                "ORDER BY id DESC LIMIT 400", (org_id, member)):
        short = (tool or "").rsplit("__", 1)[-1]
        if short not in EDIT_TOOLS:
            continue
        match = PATH.search(summary or "")
        if not match:
            continue
        path = match.group(1).rstrip(".,;:)")
        if path in seen:
            continue
        seen.add(path)
        out["recent"].append({"path": path, "tool": short, "at": views.iso(at)})
        if len(out["recent"]) >= 40:
            break
    return out


def listdir(store, path):
    target = allowed(store, path)
    if target is None or not target.is_dir():
        raise PermissionError("这个目录不属于任何成员的工作区。")
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
        raise PermissionError("这个文件不在任何成员的工作区里。")
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
        raise PermissionError("这个文件不在任何成员的工作区里。")
    return target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream"


def _quote(text):
    from urllib.parse import quote
    return quote(text, safe="")


def open_path(store, path):
    """Open a member's file or folder with the system (Explorer or the default app)."""
    target = allowed(store, path)
    if target is None:
        raise PermissionError("这个路径不属于任何成员的工作区。")
    if os.name == "nt":
        os.startfile(str(target))
    return {"opened": str(target)}


def roots_for_page(store):
    return [str(r) for r in roots(store)]
