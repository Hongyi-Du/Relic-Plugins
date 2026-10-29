"""Finder launcher installation and removal use only temporary directories."""
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import macos_app


class MacLauncher(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.root = self.folder / "Relic 中文 ' source"
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "release.json").write_text('{"version":"1.0.0-beta.1"}', encoding="utf-8")
        (self.root / "scripts/open_app.py").write_text(
            "import json,os,sys\nprint(json.dumps({'args':sys.argv[1:],'cwd':os.getcwd(),"
            "'home':os.getenv('RELIC_HOME'),'actor':os.getenv('RELIC_ACTOR')}))\n", encoding="utf-8")
        self.target = self.folder / "Applications/Relic.app"

    def install(self, **kwargs):
        return macos_app.install(self.root, sys.executable, target=self.target, **kwargs)

    def test_bundle_has_identity_arm_priority_and_upgrade_marker(self):
        self.install(env={})
        info = plistlib.loads((self.target / "Contents/Info.plist").read_bytes())
        self.assertEqual(info["CFBundleIdentifier"], macos_app.IDENTIFIER)
        self.assertEqual(info["CFBundleVersion"], "1.0.0")
        self.assertEqual(info["LSArchitecturePriority"], ["arm64"])
        self.assertTrue(macos_app.managed(self.target))
        self.assertEqual(json.loads((self.target / macos_app.MARKER).read_text())["version"], "1.0.0-beta.1")
        self.assertEqual(json.loads((self.target / macos_app.MARKER).read_text())["root"], str(self.root.resolve()))

    @unittest.skipIf(os.name == "nt", "the macOS launcher is a POSIX shell executable")
    def test_launcher_preserves_arguments_and_only_copies_allowed_install_environment(self):
        data = self.folder / "Data $literal ' 中文"
        self.install(env={"RELIC_HOME":str(data), "RELIC_ACTOR":"must-not-persist", "SECRET_TOKEN":"must-not-persist"})
        script = self.target / "Contents/MacOS/Relic"
        self.assertNotIn("must-not-persist", script.read_text())
        proc = subprocess.run([str(script), "--no-window", "literal ' $(touch nope)"], capture_output=True,
                              text=True, check=True, env={"PATH":"/usr/bin:/bin"})
        result = json.loads(proc.stdout)
        self.assertEqual(result["args"], ["--no-window", "literal ' $(touch nope)"])
        self.assertEqual(result["cwd"], str(self.root.resolve()))
        self.assertEqual(result["home"], str(data))
        self.assertIsNone(result["actor"])
        self.assertFalse((self.root / "nope").exists())

    def test_reinstall_replaces_only_the_managed_launcher_and_remove_keeps_data(self):
        data = self.folder / "data"
        data.mkdir()
        (data / "relic.sqlite3").write_bytes(b"organization fixture")
        self.install(env={"RELIC_HOME":str(data)})
        (self.target / "old-file").write_text("old version")
        self.install(env={"RELIC_HOME":str(data)})
        self.assertFalse((self.target / "old-file").exists())
        self.assertTrue(macos_app.remove(self.target))
        self.assertFalse(macos_app.remove(self.target))
        self.assertEqual((data / "relic.sqlite3").read_bytes(), b"organization fixture")
        self.assertFalse(list(self.target.parent.glob(".relic-launcher-*")))

    def test_unmanaged_app_is_neither_replaced_nor_removed(self):
        self.target.mkdir(parents=True)
        sentinel = self.target / "user-file"
        sentinel.write_text("keep")
        with self.assertRaisesRegex(RuntimeError, "not created by Relic"):
            self.install(env={})
        with self.assertRaisesRegex(RuntimeError, "not created by Relic"):
            macos_app.remove(self.target)
        self.assertEqual(sentinel.read_text(), "keep")

    @unittest.skipIf(os.name == "nt", "symlink privilege differs on Windows")
    def test_symlink_app_is_refused(self):
        self.install(env={})
        link = self.folder / "linked.app"
        link.symlink_to(self.target, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "not created by Relic"):
            macos_app.remove(link)
        self.assertTrue(self.target.is_dir())
