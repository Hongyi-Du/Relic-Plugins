"""Native package inspection: dummy executables are bytes, never executed."""
from pathlib import Path
import plistlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import native_package


class NativePackages(unittest.TestCase):
    def test_swift_bundle_contains_exact_shared_engine_and_executable_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); build = base / "build"; build.mkdir()
            (build / "Relic").write_bytes(b"dummy Mach-O fixture")
            files = {"plugins/relic/example.py": b"# same engine\n", "plugins/relic/relic_core/locales/zh-CN.json": b"{}"}
            archive = native_package.assemble(ROOT, build, "macos", base / "out", files)
            with zipfile.ZipFile(archive) as package:
                prefix = archive.stem + "/Relic.app/Contents/"
                info = plistlib.loads(package.read(prefix + "Info.plist"))
                self.assertEqual(info["LSMinimumSystemVersion"], "14.0")
                self.assertNotIn("LSUIElement", info)
                en = json.loads((ROOT / "plugins/relic/relic_core/locales/en-US.json").read_text(encoding="utf-8"))
                self.assertEqual(info["NSSpeechRecognitionUsageDescription"], en["native.speech_permission"])
                self.assertEqual(info["NSMicrophoneUsageDescription"], en["native.microphone_permission"])
                for code, language in (("en-US", "en"), ("zh-CN", "zh-Hans")):
                    words = json.loads((ROOT / "plugins/relic/relic_core/locales" / (code + ".json")).read_text(encoding="utf-8"))
                    text = package.read(prefix + "Resources/" + language + ".lproj/InfoPlist.strings").decode("utf-8")
                    self.assertIn(words["native.speech_permission"], text)
                    self.assertIn(words["native.microphone_permission"], text)
                self.assertEqual(package.getinfo(prefix + "MacOS/Relic").external_attr >> 16 & 0o111, 0o111)
                for name, data in files.items():
                    self.assertEqual(package.read(prefix + "Resources/engine/" + name), data)

    def test_windows_installer_compilation_is_separate_from_running_app(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); build = base / "build"; build.mkdir()
            (build / "Relic.exe").write_bytes(b"dummy PE fixture")
            compiler = base / "ISCC.exe"; compiler.write_bytes(b"mock compiler")
            with patch.object(native_package.shutil, "which", return_value=str(compiler)), \
                    patch.object(native_package.subprocess, "run") as run:
                archive = native_package.assemble(ROOT, build, "windows", base / "out", {"plugins/relic/shared.py": b"same"})
                args = run.call_args.args[0]
                self.assertEqual(args[0], str(compiler))
                self.assertTrue(args[-1].endswith("installer.iss"))
                self.assertTrue(archive.is_file())
                with zipfile.ZipFile(archive) as package:
                    self.assertEqual(package.read(archive.stem + "/plugins/relic/shared.py"), b"same")
