"""Create/remove the local Finder launcher. No copied runtime or model credentials."""
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import shutil
import tempfile

IDENTIFIER = "ai.hongyidu.relic.launcher"
MARKER = "Contents/Resources/relic-launcher.json"
ENVIRONMENT = ("RELIC_HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "CODEX_CLI_PATH",
               "CLAUDE_CODE_EXECUTABLE", "RELIC_NODE_PATH", "RELIC_NPM_PATH")


def destination():
    return Path.home() / "Applications" / "Relic.app"


def managed(path):
    path = Path(path)
    if path.is_symlink():
        return False
    try:
        marker = json.loads((path / MARKER).read_text(encoding="utf-8"))
        return marker.get("identifier") == IDENTIFIER and marker.get("format") == 1
    except (OSError, ValueError, AttributeError):
        return False


def install(root, python, target=None, env=None):
    root, python = Path(root).resolve(), Path(python).resolve()
    target = Path(target) if target is not None else destination()
    if target.exists() or target.is_symlink():
        if not managed(target):
            raise RuntimeError("Refusing to replace an application not created by Relic: %s" % target)
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".relic-launcher-", dir=target.parent))
    backup = stage.with_name(stage.name + "-previous")
    selected = {key: str(value) for key, value in (os.environ if env is None else env).items()
                if key in ENVIRONMENT and value}
    try:
        resources = stage / "Contents/Resources"
        executable = stage / "Contents/MacOS/Relic"
        resources.mkdir(parents=True)
        executable.parent.mkdir()
        version = json.loads((root / "release.json").read_text(encoding="utf-8"))["version"]
        numeric_version = version.split("-")[0]
        if not re.fullmatch(r"\d+(?:\.\d+){0,2}", numeric_version):
            raise RuntimeError("A numeric macOS bundle version is required.")
        info = {"CFBundleIdentifier": IDENTIFIER, "CFBundleName": "Relic", "CFBundleDisplayName": "Relic",
                "CFBundleExecutable": "Relic", "CFBundlePackageType": "APPL", "CFBundleVersion": numeric_version,
                "CFBundleShortVersionString": numeric_version, "LSUIElement": True,
                "LSArchitecturePriority": ["arm64"], "NSHighResolutionCapable": True}
        (stage / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
        marker = {"format": 1, "identifier": IDENTIFIER, "root": str(root), "python": str(python), "version": version}
        (stage / MARKER).write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
        lines = ["#!/bin/sh", 'case "${1:-}" in -psn_*) shift ;; esac']
        lines += ["export %s=%s" % (key, shlex.quote(value)) for key, value in selected.items()]
        lines += ["cd -- %s || exit 1" % shlex.quote(str(root)),
                  "exec %s -X utf8 %s \"$@\"" % (shlex.quote(str(python)), shlex.quote(str(root / "scripts/open_app.py")))]
        executable.write_text("\n".join(lines) + "\n", encoding="utf-8")
        executable.chmod(0o700)
        if target.exists():
            target.rename(backup)
        try:
            stage.rename(target)
        except BaseException:
            if backup.exists():
                backup.rename(target)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        return target
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def remove(target=None):
    target = Path(target) if target is not None else destination()
    if not target.exists() and not target.is_symlink():
        return False
    if not managed(target):
        raise RuntimeError("Refusing to remove an application not created by Relic: %s" % target)
    shutil.rmtree(target)
    return True
