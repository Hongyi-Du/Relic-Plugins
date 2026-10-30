"""Isolated native ACP discovery and argv tests; no agent or model is started."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import native


class NativeHarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.env = mock.patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def file(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture, never executed")
        path.chmod(0o755)
        return path

    def test_discovery_uses_path_on_windows_macos_and_linux(self):
        for platform, suffix in (("win32", ".exe"), ("darwin", ""), ("linux", "")):
            for command, finder in (("kimi", native.find_kimi), ("dsh", native.find_deepseek)):
                with self.subTest(platform=platform, command=command):
                    executable = self.file(platform + "/installed programs/" + command + suffix)
                    with mock.patch.object(native.sys, "platform", platform), mock.patch.object(native.platform_support.shutil, "which", return_value=str(executable)) as which:
                        self.assertEqual(finder(), str(executable.resolve()))
                        which.assert_called_once_with(command)

    def test_selected_path_has_priority_over_environment_and_path(self):
        chosen = self.file("selected folder/agent.exe")
        env_program = self.file("environment folder/agent.exe")
        for finder, variable in ((native.find_kimi, "RELIC_KIMI_PATH"), (native.find_deepseek, "RELIC_DSH_PATH")):
            with self.subTest(variable=variable), mock.patch.dict(os.environ, {variable: str(env_program)}), mock.patch.object(native.platform_support.shutil, "which") as which:
                self.assertEqual(finder(str(chosen)), str(chosen.resolve()))
                which.assert_not_called()

    def test_environment_path_with_spaces_is_used_without_shell_quoting(self):
        executable = self.file("space in folder/native executable.exe")
        for finder, variable in ((native.find_kimi, "RELIC_KIMI_PATH"), (native.find_deepseek, "RELIC_DSH_PATH")):
            with self.subTest(variable=variable), mock.patch.dict(os.environ, {variable: str(executable)}):
                self.assertEqual(finder(), str(executable.resolve()))

    def test_explicit_invalid_path_does_not_fall_back(self):
        for finder, variable in ((native.find_kimi, "RELIC_KIMI_PATH"), (native.find_deepseek, "RELIC_DSH_PATH")):
            with self.subTest(variable=variable), mock.patch.object(native.platform_support.shutil, "which") as which:
                with self.assertRaisesRegex(RuntimeError, "selected"):
                    finder(str(self.root / "missing" / "program"))
                with mock.patch.dict(os.environ, {variable: str(self.root / "also missing" / "program")}):
                    with self.assertRaisesRegex(RuntimeError, variable):
                        finder()
                which.assert_not_called()

    def test_missing_path_program_returns_none(self):
        with mock.patch.object(native.platform_support, "find_executable", return_value=None):
            self.assertIsNone(native.find_kimi())
            self.assertIsNone(native.find_deepseek())

    def test_empty_override_has_actionable_error(self):
        with mock.patch.dict(os.environ, {"RELIC_KIMI_PATH": ""}):
            with self.assertRaisesRegex(RuntimeError, "RELIC_KIMI_PATH"):
                native.find_kimi()

    def test_bare_override_can_resolve_a_cli_on_path(self):
        executable = self.file("bin/custom-dsh")
        with mock.patch.dict(os.environ, {"RELIC_DSH_PATH": "custom-dsh"}), mock.patch.object(native.platform_support.shutil, "which", return_value=str(executable)):
            self.assertEqual(native.find_deepseek(), str(executable.resolve()))

    def test_macos_gui_sparse_path_uses_shared_platform_discovery(self):
        for command, finder in (("kimi", native.find_kimi), ("dsh", native.find_deepseek)):
            executable = self.file(".local/bin/" + command)
            with self.subTest(command=command), mock.patch.object(native.sys, "platform", "darwin"), \
                    mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}), \
                    mock.patch.object(native.platform_support.Path, "home", return_value=self.root), \
                    mock.patch.object(native.platform_support.shutil, "which", return_value=None), \
                    mock.patch.object(native.platform_support.subprocess, "run") as run:
                self.assertEqual(finder(), str(executable.absolute()))
                run.assert_not_called()

    def test_bare_override_uses_macos_gui_fallback(self):
        executable = self.file(".local/bin/custom-dsh")
        with mock.patch.object(native.sys, "platform", "darwin"), \
                mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin", "RELIC_DSH_PATH": "custom-dsh"}), \
                mock.patch.object(native.platform_support.Path, "home", return_value=self.root), \
                mock.patch.object(native.platform_support.shutil, "which", return_value=None):
            self.assertEqual(native.find_deepseek(), str(executable.absolute()))

    @unittest.skipIf(os.name == "nt", "POSIX executable permission check")
    def test_non_executable_explicit_path_is_rejected_without_fallback(self):
        executable = self.file("not executable/kimi")
        executable.chmod(0o600)
        with mock.patch.object(native.platform_support.shutil, "which") as which:
            with self.assertRaisesRegex(RuntimeError, "selected"):
                native.find_kimi(str(executable))
            with mock.patch.dict(os.environ, {"RELIC_DSH_PATH": str(executable)}):
                with self.assertRaisesRegex(RuntimeError, "RELIC_DSH_PATH"):
                    native.find_deepseek()
            which.assert_not_called()

    def test_cli_launch_on_all_three_platforms(self):
        for platform, suffix in (("win32", ".cmd"), ("darwin", ""), ("linux", "")):
            with self.subTest(platform=platform), mock.patch.object(native.sys, "platform", platform):
                executable = self.file(platform + "/bin with spaces/dsh" + suffix)
                self.assertEqual(native.deepseek_launch(str(executable)), ([str(executable.resolve()), "--profile", "acp"], {}))

    def test_windows_desktop_checks_archive_not_virtual_entry(self):
        executable = self.file("desktop with spaces/DeepSeek Harness.exe")
        archive = self.file("desktop with spaces/resources/app.asar")
        with mock.patch.object(native.sys, "platform", "win32"):
            argv, env = native.deepseek_launch(str(executable))
        entry = archive / "dsh/node_modules/@deepseek-ai/dsh/lib/bin.js"
        self.assertFalse(entry.is_file())
        self.assertEqual(argv, [str(executable.resolve()), "--expose-internals", str(entry), "--profile", "acp"])
        self.assertEqual(env, {"ELECTRON_RUN_AS_NODE": "1"})
        self.assertNotIn("ELECTRON_RUN_AS_NODE", os.environ)

    def test_named_desktop_without_archive_fails_clearly(self):
        executable = self.file("missing archive/DeepSeek Harness.exe")
        with mock.patch.object(native.sys, "platform", "win32"), self.assertRaisesRegex(RuntimeError, "app.asar"):
            native.deepseek_launch(str(executable))

    def test_cli_next_to_an_archive_is_not_mistaken_for_electron(self):
        executable = self.file("cli/dsh.exe")
        self.file("cli/resources/app.asar")
        with mock.patch.object(native.sys, "platform", "win32"):
            argv, env = native.deepseek_launch(str(executable))
        self.assertEqual(argv, [str(executable.resolve()), "--profile", "acp"])
        self.assertEqual(env, {})

    def test_unverified_desktop_platforms_are_not_guessed(self):
        for platform, relative in (("darwin", "DeepSeek Harness.app/Contents/MacOS/DeepSeek Harness"), ("linux", "DeepSeek-Harness.AppImage")):
            with self.subTest(platform=platform), mock.patch.object(native.sys, "platform", platform):
                executable = self.file(relative)
                with self.assertRaisesRegex(RuntimeError, "not been verified"):
                    native.deepseek_launch(str(executable))

    def test_profile_and_overlay_are_arguments_and_environment_is_unchanged(self):
        executable = self.file("native/dsh")
        overlay = self.file("patch folder/relic.patch.yml")
        selected = {"RELIC_DSH_PROFILE": "relic-test.1", "RELIC_DSH_PATCH": str(overlay), "DSH_HOME": str(self.root / "existing home")}
        with mock.patch.dict(os.environ, selected):
            before = dict(os.environ)
            argv, env = native.deepseek_launch(str(executable))
            self.assertEqual(os.environ, before)
        self.assertEqual(argv, [str(executable.resolve()), "--profile", "relic-test.1", "--patch", str(overlay.resolve())])
        self.assertEqual(env, {})
        self.assertFalse((self.root / "existing home").exists())

    def test_invalid_profile_or_missing_overlay_is_rejected(self):
        executable = self.file("dsh")
        for profile in ("", "../desktop", "a/b", "a\\b"):
            with self.subTest(profile=profile), mock.patch.dict(os.environ, {"RELIC_DSH_PROFILE": profile}):
                with self.assertRaisesRegex(RuntimeError, "RELIC_DSH_PROFILE"):
                    native.deepseek_launch(str(executable))
        for overlay in ("", str(self.root / "missing.patch.yml")):
            with self.subTest(overlay=overlay), mock.patch.dict(os.environ, {"RELIC_DSH_PATCH": overlay}):
                with self.assertRaisesRegex(RuntimeError, "RELIC_DSH_PATCH"):
                    native.deepseek_launch(str(executable))


if __name__ == "__main__":
    unittest.main()
