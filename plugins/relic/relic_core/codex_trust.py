"""Whether Codex runs the Relic plugin's hooks, so the person can be told when it stopped.

Codex approves a plugin's hooks one by one and pins each approval to a fingerprint of the plugin's whole folder
(trusted_content_hash under [hooks.state] in ~/.codex/config.toml). Every Relic upgrade changes that folder, so Codex
then skips the hooks without a word, and leaves no trace in its logs, until the person approves them again with /hooks.
Meanwhile Codex members get no messages between their own Relic calls, strict protocols are not enforced on their
tool calls, and their activity is not recorded (2026-11-06: nine Codex members worked a whole day like that after an
upgrade). The approval is the person's safeguard: Relic never approves the hooks itself and never moves code out of
the fingerprinted folder to keep an old approval alive. It notices the mismatch and says what to do.

The fingerprint is Codex's own (codex-rs/hooks/src/engine/plugin_fingerprint.rs, plugin_content_hash): SHA-256 over
b"codex-plugin-bundle-v1", then every entry depth-first, a folder before its children and the children by name in
byte order: the relative path's length in bytes (u64, little-endian) and the path (with the platform's separators;
the root is the empty path), then b"directory", or b"file" + the size (u64, little-endian) + the contents. Entries
named __pycache__ or .venv, or ending in .pyc or .egg-info, are skipped with everything in them.
"""
import hashlib
import json
import os
import re
import stat
import struct
import time
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]  # this Relic's plugin folder (plugins/relic)
HOOKS_FILE = "hooks/codex-hooks.json"
CACHE_SECONDS = 60  # the folder does not change while Relic runs from it; config.toml is read every time
STATES = ("trusted", "changed", "untrusted", "off", "absent")
_fingerprints = {}
_configs = {}  # config.toml parsed once per change: the App asks on every tool call of a Codex member it runs


def _config(path):
    info = os.stat(path)
    key = (str(path), info.st_mtime_ns, info.st_size)
    if key not in _configs:
        import tomllib
        with open(path, "rb") as handle:
            parsed = tomllib.load(handle)
        _configs.clear()
        _configs[key] = parsed
    return _configs[key]


def codex_home():
    return Path(os.getenv("CODEX_HOME") or Path.home() / ".codex")


def _skipped(name):
    return name in ("__pycache__", ".venv") or name.endswith(".pyc") or name.endswith(".egg-info")


def content_hash(root):
    """Codex's fingerprint of a plugin folder ("sha256:<hex>"); OSError for an entry Codex would refuse (a link)."""
    root = Path(root)
    digest = hashlib.sha256(b"codex-plugin-bundle-v1")
    pending = [root]
    while pending:
        path = pending.pop()
        relative = "" if path == root else str(path.relative_to(root))
        if relative and _skipped(path.name):
            continue
        name = relative.encode("utf-8", "surrogatepass")
        digest.update(struct.pack("<Q", len(name)) + name)
        info = os.lstat(path)
        if stat.S_ISDIR(info.st_mode):
            digest.update(b"directory")
            children = sorted(os.listdir(path), key=lambda child: child.encode("utf-8", "surrogatepass"))
            pending.extend(path / child for child in reversed(children))
        elif stat.S_ISREG(info.st_mode):
            digest.update(b"file" + struct.pack("<Q", info.st_size))
            digest.update(path.read_bytes())
        else:
            raise OSError("Codex does not fingerprint this kind of entry: %s" % path)
    return "sha256:" + digest.hexdigest()


def _fingerprint(root, now):
    cached = _fingerprints.get(str(root))
    if cached and now - cached[0] < CACHE_SECONDS:
        return cached[1]
    value = content_hash(root)
    _fingerprints[str(root)] = (now, value)
    return value


def _snake(event):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", event).lower()


def declared(root=PLUGIN):
    """(plugin name, version, the keys Codex records the plugin's hooks under: <hooks file>:<event>:<group>:<hook>)."""
    root = Path(root)
    manifest = json.loads((root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8-sig"))
    hooks_file = manifest.get("hooks") or HOOKS_FILE
    hooks_file = hooks_file[2:] if hooks_file.startswith("./") else hooks_file
    hooks = json.loads((root / hooks_file).read_text(encoding="utf-8-sig")).get("hooks") or {}
    keys = ["%s:%s:%d:%d" % (hooks_file, _snake(event), group, hook)
            for event, groups in hooks.items() for group, entry in enumerate(groups or [])
            for hook, _ in enumerate((entry or {}).get("hooks") or [])]
    return manifest.get("name") or "relic", manifest.get("version") or "", keys


def status(home=None, plugin=None, now=None):
    """How Codex treats the Relic plugin's hooks:
    {"state": one of STATES, "plugin": "relic@<marketplace>", "hooks": n declared, "approved": n approved for the
    current contents, "folder": the folder fingerprinted}.
      absent     Codex is not set up here, or the Relic plugin is not enabled in it: nothing to say
      off        the person switched Codex hooks off (features.codex_hooks = false)
      untrusted  the hooks were never approved
      changed    they were approved for other contents of the plugin: an upgrade since, approve them again
      trusted    every hook is approved for these contents."""
    home = Path(home) if home else codex_home()
    plugin = Path(plugin) if plugin else PLUGIN
    now = time.time() if now is None else now
    try:
        config = _config(home / "config.toml")
        name, version, keys = declared(plugin)
    except (ImportError, OSError, ValueError):
        return {"state": "absent"}
    plugins = config.get("plugins") if isinstance(config.get("plugins"), dict) else {}
    enabled = [key for key, value in plugins.items()
               if isinstance(value, dict) and key.split("@", 1)[0] == name and value.get("enabled", True)]
    if not enabled or not keys:
        return {"state": "absent"}
    selector = enabled[0]
    features = config.get("features") if isinstance(config.get("features"), dict) else {}
    if features.get("codex_hooks", True) is False:
        return {"state": "off", "plugin": selector, "hooks": len(keys), "approved": 0}
    marketplace = selector.split("@", 1)[1] if "@" in selector else ""
    cached = home / "plugins" / "cache" / marketplace / name / version
    folder = cached if marketplace and version and cached.is_dir() else plugin  # Codex's own copy, when it has one
    try:
        fingerprint = _fingerprint(folder, now)
    except OSError:
        fingerprint = None
    hooks = config.get("hooks") if isinstance(config.get("hooks"), dict) else {}
    approvals = hooks.get("state") if isinstance(hooks.get("state"), dict) else {}
    entries = [approvals.get(selector + ":" + key) for key in keys]
    approved = [e for e in entries if isinstance(e, dict) and e.get("trusted_hash")]
    # An approval without a content fingerprint comes from a Codex that did not pin one: it still counts.
    current = [e for e in approved if e.get("trusted_content_hash") in (None, fingerprint)]
    state = "trusted" if len(current) == len(keys) else "changed" if approved else "untrusted"
    return {"state": state, "plugin": selector, "hooks": len(keys), "approved": len(current), "folder": str(folder)}
