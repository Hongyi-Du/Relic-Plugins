"""Whether Codex runs the Relic plugin's hooks (relic_core/codex_trust.py); temporary folders only, no Codex."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from relic_core import codex_trust  # noqa: E402
import server  # noqa: E402

HOOKS = {"hooks": {event: [{"hooks": [{"type": "command", "command": "python relic_hook.py"}]}]
                   for event in ("SessionStart", "UserPromptSubmit", "PreToolUse", "Stop")}}
KEYS = ["hooks/codex-hooks.json:%s:0:0" % event for event in ("session_start", "user_prompt_submit", "pre_tool_use", "stop")]


class CodexTrust(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.home = self.base / "codex"
        self.home.mkdir()
        self.plugin = self.base / "relic"
        (self.plugin / ".codex-plugin").mkdir(parents=True)
        (self.plugin / "hooks").mkdir()
        (self.plugin / ".codex-plugin" / "plugin.json").write_text(json.dumps(
            {"name": "relic", "version": "9.9.9", "hooks": "./hooks/codex-hooks.json"}), encoding="utf-8")
        (self.plugin / "hooks" / "codex-hooks.json").write_text(json.dumps(HOOKS), encoding="utf-8")
        (self.plugin / "server.py").write_text("print('relic')\n", encoding="utf-8")
        codex_trust._fingerprints.clear()

    def tearDown(self):
        codex_trust._fingerprints.clear()
        self.tmp.cleanup()

    def config(self, approvals=None, enabled=True, hooks_on=True, content=None):
        lines = ['[features]', 'codex_hooks = %s' % ("true" if hooks_on else "false"), '',
                 '[plugins."relic@relic-bridge"]', 'enabled = %s' % ("true" if enabled else "false"), '']
        for key in approvals or []:
            lines += ['[hooks.state."relic@relic-bridge:%s"]' % key, 'trusted_hash = "sha256:declared"']
            if content is not False:
                lines.append('trusted_content_hash = "%s"' % (content or codex_trust.content_hash(self.plugin)))
            lines.append('')
        (self.home / "config.toml").write_text("\n".join(lines), encoding="utf-8")

    def status(self):
        codex_trust._fingerprints.clear()
        return codex_trust.status(self.home, self.plugin)

    def test_fingerprint_follows_codex_rules(self):
        flat = self.base / "flat"
        (flat / "empty").mkdir(parents=True)
        (flat / "b.txt").write_bytes(b"bee")
        (flat / "a.txt").write_bytes(b"ay")
        # Pinned so the walk, the order, the framing and the skips cannot change unnoticed. On the person's machine the
        # same code reproduced Codex's stored approval for an installed Relic exactly (sha256:f7a7b729..., 2026-11-07).
        self.assertEqual(codex_trust.content_hash(flat),
                         "sha256:" + __import__("hashlib").sha256(
                             b"codex-plugin-bundle-v1" + b"\0" * 8 + b"directory"
                             + (5).to_bytes(8, "little") + b"a.txt" + b"file" + (2).to_bytes(8, "little") + b"ay"
                             + (5).to_bytes(8, "little") + b"b.txt" + b"file" + (3).to_bytes(8, "little") + b"bee"
                             + (5).to_bytes(8, "little") + b"empty" + b"directory").hexdigest())
        before = codex_trust.content_hash(self.plugin)
        (self.plugin / "__pycache__").mkdir()
        (self.plugin / "__pycache__" / "server.cpython-314.pyc").write_bytes(b"compiled")
        (self.plugin / "notes.pyc").write_bytes(b"compiled")
        self.assertEqual(codex_trust.content_hash(self.plugin), before)  # what Python writes while Relic runs
        (self.plugin / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
        self.assertNotEqual(codex_trust.content_hash(self.plugin), before)  # dot-files count

    def test_states(self):
        self.assertEqual(self.status()["state"], "absent")  # no Codex config at all
        self.config(enabled=False)
        self.assertEqual(self.status()["state"], "absent")
        self.config()
        self.assertEqual(self.status(), {"state": "untrusted", "plugin": "relic@relic-bridge", "hooks": 4,
                                         "approved": 0, "folder": str(self.plugin)})
        self.config(KEYS)
        self.assertEqual(self.status()["state"], "trusted")
        self.config(KEYS[:3])
        self.assertEqual(self.status()["state"], "changed")  # one hook left unapproved: Codex skips it
        self.config(KEYS)
        (self.plugin / "server.py").write_text("print('relic, upgraded')\n", encoding="utf-8")  # any file
        self.assertEqual(self.status()["state"], "changed")
        self.assertEqual(self.status()["approved"], 0)
        self.config(KEYS, content=False)
        self.assertEqual(self.status()["state"], "trusted")  # a Codex that pins no content fingerprint
        self.config(KEYS, hooks_on=False)
        self.assertEqual(self.status()["state"], "off")

    def test_codex_s_own_copy_is_the_one_fingerprinted(self):
        cached = self.home / "plugins" / "cache" / "relic-bridge" / "relic" / "9.9.9"
        shutil.copytree(self.plugin, cached)
        self.config(KEYS)
        self.assertEqual(self.status()["folder"], str(cached))
        self.assertEqual(self.status()["state"], "trusted")
        (cached / "server.py").write_text("print('replaced by an upgrade')\n", encoding="utf-8")
        self.assertEqual(self.status()["state"], "changed")

    def test_a_codex_session_is_told_once_and_only_when_hooks_are_skipped(self):
        self.config(KEYS[:1])
        with mock.patch.object(codex_trust, "PLUGIN", self.plugin), \
                mock.patch.dict(os.environ, {"CODEX_HOME": str(self.home), "CODEX_THREAD_ID": "thread-1"}):
            os.environ.pop("RELIC_ACTOR", None)
            os.environ.pop("RELIC_SEAT", None)
            codex_trust._fingerprints.clear()
            text = server.instructions()
            self.assertIn("run /hooks and trust the hooks of relic@relic-bridge", text)
            self.assertIn("call inbox at the start of each turn", text)
            self.config(KEYS)
            self.assertNotIn("/hooks", server.instructions())
            self.config(KEYS[:1])
            del os.environ["CODEX_THREAD_ID"]
            self.assertNotIn("/hooks", server.instructions())  # Claude Code sessions are not Codex's concern


if __name__ == "__main__":
    unittest.main()
