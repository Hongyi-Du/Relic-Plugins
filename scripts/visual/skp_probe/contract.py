"""Pure input contracts for the bounded SKP diagnostic; no renderer or canonical output."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re

CHROMIUM_REVISION = "f842f52ef39fd97b449eb27cff414bf05a98ddce"
SKIA_REVISION = "95ee33d7ec7791ab9c071675710a14fe6408ae4f"
CHROMIUM_DEPS_URL = f"https://raw.githubusercontent.com/chromium/chromium/{CHROMIUM_REVISION}/DEPS"
SKIA_REPOSITORY = "https://skia.googlesource.com/skia.git"
DEPENDENCIES = ("buildtools", "third_party/externals/libpng", "third_party/externals/zlib")


def require_ci() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("This diagnostic may build or execute only in GitHub Actions")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def browser_binding(browser: dict, chromium_deps: str) -> dict:
    revision = browser.get("cdp", {}).get("revision")
    if revision != "@" + CHROMIUM_REVISION:
        raise ValueError(f"Unsupported actual browser revision: {revision!r}")
    matches = re.findall(r"['\"]skia_revision['\"]\s*:\s*['\"]([0-9a-f]{40})['\"]", chromium_deps)
    if matches != [SKIA_REVISION]:
        raise ValueError(f"Official Chromium DEPS has unsupported/ambiguous Skia binding: {matches}")
    if browser.get("host_platform") != "win32":
        raise ValueError("This first diagnostic supports only the actual Windows capture and DirectWrite factory")
    return {"browser": browser, "chromium_revision": CHROMIUM_REVISION,
            "chromium_deps_url": CHROMIUM_DEPS_URL,
            "chromium_deps_sha256": hashlib.sha256(chromium_deps.encode()).hexdigest(),
            "skia_revision": matches[0], "typeface_decoder": "pinned Skia DirectWrite, no last-resort FontMgr"}


def selected_dependencies(deps_source: str) -> dict:
    """Read only literal official entries; never exec a remotely retrieved DEPS file here."""
    result = {}
    for name in DEPENDENCIES:
        matches = re.findall(r"^[ \t]*['\"]" + re.escape(name) +
                             r"['\"]\s*:\s*['\"](https://[^'\"]+@[0-9a-f]{40})['\"]", deps_source, re.M)
        if len(matches) != 1:
            raise ValueError(f"Missing/ambiguous pinned official dependency: {name}")
        result[name] = matches[0]
    return result


def select_picture(case: Path, relative_picture: str) -> tuple[Path, dict]:
    """Bind one explicitly selected original SKP to its actual trace record."""
    case = case.resolve()
    path = (case / relative_picture).resolve()
    if not path.is_relative_to(case) or path.suffix.lower() != ".skp":
        raise ValueError("Selected SKP must remain inside the actual case directory")
    index = read_json(case / "pictures.json")
    entries = [p for p in index.get("pictures", []) if p.get("file") == relative_picture]
    if len(entries) != 1:
        raise ValueError("Selected SKP has no unique original pictures.json entry")
    data = path.read_bytes()
    entry = entries[0]
    if entry.get("byte_count") != len(data) or entry.get("first_16_bytes_hex") != data[:16].hex():
        raise ValueError("Selected SKP bytes do not match the actual capture receipt")
    if not data.startswith(b"skiapict"):
        raise ValueError("Selected artifact is not an SKP stream")
    return path, {"entry": entry, "byte_count": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                  "picture_extraction_errors": index.get("errors"),
                  "quantity": index.get("quantity"), "canonical_output": False,
                  "final_png_attribution": None, "dom_source_attribution": None}
